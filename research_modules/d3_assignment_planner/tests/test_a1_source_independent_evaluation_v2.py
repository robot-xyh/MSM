from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

import d3_assignment_planner.a1_source_independent_evaluation as evaluator_v1
import d3_assignment_planner.a1_source_independent_evaluation_v2 as evaluator_v2
from d3_assignment_planner.a1_source_independent_evaluation import (
    A1SourceIndependentEvaluationContract,
    A1SourceIndependentEvaluationError,
)
from d3_assignment_planner.a1_source_independent_evaluation_v2 import (
    A1SourceIndependentEvaluationContractV2,
    iter_a1_source_independent_records_v2,
    validate_v2_preserves_v1_contract,
)
from d3_assignment_planner.learning_data import write_learning_dataset

from test_learning_dataset_bundle import _record
from frozen_source_test_support import frozen_git_source_tree_sha256


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
V1_FROZEN_SOURCE_COMMIT = "b6dbb65686fbff6dde381b25e335b0e99ff94a92"
V2_FROZEN_SOURCE_COMMIT = "145ca73f3b65f29178eeff12777c9dbd12d63a51"
OFFICIAL_V1_CONTRACT = (
    MODULE_ROOT
    / "configs"
    / "a1_source_independent_evaluation_contract_v1.json"
)
OFFICIAL_V2_CONTRACT = (
    MODULE_ROOT
    / "configs"
    / "a1_source_independent_evaluation_contract_v2.json"
)
V1_CONTRACT_SHA256 = (
    "63e8492910af0d6575e7c2dc4981171eaf9169c1278bd811395f911ffa746224"
)


def _small_source_v2() -> dict:
    return {
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
                "configured_scenario_target_count": 2,
                "resource_count": 2,
                "duration_s": 3.0,
                "seed_values": [20000, 20001, 20002],
            }
        ],
    }


def _small_v2_payload() -> dict:
    payload = json.loads(OFFICIAL_V2_CONTRACT.read_text(encoding="utf-8"))
    payload["contract_id"] = "unit-source-independent-v2"
    payload["source_dataset"] = _small_source_v2()
    payload["frozen_source"] = {
        "files": [
            "src/d3_assignment_planner/"
            "a1_source_independent_evaluation_v2.py"
        ],
        "tree_sha256": "b" * 64,
        "require_git_clean": True,
    }
    return payload


def _small_v2_contract() -> A1SourceIndependentEvaluationContractV2:
    return A1SourceIndependentEvaluationContractV2.from_dict(
        _small_v2_payload()
    )


def _small_v1_contract() -> A1SourceIndependentEvaluationContract:
    payload = json.loads(OFFICIAL_V1_CONTRACT.read_text(encoding="utf-8"))
    payload["contract_id"] = "unit-source-independent-v1"
    source = _small_source_v2()
    source["cells"] = [
        {
            "scenario_version": item["scenario_version"],
            "target_count": item["configured_scenario_target_count"],
            "resource_count": item["resource_count"],
            "duration_s": item["duration_s"],
            "seed_values": item["seed_values"],
        }
        for item in source["cells"]
    ]
    payload["source_dataset"] = source
    payload["frozen_source"] = {
        "files": [
            "src/d3_assignment_planner/"
            "a1_source_independent_evaluation.py"
        ],
        "tree_sha256": "b" * 64,
        "require_git_clean": True,
    }
    return A1SourceIndependentEvaluationContract.from_dict(payload)


def _write_dataset(
    root: Path,
    target_counts: tuple[int, int, int],
    *,
    resource_counts: tuple[int, int, int] = (2, 2, 2),
):
    records = tuple(
        _record(
            seed,
            f"episode-{seed}",
            target_count=target_count,
            resource_count=resource_count,
            scenario="assignment-aware-2v2-v1",
        )
        for seed, target_count, resource_count in zip(
            (20000, 20001, 20002),
            target_counts,
            resource_counts,
            strict=True,
        )
    )
    write_learning_dataset(
        root,
        records,
        source_kind="scalable_3d_multi_seed_batch",
        minimum_unseen_seed_count=1,
    )
    return evaluator_v1.load_a1_source_independent_manifest(
        contract=_small_v2_contract(),
        dataset_dir=root,
    )


def test_v1_contract_and_source_tree_remain_byte_stable():
    assert sha256(OFFICIAL_V1_CONTRACT.read_bytes()).hexdigest() == (
        V1_CONTRACT_SHA256
    )
    contract = A1SourceIndependentEvaluationContract.from_path(
        OFFICIAL_V1_CONTRACT
    )
    assert frozen_git_source_tree_sha256(
        REPOSITORY_ROOT,
        module_path="research_modules/d3_assignment_planner",
        commit=V1_FROZEN_SOURCE_COMMIT,
        relative_files=tuple(contract.frozen_source["files"]),
    ) == contract.frozen_source["tree_sha256"]


def test_official_v2_preserves_v1_bundle_thresholds_permissions_and_source():
    contract_v1 = A1SourceIndependentEvaluationContract.from_path(
        OFFICIAL_V1_CONTRACT
    )
    contract_v2 = A1SourceIndependentEvaluationContractV2.from_path(
        OFFICIAL_V2_CONTRACT
    )

    validate_v2_preserves_v1_contract(
        contract_v2=contract_v2,
        contract_v1=contract_v1,
    )
    assert contract_v2.status == "evaluator_v2_ready_evaluation_not_run"
    assert not any(contract_v2.permissions.values())
    assert all(
        "configured_scenario_target_count" in cell.to_dict()
        and "target_count" not in cell.to_dict()
        for cell in contract_v2.cells
    )
    assert frozen_git_source_tree_sha256(
        REPOSITORY_ROOT,
        module_path="research_modules/d3_assignment_planner",
        commit=V2_FROZEN_SOURCE_COMMIT,
        relative_files=tuple(contract_v2.frozen_source["files"]),
    ) == contract_v2.frozen_source["tree_sha256"]


def test_v2_rejects_any_v1_threshold_or_permission_change():
    contract_v1 = A1SourceIndependentEvaluationContract.from_path(
        OFFICIAL_V1_CONTRACT
    )
    payload = _small_v2_payload()
    payload["thresholds"]["minimum_negative_exact_r0_rate"] = 0.98
    changed = A1SourceIndependentEvaluationContractV2.from_dict(payload)
    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        validate_v2_preserves_v1_contract(
            contract_v2=changed,
            contract_v1=contract_v1,
        )
    assert error.value.code == "contract_v2_thresholds_differ_from_v1"

    payload = _small_v2_payload()
    payload["permissions"]["assist"] = True
    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        A1SourceIndependentEvaluationContractV2.from_dict(payload)
    assert error.value.code == "contract_permission_escalation_forbidden"


def test_v2_accepts_observed_target_count_below_equal_and_above_configured(
    tmp_path: Path,
):
    dataset = tmp_path / "dataset"
    manifest = _write_dataset(dataset, (1, 2, 3))

    records = tuple(
        iter_a1_source_independent_records_v2(
            contract=_small_v2_contract(),
            dataset_dir=dataset,
            manifest=manifest,
        )
    )

    assert sorted(len(record.anonymous_targets) for record in records) == [
        1,
        2,
        3,
    ]
    assert all(len(record.anonymous_resources) == 2 for record in records)


def test_v1_retains_historical_configured_target_equality_failure(
    tmp_path: Path,
):
    dataset = tmp_path / "dataset"
    manifest = _write_dataset(dataset, (1, 2, 3))

    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        tuple(
            evaluator_v1.iter_a1_source_independent_records(
                contract=_small_v1_contract(),
                dataset_dir=dataset,
                manifest=manifest,
            )
        )
    assert error.value.code == "source_scenario_scale_mismatch"


def test_v2_resource_count_mismatch_fails_with_anonymous_context(
    tmp_path: Path,
):
    dataset = tmp_path / "dataset"
    manifest = _write_dataset(
        dataset,
        (1, 2, 3),
        resource_counts=(1, 2, 2),
    )

    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        tuple(
            iter_a1_source_independent_records_v2(
                contract=_small_v2_contract(),
                dataset_dir=dataset,
                manifest=manifest,
            )
        )

    assert error.value.code == "source_configured_resource_count_mismatch_v2"
    message = str(error.value)
    assert '"observed_anonymous_resource_count":1' in message
    assert '"configured_resource_count":2' in message
    assert '"rule_cost_matrix_shape":[1,1]' in message
    assert "truth" not in message.lower()


def test_v2_matrix_shape_mismatch_fails_with_raw_shape_context(
    tmp_path: Path,
):
    dataset = tmp_path / "dataset"
    manifest = _write_dataset(dataset, (2, 2, 2))
    frames_path = dataset / "frames.jsonl"
    rows = frames_path.read_text(encoding="ascii").splitlines()
    first = json.loads(rows[0])
    first["rule_cost_matrix"] = [[0.1], [0.2]]
    rows[0] = json.dumps(
        first,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    frames_path.write_text("\n".join(rows) + "\n", encoding="ascii")

    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        tuple(
            iter_a1_source_independent_records_v2(
                contract=_small_v2_contract(),
                dataset_dir=dataset,
                manifest=manifest,
            )
        )

    assert error.value.code == "source_dataset_frame_invalid_v2"
    message = str(error.value)
    assert '"rule_cost_matrix_shape":{"column_counts":[1],"rows":2}' in message
    assert '"action_mask_shape":{"column_counts":[2],"rows":2}' in message
    assert "truth" not in message.lower()


def test_v2_unregistered_seed_and_cell_scenario_mismatch_fail_closed(
    tmp_path: Path,
):
    dataset = tmp_path / "dataset"
    manifest = _write_dataset(dataset, (2, 2, 2))
    frames_path = dataset / "frames.jsonl"
    rows = frames_path.read_text(encoding="ascii").splitlines()
    first = json.loads(rows[0])
    original_seed = int(first["seed"])
    original_split = str(first["split"])
    first["seed"] = 29999
    rows[0] = json.dumps(
        first,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    frames_path.write_text("\n".join(rows) + "\n", encoding="ascii")
    split_seed_values = {
        split: tuple(
            sorted(
                29999 if seed == original_seed else seed
                for seed in manifest.split_seed_values[split]
            )
        )
        for split in ("train", "validation", "test")
    }
    assert 29999 in split_seed_values[original_split]
    altered_manifest = replace(
        manifest,
        split_seed_values=split_seed_values,
    )

    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        tuple(
            iter_a1_source_independent_records_v2(
                contract=_small_v2_contract(),
                dataset_dir=dataset,
                manifest=altered_manifest,
            )
        )
    assert error.value.code == "source_record_seed_unregistered"
    assert '"seed":29999' in str(error.value)

    clean_dataset = tmp_path / "clean"
    clean_manifest = _write_dataset(clean_dataset, (2, 2, 2))
    payload = _small_v2_payload()
    payload["source_dataset"]["cells"][0]["scenario_version"] = (
        "different-2v2-v1"
    )
    different_cell = A1SourceIndependentEvaluationContractV2.from_dict(
        payload
    )
    with pytest.raises(A1SourceIndependentEvaluationError) as error:
        tuple(
            iter_a1_source_independent_records_v2(
                contract=different_cell,
                dataset_dir=clean_dataset,
                manifest=clean_manifest,
            )
        )
    assert error.value.code == "source_scenario_version_mismatch"
    assert '"scenario":"assignment-aware-2v2-v1"' in str(error.value)


def test_v2_module_exposes_no_training_or_selection_entry_point():
    forbidden_prefixes = (
        "train_",
        "fit_",
        "optimize_",
        "select_checkpoint",
        "save_checkpoint",
    )
    public_callables = {
        name
        for name, value in vars(evaluator_v2).items()
        if not name.startswith("_") and callable(value)
    }

    assert not any(
        name.startswith(forbidden_prefixes)
        for name in public_callables
    )
