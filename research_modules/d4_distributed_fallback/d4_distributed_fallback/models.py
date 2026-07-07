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


class LinkType(str, Enum):
    C2_DIRECT = "c2_direct"
    SECONDARY_RELAY = "secondary_relay"
    INTERCEPTOR_PEER = "interceptor_peer"
    VIDEO_CUE = "video_cue"


class PayloadKind(str, Enum):
    TRACK = "track"
    BBOX = "bbox"
    VIDEO_METADATA = "video_metadata"
    ASSIGNMENT = "assignment"
    TERMINAL_ASSOCIATION = "terminal_association"
    BID = "bid"
    RESOURCE_SUMMARY = "resource_summary"
    HEALTH = "health"


@dataclass(frozen=True)
class DistributedVisualEvidenceSummary:
    """D5-style distributed terminal visual evidence consumed by D4 CBBA.

    The global track id, when present, is copied from upstream evidence only.
    D4 uses it for matching/risk checks and never creates or rewrites it.
    """

    visual_support_resource_ids: tuple[str, ...] = ()
    hold_resource_ids: tuple[str, ...] = ()
    ambiguous_resource_ids: tuple[str, ...] = ()
    duplicate_lock_resource_ids: tuple[str, ...] = ()
    assigned_global_track_id: str | None = None
    terminal_confidence: float = 0.0
    terminal_ambiguity: float = 0.0
    hypothesis_count: int = 0
    support_count: int = 0
    decision_states: tuple[str, ...] = ()
    risk_reasons: tuple[str, ...] = ()
    hypothesis_only: bool = False
    stale_global_track_id: bool = False
    missing_global_track_id: bool = False
    duplicate_terminal_lock_risk: bool = False
    friend_conflict: bool = False
    global_track_id_conflict: bool = False
    local_id_conflict: bool = False

    @property
    def has_evidence(self) -> bool:
        return bool(
            self.visual_support_resource_ids
            or self.hold_resource_ids
            or self.ambiguous_resource_ids
            or self.duplicate_lock_resource_ids
            or self.decision_states
            or self.risk_reasons
            or self.hypothesis_count
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class TrackSummary:
    track_id: str
    coarse_cell: str
    age_s: float
    confidence_band: ConfidenceBand
    source_count: int
    epoch: int = 0
    visual_evidence: DistributedVisualEvidenceSummary = field(
        default_factory=DistributedVisualEvidenceSummary
    )

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
    heartbeat_timestamp_s: float | None = None
    heartbeat_stale_after_s: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class SecondaryNodeLifecycleSummary:
    node_id: str
    heartbeat_timestamp_s: float | None
    heartbeat_age_s: float | None
    lease_epoch: int
    coverage_cell: str | None
    video_cue_freshness_s: float | None
    link_stale: bool | None
    secondary_available: bool
    heartbeat: float | None = None
    video_cue_freshness: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CommunicationSummary:
    source_node_id: str
    target_node_id: str
    relay_node_id: str | None
    link_type: LinkType
    sent_timestamp: float
    received_timestamp: float
    payload_kind: PayloadKind
    stale_after_s: float
    sequence_id: str | None = None

    @property
    def latency_s(self) -> float:
        return max(0.0, self.received_timestamp - self.sent_timestamp)

    def is_stale(self, current_time_s: float | None = None) -> bool:
        reference_time = self.received_timestamp if current_time_s is None else current_time_s
        return reference_time - self.received_timestamp > self.stale_after_s

    def involves_node(self, node_id: str) -> bool:
        return node_id in {self.source_node_id, self.target_node_id, self.relay_node_id}

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
    assignment_audit: dict[str, dict[str, Any]] = field(default_factory=dict)

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
