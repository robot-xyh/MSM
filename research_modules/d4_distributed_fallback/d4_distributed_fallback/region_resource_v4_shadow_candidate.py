"""Unregistered D4 v4 development/shadow regional candidate framework.

The v4 path is separate from the frozen v3 registry. It requires an external,
content-addressed, truth-free dataset, keeps the main/v3 deterministic safety
shell, and cannot enter runtime until a later immutable registration exists.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from math import ceil, isfinite
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

from .models import to_jsonable
from .region_resource import (
    DeterministicResourceProjector,
    RegionResourceAction,
    RegionResourceAdvisoryContract,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceProjectionConfig,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
)
from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningSplit,
    load_region_learning_dataset_splits,
)
from .region_resource_learning import (
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    REGION_GRAPH_ARCHITECTURE,
    REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_OOD_MARGIN,
    REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD,
    LearnedRegionResourcePolicy,
    LoadedRegionResourceModelBundle,
    SharedRegionGraphActorCritic,
    behavior_cloning_loss,
    behavior_cloning_step,
    load_region_behavior_cloning_samples,
    load_region_resource_model_bundle,
    save_region_resource_model_bundle,
    snapshot_to_region_graph,
)
from .regional_failover import RegionalAuthorityLayer, RegionalFailoverDecision


try:  # The default deterministic D4 path still does not require torch.
    import torch
except ImportError:  # pragma: no cover - covered by the optional dependency gate.
    torch = None


REGION_RESOURCE_V4_CANDIDATE_ID = (
    "region_resource_a2_executable_transfer_shadow_v4"
)
REGION_RESOURCE_V4_MODEL_VERSION = (
    "d4-region-resource-graph-bc-executable-transfer-v4"
)
REGION_RESOURCE_V4_CANDIDATE_SCHEMA = (
    "d4-region-resource-executable-shadow-candidate-v4"
)
REGION_RESOURCE_V4_CONFIG_SCHEMA = (
    "d4-region-resource-executable-shadow-config-v4"
)
REGION_RESOURCE_V4_TRAINING_SCHEMA = (
    "d4-region-resource-executable-shadow-training-v4"
)
REGION_RESOURCE_V4_SOURCE_SCHEMA = (
    "d4-region-resource-executable-shadow-source-v4"
)
REGION_RESOURCE_V4_DECISION_SCHEMA = (
    "d4-region-resource-executable-shadow-decision-v4"
)
REGION_RESOURCE_V4_PERMISSIONS_SCHEMA = (
    "d4-region-resource-executable-shadow-permissions-v4"
)
REGION_RESOURCE_V4_FIXTURE_SCHEMA = (
    "d4-region-resource-executable-development-fixture-v4"
)
REGION_RESOURCE_V4_INTERVENTION_GATE_SCHEMA = (
    "d4-region-resource-executable-intervention-gate-v4"
)
REGION_RESOURCE_V4_CANDIDATE_FILENAME = "v4_shadow_candidate_manifest.json"
REGION_RESOURCE_V4_CONFIG_FILENAME = "training_config.json"
REGION_RESOURCE_V4_TRAINING_FILENAME = "training_summary.json"
REGION_RESOURCE_V4_SOURCE_FILENAME = "source_implementation_summary.json"
REGION_RESOURCE_V4_GATE_FILENAME = "intervention_gate.json"
REGION_RESOURCE_V4_EXTERNAL_EVIDENCE_FILENAME = (
    "external_dataset_evidence.json"
)
REGION_RESOURCE_V4_DATASET_DIRNAME = "development_dataset"
REGION_RESOURCE_V4_EXTERNAL_EVIDENCE_SCHEMA = (
    "d4-region-resource-external-runtime-dataset-evidence-v1"
)
REGION_RESOURCE_V3_FROZEN_TREE_SHA256 = (
    "07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a"
)

# A v4 candidate has not been admitted or registered.  None is intentional:
# zero-filled digests can be mistaken for a registry binding.
REGION_RESOURCE_V4_REGISTERED_MANIFEST_FILE_SHA256: str | None = None
REGION_RESOURCE_V4_REGISTERED_MANIFEST_CONTENT_SHA256: str | None = None
REGION_RESOURCE_V4_REGISTERED_MODEL_STATE_SHA256: str | None = None
REGION_RESOURCE_V4_REGISTERED_BUNDLE_MANIFEST_SHA256: str | None = None
REGION_RESOURCE_V4_REGISTERED_DATASET_SHA256: str | None = None

_V4_PROJECTION = RegionResourceProjectionConfig(
    minimum_reserve_ratio=0.10,
    minimum_reserve_resources=1,
    advisory_ttl_s=1.5,
)
_V4_RULE_CONFIG = RuleRegionResourcePolicyConfig(
    projection=_V4_PROJECTION,
    high_threat_weight=2.0,
    uncertainty_weight=0.5,
    transfer_pressure_margin=0.05,
)
_V4_INFERENCE_TIMEOUT_S = 0.250


class RegionResourceV4CandidateError(RuntimeError):
    """Stable fail-closed error for the v4 development candidate."""


@dataclass(frozen=True)
class RegionResourceV4Permissions:
    """Explicitly closed production permissions for the v4 shadow path."""

    formal_evaluation_authorized: bool = False
    assist_enabled: bool = False
    authority_enabled: bool = False
    assignment_enabled: bool = False
    takeover_enabled: bool = False
    coalition_commit_enabled: bool = False
    control_enabled: bool = False
    production_runtime_ack_enabled: bool = False
    physical_permission_available: bool = False
    actual_adoption_claimed: bool = False
    benefit_claimed: bool = False
    schema: str = REGION_RESOURCE_V4_PERMISSIONS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V4_PERMISSIONS_SCHEMA:
            raise ValueError("unsupported v4 permissions schema")
        values = (
            value
            for name, value in asdict(self).items()
            if name != "schema"
        )
        if any(type(value) is not bool or value for value in values):
            raise ValueError("v4 development candidate cannot grant permissions")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceV4Permissions":
        _require_exact_keys(value, cls.__dataclass_fields__, "v4_permissions")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceV4InterventionGate:
    """Development-only gate for a bounded D3-consumable intervention."""

    fixed_minimum_confidence: float = (
        REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD
    )
    fixed_ood_margin: float = (
        REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_OOD_MARGIN
    )
    maximum_transfer_per_edge: int = 1
    maximum_total_transfer_fraction: float = 0.10
    require_binary_match_with_r0: bool = True
    require_source_r0_treatment_signatures: bool = True
    require_authority_identity_unchanged: bool = True
    require_quota_flow_conservation: bool = True
    development_only: bool = True
    shadow_only: bool = True
    admission_closed: bool = True
    rule_fallback_required: bool = True
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_V4_INTERVENTION_GATE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V4_INTERVENTION_GATE_SCHEMA:
            raise ValueError("unsupported v4 intervention gate schema")
        if (
            float(self.fixed_minimum_confidence)
            != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD
            or float(self.fixed_ood_margin)
            != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_OOD_MARGIN
            or type(self.maximum_transfer_per_edge) is not int
            or self.maximum_transfer_per_edge != 1
            or not isfinite(float(self.maximum_total_transfer_fraction))
            or not 0.0 < self.maximum_total_transfer_fraction <= 0.10
        ):
            raise ValueError("v4 intervention gate thresholds changed")
        required_true = (
            self.require_binary_match_with_r0,
            self.require_source_r0_treatment_signatures,
            self.require_authority_identity_unchanged,
            self.require_quota_flow_conservation,
            self.development_only,
            self.shadow_only,
            self.admission_closed,
            self.rule_fallback_required,
        )
        if any(type(value) is not bool or not value for value in required_true):
            raise ValueError("v4 intervention gate safety boundary changed")
        expected = _canonical_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("v4 intervention gate content SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "fixed_minimum_confidence": self.fixed_minimum_confidence,
            "fixed_ood_margin": self.fixed_ood_margin,
            "maximum_transfer_per_edge": self.maximum_transfer_per_edge,
            "maximum_total_transfer_fraction": (
                self.maximum_total_transfer_fraction
            ),
            "require_binary_match_with_r0": (
                self.require_binary_match_with_r0
            ),
            "require_source_r0_treatment_signatures": (
                self.require_source_r0_treatment_signatures
            ),
            "require_authority_identity_unchanged": (
                self.require_authority_identity_unchanged
            ),
            "require_quota_flow_conservation": (
                self.require_quota_flow_conservation
            ),
            "development_only": self.development_only,
            "shadow_only": self.shadow_only,
            "admission_closed": self.admission_closed,
            "rule_fallback_required": self.rule_fallback_required,
            "schema": self.schema,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceV4InterventionGate":
        _require_exact_keys(
            value,
            cls.__dataclass_fields__,
            "v4_intervention_gate",
        )
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceV4ExternalDatasetEvidence:
    """Content binding for an externally captured truth-free dataset."""

    dataset_sha256: str
    dataset_split_sha256: str
    source_artifact_sha256: str
    source_kind: str
    truth_free_online_features: bool
    generated_by_v4_builder: bool
    source_worktree_dirty: bool
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_V4_EXTERNAL_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V4_EXTERNAL_EVIDENCE_SCHEMA:
            raise ValueError("unsupported v4 external dataset evidence schema")
        for name in (
            "dataset_sha256",
            "dataset_split_sha256",
            "source_artifact_sha256",
        ):
            digest = str(getattr(self, name)).lower()
            _require_sha256(digest, f"v4_external_evidence.{name}")
            if digest == "0" * 64:
                raise ValueError(
                    f"v4 external evidence {name} cannot be zero-filled"
                )
            object.__setattr__(self, name, digest)
        if self.source_kind not in {
            "main_runtime_frames",
            "external_region_learning_dataset",
        }:
            raise ValueError("unsupported v4 external source kind")
        if (
            self.truth_free_online_features is not True
            or self.generated_by_v4_builder is not False
            or self.source_worktree_dirty is not False
        ):
            raise ValueError("v4 external dataset provenance is not admissible")
        expected = _canonical_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("v4 external dataset evidence SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "dataset_sha256": self.dataset_sha256,
            "dataset_split_sha256": self.dataset_split_sha256,
            "source_artifact_sha256": self.source_artifact_sha256,
            "source_kind": self.source_kind,
            "truth_free_online_features": self.truth_free_online_features,
            "generated_by_v4_builder": self.generated_by_v4_builder,
            "source_worktree_dirty": self.source_worktree_dirty,
            "schema": self.schema,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceV4ExternalDatasetEvidence":
        _require_exact_keys(
            value,
            cls.__dataclass_fields__,
            "v4_external_dataset_evidence",
        )
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceV4BuildConfig:
    """Fixed, reproducible external-data development training contract."""

    random_seed: int = 20260729
    minimum_train_seeds: int = 8
    minimum_validation_seeds: int = 4
    minimum_test_seeds: int = 4
    hidden_dim: int = 24
    message_passing_steps: int = 2
    epochs: int = 240
    batch_size: int = 16
    learning_rate: float = 3.0e-3
    weight_decay: float = 1.0e-5
    max_grad_norm: float = 1.0
    early_stopping_patience: int = 45
    confidence_epochs: int = 180
    confidence_batch_size: int = 16
    confidence_learning_rate: float = 1.0e-2
    torch_num_threads: int = 1
    created_at_utc: str = "2026-07-29T00:00:00Z"
    candidate_id: str = REGION_RESOURCE_V4_CANDIDATE_ID
    model_version: str = REGION_RESOURCE_V4_MODEL_VERSION
    schema: str = REGION_RESOURCE_V4_CONFIG_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != REGION_RESOURCE_V4_CONFIG_SCHEMA
            or self.candidate_id != REGION_RESOURCE_V4_CANDIDATE_ID
            or self.model_version != REGION_RESOURCE_V4_MODEL_VERSION
        ):
            raise ValueError("v4 candidate identity changed")
        for name in (
            "random_seed",
            "minimum_train_seeds",
            "minimum_validation_seeds",
            "minimum_test_seeds",
            "hidden_dim",
            "message_passing_steps",
            "epochs",
            "batch_size",
            "early_stopping_patience",
            "confidence_epochs",
            "confidence_batch_size",
            "torch_num_threads",
        ):
            if type(getattr(self, name)) is not int or int(getattr(self, name)) <= 0:
                raise ValueError(f"v4 config {name} must be a positive integer")
        for name in (
            "learning_rate",
            "weight_decay",
            "max_grad_norm",
            "confidence_learning_rate",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"v4 config {name} must be finite and non-negative")
        if (
            self.learning_rate <= 0.0
            or self.max_grad_norm <= 0.0
            or self.confidence_learning_rate <= 0.0
        ):
            raise ValueError("v4 training rates are invalid")
        if not self.created_at_utc:
            raise ValueError("v4 created_at_utc must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionResourceV4CandidateManifest:
    candidate_id: str
    model_version: str
    source_identity_sha256: str
    dataset_sha256: str
    dataset_split_sha256: str
    external_dataset_evidence_sha256: str
    config_sha256: str
    training_summary_content_sha256: str
    bundle_manifest_sha256: str
    model_state_sha256: str
    runtime_gate_content_sha256: str
    artifact_files: Mapping[str, str]
    development_fixture: Mapping[str, Any]
    permissions: RegionResourceV4Permissions = field(
        default_factory=RegionResourceV4Permissions
    )
    development_only: bool = True
    shadow_only: bool = True
    admission_closed: bool = True
    rule_fallback_required: bool = True
    formal_holdout_evaluated: bool = False
    runtime_preflight_completed: bool = False
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_V4_CANDIDATE_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != REGION_RESOURCE_V4_CANDIDATE_SCHEMA
            or self.candidate_id != REGION_RESOURCE_V4_CANDIDATE_ID
            or self.model_version != REGION_RESOURCE_V4_MODEL_VERSION
        ):
            raise ValueError("v4 candidate manifest identity changed")
        for name in (
            "source_identity_sha256",
            "dataset_sha256",
            "dataset_split_sha256",
            "external_dataset_evidence_sha256",
            "config_sha256",
            "training_summary_content_sha256",
            "bundle_manifest_sha256",
            "model_state_sha256",
            "runtime_gate_content_sha256",
        ):
            _require_sha256(str(getattr(self, name)), f"v4_manifest.{name}")
        if not isinstance(self.permissions, RegionResourceV4Permissions):
            object.__setattr__(
                self,
                "permissions",
                RegionResourceV4Permissions.from_mapping(self.permissions),
            )
        if (
            self.development_only is not True
            or self.shadow_only is not True
            or self.admission_closed is not True
            or self.rule_fallback_required is not True
            or self.formal_holdout_evaluated
            or self.runtime_preflight_completed
        ):
            raise ValueError("v4 development boundary changed")
        artifacts = dict(self.artifact_files)
        if not artifacts:
            raise ValueError("v4 artifact inventory must not be empty")
        for relative_path, digest in artifacts.items():
            path = Path(relative_path)
            if (
                path.is_absolute()
                or ".." in path.parts
                or path.name == REGION_RESOURCE_V4_CANDIDATE_FILENAME
            ):
                raise ValueError("v4 artifact path is invalid")
            _require_sha256(str(digest), f"v4 artifact {relative_path}")
        object.__setattr__(self, "artifact_files", artifacts)
        fixture = dict(self.development_fixture)
        if (
            fixture.get("schema") != REGION_RESOURCE_V4_FIXTURE_SCHEMA
            or fixture.get("executable_signature_different") is not True
            or not fixture.get("difference_fields")
        ):
            raise ValueError("v4 development fixture lacks executable difference")
        object.__setattr__(self, "development_fixture", fixture)
        expected = _canonical_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("v4 manifest content SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "model_version": self.model_version,
            "source_identity_sha256": self.source_identity_sha256,
            "dataset_sha256": self.dataset_sha256,
            "dataset_split_sha256": self.dataset_split_sha256,
            "external_dataset_evidence_sha256": (
                self.external_dataset_evidence_sha256
            ),
            "config_sha256": self.config_sha256,
            "training_summary_content_sha256": (
                self.training_summary_content_sha256
            ),
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "model_state_sha256": self.model_state_sha256,
            "runtime_gate_content_sha256": self.runtime_gate_content_sha256,
            "artifact_files": dict(self.artifact_files),
            "development_fixture": dict(self.development_fixture),
            "permissions": self.permissions.to_dict(),
            "development_only": self.development_only,
            "shadow_only": self.shadow_only,
            "admission_closed": self.admission_closed,
            "rule_fallback_required": self.rule_fallback_required,
            "formal_holdout_evaluated": self.formal_holdout_evaluated,
            "runtime_preflight_completed": self.runtime_preflight_completed,
            "schema": self.schema,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceV4CandidateManifest":
        _require_exact_keys(value, cls.__dataclass_fields__, "v4_manifest")
        payload = dict(value)
        payload["permissions"] = RegionResourceV4Permissions.from_mapping(
            _mapping(payload["permissions"], "v4 permissions")
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceV4CandidateEvaluation:
    raw_recommendation: RegionResourceRecommendation
    projected_recommendation: RegionResourceRecommendation
    raw_confidence: float
    effective_confidence: float
    runtime_gate_passed: bool
    action_consistent: bool
    candidate_ood: bool
    candidate_latency_ms: float
    runtime_gate_content_sha256: str
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "raw_confidence",
            "effective_confidence",
            "candidate_latency_ms",
        ):
            if not isfinite(float(getattr(self, name))):
                raise ValueError(f"v4 evaluation {name} must be finite")
        if not 0.0 <= self.raw_confidence <= 1.0:
            raise ValueError("v4 raw confidence must be in [0, 1]")
        if not 0.0 <= self.effective_confidence <= 1.0:
            raise ValueError("v4 effective confidence must be in [0, 1]")
        _require_sha256(
            self.runtime_gate_content_sha256,
            "v4 evaluation runtime gate SHA256",
        )
        object.__setattr__(
            self, "rejection_reasons", tuple(dict.fromkeys(self.rejection_reasons))
        )


@dataclass(frozen=True)
class RegionResourceV4ShadowDecision:
    snapshot_id: str
    seed: int
    control_recommendation: RegionResourceRecommendation
    treatment_recommendation: RegionResourceRecommendation
    control_advisory: RegionResourceAdvisoryContract
    treatment_advisory: RegionResourceAdvisoryContract
    control_executable_signature_sha256: str
    treatment_executable_signature_sha256: str
    executable_signature_different: bool
    difference_fields: tuple[str, ...]
    candidate_inference_completed: bool
    runtime_gate_passed: bool
    projection_passed: bool
    shadow_treatment_selected: bool
    rule_fallback_used: bool
    rejection_reasons: tuple[str, ...]
    candidate_id: str = REGION_RESOURCE_V4_CANDIDATE_ID
    model_version: str = REGION_RESOURCE_V4_MODEL_VERSION
    permissions: RegionResourceV4Permissions = field(
        default_factory=RegionResourceV4Permissions
    )
    admission_closed: bool = True
    rule_fallback_required: bool = True
    production_runtime_ack_emitted: bool = False
    assignment_authority_granted: bool = False
    degradation_authority_granted: bool = False
    control_authority_granted: bool = False
    schema: str = REGION_RESOURCE_V4_DECISION_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != REGION_RESOURCE_V4_DECISION_SCHEMA
            or self.candidate_id != REGION_RESOURCE_V4_CANDIDATE_ID
            or self.model_version != REGION_RESOURCE_V4_MODEL_VERSION
        ):
            raise ValueError("v4 shadow decision identity changed")
        if (
            self.admission_closed is not True
            or self.rule_fallback_required is not True
            or self.production_runtime_ack_emitted
            or self.assignment_authority_granted
            or self.degradation_authority_granted
            or self.control_authority_granted
        ):
            raise ValueError("v4 shadow decision cannot grant authority")
        if self.shadow_treatment_selected:
            if (
                not self.candidate_inference_completed
                or not self.runtime_gate_passed
                or not self.projection_passed
                or not self.executable_signature_different
                or self.rule_fallback_used
            ):
                raise ValueError("v4 selected treatment lacks complete shadow evidence")
        elif not self.rule_fallback_used:
            raise ValueError("v4 unselected treatment must use rule fallback")
        if self.executable_signature_different != bool(self.difference_fields):
            raise ValueError("v4 executable difference fields are inconsistent")
        for digest in (
            self.control_executable_signature_sha256,
            self.treatment_executable_signature_sha256,
        ):
            _require_sha256(digest, "v4 executable signature")
        object.__setattr__(
            self, "difference_fields", tuple(sorted(set(self.difference_fields)))
        )
        object.__setattr__(
            self, "rejection_reasons", tuple(dict.fromkeys(self.rejection_reasons))
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class RegionResourceV4CandidateLoader:
    """Verify and load the registered v4 artifact without source-data access."""

    def __init__(
        self,
        candidate_root: str | Path,
        *,
        require_registered_binding: bool = True,
        evaluation_context: str = "runtime",
        map_location: Any = "cpu",
    ) -> None:
        if require_registered_binding:
            if not _v4_registration_available():
                raise RegionResourceV4CandidateError(
                    "v4_candidate_unregistered"
                )
        elif evaluation_context != "offline_development":
            raise RegionResourceV4CandidateError(
                "v4_unregistered_runtime_loading_forbidden"
            )
        root = Path(candidate_root)
        if root.is_symlink() or root.name != REGION_RESOURCE_V4_CANDIDATE_ID:
            raise RegionResourceV4CandidateError(
                "v4_candidate_directory_identity_mismatch"
            )
        manifest = load_region_resource_v4_candidate_manifest(
            root,
            expected_manifest_file_sha256=(
                REGION_RESOURCE_V4_REGISTERED_MANIFEST_FILE_SHA256
                if require_registered_binding
                else None
            ),
        )
        review_region_resource_v4_candidate(
            root,
            require_registered_binding=require_registered_binding,
        )
        try:
            loaded = load_region_resource_model_bundle(
                root / "bundle",
                expected_model_version=manifest.model_version,
                expected_state_dict_sha256=manifest.model_state_sha256,
                map_location=map_location,
                require_training_dataset_manifest=True,
            )
        except Exception as exc:
            raise RegionResourceV4CandidateError(
                f"v4_bundle_load_failed:{type(exc).__name__}:{exc}"
            ) from exc
        try:
            gate = RegionResourceV4InterventionGate.from_mapping(
                _read_json(root / REGION_RESOURCE_V4_GATE_FILENAME)
            )
        except Exception as exc:
            raise RegionResourceV4CandidateError(
                f"v4_intervention_gate_invalid:{type(exc).__name__}:{exc}"
            ) from exc
        self.projector = DeterministicResourceProjector(_V4_PROJECTION)
        self.rule_policy = RuleRegionResourcePolicy(
            _V4_RULE_CONFIG,
            projector=self.projector,
        )
        if gate.content_sha256 != manifest.runtime_gate_content_sha256:
            raise RegionResourceV4CandidateError(
                "v4_runtime_gate_manifest_binding_mismatch"
            )
        self.root = root
        self.manifest = manifest
        self.registered_binding_verified = bool(require_registered_binding)
        self.evaluation_context = evaluation_context
        self.loaded_bundle = loaded
        self.intervention_gate = gate
        self.policy = LearnedRegionResourcePolicy(
            loaded.model,
            loaded.manifest,
        )

    def evaluate(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceV4CandidateEvaluation:
        started = perf_counter()
        candidate_ood = self.policy.is_ood(
            snapshot,
            margin=REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_OOD_MARGIN,
        )
        if candidate_ood:
            rule = self.rule_policy.recommend(
                snapshot,
                formal_decision=formal_decision,
                fallback_reason="v4_candidate_ood",
            )
            return RegionResourceV4CandidateEvaluation(
                raw_recommendation=rule,
                projected_recommendation=rule,
                raw_confidence=0.0,
                effective_confidence=0.0,
                runtime_gate_passed=False,
                action_consistent=False,
                candidate_ood=True,
                candidate_latency_ms=(perf_counter() - started) * 1000.0,
                runtime_gate_content_sha256=(
                    self.manifest.runtime_gate_content_sha256
                ),
                rejection_reasons=("candidate_ood_rejected",),
            )
        try:
            raw = self.policy.recommend_raw(snapshot)
            projected = self.projector.project(
                snapshot,
                raw,
                formal_decision=formal_decision,
            )
            r0 = self.rule_policy.recommend(
                snapshot,
                formal_decision=formal_decision,
            )
            action_consistent, invariant_reasons = (
                evaluate_v4_intervention_invariants(
                    snapshot,
                    projected,
                    r0,
                    gate=self.intervention_gate,
                    projector=self.projector,
                    formal_decision=formal_decision,
                )
            )
        except Exception as exc:
            raise RegionResourceV4CandidateError(
                f"v4_candidate_inference_failed:{type(exc).__name__}:{exc}"
            ) from exc
        latency_ms = (perf_counter() - started) * 1000.0
        reasons: list[str] = list(invariant_reasons)
        if latency_ms > _V4_INFERENCE_TIMEOUT_S * 1000.0:
            reasons.append("candidate_inference_timeout")
        raw_confidence = float(raw.confidence)
        effective_confidence = (
            raw_confidence
            if action_consistent
            else min(raw_confidence, 0.59)
        )
        if (
            effective_confidence
            < REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD
        ):
            reasons.append("candidate_effective_confidence_below_minimum")
        reasons.extend(projected.projection_rejections)
        return RegionResourceV4CandidateEvaluation(
            raw_recommendation=raw,
            projected_recommendation=projected,
            raw_confidence=raw_confidence,
            effective_confidence=effective_confidence,
            runtime_gate_passed=not reasons,
            action_consistent=action_consistent,
            candidate_ood=False,
            candidate_latency_ms=latency_ms,
            runtime_gate_content_sha256=(
                self.manifest.runtime_gate_content_sha256
            ),
            rejection_reasons=tuple(reasons),
        )


class RegionResourceV4ShadowAdvisor:
    """Paired rule/v4 evaluator with no production authority."""

    def __init__(
        self,
        candidate_root: str | Path,
        *,
        require_registered_binding: bool = True,
        evaluation_context: str = "runtime",
        map_location: Any = "cpu",
    ) -> None:
        self.loader: RegionResourceV4CandidateLoader | None = None
        self.load_rejection_reasons: tuple[str, ...] = ()
        try:
            self.loader = RegionResourceV4CandidateLoader(
                candidate_root,
                require_registered_binding=require_registered_binding,
                evaluation_context=evaluation_context,
                map_location=map_location,
            )
        except Exception as exc:
            self.load_rejection_reasons = (
                _failure_reason("v4_candidate_load_failed", exc),
            )
        self.projector = (
            self.loader.projector
            if self.loader is not None
            else DeterministicResourceProjector(_V4_PROJECTION)
        )
        self.rule_policy = (
            self.loader.rule_policy
            if self.loader is not None
            else RuleRegionResourcePolicy(
                _V4_RULE_CONFIG,
                projector=self.projector,
            )
        )

    def advise_pair(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        evaluated_at_s: float,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceV4ShadowDecision:
        control = self.rule_policy.recommend(
            snapshot,
            formal_decision=formal_decision,
        )
        control_advisory = self.projector.build_advisory_contract(
            snapshot,
            control,
            formal_decision=formal_decision,
        )
        control_signature, _ = executable_signature(control_advisory)
        rejections = list(self.load_rejection_reasons)
        evaluation: RegionResourceV4CandidateEvaluation | None = None
        if (
            not isfinite(float(evaluated_at_s))
            or float(evaluated_at_s) < float(snapshot.timestamp_s)
            or float(evaluated_at_s)
            > float(snapshot.timestamp_s) + _V4_PROJECTION.advisory_ttl_s
        ):
            rejections.append("candidate_advisory_window_expired")
        elif self.loader is not None:
            try:
                evaluation = self.loader.evaluate(
                    snapshot,
                    formal_decision=formal_decision,
                )
                rejections.extend(evaluation.rejection_reasons)
            except Exception as exc:
                rejections.append(
                    _failure_reason("v4_candidate_evaluation_failed", exc)
                )

        candidate_advisory: RegionResourceAdvisoryContract | None = None
        candidate_signature = control_signature
        difference_fields: tuple[str, ...] = ()
        projection_passed = False
        if evaluation is not None and evaluation.runtime_gate_passed:
            try:
                candidate_advisory = self.projector.build_advisory_contract(
                    snapshot,
                    evaluation.projected_recommendation,
                    formal_decision=formal_decision,
                )
                candidate_signature, candidate_payload = executable_signature(
                    candidate_advisory
                )
                _, control_payload = executable_signature(control_advisory)
                difference_fields = executable_difference_fields(
                    control_payload,
                    candidate_payload,
                )
                projection_passed = True
                if not difference_fields:
                    rejections.append(
                        "candidate_executable_signature_matches_rule"
                    )
            except Exception as exc:
                rejections.append(
                    _failure_reason("v4_candidate_projection_failed", exc)
                )

        selected = bool(
            evaluation is not None
            and evaluation.runtime_gate_passed
            and projection_passed
            and difference_fields
            and not rejections
        )
        treatment = (
            evaluation.projected_recommendation
            if selected and evaluation is not None
            else self.rule_policy.recommend(
                snapshot,
                formal_decision=formal_decision,
                fallback_reason="v4_shadow_rule_fallback",
            )
        )
        treatment_advisory = (
            candidate_advisory
            if selected and candidate_advisory is not None
            else self.projector.build_advisory_contract(
                snapshot,
                treatment,
                formal_decision=formal_decision,
            )
        )
        treatment_signature, _ = executable_signature(treatment_advisory)
        if not selected:
            candidate_signature = treatment_signature
            difference_fields = ()
        return RegionResourceV4ShadowDecision(
            snapshot_id=snapshot.snapshot_id,
            seed=int(snapshot.seed),
            control_recommendation=control,
            treatment_recommendation=treatment,
            control_advisory=control_advisory,
            treatment_advisory=treatment_advisory,
            control_executable_signature_sha256=control_signature,
            treatment_executable_signature_sha256=treatment_signature,
            executable_signature_different=bool(
                selected and control_signature != treatment_signature
            ),
            difference_fields=difference_fields,
            candidate_inference_completed=evaluation is not None,
            runtime_gate_passed=bool(
                evaluation is not None and evaluation.runtime_gate_passed
            ),
            projection_passed=projection_passed,
            shadow_treatment_selected=selected,
            rule_fallback_used=not selected,
            rejection_reasons=tuple(rejections),
        )


def build_region_resource_v4_development_candidate(
    output_dir: str | Path,
    *,
    repository_root: str | Path,
    input_dataset_dir: str | Path,
    source_evidence_path: str | Path,
    config: RegionResourceV4BuildConfig | None = None,
) -> dict[str, Any]:
    """Train an unregistered v4 artifact from external verified data."""

    _require_torch()
    resolved = config or RegionResourceV4BuildConfig()
    destination = Path(output_dir).resolve()
    if "model_registry" in destination.parts:
        raise RegionResourceV4CandidateError(
            "v4_unregistered_registry_destination_forbidden"
        )
    if destination.name != resolved.candidate_id:
        raise RegionResourceV4CandidateError(
            "v4_output_directory_identity_mismatch"
        )
    if destination.exists():
        raise RegionResourceV4CandidateError(
            "v4_output_directory_already_exists"
        )
    external_dataset, external_evidence, governance = (
        _load_external_dataset_for_v4(
            input_dataset_dir,
            source_evidence_path=source_evidence_path,
            config=resolved,
        )
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.build-",
            dir=destination.parent,
        )
    )
    staging = temporary_parent / destination.name
    staging.mkdir()
    try:
        source_summary = _source_summary(
            repository_root,
            resolved,
            external_evidence=external_evidence,
        )
        _write_json(staging / REGION_RESOURCE_V4_SOURCE_FILENAME, source_summary)
        _write_json(
            staging / REGION_RESOURCE_V4_CONFIG_FILENAME,
            resolved.to_dict(),
        )
        _write_json(
            staging / REGION_RESOURCE_V4_GATE_FILENAME,
            REGION_RESOURCE_V4_INTERVENTION_GATE.to_dict(),
        )
        dataset_dir = staging / REGION_RESOURCE_V4_DATASET_DIRNAME
        _copy_selected_external_dataset(
            external_dataset,
            dataset_dir,
        )
        _write_json(
            staging / REGION_RESOURCE_V4_EXTERNAL_EVIDENCE_FILENAME,
            external_evidence.to_dict(),
        )
        loaded = load_region_learning_dataset_splits(
            dataset_dir,
            splits=(
                RegionLearningSplit.TRAIN,
                RegionLearningSplit.VALIDATION,
            ),
        )
        model, training_summary = _train_actor(
            loaded,
            config=resolved,
        )
        projector = DeterministicResourceProjector(_V4_PROJECTION)
        rule_policy = RuleRegionResourcePolicy(
            _V4_RULE_CONFIG,
            projector=projector,
        )
        confidence_summary = _fit_confidence_head(
            model,
            loaded,
            config=resolved,
            projector=projector,
            rule_policy=rule_policy,
        )
        gate = REGION_RESOURCE_V4_INTERVENTION_GATE
        train_samples = load_region_behavior_cloning_samples(
            loaded,
            split=RegionLearningSplit.TRAIN,
            device="cpu",
            allow_dirty_source=False,
        )
        target_inventory = _target_action_inventory(loaded)
        bundle_manifest = save_region_resource_model_bundle(
            model,
            staging / "bundle",
            model_version=resolved.model_version,
            training_graphs=tuple(sample.graph for sample in train_samples),
            created_at_utc=resolved.created_at_utc,
            training_dataset_manifest=loaded.manifest,
            lifecycle_stage=MODEL_LIFECYCLE_DEVELOPMENT,
            maximum_advisor_mode=MODEL_MAXIMUM_MODE_SHADOW,
            reward_evidence_available=False,
            final_holdout_seed_count=0,
            action_diversity_sufficient=True,
            strategy_capability_claim_allowed=False,
            target_action_inventory=target_inventory,
            runtime_confidence_gate=None,
            admission_reasons=(
                "development_only",
                "shadow_only",
                "external_truth_free_dataset_only",
                "positive_negative_confidence_calibration_required",
                "reward_evidence_unavailable",
                "formal_holdout_not_completed",
                "runtime_preflight_pending",
                "admission_closed",
                "rule_fallback_required",
                "all_production_permissions_false",
            ),
        )
        loaded_bundle = load_region_resource_model_bundle(
            staging / "bundle",
            expected_model_version=resolved.model_version,
            expected_state_dict_sha256=bundle_manifest.state_dict_sha256,
            map_location="cpu",
            require_training_dataset_manifest=True,
        )
        fixture = _evaluate_development_fixture(
            loaded_bundle,
            config=resolved,
            projector=projector,
            rule_policy=rule_policy,
        )
        training_summary.update(
            {
                "confidence_fit": confidence_summary,
                "external_dataset_governance": governance,
                "external_dataset_evidence": external_evidence.to_dict(),
                "target_action_inventory": target_inventory,
                "development_fixture": fixture,
                "intervention_gate": gate.to_dict(),
                "test_payload_fit_count": 0,
                "formal_holdout_seed_use_count": 0,
                "truth_identifier_use_count": 0,
                "future_outcome_use_count": 0,
                "permissions": RegionResourceV4Permissions().to_dict(),
            }
        )
        training_summary["content_sha256"] = _canonical_sha256(
            training_summary
        )
        _write_json(
            staging / REGION_RESOURCE_V4_TRAINING_FILENAME,
            training_summary,
        )
        artifact_files = {
            str(path.relative_to(staging)): _sha256_file(path)
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }
        manifest = RegionResourceV4CandidateManifest(
            candidate_id=resolved.candidate_id,
            model_version=resolved.model_version,
            source_identity_sha256=source_summary[
                "source_identity_sha256"
            ],
            dataset_sha256=loaded.manifest.dataset_sha256,
            dataset_split_sha256=loaded.manifest.split.split_sha256,
            external_dataset_evidence_sha256=(
                external_evidence.content_sha256
            ),
            config_sha256=_canonical_sha256(resolved.to_dict()),
            training_summary_content_sha256=training_summary[
                "content_sha256"
            ],
            bundle_manifest_sha256=artifact_files[
                "bundle/manifest.json"
            ],
            model_state_sha256=artifact_files["bundle/state_dict.pt"],
            runtime_gate_content_sha256=gate.content_sha256,
            artifact_files=artifact_files,
            development_fixture=fixture,
        )
        _write_json(
            staging / REGION_RESOURCE_V4_CANDIDATE_FILENAME,
            manifest.to_dict(),
        )
        review_region_resource_v4_candidate(
            staging,
            require_registered_binding=False,
        )
        staging.replace(destination)
        temporary_parent.rmdir()
        return {
            "candidate_manifest": manifest.to_dict(),
            "training_summary": training_summary,
            "output_dir": str(destination),
        }
    except Exception:
        shutil.rmtree(temporary_parent, ignore_errors=True)
        raise


def load_region_resource_v4_candidate_manifest(
    candidate_root: str | Path,
    *,
    expected_manifest_file_sha256: str | None = None,
) -> RegionResourceV4CandidateManifest:
    root = Path(candidate_root)
    path = root / REGION_RESOURCE_V4_CANDIDATE_FILENAME
    if root.is_symlink() or path.is_symlink():
        raise RegionResourceV4CandidateError("v4_candidate_symlink_forbidden")
    try:
        observed = _sha256_file(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = RegionResourceV4CandidateManifest.from_mapping(
            _mapping(payload, "v4 manifest")
        )
    except RegionResourceV4CandidateError:
        raise
    except Exception as exc:
        raise RegionResourceV4CandidateError(
            f"v4_candidate_manifest_invalid:{type(exc).__name__}:{exc}"
        ) from exc
    if (
        expected_manifest_file_sha256 is not None
        and observed != expected_manifest_file_sha256
    ):
        raise RegionResourceV4CandidateError(
            "v4_candidate_manifest_file_sha256_mismatch"
        )
    return manifest


def review_region_resource_v4_candidate(
    candidate_root: str | Path,
    *,
    require_registered_binding: bool = True,
) -> dict[str, Any]:
    if require_registered_binding and not _v4_registration_available():
        raise RegionResourceV4CandidateError("v4_candidate_unregistered")
    root = Path(candidate_root)
    manifest_path = root / REGION_RESOURCE_V4_CANDIDATE_FILENAME
    manifest = load_region_resource_v4_candidate_manifest(
        root,
        expected_manifest_file_sha256=(
            REGION_RESOURCE_V4_REGISTERED_MANIFEST_FILE_SHA256
            if require_registered_binding
            else None
        ),
    )
    observed_files = {
        str(path.relative_to(root)): _sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != manifest_path
    }
    if observed_files != dict(manifest.artifact_files):
        raise RegionResourceV4CandidateError(
            "v4_candidate_artifact_inventory_mismatch"
        )
    if any(path.is_symlink() for path in root.rglob("*")):
        raise RegionResourceV4CandidateError(
            "v4_candidate_artifact_symlink_forbidden"
        )
    if require_registered_binding:
        expected = {
            "content": REGION_RESOURCE_V4_REGISTERED_MANIFEST_CONTENT_SHA256,
            "model": REGION_RESOURCE_V4_REGISTERED_MODEL_STATE_SHA256,
            "bundle": REGION_RESOURCE_V4_REGISTERED_BUNDLE_MANIFEST_SHA256,
            "dataset": REGION_RESOURCE_V4_REGISTERED_DATASET_SHA256,
        }
        observed = {
            "content": manifest.content_sha256,
            "model": manifest.model_state_sha256,
            "bundle": manifest.bundle_manifest_sha256,
            "dataset": manifest.dataset_sha256,
        }
        if observed != expected:
            raise RegionResourceV4CandidateError(
                "v4_registered_identity_mismatch"
            )
    dataset = load_region_learning_dataset_splits(
        root / REGION_RESOURCE_V4_DATASET_DIRNAME,
        splits=(
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        ),
    )
    if (
        dataset.manifest.dataset_sha256 != manifest.dataset_sha256
        or dataset.manifest.split.split_sha256
        != manifest.dataset_split_sha256
    ):
        raise RegionResourceV4CandidateError(
            "v4_candidate_dataset_binding_mismatch"
        )
    loaded = load_region_resource_model_bundle(
        root / "bundle",
        expected_model_version=manifest.model_version,
        expected_state_dict_sha256=manifest.model_state_sha256,
        map_location="cpu",
        require_training_dataset_manifest=True,
    )
    if (
        loaded.manifest.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
        or loaded.manifest.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
        or loaded.manifest.assist_admitted
        or loaded.manifest.strategy_capability_claim_allowed
        or loaded.manifest.reward_evidence_available
        or not loaded.manifest.action_diversity_sufficient
        or loaded.manifest.final_holdout_seed_count != 0
        or loaded.manifest.runtime_confidence_gate is not None
    ):
        raise RegionResourceV4CandidateError(
            "v4_candidate_bundle_permission_boundary_crossed"
        )
    gate = RegionResourceV4InterventionGate.from_mapping(
        _read_json(root / REGION_RESOURCE_V4_GATE_FILENAME)
    )
    if gate.content_sha256 != manifest.runtime_gate_content_sha256:
        raise RegionResourceV4CandidateError(
            "v4_candidate_runtime_gate_binding_mismatch"
        )
    evidence = RegionResourceV4ExternalDatasetEvidence.from_mapping(
        _read_json(root / REGION_RESOURCE_V4_EXTERNAL_EVIDENCE_FILENAME)
    )
    if (
        evidence.content_sha256
        != manifest.external_dataset_evidence_sha256
        or evidence.dataset_sha256 != manifest.dataset_sha256
        or evidence.dataset_split_sha256
        != manifest.dataset_split_sha256
    ):
        raise RegionResourceV4CandidateError(
            "v4_candidate_external_evidence_binding_mismatch"
        )
    try:
        build_config = RegionResourceV4BuildConfig(
            **_read_json(root / REGION_RESOURCE_V4_CONFIG_FILENAME)
        )
    except Exception as exc:
        raise RegionResourceV4CandidateError(
            f"v4_candidate_config_invalid:{type(exc).__name__}:{exc}"
        ) from exc
    governance = _audit_external_dataset_governance(
        dataset,
        config=build_config,
    )
    training = _read_json(
        root / REGION_RESOURCE_V4_TRAINING_FILENAME
    )
    content = dict(training)
    observed_training_sha = str(content.pop("content_sha256", ""))
    if (
        _canonical_sha256(content) != observed_training_sha
        or observed_training_sha
        != manifest.training_summary_content_sha256
    ):
        raise RegionResourceV4CandidateError(
            "v4_training_summary_content_mismatch"
        )
    if training.get("external_dataset_governance") != governance:
        raise RegionResourceV4CandidateError(
            "v4_external_dataset_governance_mismatch"
        )
    return {
        "candidate_id": manifest.candidate_id,
        "model_version": manifest.model_version,
        "manifest_file_sha256": _sha256_file(manifest_path),
        "manifest_content_sha256": manifest.content_sha256,
        "model_state_sha256": manifest.model_state_sha256,
        "bundle_manifest_sha256": manifest.bundle_manifest_sha256,
        "dataset_sha256": manifest.dataset_sha256,
        "runtime_gate_content_sha256": (
            manifest.runtime_gate_content_sha256
        ),
        "development_fixture": dict(manifest.development_fixture),
        "permissions": manifest.permissions.to_dict(),
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
    }


def build_region_resource_v4_development_fixture(
    *,
    seed: int = 9901,
    region_count: int = 8,
    timestamp_s: float = 1.0,
) -> RegionResourceSnapshot:
    """Return a truth-free attribution fixture under the main safety shell."""

    if int(region_count) < 3:
        raise ValueError("v4 attribution fixture requires at least three regions")
    regions: list[RegionResourceNode] = []
    for index in range(int(region_count)):
        available = 3 if index < 5 else 2
        if index == 0:
            committed = 1
            reserve = 1
            demand = 2.0
            d1_uncertainty = 1.0
            d2_uncertainty = 1.0
            visibility = 0.2
            consistency = 0.2
        elif index == 1:
            committed = available
            reserve = 0
            demand = float(available + 1)
            d1_uncertainty = 0.1
            d2_uncertainty = 0.1
            visibility = 0.9
            consistency = 0.9
        else:
            committed = available
            reserve = 0
            demand = float(available)
            d1_uncertainty = 0.15
            d2_uncertainty = 0.10
            visibility = 0.85
            consistency = 0.90
        regions.append(
            RegionResourceNode(
                region_id=f"region-{index:03d}",
                target_demand=demand,
                high_threat_backlog=0.0,
                d1_uncertainty=d1_uncertainty,
                d2_uncertainty=d2_uncertainty,
                d5_visibility=visibility,
                d5_consistency=consistency,
                available_resources=available,
                reserve_resources=reserve,
                committed_resources=committed,
                secondary_coverage=0.85,
                secondary_readiness=0.80,
                communication_capacity=60.0,
                communication_latency_s=0.03,
                packet_loss_rate=0.01,
                current_owner_id=f"CENTER-{index:03d}",
                current_owner_layer=RegionalAuthorityLayer.CENTER,
                plan_id="v4-development-plan",
                plan_version=3,
                epoch=2,
                lease_expires_at_s=float(timestamp_s) + 60.0,
                coalition_ack_complete=True,
                owner_active=True,
                fault_fenced=False,
                assignment_conflict_count=0,
                degradation_failed=False,
            )
        )
    edges = tuple(
        RegionResourceEdge(
            source_region_id=f"region-{index:03d}",
            target_region_id=(
                f"region-{(index + 1) % int(region_count):03d}"
            ),
            transferable_resources=1,
            distance_m=400.0 + 25.0 * index,
            transfer_time_s=8.0 + 0.5 * index,
            bandwidth_mbps=24.0,
            communication_available=True,
            maneuver_available=True,
            partitioned=False,
            bidirectional=True,
            edge_id=f"edge-{index:03d}",
        )
        for index in range(int(region_count))
    )
    return RegionResourceSnapshot(
        snapshot_id=f"d4-v4-attribution-r{int(region_count)}",
        scenario_id="d4-v4-executable-transfer-held-out",
        scenario_version="v1",
        seed=int(seed),
        timestamp_s=float(timestamp_s),
        regions=tuple(regions),
        edges=edges,
    )


def executable_signature(
    advisory: RegionResourceAdvisoryContract,
) -> tuple[str, dict[str, Any]]:
    """Hash only fields consumed by the current D3 regional hint contract."""

    regions = [
        {
            "region_id": region.region_id,
            "resource_quota_delta": int(region.resource_quota_delta),
            "reserve_resources": int(
                ceil(float(region.reserve_ratio) * int(region.resources_after))
            ),
            "hold": bool(region.hold),
            "request_replan": bool(region.request_replan),
        }
        for region in sorted(advisory.regions, key=lambda item: item.region_id)
    ]
    transfers = [
        {
            "source_region_id": transfer.source_region_id,
            "target_region_id": transfer.target_region_id,
            "resource_count": int(transfer.resource_count),
            "edge_id": transfer.edge_id,
        }
        for transfer in sorted(
            advisory.transfers,
            key=lambda item: (
                item.source_region_id,
                item.target_region_id,
                item.edge_id,
            ),
        )
    ]
    payload = {"regions": regions, "transfer_allowances": transfers}
    return _canonical_sha256(payload), payload


def executable_difference_fields(
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
) -> tuple[str, ...]:
    control_regions = {
        str(item["region_id"]): item for item in control["regions"]
    }
    treatment_regions = {
        str(item["region_id"]): item for item in treatment["regions"]
    }
    fields: list[str] = []
    if set(control_regions) != set(treatment_regions):
        fields.append("region_set")
    else:
        for region_id in sorted(control_regions):
            for name in (
                "resource_quota_delta",
                "reserve_resources",
                "hold",
                "request_replan",
            ):
                if (
                    control_regions[region_id][name]
                    != treatment_regions[region_id][name]
                ):
                    fields.append(f"region:{region_id}:{name}")
    if control["transfer_allowances"] != treatment["transfer_allowances"]:
        fields.append("transfer_allowances")
    return tuple(fields)


def source_executable_signature(
    snapshot: RegionResourceSnapshot,
) -> tuple[str, dict[str, Any]]:
    """Freeze the source-cycle D3-consumable regional state."""

    payload = {
        "regions": [
            {
                "region_id": node.region_id,
                "resource_quota_delta": 0,
                "reserve_resources": int(node.reserve_resources),
                "hold": False,
                "request_replan": False,
            }
            for node in sorted(
                snapshot.regions, key=lambda item: item.region_id
            )
        ],
        "transfer_allowances": [],
    }
    return _canonical_sha256(payload), payload


def evaluate_v4_intervention_invariants(
    snapshot: RegionResourceSnapshot,
    candidate: RegionResourceRecommendation,
    r0: RegionResourceRecommendation,
    *,
    gate: RegionResourceV4InterventionGate,
    projector: DeterministicResourceProjector,
    formal_decision: RegionalFailoverDecision | None,
) -> tuple[bool, tuple[str, ...]]:
    """Validate a projected intervention without truth or future outcomes."""

    reasons: list[str] = []
    if projector.config != _V4_PROJECTION:
        reasons.append("candidate_projection_contract_mismatch")
    else:
        expected_r0 = RuleRegionResourcePolicy(
            _V4_RULE_CONFIG,
            projector=projector,
        ).recommend(
            snapshot,
            formal_decision=formal_decision,
        )
        if _canonical_sha256(to_jsonable(r0)) != _canonical_sha256(
            to_jsonable(expected_r0)
        ):
            reasons.append("r0_same_key_baseline_mismatch")
    nodes = snapshot.region_by_id
    candidate_actions = {
        action.region_id: action for action in candidate.actions
    }
    r0_actions = {action.region_id: action for action in r0.actions}
    if (
        set(candidate_actions) != set(nodes)
        or set(r0_actions) != set(nodes)
    ):
        reasons.append("candidate_region_set_mismatch")
    else:
        for region_id in sorted(nodes):
            node = nodes[region_id]
            action = candidate_actions[region_id]
            if (
                action.expected_owner_id != node.current_owner_id
                or action.expected_owner_layer != node.current_owner_layer
                or action.expected_plan_id != node.plan_id
                or action.expected_plan_version != node.plan_version
                or action.expected_epoch != node.epoch
                or action.expected_lease_expires_at_s
                != node.lease_expires_at_s
            ):
                reasons.append(
                    f"region:{region_id}:authority_identity_changed"
                )
            if (
                action.hold != r0_actions[region_id].hold
                or action.request_replan
                != r0_actions[region_id].request_replan
            ):
                reasons.append(
                    f"region:{region_id}:binary_action_differs_from_r0"
                )
    reasons.extend(candidate.projection_rejections)

    edge_by_id = {edge.edge_id: edge for edge in snapshot.edges}
    net_flow = {region_id: 0 for region_id in nodes}
    total_transfer = 0
    for transfer in candidate.transfers:
        edge = edge_by_id.get(transfer.edge_id)
        if (
            edge is None
            or not edge.permits(
                transfer.source_region_id,
                transfer.target_region_id,
            )
        ):
            reasons.append(
                f"transfer:{transfer.edge_id}:edge_identity_invalid"
            )
            continue
        if transfer.resource_count > gate.maximum_transfer_per_edge:
            reasons.append(
                f"transfer:{transfer.edge_id}:per_edge_limit_exceeded"
            )
        total_transfer += int(transfer.resource_count)
        net_flow[transfer.source_region_id] -= int(
            transfer.resource_count
        )
        net_flow[transfer.target_region_id] += int(
            transfer.resource_count
        )
    maximum_total = max(
        1,
        int(
            ceil(
                gate.maximum_total_transfer_fraction
                * snapshot.total_resources
            )
        ),
    )
    if total_transfer > maximum_total:
        reasons.append("candidate_total_transfer_limit_exceeded")
    if not candidate.transfers:
        reasons.append("candidate_transfer_missing")
    if candidate.total_quota_delta != 0 or sum(net_flow.values()) != 0:
        reasons.append("candidate_total_quota_not_conserved")
    if set(candidate_actions) == set(nodes):
        for region_id in sorted(nodes):
            if (
                candidate_actions[region_id].resource_quota_delta
                != net_flow[region_id]
            ):
                reasons.append(
                    f"region:{region_id}:quota_transfer_flow_mismatch"
                )

    candidate_advisory = projector.build_advisory_contract(
        snapshot,
        candidate,
        formal_decision=formal_decision,
    )
    r0_advisory = projector.build_advisory_contract(
        snapshot,
        r0,
        formal_decision=formal_decision,
    )
    source_signature, _ = source_executable_signature(snapshot)
    r0_signature, _ = executable_signature(r0_advisory)
    candidate_signature, _ = executable_signature(candidate_advisory)
    if candidate_signature == source_signature:
        reasons.append("candidate_signature_matches_source")
    if candidate_signature == r0_signature:
        reasons.append("candidate_signature_matches_r0")
    return not reasons, tuple(dict.fromkeys(reasons))


def _load_external_dataset_for_v4(
    dataset_dir: str | Path,
    *,
    source_evidence_path: str | Path,
    config: RegionResourceV4BuildConfig,
) -> tuple[
    LoadedRegionLearningDataset,
    RegionResourceV4ExternalDatasetEvidence,
    dict[str, Any],
]:
    root = Path(dataset_dir).resolve()
    evidence_path = Path(source_evidence_path).resolve()
    if root.is_symlink() or evidence_path.is_symlink():
        raise RegionResourceV4CandidateError(
            "v4_external_dataset_symlink_forbidden"
        )
    try:
        evidence = RegionResourceV4ExternalDatasetEvidence.from_mapping(
            _read_json(evidence_path)
        )
        loaded = load_region_learning_dataset_splits(
            root,
            splits=(
                RegionLearningSplit.TRAIN,
                RegionLearningSplit.VALIDATION,
            ),
        )
    except Exception as exc:
        raise RegionResourceV4CandidateError(
            f"v4_external_dataset_invalid:{type(exc).__name__}:{exc}"
        ) from exc
    if (
        evidence.dataset_sha256 != loaded.manifest.dataset_sha256
        or evidence.dataset_split_sha256
        != loaded.manifest.split.split_sha256
    ):
        raise RegionResourceV4CandidateError(
            "v4_external_dataset_evidence_binding_mismatch"
        )
    governance = _audit_external_dataset_governance(
        loaded,
        config=config,
    )
    return loaded, evidence, governance


def _audit_external_dataset_governance(
    loaded: LoadedRegionLearningDataset,
    *,
    config: RegionResourceV4BuildConfig,
) -> dict[str, Any]:
    manifest = loaded.manifest
    if (
        manifest.availability.dirty_episode_count != 0
        or not manifest.availability.behavior_cloning_available
    ):
        raise RegionResourceV4CandidateError(
            "v4_external_dataset_dirty_or_bc_unavailable"
        )
    split_seed_counts = {
        "train": len(manifest.split.train_seeds),
        "validation": len(manifest.split.validation_seeds),
        "test": len(manifest.split.test_seeds),
    }
    required_counts = {
        "train": config.minimum_train_seeds,
        "validation": config.minimum_validation_seeds,
        "test": config.minimum_test_seeds,
    }
    if any(
        split_seed_counts[name] < required_counts[name]
        for name in required_counts
    ):
        raise RegionResourceV4CandidateError(
            "v4_external_dataset_seed_inventory_insufficient"
        )
    if any(
        episode.split == RegionLearningSplit.TEST
        for episode in loaded.episode_records
    ):
        raise RegionResourceV4CandidateError(
            "v4_test_or_holdout_payload_read_forbidden"
        )
    if {
        episode.split for episode in loaded.episode_records
    } != {
        RegionLearningSplit.TRAIN,
        RegionLearningSplit.VALIDATION,
    }:
        raise RegionResourceV4CandidateError(
            "v4_train_validation_payload_inventory_incomplete"
        )
    for episode in loaded.episode_records:
        source = episode.source
        if (
            source.git_dirty
            or source.git_commit == "0" * len(source.git_commit)
            or source.config_sha256 == "0" * 64
        ):
            raise RegionResourceV4CandidateError(
                "v4_external_episode_source_identity_invalid"
            )

    projector = DeterministicResourceProjector(_V4_PROJECTION)
    rule_policy = RuleRegionResourcePolicy(
        _V4_RULE_CONFIG,
        projector=projector,
    )
    split_inventory: dict[str, dict[str, int]] = {}
    for split in (
        RegionLearningSplit.TRAIN,
        RegionLearningSplit.VALIDATION,
    ):
        inventory = {
            "frame_count": 0,
            "positive_executable_difference_count": 0,
            "negative_no_executable_difference_count": 0,
            "transfer_target_count": 0,
            "unsafe_difference_count": 0,
        }
        for episode in loaded.episodes(split):
            for frame in episode.frames:
                inventory["frame_count"] += 1
                target = frame.target.recommendation
                if target is None:
                    raise RegionResourceV4CandidateError(
                        "v4_external_target_unavailable"
                    )
                r0 = rule_policy.recommend(frame.snapshot)
                target_advisory = projector.build_advisory_contract(
                    frame.snapshot,
                    target,
                )
                r0_advisory = projector.build_advisory_contract(
                    frame.snapshot,
                    r0,
                )
                target_signature, _ = executable_signature(target_advisory)
                r0_signature, _ = executable_signature(r0_advisory)
                if target_signature == r0_signature:
                    inventory[
                        "negative_no_executable_difference_count"
                    ] += 1
                    continue
                valid, _ = evaluate_v4_intervention_invariants(
                    frame.snapshot,
                    target,
                    r0,
                    gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
                    projector=projector,
                    formal_decision=None,
                )
                if not valid:
                    inventory["unsafe_difference_count"] += 1
                    continue
                inventory[
                    "positive_executable_difference_count"
                ] += 1
                inventory["transfer_target_count"] += len(target.transfers)
        if (
            inventory["positive_executable_difference_count"] <= 0
            or inventory[
                "negative_no_executable_difference_count"
            ] <= 0
            or inventory["transfer_target_count"] <= 0
            or inventory["unsafe_difference_count"] > 0
        ):
            raise RegionResourceV4CandidateError(
                f"v4_{split.value}_action_diversity_or_calibration_invalid"
            )
        split_inventory[split.value] = inventory
    return {
        "dataset_sha256": manifest.dataset_sha256,
        "dataset_split_sha256": manifest.split.split_sha256,
        "split_seed_counts": split_seed_counts,
        "loaded_payload_splits": [
            RegionLearningSplit.TRAIN.value,
            RegionLearningSplit.VALIDATION.value,
        ],
        "test_payload_read_count": 0,
        "dirty_episode_count": 0,
        "truth_identifier_use_count": 0,
        "source_identity_complete": True,
        "split_action_inventory": split_inventory,
        "positive_negative_calibration_available": True,
    }


def _copy_selected_external_dataset(
    loaded: LoadedRegionLearningDataset,
    destination: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(loaded.root / "manifest.json", destination / "manifest.json")
    for episode in loaded.episode_records:
        relative = Path(episode.manifest.relative_path)
        source = loaded.root / relative
        target = destination / relative
        if source.is_symlink():
            raise RegionResourceV4CandidateError(
                "v4_external_episode_symlink_forbidden"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _train_actor(
    loaded: LoadedRegionLearningDataset,
    *,
    config: RegionResourceV4BuildConfig,
) -> tuple[SharedRegionGraphActorCritic, dict[str, Any]]:
    _require_torch()
    torch.set_num_threads(config.torch_num_threads)
    random.seed(config.random_seed)
    torch.manual_seed(config.random_seed)
    train_samples = load_region_behavior_cloning_samples(
        loaded,
        split=RegionLearningSplit.TRAIN,
        device="cpu",
        allow_dirty_source=False,
    )
    validation_samples = load_region_behavior_cloning_samples(
        loaded,
        split=RegionLearningSplit.VALIDATION,
        device="cpu",
        allow_dirty_source=False,
    )
    if not train_samples or not validation_samples:
        raise RegionResourceV4CandidateError(
            "v4_train_or_validation_samples_unavailable"
        )
    model = SharedRegionGraphActorCritic(
        hidden_dim=config.hidden_dim,
        message_passing_steps=config.message_passing_steps,
    )
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    generator = torch.Generator(device="cpu")
    generator.manual_seed(config.random_seed)
    best_loss = float("inf")
    best_epoch = 0
    best_state: dict[str, Any] | None = None
    no_improvement = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, config.epochs + 1):
        model.train()
        order = torch.randperm(
            len(train_samples), generator=generator
        ).tolist()
        weighted = 0.0
        for offset in range(0, len(order), config.batch_size):
            indices = order[offset : offset + config.batch_size]
            batch = tuple(train_samples[index] for index in indices)
            loss = behavior_cloning_step(
                model,
                optimizer,
                batch,
                max_grad_norm=config.max_grad_norm,
            )
            weighted += loss * len(indices)
        train_loss = weighted / len(train_samples)
        validation_loss = _mean_bc_loss(model, validation_samples)
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "validation_loss": validation_loss,
            }
        )
        if validation_loss < best_loss - 1.0e-9:
            best_loss = validation_loss
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
        raise RegionResourceV4CandidateError(
            "v4_training_produced_no_checkpoint"
        )
    model.load_state_dict(best_state, strict=True)
    model.eval()
    if not _model_parameters_finite(model):
        raise RegionResourceV4CandidateError(
            "v4_training_produced_nonfinite_model"
        )
    return model, {
        "schema": REGION_RESOURCE_V4_TRAINING_SCHEMA,
        "training_split": RegionLearningSplit.TRAIN.value,
        "selection_split": RegionLearningSplit.VALIDATION.value,
        "train_sample_count": len(train_samples),
        "validation_sample_count": len(validation_samples),
        "test_payload_fit_count": 0,
        "epochs_completed": len(history),
        "best_epoch": best_epoch,
        "best_validation_loss": best_loss,
        "history": history,
        "model_parameter_count": sum(
            int(parameter.numel()) for parameter in model.parameters()
        ),
        "model_parameters_finite": True,
        "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
        "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
        "actor_fit_is_behavior_cloning": True,
        "ppo_used": False,
        "formal_evaluation_authorized": False,
    }


def _fit_confidence_head(
    model: SharedRegionGraphActorCritic,
    loaded: LoadedRegionLearningDataset,
    *,
    config: RegionResourceV4BuildConfig,
    projector: DeterministicResourceProjector,
    rule_policy: RuleRegionResourcePolicy,
) -> dict[str, Any]:
    train_records = _confidence_records(
        model,
        loaded,
        split=RegionLearningSplit.TRAIN,
        projector=projector,
        rule_policy=rule_policy,
    )
    validation_records = _confidence_records(
        model,
        loaded,
        split=RegionLearningSplit.VALIDATION,
        projector=projector,
        rule_policy=rule_policy,
    )
    for name, records in (
        ("train", train_records),
        ("validation", validation_records),
    ):
        if not any(record[1] for record in records) or not any(
            not record[1] for record in records
        ):
            raise RegionResourceV4CandidateError(
                f"v4_confidence_{name}_requires_positive_and_negative_samples"
            )
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    for parameter in model.confidence_head.parameters():
        parameter.requires_grad_(True)
    optimizer = torch.optim.Adam(
        model.confidence_head.parameters(),
        lr=config.confidence_learning_rate,
    )
    order = list(range(len(train_records)))
    randomizer = random.Random(config.random_seed + 401)
    history: list[float] = []
    for _ in range(config.confidence_epochs):
        randomizer.shuffle(order)
        weighted = 0.0
        for offset in range(0, len(order), config.confidence_batch_size):
            indices = order[offset : offset + config.confidence_batch_size]
            optimizer.zero_grad()
            probabilities = torch.stack(
                [
                    model(train_records[index][0]).confidence
                    for index in indices
                ]
            )
            targets = torch.tensor(
                [float(train_records[index][1]) for index in indices],
                dtype=probabilities.dtype,
                device=probabilities.device,
            )
            loss = torch.nn.functional.mse_loss(probabilities, targets)
            if not bool(torch.isfinite(loss).item()):
                raise RegionResourceV4CandidateError(
                    "v4_confidence_fit_loss_nonfinite"
                )
            loss.backward()
            optimizer.step()
            weighted += float(loss.detach().cpu()) * len(indices)
        history.append(weighted / len(order))
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    model.eval()
    train_metrics = _confidence_metrics(model, train_records)
    validation_metrics = _confidence_metrics(model, validation_records)
    if (
        validation_metrics["positive_threshold_pass_count"] <= 0
        or validation_metrics["negative_threshold_pass_count"] > 0
        or validation_metrics["inconsistent_threshold_pass_count"] > 0
        or validation_metrics["executable_threshold_pass_count"] <= 0
    ):
        raise RegionResourceV4CandidateError(
            "v4_confidence_validation_gate_not_accepted"
        )
    return {
        "target_definition": (
            "1 only when the frozen actor matches an external truth-free "
            "executable-difference target and passes the v4 intervention "
            "invariants; no-op and mismatched outputs are explicit negatives"
        ),
        "fit_split": RegionLearningSplit.TRAIN.value,
        "audit_split": RegionLearningSplit.VALIDATION.value,
        "fit_sample_count": len(train_records),
        "validation_sample_count": len(validation_records),
        "history": history,
        "train": train_metrics,
        "validation": validation_metrics,
        "fixed_minimum_confidence": (
            REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD
        ),
        "confidence_head_only_parameter_update": True,
        "actor_frozen_during_confidence_fit": True,
        "test_payload_fit_count": 0,
        "truth_identifier_use_count": 0,
        "future_outcome_use_count": 0,
    }


def _confidence_records(
    model: SharedRegionGraphActorCritic,
    loaded: LoadedRegionLearningDataset,
    *,
    split: RegionLearningSplit,
    projector: DeterministicResourceProjector,
    rule_policy: RuleRegionResourcePolicy,
) -> tuple[tuple[Any, bool, bool, bool, tuple[str, ...]], ...]:
    policy = LearnedRegionResourcePolicy(
        model,
        _PolicyIdentity(REGION_RESOURCE_V4_MODEL_VERSION, "0" * 64),
    )
    records: list[
        tuple[Any, bool, bool, bool, tuple[str, ...]]
    ] = []
    for episode in loaded.episodes(split):
        for frame in episode.frames:
            graph = snapshot_to_region_graph(frame.snapshot, device="cpu")
            raw = policy.recommend_raw(frame.snapshot)
            projected = projector.project(frame.snapshot, raw)
            rule = rule_policy.recommend(frame.snapshot)
            valid, invariant_reasons = evaluate_v4_intervention_invariants(
                frame.snapshot,
                projected,
                rule,
                gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
                projector=projector,
                formal_decision=None,
            )
            candidate_advisory = projector.build_advisory_contract(
                frame.snapshot,
                projected,
            )
            rule_advisory = projector.build_advisory_contract(
                frame.snapshot,
                rule,
            )
            target = frame.target.recommendation
            if target is None:
                raise RegionResourceV4CandidateError(
                    "v4_confidence_target_unavailable"
                )
            target_advisory = projector.build_advisory_contract(
                frame.snapshot,
                target,
            )
            candidate_signature, _ = executable_signature(candidate_advisory)
            rule_signature, _ = executable_signature(rule_advisory)
            target_signature, _ = executable_signature(target_advisory)
            executable = candidate_signature != rule_signature
            target_executable = target_signature != rule_signature
            action_consistent = bool(
                candidate_signature == target_signature
                and (valid if target_executable else not executable)
            )
            positive = bool(target_executable and action_consistent)
            negative_reasons: list[str] = []
            if not target_executable:
                negative_reasons.append("target_no_executable_difference")
            if not executable:
                negative_reasons.append("actor_no_executable_difference")
            if candidate_signature != target_signature:
                negative_reasons.append("actor_target_signature_mismatch")
            if not valid:
                negative_reasons.append("actor_action_inconsistent")
                negative_reasons.extend(invariant_reasons)
            if projected.projection_rejections:
                negative_reasons.append("actor_projection_clipped_or_rejected")
            records.append(
                (
                    graph,
                    positive,
                    action_consistent,
                    executable,
                    tuple(dict.fromkeys(negative_reasons)),
                )
            )
    return tuple(records)


def _confidence_metrics(
    model: SharedRegionGraphActorCritic,
    records: Sequence[
        tuple[Any, bool, bool, bool, tuple[str, ...]]
    ],
) -> dict[str, Any]:
    probabilities: list[float] = []
    for graph, _, _, _, _ in records:
        with torch.no_grad():
            probabilities.append(float(model(graph).confidence.cpu()))
    threshold = REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD
    passed = [value >= threshold for value in probabilities]
    return {
        "sample_count": len(records),
        "confidence_minimum": min(probabilities),
        "confidence_mean": sum(probabilities) / len(probabilities),
        "confidence_maximum": max(probabilities),
        "target_positive_count": sum(record[1] for record in records),
        "target_negative_count": sum(not record[1] for record in records),
        "action_consistent_count": sum(record[2] for record in records),
        "executable_difference_count": sum(record[3] for record in records),
        "threshold_pass_count": sum(passed),
        "positive_threshold_pass_count": sum(
            is_pass and record[1]
            for is_pass, record in zip(passed, records, strict=True)
        ),
        "negative_threshold_pass_count": sum(
            is_pass and not record[1]
            for is_pass, record in zip(passed, records, strict=True)
        ),
        "inconsistent_threshold_pass_count": sum(
            is_pass and not record[2]
            for is_pass, record in zip(passed, records, strict=True)
        ),
        "executable_threshold_pass_count": sum(
            is_pass and record[3]
            for is_pass, record in zip(passed, records, strict=True)
        ),
        "negative_reason_inventory": {
            reason: sum(reason in record[4] for record in records)
            for reason in sorted(
                {
                    reason
                    for record in records
                    for reason in record[4]
                }
            )
        },
        "brier_score": sum(
            (probability - float(record[1])) ** 2
            for probability, record in zip(
                probabilities, records, strict=True
            )
        )
        / len(records),
    }


def _evaluate_development_fixture(
    loaded: LoadedRegionResourceModelBundle,
    *,
    config: RegionResourceV4BuildConfig,
    projector: DeterministicResourceProjector,
    rule_policy: RuleRegionResourcePolicy,
) -> dict[str, Any]:
    snapshot = build_region_resource_v4_development_fixture()
    policy = LearnedRegionResourcePolicy(loaded.model, loaded.manifest)
    if policy.is_ood(
        snapshot,
        margin=REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_OOD_MARGIN,
    ):
        raise RegionResourceV4CandidateError(
            "v4_development_fixture_is_ood"
        )
    raw = policy.recommend_raw(snapshot)
    projected = projector.project(
        snapshot,
        raw,
    )
    control = rule_policy.recommend(snapshot)
    valid, invariant_reasons = evaluate_v4_intervention_invariants(
        snapshot,
        projected,
        control,
        gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
        projector=projector,
        formal_decision=None,
    )
    control_advisory = projector.build_advisory_contract(snapshot, control)
    treatment_advisory = projector.build_advisory_contract(
        snapshot,
        projected,
    )
    control_signature, control_payload = executable_signature(
        control_advisory
    )
    treatment_signature, treatment_payload = executable_signature(
        treatment_advisory
    )
    difference_fields = executable_difference_fields(
        control_payload,
        treatment_payload,
    )
    source_signature, source_payload = source_executable_signature(snapshot)
    effective_confidence = (
        float(raw.confidence) if valid else min(float(raw.confidence), 0.59)
    )
    if (
        not valid
        or effective_confidence
        < REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD
        or not difference_fields
        or treatment_signature == source_signature
    ):
        raise RegionResourceV4CandidateError(
            "v4_development_fixture_executable_difference_unavailable:"
            + ",".join(invariant_reasons)
        )
    treatment_delta = {
        item["region_id"]: item["resource_quota_delta"]
        for item in treatment_payload["regions"]
    }
    authority_unchanged = all(
        action.expected_owner_id == snapshot.region_by_id[action.region_id].current_owner_id
        and action.expected_plan_version
        == snapshot.region_by_id[action.region_id].plan_version
        and action.expected_epoch
        == snapshot.region_by_id[action.region_id].epoch
        and action.expected_lease_expires_at_s
        == snapshot.region_by_id[action.region_id].lease_expires_at_s
        for action in projected.actions
    )
    return {
        "schema": REGION_RESOURCE_V4_FIXTURE_SCHEMA,
        "fixture_seed": snapshot.seed,
        "region_count": snapshot.region_count,
        "total_resource_count": snapshot.total_resources,
        "confirmed_source_binding_count": sum(
            node.committed_resources for node in snapshot.regions
        ),
        "source_region_id": "region-000",
        "target_region_id": "region-001",
        "source_free_resource_count": (
            snapshot.region_by_id["region-000"].available_resources
            - snapshot.region_by_id["region-000"].committed_resources
        ),
        "source_executable_signature_sha256": source_signature,
        "r0_executable_signature_sha256": control_signature,
        "treatment_executable_signature_sha256": treatment_signature,
        "treatment_differs_source": treatment_signature != source_signature,
        "treatment_differs_r0": treatment_signature != control_signature,
        "executable_signature_different": (
            control_signature != treatment_signature
        ),
        "difference_fields": list(difference_fields),
        "source_payload_sha256": _canonical_sha256(source_payload),
        "r0_transfer_count": len(control_payload["transfer_allowances"]),
        "treatment_transfer_allowances": treatment_payload[
            "transfer_allowances"
        ],
        "treatment_quota_delta": treatment_delta,
        "quota_delta_sum": sum(treatment_delta.values()),
        "owner_epoch_lease_unchanged": authority_unchanged,
        "intervention_gate_passed": valid,
        "effective_confidence": effective_confidence,
        "candidate_ood": False,
        "d3_successor_binding_required": True,
        "d3_successor_binding_available": False,
        "d3_successor_binding_status": (
            "pending_cross_module_d3_fixture_consumption"
        ),
        "truth_identifier_use_count": 0,
        "production_permission_available": False,
    }


@dataclass(frozen=True)
class _PolicyIdentity:
    model_version: str
    state_dict_sha256: str


def _source_summary(
    repository_root: str | Path,
    config: RegionResourceV4BuildConfig,
    *,
    external_evidence: RegionResourceV4ExternalDatasetEvidence,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    relative_files = (
        "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
        "region_resource.py",
        "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
        "region_resource_dataset.py",
        "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
        "region_resource_learning.py",
        "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
        "region_resource_v4_shadow_candidate.py",
    )
    files = {
        relative: _sha256_file(root / relative)
        for relative in relative_files
    }
    try:
        commit = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "HEAD"),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(root),
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                    "--",
                    "research_modules/d4_distributed_fallback",
                    "subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md",
                ),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ).stdout
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RegionResourceV4CandidateError(
            f"v4_source_git_identity_unavailable:{type(exc).__name__}"
        ) from exc
    if dirty:
        raise RegionResourceV4CandidateError(
            "v4_builder_source_worktree_dirty"
        )
    payload = {
        "schema": REGION_RESOURCE_V4_SOURCE_SCHEMA,
        "source_git_commit": commit,
        "source_worktree_dirty": dirty,
        "implementation_files": files,
        "implementation_inventory_sha256": _canonical_sha256(files),
        "config_sha256": _canonical_sha256(config.to_dict()),
        "external_dataset_evidence_sha256": (
            external_evidence.content_sha256
        ),
        "external_source_artifact_sha256": (
            external_evidence.source_artifact_sha256
        ),
        "content_addressed_rebuild_available": True,
        "clean_lineage_claimed": True,
        "truth_identifier_use_count": 0,
        "future_outcome_use_count": 0,
    }
    payload["source_identity_sha256"] = _canonical_sha256(payload)
    return payload


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
            target = frame.target.recommendation
            if target is None:
                raise RegionResourceV4CandidateError(
                    "v4_target_recommendation_unavailable"
                )
            inventory["action_count"] += len(target.actions)
            inventory["resource_quota_nonzero_count"] += sum(
                action.resource_quota_delta != 0 for action in target.actions
            )
            inventory["transfer_count"] += len(target.transfers)
            inventory["hold_true_count"] += sum(
                action.hold for action in target.actions
            )
            inventory["request_replan_true_count"] += sum(
                action.request_replan for action in target.actions
            )
    return inventory


def _mean_bc_loss(
    model: SharedRegionGraphActorCritic,
    samples: Sequence[Any],
) -> float:
    model.eval()
    with torch.no_grad():
        loss = torch.stack(
            [behavior_cloning_loss(model, sample.graph, sample.target) for sample in samples]
        ).mean()
    value = float(loss.cpu())
    if not isfinite(value):
        raise RegionResourceV4CandidateError(
            "v4_validation_loss_nonfinite"
        )
    return value


def _model_parameters_finite(model: SharedRegionGraphActorCritic) -> bool:
    return all(
        bool(torch.isfinite(parameter).all()) for parameter in model.parameters()
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(_mapping(value, path.name))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
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


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value.lower()
    ):
        raise ValueError(f"{name} must be a SHA256 hex digest")


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: Iterable[str] | Mapping[str, Any],
    name: str,
) -> None:
    expected_keys = set(expected)
    if set(value) != expected_keys:
        raise ValueError(f"{name} keys mismatch")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _failure_reason(prefix: str, exc: Exception) -> str:
    return f"{prefix}:{type(exc).__name__}:{exc}"


def _v4_registration_available() -> bool:
    values = (
        REGION_RESOURCE_V4_REGISTERED_MANIFEST_FILE_SHA256,
        REGION_RESOURCE_V4_REGISTERED_MANIFEST_CONTENT_SHA256,
        REGION_RESOURCE_V4_REGISTERED_MODEL_STATE_SHA256,
        REGION_RESOURCE_V4_REGISTERED_BUNDLE_MANIFEST_SHA256,
        REGION_RESOURCE_V4_REGISTERED_DATASET_SHA256,
    )
    if all(value is None for value in values):
        return False
    if any(value is None for value in values):
        raise RegionResourceV4CandidateError(
            "v4_registry_binding_partially_configured"
        )
    for index, value in enumerate(values):
        _require_sha256(str(value), f"v4_registered_digest_{index}")
    return True


def _require_torch() -> None:
    if torch is None:
        raise RegionResourceV4CandidateError(
            "v4 candidate requires the optional torch dependency"
        )


REGION_RESOURCE_V4_INTERVENTION_GATE = RegionResourceV4InterventionGate()
