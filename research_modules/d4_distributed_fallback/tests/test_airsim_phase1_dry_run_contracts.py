from __future__ import annotations

from d4_distributed_fallback.active_degradation import (
    ActiveDegradationArbiter,
    AssignmentValiditySummary,
    AssociationRiskSummary,
    DegradationAction,
    DegradationMode,
    TerminalAssociationSummary,
    TerminalDecisionState,
    TrackUncertaintySummary,
    build_d7_secondary_handoff,
)
from d4_distributed_fallback.coordinator import FailoverCoordinator
from d4_distributed_fallback.models import (
    AvailabilityBand,
    C2Health,
    CommBand,
    CommunicationSummary,
    ConfidenceBand,
    LinkType,
    NodeRole,
    PayloadKind,
    ResourceSummary,
    TrackSummary,
)
from d4_distributed_fallback.network import SimulatedNetwork


def _resource_from_fake_airsim(row: dict[str, object]) -> ResourceSummary:
    return ResourceSummary(
        node_id=str(row["node_id"]),
        capability_class=str(row["capability_class"]),
        availability_band=AvailabilityBand(str(row["availability_band"])),
        comm_band=CommBand(str(row["comm_band"])),
        operator_hold=bool(row.get("operator_hold", False)),
        takeover_priority=int(row.get("takeover_priority", 100)),
        lease_epoch=int(row.get("lease_epoch", 0)),
        epoch=int(row.get("epoch", 1)),
        node_role=NodeRole(str(row.get("node_role", NodeRole.INTERCEPTOR.value))),
        coordinator_only=bool(row.get("coordinator_only", False)),
        coverage_cell=None if row.get("coverage_cell") is None else str(row["coverage_cell"]),
        stable_cross_view_registration_count=(
            None
            if row.get("stable_cross_view_registration_count") is None
            else int(row["stable_cross_view_registration_count"])
        ),
    )


def _fake_phase1_resources(secondary_available: bool = True) -> list[ResourceSummary]:
    rows = [
        {
            "node_id": "sec-north-1",
            "capability_class": "tethered_recon",
            "availability_band": "high" if secondary_available else "none",
            "comm_band": "good",
            "takeover_priority": 20,
            "lease_epoch": 4,
            "node_role": "secondary_recon",
            "coordinator_only": True,
            "coverage_cell": "cell-north",
            "stable_cross_view_registration_count": 2,
            "epoch": 1,
        },
        {
            "node_id": "int-1",
            "capability_class": "observe",
            "availability_band": "high",
            "comm_band": "good",
            "node_role": "cluster_representative",
            "coverage_cell": "cell-north",
            "epoch": 1,
        },
        {
            "node_id": "int-2",
            "capability_class": "observe",
            "availability_band": "high",
            "comm_band": "limited",
            "node_role": "interceptor",
            "coverage_cell": "cell-north",
            "epoch": 1,
        },
    ]
    return [_resource_from_fake_airsim(row) for row in rows]


def _fake_phase1_task() -> TrackSummary:
    return TrackSummary(
        track_id="track-north-1",
        coarse_cell="cell-north",
        age_s=0.4,
        confidence_band=ConfidenceBand.HIGH,
        source_count=3,
        epoch=1,
    )


def _fake_secondary_video_link(
    received_timestamp: float = 10.0,
    stale_after_s: float = 2.0,
) -> CommunicationSummary:
    return CommunicationSummary(
        source_node_id="sec-north-1",
        target_node_id="int-1",
        relay_node_id=None,
        link_type=LinkType.VIDEO_CUE,
        sent_timestamp=received_timestamp - 0.2,
        received_timestamp=received_timestamp,
        payload_kind=PayloadKind.VIDEO_METADATA,
        stale_after_s=stale_after_s,
        sequence_id="sec-north-1:frame:10",
    )


def _track_uncertainty(position_sigma_m: float = 12.0) -> TrackUncertaintySummary:
    return TrackUncertaintySummary(
        track_id="track-north-1",
        coverage_cell="cell-north",
        position_sigma_m=position_sigma_m,
        covariance_trace=position_sigma_m**2,
        velocity_sigma_mps=1.5,
        measurement_age_s=0.4,
    )


def _association_risk(ambiguity_score: float = 0.05) -> AssociationRiskSummary:
    return AssociationRiskSummary(
        track_id="track-north-1",
        ambiguity_score=ambiguity_score,
        id_switch_count=0,
        duplicate_track_count=0,
        track_continuity=0.95,
    )


def _assignment_validity() -> AssignmentValiditySummary:
    return AssignmentValiditySummary(
        global_track_id="track-north-1",
        assigned_resource_id="int-1",
        plan_version=7,
        is_current=True,
        plan_age_s=0.8,
        cost_margin=0.5,
    )


def _terminal_summary(
    decision_state: TerminalDecisionState = TerminalDecisionState.LOCKED,
    observed_global_track_id: str | None = "track-north-1",
    non_locked_frames: int = 0,
    mismatch_frames: int = 0,
    cross_view_risk_score: float = 0.0,
) -> TerminalAssociationSummary:
    return TerminalAssociationSummary(
        resource_id="int-1",
        assigned_global_track_id="track-north-1",
        observed_global_track_id=observed_global_track_id,
        decision_state=decision_state,
        association_confidence=0.88,
        ambiguity_score=0.08,
        coverage_cell="cell-north",
        consecutive_non_locked_frames=non_locked_frames,
        consecutive_mismatch_frames=mismatch_frames,
        friend_conflict=False,
        cross_view_risk_score=cross_view_risk_score,
        cross_view_support_count=2,
    )


def test_case_001_no_degradation_continue_center() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(position_sigma_m=10.0),
        association_risk=_association_risk(ambiguity_score=0.05),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
        communication_summaries=[_fake_secondary_video_link()],
        current_time_s=10.5,
    )

    assert decision.mode == DegradationMode.NONE
    assert decision.action == DegradationAction.CONTINUE_CENTER
    assert decision.target_node_id is None
    assert decision.terminal_consistent
    assert decision.risk_factors == ()


def test_case_002_requests_center_replan_after_persistent_terminal_mismatch() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(position_sigma_m=55.0),
        association_risk=_association_risk(ambiguity_score=0.75),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-north-2",
            non_locked_frames=3,
            mismatch_frames=2,
            cross_view_risk_score=0.8,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
        communication_summaries=[_fake_secondary_video_link()],
        current_time_s=10.5,
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert decision.target_node_id is None
    assert not decision.terminal_consistent
    assert "d1_track_uncertainty_high" in decision.risk_factors
    assert "d2_association_ambiguity_high" in decision.risk_factors
    assert "d5_cross_view_risk_high" in decision.risk_factors
    assert "d5_terminal_id_mismatch" in decision.risk_factors


def test_blocks_2v2_degrade_to_secondary_frame_does_not_enter_visual_png() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(position_sigma_m=55.0),
        association_risk=_association_risk(ambiguity_score=0.75),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-north-2",
            non_locked_frames=3,
            mismatch_frames=2,
            cross_view_risk_score=0.8,
        ),
        c2_health=C2Health.FAILED,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
        communication_summaries=[_fake_secondary_video_link()],
        current_time_s=10.5,
    )
    handoff = build_d7_secondary_handoff(
        decision,
        current_plan_id="center-2v2-plan-007",
        current_plan_version=7,
    )

    assert decision.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert handoff.phase == 1
    assert handoff.d4_action == DegradationAction.DEGRADE_TO_SECONDARY
    assert handoff.d7_action is None
    assert handoff.reassignment_complete is False
    assert handoff.visual_png_allowed is False
    assert handoff.new_plan_id is None
    assert handoff.new_plan_version is None
    assert handoff.reason == "secondary_reassignment_pending"


def test_blocks_2v2_secondary_plan_activation_hands_new_plan_to_d7() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(position_sigma_m=55.0),
        association_risk=_association_risk(ambiguity_score=0.75),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-north-2",
            non_locked_frames=3,
            mismatch_frames=2,
            cross_view_risk_score=0.8,
        ),
        c2_health=C2Health.FAILED,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
        communication_summaries=[_fake_secondary_video_link()],
        current_time_s=10.5,
    )
    assist_handoff = build_d7_secondary_handoff(
        decision,
        current_plan_id="center-2v2-plan-007",
        current_plan_version=7,
        new_plan_id="secondary-2v2-plan-008",
        new_plan_version=8,
        secondary_plan_active=True,
        secondary_capability_class="takeover_ready",
        terminal_consistent_after_plan=False,
    )
    continue_handoff = build_d7_secondary_handoff(
        decision,
        current_plan_id="center-2v2-plan-007",
        current_plan_version=7,
        new_plan_id="secondary-2v2-plan-009",
        new_plan_version=9,
        secondary_plan_active=True,
        secondary_capability_class="takeover_ready",
        terminal_consistent_after_plan=True,
    )

    assert assist_handoff.phase == 2
    assert assist_handoff.reassignment_complete is True
    assert assist_handoff.visual_png_allowed is True
    assert assist_handoff.d7_action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert assist_handoff.new_plan_id == "secondary-2v2-plan-008"
    assert assist_handoff.new_plan_version == 8
    assert continue_handoff.d7_action == DegradationAction.CONTINUE_CENTER
    assert continue_handoff.new_plan_id == "secondary-2v2-plan-009"
    assert continue_handoff.new_plan_version == 9


def test_d7_handoff_rejects_visible_only_secondary_capability() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(position_sigma_m=55.0),
        association_risk=_association_risk(ambiguity_score=0.75),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-north-2",
            non_locked_frames=3,
            mismatch_frames=2,
            cross_view_risk_score=0.8,
        ),
        c2_health=C2Health.FAILED,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
        communication_summaries=[_fake_secondary_video_link()],
        current_time_s=10.5,
    )

    blocked = build_d7_secondary_handoff(
        decision,
        current_plan_id="center-2v2-plan-007",
        current_plan_version=7,
        new_plan_id="secondary-2v2-plan-008",
        new_plan_version=8,
        secondary_plan_active=True,
        secondary_capability_class="visible_only",
    )
    unknown = build_d7_secondary_handoff(
        decision,
        current_plan_id="center-2v2-plan-007",
        current_plan_version=7,
        new_plan_id="secondary-2v2-plan-008",
        new_plan_version=8,
        secondary_plan_active=True,
    )
    ready = build_d7_secondary_handoff(
        decision,
        current_plan_id="center-2v2-plan-007",
        current_plan_version=7,
        new_plan_id="secondary-2v2-plan-008",
        new_plan_version=8,
        secondary_plan_active=True,
        secondary_capability_class="takeover_ready",
    )
    instantaneous_only = build_d7_secondary_handoff(
        decision,
        current_plan_id="center-2v2-plan-007",
        current_plan_version=7,
        new_plan_id="secondary-2v2-plan-008",
        new_plan_version=8,
        secondary_plan_active=True,
        secondary_capability_class="takeover_ready",
        secondary_readiness_sustained=False,
    )

    assert blocked.phase == 1
    assert blocked.visual_png_allowed is False
    assert blocked.reason == "secondary_capability_not_takeover_ready"
    assert unknown.visual_png_allowed is False
    assert unknown.reason == "secondary_capability_not_takeover_ready"
    assert ready.phase == 2
    assert ready.visual_png_allowed is True
    assert instantaneous_only.phase == 1
    assert instantaneous_only.visual_png_allowed is False
    assert instantaneous_only.reason == "secondary_readiness_not_sustained"


def test_case_003_degrade_to_distributed_when_center_or_secondary_unavailable() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(position_sigma_m=55.0),
        association_risk=_association_risk(ambiguity_score=0.75),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-north-2",
            non_locked_frames=3,
            mismatch_frames=2,
            cross_view_risk_score=0.8,
        ),
        c2_health=C2Health.FAILED,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
        communication_summaries=[_fake_secondary_video_link(received_timestamp=10.0, stale_after_s=1.0)],
        current_time_s=12.0,
    )

    assert decision.mode == DegradationMode.PASSIVE_FAILOVER
    assert decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert decision.target_node_id is None
    assert "d5_cross_view_risk_high" in decision.risk_factors


def test_decision_metrics_contains_main_required_d4_fields() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(position_sigma_m=55.0),
        association_risk=_association_risk(ambiguity_score=0.75),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-north-2",
            non_locked_frames=3,
            mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
    )

    metrics = decision.to_metrics(
        failover_time=1.5,
        secondary_selected_rate=1.0,
        distributed_conflict_count=0,
    )

    assert metrics["d4_action"] == "request_center_replan"
    assert metrics["degradation_mode"] == "active_degradation"
    assert metrics["target_node_id"] is None
    assert metrics["terminal_consistent"] is False
    assert metrics["failover_time"] == 1.5
    assert metrics["secondary_selected_rate"] == 1.0
    assert metrics["distributed_conflict_count"] == 0
    assert "d5_terminal_id_mismatch" in metrics["risk_factors"]


def test_fake_airsim_center_failed_passively_degrades_to_secondary_node() -> None:
    resources = _fake_phase1_resources(secondary_available=True)
    node_ids = [resource.node_id for resource in resources]
    coordinator = FailoverCoordinator("int-1", ["sec-north-1", "int-2"])
    coordinator.update_health(now_s=5.0)

    result = coordinator.plan_degraded(
        tasks=[_fake_phase1_task()],
        resources=resources,
        network=SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1),
        now_s=5.0,
        max_rounds=10,
    )

    assert coordinator.health == C2Health.DEGRADED
    assert coordinator.leader_id == "sec-north-1"
    assert result.converged
    assert result.final_views["coordination_mode"]["state"] == "secondary_node"
    assert result.final_views["coordination_mode"]["leader_role"] == "secondary_recon"
    assert result.final_views["coordination_mode"]["coverage_cell"] == "cell-north"
    assert all(assignment.owner != "sec-north-1" for assignment in result.assignments.values())


def test_fake_airsim_secondary_failed_passively_degrades_to_distributed_cbba() -> None:
    resources = _fake_phase1_resources(secondary_available=False)
    node_ids = [resource.node_id for resource in resources]
    coordinator = FailoverCoordinator("int-1", ["sec-north-1", "int-2"])
    coordinator.update_health(now_s=5.0)

    result = coordinator.plan_degraded(
        tasks=[_fake_phase1_task()],
        resources=resources,
        network=SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1),
        now_s=5.0,
        max_rounds=10,
    )

    assert coordinator.health == C2Health.DEGRADED
    assert coordinator.leader_id == "int-1"
    assert result.converged
    assert result.final_views["coordination_mode"]["state"] == "distributed_cbba"
    assert result.final_views["coordination_mode"]["leader_role"] == "cluster_representative"


def test_fake_airsim_uncertainty_with_consistent_terminal_requests_active_secondary_assist() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(position_sigma_m=35.0),
        association_risk=_association_risk(ambiguity_score=0.45),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
        communication_summaries=[_fake_secondary_video_link()],
        current_time_s=10.5,
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert decision.target_node_id == "sec-north-1"
    assert decision.coverage_cell == "cell-north"
    assert decision.terminal_consistent
    assert "d1_track_uncertainty_medium" in decision.risk_factors
    assert "d2_association_ambiguity_medium" in decision.risk_factors


def test_fake_airsim_terminal_mismatch_requests_center_replan_when_available() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(),
        association_risk=_association_risk(),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-north-2",
            non_locked_frames=3,
            mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert decision.target_node_id is None
    assert not decision.terminal_consistent
    assert "d5_terminal_id_mismatch" in decision.risk_factors


def test_fake_airsim_terminal_reacquire_without_secondary_continues_center() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(),
        association_risk=_association_risk(),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.AMBIGUOUS,
            observed_global_track_id=None,
            non_locked_frames=4,
            mismatch_frames=0,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=False),
    )

    assert decision.mode == DegradationMode.NONE
    assert decision.action == DegradationAction.CONTINUE_CENTER
    assert decision.reason == "terminal_persistent_reacquire_center_binding_stable"
    assert decision.target_node_id is None
    assert decision.coverage_cell == "cell-north"
    assert decision.terminal_consistent


def test_fake_airsim_terminal_mismatch_requests_center_replan_without_secondary() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(),
        association_risk=_association_risk(),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.AMBIGUOUS,
            observed_global_track_id="track-north-2",
            non_locked_frames=3,
            mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=False),
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert decision.target_node_id is None
    assert decision.coverage_cell == "cell-north"


def test_fake_airsim_terminal_mismatch_with_stale_secondary_link_requests_center_replan() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(),
        association_risk=_association_risk(),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.REACQUIRE,
            observed_global_track_id="track-north-2",
            non_locked_frames=3,
            mismatch_frames=2,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
        communication_summaries=[_fake_secondary_video_link(received_timestamp=10.0, stale_after_s=1.0)],
        current_time_s=12.0,
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert decision.target_node_id is None


def test_fake_airsim_decision_payload_is_bus_serializable_without_airsim_types() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(position_sigma_m=35.0),
        association_risk=_association_risk(ambiguity_score=0.45),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=True),
    )

    payload = decision.to_dict()

    assert payload == {
        "mode": "active_degradation",
        "action": "request_secondary_assist",
        "reason": "risk_rising_request_secondary_assist",
        "target_node_id": "sec-north-1",
        "coverage_cell": "cell-north",
        "terminal_consistent": True,
        "risk_factors": [
            "d1_track_uncertainty_medium",
            "d2_association_ambiguity_medium",
        ],
        "requires_human_review": False,
    }
