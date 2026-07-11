"""Contracts for cross-node local-track registration.

These models are intentionally separate from the detection-to-track models in
``models.py``.  The online contract contains no truth identity; truth labels
belong to the offline evaluator in ``cross_node_metrics.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from .models import govern_covariance


class CorrelationStatus(str, Enum):
    """Common-information status declared for a source-track payload."""

    EXACT_KNOWN_CORRELATION = "exact_known_correlation"
    UNKNOWN_CORRELATION = "unknown_correlation"
    DUPLICATE_INFORMATION = "duplicate_information"


class FusionAction(str, Enum):
    """D2 decision sent to the D1-owned numerical fusion implementation."""

    NO_FUSION_SINGLE_SOURCE = "no_fusion_single_source"
    REQUEST_EXACT_CORRELATED_FUSION = "request_exact_correlated_fusion"
    REQUEST_COVARIANCE_INTERSECTION = "request_covariance_intersection"
    REJECT_DUPLICATE_INFORMATION = "reject_duplicate_information"


@dataclass(frozen=True, order=True, slots=True)
class SourceTrackKey:
    """Namespaced local-track identity; local IDs are never globally unique."""

    source_node_id: str
    local_track_id: str
    local_epoch: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "source_node_id": self.source_node_id,
            "local_track_id": self.local_track_id,
            "local_epoch": self.local_epoch,
        }


@dataclass(slots=True)
class SourceTrackSummary:
    """Online summary of one independent node's 3D constant-velocity track.

    ``ned_state`` is ordered ``[north, east, down, vn, ve, vd]``.  Candidate
    and current canonical IDs are untrusted hints; the center-owned registry is
    the only identity authority.
    """

    source_node_id: str
    local_track_id: str
    local_epoch: int
    measurement_timestamp: float
    arrival_timestamp: float
    ned_state: np.ndarray
    ned_covariance: np.ndarray
    quality: float
    lineage: tuple[str, ...]
    correlation_status: CorrelationStatus = CorrelationStatus.UNKNOWN_CORRELATION
    candidate_canonical_ids: tuple[str, ...] = ()
    current_canonical_id: str | None = None
    payload_id: str | None = None
    known_cross_covariance: np.ndarray | None = None
    frame: str = "NED"
    covariance_consistency: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_node_id = str(self.source_node_id).strip()
        self.local_track_id = str(self.local_track_id).strip()
        self.local_epoch = int(self.local_epoch)
        if not self.source_node_id or not self.local_track_id:
            raise ValueError("source_node_id and local_track_id must be non-empty")
        if self.local_epoch < 0:
            raise ValueError("local_epoch must be non-negative")

        self.measurement_timestamp = float(self.measurement_timestamp)
        self.arrival_timestamp = float(self.arrival_timestamp)
        if not np.isfinite(self.measurement_timestamp) or not np.isfinite(
            self.arrival_timestamp
        ):
            raise ValueError("track timestamps must be finite")
        if self.arrival_timestamp < self.measurement_timestamp:
            raise ValueError("arrival_timestamp cannot precede measurement_timestamp")

        self.ned_state = np.asarray(self.ned_state, dtype=float).reshape(-1)
        if self.ned_state.shape != (6,) or not np.all(np.isfinite(self.ned_state)):
            raise ValueError("ned_state must be a finite 6D CV state")
        self.ned_covariance, self.covariance_consistency = govern_covariance(
            self.ned_covariance,
            (6, 6),
            "source-track NED covariance",
        )

        self.quality = float(self.quality)
        if not np.isfinite(self.quality) or not 0.0 <= self.quality <= 1.0:
            raise ValueError("quality must be finite and within [0, 1]")
        self.lineage = tuple(str(item).strip() for item in self.lineage)
        if not self.lineage or any(not item for item in self.lineage):
            raise ValueError("lineage must contain at least one non-empty identifier")
        if len(set(self.lineage)) != len(self.lineage):
            raise ValueError("lineage identifiers must be unique within a payload")

        self.correlation_status = CorrelationStatus(self.correlation_status)
        self.candidate_canonical_ids = tuple(
            dict.fromkeys(str(item).strip() for item in self.candidate_canonical_ids)
        )
        if any(not item for item in self.candidate_canonical_ids):
            raise ValueError("candidate_canonical_ids cannot contain empty IDs")
        if self.current_canonical_id is not None:
            self.current_canonical_id = str(self.current_canonical_id).strip() or None
        if self.payload_id is not None:
            self.payload_id = str(self.payload_id).strip() or None
        self.frame = str(self.frame).upper()
        if self.frame != "NED":
            raise ValueError("cross-node source tracks must use the NED frame")

        if self.known_cross_covariance is not None:
            cross_covariance = np.asarray(self.known_cross_covariance, dtype=float)
            if cross_covariance.shape != (6, 6) or not np.all(
                np.isfinite(cross_covariance)
            ):
                raise ValueError("known_cross_covariance must be a finite 6x6 matrix")
            self.known_cross_covariance = cross_covariance
        if (
            self.correlation_status == CorrelationStatus.EXACT_KNOWN_CORRELATION
            and self.known_cross_covariance is None
        ):
            raise ValueError(
                "exact_known_correlation requires known_cross_covariance"
            )

    @property
    def source_key(self) -> SourceTrackKey:
        return SourceTrackKey(
            self.source_node_id,
            self.local_track_id,
            self.local_epoch,
        )

    @property
    def lineage_fingerprint(self) -> tuple[str, ...]:
        return tuple(sorted(self.lineage))

    @property
    def payload_fingerprint(self) -> tuple[object, ...]:
        if self.payload_id is not None:
            return ("payload_id", self.payload_id)
        return (
            "implicit",
            self.source_node_id,
            self.local_track_id,
            self.local_epoch,
            self.measurement_timestamp,
            self.lineage_fingerprint,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.source_key.to_dict(),
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "frame": self.frame,
            "ned_state": self.ned_state.tolist(),
            "ned_covariance": self.ned_covariance.tolist(),
            "quality": self.quality,
            "lineage": list(self.lineage),
            "correlation_status": self.correlation_status.value,
            "candidate_canonical_ids": list(self.candidate_canonical_ids),
            "current_canonical_id": self.current_canonical_id,
            "payload_id": self.payload_id,
            "known_cross_covariance": (
                None
                if self.known_cross_covariance is None
                else self.known_cross_covariance.tolist()
            ),
            "covariance_consistency": dict(self.covariance_consistency),
        }


@dataclass(frozen=True, slots=True)
class PropagatedSourceTrack:
    summary: SourceTrackSummary
    fusion_timestamp: float
    ned_state: np.ndarray
    ned_covariance: np.ndarray


@dataclass(frozen=True, slots=True)
class CanonicalTrackSnapshot:
    canonical_id: str
    fusion_timestamp: float
    ned_state: np.ndarray
    ned_covariance: np.ndarray
    quality: float
    representative_source_key: SourceTrackKey
    source_track_keys: tuple[SourceTrackKey, ...]


@dataclass(frozen=True, slots=True)
class TrackToTrackMatch:
    canonical_id: str
    source_track_key: SourceTrackKey
    mahalanobis_squared: float
    assignment_cost: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "source_track_key": self.source_track_key.to_dict(),
            "mahalanobis_squared": self.mahalanobis_squared,
            "assignment_cost": self.assignment_cost,
        }


@dataclass(frozen=True, slots=True)
class FusionDirective:
    canonical_id: str | None
    source_track_key: SourceTrackKey
    action: FusionAction
    reason: str
    reference_source_track_keys: tuple[SourceTrackKey, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "source_track_key": self.source_track_key.to_dict(),
            "action": self.action.value,
            "reason": self.reason,
            "reference_source_track_keys": [
                item.to_dict() for item in self.reference_source_track_keys
            ],
        }


@dataclass(frozen=True, slots=True)
class BindingHistoryEvent:
    fusion_timestamp: float
    source_track_key: SourceTrackKey
    canonical_id: str | None
    previous_canonical_id: str | None
    event: str
    reason: str
    mahalanobis_squared: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fusion_timestamp": self.fusion_timestamp,
            "source_track_key": self.source_track_key.to_dict(),
            "canonical_id": self.canonical_id,
            "previous_canonical_id": self.previous_canonical_id,
            "event": self.event,
            "reason": self.reason,
            "mahalanobis_squared": self.mahalanobis_squared,
        }


@dataclass(frozen=True, slots=True)
class RejectedSourceTrack:
    source_track_key: SourceTrackKey
    payload_id: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_track_key": self.source_track_key.to_dict(),
            "payload_id": self.payload_id,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CrossNodeAssociationResult:
    fusion_timestamp: float
    canonical_bindings: dict[str, tuple[SourceTrackKey, ...]]
    canonical_snapshots: tuple[CanonicalTrackSnapshot, ...]
    matches: tuple[TrackToTrackMatch, ...]
    created_canonical_ids: tuple[str, ...]
    rejected_source_tracks: tuple[RejectedSourceTrack, ...]
    fusion_directives: tuple[FusionDirective, ...]
    history_events: tuple[BindingHistoryEvent, ...]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fusion_timestamp": self.fusion_timestamp,
            "canonical_bindings": {
                canonical_id: [item.to_dict() for item in source_keys]
                for canonical_id, source_keys in self.canonical_bindings.items()
            },
            "canonical_snapshots": [
                {
                    "canonical_id": item.canonical_id,
                    "fusion_timestamp": item.fusion_timestamp,
                    "ned_state": item.ned_state.tolist(),
                    "ned_covariance": item.ned_covariance.tolist(),
                    "quality": item.quality,
                    "representative_source_key": (
                        item.representative_source_key.to_dict()
                    ),
                    "source_track_keys": [
                        key.to_dict() for key in item.source_track_keys
                    ],
                }
                for item in self.canonical_snapshots
            ],
            "matches": [item.to_dict() for item in self.matches],
            "created_canonical_ids": list(self.created_canonical_ids),
            "rejected_source_tracks": [
                item.to_dict() for item in self.rejected_source_tracks
            ],
            "fusion_directives": [
                item.to_dict() for item in self.fusion_directives
            ],
            "history_events": [item.to_dict() for item in self.history_events],
            "metrics": dict(self.metrics),
        }
