from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

import numpy as np

from .ekf import EKFState
from .fusion import FusionAdapter


CV_MOTION_MODEL_CACHE_PERFORMANCE_SCHEMA_VERSION = (
    "d1.cv_motion_model_cache_performance.v1"
)


def run_cv_motion_model_cache_variant(
    *,
    cached_cv_motion_model: bool,
    state_count: int = 200,
    step_count: int = 100,
    dt_s: float = 0.05,
    cache_capacity: int = 128,
) -> dict[str, Any]:
    """Measure repeated CV propagation without other fusion-stage work."""

    if state_count < 1 or step_count < 1:
        raise ValueError("state_count and step_count must be positive")
    if not np.isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError("dt_s must be finite and positive")
    adapter = FusionAdapter(
        process_noise=6.0,
        cached_cv_motion_model=cached_cv_motion_model,
        cv_motion_model_cache_capacity=cache_capacity,
    )
    states = [
        EKFState(
            state=np.array(
                [
                    100.0 + 2.0 * index,
                    -250.0 + 1.5 * index,
                    -80.0 - 0.2 * index,
                    3.0 + 0.01 * index,
                    -1.0 + 0.005 * index,
                    0.1,
                ],
                dtype=float,
            ),
            covariance=np.diag(
                [
                    9.0 + 0.01 * index,
                    10.0 + 0.01 * index,
                    12.0 + 0.01 * index,
                    2.0,
                    2.5,
                    3.0,
                ]
            ),
            timestamp=0.0,
        )
        for index in range(state_count)
    ]

    started = perf_counter()
    for step_index in range(1, step_count + 1):
        timestamp = float(step_index) * float(dt_s)
        states = [
            adapter._predict_to(state, timestamp)
            for state in states
        ]
    wall_time_s = perf_counter() - started
    return {
        "candidate_enabled": bool(cached_cv_motion_model),
        "state_count": int(state_count),
        "step_count": int(step_count),
        "prediction_count": int(state_count * step_count),
        "dt_s": float(dt_s),
        "wall_time_s": float(wall_time_s),
        "final_state_sha256": _state_digest(states),
        "diagnostics": adapter.cv_motion_model_cache_diagnostics(),
    }


def compare_cv_motion_model_cache_variants(
    *,
    repetitions: int = 7,
    state_count: int = 200,
    step_count: int = 100,
    dt_s: float = 0.05,
    cache_capacity: int = 128,
) -> dict[str, Any]:
    """Run alternating reference/candidate samples and compare exact outputs."""

    if repetitions < 1:
        raise ValueError("repetitions must be positive")
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
                run_cv_motion_model_cache_variant(
                    cached_cv_motion_model=enabled,
                    state_count=state_count,
                    step_count=step_count,
                    dt_s=dt_s,
                    cache_capacity=cache_capacity,
                )
            )

    reference = _summarize_samples(samples["reference"])
    candidate = _summarize_samples(samples["candidate"])
    reference_digests = {
        item["final_state_sha256"] for item in samples["reference"]
    }
    candidate_digests = {
        item["final_state_sha256"] for item in samples["candidate"]
    }
    reference_operations = {
        json.dumps(
            item["diagnostics"]["operation_counts"],
            sort_keys=True,
        )
        for item in samples["reference"]
    }
    candidate_operations = {
        json.dumps(
            item["diagnostics"]["operation_counts"],
            sort_keys=True,
        )
        for item in samples["candidate"]
    }
    reference_builds = int(
        samples["reference"][0]["diagnostics"]["operation_counts"][
            "model_build_count"
        ]
    )
    candidate_builds = int(
        samples["candidate"][0]["diagnostics"]["operation_counts"][
            "model_build_count"
        ]
    )
    build_reduction = (
        1.0 - candidate_builds / reference_builds
        if reference_builds > 0
        else 0.0
    )
    acceptance = {
        "exact_final_state_equivalence": (
            len(reference_digests) == 1
            and reference_digests == candidate_digests
        ),
        "reference_operation_counts_deterministic": (
            len(reference_operations) == 1
        ),
        "candidate_operation_counts_deterministic": (
            len(candidate_operations) == 1
        ),
        "candidate_cache_is_bounded": (
            int(
                samples["candidate"][0]["diagnostics"][
                    "cache_entry_count"
                ]
            )
            <= cache_capacity
        ),
        "model_build_reduction_at_least_90_percent": (
            build_reduction >= 0.90
        ),
    }
    return {
        "schema_version": (
            CV_MOTION_MODEL_CACHE_PERFORMANCE_SCHEMA_VERSION
        ),
        "benchmark_scope": (
            "D1 CV state propagation hotspot only; not a full-stack gate"
        ),
        "configuration": {
            "repetitions": int(repetitions),
            "state_count": int(state_count),
            "step_count": int(step_count),
            "dt_s": float(dt_s),
            "cache_capacity": int(cache_capacity),
        },
        "reference": reference,
        "candidate": candidate,
        "comparison": {
            "median_speedup": (
                reference["median_wall_time_s"]
                / candidate["median_wall_time_s"]
                if candidate["median_wall_time_s"] > 0.0
                else None
            ),
            "reference_model_build_count": reference_builds,
            "candidate_model_build_count": candidate_builds,
            "model_build_reduction_fraction": build_reduction,
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
        },
    }


def write_cv_motion_model_cache_performance_report(
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
    comparison = report["comparison"]
    reference = report["reference"]
    candidate = report["candidate"]
    markdown_destination.write_text(
        "\n".join(
            (
                "# D1 匀速模型矩阵复用专项基准",
                "",
                "## 结论",
                "",
                (
                    "该基准只测量 D1 匀速状态传播热点，不代表融合全流程或"
                    "系统实时准入。"
                ),
                (
                    f"- reference 中位耗时："
                    f"`{reference['median_wall_time_s']:.6f} s`"
                ),
                (
                    f"- candidate 中位耗时："
                    f"`{candidate['median_wall_time_s']:.6f} s`"
                ),
                (
                    f"- 中位加速比："
                    f"`{comparison['median_speedup']:.3f}`"
                ),
                (
                    f"- 模型矩阵构造次数："
                    f"`{comparison['reference_model_build_count']}` -> "
                    f"`{comparison['candidate_model_build_count']}`"
                ),
                (
                    f"- 精确状态等价："
                    f"`{comparison['acceptance']['exact_final_state_equivalence']}`"
                ),
                (
                    f"- 专项检查通过：`{comparison['passed']}`"
                ),
                "",
                "## 边界",
                "",
                (
                    "候选只缓存由精确时间差和过程噪声共同确定的只读矩阵。"
                    "每条航迹仍独立传播状态和协方差。"
                ),
                (
                    "是否进入主线仍需 main 在同一干净提交上完成多随机种子"
                    " reference/candidate 矩阵。"
                ),
                "",
            )
        ),
        encoding="utf-8",
    )


def _summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    times = [float(item["wall_time_s"]) for item in samples]
    return {
        "sample_count": len(samples),
        "wall_time_samples_s": times,
        "median_wall_time_s": float(median(times)),
        "minimum_wall_time_s": float(min(times)),
        "maximum_wall_time_s": float(max(times)),
        "final_state_sha256": samples[0]["final_state_sha256"],
        "diagnostics": samples[0]["diagnostics"],
    }


def _state_digest(states: list[EKFState]) -> str:
    digest = hashlib.sha256()
    for state in states:
        digest.update(np.ascontiguousarray(state.state).tobytes())
        digest.update(np.ascontiguousarray(state.covariance).tobytes())
        digest.update(np.asarray([state.timestamp], dtype=np.float64).tobytes())
    return digest.hexdigest()
