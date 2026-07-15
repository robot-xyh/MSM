from __future__ import annotations

import json

from d5_terminal_association import (
    LocalVisualTrack,
    TerminalAssociation,
    TerminalObservation,
    TerminalObservationBus,
    summarize_coalition_visual_completion,
    summarize_cooperative_visual_funnel,
)


def _binding(
    resource_id: str,
    role: str,
    *,
    global_track_id: str = "G1",
    target_id: str = "T001",
    plan_version: int = 9,
    coalition_version: int = 4,
    primary_count: int = 2,
    required_count: int = 3,
    terminal_authorization_scope: str = "coalition",
    arrival_coordination_required: bool = True,
) -> dict[str, object]:
    return {
        "resource_id": resource_id,
        "assigned_global_track_id": global_track_id,
        "target_id": target_id,
        "plan_id": f"plan-{global_track_id}",
        "plan_version": plan_version,
        "active_plan_owner": "center",
        "owner_node_id": "C2",
        "coalition_id": f"C-{global_track_id}",
        "coalition_version": coalition_version,
        "member_role": role,
        "coordination_mode": "hybrid" if required_count > 1 else "independent",
        "primary_resource_count": primary_count,
        "required_resource_count": required_count,
        "authorization_state": "authorized",
        "binding_state": "standby" if role == "reserve" else "committed",
        "terminal_authorization_scope": terminal_authorization_scope,
        "arrival_coordination_required": arrival_coordination_required,
    }


def _bindings() -> tuple[dict[str, object], ...]:
    return (
        _binding("R1", "primary"),
        _binding("R2", "primary"),
        _binding("R3", "reserve"),
    )


def _association(
    resource_id: str,
    frame_index: int,
    *,
    role: str = "primary",
    decision_state: str = "locked",
    reason: str = "unique_candidate_inside_gate",
    local_track_id: str | None = None,
    plan_version: int = 9,
    coalition_version: int = 4,
    friend_conflict_state: str = "none",
    projection_valid: bool = True,
    gate_accepted: bool = True,
    global_track_id: str = "G1",
    target_id: str = "T001",
    primary_count: int = 2,
    required_count: int = 3,
    terminal_authorization_scope: str = "coalition",
    arrival_coordination_required: bool = True,
    metadata: dict[str, object] | None = None,
) -> TerminalAssociation:
    local_track_id = (
        f"mot-{resource_id}"
        if local_track_id is None and decision_state != "reacquire"
        else local_track_id
    )
    return TerminalAssociation(
        assigned_global_track_id=global_track_id,
        local_track_id=local_track_id,
        association_confidence=0.94 if decision_state == "locked" else 0.2,
        ambiguity_score=0.06 if decision_state == "locked" else 0.9,
        friend_conflict_state=friend_conflict_state,
        decision_state=decision_state,
        assignment_version=2,
        reason=reason,
        resource_id=resource_id,
        plan_id=f"plan-{global_track_id}",
        plan_version=plan_version,
        coalition_id=f"C-{global_track_id}",
        coalition_version=coalition_version,
        member_role=role,
        required_resource_count=required_count,
        coordination_mode="hybrid" if required_count > 1 else "independent",
        activation_state="standby" if role == "reserve" else "committed",
        terminal_authorization_scope=terminal_authorization_scope,
        arrival_coordination_required=arrival_coordination_required,
        measurement_timestamp=float(frame_index) * 0.1,
        arrival_timestamp=float(frame_index) * 0.1 + 0.02,
        metadata={
            "frame_index": frame_index,
            "projection_timestamp": float(frame_index) * 0.1,
            "projection_valid": projection_valid,
            "projected_px": [320.0, 240.0] if projection_valid else None,
            "gate_pass_count": int(gate_accepted),
            "selected_pair": {
                "projected_px": [320.0, 240.0],
                "gate_pass": gate_accepted,
            },
            "execution_gate_pass": decision_state == "locked",
            "visual_match_decision_state": decision_state,
            "measurement_resource_id": resource_id,
            "measurement_camera_id": f"{resource_id}/front_rgb",
            "projection_camera_id": f"{resource_id}/front_rgb",
            "target_label_for_offline_test_only": target_id,
            **(metadata or {}),
        },
    )


def _rows(summary) -> dict[str, object]:
    return {
        item.resource_id: item
        for item in summary.target_summaries[0].resource_diagnostics
    }


def test_dual_primary_different_fov_reports_second_primary_visible_breakpoint() -> None:
    current = (
        _association("R1", 2),
        _association(
            "R2",
            2,
            decision_state="reacquire",
            reason="no_local_track_inside_projection_gate",
            local_track_id=None,
        ),
    )

    summary = summarize_cooperative_visual_funnel(_bindings(), current)
    target = summary.target_summaries[0]
    rows = _rows(summary)

    assert rows["R1"].visible is True
    assert rows["R2"].visible is False
    assert rows["R2"].first_failure_stage == "visible"
    assert target.second_primary_resource_id == "R2"
    assert target.second_primary_first_failure_stage == "visible"
    assert target.cooperative_completion is False
    assert summary.funnel_counts["active_primary"] == 2
    assert summary.funnel_counts["visible"] == 1


def test_individual_stability_without_common_window_fails_common_stage() -> None:
    current = tuple(
        _association(resource_id, frame_index)
        for resource_id, frame_indices in (("R1", (1, 2)), ("R2", (2, 3)))
        for frame_index in frame_indices
    )

    summary = summarize_cooperative_visual_funnel(_bindings(), current)
    target = summary.target_summaries[0]
    rows = _rows(summary)

    assert rows["R1"].stable_lock_frame_count == 2
    assert rows["R2"].stable_lock_frame_count == 2
    assert target.common_lock_frame_count == 1
    assert target.cooperative_completion is False
    assert target.reason == "common_lock_window_insufficient"
    assert rows["R2"].first_failure_stage == "common_lock_window"


def test_per_primary_contract_completes_without_common_lock_window() -> None:
    bindings = tuple(
        _binding(
            resource_id,
            role,
            terminal_authorization_scope="per_primary",
            arrival_coordination_required=False,
        )
        for resource_id, role in (
            ("R1", "primary"),
            ("R2", "primary"),
            ("R3", "reserve"),
        )
    )
    current = tuple(
        _association(
            resource_id,
            frame_index,
            terminal_authorization_scope="per_primary",
            arrival_coordination_required=False,
        )
        for resource_id, frame_indices in (("R1", (1, 2)), ("R2", (3, 4)))
        for frame_index in frame_indices
    ) + (
        _association(
            "R3",
            4,
            role="reserve",
            decision_state="hold",
            reason="coalition_member_not_activated",
            terminal_authorization_scope="per_primary",
            arrival_coordination_required=False,
        ),
    )

    summary = summarize_cooperative_visual_funnel(bindings, current)
    target = summary.target_summaries[0]
    rows = _rows(summary)
    payload = summary.to_dict()

    assert target.common_lock_frame_count == 0
    assert target.common_lock_window_required is False
    assert target.cooperative_completion is True
    assert target.reason == "per_primary_visual_completion"
    assert rows["R1"].first_failure_stage == "complete"
    assert rows["R2"].first_failure_stage == "complete"
    assert rows["R1"].reject_reason == "per_primary_visual_completion"
    assert rows["R2"].reject_reason == "per_primary_visual_completion"
    assert rows["R3"].first_failure_stage == "standby_reserve"
    assert payload["metadata"]["completion_policy_by_global_track_id"] == {
        "G1": "independent_per_primary"
    }
    assert payload["funnel_counts"]["completion_eligible"] == 2
    assert payload["online_truth_use_count"] == 0
    assert payload["global_track_id_rewrite_count"] == 0


def test_per_primary_owner_and_scope_mismatch_are_contract_first_failures() -> None:
    bindings = tuple(
        _binding(
            resource_id,
            role,
            terminal_authorization_scope="per_primary",
            arrival_coordination_required=False,
        )
        for resource_id, role in (
            ("R1", "primary"),
            ("R2", "primary"),
            ("R3", "reserve"),
        )
    )
    owner_mismatch = _association(
        "R1",
        2,
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
        metadata={"active_plan_owner": "secondary", "owner_node_id": "SEC-01"},
    )
    scope_mismatch = _association("R2", 2)

    summary = summarize_cooperative_visual_funnel(
        bindings,
        (owner_mismatch, scope_mismatch),
    )
    rows = _rows(summary)

    assert rows["R1"].first_failure_stage == "contract"
    assert rows["R1"].reject_reason == "plan_owner_mismatch"
    assert rows["R2"].first_failure_stage == "contract"
    assert rows["R2"].reject_reason == "terminal_authorization_contract_mismatch"
    assert rows["R1"].plan_owner == "center"
    assert rows["R1"].owner_node_id == "C2"
    assert rows["R1"].plan_version == 9
    assert summary.completed_target_count == 0


def test_plan_version_mismatch_is_contract_failure_not_local_rebinding() -> None:
    current = (
        _association("R1", 2),
        _association("R2", 2, plan_version=8),
    )

    summary = summarize_cooperative_visual_funnel(_bindings(), current)
    row = _rows(summary)["R2"]

    assert row.association_contract_matches is False
    assert row.locked is False
    assert row.first_failure_stage == "contract"
    assert row.reject_reason == "plan_or_coalition_version_mismatch"
    assert row.global_track_id == "G1"
    assert summary.target_summaries[0].cooperative_completion is False


def test_friend_conflict_reaches_gate_but_blocks_terminal_lock() -> None:
    current = (
        _association("R1", 2),
        _association(
            "R2",
            2,
            decision_state="hold",
            reason="verified_friend_overlap_inside_gate",
            friend_conflict_state="verified_friend_overlap",
        ),
    )

    summary = summarize_cooperative_visual_funnel(_bindings(), current)
    row = _rows(summary)["R2"]

    assert row.visible is True
    assert row.projected is True
    assert row.gate_accepted is True
    assert row.locked is False
    assert row.first_failure_stage == "locked"
    assert row.friend_conflict_state == "verified_friend_overlap"
    assert row.reject_reason == "verified_friend_overlap_inside_gate"


def test_stable_common_lock_positive_excludes_reserve_and_truth_metadata() -> None:
    current = tuple(
        _association(
            resource_id,
            frame_index,
            metadata={"actor_name": "offline-only", "object_id": 999},
        )
        for frame_index in (1, 2)
        for resource_id in ("R1", "R2")
    ) + (
        _association(
            "R3",
            2,
            role="reserve",
            decision_state="hold",
            reason="coalition_member_not_activated",
        ),
    )

    summary = summarize_cooperative_visual_funnel(_bindings(), current)
    target = summary.target_summaries[0]
    rows = _rows(summary)
    payload = summary.to_dict()

    assert target.common_lock_frame_count == 2
    assert target.common_lock_window_start_s == 0.1
    assert target.common_lock_window_end_s == 0.2
    assert target.cooperative_completion is True
    assert rows["R1"].first_failure_stage == "complete"
    assert rows["R2"].first_failure_stage == "complete"
    assert rows["R3"].active_primary is False
    assert rows["R3"].first_failure_stage == "standby_reserve"
    assert summary.active_primary_count == 2
    assert summary.funnel_counts["locked"] == 2
    assert payload["online_truth_use_count"] == 0
    assert payload["global_track_id_rewrite_count"] == 0
    assert "actor_name" not in json.dumps(payload)
    assert "object_id" not in json.dumps(payload)

    bus = TerminalObservationBus()
    for association in current:
        bus.publish_terminal_association(
            resource_id=association.resource_id or "",
            source_node_id="center",
            link_type="c2_direct",
            timestamp=float(association.metadata["projection_timestamp"]),
            terminal_association=association,
        )
    assert bus.cooperative_visual_funnel(_bindings()).completed_target_count == 1


def test_safe_cross_version_lock_tail_counts_toward_common_window() -> None:
    bus = TerminalObservationBus()
    first_bindings = _bindings()
    for resource_id in ("R1", "R2"):
        association = _association(resource_id, 1)
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="center",
            link_type="c2_direct",
            timestamp=0.1,
            terminal_association=association,
            frame_id="episode:0001",
        )
    first = bus.cooperative_visual_funnel(first_bindings)
    assert first.target_summaries[0].common_lock_frame_count == 1

    next_bindings = tuple(
        _binding(
            resource_id,
            role,
            plan_version=10,
            coalition_version=5,
        )
        for resource_id, role in (("R1", "primary"), ("R2", "primary"), ("R3", "reserve"))
    )
    for resource_id in ("R1", "R2"):
        association = _association(
            resource_id,
            2,
            plan_version=10,
            coalition_version=5,
        )
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="center",
            link_type="c2_direct",
            timestamp=0.2,
            terminal_association=association,
            frame_id="episode:0002",
        )

    summary = bus.cooperative_visual_funnel(next_bindings)
    target = summary.target_summaries[0]

    assert target.common_lock_frame_count == 2
    assert target.cooperative_completion is True
    assert target.common_lock_window_start_s == 0.1
    assert target.common_lock_window_end_s == 0.2
    transition = summary.metadata[
        "primary_membership_transition_by_global_track_id"
    ]["G1"]
    assert transition["membership_changed"] is False
    assert transition["previous_plan_version"] == 9


def test_primary_membership_change_does_not_bridge_common_window() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="center",
            link_type="c2_direct",
            timestamp=0.1,
            terminal_association=_association(resource_id, 1),
            frame_id="episode:0001",
        )
    bus.cooperative_visual_funnel(_bindings())

    next_bindings = (
        _binding("R1", "primary", plan_version=10, coalition_version=5),
        _binding("R4", "primary", plan_version=10, coalition_version=5),
        _binding("R2", "reserve", plan_version=10, coalition_version=5),
    )
    for resource_id in ("R1", "R4"):
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id="center",
            link_type="c2_direct",
            timestamp=0.2,
            terminal_association=_association(
                resource_id,
                2,
                plan_version=10,
                coalition_version=5,
            ),
            frame_id="episode:0002",
        )

    summary = bus.cooperative_visual_funnel(next_bindings)
    target = summary.target_summaries[0]
    transition = summary.metadata[
        "primary_membership_transition_by_global_track_id"
    ]["G1"]

    assert target.common_lock_frame_count == 1
    assert target.cooperative_completion is False
    assert transition["membership_changed"] is True
    assert transition["added_primary_resource_ids"] == ["R4"]
    assert transition["removed_primary_resource_ids"] == ["R2"]


def test_real_replay_style_failures_are_exposed_without_truth_identity() -> None:
    current = (
        _association(
            "R1",
            42,
            decision_state="ambiguous",
            reason="insufficient_best_second_margin",
            metadata={
                "camera_geometry": {
                    "geometry_valid": False,
                    "geometry_source": "unavailable",
                    "geometry_unavailable_reasons": ["camera_geometry_not_provided"],
                },
                "candidate_pair_logs": [
                    {
                        "projected_px": [346.2, 131.5],
                        "gate_pass": True,
                        "mahalanobis_d2": 0.5,
                    }
                ],
            },
        ),
        _association(
            "R2",
            42,
            decision_state="reacquire",
            reason="terminal_visual_evidence_expired",
            local_track_id=None,
            metadata={
                "projection_valid": False,
                "gate_pass_count": 0,
            },
        ),
    )

    summary = summarize_cooperative_visual_funnel(_bindings(), current)
    coalition_summary = summarize_coalition_visual_completion(_bindings(), current)
    completion = summary.target_summaries[0]
    rows = _rows(summary)
    payload = summary.to_dict()

    assert rows["R1"].first_failure_stage == "locked"
    assert rows["R1"].reject_reason == "insufficient_best_second_margin"
    assert rows["R2"].first_failure_stage == "visible"
    assert rows["R2"].reject_reason == "terminal_visual_evidence_expired"
    assert completion.cooperative_completion is False
    current_failures = coalition_summary.metadata["current_primary_failure_diagnostics"]
    assert current_failures["R1"]["first_failure_stage"] == "locked"
    assert current_failures["R1"]["failure_reason"] == "insufficient_best_second_margin"
    assert current_failures["R2"]["first_failure_stage"] == "visible"
    assert current_failures["R2"]["failure_reason"] == "terminal_visual_evidence_expired"
    assert payload["online_truth_use_count"] == 0
    assert payload["global_track_id_rewrite_count"] == 0
    assert "actor_name" not in json.dumps(payload)
    assert "object_id" not in json.dumps(payload)


def test_dynamic_target_and_resource_counts_and_local_only_visibility() -> None:
    bindings_with_counts = _bindings() + (
        _binding(
            "R4",
            "primary",
            global_track_id="G2",
            target_id="T002",
            primary_count=1,
            required_count=1,
        ),
    )
    bindings = tuple(
        {key: value for key, value in binding.items() if key != "required_resource_count"}
        for binding in bindings_with_counts
    )
    local_only = TerminalObservation(
        resource_id="R4",
        source_node_id="R4",
        link_type="mesh",
        timestamp=0.2,
        local_track=LocalVisualTrack(
            local_track_id="mot-R4-2",
            center_px=[300.0, 220.0],
            timestamp=0.2,
            mot_history_length=2,
        ),
        metadata={"assigned_global_track_id": "G2"},
    )

    summary = summarize_cooperative_visual_funnel(bindings, (local_only,))
    targets = {item.global_track_id: item for item in summary.target_summaries}
    g2_row = targets["G2"].resource_diagnostics[0]

    assert summary.target_count == 2
    assert summary.resource_binding_count == 4
    assert summary.active_primary_count == 3
    assert targets["G1"].primary_required_count == 2
    assert targets["G2"].primary_required_count == 1
    assert g2_row.visible is True
    assert g2_row.projected is False
    assert g2_row.first_failure_stage == "projected"


def test_fallback_coalition_missing_ack_rejects_all_primary_completion() -> None:
    bindings = tuple({**binding, "coalition_epoch": 7} for binding in _bindings())
    current = (
        _association("R1", 2),
        _association("R2", 2),
    )
    commit = {
        "state": "committed",
        "epoch": 7,
        "lease_expires_at_s": 10.0,
        "coalition_id": "C-G1",
        "coalition_version": 4,
        "plan_id": "plan-G1",
        "plan_version": 9,
        "required_member_ids": ("R1", "R2", "R3"),
        "acked_member_ids": ("R1", "R3"),
        "fallback_active": True,
    }

    summary = summarize_cooperative_visual_funnel(
        bindings,
        current,
        coalition_commits={"G1": commit},
        current_time_s=2.0,
        center_failed=True,
        fallback_active=True,
    )
    rows = _rows(summary)

    assert rows["R1"].committed_member is False
    assert rows["R2"].committed_member is False
    assert rows["R1"].first_failure_stage == "contract"
    assert rows["R2"].first_failure_stage == "contract"
    assert summary.funnel_counts["visible"] == 0
    assert summary.funnel_counts["locked"] == 0
    assert summary.target_summaries[0].cooperative_completion is False
    assert summary.target_summaries[0].reason == "coalition_commit_member_ack_incomplete"
