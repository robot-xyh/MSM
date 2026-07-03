from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from airsim_dryrun.models import (
    AirSimDetectionBox,
    AirSimFrame,
    AirSimResourceState,
    AirSimTruthObject,
)
from airsim_runtime.adapters import (
    local_visual_tracks_from_blocks_frame,
    observations_from_blocks_frame,
    resources_from_blocks_frame,
    truth_states_from_blocks_frame,
)
from airsim_runtime.blocks import BlocksProcessManager
from airsim_runtime.d4d5_stress import run_d4d5_stress_analysis
from airsim_runtime.models import (
    BlocksActorTargetSpec,
    BlocksEpisodeSpec,
    BlocksSmokeConfig,
    default_cv_5v5_actor_target_specs,
    default_cv_5v5_d4d5_stress_actor_target_specs,
    default_cv_5v5_camera_vehicle_names,
    default_cv_5v5_secondary_vehicle_names,
)
from airsim_runtime.orchestrator import AirSimBlocksSmokeOrchestrator
from airsim_runtime.real_runtime import RealAirSimRuntimeClient
from airsim_runtime.sequence import AirSimBlocksSequenceOrchestrator, D4D5_STRESS_EPISODES


def test_repo_blocks_settings_are_valid_and_enable_lidar() -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_smoke_settings.json")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert settings["SimMode"] == "Multirotor"
    assert settings["EnableRpc"] is True
    assert settings["RpcEnabled"] is True
    assert settings["ApiServerPort"] == 41451
    assert settings["LocalHostIp"] == "127.0.0.1"
    assert settings["ViewMode"] == "NoDisplay"
    assert set(settings["Vehicles"]) == {"Interceptor", "Intruder"}
    assert settings["Vehicles"]["Interceptor"]["DefaultVehicleState"] == "Inactive"
    assert settings["Vehicles"]["Intruder"]["DefaultVehicleState"] == "Inactive"
    for vehicle in settings["Vehicles"].values():
        assert vehicle["Z"] == 0
        assert vehicle["EnableCollisions"] is True
        assert vehicle["EnableCollisionPassthrogh"] is False
    lidar = settings["Vehicles"]["Interceptor"]["Sensors"]["LidarSensor1"]
    assert lidar["SensorType"] == 6
    assert lidar["Enabled"] is True


def test_minimal_blocks_settings_are_available_for_rpc_diagnostics() -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_minimal_settings.json")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert settings["SimMode"] == "Multirotor"
    assert settings["EnableRpc"] is True
    assert settings["RpcEnabled"] is True
    assert settings["ApiServerPort"] == 41451
    assert settings["ViewMode"] == "NoDisplay"
    assert list(settings["Vehicles"]) == ["Drone1"]
    assert settings["Vehicles"]["Drone1"]["DefaultVehicleState"] == "Inactive"
    assert settings["Vehicles"]["Drone1"]["Z"] == 0
    assert settings["Vehicles"]["Drone1"]["EnableCollisions"] is True
    assert settings["Vehicles"]["Drone1"]["EnableCollisionPassthrogh"] is False
    assert "Sensors" not in settings["Vehicles"]["Drone1"]


def test_computer_vision_settings_are_available_for_rpc_diagnostics() -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_cv_rpc_settings.json")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert settings["SimMode"] == "ComputerVision"
    assert settings["EnableRpc"] is True
    assert settings["RpcEnabled"] is True
    assert settings["ApiServerPort"] == 41451
    assert settings["ViewMode"] == "NoDisplay"
    assert "Vehicles" not in settings


def test_computer_vision_5v5_settings_define_camera_actors() -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_cv_5v5_settings.json")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()
    assert settings["SimMode"] == "ComputerVision"
    assert settings["EnableRpc"] is True
    assert settings["ApiServerPort"] == 41451
    assert set(settings["Vehicles"]) == {*resources, *secondaries}
    for name in (*resources, *secondaries):
        assert settings["Vehicles"][name]["VehicleType"] == "ComputerVision"
        assert "Sensors" not in settings["Vehicles"][name]


def test_computer_vision_5v5_d4d5_stress_settings_define_requested_geometry() -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_cv_5v5_d4d5_stress_settings.json")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()
    vehicles = settings["Vehicles"]
    assert settings["SimMode"] == "ComputerVision"
    assert set(vehicles) == {*resources, *secondaries}
    assert [vehicles[name]["Y"] for name in resources] == [-40, -20, 0, 20, 40]
    assert all(vehicles[name]["X"] == 0 for name in resources)
    assert [vehicles[name]["Z"] for name in secondaries] == [-60, -60]
    assert "Cameras" not in vehicles["Secondary_Recon_1"]


def test_default_cv_5v5_actor_specs_are_five_crossing_targets() -> None:
    specs = default_cv_5v5_actor_target_specs(target_z=-10.0)

    assert len(specs) == 5
    assert [spec.object_id for spec in specs] == [
        "TGT-001",
        "TGT-002",
        "TGT-003",
        "TGT-004",
        "TGT-005",
    ]
    assert specs[0].position_at(2.0)[2] == -10.0
    assert specs[0].position_at(2.0)[1] > specs[0].start_ned[1]
    assert specs[-1].position_at(2.0)[1] < specs[-1].start_ned[1]


def test_default_cv_5v5_d4d5_stress_actor_specs_match_requested_geometry() -> None:
    specs = default_cv_5v5_d4d5_stress_actor_target_specs()

    assert len(specs) == 5
    assert [spec.start_ned[0] for spec in specs] == [50.0] * 5
    assert [spec.start_ned[1] for spec in specs] == [-40.0, -20.0, 0.0, 20.0, 40.0]
    assert all(spec.start_ned[2] == -10.0 for spec in specs)
    assert all(spec.scale == (10.0, 10.0, 10.0) for spec in specs)


def test_actor_2v2_settings_use_two_inactive_interceptors_without_intruder_vehicle() -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_2v2_actor_settings.json")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert settings["SimMode"] == "Multirotor"
    assert set(settings["Vehicles"]) == {"Interceptor1", "Interceptor2"}
    assert "Intruder" not in settings["Vehicles"]
    for vehicle in settings["Vehicles"].values():
        assert vehicle["VehicleType"] == "SimpleFlight"
        assert vehicle["DefaultVehicleState"] == "Inactive"
        assert vehicle["Z"] == 0
        assert vehicle["EnableCollisions"] is True
        assert vehicle["Sensors"]["LidarSensor1"]["SensorType"] == 6


def test_blocks_smoke_config_reads_rpc_endpoint_from_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"LocalHostIp": "127.0.0.1", "ApiServerPort": 41499}),
        encoding="utf-8",
    )

    config = BlocksSmokeConfig(settings_path=settings_path)

    assert config.api_server_host() == "127.0.0.1"
    assert config.api_server_port() == 41499


def test_blocks_process_manager_uses_repo_settings(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "Blocks.sh"
    settings = tmp_path / "settings.json"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    settings.write_text("{}", encoding="utf-8")
    script.chmod(0o755)
    calls: list[dict[str, object]] = []

    class FakeProcess:
        def poll(self):
            return 0

    def fake_popen(cmd, cwd, stdout, stderr, text, env):
        calls.append(
            {"cmd": cmd, "cwd": cwd, "stdout": stdout, "stderr": stderr, "text": text, "env": env}
        )
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    manager = BlocksProcessManager(script, settings, tmp_path / "out", extra_args=("-windowed",))

    manager.start()

    assert calls
    cmd = calls[0]["cmd"]
    assert str(script.resolve()) == cmd[0]
    assert cmd[1] == f"-settings={settings.resolve()}"
    assert "-windowed" in cmd
    assert calls[0]["env"]["__NV_PRIME_RENDER_OFFLOAD"] == "1"


def test_blocks_process_manager_uses_bash_for_non_executable_script(
    tmp_path: Path, monkeypatch
) -> None:
    script = tmp_path / "Blocks.sh"
    settings = tmp_path / "settings.json"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    settings.write_text("{}", encoding="utf-8")
    script.chmod(0o644)
    calls: list[list[str]] = []

    class FakeProcess:
        def poll(self):
            return 0

    def fake_popen(cmd, cwd, stdout, stderr, text, env):
        calls.append(cmd)
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    manager = BlocksProcessManager(script, settings, tmp_path / "out")

    manager.start()

    assert calls[0][0] == "bash"
    assert calls[0][1] == str(script.resolve())
    assert calls[0][2] == f"-settings={settings.resolve()}"


def test_blocks_process_manager_diagnostics_classify_log(tmp_path: Path) -> None:
    script = tmp_path / "Blocks.sh"
    settings = tmp_path / "settings.json"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    settings.write_text(
        json.dumps(
            {
                "LocalHostIp": "127.0.0.1",
                "ApiServerPort": 41451,
                "Vehicles": {"Drone1": {"VehicleType": "SimpleFlight"}},
            }
        ),
        encoding="utf-8",
    )
    manager = BlocksProcessManager(script, settings, tmp_path / "out")
    manager.output_dir.mkdir(parents=True)
    manager.log_path.write_text(
        "\n".join(
            [
                f"LogInit: Command Line: -settings={settings.resolve()} -windowed",
                f"Loaded settings from {settings.resolve()}",
                "LogLoad: Game class is 'AirSimGameMode'",
                "LogTemp: Drone1",
                "LogInit: Display: Engine is initialized. Leaving FEngineLoop::Init()",
                "LogHMD: Failed to enumerate extensions. Please check that you have a valid OpenXR runtime installed.",
            ]
        ),
        encoding="utf-8",
    )

    diagnostics = manager.diagnostics()

    assert diagnostics["command_line_uses_settings_path"] is True
    assert diagnostics["loaded_settings_path_seen"] is True
    assert diagnostics["game_mode_seen"] is True
    assert diagnostics["engine_initialized_seen"] is True
    assert diagnostics["vehicle_log_hits"]["Drone1"] is True
    assert diagnostics["hmd_error_count"] == 1
    assert diagnostics["rpc_start_failure_seen"] is False


def test_real_runtime_samples_mock_airsim_frame(tmp_path: Path) -> None:
    fake_client = FakeAirSimClient()
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
    )
    config = BlocksSmokeConfig(output_root=tmp_path, duration_s=0.0)

    frame = runtime.sample_frame(config, frame_index=0, timestamp=0.0, output_dir=tmp_path)

    assert frame.metadata["real_airsim_used"] is True
    assert frame.metadata["image"]["ok"] is True
    assert frame.metadata["lidar"]["ok"] is True
    assert frame.truth_objects[0].object_id == "TGT-001"
    assert frame.truth_objects[0].position_ned[0] == 35.0
    assert frame.truth_objects[0].position_ned[1] == -20.0
    assert frame.resources[0].resource_id == "INT-01"
    assert frame.resources[0].position_ned[0] == 0.0
    assert frame.metadata["image"]["saved"] is False
    assert "path" not in frame.metadata["image"]


def test_real_runtime_can_opt_in_to_persist_sampled_images(tmp_path: Path) -> None:
    fake_client = FakeAirSimClient()
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
    )
    config = BlocksSmokeConfig(output_root=tmp_path, duration_s=0.0, save_images=True)

    frame = runtime.sample_frame(config, frame_index=0, timestamp=0.0, output_dir=tmp_path)

    assert frame.metadata["image"]["saved"] is True
    assert Path(frame.metadata["image"]["path"]).exists()


def test_real_runtime_moves_actor_targets_and_captures_builtin_detections(tmp_path: Path) -> None:
    fake_client = FakeAirSimClient()
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
    )
    config = BlocksSmokeConfig(
        output_root=tmp_path,
        duration_s=0.0,
        camera_vehicle_name="Interceptor",
        camera_vehicle_names=("Interceptor",),
        target_vehicle_names=(),
        resource_vehicle_names=("Interceptor",),
        target_actor_specs=(
            BlocksActorTargetSpec(
                object_id="TGT-001",
                actor_name="MSM_TargetActor_1",
                start_ned=(12.0, -6.0, -2.0),
                velocity_ned=(2.0, 0.5, 0.0),
            ),
        ),
        detection_filter_names=("MSM_TargetActor_*",),
    )

    runtime.setup_episode(config)
    frame = runtime.sample_frame(config, frame_index=0, timestamp=1.0, output_dir=tmp_path)
    runtime.teardown_episode(config)

    assert fake_client.spawned_objects == ["MSM_TargetActor_1"]
    assert fake_client.destroyed_objects[-1] == "MSM_TargetActor_1"
    assert fake_client.detection_filters["Interceptor"] == ["MSM_TargetActor_*", "MSM_TargetActor_1"]
    assert fake_client.object_poses["MSM_TargetActor_1"].position.x_val == 14.0
    assert fake_client.object_poses["MSM_TargetActor_1"].position.y_val == -5.5
    assert frame.truth_objects[0].object_id == "TGT-001"
    assert frame.truth_objects[0].position_ned == (14.0, -5.5, -2.0)
    assert frame.visual_detections
    assert frame.visual_detections[0].object_id == "TGT-001"
    assert frame.visual_detections[0].bbox_xyxy == (10.0, 20.0, 30.0, 40.0)
    assert frame.metadata["detection_count"] == 1


def test_real_runtime_captures_computer_vision_5v5_cameras(tmp_path: Path) -> None:
    settings_path = tmp_path / "cv5v5_settings.json"
    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()
    settings_path.write_text(
        json.dumps(
            {
                "SimMode": "ComputerVision",
                "Vehicles": {
                    name: {"VehicleType": "ComputerVision", "X": 0, "Y": index * 4, "Z": -10}
                    for index, name in enumerate((*resources, *secondaries))
                },
            }
        ),
        encoding="utf-8",
    )
    fake_client = FakeAirSimClient(vehicle_names=(*resources, *secondaries))
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
    )
    config = BlocksSmokeConfig(
        output_root=tmp_path,
        settings_path=settings_path,
        scenario_name="blocks_cv_5v5",
        duration_s=0.0,
        camera_vehicle_name=resources[0],
        camera_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
        capture_lidar=False,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_cv_5v5_actor_target_specs(target_z=-10.0),
        detection_filter_names=("MSM_TargetActor_*",),
    )

    runtime.setup_episode(config)
    frame = runtime.sample_frame(config, frame_index=0, timestamp=1.0, output_dir=tmp_path)
    runtime.teardown_episode(config)

    assert len(frame.truth_objects) == 5
    assert len(frame.resources) == 5
    assert len(frame.cameras) == 7
    assert frame.metadata["secondary_camera_vehicle_names"] == list(secondaries)
    assert frame.metadata["lidar"]["ok"] is False
    assert frame.metadata["lidar"]["reason"] == "no_lidar_vehicle"
    assert len(frame.metadata["images"]) == 7
    assert all(name in fake_client.detection_filters for name in (*resources, *secondaries))
    assert len(frame.visual_detections) == 35
    assert {detection.camera_id.split(":", 1)[0] for detection in frame.visual_detections} == {
        *resources,
        *secondaries,
    }


def test_real_runtime_orients_cv_cameras_toward_initial_and_secondary_assignments(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "cv5v5_settings.json"
    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()
    settings_path.write_text(
        json.dumps(
            {
                "SimMode": "ComputerVision",
                "Vehicles": {
                    name: {"VehicleType": "ComputerVision", "X": 0, "Y": index * 4, "Z": -10}
                    for index, name in enumerate((*resources, *secondaries))
                },
            }
        ),
        encoding="utf-8",
    )
    fake_client = FakeAirSimClient(vehicle_names=(*resources, *secondaries))
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
    )
    config = BlocksSmokeConfig(
        output_root=tmp_path,
        settings_path=settings_path,
        scenario_name="blocks_cv_5v5",
        duration_s=0.0,
        camera_vehicle_name=resources[0],
        camera_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
        capture_lidar=False,
        cv_camera_follow_assignments=True,
        cv_camera_follow_distance_m=12.0,
        cv_reassignment_time_s=1.0,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_cv_5v5_actor_target_specs(target_z=-10.0),
        detection_filter_names=("MSM_TargetActor_*",),
    )

    runtime.setup_episode(config)
    initial = runtime.sample_frame(config, frame_index=0, timestamp=0.5, output_dir=tmp_path)
    secondary = runtime.sample_frame(config, frame_index=1, timestamp=1.5, output_dir=tmp_path)
    runtime.teardown_episode(config)

    initial_guidance = {
        item["vehicle_name"]: item for item in initial.metadata["cv_camera_guidance"]
    }
    secondary_guidance = {
        item["vehicle_name"]: item for item in secondary.metadata["cv_camera_guidance"]
    }
    assert initial_guidance["Interceptor_Cam_2"]["target_id"] == "TGT-002"
    assert initial_guidance["Interceptor_Cam_2"]["assignment_phase"] == "initial_assignment"
    assert secondary_guidance["Interceptor_Cam_2"]["target_id"] == "TGT-003"
    assert secondary_guidance["Interceptor_Cam_3"]["target_id"] == "TGT-002"
    assert secondary_guidance["Interceptor_Cam_2"]["assignment_phase"] == "secondary_reassignment"
    assert secondary_guidance["Interceptor_Cam_2"]["pose_update_ok"] is True
    assert "yaw_deg" in secondary_guidance["Interceptor_Cam_2"]
    assert "pitch_deg" in secondary_guidance["Secondary_Recon_1"]
    assert "Interceptor_Cam_2" in fake_client.vehicle_poses


def test_real_runtime_d4d5_stress_geometry_and_secondary_camera_dimensions(tmp_path: Path) -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_cv_5v5_d4d5_stress_settings.json")
    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()
    fake_client = FakeAirSimClient(vehicle_names=(*resources, *secondaries))
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
    )
    config = BlocksSmokeConfig(
        output_root=tmp_path,
        settings_path=settings_path,
        scenario_name="blocks_cv_5v5_d4d5_stress",
        duration_s=0.0,
        camera_vehicle_name=resources[0],
        camera_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
        capture_lidar=False,
        cv_camera_follow_assignments=True,
        cv_camera_follow_distance_m=50.0,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_cv_5v5_d4d5_stress_actor_target_specs(),
        detection_filter_names=("MSM_TargetActor_*",),
    )

    runtime.setup_episode(config)
    frame = runtime.sample_frame(config, frame_index=0, timestamp=0.0, output_dir=tmp_path)
    runtime.teardown_episode(config)

    target_y = [truth.position_ned[1] for truth in frame.truth_objects]
    resource_y = [resource.position_ned[1] for resource in frame.resources]
    cameras = {camera.owner_id: camera for camera in frame.cameras}
    assert target_y == [-40.0, -20.0, 0.0, 20.0, 40.0]
    assert resource_y == [-40.0, -20.0, 0.0, 20.0, 40.0]
    assert cameras["Secondary_Recon_1"].position_ned[2] == -60.0
    assert cameras["Secondary_Recon_1"].width == 640
    assert cameras["Interceptor_Cam_1"].width == 640


def test_d4d5_stress_analysis_outputs_expected_case_actions(tmp_path: Path) -> None:
    frames = _cv5v5_stress_frames(tmp_path)
    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()

    no_degrade = run_d4d5_stress_analysis(
        frames,
        tmp_path / "no_degradation",
        case_name="no_degradation",
        resource_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
    )
    secondary = run_d4d5_stress_analysis(
        frames,
        tmp_path / "secondary",
        case_name="degrade_to_secondary",
        resource_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
    )
    distributed = run_d4d5_stress_analysis(
        frames,
        tmp_path / "distributed",
        case_name="degrade_to_distributed",
        resource_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
    )

    assert no_degrade.metrics["dominant_d4_action"] == "continue_center"
    assert secondary.metrics["d4_action_counts"]["degrade_to_secondary"] >= 1
    assert secondary.metrics["selected_secondary_node_id"] == "SEC-01"
    assert distributed.metrics["d4_action_counts"]["degrade_to_distributed"] >= 1
    assert no_degrade.metrics["multi_target_fov_rate"] == 1.0
    assert no_degrade.metrics["secondary_global_view_rate"] == 1.0
    assert no_degrade.metrics["terminal_associator_call_count"] == len(frames) * len(resources)
    assert no_degrade.metrics["terminal_associator_locked_count"] >= len(resources)
    assert secondary.metrics["terminal_associator_reacquire_count"] >= 1
    assert distributed.metrics["terminal_associator_reacquire_count"] >= 1
    assert no_degrade.output_paths["d4d5_stress_case_report"].exists()
    observation_lines = no_degrade.output_paths["d5_terminal_observations_jsonl"].read_text(
        encoding="utf-8"
    ).splitlines()
    assert observation_lines
    assert all(json.loads(line)["metadata"]["terminal_associator_used"] is True for line in observation_lines)


def test_d4d5_stress_analysis_invokes_terminal_associator_decide(tmp_path: Path, monkeypatch) -> None:
    import airsim_runtime.d4d5_stress as d4d5_stress_module

    frames = _cv5v5_stress_frames(tmp_path)
    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()

    class SpyTerminalAssociator(d4d5_stress_module.TerminalAssociator):
        call_count = 0

        def decide(self, *args, **kwargs):
            SpyTerminalAssociator.call_count += 1
            return super().decide(*args, **kwargs)

    monkeypatch.setattr(d4d5_stress_module, "TerminalAssociator", SpyTerminalAssociator)

    result = d4d5_stress_module.run_d4d5_stress_analysis(
        frames,
        tmp_path / "spy",
        case_name="no_degradation",
        resource_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
    )

    assert SpyTerminalAssociator.call_count == len(frames) * len(resources)
    assert result.metrics["terminal_associator_call_count"] == SpyTerminalAssociator.call_count


def test_real_runtime_control_helpers_call_multirotor_api(tmp_path: Path) -> None:
    fake_client = FakeAirSimClient()
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
        client_kind="multirotor",
    )
    config = BlocksSmokeConfig(
        output_root=tmp_path,
        resource_vehicle_names=("Interceptor1", "Interceptor2"),
        intercept_altitude_ned_z=-2.0,
    )

    runtime.prepare_interceptor_control(config)
    runtime.command_velocity_z(
        config,
        vehicle_name="Interceptor1",
        velocity_ned=(3.0, 4.0, 0.0),
        duration_s=0.1,
    )
    collision = runtime.collision_info("Interceptor1")
    runtime.land_and_release_interceptors(("Interceptor1", "Interceptor2"), land=True)

    assert ("enableApiControl", True, "Interceptor1") in fake_client.control_calls
    assert ("armDisarm", True, "Interceptor2") in fake_client.control_calls
    assert ("takeoffAsync", "Interceptor1") in fake_client.control_calls
    assert ("moveToZAsync", "Interceptor1", -2.0) in fake_client.control_calls
    assert ("moveByVelocityZAsync", "Interceptor1", 3.0, 4.0, -2.0, 0.1) in fake_client.control_calls
    assert ("landAsync", "Interceptor2") in fake_client.control_calls
    assert collision["has_collided"] is False


def test_blocks_frame_adapters_feed_d1_and_integrated_models() -> None:
    frame = _sample_frame()

    observations = observations_from_blocks_frame(frame, arrival_timestamp=0.2)
    truths = truth_states_from_blocks_frame(frame)
    resources = resources_from_blocks_frame(frame)

    assert observations
    assert truths[0].truth_id == "TGT-001"
    assert resources[0].resource_id == "INT-01"
    assert all(obs.metadata["real_airsim_used"] is True for obs in observations)
    assert all(obs.metadata["dry_run"] is False for obs in observations)


def test_blocks_detection_adapter_feeds_d5_local_visual_tracks() -> None:
    frame = _sample_frame()
    frame = AirSimFrame(
        **{
            **frame.__dict__,
            "visual_detections": (
                AirSimDetectionBox(
                    detection_id="det-1",
                    camera_id="Interceptor1:0",
                    object_id="TGT-001",
                    local_track_id="Interceptor1:0:MSM_TargetActor_1",
                    timestamp=0.0,
                    center_px=(20.0, 30.0),
                    bbox_xyxy=(10.0, 20.0, 30.0, 40.0),
                    confidence=1.0,
                    classification_hint="uav",
                ),
            ),
        }
    )
    d2_track = SimpleNamespace(truth_id="TGT-001", global_track_id="G-001")

    result = local_visual_tracks_from_blocks_frame(frame, [d2_track])

    assert result is not None
    local_tracks, local_truth_map = result
    assert local_tracks[0].local_track_id == "Interceptor1:0:MSM_TargetActor_1"
    assert tuple(local_tracks[0].center_px) == (20.0, 30.0)
    assert local_truth_map["Interceptor1:0:MSM_TargetActor_1"] == "G-001"


def test_blocks_orchestrator_runs_mock_capture_and_integrated_replay(tmp_path: Path) -> None:
    config = BlocksSmokeConfig(
        episode_id="pytest_blocks",
        duration_s=1.0,
        dt_s=0.5,
        output_root=tmp_path,
        launch_blocks=False,
        connection_timeout_s=0.1,
    )
    runtime = FakeBlocksRuntime()
    orchestrator = AirSimBlocksSmokeOrchestrator(runtime=runtime)

    result = orchestrator.run(config)

    assert result.connected is True
    assert result.frame_count == 3
    assert result.image_ok_count == 3
    assert result.lidar_ok_count == 3
    assert result.integrated_result is not None
    assert result.integrated_result.metadata["real_airsim_used"] is True
    assert result.output_paths["airsim_blocks_summary"].exists()


def test_blocks_orchestrator_runs_mock_cv_5v5_integrated_replay(tmp_path: Path) -> None:
    settings_path = tmp_path / "cv5v5_settings.json"
    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()
    settings_path.write_text(
        json.dumps(
            {
                "SimMode": "ComputerVision",
                "Vehicles": {
                    name: {"VehicleType": "ComputerVision", "X": 0, "Y": index * 4, "Z": -10}
                    for index, name in enumerate((*resources, *secondaries))
                },
            }
        ),
        encoding="utf-8",
    )
    fake_client = FakeAirSimClient(vehicle_names=(*resources, *secondaries))
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
    )
    config = BlocksSmokeConfig(
        episode_id="pytest_cv5v5",
        scenario_name="blocks_cv_5v5",
        duration_s=1.0,
        dt_s=0.5,
        output_root=tmp_path,
        settings_path=settings_path,
        launch_blocks=False,
        connection_timeout_s=0.1,
        camera_vehicle_name=resources[0],
        camera_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
        capture_lidar=False,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_cv_5v5_actor_target_specs(target_z=-10.0),
        detection_filter_names=("MSM_TargetActor_*",),
    )
    orchestrator = AirSimBlocksSmokeOrchestrator(runtime=runtime)

    result = orchestrator.run(config)

    assert result.connected is True
    assert result.frame_count == 3
    assert result.integrated_result is not None
    assert result.integrated_result.metadata["real_airsim_used"] is True
    assert result.metadata["actor_target_count"] == 5
    assert result.metadata["resource_vehicle_names"] == list(resources)
    assert result.metadata["secondary_camera_vehicle_names"] == list(secondaries)
    assert result.metadata["capture_lidar"] is False
    assert result.metadata["detection_count"] == 105
    assert result.output_paths["blocks_frames_jsonl"].exists()
    assert result.output_paths["blocks_sensor_observations_jsonl"].exists()


def test_blocks_orchestrator_runs_mock_controlled_intercept(tmp_path: Path) -> None:
    config = BlocksSmokeConfig(
        episode_id="pytest_intercept",
        duration_s=0.2,
        dt_s=0.1,
        output_root=tmp_path,
        launch_blocks=False,
        connection_timeout_s=0.1,
        include_integrated_pipeline=False,
        execute_intercept=True,
        control_dt_s=0.1,
        intercept_max_duration_s=0.2,
        intercept_terminal_switch_range_m=100.0,
        intercept_min_bbox_area_ratio=0.001,
        intercept_min_stable_detection_frames=2,
    )
    runtime = FakeBlocksRuntime()
    orchestrator = AirSimBlocksSmokeOrchestrator(runtime=runtime)

    result = orchestrator.run(config)

    assert result.connected is True
    assert result.metadata["control_api_used"] is True
    assert result.metadata["intercept"]["command_record_count"] > 0
    assert result.output_paths["intercept_summary"].exists()
    assert result.output_paths["control_commands"].exists()
    assert result.output_paths["intercept_trajectory_plot"].exists()
    summary = json.loads(result.output_paths["intercept_summary"].read_text(encoding="utf-8"))
    assert summary["control_api_used"] is True
    assert summary["pair_count"] == 1
    commands = result.output_paths["control_commands"].read_text(encoding="utf-8")
    assert "guidance_law" in commands
    assert "camera_quality_gate_passed" in commands
    assert "terminal_switch_reject_reason" in commands
    assert "terminal_contract_reject_reason" in commands
    assert "d4_action" in commands
    assert "d5_decision_state" in commands


def test_controlled_intercept_blocks_png_when_d5_is_not_locked(tmp_path: Path) -> None:
    config = BlocksSmokeConfig(
        episode_id="pytest_intercept_d5_hold",
        duration_s=0.2,
        dt_s=0.1,
        output_root=tmp_path,
        launch_blocks=False,
        connection_timeout_s=0.1,
        include_integrated_pipeline=False,
        execute_intercept=True,
        control_dt_s=0.1,
        intercept_max_duration_s=0.2,
        intercept_terminal_switch_range_m=100.0,
        intercept_min_bbox_area_ratio=0.001,
        intercept_min_stable_detection_frames=2,
    )
    runtime = D5AmbiguousFakeRuntime()
    orchestrator = AirSimBlocksSmokeOrchestrator(runtime=runtime)

    result = orchestrator.run(config)

    commands = result.output_paths["control_commands"].read_text(encoding="utf-8")
    summary = json.loads(result.output_paths["intercept_summary"].read_text(encoding="utf-8"))
    assert "d5_not_locked" in commands
    assert summary["pairs"][0]["terminal_locked"] is False
    assert summary["pairs"][0]["terminal_contract_reject_reason"] == "d5_not_locked"


def test_controlled_intercept_blocks_png_when_d4_holds_for_review(tmp_path: Path) -> None:
    config = BlocksSmokeConfig(
        episode_id="pytest_intercept_d4_hold",
        duration_s=0.2,
        dt_s=0.1,
        output_root=tmp_path,
        launch_blocks=False,
        connection_timeout_s=0.1,
        include_integrated_pipeline=False,
        execute_intercept=True,
        control_dt_s=0.1,
        intercept_max_duration_s=0.2,
        intercept_terminal_switch_range_m=100.0,
        intercept_min_bbox_area_ratio=0.001,
        intercept_min_stable_detection_frames=2,
    )
    runtime = D4HoldFakeRuntime()
    orchestrator = AirSimBlocksSmokeOrchestrator(runtime=runtime)

    result = orchestrator.run(config)

    commands = result.output_paths["control_commands"].read_text(encoding="utf-8")
    summary = json.loads(result.output_paths["intercept_summary"].read_text(encoding="utf-8"))
    assert "d4_hold_for_review" in commands
    assert summary["pairs"][0]["terminal_locked"] is False
    assert summary["pairs"][0]["terminal_contract_reject_reason"] == "d4_hold_for_review"


def test_blocks_orchestrator_reconnects_after_initial_rpc_failure(tmp_path: Path) -> None:
    config = BlocksSmokeConfig(
        episode_id="pytest_reconnect",
        duration_s=0.0,
        output_root=tmp_path,
        launch_blocks=False,
        connection_timeout_s=2.0,
    )
    runtime = ReconnectingFakeRuntime()
    orchestrator = AirSimBlocksSmokeOrchestrator(runtime=runtime)

    result = orchestrator.run(config)

    assert result.connected is True
    assert runtime.reconnect_count == 1


def test_blocks_sequence_runner_reuses_one_blocks_process(tmp_path: Path) -> None:
    config = BlocksSmokeConfig(
        episode_id="base",
        duration_s=0.0,
        output_root=tmp_path,
        launch_blocks=False,
        connection_timeout_s=0.1,
    )
    runtime = CountingFakeBlocksRuntime()
    process_manager = FakeSequenceProcessManager(tmp_path / "sequence")
    orchestrator = AirSimBlocksSequenceOrchestrator(
        runtime=runtime,
        process_manager=process_manager,
    )
    specs = (
        BlocksEpisodeSpec("episode_a", "D1", duration_s=0.0, include_integrated_pipeline=False),
        BlocksEpisodeSpec("episode_b", "full", duration_s=0.0, include_integrated_pipeline=False),
    )

    result = orchestrator.run(config, sequence_id="pytest_sequence", episode_specs=specs)

    assert result.connected is True
    assert len(result.episode_results) == 2
    assert process_manager.start_count == 1
    assert process_manager.stop_count == 1
    assert runtime.reset_count == 2
    assert result.output_paths["blocks_sequence_summary"].exists()
    assert (tmp_path / "pytest_sequence" / "episode_a" / "airsim_blocks_summary.json").exists()


def test_blocks_sequence_runner_writes_d4d5_stress_sequence_report(tmp_path: Path) -> None:
    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()
    fake_client = FakeAirSimClient(vehicle_names=(*resources, *secondaries))
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
    )
    process_manager = FakeSequenceProcessManager(tmp_path / "sequence")
    config = BlocksSmokeConfig(
        episode_id="base",
        scenario_name="blocks_cv_5v5_d4d5_stress",
        duration_s=0.0,
        output_root=tmp_path,
        settings_path=Path("research_modules/airsim_runtime/settings/blocks_cv_5v5_d4d5_stress_settings.json"),
        launch_blocks=False,
        connection_timeout_s=0.1,
        camera_vehicle_name=resources[0],
        camera_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
        capture_lidar=False,
        cv_camera_follow_assignments=True,
        cv_camera_follow_distance_m=50.0,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_cv_5v5_d4d5_stress_actor_target_specs(),
        detection_filter_names=("MSM_TargetActor_*",),
        metadata={"d4d5_stress_enabled": True},
    )
    specs = tuple(replace(spec, duration_s=0.0, include_integrated_pipeline=False) for spec in D4D5_STRESS_EPISODES)
    orchestrator = AirSimBlocksSequenceOrchestrator(
        runtime=runtime,
        process_manager=process_manager,
    )

    result = orchestrator.run(config, sequence_id="pytest_d4d5_stress", episode_specs=specs)

    assert result.connected is True
    assert len(result.episode_results) == 3
    assert result.output_paths["d4d5_stress_sequence_report"].exists()
    assert result.output_paths["blocks_sequence_summary"].exists()
    actions = [
        episode.metadata["d4d5_stress"]["dominant_d4_action"]
        for episode in result.episode_results
    ]
    assert actions[0] == "continue_center"
    assert "degrade_to_secondary" in result.episode_results[1].metadata["d4d5_stress"]["d4_action_counts"]
    assert "degrade_to_distributed" in result.episode_results[2].metadata["d4d5_stress"]["d4_action_counts"]


class FakeAirSimModule:
    class ImageType:
        Scene = 0

    class DrivetrainType:
        ForwardOnly = 1

    class YawMode:
        def __init__(self, is_rate=False, yaw_or_rate=0.0):
            self.is_rate = is_rate
            self.yaw_or_rate = yaw_or_rate

    class Vector3r:
        def __init__(self, x_val=0.0, y_val=0.0, z_val=0.0):
            self.x_val = x_val
            self.y_val = y_val
            self.z_val = z_val

    class Quaternionr:
        def __init__(self, x_val=0.0, y_val=0.0, z_val=0.0, w_val=1.0):
            self.x_val = x_val
            self.y_val = y_val
            self.z_val = z_val
            self.w_val = w_val

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


class FakeAirSimClient:
    def __init__(self, vehicle_names: tuple[str, ...] = ("Interceptor", "Intruder")) -> None:
        self.object_poses = {}
        self.vehicle_poses = {}
        self.spawned_objects: list[str] = []
        self.destroyed_objects: list[str] = []
        self.detection_filters: dict[str, list[str]] = {}
        self.control_calls: list[tuple] = []
        self.vehicle_names = tuple(vehicle_names)

    def ping(self):
        return True

    def reset(self):
        return None

    def enableApiControl(self, is_enabled, vehicle_name=""):
        self.control_calls.append(("enableApiControl", is_enabled, vehicle_name))

    def armDisarm(self, arm, vehicle_name=""):
        self.control_calls.append(("armDisarm", arm, vehicle_name))
        return True

    def takeoffAsync(self, timeout_sec=20, vehicle_name=""):
        self.control_calls.append(("takeoffAsync", vehicle_name))
        return _future()

    def moveToZAsync(self, z, velocity, timeout_sec=3e38, yaw_mode=None, lookahead=-1, adaptive_lookahead=1, vehicle_name=""):
        self.control_calls.append(("moveToZAsync", vehicle_name, z))
        return _future()

    def moveByVelocityZAsync(self, vx, vy, z, duration, *args, vehicle_name=""):
        self.control_calls.append(("moveByVelocityZAsync", vehicle_name, vx, vy, z, duration))
        return _future()

    def hoverAsync(self, vehicle_name=""):
        self.control_calls.append(("hoverAsync", vehicle_name))
        return _future()

    def landAsync(self, timeout_sec=60, vehicle_name=""):
        self.control_calls.append(("landAsync", vehicle_name))
        return _future()

    def simGetCollisionInfo(self, vehicle_name=""):
        return SimpleNamespace(has_collided=False, object_name="", object_id=-1, time_stamp=0)

    def listVehicles(self):
        return list(self.vehicle_names)

    def simGetVehiclePose(self, vehicle_name):
        return self.vehicle_poses.get(vehicle_name, _pose(0.0, 0.0, -0.1))

    def getMultirotorState(self, vehicle_name=""):
        velocity = _vector(0.0, 0.0, 0.0)
        return SimpleNamespace(
            kinematics_estimated=SimpleNamespace(linear_velocity=velocity),
        )

    def simGetCameraInfo(self, camera_name, vehicle_name=""):
        return SimpleNamespace(pose=self.vehicle_poses.get(vehicle_name, _pose(0.0, 0.0, -2.0)))

    def simGetImages(self, requests, vehicle_name="", external=False):
        png_header = b"\x89PNG\r\n\x1a\n"
        return [
            SimpleNamespace(
                image_data_uint8=png_header,
                width=640,
                height=480,
                image_type=0,
            )
        ]

    def simSetVehiclePose(self, pose, ignore_collision=True, vehicle_name=""):
        self.vehicle_poses[vehicle_name] = pose
        return True

    def getLidarData(self, lidar_name="", vehicle_name=""):
        return SimpleNamespace(point_cloud=[0.0, 0.0, 0.0, 1.0, 1.0, 1.0], time_stamp=123)

    def simListSceneObjects(self, name_regex=".*"):
        return ["Floor", "Block"]

    def simSpawnObject(self, object_name, asset_name, pose, scale, physics_enabled=False, is_blueprint=False):
        self.spawned_objects.append(object_name)
        self.object_poses[object_name] = pose
        return object_name

    def simSetObjectPose(self, object_name, pose, teleport=True):
        self.object_poses[object_name] = pose
        return True

    def simGetObjectPose(self, object_name):
        return self.object_poses.get(object_name, _pose(float("nan"), float("nan"), float("nan")))

    def simDestroyObject(self, object_name):
        self.destroyed_objects.append(object_name)
        return True

    def simClearDetectionMeshNames(self, camera_name, image_type, vehicle_name="", external=False):
        self.detection_filters[vehicle_name] = []

    def simSetDetectionFilterRadius(self, camera_name, image_type, radius_cm, vehicle_name="", external=False):
        return None

    def simAddDetectionFilterMeshName(
        self, camera_name, image_type, mesh_name, vehicle_name="", external=False
    ):
        self.detection_filters.setdefault(vehicle_name, []).append(mesh_name)

    def simGetDetections(self, camera_name, image_type, vehicle_name="", external=False):
        return [
            _detection(name)
            for name in sorted(self.object_poses)
            if name.startswith("MSM_TargetActor_")
        ]


class FakeBlocksRuntime:
    def ping(self):
        return True

    def wait_for_connection(self, timeout_s):
        return None

    def reset(self):
        return None

    def prepare_interceptor_control(self, config):
        self.control_prepared = True

    def command_velocity_z(self, config, *, vehicle_name, velocity_ned, duration_s):
        commands = getattr(self, "velocity_commands", [])
        commands.append((vehicle_name, velocity_ned, duration_s))
        self.velocity_commands = commands

    def hover_interceptor(self, vehicle_name):
        hovers = getattr(self, "hover_calls", [])
        hovers.append(vehicle_name)
        self.hover_calls = hovers

    def land_and_release_interceptors(self, vehicle_names, *, land=True):
        self.released_vehicle_names = tuple(vehicle_names)
        self.release_land = land

    def collision_info(self, vehicle_name):
        return {"ok": True, "has_collided": False, "object_name": "", "object_id": -1}

    def sample_frame(self, config, frame_index, timestamp, output_dir):
        frame = _sample_frame(timestamp=timestamp, frame_index=frame_index)
        image_path = output_dir / f"mock_{frame_index}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        frame.metadata["image"] = {"ok": True, "path": str(image_path), "width": 640, "height": 480}
        frame.metadata["lidar"] = {"ok": True, "point_count": 2}
        frame.metadata["vehicle_names"] = ["Interceptor", "Intruder"]
        return frame


class D5AmbiguousFakeRuntime(FakeBlocksRuntime):
    def sample_frame(self, config, frame_index, timestamp, output_dir):
        frame = super().sample_frame(config, frame_index, timestamp, output_dir)
        metadata = {
            **frame.metadata,
            "terminal_associations": [
                {
                    "resource_id": "INT-01",
                    "assigned_global_track_id": "TGT-001",
                    "local_track_id": "Interceptor:0:MSM_TargetActor_1",
                    "association_confidence": 0.4,
                    "ambiguity_score": 0.8,
                    "friend_conflict_state": "none",
                    "decision_state": "ambiguous",
                    "assignment_version": 1,
                }
            ],
        }
        return AirSimFrame(**{**frame.__dict__, "metadata": metadata})


class D4HoldFakeRuntime(FakeBlocksRuntime):
    def sample_frame(self, config, frame_index, timestamp, output_dir):
        frame = super().sample_frame(config, frame_index, timestamp, output_dir)
        metadata = {
            **frame.metadata,
            "d4_guidance_permission": {
                "action": "hold_for_review",
                "mode": "active_degradation",
                "reason": "terminal_friend_conflict",
                "requires_human_review": True,
            },
        }
        return AirSimFrame(**{**frame.__dict__, "metadata": metadata})


class ReconnectingFakeRuntime(FakeBlocksRuntime):
    def __init__(self) -> None:
        self.ping_count = 0
        self.reconnect_count = 0

    def ping(self):
        self.ping_count += 1
        if self.ping_count == 1:
            raise RuntimeError("initial connection refused")
        return True

    def reconnect(self):
        self.reconnect_count += 1


class CountingFakeBlocksRuntime(FakeBlocksRuntime):
    def __init__(self) -> None:
        self.reset_count = 0

    def reset(self):
        self.reset_count += 1


class FakeSequenceProcessManager:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.start_count = 0
        self.stop_count = 0

    def start(self):
        self.start_count += 1

    def stop(self):
        self.stop_count += 1

    def returncode(self):
        return None

    def write_diagnostics(self):
        path = self.output_dir / "blocks_diagnostics.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return path

    def format_diagnostics(self):
        return "{}"


def _sample_frame(timestamp: float = 0.0, frame_index: int = 0) -> AirSimFrame:
    return AirSimFrame(
        episode_id="pytest_blocks",
        scenario_name="blocks_readonly_smoke",
        frame_index=frame_index,
        timestamp=timestamp,
        truth_objects=(
            AirSimTruthObject(
                object_id="TGT-001",
                object_type="target",
                timestamp=timestamp,
                position_ned=(35.0, -20.0, -2.0),
                velocity_ned=(0.0, 0.0, 0.0),
                threat_score=0.9,
                coverage_cell="cell-north",
            ),
        ),
        resources=(
            AirSimResourceState(
                resource_id="INT-01",
                timestamp=timestamp,
                position_ned=(0.0, 0.0, -2.0),
                coverage_cell="cell-north",
                metadata={"airsim_vehicle_name": "Interceptor"},
            ),
        ),
        visual_detections=(
            AirSimDetectionBox(
                detection_id=f"det-{frame_index}",
                camera_id="Interceptor:0",
                object_id="TGT-001",
                local_track_id="Interceptor:0:MSM_TargetActor_1",
                timestamp=timestamp,
                center_px=(320.0 + frame_index, 240.0),
                bbox_xyxy=(290.0 + frame_index, 210.0, 350.0 + frame_index, 270.0),
                confidence=0.95,
            ),
        ),
        metadata={
            "runtime": "Blocks",
            "real_airsim_used": True,
            "image": {"ok": True},
            "lidar": {"ok": True, "point_count": 2},
            "vehicle_names": ["Interceptor", "Intruder"],
            "scene_object_count": 2,
        },
    )


def _cv5v5_stress_frames(tmp_path: Path) -> list[AirSimFrame]:
    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()
    fake_client = FakeAirSimClient(vehicle_names=(*resources, *secondaries))
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
    )
    config = BlocksSmokeConfig(
        output_root=tmp_path,
        settings_path=Path("research_modules/airsim_runtime/settings/blocks_cv_5v5_d4d5_stress_settings.json"),
        scenario_name="blocks_cv_5v5_d4d5_stress",
        duration_s=0.0,
        camera_vehicle_name=resources[0],
        camera_vehicle_names=resources,
        secondary_camera_vehicle_names=secondaries,
        capture_lidar=False,
        cv_camera_follow_assignments=True,
        cv_camera_follow_distance_m=50.0,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_cv_5v5_d4d5_stress_actor_target_specs(),
        detection_filter_names=("MSM_TargetActor_*",),
    )
    runtime.setup_episode(config)
    try:
        return [
            runtime.sample_frame(config, frame_index=0, timestamp=0.0, output_dir=tmp_path),
            runtime.sample_frame(config, frame_index=1, timestamp=0.5, output_dir=tmp_path),
        ]
    finally:
        runtime.teardown_episode(config)


def _pose(x: float, y: float, z: float):
    return SimpleNamespace(position=_vector(x, y, z))


def _vector(x: float, y: float, z: float):
    return SimpleNamespace(x_val=x, y_val=y, z_val=z)


def _vector2(x: float, y: float):
    return SimpleNamespace(x_val=x, y_val=y)


def _future():
    return SimpleNamespace(join=lambda: None)


def _detection(name: str):
    return SimpleNamespace(
        name=name,
        box2D=SimpleNamespace(min=_vector2(10.0, 20.0), max=_vector2(30.0, 40.0)),
        box3D=SimpleNamespace(min=_vector(0.0, 0.0, 0.0), max=_vector(1.0, 1.0, 1.0)),
        relative_pose=_pose(1.0, 2.0, 3.0),
    )
