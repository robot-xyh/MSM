#!/usr/bin/env python3
"""Profile D2 with truth-free D1/D2 records from one frozen online bus."""

from __future__ import annotations

import argparse
from collections import Counter
import cProfile
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import pstats
from statistics import mean, median
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Iterable

import numpy as np
import scipy

from d2_data_association.observation_governance import (
    ObservationClaimLedgerConfig,
    ReplayCoastConfig,
)
from d2_data_association.scalable_3d_models import (
    detections3d_from_d1_global_tracks,
)
from d2_data_association.sparse_3d import Scalable3DTracker


SCHEMA_VERSION = "d2-scalable3d-association-hotpath-benchmark-v2"
_TIMING_METADATA_KEYS = frozenset(
    {
        "association_runtime_seconds",
        "assignment_seconds",
        "candidate_generation_seconds",
        "index_build_seconds",
        "tracker_runtime_seconds",
    }
)
_OPERATION_KEYS = (
    "dense_pair_count",
    "spatial_query_pair_count",
    "candidate_edge_count",
    "rejected_spatial_candidate_count",
    "component_count",
    "component_matrix_pair_count",
    "velocity_cost_gated_edge_count",
)
_PROFILE_FUNCTIONS = frozenset(
    {
        "_coalesce_duplicate_tracks",
        "_conservative_query_radii",
        "_conservative_query_radius",
        "_covariance_intersection",
        "_cv_transition_and_process_noise",
        "_advance_observation_claim_watermark",
        "_assign_observation_claim",
        "_maximum_position_variance",
        "_observation_claim_ledger_summary",
        "_partition_observation_freshness",
        "_quadratic_form",
        "_store_observation_claim",
        "_update_track",
        "_velocity_mahalanobis_squared",
        "_velocity_model_gate",
        "allclose",
        "associate",
        "detections3d_from_d1_global_tracks",
        "eigvalsh",
        "govern_covariance",
        "step",
    }
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("online_observations", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare-report", type=Path)
    parser.add_argument("--repeat-count", type=int, default=5)
    parser.add_argument("--warmup-count", type=int, default=1)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    if args.repeat_count <= 0 or args.warmup_count < 0:
        parser.error("repeat-count must be positive and warmup-count non-negative")

    source_path = args.online_observations.resolve()
    pairs = _load_online_d1_d2_pairs(source_path)
    frames = _reconstruct_source_frames(pairs)

    for _ in range(args.warmup_count):
        _run_replay(frames, verify=False, collect_semantics=False)

    runs = [
        _run_replay(frames, verify=True, collect_semantics=True)
        for _ in range(args.repeat_count)
    ]
    semantic_hashes = {item["semantic_sha256"] for item in runs}
    if len(semantic_hashes) != 1:
        raise RuntimeError("repeated replay semantic hashes are not deterministic")
    if not all(item["all_cycles_equal"] for item in runs):
        raise RuntimeError("reconstructed replay differs from frozen D2 output")

    adapter_samples = [float(item["adapter_seconds"]) for item in runs]
    tracker_samples = [float(item["tracker_seconds"]) for item in runs]
    total_samples = [float(item["total_seconds"]) for item in runs]
    first = runs[0]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "online_observations_path": str(source_path),
            "online_observations_sha256": _sha256_file(source_path),
            "truth_sidecar_read": False,
            "online_truth_used": False,
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "platform": platform.platform(),
            "cpu_affinity": (
                sorted(os.sched_getaffinity(0))
                if hasattr(os, "sched_getaffinity")
                else None
            ),
            "openblas_num_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        },
        "cycle_count": len(frames),
        "semantic_equivalence": {
            "all_cycles_equal": True,
            "equal_cycle_count": int(first["equal_cycle_count"]),
            "semantic_sha256": next(iter(semantic_hashes)),
            "repeat_hashes_equal": True,
        },
        "fixed_size_diagnostics": first["fixed_size_diagnostics"],
        "timing": {
            "repeat_count": args.repeat_count,
            "warmup_count": args.warmup_count,
            "adapter_seconds": _sample_summary(adapter_samples),
            "tracker_seconds": _sample_summary(tracker_samples),
            "total_seconds": _sample_summary(total_samples),
        },
        "cycle_timing_diagnostics": _cycle_timing_diagnostics(runs),
        "profile": None,
        "comparison": None,
    }

    if args.profile:
        report["profile"] = _profile_replay(frames)
    if args.compare_report is not None:
        report["comparison"] = _compare_report(
            json.loads(args.compare_report.read_text(encoding="utf-8")),
            report,
        )

    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(args.output)


def _load_online_d1_d2_pairs(
    path: Path,
) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    latest_d1: dict[str, Any] | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            record = json.loads(line)
            if record.get("source") == "D1":
                latest_d1 = record
            if record.get("source") == "D2":
                if latest_d1 is None:
                    raise ValueError(
                        f"D2 record at line {line_number} has no preceding D1"
                    )
                pairs.append((latest_d1, record))
    if not pairs:
        raise ValueError("online bus does not contain D2 records")
    return tuple(pairs)


def _reconstruct_source_frames(
    pairs: Iterable[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[tuple[tuple[Any, ...], dict[str, Any]], ...]:
    pair_list = tuple(pairs)
    replayed_claim_metadata: dict[str, tuple[str, str, float]] = {}
    for _, d2_record in pair_list:
        for event in _governance(d2_record)["replay_quarantine_events"]:
            first_detection_id = str(event["first_detection_id"])
            value = (
                str(event["observation_id"]),
                str(event["source_namespace"]),
                float(event["source_measurement_timestamp"]),
            )
            previous = replayed_claim_metadata.setdefault(first_detection_id, value)
            if previous != value:
                raise ValueError(
                    f"inconsistent replay metadata for {first_detection_id}"
                )

    frames: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for d1_record, d2_record in pair_list:
        association = d2_record["payload"]["association"]
        replay_by_detection = {
            str(item["detection_id"]): item
            for item in _governance(d2_record)["replay_quarantine_events"]
        }
        matched_track_by_detection = {
            str(item["detection_id"]): str(item["track_id"])
            for item in association["matched_pairs"]
        }
        lineage_by_track = {
            str(item["global_track_id"]): item
            for item in d2_record["payload"]["identity_lineage"]
        }
        created_track_ids = sorted(
            str(item["global_track_id"])
            for item in d2_record["payload"]["identity_lineage"]
            if item["association_state"] == "created"
        )
        created_track_by_detection = dict(
            zip(
                association["unmatched_detection_ids"],
                created_track_ids,
                strict=True,
            )
        )

        sources: list[Any] = []
        for index, item in enumerate(d1_record["payload"]["tracks"]):
            timestamp = float(item["timestamp"])
            detection_id = f"d1-3d-{timestamp:.9f}-{index:04d}"
            replay_event = replay_by_detection.get(detection_id)
            if replay_event is not None:
                observation_id = str(replay_event["observation_id"])
                sensor_id = str(replay_event["source_namespace"])
                measurement_timestamp = float(
                    replay_event["source_measurement_timestamp"]
                )
            elif detection_id in replayed_claim_metadata:
                observation_id, sensor_id, measurement_timestamp = (
                    replayed_claim_metadata[detection_id]
                )
            else:
                track_id = matched_track_by_detection.get(
                    detection_id,
                    created_track_by_detection.get(detection_id),
                )
                if track_id is None:
                    raise ValueError(f"no D2 lineage for fresh {detection_id}")
                observations = lineage_by_track[track_id]["source_observations"]
                if not observations:
                    raise ValueError(f"empty D2 lineage for fresh {detection_id}")
                latest = max(
                    observations,
                    key=lambda value: (
                        float(value["measurement_timestamp"]),
                        str(value["observation_id"]),
                    ),
                )
                observation_id = str(latest["observation_id"])
                measurement_timestamp = float(latest["measurement_timestamp"])
                sensor_ids = [
                    str(value).split(":", 1)[1]
                    for value in latest.get("source_lineage", ())
                    if str(value).startswith("sensor:")
                ]
                sensor_id = (
                    sensor_ids[0] if sensor_ids else "d1-online-observation"
                )
            sources.append(
                SimpleNamespace(
                    state=np.asarray(item["state_ned"], dtype=float),
                    covariance=np.asarray(item["covariance"], dtype=float),
                    timestamp=timestamp,
                    metadata={
                        "latest_observation_id": observation_id,
                        "latest_sensor_id": sensor_id,
                        "latest_measurement_timestamp": measurement_timestamp,
                    },
                )
            )
        frames.append((tuple(sources), d2_record))
    return tuple(frames)


def _run_replay(
    frames: Iterable[tuple[tuple[Any, ...], dict[str, Any]]],
    *,
    verify: bool,
    collect_semantics: bool,
) -> dict[str, Any]:
    tracker = _new_tracker()
    adapter_seconds = 0.0
    tracker_seconds = 0.0
    operation_totals: Counter[str] = Counter()
    peak_component_pair_count = 0
    peak_candidate_edge_count = 0
    cycle_hashes: list[str] = []
    equal_cycle_count = 0
    cycle_count = 0
    cycle_records: list[dict[str, Any]] = []

    for sources, expected_record in frames:
        cycle_index = cycle_count
        cycle_count += 1
        started = perf_counter()
        timestamp, detections = detections3d_from_d1_global_tracks(sources)
        adapter_elapsed = perf_counter() - started
        adapter_seconds += adapter_elapsed
        started = perf_counter()
        result = tracker.step(detections, timestamp)
        tracker_elapsed = perf_counter() - started
        tracker_seconds += tracker_elapsed

        metadata = result.metadata
        for key in _OPERATION_KEYS:
            operation_totals[key] += int(metadata[key])
        operation_totals["input_detection_count"] += int(
            metadata["input_detection_count"]
        )
        operation_totals["fresh_detection_count"] += int(
            metadata["fresh_detection_count"]
        )
        operation_totals["replay_quarantined_detection_count"] += int(
            metadata["replay_quarantined_detection_count"]
        )
        operation_totals["matched_pair_count"] += len(result.matched_pairs)
        peak_component_pair_count = max(
            peak_component_pair_count,
            int(metadata["peak_component_pair_count"]),
        )
        peak_candidate_edge_count = max(
            peak_candidate_edge_count,
            int(metadata["candidate_edge_count"]),
        )

        if verify:
            _verify_cycle(tracker, result, expected_record)
            equal_cycle_count += 1
        if collect_semantics:
            cycle_hashes.append(_semantic_hash(tracker, result))
        cycle_records.append(
            {
                "cycle_index": cycle_index,
                "source_sequence": int(expected_record.get("sequence", -1)),
                "timestamp": float(result.timestamp),
                "input_detection_count": int(metadata["input_detection_count"]),
                "fresh_detection_count": int(metadata["fresh_detection_count"]),
                "active_track_count": int(metadata["active_track_count"]),
                "candidate_edge_count": int(metadata["candidate_edge_count"]),
                "observation_claim_count": int(
                    metadata["observation_claim_ledger"]["current_count"]
                ),
                "adapter_seconds": adapter_elapsed,
                "tracker_seconds": tracker_elapsed,
                "total_seconds": adapter_elapsed + tracker_elapsed,
            }
        )

    semantic_sha = sha256(
        json.dumps(cycle_hashes, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "adapter_seconds": adapter_seconds,
        "tracker_seconds": tracker_seconds,
        "total_seconds": adapter_seconds + tracker_seconds,
        "all_cycles_equal": equal_cycle_count == cycle_count if verify else None,
        "equal_cycle_count": equal_cycle_count,
        "semantic_sha256": semantic_sha,
        "cycle_records": cycle_records,
        "fixed_size_diagnostics": {
            **dict(sorted(operation_totals.items())),
            "peak_candidate_edge_count": peak_candidate_edge_count,
            "peak_component_pair_count": peak_component_pair_count,
            "position_mahalanobis_solve_count": int(
                operation_totals["spatial_query_pair_count"]
            ),
            "association_velocity_nis_solve_count": int(
                operation_totals["candidate_edge_count"]
            ),
            "matched_velocity_nis_available_count": int(
                operation_totals["matched_pair_count"]
            ),
            "online_truth_used": False,
        },
    }


def _profile_replay(
    frames: Iterable[tuple[tuple[Any, ...], dict[str, Any]]],
) -> dict[str, Any]:
    profile = cProfile.Profile()
    profile.enable()
    _run_replay(frames, verify=False, collect_semantics=False)
    profile.disable()
    selected: dict[str, dict[str, float | int]] = {}
    stats = pstats.Stats(profile)
    for (_, _, function_name), values in stats.stats.items():
        if function_name not in _PROFILE_FUNCTIONS:
            continue
        primitive_calls, total_calls, own_time, cumulative_time, _ = values
        item = selected.setdefault(
            function_name,
            {
                "primitive_calls": 0,
                "total_calls": 0,
                "own_seconds": 0.0,
                "cumulative_seconds": 0.0,
            },
        )
        item["primitive_calls"] = int(item["primitive_calls"]) + int(
            primitive_calls
        )
        item["total_calls"] = int(item["total_calls"]) + int(total_calls)
        item["own_seconds"] = float(item["own_seconds"]) + float(own_time)
        item["cumulative_seconds"] = float(
            item["cumulative_seconds"]
        ) + float(cumulative_time)
    return {
        "selected_function_count": len(selected),
        "selected_functions": dict(sorted(selected.items())),
        "top_cumulative_functions": _top_profile_functions(
            stats,
            metric_index=3,
        ),
        "top_own_time_functions": _top_profile_functions(
            stats,
            metric_index=2,
        ),
    }


def _top_profile_functions(
    stats: pstats.Stats,
    *,
    metric_index: int,
    limit: int = 25,
) -> list[dict[str, Any]]:
    ranked = sorted(
        stats.stats.items(),
        key=lambda item: (
            -float(item[1][metric_index]),
            item[0][0],
            item[0][1],
            item[0][2],
        ),
    )
    result: list[dict[str, Any]] = []
    for (filename, line_number, function_name), values in ranked[:limit]:
        primitive_calls, total_calls, own_time, cumulative_time, _ = values
        result.append(
            {
                "function": function_name,
                "location": f"{filename}:{line_number}",
                "primitive_calls": int(primitive_calls),
                "total_calls": int(total_calls),
                "own_seconds": float(own_time),
                "cumulative_seconds": float(cumulative_time),
            }
        )
    return result


def _new_tracker() -> Scalable3DTracker:
    return Scalable3DTracker(
        observation_claim_config=ObservationClaimLedgerConfig(
            config_version="main-scalable3d-observation-claim-policy-v1",
            retention_seconds=30.0,
            max_count=60_000,
            max_lateness_seconds=5.0,
        ),
        replay_coast_config=ReplayCoastConfig(
            config_version="main-scalable3d-replay-coast-policy-v1",
            grace_seconds=0.5,
        ),
    )


def _verify_cycle(
    tracker: Scalable3DTracker,
    result: Any,
    expected_record: dict[str, Any],
) -> None:
    expected = expected_record["payload"]
    expected_association = expected["association"]
    expected_governance = expected_association["observation_evidence_governance"]
    actual_tracks = _published_tracks(tracker)
    checks = {
        "tracks": actual_tracks == expected["tracks"],
        "matched_pairs": [
            item.to_dict() for item in result.matched_pairs
        ]
        == expected_association["matched_pairs"],
        "unmatched_track_ids": result.unmatched_track_ids
        == expected_association["unmatched_track_ids"],
        "unmatched_detection_ids": result.unmatched_detection_ids
        == expected_association["unmatched_detection_ids"],
        "ambiguity_score": result.ambiguity_score
        == expected_association["ambiguity_score"],
        "candidate_edge_count": result.metadata["candidate_edge_count"]
        == expected_association["candidate_edge_count"],
        "dense_pair_count": result.metadata["dense_pair_count"]
        == expected_association["dense_pair_count"],
        "replay_quarantine_events": result.metadata[
            "replay_quarantine_events"
        ]
        == expected_governance["replay_quarantine_events"],
        "observation_claim_ledger": result.metadata[
            "observation_claim_ledger"
        ]
        == expected_governance["claim_ledger"],
        "duplicate_coalescence_events": result.metadata[
            "duplicate_coalescence_events"
        ]
        == expected_governance["duplicate_coalescence_events"],
    }
    failures = sorted(key for key, value in checks.items() if not value)
    if failures:
        raise RuntimeError(
            "frozen D2 cycle mismatch at sequence "
            f"{expected_record.get('sequence')}: {', '.join(failures)}"
        )


def _semantic_hash(tracker: Scalable3DTracker, result: Any) -> str:
    canonical = {
        "tracks": [track.to_dict() for track in tracker.active_tracks()],
        "timestamp": result.timestamp,
        "associator_type": result.associator_type,
        "matched_pairs": [item.to_dict() for item in result.matched_pairs],
        "unmatched_track_ids": list(result.unmatched_track_ids),
        "unmatched_detection_ids": list(result.unmatched_detection_ids),
        "ambiguity_score": result.ambiguity_score,
        "rejected_pairs": [item.to_dict() for item in result.rejected_pairs],
        "metadata": {
            key: value
            for key, value in result.metadata.items()
            if key not in _TIMING_METADATA_KEYS
        },
        "source_node_id": result.source_node_id,
        "link_type": result.link_type,
        "risk_summary": (
            None if result.risk_summary is None else result.risk_summary.to_dict()
        ),
    }
    return sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _published_tracks(tracker: Scalable3DTracker) -> list[dict[str, Any]]:
    return [
        {
            "global_track_id": track.global_track_id,
            "timestamp": track.timestamp,
            "state_ned": track.state.tolist(),
            "covariance": track.covariance.tolist(),
            "track_state": track.lifecycle_state.value,
        }
        for track in tracker.active_tracks()
    ]


def _governance(record: dict[str, Any]) -> dict[str, Any]:
    return record["payload"]["association"]["observation_evidence_governance"]


def _sample_summary(values: list[float]) -> dict[str, Any]:
    return {
        "samples": values,
        "minimum": min(values),
        "median": median(values),
        "mean": mean(values),
        "maximum": max(values),
    }


def _cycle_timing_diagnostics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    cycle_count = len(runs[0]["cycle_records"])
    if any(len(run["cycle_records"]) != cycle_count for run in runs):
        raise RuntimeError("repeated replay cycle counts differ")

    timing_keys = ("adapter_seconds", "tracker_seconds", "total_seconds")
    records: list[dict[str, Any]] = []
    for cycle_index in range(cycle_count):
        reference = {
            key: value
            for key, value in runs[0]["cycle_records"][cycle_index].items()
            if key not in timing_keys
        }
        for run in runs[1:]:
            candidate = {
                key: value
                for key, value in run["cycle_records"][cycle_index].items()
                if key not in timing_keys
            }
            if candidate != reference:
                raise RuntimeError(
                    f"repeated replay cycle {cycle_index} diagnostics differ"
                )
        records.append(
            {
                **reference,
                **{
                    key: _sample_summary(
                        [
                            float(run["cycle_records"][cycle_index][key])
                            for run in runs
                        ]
                    )
                    for key in timing_keys
                },
            }
        )

    regular_cycle_count = max(0, cycle_count - 1)
    window_size = min(8, regular_cycle_count // 2)
    window_comparison: dict[str, Any] | None = None
    if window_size > 0:
        early = records[:window_size]
        late = records[regular_cycle_count - window_size : regular_cycle_count]
        early_summary = _cycle_window_summary(early)
        late_summary = _cycle_window_summary(late)
        early_total = float(early_summary["mean_cycle_total_seconds"])
        window_comparison = {
            "last_cycle_excluded_as_finalize": True,
            "window_size": window_size,
            "early_cycle_indices": [item["cycle_index"] for item in early],
            "late_cycle_indices": [item["cycle_index"] for item in late],
            "early": early_summary,
            "late": late_summary,
            "late_to_early_mean_cycle_total_ratio": (
                float(late_summary["mean_cycle_total_seconds"]) / early_total
                if early_total > 0.0
                else None
            ),
        }

    return {
        "timing_assertion_policy": "diagnostic_only_no_wall_clock_pass_fail",
        "repeat_count": len(runs),
        "cycle_count": cycle_count,
        "cycles": records,
        "regular_window_comparison": window_comparison,
    }


def _cycle_window_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    def mean_medians(key: str) -> float:
        return mean(float(item[key]["median"]) for item in records)

    return {
        "mean_cycle_adapter_seconds": mean_medians("adapter_seconds"),
        "mean_cycle_tracker_seconds": mean_medians("tracker_seconds"),
        "mean_cycle_total_seconds": mean_medians("total_seconds"),
        "mean_input_detection_count": mean(
            int(item["input_detection_count"]) for item in records
        ),
        "mean_fresh_detection_count": mean(
            int(item["fresh_detection_count"]) for item in records
        ),
        "mean_active_track_count": mean(
            int(item["active_track_count"]) for item in records
        ),
        "mean_candidate_edge_count": mean(
            int(item["candidate_edge_count"]) for item in records
        ),
        "mean_observation_claim_count": mean(
            int(item["observation_claim_count"]) for item in records
        ),
    }


def _compare_report(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_hash = baseline["semantic_equivalence"]["semantic_sha256"]
    candidate_hash = candidate["semantic_equivalence"]["semantic_sha256"]
    baseline_median = float(baseline["timing"]["total_seconds"]["median"])
    candidate_median = float(candidate["timing"]["total_seconds"]["median"])
    return {
        "baseline_schema_version": baseline.get("schema_version"),
        "same_frozen_input": baseline["source"]["online_observations_sha256"]
        == candidate["source"]["online_observations_sha256"],
        "semantic_hash_equal": baseline_hash == candidate_hash,
        "fixed_size_diagnostics_equal": baseline["fixed_size_diagnostics"]
        == candidate["fixed_size_diagnostics"],
        "baseline_total_median_seconds": baseline_median,
        "candidate_total_median_seconds": candidate_median,
        "speedup": baseline_median / candidate_median,
        "baseline_timing": baseline["timing"],
        "candidate_timing": candidate["timing"],
        "baseline_regular_window_comparison": baseline.get(
            "cycle_timing_diagnostics",
            {},
        ).get("regular_window_comparison"),
        "candidate_regular_window_comparison": candidate.get(
            "cycle_timing_diagnostics",
            {},
        ).get("regular_window_comparison"),
        "selected_profile_functions": _selected_profile_comparison(
            baseline,
            candidate,
        ),
    }


def _selected_profile_comparison(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    baseline_selected = (baseline.get("profile") or {}).get(
        "selected_functions"
    )
    candidate_selected = (candidate.get("profile") or {}).get(
        "selected_functions"
    )
    if not isinstance(baseline_selected, dict) or not isinstance(
        candidate_selected,
        dict,
    ):
        return None
    return {
        name: {
            "baseline": baseline_selected.get(name),
            "candidate": candidate_selected.get(name),
        }
        for name in sorted(set(baseline_selected) | set(candidate_selected))
    }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
