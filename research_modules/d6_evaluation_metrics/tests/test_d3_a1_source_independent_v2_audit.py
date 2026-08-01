from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from d6_evaluation_metrics.d3_a1_source_independent_v2_audit import (
    D3A1V2ExternalAuditError,
    D3A1V2ExternalAuditInputs,
    _DatasetFrameInfo,
    _assert_evaluation_identity_free,
    _audit_frame_csv,
    _compute_dataset_split_hash,
    _find_forbidden_identity_keys,
    _float64_matrix_sha256,
    _reconcile_metric_claims,
    _recompute_metrics,
    _require_all_permissions_false,
    _validate_dataset_split_hash,
    _validate_rule_cost_matrix_hash,
    _validate_selected_edge_safety_claims,
    _verify_result_inventory,
    audit_d3_a1_source_independent_v2,
    write_d3_a1_source_independent_v2_audit,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RESULT_DIR = (
    REPOSITORY_ROOT
    / "research_modules/d3_assignment_planner/results/"
    "a1_source_independent_evaluation_v2_20260731"
)
GENERATION_ROOT = Path("/tmp/msm-d3-a1-source-independent-fc7a1c2-output")
DATASET_DIR = GENERATION_ROOT / "learning_dataset/d3_assignment"
CONTRACT = (
    REPOSITORY_ROOT
    / "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_evaluation_contract_v2.json"
)
BUNDLE = (
    REPOSITORY_ROOT
    / "research_modules/d3_assignment_planner/results/"
    "a1_assignment_aware_development_v1_20260730/bundle"
)
FROZEN_INPUTS_AVAILABLE = all(
    path.exists()
    for path in (RESULT_DIR, GENERATION_ROOT, DATASET_DIR, CONTRACT, BUNDLE)
)
RESULT_INPUT_AVAILABLE = RESULT_DIR.is_dir()


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_result_fixture(root: Path) -> None:
    root.mkdir()
    payloads = {
        "aggregate.json": b"{}\n",
        "per_frame_evaluation.jsonl": b"{}\n",
        "per_frame_evaluation.csv": b"frame\n",
        "SOURCE_INDEPENDENT_EVALUATION_CN.md": b"# fixture\n",
    }
    for name, payload in payloads.items():
        (root / name).write_bytes(payload)
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{_sha(root / name)}  {name}\n"
            for name in sorted(payloads)
        ),
        encoding="ascii",
    )


def _metric_row(*, opportunity: bool, changed: bool = False) -> dict[str, object]:
    r0_edges = [[0, 0]]
    effective_edges = [[0, 1]] if changed else r0_edges
    teacher_edges = effective_edges if opportunity else r0_edges
    r0_sha = "a" * 64
    effective_sha = "b" * 64 if changed else r0_sha
    return {
        "teacher": {
            "opportunity": opportunity,
            "selected_edges": teacher_edges,
        },
        "r0": {
            "selected_edges": r0_edges,
            "duplicate_resource_count": 0,
            "hard_edge_violation_count": 0,
            "m_to_n_atomicity_violation_count": 0,
        },
        "candidate": {
            "selected_edges": effective_edges,
            "maximum_abs_cost_correction": 0.1 if changed else 0.0,
            "duplicate_resource_count": 0,
            "hard_edge_violation_count": 0,
            "m_to_n_atomicity_violation_count": 0,
        },
        "effective": {
            "selected_edges": effective_edges,
            "cost_matrix_sha256": effective_sha,
            "exact_r0_binding": not changed,
            "exact_r0_matrix": not changed,
            "duplicate_resource_count": 0,
            "hard_edge_violation_count": 0,
            "m_to_n_atomicity_violation_count": 0,
        },
        "model_outputs": {
            "assignment_output_count": 0,
            "plan_output_count": 0,
            "runtime_output_count": 0,
            "version_output_count": 0,
        },
        "r0_rule_cost_matrix_sha256": r0_sha,
        "r0_rule_matrix_mutated": False,
        "rejected": False,
        "rejection_reasons": [],
        "ood": False,
        "scenario_version": "fixture-v1",
    }


def _dataset_frame(
    *,
    action_mask: tuple[tuple[bool, ...], ...] = ((True, True), (True, True)),
    resource_capacities: tuple[int, ...] = (1, 1),
    target_demand_slots: tuple[int, ...] = (1, 1),
) -> _DatasetFrameInfo:
    target_count = len(action_mask)
    resource_count = len(action_mask[0])
    matrix = [[float(row + column) for column in range(resource_count)] for row in range(target_count)]
    return _DatasetFrameInfo(
        key=("fixture", 20000, "fixture-v1", 0, 0.0, "train"),
        resource_count=resource_count,
        target_count=target_count,
        rule_shape=(target_count, resource_count),
        action_shape=(target_count, resource_count),
        candidate_edge_count=target_count * resource_count,
        demand_slot_count=target_count,
        resource_capacities=resource_capacities,
        target_demand_slots=target_demand_slots,
        action_mask=action_mask,
        rule_cost_matrix_sha256=_float64_matrix_sha256(matrix),
    )


def _rewrite_result_checksums(root: Path) -> None:
    payload_names = sorted(
        path.name for path in root.iterdir() if path.name != "SHA256SUMS"
    )
    (root / "SHA256SUMS").write_text(
        "".join(f"{_sha(root / name)}  {name}\n" for name in payload_names),
        encoding="ascii",
    )


def test_result_inventory_rejects_checksum_tampering(tmp_path: Path) -> None:
    root = tmp_path / "result"
    _write_result_fixture(root)
    (root / "aggregate.json").write_text('{"tampered":true}\n', encoding="utf-8")
    with pytest.raises(D3A1V2ExternalAuditError, match="result_checksum_mismatch"):
        _verify_result_inventory(root, expected_files={path.name for path in root.iterdir()})


def test_result_inventory_rejects_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "result"
    _write_result_fixture(root)
    (root / "per_frame_evaluation.csv").unlink()
    with pytest.raises(D3A1V2ExternalAuditError, match="result_file_inventory_mismatch"):
        _verify_result_inventory(
            root,
            expected_files={
                "aggregate.json",
                "per_frame_evaluation.jsonl",
                "per_frame_evaluation.csv",
                "SOURCE_INDEPENDENT_EVALUATION_CN.md",
                "SHA256SUMS",
            },
        )


def test_result_inventory_rejects_symbolic_link(tmp_path: Path) -> None:
    root = tmp_path / "result"
    _write_result_fixture(root)
    original = root / "aggregate.json"
    target = tmp_path / "aggregate-target.json"
    original.replace(target)
    original.symlink_to(target)
    with pytest.raises(D3A1V2ExternalAuditError, match="regular_file_required"):
        _verify_result_inventory(root, expected_files={path.name for path in root.iterdir()})


@pytest.mark.skipif(
    not RESULT_INPUT_AVAILABLE,
    reason="frozen D3 A1 v2 result directory is unavailable",
)
def test_csv_tampering_with_rewritten_checksums_still_fails_closure(
    tmp_path: Path,
) -> None:
    result = tmp_path / "result"
    shutil.copytree(RESULT_DIR, result)
    csv_path = result / "per_frame_evaluation.csv"
    with csv_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = tuple(reader.fieldnames or ())
        rows = list(reader)
    rows[0]["negative_exact_r0"] = (
        "0" if rows[0]["negative_exact_r0"] == "1" else "1"
    )
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    _rewrite_result_checksums(result)
    _verify_result_inventory(
        result,
        expected_files={path.name for path in result.iterdir()},
    )
    jsonl_rows = tuple(
        json.loads(line)
        for line in (result / "per_frame_evaluation.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    )
    with pytest.raises(
        D3A1V2ExternalAuditError,
        match="evaluation_csv_jsonl_mismatch",
    ):
        _audit_frame_csv(csv_path, jsonl_rows)


def test_inputs_reject_dataset_outside_generation_root(tmp_path: Path) -> None:
    generation = tmp_path / "generation"
    (generation / "learning_dataset/d3_assignment").mkdir(parents=True)
    wrong_dataset = tmp_path / "wrong_dataset"
    wrong_dataset.mkdir()
    result = tmp_path / "result"
    result.mkdir()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    with pytest.raises(
        D3A1V2ExternalAuditError,
        match="dataset_generation_path_mismatch",
    ):
        D3A1V2ExternalAuditInputs(
            repository_root=REPOSITORY_ROOT,
            result_dir=result,
            generation_root=generation,
            dataset_dir=wrong_dataset,
            contract_path=CONTRACT,
            bundle_dir=bundle,
            audit_id="wrong-dataset",
            evaluated_at_utc="2026-07-31T00:00:00Z",
        )


@pytest.mark.parametrize(
    ("dataset", "selected_edges"),
    (
        (_dataset_frame(resource_capacities=(1, 1)), [[0, 0], [1, 0]]),
        (_dataset_frame(action_mask=((True, False), (True, True))), [[0, 1]]),
        (_dataset_frame(target_demand_slots=(2, 1)), [[0, 0]]),
    ),
    ids=("resource_capacity", "hard_mask", "m_to_n_atomicity"),
)
def test_zero_self_report_cannot_hide_selected_edge_safety_violation(
    dataset: _DatasetFrameInfo,
    selected_edges: list[list[int]],
) -> None:
    payload = {
        "selected_edges": selected_edges,
        "duplicate_resource_count": 0,
        "hard_edge_violation_count": 0,
        "m_to_n_atomicity_violation_count": 0,
    }
    with pytest.raises(
        D3A1V2ExternalAuditError,
        match="evaluation_safety_claim_mismatch",
    ):
        _validate_selected_edge_safety_claims(
            payload,
            dataset=dataset,
            label="fixture",
        )


def test_selected_edge_index_out_of_range_is_rejected() -> None:
    payload = {
        "selected_edges": [[2, 0]],
        "duplicate_resource_count": 0,
        "hard_edge_violation_count": 0,
        "m_to_n_atomicity_violation_count": 0,
    }
    with pytest.raises(
        D3A1V2ExternalAuditError,
        match="evaluation_edge_index_out_of_range",
    ):
        _validate_selected_edge_safety_claims(
            payload,
            dataset=_dataset_frame(),
            label="fixture",
        )


def test_rule_cost_matrix_hash_spoof_is_rejected() -> None:
    with pytest.raises(
        D3A1V2ExternalAuditError,
        match="evaluation_rule_cost_matrix_sha256_mismatch",
    ):
        _validate_rule_cost_matrix_hash(
            "a" * 64,
            dataset=_dataset_frame(),
            label="fixture",
        )


def test_evaluation_row_truth_identity_field_is_rejected() -> None:
    row = {"online_truth_use_count": 0, "truth_target_id": "T001"}
    with pytest.raises(
        D3A1V2ExternalAuditError,
        match="evaluation_forbidden_identity_field",
    ):
        _assert_evaluation_identity_free(row, row_number=1)


def test_dataset_split_hash_spoof_or_inventory_change_is_rejected() -> None:
    claimed = _compute_dataset_split_hash(
        {20000: "train"},
        [("scenario-v1", 20000, "episode-1", "train")],
    )
    changed_inventory = _compute_dataset_split_hash(
        {20000: "train"},
        [("scenario-v1", 20000, "episode-2", "train")],
    )
    assert changed_inventory != claimed
    with pytest.raises(
        D3A1V2ExternalAuditError,
        match="dataset_split_hash_mismatch",
    ):
        _validate_dataset_split_hash(claimed, changed_inventory)


def test_forbidden_truth_actor_and_object_identity_fields_are_detected() -> None:
    value = {
        "truth_target_id": "T001",
        "nested": {"actor_name": "Actor_1", "object_id": 4},
    }
    findings = _find_forbidden_identity_keys(value)
    assert findings == [
        "$.truth_target_id",
        "$.nested.actor_name",
        "$.nested.object_id",
    ]


def test_count_spoof_cannot_replace_independent_recomputation() -> None:
    metrics = _recompute_metrics(
        [_metric_row(opportunity=True, changed=True), _metric_row(opportunity=False)]
    )
    assert metrics["frame_count"] == 2
    assert metrics["positive_safe_binding_change"]["numerator"] == 1
    spoofed = dict(metrics)
    spoofed["frame_count"] = 999
    with pytest.raises(
        D3A1V2ExternalAuditError,
        match="aggregate_overall_metric_claim_mismatch",
    ):
        _reconcile_metric_claims(
            {
                "overall_metrics": spoofed,
                "source_subgroup_metrics": {},
            },
            {
                "overall_metrics": metrics,
                "source_subgroup_metrics": {},
            },
        )


def test_permission_authority_spoof_is_rejected() -> None:
    with pytest.raises(D3A1V2ExternalAuditError, match="permission_authority_spoof"):
        _require_all_permissions_false(
            {"runtime": True, "assignment": False},
            "fixture",
        )


def test_model_output_count_spoof_is_not_silently_zeroed() -> None:
    row = _metric_row(opportunity=False)
    row["model_outputs"]["plan_output_count"] = 1  # type: ignore[index]
    metrics = _recompute_metrics([row])
    assert metrics["model_plan_output_count"] == 1


def test_writer_rejects_existing_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "audit"
    output.mkdir()
    with pytest.raises(
        D3A1V2ExternalAuditError,
        match="output_directory_already_exists",
    ):
        write_d3_a1_source_independent_v2_audit(
            output,
            {"fixture": True},
        )


@pytest.mark.skipif(
    not FROZEN_INPUTS_AVAILABLE,
    reason="frozen D3 A1 v2 source-independent inputs are unavailable",
)
def test_frozen_source_independent_v2_result_is_independently_recomputed() -> None:
    inputs = D3A1V2ExternalAuditInputs(
        repository_root=REPOSITORY_ROOT,
        result_dir=RESULT_DIR,
        generation_root=GENERATION_ROOT,
        dataset_dir=DATASET_DIR,
        contract_path=CONTRACT,
        bundle_dir=BUNDLE,
        audit_id="d6-test-d3-a1-v2",
        evaluated_at_utc="2026-07-31T00:00:00Z",
    )
    result = audit_d3_a1_source_independent_v2(inputs)
    overall = result["independent_recomputation"]["overall_metrics"]
    assert overall["frame_count"] == 292
    assert overall["positive_safe_binding_change"] == {
        "available": True,
        "denominator": 110,
        "numerator": 13,
        "rate": 13 / 110,
        "unavailable_reason": None,
    }
    assert overall["positive_teacher_exact_match"]["numerator"] == 8
    assert overall["negative_exact_r0"]["numerator"] == 182
    assert overall["fallback_exact_r0_matrix_count"] == 94
    assert overall["fallback_exact_r0_binding_count"] == 94
    csv_closure = result["independent_recomputation"]["csv_jsonl_closure"]
    assert csv_closure["fixed_column_count"] == 21
    assert csv_closure["matched_row_count"] == 292
    assert csv_closure["mismatch_count"] == 0
    safety = result["independent_recomputation"][
        "independent_selected_edge_safety"
    ]
    assert safety["effective_machine_gate_source"] == (
        "independent_dataset_recomputation"
    )
    assert all(
        value == 0
        for field, value in safety["groups"]["effective"].items()
        if field != "edge_count"
    )
    assert result["dataset_audit"]["split_hash_verified"] is True
    assert result["preregistered_machine_gate"]["passed"] is True
    assert all(value is False for value in result["authorities"].values())
    test_metric = result["independent_recomputation"]["source_subgroup_metrics"][
        "test"
    ]["positive_teacher_exact_match"]
    assert test_metric["numerator"] == 0
    assert test_metric["denominator"] == 25
    assert result["generalization_limit"] == {
        "test_positive_teacher_exact_match_numerator": test_metric["numerator"],
        "test_positive_teacher_exact_match_denominator": test_metric["denominator"],
        "test_positive_teacher_exact_match_rate": test_metric["rate"],
        "interpretation": (
            "测试子组教师完全匹配为0/25；预注册门限仅适用于292帧总体聚合，"
            "本审计不增设结果后门限，也不据此授予运行权限。"
        ),
    }
