"""Fail-closed full-sample audit for the supplemental active-vision BC corpus.

The audit is read-only with respect to the dataset, canonical view, seed
registries, and producer summary. It validates every checksummed artifact and
every behavior-cloning sample, but it does not train a model or grant runtime
authority.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import numpy as np

from .active_vision_bc_training import (
    read_json,
    sha256_file,
    write_json_atomic,
    write_text_atomic,
)
from .active_vision_curriculum import ActiveVisionCurriculumConfig
from .active_vision_curriculum_dataset import (
    RESERVED_ACTIVE_VISION_EVALUATION_SEEDS,
    audit_active_vision_supplemental_curriculum,
)
from .active_vision_episode_dataset import (
    ActiveVisionSourceIdentityV1,
    LazyActiveVisionEpisodeDataset,
    load_active_vision_episode_dataset_lazy,
)
from .active_vision_learning import (
    ACTIVE_VISION_FEATURE_NAMES,
    active_vision_candidate_batch,
)
from .canonical_seed_view import (
    active_vision_canonical_readiness,
    load_active_vision_canonical_seed_view,
)


ACTIVE_VISION_SUPPLEMENTAL_BC_AUDIT_SCHEMA_VERSION = (
    "d5.active-vision-supplemental-bc-full-sample-audit.v1"
)
VALIDATION_DATE = "2026-07-21"
_SPLITS = ("train", "validation", "test")
_EXPECTED_EPISODE_COUNTS = {"train": 60, "validation": 20, "test": 20}
_EXPECTED_SAMPLE_COUNTS = {"train": 720, "validation": 240, "test": 240}
_EXPECTED_INTENT_COUNTS = {
    "hold": 200,
    "observe_target": 600,
    "reacquire": 200,
    "search_sector": 200,
}
_EXPECTED_FOV_COUNTS = {"wide": 1000, "zoom": 200}
_EXPECTED_ROLE_COUNTS = {"interceptor": 600, "recon": 600}
_EXPECTED_ACK_COUNTS = {"applied": 400, "rejected": 400, "missing": 400}
_LABEL_NAMES = ("reward", "outcome", "counterfactual", "causal_label")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40,64}")


class ActiveVisionSupplementalBcAuditError(RuntimeError):
    """Invalid audit invocation that must not write an output artifact."""


@dataclass(frozen=True)
class ActiveVisionSupplementalBcExpectedBindings:
    """Caller-supplied immutable identities for one clean producer run."""

    dataset_manifest_sha256: str
    canonical_view_sha256: str
    dataset_config_sha256: str
    training_registry_sha256: str
    shared_registry_sha256: str
    summary_content_sha256: str
    source_git_commit: str

    def __post_init__(self) -> None:
        for name in (
            "dataset_manifest_sha256",
            "canonical_view_sha256",
            "dataset_config_sha256",
            "training_registry_sha256",
            "shared_registry_sha256",
            "summary_content_sha256",
        ):
            value = str(getattr(self, name)).strip().lower()
            if _SHA256_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{name} must be a lowercase SHA256")
            object.__setattr__(self, name, value)
        commit = str(self.source_git_commit).strip().lower()
        if _COMMIT_PATTERN.fullmatch(commit) is None:
            raise ValueError("source_git_commit must be a full lowercase Git object ID")
        object.__setattr__(self, "source_git_commit", commit)

    def to_payload(self) -> dict[str, str]:
        return {
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "canonical_view_sha256": self.canonical_view_sha256,
            "dataset_config_sha256": self.dataset_config_sha256,
            "training_registry_sha256": self.training_registry_sha256,
            "shared_registry_sha256": self.shared_registry_sha256,
            "summary_content_sha256": self.summary_content_sha256,
            "source_git_commit": self.source_git_commit,
        }


def audit_active_vision_supplemental_bc_dataset(
    dataset_dir: str | Path,
    *,
    canonical_view_path: str | Path,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    supplemental_summary_path: str | Path,
    expected: ActiveVisionSupplementalBcExpectedBindings,
    output_json_path: str | Path,
    output_markdown_path: str | Path,
    validation_date: str = VALIDATION_DATE,
) -> dict[str, Any]:
    """Audit all 100 episodes and 1200 BC samples, then write both reports."""

    if not isinstance(expected, ActiveVisionSupplementalBcExpectedBindings):
        raise TypeError("expected must be ActiveVisionSupplementalBcExpectedBindings")
    date = str(validation_date).strip()
    if not date:
        raise ValueError("validation_date must not be empty")

    dataset_root = Path(dataset_dir).resolve()
    view_path = Path(canonical_view_path).resolve()
    training_path = Path(training_seed_registry_path).resolve()
    shared_path = Path(shared_seed_registry_path).resolve()
    summary_path = Path(supplemental_summary_path).resolve()
    json_path = Path(output_json_path).resolve()
    markdown_path = Path(output_markdown_path).resolve()
    _assert_report_paths_safe(
        (json_path, markdown_path),
        protected_roots=(
            dataset_root.parent,
            training_path.parent,
            shared_path.parent,
        ),
        source_files=(
            view_path,
            training_path,
            shared_path,
            summary_path,
            dataset_root / "manifest.json",
            dataset_root / "dataset_config.json",
            dataset_root / "SHA256SUMS",
        ),
    )

    violations: list[str] = []
    expected_payload = expected.to_payload()
    source_files = {
        "dataset_manifest_sha256": dataset_root / "manifest.json",
        "canonical_view_sha256": view_path,
        "dataset_config_sha256": dataset_root / "dataset_config.json",
        "training_registry_sha256": training_path,
        "shared_registry_sha256": shared_path,
        "dataset_checksums_sha256": dataset_root / "SHA256SUMS",
        "summary_file_sha256": summary_path,
    }
    actual_bindings: dict[str, Any] = {}
    source_hashes_before: dict[str, str | None] = {}
    for name, path in source_files.items():
        actual = _optional_sha256(path, violations, name)
        actual_bindings[name] = actual
        source_hashes_before[name] = actual

    summary = _optional_read_json(summary_path, violations, "supplemental_summary")
    view_manifest = _optional_read_json(view_path, violations, "canonical_view")
    training_registry = _optional_read_json(
        training_path, violations, "training_seed_registry"
    )
    summary_content_sha = _summary_content_sha256(summary, violations)
    actual_bindings["summary_content_sha256"] = summary_content_sha
    actual_bindings["source_git_commit"] = _nested_value(
        summary, "source_binding", "git_commit"
    )

    binding_checks: dict[str, dict[str, Any]] = {}
    for name, expected_value in expected_payload.items():
        actual_value = actual_bindings.get(name)
        passed = actual_value == expected_value
        binding_checks[name] = {
            "expected": expected_value,
            "actual": actual_value,
            "passed": passed,
        }
        if not passed:
            violations.append(
                f"binding_mismatch:{name}:expected={expected_value}:actual={actual_value}"
            )

    declared_summary_sha = None if summary is None else summary.get("content_sha256")
    if declared_summary_sha != summary_content_sha:
        violations.append(
            "summary_declared_content_sha_mismatch:"
            f"declared={declared_summary_sha}:actual={summary_content_sha}"
        )

    dataset: LazyActiveVisionEpisodeDataset | None = None
    canonical_dataset: LazyActiveVisionEpisodeDataset | None = None
    strict_loader_passed = False
    canonical_loader_passed = False
    try:
        dataset = load_active_vision_episode_dataset_lazy(dataset_root)
        strict_loader_passed = True
    except Exception as exc:  # The report must survive corrupt input evidence.
        violations.append(_exception_violation("strict_lazy_loader", exc))
    try:
        canonical_dataset = load_active_vision_canonical_seed_view(
            dataset_root,
            training_seed_registry_path=training_path,
            shared_seed_registry_path=shared_path,
            view_manifest_path=view_path,
        )
        canonical_loader_passed = True
    except Exception as exc:
        violations.append(_exception_violation("canonical_loader", exc))

    inventory, inventory_violations = _audit_dataset_inventory(
        dataset_root,
        None if dataset is None else dataset.manifest,
    )
    violations.extend(inventory_violations)

    producer_contract: Mapping[str, Any] | None = None
    if (
        dataset is not None
        and canonical_dataset is not None
        and summary is not None
        and view_manifest is not None
        and training_registry is not None
    ):
        try:
            producer_contract = _recompute_producer_contract(
                dataset,
                canonical_dataset=canonical_dataset,
                view_manifest=view_manifest,
                view_path=view_path,
                summary=summary,
                training_registry=training_registry,
                training_registry_sha256=str(
                    actual_bindings["training_registry_sha256"]
                ),
                shared_registry_sha256=str(
                    actual_bindings["shared_registry_sha256"]
                ),
            )
            if _plain_json(producer_contract) != _plain_json(summary):
                violations.append("supplemental_summary_recompute_mismatch")
        except Exception as exc:
            violations.append(_exception_violation("producer_contract_audit", exc))

    config = _config_from_summary(summary, violations)
    bc_audit: dict[str, Any] = _empty_bc_audit()
    if canonical_dataset is not None and config is not None:
        bc_audit, bc_violations = _audit_behavior_cloning_samples(
            canonical_dataset,
            view_manifest=view_manifest,
            config=config,
        )
        violations.extend(bc_violations)

    coverage_source = producer_contract if producer_contract is not None else summary
    coverage = _coverage_payload(coverage_source, bc_audit)
    _validate_acceptance_thresholds(
        coverage,
        inventory=inventory,
        bc_audit=bc_audit,
        violations=violations,
    )

    source_hashes_after = {
        name: _optional_sha256(path, violations, f"post_audit_{name}")
        for name, path in source_files.items()
    }
    sources_unchanged = source_hashes_after == source_hashes_before
    if not sources_unchanged:
        violations.append("source_artifact_changed_during_audit")

    violations = sorted(set(violations))
    passed = not violations
    report: dict[str, Any] = {
        "schema_version": ACTIVE_VISION_SUPPLEMENTAL_BC_AUDIT_SCHEMA_VERSION,
        "validation_date": date,
        "purpose": "supplemental_rule_teacher_behavior_cloning_full_sample_admission",
        "corpus_classification": {
            "formal_observation_corpus": False,
            "supplemental_rule_teacher_data": True,
            "offline_evaluation_labels_available": False,
            "real_runtime_ack_evidence": False,
        },
        "expected_bindings": expected_payload,
        "actual_bindings": actual_bindings,
        "binding_checks": binding_checks,
        "artifact_integrity": {
            **inventory,
            "strict_lazy_loader_passed": strict_loader_passed,
            "canonical_loader_passed": canonical_loader_passed,
            "source_hashes_before": source_hashes_before,
            "source_hashes_after": source_hashes_after,
            "source_artifacts_unchanged": sources_unchanged,
            "formal_900_episode_dataset_modified": False,
        },
        "acceptance_thresholds": {
            "episode_count": 100,
            "sample_count": 1200,
            "canonical_episode_counts": dict(_EXPECTED_EPISODE_COUNTS),
            "canonical_sample_counts": dict(_EXPECTED_SAMPLE_COUNTS),
            "reserved_seed_overlap_maximum": 0,
            "dirty_episode_count_maximum": 0,
            "online_truth_identifier_count_maximum": 0,
            "nonfinite_feature_sample_count_maximum": 0,
            "offline_available_sample_count_maximum_per_label": 0,
            "audit_violation_count_maximum": 0,
        },
        "coverage": coverage,
        "behavior_cloning_feature_audit": bc_audit,
        "version_and_identity_audit": _version_identity_payload(coverage_source),
        "truth_seed_and_source_audit": _truth_source_payload(coverage_source),
        "synthetic_ack_fault_coverage": {
            "counts": _source_mapping(
                coverage_source, "ack_fault_coverage", "counts"
            ),
            "expected_counts": dict(_EXPECTED_ACK_COUNTS),
            "interpretation": "deterministic_fault_injection_coverage_only",
            "real_runtime_distribution_evidence": False,
            "runtime_ack_attribution_available": False,
            "reward_or_outcome_evidence": False,
        },
        "offline_label_availability": _offline_availability_payload(
            coverage_source, bc_audit
        ),
        "admission": {
            "behavior_cloning_full_sample_audit": (
                "complete" if passed else "pending"
            ),
            "d6_cross_module_learning_admission": "pending_external_audit",
            "ppo": False,
            "assist": False,
            "online_authority": False,
            "camera_command_authority": False,
            "rule_fallback_required": True,
            "model_training_performed": False,
            "weights_written": False,
        },
        "remaining_gates": [
            "d6_cross_module_learning_admission_audit",
            "real_runtime_applied_ack_and_outcome_attribution",
            "reward_counterfactual_and_causal_labels",
            "paired_shadow_non_degradation",
            "ppo_assist_and_authority_remain_closed",
        ],
        "audit": {
            "passed": passed,
            "violation_count": len(violations),
            "violations": violations,
        },
    }
    report["content_sha256"] = _sha256_json(report)
    write_json_atomic(json_path, report)
    write_text_atomic(markdown_path, _audit_markdown(report))
    return report


def _recompute_producer_contract(
    dataset: LazyActiveVisionEpisodeDataset,
    *,
    canonical_dataset: LazyActiveVisionEpisodeDataset,
    view_manifest: Mapping[str, Any],
    view_path: Path,
    summary: Mapping[str, Any],
    training_registry: Mapping[str, Any],
    training_registry_sha256: str,
    shared_registry_sha256: str,
) -> Mapping[str, Any]:
    config = ActiveVisionCurriculumConfig(**dict(summary["config"]))
    binding = summary["source_binding"]
    source_identity = ActiveVisionSourceIdentityV1(
        git_commit=str(binding["git_commit"]),
        git_dirty=bool(binding["repository_dirty"]),
        config_sha256=str(binding["curriculum_generation_config_sha256"]),
    )
    readiness = active_vision_canonical_readiness(
        canonical_dataset,
        view_manifest=view_manifest,
        view_manifest_sha256=sha256_file(view_path),
    )
    readiness_json_path = view_path.with_name("canonical_readiness.json")
    readiness_markdown_path = view_path.with_name("canonical_readiness.md")
    return audit_active_vision_supplemental_curriculum(
        dataset,
        canonical_dataset=canonical_dataset,
        view_manifest=view_manifest,
        view_manifest_sha256=sha256_file(view_path),
        canonical_readiness=readiness,
        canonical_readiness_json_sha256=sha256_file(readiness_json_path),
        canonical_readiness_markdown_sha256=sha256_file(readiness_markdown_path),
        config=config,
        created_at_utc=str(summary["created_at_utc"]),
        training_seeds=tuple(int(seed) for seed in training_registry["training_seeds"]),
        reserved_seeds=tuple(
            int(seed) for seed in training_registry["reserved_evaluation_seeds"]
        ),
        source_identity=source_identity,
        generation_config_sha256=str(
            binding["curriculum_generation_config_sha256"]
        ),
        training_registry_sha256=training_registry_sha256,
        shared_registry_sha256=shared_registry_sha256,
    )


def _audit_behavior_cloning_samples(
    dataset: LazyActiveVisionEpisodeDataset,
    *,
    view_manifest: Mapping[str, Any] | None,
    config: ActiveVisionCurriculumConfig,
) -> tuple[dict[str, Any], list[str]]:
    violations: list[str] = []
    split_episode_counts: Counter[str] = Counter()
    split_sample_counts: Counter[str] = Counter()
    intent_counts: Counter[str] = Counter()
    fov_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    candidate_histogram: Counter[str] = Counter()
    seeds_by_split: dict[str, set[int]] = {split: set() for split in _SPLITS}
    observed_track_ids: set[str] = set()
    sample_count = 0
    finite_feature_sample_count = 0
    candidate_row_count = 0
    selected_action_unique_count = 0
    feature_minimum = math.inf
    feature_maximum = -math.inf
    version_monotonic_episode_count = 0

    for split in _SPLITS:
        for episode in dataset.iter_behavior_cloning_episodes(split):
            split_episode_counts[split] += 1
            seeds_by_split[split].add(episode.seed)
            previous_versions = (-1, -1, -1, -1)
            episode_versions_monotonic = True
            for index, transition in enumerate(episode.transitions):
                sample_count += 1
                split_sample_counts[split] += 1
                action = transition.selected_action
                intent_counts[action.intent.value] += 1
                fov_counts[action.fov_mode.value] += 1
                role = _camera_role(transition.camera_id, config)
                if role is None:
                    violations.append(
                        f"unknown_camera_role:seed={episode.seed}:sample={index}"
                    )
                else:
                    role_counts[role] += 1
                snapshot = transition.snapshot
                track_versions = tuple(item.track_version for item in snapshot.tracks)
                current_versions = (
                    snapshot.plan.plan_version,
                    snapshot.plan.coalition_version,
                    snapshot.communication.communication_version,
                    min(track_versions) if track_versions else -1,
                )
                if any(
                    current < previous
                    for current, previous in zip(current_versions, previous_versions)
                ):
                    episode_versions_monotonic = False
                    violations.append(
                        f"version_regression:seed={episode.seed}:sample={index}"
                    )
                previous_versions = current_versions
                if (
                    action.plan_version != snapshot.plan.plan_version
                    or action.coalition_version != snapshot.plan.coalition_version
                    or action.communication_version
                    != snapshot.communication.communication_version
                ):
                    violations.append(
                        f"selected_action_version_mismatch:seed={episode.seed}:sample={index}"
                    )
                observed_track_ids.update(
                    item.global_track_id for item in snapshot.tracks
                )
                observed_track_ids.update(
                    item.global_track_id for item in snapshot.plan.assignments
                )
                observed_track_ids.update(
                    item.global_track_id for item in snapshot.projections
                )
                if action.target_global_track_id is not None:
                    observed_track_ids.add(action.target_global_track_id)
                try:
                    batch = active_vision_candidate_batch(
                        snapshot,
                        camera_id=transition.camera_id,
                    )
                except Exception as exc:
                    violations.append(
                        _exception_violation(
                            f"feature_extraction_seed_{episode.seed}_sample_{index}",
                            exc,
                        )
                    )
                    continue
                features = np.asarray(batch.features)
                expected_shape = (
                    len(batch.actions),
                    len(ACTIVE_VISION_FEATURE_NAMES),
                )
                if features.shape != expected_shape or len(batch.actions) == 0:
                    violations.append(
                        f"feature_shape_mismatch:seed={episode.seed}:sample={index}:"
                        f"actual={features.shape}:expected={expected_shape}"
                    )
                else:
                    candidate_histogram[str(len(batch.actions))] += 1
                    candidate_row_count += len(batch.actions)
                    if bool(np.isfinite(features).all()):
                        finite_feature_sample_count += 1
                        feature_minimum = min(feature_minimum, float(features.min()))
                        feature_maximum = max(feature_maximum, float(features.max()))
                    else:
                        violations.append(
                            f"nonfinite_feature:seed={episode.seed}:sample={index}"
                        )
                selected_matches = sum(
                    candidate.action_key == action.action_key
                    for candidate in batch.actions
                )
                if selected_matches == 1:
                    selected_action_unique_count += 1
                else:
                    violations.append(
                        f"selected_action_candidate_multiplicity:seed={episode.seed}:"
                        f"sample={index}:count={selected_matches}"
                    )
            if episode_versions_monotonic:
                version_monotonic_episode_count += 1

    split_intersections = {
        "train_validation": sorted(
            seeds_by_split["train"] & seeds_by_split["validation"]
        ),
        "train_test": sorted(seeds_by_split["train"] & seeds_by_split["test"]),
        "validation_test": sorted(
            seeds_by_split["validation"] & seeds_by_split["test"]
        ),
    }
    reserved_overlap = sorted(
        set(RESERVED_ACTIVE_VISION_EVALUATION_SEEDS).intersection(
            set().union(*seeds_by_split.values())
        )
    )
    view_seed_values = (
        {}
        if view_manifest is None
        else view_manifest.get("canonical_split", {}).get("seed_values", {})
    )
    computed_seed_values = {
        split: sorted(seeds_by_split[split]) for split in _SPLITS
    }
    if view_seed_values != computed_seed_values:
        violations.append("canonical_numeric_seed_bucket_mismatch")
    if any(split_intersections.values()):
        violations.append("canonical_seed_not_atomic")
    if reserved_overlap:
        violations.append("reserved_seed_leakage")
    if observed_track_ids != {config.global_track_id}:
        violations.append(
            "caller_owned_global_track_id_changed:"
            f"expected={config.global_track_id}:actual={sorted(observed_track_ids)}"
        )

    payload = {
        "episode_count": sum(split_episode_counts.values()),
        "sample_count": sample_count,
        "feature_schema": {
            "feature_count": len(ACTIVE_VISION_FEATURE_NAMES),
            "feature_names": list(ACTIVE_VISION_FEATURE_NAMES),
        },
        "finite_feature_sample_count": finite_feature_sample_count,
        "nonfinite_feature_sample_count": sample_count - finite_feature_sample_count,
        "candidate_row_count": candidate_row_count,
        "candidate_count_histogram": _ordered_counter(candidate_histogram),
        "selected_action_unique_candidate_count": selected_action_unique_count,
        "feature_value_range": {
            "minimum": None if math.isinf(feature_minimum) else feature_minimum,
            "maximum": None if math.isinf(feature_maximum) else feature_maximum,
        },
        "canonical_episode_counts": _ordered_split_counter(split_episode_counts),
        "canonical_sample_counts": _ordered_split_counter(split_sample_counts),
        "canonical_seed_counts": {
            split: len(seeds_by_split[split]) for split in _SPLITS
        },
        "canonical_seed_values": computed_seed_values,
        "numeric_seed_atomic": not any(split_intersections.values()),
        "seed_intersections": split_intersections,
        "reserved_evaluation_seed_overlap": reserved_overlap,
        "intent_counts": _ordered_counts(intent_counts, _EXPECTED_INTENT_COUNTS),
        "fov_mode_counts": _ordered_counts(fov_counts, _EXPECTED_FOV_COUNTS),
        "camera_role_counts": _ordered_counts(role_counts, _EXPECTED_ROLE_COUNTS),
        "version_monotonic_episode_count": version_monotonic_episode_count,
        "version_consistency_checked_sample_count": sample_count,
        "caller_owned_global_track_id": config.global_track_id,
        "observed_global_track_id_values": sorted(observed_track_ids),
        "global_track_id_created_rewritten_or_rebound": (
            observed_track_ids != {config.global_track_id}
        ),
    }
    return payload, violations


def _audit_dataset_inventory(
    root: Path,
    manifest: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    violations: list[str] = []
    checksums_path = root / "SHA256SUMS"
    checksums: dict[str, str] = {}
    try:
        for raw_line in checksums_path.read_text(encoding="ascii").splitlines():
            digest, relative = raw_line.split("  ", 1)
            if _SHA256_PATTERN.fullmatch(digest) is None or relative in checksums:
                raise ValueError("invalid or duplicate checksum entry")
            checksums[relative] = digest
    except Exception as exc:
        violations.append(_exception_violation("checksum_inventory", exc))

    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != checksums_path
    } if root.is_dir() else set()
    checksum_set_exact = set(checksums) == actual_files
    if not checksum_set_exact:
        violations.append(
            "checksum_artifact_set_mismatch:"
            f"missing={sorted(actual_files - set(checksums))}:"
            f"extra={sorted(set(checksums) - actual_files)}"
        )

    verified_file_count = 0
    hash_mismatch_count = 0
    for relative, expected_sha in checksums.items():
        path = root / relative
        try:
            actual_sha = sha256_file(path)
        except Exception as exc:
            violations.append(_exception_violation(f"artifact_hash_{relative}", exc))
            continue
        if actual_sha != expected_sha:
            hash_mismatch_count += 1
            violations.append(
                f"artifact_sha_mismatch:{relative}:"
                f"expected={expected_sha}:actual={actual_sha}"
            )
        else:
            verified_file_count += 1

    expected_online: set[str] = set()
    expected_offline: set[str] = set()
    expected_descriptors: set[str] = set()
    descriptor_manifest_match_count = 0
    if manifest is not None:
        for descriptor in manifest.get("episodes", ()):
            uid = str(descriptor["episode_uid"])
            online = str(descriptor["online_file"])
            offline = str(descriptor["offline_file"])
            episode_file = f"episodes/{uid}.episode.json"
            expected_online.add(online)
            expected_offline.add(offline)
            expected_descriptors.add(episode_file)
            try:
                persisted = read_json(root / episode_file)
                if _plain_json(persisted) == _plain_json(descriptor):
                    descriptor_manifest_match_count += 1
                else:
                    violations.append(f"descriptor_manifest_mismatch:{uid}")
                if sha256_file(root / online) != str(descriptor["online_sha256"]):
                    violations.append(f"manifest_online_sha_mismatch:{uid}")
                if sha256_file(root / offline) != str(descriptor["offline_sha256"]):
                    violations.append(f"manifest_offline_sha_mismatch:{uid}")
            except Exception as exc:
                violations.append(_exception_violation(f"descriptor_{uid}", exc))
    actual_online = _relative_files(root, root / "online")
    actual_offline = _relative_files(root, root / "offline")
    actual_descriptors = _relative_files(root, root / "episodes")
    collections_complete = (
        expected_online == actual_online
        and expected_offline == actual_offline
        and expected_descriptors == actual_descriptors
    )
    if manifest is not None and not collections_complete:
        violations.append("online_offline_episode_collection_mismatch")

    return {
        "supplemental_output_file_count": sum(
            path.is_file() for path in root.parent.rglob("*")
        )
        if root.parent.is_dir()
        else 0,
        "supplemental_output_size_bytes": sum(
            path.stat().st_size for path in root.parent.rglob("*") if path.is_file()
        )
        if root.parent.is_dir()
        else 0,
        "dataset_file_count_including_sha256sums": (
            len(actual_files) + int(checksums_path.is_file())
        ),
        "checksummed_file_count": len(checksums),
        "checksum_artifact_set_exact": checksum_set_exact,
        "sha256_verified_file_count": verified_file_count,
        "sha256_mismatch_file_count": hash_mismatch_count,
        "online_file_count": len(actual_online),
        "offline_file_count": len(actual_offline),
        "episode_descriptor_file_count": len(actual_descriptors),
        "descriptor_manifest_match_count": descriptor_manifest_match_count,
        "online_offline_episode_collections_complete": collections_complete,
    }, violations


def _validate_acceptance_thresholds(
    coverage: Mapping[str, Any],
    *,
    inventory: Mapping[str, Any],
    bc_audit: Mapping[str, Any],
    violations: list[str],
) -> None:
    checks = {
        "episode_count": coverage.get("episode_count") == 100,
        "sample_count": coverage.get("sample_count") == 1200,
        "intent_counts": coverage.get("intent_counts") == _EXPECTED_INTENT_COUNTS,
        "fov_mode_counts": coverage.get("fov_mode_counts") == _EXPECTED_FOV_COUNTS,
        "camera_role_counts": coverage.get("camera_role_counts") == _EXPECTED_ROLE_COUNTS,
        "canonical_episode_counts": bc_audit.get("canonical_episode_counts")
        == _EXPECTED_EPISODE_COUNTS,
        "canonical_sample_counts": bc_audit.get("canonical_sample_counts")
        == _EXPECTED_SAMPLE_COUNTS,
        "finite_features": bc_audit.get("finite_feature_sample_count") == 1200,
        "selected_action_unique": bc_audit.get(
            "selected_action_unique_candidate_count"
        )
        == 1200,
        "numeric_seed_atomic": bc_audit.get("numeric_seed_atomic") is True,
        "reserved_seed_overlap": bc_audit.get("reserved_evaluation_seed_overlap")
        == [],
        "artifact_collections": inventory.get(
            "online_offline_episode_collections_complete"
        )
        is True,
        "artifact_sha": inventory.get("sha256_mismatch_file_count") == 0,
    }
    for name, passed in checks.items():
        if not passed:
            violations.append(f"acceptance_threshold_failed:{name}")


def _coverage_payload(
    source: Mapping[str, Any] | None,
    bc_audit: Mapping[str, Any],
) -> dict[str, Any]:
    producer = {} if source is None else dict(source.get("coverage", {}))
    return {
        "episode_count": producer.get("episode_count", bc_audit.get("episode_count")),
        "segment_count": producer.get("segment_count"),
        "sample_count": producer.get("sample_count", bc_audit.get("sample_count")),
        "intent_counts": producer.get("intent_counts", bc_audit.get("intent_counts", {})),
        "fov_mode_counts": producer.get(
            "fov_mode_counts", bc_audit.get("fov_mode_counts", {})
        ),
        "camera_role_counts": producer.get(
            "camera_role_counts", bc_audit.get("camera_role_counts", {})
        ),
        "canonical_episode_counts": bc_audit.get("canonical_episode_counts", {}),
        "canonical_sample_counts": bc_audit.get("canonical_sample_counts", {}),
    }


def _version_identity_payload(source: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _source_mapping(source, "version_and_identity_audit")
    changed = payload.get("global_track_id_created_or_rebound")
    return {
        **payload,
        "caller_owned_binding_rechecked_for_all_samples": True,
        "d5_created_rewritten_or_rebound_global_track_id": changed,
    }


def _truth_source_payload(source: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _source_mapping(source, "truth_seed_and_formal_isolation")
    admission = _source_mapping(source, "admission")
    return {
        **payload,
        "repository_dirty": not bool(admission.get("clean_source", False)),
        "dirty_episode_count": admission.get("dirty_episode_count"),
        "online_truth_used_for_behavior_cloning": False,
        "dirty_source_accepted": False,
    }


def _offline_availability_payload(
    source: Mapping[str, Any] | None,
    bc_audit: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _source_mapping(source, "offline_label_availability")
    sample_count = int(bc_audit.get("sample_count", 0))
    return {
        name: payload.get(
            name,
            {
                "status": "unavailable",
                "available_sample_count": 0,
                "sample_count": sample_count,
            },
        )
        for name in _LABEL_NAMES
    } | {
        "all_values_explicitly_unavailable": payload.get(
            "all_values_explicitly_unavailable", False
        ),
        "zero_padding_used": payload.get("zero_padding_used", False),
    }


def _empty_bc_audit() -> dict[str, Any]:
    return {
        "episode_count": 0,
        "sample_count": 0,
        "feature_schema": {
            "feature_count": len(ACTIVE_VISION_FEATURE_NAMES),
            "feature_names": list(ACTIVE_VISION_FEATURE_NAMES),
        },
        "finite_feature_sample_count": 0,
        "nonfinite_feature_sample_count": 0,
        "candidate_row_count": 0,
        "candidate_count_histogram": {},
        "selected_action_unique_candidate_count": 0,
        "canonical_episode_counts": {split: 0 for split in _SPLITS},
        "canonical_sample_counts": {split: 0 for split in _SPLITS},
        "canonical_seed_counts": {split: 0 for split in _SPLITS},
        "numeric_seed_atomic": False,
        "reserved_evaluation_seed_overlap": [],
        "intent_counts": {},
        "fov_mode_counts": {},
        "camera_role_counts": {},
    }


def _config_from_summary(
    summary: Mapping[str, Any] | None,
    violations: list[str],
) -> ActiveVisionCurriculumConfig | None:
    if summary is None:
        return None
    try:
        return ActiveVisionCurriculumConfig(**dict(summary["config"]))
    except Exception as exc:
        violations.append(_exception_violation("curriculum_config", exc))
        return None


def _summary_content_sha256(
    summary: Mapping[str, Any] | None,
    violations: list[str],
) -> str | None:
    if summary is None:
        return None
    try:
        content = dict(summary)
        content.pop("content_sha256", None)
        return _sha256_json(content)
    except Exception as exc:
        violations.append(_exception_violation("summary_content_hash", exc))
        return None


def _assert_report_paths_safe(
    report_paths: Sequence[Path],
    *,
    protected_roots: Sequence[Path],
    source_files: Sequence[Path],
) -> None:
    if len(set(report_paths)) != len(report_paths):
        raise ActiveVisionSupplementalBcAuditError(
            "JSON and Markdown audit paths must be distinct"
        )
    source_set = set(source_files)
    for report_path in report_paths:
        if report_path in source_set:
            raise ActiveVisionSupplementalBcAuditError(
                f"audit output must not replace a source artifact: {report_path}"
            )
        for root in protected_roots:
            if report_path == root or root in report_path.parents:
                raise ActiveVisionSupplementalBcAuditError(
                    f"audit output must be outside protected source root {root}: "
                    f"{report_path}"
                )


def _audit_markdown(report: Mapping[str, Any]) -> str:
    coverage = report["coverage"]
    features = report["behavior_cloning_feature_audit"]
    inventory = report["artifact_integrity"]
    bindings = report["actual_bindings"]
    admission = report["admission"]
    audit = report["audit"]
    return "\n".join(
        [
            "# D5 主动视觉补充行为克隆全样本准入审计",
            "",
            f"- 验证日期：`{report['validation_date']}`",
            f"- 审计结论：`{admission['behavior_cloning_full_sample_audit']}`",
            f"- 违规数：`{audit['violation_count']}`",
            f"- episode / segment / sample：`{coverage['episode_count']} / {coverage['segment_count']} / {coverage['sample_count']}`",
            f"- canonical episode：`{_inline_json(coverage['canonical_episode_counts'])}`",
            f"- canonical sample：`{_inline_json(coverage['canonical_sample_counts'])}`",
            f"- 完整文件：online / offline / episode = `{inventory['online_file_count']} / {inventory['offline_file_count']} / {inventory['episode_descriptor_file_count']}`",
            f"- SHA256 校验：`{inventory['sha256_verified_file_count']} / {inventory['checksummed_file_count']}`",
            f"- 有限特征样本：`{features['finite_feature_sample_count']} / {features['sample_count']}`，候选特征行 `{features['candidate_row_count']}`",
            f"- intent：`{_inline_json(coverage['intent_counts'])}`",
            f"- FOV：`{_inline_json(coverage['fov_mode_counts'])}`",
            f"- 相机角色：`{_inline_json(coverage['camera_role_counts'])}`",
            "",
            "验收阈值为 100 episode、1200 sample、canonical 60/20/20 episode 与 "
            "720/240/240 sample、全部文件哈希一致、全部 35 维候选特征有限，且 "
            "truth、reserved seed、dirty source 和审计违规均为 0。",
            "",
            "`applied/rejected/missing = 400/400/400` 仅表示 synthetic 确定性故障注入覆盖，"
            "不是实际运行 ACK 分布，也不构成动作到 outcome 的归因证据。",
            "",
            "reward、outcome、counterfactual、causal 四类离线标签均保持 unavailable，"
            "没有用 0 补值。PPO、assist、在线 authority 与相机命令 authority 均为 false，"
            "rule fallback required=true。",
            "",
            "该结论只完成补充规则教师数据的 behavior-cloning 全样本审计，是 D6 跨模块"
            "学习准入的前置证据；它不是正式观测语料、真实 runtime ACK 证据或模型上线许可。",
            "",
            "## 来源绑定",
            "",
            f"- dataset manifest SHA256：`{bindings['dataset_manifest_sha256']}`",
            f"- canonical view SHA256：`{bindings['canonical_view_sha256']}`",
            f"- dataset config SHA256：`{bindings['dataset_config_sha256']}`",
            f"- training registry SHA256：`{bindings['training_registry_sha256']}`",
            f"- shared registry SHA256：`{bindings['shared_registry_sha256']}`",
            f"- summary content SHA256：`{bindings['summary_content_sha256']}`",
            f"- clean source commit：`{bindings['source_git_commit']}`",
            f"- 审计内容 SHA256：`{report['content_sha256']}`",
            "",
            "## 剩余门槛",
            "",
            "- D6 跨模块学习准入审计。",
            "- 真实 runtime applied ACK 与 outcome 归因。",
            "- reward、counterfactual 与 causal 标签。",
            "- paired shadow non-degradation。",
            "- PPO、assist 与 authority 继续关闭。",
            "",
        ]
    )


def _optional_read_json(
    path: Path,
    violations: list[str],
    name: str,
) -> dict[str, Any] | None:
    try:
        return read_json(path)
    except Exception as exc:
        violations.append(_exception_violation(f"read_{name}", exc))
        return None


def _optional_sha256(
    path: Path,
    violations: list[str],
    name: str,
) -> str | None:
    try:
        return sha256_file(path)
    except Exception as exc:
        violations.append(_exception_violation(f"hash_{name}", exc))
        return None


def _exception_violation(stage: str, exc: Exception) -> str:
    code = getattr(exc, "code", None)
    code_text = "" if code is None else f":code={code}"
    return f"{stage}_failed:{type(exc).__name__}{code_text}:{exc}"


def _nested_value(value: Mapping[str, Any] | None, *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _source_mapping(
    source: Mapping[str, Any] | None,
    *keys: str,
) -> dict[str, Any]:
    value = _nested_value(source, *keys)
    return dict(value) if isinstance(value, Mapping) else {}


def _camera_role(
    camera_id: str,
    config: ActiveVisionCurriculumConfig,
) -> str | None:
    if camera_id == config.interceptor_camera_id:
        return "interceptor"
    if camera_id == config.recon_camera_id:
        return "recon"
    return None


def _ordered_counts(
    counts: Mapping[str, int],
    expected: Mapping[str, int],
) -> dict[str, int]:
    return {name: int(counts.get(name, 0)) for name in expected}


def _ordered_counter(counts: Mapping[str, int]) -> dict[str, int]:
    return {key: int(counts[key]) for key in sorted(counts, key=int)}


def _ordered_split_counter(counts: Mapping[str, int]) -> dict[str, int]:
    return {split: int(counts.get(split, 0)) for split in _SPLITS}


def _relative_files(root: Path, directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in directory.glob("*")
        if path.is_file()
    }


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _inline_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--canonical-view", type=Path, required=True)
    parser.add_argument("--training-seed-registry", type=Path, required=True)
    parser.add_argument("--shared-seed-registry", type=Path, required=True)
    parser.add_argument("--supplemental-summary", type=Path, required=True)
    parser.add_argument("--expected-dataset-manifest-sha256", required=True)
    parser.add_argument("--expected-canonical-view-sha256", required=True)
    parser.add_argument("--expected-dataset-config-sha256", required=True)
    parser.add_argument("--expected-training-registry-sha256", required=True)
    parser.add_argument("--expected-shared-registry-sha256", required=True)
    parser.add_argument("--expected-summary-content-sha256", required=True)
    parser.add_argument("--expected-source-git-commit", required=True)
    parser.add_argument("--validation-date", default=VALIDATION_DATE)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    expected = ActiveVisionSupplementalBcExpectedBindings(
        dataset_manifest_sha256=args.expected_dataset_manifest_sha256,
        canonical_view_sha256=args.expected_canonical_view_sha256,
        dataset_config_sha256=args.expected_dataset_config_sha256,
        training_registry_sha256=args.expected_training_registry_sha256,
        shared_registry_sha256=args.expected_shared_registry_sha256,
        summary_content_sha256=args.expected_summary_content_sha256,
        source_git_commit=args.expected_source_git_commit,
    )
    report = audit_active_vision_supplemental_bc_dataset(
        args.dataset_dir,
        canonical_view_path=args.canonical_view,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
        supplemental_summary_path=args.supplemental_summary,
        expected=expected,
        output_json_path=args.output_json,
        output_markdown_path=args.output_markdown,
        validation_date=args.validation_date,
    )
    print(
        json.dumps(
            {
                "behavior_cloning_full_sample_audit": report["admission"][
                    "behavior_cloning_full_sample_audit"
                ],
                "episode_count": report["coverage"]["episode_count"],
                "sample_count": report["coverage"]["sample_count"],
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
    "ACTIVE_VISION_SUPPLEMENTAL_BC_AUDIT_SCHEMA_VERSION",
    "ActiveVisionSupplementalBcAuditError",
    "ActiveVisionSupplementalBcExpectedBindings",
    "audit_active_vision_supplemental_bc_dataset",
    "build_parser",
    "main",
]
