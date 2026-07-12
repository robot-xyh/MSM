"""Isolated P2 point-mass/replay benchmarks for three-dimensional guidance.

These APIs are deliberately separate from the D7 runtime selector and the
validated planar PN/visual PNG implementation.  They never emit vehicle
commands and never bypass D3/D4/D5 contracts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import math
from statistics import mean
from time import perf_counter
from typing import Any, Iterable, Sequence

import numpy as np


P2_OPTIONAL_BENCHMARK_BOUNDARY = (
    "d7_p2_optional_offline_point_mass_replay_no_runtime_control"
)


class OptionalP2GuidanceLaw(str, Enum):
    """Research-only laws available to the isolated P2 benchmark."""

    PN_3D = "pn_3d"
    TRUE_PN = "true_pn"
    APN = "apn"
    FRPN_APPROX = "frpn_research_approximation"


DEFAULT_OPTIONAL_P2_LAWS = tuple(OptionalP2GuidanceLaw)


@dataclass(frozen=True)
class OptionalP2BenchmarkConfig:
    """Configuration for the isolated constant-speed 3D point-mass model."""

    dt_s: float = 0.02
    max_duration_s: float = 12.0
    navigation_constant: float = 3.0
    max_acceleration_mps2: float = 60.0
    intercept_radius_m: float = 5.0
    pursuer_initial_position_ned_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    pursuer_initial_velocity_ned_mps: tuple[float, float, float] = (180.0, 0.0, 0.0)
    target_initial_position_ned_m: tuple[float, float, float] = (1200.0, 150.0, 100.0)
    target_initial_velocity_ned_mps: tuple[float, float, float] = (-20.0, 0.0, 0.0)
    target_lateral_acceleration_mps2: float = 4.0
    target_vertical_acceleration_mps2: float = 1.5
    apn_feedforward_gain: float = 0.5
    frpn_los_gain: float = 1.5
    frpn_target_accel_gain: float = 0.75
    frpn_los_rate_scale_radps: float = 0.02
    frpn_target_accel_scale_mps2: float = 4.0

    def __post_init__(self) -> None:
        for name in ("dt_s", "max_duration_s", "navigation_constant"):
            if float(getattr(self, name)) <= 0.0:
                raise ValueError(f"{name} must be positive")
        for name in (
            "max_acceleration_mps2",
            "intercept_radius_m",
            "target_lateral_acceleration_mps2",
            "target_vertical_acceleration_mps2",
            "apn_feedforward_gain",
            "frpn_los_gain",
            "frpn_target_accel_gain",
        ):
            if float(getattr(self, name)) < 0.0:
                raise ValueError(f"{name} must be nonnegative")
        if self.frpn_los_rate_scale_radps <= 0.0:
            raise ValueError("frpn_los_rate_scale_radps must be positive")
        if self.frpn_target_accel_scale_mps2 <= 0.0:
            raise ValueError("frpn_target_accel_scale_mps2 must be positive")
        _vector3(self.pursuer_initial_position_ned_m)
        pursuer_velocity = _vector3(self.pursuer_initial_velocity_ned_mps)
        _vector3(self.target_initial_position_ned_m)
        target_velocity = _vector3(self.target_initial_velocity_ned_mps)
        if np.linalg.norm(pursuer_velocity) <= 1e-9:
            raise ValueError("pursuer initial speed must be positive")
        if np.linalg.norm(target_velocity) <= 1e-9:
            raise ValueError("target initial speed must be positive")


@dataclass(frozen=True)
class OptionalP2ReplaySample:
    """One truth/replay target state used only by the offline benchmark."""

    timestamp_s: float
    target_position_ned_m: tuple[float, float, float]
    target_velocity_ned_mps: tuple[float, float, float]
    target_acceleration_ned_mps2: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class OptionalP2BenchmarkResult:
    """Metrics for one law/seed point-mass or replay run."""

    seed: int
    guidance_law: str
    source: str
    hit: bool
    min_miss_distance_m: float
    final_range_m: float
    time_to_intercept_s: float | None
    control_effort_mps: float
    control_energy_m2ps3: float
    peak_acceleration_mps2: float
    compute_time_s: float
    sample_count: int
    research_approximation: bool
    approximation_note: str
    benchmark_only: bool = True
    default_runtime_path_replaced: bool = False
    png_guidance_delivery_modified: bool = False
    d3_d4_d5_gate_bypassed: bool = False
    boundary: str = P2_OPTIONAL_BENCHMARK_BOUNDARY
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_optional_p2_target_replay(
    *,
    seed: int,
    config: OptionalP2BenchmarkConfig | None = None,
) -> tuple[OptionalP2ReplaySample, ...]:
    """Generate a deterministic maneuvering target replay for a fixed seed."""

    cfg = config or OptionalP2BenchmarkConfig()
    rng = np.random.default_rng(int(seed))
    phase_lateral = float(rng.uniform(-math.pi, math.pi))
    phase_vertical = float(rng.uniform(-math.pi, math.pi))
    frequency_hz = float(rng.uniform(0.12, 0.28))
    target_position = _vector3(cfg.target_initial_position_ned_m)
    target_velocity = _vector3(cfg.target_initial_velocity_ned_mps)
    target_speed = float(np.linalg.norm(target_velocity))
    sample_count = int(math.ceil(cfg.max_duration_s / cfg.dt_s)) + 1
    replay: list[OptionalP2ReplaySample] = []

    for index in range(sample_count):
        timestamp_s = index * cfg.dt_s
        target_acceleration = _target_maneuver_acceleration(
            target_velocity,
            timestamp_s=timestamp_s,
            lateral_amplitude=cfg.target_lateral_acceleration_mps2,
            vertical_amplitude=cfg.target_vertical_acceleration_mps2,
            phase_lateral=phase_lateral,
            phase_vertical=phase_vertical,
            frequency_hz=frequency_hz,
        )
        replay.append(
            OptionalP2ReplaySample(
                timestamp_s=timestamp_s,
                target_position_ned_m=_tuple3(target_position),
                target_velocity_ned_mps=_tuple3(target_velocity),
                target_acceleration_ned_mps2=_tuple3(target_acceleration),
            )
        )
        target_velocity = _constant_speed_velocity(
            target_velocity + target_acceleration * cfg.dt_s,
            target_speed,
        )
        target_position = target_position + target_velocity * cfg.dt_s
    return tuple(replay)


def run_optional_p2_point_mass_benchmark(
    *,
    guidance_law: OptionalP2GuidanceLaw | str,
    seed: int,
    config: OptionalP2BenchmarkConfig | None = None,
) -> OptionalP2BenchmarkResult:
    """Run one isolated 3D point-mass benchmark with a generated replay."""

    cfg = config or OptionalP2BenchmarkConfig()
    replay = generate_optional_p2_target_replay(seed=seed, config=cfg)
    return run_optional_p2_replay_benchmark(
        replay,
        guidance_law=guidance_law,
        seed=seed,
        config=cfg,
        source="generated_point_mass",
    )


def run_optional_p2_replay_benchmark(
    replay: Sequence[OptionalP2ReplaySample | dict[str, Any] | Any],
    *,
    guidance_law: OptionalP2GuidanceLaw | str,
    seed: int = 0,
    config: OptionalP2BenchmarkConfig | None = None,
    source: str = "offline_replay",
) -> OptionalP2BenchmarkResult:
    """Run one law against target truth/replay samples without online control."""

    cfg = config or OptionalP2BenchmarkConfig()
    law = _coerce_law(guidance_law)
    samples = tuple(_coerce_replay_sample(sample) for sample in replay)
    _validate_replay(samples)
    pursuer_position = _vector3(cfg.pursuer_initial_position_ned_m)
    pursuer_velocity = _vector3(cfg.pursuer_initial_velocity_ned_mps)
    pursuer_speed = float(np.linalg.norm(pursuer_velocity))
    min_range_m = math.inf
    final_range_m = math.inf
    time_to_intercept_s: float | None = None
    control_effort = 0.0
    control_energy = 0.0
    peak_acceleration = 0.0
    processed_count = 0
    started = perf_counter()

    for index, sample in enumerate(samples):
        target_position = _vector3(sample.target_position_ned_m)
        target_velocity = _vector3(sample.target_velocity_ned_mps)
        target_acceleration = _vector3(sample.target_acceleration_ned_mps2)
        relative_position = target_position - pursuer_position
        relative_velocity = target_velocity - pursuer_velocity
        range_m = float(np.linalg.norm(relative_position))
        min_range_m = min(min_range_m, range_m)
        final_range_m = range_m
        processed_count += 1
        if range_m <= cfg.intercept_radius_m:
            time_to_intercept_s = sample.timestamp_s
            break
        if index + 1 >= len(samples):
            continue

        dt_s = samples[index + 1].timestamp_s - sample.timestamp_s
        acceleration = _guidance_acceleration(
            law,
            relative_position=relative_position,
            relative_velocity=relative_velocity,
            pursuer_velocity=pursuer_velocity,
            target_acceleration=target_acceleration,
            config=cfg,
        )
        acceleration = _limit_norm(acceleration, cfg.max_acceleration_mps2)
        acceleration_norm = float(np.linalg.norm(acceleration))
        control_effort += acceleration_norm * dt_s
        control_energy += acceleration_norm * acceleration_norm * dt_s
        peak_acceleration = max(peak_acceleration, acceleration_norm)
        pursuer_velocity = _constant_speed_velocity(
            pursuer_velocity + acceleration * dt_s,
            pursuer_speed,
        )
        pursuer_position = pursuer_position + pursuer_velocity * dt_s

    compute_time_s = perf_counter() - started
    is_frpn_approximation = law is OptionalP2GuidanceLaw.FRPN_APPROX
    return OptionalP2BenchmarkResult(
        seed=int(seed),
        guidance_law=law.value,
        source=str(source),
        hit=time_to_intercept_s is not None,
        min_miss_distance_m=float(min_range_m),
        final_range_m=float(final_range_m),
        time_to_intercept_s=time_to_intercept_s,
        control_effort_mps=float(control_effort),
        control_energy_m2ps3=float(control_energy),
        peak_acceleration_mps2=float(peak_acceleration),
        compute_time_s=float(compute_time_s),
        sample_count=processed_count,
        research_approximation=is_frpn_approximation,
        approximation_note=(
            "gain-scheduled robust PN research approximation; not a canonical fuzzy/FRPN law"
            if is_frpn_approximation
            else ""
        ),
        metadata={
            "navigation_constant": cfg.navigation_constant,
            "max_acceleration_mps2": cfg.max_acceleration_mps2,
            "intercept_radius_m": cfg.intercept_radius_m,
            "constant_speed_point_mass": True,
            "target_truth_used_offline_only": True,
        },
    )


def run_optional_p2_benchmark_suite(
    *,
    seeds: Iterable[int],
    laws: Iterable[OptionalP2GuidanceLaw | str] = DEFAULT_OPTIONAL_P2_LAWS,
    config: OptionalP2BenchmarkConfig | None = None,
) -> tuple[OptionalP2BenchmarkResult, ...]:
    """Run the same deterministic point-mass scenarios for every law/seed."""

    normalized_laws = tuple(_coerce_law(law) for law in laws)
    return tuple(
        run_optional_p2_point_mass_benchmark(
            guidance_law=law,
            seed=int(seed),
            config=config,
        )
        for seed in seeds
        for law in normalized_laws
    )


def summarize_optional_p2_benchmark(
    results: Iterable[OptionalP2BenchmarkResult],
) -> dict[str, Any]:
    """Aggregate hit, miss distance, effort, and compute time by law."""

    rows = tuple(results)
    law_names = tuple(dict.fromkeys(row.guidance_law for row in rows))
    by_law: dict[str, dict[str, Any]] = {}
    for law_name in law_names:
        law_rows = tuple(row for row in rows if row.guidance_law == law_name)
        by_law[law_name] = {
            "run_count": len(law_rows),
            "hit_count": sum(1 for row in law_rows if row.hit),
            "hit_rate": _mean(float(row.hit) for row in law_rows),
            "min_miss_distance_m_mean": _mean(
                row.min_miss_distance_m for row in law_rows
            ),
            "min_miss_distance_m_min": min(
                (row.min_miss_distance_m for row in law_rows),
                default=None,
            ),
            "control_effort_mps_mean": _mean(row.control_effort_mps for row in law_rows),
            "control_energy_m2ps3_mean": _mean(
                row.control_energy_m2ps3 for row in law_rows
            ),
            "compute_time_s_mean": _mean(row.compute_time_s for row in law_rows),
            "research_approximation": any(
                row.research_approximation for row in law_rows
            ),
            "approximation_notes": sorted(
                {row.approximation_note for row in law_rows if row.approximation_note}
            ),
        }
    return {
        "boundary": P2_OPTIONAL_BENCHMARK_BOUNDARY,
        "benchmark_only": True,
        "default_runtime_path_replaced": False,
        "png_guidance_delivery_modified": False,
        "d3_d4_d5_gate_bypassed": False,
        "row_count": len(rows),
        "seed_count": len({row.seed for row in rows}),
        "guidance_law_count": len(by_law),
        "guidance_laws": list(law_names),
        "frpn_is_research_approximation": True,
        "laws": by_law,
    }


def _guidance_acceleration(
    law: OptionalP2GuidanceLaw,
    *,
    relative_position: np.ndarray,
    relative_velocity: np.ndarray,
    pursuer_velocity: np.ndarray,
    target_acceleration: np.ndarray,
    config: OptionalP2BenchmarkConfig,
) -> np.ndarray:
    range_m = float(np.linalg.norm(relative_position))
    if range_m <= 1e-9:
        return np.zeros(3, dtype=float)
    los_unit = relative_position / range_m
    closing_speed = max(0.0, float(-np.dot(los_unit, relative_velocity)))
    los_angular_velocity = np.cross(relative_position, relative_velocity) / (range_m * range_m)
    pursuer_unit = _unit(pursuer_velocity, fallback=los_unit)

    if law is OptionalP2GuidanceLaw.PN_3D:
        command = (
            config.navigation_constant
            * closing_speed
            * np.cross(los_angular_velocity, los_unit)
        )
    else:
        true_pn = (
            config.navigation_constant
            * closing_speed
            * np.cross(los_angular_velocity, pursuer_unit)
        )
        if law is OptionalP2GuidanceLaw.TRUE_PN:
            command = true_pn
        elif law is OptionalP2GuidanceLaw.APN:
            target_normal = _normal_component(target_acceleration, pursuer_unit)
            command = true_pn + (
                config.apn_feedforward_gain
                * config.navigation_constant
                * target_normal
            )
        else:
            # Research approximation only: this is a deterministic robust
            # gain schedule, not a canonical fuzzy-rule FRPN implementation.
            los_ratio = float(np.linalg.norm(los_angular_velocity)) / (
                config.frpn_los_rate_scale_radps
            )
            accel_ratio = float(np.linalg.norm(target_acceleration)) / (
                config.frpn_target_accel_scale_mps2
            )
            effective_navigation_constant = (
                config.navigation_constant
                + config.frpn_los_gain * math.tanh(los_ratio)
                + config.frpn_target_accel_gain * math.tanh(accel_ratio)
            )
            robust_pn = (
                effective_navigation_constant
                * closing_speed
                * np.cross(los_angular_velocity, pursuer_unit)
            )
            target_normal = _normal_component(target_acceleration, pursuer_unit)
            command = robust_pn + config.apn_feedforward_gain * target_normal
    return _normal_component(command, pursuer_unit)


def _target_maneuver_acceleration(
    target_velocity: np.ndarray,
    *,
    timestamp_s: float,
    lateral_amplitude: float,
    vertical_amplitude: float,
    phase_lateral: float,
    phase_vertical: float,
    frequency_hz: float,
) -> np.ndarray:
    velocity_unit = _unit(target_velocity, fallback=np.array([-1.0, 0.0, 0.0]))
    horizontal_normal = _unit(
        np.cross(np.array([0.0, 0.0, 1.0]), velocity_unit),
        fallback=np.array([0.0, 1.0, 0.0]),
    )
    vertical_normal = _unit(
        np.cross(velocity_unit, horizontal_normal),
        fallback=np.array([0.0, 0.0, 1.0]),
    )
    phase = 2.0 * math.pi * frequency_hz * timestamp_s
    return (
        horizontal_normal * lateral_amplitude * math.sin(phase + phase_lateral)
        + vertical_normal * vertical_amplitude * math.sin(0.7 * phase + phase_vertical)
    )


def _coerce_law(value: OptionalP2GuidanceLaw | str) -> OptionalP2GuidanceLaw:
    if isinstance(value, OptionalP2GuidanceLaw):
        return value
    return OptionalP2GuidanceLaw(str(value))


def _coerce_replay_sample(value: OptionalP2ReplaySample | dict[str, Any] | Any) -> OptionalP2ReplaySample:
    if isinstance(value, OptionalP2ReplaySample):
        return value
    return OptionalP2ReplaySample(
        timestamp_s=float(_value(value, "timestamp_s")),
        target_position_ned_m=_tuple3(_value(value, "target_position_ned_m")),
        target_velocity_ned_mps=_tuple3(_value(value, "target_velocity_ned_mps")),
        target_acceleration_ned_mps2=_tuple3(
            _value(value, "target_acceleration_ned_mps2", (0.0, 0.0, 0.0))
        ),
    )


def _validate_replay(samples: Sequence[OptionalP2ReplaySample]) -> None:
    if len(samples) < 2:
        raise ValueError("replay must contain at least two samples")
    previous_timestamp = -math.inf
    for sample in samples:
        if sample.timestamp_s <= previous_timestamp:
            raise ValueError("replay timestamps must be strictly increasing")
        _vector3(sample.target_position_ned_m)
        _vector3(sample.target_velocity_ned_mps)
        _vector3(sample.target_acceleration_ned_mps2)
        previous_timestamp = sample.timestamp_s


def _value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _vector3(value: Iterable[float]) -> np.ndarray:
    array = np.asarray(tuple(value), dtype=float)
    if array.shape != (3,):
        raise ValueError("3D vectors must contain exactly three values")
    if not np.all(np.isfinite(array)):
        raise ValueError("3D vectors must be finite")
    return array


def _tuple3(value: Iterable[float]) -> tuple[float, float, float]:
    array = _vector3(value)
    return float(array[0]), float(array[1]), float(array[2])


def _unit(value: np.ndarray, *, fallback: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(value))
    if norm <= 1e-9:
        return _vector3(fallback)
    return value / norm


def _normal_component(value: np.ndarray, direction_unit: np.ndarray) -> np.ndarray:
    return value - direction_unit * float(np.dot(value, direction_unit))


def _limit_norm(value: np.ndarray, limit: float) -> np.ndarray:
    norm = float(np.linalg.norm(value))
    if limit <= 0.0 or norm <= limit:
        return value
    return value * (limit / norm)


def _constant_speed_velocity(value: np.ndarray, speed: float) -> np.ndarray:
    return _unit(value, fallback=np.array([1.0, 0.0, 0.0])) * speed


def _mean(values: Iterable[float]) -> float | None:
    items = tuple(float(value) for value in values)
    return mean(items) if items else None
