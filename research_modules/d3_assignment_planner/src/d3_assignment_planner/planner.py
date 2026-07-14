"""Rolling assignment planner with versioning and hysteresis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any
from uuid import uuid4

import numpy as np

from .costs import CostMatrixResult, CostModel
from .models import (
    ASSIGNMENT_CALIBRATION_PROFILE_SCHEMA_V1,
    ASSIGNMENT_PLAN_SCHEMA_V2,
    Assignment,
    AssignmentPlan,
    CoalitionMember,
    CoalitionMemberRole,
    CoalitionPlan,
    CoalitionState,
    CoordinationMode,
    DemandSatisfactionSummary,
    PlannerConfig,
    ResourceState,
    SolverResult,
    TargetDemand,
    TargetTrack,
)
from .solver import HungarianAssignmentSolver, HungarianDemandSlotSolver


@dataclass(frozen=True)
class _DemandSlot:
    target_index: int
    target_id: str
    slot_index: int
    member_role: str
    wave_id: int
    required_capability_class: str | None
    arrival_window_start_s: float | None
    arrival_window_end_s: float | None
    demand: TargetDemand


_TRANSIENT_FEEDBACK_REASONS = frozenset(
    {"primary_lock_stability_incomplete", "short_reacquire", "reacquire"}
)
_TRANSIENT_FEEDBACK_STATES = frozenset({"reacquire"})
_SOFT_MEMBER_FEEDBACK_STATES = frozenset({"hold", "reacquire"})
_HARD_FEEDBACK_STATES = frozenset(
    {
        "cross_view_conflict",
        "friend_overlap_hold",
        "lost",
        "mismatch",
        "multi_frame_inconsistent",
        "resource_unavailable",
        "wrong_binding",
    }
)
_HARD_FEEDBACK_CONFLICTS = frozenset(
    {
        "coalition_or_plan_version_mismatch",
        "member_count_exceeds_demand",
        "primary_binding_count_mismatch",
        "primary_binding_not_execution_authorized",
        "resource_multiple_local_locks",
        "wrong_binding",
    }
)


class StalePlanError(ValueError):
    """Raised when a rolling planner is asked to extend an obsolete plan."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        previous_plan_id: str | None = None,
        previous_version: int | None = None,
        expected_previous_version: int | None = None,
        latest_plan_id: str | None = None,
        latest_version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.previous_plan_id = previous_plan_id
        self.previous_version = previous_version
        self.expected_previous_version = expected_previous_version
        self.latest_plan_id = latest_plan_id
        self.latest_version = latest_version

    def to_metadata(self) -> dict[str, object]:
        """Return D6/main-friendly stale rejection metadata."""

        return {
            "stale_plan_rejected": True,
            "stale_reject_reason": self.reason,
            "previous_plan_id": self.previous_plan_id,
            "previous_plan_version": self.previous_version,
            "expected_previous_version": self.expected_previous_version,
            "latest_plan_id": self.latest_plan_id,
            "latest_plan_version": self.latest_version,
        }


class AssignmentPlanner:
    """Build, solve, and hysteresis-filter abstract candidate plans."""

    def __init__(
        self,
        cost_model: CostModel | None = None,
        solver: HungarianAssignmentSolver | None = None,
        config: PlannerConfig | None = None,
    ) -> None:
        self.config = config or PlannerConfig()
        self.cost_model = cost_model or CostModel(config=self.config)
        self.solver = solver or HungarianAssignmentSolver()
        self.demand_solver = HungarianDemandSlotSolver(self.solver)
        self._latest_version = 0
        self._latest_plan_id: str | None = None
        self._latest_published_plan: AssignmentPlan | None = None

    def plan(
        self,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        timestamp: float,
        previous_plan: AssignmentPlan | None = None,
        window_id: int | None = None,
        expected_previous_version: int | None = None,
        forced_replan: bool = False,
        publish: bool = True,
    ) -> AssignmentPlan:
        """Return a candidate plan and optionally publish its identity."""

        self._validate_previous_plan(previous_plan, expected_previous_version)
        result = self._plan_candidate(
            tracks=tracks,
            resources=resources,
            timestamp=timestamp,
            previous_plan=previous_plan,
            window_id=window_id,
        )
        result = self._annotate_input_snapshot(result, tracks, resources)
        return self._finalize_and_publish(
            result,
            previous_plan=previous_plan,
            timestamp=timestamp,
            forced_replan=forced_replan,
            publish=publish,
        )

    def plan_incremental(
        self,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        timestamp: float,
        *,
        previous_plan: AssignmentPlan,
        changed_track_ids: list[str] | tuple[str, ...] | set[str] = (),
        changed_resource_ids: list[str] | tuple[str, ...] | set[str] = (),
        window_id: int | None = None,
        expected_previous_version: int | None = None,
        forced_replan: bool = False,
        publish: bool = True,
    ) -> AssignmentPlan:
        """Replan one independent target-resource component when it is safe.

        The changed-id sets are declarations, not hints. Input fingerprints on
        ``previous_plan`` detect omitted changes. Any global or ambiguous change
        falls back to the ordinary full planner with an explicit metadata reason.
        Stale identities remain hard errors and are never silently substituted.
        """

        self._validate_previous_plan(previous_plan, expected_previous_version)
        track_items = tuple(tracks)
        resource_items = tuple(resources)
        changed_tracks = frozenset(str(value) for value in changed_track_ids)
        changed_resources = frozenset(str(value) for value in changed_resource_ids)
        started_at = perf_counter()

        matrix_result = self.cost_model.build_matrix(
            track_items,
            resource_items,
            timestamp,
        )
        fallback_reason = self._incremental_fallback_reason(
            tracks=track_items,
            resources=resource_items,
            previous_plan=previous_plan,
            changed_track_ids=changed_tracks,
            changed_resource_ids=changed_resources,
            timestamp=timestamp,
        )
        if fallback_reason is not None:
            return self._full_plan_from_incremental_request(
                tracks=track_items,
                resources=resource_items,
                timestamp=timestamp,
                previous_plan=previous_plan,
                changed_track_ids=changed_tracks,
                changed_resource_ids=changed_resources,
                fallback_reason=fallback_reason,
                window_id=window_id,
                forced_replan=forced_replan,
                publish=publish,
                started_at=started_at,
            )

        affected_targets, affected_resources = self._affected_component(
            matrix_result=matrix_result,
            previous_plan=previous_plan,
            changed_track_ids=changed_tracks,
            changed_resource_ids=changed_resources,
        )
        all_target_ids = frozenset(matrix_result.target_ids)
        all_resource_ids = frozenset(matrix_result.resource_ids)
        if not affected_targets or not affected_resources:
            return self._full_plan_from_incremental_request(
                tracks=track_items,
                resources=resource_items,
                timestamp=timestamp,
                previous_plan=previous_plan,
                changed_track_ids=changed_tracks,
                changed_resource_ids=changed_resources,
                fallback_reason="empty_affected_component",
                window_id=window_id,
                forced_replan=forced_replan,
                publish=publish,
                started_at=started_at,
            )
        if affected_targets == all_target_ids or affected_resources == all_resource_ids:
            return self._full_plan_from_incremental_request(
                tracks=track_items,
                resources=resource_items,
                timestamp=timestamp,
                previous_plan=previous_plan,
                changed_track_ids=changed_tracks,
                changed_resource_ids=changed_resources,
                fallback_reason="affected_component_is_global",
                window_id=window_id,
                forced_replan=forced_replan,
                publish=publish,
                started_at=started_at,
            )

        affected_track_items = tuple(
            track for track in track_items if track.track_id in affected_targets
        )
        affected_resource_items = tuple(
            resource
            for resource in resource_items
            if resource.resource_id in affected_resources
        )
        sub_previous = self._subplan(
            previous_plan,
            affected_target_ids=affected_targets,
            affected_resource_ids=affected_resources,
        )
        sub_candidate, _ = self._solve_candidate(
            tracks=affected_track_items,
            resources=affected_resource_items,
            timestamp=timestamp,
            previous_plan=sub_previous,
            window_id=window_id,
        )
        candidate = self._merge_incremental_result(
            sub_result=sub_candidate,
            previous_plan=previous_plan,
            tracks=track_items,
            resources=resource_items,
            matrix_result=matrix_result,
            affected_target_ids=affected_targets,
            affected_resource_ids=affected_resources,
            changed_track_ids=changed_tracks,
            changed_resource_ids=changed_resources,
            elapsed_ms=(perf_counter() - started_at) * 1000.0,
        )
        switched_matrix_result = self._apply_switch_penalty_to_matrix(
            matrix_result,
            previous_plan,
        )
        result = self._filter_candidate(
            candidate=candidate,
            previous_plan=previous_plan,
            matrix_result=switched_matrix_result,
            timestamp=timestamp,
            window_id=window_id,
            tracks=track_items,
        )
        result = replace(
            result,
            metadata={
                **dict(result.metadata),
                **self._incremental_metadata(
                    applied=True,
                    fallback_reason=None,
                    changed_track_ids=changed_tracks,
                    changed_resource_ids=changed_resources,
                    affected_target_ids=affected_targets,
                    affected_resource_ids=affected_resources,
                    all_target_ids=all_target_ids,
                    all_resource_ids=all_resource_ids,
                    elapsed_ms=(perf_counter() - started_at) * 1000.0,
                ),
            },
        )
        result = self._annotate_input_snapshot(result, track_items, resource_items)
        return self._finalize_and_publish(
            result,
            previous_plan=previous_plan,
            timestamp=timestamp,
            forced_replan=forced_replan,
            publish=publish,
        )

    def _plan_candidate(
        self,
        *,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        timestamp: float,
        previous_plan: AssignmentPlan | None,
        window_id: int | None,
    ) -> AssignmentPlan:
        """Build and hysteresis-filter a plan without identity publication."""

        candidate, matrix_result = self._solve_candidate(
            tracks=tracks,
            resources=resources,
            timestamp=timestamp,
            previous_plan=previous_plan,
            window_id=window_id,
        )
        return self._filter_candidate(
            candidate=candidate,
            previous_plan=previous_plan,
            matrix_result=matrix_result,
            timestamp=timestamp,
            window_id=window_id,
            tracks=tracks,
        )

    def _solve_candidate(
        self,
        *,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        timestamp: float,
        previous_plan: AssignmentPlan | None,
        window_id: int | None,
    ) -> tuple[AssignmentPlan, CostMatrixResult]:
        """Solve one input set without hysteresis or identity finalization."""

        matrix_result = self.cost_model.build_matrix(tracks, resources, timestamp)
        matrix_result = self._apply_switch_penalty_to_matrix(
            matrix_result,
            previous_plan,
        )
        if self._uses_demand_slots(tracks):
            candidate = self._build_demand_plan(
                tracks=tracks,
                resources=resources,
                matrix_result=matrix_result,
                timestamp=timestamp,
                previous_plan=previous_plan,
                window_id=window_id,
            )
        else:
            solver_result = self.solver.solve(
                matrix_result.matrix,
                matrix_result.unassigned_costs,
            )
            candidate = self._build_plan(
                matrix_result=matrix_result,
                solver_result=solver_result,
                timestamp=timestamp,
                previous_plan=previous_plan,
                window_id=window_id,
                decision_state="accepted",
                changed=True,
            )
        return candidate, matrix_result

    def _filter_candidate(
        self,
        *,
        candidate: AssignmentPlan,
        previous_plan: AssignmentPlan | None,
        matrix_result: CostMatrixResult,
        timestamp: float,
        window_id: int | None,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
    ) -> AssignmentPlan:
        """Apply the standard hysteresis contract to a solved candidate."""

        if previous_plan is None:
            result = candidate
        else:
            candidate, transient_held = self._apply_transient_feedback_dwell(
                candidate=candidate,
                previous_plan=previous_plan,
                matrix_result=matrix_result,
                timestamp=timestamp,
                window_id=window_id,
                tracks=tracks,
            )
            if transient_held:
                return candidate
        if previous_plan is not None and not self.config.enable_hysteresis:
            changed = candidate.stable_signature != previous_plan.stable_signature
            result = replace(
                candidate,
                changed=changed,
                decision_state="accepted_no_hysteresis",
                last_changed_at=timestamp if changed else previous_plan.last_changed_at,
                metadata={
                    **dict(candidate.metadata),
                    "hysteresis_state": "disabled",
                    "hysteresis_reason": "hysteresis_disabled",
                },
            )
        elif previous_plan is not None:
            result = self._apply_hysteresis(
                candidate=candidate,
                previous_plan=previous_plan,
                matrix_result=matrix_result,
                timestamp=timestamp,
                window_id=window_id,
            )
        return result

    def _finalize_and_publish(
        self,
        plan: AssignmentPlan,
        *,
        previous_plan: AssignmentPlan | None,
        timestamp: float,
        forced_replan: bool,
        publish: bool,
    ) -> AssignmentPlan:
        result = self._finalize_identity(
            plan,
            previous_plan=previous_plan,
            evaluated_at_s=timestamp,
            forced_replan=forced_replan,
            publish=publish,
        )
        if publish:
            self.publish_plan(result)
        return result

    def _full_plan_from_incremental_request(
        self,
        *,
        tracks: tuple[TargetTrack, ...],
        resources: tuple[ResourceState, ...],
        timestamp: float,
        previous_plan: AssignmentPlan,
        changed_track_ids: frozenset[str],
        changed_resource_ids: frozenset[str],
        fallback_reason: str,
        window_id: int | None,
        forced_replan: bool,
        publish: bool,
        started_at: float,
    ) -> AssignmentPlan:
        result = self._plan_candidate(
            tracks=tracks,
            resources=resources,
            timestamp=timestamp,
            previous_plan=previous_plan,
            window_id=window_id,
        )
        result = replace(
            result,
            metadata={
                **dict(result.metadata),
                **self._incremental_metadata(
                    applied=False,
                    fallback_reason=fallback_reason,
                    changed_track_ids=changed_track_ids,
                    changed_resource_ids=changed_resource_ids,
                    affected_target_ids=(),
                    affected_resource_ids=(),
                    all_target_ids=(track.track_id for track in tracks),
                    all_resource_ids=(resource.resource_id for resource in resources),
                    elapsed_ms=(perf_counter() - started_at) * 1000.0,
                ),
            },
        )
        result = self._annotate_input_snapshot(result, tracks, resources)
        return self._finalize_and_publish(
            result,
            previous_plan=previous_plan,
            timestamp=timestamp,
            forced_replan=forced_replan,
            publish=publish,
        )

    def _incremental_fallback_reason(
        self,
        *,
        tracks: tuple[TargetTrack, ...],
        resources: tuple[ResourceState, ...],
        previous_plan: AssignmentPlan,
        changed_track_ids: frozenset[str],
        changed_resource_ids: frozenset[str],
        timestamp: float,
    ) -> str | None:
        track_ids = tuple(track.track_id for track in tracks)
        resource_ids = tuple(resource.resource_id for resource in resources)
        if len(set(track_ids)) != len(track_ids):
            return "duplicate_track_ids"
        if len(set(resource_ids)) != len(resource_ids):
            return "duplicate_resource_ids"

        previous_track_fingerprints = self._snapshot_mapping(
            previous_plan.metadata.get("incremental_track_fingerprints")
        )
        previous_resource_fingerprints = self._snapshot_mapping(
            previous_plan.metadata.get("incremental_resource_fingerprints")
        )
        previous_demand_signatures = self._snapshot_mapping(
            previous_plan.metadata.get("incremental_demand_signatures")
        )
        if (
            previous_track_fingerprints is None
            or previous_resource_fingerprints is None
            or previous_demand_signatures is None
        ):
            return "missing_incremental_snapshot"

        current_track_fingerprints = {
            track.track_id: self._track_fingerprint(track) for track in tracks
        }
        current_resource_fingerprints = {
            resource.resource_id: self._resource_fingerprint(resource)
            for resource in resources
        }
        current_demand_signatures = {
            track.track_id: self._demand_signature(track.effective_demand)
            for track in tracks
        }
        if set(previous_track_fingerprints) != set(current_track_fingerprints):
            return "target_set_changed"
        if set(previous_resource_fingerprints) != set(current_resource_fingerprints):
            return "global_resource_capacity_changed"
        if changed_track_ids - set(current_track_fingerprints):
            return "unknown_changed_track_id"
        if changed_resource_ids - set(current_resource_fingerprints):
            return "unknown_changed_resource_id"
        if previous_demand_signatures != current_demand_signatures:
            return "target_demand_changed"

        detected_track_changes = {
            target_id
            for target_id, fingerprint in current_track_fingerprints.items()
            if previous_track_fingerprints[target_id] != fingerprint
        }
        detected_resource_changes = {
            resource_id
            for resource_id, fingerprint in current_resource_fingerprints.items()
            if previous_resource_fingerprints[resource_id] != fingerprint
        }
        if detected_track_changes - changed_track_ids:
            return "incomplete_changed_track_ids"
        if detected_resource_changes - changed_resource_ids:
            return "incomplete_changed_resource_ids"
        if not changed_track_ids and not changed_resource_ids:
            return "no_declared_changes"

        last_evaluated_at = float(
            previous_plan.metadata.get("last_evaluated_at_s", previous_plan.created_at)
        )
        stale_after_s = previous_plan.stale_after_s
        if stale_after_s is None:
            raw_stale_after = previous_plan.metadata.get("stale_after_s")
            stale_after_s = (
                None if raw_stale_after is None else float(raw_stale_after)
            )
        if (
            stale_after_s is not None
            and timestamp - last_evaluated_at > stale_after_s
        ):
            return "previous_plan_expired"
        if self._has_time_dependent_constraints(
            tracks,
            resources,
            last_evaluated_at=last_evaluated_at,
            timestamp=timestamp,
        ):
            return "time_dependent_global_constraint"
        return None

    def _affected_component(
        self,
        *,
        matrix_result: CostMatrixResult,
        previous_plan: AssignmentPlan,
        changed_track_ids: frozenset[str],
        changed_resource_ids: frozenset[str],
    ) -> tuple[frozenset[str], frozenset[str]]:
        target_neighbors: dict[str, set[str]] = {
            target_id: set() for target_id in matrix_result.target_ids
        }
        resource_neighbors: dict[str, set[str]] = {
            resource_id: set() for resource_id in matrix_result.resource_ids
        }
        for target_index, target_id in enumerate(matrix_result.target_ids):
            for resource_index, resource_id in enumerate(matrix_result.resource_ids):
                reject_reason = matrix_result.reject_reasons[target_index][resource_index]
                if (
                    reject_reason is not None
                    or float(matrix_result.matrix[target_index, resource_index])
                    >= self.config.infeasible_penalty * 0.5
                ):
                    continue
                target_neighbors[target_id].add(resource_id)
                resource_neighbors[resource_id].add(target_id)

        previous_by_resource = {
            assignment.resource_id: assignment.target_id
            for assignment in previous_plan.assignments
        }
        previous_resources_by_target = {
            target_id: {assignment.resource_id for assignment in assignments}
            for target_id, assignments in previous_plan.assignments_by_target().items()
        }
        affected_targets = set(changed_track_ids)
        affected_resources = set(changed_resource_ids)
        affected_targets.update(
            previous_by_resource[resource_id]
            for resource_id in changed_resource_ids
            if resource_id in previous_by_resource
        )

        changed = True
        while changed:
            changed = False
            for target_id in tuple(affected_targets):
                additions = (
                    target_neighbors.get(target_id, set())
                    | previous_resources_by_target.get(target_id, set())
                ) - affected_resources
                if additions:
                    affected_resources.update(additions)
                    changed = True
            for resource_id in tuple(affected_resources):
                additions = set(resource_neighbors.get(resource_id, set()))
                previous_target = previous_by_resource.get(resource_id)
                if previous_target is not None:
                    additions.add(previous_target)
                additions.difference_update(affected_targets)
                if additions:
                    affected_targets.update(additions)
                    changed = True
        return frozenset(affected_targets), frozenset(affected_resources)

    def _subplan(
        self,
        previous_plan: AssignmentPlan,
        *,
        affected_target_ids: frozenset[str],
        affected_resource_ids: frozenset[str],
    ) -> AssignmentPlan:
        assignments = tuple(
            assignment
            for assignment in previous_plan.assignments
            if assignment.target_id in affected_target_ids
            and assignment.resource_id in affected_resource_ids
        )
        coalitions = tuple(
            coalition
            for coalition in previous_plan.coalitions
            if coalition.target_id in affected_target_ids
        )
        return replace(
            previous_plan,
            assignments=assignments,
            coalitions=coalitions,
            unassigned_target_ids=tuple(
                target_id
                for target_id in previous_plan.unassigned_target_ids
                if target_id in affected_target_ids
            ),
            incomplete_target_ids=tuple(
                target_id
                for target_id in previous_plan.incomplete_target_ids
                if target_id in affected_target_ids
            ),
            demand_summaries=tuple(coalition.summary for coalition in coalitions),
            resource_count=len(affected_resource_ids),
            target_count=len(affected_target_ids),
        )

    def _merge_incremental_result(
        self,
        *,
        sub_result: AssignmentPlan,
        previous_plan: AssignmentPlan,
        tracks: tuple[TargetTrack, ...],
        resources: tuple[ResourceState, ...],
        matrix_result: CostMatrixResult,
        affected_target_ids: frozenset[str],
        affected_resource_ids: frozenset[str],
        changed_track_ids: frozenset[str],
        changed_resource_ids: frozenset[str],
        elapsed_ms: float,
    ) -> AssignmentPlan:
        switched_matrix = self._apply_switch_penalty_to_matrix(
            matrix_result,
            previous_plan,
        )
        target_index = {
            target_id: index
            for index, target_id in enumerate(switched_matrix.target_ids)
        }
        resource_index = {
            resource_id: index
            for index, resource_id in enumerate(switched_matrix.resource_ids)
        }
        preserved_target_ids = frozenset(target_index) - affected_target_ids
        preserved_assignments: list[Assignment] = []
        for assignment in previous_plan.assignments:
            if assignment.target_id not in preserved_target_ids:
                continue
            i = target_index[assignment.target_id]
            j = resource_index[assignment.resource_id]
            cost = float(switched_matrix.matrix[i, j])
            if cost >= self.config.infeasible_penalty * 0.5:
                raise ValueError(
                    "incremental component left an infeasible assignment frozen"
                )
            preserved_assignments.append(
                replace(
                    assignment,
                    cost=cost,
                    cost_breakdown=dict(switched_matrix.breakdowns[i][j]),
                    feasibility_state="feasible",
                )
            )

        preserved_coalitions = tuple(
            coalition
            for coalition in previous_plan.coalitions
            if coalition.target_id in preserved_target_ids
        )
        coalition_by_target = {
            coalition.target_id: coalition
            for coalition in preserved_coalitions + sub_result.coalitions
        }
        ordered_coalitions = tuple(
            coalition_by_target[track.track_id]
            for track in tracks
            if track.track_id in coalition_by_target
        )
        assignments = tuple(
            sorted(
                tuple(preserved_assignments) + sub_result.assignments,
                key=lambda item: (item.target_id, item.wave_id, item.resource_id),
            )
        )
        assignments = self._annotate_assignment_context(
            assignments,
            sub_result.version,
        )
        incomplete_target_ids = tuple(
            coalition.target_id
            for coalition in ordered_coalitions
            if not coalition.complete
        )
        demand_summaries = tuple(
            coalition.summary for coalition in ordered_coalitions
        )

        preserved_cost = sum(item.cost for item in preserved_assignments)
        track_by_id = {track.track_id: track for track in tracks}
        unassigned_cost_by_target = {
            target_id: float(switched_matrix.unassigned_costs[index])
            for index, target_id in enumerate(switched_matrix.target_ids)
        }
        for target_id in previous_plan.unassigned_target_ids:
            if target_id in preserved_target_ids:
                preserved_cost += (
                    unassigned_cost_by_target[target_id]
                    * track_by_id[target_id].effective_demand.required_resource_count
                )

        evidence_matrix = switched_matrix
        if self._uses_demand_slots(tracks):
            evidence_matrix = self._expand_demand_slot_matrix(
                self._demand_slots(tracks),
                resources,
                switched_matrix,
            )
        all_target_ids = frozenset(track_by_id)
        all_resource_ids = frozenset(resource_index)
        metadata = {
            **dict(sub_result.metadata),
            "resource_count": len(resources),
            "target_count": len(tracks),
            "assignment_matrix_shape": [
                len(evidence_matrix.target_ids),
                len(resources),
            ],
            "demand_slot_count": len(evidence_matrix.target_ids),
            "incomplete_target_ids": incomplete_target_ids,
            "demand_summaries": tuple(
                {
                    "target_id": summary.target_id,
                    "demand_required": summary.demand_required,
                    "demand_assigned": summary.demand_assigned,
                    "demand_shortfall": summary.demand_shortfall,
                    "coalition_complete": summary.coalition_complete,
                    "coalition_id": summary.coalition_id,
                    "coalition_version": summary.coalition_version,
                    "primary_resource_count": summary.primary_resource_count,
                }
                for summary in demand_summaries
            ),
            **self._matrix_evidence_metadata(evidence_matrix),
            **self._incremental_metadata(
                applied=True,
                fallback_reason=None,
                changed_track_ids=changed_track_ids,
                changed_resource_ids=changed_resource_ids,
                affected_target_ids=affected_target_ids,
                affected_resource_ids=affected_resource_ids,
                all_target_ids=all_target_ids,
                all_resource_ids=all_resource_ids,
                elapsed_ms=elapsed_ms,
            ),
        }
        return replace(
            sub_result,
            assignments=assignments,
            coalitions=ordered_coalitions,
            unassigned_target_ids=incomplete_target_ids,
            incomplete_target_ids=incomplete_target_ids,
            demand_summaries=demand_summaries,
            resource_count=len(resources),
            target_count=len(tracks),
            total_cost=preserved_cost + sub_result.total_cost,
            candidate_total_cost=preserved_cost
            + (
                sub_result.total_cost
                if sub_result.candidate_total_cost is None
                else sub_result.candidate_total_cost
            ),
            previous_total_cost_current=(
                None
                if sub_result.previous_total_cost_current is None
                else preserved_cost + sub_result.previous_total_cost_current
            ),
            metadata=metadata,
        )

    def _annotate_input_snapshot(
        self,
        plan: AssignmentPlan,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
    ) -> AssignmentPlan:
        return replace(
            plan,
            metadata={
                **dict(plan.metadata),
                "incremental_snapshot_schema": "d3_incremental_input_snapshot_v1",
                "incremental_track_fingerprints": tuple(
                    (track.track_id, self._track_fingerprint(track))
                    for track in tracks
                ),
                "incremental_resource_fingerprints": tuple(
                    (resource.resource_id, self._resource_fingerprint(resource))
                    for resource in resources
                ),
                "incremental_demand_signatures": tuple(
                    (track.track_id, self._demand_signature(track.effective_demand))
                    for track in tracks
                ),
            },
        )

    @staticmethod
    def _incremental_metadata(
        *,
        applied: bool,
        fallback_reason: str | None,
        changed_track_ids: Any,
        changed_resource_ids: Any,
        affected_target_ids: Any,
        affected_resource_ids: Any,
        all_target_ids: Any,
        all_resource_ids: Any,
        elapsed_ms: float,
    ) -> dict[str, object]:
        affected_targets = tuple(sorted(str(value) for value in affected_target_ids))
        affected_resources = tuple(
            sorted(str(value) for value in affected_resource_ids)
        )
        target_ids = tuple(sorted(str(value) for value in all_target_ids))
        resource_ids = tuple(sorted(str(value) for value in all_resource_ids))
        return {
            "planning_mode": "incremental" if applied else "full",
            "incremental_requested": True,
            "incremental_applied": applied,
            "incremental_fallback_reason": fallback_reason,
            "incremental_changed_track_ids": tuple(
                sorted(str(value) for value in changed_track_ids)
            ),
            "incremental_changed_resource_ids": tuple(
                sorted(str(value) for value in changed_resource_ids)
            ),
            "incremental_affected_target_ids": affected_targets,
            "incremental_affected_resource_ids": affected_resources,
            "incremental_preserved_target_ids": tuple(
                sorted(set(target_ids) - set(affected_targets))
            ),
            "incremental_preserved_resource_ids": tuple(
                sorted(set(resource_ids) - set(affected_resources))
            ),
            "incremental_subproblem_shape": [
                len(affected_targets),
                len(affected_resources),
            ],
            "incremental_solver_elapsed_ms": max(0.0, float(elapsed_ms)),
            "incremental_safety_policy": "exact_disconnected_component_or_full_fallback",
        }

    @staticmethod
    def _snapshot_mapping(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, (tuple, list)):
            return None
        result: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                return None
            result[str(item[0])] = item[1]
        return result

    @classmethod
    def _track_fingerprint(cls, track: TargetTrack) -> tuple[Any, ...]:
        return (
            float(track.threat_score),
            float(track.covariance),
            float(track.window_cost),
            bool(track.assignable),
            cls._stable_input_value(track.fov_difficulty_by_resource),
            cls._stable_input_value(track.conflict_risk_by_resource),
            cls._stable_input_value(track.feasibility_by_resource),
            cls._stable_input_value(track.metadata),
            bool(track.hard_time_window),
            track.time_window_open_at_s,
            track.time_window_close_at_s,
            track.time_window_state,
            cls._stable_input_value(track.time_window_by_resource),
            cls._demand_signature(track.effective_demand),
        )

    @classmethod
    def _resource_fingerprint(cls, resource: ResourceState) -> tuple[Any, ...]:
        return (
            resource.status,
            float(resource.health_score),
            float(resource.busy_until),
            bool(resource.operator_hold),
            float(resource.load_penalty),
            float(resource.fov_difficulty),
            float(resource.conflict_risk),
            resource.capability_class,
            float(resource.energy_fraction),
            float(resource.availability_score),
            float(resource.current_load),
            float(resource.history_failure_rate),
            cls._stable_input_value(resource.intercept_feasibility_by_target),
            cls._stable_input_value(
                resource.intercept_feasibility_score_by_target
            ),
            cls._stable_input_value(resource.metadata),
        )

    @classmethod
    def _demand_signature(cls, demand: TargetDemand) -> tuple[Any, ...]:
        return (
            demand.required_resource_count,
            demand.primary_resource_count,
            demand.coordination_mode,
            cls._stable_input_value(demand.required_capability_counts),
            demand.arrival_window_start_s,
            demand.arrival_window_end_s,
            demand.wave_interval_s,
            demand.minimum_separation_s,
            cls._stable_input_value(demand.metadata),
        )

    @classmethod
    def _stable_input_value(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return tuple(
                sorted(
                    (str(key), cls._stable_input_value(item))
                    for key, item in value.items()
                )
            )
        if isinstance(value, (tuple, list, set, frozenset)):
            items = tuple(cls._stable_input_value(item) for item in value)
            return tuple(sorted(items, key=repr)) if isinstance(value, (set, frozenset)) else items
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        return repr(value)

    @staticmethod
    def _has_time_dependent_constraints(
        tracks: tuple[TargetTrack, ...],
        resources: tuple[ResourceState, ...],
        *,
        last_evaluated_at: float,
        timestamp: float,
    ) -> bool:
        if timestamp == last_evaluated_at:
            return False
        if any(
            track.hard_time_window
            or track.time_window_open_at_s is not None
            or track.time_window_close_at_s is not None
            or track.time_window_state is not None
            or bool(track.time_window_by_resource)
            for track in tracks
        ):
            return True
        return any(
            min(last_evaluated_at, timestamp)
            < resource.busy_until
            <= max(last_evaluated_at, timestamp)
            for resource in resources
        )

    def publish_plan(self, plan: AssignmentPlan) -> AssignmentPlan:
        """Register a plan as published for subsequent stale checks."""

        plan = replace(
            plan,
            metadata={**dict(plan.metadata), "plan_published": True},
        )
        latest = self._latest_published_plan
        if latest is not None:
            same_identity = (
                plan.plan_id == latest.plan_id and plan.version == latest.version
            )
            if same_identity:
                if plan.execution_signature() != latest.execution_signature():
                    raise ValueError(
                        "published plan cannot change execution semantics without a new identity"
                    )
                self._latest_published_plan = plan
                return plan
            if plan.execution_signature() == latest.execution_signature():
                raise ValueError(
                    "evaluation-only refresh cannot advance executable plan identity"
                )
            if plan.version != latest.version + 1:
                raise StalePlanError(
                    "published plan version must extend the latest published plan",
                    reason="publish_version_discontinuity",
                    previous_plan_id=plan.previous_plan_id,
                    previous_version=plan.version - 1,
                    latest_plan_id=latest.plan_id,
                    latest_version=latest.version,
                )
            if plan.previous_plan_id != latest.plan_id:
                raise StalePlanError(
                    "published plan does not supersede the latest published plan",
                    reason="publish_previous_plan_mismatch",
                    previous_plan_id=plan.previous_plan_id,
                    previous_version=plan.version - 1,
                    latest_plan_id=latest.plan_id,
                    latest_version=latest.version,
                )
        self._latest_version = plan.version
        self._latest_plan_id = plan.plan_id
        self._latest_published_plan = plan
        return plan

    def _finalize_identity(
        self,
        plan: AssignmentPlan,
        *,
        previous_plan: AssignmentPlan | None,
        evaluated_at_s: float,
        forced_replan: bool,
        publish: bool,
    ) -> AssignmentPlan:
        execution_changed = (
            previous_plan is None
            or plan.execution_signature() != previous_plan.execution_signature()
        )
        evaluation_refresh = previous_plan is not None and not execution_changed
        identity_created_at_s = (
            plan.created_at
            if previous_plan is None or execution_changed
            else previous_plan.created_at
        )
        last_evaluated_at_s = float(evaluated_at_s)
        metadata = {
            **dict(plan.metadata),
            "execution_signature_changed": execution_changed,
            "identity_created_at_s": identity_created_at_s,
            "last_evaluated_at_s": last_evaluated_at_s,
            "plan_published": publish,
            "plan_refresh_only": False,
            "evaluation_refresh_only": evaluation_refresh,
        }
        assignments = tuple(
            replace(
                assignment,
                metadata={
                    **dict(assignment.metadata),
                    "identity_created_at_s": identity_created_at_s,
                    "last_evaluated_at_s": last_evaluated_at_s,
                },
            )
            for assignment in plan.assignments
        )
        decision_state = plan.decision_state
        changed = execution_changed
        if forced_replan and previous_plan is not None:
            decision_state = (
                "replan_applied" if execution_changed else "replan_ack_no_change"
            )
            metadata.update(
                {
                    "forced_replan": True,
                    "replan_response_state": decision_state,
                    "replan_underlying_decision_state": plan.decision_state,
                }
            )
        else:
            metadata["forced_replan"] = False

        if previous_plan is None or execution_changed:
            return replace(
                plan,
                assignments=assignments,
                changed=changed,
                decision_state=decision_state,
                metadata=metadata,
            )

        assignments = tuple(
            replace(
                assignment,
                plan_version=previous_plan.version,
                metadata={
                    **dict(assignment.metadata),
                    "plan_version": previous_plan.version,
                    "current_plan_id": previous_plan.plan_id,
                    "current_plan_version": previous_plan.version,
                    "plan_refresh_only": False,
                    "evaluation_refresh_only": True,
                },
            )
            for assignment in assignments
        )
        metadata.update(
            {
                "current_plan_id": previous_plan.plan_id,
                "current_plan_version": previous_plan.version,
                "plan_version": previous_plan.version,
            }
        )
        return replace(
            plan,
            plan_id=previous_plan.plan_id,
            version=previous_plan.version,
            assignments=assignments,
            created_at=previous_plan.created_at,
            last_changed_at=previous_plan.last_changed_at,
            previous_plan_id=previous_plan.previous_plan_id,
            changed=False,
            decision_state=decision_state,
            metadata=metadata,
        )

    def _build_plan(
        self,
        matrix_result: CostMatrixResult,
        solver_result: SolverResult,
        timestamp: float,
        previous_plan: AssignmentPlan | None,
        window_id: int | None,
        decision_state: str,
        changed: bool,
        last_changed_at: float | None = None,
        total_cost: float | None = None,
        assignments: tuple[Assignment, ...] | None = None,
        unassigned_target_ids: tuple[str, ...] | None = None,
        coalitions: tuple[CoalitionPlan, ...] | None = None,
        incomplete_target_ids: tuple[str, ...] | None = None,
        demand_summaries: tuple[DemandSatisfactionSummary, ...] | None = None,
        reported_target_count: int | None = None,
    ) -> AssignmentPlan:
        version = 1 if previous_plan is None else previous_plan.version + 1
        plan_window_id = version if window_id is None else window_id
        if assignments is None:
            assignments = self._assignments_from_solver(matrix_result, solver_result)
        if coalitions is None:
            assignments, coalitions = self._build_independent_coalitions(
                matrix_result.target_ids,
                assignments,
                previous_plan,
                timestamp,
            )
        assignments = self._annotate_assignment_context(assignments, version)
        if unassigned_target_ids is None:
            solver_unassigned = tuple(
                matrix_result.target_ids[index]
                for index in solver_result.unassigned_target_indices
            )
            assigned_target_ids = {assignment.target_id for assignment in assignments}
            unassigned_target_ids = tuple(
                target_id
                for target_id in matrix_result.target_ids
                if target_id in solver_unassigned
                or target_id not in assigned_target_ids
            )
        target_count = (
            len(matrix_result.target_ids)
            if reported_target_count is None
            else reported_target_count
        )
        resource_count = len(matrix_result.resource_ids)
        incomplete_target_ids = (
            tuple(unassigned_target_ids)
            if incomplete_target_ids is None
            else incomplete_target_ids
        )
        demand_summaries = (
            tuple(coalition.summary for coalition in coalitions)
            if demand_summaries is None
            else demand_summaries
        )
        plan_id = f"d3-plan-{uuid4().hex[:12]}"
        return AssignmentPlan(
            plan_id=plan_id,
            version=version,
            window_id=plan_window_id,
            assignments=assignments,
            unassigned_target_ids=unassigned_target_ids,
            total_cost=solver_result.objective_value if total_cost is None else total_cost,
            created_at=timestamp,
            last_changed_at=timestamp if last_changed_at is None else last_changed_at,
            resource_count=resource_count,
            target_count=target_count,
            plan_schema=ASSIGNMENT_PLAN_SCHEMA_V2,
            coalitions=coalitions,
            incomplete_target_ids=incomplete_target_ids,
            demand_summaries=demand_summaries,
            human_authorization_state=self.config.human_authorization_state,
            decision_state=decision_state,
            changed=changed,
            solver_name=solver_result.solver_name,
            previous_plan_id=None if previous_plan is None else previous_plan.plan_id,
            candidate_total_cost=solver_result.objective_value,
            metadata={
                "configured_human_authorization_state": self.config.human_authorization_state,
                "effective_human_authorization_state": self.config.human_authorization_state,
                "current_plan_id": plan_id,
                "current_plan_version": version,
                "current_plan_owner": "center",
                "current_plan_owner_node_id": self.config.source_node_id,
                "plan_owner": "center",
                "active_plan_owner": "center",
                "owner_node_id": self.config.source_node_id,
                "source_node_id": self.config.source_node_id,
                "target_node_id": self.config.target_node_id,
                "link_type": self.config.link_type,
                "plan_version": version,
                "plan_schema": ASSIGNMENT_PLAN_SCHEMA_V2,
                "stale_after_s": self.config.stale_after_s,
                "resource_count": resource_count,
                "target_count": target_count,
                "assignment_matrix_shape": [len(matrix_result.target_ids), resource_count],
                "demand_slot_count": len(matrix_result.target_ids),
                "incomplete_target_ids": incomplete_target_ids,
                "demand_summaries": tuple(
                    {
                        "target_id": summary.target_id,
                        "demand_required": summary.demand_required,
                        "demand_assigned": summary.demand_assigned,
                        "demand_shortfall": summary.demand_shortfall,
                        "coalition_complete": summary.coalition_complete,
                        "coalition_id": summary.coalition_id,
                        "coalition_version": summary.coalition_version,
                        "primary_resource_count": summary.primary_resource_count,
                    }
                    for summary in demand_summaries
                ),
                "hysteresis_enabled": self.config.enable_hysteresis,
                "hysteresis_delta": self.config.delta,
                "hysteresis_min_dwell_s": self.config.min_dwell,
                "hysteresis_max_changes_per_window": self.config.max_changes_per_window,
                "reassignment_switch_penalty": self.config.reassignment_switch_penalty,
                "transient_feedback_dwell_frames": max(
                    1,
                    int(self.config.transient_feedback_dwell_frames),
                ),
                "terminal_authorization_scope": "per_primary",
                "arrival_coordination_required": False,
                "coalition_membership": tuple(
                    {
                        "target_id": coalition.target_id,
                        "coalition_id": coalition.coalition_id,
                        "coalition_version": coalition.version,
                        "coalition_epoch": coalition.epoch,
                        "terminal_authorization_scope": coalition.terminal_authorization_scope,
                        "arrival_coordination_required": coalition.arrival_coordination_required,
                        "membership_change_reason": coalition.metadata.get(
                            "membership_change_reason"
                        ),
                        "previous_members": coalition.metadata.get("previous_members", ()),
                        "current_members": coalition.metadata.get("current_members", ()),
                        "membership_hold_basis": coalition.metadata.get(
                            "membership_hold_basis"
                        ),
                    }
                    for coalition in coalitions
                ),
                "high_threat_threshold": self.config.high_threat_threshold,
                "assignment_profile_schema": ASSIGNMENT_CALIBRATION_PROFILE_SCHEMA_V1,
                "cost_profile_id": self.config.cost_profile_id,
                "cost_profile_version": self.config.cost_profile_version,
                "feedback_profile_id": self.config.feedback_profile_id,
                "feedback_profile_version": self.config.feedback_profile_version,
                "cost_weights": self._cost_weights_metadata(),
                "planner_thresholds": self._planner_thresholds_metadata(),
                **self._matrix_evidence_metadata(matrix_result),
            },
            source_node_id=self.config.source_node_id,
            target_node_id=self.config.target_node_id,
            link_type=self.config.link_type,
            stale_after_s=self.config.stale_after_s,
        )

    def _assignments_from_solver(
        self,
        matrix_result: CostMatrixResult,
        solver_result: SolverResult,
    ) -> tuple[Assignment, ...]:
        assignments: list[Assignment] = []
        for item in solver_result.assignments:
            target_id = matrix_result.target_ids[item.target_index]
            resource_id = matrix_result.resource_ids[item.resource_index]
            cost = float(matrix_result.matrix[item.target_index, item.resource_index])
            if cost >= self.config.infeasible_penalty * 0.5:
                continue
            assignments.append(
                Assignment(
                    target_id=target_id,
                    resource_id=resource_id,
                    cost=cost,
                    cost_breakdown=dict(
                        matrix_result.breakdowns[item.target_index][item.resource_index]
                    ),
                    feasibility_state="feasible",
                )
            )
        return tuple(assignments)

    def _uses_demand_slots(
        self,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
    ) -> bool:
        if self.config.solver_name == "hungarian_demand_slots":
            return True
        return any(
            track.demand is not None
            and (
                track.demand.required_resource_count > 1
                or track.demand.coordination_mode != CoordinationMode.INDEPENDENT.value
                or bool(track.demand.required_capability_counts)
            )
            for track in tracks
        )

    def _soft_reserve_feedback_primary_pins(
        self,
        *,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        previous_plan: AssignmentPlan | None,
        matrix_result: CostMatrixResult,
    ) -> dict[str, frozenset[str]]:
        """Pin healthy primaries when only a reserve reports a soft failure."""

        if previous_plan is None:
            return {}
        feedback_events = self._terminal_feedback_events(tracks)
        if not feedback_events:
            return {}

        events_by_target: dict[str, list[Mapping[str, Any]]] = {}
        for event in feedback_events:
            if event.get("plan_version") != previous_plan.version:
                continue
            target_id = event.get("target_id")
            resource_id = event.get("resource_id")
            if target_id is None or resource_id is None:
                continue
            events_by_target.setdefault(str(target_id), []).append(event)

        target_index = {
            target_id: index
            for index, target_id in enumerate(matrix_result.target_ids)
        }
        resource_index = {
            resource_id: index
            for index, resource_id in enumerate(matrix_result.resource_ids)
        }
        resource_by_id = {
            resource.resource_id: resource for resource in resources
        }
        track_by_id = {track.track_id: track for track in tracks}
        previous_coalition_by_target = {
            coalition.target_id: coalition for coalition in previous_plan.coalitions
        }
        pins: dict[str, frozenset[str]] = {}

        for target_id, target_events in events_by_target.items():
            track = track_by_id.get(target_id)
            previous_coalition = previous_coalition_by_target.get(target_id)
            previous_assignments = previous_plan.assignments_by_target().get(
                target_id,
                (),
            )
            if track is None or previous_coalition is None or not previous_assignments:
                continue
            demand = track.effective_demand
            if (
                demand.required_resource_count
                != previous_coalition.required_resource_count
                or demand.primary_resource_count
                != previous_coalition.primary_resource_count
                or demand.coordination_mode != previous_coalition.coordination_mode
            ):
                continue
            if any(self._hard_feedback_reasons(event) for event in target_events):
                continue

            events_by_resource: dict[str, list[Mapping[str, Any]]] = {}
            for event in target_events:
                events_by_resource.setdefault(str(event["resource_id"]), []).append(
                    event
                )
            primary_assignments = tuple(
                assignment
                for assignment in previous_assignments
                if assignment.member_role == CoalitionMemberRole.PRIMARY.value
            )
            reserve_assignments = tuple(
                assignment
                for assignment in previous_assignments
                if assignment.member_role == CoalitionMemberRole.RESERVE.value
            )
            if (
                len(primary_assignments) != demand.primary_resource_count
                or not reserve_assignments
                or not all(
                    all(
                        self._is_consistent_member_feedback(event)
                        for event in events_by_resource.get(
                            assignment.resource_id,
                            (),
                        )
                    )
                    for assignment in primary_assignments
                )
                or any(
                    not events_by_resource.get(assignment.resource_id)
                    for assignment in primary_assignments
                )
                or not any(
                    self._is_soft_member_feedback(event)
                    for assignment in reserve_assignments
                    for event in events_by_resource.get(assignment.resource_id, [])
                )
            ):
                continue

            i = target_index.get(target_id)
            if i is None:
                continue
            primary_ids: set[str] = set()
            primary_feasible = True
            for assignment in primary_assignments:
                resource_id = assignment.resource_id
                j = resource_index.get(resource_id)
                resource = resource_by_id.get(resource_id)
                required_capability = assignment.metadata.get(
                    "required_capability_class"
                )
                if (
                    j is None
                    or resource is None
                    or matrix_result.reject_reasons[i][j] is not None
                    or float(matrix_result.matrix[i, j])
                    >= self.config.infeasible_penalty * 0.5
                    or (
                        required_capability is not None
                        and not self._resource_has_capability(
                            resource,
                            str(required_capability),
                        )
                    )
                ):
                    primary_feasible = False
                    break
                primary_ids.add(resource_id)
            if primary_feasible and len(primary_ids) == demand.primary_resource_count:
                pins[target_id] = frozenset(primary_ids)
        return pins

    @staticmethod
    def _is_consistent_member_feedback(event: Mapping[str, Any]) -> bool:
        state = str(event.get("terminal_feedback_state") or "").strip().lower()
        action = str(event.get("main_action") or "continue").strip().lower()
        return state == "consistent" and action == "continue"

    @staticmethod
    def _is_soft_member_feedback(event: Mapping[str, Any]) -> bool:
        state = str(event.get("terminal_feedback_state") or "").strip().lower()
        action = str(event.get("main_action") or "").strip().lower()
        return state in _SOFT_MEMBER_FEEDBACK_STATES and action in {
            "hold",
            "replan",
        }

    def _build_demand_plan(
        self,
        *,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        matrix_result: CostMatrixResult,
        timestamp: float,
        previous_plan: AssignmentPlan | None,
        window_id: int | None,
    ) -> AssignmentPlan:
        slots = self._demand_slots(tracks)
        primary_pins_by_target = self._soft_reserve_feedback_primary_pins(
            tracks=tracks,
            resources=resources,
            previous_plan=previous_plan,
            matrix_result=matrix_result,
        )
        slot_matrix_result = self._expand_demand_slot_matrix(
            slots,
            resources,
            matrix_result,
            primary_pins_by_target=primary_pins_by_target,
        )
        slots_by_target: dict[str, tuple[int, ...]] = {}
        for slot_index, slot in enumerate(slots):
            slots_by_target.setdefault(slot.target_id, tuple())
            slots_by_target[slot.target_id] += (slot_index,)

        active_slots = set(range(len(slots)))
        tentative_by_incomplete: dict[str, tuple[tuple[int, int], ...]] = {}
        final_pairs: tuple[tuple[int, int], ...] = ()
        final_objective = 0.0
        threat_by_target = {track.track_id: track.threat_score for track in tracks}

        while True:
            active_order = tuple(sorted(active_slots))
            sub_matrix = slot_matrix_result.matrix[list(active_order), :]
            sub_unassigned = slot_matrix_result.unassigned_costs[list(active_order)]
            result = self.demand_solver.solve(sub_matrix, sub_unassigned)
            pairs = tuple(
                (active_order[item.target_index], item.resource_index)
                for item in result.assignments
            )
            assigned_count: dict[str, int] = {}
            for slot_index, _ in pairs:
                target_id = slots[slot_index].target_id
                assigned_count[target_id] = assigned_count.get(target_id, 0) + 1
            active_target_ids = {
                slots[slot_index].target_id for slot_index in active_order
            }
            incomplete = [
                target_id
                for target_id in active_target_ids
                if assigned_count.get(target_id, 0)
                < slots[slots_by_target[target_id][0]].demand.required_resource_count
            ]
            if not incomplete:
                final_pairs = pairs
                final_objective = result.objective_value
                break

            victim = min(
                incomplete,
                key=lambda target_id: (threat_by_target.get(target_id, 0.0), target_id),
            )
            tentative_by_incomplete[victim] = tuple(
                pair for pair in pairs if slots[pair[0]].target_id == victim
            )
            active_slots.difference_update(slots_by_target[victim])

        pair_by_slot = {slot_index: resource_index for slot_index, resource_index in final_pairs}
        previous_coalition_by_target = {
            coalition.target_id: coalition
            for coalition in (() if previous_plan is None else previous_plan.coalitions)
        }
        coalitions: list[CoalitionPlan] = []
        assignments: list[Assignment] = []

        for track in tracks:
            target_slots = slots_by_target[track.track_id]
            complete_pairs = tuple(
                (slot_index, pair_by_slot[slot_index])
                for slot_index in target_slots
                if slot_index in pair_by_slot
            )
            complete = len(complete_pairs) == track.effective_demand.required_resource_count
            member_pairs = (
                complete_pairs
                if complete
                else tentative_by_incomplete.get(track.track_id, ())
            )
            members = tuple(
                self._coalition_member(slots[slot_index], resources[resource_index], complete)
                for slot_index, resource_index in sorted(member_pairs)
            )
            coalition = self._coalition_plan(
                track=track,
                members=members,
                complete=complete,
                previous=previous_coalition_by_target.get(track.track_id),
                timestamp=timestamp,
            )
            coalitions.append(coalition)
            if not complete:
                continue
            for slot_index, resource_index in complete_pairs:
                slot = slots[slot_index]
                cost = float(slot_matrix_result.matrix[slot_index, resource_index])
                assignments.append(
                    Assignment(
                        target_id=track.track_id,
                        resource_id=resources[resource_index].resource_id,
                        cost=cost,
                        cost_breakdown=dict(
                            slot_matrix_result.breakdowns[slot_index][resource_index]
                        ),
                        feasibility_state="feasible",
                        coalition_id=coalition.coalition_id,
                        coalition_version=coalition.version,
                        member_role=slot.member_role,
                        wave_id=slot.wave_id,
                        arrival_window_start_s=slot.arrival_window_start_s,
                        arrival_window_end_s=slot.arrival_window_end_s,
                        required_resource_count=slot.demand.required_resource_count,
                        terminal_authorization_scope=(
                            slot.demand.terminal_authorization_scope
                        ),
                        arrival_coordination_required=(
                            slot.demand.arrival_coordination_required
                        ),
                        metadata={
                            "required_capability_class": slot.required_capability_class,
                            "coordination_mode": slot.demand.coordination_mode,
                            "primary_resource_count": slot.demand.primary_resource_count,
                            "minimum_separation_s": slot.demand.minimum_separation_s,
                            "terminal_authorization_scope": (
                                slot.demand.terminal_authorization_scope
                            ),
                            "arrival_coordination_required": (
                                slot.demand.arrival_coordination_required
                            ),
                            "coalition_epoch": coalition.epoch,
                            "activation_state": (
                                "standby"
                                if slot.member_role
                                == CoalitionMemberRole.RESERVE.value
                                else "active"
                            ),
                            "executable": (
                                slot.member_role
                                != CoalitionMemberRole.RESERVE.value
                            ),
                        },
                    )
                )

        incomplete_target_ids = tuple(
            coalition.target_id for coalition in coalitions if not coalition.complete
        )
        final_objective += sum(
            float(matrix_result.unassigned_costs[index])
            * track.effective_demand.required_resource_count
            for index, track in enumerate(tracks)
            if track.track_id in incomplete_target_ids
        )
        solver_result = SolverResult(
            assignments=(),
            unassigned_target_indices=(),
            objective_value=final_objective,
            solver_name=self.demand_solver.solver_name,
            status="optimal",
        )
        plan = self._build_plan(
            matrix_result=slot_matrix_result,
            solver_result=solver_result,
            timestamp=timestamp,
            previous_plan=previous_plan,
            window_id=window_id,
            decision_state="accepted",
            changed=True,
            assignments=tuple(assignments),
            unassigned_target_ids=incomplete_target_ids,
            coalitions=tuple(coalitions),
            incomplete_target_ids=incomplete_target_ids,
            demand_summaries=tuple(coalition.summary for coalition in coalitions),
            reported_target_count=len(tracks),
        )
        if not primary_pins_by_target:
            return plan
        assert previous_plan is not None
        return replace(
            plan,
            metadata={
                **dict(plan.metadata),
                "feedback_primary_role_protection_applied": True,
                "feedback_primary_role_protection_reason": (
                    "reserve_soft_feedback_primary_consistent"
                ),
                "feedback_primary_role_protection_by_target": tuple(
                    {
                        "target_id": target_id,
                        "primary_resource_ids": tuple(sorted(resource_ids)),
                        "source_plan_id": previous_plan.plan_id,
                        "source_plan_version": previous_plan.version,
                    }
                    for target_id, resource_ids in sorted(
                        primary_pins_by_target.items()
                    )
                ),
            },
        )

    def _demand_slots(
        self,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
    ) -> tuple[_DemandSlot, ...]:
        slots: list[_DemandSlot] = []
        for target_index, track in enumerate(tracks):
            demand = track.effective_demand
            capabilities = [
                capability
                for capability, count in sorted(demand.required_capability_counts.items())
                for _ in range(count)
            ]
            capabilities.extend(
                [None] * (demand.required_resource_count - len(capabilities))
            )
            for slot_index, capability in enumerate(capabilities):
                role, wave_id = self._slot_role_wave(demand, slot_index)
                window_shift = wave_id * demand.wave_interval_s
                slots.append(
                    _DemandSlot(
                        target_index=target_index,
                        target_id=track.track_id,
                        slot_index=slot_index,
                        member_role=role,
                        wave_id=wave_id,
                        required_capability_class=capability,
                        arrival_window_start_s=(
                            None
                            if demand.arrival_window_start_s is None
                            else demand.arrival_window_start_s + window_shift
                        ),
                        arrival_window_end_s=(
                            None
                            if demand.arrival_window_end_s is None
                            else demand.arrival_window_end_s + window_shift
                        ),
                        demand=demand,
                    )
                )
        return tuple(slots)

    @staticmethod
    def _slot_role_wave(demand: TargetDemand, slot_index: int) -> tuple[str, int]:
        if demand.coordination_mode == CoordinationMode.HYBRID.value:
            if slot_index < demand.primary_resource_count:
                return CoalitionMemberRole.PRIMARY.value, 0
            return CoalitionMemberRole.RESERVE.value, 1
        if demand.coordination_mode == CoordinationMode.SEQUENTIAL.value:
            role = (
                CoalitionMemberRole.PRIMARY.value
                if slot_index == 0
                else CoalitionMemberRole.RETRY.value
            )
            return role, slot_index
        return CoalitionMemberRole.PRIMARY.value, 0

    def _expand_demand_slot_matrix(
        self,
        slots: tuple[_DemandSlot, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        matrix_result: CostMatrixResult,
        *,
        primary_pins_by_target: Mapping[str, frozenset[str]] | None = None,
    ) -> CostMatrixResult:
        primary_pins_by_target = primary_pins_by_target or {}
        pinned_owner_by_resource = {
            resource_id: target_id
            for target_id, resource_ids in primary_pins_by_target.items()
            for resource_id in resource_ids
        }
        matrix = np.zeros((len(slots), len(resources)), dtype=float)
        breakdowns: list[tuple[dict[str, float], ...]] = []
        reject_reasons: list[tuple[str | None, ...]] = []
        unassigned: list[float] = []
        for slot in slots:
            row_breakdowns: list[dict[str, float]] = []
            row_rejections: list[str | None] = []
            for resource_index, resource in enumerate(resources):
                breakdown = dict(
                    matrix_result.breakdowns[slot.target_index][resource_index]
                )
                reject_reason = matrix_result.reject_reasons[slot.target_index][resource_index]
                cost = float(matrix_result.matrix[slot.target_index, resource_index])
                if (
                    reject_reason is None
                    and slot.required_capability_class is not None
                    and not self._resource_has_capability(
                        resource, slot.required_capability_class
                    )
                ):
                    reject_reason = "required_capability_unavailable"
                    cost = self.config.infeasible_penalty
                    breakdown["infeasible"] = self.config.infeasible_penalty
                    breakdown["total"] = cost
                protected_primary_ids = primary_pins_by_target.get(slot.target_id)
                if (
                    reject_reason is None
                    and protected_primary_ids
                    and slot.member_role == CoalitionMemberRole.PRIMARY.value
                    and resource.resource_id not in protected_primary_ids
                ):
                    reject_reason = "feedback_primary_role_protected"
                    cost = self.config.infeasible_penalty
                    breakdown["infeasible"] = self.config.infeasible_penalty
                    breakdown["total"] = cost
                pinned_owner = pinned_owner_by_resource.get(resource.resource_id)
                if (
                    reject_reason is None
                    and pinned_owner is not None
                    and (
                        slot.target_id != pinned_owner
                        or slot.member_role != CoalitionMemberRole.PRIMARY.value
                    )
                ):
                    reject_reason = "feedback_primary_resource_reserved"
                    cost = self.config.infeasible_penalty
                    breakdown["infeasible"] = self.config.infeasible_penalty
                    breakdown["total"] = cost
                matrix[len(breakdowns), resource_index] = cost
                row_breakdowns.append(breakdown)
                row_rejections.append(reject_reason)
            breakdowns.append(tuple(row_breakdowns))
            reject_reasons.append(tuple(row_rejections))
            base = float(matrix_result.unassigned_costs[slot.target_index])
            priority_penalty = self.config.infeasible_penalty * (
                0.1 + 0.2 * max(0.0, min(1.0, matrix_result.target_threat_scores[slot.target_index]))
            )
            unassigned.append(base + priority_penalty)
        return CostMatrixResult(
            matrix=matrix,
            breakdowns=tuple(breakdowns),
            target_ids=tuple(
                f"{slot.target_id}#slot{slot.slot_index}" for slot in slots
            ),
            resource_ids=matrix_result.resource_ids,
            unassigned_costs=np.asarray(unassigned, dtype=float),
            target_threat_scores=tuple(
                matrix_result.target_threat_scores[slot.target_index] for slot in slots
            ),
            reject_reasons=tuple(reject_reasons),
        )

    @staticmethod
    def _resource_has_capability(resource: ResourceState, required: str) -> bool:
        capabilities = {resource.capability_class}
        extra = resource.metadata.get("capabilities", ())
        if isinstance(extra, str):
            capabilities.add(extra)
        else:
            capabilities.update(str(value) for value in extra)
        return required in capabilities

    @staticmethod
    def _coalition_member(
        slot: _DemandSlot,
        resource: ResourceState,
        executable: bool,
    ) -> CoalitionMember:
        return CoalitionMember(
            resource_id=resource.resource_id,
            member_role=slot.member_role,
            wave_id=slot.wave_id,
            arrival_window_start_s=slot.arrival_window_start_s,
            arrival_window_end_s=slot.arrival_window_end_s,
            required_capability_class=slot.required_capability_class,
            executable=executable,
        )

    def _coalition_plan(
        self,
        *,
        track: TargetTrack,
        members: tuple[CoalitionMember, ...],
        complete: bool,
        previous: CoalitionPlan | None,
        timestamp: float,
    ) -> CoalitionPlan:
        demand = track.effective_demand
        state = (
            CoalitionState.COMMITTED.value
            if complete
            else CoalitionState.INCOMPLETE.value
        )
        membership_signature = self._coalition_membership_signature(members)
        previous_signature = (
            None
            if previous is None
            else self._coalition_membership_signature(previous.members)
        )
        membership_changed = membership_signature != previous_signature
        coalition_id = (
            previous.coalition_id
            if previous is not None
            else f"d3-coalition-{track.track_id}"
        )
        coalition_version = (
            1
            if previous is None
            else previous.version + membership_changed
        )
        previous_members = () if previous is None else previous_signature
        membership_changed_at_s = (
            float(timestamp)
            if previous is None or membership_changed
            else float(previous.metadata.get("membership_changed_at_s", timestamp))
        )
        membership_change_reason = (
            "initial_membership"
            if previous is None
            else (
                "member_or_role_changed"
                if membership_changed
                else "members_held_cost_refresh"
            )
        )
        assigned = len(members)
        return CoalitionPlan(
            coalition_id=coalition_id,
            version=coalition_version,
            target_id=track.track_id,
            state=state,
            coordination_mode=demand.coordination_mode,
            required_resource_count=demand.required_resource_count,
            assigned_resource_count=assigned,
            shortfall=max(0, demand.required_resource_count - assigned),
            complete=complete,
            primary_resource_count=demand.primary_resource_count,
            members=members,
            minimum_separation_s=demand.minimum_separation_s,
            terminal_authorization_scope=demand.terminal_authorization_scope,
            arrival_coordination_required=demand.arrival_coordination_required,
            metadata={
                "primary_resource_count": demand.primary_resource_count,
                "demand_template": (
                    demand.required_resource_count,
                    demand.primary_resource_count,
                    demand.coordination_mode,
                    tuple(sorted(demand.required_capability_counts.items())),
                    demand.arrival_window_start_s,
                    demand.arrival_window_end_s,
                    demand.wave_interval_s,
                    demand.minimum_separation_s,
                    demand.terminal_authorization_scope,
                    demand.arrival_coordination_required,
                ),
                "coalition_epoch": coalition_version,
                "membership_changed_at_s": membership_changed_at_s,
                "membership_change_reason": membership_change_reason,
                "previous_members": previous_members,
                "current_members": membership_signature,
                "membership_hold_basis": (
                    "initial_admission"
                    if previous is None
                    else (
                        "hard_infeasible_or_gain_and_dwell"
                        if membership_changed
                        else "same_members_and_roles"
                    )
                ),
                "terminal_authorization_scope": demand.terminal_authorization_scope,
                "arrival_coordination_required": demand.arrival_coordination_required,
            },
        )

    @staticmethod
    def _coalition_membership_signature(
        members: tuple[CoalitionMember, ...],
    ) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((member.resource_id, member.member_role) for member in members))

    @staticmethod
    def _coalition_signature(
        *,
        demand: TargetDemand,
        state: str,
        members: tuple[CoalitionMember, ...],
    ) -> tuple[object, ...]:
        return (
            state,
            demand.required_resource_count,
            demand.primary_resource_count,
            demand.coordination_mode,
            demand.minimum_separation_s,
            tuple(
                sorted(
                    (
                        member.resource_id,
                        member.member_role,
                        member.wave_id,
                        (
                            member.arrival_window_start_s is None,
                            0.0
                            if member.arrival_window_start_s is None
                            else member.arrival_window_start_s,
                        ),
                        (
                            member.arrival_window_end_s is None,
                            0.0
                            if member.arrival_window_end_s is None
                            else member.arrival_window_end_s,
                        ),
                        member.required_capability_class or "",
                        member.executable,
                    )
                    for member in members
                )
            ),
        )

    def _build_independent_coalitions(
        self,
        target_ids: tuple[str, ...],
        assignments: tuple[Assignment, ...],
        previous_plan: AssignmentPlan | None,
        timestamp: float,
    ) -> tuple[tuple[Assignment, ...], tuple[CoalitionPlan, ...]]:
        assignment_by_target = {item.target_id: item for item in assignments}
        previous_by_target = {
            coalition.target_id: coalition
            for coalition in (() if previous_plan is None else previous_plan.coalitions)
        }
        annotated: list[Assignment] = []
        coalitions: list[CoalitionPlan] = []
        for target_id in target_ids:
            assignment = assignment_by_target.get(target_id)
            members = (
                ()
                if assignment is None
                else (
                    CoalitionMember(
                        resource_id=assignment.resource_id,
                        member_role=CoalitionMemberRole.PRIMARY.value,
                        wave_id=0,
                    ),
                )
            )
            track = TargetTrack(target_id, 0.0, 0.0, 0.0)
            coalition = self._coalition_plan(
                track=track,
                members=members,
                complete=assignment is not None,
                previous=previous_by_target.get(target_id),
                timestamp=timestamp,
            )
            coalitions.append(coalition)
            if assignment is not None:
                annotated.append(
                    replace(
                        assignment,
                        coalition_id=coalition.coalition_id,
                        coalition_version=coalition.version,
                        member_role=CoalitionMemberRole.PRIMARY.value,
                        wave_id=0,
                        required_resource_count=1,
                        terminal_authorization_scope=(
                            coalition.terminal_authorization_scope
                        ),
                        arrival_coordination_required=(
                            coalition.arrival_coordination_required
                        ),
                    )
                )
        return tuple(annotated), tuple(coalitions)

    def _apply_transient_feedback_dwell(
        self,
        *,
        candidate: AssignmentPlan,
        previous_plan: AssignmentPlan,
        matrix_result: CostMatrixResult,
        timestamp: float,
        window_id: int | None,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
    ) -> tuple[AssignmentPlan, bool]:
        """Hold a feasible primary set across short, version-matched feedback."""

        previous_primary = self._primary_resources_by_target(previous_plan)
        candidate_primary = self._primary_resources_by_target(candidate)
        changed_primary_targets = tuple(
            sorted(
                target_id
                for target_id in set(previous_primary) | set(candidate_primary)
                if previous_primary.get(target_id, frozenset())
                != candidate_primary.get(target_id, frozenset())
            )
        )
        if not changed_primary_targets:
            return candidate, False

        feedback_events = self._terminal_feedback_events(tracks)
        if not feedback_events:
            return candidate, False
        prior_records = {
            str(record.get("target_id")): record
            for record in previous_plan.metadata.get(
                "transient_feedback_dwell_records", ()
            )
            if isinstance(record, Mapping) and record.get("target_id") is not None
        }
        previous_cost, previous_feasible, previous_assignments, previous_unassigned = (
            self._score_previous_plan(previous_plan, matrix_result, candidate)
        )
        default_required = max(
            1,
            int(self.config.transient_feedback_dwell_frames),
        )
        records: list[dict[str, object]] = []
        protected_targets: list[str] = []
        released_targets: list[str] = []
        stale_feedback_count = 0
        hard_release_reasons: list[str] = []

        for target_id in changed_primary_targets:
            target_events = tuple(
                event
                for event in feedback_events
                if event.get("target_id") == target_id
            )
            current_events: list[Mapping[str, Any]] = []
            for event in target_events:
                if event.get("plan_version") != previous_plan.version:
                    stale_feedback_count += 1
                    continue
                current_events.append(event)
            if not current_events:
                continue

            hard_reasons = tuple(
                reason
                for event in current_events
                for reason in self._hard_feedback_reasons(event)
            )
            transient_events = tuple(
                event
                for event in current_events
                if self._is_transient_feedback(event)
            )
            if hard_reasons or not previous_feasible:
                released_targets.append(target_id)
                hard_release_reasons.extend(
                    hard_reasons or ("previous_assignment_infeasible",)
                )
                continue
            if not transient_events:
                continue

            prior = prior_records.get(target_id)
            prior_count = 0
            if (
                prior is not None
                and prior.get("source_plan_version") == previous_plan.version
            ):
                prior_count = max(0, int(prior.get("observed_frames", 0)))
            required_frames = max(
                (
                    max(
                        default_required,
                        self._feedback_required_frames(event, default_required),
                    )
                    for event in transient_events
                ),
                default=default_required,
            )
            observed_frames = prior_count + 1
            stable_counts = {
                str(resource_id): int(count)
                for event in transient_events
                for resource_id, count in self._feedback_stable_counts(event).items()
            }
            record = {
                "target_id": target_id,
                "source_plan_id": previous_plan.plan_id,
                "source_plan_version": previous_plan.version,
                "observed_frames": observed_frames,
                "required_frames": required_frames,
                "stable_lock_frame_count_by_resource": stable_counts,
                "reasons": tuple(
                    sorted(
                        {
                            str(event.get("reason") or event.get("terminal_feedback_state"))
                            for event in transient_events
                        }
                    )
                ),
            }
            records.append(record)
            if observed_frames < required_frames:
                protected_targets.append(target_id)
            else:
                released_targets.append(target_id)

        metadata = {
            **dict(candidate.metadata),
            "transient_feedback_dwell_enabled": True,
            "transient_feedback_dwell_frames": default_required,
            "transient_feedback_dwell_records": tuple(records),
            "transient_feedback_protected_target_ids": tuple(protected_targets),
            "transient_feedback_released_target_ids": tuple(released_targets),
            "transient_feedback_stale_event_count": stale_feedback_count,
            "transient_feedback_hard_release_reasons": tuple(
                sorted(set(hard_release_reasons))
            ),
        }
        if hard_release_reasons:
            return (
                replace(
                    candidate,
                    decision_state=(
                        "accepted_hard_feedback_release"
                        if previous_feasible
                        else "accepted_previous_infeasible"
                    ),
                    last_changed_at=timestamp,
                    metadata={
                        **metadata,
                        "transient_feedback_dwell_state": "released",
                        "transient_feedback_dwell_reason": "hard_risk",
                        "transient_feedback_protected_target_ids": (),
                    },
                ),
                True,
            )

        if protected_targets:
            held_plan = self._build_plan(
                matrix_result=matrix_result,
                solver_result=SolverResult(
                    assignments=(),
                    unassigned_target_indices=(),
                    objective_value=previous_cost,
                    solver_name=candidate.solver_name,
                    status="held",
                ),
                timestamp=timestamp,
                previous_plan=previous_plan,
                window_id=window_id,
                decision_state="held_by_transient_feedback_dwell",
                changed=False,
                last_changed_at=previous_plan.last_changed_at,
                total_cost=previous_cost,
                assignments=previous_assignments,
                unassigned_target_ids=previous_unassigned,
                coalitions=previous_plan.coalitions,
                incomplete_target_ids=previous_plan.incomplete_target_ids,
                demand_summaries=tuple(
                    coalition.summary for coalition in previous_plan.coalitions
                ),
            )
            return (
                replace(
                    held_plan,
                    candidate_total_cost=candidate.total_cost,
                    previous_total_cost_current=previous_cost,
                    metadata={
                        **dict(held_plan.metadata),
                        **metadata,
                        "transient_feedback_dwell_state": "held",
                        "transient_feedback_dwell_reason": (
                            "primary_lock_stability_incomplete"
                        ),
                        "transient_feedback_previous_feasible": previous_feasible,
                    },
                ),
                True,
            )

        if released_targets:
            return (
                replace(
                    candidate,
                    decision_state="accepted_transient_feedback_dwell_complete",
                    last_changed_at=timestamp,
                    metadata={
                        **metadata,
                        "transient_feedback_dwell_state": "released",
                        "transient_feedback_dwell_reason": (
                            "required_window_complete"
                        ),
                    },
                ),
                True,
            )

        return (
            replace(
                candidate,
                metadata={
                    **metadata,
                    "transient_feedback_dwell_state": "not_applicable",
                    "transient_feedback_dwell_reason": "no_current_transient_feedback",
                },
            ),
            False,
        )

    @staticmethod
    def _primary_resources_by_target(
        plan: AssignmentPlan,
    ) -> dict[str, frozenset[str]]:
        primary: dict[str, set[str]] = {}
        for assignment in plan.assignments:
            if assignment.member_role != CoalitionMemberRole.PRIMARY.value:
                continue
            primary.setdefault(assignment.target_id, set()).add(
                assignment.resource_id
            )
        return {
            target_id: frozenset(resource_ids)
            for target_id, resource_ids in primary.items()
        }

    @staticmethod
    def _terminal_feedback_events(
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
    ) -> tuple[Mapping[str, Any], ...]:
        events: list[Mapping[str, Any]] = []
        for track in tracks:
            raw_events = track.metadata.get("terminal_feedback_events", ())
            if isinstance(raw_events, Mapping):
                raw_events = (raw_events,)
            if not isinstance(raw_events, (tuple, list)):
                continue
            events.extend(
                event for event in raw_events if isinstance(event, Mapping)
            )
        return tuple(events)

    @staticmethod
    def _is_transient_feedback(event: Mapping[str, Any]) -> bool:
        reason = str(event.get("reason") or "").strip().lower()
        state = str(event.get("terminal_feedback_state") or "").strip().lower()
        return (
            reason in _TRANSIENT_FEEDBACK_REASONS
            or state in _TRANSIENT_FEEDBACK_STATES
        )

    @staticmethod
    def _hard_feedback_reasons(event: Mapping[str, Any]) -> tuple[str, ...]:
        reasons: list[str] = []
        state = str(event.get("terminal_feedback_state") or "").strip().lower()
        conflict = str(event.get("coalition_conflict_state") or "").strip().lower()
        friend_conflict = str(event.get("friend_conflict_state") or "").strip().lower()
        action = str(event.get("main_action") or "").strip().lower()
        if bool(event.get("duplicate_terminal_lock_risk")):
            reasons.append("duplicate_terminal_lock_risk")
        if state in _HARD_FEEDBACK_STATES:
            reasons.append(f"terminal_feedback_{state}")
        if conflict and conflict != "none":
            reasons.append(f"coalition_conflict_{conflict}")
        if friend_conflict and friend_conflict != "none":
            reasons.append(f"friend_conflict_{friend_conflict}")
        if action == "secondary_arbitration":
            reasons.append("secondary_arbitration_requested")
        if conflict in _HARD_FEEDBACK_CONFLICTS:
            reasons.append(f"hard_conflict_{conflict}")
        return tuple(dict.fromkeys(reasons))

    @staticmethod
    def _feedback_required_frames(
        event: Mapping[str, Any],
        default: int,
    ) -> int:
        raw_value = event.get("required_stable_frames")
        try:
            return default if raw_value is None else max(1, int(raw_value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _feedback_stable_counts(event: Mapping[str, Any]) -> Mapping[str, int]:
        counts = event.get("stable_lock_frame_count_by_resource")
        return counts if isinstance(counts, Mapping) else {}

    def _apply_hysteresis(
        self,
        candidate: AssignmentPlan,
        previous_plan: AssignmentPlan,
        matrix_result: CostMatrixResult,
        timestamp: float,
        window_id: int | None,
    ) -> AssignmentPlan:
        previous_cost, previous_feasible, previous_assignments, previous_unassigned = (
            self._score_previous_plan(previous_plan, matrix_result, candidate)
        )
        membership_audit = self._coalition_membership_audit(
            candidate=candidate,
            previous_plan=previous_plan,
            rescored_previous_assignments=previous_assignments,
            timestamp=timestamp,
        )
        if membership_audit["membership_hold_required"]:
            solver_result = SolverResult(
                assignments=(),
                unassigned_target_indices=(),
                objective_value=previous_cost,
                solver_name=candidate.solver_name,
                status="held",
            )
            held_plan = self._build_plan(
                matrix_result=matrix_result,
                solver_result=solver_result,
                timestamp=timestamp,
                previous_plan=previous_plan,
                window_id=window_id,
                decision_state="held_by_coalition_membership_hysteresis",
                changed=False,
                last_changed_at=previous_plan.last_changed_at,
                total_cost=previous_cost,
                assignments=previous_assignments,
                unassigned_target_ids=previous_unassigned,
                coalitions=previous_plan.coalitions,
                incomplete_target_ids=previous_plan.incomplete_target_ids,
                demand_summaries=tuple(
                    coalition.summary for coalition in previous_plan.coalitions
                ),
            )
            return replace(
                held_plan,
                candidate_total_cost=candidate.total_cost,
                previous_total_cost_current=previous_cost,
                metadata={
                    **dict(held_plan.metadata),
                    **membership_audit,
                    "hysteresis_state": "held",
                    "hysteresis_reason": "coalition_membership_hold",
                    "hysteresis_reasons": ("coalition_membership_hold",),
                },
            )
        same_assignment = candidate.stable_signature == self._assignment_signature(
            previous_assignments
        )
        dwell_time = timestamp - previous_plan.last_changed_at
        change_count = self._change_count(
            previous_plan.assignments,
            candidate.assignments,
        )
        previous_high_threat_unassigned = self._high_threat_unassigned_count(
            matrix_result,
            previous_unassigned,
        )
        candidate_high_threat_unassigned = self._high_threat_unassigned_count(
            matrix_result,
            candidate.unassigned_target_ids,
        )
        if same_assignment:
            return replace(
                candidate,
                changed=False,
                decision_state="unchanged",
                last_changed_at=previous_plan.last_changed_at,
                previous_total_cost_current=previous_cost,
                total_cost=previous_cost,
                assignments=previous_assignments,
                unassigned_target_ids=previous_unassigned,
                metadata={
                    **dict(candidate.metadata),
                    **membership_audit,
                    **self._hysteresis_metadata(
                        state="unchanged",
                        reason="same_assignment",
                        reasons=("same_assignment",),
                        dwell_time=dwell_time,
                        previous_cost=previous_cost,
                        candidate_cost=candidate.total_cost,
                        change_count=change_count,
                        improvement_ok=True,
                        dwell_ok=True,
                        change_limit_ok=True,
                        previous_feasible=previous_feasible,
                        previous_high_threat_unassigned=previous_high_threat_unassigned,
                        candidate_high_threat_unassigned=candidate_high_threat_unassigned,
                    ),
                },
            )

        improvement_ok = candidate.total_cost < (1.0 - self.config.delta) * previous_cost
        dwell_ok = dwell_time >= self.config.min_dwell
        change_limit_ok = (
            self.config.max_changes_per_window is None
            or change_count <= self.config.max_changes_per_window
        )
        high_threat_release = (
            candidate_high_threat_unassigned < previous_high_threat_unassigned
        )
        release_ok = (
            improvement_ok and dwell_ok and change_limit_ok
        ) or high_threat_release

        if previous_feasible and not release_ok:
            hold_reason = "held_by_hysteresis"
            if improvement_ok and dwell_ok and not change_limit_ok:
                hold_reason = "held_by_change_limit"
            hold_reasons = self._hold_reasons(
                improvement_ok=improvement_ok,
                dwell_ok=dwell_ok,
                change_limit_ok=change_limit_ok,
            )
            solver_result = SolverResult(
                assignments=(),
                unassigned_target_indices=(),
                objective_value=previous_cost,
                solver_name=candidate.solver_name,
                status="held",
            )
            held_plan = self._build_plan(
                matrix_result=matrix_result,
                solver_result=solver_result,
                timestamp=timestamp,
                previous_plan=previous_plan,
                window_id=window_id,
                decision_state=hold_reason,
                changed=False,
                last_changed_at=previous_plan.last_changed_at,
                total_cost=previous_cost,
                assignments=previous_assignments,
                unassigned_target_ids=previous_unassigned,
                coalitions=previous_plan.coalitions,
                incomplete_target_ids=previous_plan.incomplete_target_ids,
                demand_summaries=tuple(
                    coalition.summary for coalition in previous_plan.coalitions
                ),
            )
            return replace(
                held_plan,
                candidate_total_cost=candidate.total_cost,
                previous_total_cost_current=previous_cost,
                metadata={
                    **dict(held_plan.metadata),
                    **membership_audit,
                    **self._hysteresis_metadata(
                        state="held",
                        reason=hold_reasons[0],
                        reasons=hold_reasons,
                        dwell_time=dwell_time,
                        previous_cost=previous_cost,
                        candidate_cost=candidate.total_cost,
                        change_count=change_count,
                        improvement_ok=improvement_ok,
                        dwell_ok=dwell_ok,
                        change_limit_ok=change_limit_ok,
                        previous_feasible=previous_feasible,
                        previous_high_threat_unassigned=previous_high_threat_unassigned,
                        candidate_high_threat_unassigned=candidate_high_threat_unassigned,
                    ),
                },
            )

        reason = "accepted_previous_infeasible"
        release_reason = "previous_assignment_infeasible"
        if previous_feasible:
            if high_threat_release:
                reason = "accepted_high_threat_release"
                release_reason = "high_threat_unassigned_reduced"
            else:
                reason = "accepted_gain_and_dwell"
                release_reason = "gain_dwell_change_limit_passed"
        return replace(
            candidate,
            decision_state=reason,
            last_changed_at=timestamp,
            previous_total_cost_current=previous_cost,
            metadata={
                **dict(candidate.metadata),
                **membership_audit,
                **self._hysteresis_metadata(
                    state="released",
                    reason=release_reason,
                    reasons=(release_reason,),
                    release_reason=release_reason,
                    release_condition=reason,
                    dwell_time=dwell_time,
                    previous_cost=previous_cost,
                    candidate_cost=candidate.total_cost,
                    change_count=change_count,
                    improvement_ok=improvement_ok,
                    dwell_ok=dwell_ok,
                    change_limit_ok=change_limit_ok,
                    previous_feasible=previous_feasible,
                    previous_high_threat_unassigned=previous_high_threat_unassigned,
                    candidate_high_threat_unassigned=candidate_high_threat_unassigned,
                    high_threat_release=high_threat_release,
                ),
            },
        )

    def _coalition_membership_audit(
        self,
        *,
        candidate: AssignmentPlan,
        previous_plan: AssignmentPlan,
        rescored_previous_assignments: tuple[Assignment, ...],
        timestamp: float,
    ) -> dict[str, object]:
        """Evaluate member/role replacement per target, independently of plan refresh."""

        previous_by_target = {
            coalition.target_id: coalition for coalition in previous_plan.coalitions
        }
        candidate_by_target = {
            coalition.target_id: coalition for coalition in candidate.coalitions
        }
        previous_cost_by_target: dict[str, float] = {}
        previous_feasible_by_target: dict[str, bool] = {}
        previous_count_by_target: dict[str, int] = {}
        for assignment in rescored_previous_assignments:
            previous_cost_by_target[assignment.target_id] = (
                previous_cost_by_target.get(assignment.target_id, 0.0) + assignment.cost
            )
            previous_count_by_target[assignment.target_id] = (
                previous_count_by_target.get(assignment.target_id, 0) + 1
            )
            previous_feasible_by_target[assignment.target_id] = (
                previous_feasible_by_target.get(assignment.target_id, True)
                and assignment.feasibility_state == "feasible"
            )
        candidate_cost_by_target: dict[str, float] = {}
        for assignment in candidate.assignments:
            candidate_cost_by_target[assignment.target_id] = (
                candidate_cost_by_target.get(assignment.target_id, 0.0) + assignment.cost
            )

        records: list[dict[str, object]] = []
        hold_required = False
        changed_targets: list[str] = []
        for target_id in sorted(set(previous_by_target) | set(candidate_by_target)):
            previous = previous_by_target.get(target_id)
            current = candidate_by_target.get(target_id)
            if max(
                0 if previous is None else previous.required_resource_count,
                0 if current is None else current.required_resource_count,
            ) <= 1:
                continue
            previous_members = (
                ()
                if previous is None
                else self._coalition_membership_signature(previous.members)
            )
            current_members = (
                ()
                if current is None
                else self._coalition_membership_signature(current.members)
            )
            if previous_members == current_members:
                continue
            changed_targets.append(target_id)
            changed_at_s = (
                previous_plan.last_changed_at
                if previous is None
                else float(
                    previous.metadata.get(
                        "membership_changed_at_s", previous_plan.last_changed_at
                    )
                )
            )
            dwell_s = max(0.0, float(timestamp) - changed_at_s)
            dwell_ok = dwell_s >= self.config.min_dwell
            required = 0 if previous is None else previous.required_resource_count
            previous_feasible = (
                previous is not None
                and previous.complete
                and current is not None
                and current.required_resource_count == previous.required_resource_count
                and current.primary_resource_count == previous.primary_resource_count
                and previous_count_by_target.get(target_id, 0) == required
                and previous_feasible_by_target.get(target_id, False)
            )
            previous_target_cost = previous_cost_by_target.get(
                target_id, self.config.infeasible_penalty
            )
            candidate_target_cost = candidate_cost_by_target.get(
                target_id, self.config.infeasible_penalty
            )
            improvement_ok = candidate_target_cost < (
                (1.0 - self.config.delta) * previous_target_cost
            )
            release_reason = (
                "previous_members_hard_infeasible"
                if not previous_feasible
                else (
                    "coalition_gain_and_dwell_passed"
                    if improvement_ok and dwell_ok
                    else "coalition_membership_hold"
                )
            )
            target_hold = previous_feasible and not (improvement_ok and dwell_ok)
            hold_required = hold_required or target_hold
            records.append(
                {
                    "target_id": target_id,
                    "previous_members": previous_members,
                    "current_members": current_members,
                    "membership_changed_at_s": changed_at_s,
                    "membership_dwell_s": dwell_s,
                    "membership_min_dwell_s": self.config.min_dwell,
                    "previous_coalition_cost": previous_target_cost,
                    "candidate_coalition_cost": candidate_target_cost,
                    "required_relative_gain": self.config.delta,
                    "dwell_ok": dwell_ok,
                    "improvement_ok": improvement_ok,
                    "previous_members_feasible": previous_feasible,
                    "membership_change_reason": release_reason,
                    "membership_hold_basis": (
                        "keep_executable_members_until_gain_and_dwell"
                        if target_hold
                        else release_reason
                    ),
                }
            )
        return {
            "membership_change_reason": (
                "no_member_or_role_change"
                if not records
                else (
                    "coalition_membership_hold"
                    if hold_required
                    else "coalition_membership_released"
                )
            ),
            "membership_changed_target_ids": tuple(changed_targets),
            "membership_change_records": tuple(records),
            "membership_hold_required": hold_required,
        }

    def _score_previous_plan(
        self,
        previous_plan: AssignmentPlan,
        matrix_result: CostMatrixResult,
        candidate: AssignmentPlan,
    ) -> tuple[float, bool, tuple[Assignment, ...], tuple[str, ...]]:
        target_index = {target_id: i for i, target_id in enumerate(matrix_result.target_ids)}
        resource_index = {
            resource_id: j for j, resource_id in enumerate(matrix_result.resource_ids)
        }
        previous_by_target = previous_plan.assignments_by_target()
        candidate_coalition_by_target = {
            coalition.target_id: coalition for coalition in candidate.coalitions
        }
        previous_coalition_by_target = {
            coalition.target_id: coalition for coalition in previous_plan.coalitions
        }
        total = 0.0
        feasible = True
        assignments: list[Assignment] = []
        unassigned: list[str] = []
        used_resources: set[str] = set()

        for target_id in matrix_result.target_ids:
            target_assignments = previous_by_target.get(target_id, ())
            candidate_coalition = candidate_coalition_by_target.get(target_id)
            required = (
                candidate_coalition.required_resource_count
                if candidate_coalition is not None
                else 1
            )
            previous_coalition = previous_coalition_by_target.get(target_id)
            if not target_assignments:
                total += float(matrix_result.unassigned_costs[target_index[target_id]]) * required
                unassigned.append(target_id)
                continue
            if len(target_assignments) != required:
                feasible = False
            if (
                candidate_coalition is not None
                and previous_coalition is not None
                and (
                    candidate_coalition.required_resource_count
                    != previous_coalition.required_resource_count
                    or candidate_coalition.primary_resource_count
                    != previous_coalition.primary_resource_count
                    or candidate_coalition.coordination_mode
                    != previous_coalition.coordination_mode
                    or candidate_coalition.minimum_separation_s
                    != previous_coalition.minimum_separation_s
                    or candidate_coalition.metadata.get("demand_template")
                    != previous_coalition.metadata.get("demand_template")
                )
            ):
                feasible = False
            rescored_target: list[Assignment] = []
            for previous_assignment in target_assignments:
                resource_id = previous_assignment.resource_id
                if resource_id in used_resources:
                    feasible = False
                    total += self.config.infeasible_penalty
                    continue
                used_resources.add(resource_id)
                i = target_index.get(target_id)
                j = resource_index.get(resource_id)
                if i is None or j is None:
                    feasible = False
                    total += self.config.infeasible_penalty
                    continue
                cost = float(matrix_result.matrix[i, j])
                if cost >= self.config.infeasible_penalty * 0.5:
                    feasible = False
                total += cost
                rescored_target.append(
                    replace(
                        previous_assignment,
                        cost=cost,
                        cost_breakdown=dict(matrix_result.breakdowns[i][j]),
                        feasibility_state=(
                            "feasible"
                            if cost < self.config.infeasible_penalty * 0.5
                            else "infeasible"
                        ),
                    )
                )
            if len(rescored_target) != required:
                feasible = False
                unassigned.append(target_id)
            assignments.extend(rescored_target)

        return total, feasible, tuple(assignments), tuple(unassigned)

    def _validate_previous_plan(
        self,
        previous_plan: AssignmentPlan | None,
        expected_previous_version: int | None,
    ) -> None:
        if previous_plan is None:
            if self._latest_plan_id is None:
                return
            raise StalePlanError(
                "previous_plan is required after the planner has an active plan",
                reason="previous_plan_required",
                expected_previous_version=expected_previous_version,
                latest_plan_id=self._latest_plan_id,
                latest_version=self._latest_version,
            )
        if expected_previous_version is not None and previous_plan.version != expected_previous_version:
            raise StalePlanError(
                f"previous_plan version {previous_plan.version} does not match "
                f"expected_previous_version {expected_previous_version}",
                reason="expected_previous_version_mismatch",
                previous_plan_id=previous_plan.plan_id,
                previous_version=previous_plan.version,
                expected_previous_version=expected_previous_version,
                latest_plan_id=self._latest_plan_id,
                latest_version=self._latest_version or None,
            )
        if self._latest_version and previous_plan.version != self._latest_version:
            raise StalePlanError(
                f"previous_plan version {previous_plan.version} is stale; "
                f"latest version is {self._latest_version}",
                reason="stale_previous_version",
                previous_plan_id=previous_plan.plan_id,
                previous_version=previous_plan.version,
                expected_previous_version=expected_previous_version,
                latest_plan_id=self._latest_plan_id,
                latest_version=self._latest_version,
            )
        if self._latest_plan_id is not None and previous_plan.plan_id != self._latest_plan_id:
            raise StalePlanError(
                "previous_plan_id does not match the planner's active plan",
                reason="stale_previous_plan_id",
                previous_plan_id=previous_plan.plan_id,
                previous_version=previous_plan.version,
                expected_previous_version=expected_previous_version,
                latest_plan_id=self._latest_plan_id,
                latest_version=self._latest_version or None,
            )

    def _apply_switch_penalty_to_matrix(
        self,
        matrix_result: CostMatrixResult,
        previous_plan: AssignmentPlan | None,
    ) -> CostMatrixResult:
        penalty = float(max(0.0, self.config.reassignment_switch_penalty))
        if previous_plan is None or penalty <= 0.0:
            return matrix_result

        previous_resources_by_target = {
            target_id: {assignment.resource_id for assignment in assignments}
            for target_id, assignments in previous_plan.assignments_by_target().items()
        }
        matrix = matrix_result.matrix.copy()
        breakdown_rows = [
            [dict(breakdown) for breakdown in row]
            for row in matrix_result.breakdowns
        ]
        reject_reasons = matrix_result.reject_reasons

        for target_index, target_id in enumerate(matrix_result.target_ids):
            previous_resource_ids = previous_resources_by_target.get(target_id)
            if not previous_resource_ids:
                continue
            for resource_index, resource_id in enumerate(matrix_result.resource_ids):
                if resource_id in previous_resource_ids:
                    continue
                reject_reason = None
                if target_index < len(reject_reasons):
                    row = reject_reasons[target_index]
                    if resource_index < len(row):
                        reject_reason = row[resource_index]
                base_cost = float(matrix[target_index, resource_index])
                if (
                    reject_reason is not None
                    or base_cost >= self.config.infeasible_penalty * 0.5
                ):
                    continue

                adjusted_cost = base_cost + penalty
                matrix[target_index, resource_index] = adjusted_cost
                breakdown = breakdown_rows[target_index][resource_index]
                breakdown["reassignment_switch_penalty"] = (
                    float(breakdown.get("reassignment_switch_penalty", 0.0))
                    + penalty
                )
                breakdown["total"] = adjusted_cost

        return replace(
            matrix_result,
            matrix=matrix,
            breakdowns=tuple(
                tuple(breakdown for breakdown in row)
                for row in breakdown_rows
            ),
        )

    def _annotate_assignment_context(
        self,
        assignments: tuple[Assignment, ...],
        version: int,
    ) -> tuple[Assignment, ...]:
        annotated: list[Assignment] = []
        for assignment in assignments:
            metadata = {
                **dict(assignment.metadata),
                "source_node_id": self.config.source_node_id,
                "target_node_id": assignment.resource_id,
                "link_type": self.config.link_type,
                "plan_version": version,
                "stale_after_s": self.config.stale_after_s,
                "coalition_id": assignment.coalition_id,
                "coalition_version": assignment.coalition_version,
                "member_role": assignment.member_role,
                "wave_id": assignment.wave_id,
                "arrival_window_start_s": assignment.arrival_window_start_s,
                "arrival_window_end_s": assignment.arrival_window_end_s,
                "required_resource_count": assignment.required_resource_count,
                "terminal_authorization_scope": (
                    assignment.terminal_authorization_scope
                ),
                "arrival_coordination_required": (
                    assignment.arrival_coordination_required
                ),
                "activation_state": (
                    "standby"
                    if assignment.member_role == CoalitionMemberRole.RESERVE.value
                    else "active"
                ),
                "executable": (
                    assignment.member_role != CoalitionMemberRole.RESERVE.value
                ),
            }
            annotated.append(
                replace(
                    assignment,
                    source_node_id=self.config.source_node_id,
                    target_node_id=assignment.resource_id,
                    link_type=self.config.link_type,
                    plan_version=version,
                    stale_after_s=self.config.stale_after_s,
                    metadata=metadata,
                )
            )
        return tuple(annotated)

    def _hysteresis_metadata(
        self,
        *,
        state: str,
        reason: str,
        reasons: tuple[str, ...],
        dwell_time: float,
        previous_cost: float,
        candidate_cost: float,
        change_count: int,
        improvement_ok: bool,
        dwell_ok: bool,
        change_limit_ok: bool,
        previous_feasible: bool,
        previous_high_threat_unassigned: int,
        candidate_high_threat_unassigned: int,
        release_reason: str | None = None,
        release_condition: str | None = None,
        high_threat_release: bool = False,
    ) -> dict[str, object]:
        cost_margin = previous_cost - candidate_cost
        return {
            "hysteresis_state": state,
            "hysteresis_reason": reason,
            "hysteresis_reasons": reasons,
            "hysteresis_release_reason": release_reason,
            "hysteresis_release_condition": release_condition,
            "hysteresis_dwell_time_s": max(0.0, float(dwell_time)),
            "hysteresis_min_dwell_s": self.config.min_dwell,
            "hysteresis_delta": self.config.delta,
            "hysteresis_previous_feasible": previous_feasible,
            "hysteresis_improvement_ok": improvement_ok,
            "hysteresis_dwell_ok": dwell_ok,
            "hysteresis_change_limit_ok": change_limit_ok,
            "hysteresis_high_threat_release": high_threat_release,
            "hysteresis_previous_high_threat_unassigned_count": previous_high_threat_unassigned,
            "hysteresis_candidate_high_threat_unassigned_count": candidate_high_threat_unassigned,
            "candidate_change_count": change_count,
            "max_changes_per_window": self.config.max_changes_per_window,
            "hysteresis_candidate_change_count": change_count,
            "hysteresis_max_changes_per_window": self.config.max_changes_per_window,
            "hysteresis_previous_total_cost_current": previous_cost,
            "hysteresis_candidate_total_cost": candidate_cost,
            "hysteresis_cost_margin": cost_margin,
            "hysteresis_required_relative_gain": self.config.delta,
            "reassignment_switch_penalty": self.config.reassignment_switch_penalty,
        }

    @staticmethod
    def _hold_reasons(
        *,
        improvement_ok: bool,
        dwell_ok: bool,
        change_limit_ok: bool,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if not improvement_ok:
            reasons.append("improvement_below_delta")
        if not dwell_ok:
            reasons.append("min_dwell_not_met")
        if not change_limit_ok:
            reasons.append("change_limit_exceeded")
        return tuple(reasons) or ("held_by_hysteresis",)

    def _high_threat_unassigned_count(
        self,
        matrix_result: CostMatrixResult,
        unassigned_target_ids: tuple[str, ...],
    ) -> int:
        if not unassigned_target_ids:
            return 0
        threat_by_target = {
            target_id: threat
            for target_id, threat in zip(
                matrix_result.target_ids,
                matrix_result.target_threat_scores,
            )
        }
        return sum(
            1
            for target_id in unassigned_target_ids
            if threat_by_target.get(target_id, 0.0) >= self.config.high_threat_threshold
        )

    @staticmethod
    def _matrix_evidence_metadata(
        matrix_result: CostMatrixResult,
    ) -> dict[str, object]:
        cost_matrix = tuple(
            tuple(float(value) for value in row)
            for row in matrix_result.matrix.tolist()
        )
        edges: list[dict[str, object]] = []
        rejected_edges: list[dict[str, object]] = []
        reject_reasons = matrix_result.reject_reasons
        for target_index, target_id in enumerate(matrix_result.target_ids):
            for resource_index, resource_id in enumerate(matrix_result.resource_ids):
                reject_reason = None
                if target_index < len(reject_reasons):
                    row = reject_reasons[target_index]
                    if resource_index < len(row):
                        reject_reason = row[resource_index]
                edge = {
                    "target_id": target_id,
                    "resource_id": resource_id,
                    "cost": cost_matrix[target_index][resource_index],
                    "cost_breakdown": dict(
                        matrix_result.breakdowns[target_index][resource_index]
                    ),
                    "feasible": reject_reason is None,
                    "reject_reason": reject_reason,
                }
                edges.append(edge)
                if reject_reason is not None:
                    rejected_edges.append(edge)
        hard_reject_reasons = tuple(
            sorted(
                {
                    str(edge["reject_reason"])
                    for edge in rejected_edges
                    if edge.get("reject_reason")
                }
            )
        )
        return {
            "current_plan_evidence_schema": "d3_assignment_evidence_v1",
            "cost_matrix_target_ids": matrix_result.target_ids,
            "cost_matrix_resource_ids": matrix_result.resource_ids,
            "cost_matrix": cost_matrix,
            "current_cost_matrix": cost_matrix,
            "cost_breakdowns_by_edge": tuple(edges),
            "current_cost_breakdowns_by_edge": tuple(edges),
            "rejected_edges": tuple(rejected_edges),
            "hard_reject_count": len(rejected_edges),
            "hard_reject_reasons": hard_reject_reasons,
        }

    def _cost_weights_metadata(self) -> dict[str, float]:
        weights = self.cost_model.weights
        return {
            "window": float(weights.window),
            "covariance": float(weights.covariance),
            "threat": float(weights.threat),
            "resource_state": float(weights.resource_state),
            "fov": float(weights.fov),
            "conflict": float(weights.conflict),
        }

    def _planner_thresholds_metadata(self) -> dict[str, object]:
        return {
            "enable_hysteresis": bool(self.config.enable_hysteresis),
            "delta": float(self.config.delta),
            "min_dwell_s": float(self.config.min_dwell),
            "max_changes_per_window": self.config.max_changes_per_window,
            "reassignment_switch_penalty": float(
                self.config.reassignment_switch_penalty
            ),
            "high_threat_threshold": float(self.config.high_threat_threshold),
            "transient_feedback_dwell_frames": max(
                1,
                int(self.config.transient_feedback_dwell_frames),
            ),
            "infeasible_penalty": float(self.config.infeasible_penalty),
            "unassigned_base_cost": float(self.config.unassigned_base_cost),
        }

    @staticmethod
    def _assignment_signature(
        assignments: tuple[Assignment, ...],
    ) -> tuple[tuple[object, ...], ...]:
        return AssignmentPlan(
            plan_id="signature",
            version=0,
            window_id=0,
            assignments=assignments,
            unassigned_target_ids=(),
            total_cost=0.0,
            created_at=0.0,
            last_changed_at=0.0,
        ).stable_signature

    @classmethod
    def _change_count(
        cls,
        previous: tuple[Assignment, ...],
        candidate: tuple[Assignment, ...],
    ) -> int:
        def by_target(items: tuple[Assignment, ...]) -> dict[str, frozenset[tuple[object, ...]]]:
            grouped: dict[str, set[tuple[object, ...]]] = {}
            for signature in cls._assignment_signature(items):
                grouped.setdefault(str(signature[0]), set()).add(signature[1:])
            return {key: frozenset(value) for key, value in grouped.items()}

        previous_by_target = by_target(previous)
        candidate_by_target = by_target(candidate)
        target_ids = set(previous_by_target) | set(candidate_by_target)
        return sum(
            1
            for target_id in target_ids
            if previous_by_target.get(target_id) != candidate_by_target.get(target_id)
        )
