"""Adapters from anonymous frozen snapshots/graphs to route-local tensors."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from .schema import (
    EDGE_FEATURE_NAMES,
    OBSERVATION_FEATURE_NAMES,
    TRACK_FEATURE_NAMES,
    TrackGraphInput,
)


_MISSING = object()


def _field(value: Any, *names: str, default: Any = _MISSING) -> Any:
    """Read only explicitly allowed anonymous fields from DTOs or mappings."""

    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    if default is _MISSING:
        raise AttributeError(f"missing required field aliases: {names}")
    return default


def _samples(track: Any) -> tuple[Any, ...]:
    values = tuple(_field(track, "samples", default=()))
    if not values:
        raise ValueError("each online track must contain at least one observation")
    timestamps = [float(_field(sample, "timestamp")) for sample in values]
    if timestamps != sorted(timestamps):
        raise ValueError("track observations must be time ordered")
    return values


def _directions(track: Any) -> np.ndarray:
    directions = np.asarray(
        [_field(sample, "direction_ned") for sample in _samples(track)], dtype=float
    )
    norms = np.linalg.norm(directions, axis=1, keepdims=True)
    if np.any(norms <= 1.0e-12):
        raise ValueError("track direction cannot be zero")
    return directions / norms


def _angles(track: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    samples = _samples(track)
    times = np.asarray([_field(sample, "timestamp") for sample in samples], dtype=float)
    directions = _directions(track)
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


def _track_motion(track: Any) -> tuple[float, float]:
    samples = _samples(track)
    state = _field(samples[-1], "state_vector", default=None)
    if state is not None and len(state) == 4 and np.all(np.isfinite(state)):
        return float(state[2]), float(state[3])
    explicit = _field(
        track,
        "angular_velocity_deg_s",
        "angular_rate_deg_s",
        default=None,
    )
    if explicit is not None and len(explicit) == 2:
        return float(explicit[0]), float(explicit[1])
    times, azimuth, elevation = _angles(track)
    return _linear_slope(times, azimuth), _linear_slope(times, elevation)


def _track_uncertainty(track: Any) -> tuple[float, float]:
    latest = _samples(track)[-1]
    state_covariance = _field(latest, "state_covariance", default=None)
    if state_covariance is not None:
        covariance = np.asarray(state_covariance, dtype=float)
        if covariance.size == 16 and np.all(np.isfinite(covariance)):
            diagonal = covariance.reshape(4, 4).diagonal()
            degrees_to_mrad = np.deg2rad(1.0) * 1000.0
            bearing_sigma = math.sqrt(max(float(np.mean(diagonal[:2])), 0.0)) * degrees_to_mrad
            rate_sigma = math.sqrt(max(float(np.mean(diagonal[2:4])), 0.0))
            return max(bearing_sigma, 1.0e-3), max(rate_sigma, 1.0e-3)
    variances = []
    for sample in _samples(track):
        covariance = _field(
            sample,
            "measurement_covariance_deg2",
            "direction_covariance_deg2",
            default=None,
        )
        if covariance is None:
            continue
        values = np.asarray(covariance, dtype=float)
        if values.size == 4:
            variances.extend(values.reshape(2, 2).diagonal())
        elif values.size == 2:
            variances.extend(values)
    if variances:
        degrees_to_mrad = np.deg2rad(1.0) * 1000.0
        return (
            max(math.sqrt(max(float(np.mean(variances)), 0.0)) * degrees_to_mrad, 1.0e-3),
            1.0,
        )
    return 1.0, 1.0


def _recent_hit_ratio(track: Any) -> float:
    explicit = _field(
        track,
        "recent_sweep_hits",
        "recent_revolution_hits",
        "recent_three_hits",
        default=None,
    )
    if explicit is not None and len(explicit):
        return float(np.mean(np.asarray(tuple(explicit)[-3:], dtype=float)))
    sweeps = {int(_field(sample, "sweep_index")) for sample in _samples(track)}
    latest = max(sweeps)
    width = min(3, latest + 1)
    return sum(index in sweeps for index in range(latest - width + 1, latest + 1)) / width


def _track_state_quality(track: Any) -> float:
    state = str(_field(track, "track_state", "state", default="legacy_v1")).lower()
    return {
        "confirmed": 1.0,
        "stable": 1.0,
        "coasting": 0.6,
        "coast": 0.6,
        "dormant": 0.2,
        "tentative": 0.35,
        "terminated": 0.0,
        "legacy_v1": 0.5,
    }.get(state, 0.5)


def observation_history(track: Any, history_length: int = 6) -> tuple[np.ndarray, int]:
    samples = _samples(track)[-history_length:]
    latest_time = float(_field(samples[-1], "timestamp"))
    rows = []
    for sample in samples:
        direction = np.asarray(_field(sample, "direction_ned"), dtype=float)
        direction /= max(float(np.linalg.norm(direction)), 1.0e-12)
        azimuth = math.atan2(float(direction[1]), float(direction[0]))
        elevation = -math.atan2(
            float(direction[2]), math.hypot(float(direction[0]), float(direction[1]))
        )
        innovation = max(
            float(_field(sample, "innovation_mahalanobis2", default=0.0)), 0.0
        )
        rows.append(
            (
                float(_field(sample, "timestamp")) - latest_time,
                float(direction[0]),
                float(direction[1]),
                float(direction[2]),
                azimuth,
                elevation,
                float(_field(sample, "confidence", default=1.0)),
                math.log1p(max(float(_field(sample, "bbox_area_px2", default=0.0)), 0.0)),
                math.log1p(max(float(_field(sample, "detection_count", default=1)), 0.0)),
                math.sqrt(innovation),
            )
        )
    output = np.zeros((history_length, len(OBSERVATION_FEATURE_NAMES)), dtype=np.float32)
    output[: len(rows)] = np.asarray(rows, dtype=np.float32)
    return output, len(rows)


def track_features(track: Any, *, snapshot_v2: bool) -> np.ndarray:
    samples = _samples(track)
    times, azimuth, elevation = _angles(track)
    sweeps = sorted({int(_field(sample, "sweep_index")) for sample in samples})
    expected_sweeps = max(1, sweeps[-1] - sweeps[0] + 1)
    missing_ratio = 1.0 - len(sweeps) / expected_sweeps
    azimuth_rate, elevation_rate = _track_motion(track)
    areas = np.asarray(
        [
            float(_field(sample, "bbox_area_px2", default=0.0))
            for sample in samples
            if float(_field(sample, "bbox_area_px2", default=0.0)) > 0.0
        ],
        dtype=float,
    )
    confidences = np.asarray(
        [float(_field(sample, "confidence", default=1.0)) for sample in samples], dtype=float
    )
    area_cv = float(np.std(areas) / max(float(np.mean(areas)), 1.0e-9)) if len(areas) > 1 else 0.0
    confidence_std = float(np.std(confidences)) if len(confidences) > 1 else 0.0
    bearing_sigma, rate_sigma = _track_uncertainty(track)
    values = np.asarray(
        (
            len(samples),
            float(times[-1] - times[0]) if len(times) > 1 else 0.0,
            len(sweeps),
            float(np.ptp(azimuth)) if len(azimuth) else 0.0,
            float(np.ptp(elevation)) if len(elevation) else 0.0,
            math.hypot(azimuth_rate, elevation_rate),
            float(np.clip(missing_ratio, 0.0, 1.0)),
            1.0 / (1.0 + area_cv + confidence_std),
            azimuth_rate,
            elevation_rate,
            bearing_sigma,
            rate_sigma,
            _recent_hit_ratio(track),
            _track_state_quality(track),
            1.0 if snapshot_v2 else 0.0,
        ),
        dtype=np.float32,
    )
    if values.shape != (len(TRACK_FEATURE_NAMES),):
        raise AssertionError("track feature contract changed unexpectedly")
    return values


def _interpolate_directions(track: Any, times: np.ndarray) -> np.ndarray:
    source_times = np.asarray(
        [_field(sample, "timestamp") for sample in _samples(track)], dtype=float
    )
    source_directions = _directions(track)
    interpolated = np.column_stack(
        [np.interp(times, source_times, source_directions[:, axis]) for axis in range(3)]
    )
    return interpolated / np.maximum(np.linalg.norm(interpolated, axis=1, keepdims=True), 1.0e-12)


def _aligned_tracks(track_a: Any, track_b: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    times_a = np.asarray([_field(sample, "timestamp") for sample in _samples(track_a)], dtype=float)
    times_b = np.asarray([_field(sample, "timestamp") for sample in _samples(track_b)], dtype=float)
    start = max(float(times_a[0]), float(times_b[0]))
    end = min(float(times_a[-1]), float(times_b[-1]))
    union_start = min(float(times_a[0]), float(times_b[0]))
    union_end = max(float(times_a[-1]), float(times_b[-1]))
    if end <= start:
        return np.empty(0), np.empty((0, 3)), np.empty((0, 3)), 0.0
    times = np.unique(
        np.concatenate(
            (
                times_a[(times_a >= start) & (times_a <= end)],
                times_b[(times_b >= start) & (times_b <= end)],
            )
        )
    )
    overlap = (end - start) / max(union_end - union_start, 1.0e-12)
    return times, _interpolate_directions(track_a, times), _interpolate_directions(track_b, times), float(overlap)


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
    reference = float(np.median(times))
    identity = np.eye(3)
    rows = []
    targets = []
    for timestamp, direction_a, direction_b in zip(times, directions_a, directions_b):
        dt = float(timestamp - reference)
        for origin, direction in ((origin_a, direction_a), (origin_b, direction_b)):
            projector = identity - np.outer(direction, direction)
            rows.append(np.hstack((projector, dt * projector)))
            targets.append(projector @ origin)
    design = np.vstack(rows)
    target = np.concatenate(targets)
    solution, _, _, singular = np.linalg.lstsq(design, target, rcond=None)
    condition = (
        float(singular[0] / singular[-1])
        if len(singular) and singular[-1] > 1.0e-12
        else 1.0e12
    )
    position, velocity = solution[:3], solution[3:]
    angular_errors = []
    ray_residuals = []
    for timestamp, direction_a, direction_b in zip(times, directions_a, directions_b):
        point = position + velocity * float(timestamp - reference)
        for origin, direction in ((origin_a, direction_a), (origin_b, direction_b)):
            relative = point - origin
            predicted = relative / max(float(np.linalg.norm(relative)), 1.0e-12)
            angle = math.acos(float(np.clip(np.dot(predicted, direction), -1.0, 1.0)))
            angular_errors.append(angle * focal_length_px)
            ray_residuals.append(float(np.linalg.norm(np.cross(relative, direction))))
    return (
        float(np.sqrt(np.mean(np.square(angular_errors)))),
        float(np.linalg.norm(velocity)),
        condition,
        float(np.sqrt(np.mean(np.square(ray_residuals)))),
    )


def pair_features(
    track_a: Any,
    track_b: Any,
    origin_a: np.ndarray,
    origin_b: np.ndarray,
    focal_length_px: float,
) -> np.ndarray:
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
    times, directions_a, directions_b, overlap = _aligned_tracks(track_a, track_b)
    if len(times):
        baseline = origin_b - origin_a
        baseline /= max(float(np.linalg.norm(baseline)), 1.0e-12)
        cross = np.cross(directions_a, directions_b)
        normalized = np.abs(cross @ baseline) / np.maximum(np.linalg.norm(cross, axis=1), 1.0e-12)
        residuals = np.arcsin(np.clip(normalized, 0.0, 1.0)) * 1000.0
        median = float(np.median(residuals))
        p90 = float(np.percentile(residuals, 90))
        mad = float(np.median(np.abs(residuals - median)))
        slope = abs(_linear_slope(times, residuals))
        intersection = float(
            np.median(
                np.degrees(
                    np.arccos(np.clip(np.sum(directions_a * directions_b, axis=1), -1.0, 1.0))
                )
            )
        )
    else:
        median = p90 = mad = slope = 1.0e6
        intersection = 0.0
    reprojection, speed, condition, ray_residual = _constant_velocity_fit(
        times, directions_a, directions_b, origin_a, origin_b, focal_length_px
    )
    motion_inconsistency = math.hypot(azimuth_rate_delta, elevation_rate_delta)
    values = np.asarray(
        (
            median,
            p90,
            mad,
            slope,
            len(times),
            overlap,
            reprojection,
            speed,
            math.log10(max(condition, 1.0)),
            intersection,
            motion_inconsistency,
            ray_residual,
            azimuth_rate_delta,
            elevation_rate_delta,
            normalized_motion,
            median / max(combined_bearing_sigma, 1.0e-6),
            combined_bearing_sigma,
            min(_recent_hit_ratio(track_a), _recent_hit_ratio(track_b)),
        ),
        dtype=np.float32,
    )
    values = np.nan_to_num(values, nan=1.0e6, posinf=1.0e6, neginf=-1.0e6)
    if values.shape != (len(EDGE_FEATURE_NAMES),):
        raise AssertionError("edge feature contract changed unexpectedly")
    return values


def _active_tracks(snapshot: Any, camera_id: str) -> tuple[Any, ...]:
    tracks_by_camera = _field(snapshot, "tracks")
    tracks = tuple(tracks_by_camera[camera_id])
    return tuple(
        track
        for track in tracks
        if str(_field(track, "track_state", default="confirmed")).lower()
        not in {"dormant", "terminated"}
        and tuple(_field(track, "samples", default=()))
    )


def _station_arrays(tracks: Sequence[Any], *, snapshot_v2: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    histories = []
    lengths = []
    features = []
    for track in tracks:
        history, length = observation_history(track)
        histories.append(history)
        lengths.append(length)
        features.append(track_features(track, snapshot_v2=snapshot_v2))
    return (
        np.stack(histories).astype(np.float32) if histories else np.empty((0, 6, len(OBSERVATION_FEATURE_NAMES)), dtype=np.float32),
        np.asarray(lengths, dtype=np.int64),
        np.stack(features).astype(np.float32) if features else np.empty((0, len(TRACK_FEATURE_NAMES)), dtype=np.float32),
    )


def adapt_snapshot(snapshot: Any) -> TrackGraphInput:
    """Adapt an online snapshot without opening or inspecting offline truth fields."""

    camera_ids = tuple(str(value) for value in _field(snapshot, "camera_ids"))
    if len(camera_ids) != 2 or camera_ids[0] == camera_ids[1]:
        raise ValueError("track SuperGlue requires exactly two stations")
    tracker_fingerprint = str(
        _field(snapshot, "tracker_fingerprint", default="legacy-unfrozen-tracker")
    )
    snapshot_v2 = tracker_fingerprint != "legacy-unfrozen-tracker"
    tracks_a = _active_tracks(snapshot, camera_ids[0])
    tracks_b = _active_tracks(snapshot, camera_ids[1])
    ids_a = tuple(str(_field(track, "track_id")) for track in tracks_a)
    ids_b = tuple(str(_field(track, "track_id")) for track in tracks_b)
    history_a, lengths_a, features_a = _station_arrays(tracks_a, snapshot_v2=snapshot_v2)
    history_b, lengths_b, features_b = _station_arrays(tracks_b, snapshot_v2=snapshot_v2)
    index_a = {track_id: index for index, track_id in enumerate(ids_a)}
    index_b = {track_id: index for index, track_id in enumerate(ids_b)}
    candidate_mask = np.zeros((len(ids_a), len(ids_b)), dtype=bool)
    edge_values = np.zeros((len(ids_a), len(ids_b), len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    positions = _field(snapshot, "camera_positions_ned")
    origin_a = np.asarray(positions[camera_ids[0]], dtype=float)
    origin_b = np.asarray(positions[camera_ids[1]], dtype=float)
    focal_length_px = float(_field(snapshot, "focal_length_px"))
    pairs = tuple(_field(snapshot, "geometry_candidate_pairs", default=()))
    for raw_pair in pairs:
        if isinstance(raw_pair, Mapping):
            track_a_id = str(_field(raw_pair, "track_a_id", "track_id_a"))
            track_b_id = str(_field(raw_pair, "track_b_id", "track_id_b"))
        else:
            track_a_id, track_b_id = (str(value) for value in raw_pair)
        if track_a_id not in index_a or track_b_id not in index_b:
            continue
        row, column = index_a[track_a_id], index_b[track_b_id]
        candidate_mask[row, column] = True
        edge_values[row, column] = pair_features(
            tracks_a[row], tracks_b[column], origin_a, origin_b, focal_length_px
        )
    result = TrackGraphInput(
        seed=int(_field(snapshot, "seed")),
        split=str(_field(snapshot, "split", default="online")),
        corruption_level=str(_field(snapshot, "corruption_level")),
        revolution_index=int(_field(snapshot, "revolution_index")),
        cutoff_timestamp=float(_field(snapshot, "cutoff_timestamp")),
        track_ids_a=ids_a,
        track_ids_b=ids_b,
        observation_history_a=history_a,
        observation_history_b=history_b,
        history_lengths_a=lengths_a,
        history_lengths_b=lengths_b,
        track_features_a=features_a,
        track_features_b=features_b,
        candidate_mask=candidate_mask,
        edge_features=edge_values,
        candidate_graph_fingerprint=str(
            _field(snapshot, "candidate_graph_fingerprint", default="")
        ),
        metadata={
            "tracker_fingerprint": tracker_fingerprint,
            "candidate_count": int(np.sum(candidate_mask)),
        },
    )
    result.validate()
    return result


def adapt_frozen_graph(graph: Any, snapshot: Any) -> TrackGraphInput:
    """Use an existing 15/18-dimensional frozen graph with snapshot histories."""

    base = adapt_snapshot(snapshot)
    graph_ids_a = tuple(str(value) for value in _field(graph, "track_ids_a"))
    graph_ids_b = tuple(str(value) for value in _field(graph, "track_ids_b"))
    base_a = {track_id: index for index, track_id in enumerate(base.track_ids_a)}
    base_b = {track_id: index for index, track_id in enumerate(base.track_ids_b)}
    if any(track_id not in base_a for track_id in graph_ids_a) or any(
        track_id not in base_b for track_id in graph_ids_b
    ):
        raise ValueError("frozen graph references a track absent from the snapshot")
    edge_index = np.asarray(_field(graph, "edge_index"), dtype=np.int64)
    sparse_features = np.asarray(_field(graph, "edge_features"), dtype=np.float32)
    if edge_index.shape != (2, sparse_features.shape[0]):
        raise ValueError("frozen graph edge arrays are inconsistent")
    candidate_mask = np.zeros((len(graph_ids_a), len(graph_ids_b)), dtype=bool)
    edge_features = np.zeros(
        (len(graph_ids_a), len(graph_ids_b), len(EDGE_FEATURE_NAMES)), dtype=np.float32
    )
    for edge, (row, column) in enumerate(edge_index.T):
        candidate_mask[int(row), int(column)] = True
        edge_features[int(row), int(column)] = sparse_features[edge]
    rows_a = [base_a[track_id] for track_id in graph_ids_a]
    rows_b = [base_b[track_id] for track_id in graph_ids_b]
    result = TrackGraphInput(
        seed=base.seed,
        split=base.split,
        corruption_level=base.corruption_level,
        revolution_index=base.revolution_index,
        cutoff_timestamp=base.cutoff_timestamp,
        track_ids_a=graph_ids_a,
        track_ids_b=graph_ids_b,
        observation_history_a=base.observation_history_a[rows_a],
        observation_history_b=base.observation_history_b[rows_b],
        history_lengths_a=base.history_lengths_a[rows_a],
        history_lengths_b=base.history_lengths_b[rows_b],
        track_features_a=np.asarray(_field(graph, "node_features_a"), dtype=np.float32),
        track_features_b=np.asarray(_field(graph, "node_features_b"), dtype=np.float32),
        candidate_mask=candidate_mask,
        edge_features=edge_features,
        input_fingerprint=base.input_fingerprint,
        candidate_graph_fingerprint=base.candidate_graph_fingerprint,
        metadata=base.metadata,
    )
    result.validate()
    return result


def adapt_shared_feature_graph(snapshot: Any) -> TrackGraphInput:
    """Reuse the baseline GNN's frozen 15/18 feature contract exactly.

    The main candidate whitelist is intentionally coarse.  Some retained
    pairs can still fail the route-level precise geometry gate, for which the
    baseline graph builder emits bounded sentinel features.  Recomputing those
    pairs locally would give SuperGlue a different input despite sharing the
    same snapshot, so the formal route adapts the baseline graph itself.
    """

    try:
        from dual_optical_100target_gnn.graph import GeometryGate
        from dual_optical_100target_gnn.online import anonymous_graph_from_snapshot
    except ImportError:
        from research_modules.independent_experiments.dual_optical_100target_gnn.graph import (  # type: ignore[no-redef]
            GeometryGate,
        )
        from research_modules.independent_experiments.dual_optical_100target_gnn.online import (  # type: ignore[no-redef]
            anonymous_graph_from_snapshot,
        )

    frozen_graph, _ = anonymous_graph_from_snapshot(snapshot, GeometryGate())
    return adapt_frozen_graph(frozen_graph, snapshot)
