from __future__ import annotations

from dataclasses import replace

import pytest

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    D7RuntimeBus,
    D7RuntimePairInput,
    PngGuidanceConfig,
    TerminalDeliveryConfig,
    TerminalDeliveryState,
    TerminalGuidanceDelivery,
    VisionGuidanceObservation,
    summarize_runtime_bus_outputs,
)


def test_terminal_delivery_defaults_match_validated_short_coast() -> None:
    config = TerminalDeliveryConfig()

    assert config.control_dt_s == pytest.approx(0.1)
    assert config.image_kf_max_predict_s == pytest.approx(0.25)
    assert config.consecutive_loss_frames == 3
    assert config.command_average_window_s == pytest.approx(0.10)
    assert config.blind_push_duration_s == pytest.approx(0.25)
    assert config.command_decay_tau_s == pytest.approx(0.18)


def test_transient_loss_predicts_and_same_global_track_reacquires() -> None:
    delivery = TerminalGuidanceDelivery(_png_config())
    for index in range(3):
        measured = delivery.evaluate(
            assigned_global_track_id="G1",
            timestamp_s=index * 0.1,
            observation=_observation(index * 0.1, center_x=320.0 + index),
            **_kinematics(),
        )

    assert measured.state == TerminalDeliveryState.MEASURED
    assert measured.visual_lock_measured is True
    predicted = delivery.evaluate(
        assigned_global_track_id="G1",
        timestamp_s=0.3,
        observation=None,
        **_kinematics(),
    )
    predicted_2 = delivery.evaluate(
        assigned_global_track_id="G1",
        timestamp_s=0.4,
        observation=None,
        **_kinematics(),
    )
    reacquired = delivery.evaluate(
        assigned_global_track_id="G1",
        timestamp_s=0.5,
        observation=_observation(0.5, center_x=325.0, local_track_id="BT-9"),
        **_kinematics(),
    )

    assert predicted.state == TerminalDeliveryState.IMAGE_KF_PREDICT
    assert predicted.command is not None
    assert predicted.using_extrapolation is True
    assert predicted_2.state == TerminalDeliveryState.IMAGE_KF_PREDICT
    assert reacquired.state == TerminalDeliveryState.REACQUIRED
    assert reacquired.reason == "terminal_visual_reacquired"
    assert reacquired.assigned_global_track_id == "G1"
    assert reacquired.visual_lock_measured is True


def test_terminal_delivery_expires_at_hard_prediction_age_limit() -> None:
    delivery = TerminalGuidanceDelivery(_png_config())
    for index in range(3):
        delivery.evaluate(
            assigned_global_track_id="G1",
            timestamp_s=index * 0.1,
            observation=_observation(index * 0.1, center_x=320.0 + index),
            **_kinematics(),
        )

    states = []
    results = []
    for timestamp_s in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        result = delivery.evaluate(
            assigned_global_track_id="G1",
            timestamp_s=timestamp_s,
            observation=None,
            **_kinematics(),
        )
        states.append(result.state)
        results.append(result)

    assert states[:2] == [
        TerminalDeliveryState.IMAGE_KF_PREDICT,
        TerminalDeliveryState.IMAGE_KF_PREDICT,
    ]
    assert all(state == TerminalDeliveryState.EXPIRED for state in states[2:])
    assert results[2].measurement_age_s == pytest.approx(0.3)
    assert results[2].reason == "terminal_visual_prediction_window_expired"
    assert results[2].filter_audit_reason == "image_kf_predict_timeout"
    assert all(result.command is None for result in results[2:])


def test_first_terminal_sample_without_lock_is_acquiring_and_has_no_command() -> None:
    delivery = TerminalGuidanceDelivery(_png_config())

    result = delivery.block(
        assigned_global_track_id="G1",
        reason="d5_not_locked",
    )

    assert result.state == TerminalDeliveryState.ACQUIRING
    assert result.visual_lock_measured is False
    assert result.command is None


def test_runtime_keeps_terminal_delivery_state_independent_per_assignment_pair() -> None:
    bus = D7RuntimeBus(_png_config())
    for index in range(3):
        bus.inject_state(
            [
                _pair_input(
                    timestamp_s=index * 0.1,
                    observation=_observation(index * 0.1, center_x=320.0 + index),
                ),
                _pair_input_for_r2(timestamp_s=index * 0.1),
            ]
        )

    outputs = bus.inject_state(
        [
            _pair_input(timestamp_s=0.3, observation=None),
            _pair_input_for_r2(timestamp_s=0.3),
        ]
    )

    by_resource = {output.resource_id: output for output in outputs}
    assert by_resource["R1"].terminal_delivery_state == "image_kf_predict"
    assert by_resource["R1"].terminal_using_extrapolation is True
    assert by_resource["R2"].terminal_delivery_state == "measured"
    assert by_resource["R2"].terminal_using_extrapolation is False
    assert set(bus.control_context_ids) == {"R1->G1", "R2->G2"}
    summary = summarize_runtime_bus_outputs(outputs)
    assert summary["terminal_delivery_state_counts"] == {
        "image_kf_predict": 1,
        "measured": 1,
    }
    assert summary["terminal_extrapolation_count"] == 1
    record = by_resource["R1"].as_log_record()
    assert record["terminal_delivery_reason"] == "terminal_visual_image_kf_predict"
    assert record["terminal_prediction_age_s"] == pytest.approx(0.1)


def test_runtime_allows_bounded_coast_for_consistent_d5_reacquire_only() -> None:
    bus = D7RuntimeBus(_png_config())
    for index in range(3):
        measured = bus.evaluate_pair(
            _pair_input(
                timestamp_s=index * 0.1,
                observation=_observation(index * 0.1, center_x=320.0 + index),
            )
        )
    assert measured.visual_png_enabled is True

    reacquire = _terminal_association()
    reacquire["decision_state"] = "reacquire"
    predicted = bus.evaluate_pair(
        _pair_input(
            timestamp_s=0.3,
            observation=None,
            terminal_association=reacquire,
        )
    )

    assert predicted.raw_terminal_gate_allowed is False
    assert predicted.raw_terminal_gate_reject_reason == "d5_not_locked"
    assert predicted.terminal_contract_allowed is True
    assert predicted.effective_terminal_contract_allowed is True
    assert predicted.effective_terminal_contract_scope == "bounded_coast"
    assert predicted.terminal_contract_reject_reason == ""
    assert predicted.terminal_coast_contract_allowed is True
    assert predicted.terminal_coast_contract_reason == "bounded_coast_reacquire"
    assert predicted.terminal_delivery_state == "image_kf_predict"
    assert predicted.terminal_using_extrapolation is True
    assert predicted.latched_visual_mode_active is True
    assert predicted.effective_control_authorized is True
    assert predicted.effective_control_authorization_scope == "bounded_coast"
    assert predicted.selected_velocity_ned is not None
    coast_summary = summarize_runtime_bus_outputs([predicted])
    assert coast_summary["raw_terminal_gate_allowed_count"] == 0
    assert coast_summary["raw_terminal_gate_reject_reasons"] == {"d5_not_locked": 1}
    assert coast_summary["effective_terminal_contract_allowed_count"] == 1
    assert coast_summary["effective_terminal_contract_scope_counts"] == {
        "bounded_coast": 1
    }
    assert coast_summary["latched_visual_mode_active_count"] == 1
    assert coast_summary["effective_control_authorized_count"] == 1
    assert coast_summary["effective_control_authorization_scope_counts"] == {
        "bounded_coast": 1
    }

    blocked = bus.evaluate_pair(
        _pair_input(
            timestamp_s=0.4,
            observation=None,
            terminal_association=reacquire,
            d4_permission=D4GuidancePermission(
                action="continue_center",
                terminal_consistent=False,
            ),
        )
    )
    assert blocked.terminal_coast_contract_allowed is False
    assert blocked.terminal_delivery_state == "expired"
    assert blocked.terminal_delivery_reason == "d4_terminal_inconsistent"
    assert blocked.terminal_using_extrapolation is False
    assert blocked.selected_velocity_ned is None


@pytest.mark.parametrize(
    ("terminal_override", "permission", "reject_reason"),
    [
        ({"assignment_version": 8}, None, "assignment_version_mismatch"),
        (None, D4GuidancePermission(action="degrade_to_secondary"), "d4_reassign_pending"),
        ({"metadata": {"execution_gate_pass": False}}, None, "d5_safety_gate_blocked"),
    ],
)
def test_runtime_contract_failure_immediately_clears_pair_coast(
    terminal_override: dict[str, object] | None,
    permission: D4GuidancePermission | None,
    reject_reason: str,
) -> None:
    bus = D7RuntimeBus(_png_config())
    for index in range(3):
        output = bus.evaluate_pair(
            _pair_input(
                timestamp_s=index * 0.1,
                observation=_observation(index * 0.1, center_x=320.0 + index),
            )
        )
    assert output.terminal_delivery_state == "measured"

    blocked_terminal = _terminal_association()
    if terminal_override:
        blocked_terminal.update(terminal_override)
    blocked = bus.evaluate_pair(
        _pair_input(
            timestamp_s=0.3,
            observation=None,
            terminal_association=blocked_terminal,
            d4_permission=permission,
        )
    )

    assert blocked.terminal_contract_allowed is False
    assert blocked.terminal_contract_reject_reason == reject_reason
    assert blocked.terminal_delivery_state == "expired"
    assert blocked.terminal_delivery_reason == reject_reason
    assert blocked.terminal_using_extrapolation is False
    assert blocked.selected_velocity_ned is None
    assert blocked.assigned_global_track_id == "G1"

    fresh_without_measurement = bus.evaluate_pair(
        _pair_input(timestamp_s=0.4, observation=None)
    )
    assert fresh_without_measurement.terminal_delivery_state == "acquiring"
    assert fresh_without_measurement.selected_velocity_ned is None


def test_termination_snapshot_is_not_a_live_gate_or_control_sample() -> None:
    bus = D7RuntimeBus(_png_config())
    live_outputs = [
        bus.evaluate_pair(
            _pair_input(
                timestamp_s=index * 0.1,
                observation=_observation(index * 0.1, center_x=320.0 + index),
            )
        )
        for index in range(3)
    ]
    assert live_outputs[-1].effective_control_authorized is True

    snapshot = bus.evaluate_pair(
        replace(
            _pair_input(timestamp_s=0.3, observation=None),
            termination_snapshot=True,
            termination_status="aborted",
            termination_reason="terminal_detection_timeout",
        )
    )
    record = snapshot.as_log_record()
    summary = summarize_runtime_bus_outputs([*live_outputs, snapshot])

    assert snapshot.termination_snapshot is True
    assert snapshot.raw_terminal_gate_allowed is None
    assert snapshot.latched_visual_mode_active is False
    assert snapshot.effective_terminal_contract_allowed is False
    assert snapshot.effective_terminal_contract_scope == "termination_snapshot"
    assert snapshot.effective_control_authorized is False
    assert snapshot.effective_control_authorization_scope == "termination_snapshot"
    assert snapshot.terminal_contract_allowed is False
    assert snapshot.terminal_switch_allowed is False
    assert snapshot.termination_prior_latched_visual_mode_active is True
    assert snapshot.termination_prior_effective_control_authorized is True
    assert snapshot.mode_transition is False
    assert record["terminal_control_allowed"] is False
    assert summary["sample_count"] == 4
    assert summary["live_control_sample_count"] == 3
    assert summary["termination_snapshot_count"] == 1
    assert summary["termination_status_counts"] == {"aborted": 1}
    assert summary["termination_prior_effective_control_authorized_count"] == 1
    assert summary["terminal_switch_allowed_count"] == summary[
        "effective_control_authorized_count"
    ]

    initial_snapshot = D7RuntimeBus(_png_config()).evaluate_pair(
        replace(
            _pair_input(timestamp_s=0.0, observation=None),
            termination_snapshot=True,
            termination_status="aborted",
            termination_reason="resource_missing",
        )
    )
    assert initial_snapshot.terminal_contract_applicable is False
    assert initial_snapshot.raw_terminal_contract_allowed is None
    assert initial_snapshot.terminal_handoff_state == "termination_snapshot"
    assert initial_snapshot.terminal_switch_allowed is False


def test_dropout_audit_distinguishes_missing_lock_prediction_and_contract_reset() -> None:
    reacquire = _terminal_association()
    reacquire["decision_state"] = "reacquire"

    never_locked = D7RuntimeBus(_png_config()).evaluate_pair(
        _pair_input(
            timestamp_s=0.1,
            observation=None,
            terminal_association=reacquire,
        )
    )
    assert never_locked.terminal_delivery_state == "acquiring"
    assert never_locked.terminal_dropout_reason_scope == "measured_lock_not_established"
    assert never_locked.terminal_measured_lock_ever_established is False

    prediction_bus = D7RuntimeBus(_png_config())
    for index in range(3):
        prediction_bus.evaluate_pair(
            _pair_input(
                timestamp_s=index * 0.1,
                observation=_observation(index * 0.1, center_x=320.0 + index),
            )
        )
    prediction_expired = prediction_bus.evaluate_pair(
        _pair_input(
            timestamp_s=0.6,
            observation=None,
            terminal_association=reacquire,
        )
    )
    assert prediction_expired.terminal_delivery_state == "expired"
    assert prediction_expired.terminal_dropout_reason_scope == "prediction_window"
    assert prediction_expired.terminal_prediction_window_expired is True
    assert prediction_expired.terminal_contract_reset_reason == ""

    reset_bus = D7RuntimeBus(_png_config())
    for index in range(3):
        reset_bus.evaluate_pair(
            _pair_input(
                timestamp_s=index * 0.1,
                observation=_observation(index * 0.1, center_x=320.0 + index),
            )
        )
    reset_binding = replace(
        _binding(),
        plan_id="plan-2",
        plan_version=2,
        owner_node_id="secondary-1",
    )
    contract_reset = reset_bus.evaluate_pair(
        replace(
            _pair_input(
                timestamp_s=0.3,
                observation=None,
                terminal_association=reacquire,
            ),
            binding=reset_binding,
            d4_permission=D4GuidancePermission(
                action="continue_center",
                target_node_id="secondary-1",
                new_plan_id="plan-2",
                new_plan_version=2,
            ),
        )
    )
    assert contract_reset.terminal_dropout_reason_scope == "contract_reset"
    assert contract_reset.terminal_contract_reset_reason == "binding_signature_changed"
    assert contract_reset.terminal_measured_lock_history_available is False
    assert contract_reset.terminal_measured_lock_ever_established is True

    summary = summarize_runtime_bus_outputs(
        [never_locked, prediction_expired, contract_reset]
    )
    assert summary["terminal_dropout_reason_scope_counts"] == {
        "measured_lock_not_established": 1,
        "prediction_window": 1,
        "contract_reset": 1,
    }
    assert summary["terminal_contract_reset_reason_counts"] == {
        "binding_signature_changed": 1
    }


def test_bounded_coast_rejects_changed_local_identity() -> None:
    bus = D7RuntimeBus(_png_config())
    for index in range(3):
        bus.evaluate_pair(
            _pair_input(
                timestamp_s=index * 0.1,
                observation=_observation(index * 0.1, center_x=320.0 + index),
            )
        )
    reacquire = _terminal_association()
    reacquire.update(decision_state="reacquire", local_track_id="BT-2")

    blocked = bus.evaluate_pair(
        _pair_input(
            timestamp_s=0.3,
            observation=None,
            terminal_association=reacquire,
        )
    )

    assert blocked.raw_terminal_gate_allowed is False
    assert blocked.effective_terminal_contract_allowed is False
    assert blocked.terminal_coast_contract_allowed is False
    assert blocked.terminal_delivery_reason == "terminal_coast_local_identity_mismatch"
    assert blocked.effective_control_authorized is False
    assert blocked.selected_velocity_ned is None


def _png_config() -> PngGuidanceConfig:
    return PngGuidanceConfig(
        dt_s=0.1,
        min_bbox_area_ratio=0.0001,
        min_stable_frames=1,
        edge_margin_ratio=0.01,
        max_los_rate_variance_radps2=10.0,
        los_rate_window=2,
        max_visual_latency_s=1.0,
        min_maneuver_margin=0.0,
        law="png_vm",
    )


def _observation(
    timestamp_s: float,
    *,
    center_x: float,
    local_track_id: str = "BT-1",
) -> VisionGuidanceObservation:
    return VisionGuidanceObservation(
        timestamp_s=timestamp_s,
        frame_timestamp_s=timestamp_s,
        bbox_xyxy=(center_x - 20.0, 220.0, center_x + 20.0, 260.0),
        detection_confidence=0.95,
        local_track_id=local_track_id,
        assigned_global_track_id="G1",
    )


def _kinematics() -> dict[str, object]:
    return {
        "current_heading_rad": 0.0,
        "current_speed_mps": 8.0,
        "intercept_speed_mps": 8.0,
        "relative_position_ned": (30.0, 0.0, 0.0),
        "relative_velocity_ned": (-5.0, 0.0, 0.0),
    }


def _binding() -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id="plan-1",
        plan_version=1,
        owner_node_id="center",
        assignment_id="assign-R1-G1",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id="G1",
        track_version=9,
        authorization_state="approved",
    )


def _terminal_association() -> dict[str, object]:
    return {
        "resource_id": "R1",
        "assigned_global_track_id": "G1",
        "local_track_id": "BT-1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 9,
        "metadata": {"execution_gate_pass": True},
    }


def _pair_input(
    *,
    timestamp_s: float,
    observation: VisionGuidanceObservation | None,
    terminal_association: dict[str, object] | None = None,
    d4_permission: D4GuidancePermission | None = None,
) -> D7RuntimePairInput:
    binding = _binding()
    return D7RuntimePairInput(
        binding=binding,
        d4_permission=d4_permission
        or D4GuidancePermission(
            action="continue_center",
            target_node_id="center",
            new_plan_id=binding.plan_id,
            new_plan_version=binding.plan_version,
        ),
        terminal_association=terminal_association or _terminal_association(),
        observation=observation,
        timestamp_s=timestamp_s,
        terminal_locked=True,
        **_kinematics(),
    )


def _pair_input_for_r2(*, timestamp_s: float) -> D7RuntimePairInput:
    binding = AssignmentGuidanceBinding(
        plan_id="plan-1",
        plan_version=1,
        owner_node_id="center",
        assignment_id="assign-R2-G2",
        resource_id="R2",
        vehicle_name="Interceptor_R2",
        assigned_global_track_id="G2",
        track_version=10,
        authorization_state="approved",
    )
    observation = VisionGuidanceObservation(
        timestamp_s=timestamp_s,
        frame_timestamp_s=timestamp_s,
        bbox_xyxy=(302.0, 220.0, 342.0, 260.0),
        detection_confidence=0.95,
        local_track_id="BT-2",
        assigned_global_track_id="G2",
    )
    return D7RuntimePairInput(
        binding=binding,
        d4_permission=D4GuidancePermission(
            action="continue_center",
            target_node_id="center",
            new_plan_id=binding.plan_id,
            new_plan_version=binding.plan_version,
        ),
        terminal_association={
            "resource_id": "R2",
            "assigned_global_track_id": "G2",
            "local_track_id": "BT-2",
            "decision_state": "locked",
            "friend_conflict_state": "none",
            "assignment_version": 10,
            "metadata": {"execution_gate_pass": True},
        },
        observation=observation,
        timestamp_s=timestamp_s,
        terminal_locked=True,
        **_kinematics(),
    )
