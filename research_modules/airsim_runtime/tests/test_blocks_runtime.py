from __future__ import annotations

import json
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
from airsim_runtime.models import BlocksActorTargetSpec, BlocksEpisodeSpec, BlocksSmokeConfig
from airsim_runtime.orchestrator import AirSimBlocksSmokeOrchestrator
from airsim_runtime.real_runtime import RealAirSimRuntimeClient
from airsim_runtime.sequence import AirSimBlocksSequenceOrchestrator


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


class FakeAirSimModule:
    class ImageType:
        Scene = 0

    class Vector3r:
        def __init__(self, x_val=0.0, y_val=0.0, z_val=0.0):
            self.x_val = x_val
            self.y_val = y_val
            self.z_val = z_val

    class Pose:
        def __init__(self, position_val=None):
            self.position = position_val or FakeAirSimModule.Vector3r()

    class ImageRequest:
        def __init__(self, camera_name, image_type, pixels_as_float=False, compress=True):
            self.camera_name = camera_name
            self.image_type = image_type
            self.pixels_as_float = pixels_as_float
            self.compress = compress


class FakeAirSimClient:
    def __init__(self) -> None:
        self.object_poses = {}
        self.spawned_objects: list[str] = []
        self.destroyed_objects: list[str] = []
        self.detection_filters: dict[str, list[str]] = {}

    def ping(self):
        return True

    def reset(self):
        return None

    def listVehicles(self):
        return ["Interceptor", "Intruder"]

    def simGetVehiclePose(self, vehicle_name):
        return _pose(0.0, 0.0, -0.1)

    def getMultirotorState(self, vehicle_name=""):
        velocity = _vector(0.0, 0.0, 0.0)
        return SimpleNamespace(
            kinematics_estimated=SimpleNamespace(linear_velocity=velocity),
        )

    def simGetCameraInfo(self, camera_name, vehicle_name=""):
        return SimpleNamespace(pose=_pose(0.0, 0.0, -2.0))

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

    def sample_frame(self, config, frame_index, timestamp, output_dir):
        frame = _sample_frame(timestamp=timestamp, frame_index=frame_index)
        image_path = output_dir / f"mock_{frame_index}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        frame.metadata["image"] = {"ok": True, "path": str(image_path), "width": 640, "height": 480}
        frame.metadata["lidar"] = {"ok": True, "point_count": 2}
        frame.metadata["vehicle_names"] = ["Interceptor", "Intruder"]
        return frame


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


def _pose(x: float, y: float, z: float):
    return SimpleNamespace(position=_vector(x, y, z))


def _vector(x: float, y: float, z: float):
    return SimpleNamespace(x_val=x, y_val=y, z_val=z)


def _vector2(x: float, y: float):
    return SimpleNamespace(x_val=x, y_val=y)


def _detection(name: str):
    return SimpleNamespace(
        name=name,
        box2D=SimpleNamespace(min=_vector2(10.0, 20.0), max=_vector2(30.0, 40.0)),
        box3D=SimpleNamespace(min=_vector(0.0, 0.0, 0.0), max=_vector(1.0, 1.0, 1.0)),
        relative_pose=_pose(1.0, 2.0, 3.0),
    )
