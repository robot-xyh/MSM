from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from research_modules.independent_experiments.center_terminal_cv_campaign.common import (
    SourceCueRecord,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.geometry import (
    CameraIntrinsics,
    CameraModel,
    project_source_cue,
    propagate_source_state,
)


def source_cue() -> SourceCueRecord:
    covariance = tuple(
        tuple(1.0 if row == column else 0.0 for column in range(6)) for row in range(6)
    )
    return SourceCueRecord(
        source_track_id="SRC-TEST",
        position_ned_m=(100.0, 0.0, 0.0),
        velocity_ned_mps=(10.0, 0.0, 0.0),
        covariance_6x6=covariance,
        measurement_timestamp=0.0,
        arrival_timestamp=0.1,
        valid_until=20.0,
    )


def camera() -> CameraModel:
    return CameraModel(
        camera_id="CAM-1",
        intrinsics=CameraIntrinsics(width_px=1920, height_px=1080, horizontal_fov_deg=19.0),
        body_position_ned_m=(0.0, 0.0, 0.0),
        body_yaw_pitch_roll_deg=(0.0, 0.0, 0.0),
        camera_offset_body_m=(0.0, 0.0, 0.0),
    )


def test_state_extrapolates_from_measurement_timestamp_and_propagates_covariance() -> None:
    state, covariance = propagate_source_state(source_cue(), 2.0)
    assert state[:3] == pytest.approx((120.0, 0.0, 0.0))
    assert covariance.shape == (6, 6)
    assert np.all(np.linalg.eigvalsh(covariance) > 0.0)
    assert covariance[0, 0] > 1.0


def test_ned_body_gimbal_camera_projection_and_covariance_land_at_image_center() -> None:
    projected = project_source_cue(source_cue(), camera(), 0.2)
    assert projected.center_px == pytest.approx((960.0, 540.0))
    covariance = np.asarray(projected.covariance_px2)
    assert covariance.shape == (2, 2)
    assert np.all(np.linalg.eigvalsh(covariance) > 0.0)
    assert projected.depth_m == pytest.approx(102.0)


def test_source_record_valid_until_is_not_replaced_by_local_three_second_constant() -> None:
    cue = replace(source_cue(), valid_until=20.0)
    projected = project_source_cue(cue, camera(), 18.0)
    assert projected.position_ned_m[0] == pytest.approx(280.0)
