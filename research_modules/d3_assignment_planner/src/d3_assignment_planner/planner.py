"""Rolling assignment planner with versioning and hysteresis."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from .costs import CostMatrixResult, CostModel
from .models import (
    ASSIGNMENT_CALIBRATION_PROFILE_SCHEMA_V1,
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
        matrix_result = self._apply_switch_penalty_to_matrix(
            matrix_result,
            previous_plan,
        )
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
                metadata={
                    **dict(candidate.metadata),
                    "hysteresis_state": "disabled",
                    "hysteresis_reason": "hysteresis_disabled",
                },
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
        target_count = len(matrix_result.target_ids)
        resource_count = len(matrix_result.resource_ids)
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
                "stale_after_s": self.config.stale_after_s,
                "resource_count": resource_count,
                "target_count": target_count,
                "assignment_matrix_shape": [target_count, resource_count],
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
        dwell_time = timestamp - previous_plan.last_changed_at
        change_count = self._change_count(previous_plan.assignment_map(), candidate.assignment_map())
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

    def _remember_plan(self, plan: AssignmentPlan) -> AssignmentPlan:
        self._latest_version = plan.version
        self._latest_plan_id = plan.plan_id
        return plan

    def _apply_switch_penalty_to_matrix(
        self,
        matrix_result: CostMatrixResult,
        previous_plan: AssignmentPlan | None,
    ) -> CostMatrixResult:
        penalty = float(max(0.0, self.config.reassignment_switch_penalty))
        if previous_plan is None or penalty <= 0.0:
            return matrix_result

        previous_map = previous_plan.assignment_map()
        matrix = matrix_result.matrix.copy()
        breakdown_rows = [
            [dict(breakdown) for breakdown in row]
            for row in matrix_result.breakdowns
        ]
        reject_reasons = matrix_result.reject_reasons

        for target_index, target_id in enumerate(matrix_result.target_ids):
            previous_resource_id = previous_map.get(target_id)
            if previous_resource_id is None:
                continue
            for resource_index, resource_id in enumerate(matrix_result.resource_ids):
                if resource_id == previous_resource_id:
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
    def _change_count(previous_map: dict[str, str], candidate_map: dict[str, str]) -> int:
        target_ids = set(previous_map) | set(candidate_map)
        return sum(1 for target_id in target_ids if previous_map.get(target_id) != candidate_map.get(target_id))
