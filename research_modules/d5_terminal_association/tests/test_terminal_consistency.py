from __future__ import annotations

from d5_terminal_association import (
    CrossViewAssociation,
    TerminalAssociation,
    TerminalConsistencyConfig,
    TerminalConsistencyTracker,
    candidate_cost_margin,
    summarize_terminal_consistency,
)


def _association(
    *,
    decision: str,
    confidence: float = 0.9,
    ambiguity: float = 0.1,
    friend_state: str = "none",
    local_id: str | None = "L1",
    reason: str = "fixture",
    cue_used: bool = False,
    costs: list[tuple[str, float]] | None = None,
) -> TerminalAssociation:
    return TerminalAssociation(
        assigned_global_track_id="G1",
        local_track_id=local_id,
        association_confidence=confidence,
        ambiguity_score=ambiguity,
        friend_conflict_state=friend_state,
        decision_state=decision,
        assignment_version=2,
        reason=reason,
        candidate_costs=costs or [("L1", 1.0), ("L2", 5.5)],
        recon_cue_used=cue_used,
    )


def test_consistency_summary_tracks_locked_lost_and_reacquired_events() -> None:
    tracker = TerminalConsistencyTracker(TerminalConsistencyConfig(stable_lock_age_s=0.5))

    locked = tracker.update(
        resource_id="UAV1",
        timestamp=10.0,
        association=_association(decision="locked"),
    )
    lost = tracker.update(
        resource_id="UAV1",
        timestamp=10.1,
        association=_association(
            decision="reacquire",
            confidence=0.0,
            ambiguity=1.0,
            local_id=None,
            reason="no_local_track_inside_projection_gate",
        ),
    )
    reacquired = tracker.update(
        resource_id="UAV1",
        timestamp=10.7,
        association=_association(decision="locked", reason="unique_candidate_inside_gate"),
    )

    assert locked.consistency_state == "consistent"
    assert locked.decision_state == "locked"
    assert locked.candidate_cost_margin == 4.5
    assert lost.lost_lock_event is True
    assert lost.lock_lifecycle_state == "lost"
    assert lost.consecutive_reacquire_frames == 1
    assert lost.event_summary.startswith("lost_lock:locked->reacquire")
    assert reacquired.lock_reacquired_event is True
    assert reacquired.lock_lifecycle_state == "reacquired"
    assert reacquired.previous_decision_state == "reacquire"


def test_consistency_summary_recommends_secondary_cue_and_arbitration_after_streaks() -> None:
    tracker = TerminalConsistencyTracker(
        TerminalConsistencyConfig(
            ambiguous_frames_for_secondary=2,
            reacquire_frames_for_arbitration=2,
            conflict_frames_for_arbitration=2,
        )
    )

    first_ambiguous = tracker.update(
        resource_id="UAV1",
        timestamp=1.0,
        association=_association(decision="ambiguous", confidence=0.4, ambiguity=0.8),
    )
    second_ambiguous = tracker.update(
        resource_id="UAV1",
        timestamp=1.1,
        association=_association(decision="ambiguous", confidence=0.4, ambiguity=0.8),
    )
    first_reacquire = tracker.update(
        resource_id="UAV1",
        timestamp=1.2,
        association=_association(decision="reacquire", confidence=0.0, ambiguity=1.0, local_id=None),
    )
    second_reacquire = tracker.update(
        resource_id="UAV1",
        timestamp=1.3,
        association=_association(decision="reacquire", confidence=0.0, ambiguity=1.0, local_id=None),
    )

    assert first_ambiguous.recommended_d4_action == "observe"
    assert second_ambiguous.recommended_d4_action == "request_secondary_cue"
    assert first_reacquire.recommended_d4_action == "observe"
    assert second_reacquire.recommended_d4_action == "arbitrate"


def test_consistency_summary_reports_friend_and_duplicate_lock_conflicts() -> None:
    friend_summary = summarize_terminal_consistency(
        resource_id="UAV1",
        timestamp=2.0,
        association=_association(
            decision="hold",
            confidence=0.0,
            ambiguity=1.0,
            friend_state="verified_friend_overlap",
            reason="verified_friend_overlap_inside_gate",
        ),
    )
    duplicate_cross_view = CrossViewAssociation(
        global_track_id="G1",
        supporting_resource_ids=("UAV1", "UAV2"),
        local_track_ids=("UAV1:L1", "UAV2:L1"),
        ambiguity_score=0.1,
        duplicate_terminal_lock_risk=True,
        source_node_id="terminal_observation_bus",
        link_type="cross_view_summary",
        decision_states=("locked", "locked"),
        support_count=2,
        duplicate_lock_resource_ids=("UAV1", "UAV2"),
    )
    duplicate_summary = summarize_terminal_consistency(
        resource_id="UAV1",
        timestamp=2.1,
        association=_association(decision="locked"),
        cross_view_association=duplicate_cross_view,
    )

    assert friend_summary.consistency_state == "conflict"
    assert friend_summary.recommended_d4_action == "report_conflict"
    assert duplicate_summary.consistency_state == "conflict"
    assert duplicate_summary.recommended_d4_action == "arbitrate"
    assert duplicate_summary.cross_view_support_count == 2
    assert duplicate_summary.duplicate_lock_resource_ids == ("UAV1", "UAV2")


def test_candidate_cost_margin_handles_single_candidate() -> None:
    assert candidate_cost_margin(_association(decision="locked", costs=[("L1", 2.0)])) == float("inf")
