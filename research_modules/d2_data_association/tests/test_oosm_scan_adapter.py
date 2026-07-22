from __future__ import annotations

import numpy as np

from d2_data_association import (
    OOSM_SCAN_ADAPTER_SCHEMA_VERSION,
    OOSMScanAdapterConfig,
    Scalable3DOOSMScanAdapter,
)
from d2_data_association.scalable_3d_models import Detection3D


def _scan_detection(
    scan_name: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> Detection3D:
    return Detection3D(
        detection_id=f"detection-{scan_name}",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        position_ned=np.asarray(
            [measurement_timestamp, 0.0, -100.0],
            dtype=float,
        ),
        covariance=np.eye(3, dtype=float) * 0.1,
        velocity_ned=np.asarray([1.0, 0.0, 0.0], dtype=float),
        velocity_covariance=np.eye(3, dtype=float) * 0.1,
        source_node_id="d1-oosm-test",
        source_track_id="source-track-0",
        metadata={
            "latest_observation_id": f"observation-{scan_name}",
            "latest_sensor_id": "radar-oosm-test",
            "source_measurement_timestamp": measurement_timestamp,
        },
    )


def test_whole_scan_adapter_sorts_bounded_inversion_before_tracker_step() -> None:
    adapter = Scalable3DOOSMScanAdapter(
        config=OOSMScanAdapterConfig(max_lateness_seconds=1.0)
    )
    released_timestamps: list[float] = []
    submissions = [
        ("zero", 0.0, 0.8),
        ("two", 2.0, 2.2),
        ("one-half", 1.5, 2.3),
        ("three", 3.0, 3.1),
    ]
    for name, measurement, arrival in submissions:
        outcome = adapter.submit_scan(
            [_scan_detection(name, measurement, arrival)],
            scan_id=f"scan-{name}",
        )
        assert outcome.admitted is True
        released_timestamps.extend(
            item.timestamp for item in outcome.released_results
        )
    flushed = adapter.flush()
    released_timestamps.extend(item.timestamp for item in flushed.released_results)

    assert released_timestamps == [0.0, 1.5, 2.0, 3.0]
    assert adapter.tracker.state_timestamp == 3.0
    summary = adapter.summary()
    assert summary["schema_version"] == OOSM_SCAN_ADAPTER_SCHEMA_VERSION
    assert summary["measurement_order_inversion_count"] == 1
    assert summary["rejected_scan_count"] == 0
    assert summary["rewind_or_fixed_lag_smoothing"] is False
    assert summary["online_truth_used"] is False


def test_late_scan_is_rejected_without_rewinding_released_state() -> None:
    adapter = Scalable3DOOSMScanAdapter(
        config=OOSMScanAdapterConfig(max_lateness_seconds=0.5)
    )
    adapter.submit_scan([_scan_detection("zero", 0.0, 0.1)])
    second = adapter.submit_scan([_scan_detection("two", 2.0, 2.1)])
    assert [item.timestamp for item in second.released_results] == [0.0]

    late = adapter.submit_scan(
        [_scan_detection("late-one", 1.0, 2.2)],
        scan_id="late-one",
    )

    assert late.admitted is False
    assert late.events[0]["reason"] == "scan_max_lateness_exceeded"
    assert late.rejection_reason_counts_frame == {
        "scan_max_lateness_exceeded": 1
    }
    assert late.rejection_reason_counts_cumulative == {
        "scan_max_lateness_exceeded": 1
    }
    assert adapter.tracker.state_timestamp == 0.0
    summary = adapter.summary()
    assert summary["rejection_reason_counts"] == {
        "scan_max_lateness_exceeded": 1
    }
    flushed = adapter.flush()
    assert [item.timestamp for item in flushed.released_results] == [2.0]
    assert adapter.tracker.state_timestamp == 2.0


def test_scan_buffer_overflow_fails_closed_and_preserves_bound() -> None:
    adapter = Scalable3DOOSMScanAdapter(
        config=OOSMScanAdapterConfig(
            max_lateness_seconds=10.0,
            max_buffered_scans=1,
        )
    )
    first = adapter.submit_scan([_scan_detection("first", 0.0, 0.0)])
    overflow = adapter.submit_scan([_scan_detection("second", 1.0, 1.0)])

    assert first.admitted is True
    assert first.buffered_scan_count == 1
    assert overflow.admitted is False
    assert overflow.events[0]["reason"] == "scan_buffer_overflow"
    summary = adapter.summary()
    assert summary["buffered_scan_count"] == 1
    assert summary["peak_buffered_scan_count"] == 1
    assert summary["buffered_detection_count"] == 1
    assert summary["peak_buffered_detection_count"] == 1
    assert summary["rejection_reason_counts"] == {"scan_buffer_overflow": 1}


def test_scan_older_than_already_released_state_is_rejected_separately() -> None:
    adapter = Scalable3DOOSMScanAdapter(
        config=OOSMScanAdapterConfig(max_lateness_seconds=2.0)
    )
    adapter.submit_scan([_scan_detection("zero", 0.0, 0.0)])
    adapter.submit_scan([_scan_detection("three", 3.0, 3.0)])
    assert adapter.tracker.state_timestamp == 0.0
    adapter.flush()
    assert adapter.tracker.state_timestamp == 3.0

    rejected = adapter.submit_scan(
        [_scan_detection("stale-two-half", 2.5, 3.1)]
    )

    assert rejected.admitted is False
    assert rejected.events[0]["reason"] == "scan_older_than_released_state"
    assert adapter.tracker.state_timestamp == 3.0
