"""Read-only audit of the detached scalable-3D canonical seed split.

This module deliberately duplicates the small, frozen hashing and assignment
contract instead of importing the main-owned scalable-3D runtime.  D6 can
therefore verify learning-data governance without acquiring a control-path
dependency or rewriting any producer manifest.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CANONICAL_SEED_SPLIT_READINESS_SCHEMA_VERSION = (
    "d6.canonical-seed-split-readiness.v1"
)
SHARED_SEED_SPLIT_SCHEMA_VERSION = "scalable3d-shared-seed-split-registry-v1"
SHARED_SEED_SPLIT_POLICY_VERSION = "scalable3d-numeric-seed-atomic-split-v1"
TRAINING_SEED_REGISTRY_SCHEMA_VERSION = "scalable3d-training-seed-registry-v1"
ORDERING_COMPATIBILITY_VERSION = "d3_numeric_seed_atomic_split_v2"

EXPECTED_TRAINING_SEED_COUNT = 100
EXPECTED_RESERVED_EVALUATION_SEEDS = tuple(range(1000, 1020))
EXPECTED_SPLIT_SEED = 20260720
EXPECTED_VALIDATION_FRACTION = 0.20
EXPECTED_TEST_FRACTION = 0.20
EXPECTED_MINIMUM_TEST_SEED_COUNT = 20
_SPLITS = ("train", "validation", "test")
_HEX64 = frozenset("0123456789abcdef")


class CanonicalSeedSplitAuditError(RuntimeError):
    """Stable fail-closed error for malformed canonical split evidence."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


def audit_canonical_seed_split_readiness(
    learning_dataset_dir: str | Path,
    shared_seed_split_registry_path: str | Path,
) -> dict[str, Any]:
    """Audit D3/D4/D5 manifests against one detached numeric-seed registry.

    The function reads manifests and registries only.  It does not import the
    main runtime, modify producer data, or infer unavailable row-level counts.
    """

    dataset_root = Path(learning_dataset_dir).resolve()
    registry_path = Path(shared_seed_split_registry_path).resolve()
    training_registry_path = dataset_root.parent / "training_seed_registry.json"
    training_registry = _read_json_object(training_registry_path)
    training = _validate_training_seed_registry(training_registry)
    registry = _read_json_object(registry_path)
    canonical = _validate_shared_registry(
        registry,
        registry_file_sha256=_sha256_file(registry_path),
        training_registry=training_registry,
        training_registry_file_sha256=_sha256_file(training_registry_path),
        training=training,
    )

    manifests = {
        "d3_assignment": dataset_root / "d3_assignment" / "dataset_manifest.json",
        "d4_region": dataset_root / "d4_region" / "manifest.json",
        "d5_tracklet_graph": dataset_root / "d5_tracklet_graph" / "manifest.json",
        "d5_active_vision": dataset_root / "d5_active_vision" / "manifest.json",
    }
    for module, path in manifests.items():
        if not path.is_file():
            raise CanonicalSeedSplitAuditError(
                "module_manifest_missing", f"{module} manifest is missing: {path}"
            )

    module_audits = {
        "d3_assignment": _audit_d3_manifest(
            manifests["d3_assignment"], canonical
        ),
        "d4_region": _audit_d4_manifest(manifests["d4_region"], canonical),
        "d5_tracklet_graph": _audit_d5_tracklet_manifest(
            manifests["d5_tracklet_graph"], canonical
        ),
        "d5_active_vision": _audit_d5_active_vision_manifest(
            manifests["d5_active_vision"], canonical
        ),
    }
    nonmatching = [
        name for name, audit in module_audits.items() if not audit["exact_match"]
    ]
    joint_available = not nonmatching
    return {
        "schema_version": CANONICAL_SEED_SPLIT_READINESS_SCHEMA_VERSION,
        "registry": canonical["report"],
        "modules": module_audits,
        "joint_training": {
            "available": joint_available,
            "reason": (
                None
                if joint_available
                else "required_module_split_not_exactly_canonical"
            ),
            "required_modules": list(module_audits),
            "nonmatching_modules": nonmatching,
            "scope": (
                "cross_module_joint_training_allowed"
                if joint_available
                else "module_local_training_only"
            ),
        },
    }


def _validate_training_seed_registry(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if value.get("schema_version") != TRAINING_SEED_REGISTRY_SCHEMA_VERSION:
        raise CanonicalSeedSplitAuditError(
            "training_registry_schema_mismatch",
            "unsupported training seed registry schema",
        )
    training = _integer_sequence(value.get("training_seeds"), "training seeds")
    reserved = _integer_sequence(
        value.get("reserved_evaluation_seeds"), "reserved evaluation seeds"
    )
    if len(training) != EXPECTED_TRAINING_SEED_COUNT:
        raise CanonicalSeedSplitAuditError(
            "training_seed_coverage_mismatch",
            f"formal registry requires {EXPECTED_TRAINING_SEED_COUNT} training seeds",
        )
    if int(value.get("training_seed_count", -1)) != len(training):
        raise CanonicalSeedSplitAuditError(
            "training_seed_count_mismatch",
            "training_seed_count differs from the seed catalog",
        )
    if int(value.get("reserved_evaluation_seed_count", -1)) != len(reserved):
        raise CanonicalSeedSplitAuditError(
            "reserved_seed_count_mismatch",
            "reserved_evaluation_seed_count differs from the seed catalog",
        )
    if tuple(sorted(reserved)) != EXPECTED_RESERVED_EVALUATION_SEEDS:
        raise CanonicalSeedSplitAuditError(
            "reserved_seed_catalog_mismatch",
            "reserved evaluation seeds must remain 1000-1019",
        )
    overlap = sorted(set(training) & set(reserved))
    if overlap or int(value.get("overlap_count", -1)) != 0:
        raise CanonicalSeedSplitAuditError(
            "training_reserved_seed_overlap",
            f"training and reserved evaluation seeds overlap: {overlap}",
        )
    commit = _git_commit(value.get("git_commit"), "training registry git_commit")
    dirty = value.get("repository_dirty")
    if not isinstance(dirty, bool):
        raise CanonicalSeedSplitAuditError(
            "training_registry_dirty_flag_invalid",
            "training registry repository_dirty must be boolean",
        )
    schedule = value.get("schedule_sha256")
    if schedule is not None:
        schedule = _sha256(schedule, "training registry schedule_sha256")
    return {
        "training_seeds": tuple(sorted(training)),
        "reserved_seeds": tuple(sorted(reserved)),
        "git_commit": commit,
        "repository_dirty": dirty,
        "schedule_sha256": schedule,
    }


def _validate_shared_registry(
    registry: Mapping[str, Any],
    *,
    registry_file_sha256: str,
    training_registry: Mapping[str, Any],
    training_registry_file_sha256: str,
    training: Mapping[str, Any],
) -> dict[str, Any]:
    if registry.get("schema_version") != SHARED_SEED_SPLIT_SCHEMA_VERSION:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_schema_mismatch", "unsupported shared split registry schema"
        )
    if registry.get("policy_version") != SHARED_SEED_SPLIT_POLICY_VERSION:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_policy_mismatch", "unsupported shared split policy"
        )
    if registry.get("ordering_compatibility_version") != ORDERING_COMPATIBILITY_VERSION:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_policy_mismatch",
            "shared split ordering compatibility changed",
        )

    unsigned = dict(registry)
    claimed_content_hash = _sha256(
        unsigned.pop("content_sha256", None), "shared registry content_sha256"
    )
    if _sha256_json(unsigned) != claimed_content_hash:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_content_hash_mismatch",
            "shared split registry content hash mismatch",
        )

    source = _mapping(registry.get("source"), "shared registry source")
    if source.get("training_seed_registry_schema_version") != (
        TRAINING_SEED_REGISTRY_SCHEMA_VERSION
    ):
        raise CanonicalSeedSplitAuditError(
            "shared_registry_source_schema_mismatch",
            "shared registry source schema differs from the frozen training registry",
        )
    if source.get("training_seed_registry_sha256") != training_registry_file_sha256:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_source_sha_mismatch",
            "shared registry is not bound to the current training seed registry",
        )
    expected_source = {
        "git_commit": training["git_commit"],
        "repository_dirty": training["repository_dirty"],
        "schedule_sha256": training["schedule_sha256"],
    }
    for field, expected in expected_source.items():
        if source.get(field) != expected:
            raise CanonicalSeedSplitAuditError(
                "shared_registry_source_identity_mismatch",
                f"shared registry source {field} differs",
            )

    split_seed = _integer(registry.get("split_seed"), "split_seed")
    validation_fraction = _fraction(
        registry.get("validation_fraction"), "validation_fraction"
    )
    test_fraction = _fraction(registry.get("test_fraction"), "test_fraction")
    minimum_test_seed_count = _integer(
        registry.get("minimum_test_seed_count"), "minimum_test_seed_count"
    )
    if (
        split_seed != EXPECTED_SPLIT_SEED
        or validation_fraction != EXPECTED_VALIDATION_FRACTION
        or test_fraction != EXPECTED_TEST_FRACTION
        or minimum_test_seed_count != EXPECTED_MINIMUM_TEST_SEED_COUNT
        or registry.get("unit")
        != "numeric_seed_atomic_across_modules_scenarios_and_scales"
    ):
        raise CanonicalSeedSplitAuditError(
            "shared_registry_policy_mismatch",
            "shared split parameters differ from the frozen v1 policy",
        )

    assignments_raw = registry.get("assignments")
    if not isinstance(assignments_raw, list):
        raise CanonicalSeedSplitAuditError(
            "shared_registry_assignments_invalid", "assignments must be a list"
        )
    assignment_hash = _sha256(
        registry.get("assignment_sha256"), "assignment_sha256"
    )
    if _sha256_json(assignments_raw) != assignment_hash:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_assignment_hash_mismatch",
            "shared split assignment hash mismatch",
        )
    assignment_by_seed: dict[int, str] = {}
    for raw in assignments_raw:
        row = _mapping(raw, "shared split assignment")
        seed = _integer(row.get("seed"), "assignment seed")
        split = str(row.get("split", ""))
        if split not in _SPLITS or set(row) != {"seed", "split"}:
            raise CanonicalSeedSplitAuditError(
                "shared_registry_assignments_invalid",
                "assignment rows require only seed and a valid split",
            )
        if seed in assignment_by_seed:
            raise CanonicalSeedSplitAuditError(
                "shared_registry_assignment_duplicate", f"duplicate seed {seed}"
            )
        assignment_by_seed[seed] = split

    training_seeds = set(training["training_seeds"])
    reserved_seeds = set(training["reserved_seeds"])
    leaked_reserved = sorted(set(assignment_by_seed) & reserved_seeds)
    if leaked_reserved:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_reserved_seed_leakage",
            f"reserved seeds occur in assignments: {leaked_reserved}",
        )
    missing = sorted(training_seeds - set(assignment_by_seed))
    extra = sorted(set(assignment_by_seed) - training_seeds)
    if missing or extra:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_seed_coverage_mismatch",
            f"shared split missing={missing}, extra={extra}",
        )

    expected_assignment = _assign_seed_splits(
        training_seeds,
        split_seed=split_seed,
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
        minimum_test_seed_count=minimum_test_seed_count,
    )
    expected_rows = [
        {"seed": seed, "split": expected_assignment[seed]}
        for seed in sorted(expected_assignment)
    ]
    if assignments_raw != expected_rows or assignment_by_seed != expected_assignment:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_assignment_reproduction_mismatch",
            "assignments do not reproduce from the frozen numeric-seed policy",
        )

    expected_split_values = {
        split: sorted(seed for seed, value in expected_assignment.items() if value == split)
        for split in _SPLITS
    }
    if registry.get("split_seed_values") != expected_split_values:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_split_catalog_mismatch",
            "split_seed_values differ from assignments",
        )
    if int(registry.get("training_seed_count", -1)) != EXPECTED_TRAINING_SEED_COUNT:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_training_count_mismatch",
            "shared registry does not cover exactly 100 training seeds",
        )
    if (
        int(registry.get("reserved_evaluation_seed_count", -1))
        != len(training["reserved_seeds"])
        or registry.get("reserved_evaluation_seeds") != list(training["reserved_seeds"])
        or int(registry.get("training_reserved_overlap_count", -1)) != 0
    ):
        raise CanonicalSeedSplitAuditError(
            "shared_registry_reserved_contract_mismatch",
            "shared registry reserved-seed contract differs from its source",
        )
    expected_consumer_contract = {
        "original_dataset_mutation_allowed": False,
        "module_local_split_override_allowed": False,
        "cross_module_training_requires_exact_registry": True,
        "reserved_evaluation_seeds_allowed": False,
    }
    if registry.get("consumer_contract") != expected_consumer_contract:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_consumer_contract_mismatch",
            "shared registry consumer contract changed",
        )

    return {
        "assignment_by_seed": assignment_by_seed,
        "training_seeds": frozenset(training_seeds),
        "reserved_seeds": frozenset(reserved_seeds),
        "content_sha256": claimed_content_hash,
        "assignment_sha256": assignment_hash,
        "report": {
            "schema_version": registry["schema_version"],
            "policy_version": registry["policy_version"],
            "ordering_compatibility_version": registry[
                "ordering_compatibility_version"
            ],
            "file_sha256": registry_file_sha256,
            "content_sha256": claimed_content_hash,
            "assignment_sha256": assignment_hash,
            "source_training_seed_registry_sha256": training_registry_file_sha256,
            "source_training_seed_registry_schema_version": training_registry[
                "schema_version"
            ],
            "training_seed_count": len(training_seeds),
            "reserved_evaluation_seed_count": len(reserved_seeds),
            "training_reserved_overlap_count": 0,
            "split_seed_counts": {
                split: len(expected_split_values[split]) for split in _SPLITS
            },
            "validation": {
                "schema_valid": True,
                "policy_valid": True,
                "content_hash_valid": True,
                "assignment_hash_valid": True,
                "source_sha_valid": True,
                "assignment_reproduced": True,
                "training_seed_coverage_complete": True,
                "reserved_seed_isolation_valid": True,
            },
        },
    }


def _audit_d3_manifest(path: Path, canonical: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _read_json_object(path)
    if manifest.get("schema_version") != "d3_learning_dataset_v2":
        raise CanonicalSeedSplitAuditError(
            "d3_manifest_schema_mismatch", "unsupported D3 assignment manifest"
        )
    assignments = _assignments_from_split_catalog(
        _mapping(manifest.get("split_seed_values"), "D3 split_seed_values"),
        suffix="",
    )
    policy = _mapping(manifest.get("split_policy"), "D3 split_policy")
    policy_compatible = bool(
        manifest.get("split_policy_version") == ORDERING_COMPATIBILITY_VERSION
        and policy.get("shared_seed_values_atomic_across_scenarios") is True
        and policy.get("unit")
        == "whole_episode_grouped_by_numeric_seed_across_scenarios"
        and _numeric_equal(policy.get("split_seed"), EXPECTED_SPLIT_SEED)
        and _numeric_equal(
            policy.get("validation_fraction"), EXPECTED_VALIDATION_FRACTION
        )
        and _numeric_equal(policy.get("test_fraction"), EXPECTED_TEST_FRACTION)
    )
    summary = _module_seed_summary(
        module="d3_assignment",
        manifest_path=path,
        original_split_hash=_sha256(manifest.get("split_hash"), "D3 split_hash"),
        assignments=assignments,
        canonical=canonical,
        policy_compatible=policy_compatible,
    )
    exact = summary["exact_match"]
    summary.update(
        {
            "episode_count": _optional_nonnegative_int(manifest.get("episode_count")),
            "sample_count": _optional_nonnegative_int(manifest.get("frame_count")),
            "sample_unit": "assignment_frame",
            "mismatched_episode_count": _count_evidence(
                0 if exact else None,
                reason=None if exact else "d3_manifest_has_no_per_seed_episode_index",
            ),
            "mismatched_sample_count": _count_evidence(
                0 if exact else None,
                reason=None if exact else "d3_manifest_has_no_per_seed_frame_index",
            ),
        }
    )
    return summary


def _audit_d4_manifest(path: Path, canonical: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _read_json_object(path)
    if manifest.get("schema") != "d4-region-learning-dataset-v1":
        raise CanonicalSeedSplitAuditError(
            "d4_manifest_schema_mismatch", "unsupported D4 region manifest"
        )
    split = _mapping(manifest.get("split"), "D4 split")
    assignments = _assignments_from_split_catalog(split, suffix="_seeds")
    entries = _entry_sequence(manifest.get("episodes"), "D4 episodes")
    mismatch_episodes = 0
    mismatch_frames = 0
    for entry in entries:
        source = _mapping(entry.get("source"), "D4 episode source")
        seed = _integer(source.get("seed"), "D4 episode seed")
        declared = _split(entry.get("split"), "D4 episode split")
        if canonical["assignment_by_seed"].get(seed) != declared:
            mismatch_episodes += 1
            mismatch_frames += _integer(entry.get("frame_count"), "D4 frame_count")
    summary = _module_seed_summary(
        module="d4_region",
        manifest_path=path,
        original_split_hash=_sha256(split.get("split_sha256"), "D4 split_sha256"),
        assignments=assignments,
        canonical=canonical,
        policy_compatible=False,
    )
    summary.update(
        {
            "episode_count": len(entries),
            "sample_count": sum(
                _integer(entry.get("frame_count"), "D4 frame_count")
                for entry in entries
            ),
            "sample_unit": "region_frame",
            "mismatched_episode_count": _count_evidence(mismatch_episodes),
            "mismatched_sample_count": _count_evidence(mismatch_frames),
        }
    )
    return summary


def _audit_d5_tracklet_manifest(
    path: Path, canonical: Mapping[str, Any]
) -> dict[str, Any]:
    manifest = _read_json_object(path)
    if manifest.get("schema_version") != "d5.tracklet-dataset.v2":
        raise CanonicalSeedSplitAuditError(
            "d5_tracklet_manifest_schema_mismatch",
            "unsupported D5 tracklet graph manifest",
        )
    entries = _entry_sequence(manifest.get("episodes"), "D5 tracklet episodes")
    assignments = _assignments_from_entries(entries, module="D5 tracklet")
    policy = _mapping(manifest.get("split_policy"), "D5 tracklet split_policy")
    policy_compatible = _d5_policy_compatible(policy)
    mismatch_episodes, mismatch_edges = _entry_mismatch_counts(
        entries,
        canonical["assignment_by_seed"],
        sample_count_key="edge_count",
        module="D5 tracklet",
    )
    summary = _module_seed_summary(
        module="d5_tracklet_graph",
        manifest_path=path,
        original_split_hash=_sha256(
            manifest.get("split_sha256"), "D5 tracklet split_sha256"
        ),
        assignments=assignments,
        canonical=canonical,
        policy_compatible=policy_compatible,
    )
    summary.update(
        {
            "episode_count": len(entries),
            "sample_count": sum(
                _integer(entry.get("edge_count"), "D5 tracklet edge_count")
                for entry in entries
            ),
            "sample_unit": "candidate_edge",
            "mismatched_episode_count": _count_evidence(mismatch_episodes),
            "mismatched_sample_count": _count_evidence(mismatch_edges),
        }
    )
    return summary


def _audit_d5_active_vision_manifest(
    path: Path, canonical: Mapping[str, Any]
) -> dict[str, Any]:
    manifest = _read_json_object(path)
    if manifest.get("schema_version") != "d5.active-vision-episode-dataset.v3":
        raise CanonicalSeedSplitAuditError(
            "d5_active_vision_manifest_schema_mismatch",
            "unsupported D5 active-vision manifest",
        )
    entries = _entry_sequence(manifest.get("episodes"), "D5 active-vision episodes")
    assignments = _assignments_from_entries(entries, module="D5 active vision")
    policy = _mapping(manifest.get("split_policy"), "D5 active-vision split_policy")
    policy_compatible = _d5_policy_compatible(policy)
    mismatch_episodes, mismatch_samples = _entry_mismatch_counts(
        entries,
        canonical["assignment_by_seed"],
        sample_count_key="sample_count",
        module="D5 active vision",
    )
    summary = _module_seed_summary(
        module="d5_active_vision",
        manifest_path=path,
        original_split_hash=_sha256(
            manifest.get("split_sha256"), "D5 active-vision split_sha256"
        ),
        assignments=assignments,
        canonical=canonical,
        policy_compatible=policy_compatible,
    )
    summary.update(
        {
            "episode_count": len(entries),
            "sample_count": sum(
                _integer(entry.get("sample_count"), "D5 active-vision sample_count")
                for entry in entries
            ),
            "sample_unit": "active_vision_sample",
            "mismatched_episode_count": _count_evidence(mismatch_episodes),
            "mismatched_sample_count": _count_evidence(mismatch_samples),
        }
    )
    return summary


def _module_seed_summary(
    *,
    module: str,
    manifest_path: Path,
    original_split_hash: str,
    assignments: Mapping[int, frozenset[str]],
    canonical: Mapping[str, Any],
    policy_compatible: bool,
) -> dict[str, Any]:
    canonical_assignments = canonical["assignment_by_seed"]
    expected_seeds = set(canonical["training_seeds"])
    module_seeds = set(assignments)
    missing = sorted(expected_seeds - module_seeds)
    extra = sorted(module_seeds - expected_seeds)
    reserved = sorted(module_seeds & set(canonical["reserved_seeds"]))
    conflicts = sorted(seed for seed, values in assignments.items() if len(values) != 1)
    mismatches: list[int] = []
    pairs: Counter[str] = Counter()
    for seed in sorted(expected_seeds & module_seeds):
        actual = assignments[seed]
        expected = canonical_assignments[seed]
        if actual != frozenset({expected}):
            mismatches.append(seed)
            for value in sorted(actual):
                pairs[f"{value}_to_{expected}"] += 1
    exact = not (missing or extra or reserved or conflicts or mismatches)
    reasons: list[str] = []
    if missing:
        reasons.append("canonical_training_seed_missing")
    if extra:
        reasons.append("unregistered_seed_present")
    if reserved:
        reasons.append("reserved_evaluation_seed_present")
    if conflicts:
        reasons.append("numeric_seed_spans_multiple_splits")
    if mismatches:
        reasons.append("seed_assignment_differs_from_canonical_registry")
    return {
        "module": module,
        "manifest_sha256": _sha256_file(manifest_path),
        "original_split_hash": original_split_hash,
        "canonical_registry_content_sha256": canonical["content_sha256"],
        "canonical_assignment_sha256": canonical["assignment_sha256"],
        "module_policy_compatible": policy_compatible,
        "seed_counts": {
            split: sum(split in values for values in assignments.values())
            for split in _SPLITS
        },
        "unique_seed_count": len(module_seeds),
        "missing_seed_count": len(missing),
        "missing_seed_values": missing,
        "extra_seed_count": len(extra),
        "extra_seed_values": extra,
        "reserved_seed_count": len(reserved),
        "reserved_seed_values": reserved,
        "internally_conflicting_seed_count": len(conflicts),
        "internally_conflicting_seed_values": conflicts,
        "mismatched_seed_count": len(mismatches),
        "mismatched_seed_values": mismatches,
        "mismatch_pair_counts": dict(sorted(pairs.items())),
        "exact_match": exact,
        "reason": None if exact else ";".join(reasons),
    }


def _assignments_from_split_catalog(
    value: Mapping[str, Any], *, suffix: str
) -> dict[int, frozenset[str]]:
    assignments: dict[int, set[str]] = defaultdict(set)
    for split in _SPLITS:
        for seed in _integer_sequence(value.get(f"{split}{suffix}"), f"{split} seeds"):
            assignments[seed].add(split)
    return {seed: frozenset(splits) for seed, splits in assignments.items()}


def _assignments_from_entries(
    entries: Sequence[Mapping[str, Any]], *, module: str
) -> dict[int, frozenset[str]]:
    assignments: dict[int, set[str]] = defaultdict(set)
    for entry in entries:
        seed = _integer(entry.get("seed"), f"{module} seed")
        assignments[seed].add(_split(entry.get("split"), f"{module} split"))
    return {seed: frozenset(splits) for seed, splits in assignments.items()}


def _entry_mismatch_counts(
    entries: Sequence[Mapping[str, Any]],
    canonical: Mapping[int, str],
    *,
    sample_count_key: str,
    module: str,
) -> tuple[int, int]:
    episode_count = 0
    sample_count = 0
    for entry in entries:
        seed = _integer(entry.get("seed"), f"{module} seed")
        declared = _split(entry.get("split"), f"{module} split")
        if canonical.get(seed) != declared:
            episode_count += 1
            sample_count += _integer(
                entry.get(sample_count_key), f"{module} {sample_count_key}"
            )
    return episode_count, sample_count


def _d5_policy_compatible(policy: Mapping[str, Any]) -> bool:
    return bool(
        policy.get("shared_seed_values_atomic_across_scenarios") is True
        and _numeric_equal(policy.get("split_seed"), EXPECTED_SPLIT_SEED)
        and _numeric_equal(
            policy.get("validation_fraction"), EXPECTED_VALIDATION_FRACTION
        )
        and _numeric_equal(policy.get("test_fraction"), EXPECTED_TEST_FRACTION)
    )


def _assign_seed_splits(
    seed_values: Iterable[int],
    *,
    split_seed: int,
    validation_fraction: float,
    test_fraction: float,
    minimum_test_seed_count: int,
) -> dict[int, str]:
    seeds = sorted(set(int(seed) for seed in seed_values))
    ordered = sorted(
        seeds,
        key=lambda seed: (
            hashlib.sha256(
                f"{ORDERING_COMPATIBILITY_VERSION}|{split_seed}\0{seed}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            seed,
        ),
    )
    test_count = max(1, min(len(seeds) - 2, round(len(seeds) * test_fraction)))
    validation_count = max(
        1,
        min(len(seeds) - test_count - 1, round(len(seeds) * validation_fraction)),
    )
    if test_count < minimum_test_seed_count:
        raise CanonicalSeedSplitAuditError(
            "shared_registry_test_split_too_small",
            "canonical test split is below its declared minimum",
        )
    return {
        seed: (
            "test"
            if index < test_count
            else "validation"
            if index < test_count + validation_count
            else "train"
        )
        for index, seed in enumerate(ordered)
    }


def _count_evidence(value: int | None, *, reason: str | None = None) -> dict[str, Any]:
    return {
        "available": value is not None,
        "value": value,
        "reason": None if value is not None else reason,
    }


def _entry_sequence(value: Any, name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise CanonicalSeedSplitAuditError(
            "module_episode_inventory_invalid", f"{name} must be a list"
        )
    return tuple(_mapping(item, name) for item in value)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CanonicalSeedSplitAuditError(
            "json_invalid", f"invalid JSON object: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise CanonicalSeedSplitAuditError(
            "json_object_required", f"JSON root must be an object: {path}"
        )
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CanonicalSeedSplitAuditError(
            "mapping_required", f"{name} must be an object"
        )
    return value


def _integer_sequence(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise CanonicalSeedSplitAuditError(
            "integer_list_required", f"{name} must be a list"
        )
    result = tuple(_integer(item, name) for item in value)
    if len(result) != len(set(result)):
        raise CanonicalSeedSplitAuditError(
            "integer_list_duplicate", f"{name} contains duplicate seeds"
        )
    return result


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise CanonicalSeedSplitAuditError(
            "integer_required", f"{name} must be an integer"
        )
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalSeedSplitAuditError(
            "integer_required", f"{name} must be an integer"
        ) from exc
    if result < 0 or value != result:
        raise CanonicalSeedSplitAuditError(
            "integer_required", f"{name} must be a non-negative integer"
        )
    return result


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    return _integer(value, "optional count")


def _fraction(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalSeedSplitAuditError(
            "fraction_required", f"{name} must be numeric"
        ) from exc
    if not math.isfinite(result) or not 0.0 < result < 1.0:
        raise CanonicalSeedSplitAuditError(
            "fraction_required", f"{name} must be finite and in (0, 1)"
        )
    return result


def _split(value: Any, name: str) -> str:
    result = str(value)
    if result not in _SPLITS:
        raise CanonicalSeedSplitAuditError(
            "split_invalid", f"{name} must be train, validation, or test"
        )
    return result


def _numeric_equal(left: Any, right: int | float) -> bool:
    try:
        value = float(left)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and value == float(right)


def _git_commit(value: Any, name: str) -> str:
    text = str(value or "")
    if len(text) != 40 or any(character not in _HEX64 for character in text):
        raise CanonicalSeedSplitAuditError(
            "git_commit_invalid", f"{name} must be a lowercase 40-character hash"
        )
    return text


def _sha256(value: Any, name: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(character not in _HEX64 for character in text):
        raise CanonicalSeedSplitAuditError(
            "sha256_invalid", f"{name} must be a lowercase SHA-256 digest"
        )
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
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CanonicalSeedSplitAuditError(
            "source_artifact_missing", f"cannot read source artifact: {path}"
        ) from exc
    return digest.hexdigest()


__all__ = [
    "CANONICAL_SEED_SPLIT_READINESS_SCHEMA_VERSION",
    "CanonicalSeedSplitAuditError",
    "audit_canonical_seed_split_readiness",
]
