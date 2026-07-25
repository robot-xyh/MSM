from __future__ import annotations

import copy
from dataclasses import fields
import hashlib
import json
import os
import platform
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter
from typing import Any, Mapping, Sequence

import numpy as np

from .association_sparse_prefilter_performance import _radar_scan
from .fusion import (
    REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
    REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
    _BatchProcessingContext,
)
from .scalable_3d import Scalable3DFusionAdapter


REPLAY_PREFIX_SUMMARY_FIXTURE_SCHEMA_VERSION = (
    "d1.replay_prefix_summary_200v200_fixture.v1"
)
REPLAY_PREFIX_SUMMARY_PERFORMANCE_SCHEMA_VERSION = (
    "d1.replay_prefix_summary_performance.v1"
)
DEFAULT_REPLAY_PREFIX_SUMMARY_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "replay_prefix_summary_200v200_v1.json"
)
REPLAY_PREFIX_SUMMARY_BOOTSTRAP_SEED = 20_260_725
REPLAY_PREFIX_SUMMARY_BOOTSTRAP_RESAMPLE_COUNT = 20_000
REPLAY_PREFIX_SUMMARY_MINIMUM_PAIRED_RUN_COUNT = 5
REPLAY_PREFIX_SUMMARY_MINIMUM_CANDIDATE_FASTER_FRACTION = 0.8
REPLAY_PREFIX_SUMMARY_MINIMUM_MEDIAN_IMPROVEMENT_FRACTION = 0.05


def load_replay_prefix_summary_fixture(
    source: str | Path = DEFAULT_REPLAY_PREFIX_SUMMARY_FIXTURE,
) -> dict[str, Any]:
    path = Path(source)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != (
        REPLAY_PREFIX_SUMMARY_FIXTURE_SCHEMA_VERSION
    ):
        raise ValueError("unsupported replay prefix summary fixture schema")
    for field_name in (
        "fixture_id",
        "derivation",
        "target_count",
        "resource_count",
        "recon_node_count",
        "buffer_horizon_s",
        "measurement_timestamps_s",
        "arrival_delay_s",
        "timed_replay_sweep_count",
        "online_truth_use_count",
    ):
        if field_name not in payload:
            raise ValueError(
                f"replay prefix summary fixture missing {field_name!r}"
            )
    target_count = _positive_int(payload["target_count"], "target_count")
    resource_count = _positive_int(payload["resource_count"], "resource_count")
    recon_node_count = _positive_int(
        payload["recon_node_count"],
        "recon_node_count",
    )
    if target_count != 200 or resource_count != 200 or recon_node_count != 2:
        raise ValueError(
            "formal replay prefix summary fixture must remain 200v200 with "
            "two reconnaissance nodes"
        )
    timestamps = tuple(
        _finite_float(item, "measurement_timestamps_s")
        for item in payload["measurement_timestamps_s"]
    )
    if len(timestamps) < 2 or tuple(sorted(timestamps)) != timestamps:
        raise ValueError(
            "measurement_timestamps_s must contain at least two ordered times"
        )
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("measurement_timestamps_s must be unique")
    buffer_horizon = _positive_float(
        payload["buffer_horizon_s"],
        "buffer_horizon_s",
    )
    if abs(buffer_horizon - 6.0) > 1.0e-12:
        raise ValueError("formal fixed-lag fixture must retain a 6 second window")
    delay = _non_negative_float(payload["arrival_delay_s"], "arrival_delay_s")
    sweep_count = _positive_int(
        payload["timed_replay_sweep_count"],
        "timed_replay_sweep_count",
    )
    if int(payload["online_truth_use_count"]) != 0:
        raise ValueError("online truth use must remain zero")
    return {
        **payload,
        "source_path": str(path),
        "source_sha256": _sha256_file(path),
        "target_count": target_count,
        "resource_count": resource_count,
        "recon_node_count": recon_node_count,
        "buffer_horizon_s": buffer_horizon,
        "measurement_timestamps_s": timestamps,
        "arrival_delay_s": delay,
        "timed_replay_sweep_count": sweep_count,
        "online_truth_use_count": 0,
    }


def benchmark_replay_prefix_summary(
    *,
    fixture_path: str | Path = DEFAULT_REPLAY_PREFIX_SUMMARY_FIXTURE,
    paired_run_count: int = 7,
    warmup_pair_count: int = 1,
    development_target_count: int | None = None,
    development_replay_sweep_count: int | None = None,
) -> dict[str, Any]:
    """Run alternating fresh-process-state pairs on one frozen workload."""

    if paired_run_count < REPLAY_PREFIX_SUMMARY_MINIMUM_PAIRED_RUN_COUNT:
        raise ValueError(
            "paired_run_count must be at least "
            f"{REPLAY_PREFIX_SUMMARY_MINIMUM_PAIRED_RUN_COUNT}"
        )
    if warmup_pair_count < 0:
        raise ValueError("warmup_pair_count must be non-negative")
    fixture = load_replay_prefix_summary_fixture(fixture_path)
    target_count = fixture["target_count"]
    replay_sweep_count = fixture["timed_replay_sweep_count"]
    frozen_fixture_compliant = True
    if development_target_count is not None:
        target_count = _positive_int(
            development_target_count,
            "development_target_count",
        )
        if target_count > fixture["target_count"]:
            raise ValueError(
                "development_target_count must not exceed the frozen fixture"
            )
        frozen_fixture_compliant = False
    if development_replay_sweep_count is not None:
        replay_sweep_count = _positive_int(
            development_replay_sweep_count,
            "development_replay_sweep_count",
        )
        frozen_fixture_compliant = False

    workload = _build_workload(
        fixture,
        target_count=target_count,
    )
    workload_sha256 = _json_sha256(
        [
            {
                "observation_id": item.observation_id,
                "sensor_id": item.sensor_id,
                "modality": item.modality,
                "measurement_timestamp": item.measurement_timestamp,
                "arrival_timestamp": item.arrival_timestamp,
                "measurement": item.measurement,
                "covariance": item.covariance,
                "metadata": item.metadata,
            }
            for scan in workload
            for item in scan
        ]
    )

    for warmup_index in range(warmup_pair_count):
        selectors = (
            REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
            REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
        )
        if warmup_index % 2:
            selectors = tuple(reversed(selectors))
        for selector in selectors:
            _run_fresh_variant(
                workload,
                fixture,
                selector=selector,
                replay_sweep_count=replay_sweep_count,
            )

    pairs: list[dict[str, Any]] = []
    for pair_index in range(paired_run_count):
        selectors = (
            (
                REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
                REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
            )
            if pair_index % 2 == 0
            else (
                REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
                REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
            )
        )
        runs = {
            selector: _run_fresh_variant(
                workload,
                fixture,
                selector=selector,
                replay_sweep_count=replay_sweep_count,
            )
            for selector in selectors
        }
        reference = runs[REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR]
        candidate = runs[REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR]
        semantic_checks = _semantic_equivalence_checks(reference, candidate)
        reference_time = float(reference["timed_replay_wall_time_s"])
        candidate_time = float(candidate["timed_replay_wall_time_s"])
        pairs.append(
            {
                "pair_index": pair_index,
                "execution_order": list(selectors),
                "reference": reference,
                "candidate": candidate,
                "candidate_minus_reference_s": candidate_time - reference_time,
                "improvement_fraction": (
                    1.0 - candidate_time / reference_time
                ),
                "candidate_faster": candidate_time < reference_time,
                "semantic_checks": semantic_checks,
                "all_semantic_checks_passed": all(
                    semantic_checks.values()
                ),
            }
        )

    reference_times = [
        float(item["reference"]["timed_replay_wall_time_s"])
        for item in pairs
    ]
    candidate_times = [
        float(item["candidate"]["timed_replay_wall_time_s"])
        for item in pairs
    ]
    paired_differences = [
        candidate - reference
        for reference, candidate in zip(reference_times, candidate_times)
    ]
    reference_median = float(median(reference_times))
    candidate_median = float(median(candidate_times))
    median_improvement = 1.0 - candidate_median / reference_median
    candidate_faster_count = sum(
        candidate < reference
        for reference, candidate in zip(reference_times, candidate_times)
    )
    candidate_faster_fraction = candidate_faster_count / paired_run_count
    bootstrap = _paired_mean_difference_bootstrap(paired_differences)
    all_semantically_equal = all(
        item["all_semantic_checks_passed"] for item in pairs
    )
    diagnostics_exercised = all(
        int(
            item["candidate"]["candidate_diagnostics_delta"][
                "operation_counts"
            ].get("summary_hit_count", 0)
        )
        > 0
        for item in pairs
    )
    acceptance = {
        "frozen_200v200_fixture_used": frozen_fixture_compliant,
        "paired_run_count_at_least_five": (
            paired_run_count
            >= REPLAY_PREFIX_SUMMARY_MINIMUM_PAIRED_RUN_COUNT
        ),
        "all_semantic_checks_passed": all_semantically_equal,
        "candidate_summary_hits_exercised": diagnostics_exercised,
        "candidate_faster_fraction_at_least_80_percent": (
            candidate_faster_fraction
            >= REPLAY_PREFIX_SUMMARY_MINIMUM_CANDIDATE_FASTER_FRACTION
        ),
        "median_improvement_at_least_5_percent": (
            median_improvement
            >= REPLAY_PREFIX_SUMMARY_MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
        ),
        "paired_bootstrap_upper_bound_below_zero": (
            bootstrap["ci95_upper_s"] < 0.0
        ),
    }
    module_microbenchmark_passed = all(acceptance.values())
    return {
        "schema_version": REPLAY_PREFIX_SUMMARY_PERFORMANCE_SCHEMA_VERSION,
        "date": "2026-07-25",
        "machine": _machine_summary(),
        "source_identity": _source_identity(),
        "fixture": {
            key: value
            for key, value in fixture.items()
            if key != "notes"
        },
        "workload": {
            "generated_observation_sha256": workload_sha256,
            "target_count": target_count,
            "resource_count": fixture["resource_count"],
            "recon_node_count": fixture["recon_node_count"],
            "scan_count": len(workload),
            "observation_count": sum(len(scan) for scan in workload),
            "replay_sweep_count": replay_sweep_count,
            "frozen_fixture_compliant": frozen_fixture_compliant,
            "online_truth_use_count": 0,
        },
        "protocol": {
            "paired_run_count": paired_run_count,
            "warmup_pair_count": warmup_pair_count,
            "fresh_adapter_per_arm": True,
            "same_imported_source_state_per_arm": True,
            "same_input_per_pair": True,
            "alternating_execution_order": True,
            "timed_scope": (
                "five_complete_fixed_lag_replay_sweeps_plus_one_public_"
                "consistency_evidence_materialization"
                if replay_sweep_count == 5
                else (
                    f"{replay_sweep_count}_complete_fixed_lag_replay_sweeps_"
                    "plus_one_public_consistency_evidence_materialization"
                )
            ),
            "setup_association_excluded_from_timed_scope": True,
            "bootstrap_seed": REPLAY_PREFIX_SUMMARY_BOOTSTRAP_SEED,
            "bootstrap_resample_count": (
                REPLAY_PREFIX_SUMMARY_BOOTSTRAP_RESAMPLE_COUNT
            ),
            "reference_selector": REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
            "candidate_selector": REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
        },
        "pairs": pairs,
        "comparison": {
            "reference_times_s": reference_times,
            "candidate_times_s": candidate_times,
            "paired_differences_s": paired_differences,
            "reference_median_s": reference_median,
            "candidate_median_s": candidate_median,
            "median_improvement_fraction": median_improvement,
            "candidate_faster_count": candidate_faster_count,
            "candidate_faster_fraction": candidate_faster_fraction,
            "paired_mean_difference_bootstrap": bootstrap,
        },
        "acceptance_thresholds": {
            "minimum_paired_run_count": (
                REPLAY_PREFIX_SUMMARY_MINIMUM_PAIRED_RUN_COUNT
            ),
            "minimum_candidate_faster_fraction": (
                REPLAY_PREFIX_SUMMARY_MINIMUM_CANDIDATE_FASTER_FRACTION
            ),
            "minimum_median_improvement_fraction": (
                REPLAY_PREFIX_SUMMARY_MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
            ),
            "maximum_bootstrap_ci95_upper_s": 0.0,
            "all_semantic_checks_required": True,
        },
        "acceptance": acceptance,
        "module_microbenchmark_passed": module_microbenchmark_passed,
        "recommendation": (
            "eligible_for_main_formal_matrix_review"
            if module_microbenchmark_passed
            else "retain_default_off_and_do_not_enter_formal_matrix"
        ),
        "main_default_promotion_claimed": False,
        "airsim_or_full_stack_evidence_claimed": False,
    }


def render_replay_prefix_summary_report_cn(report: Mapping[str, Any]) -> str:
    comparison = report["comparison"]
    bootstrap = comparison["paired_mean_difference_bootstrap"]
    workload = report["workload"]
    lines = [
        "# D1 固定滞后回放前缀累计摘要微基准",
        "",
        "## 结论",
        "",
        (
            f"模块微基准判定为 "
            f"`{'通过' if report['module_microbenchmark_passed'] else '未通过'}`。"
            "该结论只决定是否建议 main 评审新的正式矩阵，不构成主线默认晋升。"
        ),
        "",
        "## 冻结输入",
        "",
        (
            f"- Git HEAD：`{report['source_identity']['git_head']}`；"
            f"源码组合摘要："
            f"`{report['source_identity']['combined_source_sha256']}`。"
        ),
        (
            f"- fixture：`{report['fixture']['fixture_id']}`，SHA-256 "
            f"`{report['fixture']['source_sha256']}`。"
        ),
        (
            f"- 规模：目标 `{workload['target_count']}`、资源 "
            f"`{workload['resource_count']}`、侦察节点 "
            f"`{workload['recon_node_count']}`。"
        ),
        (
            f"- 扫描 `{workload['scan_count']}`，观测 "
            f"`{workload['observation_count']}`，每个 arm 重复完整回放 "
            f"`{workload['replay_sweep_count']}` 轮。"
        ),
        (
            f"- 生成观测摘要：`{workload['generated_observation_sha256']}`；"
            "online truth use=`0`。"
        ),
        "",
        "## 配对结果",
        "",
        "| Pair | Reference/s | Candidate/s | Candidate-Reference/s | 改善 | 语义 |",
        "| ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["pairs"]:
        lines.append(
            "| {pair} | {reference:.9f} | {candidate:.9f} | {difference:.9f} | "
            "{improvement:.3f}% | {semantic} |".format(
                pair=item["pair_index"],
                reference=item["reference"]["timed_replay_wall_time_s"],
                candidate=item["candidate"]["timed_replay_wall_time_s"],
                difference=item["candidate_minus_reference_s"],
                improvement=100.0 * item["improvement_fraction"],
                semantic=(
                    "通过" if item["all_semantic_checks_passed"] else "失败"
                ),
            )
        )
    lines.extend(
        [
            "",
            (
                f"Reference 中位数 `{comparison['reference_median_s']:.9f} s`，"
                f"candidate 中位数 `{comparison['candidate_median_s']:.9f} s`，"
                f"中位改善 `{100.0 * comparison['median_improvement_fraction']:.3f}%`。"
            ),
            (
                f"Candidate 更快 `{comparison['candidate_faster_count']}/"
                f"{report['protocol']['paired_run_count']}`；配对均值差 bootstrap "
                f"95% 区间为 `[{bootstrap['ci95_lower_s']:.9f}, "
                f"{bootstrap['ci95_upper_s']:.9f}] s`。"
            ),
            "",
            "## 等价性",
            "",
            (
                "每一对均分别核对回放后验状态、协方差、归一化创新平方序列、"
                "门控观测 ID、一致性证据、既有操作计数、双时间戳与门控元数据、"
                "公开 GlobalTrack。候选新增诊断计数不进入既有操作计数等价比较。"
            ),
            "",
            "## 限制",
            "",
            (
                "本结果是 D1 冻结合成观测微基准。尚未执行 main 同提交的短时/长时"
                "正式矩阵，也不包含 AirSim、系统实时倍率、目标硬件或实飞证据。"
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def write_replay_prefix_summary_report(
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
            _canonical(report),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_destination.write_text(
        render_replay_prefix_summary_report_cn(report),
        encoding="utf-8",
    )


def _build_workload(
    fixture: Mapping[str, Any],
    *,
    target_count: int,
) -> tuple[tuple[Any, ...], ...]:
    scans = []
    delay = float(fixture["arrival_delay_s"])
    for scan_index, timestamp in enumerate(
        fixture["measurement_timestamps_s"]
    ):
        observations = _radar_scan(
            target_count,
            float(timestamp),
            f"replay-prefix-frozen-{scan_index:02d}",
        )
        arrival_timestamp = float(timestamp) + delay
        for observation in observations:
            observation.arrival_timestamp = arrival_timestamp
            observation.metadata["fixture_id"] = fixture["fixture_id"]
            observation.metadata["fixture_schema_version"] = (
                fixture["schema_version"]
            )
        scans.append(observations)
    return tuple(scans)


def _run_fresh_variant(
    workload: Sequence[Sequence[Any]],
    fixture: Mapping[str, Any],
    *,
    selector: str,
    replay_sweep_count: int,
) -> dict[str, Any]:
    fresh_workload = copy.deepcopy(workload)
    adapter = Scalable3DFusionAdapter(
        association_gate=40.0,
        buffer_horizon=float(fixture["buffer_horizon_s"]),
        replay_prefix_summary=selector,
    )
    setup_started = perf_counter()
    for scan in fresh_workload:
        adapter.process_scan_batch(scan, materialize_tracks=False)
    setup_wall_time_s = perf_counter() - setup_started
    adapter.consistency_evidence_records()
    diagnostics_before = adapter.replay_prefix_summary_diagnostics()
    context = _BatchProcessingContext()
    replay_outputs: dict[str, tuple[Any, ...]] = {}
    timed_started = perf_counter()
    adapter._batch_context = context
    try:
        for _ in range(replay_sweep_count):
            for track_id in sorted(adapter.tracks):
                record = adapter.tracks[track_id]
                state, nises, gated_ids = adapter._capture_replay_record(
                    record,
                    adapter.current_time,
                )
                replay_outputs[track_id] = (
                    state.state.copy(),
                    state.covariance.copy(),
                    float(state.timestamp),
                    tuple(float(item) for item in nises),
                    tuple(gated_ids),
                )
        evidence = adapter.consistency_evidence_records()
    finally:
        adapter._batch_context = None
    timed_replay_wall_time_s = perf_counter() - timed_started
    tracks = adapter.global_tracks()
    diagnostics_after = adapter.replay_prefix_summary_diagnostics()
    operation_counts = _batch_operation_counts(context)
    record_payload = _record_semantics(adapter)
    return {
        "selector": selector,
        "setup_wall_time_s": setup_wall_time_s,
        "timed_replay_wall_time_s": timed_replay_wall_time_s,
        "track_count": len(adapter.tracks),
        "replay_output_count": len(replay_outputs),
        "posterior_state_sha256": _json_sha256(
            {
                track_id: payload[0]
                for track_id, payload in replay_outputs.items()
            }
        ),
        "posterior_covariance_sha256": _json_sha256(
            {
                track_id: payload[1]
                for track_id, payload in replay_outputs.items()
            }
        ),
        "posterior_timestamp_sha256": _json_sha256(
            {
                track_id: payload[2]
                for track_id, payload in replay_outputs.items()
            }
        ),
        "nis_sha256": _json_sha256(
            {
                track_id: payload[3]
                for track_id, payload in replay_outputs.items()
            }
        ),
        "gated_observation_ids_sha256": _json_sha256(
            {
                track_id: payload[4]
                for track_id, payload in replay_outputs.items()
            }
        ),
        "consistency_evidence_sha256": _json_sha256(
            [item.to_dict() for item in evidence]
        ),
        "operation_counts": operation_counts,
        "operation_counts_sha256": _json_sha256(operation_counts),
        "global_tracks_sha256": _json_sha256(
            [item.to_dict() for item in tracks]
        ),
        "record_gate_and_timestamp_metadata_sha256": _json_sha256(
            record_payload["gate_and_timestamp_metadata"]
        ),
        "checkpoint_semantics_sha256": _json_sha256(
            record_payload["checkpoints"]
        ),
        "candidate_diagnostics_delta": _diagnostics_delta(
            diagnostics_before,
            diagnostics_after,
        ),
    }


def _record_semantics(adapter: Scalable3DFusionAdapter) -> dict[str, Any]:
    checkpoints = {}
    gate_and_timestamp_metadata = {}
    for track_id, record in sorted(adapter.tracks.items()):
        checkpoints[track_id] = [
            {
                "observation_id": item.observation_id,
                "sort_key": item.sort_key,
                "posterior_state": item.posterior.state,
                "posterior_covariance": item.posterior.covariance,
                "posterior_timestamp": item.posterior.timestamp,
                "nis": item.nis,
                "gated": item.gated,
            }
            for item in record.replay_checkpoints
        ]
        gate_and_timestamp_metadata[track_id] = {
            "observation_timestamps": [
                {
                    "observation_id": item.observation_id,
                    "measurement_timestamp": item.measurement_timestamp,
                    "arrival_timestamp": item.arrival_timestamp,
                    "filter_innovation_gate_chi2": item.metadata.get(
                        "filter_innovation_gate_chi2"
                    ),
                }
                for item in record.observations
            ],
            "latest_replay_innovation_count": record.metadata.get(
                "latest_replay_innovation_count"
            ),
            "latest_replay_filter_update_count": record.metadata.get(
                "latest_replay_filter_update_count"
            ),
            "latest_replay_innovation_gate_rejection_count": (
                record.metadata.get(
                    "latest_replay_innovation_gate_rejection_count"
                )
            ),
            "latest_replay_innovation_gate_rejected_observation_ids": (
                record.metadata.get(
                    "latest_replay_innovation_gate_rejected_observation_ids"
                )
            ),
        }
    return {
        "checkpoints": checkpoints,
        "gate_and_timestamp_metadata": gate_and_timestamp_metadata,
    }


def _batch_operation_counts(context: _BatchProcessingContext) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for item in fields(context):
        value = getattr(context, item.name)
        if isinstance(value, bool):
            counts[item.name] = value
        elif isinstance(value, int):
            counts[item.name] = int(value)
    counts["association_modality_counts"] = {
        modality: dict(sorted(modality_counts.items()))
        for modality, modality_counts in sorted(
            context.association_modality_counts.items()
        )
    }
    return counts


def _semantic_equivalence_checks(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, bool]:
    return {
        "posterior_state_exact": (
            candidate["posterior_state_sha256"]
            == reference["posterior_state_sha256"]
        ),
        "posterior_covariance_exact": (
            candidate["posterior_covariance_sha256"]
            == reference["posterior_covariance_sha256"]
        ),
        "posterior_timestamp_exact": (
            candidate["posterior_timestamp_sha256"]
            == reference["posterior_timestamp_sha256"]
        ),
        "nis_sequence_exact": (
            candidate["nis_sha256"] == reference["nis_sha256"]
        ),
        "gated_observation_ids_exact": (
            candidate["gated_observation_ids_sha256"]
            == reference["gated_observation_ids_sha256"]
        ),
        "consistency_evidence_exact": (
            candidate["consistency_evidence_sha256"]
            == reference["consistency_evidence_sha256"]
        ),
        "existing_operation_counts_exact": (
            candidate["operation_counts_sha256"]
            == reference["operation_counts_sha256"]
        ),
        "public_global_tracks_exact": (
            candidate["global_tracks_sha256"]
            == reference["global_tracks_sha256"]
        ),
        "dual_timestamps_and_gate_metadata_exact": (
            candidate["record_gate_and_timestamp_metadata_sha256"]
            == reference["record_gate_and_timestamp_metadata_sha256"]
        ),
        "checkpoint_semantics_exact": (
            candidate["checkpoint_semantics_sha256"]
            == reference["checkpoint_semantics_sha256"]
        ),
    }


def _diagnostics_delta(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    before_counts = before["operation_counts"]
    after_counts = after["operation_counts"]
    operation_counts = {
        key: int(after_counts.get(key, 0)) - int(before_counts.get(key, 0))
        for key in sorted(set(before_counts) | set(after_counts))
    }
    before_reasons = before["fallback_reasons"]
    after_reasons = after["fallback_reasons"]
    fallback_reasons = {
        key: int(after_reasons.get(key, 0)) - int(before_reasons.get(key, 0))
        for key in sorted(set(before_reasons) | set(after_reasons))
        if int(after_reasons.get(key, 0)) - int(before_reasons.get(key, 0))
    }
    return {
        "operation_counts": operation_counts,
        "fallback_reasons": fallback_reasons,
        "pending_consistency_ledger_count": int(
            after["pending_consistency_ledger_count"]
        ),
    }


def _paired_mean_difference_bootstrap(
    paired_differences: Sequence[float],
) -> dict[str, Any]:
    values = np.asarray(paired_differences, dtype=float)
    if values.ndim != 1 or values.size < 1 or not np.isfinite(values).all():
        raise ValueError("paired differences must be a finite one-dimensional array")
    rng = np.random.default_rng(REPLAY_PREFIX_SUMMARY_BOOTSTRAP_SEED)
    indices = rng.integers(
        0,
        values.size,
        size=(
            REPLAY_PREFIX_SUMMARY_BOOTSTRAP_RESAMPLE_COUNT,
            values.size,
        ),
    )
    means = values[indices].mean(axis=1)
    lower, upper = np.quantile(means, [0.025, 0.975])
    return {
        "statistic": "paired_mean_candidate_minus_reference_s",
        "observed_mean_s": float(values.mean()),
        "ci95_lower_s": float(lower),
        "ci95_upper_s": float(upper),
        "seed": REPLAY_PREFIX_SUMMARY_BOOTSTRAP_SEED,
        "resample_count": REPLAY_PREFIX_SUMMARY_BOOTSTRAP_RESAMPLE_COUNT,
    }


def _machine_summary() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "numpy": np.__version__,
    }


def _source_identity() -> dict[str, Any]:
    module_root = Path(__file__).resolve().parents[2]
    repo_root = module_root.parents[1]
    source_files = (
        module_root / "src" / "d1_sensor_fusion" / "fusion.py",
        Path(__file__).resolve(),
        DEFAULT_REPLAY_PREFIX_SUMMARY_FIXTURE,
    )
    git_head = None
    try:
        completed = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        git_head = completed.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        git_head = None
    file_hashes = {
        str(path.relative_to(repo_root)): _sha256_file(path)
        for path in source_files
    }
    return {
        "git_head": git_head,
        "source_file_sha256": file_hashes,
        "combined_source_sha256": _json_sha256(file_hashes),
        "reference_and_candidate_share_imported_source": True,
        "working_tree_commit_claimed": False,
    }


def _json_sha256(value: Any) -> str:
    payload = json.dumps(
        _canonical(value),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _canonical(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _canonical(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    result = int(value)
    if result < 1 or float(result) != float(value):
        raise ValueError(f"{name} must be a positive integer")
    return result


def _finite_float(value: Any, name: str) -> float:
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_float(value: Any, name: str) -> float:
    result = _finite_float(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _non_negative_float(value: Any, name: str) -> float:
    result = _finite_float(value, name)
    if result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return result
