"""Mahalanobis gating utilities."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import Detection, GlobalTrack, RejectedPair

POSITION_H = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ],
    dtype=float,
)
LARGE_COST = 1.0e9


@dataclass(frozen=True, slots=True)
class GatedCost:
    cost_matrix: np.ndarray
    distance_matrix: np.ndarray
    feature_cost_matrix: np.ndarray
    motion_cost_matrix: np.ndarray
    source_continuity_cost_matrix: np.ndarray
    gate_threshold_matrix: np.ndarray
    rejected_pairs: list[RejectedPair]
    candidate_counts_by_track: dict[str, int]
    candidate_counts_by_detection: dict[str, int]
    gate_thresholds_by_track: dict[str, float]
    target_density_by_track: dict[str, float]
    track_quality_by_track: dict[str, float]
    position_covariance_trace_by_track: dict[str, float]
    previous_association_risk_by_track: dict[str, float]
    covariance_regularized: bool
    covariance_consistency_by_track: dict[str, dict[str, object]]
    covariance_consistency_by_detection: dict[str, dict[str, object]]


def predicted_measurement(track: GlobalTrack) -> np.ndarray:
    return POSITION_H @ track.state


def innovation_covariance(track: GlobalTrack, detection: Detection) -> np.ndarray:
    track.ensure_covariance_consistency()
    detection.ensure_covariance_consistency()
    return POSITION_H @ track.covariance @ POSITION_H.T + detection.covariance


def mahalanobis_squared(track: GlobalTrack, detection: Detection) -> float:
    residual = detection.position - predicted_measurement(track)
    covariance = innovation_covariance(track, detection)
    try:
        solved = np.linalg.solve(covariance, residual)
    except np.linalg.LinAlgError:
        solved = np.linalg.pinv(covariance) @ residual
    return float(residual.T @ solved)


def build_gated_cost_matrix(
    tracks: list[GlobalTrack],
    detections: list[Detection],
    gate_threshold: float,
    large_cost: float = LARGE_COST,
    feature_weight: float = 0.0,
    motion_weight: float = 0.0,
    quality_aware_gate: bool = False,
    min_gate_threshold: float = 4.0,
    max_gate_threshold: float = 16.0,
    source_continuity_weight: float = 0.0,
) -> GatedCost:
    for track in tracks:
        track.ensure_covariance_consistency()
    for detection in detections:
        detection.ensure_covariance_consistency()

    rows = len(tracks)
    cols = len(detections)
    cost_matrix = np.full((rows, cols), large_cost, dtype=float)
    distance_matrix = np.full((rows, cols), np.inf, dtype=float)
    feature_cost_matrix = np.zeros((rows, cols), dtype=float)
    motion_cost_matrix = np.zeros((rows, cols), dtype=float)
    source_continuity_cost_matrix = np.zeros((rows, cols), dtype=float)
    gate_threshold_matrix = np.full((rows, cols), float(gate_threshold), dtype=float)
    rejected: list[RejectedPair] = []
    target_density_by_track = _target_density_by_track(tracks, detections)
    track_quality_by_track = {
        track.global_track_id: estimate_track_quality(track) for track in tracks
    }
    position_covariance_trace_by_track = {
        track.global_track_id: track_position_covariance_trace(track)
        for track in tracks
    }
    previous_association_risk_by_track = {
        track.global_track_id: _track_previous_association_risk(track)
        for track in tracks
    }
    covariance_consistency_by_track = {
        track.global_track_id: dict(track.covariance_consistency) for track in tracks
    }
    covariance_consistency_by_detection = {
        detection.detection_id: dict(detection.covariance_consistency)
        for detection in detections
    }
    covariance_regularized = any(
        track.covariance_regularized for track in tracks
    ) or any(detection.covariance_regularized for detection in detections)
    gate_thresholds_by_track = {
        track.global_track_id: _quality_aware_gate_threshold(
            track=track,
            base_threshold=gate_threshold,
            quality=track_quality_by_track[track.global_track_id],
            target_density=target_density_by_track[track.global_track_id],
            position_covariance_trace=position_covariance_trace_by_track[
                track.global_track_id
            ],
            previous_association_risk=previous_association_risk_by_track[
                track.global_track_id
            ],
            enabled=quality_aware_gate,
            min_gate_threshold=min_gate_threshold,
            max_gate_threshold=max_gate_threshold,
        )
        for track in tracks
    }

    for row, track in enumerate(tracks):
        track_gate_threshold = gate_thresholds_by_track[track.global_track_id]
        for col, detection in enumerate(detections):
            distance = mahalanobis_squared(track, detection)
            distance_matrix[row, col] = distance
            feature_cost = _feature_cost(track, detection)
            feature_cost_matrix[row, col] = feature_cost
            motion_cost = motion_consistency_cost(track, detection)
            motion_cost_matrix[row, col] = motion_cost
            source_continuity_cost = _source_continuity_cost(track, detection)
            source_continuity_cost_matrix[row, col] = source_continuity_cost
            gate_threshold_matrix[row, col] = track_gate_threshold
            if distance <= track_gate_threshold:
                cost_matrix[row, col] = (
                    distance
                    + feature_weight * feature_cost
                    + motion_weight * motion_cost
                    + source_continuity_weight * source_continuity_cost
                )
            else:
                rejected.append(
                    RejectedPair(
                        track_id=track.global_track_id,
                        detection_id=detection.detection_id,
                        reason="mahalanobis_gate",
                        value=distance,
                    )
                )

    candidate_counts_by_track = {
        track.global_track_id: int(np.sum(cost_matrix[row] < large_cost))
        for row, track in enumerate(tracks)
    }
    candidate_counts_by_detection = {
        detection.detection_id: int(np.sum(cost_matrix[:, col] < large_cost))
        for col, detection in enumerate(detections)
    }
    return GatedCost(
        cost_matrix=cost_matrix,
        distance_matrix=distance_matrix,
        feature_cost_matrix=feature_cost_matrix,
        motion_cost_matrix=motion_cost_matrix,
        source_continuity_cost_matrix=source_continuity_cost_matrix,
        gate_threshold_matrix=gate_threshold_matrix,
        rejected_pairs=rejected,
        candidate_counts_by_track=candidate_counts_by_track,
        candidate_counts_by_detection=candidate_counts_by_detection,
        gate_thresholds_by_track=gate_thresholds_by_track,
        target_density_by_track=target_density_by_track,
        track_quality_by_track=track_quality_by_track,
        position_covariance_trace_by_track=position_covariance_trace_by_track,
        previous_association_risk_by_track=previous_association_risk_by_track,
        covariance_regularized=covariance_regularized,
        covariance_consistency_by_track=covariance_consistency_by_track,
        covariance_consistency_by_detection=covariance_consistency_by_detection,
    )


def source_track_ids_from_detection(detection: Detection) -> set[str]:
    """Return upstream track lineage identifiers, never evaluator truth IDs."""

    values: list[object] = []
    for key in ("source_global_track_id", "source_track_id"):
        value = detection.metadata.get(key)
        if value is not None:
            values.append(value)
    multiple = detection.metadata.get("source_track_ids")
    if isinstance(multiple, (list, tuple, set, frozenset)):
        values.extend(multiple)
    return {str(value) for value in values if value is not None and str(value)}


def _source_continuity_cost(track: GlobalTrack, detection: Detection) -> float:
    detection_source_ids = source_track_ids_from_detection(detection)
    if not track.source_track_ids or not detection_source_ids:
        return 0.0
    return 0.0 if track.source_track_ids & detection_source_ids else 1.0


def ambiguity_score_from_costs(
    cost_matrix: np.ndarray,
    large_cost: float = LARGE_COST,
) -> float:
    """Return 0 for clear association and approach 1 for close alternatives."""

    if cost_matrix.size == 0:
        return 0.0

    row_scores: list[float] = []
    for row in cost_matrix:
        valid = np.sort(row[row < large_cost])
        if len(valid) < 2:
            row_scores.append(0.0)
            continue
        gap = max(float(valid[1] - valid[0]), 0.0)
        row_scores.append(float(np.exp(-0.5 * gap)))

    return float(np.mean(row_scores)) if row_scores else 0.0


def _feature_cost(track: GlobalTrack, detection: Detection) -> float:
    if track.feature is None or detection.feature is None:
        return 0.0
    if track.feature.shape != detection.feature.shape:
        return 0.0
    residual = track.feature - detection.feature
    return float(residual.T @ residual)


def motion_consistency_cost(track: GlobalTrack, detection: Detection) -> float:
    """Return a lightweight motion consistency penalty in roughly [0, 3]."""

    velocity = track.state[2:4]
    predicted_position = predicted_measurement(track)
    residual = detection.position - predicted_position
    velocity_direction_cost = _direction_cost(velocity, residual)

    history_samples = _recent_measurement_history(track)
    history_direction_cost = 0.0
    acceleration_cost = 0.0
    if history_samples:
        last_timestamp, last_position = history_samples[-1]
        dt = max(float(detection.timestamp) - last_timestamp, 1.0e-6)
        candidate_velocity = (detection.position - last_position) / dt
        acceleration_cost = _acceleration_cost(velocity, candidate_velocity, dt)
        if len(history_samples) >= 2:
            previous_timestamp, previous_position = history_samples[-2]
            previous_dt = max(last_timestamp - previous_timestamp, 1.0e-6)
            history_velocity = (last_position - previous_position) / previous_dt
            history_direction_cost = _direction_cost(
                history_velocity,
                candidate_velocity,
            )
        else:
            history_direction_cost = _direction_cost(velocity, candidate_velocity)

    return float(
        min(
            3.0,
            velocity_direction_cost
            + 0.75 * history_direction_cost
            + 0.50 * acceleration_cost,
        )
    )


def estimate_track_quality(track: GlobalTrack) -> float:
    """Estimate track quality from lifecycle, covariance, hits, and misses."""

    position_trace = track_position_covariance_trace(track)
    covariance_score = 1.0 / (1.0 + position_trace / 10.0)
    confirmation_score = min(1.0, max(float(track.hits), 0.0) / 4.0)
    age_score = min(1.0, max(float(track.age), float(track.hits), 0.0) / 6.0)
    miss_score = max(0.0, 1.0 - min(float(track.misses), 5.0) / 5.0)
    lifecycle_score = _lifecycle_quality_score(track)
    identity_score = float(np.clip(track.identity_confidence, 0.0, 1.0))
    quality = (
        0.28 * covariance_score
        + 0.18 * confirmation_score
        + 0.12 * age_score
        + 0.18 * miss_score
        + 0.16 * lifecycle_score
        + 0.08 * identity_score
    )
    return float(np.clip(quality, 0.0, 1.0))


def track_position_covariance_trace(track: GlobalTrack) -> float:
    position_covariance = POSITION_H @ track.covariance @ POSITION_H.T
    return float(max(np.trace(position_covariance), 0.0))


def _quality_aware_gate_threshold(
    *,
    track: GlobalTrack,
    base_threshold: float,
    quality: float,
    target_density: float,
    position_covariance_trace: float,
    previous_association_risk: float,
    enabled: bool,
    min_gate_threshold: float,
    max_gate_threshold: float,
) -> float:
    del track
    if not enabled:
        return float(base_threshold)

    low_quality_relaxation = max(0.0, 0.65 - quality) * 0.35
    covariance_relaxation = min(0.25, max(0.0, position_covariance_trace - 2.0) / 40.0)
    density_tightening = min(0.30, max(0.0, target_density) * 0.30)
    ambiguity_tightening = min(
        0.18,
        max(0.0, previous_association_risk) * (0.18 if target_density > 0.25 else 0.08),
    )
    factor = (
        1.0
        + low_quality_relaxation
        + covariance_relaxation
        - density_tightening
        - ambiguity_tightening
    )
    adjusted = float(base_threshold) * factor
    lower = min(float(min_gate_threshold), float(max_gate_threshold))
    upper = max(float(min_gate_threshold), float(max_gate_threshold))
    return float(np.clip(adjusted, lower, upper))


def _target_density_by_track(
    tracks: list[GlobalTrack],
    detections: list[Detection],
) -> dict[str, float]:
    if not tracks:
        return {}

    predicted_positions = [predicted_measurement(track) for track in tracks]
    densities: dict[str, float] = {}
    for row, track in enumerate(tracks):
        position = predicted_positions[row]
        scale = max(1.0, (track_position_covariance_trace(track) ** 0.5) * 3.0)
        track_neighbors = 0
        for other_row, other_position in enumerate(predicted_positions):
            if other_row == row:
                continue
            if np.linalg.norm(position - other_position) <= scale:
                track_neighbors += 1
        near_detections = sum(
            1 for detection in detections if np.linalg.norm(position - detection.position) <= scale
        )
        extra_near_detections = max(0, near_detections - 1)
        densities[track.global_track_id] = float(
            min(1.0, (track_neighbors + extra_near_detections) / 3.0)
        )
    return densities


def _track_previous_association_risk(track: GlobalTrack) -> float:
    return float(np.clip(getattr(track, "association_risk", 0.0), 0.0, 1.0))


def _direction_cost(reference: np.ndarray, candidate: np.ndarray) -> float:
    reference_norm = float(np.linalg.norm(reference))
    candidate_norm = float(np.linalg.norm(candidate))
    if reference_norm <= 1.0e-9 or candidate_norm <= 1.0e-9:
        return 0.0
    cosine = float(np.dot(reference, candidate) / (reference_norm * candidate_norm))
    return float((1.0 - np.clip(cosine, -1.0, 1.0)) / 2.0)


def _acceleration_cost(
    reference_velocity: np.ndarray,
    candidate_velocity: np.ndarray,
    dt: float,
) -> float:
    acceleration = (candidate_velocity - reference_velocity) / max(dt, 1.0e-6)
    acceleration_norm = float(np.linalg.norm(acceleration))
    speed_scale = max(1.0, float(np.linalg.norm(reference_velocity)) + 1.0)
    return float(np.clip(acceleration_norm / (2.0 * speed_scale), 0.0, 1.0))


def _recent_measurement_history(track: GlobalTrack) -> list[tuple[float, np.ndarray]]:
    samples: list[tuple[float, np.ndarray]] = []
    for entry in track.history:
        if entry.get("event") not in {"create", "update"}:
            continue
        state = entry.get("state")
        if state is None:
            continue
        samples.append(
            (
                float(entry.get("timestamp", track.timestamp)),
                np.asarray(state, dtype=float).reshape(-1)[:2],
            )
        )
    return samples[-3:]


def _lifecycle_quality_score(track: GlobalTrack) -> float:
    value = getattr(track.lifecycle_state, "value", str(track.lifecycle_state))
    if value == "engageable":
        return 1.0
    if value == "confirmed":
        return 0.78
    if value == "tentative":
        return 0.45
    if value == "lost":
        return 0.18
    return 0.0
