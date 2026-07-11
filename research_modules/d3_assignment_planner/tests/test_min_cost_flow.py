import numpy as np
import pytest

from d3_assignment_planner.min_cost_flow import (
    MinCostFlowAssignmentSolver,
    OrToolsUnavailableError,
)


def test_min_cost_flow_optional_benchmark_has_clear_unavailable_state() -> None:
    solver = MinCostFlowAssignmentSolver()
    if solver.is_available():
        pytest.skip("OR-Tools is installed; covered by the benchmark test")
    with pytest.raises(OrToolsUnavailableError, match="benchmark unavailable"):
        solver.solve(np.zeros((1, 1)), np.ones(1))


def test_min_cost_flow_optional_benchmark_when_installed() -> None:
    solver = MinCostFlowAssignmentSolver()
    if not solver.is_available():
        pytest.skip("optional OR-Tools dependency is not installed")
    result = solver.solve(
        np.array([[0.0, 5.0], [5.0, 0.0]]),
        np.array([10.0, 10.0]),
    )
    assert result.solver_name == "ortools_min_cost_flow_benchmark"
    assert {(item.target_index, item.resource_index) for item in result.assignments} == {
        (0, 0),
        (1, 1),
    }
