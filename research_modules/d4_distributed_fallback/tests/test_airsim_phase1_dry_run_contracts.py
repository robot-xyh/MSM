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
)
from d4_distributed_fallback.coordinator import FailoverCoordinator
from d4_distributed_fallback.models import (
    AvailabilityBand,
    C2Health,
    CommBand,
    ConfidenceBand,
    NodeRole,
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
    )


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
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert decision.target_node_id == "sec-north-1"
    assert decision.coverage_cell == "cell-north"
    assert decision.terminal_consistent
    assert "d1_track_uncertainty_medium" in decision.risk_factors
    assert "d2_association_ambiguity_medium" in decision.risk_factors


def test_fake_airsim_terminal_mismatch_actively_degrades_to_secondary_when_available() -> None:
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
    assert decision.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert decision.target_node_id == "sec-north-1"
    assert not decision.terminal_consistent
    assert "terminal_persistent_disagreement" in decision.risk_factors


def test_fake_airsim_terminal_mismatch_actively_degrades_to_distributed_without_secondary() -> None:
    decision = ActiveDegradationArbiter().evaluate(
        track_uncertainty=_track_uncertainty(),
        association_risk=_association_risk(),
        assignment_validity=_assignment_validity(),
        terminal_association=_terminal_summary(
            decision_state=TerminalDecisionState.AMBIGUOUS,
            observed_global_track_id=None,
            non_locked_frames=3,
            mismatch_frames=0,
        ),
        c2_health=C2Health.NORMAL,
        secondary_nodes=_fake_phase1_resources(secondary_available=False),
    )

    assert decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert decision.target_node_id is None
    assert decision.coverage_cell == "cell-north"


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

