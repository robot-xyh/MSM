from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.canonical_seed_split_readiness import (
    CanonicalSeedSplitAuditError,
    audit_canonical_seed_split_readiness,
)


_COMMIT = "1" * 40
_SCHEDULE_SHA = "2" * 64
_SPLIT_HASH = "3" * 64
_TRAINING_SEEDS = list(range(100))
_RESERVED_SEEDS = list(range(1000, 1020))
_SPLITS = ("train", "validation", "test")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha_json(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(value) + b"\n")


def _canonical_assignment() -> dict[int, str]:
    ordered = sorted(
        _TRAINING_SEEDS,
        key=lambda seed: (
            hashlib.sha256(
                f"d3_numeric_seed_atomic_split_v2|20260720\0{seed}".encode()
            ).hexdigest(),
            seed,
        ),
    )
    return {
        seed: (
            "test"
            if index < 20
            else "validation"
            if index < 40
            else "train"
        )
        for index, seed in enumerate(ordered)
    }


def _split_values(assignments: dict[int, str]) -> dict[str, list[int]]:
    return {
        split: sorted(seed for seed, value in assignments.items() if value == split)
        for split in _SPLITS
    }


def _rehash_registry(registry: dict[str, object], *, assignment: bool = False) -> None:
    if assignment:
        registry["assignment_sha256"] = _sha_json(registry["assignments"])
    unsigned = dict(registry)
    unsigned.pop("content_sha256", None)
    registry["content_sha256"] = _sha_json(unsigned)


def _build_manifest_fixture(tmp_path: Path) -> tuple[Path, Path]:
    generation = tmp_path / "generation"
    dataset = generation / "learning_dataset"
    assignments = _canonical_assignment()
    split_values = _split_values(assignments)
    training_registry = {
        "schema_version": "scalable3d-training-seed-registry-v1",
        "training_seed_count": 100,
        "training_seeds": _TRAINING_SEEDS,
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
        "overlap_count": 0,
        "git_commit": _COMMIT,
        "repository_dirty": False,
        "schedule_sha256": _SCHEDULE_SHA,
    }
    training_registry_path = generation / "training_seed_registry.json"
    _write_json(training_registry_path, training_registry)

    assignment_rows = [
        {"seed": seed, "split": assignments[seed]} for seed in _TRAINING_SEEDS
    ]
    registry: dict[str, object] = {
        "schema_version": "scalable3d-shared-seed-split-registry-v1",
        "policy_version": "scalable3d-numeric-seed-atomic-split-v1",
        "ordering_compatibility_version": "d3_numeric_seed_atomic_split_v2",
        "source": {
            "training_seed_registry_schema_version": (
                "scalable3d-training-seed-registry-v1"
            ),
            "training_seed_registry_sha256": _sha_file(training_registry_path),
            "git_commit": _COMMIT,
            "repository_dirty": False,
            "schedule_sha256": _SCHEDULE_SHA,
        },
        "unit": "numeric_seed_atomic_across_modules_scenarios_and_scales",
        "split_seed": 20260720,
        "validation_fraction": 0.2,
        "test_fraction": 0.2,
        "minimum_test_seed_count": 20,
        "training_seed_count": 100,
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
        "training_reserved_overlap_count": 0,
        "split_seed_values": split_values,
        "assignments": assignment_rows,
        "assignment_sha256": _sha_json(assignment_rows),
        "consumer_contract": {
            "original_dataset_mutation_allowed": False,
            "module_local_split_override_allowed": False,
            "cross_module_training_requires_exact_registry": True,
            "reserved_evaluation_seeds_allowed": False,
        },
    }
    _rehash_registry(registry)
    registry_path = generation / "shared" / "registry.json"
    _write_json(registry_path, registry)

    _write_json(
        dataset / "d3_assignment" / "dataset_manifest.json",
        {
            "schema_version": "d3_learning_dataset_v2",
            "episode_count": 100,
            "frame_count": 200,
            "split_hash": _SPLIT_HASH,
            "split_policy_version": "d3_numeric_seed_atomic_split_v2",
            "split_policy": {
                "shared_seed_values_atomic_across_scenarios": True,
                "unit": "whole_episode_grouped_by_numeric_seed_across_scenarios",
                "split_seed": 20260720,
                "validation_fraction": 0.2,
                "test_fraction": 0.2,
            },
            "split_seed_values": split_values,
        },
    )
    _write_json(
        dataset / "d4_region" / "manifest.json",
        {
            "schema": "d4-region-learning-dataset-v1",
            "split": {
                **{f"{split}_seeds": values for split, values in split_values.items()},
                "split_sha256": _SPLIT_HASH,
            },
            "episodes": [
                {
                    "source": {"seed": seed},
                    "split": assignments[seed],
                    "frame_count": 2,
                }
                for seed in _TRAINING_SEEDS
            ],
        },
    )
    d5_policy = {
        "shared_seed_values_atomic_across_scenarios": True,
        "unit": "whole_episode_grouped_by_scenario_version_and_seed",
        "split_seed": 20260720,
        "validation_fraction": 0.2,
        "test_fraction": 0.2,
    }
    _write_json(
        dataset / "d5_tracklet_graph" / "manifest.json",
        {
            "schema_version": "d5.tracklet-dataset.v2",
            "split_sha256": _SPLIT_HASH,
            "split_policy": d5_policy,
            "episodes": [
                {"seed": seed, "split": assignments[seed], "edge_count": 3}
                for seed in _TRAINING_SEEDS
            ],
        },
    )
    _write_json(
        dataset / "d5_active_vision" / "manifest.json",
        {
            "schema_version": "d5.active-vision-episode-dataset.v3",
            "split_sha256": _SPLIT_HASH,
            "split_policy": d5_policy,
            "episodes": [
                {"seed": seed, "split": assignments[seed], "sample_count": 4}
                for seed in _TRAINING_SEEDS
            ],
        },
    )
    return dataset, registry_path


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _move_seed_between_split_lists(
    values: dict[str, list[int]], seed: int, destination: str
) -> None:
    source = next(split for split, seeds in values.items() if seed in seeds)
    values[source].remove(seed)
    values[destination].append(seed)
    values[destination].sort()


def test_exact_registry_and_all_module_manifests_allow_joint_training(
    tmp_path: Path,
) -> None:
    dataset, registry = _build_manifest_fixture(tmp_path)

    result = audit_canonical_seed_split_readiness(dataset, registry)

    assert result["registry"]["training_seed_count"] == 100
    assert result["registry"]["split_seed_counts"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert result["registry"]["validation"] == {
        "schema_valid": True,
        "policy_valid": True,
        "content_hash_valid": True,
        "assignment_hash_valid": True,
        "source_sha_valid": True,
        "assignment_reproduced": True,
        "training_seed_coverage_complete": True,
        "reserved_seed_isolation_valid": True,
    }
    assert all(item["exact_match"] for item in result["modules"].values())
    assert result["joint_training"]["available"] is True
    assert result["joint_training"]["reason"] is None


def test_registry_content_tamper_fails_closed(tmp_path: Path) -> None:
    dataset, registry_path = _build_manifest_fixture(tmp_path)
    registry = _load(registry_path)
    registry["unit"] = "tampered"
    _write_json(registry_path, registry)

    with pytest.raises(CanonicalSeedSplitAuditError) as captured:
        audit_canonical_seed_split_readiness(dataset, registry_path)

    assert captured.value.code == "shared_registry_content_hash_mismatch"


def test_registry_assignment_hash_tamper_fails_closed(tmp_path: Path) -> None:
    dataset, registry_path = _build_manifest_fixture(tmp_path)
    registry = _load(registry_path)
    registry["assignments"][0]["split"] = "test"  # type: ignore[index]
    _rehash_registry(registry)
    _write_json(registry_path, registry)

    with pytest.raises(CanonicalSeedSplitAuditError) as captured:
        audit_canonical_seed_split_readiness(dataset, registry_path)

    assert captured.value.code == "shared_registry_assignment_hash_mismatch"


def test_registry_source_sha_mismatch_fails_closed(tmp_path: Path) -> None:
    dataset, registry_path = _build_manifest_fixture(tmp_path)
    registry = _load(registry_path)
    registry["source"]["training_seed_registry_sha256"] = "0" * 64  # type: ignore[index]
    _rehash_registry(registry)
    _write_json(registry_path, registry)

    with pytest.raises(CanonicalSeedSplitAuditError) as captured:
        audit_canonical_seed_split_readiness(dataset, registry_path)

    assert captured.value.code == "shared_registry_source_sha_mismatch"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing", "shared_registry_seed_coverage_mismatch"),
        ("extra", "shared_registry_seed_coverage_mismatch"),
        ("reserved", "shared_registry_reserved_seed_leakage"),
    ],
)
def test_registry_missing_extra_and_reserved_seed_fail_closed(
    tmp_path: Path, mutation: str, reason: str
) -> None:
    dataset, registry_path = _build_manifest_fixture(tmp_path)
    registry = _load(registry_path)
    assignments = registry["assignments"]
    assert isinstance(assignments, list)
    if mutation == "missing":
        assignments.pop()
    elif mutation == "extra":
        assignments.append({"seed": 500, "split": "train"})
    else:
        assignments.append({"seed": 1000, "split": "test"})
    _rehash_registry(registry, assignment=True)
    _write_json(registry_path, registry)

    with pytest.raises(CanonicalSeedSplitAuditError) as captured:
        audit_canonical_seed_split_readiness(dataset, registry_path)

    assert captured.value.code == reason


@pytest.mark.parametrize(
    ("module", "expected_episode_count", "expected_sample_count"),
    [
        ("d3_assignment", None, None),
        ("d4_region", 1, 2),
        ("d5_tracklet_graph", 1, 3),
        ("d5_active_vision", 1, 4),
    ],
)
def test_module_mismatch_blocks_joint_training_with_available_granularity(
    tmp_path: Path,
    module: str,
    expected_episode_count: int | None,
    expected_sample_count: int | None,
) -> None:
    dataset, registry_path = _build_manifest_fixture(tmp_path)
    paths = {
        "d3_assignment": dataset / "d3_assignment" / "dataset_manifest.json",
        "d4_region": dataset / "d4_region" / "manifest.json",
        "d5_tracklet_graph": dataset / "d5_tracklet_graph" / "manifest.json",
        "d5_active_vision": dataset / "d5_active_vision" / "manifest.json",
    }
    path = paths[module]
    manifest = _load(path)
    canonical = _canonical_assignment()
    seed = 0
    wrong = next(split for split in _SPLITS if split != canonical[seed])
    if module == "d3_assignment":
        _move_seed_between_split_lists(manifest["split_seed_values"], seed, wrong)  # type: ignore[arg-type]
    elif module == "d4_region":
        split = manifest["split"]
        values = {name: split[f"{name}_seeds"] for name in _SPLITS}  # type: ignore[index]
        _move_seed_between_split_lists(values, seed, wrong)
        next(
            entry
            for entry in manifest["episodes"]  # type: ignore[union-attr]
            if entry["source"]["seed"] == seed
        )["split"] = wrong
    else:
        next(
            entry
            for entry in manifest["episodes"]  # type: ignore[union-attr]
            if entry["seed"] == seed
        )["split"] = wrong
    _write_json(path, manifest)

    result = audit_canonical_seed_split_readiness(dataset, registry_path)
    audit = result["modules"][module]

    assert audit["exact_match"] is False
    assert audit["mismatched_seed_count"] == 1
    assert audit["mismatched_episode_count"]["value"] == expected_episode_count
    assert audit["mismatched_sample_count"]["value"] == expected_sample_count
    assert audit["mismatched_episode_count"]["available"] is (
        expected_episode_count is not None
    )
    assert result["joint_training"]["available"] is False
    assert result["joint_training"]["nonmatching_modules"] == [module]


def test_module_missing_extra_and_reserved_seeds_are_reported(tmp_path: Path) -> None:
    dataset, registry_path = _build_manifest_fixture(tmp_path)
    path = dataset / "d5_active_vision" / "manifest.json"
    manifest = _load(path)
    episodes = manifest["episodes"]
    assert isinstance(episodes, list)
    episodes[:] = [entry for entry in episodes if entry["seed"] != 0]
    episodes.append({"seed": 500, "split": "train", "sample_count": 1})
    episodes.append({"seed": 1000, "split": "test", "sample_count": 1})
    _write_json(path, manifest)

    result = audit_canonical_seed_split_readiness(dataset, registry_path)
    audit = result["modules"]["d5_active_vision"]

    assert audit["missing_seed_values"] == [0]
    assert audit["extra_seed_values"] == [500, 1000]
    assert audit["reserved_seed_values"] == [1000]
    assert audit["exact_match"] is False
    assert result["joint_training"]["available"] is False
