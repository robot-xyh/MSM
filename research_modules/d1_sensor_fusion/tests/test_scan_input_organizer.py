from __future__ import annotations

import json
from collections.abc import Mapping
from types import MappingProxyType

import numpy as np
import pytest

from d1_sensor_fusion import (
    SCAN_INPUT_AUDIT_SUMMARY_SCHEMA_VERSION,
    SCAN_INPUT_FRAME_SCHEMA_VERSION,
    SCAN_INPUT_RESULT_SCHEMA_VERSION,
    ScanInputConfig,
    ScanInputOrganizer,
    Scalable3DFusionAdapter,
    SensorObservation,
    SensorScanFrame,
    sensor_observations_from_online_batch,
)


def _scan(
    scan_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    *,
    sensor_id: str = "RADAR-A",
    source_node_id: str | None = None,
    observation_count: int = 1,
    lineage_prefix: str | None = None,
    position_offset_m: float = 0.0,
) -> SensorScanFrame:
    prefix = lineage_prefix or scan_id
    observations = tuple(
        SensorObservation(
            observation_id=f"{scan_id}-obs-{index:04d}",
            sensor_id=sensor_id,
            modality="radar",
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id="ned",
            measurement=np.array(
                [1_000.0 + 25.0 * index + position_offset_m, 0.1, -0.05, 3.0]
            ),
            covariance=np.diag([16.0, 0.01, 0.01, 4.0]),
            confidence=0.9,
            metadata={
                "scan_id": scan_id,
                "coverage_cell": "cell-a",
                "source_lineage_key": (
                    "explicit",
                    source_node_id or sensor_id,
                    prefix,
                    index,
                ),
                "source_frame_id": f"{sensor_id.lower()}_frame",
            },
            source_node_id=source_node_id or sensor_id,
            payload_kind="radar_scan",
        )
        for index in range(observation_count)
    )
    return SensorScanFrame(scan_id=scan_id, observations=observations)


def _released_ids(*results) -> list[str]:
    return [
        frame.scan_id
        for result in results
        for frame in result.released_scans
    ]


def _online_batch(
    scan_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    *,
    observation_count: int,
) -> dict:
    sensor_id = "RADAR-CENTER"
    return {
        "batch_id": scan_id,
        "sensor_id": sensor_id,
        "measurement_timestamp": measurement_timestamp,
        "arrival_timestamp": arrival_timestamp,
        "measurements": [
            {
                "observation_id": f"{scan_id}-measurement-{index:04d}",
                "sensor_id": sensor_id,
                "modality": "radar_spherical",
                "measurement_timestamp": measurement_timestamp,
                "arrival_timestamp": arrival_timestamp,
                "frame_id": "radar_center_frame",
                "measurement": [
                    1_000.0 + 100.0 * index + 2.0 * measurement_timestamp,
                    0.1 + 0.1 * index,
                    -0.05,
                ],
                "covariance": np.diag([16.0, 0.001, 0.001]),
                "confidence": 0.95,
                "metadata": {
                    "source_lineage_key": (
                        "explicit",
                        sensor_id,
                        scan_id,
                        index,
                    ),
                    "sensor_position_ned": (0.0, 0.0, 0.0),
                },
            }
            for index in range(observation_count)
        ],
    }


def test_ordered_scans_release_by_measurement_watermark_and_preserve_contract() -> None:
    organizer = ScanInputOrganizer(
        ScanInputConfig(max_lateness_s=0.5, max_buffer_residence_s=10.0)
    )
    scan_0 = _scan("scan-000", 0.0, 0.1, observation_count=3)
    scan_1 = _scan("scan-001", 1.0, 1.1, observation_count=3)
    scan_2 = _scan("scan-002", 2.0, 2.1, observation_count=3)

    result_0 = organizer.ingest(scan_0)
    result_1 = organizer.ingest(scan_1)
    result_2 = organizer.ingest(scan_2)
    tail = organizer.close()

    assert result_0.released_scans == ()
    assert _released_ids(result_1, result_2, tail) == [
        "scan-000",
        "scan-001",
        "scan-002",
    ]
    released = result_1.released_scans[0]
    assert released.schema_version == SCAN_INPUT_FRAME_SCHEMA_VERSION
    assert released.measurement_timestamp == 0.0
    assert released.arrival_timestamp == 0.1
    assert released.frame_id == "ned"
    assert len(released.source_lineage_keys) == 3
    for source, output in zip(scan_0.observations, released.observations):
        assert output.measurement_timestamp == source.measurement_timestamp
        assert output.arrival_timestamp == source.arrival_timestamp
        np.testing.assert_array_equal(output.covariance, source.covariance)
        assert output.frame_id == "ned"
        assert output.source_lineage_key == source.source_lineage_key

    audit = tail.audit
    assert audit.schema_version == SCAN_INPUT_AUDIT_SUMMARY_SCHEMA_VERSION
    assert audit.received_scan_count == 3
    assert audit.received_observation_count == 9
    assert audit.buffered_event_count == 3
    assert audit.released_scan_count == 3
    assert audit.released_observation_count == 9
    assert audit.rejected_scan_count == 0
    assert audit.current_buffered_scan_count == 0
    assert audit.closed is True
    assert json.loads(json.dumps(tail.to_dict(), allow_nan=False))["schema_version"] == (
        SCAN_INPUT_RESULT_SCHEMA_VERSION
    )


def test_main_online_batch_conversion_only_fuses_released_scans() -> None:
    organizer = ScanInputOrganizer(
        ScanInputConfig(max_lateness_s=0.5, max_buffer_residence_s=10.0)
    )
    fusion = Scalable3DFusionAdapter(association_gate=40.0)

    first_batch = _online_batch("online-scan-000", 0.0, 0.2, observation_count=3)
    first_observations = sensor_observations_from_online_batch(first_batch)
    first_frame = SensorScanFrame.from_observations(
        first_observations,
        scan_id=first_batch["batch_id"],
    )
    first = organizer.ingest(first_frame)
    assert first.released_scans == ()
    assert fusion.global_tracks() == []

    second_batch = _online_batch("online-scan-100", 1.0, 1.2, observation_count=3)
    second_frame = SensorScanFrame.from_observations(
        sensor_observations_from_online_batch(second_batch),
        scan_id=second_batch["batch_id"],
    )
    released = organizer.ingest(second_frame)
    fusion_results = tuple(
        fusion.process_scan_batch(frame.observations)
        for frame in released.released_scans
    )

    assert [frame.scan_id for frame in released.released_scans] == ["online-scan-000"]
    assert len(fusion_results) == 1
    assert len(fusion_results[0].tracks) == 3
    assert all(track.covariance.shape == (6, 6) for track in fusion_results[0].tracks)

    late_batch = _online_batch("online-scan-025-late", 0.25, 1.3, observation_count=3)
    late = organizer.ingest(
        SensorScanFrame.from_observations(
            sensor_observations_from_online_batch(late_batch),
            scan_id=late_batch["batch_id"],
        )
    )
    assert late.released_scans == ()
    assert late.audit.too_late_scan_count == 1
    assert len(fusion.global_tracks()) == 3


def test_within_window_out_of_order_scan_is_marked_and_released_in_event_time_order() -> None:
    organizer = ScanInputOrganizer(
        ScanInputConfig(max_lateness_s=1.0, max_buffer_residence_s=10.0)
    )

    result_0 = organizer.ingest(_scan("scan-000", 0.0, 0.1))
    result_2 = organizer.ingest(_scan("scan-200", 2.0, 2.1))
    result_1 = organizer.ingest(_scan("scan-100", 1.0, 2.2))
    result_3 = organizer.ingest(_scan("scan-300", 3.0, 3.1))
    tail = organizer.close()

    assert any(event.buffered and event.reordered for event in result_1.events)
    assert result_1.audit.reordered_scan_count == 1
    assert _released_ids(result_0, result_2, result_1, result_3, tail) == [
        "scan-000",
        "scan-100",
        "scan-200",
        "scan-300",
    ]
    assert tail.audit.too_late_scan_count == 0


def test_scan_older_than_closed_watermark_is_rejected_as_a_whole() -> None:
    organizer = ScanInputOrganizer(
        ScanInputConfig(max_lateness_s=1.0, max_buffer_residence_s=10.0)
    )
    organizer.ingest(_scan("scan-000", 0.0, 0.1, observation_count=2))
    organizer.ingest(_scan("scan-300", 3.0, 3.1, observation_count=2))

    late = organizer.ingest(
        _scan("scan-050-late", 0.5, 3.2, observation_count=7)
    )

    assert late.released_scans == ()
    rejected = [event for event in late.events if event.outcome == "rejected"]
    assert len(rejected) == 1
    assert rejected[0].too_late is True
    assert rejected[0].reason == "measurement_time_before_watermark"
    assert rejected[0].observation_count == 7
    assert late.audit.too_late_scan_count == 1
    assert late.audit.rejected_observation_count == 7
    assert all(event.scan_id != "scan-050-late" for event in late.events if event.released)


def test_same_measurement_time_from_multiple_sources_is_accepted_without_collision() -> None:
    organizer = ScanInputOrganizer(
        ScanInputConfig(max_lateness_s=0.5, max_buffer_residence_s=10.0)
    )
    source_a = organizer.ingest(
        _scan(
            "scan-a-100",
            1.0,
            1.1,
            sensor_id="RADAR-A",
            source_node_id="NODE-A",
            observation_count=4,
        )
    )
    source_b = organizer.ingest(
        _scan(
            "scan-b-100",
            1.0,
            1.2,
            sensor_id="RADAR-B",
            source_node_id="NODE-B",
            observation_count=6,
        )
    )
    release = organizer.ingest(
        _scan("scan-a-200", 2.0, 2.1, sensor_id="RADAR-A")
    )

    assert source_a.released_scans == source_b.released_scans == ()
    assert [frame.scan_id for frame in release.released_scans] == [
        "scan-a-100",
        "scan-b-100",
    ]
    assert release.audit.received_observation_count == 11
    assert release.audit.duplicate_scan_count == 0
    assert release.audit.timestamp_conflict_scan_count == 0


def test_duplicate_replay_and_timestamp_conflict_are_separately_audited() -> None:
    organizer = ScanInputOrganizer(
        ScanInputConfig(max_lateness_s=10.0, max_buffer_residence_s=20.0)
    )
    original = _scan(
        "scan-original",
        1.0,
        1.1,
        lineage_prefix="immutable-payload",
        observation_count=2,
    )
    organizer.ingest(original)

    duplicate = organizer.ingest(
        SensorScanFrame(
            scan_id=original.scan_id,
            observations=tuple(reversed(original.observations)),
        )
    )
    replay = organizer.ingest(
        _scan(
            "scan-relay-copy",
            1.0,
            1.2,
            lineage_prefix="immutable-payload",
            observation_count=2,
        )
    )
    conflict = organizer.ingest(
        _scan(
            "scan-original",
            1.0,
            1.3,
            lineage_prefix="immutable-payload",
            observation_count=2,
            position_offset_m=25.0,
        )
    )

    assert duplicate.released_scans == replay.released_scans == conflict.released_scans == ()
    assert any(event.duplicate for event in duplicate.events)
    assert any(event.replay for event in replay.events)
    assert any(event.timestamp_conflict for event in conflict.events)
    audit = conflict.audit
    assert audit.duplicate_scan_count == 1
    assert audit.replay_scan_count == 1
    assert audit.timestamp_conflict_scan_count == 1
    assert audit.rejected_scan_count == 3


def test_arrival_regression_is_a_timestamp_conflict_and_never_released() -> None:
    organizer = ScanInputOrganizer(
        ScanInputConfig(max_lateness_s=2.0, max_buffer_residence_s=10.0)
    )
    organizer.ingest(_scan("scan-first", 1.0, 2.0))

    regressed = organizer.ingest(_scan("scan-regressed", 1.1, 1.9))

    assert regressed.released_scans == ()
    assert regressed.audit.timestamp_conflict_scan_count == 1
    assert any(
        event.timestamp_conflict and event.reason == "arrival_timestamp_regressed"
        for event in regressed.events
    )


def test_scan_and_observation_capacity_limits_reject_incoming_frame_atomically() -> None:
    scan_limited = ScanInputOrganizer(
        ScanInputConfig(
            max_lateness_s=100.0,
            max_buffer_residence_s=100.0,
            max_buffered_scans=2,
            max_buffered_observations=20,
        )
    )
    scan_limited.ingest(_scan("scan-0", 0.0, 0.1, observation_count=2))
    scan_limited.ingest(_scan("scan-1", 1.0, 1.1, observation_count=2))
    overflow = scan_limited.ingest(
        _scan("scan-2-overflow", 2.0, 2.1, observation_count=2)
    )
    assert overflow.released_scans == ()
    assert overflow.audit.current_buffered_scan_count == 2
    assert overflow.audit.buffer_overflow_scan_count == 1
    assert any(event.buffer_overflow for event in overflow.events)

    observation_limited = ScanInputOrganizer(
        ScanInputConfig(
            max_lateness_s=100.0,
            max_buffer_residence_s=100.0,
            max_buffered_scans=10,
            max_buffered_observations=3,
        )
    )
    observation_limited.ingest(
        _scan("obs-scan-0", 0.0, 0.1, observation_count=2)
    )
    rejected = observation_limited.ingest(
        _scan("obs-scan-1", 1.0, 1.1, observation_count=2)
    )
    assert rejected.audit.current_buffered_observation_count == 2
    assert rejected.audit.rejected_observation_count == 2
    assert rejected.audit.maximum_buffered_observation_count <= 3


def test_buffer_residence_limit_expires_unreleased_frame_with_audit() -> None:
    organizer = ScanInputOrganizer(
        ScanInputConfig(max_lateness_s=100.0, max_buffer_residence_s=1.0)
    )
    organizer.ingest(_scan("scan-expiring", 0.0, 0.1, observation_count=5))

    expired = organizer.advance_arrival_time(1.2)

    assert expired.released_scans == ()
    assert expired.audit.current_buffered_scan_count == 0
    assert expired.audit.buffer_expired_scan_count == 1
    assert expired.audit.rejected_observation_count == 5
    assert any(event.buffer_expired for event in expired.events)


@pytest.mark.parametrize("observation_count", [1, 7, 200])
def test_dynamic_observation_count_has_no_2v2_or_5v5_assumption(
    observation_count: int,
) -> None:
    organizer = ScanInputOrganizer(
        ScanInputConfig(
            max_lateness_s=0.5,
            max_buffer_residence_s=10.0,
            max_buffered_observations=1_000,
        )
    )
    frame = _scan(
        f"dynamic-{observation_count}",
        0.0,
        0.1,
        observation_count=observation_count,
    )

    admitted = organizer.ingest(frame)
    released = organizer.close()

    assert admitted.released_scans == ()
    assert len(released.released_scans) == 1
    assert len(released.released_scans[0].observations) == observation_count
    assert released.audit.received_observation_count == observation_count
    assert released.audit.released_observation_count == observation_count


def test_truth_bearing_frame_is_fail_closed_before_lineage_or_release() -> None:
    frame = _scan("truth-free-boundary", 0.0, 0.1)
    frame.observations[0].metadata = {
        **dict(frame.observations[0].metadata),
        "truth_id": "offline-target-001",
    }
    organizer = ScanInputOrganizer()

    result = organizer.ingest(frame)

    assert result.released_scans == ()
    assert result.audit.invalid_frame_scan_count == 1
    assert result.audit.current_buffered_scan_count == 0
    assert result.audit.claimed_scan_count == 0
    assert any(event.invalid_frame for event in result.events)
    diagnostics = organizer.performance_diagnostics()
    assert diagnostics["validated_frame_reuse_count"] == 0
    assert diagnostics["mutated_frame_rebuild_count"] == 1
    assert diagnostics["organizer_observation_snapshot_count"] == 1


def test_intact_frame_reuses_validated_snapshot_without_second_copy() -> None:
    frame = _scan(
        "reuse-intact-frame",
        0.0,
        0.1,
        observation_count=3,
    )
    organizer = ScanInputOrganizer()

    organizer.ingest(frame)
    released = organizer.close()

    assert released.released_scans == (frame,)
    assert released.released_scans[0] is frame
    assert organizer.performance_diagnostics() == {
        "schema_version": "d1.scan_input.performance_diagnostics.v1",
        "validated_frame_reuse_count": 1,
        "mutated_frame_rebuild_count": 0,
        "iterable_frame_build_count": 0,
        "organizer_observation_snapshot_count": 0,
    }


def test_writable_array_frame_falls_back_to_alias_free_resnapshot() -> None:
    frame = _scan("reuse-array-fallback", 0.0, 0.1)
    original = frame.observations[0]
    original.measurement.setflags(write=True)
    organizer = ScanInputOrganizer()

    organizer.ingest(frame)
    released = organizer.close().released_scans[0]
    released_value = float(released.observations[0].measurement[0])
    original.measurement[0] = -999.0

    assert released is not frame
    assert released.observations[0].measurement[0] == released_value
    assert released.observations[0].measurement.flags.writeable is False
    diagnostics = organizer.performance_diagnostics()
    assert diagnostics["validated_frame_reuse_count"] == 0
    assert diagnostics["mutated_frame_rebuild_count"] == 1
    assert diagnostics["organizer_observation_snapshot_count"] == 1


def test_nested_mappingproxy_metadata_is_snapshotted_without_aliases() -> None:
    intrinsics = np.array(
        [[1_200.0, 0.0, 960.0], [0.0, 1_200.0, 540.0], [0.0, 0.0, 1.0]]
    )
    rotation = np.eye(3)
    camera_backing = {
        "intrinsics": intrinsics,
        "extrinsics": MappingProxyType(
            {
                "rotation_camera_from_ned": rotation,
                "translation_ned_m": (0.5, 0.0, 0.0),
            }
        ),
    }
    metadata_backing = {
        "scan_id": "eo-scan-001",
        "coverage_cell": "camera-front",
        "source_lineage_key": ("explicit", "EO-A", "eo-scan-001", 0),
        "camera_model": MappingProxyType(camera_backing),
        "bbox_xyxy": np.array([880.0, 470.0, 1_040.0, 610.0]),
    }
    measurement = np.array([960.0, 540.0])
    covariance = np.diag([4.0, 4.0])
    source = SensorObservation(
        observation_id="eo-scan-001-obs-0000",
        sensor_id="EO-A",
        modality="eo",
        measurement_timestamp=2.0,
        arrival_timestamp=2.15,
        frame_id="pixel",
        measurement=measurement,
        covariance=covariance,
        metadata=MappingProxyType(metadata_backing),
        source_node_id="INTERCEPTOR-01",
        payload_kind="visual_detection",
    )

    frame = SensorScanFrame(scan_id="eo-scan-001", observations=(source,))
    frozen = frame.observations[0]

    assert frozen.measurement_timestamp == 2.0
    assert frozen.arrival_timestamp == 2.15
    assert isinstance(frozen.metadata, Mapping)
    assert isinstance(frozen.metadata["camera_model"], Mapping)
    np.testing.assert_array_equal(
        frozen.metadata["camera_model"]["intrinsics"], intrinsics
    )
    np.testing.assert_array_equal(frozen.covariance, covariance)
    assert not np.shares_memory(frozen.measurement, source.measurement)
    assert not np.shares_memory(frozen.covariance, source.covariance)
    assert not np.shares_memory(
        frozen.metadata["camera_model"]["intrinsics"], intrinsics
    )

    source.measurement[0] = -1.0
    source.covariance[0, 0] = 999.0
    intrinsics[0, 0] = 10.0
    rotation[0, 0] = -1.0
    camera_backing["new_runtime_field"] = "late mutation"

    assert frozen.measurement[0] == 960.0
    assert frozen.covariance[0, 0] == 4.0
    assert frozen.metadata["camera_model"]["intrinsics"][0, 0] == 1_200.0
    assert (
        frozen.metadata["camera_model"]["extrinsics"]
        ["rotation_camera_from_ned"][0, 0]
        == 1.0
    )
    assert "new_runtime_field" not in frozen.metadata["camera_model"]
    assert frozen.measurement.flags.writeable is False
    assert frozen.covariance.flags.writeable is False
    assert frozen.metadata["bbox_xyxy"].flags.writeable is False
    with pytest.raises(TypeError):
        frozen.metadata["camera_model"]["new_key"] = "forbidden"
    with pytest.raises(ValueError):
        frozen.metadata["bbox_xyxy"][0] = 0.0


def test_nested_mappingproxy_truth_metadata_is_rejected() -> None:
    observation = SensorObservation(
        observation_id="eo-truth-obs-0000",
        sensor_id="EO-A",
        modality="eo",
        measurement_timestamp=3.0,
        arrival_timestamp=3.1,
        frame_id="pixel",
        measurement=np.array([960.0, 540.0]),
        covariance=np.diag([4.0, 4.0]),
        metadata=MappingProxyType(
            {
                "scan_id": "eo-truth-scan",
                "source_lineage_key": ("explicit", "EO-A", "truth-free", 0),
                "camera_model": MappingProxyType(
                    {"offline_truth": MappingProxyType({"target_id": "T001"})}
                ),
            }
        ),
    )

    with pytest.raises(ValueError, match="identity exposure"):
        SensorScanFrame(scan_id="eo-truth-scan", observations=(observation,))
