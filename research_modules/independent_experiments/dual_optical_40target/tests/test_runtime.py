from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

import airsim

from dual_optical_40target.core import (
    CameraSpec,
    CameraState,
    ScenarioConfig,
    online_truth_leakage_keys,
)
from dual_optical_40target.reporting import load_experiment_result
from dual_optical_40target.runtime import (
    DualOpticalAirSimRunner,
    _box3d_longest_extent,
    write_csv,
    write_airsim_settings,
    write_json,
)


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
    def __init__(self) -> None:
        self.scale = 1.0
        self.spawned = False

    def simDestroyObject(self, _name):
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
        self.name = name
        return name

    def simClearDetectionMeshNames(self, *_args, **_kwargs):
        return None

    def simSetDetectionFilterRadius(self, *_args, **_kwargs):
        return None

    def simAddDetectionFilterMeshName(self, *_args, **_kwargs):
        return None

    def simContinueForTime(self, _duration_s):
        return None

    def simGetDetections(self, *_args, **_kwargs):
        if not self.spawned:
            return []
        return [FakeDetection(self.name, (500.0, 400.0, 780.0, 650.0), self.scale)]

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


def test_completed_records_can_restore_report_inputs(tmp_path: Path) -> None:
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
    write_json(tmp_path / "metrics.json", {"acceptance": {"overall_passed": True}})
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
    write_json(tmp_path / "record_manifest.json", {"artifacts": artifacts})

    restored = load_experiment_result(tmp_path)

    assert len(restored.tracks_a) == 1
    assert len(restored.tracks_b) == 1
    assert len(restored.association.candidates) == 1
    assert restored.association.matches[0].match_id == "PAIR-001"
    assert restored.target_specs[0].truth_id == "TRUTH-001"
