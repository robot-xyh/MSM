"""Clean-lineage construction and review for a D4 A2 development candidate.

This boundary deliberately uses only the existing train and validation splits.
The dataset test split, the historical calibration split, and reserved formal
evaluation seeds are not loaded or used for model selection. The resulting
bundle is development/shadow only and cannot grant any runtime permission.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
from typing import Any, Iterable, Mapping, Sequence

try:
    import torch
except ImportError:  # pragma: no cover - optional dependency guard
    torch = None

from .region_resource import RegionResourceRecommendation
from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningSplit,
    load_region_learning_dataset_splits,
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
    save_region_resource_model_bundle,
)


REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_SCHEMA = (
    "d4-region-resource-current-lineage-candidate-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_SCHEMA = (
    "d4-region-resource-current-lineage-source-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_DATASET_SCHEMA = (
    "d4-region-resource-current-lineage-dataset-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_TRAINING_SCHEMA = (
    "d4-region-resource-current-lineage-training-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_REVIEW_SCHEMA = (
    "d4-region-resource-current-lineage-review-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_CONFIG_SCHEMA = (
    "d4-region-resource-current-lineage-config-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_FILENAME = (
    "current_lineage_candidate_manifest.json"
)
REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_FILENAME = (
    "source_implementation_summary.json"
)
REGION_RESOURCE_CURRENT_LINEAGE_DATASET_FILENAME = "dataset_summary.json"
REGION_RESOURCE_CURRENT_LINEAGE_CONFIG_FILENAME = "training_config.json"
REGION_RESOURCE_CURRENT_LINEAGE_TRAINING_FILENAME = "training_summary.json"
REGION_RESOURCE_CURRENT_LINEAGE_MODEL_VERSION = (
    "d4-region-a2-current-lineage-development-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID = (
    "region_resource_a2_current_lineage_development_v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_IMPLEMENTATION_FILES = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_dataset.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_learning.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_training.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_current_lineage_candidate.py",
)
REGION_RESOURCE_CURRENT_LINEAGE_RESERVED_SEEDS = tuple(range(1000, 1020))
_CANDIDATE_ARTIFACT_FILES = {
    REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_FILENAME,
    REGION_RESOURCE_CURRENT_LINEAGE_DATASET_FILENAME,
    REGION_RESOURCE_CURRENT_LINEAGE_CONFIG_FILENAME,
    REGION_RESOURCE_CURRENT_LINEAGE_TRAINING_FILENAME,
    "bundle/manifest.json",
    "bundle/state_dict.pt",
    "bundle/training_dataset_manifest.json",
}
_PERMISSION_FIELDS = (
    "a2_admitted",
    "assist_enabled",
    "authority_enabled",
    "assignment_enabled",
    "takeover_enabled",
    "coalition_commit_enabled",
    "control_enabled",
    "actual_adoption_claimed",
    "benefit_claimed",
)


class RegionResourceCurrentLineageCandidateError(RuntimeError):
    """Stable fail-closed error at the current-lineage candidate boundary."""


@dataclass(frozen=True)
class RegionResourceCurrentLineageCandidateConfig:
    random_seed: int = 20260728
    hidden_dim: int = 64
    message_passing_steps: int = 2
    epochs: int = 60
    batch_size: int = 32
    learning_rate: float = 8.0e-4
    weight_decay: float = 1.0e-5
    max_grad_norm: float = 1.0
    early_stopping_patience: int = 10
    device: str = "cpu"
    torch_num_threads: int = 1
    model_version: str = REGION_RESOURCE_CURRENT_LINEAGE_MODEL_VERSION
    candidate_id: str = REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID
    created_at_utc: str = "2026-07-28T00:00:00Z"
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_CONFIG_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_CURRENT_LINEAGE_CONFIG_SCHEMA:
            raise ValueError("unsupported current-lineage config schema")
        for name in (
            "random_seed",
            "hidden_dim",
            "message_passing_steps",
            "epochs",
            "batch_size",
            "early_stopping_patience",
            "torch_num_threads",
        ):
            if type(getattr(self, name)) is not int or int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("learning_rate", "max_grad_norm"):
            value = float(getattr(self, name))
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not isfinite(float(self.weight_decay)) or self.weight_decay < 0.0:
            raise ValueError("weight_decay must be finite and non-negative")
        if (
            not self.model_version
            or not self.candidate_id
            or Path(self.candidate_id).name != self.candidate_id
        ):
            raise ValueError("candidate and model identities must be safe and non-empty")
        if not self.created_at_utc:
            raise ValueError("created_at_utc must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageCandidateConfig":
        _require_exact_keys(value, set(cls.__dataclass_fields__), "training_config")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceCurrentLineageSourceSummary:
    git_commit: str
    git_tree: str
    implementation_sha256: str
    implementation_files: Mapping[str, str]
    source_identity_sha256: str
    worktree_clean: bool = True
    dirty_entry_count: int = 0
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_SCHEMA:
            raise ValueError("unsupported current-lineage source schema")
        _require_git_object_id(self.git_commit, "git_commit")
        _require_git_object_id(self.git_tree, "git_tree")
        implementation = {
            str(path): str(digest).lower()
            for path, digest in self.implementation_files.items()
        }
        if set(implementation) != set(
            REGION_RESOURCE_CURRENT_LINEAGE_IMPLEMENTATION_FILES
        ):
            raise ValueError("current-lineage implementation inventory is incomplete")
        for path, digest in implementation.items():
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("current-lineage implementation path is unsafe")
            _require_sha256(digest, f"implementation_files.{path}")
        if _sha256_json(implementation) != self.implementation_sha256:
            raise ValueError("implementation aggregate SHA256 mismatch")
        expected_identity = _sha256_json(
            {
                "git_commit": self.git_commit,
                "git_tree": self.git_tree,
                "implementation_sha256": self.implementation_sha256,
                "implementation_files": dict(sorted(implementation.items())),
            }
        )
        if self.source_identity_sha256 != expected_identity:
            raise ValueError("source identity SHA256 mismatch")
        if self.worktree_clean is not True or int(self.dirty_entry_count) != 0:
            raise ValueError("current-lineage source must describe a clean worktree")
        object.__setattr__(self, "implementation_files", implementation)
        expected_content = _sha256_json(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected_content:
            raise ValueError("source summary content SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected_content)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "git_commit": self.git_commit,
            "git_tree": self.git_tree,
            "implementation_sha256": self.implementation_sha256,
            "implementation_files": dict(sorted(self.implementation_files.items())),
            "source_identity_sha256": self.source_identity_sha256,
            "worktree_clean": self.worktree_clean,
            "dirty_entry_count": int(self.dirty_entry_count),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageSourceSummary":
        _require_exact_keys(value, set(cls.__dataclass_fields__), "source_summary")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceCurrentLineageSplitUsage:
    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    untouched_test_seeds: tuple[int, ...]
    reserved_evaluation_seeds: tuple[int, ...] = (
        REGION_RESOURCE_CURRENT_LINEAGE_RESERVED_SEEDS
    )
    training_split: str = RegionLearningSplit.TRAIN.value
    selection_split: str = RegionLearningSplit.VALIDATION.value
    train_payload_read_count: int = 0
    validation_payload_read_count: int = 0
    test_payload_read_count: int = 0
    calibration_seed_use_count: int = 0
    reserved_seed_use_count: int = 0

    def __post_init__(self) -> None:
        catalogs = {
            "train": _canonical_seed_tuple(self.train_seeds),
            "validation": _canonical_seed_tuple(self.validation_seeds),
            "test": _canonical_seed_tuple(self.untouched_test_seeds),
            "reserved": _canonical_seed_tuple(self.reserved_evaluation_seeds),
        }
        if any(not values for values in catalogs.values()):
            raise ValueError("current-lineage split catalogs must not be empty")
        names = tuple(catalogs)
        for index, left in enumerate(names):
            for right in names[index + 1 :]:
                if set(catalogs[left]) & set(catalogs[right]):
                    raise ValueError("current-lineage split seed catalogs overlap")
        if catalogs["reserved"] != REGION_RESOURCE_CURRENT_LINEAGE_RESERVED_SEEDS:
            raise ValueError("reserved evaluation seed catalog changed")
        if (
            self.training_split != RegionLearningSplit.TRAIN.value
            or self.selection_split != RegionLearningSplit.VALIDATION.value
        ):
            raise ValueError("candidate training and selection splits changed")
        if (
            int(self.train_payload_read_count) <= 0
            or int(self.validation_payload_read_count) <= 0
        ):
            raise ValueError("train and validation payload counts must be positive")
        if (
            type(self.test_payload_read_count) is not int
            or type(self.calibration_seed_use_count) is not int
            or type(self.reserved_seed_use_count) is not int
            or self.test_payload_read_count != 0
            or self.calibration_seed_use_count != 0
            or self.reserved_seed_use_count != 0
        ):
            raise ValueError("test, calibration, and reserved seed use must remain zero")
        object.__setattr__(self, "train_seeds", catalogs["train"])
        object.__setattr__(self, "validation_seeds", catalogs["validation"])
        object.__setattr__(self, "untouched_test_seeds", catalogs["test"])
        object.__setattr__(self, "reserved_evaluation_seeds", catalogs["reserved"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_seeds": list(self.train_seeds),
            "validation_seeds": list(self.validation_seeds),
            "untouched_test_seeds": list(self.untouched_test_seeds),
            "reserved_evaluation_seeds": list(self.reserved_evaluation_seeds),
            "training_split": self.training_split,
            "selection_split": self.selection_split,
            "train_payload_read_count": int(self.train_payload_read_count),
            "validation_payload_read_count": int(
                self.validation_payload_read_count
            ),
            "test_payload_read_count": int(self.test_payload_read_count),
            "calibration_seed_use_count": int(self.calibration_seed_use_count),
            "reserved_seed_use_count": int(self.reserved_seed_use_count),
        }

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageSplitUsage":
        _require_exact_keys(value, set(cls.__dataclass_fields__), "split_usage")
        payload = dict(value)
        for name in (
            "train_seeds",
            "validation_seeds",
            "untouched_test_seeds",
            "reserved_evaluation_seeds",
        ):
            payload[name] = tuple(payload[name])
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceCurrentLineagePermissions:
    a2_admitted: bool = False
    assist_enabled: bool = False
    authority_enabled: bool = False
    assignment_enabled: bool = False
    takeover_enabled: bool = False
    coalition_commit_enabled: bool = False
    control_enabled: bool = False
    actual_adoption_claimed: bool = False
    benefit_claimed: bool = False

    def __post_init__(self) -> None:
        for name in _PERMISSION_FIELDS:
            value = getattr(self, name)
            if type(value) is not bool or value:
                raise ValueError(
                    "current-lineage development candidate cannot grant permissions"
                )

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in _PERMISSION_FIELDS}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineagePermissions":
        _require_exact_keys(value, set(_PERMISSION_FIELDS), "permissions")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceCurrentLineageCandidateManifest:
    candidate_id: str
    model_version: str
    source_summary_file_sha256: str
    source_identity_sha256: str
    dataset_summary_file_sha256: str
    dataset_manifest_file_sha256: str
    dataset_sha256: str
    dataset_split_sha256: str
    config_file_sha256: str
    config_sha256: str
    training_summary_file_sha256: str
    training_summary_content_sha256: str
    bundle_manifest_sha256: str
    model_state_sha256: str
    bundle_training_manifest_sha256: str
    split_usage: RegionResourceCurrentLineageSplitUsage
    validation_sample_count: int
    validation_nonfinite_output_count: int
    artifact_files: Mapping[str, str]
    permissions: RegionResourceCurrentLineagePermissions = (
        RegionResourceCurrentLineagePermissions()
    )
    lifecycle_stage: str = MODEL_LIFECYCLE_DEVELOPMENT
    maximum_advisor_mode: str = MODEL_MAXIMUM_MODE_SHADOW
    development_shadow_candidate: bool = True
    formal_holdout_evaluated: bool = False
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_SCHEMA:
            raise ValueError("unsupported current-lineage candidate schema")
        if (
            not self.candidate_id
            or Path(self.candidate_id).name != self.candidate_id
            or not self.model_version
        ):
            raise ValueError("candidate identities must be safe and non-empty")
        for name in (
            "source_summary_file_sha256",
            "source_identity_sha256",
            "dataset_summary_file_sha256",
            "dataset_manifest_file_sha256",
            "dataset_sha256",
            "dataset_split_sha256",
            "config_file_sha256",
            "config_sha256",
            "training_summary_file_sha256",
            "training_summary_content_sha256",
            "bundle_manifest_sha256",
            "model_state_sha256",
            "bundle_training_manifest_sha256",
        ):
            _require_sha256(str(getattr(self, name)), name)
        artifacts = {
            str(path): str(digest).lower()
            for path, digest in self.artifact_files.items()
        }
        if set(artifacts) != _CANDIDATE_ARTIFACT_FILES:
            raise ValueError("current-lineage artifact inventory is incomplete")
        for path, digest in artifacts.items():
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("current-lineage artifact path is unsafe")
            _require_sha256(digest, f"artifact_files.{path}")
        expected_bindings = {
            REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_FILENAME: (
                self.source_summary_file_sha256
            ),
            REGION_RESOURCE_CURRENT_LINEAGE_DATASET_FILENAME: (
                self.dataset_summary_file_sha256
            ),
            REGION_RESOURCE_CURRENT_LINEAGE_CONFIG_FILENAME: self.config_file_sha256,
            REGION_RESOURCE_CURRENT_LINEAGE_TRAINING_FILENAME: (
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
        if not isinstance(
            self.split_usage, RegionResourceCurrentLineageSplitUsage
        ):
            raise ValueError("candidate split usage is invalid")
        if not isinstance(
            self.permissions, RegionResourceCurrentLineagePermissions
        ):
            raise ValueError("candidate permissions are invalid")
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
            or self.development_shadow_candidate is not True
            or self.formal_holdout_evaluated is not False
        ):
            raise ValueError("candidate crossed the development/shadow boundary")
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
            "dataset_summary_file_sha256": self.dataset_summary_file_sha256,
            "dataset_manifest_file_sha256": self.dataset_manifest_file_sha256,
            "dataset_sha256": self.dataset_sha256,
            "dataset_split_sha256": self.dataset_split_sha256,
            "config_file_sha256": self.config_file_sha256,
            "config_sha256": self.config_sha256,
            "training_summary_file_sha256": self.training_summary_file_sha256,
            "training_summary_content_sha256": (
                self.training_summary_content_sha256
            ),
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "model_state_sha256": self.model_state_sha256,
            "bundle_training_manifest_sha256": (
                self.bundle_training_manifest_sha256
            ),
            "split_usage": self.split_usage.to_dict(),
            "validation_sample_count": int(self.validation_sample_count),
            "validation_nonfinite_output_count": int(
                self.validation_nonfinite_output_count
            ),
            "artifact_files": dict(sorted(self.artifact_files.items())),
            "permissions": self.permissions.to_dict(),
            "lifecycle_stage": self.lifecycle_stage,
            "maximum_advisor_mode": self.maximum_advisor_mode,
            "development_shadow_candidate": self.development_shadow_candidate,
            "formal_holdout_evaluated": self.formal_holdout_evaluated,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageCandidateManifest":
        _require_exact_keys(value, set(cls.__dataclass_fields__), "candidate_manifest")
        payload = dict(value)
        payload["split_usage"] = (
            RegionResourceCurrentLineageSplitUsage.from_mapping(
                payload["split_usage"]
            )
        )
        payload["permissions"] = RegionResourceCurrentLineagePermissions.from_mapping(
            payload["permissions"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceCurrentLineageCandidateReview:
    candidate_id: str
    model_version: str
    source_identity_sha256: str
    dataset_sha256: str
    dataset_split_sha256: str
    model_state_sha256: str
    validation_sample_count: int
    validation_nonfinite_output_count: int
    clean_lineage_verified: bool = True
    train_validation_only_verified: bool = True
    bundle_loadable: bool = True
    development_shadow_verified: bool = True
    a2_admitted: bool = False
    actual_adoption_claimed: bool = False
    benefit_claimed: bool = False
    authority_granted: bool = False
    assignment_authority_granted: bool = False
    takeover_authority_granted: bool = False
    control_authority_granted: bool = False
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_REVIEW_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_CURRENT_LINEAGE_REVIEW_SCHEMA:
            raise ValueError("unsupported current-lineage review schema")
        if not all(
            (
                self.clean_lineage_verified,
                self.train_validation_only_verified,
                self.bundle_loadable,
                self.development_shadow_verified,
            )
        ):
            raise ValueError("successful review must verify every software boundary")
        for name in (
            "a2_admitted",
            "actual_adoption_claimed",
            "benefit_claimed",
            "authority_granted",
            "assignment_authority_granted",
            "takeover_authority_granted",
            "control_authority_granted",
        ):
            if type(getattr(self, name)) is not bool or getattr(self, name):
                raise ValueError("development review cannot grant runtime permissions")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_region_resource_current_lineage(
    repository_root: str | Path,
) -> RegionResourceCurrentLineageSourceSummary:
    """Inspect a clean tracked source tree without accepting bypass flags."""

    root = Path(repository_root).resolve()
    observed_root = Path(
        _git_text(root, "rev-parse", "--show-toplevel").strip()
    ).resolve()
    if observed_root != root:
        raise RegionResourceCurrentLineageCandidateError(
            "source_repository_root_mismatch"
        )
    status = _git_text(
        root, "status", "--porcelain=v1", "--untracked-files=all"
    )
    dirty_entries = tuple(line for line in status.splitlines() if line)
    if dirty_entries:
        raise RegionResourceCurrentLineageCandidateError(
            f"source_worktree_dirty:{len(dirty_entries)}"
        )
    git_commit = _git_text(root, "rev-parse", "--verify", "HEAD").strip()
    git_tree = _git_text(root, "rev-parse", "--verify", "HEAD^{tree}").strip()
    implementation: dict[str, str] = {}
    for relative_path in REGION_RESOURCE_CURRENT_LINEAGE_IMPLEMENTATION_FILES:
        path = root / relative_path
        if path.is_symlink() or not path.is_file():
            raise RegionResourceCurrentLineageCandidateError(
                f"source_implementation_file_unavailable:{relative_path}"
            )
        _git_bytes(root, "ls-files", "--error-unmatch", "--", relative_path)
        committed = _git_bytes(root, "show", f"HEAD:{relative_path}")
        working = path.read_bytes()
        if committed != working:
            raise RegionResourceCurrentLineageCandidateError(
                f"source_implementation_content_mismatch:{relative_path}"
            )
        implementation[relative_path] = _sha256_bytes(working)
    implementation_sha256 = _sha256_json(implementation)
    source_identity_sha256 = _sha256_json(
        {
            "git_commit": git_commit,
            "git_tree": git_tree,
            "implementation_sha256": implementation_sha256,
            "implementation_files": dict(sorted(implementation.items())),
        }
    )
    return RegionResourceCurrentLineageSourceSummary(
        git_commit=git_commit,
        git_tree=git_tree,
        implementation_sha256=implementation_sha256,
        implementation_files=implementation,
        source_identity_sha256=source_identity_sha256,
    )


def build_region_resource_current_lineage_candidate(
    dataset_dir: str | Path,
    *,
    repository_root: str | Path,
    output_dir: str | Path,
    config: RegionResourceCurrentLineageCandidateConfig | None = None,
    replace_output: bool = False,
) -> dict[str, Any]:
    """Build one clean-lineage, train/validation-only shadow candidate."""

    _require_torch()
    resolved = config or RegionResourceCurrentLineageCandidateConfig()
    source_summary = inspect_region_resource_current_lineage(repository_root)
    dataset_root = Path(dataset_dir).resolve()
    destination = Path(output_dir).resolve()
    if destination.name != resolved.candidate_id:
        raise RegionResourceCurrentLineageCandidateError(
            "output_directory_name_must_equal_candidate_id"
        )
    if destination.is_symlink():
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_output_symlink_forbidden"
        )
    if destination.exists() and not replace_output:
        raise RegionResourceCurrentLineageCandidateError(
            f"candidate_output_exists:{destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)

    loaded = load_region_learning_dataset_splits(
        dataset_root,
        splits=(RegionLearningSplit.TRAIN, RegionLearningSplit.VALIDATION),
    )
    split_usage = _split_usage(loaded)
    dataset_summary = _dataset_summary(loaded, split_usage=split_usage)
    config_payload = resolved.to_dict()
    config_sha256 = _sha256_json(config_payload)
    stored_config = {**config_payload, "config_sha256": config_sha256}

    temporary_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.staging-", dir=destination.parent
        )
    )
    staging = temporary_parent / resolved.candidate_id
    staging.mkdir()
    try:
        _write_json(
            staging / REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_FILENAME,
            source_summary.to_dict(),
        )
        _write_json(
            staging / REGION_RESOURCE_CURRENT_LINEAGE_DATASET_FILENAME,
            dataset_summary,
        )
        _write_json(
            staging / REGION_RESOURCE_CURRENT_LINEAGE_CONFIG_FILENAME,
            stored_config,
        )

        model, training_summary = _train_candidate(
            loaded,
            resolved,
            config_sha256=config_sha256,
        )
        bundle_manifest = save_region_resource_model_bundle(
            model,
            staging / "bundle",
            model_version=resolved.model_version,
            training_graphs=tuple(
                sample.graph
                for sample in load_region_behavior_cloning_samples(
                    loaded, split=RegionLearningSplit.TRAIN, device=resolved.device
                )
            ),
            created_at_utc=resolved.created_at_utc,
            training_dataset_manifest=loaded.manifest,
            lifecycle_stage=MODEL_LIFECYCLE_DEVELOPMENT,
            maximum_advisor_mode=MODEL_MAXIMUM_MODE_SHADOW,
            reward_evidence_available=False,
            final_holdout_seed_count=0,
            action_diversity_sufficient=False,
            strategy_capability_claim_allowed=False,
            target_action_inventory=_target_action_inventory(loaded),
            admission_reasons=(
                "current_lineage_development_candidate",
                "shadow_only",
                "train_validation_selection_only",
                "test_split_untouched",
                "calibration_seed_use_zero",
                "reserved_seed_use_zero",
                "formal_holdout_not_evaluated",
                "actual_adoption_unavailable",
                "benefit_evidence_unavailable",
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
        validation_finite = _review_validation_outputs(
            loaded,
            loaded_bundle.model,
            loaded_bundle.manifest,
        )
        training_summary["validation_output_review"] = validation_finite
        training_summary["content_sha256"] = _sha256_json(training_summary)
        _write_json(
            staging / REGION_RESOURCE_CURRENT_LINEAGE_TRAINING_FILENAME,
            training_summary,
        )

        artifact_files = {
            relative_path: _sha256_file(staging / relative_path)
            for relative_path in sorted(_CANDIDATE_ARTIFACT_FILES)
        }
        manifest = RegionResourceCurrentLineageCandidateManifest(
            candidate_id=resolved.candidate_id,
            model_version=resolved.model_version,
            source_summary_file_sha256=artifact_files[
                REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_FILENAME
            ],
            source_identity_sha256=source_summary.source_identity_sha256,
            dataset_summary_file_sha256=artifact_files[
                REGION_RESOURCE_CURRENT_LINEAGE_DATASET_FILENAME
            ],
            dataset_manifest_file_sha256=dataset_summary[
                "dataset_manifest_file_sha256"
            ],
            dataset_sha256=loaded.manifest.dataset_sha256,
            dataset_split_sha256=loaded.manifest.split.split_sha256,
            config_file_sha256=artifact_files[
                REGION_RESOURCE_CURRENT_LINEAGE_CONFIG_FILENAME
            ],
            config_sha256=config_sha256,
            training_summary_file_sha256=artifact_files[
                REGION_RESOURCE_CURRENT_LINEAGE_TRAINING_FILENAME
            ],
            training_summary_content_sha256=training_summary["content_sha256"],
            bundle_manifest_sha256=artifact_files["bundle/manifest.json"],
            model_state_sha256=artifact_files["bundle/state_dict.pt"],
            bundle_training_manifest_sha256=artifact_files[
                "bundle/training_dataset_manifest.json"
            ],
            split_usage=split_usage,
            validation_sample_count=validation_finite["sample_count"],
            validation_nonfinite_output_count=validation_finite[
                "nonfinite_output_count"
            ],
            artifact_files=artifact_files,
        )
        _write_json(
            staging / REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_FILENAME,
            manifest.to_dict(),
        )
        review = review_region_resource_current_lineage_candidate(
            staging,
            dataset_dir=dataset_root,
            repository_root=repository_root,
        )
        if destination.exists():
            if not replace_output:
                raise RegionResourceCurrentLineageCandidateError(
                    f"candidate_output_appeared:{destination}"
                )
            shutil.rmtree(destination)
        os.replace(staging, destination)
        temporary_parent.rmdir()
        return {
            "output_dir": str(destination),
            "candidate_manifest": manifest.to_dict(),
            "review": review.to_dict(),
            "training_summary": training_summary,
        }
    except Exception:
        shutil.rmtree(temporary_parent, ignore_errors=True)
        raise


def load_region_resource_current_lineage_candidate_manifest(
    candidate_root: str | Path,
    *,
    expected_manifest_file_sha256: str | None = None,
) -> RegionResourceCurrentLineageCandidateManifest:
    """Load a strict current-lineage manifest and verify its local artifact tree."""

    root = Path(candidate_root)
    path = root / REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_FILENAME
    if root.is_symlink() or path.is_symlink():
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_manifest_symlink_forbidden"
        )
    try:
        file_sha256 = _sha256_file(path)
    except OSError as exc:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_manifest_unavailable"
        ) from exc
    if expected_manifest_file_sha256 is not None:
        _require_sha256(
            expected_manifest_file_sha256, "expected_manifest_file_sha256"
        )
        if file_sha256 != expected_manifest_file_sha256:
            raise RegionResourceCurrentLineageCandidateError(
                "candidate_manifest_file_sha256_mismatch"
            )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = RegionResourceCurrentLineageCandidateManifest.from_mapping(
            payload
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RegionResourceCurrentLineageCandidateError(
            f"candidate_manifest_invalid:{type(exc).__name__}"
        ) from exc
    if root.name != manifest.candidate_id:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_directory_identity_mismatch"
        )
    for relative_path, expected_sha256 in manifest.artifact_files.items():
        artifact = root / relative_path
        if artifact.is_symlink():
            raise RegionResourceCurrentLineageCandidateError(
                f"candidate_artifact_symlink_forbidden:{relative_path}"
            )
        try:
            observed = _sha256_file(artifact)
        except OSError as exc:
            raise RegionResourceCurrentLineageCandidateError(
                f"candidate_artifact_unavailable:{relative_path}"
            ) from exc
        if observed != expected_sha256:
            raise RegionResourceCurrentLineageCandidateError(
                f"candidate_artifact_sha256_mismatch:{relative_path}"
            )
    return manifest


def review_region_resource_current_lineage_candidate(
    candidate_root: str | Path,
    *,
    dataset_dir: str | Path,
    repository_root: str | Path,
) -> RegionResourceCurrentLineageCandidateReview:
    """Rebuild every source/data/config/model binding and rerun finite validation."""

    root = Path(candidate_root)
    manifest = load_region_resource_current_lineage_candidate_manifest(root)
    source_summary = _read_source_summary(
        root / REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_FILENAME
    )
    observed_source = inspect_region_resource_current_lineage(repository_root)
    if source_summary.to_dict() != observed_source.to_dict():
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_source_lineage_mismatch"
        )
    if manifest.source_identity_sha256 != source_summary.source_identity_sha256:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_source_identity_mismatch"
        )

    config_payload = _read_json_object(
        root / REGION_RESOURCE_CURRENT_LINEAGE_CONFIG_FILENAME,
        "training_config",
    )
    config_sha256 = config_payload.pop("config_sha256", None)
    _require_sha256(str(config_sha256), "training_config.config_sha256")
    config = RegionResourceCurrentLineageCandidateConfig.from_mapping(
        config_payload
    )
    if (
        _sha256_json(config.to_dict()) != config_sha256
        or config_sha256 != manifest.config_sha256
        or config.model_version != manifest.model_version
        or config.candidate_id != manifest.candidate_id
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_training_config_mismatch"
        )

    loaded = load_region_learning_dataset_splits(
        dataset_dir,
        splits=(RegionLearningSplit.TRAIN, RegionLearningSplit.VALIDATION),
    )
    split_usage = _split_usage(loaded)
    observed_dataset_summary = _dataset_summary(loaded, split_usage=split_usage)
    stored_dataset_summary = _read_json_object(
        root / REGION_RESOURCE_CURRENT_LINEAGE_DATASET_FILENAME,
        "dataset_summary",
    )
    _validate_dataset_summary(stored_dataset_summary)
    if stored_dataset_summary != observed_dataset_summary:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_dataset_summary_mismatch"
        )
    if (
        manifest.dataset_manifest_file_sha256
        != stored_dataset_summary["dataset_manifest_file_sha256"]
        or manifest.dataset_sha256 != loaded.manifest.dataset_sha256
        or manifest.dataset_split_sha256 != loaded.manifest.split.split_sha256
        or manifest.split_usage.to_dict() != split_usage.to_dict()
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_dataset_binding_mismatch"
        )

    training_summary = _read_json_object(
        root / REGION_RESOURCE_CURRENT_LINEAGE_TRAINING_FILENAME,
        "training_summary",
    )
    _validate_training_summary(training_summary, manifest=manifest)
    bundle = load_region_resource_model_bundle(
        root / "bundle",
        expected_model_version=manifest.model_version,
        expected_state_dict_sha256=manifest.model_state_sha256,
        map_location=config.device,
        require_training_dataset_manifest=True,
    )
    if (
        bundle.manifest.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
        or bundle.manifest.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
        or bundle.manifest.assist_admitted
        or bundle.manifest.strategy_capability_claim_allowed
        or bundle.manifest.reward_evidence_available
        or bundle.manifest.final_holdout_seed_count != 0
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_bundle_permission_boundary_crossed"
        )
    embedded = bundle.training_dataset_manifest
    if (
        embedded is None
        or embedded.dataset_sha256 != manifest.dataset_sha256
        or embedded.split.split_sha256 != manifest.dataset_split_sha256
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_bundle_dataset_binding_mismatch"
        )
    if not _model_parameters_finite(bundle.model):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_model_parameter_nonfinite"
        )
    validation = _review_validation_outputs(
        loaded, bundle.model, bundle.manifest
    )
    if (
        validation["sample_count"] != manifest.validation_sample_count
        or validation["nonfinite_output_count"]
        != manifest.validation_nonfinite_output_count
        or validation != training_summary["validation_output_review"]
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_validation_review_mismatch"
        )
    return RegionResourceCurrentLineageCandidateReview(
        candidate_id=manifest.candidate_id,
        model_version=manifest.model_version,
        source_identity_sha256=manifest.source_identity_sha256,
        dataset_sha256=manifest.dataset_sha256,
        dataset_split_sha256=manifest.dataset_split_sha256,
        model_state_sha256=manifest.model_state_sha256,
        validation_sample_count=validation["sample_count"],
        validation_nonfinite_output_count=validation[
            "nonfinite_output_count"
        ],
    )


def _train_candidate(
    loaded: LoadedRegionLearningDataset,
    config: RegionResourceCurrentLineageCandidateConfig,
    *,
    config_sha256: str,
) -> tuple[SharedRegionGraphActorCritic, dict[str, Any]]:
    torch.set_num_threads(config.torch_num_threads)
    _seed_training(config.random_seed)
    device = _resolve_device(config.device)
    train_samples = load_region_behavior_cloning_samples(
        loaded, split=RegionLearningSplit.TRAIN, device=device
    )
    validation_samples = load_region_behavior_cloning_samples(
        loaded, split=RegionLearningSplit.VALIDATION, device=device
    )
    if not train_samples or not validation_samples:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_train_or_validation_samples_unavailable"
        )
    model = SharedRegionGraphActorCritic(
        hidden_dim=config.hidden_dim,
        message_passing_steps=config.message_passing_steps,
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    generator = torch.Generator(device="cpu")
    generator.manual_seed(config.random_seed)
    best_validation_loss = float("inf")
    best_epoch = 0
    best_state: dict[str, Any] | None = None
    no_improvement = 0
    history: list[dict[str, float | int]] = []
    for epoch in range(1, config.epochs + 1):
        model.train()
        order = torch.randperm(len(train_samples), generator=generator).tolist()
        weighted_loss = 0.0
        for offset in range(0, len(order), config.batch_size):
            indices = order[offset : offset + config.batch_size]
            batch = tuple(train_samples[index] for index in indices)
            loss = behavior_cloning_step(
                model,
                optimizer,
                batch,
                max_grad_norm=config.max_grad_norm,
            )
            if not isfinite(loss):
                raise RegionResourceCurrentLineageCandidateError(
                    "candidate_training_loss_nonfinite"
                )
            weighted_loss += loss * len(batch)
        train_loss = weighted_loss / len(train_samples)
        validation_loss = _mean_bc_loss(model, validation_samples)
        if not isfinite(train_loss) or not isfinite(validation_loss):
            raise RegionResourceCurrentLineageCandidateError(
                "candidate_selection_loss_nonfinite"
            )
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
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
            no_improvement = 0
        else:
            no_improvement += 1
            if no_improvement >= config.early_stopping_patience:
                break
    if best_state is None:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_training_produced_no_checkpoint"
        )
    model.load_state_dict(best_state, strict=True)
    model.to(device)
    model.eval()
    if not _model_parameters_finite(model):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_model_parameter_nonfinite"
        )
    return model, {
        "schema": REGION_RESOURCE_CURRENT_LINEAGE_TRAINING_SCHEMA,
        "config_sha256": config_sha256,
        "model_version": config.model_version,
        "training_split": RegionLearningSplit.TRAIN.value,
        "selection_split": RegionLearningSplit.VALIDATION.value,
        "train_sample_count": len(train_samples),
        "validation_sample_count": len(validation_samples),
        "test_sample_count": 0,
        "calibration_sample_count": 0,
        "reserved_evaluation_sample_count": 0,
        "epochs_completed": len(history),
        "best_epoch": best_epoch,
        "best_validation_loss": best_validation_loss,
        "history": history,
        "model_parameter_count": sum(
            int(parameter.numel()) for parameter in model.parameters()
        ),
        "model_parameters_finite": True,
        "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
        "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
        "formal_holdout_evaluated": False,
        "permissions": RegionResourceCurrentLineagePermissions().to_dict(),
    }


def _split_usage(
    loaded: LoadedRegionLearningDataset,
) -> RegionResourceCurrentLineageSplitUsage:
    manifest = loaded.manifest
    train_records = loaded.episodes(RegionLearningSplit.TRAIN)
    validation_records = loaded.episodes(RegionLearningSplit.VALIDATION)
    observed_train = {int(record.source.seed) for record in train_records}
    observed_validation = {
        int(record.source.seed) for record in validation_records
    }
    if observed_train != set(manifest.split.train_seeds):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_train_seed_inventory_mismatch"
        )
    if observed_validation != set(manifest.split.validation_seeds):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_validation_seed_inventory_mismatch"
        )
    return RegionResourceCurrentLineageSplitUsage(
        train_seeds=manifest.split.train_seeds,
        validation_seeds=manifest.split.validation_seeds,
        untouched_test_seeds=manifest.split.test_seeds,
        train_payload_read_count=len(train_records),
        validation_payload_read_count=len(validation_records),
    )


def _dataset_summary(
    loaded: LoadedRegionLearningDataset,
    *,
    split_usage: RegionResourceCurrentLineageSplitUsage,
) -> dict[str, Any]:
    manifest = loaded.manifest
    if (
        manifest.availability.dirty_episode_count != 0
        or not manifest.availability.behavior_cloning_available
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_dataset_not_clean_behavior_cloning_source"
        )
    train_entries = tuple(
        entry
        for entry in manifest.episodes
        if entry.split == RegionLearningSplit.TRAIN
    )
    validation_entries = tuple(
        entry
        for entry in manifest.episodes
        if entry.split == RegionLearningSplit.VALIDATION
    )
    summary = {
        "schema": REGION_RESOURCE_CURRENT_LINEAGE_DATASET_SCHEMA,
        "dataset_manifest_file_sha256": _sha256_file(
            loaded.root / "manifest.json"
        ),
        "dataset_sha256": manifest.dataset_sha256,
        "dataset_split_sha256": manifest.split.split_sha256,
        "dataset_episode_count": manifest.availability.episode_count,
        "dataset_frame_count": manifest.availability.frame_count,
        "dirty_episode_count": manifest.availability.dirty_episode_count,
        "behavior_cloning_available": (
            manifest.availability.behavior_cloning_available
        ),
        "train_episode_count": len(train_entries),
        "validation_episode_count": len(validation_entries),
        "train_frame_count": sum(entry.frame_count for entry in train_entries),
        "validation_frame_count": sum(
            entry.frame_count for entry in validation_entries
        ),
        "train_episode_inventory_sha256": _episode_inventory_sha256(
            train_entries
        ),
        "validation_episode_inventory_sha256": _episode_inventory_sha256(
            validation_entries
        ),
        "source_git_commits": sorted(
            {entry.source.git_commit for entry in train_entries + validation_entries}
        ),
        "split_usage": split_usage.to_dict(),
        "truth_identifier_use_count": 0,
        "test_payload_verified_during_build": False,
        "formal_holdout_evaluated": False,
    }
    summary["content_sha256"] = _sha256_json(summary)
    _validate_dataset_summary(summary)
    return summary


def _validate_dataset_summary(value: Mapping[str, Any]) -> None:
    expected = {
        "schema",
        "dataset_manifest_file_sha256",
        "dataset_sha256",
        "dataset_split_sha256",
        "dataset_episode_count",
        "dataset_frame_count",
        "dirty_episode_count",
        "behavior_cloning_available",
        "train_episode_count",
        "validation_episode_count",
        "train_frame_count",
        "validation_frame_count",
        "train_episode_inventory_sha256",
        "validation_episode_inventory_sha256",
        "source_git_commits",
        "split_usage",
        "truth_identifier_use_count",
        "test_payload_verified_during_build",
        "formal_holdout_evaluated",
        "content_sha256",
    }
    _require_exact_keys(value, expected, "dataset_summary")
    if value["schema"] != REGION_RESOURCE_CURRENT_LINEAGE_DATASET_SCHEMA:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_dataset_summary_schema_invalid"
        )
    for name in (
        "dataset_manifest_file_sha256",
        "dataset_sha256",
        "dataset_split_sha256",
        "train_episode_inventory_sha256",
        "validation_episode_inventory_sha256",
        "content_sha256",
    ):
        _require_sha256(str(value[name]), f"dataset_summary.{name}")
    content = dict(value)
    observed_content_sha256 = str(content.pop("content_sha256"))
    if _sha256_json(content) != observed_content_sha256:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_dataset_summary_content_mismatch"
        )
    RegionResourceCurrentLineageSplitUsage.from_mapping(value["split_usage"])
    if (
        type(value["dirty_episode_count"]) is not int
        or value["dirty_episode_count"] != 0
        or value["behavior_cloning_available"] is not True
        or type(value["truth_identifier_use_count"]) is not int
        or value["truth_identifier_use_count"] != 0
        or value["test_payload_verified_during_build"] is not False
        or value["formal_holdout_evaluated"] is not False
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_dataset_summary_boundary_crossed"
        )
    for name in (
        "dataset_episode_count",
        "dataset_frame_count",
        "train_episode_count",
        "validation_episode_count",
        "train_frame_count",
        "validation_frame_count",
    ):
        if type(value[name]) is not int or int(value[name]) <= 0:
            raise RegionResourceCurrentLineageCandidateError(
                f"candidate_dataset_summary_count_invalid:{name}"
            )


def _validate_training_summary(
    value: Mapping[str, Any],
    *,
    manifest: RegionResourceCurrentLineageCandidateManifest,
) -> None:
    expected = {
        "schema",
        "config_sha256",
        "model_version",
        "training_split",
        "selection_split",
        "train_sample_count",
        "validation_sample_count",
        "test_sample_count",
        "calibration_sample_count",
        "reserved_evaluation_sample_count",
        "epochs_completed",
        "best_epoch",
        "best_validation_loss",
        "history",
        "model_parameter_count",
        "model_parameters_finite",
        "lifecycle_stage",
        "maximum_advisor_mode",
        "formal_holdout_evaluated",
        "permissions",
        "validation_output_review",
        "content_sha256",
    }
    _require_exact_keys(value, expected, "training_summary")
    if value["schema"] != REGION_RESOURCE_CURRENT_LINEAGE_TRAINING_SCHEMA:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_training_summary_schema_invalid"
        )
    content = dict(value)
    observed_sha256 = str(content.pop("content_sha256"))
    _require_sha256(observed_sha256, "training_summary.content_sha256")
    if (
        _sha256_json(content) != observed_sha256
        or observed_sha256 != manifest.training_summary_content_sha256
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_training_summary_content_mismatch"
        )
    if (
        value["config_sha256"] != manifest.config_sha256
        or value["model_version"] != manifest.model_version
        or value["training_split"] != RegionLearningSplit.TRAIN.value
        or value["selection_split"] != RegionLearningSplit.VALIDATION.value
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_training_summary_binding_mismatch"
        )
    for name in (
        "test_sample_count",
        "calibration_sample_count",
        "reserved_evaluation_sample_count",
    ):
        if type(value[name]) is not int or value[name] != 0:
            raise RegionResourceCurrentLineageCandidateError(
                f"candidate_forbidden_sample_use:{name}"
            )
    if (
        type(value["validation_sample_count"]) is not int
        or value["validation_sample_count"] != manifest.validation_sample_count
        or not isfinite(float(value["best_validation_loss"]))
        or value["model_parameters_finite"] is not True
        or value["lifecycle_stage"] != MODEL_LIFECYCLE_DEVELOPMENT
        or value["maximum_advisor_mode"] != MODEL_MAXIMUM_MODE_SHADOW
        or value["formal_holdout_evaluated"] is not False
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_training_summary_boundary_crossed"
        )
    RegionResourceCurrentLineagePermissions.from_mapping(value["permissions"])
    validation = value["validation_output_review"]
    _require_exact_keys(
        validation,
        {
            "sample_count",
            "nonfinite_output_count",
            "confidence_min",
            "confidence_max",
        },
        "validation_output_review",
    )
    if (
        type(validation["sample_count"]) is not int
        or validation["sample_count"] != manifest.validation_sample_count
        or type(validation["nonfinite_output_count"]) is not int
        or validation["nonfinite_output_count"] != 0
        or not isfinite(float(validation["confidence_min"]))
        or not isfinite(float(validation["confidence_max"]))
    ):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_validation_output_nonfinite"
        )


def _review_validation_outputs(
    loaded: LoadedRegionLearningDataset,
    model: SharedRegionGraphActorCritic,
    model_manifest: Any,
) -> dict[str, float | int]:
    policy = LearnedRegionResourcePolicy(model, model_manifest)
    confidences: list[float] = []
    nonfinite = 0
    for episode in loaded.episodes(RegionLearningSplit.VALIDATION):
        for frame in episode.frames:
            try:
                recommendation = policy.recommend_raw(frame.snapshot)
                finite = _recommendation_finite(recommendation)
            except Exception as exc:
                raise RegionResourceCurrentLineageCandidateError(
                    f"candidate_validation_inference_failed:{type(exc).__name__}"
                ) from exc
            if not finite:
                nonfinite += 1
            else:
                confidences.append(float(recommendation.confidence))
    sample_count = sum(
        len(episode.frames)
        for episode in loaded.episodes(RegionLearningSplit.VALIDATION)
    )
    if nonfinite or len(confidences) != sample_count or not confidences:
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_validation_output_nonfinite"
        )
    return {
        "sample_count": sample_count,
        "nonfinite_output_count": nonfinite,
        "confidence_min": min(confidences),
        "confidence_max": max(confidences),
    }


def _target_action_inventory(
    loaded: LoadedRegionLearningDataset,
) -> dict[str, int]:
    inventory = {
        "action_count": 0,
        "resource_quota_nonzero_count": 0,
        "transfer_count": 0,
        "hold_true_count": 0,
        "request_replan_true_count": 0,
    }
    for episode in loaded.episode_records:
        for frame in episode.frames:
            recommendation = frame.target.recommendation
            if recommendation is None:
                raise RegionResourceCurrentLineageCandidateError(
                    "candidate_target_recommendation_unavailable"
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


def _mean_bc_loss(
    model: SharedRegionGraphActorCritic,
    samples: Sequence[Any],
) -> float:
    model.eval()
    with torch.no_grad():
        losses = [
            behavior_cloning_loss(model, sample.graph, sample.target)
            for sample in samples
        ]
        if not losses:
            raise RegionResourceCurrentLineageCandidateError(
                "candidate_validation_samples_unavailable"
            )
        loss = torch.stack(losses).mean()
    value = float(loss.detach().cpu())
    if not isfinite(value):
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_selection_loss_nonfinite"
        )
    return value


def _model_parameters_finite(model: SharedRegionGraphActorCritic) -> bool:
    return all(bool(torch.isfinite(parameter).all()) for parameter in model.parameters())


def _recommendation_finite(
    recommendation: RegionResourceRecommendation,
) -> bool:
    values: list[float] = [
        recommendation.created_at_s,
        recommendation.confidence,
    ]
    for action in recommendation.actions:
        values.extend(
            (
                action.resource_quota_delta,
                action.reserve_ratio,
                action.reconnaissance_priority,
                action.expected_plan_version,
                action.expected_epoch,
                action.expected_lease_expires_at_s,
            )
        )
    for transfer in recommendation.transfers:
        values.extend(
            (transfer.resource_count, transfer.expected_transfer_time_s)
        )
    return all(isfinite(float(value)) for value in values)


def _episode_inventory_sha256(entries: Iterable[Any]) -> str:
    return _sha256_json(
        [
            {
                "relative_path": entry.relative_path,
                "episode_sha256": entry.episode_sha256,
                "scenario_id": entry.source.scenario_id,
                "seed": int(entry.source.seed),
                "split": entry.split.value,
            }
            for entry in entries
        ]
    )


def _read_source_summary(
    path: Path,
) -> RegionResourceCurrentLineageSourceSummary:
    payload = _read_json_object(path, "source_summary")
    try:
        return RegionResourceCurrentLineageSourceSummary.from_mapping(payload)
    except (ValueError, TypeError, KeyError) as exc:
        raise RegionResourceCurrentLineageCandidateError(
            f"candidate_source_summary_invalid:{type(exc).__name__}"
        ) from exc


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegionResourceCurrentLineageCandidateError(
            f"candidate_{label}_unavailable"
        ) from exc
    if not isinstance(value, dict):
        raise RegionResourceCurrentLineageCandidateError(
            f"candidate_{label}_must_be_object"
        )
    return value


def _git_text(root: Path, *args: str) -> str:
    return _git_bytes(root, *args).decode("utf-8", errors="strict")


def _git_bytes(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ("git", "-C", str(root), *args),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    )
    if completed.returncode != 0:
        reason = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RegionResourceCurrentLineageCandidateError(
            f"source_git_command_failed:{args[0]}:{reason}"
        )
    return completed.stdout


def _seed_training(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    try:
        torch.use_deterministic_algorithms(True)
    except (AttributeError, RuntimeError):
        pass


def _resolve_device(value: str) -> Any:
    device = torch.device(value)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RegionResourceCurrentLineageCandidateError(
            "candidate_requested_cuda_unavailable"
        )
    return device


def _canonical_seed_tuple(values: Iterable[int]) -> tuple[int, ...]:
    result = tuple(sorted({int(value) for value in values}))
    if any(value < 0 for value in result):
        raise ValueError("seed catalogs must be non-negative")
    return result


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        observed = set(value) if isinstance(value, Mapping) else set()
        raise ValueError(
            f"{label} keys mismatch:"
            f"missing={sorted(expected - observed)};"
            f"extra={sorted(observed - expected)}"
        )


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value.lower()
    ):
        raise ValueError(f"{name} must be a SHA256")


def _require_git_object_id(value: str, name: str) -> None:
    if len(value) not in {40, 64} or any(
        character not in "0123456789abcdef" for character in value.lower()
    ):
        raise ValueError(f"{name} must be a Git object ID")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


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


def _require_torch() -> None:
    if torch is None:
        raise RegionResourceCurrentLineageCandidateError("torch_unavailable")
