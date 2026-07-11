"""Active degradation arbitration for offline D4 experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .models import (
    AvailabilityBand,
    C2Health,
    CommunicationSummary,
    LinkType,
    PayloadKind,
    ResourceSummary,
    SecondaryNodeLifecycleSummary,
    is_fixed_tethered_secondary_resource,
    is_mobile_high_recon_resource,
    is_secondary_node_resource,
    node_role_value,
    secondary_capability_class,
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

TAKEOVER_READY_SECONDARY_CAPABILITY_CLASS = "takeover_ready"
REGISTRATION_USABLE_SECONDARY_CAPABILITY_CLASS = "registration_usable"
VISIBLE_ONLY_SECONDARY_CAPABILITY_CLASS = "visible_only"
NOT_READY_SECONDARY_CAPABILITY_CLASS = "not_ready"
_MIN_TAKEOVER_CAPABILITY_SCORE = 0.70
_MIN_TAKEOVER_COVERAGE_RATIO = 0.65
_MIN_TAKEOVER_NETWORK_FULL_VIEW_RATE = 0.80


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
    truth_metrics_available: bool = True
    continuity_available: bool = True


@dataclass(frozen=True)
class AssignmentValiditySummary:
    global_track_id: str
    assigned_resource_id: str
    plan_version: int
    is_current: bool = True
    plan_age_s: float = 0.0
    cost_margin: float = 1.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


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
    secondary_single_camera_full_view_frame_rate: float | None = None
    secondary_network_joint_full_view_frame_rate: float | None = None
    secondary_network_mean_coverage_ratio: float | None = None
    cue_freshness_s: float | None = None
    gimbal_pointing_ok: bool | None = None
    secondary_coverage_ratio: float | None = None
    cross_view_association_count: int | None = None
    stable_cross_view_registration_count: int | None = None
    not_registered_count: int | None = None
    cross_view_conversion_gap: float | str | None = None
    secondary_detect_to_cross_view_reject_reasons: tuple[str, ...] = ()
    secondary_detect_available_but_not_registered: bool = False
    secondary_detect_to_cross_view_diagnostic: str | None = None


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
    center_replan_cooldown_s: float = 2.0


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
    secondary_plan_lease_epoch: int | None = None
    required_secondary_plan_lease_epoch: int | None = None
    secondary_plan_lease_expires_at_s: float | None = None
    secondary_plan_lease_valid: bool = True
    secondary_plan_source_matches_target: bool | None = None
    secondary_readiness_sustained: bool | None = None
    secondary_plan_epoch_monotonic: bool | None = None
    secondary_plan_executable: bool = False
    secondary_plan_reject_reason: str | None = None
    recovery_dual_track_audit: dict[str, object] = field(default_factory=dict)
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
        secondary_assist = self._select_secondary_node(
            secondary_nodes,
            coverage_cell,
            communication_summaries=communication_summaries,
            current_time_s=current_time_s,
            terminal_association=terminal_association,
            require_takeover_capable=False,
        )
        secondary_takeover = self._select_secondary_node(
            secondary_nodes,
            coverage_cell,
            communication_summaries=communication_summaries,
            current_time_s=current_time_s,
            terminal_association=terminal_association,
            require_takeover_capable=True,
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
                    secondary_takeover,
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
                if secondary_assist is not None:
                    return self._apply_hysteresis(
                        ActiveDegradationDecision(
                            mode=DegradationMode.ACTIVE_DEGRADATION,
                            action=DegradationAction.REQUEST_SECONDARY_ASSIST,
                            reason="terminal_persistent_reacquire_request_secondary_cue",
                            target_node_id=secondary_assist.node_id,
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
                    secondary_takeover,
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
                secondary_assist is None and self._risk_requires_active_arbitration(risk_factors)
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
                        if secondary_assist is not None
                        else DegradationMode.NONE
                    ),
                    action=(
                        DegradationAction.REQUEST_SECONDARY_ASSIST
                        if secondary_assist is not None
                        else DegradationAction.CONTINUE_CENTER
                    ),
                    reason=(
                        "risk_rising_request_secondary_assist"
                        if secondary_assist is not None
                        else "soft_risk_terminal_consistent_observe_more"
                    ),
                    target_node_id=(
                        secondary_assist.node_id if secondary_assist is not None else None
                    ),
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

        if secondary_assist is not None:
            return self._apply_hysteresis(
                ActiveDegradationDecision(
                    mode=DegradationMode.ACTIVE_DEGRADATION,
                    action=DegradationAction.REQUEST_SECONDARY_ASSIST,
                    reason="terminal_inconsistent_single_window",
                    target_node_id=secondary_assist.node_id,
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
        if association.truth_metrics_available and association.id_switch_count > 0:
            factors.append("d2_id_switch_observed")
        if association.duplicate_track_count > 0:
            factors.append("d2_duplicate_track_observed")
        if (
            association.continuity_available
            and association.track_continuity < cfg.track_continuity_low
        ):
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
        terminal_association: TerminalAssociationSummary | None = None,
        require_takeover_capable: bool = True,
    ) -> ResourceSummary | None:
        candidates = [
            resource
            for resource in resources
            if is_secondary_node_resource(resource)
            and not resource.operator_hold
            and resource.availability_band != AvailabilityBand.NONE
            and ActiveDegradationArbiter._secondary_covers_cell(resource, coverage_cell)
            and ActiveDegradationArbiter._secondary_heartbeat_is_usable(
                resource,
                current_time_s,
            )
            and ActiveDegradationArbiter._secondary_lease_is_usable(
                resource,
                current_time_s,
            )
            and ActiveDegradationArbiter._secondary_cue_is_usable(resource)
            and ActiveDegradationArbiter._secondary_gimbal_is_usable(resource)
            and ActiveDegradationArbiter._secondary_link_is_usable(
                resource,
                communication_summaries,
                current_time_s,
            )
            and (
                not require_takeover_capable
                or ActiveDegradationArbiter._secondary_capability_metadata(
                    resource,
                    coverage_cell,
                    communication_summaries=communication_summaries,
                    current_time_s=current_time_s,
                    terminal_association=terminal_association,
                )["takeover_capable"]
            )
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda resource: (
                int(resource.takeover_priority),
                -float(
                    ActiveDegradationArbiter._secondary_capability_metadata(
                        resource,
                        coverage_cell,
                        communication_summaries=communication_summaries,
                        current_time_s=current_time_s,
                        terminal_association=terminal_association,
                    )["score"]
                ),
                ActiveDegradationArbiter._secondary_capability_rank(resource),
                -int(resource.lease_epoch),
                resource.node_id,
            )
        )
        return candidates[0]

    @staticmethod
    def _secondary_covers_cell(resource: ResourceSummary, coverage_cell: str) -> bool:
        if resource.coverage_cell in {None, "", coverage_cell}:
            return True
        return (
            resource.secondary_coverage_ratio is not None
            and resource.secondary_coverage_ratio > 0.0
        )

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
    def _secondary_lease_is_usable(
        resource: ResourceSummary,
        current_time_s: float | None,
    ) -> bool:
        if current_time_s is None or resource.lease_expires_at_s is None:
            return True
        return float(current_time_s) <= float(resource.lease_expires_at_s)

    @staticmethod
    def _secondary_cue_is_usable(resource: ResourceSummary) -> bool:
        if resource.cue_freshness_s is None:
            return True
        return 0.0 <= float(resource.cue_freshness_s) <= float(resource.heartbeat_stale_after_s)

    @staticmethod
    def _secondary_gimbal_is_usable(resource: ResourceSummary) -> bool:
        return resource.gimbal_pointing_ok is not False

    @staticmethod
    def _secondary_capability_rank(resource: ResourceSummary) -> int:
        secondary_class = secondary_capability_class(resource)
        if secondary_class == "mobile_high_recon":
            return 0
        if secondary_class == "mobile_secondary_recon":
            return 1
        if secondary_class == "fixed_tethered_secondary":
            return 2
        if secondary_class == "secondary_recon":
            return 3
        if secondary_class == "ground_backup":
            return 4
        return 5

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

    @staticmethod
    def _secondary_capability_metadata(
        resource: ResourceSummary,
        coverage_cell: str,
        *,
        communication_summaries: list[CommunicationSummary] | None,
        current_time_s: float | None,
        terminal_association: TerminalAssociationSummary | None,
    ) -> dict[str, object]:
        coverage_ratio = ActiveDegradationArbiter._secondary_effective_coverage_ratio(
            resource,
            coverage_cell,
            terminal_association,
        )
        network_full_view_rate = ActiveDegradationArbiter._secondary_network_full_view_rate(
            resource,
            terminal_association,
        )
        stable_registration_count = (
            ActiveDegradationArbiter._secondary_stable_registration_count(
                resource,
                terminal_association,
            )
        )
        not_registered_count = ActiveDegradationArbiter._secondary_not_registered_count(
            resource,
            terminal_association,
        )
        registration_evidence_source = (
            ActiveDegradationArbiter._secondary_registration_evidence_source(
                resource,
                terminal_association,
            )
        )
        heartbeat_ok = ActiveDegradationArbiter._secondary_heartbeat_is_usable(
            resource,
            current_time_s,
        )
        lease_ok = ActiveDegradationArbiter._secondary_lease_is_usable(
            resource,
            current_time_s,
        )
        cue_ok = ActiveDegradationArbiter._secondary_cue_is_usable(resource)
        gimbal_ok = ActiveDegradationArbiter._secondary_gimbal_is_usable(resource)
        link_ok = ActiveDegradationArbiter._secondary_link_is_usable(
            resource,
            communication_summaries,
            current_time_s,
        )
        available = (
            not resource.operator_hold
            and resource.availability_band != AvailabilityBand.NONE
            and ActiveDegradationArbiter._secondary_covers_cell(resource, coverage_cell)
            and lease_ok
        )
        freshness_ok = heartbeat_ok and cue_ok and link_ok
        visible = available and coverage_ratio > 0.0 and gimbal_ok and freshness_ok
        registration_known = False
        registered = False
        reasons: list[str] = []
        if not available:
            reasons.append("secondary_unavailable")
        if coverage_ratio <= 0.0:
            reasons.append("coverage_unavailable")
        if not heartbeat_ok:
            reasons.append("heartbeat_stale")
        if not lease_ok:
            reasons.append("lease_expired")
        if not cue_ok:
            reasons.append("cue_stale")
        if not gimbal_ok:
            reasons.append("gimbal_not_pointing")
        if not link_ok:
            reasons.append("link_stale")

        if terminal_association is not None:
            if terminal_association.secondary_detect_available_but_not_registered:
                registration_known = True
                registered = False
                reasons.append("secondary_detect_available_but_not_registered")
            elif stable_registration_count is not None:
                registration_known = True
                registered = stable_registration_count > 0
            elif terminal_association.cross_view_association_count is not None:
                registration_known = True
                registered = terminal_association.cross_view_association_count > 0
            elif terminal_association.cross_view_support_count > 0:
                registration_known = True
                registered = True

        if not registration_known and stable_registration_count is not None:
            registration_known = True
            registered = stable_registration_count > 0

        if not registration_known and resource.cross_view_support_count is not None:
            registration_known = True
            registered = resource.cross_view_support_count > 0

        if (
            not registration_known
            and not_registered_count is not None
            and not_registered_count > 0
        ):
            registration_known = True
            registered = False

        if stable_registration_count is not None:
            reasons.append("stable_cross_view_registration_count_present")
        if not_registered_count is not None and not_registered_count > 0:
            reasons.append("not_registered_count_positive")

        if registration_known and not registered:
            reasons.append("stable_registration_missing")
        elif registration_known and registered:
            reasons.append("stable_registration_available")
        else:
            reasons.append("registration_unknown")

        coverage_score = _clamp01(coverage_ratio)
        network_score = (
            _clamp01(network_full_view_rate)
            if network_full_view_rate is not None
            else coverage_score
        )
        heartbeat_score = 1.0 if heartbeat_ok else 0.0
        link_score = 1.0 if link_ok else 0.0
        cue_score = 1.0 if cue_ok else 0.0
        freshness_score = (heartbeat_score + link_score + cue_score) / 3.0
        registration_score = 1.0 if registered else 0.0
        gimbal_score = 1.0 if gimbal_ok else 0.0
        score = _clamp01(
            0.25 * coverage_score
            + 0.15 * network_score
            + 0.25 * registration_score
            + 0.15 * freshness_score
            + 0.10 * gimbal_score
            + 0.05 * cue_score
            + 0.03 * link_score
            + 0.02 * heartbeat_score
        )
        readiness_class = ActiveDegradationArbiter._secondary_readiness_class(
            visible=visible,
            registered=registered,
            coverage_ratio=coverage_ratio,
            network_full_view_rate=network_full_view_rate,
            score=score,
        )
        takeover_capable = readiness_class == TAKEOVER_READY_SECONDARY_CAPABILITY_CLASS
        if visible:
            reasons.append("secondary_visible")
        if (
            network_full_view_rate is not None
            and network_full_view_rate < _MIN_TAKEOVER_NETWORK_FULL_VIEW_RATE
        ):
            reasons.append("network_full_view_rate_low")
        if takeover_capable:
            reasons.append("takeover_capable")
        inputs = {
            "coverage_ratio": coverage_ratio,
            "network_full_view_rate": network_full_view_rate,
            "stable_cross_view_registration_count": stable_registration_count,
            "not_registered_count": not_registered_count,
            "registration_evidence_source": registration_evidence_source,
            "stable_registration_evidence_present": stable_registration_count is not None,
            "not_registered_evidence_present": not_registered_count is not None,
            "gimbal_ok": gimbal_ok,
            "cue_freshness_s": resource.cue_freshness_s,
            "cue_fresh": cue_ok,
            "link_fresh": link_ok,
            "heartbeat_fresh": heartbeat_ok,
            "heartbeat_timestamp_s": resource.heartbeat_timestamp_s,
            "heartbeat_stale_after_s": resource.heartbeat_stale_after_s,
            "registration_known": registration_known,
            "registered": registered,
        }
        return {
            "visible": visible,
            "registered": registered,
            "takeover_capable": takeover_capable,
            "score": score,
            "readiness_class": readiness_class,
            "inputs": inputs,
            "network_full_view_rate": network_full_view_rate,
            "stable_cross_view_registration_count": stable_registration_count,
            "not_registered_count": not_registered_count,
            "registration_evidence_source": registration_evidence_source,
            "stable_registration_evidence_present": stable_registration_count is not None,
            "not_registered_evidence_present": not_registered_count is not None,
            "reasons": tuple(dict.fromkeys(reason for reason in reasons if reason)),
        }

    @staticmethod
    def _secondary_readiness_class(
        *,
        visible: bool,
        registered: bool,
        coverage_ratio: float,
        network_full_view_rate: float | None,
        score: float,
    ) -> str:
        if not visible:
            return NOT_READY_SECONDARY_CAPABILITY_CLASS
        if not registered:
            return VISIBLE_ONLY_SECONDARY_CAPABILITY_CLASS
        network_ready = (
            network_full_view_rate is None
            or network_full_view_rate >= _MIN_TAKEOVER_NETWORK_FULL_VIEW_RATE
        )
        if (
            coverage_ratio < _MIN_TAKEOVER_COVERAGE_RATIO
            or not network_ready
            or score < _MIN_TAKEOVER_CAPABILITY_SCORE
        ):
            return REGISTRATION_USABLE_SECONDARY_CAPABILITY_CLASS
        return TAKEOVER_READY_SECONDARY_CAPABILITY_CLASS

    @staticmethod
    def _secondary_network_full_view_rate(
        resource: ResourceSummary,
        terminal_association: TerminalAssociationSummary | None,
    ) -> float | None:
        values = [
            terminal_association.secondary_network_joint_full_view_frame_rate
            if terminal_association is not None
            else None,
            resource.secondary_network_full_view_rate,
        ]
        for value in values:
            if value is not None:
                return _clamp01(float(value))
        return None

    @staticmethod
    def _secondary_stable_registration_count(
        resource: ResourceSummary,
        terminal_association: TerminalAssociationSummary | None,
    ) -> int | None:
        values = [
            terminal_association.stable_cross_view_registration_count
            if terminal_association is not None
            else None,
            resource.stable_cross_view_registration_count,
        ]
        for value in values:
            if value is not None:
                return max(0, int(value))
        return None

    @staticmethod
    def _secondary_not_registered_count(
        resource: ResourceSummary,
        terminal_association: TerminalAssociationSummary | None,
    ) -> int | None:
        values = [
            terminal_association.not_registered_count
            if terminal_association is not None
            else None,
            resource.not_registered_count,
        ]
        for value in values:
            if value is not None:
                return max(0, int(value))
        return None

    @staticmethod
    def _secondary_registration_evidence_source(
        resource: ResourceSummary,
        terminal_association: TerminalAssociationSummary | None,
    ) -> str:
        if terminal_association is not None:
            if terminal_association.secondary_detect_available_but_not_registered:
                return "d5_detect_not_registered"
            if terminal_association.stable_cross_view_registration_count is not None:
                return "d5_stable_cross_view_registration_count"
            if terminal_association.not_registered_count is not None:
                return "d5_not_registered_count"
            if terminal_association.cross_view_association_count is not None:
                return "d5_cross_view_association_count_compatibility"
            if terminal_association.cross_view_support_count > 0:
                return "d5_cross_view_support_count_compatibility"
        if resource.stable_cross_view_registration_count is not None:
            return "resource_stable_cross_view_registration_count"
        if resource.not_registered_count is not None:
            return "resource_not_registered_count"
        if resource.cross_view_support_count is not None:
            return "resource_cross_view_support_count_compatibility"
        return "unknown"

    @staticmethod
    def _secondary_effective_coverage_ratio(
        resource: ResourceSummary,
        coverage_cell: str,
        terminal_association: TerminalAssociationSummary | None,
    ) -> float:
        values = [
            resource.secondary_coverage_ratio,
            terminal_association.secondary_coverage_ratio
            if terminal_association is not None
            else None,
            terminal_association.secondary_network_mean_coverage_ratio
            if terminal_association is not None
            else None,
            terminal_association.secondary_network_joint_full_view_frame_rate
            if terminal_association is not None
            else None,
            resource.secondary_network_full_view_rate,
            terminal_association.secondary_single_camera_full_view_frame_rate
            if terminal_association is not None
            else None,
        ]
        for value in values:
            if value is not None:
                return _clamp01(float(value))
        return 1.0 if ActiveDegradationArbiter._secondary_covers_cell(resource, coverage_cell) else 0.0


def build_d7_secondary_handoff(
    decision: ActiveDegradationDecision,
    *,
    current_plan_id: str | None = None,
    current_plan_version: int | None = None,
    new_plan_id: str | None = None,
    new_plan_version: int | None = None,
    secondary_plan_active: bool = False,
    secondary_capability_class: str | None = None,
    secondary_readiness_sustained: bool | None = None,
    secondary_plan_lease_expires_at_s: float | None = None,
    current_time_s: float | None = None,
    terminal_consistent_after_plan: bool = False,
) -> D7SecondaryHandoff:
    """Build the two-stage D4/D7 handoff for secondary active degradation.

    Stage 1 is the frame where D4 emits ``degrade_to_secondary``. It means the
    secondary node has been selected but reassignment has not completed, so D7
    must not enter visual PNG on that frame. Stage 2 begins only after the
    secondary plan is active, the secondary capability is takeover-ready, and
    the handoff carries the new plan id/version to D7.
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

    strictness = _secondary_plan_strictness(
        current_plan_id=current_plan_id,
        current_plan_version=current_plan_version,
        current_plan_owner="center",
        secondary_plan_id=new_plan_id,
        secondary_plan_version=new_plan_version,
        secondary_plan_active=secondary_plan_active,
        expected_secondary_source_node_id=None,
        secondary_plan_source_node_id=None,
        secondary_plan_lease_epoch=None,
        required_secondary_plan_lease_epoch=None,
        secondary_plan_lease_expires_at_s=secondary_plan_lease_expires_at_s,
        secondary_readiness_sustained=secondary_readiness_sustained,
        current_time_s=current_time_s,
    )
    capability_ready = (
        str(secondary_capability_class) == TAKEOVER_READY_SECONDARY_CAPABILITY_CLASS
        and secondary_readiness_sustained is not False
    )
    plan_core_ready = (
        secondary_plan_active
        and new_plan_id is not None
        and new_plan_version is not None
        and strictness["executable"]
    )
    plan_ready = plan_core_ready and capability_ready
    if not plan_ready:
        reject_reason = strictness["reject_reason"]
        if reject_reason is None and plan_core_ready and not capability_ready:
            reject_reason = (
                "secondary_readiness_not_sustained"
                if secondary_readiness_sustained is False
                else "secondary_capability_not_takeover_ready"
            )
        return D7SecondaryHandoff(
            phase=1,
            d4_action=decision.action,
            d7_action=None,
            target_node_id=decision.target_node_id,
            reassignment_complete=False,
            visual_png_allowed=False,
            current_plan_id=current_plan_id,
            current_plan_version=current_plan_version,
            reason=reject_reason or "secondary_reassignment_pending",
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
    secondary_plan_lease_epoch: int | None = None,
    required_secondary_plan_lease_epoch: int | None = None,
    secondary_plan_lease_expires_at_s: float | None = None,
    secondary_readiness_sustained: bool | None = None,
    decision_timestamp: float | None = None,
) -> SecondaryTakeoverPlanMetadata:
    """Build the D4 metadata contract for secondary takeover plan state."""

    source_node_id = secondary_plan_source_node_id or decision.target_node_id
    readiness_gate = (
        secondary_readiness_sustained
        if decision.action == DegradationAction.DEGRADE_TO_SECONDARY or secondary_plan_active
        else None
    )
    strictness = _secondary_plan_strictness(
        current_plan_id=current_plan_id,
        current_plan_version=current_plan_version,
        current_plan_owner=current_plan_owner,
        secondary_plan_id=secondary_plan_id,
        secondary_plan_version=secondary_plan_version,
        secondary_plan_active=secondary_plan_active,
        expected_secondary_source_node_id=decision.target_node_id,
        secondary_plan_source_node_id=source_node_id,
        secondary_plan_lease_epoch=secondary_plan_lease_epoch,
        required_secondary_plan_lease_epoch=required_secondary_plan_lease_epoch,
        secondary_plan_lease_expires_at_s=secondary_plan_lease_expires_at_s,
        secondary_readiness_sustained=readiness_gate,
        current_time_s=decision_timestamp,
    )
    recovery_audit = _recovery_dual_track_audit(
        current_plan_id=current_plan_id,
        current_plan_version=current_plan_version,
        current_plan_owner=current_plan_owner,
        secondary_plan_id=secondary_plan_id,
        secondary_plan_version=secondary_plan_version,
        secondary_plan_source_node_id=source_node_id,
        secondary_plan_lease_epoch=secondary_plan_lease_epoch,
        required_secondary_plan_lease_epoch=required_secondary_plan_lease_epoch,
        secondary_plan_lease_expires_at_s=secondary_plan_lease_expires_at_s,
        secondary_plan_source_matches_target=strictness["source_matches_target"],
        secondary_readiness_sustained=secondary_readiness_sustained,
        secondary_plan_executable=bool(strictness["executable"]),
    )
    if decision.action != DegradationAction.DEGRADE_TO_SECONDARY:
        return SecondaryTakeoverPlanMetadata(
            state=SecondaryTakeoverPlanState.NOT_APPLICABLE,
            active_plan_owner=_active_owner_for_non_secondary(decision, current_plan_owner),
            current_plan_id=current_plan_id,
            current_plan_version=current_plan_version,
            secondary_plan_source_node_id=source_node_id,
            secondary_plan_id=secondary_plan_id,
            secondary_plan_version=secondary_plan_version,
            secondary_plan_lease_epoch=secondary_plan_lease_epoch,
            required_secondary_plan_lease_epoch=required_secondary_plan_lease_epoch,
            secondary_plan_lease_expires_at_s=secondary_plan_lease_expires_at_s,
            secondary_plan_lease_valid=bool(strictness["lease_valid"]),
            secondary_plan_source_matches_target=strictness["source_matches_target"],
            secondary_readiness_sustained=secondary_readiness_sustained,
            secondary_plan_epoch_monotonic=strictness["epoch_monotonic"],
            secondary_plan_executable=False,
            secondary_plan_reject_reason=strictness["reject_reason"],
            recovery_dual_track_audit=recovery_audit,
            reason=decision.reason,
        )

    plan_ready = (
        secondary_plan_active
        and secondary_plan_id is not None
        and secondary_plan_version is not None
        and strictness["executable"]
    )
    if not plan_ready:
        reject_reason = strictness["reject_reason"] or "secondary_reassignment_pending"
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
            secondary_plan_lease_epoch=secondary_plan_lease_epoch,
            required_secondary_plan_lease_epoch=required_secondary_plan_lease_epoch,
            secondary_plan_lease_expires_at_s=secondary_plan_lease_expires_at_s,
            secondary_plan_lease_valid=bool(strictness["lease_valid"]),
            secondary_plan_source_matches_target=strictness["source_matches_target"],
            secondary_readiness_sustained=secondary_readiness_sustained,
            secondary_plan_epoch_monotonic=strictness["epoch_monotonic"],
            secondary_plan_executable=False,
            secondary_plan_reject_reason=reject_reason,
            recovery_dual_track_audit=recovery_audit,
            reason=reject_reason,
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
        secondary_plan_lease_epoch=secondary_plan_lease_epoch,
        required_secondary_plan_lease_epoch=required_secondary_plan_lease_epoch,
        secondary_plan_lease_expires_at_s=secondary_plan_lease_expires_at_s,
        secondary_plan_lease_valid=True,
        secondary_plan_source_matches_target=True,
        secondary_readiness_sustained=secondary_readiness_sustained,
        secondary_plan_epoch_monotonic=True,
        secondary_plan_executable=True,
        recovery_dual_track_audit=recovery_audit,
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


def _secondary_plan_strictness(
    *,
    current_plan_id: str | None,
    current_plan_version: int | None,
    current_plan_owner: str,
    secondary_plan_id: str | None,
    secondary_plan_version: int | None,
    secondary_plan_active: bool,
    expected_secondary_source_node_id: str | None,
    secondary_plan_source_node_id: str | None,
    secondary_plan_lease_epoch: int | None,
    required_secondary_plan_lease_epoch: int | None,
    secondary_plan_lease_expires_at_s: float | None,
    secondary_readiness_sustained: bool | None,
    current_time_s: float | None,
) -> dict[str, object]:
    lease_valid = True
    if (
        secondary_plan_lease_expires_at_s is not None
        and current_time_s is not None
        and float(current_time_s) > float(secondary_plan_lease_expires_at_s)
    ):
        lease_valid = False

    source_matches_target: bool | None = None
    if expected_secondary_source_node_id is not None:
        source_matches_target = (
            secondary_plan_source_node_id is not None
            and str(secondary_plan_source_node_id) == str(expected_secondary_source_node_id)
        )
    lease_epoch_valid: bool | None = None
    if required_secondary_plan_lease_epoch is not None:
        lease_epoch_valid = (
            secondary_plan_lease_epoch is not None
            and int(secondary_plan_lease_epoch) >= int(required_secondary_plan_lease_epoch)
        )

    already_active_secondary_plan = _is_same_active_secondary_plan(
        current_plan_id=current_plan_id,
        current_plan_version=current_plan_version,
        current_plan_owner=current_plan_owner,
        secondary_plan_id=secondary_plan_id,
        secondary_plan_version=secondary_plan_version,
        secondary_plan_active=secondary_plan_active,
    )
    epoch_monotonic: bool | None = None
    if already_active_secondary_plan:
        epoch_monotonic = True
    elif secondary_plan_version is not None and current_plan_version is not None:
        epoch_monotonic = int(secondary_plan_version) > int(current_plan_version)
    elif secondary_plan_version is not None:
        epoch_monotonic = True

    reject_reason = None
    if secondary_readiness_sustained is False:
        reject_reason = "secondary_readiness_not_sustained"
    elif source_matches_target is False:
        reject_reason = "secondary_plan_source_mismatch"
    elif lease_epoch_valid is False:
        reject_reason = "secondary_plan_lease_epoch_stale"
    elif not lease_valid:
        reject_reason = "secondary_plan_lease_expired"
    elif secondary_plan_active and not bool(epoch_monotonic):
        reject_reason = "secondary_plan_epoch_not_monotonic"

    executable = (
        secondary_plan_active
        and secondary_plan_version is not None
        and lease_valid
        and source_matches_target is not False
        and lease_epoch_valid is not False
        and secondary_readiness_sustained is not False
        and epoch_monotonic is not False
    )
    return {
        "lease_valid": lease_valid,
        "lease_epoch_valid": lease_epoch_valid,
        "source_matches_target": source_matches_target,
        "epoch_monotonic": epoch_monotonic,
        "executable": executable,
        "reject_reason": reject_reason,
    }


def _is_same_active_secondary_plan(
    *,
    current_plan_id: str | None,
    current_plan_version: int | None,
    current_plan_owner: str,
    secondary_plan_id: str | None,
    secondary_plan_version: int | None,
    secondary_plan_active: bool,
) -> bool:
    owner = str(current_plan_owner or "").strip().lower()
    return (
        secondary_plan_active
        and owner in {"secondary", "secondary_node"}
        and current_plan_id is not None
        and secondary_plan_id is not None
        and str(current_plan_id) == str(secondary_plan_id)
        and current_plan_version is not None
        and secondary_plan_version is not None
        and int(current_plan_version) == int(secondary_plan_version)
    )


def _recovery_dual_track_audit(
    *,
    current_plan_id: str | None,
    current_plan_version: int | None,
    current_plan_owner: str,
    secondary_plan_id: str | None,
    secondary_plan_version: int | None,
    secondary_plan_source_node_id: str | None,
    secondary_plan_lease_epoch: int | None,
    required_secondary_plan_lease_epoch: int | None,
    secondary_plan_lease_expires_at_s: float | None,
    secondary_plan_source_matches_target: bool | None,
    secondary_readiness_sustained: bool | None,
    secondary_plan_executable: bool,
) -> dict[str, object]:
    return {
        "center_track_plan_id": current_plan_id,
        "center_track_plan_version": current_plan_version,
        "center_track_owner": current_plan_owner,
        "secondary_track_plan_id": secondary_plan_id,
        "secondary_track_plan_version": secondary_plan_version,
        "secondary_plan_source_node_id": secondary_plan_source_node_id,
        "secondary_plan_lease_epoch": secondary_plan_lease_epoch,
        "required_secondary_plan_lease_epoch": required_secondary_plan_lease_epoch,
        "secondary_plan_lease_expires_at_s": secondary_plan_lease_expires_at_s,
        "secondary_plan_source_matches_target": secondary_plan_source_matches_target,
        "secondary_readiness_sustained": secondary_readiness_sustained,
        "secondary_plan_executable": secondary_plan_executable,
    }


def summarize_secondary_lifecycle(
    resources: list[ResourceSummary],
    coverage_cell: str,
    communication_summaries: list[CommunicationSummary] | None = None,
    current_time_s: float | None = None,
    terminal_association: TerminalAssociationSummary | None = None,
) -> tuple[SecondaryNodeLifecycleSummary, ...]:
    summaries: list[SecondaryNodeLifecycleSummary] = []
    for resource in resources:
        if not is_secondary_node_resource(resource):
            continue
        heartbeat_age = None
        if current_time_s is not None and resource.heartbeat_timestamp_s is not None:
            heartbeat_age = max(0.0, float(current_time_s) - float(resource.heartbeat_timestamp_s))
        video_freshness = _video_cue_freshness_s(
            resource,
            communication_summaries,
            current_time_s,
        )
        cue_freshness = (
            resource.cue_freshness_s
            if resource.cue_freshness_s is not None
            else video_freshness
        )
        link_stale = None
        if communication_summaries is not None:
            link_stale = not ActiveDegradationArbiter._secondary_link_is_usable(
                resource,
                communication_summaries,
                current_time_s,
            )
        coverage_matches_requested_cell = ActiveDegradationArbiter._secondary_covers_cell(
            resource,
            coverage_cell,
        )
        heartbeat_stale = None
        if current_time_s is not None and resource.heartbeat_timestamp_s is not None:
            heartbeat_stale = not ActiveDegradationArbiter._secondary_heartbeat_is_usable(
                resource,
                current_time_s,
            )
        lease_expired = None
        if current_time_s is not None and resource.lease_expires_at_s is not None:
            lease_expired = not ActiveDegradationArbiter._secondary_lease_is_usable(
                resource,
                current_time_s,
            )
        cue_stale = None
        if resource.cue_freshness_s is not None:
            cue_stale = not ActiveDegradationArbiter._secondary_cue_is_usable(resource)
        secondary_available = (
            not resource.operator_hold
            and resource.availability_band != AvailabilityBand.NONE
            and coverage_matches_requested_cell
            and ActiveDegradationArbiter._secondary_heartbeat_is_usable(resource, current_time_s)
            and ActiveDegradationArbiter._secondary_lease_is_usable(resource, current_time_s)
            and ActiveDegradationArbiter._secondary_cue_is_usable(resource)
            and ActiveDegradationArbiter._secondary_gimbal_is_usable(resource)
            and not bool(link_stale)
        )
        capability = ActiveDegradationArbiter._secondary_capability_metadata(
            resource,
            coverage_cell,
            communication_summaries=communication_summaries,
            current_time_s=current_time_s,
            terminal_association=terminal_association,
        )
        secondary_class = secondary_capability_class(resource)
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
                lease_expires_at_s=resource.lease_expires_at_s,
                lease_expired=lease_expired,
                coverage_matches_requested_cell=coverage_matches_requested_cell,
                heartbeat_stale=heartbeat_stale,
                cue_stale=cue_stale,
                link_fresh=None if link_stale is None else not link_stale,
                heartbeat=resource.heartbeat_timestamp_s,
                video_cue_freshness=video_freshness,
                capability_class=resource.capability_class,
                node_role=node_role_value(resource.node_role),
                secondary_capability_class=secondary_class,
                cue_freshness_s=cue_freshness,
                gimbal_pointing_ok=resource.gimbal_pointing_ok,
                secondary_coverage_ratio=resource.secondary_coverage_ratio,
                cross_view_support_count=resource.cross_view_support_count,
                is_mobile_high_recon=is_mobile_high_recon_resource(resource),
                is_fixed_tethered_secondary=is_fixed_tethered_secondary_resource(resource),
                secondary_visible=bool(capability["visible"]),
                secondary_registered=bool(capability["registered"]),
                secondary_takeover_capable=bool(capability["takeover_capable"]),
                secondary_capability_score=float(capability["score"]),
                secondary_capability_reasons=tuple(capability["reasons"]),
                secondary_readiness_class=str(capability["readiness_class"]),
                secondary_capability_inputs=dict(capability["inputs"]),
                secondary_network_full_view_rate=(
                    capability["network_full_view_rate"]
                    if capability["network_full_view_rate"] is not None
                    else resource.secondary_network_full_view_rate
                ),
                stable_cross_view_registration_count=(
                    capability["stable_cross_view_registration_count"]
                ),
                not_registered_count=capability["not_registered_count"],
                registration_evidence_source=str(
                    capability["registration_evidence_source"]
                ),
                stable_registration_evidence_present=bool(
                    capability["stable_registration_evidence_present"]
                ),
                not_registered_evidence_present=bool(
                    capability["not_registered_evidence_present"]
                ),
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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
