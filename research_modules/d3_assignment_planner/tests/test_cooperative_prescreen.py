from commitment_test_support import committed_target_track

from dataclasses import replace
from random import Random

import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    CooperativeCandidateObservation,
    PlannerConfig,
    ResourceState,
    StaleCooperativeCandidatePlanError,
    TargetDemand,
    TargetTrack,
    build_p1_cooperative_candidate_grid,
    demand_for_cooperative_candidate,
    export_cooperative_candidate_plan_metadata,
    rank_cooperative_candidates,
)


def _track(target_id: str, demand: TargetDemand) -> TargetTrack:
    return committed_target_track(
        track_id=target_id,
        threat_score=0.9,
        covariance=0.1,
        window_cost=0.0,
        demand=demand,
    )


def _observation(
    candidate_id: str,
    *,
    safety: int = 0,
    coalition: int = 8,
    pair: int = 18,
    spread: float = 1.0,
) -> CooperativeCandidateObservation:
    return CooperativeCandidateObservation(
        candidate_id=candidate_id,
        safety_violation_count=safety,
        coalition_completion_count=coalition,
        coalition_opportunity_count=10,
        pair_success_count=pair,
        pair_opportunity_count=20,
        arrival_spread_s=spread,
        evidence_source="main_airsim_replay",
    )


def test_candidate_grid_is_complete_stable_and_not_bound_to_m_or_n() -> None:
    first = build_p1_cooperative_candidate_grid()
    second = build_p1_cooperative_candidate_grid()

    assert len(first) == 27
    assert [item.candidate_id for item in first] == [
        item.candidate_id for item in second
    ]
    assert len({item.candidate_id for item in first}) == 27

    demand = TargetDemand(
        required_resource_count=4,
        primary_resource_count=3,
        coordination_mode="hybrid",
        wave_interval_s=4.0,
        minimum_separation_s=1.5,
    )
    configured = demand_for_cooperative_candidate(
        demand,
        first[0],
        arrival_window_start_s=12.0,
    )
    assert configured.required_resource_count == 4
    assert configured.primary_resource_count == 3
    assert configured.wave_interval_s == 4.0
    assert configured.minimum_separation_s == 1.5
    assert configured.arrival_window_end_s == (
        12.0 + first[0].primary_arrival_window_width_s
    )


def test_observed_candidate_ranking_is_stable_and_uses_fixed_precedence() -> None:
    candidates = list(build_p1_cooperative_candidate_grid()[:5])
    observations = [
        _observation(candidates[0].candidate_id, coalition=9, pair=19, spread=0.5),
        _observation(
            candidates[1].candidate_id,
            safety=1,
            coalition=10,
            pair=20,
            spread=0.1,
        ),
        _observation(candidates[2].candidate_id, coalition=9, pair=18, spread=0.2),
        _observation(candidates[3].candidate_id, coalition=9, pair=18, spread=0.8),
        _observation(candidates[4].candidate_id, coalition=8, pair=20, spread=0.1),
    ]
    expected = [
        candidates[0].candidate_id,
        candidates[2].candidate_id,
        candidates[3].candidate_id,
    ]

    first = rank_cooperative_candidates(candidates, observations)
    Random(7).shuffle(candidates)
    Random(9).shuffle(observations)
    second = rank_cooperative_candidates(candidates, observations)

    assert [item.candidate.candidate_id for item in first] == expected
    assert [item.candidate.candidate_id for item in second] == expected
    assert [item.rank for item in second] == [1, 2, 3]


def test_ranking_refuses_missing_observations_instead_of_faking_results() -> None:
    candidates = build_p1_cooperative_candidate_grid()[:2]
    with pytest.raises(ValueError, match="must match candidate IDs exactly"):
        rank_cooperative_candidates(candidates, [_observation(candidates[0].candidate_id)])


def test_dynamic_plan_export_preserves_roles_versions_and_reserve_standby() -> None:
    candidate = build_p1_cooperative_candidate_grid()[7]
    high_demand = demand_for_cooperative_candidate(
        TargetDemand(
            required_resource_count=3,
            primary_resource_count=2,
            coordination_mode="hybrid",
            wave_interval_s=4.0,
            minimum_separation_s=1.0,
        ),
        candidate,
        arrival_window_start_s=10.0,
    )
    independent = TargetDemand.independent()
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=True,
            solver_name="hungarian_demand_slots",
            human_authorization_state="approved",
        )
    )
    plan = planner.plan(
        [_track("T-HIGH", high_demand), _track("T-LOW", independent)],
        [ResourceState(f"R{index}") for index in range(1, 7)],
        timestamp=0.0,
    )

    exported = export_cooperative_candidate_plan_metadata(
        plan,
        candidate,
        current_plan_id=plan.plan_id,
        current_plan_version=plan.version,
    )
    high_members = [row for row in exported.members if row.target_id == "T-HIGH"]
    reserve = next(row for row in high_members if row.member_role == "reserve")

    assert (exported.resource_count, exported.target_count) == (6, 2)
    assert exported.candidate_parameters_match_plan is True
    assert [row.member_role for row in high_members].count("primary") == 2
    assert reserve.activation_state == "standby"
    assert reserve.wave_id == 1
    assert all(row.plan_version == plan.version for row in exported.members)
    assert all(row.coalition_version is not None for row in exported.members)

    same = planner.plan(
        [_track("T-HIGH", high_demand), _track("T-LOW", independent)],
        [ResourceState(f"R{index}") for index in range(1, 7)],
        timestamp=1.0,
        previous_plan=plan,
        expected_previous_version=plan.version,
    )
    assert same.plan_id == plan.plan_id
    assert same.version == plan.version
    assert same.changed is False
    assert same.metadata["plan_refresh_only"] is False
    assert same.metadata["evaluation_refresh_only"] is True
    assert same.coalitions[0].version == plan.coalitions[0].version


def test_candidate_export_rejects_old_plan_and_stale_coalition_version() -> None:
    candidate = build_p1_cooperative_candidate_grid()[0]
    demand = demand_for_cooperative_candidate(
        TargetDemand(), candidate, arrival_window_start_s=5.0
    )
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=False,
            solver_name="hungarian_demand_slots",
        )
    )
    plan = planner.plan(
        [_track("T", demand)],
        [ResourceState(f"R{index}") for index in range(3)],
        timestamp=0.0,
    )

    with pytest.raises(StaleCooperativeCandidatePlanError, match="current"):
        export_cooperative_candidate_plan_metadata(
            plan,
            candidate,
            current_plan_id=plan.plan_id,
            current_plan_version=plan.version + 1,
        )

    stale_assignment = replace(
        plan.assignments[0], coalition_version=plan.coalitions[0].version + 1
    )
    stale_plan = replace(
        plan,
        assignments=(stale_assignment,) + plan.assignments[1:],
    )
    with pytest.raises(StaleCooperativeCandidatePlanError, match="coalition"):
        export_cooperative_candidate_plan_metadata(
            stale_plan,
            candidate,
            current_plan_id=stale_plan.plan_id,
            current_plan_version=stale_plan.version,
        )
