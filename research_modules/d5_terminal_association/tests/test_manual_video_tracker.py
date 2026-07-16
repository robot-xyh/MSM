from __future__ import annotations

from collections import deque
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from d5_terminal_association.manual_video_tracker import (
    ManualTrackFrameRecord,
    RoiXYWH,
    TRACK_STATUS_LOST,
    TRACK_STATUS_MEASURED,
    audit_tracking_identity,
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
