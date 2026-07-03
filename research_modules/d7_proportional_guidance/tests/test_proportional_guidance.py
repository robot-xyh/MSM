from __future__ import annotations

import math

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    GuidanceConfig,
    GuidanceMode,
    GuidanceState,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
    compute_proportional_navigation_command,
    evaluate_terminal_png_contract,
    simulate_guidance_episode,
)


def test_pure_pn_reduces_range() -> None:
    config = GuidanceConfig(
        dt_s=0.05,
        max_duration_s=4.0,
        terminal_switch_range_m=1.0,
        navigation_constant=3.0,
        max_lateral_accel_mps2=80.0,
        max_turn_rate_radps=1.0,
        stop_at_intercept_radius=False,
    )
    pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (140.0, 0.0))
    target = GuidanceState("T0", 0.0, (1000.0, 160.0), (-20.0, 0.0))

    records, summary = simulate_guidance_episode(pursuer, target, config)

    assert records
    assert all(record.mode == GuidanceMode.RADAR_MIDCOURSE for record in records)
    assert summary["final_range_m"] < summary["initial_range_m"]
    assert records[-1].range_m < records[0].range_m * 0.6


def test_terminal_vision_pn_switches_mode() -> None:
    config = GuidanceConfig(
        dt_s=0.1,
        max_duration_s=6.0,
        terminal_switch_range_m=650.0,
        navigation_constant=3.0,
        max_lateral_accel_mps2=70.0,
        max_turn_rate_radps=1.0,
        stop_at_intercept_radius=False,
    )
    pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (160.0, 0.0))
    target = GuidanceState("T0", 0.0, (900.0, 100.0), (-10.0, 0.0))

    records, summary = simulate_guidance_episode(pursuer, target, config)
    modes = [record.mode for record in records]

    assert GuidanceMode.RADAR_MIDCOURSE in modes
    assert GuidanceMode.VISION_TERMINAL in modes
    assert summary["terminal_mode_entered"] is True
    assert any(record.mode_switch for record in records)
    assert records[-1].mode == GuidanceMode.VISION_TERMINAL


def test_acceleration_and_turn_rate_limits_apply() -> None:
    pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (100.0, 0.0))
    target = GuidanceState("T0", 0.0, (200.0, 800.0), (-300.0, 0.0))

    command = compute_proportional_navigation_command(
        pursuer=pursuer,
        target=target,
        dt_s=0.1,
        navigation_constant=5.0,
        mode=GuidanceMode.RADAR_MIDCOURSE,
        max_lateral_accel_mps2=8.0,
        max_turn_rate_radps=0.03,
    )

    assert abs(command.commanded_lateral_accel_mps2) > 8.0
    assert abs(command.limited_turn_rate_radps) <= 0.03 + 1e-12
    assert abs(command.limited_lateral_accel_mps2) <= 3.0 + 1e-12
    assert command.is_saturated


def test_records_include_guidance_geometry_fields() -> None:
    config = GuidanceConfig(
        dt_s=0.1,
        max_duration_s=1.0,
        terminal_switch_range_m=500.0,
        stop_at_intercept_radius=False,
    )
    records, _summary = simulate_guidance_episode(config=config)

    assert records
    for record in records:
        assert isinstance(record.mode, GuidanceMode)
        assert record.range_m >= 0.0
        assert math.isfinite(record.los_angle_rad)
        assert math.isfinite(record.los_rate_radps)
        assert math.isfinite(record.closing_speed_mps)
        data = record.as_dict()
        assert {"mode", "range_m", "los_angle_rad", "closing_speed_mps"} <= set(data)


def test_visual_png_gate_rejects_small_single_frame_detection() -> None:
    tracker = SimpleFlightPngGuidanceFilter(
        PngGuidanceConfig(
            image_width_px=640,
            image_height_px=480,
            min_bbox_area_ratio=0.01,
            min_stable_frames=2,
            law="png_vm",
        )
    )
    obs = VisionGuidanceObservation(
        timestamp_s=0.0,
        bbox_xyxy=(318.0, 238.0, 322.0, 242.0),
        detection_confidence=0.95,
        local_track_id="L1",
        assigned_global_track_id="G1",
    )

    command = tracker.evaluate(
        obs,
        current_heading_rad=0.0,
        current_speed_mps=6.0,
        intercept_speed_mps=6.0,
        relative_position_ned=(20.0, 0.0, 0.0),
        relative_velocity_ned=(-4.0, 0.0, 0.0),
    )

    assert command.quality.terminal_switch_allowed is False
    assert command.quality.camera_quality_gate_passed is False
    assert command.quality.reject_reason == "bbox_area_too_small"


def test_visual_png_gate_passes_after_stable_quality_observations() -> None:
    tracker = SimpleFlightPngGuidanceFilter(
        PngGuidanceConfig(
            dt_s=0.1,
            image_width_px=640,
            image_height_px=480,
            focal_length_px=320.0,
            min_bbox_area_ratio=0.001,
            min_stable_frames=2,
            edge_margin_ratio=0.01,
            law="png_vm",
        )
    )
    observations = [
        VisionGuidanceObservation(
            timestamp_s=0.0,
            bbox_xyxy=(300.0, 220.0, 360.0, 280.0),
            detection_confidence=0.9,
            local_track_id="L1",
            assigned_global_track_id="G1",
        ),
        VisionGuidanceObservation(
            timestamp_s=0.1,
            bbox_xyxy=(302.0, 220.0, 362.0, 280.0),
            detection_confidence=0.9,
            local_track_id="L1",
            assigned_global_track_id="G1",
        ),
        VisionGuidanceObservation(
            timestamp_s=0.2,
            bbox_xyxy=(304.0, 220.0, 364.0, 280.0),
            detection_confidence=0.9,
            local_track_id="L1",
            assigned_global_track_id="G1",
        ),
    ]

    command = None
    for obs in observations:
        command = tracker.evaluate(
            obs,
            current_heading_rad=0.0,
            current_speed_mps=6.0,
            intercept_speed_mps=6.0,
            relative_position_ned=(20.0, 1.0, 0.0),
            relative_velocity_ned=(-4.0, 0.0, 0.0),
        )

    assert command is not None
    assert command.quality.camera_quality_gate_passed is True
    assert command.quality.los_quality_gate_passed is True
    assert command.quality.maneuver_margin_gate_passed is True
    assert command.quality.terminal_switch_allowed is True
    assert command.guidance_law == "png_vm"


def test_visual_png_gate_rejects_when_not_closing() -> None:
    tracker = SimpleFlightPngGuidanceFilter(
        PngGuidanceConfig(
            dt_s=0.1,
            min_bbox_area_ratio=0.001,
            min_stable_frames=2,
            edge_margin_ratio=0.01,
        )
    )
    command = None
    for timestamp in (0.0, 0.1, 0.2):
        command = tracker.evaluate(
            VisionGuidanceObservation(
                timestamp_s=timestamp,
                bbox_xyxy=(300.0, 220.0, 360.0, 280.0),
                detection_confidence=0.9,
                local_track_id="L1",
                assigned_global_track_id="G1",
            ),
            current_heading_rad=0.0,
            current_speed_mps=6.0,
            intercept_speed_mps=6.0,
            relative_position_ned=(20.0, 0.0, 0.0),
            relative_velocity_ned=(2.0, 0.0, 0.0),
        )

    assert command is not None
    assert command.quality.terminal_switch_allowed is False
    assert command.quality.maneuver_margin_gate_passed is False
    assert command.quality.reject_reason == "not_closing"


def test_terminal_png_contract_allows_only_consistent_locked_handoff() -> None:
    binding = _binding()
    terminal = {
        "assigned_global_track_id": "G1",
        "local_track_id": "R1:0:L1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 4,
    }
    observation = {"assigned_global_track_id": "G1"}

    decision = evaluate_terminal_png_contract(
        binding=binding,
        d4_permission=D4GuidancePermission(action="continue_center"),
        terminal_association=terminal,
        observation=observation,
        timestamp_s=1.0,
        resource_id="R1",
    )

    assert decision.allowed is True
    assert decision.reject_reason == ""
    assert decision.plan_id == "plan-1"
    assert decision.d5_decision_state == "locked"


def test_terminal_png_contract_rejects_non_locked_d5_state() -> None:
    terminal = {
        "assigned_global_track_id": "G1",
        "decision_state": "ambiguous",
        "friend_conflict_state": "none",
        "assignment_version": 4,
    }

    decision = evaluate_terminal_png_contract(
        binding=_binding(),
        d4_permission=D4GuidancePermission(action="continue_center"),
        terminal_association=terminal,
    )

    assert decision.allowed is False
    assert decision.reject_reason == "d5_not_locked"


def test_terminal_png_contract_rejects_identity_and_version_mismatch() -> None:
    wrong_id = {
        "assigned_global_track_id": "G2",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 4,
    }
    wrong_version = {
        "assigned_global_track_id": "G1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 5,
    }

    id_decision = evaluate_terminal_png_contract(
        binding=_binding(),
        d4_permission=D4GuidancePermission(action="continue_center"),
        terminal_association=wrong_id,
    )
    version_decision = evaluate_terminal_png_contract(
        binding=_binding(),
        d4_permission=D4GuidancePermission(action="continue_center"),
        terminal_association=wrong_version,
    )

    assert id_decision.reject_reason == "terminal_identity_mismatch"
    assert version_decision.reject_reason == "assignment_version_mismatch"


def test_terminal_png_contract_rejects_unauthorized_and_d4_hold() -> None:
    terminal = {
        "assigned_global_track_id": "G1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 4,
    }

    unauthorized = evaluate_terminal_png_contract(
        binding=_binding(authorization_state="required"),
        d4_permission=D4GuidancePermission(action="continue_center"),
        terminal_association=terminal,
    )
    d4_hold = evaluate_terminal_png_contract(
        binding=_binding(),
        d4_permission=D4GuidancePermission(action="hold_for_review", requires_human_review=True),
        terminal_association=terminal,
    )
    d4_reassign = evaluate_terminal_png_contract(
        binding=_binding(),
        d4_permission=D4GuidancePermission(action="request_center_replan"),
        terminal_association=terminal,
    )

    assert unauthorized.reject_reason == "assignment_not_authorized"
    assert d4_hold.reject_reason == "d4_hold_for_review"
    assert d4_reassign.reject_reason == "d4_reassign_pending"


def test_terminal_png_contract_rejects_d4_terminal_inconsistent() -> None:
    terminal = {
        "assigned_global_track_id": "G1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 4,
    }

    decision = evaluate_terminal_png_contract(
        binding=_binding(),
        d4_permission=D4GuidancePermission(action="continue_center", terminal_consistent=False),
        terminal_association=terminal,
    )

    assert decision.allowed is False
    assert decision.reject_reason == "d4_terminal_inconsistent"


def _binding(authorization_state: str = "approved") -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id="plan-1",
        plan_version=2,
        assignment_id="assign-1",
        resource_id="R1",
        vehicle_name="Interceptor1",
        assigned_global_track_id="G1",
        track_version=4,
        authorization_state=authorization_state,
        target_actor_name="MSM_TargetActor_1",
        target_object_id="TGT-001",
        target_mesh_aliases=("MSM_TargetActor_1", "TGT-001"),
    )
