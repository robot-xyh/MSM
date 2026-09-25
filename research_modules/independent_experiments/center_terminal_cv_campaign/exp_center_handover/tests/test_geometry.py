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
    PoseInterpolationError,
    ProjectionUncertainty,
    TimedCameraPose,
    interpolate_camera_pose_at_measurement,
    joint_projection_covariance,
    project_source_cue,
    propagate_source_state,
    validate_arrival_freshness,
    world_ray_with_covariance,
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


def test_complete_rotation_chain_and_mount_offsets_are_applied() -> None:
    model = CameraModel(
        camera_id="MOUNTED",
        intrinsics=CameraIntrinsics(),
        body_position_ned_m=(10.0, 20.0, -30.0),
        body_yaw_pitch_roll_deg=(25.0, -4.0, 2.0),
        gimbal_yaw_pitch_roll_deg=(12.0, 3.0, -1.0),
        camera_yaw_pitch_roll_gimbal_deg=(1.5, -0.5, 0.25),
        camera_offset_body_m=(0.0, 0.0, 0.0),
        gimbal_pivot_offset_body_m=(0.4, -0.2, 0.1),
        camera_offset_gimbal_m=(0.6, 0.05, -0.03),
    )
    assert model.rotation_camera_from_ned == pytest.approx(
        model.rotation_camera_from_gimbal
        @ model.rotation_gimbal_from_body
        @ model.rotation_body_from_ned
    )
    expected_origin = np.asarray(model.body_position_ned_m) + model.rotation_ned_from_body @ (
        np.asarray(model.gimbal_pivot_offset_body_m)
        + model.rotation_body_from_gimbal @ np.asarray(model.camera_offset_gimbal_m)
    )
    assert model.camera_position_ned_m == pytest.approx(expected_origin)
    point_camera = np.asarray((150.0, 8.0, -3.0))
    point_ned = model.camera_position_ned_m + model.rotation_ned_from_camera @ point_camera
    assert model.world_to_camera(point_ned) == pytest.approx(point_camera)


def test_pose_is_interpolated_at_measurement_time_and_fails_without_bracket() -> None:
    samples = (
        TimedCameraPose(1.0, 1.08, (0.0, 0.0, 0.0), (179.0, 0.0, 0.0), (10.0, 0.0, 0.0)),
        TimedCameraPose(1.2, 1.27, (2.0, 4.0, -2.0), (-179.0, 2.0, 0.0), (30.0, 4.0, 0.0)),
    )
    interpolated = interpolate_camera_pose_at_measurement(
        camera(), samples, 1.1, maximum_bracket_gap_s=0.11
    )
    assert interpolated.body_position_ned_m == pytest.approx((1.0, 2.0, -1.0))
    assert abs(abs(interpolated.body_yaw_pitch_roll_deg[0]) - 180.0) < 1.0e-6
    assert interpolated.gimbal_yaw_pitch_roll_deg == pytest.approx((20.0, 2.0, 0.0))
    with pytest.raises(PoseInterpolationError, match="bracket"):
        interpolate_camera_pose_at_measurement(camera(), samples, 0.9)
    with pytest.raises(PoseInterpolationError, match="freshness"):
        validate_arrival_freshness(1.0, 1.3, maximum_latency_s=0.2)


def test_joint_covariance_includes_navigation_attitude_gimbal_and_pixel_terms() -> None:
    model = camera()
    target = np.asarray((120.0, 4.0, -2.0))
    target_covariance = np.diag((4.0, 4.0, 4.0))
    uncertainty = ProjectionUncertainty(
        navigation_position_covariance_m2=tuple(tuple(value for value in row) for row in np.diag((1.0, 1.0, 1.0))),
        body_attitude_covariance_rad2=tuple(tuple(value for value in row) for row in np.diag((1.0e-6, 1.0e-6, 1.0e-6))),
        gimbal_angle_covariance_rad2=tuple(tuple(value for value in row) for row in np.diag((2.0e-6, 2.0e-6, 2.0e-6))),
        pixel_center_covariance_px2=((2.25, 0.0), (0.0, 2.25)),
    )
    joint = joint_projection_covariance(model, target, target_covariance, uncertainty)
    source_only = model.projection_jacobian_ned(target) @ target_covariance @ model.projection_jacobian_ned(target).T
    assert joint.shape == (2, 2)
    assert np.all(np.linalg.eigvalsh(joint) > 0.0)
    assert np.trace(joint) > np.trace(source_only)
    origin, direction, ray_covariance = world_ray_with_covariance(
        model, (970.0, 535.0), uncertainty
    )
    assert origin == pytest.approx(model.camera_position_ned_m)
    assert np.linalg.norm(direction) == pytest.approx(1.0)
    assert ray_covariance.shape == (6, 6)
    assert np.min(np.linalg.eigvalsh(ray_covariance)) > -1.0e-8
