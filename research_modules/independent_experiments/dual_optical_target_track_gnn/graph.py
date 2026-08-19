"""Build hard-gated target-hypothesis to local-track bipartite graphs."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping, Sequence

import numpy as np

from dual_optical_online_benchmark.contracts import (
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
)

from .contracts import (
    EDGE_FEATURE_NAMES,
    TARGET_FEATURE_NAMES,
    TRACK_FEATURE_NAMES,
    TargetHypothesis,
    TargetTrackGraph,
    payload_fingerprint,
)
from .geometry import CausalityError, assert_anonymous_snapshot


CAUSAL_EVIDENCE_EPSILON_S = 1.0e-9


@dataclass(frozen=True)
class TargetTrackGate:
    minimum_track_samples: int = 2
    maximum_bearing_residual_mrad: float = 30.0
    maximum_mahalanobis2: float = 25.0
    maximum_prediction_age_s: float = 8.0
    minimum_range_m: float = 10.0
    maximum_range_m: float = 100_000.0
    maximum_angular_rate_residual_deg_s: float = 8.0
    unmatched_cost: float = 1.0

    def __post_init__(self) -> None:
        if self.minimum_track_samples < 1:
            raise ValueError("minimum_track_samples must be positive")
        if self.maximum_bearing_residual_mrad <= 0.0:
            raise ValueError("maximum bearing residual must be positive")
        if self.maximum_mahalanobis2 <= 0.0:
            raise ValueError("maximum Mahalanobis distance must be positive")
        if self.maximum_prediction_age_s <= 0.0:
            raise ValueError("maximum prediction age must be positive")
        if not 0.0 < self.minimum_range_m < self.maximum_range_m:
            raise ValueError("target-track range gate is invalid")
        if self.maximum_angular_rate_residual_deg_s <= 0.0:
            raise ValueError("maximum angular-rate residual must be positive")
        if self.unmatched_cost <= 0.0:
            raise ValueError("unmatched cost must be positive")


@dataclass(frozen=True)
class EdgeEvidence:
    gate_passed: bool
    rejection_reasons: tuple[str, ...]
    features: tuple[float, ...]
    rule_cost: float


def _angles(samples: Sequence[SnapshotTrackSample]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    times = np.asarray([sample.timestamp for sample in samples], dtype=float)
    directions = np.asarray([sample.direction_ned for sample in samples], dtype=float)
    azimuth = np.unwrap(np.arctan2(directions[:, 1], directions[:, 0]))
    horizontal = np.hypot(directions[:, 0], directions[:, 1])
    elevation = -np.arctan2(directions[:, 2], np.maximum(horizontal, 1.0e-12))
    return times, np.degrees(azimuth), np.degrees(elevation)


def _linear_slope(times: np.ndarray, values: np.ndarray) -> float:
    if len(times) < 2 or float(np.ptp(times)) <= 1.0e-9:
        return 0.0
    centered = times - float(np.mean(times))
    denominator = float(np.dot(centered, centered))
    return float(
        np.dot(centered, values - float(np.mean(values)))
        / max(denominator, 1.0e-12)
    )


def _track_bearing_sigma_mrad(track: SnapshotTrack) -> float:
    variances = []
    for sample in track.samples:
        covariance = np.asarray(sample.measurement_covariance_deg2, dtype=float).reshape(2, 2)
        variances.extend(float(value) for value in np.diag(covariance))
    if not variances:
        return 1.0
    return max(
        math.sqrt(max(float(np.mean(variances)), 0.0)) * math.pi / 180.0 * 1000.0,
        1.0e-3,
    )


def _track_rate_sigma_deg_s(track: SnapshotTrack) -> float:
    if not track.samples:
        return 1.0
    covariance = np.asarray(track.samples[-1].state_covariance, dtype=float).reshape(4, 4)
    return max(float(np.sqrt(np.mean(np.maximum(np.diag(covariance)[2:], 0.0)))), 1.0e-3)


def _recent_hit_ratio(track: SnapshotTrack) -> float:
    return float(np.mean(np.asarray(track.recent_sweep_hits, dtype=float)))


def _track_state_quality(track: SnapshotTrack) -> float:
    return {
        "confirmed": 1.0,
        "coasting": 0.6,
        "tentative": 0.35,
        "dormant": 0.15,
        "terminated": 0.0,
    }.get(track.track_state, 0.35)


def track_features(track: SnapshotTrack) -> np.ndarray:
    samples = track.samples
    if samples:
        times, azimuth, elevation = _angles(samples)
        azimuth_rate = _linear_slope(times, azimuth)
        elevation_rate = _linear_slope(times, elevation)
        sweeps = sorted({sample.sweep_index for sample in samples})
        expected_sweeps = max(1, sweeps[-1] - sweeps[0] + 1)
        missing_ratio = 1.0 - len(sweeps) / expected_sweeps
        areas = np.asarray(
            [sample.bbox_area_px2 for sample in samples if sample.bbox_area_px2 > 0.0],
            dtype=float,
        )
        confidences = np.asarray([sample.confidence for sample in samples], dtype=float)
        area_cv = (
            float(np.std(areas) / max(float(np.mean(areas)), 1.0e-9))
            if len(areas) > 1
            else 0.0
        )
        confidence_std = float(np.std(confidences)) if len(confidences) > 1 else 0.0
        values = (
            float(len(samples)),
            float(times[-1] - times[0]) if len(times) > 1 else 0.0,
            float(len(sweeps)),
            float(np.ptp(azimuth)),
            float(np.ptp(elevation)),
            math.hypot(azimuth_rate, elevation_rate),
            float(np.clip(missing_ratio, 0.0, 1.0)),
            1.0 / (1.0 + area_cv + confidence_std),
            azimuth_rate,
            elevation_rate,
            _track_bearing_sigma_mrad(track),
            _track_rate_sigma_deg_s(track),
            _recent_hit_ratio(track),
            _track_state_quality(track),
            1.0,
        )
    else:
        values = (
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
            1.0,
            _recent_hit_ratio(track),
            _track_state_quality(track),
            1.0,
        )
    array = np.asarray(values, dtype=np.float32)
    if array.shape != (len(TRACK_FEATURE_NAMES),):
        raise AssertionError("track feature contract is inconsistent")
    return array


def target_features(
    hypothesis: TargetHypothesis,
    *,
    timestamp: float,
    revolution_index: int,
) -> np.ndarray:
    state, covariance = hypothesis.predict(timestamp)
    diagonal = np.maximum(np.diag(covariance), 0.0)
    values = (
        state[0] / 1000.0,
        state[1] / 1000.0,
        state[2] / 1000.0,
        state[3] / 100.0,
        state[4] / 100.0,
        state[5] / 100.0,
        float(np.linalg.norm(state[3:])) / 100.0,
        math.sqrt(diagonal[0]) / 100.0,
        math.sqrt(diagonal[1]) / 100.0,
        math.sqrt(diagonal[2]) / 100.0,
        math.sqrt(diagonal[3]) / 10.0,
        math.sqrt(diagonal[4]) / 10.0,
        math.sqrt(diagonal[5]) / 10.0,
        float(revolution_index - hypothesis.created_revolution_index),
        hypothesis.support_count / 10.0,
        hypothesis.fit_rms_mrad,
    )
    array = np.asarray(values, dtype=np.float32)
    if array.shape != (len(TARGET_FEATURE_NAMES),):
        raise AssertionError("target feature contract is inconsistent")
    return array


def _tangent_basis(direction: np.ndarray) -> np.ndarray:
    reference = np.asarray((0.0, 0.0, 1.0), dtype=float)
    if abs(float(np.dot(reference, direction))) > 0.95:
        reference = np.asarray((0.0, 1.0, 0.0), dtype=float)
    first = np.cross(direction, reference)
    first /= max(float(np.linalg.norm(first)), 1.0e-12)
    second = np.cross(direction, first)
    second /= max(float(np.linalg.norm(second)), 1.0e-12)
    return np.vstack((first, second))


def _sample_measurement_covariance_rad2(sample: SnapshotTrackSample) -> np.ndarray:
    covariance = np.asarray(sample.measurement_covariance_deg2, dtype=float).reshape(2, 2)
    covariance *= (math.pi / 180.0) ** 2
    covariance = 0.5 * (covariance + covariance.T)
    diagonal = np.diag(covariance)
    covariance += np.diag(np.maximum(1.0e-12 - diagonal, 0.0))
    return covariance


def _observed_angular_rate_deg_s(samples: Sequence[SnapshotTrackSample]) -> float:
    if len(samples) < 2:
        return 0.0
    first = np.asarray(samples[0].direction_ned, dtype=float)
    last = np.asarray(samples[-1].direction_ned, dtype=float)
    dt = samples[-1].timestamp - samples[0].timestamp
    if dt <= 1.0e-9:
        return 0.0
    angle = math.acos(float(np.clip(np.dot(first, last), -1.0, 1.0)))
    return math.degrees(angle) / dt


def _predicted_angular_rate_deg_s(
    hypothesis: TargetHypothesis,
    camera_position: np.ndarray,
    timestamp: float,
) -> float:
    state, _ = hypothesis.predict(timestamp)
    relative = state[:3] - camera_position
    distance = max(float(np.linalg.norm(relative)), 1.0e-9)
    direction = relative / distance
    direction_rate = (np.eye(3) - np.outer(direction, direction)) @ state[3:] / distance
    return math.degrees(float(np.linalg.norm(direction_rate)))


def target_track_evidence(
    hypothesis: TargetHypothesis,
    track: SnapshotTrack,
    camera_position_ned: Sequence[float],
    *,
    cutoff_timestamp: float,
    gate: TargetTrackGate,
) -> EdgeEvidence:
    samples = tuple(
        sample
        for sample in track.samples
        if (
            sample.timestamp
            > hypothesis.last_observation_timestamp + CAUSAL_EVIDENCE_EPSILON_S
            and sample.timestamp <= cutoff_timestamp + CAUSAL_EVIDENCE_EPSILON_S
        )
    )
    reasons: list[str] = []
    if not samples:
        reasons.append("new_evidence")
    if len(samples) < gate.minimum_track_samples:
        reasons.append("track_samples")
    camera_position = np.asarray(camera_position_ned, dtype=float)
    angular_residuals = []
    mahalanobis_values = []
    ranges = []
    transverse_sigmas = []
    usable_samples = samples[-8:]
    for sample in usable_samples:
        state, covariance = hypothesis.predict(sample.timestamp)
        relative = state[:3] - camera_position
        distance = float(np.linalg.norm(relative))
        if not gate.minimum_range_m <= distance <= gate.maximum_range_m:
            continue
        predicted = relative / distance
        measured = np.asarray(sample.direction_ned, dtype=float)
        angle = math.acos(float(np.clip(np.dot(predicted, measured), -1.0, 1.0)))
        angular_residuals.append(angle * 1000.0)
        tangent = _tangent_basis(predicted)
        residual = tangent @ (measured - predicted)
        jacobian = tangent @ (np.eye(3) - np.outer(predicted, predicted)) / distance
        residual_covariance = (
            jacobian @ covariance[:3, :3] @ jacobian.T
            + _sample_measurement_covariance_rad2(sample)
        )
        residual_covariance += np.eye(2) * 1.0e-12
        mahalanobis_values.append(
            float(residual @ np.linalg.pinv(residual_covariance) @ residual)
        )
        ranges.append(distance)
        transverse = tangent @ covariance[:3, :3] @ tangent.T
        transverse_sigmas.append(
            math.sqrt(max(float(np.trace(transverse) / 2.0), 0.0))
        )
    if not angular_residuals:
        reasons.append("range")
        angular_residuals = [1.0e6]
        mahalanobis_values = [1.0e12]
        ranges = [gate.maximum_range_m]
        transverse_sigmas = [1.0e6]
    bearing_median = float(np.median(angular_residuals))
    bearing_p90 = float(np.percentile(angular_residuals, 90))
    mahalanobis_median = float(np.median(mahalanobis_values))
    mahalanobis_p90 = float(np.percentile(mahalanobis_values, 90))
    prediction_age = max(0.0, cutoff_timestamp - hypothesis.last_observation_timestamp)
    observed_rate = _observed_angular_rate_deg_s(usable_samples)
    predicted_rate = _predicted_angular_rate_deg_s(
        hypothesis, camera_position, cutoff_timestamp
    )
    rate_residual = abs(observed_rate - predicted_rate)
    if bearing_median > gate.maximum_bearing_residual_mrad:
        reasons.append("bearing")
    if mahalanobis_median > gate.maximum_mahalanobis2:
        reasons.append("mahalanobis")
    if prediction_age > gate.maximum_prediction_age_s:
        reasons.append("prediction_age")
    if rate_residual > gate.maximum_angular_rate_residual_deg_s:
        reasons.append("angular_rate")

    bearing_sigma = _track_bearing_sigma_mrad(track)
    hit_ratio = _recent_hit_ratio(track)
    features = (
        bearing_median,
        bearing_p90,
        mahalanobis_median,
        mahalanobis_p90,
        rate_residual,
        prediction_age,
        float(np.median(ranges)) / 1000.0,
        float(np.median(transverse_sigmas)),
        bearing_sigma,
        hit_ratio,
        hypothesis.fit_rms_mrad,
        float(len(samples)),
    )
    rule_cost = (
        0.35 * min(bearing_median / gate.maximum_bearing_residual_mrad, 2.0)
        + 0.25
        * min(
            math.sqrt(max(mahalanobis_median, 0.0) / gate.maximum_mahalanobis2),
            2.0,
        )
        + 0.15 * min(rate_residual / gate.maximum_angular_rate_residual_deg_s, 2.0)
        + 0.10 * min(prediction_age / gate.maximum_prediction_age_s, 2.0)
        + 0.10 * (1.0 - hit_ratio)
        + 0.05 * min(hypothesis.fit_rms_mrad / 10.0, 2.0)
    )
    return EdgeEvidence(
        gate_passed=not reasons,
        rejection_reasons=tuple(sorted(set(reasons))),
        features=tuple(
            float(np.nan_to_num(value, nan=1.0e6, posinf=1.0e6, neginf=-1.0e6))
            for value in features
        ),
        rule_cost=float(np.clip(rule_cost, 0.0, 2.0)),
    )


def _whitelist_fingerprint(
    *,
    seed: int,
    revolution_index: int,
    camera_id: str,
    hypothesis_ids: Sequence[str],
    track_ids: Sequence[str],
    edge_index: np.ndarray,
) -> str:
    edges = [
        [hypothesis_ids[int(target)], track_ids[int(track)]]
        for target, track in edge_index.T
    ]
    return payload_fingerprint(
        {
            "schema_version": "dual-optical-target-track-gnn-v1",
            "seed": seed,
            "revolution_index": revolution_index,
            "camera_id": camera_id,
            "edges": edges,
        }
    )


def build_target_track_graph(
    snapshot: RevolutionSnapshot,
    hypotheses: Sequence[TargetHypothesis],
    camera_id: str,
    *,
    gate: TargetTrackGate | None = None,
) -> TargetTrackGraph:
    """Create the immutable whitelist graph for one camera at one revolution."""

    gate = gate or TargetTrackGate()
    assert_anonymous_snapshot(snapshot)
    if camera_id not in snapshot.camera_ids:
        raise ValueError("camera_id is not present in the revolution snapshot")
    if len({item.hypothesis_id for item in hypotheses}) != len(hypotheses):
        raise ValueError("hypothesis IDs must be unique")
    noncausal = [
        item.hypothesis_id
        for item in hypotheses
        if item.created_revolution_index >= snapshot.revolution_index
    ]
    if noncausal:
        raise CausalityError(
            "current graph contains hypotheses not created before this revolution: "
            + ",".join(noncausal)
        )
    common_evidence_start = (
        max(item.last_observation_timestamp for item in hypotheses)
        if hypotheses
        else -float("inf")
    )
    tracks = tuple(
        replace(
            track,
            samples=tuple(
                sample
                for sample in track.samples
                if (
                    sample.timestamp
                    > common_evidence_start + CAUSAL_EVIDENCE_EPSILON_S
                    and sample.timestamp
                    <= snapshot.cutoff_timestamp + CAUSAL_EVIDENCE_EPSILON_S
                )
            ),
        )
        for track in snapshot.tracks[camera_id]
        if track.track_state != "terminated"
    )
    hypothesis_ids = tuple(item.hypothesis_id for item in hypotheses)
    track_ids = tuple(item.track_id for item in tracks)
    target_nodes = (
        np.vstack(
            [
                target_features(
                    item,
                    timestamp=snapshot.cutoff_timestamp,
                    revolution_index=snapshot.revolution_index,
                )
                for item in hypotheses
            ]
        ).astype(np.float32)
        if hypotheses
        else np.empty((0, len(TARGET_FEATURE_NAMES)), dtype=np.float32)
    )
    track_nodes = (
        np.vstack([track_features(item) for item in tracks]).astype(np.float32)
        if tracks
        else np.empty((0, len(TRACK_FEATURE_NAMES)), dtype=np.float32)
    )
    edges: list[tuple[int, int]] = []
    edge_features: list[tuple[float, ...]] = []
    costs: list[float] = []
    rejected: dict[str, int] = {}
    for target_index, hypothesis in enumerate(hypotheses):
        for track_index, track in enumerate(tracks):
            evidence = target_track_evidence(
                hypothesis,
                track,
                snapshot.camera_positions_ned[camera_id],
                cutoff_timestamp=snapshot.cutoff_timestamp,
                gate=gate,
            )
            if not evidence.gate_passed:
                for reason in evidence.rejection_reasons:
                    rejected[reason] = rejected.get(reason, 0) + 1
                continue
            edges.append((target_index, track_index))
            edge_features.append(evidence.features)
            costs.append(evidence.rule_cost)
    edge_index = (
        np.asarray(edges, dtype=np.int64).T
        if edges
        else np.empty((2, 0), dtype=np.int64)
    )
    edge_values = (
        np.asarray(edge_features, dtype=np.float32)
        if edge_features
        else np.empty((0, len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    )
    whitelist_fingerprint = _whitelist_fingerprint(
        seed=snapshot.seed,
        revolution_index=snapshot.revolution_index,
        camera_id=camera_id,
        hypothesis_ids=hypothesis_ids,
        track_ids=track_ids,
        edge_index=edge_index,
    )
    graph = TargetTrackGraph(
        seed=snapshot.seed,
        revolution_index=snapshot.revolution_index,
        camera_id=camera_id,
        hypothesis_ids=hypothesis_ids,
        track_ids=track_ids,
        target_features=target_nodes,
        track_features=track_nodes,
        edge_index=edge_index,
        edge_features=edge_values,
        rule_cost=np.asarray(costs, dtype=np.float32),
        whitelist_fingerprint=whitelist_fingerprint,
        rejection_counts=dict(sorted(rejected.items())),
    )
    graph.validate()
    return graph


def build_camera_graphs(
    snapshot: RevolutionSnapshot,
    hypotheses: Sequence[TargetHypothesis],
    *,
    gate: TargetTrackGate | None = None,
) -> Mapping[str, TargetTrackGraph]:
    """Build independent A and B graphs without creating cross-camera constraints."""

    return {
        camera_id: build_target_track_graph(
            snapshot, hypotheses, camera_id, gate=gate
        )
        for camera_id in snapshot.camera_ids
    }
