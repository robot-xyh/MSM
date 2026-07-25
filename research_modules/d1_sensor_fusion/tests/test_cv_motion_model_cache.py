from __future__ import annotations

import json

import numpy as np
import pytest

from d1_sensor_fusion import (
    CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION_ID,
    CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION_ID,
    FusionAdapter,
)
from d1_sensor_fusion.ekf import EKFState
from d1_sensor_fusion.observations import (
    radar_covariance_from_range,
    radar_h,
)
from d1_sensor_fusion.types import SensorObservation


_SENSOR_POSITION_NED = np.zeros(3, dtype=float)


def _radar_scan(
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_index: int,
) -> tuple[SensorObservation, ...]:
    bases = (
        np.array([450.0, -180.0, -60.0, 4.0, 0.5, 0.0]),
        np.array([900.0, 260.0, -90.0, -2.0, -0.3, 0.1]),
    )
    observations = []
    for target_index, base in enumerate(bases):
        state = base.copy()
        state[:3] += state[3:] * measurement_timestamp
        measurement = radar_h(state, _SENSOR_POSITION_NED)
        observations.append(
            SensorObservation(
                observation_id=(
                    f"cv-cache-radar-{scan_index}-{target_index}"
                ),
                sensor_id="radar-cv-cache",
                modality="radar",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                frame_id="ned",
                measurement=measurement,
                covariance=radar_covariance_from_range(measurement[0]),
                metadata={
                    "sensor_position_ned": _SENSOR_POSITION_NED,
                    "scan_id": f"cv-cache-scan-{scan_index}",
                    "coverage_cell": "cv-cache-cell",
                },
            )
        )
    return tuple(observations)


def _run_business_sequence(
    *,
    cached_cv_motion_model: bool,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    adapter = FusionAdapter(
        association_gate=40.0,
        immutable_shared_publication_metadata=True,
        radar_assignment_ambiguity_hold_evidence=True,
        cached_cv_motion_model=cached_cv_motion_model,
        cv_motion_model_cache_capacity=8,
    )
    snapshots = []
    summaries = []
    evidence = []
    schedule = (
        (0.0, 0.2),
        (0.4, 0.6),
        (0.2, 0.8),
        (0.8, 1.0),
    )
    for scan_index, (measurement_timestamp, arrival_timestamp) in enumerate(
        schedule
    ):
        result = adapter.process_scan_batch(
            _radar_scan(
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                scan_index=scan_index,
            )
        )
        snapshots.append([track.to_dict() for track in result.tracks])
        summaries.append(result.summary.to_dict())
        evidence.append(
            [item.to_dict() for item in result.structural_ambiguity_evidence]
        )
    return (
        snapshots,
        summaries,
        evidence,
        {
            "latency": adapter.latency_audit_summary().to_dict(),
            "association": adapter.association_audit_summary(),
            "consistency": [
                item.to_dict()
                for item in adapter.consistency_evidence_records()
            ],
        },
    )


def test_default_is_reference_and_configuration_is_explicit() -> None:
    reference = FusionAdapter()
    candidate = FusionAdapter(cached_cv_motion_model=True)

    assert (
        reference.cv_motion_model_cache_diagnostics()["implementation_id"]
        == CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION_ID
    )
    assert (
        candidate.cv_motion_model_cache_diagnostics()["implementation_id"]
        == CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION_ID
    )
    assert reference.cached_cv_motion_model is False
    assert candidate.cached_cv_motion_model is True

    with pytest.raises(TypeError, match="cached_cv_motion_model"):
        FusionAdapter(cached_cv_motion_model=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="cache_capacity"):
        FusionAdapter(cv_motion_model_cache_capacity=True)
    with pytest.raises(ValueError, match="at least 1"):
        FusionAdapter(cv_motion_model_cache_capacity=0)
    with pytest.raises(ValueError, match="at most"):
        FusionAdapter(cv_motion_model_cache_capacity=4_097)


def test_reference_and_candidate_are_exactly_business_equivalent_with_oosm() -> None:
    reference = _run_business_sequence(cached_cv_motion_model=False)
    candidate = _run_business_sequence(cached_cv_motion_model=True)

    assert json.dumps(candidate, sort_keys=True, allow_nan=False) == json.dumps(
        reference,
        sort_keys=True,
        allow_nan=False,
    )
    assert candidate[0][-1][0]["metadata"]["frame_id"] == "ned"
    assert (
        candidate[0][-1][0]["metadata"]["latest_measurement_timestamp"]
        == 0.8
    )
    assert candidate[3]["latency"]["oosm_observation_count"] == 2


def test_cached_models_are_read_only_and_outputs_do_not_alias_them() -> None:
    adapter = FusionAdapter(
        cached_cv_motion_model=True,
        cv_motion_model_cache_capacity=2,
    )
    initial = EKFState(
        state=np.array([10.0, 20.0, -30.0, 4.0, -2.0, 0.5]),
        covariance=np.diag([4.0, 5.0, 6.0, 1.0, 1.5, 2.0]),
        timestamp=0.0,
    )
    first = adapter._predict_to(initial, 0.2)
    transition, process_covariance = next(
        iter(adapter._cv_motion_model_cache.values())
    )
    assert transition.flags.writeable is False
    assert process_covariance.flags.writeable is False
    with pytest.raises(ValueError):
        transition[0, 0] = 2.0
    with pytest.raises(ValueError):
        process_covariance[0, 0] = 2.0

    expected = FusionAdapter()._predict_to(initial, 0.2)
    first.state[:] = -999.0
    first.covariance[:] = -999.0
    repeated = adapter._predict_to(initial, 0.2)
    np.testing.assert_array_equal(repeated.state, expected.state)
    np.testing.assert_array_equal(repeated.covariance, expected.covariance)
    np.testing.assert_array_equal(
        initial.state,
        np.array([10.0, 20.0, -30.0, 4.0, -2.0, 0.5]),
    )


def _deterministic_diagnostics() -> dict:
    adapter = FusionAdapter(
        cached_cv_motion_model=True,
        cv_motion_model_cache_capacity=2,
    )
    initial = EKFState(np.arange(6.0), np.eye(6), 0.0)
    for timestamp in (0.1, 0.1, 0.2, 0.3, 0.1):
        adapter._predict_to(initial, timestamp)
    adapter._predict_to(initial, 0.0)
    with np.errstate(all="ignore"):
        adapter._predict_to(initial, np.inf)
    return adapter.cv_motion_model_cache_diagnostics()


def test_cache_capacity_nonfinite_bypass_and_operation_counts_are_deterministic() -> None:
    first = _deterministic_diagnostics()
    second = _deterministic_diagnostics()

    assert first == second
    assert first["cache_entry_count"] == 2
    assert first["cache_capacity"] == 2
    assert first["operation_counts"] == {
        "cache_eviction_count": 2,
        "cache_hit_count": 1,
        "cache_miss_count": 4,
        "model_build_count": 5,
        "nonfinite_reference_bypass_count": 1,
        "nonpositive_dt_reference_bypass_count": 1,
        "peak_entry_count": 2,
        "prediction_request_count": 7,
    }


def test_process_noise_change_cannot_reuse_a_stale_model() -> None:
    adapter = FusionAdapter(
        process_noise=2.0,
        cached_cv_motion_model=True,
        cv_motion_model_cache_capacity=4,
    )
    initial = EKFState(np.arange(6.0), np.eye(6), 0.0)
    adapter._predict_to(initial, 0.25)
    adapter.process_noise = 9.0
    actual = adapter._predict_to(initial, 0.25)
    expected = FusionAdapter(process_noise=9.0)._predict_to(initial, 0.25)

    np.testing.assert_array_equal(actual.state, expected.state)
    np.testing.assert_array_equal(actual.covariance, expected.covariance)
    diagnostics = adapter.cv_motion_model_cache_diagnostics()
    assert diagnostics["cache_entry_count"] == 2
    assert diagnostics["operation_counts"]["cache_miss_count"] == 2
    assert diagnostics["operation_counts"].get("cache_hit_count", 0) == 0
