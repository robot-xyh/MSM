from __future__ import annotations

import pytest

from d5_terminal_association import (
    TerminalAssociation,
    summarize_cooperative_visual_funnel,
)


def _binding(resource_id: str) -> dict[str, object]:
    return {
        "resource_id": resource_id,
        "assigned_global_track_id": "G1",
        "target_id": "T001",
        "plan_id": "plan-G1",
        "plan_version": 9,
        "active_plan_owner": "center",
        "owner_node_id": "C2",
        "coalition_id": "C-G1",
        "coalition_version": 4,
        "member_role": "primary",
        "coordination_mode": "hybrid",
        "primary_resource_count": 2,
        "required_resource_count": 2,
        "authorization_state": "authorized",
        "binding_state": "committed",
        "terminal_authorization_scope": "per_primary",
        "arrival_coordination_required": False,
    }


def _association(
    resource_id: str,
    frame_index: int,
    *,
    assigned_global_track_id: str = "G1",
    decision_state: str = "locked",
    reason: str = "unique_candidate_inside_gate",
    local_track_id: str | None = "mot",
    projection_valid: bool = True,
    gate_pass_count: int = 1,
    friend_conflict_state: str = "none",
    duplicate_terminal_lock_risk: bool = False,
    bbox_edge_clipped: bool = False,
    metadata: dict[str, object] | None = None,
) -> TerminalAssociation:
    local_id = None if local_track_id is None else f"{local_track_id}-{resource_id}"
    return TerminalAssociation(
        assigned_global_track_id=assigned_global_track_id,
        local_track_id=local_id,
        association_confidence=0.95 if decision_state == "locked" else 0.45,
        ambiguity_score=0.05 if decision_state == "locked" else 0.75,
        friend_conflict_state=friend_conflict_state,
        decision_state=decision_state,
        assignment_version=2,
        reason=reason,
        plan_id="plan-G1",
        plan_version=9,
        resource_id=resource_id,
        coalition_id="C-G1",
        coalition_version=4,
        member_role="primary",
        required_resource_count=2,
        coordination_mode="hybrid",
        activation_state="committed",
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
        measurement_timestamp=frame_index * 0.1,
        arrival_timestamp=frame_index * 0.1 + 0.02,
        bbox_edge_clipped=bbox_edge_clipped,
        duplicate_terminal_lock_risk=duplicate_terminal_lock_risk,
        metadata={
            "frame_index": frame_index,
            "projection_timestamp": frame_index * 0.1,
            "projection_valid": projection_valid,
            "projected_px": [320.0, 240.0] if projection_valid else None,
            "gate_pass_count": gate_pass_count,
            "selected_pair": {
                "projected_px": [320.0, 240.0] if projection_valid else None,
                "gate_pass": gate_pass_count > 0,
            },
            "execution_gate_pass": decision_state == "locked",
            "visual_match_decision_state": decision_state,
            "measurement_resource_id": resource_id,
            "measurement_camera_id": f"{resource_id}/front_rgb",
            "projection_camera_id": f"{resource_id}/front_rgb",
            **(metadata or {}),
        },
    )


def _summary(second_primary: TerminalAssociation):
    current = (
        _association("R1", 1),
        _association("R1", 2),
        second_primary,
    )
    return summarize_cooperative_visual_funnel(
        (_binding("R1"), _binding("R2")),
        current,
    )


@pytest.mark.parametrize(
    ("second_primary", "expected_category"),
    (
        (
            _association(
                "R2",
                2,
                decision_state="reacquire",
                reason="no_current_local_visual_detection",
                local_track_id=None,
                projection_valid=False,
                gate_pass_count=0,
            ),
            "not_visible",
        ),
        (
            _association(
                "R2",
                2,
                decision_state="reacquire",
                reason="projection_invalid:outside_image",
                projection_valid=False,
                gate_pass_count=0,
            ),
            "projection_invalid",
        ),
        (
            _association(
                "R2",
                2,
                decision_state="reacquire",
                reason="no_local_track_inside_projection_gate",
                gate_pass_count=0,
            ),
            "geometry_gate_rejected",
        ),
        (
            _association(
                "R2",
                2,
                bbox_edge_clipped=True,
                metadata={
                    "d5_live_visual_funnel": {
                        "first_failure_stage": "bbox_stability",
                        "first_failure_reason": "bbox_edge_clipped",
                        "visual_match_decision_state": "locked",
                    }
                },
            ),
            "bbox_unstable_or_edge_clipped",
        ),
        (
            _association(
                "R2",
                2,
                decision_state="ambiguous",
                reason="insufficient_best_second_margin",
                gate_pass_count=2,
            ),
            "candidate_not_unique",
        ),
        (
            _association(
                "R2",
                2,
                decision_state="ambiguous",
                reason="terminal_visual_evidence_expired",
                metadata={"visual_evidence_fresh": False},
            ),
            "timestamp_or_measurement_stale",
        ),
        (
            _association("R2", 2, assigned_global_track_id="G2"),
            "assignment_or_identity_contract_mismatch",
        ),
        (
            _association(
                "R2",
                2,
                decision_state="hold",
                reason="verified_friend_overlap_inside_gate",
                friend_conflict_state="verified_friend_overlap",
            ),
            "friend_or_duplicate_lock_conflict",
        ),
        (
            _association(
                "R2",
                2,
                duplicate_terminal_lock_risk=True,
            ),
            "friend_or_duplicate_lock_conflict",
        ),
        (
            _association("R2", 2),
            "associated_but_stable_lock_incomplete",
        ),
    ),
)
def test_second_primary_passive_failure_categories(
    second_primary: TerminalAssociation,
    expected_category: str,
) -> None:
    summary = _summary(second_primary)
    target = summary.target_summaries[0]
    row = {
        item.resource_id: item for item in target.resource_diagnostics
    }["R2"]
    payload = summary.to_dict()

    assert row.failure_category == expected_category
    assert target.second_primary_resource_id == "R2"
    assert target.second_primary_failure_category == expected_category
    assert summary.failure_category_counts[expected_category] >= 1
    assert summary.second_primary_failure_category_counts == {
        expected_category: 1
    }
    assert row.global_track_id == "G1"
    assert payload["online_truth_use_count"] == 0
    assert payload["global_track_id_rewrite_count"] == 0


def test_second_primary_complete_category_uses_existing_stability_evidence() -> None:
    summary = summarize_cooperative_visual_funnel(
        (_binding("R1"), _binding("R2")),
        tuple(
            _association(resource_id, frame_index)
            for frame_index in (1, 2)
            for resource_id in ("R1", "R2")
        ),
    )

    target = summary.target_summaries[0]
    assert target.second_primary_failure_category == "complete"
    assert summary.second_primary_failure_category_counts == {"complete": 1}
    assert summary.failure_category_counts == {"complete": 2}
