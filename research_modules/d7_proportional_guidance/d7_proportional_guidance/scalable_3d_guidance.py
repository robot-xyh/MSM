"""Deterministic 3D closed-loop guidance for the scalable point-mass world.

This path is intentionally separate from the validated planar PN/PNG API. It
consumes upstream objects by field name, keeps one state bundle per assignment
pair, and returns an acceleration matrix that main can write into its world by
resource index. D7 does not allocate resources, authorize assignments, or
create/rebind global track identities.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
import math
from typing import Any

import numpy as np

from .terminal_gate import (
    ALLOWED_D4_ACTIONS,
    AssignmentGuidanceBinding,
    D4GuidancePermission,
    coerce_assignment_guidance_binding,
    coerce_d4_guidance_permission,
    evaluate_terminal_coast_contract,
    evaluate_terminal_png_contract,
)


SCALABLE_3D_GUIDANCE_BOUNDARY = "d7-deterministic-scalable-3d-guidance-v1"
EPS = 1.0e-9


class GuidanceMode3D(str, Enum):
    """Executable modes for the independent 3D guidance path."""

    HOLD = "hold"
    MIDCOURSE_PN = "midcourse_pn_3d"
    TERMINAL_VISUAL_PNG = "terminal_visual_png_3d"
    TERMINAL_VISUAL_COAST = "terminal_visual_coast_3d"
    ESTIMATED_INTERCEPT = "estimated_intercept"


@dataclass(frozen=True)
class ScalableGuidanceConfig3D:
    """Deterministic guidance and gate thresholds in SI units."""

    navigation_constant: float = 3.0
    terminal_navigation_constant: float = 3.0
    terminal_switch_range_m: float = 120.0
    intercept_radius_m: float = 5.0
    desired_closing_speed_mps: float = 12.0
    speed_response_gain: float = 1.2
    max_accel_mps2: float = 16.0
    max_lateral_accel_mps2: float = 12.0
    max_longitudinal_accel_mps2: float = 6.0
    min_closing_speed_mps: float = 0.2
    min_maneuver_margin: float = 0.15
    max_track_age_s: float = 0.75
    max_track_extrapolation_s: float = 0.50
    track_position_filter_gain: float = 0.75
    track_velocity_filter_gain: float = 0.60
    track_residual_velocity_gain: float = 0.10
    min_detection_confidence: float = 0.55
    min_bbox_area_ratio: float = 0.0008
    max_visual_latency_s: float = 0.35
    min_visual_stable_frames: int = 2
    los_process_lambda: float = 1.0e-4
    los_process_lambda_dot: float = 5.0e-3
    los_measurement_noise: float = 5.0e-3
    los_innovation_reject: float = 0.25
    ttc_area_filter_alpha: float = 0.25
    ttc_window_size: int = 5
    ttc_min_area_px2: float = 16.0
    ttc_max_area_jump_ratio: float = 2.5
    ttc_min_area_dot_px2_s: float = 1.0e-6
    ttc_max_s: float = 20.0
    max_visual_closing_speed_mps: float = 40.0
    coast_max_loss_frames: int = 2
    coast_max_duration_s: float = 0.25
    coast_command_window_s: float = 0.10
    coast_decay_tau_s: float = 0.18

    def __post_init__(self) -> None:
        positive = (
            "navigation_constant",
            "terminal_navigation_constant",
            "terminal_switch_range_m",
            "desired_closing_speed_mps",
            "max_accel_mps2",
            "max_lateral_accel_mps2",
            "max_longitudinal_accel_mps2",
            "max_track_age_s",
            "max_track_extrapolation_s",
            "los_measurement_noise",
            "los_innovation_reject",
            "ttc_min_area_px2",
            "ttc_max_s",
            "max_visual_closing_speed_mps",
            "coast_max_duration_s",
            "coast_command_window_s",
            "coast_decay_tau_s",
        )
        for name in positive:
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
        nonnegative = (
            "intercept_radius_m",
            "speed_response_gain",
            "min_closing_speed_mps",
            "min_maneuver_margin",
            "min_detection_confidence",
            "min_bbox_area_ratio",
            "max_visual_latency_s",
            "los_process_lambda",
            "los_process_lambda_dot",
            "ttc_min_area_dot_px2_s",
        )
        for name in nonnegative:
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and nonnegative")
        unit_interval = (
            "track_position_filter_gain",
            "track_velocity_filter_gain",
            "track_residual_velocity_gain",
            "ttc_area_filter_alpha",
        )
        for name in unit_interval:
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if not 0.0 <= self.min_detection_confidence <= 1.0:
            raise ValueError("min_detection_confidence must be in [0, 1]")
        if not 0.0 <= self.min_maneuver_margin < 1.0:
            raise ValueError("min_maneuver_margin must be in [0, 1)")
        if self.min_visual_stable_frames < 1:
            raise ValueError("min_visual_stable_frames must be at least one")
        if self.ttc_window_size < 2:
            raise ValueError("ttc_window_size must be at least two")
        if self.ttc_max_area_jump_ratio <= 1.0:
            raise ValueError("ttc_max_area_jump_ratio must exceed one")
        if self.coast_max_loss_frames < 1:
            raise ValueError("coast_max_loss_frames must be at least one")


@dataclass(frozen=True)
class TerminalVisualObservation3D:
    """One synchronized strapdown-camera observation in the NED contract."""

    timestamp_s: float
    bbox_xyxy: tuple[float, float, float, float]
    image_width_px: int
    image_height_px: int
    camera_intrinsics: np.ndarray
    camera_to_ned_rotation: np.ndarray
    detection_confidence: float
    local_track_id: str | None = None
    assigned_global_track_id: str | None = None
    camera_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        timestamp = float(self.timestamp_s)
        bbox = np.asarray(self.bbox_xyxy, dtype=float).reshape(-1)
        intrinsics = np.asarray(self.camera_intrinsics, dtype=float)
        rotation = np.asarray(self.camera_to_ned_rotation, dtype=float)
        if not np.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("timestamp_s must be finite and nonnegative")
        if bbox.shape != (4,) or not np.all(np.isfinite(bbox)):
            raise ValueError("bbox_xyxy must contain four finite values")
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            raise ValueError("bbox_xyxy must have positive width and height")
        if self.image_width_px <= 0 or self.image_height_px <= 0:
            raise ValueError("image dimensions must be positive")
        if intrinsics.shape != (3, 3) or not np.all(np.isfinite(intrinsics)):
            raise ValueError("camera_intrinsics must be a finite 3x3 matrix")
        if intrinsics[0, 0] <= 0.0 or intrinsics[1, 1] <= 0.0:
            raise ValueError("camera focal lengths must be positive")
        if rotation.shape != (3, 3) or not np.all(np.isfinite(rotation)):
            raise ValueError("camera_to_ned_rotation must be a finite 3x3 matrix")
        if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1.0e-6):
            raise ValueError("camera_to_ned_rotation must be orthonormal")
        if float(np.linalg.det(rotation)) < 0.999999:
            raise ValueError("camera_to_ned_rotation must be a proper rotation")
        confidence = float(self.detection_confidence)
        if not np.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("detection_confidence must be in [0, 1]")
        intrinsics = intrinsics.copy()
        rotation = rotation.copy()
        intrinsics.setflags(write=False)
        rotation.setflags(write=False)
        object.__setattr__(self, "timestamp_s", timestamp)
        object.__setattr__(self, "bbox_xyxy", tuple(float(v) for v in bbox))
        object.__setattr__(self, "camera_intrinsics", intrinsics)
        object.__setattr__(self, "camera_to_ned_rotation", rotation)
        object.__setattr__(self, "detection_confidence", confidence)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def center_px(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox_xyxy
        return (0.5 * (x1 + x2), 0.5 * (y1 + y2))

    @property
    def area_px2(self) -> float:
        x1, y1, x2, y2 = self.bbox_xyxy
        return float((x2 - x1) * (y2 - y1))

    @property
    def area_ratio(self) -> float:
        return self.area_px2 / float(self.image_width_px * self.image_height_px)

    @property
    def clipped(self) -> bool:
        x1, y1, x2, y2 = self.bbox_xyxy
        return bool(
            x1 <= 0.0
            or y1 <= 0.0
            or x2 >= float(self.image_width_px)
            or y2 >= float(self.image_height_px)
        )

    def los_unit_ned(self) -> np.ndarray:
        """Convert the bbox center ray from optical coordinates into NED."""

        u, v = self.center_px
        fx = float(self.camera_intrinsics[0, 0])
        fy = float(self.camera_intrinsics[1, 1])
        cx = float(self.camera_intrinsics[0, 2])
        cy = float(self.camera_intrinsics[1, 2])
        ray_camera = _normalize(np.array([(u - cx) / fx, (v - cy) / fy, 1.0]))
        return _normalize(self.camera_to_ned_rotation @ ray_camera)


@dataclass(frozen=True)
class AssignmentPairGuidanceInput3D:
    """All upstream state needed to command one already-assigned resource."""

    resource_index: int
    resource_state: np.ndarray
    global_track: Any
    binding: Any
    d4_permission: Any
    terminal_association: Any | None
    active_plan_id: str
    active_plan_version: int
    timestamp_s: float
    visual_observation: TerminalVisualObservation3D | Mapping[str, Any] | Any | None = None
    camera_recognition_ready: bool | None = None
    available_accel_mps2: float | None = None


@dataclass(frozen=True)
class GuidanceCommand3D:
    """Auditable NED acceleration command for one assignment pair."""

    timestamp_s: float
    resource_index: int
    resource_id: str
    assigned_global_track_id: str
    plan_id: str
    plan_version: int
    mode: GuidanceMode3D
    acceleration_ned_mps2: tuple[float, float, float]
    range_m: float | None
    closing_speed_mps: float | None
    los_unit_ned: tuple[float, float, float]
    los_rate_ned_radps: tuple[float, float, float]
    command_norm_mps2: float
    command_saturated: bool
    gate_reason: str = ""
    terminal_contract_allowed: bool = False
    visual_switch_allowed: bool = False
    camera_recognition_gate_passed: bool | None = None
    maneuver_gate_passed: bool | None = None
    maneuver_margin: float | None = None
    ttc_s: float | None = None
    track_age_s: float | None = None
    track_extrapolation_s: float = 0.0
    using_visual_coast: bool = False
    visual_loss_frame_count: int = 0
    mode_transition: bool = False
    previous_mode: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        acceleration = np.asarray(self.acceleration_ned_mps2, dtype=float)
        if acceleration.shape != (3,) or not np.all(np.isfinite(acceleration)):
            raise ValueError("acceleration_ned_mps2 must be a finite 3-vector")
        if self.command_norm_mps2 < 0.0 or not np.isfinite(self.command_norm_mps2):
            raise ValueError("command_norm_mps2 must be finite and nonnegative")
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class GuidanceBatch3D:
    """Resource-indexed acceleration matrix suitable for ``world.step``."""

    acceleration_ned_mps2: np.ndarray
    pair_commands: tuple[GuidanceCommand3D, ...]

    def __post_init__(self) -> None:
        acceleration = np.asarray(self.acceleration_ned_mps2, dtype=float)
        if acceleration.ndim != 2 or acceleration.shape[1] != 3:
            raise ValueError("acceleration_ned_mps2 must have shape (resource_count, 3)")
        if not np.all(np.isfinite(acceleration)):
            raise ValueError("batch acceleration must contain only finite values")
        acceleration = acceleration.copy()
        acceleration.setflags(write=False)
        object.__setattr__(self, "acceleration_ned_mps2", acceleration)

    def to_world_acceleration(self) -> np.ndarray:
        return self.acceleration_ned_mps2.copy()


@dataclass(frozen=True)
class PairGuidanceStateSnapshot3D:
    """Read-only diagnostic snapshot of one pair's independent state."""

    resource_id: str
    assigned_global_track_id: str
    plan_id: str
    plan_version: int
    mode: GuidanceMode3D
    track_filter_initialized: bool
    track_filter_timestamp_s: float | None
    los_filter_initialized: bool
    ttc_sample_count: int
    visual_stable_frame_count: int
    visual_loss_frame_count: int
    last_visual_command_timestamp_s: float | None


@dataclass(frozen=True)
class _TrackMeasurement3D:
    global_track_id: str
    state: np.ndarray
    covariance: np.ndarray
    timestamp_s: float
    lifecycle_state: str


@dataclass(frozen=True)
class _LosEstimate3D:
    los_unit_ned: np.ndarray
    los_rate_ned_radps: np.ndarray
    valid: bool
    reject_reason: str = ""


@dataclass(frozen=True)
class _TtcEstimate:
    ttc_s: float | None
    valid: bool
    reject_reason: str = ""


class _LosKalmanFilter3D:
    """Delivery-equivalent six-state LOS filter in the NED frame."""

    def __init__(self, config: ScalableGuidanceConfig3D) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self.x = np.zeros(6, dtype=float)
        self.x[0] = 1.0
        self.P = np.eye(6, dtype=float)
        self.initialized = False
        self.last_timestamp_s: float | None = None

    def update(self, timestamp_s: float, measured_los_ned: np.ndarray) -> _LosEstimate3D:
        measurement = _normalize(measured_los_ned)
        if not self.initialized:
            self.x[:3] = measurement
            self.x[3:] = 0.0
            self.P = np.eye(6, dtype=float)
            self.initialized = True
            self.last_timestamp_s = float(timestamp_s)
            return self._estimate(valid=True)

        dt_s = max(
            1.0e-3,
            float(timestamp_s) - float(self.last_timestamp_s or timestamp_s),
        )
        self.last_timestamp_s = float(timestamp_s)
        F = np.eye(6, dtype=float)
        F[:3, 3:] = dt_s * np.eye(3, dtype=float)
        Q = np.diag(
            [
                self.config.los_process_lambda,
                self.config.los_process_lambda,
                self.config.los_process_lambda,
                self.config.los_process_lambda_dot,
                self.config.los_process_lambda_dot,
                self.config.los_process_lambda_dot,
            ]
        )
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q
        self._apply_constraints()

        H = np.zeros((3, 6), dtype=float)
        H[:, :3] = np.eye(3, dtype=float)
        innovation = measurement - H @ self.x
        if float(np.linalg.norm(innovation)) > self.config.los_innovation_reject:
            return self._estimate(valid=False, reject_reason="los_innovation_reject")
        R = self.config.los_measurement_noise * np.eye(3, dtype=float)
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ innovation
        self.P = (np.eye(6, dtype=float) - K @ H) @ self.P
        self._apply_constraints()
        return self._estimate(valid=True)

    def _apply_constraints(self) -> None:
        los = _normalize(self.x[:3])
        self.x[:3] = los
        self.x[3:] = _project_perpendicular(self.x[3:], los)

    def _estimate(self, *, valid: bool, reject_reason: str = "") -> _LosEstimate3D:
        los = _normalize(self.x[:3])
        los_rate = _project_perpendicular(self.x[3:], los)
        return _LosEstimate3D(los, los_rate, valid, reject_reason)


class _ScaleExpansionTtc3D:
    """Delivery-equivalent bbox scale-expansion TTC estimator."""

    def __init__(self, config: ScalableGuidanceConfig3D) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self.filtered_area: float | None = None
        self.previous_raw_area: float | None = None
        self.window: deque[tuple[float, float]] = deque(maxlen=self.config.ttc_window_size)

    def update(self, observation: TerminalVisualObservation3D) -> _TtcEstimate:
        area = observation.area_px2
        if area < self.config.ttc_min_area_px2:
            return _TtcEstimate(None, False, "bbox_area_too_small")
        if observation.clipped:
            return _TtcEstimate(None, False, "bbox_clipped")
        if self.previous_raw_area is not None:
            ratio = max(area, self.previous_raw_area) / max(
                EPS, min(area, self.previous_raw_area)
            )
            if ratio > self.config.ttc_max_area_jump_ratio:
                self.previous_raw_area = area
                return _TtcEstimate(None, False, "bbox_area_jump")
        self.previous_raw_area = area
        if self.filtered_area is None:
            self.filtered_area = area
        else:
            alpha = self.config.ttc_area_filter_alpha
            self.filtered_area = alpha * area + (1.0 - alpha) * self.filtered_area
        self.window.append((observation.timestamp_s, self.filtered_area))
        slope = _window_slope(self.window)
        if slope is None or slope <= self.config.ttc_min_area_dot_px2_s:
            return _TtcEstimate(None, False, "area_not_expanding")
        ttc_s = 2.0 * self.filtered_area / slope
        if not np.isfinite(ttc_s) or ttc_s <= 0.0 or ttc_s > self.config.ttc_max_s:
            return _TtcEstimate(None, False, "ttc_out_of_range")
        return _TtcEstimate(float(ttc_s), True)


@dataclass
class _PairState:
    resource_id: str
    assigned_global_track_id: str
    plan_id: str
    plan_version: int
    los_filter: _LosKalmanFilter3D
    ttc_filter: _ScaleExpansionTtc3D
    mode: GuidanceMode3D = GuidanceMode3D.HOLD
    track_position_ned: np.ndarray | None = None
    track_velocity_ned: np.ndarray | None = None
    track_filter_timestamp_s: float | None = None
    track_covariance_trace: float | None = None
    local_track_id: str | None = None
    visual_stable_frame_count: int = 0
    visual_loss_frame_count: int = 0
    last_visual_command_timestamp_s: float | None = None
    visual_command_samples: deque[tuple[float, np.ndarray]] = field(default_factory=deque)

    def reset_visual(self) -> None:
        self.los_filter.reset()
        self.ttc_filter.reset()
        self.local_track_id = None
        self.visual_stable_frame_count = 0
        self.visual_loss_frame_count = 0
        self.last_visual_command_timestamp_s = None
        self.visual_command_samples.clear()


class ScalableGuidanceController3D:
    """Stateful deterministic controller with one state bundle per D3 pair."""

    def __init__(self, config: ScalableGuidanceConfig3D | None = None) -> None:
        self.config = config or ScalableGuidanceConfig3D()
        self._pair_states: dict[tuple[str, str], _PairState] = {}

    def reset(self) -> None:
        self._pair_states.clear()

    def reset_pair(self, resource_id: str, assigned_global_track_id: str) -> None:
        self._pair_states.pop((str(resource_id), str(assigned_global_track_id)), None)

    def pair_state(
        self,
        resource_id: str,
        assigned_global_track_id: str,
    ) -> PairGuidanceStateSnapshot3D | None:
        state = self._pair_states.get((str(resource_id), str(assigned_global_track_id)))
        if state is None:
            return None
        return PairGuidanceStateSnapshot3D(
            resource_id=state.resource_id,
            assigned_global_track_id=state.assigned_global_track_id,
            plan_id=state.plan_id,
            plan_version=state.plan_version,
            mode=state.mode,
            track_filter_initialized=state.track_position_ned is not None,
            track_filter_timestamp_s=state.track_filter_timestamp_s,
            los_filter_initialized=state.los_filter.initialized,
            ttc_sample_count=len(state.ttc_filter.window),
            visual_stable_frame_count=state.visual_stable_frame_count,
            visual_loss_frame_count=state.visual_loss_frame_count,
            last_visual_command_timestamp_s=state.last_visual_command_timestamp_s,
        )

    def command_batch(
        self,
        pair_inputs: Iterable[AssignmentPairGuidanceInput3D],
        *,
        resource_count: int,
    ) -> GuidanceBatch3D:
        """Return a full resource-indexed command array with zero-filled gaps."""

        if resource_count <= 0:
            raise ValueError("resource_count must be positive")
        inputs = sorted(
            tuple(pair_inputs),
            key=lambda item: (int(item.resource_index), str(_value(item.binding, "resource_id", ""))),
        )
        commands = np.zeros((resource_count, 3), dtype=float)
        outputs: list[GuidanceCommand3D] = []
        used_indices: set[int] = set()
        for pair_input in inputs:
            index = int(pair_input.resource_index)
            if not 0 <= index < resource_count:
                raise IndexError("resource_index out of range")
            if index in used_indices:
                raise ValueError("each resource_index may appear at most once per batch")
            used_indices.add(index)
            output = self.command_pair(pair_input)
            commands[index] = np.asarray(output.acceleration_ned_mps2, dtype=float)
            outputs.append(output)
        return GuidanceBatch3D(commands, tuple(outputs))

    def command_pair(self, pair_input: AssignmentPairGuidanceInput3D) -> GuidanceCommand3D:
        """Evaluate one pair without changing any upstream object or identity."""

        timestamp_s = float(pair_input.timestamp_s)
        if not np.isfinite(timestamp_s) or timestamp_s < 0.0:
            raise ValueError("timestamp_s must be finite and nonnegative")
        resource_state = np.asarray(pair_input.resource_state, dtype=float)
        if resource_state.shape != (6,) or not np.all(np.isfinite(resource_state)):
            raise ValueError("resource_state must be a finite six-dimensional state")
        binding = _coerce_binding(pair_input.binding)
        track = _coerce_global_track(pair_input.global_track)
        permission = coerce_d4_guidance_permission(pair_input.d4_permission)
        key = (binding.resource_id, binding.assigned_global_track_id)

        gate_reason = self._execution_gate_reason(
            pair_input=pair_input,
            binding=binding,
            track=track,
            permission=permission,
        )
        if gate_reason:
            state = self._pair_states.get(key)
            if state is not None:
                state.reset_visual()
            return self._hold_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                gate_reason=gate_reason,
            )

        state = self._ensure_pair_state(binding)
        track_reason = self._update_track_filter(state, track)
        if track_reason:
            state.reset_visual()
            return self._hold_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                gate_reason=track_reason,
            )
        assert state.track_position_ned is not None
        assert state.track_velocity_ned is not None
        assert state.track_filter_timestamp_s is not None
        track_age_s = timestamp_s - state.track_filter_timestamp_s
        if track_age_s < -EPS:
            state.reset_visual()
            return self._hold_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                gate_reason="track_timestamp_in_future",
            )
        if track_age_s > self.config.max_track_age_s:
            state.reset_visual()
            return self._hold_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                gate_reason="global_track_stale",
                track_age_s=track_age_s,
            )
        extrapolation_s = min(max(0.0, track_age_s), self.config.max_track_extrapolation_s)
        target_position = state.track_position_ned + state.track_velocity_ned * extrapolation_s
        target_velocity = state.track_velocity_ned.copy()
        relative_position = target_position - resource_state[:3]
        relative_velocity = target_velocity - resource_state[3:]
        geometry = _relative_geometry(relative_position, relative_velocity)
        available_accel = self._available_accel(pair_input.available_accel_mps2)

        if geometry["range_m"] <= self.config.intercept_radius_m:
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.ESTIMATED_INTERCEPT,
                acceleration=np.zeros(3, dtype=float),
                geometry=geometry,
                gate_reason="estimated_range_stop",
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=False,
            )

        midcourse_acceleration, midcourse_saturated = self._position_velocity_pn(
            resource_velocity=resource_state[3:],
            target_velocity=target_velocity,
            geometry=geometry,
            available_accel=available_accel,
        )
        if geometry["range_m"] > self.config.terminal_switch_range_m:
            state.reset_visual()
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.MIDCOURSE_PN,
                acceleration=midcourse_acceleration,
                geometry=geometry,
                gate_reason="terminal_range_not_reached",
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=midcourse_saturated,
            )

        association_reason = _terminal_plan_consistency_reason(
            pair_input.terminal_association,
            binding,
        )
        observation = _coerce_visual_observation(
            pair_input.visual_observation,
            pair_input.terminal_association,
        )
        d5_state = _string_value(pair_input.terminal_association, "decision_state").lower()
        if association_reason:
            state.reset_visual()
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.MIDCOURSE_PN,
                acceleration=midcourse_acceleration,
                geometry=geometry,
                gate_reason=association_reason,
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=midcourse_saturated,
            )

        if observation is None and d5_state == "reacquire":
            return self._coast_or_midcourse(
                pair_input=pair_input,
                binding=binding,
                permission=permission,
                state=state,
                geometry=geometry,
                midcourse_acceleration=midcourse_acceleration,
                midcourse_saturated=midcourse_saturated,
                available_accel=available_accel,
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
            )

        contract = evaluate_terminal_png_contract(
            binding=binding,
            d4_permission=permission,
            terminal_association=pair_input.terminal_association,
            observation=observation,
            timestamp_s=timestamp_s,
            resource_id=binding.resource_id,
        )
        if not contract.allowed:
            state.reset_visual()
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.MIDCOURSE_PN,
                acceleration=midcourse_acceleration,
                geometry=geometry,
                gate_reason=contract.reject_reason,
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=midcourse_saturated,
                terminal_contract_allowed=False,
            )
        if observation is None:
            state.reset_visual()
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.MIDCOURSE_PN,
                acceleration=midcourse_acceleration,
                geometry=geometry,
                gate_reason="visual_observation_missing",
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=midcourse_saturated,
                terminal_contract_allowed=True,
            )

        camera_ok, camera_reason = self._camera_gate(
            pair_input=pair_input,
            binding=binding,
            state=state,
            observation=observation,
        )
        if not camera_ok:
            self._clear_visual_command_history(state)
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.MIDCOURSE_PN,
                acceleration=midcourse_acceleration,
                geometry=geometry,
                gate_reason=camera_reason,
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=midcourse_saturated,
                terminal_contract_allowed=True,
                camera_gate=False,
            )

        los_estimate = state.los_filter.update(
            observation.timestamp_s,
            observation.los_unit_ned(),
        )
        ttc_estimate = state.ttc_filter.update(observation)
        if not los_estimate.valid or not ttc_estimate.valid or ttc_estimate.ttc_s is None:
            reason = los_estimate.reject_reason or ttc_estimate.reject_reason
            self._clear_visual_command_history(state)
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.MIDCOURSE_PN,
                acceleration=midcourse_acceleration,
                geometry=geometry,
                gate_reason=reason,
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=midcourse_saturated,
                terminal_contract_allowed=True,
                camera_gate=True,
                ttc_s=ttc_estimate.ttc_s,
            )

        visual_closing_speed = float(
            np.clip(
                geometry["range_m"] / ttc_estimate.ttc_s,
                self.config.min_closing_speed_mps,
                self.config.max_visual_closing_speed_mps,
            )
        )
        raw_lateral = (
            self.config.terminal_navigation_constant
            * visual_closing_speed
            * los_estimate.los_rate_ned_radps
        )
        available_lateral = min(self.config.max_lateral_accel_mps2, available_accel)
        raw_lateral_norm = float(np.linalg.norm(raw_lateral))
        maneuver_margin = 1.0 - raw_lateral_norm / max(available_lateral, EPS)
        explicit_maneuver_ready = _optional_bool_with_metadata(
            pair_input.terminal_association,
            "maneuver_capable",
        )
        maneuver_ok = bool(
            available_lateral > EPS
            and maneuver_margin >= self.config.min_maneuver_margin
            and explicit_maneuver_ready is not False
        )
        if not maneuver_ok:
            self._clear_visual_command_history(state)
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.MIDCOURSE_PN,
                acceleration=midcourse_acceleration,
                geometry=geometry,
                gate_reason=(
                    "maneuver_capability_unavailable"
                    if explicit_maneuver_ready is False or available_lateral <= EPS
                    else "maneuver_margin_low"
                ),
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=midcourse_saturated,
                terminal_contract_allowed=True,
                camera_gate=True,
                maneuver_gate=False,
                maneuver_margin=maneuver_margin,
                ttc_s=ttc_estimate.ttc_s,
            )

        lateral, lateral_saturated = _clip_norm(raw_lateral, available_lateral)
        longitudinal = self._longitudinal_acceleration(
            los_unit=los_estimate.los_unit_ned,
            resource_velocity=resource_state[3:],
            target_velocity=target_velocity,
        )
        acceleration, total_saturated = _clip_norm(
            lateral + longitudinal,
            available_accel,
        )
        self._record_visual_command(state, timestamp_s, acceleration)
        state.visual_loss_frame_count = 0
        return self._finish_command(
            pair_input=pair_input,
            binding=binding,
            state=state,
            mode=GuidanceMode3D.TERMINAL_VISUAL_PNG,
            acceleration=acceleration,
            geometry={
                **geometry,
                "los_unit": los_estimate.los_unit_ned,
                "los_rate": los_estimate.los_rate_ned_radps,
                "closing_speed_mps": visual_closing_speed,
            },
            gate_reason="",
            track_age_s=track_age_s,
            extrapolation_s=extrapolation_s,
            saturated=lateral_saturated or total_saturated,
            terminal_contract_allowed=True,
            visual_switch_allowed=True,
            camera_gate=True,
            maneuver_gate=True,
            maneuver_margin=maneuver_margin,
            ttc_s=ttc_estimate.ttc_s,
        )

    def _execution_gate_reason(
        self,
        *,
        pair_input: AssignmentPairGuidanceInput3D,
        binding: AssignmentGuidanceBinding,
        track: _TrackMeasurement3D,
        permission: D4GuidancePermission,
    ) -> str:
        if binding.assigned_global_track_id != track.global_track_id:
            return "global_track_id_mismatch"
        if not binding.is_authorized:
            return "assignment_not_authorized"
        if not binding.is_current:
            return "assignment_not_current"
        if binding.plan_id != str(pair_input.active_plan_id):
            return "stale_plan_id"
        if binding.plan_version != int(pair_input.active_plan_version):
            return "stale_plan_version"
        if binding.expires_at_s is not None and pair_input.timestamp_s > binding.expires_at_s:
            return "assignment_expired"
        if track.lifecycle_state in {"lost", "dropped", "deleted"}:
            return "global_track_not_usable"
        if pair_input.d4_permission is None:
            return "d4_permission_missing"
        action = permission.action.lower()
        d4_states = {action, permission.mode.lower(), permission.reason.lower()}
        if permission.requires_human_review:
            return "d4_hold_for_review"
        if d4_states & {
            "hold",
            "hold_for_review",
            "revoke",
            "revoked",
            "request_center_replan",
            "degrade_to_secondary",
            "degrade_to_distributed",
            "reassign",
            "coalition_fallback_unsupported",
        }:
            return "d4_action_not_executable"
        if action not in ALLOWED_D4_ACTIONS:
            return "d4_action_not_executable"
        if permission.new_plan_id is not None and permission.new_plan_id != binding.plan_id:
            return "d4_plan_mismatch"
        if (
            permission.new_plan_version is not None
            and permission.new_plan_version != binding.plan_version
        ):
            return "d4_plan_mismatch"
        if action != "request_secondary_assist" and permission.target_node_id is not None:
            if binding.owner_node_id is None:
                return "d4_owner_missing"
            if permission.target_node_id != binding.owner_node_id:
                return "d4_owner_mismatch"
        return ""

    def _ensure_pair_state(self, binding: AssignmentGuidanceBinding) -> _PairState:
        key = (binding.resource_id, binding.assigned_global_track_id)
        state = self._pair_states.get(key)
        if (
            state is None
            or state.plan_id != binding.plan_id
            or state.plan_version != binding.plan_version
        ):
            state = _PairState(
                resource_id=binding.resource_id,
                assigned_global_track_id=binding.assigned_global_track_id,
                plan_id=binding.plan_id,
                plan_version=binding.plan_version,
                los_filter=_LosKalmanFilter3D(self.config),
                ttc_filter=_ScaleExpansionTtc3D(self.config),
            )
            self._pair_states[key] = state
        return state

    def _update_track_filter(
        self,
        state: _PairState,
        track: _TrackMeasurement3D,
    ) -> str:
        measurement_position = track.state[:3]
        measurement_velocity = track.state[3:]
        timestamp_s = track.timestamp_s
        if state.track_filter_timestamp_s is None:
            state.track_position_ned = measurement_position.copy()
            state.track_velocity_ned = measurement_velocity.copy()
            state.track_filter_timestamp_s = timestamp_s
            state.track_covariance_trace = float(np.trace(track.covariance))
            return ""
        if timestamp_s + EPS < state.track_filter_timestamp_s:
            return "global_track_timestamp_regression"
        if abs(timestamp_s - state.track_filter_timestamp_s) <= EPS:
            state.track_position_ned = measurement_position.copy()
            state.track_velocity_ned = measurement_velocity.copy()
            state.track_covariance_trace = float(np.trace(track.covariance))
            return ""
        assert state.track_position_ned is not None
        assert state.track_velocity_ned is not None
        dt_s = timestamp_s - state.track_filter_timestamp_s
        predicted_position = state.track_position_ned + state.track_velocity_ned * dt_s
        residual = measurement_position - predicted_position
        state.track_position_ned = (
            predicted_position + self.config.track_position_filter_gain * residual
        )
        state.track_velocity_ned = (
            (1.0 - self.config.track_velocity_filter_gain) * state.track_velocity_ned
            + self.config.track_velocity_filter_gain * measurement_velocity
            + self.config.track_residual_velocity_gain * residual / max(dt_s, EPS)
        )
        state.track_filter_timestamp_s = timestamp_s
        state.track_covariance_trace = float(np.trace(track.covariance))
        return ""

    def _position_velocity_pn(
        self,
        *,
        resource_velocity: np.ndarray,
        target_velocity: np.ndarray,
        geometry: Mapping[str, Any],
        available_accel: float,
    ) -> tuple[np.ndarray, bool]:
        lateral_raw = (
            self.config.navigation_constant
            * max(0.0, float(geometry["closing_speed_mps"]))
            * np.asarray(geometry["los_rate"], dtype=float)
        )
        lateral, lateral_saturated = _clip_norm(
            lateral_raw,
            min(self.config.max_lateral_accel_mps2, available_accel),
        )
        longitudinal = self._longitudinal_acceleration(
            los_unit=np.asarray(geometry["los_unit"], dtype=float),
            resource_velocity=resource_velocity,
            target_velocity=target_velocity,
        )
        acceleration, total_saturated = _clip_norm(lateral + longitudinal, available_accel)
        return acceleration, lateral_saturated or total_saturated

    def _longitudinal_acceleration(
        self,
        *,
        los_unit: np.ndarray,
        resource_velocity: np.ndarray,
        target_velocity: np.ndarray,
    ) -> np.ndarray:
        desired_los_speed = (
            float(np.dot(target_velocity, los_unit)) + self.config.desired_closing_speed_mps
        )
        speed_error = desired_los_speed - float(np.dot(resource_velocity, los_unit))
        raw = self.config.speed_response_gain * speed_error * los_unit
        return _clip_norm(raw, self.config.max_longitudinal_accel_mps2)[0]

    def _camera_gate(
        self,
        *,
        pair_input: AssignmentPairGuidanceInput3D,
        binding: AssignmentGuidanceBinding,
        state: _PairState,
        observation: TerminalVisualObservation3D,
    ) -> tuple[bool, str]:
        if (
            observation.assigned_global_track_id is not None
            and observation.assigned_global_track_id != binding.assigned_global_track_id
        ):
            return False, "visual_global_track_id_mismatch"
        if observation.local_track_id is None:
            return False, "camera_recognition_local_track_missing"
        if state.local_track_id == observation.local_track_id:
            state.visual_stable_frame_count += 1
        else:
            state.reset_visual()
            state.local_track_id = observation.local_track_id
            state.visual_stable_frame_count = 1
        explicit_ready = pair_input.camera_recognition_ready
        if explicit_ready is None:
            explicit_ready = _optional_bool_with_metadata(
                pair_input.terminal_association,
                "camera_recognition_ready",
            )
        if explicit_ready is False:
            return False, "camera_recognition_capability_unavailable"
        if observation.detection_confidence < self.config.min_detection_confidence:
            return False, "detection_confidence_low"
        if observation.area_ratio < self.config.min_bbox_area_ratio:
            return False, "bbox_area_too_small"
        if observation.clipped:
            return False, "bbox_clipped"
        visual_latency_s = pair_input.timestamp_s - observation.timestamp_s
        if visual_latency_s < -EPS:
            return False, "visual_timestamp_in_future"
        if visual_latency_s > self.config.max_visual_latency_s:
            return False, "visual_latency_high"
        if state.visual_stable_frame_count < self.config.min_visual_stable_frames:
            return False, "stable_frame_count_low"
        return True, ""

    def _coast_or_midcourse(
        self,
        *,
        pair_input: AssignmentPairGuidanceInput3D,
        binding: AssignmentGuidanceBinding,
        permission: D4GuidancePermission,
        state: _PairState,
        geometry: Mapping[str, Any],
        midcourse_acceleration: np.ndarray,
        midcourse_saturated: bool,
        available_accel: float,
        track_age_s: float,
        extrapolation_s: float,
    ) -> GuidanceCommand3D:
        decision = evaluate_terminal_coast_contract(
            binding=binding,
            d4_permission=permission,
            terminal_association=pair_input.terminal_association,
            observation=None,
            timestamp_s=pair_input.timestamp_s,
            resource_id=binding.resource_id,
        )
        if not decision.allowed or state.last_visual_command_timestamp_s is None:
            state.reset_visual()
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.MIDCOURSE_PN,
                acceleration=midcourse_acceleration,
                geometry=geometry,
                gate_reason=(
                    decision.reject_reason
                    if not decision.allowed
                    else "terminal_coast_measured_lock_not_established"
                ),
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=midcourse_saturated,
            )
        coast_age_s = pair_input.timestamp_s - state.last_visual_command_timestamp_s
        next_loss_count = state.visual_loss_frame_count + 1
        if (
            coast_age_s > self.config.coast_max_duration_s
            or next_loss_count > self.config.coast_max_loss_frames
            or not state.visual_command_samples
        ):
            state.reset_visual()
            return self._finish_command(
                pair_input=pair_input,
                binding=binding,
                state=state,
                mode=GuidanceMode3D.MIDCOURSE_PN,
                acceleration=midcourse_acceleration,
                geometry=geometry,
                gate_reason="terminal_visual_coast_expired",
                track_age_s=track_age_s,
                extrapolation_s=extrapolation_s,
                saturated=midcourse_saturated,
            )
        base = np.mean([sample[1] for sample in state.visual_command_samples], axis=0)
        decay = math.exp(-max(0.0, coast_age_s) / self.config.coast_decay_tau_s)
        acceleration, saturated = _clip_norm(decay * base, available_accel)
        state.visual_loss_frame_count = next_loss_count
        return self._finish_command(
            pair_input=pair_input,
            binding=binding,
            state=state,
            mode=GuidanceMode3D.TERMINAL_VISUAL_COAST,
            acceleration=acceleration,
            geometry=geometry,
            gate_reason="bounded_visual_coast",
            track_age_s=track_age_s,
            extrapolation_s=extrapolation_s,
            saturated=saturated,
            terminal_contract_allowed=True,
            visual_switch_allowed=False,
            using_visual_coast=True,
        )

    def _record_visual_command(
        self,
        state: _PairState,
        timestamp_s: float,
        acceleration: np.ndarray,
    ) -> None:
        state.last_visual_command_timestamp_s = float(timestamp_s)
        state.visual_command_samples.append((float(timestamp_s), acceleration.copy()))
        cutoff = timestamp_s - self.config.coast_command_window_s
        while state.visual_command_samples and state.visual_command_samples[0][0] < cutoff:
            state.visual_command_samples.popleft()

    @staticmethod
    def _clear_visual_command_history(state: _PairState) -> None:
        state.visual_loss_frame_count = 0
        state.last_visual_command_timestamp_s = None
        state.visual_command_samples.clear()

    def _available_accel(self, value: float | None) -> float:
        if value is None:
            return self.config.max_accel_mps2
        value = float(value)
        if not np.isfinite(value) or value < 0.0:
            raise ValueError("available_accel_mps2 must be finite and nonnegative")
        return min(value, self.config.max_accel_mps2)

    def _hold_command(
        self,
        *,
        pair_input: AssignmentPairGuidanceInput3D,
        binding: AssignmentGuidanceBinding,
        state: _PairState | None,
        gate_reason: str,
        track_age_s: float | None = None,
    ) -> GuidanceCommand3D:
        previous_mode = None if state is None else state.mode.value
        transition = state is not None and state.mode != GuidanceMode3D.HOLD
        if state is not None:
            state.mode = GuidanceMode3D.HOLD
        return GuidanceCommand3D(
            timestamp_s=float(pair_input.timestamp_s),
            resource_index=int(pair_input.resource_index),
            resource_id=binding.resource_id,
            assigned_global_track_id=binding.assigned_global_track_id,
            plan_id=binding.plan_id,
            plan_version=binding.plan_version,
            mode=GuidanceMode3D.HOLD,
            acceleration_ned_mps2=(0.0, 0.0, 0.0),
            range_m=None,
            closing_speed_mps=None,
            los_unit_ned=(0.0, 0.0, 0.0),
            los_rate_ned_radps=(0.0, 0.0, 0.0),
            command_norm_mps2=0.0,
            command_saturated=False,
            gate_reason=gate_reason,
            track_age_s=track_age_s,
            mode_transition=transition,
            previous_mode=previous_mode,
            metadata=_command_metadata(),
        )

    def _finish_command(
        self,
        *,
        pair_input: AssignmentPairGuidanceInput3D,
        binding: AssignmentGuidanceBinding,
        state: _PairState,
        mode: GuidanceMode3D,
        acceleration: np.ndarray,
        geometry: Mapping[str, Any],
        gate_reason: str,
        track_age_s: float,
        extrapolation_s: float,
        saturated: bool,
        terminal_contract_allowed: bool = False,
        visual_switch_allowed: bool = False,
        camera_gate: bool | None = None,
        maneuver_gate: bool | None = None,
        maneuver_margin: float | None = None,
        ttc_s: float | None = None,
        using_visual_coast: bool = False,
    ) -> GuidanceCommand3D:
        acceleration = np.asarray(acceleration, dtype=float).reshape(3)
        if not np.all(np.isfinite(acceleration)):
            acceleration = np.zeros(3, dtype=float)
            mode = GuidanceMode3D.HOLD
            gate_reason = "nonfinite_command_blocked"
        previous_mode = state.mode.value
        transition = state.mode != mode
        state.mode = mode
        los = np.asarray(geometry["los_unit"], dtype=float)
        los_rate = np.asarray(geometry["los_rate"], dtype=float)
        return GuidanceCommand3D(
            timestamp_s=float(pair_input.timestamp_s),
            resource_index=int(pair_input.resource_index),
            resource_id=binding.resource_id,
            assigned_global_track_id=binding.assigned_global_track_id,
            plan_id=binding.plan_id,
            plan_version=binding.plan_version,
            mode=mode,
            acceleration_ned_mps2=tuple(float(v) for v in acceleration),
            range_m=float(geometry["range_m"]),
            closing_speed_mps=float(geometry["closing_speed_mps"]),
            los_unit_ned=tuple(float(v) for v in los),
            los_rate_ned_radps=tuple(float(v) for v in los_rate),
            command_norm_mps2=float(np.linalg.norm(acceleration)),
            command_saturated=bool(saturated),
            gate_reason=gate_reason,
            terminal_contract_allowed=terminal_contract_allowed,
            visual_switch_allowed=visual_switch_allowed,
            camera_recognition_gate_passed=camera_gate,
            maneuver_gate_passed=maneuver_gate,
            maneuver_margin=maneuver_margin,
            ttc_s=ttc_s,
            track_age_s=track_age_s,
            track_extrapolation_s=extrapolation_s,
            using_visual_coast=using_visual_coast,
            visual_loss_frame_count=state.visual_loss_frame_count,
            mode_transition=transition,
            previous_mode=previous_mode,
            metadata={
                **_command_metadata(),
                "track_covariance_trace": state.track_covariance_trace,
            },
        )


def _coerce_binding(value: Any) -> AssignmentGuidanceBinding:
    try:
        binding = coerce_assignment_guidance_binding(value)
        source_node_id = _string_value(value, "source_node_id")
        if binding.owner_node_id is None and source_node_id:
            binding = replace(binding, owner_node_id=source_node_id)
        return binding
    except (TypeError, ValueError):
        pass
    plan_version = _required_int(value, "plan_version")
    binding_state = _string_value(value, "binding_state", "active").lower()
    validity = _string_value(value, "assignment_validity_state", "")
    if not validity:
        validity = "current" if binding_state == "active" else binding_state
    metadata = dict(_value(value, "metadata", {}) or {})
    return AssignmentGuidanceBinding(
        plan_id=_required_string(value, "plan_id"),
        plan_version=plan_version,
        resource_id=_required_string(value, "resource_id"),
        vehicle_name=_string_value(value, "vehicle_name")
        or _required_string(value, "resource_id"),
        assigned_global_track_id=(
            _string_value(value, "assigned_global_track_id")
            or _required_string(value, "target_id")
        ),
        track_version=int(_value(value, "track_version", plan_version)),
        authorization_state=_string_value(value, "authorization_state", "required"),
        owner_node_id=(
            _string_value(value, "owner_node_id")
            or _string_value(value, "source_node_id")
            or None
        ),
        assignment_id=(
            _string_value(value, "assignment_id")
            or _string_value(value, "binding_id")
            or None
        ),
        assignment_validity_state=validity,
        created_at_s=float(
            _value(value, "created_at_s", _value(value, "created_at", 0.0))
        ),
        expires_at_s=_optional_float(value, "expires_at_s"),
        coalition_id=_optional_string(value, "coalition_id"),
        coalition_version=_optional_int(value, "coalition_version"),
        member_role=_string_value(value, "member_role", "primary"),
        wave_id=int(_value(value, "wave_id", 0)),
        coordination_mode=_string_value(value, "coordination_mode", "independent"),
        arrival_window_start_s=_optional_float(value, "arrival_window_start_s"),
        arrival_window_end_s=_optional_float(value, "arrival_window_end_s"),
        activation_state=_string_value(value, "activation_state", "active"),
        activation_plan_version=_optional_int(value, "activation_plan_version"),
        activation_track_version=_optional_int(value, "activation_track_version"),
        activation_coalition_version=_optional_int(value, "activation_coalition_version"),
        terminal_authorization_scope=_string_value(
            value,
            "terminal_authorization_scope",
            str(metadata.get("terminal_authorization_scope", "coalition")),
        ),
        arrival_coordination_required=bool(
            _value(
                value,
                "arrival_coordination_required",
                metadata.get("arrival_coordination_required", True),
            )
        ),
        metadata=metadata,
    )


def _coerce_global_track(value: Any) -> _TrackMeasurement3D:
    global_track_id = _required_string(value, "global_track_id")
    raw_state = _value(value, "state", None)
    if raw_state is None:
        position = np.asarray(_value(value, "position", None), dtype=float).reshape(-1)
        velocity = np.asarray(_value(value, "velocity", None), dtype=float).reshape(-1)
        if position.shape != (3,) or velocity.shape != (3,):
            raise ValueError("GlobalTrack must expose a six-state vector or 3D position/velocity")
        state = np.concatenate((position, velocity))
    else:
        state = np.asarray(raw_state, dtype=float).reshape(-1)
    if state.shape != (6,) or not np.all(np.isfinite(state)):
        raise ValueError("GlobalTrack.state must be finite with shape (6,)")
    covariance = np.asarray(_value(value, "covariance", None), dtype=float)
    if covariance.shape != (6, 6) or not np.all(np.isfinite(covariance)):
        raise ValueError("GlobalTrack.covariance must be finite with shape (6, 6)")
    timestamp_s = float(
        _value(value, "timestamp", _value(value, "measurement_timestamp", math.nan))
    )
    if not np.isfinite(timestamp_s) or timestamp_s < 0.0:
        raise ValueError("GlobalTrack timestamp must be finite and nonnegative")
    lifecycle = _value(value, "lifecycle_state", "confirmed")
    if hasattr(lifecycle, "value"):
        lifecycle = lifecycle.value
    return _TrackMeasurement3D(
        global_track_id=global_track_id,
        state=state.copy(),
        covariance=covariance.copy(),
        timestamp_s=timestamp_s,
        lifecycle_state=str(lifecycle).strip().lower(),
    )


def _coerce_visual_observation(
    value: Any | None,
    terminal_association: Any | None,
) -> TerminalVisualObservation3D | None:
    if isinstance(value, TerminalVisualObservation3D):
        return value
    payload = value
    association_metadata = _value(terminal_association, "metadata", {}) or {}
    if payload is None and isinstance(association_metadata, Mapping):
        payload = association_metadata.get("visual_observation")
        if payload is None and "bbox_xyxy" in association_metadata:
            payload = association_metadata
    if payload is None:
        return None
    geometry = _value(terminal_association, "camera_geometry", None)
    intrinsics = _value(payload, "camera_intrinsics", None)
    if intrinsics is None:
        intrinsics = _value(geometry, "camera_intrinsics", None)
    rotation = _value(payload, "camera_to_ned_rotation", None)
    if rotation is None:
        rotation = _value(geometry, "camera_to_ned_rotation", None)
    timestamp_s = _value(payload, "timestamp_s", None)
    if timestamp_s is None:
        timestamp_s = _value(payload, "exposure_timestamp", None)
    if timestamp_s is None:
        timestamp_s = _value(terminal_association, "exposure_timestamp", None)
    if timestamp_s is None:
        timestamp_s = _value(terminal_association, "measurement_timestamp", None)
    confidence = _value(payload, "detection_confidence", None)
    if confidence is None:
        confidence = _value(terminal_association, "association_confidence", 0.0)
    return TerminalVisualObservation3D(
        timestamp_s=float(timestamp_s),
        bbox_xyxy=tuple(float(v) for v in _value(payload, "bbox_xyxy", ())),
        image_width_px=int(_value(payload, "image_width_px", 0)),
        image_height_px=int(_value(payload, "image_height_px", 0)),
        camera_intrinsics=np.asarray(intrinsics, dtype=float),
        camera_to_ned_rotation=np.asarray(rotation, dtype=float),
        detection_confidence=float(confidence),
        local_track_id=(
            _string_value(payload, "local_track_id")
            or _string_value(terminal_association, "local_track_id")
            or None
        ),
        assigned_global_track_id=(
            _string_value(payload, "assigned_global_track_id")
            or _string_value(terminal_association, "assigned_global_track_id")
            or None
        ),
        camera_id=_string_value(payload, "camera_id") or None,
        metadata=dict(_value(payload, "metadata", {}) or {}),
    )


def _terminal_plan_consistency_reason(
    association: Any | None,
    binding: AssignmentGuidanceBinding,
) -> str:
    if association is None:
        return "d5_terminal_association_missing"
    plan_id = _optional_string_with_metadata(association, "plan_id")
    plan_version = _optional_int_with_metadata(association, "plan_version")
    assignment_version = _optional_int_with_metadata(association, "assignment_version")
    if plan_id is None:
        return "d5_plan_id_missing"
    if plan_id != binding.plan_id:
        return "d5_plan_id_mismatch"
    if plan_version is None:
        return "d5_plan_version_missing"
    if plan_version != binding.plan_version:
        return "d5_plan_version_mismatch"
    if assignment_version is None:
        return "d5_assignment_version_missing"
    if assignment_version != binding.track_version:
        return "d5_assignment_version_mismatch"
    resource_id = _optional_string_with_metadata(association, "resource_id")
    if resource_id is not None and resource_id != binding.resource_id:
        return "d5_resource_mismatch"
    return ""


def _relative_geometry(
    relative_position: np.ndarray,
    relative_velocity: np.ndarray,
) -> dict[str, Any]:
    range_m = float(np.linalg.norm(relative_position))
    if range_m <= EPS:
        return {
            "range_m": range_m,
            "closing_speed_mps": 0.0,
            "los_unit": np.zeros(3, dtype=float),
            "los_rate": np.zeros(3, dtype=float),
        }
    los_unit = relative_position / range_m
    radial_velocity = float(np.dot(relative_velocity, los_unit))
    los_rate = _project_perpendicular(relative_velocity, los_unit) / range_m
    return {
        "range_m": range_m,
        "closing_speed_mps": -radial_velocity,
        "los_unit": los_unit,
        "los_rate": los_rate,
    }


def _clip_norm(vector: np.ndarray, limit: float) -> tuple[np.ndarray, bool]:
    value = np.asarray(vector, dtype=float).reshape(3)
    norm = float(np.linalg.norm(value))
    if limit <= 0.0:
        return np.zeros(3, dtype=float), norm > EPS
    if norm <= limit or norm <= EPS:
        return value.copy(), False
    return value * (limit / norm), True


def _normalize(vector: np.ndarray) -> np.ndarray:
    value = np.asarray(vector, dtype=float).reshape(3)
    norm = float(np.linalg.norm(value))
    if not np.isfinite(norm) or norm <= EPS:
        raise ValueError("cannot normalize a zero or nonfinite vector")
    return value / norm


def _project_perpendicular(vector: np.ndarray, unit: np.ndarray) -> np.ndarray:
    return np.asarray(vector, dtype=float) - unit * float(np.dot(vector, unit))


def _window_slope(window: Iterable[tuple[float, float]]) -> float | None:
    samples = tuple(window)
    if len(samples) < 2:
        return None
    timestamps = np.asarray([sample[0] for sample in samples], dtype=float)
    values = np.asarray([sample[1] for sample in samples], dtype=float)
    timestamps = timestamps - timestamps.mean()
    denominator = float(np.dot(timestamps, timestamps))
    if denominator <= EPS:
        return None
    return float(np.dot(timestamps, values - values.mean()) / denominator)


def _command_metadata() -> dict[str, Any]:
    return {
        "boundary": SCALABLE_3D_GUIDANCE_BOUNDARY,
        "working_frame": "NED",
        "state_contract": "[p_N,p_E,p_D,v_N,v_E,v_D]",
        "existing_planar_png_core_modified": False,
        "end_to_end_rl_used": False,
        "d7_allocates_or_authorizes": False,
        "global_track_id_rebound": False,
    }


def _value(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _metadata_value(value: Any, name: str, default: Any = None) -> Any:
    direct = _value(value, name, None)
    if direct is not None:
        return direct
    metadata = _value(value, "metadata", {}) or {}
    if isinstance(metadata, Mapping):
        return metadata.get(name, default)
    return default


def _string_value(value: Any, name: str, default: str = "") -> str:
    raw = _value(value, name, default)
    if raw is None:
        return default
    return str(raw).strip()


def _required_string(value: Any, name: str) -> str:
    result = _string_value(value, name)
    if not result:
        raise ValueError(f"{name} must be non-empty")
    return result


def _required_int(value: Any, name: str) -> int:
    raw = _value(value, name, None)
    if raw is None:
        raise ValueError(f"{name} is required")
    return int(raw)


def _optional_string(value: Any, name: str) -> str | None:
    result = _string_value(value, name)
    return result or None


def _optional_int(value: Any, name: str) -> int | None:
    raw = _value(value, name, None)
    return None if raw is None else int(raw)


def _optional_float(value: Any, name: str) -> float | None:
    raw = _value(value, name, None)
    return None if raw is None else float(raw)


def _optional_string_with_metadata(value: Any, name: str) -> str | None:
    raw = _metadata_value(value, name, None)
    if raw is None:
        return None
    result = str(raw).strip()
    return result or None


def _optional_int_with_metadata(value: Any, name: str) -> int | None:
    raw = _metadata_value(value, name, None)
    return None if raw is None else int(raw)


def _optional_bool_with_metadata(value: Any, name: str) -> bool | None:
    raw = _metadata_value(value, name, None)
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in {"true", "yes", "1", "ready", "capable"}:
        return True
    if text in {"false", "no", "0", "unready", "incapable", "unavailable"}:
        return False
    return None
