from d3_assignment_planner import (
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    TargetDemand,
    TargetTrack,
    assignment_records_from_plan,
)


def _planner() -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=True,
            solver_name="hungarian_demand_slots",
            delta=0.2,
            min_dwell=2.0,
            human_authorization_state="approved",
        )
    )


def _track(costs: dict[str, float]) -> TargetTrack:
    return TargetTrack(
        "HIGH",
        threat_score=0.95,
        covariance=0.0,
        window_cost=0.0,
        demand=TargetDemand(),
        fov_difficulty_by_resource=costs,
    )


def _members(plan: object) -> tuple[tuple[str, str], ...]:
    coalition = plan.coalitions[0]
    return tuple(sorted((member.resource_id, member.member_role) for member in coalition.members))


def test_executable_members_hold_until_gain_and_dwell_pass() -> None:
    planner = _planner()
    resources = [ResourceState(f"R{i}") for i in range(1, 5)]
    first = planner.plan(
        [_track({"R1": 0.0, "R2": 0.1, "R3": 0.2, "R4": 5.0})],
        resources,
        timestamp=0.0,
    )
    held = planner.plan(
        [_track({"R1": 2.0, "R2": 0.1, "R3": 0.2, "R4": 0.0})],
        resources,
        timestamp=1.0,
        previous_plan=first,
    )
    released = planner.plan(
        [_track({"R1": 2.0, "R2": 0.1, "R3": 0.2, "R4": 0.0})],
        resources,
        timestamp=2.0,
        previous_plan=held,
    )

    assert _members(held) == _members(first)
    assert held.decision_state == "held_by_coalition_membership_hysteresis"
    assert held.metadata["membership_hold_required"] is True
    assert _members(released) != _members(first)
    assert released.decision_state == "accepted_gain_and_dwell"
    assert released.coalitions[0].version == first.coalitions[0].version + 1
    assert released.coalitions[0].epoch == released.coalitions[0].version
    record = released.metadata["membership_change_records"][0]
    assert record["dwell_ok"] is True
    assert record["improvement_ok"] is True
    assert record["membership_change_reason"] == "coalition_gain_and_dwell_passed"


def test_hard_infeasible_member_releases_inside_dwell() -> None:
    planner = _planner()
    resources = [ResourceState(f"R{i}") for i in range(1, 5)]
    first = planner.plan(
        [_track({"R1": 0.0, "R2": 0.1, "R3": 0.2, "R4": 5.0})],
        resources,
        timestamp=0.0,
    )
    failed_id = first.coalitions[0].members[0].resource_id
    failed_resources = [
        ResourceState(resource.resource_id, status=(
            "unavailable" if resource.resource_id == failed_id else "available"
        ))
        for resource in resources
    ]
    changed = planner.plan(
        [_track({"R1": 0.0, "R2": 0.1, "R3": 0.2, "R4": 0.3})],
        failed_resources,
        timestamp=0.5,
        previous_plan=first,
    )

    assert failed_id not in {member.resource_id for member in changed.coalitions[0].members}
    assert changed.decision_state == "accepted_previous_infeasible"
    assert changed.metadata["membership_hold_required"] is False
    assert changed.metadata["membership_change_records"][0][
        "membership_change_reason"
    ] == "previous_members_hard_infeasible"


def test_cost_evaluation_refresh_keeps_plan_and_membership_epoch() -> None:
    planner = _planner()
    resources = [ResourceState(f"R{i}") for i in range(1, 4)]
    first = planner.plan(
        [_track({"R1": 0.0, "R2": 0.1, "R3": 0.2})],
        resources,
        timestamp=0.0,
    )
    refreshed = planner.plan(
        [_track({"R1": 0.05, "R2": 0.15, "R3": 0.25})],
        resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert refreshed.version == first.version
    assert refreshed.plan_id == first.plan_id
    assert refreshed.changed is False
    assert refreshed.metadata["plan_refresh_only"] is False
    assert refreshed.metadata["evaluation_refresh_only"] is True
    assert all(
        assignment.metadata["evaluation_refresh_only"] is True
        for assignment in refreshed.assignments
    )
    assert _members(refreshed) == _members(first)
    assert refreshed.coalitions[0].version == first.coalitions[0].version
    assert refreshed.coalitions[0].metadata["membership_changed_at_s"] == 0.0
    records = assignment_records_from_plan(refreshed, previous_plan=first)
    assert {record.plan_churn_count for record in records} == {0}
    assert {record.plan_rollback_detected for record in records} == {False}
    assert {record.version for record in records} == {first.version}
    assert {record.coalition_epoch for record in records} == {
        first.coalitions[0].epoch
    }
