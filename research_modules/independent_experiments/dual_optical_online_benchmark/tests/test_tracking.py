from __future__ import annotations

import math

import pytest

from dual_optical_40target.core import RayObservation
from dual_optical_online_benchmark.tracking import (
    SharedBearingTracker,
    SharedTrackerConfig,
    _angles_from_direction,
    load_tracker_freeze,
    tracker_freeze_payload,
)
from dual_optical_online_benchmark.contracts import write_json


def _direction(azimuth_deg: float, elevation_deg: float = 0.0):
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    return (
        math.cos(elevation) * math.cos(azimuth),
        math.cos(elevation) * math.sin(azimuth),
        -math.sin(elevation),
    )


def _observation(uid: str, sweep: int, timestamp: float, azimuth_deg: float):
    return RayObservation(
        detection_uid=uid,
        camera_id="Optical_A",
        frame_index=sweep,
        sweep_index=sweep,
        timestamp=timestamp,
        origin_ned=(0.0, -1000.0, -100.0),
        direction_ned=_direction(azimuth_deg),
        bbox_xyxy=(0.0, 0.0, 1.0, 1.0),
        camera_yaw_deg=0.0,
        camera_pitch_deg=0.0,
        focal_length_px=25000.0,
    )


def test_physical_first_revisit_gate_accepts_expected_motion() -> None:
    config = SharedTrackerConfig()
    assert config.maximum_angular_rate_deg_s * 2.0 > 2.0
    tracker = SharedBearingTracker("Optical_A", config)
    first_azimuth = math.degrees(math.atan2(1000.0, 2000.0))
    second_azimuth = math.degrees(math.atan2(1000.0, 1900.0))
    tracker.update_sweep(
        0, [_observation("D0", 0, 0.5, first_azimuth)], {"D0": 1.0}
    )
    tracker.update_sweep(
        1, [_observation("D1", 1, 2.5, second_azimuth)], {"D1": 1.0}
    )
    assert len(tracker.tracks) == 1
    assert tracker.tracks[0].status(config, 1) == "confirmed"


def test_direction_conversion_does_not_mutate_position_or_inflate_rate() -> None:
    import numpy as np

    position = np.asarray((1800.0, 1000.0, 0.0), dtype=float)
    original = position.copy()
    _angles_from_direction(position)
    assert np.array_equal(position, original)

    config = SharedTrackerConfig()
    tracker = SharedBearingTracker("Optical_A", config)
    azimuths = [
        math.degrees(math.atan2(1000.0, 2000.0 - 100.0 * index))
        for index in range(3)
    ]
    for index, azimuth in enumerate(azimuths):
        uid = f"D{index}"
        tracker.update_sweep(
            index,
            [_observation(uid, index, 0.5 + 2.0 * index, azimuth)],
            {uid: 1.0},
        )
    track = tracker.tracks[0]
    assert track.state[0] == pytest.approx(azimuths[-1], abs=1.0e-6)
    assert 0.0 < track.state[2] <= config.maximum_angular_rate_deg_s


def test_three_sweep_two_hit_policy_allows_one_miss() -> None:
    config = SharedTrackerConfig()
    tracker = SharedBearingTracker("Optical_A", config)
    first_azimuth = math.degrees(math.atan2(1000.0, 2000.0))
    third_azimuth = math.degrees(math.atan2(1000.0, 1800.0))
    tracker.update_sweep(
        0, [_observation("D0", 0, 0.5, first_azimuth)], {"D0": 1.0}
    )
    tracker.update_sweep(1, [], {})
    tracker.update_sweep(
        2, [_observation("D2", 2, 4.5, third_azimuth)], {"D2": 1.0}
    )
    assert len(tracker.tracks) == 1
    assert tracker.tracks[0].status(config, 2) == "confirmed"


def test_bbox_area_does_not_bias_scanlet_direction() -> None:
    config = SharedTrackerConfig(intra_sweep_gate_deg=0.2)
    tracker = SharedBearingTracker("Optical_A", config)
    center = math.degrees(math.atan2(1000.0, 2000.0))
    first = _observation("small", 0, 0.50, center - 0.05)
    second = RayObservation(
        detection_uid="large",
        camera_id="Optical_A",
        frame_index=1,
        sweep_index=0,
        timestamp=0.51,
        origin_ned=first.origin_ned,
        direction_ned=_direction(center + 0.05),
        bbox_xyxy=(0.0, 0.0, 100.0, 100.0),
        camera_yaw_deg=0.0,
        camera_pitch_deg=0.0,
        focal_length_px=25000.0,
    )
    tracker.update_sweep(0, [first, second], {"small": 1.0, "large": 1.0})
    next_azimuth = math.degrees(math.atan2(1000.0, 1900.0))
    tracker.update_sweep(
        1, [_observation("next", 1, 2.5, next_azimuth)], {"next": 1.0}
    )
    azimuth = tracker.tracks[0].samples[0].state_vector[0]
    assert azimuth == pytest.approx(center, abs=0.01)


def test_tracker_freeze_round_trip_is_hashed(tmp_path) -> None:
    config = SharedTrackerConfig(chi2_confidence=0.995)
    payload = tracker_freeze_payload(
        config,
        calibration_manifest="calibration_manifest.json",
        calibration_manifest_sha256="a" * 64,
        validation_metrics={"accepted": True},
    )
    path = tmp_path / "tracker_freeze.json"
    write_json(path, payload)
    loaded, loaded_config = load_tracker_freeze(path)
    assert loaded["tracker_fingerprint"] == config.fingerprint
    assert loaded_config == config


def test_current_tracker_fingerprint_rejects_pre_rate_fix_freeze(tmp_path) -> None:
    config = SharedTrackerConfig()
    payload = tracker_freeze_payload(
        config,
        calibration_manifest="calibration_manifest.json",
        calibration_manifest_sha256="a" * 64,
        validation_metrics={"accepted": True},
    )
    payload["tracker_config_schema"] = "dual-optical-shared-tracker-config-v1"
    payload["tracker_fingerprint"] = "0" * 64
    path = tmp_path / "stale_tracker_freeze.json"
    write_json(path, payload)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_tracker_freeze(path)
