"""AirSim ComputerVision dry-run helpers for D5.

These helpers consume plain Python fixtures that mirror `simGetDetections`
outputs. They do not import AirSim, call simulator APIs, generate assignments,
or alter center-owned global track IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np

from .models import CrossViewAssociation, LocalVisualTrack, ReconImageCue, TerminalObservation
from .observation_bus import TerminalObservationBus


DEGRADATION_CASES = {"no_degradation", "degrade_to_secondary", "degrade_to_distributed"}


@dataclass(frozen=True)
class AirSimCVScenarioSpec:
    """Geometry assumptions for the 5v5 ComputerVision dry-run."""

    interceptor_count: int = 5
    target_count: int = 5
    nominal_target_distance_m: float = 50.0
    target_spacing_m: float = 20.0
    interceptor_camera_spacing_m: float = 20.0
    secondary_recon_height_offset_m: float = 200.0
    secondary_recon_role: str = "tethered_high_recon"
    secondary_recon_resolution: tuple[int, int] = (1920, 1080)

    def __post_init__(self) -> None:
        if self.interceptor_count <= 0 or self.target_count <= 0:
            raise ValueError("interceptor_count and target_count must be positive")
        if self.nominal_target_distance_m <= 0.0:
            raise ValueError("nominal_target_distance_m must be positive")
        if self.target_spacing_m <= 0.0 or self.interceptor_camera_spacing_m <= 0.0:
            raise ValueError("spacing values must be positive")
        if self.secondary_recon_height_offset_m <= 0.0:
            raise ValueError("secondary_recon_height_offset_m must be positive")


@dataclass(frozen=True)
class TerminalStressMetrics:
    """D5-only metrics for 5v5 multi-camera terminal evidence."""

    per_camera_detection_count: dict[str, int]
    multi_target_fov_rate: float
    cross_view_overlap_count: int
    duplicate_terminal_lock_risk: bool
    terminal_lock_accuracy: float | None
    ambiguous_fov_event_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "per_camera_detection_count", dict(self.per_camera_detection_count))
        object.__setattr__(self, "multi_target_fov_rate", float(np.clip(self.multi_target_fov_rate, 0.0, 1.0)))
        if self.terminal_lock_accuracy is not None:
            object.__setattr__(
                self,
                "terminal_lock_accuracy",
                float(np.clip(self.terminal_lock_accuracy, 0.0, 1.0)),
            )


@dataclass(frozen=True)
class TerminalEvidenceSummary:
    """D5 evidence case for D4/D6 consumption.

    This is an advisory evidence summary, not an AssignmentPlan.
    """

    case_name: str
    metrics: TerminalStressMetrics
    secondary_evidence_available: bool
    problem_observation_count: int
    cross_view_associations: tuple[CrossViewAssociation, ...] = ()
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.case_name not in DEGRADATION_CASES:
            raise ValueError(f"case_name must be one of {sorted(DEGRADATION_CASES)}")
        object.__setattr__(self, "cross_view_associations", tuple(self.cross_view_associations))
        object.__setattr__(self, "reasons", tuple(str(reason) for reason in self.reasons))
        object.__setattr__(self, "metadata", dict(self.metadata))


def local_visual_tracks_from_sim_detections(
    detections: Iterable[Any],
    *,
    resource_id: str,
    camera_id: str,
    timestamp: float,
    default_category: str = "unknown",
    default_quality: float = 0.8,
) -> list[LocalVisualTrack]:
    """Convert `simGetDetections`-like records to `LocalVisualTrack` objects."""

    tracks: list[LocalVisualTrack] = []
    for index, detection in enumerate(detections):
        bbox = _extract_bbox(detection)
        x1, y1, x2, y2 = bbox
        local_id = str(
            _get_any(detection, "local_track_id", "track_id", "detection_id")
            or f"{camera_id}_det_{index}"
        )
        category = str(_get_any(detection, "category", "label", "class_name") or default_category)
        quality = float(_get_any(detection, "confidence", "score", "quality") or default_quality)
        tracks.append(
            LocalVisualTrack(
                local_track_id=local_id,
                center_px=np.array([(x1 + x2) * 0.5, (y1 + y2) * 0.5], dtype=float),
                bbox=bbox,
                bearing_rate=np.zeros(2, dtype=float),
                category=category,
                quality=quality,
                mot_history_length=int(_get_any(detection, "mot_history_length") or 1),
                timestamp=float(timestamp),
            )
        )
    return tracks


def publish_sim_detections_as_local_observations(
    bus: TerminalObservationBus,
    detections: Iterable[Any],
    *,
    resource_id: str,
    camera_id: str,
    frame_id: str,
    timestamp: float,
    arrival_timestamp: float | None = None,
    source_node_id: str | None = None,
) -> list[LocalVisualTrack]:
    """Publish all detections from one AirSim CV camera as local observations."""

    tracks = local_visual_tracks_from_sim_detections(
        detections,
        resource_id=resource_id,
        camera_id=camera_id,
        timestamp=timestamp,
    )
    for track in tracks:
        bus.publish_local_track(
            resource_id=resource_id,
            source_node_id=source_node_id or resource_id,
            link_type="airsim_cv_detection",
            timestamp=timestamp,
            local_track=track,
            camera_id=camera_id,
            frame_id=frame_id,
            arrival_timestamp=arrival_timestamp,
            metadata={"source": "simGetDetections"},
        )
    return tracks


def compute_terminal_stress_metrics(
    observations: Iterable[TerminalObservation],
    cross_view_associations: Iterable[CrossViewAssociation],
    *,
    ambiguity_threshold: float = 0.5,
) -> TerminalStressMetrics:
    """Compute D5-only 5v5 evidence metrics from bus outputs."""

    observation_list = list(observations)
    cross_view = tuple(cross_view_associations)
    per_camera: dict[str, int] = {}
    for observation in observation_list:
        if observation.local_track is None:
            continue
        key = _camera_key(observation)
        per_camera[key] = per_camera.get(key, 0) + 1

    camera_count = len(per_camera)
    multi_target_count = sum(1 for count in per_camera.values() if count >= 2)
    multi_target_fov_rate = multi_target_count / camera_count if camera_count else 0.0
    cross_view_overlap_count = sum(1 for item in cross_view if item.support_count > 1)
    duplicate_terminal_lock_risk = any(item.duplicate_terminal_lock_risk for item in cross_view)
    ambiguous_fov_event_count = 0
    locked_with_truth = 0
    correct_locked = 0

    for observation in observation_list:
        association = observation.terminal_association
        if association is None:
            continue
        if association.decision_state == "ambiguous" or association.ambiguity_score >= ambiguity_threshold:
            ambiguous_fov_event_count += 1
        truth = observation.metadata.get("truth_global_track_id") or observation.metadata.get("true_global_track_id")
        if association.decision_state == "locked" and truth:
            locked_with_truth += 1
            if association.assigned_global_track_id == truth:
                correct_locked += 1

    terminal_lock_accuracy = (
        correct_locked / locked_with_truth if locked_with_truth else None
    )
    return TerminalStressMetrics(
        per_camera_detection_count=per_camera,
        multi_target_fov_rate=multi_target_fov_rate,
        cross_view_overlap_count=cross_view_overlap_count,
        duplicate_terminal_lock_risk=duplicate_terminal_lock_risk,
        terminal_lock_accuracy=terminal_lock_accuracy,
        ambiguous_fov_event_count=ambiguous_fov_event_count,
    )


def summarize_degradation_case(
    observations: Iterable[TerminalObservation],
    cross_view_associations: Iterable[CrossViewAssociation],
    *,
    current_time: float | None = None,
    max_secondary_cue_age_s: float = 1.0,
    min_problem_observations: int = 2,
) -> TerminalEvidenceSummary:
    """Classify D5 evidence into no/secondary/distributed degradation cases."""

    observation_list = tuple(observations)
    cross_view = tuple(cross_view_associations)
    metrics = compute_terminal_stress_metrics(observation_list, cross_view)
    secondary_available = _secondary_evidence_available(
        observation_list,
        current_time=current_time,
        max_age_s=max_secondary_cue_age_s,
    )
    problem_count, reasons = _problem_observations(observation_list, cross_view)
    has_problem = problem_count >= min_problem_observations or metrics.duplicate_terminal_lock_risk

    if not has_problem:
        case_name = "no_degradation"
    elif secondary_available:
        case_name = "degrade_to_secondary"
    else:
        case_name = "degrade_to_distributed"

    return TerminalEvidenceSummary(
        case_name=case_name,
        metrics=metrics,
        secondary_evidence_available=secondary_available,
        problem_observation_count=problem_count,
        cross_view_associations=cross_view,
        reasons=reasons or ("terminal_evidence_consistent",),
    )


def _extract_bbox(detection: Any) -> tuple[float, float, float, float]:
    bbox = _get_any(detection, "bbox", "bbox_xyxy", "xyxy", "box", "box2d", "box2D")
    if bbox is None:
        raise ValueError("detection must contain bbox or box2D")
    if isinstance(bbox, Mapping):
        if "min" in bbox and "max" in bbox:
            x1, y1 = _xy(bbox["min"])
            x2, y2 = _xy(bbox["max"])
        else:
            x1 = _float_from_any(bbox, "x_min", "xmin", "left", "x1")
            y1 = _float_from_any(bbox, "y_min", "ymin", "top", "y1")
            x2 = _float_from_any(bbox, "x_max", "xmax", "right", "x2")
            y2 = _float_from_any(bbox, "y_max", "ymax", "bottom", "y2")
    elif isinstance(bbox, (tuple, list)) and len(bbox) == 4:
        x1, y1, x2, y2 = (float(value) for value in bbox)
    else:
        min_point = _get_any(bbox, "min")
        max_point = _get_any(bbox, "max")
        if min_point is None or max_point is None:
            raise ValueError("box2D must contain min and max points")
        x1, y1 = _xy(min_point)
        x2, y2 = _xy(max_point)
    if x2 < x1 or y2 < y1:
        raise ValueError("detection bbox must be (x_min, y_min, x_max, y_max)")
    return (float(x1), float(y1), float(x2), float(y2))


def _problem_observations(
    observations: tuple[TerminalObservation, ...],
    cross_view_associations: tuple[CrossViewAssociation, ...],
) -> tuple[int, tuple[str, ...]]:
    count = 0
    reasons: list[str] = []
    for observation in observations:
        association = observation.terminal_association
        if association is None:
            continue
        truth = observation.metadata.get("truth_global_track_id") or observation.metadata.get("true_global_track_id")
        if association.decision_state in {"ambiguous", "hold", "reacquire"}:
            count += 1
            reasons.append(f"{observation.resource_id}:{association.decision_state}")
        elif truth and association.decision_state == "locked" and association.assigned_global_track_id != truth:
            count += 1
            reasons.append(f"{observation.resource_id}:locked_mismatch")
    if any(item.duplicate_terminal_lock_risk for item in cross_view_associations):
        reasons.append("duplicate_terminal_lock_risk")
    return count, tuple(dict.fromkeys(reasons))


def _secondary_evidence_available(
    observations: tuple[TerminalObservation, ...],
    *,
    current_time: float | None,
    max_age_s: float,
) -> bool:
    for observation in observations:
        for cue in observation.recon_image_cues:
            if cue.confidence <= 0.0 or cue.metadata.get("expired") is True:
                continue
            if current_time is not None and current_time - cue.timestamp > max_age_s:
                continue
            return True
    return False


def _camera_key(observation: TerminalObservation) -> str:
    return f"{observation.resource_id}/{observation.camera_id or 'default_camera'}"


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
