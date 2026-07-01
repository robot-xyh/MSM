import numpy as np

from d3_assignment_planner.solver import FallbackAssignmentSolver, HungarianAssignmentSolver


def test_fallback_solver_allows_unassigned_targets() -> None:
    solver = FallbackAssignmentSolver()
    costs = np.array([[10.0], [1.0]])
    unassigned = np.array([2.0, 2.0])

    result = solver.solve(costs, unassigned)

    assert result.solver_name == "fallback_dp"
    assert [(item.target_index, item.resource_index) for item in result.assignments] == [
        (1, 0)
    ]
    assert result.unassigned_target_indices == (0,)
    assert result.objective_value == 3.0


def test_hungarian_can_force_fallback_without_scipy() -> None:
    solver = HungarianAssignmentSolver(allow_scipy=False)
    costs = np.array([[0.4, 4.0], [3.0, 0.2]])
    unassigned = np.array([9.0, 9.0])

    result = solver.solve(costs, unassigned)

    assert result.solver_name == "fallback_dp"
    assert {(item.target_index, item.resource_index) for item in result.assignments} == {
        (0, 0),
        (1, 1),
    }
    assert result.unassigned_target_indices == ()
    assert round(result.objective_value, 6) == 0.6


def test_hungarian_uses_scipy_when_available() -> None:
    solver = HungarianAssignmentSolver(allow_scipy=True)
    costs = np.array([[4.0, 0.5], [0.2, 4.0]])
    unassigned = np.array([9.0, 9.0])

    result = solver.solve(costs, unassigned)

    assert result.solver_name in {"scipy_hungarian", "fallback_dp"}
    assert {(item.target_index, item.resource_index) for item in result.assignments} == {
        (0, 1),
        (1, 0),
    }
