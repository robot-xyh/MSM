from __future__ import annotations

import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import load_blocks_replay_jsonl


def test_load_blocks_replay_jsonl_evaluates_raw_frames_without_png(tmp_path: Path) -> None:
    frames_path = tmp_path / "blocks_frames.jsonl"
    frames = [
        _frame(
            timestamp=0.0,
            detections=[
                _detection("Interceptor_Cam_1:0", "TGT-001", "L-C1-T1"),
                _detection("Secondary_Recon_1:0", "TGT-001", "L-S1-T1"),
                _detection("Interceptor_Cam_1:0", "TGT-002", "L-C1-T2"),
            ],
        ),
        _frame(
            timestamp=1.0,
            detections=[
                _detection("Interceptor_Cam_1:0", "TGT-001", "L-C1-T1"),
                _detection("Interceptor_Cam_1:0", "TGT-002", "L-C1-T2"),
            ],
        ),
    ]
    _write_jsonl(frames_path, frames)

    collector, truth_summary = load_blocks_replay_jsonl(frames_path)
    metrics = collector.compute_episode(
        episode_id="blocks_cv_5v5_fixture",
        truth_summary=truth_summary,
    )

    assert truth_summary["total_truth_opportunities"] == 4
    assert truth_summary["high_threat_by_timestamp"] == {
        0.0: ["TGT-001"],
        1.0: ["TGT-001"],
    }
    assert truth_summary["scenario"]["source"] == "blocks_frames_jsonl"
    assert truth_summary["scenario"]["offline_only"] is True
    assert truth_summary["scenario"]["resource_count"] == 2
    assert truth_summary["scenario"]["drone_count"] == 2
    assert truth_summary["scenario"]["target_count"] == 2
    assert truth_summary["scenario"]["camera_count"] == 2
    assert metrics.resource_count == 2
    assert metrics.target_count == 2
    assert metrics.camera_count == 2
    assert metrics.drone_count == 2
    assert metrics.detection_probability == pytest.approx(1.0)
    assert metrics.terminal_association_accuracy == pytest.approx(1.0)
    assert metrics.multi_view_consensus_rate == pytest.approx(1.0)
    assert metrics.video_metadata_delivery_rate == pytest.approx(1.0)
    assert metrics.bbox_delivery_rate == pytest.approx(1.0)
    assert metrics.metadata["track_record_count"] == 5
    assert metrics.metadata["terminal_record_count"] == 5
    assert metrics.metadata["link_record_count"] == 9

    video_links = [
        link for link in collector.link_records if link.payload_kind == "video_metadata"
    ]
    bbox_links = [link for link in collector.link_records if link.payload_kind == "bbox"]
    assert video_links
    assert all(link.metadata["png_saved"] is False for link in video_links)
    assert bbox_links[0].metadata["camera_intrinsics"]["fx"] == 320.0
    assert bbox_links[0].metadata["camera_extrinsics"]["position_ned"] == [
        1.0,
        0.0,
        -10.0,
    ]
    assert bbox_links[0].metadata["object_name"] == "MSM_TargetActor_1"


def test_load_blocks_replay_jsonl_evaluates_sensor_observation_links(tmp_path: Path) -> None:
    frames_path = tmp_path / "blocks_frames.jsonl"
    observations_path = tmp_path / "blocks_sensor_observations.jsonl"
    _write_jsonl(
        frames_path,
        [
            {
                "episode_id": "blocks_sensor_fixture",
                "scenario_name": "blocks_cv_5v5",
                "timestamp": 0.0,
                "truth_objects": [
                    {
                        "object_id": "TGT-001",
                        "object_type": "target",
                        "position_ned": [10.0, 0.0, -10.0],
                        "threat_score": 0.9,
                    }
                ],
                "resources": [],
                "cameras": [],
                "visual_detections": [],
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        observations_path,
        [
            {
                "observation_id": "obs-track-001",
                "sensor_id": "BLOCKS-RADAR-01",
                "modality": "radar",
                "measurement_timestamp": 0.0,
                "arrival_timestamp": 0.25,
                "metadata": {"truth_id": "TGT-001"},
                "communication": {
                    "source_node_id": "MAIN-C2",
                    "target_node_id": "D1-FUSION",
                    "payload_kind": "track",
                    "sequence_id": 1,
                    "sent_timestamp": 0.0,
                    "received_timestamp": 0.25,
                    "stale_after_s": 0.1,
                },
            },
            {
                "observation_id": "obs-track-drop",
                "sensor_id": "BLOCKS-RADAR-01",
                "modality": "radar",
                "measurement_timestamp": 0.1,
                "metadata": {"truth_id": "TGT-001"},
                "communication": {
                    "source_node_id": "MAIN-C2",
                    "target_node_id": "D1-FUSION",
                    "payload_kind": "track",
                    "sequence_id": 2,
                    "sent_timestamp": 0.1,
                    "received_timestamp": 0.2,
                    "delivered": False,
                },
            },
        ],
    )

    collector, truth_summary = load_blocks_replay_jsonl(frames_path, observations_path)
    metrics = collector.compute_episode(
        episode_id="blocks_sensor_fixture",
        truth_summary=truth_summary,
    )

    assert metrics.detection_probability == pytest.approx(1.0)
    assert metrics.cross_node_latency_ms == pytest.approx(250.0)
    assert metrics.message_drop_rate == pytest.approx(1.0 / 2.0)
    assert metrics.stale_track_update_count == 1
    assert metrics.metadata["track_record_count"] == 1
    assert metrics.metadata["link_record_count"] == 2


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def _frame(timestamp: float, detections: list[dict[str, object]]) -> dict[str, object]:
    return {
        "episode_id": "blocks_cv_5v5_fixture",
        "scenario_name": "blocks_cv_5v5",
        "frame_index": int(timestamp),
        "timestamp": timestamp,
        "truth_objects": [
            {
                "object_id": "TGT-001",
                "object_type": "target",
                "position_ned": [10.0 + timestamp, 0.0, -10.0],
                "velocity_ned": [1.0, 0.0, 0.0],
                "threat_score": 0.9,
            },
            {
                "object_id": "TGT-002",
                "object_type": "target",
                "position_ned": [20.0 + timestamp, 0.0, -10.0],
                "velocity_ned": [1.0, 0.0, 0.0],
                "threat_score": 0.4,
            },
        ],
        "resources": [
            {
                "resource_id": "INT-01",
                "metadata": {"airsim_vehicle_name": "Interceptor_Cam_1"},
            },
            {
                "resource_id": "SEC-01",
                "metadata": {"airsim_vehicle_name": "Secondary_Recon_1"},
            },
        ],
        "cameras": [
            _camera("Interceptor_Cam_1:0", "Interceptor_Cam_1", [1.0, 0.0, -10.0]),
            _camera("Secondary_Recon_1:0", "Secondary_Recon_1", [-5.0, 0.0, -30.0]),
        ],
        "visual_detections": detections,
        "metadata": {
            "images": [
                {
                    "camera_vehicle_name": "Interceptor_Cam_1",
                    "camera_name": "0",
                    "ok": True,
                    "saved": False,
                    "width": 640,
                    "height": 480,
                },
                {
                    "camera_vehicle_name": "Secondary_Recon_1",
                    "camera_name": "0",
                    "ok": True,
                    "saved": False,
                    "width": 640,
                    "height": 480,
                },
            ]
        },
    }


def _camera(camera_id: str, owner_id: str, position: list[float]) -> dict[str, object]:
    return {
        "camera_id": camera_id,
        "owner_id": owner_id,
        "fx": 320.0,
        "fy": 320.0,
        "cx": 320.0,
        "cy": 240.0,
        "width": 640,
        "height": 480,
        "position_ned": position,
        "rotation_world_to_camera": [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
    }


def _detection(camera_id: str, object_id: str, local_track_id: str) -> dict[str, object]:
    object_index = 1 if object_id == "TGT-001" else 2
    return {
        "camera_id": camera_id,
        "object_id": object_id,
        "detection_id": f"{camera_id}:{object_id}",
        "local_track_id": local_track_id,
        "bbox_xyxy": [10.0, 20.0, 30.0, 40.0],
        "center_px": [20.0, 30.0],
        "confidence": 0.95,
        "metadata": {"airsim_detection_name": f"MSM_TargetActor_{object_index}"},
    }
