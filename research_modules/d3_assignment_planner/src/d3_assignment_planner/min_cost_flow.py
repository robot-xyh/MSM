"""Optional OR-Tools min-cost-flow benchmark for assignment comparisons."""

from __future__ import annotations

from importlib.util import find_spec

import numpy as np

from .models import SolverAssignment, SolverResult


class OrToolsUnavailableError(RuntimeError):
    """Raised when the optional benchmark dependency is not installed."""


class MinCostFlowAssignmentSolver:
    """OR-Tools benchmark; never selected by the default planner path."""

    solver_name = "ortools_min_cost_flow_benchmark"

    def __init__(self, cost_scale: int = 1_000) -> None:
        if cost_scale <= 0:
            raise ValueError("cost_scale must be positive")
        self.cost_scale = int(cost_scale)

    @staticmethod
    def is_available() -> bool:
        return find_spec("ortools") is not None

    def solve(
        self,
        cost_matrix: np.ndarray,
        unassigned_costs: np.ndarray,
    ) -> SolverResult:
        if not self.is_available():
            raise OrToolsUnavailableError(
                "OR-Tools benchmark unavailable; install ortools separately to run it"
            )

        from ortools.graph.python import min_cost_flow

        target_count, resource_count = cost_matrix.shape
        if len(unassigned_costs) != target_count:
            raise ValueError("unassigned_costs length must match target count")
        if target_count == 0:
            return SolverResult((), (), 0.0, self.solver_name, "optimal")

        source = 0
        target_offset = 1
        resource_offset = target_offset + target_count
        dummy_offset = resource_offset + resource_count
        sink = dummy_offset + target_count
        solver = min_cost_flow.SimpleMinCostFlow()
        real_arc_by_pair: dict[tuple[int, int], int] = {}
        dummy_arc_by_target: dict[int, int] = {}

        for target_index in range(target_count):
            target_node = target_offset + target_index
            solver.add_arc_with_capacity_and_unit_cost(source, target_node, 1, 0)
            for resource_index in range(resource_count):
                arc = solver.add_arc_with_capacity_and_unit_cost(
                    target_node,
                    resource_offset + resource_index,
                    1,
                    self._scaled(cost_matrix[target_index, resource_index]),
                )
                real_arc_by_pair[(target_index, resource_index)] = arc
            dummy_arc_by_target[target_index] = solver.add_arc_with_capacity_and_unit_cost(
                target_node,
                dummy_offset + target_index,
                1,
                self._scaled(unassigned_costs[target_index]),
            )

        for resource_index in range(resource_count):
            solver.add_arc_with_capacity_and_unit_cost(
                resource_offset + resource_index, sink, 1, 0
            )
        for target_index in range(target_count):
            solver.add_arc_with_capacity_and_unit_cost(
                dummy_offset + target_index, sink, 1, 0
            )

        solver.set_node_supply(source, target_count)
        solver.set_node_supply(sink, -target_count)
        status = solver.solve()
        if status != solver.OPTIMAL:
            raise RuntimeError(f"OR-Tools min-cost-flow benchmark failed: status={status}")

        assignments: list[SolverAssignment] = []
        unassigned: list[int] = []
        objective = 0.0
        for (target_index, resource_index), arc in real_arc_by_pair.items():
            if solver.flow(arc) != 1:
                continue
            cost = float(cost_matrix[target_index, resource_index])
            objective += cost
            assignments.append(SolverAssignment(target_index, resource_index, cost))
        for target_index, arc in dummy_arc_by_target.items():
            if solver.flow(arc) == 1:
                objective += float(unassigned_costs[target_index])
                unassigned.append(target_index)

        return SolverResult(
            assignments=tuple(assignments),
            unassigned_target_indices=tuple(unassigned),
            objective_value=objective,
            solver_name=self.solver_name,
            status="optimal",
        )

    def _scaled(self, value: float) -> int:
        return int(round(float(value) * self.cost_scale))
