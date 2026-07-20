from __future__ import annotations

import numpy as np

from d3_assignment_planner import (
    AssignmentPlanner,
    CostModel,
    PlannerConfig,
    ResourceState,
    TargetDemand,
    TargetTrack,
)


def _track(index: int, *, region_count: int = 2, demand: TargetDemand | None = None) -> TargetTrack:
    region = f"REGION-{index % region_count}"
    return TargetTrack(
        track_id=f"T-{index:03d}",
        threat_score=0.95 if demand is not None else 0.7,
        covariance=0.05,
        window_cost=0.0,
        position_ned=(float(index * 20), float((index % region_count) * 200), -100.0),
        velocity_ned=(-2.0, 0.0, 0.0),
        position_covariance_ned=np.eye(3) * (1.0 + index * 0.01),
        region_id=region,
        demand=demand,
    )


def _resource(index: int, *, region_count: int = 2) -> ResourceState:
    region = f"REGION-{index % region_count}"
    return ResourceState(
        resource_id=f"R-{index:03d}",
        position_ned=(float(index * 20), float((index % region_count) * 200), -100.0),
        velocity_ned=(0.0, 0.0, 0.0),
        position_covariance_ned=np.eye(3) * 0.25,
        max_speed_mps=14.0,
        max_intercept_range_m=5_000.0,
        region_id=region,
    )


def _planner(*, max_edges: int = 4) -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig.scalable_3d(
            enable_hysteresis=False,
            max_candidate_edges_per_target=max_edges,
            human_authorization_state="approved",
        )
    )


def test_non_equal_three_targets_five_resources_uses_the_same_sparse_solver_path() -> None:
    plan = _planner().plan(
        [_track(index) for index in range(3)],
        [_resource(index) for index in range(5)],
        timestamp=0.0,
    )

    assert (plan.target_count, plan.resource_count, len(plan.assignments)) == (3, 5, 3)
    assert plan.unassigned_target_ids == ()
    assert plan.metadata["candidate_edge_count"] <= 12
    assert plan.solver_name in {"scipy_hungarian", "fallback_dp"}


def test_non_equal_five_targets_three_resources_leaves_two_targets_unassigned() -> None:
    plan = _planner().plan(
        [_track(index) for index in range(5)],
        [_resource(index) for index in range(3)],
        timestamp=0.0,
    )

    assert (plan.target_count, plan.resource_count, len(plan.assignments)) == (5, 3, 3)
    assert len(plan.unassigned_target_ids) == 2
    assert len(plan.assignment_by_resource()) == 3


def test_200v200_candidate_graph_is_sparse_and_keeps_a_complete_matching() -> None:
    count = 200
    plan = _planner(max_edges=4).plan(
        [_track(index, region_count=8) for index in range(count)],
        [_resource(index, region_count=8) for index in range(count)],
        timestamp=0.0,
    )

    assert (plan.target_count, plan.resource_count, len(plan.assignments)) == (
        count,
        count,
        count,
    )
    assert plan.metadata["assignment_matrix_shape"] == [count, count]
    assert plan.metadata["candidate_full_edge_count"] == 40_000
    assert plan.metadata["candidate_edge_count"] <= count * 4
    assert plan.metadata["candidate_policy_action_count"] == plan.metadata[
        "candidate_edge_count"
    ]
    assert plan.metadata["candidate_policy_action_count"] < 40_000
    assert plan.metadata["cost_matrix_storage"] == "sparse_candidate_edges"
    assert plan.metadata["cost_matrix"] == ()
    assert len(plan.metadata["cost_breakdowns_by_edge"]) <= count * 4


def test_high_threat_m_to_n_demand_retains_enough_sparse_edges_for_three_slots() -> None:
    high = _track(
        0,
        demand=TargetDemand(
            required_resource_count=3,
            primary_resource_count=2,
            coordination_mode="hybrid",
        ),
    )
    plan = _planner(max_edges=2).plan(
        [high, _track(2)],
        [_resource(index) for index in range(5)],
        timestamp=0.0,
    )

    assert plan.solver_name == "hungarian_demand_slots"
    assert len(plan.assignments_by_target()[high.track_id]) == 3
    assert plan.coalitions[0].complete is True
    assert plan.coalitions[0].primary_resource_count == 2
    assert plan.metadata["candidate_max_edges_per_target"] == 2
    assert plan.metadata["candidate_demand_slot_count"] == 4


def test_three_dimensional_reachability_covariance_and_region_are_explainable() -> None:
    config = PlannerConfig.scalable_3d(
        max_candidate_edges_per_target=4,
        max_intercept_time_s=20.0,
        covariance_trace_scale=30.0,
    )
    model = CostModel(config=config)
    track = TargetTrack(
        "T",
        threat_score=0.9,
        covariance=0.1,
        window_cost=0.0,
        position_ned=(100.0, 0.0, -120.0),
        velocity_ned=(1.0, 0.0, 0.0),
        position_covariance_ned=np.eye(3) * 4.0,
        region_id="A",
    )
    near = ResourceState(
        "NEAR",
        position_ned=(0.0, 0.0, -120.0),
        max_speed_mps=14.0,
        region_id="A",
    )
    wrong_region = ResourceState(
        "OTHER",
        position_ned=(0.0, 0.0, -120.0),
        max_speed_mps=14.0,
        region_id="B",
    )
    slow = ResourceState(
        "SLOW",
        position_ned=(0.0, 0.0, -120.0),
        max_speed_mps=1.0,
        region_id="A",
    )

    result = model.build_matrix([track], [near, wrong_region, slow], timestamp=0.0)
    breakdown = result.breakdowns[0][0]

    assert breakdown["covariance_3d_score"] == 0.4
    assert 0.0 < breakdown["intercept_time_s"] < 20.0
    assert breakdown["reachability_3d"] > 0.0
    assert result.reject_reasons[0][1] == "region_incompatible"
    assert result.reject_reasons[0][2] == "intercept_unreachable_3d"
