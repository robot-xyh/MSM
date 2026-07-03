"""Controlled 2v2 AirSim interception episode for Blocks.

This module is still simulation-only. It commands SimpleFlight vehicles inside
AirSim and uses non-vehicle Unreal actors as targets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from airsim_dryrun.models import AirSimFrame
from d7_proportional_guidance import (
    GuidanceMode,
    GuidanceState,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
    compute_pn_command,
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

    frames: list[AirSimFrame] = []
    command_records: list[InterceptCommandRecord] = []
    pairs: list[InterceptPair] = []
    runtime.prepare_interceptor_control(config)
    try:
        for frame_index, timestamp in enumerate(_control_timestamps(config)):
            frame = runtime.sample_frame(config, frame_index, timestamp, output_dir / "images")
            frames.append(frame)
            if not pairs:
                pairs = _initial_pairs(frame)
            if not pairs:
                continue
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
    mode = GuidanceMode.VISION_TERMINAL if pair.terminal_locked else GuidanceMode.RADAR_MIDCOURSE
    command = compute_pn_command(
        pursuer=GuidanceState(
            entity_id=pair.resource_id,
            timestamp_s=timestamp,
            position_m=(float(resource_position[0]), float(resource_position[1])),
            velocity_mps=(float(resource_velocity[0]), float(resource_velocity[1])),
        ),
        target=GuidanceState(
            entity_id=pair.target_id,
            timestamp_s=timestamp,
            position_m=(float(target_position[0]), float(target_position[1])),
            velocity_mps=(float(target_velocity[0]), float(target_velocity[1])),
            source="airsim_actor_track",
        ),
        dt_s=config.control_dt_s,
        navigation_constant=config.intercept_navigation_constant,
        mode=mode,
        max_lateral_accel_mps2=20.0,
        max_turn_rate_radps=0.9,
    )
    if pair.terminal_handover_pending and visible_detection is not None:
        visual_filter = _visual_filter_for_pair(config, pair)
        current_heading = math.atan2(float(resource_velocity[1]), float(resource_velocity[0]))
        observation = _vision_observation_from_detection(frame_timestamp=timestamp, pair=pair, detection=visible_detection)
        visual_command = visual_filter.evaluate(
            observation,
            current_heading_rad=current_heading,
            current_speed_mps=max(float(np.linalg.norm(resource_velocity[:2])), config.intercept_speed_mps),
            intercept_speed_mps=config.intercept_speed_mps,
            relative_position_ned=tuple(float(value) for value in (target_position - resource_position)),
            relative_velocity_ned=tuple(float(value) for value in (target_velocity - resource_velocity)),
            command_z_ned_m=0.0,
        )
        pair.terminal_switch_reject_reason = visual_command.quality.reject_reason
        if visual_command.quality.terminal_switch_allowed:
            pair.terminal_locked = True
        if pair.terminal_locked:
            command.metadata.update(
                {
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
        command.metadata.update(_visual_metadata(visual_command))

    if pair.terminal_locked:
        heading = math.atan2(
            float(target_position[1] - resource_position[1]),
            float(target_position[0] - resource_position[0]),
        )
    else:
        heading = command.desired_heading_rad
    return (
        (
            float(config.intercept_speed_mps * math.cos(heading)),
            float(config.intercept_speed_mps * math.sin(heading)),
            0.0,
        ),
        command,
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
        assigned_global_track_id=pair.target_id,
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
    targets = sorted(
        (target for target in frame.truth_objects if target.object_type == "target"),
        key=lambda item: item.object_id,
    )
    pairs: list[InterceptPair] = []
    for resource, target in zip(resources, targets, strict=False):
        vehicle_name = str(resource.metadata.get("airsim_vehicle_name") or resource.resource_id)
        pairs.append(
            InterceptPair(
                resource_id=resource.resource_id,
                vehicle_name=vehicle_name,
                target_id=target.object_id,
            )
        )
    return pairs


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

    plot_path = output_dir / "airsim_3d_intercept_trajectories.png"
    _write_trajectory_plot(frames, plot_path)
    paths["intercept_trajectory_plot"] = plot_path
    return paths


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
    }


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
