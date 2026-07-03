"""Data models for abstract resource-target assignment research."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


CostBreakdown = dict[str, float]

TERMINAL_FEEDBACK_HOLD_STATES = frozenset({"ambiguous", "hold"})
TERMINAL_FEEDBACK_REPLAN_STATES = frozenset({"reacquire"})
TERMINAL_FEEDBACK_ARBITRATION_STATES = frozenset({"mismatch"})


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
