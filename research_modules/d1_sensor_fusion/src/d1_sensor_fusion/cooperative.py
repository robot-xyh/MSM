from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

import numpy as np

from .motion import cv_process_noise, cv_transition
from .types import (
    CISourceWeight,
    CooperativeBearingObservation,
    CooperativeLocalizationSummary,
    CooperativeObservationGroup,
    CooperativeTrackEstimate,
    CovarianceIntersectionSummary,
    LosIntersectionAngle,
)


@dataclass(frozen=True)
class BearingLocalizationConfig:
    """Conservative gates for centralized bearing-ray localization."""

    min_observers: int = 2
    min_baseline_m: float = 2.0
    min_intersection_angle_deg: float = 2.0
    max_measurement_skew_s: float = 0.5
    max_information_condition: float = 1.0e8
    max_angular_residual_deg: float = 5.0
    max_perpendicular_residual_m: float = 100.0
    max_weighted_residual_rms: float = 6.0
    process_noise_spectral_density: float = 4.0
    incomplete_covariance_policy: str = "reject"
    default_bearing_sigma_deg: float = 3.0
    default_platform_position_sigma_m: float = 10.0
    default_platform_attitude_sigma_deg: float = 5.0
    default_extrinsics_position_sigma_m: float = 2.0
    default_extrinsics_attitude_sigma_deg: float = 3.0
    max_iterations: int = 4

    def __post_init__(self) -> None:
        if self.min_observers < 2:
            raise ValueError("min_observers must be at least two")
        if self.incomplete_covariance_policy not in {"reject", "inflate"}:
            raise ValueError("incomplete_covariance_policy must be 'reject' or 'inflate'")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        for name in (
            "min_baseline_m",
            "min_intersection_angle_deg",
            "max_measurement_skew_s",
            "max_information_condition",
            "max_angular_residual_deg",
            "max_perpendicular_residual_m",
            "max_weighted_residual_rms",
            "process_noise_spectral_density",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")


def localize_bearing_observation_group(
    group: CooperativeObservationGroup,
    config: BearingLocalizationConfig | None = None,
) -> CooperativeLocalizationSummary:
    """Localize one already-associated canonical track from arbitrary bearing rays.

    The helper only performs numerical localization. It neither associates
    observations nor creates or changes ``global_track_id``.
    """

    cfg = config or BearingLocalizationConfig()
    unique, duplicates = _deduplicate_bearings(group.observations)
    base = _summary_context(group, unique, len(duplicates))

    if len(unique) < cfg.min_observers:
        return _rejected_localization(base, "insufficient_unique_observers")

    measurement_times = np.asarray([item.measurement_timestamp for item in unique], dtype=float)
    if group.estimate_timestamp + 1e-12 < float(np.max(measurement_times)):
        return _rejected_localization(base, "estimate_time_precedes_measurement")
    if base["measurement_skew_s"] > cfg.max_measurement_skew_s:
        return _rejected_localization(base, "measurement_skew_exceeds_limit")

    propagation_needed = any(
        abs(group.estimate_timestamp - item.measurement_timestamp) > 1e-12 for item in unique
    )
    if propagation_needed and group.target_velocity_ned is None:
        return _rejected_localization(base, "target_velocity_required_for_async_propagation")

    covariance_sets: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    incomplete_covariance = False
    for observation in unique:
        result = _observation_covariances(observation, cfg)
        if result is None:
            return _rejected_localization(base, "covariance_incomplete")
        bearing_covariance, platform_covariance, extrinsics_covariance, inflated = result
        if not all(
            _valid_covariance(covariance, size)
            for covariance, size in (
                (bearing_covariance, 2),
                (platform_covariance, 6),
                (extrinsics_covariance, 6),
            )
        ):
            return _rejected_localization(base, "covariance_invalid")
        incomplete_covariance = incomplete_covariance or inflated
        covariance_sets.append(
            (bearing_covariance, platform_covariance, extrinsics_covariance)
        )

    physical_origins = [item.ray_origin_ned for item in unique]
    max_baseline = max(
        float(np.linalg.norm(first - second))
        for first, second in combinations(physical_origins, 2)
    )
    if max_baseline < cfg.min_baseline_m:
        return _rejected_localization(base, "baseline_too_short")

    angles = base["los_intersection_angles"]
    if not angles or max(item.angle_deg for item in angles) < cfg.min_intersection_angle_deg:
        return _rejected_localization(base, "los_geometry_near_collinear")

    velocity = (
        np.zeros(3, dtype=float)
        if group.target_velocity_ned is None
        else np.asarray(group.target_velocity_ned, dtype=float)
    )
    propagated_origins: list[np.ndarray] = []
    directions: list[np.ndarray] = []
    process_covariances: list[np.ndarray] = []
    covariance_inflation_trace = 0.0
    for observation in unique:
        dt = group.estimate_timestamp - observation.measurement_timestamp
        propagated_origins.append(observation.ray_origin_ned + velocity * dt)
        directions.append(observation.ray_direction_ned)
        process_covariance = _time_process_covariance(
            velocity,
            dt,
            observation.timestamp_uncertainty_s,
            cfg.process_noise_spectral_density,
        )
        process_covariances.append(process_covariance)
        covariance_inflation_trace += float(np.trace(process_covariance))

    position = _unweighted_ray_solution(propagated_origins, directions)
    if position is None:
        return _rejected_localization(base, "information_rank_deficient")

    information = np.zeros((3, 3), dtype=float)
    weighted_residuals: list[float] = []
    for _ in range(cfg.max_iterations):
        information.fill(0.0)
        information_vector = np.zeros(3, dtype=float)
        for observation, origin, direction, covariance_set, process_covariance in zip(
            unique,
            propagated_origins,
            directions,
            covariance_sets,
            process_covariances,
        ):
            distance = max(float(np.dot(position - origin, direction)), 1.0)
            ray_information, _ = _ray_information(
                direction,
                distance,
                covariance_set,
                process_covariance,
            )
            information += ray_information
            information_vector += ray_information @ origin
        if np.linalg.matrix_rank(information) < 3:
            return _rejected_localization(
                base,
                "information_rank_deficient",
                information_matrix=information,
            )
        position = np.linalg.solve(information, information_vector)

    information = 0.5 * (information + information.T)
    eigenvalues = np.linalg.eigvalsh(information)
    rank = int(np.linalg.matrix_rank(information))
    condition = (
        float("inf")
        if eigenvalues[0] <= 0.0
        else float(eigenvalues[-1] / eigenvalues[0])
    )
    if rank < 3:
        return _rejected_localization(
            base,
            "information_rank_deficient",
            information_matrix=information,
            information_rank=rank,
            information_condition=condition,
        )
    if not np.isfinite(condition) or condition > cfg.max_information_condition:
        return _rejected_localization(
            base,
            "information_condition_exceeds_limit",
            information_matrix=information,
            information_rank=rank,
            information_condition=condition,
        )

    residuals: list[float] = []
    angular_residuals: list[float] = []
    weighted_residuals.clear()
    for origin, direction, covariance_set, process_covariance in zip(
        propagated_origins,
        directions,
        covariance_sets,
        process_covariances,
    ):
        delta = position - origin
        depth = float(np.dot(delta, direction))
        if depth <= 0.0:
            return _rejected_localization(
                base,
                "solution_behind_observer",
                information_matrix=information,
                information_rank=rank,
                information_condition=condition,
            )
        projector = np.eye(3) - np.outer(direction, direction)
        perpendicular = projector @ delta
        residuals.append(float(np.linalg.norm(perpendicular)))
        angular_residuals.append(
            float(
                np.degrees(
                    np.arccos(
                        np.clip(np.dot(delta / np.linalg.norm(delta), direction), -1.0, 1.0)
                    )
                )
            )
        )
        _, tangent_covariance = _ray_information(
            direction,
            depth,
            covariance_set,
            process_covariance,
        )
        basis = _tangent_basis(direction)
        tangent_residual = basis.T @ perpendicular
        weighted_residuals.append(
            float(tangent_residual.T @ np.linalg.solve(tangent_covariance, tangent_residual))
        )

    weighted_rms = float(np.sqrt(np.mean(weighted_residuals)))
    rejection_reason: str | None = None
    if max(residuals) > cfg.max_perpendicular_residual_m:
        rejection_reason = "perpendicular_residual_exceeds_limit"
    elif max(angular_residuals) > cfg.max_angular_residual_deg:
        rejection_reason = "angular_residual_exceeds_limit"
    elif weighted_rms > cfg.max_weighted_residual_rms:
        rejection_reason = "weighted_residual_exceeds_limit"
    if rejection_reason is not None:
        return _rejected_localization(
            base,
            rejection_reason,
            information_matrix=information,
            information_rank=rank,
            information_condition=condition,
            residuals_m=tuple(residuals),
            angular_residuals_deg=tuple(angular_residuals),
            weighted_residual_rms=weighted_rms,
            covariance_inflation_trace=covariance_inflation_trace,
        )

    covariance = np.linalg.inv(information)
    covariance = 0.5 * (covariance + covariance.T)
    quality_flags: list[str] = []
    if covariance_inflation_trace > 0.0:
        quality_flags.append("time_process_covariance_inflated")
    if incomplete_covariance:
        quality_flags.append("incomplete_covariance_inflated")
    return CooperativeLocalizationSummary(
        **base,
        accepted=True,
        geometry_reason=(
            "accepted_with_covariance_inflation" if quality_flags else "accepted"
        ),
        quality_flags=tuple(quality_flags),
        information_matrix=information,
        information_rank=rank,
        information_condition=condition,
        residuals_m=tuple(residuals),
        angular_residuals_deg=tuple(angular_residuals),
        weighted_residual_rms=weighted_rms,
        position_ned=position,
        position_covariance_ned=covariance,
        covariance_inflation_trace=covariance_inflation_trace,
    )


def covariance_intersection(
    estimates: Iterable[CooperativeTrackEstimate],
    estimate_timestamp: float | None = None,
    *,
    process_noise_spectral_density: float = 1.0,
    weight_grid_size: int = 101,
) -> CovarianceIntersectionSummary:
    """Fuse same-ID NED states without assuming known cross-correlation."""

    inputs = tuple(estimates)
    unique, duplicate_uuids = _deduplicate_track_estimates(inputs)
    if not unique:
        return _rejected_ci(inputs, "no_unique_estimates", duplicate_uuids)

    global_track_id = unique[0].global_track_id
    if any(item.global_track_id != global_track_id for item in unique):
        return _rejected_ci(inputs, "global_track_id_mismatch", duplicate_uuids)

    common_time = (
        max(item.estimate_timestamp for item in unique)
        if estimate_timestamp is None
        else float(estimate_timestamp)
    )
    if any(common_time + 1e-12 < item.estimate_timestamp for item in unique):
        return _rejected_ci(
            inputs,
            "estimate_time_precedes_source_state",
            duplicate_uuids,
            global_track_id=global_track_id,
            estimate_timestamp=common_time,
        )
    if weight_grid_size < 3:
        raise ValueError("weight_grid_size must be at least three")

    propagated: list[CooperativeTrackEstimate] = []
    for item in unique:
        if not _valid_covariance(item.covariance, 6, positive_definite=True):
            return _rejected_ci(
                inputs,
                "covariance_invalid",
                duplicate_uuids,
                global_track_id=global_track_id,
                estimate_timestamp=common_time,
            )
        propagated.append(
            _propagate_track_estimate(item, common_time, process_noise_spectral_density)
        )

    state = propagated[0].state.copy()
    covariance = propagated[0].covariance.copy()
    effective_weights = {propagated[0].message_uuid: 1.0}
    lineage_by_uuid = {
        item.message_uuid: tuple(item.source_lineage) for item in propagated
    }
    for item in propagated[1:]:
        state, covariance, previous_weight = _covariance_intersection_pair(
            state,
            covariance,
            item.state,
            item.covariance,
            weight_grid_size,
        )
        effective_weights = {
            key: value * previous_weight for key, value in effective_weights.items()
        }
        effective_weights[item.message_uuid] = 1.0 - previous_weight

    source_lineage = tuple(
        dict.fromkeys(lineage for item in propagated for lineage in item.source_lineage)
    )
    source_weights = tuple(
        CISourceWeight(
            message_uuid=item.message_uuid,
            source_lineage=lineage_by_uuid[item.message_uuid],
            weight=float(effective_weights.get(item.message_uuid, 0.0)),
        )
        for item in propagated
    )
    fused = CooperativeTrackEstimate(
        global_track_id=global_track_id,
        state=state,
        covariance=covariance,
        estimate_timestamp=common_time,
        measurement_timestamp=max(item.measurement_timestamp for item in propagated),
        arrival_timestamp=max(item.arrival_timestamp for item in propagated),
        message_uuid="ci:" + "|".join(item.message_uuid for item in propagated),
        source_lineage=source_lineage,
        timestamp_uncertainty_s=max(item.timestamp_uncertainty_s for item in propagated),
    )
    return CovarianceIntersectionSummary(
        global_track_id=global_track_id,
        estimate_timestamp=common_time,
        accepted=True,
        reason="accepted" if not duplicate_uuids else "accepted_after_source_deduplication",
        input_count=len(inputs),
        unique_source_count=len(propagated),
        duplicate_source_count=len(duplicate_uuids),
        duplicate_message_uuids=tuple(duplicate_uuids),
        source_weights=source_weights,
        source_measurement_timestamps=tuple(item.measurement_timestamp for item in propagated),
        source_arrival_timestamps=tuple(item.arrival_timestamp for item in propagated),
        fused_estimate=fused,
    )


def _deduplicate_bearings(
    observations: Iterable[CooperativeBearingObservation],
) -> tuple[list[CooperativeBearingObservation], list[CooperativeBearingObservation]]:
    unique: list[CooperativeBearingObservation] = []
    duplicates: list[CooperativeBearingObservation] = []
    message_uuids: set[str] = set()
    lineage_keys: set[tuple[str, ...]] = set()
    for observation in observations:
        message_uuid = observation.lineage.message_uuid
        lineage_key = observation.lineage.lineage_key
        if message_uuid in message_uuids or lineage_key in lineage_keys:
            duplicates.append(observation)
            continue
        unique.append(observation)
        message_uuids.add(message_uuid)
        lineage_keys.add(lineage_key)
    return unique, duplicates


def _summary_context(
    group: CooperativeObservationGroup,
    observations: list[CooperativeBearingObservation],
    duplicate_count: int,
) -> dict[str, object]:
    measurement_timestamps = tuple(item.measurement_timestamp for item in observations)
    arrival_timestamps = tuple(item.arrival_timestamp for item in observations)
    angles = tuple(
        LosIntersectionAngle(
            first_observer_id=first.lineage.observer_id,
            second_observer_id=second.lineage.observer_id,
            angle_deg=_acute_angle_deg(first.ray_direction_ned, second.ray_direction_ned),
        )
        for first, second in combinations(observations, 2)
    )
    measurement_skew = (
        max(measurement_timestamps) - min(measurement_timestamps)
        if measurement_timestamps
        else 0.0
    )
    max_horizon = max(
        (abs(group.estimate_timestamp - timestamp) for timestamp in measurement_timestamps),
        default=0.0,
    )
    return {
        "global_track_id": group.global_track_id,
        "estimate_timestamp": group.estimate_timestamp,
        "input_observer_count": len(group.observations),
        "unique_observer_count": len(observations),
        "duplicate_observer_count": duplicate_count,
        "observer_lineages": tuple(item.lineage for item in observations),
        "measurement_timestamps": measurement_timestamps,
        "arrival_timestamps": arrival_timestamps,
        "measurement_skew_s": float(measurement_skew),
        "max_propagation_horizon_s": float(max_horizon),
        "los_intersection_angles": angles,
    }


def _rejected_localization(
    base: dict[str, object],
    reason: str,
    *,
    information_matrix: np.ndarray | None = None,
    information_rank: int = 0,
    information_condition: float = float("inf"),
    residuals_m: tuple[float, ...] = (),
    angular_residuals_deg: tuple[float, ...] = (),
    weighted_residual_rms: float | None = None,
    covariance_inflation_trace: float = 0.0,
) -> CooperativeLocalizationSummary:
    return CooperativeLocalizationSummary(
        **base,
        accepted=False,
        geometry_reason=reason,
        quality_flags=(reason,),
        information_matrix=(
            np.zeros((3, 3), dtype=float)
            if information_matrix is None
            else information_matrix
        ),
        information_rank=information_rank,
        information_condition=information_condition,
        residuals_m=residuals_m,
        angular_residuals_deg=angular_residuals_deg,
        weighted_residual_rms=weighted_residual_rms,
        position_ned=None,
        position_covariance_ned=None,
        covariance_inflation_trace=covariance_inflation_trace,
    )


def _observation_covariances(
    observation: CooperativeBearingObservation,
    config: BearingLocalizationConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool] | None:
    values = (
        observation.bearing_covariance,
        observation.platform_pose_covariance,
        observation.sensor_extrinsics_covariance,
    )
    if all(value is not None for value in values):
        return values[0], values[1], values[2], False  # type: ignore[return-value]
    if config.incomplete_covariance_policy == "reject":
        return None

    bearing = values[0]
    if bearing is None:
        bearing = np.eye(2) * np.deg2rad(config.default_bearing_sigma_deg) ** 2
    platform = values[1]
    if platform is None:
        platform = np.diag(
            [config.default_platform_position_sigma_m**2] * 3
            + [np.deg2rad(config.default_platform_attitude_sigma_deg) ** 2] * 3
        )
    extrinsics = values[2]
    if extrinsics is None:
        extrinsics = np.diag(
            [config.default_extrinsics_position_sigma_m**2] * 3
            + [np.deg2rad(config.default_extrinsics_attitude_sigma_deg) ** 2] * 3
        )
    return bearing, platform, extrinsics, True


def _valid_covariance(
    covariance: np.ndarray,
    size: int,
    *,
    positive_definite: bool = False,
) -> bool:
    array = np.asarray(covariance, dtype=float)
    if array.shape != (size, size) or not np.all(np.isfinite(array)):
        return False
    if not np.allclose(array, array.T, atol=1e-9):
        return False
    minimum = float(np.min(np.linalg.eigvalsh(array)))
    return minimum > 1e-12 if positive_definite else minimum >= -1e-12


def _unweighted_ray_solution(
    origins: list[np.ndarray],
    directions: list[np.ndarray],
) -> np.ndarray | None:
    information = np.zeros((3, 3), dtype=float)
    information_vector = np.zeros(3, dtype=float)
    for origin, direction in zip(origins, directions):
        projector = np.eye(3) - np.outer(direction, direction)
        information += projector
        information_vector += projector @ origin
    if np.linalg.matrix_rank(information) < 3:
        return None
    return np.linalg.solve(information, information_vector)


def _ray_information(
    direction: np.ndarray,
    distance: float,
    covariance_set: tuple[np.ndarray, np.ndarray, np.ndarray],
    process_covariance: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    bearing_covariance, platform_covariance, extrinsics_covariance = covariance_set
    basis = _tangent_basis(direction)
    rotation_jacobian = -distance * _skew(direction)
    pose_jacobian = np.hstack((np.eye(3), rotation_jacobian))
    spatial_covariance = (
        pose_jacobian @ platform_covariance @ pose_jacobian.T
        + pose_jacobian @ extrinsics_covariance @ pose_jacobian.T
        + process_covariance
    )
    tangent_covariance = (
        distance**2 * bearing_covariance
        + basis.T @ spatial_covariance @ basis
    )
    tangent_covariance = _positive_definite(tangent_covariance)
    information = basis @ np.linalg.inv(tangent_covariance) @ basis.T
    return 0.5 * (information + information.T), tangent_covariance


def _time_process_covariance(
    velocity: np.ndarray,
    dt: float,
    timestamp_uncertainty_s: float,
    spectral_density: float,
) -> np.ndarray:
    process_variance = 0.25 * abs(float(dt)) ** 4 * max(float(spectral_density), 0.0)
    timing_covariance = np.outer(velocity, velocity) * float(timestamp_uncertainty_s) ** 2
    return process_variance * np.eye(3) + timing_covariance


def _tangent_basis(direction: np.ndarray) -> np.ndarray:
    axis = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(direction, axis))) > 0.9:
        axis = np.array([0.0, 1.0, 0.0])
    first = np.cross(direction, axis)
    first /= np.linalg.norm(first)
    second = np.cross(direction, first)
    second /= np.linalg.norm(second)
    return np.column_stack((first, second))


def _skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = vector
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def _positive_definite(matrix: np.ndarray, floor: float = 1e-12) -> np.ndarray:
    symmetric = 0.5 * (matrix + matrix.T)
    values, vectors = np.linalg.eigh(symmetric)
    return vectors @ np.diag(np.maximum(values, floor)) @ vectors.T


def _acute_angle_deg(first: np.ndarray, second: np.ndarray) -> float:
    cosine = abs(float(np.dot(first, second)))
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def _deduplicate_track_estimates(
    estimates: tuple[CooperativeTrackEstimate, ...],
) -> tuple[list[CooperativeTrackEstimate], list[str]]:
    unique: list[CooperativeTrackEstimate] = []
    duplicates: list[str] = []
    message_uuids: set[str] = set()
    lineage_keys: set[tuple[str, ...]] = set()
    for estimate in estimates:
        lineage_key = tuple(estimate.source_lineage)
        if estimate.message_uuid in message_uuids or lineage_key in lineage_keys:
            duplicates.append(estimate.message_uuid)
            continue
        unique.append(estimate)
        message_uuids.add(estimate.message_uuid)
        lineage_keys.add(lineage_key)
    return unique, duplicates


def _propagate_track_estimate(
    estimate: CooperativeTrackEstimate,
    common_time: float,
    spectral_density: float,
) -> CooperativeTrackEstimate:
    dt = common_time - estimate.estimate_timestamp
    transition = cv_transition(dt)
    state = transition @ estimate.state
    covariance = (
        transition @ estimate.covariance @ transition.T
        + cv_process_noise(dt, max(float(spectral_density), 0.0))
    )
    covariance[:3, :3] += (
        np.outer(estimate.state[3:], estimate.state[3:])
        * estimate.timestamp_uncertainty_s**2
    )
    return CooperativeTrackEstimate(
        global_track_id=estimate.global_track_id,
        state=state,
        covariance=0.5 * (covariance + covariance.T),
        estimate_timestamp=common_time,
        measurement_timestamp=estimate.measurement_timestamp,
        arrival_timestamp=estimate.arrival_timestamp,
        message_uuid=estimate.message_uuid,
        source_lineage=estimate.source_lineage,
        timestamp_uncertainty_s=estimate.timestamp_uncertainty_s,
    )


def _covariance_intersection_pair(
    first_state: np.ndarray,
    first_covariance: np.ndarray,
    second_state: np.ndarray,
    second_covariance: np.ndarray,
    grid_size: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    first_information = np.linalg.inv(first_covariance)
    second_information = np.linalg.inv(second_covariance)
    best: tuple[float, float, np.ndarray] | None = None
    candidates = sorted(np.linspace(0.0, 1.0, grid_size), key=lambda value: abs(value - 0.5))
    for weight in candidates:
        information = weight * first_information + (1.0 - weight) * second_information
        covariance = np.linalg.inv(information)
        sign, logdet = np.linalg.slogdet(covariance)
        if sign <= 0.0:
            continue
        if best is None or logdet < best[0] - 1e-12:
            best = (float(logdet), float(weight), covariance)
    if best is None:
        raise ValueError("covariance intersection failed to find a positive-definite result")
    _, weight, covariance = best
    state = covariance @ (
        weight * first_information @ first_state
        + (1.0 - weight) * second_information @ second_state
    )
    return state, 0.5 * (covariance + covariance.T), weight


def _rejected_ci(
    inputs: tuple[CooperativeTrackEstimate, ...],
    reason: str,
    duplicate_uuids: list[str],
    *,
    global_track_id: str | None = None,
    estimate_timestamp: float | None = None,
) -> CovarianceIntersectionSummary:
    return CovarianceIntersectionSummary(
        global_track_id=global_track_id,
        estimate_timestamp=estimate_timestamp,
        accepted=False,
        reason=reason,
        input_count=len(inputs),
        unique_source_count=max(0, len(inputs) - len(duplicate_uuids)),
        duplicate_source_count=len(duplicate_uuids),
        duplicate_message_uuids=tuple(duplicate_uuids),
        source_weights=(),
        source_measurement_timestamps=tuple(item.measurement_timestamp for item in inputs),
        source_arrival_timestamps=tuple(item.arrival_timestamp for item in inputs),
        fused_estimate=None,
    )
