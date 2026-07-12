"""Isolated capacity-constrained Hungarian/OR-Tools P2 benchmark."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.util import find_spec
from time import perf_counter
from typing import Any

import numpy as np

from .min_cost_flow import MinCostFlowAssignmentSolver, OrToolsUnavailableError
from .models import SolverResult
from .solver import HungarianAssignmentSolver


P2_CAPACITY_BENCHMARK_SCHEMA = "d3_p2_capacity_benchmark_v1"


@dataclass(frozen=True)
class CapacityBenchmarkProblem:
    """Shared demand-slot input for both isolated benchmark backends."""

    problem_id: str
    demand_slot_ids: tuple[str, ...]
    target_ids: tuple[str, ...]
    member_roles: tuple[str, ...]
    resource_ids: tuple[str, ...]
    resource_capacities: tuple[int, ...]
    cost_matrix: tuple[tuple[float, ...], ...]
    unassigned_costs: tuple[float, ...]

    def __post_init__(self) -> None:
        slot_count = len(self.demand_slot_ids)
        resource_count = len(self.resource_ids)
        if not self.problem_id:
            raise ValueError("problem_id must be non-empty")
        if len(set(self.demand_slot_ids)) != slot_count:
            raise ValueError("demand_slot_ids must be unique")
        if len(set(self.resource_ids)) != resource_count:
            raise ValueError("resource_ids must be unique")
        if len(self.target_ids) != slot_count or len(self.member_roles) != slot_count:
            raise ValueError("target_ids and member_roles must match demand slot count")
        if len(self.resource_capacities) != resource_count:
            raise ValueError("resource_capacities must match resource count")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in self.resource_capacities):
            raise ValueError("resource_capacities must contain integers")
        if any(value < 0 for value in self.resource_capacities):
            raise ValueError("resource_capacities must be non-negative")
        if len(self.cost_matrix) != slot_count:
            raise ValueError("cost_matrix row count must match demand slot count")
        if any(len(row) != resource_count for row in self.cost_matrix):
            raise ValueError("cost_matrix column count must match resource count")
        if len(self.unassigned_costs) != slot_count:
            raise ValueError("unassigned_costs must match demand slot count")
        values = [value for row in self.cost_matrix for value in row]
        values.extend(self.unassigned_costs)
        if not all(np.isfinite(float(value)) for value in values):
            raise ValueError("benchmark costs must be finite")

    @property
    def target_count(self) -> int:
        return len(dict.fromkeys(self.target_ids))

    @property
    def demand_slot_count(self) -> int:
        return len(self.demand_slot_ids)

    @property
    def resource_count(self) -> int:
        return len(self.resource_ids)


@dataclass(frozen=True)
class CapacityBenchmarkAssignment:
    demand_slot_id: str
    target_id: str
    member_role: str
    resource_id: str
    cost: float


@dataclass(frozen=True)
class CapacityBenchmarkOutcome:
    available: bool
    solver_name: str
    status: str
    objective_value: float | None
    elapsed_ms: float
    assignments: tuple[CapacityBenchmarkAssignment, ...] = ()
    unassigned_slot_ids: tuple[str, ...] = ()
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class CapacityBenchmarkComparison:
    schema: str
    problem_id: str
    target_count: int
    demand_slot_count: int
    resource_count: int
    resource_capacities: dict[str, int]
    hungarian: CapacityBenchmarkOutcome
    ortools_min_cost_flow: CapacityBenchmarkOutcome
    objective_delta: float | None
    objectives_match: bool | None
    online_planner_replaced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_p2_capacity_benchmark_problem() -> CapacityBenchmarkProblem:
    """Return a deterministic unequal-N/M hybrid and capacity input."""

    return CapacityBenchmarkProblem(
        problem_id="p2_4_resources_3_targets_hybrid_capacity_v1",
        demand_slot_ids=("H-P1", "H-P2", "H-R1", "M-P1", "L-P1"),
        target_ids=("HIGH", "HIGH", "HIGH", "MEDIUM", "LOW"),
        member_roles=("primary", "primary", "reserve", "primary", "primary"),
        resource_ids=("R1", "R2", "R3", "R4"),
        resource_capacities=(2, 1, 1, 1),
        cost_matrix=(
            (1.0, 8.0, 9.0, 9.0),
            (2.0, 1.0, 9.0, 9.0),
            (3.0, 4.0, 1.0, 9.0),
            (1.5, 9.0, 9.0, 1.0),
            (1.6, 9.0, 9.0, 2.0),
        ),
        unassigned_costs=(50.0, 50.0, 50.0, 50.0, 50.0),
    )


def run_p2_capacity_benchmark(
    problem: CapacityBenchmarkProblem | None = None,
) -> CapacityBenchmarkComparison:
    """Compare both backends without changing ``AssignmentPlanner`` selection."""

    shared_problem = problem or build_p2_capacity_benchmark_problem()
    hungarian = _run_hungarian(shared_problem)
    flow = _run_min_cost_flow(shared_problem)
    if hungarian.available and flow.available:
        objective_delta = float(flow.objective_value - hungarian.objective_value)  # type: ignore[operator]
        objectives_match = bool(np.isclose(objective_delta, 0.0, atol=1e-9))
    else:
        objective_delta = None
        objectives_match = None
    return CapacityBenchmarkComparison(
        schema=P2_CAPACITY_BENCHMARK_SCHEMA,
        problem_id=shared_problem.problem_id,
        target_count=shared_problem.target_count,
        demand_slot_count=shared_problem.demand_slot_count,
        resource_count=shared_problem.resource_count,
        resource_capacities=dict(
            zip(shared_problem.resource_ids, shared_problem.resource_capacities)
        ),
        hungarian=hungarian,
        ortools_min_cost_flow=flow,
        objective_delta=objective_delta,
        objectives_match=objectives_match,
    )


def _run_hungarian(problem: CapacityBenchmarkProblem) -> CapacityBenchmarkOutcome:
    started_at = perf_counter()
    if find_spec("scipy") is None:
        return _unavailable_outcome(
            "scipy_hungarian",
            "optional benchmark dependency 'scipy' is not installed",
            started_at,
        )
    expanded_resources = tuple(
        resource_index
        for resource_index, capacity in enumerate(problem.resource_capacities)
        for _ in range(capacity)
    )
    costs = np.asarray(problem.cost_matrix, dtype=float)
    expanded_costs = costs[:, expanded_resources]
    result = HungarianAssignmentSolver(allow_scipy=True).solve(
        expanded_costs,
        np.asarray(problem.unassigned_costs, dtype=float),
    )
    if result.solver_name != "scipy_hungarian":
        return _unavailable_outcome(
            "scipy_hungarian",
            "SciPy Hungarian backend could not be loaded",
            started_at,
        )
    return _decode_outcome(
        problem,
        result,
        tuple(expanded_resources[item.resource_index] for item in result.assignments),
        started_at,
    )


def _run_min_cost_flow(problem: CapacityBenchmarkProblem) -> CapacityBenchmarkOutcome:
    started_at = perf_counter()
    solver = MinCostFlowAssignmentSolver()
    try:
        result = solver.solve(
            np.asarray(problem.cost_matrix, dtype=float),
            np.asarray(problem.unassigned_costs, dtype=float),
            np.asarray(problem.resource_capacities, dtype=int),
        )
    except OrToolsUnavailableError as error:
        return _unavailable_outcome(solver.solver_name, str(error), started_at)
    return _decode_outcome(
        problem,
        result,
        tuple(item.resource_index for item in result.assignments),
        started_at,
    )


def _decode_outcome(
    problem: CapacityBenchmarkProblem,
    result: SolverResult,
    decoded_resource_indices: tuple[int, ...],
    started_at: float,
) -> CapacityBenchmarkOutcome:
    assignments = tuple(
        CapacityBenchmarkAssignment(
            demand_slot_id=problem.demand_slot_ids[item.target_index],
            target_id=problem.target_ids[item.target_index],
            member_role=problem.member_roles[item.target_index],
            resource_id=problem.resource_ids[resource_index],
            cost=item.cost,
        )
        for item, resource_index in zip(result.assignments, decoded_resource_indices)
    )
    return CapacityBenchmarkOutcome(
        available=True,
        solver_name=result.solver_name,
        status=result.status,
        objective_value=result.objective_value,
        elapsed_ms=(perf_counter() - started_at) * 1000.0,
        assignments=assignments,
        unassigned_slot_ids=tuple(
            problem.demand_slot_ids[index]
            for index in result.unassigned_target_indices
        ),
    )


def _unavailable_outcome(
    solver_name: str,
    reason: str,
    started_at: float,
) -> CapacityBenchmarkOutcome:
    return CapacityBenchmarkOutcome(
        available=False,
        solver_name=solver_name,
        status="unavailable",
        objective_value=None,
        elapsed_ms=(perf_counter() - started_at) * 1000.0,
        unavailable_reason=reason,
    )
