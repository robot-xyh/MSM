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
    )

    assert decision.recommended_action == "secondary_arbitration"
    assert decision.duplicate_terminal_lock_risk is True
    assert decision.allow_local_rebind is False
    assert decision.reasons == ("duplicate_terminal_lock_risk",)
