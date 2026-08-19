from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import airsim
import pytest

from dual_optical_40target.core import (
    CameraSpec,
    CameraState,
    ScenarioConfig,
    online_truth_leakage_keys,
    scan_yaw_deg,
)
from dual_optical_40target.reporting import load_experiment_result
from dual_optical_40target.runtime import (
    DualOpticalAirSimRunner,
    METRICS_SCHEMA_V3,
    RECORD_MANIFEST_SCHEMA_V3,
    SCENARIO_SCHEMA_V3,
    _box3d_longest_extent,
    _filter_detections_by_actor_name,
    advance_scene_for_detection,
    camera_scan_timestamp,
    pair_scaling_metrics,
    prepare_scene_stepping,
    reprocess_enhanced_outputs,
    tracker_sweep_index,
    write_csv,
    write_airsim_settings,
    write_json,
)
from dual_optical_40target.run_experiment import parse_args


class FakeDetection:
    def __init__(self, name: str, bbox: tuple[float, float, float, float], extent: float = 1.0):
        self.name = name
        self.box2D = SimpleNamespace(
            min=SimpleNamespace(x_val=bbox[0], y_val=bbox[1]),
            max=SimpleNamespace(x_val=bbox[2], y_val=bbox[3]),
        )
        self.box3D = SimpleNamespace(
            min=SimpleNamespace(x_val=0.0, y_val=0.0, z_val=0.0),
            max=SimpleNamespace(x_val=extent, y_val=0.8 * extent, z_val=0.3 * extent),
        )
        self.relative_pose = airsim.Pose(
            airsim.Vector3r(120.0, 0.0, 0.0), airsim.Quaternionr()
        )


class FakePreflightClient:
    def __init__(
        self, *, returned_name_suffix: str = "", stale_detection_name: str = ""
    ) -> None:
        self.scale = 1.0
        self.spawned = False
        self.returned_name_suffix = returned_name_suffix
        self.stale_detection_name = stale_detection_name
        self.destroyed_names: list[str] = []
        self.added_filter_names: list[str] = []
        self.requested_name = ""

    def simDestroyObject(self, name):
        self.destroyed_names.append(str(name))
        if str(name) == getattr(self, "name", ""):
            self.spawned = False
        return True

    def simPause(self, _paused):
        return None

    def simSetCameraFov(self, *_args, **_kwargs):
        return True

    def simSetCameraPose(self, *_args, **_kwargs):
        return True

    def simSpawnObject(self, name, *_args, **_kwargs):
        self.spawned = True
        self.requested_name = str(name)
        self.name = f"{name}{self.returned_name_suffix}"
        return self.name

    def simClearDetectionMeshNames(self, *_args, **_kwargs):
        return None

    def simSetDetectionFilterRadius(self, *_args, **_kwargs):
        return None

    def simAddDetectionFilterMeshName(self, _camera, _image_type, name, **_kwargs):
        self.added_filter_names.append(str(name))
        return None

    def simContinueForTime(self, _duration_s):
        return None

    def simGetDetections(self, *_args, **_kwargs):
        if not self.spawned:
            return []
        detections = []
        if self.stale_detection_name:
            detections.append(
                FakeDetection(
                    self.stale_detection_name,
                    (100.0, 100.0, 200.0, 200.0),
                    99.0,
                )
            )
        detections.append(
            FakeDetection(self.name, (500.0, 400.0, 780.0, 650.0), self.scale)
        )
        return detections

    def simSetObjectScale(self, _name, scale):
        self.scale = float(scale.x_val)
        return True

    def simGetObjectScale(self, _name):
        return airsim.Vector3r(self.scale, self.scale, self.scale)

    def simGetCameraInfo(self, *_args, **kwargs):
        return SimpleNamespace(
            fov=2.93,
            pose=airsim.Pose(airsim.Vector3r(), airsim.Quaternionr()),
        )

    def simGetImages(self, *_args, **_kwargs):
        return [SimpleNamespace(width=1280, height=1024, image_data_uint8=b"png", time_stamp=1)]


class FakePartialSpawnClient:
    def __init__(self) -> None:
        self.spawn_requests: list[str] = []
        self.destroyed_names: list[str] = []

    def reset(self) -> None:
        return None

    def simPause(self, _paused: bool) -> None:
        return None

    def simDestroyObject(self, name: str) -> bool:
        self.destroyed_names.append(str(name))
        return True

    def simSpawnObject(self, name: str, *_args, **_kwargs) -> str:
        self.spawn_requests.append(str(name))
        if len(self.spawn_requests) == 1:
            return f"{name}_AirSimRenamed"
        return ""


def test_settings_are_independent_and_fixed_camera_spec(tmp_path: Path) -> None:
    config = ScenarioConfig()
    path = write_airsim_settings(tmp_path / "settings.json", config, CameraSpec())
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["SimMode"] == "ComputerVision"
    assert payload["ClockSpeed"] == 0.1
    assert set(payload["Vehicles"]) == {"Optical_A", "Optical_B"}
    capture = payload["CameraDefaults"]["CaptureSettings"][0]
    assert capture["Width"] == 1280
    assert capture["Height"] == 1024
    assert capture["FOV_Degrees"] == 2.93


def test_camera_b_phase_offset_changes_yaw_but_not_global_tracker_clock() -> None:
    config = ScenarioConfig(
        scan_mode="continuous_360",
        scan_period_s=2.0,
        camera_b_scan_phase_offset_s=1.0,
    )

    for timestamp, expected_sweep in ((0.0, 0), (1.0, 0), (2.0, 1)):
        assert camera_scan_timestamp(
            config, config.camera_a_name, timestamp
        ) == timestamp
        assert camera_scan_timestamp(
            config, config.camera_b_name, timestamp
        ) == timestamp + 1.0
        assert tracker_sweep_index(config, timestamp) == expected_sweep

        yaw_a = scan_yaw_deg(
            camera_scan_timestamp(config, config.camera_a_name, timestamp),
            0.0,
            period_s=config.scan_period_s,
            mode=config.scan_mode,
        )
        yaw_b = scan_yaw_deg(
            camera_scan_timestamp(config, config.camera_b_name, timestamp),
            0.0,
            period_s=config.scan_period_s,
            mode=config.scan_mode,
        )
        phase_difference = (yaw_b - yaw_a) % 360.0
        assert math.isclose(phase_difference, 180.0, abs_tol=1e-9)


def test_zero_phase_keeps_v4_scan_and_tracker_clocks_identical() -> None:
    config = ScenarioConfig(
        scan_mode="continuous_360",
        scan_period_s=2.0,
        camera_b_scan_phase_offset_s=0.0,
    )

    for timestamp in (0.0, 1.0, 2.0):
        assert camera_scan_timestamp(
            config, config.camera_b_name, timestamp
        ) == timestamp
        assert tracker_sweep_index(config, timestamp) == (0 if timestamp < 2.0 else 1)


def test_paused_continue_steps_one_frame_or_fails_explicitly() -> None:
    class StepClient:
        def __init__(self) -> None:
            self.pauses: list[bool] = []
            self.frames: list[int] = []

        def simPause(self, paused: bool) -> None:
            self.pauses.append(paused)

        def simContinueForFrames(self, count: int) -> None:
            self.frames.append(count)

    client = StepClient()
    prepare_scene_stepping(client, "paused_continue")
    advance_scene_for_detection(client, "paused_continue")
    assert client.pauses == [True]
    assert client.frames == [1]

    with pytest.raises(RuntimeError, match="simPause"):
        prepare_scene_stepping(SimpleNamespace(), "paused_continue")
    with pytest.raises(RuntimeError, match="simContinueForFrames"):
        advance_scene_for_detection(SimpleNamespace(), "paused_continue")


def test_cli_default_target_count_remains_40(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_experiment.py"])
    assert parse_args().target_count == 40


def test_pair_scaling_metrics_cover_40_and_100_target_identities() -> None:
    fragmented = pair_scaling_metrics(40, 47, 45)
    assert fragmented == {
        "ideal_truth_pair_count": 1600,
        "actual_local_pair_count": 2115,
        "fragment_excess_a": 7,
        "fragment_excess_b": 5,
        "pair_expansion_ratio": 2115 / 1600,
    }

    hundred = pair_scaling_metrics(100, 107, 104)
    assert hundred["ideal_truth_pair_count"] == 10_000
    assert hundred["actual_local_pair_count"] == 11_128
    assert hundred["fragment_excess_a"] == 7
    assert hundred["fragment_excess_b"] == 4
    assert hundred["pair_expansion_ratio"] == 11_128 / 10_000


def test_preflight_scales_mesh_to_three_metres(tmp_path: Path) -> None:
    config = ScenarioConfig()
    runner = DualOpticalAirSimRunner(
        config=config,
        camera_spec=CameraSpec(),
        output_dir=tmp_path,
        blocks_script=Path("unused"),
        launch_blocks=False,
    )
    result = runner._run_preflight(airsim, FakePreflightClient())
    assert result["passed"] is True
    assert abs(result["final_longest_extent_m"] - 3.0) <= 0.15
    assert result["final_scale_multiplier"] == 3.0


def test_runner_actor_nonces_are_unique_per_worker(tmp_path: Path) -> None:
    first = DualOpticalAirSimRunner(
        config=ScenarioConfig(),
        camera_spec=CameraSpec(),
        output_dir=tmp_path / "first",
        blocks_script=Path("unused"),
        launch_blocks=False,
    )
    second = DualOpticalAirSimRunner(
        config=ScenarioConfig(),
        camera_spec=CameraSpec(),
        output_dir=tmp_path / "second",
        blocks_script=Path("unused"),
        launch_blocks=False,
    )

    assert first._actor_run_nonce != second._actor_run_nonce
    assert first._actor_name_for_run("Target") != second._actor_name_for_run("Target")
    assert first._actor_name_for_run("Calibration") != second._actor_name_for_run(
        "Calibration"
    )


def test_preflight_uses_only_returned_actor_name_for_detection(
    tmp_path: Path,
) -> None:
    runner = DualOpticalAirSimRunner(
        config=ScenarioConfig(),
        camera_spec=CameraSpec(),
        output_dir=tmp_path,
        blocks_script=Path("unused"),
        launch_blocks=False,
    )
    client = FakePreflightClient(
        returned_name_suffix="_AirSimRenamed",
        stale_detection_name="MSM_DualOptical_Calibration_Target_stale",
    )

    result = runner._run_preflight(airsim, client)

    assert result["passed"] is True
    assert client.requested_name.endswith(runner._actor_run_nonce)
    assert result["spawned_actor_name"] == client.name
    assert client.added_filter_names == [client.name]
    assert client.name in client.destroyed_names


def test_detection_name_guard_rejects_stale_similarly_named_actors() -> None:
    current = FakeDetection("Target_Rcurrent_AirSim", (0.0, 0.0, 1.0, 1.0))
    stale = FakeDetection("Target_Rstale_AirSim", (0.0, 0.0, 1.0, 1.0))
    asset = FakeDetection("TargetAsset", (0.0, 0.0, 1.0, 1.0))

    filtered = _filter_detections_by_actor_name(
        [stale, asset, current], {current.name: "TRUTH-001"}
    )

    assert filtered == [current]


def test_partial_spawn_failure_cleans_actual_returned_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakePartialSpawnClient()
    runner = DualOpticalAirSimRunner(
        config=ScenarioConfig(target_count=2),
        camera_spec=CameraSpec(),
        output_dir=tmp_path,
        blocks_script=Path("unused"),
        launch_blocks=False,
        client=client,
        airsim_module=airsim,
    )
    monkeypatch.setattr(runner, "_connect", lambda: (airsim, client))
    monkeypatch.setattr(
        runner,
        "_run_preflight",
        lambda _airsim, _client: {"passed": True, "final_scale_multiplier": 1.0},
    )
    monkeypatch.setattr(runner, "_new_client", lambda: client)
    monkeypatch.setattr(runner, "_wait_for_client", lambda: None)

    with pytest.raises(RuntimeError, match="failed to spawn actor"):
        runner.run()

    assert len(client.spawn_requests) == 2
    assert all(name.endswith(runner._actor_run_nonce) for name in client.spawn_requests)
    actual_first_name = f"{client.spawn_requests[0]}_AirSimRenamed"
    assert actual_first_name in client.destroyed_names


def test_anonymous_adapter_keeps_name_only_offline(tmp_path: Path) -> None:
    config = ScenarioConfig(target_count=1)
    runner = DualOpticalAirSimRunner(
        config=config,
        camera_spec=CameraSpec(),
        output_dir=tmp_path,
        blocks_script=Path("unused"),
        launch_blocks=False,
    )
    state = CameraState(
        camera_id="Optical_A",
        frame_index=0,
        timestamp=0.0,
        position_ned=config.camera_a_position_ned,
        yaw_deg=26.565051,
        pitch_deg=0.0,
    )
    raw = FakeDetection("MSM_DualOptical_Target_001", (620.0, 490.0, 660.0, 530.0), 3.0)
    online, offline = runner._anonymize_detections(
        [raw],
        camera_id="Optical_A",
        frame_index=0,
        timestamp=0.0,
        arrival_timestamp=0.01,
        camera_state=state,
        current_positions={"TRUTH-001": (2000.0, 0.0, -100.0)},
        actor_to_truth={"MSM_DualOptical_Target_001": "TRUTH-001"},
    )
    assert len(online) == 1
    assert online_truth_leakage_keys([asdict(online[0])]) == ()
    assert offline[0]["truth_id"] == "TRUTH-001"
    assert offline[0]["raw_detection_name"] == "MSM_DualOptical_Target_001"
    assert _box3d_longest_extent(raw) == 3.0


def test_anonymous_adapter_labels_logical_measurement_and_wall_rpc_times(
    tmp_path: Path,
) -> None:
    config = ScenarioConfig(target_count=1)
    runner = DualOpticalAirSimRunner(
        config=config,
        camera_spec=CameraSpec(),
        output_dir=tmp_path,
        blocks_script=Path("unused"),
        launch_blocks=False,
    )
    state = CameraState(
        camera_id=config.camera_a_name,
        frame_index=2,
        timestamp=0.02,
        position_ned=config.camera_a_position_ned,
        yaw_deg=0.0,
        pitch_deg=0.0,
    )
    online, _offline = runner._anonymize_detections(
        [FakeDetection("target", (10.0, 10.0, 20.0, 20.0), 3.0)],
        camera_id=config.camera_a_name,
        frame_index=2,
        timestamp=0.02,
        arrival_timestamp=1_800_000_000.3,
        gimbal_command_timestamp=1_800_000_000.0,
        detection_rpc_start_timestamp=1_800_000_000.1,
        detection_rpc_end_timestamp=1_800_000_000.3,
        camera_state=state,
        current_positions={"T1": (2000.0, 0.0, -100.0)},
        actor_to_truth={},
    )
    detection = online[0]
    assert detection.measurement_timestamp == 0.02
    assert detection.measurement_timestamp_source == "scripted_scene_logical_time"
    assert detection.gimbal_command_timestamp_source == "system_wall_clock_unix_s"
    assert detection.arrival_timestamp_source == "system_wall_clock_unix_s"
    assert detection.detection_rpc_timestamp_source == "system_wall_clock_unix_s"
    assert (
        detection.gimbal_command_timestamp
        < detection.detection_rpc_start_timestamp
        <= detection.detection_rpc_end_timestamp
        == detection.arrival_timestamp
    )


@pytest.mark.parametrize(
    ("scenario_schema", "metrics_schema", "manifest_schema"),
    (
        (
            "dual-optical-40target-scenario-v1",
            "dual-optical-40target-metrics-v1",
            "dual-optical-40target-record-manifest-v1",
        ),
        (
            "dual-optical-40target-scenario-v1",
            "dual-optical-40target-metrics-v2",
            "dual-optical-40target-record-manifest-v2",
        ),
        (SCENARIO_SCHEMA_V3, METRICS_SCHEMA_V3, RECORD_MANIFEST_SCHEMA_V3),
    ),
)
def test_completed_records_can_restore_report_inputs(
    tmp_path: Path,
    scenario_schema: str,
    metrics_schema: str,
    manifest_schema: str,
) -> None:
    config = ScenarioConfig(target_count=1)
    camera = CameraSpec()
    scenario = asdict(config)
    camera_record = asdict(camera) | {
        "vertical_fov_deg": camera.vertical_fov_deg,
        "effective_ifov_mrad": camera.effective_ifov_mrad,
    }
    write_json(
        tmp_path / "scenario.json",
        {
            "schema_version": scenario_schema,
            "independent_experiment": True,
            "scenario": scenario,
            "camera": camera_record,
            "target_specs_offline_truth_only": [
                {
                    "truth_id": "TRUTH-001",
                    "actor_name": "Target_001",
                    "asset_name": "Quadrotor1",
                    "start_ned": [2000.0, 0.0, -100.0],
                    "velocity_ned": [-50.0, 0.0, 0.0],
                }
            ],
        },
    )
    write_json(
        tmp_path / "metrics.json",
        {
            "schema_version": metrics_schema,
            "target_count": 1,
            "false_match_count": 0,
            "duplicate_truth_match_count": 0,
            "acceptance": {"overall_passed": True},
        },
    )
    write_json(tmp_path / "settings.json", {})
    artifact_rows = {
        "online/anonymous_detections.csv": [],
        "online/camera_scan.csv": [],
        "online/local_tracks.csv": [
            {"track_id": "A-T1", "camera_id": "Optical_A", "stable": True},
            {"track_id": "B-T1", "camera_id": "Optical_B", "stable": True},
        ],
        "online/local_track_samples.csv": [
            {
                "track_id": "A-T1",
                "camera_id": "Optical_A",
                "sample_index": 0,
                "sweep_index": 0,
                "measurement_timestamp": 0.0,
                "ray_x_ned": 1.0,
                "ray_y_ned": 0.0,
                "ray_z_ned": 0.0,
                "detection_uids": ["A-D1"],
            },
            {
                "track_id": "B-T1",
                "camera_id": "Optical_B",
                "sample_index": 0,
                "sweep_index": 0,
                "measurement_timestamp": 0.0,
                "ray_x_ned": 1.0,
                "ray_y_ned": 0.0,
                "ray_z_ned": 0.0,
                "detection_uids": ["B-D1"],
            },
        ],
        "online/cross_camera_candidates.csv": [
            {
                "track_a_id": "A-T1",
                "track_b_id": "B-T1",
                "valid": True,
                "rejection_reason": "",
                "cost": 0.1,
                "reprojection_rms_px": 1.0,
                "reprojection_max_px": 2.0,
                "ray_residual_rms_m": 1.0,
                "fitted_speed_mps": 50.0,
                "median_nearest_time_delta_s": 0.0,
                "condition_number": 5.0,
                "observation_count": 8,
                "inlier_count": 8,
                "outlier_count": 0,
                "reference_timestamp": 0.0,
                "position_ned": [2000.0, 0.0, -100.0],
                "velocity_ned": [-50.0, 0.0, 0.0],
            }
        ],
        "online/cross_camera_matches.csv": [
            {
                "match_id": "PAIR-001",
                "track_a_id": "A-T1",
                "track_b_id": "B-T1",
                "cost": 0.1,
                "reference_timestamp": 0.0,
                "position_ned": [2000.0, 0.0, -100.0],
                "velocity_ned": [-50.0, 0.0, 0.0],
            }
        ],
        "truth/match_scoring.csv": [],
        "truth/track_scoring.csv": [],
        "keyframes/manifest.csv": [],
    }
    artifacts = {}
    for relative, rows in artifact_rows.items():
        path = write_csv(tmp_path / relative, rows)
        key = {
            "online/anonymous_detections.csv": "anonymous_detections",
            "online/camera_scan.csv": "camera_scan",
            "online/local_tracks.csv": "local_tracks",
            "online/local_track_samples.csv": "local_track_samples",
            "online/cross_camera_candidates.csv": "cross_camera_candidates",
            "online/cross_camera_matches.csv": "cross_camera_matches",
            "truth/match_scoring.csv": "match_scoring",
            "truth/track_scoring.csv": "track_scoring",
            "keyframes/manifest.csv": "keyframe_manifest",
        }[relative]
        artifacts[key] = str(path.relative_to(tmp_path))
    write_json(
        tmp_path / "record_manifest.json",
        {"schema_version": manifest_schema, "artifacts": artifacts},
    )

    restored = load_experiment_result(tmp_path)

    assert len(restored.tracks_a) == 1
    assert len(restored.tracks_b) == 1
    assert len(restored.association.candidates) == 1
    assert restored.association.matches[0].match_id == "PAIR-001"
    assert restored.target_specs[0].truth_id == "TRUTH-001"

    upgraded = reprocess_enhanced_outputs(restored)
    assert upgraded.metrics["schema_version"] == METRICS_SCHEMA_V3
    assert upgraded.metrics["ideal_truth_pair_count"] == 1
    assert upgraded.metrics["actual_local_pair_count"] == 1
    assert upgraded.metrics["fragment_excess_a"] == 0
    assert upgraded.metrics["fragment_excess_b"] == 0
    assert upgraded.metrics["pair_expansion_ratio"] == 1.0
    assert upgraded.metrics["candidate_screening_elapsed_ms"] >= 0.0
    assert upgraded.metrics["candidate_fitting_elapsed_ms"] >= 0.0
    assert upgraded.metrics["association_processing_elapsed_ms"] >= 0.0
    upgraded_manifest = json.loads(
        (tmp_path / "record_manifest.json").read_text(encoding="utf-8")
    )
    assert upgraded_manifest["schema_version"] == RECORD_MANIFEST_SCHEMA_V3
