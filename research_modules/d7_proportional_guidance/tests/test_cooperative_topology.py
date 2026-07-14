from __future__ import annotations

import pytest

from d7_proportional_guidance import (
    COOPERATIVE_TOPOLOGY_BOUNDARY,
    D4GuidancePermission,
    build_cooperative_guidance_topology,
    evaluate_terminal_png_contract,
    validate_cooperative_guidance_topology,
)


def test_m5_n2_topology_expands_two_primaries_one_reserve_and_k1() -> None:
    topology = build_cooperative_guidance_topology(
        resource_ids=("R1", "R2", "R3", "R4", "R5"),
        target_ids=("T001", "T002"),
        required_counts={"T001": 3, "T002": 1},
        coordination_mode={"T001": "hybrid", "T002": "independent"},
        primary_count=2,
        plan_id="plan-m5-n2",
        plan_version=4,
        arrival_windows={"T001": (1.0, 5.0)},
    )
    validation = validate_cooperative_guidance_topology(topology)
    t001 = [
        binding
        for binding in topology.bindings
        if binding.assigned_global_track_id == "T001"
    ]
    t002 = [
        binding
        for binding in topology.bindings
        if binding.assigned_global_track_id == "T002"
    ]

    assert topology.boundary == COOPERATIVE_TOPOLOGY_BOUNDARY
    assert len(topology.bindings) == 4
    assert topology.unassigned_resource_ids == ("R5",)
    assert [(row.resource_id, row.member_role, row.wave_id, row.activation_state) for row in t001] == [
        ("R1", "primary", 0, "active"),
        ("R2", "primary", 0, "active"),
        ("R3", "reserve", 1, "standby"),
    ]
    assert len(t002) == 1
    assert t002[0].resource_id == "R4"
    assert t002[0].coalition_id is None
    assert validation.valid is True
    assert validation.primary_binding_count == 3
    assert validation.reserve_binding_count == 1
    assert validation.standby_reserve_count == 1
    assert validation.per_target_counts["T001"]["active_primary"] == 2


def test_topology_primary_contracts_allow_and_standby_reserve_is_blocked() -> None:
    topology = build_cooperative_guidance_topology(
        resource_ids=("R1", "R2", "R3"),
        target_ids=("T001",),
        required_counts=(3,),
        coordination_mode="hybrid",
        primary_count=2,
        plan_id="plan-cooperative",
        plan_version=7,
        track_versions={"T001": 11},
        coalition_versions={"T001": 2},
        arrival_windows={"T001": (1.0, 2.0)},
    )
    permission = D4GuidancePermission(
        action="continue_center",
        target_node_id="center",
        new_plan_id=topology.plan_id,
        new_plan_version=topology.plan_version,
        coalition_id=topology.bindings[0].coalition_id,
        coalition_version=topology.bindings[0].coalition_version,
        center_available=True,
    )
    decisions = {
        binding.resource_id: evaluate_terminal_png_contract(
            binding=binding,
            d4_permission=permission,
            terminal_association=_complete_terminal_association(binding),
            timestamp_s=1.5,
            resource_id=binding.resource_id,
        )
        for binding in topology.bindings
    }

    assert decisions["R1"].allowed is True
    assert decisions["R2"].allowed is True
    assert decisions["R3"].allowed is False
    assert decisions["R3"].reject_reason == "coalition_not_activated"
    assert decisions["R3"].activation_state == "standby"


def test_uniform_per_primary_scope_needs_no_arrival_window_for_active_primaries() -> None:
    topology = build_cooperative_guidance_topology(
        resource_ids=("R1", "R2", "R3"),
        target_ids=("T001",),
        required_counts={"T001": 3},
        coordination_mode="hybrid",
        primary_count=2,
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
        plan_id="plan-per-primary",
        plan_version=8,
        track_versions=12,
        coalition_versions=3,
    )
    permission = D4GuidancePermission(
        action="continue_center",
        target_node_id="center",
        new_plan_id=topology.plan_id,
        new_plan_version=topology.plan_version,
        coalition_id=topology.bindings[0].coalition_id,
        coalition_version=topology.bindings[0].coalition_version,
        center_available=True,
    )
    decisions = {}
    for binding in topology.bindings:
        terminal = {
            **_complete_terminal_association(binding),
            "coalition_visual_complete": False,
            "planned_cooperative_lock": False,
            "support_count": 1,
        }
        decisions[binding.resource_id] = evaluate_terminal_png_contract(
            binding=binding,
            d4_permission=permission,
            terminal_association=terminal,
            timestamp_s=0.0,
            resource_id=binding.resource_id,
        )

    primaries = [row for row in topology.bindings if row.member_role == "primary"]
    reserve = next(row for row in topology.bindings if row.member_role == "reserve")
    assert all(row.terminal_authorization_scope == "per_primary" for row in topology.bindings)
    assert all(row.arrival_coordination_required is False for row in topology.bindings)
    assert all(row.arrival_window_start_s is None for row in topology.bindings)
    assert all(
        row.metadata["arrival_window_required_before_terminal_png"] is False
        for row in primaries
    )
    assert reserve.activation_state == "standby"
    assert reserve.metadata["arrival_window_required_before_terminal_png"] is True
    assert all(decisions[row.resource_id].allowed is True for row in primaries)
    assert decisions[reserve.resource_id].allowed is False
    assert decisions[reserve.resource_id].reject_reason == "coalition_not_activated"
    assert topology.targets[0].terminal_authorization_scope == "per_primary"
    assert topology.targets[0].arrival_coordination_required is False


def test_per_target_terminal_authorization_policy_is_written_to_bindings() -> None:
    topology = build_cooperative_guidance_topology(
        resource_ids=("R1", "R2", "R3", "R4"),
        target_ids=("T1", "T2"),
        required_counts={"T1": 2, "T2": 2},
        coordination_mode={"T1": "hybrid", "T2": "simultaneous"},
        primary_count=1,
        terminal_authorization_scope={"T1": "per_primary", "T2": "coalition"},
        arrival_coordination_required={"T1": False, "T2": True},
        arrival_windows={"T2": (1.0, 2.0)},
    )
    by_target = {
        target_id: [
            row
            for row in topology.bindings
            if row.assigned_global_track_id == target_id
        ]
        for target_id in ("T1", "T2")
    }

    assert {row.terminal_authorization_scope for row in by_target["T1"]} == {
        "per_primary"
    }
    assert {row.arrival_coordination_required for row in by_target["T1"]} == {False}
    assert {row.terminal_authorization_scope for row in by_target["T2"]} == {
        "coalition"
    }
    assert {row.arrival_coordination_required for row in by_target["T2"]} == {True}
    assert topology.targets[0].terminal_authorization_scope == "per_primary"
    assert topology.targets[1].terminal_authorization_scope == "coalition"


def test_default_topology_keeps_legacy_coalition_arrival_gate() -> None:
    topology = build_cooperative_guidance_topology(
        resource_ids=("R1", "R2"),
        target_ids=("T1",),
        required_counts=(2,),
        coordination_mode="hybrid",
        primary_count=2,
    )
    binding = topology.bindings[0]
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=D4GuidancePermission(
            action="continue_center",
            target_node_id="center",
            new_plan_id=topology.plan_id,
            new_plan_version=topology.plan_version,
            coalition_id=binding.coalition_id,
            coalition_version=binding.coalition_version,
        ),
        terminal_association=_complete_terminal_association(binding),
        timestamp_s=0.0,
        resource_id=binding.resource_id,
    )

    assert binding.terminal_authorization_scope == "coalition"
    assert binding.arrival_coordination_required is True
    assert binding.metadata["arrival_window_required_before_terminal_png"] is True
    assert decision.allowed is False
    assert decision.reject_reason == "coalition_arrival_window_invalid"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"terminal_authorization_scope": "unsupported"},
            "unsupported terminal authorization scopes",
        ),
        (
            {"terminal_authorization_scope": {"T1": "per_primary"}},
            "terminal_authorization_scope missing targets",
        ),
        (
            {"arrival_coordination_required": {"T1": False}},
            "arrival_coordination_required missing targets",
        ),
        (
            {"arrival_coordination_required": {"T1": "false", "T2": True}},
            "arrival_coordination_required must contain bool values",
        ),
    ],
)
def test_topology_rejects_invalid_terminal_authorization_policy(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        build_cooperative_guidance_topology(
            resource_ids=("R1", "R2"),
            target_ids=("T1", "T2"),
            required_counts=(1, 1),
            **kwargs,
        )


def test_topology_has_no_m5_n2_size_assumption() -> None:
    topology = build_cooperative_guidance_topology(
        resource_ids=tuple(f"R{index}" for index in range(1, 8)),
        target_ids=("A", "B", "C"),
        required_counts=(2, 1, 3),
        coordination_mode={"A": "simultaneous", "B": "independent", "C": "hybrid"},
        primary_count=2,
        arrival_windows={"A": (0.0, 3.0), "C": (1.0, 4.0)},
    )
    validation = validate_cooperative_guidance_topology(topology)

    assert validation.valid is True
    assert validation.binding_count == 6
    assert validation.target_count == 3
    assert validation.primary_binding_count == 5
    assert validation.reserve_binding_count == 1
    assert topology.unassigned_resource_ids == ("R7",)


def test_topology_rejects_resource_shortage() -> None:
    with pytest.raises(ValueError, match="insufficient resources"):
        build_cooperative_guidance_topology(
            resource_ids=("R1", "R2"),
            target_ids=("T1", "T2"),
            required_counts=(2, 1),
            coordination_mode="hybrid",
            primary_count=2,
        )


def _complete_terminal_association(binding: object) -> dict[str, object]:
    return {
        "assigned_global_track_id": binding.assigned_global_track_id,
        "local_track_id": f"{binding.resource_id}:local-1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": binding.track_version,
        "plan_version": binding.plan_version,
        "coalition_id": binding.coalition_id,
        "coalition_version": binding.coalition_version,
        "coalition_visual_complete": True,
        "planned_cooperative_lock": True,
        "support_count": 2,
        "required_resource_count": 2,
        "coalition_conflict_state": "none",
    }
