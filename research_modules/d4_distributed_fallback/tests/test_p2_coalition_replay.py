from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from d4_distributed_fallback import (
    REPLAY_SCENARIOS,
    ExternalCoalitionReplayAdapter,
    run_p2_coalition_fault_replay,
)


ROOT = Path(__file__).resolve().parents[1]


def test_native_replay_covers_required_faults_and_metrics() -> None:
    report = run_p2_coalition_fault_replay()
    native = {
        result.scenario_id: result
        for result in report.results
        if result.backend == "native_d4_coalition_cbba"
    }

    assert tuple(native) == REPLAY_SCENARIOS
    assert all(result.result_available for result in native.values())
    assert all(result.convergence_rounds is not None for result in native.values())
    assert all(result.completion_rate is not None for result in native.values())
    assert all(result.conflict_count is not None for result in native.values())
    assert all(result.expected_outcome_met for result in native.values())

    transition = native["center_secondary_distributed"]
    assert [item["phase"] for item in transition.phase_trace] == [
        "center",
        "secondary",
        "secondary_loss",
        "distributed",
    ]
    assert transition.final_state == "executing"
    assert transition.completion_rate == 1.0
    assert transition.optimality_gap == 0.0
    assert transition.metadata["single_winner_cbba_forms_atomic_coalition"] is False


def test_native_faults_fail_closed_and_replacement_requires_new_commit() -> None:
    report = run_p2_coalition_fault_replay()
    native = {
        result.scenario_id: result
        for result in report.results
        if result.backend == "native_d4_coalition_cbba"
    }

    assert native["missing_ack"].final_reason == "missing_required_acks"
    assert native["stale_epoch"].final_reason == "coalition_epoch_stale"
    assert native["expired_lease"].final_reason == "coalition_lease_expired"
    assert native["partition"].final_state == "reconfiguring"
    for scenario_id in ("missing_ack", "stale_epoch", "expired_lease", "partition"):
        assert native[scenario_id].completion_rate == 0.0
        assert native[scenario_id].optimality_gap is None
        assert native[scenario_id].unavailable_reason

    replacement = native["member_loss_replacement"]
    assert replacement.final_state == "executing"
    assert replacement.completion_rate == 1.0
    assert replacement.optimality_gap == 0.0
    assert replacement.metadata["lost_member_id"] == "INT-3"
    assert replacement.metadata["replacement_member_id"] == "INT-4"
    assert replacement.metadata["replacement_required_full_reack"] is True


def test_external_references_are_explicitly_unavailable_by_default() -> None:
    report = run_p2_coalition_fault_replay()

    assert report.isolated_from_online_d4 is True
    assert report.replaces_online_d4 is False
    assert report.adds_default_dependency is False
    assert {item.backend for item in report.external_capabilities} == {
        "mit_cbba",
        "ca_cbba",
    }
    assert all(not item.executable_adapter_available for item in report.external_capabilities)
    external = [result for result in report.results if result.backend != "native_d4_coalition_cbba"]
    assert len(external) == 2 * len(REPLAY_SCENARIOS)
    assert all(result.status == "unavailable" for result in external)
    assert all(result.unavailable_reason for result in external)
    json.dumps(report.to_dict())


def test_external_adapter_reports_source_capability_without_execution(tmp_path: Path) -> None:
    mit_tree = tmp_path / "mit"
    mit_tree.mkdir()
    (mit_tree / "CBBA_Main.m").write_text("% reference only\n", encoding="utf-8")
    ca_tree = tmp_path / "ca"
    ca_tree.mkdir()
    (ca_tree / "README.md").write_text("CA-CBBA\n", encoding="utf-8")

    mit = ExternalCoalitionReplayAdapter("mit_cbba", mit_tree).probe()
    ca = ExternalCoalitionReplayAdapter("ca_cbba", ca_tree).probe()

    assert mit.source_detected is True
    assert mit.unavailable_reason == "mit_cbba_matlab_runtime_adapter_not_integrated"
    assert mit.executable_adapter_available is False
    assert ca.source_detected is False
    assert ca.unavailable_reason == "ca_cbba_public_reference_has_no_executable_source"


def test_replay_cli_emits_same_schema() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_p2_coalition_replay.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["schema"] == "d4_p2_isolated_coalition_replay_v1"
    assert payload["scenario_ids"] == list(REPLAY_SCENARIOS)
    assert payload["backend_summary"]["native_d4_coalition_cbba"][
        "expected_outcome_met_count"
    ] == len(REPLAY_SCENARIOS)
