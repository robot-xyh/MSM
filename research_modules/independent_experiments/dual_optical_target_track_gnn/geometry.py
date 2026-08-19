"""Causal weighted line-of-sight fitting for anonymous target hypotheses."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Mapping, Sequence

import numpy as np

from dual_optical_online_benchmark.contracts import (
    RevolutionSnapshot,
    SnapshotTrack,
    snapshot_fingerprint,
)

from .contracts import (
    BearingObservation,
    ConfirmedTrackPair,
    TargetHypothesis,
)


FORBIDDEN_ID_MARKERS = ("truth_id", "actor_id", "global_track_id")


class GeometryFitError(ValueError):
    """Raised when a hypothesis cannot be formed without weakening geometry."""


class CausalityError(ValueError):
    """Raised when current or future information reaches a hypothesis."""


@dataclass(frozen=True)
class WeightedFitConfig:
    minimum_observations: int = 6
    minimum_time_span_s: float = 0.25
    minimum_camera_baseline_m: float = 1.0
    minimum_intersection_angle_deg: float = 0.10
    maximum_condition_number: float = 1.0e10
    maximum_fit_rms_mrad: float = 25.0
    minimum_transverse_sigma_m: float = 0.05
    position_variance_floor_m2: float = 1.0e-4
    velocity_variance_floor_m2_s2: float = 1.0e-6

    def __post_init__(self) -> None:
        if self.minimum_observations < 4:
            raise ValueError("minimum_observations must be at least four")
        if self.minimum_time_span_s <= 0.0:
            raise ValueError("minimum_time_span_s must be positive")
        if self.minimum_camera_baseline_m <= 0.0:
            raise ValueError("minimum_camera_baseline_m must be positive")
        if not 0.0 < self.minimum_intersection_angle_deg < 90.0:
            raise ValueError("minimum intersection angle is invalid")
        if self.maximum_condition_number <= 1.0:
            raise ValueError("maximum condition number must exceed one")
        if self.maximum_fit_rms_mrad <= 0.0:
            raise ValueError("maximum fit RMS must be positive")


@dataclass(frozen=True)
class WeightedLineOfSightFit:
    reference_timestamp: float
    state_ned: tuple[float, float, float, float, float, float]
    covariance_6x6: tuple[float, ...]
    rms_angular_residual_mrad: float
    condition_number: float
    minimum_depth_m: float
    intersection_angle_deg: float
    cross_camera_median_time_offset_s: float


@dataclass(frozen=True)
class AsynchronousPairFitQuality:
    """Anonymous candidate-pair score computed without time alignment or truth."""

    camera_a_id: str
    camera_b_id: str
    track_a_id: str
    track_b_id: str
    sample_count_a: int
    sample_count_b: int
    cross_camera_median_time_offset_s: float | None
    gate_passed: bool
    rejection_reason: str
    rule_cost: float
    reference_timestamp: float | None = None
    state_ned: tuple[float, float, float, float, float, float] | None = None
    covariance_6x6: tuple[float, ...] | None = None
    fit_rms_mrad: float | None = None
    fit_condition_number: float | None = None
    intersection_angle_deg: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def assert_anonymous_snapshot(snapshot: RevolutionSnapshot) -> None:
    """Fail closed if an online track advertises an identity-bearing source."""

    for camera_id in snapshot.camera_ids:
        for track in snapshot.tracks[camera_id]:
            searchable = f"{track.track_id}|{track.source_kind}".lower()
            if any(marker in searchable for marker in FORBIDDEN_ID_MARKERS):
                raise ValueError("online snapshot contains a forbidden identity-bearing field")
            if "truth" in track.source_kind.lower() or "actor" in track.source_kind.lower():
                raise ValueError("online snapshot source must remain anonymous")


def _measurement_variance_rad2(track_sample: object) -> float:
    covariance = np.asarray(
        getattr(track_sample, "measurement_covariance_deg2"), dtype=float
    ).reshape(2, 2)
    diagonal = np.maximum(np.diag(covariance), 1.0e-12)
    return float(np.mean(diagonal) * (math.pi / 180.0) ** 2)


def _track_for_id(snapshot: RevolutionSnapshot, camera_id: str, track_id: str) -> SnapshotTrack:
    matches = [
        track for track in snapshot.tracks[camera_id] if track.track_id == track_id
    ]
    if len(matches) != 1:
        raise GeometryFitError(
            f"confirmed pair references {len(matches)} tracks for {camera_id}/{track_id}"
        )
    return matches[0]


def _samples_available_at_confirmation(
    track: SnapshotTrack,
    snapshot: RevolutionSnapshot,
) -> tuple[object, ...]:
    values = tuple(
        sample
        for sample in track.samples
        if sample.timestamp <= snapshot.cutoff_timestamp + 1.0e-9
    )
    if not values:
        raise GeometryFitError("confirmed pair has no causal samples at publication time")
    return values


def observations_from_confirmed_pairs(
    snapshots: Mapping[int, RevolutionSnapshot],
    confirmed_pairs: Sequence[ConfirmedTrackPair],
    *,
    creation_revolution_index: int,
    online_publications: Mapping[str, Mapping[str, object]],
) -> tuple[BearingObservation, ...]:
    """Extract only past, anonymous rays referenced by explicit confirmations."""

    if not confirmed_pairs:
        raise GeometryFitError("at least one confirmed pair is required")
    protocol_fingerprints: set[str] = set()
    seeds: set[int] = set()
    observations: list[BearingObservation] = []
    seen: set[tuple[str, str, float]] = set()
    for pair in confirmed_pairs:
        if pair.revolution_index >= creation_revolution_index:
            raise CausalityError(
                "a hypothesis may use only confirmations from earlier revolutions"
            )
        snapshot = snapshots.get(pair.revolution_index)
        if snapshot is None:
            raise GeometryFitError("a confirmed pair has no matching revolution snapshot")
        if snapshot.revolution_index != pair.revolution_index:
            raise GeometryFitError("snapshot history key does not match snapshot revolution")
        publication = online_publications.get(pair.publication_fingerprint)
        if publication is None:
            raise CausalityError(
                "confirmed pair has no registered anonymous online publication"
            )
        pair.validate_publication(publication)
        assert_anonymous_snapshot(snapshot)
        if pair.publication_seed != snapshot.seed:
            raise CausalityError("confirmed pair publication seed does not match snapshot")
        if pair.publication_protocol_fingerprint != snapshot.protocol_fingerprint:
            raise CausalityError(
                "confirmed pair publication protocol does not match snapshot"
            )
        if pair.publication_input_fingerprint != snapshot_fingerprint(snapshot):
            raise CausalityError(
                "confirmed pair publication does not reference the supplied snapshot"
            )
        protocol_fingerprints.add(snapshot.protocol_fingerprint)
        seeds.add(snapshot.seed)
        camera_a, camera_b = snapshot.camera_ids
        for camera_id, track_id in (
            (camera_a, pair.track_a_id),
            (camera_b, pair.track_b_id),
        ):
            track = _track_for_id(snapshot, camera_id, track_id)
            for sample in _samples_available_at_confirmation(track, snapshot):
                key = (camera_id, track_id, round(float(sample.timestamp), 9))
                if key in seen:
                    continue
                seen.add(key)
                observations.append(
                    BearingObservation(
                        camera_id=camera_id,
                        track_id=track_id,
                        timestamp=float(sample.timestamp),
                        camera_position_ned=tuple(
                            float(value)
                            for value in snapshot.camera_positions_ned[camera_id]
                        ),
                        direction_ned=tuple(float(value) for value in sample.direction_ned),
                        bearing_variance_rad2=_measurement_variance_rad2(sample),
                        source_revolution_index=pair.revolution_index,
                    )
                )
    if len(protocol_fingerprints) != 1 or len(seeds) != 1:
        raise GeometryFitError("hypothesis inputs must belong to one episode protocol and seed")
    return tuple(sorted(observations, key=lambda item: (item.timestamp, item.camera_id)))


def _cross_camera_median_time_offset(observations: Sequence[BearingObservation]) -> float:
    camera_ids = sorted({item.camera_id for item in observations})
    if len(camera_ids) != 2:
        raise GeometryFitError("weighted triangulation requires exactly two cameras")
    by_camera = {
        camera_id: [item for item in observations if item.camera_id == camera_id]
        for camera_id in camera_ids
    }
    offsets = []
    for item in by_camera[camera_ids[0]]:
        other = min(
            by_camera[camera_ids[1]],
            key=lambda value: abs(value.timestamp - item.timestamp),
        )
        offsets.append(abs(other.timestamp - item.timestamp))
    return float(np.median(offsets)) if offsets else float("inf")


def _design_block(direction: np.ndarray, dt: float) -> np.ndarray:
    projector = np.eye(3, dtype=float) - np.outer(direction, direction)
    return np.hstack((projector, projector * dt))


def _solve_weighted(
    observations: Sequence[BearingObservation],
    reference_timestamp: float,
    transverse_sigma_m: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    rows = []
    targets = []
    for item, sigma_m in zip(observations, transverse_sigma_m):
        direction = np.asarray(item.direction_ned, dtype=float)
        origin = np.asarray(item.camera_position_ned, dtype=float)
        projector = np.eye(3, dtype=float) - np.outer(direction, direction)
        scale = 1.0 / max(float(sigma_m), 1.0e-12)
        rows.append(
            scale
            * _design_block(direction, float(item.timestamp - reference_timestamp))
        )
        targets.append(scale * (projector @ origin))
    design = np.vstack(rows)
    target = np.concatenate(targets)
    solution, _, rank, singular_values = np.linalg.lstsq(design, target, rcond=None)
    if rank < 6 or len(singular_values) < 6 or singular_values[-1] <= 1.0e-12:
        raise GeometryFitError("line-of-sight fit is rank deficient")
    condition = float(singular_values[0] / singular_values[-1])
    residual = design @ solution - target
    normal = design.T @ design
    covariance = np.linalg.pinv(normal, rcond=1.0e-12)
    dof = max(1, len(target) - 6)
    reduced_chi2 = float(np.dot(residual, residual) / dof)
    covariance *= max(reduced_chi2, 1.0)
    return solution, covariance, condition, residual


def weighted_line_of_sight_fit(
    observations: Sequence[BearingObservation],
    *,
    config: WeightedFitConfig | None = None,
) -> WeightedLineOfSightFit:
    """Fit constant-velocity state and covariance from asynchronous weighted rays."""

    config = config or WeightedFitConfig()
    if len(observations) < config.minimum_observations:
        raise GeometryFitError("too few line-of-sight observations")
    timestamps = np.asarray([item.timestamp for item in observations], dtype=float)
    if float(np.ptp(timestamps)) < config.minimum_time_span_s:
        raise GeometryFitError("line-of-sight history is too short to estimate velocity")
    camera_positions = {
        item.camera_id: np.asarray(item.camera_position_ned, dtype=float)
        for item in observations
    }
    if len(camera_positions) != 2:
        raise GeometryFitError("weighted triangulation requires two camera positions")
    origins = list(camera_positions.values())
    baseline = float(np.linalg.norm(origins[1] - origins[0]))
    if baseline < config.minimum_camera_baseline_m:
        raise GeometryFitError("camera baseline is too short")
    reference_timestamp = float(np.median(timestamps))
    initial_sigma = np.ones(len(observations), dtype=float)
    initial_state, _, initial_condition, _ = _solve_weighted(
        observations, reference_timestamp, initial_sigma
    )
    if initial_condition > config.maximum_condition_number:
        raise GeometryFitError("initial line-of-sight fit is ill-conditioned")
    reference_rays = []
    for origin in origins:
        relative = initial_state[:3] - origin
        distance = float(np.linalg.norm(relative))
        if distance <= 1.0e-9:
            raise GeometryFitError("initial fit lies on a camera center")
        reference_rays.append(relative / distance)
    intersection_angle = math.degrees(
        math.acos(float(np.clip(np.dot(reference_rays[0], reference_rays[1]), -1.0, 1.0)))
    )
    if intersection_angle < config.minimum_intersection_angle_deg:
        raise GeometryFitError("cross-camera intersection geometry is degenerate")

    ranges = []
    for item in observations:
        dt = item.timestamp - reference_timestamp
        point = initial_state[:3] + initial_state[3:] * dt
        ranges.append(
            float(np.linalg.norm(point - np.asarray(item.camera_position_ned, dtype=float)))
        )
    transverse_sigma = np.asarray(
        [
            max(
                distance * math.sqrt(item.bearing_variance_rad2),
                config.minimum_transverse_sigma_m,
            )
            for distance, item in zip(ranges, observations)
        ],
        dtype=float,
    )
    state, covariance, condition, _ = _solve_weighted(
        observations, reference_timestamp, transverse_sigma
    )
    if condition > config.maximum_condition_number:
        raise GeometryFitError("weighted line-of-sight fit is ill-conditioned")

    angular_residuals = []
    depths = []
    for item in observations:
        dt = item.timestamp - reference_timestamp
        point = state[:3] + state[3:] * dt
        relative = point - np.asarray(item.camera_position_ned, dtype=float)
        distance = float(np.linalg.norm(relative))
        if distance <= 1.0e-9:
            raise GeometryFitError("fitted target lies on a camera center")
        predicted = relative / distance
        measured = np.asarray(item.direction_ned, dtype=float)
        angle = math.acos(float(np.clip(np.dot(predicted, measured), -1.0, 1.0)))
        angular_residuals.append(angle * 1000.0)
        depths.append(float(np.dot(relative, measured)))
    minimum_depth = min(depths)
    if minimum_depth <= 0.0:
        raise GeometryFitError("weighted fit places the target behind a camera")
    rms_mrad = float(np.sqrt(np.mean(np.square(angular_residuals))))
    if rms_mrad > config.maximum_fit_rms_mrad:
        raise GeometryFitError("weighted fit angular residual exceeds the hard gate")

    covariance = 0.5 * (covariance + covariance.T)
    diagonal_floor = np.asarray(
        [config.position_variance_floor_m2] * 3
        + [config.velocity_variance_floor_m2_s2] * 3,
        dtype=float,
    )
    diagonal = np.diag(covariance)
    covariance += np.diag(np.maximum(diagonal_floor - diagonal, 0.0))
    return WeightedLineOfSightFit(
        reference_timestamp=reference_timestamp,
        state_ned=tuple(float(value) for value in state),
        covariance_6x6=tuple(float(value) for value in covariance.reshape(-1)),
        rms_angular_residual_mrad=rms_mrad,
        condition_number=condition,
        minimum_depth_m=minimum_depth,
        intersection_angle_deg=intersection_angle,
        cross_camera_median_time_offset_s=_cross_camera_median_time_offset(
            observations
        ),
    )


def _pair_observations(
    snapshot: RevolutionSnapshot,
    track_a_id: str,
    track_b_id: str,
) -> tuple[tuple[BearingObservation, ...], int, int]:
    assert_anonymous_snapshot(snapshot)
    camera_a, camera_b = snapshot.camera_ids
    track_a = _track_for_id(snapshot, camera_a, track_a_id)
    track_b = _track_for_id(snapshot, camera_b, track_b_id)
    observations = []
    counts = []
    for camera_id, track in ((camera_a, track_a), (camera_b, track_b)):
        samples = tuple(
            sample
            for sample in track.samples
            if sample.timestamp <= snapshot.cutoff_timestamp + 1.0e-9
        )
        counts.append(len(samples))
        for sample in samples:
            source_revolution = max(
                1,
                min(
                    snapshot.revolution_index,
                    int(math.floor(max(sample.timestamp - 1.0e-9, 0.0) / 2.0)) + 1,
                ),
            )
            observations.append(
                BearingObservation(
                    camera_id=camera_id,
                    track_id=track.track_id,
                    timestamp=float(sample.timestamp),
                    camera_position_ned=tuple(
                        float(value) for value in snapshot.camera_positions_ned[camera_id]
                    ),
                    direction_ned=tuple(float(value) for value in sample.direction_ned),
                    bearing_variance_rad2=_measurement_variance_rad2(sample),
                    source_revolution_index=source_revolution,
                )
            )
    return (
        tuple(sorted(observations, key=lambda item: (item.timestamp, item.camera_id))),
        counts[0],
        counts[1],
    )


def evaluate_asynchronous_track_pair(
    snapshot: RevolutionSnapshot,
    track_a_id: str,
    track_b_id: str,
    *,
    config: WeightedFitConfig | None = None,
) -> AsynchronousPairFitQuality:
    """Score one A/B candidate directly from each station's original timestamps.

    The function deliberately performs no interpolation to a shared timestamp.
    It is suitable for producing the anonymous cost matrix that main can pass to
    Hungarian assignment before applying its own two-of-three confirmation rule.
    """

    config = config or WeightedFitConfig()
    camera_a, camera_b = snapshot.camera_ids

    def sample_count(camera_id: str, track_id: str) -> int:
        matches = [
            track
            for track in snapshot.tracks[camera_id]
            if track.track_id == track_id
        ]
        return len(matches[0].samples) if len(matches) == 1 else 0

    try:
        observations, count_a, count_b = _pair_observations(
            snapshot, track_a_id, track_b_id
        )
        time_offset = _cross_camera_median_time_offset(observations)
        fit = weighted_line_of_sight_fit(observations, config=config)
    except (GeometryFitError, np.linalg.LinAlgError) as error:
        count_a = sample_count(camera_a, track_a_id)
        count_b = sample_count(camera_b, track_b_id)
        return AsynchronousPairFitQuality(
            camera_a_id=camera_a,
            camera_b_id=camera_b,
            track_a_id=track_a_id,
            track_b_id=track_b_id,
            sample_count_a=count_a,
            sample_count_b=count_b,
            cross_camera_median_time_offset_s=None,
            gate_passed=False,
            rejection_reason=str(error),
            rule_cost=2.0,
        )
    log_condition = math.log10(max(fit.condition_number, 1.0))
    log_limit = math.log10(config.maximum_condition_number)
    angle_penalty = min(
        config.minimum_intersection_angle_deg
        / max(fit.intersection_angle_deg, 1.0e-9),
        2.0,
    )
    rule_cost = float(
        np.clip(
            0.60 * fit.rms_angular_residual_mrad / config.maximum_fit_rms_mrad
            + 0.25 * log_condition / max(log_limit, 1.0)
            + 0.15 * angle_penalty,
            0.0,
            2.0,
        )
    )
    return AsynchronousPairFitQuality(
        camera_a_id=camera_a,
        camera_b_id=camera_b,
        track_a_id=track_a_id,
        track_b_id=track_b_id,
        sample_count_a=count_a,
        sample_count_b=count_b,
        cross_camera_median_time_offset_s=time_offset,
        gate_passed=True,
        rejection_reason="",
        rule_cost=rule_cost,
        reference_timestamp=fit.reference_timestamp,
        state_ned=fit.state_ned,
        covariance_6x6=fit.covariance_6x6,
        fit_rms_mrad=fit.rms_angular_residual_mrad,
        fit_condition_number=fit.condition_number,
        intersection_angle_deg=fit.intersection_angle_deg,
    )


def form_target_hypothesis(
    hypothesis_id: str,
    snapshots: Mapping[int, RevolutionSnapshot],
    confirmed_pairs: Sequence[ConfirmedTrackPair],
    *,
    creation_revolution_index: int,
    online_publications: Mapping[str, Mapping[str, object]],
    config: WeightedFitConfig | None = None,
) -> TargetHypothesis:
    """Create one anonymous hypothesis from prior confirmed A/B geometry only."""

    if creation_revolution_index < 2:
        raise CausalityError("the first revolution cannot contain a prior hypothesis")
    observations = observations_from_confirmed_pairs(
        snapshots,
        confirmed_pairs,
        creation_revolution_index=creation_revolution_index,
        online_publications=online_publications,
    )
    fit = weighted_line_of_sight_fit(observations, config=config)
    return TargetHypothesis(
        hypothesis_id=hypothesis_id,
        created_revolution_index=creation_revolution_index,
        reference_timestamp=fit.reference_timestamp,
        state_ned=fit.state_ned,
        covariance_6x6=fit.covariance_6x6,
        support_count=len(observations),
        confirmed_pairs=tuple(confirmed_pairs),
        fit_rms_mrad=fit.rms_angular_residual_mrad,
        fit_condition_number=fit.condition_number,
        last_observation_timestamp=max(item.timestamp for item in observations),
    )
