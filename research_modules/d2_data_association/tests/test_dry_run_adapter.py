from __future__ import annotations

import inspect
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np

from d2_data_association import (
    detections_from_d1_global_tracks,
    detections_from_airsim_frame,
    run_airsim_dry_run_association,
)
import d2_data_association.dry_run_adapter as dry_run_adapter

D1_SRC_ROOT = Path(__file__).resolve().parents[2] / "d1_sensor_fusion" / "src"
if str(D1_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(D1_SRC_ROOT))

from d1_sensor_fusion.types import GlobalTrack as D1GlobalTrack
from d1_sensor_fusion.types import TrackLevel


def test_detections_from_airsim_frame_accepts_tracks_key_and_3d_covariance() -> None:
    frame = {
        "timestamp": 1.0,
        "tracks": [
            {
                "track_id": "d1-track-A",
                "truth_id": "A",
                "measurement_timestamp": 0.75,
                "position_ned": {"x": 10.0, "y": -2.0, "z": -5.0},
                "covariance_ned": np.diag([0.2, 0.3, 0.8]),
                "confidence": 0.9,
                "metadata": {"sensor": "synthetic_radar"},
            }
        ],
        "truth_ids_present": ["A"],
    }

    timestamp, detections, truth_ids = detections_from_airsim_frame(frame)

    assert timestamp == 1.0
    assert truth_ids == ["A"]
    assert len(detections) == 1
    detection = detections[0]
    assert detection.detection_id == "d1-track-A"
    assert detection.timestamp == 0.75
    assert detection.position.tolist() == [10.0, -2.0]
    assert detection.covariance.shape == (2, 2)
    assert detection.covariance[0, 0] == 0.2
    assert detection.covariance[1, 1] == 0.3
    assert detection.metadata["sensor"] == "synthetic_radar"
    assert detection.metadata["source_format"] == "airsim_dry_run"
    assert detection.metadata["measurement_timestamp"] == 0.75
    assert detection.metadata["arrival_timestamp"] == 1.0


def test_detections_from_airsim_frame_accepts_x_val_y_val_positions() -> None:
    frame = {
        "timestamp": 2.0,
        "detections": [
            {
                "detection_id": "vector3r-object",
                "truth_id": "A",
                "position": SimpleNamespace(x_val=3.0, y_val=-4.0, z_val=-10.0),
            },
            {
                "detection_id": "vector3r-dict",
                "truth_id": "B",
                "position_ned": {"x_val": 5.0, "y_val": 6.0, "z_val": -12.0},
            },
        ],
        "truth_ids_present": ["A", "B"],
    }

    _, detections, truth_ids = detections_from_airsim_frame(frame)

    assert truth_ids == ["A", "B"]
    assert detections[0].position.tolist() == [3.0, -4.0]
    assert detections[1].position.tolist() == [5.0, 6.0]


def test_airsim_dry_run_association_preserves_metrics_fields() -> None:
    frames = [
        {
            "timestamp": float(step),
            "detections": [
                {
                    "detection_id": f"A-{step}",
                    "truth_id": "A",
                    "position": {"x": float(step), "y": 0.0, "z": -5.0},
                    "covariance": [[0.2, 0.0], [0.0, 0.2]],
                    "truth_position": [float(step), 0.0],
                },
                {
                    "detection_id": f"B-{step}",
                    "truth_id": "B",
                    "position": {"x": float(step), "y": 10.0, "z": -5.0},
                    "covariance": [[0.2, 0.0], [0.0, 0.2]],
                    "truth_position": [float(step), 10.0],
                },
            ],
            "truth_ids_present": ["A", "B"],
        }
        for step in range(4)
    ]

    result = run_airsim_dry_run_association(frames)
    bus_message = result.to_bus_message()

    assert result.metrics["frame_count"] == 4
    assert "id_switch_count" in result.metrics
    assert "track_continuity" in result.metrics
    assert "id_switch_count" in bus_message
    assert "track_continuity" in bus_message
    assert len(result.active_tracks) >= 2
    assert len(result.association_logs) == 4
    assert bus_message["metrics"]["id_switch_count"] == result.metrics["id_switch_count"]
    assert bus_message["metrics"]["track_continuity"] == result.metrics["track_continuity"]


def test_airsim_dry_run_exports_global_track_ids_for_input_sized_episode() -> None:
    target_offsets = [0.0, 12.0, 24.0]
    frames = []
    for step in range(4):
        detections = []
        for target_index, y_offset in enumerate(target_offsets):
            truth_id = f"target-{target_index}"
            detections.append(
                {
                    "detection_id": f"{truth_id}-{step}",
                    "truth_id": truth_id,
                    "position": {
                        "x": float(step),
                        "y": y_offset,
                        "z": -10.0,
                    },
                    "covariance": [[0.2, 0.0], [0.0, 0.2]],
                    "truth_position": [float(step), y_offset],
                }
            )
        frames.append(
            {
                "timestamp": float(step),
                "detections": detections,
                "truth_ids_present": [f"target-{index}" for index in range(3)],
            }
        )

    result = run_airsim_dry_run_association(frames)
    bus_message = result.to_bus_message()

    assert result.metrics["id_switch_count"] == 0
    assert len(result.active_tracks) == 3
    assert len(bus_message["global_track_ids"]) == 3
    assert bus_message["global_track_ids"] == [
        track["global_track_id"] for track in bus_message["active_tracks"]
    ]
    assert set(bus_message["global_track_ids"]) == {"T001", "T002", "T003"}
    assert all("global_track_id" in track for track in bus_message["active_tracks"])


def test_airsim_2v2_replan_keeps_global_track_ids_and_records_no_id_switch() -> None:
    frames = []
    for step in range(4):
        secondary = step >= 2
        source_node_id = "secondary-node-1" if secondary else "central-planner"
        link_type = "secondary_replan" if secondary else "central_plan"
        prefix = "secondary" if secondary else "central"
        frames.append(
            {
                "timestamp": float(step),
                "detections": [
                    {
                        "detection_id": f"{prefix}-A-{step}",
                        "truth_id": "target-A",
                        "position": {"x": float(step), "y": 0.0, "z": -10.0},
                        "covariance": [[0.2, 0.0], [0.0, 0.2]],
                        "truth_position": [float(step), 0.0],
                        "metadata": {
                            "source_node_id": source_node_id,
                            "link_type": link_type,
                        },
                    },
                    {
                        "detection_id": f"{prefix}-B-{step}",
                        "truth_id": "target-B",
                        "position": {"x": float(step), "y": 25.0, "z": -10.0},
                        "covariance": [[0.2, 0.0], [0.0, 0.2]],
                        "truth_position": [float(step), 25.0],
                        "metadata": {
                            "source_node_id": source_node_id,
                            "link_type": link_type,
                        },
                    },
                ],
                "truth_ids_present": ["target-A", "target-B"],
            }
        )

    result = run_airsim_dry_run_association(frames)
    bus_message = result.to_bus_message()

    assert result.metrics["id_switch_count"] == 0
    assert bus_message["id_switch_count"] == 0
    assert bus_message["metrics"]["id_switch_count"] == 0
    assert result.metrics["track_continuity"] == 1.0
    assert result.metrics["confusion_matrix"]["target-A"] == {"T001": 4}
    assert result.metrics["confusion_matrix"]["target-B"] == {"T002": 4}


def test_d1_global_track_adapter_projects_ned_state_covariance_and_timestamps() -> None:
    covariance = np.eye(6)
    covariance[0, 0] = 0.4
    covariance[1, 1] = 0.6
    covariance[0, 1] = 0.05
    covariance[1, 0] = 0.05
    track = D1GlobalTrack(
        global_track_id="G-A",
        state=np.array([12.0, -3.0, -20.0, 1.0, 0.5, 0.0]),
        covariance=covariance,
        timestamp=10.25,
        track_level=TrackLevel.STABLE,
        metadata={
            "frame_id": "ned",
            "measurement_timestamp": 10.0,
            "arrival_timestamp": 10.4,
            "truth_id": "A",
        },
    )

    timestamp, detections, truth_ids = detections_from_d1_global_tracks([track])

    assert timestamp == 10.0
    assert truth_ids == ["A"]
    assert len(detections) == 1
    detection = detections[0]
    assert detection.detection_id == "G-A"
    assert detection.timestamp == 10.0
    assert detection.position.tolist() == [12.0, -3.0]
    assert detection.covariance.tolist() == [[0.4, 0.05], [0.05, 0.6]]
    assert detection.metadata["frame_id"] == "ned"
    assert detection.metadata["source_format"] == "d1_global_track"
    assert detection.metadata["global_track_id"] == "G-A"
    assert detection.metadata["source_global_track_id"] == "G-A"
    assert detection.metadata["measurement_timestamp"] == 10.0
    assert detection.metadata["arrival_timestamp"] == 10.4
    assert detection.metadata["covariance_projection"] == "ned_6d_to_xy"


def test_dry_run_adapter_does_not_import_airsim() -> None:
    source = inspect.getsource(dry_run_adapter)

    assert "import airsim" not in source
    assert "from airsim" not in source
