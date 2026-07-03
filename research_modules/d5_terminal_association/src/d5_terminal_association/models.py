"""Data models for terminal visual association.

The central invariant is that global track IDs are center-owned. The local
module may reference them in a decision, but it must not mutate or reassign
them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


def _as_vector(values: Any, size: int, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (size,):
        raise ValueError(f"{name} must have shape ({size},), got {array.shape}")
    return array.copy()


def _as_matrix(values: Any, shape: tuple[int, int], name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    return array.copy()


def _optional_vector(values: Any | None, size: int, name: str) -> np.ndarray | None:
    if values is None:
        return None
    return _as_vector(values, size, name)


def _optional_bbox(values: Any | None) -> tuple[float, float, float, float] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (4,):
        raise ValueError(f"bbox must have shape (4,), got {array.shape}")
    x1, y1, x2, y2 = array.tolist()
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox must be (x_min, y_min, x_max, y_max)")
    return (x1, y1, x2, y2)


def _as_string_tuple(values: Any | None) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(str(value) for value in values)


@dataclass(frozen=True)
class CameraModel:
    """Pinhole camera with a world-to-camera transform.

    `R` and `t` implement `P_c = R @ P_w + t`.
    """

    K: np.ndarray
    R: np.ndarray
    t: np.ndarray
    image_size: tuple[int, int]
    measurement_cov: np.ndarray = field(default_factory=lambda: np.diag([4.0, 4.0]))
    dist_coeffs: np.ndarray | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "K", _as_matrix(self.K, (3, 3), "K"))
        object.__setattr__(self, "R", _as_matrix(self.R, (3, 3), "R"))
        object.__setattr__(self, "t", _as_vector(self.t, 3, "t"))
        object.__setattr__(
            self, "measurement_cov", _as_matrix(self.measurement_cov, (2, 2), "measurement_cov")
        )
        if self.dist_coeffs is not None:
            coeffs = np.asarray(self.dist_coeffs, dtype=float).reshape(-1).copy()
            object.__setattr__(self, "dist_coeffs", coeffs)
        width, height = self.image_size
        if width <= 0 or height <= 0:
            raise ValueError("image_size must be positive (width, height)")


@dataclass(frozen=True)
class GlobalTrack:
    """Center-owned global track state.

    The frozen dataclass prevents accidental reassignment of `global_track_id`
    inside the terminal module.
    """

    global_track_id: str
    position: np.ndarray
    covariance: np.ndarray
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    category: str = "unknown"
    timestamp: float = 0.0
    track_version: int = 0

    def __post_init__(self) -> None:
        if not self.global_track_id:
            raise ValueError("global_track_id must be non-empty")
        object.__setattr__(self, "position", _as_vector(self.position, 3, "position"))
        object.__setattr__(self, "covariance", _as_matrix(self.covariance, (3, 3), "covariance"))
        object.__setattr__(self, "velocity", _as_vector(self.velocity, 3, "velocity"))


@dataclass(frozen=True)
class LocalVisualTrack:
    """Local detector or MOT output in image coordinates."""

    local_track_id: str
    center_px: np.ndarray
    bbox: tuple[float, float, float, float] | None = None
    bearing_rate: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=float))
    category: str = "unknown"
    quality: float = 1.0
    mot_history_length: int = 1
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.local_track_id:
            raise ValueError("local_track_id must be non-empty")
        object.__setattr__(self, "center_px", _as_vector(self.center_px, 2, "center_px"))
        object.__setattr__(self, "bbox", _optional_bbox(self.bbox))
        object.__setattr__(self, "bearing_rate", _as_vector(self.bearing_rate, 2, "bearing_rate"))
        object.__setattr__(self, "quality", float(np.clip(self.quality, 0.0, 1.0)))
        if self.mot_history_length < 0:
            raise ValueError("mot_history_length must be non-negative")


@dataclass(frozen=True)
class Assignment:
    """Center assignment that the terminal module must respect."""

    assigned_global_track_id: str
    assignment_version: int = 0
    timestamp: float = 0.0
    require_version_match: bool = True
    plan_id: str | None = None
    plan_version: int | None = None
    authorization_state: str = "authorized"
    resource_id: str | None = None


@dataclass(frozen=True)
class IdentityClaim:
    """Simulated cooperative identity or friend tag claim."""

    platform_id: str
    claim_type: str
    auth_state: str
    associated_local_track_id: str | None = None
    center_px: np.ndarray | None = None
    bbox: tuple[float, float, float, float] | None = None
    timestamp: float = 0.0
    is_friend: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.platform_id:
            raise ValueError("platform_id must be non-empty")
        object.__setattr__(self, "center_px", _optional_vector(self.center_px, 2, "center_px"))
        object.__setattr__(self, "bbox", _optional_bbox(self.bbox))


@dataclass(frozen=True)
class ReconImageCue:
    """Image-plane cue produced by a secondary reconnaissance node.

    The cue is advisory evidence for a scoped set of local resources. It does
    not authorize terminal locking and cannot rewrite `global_track_id`.
    """

    cue_id: str
    producer_node_id: str
    timestamp: float
    image_frame_id: str
    global_track_id: str | None = None
    center_px: np.ndarray | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = 1.0
    scoped_resource_ids: tuple[str, ...] = ()
    source_type: str = "secondary_recon"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.cue_id:
            raise ValueError("cue_id must be non-empty")
        if not self.producer_node_id:
            raise ValueError("producer_node_id must be non-empty")
        object.__setattr__(self, "timestamp", float(self.timestamp))
        object.__setattr__(self, "center_px", _optional_vector(self.center_px, 2, "center_px"))
        object.__setattr__(self, "bbox", _optional_bbox(self.bbox))
        object.__setattr__(self, "confidence", float(np.clip(self.confidence, 0.0, 1.0)))
        object.__setattr__(self, "scoped_resource_ids", _as_string_tuple(self.scoped_resource_ids))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ProjectionResult:
    """Image-plane projection and covariance for one global track."""

    global_track_id: str
    category: str
    pixel: np.ndarray | None
    covariance_px: np.ndarray | None
    depth: float
    valid: bool
    reason: str = ""
    predicted_px_velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=float))

    def __post_init__(self) -> None:
        object.__setattr__(self, "pixel", _optional_vector(self.pixel, 2, "pixel"))
        if self.covariance_px is not None:
            object.__setattr__(
                self, "covariance_px", _as_matrix(self.covariance_px, (2, 2), "covariance_px")
            )
        object.__setattr__(
            self, "predicted_px_velocity", _as_vector(self.predicted_px_velocity, 2, "predicted_px_velocity")
        )


@dataclass(frozen=True)
class CostBreakdown:
    """Per-pair cost terms used to build the association matrix."""

    global_track_id: str
    local_track_id: str
    total_cost: float
    mahalanobis_d2: float
    rate_cost: float
    category_cost: float
    friend_cost: float
    quality_cost: float
    gated: bool
    friend_conflict_state: str = "none"
    recon_cue_cost: float = 0.0


@dataclass(frozen=True)
class CostMatrixResult:
    """Cost matrix plus explainable per-cell terms."""

    global_track_ids: list[str]
    local_track_ids: list[str]
    costs: np.ndarray
    breakdowns: dict[tuple[str, str], CostBreakdown]


@dataclass(frozen=True)
class TerminalAssociation:
    """Conservative terminal association output.

    `assigned_global_track_id` is copied from the center assignment. The local
    node reports a local visual candidate and decision state; it does not create
    or rewrite global IDs.
    """

    assigned_global_track_id: str
    local_track_id: str | None
    association_confidence: float
    ambiguity_score: float
    friend_conflict_state: str
    decision_state: str
    assignment_version: int
    reason: str = ""
    candidate_costs: list[tuple[str, float]] = field(default_factory=list)
    recon_cue_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TerminalObservation:
    """Cross-node terminal observation summary.

    This is a passive bus payload. It can carry local visual evidence,
    terminal association output, identity claims, and secondary reconnaissance
    cues, but it does not own or alter any `global_track_id`.
    """

    resource_id: str
    source_node_id: str
    link_type: str
    timestamp: float
    local_track: LocalVisualTrack | None = None
    terminal_association: TerminalAssociation | None = None
    identity_claims: tuple[IdentityClaim, ...] = ()
    recon_image_cues: tuple[ReconImageCue, ...] = ()
    camera_id: str | None = None
    frame_id: str | None = None
    arrival_timestamp: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.source_node_id:
            raise ValueError("source_node_id must be non-empty")
        if not self.link_type:
            raise ValueError("link_type must be non-empty")
        if (
            self.local_track is None
            and self.terminal_association is None
            and not self.identity_claims
            and not self.recon_image_cues
        ):
            raise ValueError("TerminalObservation must carry at least one payload")
        object.__setattr__(self, "timestamp", float(self.timestamp))
        if self.arrival_timestamp is not None:
            object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))
        object.__setattr__(self, "identity_claims", tuple(self.identity_claims))
        object.__setattr__(self, "recon_image_cues", tuple(self.recon_image_cues))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class CrossViewAssociation:
    """Passive cross-view evidence grouped by an existing global track ID.

    `duplicate_terminal_lock_risk` is only a signal for D3/D4 arbitration. D5
    still does not change assignments or rewrite global IDs.
    """

    global_track_id: str
    supporting_resource_ids: tuple[str, ...]
    local_track_ids: tuple[str, ...]
    ambiguity_score: float
    duplicate_terminal_lock_risk: bool
    source_node_id: str
    link_type: str
    source_node_ids: tuple[str, ...] = ()
    link_types: tuple[str, ...] = ()
    decision_states: tuple[str, ...] = ()
    association_confidences: tuple[float, ...] = ()
    friend_conflict_states: tuple[str, ...] = ()
    recon_cue_used_count: int = 0
    support_count: int = 0
    duplicate_lock_resource_ids: tuple[str, ...] = ()
    duplicate_local_track_ids: tuple[str, ...] = ()
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.global_track_id:
            raise ValueError("global_track_id must be non-empty")
        if not self.source_node_id:
            raise ValueError("source_node_id must be non-empty")
        if not self.link_type:
            raise ValueError("link_type must be non-empty")
        object.__setattr__(self, "supporting_resource_ids", _as_string_tuple(self.supporting_resource_ids))
        object.__setattr__(self, "local_track_ids", _as_string_tuple(self.local_track_ids))
        object.__setattr__(self, "source_node_ids", _as_string_tuple(self.source_node_ids))
        object.__setattr__(self, "link_types", _as_string_tuple(self.link_types))
        object.__setattr__(self, "decision_states", _as_string_tuple(self.decision_states))
        object.__setattr__(self, "friend_conflict_states", _as_string_tuple(self.friend_conflict_states))
        object.__setattr__(
            self, "duplicate_lock_resource_ids", _as_string_tuple(self.duplicate_lock_resource_ids)
        )
        object.__setattr__(self, "duplicate_local_track_ids", _as_string_tuple(self.duplicate_local_track_ids))
        object.__setattr__(
            self,
            "association_confidences",
            tuple(float(np.clip(value, 0.0, 1.0)) for value in self.association_confidences),
        )
        object.__setattr__(self, "ambiguity_score", float(np.clip(self.ambiguity_score, 0.0, 1.0)))
        object.__setattr__(self, "recon_cue_used_count", int(self.recon_cue_used_count))
        object.__setattr__(self, "support_count", int(self.support_count))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class TerminalConsistencySummary:
    """Window/state summary for D4/D6 consumers.

    This summary is derived from one resource's terminal association stream and
    optional cross-view summaries. It is an advisory signal only; it does not
    create assignments or alter center-owned global track IDs.
    """

    resource_id: str
    assigned_global_track_id: str
    assignment_version: int
    timestamp: float
    decision_state: str
    consistency_state: str
    association_confidence: float
    ambiguity_score: float
    friend_conflict_state: str
    candidate_cost_margin: float
    recon_cue_used: bool
    terminal_lock_age_s: float
    consecutive_locked_frames: int
    consecutive_ambiguous_frames: int
    consecutive_hold_frames: int
    consecutive_reacquire_frames: int
    local_track_id: str | None = None
    previous_decision_state: str | None = None
    lock_lifecycle_state: str = "unknown"
    lost_lock_event: bool = False
    lock_reacquired_event: bool = False
    event_summary: str = ""
    competing_global_track_id: str | None = None
    local_best_conflicts_with_assignment: bool = False
    duplicate_terminal_lock_risk: bool = False
    duplicate_lock_resource_ids: tuple[str, ...] = ()
    duplicate_local_track_ids: tuple[str, ...] = ()
    cross_view_support_count: int = 0
    cross_view_supporting_resource_ids: tuple[str, ...] = ()
    cross_view_decision_states: tuple[str, ...] = ()
    recommended_d4_action: str = "observe"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.assigned_global_track_id:
            raise ValueError("assigned_global_track_id must be non-empty")
        object.__setattr__(self, "timestamp", float(self.timestamp))
        object.__setattr__(
            self, "association_confidence", float(np.clip(self.association_confidence, 0.0, 1.0))
        )
        object.__setattr__(self, "ambiguity_score", float(np.clip(self.ambiguity_score, 0.0, 1.0)))
        object.__setattr__(self, "terminal_lock_age_s", max(0.0, float(self.terminal_lock_age_s)))
        object.__setattr__(self, "consecutive_locked_frames", int(self.consecutive_locked_frames))
        object.__setattr__(self, "consecutive_ambiguous_frames", int(self.consecutive_ambiguous_frames))
        object.__setattr__(self, "consecutive_hold_frames", int(self.consecutive_hold_frames))
        object.__setattr__(self, "consecutive_reacquire_frames", int(self.consecutive_reacquire_frames))
        object.__setattr__(self, "duplicate_lock_resource_ids", _as_string_tuple(self.duplicate_lock_resource_ids))
        object.__setattr__(self, "duplicate_local_track_ids", _as_string_tuple(self.duplicate_local_track_ids))
        object.__setattr__(
            self, "cross_view_supporting_resource_ids", _as_string_tuple(self.cross_view_supporting_resource_ids)
        )
        object.__setattr__(self, "cross_view_decision_states", _as_string_tuple(self.cross_view_decision_states))
        object.__setattr__(self, "cross_view_support_count", int(self.cross_view_support_count))
        object.__setattr__(self, "metadata", dict(self.metadata))
