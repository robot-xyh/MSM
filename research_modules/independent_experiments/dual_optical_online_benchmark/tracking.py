"""Shared camera-local bearing tracker for the dual-optical benchmark.

The tracker consumes anonymous bearing observations only. Offline identities are
accepted by the calibration helpers, never by :class:`SharedBearingTracker`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import heapq
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from dual_optical_40target.core import RayObservation


TRACKER_FREEZE_SCHEMA = "dual-optical-shared-tracker-freeze-v1"
TRACKER_CONFIG_SCHEMA = "dual-optical-shared-tracker-config-v3"
TRACK_LIFECYCLE_STATES = (
    "tentative",
    "confirmed",
    "coasting",
    "dormant",
    "terminated",
)
CHI2_GATE_BY_CONFIDENCE: Mapping[float, float] = {
    0.95: 5.991464547,
    0.975: 7.377758908,
    0.99: 9.210340372,
    0.995: 10.596634733,
}


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _wrap_deg(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def _unwrap_near(value: float, reference: float) -> float:
    return float(reference) + _wrap_deg(float(value) - float(reference))


def _angles_from_direction(direction: Sequence[float]) -> tuple[float, float]:
    # Several callers derive a short-horizon probe from the original relative
    # position after this conversion.  Always own the buffer: normalizing a
    # caller-provided ndarray in place corrupts that position and can turn a
    # physical sub-degree bearing rate into thousands of degrees per second.
    vector = np.array(direction, dtype=float, copy=True)
    norm = float(np.linalg.norm(vector))
    if norm <= 1.0e-12:
        raise ValueError("bearing direction cannot be zero")
    vector /= norm
    azimuth = math.degrees(math.atan2(vector[1], vector[0]))
    horizontal = math.hypot(vector[0], vector[1])
    elevation = math.degrees(-math.atan2(vector[2], max(horizontal, 1.0e-12)))
    return azimuth, elevation


def _direction_from_angles(azimuth_deg: float, elevation_deg: float) -> tuple[float, float, float]:
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    horizontal = math.cos(elevation)
    return (
        horizontal * math.cos(azimuth),
        horizontal * math.sin(azimuth),
        -math.sin(elevation),
    )


@dataclass(frozen=True)
class SharedTrackerConfig:
    """Frozen parameters for one camera's sparse scan-revisit tracker."""

    chi2_confidence: float = 0.99
    process_noise_deg_s2: float = 0.10
    maximum_target_speed_mps: float = 60.0
    minimum_operating_range_m: float = 1500.0
    measurement_sigma_mrad: float = 0.55
    intra_sweep_gate_deg: float = 0.12
    intra_sweep_max_gap_s: float = 0.06
    confirmation_window_sweeps: int = 3
    confirmation_hits: int = 2
    maximum_missed_sweeps: int = 2
    maximum_global_hypotheses: int = 3
    dormant_retention_sweeps: int = 3
    minimum_tracklet_hits: int = 2
    local_k_best: int = 3
    local_hypothesis_window_sweeps: int = 2
    maximum_ambiguous_tracks: int = 8
    maximum_ambiguous_scanlets: int = 8
    maximum_ambiguous_edges: int = 32
    nominal_sweep_period_s: float = 2.0
    reconnect_angle_bin_deg: float = 4.0
    reconnect_heading_bin_deg: float = 45.0
    reconnect_mahalanobis_multiplier: float = 4.0
    reconnect_rate_gate_multiplier: float = 2.5
    reconnect_motion_corridor_multiplier: float = 4.0
    reconnect_mahalanobis_weight: float = 1.0
    reconnect_angle_weight: float = 1.0
    reconnect_rate_weight: float = 0.75
    reconnect_acceleration_weight: float = 0.25
    reconnect_gap_weight: float = 0.25
    reconnect_heading_weight: float = 0.50
    reconnect_corridor_weight: float = 0.75
    target_speed_mps: float = 50.0
    allowed_heading_offsets_deg: tuple[float, ...] = (0.0, -30.0)
    motion_initialization_residual_gate_m: float = 10.0
    corridor_x_bounds_m: tuple[float, float] = (1000.0, 3000.0)
    corridor_abs_y_bound_m: float = 650.0
    corridor_z_center_m: float = -100.0
    corridor_z_half_span_m: float = 80.0
    corridor_violation_weight: float = 0.10
    vertical_motion_residual_weight: float = 0.50

    def __post_init__(self) -> None:
        if self.chi2_confidence not in CHI2_GATE_BY_CONFIDENCE:
            raise ValueError("unsupported chi-square confidence")
        positive = (
            self.process_noise_deg_s2,
            self.maximum_target_speed_mps,
            self.minimum_operating_range_m,
            self.measurement_sigma_mrad,
            self.intra_sweep_gate_deg,
            self.intra_sweep_max_gap_s,
            self.target_speed_mps,
            self.motion_initialization_residual_gate_m,
            self.corridor_abs_y_bound_m,
            self.corridor_z_half_span_m,
            self.corridor_violation_weight,
            self.vertical_motion_residual_weight,
            self.nominal_sweep_period_s,
            self.reconnect_angle_bin_deg,
            self.reconnect_heading_bin_deg,
            self.reconnect_mahalanobis_multiplier,
            self.reconnect_rate_gate_multiplier,
            self.reconnect_motion_corridor_multiplier,
            self.reconnect_mahalanobis_weight,
            self.reconnect_angle_weight,
            self.reconnect_rate_weight,
            self.reconnect_acceleration_weight,
            self.reconnect_gap_weight,
            self.reconnect_heading_weight,
            self.reconnect_corridor_weight,
        )
        if any(value <= 0.0 or not math.isfinite(value) for value in positive):
            raise ValueError("shared tracker physical parameters must be positive")
        if not 1 <= self.confirmation_hits <= self.confirmation_window_sweeps:
            raise ValueError("invalid hit-window confirmation policy")
        if self.maximum_missed_sweeps < 1:
            raise ValueError("maximum_missed_sweeps must be positive")
        if not 1 <= self.maximum_global_hypotheses <= 5:
            raise ValueError("at most five global hypotheses are supported")
        if self.dormant_retention_sweeps not in {3, 4}:
            raise ValueError("dormant_retention_sweeps must be 3 or 4")
        if self.minimum_tracklet_hits < 2:
            raise ValueError("minimum_tracklet_hits must be at least two")
        if self.local_k_best not in {3, 5}:
            raise ValueError("local_k_best must be 3 or 5")
        if self.local_hypothesis_window_sweeps not in {2, 3}:
            raise ValueError("local_hypothesis_window_sweeps must be 2 or 3")
        if min(
            self.maximum_ambiguous_tracks,
            self.maximum_ambiguous_scanlets,
            self.maximum_ambiguous_edges,
        ) < 1:
            raise ValueError("local ambiguity bounds must be positive")
        if self.maximum_ambiguous_tracks > 8:
            raise ValueError("at most eight ambiguous tracks are supported")
        if self.maximum_ambiguous_scanlets > 8:
            raise ValueError("at most eight ambiguous scanlets are supported")
        if self.maximum_ambiguous_edges > 32:
            raise ValueError("at most 32 ambiguous edges are supported")
        if not self.allowed_heading_offsets_deg:
            raise ValueError("motion initialization requires at least one heading model")
        if len(self.corridor_x_bounds_m) != 2 or self.corridor_x_bounds_m[0] >= self.corridor_x_bounds_m[1]:
            raise ValueError("invalid motion-initialization corridor x bounds")

    @property
    def chi2_gate(self) -> float:
        return CHI2_GATE_BY_CONFIDENCE[self.chi2_confidence]

    @property
    def maximum_angular_rate_deg_s(self) -> float:
        return math.degrees(
            self.maximum_target_speed_mps / self.minimum_operating_range_m
        )

    @property
    def measurement_variance_deg2(self) -> float:
        sigma_deg = math.degrees(self.measurement_sigma_mrad / 1000.0)
        return sigma_deg * sigma_deg

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(
            {"schema_version": TRACKER_CONFIG_SCHEMA, **asdict(self)}
        )

    @property
    def scanlet_preparation_fingerprint(self) -> str:
        """Fingerprint only parameters used before candidate replay."""

        return _canonical_sha256({
            "schema_version": "dual-optical-scanlet-preparation-v1",
            "measurement_sigma_mrad": self.measurement_sigma_mrad,
            "intra_sweep_gate_deg": self.intra_sweep_gate_deg,
            "intra_sweep_max_gap_s": self.intra_sweep_max_gap_s,
        })


@dataclass(frozen=True)
class BearingScanlet:
    camera_id: str
    sweep_index: int
    timestamp: float
    origin_ned: tuple[float, float, float]
    direction_ned: tuple[float, float, float]
    detection_uids: tuple[str, ...]
    bbox_area_px2: float
    confidence: float
    measurement_covariance_deg2: tuple[float, float, float, float]

    @property
    def azimuth_deg(self) -> float:
        return _angles_from_direction(self.direction_ned)[0]

    @property
    def elevation_deg(self) -> float:
        return _angles_from_direction(self.direction_ned)[1]


@dataclass(frozen=True)
class TrackedBearingSample:
    sweep_index: int
    timestamp: float
    direction_ned: tuple[float, float, float]
    detection_uids: tuple[str, ...]
    bbox_area_px2: float
    confidence: float
    measurement_covariance_deg2: tuple[float, float, float, float]
    state_vector: tuple[float, float, float, float]
    state_covariance: tuple[float, ...]
    innovation_mahalanobis2: float


@dataclass(frozen=True)
class TrackerEvent:
    """Anonymous audit event emitted by the local tracker.

    Event records intentionally contain local opaque identifiers only.  Source
    detection identifiers and offline labels are never copied into this log.
    """

    event_type: str
    sweep_index: int
    local_track_id: str | None = None
    related_local_track_id: str | None = None
    previous_state: str | None = None
    current_state: str | None = None
    reason: str = ""
    hypothesis_count: int = 1


@dataclass
class SharedBearingTrack:
    track_id: str
    camera_id: str
    samples: list[TrackedBearingSample] = field(default_factory=list)
    state: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=float))
    covariance: np.ndarray = field(default_factory=lambda: np.eye(4, dtype=float))
    last_timestamp: float = 0.0
    hit_sweeps: list[int] = field(default_factory=list)
    missed_sweeps: int = 0
    ambiguity_count: int = 0
    motion_position_ned: np.ndarray | None = None
    motion_velocity_ned: np.ndarray | None = None
    camera_origin_ned: np.ndarray | None = None
    heading_model_index: int | None = None
    lifecycle_state: str = "tentative"
    birth_sweep: int = -1
    last_hit_sweep: int = -1
    last_hit_timestamp: float = 0.0
    last_processed_sweep: int = -1
    dormant_since_sweep: int | None = None
    terminated_sweep: int | None = None
    reconnection_boundaries: list[int] = field(default_factory=list)

    def clone(self) -> "SharedBearingTrack":
        return SharedBearingTrack(
            track_id=self.track_id,
            camera_id=self.camera_id,
            samples=list(self.samples),
            state=self.state.copy(),
            covariance=self.covariance.copy(),
            last_timestamp=self.last_timestamp,
            hit_sweeps=list(self.hit_sweeps),
            missed_sweeps=self.missed_sweeps,
            ambiguity_count=self.ambiguity_count,
            motion_position_ned=None
            if self.motion_position_ned is None
            else self.motion_position_ned.copy(),
            motion_velocity_ned=None
            if self.motion_velocity_ned is None
            else self.motion_velocity_ned.copy(),
            camera_origin_ned=None
            if self.camera_origin_ned is None
            else self.camera_origin_ned.copy(),
            heading_model_index=self.heading_model_index,
            lifecycle_state=self.lifecycle_state,
            birth_sweep=self.birth_sweep,
            last_hit_sweep=self.last_hit_sweep,
            last_hit_timestamp=self.last_hit_timestamp,
            last_processed_sweep=self.last_processed_sweep,
            dormant_since_sweep=self.dormant_since_sweep,
            terminated_sweep=self.terminated_sweep,
            reconnection_boundaries=list(self.reconnection_boundaries),
        )

    def status(self, config: SharedTrackerConfig, current_sweep: int) -> str:
        del config, current_sweep
        if self.lifecycle_state not in TRACK_LIFECYCLE_STATES:
            raise RuntimeError("track has an invalid lifecycle state")
        return self.lifecycle_state


@dataclass
class _TrackerHypothesis:
    tracks: list[SharedBearingTrack]
    cumulative_cost: float = 0.0

    def clone(self) -> "_TrackerHypothesis":
        return _TrackerHypothesis(
            tracks=[track.clone() for track in self.tracks],
            cumulative_cost=self.cumulative_cost,
        )


@dataclass
class _PendingReconnectHypothesis:
    component_key: tuple[tuple[str, ...], tuple[str, ...]]
    first_sweep: int
    last_sweep: int
    accumulated_costs: dict[tuple[str, str], float] = field(default_factory=dict)
    observation_count: int = 0
    option_count: int = 1


@dataclass(frozen=True)
class _ReconnectCost:
    total: float
    mahalanobis2: float
    angular_error_deg: float
    rate_error_deg_s: float
    acceleration_error_deg_s2: float
    gap_sweeps: int
    heading_error_deg: float
    corridor_residual_m: float


def _scanlets_for_sweep(
    camera_id: str,
    sweep_index: int,
    observations: Sequence[RayObservation],
    confidence_by_uid: Mapping[str, float],
    config: SharedTrackerConfig,
) -> tuple[BearingScanlet, ...]:
    """Collapse duplicate detections during one fast beam passage.

    Equal directional weights are intentional. Bounding-box area is retained
    for diagnostics but is not trusted as a range or quality measurement.
    """

    detection_uids = [str(item.detection_uid) for item in observations]
    if len(detection_uids) != len(set(detection_uids)):
        raise ValueError("one anonymous detection cannot be used twice in a sweep")

    groups: list[list[RayObservation]] = []
    for observation in sorted(observations, key=lambda item: item.timestamp):
        best_index: int | None = None
        best_angle = math.inf
        azimuth, elevation = _angles_from_direction(observation.direction_ned)
        for index, group in enumerate(groups):
            previous = group[-1]
            if observation.timestamp - previous.timestamp > config.intra_sweep_max_gap_s:
                continue
            mean_direction = np.mean(
                np.asarray([item.direction_ned for item in group], dtype=float), axis=0
            )
            mean_direction /= max(float(np.linalg.norm(mean_direction)), 1.0e-12)
            mean_azimuth, mean_elevation = _angles_from_direction(mean_direction)
            error = math.hypot(
                _wrap_deg(azimuth - mean_azimuth)
                * math.cos(math.radians(elevation)),
                elevation - mean_elevation,
            )
            if error <= config.intra_sweep_gate_deg and error < best_angle:
                best_index = index
                best_angle = error
        if best_index is None:
            groups.append([observation])
        else:
            groups[best_index].append(observation)

    result: list[BearingScanlet] = []
    variance = config.measurement_variance_deg2
    for group in groups:
        directions = np.asarray([item.direction_ned for item in group], dtype=float)
        direction = np.mean(directions, axis=0)
        direction /= max(float(np.linalg.norm(direction)), 1.0e-12)
        uids = tuple(dict.fromkeys(item.detection_uid for item in group))
        result.append(
            BearingScanlet(
                camera_id=camera_id,
                sweep_index=sweep_index,
                timestamp=float(np.mean([item.timestamp for item in group])),
                origin_ned=tuple(
                    float(value)
                    for value in np.mean(
                        np.asarray([item.origin_ned for item in group], dtype=float),
                        axis=0,
                    )
                ),
                direction_ned=tuple(float(value) for value in direction),
                detection_uids=uids,
                bbox_area_px2=float(max(item.bbox_area_px2 for item in group)),
                confidence=float(
                    np.mean([confidence_by_uid.get(uid, 0.0) for uid in uids])
                ),
                measurement_covariance_deg2=(variance, 0.0, 0.0, variance),
            )
        )
    return tuple(result)


def _transition(dt: float) -> np.ndarray:
    return np.asarray(
        [[1.0, 0.0, dt, 0.0], [0.0, 1.0, 0.0, dt],
         [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        dtype=float,
    )


def _process_covariance(dt: float, sigma_accel: float) -> np.ndarray:
    q = sigma_accel * sigma_accel
    block = np.asarray(
        [[dt**4 / 4.0, dt**3 / 2.0], [dt**3 / 2.0, dt**2]],
        dtype=float,
    ) * q
    result = np.zeros((4, 4), dtype=float)
    result[np.ix_((0, 2), (0, 2))] = block
    result[np.ix_((1, 3), (1, 3))] = block
    return result


def _predict(track: SharedBearingTrack, timestamp: float, config: SharedTrackerConfig) -> tuple[np.ndarray, np.ndarray]:
    dt = max(float(timestamp) - track.last_timestamp, 0.0)
    transition = _transition(dt)
    state = transition @ track.state
    if (
        track.motion_position_ned is not None
        and track.motion_velocity_ned is not None
        and track.camera_origin_ned is not None
    ):
        position = track.motion_position_ned + track.motion_velocity_ned * dt
        relative = position - track.camera_origin_ned
        azimuth, elevation = _angles_from_direction(relative)
        azimuth = _unwrap_near(azimuth, state[0])
        probe_dt = 0.01
        probe_relative = relative + track.motion_velocity_ned * probe_dt
        probe_azimuth, probe_elevation = _angles_from_direction(probe_relative)
        state = np.asarray(
            [
                azimuth,
                elevation,
                _wrap_deg(probe_azimuth - azimuth) / probe_dt,
                (probe_elevation - elevation) / probe_dt,
            ],
            dtype=float,
        )
    covariance = (
        transition @ track.covariance @ transition.T
        + _process_covariance(dt, config.process_noise_deg_s2)
    )
    return state, covariance


def _innovation(
    track: SharedBearingTrack,
    scanlet: BearingScanlet,
    config: SharedTrackerConfig,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    predicted, covariance = _predict(track, scanlet.timestamp, config)
    observation = np.asarray(
        [
            _unwrap_near(scanlet.azimuth_deg, predicted[0]),
            scanlet.elevation_deg,
        ],
        dtype=float,
    )
    design = np.asarray([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=float)
    measurement = np.asarray(scanlet.measurement_covariance_deg2, dtype=float).reshape(2, 2)
    residual = observation - design @ predicted
    residual[0] = _wrap_deg(residual[0])
    innovation_covariance = design @ covariance @ design.T + measurement
    inverse = np.linalg.pinv(innovation_covariance)
    distance = float(residual.T @ inverse @ residual)
    return distance, predicted, covariance, residual


def _update_track(
    track: SharedBearingTrack,
    scanlet: BearingScanlet,
    mahalanobis2: float,
    config: SharedTrackerConfig,
) -> None:
    previous_timestamp = track.last_timestamp
    previous_direction = (
        None
        if not track.samples
        else np.asarray(track.samples[-1].direction_ned, dtype=float)
    )
    predicted, covariance = _predict(track, scanlet.timestamp, config)
    design = np.asarray([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=float)
    measurement = np.asarray(scanlet.measurement_covariance_deg2, dtype=float).reshape(2, 2)
    observation = np.asarray(
        [_unwrap_near(scanlet.azimuth_deg, predicted[0]), scanlet.elevation_deg],
        dtype=float,
    )
    residual = observation - design @ predicted
    residual[0] = _wrap_deg(residual[0])
    innovation_covariance = design @ covariance @ design.T + measurement
    gain = covariance @ design.T @ np.linalg.pinv(innovation_covariance)
    state = predicted + gain @ residual
    identity = np.eye(4, dtype=float)
    # Joseph form preserves positive semi-definiteness under finite precision.
    posterior = (
        (identity - gain @ design) @ covariance @ (identity - gain @ design).T
        + gain @ measurement @ gain.T
    )
    track.state = state
    track.covariance = posterior
    selected_motion: tuple[float, int, np.ndarray, np.ndarray] | None = None
    if previous_direction is not None and scanlet.timestamp > previous_timestamp:
        previous_scanlet = BearingScanlet(
            camera_id=scanlet.camera_id,
            sweep_index=track.samples[-1].sweep_index,
            timestamp=previous_timestamp,
            origin_ned=tuple(
                float(value)
                for value in (
                    track.camera_origin_ned
                    if track.camera_origin_ned is not None
                    else np.asarray(scanlet.origin_ned, dtype=float)
                )
            ),
            direction_ned=tuple(float(value) for value in previous_direction),
            detection_uids=track.samples[-1].detection_uids,
            bbox_area_px2=track.samples[-1].bbox_area_px2,
            confidence=track.samples[-1].confidence,
            measurement_covariance_deg2=track.samples[-1].measurement_covariance_deg2,
        )
        selected_motion = _motion_pair_fit(previous_scanlet, scanlet, config)
        if selected_motion[0] <= config.motion_initialization_residual_gate_m:
            direction = np.asarray(scanlet.direction_ned, dtype=float)
            track.motion_position_ned = (
                np.asarray(scanlet.origin_ned, dtype=float)
                + float(selected_motion[2][1]) * direction
            )
            track.motion_velocity_ned = _heading_velocity(
                config,
                config.allowed_heading_offsets_deg[selected_motion[1]],
            )
            track.camera_origin_ned = np.asarray(scanlet.origin_ned, dtype=float)
            track.heading_model_index = int(selected_motion[1])
    if (
        selected_motion is None
        and track.motion_position_ned is not None
        and track.motion_velocity_ned is not None
    ):
        elapsed = max(scanlet.timestamp - previous_timestamp, 0.0)
        predicted_position = track.motion_position_ned + track.motion_velocity_ned * elapsed
        origin = np.asarray(scanlet.origin_ned, dtype=float)
        predicted_range = max(float(np.linalg.norm(predicted_position - origin)), 1.0)
        posterior_direction = np.asarray(
            _direction_from_angles(state[0], state[1]), dtype=float
        )
        track.motion_position_ned = origin + predicted_range * posterior_direction
        track.camera_origin_ned = origin
    track.last_timestamp = scanlet.timestamp
    track.hit_sweeps.append(scanlet.sweep_index)
    track.missed_sweeps = 0
    track.last_hit_sweep = int(scanlet.sweep_index)
    track.last_hit_timestamp = float(scanlet.timestamp)
    track.last_processed_sweep = int(scanlet.sweep_index)
    track.dormant_since_sweep = None
    track.terminated_sweep = None
    track.samples.append(
        TrackedBearingSample(
            sweep_index=scanlet.sweep_index,
            timestamp=scanlet.timestamp,
            direction_ned=_direction_from_angles(state[0], state[1]),
            detection_uids=scanlet.detection_uids,
            bbox_area_px2=scanlet.bbox_area_px2,
            confidence=scanlet.confidence,
            measurement_covariance_deg2=scanlet.measurement_covariance_deg2,
            state_vector=tuple(float(value) for value in state),
            state_covariance=tuple(float(value) for value in posterior.reshape(-1)),
            innovation_mahalanobis2=float(mahalanobis2),
        )
    )
    lower = scanlet.sweep_index - config.confirmation_window_sweeps + 1
    hit_count = sum(lower <= sweep <= scanlet.sweep_index for sweep in track.hit_sweeps)
    if hit_count >= config.confirmation_hits:
        track.lifecycle_state = "confirmed"
    elif track.lifecycle_state not in {"confirmed", "coasting", "dormant"}:
        track.lifecycle_state = "tentative"
    else:
        track.lifecycle_state = "confirmed"


def _new_track(
    camera_id: str,
    scanlet: BearingScanlet,
    config: SharedTrackerConfig,
) -> SharedBearingTrack:
    azimuth, elevation = scanlet.azimuth_deg, scanlet.elevation_deg
    variance = config.measurement_variance_deg2
    rate_variance = config.maximum_angular_rate_deg_s**2
    state = np.asarray([azimuth, elevation, 0.0, 0.0], dtype=float)
    covariance = np.diag([variance, variance, rate_variance, rate_variance])
    stable_key = "|".join(sorted(scanlet.detection_uids)) or f"{scanlet.timestamp:.6f}"
    suffix = hashlib.sha1(stable_key.encode("utf-8")).hexdigest()[:12]
    track = SharedBearingTrack(
        track_id=f"{camera_id}-KF-{suffix}",
        camera_id=camera_id,
        state=state,
        covariance=covariance,
        last_timestamp=scanlet.timestamp,
        camera_origin_ned=np.asarray(scanlet.origin_ned, dtype=float),
        lifecycle_state="tentative",
        birth_sweep=int(scanlet.sweep_index),
        last_processed_sweep=int(scanlet.sweep_index),
    )
    _update_track(track, scanlet, 0.0, config)
    return track


def _candidate_costs(
    tracks: Sequence[SharedBearingTrack],
    scanlets: Sequence[BearingScanlet],
    config: SharedTrackerConfig,
) -> tuple[np.ndarray, dict[tuple[int, int], float]]:
    unmatched_cost = config.chi2_gate + 0.25
    costs = np.full(
        (len(tracks), len(scanlets) + len(tracks)), unmatched_cost + 1000.0,
        dtype=float,
    )
    details: dict[tuple[int, int], float] = {}
    for row, track in enumerate(tracks):
        costs[row, len(scanlets) + row] = unmatched_cost
        for column, scanlet in enumerate(scanlets):
            distance, predicted, _, residual = _innovation(track, scanlet, config)
            dt = max(scanlet.timestamp - track.last_timestamp, 0.0)
            physical_gate = (
                config.maximum_angular_rate_deg_s * dt
                + 3.0 * math.sqrt(2.0 * config.measurement_variance_deg2)
            )
            angular_error = math.hypot(
                residual[0] * math.cos(math.radians(predicted[1])), residual[1]
            )
            if angular_error <= physical_gate and distance <= config.chi2_gate:
                costs[row, column] = distance
                details[(row, column)] = distance
    return costs, details


def _k_best_assignments(
    costs: np.ndarray,
    maximum: int,
) -> list[tuple[float, tuple[tuple[int, int], ...]]]:
    """Return exact bounded Murty K-best assignments for a small matrix."""

    if maximum < 1:
        raise ValueError("maximum assignment count must be positive")
    if costs.ndim != 2:
        raise ValueError("assignment costs must be a matrix")
    if costs.shape[0] == 0:
        return [(0.0, ())]

    def solve(
        fixed: tuple[tuple[int, int], ...],
        forbidden: frozenset[tuple[int, int]],
    ) -> tuple[float, tuple[tuple[int, int], ...]] | None:
        matrix = np.array(costs, dtype=float, copy=True)
        matrix[~np.isfinite(matrix)] = math.inf
        for row, column in forbidden:
            matrix[row, column] = math.inf
        fixed_rows: set[int] = set()
        fixed_columns: set[int] = set()
        for row, column in fixed:
            if row in fixed_rows or column in fixed_columns:
                return None
            fixed_rows.add(row)
            fixed_columns.add(column)
        for row, column in fixed:
            matrix[row, :] = math.inf
            matrix[:, column] = math.inf
            matrix[row, column] = costs[row, column]
        try:
            rows, columns = linear_sum_assignment(matrix)
        except ValueError:
            return None
        assignment = tuple(
            sorted((int(row), int(column)) for row, column in zip(rows, columns))
        )
        if len(assignment) != costs.shape[0]:
            return None
        values = [float(matrix[row, column]) for row, column in assignment]
        if any(not math.isfinite(value) for value in values):
            return None
        if not set(fixed) <= set(assignment):
            return None
        return float(sum(float(costs[row, column]) for row, column in assignment)), assignment

    root = solve((), frozenset())
    if root is None:
        return []
    serial = 0
    queue: list[
        tuple[
            float,
            int,
            tuple[tuple[int, int], ...],
            frozenset[tuple[int, int]],
            tuple[tuple[int, int], ...],
        ]
    ] = [(root[0], serial, (), frozenset(), root[1])]
    results: list[tuple[float, tuple[tuple[int, int], ...]]] = []
    seen_assignments: set[tuple[tuple[int, int], ...]] = set()
    seen_nodes: set[tuple[tuple[tuple[int, int], ...], frozenset[tuple[int, int]]]] = set()
    while queue and len(results) < maximum:
        cost, _, fixed, forbidden, assignment = heapq.heappop(queue)
        if assignment not in seen_assignments:
            seen_assignments.add(assignment)
            results.append((cost, assignment))
        fixed_count = len(fixed)
        for split in range(fixed_count, len(assignment)):
            child_fixed = tuple(assignment[:split])
            child_forbidden = frozenset((*forbidden, assignment[split]))
            node_key = (child_fixed, child_forbidden)
            if node_key in seen_nodes:
                continue
            seen_nodes.add(node_key)
            solved = solve(child_fixed, child_forbidden)
            if solved is None:
                continue
            serial += 1
            heapq.heappush(
                queue,
                (
                    solved[0],
                    serial,
                    child_fixed,
                    child_forbidden,
                    solved[1],
                ),
            )
    return results


def _mark_track_missed(
    track: SharedBearingTrack,
    current_sweep: int,
    config: SharedTrackerConfig,
) -> None:
    if track.lifecycle_state in {"dormant", "terminated"}:
        return
    track.missed_sweeps += 1
    track.last_processed_sweep = int(current_sweep)
    if track.lifecycle_state == "tentative":
        if track.missed_sweeps > config.maximum_missed_sweeps:
            track.lifecycle_state = "terminated"
            track.terminated_sweep = int(current_sweep)
        return
    if track.missed_sweeps <= config.maximum_missed_sweeps:
        track.lifecycle_state = "coasting"
        return
    track.lifecycle_state = "dormant"
    track.dormant_since_sweep = int(current_sweep)


def _propagate_dormant_track(
    track: SharedBearingTrack,
    current_sweep: int,
    reference_timestamp: float,
    config: SharedTrackerConfig,
) -> None:
    if track.lifecycle_state != "dormant":
        return
    timestamp = max(float(reference_timestamp), track.last_timestamp)
    predicted, covariance = _predict(track, timestamp, config)
    elapsed = max(timestamp - track.last_timestamp, 0.0)
    if track.motion_position_ned is not None and track.motion_velocity_ned is not None:
        track.motion_position_ned = (
            track.motion_position_ned + track.motion_velocity_ned * elapsed
        )
    track.state = predicted
    track.covariance = covariance
    track.last_timestamp = timestamp
    track.last_processed_sweep = int(current_sweep)


def _actual_track_samples(track: SharedBearingTrack) -> list[TrackedBearingSample]:
    return [sample for sample in track.samples if sample.detection_uids]


def _fit_tracklet_state(
    track: SharedBearingTrack,
    timestamp: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit a local tracklet in both time directions without using identity."""

    samples = _actual_track_samples(track)
    if len(samples) < 2:
        raise ValueError("a reconnecting scanlet requires at least two hits")
    selected = samples[-min(len(samples), 5):]
    times = np.asarray([sample.timestamp for sample in selected], dtype=float)
    reference = float(times[-1])
    relative_times = times - reference
    azimuths: list[float] = []
    for sample in selected:
        azimuth, _ = _angles_from_direction(sample.direction_ned)
        azimuths.append(
            azimuth if not azimuths else _unwrap_near(azimuth, azimuths[-1])
        )
    elevations = np.asarray(
        [_angles_from_direction(sample.direction_ned)[1] for sample in selected],
        dtype=float,
    )
    degree = 2 if len(selected) >= 3 else 1
    azimuth_coefficients = np.polyfit(
        relative_times, np.asarray(azimuths, dtype=float), degree
    )
    elevation_coefficients = np.polyfit(relative_times, elevations, degree)
    query = float(timestamp) - reference

    def evaluate(coefficients: np.ndarray) -> tuple[float, float, float]:
        value = float(np.polyval(coefficients, query))
        first = np.polyder(coefficients, 1)
        second = np.polyder(coefficients, 2)
        rate = float(np.polyval(first, query)) if first.size else 0.0
        acceleration = float(np.polyval(second, query)) if second.size else 0.0
        return value, rate, acceleration

    azimuth, azimuth_rate, azimuth_acceleration = evaluate(azimuth_coefficients)
    elevation, elevation_rate, elevation_acceleration = evaluate(
        elevation_coefficients
    )
    return (
        np.asarray(
            [azimuth, elevation, azimuth_rate, elevation_rate], dtype=float
        ),
        np.asarray(
            [azimuth_acceleration, elevation_acceleration], dtype=float
        ),
    )


def _heading_error_deg(first_rate: Sequence[float], second_rate: Sequence[float]) -> float:
    first = np.asarray(first_rate, dtype=float)
    second = np.asarray(second_rate, dtype=float)
    if float(np.linalg.norm(first)) <= 1.0e-6 or float(np.linalg.norm(second)) <= 1.0e-6:
        return 0.0
    first_heading = math.degrees(math.atan2(first[1], first[0]))
    second_heading = math.degrees(math.atan2(second[1], second[0]))
    return abs(_wrap_deg(first_heading - second_heading))


def _scanlet_from_sample(
    track: SharedBearingTrack,
    sample: TrackedBearingSample,
) -> BearingScanlet:
    origin = (
        np.zeros(3, dtype=float)
        if track.camera_origin_ned is None
        else track.camera_origin_ned
    )
    return BearingScanlet(
        camera_id=track.camera_id,
        sweep_index=sample.sweep_index,
        timestamp=sample.timestamp,
        origin_ned=tuple(float(value) for value in origin),
        direction_ned=sample.direction_ned,
        detection_uids=sample.detection_uids,
        bbox_area_px2=sample.bbox_area_px2,
        confidence=sample.confidence,
        measurement_covariance_deg2=sample.measurement_covariance_deg2,
    )


def _reconnection_cost(
    dormant: SharedBearingTrack,
    tracklet: SharedBearingTrack,
    config: SharedTrackerConfig,
) -> _ReconnectCost | None:
    new_samples = _actual_track_samples(tracklet)
    if len(new_samples) < config.minimum_tracklet_hits:
        return None
    first_sample = new_samples[0]
    first_timestamp = first_sample.timestamp
    forward_state, forward_covariance = _predict(
        dormant, first_timestamp, config
    )
    fitted_first, acceleration = _fit_tracklet_state(tracklet, first_timestamp)
    residual = fitted_first[:2] - forward_state[:2]
    residual[0] = _wrap_deg(residual[0])
    measurement = np.asarray(
        first_sample.measurement_covariance_deg2, dtype=float
    ).reshape(2, 2)
    innovation_covariance = forward_covariance[:2, :2] + measurement
    mahalanobis2 = float(
        residual.T @ np.linalg.pinv(innovation_covariance) @ residual
    )

    backward_state, _ = _fit_tracklet_state(
        tracklet, dormant.last_hit_timestamp
    )
    old_reference = (
        np.asarray(dormant.samples[-1].state_vector, dtype=float)
        if dormant.samples
        else dormant.state
    )
    backward_residual = backward_state[:2] - old_reference[:2]
    backward_residual[0] = _wrap_deg(backward_residual[0])
    angular_error = max(
        float(np.linalg.norm(residual)),
        float(np.linalg.norm(backward_residual)),
    )
    rate_error = float(np.linalg.norm(fitted_first[2:] - forward_state[2:]))
    acceleration_error = float(np.linalg.norm(acceleration))
    heading_error = _heading_error_deg(forward_state[2:], fitted_first[2:])
    gap_sweeps = max(1, tracklet.birth_sweep - dormant.last_hit_sweep)
    elapsed = max(first_timestamp - dormant.last_hit_timestamp, 0.0)
    angular_gate = (
        config.maximum_angular_rate_deg_s * max(elapsed, config.nominal_sweep_period_s)
        + 3.0 * math.sqrt(2.0 * config.measurement_variance_deg2)
    )

    corridor_residual = 0.0
    if dormant.samples:
        old_scanlet = _scanlet_from_sample(dormant, dormant.samples[-1])
        new_scanlet = _scanlet_from_sample(tracklet, first_sample)
        corridor_residual = float(_motion_pair_fit(old_scanlet, new_scanlet, config)[0])
    if mahalanobis2 > config.chi2_gate * config.reconnect_mahalanobis_multiplier:
        return None
    if angular_error > angular_gate:
        return None
    if rate_error > config.maximum_angular_rate_deg_s * config.reconnect_rate_gate_multiplier:
        return None
    if corridor_residual > (
        config.motion_initialization_residual_gate_m
        * config.reconnect_motion_corridor_multiplier
    ):
        return None

    total = (
        config.reconnect_mahalanobis_weight
        * mahalanobis2
        / (config.chi2_gate * config.reconnect_mahalanobis_multiplier)
        + config.reconnect_angle_weight * angular_error / max(angular_gate, 1.0e-9)
        + config.reconnect_rate_weight
        * rate_error
        / max(config.maximum_angular_rate_deg_s, 1.0e-9)
        + config.reconnect_acceleration_weight
        * acceleration_error
        / max(config.process_noise_deg_s2, 1.0e-9)
        + config.reconnect_gap_weight
        * gap_sweeps
        / config.dormant_retention_sweeps
        + config.reconnect_heading_weight * heading_error / 180.0
        + config.reconnect_corridor_weight
        * corridor_residual
        / max(config.motion_initialization_residual_gate_m, 1.0e-9)
    )
    return _ReconnectCost(
        total=float(total),
        mahalanobis2=mahalanobis2,
        angular_error_deg=angular_error,
        rate_error_deg_s=rate_error,
        acceleration_error_deg_s2=acceleration_error,
        gap_sweeps=gap_sweeps,
        heading_error_deg=heading_error,
        corridor_residual_m=corridor_residual,
    )


def _angle_bucket(state: Sequence[float], config: SharedTrackerConfig) -> tuple[int, int]:
    azimuth = (_wrap_deg(float(state[0])) + 180.0) % 360.0
    elevation = float(state[1]) + 90.0
    return (
        int(math.floor(azimuth / config.reconnect_angle_bin_deg)),
        int(math.floor(elevation / config.reconnect_angle_bin_deg)),
    )


def _sparse_reconnection_edges(
    dormant_tracks: Sequence[SharedBearingTrack],
    tracklets: Sequence[SharedBearingTrack],
    config: SharedTrackerConfig,
) -> dict[tuple[int, int], _ReconnectCost]:
    tracklet_states: dict[int, np.ndarray] = {}
    buckets: dict[tuple[int, int], list[int]] = {}
    for column, tracklet in enumerate(tracklets):
        samples = _actual_track_samples(tracklet)
        if len(samples) < config.minimum_tracklet_hits:
            continue
        state, _ = _fit_tracklet_state(tracklet, samples[0].timestamp)
        tracklet_states[column] = state
        buckets.setdefault(_angle_bucket(state, config), []).append(column)

    edges: dict[tuple[int, int], _ReconnectCost] = {}
    azimuth_bin_count = max(
        1, int(math.ceil(360.0 / config.reconnect_angle_bin_deg))
    )
    for row, dormant in enumerate(dormant_tracks):
        candidate_columns: set[int] = set()
        for column, tracklet in enumerate(tracklets):
            samples = _actual_track_samples(tracklet)
            if len(samples) < config.minimum_tracklet_hits:
                continue
            predicted, _ = _predict(dormant, samples[0].timestamp, config)
            center_azimuth, center_elevation = _angle_bucket(predicted, config)
            for azimuth_offset in (-1, 0, 1):
                for elevation_offset in (-1, 0, 1):
                    candidate_columns.update(
                        buckets.get(
                            (
                                (center_azimuth + azimuth_offset) % azimuth_bin_count,
                                center_elevation + elevation_offset,
                            ),
                            (),
                        )
                    )
            break
        for column in sorted(candidate_columns):
            tracklet_state = tracklet_states[column]
            samples = _actual_track_samples(tracklets[column])
            predicted, _ = _predict(dormant, samples[0].timestamp, config)
            heading_error = _heading_error_deg(predicted[2:], tracklet_state[2:])
            if (
                heading_error > 2.0 * config.reconnect_heading_bin_deg
                and np.linalg.norm(predicted[2:]) > 1.0e-6
                and np.linalg.norm(tracklet_state[2:]) > 1.0e-6
            ):
                continue
            cost = _reconnection_cost(dormant, tracklets[column], config)
            if cost is not None:
                edges[(row, column)] = cost
    return edges


def _bipartite_components(
    edges: Iterable[tuple[int, int]],
) -> list[tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[int, int], ...]]]:
    remaining = set(edges)
    components: list[
        tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[int, int], ...]]
    ] = []
    while remaining:
        seed = min(remaining)
        rows = {seed[0]}
        columns = {seed[1]}
        changed = True
        while changed:
            changed = False
            for row, column in tuple(remaining):
                if row in rows or column in columns:
                    before = (len(rows), len(columns))
                    rows.add(row)
                    columns.add(column)
                    changed = changed or before != (len(rows), len(columns))
        component_edges = {
            edge for edge in remaining if edge[0] in rows and edge[1] in columns
        }
        remaining -= component_edges
        components.append(
            (tuple(sorted(rows)), tuple(sorted(columns)), tuple(sorted(component_edges)))
        )
    return components


def _component_k_best(
    rows: Sequence[int],
    columns: Sequence[int],
    edge_costs: Mapping[tuple[int, int], float],
    maximum: int,
) -> list[tuple[float, tuple[tuple[int, int], ...]]]:
    row_lookup = {value: index for index, value in enumerate(rows)}
    column_lookup = {value: index for index, value in enumerate(columns)}
    unmatched_cost = max(edge_costs.values(), default=1.0) + 1.0
    matrix = np.full(
        (len(rows), len(columns) + len(rows)), math.inf, dtype=float
    )
    for local_row in range(len(rows)):
        matrix[local_row, len(columns) + local_row] = unmatched_cost
    for (row, column), cost in edge_costs.items():
        matrix[row_lookup[row], column_lookup[column]] = float(cost)
    result: list[tuple[float, tuple[tuple[int, int], ...]]] = []
    for cost, assignment in _k_best_assignments(matrix, maximum):
        real = tuple(
            sorted(
                (rows[row], columns[column])
                for row, column in assignment
                if column < len(columns)
                and math.isfinite(matrix[row, column])
            )
        )
        result.append((cost, real))
    return result


def _merge_reactivated_track(
    dormant: SharedBearingTrack,
    tracklet: SharedBearingTrack,
    current_sweep: int,
) -> None:
    existing_uids = {
        uid for sample in dormant.samples for uid in sample.detection_uids
    }
    incoming_uids = [
        uid for sample in tracklet.samples for uid in sample.detection_uids
    ]
    if existing_uids.intersection(incoming_uids):
        raise RuntimeError("reconnection would reuse an anonymous scanlet")
    boundary = len(dormant.samples)
    dormant.samples.extend(tracklet.samples)
    dormant.reconnection_boundaries.append(boundary)
    dormant.state = tracklet.state.copy()
    dormant.covariance = tracklet.covariance.copy()
    dormant.last_timestamp = tracklet.last_timestamp
    dormant.hit_sweeps = sorted(set((*dormant.hit_sweeps, *tracklet.hit_sweeps)))
    dormant.missed_sweeps = 0
    dormant.ambiguity_count += tracklet.ambiguity_count
    dormant.motion_position_ned = (
        None
        if tracklet.motion_position_ned is None
        else tracklet.motion_position_ned.copy()
    )
    dormant.motion_velocity_ned = (
        None
        if tracklet.motion_velocity_ned is None
        else tracklet.motion_velocity_ned.copy()
    )
    dormant.camera_origin_ned = (
        None
        if tracklet.camera_origin_ned is None
        else tracklet.camera_origin_ned.copy()
    )
    dormant.heading_model_index = tracklet.heading_model_index
    dormant.lifecycle_state = "confirmed"
    dormant.last_hit_sweep = tracklet.last_hit_sweep
    dormant.last_hit_timestamp = tracklet.last_hit_timestamp
    dormant.last_processed_sweep = int(current_sweep)
    dormant.dormant_since_sweep = None
    dormant.terminated_sweep = None


def _assert_unique_detection_usage(tracks: Sequence[SharedBearingTrack]) -> None:
    owners: dict[str, str] = {}
    for track in tracks:
        if track.lifecycle_state == "terminated":
            continue
        for sample in track.samples:
            for uid in sample.detection_uids:
                owner = owners.setdefault(uid, track.track_id)
                if owner != track.track_id:
                    raise RuntimeError("one anonymous scanlet was assigned to two tracks")


class SharedBearingTracker:
    """Causal tracker with a private dormant pool and bounded local MHT."""

    def __init__(self, camera_id: str, config: SharedTrackerConfig) -> None:
        self.camera_id = str(camera_id)
        self.config = config
        self._hypotheses = [_TrackerHypothesis([])]
        self._current_sweep = -1
        self._pending_first_scanlets: tuple[BearingScanlet, ...] | None = None
        self._pending_reconnect: dict[
            tuple[tuple[str, ...], tuple[str, ...]],
            _PendingReconnectHypothesis,
        ] = {}
        self._events: list[TrackerEvent] = []
        self._local_hypothesis_count = 1

    @property
    def tracks(self) -> tuple[SharedBearingTrack, ...]:
        """Tracks valid for online use; dormant history stays private."""

        return tuple(
            track
            for track in self._hypotheses[0].tracks
            if track.lifecycle_state not in {"dormant", "terminated"}
        )

    @property
    def all_tracks(self) -> tuple[SharedBearingTrack, ...]:
        """Complete anonymous history for post-run diagnostics and scoring."""

        return tuple(self._hypotheses[0].tracks)

    @property
    def dormant_tracks(self) -> tuple[SharedBearingTrack, ...]:
        return tuple(
            track
            for track in self._hypotheses[0].tracks
            if track.lifecycle_state == "dormant"
        )

    @property
    def events(self) -> tuple[TrackerEvent, ...]:
        return tuple(self._events)

    @property
    def hypothesis_count(self) -> int:
        return max(1, int(self._local_hypothesis_count))

    def update_sweep(
        self,
        sweep_index: int,
        observations: Sequence[RayObservation],
        confidence_by_uid: Mapping[str, float],
    ) -> None:
        if sweep_index <= self._current_sweep:
            raise ValueError("shared tracker sweeps must be strictly increasing")
        if any(item.camera_id != self.camera_id for item in observations):
            raise ValueError("observation camera does not match shared tracker")
        scanlets = _scanlets_for_sweep(
            self.camera_id,
            int(sweep_index),
            observations,
            confidence_by_uid,
            self.config,
        )
        self.update_scanlets(int(sweep_index), scanlets)

    def update_scanlets(
        self,
        sweep_index: int,
        scanlets: Sequence[BearingScanlet],
    ) -> None:
        """Replay already prepared anonymous scanlets.

        This entry point is used only by offline calibration caching.  It has
        the same causal checks as :meth:`update_sweep` and accepts no labels.
        """

        if sweep_index <= self._current_sweep:
            raise ValueError("shared tracker sweeps must be strictly increasing")
        if any(item.camera_id != self.camera_id for item in scanlets):
            raise ValueError("scanlet camera does not match shared tracker")
        if any(item.sweep_index != int(sweep_index) for item in scanlets):
            raise ValueError("scanlet sweep does not match tracker update")
        seen_uids: set[str] = set()
        for scanlet in scanlets:
            for uid in scanlet.detection_uids:
                if uid in seen_uids:
                    raise ValueError("one anonymous detection appears in two scanlets")
                seen_uids.add(uid)
        self._current_sweep = int(sweep_index)
        self._update_scanlets(tuple(scanlets))

    def _update_scanlets(self, scanlets: tuple[BearingScanlet, ...]) -> None:
        sweep_index = self._current_sweep
        previous_states = {
            track.track_id: track.lifecycle_state
            for track in self._hypotheses[0].tracks
        }
        if self._pending_first_scanlets is None and not self._hypotheses[0].tracks:
            self._pending_first_scanlets = scanlets
            return
        if self._pending_first_scanlets is not None and not self._hypotheses[0].tracks:
            initialized = _initialize_motion_hypotheses(
                self.camera_id,
                self._pending_first_scanlets,
                scanlets,
                self.config,
            )
            self._hypotheses = [
                min(
                    initialized,
                    key=lambda item: (
                        item.cumulative_cost,
                        tuple(track.track_id for track in item.tracks),
                    ),
                )
            ]
            self._pending_first_scanlets = None
            for track in self._hypotheses[0].tracks:
                track.last_processed_sweep = sweep_index
            _assert_unique_detection_usage(self._hypotheses[0].tracks)
            self._emit_lifecycle_events(previous_states)
            return
        branch = self._hypotheses[0].clone()
        active = [
            track
            for track in branch.tracks
            if track.lifecycle_state not in {"dormant", "terminated"}
        ]
        costs, details = _candidate_costs(active, scanlets, self.config)
        solutions = _k_best_assignments(costs, 1)
        assignment_cost, assignment = solutions[0] if solutions else (0.0, ())
        active_by_id = {track.track_id: track for track in branch.tracks}
        source_ids = [track.track_id for track in active]
        assigned_scanlets: set[int] = set()
        assigned_rows: set[int] = set()
        for row, column in assignment:
            track = active_by_id[source_ids[row]]
            assigned_rows.add(row)
            if column < len(scanlets) and (row, column) in details:
                alternatives = sum(
                    (other_row, column) in details for other_row in range(len(active))
                )
                if alternatives > 1:
                    track.ambiguity_count += alternatives - 1
                _update_track(
                    track, scanlets[column], details[(row, column)], self.config
                )
                assigned_scanlets.add(column)
            else:
                _mark_track_missed(track, sweep_index, self.config)
        for row, track in enumerate(active):
            if row not in assigned_rows:
                _mark_track_missed(
                    active_by_id[track.track_id], sweep_index, self.config
                )
        for column, scanlet in enumerate(scanlets):
            if column not in assigned_scanlets:
                branch.tracks.append(_new_track(self.camera_id, scanlet, self.config))
        branch.cumulative_cost += assignment_cost
        self._attempt_reconnections(branch.tracks)
        reference_timestamp = self._reference_timestamp(scanlets, branch.tracks)
        for track in branch.tracks:
            if track.lifecycle_state != "dormant":
                continue
            dormant_age = sweep_index - int(track.dormant_since_sweep or sweep_index)
            if dormant_age > self.config.dormant_retention_sweeps:
                track.lifecycle_state = "terminated"
                track.terminated_sweep = sweep_index
                continue
            _propagate_dormant_track(
                track,
                sweep_index,
                reference_timestamp,
                self.config,
            )
        _assert_unique_detection_usage(branch.tracks)
        self._hypotheses = [branch]
        self._emit_lifecycle_events(previous_states)

    def _reference_timestamp(
        self,
        scanlets: Sequence[BearingScanlet],
        tracks: Sequence[SharedBearingTrack],
    ) -> float:
        if scanlets:
            return float(np.median([item.timestamp for item in scanlets]))
        previous = max((track.last_timestamp for track in tracks), default=0.0)
        return previous + self.config.nominal_sweep_period_s

    def _attempt_reconnections(
        self,
        tracks: list[SharedBearingTrack],
    ) -> None:
        dormant = [track for track in tracks if track.lifecycle_state == "dormant"]
        tracklets = [
            track
            for track in tracks
            if track.lifecycle_state in {"tentative", "confirmed"}
            and len(_actual_track_samples(track)) >= self.config.minimum_tracklet_hits
            and any(track.birth_sweep > old.last_hit_sweep for old in dormant)
        ]
        edges = _sparse_reconnection_edges(dormant, tracklets, self.config)
        seen_components: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        remove_tracklet_ids: set[str] = set()
        self._local_hypothesis_count = 1
        for rows, columns, component_edges in _bipartite_components(edges):
            old_ids = tuple(sorted(dormant[row].track_id for row in rows))
            new_ids = tuple(sorted(tracklets[column].track_id for column in columns))
            component_key = (old_ids, new_ids)
            seen_components.add(component_key)
            if (
                len(rows) > self.config.maximum_ambiguous_tracks
                or len(columns) > self.config.maximum_ambiguous_scanlets
                or len(component_edges) > self.config.maximum_ambiguous_edges
            ):
                self._pending_reconnect.pop(component_key, None)
                self._events.append(TrackerEvent(
                    event_type="hypothesis_fail_closed",
                    sweep_index=self._current_sweep,
                    reason="local_component_bound_exceeded",
                ))
                continue
            row_degrees = {
                row: sum(edge[0] == row for edge in component_edges) for row in rows
            }
            column_degrees = {
                column: sum(edge[1] == column for edge in component_edges)
                for column in columns
            }
            ambiguous = any(value > 1 for value in (*row_degrees.values(), *column_degrees.values()))
            current_costs = {
                edge: edges[edge].total for edge in component_edges
            }
            if ambiguous:
                pending = self._pending_reconnect.get(component_key)
                if pending is None:
                    pending = _PendingReconnectHypothesis(
                        component_key=component_key,
                        first_sweep=self._current_sweep,
                        last_sweep=self._current_sweep,
                    )
                    self._pending_reconnect[component_key] = pending
                pending.last_sweep = self._current_sweep
                pending.observation_count += 1
                for row, column in component_edges:
                    key = (dormant[row].track_id, tracklets[column].track_id)
                    pending.accumulated_costs[key] = (
                        pending.accumulated_costs.get(key, 0.0)
                        + current_costs[(row, column)]
                    )
                averaged = {
                    (row, column): pending.accumulated_costs[
                        (dormant[row].track_id, tracklets[column].track_id)
                    ] / pending.observation_count
                    for row, column in component_edges
                }
                options = _component_k_best(
                    rows, columns, averaged, self.config.local_k_best
                )
                pending.option_count = len(options)
                self._local_hypothesis_count = max(
                    self._local_hypothesis_count, len(options)
                )
                self._events.append(TrackerEvent(
                    event_type="hypothesis_updated",
                    sweep_index=self._current_sweep,
                    reason="ambiguous_reconnection_component",
                    hypothesis_count=max(1, len(options)),
                ))
                if pending.observation_count < self.config.local_hypothesis_window_sweeps:
                    continue
                self._pending_reconnect.pop(component_key, None)
            else:
                options = _component_k_best(rows, columns, current_costs, 1)
            if not options:
                continue
            for row, column in options[0][1]:
                old_track = dormant[row]
                new_track = tracklets[column]
                if new_track.track_id in remove_tracklet_ids:
                    raise RuntimeError("one scanlet track was reactivated twice")
                _merge_reactivated_track(old_track, new_track, self._current_sweep)
                remove_tracklet_ids.add(new_track.track_id)
                self._events.append(TrackerEvent(
                    event_type="tracklet_reconnected",
                    sweep_index=self._current_sweep,
                    local_track_id=old_track.track_id,
                    related_local_track_id=new_track.track_id,
                    previous_state="dormant",
                    current_state="confirmed",
                    reason="bidirectional_motion_and_geometry_gate",
                ))
        if remove_tracklet_ids:
            tracks[:] = [
                track for track in tracks if track.track_id not in remove_tracklet_ids
            ]
        stale = [
            key for key in self._pending_reconnect if key not in seen_components
        ]
        for key in stale:
            self._pending_reconnect.pop(key, None)

    def _emit_lifecycle_events(self, previous_states: Mapping[str, str]) -> None:
        for track in self._hypotheses[0].tracks:
            previous = previous_states.get(track.track_id)
            current = track.lifecycle_state
            if previous == current:
                continue
            self._events.append(TrackerEvent(
                event_type="lifecycle_transition",
                sweep_index=self._current_sweep,
                local_track_id=track.track_id,
                previous_state=previous,
                current_state=current,
                reason="new_track" if previous is None else "sweep_update",
            ))


def _heading_velocity(config: SharedTrackerConfig, heading_offset_deg: float) -> np.ndarray:
    heading = math.radians(float(heading_offset_deg))
    return np.asarray(
        [
            -config.target_speed_mps * math.cos(heading),
            -config.target_speed_mps * math.sin(heading),
            0.0,
        ],
        dtype=float,
    )


def _motion_pair_fit(
    first: BearingScanlet,
    second: BearingScanlet,
    config: SharedTrackerConfig,
) -> tuple[float, int, np.ndarray, np.ndarray]:
    direction_first = np.asarray(first.direction_ned, dtype=float)
    direction_second = np.asarray(second.direction_ned, dtype=float)
    design = np.column_stack((-direction_first, direction_second))
    elapsed = second.timestamp - first.timestamp
    if elapsed <= 0.0:
        return math.inf, 0, np.zeros(2), np.zeros(3)
    candidates: list[tuple[float, int, np.ndarray, np.ndarray]] = []
    for index, heading in enumerate(config.allowed_heading_offsets_deg):
        displacement = _heading_velocity(config, heading) * elapsed
        ranges, *_ = np.linalg.lstsq(design, displacement, rcond=None)
        residual = design @ ranges - displacement
        position_first = np.asarray(first.origin_ned, dtype=float) + ranges[0] * direction_first
        position_second = np.asarray(second.origin_ned, dtype=float) + ranges[1] * direction_second
        lower_x, upper_x = config.corridor_x_bounds_m
        corridor_violation = max(
            0.0,
            lower_x - position_first[0],
            position_first[0] - upper_x,
            abs(position_first[1]) - config.corridor_abs_y_bound_m,
            abs(position_first[2] - config.corridor_z_center_m) - config.corridor_z_half_span_m,
            lower_x - position_second[0],
            position_second[0] - upper_x,
            abs(position_second[1]) - config.corridor_abs_y_bound_m,
            abs(position_second[2] - config.corridor_z_center_m) - config.corridor_z_half_span_m,
        )
        vertical_residual = abs(position_second[2] - position_first[2])
        cost = (
            float(np.linalg.norm(residual))
            + config.corridor_violation_weight * corridor_violation
            + config.vertical_motion_residual_weight * vertical_residual
        )
        if not all(500.0 <= value <= 5000.0 for value in ranges):
            cost += 1000.0
        candidates.append((cost, index, ranges, residual))
    return min(candidates, key=lambda item: (item[0], item[1]))


def _initialized_track(
    camera_id: str,
    first: BearingScanlet,
    second: BearingScanlet,
    heading_index: int,
    ranges_m: np.ndarray,
    residual_m: float,
    config: SharedTrackerConfig,
) -> SharedBearingTrack:
    first_azimuth, first_elevation = first.azimuth_deg, first.elevation_deg
    second_azimuth = _unwrap_near(second.azimuth_deg, first_azimuth)
    elapsed = max(second.timestamp - first.timestamp, 1.0e-6)
    state = np.asarray(
        [
            second_azimuth,
            second.elevation_deg,
            (second_azimuth - first_azimuth) / elapsed,
            (second.elevation_deg - first_elevation) / elapsed,
        ],
        dtype=float,
    )
    variance = config.measurement_variance_deg2
    rate_variance = 2.0 * variance / (elapsed * elapsed)
    covariance = np.diag([variance, variance, rate_variance, rate_variance])
    stable_key = "|".join(sorted(first.detection_uids + second.detection_uids))
    suffix = hashlib.sha1(stable_key.encode("utf-8")).hexdigest()[:12]
    track = SharedBearingTrack(
        track_id=f"{camera_id}-KF-{suffix}",
        camera_id=camera_id,
        state=state,
        covariance=covariance,
        last_timestamp=second.timestamp,
        hit_sweeps=[first.sweep_index, second.sweep_index],
        motion_position_ned=(
            np.asarray(second.origin_ned, dtype=float)
            + float(ranges_m[1]) * np.asarray(second.direction_ned, dtype=float)
        ),
        motion_velocity_ned=_heading_velocity(
            config, config.allowed_heading_offsets_deg[heading_index]
        ),
        camera_origin_ned=np.asarray(second.origin_ned, dtype=float),
        heading_model_index=int(heading_index),
        lifecycle_state="confirmed",
        birth_sweep=int(first.sweep_index),
        last_hit_sweep=int(second.sweep_index),
        last_hit_timestamp=float(second.timestamp),
        last_processed_sweep=int(second.sweep_index),
    )

    def sample(scanlet: BearingScanlet, sample_state: np.ndarray) -> TrackedBearingSample:
        return TrackedBearingSample(
            sweep_index=scanlet.sweep_index,
            timestamp=scanlet.timestamp,
            direction_ned=scanlet.direction_ned,
            detection_uids=scanlet.detection_uids,
            bbox_area_px2=scanlet.bbox_area_px2,
            confidence=scanlet.confidence,
            measurement_covariance_deg2=scanlet.measurement_covariance_deg2,
            state_vector=tuple(float(value) for value in sample_state),
            state_covariance=tuple(float(value) for value in covariance.reshape(-1)),
            innovation_mahalanobis2=float(
                max(residual_m / config.motion_initialization_residual_gate_m, 0.0) ** 2
            ),
        )

    first_state = state.copy()
    first_state[0] = first_azimuth
    first_state[1] = first_elevation
    track.samples = [sample(first, first_state), sample(second, state)]
    # Record the selected physical model as ambiguity evidence when another
    # heading model was available; the online track ID remains anonymous.
    track.ambiguity_count = int(len(config.allowed_heading_offsets_deg) > 1 and heading_index < 0)
    return track


def _initialize_motion_hypotheses(
    camera_id: str,
    first: Sequence[BearingScanlet],
    second: Sequence[BearingScanlet],
    config: SharedTrackerConfig,
) -> list[_TrackerHypothesis]:
    if not first:
        return [_TrackerHypothesis(
            [_new_track(camera_id, item, config) for item in second]
        )]
    if not second:
        return [_TrackerHypothesis(
            [_new_track(camera_id, item, config) for item in first]
        )]
    unmatched_cost = config.motion_initialization_residual_gate_m
    costs = np.full(
        (len(first), len(second) + len(first)),
        unmatched_cost + 1000.0,
        dtype=float,
    )
    fits: dict[tuple[int, int], tuple[float, int, np.ndarray, np.ndarray]] = {}
    for row, first_scanlet in enumerate(first):
        costs[row, len(second) + row] = unmatched_cost
        for column, second_scanlet in enumerate(second):
            fit = _motion_pair_fit(first_scanlet, second_scanlet, config)
            fits[(row, column)] = fit
            if fit[0] <= unmatched_cost:
                costs[row, column] = fit[0]
    hypotheses: list[_TrackerHypothesis] = []
    for assignment_cost, assignment in _k_best_assignments(
        costs, config.maximum_global_hypotheses
    ):
        tracks: list[SharedBearingTrack] = []
        assigned_second: set[int] = set()
        for row, column in assignment:
            if column < len(second) and costs[row, column] <= unmatched_cost:
                fit = fits[(int(row), int(column))]
                tracks.append(
                    _initialized_track(
                        camera_id,
                        first[int(row)],
                        second[int(column)],
                        fit[1],
                        fit[2],
                        fit[0],
                        config,
                    )
                )
                assigned_second.add(int(column))
            else:
                tracks.append(_new_track(camera_id, first[int(row)], config))
                tracks[-1].missed_sweeps = 1
        for column, scanlet in enumerate(second):
            if column not in assigned_second:
                tracks.append(_new_track(camera_id, scanlet, config))
        hypotheses.append(
            _TrackerHypothesis(tracks=tracks, cumulative_cost=assignment_cost)
        )
    return hypotheses


def tracker_freeze_payload(
    config: SharedTrackerConfig,
    *,
    calibration_manifest: str,
    calibration_manifest_sha256: str,
    validation_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": TRACKER_FREEZE_SCHEMA,
        "tracker_config_schema": TRACKER_CONFIG_SCHEMA,
        "tracker_config": asdict(config),
        "tracker_fingerprint": config.fingerprint,
        "calibration_manifest": calibration_manifest,
        "calibration_manifest_sha256": calibration_manifest_sha256,
        "validation_metrics": dict(validation_metrics),
        "test_data_accessed": False,
    }


def load_tracker_freeze(path: str | Path) -> tuple[dict[str, Any], SharedTrackerConfig]:
    freeze_path = Path(path).resolve()
    payload = json.loads(freeze_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != TRACKER_FREEZE_SCHEMA:
        raise ValueError("unsupported shared tracker freeze schema")
    config_values = dict(payload["tracker_config"])
    config_values["allowed_heading_offsets_deg"] = tuple(
        float(value) for value in config_values["allowed_heading_offsets_deg"]
    )
    config_values["corridor_x_bounds_m"] = tuple(
        float(value) for value in config_values["corridor_x_bounds_m"]
    )
    config = SharedTrackerConfig(**config_values)
    if payload.get("tracker_fingerprint") != config.fingerprint:
        raise ValueError("shared tracker config fingerprint mismatch")
    if payload.get("test_data_accessed") is not False:
        raise ValueError("shared tracker freeze does not prove test isolation")
    return payload, config


__all__ = [
    "BearingScanlet",
    "CHI2_GATE_BY_CONFIDENCE",
    "SharedBearingTrack",
    "SharedBearingTracker",
    "SharedTrackerConfig",
    "TRACK_LIFECYCLE_STATES",
    "TRACKER_FREEZE_SCHEMA",
    "TrackerEvent",
    "TrackedBearingSample",
    "load_tracker_freeze",
    "tracker_freeze_payload",
]
