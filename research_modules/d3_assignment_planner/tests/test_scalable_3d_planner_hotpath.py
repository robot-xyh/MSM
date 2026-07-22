from __future__ import annotations

import numpy as np
import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    TargetDemand,
    TargetTrack,
)
from d3_assignment_planner import planning_evidence


def _tracks(
    count: int,
    *,
    demand_by_index: dict[int, TargetDemand] | None = None,
) -> tuple[TargetTrack, ...]:
    demands = demand_by_index or {}
    return tuple(
        TargetTrack(
            track_id=f"T-{index:03d}",
            threat_score=0.95 if index in demands else 0.7,
            covariance=0.05,
            window_cost=0.0,
            position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
            velocity_ned=(-2.0, 0.0, 0.0),
            position_covariance_ned=np.eye(3) * (1.0 + index * 0.01),
            region_id="ALL",
            candidate_resource_region_ids=("ALL",),
            demand=demands.get(index),
        )
        for index in range(count)
    )


def _resources(count: int) -> tuple[ResourceState, ...]:
    return tuple(
        ResourceState(
            resource_id=f"R-{index:03d}",
            position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
            velocity_ned=(0.0, 0.0, 0.0),
            position_covariance_ned=np.eye(3) * 0.25,
            max_speed_mps=14.0,
            max_intercept_range_m=5_000.0,
            region_id="ALL",
            reachable_target_region_ids=("ALL",),
        )
        for index in range(count)
    )


def _planner(*, max_edges: int = 32) -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig.scalable_3d(
            max_candidate_edges_per_target=max_edges,
            human_authorization_state="approved",
            unassigned_base_cost=50.0,
        )
    )


@pytest.mark.parametrize(
    ("target_count", "resource_count", "assigned_count"),
    ((3, 5, 3), (5, 3, 3)),
)
def test_sparse_hotpath_preserves_non_equal_roster_semantics(
    target_count: int,
    resource_count: int,
    assigned_count: int,
) -> None:
    plan = _planner(max_edges=4).plan(
        _tracks(target_count),
        _resources(resource_count),
        timestamp=0.0,
    )

    assert (plan.target_count, plan.resource_count) == (
        target_count,
        resource_count,
    )
    assert len(plan.assignments) == assigned_count
    assert len(plan.assignment_by_resource()) == assigned_count
    assert len(plan.unassigned_target_ids) == target_count - assigned_count
    assert plan.metadata["cost_build_path"] == "vectorized_sparse_candidates"
    assert plan.metadata["candidate_edge_count"] <= target_count * 4


def test_200v200_snapshot_sanitizes_unique_sparse_breakdowns_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe_breakdown_calls = 0
    original = planning_evidence._safe_cost_breakdown

    def counted(value, *, safe_key_cache=None):
        nonlocal safe_breakdown_calls
        safe_breakdown_calls += 1
        return original(value, safe_key_cache=safe_key_cache)

    monkeypatch.setattr(planning_evidence, "_safe_cost_breakdown", counted)
    planner = _planner(max_edges=32)
    plan = planner.plan(_tracks(200), _resources(200), timestamp=0.0)
    evidence = planner.latest_planning_evidence

    candidate_count = int(plan.metadata["candidate_edge_count"])
    assert plan.metadata["candidate_full_edge_count"] == 40_000
    assert candidate_count == 6_400
    assert plan.metadata["candidate_breakdown_materialization_count"] == 6_400
    assert safe_breakdown_calls <= candidate_count + len(plan.assignments) + 16
    assert safe_breakdown_calls < plan.metadata["candidate_full_edge_count"]
    assert evidence.available is True
    assert evidence.rule_matrix is not evidence.effective_matrix
    assert np.array_equal(evidence.rule_matrix, evidence.effective_matrix)
    assert (
        evidence.rule_matrix_result.breakdowns
        is evidence.effective_matrix_result.breakdowns
    )
    with pytest.raises(TypeError):
        evidence.rule_matrix_result.breakdowns[0][0]["total"] = -1.0


def test_m_to_n_demand_slots_keep_roles_capacity_and_sparse_operation_counts() -> None:
    demand = TargetDemand(
        required_resource_count=3,
        primary_resource_count=2,
        coordination_mode="hybrid",
    )
    plan = _planner(max_edges=2).plan(
        _tracks(2, demand_by_index={0: demand}),
        _resources(5),
        timestamp=0.0,
    )

    assigned = plan.assignments_by_target()["T-000"]
    assert len(assigned) == 3
    assert sum(item.member_role == "primary" for item in assigned) == 2
    assert sum(item.member_role == "reserve" for item in assigned) == 1
    assert len(plan.assignment_by_resource()) == len(plan.assignments)
    assert plan.solver_name == "hungarian_demand_slots"
    assert plan.metadata["candidate_demand_slot_count"] == 4
    # The sparse row limit expands to the target's required demand so three
    # coalition slots can still be filled: 3 edges for T-000 plus 2 for T-001.
    assert plan.metadata["candidate_edge_count"] == 5


def test_previous_plan_cycle_reuses_sparse_snapshot_without_semantic_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner = _planner(max_edges=32)
    tracks = _tracks(200)
    resources = _resources(200)
    first = planner.plan(tracks, resources, timestamp=0.0)
    first_signature = first.stable_signature

    safe_breakdown_calls = 0
    original = planning_evidence._safe_cost_breakdown

    def counted(value, *, safe_key_cache=None):
        nonlocal safe_breakdown_calls
        safe_breakdown_calls += 1
        return original(value, safe_key_cache=safe_key_cache)

    monkeypatch.setattr(planning_evidence, "_safe_cost_breakdown", counted)
    second = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=first,
        expected_previous_version=first.version,
    )

    candidate_count = int(second.metadata["candidate_edge_count"])
    assert second.stable_signature == first_signature
    assert second.decision_state == "unchanged"
    assert second.version == first.version
    assert second.plan_id == first.plan_id
    assert second.metadata["hysteresis_reason"] == "same_assignment"
    assert safe_breakdown_calls <= candidate_count + 2 * len(second.assignments) + 16
    assert safe_breakdown_calls < second.metadata["candidate_full_edge_count"]
    assert planner.latest_planning_evidence.previous_plan_version == first.version
