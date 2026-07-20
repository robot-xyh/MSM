"""Configurable abstract assignment cost model."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
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
    candidate_mask: np.ndarray | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def candidate_edge_indices(self) -> tuple[tuple[int, int], ...]:
        """Return deterministic sparse policy/solver candidate indices."""

        mask = self.candidate_mask
        if mask is None:
            if self.reject_reasons:
                mask = np.asarray(
                    [
                        [reason is None for reason in row]
                        for row in self.reject_reasons
                    ],
                    dtype=bool,
                ).reshape(self.matrix.shape)
            else:
                mask = np.ones(self.matrix.shape, dtype=bool)
        else:
            mask = np.asarray(mask, dtype=bool).reshape(self.matrix.shape)
        rows, columns = np.nonzero(mask)
        return tuple((int(row), int(column)) for row, column in zip(rows, columns))

    @property
    def candidate_edge_count(self) -> int:
        return len(self.candidate_edge_indices)


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
        *,
        preserved_candidate_edges: Mapping[str, tuple[str, ...]] | None = None,
    ) -> CostMatrixResult:
        """Build the rule matrix and its deterministic sparse candidate mask."""

        self._validate_scalable_config()
        target_ids = tuple(track.track_id for track in tracks)
        resource_ids = tuple(resource.resource_id for resource in resources)
        matrix = np.zeros((len(tracks), len(resources)), dtype=float)
        breakdown_rows: list[list[CostBreakdown]] = []
        reject_reason_rows: list[list[str | None]] = []

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
            breakdown_rows.append(row_breakdowns)
            reject_reason_rows.append(row_reject_reasons)

        self._sparsify_candidate_rows(
            tracks=tracks,
            resources=resources,
            matrix=matrix,
            breakdown_rows=breakdown_rows,
            reject_reason_rows=reject_reason_rows,
            preserved_candidate_edges=preserved_candidate_edges or {},
        )
        candidate_mask = np.asarray(
            [
                [reason is None for reason in row]
                for row in reject_reason_rows
            ],
            dtype=bool,
        ).reshape(len(tracks), len(resources))
        candidate_edge_count = int(np.count_nonzero(candidate_mask))
        full_edge_count = len(tracks) * len(resources)
        reason_counts: dict[str, int] = {}
        for row in reject_reason_rows:
            for reason in row:
                if reason is not None:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1

        unassigned_costs = np.array(
            [self.unassigned_cost(track) for track in tracks],
            dtype=float,
        )
        return CostMatrixResult(
            matrix=matrix,
            breakdowns=tuple(tuple(row) for row in breakdown_rows),
            target_ids=target_ids,
            resource_ids=resource_ids,
            unassigned_costs=unassigned_costs,
            target_threat_scores=tuple(_clamp01(track.threat_score) for track in tracks),
            reject_reasons=tuple(tuple(row) for row in reject_reason_rows),
            candidate_mask=candidate_mask,
            metadata={
                "candidate_graph_schema": "d3_sparse_candidate_graph_v1",
                "candidate_graph_sparse": bool(
                    self.config.enable_candidate_sparsification
                ),
                "candidate_edge_count": candidate_edge_count,
                "candidate_full_edge_count": full_edge_count,
                "candidate_density": (
                    0.0
                    if full_edge_count == 0
                    else candidate_edge_count / full_edge_count
                ),
                "candidate_max_edges_per_target": (
                    self.config.max_candidate_edges_per_target
                ),
                "candidate_reject_reason_counts": tuple(sorted(reason_counts.items())),
                "candidate_policy_action_count": candidate_edge_count,
                "candidate_policy_action_space": "shared_edge_residual",
            },
        )

    def _validate_scalable_config(self) -> None:
        max_edges = self.config.max_candidate_edges_per_target
        if max_edges is not None and int(max_edges) < 1:
            raise ValueError("max_candidate_edges_per_target must be positive")
        if self.config.reachability_time_scale_s <= 0.0:
            raise ValueError("reachability_time_scale_s must be positive")
        if self.config.covariance_trace_scale <= 0.0:
            raise ValueError("covariance_trace_scale must be positive")

    def _sparsify_candidate_rows(
        self,
        *,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        matrix: np.ndarray,
        breakdown_rows: list[list[CostBreakdown]],
        reject_reason_rows: list[list[str | None]],
        preserved_candidate_edges: Mapping[str, tuple[str, ...]],
    ) -> None:
        if not self.config.enable_candidate_sparsification:
            return
        configured_limit = self.config.max_candidate_edges_per_target
        if configured_limit is None:
            return
        resource_index = {
            resource.resource_id: index for index, resource in enumerate(resources)
        }
        for target_index, track in enumerate(tracks):
            feasible = [
                index
                for index, reason in enumerate(reject_reason_rows[target_index])
                if reason is None
            ]
            limit = max(int(configured_limit), track.effective_demand.required_resource_count)
            ranked = sorted(
                feasible,
                key=lambda index: (
                    float(matrix[target_index, index]),
                    resources[index].resource_id,
                ),
            )
            retained = set(ranked[:limit])
            for resource_id in preserved_candidate_edges.get(track.track_id, ()):
                index = resource_index.get(resource_id)
                if index is not None and index in feasible:
                    retained.add(index)
            for resource_index_value in feasible:
                if resource_index_value in retained:
                    continue
                reject_reason_rows[target_index][resource_index_value] = (
                    "candidate_pruned_sparse"
                )
                matrix[target_index, resource_index_value] = self.config.infeasible_penalty
                breakdown = self._infeasible_breakdown("candidate_pruned_sparse")
                breakdown["candidate_pruned_sparse"] = 1.0
                breakdown_rows[target_index][resource_index_value] = breakdown

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
        covariance_score = self.covariance_score(track, resource)
        covariance = self.weights.covariance * covariance_score
        threat = self.weights.threat * (1.0 - _clamp01(track.threat_score))
        resource_components = self.resource_state_components(resource)
        resource_state = self.weights.resource_state * resource_components["total"]
        fov = self.weights.fov * self.fov_difficulty(track, resource)
        conflict = self.weights.conflict * self.conflict_risk(track, resource)
        reachability_score, intercept_time_s, intercept_distance_m = (
            self.reachability_score(track, resource, timestamp)
        )
        reachability_3d = self.weights.reachability_3d * reachability_score
        region_score = self.region_cost(track, resource)
        region = self.weights.region * region_score
        total = (
            window
            + covariance
            + threat
            + resource_state
            + fov
            + conflict
            + reachability_3d
            + region
        )
        return total, {
            "window": window,
            "covariance": covariance,
            "covariance_3d_score": covariance_score,
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
            "reachability_3d": reachability_3d,
            "reachability_3d_score": reachability_score,
            "intercept_time_s": (
                -1.0 if intercept_time_s is None else intercept_time_s
            ),
            "intercept_distance_m": (
                -1.0 if intercept_distance_m is None else intercept_distance_m
            ),
            "region": region,
            "region_score": region_score,
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
        if int(resource.assignment_capacity) <= 0:
            return False, "resource_capacity_exhausted"
        pair_feasible = track.feasibility_by_resource.get(resource.resource_id, True)
        if not pair_feasible:
            return False, "pair_infeasible"
        if bool(track.friendly_conflict_by_resource.get(resource.resource_id, False)):
            return False, "friendly_conflict"
        if not self.region_compatible(track, resource):
            return False, "region_incompatible"
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
        reachable, reachability_reason = self.is_reachable_3d(
            track,
            resource,
            timestamp,
        )
        if not reachable:
            return False, reachability_reason
        return True, "feasible"

    def covariance_score(
        self,
        track: TargetTrack,
        resource: ResourceState,
    ) -> float:
        """Normalize scalar or NED covariance without dropping the legacy scalar."""

        covariance_trace = _covariance_trace(track.position_covariance_ned)
        resource_trace = _covariance_trace(resource.position_covariance_ned)
        if covariance_trace is None and resource_trace is None:
            return _clamp01(track.covariance)
        combined_trace = max(0.0, covariance_trace or 0.0) + max(
            0.0,
            resource_trace or 0.0,
        )
        normalized = combined_trace / self.config.covariance_trace_scale
        return max(_clamp01(track.covariance), _clamp01(normalized))

    def region_compatible(
        self,
        track: TargetTrack,
        resource: ResourceState,
    ) -> bool:
        target_region = _optional_text(track.region_id)
        resource_region = _optional_text(resource.region_id)
        allowed_resource_regions = {
            str(value) for value in track.candidate_resource_region_ids
        }
        reachable_target_regions = {
            str(value) for value in resource.reachable_target_region_ids
        }
        if allowed_resource_regions:
            return resource_region is not None and resource_region in allowed_resource_regions
        if reachable_target_regions:
            return target_region is not None and target_region in reachable_target_regions
        if (
            not self.config.enforce_region_compatibility
            or target_region is None
            or resource_region is None
        ):
            return True
        return target_region == resource_region

    def region_cost(self, track: TargetTrack, resource: ResourceState) -> float:
        target_region = _optional_text(track.region_id)
        resource_region = _optional_text(resource.region_id)
        if target_region is None or resource_region is None or target_region == resource_region:
            return 0.0
        return _clamp01(self.config.cross_region_cost)

    def is_reachable_3d(
        self,
        track: TargetTrack,
        resource: ResourceState,
        timestamp: float,
    ) -> tuple[bool, str]:
        metrics = self._intercept_metrics(track, resource, timestamp)
        distance = metrics[1]
        intercept_time = metrics[0]
        if (
            distance is not None
            and resource.max_intercept_range_m is not None
            and distance > float(resource.max_intercept_range_m)
        ):
            return False, "intercept_range_exceeded"
        if metrics[2] is False:
            return False, "intercept_unreachable_3d"
        if (
            intercept_time is not None
            and self.config.max_intercept_time_s is not None
            and intercept_time > float(self.config.max_intercept_time_s)
        ):
            return False, "intercept_time_exceeded"
        return True, "feasible"

    def reachability_score(
        self,
        track: TargetTrack,
        resource: ResourceState,
        timestamp: float,
    ) -> tuple[float, float | None, float | None]:
        intercept_time, distance, _ = self._intercept_metrics(
            track,
            resource,
            timestamp,
        )
        time_score = (
            0.0
            if intercept_time is None
            else _clamp01(intercept_time / self.config.reachability_time_scale_s)
        )
        range_score = 0.0
        if distance is not None and resource.max_intercept_range_m not in {None, 0.0}:
            range_score = _clamp01(
                distance / float(resource.max_intercept_range_m)
            )
        intercept_score = _clamp01(
            resource.intercept_feasibility_score_by_target.get(track.track_id, 1.0)
        )
        return max(time_score, range_score, 1.0 - intercept_score), intercept_time, distance

    def _intercept_metrics(
        self,
        track: TargetTrack,
        resource: ResourceState,
        timestamp: float,
    ) -> tuple[float | None, float | None, bool | None]:
        target_position = _vector3(track.position_ned)
        resource_position = _vector3(resource.position_ned)
        if target_position is None or resource_position is None:
            return None, None, None
        target_velocity = _vector3(track.velocity_ned)
        if target_velocity is None:
            target_velocity = np.zeros(3, dtype=float)
        resource_velocity = _vector3(resource.velocity_ned)
        if resource_velocity is None:
            resource_velocity = np.zeros(3, dtype=float)
        launch_delay = max(0.0, float(resource.busy_until) - float(timestamp))
        relative = (
            target_position
            + target_velocity * launch_delay
            - resource_position
            - resource_velocity * launch_delay
        )
        distance = float(np.linalg.norm(relative))
        speed = (
            resource.max_speed_mps
            if resource.max_speed_mps is not None
            else self.config.default_resource_speed_mps
        )
        if speed is None:
            return None, distance, None
        speed = float(speed)
        if speed <= 0.0:
            return (launch_delay if distance <= 1.0e-9 else None), distance, distance <= 1.0e-9
        intercept_after_launch = _earliest_intercept_time(
            relative,
            target_velocity,
            speed,
        )
        if intercept_after_launch is None:
            return None, distance, False
        return launch_delay + intercept_after_launch, distance, True

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
            "reason_resource_capacity": 0.0,
            "reason_pair_infeasible": 0.0,
            "reason_friendly_conflict": 0.0,
            "reason_region_incompatible": 0.0,
            "reason_intercept_feasibility": 0.0,
            "reason_intercept_unreachable_3d": 0.0,
            "reason_intercept_range": 0.0,
            "reason_intercept_time": 0.0,
            "reason_candidate_pruned_sparse": 0.0,
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
            "resource_capacity_exhausted": "reason_resource_capacity",
            "pair_infeasible": "reason_pair_infeasible",
            "friendly_conflict": "reason_friendly_conflict",
            "region_incompatible": "reason_region_incompatible",
            "intercept_infeasible": "reason_intercept_feasibility",
            "intercept_unreachable_3d": "reason_intercept_unreachable_3d",
            "intercept_range_exceeded": "reason_intercept_range",
            "intercept_time_exceeded": "reason_intercept_time",
            "candidate_pruned_sparse": "reason_candidate_pruned_sparse",
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
            "covariance_3d_score": 0.0,
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
            "reachability_3d": 0.0,
            "reachability_3d_score": 0.0,
            "intercept_time_s": -1.0,
            "intercept_distance_m": -1.0,
            "region": 0.0,
            "region_score": 0.0,
            "reassignment_switch_penalty": 0.0,
            "intercept_feasibility": flags["reason_intercept_feasibility"],
            "hard_time_window_reject": time_window_hard_reject,
            "infeasible": self.config.infeasible_penalty,
            "total": self.config.infeasible_penalty,
            "reason": 1.0,
            **flags,
        }


def _vector3(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    vector = np.asarray(value, dtype=float).reshape(-1)
    if vector.size != 3 or not np.all(np.isfinite(vector)):
        raise ValueError("NED position and velocity values must be finite 3-vectors")
    return vector


def _covariance_trace(value: Any) -> float | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(array)):
        raise ValueError("position covariance must contain only finite values")
    if array.ndim == 0:
        return max(0.0, float(array))
    if array.ndim == 1:
        if array.size not in {3, 6}:
            raise ValueError("position covariance diagonal must have length 3 or 6")
        return max(0.0, float(np.sum(array[:3])))
    if array.ndim == 2 and array.shape in {(3, 3), (6, 6)}:
        return max(0.0, float(np.trace(array[:3, :3])))
    raise ValueError("position covariance must be scalar, 3/6 diagonal, or 3x3/6x6")


def _earliest_intercept_time(
    relative_position: np.ndarray,
    target_velocity: np.ndarray,
    interceptor_speed: float,
) -> float | None:
    c = float(np.dot(relative_position, relative_position))
    if c <= 1.0e-12:
        return 0.0
    a = float(np.dot(target_velocity, target_velocity) - interceptor_speed**2)
    b = float(2.0 * np.dot(relative_position, target_velocity))
    if abs(a) <= 1.0e-12:
        if b >= 0.0:
            return None
        return max(0.0, -c / b)
    discriminant = b * b - 4.0 * a * c
    if discriminant < 0.0:
        return None
    root = sqrt(max(0.0, discriminant))
    roots = ((-b - root) / (2.0 * a), (-b + root) / (2.0 * a))
    positive = [value for value in roots if value >= 0.0]
    return None if not positive else min(positive)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
