from __future__ import annotations

import json
from pathlib import Path

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.airsim_adapter import (
    AirSimDetectCollector,
    CameraPoseNED,
    DetectionNameResolver,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.config import (
    CameraCalibration,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.run_experiment import (
    run,
)


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.x_val = x
        self.y_val = y


class _Box:
    def __init__(self) -> None:
        self.min = _Point(900.0, 500.0)
        self.max = _Point(920.0, 520.0)


class _Detection:
    def __init__(self, name: str = "Actor_Truth_Target_001", box=None) -> None:
        self.name = name
        self.box2D = box or _Box()


class _Client:
    def simGetDetections(self, *args, **kwargs):
        return [_Detection()]


class _DynamicBox:
    def __init__(self, center_x: float, center_y: float, extent: float = 30.0) -> None:
        self.min = _Point(center_x - extent / 2.0, center_y - extent / 2.0)
        self.max = _Point(center_x + extent / 2.0, center_y + extent / 2.0)


class _TimelineClient:
    def __init__(self, centers_by_camera, events) -> None:
        self.centers_by_camera = centers_by_camera
        self.events = events

    def simGetDetections(self, *args, **kwargs):
        camera_id = kwargs["vehicle_name"]
        self.events.append(("detect", camera_id))
        center_x, center_y = self.centers_by_camera[camera_id]
        return [
            _Detection(
                "MSM_TargetActor_1_42",
                _DynamicBox(center_x, center_y),
            )
        ]


def test_detect_adapter_discards_airsim_object_identity() -> None:
    calibration = CameraCalibration(camera_id="Terminal_CV_01")
    collector = AirSimDetectCollector(
        _Client(),
        {calibration.camera_id: calibration},
        image_type=0,
    )
    records = collector.collect(
        calibration.camera_id,
        measurement_timestamp=1.0,
        arrival_timestamp=1.01,
        pose=CameraPoseNED((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    )
    assert len(records) == 1
    encoded = json.dumps(records[0].to_online_dict()).lower()
    assert "actor" not in encoded
    assert "truth" not in encoded
    assert records[0].recognized is True
    assert records[0].ray_origin_ned_m == (0.0, 0.0, 0.0)


def test_public_runner_writes_fixed_metrics_and_report_paths(tmp_path: Path) -> None:
    artifacts = run(
        fixture_dir=tmp_path / "fixture",
        output_dir=tmp_path / "output",
        mode="offline",
        association_backend="geometry",
        scenario_name="two_by_two_crossing",
    )
    assert artifacts.metrics_path == tmp_path / "output" / "metrics.json"
    assert artifacts.report_path == tmp_path / "output" / "REPORT_CN.md"
    assert artifacts.metrics_path.exists()
    assert artifacts.report_path.exists()
    assert (tmp_path / "output" / "figures" / "01_ned_top_and_height_views.png").exists()
    metrics = json.loads(artifacts.metrics_path.read_text(encoding="utf-8"))
    assert metrics["truth_leakage_count"] == 0


def test_name_resolver_supports_explicit_and_prefix_aliases() -> None:
    resolver = DetectionNameResolver(
        {"MSM_TargetActor_1": "TGT-001"},
        {"AirSimActual_7": "MSM_TargetActor_1"},
    )
    assert resolver.resolve("MSM_TargetActor_1_42") == (
        "TGT-001",
        "actor_name_prefix",
    )
    assert resolver.resolve("AirSimActual_7_3") == (
        "TGT-001",
        "alias_prefix",
    )


def test_airsim_run_advances_every_frame_and_scores_offline_labels(
    tmp_path: Path,
) -> None:
    fixture_dir = tmp_path / "airsim_fixture"
    output_dir = tmp_path / "output"
    fixture_dir.mkdir()
    camera_positions = {
        "Terminal_CV_01": (0.0, -42.0, -128.0),
        "Terminal_CV_02": (8.0, 42.0, -120.0),
    }
    calibrations = {
        camera_id: CameraCalibration(camera_id=camera_id)
        for camera_id in camera_positions
    }
    (fixture_dir / "calibrations.json").write_text(
        json.dumps(
            {
                "schema_version": "terminal-crossview-calibrations-v1",
                "cameras": [item.to_dict() for item in calibrations.values()],
            }
        ),
        encoding="utf-8",
    )
    target = (500.0, 0.0, -120.0)
    centers_by_camera = {}
    for camera_id, position in camera_positions.items():
        calibration = calibrations[camera_id]
        relative = tuple(target[index] - position[index] for index in range(3))
        centers_by_camera[camera_id] = (
            calibration.cx_px + calibration.fx_px * relative[1] / relative[0],
            calibration.cy_px + calibration.fy_px * relative[2] / relative[0],
        )
    frames = [
        {
            "measurement_timestamp": 0.2 * frame_index,
            "arrival_timestamp": 0.2 * frame_index + 0.01,
            "cameras": [
                {
                    "camera_id": camera_id,
                    "position_ned_m": position,
                    "yaw_pitch_roll_deg": (0.0, 0.0, 0.0),
                }
                for camera_id, position in camera_positions.items()
            ],
        }
        for frame_index in range(4)
    ]
    (fixture_dir / "capture_plan.json").write_text(
        json.dumps(
            {
                "schema_version": "terminal-crossview-airsim-capture-plan-v1",
                "apply_vehicle_pose": False,
                "camera_name": "0",
                "frames": frames,
            }
        ),
        encoding="utf-8",
    )
    events = []
    client = _TimelineClient(centers_by_camera, events)

    def advance(frame_index: int, timestamp: float) -> None:
        events.append(("advance", frame_index, timestamp))

    artifacts = run(
        fixture_dir=fixture_dir,
        output_dir=output_dir,
        mode="airsim",
        association_backend="geometry",
        client=client,
        image_type=0,
        frame_advance=advance,
        actor_name_to_truth_target={"MSM_TargetActor_1": "TGT-001"},
    )

    expected_events = []
    for frame_index in range(4):
        expected_events.append(("advance", frame_index, 0.2 * frame_index))
        expected_events.extend(
            ("detect", camera_id) for camera_id in camera_positions
        )
    assert events == expected_events
    truth_map = json.loads(
        (output_dir / "truth" / "local_track_truth_map.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(truth_map["track_to_target"]) == 2
    assert set(truth_map["track_to_target"].values()) == {"TGT-001"}
    metrics = json.loads(artifacts.metrics_path.read_text(encoding="utf-8"))
    assert metrics["association_precision"] == 1.0
    assert metrics["association_recall"] == 1.0
    assert metrics["truth_leakage_count"] == 0
    labels_text = (output_dir / "truth" / "airsim_detection_labels.jsonl").read_text(
        encoding="utf-8"
    )
    assert "MSM_TargetActor_1_42" in labels_text
    for online_path in (
        output_dir / "captured_local_tracks.jsonl",
        output_dir / "online_result.json",
        output_dir / "metrics.json",
    ):
        online_text = online_path.read_text(encoding="utf-8")
        assert "MSM_TargetActor_1_42" not in online_text
        assert "TGT-001" not in online_text
