"""Data models for the D7 offline proportional guidance module."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class GuidanceMode(str, Enum):
    """Offline guidance observation mode."""

    RADAR_MIDCOURSE = "radar_midcourse"
    VISION_TERMINAL = "vision_terminal"


@dataclass(frozen=True)
class GuidanceState:
    """Planar point-mass state in SI units."""

    entity_id: str
    timestamp_s: float
    position_m: tuple[float, float]
    velocity_mps: tuple[float, float]
    source: str = "truth"
    covariance_trace: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GuidanceConfig:
    """Configuration for offline two-dimensional PN simulation."""

    dt_s: float = 0.05
    navigation_constant: float = 3.0
    max_lateral_accel_mps2: float = 60.0
    max_turn_rate_radps: float = 0.8
    terminal_switch_range_m: float = 250.0
    terminal_switch_time_s: float | None = None
    max_duration_s: float = 20.0
    min_speed_mps: float = 1e-6
    intercept_radius_m: float = 5.0
    stop_at_intercept_radius: bool = True
    radar_position_noise_m: float = 0.0
    radar_velocity_noise_mps: float = 0.0
    vision_los_noise_rad: float = 0.0
    vision_range_noise_fraction: float = 0.0
    vision_focal_length_px: float = 800.0
    vision_image_center_x_px: float = 640.0
    random_seed: int | None = None

    def __post_init__(self) -> None:
        _require_positive("dt_s", self.dt_s)
        _require_positive("navigation_constant", self.navigation_constant)
        _require_nonnegative("max_lateral_accel_mps2", self.max_lateral_accel_mps2)
        _require_nonnegative("max_turn_rate_radps", self.max_turn_rate_radps)
        _require_positive("terminal_switch_range_m", self.terminal_switch_range_m)
        _require_positive("max_duration_s", self.max_duration_s)
        _require_nonnegative("min_speed_mps", self.min_speed_mps)
        _require_nonnegative("intercept_radius_m", self.intercept_radius_m)
        _require_nonnegative("radar_position_noise_m", self.radar_position_noise_m)
        _require_nonnegative("radar_velocity_noise_mps", self.radar_velocity_noise_mps)
        _require_nonnegative("vision_los_noise_rad", self.vision_los_noise_rad)
        _require_nonnegative("vision_range_noise_fraction", self.vision_range_noise_fraction)
        _require_positive("vision_focal_length_px", self.vision_focal_length_px)
        if self.terminal_switch_time_s is not None:
            _require_nonnegative("terminal_switch_time_s", self.terminal_switch_time_s)


@dataclass(frozen=True)
class GuidanceCommand:
    """Abstract lateral PN command for an offline point-mass update."""

    mode: GuidanceMode
    range_m: float
    los_angle_rad: float
    los_rate_radps: float
    closing_speed_mps: float
    commanded_lateral_accel_mps2: float
    limited_lateral_accel_mps2: float
    commanded_turn_rate_radps: float
    limited_turn_rate_radps: float
    heading_correction_rad: float
    current_heading_rad: float
    desired_heading_rad: float
    acceleration_vector_mps2: tuple[float, float]
    saturated_accel: bool
    saturated_turn_rate: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_saturated(self) -> bool:
        return self.saturated_accel or self.saturated_turn_rate

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        data["is_saturated"] = self.is_saturated
        return data


@dataclass(frozen=True)
class GuidanceRecord:
    """One offline simulation sample with truth, estimate, and PN fields."""

    timestamp_s: float
    resource_id: str
    target_id: str
    mode: GuidanceMode
    range_m: float
    los_angle_rad: float
    los_rate_radps: float
    closing_speed_mps: float
    commanded_lateral_accel_mps2: float
    limited_lateral_accel_mps2: float
    limited_turn_rate_radps: float
    pursuer_position_m: tuple[float, float]
    pursuer_velocity_mps: tuple[float, float]
    target_position_m: tuple[float, float]
    target_velocity_mps: tuple[float, float]
    target_estimated_position_m: tuple[float, float]
    target_estimated_velocity_mps: tuple[float, float]
    observation: dict[str, Any] = field(default_factory=dict)
    mode_switch: bool = False

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data


def _require_positive(name: str, value: float) -> None:
    if value <= 0.0:
        raise ValueError(f"{name} must be positive")


def _require_nonnegative(name: str, value: float) -> None:
    if value < 0.0:
        raise ValueError(f"{name} must be nonnegative")
