from dataclasses import replace
from time import perf_counter

import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    StalePlanError,
    TargetDemand,
    TargetTrack,
    p1_assignment_fixture_by_id,
    summarize_incremental_planning_comparison,
)


def _resources(count: int) -> tuple[ResourceState, ...]:
    return tuple(ResourceState(f"R{index}") for index in range(1, count + 1))


def _track(
    target_id: str,
    *,
    resource_count: int,
    allowed: set[str],
    preferred: str,
    threat: float = 0.8,
    demand: TargetDemand | None = None,
) -> TargetTrack:
    resource_ids = tuple(f"R{index}" for index in range(1, resource_count + 1))
    return TargetTrack(
        target_id,
        threat_score=threat,
        covariance=0.1,
        window_cost=0.1,
        demand=demand,
        feasibility_by_resource={
            resource_id: resource_id in allowed for resource_id in resource_ids
        },
        fov_difficulty_by_resource={
            resource_id: 0.0 if resource_id == preferred else 0.8
            for resource_id in resource_ids
        },
    )


def _isolated_coalition_inputs(
    *,
    preferred: str,
) -> tuple[tuple[TargetTrack, ...], tuple[ResourceState, ...]]:
    demand = TargetDemand(
        required_resource_count=2,
        primary_resource_count=1,
        coordination_mode="hybrid",
    )
    resources = _resources(5)
    tracks = (
        _track(
            "T1",
            resource_count=5,
            allowed={"R1", "R2"},
            preferred=preferred,
            threat=0.95,
            demand=demand,
        ),
        _track(
            "T2",
            resource_count=5,
            allowed={"R3", "R4", "R5"},
            preferred="R3",
        ),
    )
    return tracks, resources


def _coalition_planner(*, hysteresis: bool = False) -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=hysteresis,
            solver_name="hungarian_demand_slots",
            reassignment_switch_penalty=0.1,
            delta=0.2,
            min_dwell=5.0,
        )
    )


def test_incremental_replans_only_isolated_coalition_and_matches_full_plan() -> None:
    before_tracks, resources = _isolated_coalition_inputs(preferred="R1")
    after_tracks, _ = _isolated_coalition_inputs(preferred="R2")
    incremental_planner = _coalition_planner()
    first = incremental_planner.plan(before_tracks, resources, timestamp=0.0)

    incremental = incremental_planner.plan_incremental(
        after_tracks,
        resources,
        timestamp=3.0,
        previous_plan=first,
        changed_track_ids={"T1"},
        expected_previous_version=first.version,
    )

    full_planner = _coalition_planner()
    full_first = full_planner.plan(before_tracks, resources, timestamp=0.0)
    full_started_at = perf_counter()
    full = full_planner.plan(
        after_tracks,
        resources,
        timestamp=3.0,
        previous_plan=full_first,
    )
    full_latency_ms = (perf_counter() - full_started_at) * 1000.0
    summary = summarize_incremental_planning_comparison(
        incremental,
        full,
        previous_plan=first,
        full_latency_ms=full_latency_ms,
    )

    assert incremental.metadata["incremental_applied"] is True
    assert incremental.metadata["incremental_subproblem_shape"] == [1, 2]
    assert incremental.metadata["incremental_preserved_target_ids"] == ("T2",)
    preserved_before = first.assignments_by_target()["T2"][0]
    preserved_after = incremental.assignments_by_target()["T2"][0]
    assert preserved_after.resource_id == preserved_before.resource_id
    assert preserved_after.coalition_id == preserved_before.coalition_id
    assert preserved_after.coalition_version == preserved_before.coalition_version
    assert preserved_after.member_role == preserved_before.member_role
    assert len(incremental.assignments_by_target()["T1"]) == 2
    assert all(summary_item.coalition_complete for summary_item in incremental.demand_summaries)
    assert summary.cost_equivalent is True
    assert summary.assignment_equivalent is True
    assert summary.incremental_change_count == summary.full_change_count == 1
    assert summary.preserved_target_count == 1
    assert summary.preserved_assignment_count == 1
    assert summary.incremental_latency_ms >= 0.0
    assert summary.full_latency_ms >= 0.0

    primary = next(
        assignment
        for assignment in incremental.assignments_by_target()["T1"]
        if assignment.member_role == "primary"
    )
    assert primary.resource_id == "R2"
    assert primary.cost_breakdown["reassignment_switch_penalty"] == pytest.approx(0.0)
    assert primary.cost == pytest.approx(primary.cost_breakdown["total"])


def test_incremental_switch_penalty_is_counted_once_for_resource_change() -> None:
    resources = _resources(4)
    before = (
        _track(
            "T1",
            resource_count=4,
            allowed={"R1", "R2"},
            preferred="R1",
        ),
        _track(
            "T2",
            resource_count=4,
            allowed={"R3", "R4"},
            preferred="R3",
        ),
    )
    after = (replace(before[0], fov_difficulty_by_resource={"R1": 0.8, "R2": 0.0}), before[1])
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=False,
            reassignment_switch_penalty=0.1,
        )
    )
    first = planner.plan(before, resources, timestamp=0.0)
    second = planner.plan_incremental(
        after,
        resources,
        timestamp=3.0,
        previous_plan=first,
        changed_track_ids={"T1"},
    )

    assignment = second.assignments_by_target()["T1"][0]
    assert assignment.resource_id == "R2"
    assert assignment.cost_breakdown["reassignment_switch_penalty"] == pytest.approx(
        0.1
    )
    assert assignment.cost == pytest.approx(assignment.cost_breakdown["total"])


@pytest.mark.parametrize(
    ("resource_count", "target_count"),
    ((3, 5), (5, 3)),
)
def test_incremental_non_equal_shapes_do_not_assume_n_equals_m(
    resource_count: int,
    target_count: int,
) -> None:
    resources = _resources(resource_count)
    tracks = tuple(
        _track(
            f"T{index}",
            resource_count=resource_count,
            allowed={f"R{((index - 1) % resource_count) + 1}"},
            preferred=f"R{((index - 1) % resource_count) + 1}",
            threat=0.95 - index * 0.03,
        )
        for index in range(1, target_count + 1)
    )
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    first = planner.plan(tracks, resources, timestamp=0.0)
    changed = replace(tracks[0], threat_score=0.99)
    second = planner.plan_incremental(
        (changed,) + tracks[1:],
        resources,
        timestamp=1.0,
        previous_plan=first,
        changed_track_ids={changed.track_id},
    )

    assert second.resource_count == resource_count
    assert second.target_count == target_count
    assert second.metadata["assignment_matrix_shape"] == [
        target_count,
        resource_count,
    ]
    assert second.metadata["incremental_applied"] is True
    assert second.metadata["incremental_subproblem_shape"][0] < target_count


def test_incremental_new_target_safely_falls_back_to_full_plan() -> None:
    fixture = p1_assignment_fixture_by_id("new_target")
    before, after = fixture.steps
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    first = planner.plan(before.tracks, before.resources, timestamp=before.timestamp_s)
    second = planner.plan_incremental(
        after.tracks,
        after.resources,
        timestamp=after.timestamp_s,
        previous_plan=first,
        changed_track_ids={"T05"},
    )

    assert second.metadata["incremental_applied"] is False
    assert second.metadata["incremental_fallback_reason"] == "target_set_changed"
    assert second.metadata["planning_mode"] == "full"
    assert second.target_count == 5
    assert second.version == first.version + 1


def test_incremental_resource_failure_falls_back_when_component_is_global() -> None:
    fixture = p1_assignment_fixture_by_id("resource_failure")
    before, after = fixture.steps
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    first = planner.plan(before.tracks, before.resources, timestamp=before.timestamp_s)
    second = planner.plan_incremental(
        after.tracks,
        after.resources,
        timestamp=after.timestamp_s,
        previous_plan=first,
        changed_resource_ids={"R03"},
    )

    assert second.metadata["incremental_applied"] is False
    assert second.metadata["incremental_fallback_reason"] == (
        "affected_component_is_global"
    )
    assert "R03" not in {assignment.resource_id for assignment in second.assignments}
    assert len(second.unassigned_target_ids) == 1


def test_incremental_resource_set_change_falls_back_for_global_capacity() -> None:
    tracks, resources = _isolated_coalition_inputs(preferred="R1")
    planner = _coalition_planner()
    first = planner.plan(tracks, resources, timestamp=0.0)
    expanded_resources = resources + (ResourceState("R6"),)
    expanded_tracks = tuple(
        replace(
            track,
            feasibility_by_resource={
                **dict(track.feasibility_by_resource),
                "R6": False,
            },
            fov_difficulty_by_resource={
                **dict(track.fov_difficulty_by_resource),
                "R6": 1.0,
            },
        )
        for track in tracks
    )
    second = planner.plan_incremental(
        expanded_tracks,
        expanded_resources,
        timestamp=3.0,
        previous_plan=first,
        changed_track_ids={track.track_id for track in expanded_tracks},
        changed_resource_ids={"R6"},
    )

    assert second.metadata["incremental_applied"] is False
    assert second.metadata["incremental_fallback_reason"] == (
        "global_resource_capacity_changed"
    )
    assert second.resource_count == 6


def test_incremental_demand_change_falls_back_and_keeps_all_or_none() -> None:
    before_tracks, resources = _isolated_coalition_inputs(preferred="R1")
    planner = _coalition_planner()
    first = planner.plan(before_tracks, resources, timestamp=0.0)
    expanded_demand = TargetDemand(
        required_resource_count=3,
        primary_resource_count=2,
        coordination_mode="hybrid",
    )
    changed_track = replace(before_tracks[0], demand=expanded_demand)
    second = planner.plan_incremental(
        (changed_track, before_tracks[1]),
        resources,
        timestamp=3.0,
        previous_plan=first,
        changed_track_ids={"T1"},
    )

    assert second.metadata["incremental_applied"] is False
    assert second.metadata["incremental_fallback_reason"] == "target_demand_changed"
    t1_summary = next(item for item in second.demand_summaries if item.target_id == "T1")
    assert t1_summary.demand_required == 3
    assert t1_summary.demand_assigned == 2
    assert t1_summary.demand_shortfall == 1
    assert t1_summary.coalition_complete is False
    assert "T1" in second.incomplete_target_ids
    assert "T1" not in second.assignments_by_target()


def test_incremental_detects_omitted_changed_ids() -> None:
    before_tracks, resources = _isolated_coalition_inputs(preferred="R1")
    after_tracks, _ = _isolated_coalition_inputs(preferred="R2")
    planner = _coalition_planner()
    first = planner.plan(before_tracks, resources, timestamp=0.0)
    second = planner.plan_incremental(
        after_tracks,
        resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert second.metadata["incremental_applied"] is False
    assert second.metadata["incremental_fallback_reason"] == (
        "incomplete_changed_track_ids"
    )


def test_incremental_expired_plan_falls_back_but_stale_version_is_rejected() -> None:
    tracks, resources = _isolated_coalition_inputs(preferred="R1")
    changed_tracks, _ = _isolated_coalition_inputs(preferred="R2")
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=False,
            solver_name="hungarian_demand_slots",
            stale_after_s=1.0,
        )
    )
    first = planner.plan(tracks, resources, timestamp=0.0)
    refreshed = planner.plan_incremental(
        changed_tracks,
        resources,
        timestamp=2.0,
        previous_plan=first,
        changed_track_ids={"T1"},
        expected_previous_version=first.version,
    )

    assert refreshed.metadata["incremental_applied"] is False
    assert refreshed.metadata["incremental_fallback_reason"] == (
        "previous_plan_expired"
    )
    with pytest.raises(StalePlanError) as exc_info:
        planner.plan_incremental(
            changed_tracks,
            resources,
            timestamp=3.0,
            previous_plan=first,
            changed_track_ids={"T1"},
            expected_previous_version=first.version,
        )
    assert exc_info.value.reason == "stale_previous_version"
    assert exc_info.value.to_metadata()["stale_reject_reason"] == (
        "stale_previous_version"
    )


def test_incremental_hysteresis_matches_full_plan_stability() -> None:
    before_tracks, resources = _isolated_coalition_inputs(preferred="R1")
    after_tracks, _ = _isolated_coalition_inputs(preferred="R2")
    incremental_planner = _coalition_planner(hysteresis=True)
    first = incremental_planner.plan(before_tracks, resources, timestamp=0.0)
    incremental = incremental_planner.plan_incremental(
        after_tracks,
        resources,
        timestamp=1.0,
        previous_plan=first,
        changed_track_ids={"T1"},
    )

    full_planner = _coalition_planner(hysteresis=True)
    full_first = full_planner.plan(before_tracks, resources, timestamp=0.0)
    full = full_planner.plan(
        after_tracks,
        resources,
        timestamp=1.0,
        previous_plan=full_first,
    )
    summary = summarize_incremental_planning_comparison(
        incremental,
        full,
        previous_plan=first,
    )

    assert incremental.decision_state == full.decision_state == "held_by_hysteresis"
    assert incremental.plan_id == first.plan_id
    assert incremental.version == first.version
    assert summary.assignment_equivalent is True
    assert summary.cost_equivalent is True
    assert summary.incremental_change_count == summary.full_change_count == 0
