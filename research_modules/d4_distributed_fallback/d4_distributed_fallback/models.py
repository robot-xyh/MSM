"""Shared models for offline failover and CBBA simulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Iterable


CENTER_REPLAN_STATES = frozenset(
    {"pending", "applied", "acknowledged_no_change", "expired"}
)


def build_center_replan_risk_signature(
    risk_factors: Iterable[str],
) -> tuple[str, ...]:
    """Return the stable, immutable risk signature used by replan lifecycle state."""

    return tuple(sorted({str(item).strip() for item in risk_factors if str(item).strip()}))


@dataclass(frozen=True)
class CenterReplanStatus:
    """Read-only center replan request state consumed by D4.

    D4 observes this DTO but does not mutate the center request or resolved plan.
    """

    request_id: str
    target_id: str
    risk_signature: tuple[str, ...]
    state: str
    requested_at: float
    coalition_id: str | None = None
    coalition_version: int | None = None
    resolved_at: float | None = None
    resolved_plan_id: str | None = None
    resolved_plan_version: int | None = None

    def __post_init__(self) -> None:
        normalized_state = str(self.state).strip().lower()
        if normalized_state not in CENTER_REPLAN_STATES:
            allowed = ", ".join(sorted(CENTER_REPLAN_STATES))
            raise ValueError(f"center replan state must be one of: {allowed}")
        if not str(self.request_id).strip():
            raise ValueError("request_id must not be empty")
        if not str(self.target_id).strip():
            raise ValueError("target_id must not be empty")
        object.__setattr__(self, "state", normalized_state)
        object.__setattr__(
            self,
            "risk_signature",
            build_center_replan_risk_signature(self.risk_signature),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


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
    FIXED_TETHERED_SECONDARY = "fixed_tethered_secondary"
    SECONDARY_RECON = "secondary_recon"
    MOBILE_HIGH_RECON = "mobile_high_recon"
    MOBILE_SECONDARY_RECON = "mobile_secondary_recon"
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
    required_resource_count: int = 1
    coalition_id: str | None = None
    coalition_version: int | None = None
    coalition_complete: bool = False

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
    lease_expires_at_s: float | None = None
    epoch: int = 0
    node_role: NodeRole = NodeRole.INTERCEPTOR
    coordinator_only: bool = False
    coverage_cell: str | None = None
    heartbeat_timestamp_s: float | None = None
    heartbeat_stale_after_s: float = 2.0
    cue_freshness_s: float | None = None
    gimbal_pointing_ok: bool | None = None
    secondary_coverage_ratio: float | None = None
    cross_view_support_count: int | None = None
    secondary_network_full_view_rate: float | None = None
    stable_cross_view_registration_count: int | None = None
    not_registered_count: int | None = None
    readiness_timestamp_s: float | None = None
    readiness_stale_after_s: float | None = None
    takeover_ready_since_s: float | None = None
    takeover_ready_observation_count: int | None = None
    takeover_ready_sustained: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


FIXED_TETHERED_SECONDARY_CLASSES = frozenset(
    {
        "fixed_tethered_secondary",
        "tethered_recon",
        "secondary_c2",
    }
)
MOBILE_SECONDARY_RECON_CLASSES = frozenset(
    {
        "mobile_high_recon",
        "mobile_secondary_recon",
    }
)
SECONDARY_RECON_CAPABILITY_CLASSES = (
    FIXED_TETHERED_SECONDARY_CLASSES | MOBILE_SECONDARY_RECON_CLASSES
)
SECONDARY_NODE_ROLES = frozenset(
    {
        NodeRole.GROUND_BACKUP,
        NodeRole.FIXED_TETHERED_SECONDARY,
        NodeRole.SECONDARY_RECON,
        NodeRole.MOBILE_HIGH_RECON,
        NodeRole.MOBILE_SECONDARY_RECON,
    }
)
SECONDARY_NODE_ROLE_VALUES = frozenset(role.value for role in SECONDARY_NODE_ROLES)


def node_role_value(node_role: Any) -> str:
    if isinstance(node_role, Enum):
        return str(node_role.value)
    if node_role is None:
        return ""
    text = str(node_role).strip().lower()
    if text.startswith("noderole."):
        return text.split(".", 1)[1]
    return text


def capability_class_value(capability_class: Any) -> str:
    if capability_class is None:
        return ""
    return str(capability_class).strip().lower()


def secondary_capability_class(resource: Any) -> str:
    capability = capability_class_value(getattr(resource, "capability_class", ""))
    role = node_role_value(getattr(resource, "node_role", None))
    if capability == "mobile_high_recon" or role == NodeRole.MOBILE_HIGH_RECON.value:
        return "mobile_high_recon"
    if capability == "mobile_secondary_recon" or role == NodeRole.MOBILE_SECONDARY_RECON.value:
        return "mobile_secondary_recon"
    if capability in FIXED_TETHERED_SECONDARY_CLASSES or role == (
        NodeRole.FIXED_TETHERED_SECONDARY.value
    ):
        return "fixed_tethered_secondary"
    if role == NodeRole.SECONDARY_RECON.value:
        return "secondary_recon"
    if role == NodeRole.GROUND_BACKUP.value:
        return "ground_backup"
    return capability or role


def is_secondary_node_resource(resource: Any) -> bool:
    role = node_role_value(getattr(resource, "node_role", None))
    capability = capability_class_value(getattr(resource, "capability_class", ""))
    return role in SECONDARY_NODE_ROLE_VALUES or capability in SECONDARY_RECON_CAPABILITY_CLASSES


def is_mobile_high_recon_resource(resource: Any) -> bool:
    return secondary_capability_class(resource) == "mobile_high_recon"


def is_fixed_tethered_secondary_resource(resource: Any) -> bool:
    return secondary_capability_class(resource) == "fixed_tethered_secondary"


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
    lease_expires_at_s: float | None = None
    lease_expired: bool | None = None
    coverage_matches_requested_cell: bool = False
    heartbeat_stale: bool | None = None
    cue_stale: bool | None = None
    link_fresh: bool | None = None
    heartbeat: float | None = None
    video_cue_freshness: float | None = None
    capability_class: str | None = None
    node_role: str | None = None
    secondary_capability_class: str | None = None
    cue_freshness_s: float | None = None
    gimbal_pointing_ok: bool | None = None
    secondary_coverage_ratio: float | None = None
    cross_view_support_count: int | None = None
    is_mobile_high_recon: bool = False
    is_fixed_tethered_secondary: bool = False
    secondary_visible: bool = False
    secondary_registered: bool = False
    secondary_takeover_capable: bool = False
    secondary_capability_score: float = 0.0
    secondary_capability_reasons: tuple[str, ...] = ()
    secondary_readiness_class: str = "not_ready"
    secondary_capability_inputs: dict[str, Any] = field(default_factory=dict)
    secondary_network_full_view_rate: float | None = None
    stable_cross_view_registration_count: int | None = None
    not_registered_count: int | None = None
    registration_evidence_source: str = "unknown"
    stable_registration_evidence_present: bool = False
    not_registered_evidence_present: bool = False
    takeover_ready_consecutive_decisions: int = 0
    takeover_ready_since_s: float | None = None
    takeover_ready_duration_s: float = 0.0
    takeover_ready_required_decisions: int = 1
    takeover_ready_required_duration_s: float = 0.0
    takeover_ready_sustained: bool = False
    takeover_readiness_fallback_reason: str | None = None

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
    cost_gap_benchmark: "CBBACostGapBenchmark | None" = None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CBBACostGapBenchmark:
    """Offline comparison between D4 CBBA and a D3 centralized baseline."""

    benchmark_source: str
    cbba_total_cost: float | None
    center_total_cost: float | None
    absolute_cost_gap: float | None
    relative_cost_gap: float | None
    cbba_assignment_count: int
    center_assignment_count: int
    common_assignment_count: int
    cbba_completion_rate: float
    center_completion_rate: float
    completion_rate_gap: float
    cbba_conflict_count: int
    cbba_consensus_rounds: int
    cbba_messages_sent: int
    missing_cbba_task_ids: tuple[str, ...] = ()
    extra_cbba_task_ids: tuple[str, ...] = ()
    missing_cost_pairs: tuple[str, ...] = ()
    per_task_cost_gap: dict[str, float | None] = field(default_factory=dict)

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
