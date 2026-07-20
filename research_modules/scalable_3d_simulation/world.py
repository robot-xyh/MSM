"""Vectorized 3D point-mass world for intruders, interceptors, and recon nodes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dynamics import integrate_point_masses
from .models import (
    EntityKind,
    EntitySnapshot,
    KinematicLimits,
    MotionProfile,
    ScenarioConfig,
    WorldSnapshot,
)


@dataclass(frozen=True)
class WorldStepDiagnostics:
    """Numerical diagnostics for one world step."""

    timestamp: float
    finite_state: bool
    active_intruder_count: int
    active_interceptor_count: int
    active_recon_count: int
    max_target_speed_mps: float
    max_interceptor_speed_mps: float
    max_recon_speed_mps: float


class VectorizedPointMassWorld:
    """Own all truth-bearing point-mass states for one episode."""

    def __init__(self, config: ScenarioConfig) -> None:
        self.config = config
        self.rng = np.random.default_rng(config.seed)
        self.intruder_ids = tuple(f"TGT-{index + 1:04d}" for index in range(config.target_count))
        self.interceptor_ids = tuple(
            f"INT-{index + 1:04d}" for index in range(config.resource_count)
        )
        self.recon_ids = tuple(f"RECON-{index + 1:03d}" for index in range(config.recon_count))
        self.intruder_limits = KinematicLimits(18.0, 8.0, 0.8, 5.0)
        self.interceptor_limits = KinematicLimits(
            max(20.0, config.interceptor_speed_mps * 1.5),
            20.0,
            1.2,
            10.0,
        )
        self.recon_limits = KinematicLimits(22.0, 8.0, 0.6, 6.0)
        self.timestamp = 0.0
        self.intruder_state = np.empty((config.target_count, 6), dtype=float)
        self.interceptor_state = np.empty((config.resource_count, 6), dtype=float)
        self.recon_state = np.empty((config.recon_count, 6), dtype=float)
        self.intruder_active = np.ones(config.target_count, dtype=bool)
        self.interceptor_active = np.ones(config.resource_count, dtype=bool)
        self.recon_active = np.ones(config.recon_count, dtype=bool)
        self.intercepted_target_indices: set[int] = set()
        self.reset()

    def reset(self) -> WorldSnapshot:
        """Reset all entities to a deterministic configuration for the scenario seed."""

        self.rng = np.random.default_rng(self.config.seed)
        self.timestamp = 0.0
        self.intruder_state = self._initial_intruders()
        self.interceptor_state = self._initial_interceptors()
        self.recon_state = self._initial_recon()
        self.intruder_active.fill(True)
        self.interceptor_active.fill(True)
        self.recon_active.fill(True)
        self.intercepted_target_indices.clear()
        return self.snapshot()

    def step(
        self,
        *,
        intruder_acceleration_ned: np.ndarray | None = None,
        interceptor_acceleration_ned: np.ndarray | None = None,
        recon_acceleration_ned: np.ndarray | None = None,
    ) -> WorldStepDiagnostics:
        """Advance all entity groups by one configured physics step."""

        dt_s = self.config.physics_dt_s
        intruder_commands = (
            self.default_intruder_commands(self.timestamp)
            if intruder_acceleration_ned is None
            else np.asarray(intruder_acceleration_ned, dtype=float)
        )
        interceptor_commands = _commands_or_zeros(
            interceptor_acceleration_ned,
            self.config.resource_count,
        )
        recon_commands = _commands_or_zeros(recon_acceleration_ned, self.config.recon_count)
        self.intruder_state, _ = integrate_point_masses(
            self.intruder_state,
            intruder_commands,
            dt_s=dt_s,
            limits=self.intruder_limits,
            active=self.intruder_active,
        )
        self.interceptor_state, _ = integrate_point_masses(
            self.interceptor_state,
            interceptor_commands,
            dt_s=dt_s,
            limits=self.interceptor_limits,
            active=self.interceptor_active,
        )
        self.recon_state, _ = integrate_point_masses(
            self.recon_state,
            recon_commands,
            dt_s=dt_s,
            limits=self.recon_limits,
            active=self.recon_active,
        )
        self._enforce_world_bounds(self.intruder_state)
        self._enforce_world_bounds(self.interceptor_state)
        self._enforce_world_bounds(self.recon_state)
        self.timestamp = round(self.timestamp + dt_s, 12)
        return self.diagnostics()

    def default_intruder_commands(self, timestamp: float) -> np.ndarray:
        """Return deterministic acceleration for the configured motion profile."""

        commands = np.zeros((self.config.target_count, 3), dtype=float)
        profile = self.config.motion_profile
        velocity = self.intruder_state[:, 3:]
        horizontal_speed = np.linalg.norm(velocity[:, :2], axis=1)
        safe_speed = np.maximum(horizontal_speed, 1.0e-9)
        normal_left = np.column_stack((-velocity[:, 1], velocity[:, 0])) / safe_speed[:, None]
        if profile == MotionProfile.COORDINATED_TURN:
            commands[:, :2] = normal_left * (horizontal_speed * 0.04)[:, None]
        elif profile == MotionProfile.CROSSING:
            phase = np.sin(0.25 * timestamp + np.arange(self.config.target_count) * 0.2)
            commands[:, :2] = normal_left * (0.8 * phase)[:, None]
        elif profile == MotionProfile.FORMATION_SPLIT:
            if timestamp >= self.config.duration_s / 3.0:
                sign = np.where(np.arange(self.config.target_count) % 2 == 0, 1.0, -1.0)
                commands[:, :2] = normal_left * sign[:, None] * 0.9
        elif profile == MotionProfile.EVASIVE:
            index = np.arange(self.config.target_count, dtype=float)
            lateral = np.sin(0.7 * timestamp + index * 0.31)
            vertical = np.cos(0.45 * timestamp + index * 0.17)
            commands[:, :2] = normal_left * (1.5 * lateral)[:, None]
            commands[:, 2] = 0.5 * vertical
        return commands

    def snapshot(self) -> WorldSnapshot:
        return WorldSnapshot(
            timestamp=self.timestamp,
            intruders=EntitySnapshot(
                EntityKind.INTRUDER,
                self.intruder_ids,
                self.intruder_state,
                self.intruder_active,
            ),
            interceptors=EntitySnapshot(
                EntityKind.INTERCEPTOR,
                self.interceptor_ids,
                self.interceptor_state,
                self.interceptor_active,
            ),
            recon=EntitySnapshot(
                EntityKind.RECON,
                self.recon_ids,
                self.recon_state,
                self.recon_active,
            ),
            intercepted_target_indices=tuple(sorted(self.intercepted_target_indices)),
        )

    def diagnostics(self) -> WorldStepDiagnostics:
        finite = all(
            np.all(np.isfinite(state))
            for state in (self.intruder_state, self.interceptor_state, self.recon_state)
        )
        return WorldStepDiagnostics(
            timestamp=self.timestamp,
            finite_state=finite,
            active_intruder_count=int(np.count_nonzero(self.intruder_active)),
            active_interceptor_count=int(np.count_nonzero(self.interceptor_active)),
            active_recon_count=int(np.count_nonzero(self.recon_active)),
            max_target_speed_mps=_max_speed(self.intruder_state),
            max_interceptor_speed_mps=_max_speed(self.interceptor_state),
            max_recon_speed_mps=_max_speed(self.recon_state),
        )

    def register_intercepts(self, assignment_pairs: np.ndarray) -> tuple[int, ...]:
        """Mark assigned targets intercepted when a pair is inside the 3D radius."""

        pairs = np.asarray(assignment_pairs, dtype=int)
        if pairs.size == 0:
            return ()
        if pairs.ndim != 2 or pairs.shape[1] != 2:
            raise ValueError("assignment_pairs must have shape (pair_count, 2)")
        newly_intercepted: list[int] = []
        for resource_index, target_index in pairs:
            if not 0 <= resource_index < self.config.resource_count:
                raise IndexError("resource index out of range")
            if not 0 <= target_index < self.config.target_count:
                raise IndexError("target index out of range")
            if not self.interceptor_active[resource_index] or not self.intruder_active[target_index]:
                continue
            distance = float(
                np.linalg.norm(
                    self.interceptor_state[resource_index, :3]
                    - self.intruder_state[target_index, :3]
                )
            )
            if distance <= self.config.intercept_radius_m:
                self.intruder_active[target_index] = False
                self.intercepted_target_indices.add(int(target_index))
                newly_intercepted.append(int(target_index))
        return tuple(newly_intercepted)

    def pairwise_resource_target_distance(self) -> np.ndarray:
        """Return the full resource-target 3D distance matrix."""

        delta = self.interceptor_state[:, None, :3] - self.intruder_state[None, :, :3]
        return np.linalg.norm(delta, axis=2)

    def _initial_intruders(self) -> np.ndarray:
        count = self.config.target_count
        angles = _even_angles(count) + self.rng.normal(0.0, 0.015, count)
        radii = self.rng.uniform(
            self.config.world_half_extent_m * 0.72,
            self.config.world_half_extent_m * 0.90,
            count,
        )
        altitude = self.rng.uniform(100.0, 350.0, count)
        position = np.column_stack((radii * np.cos(angles), radii * np.sin(angles), -altitude))
        inward = -position[:, :2]
        inward /= np.maximum(np.linalg.norm(inward, axis=1, keepdims=True), 1.0e-9)
        tangent = np.column_stack((-inward[:, 1], inward[:, 0]))
        direction = inward + tangent * self.rng.normal(0.0, 0.08, (count, 1))
        direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1.0e-9)
        speed = self.rng.uniform(
            self.config.target_speed_min_mps,
            self.config.target_speed_max_mps,
            count,
        )
        velocity = np.column_stack((direction * speed[:, None], np.zeros(count)))
        return np.column_stack((position, velocity))

    def _initial_interceptors(self) -> np.ndarray:
        count = self.config.resource_count
        angles = _even_angles(count) + np.pi / max(count, 1)
        radii = self.rng.uniform(
            self.config.protected_radius_m * 1.3,
            self.config.protected_radius_m * 2.0,
            count,
        )
        altitude = self.rng.uniform(60.0, 160.0, count)
        position = np.column_stack((radii * np.cos(angles), radii * np.sin(angles), -altitude))
        outward = position[:, :2] / np.maximum(
            np.linalg.norm(position[:, :2], axis=1, keepdims=True),
            1.0e-9,
        )
        velocity = np.column_stack(
            (
                outward * (0.25 * self.config.interceptor_speed_mps),
                np.zeros(count),
            )
        )
        return np.column_stack((position, velocity))

    def _initial_recon(self) -> np.ndarray:
        count = self.config.recon_count
        if count == 0:
            return np.empty((0, 6), dtype=float)
        angles = _even_angles(count)
        radii = np.full(count, self.config.protected_radius_m * 2.5, dtype=float)
        altitude = np.full(count, 500.0, dtype=float)
        position = np.column_stack((radii * np.cos(angles), radii * np.sin(angles), -altitude))
        velocity = np.zeros((count, 3), dtype=float)
        return np.column_stack((position, velocity))

    def _enforce_world_bounds(self, state: np.ndarray) -> None:
        if state.size == 0:
            return
        extent = self.config.world_half_extent_m
        state[:, 0] = np.clip(state[:, 0], -extent, extent)
        state[:, 1] = np.clip(state[:, 1], -extent, extent)
        state[:, 2] = np.clip(
            state[:, 2],
            -self.config.maximum_altitude_m,
            -self.config.minimum_altitude_m,
        )


def _commands_or_zeros(value: np.ndarray | None, count: int) -> np.ndarray:
    if value is None:
        return np.zeros((count, 3), dtype=float)
    array = np.asarray(value, dtype=float)
    if array.shape != (count, 3):
        raise ValueError(f"command must have shape ({count}, 3)")
    return array


def _even_angles(count: int) -> np.ndarray:
    return np.arange(count, dtype=float) * (2.0 * np.pi / max(count, 1))


def _max_speed(state: np.ndarray) -> float:
    if state.size == 0:
        return 0.0
    return float(np.max(np.linalg.norm(state[:, 3:], axis=1)))
