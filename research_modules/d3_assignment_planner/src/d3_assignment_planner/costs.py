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
    def hard_safe_candidate_mask(self) -> np.ndarray:
        """Return candidate hints intersected with every hard-rejected edge."""

        matrix_shape = np.asarray(self.matrix).shape
        mask = self.candidate_mask
        if mask is None:
            mask = np.ones(matrix_shape, dtype=bool)
        else:
            mask = np.asarray(mask, dtype=bool)
            if mask.shape != matrix_shape:
                raise ValueError("candidate_mask shape must match the cost matrix")
            mask = mask.copy()
        if self.reject_reasons:
            reject_allowed = np.asarray(
                [
                    [reason is None for reason in row]
                    for row in self.reject_reasons
                ],
                dtype=bool,
            )
            if reject_allowed.shape != matrix_shape:
                raise ValueError("reject_reasons shape must match the cost matrix")
            mask &= reject_allowed
        return mask

    @property
    def candidate_edge_indices(self) -> tuple[tuple[int, int], ...]:
        """Return deterministic sparse policy/solver candidate indices."""

        mask = self.hard_safe_candidate_mask
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

        if (
            self.config.enable_candidate_sparsification
            and self.config.enable_vectorized_sparse_costs
            and self.config.max_candidate_edges_per_target is not None
        ):
            return self._build_vectorized_sparse_matrix(
                tracks,
                resources,
                timestamp,
                preserved_candidate_edges=preserved_candidate_edges or {},
            )
        return self._build_matrix_legacy(
            tracks,
            resources,
            timestamp,
            preserved_candidate_edges=preserved_candidate_edges,
        )

    def _build_matrix_legacy(
        self,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        timestamp: float,
        *,
        preserved_candidate_edges: Mapping[str, tuple[str, ...]] | None = None,
    ) -> CostMatrixResult:
        """Reference object-per-edge implementation used for regression checks."""

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
                "cost_build_path": "legacy_python_all_pairs",
                "python_full_pair_cost_evaluation_count": full_edge_count,
                "candidate_breakdown_materialization_count": full_edge_count,
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

    def _build_vectorized_sparse_matrix(
        self,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        timestamp: float,
        *,
        preserved_candidate_edges: Mapping[str, tuple[str, ...]],
    ) -> CostMatrixResult:
        """Build exact core rule costs in arrays and materialize sparse evidence.

        Pair-specific dictionaries and time-window overrides remain on the
        reference path.  This keeps their established precedence unchanged
        while removing the object-per-pair loop from the scalable 3-D profile.
        """

        self._validate_scalable_config()
        if not self._supports_vectorized_sparse_path(tracks, resources):
            legacy = self._build_matrix_legacy(
                tracks,
                resources,
                timestamp,
                preserved_candidate_edges=preserved_candidate_edges,
            )
            return CostMatrixResult(
                matrix=legacy.matrix,
                breakdowns=legacy.breakdowns,
                target_ids=legacy.target_ids,
                resource_ids=legacy.resource_ids,
                unassigned_costs=legacy.unassigned_costs,
                target_threat_scores=legacy.target_threat_scores,
                reject_reasons=legacy.reject_reasons,
                candidate_mask=legacy.candidate_mask,
                metadata={
                    **dict(legacy.metadata),
                    "cost_build_path": "legacy_complex_constraint_fallback",
                    "vectorized_sparse_fallback": True,
                },
            )

        target_count = len(tracks)
        resource_count = len(resources)
        shape = (target_count, resource_count)
        target_ids = tuple(track.track_id for track in tracks)
        resource_ids = tuple(resource.resource_id for resource in resources)
        full_edge_count = target_count * resource_count

        target_covariance = np.asarray(
            [_clamp01(track.covariance) for track in tracks],
            dtype=float,
        )
        target_covariance_trace = np.asarray(
            [
                np.nan
                if (value := _covariance_trace(track.position_covariance_ned)) is None
                else value
                for track in tracks
            ],
            dtype=float,
        )
        resource_covariance_trace = np.asarray(
            [
                np.nan
                if (value := _covariance_trace(resource.position_covariance_ned)) is None
                else value
                for resource in resources
            ],
            dtype=float,
        )
        combined_covariance = np.nan_to_num(
            target_covariance_trace[:, None], nan=0.0
        ) + np.nan_to_num(resource_covariance_trace[None, :], nan=0.0)
        covariance_score = np.maximum(
            target_covariance[:, None],
            np.clip(
                combined_covariance / self.config.covariance_trace_scale,
                0.0,
                1.0,
            ),
        )
        both_covariance_missing = (
            np.isnan(target_covariance_trace)[:, None]
            & np.isnan(resource_covariance_trace)[None, :]
        )
        covariance_score = np.where(
            both_covariance_missing,
            target_covariance[:, None],
            covariance_score,
        )

        resource_components = tuple(
            self.resource_state_components(resource) for resource in resources
        )
        resource_component_arrays = {
            key: np.asarray([item[key] for item in resource_components], dtype=float)
            for key in (
                "total",
                "status",
                "health",
                "load_penalty",
                "energy",
                "availability",
                "current_load",
                "history_failure",
            )
        }
        fov_score = np.broadcast_to(
            np.asarray([_clamp01(item.fov_difficulty) for item in resources])[None, :],
            shape,
        )
        conflict_score = np.broadcast_to(
            np.asarray([_clamp01(item.conflict_risk) for item in resources])[None, :],
            shape,
        )
        intercept_score = np.ones(shape, dtype=float)

        target_positions, target_position_valid = _vector_matrix(
            [track.position_ned for track in tracks]
        )
        target_velocities, _ = _vector_matrix(
            [track.velocity_ned for track in tracks],
            missing_as_zero=True,
        )
        resource_positions, resource_position_valid = _vector_matrix(
            [resource.position_ned for resource in resources]
        )
        resource_velocities, _ = _vector_matrix(
            [resource.velocity_ned for resource in resources],
            missing_as_zero=True,
        )
        launch_delay = np.maximum(
            0.0,
            np.asarray([float(item.busy_until) for item in resources]) - float(timestamp),
        )
        relative = (
            target_positions[:, None, :]
            + target_velocities[:, None, :] * launch_delay[None, :, None]
            - resource_positions[None, :, :]
            - resource_velocities[None, :, :] * launch_delay[None, :, None]
        )
        position_pair_valid = (
            target_position_valid[:, None] & resource_position_valid[None, :]
        )
        distance = np.full(shape, np.nan, dtype=float)
        if full_edge_count:
            distance[position_pair_valid] = np.linalg.norm(
                relative[position_pair_valid],
                axis=1,
            )

        resource_speed = np.asarray(
            [
                np.nan
                if (speed := (
                    resource.max_speed_mps
                    if resource.max_speed_mps is not None
                    else self.config.default_resource_speed_mps
                ))
                is None
                else float(speed)
                for resource in resources
            ],
            dtype=float,
        )
        intercept_time, intercept_reachable = _vectorized_intercept_time(
            relative,
            target_velocities,
            resource_speed,
            launch_delay,
            position_pair_valid,
        )
        max_range = np.asarray(
            [
                np.nan
                if resource.max_intercept_range_m is None
                else float(resource.max_intercept_range_m)
                for resource in resources
            ],
            dtype=float,
        )
        range_score = np.zeros(shape, dtype=float)
        normalizable_range = np.isfinite(max_range) & (max_range != 0.0)
        if np.any(normalizable_range):
            range_score[:, normalizable_range] = np.clip(
                distance[:, normalizable_range]
                / max_range[None, normalizable_range],
                0.0,
                1.0,
            )
            range_score[~np.isfinite(range_score)] = 0.0
        time_score = np.where(
            np.isfinite(intercept_time),
            np.clip(
                intercept_time / self.config.reachability_time_scale_s,
                0.0,
                1.0,
            ),
            0.0,
        )
        reachability_score = np.maximum.reduce(
            (time_score, range_score, 1.0 - intercept_score)
        )

        region_compatible, region_score = self._vectorized_region_terms(
            tracks,
            resources,
        )
        window_cost = np.asarray(
            [self.weights.window * _clamp01(track.window_cost) for track in tracks],
            dtype=float,
        )
        threat_cost = np.asarray(
            [
                self.weights.threat * (1.0 - _clamp01(track.threat_score))
                for track in tracks
            ],
            dtype=float,
        )
        covariance_cost = self.weights.covariance * covariance_score
        resource_cost = self.weights.resource_state * resource_component_arrays["total"]
        fov_cost = self.weights.fov * fov_score
        conflict_cost = self.weights.conflict * conflict_score
        reachability_cost = self.weights.reachability_3d * reachability_score
        region_cost = self.weights.region * region_score
        matrix = (
            window_cost[:, None]
            + covariance_cost
            + threat_cost[:, None]
            + resource_cost[None, :]
            + fov_cost
            + conflict_cost
            + reachability_cost
            + region_cost
        )

        reject_reasons = np.empty(shape, dtype=object)
        reject_reasons.fill(None)
        available = np.ones(shape, dtype=bool)

        def reject(mask: np.ndarray, reason: str) -> None:
            selected = available & np.broadcast_to(mask, shape)
            if np.any(selected):
                reject_reasons[selected] = reason
                available[selected] = False

        reject(
            ~np.asarray([bool(track.assignable) for track in tracks])[:, None],
            "target_not_assignable",
        )
        reject(
            np.asarray([bool(item.operator_hold) for item in resources])[None, :],
            "resource_operator_hold",
        )
        reject(
            np.asarray([item.status == "unavailable" for item in resources])[None, :],
            "resource_unavailable",
        )
        reject(
            np.asarray(
                [_clamp01(item.availability_score) <= 0.0 for item in resources]
            )[None, :],
            "resource_availability_zero",
        )
        reject(
            np.asarray([_clamp01(item.energy_fraction) <= 0.0 for item in resources])[
                None, :
            ],
            "resource_energy_depleted",
        )
        reject(
            np.asarray(
                [
                    item.status == "busy" and float(timestamp) < float(item.busy_until)
                    for item in resources
                ]
            )[None, :],
            "resource_busy",
        )
        reject(
            np.asarray([int(item.assignment_capacity) <= 0 for item in resources])[
                None, :
            ],
            "resource_capacity_exhausted",
        )
        reject(~region_compatible, "region_incompatible")
        reject(
            np.isfinite(distance)
            & np.isfinite(max_range)[None, :]
            & (distance > max_range[None, :]),
            "intercept_range_exceeded",
        )
        reject(intercept_reachable == 0, "intercept_unreachable_3d")
        if self.config.max_intercept_time_s is not None:
            reject(
                np.isfinite(intercept_time)
                & (intercept_time > float(self.config.max_intercept_time_s)),
                "intercept_time_exceeded",
            )

        candidate_mask = self._vectorized_candidate_mask(
            tracks=tracks,
            resources=resources,
            matrix=matrix,
            feasible_mask=available,
            preserved_candidate_edges=preserved_candidate_edges,
        )
        pruned = available & ~candidate_mask
        reject_reasons[pruned] = "candidate_pruned_sparse"
        matrix = np.asarray(matrix, dtype=float)
        matrix[~candidate_mask] = self.config.infeasible_penalty

        candidate_rows, candidate_columns = np.nonzero(candidate_mask)
        candidate_edge_count = int(len(candidate_rows))
        breakdown_array = np.empty(shape, dtype=object)
        for reason in sorted(
            {str(value) for value in reject_reasons.flat if value is not None}
        ):
            breakdown = self._infeasible_breakdown(reason)
            if reason == "candidate_pruned_sparse":
                breakdown["candidate_pruned_sparse"] = 1.0
            breakdown_array[reject_reasons == reason] = breakdown

        for target_index, resource_index in zip(candidate_rows, candidate_columns):
            total = float(matrix[target_index, resource_index])
            breakdown_array[target_index, resource_index] = {
                "window": float(window_cost[target_index]),
                "covariance": float(covariance_cost[target_index, resource_index]),
                "covariance_3d_score": float(
                    covariance_score[target_index, resource_index]
                ),
                "threat": float(threat_cost[target_index]),
                "resource_state": float(resource_cost[resource_index]),
                "resource_status": float(
                    self.weights.resource_state
                    * resource_component_arrays["status"][resource_index]
                ),
                "resource_health": float(
                    self.weights.resource_state
                    * resource_component_arrays["health"][resource_index]
                ),
                "resource_load_penalty": float(
                    self.weights.resource_state
                    * resource_component_arrays["load_penalty"][resource_index]
                ),
                "resource_energy": float(
                    self.weights.resource_state
                    * resource_component_arrays["energy"][resource_index]
                ),
                "resource_availability": float(
                    self.weights.resource_state
                    * resource_component_arrays["availability"][resource_index]
                ),
                "resource_current_load": float(
                    self.weights.resource_state
                    * resource_component_arrays["current_load"][resource_index]
                ),
                "resource_history_failure": float(
                    self.weights.resource_state
                    * resource_component_arrays["history_failure"][resource_index]
                ),
                "fov": float(fov_cost[target_index, resource_index]),
                "conflict": float(conflict_cost[target_index, resource_index]),
                "reachability_3d": float(
                    reachability_cost[target_index, resource_index]
                ),
                "reachability_3d_score": float(
                    reachability_score[target_index, resource_index]
                ),
                "intercept_time_s": (
                    -1.0
                    if not np.isfinite(intercept_time[target_index, resource_index])
                    else float(intercept_time[target_index, resource_index])
                ),
                "intercept_distance_m": (
                    -1.0
                    if not np.isfinite(distance[target_index, resource_index])
                    else float(distance[target_index, resource_index])
                ),
                "region": float(region_cost[target_index, resource_index]),
                "region_score": float(region_score[target_index, resource_index]),
                "reassignment_switch_penalty": 0.0,
                "intercept_feasibility": 0.0,
                "infeasible": 0.0,
                "total": total,
                "reason": 0.0,
            }

        breakdown_rows = tuple(
            tuple(row.tolist()) for row in breakdown_array
        )
        reject_reason_rows = tuple(
            tuple(row.tolist()) for row in reject_reasons
        )
        reason_counts = _reason_counts(reject_reasons)
        unassigned_costs = np.asarray(
            [self.unassigned_cost(track) for track in tracks],
            dtype=float,
        )
        return CostMatrixResult(
            matrix=matrix,
            breakdowns=breakdown_rows,
            target_ids=target_ids,
            resource_ids=resource_ids,
            unassigned_costs=unassigned_costs,
            target_threat_scores=tuple(
                _clamp01(track.threat_score) for track in tracks
            ),
            reject_reasons=reject_reason_rows,
            candidate_mask=candidate_mask,
            metadata={
                "candidate_graph_schema": "d3_sparse_candidate_graph_v1",
                "cost_build_path": "vectorized_sparse_candidates",
                "vectorized_sparse_fallback": False,
                "python_full_pair_cost_evaluation_count": 0,
                "vectorized_rule_pair_count": full_edge_count,
                "candidate_breakdown_materialization_count": candidate_edge_count,
                "candidate_graph_sparse": True,
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

    @staticmethod
    def _supports_vectorized_sparse_path(
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
    ) -> bool:
        """Return whether all pair-dependent rules use the core array contract."""

        for track in tracks:
            if (
                track.fov_difficulty_by_resource
                or track.conflict_risk_by_resource
                or track.feasibility_by_resource
                or track.friendly_conflict_by_resource
                or track.time_window_by_resource
                or track.hard_time_window
                or track.time_window_open_at_s is not None
                or track.time_window_close_at_s is not None
                or track.time_window_state is not None
            ):
                return False
            if any(
                key in track.metadata
                for key in (
                    "time_window_by_resource",
                    "time_windows_by_resource",
                    "hard_time_window_by_resource",
                    "time_window_closed_by_resource",
                    "time_window_state",
                    "window_state",
                    "state",
                    "time_window_closed",
                    "hard_time_window_closed",
                    "window_closed",
                    "closed",
                    "time_window_open",
                    "hard_time_window_open",
                    "window_open",
                    "open",
                    "hard_time_window",
                    "time_window_hard",
                    "hard_window",
                    "enforce_time_window",
                    "time_window_open_at_s",
                    "window_open_at_s",
                    "opens_at_s",
                    "not_before_s",
                    "time_window_close_at_s",
                    "window_close_at_s",
                    "closes_at_s",
                    "deadline_s",
                    "not_after_s",
                )
            ):
                return False
        return not any(
            resource.intercept_feasibility_by_target
            or resource.intercept_feasibility_score_by_target
            for resource in resources
        )

    def _vectorized_region_terms(
        self,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
    ) -> tuple[np.ndarray, np.ndarray]:
        target_regions = np.asarray(
            [_optional_text(track.region_id) for track in tracks],
            dtype=object,
        )
        resource_regions = np.asarray(
            [_optional_text(resource.region_id) for resource in resources],
            dtype=object,
        )
        target_missing = np.equal(target_regions, None)[:, None]
        resource_missing = np.equal(resource_regions, None)[None, :]
        same_region = target_regions[:, None] == resource_regions[None, :]
        if self.config.enforce_region_compatibility:
            compatible = target_missing | resource_missing | same_region
        else:
            compatible = np.ones(same_region.shape, dtype=bool)

        explicit_target_rows: set[int] = set()
        for target_index, track in enumerate(tracks):
            if not track.candidate_resource_region_ids:
                continue
            explicit_target_rows.add(target_index)
            compatible[target_index, :] = np.isin(
                resource_regions,
                np.asarray(
                    [str(value) for value in track.candidate_resource_region_ids],
                    dtype=object,
                ),
            )

        reachable_groups: dict[tuple[str, ...], list[int]] = {}
        for resource_index, resource in enumerate(resources):
            if resource.reachable_target_region_ids:
                key = tuple(str(value) for value in resource.reachable_target_region_ids)
                reachable_groups.setdefault(key, []).append(resource_index)
        ordinary_rows = np.asarray(
            [index not in explicit_target_rows for index in range(len(tracks))],
            dtype=bool,
        )
        ordinary_indices = np.flatnonzero(ordinary_rows)
        for region_ids, columns in reachable_groups.items():
            allowed_targets = np.isin(
                target_regions,
                np.asarray(region_ids, dtype=object),
            )
            compatible[np.ix_(ordinary_indices, np.asarray(columns, dtype=int))] = (
                allowed_targets[ordinary_indices, None]
            )

        region_score = np.where(
            target_missing | resource_missing | same_region,
            0.0,
            _clamp01(self.config.cross_region_cost),
        )
        return compatible, np.asarray(region_score, dtype=float)

    def _vectorized_candidate_mask(
        self,
        *,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        matrix: np.ndarray,
        feasible_mask: np.ndarray,
        preserved_candidate_edges: Mapping[str, tuple[str, ...]],
    ) -> np.ndarray:
        target_count, resource_count = matrix.shape
        if target_count == 0 or resource_count == 0:
            return np.zeros(matrix.shape, dtype=bool)
        configured_limit = int(self.config.max_candidate_edges_per_target or 0)
        row_limits = np.asarray(
            [
                max(configured_limit, track.effective_demand.required_resource_count)
                for track in tracks
            ],
            dtype=int,
        )
        resource_ids = np.asarray([resource.resource_id for resource in resources])
        resource_id_order = np.argsort(resource_ids, kind="stable")
        local_cost_order = np.argsort(
            matrix[:, resource_id_order],
            axis=1,
            kind="stable",
        )
        ordered_columns = resource_id_order[local_cost_order]
        row_indices = np.arange(target_count)[:, None]
        ordered_feasible = feasible_mask[row_indices, ordered_columns]
        feasible_rank = np.cumsum(ordered_feasible, axis=1)
        ordered_keep = ordered_feasible & (feasible_rank <= row_limits[:, None])
        candidate_mask = np.zeros(matrix.shape, dtype=bool)
        candidate_mask[row_indices, ordered_columns] = ordered_keep

        resource_index = {
            resource.resource_id: index for index, resource in enumerate(resources)
        }
        target_index = {track.track_id: index for index, track in enumerate(tracks)}
        for target_id, resource_id_values in preserved_candidate_edges.items():
            row = target_index.get(target_id)
            if row is None:
                continue
            for resource_id in resource_id_values:
                column = resource_index.get(resource_id)
                if column is not None and feasible_mask[row, column]:
                    candidate_mask[row, column] = True
        return candidate_mask

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


def _vector_matrix(
    values: list[Any] | tuple[Any, ...],
    *,
    missing_as_zero: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Validate NED vectors once per entity instead of once per candidate pair."""

    output = np.zeros((len(values), 3), dtype=float)
    valid = np.zeros(len(values), dtype=bool)
    for index, value in enumerate(values):
        vector = _vector3(value)
        if vector is None:
            if missing_as_zero:
                valid[index] = True
            continue
        output[index] = vector
        valid[index] = True
    return output, valid


def _vectorized_intercept_time(
    relative_position: np.ndarray,
    target_velocity: np.ndarray,
    resource_speed: np.ndarray,
    launch_delay: np.ndarray,
    position_pair_valid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized equivalent of ``_earliest_intercept_time`` for core edges.

    The reachability array uses ``1`` for reachable, ``0`` for known
    unreachable, and ``-1`` when position or speed is unavailable.  Unknown
    reachability preserves the legacy permissive behavior.
    """

    shape = position_pair_valid.shape
    intercept_after_launch = np.full(shape, np.nan, dtype=float)
    reachable = np.full(shape, -1, dtype=np.int8)
    if not shape[0] or not shape[1]:
        return intercept_after_launch, reachable

    speed = resource_speed[None, :]
    known = position_pair_valid & np.isfinite(speed)
    c = np.einsum("ijk,ijk->ij", relative_position, relative_position)
    at_target = known & (c <= 1.0e-12)
    intercept_after_launch[at_target] = 0.0
    reachable[at_target] = 1

    unresolved = known & ~at_target
    nonpositive_speed = unresolved & (speed <= 0.0)
    reachable[nonpositive_speed] = 0

    positive_speed = unresolved & (speed > 0.0)
    if np.any(positive_speed):
        target_speed_sq = np.einsum(
            "ij,ij->i",
            target_velocity,
            target_velocity,
        )[:, None]
        a = target_speed_sq - speed**2
        b = 2.0 * np.einsum(
            "ijk,ik->ij",
            relative_position,
            target_velocity,
        )
        reachable[positive_speed] = 0

        linear = positive_speed & (np.abs(a) <= 1.0e-12) & (b < 0.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            linear_time = -c / b
        valid_linear = linear & np.isfinite(linear_time) & (linear_time >= 0.0)
        intercept_after_launch[valid_linear] = linear_time[valid_linear]
        reachable[valid_linear] = 1

        quadratic = positive_speed & (np.abs(a) > 1.0e-12)
        discriminant = b * b - 4.0 * a * c
        quadratic &= discriminant >= 0.0
        root = np.sqrt(np.maximum(0.0, discriminant))
        with np.errstate(divide="ignore", invalid="ignore"):
            first = (-b - root) / (2.0 * a)
            second = (-b + root) / (2.0 * a)
        first = np.where(first >= 0.0, first, np.inf)
        second = np.where(second >= 0.0, second, np.inf)
        quadratic_time = np.minimum(first, second)
        valid_quadratic = quadratic & np.isfinite(quadratic_time)
        intercept_after_launch[valid_quadratic] = quadratic_time[valid_quadratic]
        reachable[valid_quadratic] = 1

    intercept_time = np.where(
        np.isfinite(intercept_after_launch),
        intercept_after_launch + launch_delay[None, :],
        np.nan,
    )
    return intercept_time, reachable


def _reason_counts(reject_reasons: np.ndarray) -> dict[str, int]:
    values = np.asarray(
        [str(value) for value in reject_reasons.flat if value is not None],
        dtype=object,
    )
    if values.size == 0:
        return {}
    unique, counts = np.unique(values, return_counts=True)
    return {str(reason): int(count) for reason, count in zip(unique, counts)}


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
