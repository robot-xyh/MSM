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
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
    compute_pn_command,
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
    visual_filter: SimpleFlightPngGuidanceFilter | None = None
    terminal_switch_reject_reason: str = ""
    terminal_contract_reject_reason: str = ""
    guidance_binding: AssignmentGuidanceBinding | None = None
    d4_permission: D4GuidancePermission | None = None
    terminal_association: Any | None = None


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
    detection_seen: bool
    guidance_law: str
    camera_quality_gate_passed: bool
    los_quality_gate_passed: bool
    maneuver_margin_gate_passed: bool
    terminal_switch_allowed: bool
    terminal_switch_reject_reason: str
    bbox_area_ratio: float
    los_rate_variance_radps2: float
    ttc_s: float | None
    maneuver_margin: float
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
    runtime.prepare_interceptor_control(config)
    try:
        for frame_index, timestamp in enumerate(_control_timestamps(config)):
            frame = runtime.sample_frame(config, frame_index, timestamp, output_dir / "images")
            frame = _annotate_active_replan_frame(config, frame)
            frames.append(frame)
            if not pairs:
                pairs = _initial_pairs(frame)
            if not pairs:
                continue
            _refresh_pair_assignments(frame, pairs)
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

        visible_detection = _assigned_detection(frame, pair)
        detection_seen = visible_detection is not None
        if detection_seen:
            pair.last_detection_s = frame.timestamp
        pair.d4_permission = _d4_permission_for_pair(frame, pair)
        pair.terminal_association = _terminal_association_for_pair(frame, pair, visible_detection)
        in_terminal_range = range_m <= config.intercept_terminal_switch_range_m
        if in_terminal_range:
            pair.terminal_handover_pending = True
        if in_terminal_range and not detection_seen:
            last_seen = pair.last_detection_s
            if last_seen is None or frame.timestamp - last_seen > config.intercept_detection_timeout_s:
                _abort_pair(runtime, pair, "terminal_detection_timeout")
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
        )
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
            max_turn_rate_radps=0.9,
        )
        command.metadata["guidance_law"] = "pure_pursuit"
    else:
        command = compute_pn_command(
            pursuer=pursuer_state,
            target=target_state,
            dt_s=config.control_dt_s,
            navigation_constant=config.intercept_navigation_constant,
            mode=mode,
            max_lateral_accel_mps2=20.0,
            max_turn_rate_radps=0.9,
        )
        command.metadata["guidance_law"] = (
            "radar_pn" if not pair.terminal_locked else command.metadata.get("guidance_law", "radar_pn")
        )
    command.metadata["configured_guidance_law"] = configured_law
    predicted_resource_velocity = np.asarray(_midcourse_velocity(config, command), dtype=float)
    if visual_guidance_enabled and pair.terminal_handover_pending and visible_detection is not None:
        if str(config.intercept_yaw_mode).lower() == "look_at_target":
            current_heading = math.atan2(
                float(target_position[1] - resource_position[1]),
                float(target_position[0] - resource_position[0]),
            )
        else:
            current_heading = math.atan2(float(resource_velocity[1]), float(resource_velocity[0]))
        observation = _vision_observation_from_detection(frame_timestamp=timestamp, pair=pair, detection=visible_detection)
        contract = evaluate_terminal_png_contract(
            binding=pair.guidance_binding,
            d4_permission=pair.d4_permission,
            terminal_association=pair.terminal_association,
            observation=observation,
            timestamp_s=timestamp,
            resource_id=pair.resource_id,
        )
        pair.terminal_contract_reject_reason = contract.reject_reason
        if not contract.allowed:
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
                }
            )
            return _midcourse_velocity(config, command), command

        visual_filter = _visual_filter_for_pair(config, pair)
        visual_command = visual_filter.evaluate(
            observation,
            current_heading_rad=current_heading,
            current_speed_mps=max(float(np.linalg.norm(predicted_resource_velocity[:2])), config.intercept_speed_mps),
            intercept_speed_mps=config.intercept_speed_mps,
            relative_position_ned=tuple(float(value) for value in (target_position - resource_position)),
            relative_velocity_ned=tuple(float(value) for value in (target_velocity - predicted_resource_velocity)),
            command_z_ned_m=0.0,
        )
        pair.terminal_switch_reject_reason = visual_command.quality.reject_reason
        if visual_command.quality.terminal_switch_allowed:
            pair.terminal_locked = True
        if pair.terminal_locked:
            command.metadata.update(
                {
                    "terminal_contract_allowed": True,
                    "terminal_contract_reject_reason": "",
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
                "terminal_contract_allowed": True,
                "terminal_contract_reject_reason": "",
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


def _visual_filter_for_pair(
    config: BlocksSmokeConfig,
    pair: InterceptPair,
) -> SimpleFlightPngGuidanceFilter:
    if pair.visual_filter is None:
        pair.visual_filter = SimpleFlightPngGuidanceFilter(
            PngGuidanceConfig(
                dt_s=config.control_dt_s,
                image_width_px=640,
                image_height_px=480,
                focal_length_px=320.0,
                min_bbox_area_ratio=config.intercept_min_bbox_area_ratio,
                min_detection_confidence=config.intercept_min_detection_confidence,
                min_stable_frames=config.intercept_min_stable_detection_frames,
                max_visual_latency_s=config.intercept_max_visual_latency_s,
                navigation_constant=config.intercept_navigation_constant,
                law=config.intercept_guidance_law,  # type: ignore[arg-type]
            )
        )
    return pair.visual_filter


def _vision_observation_from_detection(
    *,
    frame_timestamp: float,
    pair: InterceptPair,
    detection: Any,
) -> VisionGuidanceObservation:
    return VisionGuidanceObservation(
        timestamp_s=float(frame_timestamp),
        frame_timestamp_s=float(getattr(detection, "timestamp", frame_timestamp)),
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
            "visual_latency_s": max(0.0, float(frame_timestamp) - float(getattr(detection, "timestamp", frame_timestamp))),
            "source_node_id": pair.resource_id,
            "payload_kind": "bbox",
        },
    )


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
        "maneuver_margin": visual_command.quality.maneuver_margin,
        "control_saturated": visual_command.control_saturated,
    }


def _initial_pairs(frame: AirSimFrame) -> list[InterceptPair]:
    resources = sorted(frame.resources, key=lambda item: item.resource_id)
    sorted_targets = sorted(
        (target for target in frame.truth_objects if target.object_type == "target"),
        key=lambda item: item.object_id,
    )
    targets = {target.object_id: target for target in sorted_targets}
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
        pair.guidance_binding = _binding_for_pair(frame, resource, target, pair.vehicle_name)


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
    vehicle_to_resource = {
        str(resource.metadata.get("airsim_vehicle_name")): resource.resource_id
        for resource in frame.resources
        if resource.metadata.get("airsim_vehicle_name")
    }
    candidates = []
    for detection in frame.visual_detections:
        owner = str(detection.camera_id).split(":", 1)[0]
        if vehicle_to_resource.get(owner) != pair.resource_id:
            continue
        if str(detection.object_id) != pair.target_id:
            continue
        candidates.append(detection)
    if not candidates:
        return None
    return max(candidates, key=lambda item: float(getattr(item, "confidence", 0.0)))


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
    target_id = "" if pair is None else pair.target_id
    resource_id = "" if pair is None else pair.resource_id
    explicit = _matching_metadata_record(
        frame.metadata.get("d4_guidance_permissions"),
        resource_id=resource_id,
        target_id=target_id,
    )
    if explicit is None:
        explicit = frame.metadata.get("d4_guidance_permission")
    if explicit is None:
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
        target_id=pair.target_id,
    )
    if explicit is not None:
        return explicit
    if visible_detection is None or pair.guidance_binding is None:
        return None
    # Simulation-only adapter: current 2v2 controlled intercept has no D5 bus,
    # so make the D5-shaped evidence explicit before D7 contract validation.
    return {
        "assigned_global_track_id": pair.guidance_binding.assigned_global_track_id,
        "local_track_id": getattr(visible_detection, "local_track_id", None),
        "association_confidence": float(getattr(visible_detection, "confidence", 0.0)),
        "ambiguity_score": 0.0,
        "friend_conflict_state": "none",
        "decision_state": "locked",
        "assignment_version": pair.guidance_binding.track_version,
        "reason": "airsim_assigned_detection_simulated_d5_lock",
    }


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
    command_records.append(
        InterceptCommandRecord(
            timestamp_s=float(timestamp),
            resource_id=pair.resource_id,
            vehicle_name=pair.vehicle_name,
            target_id=pair.target_id,
            mode=_command_mode(pn_command, pair),
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
            detection_seen=bool(detection_seen),
            guidance_law=str(_command_metadata(pn_command, "guidance_law", "radar_pn" if not pair.terminal_locked else "los")),
            camera_quality_gate_passed=bool(_command_metadata(pn_command, "camera_quality_gate_passed", False)),
            los_quality_gate_passed=bool(_command_metadata(pn_command, "los_quality_gate_passed", False)),
            maneuver_margin_gate_passed=bool(_command_metadata(pn_command, "maneuver_margin_gate_passed", False)),
            terminal_switch_allowed=bool(_command_metadata(pn_command, "terminal_switch_allowed", pair.terminal_locked)),
            terminal_switch_reject_reason=str(_command_metadata(pn_command, "terminal_switch_reject_reason", pair.terminal_switch_reject_reason)),
            bbox_area_ratio=float(_command_metadata(pn_command, "bbox_area_ratio", 0.0) or 0.0),
            los_rate_variance_radps2=float(_command_metadata(pn_command, "los_rate_variance_radps2", 0.0) or 0.0),
            ttc_s=_optional_float(_command_metadata(pn_command, "ttc_s", None)),
            maneuver_margin=float(_command_metadata(pn_command, "maneuver_margin", 0.0) or 0.0),
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

    summary = {
        "control_api_used": True,
        "success_count": sum(1 for pair in pairs if pair.status in {"collision_intercept", "range_intercept"}),
        "pair_count": len(pairs),
        "parameters": {
            "guidance_law": config.intercept_guidance_law,
            "control_dt_s": config.control_dt_s,
            "intercept_speed_mps": config.intercept_speed_mps,
            "intercept_altitude_ned_z": config.intercept_altitude_ned_z,
            "intercept_radius_m": config.intercept_radius_m,
            "intercept_max_duration_s": config.intercept_max_duration_s,
            "terminal_switch_range_m": config.intercept_terminal_switch_range_m,
        },
        "pairs": [_pair_summary(pair) for pair in pairs],
        "record_count": len(command_records),
    }
    for pair in summary["pairs"]:
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
    return {
        "resource_id": pair.resource_id,
        "vehicle_name": pair.vehicle_name,
        "target_id": pair.target_id,
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
