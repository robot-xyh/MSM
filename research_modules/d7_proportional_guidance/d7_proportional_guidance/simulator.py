"""Offline two-dimensional point-mass PN episode simulation."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .models import GuidanceConfig, GuidanceMode, GuidanceRecord, GuidanceState
from .pn import compute_proportional_navigation_command, compute_pure_pursuit_command


def simulate_guidance_episode(
    pursuer_initial: GuidanceState | None = None,
    target_initial: GuidanceState | None = None,
    config: GuidanceConfig | None = None,
    resource_id: str | None = None,
    target_id: str | None = None,
) -> tuple[list[GuidanceRecord], dict[str, Any]]:
    """Simulate one offline resource-target pair with radar and vision PN.

    This is a deterministic two-dimensional point-mass model unless noise is
    configured. It does not expose flight-control, hardware, communication, or
    authorization interfaces.
    """

    cfg = config or GuidanceConfig()
    pursuer = pursuer_initial or GuidanceState(
        entity_id="R0",
        timestamp_s=0.0,
        position_m=(0.0, 0.0),
        velocity_mps=(180.0, 0.0),
    )
    target = target_initial or GuidanceState(
        entity_id="T0",
        timestamp_s=0.0,
        position_m=(1200.0, 150.0),
        velocity_mps=(-20.0, 0.0),
    )
    resource = resource_id or pursuer.entity_id
    target_name = target_id or target.entity_id
    rng = np.random.default_rng(cfg.random_seed)

    records: list[GuidanceRecord] = []
    previous_mode: GuidanceMode | None = None
    terminal_locked = False
    previous_relative_estimate: np.ndarray | None = None

    step_count = int(math.ceil(cfg.max_duration_s / cfg.dt_s))
    for step_index in range(step_count + 1):
        timestamp_s = step_index * cfg.dt_s
        true_range_m = _range_between(pursuer, target)
        if terminal_locked or _should_use_terminal_mode(timestamp_s, true_range_m, cfg):
            mode = GuidanceMode.VISION_TERMINAL
            terminal_locked = True
        else:
            mode = GuidanceMode.RADAR_MIDCOURSE

        target_estimate, observation, relative_estimate = _estimate_target_state(
            mode=mode,
            pursuer=pursuer,
            target=target,
            cfg=cfg,
            rng=rng,
            previous_relative_estimate=previous_relative_estimate,
        )
        command = _compute_guidance_command(cfg, pursuer, target_estimate, mode)

        records.append(
            GuidanceRecord(
                timestamp_s=timestamp_s,
                resource_id=resource,
                target_id=target_name,
                mode=mode,
                range_m=true_range_m,
                los_angle_rad=command.los_angle_rad,
                los_rate_radps=command.los_rate_radps,
                closing_speed_mps=command.closing_speed_mps,
                commanded_lateral_accel_mps2=command.commanded_lateral_accel_mps2,
                limited_lateral_accel_mps2=command.limited_lateral_accel_mps2,
                limited_turn_rate_radps=command.limited_turn_rate_radps,
                pursuer_position_m=pursuer.position_m,
                pursuer_velocity_mps=pursuer.velocity_mps,
                target_position_m=target.position_m,
                target_velocity_mps=target.velocity_mps,
                target_estimated_position_m=target_estimate.position_m,
                target_estimated_velocity_mps=target_estimate.velocity_mps,
                observation=observation,
                mode_switch=previous_mode is not None and mode != previous_mode,
            )
        )

        previous_mode = mode
        previous_relative_estimate = relative_estimate

        if cfg.stop_at_intercept_radius and true_range_m <= cfg.intercept_radius_m:
            break
        if timestamp_s >= cfg.max_duration_s:
            break

        pursuer = _advance_pursuer(pursuer, command.desired_heading_rad, cfg.dt_s)
        target = _advance_target(target, cfg.dt_s)

    return records, summarize_guidance_records(records, cfg)


def summarize_guidance_records(
    records: list[GuidanceRecord],
    config: GuidanceConfig | None = None,
) -> dict[str, Any]:
    """Summarize an offline guidance episode."""

    if not records:
        return {
            "steps": 0,
            "duration_s": 0.0,
            "terminal_mode_entered": False,
            "boundary": "offline_2d_point_mass_only",
        }

    ranges = np.asarray([record.range_m for record in records], dtype=float)
    min_index = int(np.argmin(ranges))
    modes = []
    for record in records:
        mode_value = record.mode.value
        if mode_value not in modes:
            modes.append(mode_value)

    intercept_radius_m = config.intercept_radius_m if config else None
    stopped_on_radius = False
    if intercept_radius_m is not None:
        stopped_on_radius = bool(records[-1].range_m <= intercept_radius_m)

    return {
        "resource_id": records[0].resource_id,
        "target_id": records[0].target_id,
        "steps": len(records),
        "duration_s": records[-1].timestamp_s,
        "initial_range_m": float(ranges[0]),
        "final_range_m": float(ranges[-1]),
        "min_range_m": float(ranges[min_index]),
        "closest_time_s": records[min_index].timestamp_s,
        "terminal_mode_entered": any(
            record.mode == GuidanceMode.VISION_TERMINAL for record in records
        ),
        "mode_sequence": modes,
        "guidance_law": config.guidance_law if config else "pn",
        "stopped_on_intercept_radius": stopped_on_radius,
        "boundary": "offline_2d_point_mass_only",
    }


def _compute_guidance_command(
    cfg: GuidanceConfig,
    pursuer: GuidanceState,
    target_estimate: GuidanceState,
    mode: GuidanceMode,
):
    if cfg.guidance_law == "pure_pursuit":
        return compute_pure_pursuit_command(
            pursuer=pursuer,
            target=target_estimate,
            dt_s=cfg.dt_s,
            mode=mode,
            max_turn_rate_radps=cfg.max_turn_rate_radps,
            min_speed_mps=cfg.min_speed_mps,
        )
    return compute_proportional_navigation_command(
        pursuer=pursuer,
        target=target_estimate,
        dt_s=cfg.dt_s,
        navigation_constant=cfg.navigation_constant,
        mode=mode,
        max_lateral_accel_mps2=cfg.max_lateral_accel_mps2,
        max_turn_rate_radps=cfg.max_turn_rate_radps,
        min_speed_mps=cfg.min_speed_mps,
    )


def _should_use_terminal_mode(
    timestamp_s: float,
    range_m: float,
    cfg: GuidanceConfig,
) -> bool:
    if range_m <= cfg.terminal_switch_range_m:
        return True
    if cfg.terminal_switch_time_s is not None and timestamp_s >= cfg.terminal_switch_time_s:
        return True
    return False


def _estimate_target_state(
    mode: GuidanceMode,
    pursuer: GuidanceState,
    target: GuidanceState,
    cfg: GuidanceConfig,
    rng: np.random.Generator,
    previous_relative_estimate: np.ndarray | None,
) -> tuple[GuidanceState, dict[str, Any], np.ndarray]:
    pursuer_position = _array2(pursuer.position_m)
    pursuer_velocity = _array2(pursuer.velocity_mps)
    target_position = _array2(target.position_m)
    target_velocity = _array2(target.velocity_mps)
    true_relative = target_position - pursuer_position

    if mode == GuidanceMode.RADAR_MIDCOURSE:
        position_noise = _normal2(rng, cfg.radar_position_noise_m)
        velocity_noise = _normal2(rng, cfg.radar_velocity_noise_mps)
        estimated_position = target_position + position_noise
        estimated_velocity = target_velocity + velocity_noise
        relative_estimate = estimated_position - pursuer_position
        range_estimate = float(np.linalg.norm(relative_estimate))
        los_angle = _angle_of(relative_estimate)
        observation = {
            "source": "global_track",
            "range_estimate_m": range_estimate,
            "los_angle_rad": los_angle,
            "position_noise_std_m": cfg.radar_position_noise_m,
            "velocity_noise_std_mps": cfg.radar_velocity_noise_mps,
        }
        return (
            GuidanceState(
                entity_id=target.entity_id,
                timestamp_s=pursuer.timestamp_s,
                position_m=_tuple2(estimated_position),
                velocity_mps=_tuple2(estimated_velocity),
                source="global_track",
                covariance_trace=2.0 * cfg.radar_position_noise_m**2,
                metadata={"mode": mode.value},
            ),
            observation,
            relative_estimate,
        )

    true_range = float(np.linalg.norm(true_relative))
    true_los = _angle_of(true_relative)
    measured_los = _wrap_pi(true_los + float(rng.normal(0.0, cfg.vision_los_noise_rad)))
    range_std = true_range * cfg.vision_range_noise_fraction
    range_estimate = max(0.0, true_range + float(rng.normal(0.0, range_std)))
    relative_estimate = range_estimate * np.array(
        [math.cos(measured_los), math.sin(measured_los)],
        dtype=float,
    )
    if previous_relative_estimate is None:
        relative_velocity_estimate = target_velocity - pursuer_velocity
        relative_velocity_source = "initial_relative_velocity"
    else:
        relative_velocity_estimate = (
            relative_estimate - previous_relative_estimate
        ) / cfg.dt_s
        relative_velocity_source = "finite_difference_los"

    estimated_position = pursuer_position + relative_estimate
    estimated_velocity = pursuer_velocity + relative_velocity_estimate
    pursuer_heading = _heading_from_velocity(pursuer_velocity, true_los)
    pixel_x = cfg.vision_image_center_x_px + cfg.vision_focal_length_px * math.tan(
        _wrap_pi(measured_los - pursuer_heading)
    )
    observation = {
        "source": "vision_los",
        "los_angle_rad": measured_los,
        "true_los_angle_rad": true_los,
        "range_estimate_m": range_estimate,
        "pixel_x": float(pixel_x),
        "focal_length_px": cfg.vision_focal_length_px,
        "relative_velocity_source": relative_velocity_source,
    }
    return (
        GuidanceState(
            entity_id=target.entity_id,
            timestamp_s=pursuer.timestamp_s,
            position_m=_tuple2(estimated_position),
            velocity_mps=_tuple2(estimated_velocity),
            source="vision_los_estimate",
            covariance_trace=None,
            metadata={"mode": mode.value},
        ),
        observation,
        relative_estimate,
    )


def _advance_pursuer(
    pursuer: GuidanceState,
    heading_rad: float,
    dt_s: float,
) -> GuidanceState:
    velocity = _array2(pursuer.velocity_mps)
    speed = float(np.linalg.norm(velocity))
    if speed <= 0.0:
        new_velocity = np.zeros(2, dtype=float)
    else:
        new_velocity = speed * np.array([math.cos(heading_rad), math.sin(heading_rad)])
    new_position = _array2(pursuer.position_m) + new_velocity * dt_s
    return GuidanceState(
        entity_id=pursuer.entity_id,
        timestamp_s=pursuer.timestamp_s + dt_s,
        position_m=_tuple2(new_position),
        velocity_mps=_tuple2(new_velocity),
        source=pursuer.source,
        covariance_trace=pursuer.covariance_trace,
        metadata=dict(pursuer.metadata),
    )


def _advance_target(target: GuidanceState, dt_s: float) -> GuidanceState:
    position = _array2(target.position_m)
    velocity = _array2(target.velocity_mps)
    return GuidanceState(
        entity_id=target.entity_id,
        timestamp_s=target.timestamp_s + dt_s,
        position_m=_tuple2(position + velocity * dt_s),
        velocity_mps=target.velocity_mps,
        source=target.source,
        covariance_trace=target.covariance_trace,
        metadata=dict(target.metadata),
    )


def _range_between(first: GuidanceState, second: GuidanceState) -> float:
    return float(np.linalg.norm(_array2(second.position_m) - _array2(first.position_m)))


def _normal2(rng: np.random.Generator, std: float) -> np.ndarray:
    if std <= 0.0:
        return np.zeros(2, dtype=float)
    return rng.normal(0.0, std, size=2)


def _array2(values: tuple[float, float]) -> np.ndarray:
    return np.asarray(values, dtype=float)


def _tuple2(values: np.ndarray) -> tuple[float, float]:
    return (float(values[0]), float(values[1]))


def _angle_of(vector: np.ndarray) -> float:
    if float(np.linalg.norm(vector)) <= 1e-12:
        return 0.0
    return math.atan2(float(vector[1]), float(vector[0]))


def _heading_from_velocity(velocity: np.ndarray, fallback_rad: float) -> float:
    speed = float(np.linalg.norm(velocity))
    if speed <= 1e-12:
        return fallback_rad
    return math.atan2(float(velocity[1]), float(velocity[0]))


def _wrap_pi(angle_rad: float) -> float:
    return (angle_rad + math.pi) % (2.0 * math.pi) - math.pi
