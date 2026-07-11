from __future__ import annotations

import numpy as np
import pytest

from d5_terminal_association import (
    Assignment,
    CameraModel,
    GlobalTrack,
    LocalVisualTrack,
    TerminalAssociation,
    TerminalAssociator,
    TerminalObservationBus,
    annotate_visual_png_handoff,
)


def _locked(
    resource_id: str,
    *,
    coalition_id: str | None = "C-G1",
    coalition_version: int | None = 4,
    plan_id: str | None = "plan-v2",
    plan_version: int | None = 9,
    required_resource_count: int = 3,
) -> TerminalAssociation:
    return TerminalAssociation(
        assigned_global_track_id="G1",
        local_track_id=f"mot-{resource_id}",
        association_confidence=0.95,
        ambiguity_score=0.05,
        friend_conflict_state="none",
        decision_state="locked",
        assignment_version=2,
        resource_id=resource_id,
        plan_id=plan_id,
        plan_version=plan_version,
        coalition_id=coalition_id,
        coalition_version=coalition_version,
        member_role="primary",
        wave_id=0,
        required_resource_count=required_resource_count,
        coordination_mode="simultaneous",
        arrival_window_start_s=4.0,
        arrival_window_end_s=6.0,
        activation_state="active",
        metadata={"execution_gate_pass": True},
    )


def _publish(bus: TerminalObservationBus, resource_id: str, association: TerminalAssociation) -> None:
    bus.publish_terminal_association(
        resource_id=resource_id,
        source_node_id="d3_central",
        link_type="c2_direct",
        timestamp=5.0,
        terminal_association=association,
        camera_id="front_rgb",
        frame_id=f"{resource_id}/front_rgb/5",
    )


def test_three_authorized_coalition_locks_are_legal_cooperative_support() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2", "R3"):
        _publish(bus, resource_id, _locked(resource_id))

    summary = bus.cross_view_associations()[0]

    assert summary.global_track_id == "G1"
    assert summary.supporting_resource_ids == ("R1", "R2", "R3")
    assert summary.duplicate_terminal_lock_risk is False
    assert summary.duplicate_lock_resource_ids == ()
    assert summary.planned_cooperative_lock is True
    assert summary.reason == "planned_cooperative_lock"
    assert summary.coalition_id == "C-G1"
    assert summary.coalition_version == 4
    assert summary.required_resource_count == 3
    assert summary.excess_lock_resource_ids == ()


def test_fourth_lock_exceeding_demand_is_conflict() -> None:
    bus = TerminalObservationBus()
    for resource_id in ("R1", "R2", "R3", "R4"):
        _publish(bus, resource_id, _locked(resource_id))

    summary = bus.cross_view_associations()[0]

    assert summary.duplicate_terminal_lock_risk is True
    assert summary.planned_cooperative_lock is False
    assert summary.reason == "coalition_member_over_demand"
    assert summary.coalition_conflict_state == "member_count_exceeds_demand"
    assert summary.excess_lock_resource_ids == ("R4",)
    assert summary.duplicate_lock_resource_ids == ("R1", "R2", "R3", "R4")


@pytest.mark.parametrize(
    ("override", "value"),
    (("coalition_id", "C-OTHER"), ("coalition_version", 5), ("plan_version", 10)),
)
def test_different_coalition_or_version_is_conflict(override: str, value: object) -> None:
    bus = TerminalObservationBus()
    _publish(bus, "R1", _locked("R1"))
    kwargs = {override: value}
    _publish(bus, "R2", _locked("R2", **kwargs))

    summary = bus.cross_view_associations()[0]

    assert summary.duplicate_terminal_lock_risk is True
    assert summary.planned_cooperative_lock is False
    assert summary.reason == "coalition_contract_conflict"
    assert summary.coalition_conflict_state == "coalition_or_plan_version_mismatch"


def test_inactive_reserve_visual_match_is_held_and_blocks_visual_png() -> None:
    camera = CameraModel(
        K=np.array([[100.0, 0.0, 320.0], [0.0, 100.0, 240.0], [0.0, 0.0, 1.0]]),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
    )
    track = GlobalTrack(
        global_track_id="G1",
        position=np.array([0.0, 0.0, 10.0]),
        covariance=np.eye(3) * 0.01,
        timestamp=5.0,
        track_version=2,
    )
    local = LocalVisualTrack(
        local_track_id="mot-R4",
        center_px=np.array([320.0, 240.0]),
        bbox=(300.0, 220.0, 340.0, 260.0),
        quality=0.95,
        mot_history_length=5,
        timestamp=5.0,
    )
    assignment = Assignment(
        "G1",
        assignment_version=2,
        resource_id="R4",
        plan_id="plan-v2",
        plan_version=9,
        coalition_id="C-G1",
        coalition_version=4,
        member_role="reserve",
        wave_id=1,
        required_resource_count=3,
        coordination_mode="hybrid",
        arrival_window_start_s=4.0,
        arrival_window_end_s=6.0,
        activation_state="standby",
    )

    association = TerminalAssociator().decide(
        assignment,
        [track],
        [local],
        camera=camera,
        current_time=5.0,
    )

    assert association.local_track_id == "mot-R4"
    assert association.decision_state == "hold"
    assert association.reason == "coalition_member_not_activated"
    assert association.metadata["visual_match_decision_state"] == "locked"
    assert association.metadata["execution_gate_pass"] is False
    assert association.member_role == "reserve"
    assert association.activation_state == "standby"

    primary_assignment = Assignment(
        "G1",
        assignment_version=2,
        resource_id="R1",
        plan_id="plan-v2",
        plan_version=9,
        coalition_id="C-G1",
        coalition_version=4,
        member_role="primary",
        wave_id=0,
        required_resource_count=3,
        coordination_mode="hybrid",
        arrival_window_start_s=4.0,
        arrival_window_end_s=6.0,
        activation_state="active",
    )
    primary = TerminalAssociator().decide(
        primary_assignment,
        [track],
        [local],
        camera=camera,
        current_time=5.0,
    )
    assert primary.decision_state == "locked"
    assert primary.metadata["execution_gate_pass"] is True
    assert primary.member_role == "primary"
    assert primary.wave_id == 0

    handoff = annotate_visual_png_handoff(
        association,
        local_track_history=[local, local, local, local],
        image_size=(640, 480),
        range_to_assigned_track_m=20.0,
        closing_speed_mps=5.0,
        detection_latency_s=0.05,
        measurement_age_s=0.0,
        los_rate_px_s=(0.0, 0.0),
    )
    assert handoff.metadata["visual_png_gate_pass"] is False
    assert "execution_gate:coalition_member_not_activated" in handoff.metadata[
        "visual_png_handoff_blockers"
    ]


def test_primary_wave_zero_and_k1_legacy_semantics_remain_active() -> None:
    single = TerminalObservationBus()
    _publish(
        single,
        "R1",
        _locked(
            "R1",
            coalition_id=None,
            coalition_version=None,
            plan_id="legacy-plan",
            plan_version=1,
            required_resource_count=1,
        ),
    )
    single_summary = single.cross_view_associations()[0]
    assert single_summary.duplicate_terminal_lock_risk is False
    assert single_summary.planned_cooperative_lock is False

    _publish(
        single,
        "R2",
        _locked(
            "R2",
            coalition_id=None,
            coalition_version=None,
            plan_id="legacy-plan",
            plan_version=1,
            required_resource_count=1,
        ),
    )
    duplicate_summary = single.cross_view_associations()[0]
    assert duplicate_summary.duplicate_terminal_lock_risk is True
    assert duplicate_summary.coalition_conflict_state == "missing_coalition_contract"
