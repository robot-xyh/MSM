from __future__ import annotations

import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.formal_r0_targeted_posterior_audit import (
    FORMAL_R0_TARGETED_POSTERIOR_INPUT_SCHEMA_VERSION,
    FormalR0TargetCell,
    FormalR0TargetedPosteriorAuditError,
    FormalR0TargetedPosteriorAuditInputs,
    _low_level_gate_reasons,
    aggregate_formal_r0_targeted_posterior_rows,
    load_formal_r0_targeted_posterior_audit_inputs,
    render_formal_r0_targeted_posterior_audit_markdown,
)


EXPECTED_TARGETS = (
    (0, "00400__r0__delayed_noisy__5v5__seed_1000"),
    (5, "00405__r0__delayed_noisy__5v5__seed_1005"),
    (8, "00408__r0__delayed_noisy__5v5__seed_1008"),
    (18, "00418__r0__delayed_noisy__5v5__seed_1018"),
    (9, "00429__r0__delayed_noisy__20v20__seed_1009"),
)


def _inputs(*, targets=EXPECTED_TARGETS) -> FormalR0TargetedPosteriorAuditInputs:
    return FormalR0TargetedPosteriorAuditInputs(
        execution_root=Path("/tmp/execution"),
        source_repository=Path("/tmp/source"),
        expected_source_git_commit="1" * 40,
        expected_execution_plan_sha256="2" * 64,
        expected_scope_cell_count=900,
        expected_completed_cell_count=177,
        expected_shard_progress=((0, 45), (5, 45), (8, 21), (9, 45), (18, 21)),
        targets=tuple(
            FormalR0TargetCell(shard_index=shard, cell_id=cell)
            for shard, cell in targets
        ),
    )


def _passing_row(cell_id: str) -> dict[str, object]:
    return {
        "cell_id": cell_id,
        "verified": True,
        "formal_acceptance_eligible": True,
        "experiment_matrix_formal_acceptance_eligible": True,
        "observation_governance_generation_integrity": True,
        "observation_governance_generation_contract_status": "verified",
        "failure_reasons": [],
    }


def test_frozen_config_contains_exact_five_target_cells() -> None:
    config = (
        Path(__file__).parents[1]
        / "configs"
        / "formal_r0_targeted_posterior_audit_1e5ed8d_20260730.json"
    )
    inputs = load_formal_r0_targeted_posterior_audit_inputs(config)

    assert tuple(
        (target.shard_index, target.cell_id) for target in inputs.targets
    ) == EXPECTED_TARGETS
    assert inputs.expected_completed_cell_count == 177
    assert inputs.expected_scope_cell_count == 900
    assert dict(inputs.expected_shard_progress) == {
        0: 45,
        5: 45,
        8: 21,
        9: 45,
        18: 21,
    }


def test_input_rejects_duplicate_target_and_bad_progress_sum() -> None:
    with pytest.raises(
        FormalR0TargetedPosteriorAuditError,
        match="duplicates",
    ):
        _inputs(targets=EXPECTED_TARGETS + (EXPECTED_TARGETS[0],))

    with pytest.raises(
        FormalR0TargetedPosteriorAuditError,
        match="do not sum",
    ):
        FormalR0TargetedPosteriorAuditInputs(
            execution_root=Path("/tmp/execution"),
            source_repository=Path("/tmp/source"),
            expected_source_git_commit="1" * 40,
            expected_execution_plan_sha256="2" * 64,
            expected_scope_cell_count=900,
            expected_completed_cell_count=177,
            expected_shard_progress=((0, 45),),
            targets=(FormalR0TargetCell(0, EXPECTED_TARGETS[0][1]),),
        )


def test_loader_rejects_target_list_that_is_not_a_list(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": (
                    FORMAL_R0_TARGETED_POSTERIOR_INPUT_SCHEMA_VERSION
                ),
                "execution_root": "/tmp/execution",
                "source_repository": "/tmp/source",
                "expected_source_git_commit": "1" * 40,
                "expected_execution_plan_sha256": "2" * 64,
                "expected_scope_cell_count": 900,
                "expected_completed_cell_count": 177,
                "expected_shard_progress": {"0": 177},
                "targets": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        FormalR0TargetedPosteriorAuditError,
        match="targets must be a list",
    ):
        load_formal_r0_targeted_posterior_audit_inputs(path)


def test_aggregate_uses_five_cell_denominator_not_177() -> None:
    rows = [_passing_row(cell) for _, cell in EXPECTED_TARGETS]
    aggregate = aggregate_formal_r0_targeted_posterior_rows(
        rows,
        expected_scope_cell_count=900,
        expected_completed_cell_count=177,
        expected_shard_progress=((0, 45), (5, 45), (8, 21), (9, 45), (18, 21)),
    )

    assert aggregate["targeted_audit_cell_count"] == 5
    assert aggregate["targeted_audit_denominator"] == 5
    assert aggregate["verified_target_cell_count"] == 5
    assert aggregate["generation_verified_target_cell_count"] == 5
    assert aggregate["verified_target_cell_rate"] == 1.0
    assert aggregate["executed_cell_count"] == 177
    assert aggregate["formal_scope_cell_count"] == 900
    assert aggregate["audited_completed_cell_rate"] == pytest.approx(5 / 177)


def test_clean_formal_failure_closes_one_target() -> None:
    rows = [_passing_row(cell) for _, cell in EXPECTED_TARGETS]
    rows[2]["verified"] = False
    rows[2]["formal_acceptance_eligible"] = False
    rows[2]["failure_reasons"] = ["clean_formal_not_eligible"]
    aggregate = aggregate_formal_r0_targeted_posterior_rows(
        rows,
        expected_scope_cell_count=900,
        expected_completed_cell_count=177,
        expected_shard_progress=((0, 45), (5, 45), (8, 21), (9, 45), (18, 21)),
    )

    assert aggregate["verified_target_cell_count"] == 4
    assert aggregate["failed_closed_target_cell_count"] == 1
    assert aggregate["clean_formal_target_cell_count"] == 4


def test_generation_failure_closes_one_target_without_zero_fill() -> None:
    rows = [_passing_row(cell) for _, cell in EXPECTED_TARGETS]
    rows[4]["verified"] = False
    rows[4]["observation_governance_generation_integrity"] = None
    rows[4]["observation_governance_generation_contract_status"] = (
        "failed_closed"
    )
    rows[4]["failure_reasons"] = ["generation_integrity_not_verified"]
    aggregate = aggregate_formal_r0_targeted_posterior_rows(
        rows,
        expected_scope_cell_count=900,
        expected_completed_cell_count=177,
        expected_shard_progress=((0, 45), (5, 45), (8, 21), (9, 45), (18, 21)),
    )

    assert aggregate["generation_verified_target_cell_count"] == 4
    assert aggregate["generation_verified_target_cell_rate"] == 0.8
    assert rows[4]["observation_governance_generation_integrity"] is None


def test_low_level_clean_formal_and_generation_gates_fail_closed() -> None:
    evidence = {
        "episode_failure_reasons_json": [],
        "online_truth_use_count": 0,
        "online_truth_field_violation_count": 0,
        "finite_state": True,
        "formal_acceptance_eligible": False,
        "experiment_matrix_formal_acceptance_eligible": True,
        "experiment_matrix_formal_failure_reasons_json": [],
        "variant_execution_failure_reasons_json": [],
        "episode_evidence_status": "descriptive_or_incomplete_evidence",
        "observation_governance_generation_integrity": None,
        "observation_governance_generation_contract_status": "failed_closed",
    }

    reasons = _low_level_gate_reasons(evidence)

    assert "clean_formal_not_eligible" in reasons
    assert "episode_evidence_status_not_clean_formal_matrix" in reasons
    assert "generation_integrity_not_verified" in reasons
    assert "generation_contract_not_verified" in reasons


def test_low_level_gate_does_not_fill_unavailable_truth_with_zero() -> None:
    evidence = {
        "episode_failure_reasons_json": [],
        "online_truth_use_count": None,
        "online_truth_field_violation_count": None,
        "finite_state": True,
        "formal_acceptance_eligible": True,
        "experiment_matrix_formal_acceptance_eligible": True,
        "experiment_matrix_formal_failure_reasons_json": [],
        "variant_execution_failure_reasons_json": [],
        "episode_evidence_status": "clean_formal_experiment_matrix",
        "observation_governance_generation_integrity": True,
        "observation_governance_generation_contract_status": "verified",
    }

    reasons = _low_level_gate_reasons(evidence)

    assert "online_truth_use_nonzero_or_unavailable" in reasons
    assert "online_truth_field_violation_nonzero_or_unavailable" in reasons


def test_report_states_progress_and_prohibited_scope_claims() -> None:
    rows = [_passing_row(cell) for _, cell in EXPECTED_TARGETS]
    aggregate = aggregate_formal_r0_targeted_posterior_rows(
        rows,
        expected_scope_cell_count=900,
        expected_completed_cell_count=177,
        expected_shard_progress=((0, 45), (5, 45), (8, 21), (9, 45), (18, 21)),
    )
    result = {
        "evaluation_date": "2026-07-30",
        "verdict": "pass",
        "source": {"actual_git_commit": "1" * 40},
        "execution_plan": {"computed_logical_sha256": "2" * 64},
        "execution_progress": {
            "completed_cell_count": 177,
            "scope_cell_count": 900,
            "shard_progress": {"0": 45, "5": 45, "8": 21, "9": 45, "18": 21},
        },
        "aggregate": aggregate,
        "cells": [],
        "failure_reasons": [],
    }

    report = render_formal_r0_targeted_posterior_audit_markdown(result)

    assert "177/900" in report
    assert "只审计 5 个目标 cell" in report
    assert "不得写成 177/177、900/900" in report
    assert "其余 172 个已执行 cell 未由本专项逐项审计" in report
