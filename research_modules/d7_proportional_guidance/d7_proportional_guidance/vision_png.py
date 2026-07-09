"""Lightweight visual proportional-navigation guidance gates.

This module extracts the reusable, simulation-safe core from the delivered
``png_guidance_delivery`` package.  It keeps only image geometry, LOS quality,
TTC/VM gain scheduling, and SimpleFlight-friendly velocity-heading outputs.
It deliberately excludes PX4 Offboard, body-rate, attitude, YOLO, TensorRT, and
real vehicle control paths.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Literal, Mapping

import numpy as np


PngGuidanceLaw = Literal["los", "png_ttc", "png_vm"]


@dataclass(frozen=True)
class PngGuidanceConfig:
    """Terminal visual guidance gate and gain parameters."""

    dt_s: float = 0.1
    image_width_px: int = 640
    image_height_px: int = 480
    focal_length_px: float = 320.0
    min_bbox_area_ratio: float = 0.0008
    min_detection_confidence: float = 0.55
    min_stable_frames: int = 2
    edge_margin_ratio: float = 0.03
    max_los_rate_variance_radps2: float = 2.0
    los_rate_window: int = 5
    los_rate_filter_alpha: float = 0.45
    max_los_rate_radps: float | None = None
    max_los_rate_step_radps: float | None = None
    reject_los_rate_outliers: bool = True
    max_visual_latency_s: float = 0.35
    navigation_constant: float = 3.0
    min_closing_speed_mps: float = 0.2
    max_turn_rate_radps: float = 0.9
    max_lateral_accel_mps2: float = 20.0
    min_maneuver_margin: float = 0.15
    ttc_fast_s: float = 1.0
    ttc_slow_s: float = 6.0
    ttc_min_gain: float = 0.5
    ttc_max_gain: float = 5.0
    terminal_dwell_frames: int = 1
    terminal_release_frames: int = 1
    terminal_reacquire_grace_frames: int = 0
    law: PngGuidanceLaw = "png_vm"

    def __post_init__(self) -> None:
        if self.dt_s <= 0.0:
            raise ValueError("dt_s must be positive")
        if self.image_width_px <= 0 or self.image_height_px <= 0:
            raise ValueError("image dimensions must be positive")
        if self.focal_length_px <= 0.0:
            raise ValueError("focal_length_px must be positive")
        if self.min_stable_frames < 1:
            raise ValueError("min_stable_frames must be at least one")
        if self.los_rate_window < 2:
            raise ValueError("los_rate_window must be at least two")
        if not 0.0 < self.los_rate_filter_alpha <= 1.0:
            raise ValueError("los_rate_filter_alpha must be in (0, 1]")
        if self.max_los_rate_radps is not None and self.max_los_rate_radps <= 0.0:
            raise ValueError("max_los_rate_radps must be positive when set")
        if self.max_los_rate_step_radps is not None and self.max_los_rate_step_radps <= 0.0:
            raise ValueError("max_los_rate_step_radps must be positive when set")
        if self.max_turn_rate_radps < 0.0 or self.max_lateral_accel_mps2 < 0.0:
            raise ValueError("guidance limits must be nonnegative")
        if self.terminal_dwell_frames < 1:
            raise ValueError("terminal_dwell_frames must be at least one")
        if self.terminal_release_frames < 1:
            raise ValueError("terminal_release_frames must be at least one")
        if self.terminal_reacquire_grace_frames < 0:
            raise ValueError("terminal_reacquire_grace_frames must be nonnegative")
        if self.law not in {"los", "png_ttc", "png_vm"}:
            raise ValueError("law must be one of 'los', 'png_ttc', or 'png_vm'")


@dataclass(frozen=True)
class VisionGuidanceObservation:
    """One terminal image observation for an assigned global target."""

    timestamp_s: float
    bbox_xyxy: tuple[float, float, float, float]
    detection_confidence: float
    local_track_id: str | None = None
    assigned_global_track_id: str | None = None
    camera_id: str | None = None
    frame_timestamp_s: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def center_px(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox_xyxy
        return ((x1 + x2) * 0.5, (y1 + y2) * 0.5)

    @property
    def width_px(self) -> float:
        x1, _y1, x2, _y2 = self.bbox_xyxy
        return max(0.0, float(x2 - x1))

    @property
    def height_px(self) -> float:
        _x1, y1, _x2, y2 = self.bbox_xyxy
        return max(0.0, float(y2 - y1))

    @property
    def area_px2(self) -> float:
        return self.width_px * self.height_px


@dataclass(frozen=True)
class VisionGuidanceQuality:
    """Gate result explaining whether terminal visual PNG is trustworthy."""

    camera_quality_gate_passed: bool
    los_quality_gate_passed: bool
    maneuver_margin_gate_passed: bool
    terminal_switch_allowed: bool
    reject_reason: str = ""
    stable_frame_count: int = 0
    bbox_area_ratio: float = 0.0
    edge_margin_ratio: float = 0.0
    los_angle_rad: float = 0.0
    los_rate_radps: float = 0.0
    raw_los_rate_radps: float = 0.0
    filtered_los_rate_radps: float = 0.0
    los_rate_variance_radps2: float = 0.0
    los_rate_clamped: bool = False
    los_rate_outlier_rejected: bool = False
    closing_speed_mps: float = 0.0
    ttc_s: float | None = None
    required_turn_rate_radps: float = 0.0
    maneuver_margin: float = 0.0


@dataclass(frozen=True)
class PngGuidanceCommand:
    """SimpleFlight-friendly terminal guidance output."""

    guidance_law: PngGuidanceLaw
    heading_rad: float
    turn_rate_radps: float
    velocity_ned: tuple[float, float, float]
    quality: VisionGuidanceQuality
    control_saturated: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class SimpleFlightPngGuidanceFilter:
    """Stateful LOS/TTC estimator for SimpleFlight velocity commands."""

    def __init__(self, config: PngGuidanceConfig | None = None) -> None:
        self.config = config or PngGuidanceConfig()
        self._last_track_id: str | None = None
        self._stable_count = 0
        self._last_los_angle: float | None = None
        self._last_timestamp: float | None = None
        self._filtered_los_rate: float | None = None
        self._area_window: deque[tuple[float, float]] = deque(maxlen=self.config.los_rate_window)
        self._los_rate_window: deque[float] = deque(maxlen=self.config.los_rate_window)

    def reset(self) -> None:
        self._last_track_id = None
        self._stable_count = 0
        self._last_los_angle = None
        self._last_timestamp = None
        self._filtered_los_rate = None
        self._area_window.clear()
        self._los_rate_window.clear()

    def evaluate(
        self,
        observation: VisionGuidanceObservation,
        *,
        current_heading_rad: float,
        current_speed_mps: float,
        intercept_speed_mps: float,
        relative_position_ned: tuple[float, float, float] | np.ndarray | None = None,
        relative_velocity_ned: tuple[float, float, float] | np.ndarray | None = None,
        command_z_ned_m: float = 0.0,
    ) -> PngGuidanceCommand:
        """Evaluate gates and return a bounded horizontal velocity command."""

        cfg = self.config
        track_id = observation.local_track_id or observation.assigned_global_track_id or "__unknown__"
        if track_id == self._last_track_id:
            self._stable_count += 1
        else:
            self._last_track_id = track_id
            self._stable_count = 1

        area_ratio = observation.area_px2 / float(cfg.image_width_px * cfg.image_height_px)
        margin_ratio = _edge_margin_ratio(observation.bbox_xyxy, cfg)
        camera_ok, camera_reason = self._camera_gate(observation, area_ratio, margin_ratio)

        timestamp = float(observation.frame_timestamp_s or observation.timestamp_s)
        los_angle = _wrap_pi(current_heading_rad + _bearing_from_bbox(observation, cfg))
        (
            raw_los_rate,
            filtered_los_rate,
            los_var,
            los_ok,
            los_reason,
            los_rate_clamped,
            los_rate_outlier_rejected,
        ) = self._update_los(timestamp, los_angle)
        ttc_s = self._estimate_ttc(timestamp, observation.area_px2)
        closing_speed = _closing_speed(relative_position_ned, relative_velocity_ned)
        turn_rate_cmd = self._turn_rate_command(
            los_rate=filtered_los_rate,
            ttc_s=ttc_s,
            closing_speed_mps=closing_speed,
        )
        limited_turn_rate = float(np.clip(turn_rate_cmd, -cfg.max_turn_rate_radps, cfg.max_turn_rate_radps))
        control_saturated = abs(limited_turn_rate - turn_rate_cmd) > 1e-9
        required_turn_rate = abs(limited_turn_rate)
        accel_limit_turn = cfg.max_lateral_accel_mps2 / max(abs(current_speed_mps), 1e-6)
        turn_capacity = min(cfg.max_turn_rate_radps, accel_limit_turn)
        maneuver_margin = 1.0 - required_turn_rate / max(turn_capacity, 1e-6)
        maneuver_ok = maneuver_margin >= cfg.min_maneuver_margin
        if closing_speed <= cfg.min_closing_speed_mps and relative_position_ned is not None:
            maneuver_ok = False
            maneuver_reason = "not_closing"
        elif not maneuver_ok:
            maneuver_reason = "maneuver_margin_low"
        else:
            maneuver_reason = ""

        reject_reason = _first_reason(camera_reason, los_reason, maneuver_reason)
        switch_allowed = camera_ok and los_ok and maneuver_ok
        if not switch_allowed:
            # Hold a conservative LOS-centering command while handover waits.
            limited_turn_rate = float(
                np.clip(_wrap_pi(los_angle - current_heading_rad) / cfg.dt_s, -cfg.max_turn_rate_radps, cfg.max_turn_rate_radps)
            )
            control_saturated = True

        heading = _wrap_pi(current_heading_rad + limited_turn_rate * cfg.dt_s)
        speed = max(0.0, float(intercept_speed_mps))
        velocity_ned = (float(speed * math.cos(heading)), float(speed * math.sin(heading)), float(command_z_ned_m))
        quality = VisionGuidanceQuality(
            camera_quality_gate_passed=camera_ok,
            los_quality_gate_passed=los_ok,
            maneuver_margin_gate_passed=maneuver_ok,
            terminal_switch_allowed=switch_allowed,
            reject_reason=reject_reason,
            stable_frame_count=self._stable_count,
            bbox_area_ratio=float(area_ratio),
            edge_margin_ratio=float(margin_ratio),
            los_angle_rad=float(los_angle),
            los_rate_radps=float(filtered_los_rate),
            raw_los_rate_radps=float(raw_los_rate),
            filtered_los_rate_radps=float(filtered_los_rate),
            los_rate_variance_radps2=float(los_var),
            los_rate_clamped=bool(los_rate_clamped),
            los_rate_outlier_rejected=bool(los_rate_outlier_rejected),
            closing_speed_mps=float(closing_speed),
            ttc_s=ttc_s,
            required_turn_rate_radps=float(required_turn_rate),
            maneuver_margin=float(maneuver_margin),
        )
        return PngGuidanceCommand(
            guidance_law=cfg.law,
            heading_rad=float(heading),
            turn_rate_radps=float(limited_turn_rate),
            velocity_ned=velocity_ned,
            quality=quality,
            control_saturated=control_saturated,
            metadata={
                "local_track_id": observation.local_track_id,
                "assigned_global_track_id": observation.assigned_global_track_id,
                "camera_id": observation.camera_id,
                "raw_los_rate_radps": float(raw_los_rate),
                "filtered_los_rate_radps": float(filtered_los_rate),
                "los_rate_clamped": bool(los_rate_clamped),
                "los_rate_outlier_rejected": bool(los_rate_outlier_rejected),
            },
        )

    def _camera_gate(
        self,
        observation: VisionGuidanceObservation,
        area_ratio: float,
        margin_ratio: float,
    ) -> tuple[bool, str]:
        cfg = self.config
        if observation.detection_confidence < cfg.min_detection_confidence:
            return False, "detection_confidence_low"
        if area_ratio < cfg.min_bbox_area_ratio:
            return False, "bbox_area_too_small"
        if margin_ratio < cfg.edge_margin_ratio:
            return False, "bbox_near_image_edge"
        if self._stable_count < cfg.min_stable_frames:
            return False, "stable_frame_count_low"
        latency = float(observation.metadata.get("visual_latency_s", 0.0))
        if latency > cfg.max_visual_latency_s:
            return False, "visual_latency_high"
        return True, ""

    def _update_los(
        self,
        timestamp: float,
        los_angle: float,
    ) -> tuple[float, float, float, bool, str, bool, bool]:
        cfg = self.config
        if self._last_timestamp is None or self._last_los_angle is None:
            self._last_timestamp = timestamp
            self._last_los_angle = los_angle
            self._filtered_los_rate = 0.0
            return 0.0, 0.0, 0.0, False, "los_history_too_short", False, False
        dt = max(1e-6, timestamp - self._last_timestamp)
        raw_los_rate = _wrap_pi(los_angle - self._last_los_angle) / dt
        self._last_timestamp = timestamp
        self._last_los_angle = los_angle

        previous_filtered = self._filtered_los_rate
        if previous_filtered is None:
            filtered_los_rate = float(raw_los_rate)
        else:
            alpha = cfg.los_rate_filter_alpha
            filtered_los_rate = float(alpha * raw_los_rate + (1.0 - alpha) * previous_filtered)

        los_rate_clamped = False
        los_rate_outlier_rejected = False
        if cfg.max_los_rate_step_radps is not None and previous_filtered is not None:
            step = filtered_los_rate - previous_filtered
            if abs(step) > cfg.max_los_rate_step_radps:
                filtered_los_rate = previous_filtered + math.copysign(cfg.max_los_rate_step_radps, step)
                los_rate_clamped = True
                los_rate_outlier_rejected = True
        if cfg.max_los_rate_radps is not None and abs(filtered_los_rate) > cfg.max_los_rate_radps:
            filtered_los_rate = float(np.clip(filtered_los_rate, -cfg.max_los_rate_radps, cfg.max_los_rate_radps))
            los_rate_clamped = True
            if abs(raw_los_rate) > cfg.max_los_rate_radps:
                los_rate_outlier_rejected = True

        self._filtered_los_rate = filtered_los_rate
        self._los_rate_window.append(float(filtered_los_rate))
        if len(self._los_rate_window) < 2:
            return (
                float(raw_los_rate),
                float(filtered_los_rate),
                0.0,
                False,
                "los_rate_window_too_short",
                los_rate_clamped,
                los_rate_outlier_rejected,
            )
        los_var = float(np.var(np.asarray(self._los_rate_window, dtype=float)))
        if los_rate_outlier_rejected and cfg.reject_los_rate_outliers:
            return (
                float(raw_los_rate),
                float(filtered_los_rate),
                los_var,
                False,
                "los_rate_spike_rejected",
                los_rate_clamped,
                los_rate_outlier_rejected,
            )
        if los_var > cfg.max_los_rate_variance_radps2:
            return (
                float(raw_los_rate),
                float(filtered_los_rate),
                los_var,
                False,
                "los_rate_variance_high",
                los_rate_clamped,
                los_rate_outlier_rejected,
            )
        return float(raw_los_rate), float(filtered_los_rate), los_var, True, "", los_rate_clamped, los_rate_outlier_rejected

    def _estimate_ttc(self, timestamp: float, area_px2: float) -> float | None:
        self._area_window.append((float(timestamp), float(area_px2)))
        if len(self._area_window) < 2:
            return None
        t = np.asarray([item[0] for item in self._area_window], dtype=float)
        a = np.asarray([item[1] for item in self._area_window], dtype=float)
        t = t - t.mean()
        denom = float(np.dot(t, t))
        if denom <= 1e-12:
            return None
        area_dot = float(np.dot(t, a - a.mean()) / denom)
        if area_dot <= 1e-6:
            return None
        ttc = 2.0 * float(a[-1]) / area_dot
        if not np.isfinite(ttc) or ttc <= 0.0:
            return None
        return float(ttc)

    def _turn_rate_command(
        self,
        *,
        los_rate: float,
        ttc_s: float | None,
        closing_speed_mps: float,
    ) -> float:
        cfg = self.config
        if cfg.law == "los":
            return float(cfg.navigation_constant * los_rate)
        if cfg.law == "png_ttc":
            gain = _ttc_gain(ttc_s, cfg)
            return float(gain * los_rate)
        vm = max(closing_speed_mps, cfg.min_closing_speed_mps)
        accel_cmd = cfg.navigation_constant * vm * los_rate
        speed_for_turn = max(vm, 1e-6)
        return float(accel_cmd / speed_for_turn)


def terminal_switch_allowed_rate(samples: Iterable[Any]) -> float:
    """Return the fraction of samples whose existing gate result allowed handoff."""

    return float(summarize_terminal_switch_quality(samples)["terminal_switch_allowed_rate"])


def summarize_terminal_switch_quality(samples: Iterable[Any]) -> dict[str, Any]:
    """Summarize already-computed terminal switch quality samples.

    This helper is intentionally passive: it never reruns the camera/LOS/maneuver
    gate and only counts ``terminal_switch_allowed`` values already emitted by
    D7 command/quality objects or persisted metadata dictionaries.
    """

    sample_count = 0
    allowed_count = 0
    reject_reasons: Counter[str] = Counter()
    for sample in samples:
        allowed = _quality_bool(_quality_value(sample, "terminal_switch_allowed"))
        if allowed is None:
            continue
        sample_count += 1
        if allowed:
            allowed_count += 1
        else:
            reason = _quality_text(_quality_value(sample, "reject_reason"))
            if reason is None:
                reason = _quality_text(_quality_value(sample, "terminal_switch_reject_reason"))
            if reason:
                reject_reasons[reason] += 1

    rejected_count = sample_count - allowed_count
    return {
        "sample_count": sample_count,
        "allowed_count": allowed_count,
        "rejected_count": rejected_count,
        "terminal_switch_allowed_rate": allowed_count / sample_count if sample_count else 0.0,
        "reject_reasons": dict(reject_reasons),
    }


def _bearing_from_bbox(observation: VisionGuidanceObservation, cfg: PngGuidanceConfig) -> float:
    center_x, _center_y = observation.center_px
    cx = cfg.image_width_px * 0.5
    return float(math.atan((center_x - cx) / cfg.focal_length_px))


def _quality_value(sample: Any, name: str) -> Any:
    if isinstance(sample, PngGuidanceCommand):
        sample = sample.quality
    if isinstance(sample, Mapping):
        return sample.get(name)
    return getattr(sample, name, None)


def _quality_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"true", "t", "yes", "y", "1", "pass", "passed", "ok"}:
        return True
    if text in {"false", "f", "no", "n", "0", "fail", "failed", "reject", "rejected"}:
        return False
    return None


def _quality_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _edge_margin_ratio(
    bbox_xyxy: tuple[float, float, float, float],
    cfg: PngGuidanceConfig,
) -> float:
    x1, y1, x2, y2 = bbox_xyxy
    margin_px = min(x1, y1, cfg.image_width_px - x2, cfg.image_height_px - y2)
    return float(margin_px / max(1.0, min(cfg.image_width_px, cfg.image_height_px)))


def _closing_speed(
    relative_position_ned: tuple[float, float, float] | np.ndarray | None,
    relative_velocity_ned: tuple[float, float, float] | np.ndarray | None,
) -> float:
    if relative_position_ned is None or relative_velocity_ned is None:
        return 0.0
    r = np.asarray(relative_position_ned, dtype=float).reshape(3)
    v = np.asarray(relative_velocity_ned, dtype=float).reshape(3)
    range_m = float(np.linalg.norm(r))
    if range_m <= 1e-9:
        return 0.0
    return float(-np.dot(r, v) / range_m)


def _ttc_gain(ttc_s: float | None, cfg: PngGuidanceConfig) -> float:
    if ttc_s is None or not np.isfinite(ttc_s):
        return cfg.ttc_min_gain
    if ttc_s <= cfg.ttc_fast_s:
        return cfg.ttc_max_gain
    if ttc_s >= cfg.ttc_slow_s:
        return cfg.ttc_min_gain
    span = cfg.ttc_slow_s - cfg.ttc_fast_s
    x = (cfg.ttc_slow_s - ttc_s) / span
    smooth = 0.5 - 0.5 * math.cos(math.pi * x)
    return float(cfg.ttc_min_gain + (cfg.ttc_max_gain - cfg.ttc_min_gain) * smooth)


def _first_reason(*reasons: str) -> str:
    for reason in reasons:
        if reason:
            return reason
    return ""


def _wrap_pi(angle_rad: float) -> float:
    return (angle_rad + math.pi) % (2.0 * math.pi) - math.pi
