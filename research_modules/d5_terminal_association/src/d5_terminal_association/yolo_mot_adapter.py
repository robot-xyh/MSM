"""YOLOv8 detector and MOT adapter for D5 terminal association.

The adapter normalizes image-frame detector/tracker output into
`LocalVisualTrack` objects. It does not create, rewrite, or infer
center-owned `global_track_id` values. AirSim truth fields and offline truth
labels are ignored by the online conversion path.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from .models import CameraGeometryEvidence, LocalVisualTrack
from .object_taxonomy import canonical_object_class


DEFAULT_YOLOV8_WEIGHTS_PATH = Path(
    "/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt"
)

TRUTH_OR_GLOBAL_FIELD_NAMES = {
    "actor_id",
    "actor_name",
    "assigned_global_track_id",
    "global_track_id",
    "name",
    "object_id",
    "object_name",
    "offline_truth_global_id",
    "true_global_track_id",
    "truth_global_track_id",
    "truth_id",
}

TRACKER_BACKENDS = {"bytetrack", "botsort", "iou_fallback"}


class YoloMotUnavailableError(RuntimeError):
    """Raised when the real YOLO/MOT runtime cannot be used."""


@dataclass(frozen=True)
class YoloMotAdapterConfig:
    """Configuration for YOLOv8 + MOT frame conversion.

    `tracker_backend` may request `bytetrack` or `botsort` for ultralytics'
    native tracker path. When that path is unavailable, the adapter can fall
    back to deterministic IoU tracking while preserving the requested backend
    in result metadata.
    """

    weights_path: Path | str = DEFAULT_YOLOV8_WEIGHTS_PATH
    tracker_backend: str = "bytetrack"
    confidence_threshold: float = 0.25
    iou_match_threshold: float = 0.3
    max_track_age_frames: int = 2
    source_name: str = "yolov8"
    default_category: str = "unknown"
    use_native_ultralytics_tracker: bool = True
    allow_iou_fallback: bool = True
    compute_device: str = "auto"
    cpu_budget_ms: float | None = None
    gpu_budget_ms: float | None = None
    offline_evaluation_iou_threshold: float = 0.5
    inference_imgsz: int | Sequence[int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "weights_path", Path(self.weights_path))
        backend = str(self.tracker_backend).lower()
        if backend not in TRACKER_BACKENDS:
            raise ValueError(f"tracker_backend must be one of {sorted(TRACKER_BACKENDS)}")
        object.__setattr__(self, "tracker_backend", backend)
        object.__setattr__(self, "confidence_threshold", float(self.confidence_threshold))
        object.__setattr__(self, "iou_match_threshold", float(self.iou_match_threshold))
        object.__setattr__(self, "max_track_age_frames", int(self.max_track_age_frames))
        if self.confidence_threshold < 0.0 or self.confidence_threshold > 1.0:
            raise ValueError("confidence_threshold must be in [0, 1]")
        if self.iou_match_threshold < 0.0 or self.iou_match_threshold > 1.0:
            raise ValueError("iou_match_threshold must be in [0, 1]")
        if self.max_track_age_frames < 0:
            raise ValueError("max_track_age_frames must be non-negative")
        object.__setattr__(self, "compute_device", str(self.compute_device or "auto"))
        object.__setattr__(self, "cpu_budget_ms", _optional_nonnegative_float(self.cpu_budget_ms))
        object.__setattr__(self, "gpu_budget_ms", _optional_nonnegative_float(self.gpu_budget_ms))
        object.__setattr__(
            self,
            "offline_evaluation_iou_threshold",
            float(self.offline_evaluation_iou_threshold),
        )
        if not 0.0 <= self.offline_evaluation_iou_threshold <= 1.0:
            raise ValueError("offline_evaluation_iou_threshold must be in [0, 1]")
        object.__setattr__(self, "inference_imgsz", _normalize_inference_imgsz(self.inference_imgsz))


@dataclass(frozen=True)
class YoloMotFrameResult:
    """Result from one image frame converted to D5 local tracks."""

    tracks: tuple[LocalVisualTrack, ...]
    status: str
    detector_backend: str
    tracker_backend: str
    resource_id: str
    camera_id: str
    frame_id: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tracks", tuple(self.tracks))
        object.__setattr__(self, "timestamp", float(self.timestamp))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class _DetectorDetection:
    bbox: tuple[float, float, float, float]
    confidence: float
    category: str
    class_id: int | None = None
    source_track_id: str | int | None = None
    mot_history_length: int = 1
    raw_category: str | None = None

    def __post_init__(self) -> None:
        raw_category = str(self.category if self.raw_category is None else self.raw_category)
        object.__setattr__(self, "raw_category", raw_category)
        object.__setattr__(self, "category", canonical_object_class(raw_category))


@dataclass
class _TrackState:
    track_id: int
    bbox: tuple[float, float, float, float]
    category: str
    confidence: float
    class_id: int | None = None
    hits: int = 1
    missed_frames: int = 0
    raw_category: str = "unknown"


@dataclass(frozen=True)
class _TrackedDetection:
    bbox: tuple[float, float, float, float]
    confidence: float
    category: str
    class_id: int | None
    track_id: str | int
    mot_history_length: int
    raw_category: str = "unknown"


class IouFallbackTracker:
    """Deterministic IoU tracker for tests and dependency-light runtime.

    The tracker is intentionally small: it performs greedy one-to-one IoU
    matching against active tracks, ages unmatched tracks, and allocates local
    integer track IDs. It is not a replacement for ByteTrack/BoT-SORT quality;
    it exists so D5 can produce stable local track IDs without GPU or optional
    tracker dependencies.
    """

    def __init__(self, *, iou_threshold: float = 0.3, max_age_frames: int = 2) -> None:
        if iou_threshold < 0.0 or iou_threshold > 1.0:
            raise ValueError("iou_threshold must be in [0, 1]")
        if max_age_frames < 0:
            raise ValueError("max_age_frames must be non-negative")
        self.iou_threshold = float(iou_threshold)
        self.max_age_frames = int(max_age_frames)
        self._next_track_id = 1
        self._tracks: dict[int, _TrackState] = {}

    def update(self, detections: Iterable[_DetectorDetection]) -> list[_TrackedDetection]:
        detection_list = list(detections)
        matched_track_ids: set[int] = set()
        matched_detection_indices: set[int] = set()
        assignments: dict[int, int] = {}
        pairs: list[tuple[float, int, int]] = []

        for detection_index, detection in enumerate(detection_list):
            for track_id, track in self._tracks.items():
                if track_id in matched_track_ids:
                    continue
                score = _bbox_iou(track.bbox, detection.bbox)
                if score >= self.iou_threshold:
                    pairs.append((score, track_id, detection_index))

        for _, track_id, detection_index in sorted(pairs, key=lambda item: (-item[0], item[1], item[2])):
            if track_id in matched_track_ids or detection_index in matched_detection_indices:
                continue
            matched_track_ids.add(track_id)
            matched_detection_indices.add(detection_index)
            assignments[detection_index] = track_id

        output: list[_TrackedDetection] = []
        for detection_index, detection in enumerate(detection_list):
            track_id = assignments.get(detection_index)
            if track_id is None:
                track_id = self._next_track_id
                self._next_track_id += 1
                self._tracks[track_id] = _TrackState(
                    track_id=track_id,
                    bbox=detection.bbox,
                    category=detection.category,
                    confidence=detection.confidence,
                    class_id=detection.class_id,
                    hits=1,
                    missed_frames=0,
                    raw_category=str(detection.raw_category),
                )
            else:
                state = self._tracks[track_id]
                state.bbox = detection.bbox
                state.category = detection.category
                state.confidence = detection.confidence
                state.class_id = detection.class_id
                state.raw_category = str(detection.raw_category)
                state.hits += 1
                state.missed_frames = 0

            state = self._tracks[track_id]
            output.append(
                _TrackedDetection(
                    bbox=detection.bbox,
                    confidence=detection.confidence,
                    category=detection.category,
                    class_id=detection.class_id,
                    track_id=track_id,
                    mot_history_length=max(state.hits, detection.mot_history_length),
                    raw_category=str(detection.raw_category),
                )
            )

        for track_id, track in list(self._tracks.items()):
            if track_id in matched_track_ids or any(track_id == item.track_id for item in output):
                continue
            track.missed_frames += 1
            if track.missed_frames > self.max_age_frames:
                del self._tracks[track_id]

        return output


class YoloMotAdapter:
    """Convert YOLOv8 + ByteTrack/BoT-SORT output into `LocalVisualTrack`.

    Tests and deterministic offline runs can inject `detector`, a callable that
    returns YOLO-like detections. Without an injected detector, the adapter
    lazily loads ultralytics from `config.weights_path`.
    """

    def __init__(
        self,
        config: YoloMotAdapterConfig | None = None,
        *,
        detector: Callable[[Any], Any] | None = None,
        model: Any | None = None,
        ultralytics_loader: Callable[[Path], Any] | None = None,
        fallback_tracker: IouFallbackTracker | None = None,
    ) -> None:
        self.config = config or YoloMotAdapterConfig()
        if detector is not None and model is not None:
            raise ValueError("provide detector or model, not both")
        self._detector = detector
        self._model = model
        self._model_was_injected = model is not None
        self._ultralytics_loader = ultralytics_loader or _load_ultralytics_model
        self._fallback_tracker_template = fallback_tracker
        self._fallback_trackers: dict[tuple[str, str], IouFallbackTracker] = {}
        self._native_models: dict[tuple[str, str], Any] = {}

    def process_frame(
        self,
        frame: Any,
        *,
        resource_id: str,
        camera_id: str,
        timestamp: float,
        frame_id: str | None = None,
        arrival_timestamp: float | None = None,
        exposure_timestamp: float | None = None,
        camera_geometry: CameraGeometryEvidence | None = None,
        target_distance_m: float | None = None,
        offline_truth_detections: Any | None = None,
        raise_on_unavailable: bool = False,
    ) -> YoloMotFrameResult:
        """Run detector/tracker for one frame and return D5 local tracks.

        ``offline_truth_detections`` is evaluated only after the online tracks
        have been produced.  It contributes aggregate recall/precision counts
        to metadata and never affects detector filtering, tracker IDs, or a
        center-owned global track binding.
        """

        stream_key = _mot_stream_key(resource_id, camera_id)
        resolved_frame_id = frame_id or f"{resource_id}/{camera_id}"
        effective_arrival_timestamp = (
            float(arrival_timestamp) if arrival_timestamp is not None else float(timestamp)
        )
        normalized_target_distance_m = _optional_positive_float(target_distance_m)
        metadata: dict[str, Any] = {
            "requested_tracker_backend": self.config.tracker_backend,
            "stream_key": {
                "resource_id": stream_key[0],
                "camera_id": stream_key[1],
            },
            "stream_key_text": _mot_stream_key_text(stream_key),
            "tracker_state_scope": "per_resource_camera_stream",
            "tracker_state_isolated": True,
            "weights_path": str(self.config.weights_path),
            "compute_device": self.config.compute_device,
            "cpu_budget_ms": self.config.cpu_budget_ms,
            "gpu_budget_ms": self.config.gpu_budget_ms,
            "runtime_budget": {
                "cpu_ms": self.config.cpu_budget_ms,
                "gpu_ms": self.config.gpu_budget_ms,
            },
            "native_tracker_preferred": self._native_tracker_requested(),
            "iou_fallback_allowed": self.config.allow_iou_fallback,
            "confidence_threshold": self.config.confidence_threshold,
            "offline_evaluation_iou_threshold": (
                self.config.offline_evaluation_iou_threshold
            ),
            "inference_imgsz_requested": _inference_imgsz_metadata_value(
                self.config.inference_imgsz
            ),
            "mot_admission_scenario": {
                "confidence_threshold": self.config.confidence_threshold,
                "target_distance_m": normalized_target_distance_m,
                "standard_confidence_grid": any(
                    np.isclose(self.config.confidence_threshold, value)
                    for value in (0.1, 0.2, 0.3)
                ),
                "standard_distance_grid": (
                    normalized_target_distance_m is not None
                    and any(
                        np.isclose(normalized_target_distance_m, value)
                        for value in (20.0, 30.0, 50.0)
                    )
                ),
            },
            "_processing_started_perf_counter_s": perf_counter(),
            "_offline_truth_bboxes": _offline_truth_bboxes(offline_truth_detections),
            "measurement_timestamp": float(timestamp),
            "arrival_timestamp": effective_arrival_timestamp,
            "exposure_timestamp": (
                float(exposure_timestamp) if exposure_timestamp is not None else float(timestamp)
            ),
            "camera_geometry": (
                camera_geometry.to_metadata()
                if camera_geometry is not None
                else {
                    "geometry_valid": False,
                    "geometry_source": "unavailable",
                    "geometry_unavailable_reasons": ["camera_geometry_not_provided"],
                }
            ),
        }

        try:
            if self._detector is not None:
                detections = self._filter_detections(
                    _normalize_detections(
                        self._detector(frame),
                        default_category=self.config.default_category,
                    )
                )
                tracked = tuple(self._fallback_tracker_for_stream(stream_key).update(detections))
                metadata["_detected_bboxes"] = tuple(item.bbox for item in detections)
                tracks = _to_local_visual_tracks(
                    tracked,
                    camera_id=camera_id,
                    timestamp=timestamp,
                    source_name=self.config.source_name,
                    tracker_backend="iou_fallback",
                    arrival_timestamp=effective_arrival_timestamp,
                    exposure_timestamp=(
                        float(exposure_timestamp) if exposure_timestamp is not None else float(timestamp)
                    ),
                    image_size=_frame_size(frame),
                    camera_geometry=camera_geometry,
                )
                metadata.update(
                    {
                        "raw_detection_count": len(detections),
                        "accepted_detection_count": len(tracks),
                        "tracker_backend": "iou_fallback",
                        "tracker_state_backend": "iou_fallback",
                        "tracker_instance_scope": "per_stream",
                        "native_model_scope": "not_used",
                        "detector_model_scope": "adapter_shared_injected_detector",
                        "detector_backend": "injected_detector",
                        "observed_compute_device": "injected_detector_unspecified",
                    }
                )
                metadata.update(
                    _tracked_frame_metadata(
                        tracked,
                        tracks,
                        detector_backend="injected_detector",
                        tracker_backend="iou_fallback",
                        frame=frame,
                    )
                )
                return self._result(
                    tracks,
                    status="ok",
                    detector_backend="injected_detector",
                    tracker_backend="iou_fallback",
                    resource_id=resource_id,
                    camera_id=camera_id,
                    frame_id=resolved_frame_id,
                    timestamp=timestamp,
                    metadata=metadata,
                )

            native_model = None
            if self._native_tracker_requested():
                try:
                    native_model = self._native_model_for_stream(stream_key)
                    detections = self._run_native_tracker(native_model, frame)
                    metadata["_detected_bboxes"] = tuple(item.bbox for item in detections)
                    tracked = tuple(
                        _TrackedDetection(
                            bbox=item.bbox,
                            confidence=item.confidence,
                            category=item.category,
                            class_id=item.class_id,
                            track_id=item.source_track_id,
                            mot_history_length=item.mot_history_length,
                            raw_category=str(item.raw_category),
                        )
                        for item in detections
                        if item.source_track_id is not None
                    )
                    tracks = _to_local_visual_tracks(
                        tracked,
                        camera_id=camera_id,
                        timestamp=timestamp,
                        source_name=self.config.source_name,
                        tracker_backend=self.config.tracker_backend,
                        arrival_timestamp=effective_arrival_timestamp,
                        exposure_timestamp=(
                            float(exposure_timestamp) if exposure_timestamp is not None else float(timestamp)
                        ),
                        image_size=_frame_size(frame),
                        camera_geometry=camera_geometry,
                    )
                    if tracks:
                        metadata.update(
                            {
                                "raw_detection_count": len(detections),
                                "accepted_detection_count": len(tracks),
                                "tracker_backend": self.config.tracker_backend,
                                "tracker_state_backend": self.config.tracker_backend,
                                "tracker_instance_scope": "per_stream",
                                "native_model_scope": "per_stream",
                                "detector_model_scope": "per_stream_native_model",
                                "detector_backend": "ultralytics_yolov8",
                                "observed_compute_device": _model_compute_device(
                                    native_model,
                                    self.config.compute_device,
                                ),
                            }
                        )
                        metadata.update(
                            _tracked_frame_metadata(
                                tracked,
                                tracks,
                                detector_backend="ultralytics_yolov8",
                                tracker_backend=self.config.tracker_backend,
                                frame=frame,
                            )
                        )
                        return self._result(
                            tracks,
                            status="ok",
                            detector_backend="ultralytics_yolov8",
                            tracker_backend=self.config.tracker_backend,
                            resource_id=resource_id,
                            camera_id=camera_id,
                            frame_id=resolved_frame_id,
                            timestamp=timestamp,
                            metadata=metadata,
                        )
                    raise YoloMotUnavailableError("native tracker returned no track IDs")
                except Exception as exc:
                    if not self.config.allow_iou_fallback:
                        raise
                    metadata["tracker_fallback_reason"] = str(exc)

            if not self.config.allow_iou_fallback and self.config.tracker_backend != "iou_fallback":
                raise YoloMotUnavailableError("native tracker unavailable and IoU fallback is disabled")
            model = native_model if native_model is not None else self._load_model()
            detections = self._filter_detections(
                _normalize_detections(
                    self._run_detector(model, frame),
                    default_category=self.config.default_category,
                )
            )
            metadata["_detected_bboxes"] = tuple(item.bbox for item in detections)
            tracked = tuple(self._fallback_tracker_for_stream(stream_key).update(detections))
            tracks = _to_local_visual_tracks(
                tracked,
                camera_id=camera_id,
                timestamp=timestamp,
                source_name=self.config.source_name,
                tracker_backend="iou_fallback",
                arrival_timestamp=effective_arrival_timestamp,
                exposure_timestamp=(
                    float(exposure_timestamp) if exposure_timestamp is not None else float(timestamp)
                ),
                image_size=_frame_size(frame),
                camera_geometry=camera_geometry,
            )
            metadata.update(
                {
                    "raw_detection_count": len(detections),
                    "accepted_detection_count": len(tracks),
                    "tracker_backend": "iou_fallback",
                    "tracker_state_backend": "iou_fallback",
                    "tracker_instance_scope": "per_stream",
                    "native_model_scope": "per_stream" if native_model is not None else "not_used",
                    "detector_model_scope": (
                        "per_stream_native_model"
                        if native_model is not None
                        else "adapter_shared_detector_model"
                    ),
                    "detector_backend": "ultralytics_yolov8",
                    "observed_compute_device": _model_compute_device(
                        model,
                        self.config.compute_device,
                    ),
                }
            )
            metadata.update(
                _tracked_frame_metadata(
                    tracked,
                    tracks,
                    detector_backend="ultralytics_yolov8",
                    tracker_backend="iou_fallback",
                    frame=frame,
                )
            )
            return self._result(
                tracks,
                status="ok",
                detector_backend="ultralytics_yolov8",
                tracker_backend="iou_fallback",
                resource_id=resource_id,
                camera_id=camera_id,
                frame_id=resolved_frame_id,
                timestamp=timestamp,
                metadata=metadata,
            )
        except YoloMotUnavailableError as exc:
            if raise_on_unavailable:
                raise
            metadata.update(
                {
                    "unavailable_reason": str(exc),
                    "tracker_backend": "iou_fallback"
                    if self.config.allow_iou_fallback
                    else self.config.tracker_backend,
                    "tracker_state_backend": "unavailable",
                    "tracker_instance_scope": "per_stream",
                    "detector_backend": "unavailable",
                    "observed_compute_device": "unavailable",
                }
            )
            return self._result(
                (),
                status="unavailable",
                detector_backend="unavailable",
                tracker_backend=metadata["tracker_backend"],
                resource_id=resource_id,
                camera_id=camera_id,
                frame_id=resolved_frame_id,
                timestamp=timestamp,
                metadata=metadata,
            )

    def ensure_available(self) -> None:
        """Raise a clear error if the real YOLO runtime cannot be loaded."""

        self._load_model()

    def reset_stream(self, resource_id: str, camera_id: str) -> None:
        """Release MOT state for one resource/camera stream."""

        stream_key = _mot_stream_key(resource_id, camera_id)
        self._fallback_trackers.pop(stream_key, None)
        self._native_models.pop(stream_key, None)

    def reset_all_streams(self) -> None:
        """Release all per-stream MOT state at an episode boundary."""

        self._fallback_trackers.clear()
        self._native_models.clear()

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        self._model = self._load_model_instance()
        return self._model

    def _load_model_instance(self) -> Any:
        if not self.config.weights_path.exists():
            raise YoloMotUnavailableError(f"YOLOv8 weights not found: {self.config.weights_path}")
        try:
            return self._ultralytics_loader(self.config.weights_path)
        except ModuleNotFoundError as exc:
            raise YoloMotUnavailableError(
                "ultralytics is not available; install ultralytics or inject a detector"
            ) from exc
        except ImportError as exc:
            raise YoloMotUnavailableError(
                "ultralytics could not be imported; install ultralytics or inject a detector"
            ) from exc
        except Exception as exc:
            raise YoloMotUnavailableError(f"failed to load YOLOv8 model: {exc}") from exc

    def _fallback_tracker_for_stream(
        self,
        stream_key: tuple[str, str],
    ) -> IouFallbackTracker:
        tracker = self._fallback_trackers.get(stream_key)
        if tracker is not None:
            return tracker
        if self._fallback_tracker_template is None:
            tracker = IouFallbackTracker(
                iou_threshold=self.config.iou_match_threshold,
                max_age_frames=self.config.max_track_age_frames,
            )
        else:
            try:
                tracker = deepcopy(self._fallback_tracker_template)
            except Exception as exc:
                raise YoloMotUnavailableError(
                    "fallback tracker must be cloneable for per-stream state isolation"
                ) from exc
        self._fallback_trackers[stream_key] = tracker
        return tracker

    def _native_model_for_stream(self, stream_key: tuple[str, str]) -> Any:
        model = self._native_models.get(stream_key)
        if model is not None:
            return model
        if self._model_was_injected:
            try:
                model = deepcopy(self._model)
            except Exception as exc:
                raise YoloMotUnavailableError(
                    "injected native model must be cloneable for per-stream tracker isolation"
                ) from exc
        else:
            model = self._load_model_instance()
        self._native_models[stream_key] = model
        return model

    def _native_tracker_requested(self) -> bool:
        return (
            self.config.tracker_backend in {"bytetrack", "botsort"}
            and self.config.use_native_ultralytics_tracker
        )

    def _run_native_tracker(self, model: Any, frame: Any) -> list[_DetectorDetection]:
        tracker_file = "bytetrack.yaml" if self.config.tracker_backend == "bytetrack" else "botsort.yaml"
        raw = model.track(
            frame,
            persist=True,
            tracker=tracker_file,
            conf=self.config.confidence_threshold,
            verbose=False,
            **_ultralytics_imgsz_kwargs(self.config.inference_imgsz),
            **_ultralytics_device_kwargs(self.config.compute_device),
        )
        detections = self._filter_detections(
            _normalize_detections(
                raw,
                names=getattr(model, "names", None),
                default_category=self.config.default_category,
            )
        )
        if not any(item.source_track_id is not None for item in detections):
            raise YoloMotUnavailableError(f"{self.config.tracker_backend} produced no local track IDs")
        return detections

    def _run_detector(self, model: Any, frame: Any) -> Any:
        if hasattr(model, "predict"):
            return model.predict(
                frame,
                conf=self.config.confidence_threshold,
                verbose=False,
                **_ultralytics_imgsz_kwargs(self.config.inference_imgsz),
                **_ultralytics_device_kwargs(self.config.compute_device),
            )
        if callable(model):
            return model(frame)
        raise YoloMotUnavailableError("YOLOv8 model is not callable and has no predict() method")

    def _filter_detections(self, detections: Iterable[_DetectorDetection]) -> list[_DetectorDetection]:
        return [
            detection
            for detection in detections
            if detection.confidence >= self.config.confidence_threshold
        ]

    def _result(
        self,
        tracks: Iterable[LocalVisualTrack],
        *,
        status: str,
        detector_backend: str,
        tracker_backend: str,
        resource_id: str,
        camera_id: str,
        frame_id: str,
        timestamp: float,
        metadata: Mapping[str, Any],
    ) -> YoloMotFrameResult:
        completed_metadata = dict(metadata)
        started = completed_metadata.pop("_processing_started_perf_counter_s", None)
        processing_latency_ms = (
            max(0.0, (perf_counter() - float(started)) * 1000.0)
            if started is not None
            else None
        )
        offline_truth_bboxes = completed_metadata.pop("_offline_truth_bboxes", None)
        detected_bboxes = tuple(completed_metadata.pop("_detected_bboxes", ()))
        completed_metadata["detector_bboxes_xyxy"] = [
            [float(value) for value in bbox]
            for bbox in detected_bboxes
        ]
        completed_metadata["detector_bbox_count"] = len(detected_bboxes)
        completed_metadata["detector_bboxes_online_safe"] = True
        completed_metadata.update(
            _runtime_performance_metadata(
                processing_latency_ms,
                cpu_budget_ms=self.config.cpu_budget_ms,
                gpu_budget_ms=self.config.gpu_budget_ms,
            )
        )
        completed_metadata["tracker_selection"] = {
            "requested": self.config.tracker_backend,
            "selected": tracker_backend if status == "ok" else None,
            "native_preferred": self._native_tracker_requested(),
            "native_active": status == "ok" and tracker_backend in {"bytetrack", "botsort"},
            "fallback_allowed": self.config.allow_iou_fallback,
            "fallback_active": status == "ok" and tracker_backend == "iou_fallback",
            "status": status,
        }
        if offline_truth_bboxes is not None:
            completed_metadata["offline_detector_evaluation"] = _offline_detector_evaluation(
                detected_bboxes,
                offline_truth_bboxes,
                iou_threshold=self.config.offline_evaluation_iou_threshold,
            )
        return YoloMotFrameResult(
            tracks=tuple(tracks),
            status=status,
            detector_backend=detector_backend,
            tracker_backend=tracker_backend,
            resource_id=resource_id,
            camera_id=camera_id,
            frame_id=frame_id,
            timestamp=timestamp,
            metadata=completed_metadata,
        )


def _mot_stream_key(resource_id: str, camera_id: str) -> tuple[str, str]:
    resource = str(resource_id)
    camera = str(camera_id)
    if not resource or not camera:
        raise ValueError("resource_id and camera_id must be non-empty MOT stream identifiers")
    return (resource, camera)


def _mot_stream_key_text(stream_key: tuple[str, str]) -> str:
    return f"{stream_key[0]}/{stream_key[1]}"


def _ultralytics_device_kwargs(compute_device: str) -> dict[str, str]:
    device = str(compute_device or "auto").strip()
    if device.lower() in {"", "auto"}:
        return {}
    return {"device": device}


def _ultralytics_imgsz_kwargs(
    inference_imgsz: int | tuple[int, int] | None,
) -> dict[str, int | tuple[int, int]]:
    if inference_imgsz is None:
        return {}
    return {"imgsz": inference_imgsz}


def _model_compute_device(model: Any, requested: str) -> str:
    device = getattr(model, "device", None)
    if device is None:
        nested_model = getattr(model, "model", None)
        device = getattr(nested_model, "device", None)
    return str(device if device is not None else requested or "unknown")


def _load_ultralytics_model(weights_path: Path) -> Any:
    from ultralytics import YOLO

    return YOLO(str(weights_path))


def _to_local_visual_tracks(
    tracked: Iterable[_TrackedDetection],
    *,
    camera_id: str,
    timestamp: float,
    source_name: str,
    tracker_backend: str,
    arrival_timestamp: float,
    exposure_timestamp: float,
    image_size: tuple[int, int] | None,
    camera_geometry: CameraGeometryEvidence | None,
) -> tuple[LocalVisualTrack, ...]:
    tracks: list[LocalVisualTrack] = []
    for item in tracked:
        x1, y1, x2, y2 = item.bbox
        clip_sides = _bbox_edge_clip_sides(item.bbox, image_size)
        tracks.append(
            LocalVisualTrack(
                local_track_id=f"{camera_id}/{source_name}_{tracker_backend}:track:{item.track_id}",
                center_px=np.array([(x1 + x2) * 0.5, (y1 + y2) * 0.5], dtype=float),
                bbox=item.bbox,
                bearing_rate=np.zeros(2, dtype=float),
                category=item.category,
                quality=item.confidence,
                mot_history_length=item.mot_history_length,
                timestamp=timestamp,
                arrival_timestamp=arrival_timestamp,
                exposure_timestamp=exposure_timestamp,
                detection_source=f"{source_name}:{tracker_backend}",
                track_transition_state=(
                    "continued" if item.mot_history_length > 1 else "initialized"
                ),
                bbox_edge_clipped=bool(clip_sides),
                bbox_edge_clip_sides=clip_sides,
                image_size=image_size,
                camera_geometry=camera_geometry,
                metadata={
                    "image_size": image_size,
                    "object_class": item.category,
                    "raw_category": item.raw_category,
                    "affiliation_inferred_from_category": False,
                },
            )
        )
    return tuple(tracks)


def _tracked_frame_metadata(
    tracked: Sequence[_TrackedDetection],
    tracks: Sequence[LocalVisualTrack],
    *,
    detector_backend: str,
    tracker_backend: str,
    frame: Any,
) -> dict[str, Any]:
    frame_size = _frame_size(frame)
    image_diag = None
    if frame_size is not None:
        width, height = frame_size
        image_diag = float(np.hypot(width, height))

    confidence_by_id: dict[str, float] = {}
    class_id_by_id: dict[str, int | None] = {}
    bbox_area_by_id: dict[str, float] = {}
    bbox_scale_by_id: dict[str, float | None] = {}
    tracker_backend_by_id: dict[str, str] = {}
    detector_backend_by_id: dict[str, str] = {}
    mot_history_by_id: dict[str, int] = {}
    transition_by_id: dict[str, str] = {}
    bbox_clipped_by_id: dict[str, bool] = {}
    bbox_clip_sides_by_id: dict[str, list[str]] = {}
    object_class_by_id: dict[str, str] = {}
    raw_category_by_id: dict[str, str] = {}

    for item, track in zip(tracked, tracks):
        area = _bbox_area(item.bbox)
        confidence_by_id[track.local_track_id] = float(item.confidence)
        class_id_by_id[track.local_track_id] = item.class_id
        bbox_area_by_id[track.local_track_id] = area
        bbox_scale_by_id[track.local_track_id] = (
            float(np.sqrt(area) / image_diag) if image_diag and area > 0.0 else None
        )
        tracker_backend_by_id[track.local_track_id] = tracker_backend
        detector_backend_by_id[track.local_track_id] = detector_backend
        mot_history_by_id[track.local_track_id] = int(track.mot_history_length)
        transition_by_id[track.local_track_id] = track.track_transition_state
        bbox_clipped_by_id[track.local_track_id] = track.bbox_edge_clipped
        bbox_clip_sides_by_id[track.local_track_id] = list(track.bbox_edge_clip_sides)
        object_class_by_id[track.local_track_id] = item.category
        raw_category_by_id[track.local_track_id] = item.raw_category

    continuity_count = sum(1 for history in mot_history_by_id.values() if history > 1)
    continuity_rate = (
        continuity_count / len(mot_history_by_id)
        if mot_history_by_id
        else None
    )

    return {
        "image_size": frame_size,
        "confidence_by_local_track_id": confidence_by_id,
        "class_id_by_local_track_id": class_id_by_id,
        "bbox_area_px_by_local_track_id": bbox_area_by_id,
        "bbox_scale_by_local_track_id": bbox_scale_by_id,
        "bbox_scale_definition": "sqrt_bbox_area_px_over_image_diagonal_px",
        "tracker_backend_by_local_track_id": tracker_backend_by_id,
        "detector_backend_by_local_track_id": detector_backend_by_id,
        "mot_history_length_by_local_track_id": mot_history_by_id,
        "track_transition_state_by_local_track_id": transition_by_id,
        "bbox_edge_clipped_by_local_track_id": bbox_clipped_by_id,
        "bbox_edge_clip_sides_by_local_track_id": bbox_clip_sides_by_id,
        "object_class_by_local_track_id": object_class_by_id,
        "raw_category_by_local_track_id": raw_category_by_id,
        "affiliation_inferred_from_category": False,
        "camera_local_id_count": len(mot_history_by_id),
        "camera_local_id_continuity_count": continuity_count,
        "camera_local_id_continuity_rate": continuity_rate,
        "camera_local_id_continuity_definition": "mot_history_length_greater_than_one_in_current_stream",
        "tracker_id_scope": "LocalVisualTrack.local_track_id_only",
        "local_track_id_scope": "resource/camera/frame/local_tracker_namespace",
    }


def _frame_size(frame: Any) -> tuple[int, int] | None:
    shape = getattr(frame, "shape", None)
    if shape is None or len(shape) < 2:
        return None
    height = int(shape[0])
    width = int(shape[1])
    if width <= 0 or height <= 0:
        return None
    return (width, height)


def _bbox_edge_clip_sides(
    bbox: tuple[float, float, float, float],
    image_size: tuple[int, int] | None,
) -> tuple[str, ...]:
    if image_size is None:
        return ()
    width, height = image_size
    x1, y1, x2, y2 = bbox
    sides: list[str] = []
    if x1 <= 0.0:
        sides.append("left")
    if y1 <= 0.0:
        sides.append("top")
    if x2 >= float(width - 1):
        sides.append("right")
    if y2 >= float(height - 1):
        sides.append("bottom")
    return tuple(sides)


def _normalize_detections(
    raw: Any,
    *,
    names: Mapping[int, str] | Sequence[str] | None = None,
    default_category: str = "unknown",
) -> list[_DetectorDetection]:
    if raw is None:
        return []
    if hasattr(raw, "boxes"):
        return _detections_from_result_object(raw, names=names, default_category=default_category)
    if isinstance(raw, Mapping):
        if "boxes" in raw and not any(key in raw for key in ("bbox", "bbox_xyxy", "xyxy", "box", "box2d", "box2D")):
            return _normalize_detections(
                raw["boxes"],
                names=raw.get("names", names),
                default_category=default_category,
            )
        return [_detection_from_record(raw, names=names, default_category=default_category)]
    if isinstance(raw, np.ndarray):
        return _detections_from_array(raw, names=names, default_category=default_category)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        detections: list[_DetectorDetection] = []
        for item in raw:
            detections.extend(_normalize_detections(item, names=names, default_category=default_category))
        return detections
    return [_detection_from_record(raw, names=names, default_category=default_category)]


def _detections_from_result_object(
    result: Any,
    *,
    names: Mapping[int, str] | Sequence[str] | None,
    default_category: str,
) -> list[_DetectorDetection]:
    boxes = getattr(result, "boxes")
    result_names = getattr(result, "names", None) or names
    xyxy_values = _to_numpy(getattr(boxes, "xyxy", None))
    if xyxy_values is None:
        return []
    xyxy_array = np.asarray(xyxy_values, dtype=float).reshape(-1, 4)
    conf_array = _optional_column(getattr(boxes, "conf", None), len(xyxy_array), default=1.0)
    cls_array = _optional_column(getattr(boxes, "cls", None), len(xyxy_array), default=np.nan)
    id_values = _to_numpy(getattr(boxes, "id", None))
    id_array = None if id_values is None else np.asarray(id_values).reshape(-1)
    detections: list[_DetectorDetection] = []
    for index, bbox_array in enumerate(xyxy_array):
        class_value = cls_array[index]
        class_id = None if np.isnan(class_value) else int(class_value)
        source_track_id = None
        if id_array is not None and index < len(id_array):
            source_track_id = _clean_track_id(id_array[index])
        detections.append(
            _DetectorDetection(
                bbox=_bbox_from_values(bbox_array),
                confidence=float(conf_array[index]),
                category=_category_from_class_id(class_id, result_names, default_category=default_category),
                class_id=class_id,
                source_track_id=source_track_id,
                mot_history_length=1,
            )
        )
    return detections


def _detections_from_array(
    values: np.ndarray,
    *,
    names: Mapping[int, str] | Sequence[str] | None,
    default_category: str,
) -> list[_DetectorDetection]:
    array = np.asarray(values, dtype=float)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.shape[1] < 4:
        raise ValueError("detection array must contain at least xyxy columns")
    detections: list[_DetectorDetection] = []
    for row in array:
        confidence = float(row[4]) if row.shape[0] >= 5 else 1.0
        class_id = int(row[5]) if row.shape[0] >= 6 and np.isfinite(row[5]) else None
        track_id = _clean_track_id(row[6]) if row.shape[0] >= 7 and np.isfinite(row[6]) else None
        detections.append(
            _DetectorDetection(
                bbox=_bbox_from_values(row[:4]),
                confidence=confidence,
                category=_category_from_class_id(class_id, names, default_category=default_category),
                class_id=class_id,
                source_track_id=track_id,
            )
        )
    return detections


def _detection_from_record(
    detection: Any,
    *,
    names: Mapping[int, str] | Sequence[str] | None,
    default_category: str,
) -> _DetectorDetection:
    bbox = _extract_bbox(detection)
    class_id = _class_id_from_record(detection)
    category_value = _get_any(detection, "category", "label", "class_name")
    record_names = _get_any(detection, "names", "class_names")
    category = str(
        category_value
        if category_value is not None
        else _category_from_class_id(
            class_id,
            record_names if record_names is not None else names,
            default_category=default_category,
        )
    )
    confidence_value = _get_any(detection, "confidence", "conf", "score", "quality")
    confidence = float(1.0 if confidence_value is None else confidence_value)
    source_track_id = _clean_track_id(
        _get_any(
            detection,
            "local_track_id",
            "track_id",
            "tracker_id",
            "byte_track_id",
            "bytetrack_id",
            "bot_sort_id",
            "botsort_id",
            "id",
        )
    )
    if _track_id_aliases_truth_or_global(detection, source_track_id):
        source_track_id = None
    history_value = _get_any(detection, "mot_history_length", "track_age", "age")
    history = int(1 if history_value is None else history_value)
    return _DetectorDetection(
        bbox=bbox,
        confidence=confidence,
        category=category,
        class_id=class_id,
        source_track_id=source_track_id,
        mot_history_length=history,
    )


def _extract_bbox(detection: Any) -> tuple[float, float, float, float]:
    bbox = _get_any(detection, "bbox", "bbox_xyxy", "xyxy", "box", "box2d", "box2D")
    if bbox is None:
        raise ValueError("detection must contain bbox, bbox_xyxy, xyxy, or box2D")
    if isinstance(bbox, Mapping):
        if "min" in bbox and "max" in bbox:
            x1, y1 = _xy(bbox["min"])
            x2, y2 = _xy(bbox["max"])
        else:
            x1 = _float_from_any(bbox, "x_min", "xmin", "left", "x1")
            y1 = _float_from_any(bbox, "y_min", "ymin", "top", "y1")
            x2 = _float_from_any(bbox, "x_max", "xmax", "right", "x2")
            y2 = _float_from_any(bbox, "y_max", "ymax", "bottom", "y2")
        return _bbox_from_values((x1, y1, x2, y2))
    if isinstance(bbox, np.ndarray):
        return _bbox_from_values(bbox.reshape(-1))
    if isinstance(bbox, Sequence) and len(bbox) == 4 and not isinstance(bbox, (str, bytes, bytearray)):
        return _bbox_from_values(bbox)
    min_point = _get_any(bbox, "min")
    max_point = _get_any(bbox, "max")
    if min_point is None or max_point is None:
        raise ValueError("box2D must contain min and max points")
    x1, y1 = _xy(min_point)
    x2, y2 = _xy(max_point)
    return _bbox_from_values((x1, y1, x2, y2))


def _bbox_from_values(values: Sequence[Any] | np.ndarray) -> tuple[float, float, float, float]:
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (4,):
        raise ValueError(f"bbox must have shape (4,), got {array.shape}")
    x1, y1, x2, y2 = (float(value) for value in array)
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox must be (x_min, y_min, x_max, y_max)")
    return (x1, y1, x2, y2)


def _bbox_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    if union <= 0.0:
        return 0.0
    return intersection / union


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _offline_truth_bboxes(raw: Any | None) -> tuple[tuple[float, float, float, float], ...] | None:
    if raw is None:
        return None
    try:
        return tuple(_collect_offline_truth_bboxes(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "offline_truth_detections must be an xyxy bbox, a sequence of xyxy "
            "bboxes, or detection records containing bbox/xyxy/box2D"
        ) from exc


def _collect_offline_truth_bboxes(raw: Any) -> list[tuple[float, float, float, float]]:
    """Extract evaluation-only boxes without interpreting identity fields."""

    if isinstance(raw, np.ndarray):
        return [
            item.bbox
            for item in _detections_from_array(
                raw,
                names=None,
                default_category="unknown",
            )
        ]
    if isinstance(raw, Mapping):
        bbox_keys = ("bbox", "bbox_xyxy", "xyxy", "box", "box2d", "box2D")
        if "boxes" in raw and not any(key in raw for key in bbox_keys):
            return _collect_offline_truth_bboxes(raw["boxes"])
        return [_extract_bbox(raw)]
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        if _is_xyxy_bbox_sequence(raw):
            return [_bbox_from_values(raw)]
        boxes: list[tuple[float, float, float, float]] = []
        for item in raw:
            boxes.extend(_collect_offline_truth_bboxes(item))
        return boxes
    if hasattr(raw, "boxes"):
        return [
            item.bbox
            for item in _detections_from_result_object(
                raw,
                names=None,
                default_category="unknown",
            )
        ]
    return [_extract_bbox(raw)]


def _is_xyxy_bbox_sequence(raw: Sequence[Any]) -> bool:
    if len(raw) != 4:
        return False
    try:
        return np.asarray(raw, dtype=float).shape == (4,)
    except (TypeError, ValueError):
        return False


def _offline_detector_evaluation(
    detected_bboxes: Sequence[tuple[float, float, float, float]],
    truth_bboxes: Sequence[tuple[float, float, float, float]],
    *,
    iou_threshold: float,
) -> dict[str, Any]:
    pairs = sorted(
        (
            (_bbox_iou(detected, truth), detected_index, truth_index)
            for detected_index, detected in enumerate(detected_bboxes)
            for truth_index, truth in enumerate(truth_bboxes)
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    matched_detections: set[int] = set()
    matched_truth: set[int] = set()
    matched_ious: list[float] = []
    for iou, detected_index, truth_index in pairs:
        if iou < iou_threshold:
            break
        if detected_index in matched_detections or truth_index in matched_truth:
            continue
        matched_detections.add(detected_index)
        matched_truth.add(truth_index)
        matched_ious.append(float(iou))

    truth_count = len(truth_bboxes)
    detected_count = len(detected_bboxes)
    matched_count = len(matched_truth)
    return {
        "offline_truth_only": True,
        "used_by_online_tracker": False,
        "iou_threshold": float(iou_threshold),
        "truth_box_count": truth_count,
        "detected_box_count": detected_count,
        "matched_truth_box_count": matched_count,
        "false_negative_count": max(0, truth_count - matched_count),
        "false_positive_count": max(0, detected_count - matched_count),
        "detector_recall": matched_count / truth_count if truth_count else None,
        "detector_precision": matched_count / detected_count if detected_count else None,
        "matched_iou_mean": float(np.mean(matched_ious)) if matched_ious else None,
        "identity_fields_emitted": False,
    }


def _runtime_performance_metadata(
    processing_latency_ms: float | None,
    *,
    cpu_budget_ms: float | None,
    gpu_budget_ms: float | None,
) -> dict[str, Any]:
    return {
        "processing_latency_ms": processing_latency_ms,
        "processing_latency_scope": "detector_plus_tracker_adapter_wall_time",
        "cpu_budget_exceeded": (
            processing_latency_ms > cpu_budget_ms
            if processing_latency_ms is not None and cpu_budget_ms is not None
            else None
        ),
        "gpu_budget_exceeded": (
            processing_latency_ms > gpu_budget_ms
            if processing_latency_ms is not None and gpu_budget_ms is not None
            else None
        ),
        "budget_comparison_scope": "wall_time_vs_declared_budget_not_profiler_attribution",
    }


def _get_any(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _float_from_any(obj: Any, *names: str) -> float:
    value = _get_any(obj, *names)
    if value is None:
        raise ValueError(f"missing coordinate field, expected one of {names}")
    return float(value)


def _xy(point: Any) -> tuple[float, float]:
    if isinstance(point, Mapping):
        return (
            _float_from_any(point, "x_val", "x", "u"),
            _float_from_any(point, "y_val", "y", "v"),
        )
    return (
        float(_get_any(point, "x_val", "x", "u")),
        float(_get_any(point, "y_val", "y", "v")),
    )


def _class_id_from_record(detection: Any) -> int | None:
    value = _get_any(detection, "class_id", "cls", "class_index")
    if value is None:
        return None
    return int(value)


def _track_id_aliases_truth_or_global(record: Any, track_id: str | int | None) -> bool:
    if track_id is None:
        return False
    track_text = str(track_id)
    for field_name in TRUTH_OR_GLOBAL_FIELD_NAMES:
        value = _get_any(record, field_name)
        if value is not None and str(value) == track_text:
            return True
    return False


def _category_from_class_id(
    class_id: int | None,
    names: Mapping[int, str] | Sequence[str] | None,
    *,
    default_category: str = "unknown",
) -> str:
    if class_id is None:
        return default_category
    if isinstance(names, Mapping):
        mapped = names.get(class_id)
        if mapped is None:
            mapped = names.get(str(class_id))
        return str(mapped) if mapped is not None else f"class_{class_id}"
    if isinstance(names, Sequence) and not isinstance(names, (str, bytes, bytearray)):
        if 0 <= class_id < len(names):
            return str(names[class_id])
    return f"class_{class_id}"


def _clean_track_id(value: Any) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, np.generic):
        return _clean_track_id(value.item())
    text = str(value)
    return text if text else None


def _to_numpy(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def _optional_column(value: Any, size: int, *, default: float) -> np.ndarray:
    array = _to_numpy(value)
    if array is None:
        return np.full(size, default, dtype=float)
    array = np.asarray(array, dtype=float).reshape(-1)
    if array.shape[0] != size:
        raise ValueError(f"expected {size} detector values, got {array.shape[0]}")
    return array


def _optional_nonnegative_float(value: float | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric < 0.0:
        raise ValueError("budget values must be non-negative")
    return numeric


def _normalize_inference_imgsz(
    value: int | Sequence[int] | None,
) -> int | tuple[int, int] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("inference_imgsz must be a positive integer or a (height, width) pair")
    if isinstance(value, (int, np.integer)):
        size = int(value)
        if size <= 0:
            raise ValueError("inference_imgsz must be positive")
        return size
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        dimensions = tuple(value)
        if len(dimensions) != 2:
            raise ValueError("inference_imgsz pair must contain (height, width)")
        if any(isinstance(item, bool) or not isinstance(item, (int, np.integer)) for item in dimensions):
            raise ValueError("inference_imgsz dimensions must be positive integers")
        height, width = (int(item) for item in dimensions)
        if height <= 0 or width <= 0:
            raise ValueError("inference_imgsz dimensions must be positive")
        return (height, width)
    raise ValueError("inference_imgsz must be a positive integer or a (height, width) pair")


def _inference_imgsz_metadata_value(
    value: int | tuple[int, int] | None,
) -> int | tuple[int, int] | None:
    return value


def _optional_positive_float(value: float | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not np.isfinite(numeric) or numeric <= 0.0:
        raise ValueError("target_distance_m must be positive and finite")
    return numeric
