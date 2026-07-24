"""Synthetic AirSim-style dry-run adapter for the D3 planner.

The adapter accepts plain mappings or lightweight objects produced by offline
phase-1 fixtures. It intentionally imports no AirSim APIs and only converts
records into the abstract D3 planning models.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .models import (
    AssignmentPlan,
    ResourceState,
    TargetTrack,
    compose_threat_score_baseline,
)
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
        forced_replan: bool = False,
        publish: bool = True,
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
            forced_replan=forced_replan,
            publish=publish,
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
    identity_commitment_state, commitment_source = (
        _identity_commitment_state_from_record(record, metadata)
    )
    metadata.setdefault("identity_commitment_input_source", commitment_source)
    covariance = _covariance_quality(record)
    explicit_threat = _read(record, "threat_score", "threat", default=None)
    if explicit_threat is None:
        baseline = compose_threat_score_baseline(
            target_state=track_state,
            distance_to_critical_zone_m=_optional_float(
                _read(record, "distance_to_critical_zone_m", default=None)
            ),
            time_to_critical_zone_s=_optional_float(
                _read(record, "time_to_critical_zone_s", "ttc_s", default=None)
            ),
            speed_mps=_optional_float(_read(record, "speed_mps", "speed", default=None)),
            covariance=covariance,
            position_ned=_read(record, "position_ned", "ned_position", default=None),
            velocity_ned=_read(record, "velocity_ned", "ned_velocity", default=None),
            critical_zone_center_ned=_read(
                record,
                "critical_zone_center_ned",
                "protected_zone_center_ned",
                default=None,
            ),
            critical_zone_radius_m=_float(
                _read(record, "critical_zone_radius_m", default=0.0),
                0.0,
            ),
        )
        threat_score = baseline.threat_score
        metadata["threat_score_source"] = "d3_explainable_baseline"
        metadata["threat_score_baseline"] = {
            "components": dict(baseline.components),
            "weights": dict(baseline.weights),
            "reasons": baseline.reasons,
            **dict(baseline.metadata),
        }
    else:
        threat_score = _clamp01(_float(explicit_threat, 0.5))
        metadata.setdefault("threat_score_source", "input")

    return TargetTrack(
        track_id=track_id,
        threat_score=threat_score,
        covariance=covariance,
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
        identity_commitment_state=identity_commitment_state,
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
    availability = _availability_score(record, available)

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
        energy_fraction=_clamp01(
            _float(
                _read(
                    record,
                    "energy_fraction",
                    "energy",
                    "battery_fraction",
                    "state_of_charge",
                    default=1.0,
                ),
                1.0,
            )
        ),
        availability_score=availability,
        current_load=_clamp01(
            _float(_read(record, "current_load", "load", "load_fraction", default=0.0), 0.0)
        ),
        history_failure_rate=_clamp01(
            _float(
                _read(
                    record,
                    "history_failure_rate",
                    "historical_failure_rate",
                    "failure_rate",
                    default=0.0,
                ),
                0.0,
            )
        ),
        intercept_feasibility_by_target=_target_bool_map(
            record,
            direct_key="intercept_feasibility_by_target",
        ),
        intercept_feasibility_score_by_target=_target_float_map(
            record,
            direct_key="intercept_feasibility_score_by_target",
        ),
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


def _identity_commitment_state_from_record(
    record: Record,
    metadata: Mapping[str, Any],
) -> tuple[Any, str]:
    direct = _read(record, "identity_commitment_state", default=None)
    if direct is not None:
        return direct, "explicit_record_field"
    nested = _read(record, "identity_commitment", default=None)
    if isinstance(nested, Mapping) and nested.get("identity_commitment_state") is not None:
        return nested["identity_commitment_state"], "identity_commitment_mapping"
    metadata_state = metadata.get("identity_commitment_state")
    if metadata_state is not None:
        return metadata_state, "metadata_field"
    return None, "missing_record_field"


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _availability_score(record: Record, available: Any) -> float:
    explicit = _read(record, "availability_score", "availability", default=None)
    if explicit is not None:
        return _clamp01(_float(explicit, 1.0))
    if available is not None and not bool(available):
        return 0.0
    return 1.0


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


def _target_bool_map(record: Record, direct_key: str) -> dict[str, bool]:
    direct = _read(record, direct_key, default=None)
    if isinstance(direct, Mapping):
        return {str(target_id): bool(value) for target_id, value in direct.items()}

    result: dict[str, bool] = {}
    target_terms = _read(record, "target_terms", "track_terms", "intercept_terms", default={})
    if not isinstance(target_terms, Mapping):
        return result
    for target_id, terms in target_terms.items():
        if not isinstance(terms, Mapping):
            continue
        value = _read(
            terms,
            "intercept_feasible",
            "intercept_feasibility",
            "feasible",
            default=None,
        )
        if value is not None:
            result[str(target_id)] = bool(value)
    return result


def _target_float_map(record: Record, direct_key: str) -> dict[str, float]:
    direct = _read(record, direct_key, default=None)
    if isinstance(direct, Mapping):
        return {str(target_id): _clamp01(_float(value, 1.0)) for target_id, value in direct.items()}

    result: dict[str, float] = {}
    target_terms = _read(record, "target_terms", "track_terms", "intercept_terms", default={})
    if not isinstance(target_terms, Mapping):
        return result
    for target_id, terms in target_terms.items():
        if not isinstance(terms, Mapping):
            continue
        value = _read(
            terms,
            "intercept_feasibility_score",
            "intercept_score",
            "feasibility_score",
            default=None,
        )
        if value is not None:
            result[str(target_id)] = _clamp01(_float(value, 1.0))
    return result
