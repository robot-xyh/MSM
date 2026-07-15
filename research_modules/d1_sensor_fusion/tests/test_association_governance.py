from __future__ import annotations

import numpy as np
import pytest

from d1_sensor_fusion.fusion import CHI2_3_999, FusionAdapter
from d1_sensor_fusion.observations import (
    CameraModel,
    acoustic_covariance,
    eo_project,
    radar_covariance_from_range,
    radar_h,
)
from d1_sensor_fusion.types import SensorObservation


SENSOR_POSITION = np.zeros(3)


def _radar(
    observation_id: str,
    state: np.ndarray,
    timestamp: float,
    scan: int,
) -> SensorObservation:
    measurement = radar_h(state, SENSOR_POSITION)
    return SensorObservation(
        observation_id=observation_id,
        sensor_id="radar-main",
        modality="radar",
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.2,
        frame_id="ned",
        measurement=measurement,
        covariance=radar_covariance_from_range(measurement[0]),
        metadata={
            "sensor_position_ned": SENSOR_POSITION,
            "sequence_id": scan,
        },
    )


def _eo(
    observation_id: str,
    sensor_id: str,
    state: np.ndarray,
    timestamp: float,
    scan: int,
    camera: CameraModel,
    pixel_offset: np.ndarray | None = None,
) -> SensorObservation:
    measurement = eo_project(state, camera)
    if pixel_offset is not None:
        measurement = measurement + np.asarray(pixel_offset, dtype=float)
    return SensorObservation(
        observation_id=observation_id,
        sensor_id=sensor_id,
        modality="eo",
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp,
        frame_id="pixel",
        measurement=measurement,
        covariance=np.eye(2),
        metadata={
            "camera_id": "interceptor-01:0",
            "camera_model": {
                "position_ned": camera.position_ned.tolist(),
                "rotation_world_to_camera": camera.rotation_world_to_camera.tolist(),
                "fx": camera.fx,
                "fy": camera.fy,
                "cx": camera.cx,
                "cy": camera.cy,
                "width": camera.width,
                "height": camera.height,
            },
            "sequence_id": scan,
        },
    )


def test_one_observer_scan_updates_each_track_at_most_once() -> None:
    adapter = FusionAdapter(association_gate=16.0)
    target_a = np.array([100.0, 20.0, -10.0, 0.0, 0.0, 0.0])
    target_b = np.array([100.0, -20.0, -10.0, 0.0, 0.0, 0.0])

    adapter.process(_radar("radar-a-0", target_a, 0.0, 0))
    adapter.process(_radar("radar-b-0", target_b, 0.0, 0))
    adapter.process(_radar("radar-a-1", target_a, 0.1, 1))
    adapter.process(_radar("radar-b-1", target_b, 0.1, 1))

    assert len(adapter.tracks) == 2
    camera = CameraModel()
    adapter.process(_eo("eo-a", "camera-detection-a", target_a, 0.2, 2, camera))
    adapter.process(_eo("eo-b", "camera-detection-b", target_b, 0.2, 2, camera))
    adapter.process(_eo("eo-a-shadow", "camera-detection-c", target_a, 0.2, 2, camera))

    tracks = adapter.global_tracks()
    assert len(tracks) == 2
    assert sorted(track.source_support.get("eo", 0) for track in tracks) == [1, 1]
    audit = adapter.association_audit_summary()
    assert audit["observer_scan_suppression_count"] == 1
    assert audit["latest_rejection_reason"] == "observer_scan_conflict"
    assert all(
        track.metadata["association_audit"]["observer_scan_suppression_count"] == 1
        for track in tracks
    )


def test_recent_unique_radar_reacquisition_does_not_create_duplicate_birth() -> None:
    adapter = FusionAdapter(
        association_gate=0.01,
        radar_reacquisition_gate=CHI2_3_999,
    )
    state = np.array([100.0, -20.0, -10.0, 1.0, 0.0, 0.0])
    for index, timestamp in enumerate((0.0, 0.1, 0.2)):
        predicted = state.copy()
        predicted[:3] += predicted[3:] * timestamp
        adapter.process(_radar(f"radar-{index}", predicted, timestamp, index))

    record = next(iter(adapter.tracks.values()))
    reacquisition = None
    score = None
    for offset_m in np.linspace(1.0, 12.0, 24):
        shifted = state.copy()
        shifted[:3] += shifted[3:] * 0.3
        shifted[1] += offset_m
        candidate = _radar("radar-reacquire", shifted, 0.3, 3)
        candidate_score = adapter._association_score(record, candidate)
        if adapter.association_gate < candidate_score < CHI2_3_999:
            reacquisition = candidate
            score = candidate_score
            break

    assert reacquisition is not None
    assert score is not None
    tracks = adapter.process(reacquisition)

    assert len(tracks) == 1
    assert tracks[0].source_support["radar"] == 4
    assert adapter.association_audit_summary()["radar_reacquisition_count"] == 1
    assert tracks[0].metadata["latest_radar_reacquisition_score"] == score


def test_bearing_only_update_with_inconsistent_cartesian_correction_is_rejected() -> None:
    adapter = FusionAdapter(
        association_gate=100.0,
        non_range_position_correction_gate=1.0e-6,
    )
    state = np.array([100.0, -20.0, -10.0, 0.0, 0.0, 0.0])
    for index, timestamp in enumerate((0.0, 0.1, 0.2)):
        adapter.process(_radar(f"radar-anchor-{index}", state, timestamp, index))

    before = adapter.global_tracks()[0]
    camera = CameraModel()
    eo = _eo(
        "eo-inconsistent",
        "camera-detection-inconsistent",
        state,
        0.3,
        3,
        camera,
        pixel_offset=np.array([2.0, 0.0]),
    )
    tracks = adapter.process(eo)

    assert len(tracks) == 1
    assert tracks[0].source_support.get("eo", 0) == 0
    assert tracks[0].metadata["hits"] == before.metadata["hits"]
    assert np.linalg.norm(tracks[0].state[:3] - before.state[:3]) < 1.0
    audit = adapter.association_audit_summary()
    assert audit["non_range_state_correction_rejection_count"] == 1
    assert audit["max_non_range_position_correction_score"] > 1.0e-6
    assert tracks[0].metadata["association_diagnostics"][
        "non_range_state_correction_rejected"
    ] == 1
    health = {item.sensor_id: item for item in adapter.sensor_health_summaries()}
    assert health[eo.sensor_id].reject_count == 1
    assert "non_range_state_correction_rejected" in health[eo.sensor_id].fault_reasons


def test_fixed_lag_checkpoint_replays_legal_cross_modal_oosm_from_origin() -> None:
    adapter = FusionAdapter(buffer_horizon=0.5, association_gate=25.0)
    state0 = np.array([100.0, 20.0, -5.0, 5.0, 0.0, 0.0])
    state04 = state0.copy()
    state04[:3] += state04[3:] * 0.4
    state1 = state0.copy()
    state1[:3] += state1[3:]
    adapter.process(_radar("radar-origin", state0, 0.0, 0))
    adapter.process(_radar("radar-middle", state04, 0.4, 4))
    before = adapter.process(_radar("radar-later", state1, 1.0, 10))[0]

    record = next(iter(adapter.tracks.values()))
    assert record.checkpoint_active
    assert record.initial_state.timestamp == 0.4
    assert record.metadata["fixed_lag_requested_boundary_timestamp"] == 0.7
    assert record.metadata["fixed_lag_checkpoint_boundary_lag_s"] == pytest.approx(0.3)
    assert record.metadata["fixed_lag_rebase_continuity_error_m"] < 1.0e-6

    delayed_acoustic = SensorObservation(
        observation_id="acoustic-origin-oosm",
        sensor_id="acoustic-main",
        modality="acoustic",
        measurement_timestamp=0.2,
        arrival_timestamp=1.3,
        frame_id="ned",
        measurement=np.array(
            [np.arctan2(state0[1], state0[0] + state0[3] * 0.2)]
        ),
        covariance=acoustic_covariance(0.9),
        metadata={"sensor_position_ned": SENSOR_POSITION, "sequence_id": 2},
    )
    after = adapter.process(delayed_acoustic)[0]

    assert after.source_support["acoustic"] == 1
    assert after.metadata["association_diagnostics"]["pre_checkpoint_oosm_replayed"] == 1
    assert after.metadata["association_audit"]["pre_checkpoint_oosm_replay_count"] == 1
    assert after.metadata["latest_pre_checkpoint_oosm_measurement_timestamp"] == 0.2
    assert np.linalg.norm(after.state[:3] - before.state[:3]) < 1.0
    assert adapter.association_audit_summary()["observer_scan_suppression_count"] == 0
