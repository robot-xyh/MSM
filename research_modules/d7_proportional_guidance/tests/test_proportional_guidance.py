from __future__ import annotations

from dataclasses import replace
import math

import pytest

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    BBOX_LOS_REPLAY_BOUNDARY,
    D7_GUIDANCE_CALIBRATION_BOUNDARY,
    D7_RUNTIME_BUS_BOUNDARY,
    D7RuntimeBus,
    D7RuntimePairInput,
    D4GuidancePermission,
    DEFAULT_CALIBRATION_THRESHOLD_VERSION,
    DEFAULT_COMPARISON_STRATEGIES,
    GuidanceConfig,
    GuidanceMode,
    GuidanceState,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
    bbox_replay_detection_to_observation,
    compute_proportional_navigation_command,
    compute_pure_pursuit_command,
    compute_three_dimensional_pn_benchmark,
    evaluate_terminal_png_contract,
    evaluate_bbox_los_replay,
    guidance_mode_from_terminal_contract,
    run_guidance_strategy_comparison,
    simulate_guidance_episode,
    summarize_guidance_calibration,
    summarize_guidance_strategy_comparison,
    summarize_runtime_bus_outputs,
    summarize_terminal_switch_quality,
    terminal_switch_allowed_rate,
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


def test_pure_pursuit_baseline_reduces_range_without_external_dependency() -> None:
    config = GuidanceConfig(
        dt_s=0.05,
        max_duration_s=4.0,
        terminal_switch_range_m=1.0,
        max_turn_rate_radps=1.0,
        stop_at_intercept_radius=False,
        guidance_law="pure_pursuit",
    )
    pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (140.0, 0.0))
    target = GuidanceState("T0", 0.0, (1000.0, 160.0), (-20.0, 0.0))

    records, summary = simulate_guidance_episode(pursuer, target, config)

    assert records
    assert summary["guidance_law"] == "pure_pursuit"
    assert summary["final_range_m"] < summary["initial_range_m"]
    assert all(record.observation["source"] == "global_track" for record in records)


def test_pure_pursuit_command_points_toward_los() -> None:
    pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (100.0, 0.0))
    target = GuidanceState("T0", 0.0, (100.0, 100.0), (0.0, 0.0))

    command = compute_pure_pursuit_command(
        pursuer=pursuer,
        target=target,
        dt_s=0.1,
        max_turn_rate_radps=0.5,
    )

    assert command.metadata["guidance_law"] == "pure_pursuit"
    assert command.desired_heading_rad > command.current_heading_rad
    assert abs(command.limited_turn_rate_radps) <= 0.5 + 1e-12


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


def test_visual_png_filters_los_rate_spike_before_near_range_command() -> None:
    config = replace(
        _tuned_png_config(),
        los_rate_filter_alpha=0.25,
        max_los_rate_radps=0.4,
        max_los_rate_step_radps=0.08,
        max_los_rate_variance_radps2=0.5,
        reject_los_rate_outliers=True,
    )
    tracker = SimpleFlightPngGuidanceFilter(config)
    centers_px = (320.0, 322.0, 324.0, 450.0)
    commands = []

    for index, center_x in enumerate(centers_px):
        commands.append(
            tracker.evaluate(
                VisionGuidanceObservation(
                    timestamp_s=index * config.dt_s,
                    bbox_xyxy=(center_x - 36.0, 204.0, center_x + 36.0, 276.0),
                    detection_confidence=0.92,
                    local_track_id="R1:BT:stable",
                    assigned_global_track_id="G1",
                ),
                current_heading_rad=0.0,
                current_speed_mps=8.0,
                intercept_speed_mps=8.0,
                relative_position_ned=(18.0, 0.4, 0.0),
                relative_velocity_ned=(-6.0, 0.0, 0.0),
            )
        )

    stable_command = commands[2]
    spike_command = commands[3]

    assert stable_command.quality.terminal_switch_allowed is True
    assert abs(stable_command.turn_rate_radps) < 0.1
    assert abs(spike_command.quality.raw_los_rate_radps) > 3.0
    assert abs(spike_command.quality.filtered_los_rate_radps) <= config.max_los_rate_radps
    assert spike_command.quality.los_rate_clamped is True
    assert spike_command.quality.los_rate_outlier_rejected is True
    assert spike_command.quality.reject_reason == "los_rate_spike_rejected"
    assert spike_command.quality.terminal_switch_allowed is False
    assert abs(spike_command.turn_rate_radps) <= config.max_turn_rate_radps


def test_tuned_visual_png_allows_terminal_switch_after_stable_los_window() -> None:
    config = _tuned_png_config()
    commands = _evaluate_tuned_png_sequence(
        config,
        [
            VisionGuidanceObservation(
                timestamp_s=index * config.dt_s,
                bbox_xyxy=(288.0, 208.0, 352.0, 272.0),
                detection_confidence=0.9,
                local_track_id="L1",
                assigned_global_track_id="G1",
            )
            for index in range(6)
        ],
    )

    quality = commands[-1].quality

    assert quality.camera_quality_gate_passed is True
    assert quality.los_quality_gate_passed is True
    assert quality.maneuver_margin_gate_passed is True
    assert quality.terminal_switch_allowed is True
    assert quality.reject_reason == ""
    assert quality.stable_frame_count == 6
    assert quality.edge_margin_ratio > config.edge_margin_ratio
    assert quality.closing_speed_mps > config.min_closing_speed_mps
    assert quality.los_rate_variance_radps2 <= config.max_los_rate_variance_radps2
    assert terminal_switch_allowed_rate(commands) == pytest.approx(4 / 6)
    assert summarize_terminal_switch_quality(commands) == {
        "sample_count": 6,
        "allowed_count": 4,
        "rejected_count": 2,
        "terminal_switch_allowed_rate": pytest.approx(4 / 6),
        "reject_reasons": {
            "stable_frame_count_low": 1,
            "los_rate_window_too_short": 1,
        },
    }


def test_tuned_visual_png_rejects_edge_bbox_with_stable_reason() -> None:
    config = _tuned_png_config()
    commands = _evaluate_tuned_png_sequence(
        config,
        [
            VisionGuidanceObservation(
                timestamp_s=index * config.dt_s,
                bbox_xyxy=(4.0, 208.0, 68.0, 272.0),
                detection_confidence=0.9,
                local_track_id="L1",
                assigned_global_track_id="G1",
            )
            for index in range(6)
        ],
    )

    assert terminal_switch_allowed_rate(commands) == 0.0
    assert {command.quality.reject_reason for command in commands} == {"bbox_near_image_edge"}
    assert all(command.quality.terminal_switch_allowed is False for command in commands)
    assert all(command.quality.camera_quality_gate_passed is False for command in commands)


def test_tuned_visual_png_rejects_unstable_bbox_with_stable_reason() -> None:
    config = _tuned_png_config()
    commands = _evaluate_tuned_png_sequence(
        config,
        [
            VisionGuidanceObservation(
                timestamp_s=index * config.dt_s,
                bbox_xyxy=(288.0, 208.0, 352.0, 272.0),
                detection_confidence=0.9,
                local_track_id=f"L{index}",
                assigned_global_track_id="G1",
            )
            for index in range(6)
        ],
    )

    assert terminal_switch_allowed_rate(commands) == 0.0
    assert {command.quality.reject_reason for command in commands} == {"stable_frame_count_low"}
    assert all(command.quality.terminal_switch_allowed is False for command in commands)
    assert all(command.quality.stable_frame_count == 1 for command in commands)


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


def test_2v2_active_secondary_visual_png_requires_effective_secondary_plan() -> None:
    primary_binding = _binding_for_pair("R1", "G1", 21)
    primary_terminal = {
        "assigned_global_track_id": "G1",
        "local_track_id": "R1:0:L1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 21,
    }

    degraded = evaluate_terminal_png_contract(
        binding=primary_binding,
        d4_permission=D4GuidancePermission(
            action="degrade_to_secondary",
            target_node_id="secondary-1",
            new_plan_id="plan-2v2-secondary",
            new_plan_version=2,
        ),
        terminal_association=primary_terminal,
        observation={"assigned_global_track_id": "G1"},
        timestamp_s=2.0,
        resource_id="R1",
    )

    assert degraded.allowed is False
    assert degraded.reject_reason == "d4_reassign_pending"
    assert guidance_mode_from_terminal_contract(
        degraded,
        handover_pending=True,
        terminal_locked=False,
    ) == GuidanceMode.ABORT_REVOKE

    secondary_binding = AssignmentGuidanceBinding(
        plan_id="plan-2v2-secondary",
        plan_version=2,
        owner_node_id="secondary-1",
        assignment_id="assign-R2-G1",
        resource_id="R2",
        vehicle_name="Interceptor_R2",
        assigned_global_track_id="G1",
        track_version=22,
        authorization_state="approved",
        target_actor_name="MSM_TargetActor_1",
        target_object_id="G1",
        target_mesh_aliases=("MSM_TargetActor_1", "G1"),
    )
    secondary_terminal = {
        "assigned_global_track_id": "G1",
        "local_track_id": "R2:0:L1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 22,
    }
    stale_plan = evaluate_terminal_png_contract(
        binding=secondary_binding,
        d4_permission=D4GuidancePermission(
            action="request_secondary_assist",
            target_node_id="secondary-1",
            new_plan_id="plan-2v2-secondary",
            new_plan_version=1,
        ),
        terminal_association=secondary_terminal,
        observation={"assigned_global_track_id": "G1"},
        timestamp_s=2.2,
        resource_id="R2",
    )

    assert stale_plan.allowed is False
    assert stale_plan.reject_reason == "d4_plan_mismatch"

    active_secondary = evaluate_terminal_png_contract(
        binding=secondary_binding,
        d4_permission=D4GuidancePermission(
            action="request_secondary_assist",
            target_node_id="secondary-1",
            new_plan_id="plan-2v2-secondary",
            new_plan_version=2,
        ),
        terminal_association=secondary_terminal,
        observation={"assigned_global_track_id": "G1"},
        timestamp_s=2.3,
        resource_id="R2",
    )
    continue_center = evaluate_terminal_png_contract(
        binding=secondary_binding,
        d4_permission=D4GuidancePermission(
            action="continue_center",
            target_node_id="secondary-1",
            new_plan_id="plan-2v2-secondary",
            new_plan_version=2,
        ),
        terminal_association=secondary_terminal,
        observation={"assigned_global_track_id": "G1"},
        timestamp_s=2.4,
        resource_id="R2",
    )

    assert active_secondary.allowed is True
    assert continue_center.allowed is True

    tracker = SimpleFlightPngGuidanceFilter(_tuned_png_config())
    command = None
    for index, half_size in enumerate((30.0, 34.0, 38.0), start=1):
        command = tracker.evaluate(
            VisionGuidanceObservation(
                timestamp_s=2.4 + index * 0.1,
                bbox_xyxy=(320.0 - half_size, 240.0 - half_size, 320.0 + half_size, 240.0 + half_size),
                detection_confidence=0.9,
                local_track_id="R2:0:L1",
                assigned_global_track_id="G1",
            ),
            current_heading_rad=0.0,
            current_speed_mps=8.0,
            intercept_speed_mps=8.0,
            relative_position_ned=(32.0, 0.5, 0.0),
            relative_velocity_ned=(-5.0, 0.0, 0.0),
        )

    assert command is not None
    assert command.guidance_law == "png_vm"
    assert command.quality.terminal_switch_allowed is True
    assert command.quality.ttc_s is not None
    assert guidance_mode_from_terminal_contract(
        active_secondary,
        handover_pending=True,
        terminal_locked=True,
    ) == GuidanceMode.VISION_TERMINAL


def test_terminal_contract_maps_reject_reasons_to_guidance_log_modes() -> None:
    ambiguous = evaluate_terminal_png_contract(
        binding=_binding(),
        d4_permission=D4GuidancePermission(action="continue_center"),
        terminal_association={
            "assigned_global_track_id": "G1",
            "decision_state": "ambiguous",
            "friend_conflict_state": "none",
            "assignment_version": 4,
        },
    )
    friend_hold = evaluate_terminal_png_contract(
        binding=_binding(),
        d4_permission=D4GuidancePermission(action="continue_center"),
        terminal_association={
            "assigned_global_track_id": "G1",
            "decision_state": "locked",
            "friend_conflict_state": "verified_friend_overlap",
            "assignment_version": 4,
        },
    )
    revoked = evaluate_terminal_png_contract(
        binding=_binding(),
        d4_permission=D4GuidancePermission(action="request_center_replan"),
        terminal_association={
            "assigned_global_track_id": "G1",
            "decision_state": "locked",
            "friend_conflict_state": "none",
            "assignment_version": 4,
        },
    )

    assert guidance_mode_from_terminal_contract(
        ambiguous,
        handover_pending=True,
        terminal_locked=False,
    ) == GuidanceMode.REACQUIRE
    assert guidance_mode_from_terminal_contract(
        friend_hold,
        handover_pending=True,
        terminal_locked=False,
    ) == GuidanceMode.HOLD
    assert guidance_mode_from_terminal_contract(
        revoked,
        handover_pending=True,
        terminal_locked=False,
    ) == GuidanceMode.ABORT_REVOKE


@pytest.mark.parametrize("pair_count", [1, 3, 5, 7])
def test_runtime_sized_pairs_keep_independent_terminal_gate_and_png_time_series(
    pair_count: int,
) -> None:
    config = _tuned_png_config()
    filters = {
        pair_index: SimpleFlightPngGuidanceFilter(config)
        for pair_index in range(pair_count)
    }
    records = []
    d5_reject_indices = {pair_count - 2} if pair_count >= 3 else set()
    d4_hold_indices = {pair_count - 1} if pair_count >= 3 else set()

    for pair_index in range(pair_count):
        resource_id = f"R{pair_index + 1}"
        target_id = f"G{pair_index + 1}"
        track_version = 40 + pair_index
        binding = _binding_for_pair(resource_id, target_id, track_version)
        d4_permission = D4GuidancePermission(action="continue_center")
        terminal_association = {
            "assigned_global_track_id": target_id,
            "local_track_id": f"{resource_id}:0:L{pair_index + 1}",
            "decision_state": "locked",
            "friend_conflict_state": "none",
            "assignment_version": track_version,
        }
        if pair_index in d5_reject_indices:
            terminal_association["decision_state"] = "ambiguous"
        if pair_index in d4_hold_indices:
            d4_permission = D4GuidancePermission(
                action="hold_for_review",
                requires_human_review=True,
            )

        pursuer = GuidanceState(
            resource_id,
            0.0,
            (0.0, float(pair_index * 12.0)),
            (8.0, 0.0),
        )
        target = GuidanceState(
            target_id,
            0.0,
            (80.0 + pair_index, float(pair_index * 12.0 + 2.0)),
            (-2.0, 0.0),
            source="global_track",
        )
        midcourse = compute_proportional_navigation_command(
            pursuer=pursuer,
            target=target,
            dt_s=config.dt_s,
            navigation_constant=config.navigation_constant,
            mode=GuidanceMode.RADAR_MIDCOURSE,
            max_lateral_accel_mps2=20.0,
            max_turn_rate_radps=0.9,
        )
        records.append(
            {
                "timestamp_s": 0.0,
                "resource_id": resource_id,
                "target_id": target_id,
                "mode": midcourse.mode.value,
                "control_context_id": f"{resource_id}->{target_id}",
                "guidance_law": "radar_pn",
                "terminal_switch_allowed": False,
                "terminal_contract_reject_reason": "",
            }
        )

        for sample_index, half_size in enumerate((28.0, 32.0, 36.0), start=1):
            timestamp_s = sample_index * config.dt_s
            center_x = 320.0 + pair_index * 3.0
            observation = VisionGuidanceObservation(
                timestamp_s=timestamp_s,
                bbox_xyxy=(
                    center_x - half_size,
                    240.0 - half_size,
                    center_x + half_size,
                    240.0 + half_size,
                ),
                detection_confidence=0.9,
                local_track_id=f"{resource_id}:0:L{pair_index + 1}",
                assigned_global_track_id=target_id,
            )
            decision = evaluate_terminal_png_contract(
                binding=binding,
                d4_permission=d4_permission,
                terminal_association=terminal_association,
                observation=observation,
                timestamp_s=timestamp_s,
                resource_id=resource_id,
            )
            if decision.allowed:
                command = filters[pair_index].evaluate(
                    observation,
                    current_heading_rad=0.0,
                    current_speed_mps=8.0,
                    intercept_speed_mps=8.0,
                    relative_position_ned=(30.0 + pair_index, 1.0, 0.0),
                    relative_velocity_ned=(-5.0, 0.0, 0.0),
                )
                records.append(
                    {
                        "timestamp_s": timestamp_s,
                        "resource_id": resource_id,
                        "target_id": target_id,
                        "control_context_id": f"{resource_id}->{target_id}",
                        "mode": GuidanceMode.VISION_TERMINAL.value,
                        "guidance_law": command.guidance_law,
                        "local_track_id": command.metadata["local_track_id"],
                        "stable_frame_count": command.quality.stable_frame_count,
                        "terminal_switch_allowed": command.quality.terminal_switch_allowed,
                        "terminal_switch_reject_reason": command.quality.reject_reason,
                        "terminal_contract_reject_reason": "",
                        "ttc_s": command.quality.ttc_s,
                    }
                )
            else:
                records.append(
                    {
                        "timestamp_s": timestamp_s,
                        "resource_id": resource_id,
                        "target_id": target_id,
                        "control_context_id": f"{resource_id}->{target_id}",
                        "mode": guidance_mode_from_terminal_contract(
                            decision,
                            handover_pending=True,
                            terminal_locked=False,
                        ).value,
                        "guidance_law": "radar_pn",
                        "terminal_switch_allowed": False,
                        "terminal_contract_reject_reason": decision.reject_reason,
                        "ttc_s": None,
                    }
                )

    expected_resources = {f"R{index + 1}" for index in range(pair_count)}
    rejected_resources = {
        f"R{index + 1}" for index in d5_reject_indices | d4_hold_indices
    }
    expected_allowed_resources = expected_resources - rejected_resources

    assert len(records) == pair_count * 4
    assert {record["resource_id"] for record in records} == expected_resources
    assert {record["control_context_id"] for record in records} == {
        f"R{index + 1}->G{index + 1}" for index in range(pair_count)
    }
    assert {
        record["resource_id"]
        for record in records
        if record["guidance_law"] == "radar_pn" and record["timestamp_s"] == 0.0
    } == expected_resources

    allowed_terminal_records = [
        record
        for record in records
        if record["guidance_law"] == "png_vm" and record["terminal_switch_allowed"]
    ]
    assert {
        record["resource_id"] for record in allowed_terminal_records
    } == expected_allowed_resources
    assert all(record["ttc_s"] is not None and record["ttc_s"] > 0.0 for record in allowed_terminal_records)
    assert summarize_terminal_switch_quality(allowed_terminal_records) == {
        "sample_count": len(expected_allowed_resources),
        "allowed_count": len(expected_allowed_resources),
        "rejected_count": 0,
        "terminal_switch_allowed_rate": 1.0,
        "reject_reasons": {},
    }

    reject_reasons = {
        record["resource_id"]: record["terminal_contract_reject_reason"]
        for record in records
        if record["terminal_contract_reject_reason"]
    }
    assert reject_reasons == {
        **{f"R{index + 1}": "d5_not_locked" for index in d5_reject_indices},
        **{f"R{index + 1}": "d4_hold_for_review" for index in d4_hold_indices},
    }
    final_png_records_by_resource = {
        record["resource_id"]: record
        for record in allowed_terminal_records
    }
    assert {
        resource_id: record["stable_frame_count"]
        for resource_id, record in final_png_records_by_resource.items()
    } == {resource_id: 3 for resource_id in expected_allowed_resources}
    assert {
        resource_id: record["local_track_id"]
        for resource_id, record in final_png_records_by_resource.items()
    } == {
        resource_id: f"{resource_id}:0:L{resource_id.removeprefix('R')}"
        for resource_id in expected_allowed_resources
    }
    assert not any(
        record["resource_id"] in rejected_resources and record["guidance_law"] == "png_vm"
        for record in records
    )


def test_runtime_bus_injects_n_pairs_with_independent_filters_and_summary() -> None:
    config = _tuned_png_config()
    bus = D7RuntimeBus(config)
    pair_count = 4
    all_outputs = []

    for sample_index, half_size in enumerate((28.0, 32.0, 36.0), start=1):
        pair_inputs = []
        for pair_index in range(pair_count):
            resource_id = f"R{pair_index + 1}"
            target_id = f"G{pair_index + 1}"
            track_version = 70 + pair_index
            pair_inputs.append(
                D7RuntimePairInput(
                    binding=_binding_for_pair(resource_id, target_id, track_version),
                    d4_permission=D4GuidancePermission(
                        action="continue_center",
                        target_node_id="center",
                        new_plan_id="plan-runtime-n",
                        new_plan_version=7,
                    ),
                    terminal_association={
                        "assigned_global_track_id": target_id,
                        "local_track_id": f"{resource_id}:BT:{pair_index + 1}",
                        "decision_state": "locked",
                        "friend_conflict_state": "none",
                        "assignment_version": track_version,
                    },
                    observation={
                        "timestamp_s": sample_index * config.dt_s,
                        "bbox_xyxy": (
                            320.0 + pair_index * 3.0 - half_size,
                            240.0 - half_size,
                            320.0 + pair_index * 3.0 + half_size,
                            240.0 + half_size,
                        ),
                        "confidence": 0.9,
                        "bytetrack_id": f"{resource_id}:BT:{pair_index + 1}",
                        "assigned_global_track_id": target_id,
                        "camera_id": "front_center",
                        "measurement_age_s": 0.02,
                    },
                    current_heading_rad=0.0,
                    current_speed_mps=8.0,
                    intercept_speed_mps=8.0,
                    relative_position_ned=(30.0 + pair_index, 1.0, 0.0),
                    relative_velocity_ned=(-5.0, 0.0, 0.0),
                )
            )
        all_outputs.extend(bus.inject_state(pair_inputs))

    allowed = [output for output in all_outputs if output.visual_png_enabled]
    summary = summarize_runtime_bus_outputs(all_outputs)

    assert len(all_outputs) == pair_count * 3
    assert len(bus.control_context_ids) == pair_count
    assert summary["boundary"] == D7_RUNTIME_BUS_BOUNDARY
    assert summary["control_context_count"] == pair_count
    assert summary["visual_png_switch_count"] == pair_count
    assert summary["visual_png_candidate_count"] == pair_count * 3
    assert summary["terminal_contract_allowed_count"] == pair_count * 3
    assert summary["terminal_switch_allowed_count"] == pair_count
    assert summary["terminal_handoff_state_counts"] == {
        "switch_gate_rejected": pair_count * 2,
        "vision_terminal": pair_count,
    }
    assert summary["guidance_mode_counts"] == {
        "handover_pending": pair_count * 2,
        "vision_terminal": pair_count,
    }
    assert summary["d4_action_counts"] == {"continue_center": pair_count * 3}
    assert summary["d5_decision_state_counts"] == {"locked": pair_count * 3}
    assert summary["plan_version_counts"] == {"7": pair_count * 3}
    assert summary["guidance_law_counts"]["png_vm"] == pair_count
    assert summary["png_guidance_law_candidate_counts"] == {"png_vm": pair_count * 3}
    assert summary["camera_quality_gate_pass_rate"] == pytest.approx(2 / 3)
    assert summary["los_quality_gate_pass_rate"] == pytest.approx(1 / 3)
    assert summary["maneuver_margin_gate_pass_rate"] == pytest.approx(1.0)
    assert summary["bbox_area_ratio_observed_count"] == pair_count * 3
    assert summary["ttc_s_observed_count"] >= pair_count
    assert summary["los_rate_abs_radps_observed_count"] == pair_count * 3
    assert {output.control_context_id for output in allowed} == {
        f"R{index + 1}->G{index + 1}" for index in range(pair_count)
    }
    assert {output.stable_frame_count for output in allowed} == {3}
    assert all(output.selected_velocity_ned is not None for output in allowed)
    assert all(
        output.png_command is not None
        and output.png_command.metadata["camera_id"] == "front_center"
        for output in allowed
    )
    allowed_record = allowed[0].as_log_record()
    assert allowed_record["terminal_mode_entered"] is True
    assert allowed_record["terminal_handoff_state"] == "vision_terminal"
    assert allowed_record["camera_quality_gate_passed"] is True
    assert allowed_record["los_quality_gate_passed"] is True
    assert allowed_record["maneuver_margin_gate_passed"] is True
    assert allowed_record["bbox_area_ratio"] > 0.0
    assert allowed_record["ttc_s"] is not None
    assert allowed_record["d4_state"] == "continue_center"
    assert allowed_record["d5_state"] == "locked"


def test_runtime_bus_resets_filter_when_same_pair_plan_signature_changes() -> None:
    config = _tuned_png_config()
    bus = D7RuntimeBus(config)
    plan_1 = AssignmentGuidanceBinding(
        plan_id="plan-center-1",
        plan_version=1,
        owner_node_id="center",
        assignment_id="assign-R1-G1",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id="G1",
        track_version=10,
        authorization_state="approved",
    )
    terminal_1 = {
        "assigned_global_track_id": "G1",
        "local_track_id": "R1:BT:1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 10,
    }

    plan_1_outputs = [
        bus.evaluate_pair(
            D7RuntimePairInput(
                binding=plan_1,
                d4_permission=D4GuidancePermission(
                    action="continue_center",
                    target_node_id="center",
                    new_plan_id="plan-center-1",
                    new_plan_version=1,
                ),
                terminal_association=terminal_1,
                observation=_runtime_observation(
                    timestamp_s=index * config.dt_s,
                    half_size=half_size,
                ),
                current_heading_rad=0.0,
                current_speed_mps=8.0,
                intercept_speed_mps=8.0,
                relative_position_ned=(30.0, 1.0, 0.0),
                relative_velocity_ned=(-5.0, 0.0, 0.0),
            )
        )
        for index, half_size in enumerate((28.0, 32.0, 36.0), start=1)
    ]
    assert plan_1_outputs[-1].visual_png_enabled is True
    assert plan_1_outputs[-1].stable_frame_count == 3

    blocked_replan = bus.evaluate_pair(
        D7RuntimePairInput(
            binding=plan_1,
            d4_permission=D4GuidancePermission(
                action="request_center_replan",
                target_node_id="secondary-1",
                new_plan_id="plan-secondary-2",
                new_plan_version=2,
            ),
            terminal_association=terminal_1,
            observation=_runtime_observation(timestamp_s=0.5, half_size=40.0),
            current_heading_rad=0.0,
            current_speed_mps=8.0,
            intercept_speed_mps=8.0,
            relative_position_ned=(28.0, 1.0, 0.0),
            relative_velocity_ned=(-5.0, 0.0, 0.0),
        )
    )
    assert blocked_replan.visual_png_enabled is False
    assert blocked_replan.guidance_law == "radar_pn"
    assert blocked_replan.terminal_contract_reject_reason == "d4_reassign_pending"
    assert blocked_replan.mode == GuidanceMode.ABORT_REVOKE

    plan_2 = AssignmentGuidanceBinding(
        plan_id="plan-secondary-2",
        plan_version=2,
        owner_node_id="secondary-1",
        assignment_id="assign-R1-G1-secondary",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id="G1",
        track_version=11,
        authorization_state="approved",
    )
    terminal_2 = {
        "assigned_global_track_id": "G1",
        "local_track_id": "R1:BT:1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 11,
    }
    first_new_plan_sample = bus.evaluate_pair(
        D7RuntimePairInput(
            binding=plan_2,
            d4_permission=D4GuidancePermission(
                action="request_secondary_assist",
                target_node_id="secondary-1",
                new_plan_id="plan-secondary-2",
                new_plan_version=2,
            ),
            terminal_association=terminal_2,
            observation=_runtime_observation(timestamp_s=0.6, half_size=42.0),
            current_heading_rad=0.0,
            current_speed_mps=8.0,
            intercept_speed_mps=8.0,
            relative_position_ned=(26.0, 1.0, 0.0),
            relative_velocity_ned=(-5.0, 0.0, 0.0),
        )
    )

    assert first_new_plan_sample.terminal_contract_allowed is True
    assert first_new_plan_sample.visual_png_enabled is False
    assert first_new_plan_sample.stable_frame_count == 1
    assert first_new_plan_sample.terminal_switch_reject_reason == "stable_frame_count_low"


def test_runtime_bus_applies_reacquire_grace_after_d5_locked_jitter() -> None:
    config = replace(_tuned_png_config(), terminal_reacquire_grace_frames=2)
    bus = D7RuntimeBus(config)
    binding = _binding_for_pair("R1", "G1", 90)
    locked_terminal = {
        "assigned_global_track_id": "G1",
        "local_track_id": "R1:BT:1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 90,
    }
    reacquire_terminal = {
        **locked_terminal,
        "decision_state": "reacquire",
    }
    outputs = []

    for index, half_size in enumerate((28.0, 32.0, 36.0), start=1):
        outputs.append(
            bus.evaluate_pair(
                D7RuntimePairInput(
                    binding=binding,
                    d4_permission=D4GuidancePermission(
                        action="continue_center",
                        target_node_id="center",
                        new_plan_id="plan-runtime-n",
                        new_plan_version=7,
                    ),
                    terminal_association=locked_terminal,
                    observation=_runtime_observation(timestamp_s=index * config.dt_s, half_size=half_size),
                    current_heading_rad=0.0,
                    current_speed_mps=8.0,
                    intercept_speed_mps=8.0,
                    relative_position_ned=(30.0, 1.0, 0.0),
                    relative_velocity_ned=(-5.0, 0.0, 0.0),
                )
            )
        )
    assert outputs[-1].visual_png_enabled is True

    outputs.append(
        bus.evaluate_pair(
            D7RuntimePairInput(
                binding=binding,
                d4_permission=D4GuidancePermission(action="continue_center"),
                terminal_association=reacquire_terminal,
                observation=_runtime_observation(timestamp_s=0.4, half_size=38.0),
                handover_pending=True,
                terminal_locked=True,
                current_heading_rad=0.0,
                current_speed_mps=8.0,
                intercept_speed_mps=8.0,
                relative_position_ned=(28.0, 1.0, 0.0),
                relative_velocity_ned=(-5.0, 0.0, 0.0),
            )
        )
    )

    for sample_index, half_size in enumerate((40.0, 42.0, 44.0, 46.0, 48.0), start=5):
        outputs.append(
            bus.evaluate_pair(
                D7RuntimePairInput(
                    binding=binding,
                    d4_permission=D4GuidancePermission(action="continue_center"),
                    terminal_association=locked_terminal,
                    observation=_runtime_observation(
                        timestamp_s=sample_index * config.dt_s,
                        half_size=half_size,
                    ),
                    handover_pending=True,
                    terminal_locked=False,
                    current_heading_rad=0.0,
                    current_speed_mps=8.0,
                    intercept_speed_mps=8.0,
                    relative_position_ned=(26.0, 1.0, 0.0),
                    relative_velocity_ned=(-5.0, 0.0, 0.0),
                )
            )
        )

    summary = summarize_runtime_bus_outputs(outputs)
    post_reacquire = outputs[4:]

    assert outputs[3].terminal_contract_allowed is False
    assert outputs[3].terminal_contract_reject_reason == "d5_not_locked"
    assert outputs[3].visual_png_enabled is False
    assert [output.terminal_switch_reject_reason for output in post_reacquire[:2]] == [
        "stable_frame_count_low",
        "los_rate_window_too_short",
    ]
    assert [output.terminal_switch_reject_reason for output in post_reacquire[2:4]] == [
        "reacquire_grace_active",
        "reacquire_grace_active",
    ]
    assert post_reacquire[2].terminal_reacquire_grace_active is True
    assert post_reacquire[3].terminal_reacquire_grace_active is True
    assert post_reacquire[-1].visual_png_enabled is True
    assert summary["terminal_reacquire_grace_active_count"] == 2
    assert summary["terminal_switch_reject_reasons"]["reacquire_grace_active"] == 2
    assert summary["visual_png_switch_count"] == 2


@pytest.mark.parametrize(
    "action",
    ["request_center_replan", "degrade_to_secondary", "degrade_to_distributed"],
)
def test_runtime_bus_blocks_visual_png_for_d4_reassign_actions_even_with_good_bbox(
    action: str,
) -> None:
    bus = D7RuntimeBus(_tuned_png_config())
    output = bus.evaluate_pair(
        D7RuntimePairInput(
            binding=_binding_for_pair("R1", "G1", 90),
            d4_permission=D4GuidancePermission(
                action=action,
                target_node_id="secondary-1",
                new_plan_id="plan-secondary-2",
                new_plan_version=2,
            ),
            terminal_association={
                "assigned_global_track_id": "G1",
                "local_track_id": "R1:BT:1",
                "decision_state": "locked",
                "friend_conflict_state": "none",
                "assignment_version": 90,
            },
            observation=_runtime_observation(timestamp_s=1.0, half_size=44.0),
            handover_pending=True,
            terminal_locked=True,
            current_heading_rad=0.0,
            current_speed_mps=8.0,
            intercept_speed_mps=8.0,
            relative_position_ned=(25.0, 0.5, 0.0),
            relative_velocity_ned=(-5.0, 0.0, 0.0),
        )
    )
    summary = summarize_runtime_bus_outputs([output])

    assert output.visual_png_enabled is False
    assert output.guidance_law == "radar_pn"
    assert output.mode == GuidanceMode.ABORT_REVOKE
    assert output.terminal_handoff_state == "contract_rejected"
    assert output.terminal_contract_reject_reason == "d4_reassign_pending"
    assert output.png_command is None
    assert output.png_guidance_law_candidate is None
    assert output.camera_quality_gate_passed is None
    assert output.bbox_xyxy == _runtime_observation(timestamp_s=1.0, half_size=44.0)["bbox_xyxy"]
    assert summary["visual_png_switch_count"] == 0
    assert summary["visual_png_candidate_count"] == 0
    assert summary["terminal_contract_reject_reasons"] == {"d4_reassign_pending": 1}
    assert summary["terminal_handoff_state_counts"] == {"contract_rejected": 1}
    assert summary["guidance_mode_counts"] == {"abort_revoke": 1}
    assert summary["d4_action_counts"] == {action: 1}


@pytest.mark.parametrize(
    "action",
    ["request_center_replan", "degrade_to_secondary", "degrade_to_distributed"],
)
def test_terminal_contract_blocks_d4_reassign_until_new_owner_version_and_d5_lock(
    action: str,
) -> None:
    old_binding = AssignmentGuidanceBinding(
        plan_id="plan-center-1",
        plan_version=1,
        owner_node_id="center",
        assignment_id="assign-R1-G1",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id="G1",
        track_version=10,
        authorization_state="approved",
    )
    old_terminal = {
        "assigned_global_track_id": "G1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 10,
    }

    blocked = evaluate_terminal_png_contract(
        binding=old_binding,
        d4_permission=D4GuidancePermission(
            action=action,
            target_node_id="secondary-1",
            new_plan_id="plan-secondary-2",
            new_plan_version=2,
        ),
        terminal_association=old_terminal,
        observation={"assigned_global_track_id": "G1"},
        timestamp_s=1.0,
        resource_id="R1",
    )

    assert blocked.allowed is False
    assert blocked.reject_reason == "d4_reassign_pending"
    assert guidance_mode_from_terminal_contract(
        blocked,
        handover_pending=True,
        terminal_locked=False,
    ) == GuidanceMode.ABORT_REVOKE

    new_binding = AssignmentGuidanceBinding(
        plan_id="plan-secondary-2",
        plan_version=2,
        owner_node_id="secondary-1",
        assignment_id="assign-R1-G1-secondary",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id="G1",
        track_version=11,
        authorization_state="approved",
    )
    stale_d5 = {
        "assigned_global_track_id": "G1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 10,
    }
    current_d5 = {
        "assigned_global_track_id": "G1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 11,
    }

    stale_version = evaluate_terminal_png_contract(
        binding=new_binding,
        d4_permission=D4GuidancePermission(
            action="request_secondary_assist",
            target_node_id="secondary-1",
            new_plan_id="plan-secondary-2",
            new_plan_version=2,
        ),
        terminal_association=stale_d5,
        observation={"assigned_global_track_id": "G1"},
        timestamp_s=1.2,
        resource_id="R1",
    )
    owner_mismatch = evaluate_terminal_png_contract(
        binding=new_binding,
        d4_permission=D4GuidancePermission(
            action="request_secondary_assist",
            target_node_id="center",
            new_plan_id="plan-secondary-2",
            new_plan_version=2,
        ),
        terminal_association=current_d5,
        observation={"assigned_global_track_id": "G1"},
        timestamp_s=1.3,
        resource_id="R1",
    )
    valid_new_plan = evaluate_terminal_png_contract(
        binding=new_binding,
        d4_permission={
            "action": "request_secondary_assist",
            "new_plan_owner_id": "secondary-1",
            "new_plan_id": "plan-secondary-2",
            "new_plan_version": 2,
        },
        terminal_association=current_d5,
        observation={"assigned_global_track_id": "G1"},
        timestamp_s=1.4,
        resource_id="R1",
    )

    assert stale_version.reject_reason == "assignment_version_mismatch"
    assert owner_mismatch.reject_reason == "d4_owner_mismatch"
    assert valid_new_plan.allowed is True
    assert valid_new_plan.d4_target_node_id == "secondary-1"


def test_terminal_contract_rejects_d4_target_owner_without_d3_owner() -> None:
    binding_without_owner = _binding_for_pair("R1", "G1", 30, owner_node_id=None)
    terminal = {
        "assigned_global_track_id": "G1",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 30,
    }

    decision = evaluate_terminal_png_contract(
        binding=binding_without_owner,
        d4_permission=D4GuidancePermission(
            action="request_secondary_assist",
            target_node_id="secondary-1",
            new_plan_id="plan-runtime-n",
            new_plan_version=7,
        ),
        terminal_association=terminal,
        observation={"assigned_global_track_id": "G1"},
        timestamp_s=1.0,
        resource_id="R1",
    )

    assert decision.allowed is False
    assert decision.reject_reason == "d4_owner_missing"
    assert guidance_mode_from_terminal_contract(
        decision,
        handover_pending=True,
        terminal_locked=False,
    ) == GuidanceMode.REACQUIRE


def test_bbox_los_replay_normalizes_yolo_bytetrack_and_stays_offline() -> None:
    config = _tuned_png_config()
    detections = [
        {
            "timestamp_s": index * config.dt_s,
            "xywh": (320.0 - half_size, 240.0 - half_size, half_size * 2.0, half_size * 2.0),
            "score": 0.92,
            "bytetrack_id": "BT-7",
            "measurement_age_s": 0.03,
        }
        for index, half_size in enumerate((28.0, 31.0, 34.0, 37.0, 40.0, 43.0))
    ]

    observation = bbox_replay_detection_to_observation(
        detections[0],
        source="yolo_bytetrack_replay",
        assigned_global_track_id="G1",
        camera_id="front_center",
        frame_index=0,
    )
    assert observation.bbox_xyxy == (292.0, 212.0, 348.0, 268.0)
    assert observation.local_track_id == "BT-7"
    assert observation.assigned_global_track_id == "G1"
    assert observation.camera_id == "front_center"
    assert observation.metadata["boundary"] == BBOX_LOS_REPLAY_BOUNDARY
    assert observation.metadata["visual_latency_s"] == pytest.approx(0.03)

    outputs, summary = evaluate_bbox_los_replay(
        detections,
        binding=_binding_for_pair("R1", "G1", 42),
        d4_permission=D4GuidancePermission(
            action="continue_center",
            target_node_id="center",
            new_plan_id="plan-runtime-n",
            new_plan_version=7,
        ),
        terminal_association={
            "assigned_global_track_id": "G1",
            "local_track_id": "BT-7",
            "decision_state": "locked",
            "friend_conflict_state": "none",
            "assignment_version": 42,
        },
        config=config,
        source="yolo_bytetrack_replay",
        assigned_global_track_id="G1",
        camera_id="front_center",
        current_heading_rad=0.0,
        current_speed_mps=8.0,
        intercept_speed_mps=8.0,
        relative_position_ned=(30.0, 1.0, 0.0),
        relative_velocity_ned=(-5.0, 0.0, 0.0),
    )

    assert summary["boundary"] == BBOX_LOS_REPLAY_BOUNDARY
    assert summary["replay_source"] == "yolo_bytetrack_replay"
    assert summary["observation_count"] == len(detections)
    assert summary["vehicle_control"] is False
    assert summary["simpleflight_control_called"] is False
    assert summary["visual_png_switch_count"] > 0
    assert {output.control_context_id for output in outputs} == {"R1->G1"}
    assert all(
        output.as_log_record()["replay_source"] == "yolo_bytetrack_replay"
        for output in outputs
    )


def test_guidance_strategy_comparison_reports_all_p1_fields() -> None:
    rows = run_guidance_strategy_comparison(seeds=[1, 2])
    summary = summarize_guidance_strategy_comparison(rows)

    assert len(rows) == 2 * len(DEFAULT_COMPARISON_STRATEGIES)
    assert {row.strategy for row in rows} == set(DEFAULT_COMPARISON_STRATEGIES)
    assert summary["row_count"] == len(rows)
    assert summary["strategy_count"] == len(DEFAULT_COMPARISON_STRATEGIES)
    for strategy in DEFAULT_COMPARISON_STRATEGIES:
        assert summary["strategies"][strategy]["seed_count"] == 2

    for row in rows:
        data = row.as_dict()
        assert {
            "seed",
            "strategy",
            "guidance_law",
            "boundary",
            "sample_count",
            "min_range_m",
            "time_to_intercept_s",
            "terminal_contract_reject_reasons",
            "terminal_switch_reject_reasons",
            "visual_png_switch_count",
        } <= set(data)
        assert row.sample_count > 0
        if row.strategy in {"pn", "pure_pursuit"}:
            assert row.boundary == "offline_2d_point_mass_only"
            assert row.min_range_m is not None
            assert row.final_range_m is not None
            assert row.visual_png_switch_count == 0
        else:
            assert row.boundary == BBOX_LOS_REPLAY_BOUNDARY
            assert row.metadata["vehicle_control"] is False
            assert row.visual_png_switch_count > 0


def test_guidance_calibration_summary_groups_multiseed_runtime_records_and_advisory() -> None:
    comparison_rows = run_guidance_strategy_comparison(seeds=[3, 4])
    config = _tuned_png_config()
    runtime_outputs = []

    for law in ("png_vm", "png_ttc"):
        for seed in (3, 4):
            bus = D7RuntimeBus(replace(config, law=law))
            for sample_index, half_size in enumerate((28.0, 32.0, 36.0), start=1):
                runtime_outputs.append(
                    bus.evaluate_pair(
                        D7RuntimePairInput(
                            binding=_binding_for_pair("R1", "G1", 80 + seed),
                            d4_permission=D4GuidancePermission(
                                action="continue_center",
                                target_node_id="center",
                                new_plan_id="plan-runtime-n",
                                new_plan_version=7,
                            ),
                            terminal_association={
                                "assigned_global_track_id": "G1",
                                "local_track_id": f"R1:BT:{seed}",
                                "decision_state": "locked",
                                "friend_conflict_state": "none",
                                "assignment_version": 80 + seed,
                            },
                            observation={
                                "timestamp_s": seed + sample_index * config.dt_s,
                                "bbox_xyxy": (
                                    320.0 - half_size,
                                    240.0 - half_size,
                                    320.0 + half_size,
                                    240.0 + half_size,
                                ),
                                "confidence": 0.9,
                                "local_track_id": f"R1:BT:{seed}",
                                "assigned_global_track_id": "G1",
                                "measurement_age_s": 0.02 + seed * 0.001,
                            },
                            current_heading_rad=0.0,
                            current_speed_mps=8.0,
                            intercept_speed_mps=8.0,
                            relative_position_ned=(28.0 + seed, 1.0, 10.0),
                            relative_velocity_ned=(-5.0, 0.0, 0.0),
                            metadata={
                                "seed": seed,
                                "terminal_range_m": 24.0 + seed,
                                "height_delta_m": 10.0,
                                "range_3d_m": 32.0 + seed,
                                "frpn_benchmark_score": 0.70 + seed * 0.01,
                                "frpn_guidance_law": "frpn_benchmark",
                            },
                        )
                    )
                )

    summary = summarize_guidance_calibration(
        [*comparison_rows, *runtime_outputs],
        current_thresholds={
            "version": DEFAULT_CALIBRATION_THRESHOLD_VERSION,
            "terminal_range_m": 30.0,
            "min_bbox_area_ratio": config.min_bbox_area_ratio,
            "max_visual_latency_s": config.max_visual_latency_s,
            "min_closing_speed_mps": config.min_closing_speed_mps,
            "min_maneuver_margin": config.min_maneuver_margin,
        },
    )

    assert summary["boundary"] == D7_GUIDANCE_CALIBRATION_BOUNDARY
    assert summary["advisory_only"] is True
    assert summary["default_control_law_changed"] is False
    assert summary["d3_d4_d5_gate_bypassed"] is False
    assert set(DEFAULT_COMPARISON_STRATEGIES) <= set(summary["guidance_law_summaries"])

    png_vm = summary["guidance_law_summaries"]["png_vm"]
    png_ttc = summary["guidance_law_summaries"]["png_ttc"]
    assert png_vm["seed_count"] == 2
    assert png_ttc["seed_count"] == 2
    assert png_vm["visual_png_switch_count"] > 0
    assert png_ttc["visual_png_switch_count"] > 0
    assert png_vm["bbox_gate"]["pass_rate"] > 0.0
    assert png_vm["los_gate"]["pass_rate"] > 0.0
    assert png_vm["maneuver_gate"]["pass_rate"] > 0.0
    assert png_vm["terminal_range_m"]["observed_count"] >= 2
    assert png_vm["closing_speed_mps"]["observed_count"] >= 2
    assert "stable_frame_count_low" in png_vm["terminal_switch_reject_reasons"]

    pn = summary["guidance_law_summaries"]["pn"]
    pure_pursuit = summary["guidance_law_summaries"]["pure_pursuit"]
    assert pn["seed_count"] == 2
    assert pure_pursuit["seed_count"] == 2
    assert pn["terminal_range_m"]["observed_count"] == 2

    advisory = summary["threshold_advisory"]
    assert advisory["version"] == DEFAULT_CALIBRATION_THRESHOLD_VERSION
    assert advisory["advisory_only"] is True
    assert advisory["default_control_law_changed"] is False
    assert advisory["thresholds"]["terminal_range_m"]["current"] == 30.0
    assert advisory["thresholds"]["min_bbox_area_ratio"]["current"] == config.min_bbox_area_ratio
    assert advisory["thresholds"]["max_visual_latency_s"]["suggested"] <= config.max_visual_latency_s
    assert advisory["thresholds"]["min_closing_speed_mps"]["suggested"] >= config.min_closing_speed_mps
    assert advisory["thresholds"]["min_maneuver_margin"]["suggested"] >= config.min_maneuver_margin

    benchmark = summary["benchmark_calibration"]
    assert benchmark["benchmark_only"] is True
    assert benchmark["default_pn_png_api_replaced"] is False
    assert benchmark["three_dimensional_guidance_replaces_default"] is False
    assert benchmark["frpn_replaces_default"] is False
    assert benchmark["height_delta_m"]["observed_count"] == len(runtime_outputs)
    assert benchmark["range_3d_m"]["observed_count"] == len(runtime_outputs)
    assert benchmark["frpn_guidance_law_counts"] == {"frpn_benchmark": len(runtime_outputs)}


def test_3d_pn_benchmark_logs_advisory_fields_without_replacing_default_png() -> None:
    benchmark = compute_three_dimensional_pn_benchmark(
        relative_position_ned=(30.0, 4.0, 20.0),
        relative_velocity_ned=(-5.0, 1.0, -2.0),
        navigation_constant=3.0,
    )
    assert benchmark.benchmark_only is True
    assert benchmark.default_pn_png_api_replaced is False
    assert benchmark.d3_d4_d5_gate_bypassed is False
    assert benchmark.range_3d_m > benchmark.horizontal_range_m
    assert benchmark.height_delta_m == pytest.approx(20.0)
    assert benchmark.commanded_accel_norm_mps2 >= 0.0

    bus = D7RuntimeBus(_tuned_png_config())
    output = bus.evaluate_pair(
        D7RuntimePairInput(
            binding=_binding_for_pair("R1", "G1", 92),
            d4_permission=D4GuidancePermission(action="continue_center"),
            terminal_association={
                "assigned_global_track_id": "G1",
                "local_track_id": "R1:BT:3d",
                "decision_state": "locked",
                "friend_conflict_state": "none",
                "assignment_version": 92,
            },
            observation=_runtime_observation(timestamp_s=0.1, half_size=36.0, local_track_id="R1:BT:3d"),
            current_heading_rad=0.0,
            current_speed_mps=8.0,
            intercept_speed_mps=8.0,
            relative_position_ned=(30.0, 4.0, 20.0),
            relative_velocity_ned=(-5.0, 1.0, -2.0),
        )
    )
    record = output.as_log_record()
    summary = summarize_runtime_bus_outputs([output])

    assert output.pn3d_benchmark_only is True
    assert output.pn3d_default_api_replaced is False
    assert record["range_3d_m"] == pytest.approx(benchmark.range_3d_m)
    assert record["height_delta_m"] == pytest.approx(20.0)
    assert record["pn3d_los_rate_norm_radps"] == pytest.approx(benchmark.los_rate_norm_radps)
    assert record["guidance_law"] == "radar_pn"
    assert summary["pn3d_benchmark_sample_count"] == 1
    assert summary["pn3d_default_api_replaced"] is False
    assert summary["range_3d_m_observed_count"] == 1
    assert summary["pn3d_los_rate_norm_radps_observed_count"] == 1


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


def _binding_for_pair(
    resource_id: str,
    target_id: str,
    track_version: int,
    owner_node_id: str | None = "center",
) -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id="plan-runtime-n",
        plan_version=7,
        owner_node_id=owner_node_id,
        assignment_id=f"assign-{resource_id}-{target_id}",
        resource_id=resource_id,
        vehicle_name=f"Interceptor_{resource_id}",
        assigned_global_track_id=target_id,
        track_version=track_version,
        authorization_state="approved",
        target_actor_name=f"MSM_TargetActor_{target_id.removeprefix('G')}",
        target_object_id=target_id,
        target_mesh_aliases=(f"MSM_TargetActor_{target_id.removeprefix('G')}", target_id),
    )


def _runtime_observation(
    *,
    timestamp_s: float,
    half_size: float,
    assigned_global_track_id: str = "G1",
    local_track_id: str = "R1:BT:1",
) -> dict:
    return {
        "timestamp_s": timestamp_s,
        "bbox_xyxy": (
            320.0 - half_size,
            240.0 - half_size,
            320.0 + half_size,
            240.0 + half_size,
        ),
        "confidence": 0.9,
        "local_track_id": local_track_id,
        "assigned_global_track_id": assigned_global_track_id,
    }


def _tuned_png_config() -> PngGuidanceConfig:
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


def _evaluate_tuned_png_sequence(
    config: PngGuidanceConfig,
    observations: list[VisionGuidanceObservation],
) -> list:
    tracker = SimpleFlightPngGuidanceFilter(config)
    return [
        tracker.evaluate(
            observation,
            current_heading_rad=0.0,
            current_speed_mps=6.0,
            intercept_speed_mps=6.0,
            relative_position_ned=(20.0, 0.0, 0.0),
            relative_velocity_ned=(-4.0, 0.0, 0.0),
        )
        for observation in observations
    ]
