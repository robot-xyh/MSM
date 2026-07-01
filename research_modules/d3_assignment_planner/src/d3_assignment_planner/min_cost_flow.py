"""Reserved min-cost-flow interface for future OR-Tools integration."""

from __future__ import annotations

import numpy as np

from .models import SolverResult


class MinCostFlowAssignmentSolver:
    """Placeholder preserving the solver boundary without importing OR-Tools."""

    solver_name = "min_cost_flow_reserved"

    def solve(
        self,
        cost_matrix: np.ndarray,
        unassigned_costs: np.ndarray,
    ) -> SolverResult:
        raise NotImplementedError(
            "OR-Tools is not installed in this environment. The min-cost-flow "
            "solver is reserved for future capacity, demand, and multi-window "
            "constraints; use HungarianAssignmentSolver for current tests."
        )
