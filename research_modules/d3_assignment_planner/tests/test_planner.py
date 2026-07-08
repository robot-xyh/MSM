from d3_assignment_planner import (
    AssignmentPlanner,
    CostModel,
    CostWeights,
    PlannerConfig,
    StalePlanError,
    apply_terminal_feedback_to_planner_inputs,
    assignment_validity_summary_from_plan,
    evaluate_terminal_feedback,
    guidance_bindings_from_assignment_plan,
)
from d3_assignment_planner.models import ResourceState, TargetTrack
from d3_assignment_planner.solver import HungarianAssignmentSolver


def _resources() -> list[ResourceState]:
    return [ResourceState("R1"), ResourceState("R2")]


def _planner(config: PlannerConfig) -> AssignmentPlanner:
    weights = CostWeights(
        window=0.0,
        covariance=0.0,
        threat=0.0,
        resource_state=0.0,
        fov=1.0,
        conflict=0.0,
    )
    return AssignmentPlanner(
        cost_model=CostModel(weights=weights, config=config),
        solver=HungarianAssignmentSolver(allow_scipy=False),
        config=config,
    )


def test_planner_assigns_lowest_cost_pairs() -> None:
    config = PlannerConfig(enable_hysteresis=False)
    planner = _planner(config)
    tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0}),
        TargetTrack("T2", 0.2, 0.1, 0.1, fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0}),
    ]

    plan = planner.plan(tracks, _resources(), timestamp=0.0)

    assert plan.assignment_map() == {"T1": "R1", "T2": "R2"}
    assert plan.version == 1
    assert plan.human_authorization_state == "required"


def test_planner_records_dynamic_non_5v5_problem_size() -> None:
    config = PlannerConfig(enable_hysteresis=False)
    planner = _planner(config)
    tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0}),
        TargetTrack("T2", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0}),
        TargetTrack("T3", 0.6, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.2, "R2": 0.2}),
    ]
    resources = [ResourceState("R1"), ResourceState("R2")]

    plan = planner.plan(tracks, resources, timestamp=0.0)

    assert plan.resource_count == 2
    assert plan.target_count == 3
    assert plan.metadata["resource_count"] == 2
    assert plan.metadata["target_count"] == 3
    assert plan.metadata["assignment_matrix_shape"] == [3, 2]
    assert len(plan.assignments) == 2
    assert plan.unassigned_target_ids == ("T3",)


def test_hysteresis_holds_when_dwell_time_is_too_short() -> None:
    config = PlannerConfig(delta=0.2, min_dwell=2.0)
    planner = _planner(config)
    initial_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0}),
        TargetTrack("T2", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0}),
    ]
    shifted_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.8, "R2": 0.0}),
        TargetTrack("T2", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 0.8}),
    ]

    first = planner.plan(initial_tracks, _resources(), timestamp=0.0)
    second = planner.plan(
        shifted_tracks,
        _resources(),
        timestamp=1.0,
        previous_plan=first,
    )

    assert second.assignment_map() == first.assignment_map()
    assert second.decision_state == "held_by_hysteresis"
    assert second.changed is False
    assert second.last_changed_at == first.last_changed_at
    assert second.candidate_total_cost == 0.0
    assert second.previous_total_cost_current == 1.6


def test_hysteresis_accepts_when_gain_and_dwell_pass() -> None:
    config = PlannerConfig(delta=0.2, min_dwell=2.0)
    planner = _planner(config)
    initial_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0}),
        TargetTrack("T2", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0}),
    ]
    shifted_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.8, "R2": 0.0}),
        TargetTrack("T2", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 0.8}),
    ]

    first = planner.plan(initial_tracks, _resources(), timestamp=0.0)
    second = planner.plan(
        shifted_tracks,
        _resources(),
        timestamp=3.0,
        previous_plan=first,
    )

    assert second.assignment_map() == {"T1": "R2", "T2": "R1"}
    assert second.decision_state == "accepted_gain_and_dwell"
    assert second.changed is True
    assert second.previous_total_cost_current == 1.6


def test_previous_infeasible_plan_is_replaced_even_inside_dwell() -> None:
    config = PlannerConfig(delta=0.2, min_dwell=5.0)
    planner = _planner(config)
    tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0}),
        TargetTrack("T2", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0}),
    ]
    first = planner.plan(tracks, _resources(), timestamp=0.0)
    resources = [ResourceState("R1", status="unavailable"), ResourceState("R2")]

    second = planner.plan(tracks, resources, timestamp=1.0, previous_plan=first)

    assert second.decision_state == "accepted_previous_infeasible"
    assert second.assignment_map() == {"T2": "R2"}


def test_d5_duplicate_feedback_writeback_forces_next_round_replan() -> None:
    config = PlannerConfig(delta=0.2, min_dwell=5.0)
    planner = _planner(config)
    tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 0.4}),
    ]
    resources = _resources()
    first = planner.plan(tracks, resources, timestamp=0.0)
    decision = evaluate_terminal_feedback(
        "consistent",
        duplicate_terminal_lock_risk=True,
        plan_version=first.version,
        resource_id="R1",
        target_id="T1",
    )
    writeback = apply_terminal_feedback_to_planner_inputs(
        tracks,
        resources,
        decision,
    )

    second = planner.plan(
        writeback.tracks,
        writeback.resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert first.assignment_map() == {"T1": "R1"}
    assert writeback.tracks[0].feasibility_by_resource["R1"] is False
    assert second.assignment_map() == {"T1": "R2"}
    assert second.decision_state == "accepted_previous_infeasible"


def test_planner_rejects_stale_previous_plan() -> None:
    config = PlannerConfig(enable_hysteresis=False)
    planner = _planner(config)
    tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0}),
        TargetTrack("T2", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0}),
    ]

    first = planner.plan(tracks, _resources(), timestamp=0.0)
    second = planner.plan(tracks, _resources(), timestamp=1.0, previous_plan=first)

    assert second.version == 2
    try:
        planner.plan(tracks, _resources(), timestamp=2.0, previous_plan=first)
    except StalePlanError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("expected stale plan rejection")


def test_planner_respects_configured_human_authorization_state() -> None:
    config = PlannerConfig(enable_hysteresis=False, human_authorization_state="approved")
    planner = _planner(config)

    plan = planner.plan(
        [TargetTrack("T1", 0.9, 0.1, 0.1)],
        [ResourceState("R1")],
        timestamp=0.0,
    )

    assert plan.human_authorization_state == "approved"
    assert plan.metadata["configured_human_authorization_state"] == "approved"
    assert plan.metadata["effective_human_authorization_state"] == "approved"


def test_center_replan_produces_new_version_and_current_d7_binding() -> None:
    config = PlannerConfig(enable_hysteresis=False, human_authorization_state="approved")
    planner = _planner(config)
    first_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 0.8}),
    ]
    second_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.8, "R2": 0.0}),
    ]

    first = planner.plan(first_tracks, _resources(), timestamp=0.0)
    second = planner.plan(second_tracks, _resources(), timestamp=1.0, previous_plan=first)
    stale_summary = assignment_validity_summary_from_plan(
        first,
        evaluated_at=1.0,
        latest_plan_id=second.plan_id,
        latest_version=second.version,
    )
    (binding,) = guidance_bindings_from_assignment_plan(second, previous_plan=first)

    assert second.version == first.version + 1
    assert second.previous_plan_id == first.plan_id
    assert second.assignment_map() == {"T1": "R2"}
    assert stale_summary.stale_plan_version is True
    assert binding.plan_version == second.version
    assert binding.resource_id == "R2"
    assert binding.binding_state == "active"
    assert binding.metadata["previous_target_for_resource"] is None


def test_hysteresis_holds_when_change_limit_exceeded() -> None:
    config = PlannerConfig(delta=0.0, min_dwell=0.0, max_changes_per_window=1)
    planner = _planner(config)
    initial_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0}),
        TargetTrack("T2", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0}),
    ]
    shifted_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.8, "R2": 0.0}),
        TargetTrack("T2", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 0.8}),
    ]

    first = planner.plan(initial_tracks, _resources(), timestamp=0.0)
    second = planner.plan(shifted_tracks, _resources(), timestamp=3.0, previous_plan=first)

    assert second.assignment_map() == first.assignment_map()
    assert second.decision_state == "held_by_change_limit"
    assert second.metadata["candidate_change_count"] == 2


def test_reassignment_switch_penalty_is_exposed_in_breakdown() -> None:
    config = PlannerConfig(
        enable_hysteresis=False,
        reassignment_switch_penalty=2.5,
    )
    planner = _planner(config)
    initial_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0}),
    ]
    shifted_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0}),
    ]

    first = planner.plan(initial_tracks, _resources(), timestamp=0.0)
    second = planner.plan(shifted_tracks, _resources(), timestamp=1.0, previous_plan=first)
    assignment = second.assignments[0]

    assert assignment.resource_id == "R2"
    assert assignment.cost_breakdown["reassignment_switch_penalty"] == 2.5


def test_plan_and_assignments_expose_cross_node_contract_fields() -> None:
    config = PlannerConfig(
        enable_hysteresis=False,
        source_node_id="center-c2",
        target_node_id="all-interceptors",
        link_type="c2_direct",
        stale_after_s=1.5,
    )
    planner = _planner(config)

    plan = planner.plan(
        [TargetTrack("T1", 0.9, 0.1, 0.1)],
        [ResourceState("R1")],
        timestamp=4.0,
    )
    assignment = plan.assignments[0]

    assert plan.plan_version == 1
    assert plan.source_node_id == "center-c2"
    assert plan.target_node_id == "all-interceptors"
    assert plan.link_type == "c2_direct"
    assert plan.stale_after_s == 1.5
    assert plan.metadata["plan_version"] == 1
    assert assignment.source_node_id == "center-c2"
    assert assignment.target_node_id == "R1"
    assert assignment.link_type == "c2_direct"
    assert assignment.plan_version == 1
    assert assignment.stale_after_s == 1.5
