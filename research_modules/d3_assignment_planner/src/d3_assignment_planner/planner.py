"""Rolling assignment planner with versioning and hysteresis."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from .costs import CostMatrixResult, CostModel
from .models import (
    Assignment,
    AssignmentPlan,
    PlannerConfig,
    ResourceState,
    SolverResult,
    TargetTrack,
)
from .solver import HungarianAssignmentSolver


class StalePlanError(ValueError):
    """Raised when a rolling planner is asked to extend an obsolete plan."""


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
        self._latest_version = 0
        self._latest_plan_id: str | None = None

    def plan(
        self,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        timestamp: float,
        previous_plan: AssignmentPlan | None = None,
        window_id: int | None = None,
        expected_previous_version: int | None = None,
    ) -> AssignmentPlan:
        """Return a versioned candidate plan after applying hysteresis."""

        self._validate_previous_plan(previous_plan, expected_previous_version)
        matrix_result = self.cost_model.build_matrix(tracks, resources, timestamp)
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
            return self._remember_plan(candidate)
        if not self.config.enable_hysteresis:
            changed = candidate.assignment_map() != previous_plan.assignment_map()
            return self._remember_plan(replace(
                candidate,
                changed=changed,
                decision_state="accepted_no_hysteresis",
                last_changed_at=timestamp if changed else previous_plan.last_changed_at,
            ))
        return self._remember_plan(self._apply_hysteresis(
            candidate=candidate,
            previous_plan=previous_plan,
            matrix_result=matrix_result,
            timestamp=timestamp,
            window_id=window_id,
        ))

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
    ) -> AssignmentPlan:
        version = 1 if previous_plan is None else previous_plan.version + 1
        plan_window_id = version if window_id is None else window_id
        if assignments is None:
            assignments = self._assignments_from_solver(matrix_result, solver_result)
        assignments, switch_penalty_total = self._apply_switch_penalty(
            assignments,
            previous_plan,
        )
        assignments = self._annotate_assignment_context(assignments, version)
        if unassigned_target_ids is None:
            unassigned_target_ids = tuple(
                matrix_result.target_ids[index]
                for index in solver_result.unassigned_target_indices
            )
        computed_total_cost = solver_result.objective_value
        if total_cost is None:
            computed_total_cost += switch_penalty_total
        target_count = len(matrix_result.target_ids)
        resource_count = len(matrix_result.resource_ids)
        return AssignmentPlan(
            plan_id=f"d3-plan-{uuid4().hex[:12]}",
            version=version,
            window_id=plan_window_id,
            assignments=assignments,
            unassigned_target_ids=unassigned_target_ids,
            total_cost=computed_total_cost if total_cost is None else total_cost,
            created_at=timestamp,
            last_changed_at=timestamp if last_changed_at is None else last_changed_at,
            resource_count=resource_count,
            target_count=target_count,
            human_authorization_state="required",
            decision_state=decision_state,
            changed=changed,
            solver_name=solver_result.solver_name,
            previous_plan_id=None if previous_plan is None else previous_plan.plan_id,
            candidate_total_cost=solver_result.objective_value,
            metadata={
                "configured_human_authorization_state": self.config.human_authorization_state,
                "forced_human_authorization_state": "required",
                "source_node_id": self.config.source_node_id,
                "target_node_id": self.config.target_node_id,
                "link_type": self.config.link_type,
                "plan_version": version,
                "stale_after_s": self.config.stale_after_s,
                "resource_count": resource_count,
                "target_count": target_count,
                "assignment_matrix_shape": [target_count, resource_count],
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

    def _apply_hysteresis(
        self,
        candidate: AssignmentPlan,
        previous_plan: AssignmentPlan,
        matrix_result: CostMatrixResult,
        timestamp: float,
        window_id: int | None,
    ) -> AssignmentPlan:
        previous_cost, previous_feasible, previous_assignments, previous_unassigned = (
            self._score_previous_plan(previous_plan, matrix_result)
        )
        same_assignment = candidate.assignment_map() == {
            item.target_id: item.resource_id for item in previous_assignments
        }
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
            )

        dwell_time = timestamp - previous_plan.last_changed_at
        improvement_ok = candidate.total_cost < (1.0 - self.config.delta) * previous_cost
        dwell_ok = dwell_time > self.config.min_dwell
        change_count = self._change_count(previous_plan.assignment_map(), candidate.assignment_map())
        change_limit_ok = (
            self.config.max_changes_per_window is None
            or change_count <= self.config.max_changes_per_window
        )

        if previous_feasible and not (improvement_ok and dwell_ok and change_limit_ok):
            hold_reason = "held_by_hysteresis"
            if improvement_ok and dwell_ok and not change_limit_ok:
                hold_reason = "held_by_change_limit"
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
            )
            return replace(
                held_plan,
                candidate_total_cost=candidate.total_cost,
                previous_total_cost_current=previous_cost,
                metadata={
                    **dict(held_plan.metadata),
                    "candidate_change_count": change_count,
                    "max_changes_per_window": self.config.max_changes_per_window,
                },
            )

        reason = "accepted_previous_infeasible"
        if previous_feasible:
            reason = "accepted_gain_and_dwell"
        return replace(
            candidate,
            decision_state=reason,
            last_changed_at=timestamp,
            previous_total_cost_current=previous_cost,
            metadata={
                **dict(candidate.metadata),
                "candidate_change_count": change_count,
                "max_changes_per_window": self.config.max_changes_per_window,
            },
        )

    def _score_previous_plan(
        self,
        previous_plan: AssignmentPlan,
        matrix_result: CostMatrixResult,
    ) -> tuple[float, bool, tuple[Assignment, ...], tuple[str, ...]]:
        target_index = {target_id: i for i, target_id in enumerate(matrix_result.target_ids)}
        resource_index = {
            resource_id: j for j, resource_id in enumerate(matrix_result.resource_ids)
        }
        previous_map = previous_plan.assignment_map()
        total = 0.0
        feasible = True
        assignments: list[Assignment] = []
        unassigned: list[str] = []
        used_resources: set[str] = set()

        for target_id in matrix_result.target_ids:
            resource_id = previous_map.get(target_id)
            if resource_id is None:
                total += float(matrix_result.unassigned_costs[target_index[target_id]])
                unassigned.append(target_id)
                continue
            if resource_id in used_resources:
                feasible = False
                total += self.config.infeasible_penalty
                unassigned.append(target_id)
                continue
            used_resources.add(resource_id)
            i = target_index.get(target_id)
            j = resource_index.get(resource_id)
            if i is None or j is None:
                feasible = False
                total += self.config.infeasible_penalty
                unassigned.append(target_id)
                continue
            cost = float(matrix_result.matrix[i, j])
            if cost >= self.config.infeasible_penalty * 0.5:
                feasible = False
            total += cost
            assignments.append(
                Assignment(
                    target_id=target_id,
                    resource_id=resource_id,
                    cost=cost,
                    cost_breakdown=dict(matrix_result.breakdowns[i][j]),
                    feasibility_state=(
                        "feasible"
                        if cost < self.config.infeasible_penalty * 0.5
                        else "infeasible"
                    ),
                )
            )

        return total, feasible, tuple(assignments), tuple(unassigned)

    def _validate_previous_plan(
        self,
        previous_plan: AssignmentPlan | None,
        expected_previous_version: int | None,
    ) -> None:
        if previous_plan is None:
            return
        if expected_previous_version is not None and previous_plan.version != expected_previous_version:
            raise StalePlanError(
                f"previous_plan version {previous_plan.version} does not match "
                f"expected_previous_version {expected_previous_version}"
            )
        if self._latest_version and previous_plan.version != self._latest_version:
            raise StalePlanError(
                f"previous_plan version {previous_plan.version} is stale; "
                f"latest version is {self._latest_version}"
            )
        if self._latest_plan_id is not None and previous_plan.plan_id != self._latest_plan_id:
            raise StalePlanError("previous_plan_id does not match the planner's active plan")

    def _remember_plan(self, plan: AssignmentPlan) -> AssignmentPlan:
        self._latest_version = plan.version
        self._latest_plan_id = plan.plan_id
        return plan

    def _apply_switch_penalty(
        self,
        assignments: tuple[Assignment, ...],
        previous_plan: AssignmentPlan | None,
    ) -> tuple[tuple[Assignment, ...], float]:
        penalty = float(max(0.0, self.config.reassignment_switch_penalty))
        if previous_plan is None or penalty <= 0.0:
            return assignments, 0.0
        previous_map = previous_plan.assignment_map()
        adjusted: list[Assignment] = []
        total_penalty = 0.0
        for assignment in assignments:
            switched = previous_map.get(assignment.target_id) not in {
                None,
                assignment.resource_id,
            }
            if not switched:
                adjusted.append(assignment)
                continue
            breakdown = dict(assignment.cost_breakdown)
            breakdown["reassignment_switch_penalty"] = penalty
            breakdown["total"] = float(breakdown.get("total", assignment.cost)) + penalty
            adjusted.append(
                replace(
                    assignment,
                    cost=assignment.cost + penalty,
                    cost_breakdown=breakdown,
                )
            )
            total_penalty += penalty
        return tuple(adjusted), total_penalty

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

    @staticmethod
    def _change_count(previous_map: dict[str, str], candidate_map: dict[str, str]) -> int:
        target_ids = set(previous_map) | set(candidate_map)
        return sum(1 for target_id in target_ids if previous_map.get(target_id) != candidate_map.get(target_id))
