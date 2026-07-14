from __future__ import annotations

import csv
from pathlib import Path

from d4_distributed_fallback import (
    ActiveDegradationArbiter,
    AssignmentValiditySummary,
    TerminalAssociationSummary,
    TerminalDecisionState,
    audit_airsim_terminal_consistency,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_posefix_persisted_output_fixture_exposes_previous_false_binding_evidence() -> None:
    audit = audit_airsim_terminal_consistency(
        FIXTURES / "posefix_smoke_control_commands.csv",
        FIXTURES / "posefix_smoke_main_episode_bus.jsonl",
    )

    assert audit.control_row_count == 4
    assert audit.control_d4_terminal_inconsistent_count == 2
    assert audit.d4_event_count == 4
    assert audit.terminal_inconsistent_count == 3
    assert audit.terminal_inconsistent_without_hard_risk_count == 2
    assert audit.center_current_coalition_safe_false_count == 2
    assert audit.hard_fail_closed_count == 1


def test_posefix_binding_replay_preserves_current_center_binding_only() -> None:
    arbiter = ActiveDegradationArbiter()
    with (FIXTURES / "posefix_smoke_binding_replay.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        for row in csv.DictReader(stream):
            assignment = AssignmentValiditySummary(
                global_track_id=row["global_track_id"],
                assigned_resource_id=row["resource_id"],
                plan_version=1,
                is_current=row["is_current"] == "true",
                plan_age_s=float(row["plan_age_s"]),
            )
            terminal = TerminalAssociationSummary(
                resource_id=row["resource_id"],
                assigned_global_track_id=row["global_track_id"],
                observed_global_track_id=row["observed_global_track_id"] or None,
                decision_state=TerminalDecisionState(row["decision_state"]),
                association_confidence=float(row["association_confidence"]),
                ambiguity_score=float(row["ambiguity_score"]),
                coverage_cell="cell-test",
                consecutive_non_locked_frames=int(
                    row["consecutive_non_locked_frames"]
                ),
            )

            actual = not arbiter.terminal_binding_reject_reasons(
                assignment,
                terminal,
            )
            assert actual is (row["expected_terminal_consistent"] == "true")
