"""Rolling assignment planner with versioning and hysteresis."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
        if previous_plan is None:
            result = candidate
        elif not self.config.enable_hysteresis:
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
        else:
            result = self._apply_hysteresis(
                candidate=candidate,
                previous_plan=previous_plan,
                matrix_result=matrix_result,
                timestamp=timestamp,
                window_id=window_id,
            )
        result = self._finalize_identity(
            result,
            previous_plan=previous_plan,
            evaluated_at_s=timestamp,
            forced_replan=forced_replan,
            publish=publish,
        )
        if publish:
            self.publish_plan(result)
        return result

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
            if plan.execution_signature() == latest.execution_signature():
                raise ValueError(
                    "published plan identity may advance only when execution semantics change"
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
        slot_matrix_result = self._expand_demand_slot_matrix(
            slots,
            resources,
            matrix_result,
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
                        metadata={
                            "required_capability_class": slot.required_capability_class,
                            "coordination_mode": slot.demand.coordination_mode,
                            "primary_resource_count": slot.demand.primary_resource_count,
                            "minimum_separation_s": slot.demand.minimum_separation_s,
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
        return self._build_plan(
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
    ) -> CostMatrixResult:
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
    ) -> CoalitionPlan:
        demand = track.effective_demand
        state = (
            CoalitionState.COMMITTED.value
            if complete
            else CoalitionState.INCOMPLETE.value
        )
        signature = self._coalition_signature(
            demand=demand,
            state=state,
            members=members,
        )
        previous_signature = None
        if previous is not None:
            previous_demand = TargetDemand(
                required_resource_count=previous.required_resource_count,
                primary_resource_count=previous.primary_resource_count,
                coordination_mode=previous.coordination_mode,
                minimum_separation_s=previous.minimum_separation_s,
            )
            previous_signature = self._coalition_signature(
                demand=previous_demand,
                state=previous.state,
                members=previous.members,
            )
        coalition_id = (
            previous.coalition_id
            if previous is not None
            else f"d3-coalition-{track.track_id}"
        )
        coalition_version = (
            1
            if previous is None
            else previous.version + (signature != previous_signature)
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
                )
            },
        )

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
                    )
                )
        return tuple(annotated), tuple(coalitions)

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
        dwell_ok = dwell_time > self.config.min_dwell
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
