"""Read-only shadow runtime boundary for the frozen current-lineage A2 model.

The adapter loads one exact development candidate, evaluates caller-provided
truth-free snapshots, and returns content-addressed diagnostics.  It cannot
publish D3 plans, acknowledge runtime consumption, form coalitions, attach a
physical outcome, compare against R0, or grant execution authority.

Formal unseen seed selection is deliberately outside this module.  Main must
provide a content-addressed seed registration for every episode.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

from .region_resource import (
    DeterministicResourceProjector,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
)
from .region_resource_current_lineage_candidate import (
    REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_FILENAME,
    REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID,
    REGION_RESOURCE_CURRENT_LINEAGE_MODEL_VERSION,
    REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_FILENAME,
    RegionResourceCurrentLineageCandidateError,
    RegionResourceCurrentLineageCandidateManifest,
    RegionResourceCurrentLineageSourceSummary,
    load_region_resource_current_lineage_candidate_manifest,
)
from .region_resource_development_candidate import (
    REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
    RegionResourceDevelopmentGateEvaluation,
    evaluate_region_resource_development_gate,
)
from .region_resource_isolated_rollout import (
    REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
    REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
    RegionResourceIsolatedCandidateGate,
)
from .region_resource_learning import (
    EDGE_FEATURE_NAMES,
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    NODE_FEATURE_NAMES,
    LearnedRegionResourcePolicy,
    load_region_resource_model_bundle,
    snapshot_to_region_graph,
)
from .region_resource_safe_adoption import (
    _build_projected_intervention_evidence,
)


REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-record-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_BINDING_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-binding-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_REGISTRATION_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-seed-registration-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_INPUT_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-input-summary-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_REGION_VERSION_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-region-version-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_PERMISSIONS_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-permissions-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_REVIEW_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-review-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_OOD_DIAGNOSTIC_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-ood-diagnostic-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_OOD_VIOLATION_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-ood-violation-v1"
)
REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_COMPATIBILITY_SCHEMA = (
    "d4-region-resource-current-lineage-shadow-compatibility-v1"
)

FROZEN_CURRENT_LINEAGE_GIT_COMMIT = (
    "b0d498d9e76e19e9045e127b6dae26ea164b3fa4"
)
FROZEN_CURRENT_LINEAGE_MANIFEST_FILE_SHA256 = (
    "7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64"
)
FROZEN_CURRENT_LINEAGE_MANIFEST_CONTENT_SHA256 = (
    "b51f2ed01d7f8b963166fe1d7e73acd6a481c5359d54ed5c3712371733aa6ba9"
)
FROZEN_CURRENT_LINEAGE_MODEL_STATE_SHA256 = (
    "fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047"
)
FROZEN_CURRENT_LINEAGE_SOURCE_IDENTITY_SHA256 = (
    "b81780cece11c792acb3113af2d4be48a19b51c0337a67c926b388197d09dfdf"
)
FROZEN_CURRENT_LINEAGE_SOURCE_SUMMARY_FILE_SHA256 = (
    "d4d678a3f1625e01999dde819641c57a7f29a0055b992cf7c0e8677f268ad9a7"
)
FROZEN_CURRENT_LINEAGE_BUNDLE_MANIFEST_SHA256 = (
    "d9fcdb348b3de8fd139b5052a4e7123a48641975cc7dcc708701a2a72ff7ab00"
)


class RegionResourceCurrentLineageShadowError(RuntimeError):
    """Fail-closed error at the frozen shadow boundary."""


class RegionResourceCurrentLineageShadowClassification(str, Enum):
    """Non-authoritative classification of one projected model output."""

    GATE_PASS_IDENTIFIABLE_NONZERO = "gate_pass_identifiable_nonzero"
    GATE_PASS_NO_IDENTIFIABLE_CHANGE = "gate_pass_no_identifiable_change"
    GATE_REJECT_IDENTIFIABLE_NONZERO = "gate_reject_identifiable_nonzero"
    GATE_REJECT_NO_IDENTIFIABLE_CHANGE = (
        "gate_reject_no_identifiable_change"
    )


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowCandidateBinding:
    candidate_id: str
    model_version: str
    source_git_commit: str
    source_identity_sha256: str
    candidate_manifest_file_sha256: str
    candidate_manifest_content_sha256: str
    source_summary_file_sha256: str
    bundle_manifest_sha256: str
    model_state_sha256: str
    dataset_sha256: str
    dataset_split_sha256: str
    binding_sha256: str = ""
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_BINDING_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_BINDING_SCHEMA:
            raise ValueError("unsupported current-lineage shadow binding schema")
        for name in (
            "candidate_id",
            "model_version",
            "source_git_commit",
        ):
            _required_text(getattr(self, name), name)
        if len(self.source_git_commit) != 40:
            raise ValueError("source_git_commit must be a full Git object id")
        for name in (
            "source_identity_sha256",
            "candidate_manifest_file_sha256",
            "candidate_manifest_content_sha256",
            "source_summary_file_sha256",
            "bundle_manifest_sha256",
            "model_state_sha256",
            "dataset_sha256",
            "dataset_split_sha256",
        ):
            _require_sha256(getattr(self, name), name)
        expected = _canonical_sha256(self.content_dict())
        if self.binding_sha256 and self.binding_sha256 != expected:
            raise ValueError("shadow candidate binding SHA256 mismatch")
        object.__setattr__(self, "binding_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_id": self.candidate_id,
            "model_version": self.model_version,
            "source_git_commit": self.source_git_commit,
            "source_identity_sha256": self.source_identity_sha256,
            "candidate_manifest_file_sha256": (
                self.candidate_manifest_file_sha256
            ),
            "candidate_manifest_content_sha256": (
                self.candidate_manifest_content_sha256
            ),
            "source_summary_file_sha256": (
                self.source_summary_file_sha256
            ),
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "model_state_sha256": self.model_state_sha256,
            "dataset_sha256": self.dataset_sha256,
            "dataset_split_sha256": self.dataset_split_sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "binding_sha256": self.binding_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageShadowCandidateBinding":
        _require_exact_keys(value, cls.__dataclass_fields__, "candidate_binding")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowSeedRegistration:
    """Main-owned registration for one caller-selected shadow episode seed."""

    registry_id: str
    registry_version: int
    episode_id: str
    scenario_id: str
    scenario_version: str
    seed: int
    candidate_binding_sha256: str
    excluded_calibration_seeds: tuple[int, ...]
    calibration_catalog_complete: bool
    registered_by: str = "main"
    seed_selected_by: str = "main"
    purpose: str = "strict_unseen_shadow"
    shadow_only: bool = True
    registration_sha256: str = ""
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_REGISTRATION_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema
            != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_REGISTRATION_SCHEMA
        ):
            raise ValueError("unsupported shadow seed registration schema")
        for name in (
            "registry_id",
            "episode_id",
            "scenario_id",
            "scenario_version",
        ):
            _required_text(getattr(self, name), name)
        if self.registered_by != "main" or self.seed_selected_by != "main":
            raise ValueError("shadow seeds must be registered and selected by main")
        if self.purpose != "strict_unseen_shadow" or self.shadow_only is not True:
            raise ValueError("seed registration crossed the shadow-only boundary")
        if self.calibration_catalog_complete is not True:
            raise ValueError("main must declare the calibration exclusion catalog complete")
        _positive_int(self.registry_version, "registry_version")
        _nonnegative_int(self.seed, "seed")
        _require_sha256(
            self.candidate_binding_sha256, "candidate_binding_sha256"
        )
        excluded = _canonical_seed_tuple(self.excluded_calibration_seeds)
        object.__setattr__(self, "excluded_calibration_seeds", excluded)
        expected = _canonical_sha256(self.content_dict())
        if self.registration_sha256 and self.registration_sha256 != expected:
            raise ValueError("shadow seed registration SHA256 mismatch")
        object.__setattr__(self, "registration_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "episode_id": self.episode_id,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "seed": self.seed,
            "candidate_binding_sha256": self.candidate_binding_sha256,
            "excluded_calibration_seeds": list(
                self.excluded_calibration_seeds
            ),
            "calibration_catalog_complete": (
                self.calibration_catalog_complete
            ),
            "registered_by": self.registered_by,
            "seed_selected_by": self.seed_selected_by,
            "purpose": self.purpose,
            "shadow_only": self.shadow_only,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.content_dict(),
            "registration_sha256": self.registration_sha256,
        }

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageShadowSeedRegistration":
        _require_exact_keys(value, cls.__dataclass_fields__, "seed_registration")
        payload = dict(value)
        payload["excluded_calibration_seeds"] = tuple(
            payload["excluded_calibration_seeds"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowRegionVersion:
    region_id: str
    owner_id: str | None
    owner_layer: str
    plan_id: str
    plan_version: int
    epoch: int
    lease_expires_at_s: float
    coalition_ack_complete: bool
    owner_active: bool
    fault_fenced: bool
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_REGION_VERSION_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema
            != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_REGION_VERSION_SCHEMA
        ):
            raise ValueError("unsupported shadow region version schema")
        _required_text(self.region_id, "region_id")
        _required_text(self.owner_layer, "owner_layer")
        _required_text(self.plan_id, "plan_id")
        if self.owner_id is not None:
            _required_text(self.owner_id, "owner_id")
        _nonnegative_int(self.plan_version, "plan_version")
        _nonnegative_int(self.epoch, "epoch")
        _finite_nonnegative(
            self.lease_expires_at_s, "lease_expires_at_s"
        )
        for name in (
            "coalition_ack_complete",
            "owner_active",
            "fault_fenced",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageShadowRegionVersion":
        _require_exact_keys(value, cls.__dataclass_fields__, "region_version")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowInputSummary:
    episode_id: str
    seed: int
    frame_index: int
    scenario_id: str
    scenario_version: str
    snapshot_id: str
    snapshot_version: int
    timestamp_s: float
    snapshot_payload_sha256: str
    authority_digest: str
    region_count: int
    edge_count: int
    total_resources: int
    committed_resources: int
    total_target_demand: float
    total_high_threat_backlog: float
    region_versions: tuple[
        RegionResourceCurrentLineageShadowRegionVersion, ...
    ]
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_INPUT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_INPUT_SCHEMA:
            raise ValueError("unsupported current-lineage shadow input schema")
        for name in (
            "episode_id",
            "scenario_id",
            "scenario_version",
            "snapshot_id",
            "authority_digest",
        ):
            _required_text(getattr(self, name), name)
        for name in (
            "seed",
            "frame_index",
            "region_count",
            "edge_count",
            "total_resources",
            "committed_resources",
        ):
            _nonnegative_int(getattr(self, name), name)
        _positive_int(self.snapshot_version, "snapshot_version")
        for name in (
            "timestamp_s",
            "total_target_demand",
            "total_high_threat_backlog",
        ):
            _finite_nonnegative(getattr(self, name), name)
        _require_sha256(
            self.snapshot_payload_sha256, "snapshot_payload_sha256"
        )
        versions = tuple(self.region_versions)
        if len(versions) != self.region_count:
            raise ValueError("region version inventory does not match region_count")
        if len({item.region_id for item in versions}) != len(versions):
            raise ValueError("shadow input region versions must be unique")
        object.__setattr__(self, "region_versions", versions)
        expected = _canonical_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("shadow input summary SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "episode_id": self.episode_id,
            "seed": self.seed,
            "frame_index": self.frame_index,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "snapshot_id": self.snapshot_id,
            "snapshot_version": self.snapshot_version,
            "timestamp_s": self.timestamp_s,
            "snapshot_payload_sha256": self.snapshot_payload_sha256,
            "authority_digest": self.authority_digest,
            "region_count": self.region_count,
            "edge_count": self.edge_count,
            "total_resources": self.total_resources,
            "committed_resources": self.committed_resources,
            "total_target_demand": self.total_target_demand,
            "total_high_threat_backlog": self.total_high_threat_backlog,
            "region_versions": [
                item.to_dict() for item in self.region_versions
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageShadowInputSummary":
        _require_exact_keys(value, cls.__dataclass_fields__, "input_summary")
        payload = dict(value)
        payload["region_versions"] = tuple(
            RegionResourceCurrentLineageShadowRegionVersion.from_mapping(item)
            for item in payload["region_versions"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowOODViolation:
    feature_scope: str
    entity_id: str
    feature_name: str
    feature_index: int
    observed_value: float
    training_minimum: float
    training_maximum: float
    accepted_minimum: float
    accepted_maximum: float
    direction: str
    exceedance: float
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_OOD_VIOLATION_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema
            != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_OOD_VIOLATION_SCHEMA
        ):
            raise ValueError("unsupported shadow OOD violation schema")
        if self.feature_scope not in {"node", "edge"}:
            raise ValueError("OOD feature scope must be node or edge")
        for name in ("entity_id", "feature_name"):
            _required_text(getattr(self, name), name)
        _nonnegative_int(self.feature_index, "feature_index")
        for name in (
            "training_minimum",
            "training_maximum",
            "accepted_minimum",
            "accepted_maximum",
            "exceedance",
        ):
            _finite_nonnegative_or_signed(getattr(self, name), name)
        if self.training_minimum > self.training_maximum:
            raise ValueError("OOD training feature bounds are inverted")
        if self.accepted_minimum > self.accepted_maximum:
            raise ValueError("OOD accepted feature bounds are inverted")
        if self.direction not in {"below", "above", "nonfinite"}:
            raise ValueError("OOD violation direction is invalid")
        if self.direction == "nonfinite":
            if isfinite(float(self.observed_value)):
                raise ValueError("nonfinite OOD reason requires nonfinite input")
        elif not isfinite(float(self.observed_value)):
            raise ValueError("finite OOD direction requires finite input")
        if self.exceedance < 0.0:
            raise ValueError("OOD exceedance must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageShadowOODViolation":
        _require_exact_keys(value, cls.__dataclass_fields__, "ood_violation")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowOODDiagnostic:
    margin: float
    node_count: int
    directed_edge_count: int
    feature_ood: bool
    violations: tuple[
        RegionResourceCurrentLineageShadowOODViolation, ...
    ]
    feature_violation_counts: Mapping[str, int]
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_OOD_DIAGNOSTIC_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema
            != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_OOD_DIAGNOSTIC_SCHEMA
        ):
            raise ValueError("unsupported shadow OOD diagnostic schema")
        if (
            not isfinite(float(self.margin))
            or float(self.margin) != REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN
        ):
            raise ValueError("shadow OOD margin must remain fixed at 0.05")
        _nonnegative_int(self.node_count, "node_count")
        _nonnegative_int(self.directed_edge_count, "directed_edge_count")
        if type(self.feature_ood) is not bool:
            raise ValueError("feature_ood must be boolean")
        violations = tuple(self.violations)
        object.__setattr__(self, "violations", violations)
        if self.feature_ood != bool(violations):
            raise ValueError("feature_ood contradicts its violation inventory")
        expected_counts = Counter(
            f"{item.feature_scope}:{item.feature_name}"
            for item in violations
        )
        counts = {
            str(name): int(count)
            for name, count in self.feature_violation_counts.items()
        }
        if counts != dict(sorted(expected_counts.items())):
            raise ValueError("OOD feature counts do not match violations")
        if any(count <= 0 for count in counts.values()):
            raise ValueError("OOD feature counts must be positive")
        object.__setattr__(self, "feature_violation_counts", counts)
        expected = _canonical_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("shadow OOD diagnostic SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "margin": self.margin,
            "node_count": self.node_count,
            "directed_edge_count": self.directed_edge_count,
            "feature_ood": self.feature_ood,
            "violations": [item.to_dict() for item in self.violations],
            "feature_violation_counts": dict(
                sorted(self.feature_violation_counts.items())
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageShadowOODDiagnostic":
        _require_exact_keys(value, cls.__dataclass_fields__, "ood_diagnostic")
        payload = dict(value)
        payload["violations"] = tuple(
            RegionResourceCurrentLineageShadowOODViolation.from_mapping(item)
            for item in payload["violations"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowPermissions:
    d3_successor_plan_available: bool = False
    runtime_ack_available: bool = False
    owner_ack_available: bool = False
    coalition_ack_available: bool = False
    physical_window_available: bool = False
    independent_r0_available: bool = False
    paired_non_degradation_available: bool = False
    benefit_available: bool = False
    formal_evidence_available: bool = False
    assist_enabled: bool = False
    authority_enabled: bool = False
    assignment_enabled: bool = False
    takeover_enabled: bool = False
    coalition_commit_enabled: bool = False
    control_enabled: bool = False
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_PERMISSIONS_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema
            != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_PERMISSIONS_SCHEMA
        ):
            raise ValueError("unsupported shadow permissions schema")
        for name in self.__dataclass_fields__:
            if name == "schema":
                continue
            if type(getattr(self, name)) is not bool or getattr(self, name):
                raise ValueError("shadow record cannot grant evidence or permission")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageShadowPermissions":
        _require_exact_keys(value, cls.__dataclass_fields__, "permissions")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowRecord:
    candidate_binding: RegionResourceCurrentLineageShadowCandidateBinding
    seed_registration_sha256: str
    input_summary: RegionResourceCurrentLineageShadowInputSummary
    ood_diagnostic: RegionResourceCurrentLineageShadowOODDiagnostic
    candidate_gate: RegionResourceIsolatedCandidateGate
    raw_model_recommendation: RegionResourceRecommendation
    deterministic_projected_recommendation: RegionResourceRecommendation
    raw_model_action_sha256: str
    deterministic_projection_sha256: str
    projection_advisory_sha256: str
    projection_completed: bool
    projection_structurally_valid: bool
    identifiable_nonzero: bool
    intervention_fields: tuple[str, ...]
    classification: RegionResourceCurrentLineageShadowClassification | str
    rejection_reasons: tuple[str, ...]
    projection_notes: tuple[str, ...]
    execution_source: str = "deterministic_rule_fallback"
    candidate_executed: bool = False
    rule_fallback_required: bool = True
    permissions: RegionResourceCurrentLineageShadowPermissions = (
        RegionResourceCurrentLineageShadowPermissions()
    )
    record_id: str = ""
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_SCHEMA:
            raise ValueError("unsupported current-lineage shadow record schema")
        _require_sha256(
            self.seed_registration_sha256, "seed_registration_sha256"
        )
        for name in (
            "raw_model_action_sha256",
            "deterministic_projection_sha256",
            "projection_advisory_sha256",
        ):
            _require_sha256(getattr(self, name), name)
        if self.projection_completed is not True:
            raise ValueError("shadow record requires deterministic projection")
        if (
            self.candidate_gate.candidate_ood_passed
            is not (not self.ood_diagnostic.feature_ood)
        ):
            raise ValueError("candidate OOD gate contradicts detailed diagnostics")
        if type(self.projection_structurally_valid) is not bool:
            raise ValueError("projection_structurally_valid must be boolean")
        if type(self.identifiable_nonzero) is not bool:
            raise ValueError("identifiable_nonzero must be boolean")
        classification = (
            self.classification
            if isinstance(
                self.classification,
                RegionResourceCurrentLineageShadowClassification,
            )
            else RegionResourceCurrentLineageShadowClassification(
                str(self.classification)
            )
        )
        object.__setattr__(self, "classification", classification)
        if (
            self.execution_source != "deterministic_rule_fallback"
            or self.candidate_executed
            or self.rule_fallback_required is not True
        ):
            raise ValueError("shadow record crossed the no-execution boundary")
        if (
            self.raw_model_recommendation.projected
            or not self.deterministic_projected_recommendation.projected
        ):
            raise ValueError("raw/projected recommendation roles are invalid")
        if (
            self.raw_model_recommendation.policy_version
            != self.candidate_binding.model_version
            or self.raw_model_recommendation.model_sha256
            != self.candidate_binding.model_state_sha256
        ):
            raise ValueError("raw recommendation model identity mismatch")
        if (
            self.deterministic_projected_recommendation.policy_version
            != self.candidate_binding.model_version
            or self.deterministic_projected_recommendation.model_sha256
            != self.candidate_binding.model_state_sha256
        ):
            raise ValueError("projected recommendation model identity mismatch")
        if _canonical_sha256(
            self.raw_model_recommendation.to_dict()
        ) != self.raw_model_action_sha256:
            raise ValueError("raw model action SHA256 mismatch")
        if _canonical_sha256(
            self.deterministic_projected_recommendation.to_dict()
        ) != self.deterministic_projection_sha256:
            raise ValueError("deterministic projection SHA256 mismatch")
        fields = tuple(sorted(set(self.intervention_fields)))
        reasons = tuple(dict.fromkeys(self.rejection_reasons))
        notes = tuple(dict.fromkeys(self.projection_notes))
        object.__setattr__(self, "intervention_fields", fields)
        object.__setattr__(self, "rejection_reasons", reasons)
        object.__setattr__(self, "projection_notes", notes)
        if bool(fields) != self.identifiable_nonzero:
            raise ValueError("nonzero classification contradicts intervention fields")
        expected_classification = _shadow_classification(
            gate_pass=self.candidate_gate.gate_pass,
            identifiable_nonzero=self.identifiable_nonzero,
        )
        if classification is not expected_classification:
            raise ValueError("shadow classification contradicts its gates")
        if not self.candidate_gate.gate_pass and not reasons:
            raise ValueError("rejected shadow gate requires rejection reasons")
        if self.candidate_gate.gate_pass and reasons:
            raise ValueError("passing shadow gate cannot contain rejection reasons")
        expected_content = _canonical_sha256(self.content_dict())
        expected_id = f"d4-a2-shadow-{expected_content[:24]}"
        if self.record_id and self.record_id != expected_id:
            raise ValueError("shadow record id does not match content")
        if self.content_sha256 and self.content_sha256 != expected_content:
            raise ValueError("shadow record content SHA256 mismatch")
        object.__setattr__(self, "record_id", expected_id)
        object.__setattr__(self, "content_sha256", expected_content)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_binding": self.candidate_binding.to_dict(),
            "seed_registration_sha256": self.seed_registration_sha256,
            "input_summary": self.input_summary.to_dict(),
            "ood_diagnostic": self.ood_diagnostic.to_dict(),
            "candidate_gate": self.candidate_gate.to_dict(),
            "raw_model_recommendation": (
                self.raw_model_recommendation.to_dict()
            ),
            "deterministic_projected_recommendation": (
                self.deterministic_projected_recommendation.to_dict()
            ),
            "raw_model_action_sha256": self.raw_model_action_sha256,
            "deterministic_projection_sha256": (
                self.deterministic_projection_sha256
            ),
            "projection_advisory_sha256": (
                self.projection_advisory_sha256
            ),
            "projection_completed": self.projection_completed,
            "projection_structurally_valid": (
                self.projection_structurally_valid
            ),
            "identifiable_nonzero": self.identifiable_nonzero,
            "intervention_fields": list(self.intervention_fields),
            "classification": self.classification.value,
            "rejection_reasons": list(self.rejection_reasons),
            "projection_notes": list(self.projection_notes),
            "execution_source": self.execution_source,
            "candidate_executed": self.candidate_executed,
            "rule_fallback_required": self.rule_fallback_required,
            "permissions": self.permissions.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.content_dict(),
            "record_id": self.record_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCurrentLineageShadowRecord":
        _require_exact_keys(value, cls.__dataclass_fields__, "shadow_record")
        payload = dict(value)
        payload["candidate_binding"] = (
            RegionResourceCurrentLineageShadowCandidateBinding.from_mapping(
                payload["candidate_binding"]
            )
        )
        payload["input_summary"] = (
            RegionResourceCurrentLineageShadowInputSummary.from_mapping(
                payload["input_summary"]
            )
        )
        payload["ood_diagnostic"] = (
            RegionResourceCurrentLineageShadowOODDiagnostic.from_mapping(
                payload["ood_diagnostic"]
            )
        )
        payload["candidate_gate"] = (
            RegionResourceIsolatedCandidateGate.from_mapping(
                payload["candidate_gate"]
            )
        )
        payload["raw_model_recommendation"] = (
            RegionResourceRecommendation.from_dict(
                payload["raw_model_recommendation"]
            )
        )
        payload["deterministic_projected_recommendation"] = (
            RegionResourceRecommendation.from_dict(
                payload["deterministic_projected_recommendation"]
            )
        )
        payload["intervention_fields"] = tuple(
            payload["intervention_fields"]
        )
        payload["rejection_reasons"] = tuple(payload["rejection_reasons"])
        payload["projection_notes"] = tuple(payload["projection_notes"])
        payload["permissions"] = (
            RegionResourceCurrentLineageShadowPermissions.from_mapping(
                payload["permissions"]
            )
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowReview:
    record_id: str
    content_sha256: str
    candidate_binding_verified: bool = True
    seed_registration_verified: bool = True
    seed_disjointness_verified: bool = True
    sequence_verified: bool = True
    input_summary_verified: bool = True
    raw_model_action_verified: bool = True
    deterministic_projection_verified: bool = True
    classification_verified: bool = True
    permissions_closed: bool = True
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_REVIEW_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_REVIEW_SCHEMA:
            raise ValueError("unsupported shadow review schema")
        _required_text(self.record_id, "record_id")
        _require_sha256(self.content_sha256, "content_sha256")
        for name in self.__dataclass_fields__:
            if name in {"record_id", "content_sha256", "schema"}:
                continue
            if getattr(self, name) is not True:
                raise ValueError("successful shadow review must verify every boundary")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionResourceCurrentLineageShadowCompatibilityReport:
    candidate_binding: RegionResourceCurrentLineageShadowCandidateBinding
    sample_count: int
    episode_count: int
    seed_count: int
    feature_ood_count: int
    feature_ood_rate: float
    gate_pass_count: int
    identifiable_nonzero_count: int
    classification_counts: Mapping[str, int]
    feature_violation_counts: Mapping[str, int]
    runtime_compatible: bool
    current_candidate_blocker: bool
    blocker_reasons: tuple[str, ...]
    permissions: RegionResourceCurrentLineageShadowPermissions = (
        RegionResourceCurrentLineageShadowPermissions()
    )
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_COMPATIBILITY_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema
            != REGION_RESOURCE_CURRENT_LINEAGE_SHADOW_COMPATIBILITY_SCHEMA
        ):
            raise ValueError("unsupported shadow compatibility report schema")
        for name in (
            "sample_count",
            "episode_count",
            "seed_count",
            "feature_ood_count",
            "gate_pass_count",
            "identifiable_nonzero_count",
        ):
            _nonnegative_int(getattr(self, name), name)
        if self.sample_count <= 0:
            raise ValueError("compatibility report requires at least one record")
        if not 0.0 <= float(self.feature_ood_rate) <= 1.0:
            raise ValueError("feature_ood_rate must be in [0, 1]")
        if self.feature_ood_count > self.sample_count:
            raise ValueError("feature OOD count exceeds sample count")
        expected_rate = self.feature_ood_count / self.sample_count
        if abs(self.feature_ood_rate - expected_rate) > 1.0e-12:
            raise ValueError("feature OOD rate denominator mismatch")
        if type(self.runtime_compatible) is not bool:
            raise ValueError("runtime_compatible must be boolean")
        if type(self.current_candidate_blocker) is not bool:
            raise ValueError("current_candidate_blocker must be boolean")
        expected_compatible = self.feature_ood_count == 0
        if self.runtime_compatible != expected_compatible:
            raise ValueError("runtime compatibility contradicts OOD observations")
        expected_blocker = self.feature_ood_count == self.sample_count
        if self.current_candidate_blocker != expected_blocker:
            raise ValueError("candidate blocker contradicts OOD observations")
        reasons = tuple(dict.fromkeys(self.blocker_reasons))
        object.__setattr__(self, "blocker_reasons", reasons)
        if self.current_candidate_blocker and not reasons:
            raise ValueError("candidate blocker requires a reason")
        if not self.current_candidate_blocker and reasons:
            raise ValueError("non-blocking report cannot contain blocker reasons")
        expected_content = _canonical_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected_content:
            raise ValueError("compatibility report SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected_content)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_binding": self.candidate_binding.to_dict(),
            "sample_count": self.sample_count,
            "episode_count": self.episode_count,
            "seed_count": self.seed_count,
            "feature_ood_count": self.feature_ood_count,
            "feature_ood_rate": self.feature_ood_rate,
            "gate_pass_count": self.gate_pass_count,
            "identifiable_nonzero_count": (
                self.identifiable_nonzero_count
            ),
            "classification_counts": dict(
                sorted(self.classification_counts.items())
            ),
            "feature_violation_counts": dict(
                sorted(self.feature_violation_counts.items())
            ),
            "runtime_compatible": self.runtime_compatible,
            "current_candidate_blocker": self.current_candidate_blocker,
            "blocker_reasons": list(self.blocker_reasons),
            "permissions": self.permissions.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}


@dataclass
class _EpisodeSequence:
    registration_sha256: str
    highest_frame_index: int
    latest_timestamp_s: float
    region_versions: dict[
        str, RegionResourceCurrentLineageShadowRegionVersion
    ]


class RegionResourceCurrentLineageShadowAdapter:
    """Evaluate the exact frozen candidate without affecting runtime state."""

    def __init__(self, candidate_root: str | Path) -> None:
        (
            self._manifest,
            self._binding,
            self._policy,
        ) = _load_frozen_candidate(candidate_root)
        self._projector = DeterministicResourceProjector()
        self._episode_sequences: dict[str, _EpisodeSequence] = {}
        self._seed_episode: dict[int, str] = {}
        self._highest_registry_version: dict[str, int] = {}

    @property
    def candidate_binding(
        self,
    ) -> RegionResourceCurrentLineageShadowCandidateBinding:
        return self._binding

    def evaluate(
        self,
        registration: RegionResourceCurrentLineageShadowSeedRegistration
        | Mapping[str, Any],
        snapshot: RegionResourceSnapshot | Mapping[str, Any],
        *,
        frame_index: int,
    ) -> RegionResourceCurrentLineageShadowRecord:
        """Return one shadow-only record for a main-registered unseen seed."""

        return self._evaluate(
            registration,
            snapshot,
            frame_index=frame_index,
            latency_override_ms=None,
            commit_sequence=True,
        )

    def _evaluate(
        self,
        registration_source: RegionResourceCurrentLineageShadowSeedRegistration
        | Mapping[str, Any],
        snapshot_source: RegionResourceSnapshot | Mapping[str, Any],
        *,
        frame_index: int,
        latency_override_ms: float | None,
        commit_sequence: bool,
    ) -> RegionResourceCurrentLineageShadowRecord:
        registration = _parse_registration(registration_source)
        snapshot = _parse_snapshot(snapshot_source)
        _nonnegative_int(frame_index, "frame_index")
        self._validate_registration(registration, snapshot)
        input_summary = _build_input_summary(
            registration, snapshot, frame_index=frame_index
        )
        self._validate_sequence(registration, input_summary)
        ood_diagnostic = _diagnose_feature_ood(
            snapshot,
            self._policy,
            margin=REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
        )

        evaluation = evaluate_region_resource_development_gate(
            self._policy,
            snapshot,
            minimum_confidence=REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
            latency_limit_ms=REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
            ood_margin=REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
            latency_override_ms=latency_override_ms,
            projector=self._projector,
        )
        raw = evaluation.recommendation
        gate = evaluation.gate
        if (
            raw is None
            or gate.candidate_finite is not True
            or not _recommendation_finite(raw)
        ):
            raise RegionResourceCurrentLineageShadowError(
                "shadow_model_output_nonfinite_or_unavailable:"
                + ",".join(gate.rejection_reasons)
            )
        expected_candidate_id = (
            f"{self._binding.model_version}:"
            f"{self._binding.model_state_sha256}"
        )
        if (
            gate.candidate_id != expected_candidate_id
            or raw.policy_version != self._binding.model_version
            or raw.model_sha256 != self._binding.model_state_sha256
        ):
            raise RegionResourceCurrentLineageShadowError(
                "shadow_model_identity_mismatch"
            )

        try:
            projected = self._projector.project(snapshot, raw)
            advisory = self._projector.build_advisory_contract(
                snapshot, projected
            )
            intervention = _build_projected_intervention_evidence(advisory)
        except Exception as exc:
            raise RegionResourceCurrentLineageShadowError(
                "shadow_deterministic_projection_failed:"
                f"{type(exc).__name__}"
            ) from exc
        if (
            evaluation.projected_recommendation is not None
            and evaluation.projected_recommendation.to_dict()
            != projected.to_dict()
        ):
            raise RegionResourceCurrentLineageShadowError(
                "shadow_projection_not_deterministic"
            )

        identifiable = intervention.identifiable_intervention_available
        classification = _shadow_classification(
            gate_pass=gate.gate_pass,
            identifiable_nonzero=identifiable,
        )
        reasons = tuple(gate.rejection_reasons)
        if gate.gate_pass:
            reasons = ()
        projection_notes = tuple(
            dict.fromkeys(
                (
                    *projected.projection_rejections,
                    *(
                        f"publication:{reason}"
                        for reason in advisory.publication_rejections
                    ),
                )
            )
        )
        record = RegionResourceCurrentLineageShadowRecord(
            candidate_binding=self._binding,
            seed_registration_sha256=registration.registration_sha256,
            input_summary=input_summary,
            ood_diagnostic=ood_diagnostic,
            candidate_gate=gate,
            raw_model_recommendation=raw,
            deterministic_projected_recommendation=projected,
            raw_model_action_sha256=_canonical_sha256(raw.to_dict()),
            deterministic_projection_sha256=_canonical_sha256(
                projected.to_dict()
            ),
            projection_advisory_sha256=_canonical_sha256(
                advisory.to_dict()
            ),
            projection_completed=True,
            projection_structurally_valid=not advisory.publication_rejections,
            identifiable_nonzero=identifiable,
            intervention_fields=intervention.intervention_fields,
            classification=classification,
            rejection_reasons=reasons,
            projection_notes=projection_notes,
        )
        if commit_sequence:
            self._commit_sequence(registration, input_summary)
        return record

    def _validate_registration(
        self,
        registration: RegionResourceCurrentLineageShadowSeedRegistration,
        snapshot: RegionResourceSnapshot,
    ) -> None:
        if registration.candidate_binding_sha256 != self._binding.binding_sha256:
            raise RegionResourceCurrentLineageShadowError(
                "shadow_seed_registration_candidate_mismatch"
            )
        if (
            registration.scenario_id != snapshot.scenario_id
            or registration.scenario_version != snapshot.scenario_version
            or registration.seed != snapshot.seed
        ):
            raise RegionResourceCurrentLineageShadowError(
                "shadow_seed_registration_input_mismatch"
            )
        split = self._manifest.split_usage
        catalogs = {
            "train": set(split.train_seeds),
            "validation": set(split.validation_seeds),
            "test": set(split.untouched_test_seeds),
            "calibration": set(registration.excluded_calibration_seeds),
            "reserved": set(split.reserved_evaluation_seeds),
        }
        overlaps = tuple(
            name
            for name, values in catalogs.items()
            if registration.seed in values
        )
        if overlaps:
            raise RegionResourceCurrentLineageShadowError(
                "shadow_seed_overlap:" + ",".join(overlaps)
            )
        highest = self._highest_registry_version.get(registration.registry_id)
        if highest is not None and registration.registry_version < highest:
            raise RegionResourceCurrentLineageShadowError(
                "shadow_seed_registry_version_stale"
            )
        existing_episode = self._seed_episode.get(registration.seed)
        if (
            existing_episode is not None
            and existing_episode != registration.episode_id
        ):
            raise RegionResourceCurrentLineageShadowError(
                "shadow_seed_reused_by_different_episode"
            )
        existing_sequence = self._episode_sequences.get(
            registration.episode_id
        )
        if (
            existing_sequence is not None
            and existing_sequence.registration_sha256
            != registration.registration_sha256
        ):
            raise RegionResourceCurrentLineageShadowError(
                "shadow_episode_registration_changed"
            )

    def _validate_sequence(
        self,
        registration: RegionResourceCurrentLineageShadowSeedRegistration,
        summary: RegionResourceCurrentLineageShadowInputSummary,
    ) -> None:
        previous = self._episode_sequences.get(registration.episode_id)
        if previous is None:
            return
        if summary.frame_index <= previous.highest_frame_index:
            raise RegionResourceCurrentLineageShadowError(
                "shadow_frame_version_stale_or_replayed"
            )
        if summary.timestamp_s <= previous.latest_timestamp_s:
            raise RegionResourceCurrentLineageShadowError(
                "shadow_timestamp_stale_or_replayed"
            )
        for current in summary.region_versions:
            old = previous.region_versions.get(current.region_id)
            if old is None:
                continue
            old_generation = (old.epoch, old.plan_version)
            current_generation = (current.epoch, current.plan_version)
            if current_generation < old_generation:
                raise RegionResourceCurrentLineageShadowError(
                    f"shadow_region_plan_version_stale:{current.region_id}"
                )
            if current_generation == old_generation and (
                current.plan_id != old.plan_id
                or current.owner_id != old.owner_id
                or current.owner_layer != old.owner_layer
            ):
                raise RegionResourceCurrentLineageShadowError(
                    f"shadow_region_generation_identity_changed:"
                    f"{current.region_id}"
                )

    def _commit_sequence(
        self,
        registration: RegionResourceCurrentLineageShadowSeedRegistration,
        summary: RegionResourceCurrentLineageShadowInputSummary,
    ) -> None:
        self._highest_registry_version[registration.registry_id] = max(
            registration.registry_version,
            self._highest_registry_version.get(registration.registry_id, 0),
        )
        self._seed_episode[registration.seed] = registration.episode_id
        self._episode_sequences[registration.episode_id] = _EpisodeSequence(
            registration_sha256=registration.registration_sha256,
            highest_frame_index=summary.frame_index,
            latest_timestamp_s=summary.timestamp_s,
            region_versions={
                item.region_id: item for item in summary.region_versions
            },
        )


class RegionResourceCurrentLineageShadowVerifier:
    """Re-run frozen inference and projection against records in episode order."""

    def __init__(self, candidate_root: str | Path) -> None:
        self._adapter = RegionResourceCurrentLineageShadowAdapter(candidate_root)

    def verify_next(
        self,
        record_source: RegionResourceCurrentLineageShadowRecord
        | Mapping[str, Any],
        registration: RegionResourceCurrentLineageShadowSeedRegistration
        | Mapping[str, Any],
        snapshot: RegionResourceSnapshot | Mapping[str, Any],
    ) -> RegionResourceCurrentLineageShadowReview:
        record = _parse_record(record_source)
        latency = record.candidate_gate.candidate_latency_ms
        if latency is None:
            raise RegionResourceCurrentLineageShadowError(
                "shadow_record_latency_unavailable"
            )
        expected = self._adapter._evaluate(
            registration,
            snapshot,
            frame_index=record.input_summary.frame_index,
            latency_override_ms=latency,
            commit_sequence=True,
        )
        if expected.to_dict() != record.to_dict():
            raise RegionResourceCurrentLineageShadowError(
                "shadow_record_replay_mismatch"
            )
        return RegionResourceCurrentLineageShadowReview(
            record_id=record.record_id,
            content_sha256=record.content_sha256,
        )


def summarize_region_resource_current_lineage_shadow_records(
    records: Sequence[
        RegionResourceCurrentLineageShadowRecord | Mapping[str, Any]
    ],
) -> RegionResourceCurrentLineageShadowCompatibilityReport:
    """Summarize runtime compatibility without creating adoption evidence."""

    parsed = tuple(_parse_record(item) for item in records)
    if not parsed:
        raise RegionResourceCurrentLineageShadowError(
            "shadow_compatibility_records_empty"
        )
    binding = parsed[0].candidate_binding
    if any(item.candidate_binding != binding for item in parsed):
        raise RegionResourceCurrentLineageShadowError(
            "shadow_compatibility_candidate_mixed"
        )
    ood_count = sum(item.ood_diagnostic.feature_ood for item in parsed)
    classifications = Counter(item.classification.value for item in parsed)
    features: Counter[str] = Counter()
    for item in parsed:
        features.update(item.ood_diagnostic.feature_violation_counts)
    blocker = ood_count == len(parsed)
    return RegionResourceCurrentLineageShadowCompatibilityReport(
        candidate_binding=binding,
        sample_count=len(parsed),
        episode_count=len(
            {item.input_summary.episode_id for item in parsed}
        ),
        seed_count=len({item.input_summary.seed for item in parsed}),
        feature_ood_count=ood_count,
        feature_ood_rate=ood_count / len(parsed),
        gate_pass_count=sum(item.candidate_gate.gate_pass for item in parsed),
        identifiable_nonzero_count=sum(
            item.identifiable_nonzero for item in parsed
        ),
        classification_counts=dict(sorted(classifications.items())),
        feature_violation_counts=dict(sorted(features.items())),
        runtime_compatible=ood_count == 0,
        current_candidate_blocker=blocker,
        blocker_reasons=(
            ("all_shadow_frames_feature_ood",) if blocker else ()
        ),
    )


def _load_frozen_candidate(
    candidate_root: str | Path,
) -> tuple[
    RegionResourceCurrentLineageCandidateManifest,
    RegionResourceCurrentLineageShadowCandidateBinding,
    LearnedRegionResourcePolicy,
]:
    root = Path(candidate_root)
    try:
        manifest = load_region_resource_current_lineage_candidate_manifest(
            root,
            expected_manifest_file_sha256=(
                FROZEN_CURRENT_LINEAGE_MANIFEST_FILE_SHA256
            ),
        )
    except (OSError, ValueError, RegionResourceCurrentLineageCandidateError) as exc:
        raise RegionResourceCurrentLineageShadowError(
            f"frozen_candidate_manifest_rejected:{type(exc).__name__}:{exc}"
        ) from exc
    if (
        manifest.candidate_id != REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID
        or manifest.model_version
        != REGION_RESOURCE_CURRENT_LINEAGE_MODEL_VERSION
        or manifest.content_sha256
        != FROZEN_CURRENT_LINEAGE_MANIFEST_CONTENT_SHA256
        or manifest.model_state_sha256
        != FROZEN_CURRENT_LINEAGE_MODEL_STATE_SHA256
        or manifest.source_identity_sha256
        != FROZEN_CURRENT_LINEAGE_SOURCE_IDENTITY_SHA256
        or manifest.source_summary_file_sha256
        != FROZEN_CURRENT_LINEAGE_SOURCE_SUMMARY_FILE_SHA256
        or manifest.bundle_manifest_sha256
        != FROZEN_CURRENT_LINEAGE_BUNDLE_MANIFEST_SHA256
    ):
        raise RegionResourceCurrentLineageShadowError(
            "frozen_candidate_identity_mismatch"
        )
    source_path = root / REGION_RESOURCE_CURRENT_LINEAGE_SOURCE_FILENAME
    try:
        source = RegionResourceCurrentLineageSourceSummary.from_mapping(
            json.loads(source_path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RegionResourceCurrentLineageShadowError(
            f"frozen_candidate_source_rejected:{type(exc).__name__}"
        ) from exc
    if (
        source.git_commit != FROZEN_CURRENT_LINEAGE_GIT_COMMIT
        or source.source_identity_sha256
        != FROZEN_CURRENT_LINEAGE_SOURCE_IDENTITY_SHA256
        or _sha256_file(source_path)
        != FROZEN_CURRENT_LINEAGE_SOURCE_SUMMARY_FILE_SHA256
    ):
        raise RegionResourceCurrentLineageShadowError(
            "frozen_candidate_source_lineage_mismatch"
        )
    try:
        bundle = load_region_resource_model_bundle(
            root / "bundle",
            expected_model_version=manifest.model_version,
            expected_state_dict_sha256=manifest.model_state_sha256,
            map_location="cpu",
            require_training_dataset_manifest=True,
        )
    except Exception as exc:
        raise RegionResourceCurrentLineageShadowError(
            f"frozen_candidate_bundle_rejected:{type(exc).__name__}:{exc}"
        ) from exc
    if (
        bundle.manifest.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
        or bundle.manifest.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
        or bundle.manifest.assist_admitted
        or bundle.manifest.strategy_capability_claim_allowed
        or bundle.manifest.reward_evidence_available
        or bundle.manifest.final_holdout_seed_count != 0
    ):
        raise RegionResourceCurrentLineageShadowError(
            "frozen_candidate_permission_boundary_crossed"
        )
    if not all(
        bool(parameter.detach().isfinite().all().item())
        for parameter in bundle.model.parameters()
    ):
        raise RegionResourceCurrentLineageShadowError(
            "frozen_candidate_model_parameter_nonfinite"
        )
    binding = RegionResourceCurrentLineageShadowCandidateBinding(
        candidate_id=manifest.candidate_id,
        model_version=manifest.model_version,
        source_git_commit=source.git_commit,
        source_identity_sha256=source.source_identity_sha256,
        candidate_manifest_file_sha256=(
            FROZEN_CURRENT_LINEAGE_MANIFEST_FILE_SHA256
        ),
        candidate_manifest_content_sha256=manifest.content_sha256,
        source_summary_file_sha256=manifest.source_summary_file_sha256,
        bundle_manifest_sha256=manifest.bundle_manifest_sha256,
        model_state_sha256=manifest.model_state_sha256,
        dataset_sha256=manifest.dataset_sha256,
        dataset_split_sha256=manifest.dataset_split_sha256,
    )
    return manifest, binding, LearnedRegionResourcePolicy(
        bundle.model, bundle.manifest
    )


def _diagnose_feature_ood(
    snapshot: RegionResourceSnapshot,
    policy: LearnedRegionResourcePolicy,
    *,
    margin: float,
) -> RegionResourceCurrentLineageShadowOODDiagnostic:
    if float(margin) != REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN:
        raise RegionResourceCurrentLineageShadowError(
            "shadow_ood_margin_changed"
        )
    graph = snapshot_to_region_graph(snapshot, device="cpu")
    bounds = policy.manifest.feature_bounds
    violations: list[RegionResourceCurrentLineageShadowOODViolation] = []
    node_rows = graph.node_features.detach().cpu().tolist()
    for entity_id, values in zip(graph.node_ids, node_rows):
        violations.extend(
            _feature_violations(
                feature_scope="node",
                entity_id=entity_id,
                values=values,
                names=NODE_FEATURE_NAMES,
                minima=bounds.node_min,
                maxima=bounds.node_max,
                margin=margin,
            )
        )
    edge_rows = graph.edge_features.detach().cpu().tolist()
    for edge_ref, values in zip(graph.edge_refs, edge_rows):
        violations.extend(
            _feature_violations(
                feature_scope="edge",
                entity_id=(
                    f"{edge_ref.edge_id}:"
                    f"{edge_ref.source_region_id}->"
                    f"{edge_ref.target_region_id}"
                ),
                values=values,
                names=EDGE_FEATURE_NAMES,
                minima=bounds.edge_min,
                maxima=bounds.edge_max,
                margin=margin,
            )
        )
    counts = Counter(
        f"{item.feature_scope}:{item.feature_name}" for item in violations
    )
    return RegionResourceCurrentLineageShadowOODDiagnostic(
        margin=margin,
        node_count=graph.node_count,
        directed_edge_count=graph.edge_count,
        feature_ood=bool(violations),
        violations=tuple(violations),
        feature_violation_counts=dict(sorted(counts.items())),
    )


def _feature_violations(
    *,
    feature_scope: str,
    entity_id: str,
    values: Sequence[float],
    names: Sequence[str],
    minima: Sequence[float],
    maxima: Sequence[float],
    margin: float,
) -> tuple[RegionResourceCurrentLineageShadowOODViolation, ...]:
    result: list[RegionResourceCurrentLineageShadowOODViolation] = []
    for index, (name, observed, low, high) in enumerate(
        zip(names, values, minima, maxima)
    ):
        observed_value = float(observed)
        training_minimum = float(low)
        training_maximum = float(high)
        scale = max(
            abs(training_minimum),
            abs(training_maximum),
            1.0,
        )
        tolerance = margin * scale
        accepted_minimum = training_minimum - tolerance
        accepted_maximum = training_maximum + tolerance
        if not isfinite(observed_value):
            direction = "nonfinite"
            exceedance = 0.0
        elif observed_value < accepted_minimum:
            direction = "below"
            exceedance = accepted_minimum - observed_value
        elif observed_value > accepted_maximum:
            direction = "above"
            exceedance = observed_value - accepted_maximum
        else:
            continue
        result.append(
            RegionResourceCurrentLineageShadowOODViolation(
                feature_scope=feature_scope,
                entity_id=entity_id,
                feature_name=name,
                feature_index=index,
                observed_value=observed_value,
                training_minimum=training_minimum,
                training_maximum=training_maximum,
                accepted_minimum=accepted_minimum,
                accepted_maximum=accepted_maximum,
                direction=direction,
                exceedance=exceedance,
            )
        )
    return tuple(result)


def _build_input_summary(
    registration: RegionResourceCurrentLineageShadowSeedRegistration,
    snapshot: RegionResourceSnapshot,
    *,
    frame_index: int,
) -> RegionResourceCurrentLineageShadowInputSummary:
    versions = tuple(
        RegionResourceCurrentLineageShadowRegionVersion(
            region_id=node.region_id,
            owner_id=node.current_owner_id,
            owner_layer=node.current_owner_layer.value,
            plan_id=node.plan_id,
            plan_version=node.plan_version,
            epoch=node.epoch,
            lease_expires_at_s=node.lease_expires_at_s,
            coalition_ack_complete=node.coalition_ack_complete,
            owner_active=node.owner_active,
            fault_fenced=node.fault_fenced,
        )
        for node in sorted(snapshot.regions, key=lambda item: item.region_id)
    )
    return RegionResourceCurrentLineageShadowInputSummary(
        episode_id=registration.episode_id,
        seed=snapshot.seed,
        frame_index=frame_index,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        snapshot_id=snapshot.snapshot_id,
        snapshot_version=snapshot.snapshot_version,
        timestamp_s=snapshot.timestamp_s,
        snapshot_payload_sha256=_canonical_sha256(snapshot.to_dict()),
        authority_digest=snapshot.authority_digest,
        region_count=snapshot.region_count,
        edge_count=len(snapshot.edges),
        total_resources=snapshot.total_resources,
        committed_resources=sum(
            node.committed_resources for node in snapshot.regions
        ),
        total_target_demand=sum(
            node.target_demand for node in snapshot.regions
        ),
        total_high_threat_backlog=sum(
            node.high_threat_backlog for node in snapshot.regions
        ),
        region_versions=versions,
    )


def _shadow_classification(
    *,
    gate_pass: bool,
    identifiable_nonzero: bool,
) -> RegionResourceCurrentLineageShadowClassification:
    if gate_pass and identifiable_nonzero:
        return (
            RegionResourceCurrentLineageShadowClassification
            .GATE_PASS_IDENTIFIABLE_NONZERO
        )
    if gate_pass:
        return (
            RegionResourceCurrentLineageShadowClassification
            .GATE_PASS_NO_IDENTIFIABLE_CHANGE
        )
    if identifiable_nonzero:
        return (
            RegionResourceCurrentLineageShadowClassification
            .GATE_REJECT_IDENTIFIABLE_NONZERO
        )
    return (
        RegionResourceCurrentLineageShadowClassification
        .GATE_REJECT_NO_IDENTIFIABLE_CHANGE
    )


def _parse_registration(
    value: RegionResourceCurrentLineageShadowSeedRegistration
    | Mapping[str, Any],
) -> RegionResourceCurrentLineageShadowSeedRegistration:
    if isinstance(value, RegionResourceCurrentLineageShadowSeedRegistration):
        return value
    try:
        return RegionResourceCurrentLineageShadowSeedRegistration.from_mapping(
            value
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceCurrentLineageShadowError(
            f"shadow_seed_registration_invalid:{type(exc).__name__}"
        ) from exc


def _parse_snapshot(
    value: RegionResourceSnapshot | Mapping[str, Any],
) -> RegionResourceSnapshot:
    if isinstance(value, RegionResourceSnapshot):
        return value
    try:
        return RegionResourceSnapshot.from_dict(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceCurrentLineageShadowError(
            f"shadow_snapshot_invalid:{type(exc).__name__}"
        ) from exc


def _parse_record(
    value: RegionResourceCurrentLineageShadowRecord | Mapping[str, Any],
) -> RegionResourceCurrentLineageShadowRecord:
    if isinstance(value, RegionResourceCurrentLineageShadowRecord):
        return value
    try:
        return RegionResourceCurrentLineageShadowRecord.from_mapping(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceCurrentLineageShadowError(
            f"shadow_record_invalid:{type(exc).__name__}"
        ) from exc


def _recommendation_finite(
    recommendation: RegionResourceRecommendation,
) -> bool:
    values: list[float] = [
        float(recommendation.created_at_s),
        float(recommendation.confidence),
    ]
    for action in recommendation.actions:
        values.extend(
            (
                float(action.resource_quota_delta),
                float(action.reserve_ratio),
                float(action.reconnaissance_priority),
                float(action.expected_plan_version),
                float(action.expected_epoch),
                float(action.expected_lease_expires_at_s),
            )
        )
    for transfer in recommendation.transfers:
        values.extend(
            (
                float(transfer.resource_count),
                float(transfer.expected_transfer_time_s),
            )
        )
    return all(isfinite(value) for value in values)


def _canonical_seed_tuple(values: Sequence[int]) -> tuple[int, ...]:
    normalized: list[int] = []
    for value in values:
        _nonnegative_int(value, "excluded_calibration_seed")
        normalized.append(value)
    return tuple(sorted(set(normalized)))


def _require_exact_keys(
    value: Mapping[str, Any], expected: Any, path: str
) -> None:
    expected_keys = set(expected)
    observed = set(value)
    if observed != expected_keys:
        raise ValueError(
            f"{path} keys mismatch:"
            f"missing={sorted(expected_keys - observed)};"
            f"extra={sorted(observed - expected_keys)}"
        )


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _finite_nonnegative(value: Any, name: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return normalized


def _finite_nonnegative_or_signed(value: Any, name: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _require_sha256(value: Any, name: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef"
        for character in normalized
    ):
        raise ValueError(f"{name} must be a SHA-256 digest")
    return normalized


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
