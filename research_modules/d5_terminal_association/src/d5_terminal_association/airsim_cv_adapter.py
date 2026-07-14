"""AirSim ComputerVision dry-run helpers for D5.

These helpers consume plain Python fixtures that mirror `simGetDetections`
outputs. They do not import AirSim, call simulator APIs, generate assignments,
or alter center-owned global track IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np

from .models import (
    CameraGeometryEvidence,
    CrossViewAssociation,
    LocalVisualTrack,
    ReconImageCue,
    TerminalObservation,
)
from .observation_bus import TerminalObservationBus


DEGRADATION_CASES = {"no_degradation", "degrade_to_secondary", "degrade_to_distributed"}
FIXED_DOWNLOOK_SECONDARY_COVERAGE_MODE = "fixed_downlook_secondary"
MOBILE_RECON_GIMBAL_COVERAGE_MODE = "mobile_recon_gimbal"
MOBILE_HIGH_RECON_CAPABILITY_CLASS = "mobile_high_recon"
SECONDARY_DETECT_REJECTION_REASONS = (
    "not_all_targets_visible",
    "network_union_incomplete",
    "no_global_binding",
    "reacquire_not_grouped",
    "stale_or_missing_recon_cue",
    "projection_invalid",
    "geometry_gate_rejected",
    "predicted_local_track_requires_measured_reacquire",
    "stability_window_failed",
    "secondary_detect_offline_only",
    "registered_to_global_track",
)
AIRSIM_TRUTH_OR_GLOBAL_FIELD_NAMES = {
    "actor_id",
    "actor_name",
    "assigned_global_track_id",
    "global_track_id",
    "name",
    "object_id",
    "object_name",
    "true_global_track_id",
    "truth_global_track_id",
    "truth_id",
}


@dataclass(frozen=True)
class AirSimCVScenarioSpec:
    """Geometry assumptions for an N-v-N ComputerVision stress dry-run.

    The default count remains the historical 5v5 stress baseline. Runtime
    simulations must pass the current drone/target count through their input
    `LocalVisualTrack[]`, `GlobalTrack[]`, and camera collections instead of
    relying on this default.
    """

    interceptor_count: int = 5
    target_count: int = 5
    nominal_target_distance_m: float = 50.0
    target_spacing_m: float = 20.0
    interceptor_camera_spacing_m: float = 20.0
    secondary_recon_height_offset_m: float = 200.0
    secondary_recon_role: str = "tethered_high_recon"
    interceptor_camera_resolution: tuple[int, int] = (1920, 1080)
    secondary_recon_resolution: tuple[int, int] = (3840, 2160)

    def __post_init__(self) -> None:
        if self.interceptor_count <= 0 or self.target_count <= 0:
            raise ValueError("interceptor_count and target_count must be positive")
        if self.nominal_target_distance_m <= 0.0:
            raise ValueError("nominal_target_distance_m must be positive")
        if self.target_spacing_m <= 0.0 or self.interceptor_camera_spacing_m <= 0.0:
            raise ValueError("spacing values must be positive")
        if self.secondary_recon_height_offset_m <= 0.0:
            raise ValueError("secondary_recon_height_offset_m must be positive")
        for name, image_size in (
            ("interceptor_camera_resolution", self.interceptor_camera_resolution),
            ("secondary_recon_resolution", self.secondary_recon_resolution),
        ):
            if len(image_size) != 2 or min(int(image_size[0]), int(image_size[1])) <= 0:
                raise ValueError(f"{name} must be positive (width, height)")


@dataclass(frozen=True)
class TerminalStressMetrics:
    """D5-only metrics for N-v-N multi-camera terminal evidence."""

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


@dataclass(frozen=True)
class SecondaryCameraFrameCoverage:
    """Per-secondary-camera target visibility for one replay frame."""

    frame_id: str
    camera_id: str
    resource_id: str | None
    timestamp: float | None
    active_target_ids: tuple[str, ...]
    active_target_count: int
    visible_target_ids: tuple[str, ...]
    visible_target_count: int
    coverage_ratio: float
    full_view: bool
    coverage_mode: str = FIXED_DOWNLOOK_SECONDARY_COVERAGE_MODE
    capability_class: str | None = None
    cue_source: str | None = None
    cue_position_ned: tuple[float, float, float] | None = None
    look_at_ned: tuple[float, float, float] | None = None
    gimbal_pointing_metadata: dict[str, Any] = field(default_factory=dict)
    cue_pointing_error_m: float | None = None
    cue_pointing_error_rad: float | None = None
    gimbal_track_error_px: float | None = None
    rejection_reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", str(self.frame_id))
        object.__setattr__(self, "camera_id", str(self.camera_id))
        if self.resource_id is not None:
            object.__setattr__(self, "resource_id", str(self.resource_id))
        if self.timestamp is not None:
            object.__setattr__(self, "timestamp", float(self.timestamp))
        object.__setattr__(self, "active_target_ids", tuple(str(item) for item in self.active_target_ids))
        object.__setattr__(self, "active_target_count", int(self.active_target_count))
        object.__setattr__(self, "visible_target_ids", tuple(str(item) for item in self.visible_target_ids))
        object.__setattr__(self, "visible_target_count", int(self.visible_target_count))
        object.__setattr__(self, "coverage_ratio", float(np.clip(self.coverage_ratio, 0.0, 1.0)))
        object.__setattr__(self, "full_view", bool(self.full_view))
        object.__setattr__(self, "coverage_mode", str(self.coverage_mode or FIXED_DOWNLOOK_SECONDARY_COVERAGE_MODE))
        object.__setattr__(self, "capability_class", _optional_string(self.capability_class))
        object.__setattr__(self, "cue_source", _optional_string(self.cue_source))
        object.__setattr__(self, "cue_position_ned", _optional_float_tuple(self.cue_position_ned, 3))
        object.__setattr__(self, "look_at_ned", _optional_float_tuple(self.look_at_ned, 3))
        object.__setattr__(self, "gimbal_pointing_metadata", dict(self.gimbal_pointing_metadata))
        object.__setattr__(self, "cue_pointing_error_m", _optional_float(self.cue_pointing_error_m))
        object.__setattr__(self, "cue_pointing_error_rad", _optional_float(self.cue_pointing_error_rad))
        object.__setattr__(self, "gimbal_track_error_px", _optional_float(self.gimbal_track_error_px))
        object.__setattr__(self, "rejection_reasons", _valid_rejection_reasons(self.rejection_reasons))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class SecondaryNetworkFrameCoverage:
    """Joint target visibility across secondary cameras for one replay frame."""

    frame_id: str
    camera_ids: tuple[str, ...]
    active_target_ids: tuple[str, ...]
    active_target_count: int
    visible_target_ids: tuple[str, ...]
    visible_target_count: int
    coverage_ratio: float
    joint_full_view: bool
    coverage_modes: tuple[str, ...] = ()
    capability_classes: tuple[str, ...] = ()
    cue_sources: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", str(self.frame_id))
        object.__setattr__(self, "camera_ids", tuple(str(item) for item in self.camera_ids))
        object.__setattr__(self, "active_target_ids", tuple(str(item) for item in self.active_target_ids))
        object.__setattr__(self, "active_target_count", int(self.active_target_count))
        object.__setattr__(self, "visible_target_ids", tuple(str(item) for item in self.visible_target_ids))
        object.__setattr__(self, "visible_target_count", int(self.visible_target_count))
        object.__setattr__(self, "coverage_ratio", float(np.clip(self.coverage_ratio, 0.0, 1.0)))
        object.__setattr__(self, "joint_full_view", bool(self.joint_full_view))
        object.__setattr__(self, "coverage_modes", _string_tuple(self.coverage_modes))
        object.__setattr__(self, "capability_classes", _string_tuple(self.capability_classes))
        object.__setattr__(self, "cue_sources", _string_tuple(self.cue_sources))
        object.__setattr__(self, "rejection_reasons", _valid_rejection_reasons(self.rejection_reasons))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class SecondaryDetectFunnelCounts:
    """Counts for the detect-to-cross-view diagnostic funnel."""

    detect_count: int
    local_or_recon_cue_count: int
    terminal_association_count: int
    cross_view_association_count: int
    multi_support_count: int
    rejection_reason_counts: dict[str, int] = field(default_factory=dict)
    breakpoint_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "detect_count", int(self.detect_count))
        object.__setattr__(self, "local_or_recon_cue_count", int(self.local_or_recon_cue_count))
        object.__setattr__(self, "terminal_association_count", int(self.terminal_association_count))
        object.__setattr__(self, "cross_view_association_count", int(self.cross_view_association_count))
        object.__setattr__(self, "multi_support_count", int(self.multi_support_count))
        object.__setattr__(
            self,
            "rejection_reason_counts",
            _valid_rejection_reason_count_map(self.rejection_reason_counts),
        )
        object.__setattr__(self, "breakpoint_reasons", _valid_rejection_reasons(self.breakpoint_reasons))


@dataclass(frozen=True)
class SecondaryVisualCoverageFunnelSummary:
    """D5 diagnostic summary for secondary coverage and association funnel."""

    secondary_single_camera_full_view_frame_rate: float
    secondary_network_joint_full_view_frame_rate: float
    secondary_camera_frame_visible_target_counts: dict[str, dict[str, int]]
    secondary_network_frame_joint_visible_target_counts: dict[str, int]
    secondary_camera_coverage_ratio_mean: dict[str, float]
    secondary_camera_coverage_ratio_min: dict[str, float]
    secondary_single_camera_coverage_ratio_mean: float
    secondary_single_camera_coverage_ratio_min: float
    secondary_network_joint_coverage_ratio_mean: float
    secondary_network_joint_coverage_ratio_min: float
    camera_frames: tuple[SecondaryCameraFrameCoverage, ...]
    network_frames: tuple[SecondaryNetworkFrameCoverage, ...]
    funnel_counts: SecondaryDetectFunnelCounts
    rejection_reason_counts: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "secondary_single_camera_full_view_frame_rate",
            float(np.clip(self.secondary_single_camera_full_view_frame_rate, 0.0, 1.0)),
        )
        object.__setattr__(
            self,
            "secondary_network_joint_full_view_frame_rate",
            float(np.clip(self.secondary_network_joint_full_view_frame_rate, 0.0, 1.0)),
        )
        object.__setattr__(
            self,
            "secondary_camera_frame_visible_target_counts",
            {
                str(camera_id): {str(frame_id): int(count) for frame_id, count in frame_counts.items()}
                for camera_id, frame_counts in self.secondary_camera_frame_visible_target_counts.items()
            },
        )
        object.__setattr__(
            self,
            "secondary_network_frame_joint_visible_target_counts",
            {
                str(frame_id): int(count)
                for frame_id, count in self.secondary_network_frame_joint_visible_target_counts.items()
            },
        )
        object.__setattr__(
            self,
            "secondary_camera_coverage_ratio_mean",
            {str(camera_id): float(np.clip(value, 0.0, 1.0)) for camera_id, value in self.secondary_camera_coverage_ratio_mean.items()},
        )
        object.__setattr__(
            self,
            "secondary_camera_coverage_ratio_min",
            {str(camera_id): float(np.clip(value, 0.0, 1.0)) for camera_id, value in self.secondary_camera_coverage_ratio_min.items()},
        )
        object.__setattr__(
            self,
            "secondary_single_camera_coverage_ratio_mean",
            float(np.clip(self.secondary_single_camera_coverage_ratio_mean, 0.0, 1.0)),
        )
        object.__setattr__(
            self,
            "secondary_single_camera_coverage_ratio_min",
            float(np.clip(self.secondary_single_camera_coverage_ratio_min, 0.0, 1.0)),
        )
        object.__setattr__(
            self,
            "secondary_network_joint_coverage_ratio_mean",
            float(np.clip(self.secondary_network_joint_coverage_ratio_mean, 0.0, 1.0)),
        )
        object.__setattr__(
            self,
            "secondary_network_joint_coverage_ratio_min",
            float(np.clip(self.secondary_network_joint_coverage_ratio_min, 0.0, 1.0)),
        )
        object.__setattr__(self, "camera_frames", tuple(self.camera_frames))
        object.__setattr__(self, "network_frames", tuple(self.network_frames))
        object.__setattr__(
            self,
            "rejection_reason_counts",
            _valid_rejection_reason_count_map(self.rejection_reason_counts),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class CalibrationSeedReadiness:
    """Per-seed D5 field coverage for AirSim calibration reports.

    The summary is a passive audit of already-produced D5 evidence. Offline
    truth labels are counted only from observation metadata and are never used
    to alter terminal association decisions.
    """

    seed_id: str
    observation_count: int
    local_track_count: int
    terminal_association_count: int
    geometry_log_count: int
    measurement_age_count: int
    local_bbox_count: int
    handoff_advisory_count: int
    bbox_stability_count: int
    truth_label_count: int
    duplicate_terminal_lock_risk_count: int
    friend_conflict_count: int
    source_counts: dict[str, int]
    detector_backend_counts: dict[str, int]
    tracker_backend_counts: dict[str, int]
    missing_required_fields: tuple[str, ...] = ()
    missing_recommended_fields: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_count", int(self.observation_count))
        object.__setattr__(self, "local_track_count", int(self.local_track_count))
        object.__setattr__(self, "terminal_association_count", int(self.terminal_association_count))
        object.__setattr__(self, "geometry_log_count", int(self.geometry_log_count))
        object.__setattr__(self, "measurement_age_count", int(self.measurement_age_count))
        object.__setattr__(self, "local_bbox_count", int(self.local_bbox_count))
        object.__setattr__(self, "handoff_advisory_count", int(self.handoff_advisory_count))
        object.__setattr__(self, "bbox_stability_count", int(self.bbox_stability_count))
        object.__setattr__(self, "truth_label_count", int(self.truth_label_count))
        object.__setattr__(
            self,
            "duplicate_terminal_lock_risk_count",
            int(self.duplicate_terminal_lock_risk_count),
        )
        object.__setattr__(self, "friend_conflict_count", int(self.friend_conflict_count))
        object.__setattr__(self, "source_counts", dict(self.source_counts))
        object.__setattr__(self, "detector_backend_counts", dict(self.detector_backend_counts))
        object.__setattr__(self, "tracker_backend_counts", dict(self.tracker_backend_counts))
        object.__setattr__(
            self,
            "missing_required_fields",
            tuple(str(item) for item in self.missing_required_fields),
        )
        object.__setattr__(
            self,
            "missing_recommended_fields",
            tuple(str(item) for item in self.missing_recommended_fields),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def ready(self) -> bool:
        """Whether this seed has the required D5 fields for calibration."""

        return not self.missing_required_fields


@dataclass(frozen=True)
class MultiSeedCalibrationReadiness:
    """Aggregate D5 field coverage across AirSim calibration seeds."""

    seeds: tuple[CalibrationSeedReadiness, ...]
    seed_count: int
    ready_seed_count: int
    total_observation_count: int
    total_terminal_association_count: int
    source_counts: dict[str, int]
    detector_backend_counts: dict[str, int]
    tracker_backend_counts: dict[str, int]
    missing_required_fields_by_seed: dict[str, tuple[str, ...]]
    missing_recommended_fields_by_seed: dict[str, tuple[str, ...]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "seeds", tuple(self.seeds))
        object.__setattr__(self, "seed_count", int(self.seed_count))
        object.__setattr__(self, "ready_seed_count", int(self.ready_seed_count))
        object.__setattr__(self, "total_observation_count", int(self.total_observation_count))
        object.__setattr__(
            self,
            "total_terminal_association_count",
            int(self.total_terminal_association_count),
        )
        object.__setattr__(self, "source_counts", dict(self.source_counts))
        object.__setattr__(self, "detector_backend_counts", dict(self.detector_backend_counts))
        object.__setattr__(self, "tracker_backend_counts", dict(self.tracker_backend_counts))
        object.__setattr__(
            self,
            "missing_required_fields_by_seed",
            {
                str(seed): tuple(str(item) for item in fields)
                for seed, fields in self.missing_required_fields_by_seed.items()
            },
        )
        object.__setattr__(
            self,
            "missing_recommended_fields_by_seed",
            {
                str(seed): tuple(str(item) for item in fields)
                for seed, fields in self.missing_recommended_fields_by_seed.items()
            },
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def ready(self) -> bool:
        """Whether all provided seeds have required D5 calibration fields."""

        return self.seed_count > 0 and self.ready_seed_count == self.seed_count


def local_visual_tracks_from_sim_detections(
    detections: Iterable[Any],
    *,
    resource_id: str,
    camera_id: str,
    timestamp: float,
    arrival_timestamp: float | None = None,
    exposure_timestamp: float | None = None,
    image_size: tuple[int, int] | None = None,
    camera_geometry: CameraGeometryEvidence | None = None,
    detection_source: str = "simGetDetections",
    default_category: str = "unknown",
    default_quality: float = 0.8,
) -> list[LocalVisualTrack]:
    """Convert detection bbox records to `LocalVisualTrack` objects.

    AirSim truth fields such as `object_id` and `actor_name` are intentionally
    ignored here. If a local-ID alias such as `track_id` repeats or embeds an
    AirSim truth/object field as a delimited component, it is treated as truth
    metadata and replaced with a camera-scoped detection ID. Truth labels may
    be carried by callers only as offline evaluation labels outside the online
    association path.
    """

    tracks: list[LocalVisualTrack] = []
    for index, detection in enumerate(detections):
        bbox = _extract_bbox(detection)
        x1, y1, x2, y2 = bbox
        local_id = _online_local_track_id(detection, camera_id=camera_id, index=index)
        category = _online_category_from_detection(detection, default_category=default_category)
        quality = float(_get_any(detection, "confidence", "score", "quality") or default_quality)
        history_length = int(_get_any(detection, "mot_history_length") or 1)
        clip_sides = _bbox_edge_clip_sides(bbox, image_size)
        transition = str(
            _get_any(detection, "track_transition_state", "track_transition")
            or ("continued" if history_length > 1 else "initialized")
        ).lower()
        tracks.append(
            LocalVisualTrack(
                local_track_id=local_id,
                center_px=np.array([(x1 + x2) * 0.5, (y1 + y2) * 0.5], dtype=float),
                bbox=bbox,
                bearing_rate=np.zeros(2, dtype=float),
                category=category,
                quality=quality,
                mot_history_length=history_length,
                timestamp=float(timestamp),
                arrival_timestamp=(
                    float(arrival_timestamp) if arrival_timestamp is not None else float(timestamp)
                ),
                exposure_timestamp=(
                    float(exposure_timestamp) if exposure_timestamp is not None else float(timestamp)
                ),
                detection_source=detection_source,
                track_transition_state=transition,
                track_reset_reason=_get_any(detection, "track_reset_reason"),
                bbox_edge_clipped=bool(clip_sides),
                bbox_edge_clip_sides=clip_sides,
                image_size=image_size,
                camera_geometry=camera_geometry,
                metadata={
                    "resource_id": resource_id,
                    "camera_id": camera_id,
                    "image_size": image_size,
                },
            )
        )
    return tracks


def local_visual_tracks_from_offline_yolo_bytetrack(
    detections: Iterable[Any],
    *,
    resource_id: str,
    camera_id: str,
    timestamp: float | None = None,
    default_category: str = "unknown",
    default_quality: float = 0.8,
    default_mot_history_length: int = 1,
    source_name: str = "offline_yolo_bytetrack",
    arrival_timestamp: float | None = None,
    exposure_timestamp: float | None = None,
    image_size: tuple[int, int] | None = None,
    camera_geometry: CameraGeometryEvidence | None = None,
) -> list[LocalVisualTrack]:
    """Convert offline detector/tracker rows to `LocalVisualTrack`.

    This is a schema adapter only. It does not run YOLO, ByteTrack, BoT-SORT,
    or Deep SORT, and it intentionally ignores AirSim/object truth fields and
    any supplied `global_track_id`. Tracker IDs are namespaced as local IDs and
    never become `assigned_global_track_id`.
    """

    tracks: list[LocalVisualTrack] = []
    seen_local_ids: dict[str, int] = {}
    for index, detection in enumerate(detections):
        bbox = _extract_bbox(detection)
        x1, y1, x2, y2 = bbox
        raw_track_id = _get_any(
            detection,
            "local_track_id",
            "track_id",
            "tracker_id",
            "byte_track_id",
            "bytetrack_id",
            "id",
        )
        if raw_track_id is None:
            base_local_id = f"{camera_id}/{source_name}:det:{index}"
        else:
            base_local_id = f"{camera_id}/{source_name}:track:{raw_track_id}"
        local_id = _unique_local_id(base_local_id, seen_local_ids)
        category = _online_category_from_detection(detection, default_category=default_category)
        quality = float(
            _get_any(detection, "confidence", "conf", "score", "quality")
            or default_quality
        )
        measurement_time = _get_any(detection, "timestamp", "measurement_timestamp", "time")
        track_timestamp = float(timestamp if timestamp is not None else (measurement_time or 0.0))
        history_length = int(
            _get_any(detection, "mot_history_length", "track_age", "age")
            or default_mot_history_length
        )
        clip_sides = _bbox_edge_clip_sides(bbox, image_size)
        tracks.append(
            LocalVisualTrack(
                local_track_id=local_id,
                center_px=np.array([(x1 + x2) * 0.5, (y1 + y2) * 0.5], dtype=float),
                bbox=bbox,
                bearing_rate=np.asarray(
                    _get_any(detection, "bearing_rate", "los_rate_px_s") or (0.0, 0.0),
                    dtype=float,
                ),
                category=category,
                quality=quality,
                mot_history_length=history_length,
                timestamp=track_timestamp,
                arrival_timestamp=(
                    float(arrival_timestamp)
                    if arrival_timestamp is not None
                    else track_timestamp
                ),
                exposure_timestamp=(
                    float(exposure_timestamp)
                    if exposure_timestamp is not None
                    else track_timestamp
                ),
                detection_source=source_name,
                track_transition_state=("continued" if history_length > 1 else "initialized"),
                track_reset_reason=_get_any(detection, "track_reset_reason"),
                bbox_edge_clipped=bool(clip_sides),
                bbox_edge_clip_sides=clip_sides,
                image_size=image_size,
                camera_geometry=camera_geometry,
                metadata={
                    "resource_id": resource_id,
                    "camera_id": camera_id,
                    "image_size": image_size,
                },
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
    image_size: tuple[int, int] | None = None,
    camera_geometry: CameraGeometryEvidence | None = None,
    exposure_timestamp: float | None = None,
) -> list[LocalVisualTrack]:
    """Publish all detections from one AirSim CV camera as local observations."""

    tracks = local_visual_tracks_from_sim_detections(
        detections,
        resource_id=resource_id,
        camera_id=camera_id,
        timestamp=timestamp,
        arrival_timestamp=arrival_timestamp,
        exposure_timestamp=exposure_timestamp,
        image_size=image_size,
        camera_geometry=camera_geometry,
    )
    for track in tracks:
        effective_arrival_timestamp = (
            float(arrival_timestamp) if arrival_timestamp is not None else float(timestamp)
        )
        bus.publish_local_track(
            resource_id=resource_id,
            source_node_id=source_node_id or resource_id,
            link_type="airsim_cv_detection",
            timestamp=timestamp,
            local_track=track,
            camera_id=camera_id,
            frame_id=frame_id,
            arrival_timestamp=arrival_timestamp,
            metadata={
                "source": "simGetDetections",
                "association_source": "geometric_detect",
                "measurement_timestamp": track.timestamp,
                "arrival_timestamp": effective_arrival_timestamp,
                "exposure_timestamp": track.exposure_timestamp,
                "measurement_age_s": max(0.0, effective_arrival_timestamp - track.timestamp),
                "prediction_age_s": None,
                "local_track_state": "measured",
                "mot_history_length": track.mot_history_length,
                "track_transition_state": track.track_transition_state,
                "track_reset_reason": track.track_reset_reason,
                "detection_source": track.detection_source,
                "bbox_edge_clipped": track.bbox_edge_clipped,
                "bbox_edge_clip_sides": list(track.bbox_edge_clip_sides),
                "camera_geometry": (
                    track.camera_geometry.to_metadata()
                    if track.camera_geometry is not None
                    else {
                        "geometry_valid": False,
                        "geometry_source": "unavailable",
                        "geometry_unavailable_reasons": ["camera_geometry_not_provided"],
                    }
                ),
                "truth_identity_used": False,
                "association_rejection_reason": "no_global_binding",
            },
        )
    return tracks


def _bbox_edge_clip_sides(
    bbox: tuple[float, float, float, float],
    image_size: tuple[int, int] | None,
) -> tuple[str, ...]:
    if image_size is None:
        return ()
    width, height = image_size
    if width <= 0 or height <= 0:
        return ()
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


def compute_terminal_stress_metrics(
    observations: Iterable[TerminalObservation],
    cross_view_associations: Iterable[CrossViewAssociation],
    *,
    ambiguity_threshold: float = 0.5,
) -> TerminalStressMetrics:
    """Compute D5-only N-v-N evidence metrics from bus outputs."""

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


def summarize_secondary_visual_coverage_funnel(
    *,
    secondary_frames: Iterable[Any] = (),
    observations: Iterable[TerminalObservation] = (),
    cross_view_associations: Iterable[CrossViewAssociation] | None = None,
    active_target_ids: Iterable[str] = (),
    secondary_camera_ids: Iterable[str] | None = None,
    current_time: float | None = None,
    max_recon_cue_age_s: float = 1.0,
) -> SecondaryVisualCoverageFunnelSummary:
    """Summarize secondary visual coverage and detect-to-cross-view fallout.

    The helper accepts plain replay dicts/dataclasses plus D5 observation DTOs.
    Offline target labels are used only to count "what was visible"; forming
    terminal/cross-view support still requires existing D5 terminal association
    payloads carrying center-owned `assigned_global_track_id` values.
    """

    active_targets = _string_tuple(active_target_ids)
    secondary_camera_filter = _string_set(secondary_camera_ids or ())
    camera_frames = _secondary_camera_frame_coverages(
        tuple(secondary_frames),
        active_target_ids=active_targets,
        secondary_camera_ids=secondary_camera_filter,
    )
    network_frames = _secondary_network_frame_coverages(camera_frames)
    observation_list = tuple(
        observation
        for observation in observations
        if _is_secondary_observation(observation, secondary_camera_filter)
    )
    cross_view = (
        tuple(cross_view_associations)
        if cross_view_associations is not None
        else _cross_view_from_terminal_observations(observation_list)
    )

    rejection_counts: dict[str, int] = {reason: 0 for reason in SECONDARY_DETECT_REJECTION_REASONS}
    for frame in camera_frames:
        for reason in frame.rejection_reasons:
            rejection_counts[reason] += 1
    for frame in network_frames:
        for reason in frame.rejection_reasons:
            rejection_counts[reason] += 1

    funnel_counts = _secondary_detect_funnel_counts(
        camera_frames=camera_frames,
        observations=observation_list,
        cross_view_associations=cross_view,
        rejection_reason_counts=rejection_counts,
        current_time=current_time,
        max_recon_cue_age_s=max_recon_cue_age_s,
    )
    rejection_counts = dict(funnel_counts.rejection_reason_counts)

    per_camera_frame_counts: dict[str, dict[str, int]] = {}
    per_camera_ratios: dict[str, list[float]] = {}
    for frame in camera_frames:
        per_camera_frame_counts.setdefault(frame.camera_id, {})[frame.frame_id] = frame.visible_target_count
        per_camera_ratios.setdefault(frame.camera_id, []).append(frame.coverage_ratio)

    camera_ratio_mean = {
        camera_id: _mean(ratios)
        for camera_id, ratios in per_camera_ratios.items()
    }
    camera_ratio_min = {
        camera_id: min(ratios) if ratios else 0.0
        for camera_id, ratios in per_camera_ratios.items()
    }
    single_ratios = [frame.coverage_ratio for frame in camera_frames]
    network_ratios = [frame.coverage_ratio for frame in network_frames]
    single_full_rate = (
        sum(1 for frame in camera_frames if frame.full_view) / len(camera_frames)
        if camera_frames
        else 0.0
    )
    network_full_rate = (
        sum(1 for frame in network_frames if frame.joint_full_view) / len(network_frames)
        if network_frames
        else 0.0
    )
    coverage_mode_counts = _count_strings(frame.coverage_mode for frame in camera_frames)
    capability_class_counts = _count_strings(frame.capability_class for frame in camera_frames)
    cue_source_counts = _count_strings(frame.cue_source for frame in camera_frames)
    mobile_improved_frames = tuple(
        frame.frame_id
        for frame in network_frames
        if frame.metadata.get("mobile_recon_gimbal_improved_joint_coverage") is True
    )

    return SecondaryVisualCoverageFunnelSummary(
        secondary_single_camera_full_view_frame_rate=single_full_rate,
        secondary_network_joint_full_view_frame_rate=network_full_rate,
        secondary_camera_frame_visible_target_counts=per_camera_frame_counts,
        secondary_network_frame_joint_visible_target_counts={
            frame.frame_id: frame.visible_target_count for frame in network_frames
        },
        secondary_camera_coverage_ratio_mean=camera_ratio_mean,
        secondary_camera_coverage_ratio_min=camera_ratio_min,
        secondary_single_camera_coverage_ratio_mean=_mean(single_ratios),
        secondary_single_camera_coverage_ratio_min=min(single_ratios) if single_ratios else 0.0,
        secondary_network_joint_coverage_ratio_mean=_mean(network_ratios),
        secondary_network_joint_coverage_ratio_min=min(network_ratios) if network_ratios else 0.0,
        camera_frames=camera_frames,
        network_frames=network_frames,
        funnel_counts=funnel_counts,
        rejection_reason_counts=rejection_counts,
        metadata={
            "active_target_ids": active_targets,
            "secondary_camera_ids": tuple(sorted(secondary_camera_filter)),
            "rejection_reason_enum": SECONDARY_DETECT_REJECTION_REASONS,
            "visible_target_scope": "offline_replay_labels_only",
            "global_binding_scope": "terminal_association_assigned_global_track_id",
            "coverage_modes": tuple(sorted(coverage_mode_counts)),
            "coverage_mode_counts": coverage_mode_counts,
            "capability_class_counts": capability_class_counts,
            "cue_source_counts": cue_source_counts,
            "fixed_downlook_secondary_frame_count": coverage_mode_counts.get(
                FIXED_DOWNLOOK_SECONDARY_COVERAGE_MODE,
                0,
            ),
            "mobile_recon_gimbal_frame_count": coverage_mode_counts.get(
                MOBILE_RECON_GIMBAL_COVERAGE_MODE,
                0,
            ),
            "fixed_downlook_secondary_network_joint_full_view_frame_count": sum(
                1
                for frame in network_frames
                if frame.metadata.get("fixed_downlook_secondary_joint_full_view") is True
            ),
            "mobile_recon_gimbal_network_joint_full_view_frame_count": sum(
                1
                for frame in network_frames
                if frame.metadata.get("mobile_recon_gimbal_joint_full_view") is True
            ),
            "mobile_recon_gimbal_improved_joint_coverage_frame_count": len(mobile_improved_frames),
            "mobile_recon_gimbal_improved_frame_ids": mobile_improved_frames,
            "mobile_recon_gimbal_added_target_ids_by_frame": {
                frame.frame_id: frame.metadata.get("mobile_recon_gimbal_added_target_ids", ())
                for frame in network_frames
                if frame.metadata.get("mobile_recon_gimbal_added_target_ids")
            },
            "cue_pointing_error_m_by_camera_frame": {
                f"{frame.frame_id}/{frame.camera_id}": frame.cue_pointing_error_m
                for frame in camera_frames
                if frame.cue_pointing_error_m is not None
            },
            "cue_pointing_error_rad_by_camera_frame": {
                f"{frame.frame_id}/{frame.camera_id}": frame.cue_pointing_error_rad
                for frame in camera_frames
                if frame.cue_pointing_error_rad is not None
            },
            "gimbal_track_error_px_by_camera_frame": {
                f"{frame.frame_id}/{frame.camera_id}": frame.gimbal_track_error_px
                for frame in camera_frames
                if frame.gimbal_track_error_px is not None
            },
        },
    )


def summarize_multiseed_calibration_readiness(
    seed_observations: Mapping[str, Iterable[TerminalObservation]],
    seed_cross_view_associations: Mapping[str, Iterable[CrossViewAssociation]] | None = None,
) -> MultiSeedCalibrationReadiness:
    """Summarize whether D5 outputs carry multi-seed calibration fields.

    Required fields cover the minimum D5 evidence needed to tune geometry gates
    and measurement-age handling. Recommended fields cover YOLO/MOT backend
    metadata, AirSim detect provenance, offline truth labels, duplicate/friend
    conflict evidence, and D7 handoff/bbox-stability advisories.
    """

    cross_view_by_seed = seed_cross_view_associations or {}
    seed_summaries = tuple(
        _calibration_seed_readiness(
            str(seed_id),
            tuple(observations),
            tuple(cross_view_by_seed.get(seed_id, ())),
        )
        for seed_id, observations in seed_observations.items()
    )
    source_counts = _merge_counts(seed.source_counts for seed in seed_summaries)
    detector_backend_counts = _merge_counts(seed.detector_backend_counts for seed in seed_summaries)
    tracker_backend_counts = _merge_counts(seed.tracker_backend_counts for seed in seed_summaries)
    return MultiSeedCalibrationReadiness(
        seeds=seed_summaries,
        seed_count=len(seed_summaries),
        ready_seed_count=sum(1 for seed in seed_summaries if seed.ready),
        total_observation_count=sum(seed.observation_count for seed in seed_summaries),
        total_terminal_association_count=sum(
            seed.terminal_association_count for seed in seed_summaries
        ),
        source_counts=source_counts,
        detector_backend_counts=detector_backend_counts,
        tracker_backend_counts=tracker_backend_counts,
        missing_required_fields_by_seed={
            seed.seed_id: seed.missing_required_fields
            for seed in seed_summaries
            if seed.missing_required_fields
        },
        missing_recommended_fields_by_seed={
            seed.seed_id: seed.missing_recommended_fields
            for seed in seed_summaries
            if seed.missing_recommended_fields
        },
        metadata={
            "required_fields": (
                "terminal_observation",
                "local_visual_track",
                "local_track_bbox",
                "local_track_timestamp",
                "terminal_association",
                "geometry_gate_log",
                "measurement_age_s",
            ),
            "recommended_fields": (
                "airsim_detect_source",
                "yolo_or_mot_backend_metadata",
                "offline_truth_label",
                "bbox_stability_advisory",
                "visual_png_handoff_advisory",
                "duplicate_or_friend_conflict_evidence",
            ),
            "truth_label_scope": "offline_metadata_only",
        },
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


def _calibration_seed_readiness(
    seed_id: str,
    observations: tuple[TerminalObservation, ...],
    cross_view_associations: tuple[CrossViewAssociation, ...],
) -> CalibrationSeedReadiness:
    local_count = 0
    association_count = 0
    geometry_log_count = 0
    measurement_age_count = 0
    bbox_count = 0
    handoff_count = 0
    bbox_stability_count = 0
    truth_count = 0
    duplicate_count = sum(1 for item in cross_view_associations if item.duplicate_terminal_lock_risk)
    friend_count = 0
    source_counts: dict[str, int] = {}
    detector_counts: dict[str, int] = {}
    tracker_counts: dict[str, int] = {}

    for observation in observations:
        _increment(source_counts, _observation_source(observation))
        truth_count += int(_has_offline_truth_label(observation.metadata))

        local = observation.local_track
        if local is not None:
            local_count += 1
            if local.bbox is not None:
                bbox_count += 1

        association = observation.terminal_association
        if association is None:
            continue
        association_count += 1
        if association.friend_conflict_state != "none":
            friend_count += 1
        if association.metadata.get("duplicate_terminal_lock_risk") is True:
            duplicate_count += 1

        detector_backend = association.metadata.get("detector_backend") or observation.metadata.get(
            "detector_backend"
        )
        tracker_backend = association.metadata.get("tracker_backend") or observation.metadata.get(
            "tracker_backend"
        )
        if detector_backend:
            _increment(detector_counts, str(detector_backend))
        if tracker_backend:
            _increment(tracker_counts, str(tracker_backend))

        pair_logs = _association_pair_logs(association)
        if any(_has_geometry_gate_fields(log) for log in pair_logs):
            geometry_log_count += 1
        if any(_has_measurement_age(log) for log in pair_logs) or _has_measurement_age(
            association.metadata
        ):
            measurement_age_count += 1
        if _has_handoff_advisory(association.metadata):
            handoff_count += 1
        if _has_bbox_stability(association.metadata):
            bbox_stability_count += 1

    missing_required: list[str] = []
    if not observations:
        missing_required.append("terminal_observation")
    if local_count == 0:
        missing_required.append("local_visual_track")
    if bbox_count == 0:
        missing_required.append("local_track_bbox")
    if not any(obs.local_track is not None and np.isfinite(obs.local_track.timestamp) for obs in observations):
        missing_required.append("local_track_timestamp")
    if association_count == 0:
        missing_required.append("terminal_association")
    if geometry_log_count == 0:
        missing_required.append("geometry_gate_log")
    if measurement_age_count == 0:
        missing_required.append("measurement_age_s")

    missing_recommended: list[str] = []
    if not any(source in source_counts for source in ("simGetDetections", "airsim_cv_detection")):
        missing_recommended.append("airsim_detect_source")
    if not detector_counts and not tracker_counts:
        missing_recommended.append("yolo_or_mot_backend_metadata")
    if truth_count == 0:
        missing_recommended.append("offline_truth_label")
    if bbox_stability_count == 0:
        missing_recommended.append("bbox_stability_advisory")
    if handoff_count == 0:
        missing_recommended.append("visual_png_handoff_advisory")
    if duplicate_count == 0 and friend_count == 0:
        missing_recommended.append("duplicate_or_friend_conflict_evidence")

    return CalibrationSeedReadiness(
        seed_id=seed_id,
        observation_count=len(observations),
        local_track_count=local_count,
        terminal_association_count=association_count,
        geometry_log_count=geometry_log_count,
        measurement_age_count=measurement_age_count,
        local_bbox_count=bbox_count,
        handoff_advisory_count=handoff_count,
        bbox_stability_count=bbox_stability_count,
        truth_label_count=truth_count,
        duplicate_terminal_lock_risk_count=duplicate_count,
        friend_conflict_count=friend_count,
        source_counts=source_counts,
        detector_backend_counts=detector_counts,
        tracker_backend_counts=tracker_counts,
        missing_required_fields=tuple(missing_required),
        missing_recommended_fields=tuple(missing_recommended),
        metadata={
            "cross_view_association_count": len(cross_view_associations),
            "online_truth_isolation": "truth counted only from TerminalObservation.metadata",
        },
    )


def _secondary_camera_frame_coverages(
    frames: tuple[Any, ...],
    *,
    active_target_ids: tuple[str, ...],
    secondary_camera_ids: set[str],
) -> tuple[SecondaryCameraFrameCoverage, ...]:
    coverages: list[SecondaryCameraFrameCoverage] = []
    for frame_index, frame in enumerate(frames):
        for sample in _iter_secondary_camera_samples(
            frame,
            frame_index=frame_index,
            fallback_active_target_ids=active_target_ids,
            secondary_camera_ids=secondary_camera_ids,
        ):
            frame_id, camera_id, resource_id, timestamp, sample_active_ids, payload = sample
            visible_raw = _visible_target_ids_from_payload(payload)
            active_ids = sample_active_ids or active_target_ids
            active_set = set(active_ids)
            if active_set:
                visible_ids = _unique_strings(item for item in visible_raw if item in active_set)
                full_view = active_set.issubset(set(visible_ids))
                coverage_ratio = len(visible_ids) / len(active_set)
            else:
                visible_ids = _unique_strings(visible_raw)
                full_view = False
                coverage_ratio = 0.0
            rejection_reasons = () if full_view else ("not_all_targets_visible",)
            cue_fields = _secondary_camera_cue_fields(payload, camera_id=camera_id, resource_id=resource_id)
            coverages.append(
                SecondaryCameraFrameCoverage(
                    frame_id=frame_id,
                    camera_id=camera_id,
                    resource_id=resource_id,
                    timestamp=timestamp,
                    active_target_ids=active_ids,
                    active_target_count=len(active_ids),
                    visible_target_ids=visible_ids,
                    visible_target_count=len(visible_ids),
                    coverage_ratio=coverage_ratio,
                    full_view=full_view,
                    coverage_mode=cue_fields["coverage_mode"],
                    capability_class=cue_fields["capability_class"],
                    cue_source=cue_fields["cue_source"],
                    cue_position_ned=cue_fields["cue_position_ned"],
                    look_at_ned=cue_fields["look_at_ned"],
                    gimbal_pointing_metadata=cue_fields["gimbal_pointing_metadata"],
                    cue_pointing_error_m=cue_fields["cue_pointing_error_m"],
                    cue_pointing_error_rad=cue_fields["cue_pointing_error_rad"],
                    gimbal_track_error_px=cue_fields["gimbal_track_error_px"],
                    rejection_reasons=rejection_reasons,
                    metadata={
                        "detection_count": _detection_count_from_payload(payload, len(visible_raw)),
                        "raw_visible_target_count": len(visible_raw),
                        "cue_source": cue_fields["cue_source"],
                        "capability_class": cue_fields["capability_class"],
                        "coverage_mode": cue_fields["coverage_mode"],
                    },
                )
            )
    return tuple(sorted(coverages, key=lambda item: (item.frame_id, item.camera_id)))


def _iter_secondary_camera_samples(
    frame: Any,
    *,
    frame_index: int,
    fallback_active_target_ids: tuple[str, ...],
    secondary_camera_ids: set[str],
) -> tuple[tuple[str, str, str | None, float | None, tuple[str, ...], Any], ...]:
    base_frame_id = str(_get_any(frame, "frame_id", "frame", "id") or f"frame_{frame_index}")
    base_timestamp = _optional_float(_get_any(frame, "timestamp", "measurement_timestamp", "time"))
    base_resource_id = _optional_string(_get_any(frame, "resource_id", "source_node_id", "node_id"))
    base_active_ids = (
        _target_ids_from_value(_get_any(frame, "active_target_ids", "active_targets", "targets"))
        or fallback_active_target_ids
    )
    samples: list[tuple[str, str, str | None, float | None, tuple[str, ...], Any]] = []

    secondary_cameras = _get_any(frame, "secondary_cameras", "secondary_camera_frames")
    if isinstance(secondary_cameras, Mapping):
        for camera_key, payload in secondary_cameras.items():
            camera_id = str(_get_any(payload, "camera_id", "camera_name", "sensor_id") or camera_key)
            resource_id = _optional_string(
                _get_any(payload, "resource_id", "source_node_id", "node_id") or base_resource_id
            )
            if secondary_camera_ids and not _camera_matches_filter(camera_id, resource_id, secondary_camera_ids):
                continue
            samples.append(
                _camera_sample_tuple(
                    payload,
                    frame_id=base_frame_id,
                    camera_id=camera_id,
                    resource_id=resource_id,
                    timestamp=base_timestamp,
                    active_target_ids=base_active_ids,
                )
            )
        return tuple(samples)

    cameras = _get_any(frame, "cameras", "camera_frames")
    if isinstance(cameras, Mapping):
        for camera_key, payload in cameras.items():
            camera_id = str(_get_any(payload, "camera_id", "camera_name", "sensor_id") or camera_key)
            resource_id = _optional_string(
                _get_any(payload, "resource_id", "source_node_id", "node_id") or base_resource_id
            )
            if secondary_camera_ids:
                if not _camera_matches_filter(camera_id, resource_id, secondary_camera_ids):
                    continue
            elif not _is_secondary_payload(payload, camera_id, resource_id):
                continue
            samples.append(
                _camera_sample_tuple(
                    payload,
                    frame_id=base_frame_id,
                    camera_id=camera_id,
                    resource_id=resource_id,
                    timestamp=base_timestamp,
                    active_target_ids=base_active_ids,
                )
            )
        return tuple(samples)

    camera_id = str(
        _get_any(frame, "camera_id", "camera_name", "sensor_id")
        or _get_any(frame, "camera")
        or "secondary_camera"
    )
    resource_id = base_resource_id
    if secondary_camera_ids and not _camera_matches_filter(camera_id, resource_id, secondary_camera_ids):
        return ()
    if not secondary_camera_ids and _get_any(frame, "is_secondary") is False:
        return ()
    return (
        _camera_sample_tuple(
            frame,
            frame_id=base_frame_id,
            camera_id=camera_id,
            resource_id=resource_id,
            timestamp=base_timestamp,
            active_target_ids=base_active_ids,
        ),
    )


def _camera_sample_tuple(
    payload: Any,
    *,
    frame_id: str,
    camera_id: str,
    resource_id: str | None,
    timestamp: float | None,
    active_target_ids: tuple[str, ...],
) -> tuple[str, str, str | None, float | None, tuple[str, ...], Any]:
    payload_timestamp = _get_any(payload, "timestamp", "measurement_timestamp", "time")
    if payload_timestamp is None:
        payload_timestamp = timestamp
    return (
        str(_get_any(payload, "frame_id", "frame", "id") or frame_id),
        str(camera_id),
        _optional_string(_get_any(payload, "resource_id", "source_node_id", "node_id") or resource_id),
        _optional_float(payload_timestamp),
        _target_ids_from_value(_get_any(payload, "active_target_ids", "active_targets", "targets"))
        or active_target_ids,
        payload,
    )


def _secondary_camera_cue_fields(
    payload: Any,
    *,
    camera_id: str,
    resource_id: str | None,
) -> dict[str, Any]:
    gimbal_metadata = _mapping_or_empty(
        _get_any(payload, "gimbal_pointing_metadata", "gimbal_metadata", "pointing_metadata")
    )
    capability_class = _optional_string(
        _get_payload_or_metadata(
            payload,
            gimbal_metadata,
            "capability_class",
            "node_capability_class",
            "capability",
        )
    )
    cue_source = _optional_string(
        _get_payload_or_metadata(
            payload,
            gimbal_metadata,
            "cue_source",
            "track_cue_source",
            "pointing_cue_source",
        )
    )
    coverage_mode = _optional_string(
        _get_payload_or_metadata(
            payload,
            gimbal_metadata,
            "coverage_mode",
            "secondary_coverage_mode",
            "camera_role",
            "mount_mode",
        )
    )
    if coverage_mode is None:
        text = " ".join(
            str(value)
            for value in (
                camera_id,
                resource_id,
                capability_class,
                cue_source,
                _get_any(payload, "role", "source", "source_node_id", "link_type"),
            )
            if value is not None
        ).lower()
        if (
            capability_class == MOBILE_HIGH_RECON_CAPABILITY_CLASS
            or "mobile_recon_gimbal" in text
            or "gimbal" in text
        ):
            coverage_mode = MOBILE_RECON_GIMBAL_COVERAGE_MODE
        else:
            coverage_mode = FIXED_DOWNLOOK_SECONDARY_COVERAGE_MODE
    if coverage_mode == MOBILE_RECON_GIMBAL_COVERAGE_MODE and capability_class is None:
        capability_class = MOBILE_HIGH_RECON_CAPABILITY_CLASS

    return {
        "coverage_mode": coverage_mode,
        "capability_class": capability_class,
        "cue_source": cue_source,
        "cue_position_ned": _optional_float_tuple(
            _get_payload_or_metadata(
                payload,
                gimbal_metadata,
                "cue_position_ned",
                "cue_position",
                "gimbal_position_ned",
                "camera_position_ned",
            ),
            3,
        ),
        "look_at_ned": _optional_float_tuple(
            _get_payload_or_metadata(
                payload,
                gimbal_metadata,
                "look_at_ned",
                "look_at",
                "target_cluster_ned",
                "target_subcluster_ned",
            ),
            3,
        ),
        "gimbal_pointing_metadata": gimbal_metadata,
        "cue_pointing_error_m": _optional_float(
            _get_payload_or_metadata(
                payload,
                gimbal_metadata,
                "cue_pointing_error_m",
                "pointing_error_m",
            )
        ),
        "cue_pointing_error_rad": _optional_float(
            _get_payload_or_metadata(
                payload,
                gimbal_metadata,
                "cue_pointing_error_rad",
                "pointing_error_rad",
            )
        ),
        "gimbal_track_error_px": _optional_float(
            _get_payload_or_metadata(
                payload,
                gimbal_metadata,
                "gimbal_track_error_px",
                "track_error_px",
            )
        ),
    }


def _secondary_network_frame_coverages(
    camera_frames: tuple[SecondaryCameraFrameCoverage, ...],
) -> tuple[SecondaryNetworkFrameCoverage, ...]:
    grouped: dict[str, list[SecondaryCameraFrameCoverage]] = {}
    for frame in camera_frames:
        grouped.setdefault(frame.frame_id, []).append(frame)

    network_frames: list[SecondaryNetworkFrameCoverage] = []
    for frame_id, group in sorted(grouped.items()):
        active_ids = _unique_strings(item for frame in group for item in frame.active_target_ids)
        active_set = set(active_ids)
        visible_ids = _unique_strings(item for frame in group for item in frame.visible_target_ids)
        if active_set:
            visible_in_active = _unique_strings(item for item in visible_ids if item in active_set)
            joint_full_view = active_set.issubset(set(visible_in_active))
            coverage_ratio = len(visible_in_active) / len(active_set)
        else:
            visible_in_active = visible_ids
            joint_full_view = False
            coverage_ratio = 0.0
        fixed_frames = tuple(
            frame for frame in group if frame.coverage_mode == FIXED_DOWNLOOK_SECONDARY_COVERAGE_MODE
        )
        mobile_frames = tuple(
            frame
            for frame in group
            if frame.coverage_mode == MOBILE_RECON_GIMBAL_COVERAGE_MODE
            or frame.capability_class == MOBILE_HIGH_RECON_CAPABILITY_CLASS
        )
        fixed_visible = _unique_strings(item for frame in fixed_frames for item in frame.visible_target_ids)
        mobile_visible = _unique_strings(item for frame in mobile_frames for item in frame.visible_target_ids)
        fixed_visible_in_active = _unique_strings(item for item in fixed_visible if not active_set or item in active_set)
        mobile_visible_in_active = _unique_strings(item for item in mobile_visible if not active_set or item in active_set)
        if active_set:
            fixed_full = active_set.issubset(set(fixed_visible_in_active))
            mobile_full = active_set.issubset(set(mobile_visible_in_active))
            fixed_ratio = len(fixed_visible_in_active) / len(active_set)
            mobile_ratio = len(mobile_visible_in_active) / len(active_set)
        else:
            fixed_full = False
            mobile_full = False
            fixed_ratio = 0.0
            mobile_ratio = 0.0
        mobile_added_ids = _unique_strings(
            item for item in visible_in_active if item not in set(fixed_visible_in_active)
        )
        mobile_improved_joint_coverage = bool(mobile_frames and not fixed_full and joint_full_view)
        rejection_reasons = () if joint_full_view else ("network_union_incomplete",)
        network_frames.append(
            SecondaryNetworkFrameCoverage(
                frame_id=frame_id,
                camera_ids=_unique_strings(frame.camera_id for frame in group),
                active_target_ids=active_ids,
                active_target_count=len(active_ids),
                visible_target_ids=visible_in_active,
                visible_target_count=len(visible_in_active),
                coverage_ratio=coverage_ratio,
                joint_full_view=joint_full_view,
                coverage_modes=_unique_strings(frame.coverage_mode for frame in group),
                capability_classes=_unique_strings(frame.capability_class for frame in group),
                cue_sources=_unique_strings(frame.cue_source for frame in group),
                rejection_reasons=rejection_reasons,
                metadata={
                    "fixed_downlook_secondary_visible_target_ids": fixed_visible_in_active,
                    "mobile_recon_gimbal_visible_target_ids": mobile_visible_in_active,
                    "mobile_recon_gimbal_added_target_ids": mobile_added_ids,
                    "fixed_downlook_secondary_coverage_ratio": fixed_ratio,
                    "mobile_recon_gimbal_coverage_ratio": mobile_ratio,
                    "fixed_downlook_secondary_joint_full_view": fixed_full,
                    "mobile_recon_gimbal_joint_full_view": mobile_full,
                    "mobile_recon_gimbal_improved_joint_coverage": mobile_improved_joint_coverage,
                },
            )
        )
    return tuple(network_frames)


def _secondary_detect_funnel_counts(
    *,
    camera_frames: tuple[SecondaryCameraFrameCoverage, ...],
    observations: tuple[TerminalObservation, ...],
    cross_view_associations: tuple[CrossViewAssociation, ...],
    rejection_reason_counts: dict[str, int],
    current_time: float | None,
    max_recon_cue_age_s: float,
) -> SecondaryDetectFunnelCounts:
    detect_count = sum(
        int(frame.metadata.get("detection_count", frame.visible_target_count))
        for frame in camera_frames
    )
    local_count = sum(1 for observation in observations if observation.local_track is not None)
    recon_cue_count = sum(len(observation.recon_image_cues) for observation in observations)
    association_count = sum(1 for observation in observations if observation.terminal_association is not None)

    if detect_count == 0:
        detect_count = local_count

    for observation in observations:
        association = observation.terminal_association
        has_local_or_cue = observation.local_track is not None or bool(observation.recon_image_cues)
        registration_reasons = _observation_registration_reasons(observation)
        if registration_reasons:
            for reason in registration_reasons:
                rejection_reason_counts[reason] += 1
            continue
        if has_local_or_cue and association is None:
            rejection_reason_counts["no_global_binding"] += 1
            if _has_offline_truth_label(observation.metadata):
                rejection_reason_counts["secondary_detect_offline_only"] += 1
        if has_local_or_cue and not _has_fresh_recon_cue(
            observation,
            current_time=current_time,
            max_age_s=max_recon_cue_age_s,
        ):
            rejection_reason_counts["stale_or_missing_recon_cue"] += 1
        if association is None:
            continue
        if association.decision_state == "reacquire":
            rejection_reason_counts["reacquire_not_grouped"] += 1
        if not association.assigned_global_track_id:
            rejection_reason_counts["no_global_binding"] += 1
        if _association_projection_invalid(association):
            rejection_reason_counts["projection_invalid"] += 1
        elif _association_geometry_gate_rejected(association):
            rejection_reason_counts["geometry_gate_rejected"] += 1

    cross_view_count = len(cross_view_associations)
    multi_support_count = sum(1 for item in cross_view_associations if item.support_count >= 2)
    breakpoint_reasons = tuple(
        reason for reason in SECONDARY_DETECT_REJECTION_REASONS if rejection_reason_counts.get(reason, 0) > 0
    )
    return SecondaryDetectFunnelCounts(
        detect_count=detect_count,
        local_or_recon_cue_count=local_count + recon_cue_count,
        terminal_association_count=association_count,
        cross_view_association_count=cross_view_count,
        multi_support_count=multi_support_count,
        rejection_reason_counts=rejection_reason_counts,
        breakpoint_reasons=breakpoint_reasons,
    )


def _cross_view_from_terminal_observations(
    observations: tuple[TerminalObservation, ...],
) -> tuple[CrossViewAssociation, ...]:
    bus = TerminalObservationBus()
    for observation in observations:
        bus.publish(observation)
    return tuple(bus.cross_view_associations())


def _observation_registration_reasons(observation: TerminalObservation) -> tuple[str, ...]:
    reasons = observation.metadata.get("detect_registration_reject_reasons")
    if reasons is None and observation.terminal_association is not None:
        reasons = observation.terminal_association.metadata.get("detect_registration_reject_reasons")
    if reasons is None:
        return ()
    return _valid_rejection_reasons(reasons)


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


def _association_pair_logs(association: Any) -> tuple[Mapping[str, Any], ...]:
    logs: list[Mapping[str, Any]] = []
    selected = association.metadata.get("selected_pair")
    if isinstance(selected, Mapping):
        logs.append(selected)
    candidates = association.metadata.get("candidate_pair_logs")
    if isinstance(candidates, Iterable) and not isinstance(candidates, (str, bytes, bytearray)):
        logs.extend(item for item in candidates if isinstance(item, Mapping))
    return tuple(logs)


def _has_geometry_gate_fields(log: Mapping[str, Any]) -> bool:
    return all(
        key in log and log[key] is not None
        for key in (
            "projected_px",
            "bbox_center_px",
            "pixel_error_px",
            "mahalanobis_d2",
            "gate_pass",
        )
    )


def _has_measurement_age(metadata: Mapping[str, Any]) -> bool:
    value = metadata.get("measurement_age_s")
    if value is None:
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _has_handoff_advisory(metadata: Mapping[str, Any]) -> bool:
    return (
        "visual_png_handoff_recommended" in metadata
        or "visual_png_gate_pass" in metadata
        or "visual_png_handoff_blockers" in metadata
    )


def _has_bbox_stability(metadata: Mapping[str, Any]) -> bool:
    return "bbox_area_cv" in metadata or "bbox_stable" in metadata


def _has_offline_truth_label(metadata: Mapping[str, Any]) -> bool:
    return (
        metadata.get("truth_global_track_id") is not None
        or metadata.get("true_global_track_id") is not None
    )


def _observation_source(observation: TerminalObservation) -> str:
    source = observation.metadata.get("source")
    if source:
        return str(source)
    return str(observation.link_type)


def _visible_target_ids_from_payload(payload: Any) -> tuple[str, ...]:
    direct = _get_any(
        payload,
        "visible_target_ids",
        "visible_targets",
        "target_ids",
        "offline_target_labels",
        "offline_target_ids",
    )
    if direct is not None:
        return _target_ids_from_value(direct)
    nested = _get_any(payload, "detections", "detects", "tracks", "local_tracks", "observations")
    if nested is not None:
        return _target_ids_from_value(nested)
    if isinstance(payload, (tuple, list)):
        return _target_ids_from_value(payload)
    target_id = _target_id_from_record(payload)
    if target_id is not None:
        return (target_id,)
    return ()


def _target_ids_from_value(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Mapping):
        target_id = _target_id_from_record(value)
        if target_id is not None:
            return (target_id,)
        nested = _get_any(value, "target_ids", "targets", "detections")
        if nested is not None and nested is not value:
            return _target_ids_from_value(nested)
        return ()
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        ids: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item:
                    ids.append(item)
                continue
            target_id = _target_id_from_record(item)
            if target_id is not None:
                ids.append(target_id)
        return _unique_strings(ids)
    target_id = _target_id_from_record(value)
    return (target_id,) if target_id is not None else ()


def _target_id_from_record(record: Any) -> str | None:
    value = _get_any(
        record,
        "target_id",
        "target_label",
        "offline_target_id",
        "offline_target_label",
        "visible_target_id",
        "truth_global_track_id",
        "true_global_track_id",
        "truth_id",
        "object_id",
        "actor_name",
        "name",
        "global_track_id",
        "assigned_global_track_id",
    )
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _detection_count_from_payload(payload: Any, fallback_count: int = 0) -> int:
    nested = _get_any(payload, "detections", "detects", "tracks", "local_tracks", "observations")
    if nested is not None:
        try:
            return len(tuple(nested))
        except TypeError:
            return fallback_count
    direct = _get_any(
        payload,
        "visible_target_ids",
        "visible_targets",
        "target_ids",
        "offline_target_labels",
        "offline_target_ids",
    )
    if direct is not None:
        return len(_target_ids_from_value(direct))
    if _target_id_from_record(payload) is not None or _get_any(payload, "bbox", "bbox_xyxy", "xyxy", "box2D") is not None:
        return 1
    return int(fallback_count)


def _is_secondary_observation(observation: TerminalObservation, secondary_camera_ids: set[str]) -> bool:
    camera_id = observation.camera_id or ""
    resource_id = observation.resource_id or ""
    if secondary_camera_ids:
        return _camera_matches_filter(camera_id, resource_id, secondary_camera_ids)
    text = " ".join(
        str(value)
        for value in (
            observation.resource_id,
            observation.source_node_id,
            observation.link_type,
            observation.camera_id,
            observation.metadata.get("source"),
            observation.metadata.get("role"),
        )
        if value is not None
    ).lower()
    return any(marker in text for marker in ("secondary", "recon", "tethered"))


def _is_secondary_payload(payload: Any, camera_id: str, resource_id: str | None) -> bool:
    if _get_any(payload, "is_secondary") is True:
        return True
    text = " ".join(
        str(value)
        for value in (
            camera_id,
            resource_id,
            _get_any(payload, "role", "source", "source_node_id", "link_type"),
        )
        if value is not None
    ).lower()
    return any(marker in text for marker in ("secondary", "recon", "tethered"))


def _camera_matches_filter(camera_id: str, resource_id: str | None, secondary_camera_ids: set[str]) -> bool:
    if not secondary_camera_ids:
        return False
    camera = str(camera_id)
    resource = str(resource_id) if resource_id is not None else ""
    return (
        camera in secondary_camera_ids
        or resource in secondary_camera_ids
        or (bool(resource) and f"{resource}/{camera}" in secondary_camera_ids)
    )


def _has_fresh_recon_cue(
    observation: TerminalObservation,
    *,
    current_time: float | None,
    max_age_s: float,
) -> bool:
    for cue in observation.recon_image_cues:
        if cue.confidence <= 0.0 or cue.metadata.get("expired") is True:
            continue
        if current_time is not None and current_time - cue.timestamp > max_age_s:
            continue
        return True
    return False


def _association_geometry_gate_rejected(association: Any) -> bool:
    if "geometry_gate_rejected" in str(association.reason):
        return True
    for log in _association_pair_logs(association):
        if log.get("gate_pass") is False:
            return True
    return False


def _association_projection_invalid(association: Any) -> bool:
    if "projection_invalid" in str(association.reason):
        return True
    if association.metadata.get("projection_valid") is False:
        return True
    for log in _association_pair_logs(association):
        if log.get("projection_valid") is False:
            return True
        if "projection_invalid" in str(log.get("reason", "")):
            return True
    return False


def _valid_rejection_reasons(reasons: Iterable[str]) -> tuple[str, ...]:
    if isinstance(reasons, str):
        reasons = (reasons,)
    valid = set(SECONDARY_DETECT_REJECTION_REASONS)
    return tuple(dict.fromkeys(str(reason) for reason in reasons if str(reason) in valid))


def _valid_rejection_reason_count_map(counts: Mapping[str, int]) -> dict[str, int]:
    result = {reason: 0 for reason in SECONDARY_DETECT_REJECTION_REASONS}
    for reason, count in counts.items():
        reason_text = str(reason)
        if reason_text in result:
            result[reason_text] = int(count)
    return result


def _unique_strings(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if value is not None and str(value)))


def _string_tuple(values: Iterable[Any]) -> tuple[str, ...]:
    return _unique_strings(values)


def _string_set(values: Iterable[Any]) -> set[str]:
    return set(_string_tuple(values))


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_float_tuple(value: Any, size: int) -> tuple[float, ...] | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.shape != (size,):
        raise ValueError(f"expected vector with shape ({size},), got {array.shape}")
    return tuple(float(item) for item in array.tolist())


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _get_payload_or_metadata(payload: Any, metadata: Mapping[str, Any], *names: str) -> Any:
    value = _get_any(payload, *names)
    if value is not None:
        return value
    for name in names:
        if name in metadata:
            return metadata[name]
    return None


def _mean(values: Iterable[float]) -> float:
    value_tuple = tuple(float(value) for value in values)
    return sum(value_tuple) / len(value_tuple) if value_tuple else 0.0


def _count_strings(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if value is None:
            continue
        text = str(value)
        if not text:
            continue
        counts[text] = counts.get(text, 0) + 1
    return counts


def _merge_counts(counts: Iterable[Mapping[str, int]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for item in counts:
        for key, value in item.items():
            merged[str(key)] = merged.get(str(key), 0) + int(value)
    return merged


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _online_local_track_id(detection: Any, *, camera_id: str, index: int) -> str:
    candidate = _get_any(detection, "local_track_id", "track_id", "detection_id")
    if candidate is not None and not _matches_airsim_truth_identity(detection, candidate):
        return str(candidate)
    return f"{camera_id}_det_{index}"


def _online_category_from_detection(detection: Any, *, default_category: str) -> str:
    explicit_category = _get_any(detection, "category", "label", "class_name")
    if explicit_category is not None:
        return str(explicit_category)

    class_id = _get_any(detection, "class_id", "cls", "class_index")
    class_names = _get_any(detection, "names", "class_names")
    if class_id is None or class_names is None:
        return str(default_category)

    class_index = int(class_id)
    if isinstance(class_names, Mapping):
        mapped = class_names.get(class_index)
        if mapped is None:
            mapped = class_names.get(str(class_index))
        return str(mapped) if mapped is not None else str(default_category)
    if isinstance(class_names, (list, tuple)) and 0 <= class_index < len(class_names):
        return str(class_names[class_index])
    return str(default_category)


def _matches_airsim_truth_identity(detection: Any, candidate: Any) -> bool:
    candidate_text = str(candidate).strip()
    if not candidate_text:
        return False
    for field_name in AIRSIM_TRUTH_OR_GLOBAL_FIELD_NAMES:
        value = _get_any(detection, field_name)
        if value is None:
            continue
        truth_text = str(value).strip()
        if not truth_text:
            continue
        if candidate_text == truth_text or _contains_delimited_identifier(candidate_text, truth_text):
            return True
    return False


def _contains_delimited_identifier(candidate: str, identifier: str) -> bool:
    """Detect runtime IDs that embed an AirSim truth alias as one component."""

    separators = ":/|#"
    start = 0
    while True:
        index = candidate.find(identifier, start)
        if index < 0:
            return False
        before_ok = index == 0 or candidate[index - 1] in separators
        end = index + len(identifier)
        after_ok = end == len(candidate) or candidate[end] in separators
        if before_ok and after_ok:
            return True
        start = index + 1


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


def _unique_local_id(base_local_id: str, seen_local_ids: dict[str, int]) -> str:
    count = seen_local_ids.get(base_local_id, 0)
    seen_local_ids[base_local_id] = count + 1
    if count == 0:
        return base_local_id
    return f"{base_local_id}#dup{count}"
