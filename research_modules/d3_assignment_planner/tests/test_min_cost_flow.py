import numpy as np
import pytest

from d3_assignment_planner.min_cost_flow import MinCostFlowAssignmentSolver


def test_min_cost_flow_reserved_interface_has_clear_message() -> None:
    solver = MinCostFlowAssignmentSolver()

    with pytest.raises(NotImplementedError, match="OR-Tools is not installed"):
        solver.solve(np.zeros((1, 1)), np.ones(1))
