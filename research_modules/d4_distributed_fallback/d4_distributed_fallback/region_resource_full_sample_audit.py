"""Fail-closed full-sample admission audit for D4 regional datasets.

The audit reads the frozen 900-episode formal corpus and the independent
100-episode rule-teacher curriculum.  It verifies every episode artifact and
every regional sample without training a model, changing an authority owner,
or granting online assist.  Missing runtime evidence remains explicitly
unavailable.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .canonical_seed_split import (
    CanonicalRegionLearningDatasetView,
    audit_canonical_region_learning_split_view,
    load_canonical_region_learning_split_view,
)
from .region_resource import DeterministicResourceProjector
from .region_resource_curriculum import (
    RegionActionCoverageCurriculumConfig,
    audit_region_action_coverage_curriculum,
)
from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningAvailability,
    RegionLearningSplit,
    load_region_learning_dataset,
)


REGION_RESOURCE_FULL_SAMPLE_AUDIT_SCHEMA = (
    "d4-region-resource-full-sample-admission-audit-v1"
)
VALIDATION_DATE = "2026-07-21"
_SPLITS = ("train", "validation", "test")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")

_FORBIDDEN_ONLINE_KEYS = {
    "actor_id",
    "actor_name",
    "actor_truth_id",
    "evaluator_truth",
    "evaluator_truth_id",
    "global_track_id",
    "object_id",
    "object_name",
    "object_truth_id",
    "offline_truth",
    "segmentation_id",
    "target_id",
    "target_truth_id",
    "truth_id",
}


class RegionResourceFullSampleAuditError(RuntimeError):
    """Invalid invocation that must not overwrite an input artifact."""


@dataclass(frozen=True)
class RegionResourceFullSampleExpectedBindings:
    """Out-of-band immutable identities for the two frozen corpora."""

    formal_manifest_sha256: str
    formal_dataset_sha256: str
    supplemental_manifest_sha256: str
    supplemental_dataset_sha256: str
    supplemental_canonical_view_sha256: str
    supplemental_summary_file_sha256: str
    supplemental_summary_content_sha256: str
    training_registry_sha256: str
    shared_registry_sha256: str
    formal_source_git_commit: str
    supplemental_source_git_commit: str

    def __post_init__(self) -> None:
        for name in (
            "formal_manifest_sha256",
            "formal_dataset_sha256",
            "supplemental_manifest_sha256",
            "supplemental_dataset_sha256",
            "supplemental_canonical_view_sha256",
            "supplemental_summary_file_sha256",
            "supplemental_summary_content_sha256",
            "training_registry_sha256",
            "shared_registry_sha256",
        ):
            value = str(getattr(self, name)).strip().lower()
            if _SHA256_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{name} must be a lowercase SHA256")
            object.__setattr__(self, name, value)
        for name in ("formal_source_git_commit", "supplemental_source_git_commit"):
            value = str(getattr(self, name)).strip().lower()
            if _COMMIT_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{name} must be a full lowercase Git object ID")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, str]:
        return {
            name: str(getattr(self, name))
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class _CorpusRequirements:
    name: str
    classification: str
    episode_count: int
    frame_count: int
    sample_count: int
    action_count: int
    canonical_seed_counts: Mapping[str, int]
    canonical_episode_counts: Mapping[str, int]
    canonical_frame_counts: Mapping[str, int]
    canonical_action_counts: Mapping[str, int]
    required_action_counts: Mapping[str, int]


_FORMAL_REQUIREMENTS = _CorpusRequirements(
    name="formal",
    classification="formal_observation_corpus",
    episode_count=900,
    frame_count=1798,
    sample_count=1798,
    action_count=14384,
    canonical_seed_counts={"train": 60, "validation": 20, "test": 20},
    canonical_episode_counts={"train": 540, "validation": 180, "test": 180},
    canonical_frame_counts={"train": 1079, "validation": 359, "test": 360},
    canonical_action_counts={"train": 8632, "validation": 2872, "test": 2880},
    required_action_counts={
        "hold_true_count": 0,
        "request_replan_true_count": 0,
        "resource_quota_nonzero_count": 0,
        "transfer_count": 0,
        "transferred_resource_count": 0,
    },
)

_SUPPLEMENTAL_REQUIREMENTS = _CorpusRequirements(
    name="supplemental",
    classification="synthetic_rule_teacher_curriculum",
    episode_count=100,
    frame_count=300,
    sample_count=300,
    action_count=1200,
    canonical_seed_counts={"train": 60, "validation": 20, "test": 20},
    canonical_episode_counts={"train": 60, "validation": 20, "test": 20},
    canonical_frame_counts={"train": 180, "validation": 60, "test": 60},
    canonical_action_counts={"train": 720, "validation": 240, "test": 240},
    required_action_counts={
        "hold_true_count": 100,
        "request_replan_true_count": 200,
        "resource_quota_nonzero_count": 200,
        "transfer_count": 100,
        "transferred_resource_count": 300,
    },
)


def audit_region_resource_full_samples(
    formal_dataset_dir: str | Path,
    supplemental_dataset_dir: str | Path,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    supplemental_canonical_view_path: str | Path,
    supplemental_summary_path: str | Path,
    expected: RegionResourceFullSampleExpectedBindings,
    output_json_path: str | Path,
    output_markdown_path: str | Path,
    validation_date: str = VALIDATION_DATE,
) -> dict[str, Any]:
    """Audit both corpora and write a machine-readable and Chinese report."""

    if not isinstance(expected, RegionResourceFullSampleExpectedBindings):
        raise TypeError("expected must be RegionResourceFullSampleExpectedBindings")
    date = str(validation_date).strip()
    if not date:
        raise ValueError("validation_date must not be empty")

    formal_root = Path(formal_dataset_dir).resolve()
    supplemental_root = Path(supplemental_dataset_dir).resolve()
    training_registry = Path(training_seed_registry_path).resolve()
    shared_registry = Path(shared_seed_registry_path).resolve()
    supplemental_view_file = Path(supplemental_canonical_view_path).resolve()
    supplemental_summary_file = Path(supplemental_summary_path).resolve()
    output_json = Path(output_json_path).resolve()
    output_markdown = Path(output_markdown_path).resolve()
    source_files = (
        formal_root / "manifest.json",
        supplemental_root / "manifest.json",
        training_registry,
        shared_registry,
        supplemental_view_file,
        supplemental_summary_file,
    )
    _assert_output_paths_safe(
        (output_json, output_markdown),
        protected_roots=(formal_root, supplemental_root),
        source_files=source_files,
    )

    expected_bindings = expected.to_dict()
    common_violations: list[str] = []
    formal_violations: list[str] = []
    supplemental_violations: list[str] = []

    formal_manifest_raw = _read_json_or_none(
        formal_root / "manifest.json", formal_violations, "formal_manifest"
    )
    supplemental_manifest_raw = _read_json_or_none(
        supplemental_root / "manifest.json",
        supplemental_violations,
        "supplemental_manifest",
    )
    supplemental_view_raw = _read_json_or_none(
        supplemental_view_file,
        supplemental_violations,
        "supplemental_canonical_view",
    )
    supplemental_summary_raw = _read_json_or_none(
        supplemental_summary_file,
        supplemental_violations,
        "supplemental_summary",
    )

    formal_inventory_before = _audit_dataset_inventory(
        formal_root, formal_manifest_raw, formal_violations, "formal"
    )
    supplemental_inventory_before = _audit_dataset_inventory(
        supplemental_root,
        supplemental_manifest_raw,
        supplemental_violations,
        "supplemental",
    )

    actual_bindings: dict[str, Any] = {
        "formal_manifest_sha256": _sha256_or_none(
            formal_root / "manifest.json", formal_violations, "formal_manifest"
        ),
        "formal_dataset_sha256": _mapping_value(
            formal_manifest_raw, "dataset_sha256"
        ),
        "supplemental_manifest_sha256": _sha256_or_none(
            supplemental_root / "manifest.json",
            supplemental_violations,
            "supplemental_manifest",
        ),
        "supplemental_dataset_sha256": _mapping_value(
            supplemental_manifest_raw, "dataset_sha256"
        ),
        "supplemental_canonical_view_sha256": _sha256_or_none(
            supplemental_view_file,
            supplemental_violations,
            "supplemental_canonical_view",
        ),
        "supplemental_summary_file_sha256": _sha256_or_none(
            supplemental_summary_file,
            supplemental_violations,
            "supplemental_summary",
        ),
        "supplemental_summary_content_sha256": _declared_content_sha256(
            supplemental_summary_raw,
            supplemental_violations,
            "supplemental_summary",
        ),
        "training_registry_sha256": _sha256_or_none(
            training_registry, common_violations, "training_registry"
        ),
        "shared_registry_sha256": _sha256_or_none(
            shared_registry, common_violations, "shared_registry"
        ),
        "formal_source_git_commit": _unique_source_commit(
            formal_manifest_raw, formal_violations, "formal"
        ),
        "supplemental_source_git_commit": _unique_source_commit(
            supplemental_manifest_raw, supplemental_violations, "supplemental"
        ),
    }
    auxiliary_source_paths = {
        "training_seed_registry": training_registry,
        "shared_seed_registry": shared_registry,
        "supplemental_canonical_view": supplemental_view_file,
        "supplemental_summary": supplemental_summary_file,
    }
    auxiliary_hashes_before = {
        name: _sha256_or_none(path, common_violations, f"pre_audit_{name}")
        for name, path in auxiliary_source_paths.items()
    }
    binding_checks: dict[str, dict[str, Any]] = {}
    for name, expected_value in expected_bindings.items():
        actual_value = actual_bindings.get(name)
        passed = actual_value == expected_value
        binding_checks[name] = {
            "expected": expected_value,
            "actual": actual_value,
            "passed": passed,
        }
        if not passed:
            target = (
                formal_violations
                if name.startswith("formal_")
                else supplemental_violations
                if name.startswith("supplemental_")
                else common_violations
            )
            target.append(
                f"binding_mismatch:{name}:expected={expected_value}:actual={actual_value}"
            )

    formal_dataset = _load_dataset_or_none(
        formal_root, formal_violations, "formal"
    )
    supplemental_dataset = _load_dataset_or_none(
        supplemental_root, supplemental_violations, "supplemental"
    )
    formal_view = _load_canonical_view_or_none(
        formal_dataset,
        training_registry=training_registry,
        shared_registry=shared_registry,
        violations=formal_violations,
        label="formal",
    )
    supplemental_view = _load_canonical_view_or_none(
        supplemental_dataset,
        training_registry=training_registry,
        shared_registry=shared_registry,
        violations=supplemental_violations,
        label="supplemental",
    )

    formal_audit = _empty_corpus_audit(_FORMAL_REQUIREMENTS)
    if formal_dataset is not None and formal_view is not None:
        formal_audit, corpus_violations = _audit_loaded_corpus(
            formal_dataset,
            formal_view,
            requirements=_FORMAL_REQUIREMENTS,
        )
        formal_violations.extend(corpus_violations)

    supplemental_audit = _empty_corpus_audit(_SUPPLEMENTAL_REQUIREMENTS)
    computed_supplemental_canonical: Mapping[str, Any] | None = None
    if supplemental_dataset is not None and supplemental_view is not None:
        supplemental_audit, corpus_violations = _audit_loaded_corpus(
            supplemental_dataset,
            supplemental_view,
            requirements=_SUPPLEMENTAL_REQUIREMENTS,
        )
        supplemental_violations.extend(corpus_violations)
        computed_supplemental_canonical = (
            audit_canonical_region_learning_split_view(supplemental_view)
        )
        if _plain_json(computed_supplemental_canonical) != _plain_json(
            supplemental_view_raw
        ):
            supplemental_violations.append(
                "supplemental_canonical_view_recompute_mismatch"
            )
        _recompute_supplemental_summary(
            supplemental_dataset,
            supplemental_view,
            supplemental_summary_raw,
            training_registry_sha256=actual_bindings.get(
                "training_registry_sha256"
            ),
            shared_registry_sha256=actual_bindings.get("shared_registry_sha256"),
            violations=supplemental_violations,
        )

    formal_inventory_after = _audit_dataset_inventory(
        formal_root, formal_manifest_raw, formal_violations, "formal_post_audit"
    )
    supplemental_inventory_after = _audit_dataset_inventory(
        supplemental_root,
        supplemental_manifest_raw,
        supplemental_violations,
        "supplemental_post_audit",
    )
    formal_sources_unchanged = (
        formal_inventory_before.get("tree_sha256")
        == formal_inventory_after.get("tree_sha256")
    )
    supplemental_sources_unchanged = (
        supplemental_inventory_before.get("tree_sha256")
        == supplemental_inventory_after.get("tree_sha256")
    )
    auxiliary_hashes_after = {
        name: _sha256_or_none(path, common_violations, f"post_audit_{name}")
        for name, path in auxiliary_source_paths.items()
    }
    auxiliary_sources_unchanged = auxiliary_hashes_before == auxiliary_hashes_after
    if not formal_sources_unchanged:
        formal_violations.append("formal_source_artifact_changed_during_audit")
    if not supplemental_sources_unchanged:
        supplemental_violations.append(
            "supplemental_source_artifact_changed_during_audit"
        )
    if not auxiliary_sources_unchanged:
        common_violations.append("auxiliary_source_artifact_changed_during_audit")

    formal_violations = sorted(set(formal_violations))
    supplemental_violations = sorted(set(supplemental_violations))
    common_violations = sorted(set(common_violations))
    formal_complete = not formal_violations and not common_violations
    supplemental_complete = not supplemental_violations and not common_violations
    combined_complete = formal_complete and supplemental_complete
    all_violations = sorted(
        set(common_violations + formal_violations + supplemental_violations)
    )

    report: dict[str, Any] = {
        "schema": REGION_RESOURCE_FULL_SAMPLE_AUDIT_SCHEMA,
        "validation_date": date,
        "audit_mode": "read_only_fail_closed",
        "purpose": "d4_formal_and_supplemental_full_sample_admission",
        "source_paths": {
            "formal_dataset": _display_path(formal_root),
            "supplemental_dataset": _display_path(supplemental_root),
            "training_seed_registry": _display_path(training_registry),
            "shared_seed_registry": _display_path(shared_registry),
            "supplemental_canonical_view": _display_path(
                supplemental_view_file
            ),
            "supplemental_summary": _display_path(supplemental_summary_file),
        },
        "expected_bindings": expected_bindings,
        "actual_bindings": actual_bindings,
        "binding_checks": binding_checks,
        "artifact_integrity": {
            "formal": {
                **formal_inventory_after,
                "source_unchanged_during_audit": formal_sources_unchanged,
            },
            "supplemental": {
                **supplemental_inventory_after,
                "source_unchanged_during_audit": supplemental_sources_unchanged,
            },
            "auxiliary_source_hashes_before": auxiliary_hashes_before,
            "auxiliary_source_hashes_after": auxiliary_hashes_after,
            "auxiliary_sources_unchanged_during_audit": (
                auxiliary_sources_unchanged
            ),
            "formal_900_episode_dataset_modified": False,
        },
        "formal_corpus": formal_audit,
        "supplemental_curriculum": {
            **supplemental_audit,
            "synthetic_evidence_boundary": {
                "structure_and_schema_evidence": True,
                "finite_value_evidence": True,
                "action_coverage_evidence": True,
                "deterministic_safety_constraint_evidence": True,
                "real_runtime_coalition_member_ack_evidence": False,
                "observed_outcome_evidence": False,
                "attributable_reward_evidence": False,
                "center_or_secondary_takeover_effect_evidence": False,
                "network_partition_effect_evidence": False,
            },
            "computed_canonical_view": computed_supplemental_canonical,
        },
        "evidence_availability": {
            "explicit_pre_projection_action_mask": {
                "status": "pending",
                "availability": "unavailable",
                "reason": "dataset_records_only_post_projection_recommendations",
            },
            "stale_plan_epoch_lease_rejection_samples": {
                "status": "pending",
                "availability": "unavailable",
                "reason": "no_explicit_rejected_candidate_or_runtime_ack_record",
            },
            "real_runtime_coalition_member_ack": {
                "status": "pending",
                "availability": "unavailable",
            },
            "observed_outcome": {
                "status": "pending",
                "availability": "unavailable",
            },
            "attributable_reward": {
                "status": "pending",
                "availability": "unavailable",
            },
            "same_seed_paired_shadow": {
                "status": "pending",
                "availability": "unavailable",
            },
        },
        "status": {
            "formal_full_sample": "complete" if formal_complete else "pending",
            "supplemental_full_sample": (
                "complete" if supplemental_complete else "pending"
            ),
            "combined_full_sample": "complete" if combined_complete else "partial",
        },
        "admission": {
            "behavior_cloning_full_sample_audit": (
                "complete" if combined_complete else "pending"
            ),
            "d6_cross_module_learning_admission": "pending_external_audit",
            "ppo_allowed": False,
            "assist_allowed": False,
            "online_authority_allowed": False,
            "rule_fallback_required": True,
            "model_training_performed": False,
            "weights_written": False,
            "deterministic_region_rules_are_only_executable_path": True,
            "lease_epoch_and_safety_projection_remain_mandatory": True,
        },
        "remaining_gates": [
            "d6_explicit_path_and_out_of_band_sha256_reaudit",
            "real_runtime_coalition_member_ack_and_outcome_attribution",
            "versioned_reward_causal_and_counterfactual_labels",
            "same_seed_paired_shadow_non_degradation",
            "ppo_assist_and_authority_remain_closed",
        ],
        "audit": {
            "passed": combined_complete,
            "fail_closed": True,
            "violation_count": len(all_violations),
            "common_violations": common_violations,
            "formal_violations": formal_violations,
            "supplemental_violations": supplemental_violations,
            "violations": all_violations,
        },
    }
    report["content_sha256"] = _sha256_json(report)
    _write_json_atomic(output_json, report)
    output_json_sha256 = _sha256_file(output_json)
    _write_text_atomic(
        output_markdown,
        _render_markdown(
            report,
            output_json_path=output_json,
            output_json_sha256=output_json_sha256,
        ),
    )
    return report


def _audit_loaded_corpus(
    dataset: LoadedRegionLearningDataset,
    canonical_view: CanonicalRegionLearningDatasetView,
    *,
    requirements: _CorpusRequirements,
) -> tuple[dict[str, Any], list[str]]:
    canonical_view.assert_source(dataset)
    violations: list[str] = []
    projector = DeterministicResourceProjector()
    canonical = audit_canonical_region_learning_split_view(canonical_view)
    canonical_violations = _canonical_contract_violations(
        canonical, requirements=requirements
    )
    violations.extend(canonical_violations)

    split_inventory = {split: Counter() for split in _SPLITS}
    totals: Counter[str] = Counter()
    source_commits: Counter[str] = Counter()
    source_config_sha256: Counter[str] = Counter()
    source_schema_counts: Counter[str] = Counter()
    frame_schema_counts: Counter[str] = Counter()
    snapshot_schema_counts: Counter[str] = Counter()
    feature_schema_counts: Counter[str] = Counter()
    recommendation_schema_counts: Counter[str] = Counter()
    target_kind_counts: Counter[str] = Counter()
    projection_rejection_reason_counts: Counter[str] = Counter()
    truth_paths: list[str] = []
    nonfinite_paths: list[str] = []
    safety_violation_samples: list[str] = []
    version_violation_samples: list[str] = []
    reward_unavailable_reasons: Counter[str] = Counter()
    observed_seed_values: set[int] = set()
    dirty_episode_count = 0
    version_monotonic_episode_count = 0
    all_numeric_finite_sample_count = 0

    for episode in canonical_view.episode_records:
        split = episode.split.value
        split_inventory[split]["episode_count"] += 1
        totals["episode_count"] += 1
        observed_seed_values.add(int(episode.source.seed))
        source_commits[episode.source.git_commit] += 1
        source_config_sha256[episode.source.config_sha256] += 1
        source_schema_counts[episode.source.schema] += 1
        dirty_episode_count += int(episode.source.git_dirty)
        truth_paths.extend(
            _forbidden_key_paths(
                episode.source.to_dict(),
                path=f"episode:{episode.source.episode_id}:source",
            )
        )
        previous_regions: dict[str, Mapping[str, Any]] = {}
        episode_version_valid = True
        for frame in episode.frames:
            prefix = f"episode:{episode.source.episode_id}:frame:{frame.frame_index}"
            frame_payload = frame.to_dict()
            frame_schema_counts[frame.schema] += 1
            snapshot_schema_counts[frame.snapshot.schema] += 1
            feature_schema_counts[frame.snapshot.feature_schema] += 1
            totals["frame_count"] += 1
            totals["sample_count"] += 1
            split_inventory[split]["frame_count"] += 1
            split_inventory[split]["sample_count"] += 1
            frame_nonfinite = _nonfinite_number_paths(frame_payload, path=prefix)
            nonfinite_paths.extend(frame_nonfinite)
            if not frame_nonfinite:
                all_numeric_finite_sample_count += 1
            truth_paths.extend(_forbidden_key_paths(frame_payload, path=prefix))

            frame_version_violations = _version_monotonicity_violations(
                frame_payload["snapshot"],
                previous_regions=previous_regions,
                path=prefix,
            )
            if frame_version_violations:
                episode_version_valid = False
                version_violation_samples.extend(frame_version_violations)

            target = frame.target
            if target.availability != RegionLearningAvailability.AVAILABLE:
                totals["target_unavailable_count"] += 1
                violations.append(f"{prefix}:target_unavailable")
                continue
            totals["target_available_count"] += 1
            if target.kind is not None:
                target_kind_counts[target.kind.value] += 1
            recommendation = target.recommendation
            if recommendation is None:
                violations.append(f"{prefix}:target_recommendation_missing")
                continue
            recommendation_schema_counts[recommendation.schema] += 1
            action_count = len(recommendation.actions)
            totals["action_count"] += action_count
            split_inventory[split]["action_count"] += action_count
            totals["hold_true_count"] += sum(
                int(action.hold) for action in recommendation.actions
            )
            totals["request_replan_true_count"] += sum(
                int(action.request_replan) for action in recommendation.actions
            )
            totals["resource_quota_positive_count"] += sum(
                action.resource_quota_delta > 0 for action in recommendation.actions
            )
            totals["resource_quota_negative_count"] += sum(
                action.resource_quota_delta < 0 for action in recommendation.actions
            )
            totals["resource_quota_zero_count"] += sum(
                action.resource_quota_delta == 0 for action in recommendation.actions
            )
            totals["resource_quota_nonzero_count"] += sum(
                action.resource_quota_delta != 0 for action in recommendation.actions
            )
            totals["transfer_count"] += len(recommendation.transfers)
            totals["transferred_resource_count"] += sum(
                transfer.resource_count for transfer in recommendation.transfers
            )
            totals["projected_recommendation_count"] += int(
                recommendation.projected
            )
            for reason in recommendation.projection_rejections:
                projection_rejection_reason_counts[str(reason)] += 1

            raw_safety = _raw_recommendation_contract_violations(
                frame_payload["snapshot"],
                recommendation.to_dict(),
                timestamp_s=float(frame.timestamp_s),
                path=prefix,
            )
            try:
                advisory = projector.build_advisory_contract(
                    frame.snapshot, recommendation
                )
                projector_rejections = [
                    f"{prefix}:projector:{reason}"
                    for reason in advisory.publication_rejections
                ]
            except Exception as exc:
                projector_rejections = [
                    f"{prefix}:projector_failed:{type(exc).__name__}:{exc}"
                ]
            sample_safety_violations = raw_safety + projector_rejections
            if sample_safety_violations:
                safety_violation_samples.extend(sample_safety_violations)
            else:
                totals["safety_valid_sample_count"] += 1

            if frame.reward.availability == RegionLearningAvailability.AVAILABLE:
                totals["reward_available_count"] += 1
            else:
                totals["reward_unavailable_count"] += 1
                reward_unavailable_reasons[
                    str(frame.reward.unavailable_reason)
                ] += 1

        if episode_version_valid:
            version_monotonic_episode_count += 1

    totals["dirty_episode_count"] = dirty_episode_count
    totals["finite_feature_sample_count"] = all_numeric_finite_sample_count
    totals["nonfinite_feature_sample_count"] = (
        totals["sample_count"] - all_numeric_finite_sample_count
    )
    totals["truth_identifier_path_count"] = len(truth_paths)
    totals["safety_invalid_sample_count"] = (
        totals["sample_count"] - totals["safety_valid_sample_count"]
    )

    expected_counts = {
        "episode_count": requirements.episode_count,
        "frame_count": requirements.frame_count,
        "sample_count": requirements.sample_count,
        "action_count": requirements.action_count,
        **dict(requirements.required_action_counts),
    }
    for name, expected_value in expected_counts.items():
        actual_value = int(totals.get(name, 0))
        if actual_value != int(expected_value):
            violations.append(
                f"{requirements.name}_{name}_mismatch:"
                f"expected={expected_value}:actual={actual_value}"
            )
    if dirty_episode_count:
        violations.append(f"{requirements.name}_dirty_episode_present")
    if nonfinite_paths:
        violations.append(f"{requirements.name}_nonfinite_numeric_feature")
    if truth_paths:
        violations.append(f"{requirements.name}_online_truth_identifier_present")
    if safety_violation_samples:
        violations.append(f"{requirements.name}_safety_contract_failed")
    if version_violation_samples:
        violations.append(f"{requirements.name}_version_or_lease_contract_failed")
    if version_monotonic_episode_count != requirements.episode_count:
        violations.append(
            f"{requirements.name}_version_monotonic_episode_count_mismatch"
        )
    if totals["reward_available_count"]:
        violations.append(f"{requirements.name}_reward_unexpectedly_available")
    if totals["projected_recommendation_count"] != requirements.sample_count:
        violations.append(
            f"{requirements.name}_post_projection_recommendation_count_mismatch"
        )

    reserved_overlap = sorted(
        observed_seed_values
        & set(canonical_view.binding.reserved_evaluation_seeds)
    )
    if reserved_overlap:
        violations.append(f"{requirements.name}_reserved_seed_leakage")

    split_payload = {
        split: {
            "episode_count": int(split_inventory[split]["episode_count"]),
            "frame_count": int(split_inventory[split]["frame_count"]),
            "sample_count": int(split_inventory[split]["sample_count"]),
            "action_count": int(split_inventory[split]["action_count"]),
        }
        for split in _SPLITS
    }
    for split in _SPLITS:
        expected_split = {
            "episode_count": requirements.canonical_episode_counts[split],
            "frame_count": requirements.canonical_frame_counts[split],
            "sample_count": requirements.canonical_frame_counts[split],
            "action_count": requirements.canonical_action_counts[split],
        }
        if split_payload[split] != expected_split:
            violations.append(
                f"{requirements.name}_canonical_{split}_inventory_mismatch:"
                f"expected={expected_split}:actual={split_payload[split]}"
            )

    audit = {
        "classification": requirements.classification,
        "schema_and_source": {
            "dataset_schema": dataset.manifest.schema,
            "source_schema_counts": _ordered_counter(source_schema_counts),
            "frame_schema_counts": _ordered_counter(frame_schema_counts),
            "snapshot_schema_counts": _ordered_counter(snapshot_schema_counts),
            "feature_schema_counts": _ordered_counter(feature_schema_counts),
            "recommendation_schema_counts": _ordered_counter(
                recommendation_schema_counts
            ),
            "source_git_commit_episode_counts": _ordered_counter(source_commits),
            "source_config_sha256_episode_counts": _ordered_counter(
                source_config_sha256
            ),
            "dirty_episode_count": dirty_episode_count,
        },
        "inventory": {
            "episode_count": int(totals["episode_count"]),
            "frame_count": int(totals["frame_count"]),
            "sample_count": int(totals["sample_count"]),
            "sample_definition": "one_region_resource_frame",
            "action_count": int(totals["action_count"]),
            "canonical_split": split_payload,
        },
        "canonical": canonical,
        "numeric_feature_audit": {
            "finite_sample_count": all_numeric_finite_sample_count,
            "nonfinite_sample_count": int(
                totals["nonfinite_feature_sample_count"]
            ),
            "nonfinite_path_count": len(nonfinite_paths),
            "nonfinite_path_examples": nonfinite_paths[:50],
        },
        "action_coverage": {
            "target_kind_counts": _ordered_counter(target_kind_counts),
            "rule_teacher_label_count": int(target_kind_counts.get("rule", 0)),
            "rule_teacher_label_is_runtime_applied_ack": False,
            "action_count": int(totals["action_count"]),
            "hold_true_count": int(totals["hold_true_count"]),
            "request_replan_true_count": int(
                totals["request_replan_true_count"]
            ),
            "resource_quota_positive_count": int(
                totals["resource_quota_positive_count"]
            ),
            "resource_quota_negative_count": int(
                totals["resource_quota_negative_count"]
            ),
            "resource_quota_zero_count": int(
                totals["resource_quota_zero_count"]
            ),
            "resource_quota_nonzero_count": int(
                totals["resource_quota_nonzero_count"]
            ),
            "transfer_count": int(totals["transfer_count"]),
            "transferred_resource_count": int(
                totals["transferred_resource_count"]
            ),
        },
        "safety_and_generation_audit": {
            "post_projection_recommendation_count": int(
                totals["projected_recommendation_count"]
            ),
            "post_projection_recommendation_is_runtime_applied_ack": False,
            "safety_valid_sample_count": int(
                totals["safety_valid_sample_count"]
            ),
            "safety_invalid_sample_count": int(
                totals["safety_invalid_sample_count"]
            ),
            "resource_quota_conservation_checked": True,
            "cross_region_transfer_legality_checked": True,
            "owner_plan_epoch_lease_binding_checked": True,
            "owner_epoch_version_lease_monotonic_episode_count": (
                version_monotonic_episode_count
            ),
            "projection_rejection_reason_counts": _ordered_counter(
                projection_rejection_reason_counts
            ),
            "safety_violation_examples": safety_violation_samples[:50],
            "version_violation_examples": version_violation_samples[:50],
            "explicit_pre_projection_action_mask_available": False,
            "explicit_stale_plan_or_lease_rejection_record_available": False,
        },
        "truth_seed_and_dirty_audit": {
            "online_truth_identifier_count": len(truth_paths),
            "truth_identifier_path_examples": truth_paths[:50],
            "numeric_seed_count": len(observed_seed_values),
            "numeric_seed_atomic": canonical["canonical_split"][
                "numeric_seed_atomic"
            ],
            "reserved_evaluation_seed_overlap": reserved_overlap,
            "dirty_episode_count": dirty_episode_count,
        },
        "reward_outcome_and_runtime_ack": {
            "reward_available_count": int(totals["reward_available_count"]),
            "reward_unavailable_count": int(
                totals["reward_unavailable_count"]
            ),
            "reward_unavailable_reason_counts": _ordered_counter(
                reward_unavailable_reasons
            ),
            "observed_outcome_available": False,
            "real_runtime_coalition_member_ack_available": False,
            "paired_shadow_available": False,
        },
    }
    return audit, sorted(set(violations))


def _raw_recommendation_contract_violations(
    snapshot: Mapping[str, Any],
    recommendation: Mapping[str, Any],
    *,
    timestamp_s: float,
    path: str,
) -> list[str]:
    """Check raw post-projection action safety without trusting dataclass load."""

    violations: list[str] = []
    if recommendation.get("projected") is not True:
        violations.append(f"{path}:recommendation_not_projected")
    for name in (
        "snapshot_id",
        "scenario_id",
        "scenario_version",
        "seed",
        "authority_digest",
    ):
        if recommendation.get(name) != snapshot.get(name):
            violations.append(f"{path}:recommendation_{name}_mismatch")
    regions = {
        str(item.get("region_id")): item
        for item in snapshot.get("regions", ())
        if isinstance(item, Mapping)
    }
    actions = [
        item for item in recommendation.get("actions", ()) if isinstance(item, Mapping)
    ]
    action_by_region = {str(item.get("region_id")): item for item in actions}
    if len(action_by_region) != len(actions) or set(action_by_region) != set(regions):
        violations.append(f"{path}:region_action_inventory_mismatch")
    quota_sum = sum(_safe_int(item.get("resource_quota_delta")) for item in actions)
    if quota_sum != 0:
        violations.append(f"{path}:resource_quota_not_conserved")

    for region_id, region in regions.items():
        action = action_by_region.get(region_id)
        if action is None:
            continue
        expected_fields = {
            "expected_owner_id": region.get("current_owner_id"),
            "expected_owner_layer": region.get("current_owner_layer"),
            "expected_plan_id": region.get("plan_id"),
            "expected_plan_version": region.get("plan_version"),
            "expected_epoch": region.get("epoch"),
            "expected_lease_expires_at_s": region.get("lease_expires_at_s"),
        }
        for field, expected in expected_fields.items():
            if action.get(field) != expected:
                violations.append(f"{path}:{region_id}:{field}_stale_or_mismatch")
        if (
            region.get("owner_active") is True
            and region.get("current_owner_layer") != "hold"
            and not _strictly_greater(region.get("lease_expires_at_s"), timestamp_s)
        ):
            violations.append(f"{path}:{region_id}:owner_lease_expired")

    edges = {
        str(item.get("edge_id")): item
        for item in snapshot.get("edges", ())
        if isinstance(item, Mapping)
    }
    net_transfer = {region_id: 0 for region_id in regions}
    seen_transfers: set[tuple[str, str, str]] = set()
    for transfer in recommendation.get("transfers", ()):
        if not isinstance(transfer, Mapping):
            violations.append(f"{path}:transfer_record_invalid")
            continue
        source_id = str(transfer.get("source_region_id"))
        target_id = str(transfer.get("target_region_id"))
        edge_id = str(transfer.get("edge_id"))
        transfer_key = (source_id, target_id, edge_id)
        if transfer_key in seen_transfers:
            violations.append(f"{path}:duplicate_transfer:{transfer_key}")
        seen_transfers.add(transfer_key)
        edge = edges.get(edge_id)
        count = _safe_int(transfer.get("resource_count"))
        if edge is None:
            violations.append(f"{path}:unknown_transfer_edge:{edge_id}")
            continue
        endpoints_match = (
            source_id == edge.get("source_region_id")
            and target_id == edge.get("target_region_id")
        ) or (
            edge.get("bidirectional") is True
            and source_id == edge.get("target_region_id")
            and target_id == edge.get("source_region_id")
        )
        if not endpoints_match:
            violations.append(f"{path}:illegal_cross_region_transfer:{edge_id}")
        if not (
            edge.get("communication_available") is True
            and edge.get("maneuver_available") is True
            and edge.get("partitioned") is False
            and _strictly_greater(edge.get("bandwidth_mbps"), 0.0)
            and count > 0
            and count <= _safe_int(edge.get("transferable_resources"))
        ):
            violations.append(f"{path}:transfer_edge_or_capacity_unavailable:{edge_id}")
        if source_id in net_transfer and target_id in net_transfer:
            net_transfer[source_id] -= count
            net_transfer[target_id] += count
    for region_id, expected_delta in net_transfer.items():
        action = action_by_region.get(region_id)
        if action is not None and _safe_int(
            action.get("resource_quota_delta")
        ) != expected_delta:
            violations.append(f"{path}:{region_id}:quota_transfer_delta_mismatch")
    return violations


def _version_monotonicity_violations(
    snapshot: Mapping[str, Any],
    *,
    previous_regions: dict[str, Mapping[str, Any]],
    path: str,
) -> list[str]:
    violations: list[str] = []
    for raw_region in snapshot.get("regions", ()):
        if not isinstance(raw_region, Mapping):
            violations.append(f"{path}:region_record_invalid")
            continue
        region = dict(raw_region)
        region_id = str(region.get("region_id"))
        previous = previous_regions.get(region_id)
        if previous is not None:
            previous_version = _safe_int(previous.get("plan_version"))
            previous_epoch = _safe_int(previous.get("epoch"))
            current_version = _safe_int(region.get("plan_version"))
            current_epoch = _safe_int(region.get("epoch"))
            if current_version < previous_version:
                violations.append(f"{path}:{region_id}:plan_version_regressed")
            if current_epoch < previous_epoch:
                violations.append(f"{path}:{region_id}:epoch_regressed")
            if _safe_float(region.get("lease_expires_at_s")) < _safe_float(
                previous.get("lease_expires_at_s")
            ):
                violations.append(f"{path}:{region_id}:lease_expiry_regressed")
            previous_identity = (
                previous.get("current_owner_id"),
                previous.get("current_owner_layer"),
                previous.get("plan_id"),
            )
            current_identity = (
                region.get("current_owner_id"),
                region.get("current_owner_layer"),
                region.get("plan_id"),
            )
            if current_identity != previous_identity and not (
                current_version > previous_version and current_epoch > previous_epoch
            ):
                violations.append(
                    f"{path}:{region_id}:owner_or_plan_changed_without_generation_bump"
                )
        previous_regions[region_id] = region
    return violations


def _canonical_contract_violations(
    canonical: Mapping[str, Any],
    *,
    requirements: _CorpusRequirements,
) -> list[str]:
    violations: list[str] = []
    split = canonical.get("canonical_split")
    if not isinstance(split, Mapping):
        return [f"{requirements.name}_canonical_split_missing"]
    checks = {
        "seed_counts": dict(requirements.canonical_seed_counts),
        "episode_counts": dict(requirements.canonical_episode_counts),
        "frame_counts": dict(requirements.canonical_frame_counts),
    }
    for name, expected in checks.items():
        if split.get(name) != expected:
            violations.append(
                f"{requirements.name}_canonical_{name}_mismatch:"
                f"expected={expected}:actual={split.get(name)}"
            )
    if split.get("numeric_seed_atomic") is not True:
        violations.append(f"{requirements.name}_canonical_seed_not_atomic")
    if split.get("reserved_seed_present") is not False:
        violations.append(f"{requirements.name}_canonical_reserved_seed_present")
    if split.get("reserved_seed_count") != 20:
        violations.append(f"{requirements.name}_reserved_seed_count_mismatch")
    return violations


def _audit_dataset_inventory(
    root: Path,
    manifest: Mapping[str, Any] | None,
    violations: list[str],
    label: str,
) -> dict[str, Any]:
    expected_hashes: dict[str, str] = {}
    if isinstance(manifest, Mapping):
        for index, item in enumerate(manifest.get("episodes", ())):
            if not isinstance(item, Mapping):
                violations.append(f"{label}_manifest_episode_{index}_invalid")
                continue
            relative = str(item.get("relative_path", ""))
            expected = str(item.get("episode_sha256", ""))
            if (
                not relative
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or _SHA256_PATTERN.fullmatch(expected) is None
                or relative in expected_hashes
            ):
                violations.append(f"{label}_manifest_episode_{index}_binding_invalid")
                continue
            expected_hashes[relative] = expected
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    } if root.is_dir() else set()
    expected_files = {"manifest.json", *expected_hashes}
    exact_inventory = actual_files == expected_files
    if not exact_inventory:
        violations.append(
            f"{label}_artifact_inventory_mismatch:"
            f"missing={sorted(expected_files - actual_files)}:"
            f"extra={sorted(actual_files - expected_files)}"
        )
    verified_count = 0
    mismatch_count = 0
    file_hashes: dict[str, str] = {}
    for relative in sorted(actual_files):
        try:
            actual = _sha256_file(root / relative)
            file_hashes[relative] = actual
        except OSError as exc:
            violations.append(
                f"{label}_artifact_hash_failed:{relative}:{type(exc).__name__}"
            )
            continue
        if relative in expected_hashes:
            if actual == expected_hashes[relative]:
                verified_count += 1
            else:
                mismatch_count += 1
                violations.append(
                    f"{label}_episode_sha256_mismatch:{relative}:"
                    f"expected={expected_hashes[relative]}:actual={actual}"
                )
    return {
        "dataset_file_count": len(actual_files),
        "manifest_episode_file_count": len(expected_hashes),
        "episode_sha256_verified_count": verified_count,
        "episode_sha256_mismatch_count": mismatch_count,
        "artifact_inventory_exact": exact_inventory,
        "tree_sha256": _sha256_json(file_hashes),
    }


def _recompute_supplemental_summary(
    dataset: LoadedRegionLearningDataset,
    canonical_view: CanonicalRegionLearningDatasetView,
    summary: Mapping[str, Any] | None,
    *,
    training_registry_sha256: Any,
    shared_registry_sha256: Any,
    violations: list[str],
) -> None:
    if not isinstance(summary, Mapping):
        return
    config_payload = summary.get("config")
    source_binding = summary.get("source_binding")
    if not isinstance(config_payload, Mapping) or not isinstance(
        source_binding, Mapping
    ):
        violations.append("supplemental_summary_config_or_binding_missing")
        return
    try:
        config = RegionActionCoverageCurriculumConfig(
            region_count=int(config_payload["region_count"]),
            resource_count=int(config_payload["resource_count"]),
            frame_interval_s=float(config_payload["frame_interval_s"]),
            scenario_id=str(config_payload["scenario_id"]),
            scenario_version=str(config_payload["scenario_version"]),
        )
        recomputed = audit_region_action_coverage_curriculum(
            dataset,
            canonical_view=canonical_view,
            config=config,
            created_at_utc=str(summary["created_at_utc"]),
            source_registry_sha256=str(training_registry_sha256),
            shared_registry_sha256=str(shared_registry_sha256),
            config_sha256=str(source_binding["config_sha256"]),
        )
    except Exception as exc:
        violations.append(
            f"supplemental_summary_recompute_failed:{type(exc).__name__}:{exc}"
        )
        return
    if _plain_json(recomputed) != _plain_json(summary):
        violations.append("supplemental_summary_recompute_mismatch")


def _load_dataset_or_none(
    root: Path, violations: list[str], label: str
) -> LoadedRegionLearningDataset | None:
    try:
        return load_region_learning_dataset(root)
    except Exception as exc:
        violations.append(
            f"{label}_strict_dataset_loader_failed:{type(exc).__name__}:{exc}"
        )
        return None


def _load_canonical_view_or_none(
    dataset: LoadedRegionLearningDataset | None,
    *,
    training_registry: Path,
    shared_registry: Path,
    violations: list[str],
    label: str,
) -> CanonicalRegionLearningDatasetView | None:
    if dataset is None:
        return None
    try:
        return load_canonical_region_learning_split_view(
            dataset,
            training_seed_registry_path=training_registry,
            shared_registry_path=shared_registry,
        )
    except Exception as exc:
        violations.append(
            f"{label}_canonical_loader_failed:{type(exc).__name__}:{exc}"
        )
        return None


def _empty_corpus_audit(requirements: _CorpusRequirements) -> dict[str, Any]:
    return {
        "classification": requirements.classification,
        "inventory": {
            "episode_count": 0,
            "frame_count": 0,
            "sample_count": 0,
            "sample_definition": "one_region_resource_frame",
            "action_count": 0,
            "canonical_split": {},
        },
        "status": "pending_loader_or_binding_failure",
    }


def _declared_content_sha256(
    value: Mapping[str, Any] | None,
    violations: list[str],
    label: str,
) -> str | None:
    if not isinstance(value, Mapping):
        return None
    declared = value.get("content_sha256")
    content = dict(value)
    content.pop("content_sha256", None)
    try:
        actual = _sha256_json(content)
    except (TypeError, ValueError) as exc:
        violations.append(f"{label}_content_hash_failed:{type(exc).__name__}")
        return None
    if declared != actual:
        violations.append(
            f"{label}_declared_content_sha256_mismatch:"
            f"declared={declared}:actual={actual}"
        )
    return actual


def _unique_source_commit(
    manifest: Mapping[str, Any] | None,
    violations: list[str],
    label: str,
) -> str | None:
    commits = {
        str(item.get("source", {}).get("git_commit"))
        for item in manifest.get("episodes", ())
        if isinstance(item, Mapping) and isinstance(item.get("source"), Mapping)
    } if isinstance(manifest, Mapping) else set()
    if len(commits) != 1:
        violations.append(f"{label}_source_git_commit_not_unique:{sorted(commits)}")
        return None
    return next(iter(commits))


def _read_json_or_none(
    path: Path, violations: list[str], label: str
) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        violations.append(f"{label}_read_failed:{type(exc).__name__}:{exc}")
        return None
    if not isinstance(value, Mapping):
        violations.append(f"{label}_json_object_required")
        return None
    return value


def _sha256_or_none(
    path: Path, violations: list[str], label: str
) -> str | None:
    try:
        return _sha256_file(path)
    except OSError as exc:
        violations.append(f"{label}_sha256_failed:{type(exc).__name__}:{exc}")
        return None


def _mapping_value(value: Mapping[str, Any] | None, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


def _forbidden_key_paths(value: Any, *, path: str) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if (
                normalized in _FORBIDDEN_ONLINE_KEYS
                or normalized.startswith("truth_")
                or normalized.endswith("_truth_id")
                or normalized.endswith("_global_track_id")
                or normalized.endswith("_target_id")
                or normalized.endswith("_object_id")
                or normalized.endswith("_actor_name")
                or "evaluator_truth" in normalized
                or "offline_truth" in normalized
            ):
                found.append(f"{path}.{key}")
            found.extend(_forbidden_key_paths(item, path=f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_forbidden_key_paths(item, path=f"{path}[{index}]"))
    return found


def _nonfinite_number_paths(value: Any, *, path: str) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.extend(_nonfinite_number_paths(item, path=f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_nonfinite_number_paths(item, path=f"{path}[{index}]"))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            finite = math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            finite = False
        if not finite:
            found.append(path)
    return found


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _safe_float(value: Any) -> float:
    if isinstance(value, bool):
        return -math.inf
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return -math.inf
    return result if math.isfinite(result) else -math.inf


def _strictly_greater(value: Any, lower: float) -> bool:
    resolved = _safe_float(value)
    return math.isfinite(resolved) and resolved > float(lower)


def _ordered_counter(value: Mapping[str, int]) -> dict[str, int]:
    return {str(key): int(value[key]) for key in sorted(value)}


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _assert_output_paths_safe(
    outputs: Iterable[Path],
    *,
    protected_roots: Iterable[Path],
    source_files: Iterable[Path],
) -> None:
    resolved_sources = {path.resolve() for path in source_files}
    resolved_roots = tuple(path.resolve() for path in protected_roots)
    for output in outputs:
        resolved = output.resolve()
        if resolved in resolved_sources:
            raise RegionResourceFullSampleAuditError(
                "audit output must not overwrite a source artifact"
            )
        for root in resolved_roots:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            raise RegionResourceFullSampleAuditError(
                "audit output must remain outside frozen dataset roots"
            )


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _render_markdown(
    report: Mapping[str, Any],
    *,
    output_json_path: Path,
    output_json_sha256: str,
) -> str:
    formal = report["formal_corpus"]
    supplemental = report["supplemental_curriculum"]
    formal_inventory = formal["inventory"]
    supplemental_inventory = supplemental["inventory"]
    status = report["status"]
    audit = report["audit"]
    lines = [
        "# D4 区域调度全样本准入审计",
        "",
        f"验证日期：{report['validation_date']}。审计模式为只读、失败关闭。",
        "",
        "## 结论",
        "",
        (
            f"正式数据全样本状态为 `{status['formal_full_sample']}`，补充课程状态为 "
            f"`{status['supplemental_full_sample']}`，联合状态为 "
            f"`{status['combined_full_sample']}`。"
        ),
        (
            "本审计没有训练行为克隆或近端策略优化模型，没有写入权重，也没有开放在线辅助或裁决权限。"
        ),
        "",
        "## 数据规模",
        "",
        "| 数据 | episode | frame | sample | action | 规范切分 |",
        "|---|---:|---:|---:|---:|---|",
        (
            f"| 正式区域数据 | {formal_inventory['episode_count']} | "
            f"{formal_inventory['frame_count']} | {formal_inventory['sample_count']} | "
            f"{formal_inventory['action_count']} | 60/20/20 seed |"
        ),
        (
            f"| 补充规则课程 | {supplemental_inventory['episode_count']} | "
            f"{supplemental_inventory['frame_count']} | "
            f"{supplemental_inventory['sample_count']} | "
            f"{supplemental_inventory['action_count']} | 60/20/20 seed |"
        ),
        "",
        "sample 定义为一个区域资源帧。action 是该帧中按区域输出的投影后动作。",
        "",
        "## 正式数据",
        "",
        _split_markdown(formal_inventory["canonical_split"]),
        "",
        _action_markdown(formal["action_coverage"]),
        "",
        (
            f"数值有限样本 {formal['numeric_feature_audit']['finite_sample_count']}/"
            f"{formal_inventory['sample_count']}，安全合同有效样本 "
            f"{formal['safety_and_generation_audit']['safety_valid_sample_count']}/"
            f"{formal_inventory['sample_count']}。"
        ),
        "",
        "## 补充课程",
        "",
        _split_markdown(supplemental_inventory["canonical_split"]),
        "",
        _action_markdown(supplemental["action_coverage"]),
        "",
        (
            f"数值有限样本 {supplemental['numeric_feature_audit']['finite_sample_count']}/"
            f"{supplemental_inventory['sample_count']}，安全合同有效样本 "
            f"{supplemental['safety_and_generation_audit']['safety_valid_sample_count']}/"
            f"{supplemental_inventory['sample_count']}。"
        ),
        "",
        "补充课程只证明结构、有限值、动作覆盖和确定性安全约束。它不提供真实运行时成员确认、执行结果、回报、中心或二级接管效果，也不提供网络分区效果。",
        "正式数据和补充课程中的 `target.kind=rule` 都只表示规则教师标签；`recommendation.projected=true` 只表示建议通过确定性投影，不表示动作已执行或已收到运行时确认。",
        "",
        "## 文件与来源",
        "",
        f"- 正式数据：`{report['source_paths']['formal_dataset']}`",
        f"- 补充课程：`{report['source_paths']['supplemental_dataset']}`",
        f"- 共享切分：`{report['source_paths']['shared_seed_registry']}`",
        f"- 审计 JSON：`{_display_path(output_json_path)}`",
        "",
        "| 项目 | 正式数据 | 补充课程 |",
        "|---|---:|---:|",
        (
            f"| 数据文件数 | {report['artifact_integrity']['formal']['dataset_file_count']} | "
            f"{report['artifact_integrity']['supplemental']['dataset_file_count']} |"
        ),
        (
            f"| episode 哈希通过 | "
            f"{report['artifact_integrity']['formal']['episode_sha256_verified_count']} | "
            f"{report['artifact_integrity']['supplemental']['episode_sha256_verified_count']} |"
        ),
        (
            f"| 审计期间源文件未变化 | "
            f"{str(report['artifact_integrity']['formal']['source_unchanged_during_audit']).lower()} | "
            f"{str(report['artifact_integrity']['supplemental']['source_unchanged_during_audit']).lower()} |"
        ),
        "",
        (
            f"审计内容 SHA256：`{report['content_sha256']}`。本次 tracked JSON "
            f"文件的带外 SHA256 为 `{output_json_sha256}`；D6 必须先按显式路径复算"
            "文件哈希，再读取内容和 availability。"
        ),
        "",
        "## 未闭合证据",
        "",
        "- 显式投影前动作掩码未记录，状态为 unavailable。",
        "- 旧计划、旧时期和过期租约的被拒候选未作为样本记录，状态为 unavailable。",
        "- 真实运行时 CoalitionMemberAck、执行结果和可归因回报未记录。",
        "- 同 seed 规则与候选策略的 paired shadow 证据未形成。",
        "- 上述证据闭合前，确定性区域规则、lease/epoch 和安全投影仍是唯一可执行路径。",
        "",
        "## 审计状态",
        "",
        f"通过：`{str(audit['passed']).lower()}`；违规数：{audit['violation_count']}。",
    ]
    if audit["violations"]:
        lines.extend(["", "失败项："])
        lines.extend(f"- `{item}`" for item in audit["violations"][:100])
    return "\n".join(lines) + "\n"


def _split_markdown(split: Mapping[str, Mapping[str, Any]]) -> str:
    rows = [
        "| split | episode | frame | sample | action |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in _SPLITS:
        item = split[name]
        rows.append(
            f"| {name} | {item['episode_count']} | {item['frame_count']} | "
            f"{item['sample_count']} | {item['action_count']} |"
        )
    return "\n".join(rows)


def _action_markdown(value: Mapping[str, Any]) -> str:
    return (
        f"动作总数 {value['action_count']}；hold={value['hold_true_count']}，"
        f"request-replan={value['request_replan_true_count']}，"
        f"非零配额={value['resource_quota_nonzero_count']}，"
        f"跨区转移={value['transfer_count']}。"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-dataset", type=Path, required=True)
    parser.add_argument("--supplemental-dataset", type=Path, required=True)
    parser.add_argument("--training-seed-registry", type=Path, required=True)
    parser.add_argument("--shared-seed-registry", type=Path, required=True)
    parser.add_argument("--supplemental-canonical-view", type=Path, required=True)
    parser.add_argument("--supplemental-summary", type=Path, required=True)
    for name in RegionResourceFullSampleExpectedBindings.__dataclass_fields__:
        parser.add_argument(f"--expected-{name.replace('_', '-')}", required=True)
    parser.add_argument("--validation-date", default=VALIDATION_DATE)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    expected = RegionResourceFullSampleExpectedBindings(
        **{
            name: getattr(args, f"expected_{name}")
            for name in RegionResourceFullSampleExpectedBindings.__dataclass_fields__
        }
    )
    report = audit_region_resource_full_samples(
        args.formal_dataset,
        args.supplemental_dataset,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
        supplemental_canonical_view_path=args.supplemental_canonical_view,
        supplemental_summary_path=args.supplemental_summary,
        expected=expected,
        output_json_path=args.output_json,
        output_markdown_path=args.output_markdown,
        validation_date=args.validation_date,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "content_sha256": report["content_sha256"],
                "passed": report["audit"]["passed"],
                "violation_count": report["audit"]["violation_count"],
            },
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0 if report["audit"]["passed"] else 1


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI.
    raise SystemExit(main())


__all__ = [
    "REGION_RESOURCE_FULL_SAMPLE_AUDIT_SCHEMA",
    "RegionResourceFullSampleAuditError",
    "RegionResourceFullSampleExpectedBindings",
    "audit_region_resource_full_samples",
    "build_parser",
    "main",
]
