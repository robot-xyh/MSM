"""Shared models for offline failover and CBBA simulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any


class C2Health(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    SUSPECT = "suspect"
    FAILED = "failed"


class ConfidenceBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AvailabilityBand(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CommBand(str, Enum):
    POOR = "poor"
    LIMITED = "limited"
    GOOD = "good"


class NodeRole(str, Enum):
    GROUND_BACKUP = "ground_backup"
    SECONDARY_RECON = "secondary_recon"
    CLUSTER_REPRESENTATIVE = "cluster_representative"
    INTERCEPTOR = "interceptor"


@dataclass(frozen=True)
class TrackSummary:
    track_id: str
    coarse_cell: str
    age_s: float
    confidence_band: ConfidenceBand
    source_count: int
    epoch: int = 0

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class ResourceSummary:
    node_id: str
    capability_class: str
    availability_band: AvailabilityBand
    comm_band: CommBand
    operator_hold: bool = False
    takeover_priority: int = 100
    lease_epoch: int = 0
    epoch: int = 0
    node_role: NodeRole = NodeRole.INTERCEPTOR
    coordinator_only: bool = False
    coverage_cell: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class BidState:
    task_id: str
    bidder: str
    score: float
    constraints_hash: str
    epoch: int
    round_id: int

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BidState":
        return cls(
            task_id=str(data["task_id"]),
            bidder=str(data["bidder"]),
            score=float(data["score"]),
            constraints_hash=str(data["constraints_hash"]),
            epoch=int(data["epoch"]),
            round_id=int(data.get("round_id", 0)),
        )


@dataclass(frozen=True)
class Assignment:
    task_id: str
    owner: str
    score: float
    epoch: int
    mode: str = "fallback_continuity"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class HealthTransition:
    from_state: C2Health
    to_state: C2Health
    time_s: float
    reason: str
    epoch: int

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class NetworkMessage:
    sender: str
    recipient: str
    kind: str
    payload: dict[str, Any]
    epoch: int
    sent_at_s: float
    deliver_at_s: float
    size_bytes: int


@dataclass
class NetworkStats:
    sent_count: int = 0
    delivered_count: int = 0
    dropped_count: int = 0
    estimated_bytes: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class CBBAResult:
    assignments: dict[str, Assignment]
    consensus_rounds: int
    converged: bool
    conflict_count: int
    completion_rate: float
    messages_sent: int
    messages_delivered: int
    messages_dropped: int
    estimated_bytes: int
    duration_s: float
    final_views: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass
class MergeResult:
    accepted: list[str]
    review: list[str]
    conflicts: list[str]
    merged_assignments: dict[str, Assignment]
    restored_normal: bool

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value
