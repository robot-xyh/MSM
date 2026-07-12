from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from d4_distributed_fallback import (
    CoalitionCommitCoordinator,
    CoalitionMemberAck,
    P1_FAILOVER_MATRIX_VERSION,
    P1_FAILOVER_SCENARIOS,
    run_p1_failover_disturbance_replay,
)


ROOT = Path(__file__).resolve().parents[1]


def _cases():
    report = run_p1_failover_disturbance_replay()
    return report, {case.scenario_id: case for case in report.cases}


def test_p1_matrix_is_versioned_complete_and_serializable() -> None:
    report, cases = _cases()

    assert report.matrix_version == P1_FAILOVER_MATRIX_VERSION
    assert report.scenario_ids == P1_FAILOVER_SCENARIOS
    assert tuple(cases) == P1_FAILOVER_SCENARIOS
    assert report.summary["scenario_count"] == len(P1_FAILOVER_SCENARIOS)
    assert report.summary["passed_count"] == len(P1_FAILOVER_SCENARIOS)
    assert report.summary["all_expected_outcomes_met"] is True
    assert report.assignment_plan_generated_by_d4 is False
    assert report.lowers_external_execution_gates is False
    json.dumps(report.to_dict())


def test_normal_center_does_not_false_degrade_and_secondary_needs_full_ack() -> None:
    report, cases = _cases()
    normal = cases["normal_center_no_false_degradation"]
    secondary = cases["secondary_takeover_full_ack"]

    assert normal.metadata["false_degradation"] is False
    assert normal.state_trace[-1]["d4_action"] == "continue_center"
    assert report.summary["false_degradation_count"] == 0
    assert secondary.final_state == "executing"
    assert secondary.execution_allowed is True
    assert secondary.state_trace[-2]["state"] == "committed"
    assert secondary.state_trace[-2]["missing_member_ids"] == []


def test_missing_ack_epoch_lease_and_digest_faults_fail_closed() -> None:
    _, cases = _cases()
    expected = {
        "missing_ack_fail_closed": "missing_required_acks",
        "stale_epoch_rejected": "coalition_epoch_stale",
        "expired_lease_fail_closed": "coalition_lease_expired",
        "digest_conflict_fail_closed": "coalition_digest_conflict",
    }

    for scenario_id, reason in expected.items():
        case = cases[scenario_id]
        assert case.passed is True
        assert case.fail_closed is True
        assert case.execution_allowed is False
        assert case.final_reason == reason


def test_member_replacement_and_partition_recovery_require_new_full_commit() -> None:
    _, cases = _cases()

    for scenario_id in ("member_loss_replacement", "network_partition_recovery"):
        case = cases[scenario_id]
        assert case.final_state == "executing"
        assert case.execution_allowed is True
        assert any(item["state"] == "reconfiguring" for item in case.state_trace)
        assert case.state_trace[-1]["epoch"] == 2
        assert case.state_trace[-1]["required_member_ids"] == case.state_trace[-1][
            "acked_member_ids"
        ]
        assert case.state_trace[-1]["missing_member_ids"] == []


def test_center_recovery_stays_in_dual_track_review() -> None:
    _, cases = _cases()
    recovery = cases["center_recovery_dual_track_audit"]

    assert recovery.final_state == "dual_track_review_required"
    assert recovery.execution_allowed is False
    assert recovery.metadata["immediate_authority_change"] is False
    assert recovery.metadata["recovery_audit"]["recovered_newer"] is True
    assert recovery.metadata["recovery_audit"]["immediate_takeover_allowed"] is False


def test_p1_replay_cli_emits_versioned_schema() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_p1_failover_replay.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["schema"] == "d4_p1_failover_disturbance_replay_v1"
    assert payload["matrix_version"] == P1_FAILOVER_MATRIX_VERSION
    assert payload["summary"]["all_expected_outcomes_met"] is True


def test_atomic_commit_uses_required_member_set_size_not_fixture_size() -> None:
    coordinator = CoalitionCommitCoordinator()
    members = ("INT-1", "INT-2", "INT-3", "INT-4")
    state = coordinator.propose(
        global_track_id="G-SCALE-1",
        coalition_id="coalition-scale-1",
        coalition_version=1,
        plan_id="plan-scale-1",
        plan_version=1,
        epoch=1,
        coordinator_id="INT-1",
        coordinator_role="cluster_representative",
        required_member_ids=members,
        lease_expires_at=20.0,
        timestamp=10.0,
    )

    for offset, member_id in enumerate(members, start=1):
        timestamp = 10.0 + 0.1 * offset
        state = coordinator.record_ack(
            state,
            CoalitionMemberAck(
                resource_id=member_id,
                global_track_id=state.global_track_id,
                coalition_id=state.coalition_id,
                coalition_version=state.coalition_version,
                plan_id=state.plan_id,
                plan_version=state.plan_version,
                epoch=state.epoch,
                can_execute=True,
                evidence_timestamp=timestamp,
                valid_until=15.0,
            ),
            timestamp=timestamp,
        )
        if member_id != members[-1]:
            assert state.state == "collecting_acks"
            assert state.missing_member_ids

    assert state.state == "committed"
    assert state.acked_member_ids == members
    assert coordinator.mark_executing(state, timestamp=10.5).state == "executing"
