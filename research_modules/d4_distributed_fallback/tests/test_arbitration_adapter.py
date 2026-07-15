from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from d4_distributed_fallback import (
    ActiveDegradationArbiter,
    ActiveDegradationConfig,
    AvailabilityBand,
    C2Health,
    CommBand,
    D4ArbitrationAdapter,
    DegradationAction,
    DegradationMode,
    DistributedVisualEvidenceSummary,
    NodeRole,
    ResourceSummary,
    SecondaryReadinessWindowConfig,
    SecondaryTakeoverPlanState,
    TrackSummary,
    build_assignment_validity_summary,
    build_communication_summary,
    build_distributed_visual_evidence_summary,
    merge_distributed_visual_evidence_into_tracks,
)
from d4_distributed_fallback.models import ConfidenceBand


def _track(position_sigma_m: float = 5.0) -> SimpleNamespace:
    covariance = np.diag(
        [
            position_sigma_m**2,
            (position_sigma_m * 0.8) ** 2,
            9.0,
            1.0,
            1.0,
            1.0,
        ]
    )
    return SimpleNamespace(
        global_track_id="G-TGT-001",
        covariance=covariance,
        timestamp=10.0,
        last_update_time=9.8,
        metadata={"coverage_cell": "cell-north", "track_version": 4},
    )


def _metrics(
    ambiguity: float = 0.05,
    id_switches: int = 0,
    continuity: float = 0.96,
    *,
    truth_metrics_available: bool = True,
    continuity_available: bool = True,
    duplicate_track_risk: float = 0.0,
    duplicate_assignment_count: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        latest_association_ambiguity=ambiguity,
        id_switch_count=id_switches,
        duplicate_assignment_count=duplicate_assignment_count,
        latest_duplicate_track_risk=duplicate_track_risk,
        track_continuity=continuity,
        truth_metrics_available=truth_metrics_available,
        continuity_available=continuity_available,
    )


def _association_result(ambiguity: float = 0.05) -> SimpleNamespace:
    return SimpleNamespace(ambiguity_score=ambiguity, metadata={})


def _plan(version: int = 3, created_at: float = 9.5) -> SimpleNamespace:
    assignments = (
        SimpleNamespace(target_id="G-TGT-001", resource_id="INT-01", cost=0.3),
        SimpleNamespace(target_id="G-TGT-002", resource_id="INT-02", cost=0.8),
    )
    return SimpleNamespace(
        plan_id="d3-plan-test",
        version=version,
        created_at=created_at,
        assignments=assignments,
        decision_state="accepted",
    )


def _assignment(cost_margin: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        target_id="G-TGT-001",
        resource_id="INT-01",
        cost=0.3,
        plan_version=3,
        cost_margin=cost_margin,
    )


def _terminal(
    decision_state: str = "locked",
    confidence: float = 0.92,
    ambiguity: float = 0.04,
    friend_state: str = "none",
    terminal_evidence_applicable: bool | None = None,
) -> SimpleNamespace:
    fields = dict(
        resource_id="INT-01",
        assigned_global_track_id="G-TGT-001",
        decision_state=decision_state,
        association_confidence=confidence,
        ambiguity_score=ambiguity,
        friend_conflict_state=friend_state,
    )
    if terminal_evidence_applicable is not None:
        fields["terminal_evidence_applicable"] = terminal_evidence_applicable
    return SimpleNamespace(**fields)


def _secondary(available: bool = True) -> ResourceSummary:
    return ResourceSummary(
        node_id="SEC-1",
        capability_class="tethered_recon",
        availability_band=AvailabilityBand.HIGH if available else AvailabilityBand.NONE,
        comm_band=CommBand.GOOD,
        takeover_priority=10,
        lease_epoch=5,
        lease_expires_at_s=20.0,
        epoch=1,
        node_role=NodeRole.SECONDARY_RECON,
        coordinator_only=True,
        coverage_cell="cell-north",
        heartbeat_timestamp_s=9.9,
        heartbeat_stale_after_s=2.0,
        cue_freshness_s=0.1,
        gimbal_pointing_ok=True,
        secondary_coverage_ratio=0.90,
        secondary_network_full_view_rate=0.90,
        stable_cross_view_registration_count=2,
    )


def _fresh_secondary_communication(
    *,
    node_id: str = "SEC-1",
    received_timestamp: float = 9.9,
) -> dict[str, object]:
    return {
        "source_node_id": node_id,
        "target_node_id": "INT-01",
        "link_type": "video_cue",
        "payload_kind": "video_metadata",
        "sent_timestamp": received_timestamp - 0.1,
        "received_timestamp": received_timestamp,
        "stale_after_s": 1.0,
    }


def _immediate_readiness_adapter() -> D4ArbitrationAdapter:
    return D4ArbitrationAdapter(
        readiness_config=SecondaryReadinessWindowConfig(
            required_consecutive_decisions=1,
            required_duration_s=0.0,
        )
    )


def _evaluate_takeover(
    adapter: D4ArbitrationAdapter,
    *,
    timestamp: float,
    secondary: ResourceSummary | None = None,
    communication_records: list[object] | None = None,
    **overrides: object,
):
    if communication_records is None:
        communication_records = [
            _fresh_secondary_communication(received_timestamp=timestamp - 0.1)
        ]
    kwargs: dict[str, object] = {
        "timestamp": timestamp,
        "track": _track(position_sigma_m=60.0),
        "association_metrics": _metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        "plan": _plan(created_at=5.0),
        "assignment": _assignment(),
        "terminal_association": _terminal(
            decision_state="reacquire",
            confidence=0.35,
            ambiguity=0.9,
        ),
        "observed_global_track_id": "G-TGT-002",
        "consecutive_non_locked_frames": 3,
        "consecutive_mismatch_frames": 2,
        "c2_health": C2Health.FAILED,
        "secondary_nodes": [secondary or _secondary()],
        "communication_records": communication_records,
    }
    kwargs.update(overrides)
    return adapter.evaluate(**kwargs)


def test_adapter_maps_low_risk_inputs_to_continue_center_event_metadata() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_result=_association_result(),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert result.decision.mode == DegradationMode.NONE
    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert result.record.plan_id == "d3-plan-test"
    assert result.record.plan_version == 3
    assert result.record.track_version == 4
    assert result.record.terminal_consistent

    event_kwargs = result.record.to_event_record_kwargs()
    assert event_kwargs["event_type"] == "d4_arbitration_decision"
    assert event_kwargs["severity"] == "info"
    metadata = event_kwargs["metadata"]
    assert metadata["d4_action"] == "continue_center"
    assert metadata["degradation_mode"] == "none"
    assert metadata["d4_degradation_mode"] == "none"
    assert metadata["selected_coordinator"] == "center"
    assert metadata["trigger_reason"] == "terminal_consistent_and_risk_low"
    assert metadata["trigger_timestamp"] == 10.0
    assert metadata["decision_timestamp"] == 10.0
    assert metadata["review_label"] == "unnecessary"
    assert metadata["active_degradation_review_label"] == "unnecessary"
    assert metadata["review_label_detail"] == "continue_center"
    assert metadata["review_label_source"] == "derived"
    assert metadata["review_pre_window_start_timestamp"] == 8.0
    assert metadata["review_pre_window_end_timestamp"] == 10.0
    assert metadata["review_post_window_start_timestamp"] == 10.0
    assert metadata["review_post_window_end_timestamp"] == 15.0
    assert metadata["secondary_diagnostic_node_id"] == "SEC-1"
    assert abs(metadata["secondary_diagnostic_heartbeat_age_s"] - 0.1) < 1e-9
    assert metadata["global_track_id"] == "G-TGT-001"
    assert metadata["plan_version"] == 3
    assignment_evidence = result.to_event_metadata()["assignment_validity"]
    assert assignment_evidence["metadata"] == {
        "plan_age_reference": "plan.created_at",
        "plan_age_reference_timestamp_s": 9.5,
        "identity_age_s": 0.5,
    }


def test_assignment_age_prefers_last_evaluated_activity_timestamp() -> None:
    summary = build_assignment_validity_summary(
        plan=SimpleNamespace(
            version=3,
            created_at=0.0,
            stale_after_s=4.0,
            decision_state="accepted",
            metadata={"last_evaluated_at_s": 9.0},
        ),
        assignment=_assignment(),
        timestamp=10.0,
        global_track_id="G-TGT-001",
        resource_id="INT-01",
    )

    assert summary.plan_age_s == 1.0
    assert summary.is_current is True
    assert summary.metadata == {
        "plan_age_reference": "plan.metadata.last_evaluated_at_s",
        "plan_age_reference_timestamp_s": 9.0,
        "identity_age_s": 10.0,
    }


def test_assignment_age_without_evaluation_metadata_keeps_created_at_behavior() -> None:
    summary = build_assignment_validity_summary(
        plan=SimpleNamespace(
            version=3,
            created_at=0.0,
            stale_after_s=4.0,
            decision_state="accepted",
        ),
        assignment=_assignment(),
        timestamp=10.0,
        global_track_id="G-TGT-001",
        resource_id="INT-01",
    )

    assert summary.plan_age_s == 10.0
    assert summary.is_current is False
    assert summary.metadata["plan_age_reference"] == "plan.created_at"
    assert summary.metadata["identity_age_s"] == 10.0


def test_assignment_becomes_stale_only_after_activity_age_exceeds_threshold() -> None:
    common = {
        "version": 3,
        "created_at": 0.0,
        "stale_after_s": 4.0,
        "decision_state": "accepted",
    }
    at_threshold = build_assignment_validity_summary(
        plan=SimpleNamespace(
            **common,
            metadata={"last_evaluated_at_s": 6.0},
        ),
        assignment=_assignment(),
        timestamp=10.0,
        global_track_id="G-TGT-001",
        resource_id="INT-01",
    )
    over_threshold = build_assignment_validity_summary(
        plan=SimpleNamespace(
            **common,
            metadata={"last_evaluated_at_s": 5.9},
        ),
        assignment=_assignment(),
        timestamp=10.0,
        global_track_id="G-TGT-001",
        resource_id="INT-01",
    )

    assert at_threshold.plan_age_s == 4.0
    assert at_threshold.is_current is True
    assert over_threshold.plan_age_s == pytest.approx(4.1)
    assert over_threshold.is_current is False


def test_adapter_reads_resource_infeasibility_as_center_replan_hard_risk() -> None:
    assignment = _assignment()
    assignment.resource_feasible = False

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=assignment,
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert result.assignment_validity.resource_feasible is False
    assert result.assignment_validity.metadata["resource_feasibility_source"] == (
        "assignment.resource_feasible"
    )
    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.decision.target_node_id is None
    assert "d3_resource_infeasible" in result.record.hard_risk_factors
    assert "d3_resource_infeasible" in result.record.terminal_binding_reject_reasons


def test_adapter_ignores_unavailable_truth_identity_metrics_online() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_result=_association_result(),
        association_metrics=_metrics(
            id_switches=4,
            continuity=0.0,
            truth_metrics_available=False,
            continuity_available=False,
        ),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert result.association_risk.truth_metrics_available is False
    assert result.association_risk.continuity_available is False
    assert result.association_risk.id_switch_count == 4
    assert result.association_risk.track_continuity == 0.0
    assert result.decision.mode == DegradationMode.NONE
    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert "d2_id_switch_observed" not in result.decision.risk_factors
    assert "d2_track_continuity_low" not in result.decision.risk_factors


def test_adapter_keeps_continuous_duplicate_track_risk_soft_when_count_is_zero() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_result=_association_result(),
        association_metrics=_metrics(
            id_switches=0,
            continuity=0.0,
            truth_metrics_available=False,
            continuity_available=False,
            duplicate_track_risk=0.8,
        ),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[],
    )

    assert result.association_risk.truth_metrics_available is False
    assert result.association_risk.continuity_available is False
    assert result.association_risk.duplicate_track_count == 0
    assert result.association_risk.duplicate_track_risk == 0.8
    assert result.decision.mode == DegradationMode.NONE
    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert "d2_duplicate_track_risk_high" in result.decision.risk_factors
    assert "d2_duplicate_track_risk_high" in result.record.soft_risk_factors
    assert "d2_duplicate_track_observed" not in result.decision.risk_factors
    assert "d2_track_continuity_low" not in result.decision.risk_factors


def test_adapter_keeps_explicit_duplicate_count_as_immediate_hard_risk() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_result=_association_result(),
        association_metrics=_metrics(
            id_switches=0,
            continuity=0.0,
            truth_metrics_available=False,
            continuity_available=False,
            duplicate_track_risk=0.8,
            duplicate_assignment_count=1,
        ),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[],
    )

    assert result.association_risk.duplicate_track_count == 1
    assert result.association_risk.duplicate_track_risk == 0.8
    assert result.decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert "d2_duplicate_track_observed" in result.decision.risk_factors
    assert "d2_duplicate_track_risk_high" not in result.decision.risk_factors
    assert "d2_duplicate_track_observed" in result.record.hard_risk_factors


def test_adapter_consumes_mobile_high_recon_metadata_without_auto_takeover() -> None:
    mobile_node = {
        "node_id": "MHR-1",
        "role": "mobile_high_recon",
        "capability_class": "mobile_high_recon",
        "availability_band": "high",
        "comm_band": "good",
        "coordinator_only": True,
        "coverage_cell": "cell-north",
        "heartbeat_timestamp_s": 9.9,
        "heartbeat_stale_after_s": 2.0,
        "lease_expires_at_s": 20.0,
        "cue_freshness": 0.2,
        "gimbal_pointing_ok": True,
        "secondary_coverage_ratio": 0.86,
        "secondary_network_full_view_rate": 0.90,
        "cross_view_support_count": 2,
    }
    d5_evidence = {
        "cue_freshness": 0.15,
        "gimbal_pointing_ok": True,
        "secondary_coverage_ratio": 0.86,
        "cross_view_support_count": 2,
        "cross_view_association_count": 2,
    }

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_result=_association_result(),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[mobile_node],
        communication_records=[_fresh_secondary_communication(node_id="MHR-1")],
        d5_evidence=d5_evidence,
    )
    metadata = result.record.to_event_metadata()
    lifecycle = metadata["secondary_lifecycle"][0]

    assert result.decision.mode == DegradationMode.NONE
    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert result.decision.target_node_id is None
    assert result.record.secondary_available is True
    assert metadata["cue_freshness_s"] == 0.15
    assert metadata["gimbal_pointing_ok"] is True
    assert metadata["secondary_coverage_ratio"] == 0.86
    assert metadata["cross_view_support_count"] == 2
    assert lifecycle["node_id"] == "MHR-1"
    assert lifecycle["secondary_capability_class"] == "mobile_high_recon"
    assert lifecycle["secondary_readiness_class"] == "takeover_ready"
    assert lifecycle["is_mobile_high_recon"] is True
    assert lifecycle["is_fixed_tethered_secondary"] is False
    assert lifecycle["cue_freshness_s"] == 0.2
    assert lifecycle["cue_stale"] is False
    assert lifecycle["gimbal_pointing_ok"] is True
    assert lifecycle["secondary_coverage_ratio"] == 0.86
    assert lifecycle["coverage_matches_requested_cell"] is True
    assert metadata["secondary_network_coverage_available"] is True
    assert abs(metadata["secondary_network_full_view_gap"] - 0.14) < 1e-9
    assert metadata["secondary_diagnostic_node_id"] == "MHR-1"
    assert metadata["secondary_diagnostic_coverage_ratio"] == 0.86
    assert metadata["secondary_diagnostic_visible"] is True
    assert metadata["secondary_diagnostic_registered"] is True
    assert metadata["secondary_diagnostic_takeover_capable"] is True
    assert metadata["secondary_diagnostic_capability_score"] > 0.0
    assert metadata["secondary_capability_class"] == "takeover_ready"
    assert metadata["secondary_capability_inputs"]["coverage_ratio"] == 0.86
    assert metadata["secondary_diagnostic_capability_class"] == "takeover_ready"


def test_secondary_assist_preserves_center_plan_owner_and_version() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(position_sigma_m=25.0),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        communication_records=[_fresh_secondary_communication()],
    )
    metadata = result.record.to_event_metadata()

    assert result.decision.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert result.record.active_plan_owner == "center"
    assert result.record.plan_version == 3
    assert result.record.secondary_takeover.state == (
        SecondaryTakeoverPlanState.NOT_APPLICABLE
    )
    assert metadata["secondary_assist_requested"] is True
    assert metadata["secondary_takeover_candidate"] is False


def test_adapter_suppresses_far_range_terminal_soft_evidence() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(
            decision_state="reacquire",
            confidence=0.1,
            ambiguity=0.95,
            terminal_evidence_applicable=False,
        ),
        consecutive_non_locked_frames=20,
        consecutive_mismatch_frames=5,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )
    metadata = result.record.to_event_metadata()

    assert result.terminal_association.terminal_evidence_applicable is False
    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert result.decision.risk_factors == ()
    assert metadata["terminal_evidence_applicable"] is False
    assert metadata["secondary_assist_requested"] is False
    assert metadata["hard_risk_factors"] == []
    assert metadata["soft_risk_factors"] == []


def test_adapter_keeps_far_range_airsim_soft_risk_combination_on_center() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=_metrics(
            ambiguity=0.4,
            duplicate_track_risk=0.8,
        ),
        plan=_plan(),
        assignment=_assignment(cost_margin=0.02),
        terminal_association=_terminal(
            decision_state="reacquire",
            confidence=0.1,
            ambiguity=0.95,
            terminal_evidence_applicable=False,
        ),
        consecutive_non_locked_frames=20,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )
    metadata = result.record.to_event_metadata()

    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert result.decision.reason == "midcourse_soft_risk_continue_center"
    assert result.record.active_plan_owner == "center"
    assert result.record.plan_version == 3
    assert metadata["terminal_evidence_applicable"] is False
    assert metadata["secondary_assist_requested"] is False
    assert metadata["hard_risk_factors"] == []
    assert metadata["soft_risk_factors"] == [
        "d2_association_ambiguity_medium",
        "d2_duplicate_track_risk_high",
        "d3_assignment_cost_margin_low",
    ]


def test_adapter_defaults_terminal_evidence_to_applicable() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert result.terminal_association.terminal_evidence_applicable is True
    assert result.record.terminal_evidence_applicable is True
    assert result.record.to_event_metadata()["terminal_evidence_applicable"] is True


def test_adapter_keeps_soft_margin_and_low_confidence_binding_consistent() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_result=_association_result(),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(cost_margin=0.02),
        terminal_association=_terminal(confidence=0.4),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[],
    )

    assert result.decision.mode == DegradationMode.NONE
    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert result.decision.reason == "soft_risk_terminal_consistent_observe_more"
    assert result.record.terminal_consistent is True
    assert result.record.review_label == "unnecessary"
    assert result.record.review_label_detail == "continue_center"
    assert "d3_assignment_cost_margin_low" in result.record.risk_factors
    assert "d5_terminal_confidence_low" in result.record.risk_factors
    metadata = result.record.to_event_metadata()
    assert metadata["hard_risk_factors"] == []
    assert metadata["soft_risk_factors"] == [
        "d3_assignment_cost_margin_low",
        "d5_terminal_confidence_low",
    ]
    assert metadata["active_degradation_false_trigger_candidate"] is False
    assert metadata["terminal_binding_consistent"] is True
    assert metadata["terminal_binding_reject_reasons"] == []
    assert metadata["terminal_visual_state"] == "locked"
    assert metadata["arbitration_state_key"] == "INT-01:G-TGT-001"


def test_adapter_isolates_hysteresis_between_resource_track_bindings() -> None:
    adapter = D4ArbitrationAdapter(
        arbiter=ActiveDegradationArbiter(
            ActiveDegradationConfig(
                min_dwell_s=10.0,
                release_consecutive_consistent_frames=2,
            )
        )
    )
    held = adapter.evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(friend_state="friend_conflict"),
    )
    assert held.decision.action == DegradationAction.HOLD_FOR_REVIEW

    second_assignment = SimpleNamespace(
        target_id="G-TGT-002",
        resource_id="INT-02",
        cost=0.8,
        plan_version=3,
    )
    second_terminal = SimpleNamespace(
        resource_id="INT-02",
        assigned_global_track_id="G-TGT-002",
        observed_global_track_id="G-TGT-002",
        decision_state="locked",
        association_confidence=0.95,
        ambiguity_score=0.01,
        friend_conflict_state="none",
    )
    healthy = adapter.evaluate(
        timestamp=10.0,
        track=_track(),
        global_track_id="G-TGT-002",
        resource_id="INT-02",
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=second_assignment,
        terminal_association=second_terminal,
    )

    assert healthy.decision.action == DegradationAction.CONTINUE_CENTER
    assert healthy.decision.reason == "terminal_consistent_and_risk_low"
    assert healthy.record.terminal_consistent is True
    assert healthy.record.arbitration_state_key == "INT-02:G-TGT-002"


def test_adapter_holds_for_review_on_verified_friend_conflict_even_if_center_failed() -> None:
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(friend_state="verified_friend_overlap"),
        c2_health=C2Health.FAILED,
        secondary_nodes=[_secondary()],
    )

    assert result.decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert result.record.requires_human_review
    assert result.record.to_event_record_kwargs()["severity"] == "warning"
    assert "terminal_friend_conflict" in result.record.risk_factors


def test_adapter_routes_duplicate_terminal_lock_to_center_replan() -> None:
    cross_view = SimpleNamespace(
        duplicate_terminal_lock_risk=True,
        ambiguity_score=0.82,
        support_count=2,
    )

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(),
        cross_view_summary=cross_view,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    assert result.terminal_association.duplicate_terminal_lock
    assert result.terminal_association.cross_view_risk_score >= 0.82
    assert result.decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.decision.target_node_id is None
    assert "d5_duplicate_terminal_lock" in result.decision.risk_factors


def test_adapter_keeps_center_authority_when_secondary_link_is_stale() -> None:
    stale_link = SimpleNamespace(
        source_node_id="SEC-1",
        target_node_id="INT-01",
        link_type="video_cue",
        payload_kind="video_metadata",
        sent_timestamp=9.0,
        received_timestamp=9.1,
        stale_after_s=0.5,
        sequence_id="sec-1:9",
    )

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(position_sigma_m=60.0),
        association_metrics=_metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        plan=_plan(created_at=5.0),
        assignment=_assignment(),
        terminal_association=_terminal(decision_state="hold", confidence=0.35, ambiguity=0.9),
        observed_global_track_id="G-TGT-002",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        communication_records=[stale_link],
    )

    assert build_communication_summary(stale_link).is_stale(10.0)
    assert result.record.communication_fresh is False
    assert result.record.secondary_available is False
    assert result.secondary_lifecycle[0].link_stale is True
    assert result.secondary_lifecycle[0].secondary_available is False
    assert result.decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.decision.target_node_id is None


def test_adapter_requests_center_replan_when_persistent_mismatch_has_fresh_secondary_link() -> None:
    fresh_link = {
        "source_node_id": "SEC-1",
        "target_node_id": "INT-01",
        "link_type": "video_cue",
        "payload_kind": "video_metadata",
        "sent_timestamp": 9.8,
        "received_timestamp": 9.9,
        "stale_after_s": 1.0,
        "sequence_id": "sec-1:10",
    }

    result = _immediate_readiness_adapter().evaluate(
        timestamp=10.0,
        track=_track(position_sigma_m=60.0),
        association_metrics=_metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        plan=_plan(created_at=5.0),
        assignment=_assignment(),
        terminal_association=_terminal(decision_state="reacquire", confidence=0.35, ambiguity=0.9),
        observed_global_track_id="G-TGT-002",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        communication_records=[fresh_link],
    )

    assert result.record.communication_fresh is True
    assert result.record.secondary_available is True
    assert result.secondary_lifecycle[0].video_cue_freshness_s is not None
    assert abs(result.secondary_lifecycle[0].video_cue_freshness_s - 0.1) < 1e-9
    assert result.decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.decision.target_node_id is None


def test_adapter_reports_secondary_detect_visible_without_cross_view_registration() -> None:
    d5_evidence = {
        "secondary_single_camera_full_view_frame_rate": 1.0,
        "secondary_network_joint_full_view_frame_rate": 0.92,
        "secondary_network_mean_coverage_ratio": 0.88,
        "cross_view_association_count": 0,
        "stable_cross_view_registration_count": 0,
        "not_registered_count": 35,
        "cross_view_conversion_gap": 1.0,
        "secondary_detect_to_cross_view_reject_reasons": ("global_binding_missing",),
    }

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(position_sigma_m=25.0),
        association_metrics=_metrics(),
        plan=_plan(),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        communication_records=[_fresh_secondary_communication()],
        d5_evidence=d5_evidence,
    )

    metadata = result.record.to_event_metadata()
    assert result.decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert result.decision.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert metadata["secondary_assist_requested"] is True
    assert metadata["secondary_takeover_candidate"] is False
    assert metadata["secondary_takeover_state"] == "not_applicable"
    assert metadata["secondary_takeover_success"] is False
    assert metadata["secondary_detect_available_but_not_registered"] is True
    assert metadata["secondary_network_joint_full_view_frame_rate"] == 0.92
    assert metadata["secondary_network_mean_coverage_ratio"] == 0.88
    assert metadata["secondary_network_coverage_available"] is True
    assert abs(metadata["secondary_network_full_view_gap"] - 0.08) < 1e-9
    assert metadata["cross_view_association_count"] == 0
    assert metadata["stable_cross_view_registration_count"] == 0
    assert metadata["not_registered_count"] == 35
    assert metadata["cross_view_conversion_gap"] == 1.0
    assert metadata["secondary_detect_to_registration_gap"] == 1.0
    assert metadata["secondary_detect_to_cross_view_reject_reasons"] == [
        "global_binding_missing"
    ]
    assert "secondary_detect_available_but_not_registered" in metadata[
        "secondary_detect_to_cross_view_diagnostic"
    ]
    assert "global_binding_missing" in metadata["secondary_detect_to_cross_view_diagnostic"]
    lifecycle = metadata["secondary_lifecycle"][0]
    assert lifecycle["secondary_visible"] is True
    assert lifecycle["secondary_registered"] is False
    assert lifecycle["secondary_takeover_capable"] is False
    assert lifecycle["secondary_readiness_class"] == "visible_only"
    assert metadata["secondary_capability_class"] == "visible_only"
    assert metadata["secondary_diagnostic_capability_class"] == "visible_only"
    assert metadata["secondary_capability_inputs"]["not_registered_count"] == 35
    assert metadata["secondary_diagnostic_visible"] is True
    assert metadata["secondary_diagnostic_registered"] is False
    assert metadata["secondary_diagnostic_takeover_capable"] is False


def test_adapter_keeps_stale_secondary_link_unselectable_with_detect_evidence() -> None:
    stale_link = {
        "source_node_id": "SEC-1",
        "target_node_id": "INT-01",
        "link_type": "video_cue",
        "payload_kind": "video_metadata",
        "sent_timestamp": 9.0,
        "received_timestamp": 9.1,
        "stale_after_s": 0.5,
    }
    d5_evidence = {
        "metadata": {
            "secondary_network_joint_full_view_frame_rate": 0.96,
            "secondary_network_mean_coverage_ratio": 0.91,
            "cross_view_association_count": 0,
            "secondary_detect_to_cross_view_reject_reasons": (
                "registration_gate_rejected",
            ),
        }
    }

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(position_sigma_m=60.0),
        association_metrics=_metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        plan=_plan(created_at=5.0),
        assignment=_assignment(),
        terminal_association=_terminal(decision_state="reacquire", confidence=0.35, ambiguity=0.9),
        observed_global_track_id="G-TGT-002",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        communication_records=[stale_link],
        d5_evidence=d5_evidence,
    )

    metadata = result.record.to_event_metadata()
    assert result.record.secondary_available is False
    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.decision.target_node_id is None
    assert metadata["selected_coordinator"] == "center"
    assert metadata["secondary_detect_available_but_not_registered"] is True
    assert "registration_gate_rejected" in metadata[
        "secondary_detect_to_cross_view_diagnostic"
    ]


def test_adapter_exposes_secondary_takeover_pending_and_active_plan_metadata() -> None:
    kwargs = dict(
        timestamp=10.0,
        track=_track(position_sigma_m=60.0),
        association_metrics=_metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        plan=_plan(created_at=5.0),
        assignment=_assignment(),
        terminal_association=_terminal(decision_state="reacquire", confidence=0.35, ambiguity=0.9),
        observed_global_track_id="G-TGT-002",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.FAILED,
        secondary_nodes=[_secondary()],
        communication_records=[_fresh_secondary_communication()],
    )

    pending = _immediate_readiness_adapter().evaluate(**kwargs)
    pending_metadata = pending.record.to_event_metadata()

    assert pending.decision.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert pending.record.secondary_takeover.state == (
        SecondaryTakeoverPlanState.PENDING_SECONDARY_PLAN
    )
    assert pending.record.active_plan_owner == "center"
    assert pending_metadata["secondary_takeover_state"] == "pending_secondary_plan"
    assert pending_metadata["secondary_plan_source_node_id"] == "SEC-1"
    assert pending_metadata["secondary_plan_id"] is None
    assert pending_metadata["secondary_reassignment_complete"] is False
    assert pending_metadata["secondary_takeover_candidate"] is True
    assert pending_metadata["secondary_takeover_success"] is False
    assert pending_metadata["secondary_plan_activation_delay_s"] is None
    assert pending_metadata["secondary_plan_pending_duration_s"] == 0.0
    assert pending_metadata["secondary_supersedes_plan_id"] == "d3-plan-test"
    assert pending_metadata["secondary_supersedes_plan_version"] == 3
    assert pending_metadata["secondary_plan_lease_epoch"] is None
    assert pending_metadata["required_secondary_plan_lease_epoch"] == 5
    assert pending_metadata["secondary_plan_lease_valid"] is False
    assert pending_metadata["secondary_plan_executable"] is False
    assert pending_metadata["recovery_dual_track_audit"]["center_track_plan_id"] == (
        "d3-plan-test"
    )

    active = _immediate_readiness_adapter().evaluate(
        **kwargs,
        trigger_timestamp=8.0,
        secondary_plan_id="secondary-plan-004",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=12.0,
    )
    active_metadata = active.record.to_event_metadata()

    assert active.record.secondary_takeover.state == (
        SecondaryTakeoverPlanState.SECONDARY_PLAN_ACTIVE
    )
    assert active.record.active_plan_owner == "secondary_node"
    assert active_metadata["secondary_takeover_state"] == "secondary_plan_active"
    assert active_metadata["secondary_plan_id"] == "secondary-plan-004"
    assert active_metadata["secondary_plan_version"] == 4
    assert active_metadata["secondary_reassignment_complete"] is True
    assert active_metadata["secondary_takeover_success"] is True
    assert active_metadata["secondary_plan_activation_delay_s"] == 2.0
    assert active_metadata["secondary_plan_pending_duration_s"] is None
    assert active_metadata["secondary_plan_lease_valid"] is True
    assert active_metadata["secondary_plan_epoch_monotonic"] is True
    assert active_metadata["secondary_plan_executable"] is True


def test_adapter_accepts_current_active_secondary_plan_with_same_id_and_version() -> None:
    result = _immediate_readiness_adapter().evaluate(
        timestamp=10.0,
        trigger_timestamp=8.0,
        track=_track(position_sigma_m=60.0),
        association_metrics=_metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        plan=_plan(version=4, created_at=8.0),
        assignment=_assignment(),
        terminal_association=_terminal(decision_state="reacquire", confidence=0.35, ambiguity=0.9),
        observed_global_track_id="G-TGT-002",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.FAILED,
        secondary_nodes=[_secondary()],
        communication_records=[_fresh_secondary_communication()],
        active_plan_owner="secondary",
        secondary_plan_id="d3-plan-test",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=12.0,
    )
    metadata = result.record.to_event_metadata()

    assert result.record.secondary_takeover.state == (
        SecondaryTakeoverPlanState.SECONDARY_PLAN_ACTIVE
    )
    assert metadata["secondary_takeover_state"] == "secondary_plan_active"
    assert metadata["secondary_plan_id"] == "d3-plan-test"
    assert metadata["secondary_plan_version"] == 4
    assert metadata["secondary_plan_epoch_monotonic"] is True
    assert metadata["secondary_plan_executable"] is True
    assert metadata["secondary_plan_reject_reason"] is None
    assert metadata["secondary_takeover_success"] is True


@pytest.mark.parametrize(
    ("lease_expires_at_s", "expected_executable", "expected_reject_reason"),
    [
        (None, False, "secondary_plan_lease_expiry_missing"),
        (10.1, True, None),
        (10.0, False, "secondary_plan_lease_expired"),
        (9.9, False, "secondary_plan_lease_expired"),
    ],
)
def test_secondary_plan_publish_requires_strict_unexpired_lease(
    lease_expires_at_s: float | None,
    expected_executable: bool,
    expected_reject_reason: str | None,
) -> None:
    result = _evaluate_takeover(
        _immediate_readiness_adapter(),
        timestamp=10.0,
        secondary_plan_id="secondary-plan-004",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=lease_expires_at_s,
    )
    metadata = result.record.to_event_metadata()

    assert metadata["secondary_plan_lease_valid"] is expected_executable
    assert metadata["secondary_plan_executable"] is expected_executable
    assert metadata["secondary_plan_reject_reason"] == expected_reject_reason
    assert metadata["secondary_takeover_state"] == (
        "secondary_plan_active" if expected_executable else "pending_secondary_plan"
    )


@pytest.mark.parametrize(
    ("missing_evidence", "expected_reason"),
    [
        ("heartbeat_timestamp", "heartbeat_timestamp_missing"),
        ("cue_freshness", "cue_freshness_missing"),
        ("gimbal_pointing", "gimbal_pointing_unknown"),
        ("communication_summary", "communication_summary_missing"),
        ("network_full_view_rate", "network_full_view_rate_missing"),
    ],
)
def test_adapter_does_not_publish_takeover_when_capability_evidence_is_missing(
    missing_evidence: str,
    expected_reason: str,
) -> None:
    secondary = _secondary()
    communication_records: list[object] = [_fresh_secondary_communication()]
    if missing_evidence == "heartbeat_timestamp":
        secondary = replace(secondary, heartbeat_timestamp_s=None)
    elif missing_evidence == "cue_freshness":
        secondary = replace(secondary, cue_freshness_s=None)
    elif missing_evidence == "gimbal_pointing":
        secondary = replace(secondary, gimbal_pointing_ok=None)
    elif missing_evidence == "communication_summary":
        communication_records = []
    elif missing_evidence == "network_full_view_rate":
        secondary = replace(secondary, secondary_network_full_view_rate=None)

    result = _evaluate_takeover(
        _immediate_readiness_adapter(),
        timestamp=10.0,
        secondary=secondary,
        communication_records=communication_records,
        secondary_plan_id="secondary-plan-004",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=12.0,
    )
    metadata = result.record.to_event_metadata()

    assert result.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert metadata["secondary_takeover_ready_sustained"] is False
    assert metadata["secondary_takeover_state"] == "not_applicable"
    assert metadata["secondary_plan_executable"] is False
    assert metadata["secondary_takeover_readiness_fallback_reason"] == expected_reason


def test_adapter_publishes_takeover_with_complete_fresh_capability_evidence() -> None:
    result = _evaluate_takeover(
        _immediate_readiness_adapter(),
        timestamp=10.0,
        secondary_plan_id="secondary-plan-004",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=12.0,
    )
    metadata = result.record.to_event_metadata()

    assert result.decision.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert metadata["secondary_capability_class"] == "takeover_ready"
    assert metadata["secondary_takeover_ready_sustained"] is True
    assert metadata["secondary_takeover_state"] == "secondary_plan_active"
    assert metadata["secondary_plan_executable"] is True


def test_adapter_rejects_expired_secondary_plan_as_not_executable() -> None:
    result = _immediate_readiness_adapter().evaluate(
        timestamp=10.0,
        trigger_timestamp=8.0,
        track=_track(position_sigma_m=60.0),
        association_metrics=_metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        plan=_plan(created_at=5.0),
        assignment=_assignment(),
        terminal_association=_terminal(decision_state="reacquire", confidence=0.35, ambiguity=0.9),
        observed_global_track_id="G-TGT-002",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.FAILED,
        secondary_nodes=[_secondary()],
        communication_records=[_fresh_secondary_communication()],
        secondary_plan_id="secondary-plan-expired",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=9.9,
    )
    metadata = result.record.to_event_metadata()

    assert result.record.secondary_takeover.state == (
        SecondaryTakeoverPlanState.PENDING_SECONDARY_PLAN
    )
    assert result.record.active_plan_owner == "center"
    assert metadata["secondary_plan_lease_valid"] is False
    assert metadata["secondary_plan_executable"] is False
    assert metadata["secondary_plan_reject_reason"] == "secondary_plan_lease_expired"
    assert metadata["secondary_takeover_success"] is False


def test_active_secondary_with_expired_lease_holds_fail_closed() -> None:
    result = _immediate_readiness_adapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=_metrics(),
        plan=_plan(version=4, created_at=9.5),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.FAILED,
        secondary_nodes=[_secondary()],
        communication_records=[_fresh_secondary_communication()],
        active_plan_owner="secondary",
        secondary_plan_id="d3-plan-test",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=9.9,
    )
    metadata = result.record.to_event_metadata()

    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert result.record.terminal_consistent is False
    assert result.record.requires_human_review is True
    assert metadata["secondary_plan_executable"] is False
    assert metadata["secondary_plan_reject_reason"] == "secondary_plan_lease_expired"
    assert metadata["terminal_binding_reject_reasons"] == [
        "secondary_plan_lease_expired"
    ]


@pytest.mark.parametrize(
    ("lease_expires_at_s", "expected_reject_reason"),
    [
        (None, "secondary_plan_lease_expiry_missing"),
        (10.0, "secondary_plan_lease_expired"),
    ],
)
def test_active_secondary_owner_cannot_maintain_invalid_lease(
    lease_expires_at_s: float | None,
    expected_reject_reason: str,
) -> None:
    result = _immediate_readiness_adapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=_metrics(),
        plan=_plan(version=4, created_at=9.5),
        assignment=_assignment(),
        terminal_association=_terminal(),
        c2_health=C2Health.FAILED,
        secondary_nodes=[_secondary()],
        communication_records=[_fresh_secondary_communication()],
        active_plan_owner="secondary",
        secondary_plan_id="d3-plan-test",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=lease_expires_at_s,
    )
    metadata = result.record.to_event_metadata()

    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert result.record.active_plan_owner == "hold_review"
    assert metadata["secondary_plan_executable"] is False
    assert metadata["secondary_plan_reject_reason"] == expected_reject_reason
    assert expected_reject_reason in metadata["terminal_binding_reject_reasons"]


def test_adapter_rejects_non_monotonic_secondary_plan_version() -> None:
    result = _immediate_readiness_adapter().evaluate(
        timestamp=10.0,
        trigger_timestamp=8.0,
        track=_track(position_sigma_m=60.0),
        association_metrics=_metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        plan=_plan(created_at=5.0),
        assignment=_assignment(),
        terminal_association=_terminal(decision_state="reacquire", confidence=0.35, ambiguity=0.9),
        observed_global_track_id="G-TGT-002",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.FAILED,
        secondary_nodes=[_secondary()],
        communication_records=[_fresh_secondary_communication()],
        secondary_plan_id="secondary-plan-stale",
        secondary_plan_version=3,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=12.0,
    )
    metadata = result.record.to_event_metadata()

    assert metadata["secondary_plan_epoch_monotonic"] is False
    assert metadata["secondary_plan_executable"] is False
    assert metadata["secondary_plan_reject_reason"] == "secondary_plan_epoch_not_monotonic"


def test_default_readiness_window_blocks_single_frame_takeover_and_audits_evidence() -> None:
    adapter = D4ArbitrationAdapter()

    first = _evaluate_takeover(adapter, timestamp=10.0)
    repeated_same_frame = _evaluate_takeover(adapter, timestamp=10.0)

    for result in (first, repeated_same_frame):
        lifecycle = result.secondary_lifecycle[0]
        metadata = result.record.to_event_metadata()
        assert result.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
        assert lifecycle.secondary_readiness_class == "takeover_ready"
        assert lifecycle.takeover_ready_consecutive_decisions == 1
        assert lifecycle.takeover_ready_sustained is False
        assert lifecycle.registration_evidence_source == (
            "resource_stable_cross_view_registration_count"
        )
        assert lifecycle.stable_registration_evidence_present is True
        assert lifecycle.not_registered_evidence_present is False
        assert metadata["secondary_takeover_state"] == "not_applicable"
        assert metadata["secondary_takeover_ready_sustained"] is False
        assert metadata["secondary_takeover_readiness_fallback_reason"] == (
            "takeover_readiness_not_sustained"
        )


def test_readiness_window_restarts_after_not_ready_edge_and_after_regression() -> None:
    adapter = D4ArbitrationAdapter()
    not_ready_secondary = replace(_secondary(), gimbal_pointing_ok=False)

    initial_not_ready = _evaluate_takeover(
        adapter,
        timestamp=9.9,
        secondary=not_ready_secondary,
    )
    first_ready = _evaluate_takeover(adapter, timestamp=10.0)
    repeated_same_frame = _evaluate_takeover(adapter, timestamp=10.0)
    second_ready = _evaluate_takeover(adapter, timestamp=10.1)
    third_ready = _evaluate_takeover(adapter, timestamp=10.21)

    assert initial_not_ready.secondary_lifecycle[0].takeover_ready_consecutive_decisions == 0
    assert initial_not_ready.secondary_lifecycle[0].takeover_ready_since_s is None
    assert first_ready.secondary_lifecycle[0].takeover_ready_consecutive_decisions == 1
    assert first_ready.secondary_lifecycle[0].takeover_ready_since_s == pytest.approx(10.0)
    assert repeated_same_frame.secondary_lifecycle[0].takeover_ready_consecutive_decisions == 1
    assert second_ready.secondary_lifecycle[0].takeover_ready_consecutive_decisions == 2
    assert third_ready.secondary_lifecycle[0].takeover_ready_consecutive_decisions == 3
    assert third_ready.secondary_lifecycle[0].takeover_ready_duration_s == pytest.approx(0.21)
    assert third_ready.secondary_lifecycle[0].takeover_ready_sustained is True
    assert third_ready.decision.action == DegradationAction.DEGRADE_TO_SECONDARY

    regressed = _evaluate_takeover(
        adapter,
        timestamp=10.3,
        secondary=not_ready_secondary,
    )
    restarted_first = _evaluate_takeover(adapter, timestamp=10.4)
    restarted_second = _evaluate_takeover(adapter, timestamp=10.5)
    restarted_third = _evaluate_takeover(adapter, timestamp=10.61)

    assert regressed.secondary_lifecycle[0].takeover_ready_consecutive_decisions == 0
    assert regressed.secondary_lifecycle[0].takeover_ready_since_s is None
    assert regressed.secondary_lifecycle[0].takeover_ready_sustained is False
    assert restarted_first.secondary_lifecycle[0].takeover_ready_consecutive_decisions == 1
    assert restarted_first.secondary_lifecycle[0].takeover_ready_since_s == pytest.approx(10.4)
    assert restarted_second.secondary_lifecycle[0].takeover_ready_consecutive_decisions == 2
    assert restarted_third.secondary_lifecycle[0].takeover_ready_consecutive_decisions == 3
    assert restarted_third.secondary_lifecycle[0].takeover_ready_duration_s == pytest.approx(0.21)
    assert restarted_third.secondary_lifecycle[0].takeover_ready_sustained is True


def test_sustained_readiness_enters_pending_then_active_with_transition_timing() -> None:
    adapter = D4ArbitrationAdapter()

    first = _evaluate_takeover(adapter, timestamp=10.0)
    second = _evaluate_takeover(adapter, timestamp=10.1)
    pending = _evaluate_takeover(adapter, timestamp=10.21)
    active = _evaluate_takeover(
        adapter,
        timestamp=10.4,
        secondary_plan_id="secondary-plan-004",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=12.0,
    )

    assert first.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert second.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert pending.decision.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert pending.record.secondary_takeover.state == (
        SecondaryTakeoverPlanState.PENDING_SECONDARY_PLAN
    )
    pending_metadata = pending.record.to_event_metadata()
    assert pending_metadata["secondary_takeover_ready_consecutive_decisions"] == 3
    assert pending_metadata["secondary_takeover_ready_sustained"] is True
    assert pending_metadata["secondary_takeover_transition"] == (
        "not_applicable->pending_secondary_plan"
    )
    assert pending_metadata["secondary_plan_pending_since_s"] == pytest.approx(10.21)

    active_metadata = active.record.to_event_metadata()
    assert active.record.secondary_takeover.state == (
        SecondaryTakeoverPlanState.SECONDARY_PLAN_ACTIVE
    )
    assert active_metadata["secondary_plan_executable"] is True
    assert active_metadata["secondary_plan_source_matches_target"] is True
    assert active_metadata["secondary_plan_lease_epoch"] == 5
    assert active_metadata["required_secondary_plan_lease_epoch"] == 5
    assert active_metadata["secondary_takeover_transition"] == (
        "pending_secondary_plan->secondary_plan_active"
    )
    assert active_metadata["secondary_plan_activation_delay_s"] == pytest.approx(0.19)
    assert active_metadata["secondary_plan_activated_at_s"] == pytest.approx(10.4)


@pytest.mark.parametrize(
    ("secondary", "communication_records", "expected_reason"),
    [
        (
            replace(_secondary(), heartbeat_timestamp_s=7.0),
            (_fresh_secondary_communication(),),
            "heartbeat_stale",
        ),
        (
            replace(_secondary(), cue_freshness_s=3.0),
            (_fresh_secondary_communication(),),
            "cue_stale",
        ),
        (
            _secondary(),
            (
                {
                    "source_node_id": "SEC-1",
                    "target_node_id": "INT-01",
                    "link_type": "video_cue",
                    "payload_kind": "video_metadata",
                    "sent_timestamp": 7.8,
                    "received_timestamp": 8.0,
                    "stale_after_s": 1.0,
                },
            ),
            "link_stale",
        ),
    ],
)
def test_secondary_health_regression_falls_back_to_distributed_with_reason(
    secondary: ResourceSummary,
    communication_records: tuple[object, ...],
    expected_reason: str,
) -> None:
    adapter = D4ArbitrationAdapter()
    for timestamp in (10.0, 10.1, 10.21):
        pending = _evaluate_takeover(adapter, timestamp=timestamp)
    assert pending.record.secondary_takeover.state == (
        SecondaryTakeoverPlanState.PENDING_SECONDARY_PLAN
    )

    regressed = _evaluate_takeover(
        adapter,
        timestamp=10.4,
        secondary=secondary,
        communication_records=list(communication_records),
    )
    metadata = regressed.record.to_event_metadata()

    assert regressed.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert metadata["secondary_takeover_state"] == "not_applicable"
    assert metadata["secondary_takeover_transition"] == (
        "pending_secondary_plan->not_applicable"
    )
    assert metadata["secondary_takeover_fallback_reason"] == expected_reason
    assert metadata["secondary_plan_executable"] is False


def test_active_secondary_plan_rejects_stale_lease_epoch_and_wrong_source() -> None:
    adapter = D4ArbitrationAdapter()
    for timestamp in (10.0, 10.1):
        _evaluate_takeover(adapter, timestamp=timestamp)

    stale_lease = _evaluate_takeover(
        adapter,
        timestamp=10.21,
        secondary_plan_id="secondary-plan-004",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=4,
        secondary_plan_lease_expires_at_s=12.0,
    )
    stale_metadata = stale_lease.record.to_event_metadata()
    assert stale_metadata["secondary_takeover_state"] == "pending_secondary_plan"
    assert stale_metadata["secondary_plan_reject_reason"] == (
        "secondary_plan_lease_epoch_stale"
    )
    assert stale_metadata["secondary_plan_executable"] is False

    wrong_source = _evaluate_takeover(
        adapter,
        timestamp=10.4,
        secondary_plan_id="secondary-plan-005",
        secondary_plan_version=5,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-OTHER",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=12.0,
    )
    wrong_source_metadata = wrong_source.record.to_event_metadata()
    assert wrong_source_metadata["secondary_takeover_state"] == "pending_secondary_plan"
    assert wrong_source_metadata["secondary_plan_reject_reason"] == (
        "secondary_plan_source_mismatch"
    )
    assert wrong_source_metadata["secondary_plan_executable"] is False


def test_active_plan_rolls_back_on_expired_lease_and_capability_regression() -> None:
    adapter = D4ArbitrationAdapter()
    for timestamp in (10.0, 10.1, 10.21):
        _evaluate_takeover(adapter, timestamp=timestamp)
    active = _evaluate_takeover(
        adapter,
        timestamp=10.4,
        secondary_plan_id="secondary-plan-004",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=11.0,
    )
    assert active.record.secondary_takeover.state == (
        SecondaryTakeoverPlanState.SECONDARY_PLAN_ACTIVE
    )

    expired = _evaluate_takeover(
        adapter,
        timestamp=11.1,
        secondary_plan_id="secondary-plan-004",
        secondary_plan_version=4,
        secondary_plan_active=True,
        secondary_plan_source_node_id="SEC-1",
        secondary_plan_lease_epoch=5,
        secondary_plan_lease_expires_at_s=11.0,
    )
    expired_metadata = expired.record.to_event_metadata()
    assert expired_metadata["secondary_takeover_state"] == "pending_secondary_plan"
    assert expired_metadata["secondary_takeover_transition"] == (
        "secondary_plan_active->pending_secondary_plan"
    )
    assert expired_metadata["secondary_takeover_fallback_reason"] == (
        "secondary_plan_lease_expired"
    )
    assert expired_metadata["secondary_plan_executable"] is False

    regressed = _evaluate_takeover(
        adapter,
        timestamp=11.2,
        secondary=replace(_secondary(), gimbal_pointing_ok=False),
    )
    regressed_metadata = regressed.record.to_event_metadata()
    assert regressed.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert regressed_metadata["secondary_takeover_transition"] == (
        "pending_secondary_plan->not_applicable"
    )
    assert regressed_metadata["secondary_takeover_fallback_reason"] == (
        "gimbal_not_pointing"
    )


def test_explicit_not_registered_evidence_is_recorded_per_decision() -> None:
    secondary = replace(
        _secondary(),
        stable_cross_view_registration_count=None,
        not_registered_count=4,
    )

    result = _evaluate_takeover(
        D4ArbitrationAdapter(),
        timestamp=10.0,
        secondary=secondary,
    )
    lifecycle = result.secondary_lifecycle[0]
    metadata = result.record.to_event_metadata()

    assert lifecycle.secondary_readiness_class == "visible_only"
    assert lifecycle.registration_evidence_source == "resource_not_registered_count"
    assert lifecycle.stable_registration_evidence_present is False
    assert lifecycle.not_registered_evidence_present is True
    assert lifecycle.not_registered_count == 4
    assert metadata["secondary_diagnostic_not_registered_evidence_present"] is True
    assert metadata["secondary_diagnostic_registration_evidence_source"] == (
        "resource_not_registered_count"
    )


def test_adapter_normalizes_d5_distributed_visual_evidence_without_d5_import() -> None:
    evidence = {
        "decision_state": "hypothesis_only",
        "assigned_global_track_id": "G-TGT-001",
        "supporting_resource_ids": ("INT-01", "INT-02"),
        "association_confidence": 0.71,
        "ambiguity_score": 0.32,
        "hypotheses": (
            {
                "assigned_global_track_id": "G-TGT-001",
                "supporting_resource_ids": ("INT-02",),
                "support_count": 1,
                "metadata": {"hypothesis_reason": "peer_bearing_bbox_consistent"},
            },
        ),
        "metadata": {"support_count": 2},
    }

    summary = build_distributed_visual_evidence_summary(
        evidence,
        expected_global_track_id="G-TGT-001",
    )

    assert isinstance(summary, DistributedVisualEvidenceSummary)
    assert summary.visual_support_resource_ids == ("INT-01", "INT-02")
    assert summary.assigned_global_track_id == "G-TGT-001"
    assert summary.hypothesis_only
    assert summary.support_count == 2
    assert summary.missing_global_track_id is False
    assert summary.global_track_id_conflict is False


def test_adapter_merges_d5_visual_evidence_into_matching_tracks_by_global_id() -> None:
    tracks = [
        TrackSummary(
            track_id="G-TGT-001",
            coarse_cell="cell-a",
            age_s=1.0,
            confidence_band=ConfidenceBand.HIGH,
            source_count=2,
            epoch=1,
        ),
        TrackSummary(
            track_id="G-TGT-002",
            coarse_cell="cell-b",
            age_s=1.0,
            confidence_band=ConfidenceBand.HIGH,
            source_count=2,
            epoch=1,
        ),
    ]
    evidence = [
        SimpleNamespace(
            decision_state="locked",
            assigned_global_track_id="G-TGT-002",
            supporting_resource_ids=("INT-03",),
            association_confidence=0.88,
            ambiguity_score=0.08,
        )
    ]

    merged = merge_distributed_visual_evidence_into_tracks(tracks, evidence)

    assert not merged[0].visual_evidence.has_evidence
    assert merged[1].visual_evidence.visual_support_resource_ids == ("INT-03",)
    assert merged[1].visual_evidence.assigned_global_track_id == "G-TGT-002"


def test_adapter_outputs_d6_compatible_active_decision_event_fields() -> None:
    result = _immediate_readiness_adapter().evaluate(
        timestamp=10.0,
        trigger_timestamp=8.5,
        review_label="necessary",
        track=_track(position_sigma_m=60.0),
        association_metrics=_metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        plan=_plan(created_at=5.0),
        assignment=_assignment(),
        terminal_association=_terminal(decision_state="reacquire", confidence=0.35, ambiguity=0.9),
        observed_global_track_id="G-TGT-002",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
        communication_records=[
            {
                "source_node_id": "SEC-1",
                "target_node_id": "INT-01",
                "link_type": "video_cue",
                "payload_kind": "video_metadata",
                "sent_timestamp": 9.8,
                "received_timestamp": 9.9,
                "stale_after_s": 1.0,
            }
        ],
    )

    event = result.record.to_event_record_kwargs()
    metadata = event["metadata"]

    assert event["event_type"] == "active_degradation_decision"
    assert metadata["degradation_mode"] == "active"
    assert metadata["d4_degradation_mode"] == "active_degradation"
    assert metadata["selected_coordinator"] == "center"
    assert metadata["coverage_cell"] == "cell-north"
    assert metadata["trigger_reason"] == "center_plan_hard_invalidation"
    assert metadata["trigger_timestamp"] == 8.5
    assert metadata["decision_timestamp"] == 10.0
    assert metadata["review_label"] == "necessary"
    assert metadata["active_degradation_review_label"] == "necessary"
    assert metadata["review_label_source"] == "explicit"
    assert metadata["review_label_detail"] == "center_replan_candidate"
    assert metadata["review_pre_window_start_timestamp"] == 6.5
    assert metadata["review_pre_window_end_timestamp"] == 8.5
    assert metadata["review_post_window_end_timestamp"] == 15.0
    assert metadata["secondary_assist_requested"] is False
    assert metadata["secondary_takeover_candidate"] is False
    assert metadata["active_degradation_necessity_label"] == "necessary"
    assert metadata["secondary_takeover_necessity_label"] == "inconclusive"
    assert metadata["secondary_plan_pending_duration_s"] is None
    assert metadata["secondary_lifecycle"][0]["heartbeat"] == 9.9
    assert abs(metadata["secondary_lifecycle"][0]["video_cue_freshness"] - 0.1) < 1e-9
    assert metadata["secondary_lifecycle"][0]["secondary_available"] is True
    assert metadata["secondary_diagnostic_node_id"] == "SEC-1"
    assert metadata["secondary_diagnostic_link_fresh"] is True


def test_adapter_marks_unnecessary_active_degradation_as_false_trigger_candidate() -> None:
    result = _immediate_readiness_adapter().evaluate(
        timestamp=10.0,
        trigger_timestamp=8.5,
        review_label="unnecessary",
        track=_track(position_sigma_m=60.0),
        association_metrics=_metrics(ambiguity=0.8, id_switches=1, continuity=0.55),
        plan=_plan(created_at=5.0),
        assignment=_assignment(),
        terminal_association=_terminal(decision_state="reacquire", confidence=0.35, ambiguity=0.9),
        observed_global_track_id="G-TGT-002",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )
    metadata = result.record.to_event_metadata()

    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert metadata["active_degradation_false_trigger_candidate"] is True
    assert metadata["active_degradation_false_trigger_reason"] == (
        "center_plan_hard_invalidation"
    )
    assert "d5_terminal_id_mismatch" in metadata["hard_risk_factors"]
