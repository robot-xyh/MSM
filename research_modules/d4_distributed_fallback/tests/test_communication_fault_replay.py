from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from d4_distributed_fallback import (
    P1_COMMUNICATION_MATRIX_VERSION,
    P1_COMMUNICATION_SCENARIOS,
    CommunicationReplayConfig,
    run_p1_communication_fault_matrix,
)


ROOT = Path(__file__).resolve().parents[1]


def _report(member_count: int = 3):
    return run_p1_communication_fault_matrix(
        CommunicationReplayConfig(
            member_ids=tuple(f"INT-{index + 1}" for index in range(member_count)),
            secondary_node_ids=("RECON-1", "RECON-2"),
        ),
        seeds=range(10),
    )


def _cases(report, scenario_id: str):
    return tuple(case for case in report.cases if case.scenario_id == scenario_id)


def test_six_scenario_ten_seed_report_is_complete_and_serializable() -> None:
    report = _report()

    assert report.matrix_version == P1_COMMUNICATION_MATRIX_VERSION
    assert report.scenario_ids == P1_COMMUNICATION_SCENARIOS
    assert report.seeds == tuple(range(10))
    assert report.summary["case_count"] == 60
    assert report.summary["all_safety_outcomes_met"] is True
    assert report.summary["false_degradation_count"] == 0
    assert report.summary["duplicate_owner_count"] == 0
    assert report.assignment_plan_generated_by_d4 is False
    assert report.lowers_external_execution_gates is False
    json.dumps(report.to_dict())


def test_normal_center_never_false_degrades() -> None:
    report = _report()

    for case in _cases(report, "normal"):
        assert case.selected_layer == "center"
        assert case.commit_state == "center_active"
        assert case.first_failure_reason is None
        assert case.metadata["false_degradation"] is False
        assert case.state_trace[-1]["action"] == "continue_center"


def test_half_second_delay_rejects_out_of_order_stale_ack_then_commits() -> None:
    report = _report()

    for case in _cases(report, "delay_0_5s"):
        assert case.selected_layer == "secondary"
        assert case.commit_state == "executing"
        assert case.execution_allowed is True
        assert case.acked_member_ids == case.required_member_ids
        assert case.rejected_ack_count == 1
        assert "ack_plan_version_stale" in case.failure_reasons
        assert case.metadata["configured_delay_s"] == [0.5, 0.5]
        assert case.metadata["out_of_order_stale_ack_injected"] is True


def test_thirty_percent_loss_is_deterministic_and_always_fail_closed_when_incomplete() -> None:
    first = _report()
    second = _report()
    first_cases = _cases(first, "loss_30pct")
    second_cases = _cases(second, "loss_30pct")

    assert [case.to_dict() for case in first_cases] == [case.to_dict() for case in second_cases]
    assert any(case.message_stats["dropped_count"] > 0 for case in first_cases)
    for case in first_cases:
        if case.missing_member_ids:
            assert case.execution_allowed is False
            assert case.commit_state == "aborted"
            assert case.commit_reason == "missing_required_acks"
        else:
            assert case.execution_allowed is True


def test_center_and_secondary_failures_preserve_hierarchy() -> None:
    report = _report()

    for case in _cases(report, "center_failure"):
        assert case.layer_trace == ("center", "secondary")
        assert case.owner_id == "RECON-1"
        assert case.execution_allowed is True
    for case in _cases(report, "center_secondary_failure"):
        assert case.layer_trace == ("center", "secondary", "distributed")
        assert case.owner_id == "INT-1"
        assert case.execution_allowed is True
        assert case.reconfigure_count == 1
        assert [item["role"] for item in case.member_exit_events] == [
            "center",
            "secondary_coordinator",
        ]


def test_partition_recovery_uses_new_generation_and_prevents_split_brain() -> None:
    report = _report()

    for case in _cases(report, "partition_recovery"):
        assert case.execution_allowed is True
        assert case.recovery_completed is True
        assert case.reconfigure_count == 1
        assert case.epoch == 2
        assert case.plan_version == 2
        assert case.coalition_version == 2
        assert case.acked_member_ids == case.required_member_ids
        assert case.split_brain_detected is True
        assert case.split_brain_prevented is True
        assert case.duplicate_owner_count == 0
        assert "network_partition" in case.failure_reasons
        assert case.metadata["stale_owner_reject_reason"] == "coalition_epoch_stale"


def test_member_count_is_input_driven() -> None:
    report = _report(member_count=5)

    assert report.config.member_ids == tuple(f"INT-{index + 1}" for index in range(5))
    for scenario_id in ("delay_0_5s", "center_failure", "center_secondary_failure"):
        for case in _cases(report, scenario_id):
            assert len(case.required_member_ids) == 5
            assert case.required_member_ids == case.acked_member_ids


def test_cli_emits_main_d6_consumable_schema() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_p1_communication_fault_replay.py"),
            "--member-count",
            "4",
            "--secondary-count",
            "2",
            "--seed-count",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["schema"] == "d4_p1_communication_fault_replay_v1"
    assert payload["config"]["member_ids"] == ["INT-1", "INT-2", "INT-3", "INT-4"]
    assert payload["summary"]["case_count"] == 12
