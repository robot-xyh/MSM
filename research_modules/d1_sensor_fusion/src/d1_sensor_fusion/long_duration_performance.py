from __future__ import annotations

import cProfile
from dataclasses import asdict, is_dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import pstats
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from .scalable_3d import Scalable3DFusionAdapter
from .scan_fusion_performance import load_frozen_sensor_scans
from .scan_input import SensorScanFrame


LONG_DURATION_PERFORMANCE_SCHEMA_VERSION = "d1.long_duration_performance.v1"
FUSED_TRACK_PUBLICATION_AUDIT_SCHEMA_VERSION = (
    "d1.fused_track_publication_audit.v2"
)

_BATCH_OPERATION_FIELDS = (
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
)


def run_long_duration_variant(
    scans: Sequence[SensorScanFrame],
    *,
    variant: str,
    direct_checkpoint_state_queries: bool,
    fixed_lag_checkpoint_suffix_reuse: bool,
    trusted_replay_checkpoint_prefix: bool,
    cached_consistency_prefix_refresh: bool,
    profile_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run one frozen scan sequence while separating fusion and hash time."""

    adapter = Scalable3DFusionAdapter(
        direct_checkpoint_state_queries=direct_checkpoint_state_queries,
        fixed_lag_checkpoint_suffix_reuse=fixed_lag_checkpoint_suffix_reuse,
        trusted_replay_checkpoint_prefix=trusted_replay_checkpoint_prefix,
        cached_consistency_prefix_refresh=cached_consistency_prefix_refresh,
    )
    operation_totals = {name: 0 for name in _BATCH_OPERATION_FIELDS}
    per_scan_semantic_digests: list[str] = []
    per_second: dict[str, dict[str, float | int]] = {}
    process_wall_time_s = 0.0
    semantic_hash_wall_time_s = 0.0
    profiler = cProfile.Profile() if profile_path is not None else None
    result = None

    for scan in scans:
        started = perf_counter()
        if profiler is not None:
            profiler.enable()
        result = adapter.process_scan_batch(scan.observations)
        if profiler is not None:
            profiler.disable()
        elapsed = perf_counter() - started
        process_wall_time_s += elapsed

        hash_started = perf_counter()
        per_scan_semantic_digests.append(_semantic_result_digest(result))
        semantic_hash_wall_time_s += perf_counter() - hash_started

        summary = result.summary.to_dict()
        for name in _BATCH_OPERATION_FIELDS:
            operation_totals[name] += int(summary[name])
        second_key = str(int(float(scan.arrival_timestamp)))
        second = per_second.setdefault(
            second_key,
            {"scan_count": 0, "observation_count": 0, "fusion_wall_time_s": 0.0},
        )
        second["scan_count"] = int(second["scan_count"]) + 1
        second["observation_count"] = int(second["observation_count"]) + len(
            scan.observations
        )
        second["fusion_wall_time_s"] = float(second["fusion_wall_time_s"]) + elapsed

    if result is None:
        raise ValueError("long-duration benchmark requires at least one released scan")

    profile = None
    if profiler is not None:
        destination = Path(profile_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(destination))
        profile = _profile_summary(destination)

    final_tracks = _semantic_track_snapshot(result.tracks)
    evidence = [item.to_dict() for item in adapter.consistency_evidence_records()]
    return {
        "variant": str(variant),
        "direct_checkpoint_state_queries": bool(direct_checkpoint_state_queries),
        "fixed_lag_checkpoint_suffix_reuse": bool(
            fixed_lag_checkpoint_suffix_reuse
        ),
        "trusted_replay_checkpoint_prefix": bool(
            trusted_replay_checkpoint_prefix
        ),
        "cached_consistency_prefix_refresh": bool(
            cached_consistency_prefix_refresh
        ),
        "scan_count": len(scans),
        "track_count": len(result.tracks),
        "process_wall_time_s": process_wall_time_s,
        "semantic_hash_wall_time_s": semantic_hash_wall_time_s,
        "operation_totals": operation_totals,
        "cumulative_diagnostics": (
            adapter.fusion_performance_diagnostics().to_dict()
        ),
        "per_second": per_second,
        "per_scan_semantic_digests": per_scan_semantic_digests,
        "per_scan_semantic_digests_sha256": _json_sha256(
            per_scan_semantic_digests
        ),
        "final_tracks_sha256": _json_sha256(final_tracks),
        "consistency_evidence_sha256": _json_sha256(evidence),
        "profile": profile,
    }


def compare_long_duration_variants(
    source: str | Path,
    *,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    scans, input_summary = load_frozen_sensor_scans(source)
    profile_root = None if profile_directory is None else Path(profile_directory)
    reference = run_long_duration_variant(
        scans,
        variant="pre_long_duration_optimization_reference",
        direct_checkpoint_state_queries=False,
        fixed_lag_checkpoint_suffix_reuse=False,
        trusted_replay_checkpoint_prefix=False,
        cached_consistency_prefix_refresh=False,
        profile_path=(
            None if profile_root is None else profile_root / "reference.prof"
        ),
    )
    optimized = run_long_duration_variant(
        scans,
        variant="checkpoint_state_and_rebase_suffix_reuse",
        direct_checkpoint_state_queries=True,
        fixed_lag_checkpoint_suffix_reuse=True,
        trusted_replay_checkpoint_prefix=True,
        cached_consistency_prefix_refresh=True,
        profile_path=(
            None if profile_root is None else profile_root / "optimized.prof"
        ),
    )

    reference_ops = reference["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    reference_diagnostics = reference["cumulative_diagnostics"]
    optimized_diagnostics = optimized["cumulative_diagnostics"]
    semantic_equal = (
        optimized["per_scan_semantic_digests"]
        == reference["per_scan_semantic_digests"]
    )
    filter_reduction = _reduction_fraction(
        int(reference_ops["replay_filter_update_count"]),
        int(optimized_ops["replay_filter_update_count"]),
    )
    has_fixed_lag_rebase = int(
        optimized_diagnostics["fixed_lag_rebase_count"]
    ) > 0
    acceptance = {
        "per_scan_semantic_equivalence": semantic_equal,
        "final_track_equivalence": (
            optimized["final_tracks_sha256"] == reference["final_tracks_sha256"]
        ),
        "consistency_evidence_equivalence": (
            optimized["consistency_evidence_sha256"]
            == reference["consistency_evidence_sha256"]
        ),
        "candidate_pair_count_preserved": (
            int(optimized_ops["association_candidate_pair_count"])
            == int(reference_ops["association_candidate_pair_count"])
        ),
        "innovation_solve_count_preserved": (
            int(optimized_ops["association_innovation_solve_count"])
            == int(reference_ops["association_innovation_solve_count"])
        ),
        "checkpoint_state_queries_exercised": (
            int(optimized_diagnostics["checkpoint_state_query_count"]) > 0
        ),
        "fixed_lag_suffix_reuse_exercised_when_applicable": (
            not has_fixed_lag_rebase
            or int(
                optimized_diagnostics[
                    "fixed_lag_checkpoint_suffix_reuse_count"
                ]
            )
            > 0
        ),
        "trusted_checkpoint_prefix_fast_path_exercised": (
            int(
                optimized_diagnostics[
                    "replay_checkpoint_prefix_fast_path_count"
                ]
            )
            > 0
        ),
        "cached_consistency_refresh_exercised": (
            int(optimized_diagnostics["cached_consistency_refresh_count"]) > 0
        ),
        "replay_filter_updates_not_increased": filter_reduction >= 0.0,
        "online_truth_use_count_zero": input_summary["online_truth_use_count"] == 0,
    }
    return {
        "schema_version": LONG_DURATION_PERFORMANCE_SCHEMA_VERSION,
        "input": input_summary,
        "reference": reference,
        "optimized": optimized,
        "comparison": {
            "fusion_wall_time_speedup": (
                float(reference["process_wall_time_s"])
                / float(optimized["process_wall_time_s"])
                if float(optimized["process_wall_time_s"]) > 0.0
                else None
            ),
            "replay_filter_update_reduction_fraction": filter_reduction,
            "history_replay_reduction_fraction": _reduction_fraction(
                int(reference_ops["history_replay_count"]),
                int(optimized_ops["history_replay_count"]),
            ),
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
        },
    }


def audit_fused_track_publications(source: str | Path) -> dict[str, Any]:
    """Audit legacy full snapshots and explicit state-only D1 publications."""

    path = Path(source)
    publication_count = 0
    materialized_snapshot_count = 0
    state_only_count = 0
    serialized_bytes = 0
    track_record_count = 0
    fusion_timestamps: set[float] = set()
    runtime_timestamps: set[float] = set()
    snapshot_hashes: set[str] = set()
    consecutive_unchanged_snapshot_count = 0
    previous_snapshot_hash: str | None = None
    state_change_publication_count = 0
    lineage_record_count = 0

    with path.open("rb") as stream:
        for raw_line in stream:
            record = json.loads(raw_line)
            if record.get("topic") != "modules.d1.fused_tracks":
                continue
            publication_count += 1
            serialized_bytes += len(raw_line)
            payload = record["payload"]
            runtime_timestamps.add(float(record["timestamp"]))
            fusion_timestamps.add(float(payload["summary"]["published_at"]))
            lineage_record_count += len(payload.get("observation_lineage", ()))
            tracks_materialized = payload.get("tracks_materialized", True)
            if not isinstance(tracks_materialized, bool):
                raise ValueError("tracks_materialized must be a boolean when present")
            tracks = payload.get("tracks", ())
            if not tracks_materialized:
                if tracks is not None and tracks != []:
                    raise ValueError(
                        "state-only D1 publication must encode tracks as [] or null"
                    )
                if int(payload.get("track_count", 0)) != 0:
                    raise ValueError("state-only D1 publication track_count must be zero")
                current_track_count = payload.get("current_track_count")
                if current_track_count is None or int(current_track_count) < 0:
                    raise ValueError(
                        "state-only D1 publication requires non-negative current_track_count"
                    )
                state_only_count += 1
                continue
            if tracks is None:
                raise ValueError(
                    "materialized D1 publication must contain a track sequence"
                )
            payload_track_count = int(payload.get("track_count", len(tracks)))
            if payload_track_count != len(tracks):
                raise ValueError(
                    "materialized D1 publication track_count must match len(tracks)"
                )
            if "current_track_count" in payload and int(
                payload["current_track_count"]
            ) != payload_track_count:
                raise ValueError(
                    "materialized D1 publication current_track_count must match track_count"
                )
            materialized_snapshot_count += 1
            track_record_count += len(tracks)
            snapshot_hash = _json_sha256(tracks)
            snapshot_hashes.add(snapshot_hash)
            if snapshot_hash == previous_snapshot_hash:
                consecutive_unchanged_snapshot_count += 1
            else:
                state_change_publication_count += 1
            previous_snapshot_hash = snapshot_hash

    if publication_count == 0:
        raise ValueError("no modules.d1.fused_tracks publications found")
    return {
        "schema_version": FUSED_TRACK_PUBLICATION_AUDIT_SCHEMA_VERSION,
        "source_path": str(path),
        "source_sha256": _sha256_file(path),
        "publication_count": publication_count,
        "materialized_snapshot_count": materialized_snapshot_count,
        "state_only_count": state_only_count,
        "serialized_bytes": serialized_bytes,
        "serialized_mebibytes": serialized_bytes / (1024.0 * 1024.0),
        "track_record_count": track_record_count,
        "lineage_record_count": lineage_record_count,
        "unique_runtime_timestamp_count": len(runtime_timestamps),
        "unique_fusion_timestamp_count": len(fusion_timestamps),
        "unique_track_snapshot_count": len(snapshot_hashes),
        "state_change_publication_count": state_change_publication_count,
        "consecutive_unchanged_snapshot_count": (
            consecutive_unchanged_snapshot_count
        ),
        "coalescible_same_fusion_timestamp_count": max(
            0,
            publication_count - len(fusion_timestamps),
        ),
    }


def write_long_duration_performance_report(
    report: Mapping[str, Any],
    *,
    publication_audit: Mapping[str, Any] | None,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    payload = dict(report)
    payload["publication_audit"] = (
        None if publication_audit is None else dict(publication_audit)
    )
    json_destination = Path(json_path)
    markdown_destination = Path(markdown_path)
    json_destination.parent.mkdir(parents=True, exist_ok=True)
    markdown_destination.parent.mkdir(parents=True, exist_ok=True)
    json_destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_destination.write_text(
        _markdown_report(payload),
        encoding="utf-8",
    )


def _semantic_result_digest(result: Any) -> str:
    summary = result.summary.to_dict()
    for name in _BATCH_OPERATION_FIELDS:
        summary.pop(name, None)
    return _json_sha256(
        {
            "tracks": _semantic_track_snapshot(result.tracks),
            "summary": summary,
        }
    )


def _semantic_track_snapshot(tracks: Sequence[Any]) -> dict[str, Any]:
    """Canonicalize one shared audit block plus every track-specific value."""

    shared_keys = ("association_audit", "latency_audit", "sensor_health")
    shared_audit: dict[str, Any] | None = None
    track_records = []
    for track in tracks:
        record = track.to_dict()
        metadata = dict(record["metadata"])
        candidate = {key: metadata.pop(key, None) for key in shared_keys}
        if shared_audit is None:
            shared_audit = candidate
        record["metadata"] = metadata
        track_records.append(record)
    return {
        "shared_audit": {} if shared_audit is None else shared_audit,
        "shared_audit_track_count": len(track_records),
        "track_records": track_records,
    }


def _json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, MappingProxyType):
        return dict(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _profile_summary(path: Path) -> dict[str, Any]:
    stats = pstats.Stats(str(path)).strip_dirs()
    selected_names = {
        "process_scan_batch",
        "_state_at",
        "_state_from_complete_replay_checkpoints",
        "_replay_record",
        "_prune_record",
        "_filter_update",
        "_scan_one_to_one_assignments",
        "_cached_non_radar_scan_cost_matrix",
        "global_tracks",
    }
    selected: dict[str, dict[str, float | int]] = {}
    for (_, _, function_name), values in stats.stats.items():
        if function_name not in selected_names:
            continue
        primitive_calls, total_calls, total_time, cumulative_time, _ = values
        entry = selected.setdefault(
            function_name,
            {
                "primitive_call_count": 0,
                "total_call_count": 0,
                "total_time_s": 0.0,
                "cumulative_time_s": 0.0,
            },
        )
        entry["primitive_call_count"] = int(entry["primitive_call_count"]) + int(
            primitive_calls
        )
        entry["total_call_count"] = int(entry["total_call_count"]) + int(
            total_calls
        )
        entry["total_time_s"] = float(entry["total_time_s"]) + float(total_time)
        entry["cumulative_time_s"] = float(entry["cumulative_time_s"]) + float(
            cumulative_time
        )
    return {
        "profile_path": str(path),
        "selected_functions": selected,
    }


def _reduction_fraction(reference: int, optimized: int) -> float:
    if reference <= 0:
        return 0.0 if optimized > reference else 1.0
    return 1.0 - float(optimized) / float(reference)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _markdown_report(report: Mapping[str, Any]) -> str:
    comparison = report["comparison"]
    reference = report["reference"]
    optimized = report["optimized"]
    reference_ops = reference["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    reference_diagnostics = reference["cumulative_diagnostics"]
    optimized_diagnostics = optimized["cumulative_diagnostics"]
    lines = [
        "# D1 长时固定滞后性能与发布审计",
        "",
        "## 结论",
        "",
        f"逐扫描语义等价验收：`{comparison['passed']}`。纯融合墙钟加速比为 "
        f"`{comparison['fusion_wall_time_speedup']:.3f}x`。语义哈希时间单独统计，"
        "不计入融合墙钟。",
        "",
        "## 融合对照",
        "",
        "| 指标 | 旧路径 | 优化路径 |",
        "| --- | ---: | ---: |",
        f"| 扫描数 | {reference['scan_count']} | {optimized['scan_count']} |",
        f"| 航迹数 | {reference['track_count']} | {optimized['track_count']} |",
        f"| 纯融合墙钟 / s | {reference['process_wall_time_s']:.3f} | {optimized['process_wall_time_s']:.3f} |",
        f"| 历史重放 | {reference_ops['history_replay_count']:,} | {optimized_ops['history_replay_count']:,} |",
        f"| 滤波更新 | {reference_ops['replay_filter_update_count']:,} | {optimized_ops['replay_filter_update_count']:,} |",
        f"| 检查点复用 | {reference_ops['replay_checkpoint_reuse_count']:,} | {optimized_ops['replay_checkpoint_reuse_count']:,} |",
        f"| 检查点状态查询 | {reference_diagnostics['checkpoint_state_query_count']:,} | {optimized_diagnostics['checkpoint_state_query_count']:,} |",
        f"| 固定滞后后缀复用 | {reference_diagnostics['fixed_lag_checkpoint_suffix_reuse_count']:,} | {optimized_diagnostics['fixed_lag_checkpoint_suffix_reuse_count']:,} |",
        f"| 合法前缀快路径 | {reference_diagnostics['replay_checkpoint_prefix_fast_path_count']:,} | {optimized_diagnostics['replay_checkpoint_prefix_fast_path_count']:,} |",
        f"| 缓存一致性刷新 | {reference_diagnostics['cached_consistency_refresh_count']:,} | {optimized_diagnostics['cached_consistency_refresh_count']:,} |",
        "",
        "逐扫描航迹、业务摘要、终态航迹和一致性证据均以确定性哈希比较。"
        "双时间戳、协方差、门控、固定滞后窗和在线真值隔离未改变。",
    ]
    audit = report.get("publication_audit")
    if audit is not None:
        lines.extend(
            [
                "",
                "## 发布审计",
                "",
                f"`modules.d1.fused_tracks` 共 {audit['publication_count']:,} 条，"
                f"其中完整快照 {audit.get('materialized_snapshot_count', audit['publication_count']):,} 条、"
                f"状态更新 {audit.get('state_only_count', 0):,} 条，"
                f"序列化体积 {audit['serialized_mebibytes']:.1f} MiB。"
                f"唯一融合时刻 {audit['unique_fusion_timestamp_count']:,} 个，"
                f"连续未变化快照 {audit['consecutive_unchanged_snapshot_count']:,} 条。",
                "",
                "D1 仍需逐个释放扫描完成有序融合和审计，但 main 无需把每次内部融合都写成"
                "全量航迹快照。建议按唯一融合时刻合并，同一时刻保留最后后验；状态未变化时"
                "记录轻量 heartbeat/lineage sidecar；状态变化、生命周期变化、质量跨档、固定"
                "周期关键帧和 episode 尾部仍发布全量快照。",
            ]
        )
    lines.extend(
        [
            "",
            "## 不退化合同",
            "",
            "- 每条接受观测仍保留 measurement_timestamp、arrival_timestamp、协方差和来源谱系。",
            "- 同一融合时刻合并时，只允许保留按既定顺序完成后的最后后验，不得跨时刻重排扫描。",
            "- D2 必须获得每次规范状态变化及其 observation lineage；不得因节流漏掉身份或生命周期事件。",
            "- 全量关键帧必须带单调序号、融合时刻、发布时刻和前序哈希；delta 丢失后可由关键帧恢复。",
            "- D6 仍能重建每条观测的接受、拒绝、乱序重放和航迹归属；不可用指标不得写成零。",
            "",
        ]
    )
    return "\n".join(lines)
