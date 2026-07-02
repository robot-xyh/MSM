"""Active degradation arbitration for offline D4 experiments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .coordinator import SECONDARY_NODE_ROLES
from .models import AvailabilityBand, C2Health, ResourceSummary, to_jsonable


class DegradationMode(str, Enum):
    NONE = "none"
    PASSIVE_FAILOVER = "passive_failover"
    ACTIVE_DEGRADATION = "active_degradation"


class DegradationAction(str, Enum):
    CONTINUE_CENTER = "continue_center"
    REQUEST_CENTER_REPLAN = "request_center_replan"
    REQUEST_SECONDARY_ASSIST = "request_secondary_assist"
    DEGRADE_TO_SECONDARY = "degrade_to_secondary"
    DEGRADE_TO_DISTRIBUTED = "degrade_to_distributed"
    HOLD_FOR_REVIEW = "hold_for_review"


class TerminalDecisionState(str, Enum):
    LOCKED = "locked"
    AMBIGUOUS = "ambiguous"
    HOLD = "hold"
    REACQUIRE = "reacquire"


@dataclass(frozen=True)
class TrackUncertaintySummary:
    track_id: str
    coverage_cell: str
    position_sigma_m: float
    covariance_trace: float
    velocity_sigma_mps: float = 0.0
    measurement_age_s: float = 0.0


@dataclass(frozen=True)
class AssociationRiskSummary:
    track_id: str
    ambiguity_score: float = 0.0
    id_switch_count: int = 0
    duplicate_track_count: int = 0
    track_continuity: float = 1.0


@dataclass(frozen=True)
class AssignmentValiditySummary:
    global_track_id: str
    assigned_resource_id: str
    plan_version: int
    is_current: bool = True
    plan_age_s: float = 0.0
    cost_margin: float = 1.0


@dataclass(frozen=True)
class TerminalAssociationSummary:
    resource_id: str
    assigned_global_track_id: str
    decision_state: TerminalDecisionState
    association_confidence: float
    ambiguity_score: float
    coverage_cell: str
    observed_global_track_id: str | None = None
    consecutive_non_locked_frames: int = 0
    consecutive_mismatch_frames: int = 0
    friend_conflict: bool = False


@dataclass(frozen=True)
class ActiveDegradationConfig:
    position_sigma_medium_m: float = 20.0
    position_sigma_high_m: float = 50.0
    covariance_trace_high: float = 2500.0
    association_ambiguity_medium: float = 0.35
    association_ambiguity_high: float = 0.70
    track_continuity_low: float = 0.60
    max_plan_age_s: float = 4.0
    min_cost_margin: float = 0.10
    terminal_confidence_min: float = 0.65
    terminal_ambiguity_high: float = 0.55
    non_locked_frame_limit: int = 3
    mismatch_frame_limit: int = 2


@dataclass(frozen=True)
class ActiveDegradationDecision:
    mode: DegradationMode
    action: DegradationAction
    reason: str
    target_node_id: str | None = None
    coverage_cell: str | None = None
    terminal_consistent: bool = False
    risk_factors: tuple[str, ...] = ()
    requires_human_review: bool = False

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


class ActiveDegradationArbiter:
    """Rule-based arbiter for active/passive D4 degradation studies."""

    def __init__(self, config: ActiveDegradationConfig | None = None) -> None:
        self.config = config or ActiveDegradationConfig()

    def evaluate(
        self,
        track_uncertainty: TrackUncertaintySummary,
        association_risk: AssociationRiskSummary,
        assignment_validity: AssignmentValiditySummary,
        terminal_association: TerminalAssociationSummary,
        c2_health: C2Health,
        secondary_nodes: list[ResourceSummary],
    ) -> ActiveDegradationDecision:
        coverage_cell = track_uncertainty.coverage_cell or terminal_association.coverage_cell
        secondary = self._select_secondary_node(secondary_nodes, coverage_cell)
        terminal_consistent = self._terminal_is_consistent(
            assignment_validity,
            terminal_association,
        )
        risk_factors = self._risk_factors(
            track_uncertainty,
            association_risk,
            assignment_validity,
            terminal_association,
        )

        if c2_health == C2Health.FAILED:
            return self._fallback_decision(
                DegradationMode.PASSIVE_FAILOVER,
                secondary,
                coverage_cell,
                terminal_consistent,
                risk_factors,
                "center_failed_passive_failover",
            )

        if terminal_association.friend_conflict:
            return ActiveDegradationDecision(
                mode=DegradationMode.ACTIVE_DEGRADATION,
                action=DegradationAction.HOLD_FOR_REVIEW,
                reason="terminal_friend_conflict",
                coverage_cell=coverage_cell,
                terminal_consistent=False,
                risk_factors=(*risk_factors, "terminal_friend_conflict"),
                requires_human_review=True,
            )

        if self._terminal_requires_active_arbitration(terminal_association):
            return self._fallback_decision(
                DegradationMode.ACTIVE_DEGRADATION,
                secondary,
                coverage_cell,
                terminal_consistent,
                (*risk_factors, "terminal_persistent_disagreement"),
                "terminal_persistent_disagreement",
            )

        if terminal_consistent and not risk_factors:
            return ActiveDegradationDecision(
                mode=DegradationMode.NONE,
                action=DegradationAction.CONTINUE_CENTER,
                reason="terminal_consistent_and_risk_low",
                coverage_cell=coverage_cell,
                terminal_consistent=True,
            )

        if terminal_consistent:
            if self._assignment_is_primary_risk(risk_factors) or secondary is None:
                return ActiveDegradationDecision(
                    mode=DegradationMode.ACTIVE_DEGRADATION,
                    action=DegradationAction.REQUEST_CENTER_REPLAN,
                    reason="risk_rising_terminal_still_consistent",
                    coverage_cell=coverage_cell,
                    terminal_consistent=True,
                    risk_factors=risk_factors,
                )
            return ActiveDegradationDecision(
                mode=DegradationMode.ACTIVE_DEGRADATION,
                action=DegradationAction.REQUEST_SECONDARY_ASSIST,
                reason="risk_rising_request_secondary_assist",
                target_node_id=secondary.node_id,
                coverage_cell=coverage_cell,
                terminal_consistent=True,
                risk_factors=risk_factors,
            )

        if secondary is not None:
            return ActiveDegradationDecision(
                mode=DegradationMode.ACTIVE_DEGRADATION,
                action=DegradationAction.REQUEST_SECONDARY_ASSIST,
                reason="terminal_inconsistent_single_window",
                target_node_id=secondary.node_id,
                coverage_cell=coverage_cell,
                terminal_consistent=False,
                risk_factors=risk_factors,
            )

        return ActiveDegradationDecision(
            mode=DegradationMode.ACTIVE_DEGRADATION,
            action=DegradationAction.REQUEST_CENTER_REPLAN,
            reason="terminal_inconsistent_no_secondary_single_window",
            coverage_cell=coverage_cell,
            terminal_consistent=False,
            risk_factors=risk_factors,
        )

    def _fallback_decision(
        self,
        mode: DegradationMode,
        secondary: ResourceSummary | None,
        coverage_cell: str,
        terminal_consistent: bool,
        risk_factors: tuple[str, ...],
        reason: str,
    ) -> ActiveDegradationDecision:
        if secondary is not None:
            return ActiveDegradationDecision(
                mode=mode,
                action=DegradationAction.DEGRADE_TO_SECONDARY,
                reason=reason,
                target_node_id=secondary.node_id,
                coverage_cell=coverage_cell,
                terminal_consistent=terminal_consistent,
                risk_factors=risk_factors,
            )
        return ActiveDegradationDecision(
            mode=mode,
            action=DegradationAction.DEGRADE_TO_DISTRIBUTED,
            reason=reason,
            coverage_cell=coverage_cell,
            terminal_consistent=terminal_consistent,
            risk_factors=risk_factors,
        )

    def _risk_factors(
        self,
        track: TrackUncertaintySummary,
        association: AssociationRiskSummary,
        assignment: AssignmentValiditySummary,
        terminal: TerminalAssociationSummary,
    ) -> tuple[str, ...]:
        factors: list[str] = []
        cfg = self.config
        if track.position_sigma_m >= cfg.position_sigma_high_m:
            factors.append("d1_track_uncertainty_high")
        elif track.position_sigma_m >= cfg.position_sigma_medium_m:
            factors.append("d1_track_uncertainty_medium")
        if track.covariance_trace >= cfg.covariance_trace_high:
            factors.append("d1_covariance_trace_high")
        if track.measurement_age_s > cfg.max_plan_age_s:
            factors.append("d1_measurement_stale")
        if association.ambiguity_score >= cfg.association_ambiguity_high:
            factors.append("d2_association_ambiguity_high")
        elif association.ambiguity_score >= cfg.association_ambiguity_medium:
            factors.append("d2_association_ambiguity_medium")
        if association.id_switch_count > 0:
            factors.append("d2_id_switch_observed")
        if association.duplicate_track_count > 0:
            factors.append("d2_duplicate_track_observed")
        if association.track_continuity < cfg.track_continuity_low:
            factors.append("d2_track_continuity_low")
        if not assignment.is_current:
            factors.append("d3_assignment_not_current")
        if assignment.plan_age_s > cfg.max_plan_age_s:
            factors.append("d3_assignment_stale")
        if assignment.cost_margin < cfg.min_cost_margin:
            factors.append("d3_assignment_cost_margin_low")
        if terminal.resource_id != assignment.assigned_resource_id:
            factors.append("d5_resource_assignment_mismatch")
        if terminal.ambiguity_score >= cfg.terminal_ambiguity_high:
            factors.append("d5_terminal_ambiguity_high")
        if terminal.association_confidence < cfg.terminal_confidence_min:
            factors.append("d5_terminal_confidence_low")
        return tuple(factors)

    def _terminal_is_consistent(
        self,
        assignment: AssignmentValiditySummary,
        terminal: TerminalAssociationSummary,
    ) -> bool:
        if terminal.friend_conflict:
            return False
        if terminal.decision_state != TerminalDecisionState.LOCKED:
            return False
        if terminal.resource_id != assignment.assigned_resource_id:
            return False
        if terminal.assigned_global_track_id != assignment.global_track_id:
            return False
        if (
            terminal.observed_global_track_id is not None
            and terminal.observed_global_track_id != assignment.global_track_id
        ):
            return False
        if terminal.association_confidence < self.config.terminal_confidence_min:
            return False
        if terminal.ambiguity_score >= self.config.terminal_ambiguity_high:
            return False
        return True

    def _terminal_requires_active_arbitration(
        self,
        terminal: TerminalAssociationSummary,
    ) -> bool:
        if terminal.consecutive_mismatch_frames >= self.config.mismatch_frame_limit:
            return True
        if (
            terminal.decision_state
            in {
                TerminalDecisionState.AMBIGUOUS,
                TerminalDecisionState.HOLD,
                TerminalDecisionState.REACQUIRE,
            }
            and terminal.consecutive_non_locked_frames >= self.config.non_locked_frame_limit
        ):
            return True
        return False

    @staticmethod
    def _assignment_is_primary_risk(risk_factors: tuple[str, ...]) -> bool:
        return any(factor.startswith("d3_") for factor in risk_factors)

    @staticmethod
    def _select_secondary_node(
        resources: list[ResourceSummary],
        coverage_cell: str,
    ) -> ResourceSummary | None:
        candidates = [
            resource
            for resource in resources
            if resource.node_role in SECONDARY_NODE_ROLES
            and not resource.operator_hold
            and resource.availability_band != AvailabilityBand.NONE
            and (resource.coverage_cell in {None, "", coverage_cell})
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda resource: (
                int(resource.takeover_priority),
                -int(resource.lease_epoch),
                resource.node_id,
            )
        )
        return candidates[0]
