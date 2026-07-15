from d3_assignment_planner import (
    AssignmentPlanner,
    CostModel,
    CostWeights,
    PlannerConfig,
    ResourceState,
    TargetDemand,
    TargetTrack,
    apply_terminal_feedback_to_planner_inputs,
    guidance_bindings_from_assignment_plan,
    plan_history_record_from_plan,
    prepare_secondary_takeover_plan,
)
from d3_assignment_planner.solver import HungarianAssignmentSolver


def _planner(**config_overrides: object) -> AssignmentPlanner:
    config_values: dict[str, object] = {"delta": 0.2, "min_dwell": 0.0}
    config_values.update(config_overrides)
    config = PlannerConfig(**config_values)
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


def _track(target_id: str, costs: dict[str, float]) -> TargetTrack:
    return TargetTrack(
        target_id,
        threat_score=0.8,
        covariance=0.0,
        window_cost=0.0,
        fov_difficulty_by_resource=costs,
    )


def test_small_round_trip_noise_and_soft_feedback_do_not_advance_plan() -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan(
        [_track("T1", {"R1": 0.50, "R2": 0.55})],
        resources,
        timestamp=0.0,
        window_id=4,
    )
    feedback = apply_terminal_feedback_to_planner_inputs(
        [_track("T1", {"R1": 0.50, "R2": 0.55})],
        resources,
        [
            {
                "target_id": "T1",
                "resource_id": "R1",
                "plan_version": first.version,
                "terminal_feedback_state": "hold",
                "main_action": "hold",
            }
        ],
    )
    held = planner.plan(
        feedback.tracks,
        feedback.resources,
        timestamp=1.0,
        previous_plan=first,
        window_id=4,
    )
    reverse_noise = planner.plan(
        [_track("T1", {"R1": 0.55, "R2": 0.50})],
        resources,
        timestamp=2.0,
        previous_plan=held,
        window_id=4,
    )

    assert first.assignment_map() == {"T1": "R1"}
    assert held.assignment_map() == first.assignment_map()
    assert reverse_noise.assignment_map() == first.assignment_map()
    assert held.plan_id == reverse_noise.plan_id == first.plan_id
    assert held.version == reverse_noise.version == first.version
    assert held.metadata["hysteresis_cost_basis_schema"] == (
        "d3_hysteresis_current_objective_v1"
    )
    assert held.metadata["hysteresis_candidate_search_total_cost"] == 0.55
    assert held.metadata["hysteresis_candidate_comparison_total_cost"] == 0.55
    assert held.metadata["hysteresis_previous_comparison_total_cost"] == 0.50
    assert held.metadata["hysteresis_improvement_ok"] is False


def test_window_budget_is_cumulative_and_recovers_in_new_window() -> None:
    planner = _planner(delta=0.0, max_changes_per_window=1)
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan(
        [_track("T1", {"R1": 0.0, "R2": 1.0})],
        resources,
        timestamp=0.0,
        window_id=7,
    )
    changed = planner.plan(
        [_track("T1", {"R1": 1.0, "R2": 0.0})],
        resources,
        timestamp=1.0,
        previous_plan=first,
        window_id=7,
    )
    held = planner.plan(
        [_track("T1", {"R1": 0.0, "R2": 1.0})],
        resources,
        timestamp=2.0,
        previous_plan=changed,
        window_id=7,
    )
    recovered = planner.plan(
        [_track("T1", {"R1": 0.0, "R2": 1.0})],
        resources,
        timestamp=3.0,
        previous_plan=held,
        window_id=8,
    )

    assert changed.assignment_map() == {"T1": "R2"}
    assert changed.metadata["hysteresis_window_changes_used"] == 1
    assert held.assignment_map() == changed.assignment_map()
    assert held.decision_state == "held_by_change_limit"
    assert held.metadata["hysteresis_window_changes_used_before"] == 1
    assert held.metadata["hysteresis_window_changes_if_accepted"] == 2
    assert held.metadata["hysteresis_window_change_budget_ok"] is False
    assert recovered.assignment_map() == {"T1": "R1"}
    assert recovered.metadata["hysteresis_change_window_id"] == 8
    assert recovered.metadata["hysteresis_window_changes_used_before"] == 0
    assert recovered.metadata["hysteresis_window_changes_used"] == 1

    history = plan_history_record_from_plan(
        held,
        sequence_index=2,
        timestamp=2.0,
        previous_plan=changed,
    ).to_dict()
    assert history["hysteresis"]["window_changes_used"] == 1
    assert history["hysteresis"]["window_candidate_change_count"] == 1
    assert history["hysteresis"]["window_changes_if_accepted"] == 2


def test_hard_resource_failure_bypasses_exhausted_window_budget() -> None:
    planner = _planner(delta=0.0, max_changes_per_window=1)
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan(
        [_track("T1", {"R1": 0.0, "R2": 1.0})],
        resources,
        timestamp=0.0,
        window_id=12,
    )
    changed = planner.plan(
        [_track("T1", {"R1": 1.0, "R2": 0.0})],
        resources,
        timestamp=1.0,
        previous_plan=first,
        window_id=12,
    )
    failed = planner.plan(
        [_track("T1", {"R1": 0.4, "R2": 0.0})],
        [ResourceState("R1"), ResourceState("R2", status="unavailable")],
        timestamp=1.1,
        previous_plan=changed,
        window_id=12,
    )

    assert failed.assignment_map() == {"T1": "R1"}
    assert failed.version == changed.version + 1
    assert failed.decision_state == "accepted_previous_infeasible"
    assert failed.metadata["hysteresis_window_change_budget_ok"] is False
    assert failed.metadata["hysteresis_window_change_budget_bypassed"] is True
    assert failed.metadata["hysteresis_window_change_budget_bypass_reason"] == (
        "accepted_previous_infeasible"
    )
    assert failed.metadata["hysteresis_window_changes_used"] == 2


def test_missing_target_wins_over_other_coalition_membership_hold() -> None:
    planner = _planner(
        solver_name="hungarian_demand_slots",
        min_dwell=10.0,
    )
    resources = [ResourceState(f"R{i}") for i in range(1, 6)]
    demand = TargetDemand(
        required_resource_count=2,
        primary_resource_count=1,
        coordination_mode="hybrid",
    )

    def coalition_track(target_id: str, costs: dict[str, float]) -> TargetTrack:
        return TargetTrack(
            target_id,
            threat_score=0.8,
            covariance=0.0,
            window_cost=0.0,
            demand=demand,
            fov_difficulty_by_resource=costs,
        )

    first = planner.plan(
        [
            coalition_track(
                "LOST",
                {"R1": 0.0, "R2": 0.1, "R3": 1.0, "R4": 1.0, "R5": 1.0},
            ),
            coalition_track(
                "KEEP",
                {"R1": 1.0, "R2": 1.0, "R3": 0.0, "R4": 0.1, "R5": 1.0},
            ),
        ],
        resources,
        timestamp=0.0,
        window_id=20,
    )
    replanned = planner.plan(
        [
            coalition_track(
                "KEEP",
                {"R1": 1.0, "R2": 1.0, "R3": 0.8, "R4": 0.1, "R5": 0.0},
            )
        ],
        resources,
        timestamp=0.5,
        previous_plan=first,
        window_id=20,
    )

    assert replanned.decision_state == "accepted_previous_infeasible"
    assert replanned.version == first.version + 1
    assert replanned.metadata["previous_missing_execution_target_ids"] == ("LOST",)
    assert replanned.metadata["membership_hold_required"] is True
    assert {assignment.target_id for assignment in replanned.assignments} == {"KEEP"}
    assert {coalition.target_id for coalition in replanned.coalitions} == {"KEEP"}
    assert {
        record["target_id"]
        for record in replanned.metadata["membership_change_records"]
    } == {"KEEP"}


def test_owner_change_publishes_new_fail_closed_identity_inside_dwell() -> None:
    planner = _planner(delta=0.9, min_dwell=100.0, max_changes_per_window=0)
    tracks = [_track("T1", {"R1": 0.5})]
    resources = [ResourceState("R1")]
    center = planner.plan(tracks, resources, timestamp=0.0, window_id=30)
    takeover_candidate = planner.plan(
        tracks,
        resources,
        timestamp=0.1,
        previous_plan=center,
        window_id=30,
        publish=False,
    )
    secondary = prepare_secondary_takeover_plan(
        takeover_candidate,
        supersedes_plan=center,
        secondary_node_id="secondary-1",
        readiness_class="takeover_ready",
        readiness_sustained=True,
        activated_at_s=0.2,
        lease_expires_at_s=5.0,
        leader_epoch=1,
    )
    secondary = planner.publish_plan(secondary)
    returned_to_center = planner.plan(
        tracks,
        resources,
        timestamp=0.3,
        previous_plan=secondary,
        window_id=30,
    )
    (old_binding,) = guidance_bindings_from_assignment_plan(
        secondary,
        now_s=0.3,
        current_plan_id=returned_to_center.plan_id,
        current_plan_version=returned_to_center.version,
    )

    assert returned_to_center.version == secondary.version + 1
    assert returned_to_center.decision_state == "accepted_execution_control_change"
    assert "execution_owner_changed" in returned_to_center.metadata[
        "execution_control_change_reasons"
    ]
    assert old_binding.assignment_validity_state == "stale"
    assert old_binding.revoke_reason == "not_current_assignment_plan"
