from __future__ import annotations

import json
import signal
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import airsim_runtime.episode_bus as episode_bus_module
from airsim_dryrun.models import (
    AirSimDetectionBox,
    AirSimFrame,
    AirSimResourceState,
    AirSimTruthObject,
)
from airsim_runtime.adapters import (
    geometric_local_visual_tracks_from_blocks_frame,
    local_visual_tracks_from_blocks_frame,
    offline_truth_map_from_blocks_frame,
    observations_from_blocks_frame,
    resources_from_blocks_frame,
    truth_states_from_blocks_frame,
)
from airsim_runtime.blocks import BlocksProcessManager
from airsim_runtime.d4d5_stress import run_d4d5_stress_analysis
from airsim_runtime.episode_bus import run_main_episode_bus
from airsim_runtime.models import (
    BlocksActorTargetSpec,
    BlocksEpisodeSpec,
    BlocksSmokeConfig,
    default_actor_target_specs,
    default_5v5_actor_target_specs,
    default_cv_5v5_actor_target_specs,
    default_cv_5v5_d4d5_stress_actor_target_specs,
    default_cv_5v5_camera_vehicle_names,
    default_cv_5v5_secondary_vehicle_names,
    default_cv_camera_vehicle_names,
    default_interceptor_vehicle_names,
    write_dynamic_computer_vision_settings,
    write_dynamic_multirotor_settings,
)
from airsim_runtime.orchestrator import AirSimBlocksSmokeOrchestrator
from airsim_runtime.real_runtime import RealAirSimRuntimeClient
from airsim_runtime.run_blocks_sequence import (
    _build_sequence_run,
    _d4d5_calibration_rows,
    _parse_float_list,
    _parse_int_list,
    _write_p1_calibration_sweep_outputs,
    parse_args,
)
from airsim_runtime.sequence import (
    AirSimBlocksSequenceOrchestrator,
    D4D5_STRESS_EPISODES,
    run_blocks_batch_sequences,
)
from d5_terminal_association import (
    AssociationConfig,
    CameraModel,
    GlobalTrack,
    LocalVisualTrack,
    TerminalAssociator,
    associate_tracks_to_detections_geometrically,
    camera_model_from_airsim_camera_info,
    evaluate_associations_offline,
)
from d6_evaluation_metrics import load_episode_log_jsonl


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


def test_5v5_actor_tuned_settings_define_five_simpleflight_interceptors() -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_5v5_actor_tuned_settings.json")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert settings["SimMode"] == "Multirotor"
    assert settings["EnableRpc"] is True
    assert settings["ApiServerPort"] == 41451
    assert list(settings["Vehicles"]) == [f"Interceptor{index}" for index in range(1, 6)]
    assert [settings["Vehicles"][name]["Y"] for name in settings["Vehicles"]] == [-20, -10, 0, 10, 20]
    for index, vehicle in enumerate(settings["Vehicles"].values()):
        assert vehicle["VehicleType"] == "SimpleFlight"
        assert vehicle["DefaultVehicleState"] == "Inactive"
        assert vehicle["AllowAPIAlways"] is True
        assert vehicle["EnableCollisions"] is True
        assert vehicle["EnableCollisionPassthrogh"] is False
        assert vehicle["Z"] == 0
        assert vehicle["RC"]["RemoteControlID"] == index
        assert vehicle["Sensors"]["LidarSensor1"]["Enabled"] is True


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
    secondary_camera = vehicles["Secondary_Recon_1"]["Cameras"]["0"]
    assert secondary_camera["Pitch"] == -90
    assert secondary_camera["CaptureSettings"][0]["FOV_Degrees"] == 140


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


def test_dynamic_n_actor_specs_and_vehicle_names_are_centered() -> None:
    resources = default_interceptor_vehicle_names(3)
    cameras = default_cv_camera_vehicle_names(4)
    specs = default_actor_target_specs(
        count=3,
        target_z=-10.0,
        target_distance_m=40.0,
        target_spacing_m=12.0,
        target_scale_m=2.0,
    )

    assert resources == ("Interceptor1", "Interceptor2", "Interceptor3")
    assert cameras == ("Interceptor_Cam_1", "Interceptor_Cam_2", "Interceptor_Cam_3", "Interceptor_Cam_4")
    assert [spec.object_id for spec in specs] == ["TGT-001", "TGT-002", "TGT-003"]
    assert [spec.start_ned[1] for spec in specs] == [-12.0, 0.0, 12.0]
    assert all(spec.scale == (2.0, 2.0, 2.0) for spec in specs)
    assert {spec.asset_name for spec in specs} == {"Quadrotor1"}


def test_actor_target_defaults_use_drone_mesh_for_yolo_terminal_tests() -> None:
    assert BlocksActorTargetSpec("TGT-001", "MSM_TargetActor_1", (0.0, 0.0, -2.0), (0.0, 0.0, 0.0)).asset_name == "Quadrotor1"
    assert BlocksSmokeConfig().target_asset_name == "Quadrotor1"
    assert {spec.asset_name for spec in default_5v5_actor_target_specs()} == {"Quadrotor1"}


def test_dynamic_n_settings_files_match_requested_vehicle_count(tmp_path: Path) -> None:
    multirotor_path = write_dynamic_multirotor_settings(
        tmp_path / "n3_multirotor.json",
        vehicle_names=default_interceptor_vehicle_names(3),
        y_spacing_m=8.0,
        tuned_terminal_camera=True,
    )
    cv_path = write_dynamic_computer_vision_settings(
        tmp_path / "n4_cv.json",
        camera_vehicle_names=default_cv_camera_vehicle_names(4),
        secondary_vehicle_names=("Secondary_Recon_1",),
        camera_spacing_m=20.0,
        secondary_height_above_targets_m=200.0,
        target_z=-10.0,
        secondary_width=1280,
        secondary_height=720,
    )

    multirotor = json.loads(multirotor_path.read_text(encoding="utf-8"))
    cv = json.loads(cv_path.read_text(encoding="utf-8"))
    assert multirotor["SimMode"] == "Multirotor"
    assert list(multirotor["Vehicles"]) == ["Interceptor1", "Interceptor2", "Interceptor3"]
    assert [multirotor["Vehicles"][name]["Y"] for name in multirotor["Vehicles"]] == [-8.0, 0.0, 8.0]
    assert all(vehicle["Cameras"]["0"]["X"] == 0.5 for vehicle in multirotor["Vehicles"].values())
    assert cv["SimMode"] == "ComputerVision"
    assert set(cv["Vehicles"]) == {
        "Interceptor_Cam_1",
        "Interceptor_Cam_2",
        "Interceptor_Cam_3",
        "Interceptor_Cam_4",
        "Secondary_Recon_1",
    }
    assert [cv["Vehicles"][f"Interceptor_Cam_{index}"]["Y"] for index in range(1, 5)] == [
        -30.0,
        -10.0,
        10.0,
        30.0,
    ]
    assert cv["Vehicles"]["Secondary_Recon_1"]["Z"] == -210.0
    assert cv["Vehicles"]["Secondary_Recon_1"]["Cameras"]["0"]["CaptureSettings"][0]["Width"] == 1280
    assert cv["Vehicles"]["Secondary_Recon_1"]["Cameras"]["0"]["Pitch"] == -90.0
    assert len(cv["Vehicles"]["Secondary_Recon_1"]["Cameras"]["0"]["CaptureSettings"]) == 2


def test_sequence_builder_uses_dynamic_n_scenario_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_blocks_sequence.py",
            "--actor-5v5",
            "--drone-count",
            "3",
            "--output-root",
            str(tmp_path),
            "--sequence-id",
            "pytest_actor_n3",
        ],
    )
    actor_args = parse_args()
    actor_config, _, _ = _build_sequence_run(actor_args, seed=7, sequence_id=actor_args.sequence_id)

    assert actor_config.scenario_name == "blocks_actor_n3"
    assert actor_config.metadata["runtime_mode"] == "actor_nvN"
    assert actor_config.metadata["drone_count"] == 3
    assert len(actor_config.resource_vehicle_names) == 3
    assert len(actor_config.target_actor_specs) == 3

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_blocks_sequence.py",
            "--cv-5v5",
            "--drone-count",
            "4",
            "--secondary-count",
            "1",
            "--output-root",
            str(tmp_path),
            "--sequence-id",
            "pytest_cv_n4",
        ],
    )
    cv_args = parse_args()
    cv_config, _, _ = _build_sequence_run(cv_args, seed=7, sequence_id=cv_args.sequence_id)

    assert cv_config.scenario_name == "blocks_cv_n4"
    assert cv_config.metadata["runtime_mode"] == "computer_vision_nvN"
    assert cv_config.metadata["drone_count"] == 4
    assert len(cv_config.resource_vehicle_names) == 4
    assert len(cv_config.camera_vehicle_names) == 4
    assert len(cv_config.secondary_camera_vehicle_names) == 1
    assert len(cv_config.target_actor_specs) == 4


def test_default_5v5_actor_specs_are_five_controlled_intercept_targets() -> None:
    specs = default_5v5_actor_target_specs(target_z=-5.0)

    assert len(specs) == 5
    assert [spec.object_id for spec in specs] == [
        "TGT-001",
        "TGT-002",
        "TGT-003",
        "TGT-004",
        "TGT-005",
    ]
    assert [spec.actor_name for spec in specs] == [f"MSM_TargetActor_{index}" for index in range(1, 6)]
    assert [spec.start_ned[1] for spec in specs] == [-20.0, -10.0, 0.0, 10.0, 20.0]
    assert specs[0].position_at(2.0)[2] == -5.0
    assert specs[0].position_at(2.0)[1] > specs[0].start_ned[1]
    assert specs[-1].position_at(2.0)[1] < specs[-1].start_ned[1]
    assert all(spec.scale == (2.0, 2.0, 2.0) for spec in specs)


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


def test_actor_2v2_tuned_settings_use_wide_fov_for_terminal_handoff() -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_2v2_actor_tuned_settings.json")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert settings["SimMode"] == "Multirotor"
    assert set(settings["Vehicles"]) == {"Interceptor1", "Interceptor2"}
    capture = settings["CameraDefaults"]["CaptureSettings"][0]
    assert capture["Width"] == 640
    assert capture["Height"] == 480
    assert capture["FOV_Degrees"] == 120
    assert settings["Vehicles"]["Interceptor1"]["Cameras"]["0"]["X"] == 0.5
    assert settings["Vehicles"]["Interceptor2"]["Cameras"]["0"]["X"] == 0.5


def test_computer_vision_5v5_d4d5_stress_200m_settings_define_high_recon_geometry() -> None:
    settings_path = Path("research_modules/airsim_runtime/settings/blocks_cv_5v5_d4d5_stress_200m_settings.json")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = default_cv_5v5_secondary_vehicle_names()
    vehicles = settings["Vehicles"]
    assert settings["SimMode"] == "ComputerVision"
    assert set(vehicles) == {*resources, *secondaries}
    assert [vehicles[name]["Z"] for name in resources] == [-10, -10, -10, -10, -10]
    assert [vehicles[name]["Z"] for name in secondaries] == [-210, -210]
    secondary_capture = vehicles["Secondary_Recon_1"]["Cameras"]["0"]["CaptureSettings"][0]
    secondary_camera = vehicles["Secondary_Recon_1"]["Cameras"]["0"]
    assert secondary_capture["Width"] == 1920
    assert secondary_capture["Height"] == 1080
    assert secondary_capture["FOV_Degrees"] == 110
    assert secondary_camera["Pitch"] == -90


def test_sequence_builder_mobile_secondary_recon_generates_gimballed_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_blocks_sequence.py",
            "--cv-5v5-d4d5-stress",
            "--cv-5v5-d4d5-stress-200m",
            "--mobile-secondary-recon",
            "--secondary-fov",
            "80",
            "--secondary-width",
            "1920",
            "--secondary-height",
            "1080",
            "--secondary-recon-standoff",
            "5",
            "--output-root",
            str(tmp_path),
            "--sequence-id",
            "pytest_mobile_recon",
        ],
    )
    args = parse_args()

    config, _, _ = _build_sequence_run(args, seed=7, sequence_id=args.sequence_id)

    settings = json.loads(config.settings_path.read_text(encoding="utf-8"))
    secondary_camera = settings["Vehicles"]["Secondary_Recon_1"]["Cameras"]["0"]
    secondary_capture = secondary_camera["CaptureSettings"][0]
    assert config.cv_secondary_mobile_recon_enabled is True
    assert config.cv_secondary_look_at_enabled is True
    assert config.cv_secondary_recon_standoff_m == 5.0
    assert config.metadata["secondary_recon_mode"] == "mobile_recon_gimbal"
    assert config.metadata["secondary_guidance_source"] == "radar_global_track_cue"
    assert secondary_camera["Pitch"] == 0.0
    assert secondary_capture["FOV_Degrees"] == 80.0
    assert secondary_capture["Width"] == 1920
    assert secondary_capture["Height"] == 1080


def test_sequence_builder_accepts_explicit_secondary_height(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_blocks_sequence.py",
            "--cv-5v5-d4d5-stress",
            "--mobile-secondary-recon",
            "--secondary-height-above-targets",
            "100",
            "--secondary-fov",
            "80",
            "--secondary-width",
            "1920",
            "--secondary-height",
            "1080",
            "--output-root",
            str(tmp_path),
            "--sequence-id",
            "pytest_mobile_recon_100m",
        ],
    )
    args = parse_args()

    config, _, _ = _build_sequence_run(args, seed=7, sequence_id=args.sequence_id)

    settings = json.loads(config.settings_path.read_text(encoding="utf-8"))
    secondary = settings["Vehicles"]["Secondary_Recon_1"]
    assert secondary["Z"] == -110.0
    assert config.metadata["secondary_height_target_m"] == 100.0
    assert config.metadata["secondary_camera_fov_degrees"] == 80.0


def test_p1_calibration_sweep_helpers_write_summary(tmp_path: Path) -> None:
    args = SimpleNamespace(sequence_id="pytest_p1_sweep")
    rows = [
        {
            "sequence_id": "pytest_p1_sweep_h50_f80_sec2_st5_seed001",
            "seed": 1,
            "case_name": "degrade_to_secondary",
            "connected": True,
            "height_m": 50.0,
            "fov_deg": 80.0,
            "secondary_count": 2,
            "standoff_m": 5.0,
            "d4_action": "degrade_to_secondary",
            "secondary_network_joint_full_view_frame_rate": 0.5,
            "secondary_network_mean_coverage_ratio": 0.8,
            "secondary_single_camera_full_view_frame_rate": 0.25,
            "secondary_gimbal_pointing_ok_rate": 1.0,
            "cross_view_association_count": 3,
            "cross_view_conversion_gap": 0.2,
            "secondary_detect_available_but_not_registered": 2,
            "terminal_lock_accuracy": 0.75,
            "bbox_mean_px2": 3200.0,
            "top_reject_reason": "geometry_gate_rejected",
        }
    ]

    paths = _write_p1_calibration_sweep_outputs(
        tmp_path,
        args=args,
        seeds=[1],
        combo_count=1,
        rows=rows,
        results=[],
    )

    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    report = paths["markdown"].read_text(encoding="utf-8")
    assert payload["calibration_suite"] == "cv_5v5_d4d5_secondary_coverage"
    assert payload["calibration_suite_version"] == "p1-d4d5-calibration-suite-v1"
    assert payload["threshold_version"] == "p1-d4d5-thresholds-v1"
    assert payload["height_comparison"][0]["height_m"] == 50.0
    assert payload["height_comparison"][0]["secondary_network_mean_coverage_ratio_mean"] == 0.8
    assert payload["aggregate"]["cross_view_association_count_mean"] == 3.0
    assert payload["aggregate"]["best_cross_view"]["secondary_count"] == 2
    assert "d6_report_outputs" in payload
    assert paths["d6_markdown"].exists()
    assert paths["d6_summary_json"].exists()
    assert "Calibration suite" in report
    assert "高度对比" in report
    assert "detect 未注册均值" in report
    assert "D6 标准报告输出" in report
    assert "geometry_gate_rejected" in report


def test_p1_calibration_rows_prefer_d6_not_registered_count_field() -> None:
    result = SimpleNamespace(
        sequence_id="pytest_p1_sweep_seed001",
        connected=True,
        episode_results=[
            SimpleNamespace(
                metadata={
                    "d4d5_stress": {
                        "case_name": "degrade_to_secondary",
                        "dominant_d4_action": "degrade_to_secondary",
                        "secondary_detect_available_but_not_registered_count": 25,
                        "secondary_detect_available_but_not_registered": 0,
                        "secondary_bbox_area_px_stats": {"mean": 1234.0},
                    }
                }
            )
        ],
    )

    rows = _d4d5_calibration_rows(
        [result],
        height_m=200.0,
        fov_deg=80.0,
        secondary_count=2,
        standoff_m=5.0,
    )

    assert rows[0]["secondary_detect_available_but_not_registered"] == 25


def test_p1_sweep_list_parsers() -> None:
    assert _parse_float_list("50,100,200", option_name="--x") == [50.0, 100.0, 200.0]
    assert _parse_int_list("1,2,3", option_name="--x") == [1, 2, 3]


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

    def fake_popen(cmd, cwd, stdout, stderr, text, env, start_new_session):
        calls.append(
            {
                "cmd": cmd,
                "cwd": cwd,
                "stdout": stdout,
                "stderr": stderr,
                "text": text,
                "env": env,
                "start_new_session": start_new_session,
            }
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
    assert calls[0]["start_new_session"] is True


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

    def fake_popen(cmd, cwd, stdout, stderr, text, env, start_new_session):
        calls.append(cmd)
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    manager = BlocksProcessManager(script, settings, tmp_path / "out")

    manager.start()

    assert calls[0][0] == "bash"
    assert calls[0][1] == str(script.resolve())
    assert calls[0][2] == f"-settings={settings.resolve()}"


def test_blocks_process_manager_stop_signals_process_group(
    tmp_path: Path, monkeypatch
) -> None:
    script = tmp_path / "Blocks.sh"
    settings = tmp_path / "settings.json"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    settings.write_text("{}", encoding="utf-8")
    signals: list[tuple[int, int]] = []

    class FakeRunningProcess:
        pid = 2468
        terminated = False

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self):
            raise AssertionError("stop should signal the process group first")

        def kill(self):
            raise AssertionError("SIGTERM path should not need process.kill")

        def wait(self, timeout=None):
            self.terminated = True
            return 0

    process = FakeRunningProcess()

    def fake_killpg(pid: int, signum: int) -> None:
        signals.append((pid, signum))
        process.terminated = True

    manager = BlocksProcessManager(script, settings, tmp_path / "out")
    manager.process = process  # type: ignore[assignment]
    monkeypatch.setattr("os.killpg", fake_killpg)
    monkeypatch.setattr(
        manager,
        "_wait_for_rpc_port_closed",
        lambda timeout_s=8.0: True,
    )

    manager.stop(timeout_s=1.0)

    assert signals == [(2468, signal.SIGTERM)]


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


def test_real_runtime_yolo_backend_uses_d5_adapter_without_simgetdetections(
    tmp_path: Path,
) -> None:
    class CountingFakeAirSimClient(FakeAirSimClient):
        def __init__(self) -> None:
            super().__init__()
            self.sim_get_detections_count = 0

        def simGetDetections(self, camera_name, image_type, vehicle_name="", external=False):
            self.sim_get_detections_count += 1
            return super().simGetDetections(camera_name, image_type, vehicle_name, external)

    class FakeYoloAdapter:
        def process_frame(self, frame, *, resource_id, camera_id, timestamp, frame_id=None):
            return SimpleNamespace(
                tracks=(
                    LocalVisualTrack(
                        local_track_id=f"{camera_id}/yolov8_iou_fallback:track:7",
                        center_px=np.array([25.0, 35.0], dtype=float),
                        bbox=(10.0, 20.0, 40.0, 50.0),
                        bearing_rate=np.zeros(2, dtype=float),
                        category="uav",
                        quality=0.82,
                        mot_history_length=3,
                        timestamp=timestamp,
                    ),
                ),
                status="ok",
                detector_backend="fake_yolov8",
                tracker_backend="iou_fallback",
                metadata={
                    "tracker_backend": "iou_fallback",
                    "requested_tracker_backend": "bytetrack",
                    "raw_detection_count": 1,
                    "accepted_detection_count": 1,
                },
            )

    fake_client = CountingFakeAirSimClient()
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_: fake_client,
        airsim_module=FakeAirSimModule,
        timeout_value=0.1,
        yolo_adapter_factory=lambda _config: FakeYoloAdapter(),
    )
    config = BlocksSmokeConfig(
        output_root=tmp_path,
        duration_s=0.0,
        camera_vehicle_name="Interceptor",
        camera_vehicle_names=("Interceptor",),
        resource_vehicle_names=("Interceptor",),
        detection_backend="yolo",
        yolo_tracker_backend="bytetrack",
    )

    frame = runtime.sample_frame(config, frame_index=0, timestamp=1.0, output_dir=tmp_path)

    assert fake_client.sim_get_detections_count == 0
    assert frame.metadata["detections"][0]["backend"] == "yolo"
    assert frame.metadata["detections"][0]["detector_backend"] == "fake_yolov8"
    assert frame.metadata["detections"][0]["tracker_backend"] == "iou_fallback"
    assert frame.visual_detections
    detection = frame.visual_detections[0]
    assert detection.object_id.startswith("local_yolo_track:")
    assert detection.local_track_id.endswith("track:7")
    assert detection.metadata["source"] == "yolov8_mot"
    assert detection.metadata["mot_history_length"] == 3
    assert "TargetActor" not in detection.object_id


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


def test_real_runtime_mobile_secondary_recon_uses_cued_subclusters(tmp_path: Path) -> None:
    settings_path = write_dynamic_computer_vision_settings(
        tmp_path / "cv_mobile_recon_settings.json",
        camera_vehicle_names=default_cv_5v5_camera_vehicle_names(),
        secondary_vehicle_names=default_cv_5v5_secondary_vehicle_names(),
        camera_spacing_m=20.0,
        camera_z=-10.0,
        target_z=-10.0,
        secondary_height_above_targets_m=200.0,
        secondary_fov_degrees=80.0,
        secondary_camera_pitch_deg=0.0,
        secondary_width=1920,
        secondary_height=1080,
    )
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
        cv_secondary_look_at_enabled=True,
        cv_secondary_mobile_recon_enabled=True,
        cv_secondary_recon_standoff_m=5.0,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_cv_5v5_d4d5_stress_actor_target_specs(),
        detection_filter_names=("MSM_TargetActor_*",),
        metadata={
            "d4d5_stress_enabled": True,
            "secondary_recon_mode": "mobile_recon_gimbal",
            "secondary_guidance_source": "radar_global_track_cue",
        },
    )

    runtime.setup_episode(config)
    frame = runtime.sample_frame(config, frame_index=0, timestamp=0.0, output_dir=tmp_path)
    runtime.teardown_episode(config)

    guidance = {
        item["vehicle_name"]: item
        for item in frame.metadata["cv_camera_guidance"]
        if item["role"] == "secondary_recon_camera"
    }
    assert set(guidance) == set(secondaries)
    assert guidance["Secondary_Recon_1"]["capability_class"] == "mobile_high_recon"
    assert guidance["Secondary_Recon_1"]["cue_source"] == "radar_global_track_cue"
    assert guidance["Secondary_Recon_1"]["coverage_cell"] == "cell-north"
    assert guidance["Secondary_Recon_2"]["coverage_cell"] == "cell-south"
    assert guidance["Secondary_Recon_1"]["gimbal_pointing_ok"] is True
    assert guidance["Secondary_Recon_1"]["cue_pointing_error_m"] == 0.0
    assert "Secondary_Recon_1" in fake_client.vehicle_poses
    assert guidance["Secondary_Recon_1"]["position_ned"][2] == -210.0
    assert guidance["Secondary_Recon_1"]["position_ned"][0] < guidance["Secondary_Recon_1"]["cue_position_ned"][0]


def test_real_runtime_three_mobile_secondary_recon_nodes_use_three_coverage_cells(
    tmp_path: Path,
) -> None:
    settings_path = write_dynamic_computer_vision_settings(
        tmp_path / "cv_mobile_recon_3sec_settings.json",
        camera_vehicle_names=default_cv_5v5_camera_vehicle_names(),
        secondary_vehicle_names=("Secondary_Recon_1", "Secondary_Recon_2", "Secondary_Recon_3"),
        camera_spacing_m=20.0,
        camera_z=-10.0,
        target_z=-10.0,
        secondary_height_above_targets_m=200.0,
        secondary_fov_degrees=80.0,
        secondary_camera_pitch_deg=0.0,
        secondary_width=1920,
        secondary_height=1080,
    )
    resources = default_cv_5v5_camera_vehicle_names()
    secondaries = ("Secondary_Recon_1", "Secondary_Recon_2", "Secondary_Recon_3")
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
        cv_secondary_look_at_enabled=True,
        cv_secondary_mobile_recon_enabled=True,
        cv_secondary_recon_standoff_m=5.0,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_cv_5v5_d4d5_stress_actor_target_specs(),
        detection_filter_names=("MSM_TargetActor_*",),
        metadata={
            "d4d5_stress_enabled": True,
            "secondary_recon_mode": "mobile_recon_gimbal",
            "secondary_guidance_source": "radar_global_track_cue",
        },
    )

    runtime.setup_episode(config)
    frame = runtime.sample_frame(config, frame_index=0, timestamp=0.0, output_dir=tmp_path)
    runtime.teardown_episode(config)

    guidance = {
        item["vehicle_name"]: item
        for item in frame.metadata["cv_camera_guidance"]
        if item["role"] == "secondary_recon_camera"
    }
    truth_by_id = {truth.object_id: truth for truth in frame.truth_objects}
    assert {
        guidance[name]["coverage_cell"]
        for name in secondaries
    } == {"cell-left", "cell-center", "cell-right"}
    assert guidance["Secondary_Recon_1"]["active_target_ids"] == ["TGT-001", "TGT-002"]
    assert guidance["Secondary_Recon_2"]["active_target_ids"] == ["TGT-003"]
    assert guidance["Secondary_Recon_3"]["active_target_ids"] == ["TGT-004", "TGT-005"]
    assert truth_by_id["TGT-001"].coverage_cell == "cell-left"
    assert truth_by_id["TGT-003"].coverage_cell == "cell-center"
    assert truth_by_id["TGT-005"].coverage_cell == "cell-right"
    assert all(guidance[name]["gimbal_pointing_ok"] is True for name in secondaries)


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
    assert no_degrade.metrics["secondary_network_global_view_rate"] == 1.0
    assert no_degrade.metrics["cross_view_association_count"] == len(resources)
    assert no_degrade.metrics["duplicate_terminal_lock_risk"] is False
    assert no_degrade.metrics["secondary_bbox_area_px_stats"] == {
        "count": len(frames) * len(secondaries) * 5,
        "min": 400.0,
        "max": 400.0,
        "mean": 400.0,
        "median": 400.0,
        "sum": float(len(frames) * len(secondaries) * 5 * 400),
    }
    assert no_degrade.metrics["terminal_associator_call_count"] == len(frames) * len(resources)
    assert no_degrade.metrics["terminal_associator_locked_count"] >= len(resources)
    assert secondary.metrics["terminal_associator_reacquire_count"] >= 1
    assert distributed.metrics["terminal_associator_reacquire_count"] >= 1
    assert no_degrade.output_paths["d4d5_stress_case_report"].exists()
    report_text = no_degrade.output_paths["d4d5_stress_case_report"].read_text(encoding="utf-8")
    for metric_name in (
        "secondary_height_above_targets_m",
        "secondary_bbox_area_px_stats",
        "secondary_network_global_view_rate",
        "cross_view_association_count",
        "duplicate_terminal_lock_risk",
    ):
        assert metric_name in report_text
    observation_lines = no_degrade.output_paths["d5_terminal_observations_jsonl"].read_text(
        encoding="utf-8"
    ).splitlines()
    assert observation_lines
    observation_payloads = [json.loads(line) for line in observation_lines]
    assert any(
        item["metadata"].get("detect_to_global_track_registration") is True
        for item in observation_payloads
    )
    candidate_lines = no_degrade.output_paths["d5_detect_to_global_candidates_jsonl"].read_text(
        encoding="utf-8"
    ).splitlines()
    assert candidate_lines
    candidate_payloads = [json.loads(line) for line in candidate_lines]
    assert {
        item["camera_pose_source"]
        for item in candidate_payloads
    } == {"airsim_camera_pose"}
    assert all("projection_valid" in item for item in candidate_payloads)
    assert all(item.get("bbox_area_px", 0.0) > 0.0 for item in candidate_payloads)
    assert all("stable_cross_view_support" in item for item in candidate_payloads)
    assert no_degrade.metrics["detect_to_global_candidate_count"] == len(candidate_payloads)
    assert no_degrade.metrics["camera_pose_source_counts"] == {"airsim_camera_pose": len(candidate_payloads)}
    assert "projection_valid_rate" in no_degrade.metrics
    assert "geometry_gate_pass_rate" in no_degrade.metrics
    assert all(
        item["metadata"].get("terminal_associator_used") is True
        or item["metadata"].get("detect_to_global_track_registration") is True
        for item in observation_payloads
    )
    assert {
        item["terminal_association"]["assigned_global_track_id"]
        for item in observation_payloads
        if item.get("terminal_association") is not None
    } == {f"G-TGT-{index + 1:03d}" for index in range(len(resources))}


def test_d4d5_stress_analysis_reports_frame_secondary_height_above_targets_200m(
    tmp_path: Path,
) -> None:
    frames = _cv5v5_stress_frames(tmp_path)
    secondaries = set(default_cv_5v5_secondary_vehicle_names())
    target_z = sum(truth.position_ned[2] for truth in frames[0].truth_objects) / len(frames[0].truth_objects)
    secondary_z = target_z - 200.0
    high_secondary_frames = [
        replace(
            frame,
            cameras=tuple(
                replace(camera, position_ned=(camera.position_ned[0], camera.position_ned[1], secondary_z))
                if camera.owner_id in secondaries
                else camera
                for camera in frame.cameras
            ),
        )
        for frame in frames
    ]

    result = run_d4d5_stress_analysis(
        high_secondary_frames,
        tmp_path / "height_200m",
        case_name="no_degradation",
        resource_vehicle_names=default_cv_5v5_camera_vehicle_names(),
        secondary_camera_vehicle_names=default_cv_5v5_secondary_vehicle_names(),
    )

    assert result.metrics["geometry"]["secondary_height_above_targets_m"] == 200.0
    assert result.metrics["secondary_height_above_targets_m"] == 200.0
    report_text = result.output_paths["d4d5_stress_case_report"].read_text(encoding="utf-8")
    assert "`secondary_height_above_targets_m`: 200.00" in report_text
    assert "secondary_bbox_area_px_stats" in report_text


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


def test_blocks_detection_adapter_does_not_override_bbox_center_by_default() -> None:
    frame = _sample_frame()
    frame = AirSimFrame(
        **{
            **frame.__dict__,
            "visual_detections": (
                AirSimDetectionBox(
                    detection_id="det-1",
                    camera_id="Interceptor:0",
                    object_id="TGT-001",
                    local_track_id="Interceptor:0:MSM_TargetActor_1",
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
    terminal_track = SimpleNamespace(
        global_track_id="G-001",
        position=np.array([0.0, 0.0, 20.0]),
        velocity=np.zeros(3),
        covariance=np.eye(3),
        category="uav",
        timestamp=0.0,
        track_version=0,
    )
    camera = CameraModel(
        K=np.array([[160.0, 0.0, 320.0], [0.0, 160.0, 240.0], [0.0, 0.0, 1.0]]),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
    )

    local_tracks, _truth_map = local_visual_tracks_from_blocks_frame(
        frame,
        [d2_track],
        terminal_tracks=[terminal_track],
        terminal_associator=TerminalAssociator(),
        terminal_camera=camera,
    )

    assert tuple(local_tracks[0].center_px) == (20.0, 30.0)


def test_geometric_adapter_ignores_wrong_object_ids_for_online_assignment() -> None:
    frame = _sample_frame()
    frame = AirSimFrame(
        **{
            **frame.__dict__,
            "visual_detections": (
                AirSimDetectionBox(
                    detection_id="det-right",
                    camera_id="Interceptor:0",
                    object_id="TGT-001",
                    local_track_id="det-right",
                    timestamp=0.0,
                    center_px=(1.0, 1.0),
                    bbox_xyxy=(328.0, 232.0, 344.0, 248.0),
                    confidence=0.95,
                    classification_hint="uav",
                ),
                AirSimDetectionBox(
                    detection_id="det-left",
                    camera_id="Interceptor:0",
                    object_id="TGT-002",
                    local_track_id="det-left",
                    timestamp=0.0,
                    center_px=(999.0, 999.0),
                    bbox_xyxy=(296.0, 232.0, 312.0, 248.0),
                    confidence=0.95,
                    classification_hint="uav",
                ),
            ),
        }
    )
    local_tracks = geometric_local_visual_tracks_from_blocks_frame(frame)
    camera = camera_model_from_airsim_camera_info(
        SimpleNamespace(
            fx=160.0,
            fy=160.0,
            cx=320.0,
            cy=240.0,
            width=640,
            height=480,
            position_ned=(0.0, 0.0, 0.0),
            rotation_world_to_camera=np.eye(3),
        ),
        measurement_sigma_px=20.0,
    )
    global_tracks = [
        GlobalTrack(
            global_track_id="G-left",
            position=np.array([-2.0, 0.0, 20.0]),
            velocity=np.zeros(3),
            covariance=np.diag([0.1, 0.1, 0.1]),
            category="uav",
        ),
        GlobalTrack(
            global_track_id="G-right",
            position=np.array([2.0, 0.0, 20.0]),
            velocity=np.zeros(3),
            covariance=np.diag([0.1, 0.1, 0.1]),
            category="uav",
        ),
    ]

    result = associate_tracks_to_detections_geometrically(
        global_tracks,
        local_tracks,
        camera,
        config=AssociationConfig(gate_chi2=25.0, min_lock_margin=1.0),
        timestamp=0.0,
    )

    assert {track.local_track_id: tuple(track.center_px) for track in local_tracks} == {
        "det-right": (336.0, 240.0),
        "det-left": (304.0, 240.0),
    }
    assert result.assignments == {"G-left": "det-left", "G-right": "det-right"}

    truth_map = offline_truth_map_from_blocks_frame(
        frame,
        [
            SimpleNamespace(truth_id="TGT-001", global_track_id="G-left"),
            SimpleNamespace(truth_id="TGT-002", global_track_id="G-right"),
        ],
    )
    metrics = evaluate_associations_offline(result, truth_map)
    assert truth_map == {"det-right": "G-left", "det-left": "G-right"}
    assert metrics.evaluated_count == 2
    assert metrics.id_mismatch_count == 2
    assert metrics.association_accuracy == 0.0


def test_real_runtime_camera_metadata_uses_settings_intrinsics_and_pose(tmp_path: Path) -> None:
    settings_path = tmp_path / "cv_2v2_settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "SimMode": "ComputerVision",
                "CameraDefaults": {
                    "CaptureSettings": [
                        {"ImageType": 0, "Width": 640, "Height": 480, "FOV_Degrees": 120}
                    ]
                },
                "Vehicles": {
                    "Cam1": {
                        "VehicleType": "ComputerVision",
                        "X": 10,
                        "Y": -4,
                        "Z": -2,
                        "Yaw": 90,
                        "Cameras": {"0": {"X": 0.5, "Y": 0.0, "Z": 0.0}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    fake_client = FakeAirSimClient(vehicle_names=("Cam1",))
    fake_client.vehicle_poses["Cam1"] = SimpleNamespace(
        position=_vector(0.5, 0.0, 0.0),
        orientation=FakeAirSimModule.Quaternionr(0.0, 0.0, 0.70710678, 0.70710678),
    )
    runtime = RealAirSimRuntimeClient(
        client_factory=lambda **_kwargs: fake_client,
        airsim_module=FakeAirSimModule,
    )
    config = BlocksSmokeConfig(
        settings_path=settings_path,
        camera_vehicle_name="Cam1",
        camera_vehicle_names=("Cam1",),
        resource_vehicle_names=(),
        target_vehicle_names=(),
        capture_lidar=False,
    )

    frame = runtime.sample_frame(config, frame_index=0, timestamp=0.0, output_dir=tmp_path)

    camera = frame.cameras[0]
    assert camera.width == 640
    assert camera.height == 480
    np.testing.assert_allclose(camera.fx, 184.752086, atol=1e-5)
    assert camera.cx == 320.0
    assert camera.cy == 240.0
    assert camera.position_ned == (10.5, -4.0, -2.0)
    assert not np.allclose(np.asarray(camera.rotation_world_to_camera), np.eye(3))


def test_main_episode_bus_writes_d1_to_d7_records_for_d6(tmp_path: Path) -> None:
    resources = tuple(f"Interceptor{index}" for index in range(1, 6))
    frames = [
        _sample_5v5_frame(timestamp=float(index) * 0.5, frame_index=index)
        for index in range(3)
    ]
    config = BlocksSmokeConfig(
        episode_id="pytest_main_bus_5v5",
        scenario_name="blocks_actor_n5",
        duration_s=1.0,
        dt_s=0.5,
        output_root=tmp_path,
        launch_blocks=False,
        resource_vehicle_names=resources,
        camera_vehicle_names=resources,
        target_vehicle_names=(),
    )

    result = run_main_episode_bus(config, frames, tmp_path / "main_bus")

    assert result.frame_count == 3
    for path in result.output_paths.values():
        assert path.exists()
    collector, truth_summary = load_episode_log_jsonl(
        result.output_paths["main_episode_bus_jsonl"]
    )
    assert truth_summary["target_count"] == 5
    assert truth_summary["resource_count"] == 5
    assert truth_summary["drone_count"] == 5
    assert truth_summary["standard_mapping_version"] == "cuas-standard-map-v1"
    assert truth_summary["scenario_version"].startswith(
        "blocks_actor_n5:resources5:targets5:cameras5:seed7:backendairsim:"
    )
    assert len(collector.track_records) >= 15
    assert len(collector.assignment_records) >= 5
    assert len(collector.terminal_records) >= 5
    assert len(collector.link_records) >= 15

    ticks = [
        json.loads(line)
        for line in result.output_paths["main_episode_bus_ticks_jsonl"]
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(ticks) == 3
    assert ticks[0]["clock"]["clock_source"] == "airsim_frame_timestamp"
    assert ticks[0]["clock"]["episode_time_s"] == 0.0
    assert ticks[0]["clock"]["publish_timestamp"] == 0.0
    assert ticks[0]["module_health"]["D1"]["status"] == "ok"
    assert ticks[0]["module_health"]["D6"]["status"] == "passive_collector"
    first_observation = ticks[0]["d1"]["observations"][0]
    assert first_observation["measurement_timestamp"] == 0.0
    assert first_observation["arrival_timestamp"] == 0.2
    assert first_observation["covariance_trace"] is not None
    assert "id_switch_count" in ticks[-1]["d2"]
    assert "track_continuity" in ticks[-1]["d2"]
    assert ticks[-1]["d3"]["resource_count"] == 5
    assert ticks[-1]["d3"]["target_count"] == 5
    assert ticks[-1]["d3"]["plan_version"] >= 1
    assert ticks[-1]["d3"]["terminal_feedback_writeback"]["feedback_count"] == 5
    assert ticks[-1]["d3"]["terminal_feedback_writeback"]["hold_resource_ids"] == []
    assert ticks[-1]["d5"]["terminal_association_count"] == 5
    assert ticks[-1]["d7"]["runtime_bus"]["sample_count"] == 5
    assert ticks[-1]["d7"]["runtime_bus"]["control_context_count"] == 5

    d4_events = [
        event
        for event in collector.event_records
        if event.event_type
        in {"active_degradation_decision", "d4_arbitration_decision", "passive_failover_start"}
    ]
    assert d4_events
    assert all("d4_action" in event.metadata for event in d4_events)
    assert all("degradation_mode" in event.metadata for event in d4_events)
    d4_actions = [event.metadata["d4_action"] for event in d4_events]
    assert "continue_center" in d4_actions
    assert d4_actions.count("request_center_replan") < len(d4_actions)
    d7_events = [
        event for event in collector.event_records if event.event_type == "d7_guidance_record"
    ]
    assert d7_events
    assert all("plan_version" in event.metadata for event in d7_events)
    assert all("d4_action" in event.metadata for event in d7_events)
    assert all("d5_decision_state" in event.metadata for event in d7_events)
    assert all("terminal_switch_allowed" in event.metadata for event in d7_events)
    assert all("d7_runtime_bus_boundary" in event.metadata for event in d7_events)
    assert all(
        event.metadata["global_track_id"] == event.metadata["target_id"]
        for event in d7_events
    )
    assert all(
        record.assigned_global_track_id == record.expected_global_track_id
        for record in collector.terminal_records
    )
    metrics_payload = json.loads(
        result.output_paths["main_episode_bus_metrics_json"].read_text(encoding="utf-8")
    )
    metrics_metadata = metrics_payload["metrics"]["metadata"]
    assert metrics_metadata["mission_outcome"] == "success"
    assert metrics_metadata["success_reason"] == "episode_bus_records_complete"
    assert metrics_metadata["clock"]["frame_count"] == 3
    assert metrics_metadata["module_health"]["D7"]["status"] == "ok"
    assert metrics_metadata["standard_mapping_version"] == "cuas-standard-map-v1"
    assert metrics_metadata["scenario_version"].startswith(
        "blocks_actor_n5:resources5:targets5:cameras5:seed7:backendairsim:"
    )
    assert metrics_metadata["scenario_config"]["resource_vehicle_names"] == list(resources)
    assert (
        metrics_metadata["scenario_config"]["standard_mapping_version"]
        == "cuas-standard-map-v1"
    )
    summary_payload = json.loads(
        result.output_paths["main_episode_bus_summary_json"].read_text(encoding="utf-8")
    )
    assert summary_payload["mission_outcome"]["mission_outcome"] == "success"
    assert summary_payload["module_health"]["D6"]["status"] == "passive_collector"
    assert summary_payload["scenario_config"]["target_count"] == 5
    assert summary_payload["standard_mapping_version"] == "cuas-standard-map-v1"
    assert summary_payload["scenario_version"].startswith(
        "blocks_actor_n5:resources5:targets5:cameras5:seed7:backendairsim:"
    )


def test_main_episode_bus_records_failed_outcome_on_module_exception(
    tmp_path: Path,
    monkeypatch,
) -> None:
    frame = _sample_5v5_frame(timestamp=0.0, frame_index=0)

    def _raise_observation_error(*_args, **_kwargs):
        raise RuntimeError("synthetic D1 adapter failure")

    monkeypatch.setattr(
        episode_bus_module,
        "observations_from_blocks_frame",
        _raise_observation_error,
    )
    config = BlocksSmokeConfig(
        episode_id="pytest_main_bus_failure",
        scenario_name="blocks_actor_n5",
        duration_s=0.5,
        dt_s=0.5,
        output_root=tmp_path,
        launch_blocks=False,
        resource_vehicle_names=tuple(f"Interceptor{index}" for index in range(1, 6)),
        target_vehicle_names=(),
    )

    result = run_main_episode_bus(config, [frame], tmp_path / "main_bus_failure")

    metrics_payload = json.loads(
        result.output_paths["main_episode_bus_metrics_json"].read_text(encoding="utf-8")
    )
    metrics_metadata = metrics_payload["metrics"]["metadata"]
    assert metrics_metadata["mission_outcome"] == "failed"
    assert metrics_metadata["failure_reason"] == "runtime_exception"
    assert metrics_metadata["module_health"]["main_episode_bus"]["status"] == "failed"
    assert metrics_metadata["runtime_errors"][0]["error_type"] == "RuntimeError"
    assert metrics_metadata["top_failure_causes"][0]["cause"] == "runtime_exception"

    collector, _truth_summary = load_episode_log_jsonl(
        result.output_paths["main_episode_bus_jsonl"]
    )
    runtime_events = [
        event for event in collector.event_records if event.event_type == "runtime_exception"
    ]
    assert runtime_events
    assert runtime_events[0].metadata["failure_reason"] == "runtime_exception"


def test_main_episode_bus_marks_secondary_takeover_plan_for_d7(tmp_path: Path) -> None:
    resources = tuple(f"Interceptor{index}" for index in range(1, 6))
    secondary_names = ("SEC-NORTH", "SEC-SOUTH")
    frames = []
    for index in range(4):
        frame = _sample_5v5_frame(timestamp=float(index) * 0.5, frame_index=index)
        frame = replace(
            frame,
            center_node_alive=index == 0,
            secondary_nodes_alive=True,
            metadata={
                **frame.metadata,
                "secondary_camera_vehicle_names": list(secondary_names),
                "images": [
                    {
                        "camera_vehicle_name": secondary_name,
                        "camera_name": "0",
                        "ok": True,
                        "width": 1280,
                        "height": 720,
                    }
                    for secondary_name in secondary_names
                ],
            },
        )
        frames.append(frame)
    config = BlocksSmokeConfig(
        episode_id="pytest_main_bus_secondary_takeover",
        scenario_name="blocks_actor_n5_secondary_takeover",
        duration_s=1.5,
        dt_s=0.5,
        output_root=tmp_path,
        launch_blocks=False,
        resource_vehicle_names=resources,
        camera_vehicle_names=resources,
        secondary_camera_vehicle_names=secondary_names,
        target_vehicle_names=(),
    )

    result = run_main_episode_bus(config, frames, tmp_path / "main_bus_secondary")

    ticks = [
        json.loads(line)
        for line in result.output_paths["main_episode_bus_ticks_jsonl"]
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert ticks[1]["d3"]["active_plan_owner"] == "center"
    assert "degrade_to_secondary" in ticks[1]["d4"]["actions"]
    assert "d4_reassign_pending" in ticks[1]["d7"]["terminal_contract_reject_reasons"]
    assert ticks[2]["d3"]["active_plan_owner"] == "secondary"
    assert ticks[2]["d3"]["plan_schema"] == "secondary_plan_v2"
    assert result.summary["current_plan"]["active_plan_owner"] == "secondary"
    assert result.summary["current_plan"]["plan_schema"] == "secondary_plan_v2"
    assert result.summary["current_plan"]["owner_node_id"] in secondary_names

    collector, _truth_summary = load_episode_log_jsonl(
        result.output_paths["main_episode_bus_jsonl"]
    )
    d4_events = [
        event
        for event in collector.event_records
        if event.event_type
        in {"active_degradation_decision", "d4_arbitration_decision", "passive_failover_start"}
    ]
    assert any(
        event.metadata.get("secondary_takeover_state") == "pending_secondary_plan"
        for event in d4_events
    )
    assert any(
        event.metadata.get("secondary_takeover_state") == "secondary_plan_active"
        for event in d4_events
    )


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
    assert result.metadata["main_episode_bus"]["record_counts"]["ticks"] == 3
    assert result.output_paths["main_episode_bus_jsonl"].exists()
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
    assert result.output_paths["main_episode_bus_jsonl"].exists()
    assert result.metadata["main_episode_bus"]["record_counts"]["ticks"] == 3


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
    assert result.metadata["main_episode_bus"]["execution_metrics_merged"] is True
    assert result.output_paths["main_episode_bus_contract_metrics_json"].exists()
    bus_metrics = json.loads(
        result.output_paths["main_episode_bus_metrics_json"].read_text(encoding="utf-8")
    )
    assert bus_metrics["metrics"]["intercept_success_count"] == summary["success_count"]
    assert bus_metrics["metrics"]["metadata"]["main_episode_bus_execution_metrics_merged"] is True
    commands = result.output_paths["control_commands"].read_text(encoding="utf-8")
    assert "guidance_law" in commands
    assert "camera_quality_gate_passed" in commands
    assert "terminal_switch_reject_reason" in commands
    assert "terminal_contract_reject_reason" in commands
    assert "d4_action" in commands
    assert "d5_decision_state" in commands


def test_blocks_orchestrator_runs_mock_5v5_controlled_intercept(tmp_path: Path) -> None:
    resources = tuple(f"Interceptor{index}" for index in range(1, 6))
    config = BlocksSmokeConfig(
        episode_id="pytest_intercept_5v5",
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
        intercept_min_stable_detection_frames=1,
        camera_vehicle_name=resources[0],
        camera_vehicle_names=resources,
        lidar_vehicle_name=resources[0],
        lidar_vehicle_names=resources,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_5v5_actor_target_specs(target_z=-5.0),
    )
    runtime = FiveVFiveFakeBlocksRuntime()
    orchestrator = AirSimBlocksSmokeOrchestrator(runtime=runtime)

    result = orchestrator.run(config)

    assert result.connected is True
    assert result.metadata["control_api_used"] is True
    assert result.metadata["intercept"]["pair_count"] == 5
    assert len(result.metadata["intercept"]["pairs"]) == 5
    assert result.metadata["intercept"]["command_record_count"] >= 5
    assert runtime.released_vehicle_names == resources
    summary = json.loads(result.output_paths["intercept_summary"].read_text(encoding="utf-8"))
    assert summary["pair_count"] == 5
    assert [pair["vehicle_name"] for pair in summary["pairs"]] == list(resources)
    commands = result.output_paths["control_commands"].read_text(encoding="utf-8")
    assert "Interceptor5" in commands
    assert "terminal_switch_allowed" in commands


def test_controlled_5v5_active_center_replan_visual_png(tmp_path: Path) -> None:
    resources = tuple(f"Interceptor{index}" for index in range(1, 6))
    config = BlocksSmokeConfig(
        episode_id="pytest_intercept_5v5_active_center",
        scenario_name="blocks_actor_5v5_active_center_replan",
        duration_s=0.4,
        dt_s=0.1,
        output_root=tmp_path,
        launch_blocks=False,
        connection_timeout_s=0.1,
        include_integrated_pipeline=True,
        execute_intercept=True,
        control_dt_s=0.1,
        intercept_max_duration_s=0.4,
        intercept_terminal_switch_range_m=100.0,
        intercept_min_bbox_area_ratio=0.001,
        intercept_min_stable_detection_frames=1,
        intercept_yaw_mode="look_at_target",
        camera_vehicle_name=resources[0],
        camera_vehicle_names=resources,
        lidar_vehicle_name=resources[0],
        lidar_vehicle_names=resources,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=default_5v5_actor_target_specs(target_z=-5.0),
        metadata={
            "active_center_replan_visual_png": True,
            "active_degradation_time_s": 0.1,
            "center_replan_time_s": 0.2,
            "center_node_id": "C2",
        },
    )
    runtime = FiveVFiveFakeBlocksRuntime()
    orchestrator = AirSimBlocksSmokeOrchestrator(runtime=runtime)

    result = orchestrator.run(config)

    assert result.connected is True
    assert result.output_paths["center_replan_events"].exists()
    summary = json.loads(result.output_paths["intercept_summary"].read_text(encoding="utf-8"))
    assert summary["pair_count"] == 5
    assert {pair["plan_id"] for pair in summary["pairs"]} == {"center_plan_v2"}
    assert {pair["d4_action"] for pair in summary["pairs"]} == {"continue_center"}
    commands = result.output_paths["control_commands"].read_text(encoding="utf-8")
    assert "request_center_replan" in commands
    assert "d4_reassign_pending" in commands
    assert "center_plan_v2" in commands
    assert "png_vm" in commands
    events = json.loads(result.output_paths["center_replan_events"].read_text(encoding="utf-8"))
    assert {event["event_type"] for event in events} >= {
        "active_center_replan_config",
        "center_replan_pending",
        "center_replan_v2",
    }
    assert result.integrated_result is not None
    metrics = result.integrated_result.metrics
    assert metrics["active_degradation_count"] >= 1
    assert metrics["d4_reassign_pending_count"] >= 1
    assert metrics["terminal_lock_count"] >= 1
    assert metrics["visual_png_switch_count"] >= 1
    assert "center_plan_v2" in metrics["metadata"]["plan_ids"]


def test_controlled_2v2_active_degradation_secondary_plan_visual_png(
    tmp_path: Path,
) -> None:
    resources = ("Interceptor1", "Interceptor2")
    config = BlocksSmokeConfig(
        episode_id="pytest_intercept_2v2_active_secondary",
        scenario_name="blocks_actor_2v2_active_secondary_visual_png",
        duration_s=0.4,
        dt_s=0.1,
        output_root=tmp_path,
        launch_blocks=False,
        connection_timeout_s=0.1,
        include_integrated_pipeline=True,
        execute_intercept=True,
        control_dt_s=0.1,
        intercept_max_duration_s=0.4,
        intercept_terminal_switch_range_m=100.0,
        intercept_min_bbox_area_ratio=0.001,
        intercept_min_stable_detection_frames=1,
        intercept_yaw_mode="look_at_target",
        camera_vehicle_name=resources[0],
        camera_vehicle_names=resources,
        lidar_vehicle_name=resources[0],
        lidar_vehicle_names=resources,
        target_vehicle_names=(),
        resource_vehicle_names=resources,
        target_actor_specs=(
            BlocksActorTargetSpec(
                object_id="TGT-001",
                actor_name="MSM_TargetActor_1",
                start_ned=(12.0, -6.0, -2.0),
                velocity_ned=(0.0, 0.0, 0.0),
            ),
            BlocksActorTargetSpec(
                object_id="TGT-002",
                actor_name="MSM_TargetActor_2",
                start_ned=(12.0, 6.0, -2.0),
                velocity_ned=(0.0, 0.0, 0.0),
            ),
        ),
        metadata={
            "active_secondary_visual_png": True,
            "active_degradation_time_s": 0.1,
            "secondary_plan_time_s": 0.2,
            "secondary_node_id": "SEC-01",
        },
    )
    runtime = TwoVTwoActiveSecondaryFakeRuntime()
    orchestrator = AirSimBlocksSmokeOrchestrator(runtime=runtime)

    result = orchestrator.run(config)

    assert result.connected is True
    assert result.output_paths["secondary_reassignment_events"].exists()
    summary = json.loads(result.output_paths["intercept_summary"].read_text(encoding="utf-8"))
    assert summary["pair_count"] == 2
    assert {pair["plan_id"] for pair in summary["pairs"]} == {"secondary_plan_v2"}
    assert {pair["target_id"] for pair in summary["pairs"]} == {"TGT-001", "TGT-002"}
    commands = result.output_paths["control_commands"].read_text(encoding="utf-8")
    assert "degrade_to_secondary" in commands
    assert "d4_reassign_pending" in commands
    assert "secondary_plan_v2" in commands
    assert "png_vm" in commands
    assert result.integrated_result is not None
    metrics = result.integrated_result.metrics
    assert metrics["active_degradation_count"] >= 1
    assert metrics["secondary_reassignment_count"] >= 1
    assert metrics["d4_reassign_pending_count"] >= 1
    assert metrics["terminal_lock_count"] >= 1
    assert metrics["visual_png_switch_count"] >= 1
    assert "secondary_plan_v2" in metrics["metadata"]["plan_ids"]


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


def test_blocks_batch_runner_reuses_one_blocks_process_across_seeds(tmp_path: Path) -> None:
    runtime = CountingFakeBlocksRuntime()
    process_manager = FakeSequenceProcessManager(tmp_path / "batch_process")
    specs = (
        BlocksEpisodeSpec("episode_a", "D1", duration_s=0.0, include_integrated_pipeline=False),
        BlocksEpisodeSpec("episode_b", "full", duration_s=0.0, include_integrated_pipeline=False),
    )
    runs = tuple(
        (
            BlocksSmokeConfig(
                episode_id="base",
                duration_s=0.0,
                output_root=tmp_path,
                seed=seed,
                launch_blocks=False,
                connection_timeout_s=0.1,
            ),
            f"pytest_batch_seed{seed:03d}",
            specs,
        )
        for seed in (1, 2, 3)
    )

    results = run_blocks_batch_sequences(
        runs,
        batch_id="pytest_batch",
        runtime=runtime,
        process_manager=process_manager,
    )

    assert len(results) == 3
    assert process_manager.start_count == 1
    assert process_manager.stop_count == 1
    assert runtime.reset_count == 6
    assert [result.sequence_id for result in results] == [
        "pytest_batch_seed001",
        "pytest_batch_seed002",
        "pytest_batch_seed003",
    ]
    assert all(result.metadata["batch_mode"] == "single_blocks_reset_loop" for result in results)
    assert (tmp_path / "pytest_batch_seed001" / "episode_a" / "airsim_blocks_summary.json").exists()


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
    sequence_report = result.output_paths["d4d5_stress_sequence_report"].read_text(encoding="utf-8")
    for metric_name in (
        "secondary_network_global_view_rate",
        "cross_view_association_count",
        "duplicate_terminal_lock_risk",
    ):
        assert metric_name in sequence_report
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

    def command_velocity_z(self, config, *, vehicle_name, velocity_ned, duration_s, yaw_deg_override=None):
        commands = getattr(self, "velocity_commands", [])
        commands.append((vehicle_name, velocity_ned, duration_s, yaw_deg_override))
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


class FiveVFiveFakeBlocksRuntime(FakeBlocksRuntime):
    def sample_frame(self, config, frame_index, timestamp, output_dir):
        frame = _sample_5v5_frame(timestamp=timestamp, frame_index=frame_index)
        frame.metadata["image"] = {"ok": True, "width": 640, "height": 480}
        frame.metadata["images"] = [
            {"ok": True, "width": 640, "height": 480, "camera_vehicle_name": name}
            for name in config.resource_vehicle_names
        ]
        frame.metadata["lidar"] = {"ok": True, "point_count": 2}
        frame.metadata["lidars"] = [
            {"ok": True, "point_count": 2, "lidar_vehicle_name": name}
            for name in config.resource_vehicle_names
        ]
        frame.metadata["vehicle_names"] = list(config.resource_vehicle_names)
        return frame


class TwoVTwoActiveSecondaryFakeRuntime(FakeBlocksRuntime):
    def sample_frame(self, config, frame_index, timestamp, output_dir):
        frame = _sample_2v2_frame(timestamp=timestamp, frame_index=frame_index)
        frame.metadata["image"] = {"ok": True, "width": 640, "height": 480}
        frame.metadata["images"] = [
            {"ok": True, "width": 640, "height": 480, "camera_vehicle_name": name}
            for name in config.resource_vehicle_names
        ]
        frame.metadata["lidar"] = {"ok": True, "point_count": 2}
        frame.metadata["lidars"] = [
            {"ok": True, "point_count": 2, "lidar_vehicle_name": name}
            for name in config.resource_vehicle_names
        ]
        frame.metadata["vehicle_names"] = list(config.resource_vehicle_names)
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


def _sample_5v5_frame(timestamp: float = 0.0, frame_index: int = 0) -> AirSimFrame:
    resource_y = (-20.0, -10.0, 0.0, 10.0, 20.0)
    truth_objects = []
    resources = []
    detections = []
    for index, y_value in enumerate(resource_y, start=1):
        target_id = f"TGT-{index:03d}"
        vehicle_name = f"Interceptor{index}"
        actor_name = f"MSM_TargetActor_{index}"
        truth_objects.append(
            AirSimTruthObject(
                object_id=target_id,
                object_type="target",
                timestamp=timestamp,
                position_ned=(35.0 + index, y_value, -5.0),
                velocity_ned=(0.0, 0.0, 0.0),
                threat_score=0.9,
                coverage_cell="cell-north" if index <= 3 else "cell-south",
                metadata={"airsim_actor_name": actor_name},
            )
        )
        resources.append(
            AirSimResourceState(
                resource_id=f"INT-{index:02d}",
                timestamp=timestamp,
                position_ned=(0.0, y_value, -5.0),
                velocity_ned=(0.0, 0.0, 0.0),
                coverage_cell="cell-north" if index <= 3 else "cell-south",
                metadata={"airsim_vehicle_name": vehicle_name},
            )
        )
        detections.append(
            AirSimDetectionBox(
                detection_id=f"det-{frame_index}-{index}",
                camera_id=f"{vehicle_name}:0",
                object_id=target_id,
                local_track_id=f"{vehicle_name}:0:{actor_name}",
                timestamp=timestamp,
                center_px=(320.0, 240.0),
                bbox_xyxy=(285.0, 205.0, 355.0, 275.0),
                confidence=0.95,
            )
        )
    return AirSimFrame(
        episode_id="pytest_blocks_5v5",
        scenario_name="blocks_actor_5v5",
        frame_index=frame_index,
        timestamp=timestamp,
        truth_objects=tuple(truth_objects),
        resources=tuple(resources),
        visual_detections=tuple(detections),
        metadata={
            "runtime": "Blocks",
            "real_airsim_used": True,
            "image": {"ok": True},
            "lidar": {"ok": True, "point_count": 2},
            "vehicle_names": [f"Interceptor{index}" for index in range(1, 6)],
            "scene_object_count": 5,
        },
    )


def _sample_2v2_frame(timestamp: float = 0.0, frame_index: int = 0) -> AirSimFrame:
    truth_objects = (
        AirSimTruthObject(
            object_id="TGT-001",
            object_type="target",
            timestamp=timestamp,
            position_ned=(12.0, -6.0, -2.0),
            velocity_ned=(0.0, 0.0, 0.0),
            threat_score=0.9,
            coverage_cell="cell-north",
            metadata={"airsim_actor_name": "MSM_TargetActor_1"},
        ),
        AirSimTruthObject(
            object_id="TGT-002",
            object_type="target",
            timestamp=timestamp,
            position_ned=(12.0, 6.0, -2.0),
            velocity_ned=(0.0, 0.0, 0.0),
            threat_score=0.9,
            coverage_cell="cell-north",
            metadata={"airsim_actor_name": "MSM_TargetActor_2"},
        ),
    )
    resources = (
        AirSimResourceState(
            resource_id="INT-01",
            timestamp=timestamp,
            position_ned=(0.0, -8.0, -2.0),
            velocity_ned=(0.0, 0.0, 0.0),
            coverage_cell="cell-north",
            metadata={"airsim_vehicle_name": "Interceptor1"},
        ),
        AirSimResourceState(
            resource_id="INT-02",
            timestamp=timestamp,
            position_ned=(0.0, 8.0, -2.0),
            velocity_ned=(0.0, 0.0, 0.0),
            coverage_cell="cell-north",
            metadata={"airsim_vehicle_name": "Interceptor2"},
        ),
    )
    detections = []
    for vehicle_name in ("Interceptor1", "Interceptor2"):
        for target_index, target_id in enumerate(("TGT-001", "TGT-002"), start=1):
            actor_name = f"MSM_TargetActor_{target_index}"
            offset = (target_index - 1) * 80.0
            detections.append(
                AirSimDetectionBox(
                    detection_id=f"det-{frame_index}-{vehicle_name}-{target_id}",
                    camera_id=f"{vehicle_name}:0",
                    object_id=target_id,
                    local_track_id=f"{vehicle_name}:0:{actor_name}",
                    timestamp=timestamp,
                    center_px=(300.0 + offset + frame_index, 240.0),
                    bbox_xyxy=(270.0 + offset + frame_index, 210.0, 330.0 + offset + frame_index, 270.0),
                    confidence=0.95,
                )
            )
    return AirSimFrame(
        episode_id="pytest_blocks_2v2_active_secondary",
        scenario_name="blocks_actor_2v2_active_secondary_visual_png",
        frame_index=frame_index,
        timestamp=timestamp,
        truth_objects=truth_objects,
        resources=resources,
        visual_detections=tuple(detections),
        metadata={
            "runtime": "Blocks",
            "real_airsim_used": True,
            "image": {"ok": True},
            "lidar": {"ok": True, "point_count": 2},
            "vehicle_names": ["Interceptor1", "Interceptor2"],
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
