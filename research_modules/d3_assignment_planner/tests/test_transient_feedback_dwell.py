from d3_assignment_planner import (
    AssignmentPlan,
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    TargetDemand,
    TargetTrack,
    apply_terminal_feedback_to_planner_inputs,
)


def _resources() -> tuple[ResourceState, ...]:
    return tuple(
        ResourceState(
            f"INT-0{index}",
            capability_class=(
                "shooter"
                if index in {1, 2, 4}
                else "scout"
                if index == 3
                else "generic"
            ),
        )
        for index in range(1, 6)
    )


def _tracks(*, switch_primary: bool) -> tuple[TargetTrack, ...]:
    t001_fov = (
        (1.0, 0.1, 0.2, 0.0, 1.0)
        if switch_primary
        else (0.0, 0.1, 0.2, 0.8, 1.0)
    )
    resource_ids = tuple(f"INT-0{index}" for index in range(1, 6))
    return (
        TargetTrack(
            "T001",
            threat_score=0.95,
            covariance=0.1,
            window_cost=0.1,
            demand=TargetDemand(
                required_resource_count=3,
                primary_resource_count=2,
                coordination_mode="hybrid",
                required_capability_counts={"shooter": 2},
            ),
            feasibility_by_resource={
                resource_id: resource_id != "INT-05"
                for resource_id in resource_ids
            },
            fov_difficulty_by_resource=dict(zip(resource_ids, t001_fov)),
        ),
        TargetTrack(
            "T002",
            threat_score=0.5,
            covariance=0.1,
            window_cost=0.1,
            feasibility_by_resource={
                resource_id: resource_id == "INT-05"
                for resource_id in resource_ids
            },
        ),
    )


def _planner() -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=True,
            min_dwell=100.0,
            solver_name="hungarian_demand_slots",
            transient_feedback_dwell_frames=2,
        )
    )


def _primary_ids(plan: AssignmentPlan, target_id: str = "T001") -> set[str]:
    return {
        assignment.resource_id
        for assignment in plan.assignments_by_target()[target_id]
        if assignment.member_role == "primary"
    }


def _stability_feedback(plan: AssignmentPlan) -> dict[str, object]:
    primary_ids = _primary_ids(plan)
    return {
        "target_id": "T001",
        "plan_version": plan.version,
        "coalition_visual_reason": "primary_lock_stability_incomplete",
        "stable_lock_frame_count_by_resource": {
            resource_id: 1 for resource_id in primary_ids
        },
        "required_stable_frames": 2,
    }


def _runtime_feedback_resources() -> tuple[ResourceState, ...]:
    return (
        ResourceState("INT-01", capability_class="reserve"),
        ResourceState("INT-02", capability_class="alpha"),
        ResourceState("INT-03", capability_class="beta"),
        ResourceState("INT-04", capability_class="beta"),
        ResourceState("INT-05"),
    )


def _runtime_feedback_tracks(*, reserve_replan: bool) -> tuple[TargetTrack, ...]:
    resource_ids = tuple(f"INT-0{index}" for index in range(1, 6))
    t001_fov = (
        (0.0, 0.1, 0.5, 0.0, 1.0)
        if reserve_replan
        else (0.0, 0.1, 0.2, 0.8, 1.0)
    )
    return (
        TargetTrack(
            "T001",
            threat_score=0.95,
            covariance=0.1,
            window_cost=0.1,
            demand=TargetDemand(
                required_resource_count=3,
                primary_resource_count=2,
                coordination_mode="hybrid",
                required_capability_counts={"alpha": 1, "beta": 1},
            ),
            feasibility_by_resource={
                resource_id: resource_id != "INT-05"
                for resource_id in resource_ids
            },
            fov_difficulty_by_resource=dict(zip(resource_ids, t001_fov)),
        ),
        TargetTrack(
            "T002",
            threat_score=0.5,
            covariance=0.1,
            window_cost=0.1,
            feasibility_by_resource={
                resource_id: resource_id == "INT-05"
                for resource_id in resource_ids
            },
        ),
    )


def test_reserve_soft_hold_preserves_primaries_and_respects_min_dwell() -> None:
    planner = _planner()
    resources = _runtime_feedback_resources()
    first = planner.plan(
        _runtime_feedback_tracks(reserve_replan=False),
        resources,
        timestamp=0.0,
    )
    feedback = (
        {
            "target_id": "T001",
            "resource_id": "INT-02",
            "plan_version": first.version,
            "terminal_feedback_state": "consistent",
            "main_action": "continue",
        },
        {
            "target_id": "T001",
            "resource_id": "INT-03",
            "plan_version": first.version,
            "terminal_feedback_state": "consistent",
            "main_action": "continue",
        },
        {
            "target_id": "T001",
            "resource_id": "INT-01",
            "plan_version": first.version,
            "terminal_feedback_state": "hold",
            "main_action": "hold",
        },
    )
    writeback = apply_terminal_feedback_to_planner_inputs(
        _runtime_feedback_tracks(reserve_replan=True),
        resources,
        feedback,
    )

    replanned = planner.plan(
        writeback.tracks,
        writeback.resources,
        timestamp=1.5,
        previous_plan=first,
        expected_previous_version=first.version,
    )

    first_members = {
        assignment.resource_id: assignment.member_role
        for assignment in first.assignments_by_target()["T001"]
    }
    replanned_members = {
        assignment.resource_id: assignment.member_role
        for assignment in replanned.assignments_by_target()["T001"]
    }
    assert first_members == {
        "INT-01": "reserve",
        "INT-02": "primary",
        "INT-03": "primary",
    }
    assert replanned_members == first_members
    assert writeback.hold_resource_ids == ()
    assert all(resource.operator_hold is False for resource in writeback.resources)
    assert all(event["reason"] is None for event in writeback.metadata["terminal_feedback_events"])
    assert all(
        event["required_stable_frames"] is None
        for event in writeback.metadata["terminal_feedback_events"]
    )
    assert replanned.version == first.version
    assert replanned.decision_state == "held_by_coalition_membership_hysteresis"
    assert replanned.metadata["membership_change_records"][0]["dwell_ok"] is False
    assert replanned.metadata["feedback_primary_role_protection_applied"] is True
    assert replanned.metadata["feedback_primary_role_protection_by_target"] == (
        {
            "target_id": "T001",
            "primary_resource_ids": ("INT-02", "INT-03"),
            "source_plan_id": first.plan_id,
            "source_plan_version": first.version,
        },
    )


def test_transient_feedback_window_does_not_bypass_coalition_min_dwell() -> None:
    planner = _planner()
    resources = _resources()
    first = planner.plan(_tracks(switch_primary=False), resources, timestamp=0.0)
    writeback = apply_terminal_feedback_to_planner_inputs(
        _tracks(switch_primary=True),
        resources,
        _stability_feedback(first),
    )

    held = planner.plan_incremental(
        writeback.tracks,
        writeback.resources,
        timestamp=1.5,
        previous_plan=first,
        changed_track_ids={"T001"},
        expected_previous_version=first.version,
    )
    released = planner.plan_incremental(
        writeback.tracks,
        writeback.resources,
        timestamp=2.0,
        previous_plan=held,
        changed_track_ids={"T001"},
        expected_previous_version=held.version,
    )

    assert _primary_ids(first) == {"INT-01", "INT-02"}
    assert _primary_ids(held) == _primary_ids(first)
    assert held.version == first.version
    assert held.decision_state == "held_by_transient_feedback_dwell"
    assert held.metadata["transient_feedback_dwell_records"] == (
        {
            "target_id": "T001",
            "source_plan_id": first.plan_id,
            "source_plan_version": first.version,
            "observed_frames": 1,
            "required_frames": 2,
            "stable_lock_frame_count_by_resource": {
                "INT-01": 1,
                "INT-02": 1,
            },
            "reasons": ("primary_lock_stability_incomplete",),
        },
    )
    assert held.metadata["incremental_applied"] is True

    assert _primary_ids(released) == _primary_ids(first)
    assert released.version == first.version
    assert released.decision_state == "held_by_coalition_membership_hysteresis"
    assert released.metadata["transient_feedback_dwell_state"] == "released"
    assert released.metadata["transient_feedback_dwell_reason"] == (
        "required_window_complete"
    )
    assert released.metadata["membership_change_records"][0]["dwell_ok"] is False


def test_hard_binding_conflict_replans_without_waiting_for_transient_dwell() -> None:
    planner = _planner()
    resources = _resources()
    first = planner.plan(_tracks(switch_primary=False), resources, timestamp=0.0)
    feedback = {
        **_stability_feedback(first),
        "resource_id": "INT-01",
        "terminal_feedback_state": "cross_view_conflict",
        "coalition_conflict_state": "coalition_or_plan_version_mismatch",
        "duplicate_terminal_lock_risk": True,
        "prohibited_edges": (
            {"target_id": "T001", "resource_id": "INT-01"},
        ),
    }
    writeback = apply_terminal_feedback_to_planner_inputs(
        _tracks(switch_primary=True),
        resources,
        feedback,
    )

    replanned = planner.plan(
        writeback.tracks,
        writeback.resources,
        timestamp=1.5,
        previous_plan=first,
        expected_previous_version=first.version,
    )

    assert writeback.prohibited_edges == (
        {"target_id": "T001", "resource_id": "INT-01"},
    )
    assert _primary_ids(replanned) == {"INT-02", "INT-04"}
    assert replanned.version == first.version + 1
    assert replanned.metadata["transient_feedback_dwell_state"] == "released"
    assert replanned.metadata["transient_feedback_dwell_reason"] == "hard_risk"
    assert "duplicate_terminal_lock_risk" in replanned.metadata[
        "transient_feedback_hard_release_reasons"
    ]
