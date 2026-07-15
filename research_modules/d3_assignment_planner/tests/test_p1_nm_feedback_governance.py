import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    CostModel,
    CostWeights,
    PlannerConfig,
    ResourceState,
    TargetTrack,
    apply_terminal_feedback_to_planner_inputs,
    assignment_evidence_from_plan,
    assignment_records_from_plan,
    build_p1_assignment_fixtures,
    evaluate_terminal_feedback,
    p1_assignment_fixture_by_id,
)
from d3_assignment_planner.solver import HungarianAssignmentSolver


def _fov_planner(*, enable_hysteresis: bool = True) -> AssignmentPlanner:
    config = PlannerConfig(
        enable_hysteresis=enable_hysteresis,
        delta=0.2,
        min_dwell=5.0,
        cost_profile_id="d3_p1_feedback_fov",
        cost_profile_version="1.0.0",
        feedback_profile_id="d3_p1_feedback_governance",
        feedback_profile_version="1.0.0",
    )
    return AssignmentPlanner(
        cost_model=CostModel(
            weights=CostWeights(
                window=0.0,
                covariance=0.0,
                threat=0.0,
                resource_state=0.0,
                fov=1.0,
                conflict=0.0,
            ),
            config=config,
        ),
        solver=HungarianAssignmentSolver(allow_scipy=False),
        config=config,
    )


@pytest.mark.parametrize(
    ("scenario_id", "resource_count", "target_count", "assigned_count"),
    (
        ("5v5", 5, 5, 5),
        ("3v5", 3, 5, 3),
        ("5v3", 5, 3, 3),
    ),
)
def test_p1_static_nm_fixtures_run_without_equal_size_assumption(
    scenario_id: str,
    resource_count: int,
    target_count: int,
    assigned_count: int,
) -> None:
    fixture = p1_assignment_fixture_by_id(scenario_id)
    step = fixture.steps[0]
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))

    plan = planner.plan(step.tracks, step.resources, timestamp=step.timestamp_s)

    assert step.resource_count == resource_count
    assert step.target_count == target_count
    assert plan.resource_count == resource_count
    assert plan.target_count == target_count
    assert len(plan.assignments) == assigned_count
    assert plan.metadata["assignment_matrix_shape"] == [target_count, resource_count]
    assert fixture.calibration_metadata()["fixture_profile_version"] == "1.1.0"
    assert fixture.calibration_metadata()["resource_target_order"] == (
        "resources_x_targets"
    )


def test_p1_new_target_fixture_updates_version_and_problem_shape() -> None:
    fixture = p1_assignment_fixture_by_id("new_target")
    before, after = fixture.steps
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))

    first = planner.plan(before.tracks, before.resources, timestamp=before.timestamp_s)
    second = planner.plan(
        after.tracks,
        after.resources,
        timestamp=after.timestamp_s,
        previous_plan=first,
    )

    assert first.target_count == 4
    assert second.target_count == 5
    assert second.resource_count == 4
    assert second.version == first.version + 1
    assert "T05" in second.assignment_map()
    assert len(second.unassigned_target_ids) == 1
    assert second.metadata["assignment_matrix_shape"] == [5, 4]


def test_p1_resource_failure_fixture_rejects_failed_resource_edges() -> None:
    fixture = p1_assignment_fixture_by_id("resource_failure")
    before, after = fixture.steps
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))

    first = planner.plan(before.tracks, before.resources, timestamp=before.timestamp_s)
    second = planner.plan(
        after.tracks,
        after.resources,
        timestamp=after.timestamp_s,
        previous_plan=first,
    )

    assert "R03" not in second.assignment_map().values()
    assert len(second.assignments) == 4
    assert len(second.unassigned_target_ids) == 1
    rejected_r03 = [
        edge
        for edge in second.metadata["rejected_edges"]
        if edge["resource_id"] == "R03"
    ]
    assert len(rejected_r03) == 5
    assert {edge["reject_reason"] for edge in rejected_r03} == {
        "resource_unavailable"
    }


def test_duplicate_feedback_changes_matrix_and_bypasses_hysteresis() -> None:
    planner = _fov_planner()
    tracks = (
        TargetTrack(
            "T01",
            0.9,
            0.1,
            0.1,
            fov_difficulty_by_resource={"R01": 0.0, "R02": 0.4},
        ),
    )
    resources = (ResourceState("R01"), ResourceState("R02"))
    first = planner.plan(tracks, resources, timestamp=0.0)
    feedback = evaluate_terminal_feedback(
        "consistent",
        duplicate_terminal_lock_risk=True,
        plan_version=first.version,
        resource_id="R01",
        target_id="T01",
        feedback_profile_id="d3_p1_feedback_governance",
        feedback_profile_version="1.0.0",
    )
    writeback = apply_terminal_feedback_to_planner_inputs(
        tracks,
        resources,
        feedback,
    )

    second = planner.plan(
        writeback.tracks,
        writeback.resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert first.assignment_map() == {"T01": "R01"}
    assert writeback.prohibited_edges == (
        {"target_id": "T01", "resource_id": "R01"},
    )
    assert second.metadata["cost_matrix"][0][0] == planner.config.infeasible_penalty
    assert second.metadata["rejected_edges"][0]["reject_reason"] == "pair_infeasible"
    assert second.assignment_map() == {"T01": "R02"}
    assert second.decision_state == "accepted_previous_infeasible"
    assert writeback.metadata["feedback_profile_id"] == (
        "d3_p1_feedback_governance"
    )


def test_friend_feedback_holds_resource_and_forces_safe_replan() -> None:
    planner = _fov_planner()
    tracks = (
        TargetTrack(
            "T02",
            0.9,
            0.1,
            0.1,
            fov_difficulty_by_resource={"R01": 0.4, "R02": 0.0},
        ),
    )
    resources = (ResourceState("R01"), ResourceState("R02"))
    first = planner.plan(tracks, resources, timestamp=0.0)
    feedback = evaluate_terminal_feedback(
        "friend_overlap_hold",
        plan_version=first.version,
        resource_id="R02",
        target_id="T02",
    )
    writeback = apply_terminal_feedback_to_planner_inputs(tracks, resources, feedback)

    second = planner.plan(
        writeback.tracks,
        writeback.resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert first.assignment_map() == {"T02": "R02"}
    assert writeback.hold_resource_ids == ("R02",)
    assert writeback.resources[1].operator_hold is True
    assert writeback.tracks[0].fov_difficulty_by_resource["R02"] == 1.0
    assert second.metadata["rejected_edges"][0]["reject_reason"] == (
        "resource_operator_hold"
    )
    assert second.assignment_map() == {"T02": "R01"}
    assert second.decision_state == "accepted_previous_infeasible"


def test_fov_feedback_changes_cost_but_hysteresis_holds_short_dwell() -> None:
    planner = _fov_planner()
    tracks = (
        TargetTrack(
            "T03",
            0.9,
            0.1,
            0.1,
            fov_difficulty_by_resource={"R01": 0.0, "R02": 0.3},
        ),
    )
    resources = (ResourceState("R01"), ResourceState("R02"))
    first = planner.plan(tracks, resources, timestamp=0.0)
    feedback = evaluate_terminal_feedback(
        "reacquire",
        plan_version=first.version,
        resource_id="R01",
        target_id="T03",
    )
    writeback = apply_terminal_feedback_to_planner_inputs(tracks, resources, feedback)

    second = planner.plan(
        writeback.tracks,
        writeback.resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert writeback.prohibited_edges == ()
    assert second.metadata["cost_matrix"][0] == (1.0, 0.3)
    assert second.assignment_map() == first.assignment_map()
    assert second.decision_state == "held_by_transient_feedback_dwell"
    assert second.version == first.version
    assert second.metadata["transient_feedback_dwell_state"] == "held"
    assert second.metadata["transient_feedback_dwell_records"][0][
        "observed_frames"
    ] == 1

    third = planner.plan(
        writeback.tracks,
        writeback.resources,
        timestamp=2.0,
        previous_plan=second,
    )

    assert third.assignment_map() == first.assignment_map()
    assert third.decision_state == "held_by_hysteresis"
    assert third.metadata["hysteresis_dwell_ok"] is False
    assert third.version == first.version


def test_ambiguous_soft_hold_uses_cost_and_does_not_bypass_min_dwell() -> None:
    planner = _fov_planner()
    tracks = (
        TargetTrack(
            "T03",
            0.9,
            0.1,
            0.1,
            fov_difficulty_by_resource={"R01": 0.0, "R02": 0.3},
        ),
    )
    resources = (ResourceState("R01"), ResourceState("R02"))
    first = planner.plan(tracks, resources, timestamp=0.0)
    feedback = evaluate_terminal_feedback(
        "ambiguous",
        plan_version=first.version,
        resource_id="R01",
        target_id="T03",
    )
    writeback = apply_terminal_feedback_to_planner_inputs(tracks, resources, feedback)

    second = planner.plan(
        writeback.tracks,
        writeback.resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert writeback.hold_resource_ids == ()
    assert all(resource.operator_hold is False for resource in writeback.resources)
    assert writeback.prohibited_edges == ()
    assert second.metadata["cost_matrix"][0] == (1.0, 0.3)
    assert second.assignment_map() == first.assignment_map()
    assert second.decision_state == "held_by_hysteresis"
    assert second.metadata["hysteresis_dwell_ok"] is False
    assert second.version == first.version


def test_explicit_feasibility_feedback_creates_hard_reject() -> None:
    planner = _fov_planner(enable_hysteresis=False)
    tracks = (
        TargetTrack(
            "T04",
            0.9,
            0.1,
            0.1,
            fov_difficulty_by_resource={"R01": 0.0, "R02": 0.5},
        ),
    )
    resources = (ResourceState("R01"), ResourceState("R02"))
    writeback = apply_terminal_feedback_to_planner_inputs(
        tracks,
        resources,
        {
            "target_id": "T04",
            "resource_id": "R01",
            "feasibility_by_resource": {"R01": False},
            "feedback_profile_id": "d3_p1_explicit_feasibility",
            "feedback_profile_version": "2.0.0",
        },
    )

    plan = planner.plan(writeback.tracks, writeback.resources, timestamp=0.0)

    assert writeback.prohibited_edges == (
        {"target_id": "T04", "resource_id": "R01"},
    )
    assert plan.metadata["rejected_edges"][0]["reject_reason"] == "pair_infeasible"
    assert plan.assignment_map() == {"T04": "R02"}
    assert writeback.metadata["feedback_profile_id"] == (
        "d3_p1_explicit_feasibility"
    )
    assert writeback.metadata["feedback_profile_version"] == "2.0.0"


def test_profile_and_weight_metadata_exports_to_main_and_d6() -> None:
    config = PlannerConfig(
        enable_hysteresis=True,
        delta=0.15,
        min_dwell=3.0,
        reassignment_switch_penalty=0.25,
        cost_profile_id="d3_cost_calibration_alpha",
        cost_profile_version="3.2.1",
        feedback_profile_id="d3_feedback_calibration_beta",
        feedback_profile_version="4.0.0",
    )
    weights = CostWeights(
        window=0.5,
        covariance=1.5,
        threat=2.0,
        resource_state=0.75,
        fov=1.25,
        conflict=1.75,
    )
    planner = AssignmentPlanner(
        cost_model=CostModel(weights=weights, config=config),
        solver=HungarianAssignmentSolver(allow_scipy=False),
        config=config,
    )
    plan = planner.plan(
        (TargetTrack("T01", 0.9, 0.1, 0.1),),
        (ResourceState("R01"),),
        timestamp=0.0,
    )
    evidence = assignment_evidence_from_plan(plan)
    (record,) = assignment_records_from_plan(plan)

    assert plan.metadata["assignment_profile_schema"] == (
        "d3_assignment_calibration_profile_v1"
    )
    assert evidence.cost_profile_id == "d3_cost_calibration_alpha"
    assert evidence.cost_profile_version == "3.2.1"
    assert evidence.feedback_profile_id == "d3_feedback_calibration_beta"
    assert evidence.feedback_profile_version == "4.0.0"
    assert evidence.cost_weights["fov"] == 1.25
    assert evidence.planner_thresholds["delta"] == 0.15
    assert record.cost_profile_id == evidence.cost_profile_id
    assert record.feedback_profile_version == evidence.feedback_profile_version
    assert record.cost_weights == evidence.cost_weights
    assert record.planner_thresholds == evidence.planner_thresholds


def test_fixture_registry_contains_only_versioned_p1_scenarios() -> None:
    fixtures = build_p1_assignment_fixtures()

    assert {fixture.scenario_id for fixture in fixtures} == {
        "5v5",
        "3v5",
        "5v3",
        "new_target",
        "resource_failure",
        "threat_demand_change",
        "d5_feedback",
        "hard_window",
    }
    assert {fixture.profile_version for fixture in fixtures} == {"1.1.0"}
    assert all(len(fixture.steps) == 2 for fixture in fixtures)
    assert all(fixture.steps[1].event_type != "baseline" for fixture in fixtures)
