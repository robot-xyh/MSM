from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from .types import GlobalTrack, ReconCueSummary


DEFAULT_RECON_CUE_POSITION_VARIANCE_M2 = 10_000.0


@dataclass(frozen=True)
class _CueTrack:
    track_id: str
    position_ned: np.ndarray
    position_covariance: np.ndarray
    coverage_cell: str | None
    measurement_timestamp: float | None
    arrival_timestamp: float | None
    quality_flags: tuple[str, ...]
    used_default_covariance: bool


def summarize_recon_cue_from_tracks(
    tracks: Iterable[GlobalTrack | Mapping[str, Any]],
    *,
    coverage_cell: str | None = None,
    reference_timestamp: float | None = None,
    stale_after_s: float | None = 1.0,
    default_position_variance_m2: float = DEFAULT_RECON_CUE_POSITION_VARIANCE_M2,
    cue_metadata: Mapping[str, Any] | None = None,
) -> ReconCueSummary:
    """Build a coarse NED pointing cue from fused tracks or track-like dicts.

    The centroid is weighted by inverse position-covariance trace, so uncertain
    tracks contribute less. Missing or malformed covariance uses a conservative
    diagonal default and is counted in `default_covariance_count`.
    """

    input_tracks = list(tracks)
    requested_cell = None if coverage_cell is None else str(coverage_cell)
    metadata = {str(key): value for key, value in dict(cue_metadata or {}).items()}
    default_covariance = _default_position_covariance(default_position_variance_m2)
    cue_tracks: list[_CueTrack] = []
    aggregate_flags: set[str] = set()

    for index, track in enumerate(input_tracks):
        track_cell = _track_coverage_cell(track)
        if requested_cell is not None and track_cell != requested_cell:
            continue

        position = _track_position(track)
        if position is None:
            aggregate_flags.add("invalid_position")
            continue

        covariance, used_default = _track_position_covariance(track, default_covariance)
        flags = set(_track_quality_flags(track))
        if used_default:
            flags.add("default_covariance")

        cue_tracks.append(
            _CueTrack(
                track_id=_track_id(track, index),
                position_ned=position,
                position_covariance=covariance,
                coverage_cell=track_cell,
                measurement_timestamp=_track_measurement_timestamp(track),
                arrival_timestamp=_track_arrival_timestamp(track),
                quality_flags=tuple(sorted(flags)),
                used_default_covariance=used_default,
            )
        )
        aggregate_flags.update(flags)

    if not cue_tracks:
        empty_covariance = default_covariance.copy()
        return ReconCueSummary(
            cue_position_ned=np.zeros(3),
            cue_covariance=empty_covariance,
            covariance_trace=float(np.trace(empty_covariance)),
            active_target_ids=(),
            track_count=0,
            stale_count=0,
            total_input_count=len(input_tracks),
            excluded_count=len(input_tracks),
            default_covariance_count=0,
            coverage_cell=requested_cell,
            coverage_cells=(),
            measurement_timestamp=None,
            arrival_timestamp=None,
            quality_flags=("empty_recon_cue", *tuple(sorted(aggregate_flags))),
            metadata=metadata,
        )

    weights = np.asarray([_covariance_weight(track.position_covariance) for track in cue_tracks])
    normalized_weights = weights / float(np.sum(weights))
    positions = np.asarray([track.position_ned for track in cue_tracks], dtype=float)
    cue_position = np.sum(positions * normalized_weights[:, None], axis=0)
    cue_covariance = np.zeros((3, 3), dtype=float)
    for weight, track in zip(normalized_weights, cue_tracks):
        delta = track.position_ned - cue_position
        cue_covariance += float(weight) * (
            track.position_covariance + np.outer(delta, delta)
        )

    measurement_timestamp = _max_optional(track.measurement_timestamp for track in cue_tracks)
    arrival_timestamp = _max_optional(track.arrival_timestamp for track in cue_tracks)
    stale_reference = reference_timestamp
    if stale_reference is None:
        stale_reference = arrival_timestamp if arrival_timestamp is not None else measurement_timestamp

    coverage_cells = tuple(
        sorted({track.coverage_cell for track in cue_tracks if track.coverage_cell is not None})
    )
    summary_cell = requested_cell
    if summary_cell is None and len(coverage_cells) == 1:
        summary_cell = coverage_cells[0]

    stale_count = sum(
        1
        for track in cue_tracks
        if _is_stale(track, reference_timestamp=stale_reference, stale_after_s=stale_after_s)
    )
    default_covariance_count = sum(1 for track in cue_tracks if track.used_default_covariance)

    return ReconCueSummary(
        cue_position_ned=cue_position,
        cue_covariance=cue_covariance,
        covariance_trace=float(np.trace(cue_covariance)),
        active_target_ids=tuple(track.track_id for track in cue_tracks),
        track_count=len(cue_tracks),
        stale_count=int(stale_count),
        total_input_count=len(input_tracks),
        excluded_count=len(input_tracks) - len(cue_tracks),
        default_covariance_count=int(default_covariance_count),
        coverage_cell=summary_cell,
        coverage_cells=coverage_cells,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        quality_flags=tuple(sorted(aggregate_flags)),
        metadata=metadata,
    )


def _track_id(track: GlobalTrack | Mapping[str, Any], index: int) -> str:
    value = _track_value(track, "global_track_id")
    if value is None:
        value = _track_value(track, "track_id")
    if value is None:
        value = _track_value(track, "id")
    if value is None:
        value = _track_metadata(track).get("global_track_id")
    if value is None:
        value = f"track_{index:03d}"
    return str(value)


def _track_position(track: GlobalTrack | Mapping[str, Any]) -> np.ndarray | None:
    position = _track_value(track, "position_ned")
    if position is None:
        position = _track_value(track, "position")
    if position is None:
        position = _track_value(track, "cue_position_ned")
    if position is None:
        state = _track_value(track, "state")
        if state is not None:
            state_array = np.asarray(state, dtype=float).reshape(-1)
            if state_array.size >= 3:
                position = state_array[:3]
    return _vector3_or_none(position)


def _track_position_covariance(
    track: GlobalTrack | Mapping[str, Any],
    default_covariance: np.ndarray,
) -> tuple[np.ndarray, bool]:
    covariance = _track_value(track, "covariance")
    if covariance is None:
        covariance = _track_value(track, "cue_covariance")

    position_covariance = _position_covariance_or_none(covariance)
    if position_covariance is None:
        return default_covariance.copy(), True
    return position_covariance, False


def _position_covariance_or_none(covariance: Any) -> np.ndarray | None:
    if covariance is None:
        return None
    try:
        array = np.asarray(covariance, dtype=float)
    except (TypeError, ValueError):
        return None

    if array.ndim == 1:
        if array.size == 3:
            array = np.diag(array)
        elif array.size == 6:
            array = np.diag(array[:3])
        elif array.size == 9:
            array = array.reshape(3, 3)
        elif array.size == 36:
            array = array.reshape(6, 6)
        else:
            return None

    if array.shape == (6, 6):
        array = array[:3, :3]
    elif array.shape != (3, 3):
        return None

    if not np.isfinite(array).all():
        return None
    return np.asarray(array, dtype=float)


def _covariance_weight(covariance: np.ndarray) -> float:
    trace = float(np.trace(covariance))
    if not np.isfinite(trace) or trace <= 0.0:
        return 1.0 / DEFAULT_RECON_CUE_POSITION_VARIANCE_M2
    return 1.0 / trace


def _track_coverage_cell(track: GlobalTrack | Mapping[str, Any]) -> str | None:
    value = _track_value(track, "coverage_cell")
    if value is None:
        value = _track_metadata(track).get("coverage_cell")
    return None if value is None else str(value)


def _track_measurement_timestamp(track: GlobalTrack | Mapping[str, Any]) -> float | None:
    for key in ("measurement_timestamp", "latest_measurement_timestamp"):
        value = _track_value(track, key)
        if value is not None:
            return float(value)
        value = _track_metadata(track).get(key)
        if value is not None:
            return float(value)
    value = _track_value(track, "timestamp")
    return None if value is None else float(value)


def _track_arrival_timestamp(track: GlobalTrack | Mapping[str, Any]) -> float | None:
    for key in ("arrival_timestamp", "latest_arrival_timestamp", "published_at"):
        value = _track_value(track, key)
        if value is not None:
            return float(value)
        value = _track_metadata(track).get(key)
        if value is not None:
            return float(value)
    value = _track_value(track, "timestamp")
    return None if value is None else float(value)


def _track_quality_flags(track: GlobalTrack | Mapping[str, Any]) -> tuple[str, ...]:
    flags = _track_value(track, "quality_flags")
    if flags is None:
        flags = _track_metadata(track).get("quality_flags", ())
    if isinstance(flags, str):
        return (flags,)
    if flags is None:
        return ()
    return tuple(str(flag) for flag in flags)


def _is_stale(
    track: _CueTrack,
    *,
    reference_timestamp: float | None,
    stale_after_s: float | None,
) -> bool:
    normalized_flags = {flag.lower() for flag in track.quality_flags}
    if normalized_flags.intersection({"stale", "stale_observation", "stale_track"}):
        return True
    if stale_after_s is None or reference_timestamp is None or track.measurement_timestamp is None:
        return False
    return float(reference_timestamp) - float(track.measurement_timestamp) > float(stale_after_s)


def _track_value(track: GlobalTrack | Mapping[str, Any], key: str) -> Any:
    if isinstance(track, Mapping):
        return track.get(key)
    return getattr(track, key, None)


def _track_metadata(track: GlobalTrack | Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = _track_value(track, "metadata")
    if isinstance(metadata, Mapping):
        return metadata
    return {}


def _vector3_or_none(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    try:
        vector = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if vector.size < 3 or not np.isfinite(vector[:3]).all():
        return None
    return np.asarray(vector[:3], dtype=float)


def _default_position_covariance(default_position_variance_m2: float) -> np.ndarray:
    variance = float(default_position_variance_m2)
    if not np.isfinite(variance) or variance <= 0.0:
        raise ValueError("default_position_variance_m2 must be a positive finite value")
    return np.eye(3) * variance


def _max_optional(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return max(present)
