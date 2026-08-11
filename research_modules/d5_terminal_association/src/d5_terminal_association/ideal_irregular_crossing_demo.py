"""Ideal irregular 3D crossing scene with narrow-field gimbal scanning.

This scenario is isolated from the original all-visible baseline.  A 100 Hz
analytic timeline drives camera visibility and confirmation dwell, while the
point-mass state is defined at 0.1 s and linearly propagated between physics
ticks.  Hungarian registration runs only when a five-frame dwell is complete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import atan2, cos, degrees, hypot, radians, sin, sqrt, tan
from typing import Iterable, Sequence

import numpy as np

from research_modules.scalable_3d_simulation.camera_projection import (
    CameraIntrinsics,
    CameraPose,
    look_at_rotation_ned_to_camera,
    project_points,
)

from .ideal_registration_demo import (
    TemporalCostResult,
    build_temporal_cost_matrix,
    solve_complete_assignment,
)


IRREGULAR_CROSSING_SCHEMA_VERSION = "d5-ideal-irregular-crossing-v1"
SCAN_MODES = ("mechanical_2s", "coverage_safe")


@dataclass(frozen=True)
class IrregularCrossingConfig:
    """Parameters for the ideal irregular crossing and scan experiment."""

    target_count: int = 20
    seed: int = 20260810
    duration_s: float = 15.0
    physics_dt_s: float = 0.1
    scan_dt_s: float = 0.01
    association_media_period_s: float = 0.1
    target_speed_min_mps: float = 3.5
    target_speed_max_mps: float = 4.7
    camera_a_position_ned: tuple[float, float, float] = (0.0, 0.0, -50.0)
    target_center_range_m: float = 3000.0
    target_range_span_m: float = 360.0
    target_center_elevation_deg: float = 2.5
    target_pair_radial_offset_m: float = 15.0
    target_pair_azimuth_separation_deg: float = 0.08
    target_pair_lateral_speed_mps: float = 0.30
    camera_b_trailing_distance_m: float = 500.0
    camera_a_width_px: int = 2600
    camera_a_height_px: int = 2160
    camera_a_horizontal_fov_deg: float = 0.621
    camera_b_width_px: int = 1920
    camera_b_height_px: int = 1080
    camera_b_horizontal_fov_deg: float = 2.750979
    search_sector_min_deg: float = -22.5
    search_sector_max_deg: float = 22.5
    mechanical_scan_speed_deg_s: float = 180.0
    coverage_safe_scan_speed_deg_s: float = 49.68
    camera_b_max_slew_deg_s: float = 180.0
    confirmation_frames: int = 5
    temporal_window_frames: int = 5
    position_scale_px: float = 20.0
    displacement_scale_px: float = 10.0
    displacement_weight: float = 0.25
    covariance_regularization: float = 1.0e-6
    crossing_near_ratio_of_width: float = 0.025

    def __post_init__(self) -> None:
        if self.target_count <= 0:
            raise ValueError("target_count must be positive")
        for name in (
            "duration_s",
            "physics_dt_s",
            "scan_dt_s",
            "association_media_period_s",
            "target_speed_min_mps",
            "target_speed_max_mps",
            "target_center_range_m",
            "target_range_span_m",
            "target_pair_radial_offset_m",
            "camera_b_trailing_distance_m",
            "mechanical_scan_speed_deg_s",
            "coverage_safe_scan_speed_deg_s",
            "camera_b_max_slew_deg_s",
            "position_scale_px",
            "displacement_scale_px",
            "covariance_regularization",
            "crossing_near_ratio_of_width",
        ):
            if float(getattr(self, name)) <= 0.0:
                raise ValueError(f"{name} must be positive")
        if self.target_speed_max_mps < self.target_speed_min_mps:
            raise ValueError("target speed range is invalid")
        if self.scan_dt_s > self.physics_dt_s:
            raise ValueError("scan_dt_s must not exceed physics_dt_s")
        if not np.isclose(
            self.physics_dt_s / self.scan_dt_s,
            round(self.physics_dt_s / self.scan_dt_s),
        ):
            raise ValueError("physics_dt_s must be an integer multiple of scan_dt_s")
        if self.search_sector_min_deg >= self.search_sector_max_deg:
            raise ValueError("search sector bounds are invalid")
        if self.confirmation_frames <= 0 or self.temporal_window_frames <= 0:
            raise ValueError("frame counts must be positive")
        if self.displacement_weight < 0.0:
            raise ValueError("displacement_weight must be non-negative")
        if self.target_pair_lateral_speed_mps >= self.target_speed_min_mps:
            raise ValueError("lateral speed must remain below total target speed")

    @property
    def confirmation_dwell_time_s(self) -> float:
        return float(self.confirmation_frames * self.scan_dt_s)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.update(
            {
                "schema_version": IRREGULAR_CROSSING_SCHEMA_VERSION,
                "working_frame": "NED",
                "scan_timeline_rate_hz": 1.0 / self.scan_dt_s,
                "physics_rate_hz": 1.0 / self.physics_dt_s,
                "association_media_rate_hz": 1.0 / self.association_media_period_s,
                "measurement_arrival_timestamp_policy": "equal_ideal_time",
                "online_truth_policy": "offline_sidecar_only",
            }
        )
        return payload


@dataclass(frozen=True)
class CrossingPair:
    """One projected pair satisfying intersection or normalized near crossing."""

    first_global_track_id: str
    second_global_track_id: str
    minimum_segment_distance_px: float
    normalized_distance_by_width: float
    exact_segment_intersection: bool


@dataclass(frozen=True)
class IrregularGeometry:
    """Center-owned point-mass geometry and reference image projections."""

    global_track_ids: tuple[str, ...]
    physics_timestamps: np.ndarray
    target_state_history_ned: np.ndarray
    global_covariances: np.ndarray
    camera_a_reference_pixels: np.ndarray
    camera_b_reference_pixels: np.ndarray
    camera_b_position_history_ned: np.ndarray
    initial_radial_span_m: float
    initial_altitude_span_m: float
    minimum_pairwise_3d_separation_m: float
    projected_crossing_pairs_a: tuple[CrossingPair, ...]
    projected_crossing_pairs_b: tuple[CrossingPair, ...]


@dataclass(frozen=True)
class ScanTimelineRecord:
    """One truth-free 100 Hz scan state record."""

    scan_index: int
    measurement_timestamp: float
    arrival_timestamp: float
    center_scan_state: str
    center_boresight_relative_azimuth_deg: float
    center_boresight_elevation_deg: float
    center_visible_anonymous_count: int
    center_confirmed_count: int
    camera_b_scan_state: str
    camera_b_boresight_azimuth_deg: float
    camera_b_boresight_elevation_deg: float
    camera_b_active_cue_global_track_id: str | None
    camera_b_confirmed_count: int


@dataclass(frozen=True)
class AnonymousPixelObservation:
    """Online local observation with dual timestamps and covariance."""

    stage: str
    camera_id: str
    local_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    center_px: tuple[float, float]
    covariance_px: np.ndarray


@dataclass(frozen=True)
class ScanAssociationEvent:
    """One event-level complete/rectangular Hungarian solve."""

    stage: str
    measurement_timestamp: float
    arrival_timestamp: float
    global_track_ids: tuple[str, ...]
    local_track_ids: tuple[str, ...]
    cost: TemporalCostResult
    selected_pairs: tuple[tuple[str, str], ...]
    selected_costs: tuple[float, ...]


@dataclass(frozen=True)
class ScanModeRun:
    """Online output for one scan mode."""

    mode: str
    scan_speed_deg_s: float
    timeline: tuple[ScanTimelineRecord, ...]
    observations: tuple[AnonymousPixelObservation, ...]
    stage_a_events: tuple[ScanAssociationEvent, ...]
    stage_b_events: tuple[ScanAssociationEvent, ...]
    global_to_camera_a: tuple[tuple[str, str], ...]
    global_camera_a_to_camera_b: tuple[tuple[str, str, str], ...]
    center_detection_event_times: tuple[tuple[str, float], ...]
    camera_b_detection_event_times: tuple[tuple[str, float], ...]
    scan_actual_duration_s: float
    revisit_interval_s: float | None
    confirmation_dwell_time_s: float


@dataclass(frozen=True)
class IrregularCrossingRun:
    """Online run containing geometry and both scan modes, without truth mapping."""

    config: IrregularCrossingConfig
    geometry: IrregularGeometry
    camera_a_intrinsics: CameraIntrinsics
    camera_b_intrinsics: CameraIntrinsics
    modes: tuple[ScanModeRun, ...]
    center_global_track_ids_before: tuple[str, ...]
    center_global_track_ids_after: tuple[str, ...]
    online_truth_usage_count: int = 0

    def mode(self, name: str) -> ScanModeRun:
        for result in self.modes:
            if result.mode == name:
                return result
        raise KeyError(name)


@dataclass(frozen=True)
class IrregularOfflineTruth:
    """Evaluator-only mapping kept out of online scan and association inputs."""

    seed: int
    global_to_camera_a: tuple[tuple[str, str], ...]
    global_to_camera_b: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ScanModeMetrics:
    """Offline metrics for one mode and seed."""

    seed: int
    mode: str
    target_count: int
    initial_radial_span_m: float
    initial_altitude_span_m: float
    minimum_pairwise_3d_separation_m: float
    projected_crossing_pair_count_a: int
    projected_crossing_pair_count_b: int
    center_discovery_ratio: float
    camera_b_cued_observation_ratio: float
    camera_b_cued_observation_available: bool
    complete_chain_ratio: float
    scan_actual_duration_s: float
    confirmation_dwell_time_s: float
    revisit_interval_s: float | None
    stage_a_association_accuracy: float | None
    stage_b_association_accuracy: float | None
    end_to_end_association_accuracy: float | None
    id_switch_count: int
    duplicate_assignment_count: int
    unmatched_count: int
    online_truth_usage_count: int
    global_track_id_rewrite_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def coverage_safe_acceptance_passed(self) -> bool:
        return bool(
            self.mode == "coverage_safe"
            and np.isclose(self.center_discovery_ratio, 1.0)
            and np.isclose(self.camera_b_cued_observation_ratio, 1.0)
            and np.isclose(self.complete_chain_ratio, 1.0)
            and self.stage_a_association_accuracy is not None
            and np.isclose(self.stage_a_association_accuracy, 1.0)
            and self.stage_b_association_accuracy is not None
            and np.isclose(self.stage_b_association_accuracy, 1.0)
            and self.end_to_end_association_accuracy is not None
            and np.isclose(self.end_to_end_association_accuracy, 1.0)
            and self.id_switch_count == 0
            and self.duplicate_assignment_count == 0
            and self.unmatched_count == 0
            and self.online_truth_usage_count == 0
            and self.global_track_id_rewrite_count == 0
        )


@dataclass(frozen=True)
class _DwellSample:
    timestamp: float
    projected_pixels_all: np.ndarray
    local_track_ids: tuple[str, ...]
    local_pixels: np.ndarray
    camera_id: str


def run_irregular_crossing_experiment(
    config: IrregularCrossingConfig | None = None,
    *,
    modes: Sequence[str] = SCAN_MODES,
) -> tuple[IrregularCrossingRun, IrregularOfflineTruth]:
    """Run the ideal geometry and requested scan modes."""

    resolved = config or IrregularCrossingConfig()
    for mode in modes:
        if mode not in SCAN_MODES:
            raise ValueError(f"unsupported scan mode: {mode}")
    rng = np.random.default_rng(resolved.seed)
    states, global_ids = _initial_states(resolved, rng)
    camera_a_ids_by_global = _shuffled_ids("A", resolved.target_count, rng)
    camera_b_ids_by_global = _shuffled_ids("B", resolved.target_count, rng)
    camera_a_intrinsics = _intrinsics(
        resolved.camera_a_width_px,
        resolved.camera_a_height_px,
        resolved.camera_a_horizontal_fov_deg,
    )
    camera_b_intrinsics = _intrinsics(
        resolved.camera_b_width_px,
        resolved.camera_b_height_px,
        resolved.camera_b_horizontal_fov_deg,
    )
    geometry = _build_geometry(
        resolved,
        states,
        global_ids,
        camera_a_intrinsics,
        camera_b_intrinsics,
    )
    mode_runs = tuple(
        _run_scan_mode(
            resolved,
            geometry,
            camera_a_intrinsics,
            camera_b_intrinsics,
            camera_a_ids_by_global,
            camera_b_ids_by_global,
            mode,
        )
        for mode in modes
    )
    online_run = IrregularCrossingRun(
        config=resolved,
        geometry=geometry,
        camera_a_intrinsics=camera_a_intrinsics,
        camera_b_intrinsics=camera_b_intrinsics,
        modes=mode_runs,
        center_global_track_ids_before=global_ids,
        center_global_track_ids_after=global_ids,
        online_truth_usage_count=0,
    )
    offline_truth = IrregularOfflineTruth(
        seed=resolved.seed,
        global_to_camera_a=tuple(zip(global_ids, camera_a_ids_by_global, strict=True)),
        global_to_camera_b=tuple(zip(global_ids, camera_b_ids_by_global, strict=True)),
    )
    return online_run, offline_truth


def evaluate_irregular_crossing(
    online_run: IrregularCrossingRun,
    offline_truth: IrregularOfflineTruth,
) -> tuple[ScanModeMetrics, ...]:
    """Evaluate mode outputs using the separate offline identity sidecar."""

    if online_run.config.seed != offline_truth.seed:
        raise ValueError("online run and offline truth seed must match")
    expected_a = dict(offline_truth.global_to_camera_a)
    expected_b = dict(offline_truth.global_to_camera_b)
    rewrite_count = sum(
        before != after
        for before, after in zip(
            online_run.center_global_track_ids_before,
            online_run.center_global_track_ids_after,
            strict=True,
        )
    )
    results: list[ScanModeMetrics] = []
    for mode in online_run.modes:
        stage_a = dict(mode.global_to_camera_a)
        chains = {
            global_id: (camera_a_id, camera_b_id)
            for global_id, camera_a_id, camera_b_id in mode.global_camera_a_to_camera_b
        }
        stage_b = {global_id: value[1] for global_id, value in chains.items()}
        correct_a = sum(stage_a[global_id] == expected_a[global_id] for global_id in stage_a)
        correct_b = sum(stage_b[global_id] == expected_b[global_id] for global_id in stage_b)
        correct_chain = sum(
            chains[global_id] == (expected_a[global_id], expected_b[global_id])
            for global_id in chains
        )
        duplicate_count = len(stage_a) - len(set(stage_a.values()))
        duplicate_count += len(stage_b) - len(set(stage_b.values()))
        cue_count = len(stage_a)
        results.append(
            ScanModeMetrics(
                seed=online_run.config.seed,
                mode=mode.mode,
                target_count=online_run.config.target_count,
                initial_radial_span_m=online_run.geometry.initial_radial_span_m,
                initial_altitude_span_m=online_run.geometry.initial_altitude_span_m,
                minimum_pairwise_3d_separation_m=(
                    online_run.geometry.minimum_pairwise_3d_separation_m
                ),
                projected_crossing_pair_count_a=len(
                    online_run.geometry.projected_crossing_pairs_a
                ),
                projected_crossing_pair_count_b=len(
                    online_run.geometry.projected_crossing_pairs_b
                ),
                center_discovery_ratio=len(stage_a) / online_run.config.target_count,
                camera_b_cued_observation_ratio=(len(stage_b) / cue_count if cue_count else 0.0),
                camera_b_cued_observation_available=cue_count > 0,
                complete_chain_ratio=len(chains) / online_run.config.target_count,
                scan_actual_duration_s=mode.scan_actual_duration_s,
                confirmation_dwell_time_s=mode.confirmation_dwell_time_s,
                revisit_interval_s=mode.revisit_interval_s,
                stage_a_association_accuracy=(correct_a / len(stage_a) if stage_a else None),
                stage_b_association_accuracy=(correct_b / len(stage_b) if stage_b else None),
                end_to_end_association_accuracy=(
                    correct_chain / len(chains) if chains else None
                ),
                id_switch_count=_id_switch_count(mode),
                duplicate_assignment_count=duplicate_count,
                unmatched_count=online_run.config.target_count - len(chains),
                online_truth_usage_count=online_run.online_truth_usage_count,
                global_track_id_rewrite_count=int(rewrite_count),
            )
        )
    return tuple(results)


def run_irregular_seed_batch(
    seeds: Iterable[int],
    *,
    base_config: IrregularCrossingConfig | None = None,
) -> tuple[ScanModeMetrics, ...]:
    """Run coverage-safe mode for a seed batch without writing media."""

    template = base_config or IrregularCrossingConfig()
    results: list[ScanModeMetrics] = []
    for seed in seeds:
        payload = asdict(template)
        payload["seed"] = int(seed)
        online_run, offline_truth = run_irregular_crossing_experiment(
            IrregularCrossingConfig(**payload), modes=("coverage_safe",)
        )
        results.append(evaluate_irregular_crossing(online_run, offline_truth)[0])
    return tuple(results)


def _initial_states(
    config: IrregularCrossingConfig,
    rng: np.random.Generator,
) -> tuple[np.ndarray, tuple[str, ...]]:
    count = config.target_count
    pair_count = count // 2
    states = np.zeros((count, 6), dtype=float)
    global_ids = tuple(f"GT-{index + 1:03d}" for index in range(count))
    camera_a = np.asarray(config.camera_a_position_ned, dtype=float)
    gap_centers = np.array([-1.8, 0.0, 1.8, -1.8, 0.0, 1.8, -1.8, 0.0, 1.8, 0.0])
    elevation_offsets = np.array(
        [-0.18, 0.16, -0.08, 0.20, 0.0, -0.16, 0.10, 0.05, -0.20, 0.14]
    )
    radial_centers = np.linspace(
        config.target_center_range_m - 0.5 * config.target_range_span_m,
        config.target_center_range_m + 0.5 * config.target_range_span_m,
        max(pair_count, 1),
    )
    state_index = 0
    for pair_index in range(pair_count):
        center_azimuth = float(gap_centers[pair_index % len(gap_centers)])
        elevation_offset = float(
            elevation_offsets[pair_index % len(elevation_offsets)]
        )
        separation = config.target_pair_azimuth_separation_deg + 0.01 * sin(
            1.3 * pair_index
        )
        lateral_speed = config.target_pair_lateral_speed_mps + 0.03 * cos(
            0.7 * pair_index
        )
        pair_speed = float(
            rng.uniform(config.target_speed_min_mps, config.target_speed_max_mps)
        )
        radial_speed = sqrt(max(pair_speed**2 - lateral_speed**2, 1.0e-12))
        for side in (-1.0, 1.0):
            azimuth = radians(center_azimuth + side * 0.5 * separation)
            elevation = radians(config.target_center_elevation_deg + elevation_offset)
            radial_distance = radial_centers[pair_index] + (
                side * config.target_pair_radial_offset_m
            )
            radial_unit = np.array(
                [
                    cos(elevation) * cos(azimuth),
                    cos(elevation) * sin(azimuth),
                    -sin(elevation),
                ],
                dtype=float,
            )
            azimuth_tangent = np.array(
                [-sin(azimuth), cos(azimuth), 0.0], dtype=float
            )
            states[state_index, :3] = camera_a + radial_distance * radial_unit
            states[state_index, 3:] = (
                -radial_speed * radial_unit
                + (-side) * lateral_speed * azimuth_tangent
            )
            state_index += 1
    if count % 2:
        azimuth = radians(5.4)
        elevation = radians(config.target_center_elevation_deg - 0.12)
        radial_unit = np.array(
            [
                cos(elevation) * cos(azimuth),
                cos(elevation) * sin(azimuth),
                -sin(elevation),
            ]
        )
        speed = float(
            rng.uniform(config.target_speed_min_mps, config.target_speed_max_mps)
        )
        states[-1, :3] = camera_a + (
            config.target_center_range_m + 0.5 * config.target_range_span_m
        ) * radial_unit
        states[-1, 3:] = -speed * radial_unit
    return states, global_ids


def _build_geometry(
    config: IrregularCrossingConfig,
    initial_states: np.ndarray,
    global_ids: tuple[str, ...],
    camera_a_intrinsics: CameraIntrinsics,
    camera_b_intrinsics: CameraIntrinsics,
) -> IrregularGeometry:
    timestamps = np.arange(
        0.0,
        config.duration_s + 0.5 * config.physics_dt_s,
        config.physics_dt_s,
    )
    positions = (
        initial_states[None, :, :3]
        + timestamps[:, None, None] * initial_states[None, :, 3:]
    )
    velocities = np.broadcast_to(
        initial_states[None, :, 3:], positions.shape
    ).copy()
    states = np.concatenate((positions, velocities), axis=2)
    camera_a_position = np.asarray(config.camera_a_position_ned, dtype=float)
    initial_centroid = np.mean(positions[0], axis=0)
    trailing_unit = (initial_centroid - camera_a_position) / np.linalg.norm(
        initial_centroid - camera_a_position
    )
    trailing_offset = -config.camera_b_trailing_distance_m * trailing_unit
    camera_b_positions = np.mean(positions, axis=1) + trailing_offset[None, :]
    reference_pose_a = CameraPose(
        position_ned=camera_a_position,
        rotation_camera_from_ned=look_at_rotation_ned_to_camera(
            camera_a_position, initial_centroid
        ),
    )
    pixels_a: list[np.ndarray] = []
    pixels_b: list[np.ndarray] = []
    for frame_index, target_positions in enumerate(positions):
        centroid = np.mean(target_positions, axis=0)
        pixels_a.append(
            project_points(
                target_positions,
                camera_pose=reference_pose_a,
                intrinsics=camera_a_intrinsics,
                pixel_noise_std=0.0,
            ).pixel_centers
        )
        camera_b_position = camera_b_positions[frame_index]
        pixels_b.append(
            project_points(
                target_positions,
                camera_pose=CameraPose(
                    position_ned=camera_b_position,
                    rotation_camera_from_ned=look_at_rotation_ned_to_camera(
                        camera_b_position, centroid
                    ),
                ),
                intrinsics=camera_b_intrinsics,
                pixel_noise_std=0.0,
            ).pixel_centers
        )
    radial_distance = np.linalg.norm(positions[0] - camera_a_position[None, :], axis=1)
    altitude = -positions[0, :, 2]
    minimum_separation = float("inf")
    for target_positions in positions:
        differences = target_positions[:, None, :] - target_positions[None, :, :]
        distances = np.linalg.norm(differences, axis=2)
        distances += np.eye(config.target_count) * 1.0e12
        minimum_separation = min(minimum_separation, float(np.min(distances)))
    covariance = np.broadcast_to(
        np.eye(6) * config.covariance_regularization,
        (len(timestamps), config.target_count, 6, 6),
    ).copy()
    return IrregularGeometry(
        global_track_ids=global_ids,
        physics_timestamps=timestamps,
        target_state_history_ned=states,
        global_covariances=covariance,
        camera_a_reference_pixels=np.stack(pixels_a),
        camera_b_reference_pixels=np.stack(pixels_b),
        camera_b_position_history_ned=camera_b_positions,
        initial_radial_span_m=float(np.ptp(radial_distance)),
        initial_altitude_span_m=float(np.ptp(altitude)),
        minimum_pairwise_3d_separation_m=minimum_separation,
        projected_crossing_pairs_a=_projected_crossings(
            np.stack(pixels_a),
            global_ids,
            camera_a_intrinsics.width_px,
            config.crossing_near_ratio_of_width,
        ),
        projected_crossing_pairs_b=_projected_crossings(
            np.stack(pixels_b),
            global_ids,
            camera_b_intrinsics.width_px,
            config.crossing_near_ratio_of_width,
        ),
    )


def _run_scan_mode(
    config: IrregularCrossingConfig,
    geometry: IrregularGeometry,
    camera_a_intrinsics: CameraIntrinsics,
    camera_b_intrinsics: CameraIntrinsics,
    camera_a_ids_by_global: tuple[str, ...],
    camera_b_ids_by_global: tuple[str, ...],
    mode: str,
) -> ScanModeRun:
    scan_speed = (
        config.mechanical_scan_speed_deg_s
        if mode == "mechanical_2s"
        else config.coverage_safe_scan_speed_deg_s
    )
    initial_states = geometry.target_state_history_ned[0]
    camera_a_position = np.asarray(config.camera_a_position_ned, dtype=float)
    initial_centroid = np.mean(initial_states[:, :3], axis=0)
    trailing_unit = (initial_centroid - camera_a_position) / np.linalg.norm(
        initial_centroid - camera_a_position
    )
    trailing_offset = -config.camera_b_trailing_distance_m * trailing_unit

    center_boresight_relative = config.search_sector_min_deg
    center_scan_direction = 1.0
    center_dwell_indices: tuple[int, ...] | None = None
    center_dwell_samples: list[_DwellSample] = []
    center_bindings: dict[str, str] = {}
    center_detection_times: dict[str, float] = {}
    center_visibility_times: dict[str, list[float]] = {
        local_id: [] for local_id in camera_a_ids_by_global
    }

    b_initial_vector = initial_centroid - (initial_centroid + trailing_offset)
    camera_b_azimuth, camera_b_elevation = _vector_angles(b_initial_vector)
    camera_b_dwell_index: int | None = None
    camera_b_dwell_samples: list[_DwellSample] = []
    camera_b_bindings: dict[str, str] = {}
    camera_b_detection_times: dict[str, float] = {}

    timeline: list[ScanTimelineRecord] = []
    observations: list[AnonymousPixelObservation] = []
    stage_a_events: list[ScanAssociationEvent] = []
    stage_b_events: list[ScanAssociationEvent] = []
    covariance_px = np.eye(2) * config.covariance_regularization
    scan_count = int(round(config.duration_s / config.scan_dt_s)) + 1

    for scan_index in range(scan_count):
        timestamp = float(scan_index * config.scan_dt_s)
        states = _state_at(initial_states, timestamp)
        target_positions = states[:, :3]
        centroid = np.mean(target_positions, axis=0)
        center_vector = centroid - camera_a_position
        center_azimuth, center_elevation = _vector_angles(center_vector)
        target_azimuths, target_elevations = _angles_from_camera(
            camera_a_position, target_positions
        )
        center_absolute_azimuth = center_azimuth + center_boresight_relative
        center_visible_indices = tuple(
            index
            for index in range(config.target_count)
            if _inside_fov(
                target_azimuths[index],
                target_elevations[index],
                center_absolute_azimuth,
                center_elevation,
                config.camera_a_horizontal_fov_deg,
                _vertical_fov_deg(camera_a_intrinsics),
            )
        )
        for target_index in center_visible_indices:
            center_visibility_times[camera_a_ids_by_global[target_index]].append(timestamp)

        center_pose = _pose_from_angles(
            camera_a_position, center_absolute_azimuth, center_elevation
        )
        center_projection = project_points(
            target_positions,
            camera_pose=center_pose,
            intrinsics=camera_a_intrinsics,
            pixel_noise_std=0.0,
        ).pixel_centers

        if center_dwell_indices is None:
            unbound_visible = tuple(
                index
                for index in center_visible_indices
                if geometry.global_track_ids[index] not in center_bindings
            )
            if unbound_visible:
                center_dwell_indices = unbound_visible
                center_dwell_samples = []
        if center_dwell_indices is not None:
            sample = _dwell_sample(
                timestamp,
                center_projection,
                center_dwell_indices,
                camera_a_ids_by_global,
                "CAMERA-A-CENTER",
            )
            center_dwell_samples.append(sample)
            observations.extend(_observations_from_sample(sample, covariance_px, "stage_a"))
            if len(center_dwell_samples) >= config.confirmation_frames:
                available_indices = tuple(
                    index
                    for index, global_id in enumerate(geometry.global_track_ids)
                    if global_id not in center_bindings
                )
                event = _associate_dwell(
                    "stage_a",
                    geometry.global_track_ids,
                    available_indices,
                    center_dwell_samples,
                    config,
                )
                stage_a_events.append(event)
                for global_id, local_id in event.selected_pairs:
                    center_bindings[global_id] = local_id
                    center_detection_times[global_id] = timestamp
                center_dwell_indices = None
                center_dwell_samples = []
        else:
            center_boresight_relative += (
                center_scan_direction * scan_speed * config.scan_dt_s
            )
            if center_boresight_relative > config.search_sector_max_deg:
                center_boresight_relative = (
                    2.0 * config.search_sector_max_deg - center_boresight_relative
                )
                center_scan_direction = -1.0
            elif center_boresight_relative < config.search_sector_min_deg:
                center_boresight_relative = (
                    2.0 * config.search_sector_min_deg - center_boresight_relative
                )
                center_scan_direction = 1.0

        camera_b_position = centroid + trailing_offset
        b_target_azimuths, b_target_elevations = _angles_from_camera(
            camera_b_position, target_positions
        )
        pending_indices = tuple(
            index
            for index, global_id in enumerate(geometry.global_track_ids)
            if global_id in center_bindings and global_id not in camera_b_bindings
        )
        if camera_b_dwell_index is None and pending_indices:
            camera_b_dwell_index = min(
                pending_indices,
                key=lambda index: _angular_distance_deg(
                    camera_b_azimuth,
                    camera_b_elevation,
                    b_target_azimuths[index],
                    b_target_elevations[index],
                ),
            )
            camera_b_dwell_samples = []
        if camera_b_dwell_index is not None:
            target_azimuth = float(b_target_azimuths[camera_b_dwell_index])
            target_elevation = float(b_target_elevations[camera_b_dwell_index])
            camera_b_azimuth, camera_b_elevation = _slew_angles(
                camera_b_azimuth,
                camera_b_elevation,
                target_azimuth,
                target_elevation,
                config.camera_b_max_slew_deg_s * config.scan_dt_s,
            )
            b_pose = _pose_from_angles(
                camera_b_position, camera_b_azimuth, camera_b_elevation
            )
            b_projection = project_points(
                target_positions,
                camera_pose=b_pose,
                intrinsics=camera_b_intrinsics,
                pixel_noise_std=0.0,
            ).pixel_centers
            if _inside_fov(
                target_azimuth,
                target_elevation,
                camera_b_azimuth,
                camera_b_elevation,
                config.camera_b_horizontal_fov_deg,
                _vertical_fov_deg(camera_b_intrinsics),
            ):
                sample = _dwell_sample(
                    timestamp,
                    b_projection,
                    (camera_b_dwell_index,),
                    camera_b_ids_by_global,
                    "CAMERA-B-INTERCEPTOR",
                )
                camera_b_dwell_samples.append(sample)
                observations.extend(
                    _observations_from_sample(sample, covariance_px, "stage_b")
                )
            else:
                camera_b_dwell_samples = []
            if len(camera_b_dwell_samples) >= config.confirmation_frames:
                available_indices = tuple(
                    index
                    for index, global_id in enumerate(geometry.global_track_ids)
                    if global_id in center_bindings and global_id not in camera_b_bindings
                )
                event = _associate_dwell(
                    "stage_b",
                    geometry.global_track_ids,
                    available_indices,
                    camera_b_dwell_samples,
                    config,
                )
                stage_b_events.append(event)
                for global_id, local_id in event.selected_pairs:
                    camera_b_bindings[global_id] = local_id
                    camera_b_detection_times[global_id] = timestamp
                camera_b_dwell_index = None
                camera_b_dwell_samples = []
        active_cue = (
            geometry.global_track_ids[camera_b_dwell_index]
            if camera_b_dwell_index is not None
            else None
        )
        timeline.append(
            ScanTimelineRecord(
                scan_index=scan_index,
                measurement_timestamp=timestamp,
                arrival_timestamp=timestamp,
                center_scan_state=(
                    "confirmation_dwell" if center_dwell_indices is not None else "search"
                ),
                center_boresight_relative_azimuth_deg=float(
                    center_boresight_relative
                ),
                center_boresight_elevation_deg=float(center_elevation),
                center_visible_anonymous_count=len(center_visible_indices),
                center_confirmed_count=len(center_bindings),
                camera_b_scan_state=(
                    "cued_confirmation_dwell"
                    if camera_b_dwell_index is not None
                    else ("awaiting_cue" if not pending_indices else "cued_slew")
                ),
                camera_b_boresight_azimuth_deg=float(camera_b_azimuth),
                camera_b_boresight_elevation_deg=float(camera_b_elevation),
                camera_b_active_cue_global_track_id=active_cue,
                camera_b_confirmed_count=len(camera_b_bindings),
            )
        )

    chains = tuple(
        (global_id, center_bindings[global_id], camera_b_bindings[global_id])
        for global_id in geometry.global_track_ids
        if global_id in center_bindings and global_id in camera_b_bindings
    )
    complete_time = (
        max(camera_b_detection_times.values())
        if len(chains) == config.target_count
        else config.duration_s
    )
    return ScanModeRun(
        mode=mode,
        scan_speed_deg_s=scan_speed,
        timeline=tuple(timeline),
        observations=tuple(observations),
        stage_a_events=tuple(stage_a_events),
        stage_b_events=tuple(stage_b_events),
        global_to_camera_a=tuple(
            (global_id, center_bindings[global_id])
            for global_id in geometry.global_track_ids
            if global_id in center_bindings
        ),
        global_camera_a_to_camera_b=chains,
        center_detection_event_times=tuple(center_detection_times.items()),
        camera_b_detection_event_times=tuple(camera_b_detection_times.items()),
        scan_actual_duration_s=float(complete_time),
        revisit_interval_s=_revisit_interval(center_visibility_times, config.scan_dt_s),
        confirmation_dwell_time_s=config.confirmation_dwell_time_s,
    )


def _associate_dwell(
    stage: str,
    all_global_ids: tuple[str, ...],
    available_indices: tuple[int, ...],
    samples: Sequence[_DwellSample],
    config: IrregularCrossingConfig,
) -> ScanAssociationEvent:
    local_ids = samples[0].local_track_ids
    if any(sample.local_track_ids != local_ids for sample in samples):
        raise ValueError("dwell local track set must remain stable")
    projected_history = [
        sample.projected_pixels_all[np.asarray(available_indices, dtype=int)]
        for sample in samples
    ]
    anonymous_history = [sample.local_pixels for sample in samples]
    cost = build_temporal_cost_matrix(
        projected_history,
        anonymous_history,
        window_frames=config.temporal_window_frames,
        position_scale_px=config.position_scale_px,
        displacement_scale_px=config.displacement_scale_px,
        displacement_weight=config.displacement_weight,
    )
    global_ids = tuple(all_global_ids[index] for index in available_indices)
    selected_pairs, selected_costs = solve_complete_assignment(
        global_ids, local_ids, cost
    )
    return ScanAssociationEvent(
        stage=stage,
        measurement_timestamp=samples[-1].timestamp,
        arrival_timestamp=samples[-1].timestamp,
        global_track_ids=global_ids,
        local_track_ids=local_ids,
        cost=cost,
        selected_pairs=selected_pairs,
        selected_costs=selected_costs,
    )


def _dwell_sample(
    timestamp: float,
    projected_pixels: np.ndarray,
    target_indices: tuple[int, ...],
    local_ids_by_global: tuple[str, ...],
    camera_id: str,
) -> _DwellSample:
    ordered = tuple(
        sorted(target_indices, key=lambda index: local_ids_by_global[index])
    )
    return _DwellSample(
        timestamp=timestamp,
        projected_pixels_all=projected_pixels.copy(),
        local_track_ids=tuple(local_ids_by_global[index] for index in ordered),
        local_pixels=projected_pixels[np.asarray(ordered, dtype=int)].copy(),
        camera_id=camera_id,
    )


def _observations_from_sample(
    sample: _DwellSample,
    covariance_px: np.ndarray,
    stage: str,
) -> tuple[AnonymousPixelObservation, ...]:
    return tuple(
        AnonymousPixelObservation(
            stage=stage,
            camera_id=sample.camera_id,
            local_track_id=local_id,
            measurement_timestamp=sample.timestamp,
            arrival_timestamp=sample.timestamp,
            center_px=(float(pixel[0]), float(pixel[1])),
            covariance_px=covariance_px.copy(),
        )
        for local_id, pixel in zip(
            sample.local_track_ids, sample.local_pixels, strict=True
        )
    )


def _state_at(initial_states: np.ndarray, timestamp: float) -> np.ndarray:
    states = initial_states.copy()
    states[:, :3] += float(timestamp) * states[:, 3:]
    return states


def _intrinsics(width: int, height: int, horizontal_fov_deg: float) -> CameraIntrinsics:
    focal = 0.5 * width / tan(0.5 * radians(horizontal_fov_deg))
    return CameraIntrinsics(
        width_px=width,
        height_px=height,
        fx=focal,
        fy=focal,
        cx=0.5 * (width - 1),
        cy=0.5 * (height - 1),
    )


def _vertical_fov_deg(intrinsics: CameraIntrinsics) -> float:
    return degrees(2.0 * np.arctan(0.5 * intrinsics.height_px / intrinsics.fy))


def _angles_from_camera(
    camera_position: np.ndarray, target_positions: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    delta = target_positions - camera_position[None, :]
    azimuth = np.degrees(np.arctan2(delta[:, 1], delta[:, 0]))
    elevation = np.degrees(np.arctan2(-delta[:, 2], np.hypot(delta[:, 0], delta[:, 1])))
    return azimuth, elevation


def _vector_angles(vector: np.ndarray) -> tuple[float, float]:
    return (
        degrees(atan2(float(vector[1]), float(vector[0]))),
        degrees(atan2(float(-vector[2]), hypot(float(vector[0]), float(vector[1])))),
    )


def _pose_from_angles(
    camera_position: np.ndarray, azimuth_deg: float, elevation_deg: float
) -> CameraPose:
    azimuth = radians(azimuth_deg)
    elevation = radians(elevation_deg)
    direction = np.array(
        [
            cos(elevation) * cos(azimuth),
            cos(elevation) * sin(azimuth),
            -sin(elevation),
        ]
    )
    return CameraPose(
        position_ned=camera_position,
        rotation_camera_from_ned=look_at_rotation_ned_to_camera(
            camera_position, camera_position + 1000.0 * direction
        ),
    )


def _inside_fov(
    target_azimuth: float,
    target_elevation: float,
    boresight_azimuth: float,
    boresight_elevation: float,
    horizontal_fov: float,
    vertical_fov: float,
) -> bool:
    return bool(
        abs(_wrap_degrees(target_azimuth - boresight_azimuth))
        <= 0.5 * horizontal_fov + 1.0e-12
        and abs(target_elevation - boresight_elevation)
        <= 0.5 * vertical_fov + 1.0e-12
    )


def _slew_angles(
    current_azimuth: float,
    current_elevation: float,
    target_azimuth: float,
    target_elevation: float,
    maximum_step_deg: float,
) -> tuple[float, float]:
    delta_azimuth = _wrap_degrees(target_azimuth - current_azimuth)
    delta_elevation = target_elevation - current_elevation
    distance = hypot(delta_azimuth, delta_elevation)
    if distance <= maximum_step_deg:
        return target_azimuth, target_elevation
    scale = maximum_step_deg / distance
    return (
        _wrap_degrees(current_azimuth + scale * delta_azimuth),
        current_elevation + scale * delta_elevation,
    )


def _angular_distance_deg(
    first_azimuth: float,
    first_elevation: float,
    second_azimuth: float,
    second_elevation: float,
) -> float:
    return hypot(
        _wrap_degrees(second_azimuth - first_azimuth),
        second_elevation - first_elevation,
    )


def _wrap_degrees(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def _projected_crossings(
    pixel_history: np.ndarray,
    global_ids: tuple[str, ...],
    image_width: int,
    near_ratio: float,
) -> tuple[CrossingPair, ...]:
    threshold = near_ratio * image_width
    pairs: list[CrossingPair] = []
    for first in range(len(global_ids)):
        for second in range(first + 1, len(global_ids)):
            minimum_distance = float("inf")
            exact = False
            for frame_index in range(pixel_history.shape[0] - 1):
                distance, intersects = _segment_distance(
                    pixel_history[frame_index, first],
                    pixel_history[frame_index + 1, first],
                    pixel_history[frame_index, second],
                    pixel_history[frame_index + 1, second],
                )
                minimum_distance = min(minimum_distance, distance)
                exact = exact or intersects
            if exact or minimum_distance <= threshold:
                pairs.append(
                    CrossingPair(
                        first_global_track_id=global_ids[first],
                        second_global_track_id=global_ids[second],
                        minimum_segment_distance_px=minimum_distance,
                        normalized_distance_by_width=minimum_distance / image_width,
                        exact_segment_intersection=exact,
                    )
                )
    return tuple(pairs)


def _segment_distance(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
) -> tuple[float, bool]:
    first_direction = first_end - first_start
    second_direction = second_end - second_start
    denominator = _cross_2d(first_direction, second_direction)
    if abs(denominator) > 1.0e-12:
        relative = second_start - first_start
        first_parameter = _cross_2d(relative, second_direction) / denominator
        second_parameter = _cross_2d(relative, first_direction) / denominator
        if 0.0 <= first_parameter <= 1.0 and 0.0 <= second_parameter <= 1.0:
            return 0.0, True
    distance = min(
        _point_segment_distance(first_start, second_start, second_end),
        _point_segment_distance(first_end, second_start, second_end),
        _point_segment_distance(second_start, first_start, first_end),
        _point_segment_distance(second_end, first_start, first_end),
    )
    return float(distance), False


def _point_segment_distance(
    point: np.ndarray, segment_start: np.ndarray, segment_end: np.ndarray
) -> float:
    direction = segment_end - segment_start
    denominator = max(float(np.dot(direction, direction)), 1.0e-12)
    parameter = float(
        np.clip(np.dot(point - segment_start, direction) / denominator, 0.0, 1.0)
    )
    closest = segment_start + parameter * direction
    return float(np.linalg.norm(point - closest))


def _cross_2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(first[0] * second[1] - first[1] * second[0])


def _revisit_interval(
    visibility_times: dict[str, list[float]], scan_dt_s: float
) -> float | None:
    intervals: list[float] = []
    for times in visibility_times.values():
        if not times:
            continue
        cluster_starts = [times[0]]
        previous = times[0]
        for timestamp in times[1:]:
            if timestamp - previous > 1.5 * scan_dt_s:
                cluster_starts.append(timestamp)
            previous = timestamp
        intervals.extend(
            second - first
            for first, second in zip(cluster_starts, cluster_starts[1:])
        )
    return float(np.median(intervals)) if intervals else None


def _id_switch_count(mode: ScanModeRun) -> int:
    switches = 0
    seen_a: dict[str, str] = {}
    seen_b: dict[str, str] = {}
    for event in mode.stage_a_events:
        for global_id, local_id in event.selected_pairs:
            if global_id in seen_a and seen_a[global_id] != local_id:
                switches += 1
            seen_a[global_id] = local_id
    for event in mode.stage_b_events:
        for global_id, local_id in event.selected_pairs:
            if global_id in seen_b and seen_b[global_id] != local_id:
                switches += 1
            seen_b[global_id] = local_id
    return switches


def _shuffled_ids(
    prefix: str, count: int, rng: np.random.Generator
) -> tuple[str, ...]:
    values = np.array(
        [f"{prefix}-L{index + 1:03d}" for index in range(count)], dtype=object
    )
    rng.shuffle(values)
    return tuple(str(value) for value in values.tolist())
