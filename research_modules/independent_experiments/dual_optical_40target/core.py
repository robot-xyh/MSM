"""Geometry and association core for the independent dual-optical experiment."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class CameraSpec:
    width: int = 1280
    height: int = 1024
    horizontal_fov_deg: float = 2.93
    equivalent_focal_length_mm: float = 300.0
    stated_ifov_mrad: float = 0.05

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("camera dimensions must be positive")
        if not 0.0 < self.horizontal_fov_deg < 180.0:
            raise ValueError("horizontal_fov_deg must be in (0, 180)")

    @property
    def focal_length_px(self) -> float:
        return self.width / (
            2.0 * math.tan(math.radians(self.horizontal_fov_deg) * 0.5)
        )

    @property
    def vertical_fov_deg(self) -> float:
        half = math.tan(math.radians(self.horizontal_fov_deg) * 0.5)
        return math.degrees(2.0 * math.atan(half * self.height / self.width))

    @property
    def effective_ifov_mrad(self) -> float:
        return math.radians(self.horizontal_fov_deg) * 1000.0 / self.width


@dataclass(frozen=True)
class ScenarioConfig:
    target_count: int = 40
    seed: int = 20260810
    duration_s: float = 12.0
    sample_rate_hz: float = 100.0
    target_speed_mps: float = 50.0
    camera_a_position_ned: tuple[float, float, float] = (0.0, -1000.0, -100.0)
    camera_b_position_ned: tuple[float, float, float] = (0.0, 1000.0, -100.0)
    corridor_center_ned: tuple[float, float, float] = (2000.0, 0.0, -100.0)
    target_asset_name: str = "Quadrotor1"
    target_longest_dimension_m: float = 3.0
    target_dimension_tolerance_m: float = 0.15
    scan_half_span_deg: float = 45.0
    scan_period_s: float = 1.0
    track_coast_s: float = 0.75
    stable_sweep_count: int = 4
    max_cross_camera_time_delta_s: float = 0.20
    api_port: int = 41451
    clock_speed: float = 0.1
    camera_name: str = "0"
    camera_a_name: str = "Optical_A"
    camera_b_name: str = "Optical_B"

    def __post_init__(self) -> None:
        if self.target_count <= 0:
            raise ValueError("target_count must be positive")
        if self.duration_s <= 0.0 or self.sample_rate_hz <= 0.0:
            raise ValueError("duration and sample rate must be positive")
        if self.target_speed_mps <= 0.0:
            raise ValueError("target speed must be positive")
        baseline = np.linalg.norm(
            np.asarray(self.camera_a_position_ned)
            - np.asarray(self.camera_b_position_ned)
        )
        if not math.isclose(float(baseline), 2000.0, abs_tol=1e-6):
            raise ValueError("the dual-optical baseline must be 2000 m")
        if self.scan_half_span_deg <= 0.0 or self.scan_period_s <= 0.0:
            raise ValueError("scan span and period must be positive")
        if self.track_coast_s <= 0.0 or self.stable_sweep_count < 2:
            raise ValueError("invalid revisit-track settings")

    @property
    def dt_s(self) -> float:
        return 1.0 / self.sample_rate_hz

    @property
    def frame_count(self) -> int:
        return int(round(self.duration_s * self.sample_rate_hz)) + 1

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

    def position_at(self, timestamp: float) -> tuple[float, float, float]:
        start = np.asarray(self.start_ned, dtype=float)
        velocity = np.asarray(self.velocity_ned, dtype=float)
        return tuple(float(value) for value in start + velocity * float(timestamp))

    @property
    def speed_mps(self) -> float:
        return float(np.linalg.norm(np.asarray(self.velocity_ned, dtype=float)))


@dataclass(frozen=True)
class CameraState:
    camera_id: str
    frame_index: int
    timestamp: float
    position_ned: tuple[float, float, float]
    yaw_deg: float
    pitch_deg: float


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
class RayObservation:
    detection_uid: str
    camera_id: str
    frame_index: int
    timestamp: float
    origin_ned: tuple[float, float, float]
    direction_ned: tuple[float, float, float]
    bbox_xyxy: tuple[float, float, float, float]
    sweep_index: int
    camera_yaw_deg: float
    camera_pitch_deg: float
    focal_length_px: float

    @property
    def azimuth_deg(self) -> float:
        direction = self.direction_ned
        return math.degrees(math.atan2(direction[1], direction[0]))

    @property
    def elevation_deg(self) -> float:
        direction = self.direction_ned
        horizontal = math.hypot(direction[0], direction[1])
        return math.degrees(-math.atan2(direction[2], max(horizontal, 1e-12)))

    @property
    def bbox_area_px2(self) -> float:
        x1, y1, x2, y2 = self.bbox_xyxy
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)


@dataclass(frozen=True)
class BearingSample:
    camera_id: str
    sweep_index: int
    timestamp: float
    origin_ned: tuple[float, float, float]
    direction_ned: tuple[float, float, float]
    detection_uids: tuple[str, ...]
    focal_length_px: float
    bbox_area_px2: float

    @property
    def azimuth_deg(self) -> float:
        direction = self.direction_ned
        return math.degrees(math.atan2(direction[1], direction[0]))

    @property
    def elevation_deg(self) -> float:
        direction = self.direction_ned
        horizontal = math.hypot(direction[0], direction[1])
        return math.degrees(-math.atan2(direction[2], max(horizontal, 1e-12)))


@dataclass
class BearingTrack:
    track_id: str
    camera_id: str
    samples: list[BearingSample] = field(default_factory=list)

    @property
    def last_timestamp(self) -> float:
        return self.samples[-1].timestamp

    @property
    def stable_sweep_count(self) -> int:
        return len({sample.sweep_index for sample in self.samples})

    def is_stable(self, required_sweeps: int) -> bool:
        return self.stable_sweep_count >= int(required_sweeps)

    @property
    def detection_uids(self) -> tuple[str, ...]:
        return tuple(uid for sample in self.samples for uid in sample.detection_uids)


@dataclass
class _OpenScanlet:
    scanlet_id: str
    camera_id: str
    sweep_index: int
    observations: list[RayObservation]

    @property
    def last_timestamp(self) -> float:
        return self.observations[-1].timestamp

    @property
    def mean_direction(self) -> np.ndarray:
        direction = np.mean(
            np.asarray([item.direction_ned for item in self.observations], dtype=float),
            axis=0,
        )
        return direction / max(float(np.linalg.norm(direction)), 1e-12)

    def representative(self) -> BearingSample:
        weights = np.asarray(
            [max(item.bbox_area_px2, 1.0) for item in self.observations],
            dtype=float,
        )
        weights /= float(np.sum(weights))
        directions = np.asarray(
            [item.direction_ned for item in self.observations], dtype=float
        )
        direction = np.sum(directions * weights[:, None], axis=0)
        direction /= max(float(np.linalg.norm(direction)), 1e-12)
        origins = np.asarray([item.origin_ned for item in self.observations], dtype=float)
        timestamps = np.asarray([item.timestamp for item in self.observations], dtype=float)
        return BearingSample(
            camera_id=self.camera_id,
            sweep_index=self.sweep_index,
            timestamp=float(np.sum(timestamps * weights)),
            origin_ned=tuple(float(value) for value in np.sum(origins * weights[:, None], axis=0)),
            direction_ned=tuple(float(value) for value in direction),
            detection_uids=tuple(item.detection_uid for item in self.observations),
            focal_length_px=float(
                np.sum(
                    np.asarray([item.focal_length_px for item in self.observations])
                    * weights
                )
            ),
            bbox_area_px2=float(
                max(item.bbox_area_px2 for item in self.observations)
            ),
        )


class ScanRevisitTracker:
    """Build camera-local tracks from sparse scan passages."""

    def __init__(
        self,
        camera_id: str,
        *,
        max_coast_s: float = 0.75,
        intra_sweep_gate_deg: float = 0.16,
        revisit_gate_deg: float = 0.45,
    ) -> None:
        self.camera_id = str(camera_id)
        self.max_coast_s = float(max_coast_s)
        self.intra_sweep_gate_deg = float(intra_sweep_gate_deg)
        self.revisit_gate_deg = float(revisit_gate_deg)
        self._current_sweep: int | None = None
        self._open_scanlets: list[_OpenScanlet] = []
        self._tracks: list[BearingTrack] = []
        self._next_scanlet = 1
        self._next_track = 1

    @property
    def tracks(self) -> tuple[BearingTrack, ...]:
        return tuple(self._tracks)

    def stable_tracks(self, required_sweeps: int = 4) -> tuple[BearingTrack, ...]:
        return tuple(
            track for track in self._tracks if track.is_stable(required_sweeps)
        )

    def update(
        self,
        *,
        sweep_index: int,
        timestamp: float,
        observations: Sequence[RayObservation],
    ) -> None:
        if any(item.camera_id != self.camera_id for item in observations):
            raise ValueError("observation camera does not match tracker camera")
        if self._current_sweep is None:
            self._current_sweep = int(sweep_index)
        if int(sweep_index) != self._current_sweep:
            self._finalize_open_scanlets()
            self._current_sweep = int(sweep_index)
        self._append_observations(list(observations), float(timestamp))

    def flush(self) -> None:
        self._finalize_open_scanlets()

    def _append_observations(
        self,
        observations: list[RayObservation],
        timestamp: float,
    ) -> None:
        if not observations:
            return
        if not self._open_scanlets:
            for observation in observations:
                self._new_scanlet(observation)
            return
        costs = np.full(
            (len(self._open_scanlets), len(observations)), 1e6, dtype=float
        )
        for row, scanlet in enumerate(self._open_scanlets):
            if timestamp - scanlet.last_timestamp > 0.06:
                continue
            for column, observation in enumerate(observations):
                angle = angular_distance_deg(
                    scanlet.mean_direction,
                    np.asarray(observation.direction_ned, dtype=float),
                )
                if angle <= self.intra_sweep_gate_deg:
                    costs[row, column] = angle
        rows, columns = linear_sum_assignment(costs)
        assigned_observations: set[int] = set()
        for row, column in zip(rows, columns):
            if costs[row, column] >= 1e5:
                continue
            self._open_scanlets[row].observations.append(observations[column])
            assigned_observations.add(int(column))
        for index, observation in enumerate(observations):
            if index not in assigned_observations:
                self._new_scanlet(observation)

    def _new_scanlet(self, observation: RayObservation) -> None:
        self._open_scanlets.append(
            _OpenScanlet(
                scanlet_id=f"{self.camera_id}-S{self._next_scanlet:05d}",
                camera_id=self.camera_id,
                sweep_index=observation.sweep_index,
                observations=[observation],
            )
        )
        self._next_scanlet += 1

    def _finalize_open_scanlets(self) -> None:
        if not self._open_scanlets:
            return
        samples = [scanlet.representative() for scanlet in self._open_scanlets]
        self._associate_samples_to_tracks(samples)
        self._open_scanlets = []

    def _associate_samples_to_tracks(self, samples: list[BearingSample]) -> None:
        if not samples:
            return
        active = [
            track
            for track in self._tracks
            if 0.0 < samples[0].timestamp - track.last_timestamp <= self.max_coast_s
        ]
        if not active:
            for sample in samples:
                self._new_track(sample)
            return
        costs = np.full((len(active), len(samples)), 1e6, dtype=float)
        for row, track in enumerate(active):
            for column, sample in enumerate(samples):
                predicted_azimuth, predicted_elevation = _predict_track_angles(
                    track, sample.timestamp
                )
                yaw_error = wrapped_angle_delta_deg(
                    predicted_azimuth, sample.azimuth_deg
                )
                elevation_error = sample.elevation_deg - predicted_elevation
                angle_error = math.hypot(
                    yaw_error * math.cos(math.radians(sample.elevation_deg)),
                    elevation_error,
                )
                if angle_error <= self.revisit_gate_deg:
                    costs[row, column] = angle_error
        rows, columns = linear_sum_assignment(costs)
        assigned_samples: set[int] = set()
        for row, column in zip(rows, columns):
            if costs[row, column] >= 1e5:
                continue
            active[row].samples.append(samples[column])
            assigned_samples.add(int(column))
        for index, sample in enumerate(samples):
            if index not in assigned_samples:
                self._new_track(sample)

    def _new_track(self, sample: BearingSample) -> None:
        self._tracks.append(
            BearingTrack(
                track_id=f"{self.camera_id}-T{self._next_track:04d}",
                camera_id=self.camera_id,
                samples=[sample],
            )
        )
        self._next_track += 1


@dataclass(frozen=True)
class CrossCameraCandidate:
    track_a_id: str
    track_b_id: str
    valid: bool
    rejection_reason: str
    cost: float
    reprojection_rms_px: float
    reprojection_max_px: float
    ray_residual_rms_m: float
    fitted_speed_mps: float
    median_nearest_time_delta_s: float
    condition_number: float
    observation_count: int
    inlier_count: int
    outlier_count: int
    reference_timestamp: float
    position_ned: tuple[float, float, float]
    velocity_ned: tuple[float, float, float]


@dataclass(frozen=True)
class CrossCameraMatch:
    match_id: str
    track_a_id: str
    track_b_id: str
    cost: float
    reference_timestamp: float
    position_ned: tuple[float, float, float]
    velocity_ned: tuple[float, float, float]


@dataclass(frozen=True)
class CrossAssociationResult:
    candidates: tuple[CrossCameraCandidate, ...]
    matches: tuple[CrossCameraMatch, ...]
    unmatched_a_track_ids: tuple[str, ...]
    unmatched_b_track_ids: tuple[str, ...]


def generate_target_specs(config: ScenarioConfig) -> tuple[TargetSpec, ...]:
    """Generate irregular depth-staggered crossing trajectories."""

    rng = np.random.default_rng(config.seed)
    count = config.target_count
    pair_count = count // 2
    base_lateral = np.linspace(-430.0, 430.0, max(pair_count, 1))
    if pair_count:
        base_lateral += rng.uniform(-12.0, 12.0, size=pair_count)
    # A fixed depth-lane spacing prevents physical overlap while the shuffled
    # lane order and crossing lateral motion keep the formation irregular.
    depth_lanes = np.linspace(1473.5, 2526.5, max(count, 1))
    if count:
        depth_lanes += rng.uniform(-0.35, 0.35, size=count)
        rng.shuffle(depth_lanes)
    targets: list[TargetSpec] = []
    for pair_index in range(pair_count):
        crossing_time = float(rng.uniform(3.0, 9.0))
        lateral_speed_magnitude = 6.0
        for member, sign in enumerate((1.0, -1.0)):
            index = pair_index * 2 + member
            lateral_speed = sign * lateral_speed_magnitude
            vertical_speed = 0.0
            approach_speed = math.sqrt(
                max(
                    config.target_speed_mps**2
                    - lateral_speed**2
                    - vertical_speed**2,
                    1e-6,
                )
            )
            start_y = float(base_lateral[pair_index] - lateral_speed * crossing_time)
            start_x = float(depth_lanes[index])
            start_z = float(-100.0 + rng.uniform(-18.0, 18.0))
            targets.append(
                TargetSpec(
                    truth_id=f"TRUTH-{index + 1:03d}",
                    actor_name=f"MSM_DualOptical_Target_{index + 1:03d}",
                    asset_name=config.target_asset_name,
                    start_ned=(start_x, start_y, start_z),
                    velocity_ned=(-approach_speed, lateral_speed, vertical_speed),
                )
            )
    if count % 2:
        index = count - 1
        lateral_speed = 6.0
        vertical_speed = 0.0
        approach_speed = math.sqrt(
            config.target_speed_mps**2 - lateral_speed**2 - vertical_speed**2
        )
        targets.append(
            TargetSpec(
                truth_id=f"TRUTH-{index + 1:03d}",
                actor_name=f"MSM_DualOptical_Target_{index + 1:03d}",
                asset_name=config.target_asset_name,
                start_ned=(float(depth_lanes[index]), 0.0, -100.0),
                velocity_ned=(-approach_speed, lateral_speed, vertical_speed),
            )
        )
    if any(not math.isclose(item.speed_mps, config.target_speed_mps, abs_tol=1e-9) for item in targets):
        raise RuntimeError("target generator failed to preserve the requested speed")
    return tuple(targets)


def look_angles_deg(
    camera_position_ned: Sequence[float], target_position_ned: Sequence[float]
) -> tuple[float, float]:
    delta = np.asarray(target_position_ned, dtype=float) - np.asarray(
        camera_position_ned, dtype=float
    )
    yaw = math.degrees(math.atan2(float(delta[1]), float(delta[0])))
    horizontal = math.hypot(float(delta[0]), float(delta[1]))
    pitch = math.degrees(-math.atan2(float(delta[2]), max(horizontal, 1e-12)))
    return yaw, pitch


def scan_yaw_deg(
    timestamp: float,
    base_yaw_deg: float,
    *,
    half_span_deg: float = 45.0,
    period_s: float = 1.0,
) -> float:
    phase = (float(timestamp) % float(period_s)) / float(period_s)
    if phase < 0.5:
        offset = -half_span_deg + 4.0 * half_span_deg * phase
    else:
        offset = 3.0 * half_span_deg - 4.0 * half_span_deg * phase
    return normalize_angle_deg(base_yaw_deg + offset)


def sweep_index(timestamp: float, *, period_s: float = 1.0) -> int:
    return int(math.floor(float(timestamp) / (0.5 * float(period_s)) + 1e-9))


def camera_rotation_world_from_local(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    rotation_yaw = np.asarray(
        ((cy, -sy, 0.0), (sy, cy, 0.0), (0.0, 0.0, 1.0)), dtype=float
    )
    rotation_pitch = np.asarray(
        ((cp, 0.0, sp), (0.0, 1.0, 0.0), (-sp, 0.0, cp)), dtype=float
    )
    return rotation_yaw @ rotation_pitch


def pixel_to_world_ray(
    pixel: Sequence[float], camera_state: CameraState, camera_spec: CameraSpec
) -> tuple[float, float, float]:
    focal = camera_spec.focal_length_px
    local = np.asarray(
        (
            1.0,
            (float(pixel[0]) - camera_spec.width * 0.5) / focal,
            (float(pixel[1]) - camera_spec.height * 0.5) / focal,
        ),
        dtype=float,
    )
    local /= float(np.linalg.norm(local))
    world = camera_rotation_world_from_local(
        camera_state.yaw_deg, camera_state.pitch_deg
    ) @ local
    world /= float(np.linalg.norm(world))
    return tuple(float(value) for value in world)


def project_world_point(
    point_ned: Sequence[float], camera_state: CameraState, camera_spec: CameraSpec
) -> tuple[float, float] | None:
    delta = np.asarray(point_ned, dtype=float) - np.asarray(
        camera_state.position_ned, dtype=float
    )
    local = camera_rotation_world_from_local(
        camera_state.yaw_deg, camera_state.pitch_deg
    ).T @ delta
    if local[0] <= 1e-6:
        return None
    focal = camera_spec.focal_length_px
    return (
        float(camera_spec.width * 0.5 + focal * local[1] / local[0]),
        float(camera_spec.height * 0.5 + focal * local[2] / local[0]),
    )


def ray_observation_from_detection(
    detection: AnonymousDetection,
    camera_state: CameraState,
    camera_spec: CameraSpec,
    *,
    scan_period_s: float = 1.0,
) -> RayObservation:
    return RayObservation(
        detection_uid=detection.detection_uid,
        camera_id=detection.camera_id,
        frame_index=detection.frame_index,
        timestamp=detection.measurement_timestamp,
        origin_ned=camera_state.position_ned,
        direction_ned=pixel_to_world_ray(
            detection.center_px, camera_state, camera_spec
        ),
        bbox_xyxy=detection.bbox_xyxy,
        sweep_index=sweep_index(
            detection.measurement_timestamp, period_s=scan_period_s
        ),
        camera_yaw_deg=camera_state.yaw_deg,
        camera_pitch_deg=camera_state.pitch_deg,
        focal_length_px=camera_spec.focal_length_px,
    )


def associate_tracks(
    tracks_a: Sequence[BearingTrack],
    tracks_b: Sequence[BearingTrack],
    *,
    expected_speed_mps: float = 50.0,
    max_time_delta_s: float = 0.20,
    unmatched_cost: float = 1.25,
) -> CrossAssociationResult:
    candidates = tuple(
        _fit_cross_camera_candidate(
            track_a,
            track_b,
            expected_speed_mps=expected_speed_mps,
            max_time_delta_s=max_time_delta_s,
        )
        for track_a in tracks_a
        for track_b in tracks_b
    )
    by_pair = {
        (candidate.track_a_id, candidate.track_b_id): candidate
        for candidate in candidates
    }
    count_a, count_b = len(tracks_a), len(tracks_b)
    if count_a == 0 or count_b == 0:
        return CrossAssociationResult(
            candidates=candidates,
            matches=(),
            unmatched_a_track_ids=tuple(track.track_id for track in tracks_a),
            unmatched_b_track_ids=tuple(track.track_id for track in tracks_b),
        )
    size = count_a + count_b
    matrix = np.full((size, size), 1e6, dtype=float)
    for row, track_a in enumerate(tracks_a):
        for column, track_b in enumerate(tracks_b):
            candidate = by_pair[(track_a.track_id, track_b.track_id)]
            if candidate.valid:
                matrix[row, column] = candidate.cost
        matrix[row, count_b + row] = unmatched_cost
    for column in range(count_b):
        matrix[count_a + column, column] = unmatched_cost
    matrix[count_a:, count_b:] = 0.0
    rows, columns = linear_sum_assignment(matrix)
    matches: list[CrossCameraMatch] = []
    matched_a: set[str] = set()
    matched_b: set[str] = set()
    for row, column in zip(rows, columns):
        if row >= count_a or column >= count_b:
            continue
        candidate = by_pair[(tracks_a[row].track_id, tracks_b[column].track_id)]
        if not candidate.valid or candidate.cost >= unmatched_cost:
            continue
        matches.append(
            CrossCameraMatch(
                match_id=f"PAIR-{len(matches) + 1:03d}",
                track_a_id=candidate.track_a_id,
                track_b_id=candidate.track_b_id,
                cost=candidate.cost,
                reference_timestamp=candidate.reference_timestamp,
                position_ned=candidate.position_ned,
                velocity_ned=candidate.velocity_ned,
            )
        )
        matched_a.add(candidate.track_a_id)
        matched_b.add(candidate.track_b_id)
    return CrossAssociationResult(
        candidates=candidates,
        matches=tuple(matches),
        unmatched_a_track_ids=tuple(
            track.track_id for track in tracks_a if track.track_id not in matched_a
        ),
        unmatched_b_track_ids=tuple(
            track.track_id for track in tracks_b if track.track_id not in matched_b
        ),
    )


def _fit_cross_camera_candidate(
    track_a: BearingTrack,
    track_b: BearingTrack,
    *,
    expected_speed_mps: float,
    max_time_delta_s: float,
) -> CrossCameraCandidate:
    samples = [*track_a.samples, *track_b.samples]
    reference_timestamp = float(np.median([sample.timestamp for sample in samples]))
    times_a = np.asarray([sample.timestamp for sample in track_a.samples], dtype=float)
    times_b = np.asarray([sample.timestamp for sample in track_b.samples], dtype=float)
    nearest_deltas = [
        float(np.min(np.abs(times_b - value))) for value in times_a
    ] + [float(np.min(np.abs(times_a - value))) for value in times_b]
    median_delta = float(np.median(nearest_deltas))
    inlier_indices = list(range(len(samples)))
    solution = np.zeros(6, dtype=float)
    rank = 0
    singular_values = np.asarray([], dtype=float)
    for _iteration in range(3):
        matrix, right = _ray_fit_system(
            samples, inlier_indices, reference_timestamp
        )
        solution, _, rank, singular_values = np.linalg.lstsq(matrix, right, rcond=None)
        errors = _candidate_reprojection_errors(
            samples, solution, reference_timestamp
        )
        proposed = [
            index for index, error in enumerate(errors) if error <= 15.0
        ]
        camera_counts = {
            track_a.camera_id: sum(
                samples[index].camera_id == track_a.camera_id for index in proposed
            ),
            track_b.camera_id: sum(
                samples[index].camera_id == track_b.camera_id for index in proposed
            ),
        }
        if (
            proposed == inlier_indices
            or min(camera_counts.values(), default=0) < 4
        ):
            break
        inlier_indices = proposed
    matrix, right = _ray_fit_system(samples, inlier_indices, reference_timestamp)
    solution, _, rank, singular_values = np.linalg.lstsq(matrix, right, rcond=None)
    condition_number = (
        float(singular_values[0] / singular_values[-1])
        if len(singular_values) >= 6 and singular_values[-1] > 1e-12
        else float("inf")
    )
    position = solution[:3]
    velocity = solution[3:]
    speed = float(np.linalg.norm(velocity))
    ray_residuals: list[float] = []
    reprojection_errors: list[float] = []
    positive_depth = True
    for index in inlier_indices:
        sample = samples[index]
        predicted = position + velocity * (sample.timestamp - reference_timestamp)
        delta = predicted - np.asarray(sample.origin_ned, dtype=float)
        direction = np.asarray(sample.direction_ned, dtype=float)
        depth = float(np.dot(delta, direction))
        positive_depth = positive_depth and depth > 0.0
        perpendicular = delta - direction * depth
        ray_residuals.append(float(np.linalg.norm(perpendicular)))
        predicted_direction = delta / max(float(np.linalg.norm(delta)), 1e-12)
        angle = math.acos(
            float(np.clip(np.dot(predicted_direction, direction), -1.0, 1.0))
        )
        reprojection_errors.append(float(sample.focal_length_px * math.tan(angle)))
    reprojection_rms = float(
        math.sqrt(np.mean(np.square(reprojection_errors)))
    )
    reprojection_max = float(max(reprojection_errors, default=float("inf")))
    ray_rms = float(math.sqrt(np.mean(np.square(ray_residuals))))
    reasons: list[str] = []
    if rank < 6:
        reasons.append("rank_deficient")
    if median_delta > max_time_delta_s:
        reasons.append("time_delta")
    if reprojection_rms > 8.0 or reprojection_max > 15.0:
        reasons.append("reprojection")
    if not 35.0 <= speed <= 65.0:
        reasons.append("speed")
    if condition_number > 1e4:
        reasons.append("condition")
    inlier_ratio = len(inlier_indices) / max(len(samples), 1)
    if inlier_ratio < 0.85:
        reasons.append("inlier_ratio")
    if not positive_depth:
        reasons.append("negative_depth")
    if velocity[0] > -25.0:
        reasons.append("not_inbound")
    valid = not reasons
    cost = (
        0.55 * min(reprojection_rms / 8.0, 10.0)
        + 0.15 * min(ray_rms / 5.0, 10.0)
        + 0.15 * min(abs(speed - expected_speed_mps) / 15.0, 10.0)
        + 0.10 * min(median_delta / max(max_time_delta_s, 1e-9), 10.0)
        + 0.05 * min(math.log10(max(condition_number, 1.0)) / 4.0, 10.0)
        + 0.05 * (1.0 - inlier_ratio)
    )
    return CrossCameraCandidate(
        track_a_id=track_a.track_id,
        track_b_id=track_b.track_id,
        valid=valid,
        rejection_reason="|".join(reasons),
        cost=float(cost),
        reprojection_rms_px=reprojection_rms,
        reprojection_max_px=reprojection_max,
        ray_residual_rms_m=ray_rms,
        fitted_speed_mps=speed,
        median_nearest_time_delta_s=median_delta,
        condition_number=condition_number,
        observation_count=len(samples),
        inlier_count=len(inlier_indices),
        outlier_count=len(samples) - len(inlier_indices),
        reference_timestamp=reference_timestamp,
        position_ned=tuple(float(value) for value in position),
        velocity_ned=tuple(float(value) for value in velocity),
    )


def _ray_fit_system(
    samples: Sequence[BearingSample],
    indices: Sequence[int],
    reference_timestamp: float,
) -> tuple[np.ndarray, np.ndarray]:
    matrix_rows: list[np.ndarray] = []
    right_rows: list[np.ndarray] = []
    for index in indices:
        sample = samples[index]
        direction = np.asarray(sample.direction_ned, dtype=float)
        projector = np.eye(3, dtype=float) - np.outer(direction, direction)
        relative_time = sample.timestamp - reference_timestamp
        matrix_rows.append(
            np.concatenate((projector, projector * relative_time), axis=1)
        )
        right_rows.append(projector @ np.asarray(sample.origin_ned, dtype=float))
    return np.vstack(matrix_rows), np.concatenate(right_rows)


def _candidate_reprojection_errors(
    samples: Sequence[BearingSample],
    solution: np.ndarray,
    reference_timestamp: float,
) -> list[float]:
    position = solution[:3]
    velocity = solution[3:]
    errors: list[float] = []
    for sample in samples:
        predicted = position + velocity * (sample.timestamp - reference_timestamp)
        delta = predicted - np.asarray(sample.origin_ned, dtype=float)
        predicted_direction = delta / max(float(np.linalg.norm(delta)), 1e-12)
        measured_direction = np.asarray(sample.direction_ned, dtype=float)
        angle = math.acos(
            float(
                np.clip(
                    np.dot(predicted_direction, measured_direction), -1.0, 1.0
                )
            )
        )
        errors.append(float(sample.focal_length_px * math.tan(angle)))
    return errors


def _predict_track_angles(
    track: BearingTrack, timestamp: float
) -> tuple[float, float]:
    samples = track.samples[-5:]
    if len(samples) < 2:
        return samples[-1].azimuth_deg, samples[-1].elevation_deg
    times = np.asarray([sample.timestamp for sample in samples], dtype=float)
    centered = times - times[-1]
    azimuths = np.unwrap(
        np.radians([sample.azimuth_deg for sample in samples])
    )
    elevations = np.asarray([sample.elevation_deg for sample in samples], dtype=float)
    design = np.column_stack((np.ones(len(samples)), centered))
    azimuth_fit = np.linalg.lstsq(design, azimuths, rcond=None)[0]
    elevation_fit = np.linalg.lstsq(design, elevations, rcond=None)[0]
    horizon = float(timestamp - times[-1])
    return (
        normalize_angle_deg(math.degrees(azimuth_fit[0] + azimuth_fit[1] * horizon)),
        float(elevation_fit[0] + elevation_fit[1] * horizon),
    )


def angular_distance_deg(first: np.ndarray, second: np.ndarray) -> float:
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    first /= max(float(np.linalg.norm(first)), 1e-12)
    second /= max(float(np.linalg.norm(second)), 1e-12)
    return math.degrees(
        math.acos(float(np.clip(np.dot(first, second), -1.0, 1.0)))
    )


def wrapped_angle_delta_deg(first: float, second: float) -> float:
    return (float(second) - float(first) + 180.0) % 360.0 - 180.0


def normalize_angle_deg(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def minimum_target_separation(
    targets: Iterable[TargetSpec], duration_s: float, *, sample_count: int = 121
) -> float:
    target_list = list(targets)
    minimum = float("inf")
    for timestamp in np.linspace(0.0, float(duration_s), int(sample_count)):
        positions = np.asarray(
            [target.position_at(float(timestamp)) for target in target_list], dtype=float
        )
        for index in range(len(positions)):
            if index + 1 >= len(positions):
                continue
            distances = np.linalg.norm(positions[index + 1 :] - positions[index], axis=1)
            minimum = min(minimum, float(np.min(distances)))
    return minimum


FORBIDDEN_ONLINE_KEY_TOKENS = (
    "actor",
    "object_id",
    "truth",
    "box3d",
    "relative_pose",
    "global_track",
)


def online_truth_leakage_keys(records: Iterable[dict[str, object]]) -> tuple[str, ...]:
    leaked: set[str] = set()

    def visit(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                key_path = f"{path}.{key}" if path else str(key)
                lower = str(key).lower()
                if any(token in lower for token in FORBIDDEN_ONLINE_KEY_TOKENS):
                    leaked.add(key_path)
                visit(item, key_path)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    for index, record in enumerate(records):
        visit(record, f"record[{index}]")
    return tuple(sorted(leaked))
