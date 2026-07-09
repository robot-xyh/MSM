from __future__ import annotations

from pathlib import Path

import numpy as np

from d5_terminal_association import (
    DEFAULT_YOLOV8_WEIGHTS_PATH,
    TerminalObservationBus,
    YoloMotAdapter,
    YoloMotAdapterConfig,
)


def _frame() -> np.ndarray:
    return np.zeros((64, 64, 3), dtype=np.uint8)


def test_mock_yolo_output_becomes_local_visual_track_with_fallback_metadata() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            tracker_backend="bytetrack",
            confidence_threshold=0.2,
            compute_device="cpu",
            cpu_budget_ms=12.5,
            gpu_budget_ms=0.0,
        ),
        detector=lambda frame: [
            {
                "xyxy": (10.0, 12.0, 30.0, 32.0),
                "confidence": 0.91,
                "class_id": 2,
                "class_name": "uav",
            }
        ],
    )

    result = adapter.process_frame(
        _frame(),
        resource_id="UAV1",
        camera_id="front_rgb",
        frame_id="UAV1/front_rgb",
        timestamp=1.25,
    )

    assert result.status == "ok"
    assert result.detector_backend == "injected_detector"
    assert result.tracker_backend == "iou_fallback"
    assert result.metadata["requested_tracker_backend"] == "bytetrack"
    assert result.metadata["tracker_backend"] == "iou_fallback"
    assert result.metadata["compute_device"] == "cpu"
    assert result.metadata["cpu_budget_ms"] == 12.5
    assert result.metadata["gpu_budget_ms"] == 0.0
    assert len(result.tracks) == 1
    track = result.tracks[0]
    assert track.local_track_id == "front_rgb/yolov8_iou_fallback:track:1"
    assert track.bbox == (10.0, 12.0, 30.0, 32.0)
    np.testing.assert_allclose(track.center_px, np.array([20.0, 22.0]))
    assert track.category == "uav"
    assert track.quality == 0.91
    assert track.timestamp == 1.25
    assert result.metadata["confidence_by_local_track_id"][track.local_track_id] == 0.91
    assert result.metadata["class_id_by_local_track_id"][track.local_track_id] == 2
    assert result.metadata["bbox_area_px_by_local_track_id"][track.local_track_id] == 400.0
    assert np.isclose(
        result.metadata["bbox_scale_by_local_track_id"][track.local_track_id],
        20.0 / np.hypot(64.0, 64.0),
    )
    assert (
        result.metadata["tracker_backend_by_local_track_id"][track.local_track_id]
        == "iou_fallback"
    )
    assert result.metadata["tracker_id_scope"] == "LocalVisualTrack.local_track_id_only"


def test_iou_fallback_keeps_local_track_id_stable_across_frames() -> None:
    detections_by_frame = [
        [{"xyxy": (10.0, 10.0, 30.0, 30.0), "confidence": 0.9, "class_name": "uav"}],
        [{"xyxy": (12.0, 11.0, 32.0, 31.0), "confidence": 0.88, "class_name": "uav"}],
    ]

    def detector(frame: np.ndarray) -> list[dict]:
        return detections_by_frame.pop(0)

    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(tracker_backend="botsort", confidence_threshold=0.2),
        detector=detector,
    )

    first = adapter.process_frame(_frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.0)
    second = adapter.process_frame(_frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.1)

    assert first.tracks[0].local_track_id == second.tracks[0].local_track_id
    assert first.tracks[0].mot_history_length == 1
    assert second.tracks[0].mot_history_length == 2
    assert second.tracker_backend == "iou_fallback"


def test_truth_and_global_fields_are_ignored_by_yolo_mot_adapter_online() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(confidence_threshold=0.1),
        detector=lambda frame: [
            {
                "bbox_xyxy": (4.0, 5.0, 24.0, 25.0),
                "confidence": 0.7,
                "global_track_id": "G-truth",
                "assigned_global_track_id": "G-assigned",
                "truth_id": "G-truth",
                "true_global_track_id": "G-truth",
                "object_id": "TargetActor_1",
                "actor_name": "TargetActor_1",
            }
        ],
    )

    result = adapter.process_frame(_frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=2.0)
    track = result.tracks[0]

    assert not hasattr(track, "global_track_id")
    assert "G-truth" not in track.local_track_id
    assert "G-assigned" not in track.local_track_id
    assert "TargetActor" not in track.local_track_id
    assert "truth" not in str(result.metadata).lower()
    assert "actor" not in str(result.metadata).lower()

    bus = TerminalObservationBus()
    bus.publish_local_track(
        resource_id="UAV1",
        source_node_id="UAV1",
        link_type="yolo_mot",
        timestamp=2.0,
        local_track=track,
        camera_id="front_rgb",
        frame_id="UAV1/front_rgb",
        metadata=result.metadata,
    )
    assert len(bus.observations()) == 1
    assert bus.cross_view_associations() == []


def test_no_ultralytics_returns_unavailable_with_clear_fallback_status() -> None:
    def missing_loader(weights_path: Path) -> object:
        raise ModuleNotFoundError("No module named 'ultralytics'")

    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="bytetrack",
            confidence_threshold=0.2,
        ),
        ultralytics_loader=missing_loader,
    )

    result = adapter.process_frame(_frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=3.0)

    assert result.status == "unavailable"
    assert result.tracker_backend == "iou_fallback"
    assert result.detector_backend == "unavailable"
    assert result.tracks == ()
    assert "ultralytics" in result.metadata["unavailable_reason"]
    assert result.metadata["requested_tracker_backend"] == "bytetrack"


def test_default_weights_path_points_to_d5_best_pt() -> None:
    assert DEFAULT_YOLOV8_WEIGHTS_PATH == Path(
        "/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt"
    )
