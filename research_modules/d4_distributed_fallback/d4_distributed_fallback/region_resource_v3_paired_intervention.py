"""Isolated development pairing for the frozen eight-region v3 candidate.

This module deliberately adds a new development-only schema instead of
loosening the historical paired-intervention schema.  The historical schema
continues to bind formal reserved seeds 1000-1019.  This schema binds
development seeds 2003-2012 and may influence only the next cycle of an
isolated treatment arm.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

from .models import to_jsonable
from .region_resource import (
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceAdvisoryContract,
    RegionResourceProjectionConfig,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
)
from .region_resource_eight_region_candidate import (
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION,
    RegionResourceEightRegionCandidateError,
    RegionResourceEightRegionCandidateManifest,
    load_region_resource_eight_region_candidate_manifest,
    review_region_resource_eight_region_candidate,
)
from .region_resource_learning import (
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    REGION_GRAPH_ARCHITECTURE,
    LearnedRegionResourcePolicy,
    LoadedRegionResourceModelBundle,
    ModelBundleValidationError,
    RegionResourceRuntimeConfidenceGateEvaluation,
    RuntimeConfidenceGateContextError,
    load_region_resource_model_bundle,
)
from .region_resource_paired_intervention import (
    REGION_RESOURCE_PAIRED_DEVELOPMENT_SEEDS,
    REGION_RESOURCE_RESERVED_EVALUATION_SEEDS,
    REGION_RESOURCE_RULE_POLICY_NAME,
    REGION_RESOURCE_RULE_POLICY_VERSION,
    REGION_RESOURCE_V3_DEVELOPMENT_PAIRED_SPEC_SCHEMA,
    RegionResourceCandidateBundleBinding,
    RegionResourcePairedArm,
    RegionResourcePairedArmEvidence,
    RegionResourcePairedArmSpecification,
    RegionResourcePairedInputBinding,
    RegionResourcePairedInterventionExecutor,
    RegionResourcePairedSafetyShellBinding,
    RegionResourcePairedThresholds,
)
from .region_resource_runtime_ack import canonical_runtime_payload_sha256
from .regional_failover import RegionalFailoverDecision


REGION_RESOURCE_V3_ISOLATED_ARM_DECISION_SCHEMA = (
    "d4-region-resource-v3-isolated-arm-decision-v1"
)
REGION_RESOURCE_V3_ISOLATED_PAIRED_DECISION_SCHEMA = (
    "d4-region-resource-v3-isolated-paired-decision-v1"
)
REGION_RESOURCE_V3_REGISTRY_BINDING_SCHEMA = (
    "d4-region-resource-v3-registry-binding-v1"
)
REGION_RESOURCE_V3_CANDIDATE_EVALUATION_SCHEMA = (
    "d4-region-resource-v3-candidate-evaluation-v1"
)

REGION_RESOURCE_V3_DEVELOPMENT_SEEDS = (
    REGION_RESOURCE_PAIRED_DEVELOPMENT_SEEDS
)
REGION_RESOURCE_V3_CANDIDATE_MANIFEST_FILE_SHA256 = (
    "5e575ec4c0cd40ddb33ae9f06ce3b5ca015825c5ad3364733234349f143459c3"
)
REGION_RESOURCE_V3_CANDIDATE_MANIFEST_CONTENT_SHA256 = (
    "7978aec0bdf577571b9b85df10cf91f11a70f5d1b937f9dd5083bbf7e836ada2"
)
REGION_RESOURCE_V3_BUNDLE_MANIFEST_SHA256 = (
    "9f3bfb1d7b786ed88683ba1d04c0a274decd5e35a64cfd392117d6f284a6238d"
)
REGION_RESOURCE_V3_MODEL_STATE_SHA256 = (
    "ace5df6dae62f8a9a80a4cd141d50a93427e609e4caa605b9962494ebfe7f52d"
)
REGION_RESOURCE_V3_RUNTIME_GATE_CONTENT_SHA256 = (
    "7797283405cad532f2911ea5965102f3b916c4ce6ccf60c17f955ea87e0e6872"
)
REGION_RESOURCE_V3_APPLICABLE_REGION_COUNT = 8
REGION_RESOURCE_V3_INFERENCE_TIMEOUT_S = 0.050

_V3_MINIMUM_CONFIDENCE = 0.60
_V3_OOD_MARGIN = 0.05
_V3_MINIMUM_RESERVE_RATIO = 0.10
_V3_MINIMUM_RESERVE_RESOURCES = 1
_V3_ADVISORY_TTL_S = 1.5
_V3_RULE_HIGH_THREAT_WEIGHT = 2.0
_V3_RULE_UNCERTAINTY_WEIGHT = 0.5
_V3_RULE_TRANSFER_PRESSURE_MARGIN = 0.05
_V3_ALLOWED_PROJECTION_NOTES = (":clipped_by_safety_projection",)


class RegionResourceV3PairedInterventionError(RuntimeError):
    """Stable fail-closed error for the v3 isolated pairing boundary."""


@dataclass(frozen=True)
class RegionResourceV3RegistryBinding:
    """Exact content and policy identity of the registered v3 candidate."""

    candidate_id: str = REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
    candidate_schema: str = (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA
    )
    candidate_manifest_file_sha256: str = (
        REGION_RESOURCE_V3_CANDIDATE_MANIFEST_FILE_SHA256
    )
    candidate_manifest_content_sha256: str = (
        REGION_RESOURCE_V3_CANDIDATE_MANIFEST_CONTENT_SHA256
    )
    bundle_manifest_sha256: str = (
        REGION_RESOURCE_V3_BUNDLE_MANIFEST_SHA256
    )
    model_state_sha256: str = REGION_RESOURCE_V3_MODEL_STATE_SHA256
    policy_name: str = REGION_GRAPH_ARCHITECTURE
    policy_version: str = (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
    )
    applicable_region_count: int = REGION_RESOURCE_V3_APPLICABLE_REGION_COUNT
    runtime_gate_content_sha256: str = (
        REGION_RESOURCE_V3_RUNTIME_GATE_CONTENT_SHA256
    )
    schema: str = REGION_RESOURCE_V3_REGISTRY_BINDING_SCHEMA

    def __post_init__(self) -> None:
        expected = {
            "candidate_id": REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID,
            "candidate_schema": (
                REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA
            ),
            "candidate_manifest_file_sha256": (
                REGION_RESOURCE_V3_CANDIDATE_MANIFEST_FILE_SHA256
            ),
            "candidate_manifest_content_sha256": (
                REGION_RESOURCE_V3_CANDIDATE_MANIFEST_CONTENT_SHA256
            ),
            "bundle_manifest_sha256": (
                REGION_RESOURCE_V3_BUNDLE_MANIFEST_SHA256
            ),
            "model_state_sha256": REGION_RESOURCE_V3_MODEL_STATE_SHA256,
            "policy_name": REGION_GRAPH_ARCHITECTURE,
            "policy_version": (
                REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
            ),
            "applicable_region_count": (
                REGION_RESOURCE_V3_APPLICABLE_REGION_COUNT
            ),
            "runtime_gate_content_sha256": (
                REGION_RESOURCE_V3_RUNTIME_GATE_CONTENT_SHA256
            ),
            "schema": REGION_RESOURCE_V3_REGISTRY_BINDING_SCHEMA,
        }
        for name, required in expected.items():
            if getattr(self, name) != required:
                raise ValueError(f"v3 registry binding mismatch: {name}")

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    @property
    def paired_bundle(self) -> RegionResourceCandidateBundleBinding:
        return RegionResourceCandidateBundleBinding(
            bundle_id=self.candidate_id,
            bundle_version=self.policy_version,
            bundle_manifest_sha256=self.bundle_manifest_sha256,
            model_state_sha256=self.model_state_sha256,
            policy_name=self.policy_name,
            policy_version=self.policy_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceV3RegistryBinding":
        _require_exact_keys(value, cls.__dataclass_fields__, "v3_registry_binding")
        return cls(**dict(value))


REGION_RESOURCE_V3_REGISTRY_BINDING = RegionResourceV3RegistryBinding()
REGION_RESOURCE_V3_PAIRED_THRESHOLDS = RegionResourcePairedThresholds(
    inference_timeout_s=REGION_RESOURCE_V3_INFERENCE_TIMEOUT_S,
    minimum_confidence=_V3_MINIMUM_CONFIDENCE,
    ood_margin=_V3_OOD_MARGIN,
    minimum_reserve_ratio=_V3_MINIMUM_RESERVE_RATIO,
    minimum_reserve_resources=_V3_MINIMUM_RESERVE_RESOURCES,
    advisory_ttl_s=_V3_ADVISORY_TTL_S,
)


@dataclass(frozen=True)
class RegionResourceV3DevelopmentPairedSpecification:
    """Development-only two-arm inventory for seeds 2003-2012."""

    experiment_id: str
    experiment_version: str
    candidate_registry: RegionResourceV3RegistryBinding
    candidate_bundle: RegionResourceCandidateBundleBinding
    thresholds: RegionResourcePairedThresholds
    safety_shell: RegionResourcePairedSafetyShellBinding
    arms: tuple[RegionResourcePairedArmSpecification, ...]
    development_seeds: tuple[int, ...] = REGION_RESOURCE_V3_DEVELOPMENT_SEEDS
    formal_reserved_seeds: tuple[int, ...] = (
        REGION_RESOURCE_RESERVED_EVALUATION_SEEDS
    )
    development_only: bool = True
    isolated_treatment_influence_allowed: bool = True
    formal_evaluation_authorized: bool = False
    ppo_enabled: bool = False
    assist_enabled: bool = False
    authority_enabled: bool = False
    takeover_enabled: bool = False
    coalition_commit_enabled: bool = False
    control_enabled: bool = False
    production_runtime_ack_enabled: bool = False
    rule_fallback_enabled: bool = True
    specification_id: str = ""
    schema: str = REGION_RESOURCE_V3_DEVELOPMENT_PAIRED_SPEC_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V3_DEVELOPMENT_PAIRED_SPEC_SCHEMA:
            raise ValueError("unsupported v3 development paired schema")
        if not self.experiment_id or not self.experiment_version:
            raise ValueError("v3 paired experiment identity must not be empty")
        if self.candidate_registry != REGION_RESOURCE_V3_REGISTRY_BINDING:
            raise ValueError("v3 paired candidate registry binding changed")
        if self.candidate_bundle != self.candidate_registry.paired_bundle:
            raise ValueError("v3 paired bundle identity mismatch")
        if self.thresholds != REGION_RESOURCE_V3_PAIRED_THRESHOLDS:
            raise ValueError("v3 paired thresholds changed")
        development = tuple(int(seed) for seed in self.development_seeds)
        formal = tuple(int(seed) for seed in self.formal_reserved_seeds)
        if development != REGION_RESOURCE_V3_DEVELOPMENT_SEEDS:
            raise ValueError("v3 development seed inventory changed")
        if formal != REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
            raise ValueError("formal reserved seed inventory changed")
        if set(development) & set(formal):
            raise ValueError("development and formal seed inventories overlap")
        object.__setattr__(self, "development_seeds", development)
        object.__setattr__(self, "formal_reserved_seeds", formal)
        if (
            self.development_only is not True
            or self.isolated_treatment_influence_allowed is not True
            or self.formal_evaluation_authorized
            or self.rule_fallback_enabled is not True
        ):
            raise ValueError("v3 development isolation boundary changed")
        if any(
            (
                self.ppo_enabled,
                self.assist_enabled,
                self.authority_enabled,
                self.takeover_enabled,
                self.coalition_commit_enabled,
                self.control_enabled,
                self.production_runtime_ack_enabled,
            )
        ):
            raise ValueError("v3 paired specification cannot grant runtime authority")

        arms = tuple(self.arms)
        if len(arms) != 2 * len(development):
            raise ValueError("v3 pairing requires two arms per development seed")
        by_seed: dict[
            int, dict[RegionResourcePairedArm, RegionResourcePairedArmSpecification]
        ] = {}
        for arm in arms:
            seed = int(arm.input_binding.seed)
            if seed not in development:
                raise ValueError("v3 paired arm contains a non-development seed")
            bucket = by_seed.setdefault(seed, {})
            if arm.arm in bucket:
                raise ValueError("v3 paired inventory contains a duplicate arm")
            bucket[arm.arm] = arm
        if set(by_seed) != set(development):
            raise ValueError("v3 paired inventory is missing a development seed")
        for seed in development:
            pair = by_seed[seed]
            if set(pair) != set(RegionResourcePairedArm):
                raise ValueError("v3 development seed requires control and treatment")
            control = pair[RegionResourcePairedArm.CONTROL]
            treatment = pair[RegionResourcePairedArm.TREATMENT]
            if control.input_binding.to_dict() != treatment.input_binding.to_dict():
                raise ValueError("v3 paired arms must bind identical inputs")
            if (
                treatment.policy_name != self.candidate_bundle.policy_name
                or treatment.policy_version != self.candidate_bundle.policy_version
            ):
                raise ValueError("v3 treatment policy identity mismatch")
        if len({arm.arm_id for arm in arms}) != len(arms):
            raise ValueError("v3 paired arm identifiers must be unique")
        object.__setattr__(
            self,
            "arms",
            tuple(
                sorted(
                    arms,
                    key=lambda item: (
                        item.input_binding.seed,
                        item.arm.value,
                    ),
                )
            ),
        )
        expected_id = (
            "d4-rr-v3-development-paired-spec-"
            + _canonical_sha256(
                {
                    key: value
                    for key, value in self.to_dict().items()
                    if key != "specification_id"
                }
            )
        )
        if self.specification_id and self.specification_id != expected_id:
            raise ValueError("v3 specification_id does not match content")
        object.__setattr__(self, "specification_id", expected_id)

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def arm_for(
        self, seed: int, arm: RegionResourcePairedArm | str
    ) -> RegionResourcePairedArmSpecification:
        normalized = (
            arm
            if isinstance(arm, RegionResourcePairedArm)
            else RegionResourcePairedArm(str(arm))
        )
        for item in self.arms:
            if item.input_binding.seed == int(seed) and item.arm == normalized:
                return item
        raise KeyError(
            f"v3 paired arm not found: seed={seed}, arm={normalized.value}"
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceV3DevelopmentPairedSpecification":
        _require_exact_keys(value, cls.__dataclass_fields__, "v3_specification")
        payload = dict(value)
        payload["candidate_registry"] = RegionResourceV3RegistryBinding.from_dict(
            _mapping(payload["candidate_registry"], "candidate_registry")
        )
        payload["candidate_bundle"] = RegionResourceCandidateBundleBinding.from_dict(
            _mapping(payload["candidate_bundle"], "candidate_bundle")
        )
        payload["thresholds"] = RegionResourcePairedThresholds.from_dict(
            _mapping(payload["thresholds"], "thresholds")
        )
        payload["safety_shell"] = RegionResourcePairedSafetyShellBinding.from_dict(
            _mapping(payload["safety_shell"], "safety_shell")
        )
        payload["arms"] = tuple(
            RegionResourcePairedArmSpecification.from_dict(
                _mapping(item, f"arms[{index}]")
            )
            for index, item in enumerate(_sequence(payload["arms"], "arms"))
        )
        payload["development_seeds"] = tuple(payload["development_seeds"])
        payload["formal_reserved_seeds"] = tuple(
            payload["formal_reserved_seeds"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceV3CandidateEvaluation:
    """Truth-free raw inference and embedded runtime-gate result."""

    raw_recommendation: RegionResourceRecommendation
    candidate_manifest_file_sha256: str
    candidate_manifest_content_sha256: str
    bundle_manifest_sha256: str
    model_state_sha256: str
    candidate_latency_ms: float
    candidate_scope_match: bool
    candidate_ood_passed: bool
    raw_output_finite: bool
    runtime_gate_applied: bool
    runtime_gate_passed: bool
    runtime_action_consistent: bool
    raw_confidence: float
    effective_confidence: float
    runtime_gate_content_sha256: str
    runtime_gate_rejection_reasons: tuple[str, ...] = ()
    schema: str = REGION_RESOURCE_V3_CANDIDATE_EVALUATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V3_CANDIDATE_EVALUATION_SCHEMA:
            raise ValueError("unsupported v3 candidate evaluation schema")
        if self.raw_recommendation.source != RecommendationSource.LEARNED:
            raise ValueError("v3 raw inference must come from the learned policy")
        if self.raw_recommendation.projected:
            raise ValueError("v3 raw inference cannot already be projected")
        if (
            self.raw_recommendation.policy_name != REGION_GRAPH_ARCHITECTURE
            or self.raw_recommendation.policy_version
            != REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
            or self.raw_recommendation.model_sha256
            != REGION_RESOURCE_V3_MODEL_STATE_SHA256
        ):
            raise ValueError("v3 raw inference policy or model identity mismatch")
        for name, expected in (
            (
                "candidate_manifest_file_sha256",
                REGION_RESOURCE_V3_CANDIDATE_MANIFEST_FILE_SHA256,
            ),
            (
                "candidate_manifest_content_sha256",
                REGION_RESOURCE_V3_CANDIDATE_MANIFEST_CONTENT_SHA256,
            ),
            (
                "bundle_manifest_sha256",
                REGION_RESOURCE_V3_BUNDLE_MANIFEST_SHA256,
            ),
            ("model_state_sha256", REGION_RESOURCE_V3_MODEL_STATE_SHA256),
            (
                "runtime_gate_content_sha256",
                REGION_RESOURCE_V3_RUNTIME_GATE_CONTENT_SHA256,
            ),
        ):
            if getattr(self, name) != expected:
                raise ValueError(f"v3 candidate evaluation identity mismatch: {name}")
        if (
            not isfinite(float(self.candidate_latency_ms))
            or self.candidate_latency_ms < 0.0
        ):
            raise ValueError("candidate latency must be finite and non-negative")
        for name in ("raw_confidence", "effective_confidence"):
            value = float(getattr(self, name))
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        reasons = _unique(self.runtime_gate_rejection_reasons)
        object.__setattr__(self, "runtime_gate_rejection_reasons", reasons)
        expected_pass = bool(
            self.candidate_scope_match
            and self.candidate_ood_passed
            and self.raw_output_finite
            and self.runtime_gate_applied
            and self.runtime_action_consistent
            and self.effective_confidence >= _V3_MINIMUM_CONFIDENCE
            and self.candidate_latency_ms
            <= 1000.0 * REGION_RESOURCE_V3_INFERENCE_TIMEOUT_S
            and not reasons
        )
        if self.runtime_gate_passed != expected_pass:
            raise ValueError("v3 runtime gate aggregate contradicts evidence")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceV3CandidateEvaluation":
        _require_exact_keys(value, cls.__dataclass_fields__, "v3_candidate_evaluation")
        payload = dict(value)
        payload["raw_recommendation"] = RegionResourceRecommendation.from_dict(
            _mapping(payload["raw_recommendation"], "raw_recommendation")
        )
        payload["runtime_gate_rejection_reasons"] = tuple(
            payload["runtime_gate_rejection_reasons"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceV3IsolatedArmDecision:
    """Main-facing output for one isolated arm, with no production authority."""

    arm: RegionResourcePairedArm | str
    arm_id: str
    specification_id: str
    specification_sha256: str
    candidate_identity_sha256: str
    candidate_scope_compatible: bool
    selected_recommendation: RegionResourceRecommendation
    advisory_contract: RegionResourceAdvisoryContract
    arm_evidence: RegionResourcePairedArmEvidence
    raw_inference_completed: bool
    runtime_gate_applied: bool
    runtime_gate_passed: bool
    projection_passed: bool
    next_cycle_isolated_adoption: bool
    isolated_treatment_influence_allowed: bool
    isolated_treatment_influence_adopted: bool
    deterministic_rule_selected: bool
    production_runtime_ack_emitted: bool = False
    assist_authority_granted: bool = False
    assignment_authority_granted: bool = False
    degradation_authority_granted: bool = False
    takeover_authority_granted: bool = False
    coalition_commit_authority_granted: bool = False
    control_authority_granted: bool = False
    schema: str = REGION_RESOURCE_V3_ISOLATED_ARM_DECISION_SCHEMA

    def __post_init__(self) -> None:
        arm = (
            self.arm
            if isinstance(self.arm, RegionResourcePairedArm)
            else RegionResourcePairedArm(str(self.arm))
        )
        object.__setattr__(self, "arm", arm)
        if self.schema != REGION_RESOURCE_V3_ISOLATED_ARM_DECISION_SCHEMA:
            raise ValueError("unsupported v3 isolated arm decision schema")
        if self.arm_id != self.arm_evidence.arm_id or arm != self.arm_evidence.arm:
            raise ValueError("v3 arm decision evidence identity mismatch")
        if self.arm_evidence.specification_sha256 != self.specification_sha256:
            raise ValueError("v3 arm decision specification hash mismatch")
        if (
            canonical_runtime_payload_sha256(
                self.selected_recommendation.to_dict()
            )
            != self.arm_evidence.executed_recommendation_sha256
        ):
            raise ValueError("v3 selected recommendation hash mismatch")
        if (
            canonical_runtime_payload_sha256(self.advisory_contract.to_dict())
            != self.arm_evidence.advisory_payload_sha256
        ):
            raise ValueError("v3 advisory contract hash mismatch")
        if self.advisory_contract.advisory_id != self.arm_evidence.advisory_id:
            raise ValueError("v3 advisory identity mismatch")
        if self.projection_passed != (
            self.arm_evidence.candidate_safety_projection_passed
        ):
            raise ValueError("v3 projection status contradicts arm evidence")
        if self.next_cycle_isolated_adoption != (
            self.arm_evidence.isolated_treatment_safe_adopted
        ):
            raise ValueError("v3 adoption status contradicts arm evidence")
        treatment = arm == RegionResourcePairedArm.TREATMENT
        if self.isolated_treatment_influence_allowed is not treatment:
            raise ValueError("candidate influence must be treatment-only")
        if self.isolated_treatment_influence_adopted != (
            treatment and self.next_cycle_isolated_adoption
        ):
            raise ValueError("v3 treatment influence adoption is inconsistent")
        if self.deterministic_rule_selected != (
            self.selected_recommendation.source == RecommendationSource.RULE
        ):
            raise ValueError("v3 selected recommendation source is inconsistent")
        if arm == RegionResourcePairedArm.CONTROL and any(
            (
                self.raw_inference_completed,
                self.runtime_gate_applied,
                self.runtime_gate_passed,
                self.next_cycle_isolated_adoption,
            )
        ):
            raise ValueError("control arm cannot contain candidate stages")
        if self.runtime_gate_passed and not (
            self.raw_inference_completed and self.runtime_gate_applied
        ):
            raise ValueError("v3 runtime gate pass lacks raw inference")
        if self.next_cycle_isolated_adoption and not (
            self.runtime_gate_passed
            and self.projection_passed
            and not self.deterministic_rule_selected
        ):
            raise ValueError("v3 adoption lacks gate and projection evidence")
        if any(
            (
                self.production_runtime_ack_emitted,
                self.assist_authority_granted,
                self.assignment_authority_granted,
                self.degradation_authority_granted,
                self.takeover_authority_granted,
                self.coalition_commit_authority_granted,
                self.control_authority_granted,
            )
        ):
            raise ValueError("v3 isolated decision cannot grant production authority")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceV3IsolatedArmDecision":
        _require_exact_keys(value, cls.__dataclass_fields__, "v3_arm_decision")
        payload = dict(value)
        payload["selected_recommendation"] = RegionResourceRecommendation.from_dict(
            _mapping(payload["selected_recommendation"], "selected_recommendation")
        )
        payload["advisory_contract"] = RegionResourceAdvisoryContract.from_dict(
            _mapping(payload["advisory_contract"], "advisory_contract")
        )
        payload["arm_evidence"] = RegionResourcePairedArmEvidence.from_dict(
            _mapping(payload["arm_evidence"], "arm_evidence")
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceV3IsolatedPairedDecision:
    """Same-input control/treatment decision returned to main orchestration."""

    specification_id: str
    specification_sha256: str
    candidate_identity_sha256: str
    seed: int
    observed_input_sha256: str
    snapshot_payload_sha256: str
    control: RegionResourceV3IsolatedArmDecision
    treatment: RegionResourceV3IsolatedArmDecision
    candidate_evaluation: RegionResourceV3CandidateEvaluation | None
    load_or_inference_rejection_reasons: tuple[str, ...]
    isolated_treatment_influence_allowed: bool = True
    development_only: bool = True
    formal_evaluation_authorized: bool = False
    production_runtime_ack_emitted: bool = False
    assist_authority_granted: bool = False
    assignment_authority_granted: bool = False
    degradation_authority_granted: bool = False
    takeover_authority_granted: bool = False
    coalition_commit_authority_granted: bool = False
    control_authority_granted: bool = False
    schema: str = REGION_RESOURCE_V3_ISOLATED_PAIRED_DECISION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V3_ISOLATED_PAIRED_DECISION_SCHEMA:
            raise ValueError("unsupported v3 isolated paired decision schema")
        if (
            self.control.arm != RegionResourcePairedArm.CONTROL
            or self.treatment.arm != RegionResourcePairedArm.TREATMENT
        ):
            raise ValueError("v3 paired decision arm ordering changed")
        for arm in (self.control, self.treatment):
            if (
                arm.specification_id != self.specification_id
                or arm.specification_sha256 != self.specification_sha256
                or arm.candidate_identity_sha256
                != self.candidate_identity_sha256
                or arm.arm_evidence.seed != int(self.seed)
                or arm.arm_evidence.observed_input_sha256
                != self.observed_input_sha256
                or arm.arm_evidence.snapshot_payload_sha256
                != self.snapshot_payload_sha256
            ):
                raise ValueError("v3 paired decision arm binding mismatch")
        if self.control.arm_evidence.observed_input_sha256 != (
            self.treatment.arm_evidence.observed_input_sha256
        ):
            raise ValueError("v3 paired arms did not use identical inputs")
        if self.control.arm_evidence.snapshot_payload_sha256 != (
            self.treatment.arm_evidence.snapshot_payload_sha256
        ):
            raise ValueError("v3 paired arms did not use identical snapshots")
        if (
            self.isolated_treatment_influence_allowed is not True
            or self.development_only is not True
            or self.formal_evaluation_authorized
        ):
            raise ValueError("v3 paired development boundary changed")
        object.__setattr__(
            self,
            "load_or_inference_rejection_reasons",
            _unique(self.load_or_inference_rejection_reasons),
        )
        if any(
            (
                self.production_runtime_ack_emitted,
                self.assist_authority_granted,
                self.assignment_authority_granted,
                self.degradation_authority_granted,
                self.takeover_authority_granted,
                self.coalition_commit_authority_granted,
                self.control_authority_granted,
            )
        ):
            raise ValueError("v3 paired decision cannot grant production authority")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceV3IsolatedPairedDecision":
        _require_exact_keys(value, cls.__dataclass_fields__, "v3_paired_decision")
        payload = dict(value)
        payload["control"] = RegionResourceV3IsolatedArmDecision.from_dict(
            _mapping(payload["control"], "control")
        )
        payload["treatment"] = RegionResourceV3IsolatedArmDecision.from_dict(
            _mapping(payload["treatment"], "treatment")
        )
        raw_evaluation = payload["candidate_evaluation"]
        payload["candidate_evaluation"] = (
            RegionResourceV3CandidateEvaluation.from_dict(
                _mapping(raw_evaluation, "candidate_evaluation")
            )
            if raw_evaluation is not None
            else None
        )
        payload["load_or_inference_rejection_reasons"] = tuple(
            payload["load_or_inference_rejection_reasons"]
        )
        return cls(**payload)


class RegionResourceV3IsolatedCandidateLoader:
    """Verify and evaluate the self-contained v3 registry candidate."""

    def __init__(
        self,
        candidate_root: str | Path,
        *,
        binding: RegionResourceV3RegistryBinding = (
            REGION_RESOURCE_V3_REGISTRY_BINDING
        ),
        map_location: Any = "cpu",
    ) -> None:
        root = Path(candidate_root)
        if root.is_symlink() or root.name != binding.candidate_id:
            raise RegionResourceV3PairedInterventionError(
                "v3_candidate_directory_identity_mismatch"
            )
        try:
            manifest = load_region_resource_eight_region_candidate_manifest(
                root,
                expected_manifest_file_sha256=(
                    binding.candidate_manifest_file_sha256
                ),
            )
            review = review_region_resource_eight_region_candidate(root)
            loaded = load_region_resource_model_bundle(
                root / "bundle",
                expected_model_version=binding.policy_version,
                expected_state_dict_sha256=binding.model_state_sha256,
                map_location=map_location,
                require_training_dataset_manifest=True,
            )
        except (
            RegionResourceEightRegionCandidateError,
            ModelBundleValidationError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise RegionResourceV3PairedInterventionError(
                f"v3_candidate_registry_validation_failed:{type(exc).__name__}:{exc}"
            ) from exc
        self._validate_candidate_identity(binding, manifest, review, loaded)

        projection = REGION_RESOURCE_V3_PAIRED_THRESHOLDS.projection_config
        self.projector = DeterministicResourceProjector(projection)
        self.rule_policy = RuleRegionResourcePolicy(
            RuleRegionResourcePolicyConfig(
                projection=projection,
                high_threat_weight=_V3_RULE_HIGH_THREAT_WEIGHT,
                uncertainty_weight=_V3_RULE_UNCERTAINTY_WEIGHT,
                transfer_pressure_margin=_V3_RULE_TRANSFER_PRESSURE_MARGIN,
            ),
            projector=self.projector,
        )
        gate = loaded.manifest.runtime_confidence_gate
        if gate is None:
            raise RegionResourceV3PairedInterventionError(
                "v3_runtime_confidence_gate_unavailable"
            )
        try:
            gate.validate_runtime_context(
                projector=self.projector,
                rule_policy=self.rule_policy,
                minimum_confidence=(
                    REGION_RESOURCE_V3_PAIRED_THRESHOLDS.minimum_confidence
                ),
                ood_margin=REGION_RESOURCE_V3_PAIRED_THRESHOLDS.ood_margin,
            )
        except RuntimeConfidenceGateContextError as exc:
            raise RegionResourceV3PairedInterventionError(
                f"v3_runtime_gate_contract_mismatch:{exc}"
            ) from exc
        if gate.content_sha256 != binding.runtime_gate_content_sha256:
            raise RegionResourceV3PairedInterventionError(
                "v3_runtime_gate_content_identity_mismatch"
            )

        self.candidate_root = root
        self.binding = binding
        self.manifest = manifest
        self.loaded_bundle = loaded
        self.policy = LearnedRegionResourcePolicy(
            loaded.model, loaded.manifest
        )
        self._fingerprint = self._candidate_fingerprint()

    @staticmethod
    def _validate_candidate_identity(
        binding: RegionResourceV3RegistryBinding,
        manifest: RegionResourceEightRegionCandidateManifest,
        review: Mapping[str, Any],
        loaded: LoadedRegionResourceModelBundle,
    ) -> None:
        expected = {
            "candidate_id": binding.candidate_id,
            "schema": binding.candidate_schema,
            "content_sha256": binding.candidate_manifest_content_sha256,
            "bundle_manifest_sha256": binding.bundle_manifest_sha256,
            "model_state_sha256": binding.model_state_sha256,
            "model_version": binding.policy_version,
            "applicable_region_count": binding.applicable_region_count,
            "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
            "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
            "read_only_shadow": True,
            "runtime_preflight_completed": False,
            "formal_holdout_evaluated": False,
        }
        for name, required in expected.items():
            if getattr(manifest, name) != required:
                raise RegionResourceV3PairedInterventionError(
                    f"v3_candidate_manifest_identity_mismatch:{name}"
                )
        if (
            loaded.manifest.architecture != binding.policy_name
            or loaded.manifest.model_version != binding.policy_version
            or loaded.manifest.state_dict_sha256 != binding.model_state_sha256
            or loaded.manifest.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
            or loaded.manifest.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
            or loaded.manifest.assist_admitted
            or loaded.manifest.strategy_capability_claim_allowed
            or loaded.manifest.reward_evidence_available
            or loaded.manifest.final_holdout_seed_count != 0
        ):
            raise RegionResourceV3PairedInterventionError(
                "v3_candidate_bundle_permission_boundary_crossed"
            )
        permissions = review.get("permissions")
        if (
            not isinstance(permissions, Mapping)
            or any(
                bool(value)
                for name, value in permissions.items()
                if name != "schema"
            )
            or review.get("read_only_shadow_verified") is not True
            or review.get("runtime_preflight_completed") is not False
            or review.get("formal_evaluation_authorized") is not False
        ):
            raise RegionResourceV3PairedInterventionError(
                "v3_candidate_review_permission_boundary_crossed"
            )

    def evaluate(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceV3CandidateEvaluation:
        if snapshot.region_count != self.binding.applicable_region_count:
            raise RegionResourceV3PairedInterventionError(
                "v3_candidate_scope_region_count_mismatch"
            )
        before = self._candidate_fingerprint()
        if before != self._fingerprint:
            raise RegionResourceV3PairedInterventionError(
                "v3_candidate_changed_before_inference"
            )

        started_at = perf_counter()
        try:
            effective, gate_evaluation = (
                self.policy.recommend_with_runtime_confidence_gate(
                    snapshot,
                    projector=self.projector,
                    rule_policy=self.rule_policy,
                    formal_decision=formal_decision,
                    minimum_confidence=(
                        REGION_RESOURCE_V3_PAIRED_THRESHOLDS.minimum_confidence
                    ),
                    ood_margin=REGION_RESOURCE_V3_PAIRED_THRESHOLDS.ood_margin,
                )
            )
            ood_passed = not self.policy.is_ood(
                snapshot,
                margin=REGION_RESOURCE_V3_PAIRED_THRESHOLDS.ood_margin,
            )
        finally:
            latency_ms = 1000.0 * (perf_counter() - started_at)
            if self._candidate_fingerprint() != self._fingerprint:
                raise RegionResourceV3PairedInterventionError(
                    "v3_candidate_changed_during_inference"
                )
        if gate_evaluation is None:
            raise RegionResourceV3PairedInterventionError(
                "v3_runtime_gate_not_applied"
            )
        return self._build_evaluation(
            gate_evaluation,
            effective=effective,
            latency_ms=latency_ms,
            ood_passed=ood_passed,
        )

    def _build_evaluation(
        self,
        gate_evaluation: RegionResourceRuntimeConfidenceGateEvaluation,
        *,
        effective: RegionResourceRecommendation,
        latency_ms: float,
        ood_passed: bool,
    ) -> RegionResourceV3CandidateEvaluation:
        raw = gate_evaluation.raw_recommendation
        finite = _recommendation_is_finite(raw) and _recommendation_is_finite(
            effective
        )
        reasons: list[str] = []
        if not gate_evaluation.gate_applied:
            reasons.append("candidate_runtime_gate_not_applied")
        if not gate_evaluation.action_consistency.action_consistent:
            reasons.append("candidate_runtime_action_inconsistent")
        if gate_evaluation.effective_confidence < _V3_MINIMUM_CONFIDENCE:
            reasons.append(
                "candidate_runtime_effective_confidence_below_minimum"
            )
        if not ood_passed:
            reasons.append("candidate_ood_rejected")
        if not finite:
            reasons.append("candidate_output_nonfinite")
        if latency_ms > 1000.0 * REGION_RESOURCE_V3_INFERENCE_TIMEOUT_S:
            reasons.append("candidate_inference_timeout")
        return RegionResourceV3CandidateEvaluation(
            raw_recommendation=raw,
            candidate_manifest_file_sha256=(
                self.binding.candidate_manifest_file_sha256
            ),
            candidate_manifest_content_sha256=(
                self.binding.candidate_manifest_content_sha256
            ),
            bundle_manifest_sha256=self.binding.bundle_manifest_sha256,
            model_state_sha256=self.binding.model_state_sha256,
            candidate_latency_ms=latency_ms,
            candidate_scope_match=True,
            candidate_ood_passed=ood_passed,
            raw_output_finite=finite,
            runtime_gate_applied=gate_evaluation.gate_applied,
            runtime_gate_passed=not reasons,
            runtime_action_consistent=(
                gate_evaluation.action_consistency.action_consistent
            ),
            raw_confidence=gate_evaluation.raw_confidence,
            effective_confidence=gate_evaluation.effective_confidence,
            runtime_gate_content_sha256=(
                self.binding.runtime_gate_content_sha256
            ),
            runtime_gate_rejection_reasons=tuple(reasons),
        )

    def _candidate_fingerprint(self) -> tuple[tuple[str, str], ...]:
        relative_paths = (
            "eight_region_shadow_candidate_manifest.json",
            *sorted(self.manifest.artifact_files),
        )
        fingerprint: list[tuple[str, str]] = []
        for relative_path in relative_paths:
            relative = Path(relative_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise RegionResourceV3PairedInterventionError(
                    "v3_candidate_artifact_path_unsafe"
                )
            path = self.candidate_root / relative
            if path.is_symlink():
                raise RegionResourceV3PairedInterventionError(
                    f"v3_candidate_artifact_symlink_forbidden:{relative_path}"
                )
            fingerprint.append((relative_path, _sha256_file(path)))
        return tuple(fingerprint)


class RegionResourceV3IsolatedPairedAdvisor:
    """Main-facing isolated control/treatment evaluator for the frozen v3 model."""

    def __init__(
        self,
        specification: RegionResourceV3DevelopmentPairedSpecification,
        candidate_root: str | Path,
        *,
        map_location: Any = "cpu",
    ) -> None:
        self.specification = specification
        self.executor = RegionResourcePairedInterventionExecutor(specification)
        self.candidate_loader: RegionResourceV3IsolatedCandidateLoader | None = None
        self.load_rejection_reasons: tuple[str, ...] = ()
        try:
            self.candidate_loader = RegionResourceV3IsolatedCandidateLoader(
                candidate_root,
                binding=specification.candidate_registry,
                map_location=map_location,
            )
        except (
            RegionResourceV3PairedInterventionError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self.load_rejection_reasons = (
                _failure_reason("v3_isolated_candidate_load_failed", exc),
            )

    @property
    def candidate_loader_ready(self) -> bool:
        return self.candidate_loader is not None

    def advise_pair(
        self,
        *,
        seed: int,
        observed_input_binding: RegionResourcePairedInputBinding,
        snapshot: RegionResourceSnapshot,
        evaluated_at_s: float,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceV3IsolatedPairedDecision:
        """Evaluate both arms on one immutable input without production ACKs."""

        control_evidence = self.executor.execute_arm(
            arm=RegionResourcePairedArm.CONTROL,
            seed=seed,
            observed_input_binding=observed_input_binding,
            snapshot=snapshot,
            evaluated_at_s=evaluated_at_s,
            formal_decision=formal_decision,
        )
        control = self._materialize_arm_decision(
            evidence=control_evidence,
            snapshot=snapshot,
            formal_decision=formal_decision,
            candidate_evaluation=None,
        )

        candidate_evaluation: RegionResourceV3CandidateEvaluation | None = None
        rejections = list(self.load_rejection_reasons)
        scope_compatible = bool(
            snapshot.region_count
            == self.specification.candidate_registry.applicable_region_count
        )
        if not scope_compatible:
            rejections.append("v3_candidate_scope_region_count_mismatch")
        elif self.candidate_loader is not None:
            try:
                candidate_evaluation = self.candidate_loader.evaluate(
                    snapshot,
                    formal_decision=formal_decision,
                )
            except (
                RegionResourceV3PairedInterventionError,
                ModelBundleValidationError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                rejections.append(
                    _failure_reason("v3_isolated_candidate_inference_failed", exc)
                )
        if candidate_evaluation is not None:
            rejections.extend(
                candidate_evaluation.runtime_gate_rejection_reasons
            )

        treatment_evidence = self.executor.execute_arm(
            arm=RegionResourcePairedArm.TREATMENT,
            seed=seed,
            observed_input_binding=observed_input_binding,
            snapshot=snapshot,
            evaluated_at_s=evaluated_at_s,
            candidate_recommendation=(
                candidate_evaluation.raw_recommendation
                if candidate_evaluation is not None
                else None
            ),
            candidate_bundle_manifest_sha256=(
                candidate_evaluation.bundle_manifest_sha256
                if candidate_evaluation is not None
                else None
            ),
            candidate_latency_ms=(
                candidate_evaluation.candidate_latency_ms
                if candidate_evaluation is not None
                else 0.0
            ),
            candidate_ood_passed=(
                candidate_evaluation.candidate_ood_passed
                if candidate_evaluation is not None
                else False
            ),
            candidate_failure_reasons=tuple(rejections),
            formal_decision=formal_decision,
        )
        treatment = self._materialize_arm_decision(
            evidence=treatment_evidence,
            snapshot=snapshot,
            formal_decision=formal_decision,
            candidate_evaluation=candidate_evaluation,
            candidate_scope_compatible=scope_compatible,
        )
        return RegionResourceV3IsolatedPairedDecision(
            specification_id=self.specification.specification_id,
            specification_sha256=self.specification.sha256,
            candidate_identity_sha256=(
                self.specification.candidate_registry.sha256
            ),
            seed=int(seed),
            observed_input_sha256=observed_input_binding.sha256,
            snapshot_payload_sha256=canonical_runtime_payload_sha256(
                snapshot.to_dict()
            ),
            control=control,
            treatment=treatment,
            candidate_evaluation=candidate_evaluation,
            load_or_inference_rejection_reasons=tuple(rejections),
        )

    def _materialize_arm_decision(
        self,
        *,
        evidence: RegionResourcePairedArmEvidence,
        snapshot: RegionResourceSnapshot,
        formal_decision: RegionalFailoverDecision | None,
        candidate_evaluation: RegionResourceV3CandidateEvaluation | None,
        candidate_scope_compatible: bool = True,
    ) -> RegionResourceV3IsolatedArmDecision:
        if evidence.arm == RegionResourcePairedArm.CONTROL:
            selected = self.executor.rule_policy.recommend(
                snapshot,
                formal_decision=formal_decision,
            )
        elif (
            candidate_evaluation is not None
            and evidence.candidate_safety_projection_passed
            and not evidence.rule_fallback_used
        ):
            selected = self.executor.projector.project(
                snapshot,
                candidate_evaluation.raw_recommendation,
                formal_decision=formal_decision,
            )
        else:
            selected = self.executor.rule_policy.recommend(
                snapshot,
                formal_decision=formal_decision,
                fallback_reason="paired_treatment_candidate_rejected",
            )
        advisory = self.executor.projector.build_advisory_contract(
            snapshot,
            selected,
            formal_decision=formal_decision,
        )
        treatment = evidence.arm == RegionResourcePairedArm.TREATMENT
        return RegionResourceV3IsolatedArmDecision(
            arm=evidence.arm,
            arm_id=evidence.arm_id,
            specification_id=self.specification.specification_id,
            specification_sha256=self.specification.sha256,
            candidate_identity_sha256=(
                self.specification.candidate_registry.sha256
            ),
            candidate_scope_compatible=(
                candidate_scope_compatible if treatment else True
            ),
            selected_recommendation=selected,
            advisory_contract=advisory,
            arm_evidence=evidence,
            raw_inference_completed=(
                treatment and candidate_evaluation is not None
            ),
            runtime_gate_applied=bool(
                treatment
                and candidate_evaluation is not None
                and candidate_evaluation.runtime_gate_applied
            ),
            runtime_gate_passed=bool(
                treatment
                and candidate_evaluation is not None
                and candidate_evaluation.runtime_gate_passed
            ),
            projection_passed=evidence.candidate_safety_projection_passed,
            next_cycle_isolated_adoption=(
                evidence.isolated_treatment_safe_adopted
            ),
            isolated_treatment_influence_allowed=treatment,
            isolated_treatment_influence_adopted=(
                evidence.isolated_treatment_safe_adopted
            ),
            deterministic_rule_selected=(
                selected.source == RecommendationSource.RULE
            ),
        )


def build_region_resource_v3_development_paired_specification(
    *,
    experiment_id: str,
    experiment_version: str,
    input_bindings: Sequence[RegionResourcePairedInputBinding],
    candidate_root: str | Path,
) -> RegionResourceV3DevelopmentPairedSpecification:
    """Build the exact v3 development pairing without touching formal seeds."""

    loader = RegionResourceV3IsolatedCandidateLoader(candidate_root)
    by_seed: dict[int, RegionResourcePairedInputBinding] = {}
    for binding in input_bindings:
        seed = int(binding.seed)
        if seed in by_seed:
            raise ValueError("v3 input bindings contain a duplicate seed")
        by_seed[seed] = binding
    if tuple(sorted(by_seed)) != REGION_RESOURCE_V3_DEVELOPMENT_SEEDS:
        raise ValueError(
            "v3 development inputs must cover exactly seeds 2003-2012"
        )
    split = loader.manifest.split_usage
    candidate_data_seeds = set(
        split.train_seeds
        + split.validation_seeds
        + split.untouched_test_seeds
        + split.reserved_evaluation_seeds
    )
    if set(by_seed) & candidate_data_seeds:
        raise ValueError(
            "v3 development pairing overlaps candidate or formal seed inventory"
        )
    bundle = loader.binding.paired_bundle
    arms: list[RegionResourcePairedArmSpecification] = []
    for seed in REGION_RESOURCE_V3_DEVELOPMENT_SEEDS:
        binding = by_seed[seed]
        arms.extend(
            (
                RegionResourcePairedArmSpecification(
                    arm=RegionResourcePairedArm.CONTROL,
                    input_binding=binding,
                    policy_name=REGION_RESOURCE_RULE_POLICY_NAME,
                    policy_version=REGION_RESOURCE_RULE_POLICY_VERSION,
                    candidate_influence_allowed=False,
                ),
                RegionResourcePairedArmSpecification(
                    arm=RegionResourcePairedArm.TREATMENT,
                    input_binding=binding,
                    policy_name=bundle.policy_name,
                    policy_version=bundle.policy_version,
                    candidate_influence_allowed=True,
                ),
            )
        )
    return RegionResourceV3DevelopmentPairedSpecification(
        experiment_id=experiment_id,
        experiment_version=experiment_version,
        candidate_registry=loader.binding,
        candidate_bundle=bundle,
        thresholds=REGION_RESOURCE_V3_PAIRED_THRESHOLDS,
        safety_shell=RegionResourcePairedSafetyShellBinding(),
        arms=tuple(arms),
    )


def _recommendation_is_finite(
    recommendation: RegionResourceRecommendation,
) -> bool:
    try:
        values = (
            float(recommendation.created_at_s),
            float(recommendation.confidence),
            *(
                value
                for action in recommendation.actions
                for value in (
                    float(action.resource_quota_delta),
                    float(action.reserve_ratio),
                    float(action.reconnaissance_priority),
                    float(action.expected_lease_expires_at_s),
                )
            ),
            *(
                value
                for transfer in recommendation.transfers
                for value in (
                    float(transfer.resource_count),
                    float(transfer.expected_transfer_time_s),
                )
            ),
        )
        return all(isfinite(value) for value in values)
    except (TypeError, ValueError):
        return False


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    serialized = json.dumps(
        to_jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def _failure_reason(prefix: str, exc: Exception) -> str:
    detail = "_".join((str(exc).strip() or type(exc).__name__).split())
    return f"{prefix}:{detail}"


def _require_exact_keys(
    value: Mapping[str, Any], expected: Mapping[str, Any], path: str
) -> None:
    actual_keys = set(value)
    expected_keys = set(expected)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise ValueError(
            f"{path} keys mismatch: missing={missing}, extra={extra}"
        )


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{path} must be an array")
    return value


def _unique(values: Sequence[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))
