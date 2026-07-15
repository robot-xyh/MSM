from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from d5_terminal_association import (
    DEFAULT_YOLOV8_WEIGHTS_PATH,
    TerminalObservationBus,
    YoloMotAdapter,
    YoloMotAdapterConfig,
)


def _frame() -> np.ndarray:
    return np.zeros((64, 64, 3), dtype=np.uint8)


class _FakeNativeModel:
    names = {0: "uav"}

    def __init__(self, *, fail_native: bool = False) -> None:
        self.fail_native = fail_native
        self.track_calls = 0
        self.predict_calls = 0
        self.track_kwargs: list[dict[str, object]] = []
        self.predict_kwargs: list[dict[str, object]] = []

    def track(self, frame: np.ndarray, **kwargs: object) -> list[dict]:
        self.track_calls += 1
        self.track_kwargs.append(dict(kwargs))
        if self.fail_native:
            raise RuntimeError("native tracker unavailable in fixture")
        return [
            {
                "xyxy": (10.0, 10.0, 30.0, 30.0),
                "confidence": 0.9,
                "class_id": 0,
                "track_id": 7,
                "mot_history_length": self.track_calls,
            }
        ]

    def predict(self, frame: np.ndarray, **kwargs: object) -> list[dict]:
        self.predict_calls += 1
        self.predict_kwargs.append(dict(kwargs))
        return [
            {
                "xyxy": (10.0, 10.0, 30.0, 30.0),
                "confidence": 0.9,
                "class_id": 0,
                "names": self.names,
            }
        ]


class _ResultsLikeBoxes:
    def __init__(self, track_ids: list[int]) -> None:
        count = len(track_ids)
        self.xyxy = np.asarray(
            [
                (10.0 + index, 10.0, 30.0 + index, 30.0)
                for index in range(count)
            ],
            dtype=float,
        ).reshape(-1, 4)
        self.conf = np.full(count, 0.9, dtype=float)
        self.cls = np.zeros(count, dtype=float)
        self.id = np.asarray(track_ids, dtype=float)


class _ResultsLike:
    names = {0: "uav"}

    def __init__(self, track_ids: list[int]) -> None:
        self.boxes = _ResultsLikeBoxes(track_ids)


class _ResultsLikeNativeModel:
    names = {0: "uav"}

    def __init__(self, events: list[list[int] | Exception]) -> None:
        self.events = list(events)

    def track(self, frame: np.ndarray, **kwargs: object) -> list[_ResultsLike]:
        if not self.events:
            raise AssertionError("unexpected native tracker call")
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return [_ResultsLike(event)]

    def predict(self, frame: np.ndarray, **kwargs: object) -> list[dict]:
        return [
            {
                "xyxy": (10.0, 10.0, 30.0, 30.0),
                "confidence": 0.9,
                "class_id": 0,
                "names": self.names,
            }
        ]


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


def test_iou_fallback_state_is_isolated_across_interleaved_resource_camera_streams() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(tracker_backend="iou_fallback", confidence_threshold=0.2),
        detector=lambda frame: [
            {"xyxy": (10.0, 10.0, 30.0, 30.0), "confidence": 0.9, "class_name": "uav"}
        ],
    )
    streams = [
        ("UAV1", "front_rgb"),
        ("UAV1", "wide_rgb"),
        ("UAV2", "front_rgb"),
    ]

    first = [
        adapter.process_frame(
            _frame(),
            resource_id=resource_id,
            camera_id=camera_id,
            timestamp=1.0,
        )
        for resource_id, camera_id in streams
    ]
    second = [
        adapter.process_frame(
            _frame(),
            resource_id=resource_id,
            camera_id=camera_id,
            timestamp=1.1,
        )
        for resource_id, camera_id in streams
    ]

    assert [result.tracks[0].mot_history_length for result in first] == [1, 1, 1]
    assert [result.tracks[0].mot_history_length for result in second] == [2, 2, 2]
    assert first[0].tracks[0].local_track_id.startswith("front_rgb/")
    assert first[1].tracks[0].local_track_id.startswith("wide_rgb/")
    assert first[0].metadata["stream_key"] == {
        "resource_id": "UAV1",
        "camera_id": "front_rgb",
    }
    assert first[2].metadata["stream_key_text"] == "UAV2/front_rgb"
    assert all(result.metadata["tracker_state_isolated"] is True for result in first + second)
    assert all(result.metadata["tracker_instance_scope"] == "per_stream" for result in first + second)


def test_per_stream_frame_resolution_is_preserved_for_1080p_and_4k() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(tracker_backend="iou_fallback", confidence_threshold=0.2),
        detector=lambda frame: [
            {
                "xyxy": (10.0, 10.0, float(frame.shape[1] - 1), float(frame.shape[0] - 1)),
                "confidence": 0.9,
                "class_name": "uav",
            }
        ],
    )

    interceptor = adapter.process_frame(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        resource_id="INT-1",
        camera_id="front_rgb",
        timestamp=1.0,
    )
    recon = adapter.process_frame(
        np.zeros((2160, 3840, 3), dtype=np.uint8),
        resource_id="RECON-1",
        camera_id="gimbal_rgb",
        timestamp=1.0,
    )

    assert interceptor.metadata["image_size"] == (1920, 1080)
    assert recon.metadata["image_size"] == (3840, 2160)
    assert interceptor.tracks[0].image_size == (1920, 1080)
    assert recon.tracks[0].image_size == (3840, 2160)
    assert interceptor.tracks[0].metadata["image_size"] == (1920, 1080)
    assert recon.tracks[0].metadata["image_size"] == (3840, 2160)
    assert interceptor.tracks[0].bbox_edge_clip_sides == ("right", "bottom")
    assert recon.tracks[0].bbox_edge_clip_sides == ("right", "bottom")


def test_episode_reset_apis_clear_only_requested_or_all_fallback_streams() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(tracker_backend="iou_fallback", confidence_threshold=0.2),
        detector=lambda frame: [
            {"xyxy": (10.0, 10.0, 30.0, 30.0), "confidence": 0.9, "class_name": "uav"}
        ],
    )

    adapter.process_frame(_frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.0)
    uav1_second = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.1
    )
    adapter.process_frame(_frame(), resource_id="UAV2", camera_id="front_rgb", timestamp=1.0)
    adapter.reset_stream("UAV1", "front_rgb")
    uav1_reset = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=2.0
    )
    uav2_continued = adapter.process_frame(
        _frame(), resource_id="UAV2", camera_id="front_rgb", timestamp=1.1
    )

    assert uav1_second.tracks[0].mot_history_length == 2
    assert uav1_reset.tracks[0].mot_history_length == 1
    assert uav2_continued.tracks[0].mot_history_length == 2

    adapter.reset_all_streams()
    assert adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=3.0
    ).tracks[0].mot_history_length == 1
    assert adapter.process_frame(
        _frame(), resource_id="UAV2", camera_id="front_rgb", timestamp=3.0
    ).tracks[0].mot_history_length == 1


def test_native_tracker_uses_independent_model_instance_per_stream_and_reset() -> None:
    loaded_models: list[_FakeNativeModel] = []

    def loader(weights_path: Path) -> _FakeNativeModel:
        model = _FakeNativeModel()
        loaded_models.append(model)
        return model

    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="bytetrack",
            confidence_threshold=0.2,
        ),
        ultralytics_loader=loader,
    )

    a_first = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.0
    )
    b_first = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="wide_rgb", timestamp=1.0
    )
    a_second = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.1
    )

    assert len(loaded_models) == 2
    assert [a_first.tracks[0].mot_history_length, b_first.tracks[0].mot_history_length] == [1, 1]
    assert a_second.tracks[0].mot_history_length == 2
    assert a_first.tracker_backend == b_first.tracker_backend == "bytetrack"
    assert a_first.metadata["native_model_scope"] == "per_stream"
    assert a_first.metadata["tracker_state_backend"] == "bytetrack"
    assert a_first.metadata["stream_key_text"] == "UAV1/front_rgb"
    assert b_first.metadata["stream_key_text"] == "UAV1/wide_rgb"

    adapter.reset_stream("UAV1", "front_rgb")
    a_reset = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=2.0
    )
    b_continued = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="wide_rgb", timestamp=1.1
    )
    assert len(loaded_models) == 3
    assert a_reset.tracks[0].mot_history_length == 1
    assert b_continued.tracks[0].mot_history_length == 2


def test_native_failure_falls_back_to_per_stream_iou_tracker_without_sharing() -> None:
    loaded_models: list[_FakeNativeModel] = []

    def loader(weights_path: Path) -> _FakeNativeModel:
        model = _FakeNativeModel(fail_native=True)
        loaded_models.append(model)
        return model

    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="botsort",
            confidence_threshold=0.2,
            allow_iou_fallback=True,
        ),
        ultralytics_loader=loader,
    )

    a_first = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.0
    )
    b_first = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="wide_rgb", timestamp=1.0
    )
    a_second = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.1
    )

    assert len(loaded_models) == 3
    assert [a_first.tracks[0].mot_history_length, b_first.tracks[0].mot_history_length] == [1, 1]
    assert a_second.tracks[0].mot_history_length == 2
    assert a_first.tracker_backend == b_first.tracker_backend == "iou_fallback"
    assert a_first.metadata["tracker_state_backend"] == "iou_fallback"
    assert a_first.metadata["native_model_scope"] == "per_stream"
    assert "native tracker unavailable" in a_first.metadata["tracker_fallback_reason"]


@pytest.mark.parametrize("backend", ("bytetrack", "botsort"))
def test_ultralytics_results_history_accumulates_consecutive_native_hits(
    backend: str,
) -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            tracker_backend=backend,
            confidence_threshold=0.2,
        ),
        model=_ResultsLikeNativeModel([[7], [7], [7]]),
    )

    results = [
        adapter.process_frame(
            _frame(),
            resource_id="UAV1",
            camera_id="front_rgb",
            timestamp=1.0 + index * 0.1,
        )
        for index in range(3)
    ]

    assert [result.tracks[0].mot_history_length for result in results] == [1, 2, 3]
    assert results[1].tracks[0].track_transition_state == "continued"
    assert results[2].metadata["native_mot_history_semantics"] == (
        "consecutive_measured_hits_per_resource_camera_backend_id"
    )


def test_ultralytics_results_history_isolated_by_resource_camera_and_native_id() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(tracker_backend="bytetrack"),
        model=_ResultsLikeNativeModel([[7], [7], [9]]),
    )

    uav1_front_first = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.0
    )
    uav1_wide_first = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="wide_rgb", timestamp=1.0
    )
    uav2_front_first = adapter.process_frame(
        _frame(), resource_id="UAV2", camera_id="front_rgb", timestamp=1.0
    )
    uav1_front_second = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.1
    )
    uav1_wide_id_switch = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="wide_rgb", timestamp=1.1
    )

    assert uav1_front_first.tracks[0].mot_history_length == 1
    assert uav1_wide_first.tracks[0].mot_history_length == 1
    assert uav2_front_first.tracks[0].mot_history_length == 1
    assert uav1_front_second.tracks[0].mot_history_length == 2
    assert uav1_wide_id_switch.tracks[0].mot_history_length == 2

    uav1_wide_new_id = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="wide_rgb", timestamp=1.2
    )
    assert uav1_wide_new_id.tracks[0].local_track_id.endswith(":track:9")
    assert uav1_wide_new_id.tracks[0].mot_history_length == 1


def test_ultralytics_results_empty_frames_reset_measured_history_and_bound_id_reuse() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            tracker_backend="bytetrack",
            max_track_age_frames=2,
        ),
        model=_ResultsLikeNativeModel([[7], [7], [], [7], [], [], [], [7]]),
    )

    histories: list[int | None] = []
    for index in range(8):
        result = adapter.process_frame(
            _frame(),
            resource_id="UAV1",
            camera_id="front_rgb",
            timestamp=1.0 + index * 0.1,
        )
        histories.append(result.tracks[0].mot_history_length if result.tracks else None)
        assert result.tracker_backend == "bytetrack"

    assert histories == [1, 2, None, 1, None, None, None, 1]


def test_ultralytics_results_reset_stream_and_episode_clear_native_history() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(tracker_backend="botsort"),
        model=_ResultsLikeNativeModel([[7], [7]]),
    )

    adapter.process_frame(_frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.0)
    second = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.1
    )
    adapter.reset_stream("UAV1", "front_rgb")
    after_stream_reset = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=2.0
    )
    adapter.process_frame(_frame(), resource_id="UAV2", camera_id="front_rgb", timestamp=2.0)
    adapter.reset_episode()
    after_episode_reset = adapter.process_frame(
        _frame(), resource_id="UAV2", camera_id="front_rgb", timestamp=3.0
    )

    assert second.tracks[0].mot_history_length == 2
    assert after_stream_reset.tracks[0].mot_history_length == 1
    assert after_episode_reset.tracks[0].mot_history_length == 1


def test_native_failure_fallback_and_reinitialized_native_do_not_share_history() -> None:
    loaded_models: list[_ResultsLikeNativeModel] = []

    def loader(weights_path: Path) -> _ResultsLikeNativeModel:
        events: list[list[int] | Exception]
        if not loaded_models:
            events = [[7], RuntimeError("native tracker failed after first result")]
        else:
            events = [[7]]
        model = _ResultsLikeNativeModel(events)
        loaded_models.append(model)
        return model

    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="bytetrack",
            allow_iou_fallback=True,
        ),
        ultralytics_loader=loader,
    )

    native_first = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.0
    )
    fallback = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.1
    )
    native_reinitialized = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=1.2
    )

    assert native_first.tracker_backend == "bytetrack"
    assert native_first.tracks[0].mot_history_length == 1
    assert fallback.tracker_backend == "iou_fallback"
    assert fallback.tracks[0].mot_history_length == 1
    assert native_reinitialized.tracker_backend == "bytetrack"
    assert native_reinitialized.tracks[0].mot_history_length == 1
    assert len(loaded_models) == 2


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


def test_generic_actor_object_names_do_not_become_yolo_online_category() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(confidence_threshold=0.1),
        detector=lambda frame: [
            {
                "bbox_xyxy": (4.0, 5.0, 24.0, 25.0),
                "confidence": 0.7,
                "name": "friend",
                "actor_name": "friend",
                "object_name": "friend",
            }
        ],
    )

    result = adapter.process_frame(_frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=2.0)

    assert result.tracks[0].category == "unknown"
    assert "actor_name" not in str(result.metadata)
    assert "object_name" not in str(result.metadata)
    assert "friend" not in str(result.metadata)


def test_detector_class_id_names_mapping_remains_valid_online_category() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(confidence_threshold=0.1),
        detector=lambda frame: [
            {
                "bbox_xyxy": (4.0, 5.0, 24.0, 25.0),
                "confidence": 0.7,
                "class_id": 2,
                "names": {"2": "uav"},
                "name": "TargetActor_1",
            }
        ],
    )

    result = adapter.process_frame(_frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=2.0)

    assert result.tracks[0].category == "uav"
    assert result.metadata["class_id_by_local_track_id"][result.tracks[0].local_track_id] == 2


@pytest.mark.parametrize(
    "raw_category",
    ("UAV", "drone", "INTRUDER", "intruder-uav", "Unmanned Aerial Vehicle"),
)
def test_yolo_category_alias_is_canonicalized_and_raw_label_is_preserved(
    raw_category: str,
) -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(tracker_backend="iou_fallback", confidence_threshold=0.1),
        detector=lambda frame: [
            {
                "xyxy": (4.0, 5.0, 24.0, 25.0),
                "confidence": 0.9,
                "class_name": raw_category,
            }
        ],
    )

    result = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=2.0
    )
    track = result.tracks[0]

    assert track.category == "uav"
    assert track.metadata["object_class"] == "uav"
    assert track.metadata["raw_category"] == raw_category
    assert track.metadata["affiliation_inferred_from_category"] is False
    assert result.metadata["raw_category_by_local_track_id"][track.local_track_id] == raw_category
    assert result.metadata["object_class_by_local_track_id"][track.local_track_id] == "uav"
    assert result.metadata["affiliation_inferred_from_category"] is False


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


def test_botsort_native_path_is_selected_before_iou_fallback() -> None:
    loaded_models: list[_FakeNativeModel] = []

    def loader(weights_path: Path) -> _FakeNativeModel:
        model = _FakeNativeModel()
        loaded_models.append(model)
        return model

    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="botsort",
            confidence_threshold=0.2,
            compute_device="cpu",
        ),
        ultralytics_loader=loader,
    )

    result = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=4.0
    )

    assert len(loaded_models) == 1
    assert loaded_models[0].track_calls == 1
    assert loaded_models[0].predict_calls == 0
    assert "imgsz" not in loaded_models[0].track_kwargs[0]
    assert result.status == "ok"
    assert result.tracker_backend == "botsort"
    assert result.metadata["tracker_selection"] == {
        "requested": "botsort",
        "selected": "botsort",
        "native_preferred": True,
        "native_active": True,
        "fallback_allowed": True,
        "fallback_active": False,
        "status": "ok",
    }
    assert result.metadata["processing_latency_ms"] >= 0.0
    assert result.metadata["observed_compute_device"] == "cpu"


def test_inference_imgsz_is_validated_and_passed_to_native_track() -> None:
    loaded_models: list[_FakeNativeModel] = []

    def loader(weights_path: Path) -> _FakeNativeModel:
        model = _FakeNativeModel()
        loaded_models.append(model)
        return model

    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="bytetrack",
            inference_imgsz=(1080, 1920),
        ),
        ultralytics_loader=loader,
    )

    result = adapter.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=4.1
    )

    assert loaded_models[0].track_kwargs[0]["imgsz"] == (1080, 1920)
    assert result.metadata["inference_imgsz_requested"] == (1080, 1920)


def test_inference_imgsz_is_passed_to_predict_and_none_preserves_default_call() -> None:
    configured_model = _FakeNativeModel()
    configured = YoloMotAdapter(
        YoloMotAdapterConfig(
            tracker_backend="iou_fallback",
            inference_imgsz=1280,
        ),
        model=configured_model,
    )
    configured_result = configured.process_frame(
        _frame(), resource_id="UAV1", camera_id="front_rgb", timestamp=4.2
    )

    default_model = _FakeNativeModel()
    default = YoloMotAdapter(
        YoloMotAdapterConfig(tracker_backend="iou_fallback"),
        model=default_model,
    )
    default_result = default.process_frame(
        _frame(), resource_id="UAV2", camera_id="front_rgb", timestamp=4.2
    )

    assert configured_model.predict_kwargs[0]["imgsz"] == 1280
    assert configured_result.metadata["inference_imgsz_requested"] == 1280
    assert "imgsz" not in default_model.predict_kwargs[0]
    assert default_result.metadata["inference_imgsz_requested"] is None


@pytest.mark.parametrize(
    "invalid",
    (0, -1, True, (), (640,), (640, 0), (640, 480, 3), (640.0, 480), "640"),
)
def test_inference_imgsz_rejects_invalid_values(invalid: object) -> None:
    with pytest.raises(ValueError, match="inference_imgsz"):
        YoloMotAdapterConfig(inference_imgsz=invalid)  # type: ignore[arg-type]


def test_offline_detector_recall_fields_do_not_change_online_local_ids() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            tracker_backend="bytetrack",
            confidence_threshold=0.2,
            offline_evaluation_iou_threshold=0.5,
        ),
        detector=lambda frame: [
            {"xyxy": (5.0, 5.0, 20.0, 20.0), "confidence": 0.9, "class_name": "uav"},
            {"xyxy": (30.0, 30.0, 45.0, 45.0), "confidence": 0.8, "class_name": "uav"},
        ],
    )
    offline_truth = [
        {"xyxy": (5.0, 5.0, 20.0, 20.0), "actor_name": "TargetActor-1"},
        {"xyxy": (30.0, 30.0, 45.0, 45.0), "truth_id": "G2"},
        {"xyxy": (48.0, 48.0, 60.0, 60.0), "object_id": "TargetActor-3"},
    ]

    result = adapter.process_frame(
        _frame(),
        resource_id="UAV1",
        camera_id="front_rgb",
        timestamp=5.0,
        offline_truth_detections=offline_truth,
    )

    evaluation = result.metadata["offline_detector_evaluation"]
    assert evaluation["offline_truth_only"] is True
    assert evaluation["used_by_online_tracker"] is False
    assert evaluation["truth_box_count"] == 3
    assert evaluation["detected_box_count"] == 2
    assert evaluation["matched_truth_box_count"] == 2
    assert evaluation["false_negative_count"] == 1
    assert evaluation["false_positive_count"] == 0
    assert np.isclose(evaluation["detector_recall"], 2.0 / 3.0)
    assert evaluation["identity_fields_emitted"] is False
    assert all("TargetActor" not in track.local_track_id for track in result.tracks)
    assert "TargetActor" not in str(result.metadata)
    assert "G2" not in str(result.metadata)


def test_offline_detector_evaluation_accepts_single_bbox_only_tuple() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(confidence_threshold=0.2),
        detector=lambda frame: [
            {"xyxy": (5.0, 5.0, 20.0, 20.0), "confidence": 0.9, "class_name": "uav"}
        ],
    )

    result = adapter.process_frame(
        _frame(),
        resource_id="UAV1",
        camera_id="front_rgb",
        timestamp=5.1,
        offline_truth_detections=(5.0, 5.0, 20.0, 20.0),
    )

    evaluation = result.metadata["offline_detector_evaluation"]
    assert evaluation["truth_box_count"] == 1
    assert evaluation["matched_truth_box_count"] == 1
    assert evaluation["offline_truth_only"] is True
    assert evaluation["identity_fields_emitted"] is False


def test_offline_detector_evaluation_accepts_multiple_bbox_only_tuples() -> None:
    truth_bboxes = (
        (5.0, 5.0, 20.0, 20.0),
        (30.0, 30.0, 45.0, 45.0),
    )
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(confidence_threshold=0.2),
        detector=lambda frame: [
            {"xyxy": bbox, "confidence": 0.9, "class_name": "uav"}
            for bbox in truth_bboxes
        ],
    )

    result = adapter.process_frame(
        _frame(),
        resource_id="UAV1",
        camera_id="front_rgb",
        timestamp=5.2,
        offline_truth_detections=truth_bboxes,
    )

    evaluation = result.metadata["offline_detector_evaluation"]
    assert evaluation["truth_box_count"] == 2
    assert evaluation["matched_truth_box_count"] == 2
    assert evaluation["detector_recall"] == 1.0
    assert evaluation["used_by_online_tracker"] is False


def test_offline_detector_evaluation_keeps_dict_detection_compatibility() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(confidence_threshold=0.2),
        detector=lambda frame: [
            {"xyxy": (8.0, 9.0, 28.0, 29.0), "confidence": 0.9, "class_name": "uav"}
        ],
    )

    result = adapter.process_frame(
        _frame(),
        resource_id="UAV1",
        camera_id="front_rgb",
        timestamp=5.3,
        offline_truth_detections={"bbox": (8.0, 9.0, 28.0, 29.0)},
    )

    evaluation = result.metadata["offline_detector_evaluation"]
    assert evaluation["truth_box_count"] == 1
    assert evaluation["matched_truth_box_count"] == 1
    assert evaluation["identity_fields_emitted"] is False


def test_offline_detector_evaluation_rejects_malformed_bbox_with_clear_error() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(confidence_threshold=0.2),
        detector=lambda frame: [],
    )

    with pytest.raises(ValueError, match="offline_truth_detections"):
        adapter.process_frame(
            _frame(),
            resource_id="UAV1",
            camera_id="front_rgb",
            timestamp=5.4,
            offline_truth_detections=((5.0, 5.0, 20.0),),
        )


def test_five_camera_crossing_and_occlusion_fixture_keeps_camera_local_namespaces() -> None:
    detections_by_call: list[list[dict]] = []
    base = [
        {
            "xyxy": (5.0 + index * 10.0, 10.0, 13.0 + index * 10.0, 18.0),
            "confidence": 0.9,
            "class_name": "uav",
        }
        for index in range(5)
    ]
    shifted = [
        {
            **item,
            "xyxy": tuple(value + (1.0 if coordinate % 2 == 0 else 0.0) for coordinate, value in enumerate(item["xyxy"])),
        }
        for item in base
    ]
    for _ in range(5):
        detections_by_call.extend((base, shifted))
    # One stream then loses all detections for one frame and recovers before
    # max_track_age_frames expires.
    detections_by_call.extend((base, [], shifted))

    def detector(frame: np.ndarray) -> list[dict]:
        return detections_by_call.pop(0)

    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            tracker_backend="bytetrack",
            confidence_threshold=0.2,
            max_track_age_frames=2,
        ),
        detector=detector,
    )

    all_tracks = []
    for index in range(5):
        resource = f"UAV{index + 1}"
        first = adapter.process_frame(
            _frame(), resource_id=resource, camera_id="front_rgb", timestamp=1.0
        )
        second = adapter.process_frame(
            _frame(), resource_id=resource, camera_id="front_rgb", timestamp=1.1
        )
        assert len(first.tracks) == len(second.tracks) == 5
        assert second.metadata["camera_local_id_continuity_rate"] == 1.0
        assert all(track.mot_history_length == 2 for track in second.tracks)
        all_tracks.extend((resource, track.local_track_id) for track in second.tracks)

    before_occlusion = adapter.process_frame(
        _frame(), resource_id="UAV6", camera_id="front_rgb", timestamp=2.0
    )
    occluded = adapter.process_frame(
        _frame(), resource_id="UAV6", camera_id="front_rgb", timestamp=2.1
    )
    recovered = adapter.process_frame(
        _frame(), resource_id="UAV6", camera_id="front_rgb", timestamp=2.2
    )

    assert len(before_occlusion.tracks) == 5
    assert occluded.tracks == ()
    assert [track.local_track_id for track in recovered.tracks] == [
        track.local_track_id for track in before_occlusion.tracks
    ]
    assert recovered.metadata["camera_local_id_continuity_rate"] == 1.0
    assert len(set(all_tracks)) == 25
    assert all(not hasattr(track, "global_track_id") for track in recovered.tracks)
