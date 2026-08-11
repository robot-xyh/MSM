from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import airsim_runtime.long_range_cv_scan as scan_module
from airsim_runtime.long_range_cv_scan import (
    CENTER_CAMERA_SPEC,
    INTERCEPTOR_CAMERA_NAME,
    INTERCEPTOR_CAMERA_SPEC,
    LongRangeCVScenario,
    LongRangeEpisodeResult,
    SectorScanScheduler,
    VelocityAwareAnonymousTracker,
    accepted_measured_pairs,
    build_serpentine_scan_grid,
    build_temporal_geometric_associators,
    crossing_geometry_preflight,
    derive_interceptor_camera_spec,
    derive_pitch_search_plan,
    evaluate_mot_continuity,
    generate_long_range_target_specs,
    minimum_target_separation,
    pixel_to_world_unit_ray,
    projected_trajectory_crossing_count,
    run_long_range_cv_campaign,
    scan_mode_definition,
    snapshot_frame_indices,
    world_ray_velocity_to_pixel_rate,
    write_long_range_cv_settings,
)
from airsim_dryrun.models import AirSimCameraInfo, AirSimDetectionBox
from airsim_runtime.long_range_mot_reaudit import camera_info_from_gimbal_record
from airsim_runtime.models import BlocksSmokeConfig
from airsim_runtime.real_runtime import RealAirSimRuntimeClient
from d5_terminal_association import CameraModel, GlobalTrack, LocalVisualTrack


class FakeAirSimModule:
    class ImageType:
        Scene = 0

    class Vector3r:
        def __init__(self, x_val=0.0, y_val=0.0, z_val=0.0):
            self.x_val = float(x_val)
            self.y_val = float(y_val)
            self.z_val = float(z_val)

    class Quaternionr:
        def __init__(self, x_val=0.0, y_val=0.0, z_val=0.0, w_val=1.0):
            self.x_val = float(x_val)
            self.y_val = float(y_val)
            self.z_val = float(z_val)
            self.w_val = float(w_val)

    class Pose:
        def __init__(self, position_val=None, orientation_val=None):
            self.position = position_val or FakeAirSimModule.Vector3r()
            self.orientation = orientation_val or FakeAirSimModule.Quaternionr()

    class ImageRequest:
        def __init__(self, camera_name, image_type, pixels_as_float=False, compress=True):
            self.camera_name = camera_name
            self.image_type = image_type
            self.pixels_as_float = pixels_as_float
            self.compress = compress


class FakeLongRangeClient:
    def __init__(self, settings: dict, *, return_detections: bool = True) -> None:
        self.settings = settings
        self.return_detections = return_detections
        self.object_poses: dict[str, object] = {}
        self.vehicle_poses: dict[str, object] = {}
        self.camera_poses: dict[str, object] = {}
        self.camera_fovs: dict[str, float] = {}
        self.calls: list[tuple] = []
        self.detection_filters: dict[str, list[str]] = {}
        self.detection_radii_cm: dict[str, int] = {}

    def ping(self):
        return True

    def reset(self):
        self.calls.append(("reset",))

    def listVehicles(self):
        return list(self.settings["Vehicles"])

    def simPause(self, paused):
        self.calls.append(("simPause", bool(paused)))
        return True

    def simContinueForTime(self, duration):
        self.calls.append(("simContinueForTime", float(duration)))
        return True

    def simSetCameraPose(self, camera_name, pose, vehicle_name=""):
        self.calls.append(("simSetCameraPose", camera_name, vehicle_name))
        self.camera_poses[vehicle_name] = pose
        return True

    def simSetCameraFov(self, camera_name, fov_degrees, vehicle_name="", external=False):
        self.calls.append(("simSetCameraFov", camera_name, vehicle_name, float(fov_degrees)))
        self.camera_fovs[vehicle_name] = float(fov_degrees)
        return True

    def simSetVehiclePose(self, pose, ignore_collision=True, vehicle_name=""):
        self.calls.append(("simSetVehiclePose", vehicle_name))
        self.vehicle_poses[vehicle_name] = pose
        return True

    def simGetVehiclePose(self, vehicle_name=""):
        return self.vehicle_poses.get(vehicle_name, FakeAirSimModule.Pose())

    def simGetCameraInfo(self, camera_name, vehicle_name=""):
        capture = self.settings["Vehicles"][vehicle_name]["Cameras"][camera_name]["CaptureSettings"][0]
        vehicle_pose = self.vehicle_poses.get(vehicle_name, FakeAirSimModule.Pose())
        camera_pose = self.camera_poses.get(vehicle_name, FakeAirSimModule.Pose())
        pose = FakeAirSimModule.Pose(vehicle_pose.position, camera_pose.orientation)
        return SimpleNamespace(
            pose=pose,
            fov=self.camera_fovs.get(vehicle_name, float(capture["FOV_Degrees"])),
        )

    def simGetImages(self, requests, vehicle_name="", external=False):
        capture = self.settings["Vehicles"][vehicle_name]["Cameras"]["0"]["CaptureSettings"][0]
        return [
            SimpleNamespace(
                image_data_uint8=b"not-saved",
                width=int(capture["Width"]),
                height=int(capture["Height"]),
                image_type=0,
            )
        ]

    def simListSceneObjects(self, regex=".*"):
        return list(self.object_poses)

    def simDestroyObject(self, object_name):
        self.object_poses.pop(object_name, None)
        self.calls.append(("simDestroyObject", object_name))
        return True

    def simSpawnObject(self, object_name, asset_name, pose, scale, physics_enabled=False):
        self.object_poses[object_name] = pose
        self.calls.append(("simSpawnObject", object_name, asset_name))
        return object_name

    def simSetObjectPose(self, object_name, pose, teleport=True):
        self.object_poses[object_name] = pose
        self.calls.append(("simSetObjectPose", object_name))
        return True

    def simGetObjectPose(self, object_name):
        return self.object_poses[object_name]

    def simClearDetectionMeshNames(self, camera_name, image_type, vehicle_name="", external=False):
        self.detection_filters[vehicle_name] = []

    def simSetDetectionFilterRadius(self, camera_name, image_type, radius_cm, vehicle_name="", external=False):
        self.detection_radii_cm[vehicle_name] = int(radius_cm)

    def simAddDetectionFilterMeshName(self, camera_name, image_type, mesh_name, vehicle_name="", external=False):
        self.detection_filters.setdefault(vehicle_name, []).append(mesh_name)

    def simGetDetections(self, camera_name, image_type, vehicle_name="", external=False):
        if not self.return_detections:
            return []
        return [
            SimpleNamespace(
                name=name,
                box2D=SimpleNamespace(
                    min=SimpleNamespace(x_val=1200.0, y_val=1000.0),
                    max=SimpleNamespace(x_val=1240.0, y_val=1040.0),
                ),
                relative_pose=FakeAirSimModule.Pose(),
                box3D=None,
            )
            for name in sorted(self.object_poses)
            if name.startswith("MSM_TargetActor_")
        ]


def _runtime(settings: dict, *, return_detections: bool = True):
    client = FakeLongRangeClient(settings, return_detections=return_detections)
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_kwargs: client,
        airsim_module=FakeAirSimModule,
    )
    return runtime, client


def _project_world_ray(camera_info: AirSimCameraInfo, ray_ned: tuple[float, float, float]) -> tuple[float, float]:
    camera_ray = np.asarray(camera_info.rotation_world_to_camera, dtype=float) @ np.asarray(
        ray_ned, dtype=float
    )
    return (
        camera_info.fx * camera_ray[0] / camera_ray[2] + camera_info.cx,
        camera_info.fy * camera_ray[1] / camera_ray[2] + camera_info.cy,
    )


def _temporal_camera() -> CameraModel:
    return CameraModel(
        K=np.array([[100.0, 0.0, 320.0], [0.0, 100.0, 240.0], [0.0, 0.0, 1.0]]),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
        measurement_cov=np.diag([4.0, 4.0]),
    )


def _temporal_global(track_id: str, pixel_u: float) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=track_id,
        position=np.array([(pixel_u - 320.0) * 0.2, 0.0, 20.0]),
        covariance=np.diag([0.02, 0.02, 0.02]),
    )


def _temporal_local(
    local_id: str,
    pixel_u: float,
    timestamp: float,
    *,
    state: str = "measured",
    bearing_rate: tuple[float, float] = (0.0, 0.0),
) -> LocalVisualTrack:
    return LocalVisualTrack(
        local_track_id=local_id,
        center_px=np.array([pixel_u, 240.0]),
        bbox=(pixel_u - 5.0, 235.0, pixel_u + 5.0, 245.0),
        bearing_rate=np.array(bearing_rate),
        quality=0.95,
        mot_history_length=5,
        timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        local_track_state=state,
        prediction_age_s=(0.1 if state != "measured" else None),
    )


def _temporal_frame(
    associator,
    globals_,
    locals_,
    timestamp: float,
    *,
    frame_id: str,
):
    return associator.associate(
        globals_,
        locals_,
        _temporal_camera(),
        resource_id="Camera",
        camera_id="Camera:0",
        stream_id="episode:test",
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        frame_id=frame_id,
    )


@pytest.mark.parametrize("gap_s", (0.06, 0.10, 0.17))
def test_runtime_temporal_bridge_coasts_without_authorizing_then_recovers(
    gap_s: float,
) -> None:
    scenario = LongRangeCVScenario(target_count=1)
    associator = build_temporal_geometric_associators(scenario, ("Camera",))["Camera"]
    globals_ = [_temporal_global("G1", 320.0)]
    initial = _temporal_frame(
        associator,
        globals_,
        [_temporal_local("anon-1", 320.0, 1.0, bearing_rate=(20.0, -10.0))],
        1.0,
        frame_id="initial",
    )
    coast = _temporal_frame(
        associator,
        globals_,
        [],
        1.0 + gap_s,
        frame_id=f"coast-{gap_s}",
    )
    recovered = _temporal_frame(
        associator,
        globals_,
        [_temporal_local("anon-1", 320.0, 1.0 + gap_s + 0.001)],
        1.0 + gap_s + 0.001,
        frame_id=f"recovered-{gap_s}",
    )

    assert len(accepted_measured_pairs(initial)) == 1
    assert accepted_measured_pairs(coast) == []
    assert coast.measured_assignments == {}
    assert coast.active_bindings == {"anon-1": "G1"}
    assert coast.coasted_records[0].prediction_age_s == pytest.approx(gap_s)
    assert coast.coasted_records[0].to_log_record()["terminal_authorization_allowed"] is False
    assert recovered.measured_assignments == {"G1": "anon-1"}
    assert recovered.binding_events[-1].event == "recovered"


def test_runtime_temporal_bridge_holds_one_frame_and_confirms_two_frame_challenger() -> None:
    scenario = LongRangeCVScenario(target_count=2)
    associator = build_temporal_geometric_associators(scenario, ("Camera",))["Camera"]
    globals_ = [_temporal_global("G1", 320.0), _temporal_global("G2", 340.0)]
    _temporal_frame(
        associator,
        globals_,
        [_temporal_local("anon-1", 320.0, 1.0)],
        1.0,
        frame_id="initial",
    )
    first = _temporal_frame(
        associator,
        globals_,
        [_temporal_local("anon-1", 340.0, 1.1)],
        1.1,
        frame_id="challenger-1",
    )
    second = _temporal_frame(
        associator,
        globals_,
        [_temporal_local("anon-1", 340.0, 1.2)],
        1.2,
        frame_id="challenger-2",
    )

    assert first.binding_events[-1].event == "pending"
    assert first.measured_assignments == {}
    assert accepted_measured_pairs(first) == []
    assert second.binding_events[-1].event == "confirmed"
    assert second.binding_events[-1].incumbent_global_track_id == "G1"
    assert second.measured_assignments == {"G2": "anon-1"}
    assert len(accepted_measured_pairs(second)) == 1


def test_runtime_temporal_bridge_predicted_input_and_episode_state_are_isolated() -> None:
    scenario = LongRangeCVScenario(target_count=2)
    associators = build_temporal_geometric_associators(scenario, ("Camera-A", "Camera-B"))
    assert associators["Camera-A"] is not associators["Camera-B"]
    globals_ = [_temporal_global("G1", 320.0), _temporal_global("G2", 340.0)]
    _temporal_frame(
        associators["Camera-A"],
        globals_,
        [_temporal_local("anon-1", 320.0, 1.0)],
        1.0,
        frame_id="camera-a-initial",
    )
    _temporal_frame(
        associators["Camera-B"],
        globals_,
        [_temporal_local("anon-1", 340.0, 1.0)],
        1.0,
        frame_id="camera-b-initial",
    )
    predicted = _temporal_frame(
        associators["Camera-A"],
        globals_,
        [_temporal_local("anon-1", 321.0, 1.1, state="predicted")],
        1.1,
        frame_id="camera-a-predicted",
    )
    associators["Camera-A"].reset(reason="episode_reset")
    continued_b = _temporal_frame(
        associators["Camera-B"],
        globals_,
        [_temporal_local("anon-1", 340.0, 1.2)],
        1.2,
        frame_id="camera-b-continued",
    )

    assert predicted.measured_assignments == {}
    assert accepted_measured_pairs(predicted) == []
    assert all(
        row["terminal_authorization_allowed"] is False
        for row in predicted.to_log_records()
    )
    assert continued_b.binding_events[-1].event == "continued"


def test_camera_reverse_design_and_independent_settings(tmp_path: Path) -> None:
    derived = derive_interceptor_camera_spec()
    assert derived.equivalent_focal_length_mm == pytest.approx(100.0)
    assert derived.horizontal_fov_deg == pytest.approx(2.750979, abs=5e-5)
    assert INTERCEPTOR_CAMERA_SPEC.horizontal_fov_deg == pytest.approx(2.750979, abs=1e-9)
    assert INTERCEPTOR_CAMERA_SPEC.vertical_fov_deg == pytest.approx(1.547629, abs=5e-5)
    scenario = LongRangeCVScenario(target_count=3)
    settings_path = write_long_range_cv_settings(
        tmp_path / "settings.json",
        scenario=scenario,
        interceptor_initial_position_ned=(2500.0, 0.0, -100.0),
    )
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["SimMode"] == "ComputerVision"
    assert settings["ClockSpeed"] == 1.0
    assert settings["ViewMode"] == "NoDisplay"
    center = settings["Vehicles"][scenario.center_vehicle_name]["Cameras"]["0"]["CaptureSettings"][0]
    interceptor = settings["Vehicles"][scenario.interceptor_vehicle_name]["Cameras"]["0"]["CaptureSettings"][0]
    assert center == {
        "FOV_Degrees": 0.621,
        "Height": 2160,
        "ImageType": 0,
        "MotionBlurAmount": 0,
        "Width": 2600,
    }
    assert interceptor["Width"] == 1920
    assert interceptor["Height"] == 1080
    assert interceptor["FOV_Degrees"] == pytest.approx(2.750979)


@pytest.mark.parametrize("target_count", (2, 5, 20))
def test_crossing_calibration_profile_is_parameterized_and_preflighted(
    target_count: int,
) -> None:
    scenario = LongRangeCVScenario(
        target_count=target_count,
        duration_s=20.0,
        geometry_profile="crossing_calibration_v1",
    )
    specs = generate_long_range_target_specs(scenario)
    preflight = crossing_geometry_preflight(specs, scenario)

    assert len(specs) == target_count
    assert preflight["passed"] is True
    assert preflight["planned_evaluable_pair_count"] == target_count // 2
    assert preflight["minimum_3d_separation_m"] >= 25.0
    for spec in specs:
        assert np.linalg.norm(spec.velocity_ned) == pytest.approx(50.0)


def test_baseline_geometry_profile_remains_default() -> None:
    default = LongRangeCVScenario(target_count=4, seed=20260810, duration_s=20.0)
    explicit = LongRangeCVScenario(
        target_count=4,
        seed=20260810,
        duration_s=20.0,
        geometry_profile="baseline_v1",
    )
    assert generate_long_range_target_specs(default) == generate_long_range_target_specs(explicit)


def test_world_ray_velocity_projects_to_pixel_rate() -> None:
    camera = SimpleNamespace(
        fx=100.0,
        fy=120.0,
        rotation_world_to_camera=np.eye(3),
    )
    rate = world_ray_velocity_to_pixel_rate(
        camera,
        (0.0, 0.0, 1.0),
        (0.1, -0.2, 0.0),
    )
    assert rate == pytest.approx((10.0, -24.0))


def test_scan_scheduler_steps_reverses_and_requires_five_hits() -> None:
    mechanical = scan_mode_definition("mechanical_2s")
    coverage = scan_mode_definition("coverage_safe")
    assert mechanical.step_deg == pytest.approx(1.8)
    assert coverage.step_deg == pytest.approx(0.621 * 0.8)
    scheduler = SectorScanScheduler(mechanical, dwell_frames=5)
    start_yaw = scheduler.current_yaw_deg
    scheduler.observe((), frame_index=0)
    assert scheduler.current_yaw_deg == pytest.approx(start_yaw + 1.8)
    scheduler.current_yaw_deg = 22.0
    scheduler.direction = 1
    scheduler.observe((), frame_index=1)
    assert scheduler.direction == -1
    assert scheduler.endpoint_reversal_count == 1
    confirmed = scheduler.observe(
        ("GT-0001",),
        frame_index=2,
        preferred_target_id="GT-0001",
        preferred_angles_deg=(3.0, 1.0),
    )
    assert not confirmed
    assert scheduler.state == "dwell"
    for frame_index in range(3, 6):
        assert not scheduler.observe(("GT-0001",), frame_index=frame_index)
    assert scheduler.observe(("GT-0001",), frame_index=6) == ("GT-0001",)
    assert scheduler.state == "scan"


def test_coverage_safe_builds_global_track_covariance_driven_pitch_rows() -> None:
    scenario = LongRangeCVScenario(target_count=20)
    specs = generate_long_range_target_specs(scenario)
    tracks, _positions = scan_module._global_tracks(
        specs,
        0.0,
        position_sigma_m=scenario.global_track_position_sigma_m,
    )
    plan = derive_pitch_search_plan(
        tracks,
        camera_position_ned=scenario.center_position_ned,
        overlap_ratio=scenario.scan_overlap_ratio,
    )
    grid = build_serpentine_scan_grid(
        min_yaw_deg=scenario.search_sector_min_deg,
        max_yaw_deg=scenario.search_sector_max_deg,
        min_pitch_deg=plan.min_pitch_deg,
        max_pitch_deg=plan.max_pitch_deg,
        horizontal_fov_deg=CENTER_CAMERA_SPEC.horizontal_fov_deg,
        vertical_fov_deg=CENTER_CAMERA_SPEC.vertical_fov_deg,
        overlap_ratio=scenario.scan_overlap_ratio,
    )

    pitch_rows = tuple(dict.fromkeys(pitch for _yaw, pitch in grid))
    assert plan.source == "center_global_tracks_with_covariance"
    assert plan.source_track_count == scenario.target_count
    assert len(pitch_rows) > 1
    assert pitch_rows == tuple(sorted(pitch_rows))
    first_row = [yaw for yaw, pitch in grid if pitch == pitch_rows[0]]
    second_row = [yaw for yaw, pitch in grid if pitch == pitch_rows[1]]
    assert first_row == sorted(first_row)
    assert second_row == sorted(second_row, reverse=True)
    assert max(abs(right - left) for left, right in zip(first_row, first_row[1:])) <= (
        CENTER_CAMERA_SPEC.horizontal_fov_deg * 0.8 + 1e-9
    )


def test_target_geometry_is_parameterized_staggered_and_crossing() -> None:
    scenario = LongRangeCVScenario(target_count=20, seed=20260810)
    specs = generate_long_range_target_specs(scenario)
    assert len(specs) == 20
    ranges = [spec.start_ned[0] for spec in specs]
    assert min(ranges) >= scenario.target_range_min_m
    assert max(ranges) <= scenario.target_range_max_m
    assert max(ranges) - min(ranges) >= 300.0
    speeds = [math.sqrt(sum(value * value for value in spec.velocity_ned)) for spec in specs]
    assert all(speed == pytest.approx(50.0, abs=1e-9) for speed in speeds)
    assert all(spec.velocity_ned[0] < 0.0 for spec in specs)
    assert all(
        sum(
            (spec.start_ned[index] - scenario.center_position_ned[index])
            * spec.velocity_ned[index]
            for index in range(3)
        )
        < 0.0
        for spec in specs
    )
    assert minimum_target_separation(specs, duration_s=scenario.duration_s) >= 25.0
    assert projected_trajectory_crossing_count(
        specs,
        camera_position_ned=scenario.center_position_ned,
        duration_s=scenario.duration_s,
    ) >= 8
    assert len(generate_long_range_target_specs(LongRangeCVScenario(target_count=7))) == 7


def test_runtime_uses_camera_pose_and_keeps_detection_truth_offline(tmp_path: Path) -> None:
    scenario = LongRangeCVScenario(target_count=1)
    target_specs = generate_long_range_target_specs(scenario)
    settings_path = write_long_range_cv_settings(
        tmp_path / "settings.json",
        scenario=scenario,
        interceptor_initial_position_ned=(2500.0, 0.0, -100.0),
    )
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    runtime, client = _runtime(settings)
    config = BlocksSmokeConfig(
        episode_id="pytest_long_range",
        settings_path=settings_path,
        camera_vehicle_name=scenario.center_vehicle_name,
        camera_vehicle_names=(scenario.center_vehicle_name, scenario.interceptor_vehicle_name),
        target_vehicle_names=(),
        resource_vehicle_names=(scenario.interceptor_vehicle_name,),
        target_actor_specs=target_specs,
        detection_filter_names=("MSM_TargetActor_*",),
        detection_radius_cm=350_000,
        capture_lidar=False,
    )
    runtime.setup_episode(config)
    vehicle_call_count = sum(call[0] == "simSetVehiclePose" for call in client.calls)
    result = runtime.set_cv_camera_gimbal_pose(
        vehicle_name=scenario.center_vehicle_name,
        camera_name="0",
        yaw_deg=4.0,
        pitch_deg=1.0,
    )
    assert result["ok"] is True
    assert result["api"] == "simSetCameraPose"
    assert sum(call[0] == "simSetVehiclePose" for call in client.calls) == vehicle_call_count
    assert any(call[0] == "simSetCameraPose" for call in client.calls)
    assert client.detection_radii_cm[scenario.center_vehicle_name] == 350_000
    assert "MSM_TargetActor_*" in client.detection_filters[scenario.center_vehicle_name]
    online, offline, metadata = runtime.capture_anonymous_cv_detections(
        config,
        frame_index=0,
        measurement_timestamp=1.25,
        vehicle_name=scenario.center_vehicle_name,
    )
    assert len(online) == len(offline) == 1
    assert online[0].object_id == ""
    assert "offline_truth_actor_name" not in online[0].metadata
    assert "relative_pose" not in online[0].metadata
    assert online[0].metadata["online_truth_identity_used"] is False
    assert offline[0]["actor_name"] == "MSM_TargetActor_1"
    assert offline[0]["offline_truth_only"] is True
    assert metadata["arrival_timestamp"] >= metadata["measurement_timestamp"]


def test_snapshot_schedule_is_endpoint_inclusive() -> None:
    assert snapshot_frame_indices(
        duration_s=12.0,
        logic_rate_hz=100.0,
        interval_s=2.0,
    ) == (0, 200, 400, 600, 800, 1000, 1200)


def test_velocity_tracker_preserves_anonymous_ids_through_crossing() -> None:
    tracker = VelocityAwareAnonymousTracker("Camera:0", max_coast_s=0.5)
    score_rows = []
    for frame_index in range(11):
        timestamp = frame_index * 0.01
        camera_info = camera_info_from_gimbal_record(
            vehicle_name=INTERCEPTOR_CAMERA_NAME,
            frame_index=frame_index,
            timestamp=timestamp,
            yaw_deg=0.0,
            pitch_deg=0.0,
            position_ned=(0.0, 0.0, 0.0),
        )
        observations = [
            ("GT-0001", 100.0 + 18.0 * frame_index, 30.0),
            ("GT-0002", 300.0 - 20.0 * frame_index, 42.0),
        ]
        if frame_index % 2:
            observations.reverse()
        detections = tuple(
            AirSimDetectionBox(
                detection_id=f"det:{frame_index}:{index}",
                camera_id="Camera:0",
                object_id="",
                local_track_id="",
                timestamp=timestamp,
                center_px=(u, 200.0),
                bbox_xyxy=(u - size / 2.0, 200.0 - size / 2.0, u + size / 2.0, 200.0 + size / 2.0),
                metadata={"online_truth_identity_used": False},
            )
            for index, (_truth, u, size) in enumerate(observations)
        )
        tracked = tracker.update(
            detections,
            timestamp=timestamp,
            frame_index=frame_index,
            camera_info=camera_info,
        )
        for (truth_id, _u, _size), detection in zip(observations, tracked):
            assert detection.object_id == ""
            assert detection.metadata["online_truth_identity_used"] is False
            score_rows.append(
                {
                    "frame_index": frame_index,
                    "measurement_timestamp": timestamp,
                    "camera_vehicle_name": "Camera",
                    "local_track_id": detection.local_track_id,
                    "truth_global_track_id": truth_id,
                }
            )
    metrics = evaluate_mot_continuity(
        score_rows,
        crossing_windows=(
            {
                "camera_vehicle_name": "Camera",
                "target_a_global_track_id": "GT-0001",
                "target_b_global_track_id": "GT-0002",
                "window_start_timestamp": 0.04,
                "window_end_timestamp": 0.07,
            },
        ),
    )["aggregate"]
    assert metrics["id_switch_count"] == 0
    assert metrics["fragmentation_count"] == 0
    assert metrics["track_purity"] == pytest.approx(1.0)
    assert metrics["crossing_track_purity"] == pytest.approx(1.0)
    assert metrics["gate_passed"] is True


def test_world_ray_tracker_compensates_large_camera_yaw_change() -> None:
    tracker = VelocityAwareAnonymousTracker("Camera:0", max_coast_s=0.5)
    target_yaw = math.radians(5.0)
    world_ray = (math.cos(target_yaw), math.sin(target_yaw), 0.0)
    local_ids = []
    for frame_index, camera_yaw in enumerate((0.0, 20.0)):
        camera_info = camera_info_from_gimbal_record(
            vehicle_name=INTERCEPTOR_CAMERA_NAME,
            frame_index=frame_index,
            timestamp=frame_index * 0.01,
            yaw_deg=camera_yaw,
            pitch_deg=0.0,
            position_ned=(0.0, 0.0, 0.0),
        )
        pixel = _project_world_ray(camera_info, world_ray)
        detection = AirSimDetectionBox(
            detection_id=f"det:{frame_index}",
            camera_id="Camera:0",
            object_id="",
            local_track_id="",
            timestamp=frame_index * 0.01,
            center_px=pixel,
            bbox_xyxy=(pixel[0] - 20.0, pixel[1] - 20.0, pixel[0] + 20.0, pixel[1] + 20.0),
            metadata={"online_truth_identity_used": False},
        )
        tracked = tracker.update(
            (detection,),
            timestamp=frame_index * 0.01,
            frame_index=frame_index,
            camera_info=camera_info,
        )[0]
        local_ids.append(tracked.local_track_id)
        assert tracked.object_id == ""
        assert tracked.metadata["camera_motion_compensated"] is True
        assert tracked.metadata["online_truth_identity_used"] is False
        assert pixel_to_world_unit_ray(pixel, camera_info) == pytest.approx(world_ray)
    assert len(set(local_ids)) == 1


def test_long_absence_is_reacquisition_not_visible_segment_switch() -> None:
    rows = [
        {
            "camera_vehicle_name": "Camera",
            "frame_index": 0,
            "measurement_timestamp": 0.00,
            "local_track_id": "local-1",
            "truth_global_track_id": "GT-0001",
        },
        {
            "camera_vehicle_name": "Camera",
            "frame_index": 1,
            "measurement_timestamp": 0.01,
            "local_track_id": "local-1",
            "truth_global_track_id": "GT-0001",
        },
        {
            "camera_vehicle_name": "Camera",
            "frame_index": 100,
            "measurement_timestamp": 1.00,
            "local_track_id": "local-2",
            "truth_global_track_id": "GT-0001",
        },
    ]
    metrics = evaluate_mot_continuity(rows)["aggregate"]
    assert metrics["raw_total_id_switch_count"] == 1
    assert metrics["raw_total_fragmentation_count"] == 1
    assert metrics["id_switch_count"] == 0
    assert metrics["fragmentation_count"] == 0
    assert metrics["reacquisition_count"] == 1
    assert metrics["reacquisition_identity_changed_count"] == 1
    assert metrics["crossing_availability"] is False
    assert metrics["gate_passed"] is False


def test_crossing_metrics_are_pair_specific_and_unavailable_pairs_do_not_pass() -> None:
    rows = []
    for frame_index in range(4):
        for truth_id, local_id in (
            ("GT-A", "local-a"),
            ("GT-B", "local-b"),
            ("GT-X", "local-x-1" if frame_index < 2 else "local-x-2"),
        ):
            rows.append(
                {
                    "camera_vehicle_name": "Camera",
                    "frame_index": frame_index,
                    "measurement_timestamp": frame_index * 0.01,
                    "local_track_id": local_id,
                    "truth_global_track_id": truth_id,
                }
            )
    windows = (
        {
            "camera_vehicle_name": "Camera",
            "target_a_global_track_id": "GT-A",
            "target_b_global_track_id": "GT-B",
            "window_start_timestamp": 0.0,
            "window_end_timestamp": 0.03,
        },
        {
            "camera_vehicle_name": "Camera",
            "target_a_global_track_id": "GT-C",
            "target_b_global_track_id": "GT-D",
            "window_start_timestamp": 0.0,
            "window_end_timestamp": 0.03,
        },
    )
    metrics = evaluate_mot_continuity(rows, crossing_windows=windows)["aggregate"]
    assert metrics["crossing_window_count"] == 2
    assert metrics["crossing_evaluable_window_count"] == 1
    assert metrics["crossing_not_evaluable_window_count"] == 1
    assert metrics["crossing_id_switch_count"] == 0
    assert metrics["crossing_track_purity"] == pytest.approx(1.0)
    unavailable = [
        row for row in metrics["crossing_window_results"] if not row["availability"]
    ]
    assert unavailable[0]["status"] == "not_evaluable"
    assert "missing_pair_observation" in unavailable[0]["unavailable_reason"]


def test_mock_mode_writes_periodic_snapshots_and_complete_records(tmp_path: Path) -> None:
    scenario = LongRangeCVScenario(
        target_count=1,
        duration_s=1.2,
        logic_rate_hz=10.0,
        capture_registration_events=False,
    )
    target_specs = generate_long_range_target_specs(scenario)
    settings_path = write_long_range_cv_settings(
        tmp_path / "settings.json",
        scenario=scenario,
        interceptor_initial_position_ned=(2500.0, 0.0, -100.0),
    )
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    runtime, client = _runtime(settings)
    result = scan_module._run_long_range_mode(
        runtime,
        scenario=scenario,
        target_specs=target_specs,
        settings_path=settings_path,
        output_dir=tmp_path / "mechanical_2s",
        mode="mechanical_2s",
    )
    assert result.metrics["online_truth_identity_use_count"] == 0
    assert result.metrics["global_track_id_rewrite_count"] == 0
    assert result.metrics["target_count"] == 1
    assert result.metrics["temporal_association"][
        "predicted_record_authorization_count"
    ] == 0
    assert result.metrics["temporal_association"]["episode_scoped_state"] is True
    assert all(
        validation["ok"]
        for validation in result.metrics["camera_validation"].values()
    )
    assert result.output_paths["metrics_json"].exists()
    assert result.output_paths["report"].exists()
    assert result.output_paths["gimbal_yaw_curve"].exists()
    assert not list(result.output_dir.glob("*.png")) == []
    snapshots = sorted(result.output_dir.rglob("frame_*_scene.png"))
    assert len(snapshots) == 2
    assert result.metrics["snapshot_saved_count"] == 2
    assert result.metrics["snapshot_capture_passed"] is True
    assert not any(
        path.suffix.lower() in {".mp4", ".gif", ".avi", ".mov", ".mkv"}
        for path in result.output_dir.rglob("*")
    )
    manifest = json.loads(result.output_paths["record_manifest"].read_text(encoding="utf-8"))
    assert manifest["missing_required_records"] == []
    assert manifest["video_generated"] is False
    for name in (
        "scan_plan_json",
        "cue_plan_csv",
        "actor_trajectory_truth_csv",
        "global_tracks_csv",
        "temporal_binding_events_csv",
        "dropout_events_csv",
        "mot_continuity_json",
        "latency_rpc_csv",
        "snapshots_manifest_csv",
        "d6_per_episode_csv",
        "d6_aggregate_json",
        "d6_markdown",
        "d6_plot",
        "d6_evaluation_index",
    ):
        assert result.output_paths[name].exists()
    d6_index = json.loads(
        result.output_paths["d6_evaluation_index"].read_text(encoding="utf-8")
    )
    assert d6_index["control_authority"] is False
    assert d6_index["p1_closed"] is False
    assert d6_index["status"] == "fail_closed"
    detection_text = result.output_paths["detections_jsonl"].read_text(encoding="utf-8")
    assert "MSM_TargetActor" not in detection_text
    detection_csv = result.output_paths["detections_csv"].read_text(encoding="utf-8")
    assert "measurement_timestamp" in detection_csv
    assert "arrival_timestamp" in detection_csv
    assert "covariance_uu" in detection_csv
    assert any(call[0] == "simSetCameraPose" for call in client.calls)
    assert any(call[0] == "simSetCameraFov" for call in client.calls)
    assert any(call[0] == "simSetVehiclePose" for call in client.calls)


def test_offline_actor_lookup_prefers_exact_and_longest_names(tmp_path: Path) -> None:
    scenario = LongRangeCVScenario(target_count=11)
    settings_path = write_long_range_cv_settings(
        tmp_path / "settings.json",
        scenario=scenario,
        interceptor_initial_position_ned=(2500.0, 0.0, -100.0),
    )
    runtime, _client = _runtime(json.loads(settings_path.read_text(encoding="utf-8")))
    runtime._active_actor_targets = {
        "TGT-001": {"actor_name": "MSM_TargetActor_1"},
        "TGT-011": {"actor_name": "MSM_TargetActor_11"},
    }

    assert runtime._object_id_for_actor_name("MSM_TargetActor_11") == "TGT-011"
    assert runtime._object_id_for_actor_name("MSM_TargetActor_11_C_0") == "TGT-011"


def test_campaign_runs_two_modes_with_one_reset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[str] = []

    class FakeRuntime:
        def wait_for_connection(self, timeout):
            events.append("wait")

        def reset(self):
            events.append("reset")

    def fake_run(runtime, *, mode, output_dir, **_kwargs):
        events.append(mode)
        return LongRangeEpisodeResult(
            mode=mode,
            output_dir=output_dir,
            metrics={
                "center_unique_discovery_ratio": 0.5,
                "center_confirmed_ratio": 0.5,
                "interceptor_observed_ratio": 0.5,
                "association_accuracy": 1.0,
                "id_switch_count": 0,
                    "detection_rpc_latency_mean_ms": 1.0,
                    "wall_time_realtime_factor": 1.0,
                    "camera_configuration_passed": True,
                    "coverage_gate_required": mode == "coverage_safe",
                    "coverage_gate_passed": mode == "mechanical_2s",
            },
            output_paths={},
        )

    monkeypatch.setattr(scan_module, "_run_long_range_mode", fake_run)
    result = run_long_range_cv_campaign(
        scenario=LongRangeCVScenario(target_count=2),
        output_dir=tmp_path / "campaign",
        modes=("mechanical_2s", "coverage_safe"),
        launch_blocks=False,
        runtime=FakeRuntime(),
    )
    assert events == ["wait", "mechanical_2s", "reset", "wait", "coverage_safe"]
    assert [episode.mode for episode in result.episode_results] == [
        "mechanical_2s",
        "coverage_safe",
    ]
    assert result.output_paths["comparison_report"].exists()
