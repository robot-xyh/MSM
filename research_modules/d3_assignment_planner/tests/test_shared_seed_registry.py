from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d3_assignment_planner import (
    SHARED_SEED_SPLIT_BINDING_SCHEMA_VERSION,
    SHARED_SEED_SPLIT_POLICY_VERSION,
    SHARED_SEED_SPLIT_SCHEMA_VERSION,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
    SharedSeedSplitBindingError,
    assign_seed_splits,
    load_learning_dataset,
    validate_shared_seed_split_binding,
    write_learning_dataset,
)
from d3_assignment_planner.learning_cli import main as learning_cli_main

from test_learning_dataset_bundle import _record


def _canonical_sha(value: object) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rehash_registry(value: dict, *, assignment: bool = True) -> None:
    if assignment:
        value["assignment_sha256"] = _canonical_sha(value["assignments"])
    body = dict(value)
    body.pop("content_sha256", None)
    value["content_sha256"] = _canonical_sha(body)


def _shared_fixture(
    tmp_path: Path,
    *,
    dataset_seeds: tuple[int, ...] = tuple(range(10)),
) -> tuple[Path, Path, Path]:
    training_seeds = tuple(range(10))
    reserved_seeds = (1000, 1001)
    source = {
        "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "git_commit": "a" * 40,
        "repository_dirty": False,
        "schedule_sha256": "b" * 64,
        "training_seed_count": len(training_seeds),
        "training_seeds": list(training_seeds),
        "reserved_evaluation_seed_count": len(reserved_seeds),
        "reserved_evaluation_seeds": list(reserved_seeds),
        "overlap_count": 0,
    }
    source_path = tmp_path / "training_seed_registry.json"
    _write_json(source_path, source)
    source_sha = sha256(source_path.read_bytes()).hexdigest()

    split_by_seed = dict(
        assign_seed_splits(
            training_seeds,
            split_seed=20260720,
            validation_fraction=0.2,
            test_fraction=0.2,
            minimum_unseen_seed_count=1,
        )
    )
    assignments = [
        {"seed": seed, "split": split_by_seed[seed]} for seed in training_seeds
    ]
    registry = {
        "schema_version": SHARED_SEED_SPLIT_SCHEMA_VERSION,
        "policy_version": SHARED_SEED_SPLIT_POLICY_VERSION,
        "ordering_compatibility_version": "d3_numeric_seed_atomic_split_v2",
        "source": {
            "training_seed_registry_schema_version": (
                TRAINING_SEED_REGISTRY_SCHEMA_VERSION
            ),
            "training_seed_registry_sha256": source_sha,
            "git_commit": source["git_commit"],
            "repository_dirty": source["repository_dirty"],
            "schedule_sha256": source["schedule_sha256"],
        },
        "unit": "numeric_seed_atomic_across_modules_scenarios_and_scales",
        "split_seed": 20260720,
        "validation_fraction": 0.2,
        "test_fraction": 0.2,
        "minimum_test_seed_count": 1,
        "training_seed_count": len(training_seeds),
        "reserved_evaluation_seed_count": len(reserved_seeds),
        "reserved_evaluation_seeds": list(reserved_seeds),
        "training_reserved_overlap_count": 0,
        "split_seed_values": {
            split: [seed for seed in training_seeds if split_by_seed[seed] == split]
            for split in ("train", "validation", "test")
        },
        "assignments": assignments,
        "assignment_sha256": _canonical_sha(assignments),
        "consumer_contract": {
            "original_dataset_mutation_allowed": False,
            "module_local_split_override_allowed": False,
            "cross_module_training_requires_exact_registry": True,
            "reserved_evaluation_seeds_allowed": False,
        },
    }
    _rehash_registry(registry)
    registry_path = tmp_path / "shared_seed_split_registry.json"
    _write_json(registry_path, registry)

    dataset = tmp_path / "dataset"
    write_learning_dataset(
        dataset,
        (_record(seed, f"episode_{seed}") for seed in dataset_seeds),
        source_kind="unit_shared_registry_fixture",
        split_seed=20260720,
        validation_fraction=0.2,
        test_fraction=0.2,
        minimum_unseen_seed_count=1,
    )
    return dataset, registry_path, source_path


def test_shared_registry_exact_mapping_is_read_only_and_old_loader_stays_compatible(
    tmp_path: Path,
) -> None:
    dataset, registry, source = _shared_fixture(tmp_path)
    paths = (
        dataset / "dataset_manifest.json",
        dataset / "frames.jsonl",
        registry,
        source,
    )
    before = {path: path.read_bytes() for path in paths}

    manifest, records = load_learning_dataset(
        dataset,
        shared_seed_registry_path=registry,
        training_seed_registry_path=source,
    )
    binding = validate_shared_seed_split_binding(
        manifest,
        records,
        registry_path=registry,
        training_seed_registry_path=source,
    )
    legacy_manifest, legacy_records = load_learning_dataset(dataset)

    assert binding.to_dict()["schema_version"] == (
        SHARED_SEED_SPLIT_BINDING_SCHEMA_VERSION
    )
    assert binding.to_dict()["joint_training_split_eligible"] is True
    assert binding.to_dict()["training_seed_count"] == 10
    assert binding.to_dict()["split_seed_counts"] == {
        "train": 6,
        "validation": 2,
        "test": 2,
    }
    assert legacy_manifest == manifest
    assert [item.to_dict() for item in legacy_records] == [
        item.to_dict() for item in records
    ]
    assert {path: path.read_bytes() for path in paths} == before


def test_loader_requires_registry_and_source_as_one_pair(tmp_path: Path) -> None:
    dataset, registry, source = _shared_fixture(tmp_path)
    with pytest.raises(ValueError, match="must be provided together"):
        load_learning_dataset(dataset, shared_seed_registry_path=registry)
    with pytest.raises(ValueError, match="must be provided together"):
        load_learning_dataset(dataset, training_seed_registry_path=source)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("schema_version", "tampered-schema", "registry_schema_mismatch"),
        ("policy_version", "tampered-policy", "registry_policy_mismatch"),
    ],
)
def test_shared_registry_rejects_schema_and_policy_changes(
    tmp_path: Path,
    field: str,
    value: str,
    code: str,
) -> None:
    dataset, registry, source = _shared_fixture(tmp_path)
    raw = json.loads(registry.read_text(encoding="utf-8"))
    raw[field] = value
    _rehash_registry(raw)
    _write_json(registry, raw)
    manifest, records = load_learning_dataset(dataset)

    with pytest.raises(SharedSeedSplitBindingError) as caught:
        validate_shared_seed_split_binding(
            manifest,
            records,
            registry_path=registry,
            training_seed_registry_path=source,
        )
    assert caught.value.code == code


def test_shared_registry_rejects_content_and_assignment_hash_tamper(
    tmp_path: Path,
) -> None:
    dataset, registry, source = _shared_fixture(tmp_path)
    manifest, records = load_learning_dataset(dataset)
    raw = json.loads(registry.read_text(encoding="utf-8"))
    original_split = raw["assignments"][0]["split"]
    raw["assignments"][0]["split"] = (
        "test" if original_split != "test" else "train"
    )
    _write_json(registry, raw)
    with pytest.raises(SharedSeedSplitBindingError) as caught:
        validate_shared_seed_split_binding(
            manifest,
            records,
            registry_path=registry,
            training_seed_registry_path=source,
        )
    assert caught.value.code == "registry_content_sha256_mismatch"

    _rehash_registry(raw, assignment=False)
    _write_json(registry, raw)
    with pytest.raises(SharedSeedSplitBindingError) as caught:
        validate_shared_seed_split_binding(
            manifest,
            records,
            registry_path=registry,
            training_seed_registry_path=source,
        )
    assert caught.value.code == "assignment_sha256_mismatch"


def test_shared_registry_rejects_self_consistent_but_different_assignment(
    tmp_path: Path,
) -> None:
    dataset, registry, source = _shared_fixture(tmp_path)
    manifest, records = load_learning_dataset(dataset)
    raw = json.loads(registry.read_text(encoding="utf-8"))
    first = next(item for item in raw["assignments"] if item["split"] == "train")
    second = next(item for item in raw["assignments"] if item["split"] == "test")
    first["split"], second["split"] = second["split"], first["split"]
    raw["split_seed_values"] = {
        split: [
            item["seed"] for item in raw["assignments"] if item["split"] == split
        ]
        for split in ("train", "validation", "test")
    }
    _rehash_registry(raw)
    _write_json(registry, raw)

    with pytest.raises(SharedSeedSplitBindingError) as caught:
        validate_shared_seed_split_binding(
            manifest,
            records,
            registry_path=registry,
            training_seed_registry_path=source,
        )
    assert caught.value.code == "assignment_policy_reproduction_mismatch"


def test_shared_registry_rejects_source_sha_mismatch(tmp_path: Path) -> None:
    dataset, registry, source = _shared_fixture(tmp_path)
    source.write_bytes(source.read_bytes() + b" ")
    manifest, records = load_learning_dataset(dataset)

    with pytest.raises(SharedSeedSplitBindingError) as caught:
        validate_shared_seed_split_binding(
            manifest,
            records,
            registry_path=registry,
            training_seed_registry_path=source,
        )
    assert caught.value.code == "source_training_registry_sha256_mismatch"


@pytest.mark.parametrize(
    ("dataset_seeds", "expected_code"),
    [
        (tuple(range(9)), "dataset_manifest_seed_coverage_mismatch"),
        (tuple(range(11)), "dataset_manifest_seed_coverage_mismatch"),
        ((*range(9), 1000), "reserved_seed_in_dataset"),
    ],
)
def test_shared_registry_rejects_missing_extra_and_reserved_dataset_seeds(
    tmp_path: Path,
    dataset_seeds: tuple[int, ...],
    expected_code: str,
) -> None:
    dataset, registry, source = _shared_fixture(
        tmp_path,
        dataset_seeds=dataset_seeds,
    )
    manifest, records = load_learning_dataset(dataset)

    with pytest.raises(SharedSeedSplitBindingError) as caught:
        validate_shared_seed_split_binding(
            manifest,
            records,
            registry_path=registry,
            training_seed_registry_path=source,
        )
    assert caught.value.code == expected_code


def test_shared_registry_rejects_non_atomic_record_split(tmp_path: Path) -> None:
    dataset, registry, source = _shared_fixture(tmp_path)
    manifest, records = load_learning_dataset(dataset)
    first = records[0]
    wrong_split = "test" if first.split != "test" else "train"
    conflicting_frame = replace(
        _record(
            first.seed,
            first.episode,
            frame_index=first.frame_index + 1,
            scenario=first.scenario_version,
        ),
        split=wrong_split,
    )
    tampered = (first, conflicting_frame, *records[1:])

    with pytest.raises(SharedSeedSplitBindingError) as caught:
        validate_shared_seed_split_binding(
            manifest,
            tampered,
            registry_path=registry,
            training_seed_registry_path=source,
        )
    assert caught.value.code == "dataset_seed_atomicity_mismatch"


def test_bc_cli_records_shared_registry_binding_in_new_bundle(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pytest.importorskip("torch")
    dataset, registry, source = _shared_fixture(tmp_path)
    bundle = tmp_path / "bundle"

    assert learning_cli_main(
        [
            "train-bc",
            "--dataset",
            str(dataset),
            "--bundle",
            str(bundle),
            "--epochs",
            "1",
            "--mini-batch-frames",
            "4",
            "--hidden-size",
            "8",
            "--shared-seed-registry",
            str(registry),
            "--training-seed-registry",
            str(source),
        ]
    ) == 0
    capsys.readouterr()
    bundle_manifest = json.loads(
        (bundle / "manifest.json").read_text(encoding="utf-8")
    )
    binding = bundle_manifest["training_results"]["shared_seed_registry_binding"]
    assert binding["status"] == "verified"
    assert binding["registry_file_sha256"] == sha256(registry.read_bytes()).hexdigest()
    assert binding["source_training_seed_registry_sha256"] == sha256(
        source.read_bytes()
    ).hexdigest()
