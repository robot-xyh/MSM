from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from research_modules.scalable_3d_simulation.camera_projection import (
    CameraIntrinsics,
    CameraPose,
    look_at_rotation_ned_to_camera,
    project_points,
)
from research_modules.scalable_3d_simulation.episode_bus import (
    assert_online_payload_truth_free,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.sensor_scene import (
    SensorScene,
    _clip_noisy_bbox,
)
from research_modules.scalable_3d_simulation.world import VectorizedPointMassWorld


def test_pinhole_projection_and_covariance_are_finite_for_visible_point() -> None:
    intrinsics = CameraIntrinsics.from_horizontal_fov(
        width_px=1920,
        height_px=1080,
        horizontal_fov_deg=90.0,
    )
    position = np.array([0.0, 0.0, -100.0])
    rotation = look_at_rotation_ned_to_camera(position, np.array([100.0, 0.0, -100.0]))
    pose = CameraPose(
        position,
        rotation,
        position_covariance_ned=np.eye(3) * 0.1,
        attitude_covariance_rad2=np.eye(3) * 1.0e-6,
    )
    projection = project_points(
        np.array([[100.0, 0.0, -100.0], [-100.0, 0.0, -100.0]]),
        camera_pose=pose,
        intrinsics=intrinsics,
        point_covariance_ned=np.eye(3),
        object_size_m=(2.0, 1.0),
    )
    assert projection.visible.tolist() == [True, False]
    assert np.allclose(projection.pixel_centers[0], [intrinsics.cx, intrinsics.cy])
    assert np.all(np.isfinite(projection.covariance_pixels[0]))
    assert np.min(np.linalg.eigvalsh(projection.covariance_pixels[0])) > 0.0


def test_radar_and_visual_online_measurements_do_not_encode_truth_identity() -> None:
    config = ScenarioConfig(
        target_count=5,
        resource_count=5,
        recon_count=1,
        duration_s=0.1,
        radar_detection_probability=1.0,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
        visual_min_bbox_area_px2=1.0e-6,
        recon_visual_min_bbox_area_px2=1.0e-6,
    )
    world = VectorizedPointMassWorld(config)
    snapshot = world.snapshot()
    scene = SensorScene(config)
    radar = scene.radar_scan(snapshot)
    first_target = snapshot.intruders.position_ned[0]
    visual = scene.visual_scan(snapshot, camera_aim_points={"CAM-INT-0001": first_target})
    assert len(radar.measurements) == config.target_count
    assert radar.offline_truth_labels
    assert visual.measurements
    for measurement in radar.measurements + visual.measurements:
        assert_online_payload_truth_free(measurement)
        assert "TGT-" not in measurement.observation_id
        assert measurement.arrival_timestamp >= measurement.measurement_timestamp
        assert measurement.covariance.shape == (
            measurement.measurement.size,
            measurement.measurement.size,
        )
        assert measurement.measurement.flags.writeable is False
        assert measurement.covariance.flags.writeable is False
    assert all(label.truth_entity_id.startswith("TGT-") for label in radar.offline_truth_labels)


def test_visual_noise_is_seed_reproducible() -> None:
    config = ScenarioConfig(
        target_count=5,
        resource_count=5,
        recon_count=1,
        duration_s=0.1,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
        visual_min_bbox_area_px2=1.0e-6,
        recon_visual_min_bbox_area_px2=1.0e-6,
    )
    snapshot = VectorizedPointMassWorld(config).snapshot()
    aim = {"CAM-INT-0001": snapshot.intruders.position_ned[0]}
    first = SensorScene(config).visual_scan(snapshot, camera_aim_points=aim)
    second = SensorScene(replace(config)).visual_scan(snapshot, camera_aim_points=aim)
    assert len(first.measurements) == len(second.measurements)
    for left, right in zip(first.measurements, second.measurements):
        assert left.observation_id == right.observation_id
        assert np.array_equal(left.measurement, right.measurement)


def test_entity_fixed_visual_schedule_is_invariant_to_prior_camera_visibility() -> None:
    config = ScenarioConfig(
        target_count=2,
        resource_count=1,
        recon_count=0,
        duration_s=0.1,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
        visual_min_bbox_area_px2=1.0e-6,
        sensor_random_schedule_version="entity_fixed_v1",
    )
    world = VectorizedPointMassWorld(config)
    world.intruder_state[:, :3] = np.array(
        [[100.0, -10.0, -100.0], [100.0, 10.0, -100.0]],
        dtype=float,
    )
    world.interceptor_state[0, :3] = np.array([0.0, 0.0, -100.0])
    world.interceptor_state[0, 3:] = np.array([1.0, 0.0, 0.0])
    snapshot = world.snapshot()
    forward = {"CAM-INT-0001": np.array([100.0, 0.0, -100.0])}
    backward = {"CAM-INT-0001": np.array([-100.0, 0.0, -100.0])}
    first_scene = SensorScene(config)
    second_scene = SensorScene(config)

    first_view = first_scene.visual_scan(snapshot, camera_aim_points=forward)
    second_view = second_scene.visual_scan(snapshot, camera_aim_points=backward)
    assert len(first_view.measurements) == 2
    assert len(second_view.measurements) == 0

    first_follow_up = first_scene.visual_scan(snapshot, camera_aim_points=forward)
    second_follow_up = second_scene.visual_scan(snapshot, camera_aim_points=forward)
    assert len(first_follow_up.measurements) == len(second_follow_up.measurements) == 2
    for left, right in zip(first_follow_up.measurements, second_follow_up.measurements):
        assert left.observation_id == right.observation_id
        assert np.array_equal(left.measurement, right.measurement)
        assert left.metadata["random_schedule_version"] == "entity_fixed_v1"


@pytest.mark.parametrize("modality", ["radar", "acoustic"])
def test_entity_fixed_sensor_schedule_is_invariant_to_prior_active_mask(
    modality: str,
) -> None:
    config = ScenarioConfig(
        target_count=2,
        resource_count=1,
        recon_count=0,
        duration_s=0.1,
        radar_detection_probability=1.0,
        radar_range_limit_m=10_000.0,
        acoustic_sensor_count=1,
        acoustic_detection_probability=1.0,
        acoustic_range_limit_m=10_000.0,
        sensor_random_schedule_version="entity_fixed_v1",
    )
    world = VectorizedPointMassWorld(config)
    full_snapshot = world.snapshot()
    partial_snapshot = replace(
        full_snapshot,
        intruders=replace(
            full_snapshot.intruders,
            active=np.array([True, False], dtype=bool),
        ),
    )
    first_scene = SensorScene(config)
    second_scene = SensorScene(config)
    scan = SensorScene.radar_scan if modality == "radar" else SensorScene.acoustic_scan

    full_first = scan(first_scene, full_snapshot)
    partial_first = scan(second_scene, partial_snapshot)
    assert len(full_first.measurements) > len(partial_first.measurements)

    full_follow_up = scan(first_scene, full_snapshot)
    partial_follow_up = scan(second_scene, full_snapshot)
    assert len(full_follow_up.measurements) == len(partial_follow_up.measurements)
    for left, right in zip(full_follow_up.measurements, partial_follow_up.measurements):
        assert left.observation_id == right.observation_id
        assert np.array_equal(left.measurement, right.measurement)
        assert left.metadata["random_schedule_version"] == "entity_fixed_v1"


def test_sensor_random_schedule_version_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="sensor_random_schedule_version"):
        ScenarioConfig(sensor_random_schedule_version="unknown")


def test_noisy_bbox_clipping_drops_outside_boxes_and_keeps_positive_geometry() -> None:
    intrinsics = CameraIntrinsics.from_horizontal_fov(
        width_px=640,
        height_px=480,
        horizontal_fov_deg=90.0,
    )

    assert _clip_noisy_bbox(
        np.array([-20.0, 200.0]),
        10.0,
        10.0,
        intrinsics,
    ) is None
    clipped = _clip_noisy_bbox(
        np.array([2.0, 200.0]),
        10.0,
        12.0,
        intrinsics,
    )

    assert clipped is not None
    center, bbox, area = clipped
    assert bbox[2] > bbox[0]
    assert bbox[3] > bbox[1]
    assert np.allclose(center, [(bbox[0] + bbox[2]) / 2.0, 200.0])
    assert area == (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def test_camera_view_accepts_per_camera_fov_without_changing_other_cameras() -> None:
    config = ScenarioConfig(
        target_count=2,
        resource_count=2,
        recon_count=1,
        duration_s=0.1,
    )
    snapshot = VectorizedPointMassWorld(config).snapshot()
    scene = SensorScene(config)

    baseline = {view.sensor_id: view for view in scene.camera_views(snapshot)}
    overridden = {
        view.sensor_id: view
        for view in scene.camera_views(
            snapshot,
            camera_horizontal_fov_deg={"CAM-INT-0001": 30.0},
        )
    }

    assert overridden["CAM-INT-0001"].intrinsics.fx > baseline["CAM-INT-0001"].intrinsics.fx
    assert overridden["CAM-INT-0002"].intrinsics.fx == baseline["CAM-INT-0002"].intrinsics.fx
    assert overridden["CAM-RECON-001"].intrinsics.fx == baseline["CAM-RECON-001"].intrinsics.fx


def test_acoustic_bearing_has_class_hint_but_no_online_identity() -> None:
    config = ScenarioConfig(
        target_count=2,
        resource_count=2,
        recon_count=1,
        duration_s=0.1,
        acoustic_detection_probability=1.0,
        acoustic_range_limit_m=5_000.0,
    )
    world = VectorizedPointMassWorld(config)
    world.intruder_state[:, :3] = np.array(
        [[1_000.0, 0.0, -120.0], [0.0, 1_100.0, -140.0]], dtype=float
    )
    batch = SensorScene(config).acoustic_scan(world.snapshot())
    assert batch.measurements
    for measurement in batch.measurements:
        assert measurement.modality == "acoustic_bearing"
        assert measurement.classification_hint == "unmanned_aircraft"
        assert measurement.metadata["soundprint_is_identity"] is False
        assert_online_payload_truth_free(measurement)
