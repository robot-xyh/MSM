from __future__ import annotations

import cProfile
from collections import Counter
import hashlib
import json
from pathlib import Path
import pstats
from statistics import median
from time import perf_counter
from typing import Any

import numpy as np

from .fusion import (
    STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION_ID,
    STRUCTURED_NUMERICAL_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION,
    STRUCTURED_NUMERICAL_JACOBIAN_REFERENCE_IMPLEMENTATION_ID,
)
from .motion import wrap_residual
from .observations import (
    CameraModel,
    acoustic_3d_h,
    acoustic_h,
    eo_project,
    measurement_model_for,
    radar_h,
)
from .types import SensorObservation


STRUCTURED_NUMERICAL_JACOBIAN_PERFORMANCE_SCHEMA_VERSION = (
    "d1.structured_numerical_jacobian_performance.v1"
)
STRUCTURED_NUMERICAL_JACOBIAN_BENCHMARK_CONFIG_SCHEMA_VERSION = (
    "d1.structured_numerical_jacobian_benchmark_config.v1"
)
DEFAULT_BENCHMARK_CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "structured_numerical_jacobian_benchmark_v1.json"
)
MINIMUM_MEDIAN_IMPROVEMENT_FRACTION = 0.10
MINIMUM_PAIRED_FASTER_FRACTION = 0.80
_PROFILE_FUNCTIONS = (
    "numerical_jacobian",
    "structured_numerical_jacobian",
    "radar_h",
    "acoustic_h",
    "acoustic_3d_h",
    "eo_project",
)


def compare_structured_numerical_jacobian_variants(
    config_path: str | Path = DEFAULT_BENCHMARK_CONFIG_PATH,
    *,
    repetitions: int | None = None,
    warmup_count: int | None = None,
    sample_count: int | None = None,
    round_count: int | None = None,
) -> dict[str, Any]:
    """Run an interleaved deterministic benchmark for the D1 candidate."""

    config, config_sha256 = _load_config(config_path)
    repetitions = _positive_override(
        repetitions,
        int(config["repetitions"]),
        "repetitions",
    )
    warmup_count = _non_negative_override(
        warmup_count,
        int(config["warmup_count"]),
        "warmup_count",
    )
    sample_count = _positive_override(
        sample_count,
        int(config["sample_count"]),
        "sample_count",
    )
    round_count = _positive_override(
        round_count,
        int(config["round_count"]),
        "round_count",
    )
    workload, workload_metadata = _build_workload(
        config,
        sample_count=sample_count,
    )
    association_gate = float(config["association_gate"])

    for _ in range(warmup_count):
        _run_variant(
            workload,
            candidate_enabled=False,
            round_count=round_count,
            association_gate=association_gate,
        )
        _run_variant(
            workload,
            candidate_enabled=True,
            round_count=round_count,
            association_gate=association_gate,
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
        for name, candidate_enabled in order:
            samples[name].append(
                _run_variant(
                    workload,
                    candidate_enabled=candidate_enabled,
                    round_count=round_count,
                    association_gate=association_gate,
                )
            )

    reference = _summarize(
        samples["reference"],
        _profile_variant(
            workload,
            candidate_enabled=False,
            round_count=round_count,
            association_gate=association_gate,
        ),
    )
    candidate = _summarize(
        samples["candidate"],
        _profile_variant(
            workload,
            candidate_enabled=True,
            round_count=round_count,
            association_gate=association_gate,
        ),
    )
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
    minimum_paired_faster_count = max(
        1,
        int(np.ceil(MINIMUM_PAIRED_FASTER_FRACTION * repetitions)),
    )
    reference_counts = reference["diagnostics"]["operation_counts"]
    candidate_counts = candidate["diagnostics"]["operation_counts"]
    semantic_acceptance = {
        "exact_jacobian_output": (
            reference["jacobian_sha256"] == candidate["jacobian_sha256"]
        ),
        "exact_nis_output": (
            reference["nis_sha256"] == candidate["nis_sha256"]
        ),
        "exact_gate_decisions": (
            reference["gate_decision_sha256"]
            == candidate["gate_decision_sha256"]
        ),
        "finite_output": (
            reference["finite_output"] and candidate["finite_output"]
        ),
        "reference_uses_output_probe": (
            int(reference_counts["output_probe_evaluation_count"]) > 0
            and int(reference_counts.get("output_probe_elision_count", 0)) == 0
        ),
        "candidate_elides_output_probe": (
            int(candidate_counts["output_probe_elision_count"]) > 0
            and int(candidate_counts.get("output_probe_evaluation_count", 0)) == 0
        ),
        "candidate_elides_inactive_columns": (
            int(candidate_counts["inactive_state_column_elision_count"]) > 0
        ),
        "operation_conservation": (
            reference["diagnostics"]["conservation"][
                "attempt_equals_success_plus_failure"
            ]
            and reference["diagnostics"]["conservation"][
                "attempt_equals_reference_plus_candidate"
            ]
            and candidate["diagnostics"]["conservation"][
                "attempt_equals_success_plus_failure"
            ]
            and candidate["diagnostics"]["conservation"][
                "attempt_equals_reference_plus_candidate"
            ]
        ),
        "online_truth_use_count_zero": (
            workload_metadata["online_truth_use_count"] == 0
        ),
    }
    stable_wall_clock_gain = (
        median_improvement_fraction
        >= MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
        and paired_faster_count >= minimum_paired_faster_count
    )
    semantic_passed = all(semantic_acceptance.values())
    recommendation = (
        "candidate_pending_main_full_stack_admission"
        if semantic_passed and stable_wall_clock_gain
        else "retain_candidate_not_recommended_for_main"
    )
    return {
        "schema_version": (
            STRUCTURED_NUMERICAL_JACOBIAN_PERFORMANCE_SCHEMA_VERSION
        ),
        "benchmark_scope": (
            "D1 measurement-model numerical Jacobian only; not full fusion, "
            "AirSim, hardware, or full-stack admission evidence"
        ),
        "configuration": {
            "config_path": str(Path(config_path)),
            "config_sha256": config_sha256,
            "repetitions": repetitions,
            "warmup_count": warmup_count,
            "sample_count": sample_count,
            "round_count": round_count,
            "seed": int(config["seed"]),
            "association_gate": association_gate,
            "modality_cycle": list(config["modality_cycle"]),
        },
        "recommendation_policy": {
            "minimum_median_improvement_fraction": (
                MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
            ),
            "minimum_paired_faster_fraction": (
                MINIMUM_PAIRED_FASTER_FRACTION
            ),
            "minimum_paired_faster_count": minimum_paired_faster_count,
            "scope": (
                "D1 module recommendation only; main admission requires a "
                "clean full-stack paired multiseed evaluation"
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
            "median_improvement_fraction": median_improvement_fraction,
            "paired_candidate_faster_count": int(paired_faster_count),
            "paired_sample_count": int(repetitions),
            "measurement_function_evaluation_reduction_fraction": (
                1.0
                - int(candidate_counts["measurement_function_evaluation_count"])
                / int(reference_counts["measurement_function_evaluation_count"])
            ),
            "semantic_acceptance": semantic_acceptance,
            "semantic_passed": semantic_passed,
            "stable_wall_clock_gain": bool(stable_wall_clock_gain),
            "integration_recommendation": recommendation,
        },
    }


def write_structured_numerical_jacobian_performance_report(
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
    candidate_counts = candidate["diagnostics"]["operation_counts"]
    profile_rows: list[str] = []
    for name in _PROFILE_FUNCTIONS:
        reference_item = reference["profile"]["selected_functions"].get(name, {})
        candidate_item = candidate["profile"]["selected_functions"].get(name, {})
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
        "模块内候选保留为待 main 全栈准入，D1 独立默认值保持关闭。"
        if comparison["integration_recommendation"]
        == "candidate_pending_main_full_stack_admission"
        else "候选保留为研究对照，不建议 main 接线。"
    )
    markdown_destination.write_text(
        "\n".join(
            (
                "# D1 结构稀疏数值雅可比专项基准",
                "",
                "## 结论",
                "",
                (
                    "冻结微基准覆盖雷达、声学、光电和激光雷达量测模型。"
                    "候选只跳过已知输出维数探测和观测方程不依赖的状态列。"
                ),
                (
                    f"- 参考中位耗时："
                    f"`{reference['median_wall_time_s']:.6f} s`"
                ),
                (
                    f"- 候选中位耗时："
                    f"`{candidate['median_wall_time_s']:.6f} s`"
                ),
                (
                    f"- 中位改善："
                    f"`{100.0 * comparison['median_improvement_fraction']:.2f}%`"
                ),
                (
                    f"- 配对更快："
                    f"`{comparison['paired_candidate_faster_count']}/"
                    f"{comparison['paired_sample_count']}`"
                ),
                (
                    "- 量测函数求值减少："
                    f"`{100.0 * comparison['measurement_function_evaluation_reduction_fraction']:.2f}%`"
                ),
                (
                    "- 雅可比、归一化创新平方和门控决策逐字节一致："
                    f"`{comparison['semantic_passed']}`"
                ),
                (
                    "- 候选操作数：output probe elision="
                    f"`{candidate_counts['output_probe_elision_count']}`，"
                    "inactive column elision="
                    f"`{candidate_counts['inactive_state_column_elision_count']}`"
                ),
                (
                    "- 候选实现 ID："
                    f"`{candidate['diagnostics']['implementation_id']}`"
                ),
                f"- 处置：{recommendation_cn}",
                "",
                "## 冻结输入",
                "",
                (
                    f"- 配置 SHA-256："
                    f"`{report['configuration']['config_sha256']}`"
                ),
                (
                    f"- 工作负载 SHA-256：`{report['input']['sha256']}`"
                ),
                (
                    f"- 样本数：`{report['configuration']['sample_count']}`；"
                    f"每样本轮数：`{report['configuration']['round_count']}`；"
                    f"确定种子：`{report['configuration']['seed']}`"
                ),
                "",
                "## 算法边界",
                "",
                (
                    "活动列仍按参考实现执行相同的中心差分、步长和数组运算。"
                    "候选不使用解析近似，不缓存跨时刻状态，也不改变创新协方差、"
                    "门限或匈牙利分配。"
                ),
                (
                    "雷达含径向速度时保留全部六个活动列。声学、光电、"
                    "激光雷达和无径向速度雷达只依赖位置三列，速度列直接写精确零。"
                ),
                "",
                "## cProfile",
                "",
                "| 函数 | 参考调用 | 参考累计秒 | 候选调用 | 候选累计秒 |",
                "|---|---:|---:|---:|---:|",
                *profile_rows,
                "",
                "## 证据限制",
                "",
                (
                    "本报告只评价 D1 数值雅可比热点。它不是完整融合、"
                    "200v200、AirSim、目标硬件或系统实时准入证据。"
                ),
                "",
            )
        ),
        encoding="utf-8",
    )


def _load_config(path: str | Path) -> tuple[dict[str, Any], str]:
    source = Path(path)
    payload = source.read_bytes()
    config = json.loads(payload.decode("utf-8"))
    if (
        config.get("schema_version")
        != STRUCTURED_NUMERICAL_JACOBIAN_BENCHMARK_CONFIG_SCHEMA_VERSION
    ):
        raise ValueError("unsupported structured Jacobian benchmark config")
    modality_cycle = config.get("modality_cycle")
    if not isinstance(modality_cycle, list) or not modality_cycle:
        raise ValueError("modality_cycle must be a non-empty list")
    supported = {
        "radar_full",
        "radar_position_only",
        "acoustic",
        "acoustic_3d",
        "eo",
        "lidar",
    }
    if any(str(item) not in supported for item in modality_cycle):
        raise ValueError("modality_cycle contains an unsupported modality")
    return config, hashlib.sha256(payload).hexdigest()


def _build_workload(
    config: dict[str, Any],
    *,
    sample_count: int,
) -> tuple[list[tuple[np.ndarray, SensorObservation]], dict[str, Any]]:
    generator = np.random.default_rng(int(config["seed"]))
    modalities = [str(item) for item in config["modality_cycle"]]
    camera = CameraModel(
        position_ned=np.array([0.0, 0.0, -20.0], dtype=float)
    )
    workload: list[tuple[np.ndarray, SensorObservation]] = []
    digest_payload: list[dict[str, Any]] = []
    modality_counts: Counter[str] = Counter()
    for index in range(sample_count):
        state = np.array(
            [
                generator.uniform(80.0, 220.0),
                generator.uniform(-60.0, 60.0),
                generator.uniform(-35.0, -5.0),
                generator.uniform(-8.0, 8.0),
                generator.uniform(-8.0, 8.0),
                generator.uniform(-3.0, 3.0),
            ],
            dtype=float,
        )
        kind = modalities[index % len(modalities)]
        observation = _observation_for_kind(index, kind, state, camera)
        workload.append((state, observation))
        modality_counts[kind] += 1
        digest_payload.append(
            {
                "kind": kind,
                "state": state.tolist(),
                "observation": {
                    "observation_id": observation.observation_id,
                    "sensor_id": observation.sensor_id,
                    "modality": observation.modality,
                    "measurement_timestamp": (
                        observation.measurement_timestamp
                    ),
                    "arrival_timestamp": observation.arrival_timestamp,
                    "frame_id": observation.frame_id,
                    "measurement": observation.measurement.tolist(),
                    "covariance": observation.covariance.tolist(),
                    "metadata": dict(observation.metadata),
                },
            }
        )
    canonical = json.dumps(
        digest_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return workload, {
        "kind": "deterministic_mixed_measurement_model_workload",
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "modality_counts": dict(sorted(modality_counts.items())),
        "online_truth_use_count": 0,
    }


def _observation_for_kind(
    index: int,
    kind: str,
    state: np.ndarray,
    camera: CameraModel,
) -> SensorObservation:
    sensor_position = np.array([2.0, -3.0, -1.0], dtype=float)
    metadata: dict[str, Any]
    if kind == "radar_full":
        measurement = radar_h(state, sensor_position)
        covariance = np.diag([9.0, 2.0e-4, 3.0e-4, 0.49])
        modality = "radar"
        frame_id = "ned"
        metadata = {
            "sensor_position_ned": sensor_position.tolist(),
            "radial_velocity_observed": True,
        }
    elif kind == "radar_position_only":
        measurement = radar_h(state, sensor_position)
        measurement[3] = 0.0
        covariance = np.diag([9.0, 2.0e-4, 3.0e-4, 100.0])
        modality = "radar"
        frame_id = "ned"
        metadata = {
            "sensor_position_ned": sensor_position.tolist(),
            "radial_velocity_observed": False,
        }
    elif kind == "acoustic":
        measurement = acoustic_h(state, sensor_position)
        covariance = np.diag([np.deg2rad(4.0) ** 2])
        modality = "acoustic"
        frame_id = "ned"
        metadata = {"sensor_position_ned": sensor_position.tolist()}
    elif kind == "acoustic_3d":
        measurement = acoustic_3d_h(state, sensor_position)
        covariance = np.diag(
            [np.deg2rad(4.0) ** 2, np.deg2rad(5.0) ** 2]
        )
        modality = "acoustic_3d"
        frame_id = "ned"
        metadata = {"sensor_position_ned": sensor_position.tolist()}
    elif kind == "eo":
        measurement = eo_project(state, camera)
        covariance = np.diag([16.0, 16.0])
        modality = "eo"
        frame_id = "pixel"
        metadata = {
            "camera_model": {
                "position_ned": camera.position_ned.tolist(),
                "rotation_world_to_camera": (
                    camera.rotation_world_to_camera.tolist()
                ),
                "fx": camera.fx,
                "fy": camera.fy,
                "cx": camera.cx,
                "cy": camera.cy,
                "width": camera.width,
                "height": camera.height,
            }
        }
    elif kind == "lidar":
        measurement = state[:3].copy()
        covariance = np.diag([0.25, 0.25, 0.49])
        modality = "lidar"
        frame_id = "ned"
        metadata = {}
    else:
        raise ValueError(f"unsupported benchmark observation kind: {kind}")
    metadata["benchmark_kind"] = kind
    return SensorObservation(
        observation_id=f"structured-jacobian-{index:05d}",
        sensor_id=f"benchmark-{modality}",
        modality=modality,
        measurement_timestamp=0.05 * index,
        arrival_timestamp=0.05 * index + 0.2,
        frame_id=frame_id,
        measurement=measurement,
        covariance=covariance,
        metadata=metadata,
    )


def _run_variant(
    workload: list[tuple[np.ndarray, SensorObservation]],
    *,
    candidate_enabled: bool,
    round_count: int,
    association_gate: float,
) -> dict[str, Any]:
    operations: Counter[str] = Counter()
    models = [
        measurement_model_for(
            observation,
            structured_jacobian=candidate_enabled,
            jacobian_operation_counts=operations,
        )
        for _, observation in workload
    ]
    checksum = 0.0
    started = perf_counter()
    for _ in range(round_count):
        for (state, _), model in zip(workload, models, strict=True):
            jacobian = model.h_jacobian_fn(state)
            checksum += float(jacobian[0, 0])
    wall_time_s = perf_counter() - started
    semantics = _semantic_snapshot(
        workload,
        candidate_enabled=candidate_enabled,
        association_gate=association_gate,
    )
    attempt_count = int(operations["jacobian_attempt_count"])
    success_count = int(operations["jacobian_success_count"])
    failure_count = int(operations["jacobian_failure_count"])
    reference_count = int(operations["reference_call_count"])
    candidate_count = int(operations["structured_candidate_call_count"])
    return {
        "wall_time_s": float(wall_time_s),
        "checksum": float(checksum),
        **semantics,
        "diagnostics": {
            "schema_version": (
                STRUCTURED_NUMERICAL_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION
            ),
            "implementation_id": (
                STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION_ID
                if candidate_enabled
                else STRUCTURED_NUMERICAL_JACOBIAN_REFERENCE_IMPLEMENTATION_ID
            ),
            "candidate_enabled": bool(candidate_enabled),
            "operation_counts": dict(sorted(operations.items())),
            "conservation": {
                "attempt_equals_success_plus_failure": (
                    attempt_count == success_count + failure_count
                ),
                "attempt_equals_reference_plus_candidate": (
                    attempt_count == reference_count + candidate_count
                ),
            },
        },
    }


def _semantic_snapshot(
    workload: list[tuple[np.ndarray, SensorObservation]],
    *,
    candidate_enabled: bool,
    association_gate: float,
) -> dict[str, Any]:
    jacobian_digest = hashlib.sha256()
    nis_digest = hashlib.sha256()
    gate_digest = hashlib.sha256()
    finite_output = True
    for state, observation in workload:
        model = measurement_model_for(
            observation,
            structured_jacobian=candidate_enabled,
        )
        predicted = model.h_fn(state)
        jacobian = model.h_jacobian_fn(state)
        residual = wrap_residual(
            model.z - predicted,
            model.angle_indices,
        )
        innovation_covariance = (
            jacobian @ np.eye(6, dtype=float) @ jacobian.T + model.r
        )
        innovation_covariance = (
            0.5 * (innovation_covariance + innovation_covariance.T)
            + 1.0e-9 * np.eye(innovation_covariance.shape[0])
        )
        nis = float(
            residual.T @ np.linalg.pinv(innovation_covariance) @ residual
        )
        gate_pass = bool(np.isfinite(nis) and nis <= association_gate)
        jacobian_digest.update(
            np.ascontiguousarray(jacobian).tobytes()
        )
        nis_digest.update(np.asarray([nis], dtype=float).tobytes())
        gate_digest.update(b"\1" if gate_pass else b"\0")
        finite_output = (
            finite_output
            and bool(np.isfinite(jacobian).all())
            and bool(np.isfinite(nis))
        )
    return {
        "jacobian_sha256": jacobian_digest.hexdigest(),
        "nis_sha256": nis_digest.hexdigest(),
        "gate_decision_sha256": gate_digest.hexdigest(),
        "finite_output": bool(finite_output),
    }


def _profile_variant(
    workload: list[tuple[np.ndarray, SensorObservation]],
    *,
    candidate_enabled: bool,
    round_count: int,
    association_gate: float,
) -> dict[str, Any]:
    profiler = cProfile.Profile()
    profiler.enable()
    result = _run_variant(
        workload,
        candidate_enabled=candidate_enabled,
        round_count=round_count,
        association_gate=association_gate,
    )
    profiler.disable()
    stats = pstats.Stats(profiler)
    selected: dict[str, dict[str, int | float]] = {}
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
        "profiled_jacobian_call_count": int(
            len(workload) * round_count
        ),
        "profiled_wall_time_s": float(result["wall_time_s"]),
        "selected_functions": selected,
    }


def _summarize(
    samples: list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    wall_times = [float(item["wall_time_s"]) for item in samples]
    diagnostics = {
        json.dumps(
            item["diagnostics"],
            sort_keys=True,
            separators=(",", ":"),
        )
        for item in samples
    }
    if len(diagnostics) != 1:
        raise RuntimeError("Jacobian operation diagnostics were not deterministic")
    return {
        "sample_count": len(samples),
        "wall_time_samples_s": wall_times,
        "median_wall_time_s": float(median(wall_times)),
        "minimum_wall_time_s": float(min(wall_times)),
        "maximum_wall_time_s": float(max(wall_times)),
        "jacobian_sha256": samples[0]["jacobian_sha256"],
        "nis_sha256": samples[0]["nis_sha256"],
        "gate_decision_sha256": samples[0]["gate_decision_sha256"],
        "finite_output": bool(
            all(item["finite_output"] for item in samples)
        ),
        "diagnostics": samples[0]["diagnostics"],
        "profile": profile,
    }


def _positive_override(
    value: int | None,
    default: int,
    name: str,
) -> int:
    selected = default if value is None else value
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise TypeError(f"{name} must be an integer")
    if selected < 1:
        raise ValueError(f"{name} must be positive")
    return int(selected)


def _non_negative_override(
    value: int | None,
    default: int,
    name: str,
) -> int:
    selected = default if value is None else value
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise TypeError(f"{name} must be an integer")
    if selected < 0:
        raise ValueError(f"{name} must be non-negative")
    return int(selected)
