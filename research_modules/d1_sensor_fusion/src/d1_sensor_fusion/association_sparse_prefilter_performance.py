from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path
from statistics import fmean, median
from time import perf_counter
from typing import Any, Callable

import numpy as np

from .fusion import (
    ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR,
    ASSOCIATION_SPARSE_PREFILTER_MODALITY_BUCKETS,
    ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR,
    FusionAdapter,
)
from .observations import (
    CameraModel,
    acoustic_3d_h,
    acoustic_covariance,
    eo_project,
    lidar_covariance,
    radar_covariance_from_range,
    radar_h,
)
from .types import SensorObservation


ASSOCIATION_SPARSE_PREFILTER_PERFORMANCE_SCHEMA_VERSION = (
    "d1.association_sparse_prefilter_performance.v2"
)
_NON_RADAR_MODALITIES = ("lidar", "acoustic", "acoustic_3d", "eo")
_MODALITY_BUCKETS = {
    "radar": "radar",
    "lidar": "lidar",
    "acoustic": "acoustic",
    "acoustic_3d": "acoustic_3d",
    "eo": "eo",
}
_SUMMARY_OPERATION_FIELDS = {
    "association_candidate_pair_count",
    "association_measurement_model_build_count",
    "association_projection_build_count",
    "association_innovation_solve_count",
    "association_radar_track_state_build_count",
    "association_radar_observation_state_build_count",
}


def benchmark_association_sparse_prefilter(
    *,
    target_count: int = 120,
    repeat_count: int = 7,
    warmup_count: int = 1,
) -> dict[str, Any]:
    """Run an alternating, same-process synthetic association microbenchmark."""

    if target_count < 2:
        raise ValueError("target_count must be at least two")
    if repeat_count < 1:
        raise ValueError("repeat_count must be positive")
    if warmup_count < 0:
        raise ValueError("warmup_count must be non-negative")

    scan_factories: dict[
        str,
        Callable[[int, float, str], tuple[SensorObservation, ...]],
    ] = {
        "radar": _radar_scan,
        "lidar": _lidar_scan,
        "acoustic": _acoustic_scan,
        "acoustic_3d": _acoustic_3d_scan,
        "eo": _eo_scan,
    }
    for _ in range(warmup_count):
        for modality, factory in scan_factories.items():
            _run_variant(
                target_count,
                modality,
                factory,
                ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR,
            )
            _run_variant(
                target_count,
                modality,
                factory,
                ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR,
            )

    modality_reports: dict[str, Any] = {}
    for modality, factory in scan_factories.items():
        runs = {
            ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR: [],
            ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR: [],
        }
        for repetition in range(repeat_count):
            selectors = (
                (
                    ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR,
                    ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR,
                )
                if repetition % 2 == 0
                else (
                    ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR,
                    ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR,
                )
            )
            for selector in selectors:
                runs[selector].append(
                    _run_variant(
                        target_count,
                        modality,
                        factory,
                        selector,
                    )
                )

        reference_runs = runs[ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR]
        candidate_runs = runs[ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR]
        reference_timing = _timing_statistics(reference_runs)
        candidate_timing = _timing_statistics(candidate_runs)
        reference_counts = reference_runs[0]["modality_counts"]
        candidate_counts = candidate_runs[0]["modality_counts"]
        exact_gate_pass_equivalence = (
            reference_counts["exact_gate_pass_count"]
            == candidate_counts["exact_gate_pass_count"]
        )
        semantic_digests = {
            item["semantic_sha256"]
            for variant_runs in runs.values()
            for item in variant_runs
        }
        operation_counts_stable = all(
            item["modality_counts"] == variant_runs[0]["modality_counts"]
            for variant_runs in runs.values()
            for item in variant_runs
        )
        pair_count = int(reference_counts["candidate_pair_count"])
        reference_solves = int(reference_counts["exact_innovation_solve_count"])
        candidate_solves = int(candidate_counts["exact_innovation_solve_count"])
        modality_reports[modality] = {
            "modality_bucket": _MODALITY_BUCKETS[modality],
            "semantic_equivalence": len(semantic_digests) == 1,
            "exact_gate_pass_equivalence": exact_gate_pass_equivalence,
            "semantic_sha256": sorted(semantic_digests),
            "operation_counts_stable": operation_counts_stable,
            "reference": {
                "timing": reference_timing,
                "modality_counts": reference_counts,
                "runs": reference_runs,
            },
            "candidate": {
                "timing": candidate_timing,
                "modality_counts": candidate_counts,
                "runs": candidate_runs,
            },
            "comparison": {
                "candidate_pair_count": pair_count,
                "exact_solve_reduction_count": (
                    reference_solves - candidate_solves
                ),
                "exact_solve_reduction_fraction": (
                    0.0
                    if reference_solves == 0
                    else 1.0 - candidate_solves / reference_solves
                ),
                "p50_wall_time_improvement_fraction": (
                    1.0
                    - candidate_timing["p50_s"] / reference_timing["p50_s"]
                ),
                "candidate_faster_run_count": sum(
                    candidate["wall_time_s"] < reference["wall_time_s"]
                    for reference, candidate in zip(
                        reference_runs,
                        candidate_runs,
                    )
                ),
                "paired_run_count": repeat_count,
            },
        }

    reference_non_radar_times = [
        sum(
            modality_reports[modality]["reference"]["runs"][index][
                "wall_time_s"
            ]
            for modality in _NON_RADAR_MODALITIES
        )
        for index in range(repeat_count)
    ]
    candidate_non_radar_times = [
        sum(
            modality_reports[modality]["candidate"]["runs"][index][
                "wall_time_s"
            ]
            for modality in _NON_RADAR_MODALITIES
        )
        for index in range(repeat_count)
    ]
    reference_non_radar_p50 = float(median(reference_non_radar_times))
    candidate_non_radar_p50 = float(median(candidate_non_radar_times))
    combined_improvement = (
        1.0 - candidate_non_radar_p50 / reference_non_radar_p50
    )
    all_semantically_equal = all(
        report["semantic_equivalence"]
        for report in modality_reports.values()
    )
    all_counts_stable = all(
        report["operation_counts_stable"]
        for report in modality_reports.values()
    )
    all_exact_gate_pass_counts_equal = all(
        report["exact_gate_pass_equivalence"]
        for report in modality_reports.values()
    )
    all_non_radar_reduce_solves = all(
        modality_reports[modality]["comparison"][
            "exact_solve_reduction_count"
        ]
        > 0
        for modality in _NON_RADAR_MODALITIES
    )
    recommend_main_ab = bool(
        all_semantically_equal
        and all_counts_stable
        and all_exact_gate_pass_counts_equal
        and all_non_radar_reduce_solves
        and combined_improvement >= 0.05
    )
    return {
        "schema_version": (
            ASSOCIATION_SPARSE_PREFILTER_PERFORMANCE_SCHEMA_VERSION
        ),
        "machine": _machine_summary(),
        "protocol": {
            "synthetic_truth_free_online_payload": True,
            "target_count": target_count,
            "candidate_pair_count_per_modality": target_count * target_count,
            "repeat_count_per_variant": repeat_count,
            "warmup_count_per_variant": warmup_count,
            "same_process": True,
            "alternating_variant_order": True,
            "timed_scope": "one_state_only_association_update_scan",
            "diagnostic_modality_buckets": (
                ASSOCIATION_SPARSE_PREFILTER_MODALITY_BUCKETS
            ),
            "timed_modalities": tuple(scan_factories),
            "other_bucket_benchmark_status": (
                "not_applicable_public_contract_rejects_unknown_modalities"
            ),
        },
        "modalities": modality_reports,
        "combined_non_radar": {
            "reference_p50_s": reference_non_radar_p50,
            "candidate_p50_s": candidate_non_radar_p50,
            "p50_wall_time_improvement_fraction": combined_improvement,
        },
        "acceptance": {
            "all_modalities_semantically_equivalent": all_semantically_equal,
            "all_operation_counts_stable": all_counts_stable,
            "all_exact_gate_pass_counts_equal": (
                all_exact_gate_pass_counts_equal
            ),
            "all_non_radar_modalities_reduce_exact_solves": (
                all_non_radar_reduce_solves
            ),
            "combined_non_radar_p50_improvement_at_least_5_percent": (
                combined_improvement >= 0.05
            ),
            "recommend_main_formal_ab": recommend_main_ab,
        },
        "scope_limits": (
            "synthetic D1 module microbenchmark only",
            "not an integrated 200v200 realtime admission",
            "not AirSim or target hardware evidence",
        ),
    }


def render_association_sparse_prefilter_report_cn(report: dict[str, Any]) -> str:
    """Render a concise Chinese report from the benchmark payload."""

    lines = [
        "# D1 模态感知保守稀疏预筛微基准",
        "",
        "## 结论",
        "",
    ]
    combined = report["combined_non_radar"]
    acceptance = report["acceptance"]
    lines.append(
        "LiDAR、二维声学、三维声学和光电四类扫描合计 P50 从 "
        f"`{combined['reference_p50_s']:.6f} s` 降至 "
        f"`{combined['candidate_p50_s']:.6f} s`，改善 "
        f"`{combined['p50_wall_time_improvement_fraction'] * 100.0:.3f}%`。"
    )
    lines.append(
        "固定输入规范输出等价："
        f"`{acceptance['all_modalities_semantically_equivalent']}`；"
        "精确门内 pair 计数等价："
        f"`{acceptance['all_exact_gate_pass_counts_equal']}`；"
        "建议 main 进入正式 A/B："
        f"`{acceptance['recommend_main_formal_ab']}`。"
    )
    lines.extend(
        [
            "",
            "## 协议",
            "",
            f"- 目标数：`{report['protocol']['target_count']}`",
            (
                "- 每模态候选对："
                f"`{report['protocol']['candidate_pair_count_per_modality']}`"
            ),
            (
                "- 每变体正式重复："
                f"`{report['protocol']['repeat_count_per_variant']}`，同进程交错执行"
            ),
            (
                "- 计时范围："
                f"`{report['protocol']['timed_scope']}`"
            ),
            "",
            "## 分模态结果",
            "",
            "| 模态 | 候选 pair | Reference P50 / s | Candidate P50 / s | "
            "墙钟改善 | 精确求解 R -> C | 精确门内通过 R/C | 求解减少 | "
            "预筛剔除 | Fallback | Candidate 更快 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: |",
        ]
    )
    display_names = {
        "radar": "雷达",
        "lidar": "LiDAR",
        "acoustic": "二维声学",
        "acoustic_3d": "三维声学",
        "eo": "光电",
    }
    for modality in ("radar", "lidar", "acoustic", "acoustic_3d", "eo"):
        item = report["modalities"][modality]
        reference = item["reference"]
        candidate = item["candidate"]
        comparison = item["comparison"]
        reference_solves = reference["modality_counts"][
            "exact_innovation_solve_count"
        ]
        candidate_solves = candidate["modality_counts"][
            "exact_innovation_solve_count"
        ]
        lines.append(
            f"| {display_names[modality]} | "
            f"{comparison['candidate_pair_count']} | "
            f"{reference['timing']['p50_s']:.6f} | "
            f"{candidate['timing']['p50_s']:.6f} | "
            f"{comparison['p50_wall_time_improvement_fraction'] * 100.0:.3f}% | "
            f"{reference_solves} -> {candidate_solves} | "
            f"{reference['modality_counts']['exact_gate_pass_count']}/"
            f"{candidate['modality_counts']['exact_gate_pass_count']} | "
            f"{comparison['exact_solve_reduction_fraction'] * 100.0:.3f}% | "
            f"{candidate['modality_counts']['conservative_prefilter_rejection_count']} | "
            f"{candidate['modality_counts']['fallback_count']} | "
            f"{comparison['candidate_faster_run_count']}/"
            f"{comparison['paired_run_count']} |"
        )
    lines.extend(
        [
            "",
            "## 保守边界",
            "",
            "预筛只在创新协方差有限、严格对称、Gershgorin 下界严格为正，且该下界高于 "
            "NumPy 伪逆截断上界时生效。未认证 pair 进入原精确求解，不作启发式删除。",
            "",
            "二维/三维声学使用现有角度环绕后的弧度残差，光电使用现有相机投影后的"
            "像素残差。雷达保留已准入的旧下界路径，因此 selector 对雷达没有新增"
            "处理收益；`other` 因公共合同拒绝未知模态而不构造合成计时输入。",
            "",
            "## 证据边界",
            "",
            "该结果是 D1 合成模块微基准，不代表完整 200v200 实时倍率，也不代表 "
            "AirSim、目标处理器或实装传感器性能。正式默认提升仍需 main 在冻结输入上"
            "完成短时和长时多 seed A/B，并由 D6 独立判定。",
            "",
        ]
    )
    return "\n".join(lines)


def write_association_sparse_prefilter_report(
    report: dict[str, Any],
    *,
    json_output: str | Path,
    markdown_output: str | Path,
) -> None:
    json_path = Path(json_output)
    markdown_path = Path(markdown_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_association_sparse_prefilter_report_cn(report),
        encoding="utf-8",
    )


def _run_variant(
    target_count: int,
    modality: str,
    factory: Callable[[int, float, str], tuple[SensorObservation, ...]],
    selector: str,
) -> dict[str, Any]:
    adapter = FusionAdapter(
        association_gate=40.0,
        association_sparse_prefilter=selector,
    )
    adapter.process_scan_batch(
        _radar_scan(target_count, 0.0, f"{modality}-origin"),
        materialize_tracks=False,
    )
    update = factory(target_count, 0.2, f"{modality}-update")
    started = perf_counter()
    result = adapter.process_scan_batch(update, materialize_tracks=False)
    wall_time_s = perf_counter() - started
    snapshot = adapter.materialize_global_tracks()
    summary = result.summary.to_dict()
    for field_name in _SUMMARY_OPERATION_FIELDS:
        summary.pop(field_name, None)
    semantic_payload = {
        "tracks": [track.to_dict() for track in snapshot.tracks],
        "summary": summary,
        "consistency_evidence": [
            item.to_dict() for item in adapter.consistency_evidence_records()
        ],
    }
    semantic_sha256 = hashlib.sha256(
        json.dumps(
            semantic_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    bucket = _MODALITY_BUCKETS[modality]
    return {
        "selector": selector,
        "wall_time_s": wall_time_s,
        "semantic_sha256": semantic_sha256,
        "modality_counts": adapter.association_sparse_prefilter_diagnostics()[
            "modality_counts"
        ][bucket],
    }


def _states(count: int, timestamp: float) -> tuple[np.ndarray, ...]:
    azimuths = np.linspace(-0.72, 0.72, count)
    ranges = 950.0 + 4.0 * np.arange(count, dtype=float)
    states = []
    for index, (azimuth, distance) in enumerate(zip(azimuths, ranges)):
        state = np.array(
            [
                distance * np.cos(azimuth),
                distance * np.sin(azimuth),
                -90.0 - 0.4 * index,
                4.0 + 0.02 * index,
                -0.4 + 0.01 * index,
                0.05,
            ],
            dtype=float,
        )
        state[:3] += state[3:] * float(timestamp)
        states.append(state)
    return tuple(states)


def _radar_scan(
    count: int,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    observations = []
    for index, state in enumerate(_states(count, timestamp)):
        measurement = radar_h(state, np.zeros(3, dtype=float))
        observations.append(
            SensorObservation(
                observation_id=f"{scan_id}-{index:04d}",
                sensor_id="radar-prefilter-benchmark",
                modality="radar",
                measurement_timestamp=timestamp,
                arrival_timestamp=timestamp + 0.1,
                frame_id="ned",
                measurement=measurement,
                covariance=radar_covariance_from_range(float(measurement[0])),
                confidence=0.95,
                metadata={
                    "sensor_position_ned": np.zeros(3, dtype=float),
                    "scan_id": scan_id,
                    "coverage_cell": "prefilter-benchmark",
                },
            )
        )
    return tuple(observations)


def _lidar_scan(
    count: int,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    return tuple(
        SensorObservation(
            observation_id=f"{scan_id}-{index:04d}",
            sensor_id="lidar-prefilter-benchmark",
            modality="lidar",
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.1,
            frame_id="ned",
            measurement=state[:3],
            covariance=lidar_covariance(float(np.linalg.norm(state[:3]))),
            confidence=0.95,
            metadata={
                "scan_id": scan_id,
                "coverage_cell": "prefilter-benchmark",
            },
        )
        for index, state in enumerate(_states(count, timestamp))
    )


def _acoustic_scan(
    count: int,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    return tuple(
        SensorObservation(
            observation_id=f"{scan_id}-{index:04d}",
            sensor_id="acoustic-prefilter-benchmark",
            modality="acoustic",
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.1,
            frame_id="ned",
            measurement=np.array([np.arctan2(state[1], state[0])], dtype=float),
            covariance=acoustic_covariance(0.95),
            confidence=0.95,
            metadata={
                "sensor_position_ned": np.zeros(3, dtype=float),
                "scan_id": scan_id,
                "coverage_cell": "prefilter-benchmark",
            },
        )
        for index, state in enumerate(_states(count, timestamp))
    )


def _acoustic_3d_scan(
    count: int,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    sensor_position = np.zeros(3, dtype=float)
    angular_variance = float(acoustic_covariance(0.95)[0, 0])
    return tuple(
        SensorObservation(
            observation_id=f"{scan_id}-{index:04d}",
            sensor_id="acoustic-3d-prefilter-benchmark",
            modality="acoustic_3d",
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.1,
            frame_id="ned",
            measurement=acoustic_3d_h(state, sensor_position),
            covariance=np.diag([angular_variance, angular_variance]),
            confidence=0.95,
            metadata={
                "sensor_position_ned": sensor_position.copy(),
                "scan_id": scan_id,
                "coverage_cell": "prefilter-benchmark",
                "soundprint_category_only": True,
            },
        )
        for index, state in enumerate(_states(count, timestamp))
    )


def _eo_scan(
    count: int,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    camera = CameraModel(
        position_ned=np.zeros(3, dtype=float),
        rotation_world_to_camera=np.array(
            [
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0],
            ],
            dtype=float,
        ),
        fx=900.0,
        fy=900.0,
        cx=640.0,
        cy=360.0,
    )
    return tuple(
        SensorObservation(
            observation_id=f"{scan_id}-{index:04d}",
            sensor_id="eo-prefilter-benchmark",
            modality="eo",
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.1,
            frame_id="pixel",
            measurement=eo_project(state, camera),
            covariance=np.diag([4.0, 4.0]),
            confidence=0.95,
            metadata={
                "camera_id": "eo-prefilter-benchmark",
                "camera_position_ned": camera.position_ned.copy(),
                "rotation_world_to_camera": (
                    camera.rotation_world_to_camera.copy()
                ),
                "fx": camera.fx,
                "fy": camera.fy,
                "cx": camera.cx,
                "cy": camera.cy,
                "scan_id": scan_id,
                "coverage_cell": "prefilter-benchmark",
            },
        )
        for index, state in enumerate(_states(count, timestamp))
    )


def _timing_statistics(runs: list[dict[str, Any]]) -> dict[str, float]:
    values = [float(item["wall_time_s"]) for item in runs]
    return {
        "mean_s": float(fmean(values)),
        "p50_s": float(median(values)),
        "p95_s": float(np.percentile(values, 95.0)),
        "minimum_s": float(min(values)),
        "maximum_s": float(max(values)),
    }


def _machine_summary() -> dict[str, Any]:
    cpu_model = platform.processor()
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "cpu_model": cpu_model or "unknown",
        "logical_cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "platform": platform.platform(),
    }
