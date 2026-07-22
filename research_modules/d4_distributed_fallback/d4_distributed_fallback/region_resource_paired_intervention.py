"""Fail-closed paired-intervention contracts for D4 regional advice.

The contract in this module is deliberately narrower than online D4
authority.  It freezes identical held-out inputs for a deterministic rule arm
and an isolated candidate arm, then proves only whether an advisory was safe
to feed into the next cycle of that isolated simulation arm.  It does not
create a runtime acknowledgement, reward, counterfactual, or causal label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

from .models import to_jsonable
from .region_resource import (
    DETERMINISTIC_RESOURCE_PROJECTOR_NAME,
    DETERMINISTIC_RESOURCE_PROJECTOR_VERSION,
    REGION_RESOURCE_SHADOW_REPORT_SCHEMA,
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceProjectionConfig,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
    ShadowPairedEvaluator,
)
from .region_resource_reward_evidence import (
    REGION_RESOURCE_REWARD_DEFINITION_VERSION,
    REGION_RESOURCE_REWARD_EVIDENCE_SCHEMA,
)
from .region_resource_runtime_ack import (
    REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA,
    canonical_runtime_payload_sha256,
)
from .region_resource_learning import (
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    REGION_GRAPH_ARCHITECTURE,
    LearnedRegionResourcePolicy,
    LoadedRegionResourceModelBundle,
    ModelBundleValidationError,
    load_region_resource_model_bundle,
)
from .regional_failover import REGIONAL_FAILOVER_SCHEMA, RegionalFailoverDecision


REGION_RESOURCE_PAIRED_SPEC_SCHEMA = "d4-region-resource-paired-intervention-spec-v1"
REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA = (
    "d4-region-resource-paired-arm-evidence-v1"
)
REGION_RESOURCE_PAIRED_MANIFEST_SCHEMA = (
    "d4-region-resource-paired-intervention-manifest-v1"
)
REGION_RESOURCE_PAIRED_SAFETY_SHELL_VERSION = (
    "d4-region-resource-paired-safety-shell-v1"
)
REGION_RESOURCE_COALITION_FENCE_VERSION = "d4-coalition-lease-epoch-ack-fence-v1"
REGION_RESOURCE_RULE_POLICY_NAME = "d4-region-resource-rule"
REGION_RESOURCE_RULE_POLICY_VERSION = "v1"
REGION_RESOURCE_RESERVED_EVALUATION_SEEDS = tuple(range(1000, 1020))
REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_ID = "region_resource_bc_900_20260720"
REGION_RESOURCE_FROZEN_DEVELOPMENT_MODEL_VERSION = (
    "d4-region-bc-900-development-v1"
)
REGION_RESOURCE_FROZEN_DEVELOPMENT_MANIFEST_SHA256 = (
    "dad2adbe9c36dd9ff8ee8bb3c11b1e07e66743c6f80dd8e956799208a10c05c9"
)
REGION_RESOURCE_FROZEN_DEVELOPMENT_STATE_DICT_SHA256 = (
    "3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62"
)
REGION_RESOURCE_FROZEN_DEVELOPMENT_TRAINING_MANIFEST_SHA256 = (
    "ff3081c8e320d9c8e1b032fb6234cd24159f0feedb1c6a706633cea6c1030dc6"
)
REGION_RESOURCE_FROZEN_DEVELOPMENT_DATASET_SHA256 = (
    "b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158"
)
REGION_RESOURCE_FROZEN_DEVELOPMENT_SPLIT_SHA256 = (
    "18a2c60097fefe05cb70ed811d28faf90c51bbbba0bbe984e07f23fb12f8d7f0"
)

_SHA256_HEX_LENGTH = 64
_ALLOWED_PROJECTION_NOTES = (":clipped_by_safety_projection",)
_FORBIDDEN_KEY_TOKENS = (
    "truth",
    "actor_id",
    "object_id",
    "global_track_id",
    "target_id",
    "evaluator_id",
)


class RegionResourcePairedArm(str, Enum):
    CONTROL = "control_rule"
    TREATMENT = "treatment_candidate"


@dataclass(frozen=True)
class RegionResourcePairedThresholds:
    """Frozen candidate and deterministic projection thresholds."""

    inference_timeout_s: float = 0.050
    minimum_confidence: float = 0.60
    ood_margin: float = 0.05
    minimum_reserve_ratio: float = 0.10
    minimum_reserve_resources: int = 1
    advisory_ttl_s: float = 1.0

    def __post_init__(self) -> None:
        for name in ("inference_timeout_s", "ood_margin", "advisory_ttl_s"):
            value = float(getattr(self, name))
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.advisory_ttl_s <= 0.0:
            raise ValueError("advisory_ttl_s must be positive")
        for name in ("minimum_confidence", "minimum_reserve_ratio"):
            value = float(getattr(self, name))
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if int(self.minimum_reserve_resources) < 0:
            raise ValueError("minimum_reserve_resources must be non-negative")

    @property
    def projection_config(self) -> RegionResourceProjectionConfig:
        return RegionResourceProjectionConfig(
            minimum_reserve_ratio=float(self.minimum_reserve_ratio),
            minimum_reserve_resources=int(self.minimum_reserve_resources),
            advisory_ttl_s=float(self.advisory_ttl_s),
        )

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourcePairedThresholds":
        _reject_truth_keys(value)
        _require_exact_keys(value, cls.__dataclass_fields__, "thresholds")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceCandidateBundleBinding:
    """Immutable identity of the candidate evaluated in the treatment arm."""

    bundle_id: str
    bundle_version: str
    bundle_manifest_sha256: str
    model_state_sha256: str
    policy_name: str
    policy_version: str

    def __post_init__(self) -> None:
        for name in ("bundle_id", "bundle_version", "policy_name", "policy_version"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        _require_sha256(self.bundle_manifest_sha256, "bundle_manifest_sha256")
        _require_sha256(self.model_state_sha256, "model_state_sha256")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceCandidateBundleBinding":
        _reject_truth_keys(value)
        _require_exact_keys(value, cls.__dataclass_fields__, "candidate_bundle")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourcePairedInputBinding:
    """Truth-free input identity repeated in both arms of one seed pair."""

    seed: int
    scenario_id: str
    scenario_version: str
    scenario_config_sha256: str
    initial_state_sha256: str
    communication_schedule_sha256: str
    fault_schedule_sha256: str
    region_snapshot_lineage_sha256: str

    def __post_init__(self) -> None:
        if not self.scenario_id or not self.scenario_version:
            raise ValueError("scenario identity must not be empty")
        if int(self.seed) < 0:
            raise ValueError("seed must be non-negative")
        for name in (
            "scenario_config_sha256",
            "initial_state_sha256",
            "communication_schedule_sha256",
            "fault_schedule_sha256",
            "region_snapshot_lineage_sha256",
        ):
            _require_sha256(str(getattr(self, name)), name)

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourcePairedInputBinding":
        _reject_truth_keys(value)
        _require_exact_keys(value, cls.__dataclass_fields__, "input_binding")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourcePairedSafetyShellBinding:
    """Version lock for the deterministic fences shared by both arms."""

    safety_shell_version: str = REGION_RESOURCE_PAIRED_SAFETY_SHELL_VERSION
    projector_name: str = DETERMINISTIC_RESOURCE_PROJECTOR_NAME
    projector_version: str = DETERMINISTIC_RESOURCE_PROJECTOR_VERSION
    regional_authority_schema: str = REGIONAL_FAILOVER_SCHEMA
    coalition_fence_version: str = REGION_RESOURCE_COALITION_FENCE_VERSION
    runtime_ack_evidence_schema: str = REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA
    reward_evidence_schema: str = REGION_RESOURCE_REWARD_EVIDENCE_SCHEMA
    reward_definition_version: str = REGION_RESOURCE_REWARD_DEFINITION_VERSION
    paired_evaluator_schema: str = REGION_RESOURCE_SHADOW_REPORT_SCHEMA

    def __post_init__(self) -> None:
        expected = {
            "safety_shell_version": REGION_RESOURCE_PAIRED_SAFETY_SHELL_VERSION,
            "projector_name": DETERMINISTIC_RESOURCE_PROJECTOR_NAME,
            "projector_version": DETERMINISTIC_RESOURCE_PROJECTOR_VERSION,
            "regional_authority_schema": REGIONAL_FAILOVER_SCHEMA,
            "coalition_fence_version": REGION_RESOURCE_COALITION_FENCE_VERSION,
            "runtime_ack_evidence_schema": REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA,
            "reward_evidence_schema": REGION_RESOURCE_REWARD_EVIDENCE_SCHEMA,
            "reward_definition_version": REGION_RESOURCE_REWARD_DEFINITION_VERSION,
            "paired_evaluator_schema": REGION_RESOURCE_SHADOW_REPORT_SCHEMA,
        }
        for name, required in expected.items():
            if getattr(self, name) != required:
                raise ValueError(f"unsupported paired safety binding: {name}")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourcePairedSafetyShellBinding":
        _reject_truth_keys(value)
        _require_exact_keys(value, cls.__dataclass_fields__, "safety_shell")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourcePairedArmSpecification:
    arm: RegionResourcePairedArm | str
    input_binding: RegionResourcePairedInputBinding
    policy_name: str
    policy_version: str
    candidate_influence_allowed: bool
    isolated_offline_only: bool = True
    arm_id: str = ""

    def __post_init__(self) -> None:
        arm = self.arm if isinstance(self.arm, RegionResourcePairedArm) else RegionResourcePairedArm(str(self.arm))
        object.__setattr__(self, "arm", arm)
        if not self.policy_name or not self.policy_version:
            raise ValueError("arm policy identity must not be empty")
        if self.isolated_offline_only is not True:
            raise ValueError("paired intervention arms must remain offline and isolated")
        expected_influence = arm == RegionResourcePairedArm.TREATMENT
        if self.candidate_influence_allowed is not expected_influence:
            raise ValueError("candidate influence must be limited to the treatment arm")
        if arm == RegionResourcePairedArm.CONTROL and (
            self.policy_name != REGION_RESOURCE_RULE_POLICY_NAME
            or self.policy_version != REGION_RESOURCE_RULE_POLICY_VERSION
        ):
            raise ValueError("control arm must execute the deterministic region rule")
        expected_id = _content_id("d4-rr-paired-arm", self, excluded=("arm_id",))
        if self.arm_id and self.arm_id != expected_id:
            raise ValueError("arm_id does not match paired arm content")
        object.__setattr__(self, "arm_id", expected_id)

    @property
    def group(self) -> tuple[str, int]:
        return (self.input_binding.scenario_id, int(self.input_binding.seed))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourcePairedArmSpecification":
        _reject_truth_keys(value)
        _require_exact_keys(value, cls.__dataclass_fields__, "arm_specification")
        payload = dict(value)
        payload["input_binding"] = RegionResourcePairedInputBinding.from_dict(
            _mapping(payload["input_binding"], "arm_specification.input_binding")
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourcePairedInterventionSpecification:
    experiment_id: str
    experiment_version: str
    candidate_bundle: RegionResourceCandidateBundleBinding
    thresholds: RegionResourcePairedThresholds
    safety_shell: RegionResourcePairedSafetyShellBinding
    arms: tuple[RegionResourcePairedArmSpecification, ...]
    reserved_seeds: tuple[int, ...] = REGION_RESOURCE_RESERVED_EVALUATION_SEEDS
    ppo_enabled: bool = False
    assist_enabled: bool = False
    authority_enabled: bool = False
    rule_fallback_enabled: bool = True
    specification_id: str = ""
    schema: str = REGION_RESOURCE_PAIRED_SPEC_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_PAIRED_SPEC_SCHEMA:
            raise ValueError("unsupported paired intervention specification schema")
        if not self.experiment_id or not self.experiment_version:
            raise ValueError("paired experiment identity must not be empty")
        seeds = tuple(int(seed) for seed in self.reserved_seeds)
        if seeds != REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
            raise ValueError("paired intervention seeds must be exactly 1000-1019")
        object.__setattr__(self, "reserved_seeds", seeds)
        if any((self.ppo_enabled, self.assist_enabled, self.authority_enabled)):
            raise ValueError("PPO, assist, and online authority must remain disabled")
        if self.rule_fallback_enabled is not True:
            raise ValueError("deterministic rule fallback must remain enabled")

        arms = tuple(self.arms)
        if len(arms) != 2 * len(seeds):
            raise ValueError("paired intervention requires exactly two arms per seed")
        by_seed: dict[int, dict[RegionResourcePairedArm, RegionResourcePairedArmSpecification]] = {}
        for arm in arms:
            seed = int(arm.input_binding.seed)
            if seed not in seeds:
                raise ValueError("paired arm contains a non-reserved seed")
            bucket = by_seed.setdefault(seed, {})
            if arm.arm in bucket:
                raise ValueError("paired intervention contains a duplicate seed arm")
            bucket[arm.arm] = arm
        if set(by_seed) != set(seeds):
            raise ValueError("paired intervention is missing one or more reserved seeds")
        for seed in seeds:
            pair = by_seed[seed]
            if set(pair) != set(RegionResourcePairedArm):
                raise ValueError("each seed requires one control and one treatment arm")
            control = pair[RegionResourcePairedArm.CONTROL]
            treatment = pair[RegionResourcePairedArm.TREATMENT]
            if control.input_binding.to_dict() != treatment.input_binding.to_dict():
                raise ValueError("paired arms must bind identical scenario inputs and schedules")
            if (
                treatment.policy_name != self.candidate_bundle.policy_name
                or treatment.policy_version != self.candidate_bundle.policy_version
            ):
                raise ValueError("treatment arm policy does not match the candidate bundle")
        if len({arm.arm_id for arm in arms}) != len(arms):
            raise ValueError("paired arm identifiers must be unique")
        ordered = tuple(
            sorted(arms, key=lambda item: (item.input_binding.seed, item.arm.value))
        )
        object.__setattr__(self, "arms", ordered)
        expected_id = _content_id(
            "d4-rr-paired-spec", self, excluded=("specification_id",)
        )
        if self.specification_id and self.specification_id != expected_id:
            raise ValueError("specification_id does not match specification content")
        object.__setattr__(self, "specification_id", expected_id)

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def arm_for(
        self, seed: int, arm: RegionResourcePairedArm | str
    ) -> RegionResourcePairedArmSpecification:
        normalized = arm if isinstance(arm, RegionResourcePairedArm) else RegionResourcePairedArm(str(arm))
        for item in self.arms:
            if item.input_binding.seed == int(seed) and item.arm == normalized:
                return item
        raise KeyError(f"paired arm not found: seed={seed}, arm={normalized.value}")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourcePairedInterventionSpecification":
        _reject_truth_keys(value)
        _require_exact_keys(value, cls.__dataclass_fields__, "specification")
        payload = dict(value)
        payload["candidate_bundle"] = RegionResourceCandidateBundleBinding.from_dict(
            _mapping(payload["candidate_bundle"], "specification.candidate_bundle")
        )
        payload["thresholds"] = RegionResourcePairedThresholds.from_dict(
            _mapping(payload["thresholds"], "specification.thresholds")
        )
        payload["safety_shell"] = RegionResourcePairedSafetyShellBinding.from_dict(
            _mapping(payload["safety_shell"], "specification.safety_shell")
        )
        payload["arms"] = tuple(
            RegionResourcePairedArmSpecification.from_dict(
                _mapping(item, f"specification.arms[{index}]")
            )
            for index, item in enumerate(
                _sequence(payload["arms"], "specification.arms")
            )
        )
        payload["reserved_seeds"] = tuple(
            int(seed)
            for seed in _sequence(
                payload["reserved_seeds"], "specification.reserved_seeds"
            )
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourcePairedArmEvidence:
    """Execution-boundary evidence for one isolated arm.

    ``isolated_treatment_safe_adopted`` proves only that the candidate passed
    D4 projection and next-cycle consumption checks inside the treatment arm.
    It is never an online runtime ACK.
    """

    arm_id: str
    arm: RegionResourcePairedArm | str
    seed: int
    specification_sha256: str
    expected_input_sha256: str
    observed_input_sha256: str
    snapshot_payload_sha256: str
    evaluated_at_s: float
    candidate_latency_ms: float
    pair_input_match: bool
    candidate_considered: bool
    candidate_bundle_match: bool
    candidate_thresholds_passed: bool
    candidate_safety_projection_passed: bool
    deterministic_rule_executed: bool
    rule_fallback_used: bool
    next_cycle_consumption_passed: bool
    isolated_arm_safe_adopted: bool
    isolated_treatment_safe_adopted: bool
    candidate_recommendation_sha256: str | None = None
    executed_recommendation_sha256: str | None = None
    advisory_id: str | None = None
    advisory_payload_sha256: str | None = None
    projection_notes: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    runtime_advisory_applied_ack_available: bool = False
    post_projection_recommendation_is_applied_ack: bool = False
    observed_outcome_available: bool = False
    paired_non_degradation_available: bool = False
    counterfactual_available: bool = False
    causal_effect_available: bool = False
    ppo_enabled: bool = False
    assist_enabled: bool = False
    online_authority: bool = False
    rule_fallback_enabled: bool = True
    schema: str = REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA:
            raise ValueError("unsupported paired arm evidence schema")
        arm = self.arm if isinstance(self.arm, RegionResourcePairedArm) else RegionResourcePairedArm(str(self.arm))
        object.__setattr__(self, "arm", arm)
        if not self.arm_id or int(self.seed) not in REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
            raise ValueError("paired arm evidence identity or seed is invalid")
        for name in (
            "specification_sha256",
            "expected_input_sha256",
            "observed_input_sha256",
            "snapshot_payload_sha256",
        ):
            _require_sha256(str(getattr(self, name)), name)
        for name in (
            "candidate_recommendation_sha256",
            "executed_recommendation_sha256",
            "advisory_payload_sha256",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_sha256(str(value), name)
        for name in ("evaluated_at_s", "candidate_latency_ms"):
            value = float(getattr(self, name))
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.pair_input_match != (
            self.expected_input_sha256 == self.observed_input_sha256
        ):
            raise ValueError("pair_input_match contradicts the input digests")
        if arm == RegionResourcePairedArm.CONTROL:
            if self.candidate_considered or self.rule_fallback_used:
                raise ValueError("control evidence cannot consider or fall back from a candidate")
            if not self.deterministic_rule_executed:
                raise ValueError("control evidence must execute the deterministic rule")
        if self.isolated_treatment_safe_adopted:
            if arm != RegionResourcePairedArm.TREATMENT:
                raise ValueError("only treatment evidence can adopt a candidate")
            if not all(
                (
                    self.pair_input_match,
                    self.candidate_considered,
                    self.candidate_bundle_match,
                    self.candidate_thresholds_passed,
                    self.candidate_safety_projection_passed,
                    self.next_cycle_consumption_passed,
                    self.isolated_arm_safe_adopted,
                )
            ):
                raise ValueError("treatment adoption lacks required safety evidence")
            if self.rule_fallback_used or self.deterministic_rule_executed:
                raise ValueError("adopted treatment cannot be a rule fallback")
        if self.isolated_arm_safe_adopted and not self.next_cycle_consumption_passed:
            raise ValueError("isolated arm adoption requires next-cycle consumption")
        if self.rule_fallback_used and (
            arm != RegionResourcePairedArm.TREATMENT
            or not self.deterministic_rule_executed
            or self.isolated_treatment_safe_adopted
        ):
            raise ValueError("rule fallback evidence is internally inconsistent")
        if any(
            (
                self.runtime_advisory_applied_ack_available,
                self.post_projection_recommendation_is_applied_ack,
                self.observed_outcome_available,
                self.paired_non_degradation_available,
                self.counterfactual_available,
                self.causal_effect_available,
                self.ppo_enabled,
                self.assist_enabled,
                self.online_authority,
            )
        ):
            raise ValueError("paired arm evidence cannot grant outcome or online authority")
        if self.rule_fallback_enabled is not True:
            raise ValueError("paired arm evidence must retain deterministic fallback")
        if self.isolated_arm_safe_adopted and (
            self.executed_recommendation_sha256 is None
            or self.advisory_id is None
            or self.advisory_payload_sha256 is None
        ):
            raise ValueError("adopted arm evidence requires recommendation and advisory hashes")
        object.__setattr__(self, "projection_notes", _unique(self.projection_notes))
        object.__setattr__(self, "rejection_reasons", _unique(self.rejection_reasons))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourcePairedArmEvidence":
        _reject_truth_keys(value)
        _require_exact_keys(value, cls.__dataclass_fields__, "arm_evidence")
        payload = dict(value)
        payload["projection_notes"] = tuple(payload.get("projection_notes", ()))
        payload["rejection_reasons"] = tuple(payload.get("rejection_reasons", ()))
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourcePairedInterventionManifest:
    """Self-contained paired-arm inventory without performance claims."""

    specification: RegionResourcePairedInterventionSpecification
    arm_evidence: tuple[RegionResourcePairedArmEvidence, ...]
    created_at_utc: str
    d6_outcome_sidecar_attached: bool = False
    observed_outcome_available: bool = False
    paired_non_degradation_available: bool = False
    counterfactual_available: bool = False
    causal_effect_available: bool = False
    formal_twenty_seed_performance_completed: bool = False
    performance_claim_allowed: bool = False
    manifest_id: str = ""
    schema: str = REGION_RESOURCE_PAIRED_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_PAIRED_MANIFEST_SCHEMA:
            raise ValueError("unsupported paired intervention manifest schema")
        if not str(self.created_at_utc).strip():
            raise ValueError("paired manifest creation time must not be empty")
        if any(
            (
                self.d6_outcome_sidecar_attached,
                self.observed_outcome_available,
                self.paired_non_degradation_available,
                self.counterfactual_available,
                self.causal_effect_available,
                self.formal_twenty_seed_performance_completed,
                self.performance_claim_allowed,
            )
        ):
            raise ValueError("D4 paired manifest cannot claim unavailable D6 outcomes")
        records = tuple(self.arm_evidence)
        expected = {(arm.input_binding.seed, arm.arm): arm for arm in self.specification.arms}
        actual: dict[tuple[int, RegionResourcePairedArm], RegionResourcePairedArmEvidence] = {}
        for record in records:
            key = (int(record.seed), record.arm)
            if key in actual:
                raise ValueError("paired manifest contains duplicate arm evidence")
            actual[key] = record
        if set(actual) != set(expected):
            raise ValueError("paired manifest requires all 40 reserved-seed arm records")
        for key, arm_spec in expected.items():
            record = actual[key]
            if record.arm_id != arm_spec.arm_id:
                raise ValueError("paired manifest arm identity mismatch")
            if record.specification_sha256 != self.specification.sha256:
                raise ValueError("paired manifest specification hash mismatch")
            if record.expected_input_sha256 != arm_spec.input_binding.sha256:
                raise ValueError("paired manifest expected input hash mismatch")
            if not record.pair_input_match:
                raise ValueError("paired manifest contains an observed input mismatch")
        for seed in self.specification.reserved_seeds:
            control = actual[(seed, RegionResourcePairedArm.CONTROL)]
            treatment = actual[(seed, RegionResourcePairedArm.TREATMENT)]
            if control.observed_input_sha256 != treatment.observed_input_sha256:
                raise ValueError("paired arm observed input hashes differ")
            if control.snapshot_payload_sha256 != treatment.snapshot_payload_sha256:
                raise ValueError("paired arm snapshot payload hashes differ")
        ordered = tuple(sorted(records, key=lambda item: (item.seed, item.arm.value)))
        object.__setattr__(self, "arm_evidence", ordered)
        expected_id = _content_id(
            "d4-rr-paired-manifest", self, excluded=("manifest_id",)
        )
        if self.manifest_id and self.manifest_id != expected_id:
            raise ValueError("manifest_id does not match manifest content")
        object.__setattr__(self, "manifest_id", expected_id)

    @property
    def treatment_safe_adoption_count(self) -> int:
        return sum(item.isolated_treatment_safe_adopted for item in self.arm_evidence)

    @property
    def failed_arm_count(self) -> int:
        return sum(not item.isolated_arm_safe_adopted for item in self.arm_evidence)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourcePairedInterventionManifest":
        _reject_truth_keys(value)
        _require_exact_keys(value, cls.__dataclass_fields__, "manifest")
        payload = dict(value)
        payload["specification"] = RegionResourcePairedInterventionSpecification.from_dict(
            _mapping(payload["specification"], "manifest.specification")
        )
        payload["arm_evidence"] = tuple(
            RegionResourcePairedArmEvidence.from_dict(
                _mapping(item, f"manifest.arm_evidence[{index}]")
            )
            for index, item in enumerate(
                _sequence(payload["arm_evidence"], "manifest.arm_evidence")
            )
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceIsolatedCandidateEvaluation:
    """Raw candidate and immutable bundle evidence from isolated inference."""

    recommendation: RegionResourceRecommendation
    bundle_manifest_sha256: str
    candidate_latency_ms: float
    candidate_ood_passed: bool

    def __post_init__(self) -> None:
        _require_sha256(self.bundle_manifest_sha256, "bundle_manifest_sha256")
        if not isfinite(float(self.candidate_latency_ms)) or self.candidate_latency_ms < 0.0:
            raise ValueError("candidate_latency_ms must be finite and non-negative")
        if self.recommendation.source != RecommendationSource.LEARNED:
            raise ValueError("isolated candidate must be a raw learned recommendation")
        if self.recommendation.projected:
            raise ValueError("isolated candidate loader must not project recommendations")


class RegionResourceIsolatedPairedCandidateLoader:
    """Read and evaluate a frozen candidate bundle without advisor authority.

    The caller must provide the out-of-band bundle identity frozen in the
    paired specification.  This loader never constructs ``RegionResourceAdvisor``
    and never requests assist or online authority.  It reads the model in eval
    mode, verifies all bundle hashes supported by the model-bundle contract,
    and checks that those files did not change during each inference.
    """

    def __init__(
        self,
        candidate_bundle: RegionResourceCandidateBundleBinding,
        bundle_dir: str | Path,
        *,
        map_location: Any = "cpu",
    ) -> None:
        source = Path(bundle_dir)
        if source.is_symlink():
            raise ModelBundleValidationError("paired_bundle_directory_symlink_forbidden")
        if candidate_bundle != REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_BINDING:
            raise ModelBundleValidationError(
                "paired_bundle_not_frozen_development_bundle"
            )
        if (
            source.name != "bundle"
            or source.parent.name != REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_ID
        ):
            raise ModelBundleValidationError("paired_bundle_id_mismatch")

        manifest_path = source / "manifest.json"
        actual_manifest_sha256 = _sha256_file(manifest_path)
        if actual_manifest_sha256 != candidate_bundle.bundle_manifest_sha256:
            raise ModelBundleValidationError("paired_bundle_manifest_sha256_mismatch")

        loaded = load_region_resource_model_bundle(
            source,
            expected_model_version=candidate_bundle.policy_version,
            expected_state_dict_sha256=candidate_bundle.model_state_sha256,
            map_location=map_location,
            require_training_dataset_manifest=True,
        )
        loaded_manifest_payload = loaded.manifest.to_dict()
        try:
            current_manifest_payload = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ModelBundleValidationError(
                "paired_bundle_manifest_unreadable_after_load"
            ) from exc
        if loaded_manifest_payload != current_manifest_payload:
            raise ModelBundleValidationError(
                "paired_bundle_manifest_changed_during_load"
            )
        if loaded.manifest.model_version != candidate_bundle.bundle_version:
            raise ModelBundleValidationError("paired_bundle_version_mismatch")
        if candidate_bundle.policy_name != REGION_GRAPH_ARCHITECTURE:
            raise ModelBundleValidationError("paired_bundle_policy_name_mismatch")
        if candidate_bundle.policy_version != loaded.manifest.model_version:
            raise ModelBundleValidationError("paired_bundle_policy_version_mismatch")
        _validate_frozen_development_manifest(loaded)

        self.bundle_dir = source
        self.bundle_manifest_sha256 = actual_manifest_sha256
        self.loaded_bundle = loaded
        self.policy = LearnedRegionResourcePolicy(loaded.model, loaded.manifest)
        self._bundle_fingerprint = _loaded_bundle_fingerprint(loaded)
        if self._bundle_fingerprint != _frozen_development_bundle_fingerprint():
            raise ModelBundleValidationError("paired_bundle_fingerprint_mismatch")

    def evaluate(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        ood_margin: float,
    ) -> RegionResourceIsolatedCandidateEvaluation:
        """Generate one raw candidate and prove that the bundle stayed frozen."""

        if not isfinite(float(ood_margin)) or float(ood_margin) < 0.0:
            raise ValueError("ood_margin must be finite and non-negative")
        before = _loaded_bundle_fingerprint(self.loaded_bundle)
        if before != self._bundle_fingerprint:
            raise ModelBundleValidationError("paired_bundle_changed_before_inference")

        started_at = perf_counter()
        try:
            recommendation = self.policy.recommend_raw(snapshot)
            ood_passed = not self.policy.is_ood(snapshot, margin=float(ood_margin))
        finally:
            latency_ms = 1000.0 * (perf_counter() - started_at)
            after = _loaded_bundle_fingerprint(self.loaded_bundle)
            if after != self._bundle_fingerprint:
                raise ModelBundleValidationError("paired_bundle_changed_during_inference")

        return RegionResourceIsolatedCandidateEvaluation(
            recommendation=recommendation,
            bundle_manifest_sha256=self.bundle_manifest_sha256,
            candidate_latency_ms=latency_ms,
            candidate_ood_passed=ood_passed,
        )


class RegionResourcePairedInterventionExecutor:
    """Apply one arm inside an isolated experiment without online authority."""

    def __init__(
        self, specification: RegionResourcePairedInterventionSpecification
    ) -> None:
        self.specification = specification
        projection = specification.thresholds.projection_config
        self.projector = DeterministicResourceProjector(projection)
        self.rule_policy = RuleRegionResourcePolicy(
            RuleRegionResourcePolicyConfig(projection=projection),
            projector=self.projector,
        )

    def execute_arm(
        self,
        *,
        arm: RegionResourcePairedArm | str,
        seed: int,
        observed_input_binding: RegionResourcePairedInputBinding,
        snapshot: RegionResourceSnapshot,
        evaluated_at_s: float,
        candidate_recommendation: RegionResourceRecommendation | None = None,
        candidate_bundle_manifest_sha256: str | None = None,
        candidate_latency_ms: float = 0.0,
        candidate_ood_passed: bool = True,
        candidate_failure_reasons: Sequence[str] = (),
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourcePairedArmEvidence:
        normalized_arm = arm if isinstance(arm, RegionResourcePairedArm) else RegionResourcePairedArm(str(arm))
        arm_spec = self.specification.arm_for(seed, normalized_arm)
        expected_input = arm_spec.input_binding
        expected_input_sha = expected_input.sha256
        observed_input_sha = observed_input_binding.sha256
        snapshot_sha = canonical_runtime_payload_sha256(snapshot.to_dict())
        if not isfinite(float(evaluated_at_s)) or float(evaluated_at_s) < 0.0:
            raise ValueError("evaluated_at_s must be finite and non-negative")
        if not isfinite(float(candidate_latency_ms)) or float(candidate_latency_ms) < 0.0:
            raise ValueError("candidate_latency_ms must be finite and non-negative")

        input_rejections = _input_rejections(expected_input, observed_input_binding)
        input_rejections.extend(_snapshot_rejections(expected_input, snapshot))
        pair_input_match = (
            not input_rejections and expected_input_sha == observed_input_sha
        )
        rejections = list(input_rejections)
        normalized_candidate_failures = _unique(candidate_failure_reasons)
        if (
            normalized_arm == RegionResourcePairedArm.CONTROL
            and normalized_candidate_failures
        ):
            raise ValueError("control arm cannot carry candidate failure reasons")
        rejections.extend(normalized_candidate_failures)
        authority_rejections = _authority_fence_rejections(
            snapshot, evaluated_at_s=float(evaluated_at_s)
        )
        rejections.extend(authority_rejections)
        advisory_window_safe = bool(
            float(evaluated_at_s)
            < snapshot.timestamp_s + self.specification.thresholds.advisory_ttl_s
        )
        if not advisory_window_safe:
            rejections.append("advisory_window_expired_before_next_cycle")
        candidate_considered = bool(
            normalized_arm == RegionResourcePairedArm.TREATMENT
            and candidate_recommendation is not None
        )
        candidate_bundle_match = normalized_arm == RegionResourcePairedArm.CONTROL
        candidate_thresholds_passed = normalized_arm == RegionResourcePairedArm.CONTROL
        candidate_projection_passed = normalized_arm == RegionResourcePairedArm.CONTROL
        candidate_sha: str | None = None
        projection_notes: tuple[str, ...] = ()
        selected: RegionResourceRecommendation | None = None
        fallback_used = False
        deterministic_rule_executed = normalized_arm == RegionResourcePairedArm.CONTROL

        if normalized_arm == RegionResourcePairedArm.TREATMENT:
            bundle = self.specification.candidate_bundle
            if candidate_recommendation is not None:
                candidate_sha = canonical_runtime_payload_sha256(
                    candidate_recommendation.to_dict()
                )
            candidate_bundle_match = bool(
                candidate_recommendation is not None
                and candidate_bundle_manifest_sha256 == bundle.bundle_manifest_sha256
                and candidate_recommendation.model_sha256 == bundle.model_state_sha256
                and candidate_recommendation.policy_name == bundle.policy_name
                and candidate_recommendation.policy_version == bundle.policy_version
                and candidate_recommendation.source == RecommendationSource.LEARNED
                and candidate_recommendation.projected is False
            )
            if not candidate_bundle_match:
                rejections.append("candidate_bundle_or_policy_mismatch")
            timeout_ms = 1000.0 * self.specification.thresholds.inference_timeout_s
            candidate_thresholds_passed = bool(
                candidate_recommendation is not None
                and not normalized_candidate_failures
                and candidate_latency_ms <= timeout_ms
                and candidate_ood_passed is True
                and candidate_recommendation.confidence
                >= self.specification.thresholds.minimum_confidence
                and _recommendation_is_finite(candidate_recommendation)
            )
            if not candidate_thresholds_passed:
                rejections.append("candidate_threshold_or_finite_gate_rejected")

            if (
                pair_input_match
                and not authority_rejections
                and advisory_window_safe
                and candidate_bundle_match
                and candidate_thresholds_passed
            ):
                assert candidate_recommendation is not None
                try:
                    projected_candidate = self.projector.project(
                        snapshot,
                        candidate_recommendation,
                        formal_decision=formal_decision,
                    )
                except Exception as exc:  # Isolated candidate errors must fail closed.
                    rejections.append(
                        _failure_reason("candidate_projection_failed", exc)
                    )
                else:
                    projection_notes = tuple(
                        projected_candidate.projection_rejections
                    )
                    candidate_projection_passed = all(
                        note.endswith(_ALLOWED_PROJECTION_NOTES)
                        for note in projection_notes
                    )
                    if candidate_projection_passed:
                        selected = projected_candidate
                    else:
                        rejections.extend(
                            f"candidate_projection_rejected:{note}"
                            for note in projection_notes
                        )
            if selected is None:
                fallback_used = True
                deterministic_rule_executed = True

        if selected is None:
            selected = self.rule_policy.recommend(
                snapshot,
                formal_decision=formal_decision,
                fallback_reason=(
                    "paired_treatment_candidate_rejected"
                    if normalized_arm == RegionResourcePairedArm.TREATMENT
                    else None
                ),
            )

        advisory = self.projector.build_advisory_contract(
            snapshot,
            selected,
            formal_decision=formal_decision,
        )
        consumption = self.projector.validate_for_consumption(
            advisory,
            snapshot,
            evaluated_at_s=float(evaluated_at_s),
            formal_decision=formal_decision,
        )
        next_cycle_passed = bool(
            pair_input_match
            and not advisory.publication_rejections
            and consumption.consumable
        )
        if advisory.publication_rejections:
            rejections.extend(
                f"executed_advisory_rejected:{reason}"
                for reason in advisory.publication_rejections
            )
        if not consumption.consumable:
            rejections.extend(
                f"next_cycle_consumption_rejected:{reason}"
                for reason in consumption.rejection_reasons
            )
        isolated_treatment_adopted = bool(
            normalized_arm == RegionResourcePairedArm.TREATMENT
            and not fallback_used
            and candidate_projection_passed
            and next_cycle_passed
        )
        return RegionResourcePairedArmEvidence(
            arm_id=arm_spec.arm_id,
            arm=normalized_arm,
            seed=int(seed),
            specification_sha256=self.specification.sha256,
            expected_input_sha256=expected_input_sha,
            observed_input_sha256=observed_input_sha,
            snapshot_payload_sha256=snapshot_sha,
            evaluated_at_s=float(evaluated_at_s),
            candidate_latency_ms=float(candidate_latency_ms),
            pair_input_match=pair_input_match,
            candidate_considered=candidate_considered,
            candidate_bundle_match=candidate_bundle_match,
            candidate_thresholds_passed=candidate_thresholds_passed,
            candidate_safety_projection_passed=candidate_projection_passed,
            deterministic_rule_executed=deterministic_rule_executed,
            rule_fallback_used=fallback_used,
            next_cycle_consumption_passed=next_cycle_passed,
            isolated_arm_safe_adopted=next_cycle_passed,
            isolated_treatment_safe_adopted=isolated_treatment_adopted,
            candidate_recommendation_sha256=candidate_sha,
            executed_recommendation_sha256=canonical_runtime_payload_sha256(
                selected.to_dict()
            ),
            advisory_id=advisory.advisory_id,
            advisory_payload_sha256=canonical_runtime_payload_sha256(
                advisory.to_dict()
            ),
            projection_notes=projection_notes,
            rejection_reasons=_unique(rejections),
        )


class RegionResourceIsolatedPairedEvaluator:
    """Stable main-facing entry for one same-snapshot isolated arm pair.

    Bundle load and inference failures are converted into treatment evidence
    with deterministic rule fallback.  The control arm never sees the learned
    candidate, and neither arm can emit an online ACK, outcome, or authority.
    """

    def __init__(
        self,
        specification: RegionResourcePairedInterventionSpecification,
        bundle_dir: str | Path,
        *,
        map_location: Any = "cpu",
    ) -> None:
        self.specification = specification
        self.executor = RegionResourcePairedInterventionExecutor(specification)
        self.bundle_dir = Path(bundle_dir)
        self.candidate_loader: RegionResourceIsolatedPairedCandidateLoader | None = None
        self.load_rejection_reasons: tuple[str, ...] = ()
        self.actual_bundle_manifest_sha256: str | None = None
        try:
            self.actual_bundle_manifest_sha256 = _sha256_file(
                self.bundle_dir / "manifest.json"
            )
            self.candidate_loader = RegionResourceIsolatedPairedCandidateLoader(
                specification.candidate_bundle,
                self.bundle_dir,
                map_location=map_location,
            )
        except (
            ModelBundleValidationError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self.load_rejection_reasons = (
                _failure_reason("isolated_candidate_load_failed", exc),
            )

    @property
    def candidate_loader_ready(self) -> bool:
        return self.candidate_loader is not None

    def execute_pair(
        self,
        *,
        seed: int,
        observed_input_binding: RegionResourcePairedInputBinding,
        snapshot: RegionResourceSnapshot,
        evaluated_at_s: float,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> tuple[RegionResourcePairedArmEvidence, RegionResourcePairedArmEvidence]:
        """Execute control and treatment against the exact same snapshot object."""

        control = self.executor.execute_arm(
            arm=RegionResourcePairedArm.CONTROL,
            seed=seed,
            observed_input_binding=observed_input_binding,
            snapshot=snapshot,
            evaluated_at_s=evaluated_at_s,
            formal_decision=formal_decision,
        )

        candidate: RegionResourceIsolatedCandidateEvaluation | None = None
        candidate_rejections = list(self.load_rejection_reasons)
        if self.candidate_loader is not None:
            try:
                candidate = self.candidate_loader.evaluate(
                    snapshot,
                    ood_margin=self.specification.thresholds.ood_margin,
                )
            except (
                ModelBundleValidationError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                candidate_rejections.append(
                    _failure_reason("isolated_candidate_inference_failed", exc)
                )
        if candidate is not None:
            if not candidate.candidate_ood_passed:
                candidate_rejections.append("isolated_candidate_ood_rejected")
            if candidate.candidate_latency_ms > (
                1000.0 * self.specification.thresholds.inference_timeout_s
            ):
                candidate_rejections.append("isolated_candidate_inference_timeout")

        treatment = self.executor.execute_arm(
            arm=RegionResourcePairedArm.TREATMENT,
            seed=seed,
            observed_input_binding=observed_input_binding,
            snapshot=snapshot,
            evaluated_at_s=evaluated_at_s,
            candidate_recommendation=(
                candidate.recommendation if candidate is not None else None
            ),
            candidate_bundle_manifest_sha256=(
                candidate.bundle_manifest_sha256
                if candidate is not None
                else self.actual_bundle_manifest_sha256
            ),
            candidate_latency_ms=(
                candidate.candidate_latency_ms if candidate is not None else 0.0
            ),
            candidate_ood_passed=(
                candidate.candidate_ood_passed if candidate is not None else False
            ),
            candidate_failure_reasons=tuple(candidate_rejections),
            formal_decision=formal_decision,
        )
        return control, treatment


def build_region_resource_paired_intervention_specification(
    *,
    experiment_id: str,
    experiment_version: str,
    input_bindings: Sequence[RegionResourcePairedInputBinding],
    candidate_bundle: RegionResourceCandidateBundleBinding,
    thresholds: RegionResourcePairedThresholds | None = None,
) -> RegionResourcePairedInterventionSpecification:
    """Build the exact 20-seed, two-arm held-out specification."""

    by_seed: dict[int, RegionResourcePairedInputBinding] = {}
    for binding in input_bindings:
        seed = int(binding.seed)
        if seed in by_seed:
            raise ValueError("input bindings contain a duplicate seed")
        by_seed[seed] = binding
    if tuple(sorted(by_seed)) != REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
        raise ValueError("input bindings must cover exactly seeds 1000-1019")
    arms: list[RegionResourcePairedArmSpecification] = []
    for seed in REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
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
                    policy_name=candidate_bundle.policy_name,
                    policy_version=candidate_bundle.policy_version,
                    candidate_influence_allowed=True,
                ),
            )
        )
    return RegionResourcePairedInterventionSpecification(
        experiment_id=experiment_id,
        experiment_version=experiment_version,
        candidate_bundle=candidate_bundle,
        thresholds=thresholds or RegionResourcePairedThresholds(),
        safety_shell=RegionResourcePairedSafetyShellBinding(),
        arms=tuple(arms),
    )


def build_region_resource_shadow_paired_evaluator(
    specification: RegionResourcePairedInterventionSpecification,
) -> ShadowPairedEvaluator:
    """Return the existing evaluator for a future independent D6 sidecar.

    Building the evaluator does not make outcomes available.  D6 must first
    provide exact arm-complete metrics bound to this specification.
    """

    if specification.reserved_seeds != REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
        raise ValueError("paired evaluator requires the frozen held-out seeds")
    return ShadowPairedEvaluator(
        minimum_unseen_seeds=len(REGION_RESOURCE_RESERVED_EVALUATION_SEEDS)
    )


def _input_rejections(
    expected: RegionResourcePairedInputBinding,
    observed: RegionResourcePairedInputBinding,
) -> list[str]:
    reasons: list[str] = []
    for name in expected.__dataclass_fields__:
        if getattr(expected, name) != getattr(observed, name):
            reasons.append(f"paired_input_mismatch:{name}")
    return reasons


def _snapshot_rejections(
    expected: RegionResourcePairedInputBinding,
    snapshot: RegionResourceSnapshot,
) -> list[str]:
    reasons: list[str] = []
    if int(snapshot.seed) != int(expected.seed):
        reasons.append("snapshot_seed_mismatch")
    if snapshot.scenario_id != expected.scenario_id:
        reasons.append("snapshot_scenario_id_mismatch")
    if snapshot.scenario_version != expected.scenario_version:
        reasons.append("snapshot_scenario_version_mismatch")
    return reasons


def _authority_fence_rejections(
    snapshot: RegionResourceSnapshot, *, evaluated_at_s: float
) -> list[str]:
    reasons: list[str] = []
    for node in snapshot.regions:
        prefix = f"region:{node.region_id}"
        if not node.owner_active:
            reasons.append(f"{prefix}:authority_owner_inactive")
        if node.fault_fenced:
            reasons.append(f"{prefix}:fault_fence_active")
        if not node.coalition_ack_complete:
            reasons.append(f"{prefix}:coalition_ack_incomplete")
        if node.lease_expires_at_s <= evaluated_at_s:
            reasons.append(f"{prefix}:authority_lease_expired")
    return reasons


def _recommendation_is_finite(recommendation: RegionResourceRecommendation) -> bool:
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


def _loaded_bundle_fingerprint(
    loaded: LoadedRegionResourceModelBundle,
) -> tuple[tuple[str, str], ...]:
    paths = [
        loaded.bundle_dir / "manifest.json",
        loaded.bundle_dir / loaded.manifest.state_dict_file,
    ]
    if loaded.manifest.training_dataset_available:
        assert loaded.manifest.training_manifest_file is not None
        paths.append(loaded.bundle_dir / loaded.manifest.training_manifest_file)
    fingerprint: list[tuple[str, str]] = []
    for path in paths:
        if path.is_symlink():
            raise ModelBundleValidationError("paired_bundle_file_symlink_forbidden")
        fingerprint.append((path.name, _sha256_file(path)))
    return tuple(fingerprint)


def _frozen_development_bundle_fingerprint() -> tuple[tuple[str, str], ...]:
    return (
        (
            "manifest.json",
            REGION_RESOURCE_FROZEN_DEVELOPMENT_MANIFEST_SHA256,
        ),
        (
            "state_dict.pt",
            REGION_RESOURCE_FROZEN_DEVELOPMENT_STATE_DICT_SHA256,
        ),
        (
            "training_dataset_manifest.json",
            REGION_RESOURCE_FROZEN_DEVELOPMENT_TRAINING_MANIFEST_SHA256,
        ),
    )


def _validate_frozen_development_manifest(
    loaded: LoadedRegionResourceModelBundle,
) -> None:
    manifest = loaded.manifest
    expected = {
        "architecture": REGION_GRAPH_ARCHITECTURE,
        "model_version": REGION_RESOURCE_FROZEN_DEVELOPMENT_MODEL_VERSION,
        "state_dict_sha256": (
            REGION_RESOURCE_FROZEN_DEVELOPMENT_STATE_DICT_SHA256
        ),
        "training_manifest_sha256": (
            REGION_RESOURCE_FROZEN_DEVELOPMENT_TRAINING_MANIFEST_SHA256
        ),
        "training_dataset_sha256": (
            REGION_RESOURCE_FROZEN_DEVELOPMENT_DATASET_SHA256
        ),
        "training_split_sha256": REGION_RESOURCE_FROZEN_DEVELOPMENT_SPLIT_SHA256,
        "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
        "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
    }
    for name, value in expected.items():
        if getattr(manifest, name) != value:
            raise ModelBundleValidationError(
                f"paired_bundle_frozen_manifest_mismatch:{name}"
            )
    if (
        manifest.training_dataset_available is not True
        or loaded.training_dataset_manifest is None
    ):
        raise ModelBundleValidationError(
            "paired_bundle_training_manifest_unavailable"
        )
    if any(
        (
            manifest.reward_evidence_available,
            manifest.action_diversity_sufficient,
            manifest.strategy_capability_claim_allowed,
        )
    ):
        raise ModelBundleValidationError(
            "paired_bundle_development_admission_flags_changed"
        )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _failure_reason(prefix: str, exc: Exception) -> str:
    detail = "_".join((str(exc).strip() or type(exc).__name__).split())
    return f"{prefix}:{detail}"


def _content_id(prefix: str, value: Any, *, excluded: Sequence[str]) -> str:
    payload = to_jsonable(value)
    if not isinstance(payload, dict):
        raise TypeError("content-addressed value must serialize to an object")
    for key in excluded:
        payload.pop(key, None)
    return f"{prefix}-{_canonical_sha256(payload)}"


def _canonical_sha256(value: Any) -> str:
    serialized = json.dumps(
        to_jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def _require_sha256(value: str, path: str) -> None:
    if len(value) != _SHA256_HEX_LENGTH or not all(
        character in "0123456789abcdefABCDEF" for character in value
    ):
        raise ValueError(f"{path} must be a SHA256 hex digest")


def _reject_truth_keys(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if any(token in normalized for token in _FORBIDDEN_KEY_TOKENS):
                raise ValueError(f"truth or target identity key is forbidden at {path}.{key}")
            _reject_truth_keys(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_truth_keys(item, f"{path}[{index}]")


def _require_exact_keys(
    value: Mapping[str, Any], expected: Mapping[str, Any], path: str
) -> None:
    actual_keys = set(value)
    expected_keys = set(expected)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise ValueError(f"{path} keys mismatch: missing={missing}, extra={extra}")


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


REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_BINDING = (
    RegionResourceCandidateBundleBinding(
        bundle_id=REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_ID,
        bundle_version=REGION_RESOURCE_FROZEN_DEVELOPMENT_MODEL_VERSION,
        bundle_manifest_sha256=(
            REGION_RESOURCE_FROZEN_DEVELOPMENT_MANIFEST_SHA256
        ),
        model_state_sha256=(
            REGION_RESOURCE_FROZEN_DEVELOPMENT_STATE_DICT_SHA256
        ),
        policy_name=REGION_GRAPH_ARCHITECTURE,
        policy_version=REGION_RESOURCE_FROZEN_DEVELOPMENT_MODEL_VERSION,
    )
)
