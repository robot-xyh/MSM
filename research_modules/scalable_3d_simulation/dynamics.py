"""Vectorized constrained point-mass dynamics in the local NED frame."""

from __future__ import annotations

import math

import numpy as np

from .models import KinematicLimits


EPS = 1.0e-12


def integrate_point_masses(
    state: np.ndarray,
    acceleration_command_ned: np.ndarray,
    *,
    dt_s: float,
    limits: KinematicLimits,
    active: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Advance `[position, velocity]` states under bounded 3D acceleration.

    Returns the next state and the acceleration that was actually realized
    after speed, climb-rate, and turn-rate constraints.
    """

    current = np.asarray(state, dtype=float)
    commands = np.asarray(acceleration_command_ned, dtype=float)
    if current.ndim != 2 or current.shape[1] != 6:
        raise ValueError("state must have shape (entity_count, 6)")
    if commands.shape != (current.shape[0], 3):
        raise ValueError("acceleration_command_ned must have shape (entity_count, 3)")
    if not np.all(np.isfinite(current)) or not np.all(np.isfinite(commands)):
        raise ValueError("state and commands must contain only finite values")
    if not np.isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError("dt_s must be positive and finite")

    mask = (
        np.ones(current.shape[0], dtype=bool)
        if active is None
        else np.asarray(active, dtype=bool).reshape(-1)
    )
    if mask.shape != (current.shape[0],):
        raise ValueError("active must have shape (entity_count,)")

    bounded_accel = _clip_row_norm(commands, limits.max_accel_mps2)
    previous_velocity = current[:, 3:]
    proposed_velocity = previous_velocity + bounded_accel * float(dt_s)
    proposed_velocity[:, 2] = np.clip(
        proposed_velocity[:, 2],
        -limits.max_climb_rate_mps,
        limits.max_climb_rate_mps,
    )
    proposed_velocity = _clip_row_norm(proposed_velocity, limits.max_speed_mps)
    next_velocity = _limit_turn_rate(
        previous_velocity,
        proposed_velocity,
        max_angle_rad=limits.max_turn_rate_radps * float(dt_s),
    )

    next_state = current.copy()
    next_state[mask, :3] = current[mask, :3] + 0.5 * (
        previous_velocity[mask] + next_velocity[mask]
    ) * float(dt_s)
    next_state[mask, 3:] = next_velocity[mask]
    realized_accel = np.zeros_like(commands)
    realized_accel[mask] = (next_velocity[mask] - previous_velocity[mask]) / float(dt_s)
    return next_state, realized_accel


def _clip_row_norm(values: np.ndarray, limit: float) -> np.ndarray:
    result = np.asarray(values, dtype=float).copy()
    norms = np.linalg.norm(result, axis=1)
    scale = np.ones_like(norms)
    over = norms > float(limit)
    scale[over] = float(limit) / np.maximum(norms[over], EPS)
    return result * scale[:, None]


def _limit_turn_rate(
    previous_velocity: np.ndarray,
    proposed_velocity: np.ndarray,
    *,
    max_angle_rad: float,
) -> np.ndarray:
    """Limit the three-dimensional change in velocity direction."""

    if max_angle_rad <= 0.0:
        raise ValueError("max_angle_rad must be positive")
    output = proposed_velocity.copy()
    previous_speed = np.linalg.norm(previous_velocity, axis=1)
    proposed_speed = np.linalg.norm(proposed_velocity, axis=1)
    eligible = np.flatnonzero((previous_speed > EPS) & (proposed_speed > EPS))
    for index in eligible:
        old_unit = previous_velocity[index] / previous_speed[index]
        new_unit = proposed_velocity[index] / proposed_speed[index]
        cosine = float(np.clip(np.dot(old_unit, new_unit), -1.0, 1.0))
        angle = math.acos(cosine)
        if angle <= max_angle_rad + 1.0e-12:
            continue
        axis = np.cross(old_unit, new_unit)
        axis_norm = float(np.linalg.norm(axis))
        if axis_norm <= EPS:
            axis = _orthogonal_axis(old_unit)
        else:
            axis = axis / axis_norm
        rotated = _rodrigues(old_unit, axis, max_angle_rad)
        output[index] = rotated * proposed_speed[index]
    return output


def _orthogonal_axis(unit: np.ndarray) -> np.ndarray:
    basis = np.array([1.0, 0.0, 0.0], dtype=float)
    if abs(float(np.dot(unit, basis))) > 0.9:
        basis = np.array([0.0, 1.0, 0.0], dtype=float)
    axis = np.cross(unit, basis)
    return axis / max(float(np.linalg.norm(axis)), EPS)


def _rodrigues(vector: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (
        vector * cosine
        + np.cross(axis, vector) * sine
        + axis * float(np.dot(axis, vector)) * (1.0 - cosine)
    )
