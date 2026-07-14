from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from types import SimpleNamespace

import pytest

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    D7RuntimeBus,
    D7RuntimePairInput,
    GuidanceMode,
    PngGuidanceConfig,
    evaluate_terminal_png_contract,
    summarize_runtime_bus_outputs,
)


def test_t001_two_active_primaries_switch_independently_and_reserve_stays_standby() -> None:
    bus = D7RuntimeBus(_config())
    primary_bindings = [
        _coalition_binding(resource_id=resource_id, role="primary", wave_id=0)
        for resource_id in ("R1", "R2")
    ]
    reserve = _coalition_binding(
        resource_id="R3",
        role="reserve",
        wave_id=1,
        activation_state="standby",
        arrival_window=(3.0, 4.0),
    )
    outputs = []

    for sample_index, half_size in enumerate((28.0, 32.0, 36.0), start=10):
        timestamp_s = sample_index / 10.0
        inputs = [
            _pair_input(binding, timestamp_s=timestamp_s, half_size=half_size)
            for binding in primary_bindings
        ]
        inputs.append(_pair_input(reserve, timestamp_s=timestamp_s, half_size=half_size))
        outputs.extend(bus.inject_state(inputs))

    primary_outputs = [row for row in outputs if row.member_role == "primary"]
    reserve_outputs = [row for row in outputs if row.member_role == "reserve"]
    summary = summarize_runtime_bus_outputs(outputs)

    assert {row.assigned_global_track_id for row in outputs} == {"G1"}
    assert {row.control_context_id for row in outputs} == {"R1->G1", "R2->G1", "R3->G1"}
    assert all(row.visual_png_enabled is False for row in reserve_outputs)
    assert {row.terminal_contract_reject_reason for row in reserve_outputs} == {
        "coalition_not_activated"
    }
    assert reserve_outputs[-1].mode == GuidanceMode.HOLD
    assert {row.resource_id for row in primary_outputs if row.visual_png_enabled} == {"R1", "R2"}
    assert all(row.terminal_contract_allowed for row in primary_outputs)
    assert all(row.d5_coalition_visual_complete is True for row in primary_outputs)
    assert all(row.guidance_law == "png_vm" for row in primary_outputs[-2:])
    assert summary["control_context_count"] == 3
    assert summary["assigned_global_track_ids"] == ["G1"]
    assert summary["coalition_ids"] == ["coalition-G1"]
    assert summary["member_role_counts"] == {"primary": 6, "reserve": 3}
    assert summary["terminal_contract_allowed_count"] == 6
    assert summary["visual_png_switch_count"] == 2
    assert summary["terminal_contract_reject_reasons"] == {
        "coalition_not_activated": 3
    }


def test_reserve_enters_visual_png_only_after_new_version_activation() -> None:
    bus = D7RuntimeBus(_config())
    standby = _coalition_binding(
        resource_id="R3",
        role="reserve",
        wave_id=1,
        activation_state="standby",
        arrival_window=(3.0, 4.0),
    )
    blocked = bus.evaluate_pair(_pair_input(standby, timestamp_s=3.0, half_size=28.0))

    activated = replace(
        standby,
        plan_id="plan-8",
        plan_version=8,
        track_version=12,
        coalition_version=2,
        activation_state="active",
        activation_plan_version=8,
        activation_track_version=12,
        activation_coalition_version=2,
    )
    activated_outputs = [
        bus.evaluate_pair(
            _pair_input(
                activated,
                timestamp_s=timestamp_s,
                half_size=half_size,
                d4_permission=_permission(activated),
                terminal_association=_terminal_association(activated),
            )
        )
        for timestamp_s, half_size in ((3.0, 28.0), (3.1, 32.0), (3.2, 36.0))
    ]

    assert blocked.terminal_contract_reject_reason == "coalition_not_activated"
    assert blocked.visual_png_enabled is False
    assert activated_outputs[0].stable_frame_count == 1
    assert activated_outputs[-1].terminal_contract_allowed is True
    assert activated_outputs[-1].coalition_gate_allowed is True
    assert activated_outputs[-1].visual_png_enabled is True
    assert activated_outputs[-1].guidance_law == "png_vm"
    assert activated_outputs[-1].coalition_version == 2


@pytest.mark.parametrize("coordination_mode", ["simultaneous", "sequential", "hybrid"])
def test_coordinated_modes_do_not_switch_before_arrival_window(
    coordination_mode: str,
) -> None:
    binding = replace(
        _coalition_binding(resource_id="R1", role="primary", wave_id=0),
        coordination_mode=coordination_mode,
        arrival_window_start_s=5.0,
        arrival_window_end_s=6.0,
    )
    output = D7RuntimeBus(_config()).evaluate_pair(
        _pair_input(binding, timestamp_s=4.9, half_size=40.0)
    )

    assert output.visual_png_enabled is False
    assert output.guidance_law == "radar_pn"
    assert output.mode == GuidanceMode.RADAR_MIDCOURSE
    assert output.terminal_contract_reject_reason == "coalition_window_not_open"
    assert output.coalition_gate_reject_reason == "coalition_window_not_open"
    assert output.png_command is None


def test_per_primary_scope_switches_without_common_lock_or_arrival_window() -> None:
    binding = replace(
        _coalition_binding(resource_id="R1", role="primary", wave_id=0),
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
        arrival_window_start_s=5.0,
        arrival_window_end_s=6.0,
    )
    own_lock_only = {
        **_terminal_association(binding),
        "coalition_visual_complete": False,
        "planned_cooperative_lock": False,
        "support_count": 1,
        "required_resource_count": 2,
    }
    bus = D7RuntimeBus(_config())
    outputs = [
        bus.evaluate_pair(
            _pair_input(
                binding,
                timestamp_s=timestamp_s,
                half_size=half_size,
                terminal_association=own_lock_only,
            )
        )
        for timestamp_s, half_size in ((0.0, 28.0), (0.1, 32.0), (0.2, 36.0))
    ]
    final = outputs[-1]
    record = final.as_log_record()
    summary = summarize_runtime_bus_outputs(outputs)

    assert all(row.terminal_contract_allowed for row in outputs)
    assert final.visual_png_enabled is True
    assert final.guidance_law == "png_vm"
    assert final.terminal_authorization_scope == "per_primary"
    assert final.arrival_coordination_required is False
    assert final.per_primary_authorization_active is True
    assert final.coalition_visual_completion_bypassed is True
    assert final.bypassed_arrival_only is True
    assert record["terminal_authorization_scope"] == "per_primary"
    assert record["bypassed_arrival_only"] is True
    assert summary["terminal_authorization_scope_counts"] == {"per_primary": 3}
    assert summary["bypassed_arrival_only_count"] == 3


def test_per_primary_scope_requires_explicit_arrival_coordination_false() -> None:
    binding = replace(
        _coalition_binding(resource_id="R1", role="primary", wave_id=0),
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=True,
        arrival_window_start_s=5.0,
        arrival_window_end_s=6.0,
    )
    terminal = {
        **_terminal_association(binding),
        "coalition_visual_complete": False,
    }
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=_permission(binding),
        terminal_association=terminal,
        timestamp_s=4.9,
        resource_id="R1",
    )

    assert decision.allowed is False
    assert decision.reject_reason == "coalition_window_not_open"
    assert decision.per_primary_authorization_active is False
    assert decision.bypassed_arrival_only is False


def test_per_primary_scope_does_not_activate_standby_reserve() -> None:
    reserve = replace(
        _coalition_binding(
            resource_id="R3",
            role="reserve",
            wave_id=1,
            activation_state="standby",
            arrival_window=(3.0, 4.0),
        ),
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
    )
    decision = evaluate_terminal_png_contract(
        binding=reserve,
        d4_permission=_permission(reserve),
        terminal_association=_terminal_association(reserve),
        timestamp_s=1.0,
        resource_id="R3",
    )

    assert decision.allowed is False
    assert decision.reject_reason == "coalition_not_activated"


def test_per_primary_scope_does_not_bypass_arrival_gate_for_activated_reserve() -> None:
    reserve = replace(
        _activated_reserve(),
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
    )
    decision = evaluate_terminal_png_contract(
        binding=reserve,
        d4_permission=_permission(reserve),
        terminal_association=_terminal_association(reserve),
        timestamp_s=2.9,
        resource_id="R3",
    )

    assert decision.allowed is False
    assert decision.reject_reason == "coalition_window_not_open"
    assert decision.per_primary_authorization_active is False


@pytest.mark.parametrize(
    ("permission", "expected_reason"),
    [
        (
            D4GuidancePermission(action="request_center_replan", mode="pending"),
            "d4_reassign_pending",
        ),
        (
            D4GuidancePermission(action="degrade_to_distributed", mode="reconfiguring"),
            "d4_reassign_pending",
        ),
    ],
)
def test_per_primary_scope_keeps_d4_pending_and_reconfiguring_blocked(
    permission: D4GuidancePermission,
    expected_reason: str,
) -> None:
    binding = replace(
        _coalition_binding(resource_id="R1", role="primary", wave_id=0),
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
    )
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=permission,
        terminal_association=_terminal_association(binding),
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.allowed is False
    assert decision.reject_reason == expected_reason


@pytest.mark.parametrize(
    ("permission_factory", "expected_reason"),
    [
        (
            lambda binding: _fallback_permission(binding, acked=("R1",)),
            "coalition_required_ack_incomplete",
        ),
        (
            lambda binding: _fallback_permission(binding, lease_expires_at_s=1.0),
            "coalition_commit_lease_expired",
        ),
        (
            lambda binding: _fallback_permission(binding, state="reconfiguring"),
            "coalition_commit_reconfiguring",
        ),
    ],
)
def test_per_primary_scope_keeps_distributed_commit_safety_gates(
    permission_factory: Callable[[AssignmentGuidanceBinding], object],
    expected_reason: str,
) -> None:
    binding = replace(
        _coalition_binding(resource_id="R1", role="primary", wave_id=0),
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
    )
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=permission_factory(binding),
        terminal_association=_terminal_association(binding),
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.allowed is False
    assert decision.reject_reason == expected_reason


@pytest.mark.parametrize(
    ("terminal_update", "expected_reason"),
    [
        ({"friend_conflict_state": "verified_friend"}, "friend_conflict"),
        ({"duplicate_terminal_lock_risk": True}, "duplicate_lock_conflict"),
        ({"decision_state": "reacquire"}, "d5_not_locked"),
    ],
)
def test_per_primary_scope_keeps_own_d5_safety_gates(
    terminal_update: dict[str, object],
    expected_reason: str,
) -> None:
    binding = replace(
        _coalition_binding(resource_id="R1", role="primary", wave_id=0),
        terminal_authorization_scope="per_primary",
        arrival_coordination_required=False,
    )
    terminal = {**_terminal_association(binding), **terminal_update}
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=_permission(binding),
        terminal_association=terminal,
        timestamp_s=0.0,
        resource_id="R1",
    )

    assert decision.allowed is False
    assert decision.reject_reason == expected_reason


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    [
        ("activation_plan_version", 7, "coalition_plan_version_mismatch"),
        ("activation_track_version", 11, "coalition_track_version_mismatch"),
        ("activation_coalition_version", 1, "coalition_version_mismatch"),
    ],
)
def test_reserve_activation_rejects_plan_track_or_coalition_version_mismatch(
    field: str,
    value: int,
    expected_reason: str,
) -> None:
    binding = _activated_reserve()
    binding = replace(binding, **{field: value})

    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=_permission(binding),
        terminal_association=_terminal_association(binding),
        timestamp_s=3.2,
        resource_id="R3",
    )

    assert decision.allowed is False
    assert decision.reject_reason == expected_reason
    assert decision.coalition_gate_allowed is False


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    [
        ("plan_version", 7, "coalition_plan_version_mismatch"),
        ("assignment_version", 11, "coalition_track_version_mismatch"),
        ("coalition_version", 1, "coalition_version_mismatch"),
    ],
)
def test_reserve_activation_rejects_d5_version_mismatch(
    field: str,
    value: int,
    expected_reason: str,
) -> None:
    binding = _activated_reserve()
    terminal = {**_terminal_association(binding), field: value}

    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=_permission(binding),
        terminal_association=terminal,
        timestamp_s=3.2,
        resource_id="R3",
    )

    assert decision.allowed is False
    assert decision.reject_reason == expected_reason


@pytest.mark.parametrize(
    ("permission", "expected_reason", "expected_mode"),
    [
        (
            D4GuidancePermission(action="coalition_fallback_unsupported"),
            "coalition_fallback_unsupported",
            GuidanceMode.ABORT_REVOKE,
        ),
        (
            D4GuidancePermission(
                action="continue_center",
                reason="coalition_fallback_unsupported",
            ),
            "coalition_fallback_unsupported",
            GuidanceMode.ABORT_REVOKE,
        ),
        (D4GuidancePermission(action="hold"), "d4_hold", GuidanceMode.HOLD),
        (D4GuidancePermission(action="revoke"), "d4_revoke", GuidanceMode.ABORT_REVOKE),
        (
            D4GuidancePermission(action="request_center_replan", mode="pending"),
            "d4_reassign_pending",
            GuidanceMode.ABORT_REVOKE,
        ),
        (
            D4GuidancePermission(
                action="continue_center",
                center_available=False,
                atomic_coalition_formed=False,
            ),
            "atomic_coalition_missing",
            GuidanceMode.ABORT_REVOKE,
        ),
        (
            D4GuidancePermission(
                action="continue_center",
                mode="center_failed",
                atomic_coalition_formed=False,
            ),
            "atomic_coalition_missing",
            GuidanceMode.ABORT_REVOKE,
        ),
    ],
)
def test_d4_safety_states_block_coalition_visual_png(
    permission: D4GuidancePermission,
    expected_reason: str,
    expected_mode: GuidanceMode,
) -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    output = D7RuntimeBus(_config()).evaluate_pair(
        _pair_input(
            binding,
            timestamp_s=1.1,
            half_size=40.0,
            d4_permission=permission,
        )
    )

    assert output.visual_png_enabled is False
    assert output.guidance_law == "radar_pn"
    assert output.terminal_contract_reject_reason == expected_reason
    assert output.d4_action_block_reason == expected_reason
    assert output.mode == expected_mode
    assert output.png_command is None


def test_t002_k1_binding_without_coalition_fields_can_switch_png_vm() -> None:
    binding = AssignmentGuidanceBinding(
        plan_id="plan-k1",
        plan_version=1,
        owner_node_id="center",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id="G1",
        track_version=4,
        authorization_state="approved",
    )
    terminal = {
        "assigned_global_track_id": "G1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 4,
    }
    permission = D4GuidancePermission(action="continue_center")
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=permission,
        terminal_association=terminal,
        timestamp_s=0.0,
        resource_id="R1",
    )
    bus = D7RuntimeBus(_config())
    outputs = [
        bus.evaluate_pair(
            _pair_input(
                binding,
                timestamp_s=timestamp_s,
                half_size=half_size,
                d4_permission=permission,
                terminal_association=terminal,
            )
        )
        for timestamp_s, half_size in ((0.0, 28.0), (0.1, 32.0), (0.2, 36.0))
    ]

    assert decision.allowed is True
    assert decision.coalition_gate_applicable is False
    assert decision.coalition_gate_allowed is None
    assert outputs[-1].terminal_contract_allowed is True
    assert outputs[-1].visual_png_enabled is True
    assert outputs[-1].guidance_law == "png_vm"
    assert outputs[-1].as_log_record()["visual_png_switch"] is True


def test_d4_no_change_ack_continue_center_still_requires_d5_locked() -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    terminal = {
        **_terminal_association(binding),
        "decision_state": "reacquire",
    }
    permission = replace(
        _permission(binding),
        reason="center_replan_no_change_ack",
        metadata={"replan_ack": "no_change", "final_action": "continue_center"},
    )
    output = D7RuntimeBus(_config()).evaluate_pair(
        _pair_input(
            binding,
            timestamp_s=1.1,
            half_size=40.0,
            d4_permission=permission,
            terminal_association=terminal,
        )
    )

    assert output.d4_action == "continue_center"
    assert output.terminal_contract_allowed is False
    assert output.visual_png_enabled is False
    assert output.as_log_record()["visual_png_switch"] is False
    assert output.terminal_contract_reject_reason == "d5_not_locked"
    assert output.mode == GuidanceMode.REACQUIRE
    assert output.terminal_switch_reject_reason == ""


def test_t001_primary_requires_coalition_visual_completion_evidence() -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    terminal = _terminal_association(binding)
    for field in (
        "coalition_visual_complete",
        "planned_cooperative_lock",
        "support_count",
        "required_resource_count",
        "coalition_conflict_state",
    ):
        terminal.pop(field, None)
    output = D7RuntimeBus(_config()).evaluate_pair(
        _pair_input(
            binding,
            timestamp_s=1.1,
            half_size=40.0,
            terminal_association=terminal,
        )
    )
    summary = summarize_runtime_bus_outputs([output])

    assert output.terminal_contract_allowed is False
    assert output.visual_png_enabled is False
    assert output.terminal_contract_reject_reason == "coalition_visual_completion_missing"
    assert output.coalition_gate_reject_reason == "coalition_visual_completion_missing"
    assert summary["terminal_contract_allowed_count"] == 0
    assert summary["visual_png_switch_count"] == 0
    assert summary["terminal_contract_reject_reasons"] == {
        "coalition_visual_completion_missing": 1
    }


def test_t001_primary_blocks_incomplete_coalition_visual_support() -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    terminal = {
        **_terminal_association(binding),
        "coalition_visual_complete": False,
        "support_count": 1,
        "required_resource_count": 2,
    }
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=_permission(binding),
        terminal_association=terminal,
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.allowed is False
    assert decision.reject_reason == "coalition_visual_incomplete"
    assert decision.d5_coalition_support_count == 1
    assert decision.d5_required_resource_count == 2


def test_t001_primary_blocks_d5_coalition_version_conflict() -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    terminal = {
        **_terminal_association(binding),
        "coalition_version": binding.coalition_version + 1,
    }
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=_permission(binding),
        terminal_association=terminal,
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.allowed is False
    assert decision.reject_reason == "coalition_version_mismatch"
    assert decision.coalition_gate_allowed is False


@pytest.mark.parametrize("commit_state", ["committed", "executing"])
def test_fallback_commit_allows_both_acked_primaries(
    commit_state: str,
) -> None:
    bindings = [
        _coalition_binding(resource_id=resource_id, role="primary", wave_id=0)
        for resource_id in ("R1", "R2")
    ]
    permission = _fallback_permission(bindings[0], state=commit_state)
    outputs = [
        D7RuntimeBus(_config()).evaluate_pair(
            _pair_input(
                binding,
                timestamp_s=1.1,
                half_size=40.0,
                d4_permission=permission,
            )
        )
        for binding in bindings
    ]
    summary = summarize_runtime_bus_outputs(outputs)

    assert all(row.terminal_contract_allowed for row in outputs)
    assert all(row.coalition_commit_gate_allowed is True for row in outputs)
    assert all(row.coalition_resource_required is True for row in outputs)
    assert all(row.coalition_resource_acked is True for row in outputs)
    assert summary["coalition_commit_gate_applicable_count"] == 2
    assert summary["coalition_commit_gate_allowed_count"] == 2
    assert summary["coalition_commit_gate_reject_reasons"] == {}
    assert summary["coalition_commit_state_counts"] == {commit_state: 2}


def test_fallback_standby_reserve_remains_blocked_even_when_acked() -> None:
    reserve = _coalition_binding(
        resource_id="R3",
        role="reserve",
        wave_id=1,
        activation_state="standby",
        arrival_window=(1.0, 2.0),
    )
    output = D7RuntimeBus(_config()).evaluate_pair(
        _pair_input(
            reserve,
            timestamp_s=1.1,
            half_size=40.0,
            d4_permission=_fallback_permission(
                reserve,
                required=("R1", "R2", "R3"),
                acked=("R1", "R2", "R3"),
            ),
        )
    )

    assert output.terminal_contract_allowed is False
    assert output.visual_png_enabled is False
    assert output.terminal_contract_reject_reason == "coalition_not_activated"


def test_fallback_missing_ack_blocks_all_required_members() -> None:
    r1 = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    r2 = _coalition_binding(resource_id="R2", role="primary", wave_id=0)
    permission = _fallback_permission(r1, acked=("R1",))

    r1_decision = evaluate_terminal_png_contract(
        binding=r1,
        d4_permission=permission,
        terminal_association=_terminal_association(r1),
        timestamp_s=1.1,
        resource_id="R1",
    )
    r2_decision = evaluate_terminal_png_contract(
        binding=r2,
        d4_permission=permission,
        terminal_association=_terminal_association(r2),
        timestamp_s=1.1,
        resource_id="R2",
    )

    assert r1_decision.reject_reason == "coalition_required_ack_incomplete"
    assert r2_decision.reject_reason == "coalition_member_ack_missing"


def test_fallback_rejects_old_epoch_and_expired_lease() -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    old_epoch = _fallback_permission(binding, epoch=binding.coalition_epoch - 1)
    expired = _fallback_permission(binding, lease_expires_at_s=1.0)

    old_epoch_decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=old_epoch,
        terminal_association=_terminal_association(binding),
        timestamp_s=1.1,
        resource_id="R1",
    )
    expired_decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=expired,
        terminal_association=_terminal_association(binding),
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert old_epoch_decision.reject_reason == "coalition_epoch_mismatch"
    assert expired_decision.reject_reason == "coalition_commit_lease_expired"


def test_fallback_without_commit_state_fails_closed() -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    permission = SimpleNamespace(
        action="continue_center",
        mode="center_failed",
        center_available=False,
        target_node_id=binding.owner_node_id,
    )
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=permission,
        terminal_association=_terminal_association(binding),
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.reject_reason == "coalition_commit_state_missing"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("plan_version", 6, "coalition_commit_plan_mismatch"),
        ("coalition_version", 0, "coalition_commit_coalition_mismatch"),
    ],
)
def test_fallback_rejects_commit_plan_or_coalition_version_mismatch(
    field: str,
    value: int,
    reason: str,
) -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    permission = _fallback_permission(binding)
    setattr(permission.commit_state, field, value)
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=permission,
        terminal_association=_terminal_association(binding),
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.reject_reason == reason


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("reconfiguring", "coalition_commit_reconfiguring"),
        ("aborted", "coalition_commit_aborted"),
    ],
)
def test_fallback_rejects_non_executable_commit_states(
    state: str,
    reason: str,
) -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=_fallback_permission(binding, state=state),
        terminal_association=_terminal_association(binding),
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.allowed is False
    assert decision.reject_reason == reason
    assert decision.coalition_commit_gate_allowed is False


def test_fallback_d4_pending_precedes_committed_coalition() -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    permission = _fallback_permission(binding)
    permission.action = "degrade_to_distributed"
    permission.mode = "pending"
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=permission,
        terminal_association=_terminal_association(binding),
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.reject_reason == "d4_reassign_pending"


def test_fallback_committed_coalition_still_requires_d5_visual_completion() -> None:
    binding = _coalition_binding(resource_id="R1", role="primary", wave_id=0)
    terminal = {
        **_terminal_association(binding),
        "coalition_visual_complete": False,
        "support_count": 1,
    }
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=_fallback_permission(binding),
        terminal_association=terminal,
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.reject_reason == "coalition_visual_incomplete"
    assert decision.coalition_commit_gate_allowed is True


def test_center_failed_k1_without_coalition_does_not_require_commit_state() -> None:
    binding = AssignmentGuidanceBinding(
        plan_id="plan-k1-fallback",
        plan_version=2,
        owner_node_id="peer-R1",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id="G1",
        track_version=5,
        authorization_state="approved",
    )
    terminal = {
        "assigned_global_track_id": "G1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 5,
    }
    permission = SimpleNamespace(
        action="continue_center",
        mode="center_failed",
        center_available=False,
        target_node_id="peer-R1",
    )
    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=permission,
        terminal_association=terminal,
        timestamp_s=1.1,
        resource_id="R1",
    )

    assert decision.allowed is True
    assert decision.coalition_commit_gate_applicable is False


def _coalition_binding(
    *,
    resource_id: str,
    role: str,
    wave_id: int,
    activation_state: str = "active",
    arrival_window: tuple[float, float] = (1.0, 2.0),
) -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id="plan-7",
        plan_version=7,
        owner_node_id="center",
        assignment_id=f"assign-{resource_id}-G1",
        resource_id=resource_id,
        vehicle_name=f"Interceptor_{resource_id}",
        assigned_global_track_id="G1",
        track_version=11,
        authorization_state="approved",
        coalition_id="coalition-G1",
        coalition_version=1,
        coalition_epoch=4,
        member_role=role,
        wave_id=wave_id,
        coordination_mode="hybrid",
        arrival_window_start_s=arrival_window[0],
        arrival_window_end_s=arrival_window[1],
        activation_state=activation_state,
    )


def _activated_reserve() -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id="plan-8",
        plan_version=8,
        owner_node_id="center",
        assignment_id="assign-R3-G1-retry",
        resource_id="R3",
        vehicle_name="Interceptor_R3",
        assigned_global_track_id="G1",
        track_version=12,
        authorization_state="approved",
        coalition_id="coalition-G1",
        coalition_version=2,
        member_role="reserve",
        wave_id=1,
        coordination_mode="hybrid",
        arrival_window_start_s=3.0,
        arrival_window_end_s=4.0,
        activation_state="active",
        activation_plan_version=8,
        activation_track_version=12,
        activation_coalition_version=2,
    )


def _permission(binding: AssignmentGuidanceBinding) -> D4GuidancePermission:
    return D4GuidancePermission(
        action="continue_center",
        target_node_id="center",
        new_plan_id=binding.plan_id,
        new_plan_version=binding.plan_version,
        coalition_id=binding.coalition_id,
        coalition_version=binding.coalition_version,
        center_available=True,
        atomic_coalition_formed=True,
    )


def _fallback_permission(
    binding: AssignmentGuidanceBinding,
    *,
    state: str = "committed",
    epoch: int | None = None,
    lease_expires_at_s: float = 2.0,
    required: tuple[str, ...] = ("R1", "R2"),
    acked: tuple[str, ...] = ("R1", "R2"),
) -> SimpleNamespace:
    commit_state = SimpleNamespace(
        state=state,
        epoch=binding.coalition_epoch if epoch is None else epoch,
        lease_expires_at_s=lease_expires_at_s,
        required_members=tuple(SimpleNamespace(resource_id=item) for item in required),
        acked_members=tuple(SimpleNamespace(resource_id=item) for item in acked),
        plan_id=binding.plan_id,
        plan_version=binding.plan_version,
        coalition_id=binding.coalition_id,
        coalition_version=binding.coalition_version,
    )
    return SimpleNamespace(
        action="continue_center",
        mode="center_failed",
        reason="distributed_fallback_committed",
        target_node_id=binding.owner_node_id,
        new_plan_id=binding.plan_id,
        new_plan_version=binding.plan_version,
        center_available=False,
        atomic_coalition_formed=True,
        commit_state=commit_state,
    )


def _terminal_association(binding: AssignmentGuidanceBinding) -> dict[str, object]:
    return {
        "resource_id": binding.resource_id,
        "assigned_global_track_id": binding.assigned_global_track_id,
        "local_track_id": f"{binding.resource_id}:BT:1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": binding.track_version,
        "plan_version": binding.plan_version,
        "coalition_id": binding.coalition_id,
        "coalition_version": binding.coalition_version,
        "planned_cooperative_lock": True,
        "support_count": 2,
        "required_resource_count": 2,
        "coalition_conflict_state": "none",
    }


def _pair_input(
    binding: AssignmentGuidanceBinding,
    *,
    timestamp_s: float,
    half_size: float,
    d4_permission: object | None = None,
    terminal_association: dict[str, object] | None = None,
) -> D7RuntimePairInput:
    return D7RuntimePairInput(
        binding=binding,
        d4_permission=d4_permission or _permission(binding),
        terminal_association=terminal_association or _terminal_association(binding),
        observation={
            "timestamp_s": timestamp_s,
            "bbox_xyxy": (
                320.0 - half_size,
                240.0 - half_size,
                320.0 + half_size,
                240.0 + half_size,
            ),
            "confidence": 0.9,
            "local_track_id": f"{binding.resource_id}:BT:1",
            "assigned_global_track_id": binding.assigned_global_track_id,
        },
        timestamp_s=timestamp_s,
        handover_pending=True,
        terminal_locked=True,
        current_heading_rad=0.0,
        current_speed_mps=8.0,
        intercept_speed_mps=8.0,
        relative_position_ned=(30.0, 1.0, 0.0),
        relative_velocity_ned=(-5.0, 0.0, 0.0),
    )


def _config() -> PngGuidanceConfig:
    return PngGuidanceConfig(
        dt_s=0.1,
        image_width_px=640,
        image_height_px=480,
        focal_length_px=320.0,
        min_bbox_area_ratio=0.001,
        min_detection_confidence=0.55,
        min_stable_frames=2,
        edge_margin_ratio=0.03,
        max_los_rate_variance_radps2=2.0,
        los_rate_window=5,
        max_visual_latency_s=0.35,
        navigation_constant=3.0,
        law="png_vm",
    )
