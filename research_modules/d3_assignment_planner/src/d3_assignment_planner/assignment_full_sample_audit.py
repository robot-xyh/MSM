"""Fail-closed, read-only audit for the formal D3 assignment dataset."""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from collections.abc import Mapping as MappingABC
import csv
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from .learning_data import (
    DATASET_FRAMES_FILENAME,
    DATASET_MANIFEST_FILENAME,
    DATASET_SPLITS,
    LEARNING_DATASET_SCHEMA_V2,
    LEARNING_DATASET_SPLIT_POLICY_V2,
    LearningDatasetManifest,
    LearningFrameRecord,
    assign_seed_splits,
)
from .shared_seed_registry import (
    SHARED_SEED_SPLIT_POLICY_VERSION,
    SHARED_SEED_SPLIT_SCHEMA_VERSION,
    SHARED_SEED_SPLIT_UNIT,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
)


ASSIGNMENT_FULL_SAMPLE_AUDIT_SCHEMA_V1 = (
    "d3.assignment-full-sample-audit.v1"
)
ASSIGNMENT_FULL_SAMPLE_AUDIT_PURPOSE = (
    "formal_assignment_behavior_cloning_full_sample_admission"
)
FORMAL_VALIDATION_DATE = "2026-07-21"
_EXPECTED_SPLITS = ("train", "validation", "test")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_KEY_PATTERN = re.compile(
    rb'"[^"\\]*(?:truth|actor|global_track_id|vehicle_name|object_name|uuid)[^"\\]*"\s*:',
    re.IGNORECASE,
)


class AssignmentFullSampleAuditError(ValueError):
    """Raised when the audit itself cannot run without touching source data."""


@dataclass(frozen=True)
class AssignmentFullSampleAuditExpected:
    """Frozen source bindings and inventory for one admitted formal corpus."""

    dataset_manifest_sha256: str
    dataset_frames_sha256: str
    training_registry_sha256: str
    shared_registry_sha256: str
    generation_summary_sha256: str
    episode_progress_sha256: str
    batch_export_summary_sha256: str
    shared_registry_content_sha256: str
    dataset_split_hash: str
    source_git_commit: str
    source_schedule_sha256: str
    episode_count: int
    frame_count: int
    candidate_edge_count: int
    selected_action_count: int
    canonical_episode_counts: Mapping[str, int]
    actual_episode_counts: Mapping[str, int]
    actual_frame_counts: Mapping[str, int]
    training_seed_count: int
    reserved_evaluation_seeds: tuple[int, ...]

    def __post_init__(self) -> None:
        for name in (
            "dataset_manifest_sha256",
            "dataset_frames_sha256",
            "training_registry_sha256",
            "shared_registry_sha256",
            "generation_summary_sha256",
            "episode_progress_sha256",
            "batch_export_summary_sha256",
            "shared_registry_content_sha256",
            "dataset_split_hash",
            "source_schedule_sha256",
        ):
            if not _HASH_PATTERN.fullmatch(str(getattr(self, name))):
                raise ValueError(f"{name} must be one lowercase SHA256 value")
        if not re.fullmatch(r"[0-9a-f]{40}", str(self.source_git_commit)):
            raise ValueError("source_git_commit must be one lowercase Git object ID")
        for name in (
            "episode_count",
            "frame_count",
            "candidate_edge_count",
            "selected_action_count",
            "training_seed_count",
        ):
            if int(getattr(self, name)) < 1:
                raise ValueError(f"{name} must be positive")
        for name in (
            "canonical_episode_counts",
            "actual_episode_counts",
            "actual_frame_counts",
        ):
            value = getattr(self, name)
            if set(value) != set(_EXPECTED_SPLITS):
                raise ValueError(f"{name} must contain train/validation/test")
            normalized = {
                split: int(value[split]) for split in _EXPECTED_SPLITS
            }
            if any(item < 1 for item in normalized.values()):
                raise ValueError(f"{name} counts must be positive")
            object.__setattr__(self, name, MappingProxyType(normalized))
        reserved = tuple(int(seed) for seed in self.reserved_evaluation_seeds)
        if reserved != tuple(sorted(set(reserved))):
            raise ValueError("reserved evaluation seeds must be sorted and unique")
        object.__setattr__(self, "reserved_evaluation_seeds", reserved)

    def bindings(self) -> dict[str, Any]:
        return {
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "dataset_frames_sha256": self.dataset_frames_sha256,
            "training_registry_sha256": self.training_registry_sha256,
            "shared_registry_sha256": self.shared_registry_sha256,
            "generation_summary_sha256": self.generation_summary_sha256,
            "episode_progress_sha256": self.episode_progress_sha256,
            "batch_export_summary_sha256": self.batch_export_summary_sha256,
            "shared_registry_content_sha256": (
                self.shared_registry_content_sha256
            ),
            "dataset_split_hash": self.dataset_split_hash,
            "source_git_commit": self.source_git_commit,
            "source_schedule_sha256": self.source_schedule_sha256,
        }


FORMAL_ASSIGNMENT_900_EXPECTED = AssignmentFullSampleAuditExpected(
    dataset_manifest_sha256=(
        "816fe6e965d4f8d790e89a00a7c90e28bb8cd08a257fe685790669ab774a9089"
    ),
    dataset_frames_sha256=(
        "6761d35d6b48639a5eb4f3306f7b3f12ca72352a1028296a0c39a4b90fdb59a2"
    ),
    training_registry_sha256=(
        "2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f"
    ),
    shared_registry_sha256=(
        "68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f"
    ),
    generation_summary_sha256=(
        "f639eea692eb09e88ed07a9fa5913381669b47217e78545b77e80b36122cb7c5"
    ),
    episode_progress_sha256=(
        "7e209e0e357dd1835c13288fb5153155f5123ebbf15427e1f130855660bbb120"
    ),
    batch_export_summary_sha256=(
        "c77069096e3ca74742dc49ac869b3623e63fa13dcc59ddccb89133375be68126"
    ),
    shared_registry_content_sha256=(
        "29eb6895c4aa570b068f15141cbbbfede3041519117852d1ad48e848a25af146"
    ),
    dataset_split_hash=(
        "679a9051e8637fad38d935eb685f09dd8abc8d43043a28264dab64b077ac70a2"
    ),
    source_git_commit="39b097e72487567ac915c2297eaa27eed49ef76b",
    source_schedule_sha256=(
        "5bb79b3f5cca264033fc5ca3d643e5c84241e7db9c3754d2277b78ebd4002c81"
    ),
    episode_count=900,
    frame_count=1604,
    candidate_edge_count=3_658_815,
    selected_action_count=117_304,
    canonical_episode_counts={"train": 60, "validation": 20, "test": 20},
    actual_episode_counts={"train": 540, "validation": 180, "test": 180},
    actual_frame_counts={"train": 962, "validation": 320, "test": 322},
    training_seed_count=100,
    reserved_evaluation_seeds=tuple(range(1000, 1020)),
)


class _Violations:
    def __init__(self, maximum_details: int = 200) -> None:
        self.total = 0
        self.details: list[str] = []
        self.maximum_details = int(maximum_details)

    def add(self, code: str) -> None:
        self.total += 1
        if len(self.details) < self.maximum_details:
            self.details.append(str(code))

    def require(self, condition: bool, code: str) -> None:
        if not condition:
            self.add(code)


@dataclass
class _FrameAuditState:
    frame_count: int
    episode_frame_counts: Counter[tuple[str, int, str]]
    split_frame_counts: Counter[str]
    split_episode_counts: Counter[str]
    split_candidate_counts: Counter[str]
    split_selected_counts: Counter[str]
    seed_splits: dict[int, str]
    episode_splits: dict[tuple[str, int, str], str]
    candidate_edge_count: int
    selected_action_count: int
    feature_value_count: int
    target_record_count: int
    resource_record_count: int
    version_checked_frame_count: int
    version_regression_count: int
    frame_sequence_violation_count: int
    timestamp_sequence_violation_count: int
    constraint_checked_frame_count: int
    identity_field_occurrence_count: int
    global_track_id_occurrence_count: int
    canonical_order_valid: bool
    split_hash: str | None
    hard_reject_reason_counts: Counter[str]
    feedback_result_counts: Counter[str]
    hysteresis_result_counts: Counter[str]


def audit_assignment_full_sample_dataset(
    dataset_dir: str | Path,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    generation_summary_path: str | Path,
    episode_progress_path: str | Path,
    batch_export_summary_path: str | Path,
    output_json_path: str | Path,
    output_markdown_path: str | Path,
    expected: AssignmentFullSampleAuditExpected = FORMAL_ASSIGNMENT_900_EXPECTED,
    validation_date: str = FORMAL_VALIDATION_DATE,
) -> dict[str, Any]:
    """Audit all formal D3 frames without mutating or materializing the corpus."""

    dataset = Path(dataset_dir).resolve()
    sources = {
        "dataset_manifest": dataset / DATASET_MANIFEST_FILENAME,
        "dataset_frames": dataset / DATASET_FRAMES_FILENAME,
        "training_registry": Path(training_seed_registry_path).resolve(),
        "shared_registry": Path(shared_seed_registry_path).resolve(),
        "generation_summary": Path(generation_summary_path).resolve(),
        "episode_progress": Path(episode_progress_path).resolve(),
        "batch_export_summary": Path(batch_export_summary_path).resolve(),
    }
    outputs = (
        Path(output_json_path).resolve(),
        Path(output_markdown_path).resolve(),
    )
    _validate_source_and_output_paths(sources, outputs)
    source_hashes_before = {
        name: _file_sha256(path) for name, path in sources.items()
    }
    violations = _Violations()
    expected_bindings = expected.bindings()
    actual_bindings: dict[str, Any] = {
        f"{name}_sha256": value
        for name, value in source_hashes_before.items()
    }
    binding_checks: dict[str, dict[str, Any]] = {}
    _bind(
        binding_checks,
        violations,
        "dataset_manifest_sha256",
        expected.dataset_manifest_sha256,
        source_hashes_before["dataset_manifest"],
    )
    _bind(
        binding_checks,
        violations,
        "dataset_frames_sha256",
        expected.dataset_frames_sha256,
        source_hashes_before["dataset_frames"],
    )
    _bind(
        binding_checks,
        violations,
        "training_registry_sha256",
        expected.training_registry_sha256,
        source_hashes_before["training_registry"],
    )
    _bind(
        binding_checks,
        violations,
        "shared_registry_sha256",
        expected.shared_registry_sha256,
        source_hashes_before["shared_registry"],
    )
    _bind(
        binding_checks,
        violations,
        "generation_summary_sha256",
        expected.generation_summary_sha256,
        source_hashes_before["generation_summary"],
    )
    _bind(
        binding_checks,
        violations,
        "episode_progress_sha256",
        expected.episode_progress_sha256,
        source_hashes_before["episode_progress"],
    )
    _bind(
        binding_checks,
        violations,
        "batch_export_summary_sha256",
        expected.batch_export_summary_sha256,
        source_hashes_before["batch_export_summary"],
    )

    manifest_raw = _read_json_object(sources["dataset_manifest"])
    manifest: LearningDatasetManifest | None = None
    try:
        manifest = LearningDatasetManifest.from_dict(manifest_raw)
        violations.require(
            set(manifest_raw) == set(manifest.to_dict()),
            "dataset_manifest_field_set_mismatch",
        )
    except (KeyError, TypeError, ValueError) as exc:
        violations.add(f"dataset_manifest_invalid:{_stable_message(exc)}")

    training_registry = _read_json_object(sources["training_registry"])
    shared_registry = _read_json_object(sources["shared_registry"])
    registry_result = _audit_seed_registries(
        training_registry,
        shared_registry,
        source_hashes_before=source_hashes_before,
        expected=expected,
        manifest=manifest,
        violations=violations,
    )
    actual_bindings.update(registry_result["actual_bindings"])
    actual_bindings.update(registry_result["binding_values"])
    for name, actual in registry_result["binding_values"].items():
        expected_value = expected_bindings[name]
        _bind(binding_checks, violations, name, expected_value, actual)

    frame_state = _audit_frames(
        sources["dataset_frames"],
        manifest=manifest,
        split_by_seed=registry_result["split_by_seed"],
        reserved_seeds=set(expected.reserved_evaluation_seeds),
        violations=violations,
    )
    if manifest is not None:
        _audit_manifest_inventory(manifest, frame_state, expected, violations)

    progress = _audit_episode_progress(
        sources["episode_progress"],
        frame_state=frame_state,
        expected=expected,
        violations=violations,
    )
    generation_summary = _read_json_object(sources["generation_summary"])
    batch_summary = _read_json_object(sources["batch_export_summary"])
    provenance = _audit_generation_provenance(
        generation_summary,
        batch_summary,
        progress=progress,
        expected=expected,
        manifest=manifest,
        violations=violations,
    )

    source_hashes_after = {
        name: _file_sha256(path) for name, path in sources.items()
    }
    violations.require(
        source_hashes_after == source_hashes_before,
        "source_artifacts_changed_during_audit",
    )
    structural_complete = violations.total == 0
    data_status = "complete" if structural_complete else "pending"
    overall_status = "partial" if structural_complete else "pending"
    coverage = _coverage_payload(frame_state, registry_result, expected)
    report: dict[str, Any] = {
        "schema_version": ASSIGNMENT_FULL_SAMPLE_AUDIT_SCHEMA_V1,
        "validation_date": str(validation_date),
        "purpose": ASSIGNMENT_FULL_SAMPLE_AUDIT_PURPOSE,
        "source_files": {name: str(path) for name, path in sources.items()},
        "expected_bindings": expected_bindings,
        "actual_bindings": actual_bindings,
        "binding_checks": binding_checks,
        "acceptance_thresholds": {
            "audit_violation_count_maximum": 0,
            "episode_count": int(expected.episode_count),
            "decision_sample_count": int(expected.frame_count),
            "canonical_episode_counts": dict(expected.canonical_episode_counts),
            "actual_episode_counts": dict(expected.actual_episode_counts),
            "actual_frame_counts": dict(expected.actual_frame_counts),
            "candidate_edge_count": int(expected.candidate_edge_count),
            "action_label_count": int(expected.candidate_edge_count),
            "selected_action_count": int(expected.selected_action_count),
            "reserved_seed_overlap_maximum": 0,
            "online_truth_use_count_maximum": 0,
            "dirty_episode_count_maximum": 0,
            "constraint_violation_count_maximum": 0,
            "global_track_id_illegal_field_count_maximum": 0,
        },
        "audit": {
            "status": overall_status,
            "passed": structural_complete,
            "violation_count": int(violations.total),
            "violations": violations.details,
            "violation_details_truncated": violations.total
            > len(violations.details),
        },
        "coverage": coverage,
        "artifact_integrity": {
            "source_hashes_before": source_hashes_before,
            "source_hashes_after": source_hashes_after,
            "source_artifacts_unchanged": (
                source_hashes_after == source_hashes_before
            ),
            "source_file_count": len(sources),
            "source_artifact_set_sha256": _sha256_json(source_hashes_before),
            "dataset_manifest_frames_binding_valid": bool(
                manifest is not None
                and manifest.frames_sha256
                == source_hashes_before["dataset_frames"]
            ),
            "formal_source_data_modified": bool(
                source_hashes_before["dataset_manifest"]
                != expected.dataset_manifest_sha256
                or source_hashes_before["dataset_frames"]
                != expected.dataset_frames_sha256
            ),
        },
        "schema_and_numeric_audit": {
            "dataset_schema_version": (
                None if manifest is None else manifest.schema_version
            ),
            "split_policy_version": (
                None if manifest is None else manifest.split_policy_version
            ),
            "validated_frame_count": int(frame_state.frame_count),
            "feature_value_count": int(frame_state.feature_value_count),
            "nonfinite_numeric_value_count": _count_violation_prefix(
                violations.details, "nonfinite_"
            ),
            "candidate_dimension_mismatch_count": _count_violation_prefix(
                violations.details, "candidate_dimension_"
            ),
            "all_validated_numeric_features_finite": not any(
                item.startswith("nonfinite_") for item in violations.details
            ),
        },
        "action_and_constraint_audit": {
            "constraint_checked_frame_count": int(
                frame_state.constraint_checked_frame_count
            ),
            "candidate_edge_count": int(frame_state.candidate_edge_count),
            "resource_target_action_label_count": int(
                frame_state.candidate_edge_count
            ),
            "selected_resource_target_action_count": int(
                frame_state.selected_action_count
            ),
            "capacity_violation_count": _count_violation_prefix(
                violations.details, "resource_capacity_"
            ),
            "demand_slot_violation_count": _count_violation_prefix(
                violations.details, "target_demand_"
            ),
            "action_index_violation_count": _count_violation_prefix(
                violations.details, "action_index_"
            ),
            "hard_reject_reason_counts": dict(
                sorted(frame_state.hard_reject_reason_counts.items())
            ),
        },
        "split_and_provenance_audit": {
            "canonical_episode_identity_counts": coverage[
                "canonical_episode_counts"
            ],
            "actual_source_episode_counts": coverage[
                "actual_episode_counts"
            ],
            "actual_decision_sample_counts": coverage[
                "actual_frame_counts"
            ],
            "reserved_evaluation_seeds": list(
                expected.reserved_evaluation_seeds
            ),
            "reserved_seed_overlap": registry_result["reserved_overlap"],
            "dirty_episode_count": int(progress["dirty_episode_count"]),
            "online_truth_use_count": int(progress["online_truth_use_count"]),
            "finite_episode_count": int(progress["finite_episode_count"]),
            "source_git_commit": provenance["source_git_commit"],
            "source_schedule_sha256": provenance["source_schedule_sha256"],
            "repository_dirty": provenance["repository_dirty"],
        },
        "version_and_identity_audit": {
            "version_checked_frame_count": int(
                frame_state.version_checked_frame_count
            ),
            "previous_plan_version_regression_count": int(
                frame_state.version_regression_count
            ),
            "frame_sequence_violation_count": int(
                frame_state.frame_sequence_violation_count
            ),
            "timestamp_sequence_violation_count": int(
                frame_state.timestamp_sequence_violation_count
            ),
            "anonymous_ordinal_identity_checked_frame_count": int(
                frame_state.frame_count
            ),
            "online_identity_field_occurrence_count": int(
                frame_state.identity_field_occurrence_count
            ),
            "global_track_id_illegal_field_count": int(
                frame_state.global_track_id_occurrence_count
            ),
            "global_track_id_created_or_rewritten": bool(
                frame_state.global_track_id_occurrence_count
            ),
            "current_plan_owner_binding": "unavailable",
            "current_plan_version_binding": "unavailable",
            "stale_plan_runtime_rejection_evidence": "unavailable",
            "explanation": (
                "formal learning frames intentionally contain anonymous ordinal "
                "tokens and previous_plan_version only; current owner/version "
                "and runtime stale-rejection records are not present"
            ),
        },
        "generation_evidence": {
            **progress,
            "feedback_result_counts": dict(
                sorted(frame_state.feedback_result_counts.items())
            ),
            "hysteresis_result_counts": dict(
                sorted(frame_state.hysteresis_result_counts.items())
            ),
            "feedback_and_hysteresis_value_type": "string",
        },
        "evidence_availability": {
            "offline_rule_teacher_reward_component_frame_count": int(
                frame_state.frame_count
            ),
            "real_runtime_applied_ack": "unavailable",
            "real_runtime_outcome_attribution": "unavailable",
            "causal_or_counterfactual_reward": "unavailable",
            "same_seed_paired_shadow_non_degradation": "unavailable",
            "zero_padding_used_for_unavailable_evidence": False,
        },
        "admission": {
            "assignment_full_sample_structural_audit": data_status,
            "runtime_plan_binding_evidence": "partial",
            "overall_status": overall_status,
            "model_training_performed": False,
            "weights_written": False,
            "ppo": False,
            "assist": False,
            "online_authority": False,
            "rule_cost_and_hungarian_default": True,
            "rule_fallback_required": True,
        },
        "remaining_gates": [
            "real_runtime_assignment_applied_ack",
            "real_runtime_outcome_attribution",
            "causal_or_counterfactual_reward",
            "same_seed_paired_rule_vs_learning_shadow_non_degradation",
            "current_plan_owner_and_current_version_runtime_binding",
            "ppo_assist_and_authority_remain_closed",
        ],
    }
    report["content_sha256"] = _sha256_json(report)
    _write_json(outputs[0], report)
    _write_markdown(outputs[1], report)
    return report


def _audit_seed_registries(
    training: Mapping[str, Any],
    shared: Mapping[str, Any],
    *,
    source_hashes_before: Mapping[str, str],
    expected: AssignmentFullSampleAuditExpected,
    manifest: LearningDatasetManifest | None,
    violations: _Violations,
) -> dict[str, Any]:
    expected_training_fields = {
        "schema_version",
        "git_commit",
        "repository_dirty",
        "schedule_sha256",
        "training_seed_count",
        "training_seeds",
        "reserved_evaluation_seed_count",
        "reserved_evaluation_seeds",
        "overlap_count",
    }
    violations.require(
        set(training) == expected_training_fields,
        "training_registry_field_set_mismatch",
    )
    violations.require(
        training.get("schema_version") == TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "training_registry_schema_mismatch",
    )
    training_seeds = _integer_sequence(
        training.get("training_seeds"), "training_seeds", violations
    )
    reserved_seeds = _integer_sequence(
        training.get("reserved_evaluation_seeds"),
        "reserved_evaluation_seeds",
        violations,
    )
    violations.require(
        training_seeds == tuple(sorted(set(training_seeds))),
        "training_seed_catalog_not_sorted_unique",
    )
    violations.require(
        reserved_seeds == tuple(expected.reserved_evaluation_seeds),
        "reserved_seed_catalog_mismatch",
    )
    violations.require(
        _strict_integer(training.get("training_seed_count"))
        == len(training_seeds)
        == expected.training_seed_count,
        "training_seed_count_mismatch",
    )
    violations.require(
        _strict_integer(training.get("reserved_evaluation_seed_count"))
        == len(reserved_seeds),
        "reserved_seed_count_mismatch",
    )
    violations.require(
        _strict_integer(training.get("overlap_count")) == 0,
        "training_reserved_overlap_declared",
    )
    violations.require(
        not set(training_seeds).intersection(reserved_seeds),
        "training_reserved_seed_overlap",
    )
    violations.require(
        training.get("repository_dirty") is False,
        "training_registry_dirty_source",
    )

    expected_shared_fields = {
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
    }
    violations.require(
        set(shared) == expected_shared_fields,
        "shared_registry_field_set_mismatch",
    )
    violations.require(
        shared.get("schema_version") == SHARED_SEED_SPLIT_SCHEMA_VERSION,
        "shared_registry_schema_mismatch",
    )
    violations.require(
        shared.get("policy_version") == SHARED_SEED_SPLIT_POLICY_VERSION,
        "shared_registry_policy_mismatch",
    )
    violations.require(
        shared.get("ordering_compatibility_version")
        == LEARNING_DATASET_SPLIT_POLICY_V2,
        "shared_registry_ordering_policy_mismatch",
    )
    violations.require(
        shared.get("unit") == SHARED_SEED_SPLIT_UNIT,
        "shared_registry_unit_mismatch",
    )
    content_payload = dict(shared)
    declared_content_sha = str(content_payload.pop("content_sha256", ""))
    actual_content_sha = _sha256_json(content_payload)
    violations.require(
        declared_content_sha == actual_content_sha,
        "shared_registry_content_sha256_mismatch",
    )
    assignments = shared.get("assignments")
    if not isinstance(assignments, list):
        assignments = []
        violations.add("shared_registry_assignments_invalid")
    declared_assignment_sha = str(shared.get("assignment_sha256", ""))
    actual_assignment_sha = _sha256_json(assignments)
    violations.require(
        declared_assignment_sha == actual_assignment_sha,
        "shared_registry_assignment_sha256_mismatch",
    )
    split_by_seed: dict[int, str] = {}
    for index, item in enumerate(assignments):
        if not isinstance(item, MappingABC) or set(item) != {"seed", "split"}:
            violations.add(f"shared_assignment_invalid:{index}")
            continue
        seed = _strict_integer(item.get("seed"))
        split = str(item.get("split"))
        if seed is None or split not in _EXPECTED_SPLITS:
            violations.add(f"shared_assignment_value_invalid:{index}")
            continue
        if seed in split_by_seed:
            violations.add(f"shared_assignment_duplicate_seed:{seed}")
            continue
        split_by_seed[seed] = split
    violations.require(
        tuple(split_by_seed) == training_seeds,
        "shared_assignment_seed_catalog_mismatch",
    )
    split_seed = _strict_integer(shared.get("split_seed"))
    validation_fraction = _strict_float(shared.get("validation_fraction"))
    test_fraction = _strict_float(shared.get("test_fraction"))
    minimum_test = _strict_integer(shared.get("minimum_test_seed_count"))
    try:
        reproduced = dict(
            assign_seed_splits(
                training_seeds,
                split_seed=0 if split_seed is None else split_seed,
                validation_fraction=(
                    0.2 if validation_fraction is None else validation_fraction
                ),
                test_fraction=0.2 if test_fraction is None else test_fraction,
                minimum_unseen_seed_count=(
                    1 if minimum_test is None else minimum_test
                ),
            )
        )
    except ValueError as exc:
        reproduced = {}
        violations.add(f"shared_assignment_policy_invalid:{_stable_message(exc)}")
    violations.require(
        reproduced == split_by_seed,
        "shared_assignment_policy_reproduction_mismatch",
    )
    canonical_counts = Counter(split_by_seed.values())
    violations.require(
        {split: canonical_counts[split] for split in _EXPECTED_SPLITS}
        == dict(expected.canonical_episode_counts),
        "canonical_episode_split_not_expected_60_20_20",
    )
    split_seed_values = shared.get("split_seed_values")
    if not isinstance(split_seed_values, MappingABC):
        split_seed_values = {}
        violations.add("shared_split_seed_values_invalid")
    for split in _EXPECTED_SPLITS:
        declared = _integer_sequence(
            split_seed_values.get(split),
            f"split_seed_values.{split}",
            violations,
        )
        actual = tuple(
            seed for seed in training_seeds if split_by_seed.get(seed) == split
        )
        violations.require(
            declared == actual,
            f"shared_split_seed_values_mismatch:{split}",
        )
        if manifest is not None:
            violations.require(
                tuple(manifest.split_seed_values[split]) == actual,
                f"manifest_shared_seed_split_mismatch:{split}",
            )
    source = shared.get("source")
    if not isinstance(source, MappingABC):
        source = {}
        violations.add("shared_registry_source_invalid")
    violations.require(
        source.get("training_seed_registry_sha256")
        == source_hashes_before["training_registry"],
        "shared_source_training_registry_sha256_mismatch",
    )
    for field in ("git_commit", "repository_dirty", "schedule_sha256"):
        violations.require(
            source.get(field) == training.get(field),
            f"shared_source_{field}_mismatch",
        )
    consumer = shared.get("consumer_contract")
    violations.require(
        consumer
        == {
            "original_dataset_mutation_allowed": False,
            "module_local_split_override_allowed": False,
            "cross_module_training_requires_exact_registry": True,
            "reserved_evaluation_seeds_allowed": False,
        },
        "shared_consumer_contract_not_fail_closed",
    )
    reserved_overlap = sorted(set(training_seeds).intersection(reserved_seeds))
    return {
        "split_by_seed": split_by_seed,
        "canonical_counts": {
            split: int(canonical_counts[split]) for split in _EXPECTED_SPLITS
        },
        "reserved_overlap": reserved_overlap,
        "actual_bindings": {
            "shared_registry_assignment_sha256": actual_assignment_sha,
            "shared_registry_declared_assignment_sha256": declared_assignment_sha,
        },
        "binding_values": {
            "shared_registry_content_sha256": actual_content_sha,
            "source_git_commit": str(training.get("git_commit", "")),
            "source_schedule_sha256": str(
                training.get("schedule_sha256", "")
            ),
            "dataset_split_hash": (
                "" if manifest is None else manifest.split_hash
            ),
        },
    }


def _audit_frames(
    path: Path,
    *,
    manifest: LearningDatasetManifest | None,
    split_by_seed: Mapping[int, str],
    reserved_seeds: set[int],
    violations: _Violations,
) -> _FrameAuditState:
    split_frame_counts: Counter[str] = Counter()
    split_candidate_counts: Counter[str] = Counter()
    split_selected_counts: Counter[str] = Counter()
    episode_frame_counts: Counter[tuple[str, int, str]] = Counter()
    seed_splits: dict[int, str] = {}
    episode_splits: dict[tuple[str, int, str], str] = {}
    episode_sequence: dict[
        tuple[str, int, str], tuple[int, float, int]
    ] = {}
    seen_frame_keys: set[tuple[str, int, str, int]] = set()
    candidate_edge_count = 0
    selected_action_count = 0
    feature_value_count = 0
    target_record_count = 0
    resource_record_count = 0
    version_checked_frame_count = 0
    version_regression_count = 0
    frame_sequence_violation_count = 0
    timestamp_sequence_violation_count = 0
    constraint_checked_frame_count = 0
    identity_occurrences = 0
    global_track_occurrences = 0
    canonical_order_valid = True
    prior_canonical_key: tuple[str, int, str, int] | None = None
    hard_reject_reasons: Counter[str] = Counter()
    feedback_results: Counter[str] = Counter()
    hysteresis_results: Counter[str] = Counter()
    frame_count = 0

    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                violations.add(f"blank_dataset_frame_line:{line_number}")
                continue
            line_identity = len(_IDENTITY_KEY_PATTERN.findall(raw_line))
            identity_occurrences += line_identity
            global_track_occurrences += raw_line.lower().count(b"global_track_id")
            try:
                payload = json.loads(
                    raw_line,
                    parse_constant=lambda value: _reject_json_constant(value),
                )
            except (json.JSONDecodeError, ValueError) as exc:
                if line_identity:
                    violations.add(f"online_truth_or_identity_field:{line_number}")
                elif "non-finite JSON constant" in str(exc):
                    violations.add(f"nonfinite_numeric_json:{line_number}")
                else:
                    violations.add(
                        f"invalid_frame_json:{line_number}:{_stable_message(exc)}"
                    )
                continue
            try:
                record = LearningFrameRecord.from_dict(payload)
            except (KeyError, TypeError, ValueError) as exc:
                if line_identity:
                    violations.add(f"online_truth_or_identity_field:{line_number}")
                else:
                    violations.add(
                        f"invalid_frame_schema:{line_number}:{_stable_message(exc)}"
                    )
                continue
            frame_count += 1
            frame_key = (
                record.scenario_version,
                int(record.seed),
                record.episode,
                int(record.frame_index),
            )
            episode_key = frame_key[:3]
            if frame_key in seen_frame_keys:
                violations.add(f"duplicate_frame:{line_number}")
            seen_frame_keys.add(frame_key)
            if prior_canonical_key is not None and frame_key <= prior_canonical_key:
                canonical_order_valid = False
                violations.add(f"noncanonical_frame_order:{line_number}")
            prior_canonical_key = frame_key
            episode_frame_counts[episode_key] += 1
            split_frame_counts[record.split] += 1
            prior_seed_split = seed_splits.setdefault(record.seed, record.split)
            if prior_seed_split != record.split:
                violations.add(f"seed_split_leakage:{record.seed}")
            prior_episode_split = episode_splits.setdefault(
                episode_key, record.split
            )
            if prior_episode_split != record.split:
                violations.add(f"episode_split_leakage:{record.episode}")
            expected_split = split_by_seed.get(record.seed)
            if expected_split is None or record.split != expected_split:
                violations.add(f"frame_split_assignment_mismatch:{line_number}")
            if record.seed in reserved_seeds:
                violations.add(f"reserved_seed_leakage:{record.seed}")

            previous = episode_sequence.get(episode_key)
            if previous is None:
                if record.frame_index != 0:
                    frame_sequence_violation_count += 1
                    violations.add(f"frame_sequence_initial_index:{line_number}")
                if record.previous_plan_version != 0:
                    version_regression_count += 1
                    violations.add(f"plan_version_initial_not_zero:{line_number}")
            else:
                prior_index, prior_timestamp, prior_version = previous
                if record.frame_index != prior_index + 1:
                    frame_sequence_violation_count += 1
                    violations.add(f"frame_sequence_noncontiguous:{line_number}")
                if record.timestamp_s <= prior_timestamp:
                    timestamp_sequence_violation_count += 1
                    violations.add(f"timestamp_sequence_not_increasing:{line_number}")
                if record.previous_plan_version < prior_version:
                    version_regression_count += 1
                    violations.add(f"plan_version_regression:{line_number}")
            episode_sequence[episode_key] = (
                int(record.frame_index),
                float(record.timestamp_s),
                int(record.previous_plan_version),
            )
            version_checked_frame_count += 1

            features = np.asarray(record.candidate_features, dtype=float)
            matrix = np.asarray(record.rule_cost_matrix, dtype=float)
            rule_costs = np.asarray(record.rule_costs, dtype=float)
            target_threats = np.asarray(record.target_threat_scores, dtype=float)
            if not (
                np.all(np.isfinite(features))
                and np.all(np.isfinite(matrix))
                and np.all(np.isfinite(rule_costs))
                and np.all(np.isfinite(record.unassigned_costs))
                and np.all(np.isfinite(target_threats))
            ):
                violations.add(f"nonfinite_numeric_feature:{line_number}")
            edges = tuple(record.candidate_edge_indices)
            selected = tuple(record.rule_selected_edges)
            candidate_set = set(edges)
            if len(edges) != len(candidate_set):
                violations.add(f"action_index_duplicate_candidate:{line_number}")
            if len(selected) != len(set(selected)):
                violations.add(f"action_index_duplicate_selected:{line_number}")
            if features.shape != (len(edges), len(manifest.feature_names) if manifest else features.shape[1]):
                violations.add(f"candidate_dimension_feature:{line_number}")
            if edges:
                edge_array = np.asarray(edges, dtype=int)
                matrix_values = matrix[edge_array[:, 0], edge_array[:, 1]]
                if not np.allclose(
                    matrix_values,
                    rule_costs,
                    rtol=0.0,
                    atol=1e-12,
                ):
                    violations.add(f"candidate_dimension_cost_binding:{line_number}")
            selected_by_target: Counter[int] = Counter()
            selected_by_resource: Counter[int] = Counter()
            for target_index, resource_index in selected:
                selected_by_target[target_index] += 1
                selected_by_resource[resource_index] += 1
                if (target_index, resource_index) not in candidate_set:
                    violations.add(f"action_index_selected_not_candidate:{line_number}")
            for target_index, target in enumerate(record.anonymous_targets):
                required = int(target["required_resource_count"])
                demand_slots = int(record.target_demand_slots[target_index])
                if demand_slots != required:
                    violations.add(f"target_demand_schema_mismatch:{line_number}")
                if selected_by_target[target_index] > demand_slots:
                    violations.add(f"target_demand_capacity_exceeded:{line_number}")
                if selected_by_target[target_index] and not bool(target["assignable"]):
                    violations.add(f"target_demand_unassignable_selected:{line_number}")
            for resource_index, resource in enumerate(record.anonymous_resources):
                capacity = int(resource["assignment_capacity"])
                if selected_by_resource[resource_index] > capacity:
                    violations.add(f"resource_capacity_exceeded:{line_number}")
                if selected_by_resource[resource_index] and not bool(resource["available"]):
                    violations.add(f"resource_capacity_unavailable_selected:{line_number}")
            constraint_checked_frame_count += 1
            candidate_edge_count += len(edges)
            selected_action_count += len(selected)
            split_candidate_counts[record.split] += len(edges)
            split_selected_counts[record.split] += len(selected)
            feature_value_count += int(features.size)
            target_record_count += len(record.anonymous_targets)
            resource_record_count += len(record.anonymous_resources)
            hard_reject_reasons.update(record.hard_reject_reason_counts)
            feedback_results[str(record.feedback_result)] += 1
            hysteresis_results[str(record.hysteresis_result)] += 1

    split_episode_counts = Counter(episode_splits.values())
    split_hash = None
    if seed_splits and episode_splits:
        split_hash = _dataset_split_hash(seed_splits, episode_splits)
    return _FrameAuditState(
        frame_count=frame_count,
        episode_frame_counts=episode_frame_counts,
        split_frame_counts=split_frame_counts,
        split_episode_counts=split_episode_counts,
        split_candidate_counts=split_candidate_counts,
        split_selected_counts=split_selected_counts,
        seed_splits=seed_splits,
        episode_splits=episode_splits,
        candidate_edge_count=candidate_edge_count,
        selected_action_count=selected_action_count,
        feature_value_count=feature_value_count,
        target_record_count=target_record_count,
        resource_record_count=resource_record_count,
        version_checked_frame_count=version_checked_frame_count,
        version_regression_count=version_regression_count,
        frame_sequence_violation_count=frame_sequence_violation_count,
        timestamp_sequence_violation_count=timestamp_sequence_violation_count,
        constraint_checked_frame_count=constraint_checked_frame_count,
        identity_field_occurrence_count=identity_occurrences,
        global_track_id_occurrence_count=global_track_occurrences,
        canonical_order_valid=canonical_order_valid,
        split_hash=split_hash,
        hard_reject_reason_counts=hard_reject_reasons,
        feedback_result_counts=feedback_results,
        hysteresis_result_counts=hysteresis_results,
    )


def _audit_manifest_inventory(
    manifest: LearningDatasetManifest,
    frames: _FrameAuditState,
    expected: AssignmentFullSampleAuditExpected,
    violations: _Violations,
) -> None:
    violations.require(
        manifest.schema_version == LEARNING_DATASET_SCHEMA_V2,
        "dataset_schema_version_mismatch",
    )
    violations.require(
        manifest.split_policy_version == LEARNING_DATASET_SPLIT_POLICY_V2,
        "dataset_split_policy_version_mismatch",
    )
    violations.require(
        manifest.frames_sha256 == expected.dataset_frames_sha256,
        "manifest_frames_sha256_mismatch",
    )
    violations.require(
        frames.split_hash == manifest.split_hash == expected.dataset_split_hash,
        "dataset_split_hash_mismatch",
    )
    violations.require(
        frames.frame_count == manifest.frame_count == expected.frame_count,
        "dataset_frame_count_mismatch",
    )
    violations.require(
        len(frames.episode_splits)
        == manifest.episode_count
        == expected.episode_count,
        "dataset_episode_count_mismatch",
    )
    violations.require(
        len(frames.seed_splits)
        == manifest.unique_seed_count
        == expected.training_seed_count,
        "dataset_seed_count_mismatch",
    )
    violations.require(
        _counter_dict(frames.split_frame_counts)
        == dict(manifest.split_frame_counts)
        == dict(expected.actual_frame_counts),
        "dataset_split_frame_counts_mismatch",
    )
    violations.require(
        _counter_dict(frames.split_episode_counts)
        == dict(manifest.split_episode_counts)
        == dict(expected.actual_episode_counts),
        "dataset_split_episode_counts_mismatch",
    )
    violations.require(
        frames.candidate_edge_count == expected.candidate_edge_count,
        "dataset_candidate_edge_count_mismatch",
    )
    violations.require(
        frames.selected_action_count == expected.selected_action_count,
        "dataset_selected_action_count_mismatch",
    )
    violations.require(
        frames.identity_field_occurrence_count == 0,
        "online_truth_or_identity_field_count_nonzero",
    )
    violations.require(
        frames.global_track_id_occurrence_count == 0,
        "global_track_id_illegal_field_count_nonzero",
    )


def _audit_episode_progress(
    path: Path,
    *,
    frame_state: _FrameAuditState,
    expected: AssignmentFullSampleAuditExpected,
    violations: _Violations,
) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            violations.add("episode_progress_header_missing")
            return _empty_progress()
        required = {
            "sequence",
            "episode_id",
            "scenario_version",
            "scenario",
            "seed",
            "scale",
            "d3_exported_frame_count",
            "d3_unavailable_reason_counts",
            "finite_state",
            "online_truth_use_count",
            "repository_dirty",
        }
        violations.require(
            required.issubset(reader.fieldnames),
            "episode_progress_required_fields_missing",
        )
        rows = [dict(row) for row in reader]
    violations.require(
        len(rows) == expected.episode_count,
        "episode_progress_row_count_mismatch",
    )
    progress_keys: set[tuple[str, int, str]] = set()
    exported_count = 0
    dirty_count = 0
    truth_count = 0
    finite_count = 0
    unavailable_reasons: Counter[str] = Counter()
    scenario_counts: Counter[str] = Counter()
    scale_counts: Counter[int] = Counter()
    for index, row in enumerate(rows):
        sequence = _parse_csv_integer(row.get("sequence"))
        seed = _parse_csv_integer(row.get("seed"))
        scale = _parse_csv_integer(row.get("scale"))
        frame_count = _parse_csv_integer(row.get("d3_exported_frame_count"))
        online_truth = _parse_csv_integer(row.get("online_truth_use_count"))
        if None in (sequence, seed, scale, frame_count, online_truth):
            violations.add(f"episode_progress_numeric_invalid:{index}")
            continue
        if sequence != index:
            violations.add(f"episode_progress_sequence_invalid:{index}")
        episode = str(row.get("episode_id", ""))
        scenario_version = str(row.get("scenario_version", ""))
        key = (scenario_version, seed, episode)
        if key in progress_keys:
            violations.add(f"episode_progress_duplicate_episode:{index}")
        progress_keys.add(key)
        exported_count += frame_count
        truth_count += online_truth
        is_dirty = row.get("repository_dirty") != "False"
        dirty_count += int(is_dirty)
        finite = row.get("finite_state") == "True"
        finite_count += int(finite)
        if not finite:
            violations.add(f"episode_progress_nonfinite_state:{index}")
        if online_truth != 0:
            violations.add(f"episode_progress_truth_use:{index}")
        if is_dirty:
            violations.add(f"episode_progress_dirty_source:{index}")
        if frame_state.episode_frame_counts.get(key, -1) != frame_count:
            violations.add(f"episode_progress_frame_binding_mismatch:{index}")
        raw_reasons = row.get("d3_unavailable_reason_counts", "{}")
        try:
            parsed = ast.literal_eval(raw_reasons)
        except (SyntaxError, ValueError):
            parsed = None
        if not isinstance(parsed, dict) or any(
            not isinstance(name, str)
            or _strict_integer(value) is None
            or int(value) < 0
            for name, value in (parsed or {}).items()
        ):
            violations.add(f"episode_progress_unavailable_reasons_invalid:{index}")
        else:
            unavailable_reasons.update(
                {str(name): int(value) for name, value in parsed.items()}
            )
        scenario_counts[str(row.get("scenario", ""))] += 1
        scale_counts[scale] += 1
    violations.require(
        progress_keys == set(frame_state.episode_splits),
        "episode_progress_dataset_episode_catalog_mismatch",
    )
    violations.require(
        exported_count == expected.frame_count == frame_state.frame_count,
        "episode_progress_exported_frame_count_mismatch",
    )
    violations.require(
        dirty_count == 0,
        "episode_progress_dirty_episode_count_nonzero",
    )
    violations.require(
        truth_count == 0,
        "episode_progress_online_truth_count_nonzero",
    )
    return {
        "episode_count": len(rows),
        "finite_episode_count": int(finite_count),
        "dirty_episode_count": int(dirty_count),
        "online_truth_use_count": int(truth_count),
        "exported_frame_count": int(exported_count),
        "unavailable_frame_reason_counts": dict(sorted(unavailable_reasons.items())),
        "unavailable_frame_count": int(sum(unavailable_reasons.values())),
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "scale_counts": {
            str(key): int(value) for key, value in sorted(scale_counts.items())
        },
    }


def _audit_generation_provenance(
    generation: Mapping[str, Any],
    batch: Mapping[str, Any],
    *,
    progress: Mapping[str, Any],
    expected: AssignmentFullSampleAuditExpected,
    manifest: LearningDatasetManifest | None,
    violations: _Violations,
) -> dict[str, Any]:
    violations.require(
        generation.get("formal") is True,
        "generation_summary_not_formal",
    )
    violations.require(
        generation.get("repository_dirty") is False,
        "generation_summary_dirty_source",
    )
    violations.require(
        generation.get("git_commit") == expected.source_git_commit,
        "generation_summary_git_commit_mismatch",
    )
    violations.require(
        generation.get("schedule_sha256") == expected.source_schedule_sha256,
        "generation_summary_schedule_sha256_mismatch",
    )
    violations.require(
        _strict_integer(generation.get("cell_count")) == expected.episode_count,
        "generation_summary_cell_count_mismatch",
    )
    violations.require(
        _strict_integer(generation.get("completed_episode_count"))
        == expected.episode_count,
        "generation_summary_episode_count_mismatch",
    )
    violations.require(
        _strict_integer(generation.get("generation_seed_count"))
        == expected.training_seed_count,
        "generation_summary_seed_count_mismatch",
    )
    violations.require(
        tuple(generation.get("reserved_evaluation_seeds", ()))
        == expected.reserved_evaluation_seeds,
        "generation_summary_reserved_seeds_mismatch",
    )
    export = generation.get("learning_export_summary")
    if not isinstance(export, MappingABC):
        export = {}
        violations.add("generation_learning_export_summary_missing")
    violations.require(
        _strict_integer(export.get("episode_count")) == expected.episode_count,
        "generation_export_episode_count_mismatch",
    )
    violations.require(
        _strict_integer(export.get("d3_frame_count")) == expected.frame_count,
        "generation_export_d3_frame_count_mismatch",
    )
    violations.require(
        export.get("d3_split_frame_counts") == dict(expected.actual_frame_counts),
        "generation_export_d3_split_counts_mismatch",
    )
    violations.require(
        _strict_integer(batch.get("episode_count")) == expected.episode_count,
        "batch_export_episode_count_mismatch",
    )
    violations.require(
        _strict_integer(batch.get("scenario_seed_group_count"))
        == expected.episode_count,
        "batch_export_scenario_seed_count_mismatch",
    )
    violations.require(
        _strict_integer(batch.get("d3_frame_count")) == expected.frame_count,
        "batch_export_d3_frame_count_mismatch",
    )
    violations.require(
        batch.get("d3_split_frame_counts") == dict(expected.actual_frame_counts),
        "batch_export_d3_split_counts_mismatch",
    )
    violations.require(
        batch.get("online_truth_policy") == "forbidden",
        "batch_export_online_truth_policy_mismatch",
    )
    if manifest is not None:
        violations.require(
            _strict_integer(progress.get("exported_frame_count"))
            == manifest.frame_count,
            "provenance_manifest_progress_frame_count_mismatch",
        )
    return {
        "source_git_commit": generation.get("git_commit"),
        "source_schedule_sha256": generation.get("schedule_sha256"),
        "repository_dirty": generation.get("repository_dirty"),
    }


def _coverage_payload(
    frames: _FrameAuditState,
    registries: Mapping[str, Any],
    expected: AssignmentFullSampleAuditExpected,
) -> dict[str, Any]:
    return {
        "episode_count": len(frames.episode_splits),
        "decision_sample_count": int(frames.frame_count),
        "frame_count": int(frames.frame_count),
        "canonical_episode_counts": dict(registries["canonical_counts"]),
        "actual_episode_counts": _counter_dict(frames.split_episode_counts),
        "actual_frame_counts": _counter_dict(frames.split_frame_counts),
        "candidate_edge_count": int(frames.candidate_edge_count),
        "edge_sample_count": int(frames.candidate_edge_count),
        "resource_target_action_label_count": int(frames.candidate_edge_count),
        "selected_resource_target_action_count": int(
            frames.selected_action_count
        ),
        "split_candidate_edge_counts": _counter_dict(
            frames.split_candidate_counts
        ),
        "split_action_label_counts": _counter_dict(
            frames.split_candidate_counts
        ),
        "split_selected_action_counts": _counter_dict(
            frames.split_selected_counts
        ),
        "anonymous_target_record_count": int(frames.target_record_count),
        "anonymous_resource_record_count": int(frames.resource_record_count),
        "feature_value_count": int(frames.feature_value_count),
        "training_seed_count": int(expected.training_seed_count),
        "canonical_split_unit": "numeric_seed_episode_identity",
        "actual_episode_split_unit": "scenario_scale_episode",
        "sample_split_unit": "decision_frame",
        "edge_label_split_unit": "candidate_resource_target_edge",
    }


def _bind(
    checks: dict[str, dict[str, Any]],
    violations: _Violations,
    name: str,
    expected: Any,
    actual: Any,
) -> None:
    passed = actual == expected
    checks[name] = {"expected": expected, "actual": actual, "passed": passed}
    violations.require(passed, f"binding_mismatch:{name}")


def _validate_source_and_output_paths(
    sources: Mapping[str, Path], outputs: Sequence[Path]
) -> None:
    for name, path in sources.items():
        if not path.is_file():
            raise AssignmentFullSampleAuditError(
                f"required source file is missing: {name}={path}"
            )
    source_paths = tuple(path.resolve() for path in sources.values())
    protected_roots = {
        sources["dataset_manifest"].parent.resolve(),
        sources["training_registry"].parent.resolve(),
    }
    for output in outputs:
        if output in source_paths or any(
            output == root or root in output.parents for root in protected_roots
        ):
            raise AssignmentFullSampleAuditError(
                "audit outputs must be outside protected source roots"
            )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_bytes(),
            parse_constant=lambda item: _reject_json_constant(item),
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise AssignmentFullSampleAuditError(
            f"cannot read required JSON object: {path}: {_stable_message(exc)}"
        ) from exc
    if not isinstance(value, dict):
        raise AssignmentFullSampleAuditError(
            f"required JSON source is not an object: {path}"
        )
    return value


def _integer_sequence(
    value: Any, name: str, violations: _Violations
) -> tuple[int, ...]:
    if not isinstance(value, list):
        violations.add(f"{name}_not_list")
        return ()
    result: list[int] = []
    for index, item in enumerate(value):
        parsed = _strict_integer(item)
        if parsed is None:
            violations.add(f"{name}_invalid_integer:{index}")
            continue
        result.append(parsed)
    return tuple(result)


def _strict_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        return None
    return int(value)


def _strict_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if isfinite(result) else None


def _parse_csv_integer(value: Any) -> int | None:
    text = str(value).strip()
    if not re.fullmatch(r"-?[0-9]+", text):
        return None
    return int(text)


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _dataset_split_hash(
    seed_splits: Mapping[int, str],
    episode_splits: Mapping[tuple[str, int, str], str],
) -> str:
    payload = {
        "dataset_schema_version": LEARNING_DATASET_SCHEMA_V2,
        "split_policy_version": LEARNING_DATASET_SPLIT_POLICY_V2,
        "seed_identity_scope": "numeric_seed_global_across_scenarios",
        "seed_assignments": [
            [int(seed), str(split)]
            for seed, split in sorted(seed_splits.items())
        ],
        "episode_assignments": [
            [scenario, int(seed), episode, split]
            for (scenario, seed, episode), split in sorted(
                episode_splits.items()
            )
        ],
    }
    return _sha256_json(payload)


def _counter_dict(value: Mapping[str, int]) -> dict[str, int]:
    return {split: int(value.get(split, 0)) for split in _EXPECTED_SPLITS}


def _count_violation_prefix(values: Sequence[str], prefix: str) -> int:
    return sum(str(value).startswith(prefix) for value in values)


def _empty_progress() -> dict[str, Any]:
    return {
        "episode_count": 0,
        "finite_episode_count": 0,
        "dirty_episode_count": 0,
        "online_truth_use_count": 0,
        "exported_frame_count": 0,
        "unavailable_frame_reason_counts": {},
        "unavailable_frame_count": 0,
        "scenario_counts": {},
        "scale_counts": {},
    }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return sha256(encoded).hexdigest()


def _stable_message(exc: BaseException) -> str:
    return " ".join(str(exc).split())[:240]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    coverage = report["coverage"]
    audit = report["audit"]
    admission = report["admission"]
    identity = report["version_and_identity_audit"]
    progress = report["generation_evidence"]
    lines = [
        "# D3 正式分配数据全样本准入审计",
        "",
        f"验证日期：{report['validation_date']}",
        "",
        "## 结论",
        "",
        (
            "正式数据的逐文件、逐 episode、逐决策帧结构审计状态为 "
            f"`{admission['assignment_full_sample_structural_audit']}`。"
            f"审计发现 {audit['violation_count']} 项结构或绑定违规。"
        ),
        (
            "当前总体状态为 `partial`。数据没有当前计划 owner、当前计划 version、"
            "真实运行应答、结果归因和同 seed 配对 shadow 记录，不能据此启动 PPO、"
            "开放 assist 或改变在线权限。规则代价和需求槽匈牙利继续作为默认路径。"
        ),
        "",
        "## 数据规模",
        "",
        "| 口径 | 训练 | 验证 | 测试 | 合计 |",
        "| --- | ---: | ---: | ---: | ---: |",
        _count_row("规范 episode 身份", coverage["canonical_episode_counts"]),
        _count_row("实际场景 episode", coverage["actual_episode_counts"]),
        _count_row("决策帧/样本", coverage["actual_frame_counts"]),
        _count_row("候选边/动作标签", coverage["split_candidate_edge_counts"]),
        _count_row("规则选中动作", coverage["split_selected_action_counts"]),
        "",
        (
            f"共 {coverage['episode_count']} 个实际 episode、"
            f"{coverage['decision_sample_count']} 个决策样本、"
            f"{coverage['candidate_edge_count']} 条候选边和"
            f" {coverage['selected_resource_target_action_count']} 条规则选中动作。"
            "60/20/20 是 100 个数值 seed 对应的规范 episode 身份切分；"
            "实际 episode 为 540/180/180，决策帧为 962/320/322。"
        ),
        "",
        "## 审计范围",
        "",
        "- 校验 manifest、frame 数据、训练 seed 注册表、共享切分注册表、生成摘要、episode 进度和批量导出摘要的 SHA256。",
        "- 逐帧校验 schema、有限数值、候选边和动作维度、索引、容量、需求槽、匿名 token、切分和前序版本单调性。",
        "- 逐 episode 校验导出帧计数、有限状态、脏工作树标记和在线真值使用计数。",
        "- 审计只读运行；正式源文件审计前后哈希一致。",
        "",
        "## 结果",
        "",
        f"- 在线真值使用：{progress['online_truth_use_count']}。",
        f"- 脏 episode：{progress['dirty_episode_count']}。",
        f"- 非法 global_track_id 字段：{identity['global_track_id_illegal_field_count']}。",
        f"- 前序计划版本回退：{identity['previous_plan_version_regression_count']}。",
        f"- 数据内容哈希：`{report['content_sha256']}`。",
        "",
        "正式生成过程中有部分规划 tick 因权威代次围栏或计划与成本帧不匹配而没有导出学习帧。"
        f"进度表记录 {progress['unavailable_frame_count']} 个未导出帧，原因分布为 "
        f"`{json.dumps(progress['unavailable_frame_reason_counts'], ensure_ascii=False, sort_keys=True)}`。"
        "审计按缺失原因保留该事实，没有用上一帧替代。",
        "",
        "## 证据边界",
        "",
        "当前数据只保存匿名 ordinal token 和 `previous_plan_version`。"
        "它可以证明样本内部索引、需求槽、容量和前序版本序列合法，不能证明当前计划 owner、"
        "当前计划 version 或运行时 stale 拒绝已经发生。离线 reward 分量来自规则教师，"
        "不能替代真实运行结果或可归因回报。",
        "",
        "后续准入仍需真实 runtime applied ACK、结果归因、因果或反事实 reward，"
        "以及同 seed 的规则路径与学习 shadow 非退化证据。上述证据闭合前，PPO、assist、"
        "在线权限和模型权重写入保持关闭。",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)


def _count_row(label: str, counts: Mapping[str, int]) -> str:
    values = [int(counts.get(split, 0)) for split in _EXPECTED_SPLITS]
    return f"| {label} | {values[0]} | {values[1]} | {values[2]} | {sum(values)} |"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the formal 900-episode D3 assignment corpus"
    )
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--training-registry", required=True, type=Path)
    parser.add_argument("--shared-registry", required=True, type=Path)
    parser.add_argument("--generation-summary", required=True, type=Path)
    parser.add_argument("--episode-progress", required=True, type=Path)
    parser.add_argument("--batch-export-summary", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-markdown", required=True, type=Path)
    parser.add_argument("--validation-date", default=FORMAL_VALIDATION_DATE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = audit_assignment_full_sample_dataset(
        args.dataset,
        training_seed_registry_path=args.training_registry,
        shared_seed_registry_path=args.shared_registry,
        generation_summary_path=args.generation_summary,
        episode_progress_path=args.episode_progress,
        batch_export_summary_path=args.batch_export_summary,
        output_json_path=args.output_json,
        output_markdown_path=args.output_markdown,
        validation_date=args.validation_date,
    )
    return 0 if report["audit"]["passed"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
