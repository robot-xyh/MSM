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
    rejected_pairs: list[RejectedPair]
    candidate_counts_by_track: dict[str, int]
    candidate_counts_by_detection: dict[str, int]


def predicted_measurement(track: GlobalTrack) -> np.ndarray:
    return POSITION_H @ track.state


def innovation_covariance(track: GlobalTrack, detection: Detection) -> np.ndarray:
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
) -> GatedCost:
    rows = len(tracks)
    cols = len(detections)
    cost_matrix = np.full((rows, cols), large_cost, dtype=float)
    distance_matrix = np.full((rows, cols), np.inf, dtype=float)
    feature_cost_matrix = np.zeros((rows, cols), dtype=float)
    rejected: list[RejectedPair] = []

    for row, track in enumerate(tracks):
        for col, detection in enumerate(detections):
            distance = mahalanobis_squared(track, detection)
            distance_matrix[row, col] = distance
            feature_cost = _feature_cost(track, detection)
            feature_cost_matrix[row, col] = feature_cost
            if distance <= gate_threshold:
                cost_matrix[row, col] = distance + feature_weight * feature_cost
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
        rejected_pairs=rejected,
        candidate_counts_by_track=candidate_counts_by_track,
        candidate_counts_by_detection=candidate_counts_by_detection,
    )


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
