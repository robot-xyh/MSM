"""Configurable abstract assignment cost model."""

from __future__ import annotations

from dataclasses import dataclass

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

        for i, track in enumerate(tracks):
            row_breakdowns: list[CostBreakdown] = []
            for j, resource in enumerate(resources):
                cost, breakdown = self.edge_cost(track, resource, timestamp)
                matrix[i, j] = cost
                row_breakdowns.append(breakdown)
            breakdown_rows.append(tuple(row_breakdowns))

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
        )

    def edge_cost(
        self,
        track: TargetTrack,
        resource: ResourceState,
        timestamp: float,
    ) -> tuple[float, CostBreakdown]:
        feasible, reason = self.is_feasible(track, resource, timestamp)
        if not feasible:
            return self.config.infeasible_penalty, {
                "window": 0.0,
                "covariance": 0.0,
                "threat": 0.0,
                "resource_state": 0.0,
                "fov": 0.0,
                "conflict": 0.0,
                "reassignment_switch_penalty": 0.0,
                "infeasible": self.config.infeasible_penalty,
                "total": self.config.infeasible_penalty,
                "reason": 0.0,
            }

        window = self.weights.window * _clamp01(track.window_cost)
        covariance = self.weights.covariance * _clamp01(track.covariance)
        threat = self.weights.threat * (1.0 - _clamp01(track.threat_score))
        resource_state = self.weights.resource_state * self.resource_state_penalty(
            resource
        )
        fov = self.weights.fov * self.fov_difficulty(track, resource)
        conflict = self.weights.conflict * self.conflict_risk(track, resource)
        total = window + covariance + threat + resource_state + fov + conflict
        return total, {
            "window": window,
            "covariance": covariance,
            "threat": threat,
            "resource_state": resource_state,
            "fov": fov,
            "conflict": conflict,
            "reassignment_switch_penalty": 0.0,
            "infeasible": 0.0,
            "total": total,
            "reason": 0.0 if reason == "feasible" else 1.0,
        }

    def is_feasible(
        self,
        track: TargetTrack,
        resource: ResourceState,
        timestamp: float,
    ) -> tuple[bool, str]:
        if not track.assignable:
            return False, "target_not_assignable"
        if resource.operator_hold:
            return False, "resource_operator_hold"
        if resource.status == "unavailable":
            return False, "resource_unavailable"
        if resource.status == "busy" and timestamp < resource.busy_until:
            return False, "resource_busy"
        pair_feasible = track.feasibility_by_resource.get(resource.resource_id, True)
        if not pair_feasible:
            return False, "pair_infeasible"
        return True, "feasible"

    def resource_state_penalty(self, resource: ResourceState) -> float:
        status_penalty = {
            "available": 0.0,
            "degraded": 0.35,
            "busy": 0.5,
            "unavailable": 1.0,
        }.get(resource.status, 0.25)
        health_penalty = 1.0 - _clamp01(resource.health_score)
        return _clamp01(status_penalty + health_penalty + resource.load_penalty)

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

    def unassigned_cost(self, track: TargetTrack) -> float:
        if not track.assignable:
            return 0.0
        threat = _clamp01(track.threat_score)
        return self.config.unassigned_base_cost * (0.5 + threat)
