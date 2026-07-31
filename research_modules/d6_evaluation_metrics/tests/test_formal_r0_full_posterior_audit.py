from __future__ import annotations

import hashlib
import json
from pathlib import Path

from d6_evaluation_metrics.formal_r0_full_posterior_audit import (
    FORMAL_R0_FULL_POSTERIOR_INPUT_SCHEMA_VERSION,
    FormalR0FullPosteriorAuditInputs,
    aggregate_formal_r0_full_posterior_rows,
    audit_canonical_r0_scope,
    audit_checksum_manifest,
    load_formal_r0_full_posterior_audit_inputs,
    required_evidence_gate_reasons,
    validate_merged_scope_manifest,
)
from d6_evaluation_metrics.formal_r0_targeted_posterior_audit import (
    _progress_identity_reasons,
    load_formal_r0_targeted_posterior_audit_inputs,
)
from d6_evaluation_metrics.strict_offline_identity import (
    STRICT_OFFLINE_ID_SWITCH_SEMANTICS,
    STRICT_OFFLINE_ID_SWITCH_SOURCE,
)


SOURCE_COMMIT = "1e5ed8ddcf27f375e922a447decfbd875d21bfdf"
PLAN_SHA = "8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373"


def _inputs(tmp_path: Path) -> FormalR0FullPosteriorAuditInputs:
    return FormalR0FullPosteriorAuditInputs(
        execution_root=tmp_path / "execution",
        source_repository=tmp_path / "source",
        expected_source_git_commit=SOURCE_COMMIT,
        expected_execution_plan_sha256=PLAN_SHA,
        expected_scope_cell_count=900,
        expected_parent_cell_count=5700,
        expected_shard_count=20,
        expected_cells_per_shard=45,
    )


def _plan_cells() -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for scope_index in range(900):
        seed = 1000 + scope_index % 20
        shard_index = scope_index % 20
        scale = (5, 20, 50, 100, 200)[(scope_index // 20) % 5]
        scenario = f"scenario_{scope_index // 100:02d}"
        cells.append(
            {
                "cell_id": (
                    f"{scope_index:05d}__r0__{scenario}__"
                    f"{scale}v{scale}__seed_{seed}"
                ),
                "comparison_key": f"{scenario}|{scale}|{seed}",
                "global_index": scope_index,
                "scope_index": scope_index,
                "shard_index": shard_index,
                "shard_sequence": scope_index // 20,
                "scale": scale,
                "scenario": scenario,
                "seed": seed,
                "variant": "R0",
            }
        )
    return cells


def _passing_row(index: int) -> dict[str, object]:
    row: dict[str, object] = {
        "cell_id": f"cell_{index:03d}",
        "scenario": "nominal",
        "scale": 5,
        "seed": 1000 + index % 20,
        "verified": True,
        "formal_acceptance_eligible": True,
        "experiment_matrix_formal_acceptance_eligible": True,
        "observation_governance_generation_integrity": True,
        "observation_governance_generation_contract_status": "verified",
        "failure_reasons": [],
        "d2_id_switch_count": None,
        "d2_id_switch_count_availability": "unavailable",
        "d2_id_switch_count_unavailable_reason": (
            "truth_identity_pairing_unavailable"
        ),
    }
    values = {
        "online_truth_use_count": 0,
        "online_truth_field_violation_count": 0,
        "finite_state": True,
        "formal_acceptance_eligible": True,
        "experiment_matrix_formal_acceptance_eligible": True,
        "d1_posterior_generation": 10,
        "d1_full_posterior_publication_count": 10,
        "d2_consumed_d1_posterior_generation": 10,
        "d2_posterior_consumption_count": 7,
        "d2_association_publication_count": 7,
        "d2_pre_tick_posterior_merge_count": 3,
        "d2_finalize_unchanged_posterior_skip_count": 0,
        "d2_pending_generation_empty": True,
        "observation_governance_generation_integrity": True,
        "observation_governance_generation_contract_status": "verified",
        "d4_advice_resource_quota_conservation_violation_count": 0,
        "d4_advice_formal_decision_mutation_count": 0,
        "d4_current_d3_plan_binding_verified": True,
        "d4_current_plan_coalition_commit_verified": True,
        "d4_communication_disposition_validation_verified": True,
        "d5_active_vision_target_reference_violation_count": 0,
        "d5_active_vision_ack_target_mismatch_count": 0,
    }
    for field, value in values.items():
        row[field] = value
        row[f"{field}_availability"] = "available"
        row[f"{field}_unavailable_reason"] = None
    return row


def _strict_id_switch_row(index: int, value: int) -> dict[str, object]:
    row = _passing_row(index)
    row.update(
        d2_id_switch_count=value,
        d2_id_switch_count_availability="available",
        d2_id_switch_count_unavailable_reason=None,
        d2_id_switch_count_semantics=STRICT_OFFLINE_ID_SWITCH_SEMANTICS,
        d2_id_switch_count_source_artifact=STRICT_OFFLINE_ID_SWITCH_SOURCE,
        d2_strict_identity_artifact_verified=True,
        d2_strict_identity_truth_isolation_verified=True,
        d2_strict_identity_id_switch_backfilled=False,
        d2_strict_identity_verification_mode="sha256_verified_artifact",
    )
    return row


def _merged_manifest() -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema_version": "scalable3d-experiment-matrix-scope-merge-v1",
        "execution_plan_sha256": PLAN_SHA,
        "source_git_commit": SOURCE_COMMIT,
        "source_repository_dirty": False,
        "scope_expected_cell_count": 900,
        "scope_completed_cell_count": 900,
        "shard_count": 20,
        "parent_full_cell_count": 5700,
        "scope_complete": True,
        "formal_scope_complete": True,
        "full_matrix_complete": False,
        "formal_matrix_complete": False,
        "scope_variants": ["R0"],
        "status": "formal_scope_complete",
        "shards": [
            {
                "shard_index": index,
                "shard_id": f"shard_{index:03d}_of_020",
                "cell_count": 45,
                "checkpoint_sha256": digest,
                "progress_sha256": digest,
                "shard_plan_sha256": digest,
            }
            for index in range(20)
        ],
    }


def test_frozen_full_config_has_exact_scope_denominators() -> None:
    config = (
        Path(__file__).parents[1]
        / "configs"
        / "formal_r0_full_posterior_audit_1e5ed8d_20260730.json"
    )
    inputs = load_formal_r0_full_posterior_audit_inputs(config)

    assert inputs.expected_scope_cell_count == 900
    assert inputs.expected_parent_cell_count == 5700
    assert inputs.expected_shard_count == 20
    assert inputs.expected_cells_per_shard == 45
    assert inputs.expected_execution_plan_sha256 == PLAN_SHA


def test_canonical_scope_requires_all_900_cells_and_20_shards(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    result = audit_canonical_r0_scope(
        {"scope": {"cells": _plan_cells()}},
        inputs,
    )

    assert result["verified"] is True
    assert result["cell_count"] == 900
    assert result["unique_cell_id_count"] == 900
    assert result["shard_count"] == 20
    assert set(result["shard_cell_counts"].values()) == {45}
    assert len(result["targets"]) == 900


def test_missing_scope_cell_fails_closed(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    cells = _plan_cells()
    cells.pop()

    result = audit_canonical_r0_scope({"scope": {"cells": cells}}, inputs)

    assert result["verified"] is False
    assert any(
        reason.startswith("canonical_scope_cell_count_mismatch")
        for reason in result["failure_reasons"]
    )
    assert "canonical_scope_index_set_mismatch" in result["failure_reasons"]


def test_duplicate_progress_identity_is_explicit() -> None:
    planned = [
        {"cell_id": "cell_a"},
        {"cell_id": "cell_b"},
    ]
    progress = [
        {"cell_id": "cell_a", "sequence": 0},
        {"cell_id": "cell_a", "sequence": 0},
    ]

    reasons = _progress_identity_reasons(progress, planned)

    assert "progress_duplicate_cell_id" in reasons
    assert "progress_duplicate_sequence" in reasons
    assert "progress_cell_identity_order_mismatch" in reasons


def test_merged_manifest_requires_all_20_shards(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    passing = validate_merged_scope_manifest(
        _merged_manifest(),
        inputs=inputs,
    )
    assert passing["verified"] is True
    assert passing["shard_count"] == 20

    missing = _merged_manifest()
    missing["shards"] = missing["shards"][:-1]
    failed = validate_merged_scope_manifest(missing, inputs=inputs)
    assert failed["verified"] is False
    assert "merged_manifest_shard_count_mismatch" in failed["failure_reasons"]
    assert (
        "merged_manifest_shard_index_set_mismatch"
        in failed["failure_reasons"]
    )


def test_checksum_tamper_fails_closed(tmp_path: Path) -> None:
    merged = tmp_path / "merged_scope"
    merged.mkdir()
    entries: list[str] = []
    for name in (
        "episode_dirs.json",
        "experiment_matrix_scope_cells.csv",
        "experiment_matrix_scope_manifest.json",
    ):
        target = merged / name
        target.write_text(f"{name}\n", encoding="utf-8")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        entries.append(f"{digest}  {name}\n")
    checksum_path = merged / "SHA256SUMS"
    checksum_path.write_text("".join(entries), encoding="utf-8")
    (merged / "episode_dirs.json").write_text("tampered\n", encoding="utf-8")

    result = audit_checksum_manifest(checksum_path, merged_dir=merged)

    assert result["verified"] is False
    assert (
        "merged_checksum_mismatch:episode_dirs.json"
        in result["failure_reasons"]
    )


def test_unavailable_required_value_is_not_zero_filled() -> None:
    row = _passing_row(0)
    row["d2_posterior_consumption_count"] = None
    row["d2_posterior_consumption_count_availability"] = "unavailable"
    row["d2_posterior_consumption_count_unavailable_reason"] = "missing"

    reasons = required_evidence_gate_reasons(row)

    assert (
        "required_evidence_unavailable:d2_posterior_consumption_count"
        in reasons
    )
    assert row["d2_posterior_consumption_count"] is None


def test_full_aggregate_uses_900_denominator_and_preserves_idsw_null() -> None:
    rows = [_passing_row(index) for index in range(900)]

    aggregate = aggregate_formal_r0_full_posterior_rows(
        rows,
        expected_scope_cell_count=900,
    )

    assert aggregate["audit_denominator"] == 900
    assert aggregate["audited_cell_count"] == 900
    assert aggregate["verified_cell_count"] == 900
    assert aggregate["generation_verified_cell_count"] == 900
    assert aggregate["skip"]["total"] == 0
    assert aggregate["pending_empty"]["all_true"] is True
    assert aggregate["id_switch_count"]["availability"] == "unavailable"
    assert aggregate["id_switch_count"]["total"] is None
    assert aggregate["safety_zero_counts"]["online_truth_use_count"][
        "expected_zero_verified"
    ] is True


def test_full_aggregate_counts_only_verified_strict_zero_and_nonzero() -> None:
    rows = [_strict_id_switch_row(0, 0), _strict_id_switch_row(1, 5)]

    aggregate = aggregate_formal_r0_full_posterior_rows(
        rows,
        expected_scope_cell_count=2,
    )

    identity = aggregate["id_switch_count"]
    assert identity["availability"] == "available"
    assert identity["available_cell_count"] == 2
    assert identity["total"] == 5
    assert identity["zero_cell_count"] == 1
    assert identity["nonzero_cell_count"] == 1


def test_full_aggregate_rejects_online_semantics_even_when_value_is_zero() -> None:
    row = _passing_row(0)
    row.update(
        d2_id_switch_count=0,
        d2_id_switch_count_availability="available",
        d2_id_switch_count_unavailable_reason=None,
    )

    aggregate = aggregate_formal_r0_full_posterior_rows(
        (row,),
        expected_scope_cell_count=1,
    )

    identity = aggregate["id_switch_count"]
    assert identity["available_cell_count"] == 0
    assert identity["total"] is None
    assert identity["unavailable_reason_distribution"] == {
        "strict_offline_provenance_not_verified": 1
    }
    assert required_evidence_gate_reasons(row) == [
        "required_evidence_invalid_strict_provenance:d2_id_switch_count"
    ]


def test_targeted_five_cell_config_remains_compatible() -> None:
    config = (
        Path(__file__).parents[1]
        / "configs"
        / "formal_r0_targeted_posterior_audit_1e5ed8d_20260730.json"
    )
    inputs = load_formal_r0_targeted_posterior_audit_inputs(config)

    assert len(inputs.targets) == 5
    assert inputs.expected_completed_cell_count == 177
    assert inputs.expected_scope_cell_count == 900


def test_schema_constant_is_stable() -> None:
    assert (
        FORMAL_R0_FULL_POSTERIOR_INPUT_SCHEMA_VERSION
        == "d6.formal-r0-full-posterior-audit-input.v1"
    )
