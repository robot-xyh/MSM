"""Data models for abstract resource-target assignment research."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from math import isfinite, sqrt
from typing import Any, Iterable, Mapping
from uuid import uuid4


CostBreakdown = dict[str, float]

TERMINAL_FEEDBACK_HOLD_STATES = frozenset(
    {"ambiguous", "hold", "friend_overlap_hold"}
)
TERMINAL_FEEDBACK_REPLAN_STATES = frozenset({"reacquire"})
TERMINAL_FEEDBACK_ARBITRATION_STATES = frozenset(
    {"mismatch", "multi_frame_inconsistent", "cross_view_conflict"}
)
_FEEDBACK_CONSTRAINT_CLASSIFICATION_SCHEMA_V1 = (
    "d3_feedback_constraint_classification_v1"
)
_SOFT_TERMINAL_FEEDBACK_STATES = frozenset(
    {
        "ambiguous",
        "detection_lost",
        "hold",
        "lost",
        "not_detected",
        "reacquire",
    }
)
_SAFETY_IDENTITY_CONFLICT_VALUES = frozenset(
    {
        "assignment_mismatch",
        "coalition_or_plan_version_mismatch",
        "conflicting_assigned_global_track_ids",
        "cross_view_conflict",
        "identity_conflict",
        "local_track_id_conflict",
        "mismatch",
        "multi_frame_inconsistent",
        "primary_binding_count_mismatch",
        "primary_binding_not_execution_authorized",
        "resource_multiple_local_locks",
        "safety_identity_conflict",
        "wrong_binding",
    }
)
_SOFT_FEEDBACK_EVIDENCE_VALUES = frozenset(
    {
        "ambiguous",
        "bbox_area_unstable",
        "bbox_area_unstable_or_too_small",
        "camera_geometry_not_provided",
        "detection_unstable",
        "detection_lost",
        "fov_unstable",
        "geometry_gate_rejected",
        "hold",
        "hypothesis_only",
        "lost",
        "measurement_age_stale",
        "not_detected",
        "reacquire",
        "stability_window_failed",
    }
)
EFFECTIVE_GUIDANCE_AUTH_STATES = frozenset(
    {"recorded", "authorized", "approved", "human_approved", "operator_approved"}
)
GUIDANCE_BINDING_ACTIVE = "active"
GUIDANCE_BINDING_STALE = "stale"
GUIDANCE_BINDING_REVOKED = "revoked"
GUIDANCE_BINDING_REASSIGNED = "reassigned"
GUIDANCE_BINDING_HOLD = "hold"
ASSIGNMENT_PLAN_SCHEMA_V1 = "assignment_plan_v1"
ASSIGNMENT_PLAN_SCHEMA_V2 = "assignment_plan_v2"
PLAN_HISTORY_RECORD_SCHEMA_V1 = "d3_plan_history_record_v1"
ASSIGNMENT_CALIBRATION_PROFILE_SCHEMA_V1 = "d3_assignment_calibration_profile_v1"
TERMINAL_FEEDBACK_PROFILE_SCHEMA_V1 = "d3_terminal_feedback_profile_v1"
DEFAULT_COST_PROFILE_ID = "d3_hungarian_baseline"
DEFAULT_COST_PROFILE_VERSION = "1.0.0"
DEFAULT_FEEDBACK_PROFILE_ID = "d3_terminal_feedback_baseline"
DEFAULT_FEEDBACK_PROFILE_VERSION = "1.0.0"
SECONDARY_PLAN_SCHEMA_V2 = "secondary_plan_v2"
SECONDARY_PLAN_ACTIVE_STATE = "secondary_plan_active"
SECONDARY_TAKEOVER_READY = "takeover_ready"
TERMINAL_AUTHORIZATION_PER_PRIMARY = "per_primary"
TERMINAL_AUTHORIZATION_SCOPES = frozenset({TERMINAL_AUTHORIZATION_PER_PRIMARY})
GUIDANCE_BINDING_STATES = frozenset(
    {
        GUIDANCE_BINDING_ACTIVE,
        GUIDANCE_BINDING_STALE,
        GUIDANCE_BINDING_REVOKED,
        GUIDANCE_BINDING_REASSIGNED,
        GUIDANCE_BINDING_HOLD,
    }
)


class CoordinationMode(str, Enum):
    INDEPENDENT = "independent"
    SIMULTANEOUS = "simultaneous"
    SEQUENTIAL = "sequential"
    HYBRID = "hybrid"


class CoalitionState(str, Enum):
    FORMING = "forming"
    COMMITTED = "committed"
    INCOMPLETE = "incomplete"
    REVOKED = "revoked"
    COMPLETED = "completed"


class CoalitionMemberRole(str, Enum):
    PRIMARY = "primary"
    RESERVE = "reserve"
    OBSERVER = "observer"
    RETRY = "retry"


class _FeedbackConstraintClass(str, Enum):
    NONE = "none"
    EDGE_SOFT = "resource_target_edge_soft"
    EDGE_HARD = "resource_target_edge_hard"
    RESOURCE_HARD = "resource_hard"
    TARGET_HARD = "target_hard"


@dataclass(frozen=True)
class TargetDemand:
    """Explicit multi-resource demand; absence means k=1 independent."""

    required_resource_count: int = 3
    primary_resource_count: int = 2
    coordination_mode: str = CoordinationMode.HYBRID.value
    required_capability_counts: Mapping[str, int] = field(default_factory=dict)
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    wave_interval_s: float = 0.0
    minimum_separation_s: float | None = None
    terminal_authorization_scope: str = TERMINAL_AUTHORIZATION_PER_PRIMARY
    arrival_coordination_required: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        count = int(self.required_resource_count)
        primary_count = int(self.primary_resource_count)
        mode = _enum_value(self.coordination_mode)
        if count < 1:
            raise ValueError("required_resource_count must be at least 1")
        if not 1 <= primary_count <= count:
            raise ValueError(
                "primary_resource_count must be between 1 and required_resource_count"
            )
        if mode not in {item.value for item in CoordinationMode}:
            raise ValueError(f"unsupported coordination_mode: {mode}")
        capability_counts = {
            str(capability): int(required)
            for capability, required in self.required_capability_counts.items()
            if int(required) > 0
        }
        if sum(capability_counts.values()) > count:
            raise ValueError("required capability counts cannot exceed resource demand")
        if (
            self.arrival_window_start_s is not None
            and self.arrival_window_end_s is not None
            and self.arrival_window_start_s > self.arrival_window_end_s
        ):
            raise ValueError("arrival window start must not exceed end")
        if self.wave_interval_s < 0.0:
            raise ValueError("wave_interval_s must be non-negative")
        if self.minimum_separation_s is not None and self.minimum_separation_s < 0.0:
            raise ValueError("minimum_separation_s must be non-negative")
        authorization_scope = str(self.terminal_authorization_scope).strip().lower()
        if authorization_scope not in TERMINAL_AUTHORIZATION_SCOPES:
            raise ValueError(
                f"unsupported terminal_authorization_scope: {authorization_scope}"
            )
        object.__setattr__(self, "required_resource_count", count)
        object.__setattr__(self, "primary_resource_count", primary_count)
        object.__setattr__(self, "coordination_mode", mode)
        object.__setattr__(self, "required_capability_counts", capability_counts)
        object.__setattr__(self, "terminal_authorization_scope", authorization_scope)
        object.__setattr__(
            self,
            "arrival_coordination_required",
            bool(self.arrival_coordination_required),
        )

    @classmethod
    def independent(cls) -> "TargetDemand":
        return cls(
            required_resource_count=1,
            primary_resource_count=1,
            coordination_mode="independent",
        )


def _enum_value(value: str | Enum) -> str:
    return str(value.value if isinstance(value, Enum) else value).strip().lower()


@dataclass(frozen=True)
class TargetTrack:
    """Abstract target state used by the offline assignment planner."""

    track_id: str
    threat_score: float
    covariance: float
    window_cost: float
    assignable: bool = True
    fov_difficulty_by_resource: Mapping[str, float] = field(default_factory=dict)
    conflict_risk_by_resource: Mapping[str, float] = field(default_factory=dict)
    feasibility_by_resource: Mapping[str, bool] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    hard_time_window: bool = False
    time_window_open_at_s: float | None = None
    time_window_close_at_s: float | None = None
    time_window_state: str | None = None
    time_window_by_resource: Mapping[str, Mapping[str, Any] | bool | str] = field(
        default_factory=dict
    )
    demand: TargetDemand | None = None
    position_ned: tuple[float, float, float] | None = None
    velocity_ned: tuple[float, float, float] | None = None
    position_covariance_ned: Any = None
    region_id: str | None = None
    candidate_resource_region_ids: tuple[str, ...] = ()
    friendly_conflict_by_resource: Mapping[str, bool] = field(default_factory=dict)

    @property
    def effective_demand(self) -> TargetDemand:
        """Return the explicit demand or the backward-compatible k=1 default."""

        return self.demand if self.demand is not None else TargetDemand.independent()


@dataclass(frozen=True)
class ResourceState:
    """Abstract resource state for candidate assignment planning."""

    resource_id: str
    status: str = "available"
    health_score: float = 1.0
    busy_until: float = 0.0
    operator_hold: bool = False
    load_penalty: float = 0.0
    fov_difficulty: float = 0.0
    conflict_risk: float = 0.0
    capability_class: str = "generic"
    energy_fraction: float = 1.0
    availability_score: float = 1.0
    current_load: float = 0.0
    history_failure_rate: float = 0.0
    intercept_feasibility_by_target: Mapping[str, bool] = field(default_factory=dict)
    intercept_feasibility_score_by_target: Mapping[str, float] = field(
        default_factory=dict
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)
    position_ned: tuple[float, float, float] | None = None
    velocity_ned: tuple[float, float, float] | None = None
    position_covariance_ned: Any = None
    max_speed_mps: float | None = None
    max_intercept_range_m: float | None = None
    region_id: str | None = None
    reachable_target_region_ids: tuple[str, ...] = ()
    assignment_capacity: int = 1


@dataclass(frozen=True)
class CostWeights:
    """Configurable weights for transparent cost terms."""

    window: float = 1.0
    covariance: float = 1.0
    threat: float = 1.0
    resource_state: float = 1.0
    fov: float = 1.0
    conflict: float = 1.0
    reachability_3d: float = 1.0
    region: float = 0.5


@dataclass(frozen=True)
class PlannerConfig:
    """Planner-level configuration for rolling assignment."""

    enable_hysteresis: bool = True
    delta: float = 0.2
    min_dwell: float = 2.0
    infeasible_penalty: float = 1_000_000.0
    unassigned_base_cost: float = 4.0
    high_threat_threshold: float = 0.7
    solver_name: str = "hungarian"
    human_authorization_state: str = "required"
    max_changes_per_window: int | None = None
    reassignment_switch_penalty: float = 0.0
    source_node_id: str = "d3_central"
    target_node_id: str | None = None
    link_type: str = "c2_direct"
    stale_after_s: float | None = None
    cost_profile_id: str = DEFAULT_COST_PROFILE_ID
    cost_profile_version: str = DEFAULT_COST_PROFILE_VERSION
    feedback_profile_id: str = DEFAULT_FEEDBACK_PROFILE_ID
    feedback_profile_version: str = DEFAULT_FEEDBACK_PROFILE_VERSION
    transient_feedback_dwell_frames: int = 2
    enable_candidate_sparsification: bool = False
    max_candidate_edges_per_target: int | None = None
    enforce_region_compatibility: bool = False
    max_intercept_time_s: float | None = None
    default_resource_speed_mps: float | None = None
    reachability_time_scale_s: float = 60.0
    covariance_trace_scale: float = 100.0
    cross_region_cost: float = 0.5

    @classmethod
    def scalable_3d(cls, **overrides: Any) -> "PlannerConfig":
        """Return the opt-in sparse three-dimensional rule profile."""

        values: dict[str, Any] = {
            "enable_candidate_sparsification": True,
            "max_candidate_edges_per_target": 12,
            "enforce_region_compatibility": True,
            "max_intercept_time_s": 900.0,
            "default_resource_speed_mps": 14.0,
            "reachability_time_scale_s": 300.0,
            "covariance_trace_scale": 100.0,
            "cost_profile_id": "d3_scalable_3d_rule",
            "cost_profile_version": "1.0.0",
        }
        values.update(overrides)
        return cls(**values)


@dataclass(frozen=True)
class Assignment:
    """One accepted abstract target-resource pair."""

    target_id: str
    resource_id: str
    cost: float
    cost_breakdown: CostBreakdown
    feasibility_state: str = "feasible"
    source_node_id: str | None = None
    target_node_id: str | None = None
    link_type: str | None = None
    plan_version: int | None = None
    stale_after_s: float | None = None
    terminal_feedback_state: str | None = None
    duplicate_terminal_lock_risk: bool = False
    coalition_id: str | None = None
    coalition_version: int | None = None
    member_role: str = CoalitionMemberRole.PRIMARY.value
    wave_id: int = 0
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    required_resource_count: int = 1
    terminal_authorization_scope: str = TERMINAL_AUTHORIZATION_PER_PRIMARY
    arrival_coordination_required: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CoalitionMember:
    """One admitted or tentative member in a target coalition."""

    resource_id: str
    member_role: str
    wave_id: int
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    required_capability_class: str | None = None
    executable: bool = True


@dataclass(frozen=True)
class DemandSatisfactionSummary:
    target_id: str
    demand_required: int
    demand_assigned: int
    demand_shortfall: int
    coalition_complete: bool
    coalition_id: str | None = None
    coalition_version: int | None = None
    primary_resource_count: int = 1


@dataclass(frozen=True)
class CoalitionSummary(DemandSatisfactionSummary):
    """Public coalition summary alias with demand satisfaction fields."""


@dataclass(frozen=True)
class CoalitionPlan:
    """Versioned all-or-none coalition admission result for one target."""

    coalition_id: str
    version: int
    target_id: str
    state: str
    coordination_mode: str
    required_resource_count: int
    assigned_resource_count: int
    shortfall: int
    complete: bool
    primary_resource_count: int = 1
    members: tuple[CoalitionMember, ...] = ()
    minimum_separation_s: float | None = None
    terminal_authorization_scope: str = TERMINAL_AUTHORIZATION_PER_PRIMARY
    arrival_coordination_required: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def epoch(self) -> int:
        """Coalition membership epoch; it advances only on member/role changes."""

        return self.version

    @property
    def summary(self) -> CoalitionSummary:
        return CoalitionSummary(
            target_id=self.target_id,
            demand_required=self.required_resource_count,
            demand_assigned=self.assigned_resource_count,
            demand_shortfall=self.shortfall,
            coalition_complete=self.complete,
            coalition_id=self.coalition_id,
            coalition_version=self.version,
            primary_resource_count=self.primary_resource_count,
        )


@dataclass(frozen=True)
class AssignmentPlan:
    """Versioned candidate assignment plan."""

    plan_id: str
    version: int
    window_id: int
    assignments: tuple[Assignment, ...]
    unassigned_target_ids: tuple[str, ...]
    total_cost: float
    created_at: float
    last_changed_at: float
    human_authorization_state: str = "required"
    decision_state: str = "accepted"
    changed: bool = True
    solver_name: str = "hungarian"
    previous_plan_id: str | None = None
    candidate_total_cost: float | None = None
    previous_total_cost_current: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    source_node_id: str | None = None
    target_node_id: str | None = None
    link_type: str | None = None
    stale_after_s: float | None = None
    terminal_feedback_state: str | None = None
    duplicate_terminal_lock_risk: bool = False
    resource_count: int = 0
    target_count: int = 0
    plan_schema: str = ASSIGNMENT_PLAN_SCHEMA_V2
    coalitions: tuple[CoalitionPlan, ...] = ()
    incomplete_target_ids: tuple[str, ...] = ()
    demand_summaries: tuple[DemandSatisfactionSummary, ...] = ()

    def assignment_map(self) -> dict[str, str]:
        """Return the legacy one-to-one map, rejecting multi-resource targets."""

        grouped = self.assignments_by_target()
        multi_resource = sorted(
            target_id for target_id, items in grouped.items() if len(items) != 1
        )
        if multi_resource:
            raise ValueError(
                "assignment_map is only valid for one-to-one plans; "
                f"multi-resource targets: {', '.join(multi_resource)}"
            )
        return {
            target_id: items[0].resource_id
            for target_id, items in grouped.items()
        }

    def assignments_by_target(self) -> dict[str, tuple[Assignment, ...]]:
        grouped: dict[str, list[Assignment]] = {}
        for assignment in self.assignments:
            grouped.setdefault(assignment.target_id, []).append(assignment)
        return {
            target_id: tuple(sorted(items, key=_assignment_sort_key))
            for target_id, items in sorted(grouped.items())
        }

    def assignment_by_resource(self) -> dict[str, Assignment]:
        result: dict[str, Assignment] = {}
        for assignment in self.assignments:
            if assignment.resource_id in result:
                raise ValueError(
                    "one resource cannot have multiple executable assignments: "
                    f"{assignment.resource_id}"
                )
            result[assignment.resource_id] = assignment
        return dict(sorted(result.items()))

    def assignment_signature(self) -> tuple[tuple[Any, ...], ...]:
        """Stable, ordering-independent executable assignment signature."""

        return tuple(sorted(_assignment_signature(item) for item in self.assignments))

    def execution_signature(self) -> tuple[Any, ...]:
        """Return the identity-driving executable semantics of this plan."""

        return (
            self.assignment_signature(),
            tuple(sorted(_coalition_execution_signature(item) for item in self.coalitions)),
            tuple(sorted(self.unassigned_target_ids)),
            tuple(sorted(self.incomplete_target_ids)),
            self.human_authorization_state,
            tuple(
                (key, _signature_value(self.metadata.get(key)))
                for key in _PLAN_EXECUTION_METADATA_KEYS
            ),
        )

    @property
    def stable_signature(self) -> tuple[tuple[Any, ...], ...]:
        return self.assignment_signature()

    @property
    def plan_version(self) -> int:
        """Alias used by cross-node messages."""

        return self.version


def _assignment_sort_key(assignment: Assignment) -> tuple[Any, ...]:
    return (
        assignment.wave_id,
        assignment.member_role,
        assignment.resource_id,
    )


def _assignment_signature(assignment: Assignment) -> tuple[Any, ...]:
    return (
        assignment.target_id,
        assignment.resource_id,
        assignment.coalition_id or "",
        -1 if assignment.coalition_version is None else assignment.coalition_version,
        assignment.member_role,
        assignment.wave_id,
        _optional_float_signature(assignment.arrival_window_start_s),
        _optional_float_signature(assignment.arrival_window_end_s),
        assignment.required_resource_count,
        assignment.terminal_authorization_scope,
        assignment.arrival_coordination_required,
        assignment.feasibility_state,
        assignment.source_node_id or "",
        assignment.target_node_id or "",
        assignment.link_type or "",
        tuple(
            (key, _signature_value(assignment.metadata.get(key)))
            for key in _ASSIGNMENT_EXECUTION_METADATA_KEYS
        ),
    )


def _optional_float_signature(value: float | None) -> tuple[bool, float]:
    return value is None, 0.0 if value is None else float(value)


_PLAN_EXECUTION_METADATA_KEYS = (
    "plan_schema",
    "plan_owner",
    "active_plan_owner",
    "owner_node_id",
    "current_plan_owner",
    "current_plan_owner_node_id",
    "secondary_takeover_state",
    "secondary_plan_executable",
    "secondary_activated_at_s",
    "secondary_lease_expires_at_s",
    "secondary_leader_epoch",
    "activation_state",
    "activation_at_s",
    "executable",
)

_ASSIGNMENT_EXECUTION_METADATA_KEYS = (
    "coordination_mode",
    "primary_resource_count",
    "minimum_separation_s",
    "terminal_authorization_scope",
    "arrival_coordination_required",
    "required_capability_class",
    "plan_owner",
    "active_plan_owner",
    "owner_node_id",
    "secondary_takeover_state",
    "secondary_plan_executable",
    "secondary_activated_at_s",
    "secondary_lease_expires_at_s",
    "secondary_leader_epoch",
    "activation_state",
    "activation_at_s",
    "executable",
)


def _coalition_execution_signature(coalition: CoalitionPlan) -> tuple[Any, ...]:
    return (
        coalition.target_id,
        coalition.coalition_id,
        coalition.version,
        coalition.state,
        coalition.coordination_mode,
        coalition.required_resource_count,
        coalition.assigned_resource_count,
        coalition.shortfall,
        coalition.complete,
        coalition.primary_resource_count,
        coalition.terminal_authorization_scope,
        coalition.arrival_coordination_required,
        _optional_float_signature(coalition.minimum_separation_s),
        tuple(
            sorted(
                (
                    member.resource_id,
                    member.member_role,
                    member.wave_id,
                    _optional_float_signature(member.arrival_window_start_s),
                    _optional_float_signature(member.arrival_window_end_s),
                    member.required_capability_class or "",
                    member.executable,
                )
                for member in coalition.members
            )
        ),
        _signature_value(coalition.metadata.get("demand_template")),
    )


def _signature_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return tuple(
            sorted((str(key), _signature_value(item)) for key, item in value.items())
        )
    if isinstance(value, (list, tuple)):
        return tuple(_signature_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(_signature_value(item) for item in value))
    if isinstance(value, float):
        return float(value)
    return value


@dataclass(frozen=True)
class AssignmentValiditySummary:
    """Compact D3 plan-validity summary for main/D4/D6 consumers."""

    plan_id: str
    version: int
    plan_age_s: float
    assignment_latency_s: float
    cost_margin: float
    stale_plan_version: bool
    duplicate_assignment_count: int
    unassigned_high_threat_count: int
    resource_count: int = 0
    target_count: int = 0
    assigned_count: int = 0
    hysteresis_reject_count: int = 0
    stale_reject_count: int = 0
    reassign_count: int = 0


@dataclass(frozen=True)
class AssignmentMismatchReplaySummary:
    """N/M replay summary for assignment calibration and D6 aggregation."""

    resource_count: int = 0
    target_count: int = 0
    assigned_count: int = 0
    unassigned_high_threat_count: int = 0
    hysteresis_reject_count: int = 0
    stale_reject_count: int = 0
    reassign_count: int = 0


@dataclass(frozen=True)
class IncrementalPlanningComparisonSummary:
    """Cost, latency, and stability comparison for incremental calibration."""

    incremental_applied: bool
    fallback_reason: str | None
    cost_delta: float
    cost_equivalent: bool
    assignment_equivalent: bool
    incremental_latency_ms: float
    full_latency_ms: float
    latency_ratio: float | None
    incremental_change_count: int
    full_change_count: int
    preserved_target_count: int
    preserved_assignment_count: int


@dataclass(frozen=True)
class TerminalFeedbackCalibrationSummary:
    """Conservative D5 feedback calibration summary.

    Suggestions are advisory only; this helper never mutates planner defaults.
    """

    seed_count: int
    assignment_record_count: int
    feedback_record_count: int
    duplicate_reject_count: int
    friend_reject_count: int
    fov_reject_count: int
    geometry_reject_count: int
    mismatch_replay_summary: AssignmentMismatchReplaySummary
    cost_suggestions: Mapping[str, str] = field(default_factory=dict)
    hysteresis_suggestions: Mapping[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    auto_apply_defaults: bool = False


@dataclass(frozen=True)
class AssignmentRecord:
    """D3-to-D6 assignment log record with D6-compatible field names."""

    timestamp: float
    plan_id: str
    version: int
    resource_id: str
    global_track_id: str | None
    cost_breakdown: Mapping[str, float] = field(default_factory=dict)
    authorization_state: str = "recorded"
    active: bool = True
    truth_id: str | None = None
    window_id: int | None = None
    decision_state: str | None = None
    changed: bool | None = None
    resource_count: int = 0
    target_count: int = 0
    assigned_count: int = 0
    identity_created_at_s: float | None = None
    last_evaluated_at_s: float | None = None
    unassigned_high_threat_count: int = 0
    hysteresis_reject_count: int = 0
    stale_reject_count: int = 0
    reassign_count: int = 0
    plan_churn_count: int = 0
    plan_rollback_detected: bool = False
    assignment_matrix_shape: tuple[int, int] | None = None
    coalition_id: str | None = None
    coalition_version: int | None = None
    coalition_epoch: int | None = None
    coalition_complete: bool | None = None
    member_role: str = CoalitionMemberRole.PRIMARY.value
    wave_id: int = 0
    activation_state: str = "active"
    assignment_validity_state: str = "current"
    terminal_authorization_scope: str = TERMINAL_AUTHORIZATION_PER_PRIMARY
    terminal_authorization_eligible: bool = True
    arrival_coordination_required: bool = False
    plan_owner: str | None = None
    active_plan_owner: str | None = None
    owner_node_id: str | None = None
    source_node_id: str | None = None
    target_node_id: str | None = None
    link_type: str | None = None
    plan_schema: str = ASSIGNMENT_PLAN_SCHEMA_V1
    replan_reason: str | None = None
    takeover_reason: str | None = None
    previous_plan_id: str | None = None
    previous_plan_version: int | None = None
    supersedes_plan_id: str | None = None
    supersedes_plan_version: int | None = None
    selected_secondary_node_id: str | None = None
    secondary_plan_version: int | None = None
    secondary_leader_epoch: int | None = None
    secondary_lease_expires_at_s: float | None = None
    secondary_takeover_state: str | None = None
    secondary_readiness_class: str | None = None
    secondary_readiness_sustained: bool | None = None
    secondary_activated_at_s: float | None = None
    total_cost: float | None = None
    candidate_total_cost: float | None = None
    previous_total_cost_current: float | None = None
    cost_margin: float | None = None
    stale_after_s: float | None = None
    stale_plan_rejected: bool = False
    stale_reject_reason: str | None = None
    latest_plan_id: str | None = None
    latest_plan_version: int | None = None
    hysteresis_state: str | None = None
    hysteresis_reason: str | None = None
    hysteresis_reasons: tuple[str, ...] = ()
    hysteresis_release_reason: str | None = None
    hysteresis_release_condition: str | None = None
    hysteresis_dwell_time_s: float | None = None
    hysteresis_min_dwell_s: float | None = None
    hysteresis_delta: float | None = None
    hysteresis_candidate_change_count: int | None = None
    hysteresis_max_changes_per_window: int | None = None
    hysteresis_improvement_ok: bool | None = None
    hysteresis_dwell_ok: bool | None = None
    hysteresis_change_limit_ok: bool | None = None
    hysteresis_high_threat_release: bool | None = None
    assignment_profile_schema: str = ASSIGNMENT_CALIBRATION_PROFILE_SCHEMA_V1
    cost_profile_id: str = DEFAULT_COST_PROFILE_ID
    cost_profile_version: str = DEFAULT_COST_PROFILE_VERSION
    feedback_profile_id: str = DEFAULT_FEEDBACK_PROFILE_ID
    feedback_profile_version: str = DEFAULT_FEEDBACK_PROFILE_VERSION
    cost_weights: Mapping[str, float] = field(default_factory=dict)
    planner_thresholds: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssignmentEvidenceExport:
    """Current-plan evidence bundle for D4/D6 replay and audit consumers."""

    plan_id: str
    version: int
    window_id: int
    current_plan_id: str
    current_plan_version: int
    resource_count: int
    target_count: int
    assigned_count: int
    identity_created_at_s: float | None = None
    last_evaluated_at_s: float | None = None
    plan_owner: str = "center"
    active_plan_owner: str = "center"
    owner_node_id: str | None = None
    source_node_id: str | None = None
    target_node_id: str | None = None
    link_type: str | None = None
    selected_secondary_node_id: str | None = None
    secondary_plan_version: int | None = None
    supersedes_plan_id: str | None = None
    supersedes_plan_version: int | None = None
    secondary_leader_epoch: int | None = None
    secondary_lease_expires_at_s: float | None = None
    secondary_takeover_state: str | None = None
    secondary_readiness_class: str | None = None
    secondary_readiness_sustained: bool | None = None
    secondary_activated_at_s: float | None = None
    cost_matrix_target_ids: tuple[str, ...] = ()
    cost_matrix_resource_ids: tuple[str, ...] = ()
    cost_matrix: tuple[tuple[float, ...], ...] = ()
    cost_breakdowns_by_edge: tuple[Mapping[str, Any], ...] = ()
    rejected_edges: tuple[Mapping[str, Any], ...] = ()
    stale_plan_rejected: bool = False
    stale_reject_reason: str | None = None
    latest_plan_id: str | None = None
    latest_plan_version: int | None = None
    assignment_profile_schema: str = ASSIGNMENT_CALIBRATION_PROFILE_SCHEMA_V1
    cost_profile_id: str = DEFAULT_COST_PROFILE_ID
    cost_profile_version: str = DEFAULT_COST_PROFILE_VERSION
    feedback_profile_id: str = DEFAULT_FEEDBACK_PROFILE_ID
    feedback_profile_version: str = DEFAULT_FEEDBACK_PROFILE_VERSION
    cost_weights: Mapping[str, float] = field(default_factory=dict)
    planner_thresholds: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanningTickHistoryRecord:
    """Canonical online record for exactly one D3 planning tick.

    ``sequence_index`` is supplied by main. History consumers order records by
    ``ordering_key``; D3 never infers cross-tick order from plan versions.
    """

    schema: str
    schema_version: int
    sequence_index: int
    ordering_key: tuple[int, float]
    timestamp: float
    plan_schema: str
    plan_id: str
    plan_version: int
    window_id: int
    changed: bool
    decision_state: str
    resource_count: int
    target_count: int
    assigned_count: int
    plan_owner: str
    active_plan_owner: str
    owner_node_id: str | None
    source_node_id: str | None
    selected_secondary_node_id: str | None
    secondary_plan_version: int | None
    secondary_leader_epoch: int | None
    secondary_lease_expires_at_s: float | None
    previous_plan_id: str | None
    previous_plan_version: int | None
    supersedes_plan_id: str | None
    supersedes_plan_version: int | None
    assignments: tuple[Mapping[str, Any], ...]
    coalitions: tuple[Mapping[str, Any], ...]
    hysteresis: Mapping[str, Any]
    membership_change_records: tuple[Mapping[str, Any], ...]
    feedback_constraints: Mapping[str, Any]
    total_cost: float
    candidate_total_cost: float | None
    previous_total_cost_current: float | None
    stale_plan_rejected: bool
    stale_reject_reason: str | None
    latest_plan_id: str | None
    latest_plan_version: int | None
    rollback_detected: bool
    rollback_reason: str | None
    replan_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic, JSON-native mapping without truth fields."""

        payload = {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "sequence_index": self.sequence_index,
            "ordering_key": self.ordering_key,
            "timestamp": self.timestamp,
            "plan_schema": self.plan_schema,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "window_id": self.window_id,
            "changed": self.changed,
            "decision_state": self.decision_state,
            "resource_count": self.resource_count,
            "target_count": self.target_count,
            "assigned_count": self.assigned_count,
            "plan_owner": self.plan_owner,
            "active_plan_owner": self.active_plan_owner,
            "owner_node_id": self.owner_node_id,
            "source_node_id": self.source_node_id,
            "selected_secondary_node_id": self.selected_secondary_node_id,
            "secondary_plan_version": self.secondary_plan_version,
            "secondary_leader_epoch": self.secondary_leader_epoch,
            "secondary_lease_expires_at_s": self.secondary_lease_expires_at_s,
            "previous_plan_id": self.previous_plan_id,
            "previous_plan_version": self.previous_plan_version,
            "supersedes_plan_id": self.supersedes_plan_id,
            "supersedes_plan_version": self.supersedes_plan_version,
            "assignments": self.assignments,
            "coalitions": self.coalitions,
            "hysteresis": self.hysteresis,
            "membership_change_records": self.membership_change_records,
            "feedback_constraints": self.feedback_constraints,
            "total_cost": self.total_cost,
            "candidate_total_cost": self.candidate_total_cost,
            "previous_total_cost_current": self.previous_total_cost_current,
            "stale_plan_rejected": self.stale_plan_rejected,
            "stale_reject_reason": self.stale_reject_reason,
            "latest_plan_id": self.latest_plan_id,
            "latest_plan_version": self.latest_plan_version,
            "rollback_detected": self.rollback_detected,
            "rollback_reason": self.rollback_reason,
            "replan_reason": self.replan_reason,
        }
        normalized = _history_json_value(payload)
        if not isinstance(normalized, dict):
            raise TypeError("planning history payload must be a mapping")
        return normalized


@dataclass(frozen=True)
class ThreatScoreBaseline:
    """Explainable baseline threat score assembled from simple scene terms."""

    threat_score: float
    components: Mapping[str, float] = field(default_factory=dict)
    weights: Mapping[str, float] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssignmentGuidanceBinding:
    """Versioned D3-to-D7 binding for simulation guidance.

    This passive DTO carries the center-owned assignment identity into D7. It
    does not contain control parameters and does not authorize local rebinds.
    """

    binding_id: str
    plan_id: str
    plan_version: int
    resource_id: str
    assigned_global_track_id: str
    target_id: str
    authorization_state: str = "required"
    guidance_phase: str = "radar_midcourse"
    plan_schema: str = ASSIGNMENT_PLAN_SCHEMA_V1
    binding_state: str = "active"
    created_at: float = 0.0
    stale_after_s: float | None = None
    vehicle_name: str | None = None
    source_node_id: str | None = None
    target_node_id: str | None = None
    link_type: str | None = None
    revoke_reason: str | None = None
    resource_actor_name: str | None = None
    target_actor_name: str | None = None
    target_object_id: str | None = None
    target_mesh_aliases: tuple[str, ...] = ()
    actor_aliases: Mapping[str, Any] = field(default_factory=dict)
    coalition_id: str | None = None
    coalition_version: int | None = None
    member_role: str = CoalitionMemberRole.PRIMARY.value
    wave_id: int = 0
    coordination_mode: str = CoordinationMode.INDEPENDENT.value
    primary_resource_count: int = 1
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    minimum_separation_s: float | None = None
    terminal_authorization_scope: str = TERMINAL_AUTHORIZATION_PER_PRIMARY
    arrival_coordination_required: bool = False
    last_evaluated_at_s: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def assignment_id(self) -> str:
        """Alias consumed by D7's assignment-like dry-run adapter."""

        return self.binding_id

    @property
    def id(self) -> str:
        """Generic identifier alias for assignment-like consumers."""

        return self.binding_id

    @property
    def version(self) -> int:
        """Alias for consumers that expect `version` instead of `plan_version`."""

        return self.plan_version

    @property
    def track_version(self) -> int:
        """D7-compatible track/assignment version alias."""

        return self.plan_version

    @property
    def assignment_validity_state(self) -> str:
        """D7-compatible validity state derived from binding state."""

        if self.binding_state == GUIDANCE_BINDING_ACTIVE:
            return "current"
        if self.binding_state == GUIDANCE_BINDING_REASSIGNED:
            return "superseded"
        return self.binding_state

    @property
    def created_at_s(self) -> float:
        return self.created_at

    @property
    def expires_at_s(self) -> float | None:
        if self.stale_after_s is None:
            return None
        freshness_base_s = (
            self.created_at
            if self.last_evaluated_at_s is None
            else self.last_evaluated_at_s
        )
        return freshness_base_s + self.stale_after_s

    @property
    def owner(self) -> str:
        """D7-compatible owner alias for the assigned resource."""

        return self.resource_id

    @property
    def assigned_resource_id(self) -> str:
        """Explicit resource alias for assignment-like adapters."""

        return self.resource_id

    @property
    def global_track_id(self) -> str:
        """Target-track alias; must remain equal to `assigned_global_track_id`."""

        return self.assigned_global_track_id

    @property
    def human_authorization_state(self) -> str:
        """Alias used by existing D7 dry-run metadata extraction."""

        return self.authorization_state

    @property
    def source(self) -> str | None:
        """Short alias for the issuing node."""

        return self.source_node_id

    @property
    def target(self) -> str | None:
        """Short alias for the receiving node/resource group."""

        return self.target_node_id

    @property
    def link(self) -> str | None:
        """Short alias for the communication link type."""

        return self.link_type

    @property
    def is_active(self) -> bool:
        return self.binding_state == GUIDANCE_BINDING_ACTIVE

    def to_assignment_metadata(self) -> dict[str, Any]:
        """Return a plain mapping suitable for D7 assignment-like inputs."""

        return {
            "assignment_id": self.assignment_id,
            "id": self.id,
            "binding_id": self.binding_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "version": self.version,
            "track_version": self.track_version,
            "resource_id": self.resource_id,
            "owner": self.owner,
            "assigned_resource_id": self.assigned_resource_id,
            "target_id": self.target_id,
            "assigned_global_track_id": self.assigned_global_track_id,
            "global_track_id": self.global_track_id,
            "authorization_state": self.authorization_state,
            "human_authorization_state": self.human_authorization_state,
            "guidance_phase": self.guidance_phase,
            "plan_schema": self.plan_schema,
            "binding_state": self.binding_state,
            "assignment_validity_state": self.assignment_validity_state,
            "created_at_s": self.created_at_s,
            "identity_created_at_s": self.created_at_s,
            "last_evaluated_at_s": (
                self.created_at_s
                if self.last_evaluated_at_s is None
                else self.last_evaluated_at_s
            ),
            "expires_at_s": self.expires_at_s,
            "vehicle_name": self.vehicle_name,
            "resource_actor_name": self.resource_actor_name,
            "target_actor_name": self.target_actor_name,
            "target_object_id": self.target_object_id,
            "target_mesh_aliases": list(self.target_mesh_aliases),
            "actor_aliases": dict(self.actor_aliases),
            "coalition_id": self.coalition_id,
            "coalition_version": self.coalition_version,
            "member_role": self.member_role,
            "wave_id": self.wave_id,
            "coordination_mode": self.coordination_mode,
            "primary_resource_count": self.primary_resource_count,
            "arrival_window_start_s": self.arrival_window_start_s,
            "arrival_window_end_s": self.arrival_window_end_s,
            "minimum_separation_s": self.minimum_separation_s,
            "terminal_authorization_scope": self.terminal_authorization_scope,
            "arrival_coordination_required": self.arrival_coordination_required,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "link_type": self.link_type,
            "source": self.source,
            "target": self.target,
            "link": self.link,
            "revoke_reason": self.revoke_reason,
            **dict(self.metadata),
        }


def guidance_bindings_from_assignment_plan(
    plan: AssignmentPlan,
    *,
    resource_vehicle_map: Mapping[str, str] | None = None,
    target_alias_map: Mapping[str, Mapping[str, Any]] | None = None,
    guidance_phase: str = "radar_midcourse",
    now_s: float | None = None,
    revoked_plan_versions: set[int] | frozenset[int] = frozenset(),
    previous_plan: AssignmentPlan | None = None,
    hold_resource_ids: set[str] | frozenset[str] = frozenset(),
    current_plan_id: str | None = None,
    current_plan_version: int | None = None,
) -> tuple[AssignmentGuidanceBinding, ...]:
    """Build passive D7 guidance bindings from one versioned D3 plan.

    Secondary plans require an explicit current plan identity. Historical plans
    remain exportable for audit, but their bindings are stale and therefore
    cannot drive D7.
    """

    if (current_plan_id is None) != (current_plan_version is None):
        raise ValueError("current plan id and version must be supplied together")

    resource_vehicle_map = resource_vehicle_map or {}
    target_alias_map = target_alias_map or {}
    now = plan.created_at if now_s is None else float(now_s)
    plan_schema = _plan_schema(plan)
    previous_by_resource = (
        {item.resource_id: item.target_id for item in previous_plan.assignments}
        if previous_plan is not None
        else {}
    )
    plan_metadata = dict(plan.metadata)
    identity_created_at_s = _metadata_float(
        plan_metadata.get("identity_created_at_s")
    )
    if identity_created_at_s is None:
        identity_created_at_s = plan.created_at
    last_evaluated_at_s = _metadata_float(
        plan_metadata.get("last_evaluated_at_s")
    )
    if last_evaluated_at_s is None:
        last_evaluated_at_s = plan.created_at
    plan_owner = _metadata_text(plan_metadata, "plan_owner") or "center"
    active_plan_owner = (
        _metadata_text(plan_metadata, "active_plan_owner") or plan_owner
    )
    owner_node_id = (
        _metadata_text(plan_metadata, "owner_node_id")
        or _metadata_text(plan_metadata, "source_node_id")
        or plan.source_node_id
    )
    current_identity_confirmed = (
        current_plan_id == plan.plan_id and current_plan_version == plan.version
        if current_plan_id is not None
        else plan_schema != SECONDARY_PLAN_SCHEMA_V2
    )
    secondary_takeover_active = (
        plan_schema != SECONDARY_PLAN_SCHEMA_V2
        or (
            _metadata_text(plan_metadata, "secondary_takeover_state")
            == SECONDARY_PLAN_ACTIVE_STATE
            and _metadata_text(plan_metadata, "secondary_readiness_class")
            == SECONDARY_TAKEOVER_READY
            and _metadata_bool(plan_metadata.get("secondary_readiness_sustained"))
            and _metadata_bool(plan_metadata.get("secondary_plan_executable"))
        )
    )
    secondary_lease_expires_at_s = _metadata_float(
        plan_metadata.get("secondary_lease_expires_at_s")
    )
    secondary_lease_expired = (
        plan_schema == SECONDARY_PLAN_SCHEMA_V2
        and secondary_lease_expires_at_s is not None
        and now > secondary_lease_expires_at_s
    )
    coalition_by_id = {
        coalition.coalition_id: coalition for coalition in plan.coalitions
    }
    plan_churn_count = _metadata_int(plan_metadata.get("plan_churn_count"))
    if plan_churn_count is None:
        plan_churn_count = _reassign_count(plan, previous_plan=previous_plan)
    plan_rollback_detected = _metadata_bool(
        plan_metadata.get("plan_rollback_detected")
    ) or (
        previous_plan is not None and plan.version < previous_plan.version
    )
    stale_reject_count = _stale_reject_count(plan)

    bindings: list[AssignmentGuidanceBinding] = []
    for index, assignment in enumerate(plan.assignments, start=1):
        target_id = assignment.target_id
        aliases = target_alias_map.get(target_id, {})
        stale_after_s = assignment.stale_after_s or plan.stale_after_s
        stale = (
            stale_after_s is not None
            and now > last_evaluated_at_s + stale_after_s
        )
        previous_target_id = previous_by_resource.get(assignment.resource_id)
        reassigned = previous_target_id not in {None, target_id}
        binding_state = _guidance_binding_state(
            plan=plan,
            assignment=assignment,
            stale=stale,
            revoked_plan_versions=revoked_plan_versions,
            hold_resource_ids=hold_resource_ids,
            reassigned=reassigned,
        )
        revoke_reason = _guidance_revoke_reason(
            plan=plan,
            assignment=assignment,
            stale=stale,
            revoked_plan_versions=revoked_plan_versions,
            hold_resource_ids=hold_resource_ids,
        )
        if not current_identity_confirmed:
            binding_state = GUIDANCE_BINDING_STALE
            revoke_reason = "not_current_assignment_plan"
        elif not secondary_takeover_active:
            binding_state = GUIDANCE_BINDING_HOLD
            revoke_reason = "secondary_takeover_not_active"
        elif secondary_lease_expired:
            binding_state = GUIDANCE_BINDING_STALE
            revoke_reason = "secondary_plan_lease_expired"
        coalition = (
            coalition_by_id.get(assignment.coalition_id)
            if assignment.coalition_id is not None
            else None
        )
        if assignment.coalition_id is not None and (
            coalition is None
            or coalition.version != assignment.coalition_version
            or coalition.state != CoalitionState.COMMITTED.value
            or not coalition.complete
        ):
            binding_state = GUIDANCE_BINDING_HOLD
            revoke_reason = "coalition_not_committed"
        if (
            assignment.member_role == CoalitionMemberRole.RESERVE.value
            and binding_state == GUIDANCE_BINDING_ACTIVE
        ):
            binding_state = GUIDANCE_BINDING_HOLD
            revoke_reason = "reserve_standby_not_activated"
        resource_actor_name = _resource_actor_name(
            resource_id=assignment.resource_id,
            vehicle_name=resource_vehicle_map.get(assignment.resource_id),
            metadata=assignment.metadata,
        )
        actor_aliases = _actor_aliases(
            resource_id=assignment.resource_id,
            target_id=target_id,
            resource_actor_name=resource_actor_name,
            aliases=aliases,
        )

        bindings.append(
            AssignmentGuidanceBinding(
                binding_id=f"{plan.plan_id}:v{plan.version}:{assignment.resource_id}:{target_id}:{index}",
                plan_id=plan.plan_id,
                plan_version=plan.version,
                resource_id=assignment.resource_id,
                vehicle_name=resource_actor_name,
                assigned_global_track_id=target_id,
                target_id=target_id,
                authorization_state=plan.human_authorization_state,
                guidance_phase=guidance_phase,
                plan_schema=plan_schema,
                binding_state=binding_state,
                created_at=plan.created_at,
                stale_after_s=stale_after_s,
                source_node_id=assignment.source_node_id or plan.source_node_id,
                target_node_id=assignment.target_node_id or plan.target_node_id,
                link_type=assignment.link_type or plan.link_type,
                revoke_reason=revoke_reason,
                resource_actor_name=resource_actor_name,
                target_actor_name=_optional_alias(aliases, "target_actor_name", "actor_name"),
                target_object_id=_optional_alias(aliases, "target_object_id", "object_id"),
                target_mesh_aliases=_mesh_aliases(aliases),
                actor_aliases=actor_aliases,
                coalition_id=assignment.coalition_id,
                coalition_version=assignment.coalition_version,
                member_role=assignment.member_role,
                wave_id=assignment.wave_id,
                coordination_mode=(
                    coalition.coordination_mode
                    if coalition is not None
                    else CoordinationMode.INDEPENDENT.value
                ),
                primary_resource_count=(
                    coalition.primary_resource_count if coalition is not None else 1
                ),
                arrival_window_start_s=assignment.arrival_window_start_s,
                arrival_window_end_s=assignment.arrival_window_end_s,
                minimum_separation_s=(
                    coalition.minimum_separation_s if coalition is not None else None
                ),
                terminal_authorization_scope=(
                    assignment.terminal_authorization_scope
                ),
                arrival_coordination_required=(
                    assignment.arrival_coordination_required
                ),
                last_evaluated_at_s=last_evaluated_at_s,
                metadata={
                    "assignment_cost": assignment.cost,
                    "assignment_feasibility_state": assignment.feasibility_state,
                    "current_plan_id": plan.plan_id,
                    "current_plan_version": plan.version,
                    "identity_created_at_s": identity_created_at_s,
                    "last_evaluated_at_s": last_evaluated_at_s,
                    "plan_owner": plan_owner,
                    "active_plan_owner": active_plan_owner,
                    "owner_node_id": owner_node_id,
                    "coalition_epoch": (
                        coalition.epoch if coalition is not None else None
                    ),
                    "coalition_complete": (
                        coalition.complete if coalition is not None else None
                    ),
                    "activation_state": (
                        "standby"
                        if assignment.member_role == CoalitionMemberRole.RESERVE.value
                        else "active"
                    ),
                    "executable": (
                        assignment.member_role != CoalitionMemberRole.RESERVE.value
                        and binding_state == GUIDANCE_BINDING_ACTIVE
                    ),
                    "terminal_authorization_eligible": (
                        assignment.member_role == CoalitionMemberRole.PRIMARY.value
                        and binding_state == GUIDANCE_BINDING_ACTIVE
                    ),
                    "terminal_authorization_scope": (
                        assignment.terminal_authorization_scope
                    ),
                    "arrival_coordination_required": (
                        assignment.arrival_coordination_required
                    ),
                    "selected_secondary_node_id": _metadata_text(
                        plan_metadata,
                        "selected_secondary_node_id",
                    ),
                    "secondary_plan_version": _metadata_int(
                        plan_metadata.get("secondary_plan_version")
                    ),
                    "plan_churn_count": plan_churn_count,
                    "plan_rollback_detected": plan_rollback_detected,
                    "stale_plan_rejected": _metadata_bool(
                        plan_metadata.get("stale_plan_rejected")
                    ),
                    "stale_reject_count": stale_reject_count,
                    "secondary_takeover_state": _metadata_text(
                        plan_metadata,
                        "secondary_takeover_state",
                    ),
                    "secondary_readiness_class": _metadata_text(
                        plan_metadata,
                        "secondary_readiness_class",
                    ),
                    "secondary_readiness_sustained": _metadata_bool_optional(
                        plan_metadata.get("secondary_readiness_sustained")
                    ),
                    "secondary_leader_epoch": _metadata_int(
                        plan_metadata.get("secondary_leader_epoch")
                    ),
                    "secondary_lease_expires_at_s": secondary_lease_expires_at_s,
                    "secondary_activated_at_s": _metadata_float(
                        plan_metadata.get("secondary_activated_at_s")
                    ),
                    "expected_current_plan_id": current_plan_id,
                    "expected_current_plan_version": current_plan_version,
                    "current_identity_confirmed": current_identity_confirmed,
                    "supersedes_plan_id": _metadata_text(
                        plan_metadata,
                        "supersedes_plan_id",
                    ),
                    "supersedes_plan_version": _metadata_int(
                        plan_metadata.get("supersedes_plan_version")
                    ),
                    "plan_schema": plan_schema,
                    "plan_decision_state": plan.decision_state,
                    "previous_plan_id": plan.previous_plan_id,
                    "previous_target_for_resource": previous_target_id,
                    "resource_reassigned": reassigned,
                    "coalition_id": assignment.coalition_id,
                    "coalition_version": assignment.coalition_version,
                    "member_role": assignment.member_role,
                    "wave_id": assignment.wave_id,
                    "coordination_mode": (
                        coalition.coordination_mode
                        if coalition is not None
                        else CoordinationMode.INDEPENDENT.value
                    ),
                    "primary_resource_count": (
                        coalition.primary_resource_count if coalition is not None else 1
                    ),
                    "arrival_window_start_s": assignment.arrival_window_start_s,
                    "arrival_window_end_s": assignment.arrival_window_end_s,
                    "minimum_separation_s": (
                        coalition.minimum_separation_s if coalition is not None else None
                    ),
                    "allow_local_rebind": False,
                },
            )
        )
    return tuple(bindings)


@dataclass(frozen=True)
class AssignmentFeedbackDecision:
    """D3 recommendation after terminal feedback or duplicate-lock risk."""

    recommended_action: str
    terminal_feedback_state: str
    duplicate_terminal_lock_risk: bool = False
    allow_local_rebind: bool = False
    reasons: tuple[str, ...] = ()
    plan_version: int | None = None
    main_action: str = "continue"
    planner_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TerminalFeedbackWriteback:
    """Next-round D3 inputs after applying conservative D5 feedback metadata."""

    tracks: tuple[TargetTrack, ...]
    resources: tuple[ResourceState, ...]
    prohibited_edges: tuple[Mapping[str, str], ...] = ()
    hold_resource_ids: tuple[str, ...] = ()
    updated_target_ids: tuple[str, ...] = ()
    updated_resource_ids: tuple[str, ...] = ()
    d7_gate_action: str = "continue"
    d4_requests: tuple[str, ...] = ()
    allow_local_rebind: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    hard_target_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SolverAssignment:
    """Index-level solver output for a real target-resource edge."""

    target_index: int
    resource_index: int
    cost: float


@dataclass(frozen=True)
class SolverResult:
    """Solver output including explicit unassigned targets."""

    assignments: tuple[SolverAssignment, ...]
    unassigned_target_indices: tuple[int, ...]
    objective_value: float
    solver_name: str
    status: str = "optimal"


def compose_threat_score_baseline(
    *,
    target_state: str = "confirmed",
    distance_to_critical_zone_m: float | None = None,
    time_to_critical_zone_s: float | None = None,
    speed_mps: float | None = None,
    covariance: float | Mapping[str, Any] | Iterable[Any] | None = None,
    position_ned: Iterable[float] | None = None,
    velocity_ned: Iterable[float] | None = None,
    critical_zone_center_ned: Iterable[float] | None = None,
    critical_zone_radius_m: float = 0.0,
    proximity_horizon_m: float = 500.0,
    ttc_horizon_s: float = 60.0,
    ttc_urgent_s: float = 5.0,
    speed_reference_mps: float = 40.0,
    weights: Mapping[str, float] | None = None,
) -> ThreatScoreBaseline:
    """Compose a minimal explainable target threat baseline.

    This is intentionally a baseline composer, not a full threat assessment
    model. It combines proximity to a protected/critical zone, TTC, speed,
    covariance uncertainty, and target state into a normalized score.
    """

    position = _vector3(position_ned)
    velocity = _vector3(velocity_ned)
    center = _vector3(critical_zone_center_ned)

    computed_distance = None
    if distance_to_critical_zone_m is not None:
        computed_distance = float(distance_to_critical_zone_m)
    elif position is not None and center is not None:
        computed_distance = max(
            0.0,
            _distance(position, center) - max(0.0, float(critical_zone_radius_m)),
        )

    computed_speed = (
        float(speed_mps)
        if speed_mps is not None
        else _speed(velocity)
        if velocity is not None
        else None
    )
    computed_ttc = (
        float(time_to_critical_zone_s)
        if time_to_critical_zone_s is not None
        else _time_to_critical_zone(
            position=position,
            velocity=velocity,
            center=center,
            distance_to_critical_zone_m=computed_distance,
        )
    )

    component_weights = dict(
        weights
        or {
            "critical_zone_proximity": 0.30,
            "time_to_critical_zone": 0.30,
            "speed": 0.15,
            "covariance": 0.10,
            "target_state": 0.15,
        }
    )
    components = {
        "critical_zone_proximity": _proximity_component(
            computed_distance,
            proximity_horizon_m=proximity_horizon_m,
        ),
        "time_to_critical_zone": _ttc_component(
            computed_ttc,
            ttc_horizon_s=ttc_horizon_s,
            ttc_urgent_s=ttc_urgent_s,
        ),
        "speed": _speed_component(
            computed_speed,
            speed_reference_mps=speed_reference_mps,
        ),
        "covariance": _covariance_component(covariance),
        "target_state": _target_state_component(target_state),
    }
    score = _weighted_component_score(components, component_weights)
    reasons = _threat_baseline_reasons(components, target_state)
    return ThreatScoreBaseline(
        threat_score=score,
        components=components,
        weights=component_weights,
        reasons=reasons,
        metadata={
            "target_state": str(target_state).strip().lower(),
            "distance_to_critical_zone_m": computed_distance,
            "time_to_critical_zone_s": computed_ttc,
            "speed_mps": computed_speed,
            "critical_zone_radius_m": float(critical_zone_radius_m),
            "baseline": "d3_explainable_threat_score_v1",
        },
    )


def evaluate_terminal_feedback(
    terminal_feedback_state: str | None,
    duplicate_terminal_lock_risk: bool = False,
    plan_version: int | None = None,
    *,
    resource_id: str | None = None,
    target_id: str | None = None,
    feedback_profile_id: str = DEFAULT_FEEDBACK_PROFILE_ID,
    feedback_profile_version: str = DEFAULT_FEEDBACK_PROFILE_VERSION,
) -> AssignmentFeedbackDecision:
    """Return a conservative D3 recommendation for terminal feedback.

    The result never permits a local resource to rewrite `global_track_id`; it
    only recommends hold, central replan, or D4 secondary arbitration.
    """

    state = (terminal_feedback_state or "consistent").strip().lower()
    reasons: list[str] = []

    if duplicate_terminal_lock_risk:
        reasons.append("duplicate_terminal_lock_risk")
        return _feedback_decision(
            action="secondary_arbitration",
            state=state,
            duplicate_terminal_lock_risk=True,
            reasons=reasons,
            plan_version=plan_version,
            resource_id=resource_id,
            target_id=target_id,
            feedback_profile_id=feedback_profile_id,
            feedback_profile_version=feedback_profile_version,
        )

    if state in TERMINAL_FEEDBACK_ARBITRATION_STATES:
        reasons.append(f"terminal_feedback_{state}")
        return _feedback_decision(
            action="secondary_arbitration",
            state=state,
            reasons=reasons,
            plan_version=plan_version,
            resource_id=resource_id,
            target_id=target_id,
            feedback_profile_id=feedback_profile_id,
            feedback_profile_version=feedback_profile_version,
        )
    if state in TERMINAL_FEEDBACK_REPLAN_STATES:
        reasons.append(f"terminal_feedback_{state}")
        return _feedback_decision(
            action="replan",
            state=state,
            reasons=reasons,
            plan_version=plan_version,
            resource_id=resource_id,
            target_id=target_id,
            feedback_profile_id=feedback_profile_id,
            feedback_profile_version=feedback_profile_version,
        )
    if state in TERMINAL_FEEDBACK_HOLD_STATES:
        reasons.append(f"terminal_feedback_{state}")
        return _feedback_decision(
            action="hold",
            state=state,
            reasons=reasons,
            plan_version=plan_version,
            resource_id=resource_id,
            target_id=target_id,
            feedback_profile_id=feedback_profile_id,
            feedback_profile_version=feedback_profile_version,
        )

    return _feedback_decision(
        action="continue",
        state=state,
        reasons=["terminal_feedback_consistent"],
        plan_version=plan_version,
        resource_id=resource_id,
        target_id=target_id,
        feedback_profile_id=feedback_profile_id,
        feedback_profile_version=feedback_profile_version,
    )


def apply_terminal_feedback_to_planner_inputs(
    tracks: Iterable[TargetTrack],
    resources: Iterable[ResourceState],
    feedback_metadata: (
        AssignmentFeedbackDecision
        | Mapping[str, Any]
        | Iterable[AssignmentFeedbackDecision | Mapping[str, Any]]
        | None
    ),
    *,
    fov_cap: float = 1.0,
    feedback_profile_id: str | None = None,
    feedback_profile_version: str | None = None,
) -> TerminalFeedbackWriteback:
    """Apply D5 feedback metadata to the next D3 planning inputs.

    This helper only maps already-authoritative metadata into D3's own input
    DTOs. It does not infer visual identity, choose a secondary node, or allow
    local `global_track_id` rebinding.
    """

    track_tuple = tuple(tracks)
    resource_tuple = tuple(resources)
    metadata_items = _feedback_metadata_items(feedback_metadata)
    resolved_feedback_profile_id = _resolve_profile_value(
        explicit_value=feedback_profile_id,
        metadata_items=metadata_items,
        key="feedback_profile_id",
        default=DEFAULT_FEEDBACK_PROFILE_ID,
    )
    resolved_feedback_profile_version = _resolve_profile_value(
        explicit_value=feedback_profile_version,
        metadata_items=metadata_items,
        key="feedback_profile_version",
        default=DEFAULT_FEEDBACK_PROFILE_VERSION,
    )
    if not metadata_items:
        return TerminalFeedbackWriteback(
            tracks=track_tuple,
            resources=resource_tuple,
            metadata={
                "feedback_count": 0,
                "allow_local_rebind": False,
                "feedback_profile_schema": TERMINAL_FEEDBACK_PROFILE_SCHEMA_V1,
                "feedback_profile_id": resolved_feedback_profile_id,
                "feedback_profile_version": resolved_feedback_profile_version,
                "fov_cap": float(fov_cap),
                "feedback_constraint_classification_schema": (
                    _FEEDBACK_CONSTRAINT_CLASSIFICATION_SCHEMA_V1
                ),
                "feedback_classifications": (),
            },
        )

    target_feasibility: dict[str, dict[str, bool]] = {}
    target_fov: dict[str, dict[str, float]] = {}
    target_feedback_events: dict[str, list[Mapping[str, Any]]] = {}
    hold_resource_ids: list[str] = []
    hold_resource_set: set[str] = set()
    hard_target_ids: list[str] = []
    hard_target_set: set[str] = set()
    prohibited_edges: list[tuple[str, str]] = []
    prohibited_edge_set: set[tuple[str, str]] = set()
    feedback_classifications: list[Mapping[str, Any]] = []
    d4_requests: list[str] = []
    d7_gate_action = "continue"

    def add_hold(resource_id: str | None) -> None:
        if resource_id and resource_id not in hold_resource_set:
            hold_resource_set.add(resource_id)
            hold_resource_ids.append(resource_id)

    def add_hard_target(target_id: str | None) -> None:
        if target_id and target_id not in hard_target_set:
            hard_target_set.add(target_id)
            hard_target_ids.append(target_id)

    def add_prohibited_edge(target_id: str | None, resource_id: str | None) -> None:
        if not target_id or not resource_id:
            return
        edge = (target_id, resource_id)
        if edge not in prohibited_edge_set:
            prohibited_edge_set.add(edge)
            prohibited_edges.append(edge)
        target_feasibility.setdefault(target_id, {})[resource_id] = False

    def add_fov(target_id: str | None, resource_id: str | None, value: Any) -> None:
        if not target_id or not resource_id:
            return
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = fov_cap
        target_fov.setdefault(target_id, {})[resource_id] = max(
            target_fov.get(target_id, {}).get(resource_id, 0.0),
            _clamp01_model(numeric_value),
        )

    for metadata in metadata_items:
        target_id = _metadata_text(
            metadata,
            "target_id",
            "global_track_id",
            "assigned_global_track_id",
        )
        resource_id = _metadata_text(
            metadata,
            "resource_id",
            "assigned_resource_id",
            "owner",
        )
        resource_update = metadata.get("resource_update")
        if resource_id is None and isinstance(resource_update, Mapping):
            resource_id = _metadata_text(resource_update, "resource_id")
        action = _metadata_text(
            metadata,
            "main_action",
            "planner_recommended_action",
            "recommended_action",
        )
        terminal_state = _metadata_text(metadata, "terminal_feedback_state")
        fov_suggestion = _metadata_text(metadata, "fov_difficulty_suggestion")
        feasibility_suggestion = _metadata_text(metadata, "feasibility_suggestion")
        d4_request = _metadata_text(metadata, "d4_request")
        gate_action = _metadata_text(metadata, "d7_gate_action")

        constraint_class, classification_reason = _classify_feedback_constraint(
            metadata,
            target_id=target_id,
            resource_id=resource_id,
            terminal_state=terminal_state,
            action=action,
        )
        constraint_scope = _feedback_constraint_scope(constraint_class)
        feedback_classifications.append(
            {
                "target_id": target_id,
                "resource_id": resource_id,
                "terminal_feedback_state": terminal_state,
                "constraint_class": constraint_class.value,
                "constraint_scope": constraint_scope,
                "classification_reason": classification_reason,
                "hard_reject": constraint_class
                in {
                    _FeedbackConstraintClass.EDGE_HARD,
                    _FeedbackConstraintClass.RESOURCE_HARD,
                    _FeedbackConstraintClass.TARGET_HARD,
                },
            }
        )

        feedback_event = _terminal_feedback_event(
            metadata,
            target_id=target_id,
            resource_id=resource_id,
            terminal_state=terminal_state,
            constraint_class=constraint_class,
            classification_reason=classification_reason,
        )
        if target_id and feedback_event is not None:
            target_feedback_events.setdefault(target_id, []).append(feedback_event)

        if d4_request:
            _append_unique(d4_requests, d4_request)
        if gate_action and gate_action != "continue":
            d7_gate_action = gate_action
        elif action and action != "continue" and d7_gate_action == "continue":
            d7_gate_action = "hold"
        elif (
            constraint_class != _FeedbackConstraintClass.NONE
            and d7_gate_action == "continue"
        ):
            d7_gate_action = "hold"

        if constraint_class == _FeedbackConstraintClass.RESOURCE_HARD:
            add_hold(resource_id)
        elif constraint_class == _FeedbackConstraintClass.TARGET_HARD:
            add_hard_target(target_id)
        elif constraint_class == _FeedbackConstraintClass.EDGE_HARD:
            add_prohibited_edge(target_id, resource_id)
        elif constraint_class == _FeedbackConstraintClass.EDGE_SOFT:
            add_fov(target_id, resource_id, fov_cap)

        raw_edges = metadata.get("prohibited_edges") or ()
        if isinstance(raw_edges, Mapping):
            raw_edges = (raw_edges,)
        for raw_edge in raw_edges:
            if not isinstance(raw_edge, Mapping):
                continue
            add_prohibited_edge(
                _metadata_text(
                    raw_edge,
                    "target_id",
                    "global_track_id",
                    "assigned_global_track_id",
                )
                or target_id,
                _metadata_text(
                    raw_edge,
                    "resource_id",
                    "assigned_resource_id",
                    "owner",
                )
                or resource_id,
            )

        raw_feasibility = metadata.get("feasibility_by_resource")
        if isinstance(raw_feasibility, Mapping) and target_id:
            for raw_resource_id, raw_feasible in raw_feasibility.items():
                update_resource_id = str(raw_resource_id)
                feasible = _metadata_bool(raw_feasible)
                target_feasibility.setdefault(target_id, {})[
                    update_resource_id
                ] = feasible
                if not feasible:
                    add_prohibited_edge(target_id, update_resource_id)

        if (
            _metadata_bool(metadata.get("prohibit_assignment_suggested"))
            or feasibility_suggestion == "temporarily_mark_current_edge_infeasible"
        ):
            add_prohibited_edge(target_id, resource_id)

        raw_fov = metadata.get("fov_difficulty_by_resource")
        if isinstance(raw_fov, Mapping) and target_id:
            for raw_resource_id, raw_value in raw_fov.items():
                add_fov(target_id, str(raw_resource_id), raw_value)

        if fov_suggestion == "increase_current_edge":
            add_fov(target_id, resource_id, fov_cap)

    updated_target_ids: list[str] = []
    updated_tracks: list[TargetTrack] = []
    resource_by_id = {resource.resource_id: resource for resource in resource_tuple}
    for track in track_tuple:
        feasibility = dict(track.feasibility_by_resource)
        fov = dict(track.fov_difficulty_by_resource)
        feedback_fov_base_by_resource: dict[str, float] = {}
        feedback_fov_applied_by_resource: dict[str, float] = {}
        changed = False
        if track.track_id in target_feasibility:
            feasibility.update(target_feasibility[track.track_id])
            changed = True
        if track.track_id in target_fov:
            for resource_id, value in target_fov[track.track_id].items():
                resource = resource_by_id.get(resource_id)
                base_value = float(
                    track.fov_difficulty_by_resource.get(
                        resource_id,
                        0.0 if resource is None else resource.fov_difficulty,
                    )
                )
                fov[resource_id] = max(float(fov.get(resource_id, 0.0)), value)
                feedback_fov_base_by_resource[resource_id] = base_value
                feedback_fov_applied_by_resource[resource_id] = float(
                    fov[resource_id]
                )
            changed = True
        feedback_events = tuple(target_feedback_events.get(track.track_id, ()))
        if feedback_events:
            changed = True
        target_hard = track.track_id in hard_target_set
        if target_hard and track.assignable:
            changed = True
        if changed:
            updated_target_ids.append(track.track_id)
            updated_tracks.append(
                replace(
                    track,
                    assignable=False if target_hard else track.assignable,
                    feasibility_by_resource=feasibility,
                    fov_difficulty_by_resource=fov,
                    metadata={
                        **dict(track.metadata),
                        "terminal_feedback_writeback_applied": True,
                        "terminal_feedback_events": feedback_events,
                        "terminal_feedback_target_hard": target_hard,
                        "terminal_feedback_fov_base_by_resource": (
                            feedback_fov_base_by_resource
                        ),
                        "terminal_feedback_fov_applied_by_resource": (
                            feedback_fov_applied_by_resource
                        ),
                    },
                )
            )
        else:
            updated_tracks.append(track)

    updated_resource_ids: list[str] = []
    updated_resources: list[ResourceState] = []
    for resource in resource_tuple:
        if resource.resource_id in hold_resource_set and not resource.operator_hold:
            updated_resource_ids.append(resource.resource_id)
            updated_resources.append(
                replace(
                    resource,
                    operator_hold=True,
                    metadata={
                        **dict(resource.metadata),
                        "terminal_feedback_writeback_applied": True,
                    },
                )
            )
        else:
            updated_resources.append(resource)

    edge_metadata = tuple(
        {"target_id": target_id, "resource_id": resource_id}
        for target_id, resource_id in prohibited_edges
    )
    metadata = {
        "feedback_count": len(metadata_items),
        "prohibited_edges": edge_metadata,
        "hold_resource_ids": tuple(hold_resource_ids),
        "hard_target_ids": tuple(hard_target_ids),
        "updated_target_ids": tuple(updated_target_ids),
        "updated_resource_ids": tuple(updated_resource_ids),
        "d7_gate_action": d7_gate_action,
        "d4_requests": tuple(d4_requests),
        "allow_local_rebind": False,
        "feedback_profile_schema": TERMINAL_FEEDBACK_PROFILE_SCHEMA_V1,
        "feedback_profile_id": resolved_feedback_profile_id,
        "feedback_profile_version": resolved_feedback_profile_version,
        "fov_cap": float(fov_cap),
        "feedback_constraint_classification_schema": (
            _FEEDBACK_CONSTRAINT_CLASSIFICATION_SCHEMA_V1
        ),
        "feedback_classifications": tuple(feedback_classifications),
        "soft_edge_feedback_count": sum(
            item["constraint_class"] == _FeedbackConstraintClass.EDGE_SOFT.value
            for item in feedback_classifications
        ),
        "hard_edge_feedback_count": sum(
            item["constraint_class"] == _FeedbackConstraintClass.EDGE_HARD.value
            for item in feedback_classifications
        ),
        "resource_hard_feedback_count": sum(
            item["constraint_class"] == _FeedbackConstraintClass.RESOURCE_HARD.value
            for item in feedback_classifications
        ),
        "target_hard_feedback_count": sum(
            item["constraint_class"] == _FeedbackConstraintClass.TARGET_HARD.value
            for item in feedback_classifications
        ),
        "terminal_feedback_events": tuple(
            event
            for target_id in sorted(target_feedback_events)
            for event in target_feedback_events[target_id]
        ),
    }
    return TerminalFeedbackWriteback(
        tracks=tuple(updated_tracks),
        resources=tuple(updated_resources),
        prohibited_edges=edge_metadata,
        hold_resource_ids=tuple(hold_resource_ids),
        updated_target_ids=tuple(updated_target_ids),
        updated_resource_ids=tuple(updated_resource_ids),
        d7_gate_action=d7_gate_action,
        d4_requests=tuple(d4_requests),
        allow_local_rebind=False,
        metadata=metadata,
        hard_target_ids=tuple(hard_target_ids),
    )


def assignment_validity_summary_from_plan(
    plan: AssignmentPlan,
    *,
    evaluated_at: float,
    latest_version: int | None = None,
    latest_plan_id: str | None = None,
    assignment_latency_s: float | None = None,
    input_timestamp_s: float | None = None,
    tracks: Iterable[TargetTrack] | None = None,
    high_threat_target_ids: Iterable[str] | None = None,
    high_threat_threshold: float = 0.7,
) -> AssignmentValiditySummary:
    """Build a compact validity summary from one D3 assignment plan."""

    stale_plan_version = _stale_plan_version(
        plan=plan,
        latest_version=latest_version,
        latest_plan_id=latest_plan_id,
    )
    return AssignmentValiditySummary(
        plan_id=plan.plan_id,
        version=plan.version,
        plan_age_s=max(0.0, float(evaluated_at) - plan.created_at),
        assignment_latency_s=_assignment_latency_s(
            plan=plan,
            assignment_latency_s=assignment_latency_s,
            input_timestamp_s=input_timestamp_s,
        ),
        cost_margin=_cost_margin(plan),
        stale_plan_version=stale_plan_version,
        duplicate_assignment_count=_duplicate_assignment_count(plan),
        unassigned_high_threat_count=_unassigned_high_threat_count(
            plan=plan,
            tracks=tracks,
            high_threat_target_ids=high_threat_target_ids,
            high_threat_threshold=high_threat_threshold,
        ),
        resource_count=_plan_resource_count(plan),
        target_count=_plan_target_count(plan),
        assigned_count=len(plan.assignments),
        hysteresis_reject_count=_hysteresis_reject_count(plan),
        stale_reject_count=_stale_reject_count(
            plan,
            stale_plan_version=stale_plan_version,
        ),
        reassign_count=_reassign_count(plan),
    )


def assignment_records_from_plan(
    plan: AssignmentPlan,
    *,
    timestamp: float | None = None,
    authorization_state: str | None = "recorded",
    truth_id_by_target: Mapping[str, str] | None = None,
    active: bool = True,
    previous_plan: AssignmentPlan | None = None,
    tracks: Iterable[TargetTrack] | None = None,
    high_threat_target_ids: Iterable[str] | None = None,
    high_threat_threshold: float = 0.7,
) -> tuple[AssignmentRecord, ...]:
    """Export D6-compatible assignment records from a D3 plan."""

    plan_metadata = dict(plan.metadata)
    identity_created_at_s = _metadata_float(
        plan_metadata.get("identity_created_at_s")
    )
    if identity_created_at_s is None:
        identity_created_at_s = plan.created_at
    last_evaluated_at_s = _metadata_float(
        plan_metadata.get("last_evaluated_at_s")
    )
    if last_evaluated_at_s is None:
        last_evaluated_at_s = plan.created_at
    record_timestamp = (
        last_evaluated_at_s if timestamp is None else float(timestamp)
    )
    record_auth = (
        plan.human_authorization_state
        if authorization_state is None
        else authorization_state
    )
    truth_id_by_target = truth_id_by_target or {}
    resource_count = _plan_resource_count(plan)
    target_count = _plan_target_count(plan)
    assignment_matrix_shape = _assignment_matrix_shape(
        plan_metadata.get("assignment_matrix_shape"),
        target_count=target_count,
        resource_count=resource_count,
    )
    assigned_count = len(plan.assignments)
    unassigned_high_threat_count = _unassigned_high_threat_count(
        plan=plan,
        tracks=tracks,
        high_threat_target_ids=high_threat_target_ids,
        high_threat_threshold=high_threat_threshold,
    )
    hysteresis_reject_count = _hysteresis_reject_count(plan)
    stale_reject_count = _stale_reject_count(plan)
    reassign_count = _reassign_count(plan, previous_plan=previous_plan)
    plan_churn_count = _metadata_int(plan_metadata.get("plan_churn_count"))
    if plan_churn_count is None:
        plan_churn_count = reassign_count
    plan_owner = _metadata_text(plan_metadata, "plan_owner") or "center"
    active_plan_owner = (
        _metadata_text(plan_metadata, "active_plan_owner") or plan_owner
    )
    owner_node_id = (
        _metadata_text(plan_metadata, "owner_node_id")
        or _metadata_text(plan_metadata, "source_node_id")
        or plan.source_node_id
    )
    previous_plan_version = _metadata_int(plan_metadata.get("previous_plan_version"))
    if previous_plan_version is None and plan.previous_plan_id and plan.version > 1:
        previous_plan_version = plan.version - 1
    supersedes_plan_version = _metadata_int(
        plan_metadata.get("supersedes_plan_version")
    )
    selected_secondary_node_id = _metadata_text(
        plan_metadata,
        "selected_secondary_node_id",
    )
    secondary_plan_version = _metadata_int(plan_metadata.get("secondary_plan_version"))
    if secondary_plan_version is None and active_plan_owner == "secondary":
        secondary_plan_version = plan.version
    plan_rollback_detected = _metadata_bool(
        plan_metadata.get("plan_rollback_detected")
    ) or (
        previous_plan is not None and plan.version < previous_plan.version
    )
    coalition_by_id = {
        coalition.coalition_id: coalition for coalition in plan.coalitions
    }
    return tuple(
        AssignmentRecord(
            timestamp=record_timestamp,
            plan_id=plan.plan_id,
            version=plan.version,
            resource_id=assignment.resource_id,
            global_track_id=assignment.target_id,
            cost_breakdown=dict(assignment.cost_breakdown),
            authorization_state=record_auth,
            active=(
                active
                and assignment.feasibility_state == "feasible"
                and assignment.member_role != CoalitionMemberRole.RESERVE.value
            ),
            truth_id=truth_id_by_target.get(assignment.target_id),
            window_id=plan.window_id,
            decision_state=plan.decision_state,
            changed=plan.changed,
            resource_count=resource_count,
            target_count=target_count,
            assigned_count=assigned_count,
            identity_created_at_s=identity_created_at_s,
            last_evaluated_at_s=last_evaluated_at_s,
            unassigned_high_threat_count=unassigned_high_threat_count,
            hysteresis_reject_count=hysteresis_reject_count,
            stale_reject_count=stale_reject_count,
            reassign_count=reassign_count,
            plan_churn_count=plan_churn_count,
            plan_rollback_detected=plan_rollback_detected,
            assignment_matrix_shape=assignment_matrix_shape,
            coalition_id=assignment.coalition_id,
            coalition_version=assignment.coalition_version,
            coalition_epoch=(
                coalition_by_id[assignment.coalition_id].epoch
                if assignment.coalition_id in coalition_by_id
                else None
            ),
            coalition_complete=(
                coalition_by_id[assignment.coalition_id].complete
                if assignment.coalition_id in coalition_by_id
                else None
            ),
            member_role=assignment.member_role,
            wave_id=assignment.wave_id,
            activation_state=(
                "standby"
                if assignment.member_role == CoalitionMemberRole.RESERVE.value
                else "active"
            ),
            assignment_validity_state=(
                "stale"
                if _metadata_bool(plan_metadata.get("stale_plan_rejected"))
                else "invalid"
                if assignment.feasibility_state != "feasible"
                else "standby"
                if assignment.member_role == CoalitionMemberRole.RESERVE.value
                else "inactive"
                if not active
                else "current"
            ),
            terminal_authorization_scope=assignment.terminal_authorization_scope,
            terminal_authorization_eligible=(
                active
                and assignment.member_role == CoalitionMemberRole.PRIMARY.value
                and assignment.feasibility_state == "feasible"
                and not _metadata_bool(plan_metadata.get("stale_plan_rejected"))
                and str(record_auth).strip().lower()
                in EFFECTIVE_GUIDANCE_AUTH_STATES
            ),
            arrival_coordination_required=assignment.arrival_coordination_required,
            plan_owner=plan_owner,
            active_plan_owner=active_plan_owner,
            owner_node_id=owner_node_id,
            source_node_id=assignment.source_node_id
            or plan.source_node_id
            or _metadata_text(plan_metadata, "source_node_id"),
            target_node_id=assignment.target_node_id
            or plan.target_node_id
            or _metadata_text(plan_metadata, "target_node_id"),
            link_type=assignment.link_type
            or plan.link_type
            or _metadata_text(plan_metadata, "link_type"),
            plan_schema=_plan_schema(plan),
            replan_reason=_metadata_text(plan_metadata, "replan_reason"),
            takeover_reason=_metadata_text(plan_metadata, "takeover_reason"),
            previous_plan_id=plan.previous_plan_id,
            previous_plan_version=previous_plan_version,
            supersedes_plan_id=_metadata_text(plan_metadata, "supersedes_plan_id"),
            supersedes_plan_version=supersedes_plan_version,
            selected_secondary_node_id=selected_secondary_node_id,
            secondary_plan_version=secondary_plan_version,
            secondary_leader_epoch=_metadata_int(
                plan_metadata.get("secondary_leader_epoch")
            ),
            secondary_lease_expires_at_s=_metadata_float(
                plan_metadata.get("secondary_lease_expires_at_s")
            ),
            secondary_takeover_state=_metadata_text(
                plan_metadata,
                "secondary_takeover_state",
            ),
            secondary_readiness_class=_metadata_text(
                plan_metadata,
                "secondary_readiness_class",
            ),
            secondary_readiness_sustained=_metadata_bool_optional(
                plan_metadata.get("secondary_readiness_sustained")
            ),
            secondary_activated_at_s=_metadata_float(
                plan_metadata.get("secondary_activated_at_s")
            ),
            total_cost=plan.total_cost,
            candidate_total_cost=plan.candidate_total_cost,
            previous_total_cost_current=plan.previous_total_cost_current,
            cost_margin=_cost_margin(plan),
            stale_after_s=(
                assignment.stale_after_s
                if assignment.stale_after_s is not None
                else plan.stale_after_s
            ),
            stale_plan_rejected=_metadata_bool(
                plan_metadata.get("stale_plan_rejected")
            ),
            stale_reject_reason=_metadata_text(
                plan_metadata,
                "stale_reject_reason",
            ),
            latest_plan_id=_metadata_text(plan_metadata, "latest_plan_id"),
            latest_plan_version=_metadata_int(
                plan_metadata.get("latest_plan_version")
            ),
            hysteresis_state=_metadata_text(plan_metadata, "hysteresis_state"),
            hysteresis_reason=_metadata_text(plan_metadata, "hysteresis_reason"),
            hysteresis_reasons=_metadata_text_tuple(
                plan_metadata.get("hysteresis_reasons")
            ),
            hysteresis_release_reason=_metadata_text(
                plan_metadata,
                "hysteresis_release_reason",
            ),
            hysteresis_release_condition=_metadata_text(
                plan_metadata,
                "hysteresis_release_condition",
            ),
            hysteresis_dwell_time_s=_metadata_float(
                plan_metadata.get("hysteresis_dwell_time_s")
            ),
            hysteresis_min_dwell_s=_metadata_float(
                plan_metadata.get("hysteresis_min_dwell_s")
            ),
            hysteresis_delta=_metadata_float(plan_metadata.get("hysteresis_delta")),
            hysteresis_candidate_change_count=_metadata_int(
                plan_metadata.get("hysteresis_candidate_change_count")
            ),
            hysteresis_max_changes_per_window=_metadata_int(
                plan_metadata.get("hysteresis_max_changes_per_window")
            ),
            hysteresis_improvement_ok=_metadata_bool_optional(
                plan_metadata.get("hysteresis_improvement_ok")
            ),
            hysteresis_dwell_ok=_metadata_bool_optional(
                plan_metadata.get("hysteresis_dwell_ok")
            ),
            hysteresis_change_limit_ok=_metadata_bool_optional(
                plan_metadata.get("hysteresis_change_limit_ok")
            ),
            hysteresis_high_threat_release=_metadata_bool_optional(
                plan_metadata.get("hysteresis_high_threat_release")
            ),
            assignment_profile_schema=(
                _metadata_text(plan_metadata, "assignment_profile_schema")
                or ASSIGNMENT_CALIBRATION_PROFILE_SCHEMA_V1
            ),
            cost_profile_id=(
                _metadata_text(plan_metadata, "cost_profile_id")
                or DEFAULT_COST_PROFILE_ID
            ),
            cost_profile_version=(
                _metadata_text(plan_metadata, "cost_profile_version")
                or DEFAULT_COST_PROFILE_VERSION
            ),
            feedback_profile_id=(
                _metadata_text(plan_metadata, "feedback_profile_id")
                or DEFAULT_FEEDBACK_PROFILE_ID
            ),
            feedback_profile_version=(
                _metadata_text(plan_metadata, "feedback_profile_version")
                or DEFAULT_FEEDBACK_PROFILE_VERSION
            ),
            cost_weights=_metadata_float_mapping(plan_metadata.get("cost_weights")),
            planner_thresholds=_metadata_mapping(
                plan_metadata.get("planner_thresholds")
            ),
        )
        for assignment in plan.assignments
    )


def assignment_evidence_from_plan(plan: AssignmentPlan) -> AssignmentEvidenceExport:
    """Export current-plan cost evidence for D4 decisions and D6 replay."""

    plan_metadata = dict(plan.metadata)
    identity_created_at_s = _metadata_float(
        plan_metadata.get("identity_created_at_s")
    )
    if identity_created_at_s is None:
        identity_created_at_s = plan.created_at
    last_evaluated_at_s = _metadata_float(
        plan_metadata.get("last_evaluated_at_s")
    )
    if last_evaluated_at_s is None:
        last_evaluated_at_s = plan.created_at
    resource_count = _plan_resource_count(plan)
    target_count = _plan_target_count(plan)
    plan_owner = _metadata_text(plan_metadata, "plan_owner") or "center"
    active_plan_owner = (
        _metadata_text(plan_metadata, "active_plan_owner") or plan_owner
    )
    selected_secondary_node_id = _metadata_text(
        plan_metadata,
        "selected_secondary_node_id",
    )
    secondary_plan_version = _metadata_int(plan_metadata.get("secondary_plan_version"))
    if secondary_plan_version is None and active_plan_owner == "secondary":
        secondary_plan_version = plan.version

    return AssignmentEvidenceExport(
        plan_id=plan.plan_id,
        version=plan.version,
        window_id=plan.window_id,
        current_plan_id=_metadata_text(plan_metadata, "current_plan_id")
        or plan.plan_id,
        current_plan_version=_metadata_int(
            plan_metadata.get("current_plan_version")
        )
        or plan.version,
        resource_count=resource_count,
        target_count=target_count,
        assigned_count=len(plan.assignments),
        identity_created_at_s=identity_created_at_s,
        last_evaluated_at_s=last_evaluated_at_s,
        plan_owner=plan_owner,
        active_plan_owner=active_plan_owner,
        owner_node_id=(
            _metadata_text(plan_metadata, "owner_node_id")
            or _metadata_text(plan_metadata, "source_node_id")
            or plan.source_node_id
        ),
        source_node_id=plan.source_node_id
        or _metadata_text(plan_metadata, "source_node_id"),
        target_node_id=plan.target_node_id
        or _metadata_text(plan_metadata, "target_node_id"),
        link_type=plan.link_type or _metadata_text(plan_metadata, "link_type"),
        selected_secondary_node_id=selected_secondary_node_id,
        secondary_plan_version=secondary_plan_version,
        supersedes_plan_id=_metadata_text(plan_metadata, "supersedes_plan_id"),
        supersedes_plan_version=_metadata_int(
            plan_metadata.get("supersedes_plan_version")
        ),
        secondary_leader_epoch=_metadata_int(
            plan_metadata.get("secondary_leader_epoch")
        ),
        secondary_lease_expires_at_s=_metadata_float(
            plan_metadata.get("secondary_lease_expires_at_s")
        ),
        secondary_takeover_state=_metadata_text(
            plan_metadata,
            "secondary_takeover_state",
        ),
        secondary_readiness_class=_metadata_text(
            plan_metadata,
            "secondary_readiness_class",
        ),
        secondary_readiness_sustained=_metadata_bool_optional(
            plan_metadata.get("secondary_readiness_sustained")
        ),
        secondary_activated_at_s=_metadata_float(
            plan_metadata.get("secondary_activated_at_s")
        ),
        cost_matrix_target_ids=_metadata_text_tuple(
            plan_metadata.get("cost_matrix_target_ids")
        ),
        cost_matrix_resource_ids=_metadata_text_tuple(
            plan_metadata.get("cost_matrix_resource_ids")
        ),
        cost_matrix=_metadata_float_matrix(plan_metadata.get("cost_matrix")),
        cost_breakdowns_by_edge=_metadata_mapping_tuple(
            plan_metadata.get("cost_breakdowns_by_edge")
        ),
        rejected_edges=_metadata_mapping_tuple(plan_metadata.get("rejected_edges")),
        stale_plan_rejected=_metadata_bool(
            plan_metadata.get("stale_plan_rejected")
        ),
        stale_reject_reason=_metadata_text(plan_metadata, "stale_reject_reason"),
        latest_plan_id=_metadata_text(plan_metadata, "latest_plan_id"),
        latest_plan_version=_metadata_int(plan_metadata.get("latest_plan_version")),
        assignment_profile_schema=(
            _metadata_text(plan_metadata, "assignment_profile_schema")
            or ASSIGNMENT_CALIBRATION_PROFILE_SCHEMA_V1
        ),
        cost_profile_id=(
            _metadata_text(plan_metadata, "cost_profile_id")
            or DEFAULT_COST_PROFILE_ID
        ),
        cost_profile_version=(
            _metadata_text(plan_metadata, "cost_profile_version")
            or DEFAULT_COST_PROFILE_VERSION
        ),
        feedback_profile_id=(
            _metadata_text(plan_metadata, "feedback_profile_id")
            or DEFAULT_FEEDBACK_PROFILE_ID
        ),
        feedback_profile_version=(
            _metadata_text(plan_metadata, "feedback_profile_version")
            or DEFAULT_FEEDBACK_PROFILE_VERSION
        ),
        cost_weights=_metadata_float_mapping(plan_metadata.get("cost_weights")),
        planner_thresholds=_metadata_mapping(plan_metadata.get("planner_thresholds")),
    )


def plan_history_record_from_plan(
    plan: AssignmentPlan,
    *,
    sequence_index: int,
    timestamp: float,
    previous_plan: AssignmentPlan | None = None,
    feedback_metadata: Mapping[str, Any] | None = None,
) -> PlanningTickHistoryRecord:
    """Build one canonical planning-tick record for main persistence and D6.

    Main owns ``sequence_index`` and the tick ``timestamp``. The optional
    ``feedback_metadata`` accepts the metadata mapping returned by
    :func:`apply_terminal_feedback_to_planner_inputs`; when omitted, the same
    backward-compatible keys are read from ``plan.metadata``.
    """

    if isinstance(sequence_index, bool) or not isinstance(sequence_index, int):
        raise TypeError("sequence_index must be an integer")
    if sequence_index < 0:
        raise ValueError("sequence_index must be non-negative")
    record_timestamp = float(timestamp)
    if not isfinite(record_timestamp):
        raise ValueError("timestamp must be finite")

    plan_metadata = dict(plan.metadata)
    evidence = assignment_evidence_from_plan(plan)
    assignment_records = assignment_records_from_plan(
        plan,
        timestamp=record_timestamp,
        previous_plan=previous_plan,
    )
    assignment_pairs = sorted(
        zip(plan.assignments, assignment_records),
        key=lambda pair: _history_assignment_sort_key(pair[0]),
    )
    assignments = tuple(
        {
            "target_id": assignment.target_id,
            "resource_id": assignment.resource_id,
            "member_role": record.member_role,
            "wave_id": record.wave_id,
            "activation_state": record.activation_state,
            "active": record.active,
            "coalition_id": record.coalition_id,
            "coalition_version": record.coalition_version,
            "coalition_epoch": record.coalition_epoch,
            "coalition_complete": record.coalition_complete,
            "assignment_validity_state": record.assignment_validity_state,
            "feasibility_state": assignment.feasibility_state,
            "cost": float(assignment.cost),
            "cost_breakdown": dict(assignment.cost_breakdown),
        }
        for assignment, record in assignment_pairs
    )
    coalitions = tuple(
        _history_coalition_record(coalition)
        for coalition in sorted(
            plan.coalitions,
            key=lambda item: (item.target_id, item.coalition_id, item.version),
        )
    )
    membership_change_records = _history_membership_change_records(
        plan_metadata.get("membership_change_records")
    )

    previous_plan_version = _metadata_int(
        plan_metadata.get("previous_plan_version")
    )
    if previous_plan_version is None and previous_plan is not None:
        previous_plan_version = previous_plan.version
    if previous_plan_version is None and plan.previous_plan_id and plan.version > 1:
        previous_plan_version = plan.version - 1
    rollback_detected = _metadata_bool(
        plan_metadata.get("plan_rollback_detected")
    ) or (previous_plan is not None and plan.version < previous_plan.version)

    return PlanningTickHistoryRecord(
        schema=PLAN_HISTORY_RECORD_SCHEMA_V1,
        schema_version=1,
        sequence_index=sequence_index,
        ordering_key=(sequence_index, record_timestamp),
        timestamp=record_timestamp,
        plan_schema=_plan_schema(plan),
        plan_id=plan.plan_id,
        plan_version=plan.version,
        window_id=plan.window_id,
        changed=bool(plan.changed),
        decision_state=plan.decision_state,
        resource_count=evidence.resource_count,
        target_count=evidence.target_count,
        assigned_count=evidence.assigned_count,
        plan_owner=evidence.plan_owner,
        active_plan_owner=evidence.active_plan_owner,
        owner_node_id=evidence.owner_node_id,
        source_node_id=evidence.source_node_id,
        selected_secondary_node_id=evidence.selected_secondary_node_id,
        secondary_plan_version=evidence.secondary_plan_version,
        secondary_leader_epoch=evidence.secondary_leader_epoch,
        secondary_lease_expires_at_s=evidence.secondary_lease_expires_at_s,
        previous_plan_id=plan.previous_plan_id,
        previous_plan_version=previous_plan_version,
        supersedes_plan_id=evidence.supersedes_plan_id,
        supersedes_plan_version=evidence.supersedes_plan_version,
        assignments=assignments,
        coalitions=coalitions,
        hysteresis=_history_hysteresis_record(plan_metadata),
        membership_change_records=membership_change_records,
        feedback_constraints=_history_feedback_constraints(
            plan_metadata,
            feedback_metadata=feedback_metadata,
        ),
        total_cost=float(plan.total_cost),
        candidate_total_cost=(
            None
            if plan.candidate_total_cost is None
            else float(plan.candidate_total_cost)
        ),
        previous_total_cost_current=(
            None
            if plan.previous_total_cost_current is None
            else float(plan.previous_total_cost_current)
        ),
        stale_plan_rejected=evidence.stale_plan_rejected,
        stale_reject_reason=evidence.stale_reject_reason,
        latest_plan_id=evidence.latest_plan_id,
        latest_plan_version=evidence.latest_plan_version,
        rollback_detected=rollback_detected,
        rollback_reason=_metadata_text(
            plan_metadata,
            "plan_rollback_reason",
            "rollback_reason",
        ),
        replan_reason=_metadata_text(plan_metadata, "replan_reason"),
    )


def _history_assignment_sort_key(assignment: Assignment) -> tuple[Any, ...]:
    role_rank = {
        CoalitionMemberRole.PRIMARY.value: 0,
        CoalitionMemberRole.RESERVE.value: 1,
        CoalitionMemberRole.RETRY.value: 2,
        CoalitionMemberRole.OBSERVER.value: 3,
    }
    return (
        assignment.target_id,
        assignment.coalition_id or "",
        assignment.wave_id,
        role_rank.get(assignment.member_role, 99),
        assignment.member_role,
        assignment.resource_id,
    )


def _history_coalition_record(coalition: CoalitionPlan) -> Mapping[str, Any]:
    members = tuple(
        {
            "resource_id": member.resource_id,
            "member_role": member.member_role,
            "wave_id": member.wave_id,
            "arrival_window_start_s": member.arrival_window_start_s,
            "arrival_window_end_s": member.arrival_window_end_s,
            "required_capability_class": member.required_capability_class,
            "executable": bool(member.executable),
        }
        for member in sorted(
            coalition.members,
            key=lambda item: (
                item.wave_id,
                {
                    CoalitionMemberRole.PRIMARY.value: 0,
                    CoalitionMemberRole.RESERVE.value: 1,
                    CoalitionMemberRole.RETRY.value: 2,
                    CoalitionMemberRole.OBSERVER.value: 3,
                }.get(item.member_role, 99),
                item.member_role,
                item.resource_id,
            ),
        )
    )
    return {
        "coalition_id": coalition.coalition_id,
        "version": coalition.version,
        "epoch": coalition.epoch,
        "target_id": coalition.target_id,
        "state": coalition.state,
        "coordination_mode": coalition.coordination_mode,
        "required_resource_count": coalition.required_resource_count,
        "primary_resource_count": coalition.primary_resource_count,
        "assigned_resource_count": coalition.assigned_resource_count,
        "shortfall": coalition.shortfall,
        "complete": bool(coalition.complete),
        "members": members,
    }


def _history_hysteresis_record(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "state": _metadata_text(metadata, "hysteresis_state"),
        "reason": _metadata_text(metadata, "hysteresis_reason"),
        "reasons": _metadata_text_tuple(metadata.get("hysteresis_reasons")),
        "release_reason": _metadata_text(metadata, "hysteresis_release_reason"),
        "release_condition": _metadata_text(
            metadata,
            "hysteresis_release_condition",
        ),
        "dwell_time_s": _metadata_float(metadata.get("hysteresis_dwell_time_s")),
        "min_dwell_s": _metadata_float(metadata.get("hysteresis_min_dwell_s")),
        "delta": _metadata_float(metadata.get("hysteresis_delta")),
        "candidate_change_count": _metadata_int(
            metadata.get("hysteresis_candidate_change_count")
            if "hysteresis_candidate_change_count" in metadata
            else metadata.get("candidate_change_count")
        ),
        "max_changes_per_window": _metadata_int(
            metadata.get("hysteresis_max_changes_per_window")
            if "hysteresis_max_changes_per_window" in metadata
            else metadata.get("max_changes_per_window")
        ),
        "previous_feasible": _metadata_bool_optional(
            metadata.get("hysteresis_previous_feasible")
        ),
        "improvement_ok": _metadata_bool_optional(
            metadata.get("hysteresis_improvement_ok")
        ),
        "dwell_ok": _metadata_bool_optional(metadata.get("hysteresis_dwell_ok")),
        "change_limit_ok": _metadata_bool_optional(
            metadata.get("hysteresis_change_limit_ok")
        ),
        "cost_basis_schema": _metadata_text(
            metadata,
            "hysteresis_cost_basis_schema",
        ),
        "candidate_search_total_cost": _metadata_float(
            metadata.get("hysteresis_candidate_search_total_cost")
        ),
        "candidate_comparison_total_cost": _metadata_float(
            metadata.get("hysteresis_candidate_comparison_total_cost")
        ),
        "previous_comparison_total_cost": _metadata_float(
            metadata.get("hysteresis_previous_comparison_total_cost")
        ),
        "change_window_id": _metadata_int(
            metadata.get("hysteresis_change_window_id")
        ),
        "window_change_budget_schema": _metadata_text(
            metadata,
            "hysteresis_window_change_budget_schema",
        ),
        "window_changes_used_before": _metadata_int(
            metadata.get("hysteresis_window_changes_used_before")
        ),
        "window_changes_used": _metadata_int(
            metadata.get("hysteresis_window_changes_used")
        ),
        "window_candidate_change_count": _metadata_int(
            metadata.get("hysteresis_window_candidate_change_count")
        ),
        "window_changes_if_accepted": _metadata_int(
            metadata.get("hysteresis_window_changes_if_accepted")
        ),
        "window_change_budget_remaining": _metadata_int(
            metadata.get("hysteresis_window_change_budget_remaining")
        ),
        "window_change_budget_ok": _metadata_bool_optional(
            metadata.get("hysteresis_window_change_budget_ok")
        ),
        "window_change_budget_bypassed": _metadata_bool_optional(
            metadata.get("hysteresis_window_change_budget_bypassed")
        ),
        "window_change_budget_bypass_reason": _metadata_text(
            metadata,
            "hysteresis_window_change_budget_bypass_reason",
        ),
        "high_threat_release": _metadata_bool_optional(
            metadata.get("hysteresis_high_threat_release")
        ),
    }


def _history_membership_change_records(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        raw_records = (value,)
    elif isinstance(value, (tuple, list)):
        raw_records = tuple(item for item in value if isinstance(item, Mapping))
    else:
        raw_records = ()
    normalized = tuple(
        item
        for item in (_history_json_value(dict(record)) for record in raw_records)
        if isinstance(item, dict)
    )
    return tuple(
        sorted(
            normalized,
            key=lambda item: (
                str(item.get("target_id") or ""),
                str(item.get("membership_change_reason") or ""),
                repr(item),
            ),
        )
    )


def _history_feedback_constraints(
    plan_metadata: Mapping[str, Any],
    *,
    feedback_metadata: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    source = dict(plan_metadata)
    if feedback_metadata is not None:
        source.update(dict(feedback_metadata))
    raw_classifications = source.get("feedback_classifications")
    if not raw_classifications:
        raw_classifications = source.get("terminal_feedback_events", ())
    if isinstance(raw_classifications, Mapping):
        raw_classifications = (raw_classifications,)
    if not isinstance(raw_classifications, (tuple, list)):
        raw_classifications = ()

    classifications = tuple(
        sorted(
            (
                _history_feedback_classification(item)
                for item in raw_classifications
                if isinstance(item, Mapping)
            ),
            key=lambda item: (
                str(item.get("target_id") or ""),
                str(item.get("resource_id") or ""),
                str(item.get("constraint_class") or ""),
                str(item.get("terminal_feedback_state") or ""),
                str(item.get("classification_reason") or ""),
            ),
        )
    )
    class_counts = {
        item["constraint_class"]: sum(
            other["constraint_class"] == item["constraint_class"]
            for other in classifications
        )
        for item in classifications
    }

    def category_count(metadata_key: str, constraint_class: str) -> int:
        if classifications:
            return int(class_counts.get(constraint_class, 0))
        return max(0, _metadata_int(source.get(metadata_key)) or 0)

    soft_edge_count = category_count(
        "soft_edge_feedback_count",
        _FeedbackConstraintClass.EDGE_SOFT.value,
    )
    hard_edge_count = category_count(
        "hard_edge_feedback_count",
        _FeedbackConstraintClass.EDGE_HARD.value,
    )
    resource_hard_count = category_count(
        "resource_hard_feedback_count",
        _FeedbackConstraintClass.RESOURCE_HARD.value,
    )
    target_hard_count = category_count(
        "target_hard_feedback_count",
        _FeedbackConstraintClass.TARGET_HARD.value,
    )
    return {
        "schema": _metadata_text(
            source,
            "feedback_constraint_classification_schema",
        )
        or _FEEDBACK_CONSTRAINT_CLASSIFICATION_SCHEMA_V1,
        "classifications": classifications,
        "soft_count": soft_edge_count,
        "hard_count": hard_edge_count + resource_hard_count + target_hard_count,
        "soft_edge_count": soft_edge_count,
        "hard_edge_count": hard_edge_count,
        "resource_hard_count": resource_hard_count,
        "target_hard_count": target_hard_count,
    }


def _history_feedback_classification(value: Mapping[str, Any]) -> Mapping[str, Any]:
    constraint_class = str(
        value.get("constraint_class")
        or value.get("feedback_constraint_class")
        or _FeedbackConstraintClass.NONE.value
    )
    hard_reject = constraint_class in {
        _FeedbackConstraintClass.EDGE_HARD.value,
        _FeedbackConstraintClass.RESOURCE_HARD.value,
        _FeedbackConstraintClass.TARGET_HARD.value,
    }
    return {
        "target_id": value.get("target_id"),
        "resource_id": value.get("resource_id"),
        "terminal_feedback_state": value.get("terminal_feedback_state"),
        "constraint_class": constraint_class,
        "constraint_scope": value.get("constraint_scope")
        or value.get("feedback_constraint_scope"),
        "classification_reason": value.get("classification_reason")
        or value.get("feedback_classification_reason"),
        "hard_reject": _metadata_bool(value.get("hard_reject"))
        or _metadata_bool(value.get("feedback_hard_reject"))
        or hard_reject,
    }


def _history_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("planning history values must be finite")
        return value
    if isinstance(value, Enum):
        return _history_json_value(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): _history_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if "truth" not in str(key).strip().lower()
        }
    if isinstance(value, (tuple, list)):
        return [_history_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_history_json_value(item) for item in value]
        return sorted(normalized, key=repr)
    raise TypeError(
        "planning history values must use JSON-native types; "
        f"got {type(value).__name__}"
    )


def summarize_incremental_planning_comparison(
    incremental_plan: AssignmentPlan,
    full_plan: AssignmentPlan,
    *,
    previous_plan: AssignmentPlan | None = None,
    full_latency_ms: float = 0.0,
    cost_tolerance: float = 1e-9,
) -> IncrementalPlanningComparisonSummary:
    """Compare incremental and full plans without changing planner defaults."""

    incremental_latency_ms = max(
        0.0,
        float(incremental_plan.metadata.get("incremental_solver_elapsed_ms", 0.0)),
    )
    normalized_full_latency_ms = max(0.0, float(full_latency_ms))
    cost_delta = float(incremental_plan.total_cost - full_plan.total_cost)
    assignment_equivalent = (
        incremental_plan.stable_signature == full_plan.stable_signature
        and tuple(sorted(incremental_plan.unassigned_target_ids))
        == tuple(sorted(full_plan.unassigned_target_ids))
        and tuple(
            sorted(
                (summary.target_id, summary.demand_shortfall)
                for summary in incremental_plan.demand_summaries
            )
        )
        == tuple(
            sorted(
                (summary.target_id, summary.demand_shortfall)
                for summary in full_plan.demand_summaries
            )
        )
    )
    preserved_target_ids = tuple(
        str(value)
        for value in incremental_plan.metadata.get(
            "incremental_preserved_target_ids", ()
        )
    )
    preserved_target_set = set(preserved_target_ids)
    return IncrementalPlanningComparisonSummary(
        incremental_applied=bool(
            incremental_plan.metadata.get("incremental_applied", False)
        ),
        fallback_reason=_metadata_text(
            incremental_plan.metadata,
            "incremental_fallback_reason",
        ),
        cost_delta=cost_delta,
        cost_equivalent=abs(cost_delta) <= max(0.0, float(cost_tolerance)),
        assignment_equivalent=assignment_equivalent,
        incremental_latency_ms=incremental_latency_ms,
        full_latency_ms=normalized_full_latency_ms,
        latency_ratio=(
            None
            if normalized_full_latency_ms <= 0.0
            else incremental_latency_ms / normalized_full_latency_ms
        ),
        incremental_change_count=_plan_target_change_count(
            previous_plan,
            incremental_plan,
        ),
        full_change_count=_plan_target_change_count(previous_plan, full_plan),
        preserved_target_count=len(preserved_target_set),
        preserved_assignment_count=sum(
            1
            for assignment in incremental_plan.assignments
            if assignment.target_id in preserved_target_set
        ),
    )


def summarize_assignment_mismatch_replay(
    assignment_records: (
        AssignmentRecord
        | AssignmentValiditySummary
        | AssignmentMismatchReplaySummary
        | Mapping[str, Any]
        | Iterable[
            AssignmentRecord
            | AssignmentValiditySummary
            | AssignmentMismatchReplaySummary
            | Mapping[str, Any]
        ]
        | None
    ),
) -> AssignmentMismatchReplaySummary:
    """Summarize N/M assignment replay records without assuming equal sizes."""

    records = _record_items(assignment_records)
    if not records:
        return AssignmentMismatchReplaySummary()

    resource_ids = {
        value
        for record in records
        if (value := _record_text(record, "resource_id", "assigned_resource_id", "owner"))
    }
    target_ids = {
        value
        for record in records
        if (value := _record_text(record, "global_track_id", "target_id", "assigned_global_track_id"))
    }
    groups = _record_groups(records)

    return AssignmentMismatchReplaySummary(
        resource_count=max(
            _record_ints(records, "resource_count"),
            default=len(resource_ids),
        ),
        target_count=max(
            _record_ints(records, "target_count"),
            default=len(target_ids),
        ),
        assigned_count=sum(_group_assigned_count(group) for group in groups.values()),
        unassigned_high_threat_count=sum(
            max(_record_ints(group, "unassigned_high_threat_count"), default=0)
            for group in groups.values()
        ),
        hysteresis_reject_count=sum(
            max(
                _record_ints(group, "hysteresis_reject_count"),
                default=(
                    1
                    if any(
                        _record_text(record, "decision_state")
                        in {"held_by_hysteresis", "held_by_change_limit"}
                        for record in group
                    )
                    else 0
                ),
            )
            for group in groups.values()
        ),
        stale_reject_count=sum(
            max(
                _record_ints(group, "stale_reject_count"),
                default=(
                    1
                    if any(_record_bool(record, "stale_plan_version") for record in group)
                    else 0
                ),
            )
            for group in groups.values()
        ),
        reassign_count=sum(_group_reassign_count(group) for group in groups.values()),
    )


def summarize_terminal_feedback_calibration(
    assignment_records: (
        AssignmentRecord
        | AssignmentValiditySummary
        | AssignmentMismatchReplaySummary
        | Mapping[str, Any]
        | Iterable[
            AssignmentRecord
            | AssignmentValiditySummary
            | AssignmentMismatchReplaySummary
            | Mapping[str, Any]
        ]
        | None
    ) = None,
    feedback_records: (
        AssignmentFeedbackDecision
        | Mapping[str, Any]
        | Iterable[AssignmentFeedbackDecision | Mapping[str, Any]]
        | None
    ) = None,
) -> TerminalFeedbackCalibrationSummary:
    """Build an advisory calibration summary from multi-seed D3/D5 records.

    The helper reports reject patterns and tuning directions; it does not
    modify `CostWeights`, `PlannerConfig`, or any default threshold.
    """

    assignment_items = _record_items(assignment_records)
    feedback_items = tuple(dict(item) for item in _feedback_metadata_items(feedback_records))
    all_items = assignment_items + feedback_items
    mismatch_summary = summarize_assignment_mismatch_replay(assignment_items)

    duplicate_reject_count = _feedback_category_count(all_items, "duplicate")
    friend_reject_count = _feedback_category_count(all_items, "friend")
    fov_reject_count = _feedback_category_count(all_items, "fov")
    geometry_reject_count = _feedback_category_count(all_items, "geometry")
    seed_count = len(
        {
            value
            for item in all_items
            if (value := _record_text(item, "seed", "seed_id", "random_seed"))
        }
    )

    cost_suggestions = _terminal_feedback_cost_suggestions(
        duplicate_reject_count=duplicate_reject_count,
        friend_reject_count=friend_reject_count,
        fov_reject_count=fov_reject_count,
        geometry_reject_count=geometry_reject_count,
    )
    hysteresis_suggestions = _terminal_feedback_hysteresis_suggestions(
        mismatch_summary=mismatch_summary,
        duplicate_reject_count=duplicate_reject_count,
        friend_reject_count=friend_reject_count,
        fov_reject_count=fov_reject_count,
        geometry_reject_count=geometry_reject_count,
    )

    return TerminalFeedbackCalibrationSummary(
        seed_count=seed_count,
        assignment_record_count=len(assignment_items),
        feedback_record_count=len(feedback_items),
        duplicate_reject_count=duplicate_reject_count,
        friend_reject_count=friend_reject_count,
        fov_reject_count=fov_reject_count,
        geometry_reject_count=geometry_reject_count,
        mismatch_replay_summary=mismatch_summary,
        cost_suggestions=cost_suggestions,
        hysteresis_suggestions=hysteresis_suggestions,
        notes=(
            "advisory_summary_only",
            "planner_defaults_not_modified",
            "allow_local_rebind_false",
        ),
        auto_apply_defaults=False,
    )


def prepare_secondary_takeover_plan(
    plan: AssignmentPlan,
    *,
    supersedes_plan: AssignmentPlan,
    secondary_node_id: str,
    readiness_class: str,
    readiness_sustained: bool,
    activated_at_s: float,
    lease_expires_at_s: float,
    leader_epoch: int,
    takeover_reason: str = "d4_degrade_to_secondary",
    target_node_id: str | None = None,
    link_type: str = "d4_secondary_relay",
) -> AssignmentPlan:
    """Activate a D4/main-selected secondary takeover plan for D7 gating.

    D3 does not select the secondary node or decide readiness. Main calls this
    helper only after D4 reports sustained ``takeover_ready``. The helper
    rejects incomplete, expired, or non-monotonic activation contracts and
    stamps the owner/source/version/lease/epoch evidence used by D7 and D6.
    """

    owner_node_id = secondary_node_id.strip()
    if not owner_node_id:
        raise ValueError("secondary_node_id is required for secondary takeover")
    if owner_node_id.lower() in {"secondary", "secondary_node", "center", "c2"}:
        raise ValueError("secondary_node_id must identify a concrete secondary node")
    superseded_owner_node_id = (
        _metadata_text(supersedes_plan.metadata, "owner_node_id")
        or supersedes_plan.source_node_id
    )
    if superseded_owner_node_id == owner_node_id:
        raise ValueError("secondary owner must differ from the superseded plan owner")
    normalized_readiness = readiness_class.strip()
    if normalized_readiness != SECONDARY_TAKEOVER_READY:
        raise ValueError("secondary takeover requires takeover_ready readiness")
    if not readiness_sustained:
        raise ValueError("secondary takeover readiness must be sustained")
    activation_time = float(activated_at_s)
    lease_expiry = float(lease_expires_at_s)
    if lease_expiry <= activation_time:
        raise ValueError("secondary takeover lease is expired at activation")
    activation_epoch = int(leader_epoch)
    if activation_epoch <= 0:
        raise ValueError("secondary leader epoch must be positive")
    if plan.version == supersedes_plan.version:
        if plan.plan_id != supersedes_plan.plan_id:
            raise ValueError(
                "secondary takeover plan identity must be newer or retain the current plan id"
            )
        if plan.execution_signature() != supersedes_plan.execution_signature():
            raise ValueError(
                "takeover candidate changed execution semantics without advancing identity"
            )
        next_version = supersedes_plan.version + 1
        next_plan_id = f"d3-plan-{uuid4().hex[:12]}"
        plan = replace(
            plan,
            plan_id=next_plan_id,
            version=next_version,
            created_at=activation_time,
            last_changed_at=activation_time,
            previous_plan_id=supersedes_plan.plan_id,
            assignments=tuple(
                replace(
                    assignment,
                    plan_version=next_version,
                    metadata={
                        **dict(assignment.metadata),
                        "current_plan_id": next_plan_id,
                        "current_plan_version": next_version,
                        "plan_version": next_version,
                    },
                )
                for assignment in plan.assignments
            ),
        )
    elif plan.version != supersedes_plan.version + 1:
        raise ValueError(
            "secondary takeover plan version must extend the superseded plan exactly once"
        )
    elif plan.plan_id == supersedes_plan.plan_id:
        next_plan_id = f"d3-plan-{uuid4().hex[:12]}"
        plan = replace(
            plan,
            plan_id=next_plan_id,
            created_at=activation_time,
            last_changed_at=activation_time,
            previous_plan_id=supersedes_plan.plan_id,
            assignments=tuple(
                replace(
                    assignment,
                    metadata={
                        **dict(assignment.metadata),
                        "current_plan_id": next_plan_id,
                        "current_plan_version": plan.version,
                        "plan_version": plan.version,
                        "identity_created_at_s": activation_time,
                        "last_evaluated_at_s": activation_time,
                    },
                )
                for assignment in plan.assignments
            ),
            metadata={
                **dict(plan.metadata),
                "new_plan_lineage_reason": "secondary_takeover_owner_change",
                "plan_refresh_only": False,
                "identity_created_at_s": activation_time,
                "last_evaluated_at_s": activation_time,
            },
        )
    if plan.plan_id == supersedes_plan.plan_id:
        raise ValueError("secondary takeover plan id must differ from the superseded plan")
    if plan.previous_plan_id != supersedes_plan.plan_id:
        raise ValueError("secondary takeover plan does not supersede the given plan")
    if activation_time < plan.created_at:
        raise ValueError("secondary takeover activation precedes plan creation")
    superseded_epoch = _metadata_int(
        supersedes_plan.metadata.get("secondary_leader_epoch")
    )
    if superseded_epoch is not None and activation_epoch <= superseded_epoch:
        raise ValueError("secondary leader epoch must be newer than the superseded epoch")

    plan_target_node_id = target_node_id or plan.target_node_id or supersedes_plan.target_node_id
    metadata: dict[str, Any] = {
        **dict(plan.metadata),
        "plan_schema": SECONDARY_PLAN_SCHEMA_V2,
        "plan_owner": "secondary",
        "active_plan_owner": "secondary",
        "current_plan_id": plan.plan_id,
        "current_plan_version": plan.version,
        "current_plan_owner": "secondary",
        "current_plan_owner_node_id": owner_node_id,
        "owner_node_id": owner_node_id,
        "selected_secondary_node_id": owner_node_id,
        "secondary_plan_version": plan.version,
        "secondary_takeover_state": SECONDARY_PLAN_ACTIVE_STATE,
        "secondary_readiness_class": normalized_readiness,
        "secondary_readiness_sustained": True,
        "secondary_activated_at_s": activation_time,
        "secondary_plan_executable": True,
        "secondary_lease_valid_at_activation": True,
        "secondary_epoch_monotonic": True,
        "source_node_id": owner_node_id,
        "target_node_id": plan_target_node_id,
        "link_type": link_type,
        "takeover_reason": takeover_reason,
        "supersedes_plan_id": supersedes_plan.plan_id,
        "supersedes_plan_version": supersedes_plan.version,
        "previous_plan_id": supersedes_plan.plan_id,
        "previous_plan_version": supersedes_plan.version,
        "plan_version": plan.version,
        "new_plan_lineage_reason": "secondary_takeover_owner_change",
        "plan_refresh_only": False,
        "evaluation_refresh_only": False,
        "identity_created_at_s": activation_time,
        "last_evaluated_at_s": activation_time,
        "allow_local_rebind": False,
        "secondary_lease_expires_at_s": lease_expiry,
        "secondary_leader_epoch": activation_epoch,
    }

    assignments: list[Assignment] = []
    for assignment in plan.assignments:
        assignment_target_node_id = assignment.target_node_id or assignment.resource_id
        assignments.append(
            replace(
                assignment,
                source_node_id=owner_node_id,
                target_node_id=assignment_target_node_id,
                link_type=link_type,
                plan_version=plan.version,
                metadata={
                    **dict(assignment.metadata),
                    "plan_schema": SECONDARY_PLAN_SCHEMA_V2,
                    "plan_owner": "secondary",
                    "active_plan_owner": "secondary",
                    "current_plan_id": plan.plan_id,
                    "current_plan_version": plan.version,
                    "current_plan_owner": "secondary",
                    "current_plan_owner_node_id": owner_node_id,
                    "owner_node_id": owner_node_id,
                    "selected_secondary_node_id": owner_node_id,
                    "secondary_plan_version": plan.version,
                    "secondary_takeover_state": SECONDARY_PLAN_ACTIVE_STATE,
                    "secondary_readiness_class": normalized_readiness,
                    "secondary_readiness_sustained": True,
                    "secondary_activated_at_s": activation_time,
                    "secondary_plan_executable": True,
                    "secondary_lease_valid_at_activation": True,
                    "secondary_epoch_monotonic": True,
                    "secondary_lease_expires_at_s": lease_expiry,
                    "secondary_leader_epoch": activation_epoch,
                    "source_node_id": owner_node_id,
                    "target_node_id": assignment_target_node_id,
                    "link_type": link_type,
                    "takeover_reason": takeover_reason,
                    "supersedes_plan_id": supersedes_plan.plan_id,
                    "supersedes_plan_version": supersedes_plan.version,
                    "plan_version": plan.version,
                    "new_plan_lineage_reason": "secondary_takeover_owner_change",
                    "plan_refresh_only": False,
                    "evaluation_refresh_only": False,
                    "identity_created_at_s": activation_time,
                    "last_evaluated_at_s": activation_time,
                    "allow_local_rebind": False,
                },
            )
        )

    return replace(
        plan,
        assignments=tuple(assignments),
        previous_plan_id=supersedes_plan.plan_id,
        source_node_id=owner_node_id,
        target_node_id=plan_target_node_id,
        link_type=link_type,
        metadata=metadata,
    )


def continue_active_secondary_plan(
    plan: AssignmentPlan,
    *,
    previous_plan: AssignmentPlan,
    readiness_class: str,
    readiness_sustained: bool,
    published_at_s: float,
    lease_expires_at_s: float,
    leader_epoch: int,
) -> AssignmentPlan:
    """Keep a rolling plan under the same active secondary owner.

    ``AssignmentPlanner.plan`` remains owner-neutral and emits center defaults.
    Main must pass its next candidate through this helper while a secondary
    owner is active. This is a continuation, not a new takeover.
    """

    previous_metadata = dict(previous_plan.metadata)
    if _plan_schema(previous_plan) != SECONDARY_PLAN_SCHEMA_V2:
        raise ValueError("previous plan is not an active secondary plan")
    if (
        _metadata_text(previous_metadata, "secondary_takeover_state")
        != SECONDARY_PLAN_ACTIVE_STATE
        or not _metadata_bool(previous_metadata.get("secondary_plan_executable"))
    ):
        raise ValueError("previous secondary plan is not active and executable")

    owner_node_id = (
        _metadata_text(previous_metadata, "owner_node_id")
        or _metadata_text(previous_metadata, "current_plan_owner_node_id")
        or previous_plan.source_node_id
    )
    if not owner_node_id or owner_node_id.lower() in {
        "secondary",
        "secondary_node",
        "center",
        "c2",
    }:
        raise ValueError("active secondary owner is missing or not concrete")
    if previous_plan.source_node_id not in {None, owner_node_id}:
        raise ValueError("previous secondary owner and source node disagree")

    normalized_readiness = readiness_class.strip()
    if normalized_readiness != SECONDARY_TAKEOVER_READY:
        raise ValueError("secondary continuation requires takeover_ready readiness")
    if not readiness_sustained:
        raise ValueError("secondary continuation readiness must be sustained")
    if plan.version <= previous_plan.version:
        raise ValueError("secondary continuation version must be newer")
    if plan.plan_id == previous_plan.plan_id:
        raise ValueError("secondary continuation plan id must be new")
    if plan.previous_plan_id != previous_plan.plan_id:
        raise ValueError("secondary continuation must extend the active plan")

    published_at = float(published_at_s)
    if published_at < plan.created_at:
        raise ValueError("secondary continuation publish time precedes plan creation")
    previous_lease_expiry = _metadata_float(
        previous_metadata.get("secondary_lease_expires_at_s")
    )
    if previous_lease_expiry is None or published_at > previous_lease_expiry:
        raise ValueError("previous secondary lease is expired")
    lease_expiry = float(lease_expires_at_s)
    if lease_expiry <= published_at:
        raise ValueError("secondary continuation lease is expired at publication")
    if lease_expiry < previous_lease_expiry:
        raise ValueError("secondary continuation lease must not regress")

    previous_epoch = _metadata_int(previous_metadata.get("secondary_leader_epoch"))
    continuation_epoch = int(leader_epoch)
    if previous_epoch is None or continuation_epoch < previous_epoch:
        raise ValueError("secondary leader epoch must not regress")

    link_type = previous_plan.link_type or "d4_secondary_relay"
    target_node_id = previous_plan.target_node_id or plan.target_node_id
    secondary_activated_at_s = _metadata_float(
        previous_metadata.get("secondary_activated_at_s")
    )
    metadata: dict[str, Any] = {
        **dict(plan.metadata),
        "plan_schema": SECONDARY_PLAN_SCHEMA_V2,
        "plan_owner": "secondary",
        "active_plan_owner": "secondary",
        "current_plan_id": plan.plan_id,
        "current_plan_version": plan.version,
        "current_plan_owner": "secondary",
        "current_plan_owner_node_id": owner_node_id,
        "owner_node_id": owner_node_id,
        "selected_secondary_node_id": owner_node_id,
        "secondary_plan_version": plan.version,
        "secondary_takeover_state": SECONDARY_PLAN_ACTIVE_STATE,
        "secondary_readiness_class": normalized_readiness,
        "secondary_readiness_sustained": True,
        "secondary_activated_at_s": secondary_activated_at_s,
        "secondary_rolled_at_s": published_at,
        "secondary_plan_executable": True,
        "secondary_lease_valid_at_activation": True,
        "secondary_epoch_monotonic": True,
        "secondary_lease_expires_at_s": lease_expiry,
        "secondary_leader_epoch": continuation_epoch,
        "source_node_id": owner_node_id,
        "target_node_id": target_node_id,
        "link_type": link_type,
        "takeover_reason": _metadata_text(previous_metadata, "takeover_reason"),
        "continuation_reason": "secondary_rolling_update",
        "supersedes_plan_id": previous_plan.plan_id,
        "supersedes_plan_version": previous_plan.version,
        "previous_plan_id": previous_plan.plan_id,
        "previous_plan_version": previous_plan.version,
        "plan_version": plan.version,
        "allow_local_rebind": False,
    }

    assignments = tuple(
        replace(
            assignment,
            source_node_id=owner_node_id,
            target_node_id=assignment.target_node_id or assignment.resource_id,
            link_type=link_type,
            plan_version=plan.version,
            metadata={
                **dict(assignment.metadata),
                "plan_schema": SECONDARY_PLAN_SCHEMA_V2,
                "plan_owner": "secondary",
                "active_plan_owner": "secondary",
                "current_plan_id": plan.plan_id,
                "current_plan_version": plan.version,
                "current_plan_owner": "secondary",
                "current_plan_owner_node_id": owner_node_id,
                "owner_node_id": owner_node_id,
                "selected_secondary_node_id": owner_node_id,
                "secondary_plan_version": plan.version,
                "secondary_takeover_state": SECONDARY_PLAN_ACTIVE_STATE,
                "secondary_readiness_class": normalized_readiness,
                "secondary_readiness_sustained": True,
                "secondary_activated_at_s": secondary_activated_at_s,
                "secondary_rolled_at_s": published_at,
                "secondary_plan_executable": True,
                "secondary_lease_valid_at_activation": True,
                "secondary_epoch_monotonic": True,
                "secondary_lease_expires_at_s": lease_expiry,
                "secondary_leader_epoch": continuation_epoch,
                "source_node_id": owner_node_id,
                "target_node_id": assignment.target_node_id
                or assignment.resource_id,
                "link_type": link_type,
                "continuation_reason": "secondary_rolling_update",
                "supersedes_plan_id": previous_plan.plan_id,
                "supersedes_plan_version": previous_plan.version,
                "previous_plan_id": previous_plan.plan_id,
                "previous_plan_version": previous_plan.version,
                "plan_version": plan.version,
                "allow_local_rebind": False,
            },
        )
        for assignment in plan.assignments
    )
    return replace(
        plan,
        assignments=assignments,
        previous_plan_id=previous_plan.plan_id,
        source_node_id=owner_node_id,
        target_node_id=target_node_id,
        link_type=link_type,
        metadata=metadata,
    )


def _vector3(value: Iterable[float] | None) -> tuple[float, float, float] | None:
    if value is None or isinstance(value, (str, bytes)):
        return None
    try:
        items = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if len(items) < 2:
        return None
    if len(items) == 2:
        return items[0], items[1], 0.0
    return items[0], items[1], items[2]


def _distance(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    return sqrt(sum((left - right) ** 2 for left, right in zip(a, b)))


def _speed(value: tuple[float, float, float] | None) -> float | None:
    if value is None:
        return None
    return sqrt(sum(component * component for component in value))


def _time_to_critical_zone(
    *,
    position: tuple[float, float, float] | None,
    velocity: tuple[float, float, float] | None,
    center: tuple[float, float, float] | None,
    distance_to_critical_zone_m: float | None,
) -> float | None:
    if distance_to_critical_zone_m is not None and distance_to_critical_zone_m <= 0.0:
        return 0.0
    if position is None or velocity is None or center is None:
        return None
    distance_to_center = _distance(position, center)
    if distance_to_center <= 0.0:
        return 0.0
    unit_to_center = tuple((center[index] - position[index]) / distance_to_center for index in range(3))
    closing_speed = sum(velocity[index] * unit_to_center[index] for index in range(3))
    if closing_speed <= 0.0:
        return None
    distance = max(0.0, float(distance_to_critical_zone_m or distance_to_center))
    return distance / closing_speed


def _proximity_component(
    distance_to_critical_zone_m: float | None,
    *,
    proximity_horizon_m: float,
) -> float:
    if distance_to_critical_zone_m is None:
        return 0.5
    if distance_to_critical_zone_m <= 0.0:
        return 1.0
    horizon = max(1.0, float(proximity_horizon_m))
    return _clamp01_model(1.0 - float(distance_to_critical_zone_m) / horizon)


def _ttc_component(
    time_to_critical_zone_s: float | None,
    *,
    ttc_horizon_s: float,
    ttc_urgent_s: float,
) -> float:
    if time_to_critical_zone_s is None:
        return 0.5
    ttc = max(0.0, float(time_to_critical_zone_s))
    urgent = max(0.0, float(ttc_urgent_s))
    horizon = max(urgent + 1.0, float(ttc_horizon_s))
    if ttc <= urgent:
        return 1.0
    if ttc >= horizon:
        return 0.0
    return _clamp01_model(1.0 - (ttc - urgent) / (horizon - urgent))


def _speed_component(
    speed_mps: float | None,
    *,
    speed_reference_mps: float,
) -> float:
    if speed_mps is None:
        return 0.5
    reference = max(1.0, float(speed_reference_mps))
    return _clamp01_model(float(speed_mps) / reference)


def _covariance_component(value: float | Mapping[str, Any] | Iterable[Any] | None) -> float:
    if value is None:
        return 0.5
    if isinstance(value, (int, float)):
        return _clamp01_model(float(value))
    if isinstance(value, Mapping):
        for key in ("normalized", "quality", "trace", "covariance"):
            nested = value.get(key)
            if isinstance(nested, (int, float)):
                return _clamp01_model(float(nested))
        return 0.5
    trace = _matrix_trace_model(value)
    if trace is None:
        return 0.5
    trace = max(0.0, trace)
    return _clamp01_model(trace / (trace + 1.0))


def _matrix_trace_model(value: Any) -> float | None:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        return None
    items = tuple(value)
    if not items:
        return 0.0
    first = items[0]
    if isinstance(first, Iterable) and not isinstance(first, (str, bytes, Mapping)):
        total = 0.0
        for index, row in enumerate(items):
            row_items = tuple(row)
            if index < len(row_items):
                try:
                    total += float(row_items[index])
                except (TypeError, ValueError):
                    pass
        return total
    total = 0.0
    for item in items:
        try:
            total += float(item)
        except (TypeError, ValueError):
            pass
    return total


def _target_state_component(target_state: str) -> float:
    state = str(target_state or "unknown").strip().lower()
    return {
        "hostile": 1.0,
        "engageable": 0.90,
        "inbound": 0.90,
        "confirmed": 0.75,
        "tracked": 0.70,
        "tentative": 0.45,
        "unknown": 0.50,
        "lost": 0.0,
        "dropped": 0.0,
        "deleted": 0.0,
    }.get(state, 0.50)


def _weighted_component_score(
    components: Mapping[str, float],
    weights: Mapping[str, float],
) -> float:
    weighted_total = 0.0
    weight_total = 0.0
    for name, value in components.items():
        weight = max(0.0, float(weights.get(name, 0.0)))
        weighted_total += weight * _clamp01_model(value)
        weight_total += weight
    if weight_total <= 0.0:
        return 0.0
    return _clamp01_model(weighted_total / weight_total)


def _threat_baseline_reasons(
    components: Mapping[str, float],
    target_state: str,
) -> tuple[str, ...]:
    reasons: list[str] = ["baseline_composed"]
    if components.get("critical_zone_proximity", 0.0) >= 0.75:
        reasons.append("critical_zone_proximity")
    if components.get("time_to_critical_zone", 0.0) >= 0.75:
        reasons.append("short_time_to_critical_zone")
    if components.get("speed", 0.0) >= 0.75:
        reasons.append("high_speed")
    if components.get("covariance", 0.0) >= 0.75:
        reasons.append("high_covariance_uncertainty")
    state = str(target_state or "unknown").strip().lower()
    if state:
        reasons.append(f"target_state_{state}")
    return tuple(reasons)


def _feedback_metadata_items(
    feedback_metadata: (
        AssignmentFeedbackDecision
        | Mapping[str, Any]
        | Iterable[AssignmentFeedbackDecision | Mapping[str, Any]]
        | None
    ),
) -> tuple[Mapping[str, Any], ...]:
    if feedback_metadata is None:
        return ()
    if isinstance(feedback_metadata, AssignmentFeedbackDecision):
        return (feedback_metadata.planner_metadata,)
    if isinstance(feedback_metadata, Mapping):
        return (feedback_metadata,)
    items: list[Mapping[str, Any]] = []
    for item in feedback_metadata:
        if isinstance(item, AssignmentFeedbackDecision):
            items.append(item.planner_metadata)
        elif isinstance(item, Mapping):
            items.append(item)
        else:
            raise TypeError("feedback metadata entries must be mappings or decisions")
    return tuple(items)


def _resolve_profile_value(
    *,
    explicit_value: str | None,
    metadata_items: tuple[Mapping[str, Any], ...],
    key: str,
    default: str,
) -> str:
    if explicit_value is not None and str(explicit_value).strip():
        return str(explicit_value).strip()
    values = {
        value
        for metadata in metadata_items
        if (value := _metadata_text(metadata, key)) is not None
    }
    if len(values) == 1:
        return next(iter(values))
    if len(values) > 1:
        return "mixed"
    return default


def _plan_target_change_count(
    previous_plan: AssignmentPlan | None,
    candidate_plan: AssignmentPlan,
) -> int:
    if previous_plan is None:
        return len(candidate_plan.assignments_by_target())

    def signatures(plan: AssignmentPlan) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            target_id: tuple(_assignment_signature(item) for item in assignments)
            for target_id, assignments in plan.assignments_by_target().items()
        }

    previous = signatures(previous_plan)
    candidate = signatures(candidate_plan)
    return sum(
        1
        for target_id in set(previous) | set(candidate)
        if previous.get(target_id) != candidate.get(target_id)
    )


def _record_items(
    records: (
        AssignmentRecord
        | AssignmentValiditySummary
        | AssignmentMismatchReplaySummary
        | Mapping[str, Any]
        | Iterable[
            AssignmentRecord
            | AssignmentValiditySummary
            | AssignmentMismatchReplaySummary
            | Mapping[str, Any]
        ]
        | None
    ),
) -> tuple[Mapping[str, Any], ...]:
    if records is None:
        return ()
    if isinstance(
        records,
        (
            AssignmentRecord,
            AssignmentValiditySummary,
            AssignmentMismatchReplaySummary,
            Mapping,
        ),
    ):
        return (_record_mapping(records),)
    return tuple(_record_mapping(record) for record in records)


def _record_mapping(
    record: (
        AssignmentRecord
        | AssignmentValiditySummary
        | AssignmentMismatchReplaySummary
        | Mapping[str, Any]
    ),
) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return record
    if hasattr(record, "__dict__"):
        return vars(record)
    raise TypeError("assignment replay records must be mappings or D3 dataclasses")


def _record_groups(
    records: Iterable[Mapping[str, Any]],
) -> dict[tuple[str | None, str | None, int | None, int | None], tuple[Mapping[str, Any], ...]]:
    grouped: dict[
        tuple[str | None, str | None, int | None, int | None],
        list[Mapping[str, Any]],
    ] = {}
    for index, record in enumerate(records):
        key = (
            _record_text(record, "seed", "seed_id", "random_seed"),
            _record_text(record, "plan_id") or f"record-{index}",
            _record_int(record.get("version")),
            _record_int(record.get("window_id")),
        )
        grouped.setdefault(key, []).append(record)
    return {key: tuple(value) for key, value in grouped.items()}


def _record_text(metadata: Mapping[str, Any], *keys: str) -> str | None:
    return _metadata_text(metadata, *keys)


def _record_bool(metadata: Mapping[str, Any], *keys: str) -> bool:
    for key in keys:
        if key in metadata:
            return _metadata_bool(metadata.get(key))
    return False


def _record_explicitly_inactive(metadata: Mapping[str, Any]) -> bool:
    if "active" not in metadata:
        return False
    return not _metadata_bool(metadata.get("active"))


def _record_int(value: Any) -> int | None:
    return _metadata_int(value)


def _record_ints(records: Iterable[Mapping[str, Any]], key: str) -> tuple[int, ...]:
    values: list[int] = []
    for record in records:
        value = _record_int(record.get(key))
        if value is not None:
            values.append(value)
    return tuple(values)


def _group_assigned_count(group: Iterable[Mapping[str, Any]]) -> int:
    group_tuple = tuple(group)
    explicit = _record_ints(group_tuple, "assigned_count")
    if explicit:
        return max(explicit)
    return sum(
        1
        for record in group_tuple
        if _record_text(record, "global_track_id", "target_id", "assigned_global_track_id")
        and not _record_explicitly_inactive(record)
    )


def _group_reassign_count(group: Iterable[Mapping[str, Any]]) -> int:
    group_tuple = tuple(group)
    explicit = _record_ints(group_tuple, "reassign_count")
    if explicit:
        return max(explicit)
    candidate_change = _record_ints(group_tuple, "candidate_change_count")
    if candidate_change and any(_record_bool(record, "changed") for record in group_tuple):
        return max(candidate_change)
    if any(_record_bool(record, "changed") for record in group_tuple) and any(
        _record_text(record, "previous_plan_id") for record in group_tuple
    ):
        return 1
    return 0


def _feedback_category_count(
    records: Iterable[Mapping[str, Any]],
    category: str,
) -> int:
    total = 0
    for record in records:
        explicit = _record_int(record.get(f"{category}_reject_count"))
        if explicit is not None:
            total += explicit
            continue
        if _record_bool(record, f"{category}_reject", f"{category}_rejected"):
            total += 1
            continue
        if _feedback_record_matches_category(record, category):
            total += 1
    return total


def _feedback_record_matches_category(
    record: Mapping[str, Any],
    category: str,
) -> bool:
    return _feedback_primary_category(record) == category


def _feedback_primary_category(record: Mapping[str, Any]) -> str | None:
    tokens = _feedback_record_tokens(record)
    if (
        _record_bool(record, "duplicate_terminal_lock_risk")
        or _record_int(record.get("duplicate_assignment_count")) not in {None, 0}
        or "duplicate" in tokens
    ):
        return "duplicate"
    if "friend" in tokens or "friend_overlap_hold" in tokens:
        return "friend"
    if (
        "geometry" in tokens
        or "pair_infeasible" in tokens
        or "infeasible" in tokens
        or _record_text(record, "feasibility_suggestion")
        == "temporarily_mark_current_edge_infeasible"
        or _has_false_feasibility(record.get("feasibility_by_resource"))
        or bool(record.get("prohibited_edges"))
    ):
        return "geometry"
    if (
        "fov" in tokens
        or _record_text(record, "fov_difficulty_suggestion")
        == "increase_current_edge"
        or bool(record.get("fov_difficulty_by_resource"))
    ):
        return "fov"
    return None


def _feedback_record_tokens(record: Mapping[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in (
        "terminal_feedback_state",
        "main_action",
        "planner_recommended_action",
        "recommended_action",
        "reject_reason",
        "revoke_reason",
        "reason",
        "d4_request",
        "feasibility_suggestion",
        "fov_difficulty_suggestion",
        "decision_state",
    ):
        value = record.get(key)
        if value is not None:
            tokens.update(str(value).strip().lower().split())
            tokens.add(str(value).strip().lower())
    raw_reasons = record.get("reasons") or ()
    if isinstance(raw_reasons, str):
        raw_reasons = (raw_reasons,)
    for reason in raw_reasons:
        text = str(reason).strip().lower()
        if text:
            tokens.update(text.split())
            tokens.add(text)
    return tokens


def _has_false_feasibility(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return any(not _metadata_bool(raw_value) for raw_value in value.values())


def _terminal_feedback_cost_suggestions(
    *,
    duplicate_reject_count: int,
    friend_reject_count: int,
    fov_reject_count: int,
    geometry_reject_count: int,
) -> Mapping[str, str]:
    return {
        "duplicate": (
            "review_conflict_or_feasibility_penalty_for_duplicate_lock_edges"
            if duplicate_reject_count
            else "insufficient_duplicate_reject_evidence"
        ),
        "friend": (
            "review_resource_hold_and_fov_penalty_for_friend_overlap"
            if friend_reject_count
            else "insufficient_friend_reject_evidence"
        ),
        "fov": (
            "review_fov_weight_or_fov_difficulty_cap"
            if fov_reject_count
            else "insufficient_fov_reject_evidence"
        ),
        "geometry": (
            "prefer_prohibited_edges_or_infeasible_penalty_for_geometry_rejects"
            if geometry_reject_count
            else "insufficient_geometry_reject_evidence"
        ),
    }


def _terminal_feedback_hysteresis_suggestions(
    *,
    mismatch_summary: AssignmentMismatchReplaySummary,
    duplicate_reject_count: int,
    friend_reject_count: int,
    fov_reject_count: int,
    geometry_reject_count: int,
) -> Mapping[str, str]:
    feedback_reject_count = (
        duplicate_reject_count
        + friend_reject_count
        + fov_reject_count
        + geometry_reject_count
    )
    if feedback_reject_count == 0:
        common = "insufficient_feedback_reject_evidence"
    elif mismatch_summary.hysteresis_reject_count > mismatch_summary.reassign_count:
        common = "review_lower_delta_min_dwell_or_change_limit_for_repeated_holds"
    elif mismatch_summary.reassign_count > max(1, mismatch_summary.hysteresis_reject_count * 2):
        common = "review_higher_delta_min_dwell_or_switch_penalty_for_churn"
    else:
        common = "keep_current_hysteresis_pending_more_seed_data"
    return {
        "duplicate": (
            "allow_previous_infeasible_bypass_or_secondary_arbitration"
            if duplicate_reject_count
            else common
        ),
        "friend": (
            "prefer_short_hold_before_replan_for_friend_overlap"
            if friend_reject_count
            else common
        ),
        "fov": (
            "review_dwell_when_fov_rejects_persist_across_seeds"
            if fov_reject_count
            else common
        ),
        "geometry": (
            "bypass_hysteresis_when_geometry_makes_previous_edge_infeasible"
            if geometry_reject_count
            else common
        ),
    }


def _metadata_text(metadata: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _metadata_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _metadata_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metadata_bool_optional(value: Any) -> bool | None:
    if value is None:
        return None
    return _metadata_bool(value)


def _metadata_text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    try:
        items = tuple(value)
    except TypeError:
        text = str(value).strip()
        return (text,) if text else ()
    return tuple(str(item).strip() for item in items if str(item).strip())


def _metadata_float_matrix(value: Any) -> tuple[tuple[float, ...], ...]:
    if value is None or isinstance(value, (str, bytes)):
        return ()
    rows: list[tuple[float, ...]] = []
    try:
        raw_rows = tuple(value)
    except TypeError:
        return ()
    for raw_row in raw_rows:
        if isinstance(raw_row, (str, bytes)):
            return ()
        try:
            rows.append(tuple(float(item) for item in raw_row))
        except (TypeError, ValueError):
            return ()
    return tuple(rows)


def _metadata_mapping_tuple(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return (dict(value),)
    try:
        items = tuple(value)
    except TypeError:
        return ()
    mappings: list[Mapping[str, Any]] = []
    for item in items:
        if isinstance(item, Mapping):
            mappings.append(dict(item))
    return tuple(mappings)


def _metadata_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _metadata_float_mapping(value: Any) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, item in value.items():
        try:
            result[str(key)] = float(item)
        except (TypeError, ValueError):
            continue
    return result


def _assignment_matrix_shape(
    value: Any,
    *,
    target_count: int,
    resource_count: int,
) -> tuple[int, int]:
    if isinstance(value, (list, tuple)):
        items = tuple(value)
        if len(items) == 2:
            try:
                return int(items[0]), int(items[1])
            except (TypeError, ValueError):
                pass
    return int(target_count), int(resource_count)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _terminal_feedback_event(
    metadata: Mapping[str, Any],
    *,
    target_id: str | None,
    resource_id: str | None,
    terminal_state: str | None,
    constraint_class: _FeedbackConstraintClass,
    classification_reason: str,
) -> Mapping[str, Any] | None:
    """Keep only D3-relevant, versioned terminal feedback evidence."""

    nested = metadata.get("coalition_visual_summary")
    summary = nested if isinstance(nested, Mapping) else metadata
    reason = _metadata_text(
        summary,
        "coalition_visual_reason",
        "reason",
    ) or _metadata_text(metadata, "coalition_visual_reason")
    conflict_state = _metadata_text(
        summary,
        "coalition_conflict_state",
    ) or _metadata_text(metadata, "coalition_conflict_state")
    stable_counts = summary.get("stable_lock_frame_count_by_resource")
    if not isinstance(stable_counts, Mapping):
        stable_counts = metadata.get("stable_lock_frame_count_by_resource")
    normalized_stable_counts: dict[str, int] = {}
    if isinstance(stable_counts, Mapping):
        for raw_resource_id, raw_count in stable_counts.items():
            try:
                normalized_stable_counts[str(raw_resource_id)] = max(
                    0,
                    int(raw_count),
                )
            except (TypeError, ValueError):
                continue
    required_stable_frames = summary.get(
        "required_stable_frames",
        metadata.get("required_stable_frames"),
    )
    if required_stable_frames is None:
        summary_metadata = summary.get("metadata")
        if isinstance(summary_metadata, Mapping):
            required_stable_frames = summary_metadata.get("required_stable_frames")
    try:
        normalized_required = (
            None
            if required_stable_frames is None
            else max(1, int(required_stable_frames))
        )
    except (TypeError, ValueError):
        normalized_required = None

    plan_version = metadata.get("plan_version", summary.get("plan_version"))
    try:
        normalized_plan_version = None if plan_version is None else int(plan_version)
    except (TypeError, ValueError):
        normalized_plan_version = None

    has_feedback_evidence = any(
        (
            terminal_state,
            reason,
            conflict_state,
            normalized_stable_counts,
            metadata.get("duplicate_terminal_lock_risk"),
            metadata.get("friend_conflict_state"),
        )
    )
    if not target_id or not has_feedback_evidence:
        return None
    return {
        "target_id": target_id,
        "resource_id": resource_id,
        "plan_version": normalized_plan_version,
        "terminal_feedback_state": terminal_state,
        "reason": reason,
        "coalition_conflict_state": conflict_state,
        "duplicate_terminal_lock_risk": _metadata_bool(
            metadata.get("duplicate_terminal_lock_risk")
            or summary.get("duplicate_terminal_lock_risk")
        ),
        "friend_conflict_state": _metadata_text(metadata, "friend_conflict_state"),
        "main_action": _metadata_text(
            metadata,
            "main_action",
            "planner_recommended_action",
            "recommended_action",
        ),
        "stable_lock_frame_count_by_resource": normalized_stable_counts,
        "required_stable_frames": normalized_required,
        "feedback_constraint_class": constraint_class.value,
        "feedback_constraint_scope": _feedback_constraint_scope(constraint_class),
        "feedback_classification_reason": classification_reason,
    }


def _classify_feedback_constraint(
    metadata: Mapping[str, Any],
    *,
    target_id: str | None,
    resource_id: str | None,
    terminal_state: str | None,
    action: str | None,
) -> tuple[_FeedbackConstraintClass, str]:
    """Classify D5 feedback without promoting pair uncertainty to resource hold."""

    values = _feedback_semantic_values(metadata)
    state = str(terminal_state or "").strip().lower()
    normalized_action = str(action or "").strip().lower()
    friend_state = str(metadata.get("friend_conflict_state") or "").strip().lower()
    explicit_class = _explicit_feedback_constraint_class(metadata)

    duplicate_assignment_count = _metadata_int(
        metadata.get("duplicate_assignment_count")
    )
    duplicate = (
        _metadata_bool(metadata.get("duplicate_terminal_lock_risk"))
        or _metadata_bool(metadata.get("duplicate_assignment"))
        or (duplicate_assignment_count is not None and duplicate_assignment_count > 0)
        or any(
            value.startswith(("duplicate_assignment", "duplicate_terminal_lock", "duplicate_lock"))
            for value in values
        )
    )
    if duplicate:
        return _FeedbackConstraintClass.EDGE_HARD, "duplicate_assignment_or_lock"

    if friend_state == "verified_friend_overlap" or any(
        value.startswith("verified_friend") for value in values
    ):
        return _FeedbackConstraintClass.TARGET_HARD, "verified_friend"
    if state == "friend_overlap_hold" or "friend_overlap_hold" in values:
        return _FeedbackConstraintClass.RESOURCE_HARD, "friend_overlap_hold"
    if state == "resource_unavailable" or "resource_unavailable" in values:
        return _FeedbackConstraintClass.RESOURCE_HARD, "resource_unavailable"

    coalition_conflict = str(
        metadata.get("coalition_conflict_state") or ""
    ).strip().lower()
    if (
        state in TERMINAL_FEEDBACK_ARBITRATION_STATES
        or coalition_conflict not in {"", "none"}
        or bool(values & _SAFETY_IDENTITY_CONFLICT_VALUES)
    ):
        return _FeedbackConstraintClass.EDGE_HARD, "safety_identity_conflict"

    raw_feasibility = metadata.get("feasibility_by_resource")
    explicit_feasibility_reject = (
        _has_false_feasibility(raw_feasibility)
        or bool(metadata.get("prohibited_edges"))
        or _metadata_bool(metadata.get("prohibit_assignment_suggested"))
        or _metadata_text(metadata, "feasibility_suggestion")
        == "temporarily_mark_current_edge_infeasible"
    )
    if explicit_feasibility_reject:
        return _FeedbackConstraintClass.EDGE_HARD, "explicit_feasibility_reject"

    resource_update = metadata.get("resource_update")
    explicit_resource_hold = (
        isinstance(resource_update, Mapping)
        and _metadata_bool(resource_update.get("operator_hold"))
    ) or _metadata_bool(metadata.get("operator_hold_suggested"))
    if explicit_class in {
        _FeedbackConstraintClass.RESOURCE_HARD,
        _FeedbackConstraintClass.TARGET_HARD,
        _FeedbackConstraintClass.EDGE_HARD,
    }:
        return explicit_class, "explicit_constraint_class"
    if explicit_resource_hold and target_id is None:
        return _FeedbackConstraintClass.RESOURCE_HARD, "explicit_resource_hard_hold"

    edge_context = target_id is not None and resource_id is not None
    if explicit_resource_hold and edge_context:
        return _FeedbackConstraintClass.EDGE_SOFT, "legacy_pair_hold_downgraded"
    if explicit_class == _FeedbackConstraintClass.EDGE_SOFT:
        return explicit_class, (
            _metadata_text(metadata, "feedback_classification_reason")
            or "explicit_edge_soft_feedback"
        )
    if state in _SOFT_TERMINAL_FEEDBACK_STATES or normalized_action in {
        "hold",
        "replan",
    }:
        return _FeedbackConstraintClass.EDGE_SOFT, "ordinary_terminal_uncertainty"
    if edge_context and (
        bool(values & _SOFT_FEEDBACK_EVIDENCE_VALUES)
        or bool(metadata.get("fov_difficulty_by_resource"))
        or _metadata_text(metadata, "fov_difficulty_suggestion")
        == "increase_current_edge"
    ):
        return (
            _FeedbackConstraintClass.EDGE_SOFT,
            "geometry_fov_or_detection_instability",
        )
    if normalized_action == "secondary_arbitration" and edge_context:
        return _FeedbackConstraintClass.EDGE_HARD, "legacy_secondary_arbitration"
    if explicit_class is not None:
        return explicit_class, "explicit_constraint_class"
    return _FeedbackConstraintClass.NONE, "no_planner_constraint"


def _explicit_feedback_constraint_class(
    metadata: Mapping[str, Any],
) -> _FeedbackConstraintClass | None:
    raw_value = _metadata_text(
        metadata,
        "feedback_constraint_class",
        "constraint_class",
    )
    aliases = {
        "edge_soft": _FeedbackConstraintClass.EDGE_SOFT,
        "soft": _FeedbackConstraintClass.EDGE_SOFT,
        "edge_hard": _FeedbackConstraintClass.EDGE_HARD,
        "hard": _FeedbackConstraintClass.EDGE_HARD,
        "resource": _FeedbackConstraintClass.RESOURCE_HARD,
        "target": _FeedbackConstraintClass.TARGET_HARD,
    }
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if normalized in aliases:
        return aliases[normalized]
    try:
        return _FeedbackConstraintClass(normalized)
    except ValueError:
        return None


def _feedback_constraint_scope(constraint_class: _FeedbackConstraintClass) -> str:
    return {
        _FeedbackConstraintClass.NONE: "none",
        _FeedbackConstraintClass.EDGE_SOFT: "resource_target_edge",
        _FeedbackConstraintClass.EDGE_HARD: "resource_target_edge",
        _FeedbackConstraintClass.RESOURCE_HARD: "resource",
        _FeedbackConstraintClass.TARGET_HARD: "target",
    }[constraint_class]


def _feedback_semantic_values(metadata: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    pending: list[Mapping[str, Any]] = [metadata]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        for key in (
            "terminal_feedback_state",
            "friend_conflict_state",
            "coalition_conflict_state",
            "decision_state",
            "reason",
            "reasons",
            "reject_reason",
            "revoke_reason",
            "visual_png_handoff_blockers",
        ):
            raw_value = current.get(key)
            raw_items = (raw_value,) if isinstance(raw_value, str) else raw_value or ()
            if not isinstance(raw_items, (tuple, list, set, frozenset)):
                raw_items = (raw_items,)
            for raw_item in raw_items:
                text = str(raw_item).strip().lower()
                if not text:
                    continue
                values.add(text)
                split_text = text
                for delimiter in (":", ",", ";", "/", "|", " "):
                    split_text = split_text.replace(delimiter, " ")
                values.update(part for part in split_text.split() if part)
        if _metadata_bool(current.get("duplicate_terminal_lock_risk")):
            values.add("duplicate_terminal_lock_risk")
        duplicate_count = _metadata_int(current.get("duplicate_assignment_count"))
        if duplicate_count is not None and duplicate_count > 0:
            values.add("duplicate_assignment")
        for nested_key in ("coalition_visual_summary", "consistency", "metadata"):
            nested = current.get(nested_key)
            if isinstance(nested, Mapping):
                pending.append(nested)
    return values


def _clamp01_model(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _feedback_decision(
    *,
    action: str,
    state: str,
    reasons: list[str],
    plan_version: int | None,
    resource_id: str | None,
    target_id: str | None,
    duplicate_terminal_lock_risk: bool = False,
    feedback_profile_id: str = DEFAULT_FEEDBACK_PROFILE_ID,
    feedback_profile_version: str = DEFAULT_FEEDBACK_PROFILE_VERSION,
) -> AssignmentFeedbackDecision:
    return AssignmentFeedbackDecision(
        recommended_action=action,
        terminal_feedback_state=state,
        duplicate_terminal_lock_risk=duplicate_terminal_lock_risk,
        allow_local_rebind=False,
        reasons=tuple(reasons),
        plan_version=plan_version,
        main_action=action,
        planner_metadata=_feedback_planner_metadata(
            action=action,
            state=state,
            reasons=reasons,
            plan_version=plan_version,
            resource_id=resource_id,
            target_id=target_id,
            duplicate_terminal_lock_risk=duplicate_terminal_lock_risk,
            feedback_profile_id=feedback_profile_id,
            feedback_profile_version=feedback_profile_version,
        ),
    )


def _feedback_planner_metadata(
    *,
    action: str,
    state: str,
    reasons: list[str],
    plan_version: int | None,
    resource_id: str | None,
    target_id: str | None,
    duplicate_terminal_lock_risk: bool,
    feedback_profile_id: str,
    feedback_profile_version: str,
) -> dict[str, Any]:
    if duplicate_terminal_lock_risk:
        constraint_class = _FeedbackConstraintClass.EDGE_HARD
        classification_reason = "duplicate_assignment_or_lock"
    elif state == "friend_overlap_hold":
        constraint_class = _FeedbackConstraintClass.RESOURCE_HARD
        classification_reason = "friend_overlap_hold"
    elif state in TERMINAL_FEEDBACK_ARBITRATION_STATES:
        constraint_class = _FeedbackConstraintClass.EDGE_HARD
        classification_reason = "safety_identity_conflict"
    elif action == "continue":
        constraint_class = _FeedbackConstraintClass.NONE
        classification_reason = "no_planner_constraint"
    else:
        constraint_class = _FeedbackConstraintClass.EDGE_SOFT
        classification_reason = "ordinary_terminal_uncertainty"
    operator_hold = constraint_class == _FeedbackConstraintClass.RESOURCE_HARD
    prohibit_assignment = constraint_class == _FeedbackConstraintClass.EDGE_HARD
    increase_fov = action in {"hold", "replan", "secondary_arbitration"}
    metadata: dict[str, Any] = {
        "main_action": action,
        "planner_recommended_action": action,
        "terminal_feedback_state": state,
        "duplicate_terminal_lock_risk": duplicate_terminal_lock_risk,
        "allow_local_rebind": False,
        "operator_hold_suggested": operator_hold,
        "prohibit_assignment_suggested": prohibit_assignment,
        "feasibility_suggestion": (
            "temporarily_mark_current_edge_infeasible"
            if prohibit_assignment
            else "review_current_edge"
            if action == "replan"
            else "unchanged"
        ),
        "fov_difficulty_suggestion": (
            "increase_current_edge" if increase_fov else "unchanged"
        ),
        "d7_gate_action": "hold" if action != "continue" else "continue",
        "d4_request": (
            "secondary_arbitration" if action == "secondary_arbitration" else None
        ),
        "reasons": tuple(reasons),
        "plan_version": plan_version,
        "feedback_profile_schema": TERMINAL_FEEDBACK_PROFILE_SCHEMA_V1,
        "feedback_profile_id": str(feedback_profile_id),
        "feedback_profile_version": str(feedback_profile_version),
        "feedback_constraint_classification_schema": (
            _FEEDBACK_CONSTRAINT_CLASSIFICATION_SCHEMA_V1
        ),
        "feedback_constraint_class": constraint_class.value,
        "feedback_constraint_scope": _feedback_constraint_scope(constraint_class),
        "feedback_classification_reason": classification_reason,
        "feedback_hard_reject": constraint_class
        in {
            _FeedbackConstraintClass.EDGE_HARD,
            _FeedbackConstraintClass.RESOURCE_HARD,
            _FeedbackConstraintClass.TARGET_HARD,
        },
    }
    if resource_id is not None:
        metadata["resource_id"] = resource_id
        metadata["resource_update"] = {
            "resource_id": resource_id,
            "operator_hold": operator_hold,
        }
    if target_id is not None:
        metadata["target_id"] = target_id
    if resource_id is not None and target_id is not None:
        if prohibit_assignment:
            metadata["prohibited_edges"] = (
                {"target_id": target_id, "resource_id": resource_id},
            )
            metadata["feasibility_by_resource"] = {resource_id: False}
        else:
            metadata["prohibited_edges"] = ()
            metadata["feasibility_by_resource"] = {}
        metadata["fov_difficulty_by_resource"] = (
            {resource_id: 1.0} if increase_fov else {}
        )
    return metadata


def _assignment_latency_s(
    *,
    plan: AssignmentPlan,
    assignment_latency_s: float | None,
    input_timestamp_s: float | None,
) -> float:
    if assignment_latency_s is not None:
        return max(0.0, float(assignment_latency_s))
    source_timestamp = input_timestamp_s
    for key in ("input_timestamp_s", "measurement_timestamp", "valid_at"):
        if source_timestamp is None and key in plan.metadata:
            source_timestamp = float(plan.metadata[key])
    if source_timestamp is None:
        return 0.0
    return max(0.0, plan.created_at - float(source_timestamp))


def _cost_margin(plan: AssignmentPlan) -> float:
    if plan.previous_total_cost_current is not None and plan.candidate_total_cost is not None:
        return float(plan.previous_total_cost_current - plan.candidate_total_cost)
    if plan.candidate_total_cost is not None:
        return float(plan.total_cost - plan.candidate_total_cost)
    return 0.0


def _hysteresis_reject_count(plan: AssignmentPlan) -> int:
    explicit = _metadata_int(plan.metadata.get("hysteresis_reject_count"))
    if explicit is not None:
        return explicit
    return 1 if plan.decision_state in {"held_by_hysteresis", "held_by_change_limit"} else 0


def _stale_reject_count(
    plan: AssignmentPlan,
    *,
    stale_plan_version: bool = False,
) -> int:
    explicit = _metadata_int(plan.metadata.get("stale_reject_count"))
    if explicit is not None:
        return explicit
    if _metadata_bool(plan.metadata.get("stale_plan_rejected")):
        return 1
    return 1 if stale_plan_version else 0


def _reassign_count(
    plan: AssignmentPlan,
    *,
    previous_plan: AssignmentPlan | None = None,
) -> int:
    explicit = _metadata_int(plan.metadata.get("reassign_count"))
    if explicit is not None:
        return explicit
    if previous_plan is not None:
        return _assignment_change_count(previous_plan.assignments, plan.assignments)
    candidate_change_count = _metadata_int(plan.metadata.get("candidate_change_count"))
    if candidate_change_count is not None and plan.changed:
        return candidate_change_count
    if plan.changed and plan.previous_plan_id:
        return len(plan.assignments)
    return 0


def _assignment_change_count(
    previous_assignments: Iterable[Assignment],
    current_assignments: Iterable[Assignment],
) -> int:
    def grouped(
        assignments: Iterable[Assignment],
    ) -> dict[str, frozenset[tuple[Any, ...]]]:
        result: dict[str, set[tuple[Any, ...]]] = {}
        for assignment in assignments:
            signature = _assignment_signature(assignment)
            result.setdefault(assignment.target_id, set()).add(signature[1:])
        return {key: frozenset(value) for key, value in result.items()}

    previous_map = grouped(previous_assignments)
    current_map = grouped(current_assignments)
    target_ids = set(previous_map) | set(current_map)
    return sum(
        1 for target_id in target_ids if previous_map.get(target_id) != current_map.get(target_id)
    )


def _stale_plan_version(
    *,
    plan: AssignmentPlan,
    latest_version: int | None,
    latest_plan_id: str | None,
) -> bool:
    if latest_version is not None and plan.version != latest_version:
        return True
    if latest_plan_id is not None and plan.plan_id != latest_plan_id:
        return True
    return False


def _duplicate_assignment_count(plan: AssignmentPlan) -> int:
    target_to_resources: dict[str, set[str]] = {}
    resource_to_targets: dict[str, set[str]] = {}
    target_to_assignments: dict[str, list[Assignment]] = {}
    invalid_count = 0
    coalition_by_id = {
        coalition.coalition_id: coalition for coalition in plan.coalitions
    }
    for assignment in plan.assignments:
        target_to_resources.setdefault(assignment.target_id, set()).add(assignment.resource_id)
        resource_to_targets.setdefault(assignment.resource_id, set()).add(assignment.target_id)
        target_to_assignments.setdefault(assignment.target_id, []).append(assignment)
        coalition = (
            coalition_by_id.get(assignment.coalition_id)
            if assignment.coalition_id is not None
            else None
        )
        coalition_invalid = assignment.coalition_id is not None and (
            coalition is None
            or coalition.version != assignment.coalition_version
            or coalition.state != CoalitionState.COMMITTED.value
            or not coalition.complete
        )
        metadata_invalid = any(
            _metadata_bool(assignment.metadata.get(key))
            for key in ("stale", "unauthorized", "revoked")
        ) or assignment.metadata.get("authorized") is False
        if (
            assignment.feasibility_state in {"stale", "unauthorized", "revoked"}
            or coalition_invalid
            or metadata_invalid
        ):
            invalid_count += 1

    coalition_by_target = {coalition.target_id: coalition for coalition in plan.coalitions}
    duplicate_targets = 0
    for target_id, assignments in target_to_assignments.items():
        required = max(item.required_resource_count for item in assignments)
        coalition = coalition_by_target.get(target_id)
        if coalition is not None:
            required = coalition.required_resource_count
        coalition_keys = {
            (item.coalition_id, item.coalition_version)
            for item in assignments
            if item.coalition_id is not None
        }
        unauthorized_multiplicity = len(assignments) > 1 and (
            len(coalition_keys) > 1
            or coalition is None
            or (
                coalition is not None
                and any(
                    item.coalition_id != coalition.coalition_id
                    or item.coalition_version != coalition.version
                    for item in assignments
                )
            )
        )
        if len(target_to_resources[target_id]) > required or unauthorized_multiplicity:
            duplicate_targets += 1
    duplicate_resources = sum(
        1 for targets in resource_to_targets.values() if len(targets) > 1
    )
    return duplicate_targets + duplicate_resources + invalid_count


def _unassigned_high_threat_count(
    *,
    plan: AssignmentPlan,
    tracks: Iterable[TargetTrack] | None,
    high_threat_target_ids: Iterable[str] | None,
    high_threat_threshold: float,
) -> int:
    if high_threat_target_ids is None:
        high_threat = {
            track.track_id
            for track in tracks or ()
            if track.threat_score >= high_threat_threshold
        }
    else:
        high_threat = {str(target_id) for target_id in high_threat_target_ids}
    return sum(1 for target_id in plan.unassigned_target_ids if target_id in high_threat)


def _plan_resource_count(plan: AssignmentPlan) -> int:
    if plan.resource_count:
        return plan.resource_count
    return len({assignment.resource_id for assignment in plan.assignments})


def _plan_target_count(plan: AssignmentPlan) -> int:
    if plan.target_count:
        return plan.target_count
    target_ids = {assignment.target_id for assignment in plan.assignments}
    target_ids.update(plan.unassigned_target_ids)
    return len(target_ids)


def _guidance_binding_state(
    *,
    plan: AssignmentPlan,
    assignment: Assignment,
    stale: bool,
    revoked_plan_versions: set[int] | frozenset[int],
    hold_resource_ids: set[str] | frozenset[str],
    reassigned: bool,
) -> str:
    if plan.version in revoked_plan_versions:
        return GUIDANCE_BINDING_REVOKED
    if stale:
        return GUIDANCE_BINDING_STALE
    if assignment.resource_id in hold_resource_ids:
        return GUIDANCE_BINDING_HOLD
    if _terminal_feedback_state(plan, assignment) in TERMINAL_FEEDBACK_HOLD_STATES | TERMINAL_FEEDBACK_REPLAN_STATES | TERMINAL_FEEDBACK_ARBITRATION_STATES:
        return GUIDANCE_BINDING_HOLD
    if plan.duplicate_terminal_lock_risk or assignment.duplicate_terminal_lock_risk:
        return GUIDANCE_BINDING_HOLD
    if _state(plan.human_authorization_state) not in EFFECTIVE_GUIDANCE_AUTH_STATES:
        return GUIDANCE_BINDING_HOLD
    if assignment.feasibility_state != "feasible":
        return GUIDANCE_BINDING_HOLD
    return GUIDANCE_BINDING_ACTIVE


def _guidance_revoke_reason(
    *,
    plan: AssignmentPlan,
    assignment: Assignment,
    stale: bool,
    revoked_plan_versions: set[int] | frozenset[int],
    hold_resource_ids: set[str] | frozenset[str],
) -> str | None:
    if plan.version in revoked_plan_versions:
        return "plan_version_revoked"
    if stale:
        return "plan_stale"
    if assignment.resource_id in hold_resource_ids:
        return "resource_hold_requested"
    terminal_feedback_state = _terminal_feedback_state(plan, assignment)
    if terminal_feedback_state in TERMINAL_FEEDBACK_HOLD_STATES | TERMINAL_FEEDBACK_REPLAN_STATES | TERMINAL_FEEDBACK_ARBITRATION_STATES:
        return f"terminal_feedback_{terminal_feedback_state}"
    if plan.duplicate_terminal_lock_risk or assignment.duplicate_terminal_lock_risk:
        return "duplicate_terminal_lock_risk"
    if _state(plan.human_authorization_state) not in EFFECTIVE_GUIDANCE_AUTH_STATES:
        return "authorization_not_effective"
    if assignment.feasibility_state != "feasible":
        return f"assignment_{assignment.feasibility_state}"
    return None


def _terminal_feedback_state(plan: AssignmentPlan, assignment: Assignment) -> str | None:
    return assignment.terminal_feedback_state or plan.terminal_feedback_state


def _plan_schema(plan: AssignmentPlan) -> str:
    for key in ("plan_schema", "plan_type", "schema"):
        value = plan.metadata.get(key)
        if value:
            return str(value)
    return plan.plan_schema


def _resource_actor_name(
    *,
    resource_id: str,
    vehicle_name: str | None,
    metadata: Mapping[str, Any],
) -> str | None:
    return (
        _optional_alias(metadata, "resource_actor_name", "actor_name", "vehicle_name")
        or vehicle_name
        or resource_id
    )


def _optional_alias(aliases: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = aliases.get(name)
        if value is not None:
            text = str(value)
            if text:
                return text
    return None


def _mesh_aliases(aliases: Mapping[str, Any]) -> tuple[str, ...]:
    raw = aliases.get("target_mesh_aliases", aliases.get("mesh_aliases", ()))
    if raw is None:
        raw = ()
    if isinstance(raw, str):
        values = (raw,)
    else:
        values = tuple(str(value) for value in raw)
    extra = [
        _optional_alias(aliases, "target_actor_name", "actor_name"),
        _optional_alias(aliases, "target_object_id", "object_id"),
    ]
    ordered: list[str] = []
    for value in (*values, *extra):
        if value and value not in ordered:
            ordered.append(value)
    return tuple(ordered)


def _actor_aliases(
    *,
    resource_id: str,
    target_id: str,
    resource_actor_name: str | None,
    aliases: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "resource_id": resource_id,
        "target_id": target_id,
    }
    if resource_actor_name:
        result["resource_actor_name"] = resource_actor_name
    target_actor_name = _optional_alias(aliases, "target_actor_name", "actor_name")
    target_object_id = _optional_alias(aliases, "target_object_id", "object_id")
    target_mesh_aliases = _mesh_aliases(aliases)
    if target_actor_name:
        result["target_actor_name"] = target_actor_name
    if target_object_id:
        result["target_object_id"] = target_object_id
    if target_mesh_aliases:
        result["target_mesh_aliases"] = target_mesh_aliases
    return result


def _state(value: str | None) -> str:
    return (value or "").strip().lower()
