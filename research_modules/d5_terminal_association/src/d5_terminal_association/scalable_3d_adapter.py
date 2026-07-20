"""Truth-isolated adapter from the scalable 3D online bus into D5.

The module deliberately uses duck typing.  It depends only on D5 contracts and
never imports simulator or D2 implementation classes.  Transport identifiers
are validated but are never reused as camera-local tracker identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
import math
import re
import time
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .models import CameraModel, GlobalTrack
from .sparse_tracklet_graph import (
    CameraLocalTracklet,
    CenterTrackBindingDecision,
    SparseTrackletGraph,
    SparseTrackletGraphConfig,
    TrackletCameraGeometry,
    TrackletCluster,
    assert_anonymous_online_payload,
    bind_clusters_to_center_tracks,
    build_sparse_tracklet_graph,
    constrained_tracklet_clusters,
    is_truth_like_local_track_id,
)


_MISSING = object()
_CANONICAL_MEASUREMENT_ORDER = ("u", "v", "xmin", "ymin", "xmax", "ymax")
_MEASUREMENT_NAME_ALIASES = {
    "center_x": "u",
    "center_y": "v",
    "cx": "u",
    "cy": "v",
    "x1": "xmin",
    "x2": "xmax",
    "x_max": "xmax",
    "x_min": "xmin",
    "y1": "ymin",
    "y2": "ymax",
    "y_max": "ymax",
    "y_min": "ymin",
}
_CAMERA_SENSOR_PATTERN = re.compile(r"^CAM-(INT-\d+|RECON-\d+)(?:-|$)", re.IGNORECASE)


@dataclass(frozen=True)
class Scalable3DAdapterConfig:
    """Anonymous tracking, geometry, scoring, and binding thresholds."""

    iou_match_threshold: float = 0.20
    max_center_distance_px: float = 80.0
    max_missed_frames: int = 2
    default_center_variance_px2: float = 9.0
    default_bbox_variance_px2: float = 16.0
    default_position_variance_m2: float = 0.25
    default_attitude_variance_rad2: float = field(
        default_factory=lambda: math.radians(0.10) ** 2
    )
    rule_probability_temperature: float = 2.5
    rule_single_projection_probability_floor: float = 0.75
    edge_probability_threshold: float = 0.50
    model_min_mean_certainty: float = 0.15
    model_inference_timeout_ms: float = 50.0
    max_binding_mahalanobis: float = 6.0
    binding_ambiguity_margin: float = 0.5
    graph_config: SparseTrackletGraphConfig = field(default_factory=SparseTrackletGraphConfig)

    def __post_init__(self) -> None:
        bounded = (
            "iou_match_threshold",
            "rule_single_projection_probability_floor",
            "edge_probability_threshold",
            "model_min_mean_certainty",
        )
        for name in bounded:
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            object.__setattr__(self, name, value)
        positive = (
            "max_center_distance_px",
            "default_center_variance_px2",
            "default_bbox_variance_px2",
            "default_position_variance_m2",
            "default_attitude_variance_rad2",
            "rule_probability_temperature",
            "model_inference_timeout_ms",
            "max_binding_mahalanobis",
        )
        for name in positive:
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, value)
        ambiguity_margin = float(self.binding_ambiguity_margin)
        if not np.isfinite(ambiguity_margin) or ambiguity_margin < 0.0:
            raise ValueError("binding_ambiguity_margin must be finite and non-negative")
        object.__setattr__(self, "binding_ambiguity_margin", ambiguity_margin)
        max_missed_frames = int(self.max_missed_frames)
        if max_missed_frames < 0:
            raise ValueError("max_missed_frames must be non-negative")
        object.__setattr__(self, "max_missed_frames", max_missed_frames)
        if not isinstance(self.graph_config, SparseTrackletGraphConfig):
            raise TypeError("graph_config must be SparseTrackletGraphConfig")


@dataclass(frozen=True)
class Scalable3DAdaptedCameraBatch:
    """One online camera scan after anonymous local tracking and geometry parsing."""

    resource_id: str
    camera_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    tracklets: tuple[CameraLocalTracklet, ...]
    camera_geometry: TrackletCameraGeometry | None
    status: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"ok", "empty", "empty_geometry_unavailable"}:
            raise ValueError("invalid adapted camera batch status")
        object.__setattr__(self, "tracklets", tuple(self.tracklets))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def source_observation_links(self) -> tuple["SourceObservationTrackletLink", ...]:
        return source_observation_tracklet_links(self.tracklets)


@dataclass(frozen=True)
class Scalable3DAssociationResult:
    """Sparse online association result with explicit model/rule provenance."""

    graph: SparseTrackletGraph
    edge_probabilities: np.ndarray
    clusters: tuple[TrackletCluster, ...]
    bindings: tuple[CenterTrackBindingDecision, ...]
    scoring_status: str
    probability_source: str
    fallback_reason: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        probabilities = np.asarray(self.edge_probabilities, dtype=float).reshape(-1).copy()
        if probabilities.shape != (self.graph.edge_count,):
            raise ValueError("edge probability count must match graph edge count")
        if not np.all(np.isfinite(probabilities)) or np.any(
            (probabilities < 0.0) | (probabilities > 1.0)
        ):
            raise ValueError("edge probabilities must be finite and in [0, 1]")
        probabilities.setflags(write=False)
        object.__setattr__(self, "edge_probabilities", probabilities)
        object.__setattr__(self, "clusters", tuple(self.clusters))
        object.__setattr__(self, "bindings", tuple(self.bindings))
        diagnostics = dict(self.graph.candidate_counts)
        diagnostics.update(dict(self.diagnostics))
        diagnostics.update(
            {
                "scoring_status": str(self.scoring_status),
                "probability_source": str(self.probability_source),
                "fallback_reason": (
                    "none" if self.fallback_reason is None else str(self.fallback_reason)
                ),
            }
        )
        object.__setattr__(self, "diagnostics", MappingProxyType(diagnostics))


@dataclass(frozen=True)
class Scalable3DStepResult:
    """End-to-end module-owned result for one collection of camera scans."""

    camera_batches: tuple[Scalable3DAdaptedCameraBatch, ...]
    center_projection_tracks: tuple[GlobalTrack, ...]
    association: Scalable3DAssociationResult

    @property
    def tracklets(self) -> tuple[CameraLocalTracklet, ...]:
        return tuple(tracklet for batch in self.camera_batches for tracklet in batch.tracklets)

    @property
    def camera_geometries(self) -> tuple[TrackletCameraGeometry, ...]:
        return tuple(
            batch.camera_geometry
            for batch in self.camera_batches
            if batch.camera_geometry is not None
        )

    @property
    def source_observation_links(self) -> tuple["SourceObservationTrackletLink", ...]:
        return source_observation_tracklet_links(self.tracklets)


@dataclass(frozen=True)
class SourceObservationTrackletLink:
    """Truth-free audit link from one source measurement to one frame tracklet."""

    source_observation_id: str
    tracklet_key: str
    camera_key: str
    measurement_timestamp: float

    def __post_init__(self) -> None:
        for name in ("source_observation_id", "tracklet_key", "camera_key"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "measurement_timestamp",
            _finite_float(self.measurement_timestamp, "measurement_timestamp"),
        )


@dataclass(frozen=True)
class _PreparedDetection:
    source_observation_id: str | None
    center_px: np.ndarray
    bbox_xyxy: tuple[float, float, float, float]
    center_covariance_px: np.ndarray
    bbox_covariance_px: np.ndarray
    confidence: float


@dataclass(frozen=True)
class _CameraTemplate:
    K: np.ndarray
    R: np.ndarray
    t: np.ndarray
    image_size: tuple[int, int]
    measurement_covariance_px: np.ndarray
    position_covariance_ned: np.ndarray
    attitude_covariance_rad2: np.ndarray
    position_covariance_source: str
    attitude_covariance_source: str

    def geometry(
        self,
        resource_id: str,
        camera_id: str,
        measurement_timestamp: float,
    ) -> TrackletCameraGeometry:
        return TrackletCameraGeometry(
            resource_id=resource_id,
            camera_id=camera_id,
            camera=CameraModel(
                K=self.K,
                R=self.R,
                t=self.t,
                image_size=self.image_size,
                measurement_cov=self.measurement_covariance_px,
            ),
            measurement_timestamp=measurement_timestamp,
            position_covariance_ned=self.position_covariance_ned,
            attitude_covariance_rad2=self.attitude_covariance_rad2,
        )


@dataclass(frozen=True)
class _PreparedCameraBatch:
    resource_id: str
    camera_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    detections: tuple[_PreparedDetection, ...]
    camera_template: _CameraTemplate | None

    @property
    def stream_key(self) -> tuple[str, str]:
        return (self.resource_id, self.camera_id)


@dataclass
class _AnonymousTrackState:
    sequence: int
    center_px: np.ndarray
    bbox_xyxy: tuple[float, float, float, float]
    measurement_timestamp: float
    tracklet_start_timestamp: float
    hits: int = 1
    missed_frames: int = 0


class _AnonymousCameraTracker:
    """Deterministic per-camera tracker that owns all local ID allocation."""

    def __init__(self, config: Scalable3DAdapterConfig) -> None:
        self.config = config
        self._next_sequence = 1
        self._tracks: dict[int, _AnonymousTrackState] = {}
        self._last_timestamp: float | None = None

    def validate_timestamp(self, timestamp: float) -> None:
        if self._last_timestamp is not None and timestamp + 1.0e-12 < self._last_timestamp:
            raise ValueError("camera scan timestamps must be monotonic within an episode")

    def update(
        self,
        detections: Sequence[_PreparedDetection],
        *,
        resource_id: str,
        camera_id: str,
        measurement_timestamp: float,
        arrival_timestamp: float,
        camera_template: _CameraTemplate | None,
    ) -> tuple[CameraLocalTracklet, ...]:
        self.validate_timestamp(measurement_timestamp)
        ordered_detections = tuple(
            sorted(
                detections,
                key=lambda item: (
                    float(item.center_px[0]),
                    float(item.center_px[1]),
                    item.bbox_xyxy,
                ),
            )
        )
        assignments = self._match(ordered_detections)
        matched_sequences = set(assignments.values())
        output: list[CameraLocalTracklet] = []

        for detection_index, detection in enumerate(ordered_detections):
            sequence = assignments.get(detection_index)
            if sequence is None:
                sequence = self._next_sequence
                self._next_sequence += 1
                state = _AnonymousTrackState(
                    sequence=sequence,
                    center_px=detection.center_px.copy(),
                    bbox_xyxy=detection.bbox_xyxy,
                    measurement_timestamp=measurement_timestamp,
                    tracklet_start_timestamp=measurement_timestamp,
                )
                self._tracks[sequence] = state
                angular_velocity = np.zeros(2, dtype=float)
                bbox_scale_rate = 0.0
            else:
                state = self._tracks[sequence]
                elapsed = measurement_timestamp - state.measurement_timestamp
                if elapsed > 1.0e-12 and camera_template is not None:
                    focal = np.array(
                        [camera_template.K[0, 0], camera_template.K[1, 1]],
                        dtype=float,
                    )
                    angular_velocity = (
                        detection.center_px - state.center_px
                    ) / focal / elapsed
                    previous_area = _bbox_area(state.bbox_xyxy)
                    current_area = _bbox_area(detection.bbox_xyxy)
                    bbox_scale_rate = 0.5 * math.log(
                        max(current_area, 1.0e-12) / max(previous_area, 1.0e-12)
                    ) / elapsed
                else:
                    angular_velocity = np.zeros(2, dtype=float)
                    bbox_scale_rate = 0.0
                state.center_px = detection.center_px.copy()
                state.bbox_xyxy = detection.bbox_xyxy
                state.measurement_timestamp = measurement_timestamp
                state.hits += 1
                state.missed_frames = 0

            local_track_id = f"trk-{sequence:06d}"
            output.append(
                CameraLocalTracklet(
                    resource_id=resource_id,
                    camera_id=camera_id,
                    local_track_id=local_track_id,
                    measurement_timestamp=measurement_timestamp,
                    arrival_timestamp=arrival_timestamp,
                    center_px=detection.center_px,
                    covariance_px=detection.center_covariance_px,
                    bbox_xyxy=detection.bbox_xyxy,
                    angular_velocity_rad_s=angular_velocity,
                    bbox_scale_rate_s=bbox_scale_rate,
                    confidence=detection.confidence,
                    tracklet_start_timestamp=state.tracklet_start_timestamp,
                    source_observation_id=detection.source_observation_id,
                    metadata={
                        "source": "scalable_3d_online_vision_bbox",
                        "tracker_backend": "d5_anonymous_iou_center",
                        "tracker_state_scope": "per_resource_camera",
                        "mot_history_length": state.hits,
                        "bbox_covariance_px": tuple(
                            tuple(float(value) for value in row)
                            for row in detection.bbox_covariance_px
                        ),
                    },
                )
            )

        for sequence, state in list(self._tracks.items()):
            if sequence in matched_sequences or any(
                tracklet.local_track_id == f"trk-{sequence:06d}" for tracklet in output
            ):
                continue
            state.missed_frames += 1
            if state.missed_frames > self.config.max_missed_frames:
                del self._tracks[sequence]

        self._last_timestamp = measurement_timestamp
        return tuple(sorted(output, key=lambda item: item.local_track_id))

    def _match(self, detections: Sequence[_PreparedDetection]) -> dict[int, int]:
        candidates: list[tuple[float, float, int, int]] = []
        for sequence, state in self._tracks.items():
            for detection_index, detection in enumerate(detections):
                iou = _bbox_iou(state.bbox_xyxy, detection.bbox_xyxy)
                distance = float(np.linalg.norm(state.center_px - detection.center_px))
                if iou < self.config.iou_match_threshold and distance > self.config.max_center_distance_px:
                    continue
                candidates.append((-iou, distance, sequence, detection_index))

        matched_sequences: set[int] = set()
        matched_detections: set[int] = set()
        assignments: dict[int, int] = {}
        for _, _, sequence, detection_index in sorted(candidates):
            if sequence in matched_sequences or detection_index in matched_detections:
                continue
            matched_sequences.add(sequence)
            matched_detections.add(detection_index)
            assignments[detection_index] = sequence
        return assignments


class Scalable3DTerminalAdapter:
    """Stateful, episode-resettable adapter for scalable 3D D5 processing."""

    def __init__(self, config: Scalable3DAdapterConfig | None = None) -> None:
        self.config = config or Scalable3DAdapterConfig()
        self._trackers: dict[tuple[str, str], _AnonymousCameraTracker] = {}

    def adapt_batch(self, batch: Any) -> Scalable3DAdaptedCameraBatch:
        return self.adapt_batches((batch,))[0]

    def adapt_batches(self, batches: Iterable[Any]) -> tuple[Scalable3DAdaptedCameraBatch, ...]:
        raw_batches = tuple(batches)
        for batch in raw_batches:
            _assert_truth_isolated_transport(batch)
        prepared = tuple(_prepare_camera_batch(batch, self.config) for batch in raw_batches)
        frame_source_keys = tuple(
            (item.measurement_timestamp, detection.source_observation_id)
            for item in prepared
            for detection in item.detections
            if detection.source_observation_id is not None
        )
        if len(frame_source_keys) != len(set(frame_source_keys)):
            raise ValueError("one source observation may belong to only one tracklet per frame")
        stream_keys = tuple(item.stream_key for item in prepared)
        if len(stream_keys) != len(set(stream_keys)):
            raise ValueError("one adapt_batches call may contain at most one batch per camera stream")
        for item in prepared:
            tracker = self._trackers.get(item.stream_key)
            if tracker is not None:
                tracker.validate_timestamp(item.measurement_timestamp)
        return tuple(self._commit_prepared_batch(item) for item in prepared)

    def process(
        self,
        batches: Iterable[Any],
        center_tracks_3d: Iterable[Any],
        *,
        edge_model: Any | None = None,
    ) -> Scalable3DStepResult:
        adapted_batches = self.adapt_batches(batches)
        center_tracks = global_tracks3d_to_projection_tracks(center_tracks_3d)
        association = run_scalable_3d_online_association(
            tuple(tracklet for batch in adapted_batches for tracklet in batch.tracklets),
            tuple(
                batch.camera_geometry
                for batch in adapted_batches
                if batch.camera_geometry is not None
            ),
            center_tracks,
            config=self.config,
            edge_model=edge_model,
        )
        return Scalable3DStepResult(adapted_batches, center_tracks, association)

    def reset_stream(self, resource_id: str, camera_id: str) -> None:
        key = (str(resource_id).strip(), str(camera_id).strip())
        self._trackers.pop(key, None)

    def reset_episode(self) -> None:
        self._trackers.clear()

    def _commit_prepared_batch(
        self,
        prepared: _PreparedCameraBatch,
    ) -> Scalable3DAdaptedCameraBatch:
        key = prepared.stream_key
        tracker = self._trackers.setdefault(key, _AnonymousCameraTracker(self.config))
        template = prepared.camera_template
        tracklets = tracker.update(
            prepared.detections,
            resource_id=prepared.resource_id,
            camera_id=prepared.camera_id,
            measurement_timestamp=prepared.measurement_timestamp,
            arrival_timestamp=prepared.arrival_timestamp,
            camera_template=template,
        )
        geometry = (
            None
            if template is None
            else template.geometry(
                prepared.resource_id,
                prepared.camera_id,
                prepared.measurement_timestamp,
            )
        )
        if tracklets:
            status = "ok"
        elif geometry is not None:
            status = "empty"
        else:
            status = "empty_geometry_unavailable"
        metadata = {
            "input_detection_count": len(prepared.detections),
            "output_tracklet_count": len(tracklets),
            "tracker_state_scope": "per_resource_camera",
            "local_id_source": "d5_tracker_allocated",
            "geometry_source": (
                "current_batch_metadata" if geometry is not None else "unavailable"
            ),
            "position_covariance_source": (
                None if template is None else template.position_covariance_source
            ),
            "attitude_covariance_source": (
                None if template is None else template.attitude_covariance_source
            ),
        }
        return Scalable3DAdaptedCameraBatch(
            resource_id=prepared.resource_id,
            camera_id=prepared.camera_id,
            measurement_timestamp=prepared.measurement_timestamp,
            arrival_timestamp=prepared.arrival_timestamp,
            tracklets=tracklets,
            camera_geometry=geometry,
            status=status,
            metadata=metadata,
        )


def global_track3d_to_projection_track(track: Any) -> GlobalTrack:
    """Copy one duck-typed six-state center track into a D5 projection hypothesis."""

    global_track_id = _field(track, "global_track_id")
    if not isinstance(global_track_id, str) or not global_track_id:
        raise ValueError("center global_track_id must be a non-empty string")
    state = _finite_array(_field(track, "state"), (6,), "center track state")
    covariance = _positive_semidefinite(
        _field(track, "covariance"),
        (6, 6),
        "center track covariance",
    )
    timestamp = _finite_float(_field(track, "timestamp"), "center track timestamp")
    track_version = int(_field(track, "track_version", 0))
    adapted = GlobalTrack(
        global_track_id=global_track_id,
        position=state[:3],
        velocity=state[3:],
        covariance=covariance[:3, :3],
        timestamp=timestamp,
        track_version=track_version,
    )
    if _field(track, "global_track_id") != global_track_id:
        raise RuntimeError("center global_track_id changed during read-only adaptation")
    return adapted


def global_tracks3d_to_projection_tracks(tracks: Iterable[Any]) -> tuple[GlobalTrack, ...]:
    adapted = tuple(global_track3d_to_projection_track(track) for track in tracks)
    identifiers = tuple(track.global_track_id for track in adapted)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("center global_track_id values must be unique")
    return adapted


def run_scalable_3d_online_association(
    tracklets: Iterable[CameraLocalTracklet],
    camera_geometries: Iterable[TrackletCameraGeometry],
    center_tracks: Iterable[GlobalTrack],
    *,
    config: Scalable3DAdapterConfig | None = None,
    edge_model: Any | None = None,
) -> Scalable3DAssociationResult:
    """Build, score, constrain, and center-bind one anonymous online graph."""

    cfg = config or Scalable3DAdapterConfig()
    tracklet_items = tuple(tracklets)
    geometry_items = tuple(camera_geometries)
    center_items = tuple(center_tracks)
    center_ids_before = tuple(track.global_track_id for track in center_items)
    graph = build_sparse_tracklet_graph(
        tracklet_items,
        geometry_items,
        center_tracks=center_items,
        config=cfg.graph_config,
    )
    (
        probabilities,
        status,
        source,
        fallback_reason,
        probability_threshold,
        inference_latency_ms,
    ) = _score_graph_edges(
        graph,
        cfg,
        edge_model,
    )
    clusters = constrained_tracklet_clusters(
        graph,
        probabilities,
        probability_threshold=probability_threshold,
    )
    bindings = bind_clusters_to_center_tracks(
        graph,
        clusters,
        geometry_items,
        center_items,
        max_binding_mahalanobis=cfg.max_binding_mahalanobis,
        ambiguity_margin=cfg.binding_ambiguity_margin,
        config=cfg.graph_config,
    )
    if tuple(track.global_track_id for track in center_items) != center_ids_before:
        raise RuntimeError("D5 association mutated a center global_track_id")
    return Scalable3DAssociationResult(
        graph=graph,
        edge_probabilities=probabilities,
        clusters=clusters,
        bindings=bindings,
        scoring_status=status,
        probability_source=source,
        fallback_reason=fallback_reason,
        diagnostics={
            "edge_probability_threshold": probability_threshold,
            "model_inference_latency_ms": inference_latency_ms,
        },
    )


def _score_graph_edges(
    graph: SparseTrackletGraph,
    config: Scalable3DAdapterConfig,
    edge_model: Any | None,
) -> tuple[np.ndarray, str, str, str | None, float, float | None]:
    rule_probabilities = _deterministic_edge_probabilities(graph, config)
    if edge_model is None:
        return (
            rule_probabilities,
            "rule_fallback_model_missing",
            "deterministic_geometry_rule",
            "model_missing",
            config.edge_probability_threshold,
            None,
        )
    if getattr(edge_model, "available", True) is not True:
        reason = str(getattr(edge_model, "failure_reason", "model_unavailable"))
        return (
            rule_probabilities,
            "rule_fallback_model_unavailable",
            "deterministic_geometry_rule",
            reason,
            config.edge_probability_threshold,
            None,
        )
    started = time.perf_counter()
    try:
        raw = edge_model.forward_graph(graph)
        if hasattr(raw, "detach") and callable(raw.detach):
            raw = raw.detach().cpu().numpy()
        probabilities = np.asarray(raw, dtype=float).reshape(-1)
        if probabilities.shape != (graph.edge_count,):
            return (
                rule_probabilities,
                "rule_fallback_model_invalid_output",
                "deterministic_geometry_rule",
                "model_output_shape_mismatch",
                config.edge_probability_threshold,
                (time.perf_counter() - started) * 1000.0,
            )
        if not np.all(np.isfinite(probabilities)):
            return (
                rule_probabilities,
                "rule_fallback_model_invalid_output",
                "deterministic_geometry_rule",
                "model_output_non_finite",
                config.edge_probability_threshold,
                (time.perf_counter() - started) * 1000.0,
            )
        if np.any((probabilities < 0.0) | (probabilities > 1.0)):
            return (
                rule_probabilities,
                "rule_fallback_model_invalid_output",
                "deterministic_geometry_rule",
                "model_output_out_of_range",
                config.edge_probability_threshold,
                (time.perf_counter() - started) * 1000.0,
            )
    except Exception as exc:
        return (
            rule_probabilities,
            "rule_fallback_model_error",
            "deterministic_geometry_rule",
            f"model_error:{type(exc).__name__}",
            config.edge_probability_threshold,
            (time.perf_counter() - started) * 1000.0,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if elapsed_ms > config.model_inference_timeout_ms:
        return (
            rule_probabilities,
            "rule_fallback_model_timeout",
            "deterministic_geometry_rule",
            "model_inference_timeout",
            config.edge_probability_threshold,
            elapsed_ms,
        )
    if graph.edge_count:
        mean_certainty = float(np.mean(np.abs(probabilities - 0.5) * 2.0))
        if mean_certainty < config.model_min_mean_certainty:
            return (
                rule_probabilities,
                "rule_fallback_low_confidence",
                "deterministic_geometry_rule",
                "model_low_mean_certainty",
                config.edge_probability_threshold,
                elapsed_ms,
            )
    probability_threshold = config.edge_probability_threshold
    if hasattr(edge_model, "decision_threshold"):
        try:
            probability_threshold = float(edge_model.decision_threshold)
        except (TypeError, ValueError):
            probability_threshold = math.nan
        if not np.isfinite(probability_threshold) or not 0.0 <= probability_threshold <= 1.0:
            return (
                rule_probabilities,
                "rule_fallback_model_invalid_threshold",
                "deterministic_geometry_rule",
                "model_decision_threshold_invalid",
                config.edge_probability_threshold,
                elapsed_ms,
            )
    return (
        probabilities,
        "model_scored",
        "loaded_edge_model",
        None,
        probability_threshold,
        elapsed_ms,
    )


def _deterministic_edge_probabilities(
    graph: SparseTrackletGraph,
    config: Scalable3DAdapterConfig,
) -> np.ndarray:
    probabilities = np.empty(graph.edge_count, dtype=float)
    for index, edge in enumerate(graph.edges):
        probability = math.exp(-max(0.0, edge.gate_score) / config.rule_probability_temperature)
        if len(edge.shared_global_track_ids) == 1:
            probability = max(
                probability,
                config.rule_single_projection_probability_floor,
            )
        probabilities[index] = float(np.clip(probability, 0.0, 1.0))
    return probabilities


def _prepare_camera_batch(batch: Any, config: Scalable3DAdapterConfig) -> _PreparedCameraBatch:
    measurements = tuple(_field(batch, "measurements", ()))
    measurement_timestamp = _finite_float(
        _field(batch, "measurement_timestamp"),
        "batch measurement_timestamp",
    )
    arrival_timestamp = _finite_float(
        _field(batch, "arrival_timestamp"),
        "batch arrival_timestamp",
    )
    if arrival_timestamp + 1.0e-12 < measurement_timestamp:
        raise ValueError("batch arrival_timestamp must not precede measurement_timestamp")
    batch_metadata = _combined_batch_metadata(batch)
    resource_id, camera_id, sensor_id = _camera_namespace(batch, measurements, batch_metadata)
    detections: list[_PreparedDetection] = []
    measurement_metadata: list[Mapping[str, Any]] = []
    for measurement in measurements:
        modality = str(_field(measurement, "modality", "")).strip().lower()
        if modality != "vision_bbox":
            raise ValueError("scalable D5 adapter accepts only vision_bbox measurements")
        item_sensor_id = str(_field(measurement, "sensor_id", sensor_id)).strip()
        if item_sensor_id != sensor_id:
            raise ValueError("all measurements in a camera batch must share sensor_id")
        item_measurement_timestamp = _finite_float(
            _field(measurement, "measurement_timestamp"),
            "measurement_timestamp",
        )
        item_arrival_timestamp = _finite_float(
            _field(measurement, "arrival_timestamp"),
            "arrival_timestamp",
        )
        if abs(item_measurement_timestamp - measurement_timestamp) > 1.0e-9:
            raise ValueError("measurement timestamp does not match its online batch")
        if abs(item_arrival_timestamp - arrival_timestamp) > 1.0e-9:
            raise ValueError("arrival timestamp does not match its online batch")
        metadata = _as_mapping(_field(measurement, "metadata", {}), "measurement metadata")
        merged_metadata = {**batch_metadata, **metadata}
        item_resource_id, item_camera_id, _ = _camera_namespace(
            batch,
            (measurement,),
            merged_metadata,
        )
        if (item_resource_id, item_camera_id) != (resource_id, camera_id):
            raise ValueError("camera namespace changes within one online batch")
        detections.append(_prepare_detection(measurement, metadata, config))
        measurement_metadata.append(merged_metadata)

    source_ids = tuple(
        item.source_observation_id
        for item in detections
        if item.source_observation_id is not None
    )
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("one source observation may belong to only one detection per frame")

    center_covariance = (
        np.mean(np.stack([item.center_covariance_px for item in detections]), axis=0)
        if detections
        else np.eye(2, dtype=float) * config.default_center_variance_px2
    )
    template_metadata = measurement_metadata[0] if measurement_metadata else batch_metadata
    camera_template = (
        _camera_template(template_metadata, center_covariance, config)
        if _has_complete_camera_metadata(template_metadata)
        else None
    )
    if detections and camera_template is None:
        raise ValueError("vision_bbox measurements require complete camera metadata")
    for metadata in measurement_metadata[1:]:
        other = _camera_template(metadata, center_covariance, config)
        if not _camera_templates_equivalent(camera_template, other):
            raise ValueError("camera geometry changes within one online batch")
    return _PreparedCameraBatch(
        resource_id=resource_id,
        camera_id=camera_id,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        detections=tuple(detections),
        camera_template=camera_template,
    )


def _prepare_detection(
    measurement: Any,
    metadata: Mapping[str, Any],
    config: Scalable3DAdapterConfig,
) -> _PreparedDetection:
    values = np.asarray(_field(measurement, "measurement"), dtype=float).reshape(-1)
    if values.shape != (6,) or not np.all(np.isfinite(values)):
        raise ValueError("vision_bbox measurement must contain six finite values")
    order = _measurement_order(metadata)
    indices = {name: order.index(name) for name in _CANONICAL_MEASUREMENT_ORDER}
    center = values[[indices["u"], indices["v"]]].astype(float, copy=True)
    bbox = tuple(
        float(values[indices[name]]) for name in ("xmin", "ymin", "xmax", "ymax")
    )
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        raise ValueError("vision_bbox bounds must have positive width and height")
    covariance_value = _field(measurement, "covariance", None)
    if covariance_value is None:
        center_covariance = np.eye(2, dtype=float) * config.default_center_variance_px2
        bbox_covariance = np.eye(4, dtype=float) * config.default_bbox_variance_px2
    else:
        covariance = np.asarray(covariance_value, dtype=float)
        if covariance.shape == (2, 2):
            center_covariance = _positive_semidefinite(
                covariance,
                (2, 2),
                "center pixel covariance",
            )
            bbox_covariance = np.eye(4, dtype=float) * config.default_bbox_variance_px2
        elif covariance.shape == (6, 6):
            covariance = _positive_semidefinite(
                covariance,
                (6, 6),
                "vision_bbox covariance",
            )
            center_indices = [indices["u"], indices["v"]]
            bbox_indices = [indices[name] for name in ("xmin", "ymin", "xmax", "ymax")]
            center_covariance = covariance[np.ix_(center_indices, center_indices)]
            bbox_covariance = covariance[np.ix_(bbox_indices, bbox_indices)]
        else:
            raise ValueError("vision_bbox covariance must be 2x2 or 6x6")
    confidence = _finite_float(_field(measurement, "confidence", 1.0), "confidence")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    raw_observation_id = _field(measurement, "observation_id", None)
    source_observation_id = (
        None if raw_observation_id is None else str(raw_observation_id).strip()
    )
    if raw_observation_id is not None and not source_observation_id:
        raise ValueError("observation_id must be non-empty when present")
    if source_observation_id is not None and is_truth_like_local_track_id(
        source_observation_id
    ):
        raise ValueError("observation_id must be an anonymous measurement key")
    return _PreparedDetection(
        source_observation_id=source_observation_id,
        center_px=center,
        bbox_xyxy=bbox,
        center_covariance_px=center_covariance,
        bbox_covariance_px=bbox_covariance,
        confidence=confidence,
    )


def _camera_template(
    metadata: Mapping[str, Any],
    measurement_covariance: np.ndarray,
    config: Scalable3DAdapterConfig,
) -> _CameraTemplate:
    intrinsics_value = metadata["camera_intrinsics"]
    if isinstance(intrinsics_value, Mapping):
        fx = _finite_float(intrinsics_value["fx"], "camera fx")
        fy = _finite_float(intrinsics_value["fy"], "camera fy")
        cx = _finite_float(intrinsics_value["cx"], "camera cx")
        cy = _finite_float(intrinsics_value["cy"], "camera cy")
        width = int(intrinsics_value["width_px"])
        height = int(intrinsics_value["height_px"])
        K = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=float)
    else:
        K = _finite_array(intrinsics_value, (3, 3), "camera intrinsics")
        image_size = _first_present(metadata, ("image_size", "camera_image_size"))
        width, height = (int(value) for value in np.asarray(image_size).reshape(2))
    if width <= 0 or height <= 0 or K[0, 0] <= 0.0 or K[1, 1] <= 0.0:
        raise ValueError("camera intrinsics and image size must be positive")

    position = _finite_array(
        _first_present(metadata, ("camera_position_ned", "position_ned")),
        (3,),
        "camera position NED",
    )
    rotation = _finite_array(
        _first_present(
            metadata,
            ("rotation_camera_from_ned", "camera_rotation_from_ned"),
        ),
        (3, 3),
        "rotation camera from NED",
    )
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1.0e-5) or np.linalg.det(rotation) <= 0.0:
        raise ValueError("camera rotation must be a proper orthonormal matrix")

    position_covariance_value = _first_present(
        metadata,
        ("camera_position_covariance_ned", "position_covariance_ned"),
        default=None,
    )
    if position_covariance_value is None:
        position_covariance = np.eye(3, dtype=float) * config.default_position_variance_m2
        position_source = "configured_fallback"
    else:
        position_covariance = _positive_semidefinite(
            position_covariance_value,
            (3, 3),
            "camera position covariance",
        )
        position_source = "metadata"
    attitude_covariance_value = _first_present(
        metadata,
        ("camera_attitude_covariance_rad2", "attitude_covariance_rad2"),
        default=None,
    )
    if attitude_covariance_value is None:
        attitude_covariance = np.eye(3, dtype=float) * config.default_attitude_variance_rad2
        attitude_source = "configured_fallback"
    else:
        attitude_covariance = _positive_semidefinite(
            attitude_covariance_value,
            (3, 3),
            "camera attitude covariance",
        )
        attitude_source = "metadata"
    return _CameraTemplate(
        K=K,
        R=rotation,
        t=-rotation @ position,
        image_size=(width, height),
        measurement_covariance_px=_positive_semidefinite(
            measurement_covariance,
            (2, 2),
            "camera measurement covariance",
        ),
        position_covariance_ned=position_covariance,
        attitude_covariance_rad2=attitude_covariance,
        position_covariance_source=position_source,
        attitude_covariance_source=attitude_source,
    )


def _camera_templates_equivalent(
    left: _CameraTemplate | None,
    right: _CameraTemplate | None,
) -> bool:
    if left is None or right is None:
        return left is right
    return bool(
        left.image_size == right.image_size
        and np.allclose(left.K, right.K)
        and np.allclose(left.R, right.R)
        and np.allclose(left.t, right.t)
        and np.allclose(left.position_covariance_ned, right.position_covariance_ned)
        and np.allclose(left.attitude_covariance_rad2, right.attitude_covariance_rad2)
    )


def _camera_namespace(
    batch: Any,
    measurements: Sequence[Any],
    metadata: Mapping[str, Any],
) -> tuple[str, str, str]:
    batch_sensor_id = str(_field(batch, "sensor_id", "")).strip()
    measurement_sensor_ids = {
        str(_field(item, "sensor_id", batch_sensor_id)).strip() for item in measurements
    }
    measurement_sensor_ids.discard("")
    if batch_sensor_id:
        measurement_sensor_ids.add(batch_sensor_id)
    if len(measurement_sensor_ids) != 1:
        raise ValueError("camera batch must identify exactly one sensor_id")
    sensor_id = next(iter(measurement_sensor_ids))
    resource_value = _first_present(
        {
            **metadata,
            "_batch_resource_id": _field(batch, "resource_id", None),
        },
        ("_batch_resource_id", "resource_id", "platform_id"),
        default=None,
    )
    camera_value = _first_present(
        {
            **metadata,
            "_batch_camera_id": _field(batch, "camera_id", None),
        },
        ("_batch_camera_id", "camera_id"),
        default=None,
    )
    if resource_value is None:
        match = _CAMERA_SENSOR_PATTERN.match(sensor_id)
        resource_id = match.group(1).upper() if match else sensor_id
    else:
        resource_id = str(resource_value).strip()
    camera_id = sensor_id if camera_value is None else str(camera_value).strip()
    if not resource_id or not camera_id:
        raise ValueError("resource_id and camera_id must be non-empty")
    return resource_id, camera_id, sensor_id


def _combined_batch_metadata(batch: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    metadata = _field(batch, "metadata", None)
    if metadata is not None:
        output.update(_as_mapping(metadata, "batch metadata"))
    camera_metadata = _field(batch, "camera_metadata", None)
    if camera_metadata is not None:
        output.update(_as_mapping(camera_metadata, "batch camera_metadata"))
    return output


def _has_complete_camera_metadata(metadata: Mapping[str, Any]) -> bool:
    return bool(
        "camera_intrinsics" in metadata
        and any(key in metadata for key in ("camera_position_ned", "position_ned"))
        and any(
            key in metadata
            for key in ("rotation_camera_from_ned", "camera_rotation_from_ned")
        )
    )


def _measurement_order(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    raw_order = metadata.get("measurement_order", _CANONICAL_MEASUREMENT_ORDER)
    normalized = tuple(
        _MEASUREMENT_NAME_ALIASES.get(str(value).strip().lower(), str(value).strip().lower())
        for value in raw_order
    )
    if len(normalized) != 6 or set(normalized) != set(_CANONICAL_MEASUREMENT_ORDER):
        raise ValueError("measurement_order must name u,v,xmin,ymin,xmax,ymax exactly once")
    return normalized


def _assert_truth_isolated_transport(payload: Any) -> None:
    assert_anonymous_online_payload(payload)
    violations: list[str] = []
    seen: set[int] = set()

    def visit(value: Any, path: str) -> None:
        if isinstance(value, str):
            if is_truth_like_local_track_id(value):
                violations.append(path)
            return
        if value is None or isinstance(value, (bool, int, float, np.generic, np.ndarray)):
            return
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        if is_dataclass(value) and not isinstance(value, type):
            for item in fields(value):
                visit(getattr(value, item.name), f"{path}.{item.name}")
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(item, f"{path}.{key}")
            return
        if isinstance(value, (list, tuple, set, frozenset)):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if hasattr(value, "__dict__") and not isinstance(value, type):
            visit(vars(value), path)

    visit(payload, "payload")
    if violations:
        raise ValueError(
            "scalable online camera payload contains truth-like identifiers: "
            + ", ".join(sorted(set(violations)))
        )


def _field(value: Any, name: str, default: Any = _MISSING) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    elif hasattr(value, name):
        return getattr(value, name)
    if default is not _MISSING:
        return default
    raise ValueError(f"required field is missing: {name}")


def source_observation_tracklet_links(
    tracklets: Iterable[CameraLocalTracklet],
) -> tuple[SourceObservationTrackletLink, ...]:
    """Export one-to-one frame links without using the key as track identity."""

    links = tuple(
        SourceObservationTrackletLink(
            source_observation_id=tracklet.source_observation_id,
            tracklet_key=tracklet.tracklet_key,
            camera_key=tracklet.camera_key,
            measurement_timestamp=tracklet.measurement_timestamp,
        )
        for tracklet in tracklets
        if tracklet.source_observation_id is not None
    )
    frame_keys = tuple(
        (link.measurement_timestamp, link.source_observation_id)
        for link in links
    )
    if len(frame_keys) != len(set(frame_keys)):
        raise ValueError("one source observation maps to multiple tracklets in one frame")
    return tuple(
        sorted(
            links,
            key=lambda item: (
                item.measurement_timestamp,
                item.camera_key,
                item.source_observation_id,
            ),
        )
    )


def _first_present(
    mapping: Mapping[str, Any],
    names: Sequence[str],
    *,
    default: Any = _MISSING,
) -> Any:
    for name in names:
        value = mapping.get(name)
        if value is not None:
            return value
    if default is not _MISSING:
        return default
    raise ValueError(f"required metadata field is missing: {'/'.join(names)}")


def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _finite_float(value: Any, name: str) -> float:
    output = float(value)
    if not np.isfinite(output):
        raise ValueError(f"{name} must be finite")
    return output


def _finite_array(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    output = np.asarray(value, dtype=float)
    if output.shape != shape or not np.all(np.isfinite(output)):
        raise ValueError(f"{name} must have shape {shape} with finite values")
    return output.copy()


def _positive_semidefinite(
    value: Any,
    shape: tuple[int, int],
    name: str,
) -> np.ndarray:
    output = _finite_array(value, shape, name)
    output = 0.5 * (output + output.T)
    if float(np.min(np.linalg.eigvalsh(output))) < -1.0e-9:
        raise ValueError(f"{name} must be positive semidefinite")
    return output


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _bbox_iou(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    union = _bbox_area(left) + _bbox_area(right) - intersection
    return float(intersection / union) if union > 0.0 else 0.0


__all__ = [
    "Scalable3DAdaptedCameraBatch",
    "Scalable3DAdapterConfig",
    "Scalable3DAssociationResult",
    "Scalable3DStepResult",
    "Scalable3DTerminalAdapter",
    "SourceObservationTrackletLink",
    "global_track3d_to_projection_track",
    "global_tracks3d_to_projection_tracks",
    "run_scalable_3d_online_association",
    "source_observation_tracklet_links",
]
