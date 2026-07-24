from __future__ import annotations
from commitment_test_support import committed_target_track

import numpy as np
import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    CostModel,
    PlannerConfig,
    ResourceState,
    TargetTrack,
)


def _track(index: int, *, candidate_regions: tuple[str, ...] = ("ALL",)) -> TargetTrack:
    return committed_target_track(
        track_id=f"T-{index:03d}",
        threat_score=0.2 + 0.7 * ((index % 11) / 10.0),
        covariance=0.05,
        window_cost=(index % 5) / 5.0,
        position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
        velocity_ned=(-2.0, 0.25 * (index % 3), 0.0),
        position_covariance_ned=np.eye(3) * (1.0 + index * 0.01),
        region_id="ALL",
        candidate_resource_region_ids=candidate_regions,
    )


def _resource(index: int) -> ResourceState:
    return ResourceState(
        resource_id=f"R-{(index * 7) % 211:03d}",
        health_score=0.8 + 0.01 * (index % 10),
        load_penalty=0.01 * (index % 4),
        fov_difficulty=0.02 * (index % 7),
        conflict_risk=0.01 * (index % 5),
        position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
        velocity_ned=(0.0, 0.0, 0.0),
        position_covariance_ned=np.eye(3) * 0.25,
        max_speed_mps=14.0,
        max_intercept_range_m=5_000.0,
        region_id="ALL",
        reachable_target_region_ids=("ALL",),
    )


def test_vectorized_sparse_costs_match_reference_rule_semantics() -> None:
    tracks = tuple(_track(index) for index in range(20))
    resources = tuple(_resource(index) for index in range(23))
    common = {
        "enable_candidate_sparsification": True,
        "max_candidate_edges_per_target": len(resources),
        "enforce_region_compatibility": True,
        "max_intercept_time_s": 900.0,
        "default_resource_speed_mps": 14.0,
        "reachability_time_scale_s": 300.0,
        "covariance_trace_scale": 100.0,
    }
    reference = CostModel(
        config=PlannerConfig(**common, enable_vectorized_sparse_costs=False)
    ).build_matrix(tracks, resources, timestamp=0.0)
    vectorized = CostModel(
        config=PlannerConfig(**common, enable_vectorized_sparse_costs=True)
    ).build_matrix(tracks, resources, timestamp=0.0)

    assert np.allclose(reference.matrix, vectorized.matrix, atol=1.0e-12)
    assert np.array_equal(reference.candidate_mask, vectorized.candidate_mask)
    assert reference.reject_reasons == vectorized.reject_reasons
    for target_index, resource_index in vectorized.candidate_edge_indices:
        reference_breakdown = reference.breakdowns[target_index][resource_index]
        actual_breakdown = vectorized.breakdowns[target_index][resource_index]
        assert reference_breakdown.keys() == actual_breakdown.keys()
        for key, expected in reference_breakdown.items():
            assert actual_breakdown[key] == pytest.approx(expected, abs=1.0e-11)


def test_200v200_structure_materializes_only_sparse_candidate_breakdowns() -> None:
    count = 200
    planner = AssignmentPlanner(
        config=PlannerConfig.scalable_3d(
            enable_hysteresis=False,
            max_candidate_edges_per_target=32,
            human_authorization_state="approved",
            unassigned_base_cost=50.0,
        )
    )
    plan = planner.plan(
        tuple(_track(index) for index in range(count)),
        tuple(_resource(index) for index in range(count)),
        timestamp=0.0,
    )

    assert len(plan.assignments) == count
    assert plan.metadata["candidate_edge_count"] == 6_400
    assert plan.metadata["candidate_full_edge_count"] == 40_000
    assert plan.metadata["cost_build_path"] == "vectorized_sparse_candidates"
    assert plan.metadata["python_full_pair_cost_evaluation_count"] == 0
    assert plan.metadata["vectorized_rule_pair_count"] == 40_000
    assert plan.metadata["candidate_breakdown_materialization_count"] == 6_400


def test_pair_specific_rules_use_reference_fallback_without_semantic_loss() -> None:
    track = committed_target_track(
        "T",
        threat_score=0.9,
        covariance=0.1,
        window_cost=0.0,
        fov_difficulty_by_resource={"R": 0.75},
        position_ned=(100.0, 0.0, -10.0),
        velocity_ned=(0.0, 0.0, 0.0),
        region_id="ALL",
    )
    resource = ResourceState(
        "R",
        position_ned=(0.0, 0.0, -10.0),
        max_speed_mps=10.0,
        region_id="ALL",
    )
    result = CostModel(config=PlannerConfig.scalable_3d()).build_matrix(
        (track,),
        (resource,),
        timestamp=0.0,
    )

    assert result.metadata["cost_build_path"] == "legacy_complex_constraint_fallback"
    assert result.breakdowns[0][0]["fov"] == 0.75
