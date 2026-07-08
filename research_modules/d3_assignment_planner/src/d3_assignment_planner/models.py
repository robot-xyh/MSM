"""Data models for abstract resource-target assignment research."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping


CostBreakdown = dict[str, float]

TERMINAL_FEEDBACK_HOLD_STATES = frozenset(
    {"ambiguous", "hold", "friend_overlap_hold"}
)
TERMINAL_FEEDBACK_REPLAN_STATES = frozenset({"reacquire"})
TERMINAL_FEEDBACK_ARBITRATION_STATES = frozenset(
    {"mismatch", "multi_frame_inconsistent", "cross_view_conflict"}
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
SECONDARY_PLAN_SCHEMA_V2 = "secondary_plan_v2"
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
    resource_count: int = 0
    target_count: int = 0

    def assignment_map(self) -> dict[str, str]:
        """Return target_id -> resource_id for assigned targets."""

        return {item.target_id: item.resource_id for item in self.assignments}

    @property
    def plan_version(self) -> int:
        """Alias used by cross-node messages."""

        return self.version


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
    assignment_matrix_shape: tuple[int, int] | None = None
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
    total_cost: float | None = None
    candidate_total_cost: float | None = None
    previous_total_cost_current: float | None = None
    cost_margin: float | None = None
    stale_after_s: float | None = None


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
            "plan_schema": self.plan_schema,
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
    plan_schema = _plan_schema(plan)
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
                metadata={
                    "assignment_cost": assignment.cost,
                    "assignment_feasibility_state": assignment.feasibility_state,
                    "plan_schema": plan_schema,
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
    *,
    resource_id: str | None = None,
    target_id: str | None = None,
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
        )

    return _feedback_decision(
        action="continue",
        state=state,
        reasons=["terminal_feedback_consistent"],
        plan_version=plan_version,
        resource_id=resource_id,
        target_id=target_id,
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
) -> TerminalFeedbackWriteback:
    """Apply D5 feedback metadata to the next D3 planning inputs.

    This helper only maps already-authoritative metadata into D3's own input
    DTOs. It does not infer visual identity, choose a secondary node, or allow
    local `global_track_id` rebinding.
    """

    track_tuple = tuple(tracks)
    resource_tuple = tuple(resources)
    metadata_items = _feedback_metadata_items(feedback_metadata)
    if not metadata_items:
        return TerminalFeedbackWriteback(
            tracks=track_tuple,
            resources=resource_tuple,
            metadata={
                "feedback_count": 0,
                "allow_local_rebind": False,
            },
        )

    target_feasibility: dict[str, dict[str, bool]] = {}
    target_fov: dict[str, dict[str, float]] = {}
    hold_resource_ids: list[str] = []
    hold_resource_set: set[str] = set()
    prohibited_edges: list[tuple[str, str]] = []
    prohibited_edge_set: set[tuple[str, str]] = set()
    d4_requests: list[str] = []
    d7_gate_action = "continue"

    def add_hold(resource_id: str | None) -> None:
        if resource_id and resource_id not in hold_resource_set:
            hold_resource_set.add(resource_id)
            hold_resource_ids.append(resource_id)

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

        if d4_request:
            _append_unique(d4_requests, d4_request)
        if gate_action and gate_action != "continue":
            d7_gate_action = gate_action
        elif action and action != "continue" and d7_gate_action == "continue":
            d7_gate_action = "hold"

        resource_update = metadata.get("resource_update")
        if isinstance(resource_update, Mapping):
            update_resource_id = (
                _metadata_text(resource_update, "resource_id") or resource_id
            )
            if _metadata_bool(resource_update.get("operator_hold")):
                add_hold(update_resource_id)

        if (
            _metadata_bool(metadata.get("operator_hold_suggested"))
            or action == "hold"
            or terminal_state == "friend_overlap_hold"
        ):
            add_hold(resource_id)

        if _metadata_bool(metadata.get("duplicate_terminal_lock_risk")):
            add_prohibited_edge(target_id, resource_id)

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
    for track in track_tuple:
        feasibility = dict(track.feasibility_by_resource)
        fov = dict(track.fov_difficulty_by_resource)
        changed = False
        if track.track_id in target_feasibility:
            feasibility.update(target_feasibility[track.track_id])
            changed = True
        if track.track_id in target_fov:
            for resource_id, value in target_fov[track.track_id].items():
                fov[resource_id] = max(float(fov.get(resource_id, 0.0)), value)
            changed = True
        if changed:
            updated_target_ids.append(track.track_id)
            updated_tracks.append(
                replace(
                    track,
                    feasibility_by_resource=feasibility,
                    fov_difficulty_by_resource=fov,
                    metadata={
                        **dict(track.metadata),
                        "terminal_feedback_writeback_applied": True,
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
        "updated_target_ids": tuple(updated_target_ids),
        "updated_resource_ids": tuple(updated_resource_ids),
        "d7_gate_action": d7_gate_action,
        "d4_requests": tuple(d4_requests),
        "allow_local_rebind": False,
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
        stale_plan_version=_stale_plan_version(
            plan=plan,
            latest_version=latest_version,
            latest_plan_id=latest_plan_id,
        ),
        duplicate_assignment_count=_duplicate_assignment_count(plan.assignments),
        unassigned_high_threat_count=_unassigned_high_threat_count(
            plan=plan,
            tracks=tracks,
            high_threat_target_ids=high_threat_target_ids,
            high_threat_threshold=high_threat_threshold,
        ),
        resource_count=_plan_resource_count(plan),
        target_count=_plan_target_count(plan),
    )


def assignment_records_from_plan(
    plan: AssignmentPlan,
    *,
    timestamp: float | None = None,
    authorization_state: str | None = "recorded",
    truth_id_by_target: Mapping[str, str] | None = None,
    active: bool = True,
) -> tuple[AssignmentRecord, ...]:
    """Export D6-compatible assignment records from a D3 plan."""

    record_timestamp = plan.created_at if timestamp is None else float(timestamp)
    record_auth = (
        plan.human_authorization_state
        if authorization_state is None
        else authorization_state
    )
    truth_id_by_target = truth_id_by_target or {}
    plan_metadata = dict(plan.metadata)
    resource_count = _plan_resource_count(plan)
    target_count = _plan_target_count(plan)
    assignment_matrix_shape = _assignment_matrix_shape(
        plan_metadata.get("assignment_matrix_shape"),
        target_count=target_count,
        resource_count=resource_count,
    )
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
    return tuple(
        AssignmentRecord(
            timestamp=record_timestamp,
            plan_id=plan.plan_id,
            version=plan.version,
            resource_id=assignment.resource_id,
            global_track_id=assignment.target_id,
            cost_breakdown=dict(assignment.cost_breakdown),
            authorization_state=record_auth,
            active=active and assignment.feasibility_state == "feasible",
            truth_id=truth_id_by_target.get(assignment.target_id),
            window_id=plan.window_id,
            decision_state=plan.decision_state,
            changed=plan.changed,
            resource_count=resource_count,
            target_count=target_count,
            assignment_matrix_shape=assignment_matrix_shape,
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
            total_cost=plan.total_cost,
            candidate_total_cost=plan.candidate_total_cost,
            previous_total_cost_current=plan.previous_total_cost_current,
            cost_margin=_cost_margin(plan),
            stale_after_s=(
                assignment.stale_after_s
                if assignment.stale_after_s is not None
                else plan.stale_after_s
            ),
        )
        for assignment in plan.assignments
    )


def prepare_secondary_takeover_plan(
    plan: AssignmentPlan,
    *,
    supersedes_plan: AssignmentPlan,
    secondary_node_id: str,
    takeover_reason: str = "d4_degrade_to_secondary",
    target_node_id: str | None = None,
    link_type: str = "d4_secondary_relay",
    lease_expires_at_s: float | None = None,
    leader_epoch: int | None = None,
) -> AssignmentPlan:
    """Annotate a D4/main-selected secondary takeover plan for D7 gating.

    D3 does not select the secondary node. This helper validates that the
    candidate plan supersedes the previous active plan and then stamps the
    owner/source/version metadata needed by D7 and D6 consumers.
    """

    owner_node_id = secondary_node_id.strip()
    if not owner_node_id:
        raise ValueError("secondary_node_id is required for secondary takeover")
    if plan.version <= supersedes_plan.version:
        raise ValueError(
            "secondary takeover plan version must be newer than the superseded plan"
        )
    if plan.previous_plan_id not in {None, supersedes_plan.plan_id}:
        raise ValueError("secondary takeover plan does not supersede the given plan")

    plan_target_node_id = target_node_id or plan.target_node_id or supersedes_plan.target_node_id
    metadata: dict[str, Any] = {
        **dict(plan.metadata),
        "plan_schema": SECONDARY_PLAN_SCHEMA_V2,
        "plan_owner": "secondary",
        "active_plan_owner": "secondary",
        "owner_node_id": owner_node_id,
        "selected_secondary_node_id": owner_node_id,
        "source_node_id": owner_node_id,
        "target_node_id": plan_target_node_id,
        "link_type": link_type,
        "takeover_reason": takeover_reason,
        "supersedes_plan_id": supersedes_plan.plan_id,
        "supersedes_plan_version": supersedes_plan.version,
        "previous_plan_id": supersedes_plan.plan_id,
        "previous_plan_version": supersedes_plan.version,
        "plan_version": plan.version,
        "allow_local_rebind": False,
    }
    if lease_expires_at_s is not None:
        metadata["secondary_lease_expires_at_s"] = float(lease_expires_at_s)
    if leader_epoch is not None:
        metadata["secondary_leader_epoch"] = int(leader_epoch)

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
                    "owner_node_id": owner_node_id,
                    "selected_secondary_node_id": owner_node_id,
                    "source_node_id": owner_node_id,
                    "target_node_id": assignment_target_node_id,
                    "link_type": link_type,
                    "takeover_reason": takeover_reason,
                    "supersedes_plan_id": supersedes_plan.plan_id,
                    "supersedes_plan_version": supersedes_plan.version,
                    "plan_version": plan.version,
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
) -> dict[str, Any]:
    operator_hold = action == "hold"
    prohibit_assignment = action == "secondary_arbitration"
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


def _duplicate_assignment_count(assignments: Iterable[Assignment]) -> int:
    target_to_resources: dict[str, set[str]] = {}
    resource_to_targets: dict[str, set[str]] = {}
    for assignment in assignments:
        target_to_resources.setdefault(assignment.target_id, set()).add(assignment.resource_id)
        resource_to_targets.setdefault(assignment.resource_id, set()).add(assignment.target_id)
    duplicate_targets = sum(
        1 for resources in target_to_resources.values() if len(resources) > 1
    )
    duplicate_resources = sum(
        1 for targets in resource_to_targets.values() if len(targets) > 1
    )
    return duplicate_targets + duplicate_resources


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
    return ASSIGNMENT_PLAN_SCHEMA_V1


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
