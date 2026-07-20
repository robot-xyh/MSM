"""Offline learning-data export for one truth-isolated scalable 3D episode."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .episode_bus import EpisodeManifest, jsonable
from .models import OfflineTruthLabel, ScenarioConfig
from .module_stack import IntegratedLearningArtifacts


LEARNING_EXPORT_SCHEMA_VERSION = "scalable3d-learning-export-v1"


class BatchLearningArtifactWriter:
    """Stage whole episodes and finalize split-safe multi-seed learning datasets."""

    def __init__(self, output_dir: str | Path) -> None:
        self.root = Path(output_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self._staging_root = self.root / "_staging"
        self._staging_root.mkdir(parents=True, exist_ok=True)
        self._d3_staging_path = self._staging_root / "d3_frames.jsonl"
        self._episode_index_path = self._staging_root / "episodes.jsonl"
        if self._d3_staging_path.exists() or self._episode_index_path.exists():
            raise FileExistsError(
                "batch learning output already contains staging files; use a fresh output"
            )
        self._episode_count = 0
        self._d3_frame_count = 0
        self._d4_frame_count = 0
        self._d5_frame_count = 0
        self._seed_groups: set[tuple[str, int]] = set()

    def stage_episode(
        self,
        *,
        config: ScenarioConfig,
        manifest: EpisodeManifest,
        artifacts: IntegratedLearningArtifacts,
        offline_truth_labels: Iterable[OfflineTruthLabel],
    ) -> Mapping[str, Any]:
        """Append one complete episode without splitting frames across datasets."""

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
        d4_path, d4_summary = _write_d4_frames(
            self.root / "d4_region" / f"{manifest.episode_id}.jsonl",
            artifacts.d4_region_frames,
        )
        del d4_path
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
        episode_row = {
            "episode_id": manifest.episode_id,
            "scenario_version": config.scenario_version,
            "seed": config.seed,
            "config_sha256": manifest.config_sha256,
            "d3_exported_frame_count": len(records),
            "d3_unavailable_reason_counts": dict(sorted(unavailable.items())),
            "d4_captured_frame_count": int(d4_summary["captured_frame_count"]),
            "d5_staged_frame_count": int(d5_summary["staged_frame_count"]),
        }
        with self._episode_index_path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(episode_row, ensure_ascii=False, sort_keys=True) + "\n"
            )
        self._episode_count += 1
        self._d3_frame_count += len(records)
        self._d4_frame_count += int(d4_summary["captured_frame_count"])
        self._d5_frame_count += int(d5_summary["staged_frame_count"])
        self._seed_groups.add((config.scenario_version, int(config.seed)))
        return episode_row

    def finalize(self) -> dict[str, Path]:
        """Write dataset manifests only after whole-seed staging is complete."""

        if self._episode_count == 0:
            raise ValueError("cannot finalize an empty batch learning export")
        paths: dict[str, Path] = {"episode_index": self._episode_index_path}
        d3_split_counts: Mapping[str, int] = {}
        if self._d3_frame_count:
            from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
                LearningFrameRecord,
                write_learning_dataset,
            )

            records = tuple(
                LearningFrameRecord.from_dict(json.loads(line))
                for line in self._d3_staging_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            manifest = write_learning_dataset(
                self.root / "d3_assignment",
                records,
                source_kind="scalable_3d_multi_seed_batch",
            )
            d3_split_counts = dict(manifest.split_frame_counts)
            paths["d3_manifest"] = self.root / "d3_assignment" / "dataset_manifest.json"
            paths["d3_frames"] = self.root / "d3_assignment" / "frames.jsonl"

        d5_finalized = False
        d5_reason: str | None = None
        if self._d5_frame_count and len(self._seed_groups) >= 3:
            from research_modules.d5_terminal_association.src.d5_terminal_association.tracklet_dataset import (
                finalize_tracklet_dataset,
            )

            finalize_tracklet_dataset(self.root / "d5_tracklet_graph")
            paths["d5_manifest"] = (
                self.root / "d5_tracklet_graph" / "manifest.json"
            )
            d5_finalized = True
        elif self._d5_frame_count:
            d5_reason = "requires_at_least_three_scenario_seed_groups"
        else:
            d5_reason = "no_nonempty_d5_graph_frames"

        summary = {
            "schema_version": LEARNING_EXPORT_SCHEMA_VERSION,
            "episode_count": self._episode_count,
            "scenario_seed_group_count": len(self._seed_groups),
            "d3_frame_count": self._d3_frame_count,
            "d3_split_frame_counts": dict(d3_split_counts),
            "d4_frame_count": self._d4_frame_count,
            "d5_staged_frame_count": self._d5_frame_count,
            "d5_dataset_finalized": d5_finalized,
            "d5_dataset_finalization_reason": d5_reason,
            "online_truth_policy": "forbidden",
            "d5_label_policy": "separate_evaluator_artifact",
        }
        summary_path = self.root / "batch_learning_export_summary.json"
        _write_json(summary_path, summary)
        paths["summary"] = summary_path
        return paths


def write_episode_learning_artifacts(
    output_dir: str | Path,
    *,
    config: ScenarioConfig,
    manifest: EpisodeManifest,
    artifacts: IntegratedLearningArtifacts,
    offline_truth_labels: Iterable[OfflineTruthLabel],
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
    from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
        write_learning_dataset,
    )

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
    dataset_manifest = write_learning_dataset(
        root,
        records,
        source_kind="scalable_3d_integrated_episode",
    )
    return {
        "frames": root / "frames.jsonl",
        "manifest": root / "dataset_manifest.json",
    }, {
        "captured_frame_count": len(planning_frames),
        "exported_frame_count": len(records),
        "split_frame_counts": dict(dataset_manifest.split_frame_counts),
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


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "BatchLearningArtifactWriter",
    "LEARNING_EXPORT_SCHEMA_VERSION",
    "write_episode_learning_artifacts",
]
