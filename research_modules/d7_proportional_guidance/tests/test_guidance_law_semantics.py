from __future__ import annotations

from dataclasses import replace

from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    D7RuntimeBus,
    D7RuntimePairInput,
    GUIDANCE_LAW_SEMANTICS_VERSION,
    GuidanceMode,
    PngGuidanceConfig,
    guidance_law_semantic_violations,
    summarize_runtime_bus_outputs,
)


def test_rejected_visual_candidate_executes_radar_pn_and_never_switches() -> None:
    bus = D7RuntimeBus(_config(min_bbox_area_ratio=0.01))
    output = bus.evaluate_pair(_pair_input(timestamp_s=0.0, half_size_px=3.0))
    record = output.as_log_record()
    summary = summarize_runtime_bus_outputs([output])

    assert output.raw_terminal_gate_allowed is True
    assert output.effective_terminal_contract_allowed is True
    assert output.camera_quality_gate_passed is False
    assert output.effective_control_authorized is False
    assert output.latched_visual_mode_active is False
    assert output.configured_guidance_law == "png_vm"
    assert output.configured_midcourse_guidance_law == "radar_pn"
    assert output.configured_terminal_guidance_law == "png_vm"
    assert output.candidate_guidance_law == "png_vm"
    assert output.executed_guidance_law == "radar_pn"
    assert output.mode == GuidanceMode.HANDOVER_PENDING
    assert output.visual_control_active is False
    assert output.executed_visual_mode_switch is False
    assert output.selected_velocity_ned is None
    assert guidance_law_semantic_violations(output) == ()

    assert record["guidance_law_semantics_version"] == (
        GUIDANCE_LAW_SEMANTICS_VERSION
    )
    assert record["configured_guidance_law"] == "png_vm"
    assert record["candidate_guidance_law"] == "png_vm"
    assert record["executed_guidance_law"] == "radar_pn"
    assert record["effective_control_authorized"] is False
    assert record["executed_visual_mode_switch"] is False
    assert summary["configured_guidance_law_counts"] == {"png_vm": 1}
    assert summary["candidate_guidance_law_counts"] == {"png_vm": 1}
    assert summary["executed_guidance_law_counts"] == {"radar_pn": 1}
    assert summary["visual_control_active_count"] == 0
    assert summary["executed_visual_mode_switch_count"] == 0
    assert summary["guidance_law_semantic_violation_count"] == 0


def test_visual_mode_switch_requires_effective_control_and_is_counted_once() -> None:
    bus = D7RuntimeBus(_config(min_bbox_area_ratio=0.0001))
    outputs = [
        bus.evaluate_pair(
            _pair_input(timestamp_s=index * 0.1, half_size_px=20.0 + index)
        )
        for index in range(4)
    ]
    switched = [row for row in outputs if row.executed_visual_mode_switch]
    summary = summarize_runtime_bus_outputs(outputs)

    assert len(switched) == 1
    assert switched[0].effective_control_authorized is True
    assert switched[0].latched_visual_mode_active is True
    assert switched[0].mode == GuidanceMode.VISION_TERMINAL
    assert switched[0].candidate_guidance_law == "png_vm"
    assert switched[0].executed_guidance_law == "png_vm"
    assert switched[0].selected_velocity_ned is not None
    assert all(guidance_law_semantic_violations(row) == () for row in outputs)
    assert summary["executed_visual_mode_switch_count"] == 1
    assert summary["visual_mode_entry_transition_count"] == 1
    assert summary["effective_control_authorized_count"] >= 1
    assert summary["guidance_law_semantic_violation_count"] == 0


def test_semantic_helper_flags_visual_law_without_effective_control() -> None:
    rejected = D7RuntimeBus(_config(min_bbox_area_ratio=0.01)).evaluate_pair(
        _pair_input(timestamp_s=0.0, half_size_px=3.0)
    )
    malformed = replace(rejected, guidance_law="png_vm")

    assert guidance_law_semantic_violations(malformed) == (
        "executed_visual_law_without_effective_control",
    )


def test_termination_snapshot_has_no_executed_law() -> None:
    bus = D7RuntimeBus(_config(min_bbox_area_ratio=0.01))
    bus.evaluate_pair(_pair_input(timestamp_s=0.0, half_size_px=3.0))
    snapshot = bus.evaluate_pair(
        replace(
            _pair_input(timestamp_s=0.1, half_size_px=3.0),
            termination_snapshot=True,
            termination_status="aborted",
            termination_reason="terminal_detection_acquisition_timeout",
        )
    )

    assert snapshot.termination_snapshot is True
    assert snapshot.executed_guidance_law is None
    assert snapshot.visual_control_active is False
    assert snapshot.executed_visual_mode_switch is False
    assert guidance_law_semantic_violations(snapshot) == ()
    assert snapshot.as_log_record()["executed_guidance_law"] is None


def _config(*, min_bbox_area_ratio: float) -> PngGuidanceConfig:
    return PngGuidanceConfig(
        dt_s=0.1,
        min_bbox_area_ratio=min_bbox_area_ratio,
        min_stable_frames=1,
        edge_margin_ratio=0.01,
        max_los_rate_variance_radps2=10.0,
        los_rate_window=2,
        max_visual_latency_s=1.0,
        min_maneuver_margin=0.0,
        law="png_vm",
    )


def _pair_input(*, timestamp_s: float, half_size_px: float) -> D7RuntimePairInput:
    binding = AssignmentGuidanceBinding(
        plan_id="plan-law-semantics",
        plan_version=1,
        owner_node_id="center",
        assignment_id="assign-R1-G1",
        resource_id="R1",
        vehicle_name="Interceptor1",
        assigned_global_track_id="G1",
        track_version=1,
        authorization_state="approved",
    )
    return D7RuntimePairInput(
        binding=binding,
        terminal_association={
            "resource_id": "R1",
            "assigned_global_track_id": "G1",
            "local_track_id": "camera-0:track-1",
            "decision_state": "locked",
            "friend_conflict_state": "none",
            "assignment_version": 1,
            "plan_version": 1,
            "metadata": {"execution_gate_pass": True},
        },
        observation={
            "timestamp_s": timestamp_s,
            "frame_timestamp_s": timestamp_s,
            "bbox_xyxy": (
                320.0 - half_size_px,
                240.0 - half_size_px,
                320.0 + half_size_px,
                240.0 + half_size_px,
            ),
            "confidence": 0.95,
            "local_track_id": "camera-0:track-1",
            "assigned_global_track_id": "G1",
            "camera_id": "front_center",
            "measurement_age_s": 0.0,
        },
        timestamp_s=timestamp_s,
        requested_guidance_law="png_vm",
        current_heading_rad=0.0,
        current_speed_mps=8.0,
        intercept_speed_mps=8.0,
        relative_position_ned=(20.0, 0.0, 0.0),
        relative_velocity_ned=(-5.0, 0.0, 0.0),
    )
