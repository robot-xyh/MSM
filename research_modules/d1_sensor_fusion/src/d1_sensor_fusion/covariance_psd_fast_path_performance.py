from __future__ import annotations

import cProfile
import hashlib
import json
from pathlib import Path
import pstats
from statistics import median
from time import perf_counter
from typing import Any

import numpy as np

from .fusion import FusionAdapter


COVARIANCE_PSD_FAST_PATH_PERFORMANCE_SCHEMA_VERSION = (
    "d1.covariance_psd_fast_path_performance.v2"
)
_PROFILE_FUNCTIONS = (
    "_limit_state_covariance",
    "_limit_covariance_diagonal",
    "_project_bounded_covariance_to_psd",
    "_bounded_covariance_constraints_satisfied",
    "cholesky",
    "eigvalsh",
    "eigh",
)
MINIMUM_MEDIAN_IMPROVEMENT_FRACTION = 0.02
MINIMUM_PAIRED_FASTER_FRACTION = 0.70


def compare_covariance_psd_fast_path_variants(
    *,
    repetitions: int = 9,
    warmup_count: int = 2,
    matrix_count: int = 2_000,
    round_count: int = 10,
    fallback_every: int = 100,
    seed: int = 20260724,
) -> dict[str, Any]:
    """Compare the exact 6x6 PSD-check paths on deterministic D1 work."""

    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    if warmup_count < 0:
        raise ValueError("warmup_count must be non-negative")
    if round_count < 1:
        raise ValueError("round_count must be positive")
    workload, workload_metadata = _synthetic_covariance_workload(
        matrix_count=matrix_count,
        fallback_every=fallback_every,
        seed=seed,
    )

    for _ in range(warmup_count):
        _run_variant(
            workload,
            candidate_enabled=False,
            round_count=round_count,
        )
        _run_variant(
            workload,
            candidate_enabled=True,
            round_count=round_count,
        )

    samples: dict[str, list[dict[str, Any]]] = {
        "reference": [],
        "candidate": [],
    }
    for repetition in range(repetitions):
        order = (
            (("reference", False), ("candidate", True))
            if repetition % 2 == 0
            else (("candidate", True), ("reference", False))
        )
        for name, enabled in order:
            samples[name].append(
                _run_variant(
                    workload,
                    candidate_enabled=enabled,
                    round_count=round_count,
                )
            )

    reference_profile = _profile_variant(
        workload,
        candidate_enabled=False,
        round_count=round_count,
    )
    candidate_profile = _profile_variant(
        workload,
        candidate_enabled=True,
        round_count=round_count,
    )
    reference = _summarize_samples(samples["reference"], reference_profile)
    candidate = _summarize_samples(samples["candidate"], candidate_profile)

    reference_digests = {
        item["output_sha256"] for item in samples["reference"]
    }
    candidate_digests = {
        item["output_sha256"] for item in samples["candidate"]
    }
    reference_reason_digests = {
        item["reason_sha256"] for item in samples["reference"]
    }
    candidate_reason_digests = {
        item["reason_sha256"] for item in samples["candidate"]
    }
    candidate_diagnostic_snapshots = {
        json.dumps(
            item["diagnostics"],
            sort_keys=True,
            separators=(",", ":"),
        )
        for item in samples["candidate"]
    }
    candidate_counts = candidate["diagnostics"]["operation_counts"]
    attempt_count = int(candidate_counts["cholesky_attempt_count"])
    success_count = int(candidate_counts["cholesky_success_count"])
    fallback_count = int(candidate_counts["cholesky_fallback_count"])
    paired_faster_count = sum(
        float(candidate_sample["wall_time_s"])
        < float(reference_sample["wall_time_s"])
        for reference_sample, candidate_sample in zip(
            samples["reference"],
            samples["candidate"],
            strict=True,
        )
    )
    median_improvement_fraction = (
        1.0
        - candidate["median_wall_time_s"]
        / reference["median_wall_time_s"]
    )
    semantic_acceptance = {
        "exact_covariance_output": (
            len(reference_digests) == 1
            and reference_digests == candidate_digests
        ),
        "exact_reason_output": (
            len(reference_reason_digests) == 1
            and reference_reason_digests == candidate_reason_digests
        ),
        "finite_symmetric_output": (
            reference["finite_symmetric_output"]
            and candidate["finite_symmetric_output"]
        ),
        "candidate_diagnostics_deterministic": (
            len(candidate_diagnostic_snapshots) == 1
        ),
        "candidate_attempt_conservation": (
            attempt_count == success_count + fallback_count
        ),
        "candidate_exercises_success_and_fallback": (
            success_count > 0 and fallback_count > 0
        ),
        "reference_candidate_disabled": (
            reference["diagnostics"]["candidate_enabled"] is False
        ),
    }
    minimum_paired_faster_count = max(
        1,
        int(np.ceil(MINIMUM_PAIRED_FASTER_FRACTION * repetitions)),
    )
    stable_wall_clock_gain = (
        median_improvement_fraction
        >= MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
        and paired_faster_count >= minimum_paired_faster_count
    )
    recommendation = (
        "candidate_worth_main_clean_multiseed_evaluation"
        if all(semantic_acceptance.values()) and stable_wall_clock_gain
        else "retain_candidate_not_recommended_for_main"
    )
    return {
        "schema_version": (
            COVARIANCE_PSD_FAST_PATH_PERFORMANCE_SCHEMA_VERSION
        ),
        "benchmark_scope": (
            "D1 synthetic 6x6 covariance limiter only; not full fusion, "
            "AirSim, hardware, or full-stack admission evidence"
        ),
        "configuration": {
            "repetitions": int(repetitions),
            "warmup_count": int(warmup_count),
            "matrix_count": int(matrix_count),
            "round_count": int(round_count),
            "fallback_every": int(fallback_every),
            "seed": int(seed),
        },
        "recommendation_policy": {
            "minimum_median_improvement_fraction": (
                MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
            ),
            "minimum_paired_faster_fraction": (
                MINIMUM_PAIRED_FASTER_FRACTION
            ),
            "minimum_paired_faster_count": (
                minimum_paired_faster_count
            ),
            "scope": (
                "D1 module candidate recommendation only; main admission "
                "requires an independent clean multiseed evaluation"
            ),
        },
        "input": workload_metadata,
        "reference": reference,
        "candidate": candidate,
        "comparison": {
            "median_speedup": (
                reference["median_wall_time_s"]
                / candidate["median_wall_time_s"]
            ),
            "median_improvement_fraction": (
                median_improvement_fraction
            ),
            "paired_candidate_faster_count": int(paired_faster_count),
            "paired_sample_count": int(repetitions),
            "semantic_acceptance": semantic_acceptance,
            "semantic_passed": all(semantic_acceptance.values()),
            "stable_wall_clock_gain": bool(stable_wall_clock_gain),
            "integration_recommendation": recommendation,
        },
    }


def write_covariance_psd_fast_path_performance_report(
    report: dict[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_destination = Path(json_path)
    markdown_destination = Path(markdown_path)
    json_destination.parent.mkdir(parents=True, exist_ok=True)
    markdown_destination.parent.mkdir(parents=True, exist_ok=True)
    json_destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )

    reference = report["reference"]
    candidate = report["candidate"]
    comparison = report["comparison"]
    reference_profile = reference["profile"]["selected_functions"]
    candidate_profile = candidate["profile"]["selected_functions"]
    profile_rows = []
    for name in _PROFILE_FUNCTIONS:
        reference_item = reference_profile.get(name, {})
        candidate_item = candidate_profile.get(name, {})
        profile_rows.append(
            "| `{}` | {} | {:.6f} | {} | {:.6f} |".format(
                name,
                int(reference_item.get("primitive_call_count", 0)),
                float(reference_item.get("cumulative_time_s", 0.0)),
                int(candidate_item.get("primitive_call_count", 0)),
                float(candidate_item.get("cumulative_time_s", 0.0)),
            )
        )
    recommendation_cn = (
        "建议由 main 在干净提交上开展完整融合多随机种子评估。"
        if comparison["stable_wall_clock_gain"]
        else "保留显式候选，不建议接入 main 默认路径。"
    )
    markdown_destination.write_text(
        "\n".join(
            (
                "# D1 协方差 PSD 检查快路径专项基准",
                "",
                "## 结论",
                "",
                (
                    "该基准使用确定种子的六维协方差合成负载，只评价"
                    " D1 协方差限幅热点。"
                ),
                (
                    f"- 参考路径中位耗时："
                    f"`{reference['median_wall_time_s']:.6f} s`"
                ),
                (
                    f"- 候选路径中位耗时："
                    f"`{candidate['median_wall_time_s']:.6f} s`"
                ),
                (
                    f"- 中位改善："
                    f"`{100.0 * comparison['median_improvement_fraction']:.2f}%`"
                ),
                (
                    f"- 配对更快样本："
                    f"`{comparison['paired_candidate_faster_count']}/"
                    f"{comparison['paired_sample_count']}`"
                ),
                (
                    "- 建议门槛：中位改善至少 "
                    f"`{100.0 * report['recommendation_policy']['minimum_median_improvement_fraction']:.2f}%`，"
                    "且更快样本比例至少 "
                    f"`{100.0 * report['recommendation_policy']['minimum_paired_faster_fraction']:.0f}%`"
                ),
                (
                    f"- 数学输出与原因严格一致："
                    f"`{comparison['semantic_passed']}`"
                ),
                (
                    f"- Cholesky 操作数：attempt="
                    f"`{candidate['diagnostics']['operation_counts']['cholesky_attempt_count']}`，"
                    f"success="
                    f"`{candidate['diagnostics']['operation_counts']['cholesky_success_count']}`，"
                    f"fallback="
                    f"`{candidate['diagnostics']['operation_counts']['cholesky_fallback_count']}`"
                ),
                (
                    "- 候选实现 ID："
                    f"`{candidate['diagnostics']['implementation_id']}`"
                ),
                (
                    "- 归一化行列式安全门限："
                    f"`{candidate['diagnostics']['relative_determinant_floor']:.17g}`"
                ),
                f"- 处置：{recommendation_cn}",
                "",
                "## 输入",
                "",
                (
                    f"- 输入哈希：`{report['input']['sha256']}`"
                ),
                (
                    f"- 矩阵数：`{report['configuration']['matrix_count']}`；"
                    f"轮数：`{report['configuration']['round_count']}`；"
                    f"确定种子：`{report['configuration']['seed']}`"
                ),
                (
                    f"- 合成不定矩阵数："
                    f"`{report['input']['indefinite_matrix_count']}`"
                ),
                "",
                "## cProfile",
                "",
                "| 函数 | 参考调用 | 参考累计秒 | 候选调用 | 候选累计秒 |",
                "|---|---:|---:|---:|---:|",
                *profile_rows,
                "",
                "## 边界",
                "",
                (
                    "候选只在有限 6×6 矩阵上先做 Cholesky，并要求归一化"
                    "行列式通过机器精度安全门。任一步失败后仍执行原有"
                    " eigvalsh 与投影，未改变投影公式或对角回退。"
                ),
                (
                    "本报告不是完整融合、200v200、AirSim、目标硬件或"
                    "系统实时准入证据。"
                ),
                "",
            )
        ),
        encoding="utf-8",
    )


def _synthetic_covariance_workload(
    *,
    matrix_count: int,
    fallback_every: int,
    seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    if matrix_count < 2:
        raise ValueError("matrix_count must be at least 2")
    if fallback_every < 2:
        raise ValueError("fallback_every must be at least 2")
    generator = np.random.default_rng(seed)
    workload = np.empty((matrix_count, 6, 6), dtype=float)
    indefinite_count = 0
    for index in range(matrix_count):
        if (index + 1) % fallback_every == 0:
            covariance = np.eye(6, dtype=float)
            covariance[:3, :3] = np.array(
                [
                    [1.0, 0.9, 0.9],
                    [0.9, 1.0, -0.9],
                    [0.9, -0.9, 1.0],
                ],
                dtype=float,
            )
            indefinite_count += 1
        else:
            factor = generator.normal(scale=0.2, size=(6, 3))
            covariance = factor @ factor.T
            covariance += np.diag(
                generator.uniform(0.5, 20.0, size=6)
            )
        workload[index] = covariance
    workload.setflags(write=False)
    return workload, {
        "kind": "deterministic_synthetic_6x6_covariance_workload",
        "sha256": hashlib.sha256(
            np.ascontiguousarray(workload).tobytes()
        ).hexdigest(),
        "indefinite_matrix_count": int(indefinite_count),
        "positive_definite_matrix_count": int(
            matrix_count - indefinite_count
        ),
        "online_truth_use_count": 0,
    }


def _run_variant(
    workload: np.ndarray,
    *,
    candidate_enabled: bool,
    round_count: int,
) -> dict[str, Any]:
    adapter = FusionAdapter(
        vectorized_covariance_limit=True,
        cholesky_covariance_psd_fast_path=candidate_enabled,
    )
    outputs = np.empty_like(workload)
    reason_digest = hashlib.sha256()
    started = perf_counter()
    for _ in range(round_count):
        for index, covariance in enumerate(workload):
            output, reasons = adapter._limit_state_covariance(covariance)
            outputs[index] = output
            for reason in reasons:
                reason_digest.update(reason.encode("utf-8"))
                reason_digest.update(b"\0")
    wall_time_s = perf_counter() - started
    return {
        "wall_time_s": float(wall_time_s),
        "output_sha256": hashlib.sha256(
            np.ascontiguousarray(outputs).tobytes()
        ).hexdigest(),
        "reason_sha256": reason_digest.hexdigest(),
        "finite_symmetric_output": bool(
            np.isfinite(outputs).all()
            and np.array_equal(outputs, outputs.transpose(0, 2, 1))
        ),
        "diagnostics": adapter.covariance_psd_check_diagnostics(),
    }


def _profile_variant(
    workload: np.ndarray,
    *,
    candidate_enabled: bool,
    round_count: int,
) -> dict[str, Any]:
    profiler = cProfile.Profile()
    profiler.enable()
    result = _run_variant(
        workload,
        candidate_enabled=candidate_enabled,
        round_count=round_count,
    )
    profiler.disable()
    stats = pstats.Stats(profiler)
    selected: dict[str, dict[str, float | int]] = {}
    for (_, _, function_name), values in stats.stats.items():
        if function_name not in _PROFILE_FUNCTIONS:
            continue
        primitive_calls, total_calls, total_time, cumulative_time, _ = values
        item = selected.setdefault(
            function_name,
            {
                "primitive_call_count": 0,
                "total_call_count": 0,
                "total_time_s": 0.0,
                "cumulative_time_s": 0.0,
            },
        )
        item["primitive_call_count"] += int(primitive_calls)
        item["total_call_count"] += int(total_calls)
        item["total_time_s"] += float(total_time)
        item["cumulative_time_s"] += float(cumulative_time)
    return {
        "profiled_operation_count": int(
            workload.shape[0] * round_count
        ),
        "profiled_wall_time_s": float(result["wall_time_s"]),
        "selected_functions": selected,
    }


def _summarize_samples(
    samples: list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    times = [float(item["wall_time_s"]) for item in samples]
    return {
        "sample_count": len(samples),
        "wall_time_samples_s": times,
        "median_wall_time_s": float(median(times)),
        "minimum_wall_time_s": float(min(times)),
        "maximum_wall_time_s": float(max(times)),
        "output_sha256": samples[0]["output_sha256"],
        "reason_sha256": samples[0]["reason_sha256"],
        "finite_symmetric_output": bool(
            all(item["finite_symmetric_output"] for item in samples)
        ),
        "diagnostics": samples[0]["diagnostics"],
        "profile": profile,
    }
