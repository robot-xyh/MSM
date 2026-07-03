from d3_assignment_planner import evaluate_terminal_feedback


def test_terminal_feedback_ambiguous_or_hold_recommends_hold() -> None:
    ambiguous = evaluate_terminal_feedback("ambiguous", plan_version=3)
    hold = evaluate_terminal_feedback("hold", plan_version=3)

    assert ambiguous.recommended_action == "hold"
    assert hold.recommended_action == "hold"
    assert ambiguous.allow_local_rebind is False
    assert hold.allow_local_rebind is False
    assert ambiguous.plan_version == 3


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


def test_terminal_feedback_metadata_maps_hold_to_operator_hold() -> None:
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
