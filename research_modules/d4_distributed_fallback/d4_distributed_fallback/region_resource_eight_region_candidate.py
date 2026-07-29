"""Reproducible eight-region D4 shadow-candidate construction.

The runtime corpus supplies the feature geometry.  The supplemental curriculum
supplies only three truth-free action recipes: hold, request-replan, and
resource transfer.  Each recipe is rebuilt on an eight-region runtime graph and
labelled by the existing deterministic rule policy and safety projector.

The resulting candidate is development/shadow only.  This module does not
publish plans, acknowledge runtime consumption, or grant physical authority.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .region_resource import (
    DETERMINISTIC_RESOURCE_PROJECTOR_NAME,
    DETERMINISTIC_RESOURCE_PROJECTOR_VERSION,
    REGION_RESOURCE_FEATURE_SCHEMA,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
)
from .region_resource_current_lineage_candidate import (
    RegionResourceCurrentLineageCandidateConfig,
    RegionResourceCurrentLineagePermissions,
    RegionResourceCurrentLineageSplitUsage,
    _review_validation_outputs,
    _train_candidate,
)
from .region_resource_dataset import (
    REGION_LEARNING_FEATURE_SEMANTICS,
    LoadedRegionLearningDataset,
    LoadedRegionLearningEpisode,
    RegionLearningEpisodeSource,
    RegionLearningFrame,
    RegionLearningReward,
    RegionLearningSplit,
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    load_region_learning_dataset,
    load_region_learning_dataset_splits,
    stage_region_learning_episode,
)
from .region_resource_learning import (
    BehaviorCloningSample,
    EDGE_FEATURE_NAMES,
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    NODE_FEATURE_NAMES,
    SharedRegionGraphActorCritic,
    load_region_behavior_cloning_samples,
    load_region_resource_model_bundle,
    save_region_resource_model_bundle,
)
from .region_resource_isolated_rollout import (
    REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
)

try:
    import torch
except ImportError:  # pragma: no cover - optional dependency guard
    torch = None


REGION_RESOURCE_EIGHT_REGION_CANDIDATE_SCHEMA = (
    "d4-region-resource-eight-region-shadow-candidate-v1"
)
REGION_RESOURCE_EIGHT_REGION_SOURCE_SCHEMA = (
    "d4-region-resource-eight-region-source-v1"
)
REGION_RESOURCE_EIGHT_REGION_VIEW_SCHEMA = (
    "d4-region-resource-eight-region-training-view-v1"
)
REGION_RESOURCE_EIGHT_REGION_TRAINING_SCHEMA = (
    "d4-region-resource-eight-region-training-v1"
)
REGION_RESOURCE_EIGHT_REGION_CONFIG_SCHEMA = (
    "d4-region-resource-eight-region-config-v1"
)
REGION_RESOURCE_EIGHT_REGION_PERMISSIONS_SCHEMA = (
    "d4-region-resource-eight-region-permissions-v1"
)

REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID = (
    "region_resource_a2_8region_runtime_action_shadow_v1"
)
REGION_RESOURCE_EIGHT_REGION_MODEL_VERSION = (
    "d4-region-a2-8region-runtime-action-shadow-v1"
)
REGION_RESOURCE_EIGHT_REGION_CANDIDATE_FILENAME = (
    "eight_region_shadow_candidate_manifest.json"
)
REGION_RESOURCE_EIGHT_REGION_SOURCE_FILENAME = (
    "source_implementation_summary.json"
)
REGION_RESOURCE_EIGHT_REGION_VIEW_FILENAME = "training_view_manifest.json"
REGION_RESOURCE_EIGHT_REGION_CONFIG_FILENAME = "training_config.json"
REGION_RESOURCE_EIGHT_REGION_TRAINING_FILENAME = "training_summary.json"

REGION_RESOURCE_EIGHT_REGION_COUNT = 8
REGION_RESOURCE_EIGHT_REGION_GLOBAL_SPLIT_SEED = 20260728
REGION_RESOURCE_EIGHT_REGION_RESERVED_SEEDS = tuple(range(1000, 1020))
REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS = tuple(range(100))

REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256 = (
    "b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158"
)
REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256 = (
    "7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72"
)
REGION_RESOURCE_EIGHT_REGION_RUNTIME_EPISODE_COUNT = 900
REGION_RESOURCE_EIGHT_REGION_RUNTIME_FRAME_COUNT = 1798
REGION_RESOURCE_EIGHT_REGION_ACTION_EPISODE_COUNT = 100
REGION_RESOURCE_EIGHT_REGION_ACTION_FRAME_COUNT = 300
REGION_RESOURCE_EIGHT_REGION_OVERLAY_FRAME_KINDS = (
    "hold",
    "request_replan",
    "transfer",
)
REGION_RESOURCE_EIGHT_REGION_OVERLAY_SCENARIO_ID = (
    "d4-eight-region-runtime-action-overlay"
)
REGION_RESOURCE_EIGHT_REGION_OVERLAY_SCENARIO_VERSION = "v1"
REGION_RESOURCE_EIGHT_REGION_OVERLAY_REWARD_REASON = (
    "development_action_overlay_has_no_observed_outcome"
)
REGION_RESOURCE_EIGHT_REGION_VIEW_RECIPE = (
    "runtime-eight-region-geometry-plus-curriculum-action-recipe-v1"
)
REGION_RESOURCE_EIGHT_REGION_CONFIDENCE_TARGET = (
    "frozen-action-normalized-error-consistency-score-v1"
)

_EXPECTED_RUNTIME_ACTION_INVENTORY = {
    "action_count": 14384,
    "resource_quota_nonzero_count": 0,
    "transfer_count": 0,
    "hold_true_count": 0,
    "request_replan_true_count": 0,
}
_EXPECTED_CURRICULUM_ACTION_INVENTORY = {
    "action_count": 1200,
    "resource_quota_nonzero_count": 200,
    "transfer_count": 100,
    "hold_true_count": 100,
    "request_replan_true_count": 200,
}
_COMMITTED_TRAINING_IMPLEMENTATION_FILES = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_dataset.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_learning.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_current_lineage_candidate.py",
)
_VIEW_BUILDER_FILE = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_eight_region_candidate.py"
)
_ARTIFACT_FILES = {
    REGION_RESOURCE_EIGHT_REGION_SOURCE_FILENAME,
    REGION_RESOURCE_EIGHT_REGION_VIEW_FILENAME,
    REGION_RESOURCE_EIGHT_REGION_CONFIG_FILENAME,
    REGION_RESOURCE_EIGHT_REGION_TRAINING_FILENAME,
    "bundle/manifest.json",
    "bundle/state_dict.pt",
    "bundle/training_dataset_manifest.json",
}
_FALSE_PERMISSION_FIELDS = (
    "assist_enabled",
    "authority_enabled",
    "assignment_enabled",
    "takeover_enabled",
    "coalition_commit_enabled",
    "control_enabled",
    "runtime_ack_available",
    "physical_permission_available",
    "formal_evaluation_authorized",
    "actual_adoption_claimed",
    "benefit_claimed",
)
_FORBIDDEN_TRUTH_KEYS = {
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


class RegionResourceEightRegionCandidateError(RuntimeError):
    """Fail-closed error for the eight-region candidate boundary."""


@dataclass(frozen=True)
class RegionResourceEightRegionCandidateConfig:
    random_seed: int = 20260728
    hidden_dim: int = 64
    message_passing_steps: int = 2
    epochs: int = 40
    batch_size: int = 32
    learning_rate: float = 8.0e-4
    weight_decay: float = 1.0e-5
    max_grad_norm: float = 1.0
    early_stopping_patience: int = 8
    confidence_epochs: int = 30
    confidence_batch_size: int = 32
    confidence_learning_rate: float = 5.0e-3
    confidence_loss_weight: float = 1.0
    confidence_continuous_tolerance: float = 0.10
    confidence_inconsistent_target_ceiling: float = 0.59
    fixed_minimum_confidence: float = (
        REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE
    )
    device: str = "cpu"
    torch_num_threads: int = 1
    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    split_seed: int = REGION_RESOURCE_EIGHT_REGION_GLOBAL_SPLIT_SEED
    applicable_region_count: int = REGION_RESOURCE_EIGHT_REGION_COUNT
    candidate_id: str = REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID
    model_version: str = REGION_RESOURCE_EIGHT_REGION_MODEL_VERSION
    created_at_utc: str = "2026-07-28T00:00:00Z"
    schema: str = REGION_RESOURCE_EIGHT_REGION_CONFIG_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_EIGHT_REGION_CONFIG_SCHEMA:
            raise ValueError("unsupported eight-region candidate config schema")
        for name in (
            "random_seed",
            "hidden_dim",
            "message_passing_steps",
            "epochs",
            "batch_size",
            "early_stopping_patience",
            "confidence_epochs",
            "confidence_batch_size",
            "torch_num_threads",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.applicable_region_count != REGION_RESOURCE_EIGHT_REGION_COUNT:
            raise ValueError("candidate scope must remain exactly eight regions")
        for name in (
            "confidence_learning_rate",
            "confidence_loss_weight",
            "confidence_continuous_tolerance",
            "confidence_inconsistent_target_ceiling",
            "fixed_minimum_confidence",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.confidence_loss_weight != 1.0:
            raise ValueError("confidence loss weight must remain 1.0")
        if not 0.0 < self.confidence_continuous_tolerance < 1.0:
            raise ValueError(
                "confidence continuous tolerance must be in (0, 1)"
            )
        if (
            self.fixed_minimum_confidence
            != REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE
            or self.fixed_minimum_confidence != 0.60
        ):
            raise ValueError("fixed minimum confidence must remain 0.60")
        if not (
            0.0
            < self.confidence_inconsistent_target_ceiling
            < self.fixed_minimum_confidence
        ):
            raise ValueError(
                "inconsistent confidence target ceiling must remain below 0.60"
            )
        if self.split_seed != REGION_RESOURCE_EIGHT_REGION_GLOBAL_SPLIT_SEED:
            raise ValueError("global split seed changed")
        if (
            self.train_fraction != 0.70
            or self.validation_fraction != 0.15
        ):
            raise ValueError("global split fractions changed")
        if (
            self.candidate_id != REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID
            or self.model_version != REGION_RESOURCE_EIGHT_REGION_MODEL_VERSION
        ):
            raise ValueError("eight-region candidate identity changed")
        if not self.created_at_utc:
            raise ValueError("created_at_utc must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_training_config(
        self,
    ) -> RegionResourceCurrentLineageCandidateConfig:
        return RegionResourceCurrentLineageCandidateConfig(
            random_seed=self.random_seed,
            hidden_dim=self.hidden_dim,
            message_passing_steps=self.message_passing_steps,
            epochs=self.epochs,
            batch_size=self.batch_size,
            learning_rate=self.learning_rate,
            weight_decay=self.weight_decay,
            max_grad_norm=self.max_grad_norm,
            early_stopping_patience=self.early_stopping_patience,
            device=self.device,
            torch_num_threads=self.torch_num_threads,
            model_version=self.model_version,
            candidate_id=self.candidate_id,
            created_at_utc=self.created_at_utc,
        )


@dataclass(frozen=True)
class RegionResourceEightRegionPermissions:
    assist_enabled: bool = False
    authority_enabled: bool = False
    assignment_enabled: bool = False
    takeover_enabled: bool = False
    coalition_commit_enabled: bool = False
    control_enabled: bool = False
    runtime_ack_available: bool = False
    physical_permission_available: bool = False
    formal_evaluation_authorized: bool = False
    actual_adoption_claimed: bool = False
    benefit_claimed: bool = False
    schema: str = REGION_RESOURCE_EIGHT_REGION_PERMISSIONS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_EIGHT_REGION_PERMISSIONS_SCHEMA:
            raise ValueError("unsupported eight-region permission schema")
        for name in _FALSE_PERMISSION_FIELDS:
            value = getattr(self, name)
            if type(value) is not bool or value:
                raise ValueError("eight-region development candidate grants no permission")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceEightRegionPermissions":
        _require_exact_keys(value, cls.__dataclass_fields__, "permissions")
        return cls(**dict(value))


@dataclass(frozen=True)
class _ConfidenceTargetRecord:
    target_score: float
    normalized_action_error: float
    action_consistent: bool
    quota_error: float
    reserve_error: float
    reconnaissance_error: float
    binary_mismatch_rate: float
    transfer_error: float


def _confidence_supervision_definition(
    config: RegionResourceEightRegionCandidateConfig,
) -> dict[str, Any]:
    return _confidence_supervision_definition_from_values(
        confidence_epochs=config.confidence_epochs,
        confidence_batch_size=config.confidence_batch_size,
        confidence_learning_rate=config.confidence_learning_rate,
        confidence_loss_weight=config.confidence_loss_weight,
        continuous_tolerance=config.confidence_continuous_tolerance,
        inconsistent_target_ceiling=(
            config.confidence_inconsistent_target_ceiling
        ),
        fixed_minimum_confidence=config.fixed_minimum_confidence,
    )


def _confidence_supervision_definition_from_values(
    *,
    confidence_epochs: int,
    confidence_batch_size: int,
    confidence_learning_rate: float,
    confidence_loss_weight: float,
    continuous_tolerance: float,
    inconsistent_target_ceiling: float,
    fixed_minimum_confidence: float,
) -> dict[str, Any]:
    payload = {
        "target_name": REGION_RESOURCE_EIGHT_REGION_CONFIDENCE_TARGET,
        "target_source": (
            "frozen_action_model_error_against_deterministic_rule_and_"
            "safety_projected_training_label"
        ),
        "normalized_error_components": [
            "quota_fraction_absolute_error",
            "reserve_ratio_absolute_error",
            "reconnaissance_priority_absolute_error",
            "hold_replan_binary_mismatch_rate",
            "transfer_fraction_absolute_error",
        ],
        "component_weights": {
            "quota": 0.20,
            "reserve": 0.20,
            "reconnaissance": 0.20,
            "hold_replan": 0.20,
            "transfer": 0.20,
        },
        "continuous_tolerance": float(continuous_tolerance),
        "action_consistency_condition": (
            "quota/reserve/reconnaissance absolute error <= tolerance; "
            "hold and request-replan bits exact; decoded transfer counts exact"
        ),
        "consistent_target_formula": (
            "clip(1 - mean(normalized_action_error_components), 0, 1)"
        ),
        "inconsistent_target_formula": (
            "min(consistent_target_formula, inconsistent_target_ceiling)"
        ),
        "inconsistent_target_ceiling": float(
            inconsistent_target_ceiling
        ),
        "fixed_minimum_confidence": float(fixed_minimum_confidence),
        "fit_split": RegionLearningSplit.TRAIN.value,
        "audit_split": RegionLearningSplit.VALIDATION.value,
        "test_split_use_count": 0,
        "reserved_evaluation_seed_use_count": 0,
        "action_model_frozen_during_fit": True,
        "fit_epochs": int(confidence_epochs),
        "fit_batch_size": int(confidence_batch_size),
        "fit_learning_rate": float(confidence_learning_rate),
        "loss": "mean_squared_error_continuous_brier_equivalent",
        "loss_weight": float(confidence_loss_weight),
        "truth_identifier_use_count": 0,
        "future_outcome_use_count": 0,
        "constant_positive_label_use_count": 0,
    }
    payload["definition_sha256"] = _sha256_json(payload)
    return payload


def _fit_action_error_confidence_head(
    model: SharedRegionGraphActorCritic,
    loaded: LoadedRegionLearningDataset,
    *,
    config: RegionResourceEightRegionCandidateConfig,
) -> dict[str, Any]:
    if torch is None:
        raise RegionResourceEightRegionCandidateError(
            "torch_required_for_confidence_supervision"
        )
    train_samples = load_region_behavior_cloning_samples(
        loaded,
        split=RegionLearningSplit.TRAIN,
        device=config.device,
    )
    validation_samples = load_region_behavior_cloning_samples(
        loaded,
        split=RegionLearningSplit.VALIDATION,
        device=config.device,
    )
    if not train_samples or not validation_samples:
        raise RegionResourceEightRegionCandidateError(
            "confidence_train_or_validation_samples_unavailable"
        )
    model.eval()
    train_targets = tuple(
        _confidence_target_record(
            model,
            sample,
            continuous_tolerance=config.confidence_continuous_tolerance,
            inconsistent_target_ceiling=(
                config.confidence_inconsistent_target_ceiling
            ),
        )
        for sample in train_samples
    )
    validation_targets = tuple(
        _confidence_target_record(
            model,
            sample,
            continuous_tolerance=config.confidence_continuous_tolerance,
            inconsistent_target_ceiling=(
                config.confidence_inconsistent_target_ceiling
            ),
        )
        for sample in validation_samples
    )
    before_train = _confidence_metrics(
        model,
        train_samples,
        train_targets,
        threshold=config.fixed_minimum_confidence,
    )
    before_validation = _confidence_metrics(
        model,
        validation_samples,
        validation_targets,
        threshold=config.fixed_minimum_confidence,
    )

    for parameter in model.parameters():
        parameter.requires_grad_(False)
    for parameter in model.confidence_head.parameters():
        parameter.requires_grad_(True)
    optimizer = torch.optim.Adam(
        model.confidence_head.parameters(),
        lr=config.confidence_learning_rate,
    )
    order = list(range(len(train_samples)))
    randomizer = random.Random(config.random_seed + 401)
    history: list[float] = []
    for _ in range(config.confidence_epochs):
        randomizer.shuffle(order)
        weighted_loss = 0.0
        for offset in range(0, len(order), config.confidence_batch_size):
            indices = order[offset : offset + config.confidence_batch_size]
            optimizer.zero_grad()
            probabilities = torch.stack(
                [model(train_samples[index].graph).confidence for index in indices]
            )
            targets = torch.tensor(
                [train_targets[index].target_score for index in indices],
                dtype=probabilities.dtype,
                device=probabilities.device,
            )
            loss = (
                torch.nn.functional.mse_loss(probabilities, targets)
                * config.confidence_loss_weight
            )
            if not bool(torch.isfinite(loss).item()):
                raise RegionResourceEightRegionCandidateError(
                    "confidence_fit_loss_nonfinite"
                )
            loss.backward()
            optimizer.step()
            weighted_loss += float(loss.detach().cpu()) * len(indices)
        history.append(weighted_loss / len(train_samples))
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    model.eval()

    after_train = _confidence_metrics(
        model,
        train_samples,
        train_targets,
        threshold=config.fixed_minimum_confidence,
    )
    after_validation = _confidence_metrics(
        model,
        validation_samples,
        validation_targets,
        threshold=config.fixed_minimum_confidence,
    )
    acceptance = _confidence_calibration_acceptance(after_validation)
    summary = {
        "definition": _confidence_supervision_definition(config),
        "fit_sample_count": len(train_samples),
        "validation_sample_count": len(validation_samples),
        "fit_target_inventory_sha256": _sha256_json(
            [asdict(item) for item in train_targets]
        ),
        "validation_target_inventory_sha256": _sha256_json(
            [asdict(item) for item in validation_targets]
        ),
        "fit_history": history,
        "final_weighted_loss": history[-1],
        "train": {
            "before_fit": before_train,
            "after_fit": after_train,
        },
        "validation": {
            "before_fit": before_validation,
            "after_fit": after_validation,
        },
        "acceptance": acceptance,
        "action_model_frozen_during_fit": True,
        "confidence_head_only_parameter_update": True,
        "test_sample_use_count": 0,
        "reserved_evaluation_seed_use_count": 0,
        "truth_identifier_use_count": 0,
        "future_outcome_use_count": 0,
        "fixed_minimum_confidence": config.fixed_minimum_confidence,
        "runtime_preflight_completed": False,
        "formal_evaluation_authorized": False,
    }
    if not _all_finite_json(summary):
        raise RegionResourceEightRegionCandidateError(
            "confidence_summary_contains_nonfinite_value"
        )
    return summary


def _confidence_target_record(
    model: SharedRegionGraphActorCritic,
    sample: BehaviorCloningSample,
    *,
    continuous_tolerance: float,
    inconsistent_target_ceiling: float,
) -> _ConfidenceTargetRecord:
    with torch.no_grad():
        output = model(sample.graph)
        predicted_quota = output.node_mean[:, 0].clamp(-1.0, 1.0)
        target_quota = sample.target.node_continuous[:, 0].clamp(-1.0, 1.0)
        quota_delta = (predicted_quota - target_quota).abs()

        predicted_reserve = torch.sigmoid(output.node_mean[:, 1])
        target_reserve = torch.sigmoid(
            sample.target.node_continuous[:, 1]
        )
        reserve_delta = (predicted_reserve - target_reserve).abs()

        predicted_recon = torch.sigmoid(output.node_mean[:, 2])
        target_recon = torch.sigmoid(
            sample.target.node_continuous[:, 2]
        )
        recon_delta = (predicted_recon - target_recon).abs()

        predicted_binary = output.node_mean[:, 3:] >= 0.0
        target_binary = sample.target.node_binary >= 0.5
        binary_mismatch = predicted_binary != target_binary

        if sample.graph.edge_count:
            predicted_transfer = torch.tanh(output.edge_mean[:, 0]).clamp(
                0.0, 1.0
            )
            target_transfer = torch.tanh(
                sample.target.edge_continuous[:, 0]
            ).clamp(0.0, 1.0)
            transfer_delta = (predicted_transfer - target_transfer).abs()
            transfer_counts_match = all(
                int(
                    round(
                        float(predicted_transfer[index].cpu())
                        * edge_ref.transferable_resources
                    )
                )
                == int(
                    round(
                        float(target_transfer[index].cpu())
                        * edge_ref.transferable_resources
                    )
                )
                for index, edge_ref in enumerate(sample.graph.edge_refs)
            )
            transfer_error = float(transfer_delta.mean().cpu())
        else:
            transfer_counts_match = True
            transfer_error = 0.0

        quota_error = float(quota_delta.mean().cpu())
        reserve_error = float(reserve_delta.mean().cpu())
        reconnaissance_error = float(recon_delta.mean().cpu())
        binary_mismatch_rate = float(
            binary_mismatch.float().mean().cpu()
        )
        normalized_error = sum(
            (
                quota_error,
                reserve_error,
                reconnaissance_error,
                binary_mismatch_rate,
                transfer_error,
            )
        ) / 5.0
        action_consistent = bool(
            float(quota_delta.max().cpu()) <= continuous_tolerance
            and float(reserve_delta.max().cpu()) <= continuous_tolerance
            and float(recon_delta.max().cpu()) <= continuous_tolerance
            and not bool(binary_mismatch.any().item())
            and transfer_counts_match
        )
        score = max(0.0, min(1.0, 1.0 - normalized_error))
        if not action_consistent:
            score = min(score, inconsistent_target_ceiling)
    return _ConfidenceTargetRecord(
        target_score=score,
        normalized_action_error=normalized_error,
        action_consistent=action_consistent,
        quota_error=quota_error,
        reserve_error=reserve_error,
        reconnaissance_error=reconnaissance_error,
        binary_mismatch_rate=binary_mismatch_rate,
        transfer_error=transfer_error,
    )


def _confidence_metrics(
    model: SharedRegionGraphActorCritic,
    samples: Sequence[BehaviorCloningSample],
    targets: Sequence[_ConfidenceTargetRecord],
    *,
    threshold: float,
) -> dict[str, Any]:
    if len(samples) != len(targets) or not samples:
        raise RegionResourceEightRegionCandidateError(
            "confidence_metric_sample_target_mismatch"
        )
    with torch.no_grad():
        probabilities = [
            float(model(sample.graph).confidence.detach().cpu())
            for sample in samples
        ]
    target_scores = [item.target_score for item in targets]
    squared_errors = [
        (probability - target) ** 2
        for probability, target in zip(
            probabilities, target_scores, strict=True
        )
    ]
    absolute_errors = [
        abs(probability - target)
        for probability, target in zip(
            probabilities, target_scores, strict=True
        )
    ]
    threshold_pass = [
        probability >= threshold for probability in probabilities
    ]
    consistent = [item.action_consistent for item in targets]
    pass_count = sum(threshold_pass)
    consistent_pass_count = sum(
        passed and agrees
        for passed, agrees in zip(
            threshold_pass, consistent, strict=True
        )
    )
    bins: list[dict[str, Any]] = []
    calibration_error = 0.0
    for bin_index in range(10):
        lower = bin_index / 10.0
        upper = (bin_index + 1) / 10.0
        indices = [
            index
            for index, probability in enumerate(probabilities)
            if lower <= probability < upper
            or (bin_index == 9 and probability == 1.0)
        ]
        if not indices:
            continue
        mean_probability = sum(probabilities[index] for index in indices) / len(
            indices
        )
        mean_target = sum(target_scores[index] for index in indices) / len(
            indices
        )
        calibration_error += (
            len(indices)
            / len(samples)
            * abs(mean_probability - mean_target)
        )
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "sample_count": len(indices),
                "mean_confidence": mean_probability,
                "mean_target": mean_target,
            }
        )
    return {
        "sample_count": len(samples),
        "target_minimum": min(target_scores),
        "target_mean": sum(target_scores) / len(target_scores),
        "target_maximum": max(target_scores),
        "confidence_minimum": min(probabilities),
        "confidence_mean": sum(probabilities) / len(probabilities),
        "confidence_maximum": max(probabilities),
        "normalized_action_error_mean": sum(
            item.normalized_action_error for item in targets
        )
        / len(targets),
        "action_consistent_count": sum(consistent),
        "action_consistent_rate": sum(consistent) / len(consistent),
        "brier_score": sum(squared_errors) / len(squared_errors),
        "mean_absolute_calibration_error": (
            sum(absolute_errors) / len(absolute_errors)
        ),
        "expected_calibration_error_10_bin": calibration_error,
        "calibration_bins": bins,
        "fixed_threshold": threshold,
        "threshold_pass_count": pass_count,
        "threshold_pass_rate": pass_count / len(samples),
        "action_consistent_threshold_pass_count": consistent_pass_count,
        "action_inconsistent_threshold_pass_count": (
            pass_count - consistent_pass_count
        ),
        "action_consistency_rate_among_threshold_pass": (
            consistent_pass_count / pass_count if pass_count else None
        ),
        "action_consistent_below_threshold_count": sum(
            agrees and not passed
            for passed, agrees in zip(
                threshold_pass, consistent, strict=True
            )
        ),
    }


def _confidence_calibration_acceptance(
    validation_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    threshold_pass_count = int(validation_metrics["threshold_pass_count"])
    inconsistent_pass_count = int(
        validation_metrics["action_inconsistent_threshold_pass_count"]
    )
    blockers: list[str] = []
    if threshold_pass_count <= 0:
        blockers.append("validation_threshold_pass_sample_unavailable")
    if inconsistent_pass_count:
        blockers.append(
            "validation_action_inconsistent_threshold_pass:"
            f"{inconsistent_pass_count}"
        )
    return {
        "criterion": (
            "at least one validation sample passes fixed confidence 0.60 and "
            "every passing sample satisfies the recorded action-consistency "
            "condition"
        ),
        "fixed_minimum_confidence": 0.60,
        "threshold_pass_count": threshold_pass_count,
        "action_inconsistent_threshold_pass_count": inconsistent_pass_count,
        "accepted": not blockers,
        "blockers": blockers,
    }


def _all_finite_json(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_all_finite_json(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_all_finite_json(item) for item in value)
    if isinstance(value, float):
        return isfinite(value)
    return True


@dataclass(frozen=True)
class RegionResourceEightRegionCandidateManifest:
    candidate_id: str
    model_version: str
    source_summary_file_sha256: str
    source_identity_sha256: str
    training_view_manifest_file_sha256: str
    training_view_content_sha256: str
    runtime_dataset_sha256: str
    action_dataset_sha256: str
    composite_dataset_sha256: str
    composite_split_sha256: str
    config_file_sha256: str
    config_sha256: str
    confidence_target_definition_sha256: str
    fixed_minimum_confidence: float
    validation_confidence_brier: float
    validation_threshold_pass_rate: float
    validation_action_consistency_rate_among_pass: float | None
    validation_action_inconsistent_threshold_pass_count: int
    confidence_calibration_accepted: bool
    training_summary_file_sha256: str
    training_summary_content_sha256: str
    bundle_manifest_sha256: str
    model_state_sha256: str
    bundle_training_manifest_sha256: str
    split_usage: RegionResourceCurrentLineageSplitUsage
    applicable_region_count: int
    validation_sample_count: int
    validation_nonfinite_output_count: int
    artifact_files: Mapping[str, str]
    permissions: RegionResourceEightRegionPermissions = (
        RegionResourceEightRegionPermissions()
    )
    lifecycle_stage: str = MODEL_LIFECYCLE_DEVELOPMENT
    maximum_advisor_mode: str = MODEL_MAXIMUM_MODE_SHADOW
    read_only_shadow: bool = True
    runtime_preflight_completed: bool = False
    formal_holdout_evaluated: bool = False
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_EIGHT_REGION_CANDIDATE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_EIGHT_REGION_CANDIDATE_SCHEMA:
            raise ValueError("unsupported eight-region candidate manifest schema")
        if (
            self.candidate_id != REGION_RESOURCE_EIGHT_REGION_CANDIDATE_ID
            or self.model_version != REGION_RESOURCE_EIGHT_REGION_MODEL_VERSION
        ):
            raise ValueError("eight-region candidate identity mismatch")
        for name in (
            "source_summary_file_sha256",
            "source_identity_sha256",
            "training_view_manifest_file_sha256",
            "training_view_content_sha256",
            "runtime_dataset_sha256",
            "action_dataset_sha256",
            "composite_dataset_sha256",
            "composite_split_sha256",
            "config_file_sha256",
            "config_sha256",
            "confidence_target_definition_sha256",
            "training_summary_file_sha256",
            "training_summary_content_sha256",
            "bundle_manifest_sha256",
            "model_state_sha256",
            "bundle_training_manifest_sha256",
        ):
            _require_sha256(str(getattr(self, name)), name)
        if (
            self.runtime_dataset_sha256
            != REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256
            or self.action_dataset_sha256
            != REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256
        ):
            raise ValueError("eight-region source dataset binding changed")
        if self.applicable_region_count != REGION_RESOURCE_EIGHT_REGION_COUNT:
            raise ValueError("candidate applicability must remain eight regions")
        if (
            self.fixed_minimum_confidence
            != REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE
            or self.fixed_minimum_confidence != 0.60
        ):
            raise ValueError("candidate minimum confidence must remain 0.60")
        for name in (
            "validation_confidence_brier",
            "validation_threshold_pass_rate",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if self.validation_action_consistency_rate_among_pass is not None:
            value = float(
                self.validation_action_consistency_rate_among_pass
            )
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(
                    "validation action consistency rate must be in [0, 1]"
                )
        if (
            type(self.validation_action_inconsistent_threshold_pass_count)
            is not int
            or self.validation_action_inconsistent_threshold_pass_count < 0
            or type(self.confidence_calibration_accepted) is not bool
        ):
            raise ValueError("candidate confidence acceptance evidence is invalid")
        expected_calibration_acceptance = bool(
            self.validation_threshold_pass_rate > 0.0
            and self.validation_action_inconsistent_threshold_pass_count == 0
        )
        if self.confidence_calibration_accepted != expected_calibration_acceptance:
            raise ValueError("candidate confidence acceptance is inconsistent")
        if (
            type(self.validation_sample_count) is not int
            or self.validation_sample_count <= 0
            or type(self.validation_nonfinite_output_count) is not int
            or self.validation_nonfinite_output_count != 0
        ):
            raise ValueError("candidate validation output must be finite and non-empty")
        if (
            self.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
            or self.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
            or self.read_only_shadow is not True
            or self.runtime_preflight_completed is not False
            or self.formal_holdout_evaluated is not False
        ):
            raise ValueError("candidate crossed the read-only development boundary")
        if not isinstance(
            self.split_usage, RegionResourceCurrentLineageSplitUsage
        ):
            raise ValueError("candidate split usage is invalid")
        if not isinstance(
            self.permissions, RegionResourceEightRegionPermissions
        ):
            raise ValueError("candidate permissions are invalid")
        artifacts = {
            str(path): str(digest).lower()
            for path, digest in self.artifact_files.items()
        }
        if set(artifacts) != _ARTIFACT_FILES:
            raise ValueError("candidate artifact inventory is incomplete")
        for path, digest in artifacts.items():
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("candidate artifact path is unsafe")
            _require_sha256(digest, f"artifact_files.{path}")
        expected_bindings = {
            REGION_RESOURCE_EIGHT_REGION_SOURCE_FILENAME: (
                self.source_summary_file_sha256
            ),
            REGION_RESOURCE_EIGHT_REGION_VIEW_FILENAME: (
                self.training_view_manifest_file_sha256
            ),
            REGION_RESOURCE_EIGHT_REGION_CONFIG_FILENAME: self.config_file_sha256,
            REGION_RESOURCE_EIGHT_REGION_TRAINING_FILENAME: (
                self.training_summary_file_sha256
            ),
            "bundle/manifest.json": self.bundle_manifest_sha256,
            "bundle/state_dict.pt": self.model_state_sha256,
            "bundle/training_dataset_manifest.json": (
                self.bundle_training_manifest_sha256
            ),
        }
        if artifacts != expected_bindings:
            raise ValueError("candidate artifact bindings are inconsistent")
        object.__setattr__(self, "artifact_files", artifacts)
        expected_content = _sha256_json(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected_content:
            raise ValueError("candidate manifest content SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected_content)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_id": self.candidate_id,
            "model_version": self.model_version,
            "source_summary_file_sha256": self.source_summary_file_sha256,
            "source_identity_sha256": self.source_identity_sha256,
            "training_view_manifest_file_sha256": (
                self.training_view_manifest_file_sha256
            ),
            "training_view_content_sha256": self.training_view_content_sha256,
            "runtime_dataset_sha256": self.runtime_dataset_sha256,
            "action_dataset_sha256": self.action_dataset_sha256,
            "composite_dataset_sha256": self.composite_dataset_sha256,
            "composite_split_sha256": self.composite_split_sha256,
            "config_file_sha256": self.config_file_sha256,
            "config_sha256": self.config_sha256,
            "confidence_target_definition_sha256": (
                self.confidence_target_definition_sha256
            ),
            "fixed_minimum_confidence": self.fixed_minimum_confidence,
            "validation_confidence_brier": self.validation_confidence_brier,
            "validation_threshold_pass_rate": (
                self.validation_threshold_pass_rate
            ),
            "validation_action_consistency_rate_among_pass": (
                self.validation_action_consistency_rate_among_pass
            ),
            "validation_action_inconsistent_threshold_pass_count": (
                self.validation_action_inconsistent_threshold_pass_count
            ),
            "confidence_calibration_accepted": (
                self.confidence_calibration_accepted
            ),
            "training_summary_file_sha256": (
                self.training_summary_file_sha256
            ),
            "training_summary_content_sha256": (
                self.training_summary_content_sha256
            ),
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "model_state_sha256": self.model_state_sha256,
            "bundle_training_manifest_sha256": (
                self.bundle_training_manifest_sha256
            ),
            "split_usage": self.split_usage.to_dict(),
            "applicable_region_count": self.applicable_region_count,
            "validation_sample_count": self.validation_sample_count,
            "validation_nonfinite_output_count": (
                self.validation_nonfinite_output_count
            ),
            "artifact_files": dict(sorted(self.artifact_files.items())),
            "permissions": self.permissions.to_dict(),
            "lifecycle_stage": self.lifecycle_stage,
            "maximum_advisor_mode": self.maximum_advisor_mode,
            "read_only_shadow": self.read_only_shadow,
            "runtime_preflight_completed": self.runtime_preflight_completed,
            "formal_holdout_evaluated": self.formal_holdout_evaluated,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceEightRegionCandidateManifest":
        _require_exact_keys(value, cls.__dataclass_fields__, "candidate_manifest")
        payload = dict(value)
        payload["split_usage"] = (
            RegionResourceCurrentLineageSplitUsage.from_mapping(
                payload["split_usage"]
            )
        )
        payload["permissions"] = RegionResourceEightRegionPermissions.from_mapping(
            payload["permissions"]
        )
        return cls(**payload)


def build_region_resource_eight_region_candidate(
    runtime_dataset_dir: str | Path,
    action_dataset_dir: str | Path,
    *,
    repository_root: str | Path,
    output_dir: str | Path,
    config: RegionResourceEightRegionCandidateConfig | None = None,
) -> dict[str, Any]:
    """Build one content-addressed eight-region development candidate."""

    resolved = config or RegionResourceEightRegionCandidateConfig()
    destination = Path(output_dir).resolve()
    if destination.name != resolved.candidate_id:
        raise RegionResourceEightRegionCandidateError(
            "output_directory_name_must_equal_candidate_id"
        )
    if destination.exists() or destination.is_symlink():
        raise RegionResourceEightRegionCandidateError(
            "candidate_output_must_not_exist"
        )
    runtime = _load_verified_source(
        runtime_dataset_dir,
        expected_sha256=REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256,
        expected_episode_count=REGION_RESOURCE_EIGHT_REGION_RUNTIME_EPISODE_COUNT,
        expected_frame_count=REGION_RESOURCE_EIGHT_REGION_RUNTIME_FRAME_COUNT,
        expected_region_count=REGION_RESOURCE_EIGHT_REGION_COUNT,
        expected_action_inventory=_EXPECTED_RUNTIME_ACTION_INVENTORY,
        source_name="runtime",
    )
    action = _load_verified_source(
        action_dataset_dir,
        expected_sha256=REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256,
        expected_episode_count=REGION_RESOURCE_EIGHT_REGION_ACTION_EPISODE_COUNT,
        expected_frame_count=REGION_RESOURCE_EIGHT_REGION_ACTION_FRAME_COUNT,
        expected_region_count=4,
        expected_action_inventory=_EXPECTED_CURRICULUM_ACTION_INVENTORY,
        source_name="action_curriculum",
    )
    _validate_global_training_seeds(runtime, action)
    source_summary = inspect_region_resource_eight_region_source(repository_root)
    config_payload = resolved.to_dict()
    config_sha256 = _sha256_json(config_payload)
    stored_config = {**config_payload, "config_sha256": config_sha256}

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.staging-", dir=destination.parent
        )
    )
    staging = temporary_parent / destination.name
    staging.mkdir()
    try:
        composite = _build_training_view_dataset(
            runtime,
            action,
            staging_root=temporary_parent / "view_build",
            config=resolved,
            source_git_commit=source_summary["git_commit"],
            source_identity_sha256=source_summary["source_identity_sha256"],
        )
        loaded = load_region_learning_dataset_splits(
            composite["dataset"].root,
            splits=(RegionLearningSplit.TRAIN, RegionLearningSplit.VALIDATION),
        )
        split_usage = _split_usage(loaded)
        view_manifest = _build_training_view_manifest(
            runtime,
            action,
            composite,
            split_usage=split_usage,
            source_summary=source_summary,
            config=resolved,
        )

        _write_json(
            staging / REGION_RESOURCE_EIGHT_REGION_SOURCE_FILENAME,
            source_summary,
        )
        _write_json(
            staging / REGION_RESOURCE_EIGHT_REGION_VIEW_FILENAME,
            view_manifest,
        )
        _write_json(
            staging / REGION_RESOURCE_EIGHT_REGION_CONFIG_FILENAME,
            stored_config,
        )

        training_config = resolved.as_training_config()
        model, training_summary = _train_candidate(
            loaded,
            training_config,
            config_sha256=config_sha256,
        )
        confidence_summary = _fit_action_error_confidence_head(
            model,
            loaded,
            config=resolved,
        )
        training_action_inventory = _action_inventory(loaded)
        bundle_manifest = save_region_resource_model_bundle(
            model,
            staging / "bundle",
            model_version=resolved.model_version,
            training_graphs=tuple(
                sample.graph
                for sample in load_region_behavior_cloning_samples(
                    loaded,
                    split=RegionLearningSplit.TRAIN,
                    device=resolved.device,
                )
            ),
            created_at_utc=resolved.created_at_utc,
            training_dataset_manifest=composite["dataset"].manifest,
            lifecycle_stage=MODEL_LIFECYCLE_DEVELOPMENT,
            maximum_advisor_mode=MODEL_MAXIMUM_MODE_SHADOW,
            reward_evidence_available=False,
            final_holdout_seed_count=0,
            action_diversity_sufficient=True,
            strategy_capability_claim_allowed=False,
            target_action_inventory=training_action_inventory,
            admission_reasons=(
                "eight_region_runtime_feature_geometry",
                "truth_free_action_curriculum_recipe",
                "global_numeric_seed_atomic_split",
                "reserved_evaluation_seeds_excluded",
                "development_read_only_shadow",
                "confidence_from_frozen_action_error",
                "confidence_threshold_fixed_at_0_60",
                "main_runtime_preflight_pending",
                "formal_evaluation_forbidden",
                "all_runtime_permissions_disabled",
            ),
        )
        loaded_bundle = load_region_resource_model_bundle(
            staging / "bundle",
            expected_model_version=resolved.model_version,
            expected_state_dict_sha256=bundle_manifest.state_dict_sha256,
            map_location=resolved.device,
            require_training_dataset_manifest=True,
        )
        validation = _review_validation_outputs(
            loaded,
            loaded_bundle.model,
            loaded_bundle.manifest,
        )
        training_summary = {
            "schema": REGION_RESOURCE_EIGHT_REGION_TRAINING_SCHEMA,
            "base_training_summary": training_summary,
            "validation_output_review": validation,
            "target_action_inventory_loaded_train_validation": (
                training_action_inventory
            ),
            "confidence_supervision": confidence_summary,
            "test_payload_used_for_training": False,
            "reserved_evaluation_seed_use_count": 0,
            "runtime_preflight_completed": False,
            "formal_evaluation_authorized": False,
            "permissions": RegionResourceEightRegionPermissions().to_dict(),
        }
        training_summary["content_sha256"] = _sha256_json(training_summary)
        _write_json(
            staging / REGION_RESOURCE_EIGHT_REGION_TRAINING_FILENAME,
            training_summary,
        )

        artifact_files = {
            relative_path: _sha256_file(staging / relative_path)
            for relative_path in sorted(_ARTIFACT_FILES)
        }
        manifest = RegionResourceEightRegionCandidateManifest(
            candidate_id=resolved.candidate_id,
            model_version=resolved.model_version,
            source_summary_file_sha256=artifact_files[
                REGION_RESOURCE_EIGHT_REGION_SOURCE_FILENAME
            ],
            source_identity_sha256=source_summary["source_identity_sha256"],
            training_view_manifest_file_sha256=artifact_files[
                REGION_RESOURCE_EIGHT_REGION_VIEW_FILENAME
            ],
            training_view_content_sha256=view_manifest["content_sha256"],
            runtime_dataset_sha256=(
                REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256
            ),
            action_dataset_sha256=(
                REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256
            ),
            composite_dataset_sha256=composite["dataset"].manifest.dataset_sha256,
            composite_split_sha256=(
                composite["dataset"].manifest.split.split_sha256
            ),
            config_file_sha256=artifact_files[
                REGION_RESOURCE_EIGHT_REGION_CONFIG_FILENAME
            ],
            config_sha256=config_sha256,
            confidence_target_definition_sha256=(
                view_manifest["confidence_supervision"][
                    "definition_sha256"
                ]
            ),
            fixed_minimum_confidence=resolved.fixed_minimum_confidence,
            validation_confidence_brier=confidence_summary["validation"][
                "after_fit"
            ]["brier_score"],
            validation_threshold_pass_rate=confidence_summary["validation"][
                "after_fit"
            ]["threshold_pass_rate"],
            validation_action_consistency_rate_among_pass=(
                confidence_summary["validation"]["after_fit"][
                    "action_consistency_rate_among_threshold_pass"
                ]
            ),
            validation_action_inconsistent_threshold_pass_count=int(
                confidence_summary["validation"]["after_fit"][
                    "action_inconsistent_threshold_pass_count"
                ]
            ),
            confidence_calibration_accepted=bool(
                confidence_summary["acceptance"]["accepted"]
            ),
            training_summary_file_sha256=artifact_files[
                REGION_RESOURCE_EIGHT_REGION_TRAINING_FILENAME
            ],
            training_summary_content_sha256=training_summary["content_sha256"],
            bundle_manifest_sha256=artifact_files["bundle/manifest.json"],
            model_state_sha256=artifact_files["bundle/state_dict.pt"],
            bundle_training_manifest_sha256=artifact_files[
                "bundle/training_dataset_manifest.json"
            ],
            split_usage=split_usage,
            applicable_region_count=REGION_RESOURCE_EIGHT_REGION_COUNT,
            validation_sample_count=int(validation["sample_count"]),
            validation_nonfinite_output_count=int(
                validation["nonfinite_output_count"]
            ),
            artifact_files=artifact_files,
        )
        _write_json(
            staging / REGION_RESOURCE_EIGHT_REGION_CANDIDATE_FILENAME,
            manifest.to_dict(),
        )
        review_region_resource_eight_region_candidate(staging)
        shutil.rmtree(temporary_parent / "view_build", ignore_errors=True)
        shutil.rmtree(composite["dataset"].root, ignore_errors=True)
        staging.replace(destination)
        temporary_parent.rmdir()
        return {
            "candidate_manifest": manifest.to_dict(),
            "source_summary": source_summary,
            "training_view_manifest": view_manifest,
            "training_summary": training_summary,
            "output_dir": str(destination),
        }
    except Exception:
        shutil.rmtree(temporary_parent, ignore_errors=True)
        raise


def load_region_resource_eight_region_candidate_manifest(
    candidate_root: str | Path,
    *,
    expected_manifest_file_sha256: str | None = None,
) -> RegionResourceEightRegionCandidateManifest:
    """Load and verify a self-contained source-controlled candidate."""

    root = Path(candidate_root)
    path = root / REGION_RESOURCE_EIGHT_REGION_CANDIDATE_FILENAME
    if root.is_symlink() or path.is_symlink():
        raise RegionResourceEightRegionCandidateError(
            "candidate_manifest_symlink_forbidden"
        )
    try:
        observed_manifest_sha = _sha256_file(path)
    except OSError as exc:
        raise RegionResourceEightRegionCandidateError(
            "candidate_manifest_unavailable"
        ) from exc
    if expected_manifest_file_sha256 is not None:
        _require_sha256(
            expected_manifest_file_sha256,
            "expected_manifest_file_sha256",
        )
        if observed_manifest_sha != expected_manifest_file_sha256:
            raise RegionResourceEightRegionCandidateError(
                "candidate_manifest_file_sha256_mismatch"
            )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = RegionResourceEightRegionCandidateManifest.from_mapping(
            payload
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RegionResourceEightRegionCandidateError(
            f"candidate_manifest_invalid:{type(exc).__name__}"
        ) from exc
    if root.name != manifest.candidate_id:
        raise RegionResourceEightRegionCandidateError(
            "candidate_directory_identity_mismatch"
        )
    for relative_path, expected_sha in manifest.artifact_files.items():
        artifact = root / relative_path
        if artifact.is_symlink():
            raise RegionResourceEightRegionCandidateError(
                f"candidate_artifact_symlink_forbidden:{relative_path}"
            )
        try:
            observed = _sha256_file(artifact)
        except OSError as exc:
            raise RegionResourceEightRegionCandidateError(
                f"candidate_artifact_unavailable:{relative_path}"
            ) from exc
        if observed != expected_sha:
            raise RegionResourceEightRegionCandidateError(
                f"candidate_artifact_sha256_mismatch:{relative_path}"
            )
    return manifest


def review_region_resource_eight_region_candidate(
    candidate_root: str | Path,
) -> dict[str, Any]:
    """Review candidate self-containment without reading source datasets."""

    root = Path(candidate_root)
    manifest = load_region_resource_eight_region_candidate_manifest(root)
    source = _read_json_object(
        root / REGION_RESOURCE_EIGHT_REGION_SOURCE_FILENAME,
        "source_summary",
    )
    view = _read_json_object(
        root / REGION_RESOURCE_EIGHT_REGION_VIEW_FILENAME,
        "training_view_manifest",
    )
    _validate_source_summary(source)
    _validate_training_view_manifest(view)
    if (
        source["source_identity_sha256"] != manifest.source_identity_sha256
        or view["content_sha256"] != manifest.training_view_content_sha256
        or view["sources"]["runtime"]["dataset_sha256"]
        != manifest.runtime_dataset_sha256
        or view["sources"]["action_curriculum"]["dataset_sha256"]
        != manifest.action_dataset_sha256
        or view["composite"]["dataset_sha256"]
        != manifest.composite_dataset_sha256
        or view["global_split"]["split_sha256"]
        != manifest.composite_split_sha256
    ):
        raise RegionResourceEightRegionCandidateError(
            "candidate_source_or_view_binding_mismatch"
        )
    config = _read_json_object(
        root / REGION_RESOURCE_EIGHT_REGION_CONFIG_FILENAME,
        "training_config",
    )
    config_sha = str(config.pop("config_sha256", ""))
    _require_exact_keys(
        config,
        RegionResourceEightRegionCandidateConfig.__dataclass_fields__,
        "training_config",
    )
    resolved = RegionResourceEightRegionCandidateConfig(**config)
    if (
        _sha256_json(resolved.to_dict()) != config_sha
        or config_sha != manifest.config_sha256
    ):
        raise RegionResourceEightRegionCandidateError(
            "candidate_training_config_mismatch"
        )
    training = _read_json_object(
        root / REGION_RESOURCE_EIGHT_REGION_TRAINING_FILENAME,
        "training_summary",
    )
    observed_training_content_sha = str(training.get("content_sha256", ""))
    content = dict(training)
    content.pop("content_sha256", None)
    if (
        _sha256_json(content) != observed_training_content_sha
        or observed_training_content_sha
        != manifest.training_summary_content_sha256
        or training.get("test_payload_used_for_training") is not False
        or training.get("reserved_evaluation_seed_use_count") != 0
        or training.get("runtime_preflight_completed") is not False
        or training.get("formal_evaluation_authorized") is not False
    ):
        raise RegionResourceEightRegionCandidateError(
            "candidate_training_summary_boundary_crossed"
        )
    confidence = training.get("confidence_supervision")
    if not isinstance(confidence, Mapping):
        raise RegionResourceEightRegionCandidateError(
            "candidate_confidence_summary_unavailable"
        )
    validation_confidence = confidence["validation"]["after_fit"]
    confidence_acceptance = confidence.get("acceptance")
    if (
        not isinstance(confidence_acceptance, Mapping)
        or confidence["definition"] != view["confidence_supervision"]
        or confidence["definition"]["definition_sha256"]
        != manifest.confidence_target_definition_sha256
        or confidence["fixed_minimum_confidence"]
        != manifest.fixed_minimum_confidence
        or confidence["test_sample_use_count"] != 0
        or confidence["reserved_evaluation_seed_use_count"] != 0
        or confidence["truth_identifier_use_count"] != 0
        or confidence["future_outcome_use_count"] != 0
        or confidence["action_model_frozen_during_fit"] is not True
        or confidence["confidence_head_only_parameter_update"] is not True
        or validation_confidence["brier_score"]
        != manifest.validation_confidence_brier
        or validation_confidence["threshold_pass_rate"]
        != manifest.validation_threshold_pass_rate
        or validation_confidence[
            "action_consistency_rate_among_threshold_pass"
        ]
        != manifest.validation_action_consistency_rate_among_pass
        or validation_confidence[
            "action_inconsistent_threshold_pass_count"
        ]
        != manifest.validation_action_inconsistent_threshold_pass_count
        or confidence_acceptance["accepted"]
        is not manifest.confidence_calibration_accepted
        or confidence_acceptance
        != _confidence_calibration_acceptance(validation_confidence)
    ):
        raise RegionResourceEightRegionCandidateError(
            "candidate_confidence_summary_binding_mismatch"
        )
    RegionResourceEightRegionPermissions.from_mapping(training["permissions"])
    bundle = load_region_resource_model_bundle(
        root / "bundle",
        expected_model_version=manifest.model_version,
        expected_state_dict_sha256=manifest.model_state_sha256,
        map_location="cpu",
        require_training_dataset_manifest=True,
    )
    embedded = bundle.training_dataset_manifest
    if (
        embedded is None
        or embedded.dataset_sha256 != manifest.composite_dataset_sha256
        or embedded.split.split_sha256 != manifest.composite_split_sha256
        or bundle.manifest.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
        or bundle.manifest.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
        or bundle.manifest.assist_admitted
        or bundle.manifest.strategy_capability_claim_allowed
        or bundle.manifest.reward_evidence_available
        or bundle.manifest.final_holdout_seed_count != 0
    ):
        raise RegionResourceEightRegionCandidateError(
            "candidate_bundle_boundary_crossed"
        )
    if not all(
        bool(parameter.detach().isfinite().all().item())
        for parameter in bundle.model.parameters()
    ):
        raise RegionResourceEightRegionCandidateError(
            "candidate_model_parameter_nonfinite"
        )
    return {
        "candidate_id": manifest.candidate_id,
        "model_version": manifest.model_version,
        "candidate_manifest_content_sha256": manifest.content_sha256,
        "source_identity_sha256": manifest.source_identity_sha256,
        "runtime_dataset_sha256": manifest.runtime_dataset_sha256,
        "action_dataset_sha256": manifest.action_dataset_sha256,
        "composite_dataset_sha256": manifest.composite_dataset_sha256,
        "composite_split_sha256": manifest.composite_split_sha256,
        "model_state_sha256": manifest.model_state_sha256,
        "applicable_region_count": manifest.applicable_region_count,
        "confidence_calibration_accepted": (
            manifest.confidence_calibration_accepted
        ),
        "confidence_calibration_blockers": list(
            confidence_acceptance["blockers"]
        ),
        "read_only_shadow_verified": True,
        "source_datasets_required_for_runtime_load": False,
        "runtime_preflight_completed": False,
        "formal_evaluation_authorized": False,
        "permissions": manifest.permissions.to_dict(),
    }


def inspect_region_resource_eight_region_source(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Bind the committed training core and the exact view-recipe bytes."""

    root = Path(repository_root).resolve()
    observed_root = Path(
        _git_text(root, "rev-parse", "--show-toplevel")
    ).resolve()
    if observed_root != root:
        raise RegionResourceEightRegionCandidateError(
            "source_repository_root_mismatch"
        )
    git_commit = _git_text(root, "rev-parse", "--verify", "HEAD")
    git_tree = _git_text(root, "rev-parse", "--verify", "HEAD^{tree}")
    committed_files: dict[str, str] = {}
    for relative_path in _COMMITTED_TRAINING_IMPLEMENTATION_FILES:
        working_path = root / relative_path
        if working_path.is_symlink() or not working_path.is_file():
            raise RegionResourceEightRegionCandidateError(
                f"committed_training_file_unavailable:{relative_path}"
            )
        committed_bytes = _git_bytes(root, "show", f"HEAD:{relative_path}")
        working_bytes = working_path.read_bytes()
        if committed_bytes != working_bytes:
            raise RegionResourceEightRegionCandidateError(
                f"committed_training_file_modified:{relative_path}"
            )
        committed_files[relative_path] = _sha256_bytes(committed_bytes)
    builder_path = root / _VIEW_BUILDER_FILE
    if builder_path.is_symlink() or not builder_path.is_file():
        raise RegionResourceEightRegionCandidateError(
            "view_builder_file_unavailable"
        )
    view_builder_sha = _sha256_file(builder_path)
    content = {
        "schema": REGION_RESOURCE_EIGHT_REGION_SOURCE_SCHEMA,
        "git_commit": git_commit,
        "git_tree": git_tree,
        "committed_training_implementation_files": dict(
            sorted(committed_files.items())
        ),
        "committed_training_implementation_sha256": _sha256_json(
            committed_files
        ),
        "view_builder_file": _VIEW_BUILDER_FILE,
        "view_builder_file_sha256": view_builder_sha,
        "view_recipe": REGION_RESOURCE_EIGHT_REGION_VIEW_RECIPE,
        "training_core_matches_commit": True,
        "view_builder_content_addressed": True,
    }
    content["source_identity_sha256"] = _sha256_json(content)
    content["content_sha256"] = _sha256_json(content)
    _validate_source_summary(content)
    return content


def _load_verified_source(
    dataset_dir: str | Path,
    *,
    expected_sha256: str,
    expected_episode_count: int,
    expected_frame_count: int,
    expected_region_count: int,
    expected_action_inventory: Mapping[str, int],
    source_name: str,
) -> LoadedRegionLearningDataset:
    try:
        loaded = load_region_learning_dataset(dataset_dir)
    except Exception as exc:
        raise RegionResourceEightRegionCandidateError(
            f"{source_name}_dataset_load_failed:{type(exc).__name__}:{exc}"
        ) from exc
    manifest = loaded.manifest
    if (
        manifest.dataset_sha256 != expected_sha256
        or manifest.availability.episode_count != expected_episode_count
        or manifest.availability.frame_count != expected_frame_count
        or manifest.availability.dirty_episode_count != 0
        or not manifest.availability.behavior_cloning_available
    ):
        raise RegionResourceEightRegionCandidateError(
            f"{source_name}_dataset_identity_or_count_mismatch"
        )
    region_counts = Counter(
        frame.snapshot.region_count
        for episode in loaded.episode_records
        for frame in episode.frames
    )
    if region_counts != Counter({expected_region_count: expected_frame_count}):
        raise RegionResourceEightRegionCandidateError(
            f"{source_name}_region_count_mismatch"
        )
    action_inventory = _action_inventory(loaded)
    if action_inventory != dict(expected_action_inventory):
        raise RegionResourceEightRegionCandidateError(
            f"{source_name}_action_inventory_mismatch"
        )
    return loaded


def _validate_global_training_seeds(
    runtime: LoadedRegionLearningDataset,
    action: LoadedRegionLearningDataset,
) -> None:
    expected = set(REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS)
    reserved = set(REGION_RESOURCE_EIGHT_REGION_RESERVED_SEEDS)
    catalogs = {
        "runtime": {int(item.source.seed) for item in runtime.episode_records},
        "action_curriculum": {
            int(item.source.seed) for item in action.episode_records
        },
    }
    for source_name, seeds in catalogs.items():
        if seeds & reserved:
            raise RegionResourceEightRegionCandidateError(
                f"{source_name}_reserved_evaluation_seed_present"
            )
        if seeds != expected:
            raise RegionResourceEightRegionCandidateError(
                f"{source_name}_seed_inventory_must_equal_0_99"
            )


def _build_training_view_dataset(
    runtime: LoadedRegionLearningDataset,
    action: LoadedRegionLearningDataset,
    *,
    staging_root: Path,
    config: RegionResourceEightRegionCandidateConfig,
    source_git_commit: str,
    source_identity_sha256: str,
) -> dict[str, Any]:
    episode_staging = staging_root / "episodes_staging"
    dataset_dir = staging_root / "dataset"
    overlay_provenance: list[dict[str, Any]] = []
    for episode in runtime.episode_records:
        stage_region_learning_episode(
            episode_staging, episode.source, episode.frames
        )
    runtime_by_seed: dict[int, list[LoadedRegionLearningEpisode]] = {}
    action_by_seed: dict[int, LoadedRegionLearningEpisode] = {}
    for episode in runtime.episode_records:
        runtime_by_seed.setdefault(int(episode.source.seed), []).append(episode)
    for episode in action.episode_records:
        seed = int(episode.source.seed)
        if seed in action_by_seed:
            raise RegionResourceEightRegionCandidateError(
                "action_curriculum_requires_one_episode_per_seed"
            )
        action_by_seed[seed] = episode

    overlay_config_sha = _sha256_json(
        {
            "view_recipe": REGION_RESOURCE_EIGHT_REGION_VIEW_RECIPE,
            "runtime_dataset_sha256": runtime.manifest.dataset_sha256,
            "action_dataset_sha256": action.manifest.dataset_sha256,
            "source_identity_sha256": source_identity_sha256,
            "region_count": REGION_RESOURCE_EIGHT_REGION_COUNT,
            "frame_kinds": list(
                REGION_RESOURCE_EIGHT_REGION_OVERLAY_FRAME_KINDS
            ),
        }
    )
    for seed in REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS:
        donor = _select_runtime_donor(runtime_by_seed[seed], seed=seed)
        curriculum = action_by_seed[seed]
        frames, provenance = _build_overlay_episode(
            donor,
            curriculum,
            seed=seed,
        )
        source = RegionLearningEpisodeSource(
            scenario_id=REGION_RESOURCE_EIGHT_REGION_OVERLAY_SCENARIO_ID,
            scenario_version=REGION_RESOURCE_EIGHT_REGION_OVERLAY_SCENARIO_VERSION,
            scenario_scale="regions-8-runtime-geometry-action-targets",
            seed=seed,
            episode_id=f"d4-eight-region-action-overlay-seed-{seed:03d}",
            git_commit=source_git_commit,
            git_dirty=False,
            config_sha256=overlay_config_sha,
        )
        stage_region_learning_episode(episode_staging, source, frames)
        overlay_provenance.append(
            {
                "seed": seed,
                "derived_episode_id": source.episode_id,
                "runtime_source_episode_id": donor.source.episode_id,
                "runtime_source_episode_sha256": donor.manifest.episode_sha256,
                "runtime_source_scenario_scale": donor.source.scenario_scale,
                "action_source_episode_id": curriculum.source.episode_id,
                "action_source_episode_sha256": (
                    curriculum.manifest.episode_sha256
                ),
                "frames": provenance,
            }
        )
    finalize_region_learning_dataset(
        episode_staging,
        dataset_dir,
        created_at_utc=config.created_at_utc,
        split_seed=config.split_seed,
        train_fraction=config.train_fraction,
        validation_fraction=config.validation_fraction,
        minimum_unique_seeds=100,
        minimum_unseen_seeds=30,
    )
    shutil.rmtree(episode_staging)
    dataset = load_region_learning_dataset(dataset_dir)
    _validate_composite_dataset(dataset)
    return {
        "dataset": dataset,
        "overlay_provenance": overlay_provenance,
        "overlay_config_sha256": overlay_config_sha,
    }


def _select_runtime_donor(
    episodes: Sequence[LoadedRegionLearningEpisode],
    *,
    seed: int,
) -> LoadedRegionLearningEpisode:
    scales = ("M5N5", "M20N20", "M50N50", "M100N100", "M200N200")
    preferred_scale = scales[seed % len(scales)]
    candidates = sorted(
        (
            episode
            for episode in episodes
            if episode.source.scenario_scale == preferred_scale
        ),
        key=lambda item: (
            item.source.scenario_id,
            item.source.scenario_version,
            item.source.episode_id,
        ),
    )
    if not candidates:
        raise RegionResourceEightRegionCandidateError(
            f"runtime_donor_scale_unavailable:{seed}:{preferred_scale}"
        )
    return candidates[0]


def _build_overlay_episode(
    donor: LoadedRegionLearningEpisode,
    curriculum: LoadedRegionLearningEpisode,
    *,
    seed: int,
) -> tuple[tuple[RegionLearningFrame, ...], list[dict[str, Any]]]:
    curriculum_frames = sorted(
        curriculum.frames, key=lambda frame: frame.frame_index
    )
    kinds = tuple(_curriculum_frame_kind(frame) for frame in curriculum_frames)
    if kinds != REGION_RESOURCE_EIGHT_REGION_OVERLAY_FRAME_KINDS:
        raise RegionResourceEightRegionCandidateError(
            f"curriculum_action_recipe_mismatch:{seed}:{kinds}"
        )
    policy = RuleRegionResourcePolicy()
    frames: list[RegionLearningFrame] = []
    provenance: list[dict[str, Any]] = []
    for frame_index, (kind, curriculum_frame) in enumerate(
        zip(kinds, curriculum_frames, strict=True)
    ):
        donor_frame = donor.frames[frame_index % len(donor.frames)]
        snapshot = _overlay_snapshot(
            donor_frame.snapshot,
            kind=kind,
            seed=seed,
            frame_index=frame_index,
        )
        target = policy.recommend(
            snapshot,
            fallback_reason=f"eight_region_action_overlay:{kind}",
        )
        _validate_overlay_target(kind, target)
        frame = RegionLearningFrame(
            frame_index=frame_index,
            timestamp_s=snapshot.timestamp_s,
            snapshot=snapshot,
            target=RegionLearningTarget.available(
                RegionLearningTargetKind.RULE,
                target,
            ),
            reward=RegionLearningReward.unavailable(
                REGION_RESOURCE_EIGHT_REGION_OVERLAY_REWARD_REASON
            ),
            recommendation=target,
        )
        frames.append(frame)
        provenance.append(
            {
                "frame_index": frame_index,
                "frame_kind": kind,
                "runtime_source_frame_index": donor_frame.frame_index,
                "runtime_snapshot_sha256": _sha256_json(
                    donor_frame.snapshot.to_dict()
                ),
                "action_source_frame_index": curriculum_frame.frame_index,
                "action_recipe_sha256": _sha256_json(
                    curriculum_frame.target.to_dict()
                ),
                "derived_snapshot_sha256": _sha256_json(snapshot.to_dict()),
                "derived_target_sha256": _sha256_json(target.to_dict()),
            }
        )
    return tuple(frames), provenance


def _curriculum_frame_kind(frame: RegionLearningFrame) -> str:
    recommendation = frame.target.recommendation
    if recommendation is None:
        raise RegionResourceEightRegionCandidateError(
            "curriculum_target_unavailable"
        )
    hold_count = sum(action.hold for action in recommendation.actions)
    replan_count = sum(
        action.request_replan for action in recommendation.actions
    )
    transfer_count = len(recommendation.transfers)
    if transfer_count:
        return "transfer"
    if hold_count:
        return "hold"
    if replan_count:
        return "request_replan"
    raise RegionResourceEightRegionCandidateError(
        "curriculum_frame_has_no_supported_action_recipe"
    )


def _overlay_snapshot(
    source: RegionResourceSnapshot,
    *,
    kind: str,
    seed: int,
    frame_index: int,
) -> RegionResourceSnapshot:
    if source.region_count != REGION_RESOURCE_EIGHT_REGION_COUNT:
        raise RegionResourceEightRegionCandidateError(
            "overlay_source_must_have_eight_regions"
        )
    nodes = {
        node.region_id: node for node in sorted(source.regions, key=lambda item: item.region_id)
    }
    edges = {
        edge.edge_id: edge for edge in sorted(source.edges, key=lambda item: item.edge_id)
    }
    ordered_ids = tuple(nodes)
    if kind == "hold":
        region_id = ordered_ids[0]
        nodes[region_id] = replace(
            nodes[region_id],
            degradation_failed=True,
        )
    elif kind == "request_replan":
        region_id = ordered_ids[1]
        nodes[region_id] = replace(
            nodes[region_id],
            assignment_conflict_count=max(
                1, nodes[region_id].assignment_conflict_count
            ),
        )
    elif kind == "transfer":
        edge = _select_overlay_transfer_edge(tuple(edges.values()))
        source_node = nodes[edge.source_region_id]
        target_node = nodes[edge.target_region_id]
        reserve = max(1, source_node.reserve_resources)
        available = max(
            source_node.available_resources,
            source_node.committed_resources + reserve + 3,
        )
        nodes[source_node.region_id] = replace(
            source_node,
            target_demand=0.0,
            high_threat_backlog=0.0,
            d1_uncertainty=0.0,
            d2_uncertainty=0.0,
            d5_visibility=1.0,
            d5_consistency=1.0,
            available_resources=available,
            reserve_resources=reserve,
            communication_latency_s=0.0,
            packet_loss_rate=0.0,
            assignment_conflict_count=0,
            degradation_failed=False,
        )
        target_capacity = max(
            0,
            target_node.available_resources - target_node.reserve_resources,
        )
        nodes[target_node.region_id] = replace(
            target_node,
            target_demand=float(target_capacity + 3),
            high_threat_backlog=0.0,
            assignment_conflict_count=0,
            degradation_failed=False,
        )
        edges[edge.edge_id] = replace(edge, transferable_resources=3)
    else:
        raise RegionResourceEightRegionCandidateError(
            f"unsupported_overlay_frame_kind:{kind}"
        )
    return RegionResourceSnapshot(
        snapshot_id=f"d4-eight-region-overlay-s{seed:03d}-f{frame_index}",
        scenario_id=REGION_RESOURCE_EIGHT_REGION_OVERLAY_SCENARIO_ID,
        scenario_version=REGION_RESOURCE_EIGHT_REGION_OVERLAY_SCENARIO_VERSION,
        seed=seed,
        timestamp_s=float(frame_index),
        regions=tuple(nodes[region_id] for region_id in sorted(nodes)),
        edges=tuple(edges[edge_id] for edge_id in sorted(edges)),
        source_authority_schema=source.source_authority_schema,
    )


def _select_overlay_transfer_edge(
    edges: Sequence[RegionResourceEdge],
) -> RegionResourceEdge:
    candidates = sorted(
        (
            edge
            for edge in edges
            if edge.communication_available
            and edge.maneuver_available
            and not edge.partitioned
            and edge.bandwidth_mbps > 0.0
        ),
        key=lambda item: item.edge_id,
    )
    if not candidates:
        raise RegionResourceEightRegionCandidateError(
            "runtime_geometry_has_no_transfer_edge"
        )
    return candidates[0]


def _validate_overlay_target(kind: str, recommendation: Any) -> None:
    action_count = len(recommendation.actions)
    hold_count = sum(action.hold for action in recommendation.actions)
    replan_count = sum(
        action.request_replan for action in recommendation.actions
    )
    nonzero_count = sum(
        action.resource_quota_delta != 0
        for action in recommendation.actions
    )
    transfer_count = len(recommendation.transfers)
    if action_count != REGION_RESOURCE_EIGHT_REGION_COUNT:
        raise RegionResourceEightRegionCandidateError(
            "overlay_target_does_not_cover_eight_regions"
        )
    supported = {
        "hold": hold_count > 0 and replan_count > 0,
        "request_replan": replan_count > 0 and hold_count == 0,
        "transfer": transfer_count > 0 and nonzero_count > 0,
    }
    if not supported[kind]:
        raise RegionResourceEightRegionCandidateError(
            f"overlay_target_action_missing:{kind}"
        )


def _validate_composite_dataset(
    dataset: LoadedRegionLearningDataset,
) -> None:
    manifest = dataset.manifest
    if (
        manifest.availability.episode_count
        != (
            REGION_RESOURCE_EIGHT_REGION_RUNTIME_EPISODE_COUNT
            + REGION_RESOURCE_EIGHT_REGION_ACTION_EPISODE_COUNT
        )
        or manifest.availability.frame_count
        != (
            REGION_RESOURCE_EIGHT_REGION_RUNTIME_FRAME_COUNT
            + REGION_RESOURCE_EIGHT_REGION_ACTION_FRAME_COUNT
        )
        or manifest.availability.dirty_episode_count != 0
        or not manifest.availability.behavior_cloning_available
    ):
        raise RegionResourceEightRegionCandidateError(
            "composite_dataset_count_or_availability_mismatch"
        )
    seed_sets = {
        RegionLearningSplit.TRAIN: set(manifest.split.train_seeds),
        RegionLearningSplit.VALIDATION: set(manifest.split.validation_seeds),
        RegionLearningSplit.TEST: set(manifest.split.test_seeds),
    }
    if (
        set.union(*seed_sets.values())
        != set(REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS)
        or any(
            left & right
            for left, right in (
                (
                    seed_sets[RegionLearningSplit.TRAIN],
                    seed_sets[RegionLearningSplit.VALIDATION],
                ),
                (
                    seed_sets[RegionLearningSplit.TRAIN],
                    seed_sets[RegionLearningSplit.TEST],
                ),
                (
                    seed_sets[RegionLearningSplit.VALIDATION],
                    seed_sets[RegionLearningSplit.TEST],
                ),
            )
        )
        or set.union(*seed_sets.values())
        & set(REGION_RESOURCE_EIGHT_REGION_RESERVED_SEEDS)
    ):
        raise RegionResourceEightRegionCandidateError(
            "composite_global_seed_split_invalid"
        )
    for episode in dataset.episode_records:
        expected_split = next(
            split for split, seeds in seed_sets.items() if episode.source.seed in seeds
        )
        if episode.split != expected_split:
            raise RegionResourceEightRegionCandidateError(
                "episode_crossed_global_seed_split"
            )
        if any(
            frame.snapshot.region_count != REGION_RESOURCE_EIGHT_REGION_COUNT
            for frame in episode.frames
        ):
            raise RegionResourceEightRegionCandidateError(
                "composite_contains_non_eight_region_frame"
            )
    inventory = _action_inventory(dataset)
    for key in (
        "resource_quota_nonzero_count",
        "transfer_count",
        "hold_true_count",
        "request_replan_true_count",
    ):
        if inventory[key] <= 0:
            raise RegionResourceEightRegionCandidateError(
                f"composite_action_support_missing:{key}"
            )


def _split_usage(
    loaded: LoadedRegionLearningDataset,
) -> RegionResourceCurrentLineageSplitUsage:
    manifest = loaded.manifest
    observed_train = {
        int(item.source.seed)
        for item in loaded.episodes(RegionLearningSplit.TRAIN)
    }
    observed_validation = {
        int(item.source.seed)
        for item in loaded.episodes(RegionLearningSplit.VALIDATION)
    }
    if (
        observed_train != set(manifest.split.train_seeds)
        or observed_validation != set(manifest.split.validation_seeds)
    ):
        raise RegionResourceEightRegionCandidateError(
            "loaded_train_validation_seed_inventory_mismatch"
        )
    return RegionResourceCurrentLineageSplitUsage(
        train_seeds=manifest.split.train_seeds,
        validation_seeds=manifest.split.validation_seeds,
        untouched_test_seeds=manifest.split.test_seeds,
        train_payload_read_count=len(
            loaded.episodes(RegionLearningSplit.TRAIN)
        ),
        validation_payload_read_count=len(
            loaded.episodes(RegionLearningSplit.VALIDATION)
        ),
    )


def _build_training_view_manifest(
    runtime: LoadedRegionLearningDataset,
    action: LoadedRegionLearningDataset,
    composite: Mapping[str, Any],
    *,
    split_usage: RegionResourceCurrentLineageSplitUsage,
    source_summary: Mapping[str, Any],
    config: RegionResourceEightRegionCandidateConfig,
) -> dict[str, Any]:
    dataset = composite["dataset"]
    action_by_split = {
        split.value: _action_inventory(dataset, split=split)
        for split in RegionLearningSplit
    }
    payload = {
        "schema": REGION_RESOURCE_EIGHT_REGION_VIEW_SCHEMA,
        "view_recipe": REGION_RESOURCE_EIGHT_REGION_VIEW_RECIPE,
        "created_at_utc": config.created_at_utc,
        "sources": {
            "runtime": _source_dataset_inventory(runtime),
            "action_curriculum": _source_dataset_inventory(action),
        },
        "composite": {
            "dataset_sha256": dataset.manifest.dataset_sha256,
            "dataset_manifest_file_sha256": _sha256_file(
                dataset.root / "manifest.json"
            ),
            "episode_count": dataset.manifest.availability.episode_count,
            "frame_count": dataset.manifest.availability.frame_count,
            "region_count": REGION_RESOURCE_EIGHT_REGION_COUNT,
            "runtime_frame_count": (
                REGION_RESOURCE_EIGHT_REGION_RUNTIME_FRAME_COUNT
            ),
            "overlay_frame_count": (
                REGION_RESOURCE_EIGHT_REGION_ACTION_FRAME_COUNT
            ),
            "overlay_config_sha256": composite["overlay_config_sha256"],
            "episode_inventory_sha256": _episode_inventory_sha256(
                dataset
            ),
            "frame_inventory_sha256": _frame_inventory_sha256(dataset),
        },
        "global_split": {
            **dataset.manifest.split.to_dict(),
            "split_usage": split_usage.to_dict(),
            "seed_atomic_across_all_sources": True,
            "seed_overlap_count": 0,
            "reserved_evaluation_seeds": list(
                REGION_RESOURCE_EIGHT_REGION_RESERVED_SEEDS
            ),
            "reserved_seed_presence_count": 0,
        },
        "feature_schema": {
            "schema": REGION_RESOURCE_FEATURE_SCHEMA,
            "node_feature_names": list(NODE_FEATURE_NAMES),
            "edge_feature_names": list(EDGE_FEATURE_NAMES),
            "feature_semantics_sha256": _sha256_json(
                REGION_LEARNING_FEATURE_SEMANTICS
            ),
            "applicable_region_count": REGION_RESOURCE_EIGHT_REGION_COUNT,
            "runtime_geometry_source": "runtime",
        },
        "label_source": {
            "source": "truth_free_deterministic_rule_and_safety_projection",
            "policy_name": RuleRegionResourcePolicy.policy_name,
            "policy_version": RuleRegionResourcePolicy.policy_version,
            "projector_name": DETERMINISTIC_RESOURCE_PROJECTOR_NAME,
            "projector_version": DETERMINISTIC_RESOURCE_PROJECTOR_VERSION,
            "curriculum_role": "action_recipe_only",
            "frame_kinds": list(
                REGION_RESOURCE_EIGHT_REGION_OVERLAY_FRAME_KINDS
            ),
            "truth_identifier_use_count": 0,
            "evaluation_label_use_count": 0,
        },
        "confidence_supervision": _confidence_supervision_definition(config),
        "action_inventory": {
            "runtime_source": _action_inventory(runtime),
            "action_curriculum_source": _action_inventory(action),
            "composite_total": _action_inventory(dataset),
            "composite_by_split": action_by_split,
        },
        "overlay_provenance": composite["overlay_provenance"],
        "source_identity_sha256": source_summary["source_identity_sha256"],
        "runtime_preflight_completed": False,
        "formal_evaluation_authorized": False,
        "permissions": RegionResourceEightRegionPermissions().to_dict(),
    }
    payload["content_sha256"] = _sha256_json(payload)
    _validate_training_view_manifest(payload)
    return payload


def _source_dataset_inventory(
    dataset: LoadedRegionLearningDataset,
) -> dict[str, Any]:
    files = [
        {
            "relative_path": "manifest.json",
            "sha256": _sha256_file(dataset.root / "manifest.json"),
            "record_type": "manifest",
        }
    ]
    for entry in dataset.manifest.episodes:
        files.append(
            {
                "relative_path": entry.relative_path,
                "sha256": entry.episode_sha256,
                "record_type": "episode",
                "episode_id": entry.source.episode_id,
                "seed": int(entry.source.seed),
                "frame_count": int(entry.frame_count),
                "scenario_id": entry.source.scenario_id,
                "scenario_version": entry.source.scenario_version,
                "scenario_scale": entry.source.scenario_scale,
            }
        )
    return {
        "dataset_sha256": dataset.manifest.dataset_sha256,
        "dataset_split_sha256": dataset.manifest.split.split_sha256,
        "episode_count": dataset.manifest.availability.episode_count,
        "frame_count": dataset.manifest.availability.frame_count,
        "seed_inventory": sorted(
            {int(item.source.seed) for item in dataset.episode_records}
        ),
        "episode_inventory_sha256": _episode_inventory_sha256(dataset),
        "frame_inventory_sha256": _frame_inventory_sha256(dataset),
        "action_inventory": _action_inventory(dataset),
        "file_inventory": files,
        "file_inventory_sha256": _sha256_json(files),
    }


def _validate_source_summary(value: Mapping[str, Any]) -> None:
    expected = {
        "schema",
        "git_commit",
        "git_tree",
        "committed_training_implementation_files",
        "committed_training_implementation_sha256",
        "view_builder_file",
        "view_builder_file_sha256",
        "view_recipe",
        "training_core_matches_commit",
        "view_builder_content_addressed",
        "source_identity_sha256",
        "content_sha256",
    }
    _require_exact_keys(value, expected, "source_summary")
    if (
        value["schema"] != REGION_RESOURCE_EIGHT_REGION_SOURCE_SCHEMA
        or value["view_recipe"] != REGION_RESOURCE_EIGHT_REGION_VIEW_RECIPE
        or value["training_core_matches_commit"] is not True
        or value["view_builder_content_addressed"] is not True
    ):
        raise RegionResourceEightRegionCandidateError(
            "source_summary_boundary_invalid"
        )
    for name in (
        "committed_training_implementation_sha256",
        "view_builder_file_sha256",
        "source_identity_sha256",
        "content_sha256",
    ):
        _require_sha256(str(value[name]), f"source_summary.{name}")
    files = value["committed_training_implementation_files"]
    if set(files) != set(_COMMITTED_TRAINING_IMPLEMENTATION_FILES):
        raise RegionResourceEightRegionCandidateError(
            "source_summary_implementation_inventory_incomplete"
        )
    if (
        _sha256_json(files)
        != value["committed_training_implementation_sha256"]
    ):
        raise RegionResourceEightRegionCandidateError(
            "source_summary_implementation_hash_mismatch"
        )
    content = dict(value)
    observed_content_sha = content.pop("content_sha256")
    observed_identity = content.pop("source_identity_sha256")
    if _sha256_json(content) != observed_identity:
        raise RegionResourceEightRegionCandidateError(
            "source_summary_identity_mismatch"
        )
    content["source_identity_sha256"] = observed_identity
    if _sha256_json(content) != observed_content_sha:
        raise RegionResourceEightRegionCandidateError(
            "source_summary_content_mismatch"
        )


def _validate_training_view_manifest(value: Mapping[str, Any]) -> None:
    expected = {
        "schema",
        "view_recipe",
        "created_at_utc",
        "sources",
        "composite",
        "global_split",
        "feature_schema",
        "label_source",
        "confidence_supervision",
        "action_inventory",
        "overlay_provenance",
        "source_identity_sha256",
        "runtime_preflight_completed",
        "formal_evaluation_authorized",
        "permissions",
        "content_sha256",
    }
    _require_exact_keys(value, expected, "training_view_manifest")
    if (
        value["schema"] != REGION_RESOURCE_EIGHT_REGION_VIEW_SCHEMA
        or value["view_recipe"] != REGION_RESOURCE_EIGHT_REGION_VIEW_RECIPE
        or value["runtime_preflight_completed"] is not False
        or value["formal_evaluation_authorized"] is not False
    ):
        raise RegionResourceEightRegionCandidateError(
            "training_view_boundary_invalid"
        )
    _require_sha256(
        str(value["source_identity_sha256"]),
        "training_view.source_identity_sha256",
    )
    sources = value["sources"]
    if set(sources) != {"runtime", "action_curriculum"}:
        raise RegionResourceEightRegionCandidateError(
            "training_view_source_inventory_invalid"
        )
    if (
        sources["runtime"]["dataset_sha256"]
        != REGION_RESOURCE_EIGHT_REGION_RUNTIME_DATASET_SHA256
        or sources["action_curriculum"]["dataset_sha256"]
        != REGION_RESOURCE_EIGHT_REGION_ACTION_DATASET_SHA256
        or sources["runtime"]["episode_count"]
        != REGION_RESOURCE_EIGHT_REGION_RUNTIME_EPISODE_COUNT
        or sources["runtime"]["frame_count"]
        != REGION_RESOURCE_EIGHT_REGION_RUNTIME_FRAME_COUNT
        or sources["action_curriculum"]["episode_count"]
        != REGION_RESOURCE_EIGHT_REGION_ACTION_EPISODE_COUNT
        or sources["action_curriculum"]["frame_count"]
        != REGION_RESOURCE_EIGHT_REGION_ACTION_FRAME_COUNT
    ):
        raise RegionResourceEightRegionCandidateError(
            "training_view_source_binding_mismatch"
        )
    for source_name, source in sources.items():
        if (
            source["seed_inventory"]
            != list(REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS)
            or set(source["seed_inventory"])
            & set(REGION_RESOURCE_EIGHT_REGION_RESERVED_SEEDS)
            or _sha256_json(source["file_inventory"])
            != source["file_inventory_sha256"]
        ):
            raise RegionResourceEightRegionCandidateError(
                f"training_view_source_inventory_mismatch:{source_name}"
            )
    split = value["global_split"]
    train = set(split["train_seeds"])
    validation = set(split["validation_seeds"])
    test = set(split["test_seeds"])
    if (
        train | validation | test
        != set(REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS)
        or train & validation
        or train & test
        or validation & test
        or (train | validation | test)
        & set(REGION_RESOURCE_EIGHT_REGION_RESERVED_SEEDS)
        or split["reserved_evaluation_seeds"]
        != list(REGION_RESOURCE_EIGHT_REGION_RESERVED_SEEDS)
        or split["seed_atomic_across_all_sources"] is not True
        or split["seed_overlap_count"] != 0
        or split["reserved_seed_presence_count"] != 0
    ):
        raise RegionResourceEightRegionCandidateError(
            "training_view_global_split_invalid"
        )
    if value["feature_schema"] != {
        "schema": REGION_RESOURCE_FEATURE_SCHEMA,
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "feature_semantics_sha256": _sha256_json(
            REGION_LEARNING_FEATURE_SEMANTICS
        ),
        "applicable_region_count": REGION_RESOURCE_EIGHT_REGION_COUNT,
        "runtime_geometry_source": "runtime",
    }:
        raise RegionResourceEightRegionCandidateError(
            "training_view_feature_schema_mismatch"
        )
    if (
        value["label_source"]["truth_identifier_use_count"] != 0
        or value["label_source"]["evaluation_label_use_count"] != 0
        or value["label_source"]["curriculum_role"] != "action_recipe_only"
    ):
        raise RegionResourceEightRegionCandidateError(
            "training_view_label_source_invalid"
        )
    confidence_definition = value["confidence_supervision"]
    expected_confidence_definition = (
        _confidence_supervision_definition_from_values(
            confidence_epochs=int(confidence_definition["fit_epochs"]),
            confidence_batch_size=int(
                confidence_definition["fit_batch_size"]
            ),
            confidence_learning_rate=float(
                confidence_definition["fit_learning_rate"]
            ),
            confidence_loss_weight=float(
                confidence_definition["loss_weight"]
            ),
            continuous_tolerance=float(
                confidence_definition["continuous_tolerance"]
            ),
            inconsistent_target_ceiling=float(
                confidence_definition["inconsistent_target_ceiling"]
            ),
            fixed_minimum_confidence=float(
                confidence_definition["fixed_minimum_confidence"]
            ),
        )
    )
    if confidence_definition != expected_confidence_definition:
        raise RegionResourceEightRegionCandidateError(
            "training_view_confidence_definition_mismatch"
        )
    if (
        confidence_definition["fixed_minimum_confidence"]
        != REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE
        or confidence_definition["fixed_minimum_confidence"] != 0.60
        or confidence_definition["inconsistent_target_ceiling"] >= 0.60
        or confidence_definition["loss_weight"] != 1.0
        or confidence_definition["test_split_use_count"] != 0
        or confidence_definition["reserved_evaluation_seed_use_count"] != 0
        or confidence_definition["truth_identifier_use_count"] != 0
        or confidence_definition["future_outcome_use_count"] != 0
        or confidence_definition["constant_positive_label_use_count"] != 0
        or confidence_definition["action_model_frozen_during_fit"] is not True
    ):
        raise RegionResourceEightRegionCandidateError(
            "training_view_confidence_boundary_crossed"
        )
    inventory = value["action_inventory"]["composite_total"]
    for key in (
        "resource_quota_nonzero_count",
        "transfer_count",
        "hold_true_count",
        "request_replan_true_count",
    ):
        if int(inventory[key]) <= 0:
            raise RegionResourceEightRegionCandidateError(
                f"training_view_action_support_missing:{key}"
            )
    if (
        len(value["overlay_provenance"])
        != REGION_RESOURCE_EIGHT_REGION_ACTION_EPISODE_COUNT
        or {item["seed"] for item in value["overlay_provenance"]}
        != set(REGION_RESOURCE_EIGHT_REGION_TRAINING_SEEDS)
    ):
        raise RegionResourceEightRegionCandidateError(
            "training_view_overlay_provenance_incomplete"
        )
    _reject_truth_identifiers(value, path="training_view")
    RegionResourceEightRegionPermissions.from_mapping(value["permissions"])
    content = dict(value)
    observed_content_sha = str(content.pop("content_sha256", ""))
    _require_sha256(
        observed_content_sha, "training_view_manifest.content_sha256"
    )
    if _sha256_json(content) != observed_content_sha:
        raise RegionResourceEightRegionCandidateError(
            "training_view_content_sha256_mismatch"
        )


def _action_inventory(
    dataset: LoadedRegionLearningDataset,
    *,
    split: RegionLearningSplit | None = None,
) -> dict[str, int]:
    inventory = {
        "action_count": 0,
        "resource_quota_nonzero_count": 0,
        "transfer_count": 0,
        "hold_true_count": 0,
        "request_replan_true_count": 0,
    }
    for episode in dataset.episodes(split):
        for frame in episode.frames:
            recommendation = frame.target.recommendation
            if recommendation is None:
                raise RegionResourceEightRegionCandidateError(
                    "target_recommendation_unavailable"
                )
            inventory["action_count"] += len(recommendation.actions)
            inventory["resource_quota_nonzero_count"] += sum(
                action.resource_quota_delta != 0
                for action in recommendation.actions
            )
            inventory["transfer_count"] += len(recommendation.transfers)
            inventory["hold_true_count"] += sum(
                action.hold for action in recommendation.actions
            )
            inventory["request_replan_true_count"] += sum(
                action.request_replan for action in recommendation.actions
            )
    return inventory


def _episode_inventory_sha256(
    dataset: LoadedRegionLearningDataset,
) -> str:
    return _sha256_json(
        [
            {
                "relative_path": entry.relative_path,
                "episode_sha256": entry.episode_sha256,
                "source_identity_sha256": entry.source.identity_sha256,
                "seed": int(entry.source.seed),
                "frame_count": int(entry.frame_count),
                "split": entry.split.value,
            }
            for entry in dataset.manifest.episodes
        ]
    )


def _frame_inventory_sha256(
    dataset: LoadedRegionLearningDataset,
) -> str:
    return _sha256_json(
        [
            {
                "episode_sha256": entry.episode_sha256,
                "frame_count": int(entry.frame_count),
                "first_frame_index": int(entry.first_frame_index),
                "last_frame_index": int(entry.last_frame_index),
                "first_timestamp_s": float(entry.first_timestamp_s),
                "last_timestamp_s": float(entry.last_timestamp_s),
            }
            for entry in dataset.manifest.episodes
        ]
    )


def _reject_truth_identifiers(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            current = f"{path}.{key}"
            if normalized in _FORBIDDEN_TRUTH_KEYS or (
                "truth" in normalized and normalized not in {"truth_identifier_use_count"}
            ):
                raise RegionResourceEightRegionCandidateError(
                    f"forbidden_truth_identifier:{current}"
                )
            _reject_truth_identifiers(item, path=current)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_truth_identifiers(item, path=f"{path}[{index}]")


def _read_json_object(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegionResourceEightRegionCandidateError(
            f"{name}_unavailable_or_invalid"
        ) from exc
    if not isinstance(value, dict):
        raise RegionResourceEightRegionCandidateError(
            f"{name}_must_be_json_object"
        )
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: Iterable[str],
    name: str,
) -> None:
    expected_set = set(expected)
    actual = set(value)
    if actual != expected_set:
        raise ValueError(
            f"{name} keys mismatch:"
            f"missing={sorted(expected_set - actual)};"
            f"extra={sorted(actual - expected_set)}"
        )


def _require_sha256(value: str, name: str) -> None:
    if (
        len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256")


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


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
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _git_text(root: Path, *args: str) -> str:
    return _git_bytes(root, *args).decode("utf-8").strip()


def _git_bytes(root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(
            ("git", "-C", str(root), *args),
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        raise RegionResourceEightRegionCandidateError(
            "source_git_command_failed:"
            + exc.output.decode("utf-8", errors="replace").strip()
        ) from exc
