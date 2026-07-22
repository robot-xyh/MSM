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
    CoalitionPlan,
    DemandSatisfactionSummary,
    ResourceState,
    TargetDemand,
    TargetTrack,
)
from .runtime_plan_ack import (
    canonical_runtime_payload_sha256,
    validated_assignment_plan_payload_sha256,
)


PLANNING_FRAME_EVIDENCE_SCHEMA_V1 = "d3_planning_frame_evidence_v1"
_EMPTY_MAPPING: Mapping[str, Any] = MappingProxyType({})

_PLAN_REPLAY_METADATA_KEYS = frozenset(
    {
        "plan_schema",
        "plan_owner",
        "active_plan_owner",
        "owner_node_id",
        "current_plan_owner",
        "current_plan_owner_node_id",
        "secondary_takeover_state",
        "secondary_plan_executable",
        "secondary_activated_at_s",
        "secondary_lease_expires_at_s",
        "secondary_leader_epoch",
        "activation_state",
        "activation_at_s",
        "executable",
        "hysteresis_change_window_id",
        "hysteresis_window_changes_used",
    }
)
_PLAN_REPLAY_NODE_KEYS = frozenset(
    {"owner_node_id", "current_plan_owner_node_id"}
)
_ASSIGNMENT_REPLAY_METADATA_KEYS = frozenset(
    {
        "coordination_mode",
        "primary_resource_count",
        "minimum_separation_s",
        "terminal_authorization_scope",
        "arrival_coordination_required",
        "required_capability_class",
        "plan_owner",
        "active_plan_owner",
        "owner_node_id",
        "secondary_takeover_state",
        "secondary_plan_executable",
        "secondary_activated_at_s",
        "secondary_lease_expires_at_s",
        "secondary_leader_epoch",
        "activation_state",
        "activation_at_s",
        "executable",
        "regional_owner_layer",
        "regional_region_id",
        "regional_epoch",
        "regional_lease_expires_at_s",
        "regional_commit_state",
        "regional_commit_required",
        "regional_commit_mode",
        "regional_commit_evidence_present",
    }
)
_COALITION_REPLAY_METADATA_KEYS = frozenset(
    {
        "demand_template",
        "membership_changed_at_s",
    }
)


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
    recorded_authority_transition_sha256: str | None = None
    forced_replan: bool = False
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
    forced_replan: bool = False,
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
    prior_target_ids = _plan_target_ids(previous_plan) - set(target_tokens)
    target_tokens.update(
        {
            target_id: f"previous_target_{index:04d}"
            for index, target_id in enumerate(sorted(prior_target_ids))
        }
    )
    resource_tokens = {
        resource_id: f"resource_{index:04d}"
        for index, resource_id in enumerate(rule_matrix_result.resource_ids)
    }
    prior_resource_ids = _plan_resource_ids(previous_plan) - set(resource_tokens)
    resource_tokens.update(
        {
            resource_id: f"previous_resource_{index:04d}"
            for index, resource_id in enumerate(sorted(prior_resource_ids))
        }
    )
    coalition_tokens = {
        coalition_id: f"coalition_{index:04d}"
        for index, coalition_id in enumerate(
            sorted(_plan_coalition_ids(plan) | _plan_coalition_ids(previous_plan))
        )
    }
    node_tokens = {
        node_id: f"node_{index:04d}"
        for index, node_id in enumerate(
            sorted(
                _plan_node_ids(plan, resource_tokens)
                | _plan_node_ids(previous_plan, resource_tokens)
            )
        )
    }
    anonymous_tracks = tuple(
        _anonymous_track(track, target_tokens[track.track_id])
        for track in track_items
    )
    anonymous_resources = tuple(
        _anonymous_resource(resource, resource_tokens[resource.resource_id])
        for resource in resource_items
    )
    anonymous_plan = _anonymous_plan(
        plan,
        target_tokens,
        resource_tokens,
        coalition_tokens,
        node_tokens,
    )
    anonymous_previous = (
        None
        if previous_plan is None
        else _anonymous_plan(
            previous_plan,
            target_tokens,
            resource_tokens,
            coalition_tokens,
            node_tokens,
        )
    )
    recorded_authority_transition_sha256 = None
    if path == "regional_authority":
        if anonymous_previous is None:
            return PlanningFrameEvidence.unavailable(
                reason="regional_authority_previous_plan_missing",
                planning_path=path,
            )
        recorded_authority_transition_sha256 = (
            canonical_recorded_authority_transition_sha256(
                planning_path=path,
                selection_source=source,
                timestamp_s=timestamp,
                plan=anonymous_plan,
                previous_plan=anonymous_previous,
            )
        )

    # Sparse rule matrices intentionally reuse one reject-template mapping for
    # thousands of pruned cells.  Preserve that sharing while detaching the
    # snapshot, and reuse the sanitized structure when rule/effective results
    # point at the same source evidence.
    breakdown_cache: dict[
        int,
        tuple[Mapping[str, Any], Mapping[str, float]],
    ] = {}
    safe_key_cache: dict[str, bool] = {}
    anonymous_rule_matrix_result = _anonymous_matrix_result(
        rule_matrix_result,
        target_tokens,
        resource_tokens,
        keep_learning_metadata=False,
        breakdown_cache=breakdown_cache,
        safe_key_cache=safe_key_cache,
    )
    anonymous_effective_matrix_result = _anonymous_matrix_result(
        effective_matrix_result,
        target_tokens,
        resource_tokens,
        keep_learning_metadata=True,
        breakdown_cache=breakdown_cache,
        safe_key_cache=safe_key_cache,
        shared_breakdowns=(
            anonymous_rule_matrix_result.breakdowns
            if effective_matrix_result.breakdowns is rule_matrix_result.breakdowns
            else None
        ),
        shared_reject_reasons=(
            anonymous_rule_matrix_result.reject_reasons
            if effective_matrix_result.reject_reasons
            is rule_matrix_result.reject_reasons
            else None
        ),
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
        rule_matrix_result=anonymous_rule_matrix_result,
        effective_matrix_result=anonymous_effective_matrix_result,
        shadow_proposal_matrix=shadow_proposal,
        learning_mode=learning_mode,
        learning_state=learning_state,
        fallback_reason=fallback_reason,
        solver_name=str(plan.solver_name),
        tracks=anonymous_tracks,
        resources=anonymous_resources,
        plan=anonymous_plan,
        previous_plan=anonymous_previous,
        recorded_authority_transition_sha256=(
            recorded_authority_transition_sha256
        ),
        forced_replan=bool(forced_replan),
    )


def canonical_recorded_authority_transition_sha256(
    *,
    planning_path: str,
    selection_source: str,
    timestamp_s: float,
    plan: AssignmentPlan,
    previous_plan: AssignmentPlan,
) -> str:
    """Bind one recorded regional authority transition without exposing truth.

    Regional ownership is an external adjudication input to offline replay.  Its
    recorded output plan is therefore hashed together with the exact prior plan
    and frame identity.  Other planning paths continue to treat the output plan
    only as a replay result.
    """

    path = _required_text(planning_path, "planning_path")
    source = _required_text(selection_source, "selection_source")
    timestamp = float(timestamp_s)
    if path != "regional_authority" or source != "regional_authority":
        raise ValueError("recorded authority transition requires regional_authority")
    if not isfinite(timestamp):
        raise ValueError("recorded authority transition timestamp must be finite")
    previous_sha256 = validated_assignment_plan_payload_sha256(previous_plan)
    plan_sha256 = validated_assignment_plan_payload_sha256(plan)
    return canonical_runtime_payload_sha256(
        {
            "schema": "d3_recorded_regional_authority_transition_v1",
            "planning_path": path,
            "selection_source": source,
            "timestamp_s": timestamp,
            "previous_plan_id": previous_plan.plan_id,
            "previous_plan_version": previous_plan.version,
            "previous_plan_payload_sha256": previous_sha256,
            "plan_id": plan.plan_id,
            "plan_version": plan.version,
            "plan_previous_plan_id": plan.previous_plan_id,
            "plan_payload_sha256": plan_sha256,
        }
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
    breakdown_cache: dict[
        int,
        tuple[Mapping[str, Any], Mapping[str, float]],
    ] | None = None,
    safe_key_cache: dict[str, bool] | None = None,
    shared_breakdowns: tuple[tuple[Mapping[str, float], ...], ...] | None = None,
    shared_reject_reasons: tuple[tuple[str | None, ...], ...] | None = None,
) -> CostMatrixResult:
    metadata = (
        _safe_learning_metadata(result.metadata)
        if keep_learning_metadata
        else MappingProxyType({})
    )
    sanitized_breakdowns = (
        shared_breakdowns
        if shared_breakdowns is not None
        else tuple(
            tuple(
                _cached_safe_cost_breakdown(
                    value,
                    breakdown_cache=breakdown_cache,
                    safe_key_cache=safe_key_cache,
                )
                for value in row
            )
            for row in result.breakdowns
        )
    )
    sanitized_reject_reasons = (
        shared_reject_reasons
        if shared_reject_reasons is not None
        else tuple(
            tuple(None if value is None else str(value) for value in row)
            for row in result.reject_reasons
        )
    )
    return CostMatrixResult(
        matrix=_readonly_array(result.matrix, dtype=float),
        breakdowns=sanitized_breakdowns,
        target_ids=tuple(target_tokens[value] for value in result.target_ids),
        resource_ids=tuple(resource_tokens[value] for value in result.resource_ids),
        unassigned_costs=_readonly_array(result.unassigned_costs, dtype=float),
        target_threat_scores=tuple(float(value) for value in result.target_threat_scores),
        reject_reasons=sanitized_reject_reasons,
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
    coalition_tokens: Mapping[str, str],
    node_tokens: Mapping[str, str],
) -> AssignmentPlan:
    assignments = tuple(
        _anonymous_assignment(
            assignment,
            target_tokens,
            resource_tokens,
            coalition_tokens,
            node_tokens,
        )
        for assignment in plan.assignments
        if assignment.target_id in target_tokens
        and assignment.resource_id in resource_tokens
    )
    coalitions = tuple(
        _anonymous_coalition(
            coalition,
            target_tokens,
            resource_tokens,
            coalition_tokens,
        )
        for coalition in plan.coalitions
        if coalition.target_id in target_tokens
        and coalition.coalition_id in coalition_tokens
    )
    demand_summaries = tuple(
        _anonymous_demand_summary(summary, target_tokens, coalition_tokens)
        for summary in plan.demand_summaries
        if summary.target_id in target_tokens
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
        metadata=_safe_plan_replay_metadata(
            plan.metadata,
            resource_tokens,
            node_tokens,
        ),
        source_node_id=_anonymous_endpoint(
            plan.source_node_id,
            resource_tokens,
            node_tokens,
        ),
        target_node_id=_anonymous_endpoint(
            plan.target_node_id,
            resource_tokens,
            node_tokens,
        ),
        resource_count=int(plan.resource_count),
        target_count=int(plan.target_count),
        coalitions=coalitions,
        demand_summaries=demand_summaries,
    )


def _anonymous_assignment(
    assignment: Assignment,
    target_tokens: Mapping[str, str],
    resource_tokens: Mapping[str, str],
    coalition_tokens: Mapping[str, str],
    node_tokens: Mapping[str, str],
) -> Assignment:
    return replace(
        assignment,
        target_id=target_tokens[assignment.target_id],
        resource_id=resource_tokens[assignment.resource_id],
        cost_breakdown=_safe_cost_breakdown(assignment.cost_breakdown),
        source_node_id=_anonymous_endpoint(
            assignment.source_node_id,
            resource_tokens,
            node_tokens,
        ),
        target_node_id=_anonymous_endpoint(
            assignment.target_node_id,
            resource_tokens,
            node_tokens,
        ),
        coalition_id=(
            None
            if assignment.coalition_id is None
            else coalition_tokens[assignment.coalition_id]
        ),
        metadata=_safe_assignment_replay_metadata(
            assignment.metadata,
            resource_tokens,
            node_tokens,
        ),
    )


def _anonymous_coalition(
    coalition: CoalitionPlan,
    target_tokens: Mapping[str, str],
    resource_tokens: Mapping[str, str],
    coalition_tokens: Mapping[str, str],
) -> CoalitionPlan:
    return replace(
        coalition,
        coalition_id=coalition_tokens[coalition.coalition_id],
        target_id=target_tokens[coalition.target_id],
        members=tuple(
            replace(member, resource_id=resource_tokens[member.resource_id])
            for member in coalition.members
            if member.resource_id in resource_tokens
        ),
        metadata=MappingProxyType(
            {
                key: _safe_replay_value(coalition.metadata[key])
                for key in _COALITION_REPLAY_METADATA_KEYS
                if key in coalition.metadata
            }
        ),
    )


def _anonymous_demand_summary(
    summary: DemandSatisfactionSummary,
    target_tokens: Mapping[str, str],
    coalition_tokens: Mapping[str, str],
) -> DemandSatisfactionSummary:
    return replace(
        summary,
        target_id=target_tokens[summary.target_id],
        coalition_id=(
            None
            if summary.coalition_id is None
            else coalition_tokens[summary.coalition_id]
        ),
    )


def _safe_plan_replay_metadata(
    metadata: Mapping[str, Any],
    resource_tokens: Mapping[str, str],
    node_tokens: Mapping[str, str],
) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            key: (
                _anonymous_endpoint(
                    metadata[key],
                    resource_tokens,
                    node_tokens,
                )
                if key in _PLAN_REPLAY_NODE_KEYS
                else _safe_replay_value(metadata[key])
            )
            for key in _PLAN_REPLAY_METADATA_KEYS
            if key in metadata
        }
    )


def _safe_assignment_replay_metadata(
    metadata: Mapping[str, Any],
    resource_tokens: Mapping[str, str],
    node_tokens: Mapping[str, str],
) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            key: (
                _anonymous_endpoint(
                    metadata[key],
                    resource_tokens,
                    node_tokens,
                )
                if key == "owner_node_id"
                else _safe_replay_value(metadata[key])
            )
            for key in _ASSIGNMENT_REPLAY_METADATA_KEYS
            if key in metadata
        }
    )


def _anonymous_endpoint(
    value: str | None,
    resource_tokens: Mapping[str, str],
    node_tokens: Mapping[str, str],
) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text in resource_tokens:
        return resource_tokens[text]
    return node_tokens[text]


def _safe_replay_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _safe_replay_value(item)
                for key, item in value.items()
                if _safe_key(key)
            }
        )
    if isinstance(value, (tuple, list)):
        return tuple(_safe_replay_value(item) for item in value)
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    raise TypeError("unsupported planning replay metadata value")


def _plan_target_ids(plan: AssignmentPlan | None) -> set[str]:
    if plan is None:
        return set()
    return {
        *(assignment.target_id for assignment in plan.assignments),
        *(coalition.target_id for coalition in plan.coalitions),
        *(summary.target_id for summary in plan.demand_summaries),
        *plan.unassigned_target_ids,
        *plan.incomplete_target_ids,
    }


def _plan_resource_ids(plan: AssignmentPlan | None) -> set[str]:
    if plan is None:
        return set()
    return {
        *(assignment.resource_id for assignment in plan.assignments),
        *(
            member.resource_id
            for coalition in plan.coalitions
            for member in coalition.members
        ),
    }


def _plan_coalition_ids(plan: AssignmentPlan | None) -> set[str]:
    if plan is None:
        return set()
    return {
        *(coalition.coalition_id for coalition in plan.coalitions),
        *(
            assignment.coalition_id
            for assignment in plan.assignments
            if assignment.coalition_id is not None
        ),
        *(
            summary.coalition_id
            for summary in plan.demand_summaries
            if summary.coalition_id is not None
        ),
    }


def _plan_node_ids(
    plan: AssignmentPlan | None,
    resource_tokens: Mapping[str, str],
) -> set[str]:
    if plan is None:
        return set()
    values = {
        plan.source_node_id,
        plan.target_node_id,
        *(assignment.source_node_id for assignment in plan.assignments),
        *(assignment.target_node_id for assignment in plan.assignments),
        *(
            plan.metadata.get(key)
            for key in _PLAN_REPLAY_NODE_KEYS
        ),
        *(
            assignment.metadata.get("owner_node_id")
            for assignment in plan.assignments
        ),
    }
    return {
        str(value)
        for value in values
        if value is not None and str(value) not in resource_tokens
    }


def _cached_safe_cost_breakdown(
    value: Mapping[str, Any],
    *,
    breakdown_cache: dict[
        int,
        tuple[Mapping[str, Any], Mapping[str, float]],
    ] | None,
    safe_key_cache: dict[str, bool] | None,
) -> Mapping[str, float]:
    if breakdown_cache is None:
        return _safe_cost_breakdown(value, safe_key_cache=safe_key_cache)
    cache_key = id(value)
    cached = breakdown_cache.get(cache_key)
    if cached is not None and cached[0] is value:
        return cached[1]
    sanitized = _safe_cost_breakdown(value, safe_key_cache=safe_key_cache)
    breakdown_cache[cache_key] = (value, sanitized)
    return sanitized


def _safe_cost_breakdown(
    value: Mapping[str, Any],
    *,
    safe_key_cache: dict[str, bool] | None = None,
) -> Mapping[str, float]:
    return MappingProxyType(
        {
            str(key): float(item)
            for key, item in value.items()
            if _cached_safe_key(key, safe_key_cache)
            and isinstance(item, (int, float, np.number))
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


def _cached_safe_key(value: Any, cache: dict[str, bool] | None) -> bool:
    if cache is None:
        return _safe_key(value)
    key = str(value)
    if key not in cache:
        cache[key] = _safe_key(key)
    return cache[key]


def _readonly_array(value: Any, *, dtype: Any) -> np.ndarray:
    source = np.asarray(value, dtype=dtype)
    immutable = np.frombuffer(source.tobytes(order="C"), dtype=source.dtype).reshape(
        source.shape
    )
    immutable.setflags(write=False)
    return immutable


def _required_text(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result
