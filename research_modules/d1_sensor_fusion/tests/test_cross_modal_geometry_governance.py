from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

import numpy as np
import pytest

from d1_sensor_fusion.fusion import FusionAdapter
from d1_sensor_fusion.observations import (
    CameraModel,
    eo_project,
    radar_covariance_from_range,
    radar_h,
)
from d1_sensor_fusion.scan_input import SensorScanFrame
from d1_sensor_fusion.types import SensorObservation


SENSOR_POSITION = np.zeros(3, dtype=float)
TARGET_A = np.array([20.0, 0.0, 100.0, 0.0, 0.0, 0.0], dtype=float)
TARGET_B = np.array([-20.0, 0.0, 100.0, 0.0, 0.0, 0.0], dtype=float)
CAMERA = CameraModel(
    position_ned=np.zeros(3, dtype=float),
    rotation_world_to_camera=np.eye(3, dtype=float),
    fx=1_000.0,
    fy=1_000.0,
    cx=960.0,
    cy=540.0,
    width=1_920,
    height=1_080,
)


def _radar(
    observation_id: str,
    state: np.ndarray,
    timestamp: float,
    scan_id: str,
) -> SensorObservation:
    measurement = radar_h(state, SENSOR_POSITION)
    return SensorObservation(
        observation_id=observation_id,
        sensor_id="anonymous-radar",
        modality="radar",
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.05,
        frame_id="ned",
        measurement=measurement,
        covariance=radar_covariance_from_range(float(measurement[0])),
        confidence=0.9,
        metadata={
            "sensor_position_ned": SENSOR_POSITION,
            "scan_id": scan_id,
        },
    )


def _eo(
    observation_id: str,
    state: np.ndarray,
    measurement_timestamp: float,
    arrival_timestamp: float,
    *,
    variance_px2: float,
    camera_model: dict | None = None,
) -> SensorObservation:
    return SensorObservation(
        observation_id=observation_id,
        sensor_id="anonymous-camera",
        modality="eo",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="pixel",
        measurement=eo_project(state, CAMERA),
        covariance=np.eye(2, dtype=float) * variance_px2,
        confidence=1.0,
        metadata={
            "camera_id": "anonymous-camera",
            "camera_model": camera_model or _camera_metadata(),
        },
    )


def _camera_metadata() -> dict:
    return {
        "position_ned": CAMERA.position_ned.tolist(),
        "rotation_world_to_camera": CAMERA.rotation_world_to_camera.tolist(),
        "intrinsics": {
            "fx": CAMERA.fx,
            "fy": CAMERA.fy,
            "cx": CAMERA.cx,
            "cy": CAMERA.cy,
            "width": CAMERA.width,
            "height": CAMERA.height,
        },
    }


def _frozen_observations(
    observations: tuple[SensorObservation, ...],
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    return SensorScanFrame.from_observations(
        observations,
        scan_id=scan_id,
    ).observations


def _seed_tracks(adapter: FusionAdapter, *, include_later_scan: bool = False) -> None:
    for index, timestamp in enumerate((0.0, 0.1)):
        observations = (
            _radar(f"radar-a-{index}", TARGET_A, timestamp, f"radar-{index}"),
            _radar(f"radar-b-{index}", TARGET_B, timestamp, f"radar-{index}"),
        )
        adapter.process_scan_batch(
            _frozen_observations(observations, f"radar-{index}"),
            materialize_tracks=False,
        )
    if include_later_scan:
        observations = (
            _radar("radar-a-later", TARGET_A, 1.0, "radar-later"),
            _radar("radar-b-later", TARGET_B, 1.0, "radar-later"),
        )
        adapter.process_scan_batch(
            _frozen_observations(observations, "radar-later"),
            materialize_tracks=False,
        )


def _record_for_anchor(adapter: FusionAdapter, observation_id: str):
    return next(
        record
        for record in adapter.tracks.values()
        if record.initial_observation_id == observation_id
    )


def _state_digest(record) -> str:
    payload = {
        "state": record.current_state.state.tolist(),
        "covariance": record.current_state.covariance.tolist(),
        "timestamp": record.current_state.timestamp,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lineage_digest(record) -> str:
    payload = [
        {
            "observation_id": observation.observation_id,
            "measurement_timestamp": observation.measurement_timestamp,
            "arrival_timestamp": observation.arrival_timestamp,
            "covariance": observation.covariance.tolist(),
        }
        for observation in record.observations
    ]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_frozen_anonymous_camera_geometry_keeps_legal_radar_eo_fusion() -> None:
    adapter = FusionAdapter(association_gate=40.0)
    _seed_tracks(adapter)
    observation = _eo(
        "anonymous-eo-a",
        TARGET_A,
        0.2,
        0.45,
        variance_px2=0.25,
    )
    frozen = _frozen_observations((observation,), "camera-legal")[0]

    assert isinstance(frozen.metadata["camera_model"], Mapping)
    parsed = CameraModel.from_metadata(frozen.metadata)
    assert np.array_equal(parsed.position_ned, CAMERA.position_ned)
    assert np.array_equal(
        parsed.rotation_world_to_camera,
        CAMERA.rotation_world_to_camera,
    )
    assert (parsed.fx, parsed.fy, parsed.width, parsed.height) == (
        1_000.0,
        1_000.0,
        1_920,
        1_080,
    )

    result = adapter.process_scan_batch((frozen,), materialize_tracks=False)
    record_a = _record_for_anchor(adapter, "radar-a-0")
    record_b = _record_for_anchor(adapter, "radar-b-0")

    assert result.summary.accepted_observation_count == 1
    assert result.summary.affected_track_ids == (record_a.track_id,)
    assert record_a.source_support["eo"] == 1
    assert record_b.source_support.get("eo", 0) == 0
    accepted = next(
        item for item in record_a.observations if item.observation_id == observation.observation_id
    )
    assert accepted.measurement_timestamp == 0.2
    assert accepted.arrival_timestamp == 0.45
    assert np.array_equal(accepted.covariance, np.eye(2) * 0.25)
    audit = adapter.association_audit_summary()
    assert audit["eo_projection_gate_pass_count"] == 1
    assert audit["eo_projection_gate_rejection_count"] == 0
    assert audit["eo_projection_unavailable_count"] == 0


@pytest.mark.parametrize(
    ("variance_px2", "arrival_timestamp"),
    ((0.25, 0.45), (4.0, 6.2)),
)
def test_crossed_eo_does_not_pollute_radar_lineage(
    variance_px2: float,
    arrival_timestamp: float,
) -> None:
    adapter = FusionAdapter(association_gate=40.0, buffer_horizon=6.0)
    control = FusionAdapter(association_gate=40.0, buffer_horizon=6.0)
    include_later = arrival_timestamp > 1.0
    _seed_tracks(adapter, include_later_scan=include_later)
    _seed_tracks(control, include_later_scan=include_later)
    record_a = _record_for_anchor(adapter, "radar-a-0")
    record_b = _record_for_anchor(adapter, "radar-b-0")
    lineage_before = {
        record_a.track_id: _lineage_digest(record_a),
        record_b.track_id: _lineage_digest(record_b),
    }
    conflict_state = np.array([0.0, 80.0, 100.0, 0.0, 0.0, 0.0], dtype=float)
    observation = _eo(
        "anonymous-eo-crossed",
        conflict_state,
        0.2,
        arrival_timestamp,
        variance_px2=variance_px2,
    )
    frozen = _frozen_observations((observation,), "camera-crossed")[0]

    result = adapter.process_scan_batch((frozen,), materialize_tracks=False)
    control.current_time = arrival_timestamp
    control._predict_all_to(arrival_timestamp)

    assert result.summary.accepted_observation_count == 0
    assert result.summary.unaccepted_observation_count == 1
    for anchor in ("radar-a-0", "radar-b-0"):
        actual = _record_for_anchor(adapter, anchor)
        expected = _record_for_anchor(control, anchor)
        assert _lineage_digest(actual) == lineage_before[actual.track_id]
        assert _state_digest(actual) == _state_digest(expected)
        assert actual.source_support.get("eo", 0) == 0
    audit = adapter.association_audit_summary()
    assert audit["eo_projection_gate_rejection_count"] == 1
    assert (
        audit["latest_eo_projection_rejection_reason"]
        == "projection_innovation_gate_rejected"
    )
    if arrival_timestamp == 6.2:
        assert adapter.latency_audit_summary().oosm_observation_count == 1
        assert observation.arrival_timestamp - observation.measurement_timestamp == 6.0


def test_invalid_explicit_camera_geometry_fails_closed() -> None:
    adapter = FusionAdapter(association_gate=40.0)
    _seed_tracks(adapter)
    invalid_model = _camera_metadata()
    invalid_model["rotation_world_to_camera"] = np.zeros((3, 3)).tolist()
    observation = _eo(
        "anonymous-eo-invalid-camera",
        TARGET_A,
        0.2,
        0.45,
        variance_px2=1.0,
        camera_model=invalid_model,
    )
    frozen = _frozen_observations((observation,), "camera-invalid")[0]
    lineage_before = {
        record.track_id: _lineage_digest(record)
        for record in adapter.tracks.values()
    }

    result = adapter.process_scan_batch((frozen,), materialize_tracks=False)

    assert result.summary.accepted_observation_count == 0
    assert all(
        _lineage_digest(record) == lineage_before[record.track_id]
        for record in adapter.tracks.values()
    )
    audit = adapter.association_audit_summary()
    assert audit["eo_projection_unavailable_count"] == 1
    assert (
        audit["latest_eo_projection_rejection_reason"]
        == "camera_geometry_or_projection_unavailable"
    )


def test_track_behind_camera_fails_closed_without_lineage_change() -> None:
    adapter = FusionAdapter(association_gate=40.0)
    _seed_tracks(adapter)
    away_facing_model = _camera_metadata()
    away_facing_model["rotation_world_to_camera"] = np.diag([1.0, 1.0, -1.0]).tolist()
    observation = SensorObservation(
        observation_id="anonymous-eo-behind-camera",
        sensor_id="anonymous-camera",
        modality="eo",
        measurement_timestamp=0.2,
        arrival_timestamp=0.45,
        frame_id="pixel",
        measurement=np.array([960.0, 540.0], dtype=float),
        covariance=np.eye(2, dtype=float),
        confidence=1.0,
        metadata={"camera_model": away_facing_model},
    )
    frozen = _frozen_observations((observation,), "camera-behind")[0]
    lineage_before = {
        record.track_id: _lineage_digest(record)
        for record in adapter.tracks.values()
    }

    result = adapter.process_scan_batch((frozen,), materialize_tracks=False)

    assert result.summary.accepted_observation_count == 0
    assert all(
        _lineage_digest(record) == lineage_before[record.track_id]
        for record in adapter.tracks.values()
    )
    audit = adapter.association_audit_summary()
    assert audit["eo_projection_unavailable_count"] == 1
    assert (
        audit["latest_eo_projection_rejection_reason"]
        == "camera_geometry_or_projection_unavailable"
    )


def test_six_second_delayed_legal_eo_keeps_timestamps_and_covariance() -> None:
    adapter = FusionAdapter(association_gate=40.0, buffer_horizon=6.0)
    _seed_tracks(adapter, include_later_scan=True)
    observation = _eo(
        "anonymous-eo-six-second-oosm",
        TARGET_A,
        0.2,
        6.2,
        variance_px2=0.25,
    )
    frozen = _frozen_observations((observation,), "camera-six-second")[0]
    track_id = _record_for_anchor(adapter, "radar-a-0").track_id

    result = adapter.process_scan_batch((frozen,), materialize_tracks=False)
    record_a = adapter.tracks[track_id]

    assert result.summary.accepted_observation_count == 1
    accepted = next(
        item
        for item in (*record_a.archived_observations, *record_a.observations)
        if item.observation_id == observation.observation_id
    )
    assert accepted.measurement_timestamp == 0.2
    assert accepted.arrival_timestamp == 6.2
    assert np.array_equal(accepted.covariance, np.eye(2) * 0.25)
    assert adapter.latency_audit_summary().oosm_observation_count == 1
    assert adapter.buffer_horizon == 6.0
