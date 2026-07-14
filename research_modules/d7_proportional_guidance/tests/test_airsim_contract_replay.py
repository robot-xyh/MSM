from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    D7RuntimeBus,
    D7RuntimePairInput,
    GuidanceMode,
    PngGuidanceConfig,
    VisionGuidanceObservation,
    analyze_airsim_contract_replay,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_real_posefix_excerpt_keeps_all_three_rejections_fail_closed() -> None:
    analysis = analyze_airsim_contract_replay(
        FIXTURES / "p1_cooperative_posefix_contract_excerpt.csv",
        FIXTURES / "p1_cooperative_posefix_intercept_summary_excerpt.json",
    )
    impacts = {row.reason: row for row in analysis.reason_impacts}

    assert impacts["coalition_not_activated"].sample_count == 4
    assert impacts["coalition_window_closed"].sample_count == 3
    assert impacts["d4_owner_missing"].sample_count == 5
    assert all(row.visual_png_enabled_count == 0 for row in impacts.values())
    assert all(row.terminal_contract_allowed_count == 0 for row in impacts.values())
    assert all(row.radar_pn_fallback_count == row.sample_count for row in impacts.values())
    assert analysis.plan_version_regression_count == 1
    assert analysis.physical_pair_success_count == 1
    assert analysis.coalition_completion_count == 0
    assert analysis.online_truth_use_count == 0


def test_monotonic_current_plan_updates_preserve_filter_but_recheck_contract() -> None:
    bus = D7RuntimeBus(_config())
    outputs = []
    for index, version in enumerate((10, 11, 12, 13)):
        binding = _binding(plan_version=version, track_version=version)
        outputs.append(
            bus.evaluate_pair(
                _input(binding, timestamp_s=1.0 + 0.1 * index, half_size=30.0 + 4.0 * index)
            )
        )

    assert outputs[1].metadata["binding_transition"] == "monotonic_current_update"
    assert outputs[1].metadata["binding_state_preserved"] is True
    assert outputs[1].terminal_lifecycle_reset is False
    assert outputs[1].stable_frame_count == 2
    assert outputs[-1].visual_png_enabled is True
    assert outputs[-1].guidance_law == "png_vm"
    assert outputs[-1].plan_version == 13


def test_missing_owner_and_standby_reserve_still_block_visual_png() -> None:
    bus = D7RuntimeBus(_config())
    current = _binding(plan_version=48, track_version=48)
    bus.evaluate_pair(_input(current, timestamp_s=1.0, half_size=34.0))

    missing_owner = replace(
        current,
        plan_id="airsim_control_plan",
        plan_version=1,
        track_version=1,
        owner_node_id=None,
    )
    blocked_owner = bus.evaluate_pair(
        _input(missing_owner, timestamp_s=1.1, half_size=38.0, d4_target="d3_central")
    )
    reserve = replace(
        current,
        resource_id="R3",
        vehicle_name="Interceptor3",
        member_role="reserve",
        wave_id=1,
        activation_state="standby",
    )
    blocked_reserve = bus.evaluate_pair(
        _input(reserve, timestamp_s=1.1, half_size=38.0)
    )

    assert blocked_owner.terminal_contract_reject_reason == "d4_owner_missing"
    assert blocked_owner.guidance_law == "radar_pn"
    assert blocked_owner.visual_png_enabled is False
    assert blocked_owner.metadata["binding_transition"] == "plan_version_regression"
    assert blocked_owner.metadata["binding_state_preserved"] is False
    assert blocked_reserve.terminal_contract_reject_reason == "coalition_not_activated"
    assert blocked_reserve.guidance_law == "radar_pn"
    assert blocked_reserve.mode == GuidanceMode.HOLD


def test_closed_arrival_window_blocks_png_but_keeps_midcourse_control() -> None:
    binding = replace(
        _binding(plan_version=20, track_version=20),
        arrival_window_start_s=1.0,
        arrival_window_end_s=1.1,
    )
    output = D7RuntimeBus(_config()).evaluate_pair(
        _input(binding, timestamp_s=1.2, half_size=40.0)
    )

    assert output.terminal_contract_reject_reason == "coalition_window_closed"
    assert output.visual_png_enabled is False
    assert output.guidance_law == "radar_pn"
    assert output.mode == GuidanceMode.RADAR_MIDCOURSE
    assert output.metadata["arrival_window_semantics"] == "terminal_png_permission_window"


def _config() -> PngGuidanceConfig:
    return PngGuidanceConfig(
        dt_s=0.1,
        min_bbox_area_ratio=0.0001,
        min_stable_frames=2,
        edge_margin_ratio=0.01,
        max_los_rate_variance_radps2=10.0,
        los_rate_window=2,
        max_visual_latency_s=1.0,
        min_maneuver_margin=0.0,
        terminal_dwell_frames=2,
        law="png_vm",
    )


def _binding(*, plan_version: int, track_version: int) -> AssignmentGuidanceBinding:
    return AssignmentGuidanceBinding(
        plan_id=f"d3-plan-{plan_version}",
        plan_version=plan_version,
        owner_node_id="d3_central",
        assignment_id=f"R1:G1:v{plan_version}",
        resource_id="R1",
        vehicle_name="Interceptor1",
        assigned_global_track_id="G1",
        track_version=track_version,
        authorization_state="recorded",
        coalition_id="coalition-G1",
        coalition_version=plan_version,
        member_role="primary",
        wave_id=0,
        coordination_mode="hybrid",
        arrival_window_start_s=1.0,
        arrival_window_end_s=2.0,
        activation_state="active",
    )


def _input(
    binding: AssignmentGuidanceBinding,
    *,
    timestamp_s: float,
    half_size: float,
    d4_target: str | None = None,
) -> D7RuntimePairInput:
    terminal = {
        "assigned_global_track_id": binding.assigned_global_track_id,
        "local_track_id": "BT-1",
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
        "metadata": {"execution_gate_pass": True},
    }
    observation = VisionGuidanceObservation(
        timestamp_s=timestamp_s,
        frame_timestamp_s=timestamp_s,
        bbox_xyxy=(320.0 - half_size, 240.0 - half_size, 320.0 + half_size, 240.0 + half_size),
        detection_confidence=0.95,
        local_track_id="BT-1",
        assigned_global_track_id=binding.assigned_global_track_id,
    )
    return D7RuntimePairInput(
        binding=binding,
        d4_permission=D4GuidancePermission(
            action="continue_center",
            target_node_id=d4_target if d4_target is not None else binding.owner_node_id,
            new_plan_id=binding.plan_id,
            new_plan_version=binding.plan_version,
            coalition_id=binding.coalition_id,
            coalition_version=binding.coalition_version,
        ),
        terminal_association=terminal,
        observation=observation,
        timestamp_s=timestamp_s,
        resource_id=binding.resource_id,
        terminal_locked=True,
        current_speed_mps=6.0,
        intercept_speed_mps=6.0,
        relative_position_ned=(20.0, 0.0, 0.0),
        relative_velocity_ned=(-4.0, 0.0, 0.0),
        requested_guidance_law="png_vm",
    )
