from __future__ import annotations

from d4_distributed_fallback.active_degradation import (
    ActiveDegradationArbiter,
    ActiveDegradationConfig,
    AssignmentValiditySummary,
    AssociationRiskSummary,
    DegradationAction,
    DegradationMode,
    TerminalAssociationSummary,
    TerminalDecisionState,
    TrackUncertaintySummary,
    summarize_secondary_lifecycle,
)
from d4_distributed_fallback.models import (
    AvailabilityBand,
    C2Health,
    CommBand,
    CommunicationSummary,
    LinkType,
    NodeRole,
    PayloadKind,
    ResourceSummary,
)


def _track(position_sigma_m: float = 8.0) -> TrackUncertaintySummary:
    return TrackUncertaintySummary(
        track_id="track-1",
        coverage_cell="cell-north",
        position_sigma_m=position_sigma_m,
        covariance_trace=position_sigma_m**2,
    )


def _association(ambiguity_score: float = 0.05) -> AssociationRiskSummary:
    return AssociationRiskSummary(
        track_id="track-1",
        ambiguity_score=ambiguity_score,
        id_switch_count=0,
        duplicate_track_count=0,
        track_continuity=0.95,
    )


def _assignment(is_current: bool = True, cost_margin: float = 0.8) -> AssignmentValiditySummary:
    return AssignmentValiditySummary(
        global_track_id="track-1",
        assigned_resource_id="int-1",
        plan_version=3,
        is_current=is_current,
        plan_age_s=1.0,
        cost_margin=cost_margin,
    )


def _terminal(
    decision_state: TerminalDecisionState = TerminalDecisionState.LOCKED,
    observed_global_track_id: str | None = "track-1",
    consecutive_non_locked_frames: int = 0,
    consecutive_mismatch_frames: int = 0,
) -> TerminalAssociationSummary:
    return TerminalAssociationSummary(
        resource_id="int-1",
        assigned_global_track_id="track-1",
        observed_global_track_id=observed_global_track_id,
        decision_state=decision_state,
        association_confidence=0.9,
        ambiguity_score=0.05,
        coverage_cell="cell-north",
        consecutive_non_locked_frames=consecutive_non_locked_frames,
        consecutive_mismatch_frames=consecutive_mismatch_frames,
    )


def _secondary(available: bool = True, coverage_cell: str = "cell-north") -> ResourceSummary:
    return ResourceSummary(
        node_id="sec-1",
        capability_class="tethered_recon",
        availability_band=AvailabilityBand.HIGH if available else AvailabilityBand.NONE,
        comm_band=CommBand.GOOD,
        takeover_priority=20,
        lease_epoch=4,
        epoch=1,
        node_role=NodeRole.SECONDARY_RECON,
        coordinator_only=True,
        coverage_cell=coverage_cell,
        heartbeat_timestamp_s=10.0,
        heartbeat_stale_after_s=2.0,
    )


def _secondary_link(
    received_timestamp: float = 10.0,
    stale_after_s: float = 1.0,
    payload_kind: PayloadKind = PayloadKind.VIDEO_METADATA,
) -> CommunicationSummary:
    return CommunicationSummary(
        source_node_id="sec-1",
        target_node_id="int-1",
        relay_node_id=None,
        link_type=LinkType.VIDEO_CUE,
        sent_timestamp=received_timestamp - 0.1,
        received_timestamp=received_timestamp,
        payload_kind=payload_kind,
        stale_after_s=stale_after_s,
        sequence_id="sec-1:10",
    )


def test_low_risk_consistent_terminal_continues_center_plan() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert decision.mode == DegradationMode.NONE
    assert decision.action == DegradationAction.CONTINUE_CENTER
    assert decision.terminal_consistent
    assert decision.risk_factors == ()


def test_risk_rising_but_terminal_consistent_requests_secondary_assist() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(position_sigma_m=30.0),
        association_risk=_association(ambiguity_score=0.4),
        assignment_validity=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert decision.target_node_id == "sec-1"
    assert decision.terminal_consistent


def test_assignment_risk_with_consistent_terminal_requests_center_replan() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(is_current=False, cost_margin=0.02),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert "d3_assignment_not_current" in decision.risk_factors


def test_persistent_terminal_disagreement_degrades_to_secondary_if_covered() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-2",
            consecutive_non_locked_frames=3,
            consecutive_mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert decision.target_node_id == "sec-1"
    assert not decision.terminal_consistent


def test_persistent_terminal_disagreement_without_secondary_degrades_to_distributed() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(
            decision_state=TerminalDecisionState.AMBIGUOUS,
            observed_global_track_id=None,
            consecutive_non_locked_frames=3,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary(available=False)],
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED


def test_center_failed_uses_passive_failover_to_secondary() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.FAILED,
        secondary_nodes=[_secondary()],
    )

    assert decision.mode == DegradationMode.PASSIVE_FAILOVER
    assert decision.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert decision.target_node_id == "sec-1"


def test_secondary_outside_coverage_is_not_selected() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(
            decision_state=TerminalDecisionState.HOLD,
            consecutive_non_locked_frames=3,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary(coverage_cell="cell-south")],
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert decision.target_node_id is None


def test_active_arbitration_selects_secondary_from_dynamic_resource_list() -> None:
    resources = [
        ResourceSummary(
            "sec-south",
            "tethered_recon",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            takeover_priority=1,
            lease_epoch=9,
            epoch=1,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-south",
            heartbeat_timestamp_s=10.0,
        ),
        ResourceSummary(
            "sec-north-primary",
            "tethered_recon",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            takeover_priority=20,
            lease_epoch=3,
            epoch=1,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-north",
            heartbeat_timestamp_s=10.0,
        ),
        ResourceSummary(
            "sec-north-backup",
            "tethered_recon",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            takeover_priority=30,
            lease_epoch=4,
            epoch=1,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-north",
            heartbeat_timestamp_s=10.0,
        ),
        ResourceSummary(
            "int-1",
            "observe",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            epoch=1,
            node_role=NodeRole.INTERCEPTOR,
            coverage_cell="cell-north",
        ),
    ]

    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-2",
            consecutive_non_locked_frames=3,
            consecutive_mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=resources,
        current_time_s=10.5,
    )
    lifecycle = summarize_secondary_lifecycle(resources, "cell-north", current_time_s=10.5)

    assert decision.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert decision.target_node_id == "sec-north-primary"
    assert len(lifecycle) == 3
    assert {node.node_id for node in lifecycle} == {
        "sec-south",
        "sec-north-primary",
        "sec-north-backup",
    }


def test_terminal_from_different_resource_is_not_consistent() -> None:
    terminal = TerminalAssociationSummary(
        resource_id="int-2",
        assigned_global_track_id="track-1",
        observed_global_track_id="track-1",
        decision_state=TerminalDecisionState.LOCKED,
        association_confidence=0.9,
        ambiguity_score=0.05,
        coverage_cell="cell-north",
    )

    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=terminal,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert not decision.terminal_consistent
    assert "d5_resource_assignment_mismatch" in decision.risk_factors


def test_fresh_secondary_link_supports_active_secondary_assist() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(position_sigma_m=30.0),
        association_risk=_association(ambiguity_score=0.4),
        assignment_validity=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        communication_summaries=[_secondary_link(received_timestamp=10.0, stale_after_s=2.0)],
        current_time_s=10.5,
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert decision.target_node_id == "sec-1"


def test_stale_secondary_link_allows_distributed_only_after_persistent_terminal_mismatch() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-2",
            consecutive_non_locked_frames=3,
            consecutive_mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        communication_summaries=[_secondary_link(received_timestamp=10.0, stale_after_s=1.0)],
        current_time_s=12.0,
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert decision.target_node_id is None


def test_duplicate_terminal_lock_is_not_treated_as_consistent() -> None:
    terminal = TerminalAssociationSummary(
        resource_id="int-1",
        assigned_global_track_id="track-1",
        observed_global_track_id="track-1",
        decision_state=TerminalDecisionState.LOCKED,
        association_confidence=0.9,
        ambiguity_score=0.05,
        coverage_cell="cell-north",
        duplicate_terminal_lock=True,
    )

    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=terminal,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert not decision.terminal_consistent
    assert "d5_duplicate_terminal_lock" in decision.risk_factors


def test_friend_conflict_holds_even_when_center_failed() -> None:
    terminal = TerminalAssociationSummary(
        resource_id="int-1",
        assigned_global_track_id="track-1",
        observed_global_track_id="track-1",
        decision_state=TerminalDecisionState.LOCKED,
        association_confidence=0.9,
        ambiguity_score=0.05,
        coverage_cell="cell-north",
        friend_conflict=True,
    )

    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=terminal,
        c2_health=C2Health.FAILED,
        secondary_nodes=[_secondary()],
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert decision.requires_human_review


def test_stale_secondary_heartbeat_prevents_secondary_takeover() -> None:
    stale_secondary = _secondary()
    stale_secondary = ResourceSummary(
        **{
            **stale_secondary.to_dict(),
            "availability_band": AvailabilityBand.HIGH,
            "comm_band": CommBand.GOOD,
            "node_role": NodeRole.SECONDARY_RECON,
            "heartbeat_timestamp_s": 7.0,
            "heartbeat_stale_after_s": 1.0,
        }
    )

    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-2",
            consecutive_non_locked_frames=3,
            consecutive_mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[stale_secondary],
        communication_summaries=[_secondary_link(received_timestamp=10.0, stale_after_s=2.0)],
        current_time_s=10.0,
    )

    lifecycle = summarize_secondary_lifecycle(
        [stale_secondary],
        "cell-north",
        communication_summaries=[_secondary_link(received_timestamp=10.0, stale_after_s=2.0)],
        current_time_s=10.0,
    )

    assert lifecycle[0].heartbeat_age_s == 3.0
    assert lifecycle[0].heartbeat == 7.0
    assert lifecycle[0].video_cue_freshness_s == 0.0
    assert lifecycle[0].video_cue_freshness == 0.0
    assert lifecycle[0].link_stale is False
    assert lifecycle[0].secondary_available is False
    assert decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED


def test_windowed_risk_threshold_debounces_persistent_mismatch_escalation() -> None:
    arbiter = ActiveDegradationArbiter(
        ActiveDegradationConfig(risk_window_size=2, risk_window_threshold=2)
    )
    kwargs = dict(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-2",
            consecutive_non_locked_frames=3,
            consecutive_mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        current_time_s=10.0,
    )

    first = arbiter.evaluate(**kwargs)
    second = arbiter.evaluate(**{**kwargs, "current_time_s": 10.1})

    assert first.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert first.reason == "terminal_inconsistent_single_window"
    assert second.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert second.reason == "terminal_persistent_disagreement"


def test_min_dwell_and_release_frames_hold_degradation_before_release() -> None:
    arbiter = ActiveDegradationArbiter(
        ActiveDegradationConfig(min_dwell_s=5.0, release_consecutive_consistent_frames=2)
    )
    high_risk = dict(
        track_uncertainty=_track(),
        association_risk=_association(),
        assignment_validity=_assignment(),
        terminal_association=_terminal(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-2",
            consecutive_non_locked_frames=3,
            consecutive_mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        current_time_s=10.0,
    )
    low_risk = {
        **high_risk,
        "terminal_association": _terminal(),
        "current_time_s": 12.0,
    }

    degraded = arbiter.evaluate(**high_risk)
    held = arbiter.evaluate(**low_risk)
    released = arbiter.evaluate(**{**low_risk, "current_time_s": 16.0})

    assert degraded.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert held.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert held.reason == "release_condition_pending"
    assert released.action == DegradationAction.CONTINUE_CENTER
