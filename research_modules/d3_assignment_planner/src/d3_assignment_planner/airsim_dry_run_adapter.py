"""Synthetic AirSim-style dry-run adapter for the D3 planner.

The adapter accepts plain mappings or lightweight objects produced by offline
phase-1 fixtures. It intentionally imports no AirSim APIs and only converts
records into the abstract D3 planning models.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .models import AssignmentPlan, ResourceState, TargetTrack
from .planner import AssignmentPlanner


Record = Mapping[str, Any] | object


class AirSimDryRunAssignmentAdapter:
    """Map synthetic AirSim-style records to D3 inputs and run the planner."""

    def __init__(self, planner: AssignmentPlanner | None = None) -> None:
        self.planner = planner or AssignmentPlanner()

    def plan(
        self,
        global_tracks: Iterable[Record | TargetTrack],
        resource_states: Iterable[Record | ResourceState],
        timestamp: float,
        previous_plan: AssignmentPlan | None = None,
        window_id: int | None = None,
        expected_previous_version: int | None = None,
    ) -> AssignmentPlan:
        """Return an `AssignmentPlan` from synthetic dry-run records."""

        tracks = adapt_airsim_global_tracks(global_tracks)
        resources = adapt_airsim_resource_states(resource_states, timestamp=timestamp)
        return self.planner.plan(
            tracks=tracks,
            resources=resources,
            timestamp=timestamp,
            previous_plan=previous_plan,
            window_id=window_id,
            expected_previous_version=expected_previous_version,
        )


def adapt_airsim_global_tracks(
    records: Iterable[Record | TargetTrack],
) -> list[TargetTrack]:
    """Convert synthetic GlobalTrack-like records into D3 `TargetTrack`s."""

    return [record if isinstance(record, TargetTrack) else _target_from_record(record) for record in records]


def adapt_airsim_resource_states(
    records: Iterable[Record | ResourceState],
    timestamp: float | None = None,
) -> list[ResourceState]:
    """Convert synthetic ResourceState-like records into D3 `ResourceState`s."""

    return [
        record
        if isinstance(record, ResourceState)
        else _resource_from_record(record, timestamp=timestamp)
        for record in records
    ]


def _target_from_record(record: Record) -> TargetTrack:
    track_id = str(_require(record, "global_track_id", "track_id", "id"))
    track_state = str(_read(record, "track_state", "state", default="confirmed")).lower()
    explicit_assignable = _read(record, "assignable", default=None)
    assignable = (
        bool(explicit_assignable)
        if explicit_assignable is not None
        else track_state not in {"lost", "dropped", "deleted"}
    )
    metadata = _metadata(record)
    metadata.setdefault("source_adapter", "airsim_dry_run")
    metadata.setdefault("track_state", track_state)

    return TargetTrack(
        track_id=track_id,
        threat_score=_clamp01(_float(_read(record, "threat_score", "threat", default=0.5), 0.5)),
        covariance=_covariance_quality(record),
        window_cost=_clamp01(_float(_read(record, "window_cost", "time_window_cost", default=0.5), 0.5)),
        assignable=assignable,
        fov_difficulty_by_resource=_pair_float_map(
            record,
            direct_key="fov_difficulty_by_resource",
            term_keys=("fov", "fov_difficulty", "vision_difficulty"),
        ),
        conflict_risk_by_resource=_pair_float_map(
            record,
            direct_key="conflict_risk_by_resource",
            term_keys=("conflict", "conflict_risk", "route_conflict"),
        ),
        feasibility_by_resource=_pair_bool_map(record),
        metadata=metadata,
    )


def _resource_from_record(record: Record, timestamp: float | None) -> ResourceState:
    resource_id = str(_require(record, "resource_id", "vehicle_name", "id"))
    busy_until = _float(_read(record, "busy_until", default=0.0), 0.0)
    status = str(_read(record, "status", default="available")).lower()
    available = _read(record, "available", default=None)
    if available is not None and not bool(available):
        status = "unavailable"
    elif status == "available" and timestamp is not None and busy_until > timestamp:
        status = "busy"

    metadata = _metadata(record)
    metadata.setdefault("source_adapter", "airsim_dry_run")

    return ResourceState(
        resource_id=resource_id,
        status=status,
        health_score=_clamp01(_float(_read(record, "health_score", "readiness", default=1.0), 1.0)),
        busy_until=busy_until,
        operator_hold=bool(_read(record, "operator_hold", "hold", default=False)),
        load_penalty=_clamp01(_float(_read(record, "load_penalty", default=0.0), 0.0)),
        fov_difficulty=_clamp01(_float(_read(record, "fov_difficulty", default=0.0), 0.0)),
        conflict_risk=_clamp01(_float(_read(record, "conflict_risk", default=0.0), 0.0)),
        capability_class=str(_read(record, "capability_class", default="generic")),
        metadata=metadata,
    )


def _read(record: Record, *keys: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        for key in keys:
            if key in record:
                return record[key]
        return default
    for key in keys:
        if hasattr(record, key):
            return getattr(record, key)
    return default


def _require(record: Record, *keys: str) -> Any:
    value = _read(record, *keys, default=None)
    if value is None:
        names = ", ".join(keys)
        raise ValueError(f"record is missing one of required fields: {names}")
    return value


def _metadata(record: Record) -> dict[str, Any]:
    value = _read(record, "metadata", default={})
    return dict(value) if isinstance(value, Mapping) else {}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _covariance_quality(record: Record) -> float:
    explicit = _read(record, "covariance", default=None)
    if isinstance(explicit, (int, float)):
        return _clamp01(float(explicit))
    if isinstance(explicit, Mapping):
        nested = _read(explicit, "normalized", "quality", "trace", default=None)
        if nested is not None:
            return _clamp01(_float(nested, 0.5))
    matrix = _read(record, "position_covariance", "covariance_matrix", default=explicit)
    trace = _matrix_trace(matrix)
    if trace is None:
        return 0.5
    trace = max(0.0, trace)
    return _clamp01(trace / (trace + 1.0))


def _matrix_trace(value: Any) -> float | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if not value:
        return 0.0
    first = value[0]
    if isinstance(first, Sequence) and not isinstance(first, (str, bytes)):
        total = 0.0
        for index, row in enumerate(value):
            if index < len(row):
                total += _float(row[index], 0.0)
        return total
    return sum(_float(item, 0.0) for item in value)


def _pair_float_map(
    record: Record,
    direct_key: str,
    term_keys: tuple[str, ...],
) -> dict[str, float]:
    direct = _read(record, direct_key, default=None)
    if isinstance(direct, Mapping):
        return {str(resource_id): _clamp01(_float(value, 0.0)) for resource_id, value in direct.items()}

    result: dict[str, float] = {}
    pair_terms = _read(record, "pair_terms", "resource_terms", default={})
    if not isinstance(pair_terms, Mapping):
        return result
    for resource_id, terms in pair_terms.items():
        if not isinstance(terms, Mapping):
            continue
        value = _read(terms, *term_keys, default=None)
        if value is not None:
            result[str(resource_id)] = _clamp01(_float(value, 0.0))
    return result


def _pair_bool_map(record: Record) -> dict[str, bool]:
    direct = _read(record, "feasibility_by_resource", default=None)
    if isinstance(direct, Mapping):
        return {str(resource_id): bool(value) for resource_id, value in direct.items()}

    result: dict[str, bool] = {}
    pair_terms = _read(record, "pair_terms", "resource_terms", default={})
    if not isinstance(pair_terms, Mapping):
        return result
    for resource_id, terms in pair_terms.items():
        if not isinstance(terms, Mapping):
            continue
        value = _read(terms, "feasible", "pair_feasible", default=None)
        if value is not None:
            result[str(resource_id)] = bool(value)
    return result
