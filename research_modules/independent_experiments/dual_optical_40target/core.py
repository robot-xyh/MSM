"""Geometry and association core for the independent dual-optical experiment."""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import math
import time
from typing import Iterable, Literal, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.stats import chi2


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
    scan_mode: Literal["triangle", "continuous_360"] = "triangle"
    target_motion_profile: Literal[
        "legacy_crossing", "split_0_minus30"
    ] = "legacy_crossing"
    gimbal_pose_error_enabled: bool = False
    gimbal_fixed_bias_mrad: float = 0.4
    gimbal_jitter_rms_mrad: float = 0.3
    deterministic_step_mode: Literal[
        "legacy_wall_yield", "paused_continue"
    ] = "legacy_wall_yield"
    track_coast_s: float = 0.75
    stable_sweep_count: int = 4
    max_cross_camera_time_delta_s: float = 0.20
    api_port: int = 41451
    clock_speed: float = 0.1
    camera_name: str = "0"
    camera_a_name: str = "Optical_A"
    camera_b_name: str = "Optical_B"
    camera_b_scan_phase_offset_s: float = 0.0

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
        if self.scan_mode not in {"triangle", "continuous_360"}:
            raise ValueError("unsupported scan mode")
        if self.scan_mode == "continuous_360":
            if not math.isclose(self.scan_period_s, 2.0, abs_tol=1e-9):
                raise ValueError("continuous_360 requires a 2.0 s scan period")
            if math.isclose(self.track_coast_s, 0.75, abs_tol=1e-12):
                object.__setattr__(self, "track_coast_s", 2.5)
        if self.target_motion_profile not in {
            "legacy_crossing",
            "split_0_minus30",
        }:
            raise ValueError("unsupported target motion profile")
        if self.gimbal_fixed_bias_mrad < 0.0 or self.gimbal_jitter_rms_mrad < 0.0:
            raise ValueError("gimbal error magnitudes must be non-negative")
        if self.deterministic_step_mode not in {
            "legacy_wall_yield",
            "paused_continue",
        }:
            raise ValueError("unsupported deterministic step mode")
        if self.track_coast_s <= 0.0 or self.stable_sweep_count < 2:
            raise ValueError("invalid revisit-track settings")
        if not 0.0 <= self.camera_b_scan_phase_offset_s < self.scan_period_s:
            raise ValueError("camera B scan phase offset must be within one scan period")

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
    heading_offset_deg: float | None = None

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
    gimbal_command_timestamp: float | None = None
    detection_rpc_start_timestamp: float | None = None
    detection_rpc_end_timestamp: float | None = None
    measurement_timestamp_source: str = "scripted_scene_logical_time"
    gimbal_command_timestamp_source: str = "unavailable"
    arrival_timestamp_source: str = "producer_clock_unspecified"
    detection_rpc_timestamp_source: str = "unavailable"


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
    measurement_covariance_rad2: tuple[tuple[float, float], tuple[float, float]] = (
        (2.5e-7, 0.0),
        (0.0, 2.5e-7),
    )
    pose_covariance_rad2: tuple[tuple[float, float], tuple[float, float]] = (
        (2.5e-7, 0.0),
        (0.0, 2.5e-7),
    )
    prediction_covariance_rad2: tuple[tuple[float, float], tuple[float, float]] = (
        (4.0e-6, 0.0),
        (0.0, 4.0e-6),
    )
    azimuth_rate_rad_s: float = 0.0
    elevation_rate_rad_s: float = 0.0
    kinematic_state_covariance: tuple[tuple[float, ...], ...] = (
        (4.0e-6, 0.0, 0.0, 0.0),
        (0.0, 4.0e-6, 0.0, 0.0),
        (0.0, 0.0, 1.0e-6, 0.0),
        (0.0, 0.0, 0.0, 1.0e-6),
    )
    covariance_source: str = "legacy_conservative_default"

    @property
    def angular_covariance_rad2(self) -> np.ndarray:
        covariance = (
            np.asarray(self.measurement_covariance_rad2, dtype=float)
            + np.asarray(self.pose_covariance_rad2, dtype=float)
            + np.asarray(self.prediction_covariance_rad2, dtype=float)
        )
        return _regularize_covariance(covariance)

    def predicted_angular_covariance_rad2(self, timestamp: float) -> np.ndarray:
        state_covariance = np.asarray(self.kinematic_state_covariance, dtype=float)
        if state_covariance.shape != (4, 4) or not np.all(
            np.isfinite(state_covariance)
        ):
            state_covariance = np.diag((4.0e-6, 4.0e-6, 1.0e-6, 1.0e-6))
        dt = float(timestamp - self.timestamp)
        transition = np.asarray(
            (
                (1.0, 0.0, dt, 0.0),
                (0.0, 1.0, 0.0, dt),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
            dtype=float,
        )
        propagated = transition @ state_covariance @ transition.T
        return _regularize_covariance(
            np.asarray(self.measurement_covariance_rad2, dtype=float)
            + np.asarray(self.pose_covariance_rad2, dtype=float)
            + propagated[:2, :2]
        )

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
    hit_history: tuple[bool, ...] = ()
    track_state: str = "legacy"
    state_covariance: tuple[tuple[float, ...], ...] = ()

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
    normalized_reprojection_chi2: float = float("inf")
    normalized_reprojection_dof: int = 0
    normalized_reprojection_gate: float = float("inf")
    covariance_gate_confidence: float = 0.99


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


AssociationState = Literal[
    "tentative", "pending", "confirmed", "coasting", "rejected"
]


@dataclass(frozen=True)
class AssociationConfig:
    expected_speed_mps: float = 50.0
    max_time_delta_s: float = 0.20
    unmatched_cost: float = 1.25
    coplanarity_median_gate_mrad: float = 0.50
    covariance_gate_confidence: float = 0.99
    min_aligned_samples: int = 2
    minimum_track_sweeps: int = 2
    decision_period_s: float = 0.50
    top_k: int = 3
    history_discount: float = 0.80
    assignment_switch_penalty: float = 0.10
    crossing_separation_deg: float = 0.20
    competing_support_gate: float = 0.25
    confirmation_window: int = 3
    confirmation_hits: int = 2
    confirmation_support: float = 0.70
    contradiction_epochs: int = 2
    coasting_duration_s: float = 1.0
    hypothesis_temperature: float = 0.20
    ambiguity_resolution_revolutions: int = 2
    ambiguity_support_margin: float = 0.10
    ambiguity_cost_margin: float = 0.05
    fragment_merge_position_gate_m: float = 5.0
    fragment_merge_velocity_gate_mps: float = 2.0
    online_prefilter_multiplier: float = 3.0

    def __post_init__(self) -> None:
        if self.expected_speed_mps <= 0.0 or self.max_time_delta_s <= 0.0:
            raise ValueError("speed and time-delta settings must be positive")
        if self.unmatched_cost <= 0.0 or self.coplanarity_median_gate_mrad <= 0.0:
            raise ValueError("association gates must be positive")
        if self.covariance_gate_confidence not in {0.95, 0.975, 0.99, 0.995}:
            raise ValueError("unsupported chi-square confidence")
        if self.min_aligned_samples < 2 or self.minimum_track_sweeps < 2:
            raise ValueError("insufficient temporal evidence requirement")
        if self.decision_period_s <= 0.0 or self.top_k <= 0:
            raise ValueError("decision period and top_k must be positive")
        if not 0.0 <= self.history_discount < 1.0:
            raise ValueError("history_discount must be in [0, 1)")
        if self.assignment_switch_penalty < 0.0:
            raise ValueError("assignment_switch_penalty must be non-negative")
        if self.crossing_separation_deg <= 0.0:
            raise ValueError("crossing separation must be positive")
        if not 0.0 <= self.competing_support_gate <= 1.0:
            raise ValueError("competing support gate must be in [0, 1]")
        if not 1 <= self.confirmation_hits <= self.confirmation_window:
            raise ValueError("invalid confirmation hit/window settings")
        if not 0.0 <= self.confirmation_support <= 1.0:
            raise ValueError("confirmation support must be in [0, 1]")
        if self.contradiction_epochs <= 0 or self.coasting_duration_s < 0.0:
            raise ValueError("invalid contradiction or coasting settings")
        if self.hypothesis_temperature <= 0.0:
            raise ValueError("hypothesis temperature must be positive")
        if self.ambiguity_resolution_revolutions < 2:
            raise ValueError("ambiguity resolution requires at least two revolutions")
        if not 0.0 <= self.ambiguity_support_margin <= 1.0:
            raise ValueError("ambiguity support margin must be in [0, 1]")
        if self.ambiguity_cost_margin < 0.0:
            raise ValueError("ambiguity cost margin must be non-negative")
        if (
            self.fragment_merge_position_gate_m <= 0.0
            or self.fragment_merge_velocity_gate_mps <= 0.0
        ):
            raise ValueError("fragment merge gates must be positive")
        if self.online_prefilter_multiplier < 1.0:
            raise ValueError("online prefilter multiplier must be at least one")


@dataclass(frozen=True)
class EpipolarEvidence:
    track_a_id: str
    track_b_id: str
    gate_passed: bool
    rejection_reason: str
    aligned_sample_count: int
    timestamps_s: tuple[float, ...]
    residuals_mrad: tuple[float, ...]
    residual_median_mrad: float
    residual_p90_mrad: float
    residual_mad_mrad: float
    residual_slope_mrad_per_s: float
    intersection_angle_median_deg: float
    normalized_residuals_chi2: tuple[float, ...] = ()
    normalized_residual_median_chi2: float = float("inf")
    normalized_residual_p90_chi2: float = float("inf")
    chi_square_gate: float = float("inf")
    covariance_gate_confidence: float = 0.99
    covariance_source: str = "legacy_conservative_default"


@dataclass(frozen=True)
class GlobalAssignmentHypothesis:
    hypothesis_id: str
    rank: int
    total_cost: float
    normalized_support: float
    matches: tuple[tuple[str, str], ...]
    unmatched_a_track_ids: tuple[str, ...]
    unmatched_b_track_ids: tuple[str, ...]


@dataclass(frozen=True)
class AssociationDecisionRecord:
    epoch_index: int
    timestamp: float
    active_a_track_count: int
    active_b_track_count: int
    full_pair_count: int
    coarse_gate_pass_count: int
    fit_evaluation_count: int
    valid_fit_count: int
    hypothesis_count: int
    best_hypothesis_cost: float | None


@dataclass(frozen=True)
class AssociationHypothesisRecord:
    epoch_index: int
    timestamp: float
    rank: int
    total_cost: float
    normalized_support: float
    match_count: int
    matches: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class AssociationStateRecord:
    epoch_index: int
    timestamp: float
    track_a_id: str
    track_b_id: str
    state: AssociationState
    pair_support: float
    smoothed_support: float
    competing_support: float
    crossing_alert: bool
    mapping_hits_in_window: int
    contradiction_streak: int
    reason: str
    ambiguity_age_revolutions: int = 0
    retained_hypothesis_count: int = 1


@dataclass(frozen=True)
class TemporalAssociationResult:
    config: AssociationConfig
    epipolar_evidence: tuple[EpipolarEvidence, ...]
    fitted_candidates: tuple[CrossCameraCandidate, ...]
    hypotheses: tuple[GlobalAssignmentHypothesis, ...]
    decisions: tuple[AssociationDecisionRecord, ...]
    hypothesis_history: tuple[AssociationHypothesisRecord, ...]
    state_history: tuple[AssociationStateRecord, ...]
    fragment_suppressions: tuple[FragmentSuppressionRecord, ...]
    selected_matches: tuple[CrossCameraMatch, ...]
    confirmed_matches: tuple[CrossCameraMatch, ...]
    unmatched_a_track_ids: tuple[str, ...]
    unmatched_b_track_ids: tuple[str, ...]
    full_pair_count: int
    coarse_gate_pass_count: int
    fit_evaluation_count: int
    candidate_screening_elapsed_ms: float = 0.0
    candidate_fitting_elapsed_ms: float = 0.0
    processing_elapsed_ms: float = 0.0


@dataclass(frozen=True)
class GeometrySensitivity:
    track_a_id: str
    track_b_id: str
    reference_timestamp: float
    angular_noise_mrad: float
    requested_sample_count: int
    valid_sample_count: int
    intersection_angle_deg: float
    range_a_m: float
    range_b_m: float
    position_sensitivity_p50_m: float
    position_sensitivity_p95_m: float
    evidence_label: str = "modeled_geometry_sensitivity"


@dataclass(frozen=True)
class FragmentSuppressionRecord:
    retained_track_a_id: str
    retained_track_b_id: str
    suppressed_track_a_id: str
    suppressed_track_b_id: str
    comparison_timestamp: float
    predicted_position_delta_m: float
    velocity_delta_mps: float
    reason: str = "duplicate_constant_velocity_fragment"


def _ambiguity_resolution(
    pair: tuple[str, str],
    *,
    selected_pairs: set[tuple[str, str]],
    pair_supports: Mapping[tuple[str, str], float],
    smoothed_supports: Mapping[tuple[str, str], float],
    candidate_costs: Mapping[tuple[str, str], float],
    previous_age: int,
    ambiguous: bool,
    config: AssociationConfig,
) -> tuple[int, bool, int]:
    """Age and resolve one bounded ambiguity without using identity labels."""

    competitors = sorted(
        candidate_pair
        for candidate_pair in pair_supports
        if candidate_pair != pair
        and (candidate_pair[0] == pair[0] or candidate_pair[1] == pair[1])
    )
    retained_count = min(config.top_k, 1 + len(competitors))
    if not ambiguous:
        return 0, False, retained_count
    age = previous_age + 1
    if age < config.ambiguity_resolution_revolutions or pair not in selected_pairs:
        return age, False, retained_count
    contenders = [pair, *competitors]
    ranked = sorted(
        contenders,
        key=lambda candidate_pair: (
            -float(smoothed_supports.get(candidate_pair, 0.0)),
            float(candidate_costs.get(candidate_pair, math.inf)),
            candidate_pair[0],
            candidate_pair[1],
        ),
    )
    if ranked[0] != pair:
        return age, False, retained_count
    if len(ranked) == 1:
        sufficient = (
            float(smoothed_supports.get(pair, 0.0))
            >= config.confirmation_support
        )
    else:
        runner_up = ranked[1]
        support_margin = float(smoothed_supports.get(pair, 0.0)) - float(
            smoothed_supports.get(runner_up, 0.0)
        )
        cost_margin = float(candidate_costs.get(runner_up, math.inf)) - float(
            candidate_costs.get(pair, math.inf)
        )
        sufficient = bool(
            support_margin >= config.ambiguity_support_margin
            and cost_margin >= config.ambiguity_cost_margin
        )
    return age, sufficient, retained_count


def generate_target_specs(config: ScenarioConfig) -> tuple[TargetSpec, ...]:
    """Generate irregular depth-staggered crossing trajectories."""

    if config.target_motion_profile == "split_0_minus30":
        return _generate_split_heading_target_specs(config)

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
                    actor_name=(
                        f"MSM_DualOptical_S{config.seed}_Target_{index + 1:03d}"
                    ),
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
                actor_name=(
                    f"MSM_DualOptical_S{config.seed}_Target_{index + 1:03d}"
                ),
                asset_name=config.target_asset_name,
                start_ned=(float(depth_lanes[index]), 0.0, -100.0),
                velocity_ned=(-approach_speed, lateral_speed, vertical_speed),
            )
        )
    if any(not math.isclose(item.speed_mps, config.target_speed_mps, abs_tol=1e-9) for item in targets):
        raise RuntimeError("target generator failed to preserve the requested speed")
    return tuple(targets)


def _generate_split_heading_target_specs(
    config: ScenarioConfig,
) -> tuple[TargetSpec, ...]:
    """Generate spatially interleaved 0/-30 degree inbound target groups."""

    rng = np.random.default_rng(config.seed)
    count = config.target_count
    depth_lanes = np.linspace(1473.5, 2526.5, count, dtype=float)
    depth_lanes += rng.uniform(-0.35, 0.35, size=count)
    rng.shuffle(depth_lanes)
    lateral_lanes = np.linspace(-430.0, 430.0, count, dtype=float)
    lateral_lanes += rng.uniform(-8.0, 8.0, size=count)
    # A cyclic permutation decouples depth order from lateral order while the
    # alternating group labels keep both headings present across the corridor.
    lateral_lanes = np.roll(lateral_lanes, int(rng.integers(0, max(count, 1))))
    first_group_is_zero = bool(rng.integers(0, 2))
    targets: list[TargetSpec] = []
    for index in range(count):
        zero_degree_group = (index % 2 == 0) == first_group_is_zero
        heading_offset_deg = 0.0 if zero_degree_group else -30.0
        relative_heading_rad = math.radians(heading_offset_deg)
        velocity = (
            -config.target_speed_mps * math.cos(relative_heading_rad),
            -config.target_speed_mps * math.sin(relative_heading_rad),
            0.0,
        )
        targets.append(
            TargetSpec(
                truth_id=f"TRUTH-{index + 1:03d}",
                actor_name=(
                    f"MSM_DualOptical_S{config.seed}_Target_{index + 1:03d}"
                ),
                asset_name=config.target_asset_name,
                start_ned=(
                    float(depth_lanes[index]),
                    float(lateral_lanes[index]),
                    float(-100.0 + rng.uniform(-18.0, 18.0)),
                ),
                velocity_ned=tuple(float(value) for value in velocity),
                heading_offset_deg=heading_offset_deg,
            )
        )
    if any(
        not math.isclose(item.speed_mps, config.target_speed_mps, abs_tol=1e-9)
        for item in targets
    ):
        raise RuntimeError("split-heading generator failed to preserve speed")
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
    mode: Literal["triangle", "continuous_360"] = "triangle",
) -> float:
    phase = (float(timestamp) % float(period_s)) / float(period_s)
    if mode == "continuous_360":
        offset = 360.0 * phase
    elif mode == "triangle":
        if phase < 0.5:
            offset = -half_span_deg + 4.0 * half_span_deg * phase
        else:
            offset = 3.0 * half_span_deg - 4.0 * half_span_deg * phase
    else:
        raise ValueError(f"unsupported scan mode: {mode}")
    return normalize_angle_deg(base_yaw_deg + offset)


def sweep_index(
    timestamp: float,
    *,
    period_s: float = 1.0,
    mode: Literal["triangle", "continuous_360"] = "triangle",
) -> int:
    divisor = float(period_s) if mode == "continuous_360" else 0.5 * float(period_s)
    if mode not in {"triangle", "continuous_360"}:
        raise ValueError(f"unsupported scan mode: {mode}")
    return int(math.floor(float(timestamp) / divisor + 1e-9))


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
    scan_mode: Literal["triangle", "continuous_360"] = "triangle",
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
            detection.measurement_timestamp,
            period_s=scan_period_s,
            mode=scan_mode,
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
            covariance_gate_confidence=0.99,
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


def normalized_symmetric_coplanarity_mrad(
    origin_a: Sequence[float],
    direction_a: Sequence[float],
    origin_b: Sequence[float],
    direction_b: Sequence[float],
) -> tuple[float, float]:
    """Return symmetric coplanarity residual and acute ray angle.

    The scalar triple product is normalized by both epipolar-plane normals.
    Averaging the two angular residuals removes the arbitrary choice of which
    camera supplies the reference epipolar plane.
    """

    origin_a_array = np.asarray(origin_a, dtype=float)
    origin_b_array = np.asarray(origin_b, dtype=float)
    direction_a_array = np.asarray(direction_a, dtype=float)
    direction_b_array = np.asarray(direction_b, dtype=float)
    direction_a_array /= max(float(np.linalg.norm(direction_a_array)), 1e-12)
    direction_b_array /= max(float(np.linalg.norm(direction_b_array)), 1e-12)
    baseline = origin_b_array - origin_a_array
    baseline_norm = float(np.linalg.norm(baseline))
    if baseline_norm <= 1e-9:
        raise ValueError("coplanarity requires a non-zero camera baseline")
    baseline /= baseline_norm
    normal_a = np.cross(direction_a_array, baseline)
    normal_b = np.cross(direction_b_array, baseline)
    normal_a_norm = float(np.linalg.norm(normal_a))
    normal_b_norm = float(np.linalg.norm(normal_b))
    if min(normal_a_norm, normal_b_norm) <= 1e-9:
        raise ValueError("epipolar plane is degenerate for a baseline-aligned ray")
    triple = abs(float(np.dot(direction_b_array, normal_a)))
    residual_a = math.asin(float(np.clip(triple / normal_a_norm, 0.0, 1.0)))
    residual_b = math.asin(
        float(
            np.clip(
                abs(float(np.dot(direction_a_array, normal_b))) / normal_b_norm,
                0.0,
                1.0,
            )
        )
    )
    ray_angle = math.degrees(
        math.acos(
            float(
                np.clip(
                    abs(float(np.dot(direction_a_array, direction_b_array))),
                    0.0,
                    1.0,
                )
            )
        )
    )
    return 500.0 * (residual_a + residual_b), ray_angle


def _regularize_covariance(covariance: np.ndarray) -> np.ndarray:
    value = np.asarray(covariance, dtype=float)
    if value.shape != (2, 2) or not np.all(np.isfinite(value)):
        return np.eye(2, dtype=float) * 1.0e-6
    value = 0.5 * (value + value.T)
    eigenvalues, eigenvectors = np.linalg.eigh(value)
    eigenvalues = np.maximum(eigenvalues, 1.0e-12)
    return eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T


def _ray_from_angles_rad(azimuth: float, elevation: float) -> np.ndarray:
    return np.asarray(
        (
            math.cos(elevation) * math.cos(azimuth),
            math.cos(elevation) * math.sin(azimuth),
            -math.sin(elevation),
        ),
        dtype=float,
    )


def _angles_from_ray_rad(direction: Sequence[float]) -> tuple[float, float]:
    value = np.asarray(direction, dtype=float)
    value /= max(float(np.linalg.norm(value)), 1e-12)
    return (
        math.atan2(float(value[1]), float(value[0])),
        -math.atan2(float(value[2]), math.hypot(float(value[0]), float(value[1]))),
    )


def _signed_coplanarity_rad(
    origin_a: Sequence[float],
    direction_a: Sequence[float],
    origin_b: Sequence[float],
    direction_b: Sequence[float],
) -> float:
    baseline = np.asarray(origin_b, dtype=float) - np.asarray(origin_a, dtype=float)
    baseline /= max(float(np.linalg.norm(baseline)), 1e-12)
    direction_a_value = np.asarray(direction_a, dtype=float)
    direction_b_value = np.asarray(direction_b, dtype=float)
    direction_a_value /= max(float(np.linalg.norm(direction_a_value)), 1e-12)
    direction_b_value /= max(float(np.linalg.norm(direction_b_value)), 1e-12)
    normal = np.cross(direction_a_value, baseline)
    normal_norm = float(np.linalg.norm(normal))
    if normal_norm <= 1e-9:
        raise ValueError("epipolar plane is degenerate for covariance propagation")
    return math.asin(
        float(
            np.clip(
                np.dot(direction_b_value, normal / normal_norm),
                -1.0,
                1.0,
            )
        )
    )


def _coplanarity_variance_rad2(
    origin_a: Sequence[float],
    direction_a: Sequence[float],
    covariance_a: np.ndarray,
    origin_b: Sequence[float],
    direction_b: Sequence[float],
    covariance_b: np.ndarray,
) -> float:
    angles = [*_angles_from_ray_rad(direction_a), *_angles_from_ray_rad(direction_b)]
    step = 1.0e-6
    jacobian = np.zeros(4, dtype=float)
    for index in range(4):
        positive = list(angles)
        negative = list(angles)
        positive[index] += step
        negative[index] -= step
        positive_value = _signed_coplanarity_rad(
            origin_a,
            _ray_from_angles_rad(positive[0], positive[1]),
            origin_b,
            _ray_from_angles_rad(positive[2], positive[3]),
        )
        negative_value = _signed_coplanarity_rad(
            origin_a,
            _ray_from_angles_rad(negative[0], negative[1]),
            origin_b,
            _ray_from_angles_rad(negative[2], negative[3]),
        )
        jacobian[index] = (positive_value - negative_value) / (2.0 * step)
    covariance = np.zeros((4, 4), dtype=float)
    covariance[:2, :2] = _regularize_covariance(covariance_a)
    covariance[2:, 2:] = _regularize_covariance(covariance_b)
    return max(float(jacobian @ covariance @ jacobian.T), 1.0e-12)


def build_epipolar_evidence(
    track_a: BearingTrack,
    track_b: BearingTrack,
    *,
    config: AssociationConfig | None = None,
) -> EpipolarEvidence:
    config = config or AssociationConfig()
    timestamps = _aligned_track_timestamps(track_a, track_b)
    residuals: list[float] = []
    normalized_residuals: list[float] = []
    valid_timestamps: list[float] = []
    intersection_angles: list[float] = []
    degenerate_count = 0
    for timestamp in timestamps:
        sample_a = _interpolate_track_sample(track_a, timestamp)
        sample_b = _interpolate_track_sample(track_b, timestamp)
        if sample_a is None or sample_b is None:
            continue
        origin_a, direction_a, _focal_a, covariance_a, source_a = sample_a
        origin_b, direction_b, _focal_b, covariance_b, source_b = sample_b
        try:
            residual, intersection_angle = normalized_symmetric_coplanarity_mrad(
                origin_a, direction_a, origin_b, direction_b
            )
        except ValueError:
            degenerate_count += 1
            continue
        valid_timestamps.append(float(timestamp))
        residuals.append(float(residual))
        normal_variance = _coplanarity_variance_rad2(
            origin_a,
            direction_a,
            covariance_a,
            origin_b,
            direction_b,
            covariance_b,
        )
        normalized_residuals.append(
            float((residual / 1000.0) ** 2 / max(normal_variance, 1e-12))
        )
        intersection_angles.append(float(intersection_angle))
    if residuals:
        residual_array = np.asarray(residuals, dtype=float)
        median = float(np.median(residual_array))
        p90 = float(np.percentile(residual_array, 90.0))
        mad = float(np.median(np.abs(residual_array - median)))
        if len(residual_array) >= 2 and np.ptp(valid_timestamps) > 1e-9:
            centered = np.asarray(valid_timestamps, dtype=float) - float(
                np.mean(valid_timestamps)
            )
            design = np.column_stack((np.ones(len(centered)), centered))
            slope = float(np.linalg.lstsq(design, residual_array, rcond=None)[0][1])
        else:
            slope = 0.0
        intersection_angle_median = float(np.median(intersection_angles))
        normalized_array = np.asarray(normalized_residuals, dtype=float)
        normalized_median = float(np.median(normalized_array))
        normalized_p90 = float(np.percentile(normalized_array, 90.0))
    else:
        median = p90 = mad = float("inf")
        slope = 0.0
        intersection_angle_median = 0.0
        normalized_median = normalized_p90 = float("inf")
    chi_square_gate = float(chi2.ppf(config.covariance_gate_confidence, df=1))
    reasons: list[str] = []
    if len(residuals) < config.min_aligned_samples:
        reasons.append("insufficient_aligned_samples")
    if normalized_residuals and normalized_p90 > chi_square_gate:
        reasons.append("normalized_coplanarity_chi2")
    if degenerate_count and not residuals:
        reasons.append("degenerate_geometry")
    return EpipolarEvidence(
        track_a_id=track_a.track_id,
        track_b_id=track_b.track_id,
        gate_passed=not reasons,
        rejection_reason="|".join(reasons),
        aligned_sample_count=len(residuals),
        timestamps_s=tuple(valid_timestamps),
        residuals_mrad=tuple(residuals),
        residual_median_mrad=median,
        residual_p90_mrad=p90,
        residual_mad_mrad=mad,
        residual_slope_mrad_per_s=slope,
        intersection_angle_median_deg=intersection_angle_median,
        normalized_residuals_chi2=tuple(normalized_residuals),
        normalized_residual_median_chi2=normalized_median,
        normalized_residual_p90_chi2=normalized_p90,
        chi_square_gate=chi_square_gate,
        covariance_gate_confidence=config.covariance_gate_confidence,
        covariance_source=(
            "snapshot_v2"
            if residuals and source_a == source_b == "snapshot_v2"
            else "mixed_or_legacy_conservative_default"
        ),
    )


def k_best_global_assignments(
    tracks_a: Sequence[BearingTrack],
    tracks_b: Sequence[BearingTrack],
    candidates: Sequence[CrossCameraCandidate],
    *,
    config: AssociationConfig | None = None,
    previous_mapping: Mapping[str, str] | None = None,
) -> tuple[GlobalAssignmentHypothesis, ...]:
    """Compute deterministic Murty-style Top-K one-to-one assignments."""

    config = config or AssociationConfig()
    ordered_a = tuple(sorted(tracks_a, key=lambda item: item.track_id))
    ordered_b = tuple(sorted(tracks_b, key=lambda item: item.track_id))
    previous_mapping = dict(previous_mapping or {})
    count_a, count_b = len(ordered_a), len(ordered_b)
    if count_a == 0:
        return (
            GlobalAssignmentHypothesis(
                hypothesis_id="HYP-001",
                rank=1,
                total_cost=float(count_b * config.unmatched_cost),
                normalized_support=1.0,
                matches=(),
                unmatched_a_track_ids=(),
                unmatched_b_track_ids=tuple(item.track_id for item in ordered_b),
            ),
        )
    candidate_by_pair = {
        (item.track_a_id, item.track_b_id): item for item in candidates if item.valid
    }
    infinite_cost = 1e9
    matrix = np.full((count_a, count_b + count_a), infinite_cost, dtype=float)
    for row, track_a in enumerate(ordered_a):
        for column, track_b in enumerate(ordered_b):
            candidate = candidate_by_pair.get((track_a.track_id, track_b.track_id))
            if candidate is None or candidate.cost >= config.unmatched_cost:
                continue
            switch_penalty = (
                config.assignment_switch_penalty
                if track_a.track_id in previous_mapping
                and previous_mapping[track_a.track_id] != track_b.track_id
                else 0.0
            )
            # The fixed base cost assumes every B track is unmatched. Matching
            # one B track removes that unmatched charge and adds pair cost.
            matrix[row, column] = (
                candidate.cost - config.unmatched_cost + switch_penalty
            )
        matrix[row, count_b + row] = config.unmatched_cost
    raw_solutions = _murty_k_best(matrix, config.top_k, infinite_cost=infinite_cost)
    if not raw_solutions:
        return ()
    base_cost = count_b * config.unmatched_cost
    total_costs = np.asarray(
        [base_cost + solution[0] for solution in raw_solutions], dtype=float
    )
    relative = np.exp(
        -(total_costs - float(np.min(total_costs))) / config.hypothesis_temperature
    )
    supports = relative / max(float(np.sum(relative)), 1e-12)
    hypotheses: list[GlobalAssignmentHypothesis] = []
    for rank, ((assignment_cost, assignment), support) in enumerate(
        zip(raw_solutions, supports), start=1
    ):
        del assignment_cost
        matched_pairs = tuple(
            (ordered_a[row].track_id, ordered_b[column].track_id)
            for row, column in assignment
            if column < count_b
        )
        matched_a = {item[0] for item in matched_pairs}
        matched_b = {item[1] for item in matched_pairs}
        hypotheses.append(
            GlobalAssignmentHypothesis(
                hypothesis_id=f"HYP-{rank:03d}",
                rank=rank,
                total_cost=float(total_costs[rank - 1]),
                normalized_support=float(support),
                matches=matched_pairs,
                unmatched_a_track_ids=tuple(
                    item.track_id for item in ordered_a if item.track_id not in matched_a
                ),
                unmatched_b_track_ids=tuple(
                    item.track_id for item in ordered_b if item.track_id not in matched_b
                ),
            )
        )
    return tuple(hypotheses)


def associate_tracks_temporally(
    tracks_a: Sequence[BearingTrack],
    tracks_b: Sequence[BearingTrack],
    *,
    config: AssociationConfig | None = None,
) -> TemporalAssociationResult:
    """Run coarse geometry, Top-K assignment, and delayed confirmation."""

    processing_started = time.perf_counter()
    config = config or AssociationConfig()
    ordered_a = tuple(sorted(tracks_a, key=lambda item: item.track_id))
    ordered_b = tuple(sorted(tracks_b, key=lambda item: item.track_id))
    all_timestamps = [
        sample.timestamp
        for track in (*ordered_a, *ordered_b)
        for sample in track.samples
    ]
    if not all_timestamps:
        return TemporalAssociationResult(
            config=config,
            epipolar_evidence=(),
            fitted_candidates=(),
            hypotheses=(),
            decisions=(),
            hypothesis_history=(),
            state_history=(),
            fragment_suppressions=(),
            selected_matches=(),
            confirmed_matches=(),
            unmatched_a_track_ids=tuple(item.track_id for item in ordered_a),
            unmatched_b_track_ids=tuple(item.track_id for item in ordered_b),
            full_pair_count=len(ordered_a) * len(ordered_b),
            coarse_gate_pass_count=0,
            fit_evaluation_count=0,
            processing_elapsed_ms=(time.perf_counter() - processing_started)
            * 1000.0,
        )
    period = config.decision_period_s
    first_epoch = math.floor(min(all_timestamps) / period + 1e-9) * period
    last_epoch = math.ceil(max(all_timestamps) / period - 1e-9) * period
    epoch_count = int(round((last_epoch - first_epoch) / period)) + 1
    epoch_times = [first_epoch + index * period for index in range(epoch_count)]
    # The independent experiment is a post-episode batch association. Compute
    # each expensive six-parameter fit once, then replay its time-local
    # epipolar evidence through the delayed-confirmation state machine.
    candidate_screening_started = time.perf_counter()
    final_evidence = tuple(
        build_epipolar_evidence(track_a, track_b, config=config)
        for track_a in ordered_a
        for track_b in ordered_b
    )
    candidate_screening_elapsed_ms = (
        time.perf_counter() - candidate_screening_started
    ) * 1000.0
    track_a_by_id = {item.track_id: item for item in ordered_a}
    track_b_by_id = {item.track_id: item for item in ordered_b}
    candidate_fitting_started = time.perf_counter()
    final_candidates = tuple(
        _fit_cross_camera_candidate(
            track_a_by_id[item.track_a_id],
            track_b_by_id[item.track_b_id],
            expected_speed_mps=config.expected_speed_mps,
            max_time_delta_s=config.max_time_delta_s,
            covariance_gate_confidence=config.covariance_gate_confidence,
        )
        for item in final_evidence
        if item.gate_passed
    )
    candidate_fitting_elapsed_ms = (
        time.perf_counter() - candidate_fitting_started
    ) * 1000.0
    evidence_by_pair = {
        (item.track_a_id, item.track_b_id): item for item in final_evidence
    }
    candidate_by_pair = {
        (item.track_a_id, item.track_b_id): item for item in final_candidates
    }
    mapping_history: dict[tuple[str, str], list[bool]] = {}
    relation_states: dict[tuple[str, str], AssociationState] = {}
    contradiction_streaks: dict[tuple[str, str], int] = {}
    coast_streaks: dict[tuple[str, str], int] = {}
    support_numerators: dict[tuple[str, str], float] = {}
    support_denominators: dict[tuple[str, str], float] = {}
    ambiguity_ages: dict[tuple[str, str], int] = {}
    state_history: list[AssociationStateRecord] = []
    decisions: list[AssociationDecisionRecord] = []
    hypothesis_history: list[AssociationHypothesisRecord] = []
    previous_mapping: dict[str, str] = {}
    final_hypotheses: tuple[GlobalAssignmentHypothesis, ...] = ()
    final_active_a: tuple[BearingTrack, ...] = ()
    final_active_b: tuple[BearingTrack, ...] = ()
    for epoch_index, timestamp in enumerate(epoch_times):
        active_a = _stable_track_prefixes(ordered_a, timestamp, config)
        active_b = _stable_track_prefixes(ordered_b, timestamp, config)
        active_by_id = {
            track.track_id: track for track in (*active_a, *active_b)
        }
        active_pairs = {
            (track_a.track_id, track_b.track_id)
            for track_a in active_a
            for track_b in active_b
        }
        epoch_gate_pairs = {
            pair
            for pair in active_pairs
            if _epipolar_prefix_passes(evidence_by_pair[pair], timestamp, config)
        }
        fitted_candidates = tuple(
            candidate_by_pair[pair]
            for pair in sorted(epoch_gate_pairs)
            if pair in candidate_by_pair
        )
        hypotheses = k_best_global_assignments(
            active_a,
            active_b,
            fitted_candidates,
            config=config,
            previous_mapping=previous_mapping,
        )
        hypothesis_history.extend(
            AssociationHypothesisRecord(
                epoch_index=epoch_index,
                timestamp=float(timestamp),
                rank=item.rank,
                total_cost=item.total_cost,
                normalized_support=item.normalized_support,
                match_count=len(item.matches),
                matches=item.matches,
            )
            for item in hypotheses
        )
        current_pairs = set(hypotheses[0].matches) if hypotheses else set()
        pair_supports: dict[tuple[str, str], float] = {}
        for hypothesis in hypotheses:
            for pair in hypothesis.matches:
                pair_supports[pair] = (
                    pair_supports.get(pair, 0.0) + hypothesis.normalized_support
                )
        universe = set(relation_states) | set(pair_supports) | current_pairs
        history_sets = current_pairs
        smoothed_supports: dict[tuple[str, str], float] = {}
        for pair in sorted(universe):
            current_support = pair_supports.get(pair, 0.0)
            support_numerators[pair] = (
                config.history_discount * support_numerators.get(pair, 0.0)
                + current_support
            )
            support_denominators[pair] = (
                config.history_discount * support_denominators.get(pair, 0.0) + 1.0
            )
            smoothed_supports[pair] = support_numerators[pair] / max(
                support_denominators[pair], 1e-12
            )
        for pair in sorted(universe):
            current_support = pair_supports.get(pair, 0.0)
            smoothed_support = smoothed_supports[pair]
            history = mapping_history.setdefault(pair, [])
            history.append(pair in history_sets)
            del history[:-config.confirmation_window]
            hits = sum(history)
            competing_support = max(
                (
                    support
                    for candidate_pair, support in pair_supports.items()
                    if candidate_pair != pair
                    and (
                        candidate_pair[0] == pair[0]
                        or candidate_pair[1] == pair[1]
                    )
                ),
                default=0.0,
            )
            track_a = active_by_id.get(pair[0])
            track_b = active_by_id.get(pair[1])
            crossing_alert = bool(
                track_a is not None
                and track_b is not None
                and (
                    _track_has_close_neighbor(
                        track_a, active_a, timestamp, config.crossing_separation_deg
                    )
                    or _track_has_close_neighbor(
                        track_b, active_b, timestamp, config.crossing_separation_deg
                    )
                )
            )
            previous_state = relation_states.get(pair)
            contradiction = contradiction_streaks.get(pair, 0)
            coast = coast_streaks.get(pair, 0)
            ambiguous = bool(
                crossing_alert
                or competing_support >= config.competing_support_gate
            )
            ambiguity_age, ambiguity_resolved, retained_hypothesis_count = (
                _ambiguity_resolution(
                    pair,
                    selected_pairs=current_pairs,
                    pair_supports=pair_supports,
                    smoothed_supports=smoothed_supports,
                    candidate_costs={
                        candidate_pair: candidate_by_pair[candidate_pair].cost
                        for candidate_pair in pair_supports
                        if candidate_pair in candidate_by_pair
                    },
                    previous_age=ambiguity_ages.get(pair, 0),
                    ambiguous=ambiguous,
                    config=config,
                )
            )
            ambiguity_ages[pair] = ambiguity_age
            if pair in current_pairs:
                contradiction = 0
                coast = 0
                if ambiguous and not ambiguity_resolved:
                    state: AssociationState = "pending"
                    reason = (
                        "crossing_alert"
                        if crossing_alert
                        else "competing_hypothesis"
                    )
                elif previous_state == "confirmed":
                    state = "confirmed"
                    reason = "confirmation_maintained"
                elif (
                    len(history) >= config.confirmation_window
                    and hits >= config.confirmation_hits
                    and smoothed_support >= config.confirmation_support
                ):
                    state = "confirmed"
                    reason = (
                        "ambiguity_resolved_after_two_revolutions"
                        if ambiguity_resolved
                        else "temporal_confirmation"
                    )
                elif previous_state in {"pending", "tentative"}:
                    state = "pending"
                    reason = "confirmation_window_incomplete"
                else:
                    state = "tentative"
                    reason = "first_global_hypothesis"
            else:
                conflicting = any(
                    candidate_pair[0] == pair[0] or candidate_pair[1] == pair[1]
                    for candidate_pair in current_pairs
                )
                if previous_state == "confirmed" and conflicting:
                    contradiction += 1
                    if contradiction >= config.contradiction_epochs:
                        state = "pending"
                        reason = "contradictory_epochs"
                    else:
                        state = "confirmed"
                        reason = "single_contradiction_held"
                elif previous_state in {"confirmed", "coasting"} and not conflicting:
                    coast += 1
                    maximum_coast_epochs = max(
                        1,
                        int(
                            math.ceil(
                                config.coasting_duration_s / config.decision_period_s
                            )
                        ),
                    )
                    if coast <= maximum_coast_epochs:
                        state = "coasting"
                        reason = "temporarily_unobserved"
                    else:
                        state = "rejected"
                        reason = "coasting_expired"
                else:
                    state = "rejected"
                    reason = "not_in_best_hypothesis"
            relation_states[pair] = state
            contradiction_streaks[pair] = contradiction
            coast_streaks[pair] = coast
            state_history.append(
                AssociationStateRecord(
                    epoch_index=epoch_index,
                    timestamp=float(timestamp),
                    track_a_id=pair[0],
                    track_b_id=pair[1],
                    state=state,
                    pair_support=float(current_support),
                    smoothed_support=float(smoothed_support),
                    competing_support=float(competing_support),
                    crossing_alert=crossing_alert,
                    mapping_hits_in_window=hits,
                    contradiction_streak=contradiction,
                    reason=reason,
                    ambiguity_age_revolutions=ambiguity_age,
                    retained_hypothesis_count=retained_hypothesis_count,
                )
            )
        previous_mapping = dict(hypotheses[0].matches) if hypotheses else previous_mapping
        decisions.append(
            AssociationDecisionRecord(
                epoch_index=epoch_index,
                timestamp=float(timestamp),
                active_a_track_count=len(active_a),
                active_b_track_count=len(active_b),
                full_pair_count=len(active_a) * len(active_b),
                coarse_gate_pass_count=len(epoch_gate_pairs),
                fit_evaluation_count=len(fitted_candidates),
                valid_fit_count=sum(item.valid for item in fitted_candidates),
                hypothesis_count=len(hypotheses),
                best_hypothesis_cost=(
                    hypotheses[0].total_cost if hypotheses else None
                ),
            )
        )
        final_hypotheses = hypotheses
        final_active_a = active_a
        final_active_b = active_b
    final_pairs = set(final_hypotheses[0].matches) if final_hypotheses else set()
    candidate_by_pair = {
        (item.track_a_id, item.track_b_id): item for item in final_candidates
    }
    retained_pairs, fragment_suppressions = _suppress_duplicate_fragments(
        tuple(
            pair
            for pair in sorted(final_pairs)
            if pair in candidate_by_pair and candidate_by_pair[pair].valid
        ),
        candidate_by_pair,
        relation_states,
        config,
    )
    selected_matches: list[CrossCameraMatch] = []
    confirmed_matches: list[CrossCameraMatch] = []
    for pair in retained_pairs:
        candidate = candidate_by_pair[pair]
        match = CrossCameraMatch(
            match_id=f"ENH-PAIR-{len(selected_matches) + 1:03d}",
            track_a_id=pair[0],
            track_b_id=pair[1],
            cost=candidate.cost,
            reference_timestamp=candidate.reference_timestamp,
            position_ned=candidate.position_ned,
            velocity_ned=candidate.velocity_ned,
        )
        selected_matches.append(match)
        if relation_states.get(pair) == "confirmed":
            confirmed_matches.append(match)
    matched_a = {item.track_a_id for item in selected_matches}
    matched_b = {item.track_b_id for item in selected_matches}
    return TemporalAssociationResult(
        config=config,
        epipolar_evidence=final_evidence,
        fitted_candidates=final_candidates,
        hypotheses=final_hypotheses,
        decisions=tuple(decisions),
        hypothesis_history=tuple(hypothesis_history),
        state_history=tuple(state_history),
        fragment_suppressions=fragment_suppressions,
        selected_matches=tuple(selected_matches),
        confirmed_matches=tuple(confirmed_matches),
        unmatched_a_track_ids=tuple(
            item.track_id for item in final_active_a if item.track_id not in matched_a
        ),
        unmatched_b_track_ids=tuple(
            item.track_id for item in final_active_b if item.track_id not in matched_b
        ),
        full_pair_count=len(final_active_a) * len(final_active_b),
        coarse_gate_pass_count=sum(item.gate_passed for item in final_evidence),
        fit_evaluation_count=len(final_candidates),
        candidate_screening_elapsed_ms=candidate_screening_elapsed_ms,
        candidate_fitting_elapsed_ms=candidate_fitting_elapsed_ms,
        processing_elapsed_ms=(time.perf_counter() - processing_started) * 1000.0,
    )


def _suppress_duplicate_fragments(
    pairs: Sequence[tuple[str, str]],
    candidates: Mapping[tuple[str, str], CrossCameraCandidate],
    states: Mapping[tuple[str, str], AssociationState],
    config: AssociationConfig,
) -> tuple[tuple[tuple[str, str], ...], tuple[FragmentSuppressionRecord, ...]]:
    ranked = sorted(
        pairs,
        key=lambda pair: (
            0 if states.get(pair) == "confirmed" else 1,
            candidates[pair].cost,
            pair,
        ),
    )
    retained: list[tuple[str, str]] = []
    suppressions: list[FragmentSuppressionRecord] = []
    for pair in ranked:
        candidate = candidates[pair]
        duplicate_of: tuple[str, str] | None = None
        duplicate_position_delta = float("inf")
        duplicate_velocity_delta = float("inf")
        for retained_pair in retained:
            retained_candidate = candidates[retained_pair]
            timestamp = 0.5 * (
                candidate.reference_timestamp
                + retained_candidate.reference_timestamp
            )
            candidate_position = np.asarray(candidate.position_ned, dtype=float) + np.asarray(
                candidate.velocity_ned, dtype=float
            ) * (timestamp - candidate.reference_timestamp)
            retained_position = np.asarray(
                retained_candidate.position_ned, dtype=float
            ) + np.asarray(retained_candidate.velocity_ned, dtype=float) * (
                timestamp - retained_candidate.reference_timestamp
            )
            position_delta = float(
                np.linalg.norm(candidate_position - retained_position)
            )
            velocity_delta = float(
                np.linalg.norm(
                    np.asarray(candidate.velocity_ned, dtype=float)
                    - np.asarray(retained_candidate.velocity_ned, dtype=float)
                )
            )
            if (
                position_delta <= config.fragment_merge_position_gate_m
                and velocity_delta <= config.fragment_merge_velocity_gate_mps
            ):
                duplicate_of = retained_pair
                duplicate_position_delta = position_delta
                duplicate_velocity_delta = velocity_delta
                break
        if duplicate_of is None:
            retained.append(pair)
            continue
        comparison_timestamp = 0.5 * (
            candidate.reference_timestamp
            + candidates[duplicate_of].reference_timestamp
        )
        suppressions.append(
            FragmentSuppressionRecord(
                retained_track_a_id=duplicate_of[0],
                retained_track_b_id=duplicate_of[1],
                suppressed_track_a_id=pair[0],
                suppressed_track_b_id=pair[1],
                comparison_timestamp=comparison_timestamp,
                predicted_position_delta_m=duplicate_position_delta,
                velocity_delta_mps=duplicate_velocity_delta,
            )
        )
    return tuple(sorted(retained)), tuple(suppressions)


def estimate_geometry_sensitivity(
    matches: Sequence[CrossCameraMatch],
    tracks_a: Sequence[BearingTrack],
    tracks_b: Sequence[BearingTrack],
    *,
    angular_noise_mrad: float = 0.15,
    sample_count: int = 1000,
    seed: int = 20260811,
) -> tuple[GeometrySensitivity, ...]:
    """Estimate modeled position sensitivity without using offline identity."""

    if angular_noise_mrad <= 0.0 or sample_count <= 0:
        raise ValueError("noise and sample count must be positive")
    by_a = {item.track_id: item for item in tracks_a}
    by_b = {item.track_id: item for item in tracks_b}
    records: list[GeometrySensitivity] = []
    for match_index, match in enumerate(matches):
        track_a = by_a.get(match.track_a_id)
        track_b = by_b.get(match.track_b_id)
        if track_a is None or track_b is None:
            continue
        sample_a = _interpolate_track_sample(track_a, match.reference_timestamp)
        sample_b = _interpolate_track_sample(track_b, match.reference_timestamp)
        if sample_a is None:
            sample_a = _nearest_track_sample(track_a, match.reference_timestamp)
        if sample_b is None:
            sample_b = _nearest_track_sample(track_b, match.reference_timestamp)
        origin_a = np.asarray(sample_a[0], dtype=float)
        origin_b = np.asarray(sample_b[0], dtype=float)
        position = np.asarray(match.position_ned, dtype=float)
        direction_a = position - origin_a
        direction_b = position - origin_b
        range_a = float(np.linalg.norm(direction_a))
        range_b = float(np.linalg.norm(direction_b))
        if min(range_a, range_b) <= 1e-9:
            continue
        direction_a /= range_a
        direction_b /= range_b
        intersection_angle = math.degrees(
            math.acos(
                float(
                    np.clip(
                        abs(float(np.dot(direction_a, direction_b))), 0.0, 1.0
                    )
                )
            )
        )
        stable_offset = sum(ord(value) for value in match.track_a_id + match.track_b_id)
        rng = np.random.default_rng(seed + match_index * 1009 + stable_offset)
        errors: list[float] = []
        sigma = angular_noise_mrad * 1e-3
        for _sample_index in range(sample_count):
            perturbed_a = _perturb_unit_ray(direction_a, sigma, rng)
            perturbed_b = _perturb_unit_ray(direction_b, sigma, rng)
            estimate = _closest_ray_midpoint(
                origin_a, perturbed_a, origin_b, perturbed_b
            )
            if estimate is None:
                continue
            errors.append(float(np.linalg.norm(estimate - position)))
        records.append(
            GeometrySensitivity(
                track_a_id=match.track_a_id,
                track_b_id=match.track_b_id,
                reference_timestamp=match.reference_timestamp,
                angular_noise_mrad=angular_noise_mrad,
                requested_sample_count=sample_count,
                valid_sample_count=len(errors),
                intersection_angle_deg=intersection_angle,
                range_a_m=range_a,
                range_b_m=range_b,
                position_sensitivity_p50_m=(
                    float(np.percentile(errors, 50.0)) if errors else float("inf")
                ),
                position_sensitivity_p95_m=(
                    float(np.percentile(errors, 95.0)) if errors else float("inf")
                ),
            )
        )
    return tuple(records)


def _epipolar_prefix_passes(
    evidence: EpipolarEvidence,
    timestamp: float,
    config: AssociationConfig,
) -> bool:
    normalized_residuals = [
        residual
        for sample_timestamp, residual in zip(
            evidence.timestamps_s, evidence.normalized_residuals_chi2
        )
        if sample_timestamp <= timestamp + 1e-9
    ]
    gate = float(chi2.ppf(config.covariance_gate_confidence, df=1))
    return bool(
        len(normalized_residuals) >= config.min_aligned_samples
        and np.all(np.isfinite(normalized_residuals))
        and float(np.percentile(normalized_residuals, 90.0)) <= gate
    )


def _aligned_track_timestamps(
    track_a: BearingTrack, track_b: BearingTrack
) -> tuple[float, ...]:
    if not track_a.samples or not track_b.samples:
        return ()
    lower = max(track_a.samples[0].timestamp, track_b.samples[0].timestamp)
    upper = min(track_a.samples[-1].timestamp, track_b.samples[-1].timestamp)
    if upper < lower:
        return ()
    values = sorted(
        sample.timestamp
        for sample in (*track_a.samples, *track_b.samples)
        if lower - 1e-9 <= sample.timestamp <= upper + 1e-9
    )
    unique: list[float] = []
    for value in values:
        if not unique or abs(value - unique[-1]) > 1e-6:
            unique.append(float(value))
    return tuple(unique)


def _interpolate_track_sample(
    track: BearingTrack, timestamp: float
) -> tuple[np.ndarray, np.ndarray, float, np.ndarray, str] | None:
    if not track.samples:
        return None
    samples = track.samples
    if timestamp < samples[0].timestamp - 1e-9 or timestamp > samples[-1].timestamp + 1e-9:
        return None
    times = np.asarray([item.timestamp for item in samples], dtype=float)
    upper = int(np.searchsorted(times, timestamp, side="left"))
    if upper < len(samples) and abs(samples[upper].timestamp - timestamp) <= 1e-9:
        item = samples[upper]
        direction = np.asarray(item.direction_ned, dtype=float)
        if item.covariance_source == "snapshot_v2":
            azimuth = math.radians(item.azimuth_deg) + item.azimuth_rate_rad_s * (
                timestamp - item.timestamp
            )
            elevation = math.radians(item.elevation_deg) + item.elevation_rate_rad_s * (
                timestamp - item.timestamp
            )
            direction = _ray_from_angles_rad(azimuth, elevation)
        return (
            np.asarray(item.origin_ned, dtype=float),
            direction,
            float(item.focal_length_px),
            item.predicted_angular_covariance_rad2(timestamp),
            item.covariance_source,
        )
    if upper == 0 or upper >= len(samples):
        return None
    first, second = samples[upper - 1], samples[upper]
    fraction = (timestamp - first.timestamp) / max(
        second.timestamp - first.timestamp, 1e-12
    )
    origin = (1.0 - fraction) * np.asarray(first.origin_ned, dtype=float) + fraction * np.asarray(
        second.origin_ned, dtype=float
    )
    direction = (1.0 - fraction) * np.asarray(
        first.direction_ned, dtype=float
    ) + fraction * np.asarray(second.direction_ned, dtype=float)
    direction /= max(float(np.linalg.norm(direction)), 1e-12)
    focal = (1.0 - fraction) * first.focal_length_px + fraction * second.focal_length_px
    covariance = (
        (1.0 - fraction) * first.predicted_angular_covariance_rad2(timestamp)
        + fraction * second.predicted_angular_covariance_rad2(timestamp)
    )
    source = (
        "snapshot_v2"
        if first.covariance_source == second.covariance_source == "snapshot_v2"
        else "mixed_or_legacy_conservative_default"
    )
    return origin, direction, float(focal), _regularize_covariance(covariance), source


def _nearest_track_sample(
    track: BearingTrack, timestamp: float
) -> tuple[np.ndarray, np.ndarray, float]:
    item = min(track.samples, key=lambda sample: abs(sample.timestamp - timestamp))
    return (
        np.asarray(item.origin_ned, dtype=float),
        np.asarray(item.direction_ned, dtype=float),
        float(item.focal_length_px),
    )


def _stable_track_prefixes(
    tracks: Sequence[BearingTrack],
    timestamp: float,
    config: AssociationConfig,
) -> tuple[BearingTrack, ...]:
    prefixes: list[BearingTrack] = []
    for track in tracks:
        samples = [item for item in track.samples if item.timestamp <= timestamp + 1e-9]
        if not samples:
            continue
        prefix = BearingTrack(
            track_id=track.track_id,
            camera_id=track.camera_id,
            samples=samples,
            hit_history=track.hit_history,
            track_state=track.track_state,
            state_covariance=track.state_covariance,
        )
        if prefix.is_stable(config.minimum_track_sweeps):
            prefixes.append(prefix)
    return tuple(prefixes)


def _murty_k_best(
    matrix: np.ndarray,
    count: int,
    *,
    infinite_cost: float,
) -> list[tuple[float, tuple[tuple[int, int], ...]]]:
    initial = _solve_assignment_subproblem(
        matrix, fixed=(), forbidden=frozenset(), infinite_cost=infinite_cost
    )
    if initial is None:
        return []
    serial = 0
    heap: list[
        tuple[
            float,
            int,
            tuple[tuple[int, int], ...],
            frozenset[tuple[int, int]],
            tuple[tuple[int, int], ...],
        ]
    ] = [(initial[0], serial, (), frozenset(), initial[1])]
    queued_constraints: set[
        tuple[tuple[tuple[int, int], ...], frozenset[tuple[int, int]]]
    ] = {((), frozenset())}
    emitted: set[tuple[tuple[int, int], ...]] = set()
    results: list[tuple[float, tuple[tuple[int, int], ...]]] = []
    while heap and len(results) < count:
        cost, _serial, fixed, forbidden, assignment = heapq.heappop(heap)
        if assignment not in emitted:
            emitted.add(assignment)
            results.append((cost, assignment))
        prefix_length = len(fixed)
        for split in range(prefix_length, len(assignment)):
            child_fixed = assignment[:split]
            child_forbidden = frozenset((*forbidden, assignment[split]))
            constraint_key = (child_fixed, child_forbidden)
            if constraint_key in queued_constraints:
                continue
            queued_constraints.add(constraint_key)
            solved = _solve_assignment_subproblem(
                matrix,
                fixed=child_fixed,
                forbidden=child_forbidden,
                infinite_cost=infinite_cost,
            )
            if solved is None:
                continue
            serial += 1
            heapq.heappush(
                heap,
                (solved[0], serial, child_fixed, child_forbidden, solved[1]),
            )
    return results


def _solve_assignment_subproblem(
    matrix: np.ndarray,
    *,
    fixed: tuple[tuple[int, int], ...],
    forbidden: frozenset[tuple[int, int]],
    infinite_cost: float,
) -> tuple[float, tuple[tuple[int, int], ...]] | None:
    row_count, column_count = matrix.shape
    fixed_rows = {row for row, _column in fixed}
    fixed_columns = {column for _row, column in fixed}
    if len(fixed_rows) != len(fixed) or len(fixed_columns) != len(fixed):
        return None
    if any(pair in forbidden for pair in fixed):
        return None
    if any(
        row < 0
        or row >= row_count
        or column < 0
        or column >= column_count
        or matrix[row, column] >= infinite_cost * 0.5
        for row, column in fixed
    ):
        return None
    remaining_rows = [row for row in range(row_count) if row not in fixed_rows]
    remaining_columns = [
        column for column in range(column_count) if column not in fixed_columns
    ]
    working = matrix[np.ix_(remaining_rows, remaining_columns)].copy()
    row_lookup = {row: index for index, row in enumerate(remaining_rows)}
    column_lookup = {
        column: index for index, column in enumerate(remaining_columns)
    }
    for row, column in forbidden:
        if row in row_lookup and column in column_lookup:
            working[row_lookup[row], column_lookup[column]] = infinite_cost
    assignments = list(fixed)
    if remaining_rows:
        try:
            rows, columns = linear_sum_assignment(working)
        except ValueError:
            return None
        if len(rows) != len(remaining_rows):
            return None
        for local_row, local_column in zip(rows, columns):
            if working[local_row, local_column] >= infinite_cost * 0.5:
                return None
            assignments.append(
                (remaining_rows[int(local_row)], remaining_columns[int(local_column)])
            )
    assignments.sort()
    assignment_tuple = tuple(assignments)
    cost = float(sum(matrix[row, column] for row, column in assignment_tuple))
    return cost, assignment_tuple


def _track_has_close_neighbor(
    track: BearingTrack,
    tracks: Sequence[BearingTrack],
    timestamp: float,
    gate_deg: float,
) -> bool:
    direction = _predicted_track_direction(track, timestamp)
    for other in tracks:
        if other.track_id == track.track_id:
            continue
        other_direction = _predicted_track_direction(other, timestamp)
        if angular_distance_deg(direction, other_direction) < gate_deg:
            return True
    return False


def _predicted_track_direction(track: BearingTrack, timestamp: float) -> np.ndarray:
    azimuth_deg, elevation_deg = _predict_track_angles(track, timestamp)
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    return np.asarray(
        (
            math.cos(elevation) * math.cos(azimuth),
            math.cos(elevation) * math.sin(azimuth),
            -math.sin(elevation),
        ),
        dtype=float,
    )


def _perturb_unit_ray(
    direction: np.ndarray, sigma_rad: float, rng: np.random.Generator
) -> np.ndarray:
    reference = (
        np.asarray((0.0, 0.0, 1.0), dtype=float)
        if abs(float(direction[2])) < 0.9
        else np.asarray((0.0, 1.0, 0.0), dtype=float)
    )
    tangent_a = np.cross(direction, reference)
    tangent_a /= max(float(np.linalg.norm(tangent_a)), 1e-12)
    tangent_b = np.cross(direction, tangent_a)
    perturbation = rng.normal(0.0, sigma_rad, size=2)
    result = direction + perturbation[0] * tangent_a + perturbation[1] * tangent_b
    return result / max(float(np.linalg.norm(result)), 1e-12)


def _closest_ray_midpoint(
    origin_a: np.ndarray,
    direction_a: np.ndarray,
    origin_b: np.ndarray,
    direction_b: np.ndarray,
) -> np.ndarray | None:
    offset = origin_a - origin_b
    a = float(np.dot(direction_a, direction_a))
    b = float(np.dot(direction_a, direction_b))
    c = float(np.dot(direction_b, direction_b))
    d = float(np.dot(direction_a, offset))
    e = float(np.dot(direction_b, offset))
    denominator = a * c - b * b
    if denominator <= 1e-10:
        return None
    distance_a = (b * e - c * d) / denominator
    distance_b = (a * e - b * d) / denominator
    if distance_a <= 0.0 or distance_b <= 0.0:
        return None
    point_a = origin_a + distance_a * direction_a
    point_b = origin_b + distance_b * direction_b
    return 0.5 * (point_a + point_b)


def _fit_cross_camera_candidate(
    track_a: BearingTrack,
    track_b: BearingTrack,
    *,
    expected_speed_mps: float,
    max_time_delta_s: float,
    covariance_gate_confidence: float = 0.99,
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
    solved_indices: tuple[int, ...] = ()
    for _iteration in range(3):
        matrix, right = _ray_fit_system(
            samples, inlier_indices, reference_timestamp
        )
        solution, _, rank, singular_values = np.linalg.lstsq(matrix, right, rcond=None)
        solved_indices = tuple(inlier_indices)
        errors = _candidate_normalized_reprojection_errors(
            samples, solution, reference_timestamp
        )
        outlier_gate = float(chi2.ppf(covariance_gate_confidence, df=2))
        proposed = [
            index for index, error in enumerate(errors) if error <= outlier_gate
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
    if tuple(inlier_indices) != solved_indices:
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
    normalized_reprojection: list[float] = []
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
        angular_residual = _angular_residual_vector_rad(
            measured_direction=direction,
            predicted_direction=predicted_direction,
        )
        normalized_reprojection.append(
            float(
                angular_residual.T
                @ np.linalg.pinv(sample.angular_covariance_rad2)
                @ angular_residual
            )
        )
    reprojection_rms = float(
        math.sqrt(np.mean(np.square(reprojection_errors)))
    )
    reprojection_max = float(max(reprojection_errors, default=float("inf")))
    ray_rms = float(math.sqrt(np.mean(np.square(ray_residuals))))
    normalized_reprojection_chi2 = float(
        np.sum(normalized_reprojection) / max(len(normalized_reprojection), 1)
    )
    normalized_reprojection_dof = 2
    normalized_reprojection_gate = float(
        chi2.ppf(covariance_gate_confidence, df=normalized_reprojection_dof)
    )
    reasons: list[str] = []
    if rank < 6:
        reasons.append("rank_deficient")
    if median_delta > max_time_delta_s:
        reasons.append("time_delta")
    if normalized_reprojection_chi2 > normalized_reprojection_gate:
        reasons.append("normalized_reprojection_chi2")
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
        0.55
        * min(
            normalized_reprojection_chi2 / max(normalized_reprojection_gate, 1e-9),
            10.0,
        )
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
        normalized_reprojection_chi2=normalized_reprojection_chi2,
        normalized_reprojection_dof=normalized_reprojection_dof,
        normalized_reprojection_gate=normalized_reprojection_gate,
        covariance_gate_confidence=covariance_gate_confidence,
    )


def _angular_residual_vector_rad(
    *, measured_direction: Sequence[float], predicted_direction: Sequence[float]
) -> np.ndarray:
    measured_azimuth, measured_elevation = _angles_from_ray_rad(measured_direction)
    predicted_azimuth, predicted_elevation = _angles_from_ray_rad(predicted_direction)
    azimuth_delta = (measured_azimuth - predicted_azimuth + math.pi) % (
        2.0 * math.pi
    ) - math.pi
    return np.asarray(
        (
            azimuth_delta * math.cos(measured_elevation),
            measured_elevation - predicted_elevation,
        ),
        dtype=float,
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


def _candidate_normalized_reprojection_errors(
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
        residual = _angular_residual_vector_rad(
            measured_direction=sample.direction_ned,
            predicted_direction=predicted_direction,
        )
        errors.append(
            float(
                residual.T
                @ np.linalg.pinv(sample.angular_covariance_rad2)
                @ residual
            )
        )
    return errors


def _predict_track_angles(
    track: BearingTrack, timestamp: float
) -> tuple[float, float]:
    samples = track.samples[-5:]
    latest = samples[-1]
    if latest.covariance_source == "snapshot_v2":
        horizon = float(timestamp - latest.timestamp)
        return (
            normalize_angle_deg(
                latest.azimuth_deg
                + math.degrees(latest.azimuth_rate_rad_s * horizon)
            ),
            float(
                latest.elevation_deg
                + math.degrees(latest.elevation_rate_rad_s * horizon)
            ),
        )
    if len(samples) < 2:
        return latest.azimuth_deg, latest.elevation_deg
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
