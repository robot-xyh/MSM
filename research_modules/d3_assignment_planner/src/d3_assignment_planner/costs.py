"""Configurable abstract assignment cost model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .models import CostBreakdown, CostWeights, PlannerConfig, ResourceState, TargetTrack


@dataclass(frozen=True)
class CostMatrixResult:
    """Cost matrix and per-edge metadata for target-resource assignment."""

    matrix: np.ndarray
    breakdowns: tuple[tuple[CostBreakdown, ...], ...]
    target_ids: tuple[str, ...]
    resource_ids: tuple[str, ...]
    unassigned_costs: np.ndarray
    target_threat_scores: tuple[float, ...] = ()
    reject_reasons: tuple[tuple[str | None, ...], ...] = ()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class CostModel:
    """Builds transparent cost matrices from normalized abstract features."""

    def __init__(
        self,
        weights: CostWeights | None = None,
        config: PlannerConfig | None = None,
    ) -> None:
        self.weights = weights or CostWeights()
        self.config = config or PlannerConfig()

    def build_matrix(
        self,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        timestamp: float,
    ) -> CostMatrixResult:
        target_ids = tuple(track.track_id for track in tracks)
        resource_ids = tuple(resource.resource_id for resource in resources)
        matrix = np.zeros((len(tracks), len(resources)), dtype=float)
        breakdown_rows: list[tuple[CostBreakdown, ...]] = []
        reject_reason_rows: list[tuple[str | None, ...]] = []

        for i, track in enumerate(tracks):
            row_breakdowns: list[CostBreakdown] = []
            row_reject_reasons: list[str | None] = []
            for j, resource in enumerate(resources):
                cost, breakdown, reject_reason = self._edge_cost_with_reason(
                    track,
                    resource,
                    timestamp,
                )
                matrix[i, j] = cost
                row_breakdowns.append(breakdown)
                row_reject_reasons.append(reject_reason)
            breakdown_rows.append(tuple(row_breakdowns))
            reject_reason_rows.append(tuple(row_reject_reasons))

        unassigned_costs = np.array(
            [self.unassigned_cost(track) for track in tracks],
            dtype=float,
        )
        return CostMatrixResult(
            matrix=matrix,
            breakdowns=tuple(breakdown_rows),
            target_ids=target_ids,
            resource_ids=resource_ids,
            unassigned_costs=unassigned_costs,
            target_threat_scores=tuple(_clamp01(track.threat_score) for track in tracks),
            reject_reasons=tuple(reject_reason_rows),
        )

    def edge_cost(
        self,
        track: TargetTrack,
        resource: ResourceState,
        timestamp: float,
    ) -> tuple[float, CostBreakdown]:
        cost, breakdown, _ = self._edge_cost_with_reason(track, resource, timestamp)
        return cost, breakdown

    def _edge_cost_with_reason(
        self,
        track: TargetTrack,
        resource: ResourceState,
        timestamp: float,
    ) -> tuple[float, CostBreakdown, str | None]:
        feasible, reason = self.is_feasible(track, resource, timestamp)
        if not feasible:
            return (
                self.config.infeasible_penalty,
                self._infeasible_breakdown(reason),
                reason,
            )

        window = self.weights.window * _clamp01(track.window_cost)
        covariance = self.weights.covariance * _clamp01(track.covariance)
        threat = self.weights.threat * (1.0 - _clamp01(track.threat_score))
        resource_components = self.resource_state_components(resource)
        resource_state = self.weights.resource_state * resource_components["total"]
        fov = self.weights.fov * self.fov_difficulty(track, resource)
        conflict = self.weights.conflict * self.conflict_risk(track, resource)
        total = window + covariance + threat + resource_state + fov + conflict
        return total, {
            "window": window,
            "covariance": covariance,
            "threat": threat,
            "resource_state": resource_state,
            "resource_status": self.weights.resource_state * resource_components["status"],
            "resource_health": self.weights.resource_state * resource_components["health"],
            "resource_load_penalty": self.weights.resource_state * resource_components["load_penalty"],
            "resource_energy": self.weights.resource_state * resource_components["energy"],
            "resource_availability": self.weights.resource_state * resource_components["availability"],
            "resource_current_load": self.weights.resource_state * resource_components["current_load"],
            "resource_history_failure": self.weights.resource_state * resource_components["history_failure"],
            "fov": fov,
            "conflict": conflict,
            "reassignment_switch_penalty": 0.0,
            "intercept_feasibility": 0.0,
            "infeasible": 0.0,
            "total": total,
            "reason": 0.0 if reason == "feasible" else 1.0,
        }, None

    def is_feasible(
        self,
        track: TargetTrack,
        resource: ResourceState,
        timestamp: float,
    ) -> tuple[bool, str]:
        if not track.assignable:
            return False, "target_not_assignable"
        window_reject_reason = self.time_window_reject_reason(
            track,
            resource,
            timestamp,
        )
        if window_reject_reason is not None:
            return False, window_reject_reason
        if resource.operator_hold:
            return False, "resource_operator_hold"
        if resource.status == "unavailable":
            return False, "resource_unavailable"
        if _clamp01(resource.availability_score) <= 0.0:
            return False, "resource_availability_zero"
        if _clamp01(resource.energy_fraction) <= 0.0:
            return False, "resource_energy_depleted"
        if resource.status == "busy" and timestamp < resource.busy_until:
            return False, "resource_busy"
        pair_feasible = track.feasibility_by_resource.get(resource.resource_id, True)
        if not pair_feasible:
            return False, "pair_infeasible"
        intercept_feasible = resource.intercept_feasibility_by_target.get(
            track.track_id,
            True,
        )
        if not intercept_feasible:
            return False, "intercept_infeasible"
        intercept_score = resource.intercept_feasibility_score_by_target.get(
            track.track_id,
            1.0,
        )
        if _clamp01(intercept_score) <= 0.0:
            return False, "intercept_infeasible"
        return True, "feasible"

    def resource_state_penalty(self, resource: ResourceState) -> float:
        return self.resource_state_components(resource)["total"]

    def resource_state_components(self, resource: ResourceState) -> dict[str, float]:
        status_penalty = {
            "available": 0.0,
            "degraded": 0.35,
            "busy": 0.5,
            "unavailable": 1.0,
        }.get(resource.status, 0.25)
        health_penalty = 1.0 - _clamp01(resource.health_score)
        load_penalty = _clamp01(resource.load_penalty)
        energy_penalty = 1.0 - _clamp01(resource.energy_fraction)
        availability_penalty = 1.0 - _clamp01(resource.availability_score)
        current_load_penalty = _clamp01(resource.current_load)
        history_failure_penalty = _clamp01(resource.history_failure_rate)
        total = _clamp01(
            status_penalty
            + health_penalty
            + load_penalty
            + energy_penalty
            + availability_penalty
            + current_load_penalty
            + history_failure_penalty
        )
        return {
            "status": _clamp01(status_penalty),
            "health": _clamp01(health_penalty),
            "load_penalty": load_penalty,
            "energy": energy_penalty,
            "availability": availability_penalty,
            "current_load": current_load_penalty,
            "history_failure": history_failure_penalty,
            "total": total,
        }

    def fov_difficulty(self, track: TargetTrack, resource: ResourceState) -> float:
        value = track.fov_difficulty_by_resource.get(
            resource.resource_id,
            resource.fov_difficulty,
        )
        return _clamp01(value)

    def conflict_risk(self, track: TargetTrack, resource: ResourceState) -> float:
        value = track.conflict_risk_by_resource.get(
            resource.resource_id,
            resource.conflict_risk,
        )
        return _clamp01(value)

    def time_window_reject_reason(
        self,
        track: TargetTrack,
        resource: ResourceState,
        timestamp: float,
    ) -> str | None:
        """Return a hard time-window reject reason when the edge is closed."""

        for metadata in _time_window_metadata_candidates(track, resource):
            reason = _time_window_reject_reason_from_metadata(metadata, timestamp)
            if reason is not None:
                return reason
        return None

    def unassigned_cost(self, track: TargetTrack) -> float:
        if not track.assignable:
            return 0.0
        threat = _clamp01(track.threat_score)
        return self.config.unassigned_base_cost * (0.5 + threat)

    def _infeasible_breakdown(self, reason: str) -> CostBreakdown:
        flags = {
            "reason_target_not_assignable": 0.0,
            "reason_resource_operator_hold": 0.0,
            "reason_resource_unavailable": 0.0,
            "reason_resource_availability": 0.0,
            "reason_resource_energy": 0.0,
            "reason_resource_busy": 0.0,
            "reason_pair_infeasible": 0.0,
            "reason_intercept_feasibility": 0.0,
            "reason_time_window_closed": 0.0,
            "reason_time_window_not_yet_open": 0.0,
        }
        reason_key = {
            "target_not_assignable": "reason_target_not_assignable",
            "resource_operator_hold": "reason_resource_operator_hold",
            "resource_unavailable": "reason_resource_unavailable",
            "resource_availability_zero": "reason_resource_availability",
            "resource_energy_depleted": "reason_resource_energy",
            "resource_busy": "reason_resource_busy",
            "pair_infeasible": "reason_pair_infeasible",
            "intercept_infeasible": "reason_intercept_feasibility",
            "time_window_closed": "reason_time_window_closed",
            "time_window_expired": "reason_time_window_closed",
            "time_window_not_yet_open": "reason_time_window_not_yet_open",
        }.get(reason)
        if reason_key is not None:
            flags[reason_key] = 1.0
        time_window_hard_reject = max(
            flags["reason_time_window_closed"],
            flags["reason_time_window_not_yet_open"],
        )
        return {
            "window": 0.0,
            "covariance": 0.0,
            "threat": 0.0,
            "resource_state": 0.0,
            "resource_status": 0.0,
            "resource_health": 0.0,
            "resource_load_penalty": 0.0,
            "resource_energy": 0.0,
            "resource_availability": 0.0,
            "resource_current_load": 0.0,
            "resource_history_failure": 0.0,
            "fov": 0.0,
            "conflict": 0.0,
            "reassignment_switch_penalty": 0.0,
            "intercept_feasibility": flags["reason_intercept_feasibility"],
            "hard_time_window_reject": time_window_hard_reject,
            "infeasible": self.config.infeasible_penalty,
            "total": self.config.infeasible_penalty,
            "reason": 1.0,
            **flags,
        }


def _time_window_metadata_candidates(
    track: TargetTrack,
    resource: ResourceState,
) -> tuple[Mapping[str, Any], ...]:
    candidates: list[Mapping[str, Any]] = []
    resource_window = track.time_window_by_resource.get(resource.resource_id)
    if resource_window is not None:
        candidate = _coerce_window_metadata(resource_window)
        if candidate:
            candidates.append(candidate)

    for key in (
        "time_window_by_resource",
        "time_windows_by_resource",
        "hard_time_window_by_resource",
    ):
        value = track.metadata.get(key)
        if not isinstance(value, Mapping):
            continue
        resource_value = value.get(resource.resource_id)
        if resource_value is None:
            continue
        candidate = _coerce_window_metadata(resource_value)
        if candidate:
            candidates.append(candidate)

    closed_by_resource = track.metadata.get("time_window_closed_by_resource")
    if (
        isinstance(closed_by_resource, Mapping)
        and resource.resource_id in closed_by_resource
    ):
        candidates.append(
            {"time_window_closed": closed_by_resource[resource.resource_id]}
        )

    direct: dict[str, Any] = {}
    if track.hard_time_window:
        direct["hard_time_window"] = True
    if track.time_window_open_at_s is not None:
        direct["time_window_open_at_s"] = track.time_window_open_at_s
    if track.time_window_close_at_s is not None:
        direct["time_window_close_at_s"] = track.time_window_close_at_s
    if track.time_window_state is not None:
        direct["time_window_state"] = track.time_window_state
    if direct:
        candidates.append(direct)

    if track.metadata:
        candidates.append(track.metadata)
    return tuple(candidates)


def _coerce_window_metadata(value: Mapping[str, Any] | bool | str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, bool):
        return {"time_window_open": value}
    text = str(value).strip()
    if text:
        return {"time_window_state": text}
    return {}


def _time_window_reject_reason_from_metadata(
    metadata: Mapping[str, Any],
    timestamp: float,
) -> str | None:
    state = _metadata_text(metadata, "time_window_state", "window_state", "state")
    if state is not None:
        normalized_state = state.lower().replace("-", "_")
        if normalized_state in {
            "closed",
            "blocked",
            "expired",
            "not_open",
            "not_yet_open",
            "outside",
            "outside_window",
        }:
            if normalized_state in {"not_open", "not_yet_open"}:
                return "time_window_not_yet_open"
            if normalized_state == "expired":
                return "time_window_expired"
            return "time_window_closed"

    closed = _metadata_bool_optional(
        metadata,
        "time_window_closed",
        "hard_time_window_closed",
        "window_closed",
        "closed",
    )
    if closed is True:
        return "time_window_closed"
    open_state = _metadata_bool_optional(
        metadata,
        "time_window_open",
        "hard_time_window_open",
        "window_open",
        "open",
    )
    if open_state is False:
        return "time_window_closed"

    hard = _metadata_bool_optional(
        metadata,
        "hard_time_window",
        "time_window_hard",
        "hard_window",
        "enforce_time_window",
    )
    if hard is not True:
        return None

    open_at = _metadata_float(
        metadata,
        "time_window_open_at_s",
        "window_open_at_s",
        "opens_at_s",
        "not_before_s",
    )
    close_at = _metadata_float(
        metadata,
        "time_window_close_at_s",
        "window_close_at_s",
        "closes_at_s",
        "deadline_s",
        "not_after_s",
    )
    if open_at is not None and float(timestamp) < open_at:
        return "time_window_not_yet_open"
    if close_at is not None and float(timestamp) > close_at:
        return "time_window_expired"
    return None


def _metadata_text(metadata: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _metadata_bool_optional(
    metadata: Mapping[str, Any],
    *keys: str,
) -> bool | None:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if "closed" in key and normalized == "closed":
                return True
            if normalized in {"1", "true", "yes", "y", "on", "open"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", "closed"}:
                return False
            continue
        if isinstance(value, (int, float)):
            return bool(value)
    return None


def _metadata_float(metadata: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None
