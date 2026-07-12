from collections import Counter

import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    CapacityBenchmarkProblem,
    PlannerConfig,
    build_p2_capacity_benchmark_problem,
    run_p2_capacity_benchmark,
)
from d3_assignment_planner.min_cost_flow import MinCostFlowAssignmentSolver


def test_p2_fixture_covers_unequal_nm_hybrid_roles_and_capacity() -> None:
    problem = build_p2_capacity_benchmark_problem()

    assert (problem.resource_count, problem.target_count) == (4, 3)
    assert problem.demand_slot_count == 5
    assert Counter(problem.member_roles) == {"primary": 4, "reserve": 1}
    assert problem.resource_capacities == (2, 1, 1, 1)


def test_p2_same_input_hungarian_and_optional_flow_comparison() -> None:
    result = run_p2_capacity_benchmark()

    assert result.online_planner_replaced is False
    assert result.hungarian.available is True
    assert result.hungarian.solver_name == "scipy_hungarian"
    assert result.hungarian.objective_value == pytest.approx(5.6)
    assert result.hungarian.unassigned_slot_ids == ()
    assignment_counts = Counter(
        assignment.resource_id for assignment in result.hungarian.assignments
    )
    assert assignment_counts["R1"] == 2
    assert all(
        assignment_counts[resource_id] <= capacity
        for resource_id, capacity in result.resource_capacities.items()
    )

    flow = result.ortools_min_cost_flow
    if flow.available:
        assert flow.objective_value == pytest.approx(result.hungarian.objective_value)
        assert result.objective_delta == pytest.approx(0.0)
        assert result.objectives_match is True
    else:
        assert flow.status == "unavailable"
        assert flow.unavailable_reason
        assert "ortools" in flow.unavailable_reason.lower()
        assert result.objective_delta is None
        assert result.objectives_match is None


def test_p2_unavailable_dependency_is_structured_not_raised(monkeypatch) -> None:
    monkeypatch.setattr(
        MinCostFlowAssignmentSolver,
        "is_available",
        staticmethod(lambda: False),
    )

    result = run_p2_capacity_benchmark().to_dict()

    flow = result["ortools_min_cost_flow"]
    assert flow["available"] is False
    assert flow["status"] == "unavailable"
    assert flow["unavailable_reason"]


def test_p2_input_rejects_mismatched_capacity_shape() -> None:
    problem = build_p2_capacity_benchmark_problem()
    with pytest.raises(ValueError, match="resource_capacities"):
        CapacityBenchmarkProblem(
            problem_id=problem.problem_id,
            demand_slot_ids=problem.demand_slot_ids,
            target_ids=problem.target_ids,
            member_roles=problem.member_roles,
            resource_ids=problem.resource_ids,
            resource_capacities=(1,),
            cost_matrix=problem.cost_matrix,
            unassigned_costs=problem.unassigned_costs,
        )


def test_p2_benchmark_does_not_change_online_planner_default() -> None:
    run_p2_capacity_benchmark()

    config = PlannerConfig()
    planner = AssignmentPlanner(config=config)
    assert config.solver_name == "hungarian"
    assert planner.solver.__class__.__name__ == "HungarianAssignmentSolver"
