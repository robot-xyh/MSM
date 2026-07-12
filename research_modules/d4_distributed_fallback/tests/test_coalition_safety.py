from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from d4_distributed_fallback import (
    C2Health,
    CenterReplanStatus,
    CoalitionSafetyAction,
    D4ArbitrationAdapter,
    DegradationAction,
)
from d4_distributed_fallback.coordinator import FailoverCoordinator
from d4_distributed_fallback.models import ConfidenceBand, TrackSummary
from d4_distributed_fallback.network import SimulatedNetwork


TRACK_ID = "G-COALITION-1"
MEMBER_IDS = ("INT-1", "INT-2", "INT-3")


def _track() -> SimpleNamespace:
    return SimpleNamespace(
        global_track_id=TRACK_ID,
        covariance=np.diag([4.0, 4.0, 4.0, 1.0, 1.0, 1.0]),
        timestamp=10.0,
        last_update_time=9.9,
        metadata={"coverage_cell": "cell-1", "track_version": 7},
    )


def _assignment(
    resource_id: str,
    *,
    plan_version: int = 4,
    coalition_version: int = 2,
    required_resource_count: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        target_id=TRACK_ID,
        resource_id=resource_id,
        cost=0.2 + 0.1 * MEMBER_IDS.index(resource_id),
        plan_version=plan_version,
        coalition_id="coalition-1",
        coalition_version=coalition_version,
        member_role="primary",
        wave_id=0,
        required_resource_count=required_resource_count,
    )


def _plan(
    *,
    plan_version: int = 4,
    coalition_version: int = 2,
    assignment_coalition_version: int | None = None,
) -> SimpleNamespace:
    member_version = (
        coalition_version
        if assignment_coalition_version is None
        else assignment_coalition_version
    )
    assignments = tuple(
        _assignment(
            resource_id,
            plan_version=plan_version,
            coalition_version=member_version,
        )
        for resource_id in MEMBER_IDS
    )
    coalition = SimpleNamespace(
        coalition_id="coalition-1",
        version=coalition_version,
        target_id=TRACK_ID,
        state="committed",
        coordination_mode="simultaneous",
        required_resource_count=3,
        assigned_resource_count=3,
        shortfall=0,
        complete=True,
        members=tuple(
            SimpleNamespace(
                resource_id=resource_id,
                member_role="primary",
                wave_id=0,
                executable=True,
            )
            for resource_id in MEMBER_IDS
        ),
    )
    return SimpleNamespace(
        plan_id="d3-plan-v2",
        version=plan_version,
        plan_schema="assignment_plan_v2",
        created_at=9.8,
        assignments=assignments,
        coalitions=(coalition,),
        decision_state="accepted",
    )


def _terminal() -> SimpleNamespace:
    return SimpleNamespace(
        resource_id="INT-1",
        assigned_global_track_id=TRACK_ID,
        decision_state="locked",
        association_confidence=0.95,
        ambiguity_score=0.02,
        friend_conflict_state="none",
        coalition_id="coalition-1",
        coalition_version=2,
    )


def _cross_view(locked_ids: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        duplicate_terminal_lock_risk=True,
        duplicate_lock_resource_ids=locked_ids,
        ambiguity_score=0.02,
        support_count=len(locked_ids),
    )


def _recovered_cross_view(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "global_track_id": TRACK_ID,
        "plan_id": "d3-plan-v2",
        "plan_version": 4,
        "coalition_id": "coalition-1",
        "coalition_version": 2,
        "primary_required_count": 3,
        "primary_locked_resource_ids": MEMBER_IDS,
        "primary_lock_complete": True,
        "coalition_visual_consensus": True,
        "planned_cooperative_lock": True,
        "duplicate_terminal_lock_risk": False,
        "coalition_conflict_state": "none",
        "coalition_commit_required": False,
        "coalition_commit_valid": True,
        "coalition_commit_conflict_reasons": (),
        "ambiguity_score": 0.02,
        "support_count": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _evaluate(
    *,
    plan: SimpleNamespace,
    c2_health: C2Health,
    locked_ids: tuple[str, ...] = MEMBER_IDS,
    expected_plan_version: int = 4,
    center_replan_status: CenterReplanStatus | None = None,
):
    return D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=SimpleNamespace(
            latest_association_ambiguity=0.02,
            id_switch_count=0,
            duplicate_assignment_count=0,
            track_continuity=1.0,
        ),
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=_terminal(),
        cross_view_summary=_cross_view(locked_ids),
        c2_health=c2_health,
        expected_plan_version=expected_plan_version,
        center_replan_status=center_replan_status,
    )


def test_k1_center_failure_keeps_existing_distributed_fallback_behavior() -> None:
    assignment = SimpleNamespace(
        target_id=TRACK_ID,
        resource_id="INT-1",
        cost=0.2,
        plan_version=4,
        coalition_id="independent-1",
        coalition_version=1,
        required_resource_count=1,
    )
    plan = SimpleNamespace(
        plan_id="d3-k1",
        version=4,
        created_at=9.8,
        decision_state="accepted",
        assignments=(assignment,),
        coalitions=(
            SimpleNamespace(
                coalition_id="independent-1",
                version=1,
                target_id=TRACK_ID,
                coordination_mode="independent",
                required_resource_count=1,
                assigned_resource_count=1,
                complete=True,
                members=(
                    SimpleNamespace(
                        resource_id="INT-1",
                        member_role="primary",
                        executable=True,
                    ),
                ),
            ),
        ),
    )

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        plan=plan,
        assignment=assignment,
        terminal_association=_terminal(),
        c2_health=C2Health.FAILED,
    )

    assert result.coalition_safety.coalition_required is False
    assert result.coalition_safety.safety_action == CoalitionSafetyAction.NOT_APPLICABLE
    assert result.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED


def test_k3_valid_center_plan_allows_authorized_multi_resource_locks() -> None:
    result = _evaluate(plan=_plan(), c2_health=C2Health.NORMAL)

    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert result.terminal_association.duplicate_terminal_lock is False
    assert result.coalition_safety.safety_action == CoalitionSafetyAction.CONTINUE_CENTER
    assert result.coalition_safety.safe_to_execute is True
    assert result.coalition_safety.legal_multi_resource_lock is True
    assert result.coalition_safety.authorized_resource_ids == MEMBER_IDS
    assert result.coalition_safety.locked_resource_ids == MEMBER_IDS
    json.dumps(result.record.to_event_metadata())


def test_k3_center_failure_blocks_secondary_and_distributed_fallback() -> None:
    result = _evaluate(plan=_plan(), c2_health=C2Health.FAILED)

    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert result.decision.reason == "coalition_fallback_unsupported"
    assert result.coalition_safety.safety_action == CoalitionSafetyAction.HOLD_OR_REVOKE
    assert result.coalition_safety.fallback_supported is False
    assert result.coalition_safety.candidate_action == "degrade_to_distributed"
    assert result.coalition_safety.gated_action == "hold_for_review"
    metadata = result.record.to_event_metadata()
    assert metadata["coalition_safety_action"] == "hold_or_revoke"
    assert "coalition_fallback_unsupported" in metadata["hard_risk_factors"]


def test_k3_center_available_redirects_active_distributed_candidate_to_replan() -> None:
    plan = _plan()
    terminal = SimpleNamespace(
        resource_id="INT-1",
        assigned_global_track_id=TRACK_ID,
        observed_global_track_id="OTHER-TRACK",
        decision_state="reacquire",
        association_confidence=0.25,
        ambiguity_score=0.9,
        friend_conflict_state="none",
        coalition_id="coalition-1",
        coalition_version=2,
    )

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=SimpleNamespace(
            latest_association_ambiguity=0.8,
            id_switch_count=1,
            duplicate_assignment_count=0,
            track_continuity=0.5,
        ),
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=terminal,
        observed_global_track_id="OTHER-TRACK",
        consecutive_non_locked_frames=3,
        consecutive_mismatch_frames=2,
        c2_health=C2Health.NORMAL,
        secondary_nodes=(),
        expected_plan_version=4,
    )

    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.decision.reason == (
        "coalition_fallback_unsupported_request_center_replan"
    )
    assert result.coalition_safety.safety_action == (
        CoalitionSafetyAction.REQUEST_CENTER_REPLAN
    )
    assert result.coalition_safety.candidate_action == "degrade_to_distributed"
    assert result.coalition_safety.gated_action == "request_center_replan"
    assert result.coalition_safety.safe_to_execute is False
    assert "coalition_atomic_fallback_unavailable" in (
        result.coalition_safety.conflict_reasons
    )
    metadata = result.record.to_event_metadata()
    assert metadata["coalition_candidate_action"] == "degrade_to_distributed"
    assert metadata["coalition_gated_action"] == "request_center_replan"


def test_replan_ack_cools_down_new_soft_risk_until_boundary_but_not_hard_risk() -> None:
    plan = _plan()
    persistent_terminal = SimpleNamespace(
        resource_id="INT-1",
        assigned_global_track_id=TRACK_ID,
        decision_state="reacquire",
        association_confidence=0.95,
        ambiguity_score=0.02,
        friend_conflict_state="none",
        coalition_id="coalition-1",
        coalition_version=2,
    )
    uncertain_track = SimpleNamespace(
        global_track_id=TRACK_ID,
        covariance=np.diag([3600.0, 2500.0, 9.0, 1.0, 1.0, 1.0]),
        timestamp=10.0,
        last_update_time=9.9,
        metadata={"coverage_cell": "cell-1", "track_version": 7},
    )
    common = {
        "timestamp": 10.0,
        "track": uncertain_track,
        "association_metrics": SimpleNamespace(
            latest_association_ambiguity=0.02,
            id_switch_count=0,
            duplicate_assignment_count=0,
            track_continuity=1.0,
        ),
        "plan": plan,
        "assignment": plan.assignments[0],
        "terminal_association": persistent_terminal,
        "consecutive_non_locked_frames": 4,
        "c2_health": C2Health.NORMAL,
        "expected_plan_version": 4,
    }

    adapter = D4ArbitrationAdapter()
    assert adapter.arbiter.config.center_replan_cooldown_s == 2.0
    initial = adapter.evaluate(**common)
    assert initial.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert "terminal_persistent_disagreement" in initial.decision.risk_factors

    status = CenterReplanStatus(
        request_id="persistent-replan-1",
        target_id=TRACK_ID,
        coalition_id="coalition-1",
        coalition_version=2,
        risk_signature=initial.decision.risk_factors,
        state="acknowledged_no_change",
        requested_at=9.5,
        resolved_at=10.0,
    )
    acknowledged = adapter.evaluate(
        **common,
        center_replan_status=status,
    )

    assert acknowledged.decision.action == DegradationAction.CONTINUE_CENTER
    assert acknowledged.decision.reason == "center_replan_acknowledged_no_change"
    assert acknowledged.decision.terminal_consistent is False
    assert acknowledged.record.center_replan_suppressed_duplicate is True

    soft_metrics = SimpleNamespace(
        latest_association_ambiguity=0.4,
        id_switch_count=0,
        duplicate_assignment_count=0,
        track_continuity=1.0,
    )
    soft_risk_during_cooldown = adapter.evaluate(
        **{
            **common,
            "timestamp": 10.5,
            "association_metrics": soft_metrics,
            "center_replan_status": status,
        }
    )

    assert soft_risk_during_cooldown.decision.action == DegradationAction.CONTINUE_CENTER
    assert "d2_association_ambiguity_medium" in (
        soft_risk_during_cooldown.decision.risk_factors
    )
    assert soft_risk_during_cooldown.record.center_replan_risk_worsened is True
    assert soft_risk_during_cooldown.record.center_replan_cooldown_active is True
    assert soft_risk_during_cooldown.record.center_replan_cooldown_until == 12.0
    assert soft_risk_during_cooldown.record.center_replan_suppressed_duplicate is True

    friend_terminal = SimpleNamespace(
        **{
            **vars(persistent_terminal),
            "friend_conflict_state": "verified_friend_overlap",
        }
    )
    friend_conflict = adapter.evaluate(
        **{
            **common,
            "timestamp": 10.5,
            "terminal_association": friend_terminal,
            "center_replan_status": status,
        }
    )
    version_conflict = adapter.evaluate(
        **{
            **common,
            "timestamp": 10.5,
            "expected_plan_version": 5,
            "center_replan_status": status,
        }
    )

    assert friend_conflict.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert friend_conflict.record.center_replan_bypass_reason == "hard_safety_risk"
    assert version_conflict.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert version_conflict.record.center_replan_bypass_reason == "hard_safety_risk"

    reopened_at_boundary = adapter.evaluate(
        **{
            **common,
            "timestamp": 12.0,
            "association_metrics": soft_metrics,
            "center_replan_status": status,
        }
    )

    assert reopened_at_boundary.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert reopened_at_boundary.record.center_replan_risk_worsened is True
    assert reopened_at_boundary.record.center_replan_cooldown_active is False
    assert reopened_at_boundary.record.center_replan_bypass_reason == "risk_worsened"


def test_k3_rejects_fourth_unauthorized_lock_member() -> None:
    result = _evaluate(
        plan=_plan(),
        c2_health=C2Health.NORMAL,
        locked_ids=(*MEMBER_IDS, "INT-4"),
    )

    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert result.decision.reason == "coalition_membership_conflict"
    assert result.coalition_safety.unauthorized_resource_ids == ("INT-4",)
    assert "coalition_lock_count_exceeded" in result.coalition_safety.conflict_reasons


def test_k3_coalition_conflict_bypasses_center_replan_cooldown() -> None:
    initial = _evaluate(
        plan=_plan(),
        c2_health=C2Health.NORMAL,
        locked_ids=(*MEMBER_IDS, "INT-4"),
    )
    status = CenterReplanStatus(
        request_id="coalition-replan-1",
        target_id=TRACK_ID,
        coalition_id="coalition-1",
        coalition_version=2,
        risk_signature=initial.decision.risk_factors,
        state="pending",
        requested_at=9.5,
    )

    result = _evaluate(
        plan=_plan(),
        c2_health=C2Health.NORMAL,
        locked_ids=(*MEMBER_IDS, "INT-4"),
        center_replan_status=status,
    )

    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert result.record.center_replan_bypass_reason == "hard_safety_risk"


def test_k3_rejects_stale_plan_and_coalition_versions() -> None:
    stale_plan = _evaluate(
        plan=_plan(plan_version=4),
        c2_health=C2Health.NORMAL,
        expected_plan_version=5,
    )
    stale_coalition = _evaluate(
        plan=_plan(coalition_version=2, assignment_coalition_version=1),
        c2_health=C2Health.NORMAL,
    )

    assert stale_plan.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert stale_plan.decision.reason == "coalition_plan_version_stale"
    assert stale_plan.coalition_safety.stale_plan_version is True
    assert stale_coalition.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert stale_coalition.decision.reason == "coalition_version_stale"
    assert stale_coalition.coalition_safety.stale_coalition_version is True


def test_pending_soft_replan_converges_when_current_coalition_consensus_recovers() -> None:
    plan = _plan()
    coalition = SimpleNamespace(
        **{
            **vars(plan.coalitions[0]),
            "members": tuple(
                SimpleNamespace(
                    resource_id=resource_id,
                    member_role="primary" if index < 2 else "reserve",
                    wave_id=0,
                    executable=True,
                )
                for index, resource_id in enumerate(MEMBER_IDS)
            ),
        }
    )
    plan = SimpleNamespace(**{**vars(plan), "coalitions": (coalition,)})
    adapter = D4ArbitrationAdapter()
    initial = adapter.evaluate(
        timestamp=9.5,
        track=SimpleNamespace(
            **{
                **vars(_track()),
                "covariance": np.diag([3600.0, 2500.0, 9.0, 1.0, 1.0, 1.0]),
            }
        ),
        association_metrics=SimpleNamespace(
            latest_association_ambiguity=0.02,
            id_switch_count=0,
            duplicate_assignment_count=0,
            track_continuity=1.0,
        ),
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        expected_plan_version=4,
    )
    assert initial.decision.action == DegradationAction.REQUEST_CENTER_REPLAN

    pending = CenterReplanStatus(
        request_id="soft-coalition-replan-1",
        target_id=TRACK_ID,
        coalition_id="coalition-1",
        coalition_version=2,
        risk_signature=("d5_terminal_confidence_low",),
        state="pending",
        requested_at=9.5,
    )
    results = []
    for assignment in plan.assignments[:2]:
        terminal = SimpleNamespace(
            **{
                **vars(_terminal()),
                "resource_id": assignment.resource_id,
            }
        )
        results.append(
            adapter.evaluate(
                timestamp=10.0,
                track=_track(),
                association_metrics=SimpleNamespace(
                    latest_association_ambiguity=0.02,
                    id_switch_count=0,
                    duplicate_assignment_count=0,
                    track_continuity=1.0,
                ),
                plan=plan,
                assignment=assignment,
                terminal_association=terminal,
                cross_view_summary=_recovered_cross_view(
                    primary_required_count=2,
                    primary_locked_resource_ids=MEMBER_IDS[:2],
                    support_count=2,
                ),
                c2_health=C2Health.NORMAL,
                expected_plan_version=4,
                expected_coalition_version=2,
                center_replan_status=pending,
            )
        )

    assert {result.decision.action for result in results} == {
        DegradationAction.CONTINUE_CENTER
    }
    assert all(
        result.decision.reason == "center_replan_pending_coalition_recovered"
        for result in results
    )
    assert all(result.coalition_safety.center_consensus_recovered for result in results)
    assert all(result.record.center_replan_coalition_recovered for result in results)
    assert all(
        result.record.center_replan_resolution_hint == "acknowledged_no_change"
        for result in results
    )
    assert all(
        result.coalition_safety.locked_resource_ids == MEMBER_IDS[:2]
        for result in results
    )


def test_recovered_coalition_consensus_does_not_bypass_duplicate_hard_risk() -> None:
    plan = _plan()
    pending = CenterReplanStatus(
        request_id="soft-coalition-replan-2",
        target_id=TRACK_ID,
        coalition_id="coalition-1",
        coalition_version=2,
        risk_signature=("d5_terminal_confidence_low",),
        state="pending",
        requested_at=9.5,
    )

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=SimpleNamespace(
            latest_association_ambiguity=0.02,
            id_switch_count=0,
            duplicate_assignment_count=1,
            track_continuity=1.0,
        ),
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=_terminal(),
        cross_view_summary=_recovered_cross_view(),
        c2_health=C2Health.NORMAL,
        expected_plan_version=4,
        expected_coalition_version=2,
        center_replan_status=pending,
    )

    assert result.coalition_safety.center_consensus_recovered is True
    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert "d2_duplicate_track_observed" in result.decision.risk_factors
    assert result.record.center_replan_coalition_recovered is False
    assert result.record.center_replan_bypass_reason == "hard_safety_risk"


def test_incomplete_commit_cannot_claim_current_coalition_recovery() -> None:
    plan = _plan()
    pending = CenterReplanStatus(
        request_id="soft-coalition-replan-3",
        target_id=TRACK_ID,
        coalition_id="coalition-1",
        coalition_version=2,
        risk_signature=("d5_terminal_confidence_low",),
        state="pending",
        requested_at=9.5,
    )

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=_terminal(),
        cross_view_summary=_recovered_cross_view(
            coalition_commit_required=True,
            coalition_commit_valid=False,
            coalition_commit_state="collecting_acks",
            coalition_commit_required_member_ids=MEMBER_IDS,
            coalition_commit_acked_member_ids=MEMBER_IDS[:2],
            coalition_commit_conflict_reasons=("coalition_commit_missing_ack",),
        ),
        c2_health=C2Health.NORMAL,
        expected_plan_version=4,
        expected_coalition_version=2,
        center_replan_status=pending,
    )

    assert result.coalition_safety.center_consensus_recovered is False
    assert "coalition_commit_incomplete" in result.coalition_safety.conflict_reasons
    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert result.record.center_replan_bypass_reason == "hard_safety_risk"


def test_stale_visual_coalition_version_cannot_resolve_pending_replan() -> None:
    plan = _plan()
    pending = CenterReplanStatus(
        request_id="soft-coalition-replan-4",
        target_id=TRACK_ID,
        coalition_id="coalition-1",
        coalition_version=2,
        risk_signature=("d5_terminal_confidence_low",),
        state="pending",
        requested_at=9.5,
    )

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=_terminal(),
        cross_view_summary=_recovered_cross_view(coalition_version=1),
        c2_health=C2Health.NORMAL,
        expected_plan_version=4,
        expected_coalition_version=2,
        center_replan_status=pending,
    )

    assert result.coalition_safety.center_consensus_recovered is False
    assert "coalition_visual_coalition_version_stale" in (
        result.coalition_safety.conflict_reasons
    )
    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert result.record.center_replan_bypass_reason == "hard_safety_risk"


def test_center_failure_cannot_use_visual_consensus_to_resolve_pending_replan() -> None:
    plan = _plan()
    pending = CenterReplanStatus(
        request_id="soft-coalition-replan-5",
        target_id=TRACK_ID,
        coalition_id="coalition-1",
        coalition_version=2,
        risk_signature=("d5_terminal_confidence_low",),
        state="pending",
        requested_at=9.5,
    )

    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=_terminal(),
        cross_view_summary=_recovered_cross_view(),
        c2_health=C2Health.FAILED,
        expected_plan_version=4,
        expected_coalition_version=2,
        center_replan_status=pending,
    )

    assert result.coalition_safety.center_consensus_recovered is False
    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert result.record.center_replan_bypass_reason == "center_failed"


def test_k3_coordinator_never_runs_single_winner_cbba() -> None:
    coordinator = FailoverCoordinator("INT-1", ["INT-2", "INT-3"])
    coordinator.health = C2Health.FAILED
    task = TrackSummary(
        TRACK_ID,
        "cell-1",
        0.2,
        ConfidenceBand.HIGH,
        source_count=3,
        required_resource_count=3,
        coalition_id="coalition-1",
        coalition_version=2,
        coalition_complete=True,
    )
    network = SimulatedNetwork(node_ids=list(MEMBER_IDS))

    result = coordinator.plan_degraded([task], [], network, now_s=10.0)

    assert result.assignments == {}
    assert result.final_views["reason"]["state"] == "coalition_fallback_unsupported"
    assert result.final_views["coalition_safety"]["safety_action"] == "hold_or_revoke"
