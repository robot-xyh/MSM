"""Offline learning-data export for one truth-isolated scalable 3D episode."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time
from typing import Any, Iterable, Mapping

from .episode_bus import EpisodeManifest, jsonable
from .models import OfflineTruthLabel, ScenarioConfig
from .module_stack import IntegratedLearningArtifacts


LEARNING_EXPORT_SCHEMA_VERSION = "scalable3d-learning-export-v2"


class BatchLearningArtifactWriter:
    """Stage whole episodes and finalize split-safe multi-seed learning datasets."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        formal: bool = False,
        resume: bool = False,
    ) -> None:
        self.root = Path(output_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self._formal = bool(formal)
        self._staging_root = self.root / "_staging"
        self._d3_staging_path = self._staging_root / "d3_frames.jsonl"
        self._d4_staging_root = self._staging_root / "d4_region_episodes"
        self._episode_index_path = self._staging_root / "episodes.jsonl"
        self._episode_rows: list[Mapping[str, Any]] = []
        self._episode_ids: set[str] = set()
        self._episode_count = 0
        self._d3_frame_count = 0
        self._d4_frame_count = 0
        self._d5_frame_count = 0
        self._d5_active_vision_frame_count = 0
        self._seed_groups: set[tuple[str, int]] = set()
        if resume:
            self._restore_staging_state()
            return
        self._staging_root.mkdir(parents=True, exist_ok=True)
        if self._d3_staging_path.exists() or self._episode_index_path.exists():
            raise FileExistsError(
                "batch learning output already contains staging files; use a fresh output"
            )

    @property
    def episode_rows(self) -> tuple[Mapping[str, Any], ...]:
        """Return the indexed, fully staged episodes in durable order."""

        return tuple(dict(row) for row in self._episode_rows)

    def _restore_staging_state(self) -> None:
        if not self._staging_root.is_dir() or not self._episode_index_path.is_file():
            raise FileNotFoundError(
                "resumable batch output is missing _staging/episodes.jsonl"
            )
        if (self.root / "episodes.jsonl").exists() or (
            self.root / "batch_learning_export_summary.json"
        ).exists():
            raise RuntimeError("batch learning output is already finalized")
        rows = _read_jsonl_objects(self._episode_index_path)
        if not rows:
            raise RuntimeError("resumable batch staging contains no indexed episodes")
        required = {
            "episode_id",
            "scenario_version",
            "seed",
            "d3_exported_frame_count",
            "d4_captured_frame_count",
            "d5_staged_frame_count",
            "d5_active_vision_staged_frame_count",
        }
        for row in rows:
            if not required.issubset(row):
                raise RuntimeError("staged episode index is missing required fields")
            episode_id = str(row["episode_id"])
            if not episode_id or episode_id in self._episode_ids:
                raise RuntimeError("staged episode index contains duplicate episode IDs")
            self._episode_ids.add(episode_id)
            self._episode_rows.append(dict(row))
            self._episode_count += 1
            self._d3_frame_count += int(row["d3_exported_frame_count"])
            self._d4_frame_count += int(row["d4_captured_frame_count"])
            self._d5_frame_count += int(row["d5_staged_frame_count"])
            self._d5_active_vision_frame_count += int(
                row["d5_active_vision_staged_frame_count"]
            )
            self._seed_groups.add(
                (str(row["scenario_version"]), int(row["seed"]))
            )
        self._audit_staging_counts()

    def _audit_staging_counts(self) -> None:
        actual_d3 = _line_count(self._d3_staging_path)
        actual_d4 = len(tuple(self._d4_staging_root.rglob("*.jsonl")))
        actual_d5 = len(
            tuple((self.root / "d5_tracklet_graph" / "episodes").glob("*.episode.json"))
        )
        actual_active = len(
            tuple((self.root / "d5_active_vision" / "episodes").glob("*.episode.json"))
        )
        expected_active = sum(
            int(row["d5_active_vision_staged_frame_count"]) > 0
            for row in self._episode_rows
        )
        expected = (
            self._d3_frame_count,
            sum(
                int(row["d4_captured_frame_count"]) > 0
                for row in self._episode_rows
            ),
            self._d5_frame_count,
            expected_active,
        )
        actual = (actual_d3, actual_d4, actual_d5, actual_active)
        if actual != expected:
            raise RuntimeError(
                "batch staging contains unindexed or incomplete episode artifacts: "
                f"expected={expected}, actual={actual}"
            )

    def stage_episode(
        self,
        *,
        config: ScenarioConfig,
        manifest: EpisodeManifest,
        artifacts: IntegratedLearningArtifacts,
        offline_truth_labels: Iterable[OfflineTruthLabel],
        online_messages: Iterable[Any] = (),
    ) -> Mapping[str, Any]:
        """Append one complete episode without splitting frames across datasets."""

        if manifest.episode_id in self._episode_ids:
            raise ValueError(f"episode is already staged: {manifest.episode_id}")

        d3_started = time.perf_counter()
        records, unavailable = _build_d3_records(
            config=config,
            manifest=manifest,
            planning_frames=artifacts.d3_planning_frames,
        )
        with self._d3_staging_path.open("a", encoding="utf-8") as stream:
            for record in records:
                stream.write(
                    json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
                )
        d3_stage_wall_s = time.perf_counter() - d3_started
        d4_started = time.perf_counter()
        _, d4_summary = _stage_d4_learning_episode(
            self._d4_staging_root,
            config=config,
            manifest=manifest,
            frames=artifacts.d4_region_frames,
        )
        d4_stage_wall_s = time.perf_counter() - d4_started
        d5_graph_started = time.perf_counter()
        _, d5_summary = _write_d5_frames(
            self.root / "d5_tracklet_graph",
            config=config,
            manifest=manifest,
            graph_frames=artifacts.d5_graph_frames,
            offline_truth_labels=tuple(offline_truth_labels),
            generation_config={
                "schema_version": LEARNING_EXPORT_SCHEMA_VERSION,
                "source": "scalable_3d_multi_seed_batch",
                "truth_join": "offline_observation_id_to_anonymous_tracklet_v1",
            },
        )
        d5_graph_stage_wall_s = time.perf_counter() - d5_graph_started
        d5_active_started = time.perf_counter()
        _, d5_active_summary = _write_d5_active_vision_episode(
            self.root / "d5_active_vision",
            config=config,
            manifest=manifest,
            active_vision_frames=artifacts.d5_active_vision_frames,
            online_messages=tuple(online_messages),
            generation_config={
                "schema_version": LEARNING_EXPORT_SCHEMA_VERSION,
                "source": "scalable_3d_multi_seed_batch",
                "recording_mode": "whole_episode",
                "offline_reward_policy": "explicit_unavailable_until_d6_join",
            },
        )
        d5_active_stage_wall_s = time.perf_counter() - d5_active_started
        episode_row = {
            "episode_id": manifest.episode_id,
            "scenario_version": config.scenario_version,
            "seed": config.seed,
            "config_sha256": manifest.config_sha256,
            "d3_exported_frame_count": len(records),
            "d3_unavailable_reason_counts": dict(sorted(unavailable.items())),
            "d4_captured_frame_count": int(d4_summary["captured_frame_count"]),
            "d5_staged_frame_count": int(d5_summary["staged_frame_count"]),
            "d5_active_vision_staged_frame_count": int(
                d5_active_summary["staged_frame_count"]
            ),
            "d3_stage_wall_s": d3_stage_wall_s,
            "d4_stage_wall_s": d4_stage_wall_s,
            "d5_graph_stage_wall_s": d5_graph_stage_wall_s,
            "d5_active_vision_stage_wall_s": d5_active_stage_wall_s,
        }
        with self._episode_index_path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(episode_row, ensure_ascii=False, sort_keys=True) + "\n"
            )
        self._episode_count += 1
        self._episode_ids.add(manifest.episode_id)
        self._episode_rows.append(dict(episode_row))
        self._d3_frame_count += len(records)
        self._d4_frame_count += int(d4_summary["captured_frame_count"])
        self._d5_frame_count += int(d5_summary["staged_frame_count"])
        self._d5_active_vision_frame_count += int(
            d5_active_summary["staged_frame_count"]
        )
        self._seed_groups.add((config.scenario_version, int(config.seed)))
        return episode_row

    def finalize(self) -> dict[str, Path]:
        """Write dataset manifests only after whole-seed staging is complete."""

        if self._episode_count == 0:
            raise ValueError("cannot finalize an empty batch learning export")
        paths: dict[str, Path] = {}
        d3_split_counts: Mapping[str, int] = {}
        if self._d3_frame_count:
            from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
                iter_learning_frame_records,
                write_learning_dataset,
            )

            manifest = write_learning_dataset(
                self.root / "d3_assignment",
                iter_learning_frame_records(self._d3_staging_path),
                source_kind="scalable_3d_multi_seed_batch",
                minimum_unseen_seed_count=20 if self._formal else 1,
            )
            d3_split_counts = dict(manifest.split_frame_counts)
            paths["d3_manifest"] = self.root / "d3_assignment" / "dataset_manifest.json"
            paths["d3_frames"] = self.root / "d3_assignment" / "frames.jsonl"

        d4_finalized = False
        d4_reason: str | None = None
        d4_availability: Mapping[str, Any] = {}
        if self._d4_frame_count and len({seed for _, seed in self._seed_groups}) >= 3:
            from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
                finalize_region_learning_dataset,
            )

            d4_manifest = finalize_region_learning_dataset(
                self._d4_staging_root,
                self.root / "d4_region",
                created_at_utc=_utc_now(),
                split_seed=20260720,
                minimum_unseen_seeds=20 if self._formal else 2,
            )
            paths["d4_manifest"] = self.root / "d4_region" / "manifest.json"
            d4_availability = d4_manifest.availability.to_dict()
            d4_finalized = True
            shutil.rmtree(self._d4_staging_root)
        elif self._d4_frame_count:
            d4_reason = "requires_at_least_three_unique_numeric_seeds"
        else:
            d4_reason = "no_d4_region_learning_frames"

        d5_finalized = False
        d5_reason: str | None = None
        d5_graph_seed_count = _staged_d5_graph_seed_count(
            self.root / "d5_tracklet_graph"
        )
        if self._d5_frame_count and d5_graph_seed_count >= 3:
            from research_modules.d5_terminal_association.src.d5_terminal_association.tracklet_dataset import (
                finalize_tracklet_dataset,
            )

            finalize_tracklet_dataset(self.root / "d5_tracklet_graph")
            paths["d5_manifest"] = (
                self.root / "d5_tracklet_graph" / "manifest.json"
            )
            d5_finalized = True
        elif self._d5_frame_count:
            d5_reason = "requires_at_least_three_unique_nonempty_graph_seeds"
        else:
            d5_reason = "no_nonempty_d5_graph_frames"

        d5_active_finalized = False
        d5_active_reason: str | None = None
        if self._d5_active_vision_frame_count:
            from research_modules.d5_terminal_association.src.d5_terminal_association import (
                ActiveVisionDatasetValidationError,
                finalize_active_vision_episode_dataset,
            )

            try:
                finalize_active_vision_episode_dataset(
                    self.root / "d5_active_vision"
                )
            except ActiveVisionDatasetValidationError as exc:
                d5_active_reason = exc.code
            else:
                paths["d5_active_vision_manifest"] = (
                    self.root / "d5_active_vision" / "manifest.json"
                )
                d5_active_finalized = True
        else:
            d5_active_reason = "no_active_vision_decision_frames"

        summary = {
            "schema_version": LEARNING_EXPORT_SCHEMA_VERSION,
            "episode_count": self._episode_count,
            "scenario_seed_group_count": len(self._seed_groups),
            "d3_frame_count": self._d3_frame_count,
            "d3_split_frame_counts": dict(d3_split_counts),
            "d4_frame_count": self._d4_frame_count,
            "d4_dataset_finalized": d4_finalized,
            "d4_dataset_finalization_reason": d4_reason,
            "d4_dataset_availability": dict(d4_availability),
            "d5_staged_frame_count": self._d5_frame_count,
            "d5_nonempty_graph_seed_count": d5_graph_seed_count,
            "d5_dataset_finalized": d5_finalized,
            "d5_dataset_finalization_reason": d5_reason,
            "d5_active_vision_frame_count": self._d5_active_vision_frame_count,
            "d5_active_vision_dataset_finalized": d5_active_finalized,
            "d5_active_vision_dataset_finalization_reason": d5_active_reason,
            "online_truth_policy": "forbidden",
            "d5_label_policy": "separate_evaluator_artifact",
        }
        summary_path = self.root / "batch_learning_export_summary.json"
        _write_json(summary_path, summary)
        paths["summary"] = summary_path

        if self._d3_staging_path.exists():
            self._d3_staging_path.unlink()
        episode_index_path = self.root / "episodes.jsonl"
        self._episode_index_path.replace(episode_index_path)
        paths["episode_index"] = episode_index_path
        try:
            self._staging_root.rmdir()
        except OSError:
            # Unfinalized D4 episode data remains recoverable in staging.
            pass
        return paths


def write_episode_learning_artifacts(
    output_dir: str | Path,
    *,
    config: ScenarioConfig,
    manifest: EpisodeManifest,
    artifacts: IntegratedLearningArtifacts,
    offline_truth_labels: Iterable[OfflineTruthLabel],
    online_messages: Iterable[Any] = (),
) -> dict[str, Path]:
    """Persist D3/D4 truth-free features and physically separate D5 labels."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    summary: dict[str, Any] = {
        "schema_version": LEARNING_EXPORT_SCHEMA_VERSION,
        "episode_id": manifest.episode_id,
        "scenario_version": config.scenario_version,
        "seed": config.seed,
        "config_sha256": manifest.config_sha256,
        "online_truth_policy": "forbidden",
        "d5_label_policy": "separate_evaluator_artifact",
    }

    d3_paths, d3_summary = _write_d3_frames(
        root / "d3_assignment",
        config=config,
        manifest=manifest,
        planning_frames=artifacts.d3_planning_frames,
    )
    paths.update({f"d3_{key}": value for key, value in d3_paths.items()})
    summary["d3"] = d3_summary

    d4_path, d4_summary = _write_d4_frames(
        root / "d4_region_frames.jsonl",
        artifacts.d4_region_frames,
    )
    if d4_path is not None:
        paths["d4_frames"] = d4_path
    summary["d4"] = d4_summary

    d5_paths, d5_summary = _write_d5_frames(
        root / "d5_tracklet_graph",
        config=config,
        manifest=manifest,
        graph_frames=artifacts.d5_graph_frames,
        offline_truth_labels=tuple(offline_truth_labels),
    )
    paths.update({f"d5_{key}": value for key, value in d5_paths.items()})
    summary["d5"] = d5_summary

    d5_active_paths, d5_active_summary = _write_d5_active_vision_episode(
        root / "d5_active_vision",
        config=config,
        manifest=manifest,
        active_vision_frames=artifacts.d5_active_vision_frames,
        online_messages=tuple(online_messages),
    )
    paths.update(
        {f"d5_active_vision_{key}": value for key, value in d5_active_paths.items()}
    )
    summary["d5_active_vision"] = d5_active_summary

    summary_path = root / "learning_export_summary.json"
    _write_json(summary_path, summary)
    paths["summary"] = summary_path
    return paths


def _write_d3_frames(
    root: Path,
    *,
    config: ScenarioConfig,
    manifest: EpisodeManifest,
    planning_frames: tuple[Any, ...],
) -> tuple[dict[str, Path], dict[str, Any]]:
    records, unavailable_reasons = _build_d3_records(
        config=config,
        manifest=manifest,
        planning_frames=planning_frames,
    )
    if not records:
        return {}, {
            "captured_frame_count": len(planning_frames),
            "exported_frame_count": 0,
            "unavailable_reason_counts": dict(sorted(unavailable_reasons.items())),
        }
    root.mkdir(parents=True, exist_ok=True)
    staging_path = root / "staging_frames.jsonl"
    with staging_path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(
                json.dumps(record.to_dict(), ensure_ascii=True, sort_keys=True) + "\n"
            )
    return {
        "staging_frames": staging_path,
    }, {
        "captured_frame_count": len(planning_frames),
        "exported_frame_count": len(records),
        "dataset_finalized": False,
        "dataset_finalization_reason": "requires_complete_multi_seed_catalog",
        "unavailable_reason_counts": dict(sorted(unavailable_reasons.items())),
    }


def _build_d3_records(
    *,
    config: ScenarioConfig,
    manifest: EpisodeManifest,
    planning_frames: tuple[Any, ...],
) -> tuple[list[Any], Counter[str]]:
    from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
        build_learning_frame_record,
    )

    records: list[Any] = []
    unavailable_reasons: Counter[str] = Counter()
    for frame_index, evidence in enumerate(planning_frames):
        if not bool(getattr(evidence, "available", False)):
            unavailable_reasons[str(getattr(evidence, "reason", "unavailable"))] += 1
            continue
        required = (
            getattr(evidence, "timestamp_s", None),
            getattr(evidence, "rule_matrix_result", None),
            getattr(evidence, "plan", None),
        )
        if any(value is None for value in required):
            unavailable_reasons["incomplete_planning_evidence"] += 1
            continue
        records.append(
            build_learning_frame_record(
                scenario_version=config.scenario_version,
                seed=config.seed,
                episode=manifest.episode_id,
                frame_index=frame_index,
                timestamp_s=float(evidence.timestamp_s),
                matrix_result=evidence.rule_matrix_result,
                tracks=evidence.tracks,
                resources=evidence.resources,
                plan=evidence.plan,
                previous_plan=evidence.previous_plan,
            )
        )
    return records, unavailable_reasons


def _write_d4_frames(
    path: Path,
    frames: tuple[Any, ...],
) -> tuple[Path | None, dict[str, Any]]:
    if not frames:
        return None, {"captured_frame_count": 0, "recommendation_frame_count": 0}
    path.parent.mkdir(parents=True, exist_ok=True)
    recommendation_count = 0
    with path.open("w", encoding="utf-8") as stream:
        for frame in frames:
            recommendation = frame.recommendation
            recommendation_count += int(recommendation is not None)
            stream.write(
                json.dumps(
                    {
                        "schema_version": LEARNING_EXPORT_SCHEMA_VERSION,
                        "frame_index": int(frame.frame_index),
                        "timestamp_s": float(frame.timestamp_s),
                        "snapshot": jsonable(frame.snapshot),
                        "recommendation": (
                            None if recommendation is None else jsonable(recommendation)
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    return path, {
        "captured_frame_count": len(frames),
        "recommendation_frame_count": recommendation_count,
        "formal_decision_mutation_count": 0,
    }


def _stage_d4_learning_episode(
    root: Path,
    *,
    config: ScenarioConfig,
    manifest: EpisodeManifest,
    frames: tuple[Any, ...],
) -> tuple[Path | None, dict[str, Any]]:
    """Stage one truth-free D4 episode with explicit target/reward availability."""

    if not frames:
        return None, {
            "captured_frame_count": 0,
            "target_available_count": 0,
            "target_unavailable_count": 0,
            "reward_available_count": 0,
            "reward_unavailable_count": 0,
        }
    from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
        RecommendationSource,
        RegionLearningEpisodeSource,
        RegionLearningFrame,
        RegionLearningReward,
        RegionLearningTarget,
        RegionLearningTargetKind,
        stage_region_learning_episode,
    )

    source = RegionLearningEpisodeSource(
        scenario_id=config.scenario_name,
        scenario_version=config.scenario_version,
        scenario_scale=f"M{config.target_count}N{config.resource_count}",
        seed=config.seed,
        episode_id=manifest.episode_id,
        git_commit=manifest.git_commit,
        git_dirty=manifest.repository_dirty,
        config_sha256=manifest.config_sha256,
    )
    records = []
    target_available_count = 0
    for frame in sorted(frames, key=lambda item: int(item.frame_index)):
        advisory_result = frame.recommendation
        recommendation = (
            None
            if advisory_result is None
            else getattr(advisory_result, "recommendation", None)
        )
        if (
            recommendation is not None
            and recommendation.source == RecommendationSource.RULE
        ):
            target = RegionLearningTarget.available(
                RegionLearningTargetKind.RULE,
                recommendation,
            )
            target_available_count += 1
        else:
            target = RegionLearningTarget.unavailable(
                "rule_target_not_emitted"
                if recommendation is None
                else "non_rule_target_not_admitted"
            )
        records.append(
            RegionLearningFrame(
                frame_index=int(frame.frame_index),
                timestamp_s=float(frame.timestamp_s),
                snapshot=frame.snapshot,
                target=target,
                reward=RegionLearningReward.unavailable(
                    "d6_episode_outcome_not_joined"
                ),
                recommendation=recommendation,
            )
        )
    staged = stage_region_learning_episode(root, source, records)
    frame_count = len(records)
    return staged.path, {
        "captured_frame_count": frame_count,
        "target_available_count": target_available_count,
        "target_unavailable_count": frame_count - target_available_count,
        "reward_available_count": 0,
        "reward_unavailable_count": frame_count,
    }


def _write_d5_frames(
    root: Path,
    *,
    config: ScenarioConfig,
    manifest: EpisodeManifest,
    graph_frames: tuple[Any, ...],
    offline_truth_labels: tuple[OfflineTruthLabel, ...],
    generation_config: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Path], dict[str, Any]]:
    from research_modules.d5_terminal_association.src.d5_terminal_association.tracklet_dataset import (
        join_offline_observation_labels,
        stage_tracklet_dataset_episode,
    )

    label_by_observation: dict[str, OfflineTruthLabel] = {}
    for label in offline_truth_labels:
        if label.observation_id in label_by_observation:
            raise ValueError(f"duplicate offline observation label: {label.observation_id}")
        label_by_observation[label.observation_id] = label

    staged_count = 0
    skipped_empty_count = 0
    complete_count = 0
    missing_tracklet_count = 0
    resolved_generation_config: Mapping[str, Any] = (
        {
            "schema_version": LEARNING_EXPORT_SCHEMA_VERSION,
            "scenario_version": config.scenario_version,
            "config_sha256": manifest.config_sha256,
            "source": "scalable_3d_integrated_episode",
            "truth_join": "offline_observation_id_to_anonymous_tracklet_v1",
        }
        if generation_config is None
        else generation_config
    )
    for frame in graph_frames:
        graph = frame.graph
        if int(getattr(graph, "node_count", 0)) == 0:
            skipped_empty_count += 1
            continue
        source_ids = {
            str(node.source_observation_id)
            for node in graph.nodes
            if getattr(node, "source_observation_id", None) is not None
        }
        frame_labels = tuple(
            label_by_observation[source_id]
            for source_id in sorted(source_ids)
            if source_id in label_by_observation
        )
        joined = join_offline_observation_labels(graph, frame_labels)
        complete_count += int(joined.labels_complete)
        missing_tracklet_count += len(joined.missing_tracklet_keys)
        stage_tracklet_dataset_episode(
            root,
            graph,
            joined.tracklet_labels,
            scenario_version=config.scenario_version,
            seed=config.seed,
            episode_id=(
                f"{manifest.episode_id}-d5-frame-{int(frame.frame_index):06d}"
            ),
            generation_config=resolved_generation_config,
            labels_complete=joined.labels_complete,
            candidate_recall_available=joined.labels_complete,
            hard_negative_provenance={
                "source": "online_geometric_candidate_gate",
                "truth_use": "offline_label_only",
                "frame_index": int(frame.frame_index),
            },
        )
        staged_count += 1
    if staged_count == 0:
        return {}, {
            "captured_frame_count": len(graph_frames),
            "staged_frame_count": 0,
            "skipped_empty_frame_count": skipped_empty_count,
            "complete_label_frame_count": 0,
            "missing_tracklet_label_count": 0,
        }
    return {
        "config": root / "dataset_config.json",
        "staging_root": root,
    }, {
        "captured_frame_count": len(graph_frames),
        "staged_frame_count": staged_count,
        "skipped_empty_frame_count": skipped_empty_count,
        "complete_label_frame_count": complete_count,
        "missing_tracklet_label_count": missing_tracklet_count,
        "dataset_finalized": False,
        "dataset_finalization_reason": "requires_at_least_three_scenario_seed_groups",
    }


def _write_d5_active_vision_episode(
    root: Path,
    *,
    config: ScenarioConfig,
    manifest: EpisodeManifest,
    active_vision_frames: tuple[Any, ...],
    online_messages: tuple[Any, ...] = (),
    generation_config: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Path], dict[str, Any]]:
    """Stage one complete D5 active-vision episode with detached labels."""

    if not active_vision_frames:
        return {}, {
            "captured_frame_count": 0,
            "staged_frame_count": 0,
            "sample_count": 0,
            "offline_reward_status": "unavailable",
        }
    from research_modules.d5_terminal_association.src.d5_terminal_association import (
        ActiveVisionEpisodeRecordV1,
        ActiveVisionRuntimeAckV1,
        ActiveVisionSourceIdentityV1,
        active_vision_sample_from_decision,
        stage_active_vision_episode_record,
        stage_active_vision_offline_labels,
        unavailable_active_vision_offline_labels,
    )

    acknowledgements = _active_vision_acknowledgements(online_messages)
    samples = []
    joined_ack_count = 0
    accepted_ack_count = 0
    rejected_ack_count = 0
    for frame in sorted(
        active_vision_frames,
        key=lambda item: (int(item.frame_index), float(item.timestamp_s)),
    ):
        feedback_by_camera = {
            item.camera_state.camera_id: item for item in frame.camera_feedback
        }
        for decision in sorted(
            frame.decisions,
            key=lambda item: item.effective_action.camera_id,
        ):
            camera_id = decision.effective_action.camera_id
            feedback = feedback_by_camera.get(camera_id)
            if feedback is None:
                raise ValueError(
                    f"active-vision frame is missing camera feedback: {camera_id}"
                )
            sequence_index = len(samples)
            key_prefix = (
                f"{manifest.episode_id}:active-vision:"
                f"{int(frame.frame_index):06d}:{camera_id}"
            )
            ack_payload = acknowledgements.pop(
                (
                    camera_id,
                    float(frame.timestamp_s),
                    int(decision.plan_version),
                    int(decision.coalition_version),
                    int(decision.communication_version),
                ),
                None,
            )
            runtime_ack = None
            if ack_payload is not None:
                runtime_ack = ActiveVisionRuntimeAckV1(
                    sample_key=key_prefix,
                    camera_id=camera_id,
                    command_version=int(ack_payload["command_version"]),
                    ack_timestamp=float(ack_payload["ack_timestamp"]),
                    accepted=bool(ack_payload["status"] == "applied"),
                    status_code=str(ack_payload["reason"]),
                    plan_version=int(ack_payload["plan_version"]),
                    coalition_version=int(ack_payload["coalition_version"]),
                    communication_version=int(
                        ack_payload["communication_version"]
                    ),
                )
                joined_ack_count += 1
                accepted_ack_count += int(runtime_ack.accepted)
                rejected_ack_count += int(not runtime_ack.accepted)
            samples.append(
                active_vision_sample_from_decision(
                    sample_key=key_prefix,
                    observation_key=f"{key_prefix}:observation",
                    sequence_index=sequence_index,
                    camera_id=camera_id,
                    snapshot=frame.snapshot,
                    decision=decision,
                    camera_feedback=feedback,
                    runtime_ack=runtime_ack,
                )
            )
    if acknowledgements:
        raise ValueError(
            "active-vision runtime ACKs did not match a captured learning decision"
        )
    record = ActiveVisionEpisodeRecordV1(
        scenario_version=config.scenario_version,
        seed=config.seed,
        episode_id=manifest.episode_id,
        source_identity=ActiveVisionSourceIdentityV1(
            git_commit=manifest.git_commit,
            git_dirty=manifest.repository_dirty,
            config_sha256=manifest.config_sha256,
        ),
        samples=tuple(samples),
        synthetic_fixture=True,
    )
    descriptor = stage_active_vision_episode_record(
        root,
        record,
        generation_config=(
            {
                "schema_version": LEARNING_EXPORT_SCHEMA_VERSION,
                "source": "scalable_3d_integrated_episode",
                "recording_mode": "whole_episode",
                "offline_reward_policy": (
                    "explicit_unavailable_until_d6_join"
                ),
            }
            if generation_config is None
            else generation_config
        ),
    )
    descriptor = stage_active_vision_offline_labels(
        root,
        record.episode_uid,
        unavailable_active_vision_offline_labels(record),
    )
    if joined_ack_count == len(samples):
        runtime_ack_status = "joined"
    elif joined_ack_count:
        runtime_ack_status = "partial"
    else:
        runtime_ack_status = "not_joined"
    return {
        "config": root / "dataset_config.json",
        "online_record": root / str(descriptor["online_file"]),
        "offline_labels": root / str(descriptor["offline_file"]),
        "descriptor": root / "episodes" / f"{record.episode_uid}.episode.json",
    }, {
        "captured_frame_count": len(active_vision_frames),
        "staged_frame_count": len(active_vision_frames),
        "sample_count": len(samples),
        "offline_reward_status": "unavailable",
        "runtime_ack_status": runtime_ack_status,
        "runtime_ack_count": joined_ack_count,
        "runtime_ack_accepted_count": accepted_ack_count,
        "runtime_ack_rejected_count": rejected_ack_count,
        "dataset_finalized": False,
        "dataset_finalization_reason": "requires_multi_seed_offline_join",
    }


def _active_vision_acknowledgements(
    online_messages: tuple[Any, ...],
) -> dict[tuple[str, float, int, int, int], Mapping[str, Any]]:
    """Index truth-free camera ACKs by the decision identity used at export."""

    acknowledgements: dict[
        tuple[str, float, int, int, int], Mapping[str, Any]
    ] = {}
    required = {
        "camera_id",
        "issued_timestamp",
        "ack_timestamp",
        "plan_version",
        "coalition_version",
        "communication_version",
        "command_version",
        "status",
        "reason",
    }
    for message in online_messages:
        if getattr(message, "topic", None) != "runtime.camera_command_ack":
            continue
        payload = getattr(message, "payload", None)
        if not isinstance(payload, Mapping) or not required.issubset(payload):
            raise ValueError("active-vision runtime ACK payload is incomplete")
        key = (
            str(payload["camera_id"]),
            float(payload["issued_timestamp"]),
            int(payload["plan_version"]),
            int(payload["coalition_version"]),
            int(payload["communication_version"]),
        )
        if key in acknowledgements:
            raise ValueError("duplicate active-vision runtime ACK identity")
        if int(payload["command_version"]) != int(
            payload["communication_version"]
        ):
            raise ValueError(
                "active-vision command version must equal its communication version"
            )
        acknowledgements[key] = payload
    return acknowledgements


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_jsonl_objects(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                raise RuntimeError(f"blank JSONL row in {path} at line {line_number}")
            payload = json.loads(line)
            if not isinstance(payload, Mapping):
                raise RuntimeError(
                    f"JSONL row is not an object in {path} at line {line_number}"
                )
            rows.append(payload)
    return rows


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as stream:
        return sum(1 for _ in stream)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _staged_d5_graph_seed_count(root: Path) -> int:
    seeds: set[int] = set()
    for path in sorted((root / "episodes").glob("*.episode.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or "seed" not in payload:
            raise ValueError(f"invalid D5 staged episode descriptor: {path}")
        seeds.add(int(payload["seed"]))
    return len(seeds)


__all__ = [
    "BatchLearningArtifactWriter",
    "LEARNING_EXPORT_SCHEMA_VERSION",
    "write_episode_learning_artifacts",
]
