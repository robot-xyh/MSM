from __future__ import annotations

import cProfile
import json
from pathlib import Path
import pstats
from time import perf_counter
from typing import Any, Mapping, Sequence

import numpy as np

from .long_duration_performance import (
    _coalesced_scan_semantic_digest,
    _json_sha256,
    _semantic_track_snapshot,
)
from .scalable_3d import Scalable3DFusionAdapter
from .scan_input import ScanInputOrganizer, SensorScanFrame
from .tail_latency_performance import (
    _scan_claims_sha256,
    load_frozen_sensor_frames,
)


PUBLICATION_METADATA_PERFORMANCE_SCHEMA_VERSION = (
    "d1.publication_metadata_performance.v1"
)

_FUSION_OPERATION_FIELDS = (
    "history_replay_count",
    "origin_replay_count",
    "state_cache_hit_count",
    "state_cache_miss_count",
    "finalization_replay_count",
    "replay_filter_update_count",
    "replay_checkpoint_reuse_count",
    "global_track_materialization_count",
    "sensor_health_snapshot_build_count",
    "association_candidate_pair_count",
    "association_measurement_model_build_count",
    "association_projection_build_count",
    "association_innovation_solve_count",
    "association_radar_track_state_build_count",
    "association_radar_observation_state_build_count",
    "deferred_update_replay_avoidance_count",
)

_PROFILE_SPECS = (
    ("process_scan_batch", "fusion.py", "process_scan_batch"),
    ("global_tracks", "fusion.py", "global_tracks"),
    ("_to_global_track", "fusion.py", "_to_global_track"),
    ("_track_publication_context", "fusion.py", "_track_publication_context"),
    (
        "_freeze_publication_audit_value",
        "fusion.py",
        "_freeze_publication_audit_value",
    ),
)


def analyze_frozen_publication_metadata(
    source: str | Path,
    *,
    repeat_count: int = 1,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Run strict reference/candidate publication materialization A/B."""

    if repeat_count < 1:
        raise ValueError("repeat_count must be positive")
    frames, input_summary = load_frozen_sensor_frames(source)
    profile_root = (
        None if profile_directory is None else Path(profile_directory)
    )
    runs: dict[str, list[dict[str, Any]]] = {
        "reference": [],
        "candidate": [],
    }
    execution_order: list[str] = []
    for repeat_index in range(repeat_count):
        order = ("reference", "candidate")
        if repeat_index % 2:
            order = tuple(reversed(order))
        for variant in order:
            execution_order.append(variant)
            profile_path = None
            if profile_root is not None and not runs[variant]:
                profile_root.mkdir(parents=True, exist_ok=True)
                profile_path = profile_root / f"d1_publication_{variant}.prof"
            runs[variant].append(
                _run_publication_variant(
                    frames,
                    variant=variant,
                    immutable_shared_publication_metadata=(
                        variant == "candidate"
                    ),
                    profile_path=profile_path,
                )
            )

    reference = runs["reference"][0]
    candidate = runs["candidate"][0]
    acceptance = _acceptance(
        reference,
        candidate,
        input_summary=input_summary,
    )
    repeat_determinism = {
        variant: _variant_repeat_determinism(items)
        for variant, items in runs.items()
    }
    acceptance["reference_repeat_determinism"] = repeat_determinism[
        "reference"
    ]
    acceptance["candidate_repeat_determinism"] = repeat_determinism[
        "candidate"
    ]
    timing = {
        "repeat_count": int(repeat_count),
        "execution_order": execution_order,
        "reference": _timing_summary(runs["reference"]),
        "candidate": _timing_summary(runs["candidate"]),
        "wall_time_used_for_acceptance": False,
    }
    reference_median = timing["reference"]["p50_fusion_wall_time_s"]
    candidate_median = timing["candidate"]["p50_fusion_wall_time_s"]
    timing["p50_speedup"] = (
        float(reference_median) / float(candidate_median)
        if float(candidate_median) > 0.0
        else None
    )
    return {
        "schema_version": PUBLICATION_METADATA_PERFORMANCE_SCHEMA_VERSION,
        "input": input_summary,
        "comparison": {
            "reference": _compact_result(reference),
            "candidate": _compact_result(candidate),
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
            "timing": timing,
        },
        "constraints": {
            "fusion_math_changed": False,
            "fixed_lag_window_changed": False,
            "scan_frequency_changed": False,
            "publication_frequency_changed": False,
            "association_gate_changed": False,
            "observation_content_changed": False,
            "online_truth_use_count": int(
                input_summary["online_truth_use_count"]
            ),
            "wall_time_used_for_acceptance": False,
            "formal_multi_seed_evidence": False,
            "candidate_promoted_to_default": False,
        },
    }


def write_publication_metadata_report(
    report: Mapping[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_destination = Path(json_path)
    markdown_destination = Path(markdown_path)
    json_destination.parent.mkdir(parents=True, exist_ok=True)
    markdown_destination.parent.mkdir(parents=True, exist_ok=True)
    json_destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_destination.write_text(
        render_publication_metadata_report_cn(report),
        encoding="utf-8",
    )


def render_publication_metadata_report_cn(
    report: Mapping[str, Any],
) -> str:
    source = report["input"]
    comparison = report["comparison"]
    reference = comparison["reference"]
    candidate = comparison["candidate"]
    timing = comparison["timing"]
    reference_counts = reference["publication_materialization_diagnostics"][
        "operation_counts"
    ]
    candidate_counts = candidate["publication_materialization_diagnostics"][
        "operation_counts"
    ]
    lines = [
        "# D1 GlobalTrack 共享审计元数据候选验证",
        "",
        "## 证据边界",
        "",
        f"- 冻结输入：`{source['source_path']}`",
        f"- SHA-256：`{source['source_sha256']}`",
        f"- 扫描数：{int(source['input_batch_count']):,}；观测数："
        f"{int(source['input_observation_count']):,}。",
        "- reference 保留逐航迹复制共享审计映射；candidate 在每个发布扫描内"
        "递归冻结共享审计树，再由所有航迹只读复用。",
        "- 墙钟和 cProfile 只作归因，不参与语义验收；本报告不是正式多 seed 放行。",
        "",
        "## 等价判定",
        "",
        f"- 通过：`{comparison['passed']}`",
    ]
    for name, passed in comparison["acceptance"].items():
        lines.append(f"- `{name}`：`{passed}`")
    lines.extend(
        [
            "",
            "逐发布完整 `GlobalTrack.to_dict()`、逐扫描融合语义摘要、状态与协方差、"
            "双时间戳、谱系、质量分级、诊断、终态和一致性证据均纳入摘要比较。",
            "",
            "## 操作计数",
            "",
            "| 操作 | reference | candidate |",
            "| --- | ---: | ---: |",
            "| 逐航迹共享审计映射复制 | "
            f"{int(reference_counts.get('per_track_shared_audit_mapping_copy_count', 0)):,} | "
            f"{int(candidate_counts.get('per_track_shared_audit_mapping_copy_count', 0)):,} |",
            "| 逐航迹不可变审计值复用 | "
            f"{int(reference_counts.get('shared_audit_value_reuse_count', 0)):,} | "
            f"{int(candidate_counts.get('shared_audit_value_reuse_count', 0)):,} |",
            "| 共享不可变映射构造 | "
            f"{int(reference_counts.get('immutable_shared_mapping_build_count', 0)):,} | "
            f"{int(candidate_counts.get('immutable_shared_mapping_build_count', 0)):,} |",
            "| GlobalTrack 元数据物化 | "
            f"{int(reference_counts.get('global_track_metadata_materialization_count', 0)):,} | "
            f"{int(candidate_counts.get('global_track_metadata_materialization_count', 0)):,} |",
            "",
            "## 运行时间",
            "",
            f"- reference 融合总时长 P50："
            f"`{float(timing['reference']['p50_fusion_wall_time_s']):.3f} s`。",
            f"- candidate 融合总时长 P50："
            f"`{float(timing['candidate']['p50_fusion_wall_time_s']):.3f} s`。",
            f"- P50 加速比：`{float(timing['p50_speedup'] or 0.0):.3f}x`。",
            "",
            "candidate 默认关闭。只有 main 在冻结多 seed 上确认严格等价、稳定收益和"
            "下游兼容性后，才可讨论改为默认路径；D1 实时缺口当前仍保持未关闭。",
            "",
        ]
    )
    return "\n".join(lines)


def _run_publication_variant(
    frames: Sequence[SensorScanFrame],
    *,
    variant: str,
    immutable_shared_publication_metadata: bool,
    profile_path: Path | None,
) -> dict[str, Any]:
    organizer = ScanInputOrganizer()
    adapter = Scalable3DFusionAdapter(
        immutable_shared_publication_metadata=(
            immutable_shared_publication_metadata
        )
    )
    scan_input_digests: list[str] = []
    release_group_sizes: list[int] = []
    fusion_digests: list[str] = []
    publication_digests: list[str] = []
    operation_snapshots: list[dict[str, int]] = []
    diagnostic_snapshots: list[dict[str, Any]] = []
    operation_totals = {name: 0 for name in _FUSION_OPERATION_FIELDS}
    final_tracks: Sequence[Any] | None = None
    fusion_wall_time_s = 0.0
    profiler = cProfile.Profile() if profile_path is not None else None

    def consume(scans: Sequence[SensorScanFrame]) -> None:
        nonlocal final_tracks, fusion_wall_time_s
        group = tuple(scans)
        if not group:
            return
        release_group_sizes.append(len(group))
        for index, scan in enumerate(group):
            fusion_timestamp = max(
                float(adapter.current_time),
                float(scan.arrival_timestamp),
            )
            next_timestamp = (
                None
                if index + 1 == len(group)
                else max(
                    fusion_timestamp,
                    float(group[index + 1].arrival_timestamp),
                )
            )
            materialize_tracks = bool(
                next_timestamp is None
                or next_timestamp > fusion_timestamp + 1.0e-9
            )
            started = perf_counter()
            if profiler is not None:
                profiler.enable()
            result = adapter.process_scan_batch(
                scan.observations,
                materialize_tracks=materialize_tracks,
            )
            if profiler is not None:
                profiler.disable()
            fusion_wall_time_s += perf_counter() - started
            summary = result.summary.to_dict()
            snapshot = {
                name: int(summary[name])
                for name in _FUSION_OPERATION_FIELDS
            }
            operation_snapshots.append(snapshot)
            for name, count in snapshot.items():
                operation_totals[name] += int(count)
            diagnostic_snapshots.append(
                adapter.fusion_performance_diagnostics().to_dict()
            )
            fusion_digests.append(
                _coalesced_scan_semantic_digest(adapter, result)
            )
            if materialize_tracks:
                final_tracks = result.tracks
                publication_digests.append(
                    _json_sha256(
                        [
                            track.to_dict()
                            for track in sorted(
                                result.tracks,
                                key=lambda item: item.global_track_id,
                            )
                        ]
                    )
                )

    for frame in frames:
        result = organizer.ingest(frame)
        scan_input_digests.append(_json_sha256(result.to_dict()))
        consume(result.released_scans)
    close_result = organizer.close()
    close_digest = _json_sha256(close_result.to_dict())
    consume(close_result.released_scans)
    if final_tracks is None:
        raise ValueError("publication benchmark produced no GlobalTrack output")

    profile = None
    if profiler is not None and profile_path is not None:
        profiler.dump_stats(str(profile_path))
        profile = _profile_summary(profile_path)
    return {
        "variant": variant,
        "scan_input_digests_sha256": _json_sha256(scan_input_digests),
        "scan_input_close_digest": close_digest,
        "scan_input_audit": organizer.audit_summary().to_dict(),
        "scan_claims_sha256": _scan_claims_sha256(organizer),
        "release_group_sizes": release_group_sizes,
        "fusion_digests": fusion_digests,
        "fusion_digests_sha256": _json_sha256(fusion_digests),
        "publication_digests": publication_digests,
        "publication_digests_sha256": _json_sha256(publication_digests),
        "operation_snapshots": operation_snapshots,
        "operation_snapshots_sha256": _json_sha256(operation_snapshots),
        "operation_totals": operation_totals,
        "diagnostic_snapshots": diagnostic_snapshots,
        "diagnostic_snapshots_sha256": _json_sha256(diagnostic_snapshots),
        "fusion_cumulative_diagnostics": (
            adapter.fusion_performance_diagnostics().to_dict()
        ),
        "publication_materialization_diagnostics": (
            adapter.publication_materialization_diagnostics()
        ),
        "final_tracks_sha256": _json_sha256(
            _semantic_track_snapshot(final_tracks)
        ),
        "consistency_evidence_sha256": _json_sha256(
            [item.to_dict() for item in adapter.consistency_evidence_records()]
        ),
        "fusion_wall_time_s": float(fusion_wall_time_s),
        "profile": profile,
    }


def _acceptance(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    input_summary: Mapping[str, Any],
) -> dict[str, bool]:
    reference_counts = reference["publication_materialization_diagnostics"][
        "operation_counts"
    ]
    candidate_counts = candidate["publication_materialization_diagnostics"][
        "operation_counts"
    ]
    reference_materializations = int(
        reference_counts.get("global_track_metadata_materialization_count", 0)
    )
    candidate_materializations = int(
        candidate_counts.get("global_track_metadata_materialization_count", 0)
    )
    return {
        "per_input_scan_result_equivalence": (
            reference["scan_input_digests_sha256"]
            == candidate["scan_input_digests_sha256"]
        ),
        "scan_input_close_result_equivalence": (
            reference["scan_input_close_digest"]
            == candidate["scan_input_close_digest"]
        ),
        "scan_input_audit_equivalence": (
            reference["scan_input_audit"] == candidate["scan_input_audit"]
        ),
        "scan_claim_registry_equivalence": (
            reference["scan_claims_sha256"]
            == candidate["scan_claims_sha256"]
        ),
        "release_group_schedule_equivalence": (
            reference["release_group_sizes"]
            == candidate["release_group_sizes"]
        ),
        "per_scan_fusion_semantic_equivalence": (
            reference["fusion_digests"] == candidate["fusion_digests"]
        ),
        "per_publication_complete_global_track_equivalence": (
            reference["publication_digests"]
            == candidate["publication_digests"]
        ),
        "per_scan_fusion_operation_equivalence": (
            reference["operation_snapshots"]
            == candidate["operation_snapshots"]
        ),
        "per_scan_fusion_diagnostic_equivalence": (
            reference["diagnostic_snapshots"]
            == candidate["diagnostic_snapshots"]
        ),
        "fusion_cumulative_diagnostic_equivalence": (
            reference["fusion_cumulative_diagnostics"]
            == candidate["fusion_cumulative_diagnostics"]
        ),
        "final_global_track_equivalence": (
            reference["final_tracks_sha256"]
            == candidate["final_tracks_sha256"]
        ),
        "consistency_evidence_equivalence": (
            reference["consistency_evidence_sha256"]
            == candidate["consistency_evidence_sha256"]
        ),
        "complete_materialization_count_preserved": (
            reference_materializations > 0
            and reference_materializations == candidate_materializations
            and len(reference["publication_digests"])
            == len(candidate["publication_digests"])
        ),
        "reference_per_track_copy_observed": (
            int(
                reference_counts.get(
                    "per_track_shared_audit_mapping_copy_count",
                    0,
                )
            )
            > 0
        ),
        "candidate_per_track_copy_eliminated": (
            int(
                candidate_counts.get(
                    "per_track_shared_audit_mapping_copy_count",
                    0,
                )
            )
            == 0
        ),
        "candidate_shared_value_reuse_accounted": (
            int(candidate_counts.get("shared_audit_value_reuse_count", 0))
            == 3 * candidate_materializations
        ),
        "candidate_immutable_tree_built": (
            int(
                candidate_counts.get(
                    "immutable_shared_mapping_build_count",
                    0,
                )
            )
            > 0
        ),
        "online_truth_use_count_zero": (
            int(input_summary["online_truth_use_count"]) == 0
        ),
    }


def _variant_repeat_determinism(
    runs: Sequence[Mapping[str, Any]],
) -> bool:
    signatures = {
        (
            item["scan_input_digests_sha256"],
            item["fusion_digests_sha256"],
            item["publication_digests_sha256"],
            item["operation_snapshots_sha256"],
            item["diagnostic_snapshots_sha256"],
            item["final_tracks_sha256"],
            item["consistency_evidence_sha256"],
            _json_sha256(item["publication_materialization_diagnostics"]),
        )
        for item in runs
    }
    return len(signatures) == 1


def _timing_summary(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = np.asarray(
        [float(item["fusion_wall_time_s"]) for item in runs],
        dtype=float,
    )
    return {
        "sample_count": int(values.size),
        "p50_fusion_wall_time_s": float(np.quantile(values, 0.5)),
        "p95_fusion_wall_time_s": float(np.quantile(values, 0.95)),
        "min_fusion_wall_time_s": float(np.min(values)),
        "max_fusion_wall_time_s": float(np.max(values)),
    }


def _compact_result(result: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "variant",
        "scan_input_digests_sha256",
        "scan_input_close_digest",
        "scan_input_audit",
        "scan_claims_sha256",
        "release_group_sizes",
        "fusion_digests_sha256",
        "publication_digests_sha256",
        "operation_snapshots_sha256",
        "operation_totals",
        "diagnostic_snapshots_sha256",
        "fusion_cumulative_diagnostics",
        "publication_materialization_diagnostics",
        "final_tracks_sha256",
        "consistency_evidence_sha256",
        "fusion_wall_time_s",
        "profile",
    )
    return {key: result[key] for key in keys}


def _profile_summary(path: Path) -> dict[str, Any]:
    stats = pstats.Stats(str(path))
    selected: dict[str, dict[str, Any]] = {}
    for label, filename, function_name in _PROFILE_SPECS:
        matches = [
            (key, values)
            for key, values in stats.stats.items()
            if Path(str(key[0])).name == filename and key[2] == function_name
        ]
        selected[label] = {
            "primitive_call_count": int(
                sum(int(values[0]) for _, values in matches)
            ),
            "total_call_count": int(
                sum(int(values[1]) for _, values in matches)
            ),
            "self_time_s": float(
                sum(float(values[2]) for _, values in matches)
            ),
            "cumulative_time_s": float(
                sum(float(values[3]) for _, values in matches)
            ),
        }
    return {
        "profile_path": str(path),
        "profile_total_time_s": float(stats.total_tt),
        "selected_functions": selected,
        "timing_used_for_acceptance": False,
    }
