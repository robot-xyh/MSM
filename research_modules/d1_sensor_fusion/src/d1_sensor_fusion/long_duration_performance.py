from __future__ import annotations

import cProfile
from dataclasses import asdict, is_dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import pstats
from statistics import fmean
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from .scalable_3d import Scalable3DFusionAdapter
from .scan_fusion_performance import (
    load_frozen_sensor_scan_release_groups,
    load_frozen_sensor_scans,
)
from .scan_input import SensorScanFrame


LONG_DURATION_PERFORMANCE_SCHEMA_VERSION = "d1.long_duration_performance.v1"
COALESCED_RELEASE_PERFORMANCE_SCHEMA_VERSION = (
    "d1.coalesced_release_performance.v1"
)
CONSISTENCY_COUNTER_REFRESH_PERFORMANCE_SCHEMA_VERSION = (
    "d1.consistency_counter_refresh_performance.v1"
)
COVARIANCE_LIMIT_PERFORMANCE_SCHEMA_VERSION = (
    "d1.covariance_limit_performance.v1"
)
COVARIANCE_LIMIT_SEMANTIC_ONCE_SCHEMA_VERSION = (
    "d1.covariance_limit_semantic_once.v1"
)
COVARIANCE_LIMIT_INTERLEAVED_MAX_SPAN_S = 6.0
FUSED_TRACK_PUBLICATION_AUDIT_SCHEMA_VERSION = (
    "d1.fused_track_publication_audit.v2"
)

_BATCH_OPERATION_FIELDS = (
    "history_replay_count",
    "origin_replay_count",
    "state_cache_hit_count",
    "state_cache_miss_count",
    "finalization_replay_count",
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


def run_long_duration_variant(
    scans: Sequence[SensorScanFrame],
    *,
    variant: str,
    direct_checkpoint_state_queries: bool,
    fixed_lag_checkpoint_suffix_reuse: bool,
    trusted_replay_checkpoint_prefix: bool,
    cached_consistency_prefix_refresh: bool,
    profile_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run one frozen scan sequence while separating fusion and hash time."""

    adapter = Scalable3DFusionAdapter(
        direct_checkpoint_state_queries=direct_checkpoint_state_queries,
        fixed_lag_checkpoint_suffix_reuse=fixed_lag_checkpoint_suffix_reuse,
        trusted_replay_checkpoint_prefix=trusted_replay_checkpoint_prefix,
        cached_consistency_prefix_refresh=cached_consistency_prefix_refresh,
    )
    operation_totals = {name: 0 for name in _BATCH_OPERATION_FIELDS}
    per_scan_semantic_digests: list[str] = []
    per_second: dict[str, dict[str, float | int]] = {}
    process_wall_time_s = 0.0
    semantic_hash_wall_time_s = 0.0
    profiler = cProfile.Profile() if profile_path is not None else None
    result = None

    for scan in scans:
        started = perf_counter()
        if profiler is not None:
            profiler.enable()
        result = adapter.process_scan_batch(scan.observations)
        if profiler is not None:
            profiler.disable()
        elapsed = perf_counter() - started
        process_wall_time_s += elapsed

        hash_started = perf_counter()
        per_scan_semantic_digests.append(_semantic_result_digest(result))
        semantic_hash_wall_time_s += perf_counter() - hash_started

        summary = result.summary.to_dict()
        for name in _BATCH_OPERATION_FIELDS:
            operation_totals[name] += int(summary[name])
        second_key = str(int(float(scan.arrival_timestamp)))
        second = per_second.setdefault(
            second_key,
            {"scan_count": 0, "observation_count": 0, "fusion_wall_time_s": 0.0},
        )
        second["scan_count"] = int(second["scan_count"]) + 1
        second["observation_count"] = int(second["observation_count"]) + len(
            scan.observations
        )
        second["fusion_wall_time_s"] = float(second["fusion_wall_time_s"]) + elapsed

    if result is None:
        raise ValueError("long-duration benchmark requires at least one released scan")

    profile = None
    if profiler is not None:
        destination = Path(profile_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(destination))
        profile = _profile_summary(destination)

    final_tracks = _semantic_track_snapshot(result.tracks)
    evidence = [item.to_dict() for item in adapter.consistency_evidence_records()]
    return {
        "variant": str(variant),
        "direct_checkpoint_state_queries": bool(direct_checkpoint_state_queries),
        "fixed_lag_checkpoint_suffix_reuse": bool(
            fixed_lag_checkpoint_suffix_reuse
        ),
        "trusted_replay_checkpoint_prefix": bool(
            trusted_replay_checkpoint_prefix
        ),
        "cached_consistency_prefix_refresh": bool(
            cached_consistency_prefix_refresh
        ),
        "scan_count": len(scans),
        "track_count": len(result.tracks),
        "process_wall_time_s": process_wall_time_s,
        "semantic_hash_wall_time_s": semantic_hash_wall_time_s,
        "operation_totals": operation_totals,
        "cumulative_diagnostics": (
            adapter.fusion_performance_diagnostics().to_dict()
        ),
        "per_second": per_second,
        "per_scan_semantic_digests": per_scan_semantic_digests,
        "per_scan_semantic_digests_sha256": _json_sha256(
            per_scan_semantic_digests
        ),
        "final_tracks_sha256": _json_sha256(final_tracks),
        "consistency_evidence_sha256": _json_sha256(evidence),
        "profile": profile,
    }


def run_coalesced_release_schedule_variant(
    release_groups: Sequence[Sequence[SensorScanFrame]],
    *,
    variant: str,
    adapter_options: Mapping[str, Any] | None = None,
    profile_path: str | Path | None = None,
) -> dict[str, Any]:
    """Replay the current main state-only/full materialization schedule.

    Fusion wall time excludes semantic hashing.  Every released scan is still
    fused exactly once; only consecutive scans in one organizer release group
    that resolve to the same fusion timestamp defer detached ``GlobalTrack``
    construction until that timestamp's final scan.
    """

    adapter = Scalable3DFusionAdapter(**dict(adapter_options or {}))
    operation_totals = {name: 0 for name in _BATCH_OPERATION_FIELDS}
    per_scan_semantic_digests: list[str] = []
    per_second: dict[str, dict[str, float | int]] = {}
    process_wall_time_s = 0.0
    semantic_hash_wall_time_s = 0.0
    profiler = cProfile.Profile() if profile_path is not None else None
    last_materialized_tracks: Sequence[Any] | None = None
    scan_count = 0
    observation_count = 0
    materialized_snapshot_count = 0
    state_only_scan_count = 0

    for release_group in release_groups:
        scans = tuple(release_group)
        for index, scan in enumerate(scans):
            fusion_timestamp = max(
                float(adapter.current_time),
                float(scan.arrival_timestamp),
            )
            next_fusion_timestamp = None
            if index + 1 < len(scans):
                next_fusion_timestamp = max(
                    fusion_timestamp,
                    float(scans[index + 1].arrival_timestamp),
                )
            materialize_tracks = bool(
                next_fusion_timestamp is None
                or next_fusion_timestamp > fusion_timestamp + 1.0e-9
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
            elapsed = perf_counter() - started
            process_wall_time_s += elapsed

            hash_started = perf_counter()
            per_scan_semantic_digests.append(
                _coalesced_scan_semantic_digest(adapter, result)
            )
            semantic_hash_wall_time_s += perf_counter() - hash_started

            summary = result.summary.to_dict()
            for name in _BATCH_OPERATION_FIELDS:
                operation_totals[name] += int(summary.get(name, 0))
            if materialize_tracks:
                last_materialized_tracks = result.tracks
                materialized_snapshot_count += 1
            else:
                state_only_scan_count += 1
            scan_count += 1
            observation_count += len(scan.observations)
            second_key = str(int(float(scan.arrival_timestamp)))
            second = per_second.setdefault(
                second_key,
                {
                    "scan_count": 0,
                    "observation_count": 0,
                    "fusion_wall_time_s": 0.0,
                },
            )
            second["scan_count"] = int(second["scan_count"]) + 1
            second["observation_count"] = int(second["observation_count"]) + len(
                scan.observations
            )
            second["fusion_wall_time_s"] = (
                float(second["fusion_wall_time_s"]) + elapsed
            )

    if last_materialized_tracks is None:
        raise ValueError("coalesced benchmark requires at least one released scan")

    profile = None
    if profiler is not None:
        destination = Path(profile_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(destination))
        profile = _profile_summary(destination)

    final_tracks = _semantic_track_snapshot(last_materialized_tracks)
    evidence = [item.to_dict() for item in adapter.consistency_evidence_records()]
    return {
        "variant": str(variant),
        "adapter_options": dict(adapter_options or {}),
        "release_group_count": len(release_groups),
        "scan_count": scan_count,
        "observation_count": observation_count,
        "track_count": len(last_materialized_tracks),
        "materialized_snapshot_count": materialized_snapshot_count,
        "state_only_scan_count": state_only_scan_count,
        "process_wall_time_s": process_wall_time_s,
        "semantic_hash_wall_time_s": semantic_hash_wall_time_s,
        "operation_totals": operation_totals,
        "cumulative_diagnostics": adapter.fusion_performance_diagnostics().to_dict(),
        "latency_audit": adapter.latency_audit_summary().to_dict(),
        "per_second": per_second,
        "per_scan_semantic_digests": per_scan_semantic_digests,
        "per_scan_semantic_digests_sha256": _json_sha256(
            per_scan_semantic_digests
        ),
        "final_tracks_sha256": _json_sha256(final_tracks),
        "consistency_evidence_sha256": _json_sha256(evidence),
        "profile": profile,
    }


def compare_long_duration_variants(
    source: str | Path,
    *,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    scans, input_summary = load_frozen_sensor_scans(source)
    profile_root = None if profile_directory is None else Path(profile_directory)
    reference = run_long_duration_variant(
        scans,
        variant="pre_long_duration_optimization_reference",
        direct_checkpoint_state_queries=False,
        fixed_lag_checkpoint_suffix_reuse=False,
        trusted_replay_checkpoint_prefix=False,
        cached_consistency_prefix_refresh=False,
        profile_path=(
            None if profile_root is None else profile_root / "reference.prof"
        ),
    )
    optimized = run_long_duration_variant(
        scans,
        variant="checkpoint_state_and_rebase_suffix_reuse",
        direct_checkpoint_state_queries=True,
        fixed_lag_checkpoint_suffix_reuse=True,
        trusted_replay_checkpoint_prefix=True,
        cached_consistency_prefix_refresh=True,
        profile_path=(
            None if profile_root is None else profile_root / "optimized.prof"
        ),
    )

    reference_ops = reference["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    reference_diagnostics = reference["cumulative_diagnostics"]
    optimized_diagnostics = optimized["cumulative_diagnostics"]
    semantic_equal = (
        optimized["per_scan_semantic_digests"]
        == reference["per_scan_semantic_digests"]
    )
    filter_reduction = _reduction_fraction(
        int(reference_ops["replay_filter_update_count"]),
        int(optimized_ops["replay_filter_update_count"]),
    )
    has_fixed_lag_rebase = int(
        optimized_diagnostics["fixed_lag_rebase_count"]
    ) > 0
    acceptance = {
        "per_scan_semantic_equivalence": semantic_equal,
        "final_track_equivalence": (
            optimized["final_tracks_sha256"] == reference["final_tracks_sha256"]
        ),
        "consistency_evidence_equivalence": (
            optimized["consistency_evidence_sha256"]
            == reference["consistency_evidence_sha256"]
        ),
        "candidate_pair_count_preserved": (
            int(optimized_ops["association_candidate_pair_count"])
            == int(reference_ops["association_candidate_pair_count"])
        ),
        "innovation_solve_count_preserved": (
            int(optimized_ops["association_innovation_solve_count"])
            == int(reference_ops["association_innovation_solve_count"])
        ),
        "checkpoint_state_queries_exercised": (
            int(optimized_diagnostics["checkpoint_state_query_count"]) > 0
        ),
        "fixed_lag_suffix_reuse_exercised_when_applicable": (
            not has_fixed_lag_rebase
            or int(
                optimized_diagnostics[
                    "fixed_lag_checkpoint_suffix_reuse_count"
                ]
            )
            > 0
        ),
        "trusted_checkpoint_prefix_fast_path_exercised": (
            int(
                optimized_diagnostics[
                    "replay_checkpoint_prefix_fast_path_count"
                ]
            )
            > 0
        ),
        "cached_consistency_refresh_exercised": (
            int(optimized_diagnostics["cached_consistency_refresh_count"]) > 0
        ),
        "replay_filter_updates_not_increased": filter_reduction >= 0.0,
        "online_truth_use_count_zero": input_summary["online_truth_use_count"] == 0,
    }
    return {
        "schema_version": LONG_DURATION_PERFORMANCE_SCHEMA_VERSION,
        "input": input_summary,
        "reference": reference,
        "optimized": optimized,
        "comparison": {
            "fusion_wall_time_speedup": (
                float(reference["process_wall_time_s"])
                / float(optimized["process_wall_time_s"])
                if float(optimized["process_wall_time_s"]) > 0.0
                else None
            ),
            "replay_filter_update_reduction_fraction": filter_reduction,
            "history_replay_reduction_fraction": _reduction_fraction(
                int(reference_ops["history_replay_count"]),
                int(optimized_ops["history_replay_count"]),
            ),
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
        },
    }


def compare_coalesced_release_performance_variants(
    source: str | Path,
    *,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Compare the clean baseline with D1's next association/materialization path."""

    release_groups, input_summary = load_frozen_sensor_scan_release_groups(source)
    profile_root = None if profile_directory is None else Path(profile_directory)
    reference = run_coalesced_release_schedule_variant(
        release_groups,
        variant="clean_reference",
        adapter_options={
            "radar_association_lower_bound_gate": False,
            "reuse_track_classification_a95": False,
        },
        profile_path=(
            None if profile_root is None else profile_root / "reference.prof"
        ),
    )
    optimized = run_coalesced_release_schedule_variant(
        release_groups,
        variant="radar_lower_bound_and_single_a95",
        adapter_options={
            "radar_association_lower_bound_gate": True,
            "reuse_track_classification_a95": True,
        },
        profile_path=(
            None if profile_root is None else profile_root / "optimized.prof"
        ),
    )

    reference_ops = reference["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    solve_reduction = _reduction_fraction(
        int(reference_ops["association_innovation_solve_count"]),
        int(optimized_ops["association_innovation_solve_count"]),
    )
    fixed_lag_fields = (
        "history_replay_count",
        "origin_replay_count",
        "state_cache_hit_count",
        "state_cache_miss_count",
        "finalization_replay_count",
        "replay_filter_update_count",
        "replay_checkpoint_reuse_count",
    )
    acceptance = {
        "per_scan_semantic_equivalence": (
            optimized["per_scan_semantic_digests"]
            == reference["per_scan_semantic_digests"]
        ),
        "final_track_equivalence": (
            optimized["final_tracks_sha256"]
            == reference["final_tracks_sha256"]
        ),
        "consistency_evidence_equivalence": (
            optimized["consistency_evidence_sha256"]
            == reference["consistency_evidence_sha256"]
        ),
        "candidate_pair_count_preserved": (
            int(optimized_ops["association_candidate_pair_count"])
            == int(reference_ops["association_candidate_pair_count"])
        ),
        "exact_innovation_solve_reduction_at_least_50_percent": (
            solve_reduction >= 0.50
        ),
        "fixed_lag_operation_counts_preserved": all(
            int(optimized_ops[name]) == int(reference_ops[name])
            for name in fixed_lag_fields
        ),
        "materialization_schedule_preserved": (
            optimized["materialized_snapshot_count"]
            == reference["materialized_snapshot_count"]
            and optimized["state_only_scan_count"]
            == reference["state_only_scan_count"]
            and int(optimized_ops["global_track_materialization_count"])
            == int(reference_ops["global_track_materialization_count"])
            and int(optimized_ops["sensor_health_snapshot_build_count"])
            == int(reference_ops["sensor_health_snapshot_build_count"])
        ),
        "scan_and_observation_count_preserved": (
            optimized["scan_count"] == reference["scan_count"]
            and optimized["observation_count"] == reference["observation_count"]
        ),
        "online_truth_use_count_zero": input_summary["online_truth_use_count"] == 0,
    }
    return {
        "schema_version": COALESCED_RELEASE_PERFORMANCE_SCHEMA_VERSION,
        "input": input_summary,
        "reference": reference,
        "optimized": optimized,
        "comparison": {
            "fusion_wall_time_speedup": (
                float(reference["process_wall_time_s"])
                / float(optimized["process_wall_time_s"])
                if float(optimized["process_wall_time_s"]) > 0.0
                else None
            ),
            "innovation_solve_reduction_fraction": solve_reduction,
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
        },
    }


def compare_coalesced_release_performance_sources(
    sources: Sequence[str | Path],
    *,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Run the coalesced benchmark across deterministic frozen seeds."""

    source_paths = tuple(Path(item) for item in sources)
    if not source_paths:
        raise ValueError("at least one frozen source is required")
    runs = []
    for index, source in enumerate(source_paths):
        runs.append(
            compare_coalesced_release_performance_variants(
                source,
                profile_directory=(
                    profile_directory if index == 0 else None
                ),
            )
        )

    reference_times = [
        float(item["reference"]["process_wall_time_s"]) for item in runs
    ]
    optimized_times = [
        float(item["optimized"]["process_wall_time_s"]) for item in runs
    ]
    run_speedups = [
        before / after
        for before, after in zip(reference_times, optimized_times)
    ]
    candidate_faster_count = sum(
        after < before
        for before, after in zip(reference_times, optimized_times)
    )
    semantic_passed = all(item["comparison"]["passed"] for item in runs)
    aggregate_speedup = fmean(reference_times) / fmean(optimized_times)
    stable_wall_time_improvement = (
        candidate_faster_count == len(runs) and aggregate_speedup >= 1.02
    )
    return {
        "schema_version": COALESCED_RELEASE_PERFORMANCE_SCHEMA_VERSION,
        "runs": runs,
        "aggregate": {
            "run_count": len(runs),
            "reference_mean_fusion_wall_time_s": fmean(reference_times),
            "optimized_mean_fusion_wall_time_s": fmean(optimized_times),
            "aggregate_fusion_wall_time_speedup": aggregate_speedup,
            "per_run_fusion_wall_time_speedups": run_speedups,
            "candidate_faster_count": candidate_faster_count,
            "semantic_and_operation_acceptance_passed": semantic_passed,
            "stable_wall_time_improvement": stable_wall_time_improvement,
            "passed": semantic_passed and stable_wall_time_improvement,
        },
    }


def compare_consistency_counter_refresh_variants(
    source: str | Path,
    *,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Compare full record revalidation with validated replay-counter copies."""

    release_groups, input_summary = load_frozen_sensor_scan_release_groups(source)
    profile_root = None if profile_directory is None else Path(profile_directory)
    reference = run_coalesced_release_schedule_variant(
        release_groups,
        variant="full_consistency_record_revalidation",
        adapter_options={"trusted_consistency_counter_refresh": False},
        profile_path=(
            None if profile_root is None else profile_root / "reference.prof"
        ),
    )
    optimized = run_coalesced_release_schedule_variant(
        release_groups,
        variant="validated_consistency_counter_copy",
        adapter_options={"trusted_consistency_counter_refresh": True},
        profile_path=(
            None if profile_root is None else profile_root / "optimized.prof"
        ),
    )

    reference_ops = reference["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    acceptance = {
        "per_scan_state_covariance_timestamp_lineage_and_level_equivalence": (
            optimized["per_scan_semantic_digests"]
            == reference["per_scan_semantic_digests"]
        ),
        "final_track_equivalence": (
            optimized["final_tracks_sha256"]
            == reference["final_tracks_sha256"]
        ),
        "consistency_evidence_equivalence": (
            optimized["consistency_evidence_sha256"]
            == reference["consistency_evidence_sha256"]
        ),
        "operation_counts_preserved": all(
            int(optimized_ops[name]) == int(reference_ops[name])
            for name in _BATCH_OPERATION_FIELDS
        ),
        "cumulative_diagnostics_preserved": (
            optimized["cumulative_diagnostics"]
            == reference["cumulative_diagnostics"]
        ),
        "materialization_schedule_preserved": (
            optimized["materialized_snapshot_count"]
            == reference["materialized_snapshot_count"]
            and optimized["state_only_scan_count"]
            == reference["state_only_scan_count"]
        ),
        "scan_and_observation_count_preserved": (
            optimized["scan_count"] == reference["scan_count"]
            and optimized["observation_count"] == reference["observation_count"]
        ),
        "cached_consistency_refresh_exercised": (
            int(
                optimized["cumulative_diagnostics"][
                    "cached_consistency_refresh_count"
                ]
            )
            > 0
        ),
        "online_truth_use_count_zero": input_summary["online_truth_use_count"] == 0,
    }
    return {
        "schema_version": CONSISTENCY_COUNTER_REFRESH_PERFORMANCE_SCHEMA_VERSION,
        "input": input_summary,
        "reference": reference,
        "optimized": optimized,
        "comparison": {
            "fusion_wall_time_speedup": (
                float(reference["process_wall_time_s"])
                / float(optimized["process_wall_time_s"])
                if float(optimized["process_wall_time_s"]) > 0.0
                else None
            ),
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
        },
    }


def compare_consistency_counter_refresh_sources(
    sources: Sequence[str | Path],
    *,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Run strict replay-counter A/B across deterministic frozen seeds."""

    source_paths = tuple(Path(item) for item in sources)
    if not source_paths:
        raise ValueError("at least one frozen source is required")
    runs = [
        compare_consistency_counter_refresh_variants(
            source,
            profile_directory=profile_directory if index == 0 else None,
        )
        for index, source in enumerate(source_paths)
    ]
    reference_times = [
        float(item["reference"]["process_wall_time_s"]) for item in runs
    ]
    optimized_times = [
        float(item["optimized"]["process_wall_time_s"]) for item in runs
    ]
    speedups = [
        before / after for before, after in zip(reference_times, optimized_times)
    ]
    candidate_faster_count = sum(
        after < before
        for before, after in zip(reference_times, optimized_times)
    )
    semantic_passed = all(item["comparison"]["passed"] for item in runs)
    aggregate_speedup = fmean(reference_times) / fmean(optimized_times)
    stable_wall_time_improvement = (
        candidate_faster_count == len(runs) and aggregate_speedup >= 1.02
    )
    return {
        "schema_version": CONSISTENCY_COUNTER_REFRESH_PERFORMANCE_SCHEMA_VERSION,
        "runs": runs,
        "aggregate": {
            "run_count": len(runs),
            "reference_mean_fusion_wall_time_s": fmean(reference_times),
            "optimized_mean_fusion_wall_time_s": fmean(optimized_times),
            "aggregate_fusion_wall_time_speedup": aggregate_speedup,
            "per_run_fusion_wall_time_speedups": speedups,
            "candidate_faster_count": candidate_faster_count,
            "semantic_and_operation_acceptance_passed": semantic_passed,
            "stable_wall_time_improvement": stable_wall_time_improvement,
            "passed": semantic_passed and stable_wall_time_improvement,
        },
    }


def compare_covariance_limit_variants(
    source: str | Path,
    *,
    repeat_count: int = 5,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Interleave scalar-reference and vectorized covariance-limit replays."""

    if isinstance(repeat_count, bool) or not isinstance(repeat_count, int):
        raise TypeError("repeat_count must be an integer")
    if repeat_count < 5:
        raise ValueError("repeat_count must be at least 5")

    release_groups, loaded_input_summary = (
        load_frozen_sensor_scan_release_groups(source)
    )
    input_summary = _frozen_release_span_summary(
        release_groups,
        loaded_input_summary,
    )
    if (
        float(input_summary["measurement_span_s"])
        > COVARIANCE_LIMIT_INTERLEAVED_MAX_SPAN_S + 1.0e-9
        or float(input_summary["arrival_span_s"])
        > COVARIANCE_LIMIT_INTERLEAVED_MAX_SPAN_S + 1.0e-9
    ):
        raise ValueError(
            "interleaved covariance-limit performance evidence is limited "
            "to frozen inputs no longer than 6 seconds; use "
            "compare_covariance_limit_semantics_once for longer fixtures"
        )
    options = {
        "reference": {"vectorized_covariance_limit": False},
        "optimized": {"vectorized_covariance_limit": True},
    }

    warmup = {
        name: run_coalesced_release_schedule_variant(
            release_groups,
            variant=f"{name}_covariance_limit_warmup",
            adapter_options=adapter_options,
        )
        for name, adapter_options in options.items()
    }
    warmup_acceptance = _covariance_limit_semantic_acceptance(
        warmup["reference"],
        warmup["optimized"],
        input_summary=input_summary,
    )

    runs: dict[str, list[dict[str, Any]]] = {
        "reference": [],
        "optimized": [],
    }
    timing_order: list[dict[str, Any]] = []
    per_round_acceptance: list[dict[str, bool]] = []
    for round_index in range(repeat_count):
        execution_order = (
            ("reference", "optimized")
            if round_index % 2 == 0
            else ("optimized", "reference")
        )
        round_results: dict[str, dict[str, Any]] = {}
        for execution_position, name in enumerate(execution_order):
            result = run_coalesced_release_schedule_variant(
                release_groups,
                variant=f"{name}_covariance_limit_round_{round_index + 1}",
                adapter_options=options[name],
            )
            runs[name].append(result)
            round_results[name] = result
            timing_order.append(
                {
                    "round_index": round_index + 1,
                    "execution_position": execution_position + 1,
                    "variant": name,
                    "process_wall_time_s": float(result["process_wall_time_s"]),
                }
            )
        per_round_acceptance.append(
            _covariance_limit_semantic_acceptance(
                round_results["reference"],
                round_results["optimized"],
                input_summary=input_summary,
            )
        )

    profile_root = None if profile_directory is None else Path(profile_directory)
    if profile_root is None:
        profile_reference = runs["reference"][0]
        profile_optimized = runs["optimized"][0]
    else:
        profile_reference = run_coalesced_release_schedule_variant(
            release_groups,
            variant="scalar_covariance_limit_profile",
            adapter_options=options["reference"],
            profile_path=profile_root / "reference.prof",
        )
        profile_optimized = run_coalesced_release_schedule_variant(
            release_groups,
            variant="vectorized_covariance_limit_profile",
            adapter_options=options["optimized"],
            profile_path=profile_root / "optimized.prof",
        )
    profile_acceptance = _covariance_limit_semantic_acceptance(
        profile_reference,
        profile_optimized,
        input_summary=input_summary,
    )

    reference_times = [
        float(item["process_wall_time_s"]) for item in runs["reference"]
    ]
    optimized_times = [
        float(item["process_wall_time_s"]) for item in runs["optimized"]
    ]
    reference_distribution = _timing_distribution(reference_times)
    optimized_distribution = _timing_distribution(optimized_times)
    faster_count = sum(
        optimized < reference
        for reference, optimized in zip(reference_times, optimized_times)
    )
    required_faster_count = int(np.ceil(0.8 * repeat_count))
    p50_speedup = (
        reference_distribution["p50_s"] / optimized_distribution["p50_s"]
        if optimized_distribution["p50_s"] > 0.0
        else None
    )
    p95_speedup = (
        reference_distribution["p95_s"] / optimized_distribution["p95_s"]
        if optimized_distribution["p95_s"] > 0.0
        else None
    )
    deterministic_within_variant = all(
        _covariance_limit_semantic_signature(item)
        == _covariance_limit_semantic_signature(items[0])
        for items in runs.values()
        for item in items[1:]
    )
    semantic_acceptance = {
        "warmup_semantics_preserved": all(warmup_acceptance.values()),
        "every_interleaved_round_semantics_preserved": all(
            all(item.values()) for item in per_round_acceptance
        ),
        "profile_run_semantics_preserved": all(profile_acceptance.values()),
        "deterministic_within_each_variant": deterministic_within_variant,
        "online_truth_use_count_zero": (
            int(input_summary["online_truth_use_count"]) == 0
        ),
    }
    timing_acceptance = {
        "optimized_faster_in_at_least_80_percent_of_rounds": (
            faster_count >= required_faster_count
        ),
        "p50_speedup_at_least_1_02": (
            p50_speedup is not None and p50_speedup >= 1.02
        ),
        "optimized_p95_lower_than_reference": (
            optimized_distribution["p95_s"]
            < reference_distribution["p95_s"]
        ),
    }
    return {
        "schema_version": COVARIANCE_LIMIT_PERFORMANCE_SCHEMA_VERSION,
        "input": input_summary,
        "benchmark": {
            "warmup_pair_count": 1,
            "repeat_count": repeat_count,
            "execution_order": timing_order,
            "reference": reference_distribution,
            "optimized": optimized_distribution,
            "per_round_speedups": [
                reference / optimized if optimized > 0.0 else None
                for reference, optimized in zip(
                    reference_times,
                    optimized_times,
                )
            ],
            "p50_speedup": p50_speedup,
            "p95_speedup": p95_speedup,
            "optimized_faster_count": faster_count,
            "required_faster_count": required_faster_count,
        },
        "reference": profile_reference,
        "optimized": profile_optimized,
        "comparison": {
            "warmup_acceptance": warmup_acceptance,
            "per_round_acceptance": per_round_acceptance,
            "profile_acceptance": profile_acceptance,
            "semantic_acceptance": semantic_acceptance,
            "timing_acceptance": timing_acceptance,
            "semantic_passed": all(semantic_acceptance.values()),
            "timing_passed": all(timing_acceptance.values()),
            "passed": (
                all(semantic_acceptance.values())
                and all(timing_acceptance.values())
            ),
        },
    }


def compare_covariance_limit_semantics_once(
    source: str | Path,
) -> dict[str, Any]:
    """Run one scalar/vectorized pair on a long frozen fixture.

    This helper intentionally performs no warmup, repetition, profiling, or
    timing acceptance.  It exists to exercise fixed-lag rebase and OOSM while
    limiting a long fixture to one reference and one optimized replay.
    """

    release_groups, loaded_input_summary = (
        load_frozen_sensor_scan_release_groups(source)
    )
    input_summary = _frozen_release_span_summary(
        release_groups,
        loaded_input_summary,
    )
    reference = run_coalesced_release_schedule_variant(
        release_groups,
        variant="scalar_covariance_limit_long_semantic_once",
        adapter_options={"vectorized_covariance_limit": False},
    )
    optimized = run_coalesced_release_schedule_variant(
        release_groups,
        variant="vectorized_covariance_limit_long_semantic_once",
        adapter_options={"vectorized_covariance_limit": True},
    )
    semantic_acceptance = _covariance_limit_semantic_acceptance(
        reference,
        optimized,
        input_summary=input_summary,
    )
    reference_diagnostics = reference["cumulative_diagnostics"]
    optimized_diagnostics = optimized["cumulative_diagnostics"]
    reference_latency = reference["latency_audit"]
    optimized_latency = optimized["latency_audit"]
    scenario_acceptance = {
        "measurement_or_arrival_span_exceeds_6_seconds": (
            max(
                float(input_summary["measurement_span_s"]),
                float(input_summary["arrival_span_s"]),
            )
            > COVARIANCE_LIMIT_INTERLEAVED_MAX_SPAN_S
        ),
        "fixed_lag_rebase_exercised_in_both_variants": (
            int(reference_diagnostics["fixed_lag_rebase_count"]) > 0
            and int(optimized_diagnostics["fixed_lag_rebase_count"]) > 0
        ),
        "oosm_exercised_in_both_variants": (
            int(reference_latency["oosm_observation_count"]) > 0
            and int(optimized_latency["oosm_observation_count"]) > 0
        ),
        "online_truth_use_count_zero": (
            int(input_summary["online_truth_use_count"]) == 0
        ),
    }
    return {
        "schema_version": COVARIANCE_LIMIT_SEMANTIC_ONCE_SCHEMA_VERSION,
        "input": input_summary,
        "execution_policy": {
            "warmup_count": 0,
            "repeat_count": 1,
            "profiled": False,
            "timing_acceptance": False,
        },
        "reference": reference,
        "optimized": optimized,
        "comparison": {
            "semantic_acceptance": semantic_acceptance,
            "scenario_acceptance": scenario_acceptance,
            "passed": (
                all(semantic_acceptance.values())
                and all(scenario_acceptance.values())
            ),
        },
    }


def audit_fused_track_publications(source: str | Path) -> dict[str, Any]:
    """Audit legacy full snapshots and explicit state-only D1 publications."""

    path = Path(source)
    publication_count = 0
    materialized_snapshot_count = 0
    state_only_count = 0
    serialized_bytes = 0
    track_record_count = 0
    fusion_timestamps: set[float] = set()
    runtime_timestamps: set[float] = set()
    snapshot_hashes: set[str] = set()
    consecutive_unchanged_snapshot_count = 0
    previous_snapshot_hash: str | None = None
    state_change_publication_count = 0
    lineage_record_count = 0

    with path.open("rb") as stream:
        for raw_line in stream:
            record = json.loads(raw_line)
            if record.get("topic") != "modules.d1.fused_tracks":
                continue
            publication_count += 1
            serialized_bytes += len(raw_line)
            payload = record["payload"]
            runtime_timestamps.add(float(record["timestamp"]))
            fusion_timestamps.add(float(payload["summary"]["published_at"]))
            lineage_record_count += len(payload.get("observation_lineage", ()))
            tracks_materialized = payload.get("tracks_materialized", True)
            if not isinstance(tracks_materialized, bool):
                raise ValueError("tracks_materialized must be a boolean when present")
            tracks = payload.get("tracks", ())
            if not tracks_materialized:
                if tracks is not None and tracks != []:
                    raise ValueError(
                        "state-only D1 publication must encode tracks as [] or null"
                    )
                if int(payload.get("track_count", 0)) != 0:
                    raise ValueError("state-only D1 publication track_count must be zero")
                current_track_count = payload.get("current_track_count")
                if current_track_count is None or int(current_track_count) < 0:
                    raise ValueError(
                        "state-only D1 publication requires non-negative current_track_count"
                    )
                state_only_count += 1
                continue
            if tracks is None:
                raise ValueError(
                    "materialized D1 publication must contain a track sequence"
                )
            payload_track_count = int(payload.get("track_count", len(tracks)))
            if payload_track_count != len(tracks):
                raise ValueError(
                    "materialized D1 publication track_count must match len(tracks)"
                )
            if "current_track_count" in payload and int(
                payload["current_track_count"]
            ) != payload_track_count:
                raise ValueError(
                    "materialized D1 publication current_track_count must match track_count"
                )
            materialized_snapshot_count += 1
            track_record_count += len(tracks)
            snapshot_hash = _json_sha256(tracks)
            snapshot_hashes.add(snapshot_hash)
            if snapshot_hash == previous_snapshot_hash:
                consecutive_unchanged_snapshot_count += 1
            else:
                state_change_publication_count += 1
            previous_snapshot_hash = snapshot_hash

    if publication_count == 0:
        raise ValueError("no modules.d1.fused_tracks publications found")
    return {
        "schema_version": FUSED_TRACK_PUBLICATION_AUDIT_SCHEMA_VERSION,
        "source_path": str(path),
        "source_sha256": _sha256_file(path),
        "publication_count": publication_count,
        "materialized_snapshot_count": materialized_snapshot_count,
        "state_only_count": state_only_count,
        "serialized_bytes": serialized_bytes,
        "serialized_mebibytes": serialized_bytes / (1024.0 * 1024.0),
        "track_record_count": track_record_count,
        "lineage_record_count": lineage_record_count,
        "unique_runtime_timestamp_count": len(runtime_timestamps),
        "unique_fusion_timestamp_count": len(fusion_timestamps),
        "unique_track_snapshot_count": len(snapshot_hashes),
        "state_change_publication_count": state_change_publication_count,
        "consecutive_unchanged_snapshot_count": (
            consecutive_unchanged_snapshot_count
        ),
        "coalescible_same_fusion_timestamp_count": max(
            0,
            publication_count - len(fusion_timestamps),
        ),
    }


def write_long_duration_performance_report(
    report: Mapping[str, Any],
    *,
    publication_audit: Mapping[str, Any] | None,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    payload = dict(report)
    payload["publication_audit"] = (
        None if publication_audit is None else dict(publication_audit)
    )
    json_destination = Path(json_path)
    markdown_destination = Path(markdown_path)
    json_destination.parent.mkdir(parents=True, exist_ok=True)
    markdown_destination.parent.mkdir(parents=True, exist_ok=True)
    json_destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_destination.write_text(
        _markdown_report(payload),
        encoding="utf-8",
    )


def write_coalesced_release_performance_report(
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
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default)
        + "\n",
        encoding="utf-8",
    )
    markdown_destination.write_text(
        _coalesced_release_markdown_report(report),
        encoding="utf-8",
    )


def write_consistency_counter_refresh_performance_report(
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
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default)
        + "\n",
        encoding="utf-8",
    )
    markdown_destination.write_text(
        _consistency_counter_refresh_markdown_report(report),
        encoding="utf-8",
    )


def _coalesced_scan_semantic_digest(adapter: Any, result: Any) -> str:
    summary = result.summary.to_dict()
    for name in _BATCH_OPERATION_FIELDS:
        summary.pop(name, None)
    tracks_materialized = bool(result.tracks_materialized)
    return _json_sha256(
        {
            "tracks_materialized": tracks_materialized,
            "summary": summary,
            "posterior": _internal_posterior_snapshot(adapter),
            "materialized_tracks": (
                _semantic_track_snapshot(result.tracks)
                if tracks_materialized
                else None
            ),
        }
    )


def _internal_posterior_snapshot(adapter: Any) -> dict[str, Any]:
    """Capture semantic state without constructing detached GlobalTrack objects."""

    records = []
    for track_id in sorted(adapter.tracks):
        record = adapter.tracks[track_id]
        records.append(
            {
                "track_id": record.track_id,
                "current_state": record.current_state.state,
                "current_covariance": record.current_state.covariance,
                "current_timestamp": record.current_state.timestamp,
                "current_state_covariance_limited": (
                    record.current_state_covariance_limited
                ),
                "created_timestamp": record.created_timestamp,
                "hits": record.hits,
                "source_support": dict(record.source_support),
                "identity_likelihood": dict(record.identity_likelihood),
                "recent_nis": tuple(record.recent_nis),
                "covariance_limit_reasons": dict(
                    record.covariance_limit_reasons
                ),
                "association_diagnostics": dict(
                    record.association_diagnostics
                ),
                "metadata": dict(record.metadata),
                "active_observation_ids": tuple(
                    sorted(item.observation_id for item in record.observations)
                ),
                "archived_observation_ids": tuple(
                    sorted(
                        item.observation_id
                        for item in record.archived_observations
                    )
                ),
                "accepted_observer_scan_keys": tuple(
                    sorted(record.accepted_observer_scan_keys)
                ),
                "track_level": adapter._classify(record).value,
            }
        )
    return {
        "current_time": adapter.current_time,
        "next_track_id": adapter._next_track_id,
        "records": records,
        "consistency_lineage_records": [
            {
                "observation_id": item.observation_id,
                "evidence_id": item.evidence_id,
                "source_lineage": item.source_lineage,
                "measurement_timestamp": item.measurement_timestamp,
                "arrival_timestamp": item.arrival_timestamp,
                "source_global_track_id": item.source_global_track_id,
            }
            for item in adapter.consistency_evidence_records()
        ],
    }


def _semantic_result_digest(result: Any) -> str:
    summary = result.summary.to_dict()
    for name in _BATCH_OPERATION_FIELDS:
        summary.pop(name, None)
    return _json_sha256(
        {
            "tracks": _semantic_track_snapshot(result.tracks),
            "summary": summary,
        }
    )


def _semantic_track_snapshot(tracks: Sequence[Any]) -> dict[str, Any]:
    """Canonicalize one shared audit block plus every track-specific value."""

    shared_keys = ("association_audit", "latency_audit", "sensor_health")
    shared_audit: dict[str, Any] | None = None
    track_records = []
    for track in tracks:
        record = track.to_dict()
        metadata = dict(record["metadata"])
        candidate = {key: metadata.pop(key, None) for key in shared_keys}
        if shared_audit is None:
            shared_audit = candidate
        record["metadata"] = metadata
        track_records.append(record)
    return {
        "shared_audit": {} if shared_audit is None else shared_audit,
        "shared_audit_track_count": len(track_records),
        "track_records": track_records,
    }


def _json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, MappingProxyType):
        return dict(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _profile_summary(path: Path) -> dict[str, Any]:
    stats = pstats.Stats(str(path)).strip_dirs()
    selected_names = {
        "process_scan_batch",
        "_predict_all_to",
        "_limit_record_covariance",
        "_limit_state_covariance",
        "_limit_covariance_diagonal",
        "_clip_covariance_off_diagonal_reference",
        "_clip_covariance_off_diagonal_vectorized",
        "_state_at",
        "_state_from_complete_replay_checkpoints",
        "_replay_record",
        "_prune_record",
        "_filter_update",
        "_scan_one_to_one_assignments",
        "_radar_scan_cost_matrix",
        "_cached_non_radar_scan_cost_matrix",
        "global_tracks",
        "_to_global_track",
        "covariance_a95",
        "pinv",
        "_refresh_cached_consistency_evidence_if_enabled",
        "with_replay_counters",
        "replace",
    }
    selected: dict[str, dict[str, float | int]] = {}
    for (_, _, function_name), values in stats.stats.items():
        if function_name not in selected_names:
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
        entry["primitive_call_count"] = int(entry["primitive_call_count"]) + int(
            primitive_calls
        )
        entry["total_call_count"] = int(entry["total_call_count"]) + int(
            total_calls
        )
        entry["total_time_s"] = float(entry["total_time_s"]) + float(total_time)
        entry["cumulative_time_s"] = float(entry["cumulative_time_s"]) + float(
            cumulative_time
        )
    return {
        "profile_path": str(path),
        "profile_total_time_s": float(stats.total_tt),
        "selected_functions": selected,
    }


def _covariance_limit_semantic_acceptance(
    reference: Mapping[str, Any],
    optimized: Mapping[str, Any],
    *,
    input_summary: Mapping[str, Any],
) -> dict[str, bool]:
    return {
        "per_scan_state_covariance_timestamp_lineage_level_equivalence": (
            optimized["per_scan_semantic_digests"]
            == reference["per_scan_semantic_digests"]
        ),
        "final_global_track_equivalence": (
            optimized["final_tracks_sha256"]
            == reference["final_tracks_sha256"]
        ),
        "consistency_evidence_equivalence": (
            optimized["consistency_evidence_sha256"]
            == reference["consistency_evidence_sha256"]
        ),
        "operation_counts_equivalence": (
            optimized["operation_totals"] == reference["operation_totals"]
        ),
        "cumulative_diagnostics_equivalence": (
            optimized["cumulative_diagnostics"]
            == reference["cumulative_diagnostics"]
        ),
        "latency_audit_equivalence": (
            optimized["latency_audit"] == reference["latency_audit"]
        ),
        "materialization_schedule_equivalence": (
            optimized["materialized_snapshot_count"]
            == reference["materialized_snapshot_count"]
            and optimized["state_only_scan_count"]
            == reference["state_only_scan_count"]
        ),
        "scan_observation_and_track_counts_equivalence": (
            optimized["scan_count"] == reference["scan_count"]
            and optimized["observation_count"] == reference["observation_count"]
            and optimized["track_count"] == reference["track_count"]
        ),
        "online_truth_use_count_zero": (
            int(input_summary["online_truth_use_count"]) == 0
        ),
    }


def _covariance_limit_semantic_signature(
    result: Mapping[str, Any],
) -> tuple[Any, ...]:
    return (
        result["per_scan_semantic_digests_sha256"],
        result["final_tracks_sha256"],
        result["consistency_evidence_sha256"],
        _json_sha256(result["operation_totals"]),
        _json_sha256(result["cumulative_diagnostics"]),
        _json_sha256(result["latency_audit"]),
        int(result["materialized_snapshot_count"]),
        int(result["state_only_scan_count"]),
    )


def _frozen_release_span_summary(
    release_groups: Sequence[Sequence[SensorScanFrame]],
    input_summary: Mapping[str, Any],
) -> dict[str, Any]:
    scans = tuple(scan for group in release_groups for scan in group)
    if not scans:
        raise ValueError("covariance-limit replay requires at least one scan")
    measurement_timestamps = np.asarray(
        [float(scan.measurement_timestamp) for scan in scans],
        dtype=float,
    )
    arrival_timestamps = np.asarray(
        [float(scan.arrival_timestamp) for scan in scans],
        dtype=float,
    )
    return {
        **dict(input_summary),
        "measurement_span_s": float(
            np.max(measurement_timestamps) - np.min(measurement_timestamps)
        ),
        "arrival_span_s": float(
            np.max(arrival_timestamps) - np.min(arrival_timestamps)
        ),
        "interleaved_max_span_s": COVARIANCE_LIMIT_INTERLEAVED_MAX_SPAN_S,
    }


def _timing_distribution(samples: Sequence[float]) -> dict[str, float | int]:
    values = np.asarray(tuple(float(item) for item in samples), dtype=float)
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("timing samples must be a non-empty finite sequence")
    return {
        "sample_count": int(values.size),
        "mean_s": float(np.mean(values)),
        "p50_s": float(np.percentile(values, 50)),
        "p95_s": float(np.percentile(values, 95)),
        "min_s": float(np.min(values)),
        "max_s": float(np.max(values)),
    }


def _reduction_fraction(reference: int, optimized: int) -> float:
    if reference <= 0:
        return 0.0 if optimized > reference else 1.0
    return 1.0 - float(optimized) / float(reference)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _coalesced_release_markdown_report(report: Mapping[str, Any]) -> str:
    aggregate = report["aggregate"]
    runs = report["runs"]
    lines = [
        "# D1 雷达关联与快照物化性能基准",
        "",
        "## 结论",
        "",
        (
            f"冻结输入共 {aggregate['run_count']} 个 seed。旧路径纯融合墙钟均值为 "
            f"{aggregate['reference_mean_fusion_wall_time_s']:.3f} 秒，优化路径为 "
            f"{aggregate['optimized_mean_fusion_wall_time_s']:.3f} 秒，均值加速 "
            f"{aggregate['aggregate_fusion_wall_time_speedup']:.3f} 倍。"
        ),
        (
            "逐扫描后验、终态航迹和在线一致性证据均通过确定性哈希验证。"
            "扫描、观测、固定滞后操作数和 state-only/full 快照计划保持不变。"
        ),
        "",
        "## 分 seed 结果",
        "",
        "| 输入 | 扫描/观测 | 旧路径 / s | 优化路径 / s | 加速 | 精确求解旧/新 | 完整/状态更新 | 语义验收 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in runs:
        source = Path(item["input"]["source_path"])
        reference = item["reference"]
        optimized = item["optimized"]
        reference_ops = reference["operation_totals"]
        optimized_ops = optimized["operation_totals"]
        lines.append(
            f"| `{source.parent.name}` | {reference['scan_count']:,}/"
            f"{reference['observation_count']:,} | "
            f"{reference['process_wall_time_s']:.3f} | "
            f"{optimized['process_wall_time_s']:.3f} | "
            f"{item['comparison']['fusion_wall_time_speedup']:.3f}x | "
            f"{reference_ops['association_innovation_solve_count']:,}/"
            f"{optimized_ops['association_innovation_solve_count']:,} | "
            f"{optimized['materialized_snapshot_count']:,}/"
            f"{optimized['state_only_scan_count']:,} | "
            f"{'通过' if item['comparison']['passed'] else '失败'} |"
        )

    first = runs[0]
    reference_profile = first["reference"].get("profile")
    optimized_profile = first["optimized"].get("profile")
    if reference_profile is not None and optimized_profile is not None:
        before_functions = reference_profile["selected_functions"]
        after_functions = optimized_profile["selected_functions"]
        lines.extend(
            [
                "",
                "## 代表 seed 剖析",
                "",
                "cProfile 只用于分离热点，绝对时间受剖析开销影响。",
                "",
                "| 阶段 | 函数 | 旧路径累计 / s | 优化路径累计 / s |",
                "| --- | --- | ---: | ---: |",
            ]
        )
        stages = (
            ("雷达候选与创新求解", "_radar_scan_cost_matrix"),
            ("固定滞后状态查询", "_state_at"),
            ("固定滞后历史重放", "_replay_record"),
            ("完整快照入口", "global_tracks"),
            ("航迹对象物化", "_to_global_track"),
            ("置信椭圆半径", "covariance_a95"),
        )
        for stage, name in stages:
            before = before_functions.get(name, {})
            after = after_functions.get(name, {})
            lines.append(
                f"| {stage} | `{name}` | "
                f"{float(before.get('cumulative_time_s', 0.0)):.3f} | "
                f"{float(after.get('cumulative_time_s', 0.0)):.3f} |"
            )

    lines.extend(
        [
            "",
            "## 算法边界",
            "",
            "雷达预门控只对有限、逐元素严格对称且通过 Gershgorin 严格正定认证的创新协方差"
            "生效。正定下界还必须高于 NumPy `pinv` 的奇异值截断上界；不定、近奇异、非对称或"
            "其他未认证矩阵全部执行原有精确 `pinv`。只有已认证矩阵的马氏距离保守下界严格"
            "超过原门限时，候选对才跳过伪逆。Hungarian 一对一分配、原门限和 `pinv` 语义不变。"
            "完整快照只复用同一次协方差得到的 A95，分级阈值和发布字段不变。",
            "",
            "结果证明当前冻结三维质点输入上的语义等价和本机性能收益。它不证明 AirSim 实时性、"
            "真实雷达精度、正式系统容量或 200 对 200 闭环实时性。",
            "",
        ]
    )
    return "\n".join(lines)


def _consistency_counter_refresh_markdown_report(
    report: Mapping[str, Any],
) -> str:
    aggregate = report["aggregate"]
    runs = report["runs"]
    lines = [
        "# D1 一致性证据计数刷新性能基准",
        "",
        "## 结论",
        "",
        (
            f"冻结输入共 {aggregate['run_count']} 个 seed。完整记录重验路径纯融合墙钟均值为 "
            f"{aggregate['reference_mean_fusion_wall_time_s']:.3f} 秒，受限计数复制路径为 "
            f"{aggregate['optimized_mean_fusion_wall_time_s']:.3f} 秒，均值加速 "
            f"{aggregate['aggregate_fusion_wall_time_speedup']:.3f} 倍。"
        ),
        (
            "每一扫描的状态、协方差、时间戳、来源谱系和航迹分级，以及终态航迹、"
            "逐观测一致性证据和全部融合操作计数均执行严格比较。"
        ),
        "",
        "## 分 seed 结果",
        "",
        "| 输入 | 扫描/观测 | 完整重验 / s | 受限复制 / s | 加速 | 一致性刷新 | 语义验收 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in runs:
        source = Path(item["input"]["source_path"])
        reference = item["reference"]
        optimized = item["optimized"]
        refresh_count = optimized["cumulative_diagnostics"][
            "cached_consistency_refresh_count"
        ]
        lines.append(
            f"| `{source.parent.name}` | {optimized['scan_count']:,}/"
            f"{optimized['observation_count']:,} | "
            f"{reference['process_wall_time_s']:.3f} | "
            f"{optimized['process_wall_time_s']:.3f} | "
            f"{item['comparison']['fusion_wall_time_speedup']:.3f}x | "
            f"{refresh_count:,} | "
            f"{'通过' if item['comparison']['passed'] else '失败'} |"
        )

    first = runs[0]
    reference_profile = first["reference"].get("profile")
    optimized_profile = first["optimized"].get("profile")
    if reference_profile is not None and optimized_profile is not None:
        before = reference_profile["selected_functions"]
        after = optimized_profile["selected_functions"]
        lines.extend(
            [
                "",
                "## 代表 seed 剖析",
                "",
                "cProfile 绝对时间受剖析开销影响，仅用于定位调用链。",
                "",
                "| 函数 | 完整重验累计 / s | 受限复制累计 / s |",
                "| --- | ---: | ---: |",
            ]
        )
        for name in (
            "_refresh_cached_consistency_evidence_if_enabled",
            "replace",
            "with_replay_counters",
            "_replay_record",
            "process_scan_batch",
        ):
            lines.append(
                f"| `{name}` | "
                f"{float(before.get(name, {}).get('cumulative_time_s', 0.0)):.3f} | "
                f"{float(after.get(name, {}).get('cumulative_time_s', 0.0)):.3f} |"
            )

    lines.extend(
        [
            "",
            "## 实施边界",
            "",
            "优化只适用于已通过构造校验、且固定滞后缓存确认估计内容未变化的证据记录。"
            "新路径仅校验并更新非负的 replay_revision 与 replay_count；观测、估计、协方差、"
            "可用性、双时间戳、来源谱系和 evidence_id 复用原不可变值。新建证据、滤波更新、"
            "重复观测、OOSM 标记和不可用记录仍执行完整构造校验。",
            "",
            "该结果只证明冻结三维质点输入上的语义等价与本机性能变化。"
            "实时倍率、长于 10 秒的增长率、AirSim 和真实传感器性能仍需单独验收。",
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_report(report: Mapping[str, Any]) -> str:
    comparison = report["comparison"]
    reference = report["reference"]
    optimized = report["optimized"]
    reference_ops = reference["operation_totals"]
    optimized_ops = optimized["operation_totals"]
    reference_diagnostics = reference["cumulative_diagnostics"]
    optimized_diagnostics = optimized["cumulative_diagnostics"]
    lines = [
        "# D1 长时固定滞后性能与发布审计",
        "",
        "## 结论",
        "",
        f"逐扫描语义等价验收：`{comparison['passed']}`。纯融合墙钟加速比为 "
        f"`{comparison['fusion_wall_time_speedup']:.3f}x`。语义哈希时间单独统计，"
        "不计入融合墙钟。",
        "",
        "## 融合对照",
        "",
        "| 指标 | 旧路径 | 优化路径 |",
        "| --- | ---: | ---: |",
        f"| 扫描数 | {reference['scan_count']} | {optimized['scan_count']} |",
        f"| 航迹数 | {reference['track_count']} | {optimized['track_count']} |",
        f"| 纯融合墙钟 / s | {reference['process_wall_time_s']:.3f} | {optimized['process_wall_time_s']:.3f} |",
        f"| 历史重放 | {reference_ops['history_replay_count']:,} | {optimized_ops['history_replay_count']:,} |",
        f"| 滤波更新 | {reference_ops['replay_filter_update_count']:,} | {optimized_ops['replay_filter_update_count']:,} |",
        f"| 检查点复用 | {reference_ops['replay_checkpoint_reuse_count']:,} | {optimized_ops['replay_checkpoint_reuse_count']:,} |",
        f"| 检查点状态查询 | {reference_diagnostics['checkpoint_state_query_count']:,} | {optimized_diagnostics['checkpoint_state_query_count']:,} |",
        f"| 固定滞后后缀复用 | {reference_diagnostics['fixed_lag_checkpoint_suffix_reuse_count']:,} | {optimized_diagnostics['fixed_lag_checkpoint_suffix_reuse_count']:,} |",
        f"| 合法前缀快路径 | {reference_diagnostics['replay_checkpoint_prefix_fast_path_count']:,} | {optimized_diagnostics['replay_checkpoint_prefix_fast_path_count']:,} |",
        f"| 缓存一致性刷新 | {reference_diagnostics['cached_consistency_refresh_count']:,} | {optimized_diagnostics['cached_consistency_refresh_count']:,} |",
        "",
        "逐扫描航迹、业务摘要、终态航迹和一致性证据均以确定性哈希比较。"
        "双时间戳、协方差、门控、固定滞后窗和在线真值隔离未改变。",
    ]
    audit = report.get("publication_audit")
    if audit is not None:
        lines.extend(
            [
                "",
                "## 发布审计",
                "",
                f"`modules.d1.fused_tracks` 共 {audit['publication_count']:,} 条，"
                f"其中完整快照 {audit.get('materialized_snapshot_count', audit['publication_count']):,} 条、"
                f"状态更新 {audit.get('state_only_count', 0):,} 条，"
                f"序列化体积 {audit['serialized_mebibytes']:.1f} MiB。"
                f"唯一融合时刻 {audit['unique_fusion_timestamp_count']:,} 个，"
                f"连续未变化快照 {audit['consecutive_unchanged_snapshot_count']:,} 条。",
                "",
                "D1 仍需逐个释放扫描完成有序融合和审计，但 main 无需把每次内部融合都写成"
                "全量航迹快照。建议按唯一融合时刻合并，同一时刻保留最后后验；状态未变化时"
                "记录轻量 heartbeat/lineage sidecar；状态变化、生命周期变化、质量跨档、固定"
                "周期关键帧和 episode 尾部仍发布全量快照。",
            ]
        )
    lines.extend(
        [
            "",
            "## 不退化合同",
            "",
            "- 每条接受观测仍保留 measurement_timestamp、arrival_timestamp、协方差和来源谱系。",
            "- 同一融合时刻合并时，只允许保留按既定顺序完成后的最后后验，不得跨时刻重排扫描。",
            "- D2 必须获得每次规范状态变化及其 observation lineage；不得因节流漏掉身份或生命周期事件。",
            "- 全量关键帧必须带单调序号、融合时刻、发布时刻和前序哈希；delta 丢失后可由关键帧恢复。",
            "- D6 仍能重建每条观测的接受、拒绝、乱序重放和航迹归属；不可用指标不得写成零。",
            "",
        ]
    )
    return "\n".join(lines)
