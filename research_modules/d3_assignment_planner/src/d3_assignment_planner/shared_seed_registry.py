"""Read-only binding of D3 datasets to the main-owned shared seed registry."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any, Iterable, Mapping

from .learning_data import (
    DATASET_SPLITS,
    LEARNING_DATASET_SCHEMA_V2,
    LEARNING_DATASET_SPLIT_POLICY_V2,
    LearningDatasetManifest,
    LearningFrameRecord,
    assign_seed_splits,
    validate_split_integrity,
)


SHARED_SEED_SPLIT_SCHEMA_VERSION = "scalable3d-shared-seed-split-registry-v1"
SHARED_SEED_SPLIT_POLICY_VERSION = "scalable3d-numeric-seed-atomic-split-v1"
TRAINING_SEED_REGISTRY_SCHEMA_VERSION = "scalable3d-training-seed-registry-v1"
SHARED_SEED_SPLIT_BINDING_SCHEMA_VERSION = "d3_shared_seed_split_binding_v1"
SHARED_SEED_SPLIT_UNIT = "numeric_seed_atomic_across_modules_scenarios_and_scales"


class SharedSeedSplitBindingError(ValueError):
    """Fail-closed error with a stable reason code for joint-training callers."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class SharedSeedSplitBinding:
    """Hash-bound proof that one D3 dataset uses the shared numeric-seed split."""

    registry_file_sha256: str
    registry_content_sha256: str
    assignment_sha256: str
    source_training_seed_registry_sha256: str
    source_git_commit: str
    source_schedule_sha256: str | None
    dataset_split_hash: str
    dataset_frames_sha256: str
    training_seed_count: int
    split_seed_counts: Mapping[str, int]
    reserved_evaluation_seeds: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SHARED_SEED_SPLIT_BINDING_SCHEMA_VERSION,
            "status": "verified",
            "joint_training_split_eligible": True,
            "shared_registry_schema_version": SHARED_SEED_SPLIT_SCHEMA_VERSION,
            "shared_registry_policy_version": SHARED_SEED_SPLIT_POLICY_VERSION,
            "ordering_compatibility_version": LEARNING_DATASET_SPLIT_POLICY_V2,
            "registry_file_sha256": self.registry_file_sha256,
            "registry_content_sha256": self.registry_content_sha256,
            "assignment_sha256": self.assignment_sha256,
            "source_training_seed_registry_schema_version": (
                TRAINING_SEED_REGISTRY_SCHEMA_VERSION
            ),
            "source_training_seed_registry_sha256": (
                self.source_training_seed_registry_sha256
            ),
            "source_git_commit": self.source_git_commit,
            "source_schedule_sha256": self.source_schedule_sha256,
            "dataset_schema_version": LEARNING_DATASET_SCHEMA_V2,
            "dataset_split_policy_version": LEARNING_DATASET_SPLIT_POLICY_V2,
            "dataset_split_hash": self.dataset_split_hash,
            "dataset_frames_sha256": self.dataset_frames_sha256,
            "training_seed_count": int(self.training_seed_count),
            "split_seed_counts": {
                split: int(self.split_seed_counts[split]) for split in DATASET_SPLITS
            },
            "reserved_evaluation_seeds": list(self.reserved_evaluation_seeds),
            "reserved_seed_overlap_count": 0,
            "numeric_seed_atomic": True,
            "exact_seed_coverage": True,
            "exact_assignment_match": True,
            "original_dataset_mutated": False,
        }


def validate_shared_seed_split_binding(
    manifest: LearningDatasetManifest,
    records: Iterable[LearningFrameRecord],
    *,
    registry_path: str | Path,
    training_seed_registry_path: str | Path,
) -> SharedSeedSplitBinding:
    """Verify a D3 dataset against a detached main-owned registry without writes."""

    registry_file = Path(registry_path)
    source_file = Path(training_seed_registry_path)
    registry = _read_json_object(registry_file, "shared_seed_registry_read_failed")
    source = _read_json_object(source_file, "training_seed_registry_read_failed")
    registry_file_sha256 = _file_sha256(registry_file)
    source_file_sha256 = _file_sha256(source_file)

    _require_exact_keys(
        registry,
        {
            "schema_version",
            "policy_version",
            "ordering_compatibility_version",
            "source",
            "unit",
            "split_seed",
            "validation_fraction",
            "test_fraction",
            "minimum_test_seed_count",
            "training_seed_count",
            "reserved_evaluation_seed_count",
            "reserved_evaluation_seeds",
            "training_reserved_overlap_count",
            "split_seed_values",
            "assignments",
            "assignment_sha256",
            "consumer_contract",
            "content_sha256",
        },
        "registry_fields_mismatch",
    )
    if registry["schema_version"] != SHARED_SEED_SPLIT_SCHEMA_VERSION:
        _fail("registry_schema_mismatch", "unsupported shared seed registry schema")
    if registry["policy_version"] != SHARED_SEED_SPLIT_POLICY_VERSION:
        _fail("registry_policy_mismatch", "unsupported shared seed registry policy")
    if registry["ordering_compatibility_version"] != LEARNING_DATASET_SPLIT_POLICY_V2:
        _fail(
            "ordering_policy_mismatch",
            "shared registry is not compatible with the D3 numeric-seed policy",
        )
    if registry["unit"] != SHARED_SEED_SPLIT_UNIT:
        _fail("registry_unit_mismatch", "shared registry split unit is invalid")
    expected_consumer_contract = {
        "original_dataset_mutation_allowed": False,
        "module_local_split_override_allowed": False,
        "cross_module_training_requires_exact_registry": True,
        "reserved_evaluation_seeds_allowed": False,
    }
    if registry["consumer_contract"] != expected_consumer_contract:
        _fail(
            "consumer_contract_mismatch",
            "shared registry consumer contract must remain fail closed",
        )

    content_sha256 = _sha256_value(registry["content_sha256"], "content_sha256")
    content_payload = dict(registry)
    del content_payload["content_sha256"]
    if _sha256_json(content_payload) != content_sha256:
        _fail("registry_content_sha256_mismatch", "shared registry content was modified")

    training_seeds, reserved_seeds = _validate_source_registry(source)
    source_block = registry["source"]
    if not isinstance(source_block, MappingABC):
        _fail("registry_source_invalid", "shared registry source must be an object")
    _require_exact_keys(
        source_block,
        {
            "training_seed_registry_schema_version",
            "training_seed_registry_sha256",
            "git_commit",
            "repository_dirty",
            "schedule_sha256",
        },
        "registry_source_fields_mismatch",
    )
    declared_source_sha = _sha256_value(
        source_block["training_seed_registry_sha256"],
        "training_seed_registry_sha256",
    )
    if declared_source_sha != source_file_sha256:
        _fail(
            "source_training_registry_sha256_mismatch",
            "shared registry does not bind the supplied training seed registry",
        )
    if source_block["training_seed_registry_schema_version"] != source["schema_version"]:
        _fail("source_schema_binding_mismatch", "source schema provenance differs")
    for field in ("git_commit", "repository_dirty", "schedule_sha256"):
        if source_block[field] != source[field]:
            _fail(
                "source_provenance_mismatch",
                f"shared registry source field differs: {field}",
            )

    training_seed_count = _integer(registry["training_seed_count"], "training_seed_count")
    reserved_seed_count = _integer(
        registry["reserved_evaluation_seed_count"],
        "reserved_evaluation_seed_count",
    )
    registry_reserved = _seed_sequence(
        registry["reserved_evaluation_seeds"], "reserved_evaluation_seeds"
    )
    if training_seed_count != len(training_seeds):
        _fail("training_seed_count_mismatch", "training seed count differs from source")
    if reserved_seed_count != len(reserved_seeds) or registry_reserved != reserved_seeds:
        _fail("reserved_seed_catalog_mismatch", "reserved seed catalog differs from source")
    if _integer(
        registry["training_reserved_overlap_count"],
        "training_reserved_overlap_count",
    ) != 0:
        _fail("reserved_seed_overlap", "shared registry declares reserved seed overlap")

    split_seed = _integer(registry["split_seed"], "split_seed")
    validation_fraction = _fraction(
        registry["validation_fraction"], "validation_fraction"
    )
    test_fraction = _fraction(registry["test_fraction"], "test_fraction")
    minimum_test_seed_count = _integer(
        registry["minimum_test_seed_count"], "minimum_test_seed_count"
    )
    if minimum_test_seed_count < 1:
        _fail("minimum_test_seed_count_invalid", "minimum test seed count must be positive")

    assignments = registry["assignments"]
    if not isinstance(assignments, list):
        _fail("assignments_invalid", "shared registry assignments must be a list")
    assignment_sha256 = _sha256_value(
        registry["assignment_sha256"], "assignment_sha256"
    )
    if _sha256_json(assignments) != assignment_sha256:
        _fail("assignment_sha256_mismatch", "shared registry assignments were modified")
    split_by_seed: dict[int, str] = {}
    assignment_order: list[int] = []
    for item in assignments:
        if not isinstance(item, MappingABC) or set(item) != {"seed", "split"}:
            _fail("assignment_fields_mismatch", "assignment fields are invalid")
        seed = _integer(item["seed"], "assignment.seed")
        split = str(item["split"])
        if split not in DATASET_SPLITS:
            _fail("assignment_split_invalid", f"unsupported shared split: {split}")
        if seed in split_by_seed:
            _fail("duplicate_assignment_seed", f"duplicate shared seed: {seed}")
        split_by_seed[seed] = split
        assignment_order.append(seed)
    if assignment_order != list(training_seeds):
        _fail(
            "assignment_seed_catalog_mismatch",
            "assignments must cover the sorted source training seed catalog exactly",
        )

    expected_by_d3 = dict(
        assign_seed_splits(
            training_seeds,
            split_seed=split_seed,
            validation_fraction=validation_fraction,
            test_fraction=test_fraction,
            minimum_unseen_seed_count=minimum_test_seed_count,
        )
    )
    if split_by_seed != expected_by_d3:
        _fail(
            "assignment_policy_reproduction_mismatch",
            "shared assignments do not reproduce under the D3 v2 policy",
        )

    split_seed_values_raw = registry["split_seed_values"]
    if not isinstance(split_seed_values_raw, MappingABC) or set(
        split_seed_values_raw
    ) != set(DATASET_SPLITS):
        _fail("split_seed_values_invalid", "shared split seed catalog is invalid")
    registry_seed_values = {
        split: _seed_sequence(split_seed_values_raw[split], f"split_seed_values.{split}")
        for split in DATASET_SPLITS
    }
    expected_seed_values = {
        split: tuple(seed for seed in training_seeds if split_by_seed[seed] == split)
        for split in DATASET_SPLITS
    }
    if registry_seed_values != expected_seed_values:
        _fail(
            "split_seed_values_mismatch",
            "shared split seed values differ from assignments",
        )

    if manifest.schema_version != LEARNING_DATASET_SCHEMA_V2:
        _fail("dataset_schema_mismatch", "D3 dataset schema is not v2")
    if manifest.split_policy_version != LEARNING_DATASET_SPLIT_POLICY_V2:
        _fail("dataset_policy_mismatch", "D3 dataset split policy is not v2")
    if (
        manifest.split_seed != split_seed
        or manifest.validation_fraction != validation_fraction
        or manifest.test_fraction != test_fraction
        or manifest.minimum_unseen_seed_count != minimum_test_seed_count
    ):
        _fail(
            "dataset_split_parameters_mismatch",
            "D3 manifest split parameters differ from the shared registry",
        )
    manifest_seed_values = {
        split: tuple(int(seed) for seed in manifest.split_seed_values[split])
        for split in DATASET_SPLITS
    }
    manifest_seeds = set().union(*(set(values) for values in manifest_seed_values.values()))
    manifest_reserved_overlap = manifest_seeds & set(reserved_seeds)
    if manifest_reserved_overlap:
        _fail(
            "reserved_seed_in_dataset",
            "reserved evaluation seeds entered the D3 manifest: "
            f"{sorted(manifest_reserved_overlap)}",
        )
    if manifest.unique_seed_count != training_seed_count or manifest_seeds != set(
        training_seeds
    ):
        _fail(
            "dataset_manifest_seed_coverage_mismatch",
            "D3 manifest does not cover the source training seeds exactly",
        )
    if manifest_seed_values != registry_seed_values:
        _fail(
            "dataset_manifest_assignment_mismatch",
            "D3 manifest seed assignments differ from the shared registry",
        )

    items = tuple(records)
    try:
        validate_split_integrity(
            items,
            minimum_unseen_seed_count=minimum_test_seed_count,
        )
    except ValueError as exc:
        raise SharedSeedSplitBindingError(
            "dataset_seed_atomicity_mismatch", str(exc)
        ) from exc
    if len(items) != manifest.frame_count:
        _fail(
            "dataset_record_frame_count_mismatch",
            "D3 record count differs from the dataset manifest",
        )
    episode_count = len(
        {
            (item.scenario_version, int(item.seed), item.episode)
            for item in items
        }
    )
    if episode_count != manifest.episode_count:
        _fail(
            "dataset_record_episode_count_mismatch",
            "D3 episode count differs from the dataset manifest",
        )
    record_seed_values = {int(item.seed) for item in items}
    reserved_overlap = record_seed_values & set(reserved_seeds)
    if reserved_overlap:
        _fail(
            "reserved_seed_in_dataset",
            f"reserved evaluation seeds entered the D3 dataset: {sorted(reserved_overlap)}",
        )
    missing = set(training_seeds) - record_seed_values
    extra = record_seed_values - set(training_seeds)
    if missing or extra:
        _fail(
            "dataset_record_seed_coverage_mismatch",
            f"D3 records have missing seeds {sorted(missing)} and extra seeds {sorted(extra)}",
        )
    for item in items:
        if item.split != split_by_seed[int(item.seed)]:
            _fail(
                "dataset_record_assignment_mismatch",
                f"D3 record split differs for seed {item.seed}",
            )

    return SharedSeedSplitBinding(
        registry_file_sha256=registry_file_sha256,
        registry_content_sha256=content_sha256,
        assignment_sha256=assignment_sha256,
        source_training_seed_registry_sha256=source_file_sha256,
        source_git_commit=str(source["git_commit"]),
        source_schedule_sha256=(
            None if source["schedule_sha256"] is None else str(source["schedule_sha256"])
        ),
        dataset_split_hash=manifest.split_hash,
        dataset_frames_sha256=manifest.frames_sha256,
        training_seed_count=training_seed_count,
        split_seed_counts={
            split: len(registry_seed_values[split]) for split in DATASET_SPLITS
        },
        reserved_evaluation_seeds=reserved_seeds,
    )


def _validate_source_registry(value: Mapping[str, Any]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    _require_exact_keys(
        value,
        {
            "schema_version",
            "git_commit",
            "repository_dirty",
            "schedule_sha256",
            "training_seed_count",
            "training_seeds",
            "reserved_evaluation_seed_count",
            "reserved_evaluation_seeds",
            "overlap_count",
        },
        "source_registry_fields_mismatch",
    )
    if value["schema_version"] != TRAINING_SEED_REGISTRY_SCHEMA_VERSION:
        _fail("source_registry_schema_mismatch", "unsupported training seed registry schema")
    training = _seed_sequence(value["training_seeds"], "training_seeds")
    reserved = _seed_sequence(
        value["reserved_evaluation_seeds"], "reserved_evaluation_seeds"
    )
    if not training:
        _fail("source_training_seed_catalog_empty", "training seed catalog is empty")
    if _integer(value["training_seed_count"], "training_seed_count") != len(training):
        _fail("source_training_seed_count_mismatch", "training seed count is invalid")
    if _integer(
        value["reserved_evaluation_seed_count"], "reserved_evaluation_seed_count"
    ) != len(reserved):
        _fail("source_reserved_seed_count_mismatch", "reserved seed count is invalid")
    overlap = set(training) & set(reserved)
    if overlap or _integer(value["overlap_count"], "overlap_count") != 0:
        _fail("source_seed_overlap", f"training and reserved seeds overlap: {sorted(overlap)}")
    commit = str(value["git_commit"])
    if len(commit) != 40 or not set(commit).issubset(frozenset("0123456789abcdef")):
        _fail("source_git_commit_invalid", "source Git commit must be a 40-character hex ID")
    if not isinstance(value["repository_dirty"], bool):
        _fail("source_repository_state_invalid", "source dirty state must be boolean")
    schedule_sha = value["schedule_sha256"]
    if schedule_sha is not None:
        _sha256_value(schedule_sha, "schedule_sha256")
    return training, reserved


def _seed_sequence(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        _fail("seed_catalog_invalid", f"{name} must be a JSON list")
    seeds = tuple(_integer(item, name) for item in value)
    if any(seed < 0 for seed in seeds):
        _fail("negative_seed", f"{name} contains a negative seed")
    if seeds != tuple(sorted(set(seeds))):
        _fail("seed_catalog_not_sorted_unique", f"{name} must be sorted and unique")
    return seeds


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], code: str
) -> None:
    if not isinstance(value, MappingABC) or set(value) != expected:
        _fail(code, "JSON object fields do not match the declared schema")


def _read_json_object(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SharedSeedSplitBindingError(code, f"cannot read JSON object: {path}") from exc
    if not isinstance(value, dict):
        _fail(code, f"JSON object required: {path}")
    return value


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("integer_invalid", f"{name} must be an integer")
    return int(value)


def _fraction(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("fraction_invalid", f"{name} must be numeric")
    number = float(value)
    if not isfinite(number) or not 0.0 < number < 1.0:
        _fail("fraction_invalid", f"{name} must be finite and in (0, 1)")
    return number


def _sha256_value(value: Any, name: str) -> str:
    text = str(value)
    if len(text) != 64 or not set(text).issubset(frozenset("0123456789abcdef")):
        _fail("sha256_invalid", f"{name} must be lowercase SHA256")
    return text


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise SharedSeedSplitBindingError(
            "registry_file_hash_failed", f"cannot hash registry file: {path}"
        ) from exc
    return digest.hexdigest()


def _fail(code: str, message: str) -> None:
    raise SharedSeedSplitBindingError(code, message)
