from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import median
from time import perf_counter
from types import MappingProxyType
from typing import Any

import numpy as np

from .scalable_3d import (
    ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION,
    ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
    OnlineBatchFrameBuilder,
)
from .scan_input import SensorScanFrame


ONLINE_BATCH_FRAME_HANDOFF_PERFORMANCE_SCHEMA_VERSION = (
    "d1.online_batch_frame_handoff_performance.v1"
)
MINIMUM_MEASUREMENT_COUNT = 200
MINIMUM_REPETITIONS = 7
MINIMUM_MEDIAN_IMPROVEMENT_FRACTION = 0.20
MINIMUM_CANDIDATE_FASTER_FRACTION = 0.70


@dataclass(frozen=True)
class _FrozenOnlineMeasurement:
    observation_id: str
    sensor_id: str
    modality: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    measurement: np.ndarray
    covariance: np.ndarray
    confidence: float
    classification_hint: str | None
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "measurement",
            _readonly_array(self.measurement),
        )
        object.__setattr__(
            self,
            "covariance",
            _readonly_array(self.covariance),
        )
        object.__setattr__(
            self,
            "metadata",
            _freeze_mapping(self.metadata),
        )


@dataclass(frozen=True)
class _FrozenOnlineBatch:
    batch_id: str
    sensor_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    measurements: tuple[_FrozenOnlineMeasurement, ...]


def compare_online_batch_frame_handoff_variants(
    *,
    repetitions: int = MINIMUM_REPETITIONS,
    measurement_count: int = MINIMUM_MEASUREMENT_COUNT,
) -> dict[str, Any]:
    """Run the pre-registered frozen 200-measurement handoff benchmark."""

    if repetitions < MINIMUM_REPETITIONS:
        raise ValueError(
            f"repetitions must be at least {MINIMUM_REPETITIONS}"
        )
    if measurement_count < MINIMUM_MEASUREMENT_COUNT:
        raise ValueError(
            f"measurement_count must be at least {MINIMUM_MEASUREMENT_COUNT}"
        )

    batch = _build_frozen_batch(measurement_count)
    OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION
    ).build(batch)
    OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    ).build(batch)

    reference_builder = OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION
    )
    candidate_builder = OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    builders = {
        "reference": reference_builder,
        "candidate": candidate_builder,
    }
    samples: dict[str, list[dict[str, Any]]] = {
        "reference": [],
        "candidate": [],
    }
    for repetition in range(repetitions):
        order = (
            ("reference", "candidate")
            if repetition % 2 == 0
            else ("candidate", "reference")
        )
        for name in order:
            samples[name].append(_timed_build(builders[name], batch))

    reference_summary = _summarize_samples(samples["reference"])
    candidate_summary = _summarize_samples(samples["candidate"])
    reference_times = [
        float(item["wall_time_s"]) for item in samples["reference"]
    ]
    candidate_times = [
        float(item["wall_time_s"]) for item in samples["candidate"]
    ]
    candidate_faster_count = sum(
        candidate < reference
        for reference, candidate in zip(
            reference_times,
            candidate_times,
            strict=True,
        )
    )
    candidate_faster_fraction = candidate_faster_count / repetitions
    reference_median = float(reference_summary["median_wall_time_s"])
    candidate_median = float(candidate_summary["median_wall_time_s"])
    median_improvement_fraction = (
        1.0 - candidate_median / reference_median
        if reference_median > 0.0
        else 0.0
    )

    reference_diagnostics = reference_builder.diagnostics()
    candidate_diagnostics = candidate_builder.diagnostics()
    reference_counts = reference_diagnostics["operation_counts"]
    candidate_counts = candidate_diagnostics["operation_counts"]
    expected_measurement_checks = repetitions * measurement_count
    reference_digests = {
        item["canonical_frame_sha256"] for item in samples["reference"]
    }
    candidate_digests = {
        item["canonical_frame_sha256"] for item in samples["candidate"]
    }
    exception_summaries = _exception_equivalence_summaries(batch)

    semantic_acceptance = {
        "canonical_frame_sha256_equal": (
            len(reference_digests) == 1
            and reference_digests == candidate_digests
        ),
        "all_exception_summaries_equal": all(
            item["equivalent"] for item in exception_summaries.values()
        ),
        "reference_raw_batch_check_count": (
            reference_counts["raw_batch_identity_check_count"] == repetitions
        ),
        "reference_raw_measurement_check_count": (
            reference_counts["raw_measurement_identity_check_count"]
            == expected_measurement_checks
        ),
        "reference_converted_collection_check_count": (
            reference_counts[
                "converted_observation_collection_check_count"
            ]
            == repetitions
        ),
        "reference_frame_final_check_count": (
            reference_counts["frame_final_identity_check_count"]
            == repetitions
        ),
        "candidate_raw_batch_check_count": (
            candidate_counts["raw_batch_identity_check_count"] == repetitions
        ),
        "candidate_eliminates_per_measurement_duplicate_checks": (
            candidate_counts["raw_measurement_identity_check_count"] == 0
        ),
        "candidate_eliminates_converted_collection_duplicate_checks": (
            candidate_counts[
                "converted_observation_collection_check_count"
            ]
            == 0
        ),
        "candidate_frame_final_check_count": (
            candidate_counts["frame_final_identity_check_count"]
            == repetitions
        ),
        "candidate_uses_closed_handoff_without_fallback": (
            candidate_counts["candidate_closed_handoff_count"] == repetitions
            and candidate_counts["candidate_reference_fallback_count"] == 0
        ),
        "candidate_runs_structural_eligibility_check": (
            candidate_counts["snapshot_structure_check_count"] == repetitions
            and candidate_counts["snapshot_structure_eligible_count"]
            == repetitions
            and candidate_counts["snapshot_structure_ineligible_count"] == 0
            and candidate_counts["snapshot_structure_error_count"] == 0
        ),
        "candidate_completes_deep_snapshot": (
            candidate_counts["closed_payload_snapshot_attempt_count"]
            == repetitions
            and candidate_counts["closed_payload_snapshot_success_count"]
            == repetitions
            and candidate_counts["closed_payload_snapshot_failure_count"] == 0
            and candidate_counts["candidate_resource_rejection_count"] == 0
        ),
        "reference_counter_conservation": all(
            reference_diagnostics["conservation"].values()
        ),
        "candidate_counter_conservation": all(
            candidate_diagnostics["conservation"].values()
        ),
        "default_implementation_remains_reference": (
            OnlineBatchFrameBuilder().implementation
            == ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION
        ),
    }
    performance_acceptance = {
        "median_improvement_at_least_20_percent": (
            median_improvement_fraction
            >= MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
        ),
        "candidate_faster_fraction_at_least_70_percent": (
            candidate_faster_fraction
            >= MINIMUM_CANDIDATE_FASTER_FRACTION
        ),
    }
    module_threshold_met = bool(
        all(semantic_acceptance.values())
        and all(performance_acceptance.values())
    )

    return {
        "schema_version": (
            ONLINE_BATCH_FRAME_HANDOFF_PERFORMANCE_SCHEMA_VERSION
        ),
        "validation_date": "2026-07-25",
        "benchmark_scope": (
            "D1 default no-source-key R0 raw online batch to read-only "
            "SensorScanFrame handoff; module microbenchmark only"
        ),
        "selection_evidence": {
            "source": "main development cProfile",
            "scenario": "default R0 200v200 2.2s seed 1112",
            "batch_count": 95,
            "observation_count": 2_044,
            "online_observation_identity_check_call_count": 190,
            "online_observation_identity_check_cumulative_s": 2.236763,
            "converter_collection_check_call_count": 95,
            "converter_collection_check_cumulative_s": 1.120932,
            "frame_final_check_call_count": 95,
            "frame_final_check_cumulative_s": 1.115831,
            "sensor_scan_frame_post_init_cumulative_s": 1.397623,
            "raw_payload_check_call_count": 2_139,
            "raw_payload_check_cumulative_s": 0.403673,
            "raw_measurement_check_call_count": 2_044,
            "raw_measurement_check_cumulative_s": 0.206688,
            "raw_batch_check_call_count": 95,
            "raw_batch_check_cumulative_s": 0.196985,
            "admission_use": "candidate selection only",
        },
        "configuration": {
            "repetitions": repetitions,
            "measurement_count": measurement_count,
            "warmup_count_per_variant": 1,
            "interleaved_order": True,
            "modality": "radar_spherical",
            "source_key_enabled": False,
            "structural_ambiguity_hold_enabled": False,
        },
        "preregistered_policy": {
            "minimum_measurement_count": MINIMUM_MEASUREMENT_COUNT,
            "minimum_repetitions": MINIMUM_REPETITIONS,
            "minimum_median_improvement_fraction": (
                MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
            ),
            "minimum_candidate_faster_fraction": (
                MINIMUM_CANDIDATE_FASTER_FRACTION
            ),
            "all_semantic_and_exception_summaries_must_match": True,
            "candidate_remains_default_off": True,
            "main_full_stack_admission_claimed": False,
        },
        "reference": {
            **reference_summary,
            "diagnostics": reference_diagnostics,
        },
        "candidate": {
            **candidate_summary,
            "diagnostics": candidate_diagnostics,
        },
        "comparison": {
            "median_improvement_fraction": median_improvement_fraction,
            "median_speedup": (
                reference_median / candidate_median
                if candidate_median > 0.0
                else None
            ),
            "candidate_faster_count": candidate_faster_count,
            "candidate_faster_fraction": candidate_faster_fraction,
            "canonical_frame_sha256": next(iter(reference_digests)),
            "exception_summaries": exception_summaries,
            "semantic_acceptance": semantic_acceptance,
            "performance_acceptance": performance_acceptance,
            "module_threshold_met": module_threshold_met,
            "recommend_main_explicit_ab": module_threshold_met,
            "recommend_default_promotion": False,
        },
        "constraints": {
            "full_raw_batch_check_preserved": True,
            "final_readonly_frame_check_preserved": True,
            "public_raw_measurement_validation_preserved": True,
            "public_raw_observation_validation_preserved": True,
            "truth_actor_object_target_rejection_preserved": True,
            "covariance_and_timestamp_validation_preserved": True,
            "lineage_and_duplicate_validation_preserved": True,
            "no_public_validation_bypass": True,
            "raw_source_absolute_immutability_claimed": False,
            "ordinary_snapshot_exception_falls_back_to_reference": True,
            "memory_error_falls_back_to_reference": False,
            "online_truth_use_count": 0,
            "system_realtime_claimed": False,
            "airsim_or_hardware_claimed": False,
        },
    }


def canonical_sensor_scan_frame_sha256(frame: SensorScanFrame) -> str:
    payload = json.dumps(
        _json_safe(frame.to_dict()),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_online_batch_frame_handoff_report(
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
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    comparison = report["comparison"]
    reference = report["reference"]
    candidate = report["candidate"]
    reference_counts = reference["diagnostics"]["operation_counts"]
    candidate_counts = candidate["diagnostics"]["operation_counts"]
    status = (
        "D1 模块门槛通过"
        if comparison["module_threshold_met"]
        else "D1 模块门槛未通过"
    )
    markdown_destination.write_text(
        "\n".join(
            (
                "# D1 在线批次到扫描帧交接微基准",
                "",
                "## 结论",
                "",
                f"- 判定：**{status}**。",
                (
                    f"- reference 中位耗时："
                    f"`{reference['median_wall_time_s']:.6f} s`。"
                ),
                (
                    f"- candidate 中位耗时："
                    f"`{candidate['median_wall_time_s']:.6f} s`。"
                ),
                (
                    f"- 中位改善："
                    f"`{100.0 * comparison['median_improvement_fraction']:.3f}%`。"
                ),
                (
                    f"- candidate 更快：`{comparison['candidate_faster_count']}/"
                    f"{report['configuration']['repetitions']}`。"
                ),
                (
                    f"- 规范帧 SHA-256："
                    f"`{comparison['canonical_frame_sha256']}`。"
                ),
                "",
                "## 验证遍历",
                "",
                "| 路径 | 整批 raw 检查 | 逐量测 raw 检查 | 转换后集合检查 | 最终帧检查 |",
                "| --- | ---: | ---: | ---: | ---: |",
                (
                    f"| reference | "
                    f"{reference_counts['raw_batch_identity_check_count']} | "
                    f"{reference_counts['raw_measurement_identity_check_count']} | "
                    f"{reference_counts['converted_observation_collection_check_count']} | "
                    f"{reference_counts['frame_final_identity_check_count']} |"
                ),
                (
                    f"| candidate | "
                    f"{candidate_counts['raw_batch_identity_check_count']} | "
                    f"{candidate_counts['raw_measurement_identity_check_count']} | "
                    f"{candidate_counts['converted_observation_collection_check_count']} | "
                    f"{candidate_counts['frame_final_identity_check_count']} |"
                ),
                "",
                "## 边界",
                "",
                "- candidate 先做结构合格检查，再建立深快照；该检查不声称 raw 来源绝对不可变。",
                "- 结构不合格或普通快照异常回退 reference；MemoryError 原样拒绝，不进入回退。",
                "- 公开裸量测、裸观测和扫描帧入口继续完整失败关闭校验。",
                "- 本结果只表示 D1 模块微基准门槛，不构成 main 全栈、AirSim、硬件或实时准入。",
                "",
            )
        ),
        encoding="utf-8",
    )


def _timed_build(
    builder: OnlineBatchFrameBuilder,
    batch: _FrozenOnlineBatch,
) -> dict[str, Any]:
    started = perf_counter()
    frame = builder.build(batch)
    elapsed = perf_counter() - started
    return {
        "wall_time_s": elapsed,
        "observation_count": len(frame.observations),
        "canonical_frame_sha256": canonical_sensor_scan_frame_sha256(frame),
    }


def _summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    wall_times = [float(item["wall_time_s"]) for item in samples]
    return {
        "sample_count": len(samples),
        "wall_time_samples_s": wall_times,
        "minimum_wall_time_s": min(wall_times),
        "median_wall_time_s": median(wall_times),
        "maximum_wall_time_s": max(wall_times),
        "canonical_frame_sha256_values": sorted(
            {item["canonical_frame_sha256"] for item in samples}
        ),
    }


def _build_frozen_batch(measurement_count: int) -> _FrozenOnlineBatch:
    batch_id = "online-frame-handoff-benchmark-0001"
    sensor_id = "RADAR-CENTER"
    measurement_timestamp = 1.0
    arrival_timestamp = 1.2
    measurements = tuple(
        _FrozenOnlineMeasurement(
            observation_id=f"benchmark-observation-{index:04d}",
            sensor_id=sensor_id,
            modality="radar_spherical",
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id="radar_center_frame",
            measurement=np.array(
                [1_000.0 + index, 0.001 * index, -0.05],
                dtype=float,
            ),
            covariance=np.diag([16.0, 1.0e-4, 1.0e-4]),
            confidence=0.95,
            classification_hint="unmanned_aircraft",
            metadata={
                "source_lineage_key": (
                    "explicit",
                    sensor_id,
                    batch_id,
                    index,
                ),
                "sensor_position_ned": (0.0, 0.0, 0.0),
                "range_dependent_covariance": True,
            },
        )
        for index in range(measurement_count)
    )
    return _FrozenOnlineBatch(
        batch_id=batch_id,
        sensor_id=sensor_id,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        measurements=measurements,
    )


def _exception_equivalence_summaries(
    batch: _FrozenOnlineBatch,
) -> dict[str, dict[str, Any]]:
    first = batch.measurements[0]
    second = batch.measurements[1]
    cases = {
        "truth_actor_leak": replace(
            batch,
            measurements=(
                replace(
                    first,
                    metadata={
                        **dict(first.metadata),
                        "actor_id": "forbidden-actor",
                    },
                ),
                *batch.measurements[1:],
            ),
        ),
        "bad_covariance": replace(
            batch,
            measurements=(
                replace(
                    first,
                    covariance=np.diag([-1.0, 1.0e-4, 1.0e-4]),
                ),
                *batch.measurements[1:],
            ),
        ),
        "measurement_timestamp_conflict": replace(
            batch,
            measurements=(
                replace(first, measurement_timestamp=1.1),
                *batch.measurements[1:],
            ),
        ),
        "arrival_timestamp_conflict": replace(
            batch,
            arrival_timestamp=0.5,
        ),
        "sensor_id_conflict": replace(
            batch,
            measurements=(
                replace(first, sensor_id="RADAR-OTHER"),
                *batch.measurements[1:],
            ),
        ),
        "duplicate_observation_id": replace(
            batch,
            measurements=(
                first,
                replace(
                    second,
                    observation_id=first.observation_id,
                ),
                *batch.measurements[2:],
            ),
        ),
        "duplicate_source_lineage": replace(
            batch,
            measurements=(
                first,
                replace(
                    second,
                    metadata=dict(first.metadata),
                ),
                *batch.measurements[2:],
            ),
        ),
        "scan_modality_conflict": replace(
            batch,
            measurements=(
                first,
                replace(
                    second,
                    modality="lidar",
                    frame_id="ned",
                    measurement=np.array([100.0, 20.0, -5.0]),
                    covariance=np.eye(3),
                ),
                *batch.measurements[2:],
            ),
        ),
    }
    summaries: dict[str, dict[str, Any]] = {}
    for name, case in cases.items():
        reference = _exception_summary(
            OnlineBatchFrameBuilder(
                implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION
            ),
            case,
        )
        candidate = _exception_summary(
            OnlineBatchFrameBuilder(
                implementation=ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
            ),
            case,
        )
        summaries[name] = {
            "reference": reference,
            "candidate": candidate,
            "equivalent": reference == candidate,
        }
    return summaries


def _exception_summary(
    builder: OnlineBatchFrameBuilder,
    batch: Any,
) -> dict[str, Any]:
    try:
        builder.build(batch)
    except Exception as exc:
        return {
            "outcome": "rejected",
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    return {"outcome": "accepted"}


def _readonly_array(value: Any) -> np.ndarray:
    result = np.array(value, dtype=float, copy=True)
    result.setflags(write=False)
    return result


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {str(key): _freeze_value(item) for key, item in value.items()}
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, np.ndarray):
        return _readonly_array(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    if isinstance(value, np.generic):
        return value.item()
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(
                value.items(),
                key=lambda item: str(item[0]),
            )
        }
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_json_safe(item) for item in value),
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    return value
