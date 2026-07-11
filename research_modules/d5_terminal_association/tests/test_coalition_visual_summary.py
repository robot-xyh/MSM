from __future__ import annotations

from d5_terminal_association import (
    TerminalAssociation,
    TerminalObservationBus,
    summarize_coalition_visual_completion,
)


def _binding(
    resource_id: str,
    role: str,
    *,
    plan_version: int = 9,
) -> dict[str, object]:
    return {
        "resource_id": resource_id,
        "assigned_global_track_id": "G1",
        "plan_id": "plan-v2",
        "plan_version": plan_version,
        "coalition_id": "C-G1",
        "coalition_version": 4,
        "member_role": role,
        "coordination_mode": "hybrid",
        "primary_resource_count": 2,
        "required_resource_count": 3,
        "authorization_state": "authorized",
        "binding_state": "standby" if role == "reserve" else "active",
    }


def _association(
    resource_id: str,
    role: str,
    frame_index: int,
    *,
    decision_state: str = "locked",
    visual_match_state: str | None = None,
    plan_version: int = 9,
    metadata: dict[str, object] | None = None,
) -> TerminalAssociation:
    association_metadata = {
        "frame_index": frame_index,
        "projection_timestamp": float(frame_index),
        "execution_gate_pass": decision_state == "locked",
        "visual_match_decision_state": visual_match_state or decision_state,
        "measurement_resource_id": resource_id,
        "measurement_camera_id": f"{resource_id}/front_rgb",
        "projection_camera_id": f"{resource_id}/front_rgb",
        **(metadata or {}),
    }
    return TerminalAssociation(
        assigned_global_track_id="G1",
        local_track_id=f"mot-{resource_id}-{frame_index}",
        association_confidence=0.95,
        ambiguity_score=0.05,
        friend_conflict_state="none",
        decision_state=decision_state,
        assignment_version=2,
        resource_id=resource_id,
        plan_id="plan-v2",
        plan_version=plan_version,
        coalition_id="C-G1",
        coalition_version=4,
        member_role=role,
        wave_id=1 if role == "reserve" else 0,
        required_resource_count=3,
        coordination_mode="hybrid",
        activation_state="standby" if role == "reserve" else "active",
        metadata=association_metadata,
    )


def _bindings() -> tuple[dict[str, object], ...]:
    return (
        _binding("R1", "primary"),
        _binding("R2", "primary"),
        _binding("R3", "reserve"),
    )


def _stable_primary_history() -> tuple[TerminalAssociation, ...]:
    return (
        _association("R1", "primary", 1),
        _association("R2", "primary", 1),
    )


def test_hybrid_two_primary_one_reserve_reports_visual_completion() -> None:
    bus = TerminalObservationBus()
    for association in (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2),
        _association(
            "R3",
            "reserve",
            2,
            decision_state="hold",
            visual_match_state="locked",
        ),
    ):
        bus.publish_terminal_association(
            resource_id=association.resource_id or "",
            source_node_id="d3_central",
            link_type="c2_direct",
            timestamp=2.0,
            terminal_association=association,
            camera_id=f"{association.resource_id}/front_rgb",
            frame_id=f"frame-{association.resource_id}-2",
        )

    summary = bus.coalition_visual_summary(
        _bindings(),
        historical_associations=_stable_primary_history(),
    )

    assert summary.primary_required_count == 2
    assert summary.primary_locked_resource_ids == ("R1", "R2")
    assert summary.primary_lock_complete is True
    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.coalition_visual_consensus is True
    assert summary.planned_cooperative_lock is True
    assert summary.duplicate_terminal_lock_risk is False
    assert summary.visual_png_authorized_resource_ids == ("R1", "R2")
    assert summary.metadata["reserve_visual_png_authorized"] is False


def test_d3_style_bindings_infer_total_demand_from_coalition_members() -> None:
    bindings = tuple(
        {key: value for key, value in binding.items() if key != "required_resource_count"}
        for binding in _bindings()
    )
    current = (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2),
        _association(
            "R3",
            "reserve",
            2,
            decision_state="hold",
            visual_match_state="locked",
        ),
    )

    summary = summarize_coalition_visual_completion(
        bindings,
        current,
        _stable_primary_history(),
    )

    assert summary.primary_required_count == 2
    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.coalition_visual_consensus is True


def test_accumulated_bus_uses_latest_frame_and_earlier_frames_for_stability() -> None:
    bus = TerminalObservationBus()
    for frame_index in (1, 2):
        for resource_id in ("R1", "R2"):
            association = _association(resource_id, "primary", frame_index)
            bus.publish_terminal_association(
                resource_id=resource_id,
                source_node_id="d3_central",
                link_type="c2_direct",
                timestamp=float(frame_index),
                terminal_association=association,
                frame_id=f"frame-{frame_index}",
            )

    summary = bus.coalition_visual_summary(_bindings())

    assert summary.stable_lock_frame_count_by_resource == {"R1": 2, "R2": 2}
    assert summary.primary_lock_complete is True


def test_missing_one_primary_never_completes_with_ready_reserve() -> None:
    current = (
        _association("R1", "primary", 2),
        _association(
            "R3",
            "reserve",
            2,
            decision_state="hold",
            visual_match_state="locked",
        ),
    )

    summary = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
    )

    assert summary.primary_locked_resource_ids == ("R1",)
    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.primary_lock_complete is False
    assert summary.coalition_visual_consensus is False
    assert summary.visual_png_authorized_resource_ids == ()


def test_reserve_only_visual_match_is_readiness_not_consensus() -> None:
    current = (
        _association(
            "R3",
            "reserve",
            2,
            decision_state="hold",
            visual_match_state="locked",
        ),
    )

    summary = summarize_coalition_visual_completion(_bindings(), current)

    assert summary.primary_locked_resource_ids == ()
    assert summary.primary_lock_complete is False
    assert summary.reserve_ready_resource_ids == ("R3",)
    assert summary.coalition_visual_consensus is False
    assert summary.planned_cooperative_lock is False


def test_primary_lock_requires_two_consecutive_frames_for_each_resource() -> None:
    current = (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2),
    )
    unstable_history = (
        _association("R1", "primary", 1),
        _association("R2", "primary", 1, decision_state="hold"),
    )

    unstable = summarize_coalition_visual_completion(
        _bindings(),
        current,
        unstable_history,
    )
    stable = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
    )

    assert unstable.primary_locked_resource_ids == ("R1", "R2")
    assert unstable.stable_lock_frame_count_by_resource == {"R1": 2, "R2": 1}
    assert unstable.primary_lock_complete is False
    assert unstable.reason == "primary_lock_stability_incomplete"
    assert stable.stable_lock_frame_count_by_resource == {"R1": 2, "R2": 2}
    assert stable.primary_lock_complete is True


def test_current_plan_version_conflict_blocks_consensus_and_cooperative_lock() -> None:
    current = (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2, plan_version=8),
    )

    summary = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
    )

    assert summary.primary_lock_complete is False
    assert summary.coalition_visual_consensus is False
    assert summary.planned_cooperative_lock is False
    assert summary.duplicate_terminal_lock_risk is True
    assert summary.coalition_conflict_state == "coalition_or_plan_version_mismatch"
    assert summary.metadata["version_conflict_resource_ids"] == ("R2",)


def test_borrowed_secondary_bbox_cannot_make_reserve_ready() -> None:
    borrowed = _association(
        "R3",
        "reserve",
        2,
        decision_state="hold",
        visual_match_state="locked",
        metadata={
            "measurement_resource_id": "Secondary1",
            "measurement_camera_id": "Secondary1/down_rgb",
            "projection_camera_id": "R3/front_rgb",
            "recon_cue_used": True,
        },
    )

    summary = summarize_coalition_visual_completion(_bindings(), (borrowed,))

    assert summary.reserve_ready_resource_ids == ()
    assert summary.metadata["secondary_cue_policy"] == "search_or_registration_only"


def test_unbound_execution_lock_preserves_over_demand_safety() -> None:
    current = (
        _association("R1", "primary", 2),
        _association("R2", "primary", 2),
        _association("R3", "reserve", 2),
        _association("R4", "primary", 2),
    )

    summary = summarize_coalition_visual_completion(
        _bindings(),
        current,
        _stable_primary_history(),
    )

    assert summary.primary_lock_complete is False
    assert summary.coalition_visual_consensus is False
    assert summary.duplicate_terminal_lock_risk is True
    assert summary.coalition_conflict_state == "member_count_exceeds_demand"
    assert summary.excess_lock_resource_ids == ("R4",)
