from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

import numpy as np
import pytest

import d3_assignment_planner.a1_source_independent_evaluation as evaluator
from d3_assignment_planner import (
    A1_SOURCE_INDEPENDENT_MODE,
    A1AssignmentAwareConfig,
    A1SourceIndependentEvaluationContract,
    A1SourceIndependentEvaluationError,
    EDGE_FEATURE_NAMES,
    LearningDatasetManifest,
    aggregate_a1_source_independent_rows,
    iter_a1_source_independent_records,
    load_a1_source_independent_manifest,
    run_a1_source_independent_evaluation,
    source_tree_sha256,
    validate_a1_source_independent_bundle,
    validate_a1_source_independent_input,
    write_learning_dataset,
)

from test_a1_assignment_aware_development import _assignment_aware_record
from frozen_source_test_support import frozen_git_source_tree_sha256


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
V1_FROZEN_SOURCE_COMMIT = "b6dbb65686fbff6dde381b25e335b0e99ff94a92"
OFFICIAL_CONTRACT = (
    MODULE_ROOT
    / "configs"
    / "a1_source_independent_evaluation_contract_v1.json"
)
FROZEN_BUNDLE = (
    MODULE_ROOT
    / "results"
    / "a1_assignment_aware_development_v1_20260730"
    / "bundle"
)


def _small_contract_payload() -> dict:
    import json

    payload = json.loads(OFFICIAL_CONTRACT.read_text(encoding="utf-8"))
    payload["contract_id"] = "unit-source-independent-v1"
    payload["source_dataset"] = {
        "dataset_schema_version": "d3_learning_dataset_v2",
        "split_policy_version": "d3_numeric_seed_atomic_split_v2",
        "source_kind": "scalable_3d_multi_seed_batch",
        "generation_schedule_sha256": "a" * 64,
        "episode_count": 3,
        "unique_seed_count": 3,
        "seed_values": [20000, 20001, 20002],
        "split_seed_counts": {
            "train": 1,
            "validation": 1,
            "test": 1,
        },
        "training_seed_values": [0],
        "formal_holdout_seed_values": list(range(1000, 1020)),
        "cells": [
            {
                "scenario_version": "assignment-aware-2v2-v1",
                "target_count": 2,
                "resource_count": 2,
                "duration_s": 3.0,
                "seed_values": [20000, 20001, 20002],
            }
        ],
    }
    payload["frozen_source"] = {
        "files": [
            "src/d3_assignment_planner/"
            "a1_source_independent_evaluation.py"
        ],
        "tree_sha256": "b" * 64,
        "require_git_clean": True,
    }
    return payload


def _small_contract() -> A1SourceIndependentEvaluationContract:
    return A1SourceIndependentEvaluationContract.from_dict(
        _small_contract_payload()
    )


def _manifest() -> LearningDatasetManifest:
    return LearningDatasetManifest(
        schema_version="d3_learning_dataset_v2",
        split_policy_version="d3_numeric_seed_atomic_split_v2",
        feature_names=EDGE_FEATURE_NAMES,
        split_hash="c" * 64,
        frames_sha256="d" * 64,
        frame_count=3,
        episode_count=3,
        unique_seed_count=3,
        split_frame_counts={"train": 1, "validation": 1, "test": 1},
        split_episode_counts={"train": 1, "validation": 1, "test": 1},
        split_seed_values={
            "train": (20000,),
            "validation": (20001,),
            "test": (20002,),
        },
        split_seed=20260720,
        validation_fraction=0.2,
        test_fraction=0.2,
        minimum_unseen_seed_count=1,
        unseen_test_seed_count=1,
        source_kind="scalable_3d_multi_seed_batch",
    )


def _row(
    split: str,
    *,
    opportunity: bool,
    changed: bool,
    rejected: bool = False,
    exact_matrix: bool = True,
    exact_binding: bool = True,
) -> dict:
    r0_edges = [[0, 0]]
    changed_edges = [[0, 1]]
    effective_edges = changed_edges if changed else r0_edges
    teacher_edges = changed_edges if opportunity else r0_edges
    reasons = ["feature_ood"] if rejected else []
    return {
        "source_split": split,
        "scenario_version": "assignment-aware-2v2-v1",
        "input_finite": True,
        "teacher": {
            "opportunity": opportunity,
            "selected_edges": teacher_edges,
        },
        "candidate": {
            "maximum_abs_cost_correction": 0.01 if changed else 0.0,
        },
        "effective": {
            "selected_edges": effective_edges,
            "binding_change_count_from_r0": 2 if changed else 0,
            "exact_r0_binding": exact_binding,
            "exact_r0_matrix": exact_matrix,
            "duplicate_resource_count": 0,
            "hard_edge_violation_count": 0,
            "m_to_n_atomicity_violation_count": 0,
        },
        "r0_rule_matrix_mutated": False,
        "ood": rejected,
        "rejected": rejected,
        "rejection_reasons": reasons,
        "rejection_reason_count": len(reasons),
        "permissions": dict(evaluator._CLOSED_PERMISSIONS),
        "model_outputs": {
            "assignment_output_count": 0,
            "plan_output_count": 0,
            "version_output_count": 0,
            "runtime_output_count": 0,
        },
    }


def _aggregate(rows: tuple[dict, ...]) -> dict:
    contract = _small_contract()
    return dict(
        aggregate_a1_source_independent_rows(
            rows,
            contract=contract,
            source_audit={
                "generation_cell_count": 3,
                "generation_finite_failure_count": 0,
                "generation_online_truth_use_count": 0,
                "dataset_truth_field_count": 0,
                "dataset_manifest_sha256": "e" * 64,
            },
            dataset_manifest=_manifest(),
            model_summary={
                **dict(contract.frozen_bundle),
                "normalization_refit_count": 0,
                "model_weight_update_count": 0,
            },
            source_summary={
                "evaluator_source_tree_sha256": "b" * 64,
                "contract_sha256": contract.contract_sha256,
            },
        )
    )


def _write_generation_fixture(root: Path, *, truth_use_count: int = 0) -> Path:
    import json

    contract = _small_contract()
    cells = [
        {
            "scenario": "assignment-aware",
            "scale": 2,
            "seed": seed,
            "duration_s": 3.0,
        }
        for seed in contract.seed_values
    ]
    root.mkdir()
    dataset = root / "learning_dataset" / "d3_assignment"
    dataset.mkdir(parents=True)
    (dataset / "dataset_manifest.json").write_text("{}\n", encoding="utf-8")
    (dataset / "frames.jsonl").write_text("{}\n", encoding="utf-8")
    values = {
        "generation_plan.json": {
            "schedule_sha256": "a" * 64,
            "repository_dirty": False,
            "cell_count": 3,
            "cells": cells,
            "reserved_evaluation_seeds": list(range(1000, 1020)),
        },
        "generation_summary.json": {
            "repository_dirty": False,
            "completed_episode_count": 3,
        },
        "generation_checkpoint.json": {
            "state": "finalized",
            "completed_episode_count": 3,
        },
    }
    for filename, value in values.items():
        (root / filename).write_text(
            json.dumps(value, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    with (root / "episode_progress.jsonl").open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as stream:
        for index, cell in enumerate(cells):
            row = {
                **cell,
                "finite_state": True,
                "online_truth_use_count": (
                    truth_use_count if index == 0 else 0
                ),
            }
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    return dataset


def test_official_contract_freezes_bundle_source_and_thresholds():
    contract = A1SourceIndependentEvaluationContract.from_path(
        OFFICIAL_CONTRACT
    )

    assert contract.mode == A1_SOURCE_INDEPENDENT_MODE
    assert contract.status == "evaluator_ready_evaluation_not_run"
    assert contract.frozen_bundle["manifest_sha256"] == (
        "ec9f93d668e1aa319f65fcda0d73adb0527f316a2d1880e93e88697b6468ad3d"
    )
    assert contract.frozen_bundle["state_dict_sha256"] == (
        "c185823bd9a4cf5363d17854385aeb74c340c8ac384327281d224a1097eb8206"
    )
    assert contract.frozen_bundle["tree_sha256"] == (
        "de7b627df9782d7d2577687f30d02d4faeeaf577ecc557c2b8d91dd6e7115dd9"
    )
    assert contract.seed_values == tuple(range(20000, 20100))
    assert contract.thresholds == {
        "minimum_positive_safe_binding_change_count": 1,
        "minimum_positive_safe_binding_change_rate": 0.05,
        "minimum_positive_teacher_exact_match_count": 1,
        "minimum_positive_teacher_exact_match_rate": 0.02,
        "minimum_negative_exact_r0_rate": 0.99,
    }
    assert not any(contract.permissions.values())
    assert frozen_git_source_tree_sha256(
        REPOSITORY_ROOT,
        module_path="research_modules/d3_assignment_planner",
        commit=V1_FROZEN_SOURCE_COMMIT,
        relative_files=tuple(contract.frozen_source["files"]),
    ) == contract.frozen_source["tree_sha256"]


def test_frozen_bundle_loads_only_for_read_only_evaluation():
    pytest.importorskip("torch")
    loaded = validate_a1_source_independent_bundle(
        contract=A1SourceIndependentEvaluationContract.from_path(
            OFFICIAL_CONTRACT
        ),
        bundle_dir=FROZEN_BUNDLE,
    )

    assert loaded.loaded is True
    assert loaded.mode == A1_SOURCE_INDEPENDENT_MODE
    assert loaded.assist_authorized is False
    assert loaded.authority_granted is False
    assert loaded.production_admission_granted is False


def test_bundle_tamper_and_wrong_expected_summary_fail_closed(tmp_path: Path):
    pytest.importorskip("torch")
    copied = tmp_path / "bundle"
    shutil.copytree(FROZEN_BUNDLE, copied)
    state = copied / "state_dict.json"
    state.write_bytes(state.read_bytes() + b"tamper")
    contract = A1SourceIndependentEvaluationContract.from_path(
        OFFICIAL_CONTRACT
    )

    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        validate_a1_source_independent_bundle(
            contract=contract,
            bundle_dir=copied,
        )
    assert error.value.code == "frozen_bundle_load_failed"

    payload = _small_contract_payload()
    payload["frozen_bundle"]["manifest_sha256"] = "f" * 64
    wrong = A1SourceIndependentEvaluationContract.from_dict(payload)
    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        validate_a1_source_independent_bundle(
            contract=wrong,
            bundle_dir=FROZEN_BUNDLE,
        )
    assert error.value.code == "frozen_bundle_load_failed"


def test_contract_rejects_seed_overlap_and_permission_escalation():
    payload = _small_contract_payload()
    payload["source_dataset"]["training_seed_values"] = [20000]
    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        A1SourceIndependentEvaluationContract.from_dict(payload)
    assert error.value.code == "contract_seed_separation_invalid"

    payload = _small_contract_payload()
    payload["permissions"]["assist"] = True
    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        A1SourceIndependentEvaluationContract.from_dict(payload)
    assert error.value.code == "contract_permission_escalation_forbidden"


def test_generation_truth_use_is_rejected(tmp_path: Path):
    root = tmp_path / "generation"
    dataset = _write_generation_fixture(root, truth_use_count=1)

    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        validate_a1_source_independent_input(
            contract=_small_contract(),
            generation_root=root,
            dataset_dir=dataset,
        )
    assert error.value.code == "generation_online_truth_use_nonzero"


def test_generation_evidence_records_zero_truth_and_source_hashes(
    tmp_path: Path,
):
    root = tmp_path / "generation"
    dataset = _write_generation_fixture(root)

    result = validate_a1_source_independent_input(
        contract=_small_contract(),
        generation_root=root,
        dataset_dir=dataset,
    )

    assert result["generation_cell_count"] == 3
    assert result["generation_online_truth_use_count"] == 0
    assert result["dataset_truth_field_count"] == 0
    assert len(result["dataset_manifest_sha256"]) == 64
    assert len(result["dataset_frames_sha256"]) == 64


def test_dataset_records_are_validated_and_streamed_without_materializing(
    tmp_path: Path,
):
    dataset = tmp_path / "dataset"
    records = tuple(
        replace(
            _assignment_aware_record(
                seed,
                "train",
                opportunity=(seed % 2 == 0),
            ),
            split="unassigned",
        )
        for seed in (20000, 20001, 20002)
    )
    write_learning_dataset(
        dataset,
        records,
        source_kind="scalable_3d_multi_seed_batch",
        minimum_unseen_seed_count=1,
    )
    contract = _small_contract()

    manifest = load_a1_source_independent_manifest(
        contract=contract,
        dataset_dir=dataset,
    )
    loaded = tuple(
        iter_a1_source_independent_records(
            contract=contract,
            dataset_dir=dataset,
            manifest=manifest,
        )
    )

    assert len(loaded) == 3
    assert {record.seed for record in loaded} == {20000, 20001, 20002}
    assert {record.split for record in loaded} == {
        "train",
        "validation",
        "test",
    }


def test_test_split_is_evaluated_as_source_independent_subgroup():
    pytest.importorskip("torch")
    contract = A1SourceIndependentEvaluationContract.from_path(
        OFFICIAL_CONTRACT
    )
    loaded = validate_a1_source_independent_bundle(
        contract=contract,
        bundle_dir=FROZEN_BUNDLE,
    )
    record = _assignment_aware_record(
        20000,
        "test",
        opportunity=True,
    )
    manifest = loaded.manifest
    config = A1AssignmentAwareConfig(**dict(manifest["configuration"]))
    row = evaluator._evaluate_source_independent_frame(
        record,
        policy=loaded.policy,
        normalization_mean=np.asarray(
            manifest["normalization"]["mean"],
            dtype=np.float32,
        ),
        normalization_scale=np.asarray(
            manifest["normalization"]["scale"],
            dtype=np.float32,
        ),
        config=config,
        permissions=contract.permissions,
    )

    assert row["source_split"] == "test"
    assert row["evaluation_group"] == A1_SOURCE_INDEPENDENT_MODE
    assert row["evaluation_subgroup"].endswith("/test")
    assert row["online_truth_use_count"] == 0
    assert not any(row["permissions"].values())
    assert row["model_outputs"]["assignment_output_count"] == 0
    assert row["model_outputs"]["plan_output_count"] == 0


def test_writer_emits_all_artifacts_checksums_and_refuses_overwrite(
    tmp_path: Path,
):
    pytest.importorskip("torch")
    official = A1SourceIndependentEvaluationContract.from_path(
        OFFICIAL_CONTRACT
    )
    loaded = validate_a1_source_independent_bundle(
        contract=official,
        bundle_dir=FROZEN_BUNDLE,
    )
    manifest = loaded.manifest
    config = A1AssignmentAwareConfig(**dict(manifest["configuration"]))
    rows = tuple(
        evaluator._evaluate_source_independent_frame(
            _assignment_aware_record(
                seed,
                split,
                opportunity=(split == "train"),
            ),
            policy=loaded.policy,
            normalization_mean=np.asarray(
                manifest["normalization"]["mean"],
                dtype=np.float32,
            ),
            normalization_scale=np.asarray(
                manifest["normalization"]["scale"],
                dtype=np.float32,
            ),
            config=config,
            permissions=_small_contract().permissions,
        )
        for seed, split in zip(
            (20000, 20001, 20002),
            ("train", "validation", "test"),
            strict=True,
        )
    )
    aggregate = _aggregate(tuple(dict(row) for row in rows))
    output = tmp_path / "evaluation"
    evaluator._write_evaluation_outputs(
        output,
        rows=rows,
        aggregate=aggregate,
        contract=_small_contract(),
    )

    assert {path.name for path in output.iterdir()} == {
        "per_frame_evaluation.jsonl",
        "per_frame_evaluation.csv",
        "aggregate.json",
        "SOURCE_INDEPENDENT_EVALUATION_CN.md",
        "SHA256SUMS",
    }
    checksum_lines = (output / "SHA256SUMS").read_text(
        encoding="ascii"
    ).splitlines()
    assert len(checksum_lines) == 4
    assert all("  SHA256SUMS" not in line for line in checksum_lines)
    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        evaluator._write_evaluation_outputs(
            output,
            rows=rows,
            aggregate=aggregate,
            contract=_small_contract(),
        )
    assert error.value.code == "evaluation_output_already_exists"


def test_preregistered_machine_gates_pass_for_complete_synthetic_rows():
    result = _aggregate(
        (
            _row("train", opportunity=True, changed=True),
            _row("validation", opportunity=False, changed=False),
            _row("test", opportunity=False, changed=False),
        )
    )

    assert result["machine_gate_passed"] is True
    assert result["overall_metrics"]["positive_safe_binding_change"] == {
        "numerator": 1,
        "denominator": 1,
        "rate": 1.0,
        "available": True,
        "unavailable_reason": None,
    }
    assert result["overall_metrics"]["negative_exact_r0"]["rate"] == 1.0
    assert result["formal_admission_granted"] is False
    assert result["runtime_adoption_granted"] is False


@pytest.mark.parametrize("empty_kind", ("positive", "negative"))
def test_empty_denominator_is_explicit_and_fails_gate(empty_kind: str):
    if empty_kind == "positive":
        rows = (
            _row("train", opportunity=False, changed=False),
            _row("validation", opportunity=False, changed=False),
            _row("test", opportunity=False, changed=False),
        )
        metric_name = "positive_safe_binding_change"
        gate_name = "positive_denominator_nonzero"
    else:
        rows = (
            _row("train", opportunity=True, changed=True),
            _row("validation", opportunity=True, changed=True),
            _row("test", opportunity=True, changed=True),
        )
        metric_name = "negative_exact_r0"
        gate_name = "negative_denominator_nonzero"

    result = _aggregate(rows)

    metric = result["overall_metrics"][metric_name]
    assert metric["denominator"] == 0
    assert metric["rate"] is None
    assert metric["available"] is False
    assert metric["unavailable_reason"] == "denominator_zero"
    assert result["machine_gate"][gate_name] is False
    assert result["machine_gate_passed"] is False


def test_fallback_mismatch_and_row_permission_escalation_fail_gate():
    rows = [
        _row("train", opportunity=True, changed=True),
        _row(
            "validation",
            opportunity=False,
            changed=False,
            rejected=True,
            exact_matrix=False,
            exact_binding=False,
        ),
        _row("test", opportunity=False, changed=False),
    ]
    rows[2]["permissions"]["assist"] = True
    rows[2]["model_outputs"]["assignment_output_count"] = 1

    result = _aggregate(tuple(rows))

    assert result["machine_gate"]["fallback_matrix_exact_r0"] is False
    assert result["machine_gate"]["fallback_binding_exact_r0"] is False
    assert result["machine_gate"]["all_permissions_false"] is False
    assert result["machine_gate"]["zero_model_assignment_output"] is False
    assert result["machine_gate_passed"] is False


def test_output_directory_refuses_repeat_before_reading_inputs(tmp_path: Path):
    output = tmp_path / "already-exists"
    output.mkdir()

    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        run_a1_source_independent_evaluation(
            contract_path=tmp_path / "missing-contract.json",
            bundle_dir=tmp_path / "missing-bundle",
            generation_root=tmp_path / "missing-generation",
            dataset_dir=tmp_path / "missing-dataset",
            output_dir=output,
            module_root=MODULE_ROOT,
            mode=A1_SOURCE_INDEPENDENT_MODE,
        )
    assert error.value.code == "evaluation_output_already_exists"


def test_mode_other_than_source_independent_is_rejected(tmp_path: Path):
    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        run_a1_source_independent_evaluation(
            contract_path=OFFICIAL_CONTRACT,
            bundle_dir=FROZEN_BUNDLE,
            generation_root=tmp_path / "generation",
            dataset_dir=tmp_path / "dataset",
            output_dir=tmp_path / "output",
            module_root=MODULE_ROOT,
            mode="shadow",
        )
    assert error.value.code == "source_independent_mode_required"


def test_source_inventory_digest_changes_after_tamper(tmp_path: Path):
    (tmp_path / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    first = source_tree_sha256(tmp_path, ("a.py",))
    (tmp_path / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    second = source_tree_sha256(tmp_path, ("a.py",))

    assert first != second


def test_evaluator_module_has_no_training_or_selection_entry_point():
    forbidden_prefixes = (
        "train_",
        "fit_",
        "optimize_",
        "select_checkpoint",
        "save_checkpoint",
    )
    public_callables = {
        name
        for name, value in vars(evaluator).items()
        if not name.startswith("_") and callable(value)
    }

    assert not any(
        name.startswith(forbidden_prefixes)
        for name in public_callables
    )
