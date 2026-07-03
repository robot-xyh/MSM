"""Shared data models for offline data association experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class TrackLifecycleState(str, Enum):
    """Research-only track lifecycle states."""

    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    ENGAGEABLE = "engageable"
    LOST = "lost"
    DROPPED = "dropped"


@dataclass(slots=True)
class AssociationRiskSummary:
    """Weak cross-view association risk evidence for offline coordination.

    D2 remains the authority for `global_track_id`. Cross-node, D5 terminal,
    secondary-node, or interceptor-peer inputs represented here are weak
    evidence for risk scoring only; they do not rewrite global track identity.
    """

    timestamp: float
    source_node_id: str | None = None
    link_type: str | None = None
    d5_disagreement_count: int = 0
    duplicate_track_risk: float = 0.0
    association_ambiguity: float = 0.0
    covariance_overlap_rate: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.timestamp = float(self.timestamp)
        self.d5_disagreement_count = int(self.d5_disagreement_count)
        self.duplicate_track_risk = float(self.duplicate_track_risk)
        self.association_ambiguity = float(self.association_ambiguity)
        self.covariance_overlap_rate = float(self.covariance_overlap_rate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "source_node_id": self.source_node_id,
            "link_type": self.link_type,
            "d5_disagreement_count": self.d5_disagreement_count,
            "duplicate_track_risk": self.duplicate_track_risk,
            "association_ambiguity": self.association_ambiguity,
            "covariance_overlap_rate": self.covariance_overlap_rate,
            "metadata": _json_ready(self.metadata),
        }


def _as_vector(value: Any, size: int, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.shape != (size,):
        raise ValueError(f"{name} must have shape ({size},), got {array.shape}")
    return array


def _as_matrix(value: Any, shape: tuple[int, int], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    return array


@dataclass(slots=True)
class Detection:
    """Single 2D position detection used by the offline tracker."""

    detection_id: str
    timestamp: float
    position: np.ndarray
    covariance: np.ndarray | None = None
    truth_id: str | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    feature: np.ndarray | None = None

    def __post_init__(self) -> None:
        self.position = _as_vector(self.position, 2, "position")
        if self.covariance is None:
            self.covariance = np.eye(2, dtype=float)
        else:
            self.covariance = _as_matrix(self.covariance, (2, 2), "covariance")
        if self.feature is not None:
            self.feature = np.asarray(self.feature, dtype=float).reshape(-1)
        self.timestamp = float(self.timestamp)
        self.confidence = float(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detection_id": self.detection_id,
            "timestamp": self.timestamp,
            "position": self.position.tolist(),
            "covariance": self.covariance.tolist(),
            "truth_id": self.truth_id,
            "confidence": self.confidence,
            "metadata": _json_ready(self.metadata),
            "feature": None if self.feature is None else self.feature.tolist(),
        }


@dataclass(slots=True)
class TrackTransition:
    timestamp: float
    track_id: str
    from_state: str
    to_state: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "track_id": self.track_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
        }


@dataclass(slots=True)
class GlobalTrack:
    """Global constant-velocity track state `[x, y, vx, vy]`."""

    global_track_id: str
    state: np.ndarray
    covariance: np.ndarray
    timestamp: float
    lifecycle_state: TrackLifecycleState = TrackLifecycleState.TENTATIVE
    hits: int = 0
    consecutive_hits: int = 0
    misses: int = 0
    age: int = 0
    created_at: float = 0.0
    last_update_time: float = 0.0
    last_detection_id: str | None = None
    truth_id: str | None = None
    identity_confidence: float = 0.0
    feature: np.ndarray | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    transition_log: list[TrackTransition] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.state = _as_vector(self.state, 4, "state")
        self.covariance = _as_matrix(self.covariance, (4, 4), "covariance")
        if self.feature is not None:
            self.feature = np.asarray(self.feature, dtype=float).reshape(-1)
        self.timestamp = float(self.timestamp)
        self.created_at = float(self.created_at)
        self.last_update_time = float(self.last_update_time)

    @property
    def position(self) -> np.ndarray:
        return self.state[:2]

    def append_history(self, event: str, detection: Detection | None = None) -> None:
        entry: dict[str, Any] = {
            "timestamp": self.timestamp,
            "event": event,
            "state": self.state.tolist(),
            "covariance_trace": float(np.trace(self.covariance)),
            "lifecycle_state": self.lifecycle_state.value,
            "hits": self.hits,
            "misses": self.misses,
        }
        if detection is not None:
            entry["detection_id"] = detection.detection_id
            entry["truth_id"] = detection.truth_id
        self.history.append(entry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "state": self.state.tolist(),
            "covariance": self.covariance.tolist(),
            "timestamp": self.timestamp,
            "lifecycle_state": self.lifecycle_state.value,
            "hits": self.hits,
            "consecutive_hits": self.consecutive_hits,
            "misses": self.misses,
            "age": self.age,
            "created_at": self.created_at,
            "last_update_time": self.last_update_time,
            "last_detection_id": self.last_detection_id,
            "truth_id": self.truth_id,
            "identity_confidence": self.identity_confidence,
            "feature": None if self.feature is None else self.feature.tolist(),
            "history": _json_ready(self.history),
            "transition_log": [transition.to_dict() for transition in self.transition_log],
        }


@dataclass(frozen=True, slots=True)
class MatchedPair:
    track_id: str
    detection_id: str
    cost: float
    probability: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "detection_id": self.detection_id,
            "cost": self.cost,
            "probability": self.probability,
        }


@dataclass(frozen=True, slots=True)
class RejectedPair:
    track_id: str
    detection_id: str
    reason: str
    value: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "detection_id": self.detection_id,
            "reason": self.reason,
            "value": self.value,
        }


@dataclass(slots=True)
class AssociationResult:
    timestamp: float
    matched_pairs: list[MatchedPair]
    unmatched_track_ids: list[str]
    unmatched_detection_ids: list[str]
    ambiguity_score: float
    associator_type: str
    rejected_pairs: list[RejectedPair] = field(default_factory=list)
    cost_matrix: np.ndarray | None = None
    distance_matrix: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_node_id: str | None = None
    link_type: str | None = None
    risk_summary: AssociationRiskSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "matched_pairs": [pair.to_dict() for pair in self.matched_pairs],
            "unmatched_track_ids": list(self.unmatched_track_ids),
            "unmatched_detection_ids": list(self.unmatched_detection_ids),
            "ambiguity_score": self.ambiguity_score,
            "associator_type": self.associator_type,
            "rejected_pairs": [pair.to_dict() for pair in self.rejected_pairs],
            "cost_matrix": None if self.cost_matrix is None else self.cost_matrix.tolist(),
            "distance_matrix": None
            if self.distance_matrix is None
            else self.distance_matrix.tolist(),
            "metadata": _json_ready(self.metadata),
            "source_node_id": self.source_node_id,
            "link_type": self.link_type,
            "risk_summary": None
            if self.risk_summary is None
            else self.risk_summary.to_dict(),
        }


@dataclass(slots=True)
class AssociationLogEntry:
    timestamp: float
    associator_type: str
    matched_pairs: list[MatchedPair]
    unmatched_track_ids: list[str]
    unmatched_detection_ids: list[str]
    ambiguity_score: float
    runtime_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)
    source_node_id: str | None = None
    link_type: str | None = None
    risk_summary: AssociationRiskSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "associator_type": self.associator_type,
            "matched_pairs": [pair.to_dict() for pair in self.matched_pairs],
            "unmatched_track_ids": list(self.unmatched_track_ids),
            "unmatched_detection_ids": list(self.unmatched_detection_ids),
            "ambiguity_score": self.ambiguity_score,
            "runtime_seconds": self.runtime_seconds,
            "metadata": _json_ready(self.metadata),
            "source_node_id": self.source_node_id,
            "link_type": self.link_type,
            "risk_summary": None
            if self.risk_summary is None
            else self.risk_summary.to_dict(),
        }


def _json_ready(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value
