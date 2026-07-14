from __future__ import annotations

from dataclasses import replace

from d5_terminal_association import (
    TerminalAssociation,
    per_primary_terminal_evidence,
)


def _locked_primary() -> TerminalAssociation:
    return TerminalAssociation(
        assigned_global_track_id="GT-001",
        local_track_id="front/yolov8_bytetrack:track:7",
        association_confidence=0.95,
        ambiguity_score=0.02,
        friend_conflict_state="none",
        decision_state="locked",
        assignment_version=4,
        plan_id="plan-4",
        plan_version=4,
        authorization_state="authorized",
        resource_id="INT-01",
        coalition_id="coalition-T001",
        coalition_version=2,
        member_role="primary",
        required_resource_count=2,
        activation_state="executing",
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
        local_track_state="measured",
        metadata={
            "visual_match_decision_state": "locked",
            "execution_gate_pass": True,
        },
    )


def test_active_primary_can_report_independent_lock_without_other_primary() -> None:
    association = _locked_primary()

    evidence = per_primary_terminal_evidence(
        association,
        terminal_authorization_scope="per_primary",
    )

    assert evidence.independently_locked is True
    assert evidence.rejection_reasons == ()
    assert evidence.assigned_global_track_id == association.assigned_global_track_id
    record = evidence.to_dict()
    assert record["terminal_authorization_scope"] == "per_primary"
    assert record["arrival_coordination_required"] is False
    assert record["requires_other_primary_same_frame_lock"] is False
    assert record["grants_control_authority"] is False
    assert record["global_track_id_rewrite_count"] == 0


def test_per_primary_evidence_remains_fail_closed_for_safety_conflicts() -> None:
    association = replace(
        _locked_primary(),
        friend_conflict_state="verified_friend_overlap",
        duplicate_terminal_lock_risk=True,
        metadata={
            "visual_match_decision_state": "locked",
            "execution_gate_pass": False,
        },
    )

    evidence = per_primary_terminal_evidence(
        association,
        terminal_authorization_scope="per_primary",
    )

    assert evidence.independently_locked is False
    assert "friend_conflict_present" in evidence.rejection_reasons
    assert "duplicate_terminal_lock_risk" in evidence.rejection_reasons
    assert "execution_gate_rejected" in evidence.rejection_reasons


def test_reserve_or_unversioned_binding_cannot_claim_independent_primary_lock() -> None:
    reserve = replace(
        _locked_primary(),
        member_role="reserve",
        activation_state="standby",
        plan_id=None,
        plan_version=None,
    )

    evidence = per_primary_terminal_evidence(
        reserve,
        terminal_authorization_scope="per_primary",
    )

    assert evidence.independently_locked is False
    assert "member_role_not_active_primary" in evidence.rejection_reasons
    assert "primary_not_active" in evidence.rejection_reasons
    assert "versioned_plan_binding_missing" in evidence.rejection_reasons


def test_coalition_scope_does_not_masquerade_as_per_primary_authorization() -> None:
    coalition_contract = replace(
        _locked_primary(),
        terminal_authorization_scope="coalition",
        arrival_coordination_required=True,
    )
    evidence = per_primary_terminal_evidence(
        coalition_contract,
        terminal_authorization_scope="coalition",
        arrival_coordination_required=True,
    )

    assert evidence.independently_locked is False
    assert evidence.rejection_reasons == (
        "terminal_authorization_scope_not_per_primary",
        "arrival_coordination_still_required",
    )


def test_per_primary_scope_still_requires_arrival_coordination_to_be_disabled() -> None:
    evidence = per_primary_terminal_evidence(
        replace(_locked_primary(), arrival_coordination_required=True)
    )

    assert evidence.independently_locked is False
    assert evidence.rejection_reasons == ("arrival_coordination_still_required",)


def test_helper_argument_cannot_override_association_contract() -> None:
    evidence = per_primary_terminal_evidence(
        _locked_primary(),
        terminal_authorization_scope="coalition",
        arrival_coordination_required=True,
    )

    assert evidence.independently_locked is False
    assert evidence.rejection_reasons == (
        "terminal_authorization_scope_mismatch",
        "arrival_coordination_contract_mismatch",
    )


def test_per_primary_evidence_rejects_noncurrent_center_binding() -> None:
    evidence = per_primary_terminal_evidence(
        _locked_primary(),
        terminal_authorization_scope="per_primary",
        expected_resource_id="INT-02",
        expected_assigned_global_track_id="GT-009",
        expected_plan_id="plan-5",
        expected_plan_version=5,
        expected_coalition_id="coalition-T009",
        expected_coalition_version=3,
    )

    assert evidence.independently_locked is False
    assert evidence.rejection_reasons == (
        "resource_binding_mismatch",
        "global_track_binding_mismatch",
        "plan_id_mismatch",
        "plan_version_mismatch",
        "coalition_id_mismatch",
        "coalition_version_mismatch",
    )
