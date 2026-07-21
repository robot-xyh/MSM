from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.shared_seed_split import (
    SHARED_SEED_SPLIT_SCHEMA_VERSION,
    SharedSeedSplitError,
    assign_shared_seed_splits,
    build_shared_seed_split_registry,
    load_shared_seed_split_registry,
    write_shared_seed_split_registry,
)


_D3_FORMAL_TEST_SEEDS = {
    1,
    4,
    5,
    8,
    9,
    15,
    28,
    34,
    43,
    53,
    56,
    58,
    66,
    67,
    70,
    76,
    81,
    94,
    95,
    98,
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _source_registry() -> dict[str, object]:
    return {
        "schema_version": "scalable3d-training-seed-registry-v1",
        "git_commit": "1" * 40,
        "repository_dirty": False,
        "schedule_sha256": "2" * 64,
        "training_seed_count": 100,
        "training_seeds": list(range(100)),
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "overlap_count": 0,
    }


def _write_source(path: Path, value: dict[str, object] | None = None) -> None:
    path.write_bytes(_canonical(value or _source_registry()) + b"\n")


def test_shared_split_matches_frozen_d3_development_catalog() -> None:
    assignment = assign_shared_seed_splits(range(100))
    assert len(assignment) == 100
    assert sum(split == "train" for split in assignment.values()) == 60
    assert sum(split == "validation" for split in assignment.values()) == 20
    assert {seed for seed, split in assignment.items() if split == "test"} == (
        _D3_FORMAL_TEST_SEEDS
    )
    assert assign_shared_seed_splits(reversed(range(100))) == assignment


def test_registry_binds_source_and_reserved_seed_isolation() -> None:
    source = _source_registry()
    source_sha = hashlib.sha256(_canonical(source) + b"\n").hexdigest()
    registry = build_shared_seed_split_registry(
        source, training_seed_registry_sha256=source_sha
    )
    assert registry["schema_version"] == SHARED_SEED_SPLIT_SCHEMA_VERSION
    assert registry["source"]["training_seed_registry_sha256"] == source_sha
    assert registry["training_reserved_overlap_count"] == 0
    assert registry["reserved_evaluation_seeds"] == list(range(1000, 1020))
    assert len(registry["split_seed_values"]["test"]) == 20
    assert set(registry["split_seed_values"]["test"]).isdisjoint(
        registry["reserved_evaluation_seeds"]
    )


def test_writer_is_atomic_idempotent_and_detects_tamper(tmp_path: Path) -> None:
    source = tmp_path / "training_seed_registry.json"
    output = tmp_path / "sidecars" / "shared_seed_split_registry.json"
    _write_source(source)
    first = write_shared_seed_split_registry(source, output)
    second = write_shared_seed_split_registry(source, output)
    assert first == second
    assert load_shared_seed_split_registry(
        output, training_seed_registry_path=source
    ) == first

    tampered = json.loads(output.read_text(encoding="utf-8"))
    tampered["assignments"][0]["split"] = "test"
    output.write_bytes(_canonical(tampered) + b"\n")
    with pytest.raises(SharedSeedSplitError) as exc_info:
        load_shared_seed_split_registry(output, training_seed_registry_path=source)
    assert exc_info.value.code == "registry_reproduction_mismatch"


def test_writer_never_replaces_source_registry(tmp_path: Path) -> None:
    source = tmp_path / "training_seed_registry.json"
    _write_source(source)
    with pytest.raises(SharedSeedSplitError) as exc_info:
        write_shared_seed_split_registry(source, source)
    assert exc_info.value.code == "source_mutation_forbidden"


def test_training_reserved_overlap_fails_closed() -> None:
    source = _source_registry()
    source["reserved_evaluation_seeds"] = [99, *range(1000, 1019)]
    source["reserved_evaluation_seed_count"] = 20
    source["overlap_count"] = 1
    with pytest.raises(SharedSeedSplitError) as exc_info:
        build_shared_seed_split_registry(
            source, training_seed_registry_sha256="3" * 64
        )
    assert exc_info.value.code == "training_reserved_seed_overlap"


def test_declared_minimum_test_seed_count_is_enforced() -> None:
    with pytest.raises(SharedSeedSplitError) as exc_info:
        assign_shared_seed_splits(range(50), minimum_test_seed_count=20)
    assert exc_info.value.code == "insufficient_test_seeds"
