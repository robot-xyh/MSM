from __future__ import annotations

import argparse
import cProfile
import gc
import json
import os
from pathlib import Path
import pstats
import resource
import subprocess
import sys
import tempfile
from time import perf_counter
from typing import Any, Mapping, Sequence

import numpy as np

from .consistency_evidence import ConsistencySourceProvenance
from .fusion import (
    GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_IMPLEMENTATION_ID,
    GLOBAL_TRACK_MATERIALIZATION_REFERENCE_IMPLEMENTATION_ID,
)
from .long_duration_performance import (
    _internal_posterior_snapshot,
    _json_sha256,
)
from .scalable_3d import Scalable3DFusionAdapter
from .scan_input import ScanInputOrganizer, SensorScanFrame
from .tail_latency_performance import load_frozen_sensor_frames


GLOBAL_TRACK_MATERIALIZATION_PERFORMANCE_SCHEMA_VERSION = (
    "d1.global_track_materialization_performance.v1"
)
GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR = "per_track_a95_summary_v1"
GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR = "batched_a95_summary_v1"
GLOBAL_TRACK_MATERIALIZATION_MINIMUM_PAIRED_RUN_COUNT = 7
GLOBAL_TRACK_MATERIALIZATION_MINIMUM_FASTER_FRACTION = 0.80
GLOBAL_TRACK_MATERIALIZATION_MINIMUM_MEDIAN_IMPROVEMENT_PERCENT = 10.0
GLOBAL_TRACK_MATERIALIZATION_BOOTSTRAP_RESAMPLE_COUNT = 20_000
GLOBAL_TRACK_MATERIALIZATION_BOOTSTRAP_SEED = 20260801

_SELECTORS = frozenset(
    {
        GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR,
        GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR,
    }
)
_PROFILE_FUNCTIONS = (
    "process_scan_batch",
    "global_tracks",
    "_to_global_track",
    "_batched_global_track_a95_values",
    "covariance_a95",
    "_track_publication_context",
    "eigvalsh",
)
_OPTIMIZATION_OPERATION_FIELDS = frozenset(
    {
        "batched_a95_eigvalsh_call_count",
        "batched_a95_summary_build_count",
        "batched_a95_summary_matrix_count",
        "batched_a95_summary_reuse_count",
        "per_track_a95_summary_call_count",
    }
)
_FORBIDDEN_ONLINE_IDENTITY_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "ground_truth",
        "ground_truth_id",
        "object_id",
        "object_name",
        "target_id",
        "target_name",
        "truth",
        "truth_id",
        "truth_label",
    }
)


class _TimedScalable3DFusionAdapter(Scalable3DFusionAdapter):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.global_track_materialization_samples_s: list[float] = []

    def global_tracks(self) -> list[Any]:
        started = perf_counter()
        result = super().global_tracks()
        self.global_track_materialization_samples_s.append(
            perf_counter() - started
        )
        return result


def run_global_track_materialization_worker(
    source: str | Path,
    *,
    implementation: str,
    profile_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run one isolated arm against an immutable, identity-free replay."""

    selector = _validated_selector(implementation)
    frames, input_summary = load_frozen_sensor_frames(source)
    organizer = ScanInputOrganizer()
    adapter = _TimedScalable3DFusionAdapter(
        immutable_shared_publication_metadata=True,
        batched_global_track_a95_summary=(
            selector == GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR
        ),
    )
    profiler = cProfile.Profile() if profile_path is not None else None
    scan_input_samples_s: list[float] = []
    fusion_samples_s: list[float] = []
    scan_input_result_sha256: list[str] = []
    posterior_sha256: list[str] = []
    nis_gate_sha256: list[str] = []
    operation_snapshot_sha256: list[str] = []
    publication_payload_sha256: list[str] = []
    publication_track_counts: list[int] = []
    final_tracks: tuple[Any, ...] = ()

    def consume(scans: Sequence[SensorScanFrame]) -> None:
        nonlocal final_tracks
        group = tuple(scans)
        for scan_index, scan in enumerate(group):
            fusion_timestamp = max(
                float(adapter.current_time),
                float(scan.arrival_timestamp),
            )
            next_timestamp = (
                None
                if scan_index + 1 == len(group)
                else max(
                    fusion_timestamp,
                    float(group[scan_index + 1].arrival_timestamp),
                )
            )
            materialize_tracks = bool(
                next_timestamp is None
                or next_timestamp > fusion_timestamp + 1.0e-9
            )
            started = perf_counter()
            if profiler is not None:
                profiler.enable()
            result = adapter.process_scan_batch(
                scan.observations,
                materialize_tracks=materialize_tracks,
            )
            if profiler is not None:
                profiler.disable()
            fusion_samples_s.append(perf_counter() - started)

            posterior_sha256.append(
                _json_sha256(_internal_posterior_snapshot(adapter))
            )
            evidence = adapter.consistency_evidence_snapshot()
            nis_gate_sha256.append(
                _json_sha256(
                    [
                        {
                            "observation_id": item.observation_id,
                            "source_lineage": item.source_lineage,
                            "nis": item.nis,
                            "gate_threshold": item.gate_threshold,
                            "gate_decision": item.gate_decision,
                            "accepted": item.accepted,
                            "source_global_track_id": (
                                item.source_global_track_id
                            ),
                        }
                        for item in evidence
                    ]
                )
            )
            operation_snapshot_sha256.append(
                _json_sha256(result.summary.to_dict())
            )
            if result.tracks_materialized:
                payload = [item.to_dict() for item in result.tracks]
                publication_payload_sha256.append(_json_sha256(payload))
                publication_track_counts.append(len(payload))
                final_tracks = tuple(result.tracks)

    wall_started = perf_counter()
    for frame in frames:
        started = perf_counter()
        result = organizer.ingest(frame)
        scan_input_samples_s.append(perf_counter() - started)
        scan_input_result_sha256.append(_json_sha256(result.to_dict()))
        consume(result.released_scans)
    started = perf_counter()
    tail = organizer.close()
    scan_input_samples_s.append(perf_counter() - started)
    scan_input_result_sha256.append(_json_sha256(tail.to_dict()))
    consume(tail.released_scans)
    module_pipeline_wall_s = perf_counter() - wall_started

    if not final_tracks:
        raise RuntimeError("frozen replay produced no materialized GlobalTrack payload")

    source_digest = str(input_summary["source_sha256"])
    if not source_digest.startswith("sha256:"):
        source_digest = "sha256:" + source_digest
    config_digest = _json_sha256(
        {
            "benchmark_schema": (
                GLOBAL_TRACK_MATERIALIZATION_PERFORMANCE_SCHEMA_VERSION
            ),
            "fusion_semantics": "unchanged_reference_semantics",
            "immutable_shared_publication_metadata": True,
            "scan_input": organizer.execution_config(),
        }
    )
    consistency_export = adapter.export_consistency_evidence(
        ConsistencySourceProvenance(
            scenario_id="d1-global-track-materialization-development-fixture",
            scenario_version="v1",
            run_id="frozen-replay",
            seed=42000,
            producer_id="d1_sensor_fusion",
            producer_version="global-track-materialization-ab-v1",
            source_schema_version="scalable3d-observation-v1",
            source_digest=source_digest,
            config_digest=config_digest,
        )
    ).to_dict()
    final_global_track_export = [item.to_dict() for item in final_tracks]

    profile_summary = None
    if profiler is not None and profile_path is not None:
        destination = Path(profile_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(destination))
        profile_summary = _profile_summary(destination)

    publication_diagnostics = adapter.publication_materialization_diagnostics()
    return {
        "schema_version": GLOBAL_TRACK_MATERIALIZATION_PERFORMANCE_SCHEMA_VERSION,
        "worker_pid": os.getpid(),
        "fresh_process": True,
        "implementation": selector,
        "implementation_id": publication_diagnostics[
            "global_track_materialization_implementation_id"
        ],
        "candidate_enabled": bool(adapter.batched_global_track_a95_summary),
        "candidate_default_enabled": bool(
            Scalable3DFusionAdapter().batched_global_track_a95_summary
        ),
        "input": dict(input_summary),
        "workload": {
            "scan_count": len(posterior_sha256),
            "observation_count": int(input_summary["input_observation_count"]),
            "publication_count": len(publication_payload_sha256),
            "materialized_track_count": int(
                sum(publication_track_counts)
            ),
            "final_track_count": len(final_tracks),
        },
        "timing": {
            "global_track_materialization": _timing_summary(
                adapter.global_track_materialization_samples_s
            ),
            "fusion": _timing_summary(fusion_samples_s),
            "scan_input": _timing_summary(scan_input_samples_s),
            "module_pipeline_wall_s": float(module_pipeline_wall_s),
        },
        "rss": {
            "peak_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "source": "resource.RUSAGE_SELF.ru_maxrss_linux_kib",
        },
        "semantic_evidence": {
            "scan_input_result_stream_sha256": _json_sha256(
                scan_input_result_sha256
            ),
            "per_scan_posterior_covariance_lineage_level_sha256": (
                _json_sha256(posterior_sha256)
            ),
            "per_scan_nis_gate_id_sha256": _json_sha256(nis_gate_sha256),
            "per_scan_operation_count_sha256": _json_sha256(
                operation_snapshot_sha256
            ),
            "publication_payload_stream_sha256": _json_sha256(
                publication_payload_sha256
            ),
            "final_global_track_export_sha256": _json_sha256(
                final_global_track_export
            ),
            "final_consistency_evidence_export_sha256": _json_sha256(
                consistency_export
            ),
            "publication_payload_forbidden_identity_key_count": (
                _forbidden_identity_key_count(final_global_track_export)
            ),
            "consistency_export_forbidden_identity_key_count": (
                _forbidden_identity_key_count(consistency_export)
            ),
        },
        "operation_evidence": {
            "fusion": adapter.fusion_performance_diagnostics().to_dict(),
            "scan_input": organizer.performance_diagnostics(),
            "publication": publication_diagnostics,
        },
        "profile": profile_summary,
        "constraints": {
            "fusion_math_changed": False,
            "ekf_or_oosm_changed": False,
            "fixed_lag_changed": False,
            "nis_or_gate_changed": False,
            "dual_timestamps_changed": False,
            "ned_or_covariance_contract_changed": False,
            "lineage_or_quality_bucket_changed": False,
            "global_track_payload_changed": False,
            "global_track_id_write_enabled": False,
            "online_truth_use_count": int(input_summary["online_truth_use_count"]),
            "formal_seed_1000_1019_used": False,
            "formal_r0_used": False,
            "system_realtime_gap_closed": False,
        },
    }


def benchmark_global_track_materialization_candidate(
    source: str | Path,
    *,
    paired_run_count: int = GLOBAL_TRACK_MATERIALIZATION_MINIMUM_PAIRED_RUN_COUNT,
    include_profiles: bool = True,
) -> dict[str, Any]:
    """Run the pre-registered alternating fresh-process module gate."""

    if isinstance(paired_run_count, bool) or int(paired_run_count) < 1:
        raise ValueError("paired_run_count must be a positive integer")
    pair_count = int(paired_run_count)
    source_path = Path(source).resolve()
    profile_results: dict[str, Any] = {}
    if include_profiles:
        for selector in (
            GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR,
            GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR,
        ):
            profile_results[selector] = _run_fresh_worker(
                source_path,
                selector,
                profile=True,
            )

    pairs: list[dict[str, Any]] = []
    run_order: list[str] = []
    for pair_index in range(pair_count):
        order = (
            (
                GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR,
                GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR,
            )
            if pair_index % 2 == 0
            else (
                GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR,
                GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR,
            )
        )
        arms: dict[str, dict[str, Any]] = {}
        for selector in order:
            arms[selector] = _run_fresh_worker(source_path, selector)
            run_order.append(selector)
        comparison = compare_global_track_materialization_workers(
            arms[GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR],
            arms[GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR],
        )
        pairs.append(
            {
                "pair_index": pair_index,
                "execution_order": list(order),
                "reference": arms[
                    GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR
                ],
                "candidate": arms[
                    GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR
                ],
                "comparison": comparison,
            }
        )

    aggregate = _aggregate_pairs(pairs)
    acceptance = {
        "paired_run_count_at_least_seven": (
            pair_count >= GLOBAL_TRACK_MATERIALIZATION_MINIMUM_PAIRED_RUN_COUNT
        ),
        "candidate_faster_fraction_at_least_80_percent": (
            aggregate["candidate_faster_fraction"]
            >= GLOBAL_TRACK_MATERIALIZATION_MINIMUM_FASTER_FRACTION
        ),
        "median_module_wall_improvement_at_least_10_percent": (
            aggregate["median_module_wall_improvement_percent"]
            >= GLOBAL_TRACK_MATERIALIZATION_MINIMUM_MEDIAN_IMPROVEMENT_PERCENT
        ),
        "paired_bootstrap_difference_95_percent_upper_below_zero": (
            aggregate["paired_bootstrap_module_wall_difference_s_95_ci"][1]
            < 0.0
        ),
        "semantic_equivalence_all_pairs": all(
            item["comparison"]["semantic_passed"] for item in pairs
        ),
        "operation_conservation_all_pairs": all(
            item["comparison"]["operation_passed"] for item in pairs
        ),
        "candidate_default_off_all_pairs": all(
            not item["candidate"]["candidate_default_enabled"]
            for item in pairs
        ),
        "online_truth_isolated_all_pairs": all(
            item["reference"]["constraints"]["online_truth_use_count"] == 0
            and item["candidate"]["constraints"]["online_truth_use_count"] == 0
            for item in pairs
        ),
        "implementation_identity_exact_all_pairs": all(
            item["reference"]["implementation_id"]
            == GLOBAL_TRACK_MATERIALIZATION_REFERENCE_IMPLEMENTATION_ID
            and item["candidate"]["implementation_id"]
            == GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_IMPLEMENTATION_ID
            for item in pairs
        ),
    }
    passed = all(acceptance.values())
    return {
        "schema_version": GLOBAL_TRACK_MATERIALIZATION_PERFORMANCE_SCHEMA_VERSION,
        "candidate_identity": (
            GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_IMPLEMENTATION_ID
        ),
        "reference_identity": (
            GLOBAL_TRACK_MATERIALIZATION_REFERENCE_IMPLEMENTATION_ID
        ),
        "decision": (
            "module_gate_passed_candidate_remains_default_off_pending_main"
            if passed
            else "module_gate_failed_candidate_rejected_for_main_integration"
        ),
        "passed": passed,
        "preregistered_gate": {
            "minimum_paired_run_count": (
                GLOBAL_TRACK_MATERIALIZATION_MINIMUM_PAIRED_RUN_COUNT
            ),
            "minimum_candidate_faster_fraction": (
                GLOBAL_TRACK_MATERIALIZATION_MINIMUM_FASTER_FRACTION
            ),
            "minimum_median_module_wall_improvement_percent": (
                GLOBAL_TRACK_MATERIALIZATION_MINIMUM_MEDIAN_IMPROVEMENT_PERCENT
            ),
            "bootstrap_resample_count": (
                GLOBAL_TRACK_MATERIALIZATION_BOOTSTRAP_RESAMPLE_COUNT
            ),
            "bootstrap_seed": GLOBAL_TRACK_MATERIALIZATION_BOOTSTRAP_SEED,
            "bootstrap_paired_difference_95_percent_upper_must_be_below_s": 0.0,
            "semantic_pairs_required": pair_count,
            "module_wall_definition": (
                "sum_of_FusionAdapter.global_tracks_elapsed_time_per_fresh_replay"
            ),
        },
        "acceptance": acceptance,
        "input": pairs[0]["reference"]["input"],
        "run_order": run_order,
        "hotspot_selection": _hotspot_selection(profile_results, pairs),
        "profiles": {
            selector: value.get("profile")
            for selector, value in profile_results.items()
        },
        "aggregate": aggregate,
        "pairs": pairs,
        "evidence_boundary": {
            "development_fixture_only": True,
            "formal_seed_1000_1019_used": False,
            "formal_r0_used": False,
            "candidate_promoted_to_default": False,
            "main_or_scalable_integration_modified": False,
            "system_realtime_gap_closed": False,
            "airsim_or_hardware_evidence": False,
        },
    }


def compare_global_track_materialization_workers(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    reference_semantic = reference["semantic_evidence"]
    candidate_semantic = candidate["semantic_evidence"]
    semantic_checks = {
        key: reference_semantic[key] == candidate_semantic[key]
        for key in (
            "scan_input_result_stream_sha256",
            "per_scan_posterior_covariance_lineage_level_sha256",
            "per_scan_nis_gate_id_sha256",
            "per_scan_operation_count_sha256",
            "publication_payload_stream_sha256",
            "final_global_track_export_sha256",
            "final_consistency_evidence_export_sha256",
        )
    }
    semantic_checks.update(
        {
            "publication_payload_online_identity_free": (
                reference_semantic[
                    "publication_payload_forbidden_identity_key_count"
                ]
                == candidate_semantic[
                    "publication_payload_forbidden_identity_key_count"
                ]
                == 0
            ),
            "consistency_export_online_identity_free": (
                reference_semantic[
                    "consistency_export_forbidden_identity_key_count"
                ]
                == candidate_semantic[
                    "consistency_export_forbidden_identity_key_count"
                ]
                == 0
            ),
        }
    )

    reference_operations = reference["operation_evidence"]
    candidate_operations = candidate["operation_evidence"]
    reference_publication = reference_operations["publication"]["operation_counts"]
    candidate_publication = candidate_operations["publication"]["operation_counts"]
    common_reference = {
        key: value
        for key, value in reference_publication.items()
        if key not in _OPTIMIZATION_OPERATION_FIELDS
    }
    common_candidate = {
        key: value
        for key, value in candidate_publication.items()
        if key not in _OPTIMIZATION_OPERATION_FIELDS
    }
    materialized_track_count = int(reference["workload"]["materialized_track_count"])
    nonempty_publication_count = sum(
        1
        for count in reference["workload"].get("publication_track_counts", ())
        if int(count) > 0
    )
    # Older worker payloads do not expose the count list. The candidate's
    # eigensolver counter is itself bounded by total publication count.
    operation_checks = {
        "fusion_operation_counts_equal": (
            reference_operations["fusion"] == candidate_operations["fusion"]
        ),
        "scan_input_operation_counts_equal": (
            reference_operations["scan_input"]
            == candidate_operations["scan_input"]
        ),
        "common_publication_operation_counts_equal": (
            common_reference == common_candidate
        ),
        "reference_scalar_summary_count_complete": (
            int(reference_publication.get("per_track_a95_summary_call_count", 0))
            == materialized_track_count
        ),
        "candidate_scalar_summary_count_zero": (
            int(candidate_publication.get("per_track_a95_summary_call_count", 0))
            == 0
        ),
        "candidate_batched_matrix_count_complete": (
            int(candidate_publication.get("batched_a95_summary_matrix_count", 0))
            == materialized_track_count
        ),
        "candidate_batched_reuse_count_complete": (
            int(candidate_publication.get("batched_a95_summary_reuse_count", 0))
            == materialized_track_count
        ),
        "candidate_batched_eigensolver_count_bounded": (
            0
            < int(
                candidate_publication.get("batched_a95_eigvalsh_call_count", 0)
            )
            <= int(candidate["workload"]["publication_count"])
        ),
        "candidate_batched_build_count_matches_publications": (
            int(candidate_publication.get("batched_a95_summary_build_count", 0))
            == int(candidate["workload"]["publication_count"])
        ),
    }
    del nonempty_publication_count

    reference_wall = float(
        reference["timing"]["global_track_materialization"]["sum_s"]
    )
    candidate_wall = float(
        candidate["timing"]["global_track_materialization"]["sum_s"]
    )
    return {
        "semantic_checks": semantic_checks,
        "semantic_passed": all(semantic_checks.values()),
        "operation_checks": operation_checks,
        "operation_passed": all(operation_checks.values()),
        "module_wall_difference_s": candidate_wall - reference_wall,
        "module_wall_relative_change": (
            (candidate_wall - reference_wall) / reference_wall
        ),
        "candidate_faster": candidate_wall < reference_wall,
    }


def write_global_track_materialization_report(
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
        render_global_track_materialization_report_cn(report),
        encoding="utf-8",
    )


def render_global_track_materialization_report_cn(
    report: Mapping[str, Any],
) -> str:
    aggregate = report["aggregate"]
    hotspot = report["hotspot_selection"]
    input_summary = report["input"]
    acceptance = report["acceptance"]
    lines = [
        "# D1 GlobalTrack 完整物化批量质量摘要候选报告",
        "",
        "## 结论",
        "",
        f"候选 `{report['candidate_identity']}` 的模块门结果为 "
        f"`{'通过' if report['passed'] else '未通过'}`。候选保持默认关闭，"
        "本报告不构成 main 接线或系统实时闭合证据。",
        "",
        f"冻结输入含 {int(input_summary['input_batch_count']):,} 个扫描和 "
        f"{int(input_summary['input_observation_count']):,} 条匿名观测，SHA-256 为 "
        f"`{input_summary['source_sha256']}`。未运行正式 seeds 1000--1019，"
        "未运行正式 R0。",
        "",
        "## 热点选择",
        "",
        f"当前 reference 剖析中，`global_tracks` 累计 "
        f"`{hotspot['reference_global_tracks_profile_cumulative_s']:.6f} s`，"
        f"`_to_global_track` 累计 "
        f"`{hotspot['reference_to_global_track_profile_cumulative_s']:.6f} s`，"
        f"scan-input 墙钟为 `{hotspot['reference_scan_input_wall_s']:.6f} s`。"
        "完整航迹物化是本轮两个允许方向中较大的热点，因此只推进这一身份。",
        "",
        "未剖析的 7 次 reference 中，完整航迹物化和 scan-input 墙钟中位数分别为 "
        f"`{hotspot['reference_unprofiled_global_track_materialization_p50_s']:.6f}` 和 "
        f"`{hotspot['reference_unprofiled_scan_input_p50_s']:.6f} s`。",
        "",
        "候选把同一发布帧内逐航迹执行的二维位置协方差特征值分解合并为一个批量调用。"
        "状态和协方差仍逐航迹复制，完整元数据、双时间戳、谱系、质量分档和编号均保持原格式。",
        "",
        "## 预注册门",
        "",
    ]
    for name, passed in acceptance.items():
        lines.append(f"- `{name}`：`{passed}`")
    lines.extend(
        [
            "",
            "## 性能",
            "",
            f"交替 fresh-process 共 {int(aggregate['paired_run_count'])} 对。候选更快比例为 "
            f"`{aggregate['candidate_faster_fraction']:.6f}`，reference/candidate 模块"
            f"墙钟中位数为 `{aggregate['reference_module_wall']['p50_s']:.6f}/"
            f"{aggregate['candidate_module_wall']['p50_s']:.6f} s`，中位改善 "
            f"`{aggregate['median_module_wall_improvement_percent']:.3f}%`。",
            "",
            "配对模块墙钟差的 bootstrap 95% 区间为 "
            f"`[{aggregate['paired_bootstrap_module_wall_difference_s_95_ci'][0]:.6f}, "
            f"{aggregate['paired_bootstrap_module_wall_difference_s_95_ci'][1]:.6f}] s`。",
            "",
            "| 指标 | Reference | Candidate |",
            "| --- | ---: | ---: |",
            f"| 模块 run P50 / s | {aggregate['reference_module_wall']['p50_s']:.6f} | "
            f"{aggregate['candidate_module_wall']['p50_s']:.6f} |",
            f"| 模块 run P95 / s | {aggregate['reference_module_wall']['p95_s']:.6f} | "
            f"{aggregate['candidate_module_wall']['p95_s']:.6f} |",
            f"| 模块 run max / s | {aggregate['reference_module_wall']['max_s']:.6f} | "
            f"{aggregate['candidate_module_wall']['max_s']:.6f} |",
            f"| 单次发布 P50 / ms | {aggregate['reference_publication_call']['p50_ms']:.6f} | "
            f"{aggregate['candidate_publication_call']['p50_ms']:.6f} |",
            f"| 单次发布 P95 / ms | {aggregate['reference_publication_call']['p95_ms']:.6f} | "
            f"{aggregate['candidate_publication_call']['p95_ms']:.6f} |",
            f"| 单次发布 max / ms | {aggregate['reference_publication_call']['max_ms']:.6f} | "
            f"{aggregate['candidate_publication_call']['max_ms']:.6f} |",
            f"| 全融合 run P50 / s | {aggregate['reference_fusion_wall']['p50_s']:.6f} | "
            f"{aggregate['candidate_fusion_wall']['p50_s']:.6f} |",
            f"| 全融合 run P95 / s | {aggregate['reference_fusion_wall']['p95_s']:.6f} | "
            f"{aggregate['candidate_fusion_wall']['p95_s']:.6f} |",
            f"| 全融合 run max / s | {aggregate['reference_fusion_wall']['max_s']:.6f} | "
            f"{aggregate['candidate_fusion_wall']['max_s']:.6f} |",
            f"| 峰值 RSS P50 / KiB | {aggregate['reference_peak_rss_kib']['p50']:.0f} | "
            f"{aggregate['candidate_peak_rss_kib']['p50']:.0f} |",
            f"| 峰值 RSS P95 / KiB | {aggregate['reference_peak_rss_kib']['p95']:.0f} | "
            f"{aggregate['candidate_peak_rss_kib']['p95']:.0f} |",
            f"| 峰值 RSS max / KiB | {aggregate['reference_peak_rss_kib']['max']:.0f} | "
            f"{aggregate['candidate_peak_rss_kib']['max']:.0f} |",
            "",
            "全融合与 scan-input 墙钟也已记录，但不用于本候选的 10% 模块门。局部物化收益"
            "不能外推为 200 对 200 实时闭合。",
            "",
            "## 语义与工作量",
            "",
            f"逐扫描语义通过 `{aggregate['semantic_pair_pass_count']}/"
            f"{aggregate['paired_run_count']}`，工作量守恒通过 "
            f"`{aggregate['operation_pair_pass_count']}/{aggregate['paired_run_count']}`。"
            "比较范围包含后验、协方差、NIS、门控观测编号、完整 publication payload、"
            "一致性证据、业务操作计数和最终离线导出。",
            "",
            f"逐航迹标量质量摘要从每臂 "
            f"`{int(aggregate['reference_scalar_a95_summary_count']) if 'reference_scalar_a95_summary_count' in aggregate else 0:,}` 次"
            "改为每发布帧一次批量特征值调用；候选仍对每条物化航迹记录一次质量摘要请求和"
            "一次结果复用。在线真值使用和 `global_track_id` 写权限均为 0。",
            "",
            f"每个 fresh arm 执行 `{int(aggregate['global_tracks_call_count']):,}` 次完整发布，"
            f"物化 `{int(aggregate['global_track_metadata_materialization_count']):,}` 条航迹。"
            f"reference 标量摘要 `{int(aggregate['reference_scalar_a95_summary_count']):,}` 次；"
            f"candidate 批量矩阵 `{int(aggregate['candidate_batched_a95_matrix_count']):,}` 个、"
            f"批量特征值调用 `{int(aggregate['candidate_batched_a95_eigvalsh_call_count']):,}` 次。",
            "",
            "## 边界",
            "",
            "- 候选默认关闭，reference 构造行为保持不变。",
            "- 没有改变融合数学、扩展卡尔曼滤波、乱序量测处理、固定滞后、门控或质量门限。",
            "- 没有运行 AirSim、正式 R0、目标硬件或正式 seeds 1000--1019。",
            "- main 是否接线需要独立集成审查和系统级多 seed 验收。",
            "",
        ]
    )
    return "\n".join(lines)


def _aggregate_pairs(pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reference_walls = np.asarray(
        [
            item["reference"]["timing"]["global_track_materialization"][
                "sum_s"
            ]
            for item in pairs
        ],
        dtype=float,
    )
    candidate_walls = np.asarray(
        [
            item["candidate"]["timing"]["global_track_materialization"][
                "sum_s"
            ]
            for item in pairs
        ],
        dtype=float,
    )
    differences = candidate_walls - reference_walls
    relative_changes = differences / reference_walls
    bootstrap_absolute, bootstrap_relative = _paired_bootstrap(
        differences,
        relative_changes,
    )
    reference_calls = [
        value
        for item in pairs
        for value in item["reference"]["timing"][
            "global_track_materialization"
        ]["samples_s"]
    ]
    candidate_calls = [
        value
        for item in pairs
        for value in item["candidate"]["timing"][
            "global_track_materialization"
        ]["samples_s"]
    ]
    reference_rss = [item["reference"]["rss"]["peak_kib"] for item in pairs]
    candidate_rss = [item["candidate"]["rss"]["peak_kib"] for item in pairs]
    reference_fusion_walls = [
        item["reference"]["timing"]["fusion"]["sum_s"] for item in pairs
    ]
    candidate_fusion_walls = [
        item["candidate"]["timing"]["fusion"]["sum_s"] for item in pairs
    ]
    reference_scan_input_walls = [
        item["reference"]["timing"]["scan_input"]["sum_s"] for item in pairs
    ]
    candidate_scan_input_walls = [
        item["candidate"]["timing"]["scan_input"]["sum_s"] for item in pairs
    ]
    reference_pipeline_walls = [
        item["reference"]["timing"]["module_pipeline_wall_s"]
        for item in pairs
    ]
    candidate_pipeline_walls = [
        item["candidate"]["timing"]["module_pipeline_wall_s"]
        for item in pairs
    ]
    first_reference_ops = pairs[0]["reference"]["operation_evidence"][
        "publication"
    ]["operation_counts"]
    first_candidate_ops = pairs[0]["candidate"]["operation_evidence"][
        "publication"
    ]["operation_counts"]
    return {
        "paired_run_count": len(pairs),
        "candidate_faster_count": int(np.count_nonzero(differences < 0.0)),
        "candidate_faster_fraction": float(np.mean(differences < 0.0)),
        "reference_module_wall": _timing_summary(reference_walls),
        "candidate_module_wall": _timing_summary(candidate_walls),
        "median_module_wall_improvement_percent": float(
            100.0
            * (np.median(reference_walls) - np.median(candidate_walls))
            / np.median(reference_walls)
        ),
        "paired_module_wall_difference_s": [
            float(item) for item in differences
        ],
        "paired_relative_change": [float(item) for item in relative_changes],
        "paired_bootstrap_module_wall_difference_s_95_ci": bootstrap_absolute,
        "paired_bootstrap_relative_change_95_ci": bootstrap_relative,
        "reference_publication_call": _millisecond_timing_summary(reference_calls),
        "candidate_publication_call": _millisecond_timing_summary(candidate_calls),
        "reference_fusion_wall": _timing_summary(reference_fusion_walls),
        "candidate_fusion_wall": _timing_summary(candidate_fusion_walls),
        "reference_scan_input_wall": _timing_summary(reference_scan_input_walls),
        "candidate_scan_input_wall": _timing_summary(candidate_scan_input_walls),
        "reference_pipeline_wall": _timing_summary(reference_pipeline_walls),
        "candidate_pipeline_wall": _timing_summary(candidate_pipeline_walls),
        "reference_peak_rss_kib": _numeric_summary(reference_rss),
        "candidate_peak_rss_kib": _numeric_summary(candidate_rss),
        "semantic_pair_pass_count": sum(
            int(item["comparison"]["semantic_passed"]) for item in pairs
        ),
        "operation_pair_pass_count": sum(
            int(item["comparison"]["operation_passed"]) for item in pairs
        ),
        "reference_scalar_a95_summary_count": int(
            first_reference_ops.get("per_track_a95_summary_call_count", 0)
        ),
        "candidate_scalar_a95_summary_count": int(
            first_candidate_ops.get("per_track_a95_summary_call_count", 0)
        ),
        "candidate_batched_a95_matrix_count": int(
            first_candidate_ops.get("batched_a95_summary_matrix_count", 0)
        ),
        "candidate_batched_a95_eigvalsh_call_count": int(
            first_candidate_ops.get("batched_a95_eigvalsh_call_count", 0)
        ),
        "global_tracks_call_count": int(
            first_reference_ops.get("global_tracks_call_count", 0)
        ),
        "global_track_metadata_materialization_count": int(
            first_reference_ops.get(
                "global_track_metadata_materialization_count",
                0,
            )
        ),
    }


def _paired_bootstrap(
    differences: np.ndarray,
    relative_changes: np.ndarray,
) -> tuple[list[float], list[float]]:
    rng = np.random.default_rng(GLOBAL_TRACK_MATERIALIZATION_BOOTSTRAP_SEED)
    indices = rng.integers(
        0,
        len(differences),
        size=(GLOBAL_TRACK_MATERIALIZATION_BOOTSTRAP_RESAMPLE_COUNT, len(differences)),
    )
    absolute_samples = np.mean(differences[indices], axis=1)
    relative_samples = np.mean(relative_changes[indices], axis=1)
    return (
        [float(item) for item in np.percentile(absolute_samples, [2.5, 97.5])],
        [float(item) for item in np.percentile(relative_samples, [2.5, 97.5])],
    )


def _hotspot_selection(
    profiles: Mapping[str, Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reference = profiles.get(GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR)
    if reference is None:
        reference = pairs[0]["reference"]
    selected = (reference.get("profile") or {}).get("selected_functions", {})
    return {
        "selected_hotspot": "complete_global_track_materialization",
        "single_candidate_only": True,
        "reference_global_tracks_profile_cumulative_s": float(
            selected.get("global_tracks", {}).get("cumulative_time_s", 0.0)
        ),
        "reference_to_global_track_profile_cumulative_s": float(
            selected.get("_to_global_track", {}).get("cumulative_time_s", 0.0)
        ),
        "reference_covariance_a95_profile_cumulative_s": float(
            selected.get("covariance_a95", {}).get("cumulative_time_s", 0.0)
        ),
        "reference_scan_input_wall_s": float(
            reference["timing"]["scan_input"]["sum_s"]
        ),
        "reference_unprofiled_global_track_materialization_p50_s": float(
            np.median(
                [
                    item["reference"]["timing"][
                        "global_track_materialization"
                    ]["sum_s"]
                    for item in pairs
                ]
            )
        ),
        "reference_unprofiled_scan_input_p50_s": float(
            np.median(
                [
                    item["reference"]["timing"]["scan_input"]["sum_s"]
                    for item in pairs
                ]
            )
        ),
        "rejected_candidate_identity_reused": False,
        "required_observation_subset_v1_reused": False,
        "fixed_lag_checkpoint_prefix_cumulative_summary_v1_reused": False,
        "association_sparse_prefilter_reused": False,
    }


def _run_fresh_worker(
    source: Path,
    selector: str,
    *,
    profile: bool = False,
) -> dict[str, Any]:
    package_root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        str(package_root)
        if not existing_pythonpath
        else str(package_root) + os.pathsep + existing_pythonpath
    )
    profile_path: Path | None = None
    if profile:
        handle = tempfile.NamedTemporaryFile(
            prefix="d1_global_track_materialization_",
            suffix=".prof",
            delete=False,
        )
        profile_path = Path(handle.name)
        handle.close()
    command = [
        sys.executable,
        "-m",
        "d1_sensor_fusion.global_track_materialization_performance",
        "--worker",
        "--input",
        str(source),
        "--implementation",
        selector,
    ]
    if profile_path is not None:
        command.extend(("--profile-path", str(profile_path)))
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        result = json.loads(completed.stdout)
    finally:
        if profile_path is not None:
            profile_path.unlink(missing_ok=True)
    return result


def _profile_summary(path: Path) -> dict[str, Any]:
    stats = pstats.Stats(str(path))
    selected: dict[str, dict[str, float | int]] = {}
    for (_, _, function_name), values in stats.stats.items():
        if function_name not in _PROFILE_FUNCTIONS:
            continue
        primitive_calls, total_calls, total_time, cumulative_time, _ = values
        current = selected.get(function_name)
        if current is None or float(current["cumulative_time_s"]) < cumulative_time:
            selected[function_name] = {
                "primitive_call_count": int(primitive_calls),
                "total_call_count": int(total_calls),
                "self_time_s": float(total_time),
                "cumulative_time_s": float(cumulative_time),
            }
    return {
        "total_time_s": float(stats.total_tt),
        "selected_functions": selected,
        "timing_used_for_gate": False,
    }


def _timing_summary(values: Sequence[float]) -> dict[str, Any]:
    array = np.asarray(tuple(values), dtype=float)
    if array.size == 0:
        return {
            "sample_count": 0,
            "samples_s": [],
            "sum_s": 0.0,
            "mean_s": 0.0,
            "p50_s": 0.0,
            "p95_s": 0.0,
            "max_s": 0.0,
        }
    return {
        "sample_count": int(array.size),
        "samples_s": [float(item) for item in array],
        "sum_s": float(np.sum(array)),
        "mean_s": float(np.mean(array)),
        "p50_s": float(np.percentile(array, 50.0)),
        "p95_s": float(np.percentile(array, 95.0)),
        "max_s": float(np.max(array)),
    }


def _millisecond_timing_summary(values: Sequence[float]) -> dict[str, Any]:
    array = np.asarray(tuple(values), dtype=float) * 1000.0
    return {
        "sample_count": int(array.size),
        "p50_ms": float(np.percentile(array, 50.0)),
        "p95_ms": float(np.percentile(array, 95.0)),
        "max_ms": float(np.max(array)),
    }


def _numeric_summary(values: Sequence[float]) -> dict[str, float | int]:
    array = np.asarray(tuple(values), dtype=float)
    return {
        "sample_count": int(array.size),
        "p50": float(np.percentile(array, 50.0)),
        "p95": float(np.percentile(array, 95.0)),
        "max": float(np.max(array)),
    }


def _forbidden_identity_key_count(value: Any) -> int:
    if isinstance(value, Mapping):
        count = 0
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            count += int(normalized in _FORBIDDEN_ONLINE_IDENTITY_KEYS)
            count += _forbidden_identity_key_count(nested)
        return count
    if isinstance(value, (list, tuple)):
        return sum(_forbidden_identity_key_count(item) for item in value)
    return 0


def _validated_selector(value: str) -> str:
    selector = str(value).strip()
    if selector not in _SELECTORS:
        raise ValueError(f"implementation must be one of {sorted(_SELECTORS)!r}")
    return selector


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--implementation",
        choices=sorted(_SELECTORS),
        default=GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR,
    )
    parser.add_argument("--profile-path", type=Path)
    args = parser.parse_args()
    if not args.worker:
        raise SystemExit("this module entry point is reserved for fresh workers")
    gc.collect()
    result = run_global_track_materialization_worker(
        args.input,
        implementation=args.implementation,
        profile_path=args.profile_path,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    _main()
