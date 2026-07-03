"""Data models for abstract resource-target assignment research."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


CostBreakdown = dict[str, float]

TERMINAL_FEEDBACK_HOLD_STATES = frozenset({"ambiguous", "hold"})
TERMINAL_FEEDBACK_REPLAN_STATES = frozenset({"reacquire"})
TERMINAL_FEEDBACK_ARBITRATION_STATES = frozenset({"mismatch"})
EFFECTIVE_GUIDANCE_AUTH_STATES = frozenset(
    {"recorded", "authorized", "approved", "human_approved", "operator_approved"}
)
GUIDANCE_BINDING_ACTIVE = "active"
GUIDANCE_BINDING_STALE = "stale"
GUIDANCE_BINDING_REVOKED = "revoked"
GUIDANCE_BINDING_REASSIGNED = "reassigned"
GUIDANCE_BINDING_HOLD = "hold"
GUIDANCE_BINDING_STATES = frozenset(
    {
        GUIDANCE_BINDING_ACTIVE,
        GUIDANCE_BINDING_STALE,
        GUIDANCE_BINDING_REVOKED,
        GUIDANCE_BINDING_REASSIGNED,
        GUIDANCE_BINDING_HOLD,
    }
)


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
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CostWeights:
    """Configurable weights for transparent cost terms."""

    window: float = 1.0
    covariance: float = 1.0
    threat: float = 1.0
    resource_state: float = 1.0
    fov: float = 1.0
    conflict: float = 1.0


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
    metadata: Mapping[str, Any] = field(default_factory=dict)


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

    def assignment_map(self) -> dict[str, str]:
        """Return target_id -> resource_id for assigned targets."""

        return {item.target_id: item.resource_id for item in self.assignments}

    @property
    def plan_version(self) -> int:
        """Alias used by cross-node messages."""

        return self.version


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
        return self.created_at + self.stale_after_s

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
            "binding_state": self.binding_state,
            "assignment_validity_state": self.assignment_validity_state,
            "created_at_s": self.created_at_s,
            "expires_at_s": self.expires_at_s,
            "vehicle_name": self.vehicle_name,
            "resource_actor_name": self.resource_actor_name,
            "target_actor_name": self.target_actor_name,
            "target_object_id": self.target_object_id,
            "target_mesh_aliases": list(self.target_mesh_aliases),
            "actor_aliases": dict(self.actor_aliases),
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
) -> tuple[AssignmentGuidanceBinding, ...]:
    """Build passive D7 guidance bindings from one versioned D3 plan."""

    resource_vehicle_map = resource_vehicle_map or {}
    target_alias_map = target_alias_map or {}
    now = plan.created_at if now_s is None else float(now_s)
    previous_by_resource = (
        {item.resource_id: item.target_id for item in previous_plan.assignments}
        if previous_plan is not None
        else {}
    )

    bindings: list[AssignmentGuidanceBinding] = []
    for index, assignment in enumerate(plan.assignments, start=1):
        target_id = assignment.target_id
        aliases = target_alias_map.get(target_id, {})
        stale_after_s = assignment.stale_after_s or plan.stale_after_s
        stale = stale_after_s is not None and now > plan.created_at + stale_after_s
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
                metadata={
                    "assignment_cost": assignment.cost,
                    "assignment_feasibility_state": assignment.feasibility_state,
                    "plan_decision_state": plan.decision_state,
                    "previous_plan_id": plan.previous_plan_id,
                    "previous_target_for_resource": previous_target_id,
                    "resource_reassigned": reassigned,
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


def evaluate_terminal_feedback(
    terminal_feedback_state: str | None,
    duplicate_terminal_lock_risk: bool = False,
    plan_version: int | None = None,
) -> AssignmentFeedbackDecision:
    """Return a conservative D3 recommendation for terminal feedback.

    The result never permits a local resource to rewrite `global_track_id`; it
    only recommends hold, central replan, or D4 secondary arbitration.
    """

    state = (terminal_feedback_state or "consistent").strip().lower()
    reasons: list[str] = []

    if duplicate_terminal_lock_risk:
        reasons.append("duplicate_terminal_lock_risk")
        return AssignmentFeedbackDecision(
            recommended_action="secondary_arbitration",
            terminal_feedback_state=state,
            duplicate_terminal_lock_risk=True,
            reasons=tuple(reasons),
            plan_version=plan_version,
        )

    if state in TERMINAL_FEEDBACK_ARBITRATION_STATES:
        reasons.append(f"terminal_feedback_{state}")
        return AssignmentFeedbackDecision(
            recommended_action="secondary_arbitration",
            terminal_feedback_state=state,
            reasons=tuple(reasons),
            plan_version=plan_version,
        )
    if state in TERMINAL_FEEDBACK_REPLAN_STATES:
        reasons.append(f"terminal_feedback_{state}")
        return AssignmentFeedbackDecision(
            recommended_action="replan",
            terminal_feedback_state=state,
            reasons=tuple(reasons),
            plan_version=plan_version,
        )
    if state in TERMINAL_FEEDBACK_HOLD_STATES:
        reasons.append(f"terminal_feedback_{state}")
        return AssignmentFeedbackDecision(
            recommended_action="hold",
            terminal_feedback_state=state,
            reasons=tuple(reasons),
            plan_version=plan_version,
        )

    return AssignmentFeedbackDecision(
        recommended_action="continue",
        terminal_feedback_state=state,
        reasons=("terminal_feedback_consistent",),
        plan_version=plan_version,
    )


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
    if _terminal_feedback_state(plan, assignment) in {"ambiguous", "hold", "reacquire", "mismatch"}:
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
    if terminal_feedback_state in {"ambiguous", "hold", "reacquire", "mismatch"}:
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
