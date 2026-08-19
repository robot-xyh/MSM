"""Build a geometry-gated bipartite graph from anonymous bearing tracks."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .schema import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    AnonymousTrack,
    CorruptionSummary,
    GraphLabels,
    OfflineLabels,
    OnlineEpisode,
    OnlineGraph,
)


@dataclass(frozen=True)
class GeometryGate:
    coplanarity_median_mrad: float = 0.50
    minimum_aligned_samples: int = 3
    minimum_time_overlap_ratio: float = 0.15
    maximum_reprojection_rms_px: float = 30.0
    minimum_intersection_angle_deg: float = 1.0
    maximum_condition_number: float = 1.0e8
    minimum_stable_sweeps: int = 4


@dataclass(frozen=True)
class PairEvidence:
    features: tuple[float, ...]
    geometry_cost: float
    gate_passed: bool
    rejection_reason: str


def _angles(track: AnonymousTrack) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    times = np.asarray([sample.timestamp for sample in track.samples], dtype=float)
    directions = np.asarray([sample.direction_ned for sample in track.samples], dtype=float)
    azimuth = np.unwrap(np.arctan2(directions[:, 1], directions[:, 0]))
    horizontal = np.hypot(directions[:, 0], directions[:, 1])
    elevation = -np.arctan2(directions[:, 2], np.maximum(horizontal, 1e-12))
    return times, np.degrees(azimuth), np.degrees(elevation)


def _linear_slope(times: np.ndarray, values: np.ndarray) -> float:
    if len(times) < 2 or float(np.ptp(times)) <= 1e-9:
        return 0.0
    centered = times - float(np.mean(times))
    denominator = float(np.dot(centered, centered))
    return float(np.dot(centered, values - float(np.mean(values))) / max(denominator, 1e-12))


def _track_motion(track: AnonymousTrack) -> tuple[float, float]:
    if track.angular_velocity_deg_s is not None:
        return tuple(float(value) for value in track.angular_velocity_deg_s)
    times, azimuth, elevation = _angles(track)
    return _linear_slope(times, azimuth), _linear_slope(times, elevation)


def _track_uncertainty(track: AnonymousTrack) -> tuple[float, float]:
    """Return bearing sigma in mrad and angular-rate sigma in deg/s."""

    if track.state_covariance is not None:
        covariance = np.asarray(track.state_covariance, dtype=float)
        side = 2 if covariance.size == 4 else 4
        diagonal = covariance.reshape(side, side).diagonal()
        bearing_variances = diagonal[: min(2, len(diagonal))]
        rate_variances = diagonal[2:4]
        bearing_sigma = float(np.sqrt(max(float(np.mean(bearing_variances)), 0.0)))
        rate_sigma = (
            float(np.sqrt(max(float(np.mean(rate_variances)), 0.0)))
            if len(rate_variances)
            else 1.0
        )
        return max(bearing_sigma, 1.0e-3), max(rate_sigma, 1.0e-3)
    sample_variances = []
    for sample in track.samples:
        if sample.direction_covariance_mrad2 is None:
            continue
        covariance = np.asarray(sample.direction_covariance_mrad2, dtype=float)
        diagonal = covariance if covariance.size == 2 else covariance.reshape(2, 2).diagonal()
        sample_variances.extend(float(value) for value in diagonal)
    if sample_variances:
        return max(float(np.sqrt(np.mean(sample_variances))), 1.0e-3), 1.0
    # V1 carries no covariance. The nonzero fallback keeps normalized features
    # finite; the V2 availability feature tells the model this value is imputed.
    return 1.0, 1.0


def _recent_hit_ratio(track: AnonymousTrack) -> float:
    if track.recent_revolution_hits:
        return float(np.mean(np.asarray(track.recent_revolution_hits, dtype=float)))
    if not track.samples:
        return 0.0
    last = max(sample.sweep_index for sample in track.samples)
    hits = {sample.sweep_index for sample in track.samples}
    return sum(index in hits for index in range(max(0, last - 2), last + 1)) / min(3, last + 1)


def _track_state_quality(track: AnonymousTrack) -> float:
    state = track.track_state.strip().lower()
    return {
        "confirmed": 1.0,
        "stable": 1.0,
        "coasting": 0.6,
        "coast": 0.6,
        "tentative": 0.35,
        "lost": 0.0,
        "legacy_v1": 0.5,
    }.get(state, 0.5)


def node_features(track: AnonymousTrack) -> np.ndarray:
    times, azimuth, elevation = _angles(track)
    sweep_values = sorted({sample.sweep_index for sample in track.samples})
    missing_ratio = 0.0
    if sweep_values:
        expected = max(1, sweep_values[-1] - sweep_values[0] + 1)
        missing_ratio = 1.0 - len(sweep_values) / expected
    azimuth_slope, elevation_slope = _track_motion(track)
    angular_speed = math.hypot(azimuth_slope, elevation_slope)
    areas = np.asarray(
        [sample.bbox_area_px2 for sample in track.samples if sample.bbox_area_px2 > 0.0],
        dtype=float,
    )
    confidences = np.asarray([sample.confidence for sample in track.samples], dtype=float)
    area_cv = (
        float(np.std(areas) / max(float(np.mean(areas)), 1e-9)) if len(areas) > 1 else 0.0
    )
    confidence_std = float(np.std(confidences)) if len(confidences) > 1 else 0.0
    detection_stability = 1.0 / (1.0 + area_cv + confidence_std)
    bearing_sigma, rate_sigma = _track_uncertainty(track)
    values = np.asarray(
        [
            len(track.samples),
            track.duration_s,
            track.sweep_count,
            float(np.ptp(azimuth)) if len(azimuth) else 0.0,
            float(np.ptp(elevation)) if len(elevation) else 0.0,
            angular_speed,
            float(np.clip(missing_ratio, 0.0, 1.0)),
            float(np.clip(detection_stability, 0.0, 1.0)),
            azimuth_slope,
            elevation_slope,
            bearing_sigma,
            rate_sigma,
            _recent_hit_ratio(track),
            _track_state_quality(track),
            1.0 if track.snapshot_contract_version == "v2" else 0.0,
        ],
        dtype=np.float32,
    )
    if values.shape != (len(NODE_FEATURE_NAMES),):
        raise AssertionError("node feature definition is inconsistent")
    return values


def _interpolate_directions(track: AnonymousTrack, times: np.ndarray) -> np.ndarray:
    source_times = np.asarray([sample.timestamp for sample in track.samples], dtype=float)
    source_directions = np.asarray(
        [sample.direction_ned for sample in track.samples], dtype=float
    )
    interpolated = np.column_stack(
        [np.interp(times, source_times, source_directions[:, axis]) for axis in range(3)]
    )
    norms = np.linalg.norm(interpolated, axis=1, keepdims=True)
    return interpolated / np.maximum(norms, 1e-12)


def _aligned_tracks(
    track_a: AnonymousTrack,
    track_b: AnonymousTrack,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    times_a = np.asarray([sample.timestamp for sample in track_a.samples], dtype=float)
    times_b = np.asarray([sample.timestamp for sample in track_b.samples], dtype=float)
    start = max(float(times_a[0]), float(times_b[0]))
    end = min(float(times_a[-1]), float(times_b[-1]))
    union_start = min(float(times_a[0]), float(times_b[0]))
    union_end = max(float(times_a[-1]), float(times_b[-1]))
    if end <= start:
        return np.empty(0), np.empty((0, 3)), np.empty((0, 3)), 0.0
    times = np.unique(
        np.concatenate(
            [times_a[(times_a >= start) & (times_a <= end)], times_b[(times_b >= start) & (times_b <= end)]]
        )
    )
    overlap_ratio = (end - start) / max(union_end - union_start, 1e-12)
    return (
        times,
        _interpolate_directions(track_a, times),
        _interpolate_directions(track_b, times),
        float(overlap_ratio),
    )


def _constant_velocity_fit(
    times: np.ndarray,
    directions_a: np.ndarray,
    directions_b: np.ndarray,
    origin_a: np.ndarray,
    origin_b: np.ndarray,
    focal_length_px: float,
) -> tuple[float, float, float, float]:
    if len(times) < 3:
        return 1.0e6, 0.0, 1.0e12, 1.0e6
    reference_time = float(np.median(times))
    rows = []
    targets = []
    identity = np.eye(3)
    for timestamp, direction_a, direction_b in zip(times, directions_a, directions_b):
        dt = float(timestamp - reference_time)
        for origin, direction in ((origin_a, direction_a), (origin_b, direction_b)):
            projector = identity - np.outer(direction, direction)
            rows.append(np.hstack([projector, dt * projector]))
            targets.append(projector @ origin)
    design = np.vstack(rows)
    target = np.concatenate(targets)
    solution, _, _, singular_values = np.linalg.lstsq(design, target, rcond=None)
    condition = (
        float(singular_values[0] / singular_values[-1])
        if len(singular_values) and singular_values[-1] > 1e-12
        else 1.0e12
    )
    position = solution[:3]
    velocity = solution[3:]
    angular_errors = []
    ray_residuals = []
    for timestamp, direction_a, direction_b in zip(times, directions_a, directions_b):
        point = position + velocity * float(timestamp - reference_time)
        for origin, direction in ((origin_a, direction_a), (origin_b, direction_b)):
            relative = point - origin
            distance = max(float(np.linalg.norm(relative)), 1e-12)
            predicted = relative / distance
            angle = math.acos(float(np.clip(np.dot(predicted, direction), -1.0, 1.0)))
            angular_errors.append(angle * focal_length_px)
            ray_residuals.append(float(np.linalg.norm(np.cross(relative, direction))))
    return (
        float(np.sqrt(np.mean(np.square(angular_errors)))),
        float(np.linalg.norm(velocity)),
        condition,
        float(np.sqrt(np.mean(np.square(ray_residuals)))),
    )


def pair_evidence(
    track_a: AnonymousTrack,
    track_b: AnonymousTrack,
    origin_a: np.ndarray,
    origin_b: np.ndarray,
    focal_length_px: float,
    gate: GeometryGate,
) -> PairEvidence:
    azimuth_rate_a, elevation_rate_a = _track_motion(track_a)
    azimuth_rate_b, elevation_rate_b = _track_motion(track_b)
    bearing_sigma_a, rate_sigma_a = _track_uncertainty(track_a)
    bearing_sigma_b, rate_sigma_b = _track_uncertainty(track_b)
    combined_bearing_sigma = math.hypot(bearing_sigma_a, bearing_sigma_b)
    combined_rate_sigma = math.hypot(rate_sigma_a, rate_sigma_b)
    azimuth_rate_delta = abs(azimuth_rate_a - azimuth_rate_b)
    elevation_rate_delta = abs(elevation_rate_a - elevation_rate_b)
    normalized_motion = math.hypot(
        azimuth_rate_delta / max(combined_rate_sigma, 1.0e-6),
        elevation_rate_delta / max(combined_rate_sigma, 1.0e-6),
    )
    hit_overlap = min(_recent_hit_ratio(track_a), _recent_hit_ratio(track_b))
    times, directions_a, directions_b, overlap_ratio = _aligned_tracks(track_a, track_b)
    aligned_count = len(times)
    if aligned_count:
        baseline = origin_b - origin_a
        baseline /= max(float(np.linalg.norm(baseline)), 1e-12)
        cross = np.cross(directions_a, directions_b)
        cross_norm = np.linalg.norm(cross, axis=1)
        normalized = np.abs(cross @ baseline) / np.maximum(cross_norm, 1e-12)
        residuals = np.arcsin(np.clip(normalized, 0.0, 1.0)) * 1000.0
        median = float(np.median(residuals))
        p90 = float(np.percentile(residuals, 90))
        mad = float(np.median(np.abs(residuals - median)))
        slope = abs(_linear_slope(times, residuals))
        intersections = np.degrees(
            np.arccos(np.clip(np.sum(directions_a * directions_b, axis=1), -1.0, 1.0))
        )
        intersection = float(np.median(intersections))
    else:
        median = p90 = mad = slope = 1.0e6
        intersection = 0.0

    reasons: list[str] = []
    if aligned_count < gate.minimum_aligned_samples:
        reasons.append("aligned_samples")
    if overlap_ratio < gate.minimum_time_overlap_ratio:
        reasons.append("time_overlap")
    if median > gate.coplanarity_median_mrad:
        reasons.append("coplanarity")
    if intersection < gate.minimum_intersection_angle_deg:
        reasons.append("intersection_angle")

    if reasons:
        features = (
            median,
            p90,
            mad,
            slope,
            float(aligned_count),
            overlap_ratio,
            1.0e6,
            0.0,
            12.0,
            intersection,
            1.0e6,
            1.0e6,
            azimuth_rate_delta,
            elevation_rate_delta,
            normalized_motion,
            median / max(combined_bearing_sigma, 1.0e-6),
            combined_bearing_sigma,
            hit_overlap,
        )
        return PairEvidence(
            features=features,
            geometry_cost=2.0,
            gate_passed=False,
            rejection_reason="|".join(reasons),
        )

    reprojection, speed, condition, ray_residual = _constant_velocity_fit(
        times,
        directions_a,
        directions_b,
        origin_a,
        origin_b,
        focal_length_px,
    )
    motion_inconsistency = math.hypot(azimuth_rate_delta, elevation_rate_delta)
    log_condition = math.log10(max(condition, 1.0))
    features = (
        median,
        p90,
        mad,
        slope,
        float(aligned_count),
        overlap_ratio,
        reprojection,
        speed,
        log_condition,
        intersection,
        motion_inconsistency,
        ray_residual,
        azimuth_rate_delta,
        elevation_rate_delta,
        normalized_motion,
        median / max(combined_bearing_sigma, 1.0e-6),
        combined_bearing_sigma,
        hit_overlap,
    )

    if reprojection > gate.maximum_reprojection_rms_px:
        reasons.append("reprojection")
    if condition > gate.maximum_condition_number:
        reasons.append("condition_number")

    geometry_cost = (
        0.25 * min(median / gate.coplanarity_median_mrad, 2.0)
        + 0.15 * min(p90 / max(gate.coplanarity_median_mrad * 2.0, 1e-9), 2.0)
        + 0.10 * min(mad / max(gate.coplanarity_median_mrad, 1e-9), 2.0)
        + 0.10 * min(slope / 0.25, 2.0)
        + 0.15 * min(reprojection / gate.maximum_reprojection_rms_px, 2.0)
        + 0.10 * min(motion_inconsistency / 1.0, 2.0)
        + 0.10 * (1.0 - min(overlap_ratio, 1.0))
        + 0.05 * min(max(log_condition - 2.0, 0.0) / 6.0, 2.0)
    )
    return PairEvidence(
        features=tuple(float(np.nan_to_num(value, nan=1.0e6, posinf=1.0e6, neginf=-1.0e6)) for value in features),
        geometry_cost=float(np.clip(geometry_cost, 0.0, 2.0)),
        gate_passed=not reasons,
        rejection_reason="|".join(reasons),
    )


def build_graph(
    episode: OnlineEpisode,
    labels: OfflineLabels,
    corruption_summary: CorruptionSummary,
    *,
    gate: GeometryGate | None = None,
) -> tuple[OnlineGraph, GraphLabels, dict[str, int]]:
    graph, diagnostics = build_online_graph(
        episode,
        corruption_summary,
        gate=gate,
    )
    identities_a = tuple(labels.track_identity.get(track_id) for track_id in graph.track_ids_a)
    identities_b = tuple(labels.track_identity.get(track_id) for track_id in graph.track_ids_b)
    edge_labels = np.asarray(
        [
            float(
                identities_a[index_a] is not None
                and identities_a[index_a] == identities_b[index_b]
            )
            for index_a, index_b in graph.edge_index.T
        ],
        dtype=np.float32,
    )
    graph_labels = GraphLabels(
        edge_labels=edge_labels,
        identity_a=identities_a,
        identity_b=identities_b,
        expected_identities=labels.expected_identities,
    )
    graph_labels.validate(graph)
    return (
        graph,
        graph_labels,
        {**diagnostics, "positive_candidate_edge_count": int(np.sum(edge_labels))},
    )


def build_online_graph(
    episode: OnlineEpisode,
    corruption_summary: CorruptionSummary,
    *,
    gate: GeometryGate | None = None,
) -> tuple[OnlineGraph, dict[str, int]]:
    """Build the anonymous graph without requiring or constructing identity labels."""

    gate = gate or GeometryGate()
    camera_a, camera_b = episode.camera_ids
    shared_candidate_ids_a = (
        {track_a for track_a, _ in episode.geometry_candidate_pairs}
        if episode.geometry_candidate_pairs is not None
        else None
    )
    shared_candidate_ids_b = (
        {track_b for _, track_b in episode.geometry_candidate_pairs}
        if episode.geometry_candidate_pairs is not None
        else None
    )
    tracks_a = tuple(
        track
        for track in episode.tracks[camera_a]
        if (
            track.track_id in shared_candidate_ids_a
            if shared_candidate_ids_a is not None
            else track.sweep_count >= gate.minimum_stable_sweeps
        )
    )
    tracks_b = tuple(
        track
        for track in episode.tracks[camera_b]
        if (
            track.track_id in shared_candidate_ids_b
            if shared_candidate_ids_b is not None
            else track.sweep_count >= gate.minimum_stable_sweeps
        )
    )
    nodes_a = (
        np.vstack([node_features(track) for track in tracks_a]).astype(np.float32)
        if tracks_a
        else np.empty((0, len(NODE_FEATURE_NAMES)), dtype=np.float32)
    )
    nodes_b = (
        np.vstack([node_features(track) for track in tracks_b]).astype(np.float32)
        if tracks_b
        else np.empty((0, len(NODE_FEATURE_NAMES)), dtype=np.float32)
    )
    origin_a = np.asarray(episode.camera_positions_ned[camera_a], dtype=float)
    origin_b = np.asarray(episode.camera_positions_ned[camera_b], dtype=float)
    edge_pairs: list[tuple[int, int]] = []
    edge_features: list[tuple[float, ...]] = []
    geometry_costs: list[float] = []
    rejected: dict[str, int] = {}
    evaluated = 0
    shared_candidates = episode.geometry_candidate_pairs
    track_ids_a = {track.track_id for track in tracks_a}
    track_ids_b = {track.track_id for track in tracks_b}
    unknown_shared_candidates = 0
    if shared_candidates is not None:
        unknown_shared_candidates = sum(
            track_a not in track_ids_a or track_b not in track_ids_b
            for track_a, track_b in shared_candidates
        )
    track_lookup_a = {
        track.track_id: (index, track) for index, track in enumerate(tracks_a)
    }
    track_lookup_b = {
        track.track_id: (index, track) for index, track in enumerate(tracks_b)
    }

    def evaluate_pair(index_a: int, track_a: AnonymousTrack, index_b: int, track_b: AnonymousTrack) -> None:
        nonlocal evaluated
        evaluated += 1
        evidence = pair_evidence(
            track_a,
            track_b,
            origin_a,
            origin_b,
            episode.focal_length_px,
            gate,
        )
        if not evidence.gate_passed:
            for reason in evidence.rejection_reason.split("|"):
                rejected[reason] = rejected.get(reason, 0) + 1
            if shared_candidates is None:
                return
        edge_pairs.append((index_a, index_b))
        edge_features.append(evidence.features)
        geometry_costs.append(evidence.geometry_cost)

    if shared_candidates is not None:
        # Main has already reduced the all-to-all space. Preserve its exact
        # anonymous whitelist and run precise evidence only for those edges.
        for track_a_id, track_b_id in shared_candidates:
            value_a = track_lookup_a.get(track_a_id)
            value_b = track_lookup_b.get(track_b_id)
            if value_a is None or value_b is None:
                continue
            index_a, track_a = value_a
            index_b, track_b = value_b
            evaluate_pair(index_a, track_a, index_b, track_b)
    else:
        for index_a, track_a in enumerate(tracks_a):
            for index_b, track_b in enumerate(tracks_b):
                evaluate_pair(index_a, track_a, index_b, track_b)

    edge_index = (
        np.asarray(edge_pairs, dtype=np.int64).T
        if edge_pairs
        else np.empty((2, 0), dtype=np.int64)
    )
    features = (
        np.asarray(edge_features, dtype=np.float32)
        if edge_features
        else np.empty((0, len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    )
    graph = OnlineGraph(
        seed=episode.seed,
        corruption_level=corruption_summary.level,
        camera_ids=episode.camera_ids,
        track_ids_a=tuple(track.track_id for track in tracks_a),
        track_ids_b=tuple(track.track_id for track in tracks_b),
        node_features_a=nodes_a,
        node_features_b=nodes_b,
        edge_index=edge_index,
        edge_features=features,
        geometry_cost=np.asarray(geometry_costs, dtype=np.float32),
        corruption_summary=corruption_summary,
    )
    graph.validate()
    diagnostics = {
        "full_pair_count": len(tracks_a) * len(tracks_b),
        "evaluated_pair_count": evaluated,
        "candidate_edge_count": len(edge_pairs),
        "main_geometry_candidate_count": (
            len(shared_candidates) if shared_candidates is not None else -1
        ),
        "main_geometry_unknown_track_pair_count": unknown_shared_candidates,
        "route_precise_fit_pair_count": evaluated,
        "route_avoided_full_pair_count": (
            max(0, len(tracks_a) * len(tracks_b) - evaluated)
            if shared_candidates is not None
            else 0
        ),
        "candidate_graph_fingerprint": episode.candidate_graph_fingerprint or "",
        "geometry_candidate_source": (
            "main_snapshot_allowlist_v2"
            if shared_candidates is not None
            else "frozen_route_gate_v1_fallback"
        ),
        **{f"rejected_{key}": value for key, value in sorted(rejected.items())},
    }
    return graph, diagnostics
