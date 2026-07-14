from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from d5_terminal_association import (
    MOT_ADMISSION_CONFIDENCE_THRESHOLDS,
    MOT_ADMISSION_TARGET_DISTANCES_M,
    NativeMotAdmissionCriteria,
    NativeMotAdmissionMonitor,
    NativeMotScenarioMetadata,
    YoloMotAdapter,
    YoloMotAdapterConfig,
    evaluate_offline_detector_after_online,
)


class _NativeModel:
    names = {0: "uav"}

    def __init__(self, track_ids: tuple[int, ...] = (7,)) -> None:
        self.track_ids = track_ids
        self.calls = 0

    def track(self, frame: np.ndarray, **kwargs: object) -> list[dict]:
        track_id = self.track_ids[min(self.calls, len(self.track_ids) - 1)]
        self.calls += 1
        return [
            {
                "xyxy": (10.0, 10.0, 30.0, 30.0),
                "confidence": 0.95,
                "class_id": 0,
                "track_id": track_id,
                "mot_history_length": self.calls,
            }
        ]

    def predict(self, frame: np.ndarray, **kwargs: object) -> list[dict]:
        return []


def _frame() -> np.ndarray:
    return np.zeros((64, 64, 3), dtype=np.uint8)


def _truth() -> list[dict]:
    return [
        {
            "xyxy": (10.0, 10.0, 30.0, 30.0),
            "truth_id": "offline-target-1",
        }
    ]


@pytest.mark.parametrize("backend", ("bytetrack", "botsort"))
def test_native_backend_meets_admission_with_post_online_truth_scoring(backend: str) -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend=backend,
            confidence_threshold=0.2,
        ),
        ultralytics_loader=lambda path: _NativeModel(),
    )
    monitor = NativeMotAdmissionMonitor(
        NativeMotAdmissionCriteria(minimum_frame_count=5)
    )
    scenario = NativeMotScenarioMetadata(
        confidence_threshold=0.2,
        target_distance_m=30.0,
        warmup_frame_count=2,
        scenario_id="native-admission",
    )

    for index, latency_ms in enumerate((900.0, 800.0, 10.0, 20.0, 30.0)):
        result = adapter.process_frame(
            _frame(),
            resource_id="INT-01",
            camera_id="front_rgb",
            timestamp=index * 0.1,
            target_distance_m=30.0,
        )
        result = replace(
            result,
            metadata={**result.metadata, "processing_latency_ms": latency_ms},
        )
        assert "offline_detector_evaluation" not in result.metadata
        online_metadata = deepcopy(result.metadata)
        monitor.observe(
            result,
            scenario=scenario,
            offline_truth_detections=_truth(),
        )
        assert result.metadata == online_metadata

    summary = monitor.summary("INT-01", "front_rgb")
    assert summary.native_active_frame_rate == 1.0
    assert summary.fallback_frame_count == 0
    assert summary.accepted_detection_count == 5
    assert summary.warmup_excluded_latency_sample_count == 3
    assert np.isclose(summary.warmup_excluded_p95_latency_ms, 29.0)
    assert summary.local_continuity == 1.0
    assert summary.terminal_local_id_switch_count == 0
    assert summary.offline_detector_true_positive_count == 5
    assert summary.offline_detector_false_positive_count == 0
    assert summary.offline_detector_false_negative_count == 0
    assert summary.offline_detector_precision == 1.0
    assert summary.offline_detector_recall == 1.0
    assert summary.post_online_truth_frame_count == 5
    assert summary.legacy_metadata_truth_frame_count == 0
    assert summary.native_mot_admitted is True
    assert summary.rejection_reasons == ()
    assert summary.to_dict()["iou_fallback_counts_as_native"] is False
    assert summary.to_dict()["tracker_backend"] == backend
    assert summary.to_dict()["detector_precision"] == 1.0
    assert summary.to_dict()["detector_recall"] == 1.0
    assert summary.to_dict()["local_track_continuity"] == 1.0
    assert summary.to_dict()["online_truth_use_count"] == 0
    assert "offline-target-1" not in str(summary.to_dict())


def test_standard_confidence_and_distance_grid_is_present_in_frame_metadata() -> None:
    for confidence in MOT_ADMISSION_CONFIDENCE_THRESHOLDS:
        for distance_m in MOT_ADMISSION_TARGET_DISTANCES_M:
            adapter = YoloMotAdapter(
                YoloMotAdapterConfig(
                    weights_path=Path(__file__),
                    tracker_backend="bytetrack",
                    confidence_threshold=confidence,
                ),
                ultralytics_loader=lambda path: _NativeModel(),
            )
            result = adapter.process_frame(
                _frame(),
                resource_id="INT-01",
                camera_id="front_rgb",
                timestamp=1.0,
                target_distance_m=distance_m,
            )
            assert result.metadata["mot_admission_scenario"] == {
                "confidence_threshold": confidence,
                "target_distance_m": distance_m,
                "standard_confidence_grid": True,
                "standard_distance_grid": True,
            }


def test_screening_and_confirmation_frame_contracts_are_explicit() -> None:
    screening = NativeMotScenarioMetadata(
        confidence_threshold=0.1,
        target_distance_m=20.0,
        evaluation_stage="single_camera_screening",
    )
    confirmation = NativeMotScenarioMetadata(
        confidence_threshold=0.2,
        target_distance_m=30.0,
        evaluation_stage="two_camera_confirmation",
    )

    assert screening.expected_frame_count == 100
    assert confirmation.expected_frame_count == 200
    assert screening.to_dict()["truth_scoring_policy"] == (
        "evaluation_only_after_online_tracking"
    )


def test_iou_fallback_is_explicitly_rejected_as_native_mot() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            tracker_backend="bytetrack",
            confidence_threshold=0.1,
        ),
        detector=lambda frame: [
            {
                "xyxy": (10.0, 10.0, 30.0, 30.0),
                "confidence": 0.95,
                "class_name": "uav",
            }
        ],
    )
    monitor = NativeMotAdmissionMonitor(
        NativeMotAdmissionCriteria(minimum_frame_count=2)
    )
    scenario = NativeMotScenarioMetadata(
        confidence_threshold=0.1,
        target_distance_m=20.0,
        warmup_frame_count=0,
    )
    for index in range(2):
        result = adapter.process_frame(
            _frame(),
            resource_id="INT-01",
            camera_id="front_rgb",
            timestamp=float(index),
        )
        monitor.observe(
            result,
            scenario=scenario,
            offline_truth_detections=_truth(),
        )

    summary = monitor.summary("INT-01", "front_rgb")
    assert summary.native_active_frame_rate == 0.0
    assert summary.fallback_frame_count == 2
    assert summary.native_mot_admitted is False
    assert "iou_fallback_frame_present" in summary.rejection_reasons
    assert "native_active_frame_rate_below_threshold" in summary.rejection_reasons


def test_terminal_local_id_switch_is_scored_offline_and_monitor_resets_per_stream() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="botsort",
            confidence_threshold=0.3,
        ),
        ultralytics_loader=lambda path: _NativeModel((7, 7, 8)),
    )
    monitor = NativeMotAdmissionMonitor(
        NativeMotAdmissionCriteria(
            minimum_frame_count=3,
            maximum_terminal_local_id_switch_count=0,
        )
    )
    scenario = NativeMotScenarioMetadata(
        confidence_threshold=0.3,
        target_distance_m=50.0,
        warmup_frame_count=0,
    )
    for index in range(3):
        result = adapter.process_frame(
            _frame(),
            resource_id="INT-01",
            camera_id="front_rgb",
            timestamp=float(index),
        )
        monitor.observe(
            result,
            scenario=scenario,
            offline_truth_detections=_truth(),
        )

    summary = monitor.summary("INT-01", "front_rgb")
    assert summary.terminal_local_id_switch_count == 1
    assert summary.local_continuity == 0.5
    assert "terminal_local_id_switch_count_exceeded" in summary.rejection_reasons

    monitor.reset_stream("INT-01", "front_rgb")
    with pytest.raises(KeyError):
        monitor.summary("INT-01", "front_rgb")

    other_result = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="botsort",
            confidence_threshold=0.3,
        ),
        ultralytics_loader=lambda path: _NativeModel(),
    ).process_frame(
        _frame(),
        resource_id="INT-02",
        camera_id="front_rgb",
        timestamp=0.0,
    )
    monitor.observe(other_result, scenario=scenario, offline_truth_detections=_truth())
    assert len(monitor.summaries()) == 1
    monitor.reset_all_streams()
    assert monitor.summaries() == ()


def test_public_post_online_detector_evaluator_does_not_mutate_result() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="bytetrack",
        ),
        ultralytics_loader=lambda path: _NativeModel(),
    )
    result = adapter.process_frame(
        _frame(),
        resource_id="INT-01",
        camera_id="front_rgb",
        timestamp=0.0,
    )
    metadata_before = deepcopy(result.metadata)
    local_ids_before = tuple(track.local_track_id for track in result.tracks)
    offline_truth = [
        *_truth(),
        {"xyxy": (40.0, 40.0, 50.0, 50.0), "truth_id": "offline-target-2"},
    ]

    evaluation = evaluate_offline_detector_after_online(result, offline_truth)

    assert evaluation.true_positive_count == 1
    assert evaluation.false_positive_count == 0
    assert evaluation.false_negative_count == 1
    assert evaluation.detector_precision == 1.0
    assert evaluation.detector_recall == 0.5
    assert evaluation.to_dict()["evaluation_phase"] == "after_online_result"
    assert result.metadata == metadata_before
    assert tuple(track.local_track_id for track in result.tracks) == local_ids_before
    assert "offline-target" not in str(result.metadata)


@pytest.mark.parametrize(
    ("resource_id", "shape", "expected_size"),
    (
        ("INT-01", (1080, 1920, 3), (1920, 1080)),
        ("RECON-01", (2160, 3840, 3), (3840, 2160)),
    ),
)
def test_dual_route_reports_online_yolo_offline_airsim_and_tracker_separately(
    resource_id: str,
    shape: tuple[int, int, int],
    expected_size: tuple[int, int],
) -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="bytetrack",
        ),
        ultralytics_loader=lambda path: _NativeModel(),
    )
    result = adapter.process_frame(
        np.zeros(shape, dtype=np.uint8),
        resource_id=resource_id,
        camera_id="front_rgb",
        timestamp=1.0,
    )
    online_metadata = deepcopy(result.metadata)
    online_local_ids = tuple(track.local_track_id for track in result.tracks)
    airsim_detections = [
        {
            "box2D": {
                "min": {"x": 10.0, "y": 10.0},
                "max": {"x": 30.0, "y": 30.0},
            },
            "object_id": "TargetActor_001",
        }
    ]
    monitor = NativeMotAdmissionMonitor(
        NativeMotAdmissionCriteria(minimum_frame_count=1)
    )

    monitor.observe(
        result,
        scenario=NativeMotScenarioMetadata(0.25, 20.0, warmup_frame_count=0),
        offline_truth_detections=airsim_detections,
    )

    summary = monitor.summary(resource_id, "front_rgb")
    payload = summary.to_dict()
    assert result.metadata == online_metadata
    assert tuple(track.local_track_id for track in result.tracks) == online_local_ids
    assert result.metadata["image_size"] == expected_size
    assert result.tracks[0].image_size == expected_size
    assert "TargetActor_001" not in str(result.metadata)
    assert "TargetActor_001" not in str(result.tracks)
    assert payload["online_yolo_detection_count"] == 1
    assert payload["online_local_track_count"] == 1
    assert payload["offline_reference_box_count"] == 1
    assert payload["offline_reference_matched_count"] == 1
    assert payload["offline_reference_missed_count"] == 0
    assert payload["offline_reference_unmatched_online_count"] == 0
    assert payload["native_active_frame_count"] == 1
    assert payload["fallback_frame_count"] == 0
    assert payload["post_online_truth_frame_count"] == 1
    assert payload["truth_identity_used_online"] is False


def test_legacy_metadata_scoring_remains_compatible_when_no_post_online_truth_is_given() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="bytetrack",
        ),
        ultralytics_loader=lambda path: _NativeModel(),
    )
    result = adapter.process_frame(
        _frame(),
        resource_id="INT-01",
        camera_id="front_rgb",
        timestamp=0.0,
        offline_truth_detections=_truth(),
    )
    monitor = NativeMotAdmissionMonitor(
        NativeMotAdmissionCriteria(minimum_frame_count=1)
    )

    monitor.observe(
        result,
        scenario=NativeMotScenarioMetadata(0.25, 30.0, warmup_frame_count=0),
    )

    summary = monitor.summary("INT-01", "front_rgb")
    assert summary.offline_detector_true_positive_count == 1
    assert summary.offline_truth_frame_count == 1
    assert summary.post_online_truth_frame_count == 0
    assert summary.legacy_metadata_truth_frame_count == 1
    assert summary.native_mot_admitted is False
    assert "post_online_truth_frame_coverage_incomplete" in summary.rejection_reasons
    assert "legacy_truth_metadata_not_admissible" in summary.rejection_reasons


def test_post_online_truth_takes_precedence_over_legacy_metadata_without_double_counting() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="bytetrack",
        ),
        ultralytics_loader=lambda path: _NativeModel(),
    )
    result = adapter.process_frame(
        _frame(),
        resource_id="INT-01",
        camera_id="front_rgb",
        timestamp=0.0,
        offline_truth_detections=_truth(),
    )
    monitor = NativeMotAdmissionMonitor(
        NativeMotAdmissionCriteria(minimum_frame_count=1)
    )
    post_online_truth = [
        *_truth(),
        {"xyxy": (40.0, 40.0, 50.0, 50.0), "truth_id": "offline-target-2"},
    ]

    monitor.observe(
        result,
        scenario=NativeMotScenarioMetadata(0.25, 30.0, warmup_frame_count=0),
        offline_truth_detections=post_online_truth,
    )

    summary = monitor.summary("INT-01", "front_rgb")
    assert summary.offline_detector_true_positive_count == 1
    assert summary.offline_detector_false_negative_count == 1
    assert summary.offline_truth_frame_count == 1
    assert summary.post_online_truth_frame_count == 1
    assert summary.legacy_metadata_truth_frame_count == 0


def test_stream_scenario_change_requires_explicit_reset() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(
            weights_path=Path(__file__),
            tracker_backend="bytetrack",
        ),
        ultralytics_loader=lambda path: _NativeModel(),
    )
    result = adapter.process_frame(
        _frame(), resource_id="INT-01", camera_id="front_rgb", timestamp=0.0
    )
    monitor = NativeMotAdmissionMonitor()
    monitor.observe(
        result,
        scenario=NativeMotScenarioMetadata(0.2, 20.0),
    )
    with pytest.raises(ValueError, match="without reset_stream"):
        monitor.observe(
            result,
            scenario=NativeMotScenarioMetadata(0.2, 30.0),
        )
