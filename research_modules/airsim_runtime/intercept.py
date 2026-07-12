"""Controlled 2v2 AirSim interception episode for Blocks.

This module is still simulation-only. It commands SimpleFlight vehicles inside
AirSim and uses non-vehicle Unreal actors as targets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from airsim_dryrun.models import AirSimFrame
from d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    GuidanceMode,
    GuidanceState,
    MidcourseReacquisitionConfig,
    MidcourseReacquisitionSelector,
    PngGuidanceConfig,
    TerminalDeliveryConfig,
    TerminalDeliveryState,
    TerminalGuidanceDelivery,
    TerminalLifecycleContext,
    VisionGuidanceObservation,
    build_cooperative_guidance_topology,
    coerce_assignment_guidance_binding,
    compute_midcourse_reacquisition_command,
    compute_pure_pursuit_command,
    evaluate_terminal_png_contract,
    guidance_mode_from_terminal_contract,
    select_runtime_guidance_law,
)

from .models import BlocksSmokeConfig


@dataclass
class InterceptPair:
    resource_id: str
    vehicle_name: str
    target_id: str
    active: bool = True
    status: str = "active"
    abort_reason: str | None = None
    min_range_m: float = float("inf")
    time_to_intercept_s: float | None = None
    last_detection_s: float | None = None
    terminal_locked: bool = False
    terminal_handover_pending: bool = False
    terminal_switch_reject_reason: str = ""
    terminal_contract_reject_reason: str = ""
    guidance_binding: AssignmentGuidanceBinding | None = None
    d4_permission: D4GuidancePermission | None = None
    terminal_association: Any | None = None
    member_role: str = "primary"
    wave_id: int = 0
    activation_state: str = "active"
    assigned_global_track_id: str | None = None
    terminal_acquisition_started_s: float | None = None
    online_truth_id_used: bool = False
    terminal_delivery: TerminalGuidanceDelivery | None = None
    terminal_delivery_state: str = ""
    terminal_delivery_reason: str = ""
    terminal_local_track_id: str | None = None
    midcourse_selector: MidcourseReacquisitionSelector | None = None
    midcourse_binding_key: tuple[str, str, str, int] | None = None
    last_recorded_mode: str | None = None


@dataclass
class InterceptCommandRecord:
    timestamp_s: float
    resource_id: str
    vehicle_name: str
    target_id: str
    mode: str
    range_m: float
    command_vx_mps: float
    command_vy_mps: float
    command_z_ned_m: float
    los_rate_radps: float
    closing_speed_mps: float
    terminal_locked: bool
    terminal_handover_pending: bool
    plan_id: str
    plan_version: int
    track_version: int
    d4_action: str
    d4_mode: str
    d4_target_node_id: str
    assignment_phase: str
    d5_decision_state: str
    terminal_contract_reject_reason: str
    terminal_contract_allowed: bool
    terminal_control_allowed: bool
    mode_switched: bool
    physical_intercept: bool
    detection_seen: bool
    guidance_law: str
    camera_quality_gate_passed: bool
    los_quality_gate_passed: bool
    maneuver_margin_gate_passed: bool
    terminal_switch_allowed: bool
    terminal_switch_reject_reason: str
    terminal_delivery_state: str
    terminal_delivery_reason: str
    terminal_using_extrapolation: bool
    terminal_prediction_age_s: float | None
    terminal_blind_elapsed_s: float
    terminal_blind_decay: float
    local_track_id: str
    terminal_filter_state: str
    terminal_filter_reason: str
    terminal_filter_innovation_rejected: bool
    terminal_filter_reset: bool
    terminal_filter_reset_reason: str
    terminal_image_innovation_norm_rad: float | None
    terminal_trend_coast_applied: bool
    ttc_raw_area_px2: float | None
    ttc_filtered_area_px2: float | None
    ttc_area_dot_px2_s: float | None
    ttc_reject_reason: str
    terminal_delivery_profile: str
    visual_reacquisition: bool
    terminal_visual_lost_after_coast: bool
    truth_identity_online_use: bool
    bbox_area_ratio: float
    los_rate_variance_radps2: float
    ttc_s: float | None
    maneuver_margin: float
    midcourse_guidance_selection: str
    midcourse_selection_reason: str
    midcourse_reacquisition_active: bool
    midcourse_overshoot_detected: bool
    midcourse_minimum_range_m: float | None
    control_saturated: bool
    collision_seen: bool
    collision_object_name: str
    status: str
    abort_reason: str | None = None


@dataclass
class InterceptRunResult:
    frames: list[AirSimFrame]
    pairs: list[InterceptPair]
    command_records: list[InterceptCommandRecord]
    output_paths: dict[str, Path] = field(default_factory=dict)

    @property
    def success_count(self) -> int:
        return sum(1 for pair in self.pairs if pair.status in {"collision_intercept", "range_intercept"})


def run_controlled_intercept_episode(
    runtime: Any,
    config: BlocksSmokeConfig,
    output_dir: Path,
) -> InterceptRunResult:
    """Run the first real AirSim control gate with actor targets."""

    select_runtime_guidance_law(config.intercept_guidance_law)

    frames: list[AirSimFrame] = []
    command_records: list[InterceptCommandRecord] = []
    pairs: list[InterceptPair] = []
    control_bus = None
    if config.include_integrated_pipeline and not (
        _active_center_replan_enabled(config) or _active_secondary_visual_png_enabled(config)
    ):
        from .episode_bus import MainAirSimEpisodeBus

        control_bus = MainAirSimEpisodeBus(config)
    runtime.prepare_interceptor_control(config)
    try:
        for frame_index, timestamp in enumerate(_control_timestamps(config)):
            frame = runtime.sample_frame(config, frame_index, timestamp, output_dir / "images")
            frame = _annotate_active_replan_frame(config, frame)
            frame = _apply_intercept_detection_dropout(config, frame)
            control_evidence: dict[str, dict[str, Any]] = {}
            if control_bus is not None:
                control_bus.process_frame(frame)
                control_evidence = control_bus.control_evidence()
            frames.append(frame)
            if not pairs:
                pairs = _initial_pairs(frame, config)
            if not pairs:
                continue
            _refresh_pair_assignments(frame, pairs)
            _apply_online_control_evidence(pairs, control_evidence)
            for pair in pairs:
                _reset_midcourse_selector_for_binding_change(pair)
            _step_pairs(runtime, config, frame, pairs, command_records)
            if all(not pair.active for pair in pairs):
                break
        for pair in pairs:
            if pair.active:
                pair.active = False
                pair.status = "timeout"
        output_paths = _write_intercept_outputs(
            config,
            output_dir,
            frames,
            pairs,
            command_records,
        )
        return InterceptRunResult(
            frames=frames,
            pairs=pairs,
            command_records=command_records,
            output_paths=output_paths,
        )
    finally:
        vehicle_names = tuple(pair.vehicle_name for pair in pairs) or tuple(config.resource_vehicle_names)
        runtime.land_and_release_interceptors(vehicle_names, land=config.intercept_land_after)


def _step_pairs(
    runtime: Any,
    config: BlocksSmokeConfig,
    frame: AirSimFrame,
    pairs: list[InterceptPair],
    command_records: list[InterceptCommandRecord],
) -> None:
    resources = {resource.resource_id: resource for resource in frame.resources}
    targets = {target.object_id: target for target in frame.truth_objects if target.object_type == "target"}
    detections = _detections_by_resource(frame)
    for pair in pairs:
        if not pair.active:
            continue
        resource = resources.get(pair.resource_id)
        target = targets.get(pair.target_id)
        if resource is None:
            _abort_pair(runtime, pair, "resource_missing")
            continue
        if target is None:
            _abort_pair(runtime, pair, "target_missing")
            continue

        resource_position = np.asarray(resource.position_ned, dtype=float)
        target_position = np.asarray(target.position_ned, dtype=float)
        resource_velocity = np.asarray(resource.velocity_ned, dtype=float)
        target_velocity = np.asarray(target.velocity_ned, dtype=float)
        relative = target_position - resource_position
        range_m = float(np.linalg.norm(relative))
        pair.min_range_m = min(pair.min_range_m, range_m)

        collision = runtime.collision_info(pair.vehicle_name)
        collision_seen = _is_assigned_target_collision(collision, target)
        collision["target_collision_seen"] = collision_seen
        if collision_seen:
            pair.status = "collision_intercept"
            pair.time_to_intercept_s = frame.timestamp
            pair.active = False
            runtime.hover_interceptor(pair.vehicle_name)
            _record_command(config, frame.timestamp, pair, range_m, (0.0, 0.0, 0.0), None, True, collision, command_records)
            continue
        if range_m <= config.intercept_radius_m:
            pair.status = "range_intercept"
            pair.time_to_intercept_s = frame.timestamp
            pair.active = False
            runtime.hover_interceptor(pair.vehicle_name)
            _record_command(config, frame.timestamp, pair, range_m, (0.0, 0.0, 0.0), None, True, collision, command_records)
            continue

        pair.d4_permission = _d4_permission_for_pair(frame, pair)
        pair.terminal_association = _terminal_association_for_pair(frame, pair, None)
        visible_detection = _assigned_detection(frame, pair)
        detection_seen = visible_detection is not None
        if detection_seen:
            pair.last_detection_s = frame.timestamp
            pair.terminal_acquisition_started_s = None
        in_terminal_range = range_m <= config.intercept_terminal_switch_range_m
        if in_terminal_range:
            pair.terminal_handover_pending = True
        if _terminal_detection_acquisition_timed_out(
            pair,
            timestamp_s=frame.timestamp,
            in_terminal_range=in_terminal_range,
            detection_seen=detection_seen,
            timeout_s=config.intercept_detection_timeout_s,
        ):
            _abort_pair(runtime, pair, "terminal_detection_acquisition_timeout")
            _record_command(config, frame.timestamp, pair, range_m, (0.0, 0.0, 0.0), None, False, collision, command_records)
            continue

        velocity_command, pn_command = _pn_velocity_command(
            config,
            pair,
            frame.timestamp,
            resource_position,
            resource_velocity,
            target_position,
            target_velocity,
            visible_detection,
            _camera_info_for_pair(frame, pair),
        )
        if _terminal_delivery_requires_abort(pair):
            _abort_pair(runtime, pair, "terminal_visual_lost_after_coast")
            _record_command(
                config,
                frame.timestamp,
                pair,
                range_m,
                (0.0, 0.0, 0.0),
                pn_command,
                detection_seen,
                collision,
                command_records,
            )
            continue
        if resource_position[2] > 0.25:
            _abort_pair(runtime, pair, "below_ground_or_invalid_altitude")
            _record_command(config, frame.timestamp, pair, range_m, (0.0, 0.0, 0.0), pn_command, detection_seen, collision, command_records)
            continue
        runtime.command_velocity_z(
            config,
            vehicle_name=pair.vehicle_name,
            velocity_ned=velocity_command,
            duration_s=config.control_dt_s,
            yaw_deg_override=_yaw_override_deg(config, resource_position, target_position),
        )
        _record_command(
            config,
            frame.timestamp,
            pair,
            range_m,
            velocity_command,
            pn_command,
            detection_seen,
            collision,
            command_records,
        )


def _pn_velocity_command(
    config: BlocksSmokeConfig,
    pair: InterceptPair,
    timestamp: float,
    resource_position: np.ndarray,
    resource_velocity: np.ndarray,
    target_position: np.ndarray,
    target_velocity: np.ndarray,
    visible_detection: Any | None,
    camera_info: Any | None = None,
) -> tuple[tuple[float, float, float], Any]:
    pursuer_speed = float(np.linalg.norm(resource_velocity[:2]))
    if pursuer_speed < 0.5:
        initial_heading = math.atan2(
            float(target_position[1] - resource_position[1]),
            float(target_position[0] - resource_position[0]),
        )
        resource_velocity = np.asarray(
            [
                config.intercept_speed_mps * math.cos(initial_heading),
                config.intercept_speed_mps * math.sin(initial_heading),
                0.0,
            ],
            dtype=float,
        )
    law_selection = select_runtime_guidance_law(config.intercept_guidance_law)
    configured_law = law_selection.requested_law.value
    visual_guidance_enabled = law_selection.requires_terminal_gate
    mode = (
        GuidanceMode.VISION_TERMINAL
        if visual_guidance_enabled and pair.terminal_locked
        else GuidanceMode.RADAR_MIDCOURSE
    )
    pursuer_state = GuidanceState(
        entity_id=pair.resource_id,
        timestamp_s=timestamp,
        position_m=(float(resource_position[0]), float(resource_position[1])),
        velocity_mps=(float(resource_velocity[0]), float(resource_velocity[1])),
    )
    target_state = GuidanceState(
        entity_id=pair.target_id,
        timestamp_s=timestamp,
        position_m=(float(target_position[0]), float(target_position[1])),
        velocity_mps=(float(target_velocity[0]), float(target_velocity[1])),
        source="airsim_actor_track",
    )
    if law_selection.midcourse_law.value == "pure_pursuit":
        command = compute_pure_pursuit_command(
            pursuer=pursuer_state,
            target=target_state,
            dt_s=config.control_dt_s,
            mode=GuidanceMode.RADAR_MIDCOURSE,
            max_turn_rate_radps=config.intercept_max_turn_rate_radps,
        )
        command.metadata["guidance_law"] = "pure_pursuit"
    else:
        if pair.midcourse_selector is None:
            pair.midcourse_selector = MidcourseReacquisitionSelector(
                MidcourseReacquisitionConfig(
                    exit_closing_speed_mps=2.0,
                    exit_consecutive_frames=max(10, int(round(1.0 / config.control_dt_s))),
                    max_reacquisition_turn_rate_radps=config.intercept_max_turn_rate_radps,
                )
            )
        command = compute_midcourse_reacquisition_command(
            pair.midcourse_selector,
            pursuer=pursuer_state,
            target=target_state,
            dt_s=config.control_dt_s,
            navigation_constant=config.intercept_navigation_constant,
            mode=mode,
            max_lateral_accel_mps2=config.intercept_max_lateral_accel_mps2,
            max_turn_rate_radps=config.intercept_max_turn_rate_radps,
        )
        command.metadata["guidance_law"] = command.metadata.get("guidance_law", "radar_pn")
    command.metadata["configured_guidance_law"] = configured_law
    predicted_resource_velocity = np.asarray(_midcourse_velocity(config, command), dtype=float)
    if visual_guidance_enabled and pair.terminal_handover_pending:
        if str(config.intercept_yaw_mode).lower() == "look_at_target":
            current_heading = math.atan2(
                float(target_position[1] - resource_position[1]),
                float(target_position[0] - resource_position[0]),
            )
        else:
            current_heading = math.atan2(float(resource_velocity[1]), float(resource_velocity[0]))
        observation = (
            None
            if visible_detection is None
            else _vision_observation_from_detection(
                frame_timestamp=timestamp,
                pair=pair,
                detection=visible_detection,
                camera_info=camera_info,
            )
        )
        contract = evaluate_terminal_png_contract(
            binding=pair.guidance_binding,
            d4_permission=pair.d4_permission,
            terminal_association=pair.terminal_association,
            observation=observation,
            timestamp_s=timestamp,
            resource_id=pair.resource_id,
        )
        pair.terminal_contract_reject_reason = contract.reject_reason
        transient_visual_loss = bool(
            pair.terminal_locked
            and observation is None
            and contract.reject_reason
            in {"d5_not_locked", "terminal_association_missing", "visual_observation_missing"}
        )
        if not contract.allowed and not transient_visual_loss:
            if pair.terminal_delivery is not None:
                blocked = pair.terminal_delivery.block(
                    assigned_global_track_id=(
                        pair.assigned_global_track_id
                        or pair.guidance_binding.assigned_global_track_id
                    ),
                    reason=contract.reject_reason,
                )
                pair.terminal_delivery_state = blocked.state.value
                pair.terminal_delivery_reason = blocked.reason
            guidance_mode = guidance_mode_from_terminal_contract(
                contract,
                handover_pending=pair.terminal_handover_pending,
                terminal_locked=pair.terminal_locked,
            )
            command.metadata.update(
                {
                    "terminal_contract_allowed": False,
                    "terminal_contract_reject_reason": contract.reject_reason,
                    "d4_action": contract.d4_action,
                    "d5_decision_state": contract.d5_decision_state,
                    "plan_id": contract.plan_id,
                    "plan_version": contract.plan_version,
                    "track_version": contract.track_version,
                    "mode_override": guidance_mode.value,
                    "guidance_law": "radar_pn",
                    "terminal_switch_allowed": False,
                    "terminal_switch_reject_reason": contract.reject_reason,
                }
            )
            return _midcourse_velocity(config, command), command

        delivery = _terminal_delivery_for_pair(config, pair, camera_info=camera_info)
        delivery_result = delivery.evaluate(
            assigned_global_track_id=(
                pair.assigned_global_track_id
                or pair.guidance_binding.assigned_global_track_id
            ),
            timestamp_s=timestamp,
            observation=observation,
            current_heading_rad=current_heading,
            current_speed_mps=max(float(np.linalg.norm(predicted_resource_velocity[:2])), config.intercept_speed_mps),
            intercept_speed_mps=config.intercept_speed_mps,
            relative_position_ned=tuple(float(value) for value in (target_position - resource_position)),
            relative_velocity_ned=tuple(float(value) for value in (target_velocity - predicted_resource_velocity)),
            command_z_ned_m=0.0,
            lifecycle_context=_terminal_lifecycle_context(pair, observation),
            soft_prediction_eligible=_terminal_soft_prediction_eligible(
                pair,
                contract_allowed=bool(contract.allowed),
            ),
        )
        pair.terminal_delivery_state = delivery_result.state.value
        pair.terminal_delivery_reason = delivery_result.reason
        visual_command = delivery_result.command
        command.metadata.update(
            {
                "terminal_delivery_state": delivery_result.state.value,
                "terminal_delivery_reason": delivery_result.reason,
                "terminal_using_extrapolation": delivery_result.using_extrapolation,
                "terminal_prediction_age_s": delivery_result.measurement_age_s,
                "terminal_blind_elapsed_s": delivery_result.blind_elapsed_s,
                "terminal_blind_decay": delivery_result.blind_decay,
                "terminal_loss_frame_count": delivery_result.loss_frame_count,
                "local_track_id": (
                    observation.local_track_id
                    if observation is not None
                    else _optional_record_string(pair.terminal_association, "local_track_id")
                ),
                "terminal_filter_state": delivery_result.filter_audit_state.value,
                "terminal_filter_reason": delivery_result.filter_audit_reason,
                "terminal_filter_innovation_rejected": (
                    delivery_result.filter_audit_state.value == "innovation_rejected"
                ),
                "terminal_filter_reset": delivery_result.lifecycle_reset,
                "terminal_filter_reset_reason": delivery_result.lifecycle_reset_reason,
                "terminal_image_innovation_norm_rad": delivery_result.image_innovation_norm_rad,
                "terminal_trend_coast_applied": delivery_result.trend_coast_applied,
                "terminal_trend_coast_velocity_ned": delivery_result.trend_coast_velocity_ned,
                "terminal_delivery_profile": _terminal_delivery_profile(config),
                "online_truth_id_used": pair.online_truth_id_used,
                **_terminal_camera_metadata(camera_info, delivery.png_config),
            }
        )
        if visual_command is None:
            pair.terminal_switch_reject_reason = delivery_result.reason
            command.metadata.update(
                {
                    "terminal_contract_allowed": bool(contract.allowed),
                    "terminal_contract_reject_reason": contract.reject_reason,
                    "terminal_contract_coast_exception": transient_visual_loss,
                    "d4_action": contract.d4_action,
                    "d5_decision_state": contract.d5_decision_state,
                    "plan_id": contract.plan_id,
                    "plan_version": contract.plan_version,
                    "track_version": contract.track_version,
                    "mode_override": GuidanceMode.RADAR_MIDCOURSE.value,
                    "guidance_law": "radar_pn",
                    "terminal_switch_allowed": False,
                    "terminal_switch_reject_reason": delivery_result.reason,
                }
            )
            return _midcourse_velocity(config, command), command
        pair.terminal_switch_reject_reason = visual_command.quality.reject_reason
        if visual_command.quality.terminal_switch_allowed:
            pair.terminal_locked = True
        if pair.terminal_locked:
            command.metadata.update(
                {
                    "terminal_contract_allowed": bool(contract.allowed),
                    "terminal_contract_reject_reason": contract.reject_reason,
                    "terminal_contract_coast_exception": transient_visual_loss,
                    "d4_action": contract.d4_action,
                    "d5_decision_state": contract.d5_decision_state,
                    "plan_id": contract.plan_id,
                    "plan_version": contract.plan_version,
                    "track_version": contract.track_version,
                    "mode_override": GuidanceMode.VISION_TERMINAL.value,
                    "guidance_law": visual_command.guidance_law,
                    "camera_quality_gate_passed": visual_command.quality.camera_quality_gate_passed,
                    "los_quality_gate_passed": visual_command.quality.los_quality_gate_passed,
                    "maneuver_margin_gate_passed": visual_command.quality.maneuver_margin_gate_passed,
                    "terminal_switch_allowed": visual_command.quality.terminal_switch_allowed,
                    "terminal_switch_reject_reason": visual_command.quality.reject_reason,
                    "bbox_area_ratio": visual_command.quality.bbox_area_ratio,
                    "los_rate_variance_radps2": visual_command.quality.los_rate_variance_radps2,
                    "ttc_s": visual_command.quality.ttc_s,
                    "maneuver_margin": visual_command.quality.maneuver_margin,
                    "control_saturated": visual_command.control_saturated,
                }
            )
            return visual_command.velocity_ned, command
        command.metadata.update(
            {
                "terminal_contract_allowed": bool(contract.allowed),
                "terminal_contract_reject_reason": contract.reject_reason,
                "terminal_contract_coast_exception": transient_visual_loss,
                "d4_action": contract.d4_action,
                "d5_decision_state": contract.d5_decision_state,
                "plan_id": contract.plan_id,
                "plan_version": contract.plan_version,
                "track_version": contract.track_version,
                **_visual_metadata(visual_command),
            }
        )

    if pair.terminal_locked:
        heading = math.atan2(
            float(target_position[1] - resource_position[1]),
            float(target_position[0] - resource_position[0]),
        )
    else:
        heading = command.desired_heading_rad
    return _velocity_from_heading(config, heading), command


def _yaw_override_deg(
    config: BlocksSmokeConfig,
    resource_position: np.ndarray,
    target_position: np.ndarray,
) -> float | None:
    if str(config.intercept_yaw_mode).lower() != "look_at_target":
        return None
    relative = target_position - resource_position
    if abs(float(relative[0])) + abs(float(relative[1])) < 1e-9:
        return None
    return float(math.degrees(math.atan2(float(relative[1]), float(relative[0]))))


def _midcourse_velocity(config: BlocksSmokeConfig, command: Any) -> tuple[float, float, float]:
    return _velocity_from_heading(config, float(command.desired_heading_rad))


def _velocity_from_heading(
    config: BlocksSmokeConfig,
    heading_rad: float,
) -> tuple[float, float, float]:
    return (
        float(config.intercept_speed_mps * math.cos(heading_rad)),
        float(config.intercept_speed_mps * math.sin(heading_rad)),
        0.0,
    )


def _terminal_delivery_for_pair(
    config: BlocksSmokeConfig,
    pair: InterceptPair,
    *,
    camera_info: Any | None = None,
) -> TerminalGuidanceDelivery:
    if pair.terminal_delivery is None:
        width_px, height_px, focal_length_px = _terminal_camera_intrinsics(camera_info)
        png_config = PngGuidanceConfig(
            dt_s=config.control_dt_s,
            image_width_px=width_px,
            image_height_px=height_px,
            focal_length_px=focal_length_px,
            min_bbox_area_ratio=config.intercept_min_bbox_area_ratio,
            min_detection_confidence=config.intercept_min_detection_confidence,
            min_stable_frames=config.intercept_min_stable_detection_frames,
            max_visual_latency_s=config.intercept_max_visual_latency_s,
            navigation_constant=config.intercept_navigation_constant,
            max_turn_rate_radps=config.intercept_max_turn_rate_radps,
            max_lateral_accel_mps2=config.intercept_max_lateral_accel_mps2,
            min_maneuver_margin=config.intercept_min_maneuver_margin,
            law=config.intercept_guidance_law,  # type: ignore[arg-type]
        )
        pair.terminal_delivery = TerminalGuidanceDelivery(
            png_config=png_config,
            config=TerminalDeliveryConfig(
                control_dt_s=config.control_dt_s,
                soft_innovation_reject_prediction=(
                    config.intercept_terminal_soft_prediction_enabled
                ),
                delivery_trend_coast=config.intercept_terminal_trend_coast_enabled,
            ),
        )
    return pair.terminal_delivery


def _camera_info_for_pair(frame: AirSimFrame, pair: InterceptPair) -> Any | None:
    for camera in frame.cameras:
        owner_id = str(getattr(camera, "owner_id", ""))
        camera_id = str(getattr(camera, "camera_id", ""))
        if owner_id == pair.vehicle_name or camera_id.split(":", 1)[0] == pair.vehicle_name:
            return camera
    return None


def _terminal_camera_intrinsics(camera_info: Any | None) -> tuple[int, int, float]:
    width_px = max(1, int(getattr(camera_info, "width", 640) or 640))
    height_px = max(1, int(getattr(camera_info, "height", 480) or 480))
    focal_length_px = float(getattr(camera_info, "fx", 0.0) or 0.0)
    if not math.isfinite(focal_length_px) or focal_length_px <= 0.0:
        focal_length_px = width_px * 0.5
    return width_px, height_px, focal_length_px


def _terminal_camera_metadata(
    camera_info: Any | None,
    png_config: PngGuidanceConfig,
) -> dict[str, Any]:
    return {
        "camera_image_width_px": int(png_config.image_width_px),
        "camera_image_height_px": int(png_config.image_height_px),
        "camera_focal_length_px": float(png_config.focal_length_px),
        "camera_intrinsics_source": (
            "airsim_camera_info" if camera_info is not None else "runtime_fallback"
        ),
    }


def _vision_observation_from_detection(
    *,
    frame_timestamp: float,
    pair: InterceptPair,
    detection: Any,
    camera_info: Any | None = None,
) -> VisionGuidanceObservation:
    measurement_timestamp = float(getattr(detection, "timestamp", frame_timestamp))
    detection_metadata = dict(getattr(detection, "metadata", {}) or {})
    return VisionGuidanceObservation(
        timestamp_s=float(frame_timestamp),
        frame_timestamp_s=measurement_timestamp,
        bbox_xyxy=tuple(float(value) for value in detection.bbox_xyxy),
        detection_confidence=float(getattr(detection, "confidence", 0.0)),
        local_track_id=str(getattr(detection, "local_track_id", "")) or None,
        assigned_global_track_id=(
            pair.guidance_binding.assigned_global_track_id
            if pair.guidance_binding is not None
            else pair.target_id
        ),
        camera_id=str(getattr(detection, "camera_id", "")) or None,
        metadata={
            "measurement_timestamp": measurement_timestamp,
            "arrival_timestamp": float(frame_timestamp),
            "exposure_timestamp": float(
                detection_metadata.get("exposure_timestamp", measurement_timestamp)
            ),
            "visual_latency_s": max(0.0, float(frame_timestamp) - measurement_timestamp),
            "source_node_id": pair.resource_id,
            "payload_kind": "bbox",
            "detection_source": detection_metadata.get("detection_source", "airsim_runtime"),
            "bbox_edge_clipped": _bbox_edge_clipped(detection.bbox_xyxy, camera_info),
            **_camera_geometry_metadata(camera_info, frame_timestamp),
        },
    )


def _terminal_lifecycle_context(
    pair: InterceptPair,
    observation: VisionGuidanceObservation | None,
) -> TerminalLifecycleContext:
    binding = pair.guidance_binding
    assigned_global_track_id = (
        pair.assigned_global_track_id
        or (binding.assigned_global_track_id if binding is not None else pair.target_id)
    )
    observed_local_track_id = (
        observation.local_track_id
        if observation is not None and observation.local_track_id
        else None
    )
    if observed_local_track_id is not None:
        pair.terminal_local_track_id = observed_local_track_id
    local_track_id = pair.terminal_local_track_id
    return TerminalLifecycleContext(
        resource_id=pair.resource_id,
        assigned_global_track_id=str(assigned_global_track_id),
        local_track_id=local_track_id,
        plan_owner_id=(binding.owner_node_id if binding is not None else None),
        plan_version=(int(binding.plan_version) if binding is not None else 0),
    )


def _terminal_soft_prediction_eligible(
    pair: InterceptPair,
    *,
    contract_allowed: bool,
) -> bool:
    association = pair.terminal_association
    metadata = dict(_record_value(association, "metadata", {}) or {})
    friend_conflict = str(
        _record_value(association, "friend_conflict_state", "none") or "none"
    ).lower()
    duplicate_lock = bool(
        _record_value(association, "duplicate_terminal_lock_risk", False)
        or metadata.get("duplicate_terminal_lock_risk", False)
    )
    return bool(contract_allowed and friend_conflict == "none" and not duplicate_lock)


def _terminal_delivery_profile(config: BlocksSmokeConfig) -> str:
    enabled = []
    if config.intercept_terminal_soft_prediction_enabled:
        enabled.append("soft_prediction")
    if config.intercept_terminal_trend_coast_enabled:
        enabled.append("trend_coast")
    return "candidate_" + "_".join(enabled) if enabled else "baseline"


def _camera_geometry_metadata(
    camera_info: Any | None,
    arrival_timestamp: float,
) -> dict[str, Any]:
    if camera_info is None:
        return {
            "camera_geometry_valid": False,
            "camera_geometry_unavailable_reasons": ["camera_info_unavailable"],
        }
    try:
        world_to_camera = np.asarray(
            getattr(camera_info, "rotation_world_to_camera"), dtype=float
        ).reshape(3, 3)
        camera_to_ned = world_to_camera.T
        camera_position_ned = tuple(float(value) for value in camera_info.position_ned)
        camera_timestamp = float(getattr(camera_info, "timestamp", arrival_timestamp))
        width = max(1, int(getattr(camera_info, "width", 640) or 640))
        height = max(1, int(getattr(camera_info, "height", 480) or 480))
        intrinsics = (
            (float(getattr(camera_info, "fx", width * 0.5)), 0.0, float(getattr(camera_info, "cx", width * 0.5))),
            (0.0, float(getattr(camera_info, "fy", width * 0.5)), float(getattr(camera_info, "cy", height * 0.5))),
            (0.0, 0.0, 1.0),
        )
    except (AttributeError, TypeError, ValueError):
        return {
            "camera_geometry_valid": False,
            "camera_geometry_unavailable_reasons": ["camera_info_invalid"],
        }
    attitude_age_s = max(0.0, float(arrival_timestamp) - camera_timestamp)
    return {
        "camera_intrinsics": intrinsics,
        "camera_to_ned_rotation": tuple(tuple(float(value) for value in row) for row in camera_to_ned),
        "camera_position_ned": camera_position_ned,
        "attitude_timestamp_s": camera_timestamp,
        "attitude_age_s": attitude_age_s,
        "camera_geometry_valid": attitude_age_s <= 0.05,
        "camera_geometry_source": "airsim_camera_info",
        "camera_geometry_unavailable_reasons": (
            [] if attitude_age_s <= 0.05 else ["camera_attitude_unavailable_or_stale"]
        ),
    }


def _bbox_edge_clipped(bbox_xyxy: Any, camera_info: Any | None) -> bool:
    if camera_info is None:
        return False
    try:
        x1, y1, x2, y2 = (float(value) for value in bbox_xyxy)
        width = float(getattr(camera_info, "width"))
        height = float(getattr(camera_info, "height"))
    except (AttributeError, TypeError, ValueError):
        return False
    return bool(x1 <= 0.0 or y1 <= 0.0 or x2 >= width or y2 >= height)


def _visual_metadata(visual_command: Any) -> dict[str, Any]:
    return {
        "guidance_law": visual_command.guidance_law,
        "camera_quality_gate_passed": visual_command.quality.camera_quality_gate_passed,
        "los_quality_gate_passed": visual_command.quality.los_quality_gate_passed,
        "maneuver_margin_gate_passed": visual_command.quality.maneuver_margin_gate_passed,
        "terminal_switch_allowed": visual_command.quality.terminal_switch_allowed,
        "terminal_switch_reject_reason": visual_command.quality.reject_reason,
        "bbox_area_ratio": visual_command.quality.bbox_area_ratio,
        "los_rate_variance_radps2": visual_command.quality.los_rate_variance_radps2,
        "ttc_s": visual_command.quality.ttc_s,
        "ttc_raw_area_px2": visual_command.quality.ttc_raw_area_px2,
        "ttc_filtered_area_px2": visual_command.quality.ttc_filtered_area_px2,
        "ttc_area_dot_px2_s": visual_command.quality.ttc_area_dot_px2_s,
        "ttc_reject_reason": visual_command.quality.ttc_reject_reason,
        "maneuver_margin": visual_command.quality.maneuver_margin,
        "required_turn_rate_radps": visual_command.quality.required_turn_rate_radps,
        "turn_rate_capacity_radps": visual_command.quality.turn_rate_capacity_radps,
        "control_saturated": visual_command.control_saturated,
    }


def _initial_pairs(frame: AirSimFrame, config: BlocksSmokeConfig) -> list[InterceptPair]:
    resources = sorted(frame.resources, key=lambda item: item.resource_id)
    sorted_targets = sorted(
        (target for target in frame.truth_objects if target.object_type == "target"),
        key=lambda item: item.object_id,
    )
    targets = {target.object_id: target for target in sorted_targets}
    if config.cooperative_demand_enabled and resources and sorted_targets:
        high_threat_count = min(
            max(0, int(config.cooperative_high_threat_target_count)),
            len(sorted_targets),
        )
        required_counts = {
            target.object_id: (
                int(config.high_threat_required_resource_count)
                if index < high_threat_count
                else 1
            )
            for index, target in enumerate(sorted_targets)
        }
        vehicle_names = {
            resource.resource_id: str(
                resource.metadata.get("airsim_vehicle_name") or resource.resource_id
            )
            for resource in resources
        }
        topology = build_cooperative_guidance_topology(
            resource_ids=[resource.resource_id for resource in resources],
            target_ids=[target.object_id for target in sorted_targets],
            required_counts=required_counts,
            coordination_mode={
                target.object_id: (
                    config.cooperative_coordination_mode
                    if required_counts[target.object_id] > 1
                    else "independent"
                )
                for target in sorted_targets
            },
            primary_count=int(config.cooperative_primary_count),
            plan_id="airsim_control_cooperative_plan",
            plan_version=1,
            vehicle_names=vehicle_names,
            arrival_windows={
                target.object_id: (0.0, float(config.intercept_max_duration_s))
                for target in sorted_targets
                if required_counts[target.object_id] > 1
            },
        )
        return [
            InterceptPair(
                resource_id=binding.resource_id,
                vehicle_name=binding.vehicle_name,
                target_id=binding.assigned_global_track_id,
                active=binding.activation_state == "active",
                status=("active" if binding.activation_state == "active" else "standby"),
                guidance_binding=binding,
                d4_permission=_d4_permission_for_pair(frame, None),
                member_role=binding.member_role,
                wave_id=binding.wave_id,
                activation_state=binding.activation_state,
                assigned_global_track_id=binding.assigned_global_track_id,
            )
            for binding in topology.bindings
        ]
    pairs: list[InterceptPair] = []
    for resource, fallback_target in zip(resources, sorted_targets, strict=False):
        target = _assignment_target_for_resource(frame, resource.resource_id, targets, fallback_target)
        vehicle_name = str(resource.metadata.get("airsim_vehicle_name") or resource.resource_id)
        pairs.append(
            InterceptPair(
                resource_id=resource.resource_id,
                vehicle_name=vehicle_name,
                target_id=target.object_id,
                guidance_binding=_binding_for_pair(frame, resource, target, vehicle_name),
                d4_permission=_d4_permission_for_pair(frame, None),
                assigned_global_track_id=target.object_id,
            )
        )
    return pairs


def _refresh_pair_assignments(frame: AirSimFrame, pairs: list[InterceptPair]) -> None:
    resources = {resource.resource_id: resource for resource in frame.resources}
    targets = {target.object_id: target for target in frame.truth_objects if target.object_type == "target"}
    for pair in pairs:
        resource = resources.get(pair.resource_id)
        if resource is None:
            continue
        current_target = targets.get(pair.target_id)
        fallback_target = current_target or next(iter(targets.values()), None)
        if fallback_target is None:
            continue
        target = _assignment_target_for_resource(frame, pair.resource_id, targets, fallback_target)
        pair.target_id = target.object_id
        if (
            pair.guidance_binding is not None
            and pair.guidance_binding.metadata.get("boundary")
            == "d7_binding_topology_only_no_assignment_optimization_no_vehicle_control"
            and pair.guidance_binding.assigned_global_track_id == pair.target_id
        ):
            continue
        pair.guidance_binding = _binding_for_pair(frame, resource, target, pair.vehicle_name)
        pair.assigned_global_track_id = pair.guidance_binding.assigned_global_track_id


def _reset_midcourse_selector_for_binding_change(pair: InterceptPair) -> None:
    binding_key = (
        pair.target_id,
        str(pair.assigned_global_track_id or pair.target_id),
        _pair_plan_id(pair),
        _pair_plan_version(pair),
    )
    previous = pair.midcourse_binding_key
    pair.midcourse_binding_key = binding_key
    if previous is not None and previous != binding_key and pair.midcourse_selector is not None:
        pair.midcourse_selector.reset()


def _assignment_target_for_resource(
    frame: AirSimFrame,
    resource_id: str,
    targets: dict[str, Any],
    fallback_target: Any,
) -> Any:
    explicit = _matching_metadata_record(
        frame.metadata.get("assignment_guidance_bindings"),
        resource_id=str(resource_id),
        target_id="",
    )
    if explicit is None:
        return fallback_target
    target_id = (
        _optional_record_string(explicit, "target_object_id")
        or _optional_record_string(explicit, "assigned_global_track_id")
        or _optional_record_string(explicit, "target_id")
        or _optional_record_string(explicit, "global_track_id")
    )
    target_id = _normalize_track_id(target_id)
    return targets.get(target_id, fallback_target)


def _detections_by_resource(frame: AirSimFrame) -> dict[str, set[str]]:
    vehicle_to_resource = {
        str(resource.metadata.get("airsim_vehicle_name")): resource.resource_id
        for resource in frame.resources
        if resource.metadata.get("airsim_vehicle_name")
    }
    detections: dict[str, set[str]] = {}
    for detection in frame.visual_detections:
        owner = str(detection.camera_id).split(":", 1)[0]
        resource_id = vehicle_to_resource.get(owner)
        if resource_id is None:
            continue
        detections.setdefault(resource_id, set()).add(str(detection.object_id))
    return detections


def _assigned_detection(frame: AirSimFrame, pair: InterceptPair) -> Any | None:
    if pair.terminal_association is None:
        return None
    local_track_id = _optional_record_string(pair.terminal_association, "local_track_id")
    if not local_track_id:
        return None
    for detection in frame.visual_detections:
        if str(getattr(detection, "local_track_id", "")) == local_track_id:
            return detection
    association_metadata = dict(
        _record_value(pair.terminal_association, "metadata", {}) or {}
    )
    if str(association_metadata.get("source", "")).startswith("main_simulated_d5_"):
        vehicle_to_resource = {
            str(resource.metadata.get("airsim_vehicle_name")): resource.resource_id
            for resource in frame.resources
            if resource.metadata.get("airsim_vehicle_name")
        }
        candidates = [
            detection
            for detection in frame.visual_detections
            if vehicle_to_resource.get(str(detection.camera_id).split(":", 1)[0])
            == pair.resource_id
        ]
        if candidates:
            return max(
                candidates,
                key=lambda item: float(getattr(item, "confidence", 0.0)),
            )
    return None


def _apply_online_control_evidence(
    pairs: list[InterceptPair],
    evidence_by_resource: dict[str, dict[str, Any]],
) -> None:
    for pair in pairs:
        evidence = evidence_by_resource.get(pair.resource_id)
        if evidence is None:
            continue
        binding = evidence.get("binding")
        if binding is not None:
            pair.guidance_binding = coerce_assignment_guidance_binding(binding)
            pair.assigned_global_track_id = pair.guidance_binding.assigned_global_track_id
        pair.d4_permission = evidence.get("d4_permission")
        pair.terminal_association = evidence.get("terminal_association")
        pair.online_truth_id_used = bool(evidence.get("online_truth_id_used", False))


def _binding_for_pair(
    frame: AirSimFrame,
    resource: Any,
    target: Any,
    vehicle_name: str,
) -> AssignmentGuidanceBinding:
    explicit = _matching_metadata_record(
        frame.metadata.get("assignment_guidance_bindings"),
        resource_id=str(resource.resource_id),
        target_id=str(target.object_id),
    )
    if explicit is not None:
        return AssignmentGuidanceBinding(
            plan_id=str(_record_value(explicit, "plan_id", "airsim_control_plan")),
            plan_version=int(_record_value(explicit, "plan_version", 1)),
            assignment_id=_optional_record_string(explicit, "assignment_id"),
            resource_id=str(_record_value(explicit, "resource_id", resource.resource_id)),
            vehicle_name=str(_record_value(explicit, "vehicle_name", vehicle_name)),
            assigned_global_track_id=str(
                _record_value(explicit, "assigned_global_track_id", target.object_id)
            ),
            track_version=int(_record_value(explicit, "track_version", 1)),
            authorization_state=str(_record_value(explicit, "authorization_state", "recorded")),
            owner_node_id=(
                _optional_record_string(explicit, "owner_node_id")
                or _optional_record_string(explicit, "source_node_id")
                or _optional_record_string(explicit, "issuing_node_id")
            ),
            assignment_validity_state=str(
                _record_value(explicit, "assignment_validity_state", "current")
            ),
            created_at_s=float(_record_value(explicit, "created_at_s", frame.timestamp)),
            expires_at_s=_optional_record_float(explicit, "expires_at_s"),
            target_actor_name=_optional_record_string(explicit, "target_actor_name"),
            target_object_id=_optional_record_string(explicit, "target_object_id"),
            target_mesh_aliases=_mesh_aliases_from_record(explicit),
            metadata=dict(_record_value(explicit, "metadata", {}) or {}),
        )

    target_metadata = getattr(target, "metadata", {}) or {}
    actor_name = str(target_metadata.get("airsim_actor_name") or "")
    aliases = tuple(
        item
        for item in (
            actor_name,
            str(target.object_id),
            *tuple(str(value) for value in target_metadata.get("mesh_aliases", ()) or ()),
        )
        if item
    )
    return AssignmentGuidanceBinding(
        plan_id=str(frame.metadata.get("plan_id", "airsim_control_plan")),
        plan_version=int(frame.metadata.get("plan_version", 1)),
        assignment_id=f"{resource.resource_id}:{target.object_id}",
        resource_id=str(resource.resource_id),
        vehicle_name=vehicle_name,
        assigned_global_track_id=str(target.object_id),
        track_version=int(frame.metadata.get("track_version", 1)),
        authorization_state=str(frame.metadata.get("authorization_state", "recorded")),
        assignment_validity_state=str(frame.metadata.get("assignment_validity_state", "current")),
        created_at_s=float(frame.metadata.get("plan_created_at_s", frame.timestamp)),
        target_actor_name=actor_name or None,
        target_object_id=str(target.object_id),
        target_mesh_aliases=aliases,
        metadata={"source": "airsim_control_simulated_binding"},
    )


def _annotate_active_replan_frame(
    config: BlocksSmokeConfig,
    frame: AirSimFrame,
) -> AirSimFrame:
    if _active_center_replan_enabled(config):
        return _annotate_active_center_replan_frame(config, frame)
    return _annotate_active_secondary_visual_png_frame(config, frame)


def _annotate_active_center_replan_frame(
    config: BlocksSmokeConfig,
    frame: AirSimFrame,
) -> AirSimFrame:
    truth_targets = sorted(
        (target for target in frame.truth_objects if target.object_type == "target"),
        key=lambda item: item.object_id,
    )
    resources = sorted(frame.resources, key=lambda item: item.resource_id)
    if not truth_targets or not resources:
        return frame

    active_time = float(config.metadata.get("active_degradation_time_s", 1.5))
    center_replan_time = float(config.metadata.get("center_replan_time_s", 2.0))
    center_node_id = str(config.metadata.get("center_node_id", "C2"))
    if frame.timestamp < active_time:
        phase = "center_initial"
        plan_id = "center_plan_v1"
        plan_version = 1
        d4_action = "continue_center"
        d4_reason = "center_plan_initial"
        d4_terminal_consistent = True
        terminal_locked = False
    elif frame.timestamp < center_replan_time:
        phase = "center_replan_pending"
        plan_id = "center_plan_v1"
        plan_version = 1
        d4_action = "request_center_replan"
        d4_reason = "center_resolution_delay_high_dynamic_active_degradation"
        d4_terminal_consistent = False
        terminal_locked = False
    else:
        phase = "center_replan_v2"
        plan_id = "center_plan_v2"
        plan_version = 2
        d4_action = "continue_center"
        d4_reason = "center_plan_v2_active"
        d4_terminal_consistent = True
        terminal_locked = True

    targets_by_id = {target.object_id: target for target in truth_targets}
    initial_assignments = {
        resource.resource_id: truth_targets[index % len(truth_targets)].object_id
        for index, resource in enumerate(resources)
    }
    replan_assignments = _center_replan_assignments(resources, truth_targets)
    assignments = replan_assignments if phase == "center_replan_v2" else initial_assignments
    bindings: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    terminal_associations: list[dict[str, Any]] = []
    for resource_index, resource in enumerate(resources):
        target_id = assignments[resource.resource_id]
        target = targets_by_id[target_id]
        vehicle_name = str(resource.metadata.get("airsim_vehicle_name") or resource.resource_id)
        actor_name = str(target.metadata.get("airsim_actor_name") or target.object_id)
        assignment_id = f"{resource.resource_id}:{target_id}:v{plan_version}"
        bindings.append(
            {
                "plan_id": plan_id,
                "plan_version": plan_version,
                "assignment_id": assignment_id,
                "resource_id": resource.resource_id,
                "vehicle_name": vehicle_name,
                "assigned_global_track_id": target_id,
                "target_id": target_id,
                "target_object_id": target_id,
                "owner_node_id": center_node_id,
                "source_node_id": center_node_id,
                "track_version": plan_version,
                "authorization_state": "recorded",
                "assignment_validity_state": "current",
                "created_at_s": frame.timestamp,
                "target_actor_name": actor_name,
                "target_mesh_aliases": (actor_name, target_id),
                "metadata": {
                    "source": "main_active_center_replan_visual_png",
                    "plan_schema": "center_plan_v2"
                    if phase == "center_replan_v2"
                    else "assignment_plan_v1",
                    "assignment_phase": phase,
                    "allow_local_rebind": False,
                    "issuing_node_id": center_node_id,
                },
            }
        )
        permissions.append(
            {
                "resource_id": resource.resource_id,
                "assigned_global_track_id": target_id,
                "target_id": target_id,
                "action": d4_action,
                "mode": "active_degradation" if phase != "center_initial" else "none",
                "reason": d4_reason,
                "target_node_id": center_node_id,
                "terminal_consistent": d4_terminal_consistent,
                "requires_human_review": False,
                "new_plan_id": "center_plan_v2" if phase == "center_replan_v2" else None,
                "new_plan_version": 2 if phase == "center_replan_v2" else None,
                "metadata": {
                    "assignment_phase": phase,
                    "center_replan_active": phase == "center_replan_v2",
                    "d4_reassign_pending": phase == "center_replan_pending",
                    "trigger_reason": "center_resolution_delay_high_dynamic_replan",
                },
            }
        )
        terminal_associations.append(
            {
                "resource_id": resource.resource_id,
                "assigned_global_track_id": target_id,
                "target_id": target_id,
                "local_track_id": f"{vehicle_name}:0:det:{resource_index + 1:04d}",
                "association_confidence": 0.93 if terminal_locked else 0.45,
                "ambiguity_score": 0.04 if terminal_locked else 0.70,
                "friend_conflict_state": "none",
                "decision_state": "locked" if terminal_locked else "ambiguous",
                "assignment_version": plan_version,
                "reason": "center_plan_v2_consistent_visual_lock"
                if terminal_locked
                else "awaiting_center_replan",
                "metadata": {
                    "source": "main_simulated_d5_terminal_association",
                    "assignment_phase": phase,
                    "global_track_id_mutated": False,
                },
            }
        )

    metadata = {
        **frame.metadata,
        "plan_id": plan_id,
        "plan_version": plan_version,
        "track_version": plan_version,
        "assignment_phase": phase,
        "active_center_replan_visual_png": {
            "enabled": True,
            "phase": phase,
            "active_degradation_time_s": active_time,
            "center_replan_time_s": center_replan_time,
            "center_node_id": center_node_id,
            "center_plan_v1": "center_plan_v1",
            "center_plan_v2": "center_plan_v2",
        },
        "assignment_guidance_bindings": bindings,
        "d4_guidance_permissions": permissions,
        "terminal_associations": terminal_associations,
    }
    return replace(frame, metadata=metadata)


def _center_replan_assignments(resources: list[Any], truth_targets: list[Any]) -> dict[str, str]:
    # This center-node active-degradation gate validates plan versioning and
    # D4/D5/D7 contracts. It intentionally keeps the same resource-target
    # binding so the current camera can still see the assigned target.
    return {
        resource.resource_id: truth_targets[index % len(truth_targets)].object_id
        for index, resource in enumerate(resources)
    }


def _annotate_active_secondary_visual_png_frame(
    config: BlocksSmokeConfig,
    frame: AirSimFrame,
) -> AirSimFrame:
    if not _active_secondary_visual_png_enabled(config):
        return frame
    truth_targets = sorted(
        (target for target in frame.truth_objects if target.object_type == "target"),
        key=lambda item: item.object_id,
    )
    resources = sorted(frame.resources, key=lambda item: item.resource_id)
    if len(truth_targets) < 2 or len(resources) < 2:
        return frame

    active_time = float(config.metadata.get("active_degradation_time_s", 1.5))
    secondary_time = float(config.metadata.get("secondary_plan_time_s", 2.0))
    secondary_node_id = str(config.metadata.get("secondary_node_id", "SEC-01"))
    if frame.timestamp < active_time:
        phase = "center_initial"
        plan_id = "center_plan_v1"
        plan_version = 1
        d4_action = "continue_center"
        d4_mode = "none"
        d4_reason = "center_plan_initial"
        d4_terminal_consistent = True
        terminal_locked = False
    elif frame.timestamp < secondary_time:
        phase = "secondary_reassignment_pending"
        plan_id = "center_plan_v1"
        plan_version = 1
        d4_action = "degrade_to_secondary"
        d4_mode = "active_degradation"
        d4_reason = "center_plan_stale_high_dynamic_active_degradation"
        d4_terminal_consistent = False
        terminal_locked = False
    else:
        phase = "secondary_reassignment"
        plan_id = "secondary_plan_v2"
        plan_version = 2
        d4_action = "request_secondary_assist"
        d4_mode = "active_degradation"
        d4_reason = "secondary_plan_active"
        d4_terminal_consistent = True
        terminal_locked = True

    center_assignments = {
        resources[0].resource_id: truth_targets[1].object_id,
        resources[1].resource_id: truth_targets[0].object_id,
    }
    secondary_assignments = {
        resources[0].resource_id: truth_targets[0].object_id,
        resources[1].resource_id: truth_targets[1].object_id,
    }
    assignments = secondary_assignments if phase == "secondary_reassignment" else center_assignments
    targets_by_id = {target.object_id: target for target in truth_targets}
    bindings: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    terminal_associations: list[dict[str, Any]] = []
    for resource_index, resource in enumerate(resources[:2]):
        target_id = assignments[resource.resource_id]
        target = targets_by_id[target_id]
        vehicle_name = str(resource.metadata.get("airsim_vehicle_name") or resource.resource_id)
        actor_name = str(target.metadata.get("airsim_actor_name") or target.object_id)
        assignment_id = f"{resource.resource_id}:{target_id}:v{plan_version}"
        owner_node_id = secondary_node_id if phase == "secondary_reassignment" else "C2"
        bindings.append(
            {
                "plan_id": plan_id,
                "plan_version": plan_version,
                "assignment_id": assignment_id,
                "resource_id": resource.resource_id,
                "vehicle_name": vehicle_name,
                "assigned_global_track_id": target_id,
                "target_id": target_id,
                "target_object_id": target_id,
                "owner_node_id": owner_node_id,
                "source_node_id": owner_node_id,
                "track_version": plan_version,
                "authorization_state": "recorded",
                "assignment_validity_state": "current",
                "created_at_s": frame.timestamp,
                "target_actor_name": actor_name,
                "target_mesh_aliases": (actor_name, target_id),
                "metadata": {
                    "source": "main_active_secondary_visual_png",
                    "plan_schema": "secondary_plan_v2"
                    if phase == "secondary_reassignment"
                    else "assignment_plan_v1",
                    "assignment_phase": phase,
                    "allow_local_rebind": False,
                    "issuing_node_id": owner_node_id,
                },
            }
        )
        permissions.append(
            {
                "resource_id": resource.resource_id,
                "assigned_global_track_id": target_id,
                "target_id": target_id,
                "action": d4_action,
                "mode": d4_mode,
                "reason": d4_reason,
                "target_node_id": secondary_node_id
                if d4_action in {"degrade_to_secondary", "request_secondary_assist"}
                else None,
                "terminal_consistent": d4_terminal_consistent,
                "requires_human_review": False,
                "new_plan_id": "secondary_plan_v2"
                if phase == "secondary_reassignment"
                else None,
                "new_plan_version": 2 if phase == "secondary_reassignment" else None,
                "metadata": {
                    "assignment_phase": phase,
                    "secondary_reassignment": phase == "secondary_reassignment",
                    "d4_reassign_pending": phase == "secondary_reassignment_pending",
                    "trigger_reason": "center_resolution_delay_high_dynamic_replan",
                },
            }
        )
        terminal_associations.append(
            {
                "resource_id": resource.resource_id,
                "assigned_global_track_id": target_id,
                "target_id": target_id,
                "local_track_id": f"{vehicle_name}:0:det:{resource_index + 1:04d}",
                "association_confidence": 0.92 if terminal_locked else 0.45,
                "ambiguity_score": 0.05 if terminal_locked else 0.70,
                "friend_conflict_state": "none",
                "decision_state": "locked" if terminal_locked else "ambiguous",
                "assignment_version": plan_version,
                "reason": "secondary_plan_consistent_visual_lock"
                if terminal_locked
                else "awaiting_secondary_reassignment",
                "metadata": {
                    "source": "main_simulated_d5_terminal_association",
                    "assignment_phase": phase,
                    "global_track_id_mutated": False,
                },
            }
        )

    metadata = {
        **frame.metadata,
        "plan_id": plan_id,
        "plan_version": plan_version,
        "track_version": plan_version,
        "assignment_phase": phase,
        "active_secondary_visual_png": {
            "enabled": True,
            "phase": phase,
            "active_degradation_time_s": active_time,
            "secondary_plan_time_s": secondary_time,
            "secondary_node_id": secondary_node_id,
            "center_plan_id": "center_plan_v1",
            "secondary_plan_id": "secondary_plan_v2",
        },
        "assignment_guidance_bindings": bindings,
        "d4_guidance_permissions": permissions,
        "terminal_associations": terminal_associations,
    }
    return replace(frame, metadata=metadata)


def _active_secondary_visual_png_enabled(config: BlocksSmokeConfig) -> bool:
    return bool(config.metadata.get("active_secondary_visual_png"))


def _active_center_replan_enabled(config: BlocksSmokeConfig) -> bool:
    return bool(config.metadata.get("active_center_replan_visual_png"))


def _d4_permission_for_pair(frame: AirSimFrame, pair: InterceptPair | None) -> D4GuidancePermission:
    target_id = "" if pair is None else (pair.assigned_global_track_id or pair.target_id)
    resource_id = "" if pair is None else pair.resource_id
    explicit = _matching_metadata_record(
        frame.metadata.get("d4_guidance_permissions"),
        resource_id=resource_id,
        target_id=target_id,
    )
    if explicit is None:
        explicit = frame.metadata.get("d4_guidance_permission")
    if explicit is None:
        if pair is not None and pair.d4_permission is not None:
            return pair.d4_permission
        return D4GuidancePermission()
    return D4GuidancePermission(
        action=str(_record_value(explicit, "action", "continue_center")),
        mode=str(_record_value(explicit, "mode", "none")),
        reason=str(_record_value(explicit, "reason", "")),
        target_node_id=_optional_record_string(explicit, "target_node_id"),
        terminal_consistent=bool(_record_value(explicit, "terminal_consistent", True)),
        requires_human_review=bool(_record_value(explicit, "requires_human_review", False)),
        new_plan_id=_optional_record_string(explicit, "new_plan_id"),
        new_plan_version=_optional_record_int(explicit, "new_plan_version"),
        metadata=dict(_record_value(explicit, "metadata", {}) or {}),
    )


def _terminal_association_for_pair(
    frame: AirSimFrame,
    pair: InterceptPair,
    visible_detection: Any | None,
) -> Any | None:
    explicit = _matching_metadata_record(
        frame.metadata.get("terminal_associations"),
        resource_id=pair.resource_id,
        target_id=pair.assigned_global_track_id or pair.target_id,
    )
    if explicit is not None:
        return explicit
    return pair.terminal_association


def _matching_metadata_record(
    records: Any,
    *,
    resource_id: str,
    target_id: str,
) -> Any | None:
    if records is None:
        return None
    if isinstance(records, dict):
        for key in (
            f"{resource_id}:{target_id}",
            f"{target_id}:{resource_id}",
            resource_id,
            target_id,
        ):
            if key in records:
                return records[key]
        if _record_matches(records, resource_id, target_id):
            return records
        return None
    try:
        iterable = tuple(records)
    except TypeError:
        return records if _record_matches(records, resource_id, target_id) else None
    for record in iterable:
        if _record_matches(record, resource_id, target_id):
            return record
    return None


def _record_matches(record: Any, resource_id: str, target_id: str) -> bool:
    record_resource = _optional_record_string(record, "resource_id")
    record_target = (
        _optional_record_string(record, "assigned_global_track_id")
        or _optional_record_string(record, "target_id")
        or _optional_record_string(record, "global_track_id")
    )
    resource_ok = not resource_id or record_resource in {None, resource_id}
    target_aliases = {target_id, f"G-{target_id}"}
    if target_id.startswith("G-"):
        target_aliases.add(target_id.removeprefix("G-"))
    target_ok = not target_id or record_target is None or record_target in target_aliases
    return resource_ok and target_ok


def _record_value(record: Any, name: str, default: Any) -> Any:
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _optional_record_string(record: Any, name: str) -> str | None:
    value = _record_value(record, name, None)
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_record_int(record: Any, name: str) -> int | None:
    value = _record_value(record, name, None)
    if value is None:
        return None
    return int(value)


def _optional_record_float(record: Any, name: str) -> float | None:
    value = _record_value(record, name, None)
    if value is None:
        return None
    return float(value)


def _mesh_aliases_from_record(record: Any) -> tuple[str, ...]:
    aliases = _record_value(record, "target_mesh_aliases", ())
    if isinstance(aliases, str):
        return (aliases,) if aliases else ()
    try:
        return tuple(str(item) for item in aliases if str(item))
    except TypeError:
        return (str(aliases),)


def _is_assigned_target_collision(collision: dict[str, Any], target: Any) -> bool:
    if not bool(collision.get("has_collided", False)):
        return False
    object_name = str(collision.get("object_name") or "")
    actor_name = str(getattr(target, "metadata", {}).get("airsim_actor_name") or "")
    if actor_name and actor_name in object_name:
        return True
    return bool(object_name and str(target.object_id) in object_name)


def _abort_pair(runtime: Any, pair: InterceptPair, reason: str) -> None:
    pair.status = "aborted"
    pair.abort_reason = reason
    pair.active = False
    runtime.hover_interceptor(pair.vehicle_name)


def _terminal_delivery_requires_abort(pair: InterceptPair) -> bool:
    return bool(
        pair.terminal_delivery_state == TerminalDeliveryState.EXPIRED.value
        and pair.terminal_delivery_reason == "terminal_visual_lost_after_coast"
    )


def _terminal_detection_acquisition_timed_out(
    pair: InterceptPair,
    *,
    timestamp_s: float,
    in_terminal_range: bool,
    detection_seen: bool,
    timeout_s: float,
) -> bool:
    if detection_seen or not in_terminal_range or pair.terminal_locked:
        pair.terminal_acquisition_started_s = None
        return False
    if pair.terminal_acquisition_started_s is None:
        pair.terminal_acquisition_started_s = float(timestamp_s)
        return False
    return float(timestamp_s) - pair.terminal_acquisition_started_s > float(timeout_s)


def _apply_intercept_detection_dropout(
    config: BlocksSmokeConfig,
    frame: AirSimFrame,
) -> AirSimFrame:
    start = config.intercept_detection_dropout_start_s
    end = config.intercept_detection_dropout_end_s
    active = bool(
        start is not None
        and end is not None
        and float(start) <= float(frame.timestamp) < float(end)
    )
    if not active:
        return frame
    return replace(
        frame,
        visual_detections=(),
        metadata={
            **frame.metadata,
            "intercept_detection_dropout": {
                "active": True,
                "start_s": float(start),
                "end_s": float(end),
                "suppressed_detection_count": len(frame.visual_detections),
                "scope": "online_visual_detections_before_d5_d7",
            },
        },
    )


def _record_command(
    config: BlocksSmokeConfig,
    timestamp: float,
    pair: InterceptPair,
    range_m: float,
    velocity_command: tuple[float, float, float],
    pn_command: Any | None,
    detection_seen: bool,
    collision: dict[str, Any],
    command_records: list[InterceptCommandRecord],
) -> None:
    collision_seen = _recorded_collision_seen(collision)
    command_mode = _command_mode(pn_command, pair)
    mode_switched = bool(
        pair.last_recorded_mode is not None and pair.last_recorded_mode != command_mode
    )
    pair.last_recorded_mode = command_mode
    command_records.append(
        InterceptCommandRecord(
            timestamp_s=float(timestamp),
            resource_id=pair.resource_id,
            vehicle_name=pair.vehicle_name,
            target_id=pair.target_id,
            mode=command_mode,
            range_m=float(range_m),
            command_vx_mps=float(velocity_command[0]),
            command_vy_mps=float(velocity_command[1]),
            command_z_ned_m=float(config.intercept_altitude_ned_z),
            los_rate_radps=float(getattr(pn_command, "los_rate_radps", 0.0) if pn_command is not None else 0.0),
            closing_speed_mps=float(getattr(pn_command, "closing_speed_mps", 0.0) if pn_command is not None else 0.0),
            terminal_locked=bool(pair.terminal_locked),
            terminal_handover_pending=bool(pair.terminal_handover_pending),
            plan_id=str(_command_metadata(pn_command, "plan_id", _pair_plan_id(pair))),
            plan_version=int(_command_metadata(pn_command, "plan_version", _pair_plan_version(pair)) or 0),
            track_version=int(_command_metadata(pn_command, "track_version", _pair_track_version(pair)) or 0),
            d4_action=str(_command_metadata(pn_command, "d4_action", _pair_d4_action(pair))),
            d4_mode=_pair_d4_mode(pair),
            d4_target_node_id=_pair_d4_target_node_id(pair),
            assignment_phase=_pair_assignment_phase(pair),
            d5_decision_state=str(_command_metadata(pn_command, "d5_decision_state", _pair_d5_state(pair))),
            terminal_contract_reject_reason=str(
                _command_metadata(
                    pn_command,
                    "terminal_contract_reject_reason",
                    pair.terminal_contract_reject_reason,
                )
            ),
            terminal_contract_allowed=bool(
                _command_metadata(pn_command, "terminal_contract_allowed", False)
            ),
            terminal_control_allowed=bool(
                _command_metadata(pn_command, "terminal_switch_allowed", False)
            ),
            mode_switched=mode_switched,
            physical_intercept=pair.status in {"collision_intercept", "range_intercept"},
            detection_seen=bool(detection_seen),
            guidance_law=str(_command_metadata(pn_command, "guidance_law", "radar_pn" if not pair.terminal_locked else "los")),
            camera_quality_gate_passed=bool(_command_metadata(pn_command, "camera_quality_gate_passed", False)),
            los_quality_gate_passed=bool(_command_metadata(pn_command, "los_quality_gate_passed", False)),
            maneuver_margin_gate_passed=bool(_command_metadata(pn_command, "maneuver_margin_gate_passed", False)),
            terminal_switch_allowed=bool(_command_metadata(pn_command, "terminal_switch_allowed", pair.terminal_locked)),
            terminal_switch_reject_reason=str(_command_metadata(pn_command, "terminal_switch_reject_reason", pair.terminal_switch_reject_reason)),
            terminal_delivery_state=str(
                _command_metadata(
                    pn_command,
                    "terminal_delivery_state",
                    pair.terminal_delivery_state,
                )
            ),
            terminal_delivery_reason=str(
                _command_metadata(
                    pn_command,
                    "terminal_delivery_reason",
                    pair.terminal_delivery_reason,
                )
            ),
            terminal_using_extrapolation=bool(
                _command_metadata(pn_command, "terminal_using_extrapolation", False)
            ),
            terminal_prediction_age_s=_optional_float(
                _command_metadata(pn_command, "terminal_prediction_age_s", None)
            ),
            terminal_blind_elapsed_s=float(
                _command_metadata(pn_command, "terminal_blind_elapsed_s", 0.0) or 0.0
            ),
            terminal_blind_decay=float(
                _command_metadata(pn_command, "terminal_blind_decay", 0.0) or 0.0
            ),
            local_track_id=str(
                _command_metadata(
                    pn_command,
                    "local_track_id",
                    _optional_record_string(pair.terminal_association, "local_track_id") or "",
                )
                or ""
            ),
            terminal_filter_state=str(
                _command_metadata(pn_command, "terminal_filter_state", "") or ""
            ),
            terminal_filter_reason=str(
                _command_metadata(pn_command, "terminal_filter_reason", "") or ""
            ),
            terminal_filter_innovation_rejected=bool(
                _command_metadata(
                    pn_command,
                    "terminal_filter_innovation_rejected",
                    False,
                )
            ),
            terminal_filter_reset=bool(
                _command_metadata(pn_command, "terminal_filter_reset", False)
            ),
            terminal_filter_reset_reason=str(
                _command_metadata(pn_command, "terminal_filter_reset_reason", "") or ""
            ),
            terminal_image_innovation_norm_rad=_optional_float(
                _command_metadata(
                    pn_command,
                    "terminal_image_innovation_norm_rad",
                    None,
                )
            ),
            terminal_trend_coast_applied=bool(
                _command_metadata(pn_command, "terminal_trend_coast_applied", False)
            ),
            ttc_raw_area_px2=_optional_float(
                _command_metadata(pn_command, "ttc_raw_area_px2", None)
            ),
            ttc_filtered_area_px2=_optional_float(
                _command_metadata(pn_command, "ttc_filtered_area_px2", None)
            ),
            ttc_area_dot_px2_s=_optional_float(
                _command_metadata(pn_command, "ttc_area_dot_px2_s", None)
            ),
            ttc_reject_reason=str(
                _command_metadata(pn_command, "ttc_reject_reason", "") or ""
            ),
            terminal_delivery_profile=str(
                _command_metadata(
                    pn_command,
                    "terminal_delivery_profile",
                    _terminal_delivery_profile(config),
                )
            ),
            visual_reacquisition=str(
                _command_metadata(pn_command, "terminal_delivery_state", "")
            )
            == TerminalDeliveryState.REACQUIRED.value,
            terminal_visual_lost_after_coast=str(
                _command_metadata(pn_command, "terminal_delivery_reason", "")
            )
            == "terminal_visual_lost_after_coast",
            truth_identity_online_use=bool(
                _command_metadata(
                    pn_command,
                    "online_truth_id_used",
                    pair.online_truth_id_used,
                )
            ),
            bbox_area_ratio=float(_command_metadata(pn_command, "bbox_area_ratio", 0.0) or 0.0),
            los_rate_variance_radps2=float(_command_metadata(pn_command, "los_rate_variance_radps2", 0.0) or 0.0),
            ttc_s=_optional_float(_command_metadata(pn_command, "ttc_s", None)),
            maneuver_margin=float(_command_metadata(pn_command, "maneuver_margin", 0.0) or 0.0),
            midcourse_guidance_selection=str(
                _command_metadata(pn_command, "midcourse_guidance_selection", "")
            ),
            midcourse_selection_reason=str(
                _command_metadata(pn_command, "midcourse_selection_reason", "")
            ),
            midcourse_reacquisition_active=bool(
                _command_metadata(pn_command, "midcourse_reacquisition_active", False)
            ),
            midcourse_overshoot_detected=bool(
                _command_metadata(pn_command, "midcourse_overshoot_detected", False)
            ),
            midcourse_minimum_range_m=_optional_float(
                _command_metadata(pn_command, "midcourse_minimum_range_m", None)
            ),
            control_saturated=bool(_command_metadata(pn_command, "control_saturated", getattr(pn_command, "is_saturated", False) if pn_command is not None else False)),
            collision_seen=bool(collision_seen),
            collision_object_name=str(collision.get("object_name") or ""),
            status=pair.status,
            abort_reason=pair.abort_reason,
        )
    )


def _recorded_collision_seen(collision: dict[str, Any]) -> bool:
    return bool(collision.get("target_collision_seen", False))


def _command_metadata(command: Any | None, key: str, default: Any) -> Any:
    if command is None:
        return default
    metadata = getattr(command, "metadata", {}) or {}
    return metadata.get(key, default)


def _pair_plan_id(pair: InterceptPair) -> str:
    if pair.guidance_binding is None:
        return ""
    return pair.guidance_binding.plan_id


def _pair_plan_version(pair: InterceptPair) -> int:
    if pair.guidance_binding is None:
        return 0
    return int(pair.guidance_binding.plan_version)


def _pair_track_version(pair: InterceptPair) -> int:
    if pair.guidance_binding is None:
        return 0
    return int(pair.guidance_binding.track_version)


def _pair_d4_action(pair: InterceptPair) -> str:
    if pair.d4_permission is None:
        return ""
    return pair.d4_permission.action


def _pair_d5_state(pair: InterceptPair) -> str:
    if pair.terminal_association is None:
        return ""
    return str(_record_value(pair.terminal_association, "decision_state", ""))


def _command_mode(command: Any | None, pair: InterceptPair) -> str:
    if command is None:
        return "vision_terminal" if pair.terminal_locked else "radar_midcourse"
    mode = _command_metadata(command, "mode_override", None)
    if mode is not None:
        return str(mode)
    return str(command.mode.value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _control_timestamps(config: BlocksSmokeConfig) -> list[float]:
    step_count = int(math.ceil(config.intercept_max_duration_s / config.control_dt_s))
    return [round(index * config.control_dt_s, 6) for index in range(step_count + 1)]


def _write_intercept_outputs(
    config: BlocksSmokeConfig,
    output_dir: Path,
    frames: list[AirSimFrame],
    pairs: list[InterceptPair],
    command_records: list[InterceptCommandRecord],
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    commands_path = output_dir / "control_commands.csv"
    with commands_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(command_records[0]).keys()) if command_records else ["timestamp_s"])
        writer.writeheader()
        for record in command_records:
            writer.writerow(asdict(record))
    paths["control_commands"] = commands_path

    success_semantics = _intercept_success_semantics(config, pairs)
    summary = {
        "control_api_used": True,
        "runtime_mode": "SimpleFlight",
        "physical_intercept_available": True,
        "physical_intercept_unavailable_reason": "",
        "success_count": sum(1 for pair in pairs if pair.status in {"collision_intercept", "range_intercept"}),
        "pair_count": len(pairs),
        "success_semantics": success_semantics,
        **{
            key: value
            for key, value in success_semantics.items()
            if key.endswith("_count")
        },
        "parameters": {
            "guidance_law": config.intercept_guidance_law,
            "control_dt_s": config.control_dt_s,
            "intercept_speed_mps": config.intercept_speed_mps,
            "intercept_altitude_ned_z": config.intercept_altitude_ned_z,
            "intercept_radius_m": config.intercept_radius_m,
            "intercept_distance_frame": "NED",
            "intercept_distance_dimension": "3d_euclidean",
            "intercept_success_criteria_version": "airsim-range-intercept-v2",
            "intercept_max_duration_s": config.intercept_max_duration_s,
            "terminal_switch_range_m": config.intercept_terminal_switch_range_m,
            "detection_timeout_s": config.intercept_detection_timeout_s,
            "detection_dropout_start_s": config.intercept_detection_dropout_start_s,
            "detection_dropout_end_s": config.intercept_detection_dropout_end_s,
            "terminal_delivery_profile": _terminal_delivery_profile(config),
            "terminal_soft_prediction_enabled": (
                config.intercept_terminal_soft_prediction_enabled
            ),
            "terminal_trend_coast_enabled": (
                config.intercept_terminal_trend_coast_enabled
            ),
            "max_turn_rate_radps": config.intercept_max_turn_rate_radps,
            "min_maneuver_margin": config.intercept_min_maneuver_margin,
            "cooperative_demand_enabled": config.cooperative_demand_enabled,
            "cooperative_coordination_mode": config.cooperative_coordination_mode,
            "cooperative_primary_count": config.cooperative_primary_count,
        },
        "pairs": [_pair_summary(pair) for pair in pairs],
        "record_count": len(command_records),
    }
    required_primary_counts: dict[str, int] = {}
    for pair in summary["pairs"]:
        if pair["required_primary"]:
            target_id = str(pair["target_id"])
            required_primary_counts[target_id] = required_primary_counts.get(target_id, 0) + 1
    for pair in summary["pairs"]:
        pair["required_primary_count"] = required_primary_counts.get(str(pair["target_id"]))
        if pair["min_range_m"] == float("inf"):
            pair["min_range_m"] = None
    summary_path = output_dir / "intercept_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    paths["intercept_summary"] = summary_path

    if _active_secondary_visual_png_enabled(config):
        events_path = output_dir / "secondary_reassignment_events.json"
        events_path.write_text(
            json.dumps(
                _secondary_reassignment_events(config, command_records),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        paths["secondary_reassignment_events"] = events_path
    if _active_center_replan_enabled(config):
        events_path = output_dir / "center_replan_events.json"
        events_path.write_text(
            json.dumps(
                _center_replan_events(config, command_records),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        paths["center_replan_events"] = events_path

    plot_path = output_dir / "airsim_3d_intercept_trajectories.png"
    _write_trajectory_plot(frames, plot_path)
    paths["intercept_trajectory_plot"] = plot_path
    return paths


def _intercept_success_semantics(
    config: BlocksSmokeConfig,
    pairs: list[InterceptPair],
) -> dict[str, Any]:
    success_statuses = {"collision_intercept", "range_intercept"}
    participating = [pair for pair in pairs if pair.activation_state == "active"]
    successful = [pair for pair in participating if pair.status in success_statuses]
    target_ids = sorted({pair.target_id for pair in participating})
    successful_target_ids = sorted({pair.target_id for pair in successful})
    coalition_target_ids = sorted(
        {
            pair.target_id
            for pair in participating
            if sum(
                1
                for candidate in participating
                if candidate.target_id == pair.target_id
                and candidate.member_role == "primary"
            )
            > 1
        }
    )
    completed_coalition_target_ids = []
    for target_id in coalition_target_ids:
        required_primaries = [
            pair
            for pair in participating
            if pair.target_id == target_id and pair.member_role == "primary"
        ]
        if required_primaries and all(
            pair.status in success_statuses for pair in required_primaries
        ):
            completed_coalition_target_ids.append(target_id)
    return {
        "criteria_version": "airsim-range-intercept-v2",
        "distance_frame": "NED",
        "distance_dimension": "3d_euclidean",
        "range_threshold_m": float(config.intercept_radius_m),
        "pair_physical_success_count": len(successful),
        "pair_physical_opportunity_count": len(participating),
        "target_intercept_success_count": len(successful_target_ids),
        "target_intercept_opportunity_count": len(target_ids),
        "successful_target_ids": successful_target_ids,
        "coalition_completion_count": len(completed_coalition_target_ids),
        "coalition_opportunity_count": len(coalition_target_ids),
        "completed_coalition_target_ids": completed_coalition_target_ids,
        "standby_reserve_excluded_from_pair_denominator": True,
    }


def _secondary_reassignment_events(
    config: BlocksSmokeConfig,
    command_records: list[InterceptCommandRecord],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "event_type": "active_degradation_config",
            "active_degradation_time_s": float(config.metadata.get("active_degradation_time_s", 1.5)),
            "secondary_plan_time_s": float(config.metadata.get("secondary_plan_time_s", 2.0)),
            "secondary_node_id": str(config.metadata.get("secondary_node_id", "SEC-01")),
        }
    ]
    seen: set[tuple[str, str, str]] = set()
    for record in command_records:
        if record.assignment_phase not in {
            "secondary_reassignment_pending",
            "secondary_reassignment",
        }:
            continue
        key = (record.resource_id, record.target_id, record.assignment_phase)
        if key in seen:
            continue
        seen.add(key)
        events.append(
            {
                "event_type": record.assignment_phase,
                "timestamp_s": record.timestamp_s,
                "resource_id": record.resource_id,
                "target_id": record.target_id,
                "plan_id": record.plan_id,
                "plan_version": record.plan_version,
                "d4_action": record.d4_action,
                "d4_mode": record.d4_mode,
                "target_node_id": record.d4_target_node_id,
                "terminal_contract_reject_reason": record.terminal_contract_reject_reason,
                "guidance_law": record.guidance_law,
            }
        )
    return events


def _center_replan_events(
    config: BlocksSmokeConfig,
    command_records: list[InterceptCommandRecord],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "event_type": "active_center_replan_config",
            "active_degradation_time_s": float(config.metadata.get("active_degradation_time_s", 1.5)),
            "center_replan_time_s": float(config.metadata.get("center_replan_time_s", 2.0)),
            "center_node_id": str(config.metadata.get("center_node_id", "C2")),
        }
    ]
    seen: set[tuple[str, str, str]] = set()
    for record in command_records:
        if record.assignment_phase not in {
            "center_replan_pending",
            "center_replan_v2",
        }:
            continue
        key = (record.resource_id, record.target_id, record.assignment_phase)
        if key in seen:
            continue
        seen.add(key)
        events.append(
            {
                "event_type": record.assignment_phase,
                "timestamp_s": record.timestamp_s,
                "resource_id": record.resource_id,
                "target_id": record.target_id,
                "plan_id": record.plan_id,
                "plan_version": record.plan_version,
                "d4_action": record.d4_action,
                "d4_mode": record.d4_mode,
                "target_node_id": record.d4_target_node_id,
                "terminal_contract_reject_reason": record.terminal_contract_reject_reason,
                "guidance_law": record.guidance_law,
            }
        )
    return events


def _pair_summary(pair: InterceptPair) -> dict[str, Any]:
    binding = pair.guidance_binding
    physical_success = pair.status in {"collision_intercept", "range_intercept"}
    return {
        "resource_id": pair.resource_id,
        "vehicle_name": pair.vehicle_name,
        "target_id": pair.target_id,
        "assigned_global_track_id": pair.assigned_global_track_id,
        "assigned": binding is not None,
        "active": pair.active,
        "status": pair.status,
        "abort_reason": pair.abort_reason,
        "min_range_m": pair.min_range_m,
        "time_to_intercept_s": pair.time_to_intercept_s,
        "last_detection_s": pair.last_detection_s,
        "terminal_locked": pair.terminal_locked,
        "terminal_handover_pending": pair.terminal_handover_pending,
        "terminal_switch_reject_reason": pair.terminal_switch_reject_reason,
        "terminal_contract_reject_reason": pair.terminal_contract_reject_reason,
        "plan_id": _pair_plan_id(pair),
        "plan_version": _pair_plan_version(pair),
        "track_version": _pair_track_version(pair),
        "d4_action": _pair_d4_action(pair),
        "d4_mode": _pair_d4_mode(pair),
        "d4_target_node_id": _pair_d4_target_node_id(pair),
        "assignment_phase": _pair_assignment_phase(pair),
        "d5_decision_state": _pair_d5_state(pair),
        "member_role": pair.member_role,
        "wave_id": pair.wave_id,
        "activation_state": pair.activation_state,
        "required_primary": pair.member_role == "primary" and pair.activation_state == "active",
        "required_primary_count": None,
        "arrival_window": None
        if binding is None
        else [binding.arrival_window_start_s, binding.arrival_window_end_s],
        "arrival_timestamp_s": pair.time_to_intercept_s,
        "physical_success": physical_success,
        "online_truth_id_used": pair.online_truth_id_used,
        "terminal_delivery_state": pair.terminal_delivery_state,
        "terminal_delivery_reason": pair.terminal_delivery_reason,
    }


def _pair_d4_mode(pair: InterceptPair) -> str:
    if pair.d4_permission is None:
        return ""
    return pair.d4_permission.mode


def _pair_d4_target_node_id(pair: InterceptPair) -> str:
    if pair.d4_permission is None or pair.d4_permission.target_node_id is None:
        return ""
    return pair.d4_permission.target_node_id


def _pair_assignment_phase(pair: InterceptPair) -> str:
    if pair.d4_permission is not None:
        phase = pair.d4_permission.metadata.get("assignment_phase")
        if phase:
            return str(phase)
    if pair.guidance_binding is not None:
        phase = pair.guidance_binding.metadata.get("assignment_phase")
        if phase:
            return str(phase)
    return ""


def _normalize_track_id(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text.startswith("G-"):
        return text[2:]
    return text


def _write_trajectory_plot(frames: list[AirSimFrame], path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    series: dict[str, list[tuple[float, float, float]]] = {}
    for frame in frames:
        for target in frame.truth_objects:
            series.setdefault(f"target:{target.object_id}", []).append(_plot_point(target.position_ned))
        for resource in frame.resources:
            series.setdefault(f"resource:{resource.resource_id}", []).append(_plot_point(resource.position_ned))
    if not series:
        return
    points = np.asarray([point for values in series.values() for point in values], dtype=float)
    mins = points.min(axis=0) - 1.0
    maxs = points.max(axis=0) + 1.0
    az = math.radians(-42.0)
    el = math.radians(24.0)

    def project(array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x, y, z = array[:, 0], array[:, 1], array[:, 2]
        x1 = math.cos(az) * x - math.sin(az) * y
        y1 = math.sin(az) * x + math.cos(az) * y
        y2 = math.cos(el) * y1 - math.sin(el) * z
        return x1, y2

    fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
    ax.axis("off")
    ax.set_aspect("equal", adjustable="datalim")
    x0, y0, z0 = mins
    x1, y1, z1 = maxs
    for a, b in [
        ((x0, y0, z0), (x1, y0, z0)),
        ((x0, y1, z0), (x1, y1, z0)),
        ((x0, y0, z1), (x1, y0, z1)),
        ((x0, y1, z1), (x1, y1, z1)),
        ((x0, y0, z0), (x0, y1, z0)),
        ((x1, y0, z0), (x1, y1, z0)),
        ((x0, y0, z0), (x0, y0, z1)),
        ((x1, y1, z0), (x1, y1, z1)),
    ]:
        xs, ys = project(np.asarray([a, b], dtype=float))
        ax.plot(xs, ys, color="#d8dde3", lw=0.8)
    colors = ["#d62728", "#ff7f0e", "#1f77b4", "#2ca02c", "#9467bd", "#8c564b"]
    for index, (name, values) in enumerate(sorted(series.items())):
        array = np.asarray(values, dtype=float)
        xs, ys = project(array)
        marker = "s" if name.startswith("resource:") else "o"
        ax.plot(xs, ys, label=name, color=colors[index % len(colors)], marker=marker, lw=2.2)
        ax.scatter(xs[-1:], ys[-1:], color=colors[index % len(colors)], marker="*", s=80)
    fig.text(0.03, 0.95, "AirSim Controlled Intercept 3D Trajectories", fontsize=16, fontweight="bold")
    fig.text(0.03, 0.04, "Coordinates: North=X_NED, East=Y_NED, Altitude=-Z_NED. Star=end.", fontsize=9)
    ax.legend(loc="upper right", frameon=True, fontsize=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _plot_point(position_ned: tuple[float, float, float]) -> tuple[float, float, float]:
    return (float(position_ned[0]), float(position_ned[1]), -float(position_ned[2]))
