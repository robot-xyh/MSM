from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from d4_distributed_fallback import (
    AvailabilityBand,
    C2Health,
    CommBand,
    D4ArbitrationAdapter,
    DegradationAction,
    DegradationMode,
    DistributedVisualEvidenceSummary,
    NodeRole,
    ResourceSummary,
    SecondaryTakeoverPlanState,
    TrackSummary,
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
) -> SimpleNamespace:
    return SimpleNamespace(
        latest_association_ambiguity=ambiguity,
        id_switch_count=id_switches,
        duplicate_assignment_count=0,
        track_continuity=continuity,
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
) -> SimpleNamespace:
    return SimpleNamespace(
        resource_id="INT-01",
        assigned_global_track_id="G-TGT-001",
        decision_state=decision_state,
        association_confidence=confidence,
        ambiguity_score=ambiguity,
        friend_conflict_state=friend_state,
    )


def _secondary(available: bool = True) -> ResourceSummary:
    return ResourceSummary(
        node_id="SEC-1",
        capability_class="tethered_recon",
        availability_band=AvailabilityBand.HIGH if available else AvailabilityBand.NONE,
        comm_band=CommBand.GOOD,
        takeover_priority=10,
        lease_epoch=5,
        epoch=1,
        node_role=NodeRole.SECONDARY_RECON,
        coordinator_only=True,
        coverage_cell="cell-north",
        heartbeat_timestamp_s=9.9,
        heartbeat_stale_after_s=2.0,
    )


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
    assert metadata["review_label"] == "continue_center"
    assert metadata["global_track_id"] == "G-TGT-001"
    assert metadata["plan_version"] == 3


def test_adapter_keeps_soft_margin_and_low_terminal_confidence_as_observe_more() -> None:
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
    assert result.decision.reason == "terminal_transient_observe_more"
    assert result.record.review_label == "observe_more_not_degradation"
    assert "d3_assignment_cost_margin_low" in result.record.risk_factors
    assert "d5_terminal_confidence_low" in result.record.risk_factors


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


def test_adapter_routes_duplicate_terminal_lock_to_secondary_assist() -> None:
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
    assert result.decision.action == DegradationAction.REQUEST_SECONDARY_ASSIST
    assert result.decision.target_node_id == "SEC-1"
    assert "d5_duplicate_terminal_lock" in result.decision.risk_factors


def test_adapter_prefers_distributed_when_secondary_link_is_stale() -> None:
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
    assert result.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert result.decision.target_node_id is None


def test_adapter_selects_secondary_when_persistent_mismatch_has_fresh_secondary_link() -> None:
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
        communication_records=[fresh_link],
    )

    assert result.record.communication_fresh is True
    assert result.record.secondary_available is True
    assert result.secondary_lifecycle[0].video_cue_freshness_s is not None
    assert abs(result.secondary_lifecycle[0].video_cue_freshness_s - 0.1) < 1e-9
    assert result.decision.mode == DegradationMode.ACTIVE_DEGRADATION
    assert result.decision.action == DegradationAction.DEGRADE_TO_SECONDARY
    assert result.decision.target_node_id == "SEC-1"


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
        c2_health=C2Health.NORMAL,
        secondary_nodes=[_secondary()],
    )

    pending = D4ArbitrationAdapter().evaluate(**kwargs)
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
    assert pending_metadata["secondary_supersedes_plan_id"] == "d3-plan-test"
    assert pending_metadata["secondary_supersedes_plan_version"] == 3

    active = D4ArbitrationAdapter().evaluate(
        **kwargs,
        secondary_plan_id="secondary-plan-004",
        secondary_plan_version=4,
        secondary_plan_active=True,
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
    result = D4ArbitrationAdapter().evaluate(
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
    assert metadata["selected_coordinator"] == "secondary_node"
    assert metadata["coverage_cell"] == "cell-north"
    assert metadata["trigger_reason"] == "terminal_persistent_disagreement"
    assert metadata["trigger_timestamp"] == 8.5
    assert metadata["decision_timestamp"] == 10.0
    assert metadata["review_label"] == "necessary"
    assert metadata["secondary_lifecycle"][0]["heartbeat"] == 9.9
    assert abs(metadata["secondary_lifecycle"][0]["video_cue_freshness"] - 0.1) < 1e-9
    assert metadata["secondary_lifecycle"][0]["secondary_available"] is True
