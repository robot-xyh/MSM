"""Bounded terminal visual prediction and command coast for one assignment pair.

This module exposes the short-horizon mechanism validated in
``png_guidance_delivery`` without changing the position-PN, TTC-PNG, or VM-PNG
laws.  Measured and image-KF-predicted observations are still evaluated by the
existing :class:`SimpleFlightPngGuidanceFilter`; blind push only coasts a short
average of previously accepted commands with exponential decay.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
import math
from typing import Any

import numpy as np

from .vision_png import (
    PngGuidanceCommand,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
)


TERMINAL_GUIDANCE_DELIVERY_BOUNDARY = (
    "d7_per_assignment_pair_bounded_terminal_visual_prediction_and_coast"
)


class TerminalDeliveryState(str, Enum):
    ACQUIRING = "acquiring"
    MEASURED = "measured"
    IMAGE_KF_PREDICT = "image_kf_predict"
    BLIND_PUSH = "blind_push"
    REACQUIRED = "reacquired"
    EXPIRED = "expired"


class TerminalFilterAuditState(str, Enum):
    """Auditable image-filter state, independent of the delivery state machine."""

    MEASURED = "measured"
    PREDICTED = "predicted"
    INNOVATION_REJECTED = "innovation_rejected"
    RESET = "reset"
    EXPIRED = "expired"


@dataclass(frozen=True)
class TerminalLifecycleContext:
    """Identity and plan tuple that may own one terminal-filter history."""

    resource_id: str
    assigned_global_track_id: str
    local_track_id: str | None
    plan_owner_id: str | None
    plan_version: int


@dataclass(frozen=True)
class _ImageKfUpdateResult:
    accepted: bool
    innovation_rejected: bool = False
    predicted_theta: np.ndarray | None = None
    prediction_age_s: float | None = None
    innovation_norm_rad: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class TerminalDeliveryConfig:
    """Defaults aligned with the validated delivery terminal mechanism."""

    control_dt_s: float = 0.1
    image_kf_max_predict_s: float = 0.25
    consecutive_loss_frames: int = 3
    command_average_window_s: float = 0.10
    blind_push_duration_s: float = 0.25
    command_decay_tau_s: float = 0.18
    image_measurement_noise_rad: float = 0.006
    image_accel_noise_rad_s2: float = 8.0
    image_innovation_reject_rad: float = 0.20
    soft_innovation_reject_prediction: bool = False
    delivery_trend_coast: bool = False
    delivery_trend_coast_gain: float = 0.10
    delivery_trend_coast_cap_mps: float = 0.75
    image_max_angle_rad: float = 1.0
    image_max_rate_rad_s: float = 8.0

    def __post_init__(self) -> None:
        positive = {
            "control_dt_s": self.control_dt_s,
            "image_kf_max_predict_s": self.image_kf_max_predict_s,
            "command_average_window_s": self.command_average_window_s,
            "blind_push_duration_s": self.blind_push_duration_s,
            "command_decay_tau_s": self.command_decay_tau_s,
            "image_measurement_noise_rad": self.image_measurement_noise_rad,
            "image_accel_noise_rad_s2": self.image_accel_noise_rad_s2,
            "image_innovation_reject_rad": self.image_innovation_reject_rad,
            "image_max_angle_rad": self.image_max_angle_rad,
            "image_max_rate_rad_s": self.image_max_rate_rad_s,
        }
        for name, value in positive.items():
            if value <= 0.0:
                raise ValueError(f"{name} must be positive")
        if self.consecutive_loss_frames < 1:
            raise ValueError("consecutive_loss_frames must be at least one")
        if self.delivery_trend_coast_gain < 0.0:
            raise ValueError("delivery_trend_coast_gain must be nonnegative")
        if self.delivery_trend_coast_cap_mps < 0.0:
            raise ValueError("delivery_trend_coast_cap_mps must be nonnegative")


@dataclass(frozen=True)
class TerminalDeliveryResult:
    state: TerminalDeliveryState
    reason: str
    assigned_global_track_id: str
    command: PngGuidanceCommand | None = None
    effective_observation: VisionGuidanceObservation | None = None
    visual_lock_measured: bool = False
    using_extrapolation: bool = False
    loss_frame_count: int = 0
    measurement_age_s: float | None = None
    blind_elapsed_s: float = 0.0
    blind_decay: float = 0.0
    command_sample_count: int = 0
    filter_audit_state: TerminalFilterAuditState = TerminalFilterAuditState.EXPIRED
    filter_audit_reason: str = ""
    lifecycle_reset: bool = False
    lifecycle_reset_reason: str = ""
    image_innovation_norm_rad: float | None = None
    trend_coast_applied: bool = False
    trend_coast_velocity_ned: tuple[float, float, float] = (0.0, 0.0, 0.0)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def command_available(self) -> bool:
        return self.command is not None


@dataclass(frozen=True)
class _CommandSample:
    timestamp_s: float
    command: PngGuidanceCommand


class _TerminalImageAngleKF:
    """Constant-angular-rate KF equivalent to delivery ``TerminalImageKF``."""

    def __init__(self, config: TerminalDeliveryConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self.x = np.zeros(4, dtype=float)
        self.P = np.diag([0.05, 0.05, 1.0, 1.0]).astype(float)
        self.initialized = False
        self.last_timestamp_s: float | None = None
        self.last_measurement_timestamp_s: float | None = None

    def update(
        self,
        theta: np.ndarray,
        timestamp_s: float,
        *,
        allow_soft_prediction: bool = False,
    ) -> _ImageKfUpdateResult:
        theta = np.asarray(theta, dtype=float).reshape(2)
        theta = np.clip(
            np.nan_to_num(
                theta,
                nan=0.0,
                posinf=self.config.image_max_angle_rad,
                neginf=-self.config.image_max_angle_rad,
            ),
            -self.config.image_max_angle_rad,
            self.config.image_max_angle_rad,
        )
        if not self.initialized:
            self.reset_with_measurement(theta, timestamp_s)
            return _ImageKfUpdateResult(accepted=True)

        self._predict_to(timestamp_s)
        innovation = theta - self.x[:2]
        innovation_norm = float(np.linalg.norm(innovation))
        if innovation_norm > self.config.image_innovation_reject_rad:
            age_s = self.measurement_age(timestamp_s)
            if (
                allow_soft_prediction
                and age_s is not None
                and age_s <= self.config.image_kf_max_predict_s
                and np.all(np.isfinite(self.x))
            ):
                return _ImageKfUpdateResult(
                    accepted=False,
                    innovation_rejected=True,
                    predicted_theta=np.array(self.x[:2], dtype=float),
                    prediction_age_s=age_s,
                    innovation_norm_rad=innovation_norm,
                    reason="image_kf_soft_reject_predict",
                )
            self.reset_with_measurement(theta, timestamp_s)
            return _ImageKfUpdateResult(
                accepted=False,
                innovation_rejected=True,
                innovation_norm_rad=innovation_norm,
                reason="image_kf_innovation_reject",
            )

        H = np.zeros((2, 4), dtype=float)
        H[:, :2] = np.eye(2)
        noise = self.config.image_measurement_noise_rad**2
        S = H @ self.P @ H.T + noise * np.eye(2)
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ innovation
        self.P = (np.eye(4) - K @ H) @ self.P
        self._apply_limits()
        self.last_measurement_timestamp_s = float(timestamp_s)
        return _ImageKfUpdateResult(
            accepted=True,
            innovation_norm_rad=innovation_norm,
        )

    def reset_with_measurement(self, theta: np.ndarray, timestamp_s: float) -> None:
        self.reset()
        self.x[:2] = np.asarray(theta, dtype=float).reshape(2)
        self.initialized = True
        self.last_timestamp_s = float(timestamp_s)
        self.last_measurement_timestamp_s = float(timestamp_s)

    def measurement_age(self, timestamp_s: float) -> float | None:
        if self.last_measurement_timestamp_s is None:
            return None
        return max(0.0, float(timestamp_s) - self.last_measurement_timestamp_s)

    def predict(self, timestamp_s: float) -> tuple[np.ndarray, float] | None:
        if not self.initialized or self.last_measurement_timestamp_s is None:
            return None
        age_s = max(0.0, float(timestamp_s) - self.last_measurement_timestamp_s)
        if age_s > self.config.image_kf_max_predict_s:
            return None
        self._predict_to(timestamp_s)
        if not np.all(np.isfinite(self.x)):
            return None
        return np.array(self.x[:2], dtype=float), age_s

    def _predict_to(self, timestamp_s: float) -> None:
        timestamp_s = float(timestamp_s)
        dt = self.config.control_dt_s
        if self.last_timestamp_s is not None:
            dt = max(1.0e-3, timestamp_s - self.last_timestamp_s)
        self.last_timestamp_s = timestamp_s

        F = np.eye(4, dtype=float)
        F[0, 2] = dt
        F[1, 3] = dt
        q = self.config.image_accel_noise_rad_s2**2
        q_axis = q * np.array(
            [[0.25 * dt**4, 0.5 * dt**3], [0.5 * dt**3, dt**2]],
            dtype=float,
        )
        Q = np.zeros((4, 4), dtype=float)
        Q[np.ix_([0, 2], [0, 2])] = q_axis
        Q[np.ix_([1, 3], [1, 3])] = q_axis
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q
        self._apply_limits()

    def _apply_limits(self) -> None:
        angle = self.config.image_max_angle_rad
        rate = self.config.image_max_rate_rad_s
        self.x[:2] = np.clip(self.x[:2], -angle, angle)
        self.x[2:] = np.clip(self.x[2:], -rate, rate)


class TerminalGuidanceDelivery:
    """Stateful bounded terminal delivery for exactly one assignment pair."""

    def __init__(
        self,
        png_config: PngGuidanceConfig | None = None,
        config: TerminalDeliveryConfig | None = None,
    ) -> None:
        self.png_config = png_config or PngGuidanceConfig()
        self.config = config or TerminalDeliveryConfig(control_dt_s=self.png_config.dt_s)
        self._filter = SimpleFlightPngGuidanceFilter(self.png_config)
        self._image_kf = _TerminalImageAngleKF(self.config)
        self.reset()

    def reset(self) -> None:
        self._filter.reset()
        self._image_kf.reset()
        self._lifecycle_context: TerminalLifecycleContext | None = None
        self._assigned_global_track_id: str | None = None
        self._last_observation: VisionGuidanceObservation | None = None
        self._last_measurement_timestamp_s: float | None = None
        self._loss_frame_count = 0
        self._had_measured_lock = False
        self._loss_started_after_lock = False
        self._blind_started_at_s: float | None = None
        self._blind_base_command: PngGuidanceCommand | None = None
        self._blind_trend_velocity = np.zeros(3, dtype=float)
        self._command_samples: deque[_CommandSample] = deque()

    def ensure_lifecycle(self, context: TerminalLifecycleContext) -> str:
        """Reset all predictive history when identity or plan ownership changes."""

        previous = self._lifecycle_context
        if previous is None:
            self._lifecycle_context = context
            self._assigned_global_track_id = context.assigned_global_track_id
            return ""
        if previous == context:
            return ""
        changed = [
            name
            for name in (
                "resource_id",
                "assigned_global_track_id",
                "local_track_id",
                "plan_owner_id",
                "plan_version",
            )
            if getattr(previous, name) != getattr(context, name)
        ]
        self.reset()
        self._lifecycle_context = context
        self._assigned_global_track_id = context.assigned_global_track_id
        return "lifecycle_" + "_and_".join(changed) + "_changed"

    @property
    def has_measured_lock(self) -> bool:
        """Return whether this pair has measured state eligible for bounded coast."""

        return self._had_measured_lock and self._last_observation is not None

    def block(
        self,
        *,
        assigned_global_track_id: str,
        reason: str,
    ) -> TerminalDeliveryResult:
        """Immediately block and clear all extrapolation state for this pair."""

        acquiring = not self._had_measured_lock and reason == "d5_not_locked"
        self.reset()
        self._assigned_global_track_id = assigned_global_track_id
        return TerminalDeliveryResult(
            state=(
                TerminalDeliveryState.ACQUIRING
                if acquiring
                else TerminalDeliveryState.EXPIRED
            ),
            reason=reason,
            assigned_global_track_id=assigned_global_track_id,
            filter_audit_state=TerminalFilterAuditState.EXPIRED,
            filter_audit_reason=reason,
            metadata={"boundary": TERMINAL_GUIDANCE_DELIVERY_BOUNDARY, "blocked": True},
        )

    def evaluate(
        self,
        *,
        assigned_global_track_id: str,
        timestamp_s: float,
        observation: VisionGuidanceObservation | None,
        current_heading_rad: float,
        current_speed_mps: float,
        intercept_speed_mps: float,
        relative_position_ned: tuple[float, float, float] | np.ndarray | None = None,
        relative_velocity_ned: tuple[float, float, float] | np.ndarray | None = None,
        command_z_ned_m: float = 0.0,
        safety_gate_passed: bool = True,
        lifecycle_context: TerminalLifecycleContext | None = None,
        soft_prediction_eligible: bool = False,
    ) -> TerminalDeliveryResult:
        """Evaluate one terminal sample without creating or rebinding a global ID."""

        timestamp_s = float(timestamp_s)
        lifecycle_reset_reason = ""
        if lifecycle_context is not None:
            lifecycle_reset_reason = self.ensure_lifecycle(lifecycle_context)
        if not safety_gate_passed:
            return self.block(
                assigned_global_track_id=assigned_global_track_id,
                reason="d5_safety_gate_blocked",
            )
        if (
            self._assigned_global_track_id is not None
            and assigned_global_track_id != self._assigned_global_track_id
        ):
            return self.block(
                assigned_global_track_id=assigned_global_track_id,
                reason="terminal_identity_mismatch",
            )
        self._assigned_global_track_id = assigned_global_track_id

        if observation is not None:
            observed_global_id = observation.assigned_global_track_id
            if observed_global_id and observed_global_id != assigned_global_track_id:
                return self.block(
                    assigned_global_track_id=assigned_global_track_id,
                    reason="terminal_identity_mismatch",
                )
            return self._evaluate_measurement(
                observation=observation,
                assigned_global_track_id=assigned_global_track_id,
                timestamp_s=timestamp_s,
                current_heading_rad=current_heading_rad,
                current_speed_mps=current_speed_mps,
                intercept_speed_mps=intercept_speed_mps,
                relative_position_ned=relative_position_ned,
                relative_velocity_ned=relative_velocity_ned,
                command_z_ned_m=command_z_ned_m,
                lifecycle_reset_reason=lifecycle_reset_reason,
                soft_prediction_eligible=soft_prediction_eligible,
            )
        return self._evaluate_loss(
            assigned_global_track_id=assigned_global_track_id,
            timestamp_s=timestamp_s,
            current_heading_rad=current_heading_rad,
            current_speed_mps=current_speed_mps,
            intercept_speed_mps=intercept_speed_mps,
            relative_position_ned=relative_position_ned,
            relative_velocity_ned=relative_velocity_ned,
            command_z_ned_m=command_z_ned_m,
        )

    def _evaluate_measurement(
        self,
        *,
        observation: VisionGuidanceObservation,
        assigned_global_track_id: str,
        timestamp_s: float,
        current_heading_rad: float,
        current_speed_mps: float,
        intercept_speed_mps: float,
        relative_position_ned: tuple[float, float, float] | np.ndarray | None,
        relative_velocity_ned: tuple[float, float, float] | np.ndarray | None,
        command_z_ned_m: float,
        lifecycle_reset_reason: str,
        soft_prediction_eligible: bool,
    ) -> TerminalDeliveryResult:
        reacquired = self._had_measured_lock and self._loss_started_after_lock
        theta = self._angles_from_observation(observation)
        kf_result = self._image_kf.update(
            theta,
            timestamp_s,
            allow_soft_prediction=(
                self.config.soft_innovation_reject_prediction
                and soft_prediction_eligible
                and not lifecycle_reset_reason
            ),
        )
        effective_observation = observation
        using_extrapolation = False
        if kf_result.predicted_theta is not None:
            effective_observation = self._predicted_observation(
                timestamp_s,
                kf_result.predicted_theta,
            )
            using_extrapolation = True
        elif kf_result.innovation_rejected:
            self._filter.reset()
            self._command_samples.clear()
            self._had_measured_lock = False
            self._loss_started_after_lock = False
            self._blind_started_at_s = None
            self._blind_base_command = None
            self._blind_trend_velocity = np.zeros(3, dtype=float)
            return TerminalDeliveryResult(
                state=TerminalDeliveryState.EXPIRED,
                reason="terminal_visual_image_kf_innovation_rejected",
                assigned_global_track_id=assigned_global_track_id,
                effective_observation=observation,
                image_innovation_norm_rad=kf_result.innovation_norm_rad,
                filter_audit_state=TerminalFilterAuditState.INNOVATION_REJECTED,
                filter_audit_reason=kf_result.reason,
                lifecycle_reset=bool(lifecycle_reset_reason),
                lifecycle_reset_reason=lifecycle_reset_reason,
                metadata={"boundary": TERMINAL_GUIDANCE_DELIVERY_BOUNDARY},
            )
        command = self._filter.evaluate(
            effective_observation,
            current_heading_rad=current_heading_rad,
            current_speed_mps=current_speed_mps,
            intercept_speed_mps=intercept_speed_mps,
            relative_position_ned=relative_position_ned,
            relative_velocity_ned=relative_velocity_ned,
            command_z_ned_m=command_z_ned_m,
        )
        if command.quality.terminal_switch_allowed and not using_extrapolation:
            self._record_command(timestamp_s, command)
        if not using_extrapolation:
            self._last_observation = observation
            self._last_measurement_timestamp_s = timestamp_s
        self._loss_frame_count = 0
        self._had_measured_lock = True
        self._loss_started_after_lock = False
        self._blind_started_at_s = None
        self._blind_base_command = None
        self._blind_trend_velocity = np.zeros(3, dtype=float)
        state = (
            TerminalDeliveryState.IMAGE_KF_PREDICT
            if using_extrapolation
            else TerminalDeliveryState.REACQUIRED
            if reacquired
            else TerminalDeliveryState.MEASURED
        )
        reason = (
            "terminal_visual_image_kf_soft_reject_predict"
            if using_extrapolation
            else "terminal_visual_reacquired"
            if reacquired
            else "terminal_visual_measured"
        )
        audit_state = (
            TerminalFilterAuditState.RESET
            if lifecycle_reset_reason
            else TerminalFilterAuditState.PREDICTED
            if using_extrapolation
            else TerminalFilterAuditState.MEASURED
        )
        return TerminalDeliveryResult(
            state=state,
            reason=reason,
            assigned_global_track_id=assigned_global_track_id,
            command=command,
            effective_observation=effective_observation,
            visual_lock_measured=not using_extrapolation,
            using_extrapolation=using_extrapolation,
            loss_frame_count=0,
            measurement_age_s=(kf_result.prediction_age_s if using_extrapolation else 0.0),
            command_sample_count=len(self._command_samples),
            filter_audit_state=audit_state,
            filter_audit_reason=(
                lifecycle_reset_reason or kf_result.reason or "image_kf_measurement_accepted"
            ),
            lifecycle_reset=bool(lifecycle_reset_reason),
            lifecycle_reset_reason=lifecycle_reset_reason,
            image_innovation_norm_rad=kf_result.innovation_norm_rad,
            metadata={"boundary": TERMINAL_GUIDANCE_DELIVERY_BOUNDARY},
        )

    def _evaluate_loss(
        self,
        *,
        assigned_global_track_id: str,
        timestamp_s: float,
        current_heading_rad: float,
        current_speed_mps: float,
        intercept_speed_mps: float,
        relative_position_ned: tuple[float, float, float] | np.ndarray | None,
        relative_velocity_ned: tuple[float, float, float] | np.ndarray | None,
        command_z_ned_m: float,
    ) -> TerminalDeliveryResult:
        if not self._had_measured_lock or self._last_observation is None:
            return TerminalDeliveryResult(
                state=TerminalDeliveryState.ACQUIRING,
                reason="terminal_visual_acquiring",
                assigned_global_track_id=assigned_global_track_id,
                filter_audit_state=TerminalFilterAuditState.EXPIRED,
                filter_audit_reason="image_kf_uninitialized",
                metadata={"boundary": TERMINAL_GUIDANCE_DELIVERY_BOUNDARY},
            )

        self._loss_frame_count += 1
        self._loss_started_after_lock = True
        measurement_age_s = self._measurement_age(timestamp_s)
        if self._loss_frame_count < self.config.consecutive_loss_frames:
            prediction = self._image_kf.predict(timestamp_s)
            if prediction is not None:
                theta, prediction_age_s = prediction
                predicted_observation = self._predicted_observation(timestamp_s, theta)
                command = self._filter.evaluate(
                    predicted_observation,
                    current_heading_rad=current_heading_rad,
                    current_speed_mps=current_speed_mps,
                    intercept_speed_mps=intercept_speed_mps,
                    relative_position_ned=relative_position_ned,
                    relative_velocity_ned=relative_velocity_ned,
                    command_z_ned_m=command_z_ned_m,
                )
                return TerminalDeliveryResult(
                    state=TerminalDeliveryState.IMAGE_KF_PREDICT,
                    reason="terminal_visual_image_kf_predict",
                    assigned_global_track_id=assigned_global_track_id,
                    command=command,
                    effective_observation=predicted_observation,
                    using_extrapolation=True,
                    loss_frame_count=self._loss_frame_count,
                    measurement_age_s=prediction_age_s,
                    command_sample_count=len(self._command_samples),
                    filter_audit_state=TerminalFilterAuditState.PREDICTED,
                    filter_audit_reason="image_kf_detection_loss_predict",
                    metadata={"boundary": TERMINAL_GUIDANCE_DELIVERY_BOUNDARY},
                )

        if self._blind_started_at_s is None:
            self._blind_started_at_s = timestamp_s
            self._blind_base_command = self._average_recent_command(timestamp_s)
            self._blind_trend_velocity = self._recent_los_trend_velocity(timestamp_s)
        blind_elapsed_s = max(0.0, timestamp_s - self._blind_started_at_s)
        if (
            self._blind_base_command is not None
            and blind_elapsed_s <= self.config.blind_push_duration_s
        ):
            decay = math.exp(-blind_elapsed_s / self.config.command_decay_tau_s)
            command = self._decayed_command(
                self._blind_base_command,
                decay,
                trend_velocity=self._blind_trend_velocity,
                speed_cap_mps=max(0.0, float(intercept_speed_mps)),
            )
            trend_applied = bool(
                self.config.delivery_trend_coast
                and np.linalg.norm(self._blind_trend_velocity[:2]) > 0.0
            )
            return TerminalDeliveryResult(
                state=TerminalDeliveryState.BLIND_PUSH,
                reason="terminal_visual_blind_push",
                assigned_global_track_id=assigned_global_track_id,
                command=command,
                using_extrapolation=True,
                loss_frame_count=self._loss_frame_count,
                measurement_age_s=measurement_age_s,
                blind_elapsed_s=blind_elapsed_s,
                blind_decay=decay,
                command_sample_count=len(self._command_samples),
                filter_audit_state=TerminalFilterAuditState.PREDICTED,
                filter_audit_reason="terminal_command_coast",
                trend_coast_applied=trend_applied,
                trend_coast_velocity_ned=tuple(
                    float(value) * decay for value in self._blind_trend_velocity
                ),
                metadata={"boundary": TERMINAL_GUIDANCE_DELIVERY_BOUNDARY},
            )

        return TerminalDeliveryResult(
            state=TerminalDeliveryState.EXPIRED,
            reason="terminal_visual_lost_after_coast",
            assigned_global_track_id=assigned_global_track_id,
            using_extrapolation=False,
            loss_frame_count=self._loss_frame_count,
            measurement_age_s=measurement_age_s,
            blind_elapsed_s=blind_elapsed_s,
            command_sample_count=len(self._command_samples),
            filter_audit_state=TerminalFilterAuditState.EXPIRED,
            filter_audit_reason="terminal_visual_lost_after_coast",
            metadata={"boundary": TERMINAL_GUIDANCE_DELIVERY_BOUNDARY},
        )

    def _angles_from_observation(self, observation: VisionGuidanceObservation) -> np.ndarray:
        center_x, center_y = observation.center_px
        return np.array(
            [
                math.atan2(
                    center_x - 0.5 * self.png_config.image_width_px,
                    self.png_config.focal_length_px,
                ),
                math.atan2(
                    center_y - 0.5 * self.png_config.image_height_px,
                    self.png_config.focal_length_px,
                ),
            ],
            dtype=float,
        )

    def _predicted_observation(
        self,
        timestamp_s: float,
        theta: np.ndarray,
    ) -> VisionGuidanceObservation:
        assert self._last_observation is not None
        last = self._last_observation
        center_x = 0.5 * self.png_config.image_width_px + self.png_config.focal_length_px * math.tan(float(theta[0]))
        center_y = 0.5 * self.png_config.image_height_px + self.png_config.focal_length_px * math.tan(float(theta[1]))
        half_width = 0.5 * last.width_px
        half_height = 0.5 * last.height_px
        max_x = float(self.png_config.image_width_px)
        max_y = float(self.png_config.image_height_px)
        center_x = float(np.clip(center_x, half_width, max(half_width, max_x - half_width)))
        center_y = float(np.clip(center_y, half_height, max(half_height, max_y - half_height)))
        metadata = {
            **last.metadata,
            "terminal_delivery_state": TerminalDeliveryState.IMAGE_KF_PREDICT.value,
            "terminal_prediction": True,
        }
        return replace(
            last,
            timestamp_s=timestamp_s,
            frame_timestamp_s=timestamp_s,
            bbox_xyxy=(
                center_x - half_width,
                center_y - half_height,
                center_x + half_width,
                center_y + half_height,
            ),
            metadata=metadata,
        )

    def _record_command(self, timestamp_s: float, command: PngGuidanceCommand) -> None:
        self._command_samples.append(_CommandSample(timestamp_s, command))
        self._prune_commands(timestamp_s)

    def _prune_commands(self, timestamp_s: float) -> None:
        keep_s = max(
            1.0,
            self.config.command_average_window_s,
            self.config.blind_push_duration_s,
            self.config.image_kf_max_predict_s,
        )
        while self._command_samples and timestamp_s - self._command_samples[0].timestamp_s > keep_s:
            self._command_samples.popleft()

    def _average_recent_command(self, timestamp_s: float) -> PngGuidanceCommand | None:
        self._prune_commands(timestamp_s)
        samples = [
            sample
            for sample in self._command_samples
            if timestamp_s - sample.timestamp_s <= self.config.command_average_window_s + 1.0e-9
        ]
        if not samples:
            samples = list(self._command_samples)[-1:]
        if not samples:
            return None
        commands = [sample.command for sample in samples]
        base = commands[-1]
        velocity = np.mean(np.asarray([item.velocity_ned for item in commands], dtype=float), axis=0)
        turn_rate = float(np.mean([item.turn_rate_radps for item in commands]))
        heading = math.atan2(float(velocity[1]), float(velocity[0]))
        return replace(
            base,
            heading_rad=heading,
            turn_rate_radps=turn_rate,
            velocity_ned=tuple(float(item) for item in velocity),
            metadata={
                **base.metadata,
                "terminal_command_average_window_s": self.config.command_average_window_s,
                "terminal_command_sample_count": len(samples),
            },
        )

    def _recent_los_trend_velocity(self, timestamp_s: float) -> np.ndarray:
        if not self.config.delivery_trend_coast:
            return np.zeros(3, dtype=float)
        self._prune_commands(timestamp_s)
        samples = [
            sample
            for sample in self._command_samples
            if timestamp_s - sample.timestamp_s
            <= self.config.command_average_window_s + 1.0e-9
        ]
        if not samples:
            samples = list(self._command_samples)[-1:]
        if not samples:
            return np.zeros(3, dtype=float)
        los_rates = [
            float(sample.command.quality.filtered_los_rate_radps)
            for sample in samples
        ]
        base_velocity = np.mean(
            np.asarray([sample.command.velocity_ned for sample in samples], dtype=float),
            axis=0,
        )
        horizontal_speed = float(np.linalg.norm(base_velocity[:2]))
        if horizontal_speed <= 1.0e-9:
            return np.zeros(3, dtype=float)
        normal = np.array(
            [-base_velocity[1] / horizontal_speed, base_velocity[0] / horizontal_speed],
            dtype=float,
        )
        magnitude = (
            horizontal_speed
            * self.config.delivery_trend_coast_gain
            * float(np.mean(los_rates))
        )
        magnitude = float(
            np.clip(
                magnitude,
                -self.config.delivery_trend_coast_cap_mps,
                self.config.delivery_trend_coast_cap_mps,
            )
        )
        return np.array([normal[0] * magnitude, normal[1] * magnitude, 0.0], dtype=float)

    @staticmethod
    def _decayed_command(
        command: PngGuidanceCommand,
        decay: float,
        *,
        trend_velocity: np.ndarray | None = None,
        speed_cap_mps: float = 0.0,
    ) -> PngGuidanceCommand:
        velocity_array = np.asarray(command.velocity_ned, dtype=float) * decay
        trend = np.zeros(3, dtype=float)
        if trend_velocity is not None:
            trend = np.asarray(trend_velocity, dtype=float).reshape(3) * decay
            trend[2] = 0.0
            velocity_array += trend
        horizontal_norm = float(np.linalg.norm(velocity_array[:2]))
        if speed_cap_mps > 0.0 and horizontal_norm > speed_cap_mps:
            velocity_array[:2] *= speed_cap_mps / horizontal_norm
        velocity = tuple(float(value) for value in velocity_array)
        heading = command.heading_rad
        if abs(velocity[0]) + abs(velocity[1]) > 1.0e-9:
            heading = math.atan2(velocity[1], velocity[0])
        return replace(
            command,
            heading_rad=heading,
            turn_rate_radps=command.turn_rate_radps * decay,
            velocity_ned=velocity,
            metadata={
                **command.metadata,
                "terminal_delivery_state": TerminalDeliveryState.BLIND_PUSH.value,
                "terminal_blind_decay": decay,
                "terminal_delivery_trend_coast_velocity_ned": tuple(
                    float(value) for value in trend
                ),
            },
        )

    def _measurement_age(self, timestamp_s: float) -> float | None:
        if self._last_measurement_timestamp_s is None:
            return None
        return max(0.0, timestamp_s - self._last_measurement_timestamp_s)
