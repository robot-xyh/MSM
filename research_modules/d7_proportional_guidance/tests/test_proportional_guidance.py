from __future__ import annotations

import math

import pytest

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
    compute_pure_pursuit_command,
    evaluate_terminal_png_contract,
    guidance_mode_from_terminal_contract,
    simulate_guidance_episode,
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


def test_five_parallel_pairs_keep_independent_terminal_gate_and_png_time_series() -> None:
    config = _tuned_png_config()
    filters = {
        pair_index: SimpleFlightPngGuidanceFilter(config)
        for pair_index in range(5)
    }
    records = []

    for pair_index in range(5):
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
        if pair_index == 3:
            terminal_association["decision_state"] = "ambiguous"
        if pair_index == 4:
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

    assert len(records) == 20
    assert {record["resource_id"] for record in records} == {
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
    }

    allowed_terminal_records = [
        record
        for record in records
        if record["guidance_law"] == "png_vm" and record["terminal_switch_allowed"]
    ]
    assert {record["resource_id"] for record in allowed_terminal_records} == {"R1", "R2", "R3"}
    assert all(record["ttc_s"] is not None and record["ttc_s"] > 0.0 for record in allowed_terminal_records)
    assert summarize_terminal_switch_quality(allowed_terminal_records) == {
        "sample_count": 3,
        "allowed_count": 3,
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
        "R4": "d5_not_locked",
        "R5": "d4_hold_for_review",
    }
    final_png_records_by_resource = {
        record["resource_id"]: record
        for record in allowed_terminal_records
    }
    assert {
        resource_id: record["stable_frame_count"]
        for resource_id, record in final_png_records_by_resource.items()
    } == {"R1": 3, "R2": 3, "R3": 3}
    assert {
        resource_id: record["local_track_id"]
        for resource_id, record in final_png_records_by_resource.items()
    } == {
        "R1": "R1:0:L1",
        "R2": "R2:0:L2",
        "R3": "R3:0:L3",
    }
    assert not any(
        record["resource_id"] in {"R4", "R5"} and record["guidance_law"] == "png_vm"
        for record in records
    )


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
) -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id="plan-5v5",
        plan_version=7,
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
