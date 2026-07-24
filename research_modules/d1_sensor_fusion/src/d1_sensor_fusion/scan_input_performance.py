from __future__ import annotations

import gc
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

import numpy as np

from .scan_input import (
    SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
    SCAN_INPUT_REFERENCE_IMPLEMENTATION,
    ScanInputOrganizer,
    SensorScanFrame,
)
from .tail_latency_performance import load_frozen_sensor_frames


SCAN_INPUT_PERFORMANCE_BENCHMARK_SCHEMA_VERSION = (
    "d1.scan_input.performance_benchmark.v1"
)


def benchmark_scan_input_implementations(
    source: str | Path,
    *,
    repeat_count: int = 5,
    benchmark_scan_count: int | None = None,
) -> dict[str, Any]:
    """Compare the frozen reference and default candidate on identical frames."""

    if repeat_count < 1:
        raise ValueError("repeat_count must be positive")
    frames, input_summary = load_frozen_sensor_frames(source)
    if benchmark_scan_count is None:
        selected_frames = frames
    else:
        if benchmark_scan_count < 1:
            raise ValueError("benchmark_scan_count must be positive")
        selected_frames = frames[: min(len(frames), int(benchmark_scan_count))]

    reference_snapshot = _semantic_snapshot(
        selected_frames,
        implementation=SCAN_INPUT_REFERENCE_IMPLEMENTATION,
    )
    candidate_snapshot = _semantic_snapshot(
        selected_frames,
        implementation=SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
    )
    acceptance = {
        "claim_content_frame_digest_equivalence": (
            reference_snapshot["claim_records"]
            == candidate_snapshot["claim_records"]
        ),
        "result_event_field_equivalence": (
            reference_snapshot["result_records"]
            == candidate_snapshot["result_records"]
        ),
        "release_order_equivalence": (
            reference_snapshot["release_order"]
            == candidate_snapshot["release_order"]
        ),
        "audit_summary_equivalence": (
            reference_snapshot["final_audit"]
            == candidate_snapshot["final_audit"]
        ),
        "default_candidate_selected": (
            ScanInputOrganizer().execution_config()["implementation"]
            == SCAN_INPUT_CANDIDATE_IMPLEMENTATION
        ),
    }
    timing = _interleaved_timings(
        selected_frames,
        repeat_count=repeat_count,
    )
    return {
        "schema_version": SCAN_INPUT_PERFORMANCE_BENCHMARK_SCHEMA_VERSION,
        "input": {
            "source_name": Path(source).name,
            "source_sha256": input_summary["source_sha256"],
            "source_frame_count": input_summary["input_batch_count"],
            "source_observation_count": input_summary["input_observation_count"],
            "benchmark_frame_count": len(selected_frames),
            "benchmark_observation_count": sum(
                len(frame.observations) for frame in selected_frames
            ),
            "online_truth_use_count": input_summary["online_truth_use_count"],
            "frames_preconstructed_before_timing": True,
        },
        "implementations": {
            "reference": SCAN_INPUT_REFERENCE_IMPLEMENTATION,
            "candidate": SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
            "candidate_is_default": True,
        },
        "acceptance": acceptance,
        "passed": all(acceptance.values()),
        "reference": _compact_snapshot(reference_snapshot),
        "candidate": _compact_snapshot(candidate_snapshot),
        "interleaved_wall_time": timing,
        "evidence_boundary": {
            "d1_owned_frozen_replay_benchmark": True,
            "wall_time_used_for_acceptance": False,
            "fusion_included": False,
            "d2_association_included": False,
            "airsim_included": False,
            "formal_main_13_pair_matrix_included": False,
            "system_realtime_gap_closed": False,
        },
    }


def write_scan_input_performance_report(
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
        render_scan_input_performance_report_cn(report),
        encoding="utf-8",
    )


def render_scan_input_performance_report_cn(report: Mapping[str, Any]) -> str:
    source = report["input"]
    timing = report["interleaved_wall_time"]
    reference_timing = timing["reference"]
    candidate_timing = timing["candidate"]
    reference_operations = report["reference"]["performance_diagnostics"]
    candidate_operations = report["candidate"]["performance_diagnostics"]
    lines = [
        "# D1 扫描输入 reference/candidate 专项基准",
        "",
        "## 结论",
        "",
        f"严格等价验收：`{report['passed']}`。candidate 是默认路径，reference 保留为"
        "显式可选路径。墙钟只作专项性能描述，不参与等价放行。",
        "",
        "本次输入为 "
        f"`{source['benchmark_frame_count']:,}` 帧、"
        f"`{source['benchmark_observation_count']:,}` 条匿名观测；冻结文件 "
        f"SHA-256 为 `{source['source_sha256']}`。计时前已完成帧构造，结果不包含"
        "传感器 payload 转换、融合、D2 关联或 AirSim。",
        "",
        "## 严格等价",
        "",
    ]
    for name, passed in report["acceptance"].items():
        lines.append(f"- `{name}`：`{passed}`")
    lines.extend(
        [
            "",
            "## 操作计数",
            "",
            "| 操作 | reference | candidate |",
            "| --- | ---: | ---: |",
        ]
    )
    for field in (
        "claim_build_count",
        "claim_observation_count",
        "source_lineage_reconstruction_count",
        "cached_source_lineage_reuse_count",
        "lineage_sort_key_construction_count",
        "buffer_partition_pass_count",
        "buffer_partition_item_visit_count",
        "buffered_observation_count_rescan_count",
        "buffered_observation_count_rescan_item_visit_count",
        "buffered_observation_count_cache_read_count",
    ):
        lines.append(
            f"| `{field}` | {int(reference_operations[field]):,} | "
            f"{int(candidate_operations[field]):,} |"
        )
    lines.extend(
        [
            "",
            "## 交错墙钟",
            "",
            f"交错运行 `{timing['repeat_count']}` 轮。reference P50/P95 为 "
            f"`{reference_timing['p50_s']:.6f}/"
            f"{reference_timing['p95_s']:.6f} s`；candidate P50/P95 为 "
            f"`{candidate_timing['p50_s']:.6f}/"
            f"{candidate_timing['p95_s']:.6f} s`。P50 加速比为 "
            f"`{timing['p50_speedup']:.3f}x`，P50 墙钟下降 "
            f"`{timing['p50_reduction_percent']:.3f}%`。",
            "",
            "## 证据边界",
            "",
            "- 本结果属于 D1 实现与冻结回放专项证据。",
            "- main 正式 13-pair 矩阵尚未运行，不能据此关闭系统实时 P1。",
            "- 本轮没有改变双时间戳、NED、协方差、真值隔离、6 秒 fixed-lag、"
            "量测频率、缓冲门限或 global_track_id 合同。",
            "",
        ]
    )
    return "\n".join(lines)


def _semantic_snapshot(
    frames: Sequence[SensorScanFrame],
    *,
    implementation: str,
) -> dict[str, Any]:
    organizer = ScanInputOrganizer(implementation=implementation)
    result_records: list[dict[str, Any]] = []
    release_order: list[str] = []
    for frame in frames:
        result = organizer.ingest(frame)
        release_order.extend(item.scan_id for item in result.released_scans)
        result_records.append(
            {
                "released_scan_ids": tuple(
                    item.scan_id for item in result.released_scans
                ),
                "events": tuple(item.to_dict() for item in result.events),
                "audit": result.audit.to_dict(),
            }
        )
    tail = organizer.close()
    release_order.extend(item.scan_id for item in tail.released_scans)
    result_records.append(
        {
            "released_scan_ids": tuple(
                item.scan_id for item in tail.released_scans
            ),
            "events": tuple(item.to_dict() for item in tail.events),
            "audit": tail.audit.to_dict(),
        }
    )
    claim_records = tuple(
        {
            "scan_key": claim.scan_key,
            "lineage_digests": claim.lineage_digests,
            "source_lineage_digest": claim.source_lineage_digest,
            "content_digest": claim.content_digest,
            "frame_digest": claim.frame_digest,
            "measurement_timestamp": claim.measurement_timestamp,
            "arrival_timestamp": claim.arrival_timestamp,
        }
        for _, claim in sorted(organizer._scan_claims.items())
    )
    return {
        "result_records": tuple(result_records),
        "release_order": tuple(release_order),
        "claim_records": claim_records,
        "final_audit": tail.audit.to_dict(),
        "execution_config": organizer.execution_config(),
        "performance_diagnostics": organizer.performance_diagnostics(),
    }


def _compact_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "result_stream_sha256": _canonical_sha256(snapshot["result_records"]),
        "release_order_sha256": _canonical_sha256(snapshot["release_order"]),
        "claim_registry_sha256": _canonical_sha256(snapshot["claim_records"]),
        "final_audit": snapshot["final_audit"],
        "execution_config": snapshot["execution_config"],
        "performance_diagnostics": snapshot["performance_diagnostics"],
    }


def _interleaved_timings(
    frames: Sequence[SensorScanFrame],
    *,
    repeat_count: int,
) -> dict[str, Any]:
    timings = {
        SCAN_INPUT_REFERENCE_IMPLEMENTATION: [],
        SCAN_INPUT_CANDIDATE_IMPLEMENTATION: [],
    }
    run_order: list[str] = []
    for repeat_index in range(repeat_count):
        order = (
            (
                SCAN_INPUT_REFERENCE_IMPLEMENTATION,
                SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
            )
            if repeat_index % 2 == 0
            else (
                SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
                SCAN_INPUT_REFERENCE_IMPLEMENTATION,
            )
        )
        for implementation in order:
            gc.collect()
            started = perf_counter()
            organizer = ScanInputOrganizer(implementation=implementation)
            for frame in frames:
                organizer.ingest(frame)
            organizer.close()
            timings[implementation].append(perf_counter() - started)
            run_order.append(implementation)

    reference = _timing_summary(
        timings[SCAN_INPUT_REFERENCE_IMPLEMENTATION]
    )
    candidate = _timing_summary(
        timings[SCAN_INPUT_CANDIDATE_IMPLEMENTATION]
    )
    return {
        "repeat_count": repeat_count,
        "run_order": tuple(run_order),
        "reference": reference,
        "candidate": candidate,
        "p50_speedup": reference["p50_s"] / candidate["p50_s"],
        "p50_reduction_percent": (
            100.0
            * (reference["p50_s"] - candidate["p50_s"])
            / reference["p50_s"]
        ),
        "wall_time_used_for_acceptance": False,
    }


def _timing_summary(values: Sequence[float]) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    return {
        "samples_s": tuple(float(item) for item in array),
        "mean_s": float(np.mean(array)),
        "p50_s": float(np.percentile(array, 50.0)),
        "p95_s": float(np.percentile(array, 95.0)),
        "min_s": float(np.min(array)),
        "max_s": float(np.max(array)),
    }


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
