from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from d1_sensor_fusion import (
    GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_IMPLEMENTATION_ID,
    GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR,
    GLOBAL_TRACK_MATERIALIZATION_REFERENCE_IMPLEMENTATION_ID,
    GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR,
    FusionAdapter,
    SensorObservation,
    benchmark_global_track_materialization_candidate,
    compare_global_track_materialization_workers,
    run_global_track_materialization_worker,
)
from d1_sensor_fusion.observations import (
    radar_covariance_from_range,
    radar_h,
)


def _radar_scan(index: int, *, target_count: int = 4) -> tuple[SensorObservation, ...]:
    measurement_timestamp = 0.1 * index
    arrival_timestamp = measurement_timestamp + 0.05
    scan_id = f"global-track-materialization-scan-{index:03d}"
    observations = []
    for target_index in range(target_count):
        state = np.asarray(
            [
                200.0 + 80.0 * target_index + 2.0 * index,
                -40.0 + 25.0 * target_index,
                -30.0,
                20.0,
                0.0,
                0.0,
            ],
            dtype=float,
        )
        measurement = radar_h(state, np.zeros(3))
        observation_id = f"global-track-materialization-{index:03d}-{target_index:03d}"
        observations.append(
            SensorObservation(
                observation_id=observation_id,
                sensor_id="RADAR-GTM",
                modality="radar",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                frame_id="ned",
                measurement=measurement,
                covariance=radar_covariance_from_range(float(measurement[0])),
                confidence=0.95,
                metadata={
                    "sensor_position_ned": np.zeros(3),
                    "scan_id": scan_id,
                    "source_lineage_key": (
                        "explicit",
                        "RADAR-GTM",
                        scan_id,
                        target_index,
                    ),
                },
            )
        )
    return tuple(observations)


def _write_frozen_replay(path: Path) -> None:
    records = []
    sequence = 0
    for scan_index in range(5):
        observations = _radar_scan(scan_index)
        first = observations[0]
        sequence += 1
        records.append(
            {
                "sequence": sequence,
                "topic": "sensor.observations",
                "source": first.sensor_id,
                "timestamp": first.arrival_timestamp,
                "schema_version": "scalable3d-observation-v1",
                "payload": {
                    "batch_id": first.metadata["scan_id"],
                    "sensor_id": first.sensor_id,
                    "measurement_timestamp": first.measurement_timestamp,
                    "arrival_timestamp": first.arrival_timestamp,
                    "measurements": [
                        {
                            "observation_id": item.observation_id,
                            "sensor_id": item.sensor_id,
                            "modality": item.modality,
                            "measurement_timestamp": item.measurement_timestamp,
                            "arrival_timestamp": item.arrival_timestamp,
                            "frame_id": item.frame_id,
                            "measurement": item.measurement.tolist(),
                            "covariance": item.covariance.tolist(),
                            "confidence": item.confidence,
                            "classification_hint": item.classification_hint,
                            "metadata": {
                                "sensor_position_ned": [0.0, 0.0, 0.0],
                                "scan_id": item.metadata["scan_id"],
                                "source_lineage_key": list(
                                    item.metadata["source_lineage_key"]
                                ),
                            },
                        }
                        for item in observations
                    ],
                },
            }
        )
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )


def test_candidate_is_default_off_and_publishes_exact_detached_tracks() -> None:
    reference = FusionAdapter(immutable_shared_publication_metadata=True)
    candidate = FusionAdapter(
        immutable_shared_publication_metadata=True,
        batched_global_track_a95_summary=True,
    )

    for scan_index in range(4):
        reference_result = reference.process_scan_batch(_radar_scan(scan_index))
        candidate_result = candidate.process_scan_batch(_radar_scan(scan_index))
        assert [item.to_dict() for item in candidate_result.tracks] == [
            item.to_dict() for item in reference_result.tracks
        ]
        assert candidate_result.summary.to_dict() == reference_result.summary.to_dict()

    assert FusionAdapter().batched_global_track_a95_summary is False
    reference_diagnostics = reference.publication_materialization_diagnostics()
    candidate_diagnostics = candidate.publication_materialization_diagnostics()
    assert (
        reference_diagnostics["global_track_materialization_implementation_id"]
        == GLOBAL_TRACK_MATERIALIZATION_REFERENCE_IMPLEMENTATION_ID
    )
    assert (
        candidate_diagnostics["global_track_materialization_implementation_id"]
        == GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_IMPLEMENTATION_ID
    )
    reference_counts = reference_diagnostics["operation_counts"]
    candidate_counts = candidate_diagnostics["operation_counts"]
    assert reference_counts["per_track_a95_summary_call_count"] > 0
    assert candidate_counts.get("per_track_a95_summary_call_count", 0) == 0
    assert (
        candidate_counts["batched_a95_summary_matrix_count"]
        == candidate_counts["batched_a95_summary_reuse_count"]
        == reference_counts["per_track_a95_summary_call_count"]
    )

    detached = candidate_result.tracks[0]
    internal_before = candidate.tracks[detached.global_track_id].current_state.state.copy()
    detached.state[0] += 10_000.0
    detached.covariance[0, 0] += 10_000.0
    assert np.array_equal(
        candidate.tracks[detached.global_track_id].current_state.state,
        internal_before,
    )


def test_candidate_configuration_fails_closed() -> None:
    with pytest.raises(TypeError, match="must be a bool"):
        FusionAdapter(batched_global_track_a95_summary=1)
    with pytest.raises(ValueError, match="requires"):
        FusionAdapter(
            reuse_track_classification_a95=False,
            batched_global_track_a95_summary=True,
        )


def test_worker_strict_semantics_and_operation_conservation(tmp_path: Path) -> None:
    source = tmp_path / "online_observations.jsonl"
    _write_frozen_replay(source)
    reference = run_global_track_materialization_worker(
        source,
        implementation=GLOBAL_TRACK_MATERIALIZATION_REFERENCE_SELECTOR,
    )
    candidate = run_global_track_materialization_worker(
        source,
        implementation=GLOBAL_TRACK_MATERIALIZATION_CANDIDATE_SELECTOR,
    )
    comparison = compare_global_track_materialization_workers(reference, candidate)

    assert comparison["semantic_passed"] is True
    assert comparison["operation_passed"] is True
    assert all(comparison["semantic_checks"].values())
    assert all(comparison["operation_checks"].values())
    assert reference["candidate_default_enabled"] is False
    assert candidate["candidate_default_enabled"] is False
    assert reference["constraints"]["online_truth_use_count"] == 0
    assert candidate["constraints"]["global_track_id_write_enabled"] is False


def test_one_pair_fresh_process_run_is_diagnostic_not_gate_pass(
    tmp_path: Path,
) -> None:
    source = tmp_path / "online_observations.jsonl"
    _write_frozen_replay(source)
    report = benchmark_global_track_materialization_candidate(
        source,
        paired_run_count=1,
        include_profiles=False,
    )

    assert report["passed"] is False
    assert report["acceptance"]["paired_run_count_at_least_seven"] is False
    assert report["acceptance"]["semantic_equivalence_all_pairs"] is True
    assert report["acceptance"]["operation_conservation_all_pairs"] is True
    assert report["pairs"][0]["reference"]["fresh_process"] is True
    assert report["pairs"][0]["candidate"]["fresh_process"] is True
