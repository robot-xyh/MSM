from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    D7RuntimeBus,
    D7RuntimePairInput,
    OptionalLos6DKalmanReplay,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    TerminalDeliveryConfig,
    TerminalDeliveryState,
    TerminalFilterAuditState,
    TerminalGuidanceDelivery,
    TerminalLifecycleContext,
    VisionGuidanceObservation,
)


def test_png_ttc_uses_delivery_area_ema_and_rejects_jump_and_clipping() -> None:
    guidance = SimpleFlightPngGuidanceFilter(_png_config(law="png_ttc"))

    first = guidance.evaluate(_observation(0.0, size_px=40.0), **_kinematics())
    second = guidance.evaluate(_observation(0.1, size_px=44.0), **_kinematics())

    assert first.quality.ttc_valid is False
    assert first.quality.ttc_reject_reason == "area_not_expanding"
    assert second.quality.ttc_raw_area_px2 == pytest.approx(1936.0)
    assert second.quality.ttc_filtered_area_px2 == pytest.approx(1684.0)
    assert second.quality.ttc_area_dot_px2_s == pytest.approx(840.0)
    assert second.quality.ttc_s == pytest.approx(2.0 * 1684.0 / 840.0)
    assert second.quality.ttc_valid is True

    jump = guidance.evaluate(_observation(0.2, size_px=120.0), **_kinematics())
    assert jump.quality.ttc_valid is False
    assert jump.quality.ttc_reject_reason == "bbox_area_jump"
    assert jump.quality.terminal_switch_allowed is False

    clipped_observation = replace(
        _observation(0.3, size_px=40.0),
        bbox_xyxy=(0.0, 220.0, 40.0, 260.0),
    )
    clipped = guidance.evaluate(clipped_observation, **_kinematics())
    assert clipped.quality.ttc_reject_reason == "bbox_left_clipped"
    assert clipped.quality.terminal_switch_allowed is False


def test_png_vm_does_not_apply_ttc_validity_gate() -> None:
    guidance = SimpleFlightPngGuidanceFilter(_png_config(law="png_vm"))
    guidance.evaluate(_observation(0.0, size_px=40.0), **_kinematics())
    guidance.evaluate(_observation(0.1, size_px=40.0), **_kinematics())
    second = guidance.evaluate(_observation(0.2, size_px=40.0), **_kinematics())

    assert second.quality.ttc_valid is None
    assert second.quality.ttc_reject_reason == ""
    assert second.quality.terminal_switch_allowed is True
    assert second.guidance_law == "png_vm"


def test_local_track_and_plan_changes_emit_reset_and_do_not_inherit_history() -> None:
    bus = D7RuntimeBus(_png_config())
    for index in range(2):
        bus.evaluate_pair(_pair_input(index * 0.1, local_track_id="BT-1"))

    local_switch = bus.evaluate_pair(_pair_input(0.2, local_track_id="BT-2"))
    assert local_switch.terminal_lifecycle_reset is True
    assert "local_track_id" in local_switch.terminal_lifecycle_reset_reason
    assert local_switch.terminal_filter_audit_state == "reset"
    assert local_switch.stable_frame_count == 1

    plan_switch = bus.evaluate_pair(
        _pair_input(0.3, local_track_id="BT-2", plan_version=2)
    )
    assert plan_switch.terminal_lifecycle_reset is True
    assert plan_switch.terminal_lifecycle_reset_reason == "binding_signature_changed"
    assert plan_switch.terminal_filter_audit_state == "reset"

    global_switch_without_measurement = bus.evaluate_pair(
        _pair_input(
            0.4,
            local_track_id="BT-3",
            global_track_id="G2",
            observation=False,
        )
    )
    assert global_switch_without_measurement.terminal_delivery_state == "acquiring"
    assert global_switch_without_measurement.selected_velocity_ned is None


def test_innovation_spike_is_fail_closed_by_default() -> None:
    delivery = TerminalGuidanceDelivery(_png_config())
    context = _lifecycle()
    for index in range(3):
        delivery.evaluate(
            assigned_global_track_id="G1",
            timestamp_s=index * 0.1,
            observation=_observation(index * 0.1, center_x=320.0 + index),
            lifecycle_context=context,
            **_kinematics(),
        )

    rejected = delivery.evaluate(
        assigned_global_track_id="G1",
        timestamp_s=0.3,
        observation=_observation(0.3, center_x=600.0),
        lifecycle_context=context,
        soft_prediction_eligible=True,
        **_kinematics(),
    )

    assert rejected.command is None
    assert rejected.state == TerminalDeliveryState.EXPIRED
    assert rejected.filter_audit_state == TerminalFilterAuditState.INNOVATION_REJECTED
    assert rejected.filter_audit_reason == "image_kf_innovation_reject"


def test_soft_innovation_prediction_requires_explicit_enable_and_same_context() -> None:
    delivery = TerminalGuidanceDelivery(
        _png_config(),
        TerminalDeliveryConfig(soft_innovation_reject_prediction=True),
    )
    context = _lifecycle()
    for index in range(3):
        delivery.evaluate(
            assigned_global_track_id="G1",
            timestamp_s=index * 0.1,
            observation=_observation(index * 0.1, center_x=320.0 + index),
            lifecycle_context=context,
            soft_prediction_eligible=True,
            **_kinematics(),
        )

    predicted = delivery.evaluate(
        assigned_global_track_id="G1",
        timestamp_s=0.3,
        observation=_observation(0.3, center_x=600.0),
        lifecycle_context=context,
        soft_prediction_eligible=True,
        **_kinematics(),
    )
    assert predicted.state == TerminalDeliveryState.IMAGE_KF_PREDICT
    assert predicted.command is not None
    assert predicted.using_extrapolation is True
    assert predicted.filter_audit_state == TerminalFilterAuditState.PREDICTED
    assert predicted.filter_audit_reason == "image_kf_soft_reject_predict"

    changed_context = replace(context, local_track_id="BT-2")
    reset = delivery.evaluate(
        assigned_global_track_id="G1",
        timestamp_s=0.4,
        observation=_observation(0.4, center_x=600.0, local_track_id="BT-2"),
        lifecycle_context=changed_context,
        soft_prediction_eligible=True,
        **_kinematics(),
    )
    assert reset.filter_audit_state == TerminalFilterAuditState.RESET
    assert reset.using_extrapolation is False


def test_one_to_five_dropout_frames_remain_bounded() -> None:
    delivery = TerminalGuidanceDelivery(_png_config())
    for index in range(3):
        delivery.evaluate(
            assigned_global_track_id="G1",
            timestamp_s=index * 0.1,
            observation=_observation(index * 0.1, center_x=320.0 + index),
            lifecycle_context=_lifecycle(),
            **_kinematics(),
        )

    results = [
        delivery.evaluate(
            assigned_global_track_id="G1",
            timestamp_s=0.3 + index * 0.1,
            observation=None,
            lifecycle_context=_lifecycle(),
            **_kinematics(),
        )
        for index in range(5)
    ]

    assert [result.state for result in results[:2]] == [
        TerminalDeliveryState.IMAGE_KF_PREDICT,
        TerminalDeliveryState.IMAGE_KF_PREDICT,
    ]
    assert all(result.state == TerminalDeliveryState.BLIND_PUSH for result in results[2:])
    expired = delivery.evaluate(
        assigned_global_track_id="G1",
        timestamp_s=0.8,
        observation=None,
        lifecycle_context=_lifecycle(),
        **_kinematics(),
    )
    assert expired.state == TerminalDeliveryState.EXPIRED
    assert expired.command is None
    assert expired.filter_audit_state == TerminalFilterAuditState.EXPIRED


@pytest.mark.parametrize(
    "terminal_metadata,friend_state,expected_reason",
    [
        ({"execution_gate_pass": True, "duplicate_terminal_lock_risk": True}, "none", "duplicate_lock_conflict"),
        ({"execution_gate_pass": True}, "verified_friend", "friend_conflict"),
    ],
)
def test_friend_or_duplicate_conflict_clears_coast(
    terminal_metadata: dict[str, object],
    friend_state: str,
    expected_reason: str,
) -> None:
    bus = D7RuntimeBus(_png_config())
    for index in range(3):
        bus.evaluate_pair(_pair_input(index * 0.1))
    terminal = _terminal_association("BT-1")
    terminal["friend_conflict_state"] = friend_state
    terminal["metadata"] = terminal_metadata

    blocked = bus.evaluate_pair(
        _pair_input(0.3, observation=False, terminal_association=terminal)
    )
    assert blocked.terminal_contract_reject_reason == expected_reason
    assert blocked.terminal_coast_contract_allowed is False
    assert blocked.selected_velocity_ned is None
    assert blocked.terminal_delivery_state == "expired"


def test_delivery_trend_coast_is_optional_horizontal_and_capped() -> None:
    disabled = _delivery_with_moving_los(delivery_trend_coast=False)
    enabled = _delivery_with_moving_los(delivery_trend_coast=True)

    disabled_coast = disabled.evaluate(
        assigned_global_track_id="G1",
        timestamp_s=0.3,
        observation=None,
        lifecycle_context=_lifecycle(),
        **_kinematics(),
    )
    enabled_coast = enabled.evaluate(
        assigned_global_track_id="G1",
        timestamp_s=0.3,
        observation=None,
        lifecycle_context=_lifecycle(),
        **_kinematics(),
    )

    assert disabled_coast.trend_coast_applied is False
    assert enabled_coast.trend_coast_applied is True
    trend = np.asarray(enabled_coast.trend_coast_velocity_ned)
    assert trend[2] == pytest.approx(0.0)
    assert np.linalg.norm(trend[:2]) <= 0.75 + 1.0e-9
    assert np.linalg.norm(np.asarray(enabled_coast.command.velocity_ned)[:2]) <= 8.0 + 1.0e-9


def test_optional_6d_los_replay_prefers_direct_camera_to_ned_rotation() -> None:
    backend = OptionalLos6DKalmanReplay(_png_config())
    metadata = {
        "camera_to_ned_rotation": np.array(
            [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]
        ).tolist(),
        "camera_to_body_rotation": np.eye(3).tolist(),
        "body_to_ned_rotation": np.eye(3).tolist(),
        "attitude_timestamp": 1.0,
    }

    result = backend.evaluate(replace(_observation(1.0), metadata=metadata))

    assert result.available is True
    assert result.lambda_ned == pytest.approx((1.0, 0.0, 0.0))


def test_optional_6d_los_replay_accepts_split_rotations() -> None:
    backend = OptionalLos6DKalmanReplay(_png_config())
    metadata = {
        "camera_to_body_rotation": np.eye(3).tolist(),
        "body_to_ned_rotation": np.eye(3).tolist(),
        "attitude_timestamp_s": 1.0,
    }

    result = backend.evaluate(replace(_observation(1.0), metadata=metadata))

    assert result.available is True
    assert result.lambda_ned == pytest.approx((0.0, 0.0, 1.0))


def test_optional_6d_los_replay_reports_missing_rotation() -> None:
    backend = OptionalLos6DKalmanReplay(_png_config())

    result = backend.evaluate(
        replace(
            _observation(1.0),
            metadata={"attitude_timestamp": 1.0},
        )
    )

    assert result.available is False
    assert result.reason == "camera_to_ned_rotation_unavailable"


def test_optional_6d_los_replay_rejects_unsynchronized_direct_rotation() -> None:
    backend = OptionalLos6DKalmanReplay(_png_config())
    metadata = {
        "camera_to_ned_rotation": np.eye(3).tolist(),
        "attitude_timestamp": 1.0,
    }

    result = backend.evaluate(
        replace(
            _observation(1.2),
            metadata=metadata,
        )
    )

    assert result.available is False
    assert result.reason == "attitude_timestamp_unsynchronized"


def _png_config(*, law: str = "png_vm") -> PngGuidanceConfig:
    return PngGuidanceConfig(
        dt_s=0.1,
        min_bbox_area_ratio=0.0001,
        min_stable_frames=1,
        edge_margin_ratio=0.0,
        max_los_rate_variance_radps2=100.0,
        los_rate_window=2,
        max_visual_latency_s=1.0,
        min_maneuver_margin=-10.0,
        law=law,
    )


def _observation(
    timestamp_s: float,
    *,
    center_x: float = 320.0,
    size_px: float = 40.0,
    local_track_id: str = "BT-1",
) -> VisionGuidanceObservation:
    half = 0.5 * size_px
    return VisionGuidanceObservation(
        timestamp_s=timestamp_s,
        frame_timestamp_s=timestamp_s,
        bbox_xyxy=(center_x - half, 240.0 - half, center_x + half, 240.0 + half),
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


def _lifecycle() -> TerminalLifecycleContext:
    return TerminalLifecycleContext("R1", "G1", "BT-1", "center", 1)


def _binding(global_track_id: str = "G1", plan_version: int = 1) -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id="plan-1",
        plan_version=plan_version,
        owner_node_id="center",
        assignment_id=f"assign-R1-{global_track_id}",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id=global_track_id,
        track_version=9,
        authorization_state="approved",
    )


def _terminal_association(local_track_id: str, global_track_id: str = "G1") -> dict[str, object]:
    return {
        "resource_id": "R1",
        "assigned_global_track_id": global_track_id,
        "local_track_id": local_track_id,
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 9,
        "metadata": {"execution_gate_pass": True},
    }


def _pair_input(
    timestamp_s: float,
    *,
    local_track_id: str = "BT-1",
    global_track_id: str = "G1",
    plan_version: int = 1,
    observation: bool = True,
    terminal_association: dict[str, object] | None = None,
) -> D7RuntimePairInput:
    binding = _binding(global_track_id, plan_version)
    visual_observation = (
        replace(
            _observation(timestamp_s, local_track_id=local_track_id),
            assigned_global_track_id=global_track_id,
        )
        if observation
        else None
    )
    return D7RuntimePairInput(
        binding=binding,
        d4_permission=D4GuidancePermission(
            action="continue_center",
            target_node_id="center",
            new_plan_id=binding.plan_id,
            new_plan_version=binding.plan_version,
        ),
        terminal_association=terminal_association
        or _terminal_association(local_track_id, global_track_id),
        observation=visual_observation,
        timestamp_s=timestamp_s,
        terminal_locked=True,
        **_kinematics(),
    )


def _delivery_with_moving_los(*, delivery_trend_coast: bool) -> TerminalGuidanceDelivery:
    delivery = TerminalGuidanceDelivery(
        _png_config(),
        TerminalDeliveryConfig(
            consecutive_loss_frames=1,
            delivery_trend_coast=delivery_trend_coast,
            delivery_trend_coast_cap_mps=0.75,
        ),
    )
    for index, center_x in enumerate((315.0, 320.0, 330.0)):
        delivery.evaluate(
            assigned_global_track_id="G1",
            timestamp_s=index * 0.1,
            observation=_observation(index * 0.1, center_x=center_x),
            lifecycle_context=_lifecycle(),
            **_kinematics(),
        )
    return delivery
