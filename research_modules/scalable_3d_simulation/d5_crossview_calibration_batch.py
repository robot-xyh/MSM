"""Clean multi-seed producer for D5 cross-view calibration evidence.

The producer runs the integrated stack without exposing evaluator identity to
online D1-D5. It persists complete episode logs plus a D5 numeric graph dataset
whose truth labels remain in the existing evaluator-only sidecar.
"""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from research_modules.d5_terminal_association.src.d5_terminal_association.tracklet_dataset import (
    finalize_tracklet_dataset,
    join_offline_observation_labels,
    stage_tracklet_dataset_episode,
)

from .learning_runtime import LearningRuntimeOptions, resolve_learning_runtime
from .models import OFFLINE_TRUTH_DISPOSITION_TARGET, ScenarioConfig
from .module_stack import IntegratedStackConfig
from .orchestrator import EpisodeResult, run_episode


D5_CROSSVIEW_BATCH_SCHEMA = "scalable3d-d5-crossview-calibration-batch-v1"
D5_CROSSVIEW_GENERATION_SCHEMA = (
    "scalable3d-d5-crossview-calibration-generation-v1"
)
D5_CROSSVIEW_FRAME_INDEX_SCHEMA = "d6.d5-crossview-frame-index.v1"
D5_CROSSVIEW_RESERVED_SEEDS = tuple(range(1000, 1020))
D5_CROSSVIEW_VARIANTS = frozenset({"R0", "G1"})

MANIFEST_FILENAME = "manifest.json"
SUMMARY_FILENAME = "per_seed.csv"
REPORT_FILENAME = "D5_CROSSVIEW_CALIBRATION_BATCH_CN.md"
CHECKSUMS_FILENAME = "SHA256SUMS"
FRAME_INDEX_FILENAME = "d5_crossview_frame_index.json"
DATASET_DIRECTORY = "d5_tracklet_dataset"
EPISODES_DIRECTORY = "episodes"

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True, slots=True)
class D5CrossviewCalibrationBatchOptions:
    """Explicit batch controls; scale remains defined by the input config."""

    config_path: Path
    output_dir: Path
    variant: str = "R0"
    seeds: tuple[int, ...] = D5_CROSSVIEW_RESERVED_SEEDS
    evaluated_at_utc: str = "2026-07-26T00:00:00Z"
    d5_bundle_dir: Path | None = None
    formal: bool = False

    def __post_init__(self) -> None:
        for name in ("config_path", "output_dir"):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise TypeError(f"{name} must be a pathlib.Path")
            object.__setattr__(self, name, value.expanduser().resolve())
        variant = str(self.variant).strip().upper()
        if variant not in D5_CROSSVIEW_VARIANTS:
            raise ValueError("variant must be R0 or G1")
        object.__setattr__(self, "variant", variant)
        seeds = tuple(int(seed) for seed in self.seeds)
        if len(seeds) < 3 or len(set(seeds)) != len(seeds):
            raise ValueError(
                "at least three unique seeds are required to finalize the dataset"
            )
        if tuple(sorted(seeds)) != seeds:
            raise ValueError("seeds must be strictly increasing")
        if self.formal and seeds != D5_CROSSVIEW_RESERVED_SEEDS:
            raise ValueError("formal calibration requires seeds 1000-1019")
        object.__setattr__(self, "seeds", seeds)
        evaluated_at = str(self.evaluated_at_utc).strip()
        if _UTC_RE.fullmatch(evaluated_at) is None:
            raise ValueError("evaluated_at_utc must use YYYY-MM-DDTHH:MM:SSZ")
        object.__setattr__(self, "evaluated_at_utc", evaluated_at)
        bundle = self.d5_bundle_dir
        if bundle is not None:
            if not isinstance(bundle, Path):
                raise TypeError("d5_bundle_dir must be a pathlib.Path")
            bundle = bundle.expanduser().resolve()
            object.__setattr__(self, "d5_bundle_dir", bundle)
        if variant == "R0" and bundle is not None:
            raise ValueError("R0 must not load a D5 model bundle")
        if variant == "G1" and bundle is None:
            raise ValueError("G1 requires an explicit D5 model bundle")


@dataclass(frozen=True, slots=True)
class D5CrossviewSeedSummary:
    seed: int
    episode_id: str
    config_sha256: str
    finite_state: bool
    online_truth_use_count: int
    visual_target_observation_count: int
    visual_false_alarm_count: int
    d5_publication_count: int
    graph_frame_count: int
    graph_node_count: int
    graph_edge_count: int
    candidate_edge_count: int
    cross_call_camera_reuse_count: int
    bound_decision_count: int
    complete_label_frame_count: int
    incomplete_label_frame_count: int
    source_link_count: int
    source_link_coverage_violation_count: int
    loaded_model_frame_count: int
    rule_frame_count: int
    fallback_frame_count: int
    max_model_inference_latency_ms: float | None

    def __post_init__(self) -> None:
        if int(self.seed) < 0:
            raise ValueError("seed must be non-negative")
        for name, value in asdict(self).items():
            if name in {
                "episode_id",
                "config_sha256",
                "finite_state",
                "max_model_inference_latency_ms",
            }:
                continue
            if int(value) < 0:
                raise ValueError(f"{name} must be non-negative")
        latency = self.max_model_inference_latency_ms
        if latency is not None and (not isfinite(latency) or latency < 0.0):
            raise ValueError("max_model_inference_latency_ms must be finite")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_d5_crossview_calibration_batch(
    options: D5CrossviewCalibrationBatchOptions,
) -> Mapping[str, Path]:
    """Run one immutable R0 or admitted-G1 calibration batch."""

    if not isinstance(options, D5CrossviewCalibrationBatchOptions):
        raise TypeError("options must be D5CrossviewCalibrationBatchOptions")
    if not options.config_path.is_file():
        raise FileNotFoundError(options.config_path)
    if options.output_dir.exists():
        raise FileExistsError(options.output_dir)

    base = ScenarioConfig.from_dict(
        json.loads(options.config_path.read_text(encoding="utf-8"))
    )
    if (
        base.metadata.get("calibration_scope")
        != "d5_truth_isolated_crossview_visibility"
    ):
        raise ValueError("config is not a D5 cross-view calibration scenario")
    if base.metadata.get("online_truth_policy") != "forbidden":
        raise ValueError("calibration config must forbid online truth")
    if float(base.visual_false_alarm_rate) != 0.0:
        raise ValueError(
            "cross-view identity calibration requires zero synthetic false alarms"
        )

    output_parent = options.output_dir.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{options.output_dir.name}.partial-",
            dir=output_parent,
        )
    )
    try:
        result = _run_batch_into(staging, base=base, options=options)
        _write_batch_outputs(staging, result=result, options=options)
        os.replace(staging, options.output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "manifest": options.output_dir / MANIFEST_FILENAME,
        "per_seed": options.output_dir / SUMMARY_FILENAME,
        "report": options.output_dir / REPORT_FILENAME,
        "checksums": options.output_dir / CHECKSUMS_FILENAME,
        "frame_index_sidecar": options.output_dir / FRAME_INDEX_FILENAME,
        "dataset_manifest": (
            options.output_dir / DATASET_DIRECTORY / "manifest.json"
        ),
    }


@dataclass(frozen=True, slots=True)
class _BatchResult:
    source_git_commit: str
    source_repository_dirty: bool
    base_config_sha256: str
    exogenous_config_sha256: str
    dataset_manifest_sha256: str
    frame_index_sidecar_sha256: str
    frame_index_record_count: int
    summaries: tuple[D5CrossviewSeedSummary, ...]
    probability_source_counts: Mapping[str, int]
    scoring_status_counts: Mapping[str, int]
    fallback_reason_counts: Mapping[str, int]


def _run_batch_into(
    staging: Path,
    *,
    base: ScenarioConfig,
    options: D5CrossviewCalibrationBatchOptions,
) -> _BatchResult:
    dataset_root = staging / DATASET_DIRECTORY
    summaries: list[D5CrossviewSeedSummary] = []
    source_commit: str | None = None
    source_repository_dirty: bool | None = None
    probability_sources: Counter[str] = Counter()
    scoring_statuses: Counter[str] = Counter()
    fallback_reasons: Counter[str] = Counter()
    generation_config = {
        "schema_version": D5_CROSSVIEW_GENERATION_SCHEMA,
        "scenario_version": base.scenario_version,
        "variant": options.variant,
        "sensor_random_schedule_version": "entity_fixed_v1",
        "truth_join": "offline_observation_id_to_anonymous_tracklet_v1",
        "recon_track_cues_enabled": True,
    }

    for seed in options.seeds:
        config = replace(
            base,
            seed=seed,
            sensor_random_schedule_version="entity_fixed_v1",
        )
        learning = LearningRuntimeOptions(
            d5_bundle_dir=options.d5_bundle_dir,
        )
        resolved = resolve_learning_runtime(
            config,
            learning,
            stack_config=IntegratedStackConfig(
                capture_learning_artifacts=True,
                d5_recon_track_cues_enabled=True,
            ),
        )
        episode_dir = staging / EPISODES_DIRECTORY / f"seed_{seed:04d}"
        episode = run_episode(
            resolved.config,
            output_dir=episode_dir,
            module_stack=resolved.stack,
        )
        commit, repository_dirty = _validate_episode(
            episode,
            expected_seed=seed,
            formal=options.formal,
        )
        if source_commit is None:
            source_commit = commit
            source_repository_dirty = repository_dirty
        elif source_commit != commit:
            raise RuntimeError("source Git commit changed across calibration seeds")
        elif source_repository_dirty != repository_dirty:
            raise RuntimeError(
                "source repository state changed across calibration seeds"
            )

        artifacts = resolved.stack.learning_artifacts()
        label_summary = _stage_d5_graph_frames(
            dataset_root,
            episode=episode,
            graph_frames=artifacts.d5_graph_frames,
            generation_config=generation_config,
        )
        seed_summary, sources, statuses, fallbacks = _summarize_seed(
            episode,
            graph_frames=artifacts.d5_graph_frames,
            label_summary=label_summary,
        )
        _validate_variant_execution(seed_summary, options.variant)
        summaries.append(seed_summary)
        probability_sources.update(sources)
        scoring_statuses.update(statuses)
        fallback_reasons.update(fallbacks)

    if source_commit is None or source_repository_dirty is None:
        raise RuntimeError("calibration batch produced no episodes")
    dataset_manifest = finalize_tracklet_dataset(dataset_root)
    dataset_manifest_path = dataset_root / "manifest.json"
    frame_index_record_count = _write_frame_index_sidecar(
        staging / FRAME_INDEX_FILENAME,
        dataset_manifest_path,
    )
    frame_index_sidecar_sha256 = _sha256_file(
        staging / FRAME_INDEX_FILENAME
    )
    if len({item.seed for item in summaries}) != len(options.seeds):
        raise RuntimeError("calibration seed inventory changed during execution")
    return _BatchResult(
        source_git_commit=source_commit,
        source_repository_dirty=source_repository_dirty,
        base_config_sha256=_canonical_sha256(base.to_dict()),
        exogenous_config_sha256=_exogenous_config_sha256(base),
        dataset_manifest_sha256=_sha256_file(dataset_manifest_path),
        frame_index_sidecar_sha256=frame_index_sidecar_sha256,
        frame_index_record_count=frame_index_record_count,
        summaries=tuple(summaries),
        probability_source_counts=dict(sorted(probability_sources.items())),
        scoring_status_counts=dict(sorted(scoring_statuses.items())),
        fallback_reason_counts=dict(sorted(fallback_reasons.items())),
    )


def _validate_episode(
    episode: EpisodeResult,
    *,
    expected_seed: int,
    formal: bool,
) -> tuple[str, bool]:
    if int(episode.config.seed) != int(expected_seed):
        raise RuntimeError("episode seed differs from the batch plan")
    commit = str(episode.manifest.git_commit)
    if _SHA1_RE.fullmatch(commit) is None:
        raise RuntimeError("episode did not report a full Git commit")
    repository_dirty = bool(episode.manifest.repository_dirty)
    if formal and repository_dirty:
        raise RuntimeError("formal calibration requires a clean source worktree")
    if not bool(episode.summary.get("finite_state")):
        raise RuntimeError("calibration episode produced non-finite state")
    if int(episode.summary.get("online_truth_use_count", -1)) != 0:
        raise RuntimeError("calibration episode used online truth")
    return commit, repository_dirty


@dataclass(frozen=True, slots=True)
class _LabelStagingSummary:
    graph_frame_count: int
    complete_label_frame_count: int
    incomplete_label_frame_count: int
    source_link_count: int
    source_link_coverage_violation_count: int


def _stage_d5_graph_frames(
    dataset_root: Path,
    *,
    episode: EpisodeResult,
    graph_frames: Iterable[Any],
    generation_config: Mapping[str, Any],
) -> _LabelStagingSummary:
    label_by_observation = {
        label.observation_id: label
        for label in episode.offline_truth_labels
        if label.disposition == OFFLINE_TRUTH_DISPOSITION_TARGET
    }
    graph_frame_count = 0
    complete_count = 0
    incomplete_count = 0
    source_link_count = 0
    coverage_violations = 0
    for frame in graph_frames:
        graph = frame.graph
        if int(graph.node_count) == 0:
            continue
        graph_frame_count += 1
        source_links = tuple(frame.source_observation_links)
        source_link_count += len(source_links)
        required_links = {
            node.tracklet_key
            for node in graph.nodes
            if node.source_observation_id is not None
        }
        actual_links = {link.tracklet_key for link in source_links}
        if (
            len(actual_links) != len(source_links)
            or actual_links != required_links
        ):
            coverage_violations += 1
        source_ids = {
            str(node.source_observation_id)
            for node in graph.nodes
            if node.source_observation_id is not None
        }
        frame_labels = tuple(
            label_by_observation[source_id]
            for source_id in sorted(source_ids)
            if source_id in label_by_observation
        )
        joined = join_offline_observation_labels(graph, frame_labels)
        complete_count += int(joined.labels_complete)
        incomplete_count += int(not joined.labels_complete)
        stage_tracklet_dataset_episode(
            dataset_root,
            graph,
            joined.tracklet_labels,
            scenario_version=episode.config.scenario_version,
            seed=episode.config.seed,
            episode_id=_stable_frame_coordinate(
                episode.config.scenario_version,
                episode.config.seed,
                int(frame.frame_index),
            ),
            generation_config=generation_config,
            labels_complete=joined.labels_complete,
            candidate_recall_available=joined.labels_complete,
            hard_negative_provenance={
                "source": "online_geometric_candidate_gate",
                "truth_use": "offline_label_only",
                "frame_index": int(frame.frame_index),
            },
        )
    if graph_frame_count == 0:
        raise RuntimeError("calibration episode produced no D5 graph frames")
    if incomplete_count or coverage_violations:
        raise RuntimeError(
            "D5 graph/source lineage is incomplete for offline evaluation"
        )
    return _LabelStagingSummary(
        graph_frame_count=graph_frame_count,
        complete_label_frame_count=complete_count,
        incomplete_label_frame_count=incomplete_count,
        source_link_count=source_link_count,
        source_link_coverage_violation_count=coverage_violations,
    )


def _summarize_seed(
    episode: EpisodeResult,
    *,
    graph_frames: Iterable[Any],
    label_summary: _LabelStagingSummary,
) -> tuple[
    D5CrossviewSeedSummary,
    Counter[str],
    Counter[str],
    Counter[str],
]:
    graph_items = tuple(graph_frames)
    payloads = tuple(
        dict(message.payload)
        for message in episode.online_messages
        if message.topic == "modules.d5.terminal_association"
    )
    sources = Counter(
        str(payload.get("probability_source", "unavailable"))
        for payload in payloads
    )
    statuses = Counter(
        str(payload.get("scoring_status", "unavailable"))
        for payload in payloads
    )
    fallbacks = Counter(
        str(payload.get("fallback_reason") or "none")
        for payload in payloads
    )
    latencies = tuple(
        float(payload.get("diagnostics", {}).get("model_inference_latency_ms"))
        for payload in payloads
        if payload.get("diagnostics", {}).get("model_inference_latency_ms")
        is not None
    )
    target_visual = sum(
        label.disposition == OFFLINE_TRUTH_DISPOSITION_TARGET
        and str(label.observation_id).startswith("vision-")
        for label in episode.offline_truth_labels
    )
    false_visual = sum(
        label.disposition != OFFLINE_TRUTH_DISPOSITION_TARGET
        and str(label.observation_id).startswith("vision-")
        for label in episode.offline_truth_labels
    )
    summary = D5CrossviewSeedSummary(
        seed=episode.config.seed,
        episode_id=episode.manifest.episode_id,
        config_sha256=episode.manifest.config_sha256,
        finite_state=bool(episode.summary.get("finite_state")),
        online_truth_use_count=int(
            episode.summary.get("online_truth_use_count", -1)
        ),
        visual_target_observation_count=int(target_visual),
        visual_false_alarm_count=int(false_visual),
        d5_publication_count=len(payloads),
        graph_frame_count=label_summary.graph_frame_count,
        graph_node_count=sum(int(frame.graph.node_count) for frame in graph_items),
        graph_edge_count=sum(int(frame.graph.edge_count) for frame in graph_items),
        candidate_edge_count=sum(
            int(frame.graph.candidate_counts.get("candidate_tracklet_edges", 0))
            for frame in graph_items
        ),
        cross_call_camera_reuse_count=sum(
            int(
                payload.get("diagnostics", {}).get(
                    "snapshot_cross_call_active_camera_count",
                    0,
                )
            )
            for payload in payloads
        ),
        bound_decision_count=sum(
            sum(
                item.get("decision_state") == "bound"
                for item in payload.get("bindings", ())
            )
            for payload in payloads
        ),
        complete_label_frame_count=label_summary.complete_label_frame_count,
        incomplete_label_frame_count=(
            label_summary.incomplete_label_frame_count
        ),
        source_link_count=label_summary.source_link_count,
        source_link_coverage_violation_count=(
            label_summary.source_link_coverage_violation_count
        ),
        loaded_model_frame_count=int(sources.get("loaded_edge_model", 0)),
        rule_frame_count=int(sources.get("deterministic_geometry_rule", 0)),
        fallback_frame_count=sum(
            count for reason, count in fallbacks.items() if reason != "none"
        ),
        max_model_inference_latency_ms=(
            None if not latencies else max(latencies)
        ),
    )
    return summary, sources, statuses, fallbacks


def _validate_variant_execution(
    summary: D5CrossviewSeedSummary,
    variant: str,
) -> None:
    if summary.candidate_edge_count <= 0 or summary.graph_edge_count <= 0:
        raise RuntimeError("calibration seed produced no cross-view graph edges")
    if summary.visual_target_observation_count <= 0:
        raise RuntimeError("calibration seed produced no target visual observations")
    if summary.source_link_coverage_violation_count:
        raise RuntimeError("calibration seed has source-link coverage violations")
    if variant == "R0":
        if (
            summary.rule_frame_count != summary.d5_publication_count
            or summary.loaded_model_frame_count != 0
        ):
            raise RuntimeError("R0 execution did not remain on the rule scorer")
    else:
        if (
            summary.loaded_model_frame_count != summary.d5_publication_count
            or summary.rule_frame_count != 0
            or summary.fallback_frame_count != 0
        ):
            raise RuntimeError("G1 execution did not use the model on every frame")


def _write_batch_outputs(
    staging: Path,
    *,
    result: _BatchResult,
    options: D5CrossviewCalibrationBatchOptions,
) -> None:
    rows = tuple(item.to_dict() for item in result.summaries)
    with (staging / SUMMARY_FILENAME).open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    manifest_payload: dict[str, Any] = {
        "schema_version": D5_CROSSVIEW_BATCH_SCHEMA,
        "evaluated_at_utc": options.evaluated_at_utc,
        "formal": options.formal,
        "variant": options.variant,
        "source_git_commit": result.source_git_commit,
        "source_repository_dirty": result.source_repository_dirty,
        "source_worktree_required_clean": options.formal,
        "config_file": _portable_source_path(options.config_path),
        "base_config_sha256": result.base_config_sha256,
        "exogenous_config_sha256": result.exogenous_config_sha256,
        "seed_values": list(options.seeds),
        "seed_count": len(options.seeds),
        "dataset_manifest": f"{DATASET_DIRECTORY}/manifest.json",
        "dataset_manifest_sha256": result.dataset_manifest_sha256,
        "frame_index_sidecar": FRAME_INDEX_FILENAME,
        "frame_index_sidecar_schema": D5_CROSSVIEW_FRAME_INDEX_SCHEMA,
        "frame_index_sidecar_sha256": result.frame_index_sidecar_sha256,
        "frame_index_record_count": result.frame_index_record_count,
        "probability_source_counts": dict(result.probability_source_counts),
        "scoring_status_counts": dict(result.scoring_status_counts),
        "fallback_reason_counts": dict(result.fallback_reason_counts),
        "totals": _aggregate_totals(result.summaries),
        "authority": {
            "evaluation_only": True,
            "model_promotion_granted": False,
            "default_path_change_granted": False,
            "assignment_authority_granted": False,
            "failover_authority_granted": False,
            "control_authority_granted": False,
        },
    }
    manifest_payload["content_sha256"] = _canonical_sha256(manifest_payload)
    _write_json(staging / MANIFEST_FILENAME, manifest_payload)
    (staging / REPORT_FILENAME).write_text(
        _render_report(manifest_payload),
        encoding="utf-8",
    )
    _write_checksums(staging)


def _aggregate_totals(
    summaries: Iterable[D5CrossviewSeedSummary],
) -> dict[str, Any]:
    items = tuple(summaries)
    fields = (
        "visual_target_observation_count",
        "visual_false_alarm_count",
        "d5_publication_count",
        "graph_frame_count",
        "graph_node_count",
        "graph_edge_count",
        "candidate_edge_count",
        "cross_call_camera_reuse_count",
        "bound_decision_count",
        "complete_label_frame_count",
        "incomplete_label_frame_count",
        "source_link_count",
        "source_link_coverage_violation_count",
        "loaded_model_frame_count",
        "rule_frame_count",
        "fallback_frame_count",
    )
    totals = {
        name: sum(int(getattr(item, name)) for item in items)
        for name in fields
    }
    totals["finite_seed_count"] = sum(item.finite_state for item in items)
    totals["online_truth_use_count"] = sum(
        item.online_truth_use_count for item in items
    )
    latencies = tuple(
        item.max_model_inference_latency_ms
        for item in items
        if item.max_model_inference_latency_ms is not None
    )
    totals["max_model_inference_latency_ms"] = (
        None if not latencies else max(latencies)
    )
    return totals


def _render_report(manifest: Mapping[str, Any]) -> str:
    totals = manifest["totals"]
    return "\n".join(
        (
            "# D5 跨视角校准批量运行报告",
            "",
            "## 结论",
            "",
            f"- 变体：`{manifest['variant']}`。",
            f"- seed：`{manifest['seed_count']}` 个，来源提交："
            f"`{manifest['source_git_commit']}`。",
            f"- 状态有限：`{totals['finite_seed_count']}/"
            f"{manifest['seed_count']}`；在线真值读取："
            f"`{totals['online_truth_use_count']}`。",
            f"- 目标视觉观测：`{totals['visual_target_observation_count']}`；"
            f"视觉虚警：`{totals['visual_false_alarm_count']}`。",
            f"- 图节点/候选边/保留边：`{totals['graph_node_count']}` / "
            f"`{totals['candidate_edge_count']}` / "
            f"`{totals['graph_edge_count']}`。",
            f"- 完整标签帧：`{totals['complete_label_frame_count']}`；"
            f"不完整标签帧：`{totals['incomplete_label_frame_count']}`；"
            f"来源链接违规：`{totals['source_link_coverage_violation_count']}`。",
            f"- 稳定帧坐标 sidecar：`{manifest['frame_index_record_count']}` 条，"
            f"SHA-256 `{manifest['frame_index_sidecar_sha256']}`。",
            "",
            "本报告只说明运行和数据装配状态。边分类精度、错误合并率、中心绑定正确率"
            "和模型收益由 D6 使用 evaluator-only 标签另行计算。本批次不授予模型晋级、"
            "默认路径、分配、故障接管或控制权限。",
            "",
        )
    )


def _exogenous_config_sha256(config: ScenarioConfig) -> str:
    payload = config.to_dict()
    for name in (
        "d1_model_version",
        "d2_model_version",
        "d3_policy_version",
        "d4_policy_version",
        "d5_model_version",
        "d5_active_vision_policy_version",
        "d7_model_version",
    ):
        payload[name] = "<algorithm-version-excluded>"
    payload["seed"] = "<seed-excluded>"
    return _canonical_sha256(payload)


def _write_frame_index_sidecar(
    output_path: Path,
    dataset_manifest_path: Path,
) -> int:
    manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    episodes = manifest.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        raise RuntimeError("finalized D5 dataset has no episode descriptors")
    records: list[dict[str, Any]] = []
    episode_uids: set[str] = set()
    coordinates: set[tuple[str, int, int]] = set()
    for descriptor in episodes:
        if not isinstance(descriptor, Mapping):
            raise RuntimeError("D5 dataset episode descriptor is invalid")
        provenance = descriptor.get("hard_negative_provenance")
        if not isinstance(provenance, Mapping):
            raise RuntimeError("D5 dataset frame provenance is missing")
        episode_uid = str(descriptor.get("episode_uid", "")).strip()
        scenario_version = str(
            descriptor.get("scenario_version", "")
        ).strip()
        seed = descriptor.get("seed")
        frame_index = provenance.get("frame_index")
        if (
            not episode_uid
            or not scenario_version
            or type(seed) is not int
            or type(frame_index) is not int
            or seed < 0
            or frame_index < 0
        ):
            raise RuntimeError("D5 dataset frame coordinate is invalid")
        coordinate = (scenario_version, seed, frame_index)
        if episode_uid in episode_uids:
            raise RuntimeError("D5 dataset episode UID is duplicated")
        if coordinate in coordinates:
            raise RuntimeError("D5 dataset frame coordinate is duplicated")
        episode_uids.add(episode_uid)
        coordinates.add(coordinate)
        records.append(
            {
                "episode_uid": episode_uid,
                "scenario_version": scenario_version,
                "seed": seed,
                "frame_index": frame_index,
            }
        )
    records.sort(
        key=lambda item: (
            item["scenario_version"],
            item["seed"],
            item["frame_index"],
            item["episode_uid"],
        )
    )
    _write_json(
        output_path,
        {
            "schema_version": D5_CROSSVIEW_FRAME_INDEX_SCHEMA,
            "coordinate_semantics": "scenario_version_seed_frame_index",
            "dataset_manifest_sha256": _sha256_file(
                dataset_manifest_path
            ),
            "records": records,
        },
    )
    return len(records)


def _stable_frame_coordinate(
    scenario_version: str,
    seed: int,
    frame_index: int,
) -> str:
    return (
        f"d5-crossview-calibration:{str(scenario_version)}:"
        f"seed-{int(seed):04d}:frame-{int(frame_index):06d}"
    )


def _portable_source_path(path: Path) -> str:
    repository_root = Path(__file__).resolve().parents[2]
    try:
        return path.resolve().relative_to(repository_root).as_posix()
    except ValueError:
        return path.name


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_checksums(root: Path) -> None:
    files = tuple(
        sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.name != CHECKSUMS_FILENAME
        )
    )
    lines = [
        f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in files
    ]
    (root / CHECKSUMS_FILENAME).write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "D5_CROSSVIEW_BATCH_SCHEMA",
    "D5_CROSSVIEW_FRAME_INDEX_SCHEMA",
    "D5_CROSSVIEW_RESERVED_SEEDS",
    "D5CrossviewCalibrationBatchOptions",
    "D5CrossviewSeedSummary",
    "run_d5_crossview_calibration_batch",
]
