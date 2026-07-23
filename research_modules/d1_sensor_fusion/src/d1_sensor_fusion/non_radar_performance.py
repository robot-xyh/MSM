from __future__ import annotations

import os
import platform
from collections.abc import Sequence
from pathlib import Path
from statistics import fmean, median
from typing import Any

import numpy as np

from .long_duration_performance import run_coalesced_release_schedule_variant
from .scan_fusion_performance import load_frozen_sensor_scan_release_groups
from .scan_input import SensorScanFrame


NON_RADAR_INNOVATION_PERFORMANCE_SCHEMA_VERSION = (
    "d1.non_radar_innovation_performance.v1"
)
_SEMANTIC_FIELDS = (
    "per_scan_semantic_digests_sha256",
    "final_tracks_sha256",
    "consistency_evidence_sha256",
    "operation_totals",
    "cumulative_diagnostics",
    "track_count",
    "materialized_snapshot_count",
    "state_only_scan_count",
)


def benchmark_batched_non_radar_innovation(
    source: str | Path,
    *,
    repeat_count: int = 5,
    warmup_count: int = 1,
    maximum_scan_count: int | None = None,
    warmup_scan_count: int | None = 128,
) -> dict[str, Any]:
    """Compare scalar and batched innovation solves in one Python process."""

    if repeat_count < 1:
        raise ValueError("repeat_count must be positive")
    if warmup_count < 0:
        raise ValueError("warmup_count must be non-negative")
    release_groups, input_summary = load_frozen_sensor_scan_release_groups(source)
    measured_groups = _release_group_prefix(
        release_groups,
        maximum_scan_count,
    )
    if not measured_groups:
        raise ValueError("benchmark requires at least one released scan")
    warmup_groups = _release_group_prefix(
        measured_groups,
        warmup_scan_count,
    )

    for _ in range(warmup_count):
        _run_variant(warmup_groups, batched=False, variant="warmup_scalar")
        _run_variant(warmup_groups, batched=True, variant="warmup_batched")

    measured: dict[str, list[dict[str, Any]]] = {
        "scalar_per_candidate": [],
        "batched_matrix_stack": [],
    }
    for repetition in range(repeat_count):
        order = (
            (False, True)
            if repetition % 2 == 0
            else (True, False)
        )
        for batched in order:
            key = "batched_matrix_stack" if batched else "scalar_per_candidate"
            result = _run_variant(
                measured_groups,
                batched=batched,
                variant=f"{key}_repeat_{repetition + 1:02d}",
            )
            measured[key].append(_compact_result(result))

    reference = measured["scalar_per_candidate"][0]
    equivalence = {
        field: all(
            result[field] == reference[field]
            for results in measured.values()
            for result in results
        )
        for field in _SEMANTIC_FIELDS
    }
    scalar_times = [
        float(result["process_wall_time_s"])
        for result in measured["scalar_per_candidate"]
    ]
    batched_times = [
        float(result["process_wall_time_s"])
        for result in measured["batched_matrix_stack"]
    ]
    scalar_statistics = _timing_statistics(scalar_times)
    batched_statistics = _timing_statistics(batched_times)
    p50_speedup = (
        scalar_statistics["p50_s"] / batched_statistics["p50_s"]
        if batched_statistics["p50_s"] > 0.0
        else None
    )
    mean_speedup = (
        scalar_statistics["mean_s"] / batched_statistics["mean_s"]
        if batched_statistics["mean_s"] > 0.0
        else None
    )
    acceptance = {
        **{f"semantic_{key}": value for key, value in equivalence.items()},
        "online_truth_use_count_zero": (
            int(input_summary["online_truth_use_count"]) == 0
        ),
        "p50_improvement_at_least_10_percent": (
            p50_speedup is not None and p50_speedup >= (1.0 / 0.9)
        ),
    }
    selected_scan_count = sum(len(group) for group in measured_groups)
    selected_observation_count = sum(
        len(scan.observations)
        for group in measured_groups
        for scan in group
    )
    return {
        "schema_version": NON_RADAR_INNOVATION_PERFORMANCE_SCHEMA_VERSION,
        "process_id": os.getpid(),
        "machine": _machine_summary(),
        "input": {
            **input_summary,
            "selected_scan_count": selected_scan_count,
            "selected_observation_count": selected_observation_count,
            "maximum_scan_count": maximum_scan_count,
        },
        "protocol": {
            "same_process": True,
            "warmup_count_per_variant": warmup_count,
            "warmup_scan_count": sum(len(group) for group in warmup_groups),
            "repeat_count_per_variant": repeat_count,
            "alternating_variant_order": True,
        },
        "scalar_per_candidate": {
            "timing": scalar_statistics,
            "runs": measured["scalar_per_candidate"],
        },
        "batched_matrix_stack": {
            "timing": batched_statistics,
            "runs": measured["batched_matrix_stack"],
        },
        "comparison": {
            "p50_speedup": p50_speedup,
            "mean_speedup": mean_speedup,
            "semantic_equivalence": equivalence,
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
        },
    }


def render_non_radar_innovation_benchmark_cn(report: dict[str, Any]) -> str:
    """Render a concise Chinese report from one benchmark artifact."""

    source = report["input"]
    protocol = report["protocol"]
    scalar = report["scalar_per_candidate"]["timing"]
    batched = report["batched_matrix_stack"]["timing"]
    comparison = report["comparison"]
    machine = report["machine"]
    equivalence = comparison["semantic_equivalence"]
    semantic_status = "通过" if all(equivalence.values()) else "未通过"
    return "\n".join(
        [
            "# D1 非雷达创新批处理性能基准",
            "",
            "## 结论",
            "",
            (
                f"逐候选路径 P50 为 `{scalar['p50_s']:.3f} s`，批处理路径 "
                f"P50 为 `{batched['p50_s']:.3f} s`，加速 "
                f"`{comparison['p50_speedup']:.3f}x`。规范输出等价验收："
                f"`{semantic_status}`。"
            ),
            "",
            "## 输入与口径",
            "",
            f"- 源文件：`{source['source_path']}`",
            f"- SHA-256：`{source['source_sha256']}`",
            (
                f"- 选取扫描/观测：{source['selected_scan_count']} / "
                f"{source['selected_observation_count']}"
            ),
            (
                f"- 同进程预热：每个变体 {protocol['warmup_count_per_variant']} 次，"
                f"每次 {protocol['warmup_scan_count']} 个扫描"
            ),
            (
                f"- 正式重复：每个变体 {protocol['repeat_count_per_variant']} 次，"
                "交错执行"
            ),
            (
                f"- 机器：{machine['cpu_model']}，逻辑处理器 "
                f"{machine['logical_cpu_count']}，Python {machine['python_version']}，"
                f"NumPy {machine['numpy_version']}"
            ),
            "",
            "## 墙钟统计",
            "",
            "| 路径 | 均值 / s | P50 / s | P95 / s | 最小 / s | 最大 / s |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            (
                f"| 逐候选伪逆 | {scalar['mean_s']:.3f} | "
                f"{scalar['p50_s']:.3f} | {scalar['p95_s']:.3f} | "
                f"{scalar['minimum_s']:.3f} | {scalar['maximum_s']:.3f} |"
            ),
            (
                f"| 矩阵栈批处理 | {batched['mean_s']:.3f} | "
                f"{batched['p50_s']:.3f} | {batched['p95_s']:.3f} | "
                f"{batched['minimum_s']:.3f} | {batched['maximum_s']:.3f} |"
            ),
            "",
            "## 等价性",
            "",
            *[
                f"- {'通过' if value else '未通过'}：`{key}`"
                for key, value in equivalence.items()
            ],
            "",
            "## 边界",
            "",
            (
                "本基准只证明冻结输入上的 D1 模块性能和规范输出等价性。"
                "它不代表完整 D1-D7 闭环实时倍率，也不代表 AirSim 或实装传感器性能。"
            ),
            "",
        ]
    )


def _run_variant(
    release_groups: Sequence[Sequence[SensorScanFrame]],
    *,
    batched: bool,
    variant: str,
) -> dict[str, Any]:
    return run_coalesced_release_schedule_variant(
        release_groups,
        variant=variant,
        adapter_options={
            "batched_non_radar_innovation_solve": bool(batched),
        },
    )


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant": result["variant"],
        "process_wall_time_s": float(result["process_wall_time_s"]),
        **{field: result[field] for field in _SEMANTIC_FIELDS},
    }


def _release_group_prefix(
    release_groups: Sequence[Sequence[SensorScanFrame]],
    maximum_scan_count: int | None,
) -> tuple[tuple[SensorScanFrame, ...], ...]:
    if maximum_scan_count is None:
        return tuple(tuple(group) for group in release_groups)
    if maximum_scan_count < 1:
        raise ValueError("maximum_scan_count must be positive")
    selected: list[tuple[SensorScanFrame, ...]] = []
    remaining = int(maximum_scan_count)
    for group in release_groups:
        if remaining <= 0:
            break
        items = tuple(group[:remaining])
        if items:
            selected.append(items)
            remaining -= len(items)
    return tuple(selected)


def _timing_statistics(values: Sequence[float]) -> dict[str, Any]:
    samples = tuple(float(value) for value in values)
    return {
        "samples_s": samples,
        "mean_s": fmean(samples),
        "p50_s": median(samples),
        "p95_s": float(np.percentile(samples, 95)),
        "minimum_s": min(samples),
        "maximum_s": max(samples),
    }


def _machine_summary() -> dict[str, Any]:
    cpu_model = platform.processor().strip()
    cpuinfo = Path("/proc/cpuinfo")
    if (
        not cpu_model
        or cpu_model.lower() in {"x86_64", "amd64", "aarch64", "arm64"}
    ) and cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name"):
                cpu_model = line.split(":", 1)[-1].strip()
                break
    return {
        "platform": platform.platform(),
        "cpu_model": cpu_model or "unknown",
        "logical_cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
    }
