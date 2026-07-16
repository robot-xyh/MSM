from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
import pytest

from d5_terminal_association.cross_view_registration import adaptive_pixel_covariance_px
from d5_terminal_association.manual_video_tracker import (
    ManualTrackFrameRecord,
    ManualVideoTrackingError,
    RoiXYWH,
    TRACK_STATUS_LOST,
    TRACK_STATUS_MEASURED,
    audit_tracking_identity,
    manual_records_to_local_image_observations,
    parse_rois,
    track_manual_rois_in_video,
    validate_rois_for_frame,
)


class _SequenceTracker:
    def __init__(self, updates: list[tuple[bool, tuple[float, float, float, float]]]) -> None:
        self._updates = deque(updates)
        self.initial_bbox: tuple[float, float, float, float] | None = None

    def init(self, image: np.ndarray, bounding_box: tuple[float, float, float, float]) -> bool:
        self.initial_bbox = bounding_box
        return True

    def update(self, image: np.ndarray) -> tuple[bool, tuple[float, float, float, float]]:
        return self._updates.popleft()


def _write_synthetic_video(path: Path, *, frame_count: int = 4) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5.0,
        (96, 64),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MP4 writer is unavailable")
    try:
        for frame_index in range(frame_count):
            frame = np.zeros((64, 96, 3), dtype=np.uint8)
            cv2.rectangle(frame, (10 + frame_index, 12), (21 + frame_index, 23), (255, 255, 255), -1)
            cv2.rectangle(frame, (50, 30 + frame_index), (61, 41 + frame_index), (180, 180, 180), -1)
            writer.write(frame)
    finally:
        writer.release()


def test_parse_and_validate_rois() -> None:
    rois = parse_rois("10,20,12,14; 30.5,40,16,18")
    assert rois == (RoiXYWH(10.0, 20.0, 12.0, 14.0), RoiXYWH(30.5, 40.0, 16.0, 18.0))
    assert validate_rois_for_frame(rois, frame_width=100, frame_height=80) == rois


@pytest.mark.parametrize(
    "value",
    ("", "1,2,3", "1,2,-3,4", "-1,2,3,4", "1,2,nan,4", "1,2,3,4;"),
)
def test_parse_rois_rejects_invalid_input(value: str) -> None:
    with pytest.raises(ValueError):
        parse_rois(value)


def test_validate_rois_rejects_out_of_frame() -> None:
    with pytest.raises(ValueError, match="exceeds frame bounds"):
        validate_rois_for_frame(
            (RoiXYWH(90.0, 10.0, 20.0, 10.0),),
            frame_width=100,
            frame_height=80,
        )


def test_lost_record_cannot_carry_a_stale_measurement() -> None:
    with pytest.raises(ValueError, match="must not contain"):
        ManualTrackFrameRecord(
            frame_index=2,
            timestamp_s=0.4,
            local_track_id="local-001",
            bbox=(1.0, 2.0, 3.0, 4.0),
            center=(2.5, 4.0),
            status=TRACK_STATUS_LOST,
            tracker_backend="csrt",
        )


def test_headless_synthetic_video_keeps_ids_and_marks_loss(tmp_path: Path) -> None:
    input_video = tmp_path / "synthetic.mp4"
    _write_synthetic_video(input_video)
    tracker_instances = [
            _SequenceTracker(
                [
                    (True, (11.0, 12.0, 12.0, 12.0)),
                    (True, (12.0, 12.0, 12.0, 12.0)),
                    (True, (13.0, 12.0, 12.0, 12.0)),
                ]
            ),
            _SequenceTracker(
                [
                    (True, (50.0, 31.0, 12.0, 12.0)),
                    (False, (0.0, 0.0, 0.0, 0.0)),
                    (True, (50.0, 33.0, 12.0, 12.0)),
                ]
            ),
        ]
    trackers = deque(tracker_instances)

    result = track_manual_rois_in_video(
        input_video,
        rois=(RoiXYWH(10.0, 12.0, 12.0, 12.0), RoiXYWH(50.0, 30.0, 12.0, 12.0)),
        output_dir=tmp_path / "output",
        tracker_factory=lambda backend: trackers.popleft(),
    )

    assert result.summary.processed_frame_count == 4
    assert all(
        isinstance(value, int)
        for tracker in tracker_instances
        for value in (tracker.initial_bbox or ())
    )
    assert result.summary.local_track_count == 2
    assert [track.local_track_id for track in result.summary.tracks] == ["local-001", "local-002"]
    assert [(track.valid_frame_count, track.lost_frame_count) for track in result.summary.tracks] == [
        (4, 0),
        (3, 1),
    ]
    lost = [record for record in result.records if record.status == TRACK_STATUS_LOST]
    assert len(lost) == 1
    assert lost[0].local_track_id == "local-002"
    assert lost[0].bbox is None
    assert lost[0].center is None
    assert any(
        record.local_track_id == "local-002"
        and record.frame_index == 3
        and record.status == TRACK_STATUS_MEASURED
        for record in result.records
    )
    assert result.output_video_path.is_file()
    assert result.records_csv_path.is_file()
    summary = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert summary["schema_version"] == "d5.manual_local_video_tracking.v1"
    assert summary["tracks"][1]["lost_frame_count"] == 1


def test_bright_hungarian_keeps_two_targets_one_to_one(tmp_path: Path) -> None:
    input_video = tmp_path / "bright_targets.mp4"
    _write_synthetic_video(input_video, frame_count=4)
    tracker_instances = [
        _SequenceTracker([(True, (20.0, 20.0, 12.0, 12.0))] * 3),
        _SequenceTracker([(True, (20.0, 20.0, 12.0, 12.0))] * 3),
    ]
    trackers = deque(tracker_instances)

    result = track_manual_rois_in_video(
        input_video,
        rois=(RoiXYWH(10.0, 12.0, 12.0, 12.0), RoiXYWH(50.0, 30.0, 12.0, 12.0)),
        output_dir=tmp_path / "bright_output",
        tracker_factory=lambda backend: trackers.popleft(),
        association_backend="bright_hungarian",
        blob_contrast_threshold=5.0,
        association_gate_px=12.0,
    )

    assert all(track.lost_frame_count == 0 for track in result.summary.tracks)
    assert result.summary.duplicate_measurement_count == 0
    assert result.summary.minimum_center_separation_px is not None
    assert result.summary.minimum_center_separation_px > 20.0
    for frame_index in range(4):
        frame_records = [record for record in result.records if record.frame_index == frame_index]
        assert {record.local_track_id for record in frame_records} == {"local-001", "local-002"}
        assert len({record.center for record in frame_records}) == 2


def test_duplicate_measurement_audit_detects_collapsed_tracks() -> None:
    records = (
        ManualTrackFrameRecord(
            frame_index=0,
            timestamp_s=0.0,
            local_track_id="local-001",
            bbox=(10.0, 10.0, 12.0, 12.0),
            center=(16.0, 16.0),
            status=TRACK_STATUS_MEASURED,
            tracker_backend="csrt",
        ),
        ManualTrackFrameRecord(
            frame_index=0,
            timestamp_s=0.0,
            local_track_id="local-002",
            bbox=(11.0, 10.0, 12.0, 12.0),
            center=(17.0, 16.0),
            status=TRACK_STATUS_MEASURED,
            tracker_backend="csrt",
        ),
        ManualTrackFrameRecord(
            frame_index=0,
            timestamp_s=0.0,
            local_track_id="local-003",
            bbox=None,
            center=None,
            status=TRACK_STATUS_LOST,
            tracker_backend="csrt",
        ),
    )

    audit = audit_tracking_identity(records)
    assert audit.duplicate_measurement_count == 1
    assert audit.duplicate_measurement_frame_count == 1
    assert audit.minimum_center_separation_px == pytest.approx(1.0)
    assert audit.maximum_bbox_iou is not None
    assert audit.maximum_bbox_iou > 0.70


def test_manual_records_convert_covariance_timestamps_infrared_bbox_and_history() -> None:
    records = (
        ManualTrackFrameRecord(
            frame_index=0,
            timestamp_s=1.0,
            local_track_id="local-007",
            bbox=(10.0, 20.0, 12.0, 8.0),
            center=(16.0, 24.0),
            status=TRACK_STATUS_MEASURED,
            tracker_backend="csrt",
            association_backend="bright_hungarian",
        ),
        ManualTrackFrameRecord(
            frame_index=1,
            timestamp_s=1.2,
            local_track_id="local-007",
            bbox=(11.0, 21.0, 12.0, 8.0),
            center=(17.0, 25.0),
            status=TRACK_STATUS_MEASURED,
            tracker_backend="csrt",
            association_backend="bright_hungarian",
        ),
        ManualTrackFrameRecord(
            frame_index=2,
            timestamp_s=1.4,
            local_track_id="local-007",
            bbox=None,
            center=None,
            status=TRACK_STATUS_LOST,
            tracker_backend="csrt",
            association_backend="bright_hungarian",
        ),
        ManualTrackFrameRecord(
            frame_index=3,
            timestamp_s=1.6,
            local_track_id="local-007",
            bbox=(13.0, 22.0, 12.0, 8.0),
            center=(19.0, 26.0),
            status=TRACK_STATUS_MEASURED,
            tracker_backend="csrt",
            association_backend="bright_hungarian",
        ),
    )

    observations = manual_records_to_local_image_observations(
        records,
        sensor_id="ir-camera-01",
        stream_id="manual-offline",
        image_size=(640, 480),
        spectral_band="infrared",
        local_epoch=3,
        arrival_delay_s=0.05,
        confidence=0.8,
    )

    assert len(observations) == 4
    first, second, lost, recovered = observations
    assert first.local_track_id == "local-007"
    assert first.source_track_key == "ir-camera-01/manual-offline/epoch-3/local-007"
    assert first.spectral_band == "infrared"
    assert first.measurement_timestamp == pytest.approx(1.0)
    assert first.arrival_timestamp == pytest.approx(1.05)
    assert first.bbox_xyxy == (10.0, 20.0, 22.0, 28.0)
    assert np.allclose(
        first.pixel_covariance,
        adaptive_pixel_covariance_px(12.0 * 8.0, (640, 480)),
    )
    assert first.confidence == pytest.approx(0.8)
    assert first.metadata["frame_index"] == 0
    assert first.metadata["tracker_backend"] == "csrt"
    assert first.metadata["association_backend"] == "bright_hungarian"
    assert [
        observation.metadata["mot_history_length"] for observation in observations
    ] == [1, 2, 0, 1]
    assert second.metadata["continuous_measured_history"] == 2
    assert lost.track_state == TRACK_STATUS_LOST
    assert lost.center_px is None
    assert lost.bbox_xyxy is None
    assert lost.pixel_covariance is None
    assert lost.confidence == 0.0
    assert recovered.track_state == TRACK_STATUS_MEASURED
    assert "global_track_id" not in str([observation.to_dict() for observation in observations])


def test_documented_95_frame_records_convert_to_470_measured_and_5_lost() -> None:
    lost_frames = {
        "local-001": {57, 58, 89},
        "local-003": {34, 35},
    }
    records: list[ManualTrackFrameRecord] = []
    for frame_index in range(95):
        for track_index in range(5):
            local_track_id = f"local-{track_index + 1:03d}"
            lost = frame_index in lost_frames.get(local_track_id, set())
            x = 20.0 + 100.0 * track_index + 0.1 * frame_index
            y = 30.0 + 3.0 * track_index
            records.append(
                ManualTrackFrameRecord(
                    frame_index=frame_index,
                    timestamp_s=frame_index / 5.0,
                    local_track_id=local_track_id,
                    bbox=None if lost else (x, y, 12.0, 12.0),
                    center=None if lost else (x + 6.0, y + 6.0),
                    status=TRACK_STATUS_LOST if lost else TRACK_STATUS_MEASURED,
                    tracker_backend="csrt",
                    association_backend="bright_hungarian",
                )
            )

    observations = manual_records_to_local_image_observations(
        records,
        sensor_id="visible-camera-01",
        stream_id="b-mp4-manual",
        image_size=(640, 496),
    )

    assert len(observations) == 475
    assert sum(item.track_state == TRACK_STATUS_MEASURED for item in observations) == 470
    assert sum(item.track_state == TRACK_STATUS_LOST for item in observations) == 5
    recovered = next(
        item
        for item in observations
        if item.local_track_id == "local-001" and item.metadata["frame_index"] == 59
    )
    assert recovered.metadata["mot_history_length"] == 1


def test_manual_record_conversion_rejects_duplicate_track_collapse() -> None:
    records = (
        ManualTrackFrameRecord(
            frame_index=4,
            timestamp_s=0.8,
            local_track_id="local-001",
            bbox=(10.0, 10.0, 12.0, 12.0),
            center=(16.0, 16.0),
            status=TRACK_STATUS_MEASURED,
            tracker_backend="csrt",
        ),
        ManualTrackFrameRecord(
            frame_index=4,
            timestamp_s=0.8,
            local_track_id="local-002",
            bbox=(10.0, 10.0, 12.0, 12.0),
            center=(16.0, 16.0),
            status=TRACK_STATUS_MEASURED,
            tracker_backend="csrt",
        ),
    )

    with pytest.raises(ManualVideoTrackingError, match="identity audit.*duplicate"):
        manual_records_to_local_image_observations(
            records,
            sensor_id="visible-camera-01",
            stream_id="collapsed",
            image_size=(640, 480),
        )


def test_root_package_import_does_not_load_manual_video_dependencies() -> None:
    module_root = Path(__file__).resolve().parents[1]
    repository_root = Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(module_root / "src")
    script = """
import builtins
import sys

real_import = builtins.__import__

def without_offline_video_dependencies(name, *args, **kwargs):
    if name == "cv2" or name.startswith("scipy"):
        raise ModuleNotFoundError(name)
    return real_import(name, *args, **kwargs)

builtins.__import__ = without_offline_video_dependencies
import d5_terminal_association

assert "d5_terminal_association.manual_video_tracker" not in sys.modules
assert not hasattr(d5_terminal_association, "ManualTrackFrameRecord")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
