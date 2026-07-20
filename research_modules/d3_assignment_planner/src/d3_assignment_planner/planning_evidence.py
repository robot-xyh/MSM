"""Local, single-frame evidence for offline D3 learning-data recording."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from .costs import CostMatrixResult
from .models import (
    Assignment,
    AssignmentPlan,
    ResourceState,
    TargetDemand,
    TargetTrack,
)


PLANNING_FRAME_EVIDENCE_SCHEMA_V1 = "d3_planning_frame_evidence_v1"
_EMPTY_MAPPING: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class PlanningFrameEvidence:
    """One anonymous, detached planning frame retained only inside a planner."""

    available: bool
    reason: str
    planning_path: str
    selection_source: str = "unavailable"
    timestamp_s: float | None = None
    plan_id: str | None = None
    plan_version: int | None = None
    previous_plan_version: int | None = None
    rule_matrix_result: CostMatrixResult | None = None
    effective_matrix_result: CostMatrixResult | None = None
    shadow_proposal_matrix: np.ndarray | None = None
    learning_mode: str = "disabled"
    learning_state: str = "unavailable"
    fallback_reason: str | None = None
    solver_name: str | None = None
    tracks: tuple[TargetTrack, ...] = ()
    resources: tuple[ResourceState, ...] = ()
    plan: AssignmentPlan | None = None
    previous_plan: AssignmentPlan | None = None
    schema_version: str = PLANNING_FRAME_EVIDENCE_SCHEMA_V1

    @property
    def rule_matrix(self) -> np.ndarray | None:
        return (
            None
            if self.rule_matrix_result is None
            else self.rule_matrix_result.matrix
        )

    @property
    def effective_matrix(self) -> np.ndarray | None:
        return (
            None
            if self.effective_matrix_result is None
            else self.effective_matrix_result.matrix
        )

    @classmethod
    def unavailable(
        cls,
        *,
        reason: str,
        planning_path: str,
    ) -> "PlanningFrameEvidence":
        return cls(
            available=False,
            reason=_required_text(reason, "reason"),
            planning_path=_required_text(planning_path, "planning_path"),
        )


def build_planning_frame_evidence(
    *,
    planning_path: str,
    selection_source: str,
    timestamp_s: float,
    rule_matrix_result: CostMatrixResult,
    effective_matrix_result: CostMatrixResult,
    tracks: Sequence[TargetTrack],
    resources: Sequence[ResourceState],
    plan: AssignmentPlan,
    previous_plan: AssignmentPlan | None,
) -> PlanningFrameEvidence:
    """Build a detached anonymous snapshot, or an explicit unavailable result."""

    path = _required_text(planning_path, "planning_path")
    source = _required_text(selection_source, "selection_source")
    timestamp = float(timestamp_s)
    if not isfinite(timestamp):
        return PlanningFrameEvidence.unavailable(
            reason="non_finite_planning_timestamp",
            planning_path=path,
        )

    track_items = tuple(tracks)
    resource_items = tuple(resources)
    consistency_reason = _frame_consistency_reason(
        rule_matrix_result=rule_matrix_result,
        effective_matrix_result=effective_matrix_result,
        tracks=track_items,
        resources=resource_items,
        plan=plan,
    )
    if consistency_reason is not None:
        return PlanningFrameEvidence.unavailable(
            reason=consistency_reason,
            planning_path=path,
        )

    learning = _learning_snapshot(
        rule_matrix_result,
        effective_matrix_result,
    )
    if learning[0] is not None:
        return PlanningFrameEvidence.unavailable(
            reason=learning[0],
            planning_path=path,
        )
    _, learning_mode, learning_state, fallback_reason, shadow_proposal = learning

    target_tokens = {
        target_id: f"target_{index:04d}"
        for index, target_id in enumerate(rule_matrix_result.target_ids)
    }
    resource_tokens = {
        resource_id: f"resource_{index:04d}"
        for index, resource_id in enumerate(rule_matrix_result.resource_ids)
    }
    anonymous_tracks = tuple(
        _anonymous_track(track, target_tokens[track.track_id])
        for track in track_items
    )
    anonymous_resources = tuple(
        _anonymous_resource(resource, resource_tokens[resource.resource_id])
        for resource in resource_items
    )
    anonymous_plan = _anonymous_plan(plan, target_tokens, resource_tokens)
    anonymous_previous = (
        None
        if previous_plan is None
        else _anonymous_plan(previous_plan, target_tokens, resource_tokens)
    )

    return PlanningFrameEvidence(
        available=True,
        reason="available",
        planning_path=path,
        selection_source=source,
        timestamp_s=timestamp,
        plan_id=str(plan.plan_id),
        plan_version=int(plan.version),
        previous_plan_version=(
            0 if previous_plan is None else int(previous_plan.version)
        ),
        rule_matrix_result=_anonymous_matrix_result(
            rule_matrix_result,
            target_tokens,
            resource_tokens,
            keep_learning_metadata=False,
        ),
        effective_matrix_result=_anonymous_matrix_result(
            effective_matrix_result,
            target_tokens,
            resource_tokens,
            keep_learning_metadata=True,
        ),
        shadow_proposal_matrix=shadow_proposal,
        learning_mode=learning_mode,
        learning_state=learning_state,
        fallback_reason=fallback_reason,
        solver_name=str(plan.solver_name),
        tracks=anonymous_tracks,
        resources=anonymous_resources,
        plan=anonymous_plan,
        previous_plan=anonymous_previous,
    )


def _frame_consistency_reason(
    *,
    rule_matrix_result: CostMatrixResult,
    effective_matrix_result: CostMatrixResult,
    tracks: tuple[TargetTrack, ...],
    resources: tuple[ResourceState, ...],
    plan: AssignmentPlan,
) -> str | None:
    target_ids = tuple(track.track_id for track in tracks)
    resource_ids = tuple(resource.resource_id for resource in resources)
    if len(set(target_ids)) != len(target_ids):
        return "duplicate_track_ids"
    if len(set(resource_ids)) != len(resource_ids):
        return "duplicate_resource_ids"
    if rule_matrix_result.target_ids != target_ids:
        return "rule_matrix_track_snapshot_mismatch"
    if rule_matrix_result.resource_ids != resource_ids:
        return "rule_matrix_resource_snapshot_mismatch"
    if effective_matrix_result.target_ids != target_ids:
        return "effective_matrix_track_snapshot_mismatch"
    if effective_matrix_result.resource_ids != resource_ids:
        return "effective_matrix_resource_snapshot_mismatch"

    shape = (len(tracks), len(resources))
    if np.asarray(rule_matrix_result.matrix).shape != shape:
        return "rule_matrix_shape_mismatch"
    if np.asarray(effective_matrix_result.matrix).shape != shape:
        return "effective_matrix_shape_mismatch"
    if np.asarray(rule_matrix_result.unassigned_costs).shape != (len(tracks),):
        return "rule_unassigned_cost_shape_mismatch"
    if np.asarray(effective_matrix_result.unassigned_costs).shape != (len(tracks),):
        return "effective_unassigned_cost_shape_mismatch"
    if plan.target_count != len(tracks) or plan.resource_count != len(resources):
        return "plan_roster_shape_mismatch"
    if any(
        assignment.target_id not in set(target_ids)
        or assignment.resource_id not in set(resource_ids)
        for assignment in plan.assignments
    ):
        return "plan_assignment_outside_input_snapshot"
    return None


def _learning_snapshot(
    rule: CostMatrixResult,
    effective: CostMatrixResult,
) -> tuple[str | None, str, str, str | None, np.ndarray | None]:
    metadata = effective.metadata
    mode = str(metadata.get("learning_mode", "disabled")).strip().lower()
    applied = bool(metadata.get("learning_applied", False))
    shadow_only = bool(metadata.get("learning_shadow_only", False))
    raw_fallback = metadata.get("learning_fallback_reason")
    fallback = None if raw_fallback is None else str(raw_fallback)
    same_matrix = np.array_equal(
        np.asarray(rule.matrix, dtype=float),
        np.asarray(effective.matrix, dtype=float),
    )

    if fallback is not None:
        if not same_matrix:
            return (
                "learning_fallback_changed_effective_matrix",
                mode,
                "unavailable",
                fallback,
                None,
            )
        return None, mode, "rule_fallback", fallback, None
    if applied:
        if mode != "assist" or shadow_only:
            return "ambiguous_assist_matrix_state", mode, "unavailable", None, None
        return None, mode, "assist_effective", None, None
    if shadow_only:
        if mode != "shadow" or not same_matrix:
            return "ambiguous_shadow_matrix_state", mode, "unavailable", None, None
        proposal = _shadow_proposal(rule, effective)
        if proposal is None:
            return "shadow_proposal_shape_mismatch", mode, "unavailable", None, None
        return None, mode, "shadow_proposal", None, proposal
    if not same_matrix:
        return "unclassified_effective_matrix_change", mode, "unavailable", None, None
    return None, mode, "rule_only", None, None


def _shadow_proposal(
    rule: CostMatrixResult,
    effective: CostMatrixResult,
) -> np.ndarray | None:
    mask = _candidate_mask(effective)
    values = np.asarray(
        effective.metadata.get("learning_shadow_proposed_costs", ()),
        dtype=float,
    ).reshape(-1)
    if values.shape != (int(np.count_nonzero(mask)),) or not np.all(
        np.isfinite(values)
    ):
        return None
    proposal = np.asarray(rule.matrix, dtype=float).copy()
    proposal[mask] = values
    return _readonly_array(proposal, dtype=float)


def _candidate_mask(result: CostMatrixResult) -> np.ndarray:
    if result.candidate_mask is not None:
        return np.asarray(result.candidate_mask, dtype=bool).reshape(result.matrix.shape)
    if result.reject_reasons:
        return np.asarray(
            [
                [reason is None for reason in row]
                for row in result.reject_reasons
            ],
            dtype=bool,
        ).reshape(result.matrix.shape)
    return np.ones(result.matrix.shape, dtype=bool)


def _anonymous_matrix_result(
    result: CostMatrixResult,
    target_tokens: Mapping[str, str],
    resource_tokens: Mapping[str, str],
    *,
    keep_learning_metadata: bool,
) -> CostMatrixResult:
    metadata = (
        _safe_learning_metadata(result.metadata)
        if keep_learning_metadata
        else MappingProxyType({})
    )
    return CostMatrixResult(
        matrix=_readonly_array(result.matrix, dtype=float),
        breakdowns=tuple(
            tuple(_safe_cost_breakdown(value) for value in row)
            for row in result.breakdowns
        ),
        target_ids=tuple(target_tokens[value] for value in result.target_ids),
        resource_ids=tuple(resource_tokens[value] for value in result.resource_ids),
        unassigned_costs=_readonly_array(result.unassigned_costs, dtype=float),
        target_threat_scores=tuple(float(value) for value in result.target_threat_scores),
        reject_reasons=tuple(
            tuple(None if value is None else str(value) for value in row)
            for row in result.reject_reasons
        ),
        candidate_mask=(
            None
            if result.candidate_mask is None
            else _readonly_array(result.candidate_mask, dtype=bool)
        ),
        metadata=metadata,
    )


def _anonymous_track(track: TargetTrack, token: str) -> TargetTrack:
    demand = track.demand
    anonymous_demand = None
    if demand is not None:
        anonymous_demand = TargetDemand(
            required_resource_count=int(demand.required_resource_count),
            primary_resource_count=int(demand.primary_resource_count),
            coordination_mode=str(demand.coordination_mode),
            arrival_window_start_s=demand.arrival_window_start_s,
            arrival_window_end_s=demand.arrival_window_end_s,
            wave_interval_s=float(demand.wave_interval_s),
            minimum_separation_s=demand.minimum_separation_s,
            terminal_authorization_scope=str(demand.terminal_authorization_scope),
            arrival_coordination_required=bool(
                demand.arrival_coordination_required
            ),
            required_capability_counts=_EMPTY_MAPPING,
            metadata=_EMPTY_MAPPING,
        )
        object.__setattr__(
            anonymous_demand,
            "required_capability_counts",
            _EMPTY_MAPPING,
        )
    return TargetTrack(
        track_id=token,
        threat_score=float(track.threat_score),
        covariance=float(track.covariance),
        window_cost=float(track.window_cost),
        assignable=bool(track.assignable),
        fov_difficulty_by_resource=_EMPTY_MAPPING,
        conflict_risk_by_resource=_EMPTY_MAPPING,
        feasibility_by_resource=_EMPTY_MAPPING,
        metadata=_EMPTY_MAPPING,
        time_window_by_resource=_EMPTY_MAPPING,
        demand=anonymous_demand,
        friendly_conflict_by_resource=_EMPTY_MAPPING,
    )


def _anonymous_resource(resource: ResourceState, token: str) -> ResourceState:
    return ResourceState(
        resource_id=token,
        status="available" if resource.status == "available" else "unavailable",
        health_score=float(resource.health_score),
        busy_until=float(resource.busy_until),
        operator_hold=bool(resource.operator_hold),
        load_penalty=float(resource.load_penalty),
        fov_difficulty=float(resource.fov_difficulty),
        conflict_risk=float(resource.conflict_risk),
        capability_class="anonymous",
        energy_fraction=float(resource.energy_fraction),
        availability_score=float(resource.availability_score),
        current_load=float(resource.current_load),
        history_failure_rate=float(resource.history_failure_rate),
        intercept_feasibility_by_target=_EMPTY_MAPPING,
        intercept_feasibility_score_by_target=_EMPTY_MAPPING,
        metadata=_EMPTY_MAPPING,
        assignment_capacity=int(resource.assignment_capacity),
    )


def _anonymous_plan(
    plan: AssignmentPlan,
    target_tokens: Mapping[str, str],
    resource_tokens: Mapping[str, str],
) -> AssignmentPlan:
    assignments = tuple(
        _anonymous_assignment(assignment, target_tokens, resource_tokens)
        for assignment in plan.assignments
        if assignment.target_id in target_tokens
        and assignment.resource_id in resource_tokens
    )
    return replace(
        plan,
        assignments=assignments,
        unassigned_target_ids=tuple(
            target_tokens[value]
            for value in plan.unassigned_target_ids
            if value in target_tokens
        ),
        incomplete_target_ids=tuple(
            target_tokens[value]
            for value in plan.incomplete_target_ids
            if value in target_tokens
        ),
        metadata=MappingProxyType({}),
        source_node_id=None,
        target_node_id=None,
        link_type=None,
        resource_count=len(resource_tokens),
        target_count=len(target_tokens),
        coalitions=(),
        demand_summaries=(),
    )


def _anonymous_assignment(
    assignment: Assignment,
    target_tokens: Mapping[str, str],
    resource_tokens: Mapping[str, str],
) -> Assignment:
    return replace(
        assignment,
        target_id=target_tokens[assignment.target_id],
        resource_id=resource_tokens[assignment.resource_id],
        cost_breakdown=_safe_cost_breakdown(assignment.cost_breakdown),
        source_node_id=None,
        target_node_id=None,
        link_type=None,
        coalition_id=None,
        metadata=MappingProxyType({}),
    )


def _safe_cost_breakdown(value: Mapping[str, Any]) -> Mapping[str, float]:
    return MappingProxyType(
        {
            str(key): float(item)
            for key, item in value.items()
            if _safe_key(key) and isinstance(item, (int, float, np.number))
        }
    )


def _safe_learning_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    allowed = {
        "learning_residual_schema",
        "learning_mode",
        "learning_formula",
        "learning_alpha",
        "learning_candidate_action_count",
        "learning_dense_action_count",
        "learning_inference_elapsed_s",
        "learning_confidence",
        "learning_applied",
        "learning_shadow_only",
        "learning_fallback_reason",
        "learning_max_abs_adjustment",
    }
    return MappingProxyType(
        {
            str(key): _safe_scalar(value)
            for key, value in metadata.items()
            if str(key) in allowed
        }
    )


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return str(type(value).__name__)


def _safe_key(value: Any) -> bool:
    key = str(value).strip().lower()
    forbidden = ("truth", "actor", "object_id", "objectid", "mesh_alias")
    return bool(key) and not any(item in key for item in forbidden)


def _readonly_array(value: Any, *, dtype: Any) -> np.ndarray:
    copied = np.ascontiguousarray(np.array(value, dtype=dtype, copy=True))
    immutable = np.frombuffer(copied.tobytes(), dtype=copied.dtype).reshape(copied.shape)
    immutable.setflags(write=False)
    return immutable


def _required_text(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result
