from dataclasses import replace

import pytest

from d3_assignment_planner import (
    Assignment,
    AssignmentPlan,
    AssignmentPlanner,
    CoalitionMember,
    CoalitionPlan,
    PlannerConfig,
    ResourceState,
    TargetDemand,
    TargetTrack,
    assignment_validity_summary_from_plan,
    guidance_bindings_from_assignment_plan,
)


def _track(
    target_id: str,
    threat: float = 0.9,
    demand: TargetDemand | None = None,
    **kwargs: object,
) -> TargetTrack:
    return TargetTrack(
        target_id,
        threat_score=threat,
        covariance=0.0,
        window_cost=0.0,
        demand=demand,
        **kwargs,
    )


def _planner(*, hysteresis: bool = False, authorization: str = "approved") -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=hysteresis,
            solver_name="hungarian_demand_slots",
            human_authorization_state=authorization,
        )
    )


def test_k1_default_remains_independent_and_legacy_map_compatible() -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    plan = planner.plan([_track("T1")], [ResourceState("R1")], timestamp=0.0)

    assert plan.assignment_map() == {"T1": "R1"}
    assert plan.solver_name in {"scipy_hungarian", "fallback_dp"}
    assert plan.coalitions[0].coordination_mode == "independent"
    assert plan.demand_summaries[0].demand_required == 1
    assert plan.demand_summaries[0].coalition_complete is True


def test_three_to_one_default_explicit_demand_builds_hybrid_two_plus_one() -> None:
    plan = _planner().plan(
        [_track("HIGH", demand=TargetDemand(arrival_window_start_s=10.0, arrival_window_end_s=12.0, wave_interval_s=5.0, minimum_separation_s=2.0))],
        [ResourceState(f"R{i}") for i in range(1, 4)],
        timestamp=0.0,
    )

    assert plan.solver_name == "hungarian_demand_slots"
    assert len(plan.assignments) == 3
    assert [item.member_role for item in plan.assignments].count("primary") == 2
    assert [item.member_role for item in plan.assignments].count("reserve") == 1
    assert {item.wave_id for item in plan.assignments if item.member_role == "primary"} == {0}
    reserve = next(item for item in plan.assignments if item.member_role == "reserve")
    assert (reserve.wave_id, reserve.arrival_window_start_s, reserve.arrival_window_end_s) == (1, 15.0, 17.0)
    assert plan.coalitions[0].state == "committed"
    assert plan.coalitions[0].minimum_separation_s == 2.0
    assert plan.demand_summaries[0].demand_shortfall == 0
    with pytest.raises(ValueError, match="only valid for one-to-one"):
        plan.assignment_map()

    bindings = guidance_bindings_from_assignment_plan(plan)
    assert len(bindings) == 3
    assert all(binding.binding_state == "active" for binding in bindings)
    assert {binding.coordination_mode for binding in bindings} == {"hybrid"}
    assert {binding.minimum_separation_s for binding in bindings} == {2.0}


def test_hybrid_k4_uses_configured_three_primary_plus_one_reserve() -> None:
    plan = _planner().plan(
        [
            _track(
                "HIGH",
                demand=TargetDemand(
                    required_resource_count=4,
                    primary_resource_count=3,
                    coordination_mode="hybrid",
                ),
            )
        ],
        [ResourceState(f"R{i}") for i in range(1, 5)],
        timestamp=0.0,
    )

    assert plan.coalitions[0].primary_resource_count == 3
    assert plan.coalitions[0].summary.primary_resource_count == 3
    assert plan.metadata["demand_summaries"][0]["primary_resource_count"] == 3
    assert [item.member_role for item in plan.assignments].count("primary") == 3
    assert [item.member_role for item in plan.assignments].count("reserve") == 1
    assert {item.wave_id for item in plan.assignments if item.member_role == "primary"} == {0}
    assert {item.wave_id for item in plan.assignments if item.member_role == "reserve"} == {1}
    bindings = guidance_bindings_from_assignment_plan(plan)
    assert {binding.primary_resource_count for binding in bindings} == {3}
    assert {binding.metadata["primary_resource_count"] for binding in bindings} == {3}


def test_primary_resource_count_validation_and_independent_default() -> None:
    with pytest.raises(ValueError, match="primary_resource_count"):
        TargetDemand(primary_resource_count=0)
    with pytest.raises(ValueError, match="primary_resource_count"):
        TargetDemand(required_resource_count=3, primary_resource_count=4)

    fallback = _track("T").effective_demand
    explicit = TargetDemand.independent()
    assert (fallback.required_resource_count, fallback.primary_resource_count) == (1, 1)
    assert (explicit.required_resource_count, explicit.primary_resource_count) == (1, 1)


def test_two_resources_cannot_publish_partial_k3_coalition() -> None:
    plan = _planner().plan(
        [_track("HIGH", demand=TargetDemand())],
        [ResourceState("R1"), ResourceState("R2")],
        timestamp=0.0,
    )

    assert plan.assignments == ()
    assert plan.unassigned_target_ids == ("HIGH",)
    assert plan.incomplete_target_ids == ("HIGH",)
    coalition = plan.coalitions[0]
    assert coalition.state == "incomplete"
    assert coalition.assigned_resource_count == 2
    assert coalition.shortfall == 1
    assert all(member.executable is False for member in coalition.members)
    assert guidance_bindings_from_assignment_plan(plan) == ()


def test_five_resources_admit_k3_high_threat_and_k1_target() -> None:
    plan = _planner().plan(
        [
            _track("HIGH", threat=0.99, demand=TargetDemand()),
            _track("LOW", threat=0.2),
        ],
        [ResourceState(f"R{i}") for i in range(1, 6)],
        timestamp=0.0,
    )

    assert {key: len(value) for key, value in plan.assignments_by_target().items()} == {
        "HIGH": 3,
        "LOW": 1,
    }
    assert len(plan.assignment_by_resource()) == 4
    assert plan.incomplete_target_ids == ()
    assert all(summary.coalition_complete for summary in plan.demand_summaries)


def test_capability_slots_admit_matching_roles_and_reject_shortfall() -> None:
    demand = TargetDemand(
        required_capability_counts={"interceptor": 2, "sensor": 1}
    )
    resources = [
        ResourceState("I1", capability_class="interceptor"),
        ResourceState("I2", capability_class="interceptor"),
        ResourceState("S1", capability_class="sensor"),
    ]
    complete = _planner().plan([_track("HIGH", demand=demand)], resources, timestamp=0.0)

    required_by_resource = {
        item.resource_id: item.metadata["required_capability_class"]
        for item in complete.assignments
    }
    assert required_by_resource == {"I1": "interceptor", "I2": "interceptor", "S1": "sensor"}

    incomplete = _planner().plan(
        [_track("HIGH", demand=demand)],
        resources[:2] + [ResourceState("G1", capability_class="generic")],
        timestamp=0.0,
    )
    assert incomplete.assignments == ()
    assert incomplete.coalitions[0].assigned_resource_count == 2
    assert incomplete.coalitions[0].shortfall == 1


@pytest.mark.parametrize(
    ("mode", "expected_roles", "expected_waves"),
    [
        ("simultaneous", ["primary", "primary", "primary"], [0, 0, 0]),
        ("sequential", ["primary", "retry", "retry"], [0, 1, 2]),
        ("hybrid", ["primary", "primary", "reserve"], [0, 0, 1]),
    ],
)
def test_coordination_mode_role_and_wave_contract(
    mode: str,
    expected_roles: list[str],
    expected_waves: list[int],
) -> None:
    plan = _planner().plan(
        [_track("T", demand=TargetDemand(coordination_mode=mode))],
        [ResourceState(f"R{i}") for i in range(3)],
        timestamp=0.0,
    )
    ordered = sorted(plan.assignments, key=lambda item: (item.wave_id, item.member_role, item.resource_id))
    assert sorted(item.member_role for item in ordered) == sorted(expected_roles)
    assert sorted(item.wave_id for item in ordered) == sorted(expected_waves)


def test_member_window_change_increments_coalition_version_and_stales_old_binding() -> None:
    planner = _planner(hysteresis=True)
    resources = [ResourceState(f"R{i}") for i in range(3)]
    first = planner.plan(
        [_track("T", demand=TargetDemand(arrival_window_start_s=10.0, arrival_window_end_s=12.0))],
        resources,
        timestamp=0.0,
    )
    second = planner.plan(
        [_track("T", demand=TargetDemand(arrival_window_start_s=20.0, arrival_window_end_s=22.0))],
        resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert second.coalitions[0].coalition_id == first.coalitions[0].coalition_id
    assert second.coalitions[0].version == first.coalitions[0].version + 1
    assert second.decision_state == "accepted_previous_infeasible"
    assert second.stable_signature != first.stable_signature
    old = guidance_bindings_from_assignment_plan(
        first,
        current_plan_id=second.plan_id,
        current_plan_version=second.version,
    )
    assert all(binding.binding_state == "stale" for binding in old)
    assert all(binding.revoke_reason == "not_current_assignment_plan" for binding in old)


def test_primary_count_change_increments_coalition_version() -> None:
    planner = _planner(hysteresis=True)
    resources = [ResourceState(f"R{i}") for i in range(4)]
    first = planner.plan(
        [
            _track(
                "T",
                demand=TargetDemand(
                    required_resource_count=4,
                    primary_resource_count=2,
                ),
            )
        ],
        resources,
        timestamp=0.0,
    )
    second = planner.plan(
        [
            _track(
                "T",
                demand=TargetDemand(
                    required_resource_count=4,
                    primary_resource_count=3,
                ),
            )
        ],
        resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert second.coalitions[0].coalition_id == first.coalitions[0].coalition_id
    assert second.coalitions[0].version == first.coalitions[0].version + 1
    assert second.coalitions[0].primary_resource_count == 3
    assert second.decision_state == "accepted_previous_infeasible"
    assert second.stable_signature != first.stable_signature


def test_legal_multiplicity_is_not_duplicate_but_excess_and_resource_conflict_are() -> None:
    legal = _planner().plan(
        [_track("T", demand=TargetDemand())],
        [ResourceState(f"R{i}") for i in range(3)],
        timestamp=0.0,
    )
    legal_summary = assignment_validity_summary_from_plan(legal, evaluated_at=0.0)
    assert legal_summary.duplicate_assignment_count == 0

    coalition = legal.coalitions[0]
    excess_assignment = replace(
        legal.assignments[0],
        resource_id="R4",
    )
    conflicting_assignment = Assignment(
        target_id="OTHER",
        resource_id=legal.assignments[0].resource_id,
        cost=1.0,
        cost_breakdown={"total": 1.0},
    )
    invalid = replace(
        legal,
        assignments=legal.assignments + (excess_assignment, conflicting_assignment),
        coalitions=(coalition,),
    )
    invalid_summary = assignment_validity_summary_from_plan(invalid, evaluated_at=0.0)
    assert invalid_summary.duplicate_assignment_count == 2


def test_stale_or_unauthorized_assignment_is_counted_as_duplicate_anomaly() -> None:
    plan = AssignmentPlan(
        plan_id="manual",
        version=1,
        window_id=1,
        assignments=(
            Assignment("T", "R", 1.0, {"total": 1.0}, feasibility_state="stale"),
        ),
        unassigned_target_ids=(),
        total_cost=1.0,
        created_at=0.0,
        last_changed_at=0.0,
    )
    summary = assignment_validity_summary_from_plan(plan, evaluated_at=0.0)
    assert summary.duplicate_assignment_count == 1


def test_manual_non_committed_coalition_binding_is_held() -> None:
    assignment = Assignment(
        "T",
        "R",
        1.0,
        {"total": 1.0},
        coalition_id="C",
        coalition_version=2,
        required_resource_count=2,
    )
    coalition = CoalitionPlan(
        coalition_id="C",
        version=2,
        target_id="T",
        state="incomplete",
        coordination_mode="simultaneous",
        required_resource_count=2,
        assigned_resource_count=1,
        shortfall=1,
        complete=False,
        members=(CoalitionMember("R", "primary", 0, executable=False),),
    )
    plan = AssignmentPlan(
        plan_id="manual",
        version=1,
        window_id=1,
        assignments=(assignment,),
        unassigned_target_ids=("T",),
        total_cost=1.0,
        created_at=0.0,
        last_changed_at=0.0,
        human_authorization_state="approved",
        coalitions=(coalition,),
        incomplete_target_ids=("T",),
    )
    (binding,) = guidance_bindings_from_assignment_plan(plan)
    assert binding.binding_state == "hold"
    assert binding.revoke_reason == "coalition_not_committed"
