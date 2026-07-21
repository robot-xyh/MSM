"""Audited behavior-cloning workflow for D4 regional graph advice.

This module is offline-only. It reads a finalized D4 dataset, trains a graph
advisor, and writes a development bundle. It never changes D4 authority,
assignment versions, coalition state, leases, or the source dataset.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import random
import shutil
import tempfile
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

from .region_resource import DeterministicResourceProjector
from .region_resource_dataset import (
    REGION_LEARNING_EPISODE_SCHEMA,
    REGION_LEARNING_FRAME_SCHEMA,
    REGION_LEARNING_SOURCE_SCHEMA,
    LoadedRegionLearningDataset,
    RegionLearningAvailability,
    RegionLearningSplit,
    load_region_learning_dataset,
)
from .region_resource_learning import (
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    LearnedRegionResourcePolicy,
    SharedRegionGraphActorCritic,
    behavior_cloning_loss,
    behavior_cloning_step,
    load_region_behavior_cloning_samples,
    load_region_resource_model_bundle,
    recommendation_to_policy_target,
    save_region_resource_model_bundle,
    snapshot_to_region_graph,
)


try:  # D4's deterministic runtime does not depend on torch.
    import torch
except ImportError:  # pragma: no cover - exercised in minimal deployments.
    torch = None


D4_DATA_READINESS_SCHEMA = "d4-region-data-readiness-v1"
D4_MODEL_READINESS_SCHEMA = "d4-region-bc-model-readiness-v1"
D4_TRAINING_CONFIG_SCHEMA = "d4-region-bc-training-config-v1"
D4_TRAINING_METRICS_SCHEMA = "d4-region-bc-training-metrics-v1"
D4_ARTIFACT_MANIFEST_SCHEMA = "d4-region-bc-artifact-manifest-v1"
D4_TRACKED_RESULTS_SCHEMA = "d4-region-bc-tracked-results-v1"


class RegionBehaviorCloningError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegionBehaviorCloningConfig:
    random_seed: int = 20260720
    hidden_dim: int = 64
    message_passing_steps: int = 2
    epochs: int = 80
    batch_size: int = 32
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-5
    max_grad_norm: float = 1.0
    early_stopping_patience: int = 12
    minimum_development_test_seeds: int = 10
    minimum_final_holdout_seeds: int = 20
    final_holdout_seeds: tuple[int, ...] = tuple(range(1000, 1020))
    device: str = "cpu"
    torch_num_threads: int = 1
    model_version: str = "d4-region-bc-900-development-v1"
    d6_audit_frame_count: int | None = None
    d6_unattributed_transition_frame_count: int | None = None
    d6_reward_available_count: int | None = None
    d6_causal_label_available_count: int | None = None
    d6_counterfactual_available_count: int | None = None
    d6_audit_artifact_sha256: str | None = None
    schema: str = D4_TRAINING_CONFIG_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != D4_TRAINING_CONFIG_SCHEMA:
            raise ValueError("unsupported D4 training config schema")
        for name in (
            "random_seed",
            "hidden_dim",
            "message_passing_steps",
            "epochs",
            "batch_size",
            "early_stopping_patience",
            "minimum_development_test_seeds",
            "minimum_final_holdout_seeds",
            "torch_num_threads",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("learning_rate", "max_grad_norm"):
            value = float(getattr(self, name))
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not isfinite(float(self.weight_decay)) or self.weight_decay < 0.0:
            raise ValueError("weight_decay must be finite and non-negative")
        holdouts = tuple(sorted({int(seed) for seed in self.final_holdout_seeds}))
        if any(seed < 0 for seed in holdouts):
            raise ValueError("final holdout seeds must be non-negative")
        if len(holdouts) < self.minimum_final_holdout_seeds:
            raise ValueError("final holdout inventory is smaller than its gate")
        if not self.model_version:
            raise ValueError("model_version must not be empty")
        d6_counts = (
            self.d6_audit_frame_count,
            self.d6_unattributed_transition_frame_count,
            self.d6_reward_available_count,
            self.d6_causal_label_available_count,
            self.d6_counterfactual_available_count,
        )
        if any(value is not None for value in d6_counts):
            if any(value is None for value in d6_counts):
                raise ValueError("D6 audit counts must be supplied together")
            if any(int(value) < 0 for value in d6_counts if value is not None):
                raise ValueError("D6 audit counts must be non-negative")
        if self.d6_audit_artifact_sha256 is not None:
            digest = self.d6_audit_artifact_sha256.lower()
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("D6 audit artifact SHA256 is invalid")
            object.__setattr__(self, "d6_audit_artifact_sha256", digest)
        object.__setattr__(self, "final_holdout_seeds", holdouts)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["final_holdout_seeds"] = list(self.final_holdout_seeds)
        return payload


def audit_region_learning_dataset(
    dataset_root: str | Path,
    *,
    config: RegionBehaviorCloningConfig | None = None,
) -> tuple[LoadedRegionLearningDataset, dict[str, Any]]:
    """Load and independently summarize a finalized, immutable D4 dataset."""

    resolved_config = config or RegionBehaviorCloningConfig()
    root = Path(dataset_root).resolve()
    manifest_path = root / "manifest.json"
    manifest_file_sha256 = _sha256_file(manifest_path)
    loaded = load_region_learning_dataset(root)
    manifest = loaded.manifest

    split_seed_sets = {
        RegionLearningSplit.TRAIN: set(manifest.split.train_seeds),
        RegionLearningSplit.VALIDATION: set(manifest.split.validation_seeds),
        RegionLearningSplit.TEST: set(manifest.split.test_seeds),
    }
    split_episode_counts = {split.value: 0 for split in RegionLearningSplit}
    split_frame_counts = {split.value: 0 for split in RegionLearningSplit}
    split_scenario_groups: dict[str, set[tuple[str, int]]] = {
        split.value: set() for split in RegionLearningSplit
    }
    split_node_counts: dict[str, list[int]] = {
        split.value: [] for split in RegionLearningSplit
    }
    split_edge_counts: dict[str, list[int]] = {
        split.value: [] for split in RegionLearningSplit
    }
    split_resource_counts: dict[str, list[int]] = {
        split.value: [] for split in RegionLearningSplit
    }
    numeric_seed_splits: dict[int, set[str]] = {}
    scenario_seed_splits: dict[tuple[str, str, str, int], set[str]] = {}
    episode_ids: set[str] = set()
    source_identities: set[str] = set()
    scenario_ids: set[str] = set()
    scenario_scales: set[str] = set()
    git_commits: set[str] = set()
    config_hashes: set[str] = set()
    observed_frame_schemas: set[str] = set()
    observed_source_schemas: set[str] = set()
    episode_sha_verified_count = 0

    for episode in loaded.episode_records:
        entry = episode.manifest
        source = episode.source
        path = root / entry.relative_path
        if _sha256_file(path) != entry.episode_sha256:
            raise RegionBehaviorCloningError(
                f"episode SHA256 changed after verified load: {entry.relative_path}"
            )
        episode_sha_verified_count += 1
        split = episode.split.value
        split_episode_counts[split] += 1
        split_frame_counts[split] += len(episode.frames)
        split_scenario_groups[split].add((source.scenario_id, int(source.seed)))
        numeric_seed_splits.setdefault(int(source.seed), set()).add(split)
        group = (
            source.scenario_id,
            source.scenario_version,
            source.scenario_scale or "unspecified",
            int(source.seed),
        )
        scenario_seed_splits.setdefault(group, set()).add(split)
        episode_ids.add(source.episode_id)
        source_identities.add(source.identity_sha256)
        scenario_ids.add(source.scenario_id)
        scenario_scales.add(source.scenario_scale or "unspecified")
        git_commits.add(source.git_commit)
        config_hashes.add(source.config_sha256)
        observed_source_schemas.add(source.schema)
        for frame in episode.frames:
            observed_frame_schemas.add(frame.schema)
            split_node_counts[split].append(frame.snapshot.region_count)
            split_edge_counts[split].append(len(frame.snapshot.edges))
            split_resource_counts[split].append(frame.snapshot.total_resources)

    train_seeds = split_seed_sets[RegionLearningSplit.TRAIN]
    validation_seeds = split_seed_sets[RegionLearningSplit.VALIDATION]
    test_seeds = split_seed_sets[RegionLearningSplit.TEST]
    all_dataset_seeds = train_seeds | validation_seeds | test_seeds
    holdouts = set(resolved_config.final_holdout_seeds)
    split_disjoint = not (
        train_seeds & validation_seeds
        or train_seeds & test_seeds
        or validation_seeds & test_seeds
    )
    numeric_seed_atomic = all(len(values) == 1 for values in numeric_seed_splits.values())
    scenario_seed_atomic = all(
        len(values) == 1 for values in scenario_seed_splits.values()
    )
    external_holdout_absent_from_train = not bool(holdouts & train_seeds)
    external_holdout_absent_from_dataset = not bool(holdouts & all_dataset_seeds)
    development_test_gate_met = (
        len(test_seeds) >= resolved_config.minimum_development_test_seeds
    )
    internal_test_meets_final_gate = (
        len(test_seeds) >= resolved_config.minimum_final_holdout_seeds
    )

    verification = {
        "manifest_schema_verified": manifest.schema
        == "d4-region-learning-dataset-v1",
        "dataset_content_sha256_verified": manifest.dataset_id
        == f"d4-region-learning-dataset-{manifest.dataset_sha256}",
        "manifest_file_sha256_verified_on_read": bool(manifest_file_sha256),
        "episode_sha256_verified": episode_sha_verified_count
        == manifest.availability.episode_count,
        "episode_schema_verified": observed_frame_schemas
        == {REGION_LEARNING_FRAME_SCHEMA},
        "source_schema_verified": observed_source_schemas
        == {REGION_LEARNING_SOURCE_SCHEMA},
        "episode_identity_unique": len(episode_ids)
        == manifest.availability.episode_count,
        "source_identity_unique": len(source_identities)
        == manifest.availability.episode_count,
        "split_seed_sets_disjoint": split_disjoint,
        "numeric_seed_atomic": numeric_seed_atomic,
        "scenario_seed_atomic": scenario_seed_atomic,
        "train_validation_test_leakage_absent": split_disjoint
        and numeric_seed_atomic
        and scenario_seed_atomic,
        "external_holdout_absent_from_train": external_holdout_absent_from_train,
        "external_holdout_absent_from_dataset": external_holdout_absent_from_dataset,
        "dirty_source_absent": manifest.availability.dirty_episode_count == 0,
    }
    violations = tuple(sorted(key for key, value in verification.items() if not value))
    warnings: list[str] = []
    if manifest.availability.reward_available_count == 0:
        warnings.append("reward_unavailable_for_all_frames")
    if not internal_test_meets_final_gate:
        warnings.append("internal_test_below_twenty_seed_final_assist_gate")
    warnings.append("external_holdout_evaluation_not_completed")

    report = {
        "schema": D4_DATA_READINESS_SCHEMA,
        "audited_at_utc": _utc_now(),
        "dataset_root": str(root),
        "manifest_file": str(manifest_path),
        "manifest_file_sha256": manifest_file_sha256,
        "dataset_schema": manifest.schema,
        "dataset_id": manifest.dataset_id,
        "dataset_sha256": manifest.dataset_sha256,
        "dataset_created_at_utc": manifest.created_at_utc,
        "source_identity": {
            "git_commits": sorted(git_commits),
            "git_dirty_episode_count": manifest.availability.dirty_episode_count,
            "unique_episode_ids": len(episode_ids),
            "unique_source_identity_sha256": len(source_identities),
            "unique_config_sha256": len(config_hashes),
        },
        "inventory": {
            "episode_count": manifest.availability.episode_count,
            "frame_count": manifest.availability.frame_count,
            "scenario_count": len(scenario_ids),
            "scenario_scale_count": len(scenario_scales),
            "scenario_scales": sorted(scenario_scales),
            "episode_sha256_verified_count": episode_sha_verified_count,
            "target_available_count": manifest.availability.target_available_count,
            "target_unavailable_count": manifest.availability.target_unavailable_count,
            "recommendation_available_count": (
                manifest.availability.recommendation_available_count
            ),
            "reward_available_count": manifest.availability.reward_available_count,
            "reward_unavailable_count": manifest.availability.reward_unavailable_count,
        },
        "split": {
            "algorithm": manifest.split.algorithm,
            "split_seed": manifest.split.split_seed,
            "split_sha256": manifest.split.split_sha256,
            "train_fraction": manifest.split.train_fraction,
            "validation_fraction": manifest.split.validation_fraction,
            "unique_seed_count": manifest.split.unique_seed_count,
            "unseen_seed_count": manifest.split.unseen_seed_count,
            "train_seed_count": len(train_seeds),
            "validation_seed_count": len(validation_seeds),
            "internal_test_seed_count": len(test_seeds),
            "train_episode_count": split_episode_counts["train"],
            "validation_episode_count": split_episode_counts["validation"],
            "internal_test_episode_count": split_episode_counts["test"],
            "train_frame_count": split_frame_counts["train"],
            "validation_frame_count": split_frame_counts["validation"],
            "internal_test_frame_count": split_frame_counts["test"],
            "scenario_seed_group_counts": {
                name: len(groups) for name, groups in split_scenario_groups.items()
            },
            "development_test_gate": {
                "minimum_seed_count": resolved_config.minimum_development_test_seeds,
                "observed_seed_count": len(test_seeds),
                "met": development_test_gate_met,
            },
            "final_assist_internal_test_gate": {
                "minimum_seed_count": resolved_config.minimum_final_holdout_seeds,
                "observed_seed_count": len(test_seeds),
                "met": internal_test_meets_final_gate,
            },
        },
        "external_holdout": {
            "required_seeds": list(resolved_config.final_holdout_seeds),
            "required_seed_count": resolved_config.minimum_final_holdout_seeds,
            "present_in_training": sorted(holdouts & train_seeds),
            "present_anywhere_in_dataset": sorted(holdouts & all_dataset_seeds),
            "evaluation_completed": False,
        },
        "scale_coverage": {
            split: _range_summary(
                split_node_counts[split],
                split_edge_counts[split],
                split_resource_counts[split],
            )
            for split in ("train", "validation", "test")
        },
        "target_action_inventory": {
            split.value: _target_action_inventory(loaded, split)
            for split in RegionLearningSplit
        },
        "verification": verification,
        "violations": list(violations),
        "warnings": sorted(set(warnings)),
        "readiness": {
            "behavior_cloning_development_available": bool(
                manifest.availability.behavior_cloning_available
                and development_test_gate_met
                and not violations
            ),
            "pipeline_usable": bool(
                manifest.availability.behavior_cloning_available
                and development_test_gate_met
                and not violations
            ),
            "ppo_available": False,
            "assist_available": False,
            "strategy_capability_claim_allowed": False,
            "reason": "pipeline_usable_but_action_diversity_insufficient_shadow_only",
        },
    }
    inventories = report["target_action_inventory"]
    if all(
        inventory["resource_quota_nonzero_count"] == 0
        and inventory["transfer_count"] == 0
        for inventory in inventories.values()
    ):
        report["warnings"].append("resource_reallocation_targets_absent")
    if all(
        inventory["hold_true_count"] == 0
        and inventory["request_replan_true_count"] == 0
        for inventory in inventories.values()
    ):
        report["warnings"].append("hold_and_replan_positive_targets_absent")
    report["warnings"] = sorted(set(report["warnings"]))
    action_inventory = _aggregate_target_action_inventory(inventories)
    action_diversity_sufficient = all(
        action_inventory[name] > 0
        for name in (
            "resource_quota_nonzero_count",
            "transfer_count",
            "hold_true_count",
            "request_replan_true_count",
        )
    )
    report["target_action_inventory_total"] = action_inventory
    report["readiness"]["action_diversity_sufficient"] = (
        action_diversity_sufficient
    )
    report["readiness"]["full_action_learning_available"] = (
        action_diversity_sufficient
    )
    report["readiness"]["reason"] = (
        "development_pipeline_available_but_reward_and_holdout_evidence_unavailable"
        if action_diversity_sufficient
        else "pipeline_usable_but_action_diversity_insufficient_shadow_only"
    )
    if violations:
        raise RegionBehaviorCloningError(
            "D4 dataset audit failed: " + ",".join(violations)
        )
    if not report["readiness"]["behavior_cloning_development_available"]:
        raise RegionBehaviorCloningError("D4 behavior-cloning development gate failed")
    return loaded, report


def train_region_behavior_cloning(
    dataset_root: str | Path,
    output_dir: str | Path,
    *,
    config: RegionBehaviorCloningConfig | None = None,
    replace_output: bool = False,
) -> dict[str, Any]:
    """Train and atomically publish one development/shadow-only model bundle."""

    _require_torch()
    resolved_config = config or RegionBehaviorCloningConfig()
    dataset_path = Path(dataset_root).resolve()
    destination = Path(output_dir).resolve()
    if destination == dataset_path or dataset_path in destination.parents:
        raise RegionBehaviorCloningError("training output must not be inside the dataset")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not replace_output:
        raise RegionBehaviorCloningError(f"training output already exists: {destination}")

    loaded, data_readiness = audit_region_learning_dataset(
        dataset_path,
        config=resolved_config,
    )
    manifest_sha_before = _sha256_file(dataset_path / "manifest.json")
    d6_audit = _validate_d6_audit(resolved_config, data_readiness)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
    )
    started = perf_counter()
    try:
        config_payload = resolved_config.to_dict()
        config_payload["dataset_sha256"] = loaded.manifest.dataset_sha256
        config_payload["dataset_split_sha256"] = loaded.manifest.split.split_sha256
        config_sha256 = _sha256_json(config_payload)
        config_payload["config_sha256"] = config_sha256
        _write_json(staging / "training_config.json", config_payload)
        _write_json(staging / "data_readiness.json", data_readiness)

        _seed_training(resolved_config)
        device = _resolve_device(resolved_config.device)
        train_samples = load_region_behavior_cloning_samples(
            loaded, split=RegionLearningSplit.TRAIN, device=device
        )
        validation_samples = load_region_behavior_cloning_samples(
            loaded, split=RegionLearningSplit.VALIDATION, device=device
        )
        model = SharedRegionGraphActorCritic(
            hidden_dim=resolved_config.hidden_dim,
            message_passing_steps=resolved_config.message_passing_steps,
        ).to(device)
        optimizer = torch.optim.Adam(
            model.parameters(),
            lr=resolved_config.learning_rate,
            weight_decay=resolved_config.weight_decay,
        )
        generator = torch.Generator(device="cpu")
        generator.manual_seed(resolved_config.random_seed)
        best_validation_loss = float("inf")
        best_epoch = 0
        best_state: dict[str, Any] | None = None
        epochs_without_improvement = 0
        history: list[dict[str, Any]] = []
        training_started = perf_counter()

        for epoch in range(1, resolved_config.epochs + 1):
            model.train()
            order = torch.randperm(len(train_samples), generator=generator).tolist()
            weighted_loss = 0.0
            for offset in range(0, len(order), resolved_config.batch_size):
                indices = order[offset : offset + resolved_config.batch_size]
                batch = tuple(train_samples[index] for index in indices)
                loss = behavior_cloning_step(
                    model,
                    optimizer,
                    batch,
                    max_grad_norm=resolved_config.max_grad_norm,
                )
                weighted_loss += loss * len(batch)
            train_loss = weighted_loss / len(train_samples)
            validation_loss = _mean_bc_loss(model, validation_samples)
            history.append(
                {
                    "epoch": epoch,
                    "train_loss": train_loss,
                    "validation_loss": validation_loss,
                }
            )
            if validation_loss < best_validation_loss - 1.0e-9:
                best_validation_loss = validation_loss
                best_epoch = epoch
                best_state = {
                    key: value.detach().cpu().clone()
                    for key, value in model.state_dict().items()
                }
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1
                if epochs_without_improvement >= resolved_config.early_stopping_patience:
                    break

        if best_state is None:
            raise RegionBehaviorCloningError("training produced no finite checkpoint")
        model.load_state_dict(best_state, strict=True)
        model.to(device)
        model.eval()
        training_duration_s = perf_counter() - training_started

        admission_reasons = [
            "development_bundle",
            "reward_evidence_unavailable",
            "final_holdout_not_completed",
            "shadow_validation_pending",
            "confidence_head_uncalibrated",
        ]
        if d6_audit is not None:
            admission_reasons.append("causal_attribution_unavailable")
            if not d6_audit["artifact_bound"]:
                admission_reasons.append("d6_audit_artifact_binding_pending")
        if not data_readiness["readiness"]["full_action_learning_available"]:
            admission_reasons.extend(
                (
                    "action_diversity_insufficient",
                    "resource_reallocation_targets_absent",
                    "hold_replan_positive_targets_absent",
                    "strategy_capability_not_demonstrated",
                )
            )
        action_inventory = data_readiness["target_action_inventory_total"]
        action_diversity_sufficient = data_readiness["readiness"][
            "action_diversity_sufficient"
        ]
        bundle_dir = staging / "bundle"
        bundle_manifest = save_region_resource_model_bundle(
            model,
            bundle_dir,
            model_version=resolved_config.model_version,
            training_graphs=tuple(sample.graph for sample in train_samples),
            created_at_utc=_utc_now(),
            training_dataset_manifest=loaded.manifest,
            lifecycle_stage=MODEL_LIFECYCLE_DEVELOPMENT,
            maximum_advisor_mode=MODEL_MAXIMUM_MODE_SHADOW,
            reward_evidence_available=False,
            final_holdout_seed_count=0,
            action_diversity_sufficient=action_diversity_sufficient,
            strategy_capability_claim_allowed=False,
            target_action_inventory=action_inventory,
            admission_reasons=tuple(admission_reasons),
        )
        loaded_bundle = load_region_resource_model_bundle(
            bundle_dir,
            expected_model_version=resolved_config.model_version,
            expected_state_dict_sha256=bundle_manifest.state_dict_sha256,
            map_location=device,
            require_training_dataset_manifest=True,
        )

        split_metrics = {
            split.value: _evaluate_split(
                loaded,
                split,
                loaded_bundle.model,
                loaded_bundle.manifest,
                device=device,
            )
            for split in RegionLearningSplit
        }
        training_metrics = {
            "schema": D4_TRAINING_METRICS_SCHEMA,
            "model_version": resolved_config.model_version,
            "random_seed": resolved_config.random_seed,
            "device": str(device),
            "epoch_limit": resolved_config.epochs,
            "epochs_completed": len(history),
            "best_epoch": best_epoch,
            "best_validation_loss": best_validation_loss,
            "early_stopped": len(history) < resolved_config.epochs,
            "training_duration_s": training_duration_s,
            "history": history,
            "splits": split_metrics,
        }
        _write_json(staging / "training_metrics.json", training_metrics)

        model_readiness = {
            "schema": D4_MODEL_READINESS_SCHEMA,
            "assessed_at_utc": _utc_now(),
            "model_version": bundle_manifest.model_version,
            "state_dict_sha256": bundle_manifest.state_dict_sha256,
            "training_config_sha256": config_sha256,
            "training_dataset_sha256": loaded.manifest.dataset_sha256,
            "training_split_sha256": loaded.manifest.split.split_sha256,
            "lifecycle_stage": bundle_manifest.lifecycle_stage,
            "maximum_advisor_mode": bundle_manifest.maximum_advisor_mode,
            "development_training_completed": True,
            "development_test_seed_count": len(loaded.manifest.split.test_seeds),
            "development_test_gate_met": (
                len(loaded.manifest.split.test_seeds)
                >= resolved_config.minimum_development_test_seeds
            ),
            "reward_evidence_available": False,
            "ppo_available": False,
            "final_holdout_required_seed_count": (
                resolved_config.minimum_final_holdout_seeds
            ),
            "final_holdout_evaluated_seed_count": 0,
            "final_holdout_evaluation_completed": False,
            "shadow_only": True,
            "assist_eligible": False,
            "pipeline_usable": True,
            "action_diversity_sufficient": (
                bundle_manifest.action_diversity_sufficient
            ),
            "strategy_capability_claim_allowed": (
                bundle_manifest.strategy_capability_claim_allowed
            ),
            "low_loss_is_strategy_capability_evidence": False,
            "target_action_inventory": dict(
                bundle_manifest.target_action_inventory
            ),
            "formal_state_machine_unchanged": True,
            "deterministic_projector_required": True,
            "rule_fallback_required": True,
            "full_action_learning_available": data_readiness["readiness"][
                "full_action_learning_available"
            ],
            "confidence_calibrated": False,
            "external_d6_audit": d6_audit,
            "admission_reasons": list(bundle_manifest.admission_reasons),
            "d6_or_producer_required_fields": [
                "episode_outcome_availability",
                "episode_terminal_outcome",
                "physical_intercept_result",
                "high_threat_backlog_trajectory",
                "resource_transfer_completion",
                "plan_churn_count",
                "communication_load_and_delivery_ack",
                "fail_closed_and_safety_violation_counts",
                "coalition_commit_and_member_ack_outcomes",
                "owner_epoch_lease_plan_version_validity",
                "counterfactual_or_paired_baseline_identity",
                "reward_formula_version_and_normalization",
                "final_holdout_seed_identity_1000_1019",
            ],
        }
        _write_json(staging / "model_readiness.json", model_readiness)
        (staging / "TRAINING_REPORT_CN.md").write_text(
            _render_training_report(data_readiness, training_metrics, model_readiness),
            encoding="utf-8",
        )

        if _sha256_file(dataset_path / "manifest.json") != manifest_sha_before:
            raise RegionBehaviorCloningError("source dataset manifest changed during training")
        artifact_manifest = _artifact_manifest(staging)
        _write_json(staging / "artifact_manifest.json", artifact_manifest)
        if destination.exists():
            if not replace_output:
                raise RegionBehaviorCloningError(
                    f"training output appeared during run: {destination}"
                )
            shutil.rmtree(destination)
        os.replace(staging, destination)
        return {
            "output_dir": str(destination),
            "data_readiness": data_readiness,
            "training_metrics": training_metrics,
            "model_readiness": model_readiness,
            "artifact_manifest": artifact_manifest,
            "total_duration_s": perf_counter() - started,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def publish_region_behavior_cloning_results(
    run_output_dir: str | Path,
    tracked_results_dir: str | Path,
    *,
    bundle_locator: str,
    training_command: str,
    replace_output: bool = False,
) -> dict[str, Any]:
    """Publish text-only evidence while keeping model weights in ignored storage."""

    source = Path(run_output_dir).resolve()
    destination = Path(tracked_results_dir).resolve()
    locator = Path(bundle_locator)
    if locator.is_absolute() or ".." in locator.parts or not locator.parts:
        raise RegionBehaviorCloningError(
            "bundle_locator must be a non-empty repository-relative path"
        )
    required = (
        "data_readiness.json",
        "training_config.json",
        "training_metrics.json",
        "model_readiness.json",
        "TRAINING_REPORT_CN.md",
    )
    missing = [name for name in required if not (source / name).is_file()]
    if missing:
        raise RegionBehaviorCloningError(
            "training evidence is incomplete: " + ",".join(missing)
        )
    if destination.exists() and not replace_output:
        raise RegionBehaviorCloningError(
            f"tracked training results already exist: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
    )
    try:
        for name in required:
            shutil.copy2(source / name, staging / name)
        readiness = json.loads(
            (source / "model_readiness.json").read_text(encoding="utf-8")
        )
        (staging / "TRAINING_COMMAND.md").write_text(
            "# D4 行为克隆训练命令\n\n"
            "```bash\n"
            + training_command.strip()
            + "\n```\n",
            encoding="utf-8",
        )
        (staging / "LOCAL_BUNDLE_LOCATION.md").write_text(
            "# D4 模型本地定位\n\n"
            f"- 本地运行目录：`{locator.as_posix()}`\n"
            f"- 本地模型包：`{(locator / 'bundle').as_posix()}`\n"
            f"- 模型版本：`{readiness['model_version']}`\n"
            f"- 权重 SHA256：`{readiness['state_dict_sha256']}`\n"
            "- 准入状态：管线可用但动作多样性不足，开发模型仅影子运行。\n"
            "- 能力口径：低损失不能作为调度策略能力证据。\n"
            "- 权重文件位于 Git 忽略目录，当前未使用 Git LFS，不进入普通 Git 提交。\n",
            encoding="utf-8",
        )
        files = []
        for path in sorted(item for item in staging.iterdir() if item.is_file()):
            if path.suffix in {".pt", ".pth", ".ckpt"}:
                raise RegionBehaviorCloningError(
                    "tracked result set must not contain model weights"
                )
            files.append(
                {
                    "relative_path": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
        manifest = {
            "schema": D4_TRACKED_RESULTS_SCHEMA,
            "created_at_utc": _utc_now(),
            "model_version": readiness["model_version"],
            "state_dict_sha256": readiness["state_dict_sha256"],
            "training_config_sha256": readiness["training_config_sha256"],
            "training_dataset_sha256": readiness["training_dataset_sha256"],
            "training_split_sha256": readiness["training_split_sha256"],
            "local_bundle_locator": (locator / "bundle").as_posix(),
            "weights_tracked_by_git": False,
            "git_lfs_available": False,
            "files": files,
        }
        _write_json(staging / "manifest.json", manifest)
        if destination.exists():
            if not replace_output:
                raise RegionBehaviorCloningError(
                    f"tracked output appeared during publish: {destination}"
                )
            shutil.rmtree(destination)
        os.replace(staging, destination)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _evaluate_split(
    loaded: LoadedRegionLearningDataset,
    split: RegionLearningSplit,
    model: Any,
    model_manifest: Any,
    *,
    device: Any,
) -> dict[str, Any]:
    model.eval()
    policy = LearnedRegionResourcePolicy(model, model_manifest)
    projector = DeterministicResourceProjector()
    target_inventory = _target_action_inventory(loaded, split)
    losses: list[float] = []
    quota_errors: list[float] = []
    reserve_errors: list[float] = []
    reconnaissance_errors: list[float] = []
    transfer_errors: list[float] = []
    hold_correct = 0
    replan_correct = 0
    hold_confusion = {"true_positive": 0, "true_negative": 0, "false_positive": 0, "false_negative": 0}
    replan_confusion = {"true_positive": 0, "true_negative": 0, "false_positive": 0, "false_negative": 0}
    action_count = 0
    quota_exact = 0
    transfer_exact = 0
    transfer_field_count = 0
    version_checks = {
        "owner": [0, 0],
        "plan_id": [0, 0],
        "plan_version": [0, 0],
        "epoch": [0, 0],
        "lease": [0, 0],
    }
    resource_conservation = [0, 0]
    communication_adjacency = [0, 0]
    projection_rejection_frames = 0
    projection_rejection_counts: dict[str, int] = {}
    inference_latency_ms: list[float] = []
    confidence_values: list[float] = []
    scale_latency: dict[str, list[float]] = {}
    scale_frames: dict[str, int] = {}
    scale_nodes: dict[str, list[int]] = {}
    scale_edges: dict[str, list[int]] = {}

    with torch.no_grad():
        for episode in loaded.episodes(split):
            scale = episode.source.scenario_scale or "unspecified"
            for frame in episode.frames:
                snapshot = frame.snapshot
                target_recommendation = frame.target.recommendation
                if (
                    frame.target.availability != RegionLearningAvailability.AVAILABLE
                    or target_recommendation is None
                ):
                    raise RegionBehaviorCloningError("available BC split lost a target")
                graph = snapshot_to_region_graph(snapshot, device=device)
                target = recommendation_to_policy_target(
                    snapshot, graph, target_recommendation
                )
                output = model(graph)
                losses.append(float(behavior_cloning_loss(model, graph, target).cpu()))

                started = perf_counter()
                raw = policy.recommend_raw(snapshot)
                projected = projector.project(snapshot, raw)
                latency_ms = (perf_counter() - started) * 1000.0
                inference_latency_ms.append(latency_ms)
                scale_latency.setdefault(scale, []).append(latency_ms)
                scale_frames[scale] = scale_frames.get(scale, 0) + 1
                scale_nodes.setdefault(scale, []).append(snapshot.region_count)
                scale_edges.setdefault(scale, []).append(len(snapshot.edges))
                confidence_values.append(raw.confidence)

                if projected.projection_rejections:
                    projection_rejection_frames += 1
                    for reason in projected.projection_rejections:
                        projection_rejection_counts[reason] = (
                            projection_rejection_counts.get(reason, 0) + 1
                        )
                resource_conservation[1] += 1
                resource_conservation[0] += int(projected.total_quota_delta == 0)

                predicted_actions = {
                    action.region_id: action for action in projected.actions
                }
                target_actions = {
                    action.region_id: action for action in target_recommendation.actions
                }
                for region_id, target_action in target_actions.items():
                    predicted = predicted_actions[region_id]
                    node = snapshot.region_by_id[region_id]
                    action_count += 1
                    error = abs(
                        predicted.resource_quota_delta
                        - target_action.resource_quota_delta
                    )
                    quota_errors.append(float(error))
                    quota_exact += int(error == 0)
                    reserve_errors.append(
                        abs(predicted.reserve_ratio - target_action.reserve_ratio)
                    )
                    reconnaissance_errors.append(
                        abs(
                            predicted.reconnaissance_priority
                            - target_action.reconnaissance_priority
                        )
                    )
                    hold_correct += int(predicted.hold == target_action.hold)
                    replan_correct += int(
                        predicted.request_replan == target_action.request_replan
                    )
                    _update_binary_confusion(
                        hold_confusion,
                        predicted=predicted.hold,
                        target=target_action.hold,
                    )
                    _update_binary_confusion(
                        replan_confusion,
                        predicted=predicted.request_replan,
                        target=target_action.request_replan,
                    )
                    checks = {
                        "owner": (
                            predicted.expected_owner_id == node.current_owner_id
                            and predicted.expected_owner_layer
                            == node.current_owner_layer
                        ),
                        "plan_id": predicted.expected_plan_id == node.plan_id,
                        "plan_version": (
                            predicted.expected_plan_version == node.plan_version
                        ),
                        "epoch": predicted.expected_epoch == node.epoch,
                        "lease": (
                            predicted.expected_lease_expires_at_s
                            == node.lease_expires_at_s
                        ),
                    }
                    for key, passed in checks.items():
                        version_checks[key][0] += int(passed)
                        version_checks[key][1] += 1

                target_transfers = {
                    (item.edge_id, item.source_region_id, item.target_region_id): (
                        item.resource_count
                    )
                    for item in target_recommendation.transfers
                }
                predicted_transfers = {
                    (item.edge_id, item.source_region_id, item.target_region_id): (
                        item.resource_count
                    )
                    for item in projected.transfers
                }
                graph_transfer_keys = {
                    (edge.edge_id, edge.source_region_id, edge.target_region_id)
                    for edge in graph.edge_refs
                }
                for key in graph_transfer_keys:
                    error = abs(
                        predicted_transfers.get(key, 0)
                        - target_transfers.get(key, 0)
                    )
                    transfer_errors.append(float(error))
                    transfer_exact += int(error == 0)
                    transfer_field_count += 1

                edges = {edge.edge_id: edge for edge in snapshot.edges}
                for transfer in projected.transfers:
                    communication_adjacency[1] += 1
                    edge = edges.get(transfer.edge_id)
                    communication_adjacency[0] += int(
                        edge is not None
                        and edge.permits(
                            transfer.source_region_id, transfer.target_region_id
                        )
                        and edge.open_for_transfer
                        and transfer.resource_count <= edge.transferable_resources
                    )

    frame_count = len(losses)
    return {
        "split": split.value,
        "episode_count": len(loaded.episodes(split)),
        "frame_count": frame_count,
        "unique_seed_count": len(
            {episode.source.seed for episode in loaded.episodes(split)}
        ),
        "behavior_cloning_loss": _distribution(losses),
        "action_fields": {
            "resource_quota_delta_mae": _mean(quota_errors),
            "resource_quota_delta_exact_accuracy": _rate(
                quota_exact, action_count
            ),
            "resource_quota_delta_target_nonzero_count": target_inventory[
                "resource_quota_nonzero_count"
            ],
            "resource_quota_delta_metric_informative": target_inventory[
                "resource_quota_nonzero_count"
            ]
            > 0,
            "reserve_ratio_mae": _mean(reserve_errors),
            "reconnaissance_priority_mae": _mean(reconnaissance_errors),
            "hold_accuracy": _rate(hold_correct, action_count),
            "hold_classification": _binary_metrics(hold_confusion),
            "request_replan_accuracy": _rate(replan_correct, action_count),
            "request_replan_classification": _binary_metrics(replan_confusion),
            "transfer_resource_count_mae": _mean(transfer_errors),
            "transfer_resource_count_exact_accuracy": _rate(
                transfer_exact, transfer_field_count
            ),
            "transfer_target_nonzero_count": target_inventory["transfer_count"],
            "transfer_metric_informative": target_inventory["transfer_count"] > 0,
            "action_count": action_count,
            "directed_edge_action_count": transfer_field_count,
        },
        "safety_projection": {
            "projection_rejection_frame_count": projection_rejection_frames,
            "projection_rejection_frame_rate": _rate(
                projection_rejection_frames, frame_count
            ),
            "projection_rejection_counts": dict(
                sorted(projection_rejection_counts.items())
            ),
            "resource_conservation_rate": _rate(*resource_conservation),
            "communication_adjacency": {
                "available": communication_adjacency[1] > 0,
                "valid_count": communication_adjacency[0],
                "checked_count": communication_adjacency[1],
                "valid_rate": (
                    _rate(*communication_adjacency)
                    if communication_adjacency[1]
                    else None
                ),
            },
            "authority_consistency_rates": {
                key: _rate(values[0], values[1])
                for key, values in version_checks.items()
            },
        },
        "model_confidence": _distribution(confidence_values),
        "inference_latency_ms": _distribution(inference_latency_ms),
        "scale_coverage": {
            scale: {
                "frame_count": scale_frames[scale],
                "region_count_min": min(scale_nodes[scale]),
                "region_count_max": max(scale_nodes[scale]),
                "edge_count_min": min(scale_edges[scale]),
                "edge_count_max": max(scale_edges[scale]),
                "inference_latency_ms": _distribution(scale_latency[scale]),
            }
            for scale in sorted(scale_frames)
        },
    }


def _mean_bc_loss(model: Any, samples: Sequence[Any]) -> float:
    model.eval()
    values: list[float] = []
    with torch.no_grad():
        for sample in samples:
            values.append(float(behavior_cloning_loss(model, sample.graph, sample.target).cpu()))
    if not values or not all(isfinite(value) for value in values):
        raise RegionBehaviorCloningError("validation loss is empty or non-finite")
    return sum(values) / len(values)


def _target_action_inventory(
    loaded: LoadedRegionLearningDataset,
    split: RegionLearningSplit,
) -> dict[str, Any]:
    action_count = 0
    quota_nonzero = 0
    hold_true = 0
    replan_true = 0
    transfer_count = 0
    transfer_resource_count = 0
    transfer_frame_count = 0
    reserve_values: set[float] = set()
    reconnaissance_values: set[float] = set()
    for episode in loaded.episodes(split):
        for frame in episode.frames:
            recommendation = frame.target.recommendation
            if recommendation is None:
                continue
            transfer_count += len(recommendation.transfers)
            transfer_resource_count += sum(
                transfer.resource_count for transfer in recommendation.transfers
            )
            transfer_frame_count += int(bool(recommendation.transfers))
            for action in recommendation.actions:
                action_count += 1
                quota_nonzero += int(action.resource_quota_delta != 0)
                hold_true += int(action.hold)
                replan_true += int(action.request_replan)
                reserve_values.add(float(action.reserve_ratio))
                reconnaissance_values.add(float(action.reconnaissance_priority))
    return {
        "action_count": action_count,
        "resource_quota_nonzero_count": quota_nonzero,
        "resource_quota_nonzero_rate": _rate(quota_nonzero, action_count),
        "hold_true_count": hold_true,
        "hold_true_rate": _rate(hold_true, action_count),
        "request_replan_true_count": replan_true,
        "request_replan_true_rate": _rate(replan_true, action_count),
        "transfer_count": transfer_count,
        "transfer_resource_count": transfer_resource_count,
        "transfer_frame_count": transfer_frame_count,
        "reserve_ratio_unique_count": len(reserve_values),
        "reserve_ratio_min": min(reserve_values),
        "reserve_ratio_max": max(reserve_values),
        "reconnaissance_priority_unique_count": len(reconnaissance_values),
        "reconnaissance_priority_min": min(reconnaissance_values),
        "reconnaissance_priority_max": max(reconnaissance_values),
    }


def _aggregate_target_action_inventory(
    inventories: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    fields = (
        "action_count",
        "resource_quota_nonzero_count",
        "transfer_count",
        "hold_true_count",
        "request_replan_true_count",
    )
    return {
        field: sum(int(inventory[field]) for inventory in inventories.values())
        for field in fields
    }


def _update_binary_confusion(
    counts: dict[str, int],
    *,
    predicted: bool,
    target: bool,
) -> None:
    if predicted and target:
        counts["true_positive"] += 1
    elif not predicted and not target:
        counts["true_negative"] += 1
    elif predicted:
        counts["false_positive"] += 1
    else:
        counts["false_negative"] += 1


def _binary_metrics(counts: Mapping[str, int]) -> dict[str, Any]:
    true_positive = int(counts["true_positive"])
    true_negative = int(counts["true_negative"])
    false_positive = int(counts["false_positive"])
    false_negative = int(counts["false_negative"])
    positive_targets = true_positive + false_negative
    negative_targets = true_negative + false_positive
    precision_denominator = true_positive + false_positive
    recall = (
        true_positive / positive_targets if positive_targets else None
    )
    specificity = (
        true_negative / negative_targets if negative_targets else None
    )
    precision = (
        true_positive / precision_denominator if precision_denominator else None
    )
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision is not None
        and recall is not None
        and precision + recall > 0.0
        else None
    )
    balanced_accuracy = (
        (recall + specificity) / 2.0
        if recall is not None and specificity is not None
        else None
    )
    return {
        **{key: int(value) for key, value in counts.items()},
        "positive_target_count": positive_targets,
        "negative_target_count": negative_targets,
        "predicted_positive_count": true_positive + false_positive,
        "accuracy": _rate(
            true_positive + true_negative,
            positive_targets + negative_targets,
        ),
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "balanced_accuracy": balanced_accuracy,
        "both_classes_available": positive_targets > 0 and negative_targets > 0,
    }


def _seed_training(config: RegionBehaviorCloningConfig) -> None:
    random.seed(config.random_seed)
    torch.manual_seed(config.random_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.random_seed)
    torch.set_num_threads(config.torch_num_threads)
    torch.use_deterministic_algorithms(True, warn_only=True)


def _resolve_device(requested: str) -> Any:
    normalized = str(requested).strip().lower()
    if normalized.startswith("cuda") and not torch.cuda.is_available():
        raise RegionBehaviorCloningError("CUDA requested but unavailable")
    return torch.device(normalized)


def _render_training_report(
    data: Mapping[str, Any],
    metrics: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> str:
    split = data["split"]
    lines = [
        "# D4 区域资源行为克隆开发模型报告",
        "",
        "## 结论",
        "",
        (
            "正式数据通过清单、逐 episode 哈希、源身份和数值种子原子划分校验。"
            "本轮完成行为克隆开发模型训练，模型仅允许影子运行。"
        ),
        (
            "当前结论是管线可用但动作多样性不足，准入状态为 shadow-only。"
            "训练或内部测试的低损失只说明对现有退化标签的拟合，不能用来宣称调度策略能力。"
        ),
        (
            "全部帧缺少可验证回报，外部保留种子 1000-1019 尚未执行最终评估。"
            "因此近端策略优化不可用，模型不得进入辅助决策。"
        ),
        "",
        "## 数据审计",
        "",
        f"- episode：{data['inventory']['episode_count']}，帧：{data['inventory']['frame_count']}。",
        (
            f"- 训练/验证/内部测试种子：{split['train_seed_count']}/"
            f"{split['validation_seed_count']}/{split['internal_test_seed_count']}。"
        ),
        (
            f"- 训练/验证/内部测试帧：{split['train_frame_count']}/"
            f"{split['validation_frame_count']}/{split['internal_test_frame_count']}。"
        ),
        f"- 数据集 SHA256：`{data['dataset_sha256']}`。",
        "- 在线真值标识未进入区域图合同；外部保留种子未进入正式数据。",
        (
            f"- 全部 {data['target_action_inventory_total']['action_count']} 个区域动作中，"
            f"非零配额={data['target_action_inventory_total']['resource_quota_nonzero_count']}、"
            f"跨区域转移={data['target_action_inventory_total']['transfer_count']}、"
            f"保持={data['target_action_inventory_total']['hold_true_count']}、"
            f"请求重规划={data['target_action_inventory_total']['request_replan_true_count']}。"
        ),
        "- 配额、转移、保持和重规划指标没有正类支持；相应高准确率或低误差不具备策略判别力。",
        "",
        "## 训练结果",
        "",
        (
            f"固定随机种子 {metrics['random_seed']}，完成 {metrics['epochs_completed']} 个 epoch，"
            f"最佳 epoch 为 {metrics['best_epoch']}，训练耗时 {metrics['training_duration_s']:.2f} 秒。"
        ),
        "",
        "| 划分 | 损失均值 | 配额误差 | 保留比例误差 | 侦察优先级误差 | 保持准确率 | 重规划准确率 | 推理 P95/ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in ("train", "validation", "test"):
        item = metrics["splits"][name]
        action = item["action_fields"]
        lines.append(
            "| "
            + " | ".join(
                (
                    name,
                    f"{item['behavior_cloning_loss']['mean']:.6f}",
                    f"{action['resource_quota_delta_mae']:.4f}",
                    f"{action['reserve_ratio_mae']:.4f}",
                    f"{action['reconnaissance_priority_mae']:.4f}",
                    f"{action['hold_accuracy']:.4f}",
                    f"{action['request_replan_accuracy']:.4f}",
                    f"{item['inference_latency_ms']['p95']:.4f}",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 安全边界",
            "",
            "- 模型只输出区域级建议，确定性投影器继续执行资源守恒、通信邻接、联盟确认和版本租约检查。",
            "- 中心、二级和分布式正式裁决保持原实现，规则策略仍是超时、异常、越界和低置信度时的回退路径。",
            "- 置信度头未获得校准标签，当前置信度数值不用于能力结论。",
            f"- 模型状态：`{readiness['lifecycle_stage']}`；最高模式：`{readiness['maximum_advisor_mode']}`。",
            "- bundle admission 明确记录 `action_diversity_sufficient=false` 和 `strategy_capability_claim_allowed=false`。",
            "",
            "## 待补条件",
            "",
            "D6 或数据生产端需提供可审计的任务结果、物理结果、通信确认、安全事件、联盟结果和回报公式版本。",
            "完成外部 20 个保留种子的成对影子评估后，才能重新审查辅助决策准入。",
            "",
        ]
    )
    d6_audit = readiness.get("external_d6_audit")
    if d6_audit is not None:
        lines.extend(
            [
                "## D6 外部审计",
                "",
                (
                    f"D6 审计覆盖 {d6_audit['frame_count']} 帧，其中 "
                    f"{d6_audit['unattributed_transition_frame_count']} 帧仅有无归因相邻状态转移。"
                ),
                (
                    f"回报可用数为 {d6_audit['reward_available_count']}，"
                    f"因果标签可用数为 {d6_audit['causal_label_available_count']}，"
                    f"反事实标签可用数为 {d6_audit['counterfactual_available_count']}。"
                    "该证据只用于限制模型准入，不被转换成训练回报。"
                ),
                (
                    "D6 审计制品尚未提供 SHA256 绑定。"
                    if not d6_audit["artifact_bound"]
                    else f"D6 审计制品 SHA256：`{d6_audit['artifact_sha256']}`。"
                ),
                "",
            ]
        )
    return "\n".join(lines)


def _validate_d6_audit(
    config: RegionBehaviorCloningConfig,
    data_readiness: Mapping[str, Any],
) -> dict[str, Any] | None:
    if config.d6_audit_frame_count is None:
        return None
    frame_count = int(config.d6_audit_frame_count)
    if frame_count != int(data_readiness["inventory"]["frame_count"]):
        raise RegionBehaviorCloningError(
            "D6 audit frame count does not match the D4 dataset"
        )
    unattributed = int(config.d6_unattributed_transition_frame_count or 0)
    if unattributed > frame_count:
        raise RegionBehaviorCloningError(
            "D6 unattributed transition count exceeds frame count"
        )
    reward_count = int(config.d6_reward_available_count or 0)
    causal_count = int(config.d6_causal_label_available_count or 0)
    counterfactual_count = int(config.d6_counterfactual_available_count or 0)
    if max(reward_count, causal_count, counterfactual_count) > frame_count:
        raise RegionBehaviorCloningError("D6 availability count exceeds frame count")
    return {
        "source": "D6 formal dataset audit reported by main",
        "frame_count": frame_count,
        "unattributed_transition_frame_count": unattributed,
        "unattributed_transition_frame_rate": unattributed / frame_count,
        "reward_available_count": reward_count,
        "causal_label_available_count": causal_count,
        "counterfactual_available_count": counterfactual_count,
        "artifact_sha256": config.d6_audit_artifact_sha256,
        "artifact_bound": config.d6_audit_artifact_sha256 is not None,
        "training_reward_derived": False,
    }


def _artifact_manifest(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        files.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return {
        "schema": D4_ARTIFACT_MANIFEST_SCHEMA,
        "created_at_utc": _utc_now(),
        "files": files,
    }


def _range_summary(
    node_counts: Sequence[int],
    edge_counts: Sequence[int],
    resource_counts: Sequence[int],
) -> dict[str, Any]:
    return {
        "frame_count": len(node_counts),
        "region_count_min": min(node_counts),
        "region_count_max": max(node_counts),
        "edge_count_min": min(edge_counts),
        "edge_count_max": max(edge_counts),
        "resource_count_min": min(resource_counts),
        "resource_count_max": max(resource_counts),
    }


def _distribution(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(float(value) for value in values)
    if not ordered or not all(isfinite(value) for value in ordered):
        raise RegionBehaviorCloningError("metric distribution is empty or non-finite")
    return {
        "count": len(ordered),
        "mean": sum(ordered) / len(ordered),
        "min": ordered[0],
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
        "max": ordered[-1],
    }


def _percentile(ordered: Sequence[float], fraction: float) -> float:
    if len(ordered) == 1:
        return float(ordered[0])
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return float(ordered[low] * (1.0 - weight) + ordered[high] * weight)


def _mean(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha256_json(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _require_torch() -> None:
    if torch is None:
        raise RegionBehaviorCloningError("torch is required for D4 behavior cloning")
