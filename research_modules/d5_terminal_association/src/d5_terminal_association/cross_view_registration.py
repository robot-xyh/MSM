"""Geometry-driven detect-to-global-track registration helpers.

This layer converts per-camera `LocalVisualTrack` detections into passive
support for existing center-owned `global_track_id` values. It never creates,
rewrites, or rebinds global IDs; a registration is only emitted when a current
`GlobalTrack` and upstream D2/D3 binding already exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import exp, hypot, isfinite, sqrt
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .associator import (
    AUTHORIZED_ASSIGNMENT_STATES,
    AssociationConfig,
    TerminalAssociator,
    calibration_health_metadata,
)
from .models import (
    Assignment,
    CameraModel,
    CrossViewAssociation,
    GlobalTrack,
    LocalVisualTrack,
    ProjectionResult,
    TerminalAssociation,
    TerminalObservation,
)
from .observation_bus import TerminalObservationBus


REGISTERED_TO_GLOBAL_TRACK_REASON = "registered_to_global_track"
STABILITY_WINDOW_FAILED_REASON = "stability_window_failed"
PROJECTION_INVALID_REASON = "projection_invalid"
DETECT_REGISTRATION_REASONS = (
    "not_all_targets_visible",
    "network_union_incomplete",
    "no_global_binding",
    "reacquire_not_grouped",
    "stale_or_missing_recon_cue",
    PROJECTION_INVALID_REASON,
    "geometry_gate_rejected",
    STABILITY_WINDOW_FAILED_REASON,
    "secondary_detect_offline_only",
    REGISTERED_TO_GLOBAL_TRACK_REASON,
)
CAMERA_POSE_SOURCES = ("airsim_camera_pose", "runtime_guidance_pose", "look_at_fallback")
DEFAULT_STABILITY_WINDOW_FRAMES = 3
DEFAULT_STABILITY_REQUIRED_GATE_PASSES = 2

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


@dataclass(frozen=True)
class GlobalTrackBinding:
    """Existing upstream binding that allows D5 to reference a global track.

    The binding may come from D2's current track table, a D3 assignment, or a
    D4/main replay context. It is an authorization to evaluate evidence only;
    D5 still does not allocate or reassign resources.
    """

    global_track_id: str
    binding_source: str = "d2_d3_binding"
    resource_id: str | None = None
    camera_id: str | None = None
    scoped_resource_ids: tuple[str, ...] = ()
    timestamp: float | None = None
    stale: bool = False
    assignment_version: int | None = None
    plan_id: str | None = None
    plan_version: int | None = None
    authorization_state: str = "authorized"
    coalition_id: str | None = None
    coalition_version: int | None = None
    member_role: str = "primary"
    wave_id: int = 0
    required_resource_count: int = 1
    coordination_mode: str = "independent"
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    activation_state: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.global_track_id:
            raise ValueError("global_track_id must be non-empty")
        object.__setattr__(self, "global_track_id", str(self.global_track_id))
        object.__setattr__(self, "binding_source", str(self.binding_source or "d2_d3_binding"))
        object.__setattr__(self, "resource_id", _optional_string(self.resource_id))
        object.__setattr__(self, "camera_id", _optional_string(self.camera_id))
        object.__setattr__(self, "scoped_resource_ids", _string_tuple(self.scoped_resource_ids))
        if self.timestamp is not None:
            object.__setattr__(self, "timestamp", float(self.timestamp))
        if self.assignment_version is not None:
            object.__setattr__(self, "assignment_version", int(self.assignment_version))
        if self.plan_version is not None:
            object.__setattr__(self, "plan_version", int(self.plan_version))
        object.__setattr__(self, "plan_id", _optional_string(self.plan_id))
        object.__setattr__(self, "authorization_state", str(self.authorization_state or "authorized"))
        object.__setattr__(self, "coalition_id", _optional_string(self.coalition_id))
        if self.coalition_version is not None:
            object.__setattr__(self, "coalition_version", int(self.coalition_version))
        object.__setattr__(self, "member_role", str(self.member_role).strip().lower())
        object.__setattr__(self, "wave_id", int(self.wave_id))
        object.__setattr__(self, "required_resource_count", int(self.required_resource_count))
        if self.required_resource_count < 1:
            raise ValueError("required_resource_count must be at least 1")
        if self.wave_id < 0:
            raise ValueError("wave_id must be non-negative")
        if (self.coalition_id is None) != (self.coalition_version is None):
            raise ValueError("coalition_id and coalition_version must be provided together")
        if (
            self.arrival_window_start_s is not None
            and self.arrival_window_end_s is not None
            and float(self.arrival_window_start_s) > float(self.arrival_window_end_s)
        ):
            raise ValueError("arrival window start must not exceed end")
        object.__setattr__(self, "coordination_mode", str(self.coordination_mode).strip().lower())
        object.__setattr__(self, "activation_state", str(self.activation_state).strip().lower())
        if self.arrival_window_start_s is not None:
            object.__setattr__(self, "arrival_window_start_s", float(self.arrival_window_start_s))
        if self.arrival_window_end_s is not None:
            object.__setattr__(self, "arrival_window_end_s", float(self.arrival_window_end_s))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class CameraLocalTrackBatch:
    """Per-camera detections plus the camera model used for registration."""

    resource_id: str
    camera_id: str
    camera: CameraModel
    local_tracks: tuple[LocalVisualTrack, ...]
    frame_id: str | None = None
    timestamp: float | None = None
    covariance_px: np.ndarray | None = None
    arrival_timestamp: float | None = None
    source_node_id: str | None = None
    link_type: str = "cross_view_registration"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.camera_id:
            raise ValueError("camera_id must be non-empty")
        object.__setattr__(self, "resource_id", str(self.resource_id))
        object.__setattr__(self, "camera_id", str(self.camera_id))
        object.__setattr__(self, "local_tracks", tuple(self.local_tracks))
        object.__setattr__(self, "frame_id", str(self.frame_id or f"{self.resource_id}/{self.camera_id}"))
        if self.timestamp is not None:
            object.__setattr__(self, "timestamp", float(self.timestamp))
        if self.arrival_timestamp is not None:
            object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))
        if self.covariance_px is not None:
            object.__setattr__(self, "covariance_px", _as_matrix(self.covariance_px, (2, 2), "covariance_px"))
        object.__setattr__(self, "source_node_id", _optional_string(self.source_node_id) or self.resource_id)
        object.__setattr__(self, "link_type", str(self.link_type or "cross_view_registration"))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class RegistrationStabilityConfig:
    """Temporal confirmation rule for detect-to-global registration support."""

    window_frames: int = DEFAULT_STABILITY_WINDOW_FRAMES
    required_gate_passes: int = DEFAULT_STABILITY_REQUIRED_GATE_PASSES

    def __post_init__(self) -> None:
        if self.window_frames <= 0:
            raise ValueError("window_frames must be positive")
        if self.required_gate_passes <= 0:
            raise ValueError("required_gate_passes must be positive")
        if self.required_gate_passes > self.window_frames:
            raise ValueError("required_gate_passes cannot exceed window_frames")
        object.__setattr__(self, "window_frames", int(self.window_frames))
        object.__setattr__(self, "required_gate_passes", int(self.required_gate_passes))


@dataclass(frozen=True)
class DetectToGlobalTrackCandidate:
    """One local detect/global-track registration candidate."""

    resource_id: str
    camera_id: str
    frame_id: str
    local_track_id: str
    global_track_id: str | None
    timestamp: float
    mahalanobis_d2: float | None
    gate_passed: bool
    selected: bool
    association_probability: float
    reject_reasons: tuple[str, ...]
    decision_state: str
    outcome: str | None = None
    projected_px: tuple[float, float] | None = None
    bbox_center_px: tuple[float, float] | None = None
    pixel_error_px: float | None = None
    reprojection_error: float | None = None
    covariance_px: np.ndarray | None = None
    projection_valid: bool = False
    camera_pose_source: str = "look_at_fallback"
    calibration_health: str = "unknown"
    drift_warning: bool = False
    bbox_area_px: float | None = None
    offline_truth_global_id: str | None = None
    stable_cross_view_support: bool = False
    stability_pass_count: int = 0
    stability_window_size: int = DEFAULT_STABILITY_WINDOW_FRAMES
    stability_required_passes: int = DEFAULT_STABILITY_REQUIRED_GATE_PASSES
    assignment_version: int | None = None
    binding_source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_id", str(self.resource_id))
        object.__setattr__(self, "camera_id", str(self.camera_id))
        object.__setattr__(self, "frame_id", str(self.frame_id))
        object.__setattr__(self, "local_track_id", str(self.local_track_id))
        object.__setattr__(self, "global_track_id", _optional_string(self.global_track_id))
        object.__setattr__(self, "timestamp", float(self.timestamp))
        object.__setattr__(self, "mahalanobis_d2", _finite_or_none(self.mahalanobis_d2))
        object.__setattr__(self, "association_probability", float(np.clip(self.association_probability, 0.0, 1.0)))
        object.__setattr__(self, "reject_reasons", _valid_reason_tuple(self.reject_reasons))
        object.__setattr__(self, "decision_state", str(self.decision_state))
        object.__setattr__(
            self,
            "outcome",
            str(self.outcome or _default_candidate_outcome(self.decision_state, self.reject_reasons)),
        )
        object.__setattr__(self, "projected_px", _optional_pair(self.projected_px))
        object.__setattr__(self, "bbox_center_px", _optional_pair(self.bbox_center_px))
        object.__setattr__(self, "pixel_error_px", _finite_or_none(self.pixel_error_px))
        reprojection_error = _finite_or_none(
            self.reprojection_error if self.reprojection_error is not None else self.pixel_error_px
        )
        object.__setattr__(self, "reprojection_error", reprojection_error)
        if self.covariance_px is not None:
            object.__setattr__(self, "covariance_px", _as_matrix(self.covariance_px, (2, 2), "covariance_px"))
        object.__setattr__(self, "projection_valid", bool(self.projection_valid))
        object.__setattr__(self, "camera_pose_source", _camera_pose_source_value(self.camera_pose_source))
        health = calibration_health_metadata(
            projection_valid=self.projection_valid,
            reprojection_error=self.reprojection_error,
            camera_pose_source=self.camera_pose_source,
        )
        object.__setattr__(self, "calibration_health", str(health["calibration_health"]))
        object.__setattr__(self, "drift_warning", bool(health["drift_warning"]))
        object.__setattr__(self, "bbox_area_px", _finite_or_none(self.bbox_area_px))
        object.__setattr__(self, "offline_truth_global_id", _optional_string(self.offline_truth_global_id))
        object.__setattr__(self, "stable_cross_view_support", bool(self.stable_cross_view_support))
        object.__setattr__(self, "stability_pass_count", int(self.stability_pass_count))
        object.__setattr__(self, "stability_window_size", int(self.stability_window_size))
        object.__setattr__(self, "stability_required_passes", int(self.stability_required_passes))
        if self.assignment_version is not None:
            object.__setattr__(self, "assignment_version", int(self.assignment_version))
        object.__setattr__(self, "binding_source", _optional_string(self.binding_source))
        metadata = _online_metadata(self.metadata)
        metadata.update(
            {
                "pixel_error_px": self.pixel_error_px,
                "reprojection_error": self.reprojection_error,
                "reprojection_error_px": self.reprojection_error,
                "mahalanobis_d2": self.mahalanobis_d2,
                "gate_pass": self.gate_passed,
                "projection_valid": self.projection_valid,
                "camera_pose_source": self.camera_pose_source,
                "camera_pose_source_trusted": health["camera_pose_source_trusted"],
                "calibration_health": self.calibration_health,
                "calibration_health_reason": health["calibration_health_reason"],
                "drift_warning": self.drift_warning,
                "bbox_area_px": self.bbox_area_px,
                "offline_truth_global_id": self.offline_truth_global_id,
                "stable_cross_view_support": self.stable_cross_view_support,
                "stability_pass_count": self.stability_pass_count,
                "stability_window_size": self.stability_window_size,
                "stability_required_passes": self.stability_required_passes,
                "detect_to_global_candidate": True,
                "detect_registration_outcome": self.outcome,
                "detect_registration_reject_reasons": self.reject_reasons,
                "decision_state": self.decision_state,
            }
        )
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True)
class DetectToGlobalTrackRegistrationResult:
    """Registration candidates plus passive cross-view support."""

    candidates: tuple[DetectToGlobalTrackCandidate, ...]
    observations: tuple[TerminalObservation, ...]
    cross_view_associations: tuple[CrossViewAssociation, ...]
    stable_cross_view_associations: tuple[CrossViewAssociation, ...] = ()
    rejection_reason_counts: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "cross_view_associations", tuple(self.cross_view_associations))
        object.__setattr__(self, "stable_cross_view_associations", tuple(self.stable_cross_view_associations))
        object.__setattr__(
            self,
            "rejection_reason_counts",
            _reason_count_map(self.rejection_reason_counts),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class _PairRecord:
    row: int
    col: int
    binding: GlobalTrackBinding
    local_track: LocalVisualTrack
    projection: ProjectionResult
    mahalanobis_d2: float
    covariance_px: np.ndarray | None
    gate_passed: bool
    pixel_error_px: float | None
    projection_valid: bool
    camera_pose_source: str
    bbox_area_px: float | None
    offline_truth_global_id: str | None


def binding_from_assignment(
    assignment: Assignment,
    *,
    camera_id: str | None = None,
    scoped_resource_ids: Iterable[str] = (),
    binding_source: str = "d3_assignment",
    stale: bool = False,
) -> GlobalTrackBinding:
    """Create a registration binding from an existing D3/D4 assignment."""

    return GlobalTrackBinding(
        global_track_id=assignment.assigned_global_track_id,
        binding_source=binding_source,
        resource_id=assignment.resource_id,
        camera_id=camera_id,
        scoped_resource_ids=tuple(scoped_resource_ids),
        timestamp=assignment.timestamp,
        stale=stale,
        assignment_version=assignment.assignment_version,
        plan_id=assignment.plan_id,
        plan_version=assignment.plan_version,
        authorization_state=assignment.authorization_state,
        coalition_id=assignment.coalition_id,
        coalition_version=assignment.coalition_version,
        member_role=assignment.member_role,
        wave_id=assignment.wave_id,
        required_resource_count=assignment.required_resource_count,
        coordination_mode=assignment.coordination_mode,
        arrival_window_start_s=assignment.arrival_window_start_s,
        arrival_window_end_s=assignment.arrival_window_end_s,
        activation_state=assignment.activation_state,
    )


def register_local_visual_tracks_to_global_tracks(
    *,
    global_tracks: Iterable[GlobalTrack],
    camera_batches: Iterable[CameraLocalTrackBatch],
    bindings: Iterable[GlobalTrackBinding | Assignment | Mapping[str, Any] | str] | None = None,
    current_time: float | None = None,
    config: AssociationConfig | None = None,
    max_binding_age_s: float | None = 1.0,
    network_union_complete: bool | None = None,
    stability_config: RegistrationStabilityConfig | None = None,
) -> DetectToGlobalTrackRegistrationResult:
    """Register local detections as support for existing global track IDs.

    `bindings=None` means every supplied `GlobalTrack.global_track_id` is an
    existing upstream binding. Passing an empty iterable means no binding is
    available, so detections remain local-only and report `no_global_binding`.
    """

    cfg = config or AssociationConfig()
    stability = stability_config or RegistrationStabilityConfig()
    track_by_id = {track.global_track_id: track for track in global_tracks}
    binding_list = (
        tuple(
            GlobalTrackBinding(global_track_id=track_id, binding_source="global_track_pool")
            for track_id in track_by_id
        )
        if bindings is None
        else tuple(_normalize_binding(binding) for binding in bindings)
    )

    bus = TerminalObservationBus()
    candidates: list[DetectToGlobalTrackCandidate] = []
    reason_counts = _reason_count_map({})
    assignment_backends: list[str] = []
    associator = TerminalAssociator(config=cfg)

    for batch in camera_batches:
        batch_time = _batch_timestamp(batch, current_time)
        active_bindings, stale_or_missing = _fresh_bindings_for_batch(
            binding_list,
            batch=batch,
            timestamp=batch_time,
            max_binding_age_s=max_binding_age_s,
        )
        active_bindings = tuple(binding for binding in active_bindings if binding.global_track_id in track_by_id)
        batch_candidates, backend = _register_batch(
            batch=batch,
            batch_time=batch_time,
            active_bindings=active_bindings,
            stale_or_missing_binding=stale_or_missing,
            track_by_id=track_by_id,
            associator=associator,
            config=cfg,
            bus=bus,
            reason_counts=reason_counts,
        )
        candidates.extend(batch_candidates)
        if backend is not None:
            assignment_backends.append(backend)

    if network_union_complete is False:
        reason_counts["network_union_incomplete"] += 1

    candidates = _annotate_candidate_stability(candidates, stability)
    _annotate_observation_stability(bus.observations(), candidates, stability)
    cross_view = tuple(bus.cross_view_associations())
    stable_cross_view = _stable_cross_view_associations(bus.observations(), candidates)
    stable_count = sum(1 for item in candidates if item.stable_cross_view_support)
    unstable_selected_count = sum(1 for item in candidates if item.selected and not item.stable_cross_view_support)
    reason_counts[REGISTERED_TO_GLOBAL_TRACK_REASON] = stable_count
    if unstable_selected_count:
        reason_counts[STABILITY_WINDOW_FAILED_REASON] += unstable_selected_count
    return DetectToGlobalTrackRegistrationResult(
        candidates=tuple(candidates),
        observations=bus.observations(),
        cross_view_associations=cross_view,
        stable_cross_view_associations=stable_cross_view,
        rejection_reason_counts=reason_counts,
        metadata={
            "candidate_count": len(candidates),
            "registered_candidate_count": sum(1 for item in candidates if item.selected),
            "stable_registered_candidate_count": stable_count,
            "unstable_registered_candidate_count": unstable_selected_count,
            "global_binding_count": len(binding_list),
            "global_track_count": len(track_by_id),
            "assignment_backends": tuple(dict.fromkeys(assignment_backends)),
            "network_union_complete": network_union_complete,
            "reject_reason_enum": DETECT_REGISTRATION_REASONS,
            "global_id_policy": "existing_global_track_id_support_only",
            "truth_id_online_use": "ignored",
            "camera_pose_source_policy": CAMERA_POSE_SOURCES,
            "stability_window_frames": stability.window_frames,
            "stability_required_gate_passes": stability.required_gate_passes,
            **_calibration_summary_metadata(candidates),
        },
    )


def _register_batch(
    *,
    batch: CameraLocalTrackBatch,
    batch_time: float,
    active_bindings: tuple[GlobalTrackBinding, ...],
    stale_or_missing_binding: bool,
    track_by_id: Mapping[str, GlobalTrack],
    associator: TerminalAssociator,
    config: AssociationConfig,
    bus: TerminalObservationBus,
    reason_counts: dict[str, int],
) -> tuple[list[DetectToGlobalTrackCandidate], str | None]:
    local_tracks = tuple(batch.local_tracks)
    if not local_tracks:
        return [], None

    if not active_bindings:
        reason = "stale_or_missing_recon_cue" if stale_or_missing_binding else "no_global_binding"
        candidates = []
        for local_track in local_tracks:
            reasons = [reason]
            if reason == "no_global_binding" and _has_offline_truth_label(batch, local_track):
                reasons.append("secondary_detect_offline_only")
            _count_reasons(reason_counts, reasons)
            candidates.append(
                _local_only_candidate(
                    batch,
                    local_track,
                    timestamp=batch_time,
                    reasons=tuple(reasons),
                    decision_state="rejected",
                    metadata={"registration_state": "no_fresh_global_binding"},
                )
            )
            _publish_local_only(bus, batch, local_track, batch_time, reasons)
        return candidates, None

    bound_tracks = [track_by_id[binding.global_track_id] for binding in active_bindings]
    projections = associator.project_tracks_to_image(bound_tracks, batch.camera, timestamp=batch_time)
    costs = np.full((len(active_bindings), len(local_tracks)), config.cost_inf, dtype=float)
    pair_records: dict[tuple[int, int], _PairRecord] = {}
    camera_pose_source = _camera_pose_source_from_batch(batch)

    for row, binding in enumerate(active_bindings):
        projection = projections[binding.global_track_id]
        for col, local_track in enumerate(local_tracks):
            bbox_area_px = _bbox_area_px_for_track(batch, local_track)
            additional_covariance_px = _adaptive_or_fallback_covariance_px(
                batch,
                local_track,
                bbox_area_px,
            )
            d2, covariance_px = _mahalanobis_d2_with_covariance(
                local_track.center_px,
                projection,
                additional_covariance_px,
            )
            gate_passed = projection.valid and isfinite(d2) and d2 <= config.gate_chi2
            if gate_passed:
                costs[row, col] = d2
            pair_records[(row, col)] = _PairRecord(
                row=row,
                col=col,
                binding=binding,
                local_track=local_track,
                projection=projection,
                mahalanobis_d2=d2,
                covariance_px=covariance_px,
                gate_passed=gate_passed,
                pixel_error_px=_pixel_error_px(local_track, projection),
                projection_valid=projection.valid,
                camera_pose_source=camera_pose_source,
                bbox_area_px=bbox_area_px,
                offline_truth_global_id=_offline_truth_global_id(batch, local_track),
            )

    selected_pairs, backend = _unique_assignment(costs, config.cost_inf)
    selected_set = set(selected_pairs)
    selected_cols = {col for _, col in selected_pairs}
    probability_by_pair = _candidate_probabilities(pair_records.values())
    candidates: list[DetectToGlobalTrackCandidate] = []

    for key, record in sorted(pair_records.items()):
        selected = key in selected_set
        reasons: tuple[str, ...]
        if selected:
            reasons = (REGISTERED_TO_GLOBAL_TRACK_REASON,)
        elif record.gate_passed:
            reasons = ()
        else:
            reasons = _pair_reject_reasons(record)
        candidates.append(
            _pair_candidate(
                batch,
                record,
                timestamp=batch_time,
                selected=selected,
                probability=probability_by_pair.get(key, 0.0),
                reasons=reasons,
            )
        )

    for col, local_track in enumerate(local_tracks):
        if col in selected_cols:
            row = next(row for row, selected_col in selected_pairs if selected_col == col)
            record = pair_records[(row, col)]
            _count_reasons(reason_counts, (REGISTERED_TO_GLOBAL_TRACK_REASON,))
            _publish_registered(bus, batch, record, batch_time, costs, active_bindings, config, probability_by_pair)
            continue

        gated_candidates = [record for (row, candidate_col), record in pair_records.items() if candidate_col == col and record.gate_passed]
        if gated_candidates:
            _publish_local_only(
                bus,
                batch,
                local_track,
                batch_time,
                (),
                metadata={"registration_state": "jpda_candidate_not_selected"},
            )
            continue

        rejected_reasons = _local_reject_reasons_for_col(pair_records, col)
        _count_reasons(reason_counts, rejected_reasons)
        _publish_local_only(
            bus,
            batch,
            local_track,
            batch_time,
            rejected_reasons,
            metadata={"registration_state": "all_geometry_gates_rejected"},
        )

    return candidates, backend


def _publish_registered(
    bus: TerminalObservationBus,
    batch: CameraLocalTrackBatch,
    record: _PairRecord,
    timestamp: float,
    costs: np.ndarray,
    active_bindings: Sequence[GlobalTrackBinding],
    config: AssociationConfig,
    probability_by_pair: Mapping[tuple[int, int], float],
) -> None:
    binding = record.binding
    local_track = record.local_track
    confidence = _registration_confidence(record.mahalanobis_d2, local_track)
    margin = _assignment_margin(costs, record.row, record.col)
    ambiguity = 0.0 if margin == float("inf") else 1.0 / (1.0 + max(0.0, margin))
    candidate_costs = [
        (active_bindings[active_row].global_track_id, float(costs[active_row, record.col]))
        for active_row in range(costs.shape[0])
        if isfinite(float(costs[active_row, record.col]))
    ]
    calibration = calibration_health_metadata(
        projection_valid=record.projection_valid,
        reprojection_error=record.pixel_error_px,
        camera_pose_source=record.camera_pose_source,
        good_error_px=config.calibration_good_reprojection_error_px,
        warn_error_px=config.calibration_warn_reprojection_error_px,
        drift_error_px=config.calibration_drift_reprojection_error_px,
        trusted_camera_pose_sources=config.trusted_camera_pose_sources,
    )
    metadata = {
        "detect_to_global_track_registration": True,
        "detect_to_global_candidate": True,
        "detect_registration_outcome": "candidate",
        "detect_registration_reject_reasons": (REGISTERED_TO_GLOBAL_TRACK_REASON,),
        "measurement_timestamp": timestamp,
        "arrival_timestamp": batch.arrival_timestamp,
        "local_track_timestamp": local_track.timestamp,
        "measurement_age_s": _measurement_age_s(local_track, timestamp),
        "mahalanobis_d2": _finite_or_none(record.mahalanobis_d2),
        "association_probability": probability_by_pair.get((record.row, record.col), 0.0),
        "gate_chi2": float(config.gate_chi2),
        "gate_pass": True,
        "projected_px": _projection_pixel_list(record.projection),
        "bbox_center_px": _vector_list(local_track.center_px),
        "pixel_error_px": _finite_or_none(record.pixel_error_px),
        "reprojection_error": _finite_or_none(record.pixel_error_px),
        "reprojection_error_px": _finite_or_none(record.pixel_error_px),
        "projection_valid": record.projection_valid,
        "projection_reason": record.projection.reason,
        "projection_depth_m": float(record.projection.depth),
        "covariance_px": _matrix_list(record.covariance_px),
        "projection_covariance_px": _matrix_list(record.projection.covariance_px),
        "camera_pose_source": record.camera_pose_source,
        "camera_pose_source_trusted": calibration["camera_pose_source_trusted"],
        "calibration_health": calibration["calibration_health"],
        "calibration_health_reason": calibration["calibration_health_reason"],
        "drift_warning": calibration["drift_warning"],
        "bbox_area_px": _finite_or_none(record.bbox_area_px),
        "binding_source": binding.binding_source,
        "plan_id": binding.plan_id,
        "plan_version": binding.plan_version,
        "coalition_id": binding.coalition_id,
        "coalition_version": binding.coalition_version,
        "member_role": binding.member_role,
        "wave_id": binding.wave_id,
        "required_resource_count": binding.required_resource_count,
        "coordination_mode": binding.coordination_mode,
        "arrival_window_start_s": binding.arrival_window_start_s,
        "arrival_window_end_s": binding.arrival_window_end_s,
        "activation_state": binding.activation_state,
        "global_id_policy": "existing_global_track_id_support_only",
        "truth_id_online_use": "ignored",
        "registration_stability_state": "candidate",
        "stable_cross_view_support": False,
        "stability_pass_count": 0,
    }
    association = TerminalAssociation(
        assigned_global_track_id=binding.global_track_id,
        local_track_id=local_track.local_track_id,
        association_confidence=confidence,
        ambiguity_score=ambiguity,
        friend_conflict_state="none",
        decision_state="registered",
        assignment_version=(
            binding.assignment_version
            if binding.assignment_version is not None
            else 0
        ),
        reason=REGISTERED_TO_GLOBAL_TRACK_REASON,
        candidate_costs=sorted(candidate_costs, key=lambda item: item[1]),
        recon_cue_used=False,
        metadata=metadata,
        plan_id=binding.plan_id,
        plan_version=binding.plan_version,
        authorization_state=binding.authorization_state,
        resource_id=batch.resource_id,
        coalition_id=binding.coalition_id,
        coalition_version=binding.coalition_version,
        member_role=binding.member_role,
        wave_id=binding.wave_id,
        required_resource_count=binding.required_resource_count,
        coordination_mode=binding.coordination_mode,
        arrival_window_start_s=binding.arrival_window_start_s,
        arrival_window_end_s=binding.arrival_window_end_s,
        activation_state=binding.activation_state,
    )
    bus.publish_terminal_association(
        resource_id=batch.resource_id,
        source_node_id=batch.source_node_id or batch.resource_id,
        link_type=batch.link_type,
        timestamp=timestamp,
        terminal_association=association,
        local_track=local_track,
        camera_id=batch.camera_id,
        frame_id=batch.frame_id,
        arrival_timestamp=batch.arrival_timestamp,
        metadata={
            "detect_to_global_track_registration": True,
            "detect_to_global_candidate": True,
            "detect_registration_outcome": "candidate",
            "detect_registration_reject_reasons": (REGISTERED_TO_GLOBAL_TRACK_REASON,),
            "measurement_timestamp": timestamp,
            "arrival_timestamp": batch.arrival_timestamp,
            "local_track_timestamp": local_track.timestamp,
            "measurement_age_s": _measurement_age_s(local_track, timestamp),
            "binding_source": binding.binding_source,
            "pixel_error_px": _finite_or_none(record.pixel_error_px),
            "reprojection_error": _finite_or_none(record.pixel_error_px),
            "reprojection_error_px": _finite_or_none(record.pixel_error_px),
            "mahalanobis_d2": _finite_or_none(record.mahalanobis_d2),
            "gate_pass": True,
            "projection_valid": record.projection_valid,
            "projection_reason": record.projection.reason,
            "projection_depth_m": float(record.projection.depth),
            "covariance_px": _matrix_list(record.covariance_px),
            "projection_covariance_px": _matrix_list(record.projection.covariance_px),
            "camera_pose_source": record.camera_pose_source,
            "camera_pose_source_trusted": calibration["camera_pose_source_trusted"],
            "calibration_health": calibration["calibration_health"],
            "calibration_health_reason": calibration["calibration_health_reason"],
            "drift_warning": calibration["drift_warning"],
            "bbox_area_px": _finite_or_none(record.bbox_area_px),
            "registration_stability_state": "candidate",
            "stable_cross_view_support": False,
            "stability_pass_count": 0,
            "truth_id_online_use": "ignored",
        },
    )


def _publish_local_only(
    bus: TerminalObservationBus,
    batch: CameraLocalTrackBatch,
    local_track: LocalVisualTrack,
    timestamp: float,
    reasons: Sequence[str],
    metadata: Mapping[str, Any] | None = None,
) -> None:
    merged = {
        "detect_to_global_track_registration": True,
        "detect_to_global_candidate": True,
        "detect_registration_outcome": _outcome_from_reasons(reasons),
        "detect_registration_reject_reasons": tuple(reasons),
        "measurement_timestamp": timestamp,
        "arrival_timestamp": batch.arrival_timestamp,
        "local_track_timestamp": local_track.timestamp,
        "measurement_age_s": _measurement_age_s(local_track, timestamp),
        "truth_id_online_use": "ignored",
    }
    if metadata:
        merged.update(_online_metadata(metadata))
    bus.publish_local_track(
        resource_id=batch.resource_id,
        source_node_id=batch.source_node_id or batch.resource_id,
        link_type=batch.link_type,
        timestamp=timestamp,
        local_track=local_track,
        camera_id=batch.camera_id,
        frame_id=batch.frame_id,
        arrival_timestamp=batch.arrival_timestamp,
        metadata=merged,
    )


def _normalize_binding(binding: GlobalTrackBinding | Assignment | Mapping[str, Any] | str) -> GlobalTrackBinding:
    if isinstance(binding, GlobalTrackBinding):
        return binding
    if isinstance(binding, Assignment):
        return binding_from_assignment(binding)
    if isinstance(binding, str):
        return GlobalTrackBinding(global_track_id=binding, binding_source="global_track_id")
    if isinstance(binding, Mapping):
        global_track_id = (
            binding.get("global_track_id")
            or binding.get("assigned_global_track_id")
            or binding.get("target_id")
        )
        if global_track_id is None:
            raise ValueError(
                "binding mapping must include global_track_id, assigned_global_track_id, or target_id"
            )
        return GlobalTrackBinding(
            global_track_id=str(global_track_id),
            binding_source=str(binding.get("binding_source", binding.get("source", "d2_d3_binding"))),
            resource_id=_optional_string(binding.get("resource_id")),
            camera_id=_optional_string(binding.get("camera_id")),
            scoped_resource_ids=_string_tuple(binding.get("scoped_resource_ids", ())),
            timestamp=_optional_float(binding.get("timestamp")),
            stale=bool(binding.get("stale", binding.get("assigned_global_track_stale", False))),
            assignment_version=_optional_int(binding.get("assignment_version")),
            plan_id=_optional_string(binding.get("plan_id")),
            plan_version=_optional_int(binding.get("plan_version")),
            authorization_state=str(binding.get("authorization_state", "authorized")),
            coalition_id=_optional_string(binding.get("coalition_id")),
            coalition_version=_optional_int(binding.get("coalition_version")),
            member_role=str(binding.get("member_role", "primary")),
            wave_id=int(binding.get("wave_id", 0)),
            required_resource_count=int(binding.get("required_resource_count", 1)),
            coordination_mode=str(binding.get("coordination_mode", "independent")),
            arrival_window_start_s=_optional_float(binding.get("arrival_window_start_s")),
            arrival_window_end_s=_optional_float(binding.get("arrival_window_end_s")),
            activation_state=str(binding.get("activation_state", binding.get("binding_state", "active"))),
            metadata=_online_metadata(binding.get("metadata", {})),
        )
    raise TypeError(f"unsupported binding type: {type(binding)!r}")


def _fresh_bindings_for_batch(
    bindings: tuple[GlobalTrackBinding, ...],
    *,
    batch: CameraLocalTrackBatch,
    timestamp: float,
    max_binding_age_s: float | None,
) -> tuple[tuple[GlobalTrackBinding, ...], bool]:
    in_scope: list[GlobalTrackBinding] = []
    stale_or_missing = False
    for binding in bindings:
        if binding.camera_id is not None and binding.camera_id != batch.camera_id:
            continue
        if binding.scoped_resource_ids and batch.resource_id not in binding.scoped_resource_ids:
            continue
        in_scope.append(binding)
        if _binding_is_fresh(binding, timestamp=timestamp, max_binding_age_s=max_binding_age_s):
            continue
        stale_or_missing = True

    fresh = tuple(
        binding
        for binding in in_scope
        if _binding_is_fresh(binding, timestamp=timestamp, max_binding_age_s=max_binding_age_s)
    )
    return fresh, bool(stale_or_missing and not fresh)


def _binding_is_fresh(
    binding: GlobalTrackBinding,
    *,
    timestamp: float,
    max_binding_age_s: float | None,
) -> bool:
    if binding.stale:
        return False
    if binding.authorization_state.lower() not in AUTHORIZED_ASSIGNMENT_STATES:
        return False
    if max_binding_age_s is not None and binding.timestamp is not None and binding.timestamp > 0.0:
        age_s = float(timestamp) - float(binding.timestamp)
        if age_s < -1e-9 or age_s > max_binding_age_s:
            return False
    return True


def _batch_timestamp(batch: CameraLocalTrackBatch, current_time: float | None) -> float:
    if current_time is not None:
        return float(current_time)
    if batch.timestamp is not None:
        return float(batch.timestamp)
    if batch.local_tracks:
        return max(float(track.timestamp) for track in batch.local_tracks)
    return 0.0


def _mahalanobis_d2_with_covariance(
    pixel: np.ndarray,
    projection: ProjectionResult,
    additional_covariance_px: np.ndarray | None,
) -> tuple[float, np.ndarray | None]:
    if not projection.valid or projection.pixel is None or projection.covariance_px is None:
        return float("inf"), None
    covariance = projection.covariance_px.copy()
    if additional_covariance_px is not None:
        covariance = covariance + additional_covariance_px
    residual = np.asarray(pixel, dtype=float).reshape(2) - projection.pixel
    value = float(residual.T @ np.linalg.pinv(covariance) @ residual)
    if not isfinite(value):
        return float("inf"), covariance
    return value, covariance


def _unique_assignment(costs: np.ndarray, cost_inf: float) -> tuple[tuple[tuple[int, int], ...], str]:
    if costs.size == 0:
        return (), "empty"
    try:
        from scipy.optimize import linear_sum_assignment  # type: ignore

        rows, cols = linear_sum_assignment(costs)
        return (
            tuple(
                (int(row), int(col))
                for row, col in zip(rows, cols)
                if isfinite(float(costs[row, col])) and float(costs[row, col]) < cost_inf
            ),
            "scipy_hungarian",
        )
    except Exception:
        return _greedy_unique_assignment(costs, cost_inf), "greedy_unique_with_jpda_candidates"


def _greedy_unique_assignment(costs: np.ndarray, cost_inf: float) -> tuple[tuple[int, int], ...]:
    candidates: list[tuple[float, int, int]] = []
    for row in range(costs.shape[0]):
        for col in range(costs.shape[1]):
            value = float(costs[row, col])
            if isfinite(value) and value < cost_inf:
                candidates.append((value, row, col))
    assigned_rows: set[int] = set()
    assigned_cols: set[int] = set()
    selected: list[tuple[int, int]] = []
    for _, row, col in sorted(candidates):
        if row in assigned_rows or col in assigned_cols:
            continue
        assigned_rows.add(row)
        assigned_cols.add(col)
        selected.append((row, col))
    return tuple(selected)


def _candidate_probabilities(records: Iterable[_PairRecord]) -> dict[tuple[int, int], float]:
    by_col: dict[int, list[_PairRecord]] = {}
    for record in records:
        if record.gate_passed and isfinite(record.mahalanobis_d2):
            by_col.setdefault(record.col, []).append(record)
    probabilities: dict[tuple[int, int], float] = {}
    for col, col_records in by_col.items():
        weights = [exp(-0.5 * min(100.0, record.mahalanobis_d2)) for record in col_records]
        total = sum(weights)
        if total <= 0.0:
            continue
        for record, weight in zip(col_records, weights):
            probabilities[(record.row, col)] = weight / total
    return probabilities


def _pair_candidate(
    batch: CameraLocalTrackBatch,
    record: _PairRecord,
    *,
    timestamp: float,
    selected: bool,
    probability: float,
    reasons: tuple[str, ...],
) -> DetectToGlobalTrackCandidate:
    projection = record.projection
    decision_state = "registered" if selected else "candidate" if record.gate_passed else "rejected"
    outcome = _candidate_outcome(
        selected=selected,
        gate_passed=record.gate_passed,
        reasons=reasons,
    )
    calibration = calibration_health_metadata(
        projection_valid=projection.valid,
        reprojection_error=record.pixel_error_px,
        camera_pose_source=record.camera_pose_source,
    )
    return DetectToGlobalTrackCandidate(
        resource_id=batch.resource_id,
        camera_id=batch.camera_id,
        frame_id=batch.frame_id or f"{batch.resource_id}/{batch.camera_id}",
        local_track_id=record.local_track.local_track_id,
        global_track_id=record.binding.global_track_id,
        timestamp=timestamp,
        mahalanobis_d2=record.mahalanobis_d2,
        gate_passed=record.gate_passed,
        selected=selected,
        association_probability=probability,
        reject_reasons=reasons,
        decision_state=decision_state,
        outcome=outcome,
        projected_px=_projection_pixel_tuple(projection),
        bbox_center_px=_vector_tuple(record.local_track.center_px),
        pixel_error_px=record.pixel_error_px,
        reprojection_error=record.pixel_error_px,
        covariance_px=record.covariance_px,
        projection_valid=record.projection_valid,
        camera_pose_source=record.camera_pose_source,
        calibration_health=calibration["calibration_health"],
        drift_warning=calibration["drift_warning"],
        bbox_area_px=record.bbox_area_px,
        offline_truth_global_id=record.offline_truth_global_id,
        assignment_version=record.binding.assignment_version,
        binding_source=record.binding.binding_source,
        metadata={
            "projection_valid": projection.valid,
            "projection_reason": projection.reason,
            "projection_depth_m": float(projection.depth),
            "measurement_timestamp": timestamp,
            "arrival_timestamp": batch.arrival_timestamp,
            "local_track_timestamp": record.local_track.timestamp,
            "measurement_age_s": _measurement_age_s(record.local_track, timestamp),
            "covariance_px": _matrix_list(record.covariance_px),
            "projection_covariance_px": _matrix_list(projection.covariance_px),
            "gate_pass": record.gate_passed,
            "camera_pose_source": record.camera_pose_source,
            "camera_pose_source_trusted": calibration["camera_pose_source_trusted"],
            "calibration_health": calibration["calibration_health"],
            "calibration_health_reason": calibration["calibration_health_reason"],
            "drift_warning": calibration["drift_warning"],
            "reprojection_error": _finite_or_none(record.pixel_error_px),
            "reprojection_error_px": _finite_or_none(record.pixel_error_px),
            "bbox_area_px": _finite_or_none(record.bbox_area_px),
            "offline_truth_global_id": record.offline_truth_global_id,
            "binding_source": record.binding.binding_source,
            "truth_id_online_use": "ignored",
            "global_id_policy": "existing_global_track_id_support_only",
        },
    )


def _local_only_candidate(
    batch: CameraLocalTrackBatch,
    local_track: LocalVisualTrack,
    *,
    timestamp: float,
    reasons: tuple[str, ...],
    decision_state: str,
    metadata: Mapping[str, Any],
) -> DetectToGlobalTrackCandidate:
    bbox_area_px = _bbox_area_px_for_track(batch, local_track)
    camera_pose_source = _camera_pose_source_from_batch(batch)
    calibration = calibration_health_metadata(
        projection_valid=False,
        reprojection_error=None,
        camera_pose_source=camera_pose_source,
    )
    return DetectToGlobalTrackCandidate(
        resource_id=batch.resource_id,
        camera_id=batch.camera_id,
        frame_id=batch.frame_id or f"{batch.resource_id}/{batch.camera_id}",
        local_track_id=local_track.local_track_id,
        global_track_id=None,
        timestamp=timestamp,
        mahalanobis_d2=None,
        gate_passed=False,
        selected=False,
        association_probability=0.0,
        reject_reasons=reasons,
        decision_state=decision_state,
        outcome=_outcome_from_reasons(reasons),
        bbox_center_px=_vector_tuple(local_track.center_px),
        projection_valid=False,
        camera_pose_source=camera_pose_source,
        calibration_health=calibration["calibration_health"],
        drift_warning=calibration["drift_warning"],
        bbox_area_px=bbox_area_px,
        offline_truth_global_id=_offline_truth_global_id(batch, local_track),
        metadata={
            **metadata,
            "gate_pass": False,
            "projection_valid": False,
            "measurement_timestamp": timestamp,
            "arrival_timestamp": batch.arrival_timestamp,
            "local_track_timestamp": local_track.timestamp,
            "measurement_age_s": _measurement_age_s(local_track, timestamp),
            "camera_pose_source": camera_pose_source,
            "camera_pose_source_trusted": calibration["camera_pose_source_trusted"],
            "calibration_health": calibration["calibration_health"],
            "calibration_health_reason": calibration["calibration_health_reason"],
            "drift_warning": calibration["drift_warning"],
            "reprojection_error": None,
            "reprojection_error_px": None,
            "bbox_area_px": _finite_or_none(bbox_area_px),
        },
    )


def _registration_confidence(mahalanobis_d2: float, local_track: LocalVisualTrack) -> float:
    if not isfinite(mahalanobis_d2):
        return 0.0
    geometry_score = exp(-0.5 * min(100.0, mahalanobis_d2))
    history_score = min(1.0, max(0.0, local_track.mot_history_length / 5.0))
    return float(np.clip(geometry_score * local_track.quality * history_score, 0.0, 1.0))


def adaptive_pixel_covariance_px(
    bbox_area_px: float,
    image_size: tuple[int, int],
    *,
    min_sigma_px: float = 25.0,
    max_sigma_px: float = 90.0,
) -> np.ndarray:
    """Return the P1 secondary-camera adaptive detection covariance.

    The formula intentionally depends only on image geometry and bbox scale,
    not on offline truth labels or actor IDs.
    """

    area = max(0.0, float(bbox_area_px))
    width, height = image_size
    image_diag_px = hypot(float(width), float(height))
    sigma = max(float(min_sigma_px), 0.5 * sqrt(area), 0.008 * image_diag_px)
    sigma = float(np.clip(sigma, float(min_sigma_px), float(max_sigma_px)))
    return np.diag([sigma * sigma, sigma * sigma])


def _adaptive_or_fallback_covariance_px(
    batch: CameraLocalTrackBatch,
    local_track: LocalVisualTrack,
    bbox_area_px: float | None,
) -> np.ndarray | None:
    if bbox_area_px is not None and bbox_area_px > 0.0:
        return adaptive_pixel_covariance_px(bbox_area_px, batch.camera.image_size)
    return batch.covariance_px


def _bbox_area_px_for_track(batch: CameraLocalTrackBatch, local_track: LocalVisualTrack) -> float | None:
    if local_track.bbox is not None:
        x1, y1, x2, y2 = local_track.bbox
        return max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))

    for key in (
        "bbox_area_px_by_local_track_id",
        "bbox_area_by_local_track_id",
        "bbox_area_px_by_track_id",
        "bbox_area_by_track_id",
    ):
        values = batch.metadata.get(key)
        if isinstance(values, Mapping) and local_track.local_track_id in values:
            return _optional_positive_float(values[local_track.local_track_id])

    if len(batch.local_tracks) == 1:
        for key in ("bbox_area_px", "bbox_area"):
            if key in batch.metadata:
                return _optional_positive_float(batch.metadata.get(key))
    return None


def _camera_pose_source_from_batch(batch: CameraLocalTrackBatch) -> str:
    direct = batch.metadata.get("camera_pose_source")
    if direct is not None:
        return _camera_pose_source_value(direct)
    if batch.metadata.get("airsim_camera_pose") is not None:
        return "airsim_camera_pose"
    if batch.metadata.get("runtime_guidance_pose") is not None:
        return "runtime_guidance_pose"
    return "look_at_fallback"


def _camera_pose_source_value(value: Any) -> str:
    text = str(value or "").strip()
    if text in CAMERA_POSE_SOURCES:
        return text
    return "look_at_fallback"


def _offline_truth_global_id(batch: CameraLocalTrackBatch, local_track: LocalVisualTrack) -> str | None:
    for key in (
        "offline_truth_by_local_track_id",
        "truth_by_local_track_id",
        "truth_global_track_id_by_local_track_id",
        "true_global_track_id_by_local_track_id",
        "offline_truth_global_id_by_local_track_id",
    ):
        values = batch.metadata.get(key)
        if isinstance(values, Mapping) and local_track.local_track_id in values:
            return _optional_string(values[local_track.local_track_id])
    if len(batch.local_tracks) == 1:
        for key in (
            "offline_truth_global_id",
            "truth_global_track_id",
            "true_global_track_id",
            "truth_id",
        ):
            if key in batch.metadata:
                return _optional_string(batch.metadata.get(key))
    return None


def _annotate_candidate_stability(
    candidates: list[DetectToGlobalTrackCandidate],
    stability: RegistrationStabilityConfig,
) -> list[DetectToGlobalTrackCandidate]:
    history_by_key: dict[tuple[str, str, str, str], list[DetectToGlobalTrackCandidate]] = {}
    annotated: list[DetectToGlobalTrackCandidate] = []
    for candidate in sorted(candidates, key=lambda item: (item.timestamp, item.frame_id, item.resource_id, item.camera_id, item.local_track_id)):
        if candidate.global_track_id is None:
            annotated_candidate = replace(
                candidate,
                stability_window_size=stability.window_frames,
                stability_required_passes=stability.required_gate_passes,
            )
            annotated.append(annotated_candidate)
            continue
        key = _stability_key(candidate)
        window = history_by_key.setdefault(key, [])
        window.append(candidate)
        if len(window) > stability.window_frames:
            del window[: len(window) - stability.window_frames]
        pass_count = sum(1 for item in window if item.selected and item.gate_passed)
        stable = bool(candidate.selected and candidate.gate_passed and pass_count >= stability.required_gate_passes)
        reasons = candidate.reject_reasons
        if candidate.selected and not stable and STABILITY_WINDOW_FAILED_REASON not in reasons:
            reasons = tuple(reason for reason in reasons if reason != REGISTERED_TO_GLOBAL_TRACK_REASON)
            reasons = reasons + (STABILITY_WINDOW_FAILED_REASON,)
        if stable and REGISTERED_TO_GLOBAL_TRACK_REASON not in reasons:
            reasons = tuple(reason for reason in reasons if reason != STABILITY_WINDOW_FAILED_REASON)
            reasons = reasons + (REGISTERED_TO_GLOBAL_TRACK_REASON,)
        decision_state = "registered" if stable else "candidate" if candidate.gate_passed else candidate.decision_state
        outcome = REGISTERED_TO_GLOBAL_TRACK_REASON if stable else _outcome_from_reasons(reasons)
        annotated.append(
            replace(
                candidate,
                reject_reasons=reasons,
                decision_state=decision_state,
                outcome=outcome,
                stable_cross_view_support=stable,
                stability_pass_count=pass_count,
                stability_window_size=stability.window_frames,
                stability_required_passes=stability.required_gate_passes,
            )
        )
    # `replace` creates new objects, so restore original production order by the
    # identifying fields that are unique for this helper's pair-candidate stream.
    index_by_signature = {
        _candidate_signature(candidate): index for index, candidate in enumerate(candidates)
    }
    return sorted(annotated, key=lambda item: index_by_signature.get(_candidate_signature(item), len(candidates)))


def _annotate_observation_stability(
    observations: tuple[TerminalObservation, ...],
    candidates: Sequence[DetectToGlobalTrackCandidate],
    stability: RegistrationStabilityConfig,
) -> None:
    by_signature = {_observation_candidate_signature(candidate): candidate for candidate in candidates}
    for observation in observations:
        association = observation.terminal_association
        if association is None or association.local_track_id is None:
            continue
        key = (
            observation.resource_id,
            observation.camera_id or "",
            observation.frame_id or "",
            association.local_track_id,
            association.assigned_global_track_id,
        )
        candidate = by_signature.get(key)
        if candidate is None:
            continue
        state = "stable" if candidate.stable_cross_view_support else "candidate"
        outcome = (
            REGISTERED_TO_GLOBAL_TRACK_REASON
            if candidate.stable_cross_view_support
            else _outcome_from_reasons(candidate.reject_reasons)
        )
        observation.metadata.update(
            {
                "registration_stability_state": state,
                "stable_cross_view_support": candidate.stable_cross_view_support,
                "stability_pass_count": candidate.stability_pass_count,
                "stability_window_size": stability.window_frames,
                "stability_required_passes": stability.required_gate_passes,
                "detect_registration_outcome": outcome,
                "detect_registration_reject_reasons": candidate.reject_reasons,
            }
        )
        association.metadata.update(
            {
                "registration_stability_state": state,
                "stable_cross_view_support": candidate.stable_cross_view_support,
                "stability_pass_count": candidate.stability_pass_count,
                "stability_window_size": stability.window_frames,
                "stability_required_passes": stability.required_gate_passes,
                "detect_registration_outcome": outcome,
                "detect_registration_reject_reasons": candidate.reject_reasons,
            }
        )


def _stable_cross_view_associations(
    observations: tuple[TerminalObservation, ...],
    candidates: Sequence[DetectToGlobalTrackCandidate],
) -> tuple[CrossViewAssociation, ...]:
    stable_signatures = {
        _observation_candidate_signature(candidate)
        for candidate in candidates
        if candidate.stable_cross_view_support
    }
    bus = TerminalObservationBus()
    for observation in observations:
        association = observation.terminal_association
        if association is None or association.local_track_id is None:
            continue
        key = (
            observation.resource_id,
            observation.camera_id or "",
            observation.frame_id or "",
            association.local_track_id,
            association.assigned_global_track_id,
        )
        if key in stable_signatures:
            bus.publish(observation)
    return tuple(bus.cross_view_associations())


def _stability_key(candidate: DetectToGlobalTrackCandidate) -> tuple[str, str, str, str]:
    return (
        candidate.resource_id,
        candidate.camera_id,
        candidate.local_track_id,
        candidate.global_track_id or "",
    )


def _candidate_signature(candidate: DetectToGlobalTrackCandidate) -> tuple[str, str, str, str, str | None, float]:
    return (
        candidate.resource_id,
        candidate.camera_id,
        candidate.frame_id,
        candidate.local_track_id,
        candidate.global_track_id,
        candidate.timestamp,
    )


def _observation_candidate_signature(
    candidate: DetectToGlobalTrackCandidate,
) -> tuple[str, str, str, str, str]:
    return (
        candidate.resource_id,
        candidate.camera_id,
        candidate.frame_id,
        candidate.local_track_id,
        candidate.global_track_id or "",
    )


def _assignment_margin(costs: np.ndarray, row: int, col: int) -> float:
    selected = float(costs[row, col])
    alternatives: list[float] = []
    for other_row in range(costs.shape[0]):
        if other_row != row and isfinite(float(costs[other_row, col])):
            alternatives.append(float(costs[other_row, col]))
    for other_col in range(costs.shape[1]):
        if other_col != col and isfinite(float(costs[row, other_col])):
            alternatives.append(float(costs[row, other_col]))
    if not alternatives:
        return float("inf")
    return min(alternatives) - selected


def _pair_reject_reasons(record: _PairRecord) -> tuple[str, ...]:
    if not record.projection_valid:
        return (PROJECTION_INVALID_REASON,)
    return ("geometry_gate_rejected",)


def _local_reject_reasons_for_col(
    pair_records: Mapping[tuple[int, int], _PairRecord],
    col: int,
) -> tuple[str, ...]:
    reasons: list[str] = []
    for (_, candidate_col), record in sorted(pair_records.items()):
        if candidate_col != col:
            continue
        for reason in _pair_reject_reasons(record):
            if reason not in reasons:
                reasons.append(reason)
    return tuple(reasons or ("geometry_gate_rejected",))


def _candidate_outcome(
    *,
    selected: bool,
    gate_passed: bool,
    reasons: Sequence[str],
) -> str:
    if selected:
        return REGISTERED_TO_GLOBAL_TRACK_REASON
    if gate_passed:
        return "candidate_not_selected"
    return _outcome_from_reasons(reasons)


def _default_candidate_outcome(decision_state: str, reasons: Iterable[str]) -> str:
    reason_outcome = _outcome_from_reasons(reasons)
    if reason_outcome != "candidate_not_selected":
        return reason_outcome
    state = str(decision_state)
    if state == "registered":
        return REGISTERED_TO_GLOBAL_TRACK_REASON
    if state == "rejected":
        return "rejected"
    return "candidate_not_selected"


def _outcome_from_reasons(reasons: Iterable[str]) -> str:
    normalized = _valid_reason_tuple(reasons)
    if normalized:
        return normalized[0]
    return "candidate_not_selected"


def _measurement_age_s(local_track: LocalVisualTrack, timestamp: float) -> float:
    return max(0.0, float(timestamp) - float(local_track.timestamp))


def _pixel_error_px(local_track: LocalVisualTrack, projection: ProjectionResult) -> float | None:
    if projection.pixel is None:
        return None
    return float(np.linalg.norm(local_track.center_px - projection.pixel))


def _projection_pixel_tuple(projection: ProjectionResult) -> tuple[float, float] | None:
    if projection.pixel is None:
        return None
    return _vector_tuple(projection.pixel)


def _projection_pixel_list(projection: ProjectionResult) -> list[float] | None:
    if projection.pixel is None:
        return None
    return _vector_list(projection.pixel)


def _vector_tuple(values: np.ndarray) -> tuple[float, float]:
    array = np.asarray(values, dtype=float).reshape(2)
    return (float(array[0]), float(array[1]))


def _vector_list(values: np.ndarray) -> list[float]:
    return [float(item) for item in np.asarray(values, dtype=float).reshape(-1).tolist()]


def _matrix_list(values: np.ndarray | None) -> list[list[float]] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float)
    if array.ndim != 2:
        return None
    return [[float(item) for item in row] for row in array.tolist()]


def _has_offline_truth_label(batch: CameraLocalTrackBatch, local_track: LocalVisualTrack) -> bool:
    if _metadata_has_truth(batch.metadata):
        return True
    for key in (
        "offline_truth_by_local_track_id",
        "truth_by_local_track_id",
        "truth_global_track_id_by_local_track_id",
        "true_global_track_id_by_local_track_id",
    ):
        value = batch.metadata.get(key)
        if isinstance(value, Mapping) and local_track.local_track_id in value:
            return True
    return False


def _metadata_has_truth(metadata: Mapping[str, Any]) -> bool:
    return any(key in metadata for key in TRUTH_OR_GLOBAL_FIELD_NAMES)


def _online_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {str(key): value for key, value in metadata.items() if str(key) not in TRUTH_OR_GLOBAL_FIELD_NAMES}


def _calibration_summary_metadata(
    candidates: Sequence[DetectToGlobalTrackCandidate],
) -> dict[str, Any]:
    health_counts: dict[str, int] = {}
    pose_source_counts: dict[str, int] = {}
    errors = [
        error
        for error in (_finite_or_none(candidate.reprojection_error) for candidate in candidates)
        if error is not None
    ]
    for candidate in candidates:
        health_counts[candidate.calibration_health] = health_counts.get(candidate.calibration_health, 0) + 1
        pose_source_counts[candidate.camera_pose_source] = pose_source_counts.get(candidate.camera_pose_source, 0) + 1
    return {
        "calibration_health_counts": health_counts,
        "camera_pose_source_counts": pose_source_counts,
        "projection_valid_count": sum(1 for candidate in candidates if candidate.projection_valid),
        "projection_invalid_count": sum(1 for candidate in candidates if not candidate.projection_valid),
        "drift_warning_count": sum(1 for candidate in candidates if candidate.drift_warning),
        "reprojection_error_count": len(errors),
        "reprojection_error_mean_px": float(np.mean(errors)) if errors else None,
        "reprojection_error_max_px": float(np.max(errors)) if errors else None,
    }


def _count_reasons(counts: dict[str, int], reasons: Iterable[str]) -> None:
    for reason in _valid_reason_tuple(reasons):
        counts[reason] = counts.get(reason, 0) + 1


def _reason_count_map(counts: Mapping[str, int]) -> dict[str, int]:
    result = {reason: 0 for reason in DETECT_REGISTRATION_REASONS}
    for reason, count in counts.items():
        if reason in result:
            result[reason] = int(count)
    return result


def _valid_reason_tuple(reasons: Iterable[str]) -> tuple[str, ...]:
    if isinstance(reasons, str):
        reasons = (reasons,)
    valid = set(DETECT_REGISTRATION_REASONS)
    return tuple(dict.fromkeys(str(reason) for reason in reasons if str(reason) in valid))


def _as_matrix(values: Any, shape: tuple[int, int], name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    return array.copy()


def _optional_pair(values: tuple[float, float] | None) -> tuple[float, float] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (2,):
        raise ValueError(f"pair must have shape (2,), got {array.shape}")
    return (float(array[0]), float(array[1]))


def _optional_string(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _string_tuple(values: Any | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,) if values else ()
    return tuple(str(value) for value in values if value is not None and str(value))


def _optional_float(value: Any | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_positive_float(value: Any | None) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not isfinite(result) or result <= 0.0:
        return None
    return result


def _optional_int(value: Any | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if isfinite(value) else None
