"""Classical two-dimensional proportional navigation calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Iterable

import numpy as np

from .models import GuidanceCommand, GuidanceMode, GuidanceState


EPS = 1e-9


@dataclass(frozen=True)
class ThreeDimensionalPnBenchmark:
    """Advisory 3D geometry PN fields that do not replace the default 2D API."""

    range_3d_m: float
    horizontal_range_m: float
    height_delta_m: float
    closing_speed_mps: float
    los_rate_norm_radps: float
    los_rate_vector_ned: tuple[float, float, float]
    commanded_accel_vector_ned_mps2: tuple[float, float, float]
    commanded_accel_norm_mps2: float
    navigation_constant: float
    benchmark_only: bool = True
    default_pn_png_api_replaced: bool = False
    d3_d4_d5_gate_bypassed: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def compute_proportional_navigation_command(
    pursuer: GuidanceState,
    target: GuidanceState,
    dt_s: float,
    navigation_constant: float,
    mode: GuidanceMode | str = GuidanceMode.RADAR_MIDCOURSE,
    max_lateral_accel_mps2: float | None = None,
    max_turn_rate_radps: float | None = None,
    min_speed_mps: float = EPS,
) -> GuidanceCommand:
    """Compute a classical planar PN command in SI units.

    The formula uses lambda_dot from planar relative geometry and computes
    a_n = N * V_c * lambda_dot. The returned command is an abstract offline
    point-mass command, not a vehicle or actuator interface.
    """

    if dt_s <= 0.0:
        raise ValueError("dt_s must be positive")
    if navigation_constant <= 0.0:
        raise ValueError("navigation_constant must be positive")
    if max_lateral_accel_mps2 is not None and max_lateral_accel_mps2 < 0.0:
        raise ValueError("max_lateral_accel_mps2 must be nonnegative")
    if max_turn_rate_radps is not None and max_turn_rate_radps < 0.0:
        raise ValueError("max_turn_rate_radps must be nonnegative")

    guidance_mode = _coerce_mode(mode)
    pursuer_position = _xy_array(pursuer.position_m)
    pursuer_velocity = _xy_array(pursuer.velocity_mps)
    target_position = _xy_array(target.position_m)
    target_velocity = _xy_array(target.velocity_mps)

    relative_position = target_position - pursuer_position
    relative_velocity = target_velocity - pursuer_velocity
    range_m = float(np.linalg.norm(relative_position))

    if range_m <= EPS:
        los_angle_rad = 0.0
        los_rate_radps = 0.0
        closing_speed_mps = 0.0
    else:
        los_angle_rad = math.atan2(float(relative_position[1]), float(relative_position[0]))
        los_rate_radps = float(_cross2(relative_position, relative_velocity) / (range_m * range_m))
        closing_speed_mps = float(-np.dot(relative_position, relative_velocity) / range_m)

    speed_mps = float(np.linalg.norm(pursuer_velocity))
    if speed_mps > min_speed_mps:
        current_heading_rad = math.atan2(float(pursuer_velocity[1]), float(pursuer_velocity[0]))
    else:
        current_heading_rad = los_angle_rad

    commanded_lateral_accel_mps2 = (
        navigation_constant * closing_speed_mps * los_rate_radps
    )
    commanded_turn_rate_radps = _safe_turn_rate(
        commanded_lateral_accel_mps2,
        speed_mps,
        min_speed_mps,
    )

    accel_limited = _clip_optional(
        commanded_lateral_accel_mps2,
        max_lateral_accel_mps2,
    )
    turn_from_accel_limit = _safe_turn_rate(accel_limited, speed_mps, min_speed_mps)
    limited_turn_rate_radps = _clip_optional(
        turn_from_accel_limit,
        max_turn_rate_radps,
    )
    limited_lateral_accel_mps2 = limited_turn_rate_radps * speed_mps

    heading_correction_rad = limited_turn_rate_radps * dt_s
    desired_heading_rad = _wrap_pi(current_heading_rad + heading_correction_rad)
    acceleration_vector = _lateral_accel_vector(
        pursuer_velocity,
        limited_lateral_accel_mps2,
        speed_mps,
        min_speed_mps,
    )

    saturated_accel = abs(accel_limited - commanded_lateral_accel_mps2) > 1e-9
    saturated_turn_rate = abs(limited_turn_rate_radps - turn_from_accel_limit) > 1e-9

    return GuidanceCommand(
        mode=guidance_mode,
        range_m=range_m,
        los_angle_rad=los_angle_rad,
        los_rate_radps=los_rate_radps,
        closing_speed_mps=closing_speed_mps,
        commanded_lateral_accel_mps2=commanded_lateral_accel_mps2,
        limited_lateral_accel_mps2=limited_lateral_accel_mps2,
        commanded_turn_rate_radps=commanded_turn_rate_radps,
        limited_turn_rate_radps=limited_turn_rate_radps,
        heading_correction_rad=heading_correction_rad,
        current_heading_rad=current_heading_rad,
        desired_heading_rad=desired_heading_rad,
        acceleration_vector_mps2=(
            float(acceleration_vector[0]),
            float(acceleration_vector[1]),
        ),
        saturated_accel=saturated_accel,
        saturated_turn_rate=saturated_turn_rate,
        metadata={
            "navigation_constant": float(navigation_constant),
            "dt_s": float(dt_s),
            "pursuer_speed_mps": speed_mps,
            "target_source": target.source,
        },
    )


compute_pn_command = compute_proportional_navigation_command


def compute_three_dimensional_pn_benchmark(
    *,
    relative_position_ned: tuple[float, float, float] | np.ndarray,
    relative_velocity_ned: tuple[float, float, float] | np.ndarray,
    navigation_constant: float,
) -> ThreeDimensionalPnBenchmark:
    """Compute report-only 3D PN geometry from relative NED state.

    This helper is intentionally benchmark/advisory only.  It does not change
    ``compute_proportional_navigation_command()``, does not emit a vehicle
    command, and does not bypass D3/D4/D5 terminal gates.
    """

    if navigation_constant <= 0.0:
        raise ValueError("navigation_constant must be positive")
    r = _xyz_array(relative_position_ned)
    v = _xyz_array(relative_velocity_ned)
    range_3d_m = float(np.linalg.norm(r))
    horizontal_range_m = float(np.linalg.norm(r[:2]))
    height_delta_m = float(r[2])
    if range_3d_m <= EPS:
        los_rate_vector = np.zeros(3, dtype=float)
        closing_speed_mps = 0.0
    else:
        los_unit = r / range_3d_m
        closing_speed_mps = float(-np.dot(los_unit, v))
        los_rate_vector = (v - los_unit * float(np.dot(los_unit, v))) / range_3d_m
    accel_vector = float(navigation_constant * closing_speed_mps) * los_rate_vector
    return ThreeDimensionalPnBenchmark(
        range_3d_m=range_3d_m,
        horizontal_range_m=horizontal_range_m,
        height_delta_m=height_delta_m,
        closing_speed_mps=closing_speed_mps,
        los_rate_norm_radps=float(np.linalg.norm(los_rate_vector)),
        los_rate_vector_ned=(
            float(los_rate_vector[0]),
            float(los_rate_vector[1]),
            float(los_rate_vector[2]),
        ),
        commanded_accel_vector_ned_mps2=(
            float(accel_vector[0]),
            float(accel_vector[1]),
            float(accel_vector[2]),
        ),
        commanded_accel_norm_mps2=float(np.linalg.norm(accel_vector)),
        navigation_constant=float(navigation_constant),
        metadata={
            "benchmark_guidance_law": "pn_3d_geometry",
            "three_dimensional_guidance_replaces_default": False,
        },
    )


def compute_pure_pursuit_command(
    pursuer: GuidanceState,
    target: GuidanceState,
    dt_s: float,
    mode: GuidanceMode | str = GuidanceMode.RADAR_MIDCOURSE,
    max_turn_rate_radps: float | None = None,
    min_speed_mps: float = EPS,
) -> GuidanceCommand:
    """Compute a simple planar pure-pursuit heading command.

    The command points the pursuer toward the current estimated target
    position. It is intentionally a lightweight baseline and does not import
    PythonRobotics or any external path-tracking package.
    """

    if dt_s <= 0.0:
        raise ValueError("dt_s must be positive")
    if max_turn_rate_radps is not None and max_turn_rate_radps < 0.0:
        raise ValueError("max_turn_rate_radps must be nonnegative")

    guidance_mode = _coerce_mode(mode)
    pursuer_position = _xy_array(pursuer.position_m)
    pursuer_velocity = _xy_array(pursuer.velocity_mps)
    target_position = _xy_array(target.position_m)
    target_velocity = _xy_array(target.velocity_mps)

    relative_position = target_position - pursuer_position
    relative_velocity = target_velocity - pursuer_velocity
    range_m = float(np.linalg.norm(relative_position))
    los_angle_rad = 0.0 if range_m <= EPS else math.atan2(float(relative_position[1]), float(relative_position[0]))
    los_rate_radps = 0.0 if range_m <= EPS else float(_cross2(relative_position, relative_velocity) / (range_m * range_m))
    closing_speed_mps = 0.0 if range_m <= EPS else float(-np.dot(relative_position, relative_velocity) / range_m)

    speed_mps = float(np.linalg.norm(pursuer_velocity))
    current_heading_rad = (
        math.atan2(float(pursuer_velocity[1]), float(pursuer_velocity[0]))
        if speed_mps > min_speed_mps
        else los_angle_rad
    )
    heading_error_rad = _wrap_pi(los_angle_rad - current_heading_rad)
    commanded_turn_rate_radps = heading_error_rad / dt_s
    limited_turn_rate_radps = _clip_optional(commanded_turn_rate_radps, max_turn_rate_radps)
    desired_heading_rad = _wrap_pi(current_heading_rad + limited_turn_rate_radps * dt_s)
    limited_lateral_accel_mps2 = limited_turn_rate_radps * speed_mps
    acceleration_vector = _lateral_accel_vector(
        pursuer_velocity,
        limited_lateral_accel_mps2,
        speed_mps,
        min_speed_mps,
    )

    return GuidanceCommand(
        mode=guidance_mode,
        range_m=range_m,
        los_angle_rad=los_angle_rad,
        los_rate_radps=los_rate_radps,
        closing_speed_mps=closing_speed_mps,
        commanded_lateral_accel_mps2=commanded_turn_rate_radps * speed_mps,
        limited_lateral_accel_mps2=limited_lateral_accel_mps2,
        commanded_turn_rate_radps=commanded_turn_rate_radps,
        limited_turn_rate_radps=limited_turn_rate_radps,
        heading_correction_rad=limited_turn_rate_radps * dt_s,
        current_heading_rad=current_heading_rad,
        desired_heading_rad=desired_heading_rad,
        acceleration_vector_mps2=(float(acceleration_vector[0]), float(acceleration_vector[1])),
        saturated_accel=False,
        saturated_turn_rate=abs(limited_turn_rate_radps - commanded_turn_rate_radps) > 1e-9,
        metadata={
            "guidance_law": "pure_pursuit",
            "dt_s": float(dt_s),
            "pursuer_speed_mps": speed_mps,
            "target_source": target.source,
            "heading_error_rad": heading_error_rad,
        },
    )


def _coerce_mode(mode: GuidanceMode | str) -> GuidanceMode:
    if isinstance(mode, GuidanceMode):
        return mode
    return GuidanceMode(str(mode))


def _xy_array(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(tuple(values), dtype=float)
    if array.shape != (2,):
        raise ValueError("state vectors must contain exactly two values")
    return array


def _xyz_array(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(tuple(values), dtype=float)
    if array.shape != (3,):
        raise ValueError("3D state vectors must contain exactly three values")
    return array


def _cross2(left: np.ndarray, right: np.ndarray) -> float:
    return float(left[0] * right[1] - left[1] * right[0])


def _clip_optional(value: float, limit: float | None) -> float:
    if limit is None:
        return float(value)
    return float(np.clip(value, -limit, limit))


def _safe_turn_rate(accel_mps2: float, speed_mps: float, min_speed_mps: float) -> float:
    if speed_mps <= min_speed_mps:
        return 0.0
    return float(accel_mps2 / speed_mps)


def _lateral_accel_vector(
    velocity_mps: np.ndarray,
    lateral_accel_mps2: float,
    speed_mps: float,
    min_speed_mps: float,
) -> np.ndarray:
    if speed_mps <= min_speed_mps:
        return np.zeros(2, dtype=float)
    unit_velocity = velocity_mps / speed_mps
    normal_left = np.array([-unit_velocity[1], unit_velocity[0]], dtype=float)
    return normal_left * lateral_accel_mps2


def _wrap_pi(angle_rad: float) -> float:
    return (angle_rad + math.pi) % (2.0 * math.pi) - math.pi
