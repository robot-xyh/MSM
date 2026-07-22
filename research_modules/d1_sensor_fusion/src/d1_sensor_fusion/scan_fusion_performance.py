from __future__ import annotations

import cProfile
import hashlib
import json
import pstats
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from .scalable_3d import (
    Scalable3DFusionAdapter,
    sensor_observations_from_online_batch,
)
from .scan_input import ScanInputOrganizer, SensorScanFrame


SCAN_FUSION_PERFORMANCE_SCHEMA_VERSION = "d1.scan_fusion_performance.v1"
SCAN_ASSOCIATION_PERFORMANCE_SCHEMA_VERSION = (
    "d1.scan_association_performance.v1"
)
_OPERATION_FIELDS = (
    "history_replay_count",
    "finalization_replay_count",
    "state_cache_hit_count",
    "state_cache_miss_count",
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


def load_frozen_sensor_scans(path: str | Path) -> tuple[tuple[SensorScanFrame, ...], dict[str, Any]]:
    """Load identity-free bus observations through the production scan organizer."""

    source = Path(path)
    organizer = ScanInputOrganizer()
    released: list[SensorScanFrame] = []
    input_batch_count = 0
    input_observation_count = 0
    with source.open("r", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record.get("topic") != "sensor.observations":
                continue
            payload = record["payload"]
            observations = sensor_observations_from_online_batch(payload)
            input_batch_count += 1
            input_observation_count += len(observations)
            result = organizer.ingest(
                SensorScanFrame.from_observations(
                    observations,
                    scan_id=str(payload["batch_id"]),
                )
            )
            released.extend(result.released_scans)
    released.extend(organizer.close().released_scans)
    audit = organizer.audit_summary().to_dict()
    return tuple(released), {
        "source_path": str(source),
        "source_sha256": _sha256_file(source),
        "input_batch_count": input_batch_count,
        "input_observation_count": input_observation_count,
        "released_scan_count": len(released),
        "scan_input_audit": audit,
        "online_truth_use_count": 0,
    }


def run_scan_fusion_variant(
    scans: Sequence[SensorScanFrame],
    *,
    variant: str,
    incremental_replay_cache: bool,
    shared_publication_audit_snapshot: bool,
    scan_association_model_cache: bool = True,
    profile_path: str | Path | None = None,
) -> dict[str, Any]:
    adapter = Scalable3DFusionAdapter(
        incremental_replay_cache=incremental_replay_cache,
        shared_publication_audit_snapshot=shared_publication_audit_snapshot,
        scan_association_model_cache=scan_association_model_cache,
    )
    operation_totals = {name: 0 for name in _OPERATION_FIELDS}
    per_scan_semantic_digests: list[str] = []
    process_wall_time_s = 0.0
    profiler = cProfile.Profile() if profile_path is not None else None
    result = None

    for scan in scans:
        started = perf_counter()
        if profiler is not None:
            profiler.enable()
        result = adapter.process_scan_batch(scan.observations)
        if profiler is not None:
            profiler.disable()
        process_wall_time_s += perf_counter() - started
        summary = result.summary.to_dict()
        for name in _OPERATION_FIELDS:
            operation_totals[name] += int(summary[name])
        per_scan_semantic_digests.append(_semantic_result_digest(result))

    if result is None:
        raise ValueError("scan fusion benchmark requires at least one released scan")

    profile_summary = None
    if profiler is not None:
        destination = Path(profile_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(destination))
        profile_summary = _profile_summary(destination)

    final_tracks = _canonical([track.to_dict() for track in result.tracks])
    evidence = _canonical(
        [item.to_dict() for item in adapter.consistency_evidence_records()]
    )
    return {
        "variant": str(variant),
        "incremental_replay_cache": bool(incremental_replay_cache),
        "shared_publication_audit_snapshot": bool(
            shared_publication_audit_snapshot
        ),
        "scan_association_model_cache": bool(scan_association_model_cache),
        "scan_count": len(scans),
        "track_count": len(result.tracks),
        "process_wall_time_s": process_wall_time_s,
        "operation_totals": operation_totals,
        "per_scan_semantic_digests": tuple(per_scan_semantic_digests),
        "final_tracks_sha256": _json_sha256(final_tracks),
        "consistency_evidence_sha256": _json_sha256(evidence),
        "profile": profile_summary,
    }


def compare_scan_fusion_variants(
    source: str | Path,
    *,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    scans, input_summary = load_frozen_sensor_scans(source)
    profile_root = None if profile_directory is None else Path(profile_directory)
    legacy = run_scan_fusion_variant(
        scans,
        variant="uncached_reference",
        incremental_replay_cache=False,
        shared_publication_audit_snapshot=False,
    )
    optimized = run_scan_fusion_variant(
        scans,
        variant="incremental_checkpoint_cache",
        incremental_replay_cache=True,
        shared_publication_audit_snapshot=True,
    )
    if profile_root is not None:
        legacy_profiled = run_scan_fusion_variant(
            scans,
            variant="uncached_reference_profiled",
            incremental_replay_cache=False,
            shared_publication_audit_snapshot=False,
            profile_path=profile_root / "uncached_reference.prof",
        )
        optimized_profiled = run_scan_fusion_variant(
            scans,
            variant="incremental_checkpoint_cache_profiled",
            incremental_replay_cache=True,
            shared_publication_audit_snapshot=True,
            profile_path=profile_root / "incremental_checkpoint_cache.prof",
        )
        legacy["profile"] = legacy_profiled["profile"]
        optimized["profile"] = optimized_profiled["profile"]

    legacy_ops = legacy["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    per_scan_equal = (
        optimized["per_scan_semantic_digests"]
        == legacy["per_scan_semantic_digests"]
    )
    final_equal = optimized["final_tracks_sha256"] == legacy["final_tracks_sha256"]
    evidence_equal = (
        optimized["consistency_evidence_sha256"]
        == legacy["consistency_evidence_sha256"]
    )
    filter_reduction = _reduction_fraction(
        int(legacy_ops["replay_filter_update_count"]),
        int(optimized_ops["replay_filter_update_count"]),
    )
    health_reduction = _reduction_fraction(
        int(legacy_ops["sensor_health_snapshot_build_count"]),
        int(optimized_ops["sensor_health_snapshot_build_count"]),
    )
    acceptance = {
        "per_scan_semantic_equivalence": per_scan_equal,
        "final_track_equivalence": final_equal,
        "consistency_evidence_equivalence": evidence_equal,
        "replay_filter_update_reduction_at_least_90_percent": (
            filter_reduction >= 0.90
        ),
        "one_health_snapshot_per_scan": (
            int(optimized_ops["sensor_health_snapshot_build_count"])
            == len(scans)
        ),
        "online_truth_use_count_zero": input_summary["online_truth_use_count"] == 0,
    }
    return {
        "schema_version": SCAN_FUSION_PERFORMANCE_SCHEMA_VERSION,
        "input": input_summary,
        "uncached_reference": legacy,
        "optimized": optimized,
        "comparison": {
            "wall_time_speedup": (
                legacy["process_wall_time_s"] / optimized["process_wall_time_s"]
                if optimized["process_wall_time_s"] > 0.0
                else None
            ),
            "replay_filter_update_reduction_fraction": filter_reduction,
            "sensor_health_snapshot_reduction_fraction": health_reduction,
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
        },
    }


def compare_scan_association_variants(
    source: str | Path,
    *,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Compare the previous default with scan-local model/projection reuse."""

    scans, input_summary = load_frozen_sensor_scans(source)
    profile_root = None if profile_directory is None else Path(profile_directory)
    current_default = run_scan_fusion_variant(
        scans,
        variant="current_default",
        incremental_replay_cache=True,
        shared_publication_audit_snapshot=True,
        scan_association_model_cache=False,
    )
    optimized = run_scan_fusion_variant(
        scans,
        variant="scan_association_model_cache",
        incremental_replay_cache=True,
        shared_publication_audit_snapshot=True,
        scan_association_model_cache=True,
    )
    if profile_root is not None:
        current_profiled = run_scan_fusion_variant(
            scans,
            variant="current_default_profiled",
            incremental_replay_cache=True,
            shared_publication_audit_snapshot=True,
            scan_association_model_cache=False,
            profile_path=profile_root / "current_default.prof",
        )
        optimized_profiled = run_scan_fusion_variant(
            scans,
            variant="scan_association_model_cache_profiled",
            incremental_replay_cache=True,
            shared_publication_audit_snapshot=True,
            scan_association_model_cache=True,
            profile_path=profile_root / "scan_association_model_cache.prof",
        )
        current_default["profile"] = current_profiled["profile"]
        optimized["profile"] = optimized_profiled["profile"]

    current_ops = current_default["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    per_scan_equal = (
        optimized["per_scan_semantic_digests"]
        == current_default["per_scan_semantic_digests"]
    )
    final_equal = (
        optimized["final_tracks_sha256"]
        == current_default["final_tracks_sha256"]
    )
    evidence_equal = (
        optimized["consistency_evidence_sha256"]
        == current_default["consistency_evidence_sha256"]
    )
    model_reduction = _reduction_fraction(
        int(current_ops["association_measurement_model_build_count"]),
        int(optimized_ops["association_measurement_model_build_count"]),
    )
    projection_reduction = _reduction_fraction(
        int(current_ops["association_projection_build_count"]),
        int(optimized_ops["association_projection_build_count"]),
    )
    acceptance = {
        "per_scan_semantic_equivalence": per_scan_equal,
        "final_track_equivalence": final_equal,
        "consistency_evidence_equivalence": evidence_equal,
        "candidate_pair_count_preserved": (
            int(current_ops["association_candidate_pair_count"])
            == int(optimized_ops["association_candidate_pair_count"])
        ),
        "innovation_solve_count_preserved": (
            int(current_ops["association_innovation_solve_count"])
            == int(optimized_ops["association_innovation_solve_count"])
        ),
        "measurement_model_build_reduction_at_least_95_percent": (
            model_reduction >= 0.95
        ),
        "projection_build_count_not_increased": (
            int(optimized_ops["association_projection_build_count"])
            <= int(current_ops["association_projection_build_count"])
        ),
        "online_truth_use_count_zero": input_summary["online_truth_use_count"] == 0,
    }
    return {
        "schema_version": SCAN_ASSOCIATION_PERFORMANCE_SCHEMA_VERSION,
        "input": input_summary,
        "current_default": current_default,
        "optimized": optimized,
        "comparison": {
            "wall_time_speedup": (
                current_default["process_wall_time_s"]
                / optimized["process_wall_time_s"]
                if optimized["process_wall_time_s"] > 0.0
                else None
            ),
            "measurement_model_build_reduction_fraction": model_reduction,
            "projection_build_reduction_fraction": projection_reduction,
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
        },
    }


def write_scan_fusion_performance_report(
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
        json.dumps(_canonical(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_destination.write_text(_markdown_report(report), encoding="utf-8")


def write_scan_association_performance_report(
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
        json.dumps(_canonical(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_destination.write_text(
        _association_markdown_report(report),
        encoding="utf-8",
    )


def _semantic_result_digest(result: Any) -> str:
    summary = result.summary.to_dict()
    for name in _OPERATION_FIELDS:
        summary.pop(name, None)
    return _json_sha256(
        {
            "tracks": [track.to_dict() for track in result.tracks],
            "summary": summary,
        }
    )


def _profile_summary(path: Path) -> dict[str, Any]:
    stats = pstats.Stats(str(path)).strip_dirs()
    names = {
        "process_scan_batch",
        "_scan_one_to_one_assignments",
        "_cached_non_radar_scan_cost_matrix",
        "_association_score",
        "_innovation_nis",
        "_innovation_nis_from_model",
        "_state_at",
        "_replay_record",
        "_filter_update",
        "measurement_model_for",
        "numerical_jacobian",
        "global_tracks",
        "_to_global_track",
        "sensor_health_summaries",
    }
    selected: dict[str, dict[str, float | int]] = {}
    for (_, _, function_name), values in stats.stats.items():
        if function_name not in names:
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
        entry["primitive_call_count"] += int(primitive_calls)
        entry["total_call_count"] += int(total_calls)
        entry["total_time_s"] += float(total_time)
        entry["cumulative_time_s"] += float(cumulative_time)
    return {
        "profile_path": str(path),
        "profile_total_calls": int(stats.total_calls),
        "profile_primitive_calls": int(stats.prim_calls),
        "profile_total_time_s": float(stats.total_tt),
        "functions": selected,
    }


def _markdown_report(report: Mapping[str, Any]) -> str:
    source = report["input"]
    audit = source["scan_input_audit"]
    legacy = report["uncached_reference"]
    optimized = report["optimized"]
    comparison = report["comparison"]
    legacy_ops = legacy["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    acceptance = comparison["acceptance"]
    lines = [
        "# D1逐扫描融合性能基准",
        "",
        "## 结论",
        "",
        (
            "冻结输入上的逐扫描航迹、批次摘要和一致性证据保持等价。"
            f"历史滤波更新由 {legacy_ops['replay_filter_update_count']:,} 次降至 "
            f"{optimized_ops['replay_filter_update_count']:,} 次，"
            f"操作数下降 {comparison['replay_filter_update_reduction_fraction']:.1%}。"
        ),
        (
            f"纯融合墙钟由 {legacy['process_wall_time_s']:.3f} 秒降至 "
            f"{optimized['process_wall_time_s']:.3f} 秒，本机单次对照加速 "
            f"{comparison['wall_time_speedup']:.2f} 倍。墙钟只用于说明，"
            "验收依据是确定性操作数和语义哈希。"
        ),
        "",
        "## 输入",
        "",
        f"- 输入文件：`{source['source_path']}`",
        f"- SHA-256：`{source['source_sha256']}`",
        f"- 扫描/观测：{source['released_scan_count']} / {source['input_observation_count']}",
        f"- 重排扫描：{audit['reordered_scan_count']}",
        (
            f"- 峰值缓冲：{audit['maximum_buffered_scan_count']} 扫描 / "
            f"{audit['maximum_buffered_observation_count']} 观测"
        ),
        "- 在线真值使用：0",
        "",
        "## 操作计数",
        "",
        "| 指标 | 未缓存参考 | 增量检查点 |",
        "| --- | ---: | ---: |",
    ]
    for name in _OPERATION_FIELDS:
        lines.append(
            f"| `{name}` | {legacy_ops[name]:,} | {optimized_ops[name]:,} |"
        )
    if legacy.get("profile") is not None and optimized.get("profile") is not None:
        legacy_functions = legacy["profile"]["functions"]
        optimized_functions = optimized["profile"]["functions"]
        lines.extend(
            [
                "",
                "## 函数剖析",
                "",
                (
                    "下表为 cProfile 累计时间。profiler 会放大墙钟，"
                    "只用于定位函数占比。"
                ),
                "",
                "| 函数 | 未缓存调用 | 未缓存累计秒 | 优化调用 | 优化累计秒 |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for name in (
            "process_scan_batch",
            "_replay_record",
            "_state_at",
            "_filter_update",
            "global_tracks",
            "sensor_health_summaries",
        ):
            before = legacy_functions[name]
            after = optimized_functions[name]
            lines.append(
                f"| `{name}` | {before['total_call_count']:,} | "
                f"{before['cumulative_time_s']:.3f} | "
                f"{after['total_call_count']:,} | "
                f"{after['cumulative_time_s']:.3f} |"
            )
    lines.extend(
        [
            "",
            "## 验收",
            "",
            *[
                f"- {'通过' if passed else '失败'}：`{name}`"
                for name, passed in acceptance.items()
            ],
            "",
            "## 边界",
            "",
            "本基准证明冻结质点输入上的 D1 逐扫描语义等价和操作数下降。",
            "不证明真实传感器精度、AirSim 性能、200对200完整闭环实时性或物理拦截效果。",
            "",
        ]
    )
    return "\n".join(lines)


def _association_markdown_report(report: Mapping[str, Any]) -> str:
    source = report["input"]
    audit = source["scan_input_audit"]
    current = report["current_default"]
    optimized = report["optimized"]
    comparison = report["comparison"]
    current_ops = current["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    lines = [
        "# D1扫描关联工作区性能基准",
        "",
        "## 结论",
        "",
        (
            "当前默认路径与扫描内模型缓存路径的逐扫描航迹、批次语义、"
            "最终航迹和一致性证据保持等价。"
        ),
        (
            "量测模型构造由 "
            f"{current_ops['association_measurement_model_build_count']:,} 次降至 "
            f"{optimized_ops['association_measurement_model_build_count']:,} 次，"
            f"下降 {comparison['measurement_model_build_reduction_fraction']:.2%}。"
        ),
        (
            f"纯融合墙钟由 {current['process_wall_time_s']:.3f} 秒降至 "
            f"{optimized['process_wall_time_s']:.3f} 秒，本机单次对照加速 "
            f"{comparison['wall_time_speedup']:.2f} 倍。墙钟只作说明，"
            "验收依据是语义哈希和确定性操作计数。"
        ),
        "",
        "## 输入",
        "",
        f"- 输入文件：`{source['source_path']}`",
        f"- SHA-256：`{source['source_sha256']}`",
        f"- 扫描/观测：{source['released_scan_count']} / {source['input_observation_count']}",
        f"- 重排扫描：{audit['reordered_scan_count']}",
        (
            f"- 峰值缓冲：{audit['maximum_buffered_scan_count']} 扫描 / "
            f"{audit['maximum_buffered_observation_count']} 观测"
        ),
        "- 在线真值使用：0",
        "",
        "## 操作计数",
        "",
        "| 指标 | 当前默认 | 扫描内缓存 |",
        "| --- | ---: | ---: |",
    ]
    for name in (
        "association_candidate_pair_count",
        "association_measurement_model_build_count",
        "association_projection_build_count",
        "association_innovation_solve_count",
        "association_radar_track_state_build_count",
        "association_radar_observation_state_build_count",
        "global_track_materialization_count",
    ):
        lines.append(
            f"| `{name}` | {current_ops[name]:,} | {optimized_ops[name]:,} |"
        )

    if current.get("profile") is not None and optimized.get("profile") is not None:
        current_functions = current["profile"]["functions"]
        optimized_functions = optimized["profile"]["functions"]
        lines.extend(
            [
                "",
                "## 函数剖析",
                "",
                "cProfile 会放大绝对墙钟，本表只用于解释剩余热点。",
                "",
                "| 函数 | 当前调用 | 当前累计秒 | 优化调用 | 优化累计秒 |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for name in (
            "process_scan_batch",
            "_scan_one_to_one_assignments",
            "_association_score",
            "_cached_non_radar_scan_cost_matrix",
            "measurement_model_for",
            "numerical_jacobian",
            "global_tracks",
        ):
            before = current_functions.get(name, {})
            after = optimized_functions.get(name, {})
            lines.append(
                f"| `{name}` | {int(before.get('total_call_count', 0)):,} | "
                f"{float(before.get('cumulative_time_s', 0.0)):.3f} | "
                f"{int(after.get('total_call_count', 0)):,} | "
                f"{float(after.get('cumulative_time_s', 0.0)):.3f} |"
            )

    lines.extend(
        [
            "",
            "## 验收",
            "",
            *[
                f"- {'通过' if passed else '失败'}：`{name}`"
                for name, passed in comparison["acceptance"].items()
            ],
            "",
            "## 边界",
            "",
            "本基准只证明冻结输入上的扫描内模型复用保持 D1 输出语义并减少重复构造。",
            "候选对数量、每对创新协方差求解、扫描原子性和 Hungarian 分配均未减少。",
            "结果不证明 AirSim、传感器精度或200对200完整系统已经实时。",
            "",
        ]
    )
    return "\n".join(lines)


def _canonical(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _canonical(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _json_sha256(value: Any) -> str:
    payload = json.dumps(
        _canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reduction_fraction(baseline: int, optimized: int) -> float:
    if baseline <= 0:
        return 0.0
    return float((baseline - optimized) / baseline)
