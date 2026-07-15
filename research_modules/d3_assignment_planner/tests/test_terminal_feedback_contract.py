from d3_assignment_planner import (
    ResourceState,
    TargetTrack,
    apply_terminal_feedback_to_planner_inputs,
    evaluate_terminal_feedback,
)


def test_terminal_feedback_ambiguous_or_hold_recommends_hold() -> None:
    ambiguous = evaluate_terminal_feedback("ambiguous", plan_version=3)
    hold = evaluate_terminal_feedback("hold", plan_version=3)

    assert ambiguous.recommended_action == "hold"
    assert hold.recommended_action == "hold"
    assert ambiguous.allow_local_rebind is False
    assert hold.allow_local_rebind is False
    assert ambiguous.plan_version == 3
    assert hold.planner_metadata["operator_hold_suggested"] is False
    assert hold.planner_metadata["feedback_constraint_class"] == (
        "resource_target_edge_soft"
    )


def test_terminal_feedback_reacquire_recommends_replan_without_rebind() -> None:
    decision = evaluate_terminal_feedback("reacquire", plan_version=4)

    assert decision.recommended_action == "replan"
    assert decision.allow_local_rebind is False
    assert decision.reasons == ("terminal_feedback_reacquire",)
    assert decision.plan_version == 4


def test_terminal_feedback_mismatch_recommends_secondary_arbitration() -> None:
    decision = evaluate_terminal_feedback("mismatch", plan_version=5)

    assert decision.recommended_action == "secondary_arbitration"
    assert decision.allow_local_rebind is False
    assert decision.reasons == ("terminal_feedback_mismatch",)
    assert decision.plan_version == 5
    assert decision.planner_metadata["feedback_constraint_class"] == (
        "resource_target_edge_hard"
    )


def test_duplicate_terminal_lock_risk_overrides_feedback_state() -> None:
    decision = evaluate_terminal_feedback(
        "consistent",
        duplicate_terminal_lock_risk=True,
        plan_version=6,
        resource_id="R1",
        target_id="T1",
    )

    assert decision.recommended_action == "secondary_arbitration"
    assert decision.main_action == "secondary_arbitration"
    assert decision.duplicate_terminal_lock_risk is True
    assert decision.allow_local_rebind is False
    assert decision.reasons == ("duplicate_terminal_lock_risk",)
    assert decision.planner_metadata["prohibit_assignment_suggested"] is True
    assert decision.planner_metadata["feasibility_by_resource"] == {"R1": False}
    assert decision.planner_metadata["fov_difficulty_by_resource"] == {"R1": 1.0}
    assert decision.planner_metadata["prohibited_edges"] == (
        {"target_id": "T1", "resource_id": "R1"},
    )


def test_friend_overlap_feedback_metadata_maps_to_resource_hold() -> None:
    decision = evaluate_terminal_feedback(
        "friend_overlap_hold",
        plan_version=7,
        resource_id="R2",
        target_id="T2",
    )

    assert decision.recommended_action == "hold"
    assert decision.main_action == "hold"
    assert decision.planner_metadata["operator_hold_suggested"] is True
    assert decision.planner_metadata["resource_update"] == {
        "resource_id": "R2",
        "operator_hold": True,
    }
    assert decision.planner_metadata["feasibility_suggestion"] == "unchanged"
    assert decision.planner_metadata["fov_difficulty_suggestion"] == "increase_current_edge"


def test_ambiguous_feedback_is_edge_soft_and_never_sets_resource_hold() -> None:
    decision = evaluate_terminal_feedback(
        "ambiguous",
        plan_version=7,
        resource_id="R2",
        target_id="T2",
    )
    writeback = apply_terminal_feedback_to_planner_inputs(
        [TargetTrack("T2", 0.8, 0.1, 0.1)],
        [ResourceState("R1"), ResourceState("R2")],
        decision,
    )

    assert decision.planner_metadata["operator_hold_suggested"] is False
    assert decision.planner_metadata["feedback_constraint_class"] == (
        "resource_target_edge_soft"
    )
    assert writeback.hold_resource_ids == ()
    assert writeback.resources[1].operator_hold is False
    assert writeback.prohibited_edges == ()
    assert writeback.tracks[0].fov_difficulty_by_resource["R2"] == 1.0
    assert writeback.d7_gate_action == "hold"
    assert writeback.metadata["feedback_classifications"] == (
        {
            "target_id": "T2",
            "resource_id": "R2",
            "terminal_feedback_state": "ambiguous",
            "constraint_class": "resource_target_edge_soft",
            "constraint_scope": "resource_target_edge",
            "classification_reason": "ordinary_terminal_uncertainty",
            "hard_reject": False,
        },
    )


def test_legacy_nested_pair_hold_is_accepted_as_soft_feedback() -> None:
    writeback = apply_terminal_feedback_to_planner_inputs(
        [TargetTrack("T2", 0.8, 0.1, 0.1)],
        [ResourceState("R1"), ResourceState("R2")],
        {
            "target_id": "T2",
            "operator_hold_suggested": True,
            "resource_update": {"resource_id": "R2", "operator_hold": True},
        },
    )

    assert writeback.hold_resource_ids == ()
    assert writeback.resources[1].operator_hold is False
    assert writeback.tracks[0].fov_difficulty_by_resource["R2"] == 1.0
    assert writeback.metadata["feedback_classifications"][0][
        "classification_reason"
    ] == "legacy_pair_hold_downgraded"


def test_terminal_feedback_metadata_maps_reacquire_to_replan_suggestions() -> None:
    decision = evaluate_terminal_feedback(
        "reacquire",
        plan_version=8,
        resource_id="R3",
        target_id="T3",
    )

    assert decision.recommended_action == "replan"
    assert decision.main_action == "replan"
    assert decision.planner_metadata["operator_hold_suggested"] is False
    assert decision.planner_metadata["prohibit_assignment_suggested"] is False
    assert decision.planner_metadata["feasibility_suggestion"] == "review_current_edge"
    assert decision.planner_metadata["fov_difficulty_by_resource"] == {"R3": 1.0}


def test_feedback_writeback_maps_duplicate_to_next_round_prohibited_edge() -> None:
    decision = evaluate_terminal_feedback(
        "consistent",
        duplicate_terminal_lock_risk=True,
        plan_version=9,
        resource_id="R1",
        target_id="T1",
    )

    writeback = apply_terminal_feedback_to_planner_inputs(
        [TargetTrack("T1", 0.8, 0.1, 0.1)],
        [ResourceState("R1"), ResourceState("R2")],
        decision,
    )

    assert writeback.allow_local_rebind is False
    assert writeback.prohibited_edges == ({"target_id": "T1", "resource_id": "R1"},)
    assert writeback.d7_gate_action == "hold"
    assert writeback.d4_requests == ("secondary_arbitration",)
    assert writeback.tracks[0].feasibility_by_resource["R1"] is False
    assert writeback.tracks[0].fov_difficulty_by_resource["R1"] == 1.0


def test_feedback_writeback_maps_friend_hold_to_resource_hold_and_fov_cost() -> None:
    decision = evaluate_terminal_feedback(
        "friend_overlap_hold",
        plan_version=10,
        resource_id="R2",
        target_id="T2",
    )

    writeback = apply_terminal_feedback_to_planner_inputs(
        [TargetTrack("T2", 0.8, 0.1, 0.1)],
        [ResourceState("R1"), ResourceState("R2")],
        decision.planner_metadata,
    )

    assert writeback.hold_resource_ids == ("R2",)
    assert writeback.resources[1].operator_hold is True
    assert writeback.tracks[0].fov_difficulty_by_resource["R2"] == 1.0
    assert writeback.tracks[0].feasibility_by_resource == {}
    assert writeback.metadata["allow_local_rebind"] is False


def test_verified_friend_feedback_is_target_hard_fail_closed() -> None:
    writeback = apply_terminal_feedback_to_planner_inputs(
        [TargetTrack("T2", 0.8, 0.1, 0.1)],
        [ResourceState("R1"), ResourceState("R2")],
        {
            "target_id": "T2",
            "resource_id": "R2",
            "terminal_feedback_state": "hold",
            "friend_conflict_state": "verified_friend_overlap",
            "operator_hold_suggested": True,
        },
    )

    assert writeback.hard_target_ids == ("T2",)
    assert writeback.tracks[0].assignable is False
    assert writeback.hold_resource_ids == ()
    assert all(resource.operator_hold is False for resource in writeback.resources)
    assert writeback.metadata["feedback_classifications"][0][
        "classification_reason"
    ] == "verified_friend"


def test_duplicate_assignment_metadata_is_edge_hard_fail_closed() -> None:
    writeback = apply_terminal_feedback_to_planner_inputs(
        [TargetTrack("T2", 0.8, 0.1, 0.1)],
        [ResourceState("R1"), ResourceState("R2")],
        {
            "target_id": "T2",
            "resource_id": "R2",
            "terminal_feedback_state": "hold",
            "duplicate_assignment_count": 1,
        },
    )

    assert writeback.prohibited_edges == (
        {"target_id": "T2", "resource_id": "R2"},
    )
    assert writeback.tracks[0].feasibility_by_resource["R2"] is False
    assert writeback.resources[1].operator_hold is False
    assert writeback.metadata["feedback_classifications"][0][
        "classification_reason"
    ] == "duplicate_assignment_or_lock"


def test_feedback_writeback_applies_explicit_fov_and_feasibility_metadata() -> None:
    writeback = apply_terminal_feedback_to_planner_inputs(
        [TargetTrack("T3", 0.8, 0.1, 0.1, fov_difficulty_by_resource={"R3": 0.2})],
        [ResourceState("R3")],
        {
            "target_id": "T3",
            "resource_id": "R3",
            "d7_gate_action": "hold",
            "feasibility_by_resource": {"R3": False},
            "fov_difficulty_by_resource": {"R3": 0.75},
        },
    )

    assert writeback.prohibited_edges == ({"target_id": "T3", "resource_id": "R3"},)
    assert writeback.tracks[0].feasibility_by_resource["R3"] is False
    assert writeback.tracks[0].fov_difficulty_by_resource["R3"] == 0.75
    assert writeback.d7_gate_action == "hold"
    assert writeback.metadata["feedback_classifications"][0][
        "classification_reason"
    ] == "explicit_feasibility_reject"
