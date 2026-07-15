import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    CostModel,
    CostWeights,
    PlannerConfig,
    StalePlanError,
    apply_terminal_feedback_to_planner_inputs,
    assignment_evidence_from_plan,
    assignment_records_from_plan,
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


def test_planner_allows_missing_previous_plan_on_first_call() -> None:
    planner = _planner(PlannerConfig(enable_hysteresis=False))

    plan = planner.plan(
        [TargetTrack("T1", 0.9, 0.1, 0.1)],
        [ResourceState("R1")],
        timestamp=0.0,
        previous_plan=None,
    )

    assert plan.version == 1
    assert plan.previous_plan_id is None


def test_planner_requires_previous_plan_after_active_plan() -> None:
    planner = _planner(PlannerConfig(enable_hysteresis=False))
    tracks = [TargetTrack("T1", 0.9, 0.1, 0.1)]
    resources = [ResourceState("R1")]
    first = planner.plan(tracks, resources, timestamp=0.0)

    with pytest.raises(StalePlanError) as exc_info:
        planner.plan(tracks, resources, timestamp=1.0, previous_plan=None)

    error = exc_info.value
    assert error.reason == "previous_plan_required"
    assert error.latest_plan_id == first.plan_id
    assert error.latest_version == first.version
    assert error.to_metadata()["stale_reject_reason"] == "previous_plan_required"
    assert error.to_metadata()["latest_plan_id"] == first.plan_id
    assert error.to_metadata()["latest_plan_version"] == first.version


def test_missing_previous_plan_rejection_does_not_reset_version() -> None:
    planner = _planner(PlannerConfig(enable_hysteresis=False))
    tracks = [TargetTrack("T1", 0.9, 0.1, 0.1)]
    resources = [ResourceState("R1")]
    first = planner.plan(tracks, resources, timestamp=0.0)

    with pytest.raises(StalePlanError, match="previous_plan is required"):
        planner.plan(tracks, resources, timestamp=1.0, previous_plan=None)

    second = planner.plan(tracks, resources, timestamp=2.0, previous_plan=first)

    assert second.version == first.version
    assert second.plan_id == first.plan_id
    assert second.created_at == first.created_at
    assert second.previous_plan_id == first.previous_plan_id
    assert second.changed is False


def test_planner_preserves_expected_and_stale_version_rejections() -> None:
    planner = _planner(PlannerConfig(enable_hysteresis=False))
    tracks = [TargetTrack("T1", 0.9, 0.1, 0.1)]
    resources = [ResourceState("R1")]
    first = planner.plan(tracks, resources, timestamp=0.0)

    with pytest.raises(StalePlanError) as expected_exc_info:
        planner.plan(
            tracks,
            resources,
            timestamp=1.0,
            previous_plan=first,
            expected_previous_version=first.version + 1,
        )
    assert expected_exc_info.value.reason == "expected_previous_version_mismatch"
    assert expected_exc_info.value.latest_plan_id == first.plan_id
    assert expected_exc_info.value.latest_version == first.version

    shifted_tracks = [
        TargetTrack(
            "T1",
            0.9,
            0.1,
            0.1,
            feasibility_by_resource={"R1": False},
        )
    ]
    second = planner.plan(
        shifted_tracks,
        resources,
        timestamp=2.0,
        previous_plan=first,
        expected_previous_version=first.version,
    )
    with pytest.raises(StalePlanError) as stale_exc_info:
        planner.plan(
            tracks,
            resources,
            timestamp=3.0,
            previous_plan=first,
            expected_previous_version=first.version,
        )
    assert stale_exc_info.value.reason == "stale_previous_version"
    assert stale_exc_info.value.latest_plan_id == second.plan_id
    assert stale_exc_info.value.latest_version == second.version


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
    assert second.metadata["hysteresis_state"] == "held"
    assert second.metadata["hysteresis_reason"] == "min_dwell_not_met"
    assert second.metadata["hysteresis_reasons"] == ("min_dwell_not_met",)
    assert second.metadata["hysteresis_dwell_ok"] is False

    record = assignment_records_from_plan(second)[0]
    assert record.hysteresis_state == "held"
    assert record.hysteresis_reason == "min_dwell_not_met"
    assert record.hysteresis_reasons == ("min_dwell_not_met",)
    assert record.hysteresis_dwell_ok is False
    assert record.hysteresis_candidate_change_count == 2


def test_hysteresis_hold_audits_new_target_without_versioning_it() -> None:
    config = PlannerConfig(delta=0.2, min_dwell=2.0)
    planner = _planner(config)
    resources = _resources()
    first = planner.plan(
        [
            TargetTrack(
                "T1",
                0.9,
                0.1,
                0.1,
                fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0},
            ),
            TargetTrack(
                "T2",
                0.8,
                0.1,
                0.1,
                fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0},
            ),
        ],
        resources,
        timestamp=0.0,
    )
    candidate_tracks = [
        TargetTrack(
            "T1",
            0.9,
            0.1,
            0.1,
            fov_difficulty_by_resource={"R1": 0.8, "R2": 0.0},
        ),
        TargetTrack(
            "T2",
            0.8,
            0.1,
            0.1,
            fov_difficulty_by_resource={"R1": 0.0, "R2": 0.8},
        ),
        TargetTrack(
            "T3",
            0.4,
            0.1,
            0.1,
            feasibility_by_resource={"R1": False, "R2": False},
        ),
    ]

    held = planner.plan(
        candidate_tracks,
        resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert held.decision_state == "held_by_hysteresis"
    assert held.plan_id == first.plan_id
    assert held.version == first.version
    assert held.execution_signature() == first.execution_signature()
    assert held.unassigned_target_ids == first.unassigned_target_ids == ()
    assert held.target_count == 3
    assert held.metadata["hysteresis_candidate_unassigned_target_ids"] == ("T3",)
    assert held.metadata["hysteresis_pending_new_target_ids"] == ("T3",)


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
    assert second.metadata["hysteresis_state"] == "released"
    assert second.metadata["hysteresis_release_reason"] == "gain_dwell_change_limit_passed"


def test_hysteresis_releases_when_high_threat_unassigned_target_improves() -> None:
    config = PlannerConfig(delta=0.9, min_dwell=10.0, high_threat_threshold=0.7)
    planner = _planner(config)
    initial_tracks = [
        TargetTrack("T1", 0.1, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0}),
        TargetTrack(
            "T2",
            0.95,
            0.1,
            0.1,
            fov_difficulty_by_resource={"R1": 0.0},
            feasibility_by_resource={"R1": False},
        ),
    ]
    shifted_tracks = [
        TargetTrack("T1", 0.1, 0.1, 0.1, fov_difficulty_by_resource={"R1": 1.0}),
        TargetTrack("T2", 0.95, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0}),
    ]
    resources = [ResourceState("R1")]

    first = planner.plan(initial_tracks, resources, timestamp=0.0)
    second = planner.plan(
        shifted_tracks,
        resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert first.assignment_map() == {"T1": "R1"}
    assert first.unassigned_target_ids == ("T2",)
    assert second.assignment_map() == {"T2": "R1"}
    assert second.decision_state == "accepted_high_threat_release"
    assert second.metadata["hysteresis_state"] == "released"
    assert second.metadata["hysteresis_release_reason"] == "high_threat_unassigned_reduced"
    assert second.metadata["hysteresis_high_threat_release"] is True
    assert second.metadata["hysteresis_previous_high_threat_unassigned_count"] == 1
    assert second.metadata["hysteresis_candidate_high_threat_unassigned_count"] == 0


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


def test_missing_previous_execution_target_releases_hold_fail_closed() -> None:
    planner = _planner(PlannerConfig(delta=0.9, min_dwell=30.0))
    resources = _resources()
    first = planner.plan(
        [
            TargetTrack(
                "T1",
                0.9,
                0.1,
                0.1,
                fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0},
            ),
            TargetTrack(
                "T2",
                0.8,
                0.1,
                0.1,
                fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0},
            ),
        ],
        resources,
        timestamp=0.0,
    )

    replanned = planner.plan(
        [
            TargetTrack(
                "T1",
                0.9,
                0.1,
                0.1,
                fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0},
            )
        ],
        resources,
        timestamp=0.5,
        previous_plan=first,
    )

    assert replanned.decision_state == "accepted_previous_infeasible"
    assert replanned.plan_id != first.plan_id
    assert replanned.version == first.version + 1
    assert replanned.assignment_map() == {"T1": "R1"}
    assert {coalition.target_id for coalition in replanned.coalitions} == {"T1"}
    assert replanned.metadata["previous_missing_execution_target_ids"] == ("T2",)


def test_planner_hard_rejects_closed_time_window_edge() -> None:
    config = PlannerConfig(enable_hysteresis=False)
    planner = _planner(config)
    tracks = [
        TargetTrack(
            "T1",
            0.9,
            0.1,
            0.0,
            fov_difficulty_by_resource={"R1": 0.0, "R2": 0.7},
            time_window_by_resource={"R1": {"state": "closed"}},
        )
    ]

    plan = planner.plan(tracks, _resources(), timestamp=10.0)
    evidence = assignment_evidence_from_plan(plan)

    assert plan.assignment_map() == {"T1": "R2"}
    assert plan.unassigned_target_ids == ()
    assert plan.metadata["hard_reject_count"] == 1
    assert plan.metadata["hard_reject_reasons"] == ("time_window_closed",)
    assert plan.metadata["rejected_edges"][0]["target_id"] == "T1"
    assert plan.metadata["rejected_edges"][0]["resource_id"] == "R1"
    assert plan.metadata["rejected_edges"][0]["reject_reason"] == "time_window_closed"
    assert evidence.current_plan_id == plan.plan_id
    assert evidence.current_plan_version == plan.version
    assert evidence.cost_matrix_target_ids == ("T1",)
    assert evidence.cost_matrix_resource_ids == ("R1", "R2")
    assert evidence.rejected_edges[0]["reject_reason"] == "time_window_closed"


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
    shifted_tracks = [
        TargetTrack("T1", 0.9, 0.1, 0.1, feasibility_by_resource={"R1": False}),
        tracks[1],
    ]
    second = planner.plan(
        shifted_tracks,
        _resources(),
        timestamp=1.0,
        previous_plan=first,
    )

    assert second.version == 2
    try:
        planner.plan(tracks, _resources(), timestamp=2.0, previous_plan=first)
    except StalePlanError as exc:
        assert "stale" in str(exc)
        assert exc.reason == "stale_previous_version"
        assert exc.to_metadata()["stale_reject_reason"] == "stale_previous_version"
        assert exc.to_metadata()["latest_plan_version"] == second.version
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
    assert binding.assignment_validity_state == "current"
    assert binding.revoke_reason is None
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


def test_zero_switch_penalty_allows_lower_cost_reassignment() -> None:
    config = PlannerConfig(
        enable_hysteresis=False,
        reassignment_switch_penalty=0.0,
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

    assert first.assignment_map() == {"T1": "R1"}
    assert second.assignment_map() == {"T1": "R2"}
    assert second.assignments[0].cost_breakdown["reassignment_switch_penalty"] == 0.0


def test_switch_penalty_is_applied_before_solve_without_double_charging() -> None:
    config = PlannerConfig(
        enable_hysteresis=False,
        reassignment_switch_penalty=0.5,
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
    evidence = assignment_evidence_from_plan(second)
    edge_by_resource = {
        str(edge["resource_id"]): edge
        for edge in evidence.cost_breakdowns_by_edge
    }

    assert assignment.resource_id == "R2"
    assert assignment.cost == 0.5
    assert assignment.cost_breakdown["reassignment_switch_penalty"] == 0.5
    assert assignment.cost_breakdown["total"] == assignment.cost
    assert evidence.cost_matrix == ((1.0, 0.5),)
    assert edge_by_resource["R1"]["cost_breakdown"]["reassignment_switch_penalty"] == 0.0
    assert edge_by_resource["R2"]["cost_breakdown"]["reassignment_switch_penalty"] == 0.5
    assert edge_by_resource["R2"]["cost_breakdown"]["total"] == 0.5
    assert second.candidate_total_cost == assignment.cost
    assert second.total_cost == assignment.cost


def test_large_switch_penalty_preserves_previous_resource_in_hungarian_solve() -> None:
    config = PlannerConfig(
        enable_hysteresis=False,
        reassignment_switch_penalty=2.0,
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
    evidence = assignment_evidence_from_plan(second)

    assert first.assignment_map() == {"T1": "R1"}
    assert second.assignment_map() == {"T1": "R1"}
    assert second.changed is False
    assert second.assignments[0].cost_breakdown["reassignment_switch_penalty"] == 0.0
    assert evidence.cost_matrix == ((1.0, 2.0),)
    assert second.candidate_total_cost == 1.0
    assert second.total_cost == 1.0


def test_switch_penalty_skips_infeasible_new_target_and_unassigned_costs() -> None:
    config = PlannerConfig(
        enable_hysteresis=False,
        reassignment_switch_penalty=3.0,
    )
    planner = _planner(config)
    first = planner.plan(
        [TargetTrack("T1", 0.9, 0.1, 0.1, fov_difficulty_by_resource={"R1": 0.0})],
        [ResourceState("R1")],
        timestamp=0.0,
    )
    tracks = [
        TargetTrack(
            "T1",
            0.9,
            0.1,
            0.1,
            feasibility_by_resource={"R1": False, "R2": False},
        ),
        TargetTrack(
            "T2",
            0.2,
            0.1,
            0.1,
            fov_difficulty_by_resource={"R1": 0.25, "R2": 0.5},
        ),
    ]
    second = planner.plan(
        tracks,
        _resources(),
        timestamp=1.0,
        previous_plan=first,
    )
    evidence = assignment_evidence_from_plan(second)
    edge_by_pair = {
        (str(edge["target_id"]), str(edge["resource_id"])): edge
        for edge in evidence.cost_breakdowns_by_edge
    }

    assert second.assignment_map() == {"T2": "R1"}
    assert second.unassigned_target_ids == ("T1",)
    assert second.total_cost == config.unassigned_base_cost * (0.5 + 0.9) + 0.25
    assert evidence.cost_matrix[0] == (
        config.infeasible_penalty,
        config.infeasible_penalty,
    )
    assert evidence.cost_matrix[1] == (0.25, 0.5)
    assert edge_by_pair[("T1", "R2")]["cost_breakdown"][
        "reassignment_switch_penalty"
    ] == 0.0
    assert edge_by_pair[("T2", "R1")]["cost_breakdown"][
        "reassignment_switch_penalty"
    ] == 0.0


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
