"""Manual-initialized local multi-object tracking for offline videos.

Each user-selected ROI owns an independent OpenCV tracker and an immutable
camera-local identifier. This utility deliberately has no concept of AirSim
truth, actor names, or center-owned global track identifiers.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from research_modules.integration_contracts import LocalImageTrackObservation

from .cross_view_registration import adaptive_pixel_covariance_px


SUPPORTED_TRACKER_BACKENDS = ("csrt", "kcf")
SUPPORTED_ASSOCIATION_BACKENDS = ("tracker", "bright_hungarian")
TRACK_STATUS_MEASURED = "measured"
TRACK_STATUS_LOST = "lost"


class ManualVideoTrackingError(RuntimeError):
    """Raised when the manual video tracking workflow cannot continue."""


class TrackerProtocol(Protocol):
    """Minimal OpenCV tracker interface used by this module."""

    def init(self, image: np.ndarray, bounding_box: tuple[float, float, float, float]) -> Any:
        ...

    def update(self, image: np.ndarray) -> tuple[bool, Sequence[float]]:
        ...


TrackerFactory = Callable[[str], TrackerProtocol]


@dataclass(frozen=True)
class RoiXYWH:
    """A validated image ROI in ``x, y, width, height`` form."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("ROI values must be finite")
        if self.x < 0.0 or self.y < 0.0:
            raise ValueError("ROI x and y must be non-negative")
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("ROI width and height must be positive")

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (float(self.x), float(self.y), float(self.width), float(self.height))


@dataclass(frozen=True)
class ManualTrackFrameRecord:
    """One local-track state at one source video frame."""

    frame_index: int
    timestamp_s: float
    local_track_id: str
    bbox: tuple[float, float, float, float] | None
    center: tuple[float, float] | None
    status: str
    tracker_backend: str
    association_backend: str = "tracker"

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame_index must be non-negative")
        if not math.isfinite(self.timestamp_s) or self.timestamp_s < 0.0:
            raise ValueError("timestamp_s must be finite and non-negative")
        if not self.local_track_id:
            raise ValueError("local_track_id is required")
        if self.tracker_backend not in SUPPORTED_TRACKER_BACKENDS:
            raise ValueError("unsupported tracker_backend")
        if self.association_backend not in SUPPORTED_ASSOCIATION_BACKENDS:
            raise ValueError("unsupported association_backend")
        if self.status == TRACK_STATUS_MEASURED:
            if self.bbox is None or self.center is None:
                raise ValueError("measured records require bbox and center")
        elif self.status == TRACK_STATUS_LOST:
            if self.bbox is not None or self.center is not None:
                raise ValueError("lost records must not contain bbox or center")
        else:
            raise ValueError(f"unsupported track status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp_s": self.timestamp_s,
            "local_track_id": self.local_track_id,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "center": list(self.center) if self.center is not None else None,
            "status": self.status,
            "tracker_backend": self.tracker_backend,
            "association_backend": self.association_backend,
        }


@dataclass(frozen=True)
class ManualTrackStatistics:
    """Per-local-ID availability statistics."""

    local_track_id: str
    valid_frame_count: int
    lost_frame_count: int
    first_lost_frame: int | None
    final_status: str


@dataclass(frozen=True)
class ManualTrackingIdentityAudit:
    """Frame-local audit for duplicated measurements and track separation."""

    duplicate_measurement_count: int
    duplicate_measurement_frame_count: int
    duplicate_measurement_iou_threshold: float
    minimum_center_separation_px: float | None
    maximum_bbox_iou: float | None


@dataclass(frozen=True)
class ManualVideoTrackingSummary:
    """Summary and artifact provenance for one video tracking run."""

    schema_version: str
    input_video: str
    output_video: str
    records_csv: str
    tracker_backend: str
    association_backend: str
    source_fps: float
    source_width: int
    source_height: int
    processed_frame_count: int
    local_track_count: int
    interrupted_by_user: bool
    duplicate_measurement_count: int
    duplicate_measurement_frame_count: int
    duplicate_measurement_iou_threshold: float
    minimum_center_separation_px: float | None
    maximum_bbox_iou: float | None
    initial_rois: tuple[tuple[float, float, float, float], ...]
    tracks: tuple[ManualTrackStatistics, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["initial_rois"] = [list(roi) for roi in self.initial_rois]
        payload["tracks"] = [asdict(track) for track in self.tracks]
        return payload


@dataclass(frozen=True)
class ManualVideoTrackingResult:
    """In-memory result returned by :func:`track_manual_rois_in_video`."""

    records: tuple[ManualTrackFrameRecord, ...]
    summary: ManualVideoTrackingSummary
    output_video_path: Path
    records_csv_path: Path
    summary_json_path: Path


def manual_records_to_local_image_observations(
    records: Sequence[ManualTrackFrameRecord],
    *,
    sensor_id: str,
    stream_id: str,
    image_size: tuple[int, int],
    spectral_band: str = "visible",
    local_epoch: int = 0,
    arrival_delay_s: float = 0.0,
    confidence: float = 1.0,
) -> tuple[LocalImageTrackObservation, ...]:
    """Convert offline manual-track records to module-neutral local observations.

    The adapter preserves only camera-local identity. It audits the complete
    input sequence before conversion and rejects the batch if two local tracks
    collapse onto a duplicate same-frame measurement.
    """

    normalized_records = tuple(records)
    identity_audit = audit_tracking_identity(normalized_records)
    if identity_audit.duplicate_measurement_count > 0:
        raise ManualVideoTrackingError(
            "manual record conversion rejected by identity audit: "
            f"{identity_audit.duplicate_measurement_count} duplicate measurement(s) "
            f"across {identity_audit.duplicate_measurement_frame_count} frame(s)"
        )

    normalized_sensor_id = str(sensor_id).strip()
    normalized_stream_id = str(stream_id).strip()
    if not normalized_sensor_id or not normalized_stream_id:
        raise ValueError("sensor_id and stream_id must be non-empty")
    try:
        width, height = (int(value) for value in image_size)
    except (TypeError, ValueError) as exc:
        raise ValueError("image_size must be a (width, height) pair") from exc
    normalized_image_size = (width, height)
    if width <= 0 or height <= 0:
        raise ValueError("image_size must be positive (width, height)")

    normalized_spectral_band = str(spectral_band).strip().lower()
    if normalized_spectral_band not in {"visible", "infrared"}:
        raise ValueError("spectral_band must be 'visible' or 'infrared'")
    normalized_local_epoch = int(local_epoch)
    if normalized_local_epoch < 0:
        raise ValueError("local_epoch must be non-negative")
    normalized_arrival_delay_s = float(arrival_delay_s)
    if not math.isfinite(normalized_arrival_delay_s) or normalized_arrival_delay_s < 0.0:
        raise ValueError("arrival_delay_s must be finite and non-negative")
    normalized_confidence = float(confidence)
    if not math.isfinite(normalized_confidence) or not 0.0 <= normalized_confidence <= 1.0:
        raise ValueError("confidence must be finite and within [0, 1]")

    history_by_local_track: dict[str, tuple[int, int]] = {}
    observations: list[LocalImageTrackObservation] = []
    for record in normalized_records:
        previous_frame, previous_history = history_by_local_track.get(
            record.local_track_id,
            (-2, 0),
        )
        if record.status == TRACK_STATUS_MEASURED:
            measured_history = (
                previous_history + 1
                if previous_history > 0 and record.frame_index == previous_frame + 1
                else 1
            )
        else:
            measured_history = 0
        history_by_local_track[record.local_track_id] = (
            record.frame_index,
            measured_history,
        )

        metadata = {
            "source": "manual_video_tracker",
            "frame_index": record.frame_index,
            "image_size": normalized_image_size,
            "tracker_backend": record.tracker_backend,
            "association_backend": record.association_backend,
            "mot_history_length": measured_history,
            "continuous_measured_history": measured_history,
        }
        arrival_timestamp = record.timestamp_s + normalized_arrival_delay_s
        if record.status == TRACK_STATUS_LOST:
            observations.append(
                LocalImageTrackObservation(
                    sensor_id=normalized_sensor_id,
                    stream_id=normalized_stream_id,
                    local_track_id=record.local_track_id,
                    local_epoch=normalized_local_epoch,
                    spectral_band=normalized_spectral_band,
                    measurement_timestamp=record.timestamp_s,
                    arrival_timestamp=arrival_timestamp,
                    center_px=None,
                    bbox_xyxy=None,
                    pixel_covariance=None,
                    confidence=0.0,
                    track_state=TRACK_STATUS_LOST,
                    metadata=metadata,
                )
            )
            continue

        if record.bbox is None or record.center is None:  # Defensive for external records.
            raise ValueError("measured manual records require bbox and center")
        x, y, bbox_width, bbox_height = record.bbox
        observations.append(
            LocalImageTrackObservation(
                sensor_id=normalized_sensor_id,
                stream_id=normalized_stream_id,
                local_track_id=record.local_track_id,
                local_epoch=normalized_local_epoch,
                spectral_band=normalized_spectral_band,
                measurement_timestamp=record.timestamp_s,
                arrival_timestamp=arrival_timestamp,
                center_px=np.asarray(record.center, dtype=float),
                bbox_xyxy=(
                    float(x),
                    float(y),
                    float(x + bbox_width),
                    float(y + bbox_height),
                ),
                pixel_covariance=adaptive_pixel_covariance_px(
                    float(bbox_width * bbox_height),
                    normalized_image_size,
                ),
                confidence=normalized_confidence,
                track_state=TRACK_STATUS_MEASURED,
                metadata=metadata,
            )
        )
    return tuple(observations)


@dataclass
class _TrackRuntime:
    local_track_id: str
    tracker: TrackerProtocol
    color: tuple[int, int, int]
    last_measured_center: tuple[float, float]
    trail: list[tuple[float, float]]
    measured_history: list[tuple[int, tuple[float, float]]]
    initial_size: tuple[float, float]


def parse_rois(value: str) -> tuple[RoiXYWH, ...]:
    """Parse ``x,y,w,h;x,y,w,h`` into validated ROIs."""

    if not value or not value.strip():
        raise ValueError("at least one ROI is required")
    rois: list[RoiXYWH] = []
    for index, raw_roi in enumerate(value.split(";"), start=1):
        text = raw_roi.strip()
        if not text:
            raise ValueError(f"ROI {index} is empty")
        fields = [field.strip() for field in text.split(",")]
        if len(fields) != 4:
            raise ValueError(f"ROI {index} must contain x,y,w,h")
        try:
            numbers = [float(field) for field in fields]
        except ValueError as exc:
            raise ValueError(f"ROI {index} contains a non-numeric value") from exc
        rois.append(RoiXYWH(*numbers))
    if not rois:
        raise ValueError("at least one ROI is required")
    return tuple(rois)


def validate_rois_for_frame(
    rois: Iterable[RoiXYWH], *, frame_width: int, frame_height: int
) -> tuple[RoiXYWH, ...]:
    """Validate that every ROI is fully contained by the source frame."""

    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame dimensions must be positive")
    normalized = tuple(rois)
    if not normalized:
        raise ValueError("at least one ROI is required")
    for index, roi in enumerate(normalized, start=1):
        if roi.x + roi.width > frame_width or roi.y + roi.height > frame_height:
            raise ValueError(
                f"ROI {index} exceeds frame bounds {frame_width}x{frame_height}: {roi.as_tuple()}"
            )
    return normalized


def select_rois_from_first_frame(
    input_video: Path | str, *, window_name: str = "Select targets in local-ID order"
) -> tuple[RoiXYWH, ...]:
    """Open the first frame and let the user select multiple ROIs in ID order."""

    input_path = Path(input_video)
    capture = cv2.VideoCapture(str(input_path))
    try:
        if not capture.isOpened():
            raise ManualVideoTrackingError(f"cannot open input video: {input_path}")
        ok, first_frame = capture.read()
        if not ok or first_frame is None:
            raise ManualVideoTrackingError(f"cannot read first frame: {input_path}")
    finally:
        capture.release()

    try:
        selected = cv2.selectROIs(
            window_name,
            first_frame,
            showCrosshair=True,
            fromCenter=False,
        )
    except cv2.error as exc:
        raise ManualVideoTrackingError(
            "OpenCV ROI selection failed; use --rois for a headless run"
        ) from exc
    finally:
        try:
            cv2.destroyWindow(window_name)
        except cv2.error:
            pass

    rois = tuple(RoiXYWH(*map(float, roi)) for roi in np.asarray(selected).reshape(-1, 4))
    if not rois:
        raise ManualVideoTrackingError("no ROI was selected")
    height, width = first_frame.shape[:2]
    return validate_rois_for_frame(rois, frame_width=width, frame_height=height)


def create_opencv_tracker(backend: str) -> TrackerProtocol:
    """Create a CSRT or KCF tracker across OpenCV API variants."""

    normalized = backend.lower()
    if normalized not in SUPPORTED_TRACKER_BACKENDS:
        raise ValueError(f"backend must be one of {SUPPORTED_TRACKER_BACKENDS}")
    factory_name = f"Tracker{normalized.upper()}_create"
    factory = getattr(cv2, factory_name, None)
    if factory is None:
        factory = getattr(getattr(cv2, "legacy", None), factory_name, None)
    if factory is None:
        raise ManualVideoTrackingError(
            f"OpenCV tracker backend {normalized} is unavailable in this build"
        )
    return factory()


def track_manual_rois_in_video(
    input_video: Path | str,
    *,
    rois: Sequence[RoiXYWH],
    output_dir: Path | str,
    tracker_backend: str = "csrt",
    association_backend: str = "tracker",
    display: bool = False,
    tail_length: int = 30,
    codec: str = "mp4v",
    tracker_factory: TrackerFactory = create_opencv_tracker,
    blob_contrast_threshold: float = 12.0,
    association_gate_px: float = 20.0,
    duplicate_iou_threshold: float = 0.70,
) -> ManualVideoTrackingResult:
    """Track manually initialized ROIs and write annotated video/CSV/JSON."""

    input_path = Path(input_video)
    output_path = Path(output_dir)
    backend = tracker_backend.lower()
    association = association_backend.lower()
    if backend not in SUPPORTED_TRACKER_BACKENDS:
        raise ValueError(f"tracker_backend must be one of {SUPPORTED_TRACKER_BACKENDS}")
    if association not in SUPPORTED_ASSOCIATION_BACKENDS:
        raise ValueError(f"association_backend must be one of {SUPPORTED_ASSOCIATION_BACKENDS}")
    if tail_length < 1:
        raise ValueError("tail_length must be positive")
    if len(codec) != 4:
        raise ValueError("codec must be a four-character code")
    if not math.isfinite(blob_contrast_threshold) or blob_contrast_threshold <= 0.0:
        raise ValueError("blob_contrast_threshold must be positive")
    if not math.isfinite(association_gate_px) or association_gate_px <= 0.0:
        raise ValueError("association_gate_px must be positive")
    if not 0.0 <= duplicate_iou_threshold <= 1.0:
        raise ValueError("duplicate_iou_threshold must be in [0, 1]")

    capture = cv2.VideoCapture(str(input_path))
    writer: cv2.VideoWriter | None = None
    interrupted = False
    records: list[ManualTrackFrameRecord] = []
    try:
        if not capture.isOpened():
            raise ManualVideoTrackingError(f"cannot open input video: {input_path}")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ManualVideoTrackingError(f"cannot read first frame: {input_path}")

        frame_height, frame_width = frame.shape[:2]
        source_fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(source_fps) or source_fps <= 0.0:
            raise ManualVideoTrackingError("input video has no valid FPS")
        validated_rois = validate_rois_for_frame(
            rois,
            frame_width=frame_width,
            frame_height=frame_height,
        )

        output_path.mkdir(parents=True, exist_ok=True)
        output_video_path = output_path / f"{input_path.stem}_manual_tracks.mp4"
        records_csv_path = output_path / f"{input_path.stem}_manual_tracks.csv"
        summary_json_path = output_path / f"{input_path.stem}_manual_tracks_summary.json"
        if output_video_path.resolve() == input_path.resolve():
            raise ManualVideoTrackingError("output video must not overwrite the input video")

        writer = cv2.VideoWriter(
            str(output_video_path),
            cv2.VideoWriter_fourcc(*codec),
            source_fps,
            (frame_width, frame_height),
        )
        if not writer.isOpened():
            raise ManualVideoTrackingError(f"cannot open output video writer: {output_video_path}")

        runtimes: list[_TrackRuntime] = []
        for index, roi in enumerate(validated_rois, start=1):
            tracker = tracker_factory(backend)
            initialized = tracker.init(frame, _opencv_init_bbox(roi))
            if initialized is False:
                raise ManualVideoTrackingError(f"tracker initialization failed for ROI {index}")
            center = roi.center
            runtimes.append(
                _TrackRuntime(
                    local_track_id=f"local-{index:03d}",
                    tracker=tracker,
                    color=_track_color(index - 1),
                    last_measured_center=center,
                    trail=[center],
                    measured_history=[(0, center)],
                    initial_size=(roi.width, roi.height),
                )
            )

        frame_index = 0
        while True:
            timestamp_s = frame_index / source_fps
            frame_records: list[ManualTrackFrameRecord] = []
            if frame_index == 0:
                measured_rois: list[RoiXYWH | None] = list(validated_rois)
            else:
                tracker_rois: list[RoiXYWH | None] = []
                for runtime in runtimes:
                    update_ok, raw_bbox = runtime.tracker.update(frame)
                    tracker_rois.append(
                        _clip_tracker_bbox(raw_bbox, frame_width=frame_width, frame_height=frame_height)
                        if update_ok
                        else None
                    )

                if association == "bright_hungarian":
                    candidates = _bright_candidates(
                        frame,
                        contrast_threshold=blob_contrast_threshold,
                    )
                    measured_rois = _associate_bright_candidates(
                        runtimes,
                        tracker_rois,
                        candidates,
                        frame_index=frame_index,
                        frame_width=frame_width,
                        frame_height=frame_height,
                        association_gate_px=association_gate_px,
                    )
                else:
                    measured_rois = _reject_duplicate_tracker_rois(
                        tracker_rois,
                        duplicate_iou_threshold=duplicate_iou_threshold,
                    )

            for runtime, measured_roi in zip(runtimes, measured_rois):

                if measured_roi is None:
                    record = ManualTrackFrameRecord(
                        frame_index=frame_index,
                        timestamp_s=timestamp_s,
                        local_track_id=runtime.local_track_id,
                        bbox=None,
                        center=None,
                        status=TRACK_STATUS_LOST,
                        tracker_backend=backend,
                        association_backend=association,
                    )
                else:
                    center = measured_roi.center
                    runtime.last_measured_center = center
                    runtime.trail.append(center)
                    runtime.measured_history.append((frame_index, center))
                    if len(runtime.trail) > tail_length:
                        del runtime.trail[:-tail_length]
                    record = ManualTrackFrameRecord(
                        frame_index=frame_index,
                        timestamp_s=timestamp_s,
                        local_track_id=runtime.local_track_id,
                        bbox=measured_roi.as_tuple(),
                        center=center,
                        status=TRACK_STATUS_MEASURED,
                        tracker_backend=backend,
                        association_backend=association,
                    )
                frame_records.append(record)
                records.append(record)

            annotated = _annotate_frame(frame, runtimes, frame_records)
            writer.write(annotated)
            if display:
                cv2.imshow("D5 manual local multi-object tracking", annotated)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    interrupted = True
                    break

            ok, next_frame = capture.read()
            if not ok or next_frame is None:
                break
            frame = next_frame
            frame_index += 1

        processed_frame_count = max((record.frame_index for record in records), default=-1) + 1
        track_statistics = _summarize_tracks(records, tuple(runtime.local_track_id for runtime in runtimes))
        identity_audit = audit_tracking_identity(
            records,
            duplicate_measurement_iou_threshold=duplicate_iou_threshold,
        )
        summary = ManualVideoTrackingSummary(
            schema_version="d5.manual_local_video_tracking.v1",
            input_video=str(input_path.resolve()),
            output_video=str(output_video_path.resolve()),
            records_csv=str(records_csv_path.resolve()),
            tracker_backend=backend,
            association_backend=association,
            source_fps=source_fps,
            source_width=frame_width,
            source_height=frame_height,
            processed_frame_count=processed_frame_count,
            local_track_count=len(runtimes),
            interrupted_by_user=interrupted,
            duplicate_measurement_count=identity_audit.duplicate_measurement_count,
            duplicate_measurement_frame_count=identity_audit.duplicate_measurement_frame_count,
            duplicate_measurement_iou_threshold=identity_audit.duplicate_measurement_iou_threshold,
            minimum_center_separation_px=identity_audit.minimum_center_separation_px,
            maximum_bbox_iou=identity_audit.maximum_bbox_iou,
            initial_rois=tuple(roi.as_tuple() for roi in validated_rois),
            tracks=track_statistics,
        )
        _write_records_csv(records_csv_path, records)
        summary_json_path.write_text(
            json.dumps(summary.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return ManualVideoTrackingResult(
            records=tuple(records),
            summary=summary,
            output_video_path=output_video_path,
            records_csv_path=records_csv_path,
            summary_json_path=summary_json_path,
        )
    except cv2.error as exc:
        raise ManualVideoTrackingError(f"OpenCV tracking failed: {exc}") from exc
    finally:
        capture.release()
        if writer is not None:
            writer.release()
        if display:
            cv2.destroyAllWindows()


def _clip_tracker_bbox(
    values: Sequence[float], *, frame_width: int, frame_height: int
) -> RoiXYWH | None:
    try:
        x, y, width, height = (float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x, y, width, height)):
        return None
    if width <= 0.0 or height <= 0.0:
        return None
    x1 = min(max(x, 0.0), float(frame_width))
    y1 = min(max(y, 0.0), float(frame_height))
    x2 = min(max(x + width, 0.0), float(frame_width))
    y2 = min(max(y + height, 0.0), float(frame_height))
    if x2 <= x1 or y2 <= y1:
        return None
    return RoiXYWH(x1, y1, x2 - x1, y2 - y1)


def _opencv_init_bbox(roi: RoiXYWH) -> tuple[int, int, int, int]:
    """Convert a validated ROI to the integer Rect expected by OpenCV trackers."""

    return (
        int(round(roi.x)),
        int(round(roi.y)),
        max(1, int(round(roi.width))),
        max(1, int(round(roi.height))),
    )


def _bright_candidates(
    frame: np.ndarray,
    *,
    contrast_threshold: float,
    nms_kernel_size: int = 7,
) -> tuple[tuple[float, float], ...]:
    """Detect compact positive-contrast image peaks without assigning identity."""

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    foreground = gray - cv2.GaussianBlur(gray, (31, 31), 0.0)
    local_maximum = cv2.dilate(
        foreground,
        np.ones((nms_kernel_size, nms_kernel_size), dtype=np.uint8),
    )
    maximum_mask = np.isclose(foreground, local_maximum) & (foreground >= contrast_threshold)
    component_count, labels = cv2.connectedComponents(maximum_mask.astype(np.uint8), 8)
    candidates: list[tuple[float, float, float]] = []
    for label in range(1, component_count):
        ys, xs = np.where(labels == label)
        if xs.size == 0:
            continue
        responses = foreground[ys, xs]
        best_index = int(np.argmax(responses))
        candidates.append((float(responses[best_index]), float(xs[best_index]), float(ys[best_index])))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    return tuple((x, y) for _, x, y in candidates)


def _associate_bright_candidates(
    runtimes: Sequence[_TrackRuntime],
    tracker_rois: Sequence[RoiXYWH | None],
    candidates: Sequence[tuple[float, float]],
    *,
    frame_index: int,
    frame_width: int,
    frame_height: int,
    association_gate_px: float,
) -> list[RoiXYWH | None]:
    """Assign peak candidates one-to-one using constant-velocity predictions."""

    if not runtimes or not candidates:
        return [None] * len(runtimes)
    predictions = [
        _predict_track_center(runtime, tracker_roi, frame_index)
        for runtime, tracker_roi in zip(runtimes, tracker_rois)
    ]
    costs = np.full((len(runtimes), len(candidates)), np.inf, dtype=float)
    for track_index, (prediction_x, prediction_y) in enumerate(predictions):
        tracker_center = tracker_rois[track_index].center if tracker_rois[track_index] else None
        for candidate_index, (candidate_x, candidate_y) in enumerate(candidates):
            prediction_distance = math.hypot(candidate_x - prediction_x, candidate_y - prediction_y)
            tracker_distance = (
                math.hypot(candidate_x - tracker_center[0], candidate_y - tracker_center[1])
                if tracker_center is not None
                else prediction_distance
            )
            costs[track_index, candidate_index] = prediction_distance + 0.05 * tracker_distance

    assignments: list[RoiXYWH | None] = [None] * len(runtimes)
    row_indices, column_indices = linear_sum_assignment(costs)
    for track_index, candidate_index in zip(row_indices.tolist(), column_indices.tolist()):
        candidate_x, candidate_y = candidates[candidate_index]
        prediction_x, prediction_y = predictions[track_index]
        if math.hypot(candidate_x - prediction_x, candidate_y - prediction_y) > association_gate_px:
            continue
        width, height = runtimes[track_index].initial_size
        assignments[track_index] = _roi_centered_on(
            candidate_x,
            candidate_y,
            width,
            height,
            frame_width=frame_width,
            frame_height=frame_height,
        )
    return assignments


def _predict_track_center(
    runtime: _TrackRuntime,
    tracker_roi: RoiXYWH | None,
    frame_index: int,
) -> tuple[float, float]:
    history = runtime.measured_history
    if len(history) >= 2:
        previous_frame, previous_center = history[-2]
        last_frame, last_center = history[-1]
        elapsed_frames = max(1, last_frame - previous_frame)
        velocity_x = (last_center[0] - previous_center[0]) / elapsed_frames
        velocity_y = (last_center[1] - previous_center[1]) / elapsed_frames
        prediction_horizon = max(1, frame_index - last_frame)
        return (
            last_center[0] + velocity_x * prediction_horizon,
            last_center[1] + velocity_y * prediction_horizon,
        )
    if tracker_roi is not None:
        return tracker_roi.center
    return runtime.last_measured_center


def _roi_centered_on(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    *,
    frame_width: int,
    frame_height: int,
) -> RoiXYWH:
    x1 = min(max(center_x - width / 2.0, 0.0), max(0.0, frame_width - width))
    y1 = min(max(center_y - height / 2.0, 0.0), max(0.0, frame_height - height))
    return RoiXYWH(x1, y1, min(width, frame_width), min(height, frame_height))


def _reject_duplicate_tracker_rois(
    rois: Sequence[RoiXYWH | None], *, duplicate_iou_threshold: float
) -> list[RoiXYWH | None]:
    """Fail closed when independent trackers claim the same image measurement."""

    rejected: set[int] = set()
    for left_index, left in enumerate(rois):
        if left is None:
            continue
        for right_index in range(left_index + 1, len(rois)):
            right = rois[right_index]
            if right is None:
                continue
            if _roi_iou(left, right) >= duplicate_iou_threshold:
                rejected.update((left_index, right_index))
    return [None if index in rejected else roi for index, roi in enumerate(rois)]


def _roi_iou(left: RoiXYWH, right: RoiXYWH) -> float:
    x1 = max(left.x, right.x)
    y1 = max(left.y, right.y)
    x2 = min(left.x + left.width, right.x + right.width)
    y2 = min(left.y + left.height, right.y + right.height)
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = left.width * left.height + right.width * right.height - intersection
    return intersection / union if union > 0.0 else 0.0


def audit_tracking_identity(
    records: Sequence[ManualTrackFrameRecord],
    *,
    duplicate_measurement_iou_threshold: float = 0.70,
) -> ManualTrackingIdentityAudit:
    """Audit same-frame measured tracks for collapsed/duplicated measurements."""

    if not 0.0 <= duplicate_measurement_iou_threshold <= 1.0:
        raise ValueError("duplicate_measurement_iou_threshold must be in [0, 1]")
    by_frame: dict[int, list[ManualTrackFrameRecord]] = {}
    for record in records:
        if record.status == TRACK_STATUS_MEASURED:
            by_frame.setdefault(record.frame_index, []).append(record)

    duplicate_count = 0
    duplicate_frames: set[int] = set()
    minimum_separation = math.inf
    maximum_iou = 0.0
    measured_pair_count = 0
    for frame_index, frame_records in by_frame.items():
        for left_index, left in enumerate(frame_records):
            if left.bbox is None or left.center is None:
                continue
            left_roi = RoiXYWH(*left.bbox)
            for right in frame_records[left_index + 1 :]:
                if right.bbox is None or right.center is None:
                    continue
                measured_pair_count += 1
                separation = math.hypot(
                    left.center[0] - right.center[0],
                    left.center[1] - right.center[1],
                )
                iou = _roi_iou(left_roi, RoiXYWH(*right.bbox))
                minimum_separation = min(minimum_separation, separation)
                maximum_iou = max(maximum_iou, iou)
                if separation <= 1e-6 or iou >= duplicate_measurement_iou_threshold:
                    duplicate_count += 1
                    duplicate_frames.add(frame_index)

    return ManualTrackingIdentityAudit(
        duplicate_measurement_count=duplicate_count,
        duplicate_measurement_frame_count=len(duplicate_frames),
        duplicate_measurement_iou_threshold=duplicate_measurement_iou_threshold,
        minimum_center_separation_px=(minimum_separation if measured_pair_count else None),
        maximum_bbox_iou=(maximum_iou if measured_pair_count else None),
    )


def _track_color(index: int) -> tuple[int, int, int]:
    palette = (
        (70, 220, 70),
        (70, 180, 255),
        (255, 120, 70),
        (230, 90, 220),
        (60, 230, 230),
        (200, 200, 80),
        (160, 90, 255),
        (255, 180, 80),
    )
    return palette[index % len(palette)]


def _annotate_frame(
    frame: np.ndarray,
    runtimes: Sequence[_TrackRuntime],
    frame_records: Sequence[ManualTrackFrameRecord],
) -> np.ndarray:
    annotated = frame.copy()
    for runtime, record in zip(runtimes, frame_records):
        points = [(int(round(x)), int(round(y))) for x, y in runtime.trail]
        if len(points) >= 2:
            cv2.polylines(annotated, [np.asarray(points, dtype=np.int32)], False, runtime.color, 1)

        if record.status == TRACK_STATUS_MEASURED and record.bbox is not None:
            x, y, width, height = record.bbox
            x1, y1 = int(round(x)), int(round(y))
            x2, y2 = int(round(x + width)), int(round(y + height))
            cv2.rectangle(annotated, (x1, y1), (x2, y2), runtime.color, 2)
            label_anchor = (x1, max(14, y1 - 5))
            label = runtime.local_track_id
        else:
            cx, cy = runtime.last_measured_center
            label_anchor = (int(round(cx)), max(14, int(round(cy)) - 5))
            label = f"{runtime.local_track_id} LOST"
        cv2.putText(
            annotated,
            label,
            label_anchor,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            runtime.color,
            1,
            cv2.LINE_AA,
        )
    return annotated


def _summarize_tracks(
    records: Sequence[ManualTrackFrameRecord], local_track_ids: Sequence[str]
) -> tuple[ManualTrackStatistics, ...]:
    statistics: list[ManualTrackStatistics] = []
    for local_track_id in local_track_ids:
        track_records = [record for record in records if record.local_track_id == local_track_id]
        lost_frames = [
            record.frame_index for record in track_records if record.status == TRACK_STATUS_LOST
        ]
        statistics.append(
            ManualTrackStatistics(
                local_track_id=local_track_id,
                valid_frame_count=sum(
                    record.status == TRACK_STATUS_MEASURED for record in track_records
                ),
                lost_frame_count=len(lost_frames),
                first_lost_frame=lost_frames[0] if lost_frames else None,
                final_status=track_records[-1].status,
            )
        )
    return tuple(statistics)


def _write_records_csv(path: Path, records: Sequence[ManualTrackFrameRecord]) -> None:
    fieldnames = (
        "frame_index",
        "timestamp_s",
        "local_track_id",
        "bbox",
        "center",
        "bbox_x",
        "bbox_y",
        "bbox_width",
        "bbox_height",
        "center_x",
        "center_y",
        "status",
        "tracker_backend",
        "association_backend",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            bbox = record.bbox
            center = record.center
            writer.writerow(
                {
                    "frame_index": record.frame_index,
                    "timestamp_s": f"{record.timestamp_s:.6f}",
                    "local_track_id": record.local_track_id,
                    "bbox": json.dumps(list(bbox)) if bbox is not None else "",
                    "center": json.dumps(list(center)) if center is not None else "",
                    "bbox_x": "" if bbox is None else f"{bbox[0]:.6f}",
                    "bbox_y": "" if bbox is None else f"{bbox[1]:.6f}",
                    "bbox_width": "" if bbox is None else f"{bbox[2]:.6f}",
                    "bbox_height": "" if bbox is None else f"{bbox[3]:.6f}",
                    "center_x": "" if center is None else f"{center[0]:.6f}",
                    "center_y": "" if center is None else f"{center[1]:.6f}",
                    "status": record.status,
                    "tracker_backend": record.tracker_backend,
                    "association_backend": record.association_backend,
                }
            )
