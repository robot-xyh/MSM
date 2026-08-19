"""Geometry, local tracking, and cross-station association for the guide case.

The online path uses anonymous bearings only. Actor names and scenario truth are
kept by the runtime in a separate offline scoring file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class CameraSpec:
    width: int = 1280
    height: int = 1024
    horizontal_fov_deg: float = 2.93
    angular_noise_sigma_mrad: float = 0.15

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("camera dimensions must be positive")
        if not 0.0 < self.horizontal_fov_deg < 180.0:
            raise ValueError("horizontal_fov_deg must be in (0, 180)")
        if self.angular_noise_sigma_mrad < 0.0:
            raise ValueError("angular noise must be non-negative")

    @property
    def focal_length_px(self) -> float:
        return self.width / (
            2.0 * math.tan(math.radians(self.horizontal_fov_deg) * 0.5)
        )

    @property
    def vertical_fov_deg(self) -> float:
        half_width = math.tan(math.radians(self.horizontal_fov_deg) * 0.5)
        return math.degrees(
            2.0 * math.atan(half_width * self.height / self.width)
        )


@dataclass(frozen=True)
class ScenarioConfig:
    target_count: int = 100
    seed: int = 20260812
    duration_s: float = 5.0
    sample_rate_hz: float = 100.0
    crossing_time_s: float = 2.5
    crossing_pair_count: int = 10
    camera_a_position_ned: tuple[float, float, float] = (0.0, -2000.0, -100.0)
    camera_b_position_ned: tuple[float, float, float] = (0.0, 2000.0, -100.0)
    corridor_center_ned: tuple[float, float, float] = (8000.0, 0.0, -950.0)
    scan_half_span_deg: float = 8.0
    scan_period_s: float = 1.0
    target_asset_name: str = "Quadrotor1"
    target_longest_dimension_m: float = 3.0
    target_dimension_tolerance_m: float = 0.20
    camera_name: str = "0"
    camera_a_name: str = "Optical_A"
    camera_b_name: str = "Optical_B"
    api_port: int = 41451
    clock_speed: float = 0.1
    detection_filter_radius_cm: float = 2_000_000.0
    local_track_gate_deg: float = 0.42
    local_track_coast_s: float = 0.70
    stable_sweep_count: int = 4

    def __post_init__(self) -> None:
        if self.target_count != 100:
            raise ValueError("this fixed guide case requires exactly 100 targets")
        if self.crossing_pair_count != 10:
            raise ValueError("this fixed guide case requires exactly 10 crossing pairs")
        if self.duration_s != 5.0 or self.sample_rate_hz != 100.0:
            raise ValueError("the fixed guide case is 5 s at 100 Hz")
        if not 0.0 < self.crossing_time_s < self.duration_s:
            raise ValueError("crossing time must be inside the episode")
        if self.scan_period_s != 1.0:
            raise ValueError("one full scan must take 1 s")
        if self.detection_filter_radius_cm <= 0.0:
            raise ValueError("detection filter radius must be positive")
        baseline = float(
            np.linalg.norm(
                np.asarray(self.camera_a_position_ned)
                - np.asarray(self.camera_b_position_ned)
            )
        )
        if not math.isclose(baseline, 4000.0, abs_tol=1e-9):
            raise ValueError("the guide-case baseline must be 4 km")

    @property
    def dt_s(self) -> float:
        return 1.0 / self.sample_rate_hz

    @property
    def frame_count(self) -> int:
        # [0, 5) gives exactly ten 0.5 s half-sweeps.
        return int(round(self.duration_s * self.sample_rate_hz))

    @property
    def half_sweep_count(self) -> int:
        return int(round(self.duration_s / (0.5 * self.scan_period_s)))

    @property
    def camera_positions(self) -> dict[str, tuple[float, float, float]]:
        return {
            self.camera_a_name: self.camera_a_position_ned,
            self.camera_b_name: self.camera_b_position_ned,
        }


@dataclass(frozen=True)
class TargetSpec:
    truth_id: str
    actor_name: str
    asset_name: str
    start_ned: tuple[float, float, float]
    velocity_ned: tuple[float, float, float]
    crossing_group: int | None = None

    def position_at(self, timestamp: float) -> tuple[float, float, float]:
        position = np.asarray(self.start_ned) + np.asarray(self.velocity_ned) * float(
            timestamp
        )
        return tuple(float(value) for value in position)

    @property
    def horizontal_speed_mps(self) -> float:
        return math.hypot(self.velocity_ned[0], self.velocity_ned[1])


@dataclass(frozen=True)
class CameraState:
    camera_id: str
    frame_index: int
    timestamp: float
    position_ned: tuple[float, float, float]
    yaw_deg: float
    pitch_deg: float
    half_sweep_index: int


@dataclass(frozen=True)
class AnonymousDetection:
    detection_uid: str
    camera_id: str
    frame_index: int
    measurement_timestamp: float
    arrival_timestamp: float
    bbox_xyxy: tuple[float, float, float, float]
    center_px: tuple[float, float]
    confidence: float


@dataclass(frozen=True)
class BearingObservation:
    observation_uid: str
    camera_id: str
    frame_index: int
    timestamp: float
    half_sweep_index: int
    origin_ned: tuple[float, float, float]
    direction_ned: tuple[float, float, float]
    bbox_xyxy: tuple[float, float, float, float]

    @property
    def azimuth_deg(self) -> float:
        return math.degrees(math.atan2(self.direction_ned[1], self.direction_ned[0]))

    @property
    def elevation_deg(self) -> float:
        horizontal = math.hypot(self.direction_ned[0], self.direction_ned[1])
        return math.degrees(
            -math.atan2(self.direction_ned[2], max(horizontal, 1e-12))
        )


@dataclass(frozen=True)
class BearingSample:
    half_sweep_index: int
    timestamp: float
    origin_ned: tuple[float, float, float]
    direction_ned: tuple[float, float, float]
    observation_uids: tuple[str, ...]


@dataclass(frozen=True)
class BearingTrack:
    track_id: str
    camera_id: str
    samples: tuple[BearingSample, ...]

    @property
    def observation_uids(self) -> tuple[str, ...]:
        return tuple(uid for sample in self.samples for uid in sample.observation_uids)


@dataclass(frozen=True)
class ResidualStatistics:
    track_a_id: str
    track_b_id: str
    sample_count: int
    timestamps_s: tuple[float, ...]
    residuals_mrad: tuple[float, ...]
    median_mrad: float
    p90_mrad: float
    mad_mrad: float
    slope_mrad_per_s: float
    motion_fit_rms_m: float
    ray_gap_p90_m: float
    fitted_horizontal_speed_mps: float
    fitted_vertical_speed_mps: float
    vote_count: int = 0
    shared_sweep_count: int = 0
    gate_passed: bool = False
    combined_cost: float = math.inf


@dataclass(frozen=True)
class ScanAssignment:
    half_sweep_index: int
    track_a_id: str
    track_b_id: str
    residual_mrad: float
    ambiguous: bool


@dataclass(frozen=True)
class AssociationState:
    half_sweep_index: int
    track_a_id: str
    track_b_id: str
    state: str
    consecutive_support: int
    vote_count: int
    residual_mrad: float
    reason: str


@dataclass(frozen=True)
class FinalMatch:
    match_id: str
    track_a_id: str
    track_b_id: str
    vote_count: int
    vote_ratio: float
    median_residual_mrad: float
    p90_residual_mrad: float
    slope_mrad_per_s: float
    combined_cost: float
    state: str


@dataclass(frozen=True)
class AssociationResult:
    residual_statistics: tuple[ResidualStatistics, ...]
    scan_assignments: tuple[ScanAssignment, ...]
    state_history: tuple[AssociationState, ...]
    final_matches: tuple[FinalMatch, ...]
    vote_matrix: np.ndarray = field(compare=False, repr=False)
    track_a_ids: tuple[str, ...] = ()
    track_b_ids: tuple[str, ...] = ()


@dataclass
class _MutableTrack:
    track_id: str
    camera_id: str
    observations: list[BearingObservation]
    last_timestamp: float
    last_direction: np.ndarray
    previous_timestamp: float | None = None
    previous_direction: np.ndarray | None = None

    def predict(self, timestamp: float) -> np.ndarray:
        if self.previous_timestamp is None or self.previous_direction is None:
            return self.last_direction
        dt = self.last_timestamp - self.previous_timestamp
        if dt <= 1e-9:
            return self.last_direction
        rate = (self.last_direction - self.previous_direction) / dt
        predicted = self.last_direction + rate * (timestamp - self.last_timestamp)
        return _unit(predicted)

    def update(self, observation: BearingObservation) -> None:
        self.previous_timestamp = self.last_timestamp
        self.previous_direction = self.last_direction
        self.last_timestamp = observation.timestamp
        self.last_direction = np.asarray(observation.direction_ned, dtype=float)
        self.observations.append(observation)


class AnonymousBearingTracker:
    """A small world-bearing tracker used before cross-station association."""

    def __init__(self, camera_id: str, *, gate_deg: float, max_coast_s: float) -> None:
        self.camera_id = camera_id
        self.gate_deg = float(gate_deg)
        self.max_coast_s = float(max_coast_s)
        self._tracks: list[_MutableTrack] = []
        self._next_id = 1

    def update(
        self, timestamp: float, observations: Sequence[BearingObservation]
    ) -> None:
        active_indices = [
            index
            for index, track in enumerate(self._tracks)
            if timestamp - track.last_timestamp <= self.max_coast_s
        ]
        unmatched_observations = set(range(len(observations)))
        if active_indices and observations:
            cost = np.full((len(active_indices), len(observations)), 1e6, dtype=float)
            for row, track_index in enumerate(active_indices):
                predicted = self._tracks[track_index].predict(timestamp)
                for column, observation in enumerate(observations):
                    distance = angular_distance_deg(
                        predicted, np.asarray(observation.direction_ned)
                    )
                    if distance <= self.gate_deg:
                        cost[row, column] = distance
            rows, columns = linear_sum_assignment(cost)
            for row, column in zip(rows, columns, strict=True):
                if cost[row, column] >= 1e5:
                    continue
                self._tracks[active_indices[row]].update(observations[column])
                unmatched_observations.discard(column)
        for observation_index in sorted(unmatched_observations):
            observation = observations[observation_index]
            self._tracks.append(
                _MutableTrack(
                    track_id=f"{self.camera_id}-T{self._next_id:03d}",
                    camera_id=self.camera_id,
                    observations=[observation],
                    last_timestamp=observation.timestamp,
                    last_direction=np.asarray(observation.direction_ned, dtype=float),
                )
            )
            self._next_id += 1

    def tracks(self, minimum_sweeps: int) -> tuple[BearingTrack, ...]:
        completed: list[BearingTrack] = []
        for track in self._tracks:
            grouped: dict[int, list[BearingObservation]] = {}
            for observation in track.observations:
                grouped.setdefault(observation.half_sweep_index, []).append(observation)
            samples = []
            for sweep, values in sorted(grouped.items()):
                weights = np.ones(len(values), dtype=float)
                direction = _unit(
                    np.average(
                        np.asarray([item.direction_ned for item in values]),
                        axis=0,
                        weights=weights,
                    )
                )
                samples.append(
                    BearingSample(
                        half_sweep_index=sweep,
                        timestamp=float(np.average([item.timestamp for item in values])),
                        origin_ned=values[0].origin_ned,
                        direction_ned=tuple(float(value) for value in direction),
                        observation_uids=tuple(
                            item.observation_uid for item in values
                        ),
                    )
                )
            if len(samples) >= minimum_sweeps:
                completed.append(
                    BearingTrack(track.track_id, track.camera_id, tuple(samples))
                )
        return tuple(completed)


def generate_target_specs(config: ScenarioConfig) -> tuple[TargetSpec, ...]:
    """Generate 10 deterministic crossing pairs and 80 separated tracks."""

    rng = np.random.default_rng(config.seed)
    targets: list[TargetSpec] = []
    truth_index = 1
    crossing_centres = [
        (6900.0 + 350.0 * row, lateral, -950.0)
        for row in range(5)
        for lateral in (-350.0, 350.0)
    ]
    for group, centre in enumerate(crossing_centres, start=1):
        for lateral_sign, vertical_sign in ((1.0, 1.0), (-1.0, -1.0)):
            velocity = np.asarray(
                (-45.0, 25.0 * lateral_sign, 10.0 * vertical_sign), dtype=float
            )
            start = np.asarray(centre, dtype=float) - velocity * config.crossing_time_s
            targets.append(
                TargetSpec(
                    truth_id=f"TRUTH-{truth_index:03d}",
                    actor_name=f"MSM_Guide_Target_{truth_index:03d}",
                    asset_name=config.target_asset_name,
                    start_ned=tuple(float(value) for value in start),
                    velocity_ned=tuple(float(value) for value in velocity),
                    crossing_group=group,
                )
            )
            truth_index += 1

    for row in range(8):
        for column in range(10):
            horizontal_speed = float(rng.uniform(40.0, 60.0))
            lateral_speed = float(rng.uniform(-8.0, 8.0))
            approach_speed = -math.sqrt(
                max(horizontal_speed**2 - lateral_speed**2, 1e-9)
            )
            vertical_speed = float(rng.uniform(-20.0, 20.0))
            start = (
                8800.0 + 170.0 * row + float(rng.uniform(-5.0, 5.0)),
                -765.0 + 170.0 * column + float(rng.uniform(-5.0, 5.0)),
                -950.0 + float(rng.uniform(-25.0, 25.0)),
            )
            targets.append(
                TargetSpec(
                    truth_id=f"TRUTH-{truth_index:03d}",
                    actor_name=f"MSM_Guide_Target_{truth_index:03d}",
                    asset_name=config.target_asset_name,
                    start_ned=start,
                    velocity_ned=(approach_speed, lateral_speed, vertical_speed),
                )
            )
            truth_index += 1

    if len(targets) != config.target_count:
        raise RuntimeError("target generator returned the wrong count")
    minimum = minimum_initial_separation(targets)
    if minimum <= 100.0:
        raise RuntimeError(f"initial target separation is only {minimum:.3f} m")
    if any(not 40.0 <= target.horizontal_speed_mps <= 60.0 for target in targets):
        raise RuntimeError("horizontal speed constraint was violated")
    if any(abs(target.velocity_ned[2]) > 20.0 for target in targets):
        raise RuntimeError("vertical speed constraint was violated")
    validate_crossing_pairs(targets, config)
    return tuple(targets)


def validate_crossing_pairs(
    targets: Sequence[TargetSpec], config: ScenarioConfig, *, tolerance_m: float = 1e-6
) -> None:
    groups: dict[int, list[TargetSpec]] = {}
    for target in targets:
        if target.crossing_group is not None:
            groups.setdefault(target.crossing_group, []).append(target)
    if len(groups) != config.crossing_pair_count:
        raise RuntimeError("crossing-pair count does not match the scenario")
    for group, members in groups.items():
        if len(members) != 2:
            raise RuntimeError(f"crossing group {group} is not a pair")
        separation = math.dist(
            members[0].position_at(config.crossing_time_s),
            members[1].position_at(config.crossing_time_s),
        )
        if separation > tolerance_m:
            raise RuntimeError(f"crossing group {group} misses by {separation:.6f} m")


def crossing_pairs(targets: Sequence[TargetSpec]) -> tuple[tuple[str, str], ...]:
    grouped: dict[int, list[str]] = {}
    for target in targets:
        if target.crossing_group is not None:
            grouped.setdefault(target.crossing_group, []).append(target.truth_id)
    return tuple(tuple(sorted(values)) for _, values in sorted(grouped.items()))


def minimum_initial_separation(targets: Sequence[TargetSpec]) -> float:
    minimum = math.inf
    for index, first in enumerate(targets):
        for second in targets[index + 1 :]:
            minimum = min(minimum, math.dist(first.start_ned, second.start_ned))
    return float(minimum)


def look_angles_deg(
    camera_position_ned: Sequence[float], point_ned: Sequence[float]
) -> tuple[float, float]:
    delta = np.asarray(point_ned, dtype=float) - np.asarray(
        camera_position_ned, dtype=float
    )
    yaw = math.degrees(math.atan2(float(delta[1]), float(delta[0])))
    pitch = math.degrees(
        -math.atan2(float(delta[2]), max(math.hypot(delta[0], delta[1]), 1e-12))
    )
    return yaw, pitch


def scan_yaw_deg(
    timestamp: float,
    base_yaw_deg: float,
    *,
    half_span_deg: float = 8.0,
    period_s: float = 1.0,
) -> float:
    phase = (float(timestamp) % period_s) / period_s
    if phase < 0.5:
        offset = -half_span_deg + 4.0 * half_span_deg * phase
    else:
        offset = 3.0 * half_span_deg - 4.0 * half_span_deg * phase
    return normalize_angle_deg(base_yaw_deg + offset)


def half_sweep_index(timestamp: float, *, period_s: float = 1.0) -> int:
    return int(math.floor(timestamp / (0.5 * period_s) + 1e-9))


def camera_rotation_world_from_local(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    rotation_yaw = np.asarray(
        (
            (math.cos(yaw), -math.sin(yaw), 0.0),
            (math.sin(yaw), math.cos(yaw), 0.0),
            (0.0, 0.0, 1.0),
        )
    )
    rotation_pitch = np.asarray(
        (
            (math.cos(pitch), 0.0, math.sin(pitch)),
            (0.0, 1.0, 0.0),
            (-math.sin(pitch), 0.0, math.cos(pitch)),
        )
    )
    return rotation_yaw @ rotation_pitch


def project_world_point(
    point_ned: Sequence[float], state: CameraState, camera: CameraSpec
) -> tuple[float, float] | None:
    delta = np.asarray(point_ned, dtype=float) - np.asarray(state.position_ned)
    local = camera_rotation_world_from_local(state.yaw_deg, state.pitch_deg).T @ delta
    if local[0] <= 1e-9:
        return None
    return (
        camera.width * 0.5 + camera.focal_length_px * local[1] / local[0],
        camera.height * 0.5 + camera.focal_length_px * local[2] / local[0],
    )


def pixel_to_world_ray(
    pixel: Sequence[float], state: CameraState, camera: CameraSpec
) -> tuple[float, float, float]:
    local = _unit(
        np.asarray(
            (
                1.0,
                (float(pixel[0]) - camera.width * 0.5) / camera.focal_length_px,
                (float(pixel[1]) - camera.height * 0.5) / camera.focal_length_px,
            )
        )
    )
    world = camera_rotation_world_from_local(state.yaw_deg, state.pitch_deg) @ local
    return tuple(float(value) for value in _unit(world))


def perturb_unit_ray(
    direction: Sequence[float], sigma_mrad: float, rng: np.random.Generator
) -> tuple[float, float, float]:
    ray = _unit(np.asarray(direction, dtype=float))
    helper = np.asarray((0.0, 0.0, 1.0))
    if abs(float(np.dot(ray, helper))) > 0.9:
        helper = np.asarray((0.0, 1.0, 0.0))
    tangent_a = _unit(np.cross(ray, helper))
    tangent_b = _unit(np.cross(ray, tangent_a))
    offsets = rng.normal(0.0, sigma_mrad * 1e-3, size=2)
    return tuple(float(value) for value in _unit(ray + offsets[0] * tangent_a + offsets[1] * tangent_b))


def observation_from_detection(
    detection: AnonymousDetection,
    state: CameraState,
    camera: CameraSpec,
    rng: np.random.Generator,
) -> BearingObservation:
    ideal_ray = pixel_to_world_ray(detection.center_px, state, camera)
    noisy_ray = perturb_unit_ray(
        ideal_ray, camera.angular_noise_sigma_mrad, rng
    )
    return BearingObservation(
        observation_uid=detection.detection_uid,
        camera_id=detection.camera_id,
        frame_index=detection.frame_index,
        timestamp=detection.measurement_timestamp,
        half_sweep_index=state.half_sweep_index,
        origin_ned=state.position_ned,
        direction_ned=noisy_ray,
        bbox_xyxy=detection.bbox_xyxy,
    )


def normalized_coplanarity_residual_mrad(
    origin_a: Sequence[float],
    direction_a: Sequence[float],
    origin_b: Sequence[float],
    direction_b: Sequence[float],
) -> float:
    baseline = np.asarray(origin_b, dtype=float) - np.asarray(origin_a, dtype=float)
    baseline_norm = float(np.linalg.norm(baseline))
    if baseline_norm <= 1e-9:
        raise ValueError("coplanarity requires distinct stations")
    baseline /= baseline_norm
    ray_a = _unit(np.asarray(direction_a, dtype=float))
    ray_b = _unit(np.asarray(direction_b, dtype=float))
    normal_a = np.cross(ray_a, baseline)
    normal_b = np.cross(ray_b, -baseline)
    norm_a = float(np.linalg.norm(normal_a))
    norm_b = float(np.linalg.norm(normal_b))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return math.inf
    residual_a = math.asin(
        float(np.clip(abs(np.dot(ray_b, normal_a / norm_a)), 0.0, 1.0))
    )
    residual_b = math.asin(
        float(np.clip(abs(np.dot(ray_a, normal_b / norm_b)), 0.0, 1.0))
    )
    return 500.0 * (residual_a + residual_b)


def residual_sequence(
    track_a: BearingTrack, track_b: BearingTrack
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    samples_a = {sample.half_sweep_index: sample for sample in track_a.samples}
    samples_b = {sample.half_sweep_index: sample for sample in track_b.samples}
    common = sorted(set(samples_a) & set(samples_b))
    timestamps: list[float] = []
    residuals: list[float] = []
    for sweep in common:
        sample_a = samples_a[sweep]
        sample_b = samples_b[sweep]
        timestamp = 0.5 * (sample_a.timestamp + sample_b.timestamp)
        ray_a = interpolate_track_direction(track_a, timestamp)
        ray_b = interpolate_track_direction(track_b, timestamp)
        residual = normalized_coplanarity_residual_mrad(
            sample_a.origin_ned, ray_a, sample_b.origin_ned, ray_b
        )
        timestamps.append(timestamp)
        residuals.append(residual)
    return tuple(timestamps), tuple(residuals)


def build_residual_statistics(
    track_a: BearingTrack,
    track_b: BearingTrack,
    *,
    vote_count: int = 0,
    shared_sweep_count: int = 0,
) -> ResidualStatistics:
    timestamps, residuals = residual_sequence(track_a, track_b)
    if not residuals:
        return ResidualStatistics(
            track_a.track_id,
            track_b.track_id,
            0,
            (),
            (),
            math.inf,
            math.inf,
            math.inf,
            math.inf,
            math.inf,
            math.inf,
            math.inf,
            math.inf,
            vote_count,
            shared_sweep_count,
            False,
            math.inf,
        )
    values = np.asarray(residuals, dtype=float)
    median = float(np.median(values))
    p90 = float(np.percentile(values, 90.0))
    mad = float(np.median(np.abs(values - median)))
    slope = 0.0
    if len(values) >= 2 and max(timestamps) - min(timestamps) > 1e-9:
        slope = float(np.polyfit(np.asarray(timestamps), values, 1)[0])
    positions, ray_gaps = _triangulated_sequence(track_a, track_b, timestamps)
    motion_rms = math.inf
    horizontal_speed = math.inf
    vertical_speed = math.inf
    if len(positions) >= 3:
        design = np.column_stack((np.ones(len(timestamps)), np.asarray(timestamps)))
        coefficients, *_ = np.linalg.lstsq(design, np.asarray(positions), rcond=None)
        fitted = design @ coefficients
        motion_rms = float(
            np.sqrt(np.mean(np.sum((np.asarray(positions) - fitted) ** 2, axis=1)))
        )
        velocity = coefficients[1]
        horizontal_speed = float(math.hypot(velocity[0], velocity[1]))
        vertical_speed = float(velocity[2])
    ray_gap_p90 = float(np.percentile(ray_gaps, 90.0)) if ray_gaps else math.inf
    vote_ratio = vote_count / max(shared_sweep_count, 1)
    gate_passed = bool(
        len(values) >= 3
        and median <= 0.80
        and p90 <= 1.50
        and abs(slope) <= 0.35
        and motion_rms <= 20.0
        and ray_gap_p90 <= 20.0
        and 20.0 <= horizontal_speed <= 85.0
        and abs(vertical_speed) <= 45.0
        and vote_count >= 2
    )
    combined = (
        median + 0.20 * p90 + 0.30 * mad + 0.50 * abs(slope)
        + 0.80 * (1.0 - vote_ratio)
        + 0.03 * motion_rms
        + 0.02 * ray_gap_p90
    )
    return ResidualStatistics(
        track_a.track_id,
        track_b.track_id,
        len(values),
        timestamps,
        residuals,
        median,
        p90,
        mad,
        slope,
        motion_rms,
        ray_gap_p90,
        horizontal_speed,
        vertical_speed,
        vote_count,
        shared_sweep_count,
        gate_passed,
        combined,
    )


def scan_level_assignments(
    tracks_a: Sequence[BearingTrack],
    tracks_b: Sequence[BearingTrack],
    *,
    gate_mrad: float = 1.50,
    ambiguity_margin_mrad: float = 0.12,
) -> tuple[ScanAssignment, ...]:
    assignments: list[ScanAssignment] = []
    sweeps = sorted(
        {sample.half_sweep_index for track in tracks_a for sample in track.samples}
        & {sample.half_sweep_index for track in tracks_b for sample in track.samples}
    )
    for sweep in sweeps:
        available_a = [track for track in tracks_a if _sample_for_sweep(track, sweep)]
        available_b = [track for track in tracks_b if _sample_for_sweep(track, sweep)]
        if not available_a or not available_b:
            continue
        cost = np.full((len(available_a), len(available_b)), 1e6, dtype=float)
        for row, track_a in enumerate(available_a):
            sample_a = _sample_for_sweep(track_a, sweep)
            assert sample_a is not None
            for column, track_b in enumerate(available_b):
                sample_b = _sample_for_sweep(track_b, sweep)
                assert sample_b is not None
                timestamp = 0.5 * (sample_a.timestamp + sample_b.timestamp)
                residual = normalized_coplanarity_residual_mrad(
                    sample_a.origin_ned,
                    interpolate_track_direction(track_a, timestamp),
                    sample_b.origin_ned,
                    interpolate_track_direction(track_b, timestamp),
                )
                if residual <= gate_mrad:
                    cost[row, column] = residual
        rows, columns = linear_sum_assignment(cost)
        for row, column in zip(rows, columns, strict=True):
            residual = float(cost[row, column])
            if residual >= 1e5:
                continue
            row_values = np.sort(cost[row][cost[row] < 1e5])
            column_values = np.sort(cost[:, column][cost[:, column] < 1e5])
            row_margin = math.inf if len(row_values) < 2 else row_values[1] - row_values[0]
            column_margin = (
                math.inf if len(column_values) < 2 else column_values[1] - column_values[0]
            )
            assignments.append(
                ScanAssignment(
                    sweep,
                    available_a[row].track_id,
                    available_b[column].track_id,
                    residual,
                    min(row_margin, column_margin) < ambiguity_margin_mrad,
                )
            )
    return tuple(assignments)


def associate_tracks(
    tracks_a: Sequence[BearingTrack], tracks_b: Sequence[BearingTrack]
) -> AssociationResult:
    tracks_a = tuple(sorted(tracks_a, key=lambda item: item.track_id))
    tracks_b = tuple(sorted(tracks_b, key=lambda item: item.track_id))
    scan_assignments = scan_level_assignments(tracks_a, tracks_b)
    votes: dict[tuple[str, str], int] = {}
    for assignment in scan_assignments:
        key = (assignment.track_a_id, assignment.track_b_id)
        votes[key] = votes.get(key, 0) + 1
    statistics: list[ResidualStatistics] = []
    for track_a in tracks_a:
        sweeps_a = {sample.half_sweep_index for sample in track_a.samples}
        for track_b in tracks_b:
            shared = len(
                sweeps_a & {sample.half_sweep_index for sample in track_b.samples}
            )
            statistics.append(
                build_residual_statistics(
                    track_a,
                    track_b,
                    vote_count=votes.get((track_a.track_id, track_b.track_id), 0),
                    shared_sweep_count=shared,
                )
            )

    state_history = _build_state_history(scan_assignments)
    state_lookup: dict[tuple[str, str], str] = {}
    for record in state_history:
        state_lookup[(record.track_a_id, record.track_b_id)] = record.state

    stats_lookup = {
        (item.track_a_id, item.track_b_id): item for item in statistics
    }
    matrix = np.full((len(tracks_a), len(tracks_b)), math.inf, dtype=float)
    vote_matrix = np.zeros_like(matrix)
    for row, track_a in enumerate(tracks_a):
        for column, track_b in enumerate(tracks_b):
            stat = stats_lookup[(track_a.track_id, track_b.track_id)]
            vote_matrix[row, column] = stat.vote_count
            if stat.gate_passed:
                matrix[row, column] = stat.combined_cost
    selected = _assignment_with_unmatched(matrix, unmatched_cost=2.5)
    matches: list[FinalMatch] = []
    for row, column in selected:
        stat = stats_lookup[(tracks_a[row].track_id, tracks_b[column].track_id)]
        state = state_lookup.get((stat.track_a_id, stat.track_b_id), "tentative")
        if state not in {"confirmed", "coasting"} and stat.vote_count >= 3:
            state = "confirmed"
        matches.append(
            FinalMatch(
                match_id=f"PAIR-{len(matches) + 1:03d}",
                track_a_id=stat.track_a_id,
                track_b_id=stat.track_b_id,
                vote_count=stat.vote_count,
                vote_ratio=stat.vote_count / max(stat.shared_sweep_count, 1),
                median_residual_mrad=stat.median_mrad,
                p90_residual_mrad=stat.p90_mrad,
                slope_mrad_per_s=stat.slope_mrad_per_s,
                combined_cost=stat.combined_cost,
                state=state,
            )
        )
    return AssociationResult(
        residual_statistics=tuple(statistics),
        scan_assignments=scan_assignments,
        state_history=state_history,
        final_matches=tuple(matches),
        vote_matrix=vote_matrix,
        track_a_ids=tuple(track.track_id for track in tracks_a),
        track_b_ids=tuple(track.track_id for track in tracks_b),
    )


def select_multi_time_pairs(
    statistics: Sequence[ResidualStatistics],
    track_a_ids: Sequence[str],
    track_b_ids: Sequence[str],
) -> tuple[tuple[str, str], ...]:
    """Select one-to-one pairs from trajectory evidence without scan votes."""

    lookup = {(item.track_a_id, item.track_b_id): item for item in statistics}
    matrix = np.full((len(track_a_ids), len(track_b_ids)), math.inf, dtype=float)
    for row, track_a_id in enumerate(track_a_ids):
        for column, track_b_id in enumerate(track_b_ids):
            item = lookup[(track_a_id, track_b_id)]
            physically_valid = bool(
                item.sample_count >= 3
                and item.median_mrad <= 0.80
                and item.p90_mrad <= 1.50
                and abs(item.slope_mrad_per_s) <= 0.35
                and item.motion_fit_rms_m <= 20.0
                and item.ray_gap_p90_m <= 20.0
                and 20.0 <= item.fitted_horizontal_speed_mps <= 85.0
                and abs(item.fitted_vertical_speed_mps) <= 45.0
            )
            if physically_valid:
                matrix[row, column] = (
                    item.median_mrad
                    + 0.20 * item.p90_mrad
                    + 0.30 * item.mad_mrad
                    + 0.50 * abs(item.slope_mrad_per_s)
                    + 0.03 * item.motion_fit_rms_m
                    + 0.02 * item.ray_gap_p90_m
                )
    selected = _assignment_with_unmatched(matrix, unmatched_cost=2.0)
    return tuple((track_a_ids[row], track_b_ids[column]) for row, column in selected)


def build_synthetic_tracks(
    config: ScenarioConfig,
    camera: CameraSpec,
) -> tuple[
    tuple[BearingTrack, ...],
    tuple[BearingTrack, ...],
    dict[str, str],
]:
    """Create deterministic anonymous bearing tracks for tests and dry validation."""

    targets = generate_target_specs(config)
    rng = np.random.default_rng(config.seed + 91)
    tracks_by_camera: dict[str, list[BearingTrack]] = {
        config.camera_a_name: [],
        config.camera_b_name: [],
    }
    observation_truth: dict[str, str] = {}
    for camera_id, origin in config.camera_positions.items():
        for target_index, target in enumerate(targets, start=1):
            samples: list[BearingSample] = []
            for sweep in range(config.half_sweep_count):
                timestamp = 0.25 + 0.5 * sweep
                point = np.asarray(target.position_at(timestamp))
                ideal = _unit(point - np.asarray(origin))
                noisy = perturb_unit_ray(
                    ideal, camera.angular_noise_sigma_mrad, rng
                )
                uid = f"{camera_id}-S{sweep:02d}-O{target_index:03d}"
                observation_truth[uid] = target.truth_id
                samples.append(
                    BearingSample(
                        half_sweep_index=sweep,
                        timestamp=timestamp,
                        origin_ned=origin,
                        direction_ned=noisy,
                        observation_uids=(uid,),
                    )
                )
            tracks_by_camera[camera_id].append(
                BearingTrack(
                    track_id=f"{camera_id}-T{target_index:03d}",
                    camera_id=camera_id,
                    samples=tuple(samples),
                )
            )
    return (
        tuple(tracks_by_camera[config.camera_a_name]),
        tuple(tracks_by_camera[config.camera_b_name]),
        observation_truth,
    )


def majority_track_truth(
    tracks: Sequence[BearingTrack], observation_truth: Mapping[str, str]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for track in tracks:
        values = [
            observation_truth[uid]
            for uid in track.observation_uids
            if uid in observation_truth
        ]
        if values:
            result[track.track_id] = max(sorted(set(values)), key=values.count)
    return result


def score_matches(
    matches: Sequence[FinalMatch],
    truth_a: Mapping[str, str],
    truth_b: Mapping[str, str],
    *,
    target_count: int,
) -> dict[str, float | int]:
    scored = [
        truth_a.get(match.track_a_id, "") == truth_b.get(match.track_b_id, "")
        and truth_a.get(match.track_a_id, "") != ""
        for match in matches
    ]
    correct = sum(scored)
    false = len(scored) - correct
    unique_correct_targets = {
        truth_a[match.track_a_id]
        for match, is_correct in zip(matches, scored, strict=True)
        if is_correct
    }
    return {
        "selected_match_count": len(matches),
        "correct_match_count": correct,
        "false_match_count": false,
        "association_precision": correct / max(len(matches), 1),
        "unique_target_recall": len(unique_correct_targets) / target_count,
    }


def online_truth_leakage_keys(records: Iterable[Mapping[str, object]]) -> tuple[str, ...]:
    forbidden = ("truth", "actor", "box3d", "object_name", "ground_truth")
    findings: list[str] = []

    def walk(value: object, path: str) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                key_path = f"{path}.{key}" if path else str(key)
                if any(token in str(key).lower() for token in forbidden):
                    findings.append(key_path)
                walk(nested, key_path)
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                walk(nested, f"{path}[{index}]")

    for record_index, record in enumerate(records):
        walk(record, f"record[{record_index}]")
    return tuple(sorted(set(findings)))


def interpolate_track_direction(track: BearingTrack, timestamp: float) -> np.ndarray:
    samples = sorted(track.samples, key=lambda item: item.timestamp)
    if timestamp <= samples[0].timestamp:
        return np.asarray(samples[0].direction_ned)
    if timestamp >= samples[-1].timestamp:
        return np.asarray(samples[-1].direction_ned)
    for first, second in zip(samples, samples[1:], strict=False):
        if first.timestamp <= timestamp <= second.timestamp:
            fraction = (timestamp - first.timestamp) / max(
                second.timestamp - first.timestamp, 1e-12
            )
            return _unit(
                (1.0 - fraction) * np.asarray(first.direction_ned)
                + fraction * np.asarray(second.direction_ned)
            )
    return np.asarray(samples[-1].direction_ned)


def angular_distance_deg(first: Sequence[float], second: Sequence[float]) -> float:
    first_unit = _unit(np.asarray(first, dtype=float))
    second_unit = _unit(np.asarray(second, dtype=float))
    return math.degrees(
        math.acos(float(np.clip(np.dot(first_unit, second_unit), -1.0, 1.0)))
    )


def normalize_angle_deg(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def _sample_for_sweep(track: BearingTrack, sweep: int) -> BearingSample | None:
    return next(
        (sample for sample in track.samples if sample.half_sweep_index == sweep), None
    )


def _triangulated_sequence(
    track_a: BearingTrack,
    track_b: BearingTrack,
    timestamps: Sequence[float],
) -> tuple[list[tuple[float, float, float]], list[float]]:
    positions: list[tuple[float, float, float]] = []
    gaps: list[float] = []
    origin_a = np.asarray(track_a.samples[0].origin_ned, dtype=float)
    origin_b = np.asarray(track_b.samples[0].origin_ned, dtype=float)
    for timestamp in timestamps:
        ray_a = interpolate_track_direction(track_a, timestamp)
        ray_b = interpolate_track_direction(track_b, timestamp)
        midpoint, gap, forward = _closest_ray_midpoint(
            origin_a, ray_a, origin_b, ray_b
        )
        if not forward:
            continue
        positions.append(tuple(float(value) for value in midpoint))
        gaps.append(gap)
    return positions, gaps


def _closest_ray_midpoint(
    origin_a: np.ndarray,
    ray_a: np.ndarray,
    origin_b: np.ndarray,
    ray_b: np.ndarray,
) -> tuple[np.ndarray, float, bool]:
    ray_a = _unit(ray_a)
    ray_b = _unit(ray_b)
    delta = origin_a - origin_b
    aa = float(np.dot(ray_a, ray_a))
    bb = float(np.dot(ray_a, ray_b))
    cc = float(np.dot(ray_b, ray_b))
    dd = float(np.dot(ray_a, delta))
    ee = float(np.dot(ray_b, delta))
    denominator = aa * cc - bb * bb
    if abs(denominator) <= 1e-10:
        return 0.5 * (origin_a + origin_b), math.inf, False
    distance_a = (bb * ee - cc * dd) / denominator
    distance_b = (aa * ee - bb * dd) / denominator
    point_a = origin_a + distance_a * ray_a
    point_b = origin_b + distance_b * ray_b
    return (
        0.5 * (point_a + point_b),
        float(np.linalg.norm(point_a - point_b)),
        bool(distance_a > 0.0 and distance_b > 0.0),
    )


def _build_state_history(
    assignments: Sequence[ScanAssignment], *, confirmation_length: int = 3
) -> tuple[AssociationState, ...]:
    by_sweep: dict[int, list[ScanAssignment]] = {}
    for assignment in assignments:
        by_sweep.setdefault(assignment.half_sweep_index, []).append(assignment)
    consecutive: dict[tuple[str, str], int] = {}
    votes: dict[tuple[str, str], int] = {}
    records: list[AssociationState] = []
    previous_for_a: dict[str, str] = {}
    for sweep in sorted(by_sweep):
        present_pairs: set[tuple[str, str]] = set()
        for assignment in sorted(
            by_sweep[sweep], key=lambda item: (item.track_a_id, item.track_b_id)
        ):
            key = (assignment.track_a_id, assignment.track_b_id)
            present_pairs.add(key)
            votes[key] = votes.get(key, 0) + 1
            if assignment.ambiguous:
                state = "pending"
                reason = "crossing_or_competing_candidate"
                consecutive[key] = 0
            else:
                same_as_previous = previous_for_a.get(assignment.track_a_id) in {
                    None,
                    assignment.track_b_id,
                }
                consecutive[key] = consecutive.get(key, 0) + 1 if same_as_previous else 1
                state = (
                    "confirmed"
                    if consecutive[key] >= confirmation_length
                    else "tentative"
                )
                reason = "continuous_support" if state == "confirmed" else "collecting_support"
            previous_for_a[assignment.track_a_id] = assignment.track_b_id
            records.append(
                AssociationState(
                    sweep,
                    assignment.track_a_id,
                    assignment.track_b_id,
                    state,
                    consecutive.get(key, 0),
                    votes[key],
                    assignment.residual_mrad,
                    reason,
                )
            )
        for key, count in list(consecutive.items()):
            if key not in present_pairs and count >= confirmation_length:
                records.append(
                    AssociationState(
                        sweep,
                        key[0],
                        key[1],
                        "coasting",
                        count,
                        votes.get(key, 0),
                        math.nan,
                        "one_sweep_without_support",
                    )
                )
                consecutive[key] = max(0, count - 1)
    return tuple(records)


def _assignment_with_unmatched(
    pair_cost: np.ndarray, *, unmatched_cost: float
) -> tuple[tuple[int, int], ...]:
    rows, columns = pair_cost.shape
    if rows == 0 or columns == 0:
        return ()
    size = rows + columns
    large = 1e6
    augmented = np.full((size, size), large, dtype=float)
    augmented[:rows, :columns] = np.where(np.isfinite(pair_cost), pair_cost, large)
    for row in range(rows):
        augmented[row, columns + row] = unmatched_cost
    for column in range(columns):
        augmented[rows + column, column] = unmatched_cost
    augmented[rows:, columns:] = 0.0
    selected_rows, selected_columns = linear_sum_assignment(augmented)
    selected = []
    for row, column in zip(selected_rows, selected_columns, strict=True):
        if row < rows and column < columns and pair_cost[row, column] < unmatched_cost:
            selected.append((int(row), int(column)))
    return tuple(selected)


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError("zero vector cannot be normalized")
    return vector / norm
