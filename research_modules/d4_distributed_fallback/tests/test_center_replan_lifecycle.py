from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import numpy as np
import pytest

from d4_distributed_fallback import (
    C2Health,
    CenterReplanStatus,
    D4ArbitrationAdapter,
    DegradationAction,
    DegradationMode,
    build_center_replan_risk_signature,
)


def _track(position_sigma_m: float = 60.0) -> SimpleNamespace:
    return SimpleNamespace(
        global_track_id="G-TGT-001",
        covariance=np.diag(
            [
                position_sigma_m**2,
                (position_sigma_m * 0.8) ** 2,
                9.0,
                1.0,
                1.0,
                1.0,
            ]
        ),
        timestamp=10.0,
        last_update_time=9.9,
        metadata={"coverage_cell": "cell-north"},
    )


def _plan(
    version: int = 3,
    *,
    created_at: float = 9.8,
    last_evaluated_at_s: float | None = None,
    stale_after_s: float | None = None,
) -> SimpleNamespace:
    metadata = {}
    if last_evaluated_at_s is not None:
        metadata["last_evaluated_at_s"] = last_evaluated_at_s
    return SimpleNamespace(
        plan_id=f"plan-{version}",
        version=version,
        created_at=created_at,
        stale_after_s=stale_after_s,
        decision_state="accepted",
        metadata=metadata,
        assignments=(
            SimpleNamespace(
                target_id="G-TGT-001",
                resource_id="INT-01",
                plan_version=version,
                cost=0.2,
            ),
        ),
    )


def _assignment(plan_version: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        target_id="G-TGT-001",
        resource_id="INT-01",
        plan_version=plan_version,
        cost=0.2,
    )


def _terminal(
    *,
    decision_state: str = "locked",
    friend_state: str = "none",
    duplicate_terminal_lock: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        resource_id="INT-01",
        assigned_global_track_id="G-TGT-001",
        decision_state=decision_state,
        association_confidence=0.92,
        ambiguity_score=0.04,
        friend_conflict_state=friend_state,
        duplicate_terminal_lock=duplicate_terminal_lock,
    )


def _evaluate(
    *,
    center_replan_status: CenterReplanStatus | None = None,
    c2_health: C2Health = C2Health.NORMAL,
    plan_version: int = 3,
    current_plan_version: int | None = None,
    id_switch_count: int = 0,
    terminal_state: str = "locked",
    friend_state: str = "none",
    duplicate_terminal_lock: bool = False,
    plan_created_at: float = 9.8,
    plan_last_evaluated_at_s: float | None = None,
    plan_stale_after_s: float | None = None,
):
    return D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        association_metrics=SimpleNamespace(
            latest_association_ambiguity=0.05,
            id_switch_count=id_switch_count,
            duplicate_assignment_count=0,
            track_continuity=0.96,
            truth_metrics_available=True,
            continuity_available=True,
        ),
        plan=_plan(
            plan_version,
            created_at=plan_created_at,
            last_evaluated_at_s=plan_last_evaluated_at_s,
            stale_after_s=plan_stale_after_s,
        ),
        assignment=_assignment(plan_version),
        terminal_association=_terminal(
            decision_state=terminal_state,
            friend_state=friend_state,
            duplicate_terminal_lock=duplicate_terminal_lock,
        ),
        c2_health=c2_health,
        current_plan_version=current_plan_version,
        center_replan_status=center_replan_status,
    )


def _status(
    state: str,
    risk_signature: tuple[str, ...],
    **overrides: object,
) -> CenterReplanStatus:
    values: dict[str, object] = {
        "request_id": "replan-001",
        "target_id": "G-TGT-001",
        "risk_signature": risk_signature,
        "state": state,
        "requested_at": 9.5,
    }
    values.update(overrides)
    return CenterReplanStatus(**values)


def test_center_replan_status_is_immutable_normalized_and_serializable() -> None:
    status = _status(
        "APPLIED",
        ("d1_track_uncertainty_high", "d1_covariance_trace_high", "d1_track_uncertainty_high"),
        resolved_at=9.9,
        resolved_plan_id="plan-4",
        resolved_plan_version=4,
    )

    assert status.state == "applied"
    assert status.risk_signature == (
        "d1_covariance_trace_high",
        "d1_track_uncertainty_high",
    )
    assert status.to_dict()["risk_signature"] == [
        "d1_covariance_trace_high",
        "d1_track_uncertainty_high",
    ]
    assert status.to_dict()["resolved_plan_version"] == 4
    with pytest.raises(FrozenInstanceError):
        status.state = "expired"  # type: ignore[misc]
    with pytest.raises(ValueError, match="center replan state"):
        _status("failed", ())


@pytest.mark.parametrize(
    ("state", "expected_reason"),
    [
        ("pending", "center_replan_pending"),
        ("acknowledged_no_change", "center_replan_acknowledged_no_change"),
        ("applied", "center_replan_applied"),
    ],
)
def test_non_worsening_replan_lifecycle_does_not_repeat_center_escalation(
    state: str,
    expected_reason: str,
) -> None:
    initial = _evaluate()
    status = _status(state, build_center_replan_risk_signature(initial.decision.risk_factors))

    result = _evaluate(center_replan_status=status)
    metadata = result.to_event_metadata()

    assert initial.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert result.decision.mode == DegradationMode.NONE
    assert result.decision.reason == expected_reason
    assert result.decision.risk_factors == initial.decision.risk_factors
    assert metadata["center_replan_suppressed_duplicate"] is True
    assert metadata["center_replan_status"]["request_id"] == "replan-001"


def test_acknowledged_no_change_keeps_d5_gate_independent_from_d4_action() -> None:
    initial = _evaluate(terminal_state="reacquire")
    status = _status(
        "acknowledged_no_change",
        build_center_replan_risk_signature(initial.decision.risk_factors),
    )

    result = _evaluate(center_replan_status=status, terminal_state="reacquire")

    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert result.decision.terminal_consistent is False
    assert result.terminal_association.decision_state.value == "reacquire"
    assert result.decision.risk_factors


def test_expired_request_allows_a_new_center_replan() -> None:
    initial = _evaluate()
    status = _status("expired", initial.decision.risk_factors, resolved_at=9.9)

    result = _evaluate(center_replan_status=status)

    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.record.center_replan_suppressed_duplicate is False
    assert result.record.center_replan_bypass_reason == "request_expired"


def test_applied_status_does_not_cool_down_until_resolved_plan_is_current() -> None:
    initial = _evaluate()
    status = _status(
        "applied",
        initial.decision.risk_factors,
        resolved_at=9.9,
        resolved_plan_id="plan-4",
        resolved_plan_version=4,
    )

    result = _evaluate(center_replan_status=status)

    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.record.center_replan_bypass_reason == "resolved_plan_not_current"


def test_pending_request_reopens_for_worsened_risk_at_cooldown_boundary() -> None:
    status = _status(
        "pending",
        ("d1_track_uncertainty_high",),
        requested_at=8.0,
    )

    result = _evaluate(center_replan_status=status)

    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.record.center_replan_risk_worsened is True
    assert result.record.center_replan_cooldown_active is False
    assert result.record.center_replan_bypass_reason == "risk_worsened"


@pytest.mark.parametrize(
    ("kwargs", "expected_factor"),
    [
        ({"current_plan_version": 4}, "d3_assignment_not_current"),
        ({"id_switch_count": 1}, "d2_id_switch_observed"),
    ],
)
def test_hard_safety_risk_bypasses_replan_cooldown(
    kwargs: dict[str, object],
    expected_factor: str,
) -> None:
    initial = _evaluate(**kwargs)
    status = _status("pending", initial.decision.risk_factors)

    result = _evaluate(center_replan_status=status, **kwargs)

    assert expected_factor in result.decision.risk_factors
    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.record.center_replan_bypass_reason == "hard_safety_risk"


def test_stale_activity_age_remains_a_hard_replan_cooldown_bypass() -> None:
    kwargs = {
        "plan_created_at": 0.0,
        "plan_last_evaluated_at_s": 5.0,
        "plan_stale_after_s": 4.0,
    }
    initial = _evaluate(**kwargs)
    status = _status("pending", initial.decision.risk_factors)

    result = _evaluate(center_replan_status=status, **kwargs)

    assert result.assignment_validity.plan_age_s == 5.0
    assert "d3_assignment_stale" in result.decision.risk_factors
    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert result.record.center_replan_bypass_reason == "hard_safety_risk"


def test_illegal_duplicate_lock_bypasses_replan_cooldown() -> None:
    initial = _evaluate(duplicate_terminal_lock=True)
    status = _status("pending", initial.decision.risk_factors)

    result = _evaluate(
        center_replan_status=status,
        duplicate_terminal_lock=True,
    )

    assert result.decision.action == DegradationAction.REQUEST_CENTER_REPLAN
    assert "d5_duplicate_terminal_lock" in result.decision.risk_factors
    assert result.record.center_replan_bypass_reason == "hard_safety_risk"


def test_friend_conflict_hold_is_never_replaced_by_replan_cooldown() -> None:
    initial = _evaluate(friend_state="verified_friend_overlap")
    status = _status("pending", initial.decision.risk_factors)

    result = _evaluate(
        center_replan_status=status,
        friend_state="verified_friend_overlap",
    )

    assert result.decision.action == DegradationAction.HOLD_FOR_REVIEW
    assert "terminal_friend_conflict" in result.decision.risk_factors
    assert result.record.center_replan_bypass_reason == "hard_safety_risk"


def test_center_failure_bypasses_replan_status_and_continues_fallback() -> None:
    initial = _evaluate()
    status = _status("pending", initial.decision.risk_factors)

    result = _evaluate(
        center_replan_status=status,
        c2_health=C2Health.FAILED,
    )

    assert result.decision.mode == DegradationMode.PASSIVE_FAILOVER
    assert result.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert result.record.center_replan_bypass_reason == "center_failed"
