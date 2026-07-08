"""Active degradation arbitration for offline D4 experiments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .coordinator import SECONDARY_NODE_ROLES
from .models import (
    AvailabilityBand,
    C2Health,
    CommunicationSummary,
    LinkType,
    PayloadKind,
    ResourceSummary,
    SecondaryNodeLifecycleSummary,
    to_jsonable,
)


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


class SecondaryTakeoverPlanState(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    PENDING_SECONDARY_PLAN = "pending_secondary_plan"
    SECONDARY_PLAN_ACTIVE = "secondary_plan_active"


_HARD_ASSIGNMENT_RISK_FACTORS = frozenset(
    {
        "d3_assignment_not_current",
        "d3_assignment_stale",
    }
)

_HARD_ACTIVE_ARBITRATION_RISK_FACTORS = frozenset(
    {
        "d1_track_uncertainty_high",
        "d1_covariance_trace_high",
        "d1_measurement_stale",
        "d2_id_switch_observed",
        "d2_duplicate_track_observed",
        "d2_track_continuity_low",
        *_HARD_ASSIGNMENT_RISK_FACTORS,
        "d5_duplicate_terminal_lock",
        "d5_resource_assignment_mismatch",
    }
)

_SOFT_CENTER_PLAN_RISK_FACTORS = frozenset(
    {
        "d3_assignment_cost_margin_low",
    }
)


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
    duplicate_terminal_lock: bool = False
    cross_view_risk_score: float = 0.0
    cross_view_support_count: int = 0


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
    cross_view_risk_high: float = 0.65
    non_locked_frame_limit: int = 3
    mismatch_frame_limit: int = 2
    min_dwell_s: float = 0.0
    release_consecutive_consistent_frames: int = 1
    risk_window_size: int = 1
    risk_window_threshold: int = 1


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

    def to_metrics(
        self,
        failover_time: float | None = None,
        secondary_selected_rate: float = 0.0,
        distributed_conflict_count: int = 0,
    ) -> dict[str, object]:
        return {
            "d4_action": self.action.value,
            "degradation_mode": self.mode.value,
            "target_node_id": self.target_node_id,
            "risk_factors": list(self.risk_factors),
            "terminal_consistent": self.terminal_consistent,
            "failover_time": failover_time,
            "secondary_selected_rate": secondary_selected_rate,
            "distributed_conflict_count": distributed_conflict_count,
        }


@dataclass(frozen=True)
class D7SecondaryHandoff:
    """D4-to-D7 handoff gate for secondary-node active degradation."""

    phase: int
    d4_action: DegradationAction
    d7_action: DegradationAction | None
    target_node_id: str | None
    reassignment_complete: bool
    visual_png_allowed: bool
    current_plan_id: str | None = None
    current_plan_version: int | None = None
    new_plan_id: str | None = None
    new_plan_version: int | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


@dataclass(frozen=True)
class SecondaryTakeoverPlanMetadata:
    """D4 record metadata for secondary takeover plan lifecycle.

    D4 does not create a D3 AssignmentPlan. This metadata only tells main/D3/D7
    which plan is still active, which secondary node is the proposed source,
    and whether a secondary plan id/version has already become active.
    """

    state: SecondaryTakeoverPlanState
    active_plan_owner: str
    pending_plan_owner: str | None = None
    secondary_plan_source_node_id: str | None = None
    current_plan_id: str | None = None
    current_plan_version: int | None = None
    secondary_plan_id: str | None = None
    secondary_plan_version: int | None = None
    secondary_supersedes_plan_id: str | None = None
    secondary_supersedes_plan_version: int | None = None
    secondary_reassignment_complete: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


class ActiveDegradationArbiter:
    """Rule-based arbiter for active/passive D4 degradation studies."""

    def __init__(self, config: ActiveDegradationConfig | None = None) -> None:
        self.config = config or ActiveDegradationConfig()
        self._last_degradation_time_s: float | None = None
        self._last_degradation_decision: ActiveDegradationDecision | None = None
        self._release_consistent_frames = 0
        self._risk_window: list[bool] = []

    def evaluate(
        self,
        track_uncertainty: TrackUncertaintySummary,
        association_risk: AssociationRiskSummary,
        assignment_validity: AssignmentValiditySummary,
        terminal_association: TerminalAssociationSummary,
        c2_health: C2Health,
        secondary_nodes: list[ResourceSummary],
        communication_summaries: list[CommunicationSummary] | None = None,
        current_time_s: float | None = None,
    ) -> ActiveDegradationDecision:
        coverage_cell = track_uncertainty.coverage_cell or terminal_association.coverage_cell
        secondary = self._select_secondary_node(
            secondary_nodes,
            coverage_cell,
            communication_summaries=communication_summaries,
            current_time_s=current_time_s,
        )
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
        risk_window_met = self._update_risk_window(
            bool(risk_factors) or not terminal_consistent or c2_health == C2Health.FAILED
        )

        if terminal_association.friend_conflict:
            return self._apply_hysteresis(
                ActiveDegradationDecision(
                    mode=DegradationMode.ACTIVE_DEGRADATION,
                    action=DegradationAction.HOLD_FOR_REVIEW,
                    reason="terminal_friend_conflict",
                    coverage_cell=coverage_cell,
                    terminal_consistent=False,
                    risk_factors=(*risk_factors, "terminal_friend_conflict"),
                    requires_human_review=True,
                ),
                current_time_s,
                terminal_consistent=False,
                risk_factors=(*risk_factors, "terminal_friend_conflict"),
            )

        if c2_health == C2Health.FAILED:
            return self._apply_hysteresis(
                self._fallback_decision(
                    DegradationMode.PASSIVE_FAILOVER,
                    secondary,
                    coverage_cell,
                    terminal_consistent,
                    risk_factors,
                    "center_failed_passive_failover",
                ),
                current_time_s,
                terminal_consistent=terminal_consistent,
                risk_factors=risk_factors,
            )

        if self._terminal_requires_active_arbitration(terminal_association) and risk_window_met:
            if not self._terminal_has_assignment_conflict(
                assignment_validity,
                terminal_association,
            ) and not self._risk_requires_active_arbitration(risk_factors):
                if secondary is not None:
                    return self._apply_hysteresis(
                        ActiveDegradationDecision(
                            mode=DegradationMode.ACTIVE_DEGRADATION,
                            action=DegradationAction.REQUEST_SECONDARY_ASSIST,
                            reason="terminal_persistent_reacquire_request_secondary_cue",
                            target_node_id=secondary.node_id,
                            coverage_cell=coverage_cell,
                            terminal_consistent=False,
                            risk_factors=(*risk_factors, "terminal_persistent_reacquire"),
                        ),
                        current_time_s,
                        terminal_consistent=False,
                        risk_factors=(*risk_factors, "terminal_persistent_reacquire"),
                    )
                return self._apply_hysteresis(
                    ActiveDegradationDecision(
                        mode=DegradationMode.NONE,
                        action=DegradationAction.CONTINUE_CENTER,
                        reason="terminal_persistent_reacquire_no_secondary",
                        coverage_cell=coverage_cell,
                        terminal_consistent=False,
                        risk_factors=(*risk_factors, "terminal_persistent_reacquire"),
                    ),
                    current_time_s,
                    terminal_consistent=False,
                    risk_factors=(*risk_factors, "terminal_persistent_reacquire"),
                )
            return self._apply_hysteresis(
                self._fallback_decision(
                    DegradationMode.ACTIVE_DEGRADATION,
                    secondary,
                    coverage_cell,
                    terminal_consistent,
                    (*risk_factors, "terminal_persistent_disagreement"),
                    "terminal_persistent_disagreement",
                ),
                current_time_s,
                terminal_consistent=terminal_consistent,
                risk_factors=(*risk_factors, "terminal_persistent_disagreement"),
            )

        if terminal_consistent and not risk_factors:
            return self._apply_hysteresis(
                ActiveDegradationDecision(
                    mode=DegradationMode.NONE,
                    action=DegradationAction.CONTINUE_CENTER,
                    reason="terminal_consistent_and_risk_low",
                    coverage_cell=coverage_cell,
                    terminal_consistent=True,
                ),
                current_time_s,
                terminal_consistent=True,
                risk_factors=(),
            )

        if terminal_consistent:
            if self._only_soft_center_plan_risk(risk_factors):
                return self._apply_hysteresis(
                    ActiveDegradationDecision(
                        mode=DegradationMode.NONE,
                        action=DegradationAction.CONTINUE_CENTER,
                        reason="soft_center_plan_risk_observe_more",
                        coverage_cell=coverage_cell,
                        terminal_consistent=True,
                        risk_factors=risk_factors,
                    ),
                    current_time_s,
                    terminal_consistent=True,
                    risk_factors=risk_factors,
                )
            if self._assignment_is_primary_risk(risk_factors) or (
                secondary is None and self._risk_requires_active_arbitration(risk_factors)
            ):
                return self._apply_hysteresis(
                    ActiveDegradationDecision(
                        mode=DegradationMode.ACTIVE_DEGRADATION,
                        action=DegradationAction.REQUEST_CENTER_REPLAN,
                        reason="risk_rising_terminal_still_consistent",
                        coverage_cell=coverage_cell,
                        terminal_consistent=True,
                        risk_factors=risk_factors,
                    ),
                    current_time_s,
                    terminal_consistent=True,
                    risk_factors=risk_factors,
                )
            return self._apply_hysteresis(
                ActiveDegradationDecision(
                    mode=(
                        DegradationMode.ACTIVE_DEGRADATION
                        if secondary is not None
                        else DegradationMode.NONE
                    ),
                    action=(
                        DegradationAction.REQUEST_SECONDARY_ASSIST
                        if secondary is not None
                        else DegradationAction.CONTINUE_CENTER
                    ),
                    reason=(
                        "risk_rising_request_secondary_assist"
                        if secondary is not None
                        else "soft_risk_terminal_consistent_observe_more"
                    ),
                    target_node_id=secondary.node_id if secondary is not None else None,
                    coverage_cell=coverage_cell,
                    terminal_consistent=True,
                    risk_factors=risk_factors,
                ),
                current_time_s,
                terminal_consistent=True,
                risk_factors=risk_factors,
            )

        if not self._risk_requires_active_arbitration(risk_factors):
            return self._apply_hysteresis(
                ActiveDegradationDecision(
                    mode=DegradationMode.NONE,
                    action=DegradationAction.CONTINUE_CENTER,
                    reason="terminal_transient_observe_more",
                    coverage_cell=coverage_cell,
                    terminal_consistent=False,
                    risk_factors=risk_factors,
                ),
                current_time_s,
                terminal_consistent=False,
                risk_factors=risk_factors,
            )

        if secondary is not None:
            return self._apply_hysteresis(
                ActiveDegradationDecision(
                    mode=DegradationMode.ACTIVE_DEGRADATION,
                    action=DegradationAction.REQUEST_SECONDARY_ASSIST,
                    reason="terminal_inconsistent_single_window",
                    target_node_id=secondary.node_id,
                    coverage_cell=coverage_cell,
                    terminal_consistent=False,
                    risk_factors=risk_factors,
                ),
                current_time_s,
                terminal_consistent=False,
                risk_factors=risk_factors,
            )

        return self._apply_hysteresis(
            ActiveDegradationDecision(
                mode=DegradationMode.ACTIVE_DEGRADATION,
                action=DegradationAction.REQUEST_CENTER_REPLAN,
                reason="terminal_inconsistent_no_secondary_single_window",
                coverage_cell=coverage_cell,
                terminal_consistent=False,
                risk_factors=risk_factors,
            ),
            current_time_s,
            terminal_consistent=False,
            risk_factors=risk_factors,
        )

    def _update_risk_window(self, risk_signal: bool) -> bool:
        size = max(1, int(self.config.risk_window_size))
        threshold = max(1, int(self.config.risk_window_threshold))
        self._risk_window.append(bool(risk_signal))
        if len(self._risk_window) > size:
            self._risk_window = self._risk_window[-size:]
        return sum(1 for item in self._risk_window if item) >= min(threshold, size)

    def _apply_hysteresis(
        self,
        decision: ActiveDegradationDecision,
        current_time_s: float | None,
        *,
        terminal_consistent: bool,
        risk_factors: tuple[str, ...],
    ) -> ActiveDegradationDecision:
        low_risk_release = terminal_consistent and not risk_factors
        if low_risk_release:
            self._release_consistent_frames += 1
        else:
            self._release_consistent_frames = 0

        if (
            decision.mode == DegradationMode.NONE
            and self._last_degradation_decision is not None
            and not self._release_condition_met(current_time_s)
        ):
            held = self._last_degradation_decision
            return ActiveDegradationDecision(
                mode=held.mode,
                action=held.action,
                reason="release_condition_pending",
                target_node_id=held.target_node_id,
                coverage_cell=held.coverage_cell,
                terminal_consistent=True,
                risk_factors=("release_condition_pending",),
                requires_human_review=held.requires_human_review,
            )

        if decision.mode == DegradationMode.NONE:
            self._last_degradation_decision = None
            self._last_degradation_time_s = None
            return decision

        self._last_degradation_decision = decision
        if current_time_s is not None:
            self._last_degradation_time_s = float(current_time_s)
        return decision

    def _release_condition_met(self, current_time_s: float | None) -> bool:
        required_frames = max(1, int(self.config.release_consecutive_consistent_frames))
        frames_ok = self._release_consistent_frames >= required_frames
        dwell = max(0.0, float(self.config.min_dwell_s))
        if current_time_s is None or self._last_degradation_time_s is None:
            return frames_ok and dwell == 0.0
        dwell_ok = (float(current_time_s) - self._last_degradation_time_s) >= dwell
        return frames_ok and dwell_ok

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
        if terminal.duplicate_terminal_lock:
            factors.append("d5_duplicate_terminal_lock")
        if terminal.cross_view_risk_score >= cfg.cross_view_risk_high:
            factors.append("d5_cross_view_risk_high")
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
        if terminal.duplicate_terminal_lock:
            return False
        if terminal.cross_view_risk_score >= self.config.cross_view_risk_high:
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

    def _terminal_has_assignment_conflict(
        self,
        assignment: AssignmentValiditySummary,
        terminal: TerminalAssociationSummary,
    ) -> bool:
        if terminal.friend_conflict:
            return True
        if terminal.duplicate_terminal_lock:
            return True
        if terminal.resource_id != assignment.assigned_resource_id:
            return True
        if terminal.assigned_global_track_id != assignment.global_track_id:
            return True
        return (
            terminal.observed_global_track_id is not None
            and terminal.observed_global_track_id != assignment.global_track_id
        )

    @staticmethod
    def _assignment_is_primary_risk(risk_factors: tuple[str, ...]) -> bool:
        return any(factor in _HARD_ASSIGNMENT_RISK_FACTORS for factor in risk_factors)

    @staticmethod
    def _risk_requires_active_arbitration(risk_factors: tuple[str, ...]) -> bool:
        """Return whether non-persistent terminal disagreement should escalate now."""

        return any(factor in _HARD_ACTIVE_ARBITRATION_RISK_FACTORS for factor in risk_factors)

    @staticmethod
    def _only_soft_center_plan_risk(risk_factors: tuple[str, ...]) -> bool:
        return bool(risk_factors) and all(
            factor in _SOFT_CENTER_PLAN_RISK_FACTORS for factor in risk_factors
        )

    @staticmethod
    def _select_secondary_node(
        resources: list[ResourceSummary],
        coverage_cell: str,
        communication_summaries: list[CommunicationSummary] | None = None,
        current_time_s: float | None = None,
    ) -> ResourceSummary | None:
        candidates = [
            resource
            for resource in resources
            if resource.node_role in SECONDARY_NODE_ROLES
            and not resource.operator_hold
            and resource.availability_band != AvailabilityBand.NONE
            and (resource.coverage_cell in {None, "", coverage_cell})
            and ActiveDegradationArbiter._secondary_heartbeat_is_usable(
                resource,
                current_time_s,
            )
            and ActiveDegradationArbiter._secondary_link_is_usable(
                resource,
                communication_summaries,
                current_time_s,
            )
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

    @staticmethod
    def _secondary_heartbeat_is_usable(
        resource: ResourceSummary,
        current_time_s: float | None,
    ) -> bool:
        if current_time_s is None or resource.heartbeat_timestamp_s is None:
            return True
        return float(current_time_s) - float(resource.heartbeat_timestamp_s) <= float(
            resource.heartbeat_stale_after_s
        )

    @staticmethod
    def _secondary_link_is_usable(
        resource: ResourceSummary,
        communication_summaries: list[CommunicationSummary] | None,
        current_time_s: float | None,
    ) -> bool:
        if communication_summaries is None:
            return True
        usable_link_types = {
            LinkType.C2_DIRECT,
            LinkType.SECONDARY_RELAY,
            LinkType.VIDEO_CUE,
        }
        usable_payloads = {
            PayloadKind.TRACK,
            PayloadKind.BBOX,
            PayloadKind.VIDEO_METADATA,
            PayloadKind.ASSIGNMENT,
            PayloadKind.TERMINAL_ASSOCIATION,
            PayloadKind.RESOURCE_SUMMARY,
            PayloadKind.HEALTH,
        }
        return any(
            summary.involves_node(resource.node_id)
            and summary.link_type in usable_link_types
            and summary.payload_kind in usable_payloads
            and not summary.is_stale(current_time_s)
            for summary in communication_summaries
        )


def build_d7_secondary_handoff(
    decision: ActiveDegradationDecision,
    *,
    current_plan_id: str | None = None,
    current_plan_version: int | None = None,
    new_plan_id: str | None = None,
    new_plan_version: int | None = None,
    secondary_plan_active: bool = False,
    terminal_consistent_after_plan: bool = False,
) -> D7SecondaryHandoff:
    """Build the two-stage D4/D7 handoff for secondary active degradation.

    Stage 1 is the frame where D4 emits ``degrade_to_secondary``. It means the
    secondary node has been selected but reassignment has not completed, so D7
    must not enter visual PNG on that frame. Stage 2 begins only after the
    secondary plan is active and carries the new plan id/version to D7.
    """

    if decision.action != DegradationAction.DEGRADE_TO_SECONDARY:
        return D7SecondaryHandoff(
            phase=2,
            d4_action=decision.action,
            d7_action=decision.action,
            target_node_id=decision.target_node_id,
            reassignment_complete=True,
            visual_png_allowed=decision.action
            in {DegradationAction.CONTINUE_CENTER, DegradationAction.REQUEST_SECONDARY_ASSIST},
            current_plan_id=current_plan_id,
            current_plan_version=current_plan_version,
            new_plan_id=new_plan_id,
            new_plan_version=new_plan_version,
            reason=decision.reason,
        )

    plan_ready = secondary_plan_active and new_plan_id is not None and new_plan_version is not None
    if not plan_ready:
        return D7SecondaryHandoff(
            phase=1,
            d4_action=decision.action,
            d7_action=None,
            target_node_id=decision.target_node_id,
            reassignment_complete=False,
            visual_png_allowed=False,
            current_plan_id=current_plan_id,
            current_plan_version=current_plan_version,
            reason="secondary_reassignment_pending",
        )

    return D7SecondaryHandoff(
        phase=2,
        d4_action=decision.action,
        d7_action=DegradationAction.CONTINUE_CENTER
        if terminal_consistent_after_plan
        else DegradationAction.REQUEST_SECONDARY_ASSIST,
        target_node_id=decision.target_node_id,
        reassignment_complete=True,
        visual_png_allowed=True,
        current_plan_id=current_plan_id,
        current_plan_version=current_plan_version,
        new_plan_id=new_plan_id,
        new_plan_version=new_plan_version,
        reason="secondary_plan_active",
    )


def build_secondary_takeover_plan_metadata(
    decision: ActiveDegradationDecision,
    *,
    current_plan_id: str | None = None,
    current_plan_version: int | None = None,
    current_plan_owner: str = "center",
    secondary_plan_id: str | None = None,
    secondary_plan_version: int | None = None,
    secondary_plan_active: bool = False,
    secondary_plan_source_node_id: str | None = None,
) -> SecondaryTakeoverPlanMetadata:
    """Build the D4 metadata contract for secondary takeover plan state."""

    source_node_id = secondary_plan_source_node_id or decision.target_node_id
    if decision.action != DegradationAction.DEGRADE_TO_SECONDARY:
        return SecondaryTakeoverPlanMetadata(
            state=SecondaryTakeoverPlanState.NOT_APPLICABLE,
            active_plan_owner=_active_owner_for_non_secondary(decision, current_plan_owner),
            current_plan_id=current_plan_id,
            current_plan_version=current_plan_version,
            secondary_plan_source_node_id=source_node_id,
            secondary_plan_id=secondary_plan_id,
            secondary_plan_version=secondary_plan_version,
            reason=decision.reason,
        )

    plan_ready = (
        secondary_plan_active
        and secondary_plan_id is not None
        and secondary_plan_version is not None
    )
    if not plan_ready:
        return SecondaryTakeoverPlanMetadata(
            state=SecondaryTakeoverPlanState.PENDING_SECONDARY_PLAN,
            active_plan_owner=current_plan_owner,
            pending_plan_owner="secondary_node",
            secondary_plan_source_node_id=source_node_id,
            current_plan_id=current_plan_id,
            current_plan_version=current_plan_version,
            secondary_plan_id=secondary_plan_id,
            secondary_plan_version=secondary_plan_version,
            secondary_supersedes_plan_id=current_plan_id,
            secondary_supersedes_plan_version=current_plan_version,
            secondary_reassignment_complete=False,
            reason="secondary_reassignment_pending",
        )

    return SecondaryTakeoverPlanMetadata(
        state=SecondaryTakeoverPlanState.SECONDARY_PLAN_ACTIVE,
        active_plan_owner="secondary_node",
        secondary_plan_source_node_id=source_node_id,
        current_plan_id=current_plan_id,
        current_plan_version=current_plan_version,
        secondary_plan_id=secondary_plan_id,
        secondary_plan_version=secondary_plan_version,
        secondary_supersedes_plan_id=current_plan_id,
        secondary_supersedes_plan_version=current_plan_version,
        secondary_reassignment_complete=True,
        reason="secondary_plan_active",
    )


def _active_owner_for_non_secondary(
    decision: ActiveDegradationDecision,
    current_plan_owner: str,
) -> str:
    if decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED:
        return "distributed_cbba"
    if decision.action == DegradationAction.HOLD_FOR_REVIEW:
        return "hold_review"
    return current_plan_owner


def summarize_secondary_lifecycle(
    resources: list[ResourceSummary],
    coverage_cell: str,
    communication_summaries: list[CommunicationSummary] | None = None,
    current_time_s: float | None = None,
) -> tuple[SecondaryNodeLifecycleSummary, ...]:
    summaries: list[SecondaryNodeLifecycleSummary] = []
    for resource in resources:
        if resource.node_role not in SECONDARY_NODE_ROLES:
            continue
        heartbeat_age = None
        if current_time_s is not None and resource.heartbeat_timestamp_s is not None:
            heartbeat_age = max(0.0, float(current_time_s) - float(resource.heartbeat_timestamp_s))
        video_freshness = _video_cue_freshness_s(
            resource,
            communication_summaries,
            current_time_s,
        )
        link_stale = None
        if communication_summaries is not None:
            link_stale = not ActiveDegradationArbiter._secondary_link_is_usable(
                resource,
                communication_summaries,
                current_time_s,
            )
        secondary_available = (
            not resource.operator_hold
            and resource.availability_band != AvailabilityBand.NONE
            and (resource.coverage_cell in {None, "", coverage_cell})
            and ActiveDegradationArbiter._secondary_heartbeat_is_usable(resource, current_time_s)
            and not bool(link_stale)
        )
        summaries.append(
            SecondaryNodeLifecycleSummary(
                node_id=resource.node_id,
                heartbeat_timestamp_s=resource.heartbeat_timestamp_s,
                heartbeat_age_s=heartbeat_age,
                lease_epoch=int(resource.lease_epoch),
                coverage_cell=resource.coverage_cell,
                video_cue_freshness_s=video_freshness,
                link_stale=link_stale,
                secondary_available=secondary_available,
                heartbeat=resource.heartbeat_timestamp_s,
                video_cue_freshness=video_freshness,
            )
        )
    return tuple(summaries)


def _video_cue_freshness_s(
    resource: ResourceSummary,
    communication_summaries: list[CommunicationSummary] | None,
    current_time_s: float | None,
) -> float | None:
    if communication_summaries is None or current_time_s is None:
        return None
    ages = [
        max(0.0, float(current_time_s) - summary.received_timestamp)
        for summary in communication_summaries
        if summary.involves_node(resource.node_id)
        and summary.link_type == LinkType.VIDEO_CUE
        and summary.payload_kind in {PayloadKind.BBOX, PayloadKind.VIDEO_METADATA}
    ]
    return min(ages) if ages else None
