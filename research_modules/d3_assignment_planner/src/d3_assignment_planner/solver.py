"""Hungarian solvers for one-to-one and demand-slot assignment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import SolverAssignment, SolverResult


@dataclass(frozen=True)
class _PreparedProblem:
    matrix: np.ndarray
    target_count: int
    resource_count: int


def _prepare_optional_assignment(
    cost_matrix: np.ndarray,
    unassigned_costs: np.ndarray,
) -> _PreparedProblem:
    """Add dummy unassignment columns so every target can be left unassigned."""

    target_count, resource_count = cost_matrix.shape
    if len(unassigned_costs) != target_count:
        raise ValueError("unassigned_costs length must match target count")
    dummy = np.repeat(unassigned_costs.reshape(target_count, 1), target_count, axis=1)
    prepared = np.concatenate([cost_matrix, dummy], axis=1)
    return _PreparedProblem(
        matrix=prepared,
        target_count=target_count,
        resource_count=resource_count,
    )


class HungarianAssignmentSolver:
    """SciPy Hungarian solver with a deterministic fallback path."""

    def __init__(self, allow_scipy: bool = True, fallback_max_columns: int = 22) -> None:
        self.allow_scipy = allow_scipy
        self.fallback = FallbackAssignmentSolver(max_columns=fallback_max_columns)

    def solve(
        self,
        cost_matrix: np.ndarray,
        unassigned_costs: np.ndarray,
        candidate_mask: np.ndarray | None = None,
    ) -> SolverResult:
        if candidate_mask is not None:
            return self._solve_sparse_components(
                cost_matrix,
                unassigned_costs,
                candidate_mask,
            )
        return self._solve_dense(cost_matrix, unassigned_costs)

    def _solve_dense(
        self,
        cost_matrix: np.ndarray,
        unassigned_costs: np.ndarray,
    ) -> SolverResult:
        prepared = _prepare_optional_assignment(cost_matrix, unassigned_costs)
        if prepared.target_count == 0:
            return SolverResult((), (), 0.0, "hungarian", "optimal")

        if self.allow_scipy:
            try:
                from scipy.optimize import linear_sum_assignment

                row_indices, col_indices = linear_sum_assignment(prepared.matrix)
                return _decode_solution(
                    prepared,
                    tuple((int(row), int(col)) for row, col in zip(row_indices, col_indices)),
                    solver_name="scipy_hungarian",
                )
            except ImportError:
                pass

        return self.fallback.solve(cost_matrix, unassigned_costs)

    def _solve_sparse_components(
        self,
        cost_matrix: np.ndarray,
        unassigned_costs: np.ndarray,
        candidate_mask: np.ndarray,
    ) -> SolverResult:
        """Solve disconnected candidate components with local Hungarian matrices."""

        matrix = np.asarray(cost_matrix, dtype=float)
        mask = np.asarray(candidate_mask, dtype=bool)
        if matrix.ndim != 2 or mask.shape != matrix.shape:
            raise ValueError("candidate_mask shape must match cost_matrix")
        target_count, _ = matrix.shape
        if len(unassigned_costs) != target_count:
            raise ValueError("unassigned_costs length must match target count")
        if target_count == 0:
            return SolverResult((), (), 0.0, "hungarian", "optimal")

        assignments: list[SolverAssignment] = []
        unassigned: list[int] = []
        objective = 0.0
        component_solver_names: set[str] = set()
        for target_indices, resource_indices in _candidate_components(mask):
            if not resource_indices:
                for target_index in target_indices:
                    unassigned.append(target_index)
                    objective += float(unassigned_costs[target_index])
                continue
            local_matrix = matrix[np.ix_(target_indices, resource_indices)].copy()
            local_mask = mask[np.ix_(target_indices, resource_indices)]
            local_matrix[~local_mask] = np.inf
            local_unassigned = np.asarray(unassigned_costs, dtype=float)[
                list(target_indices)
            ]
            result = self._solve_dense(local_matrix, local_unassigned)
            component_solver_names.add(result.solver_name)
            objective += result.objective_value
            assignments.extend(
                SolverAssignment(
                    target_index=target_indices[item.target_index],
                    resource_index=resource_indices[item.resource_index],
                    cost=item.cost,
                )
                for item in result.assignments
            )
            unassigned.extend(
                target_indices[index]
                for index in result.unassigned_target_indices
            )
        return SolverResult(
            assignments=tuple(sorted(assignments, key=lambda item: item.target_index)),
            unassigned_target_indices=tuple(sorted(unassigned)),
            objective_value=float(objective),
            solver_name=(
                next(iter(component_solver_names))
                if len(component_solver_names) == 1
                else (
                    "scipy_hungarian"
                    if not component_solver_names and self.allow_scipy
                    else "fallback_dp"
                )
            ),
            status="optimal",
        )


class HungarianDemandSlotSolver:
    """Hungarian backend for planner-expanded role/wave demand slots."""

    solver_name = "hungarian_demand_slots"

    def __init__(self, base_solver: HungarianAssignmentSolver | None = None) -> None:
        self.base_solver = base_solver or HungarianAssignmentSolver()

    def solve(
        self,
        cost_matrix: np.ndarray,
        unassigned_costs: np.ndarray,
        candidate_mask: np.ndarray | None = None,
    ) -> SolverResult:
        result = self.base_solver.solve(
            cost_matrix,
            unassigned_costs,
            candidate_mask=candidate_mask,
        )
        return SolverResult(
            assignments=result.assignments,
            unassigned_target_indices=result.unassigned_target_indices,
            objective_value=result.objective_value,
            solver_name=self.solver_name,
            status=result.status,
        )


class FallbackAssignmentSolver:
    """Small-scale dynamic-programming fallback for optional assignment."""

    def __init__(self, max_columns: int = 22) -> None:
        self.max_columns = max_columns

    def solve(
        self,
        cost_matrix: np.ndarray,
        unassigned_costs: np.ndarray,
    ) -> SolverResult:
        prepared = _prepare_optional_assignment(cost_matrix, unassigned_costs)
        rows, cols = prepared.matrix.shape
        if rows == 0:
            return SolverResult((), (), 0.0, "fallback_dp", "optimal")
        if cols > self.max_columns:
            raise RuntimeError(
                f"Fallback solver supports at most {self.max_columns} columns; "
                f"got {cols}. Install SciPy or reduce problem size."
            )

        dp: dict[int, float] = {0: 0.0}
        parents: list[dict[int, tuple[int, int]]] = []
        for row in range(rows):
            next_dp: dict[int, float] = {}
            parent_for_row: dict[int, tuple[int, int]] = {}
            for mask, cost_so_far in dp.items():
                for col in range(cols):
                    if mask & (1 << col):
                        continue
                    next_mask = mask | (1 << col)
                    candidate = cost_so_far + float(prepared.matrix[row, col])
                    if candidate < next_dp.get(next_mask, float("inf")):
                        next_dp[next_mask] = candidate
                        parent_for_row[next_mask] = (mask, col)
            dp = next_dp
            parents.append(parent_for_row)

        best_mask = min(dp, key=dp.get)
        selected: list[tuple[int, int]] = []
        mask = best_mask
        for row in range(rows - 1, -1, -1):
            previous_mask, col = parents[row][mask]
            selected.append((row, col))
            mask = previous_mask
        selected.reverse()
        return _decode_solution(prepared, tuple(selected), solver_name="fallback_dp")


def _decode_solution(
    prepared: _PreparedProblem,
    selected: tuple[tuple[int, int], ...],
    solver_name: str,
) -> SolverResult:
    assignments: list[SolverAssignment] = []
    unassigned: list[int] = []
    objective = 0.0
    for row, col in selected:
        if row >= prepared.target_count:
            continue
        objective += float(prepared.matrix[row, col])
        if col < prepared.resource_count:
            assignments.append(
                SolverAssignment(
                    target_index=row,
                    resource_index=col,
                    cost=float(prepared.matrix[row, col]),
                )
            )
        else:
            unassigned.append(row)
    return SolverResult(
        assignments=tuple(assignments),
        unassigned_target_indices=tuple(unassigned),
        objective_value=objective,
        solver_name=solver_name,
        status="optimal",
    )


def _candidate_components(
    candidate_mask: np.ndarray,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Return deterministic connected components of a bipartite candidate graph."""

    target_count, resource_count = candidate_mask.shape
    target_neighbors = tuple(
        tuple(int(value) for value in np.flatnonzero(candidate_mask[row]))
        for row in range(target_count)
    )
    resource_neighbors: list[list[int]] = [[] for _ in range(resource_count)]
    rows, columns = np.nonzero(candidate_mask)
    for row, column in zip(rows, columns):
        resource_neighbors[int(column)].append(int(row))

    visited_targets: set[int] = set()
    visited_resources: set[int] = set()
    components: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for start in range(target_count):
        if start in visited_targets:
            continue
        pending_targets = [start]
        component_targets: set[int] = set()
        component_resources: set[int] = set()
        while pending_targets:
            target = pending_targets.pop()
            if target in component_targets:
                continue
            component_targets.add(target)
            visited_targets.add(target)
            for resource in target_neighbors[target]:
                if resource in component_resources:
                    continue
                component_resources.add(resource)
                visited_resources.add(resource)
                pending_targets.extend(resource_neighbors[resource])
        components.append(
            (
                tuple(sorted(component_targets)),
                tuple(sorted(component_resources)),
            )
        )
    return tuple(components)
