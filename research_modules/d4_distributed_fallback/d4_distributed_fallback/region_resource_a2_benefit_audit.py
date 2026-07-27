"""Truth-free same-key A2/R0 benefit-audit input contracts.

The online :class:`RegionResourceSafeAdoptionEvidence` proves only that one
candidate recommendation reached a physical execution window through the
current authority fences.  This module adds a separate, read-only pairing
contract for D6.  It binds that candidate window to one independently executed
deterministic-rule (R0) window under the same exogenous configuration.

No DTO in this module contains outcome metrics or grants model, assignment,
failover, or control authority.  D6 must load the referenced event logs and
compute any benefit or non-degradation result outside D4.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from hashlib import sha256
import json
from math import isclose, isfinite
import re
from typing import Any, Mapping, Sequence

from .region_resource import (
    RegionResourceAdvisoryContract,
    RuleRegionResourcePolicy,
)
from .region_resource_safe_adoption import (
    RegionResourceAppliedRecommendation,
    RegionResourceD3PlanReference,
    RegionResourcePhysicalWindowEvidence,
    RegionResourceSafeAdoptionEvidence,
    RegionResourceSafeAdoptionPreparation,
)


REGION_RESOURCE_A2_AUDIT_CONTEXT_SCHEMA = (
    "d4-region-resource-a2-audit-context-v1"
)
REGION_RESOURCE_A2_AUDIT_WINDOW_SCHEMA = (
    "d4-region-resource-a2-audit-window-reference-v1"
)
REGION_RESOURCE_A2_AUDIT_PERMISSIONS_SCHEMA = (
    "d4-region-resource-a2-audit-permissions-v1"
)
REGION_RESOURCE_A2_SAFE_ADOPTION_SOURCE_SCHEMA = (
    "d4-region-resource-a2-safe-adoption-audit-source-v1"
)
REGION_RESOURCE_A2_BENEFIT_AUDIT_INPUT_SCHEMA = (
    "d4-region-resource-a2-benefit-audit-input-v1"
)
REGION_RESOURCE_A2_BENEFIT_AUDIT_BATCH_SCHEMA = (
    "d4-region-resource-a2-benefit-audit-batch-v1"
)
_DEVELOPMENT_INTERVENTION_POLICY_NAME = (
    "d4-a2-constrained-development-intervention"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TIME_TOLERANCE_S = 1.0e-9
_FORBIDDEN_TRUTH_OR_RESULT_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "airsim_id",
        "ground_truth",
        "ground_truth_id",
        "intercept_success",
        "object_id",
        "object_name",
        "offline_outcome",
        "offline_outcomes",
        "offline_reward",
        "offline_rewards",
        "offline_truth_labels",
        "outcome",
        "outcome_value",
        "reward",
        "reward_value",
        "truth",
        "truth_id",
        "truth_ids",
        "truth_position",
        "truth_velocity",
    }
)


class RegionResourceA2AuditArm(str, Enum):
    """Execution arm represented by one physical-window reference."""

    A2 = "A2"
    R0 = "R0"


class RegionResourceA2BenefitAuditError(ValueError):
    """Stable fail-closed rejection from the A2/R0 audit contract."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class RegionResourceA2SafeAdoptionAuditSource:
    """Strict read-only projection of a persisted safe-adoption record.

    Main may build this projection from the in-process DTO or from one A2
    record loaded from an episode's ``learning_adoption_evidence.json``.
    """

    evidence_id: str
    evidence_content_sha256: str
    advisory_id: str
    advisory_version: int
    policy_name: str
    policy_version: str
    physical_window_id: str
    physical_window_start_s: float
    physical_window_end_s: float
    physical_window_payload_sha256: str
    physical_execution_observed: bool
    hard_constraint_violation_count: int
    applied_plan_id: str
    applied_plan_version: int
    plan_valid_until_s: float
    authority_lease_expires_at_s: float
    intervention_id: str
    intervention_payload_sha256: str
    intervention_fields: tuple[str, ...]
    identifiable_intervention_available: bool
    available: bool = True
    safe_adoption_available: bool = True
    a2_benefit_available: bool = False
    authority_granted: bool = False
    online_truth_used: bool = False
    schema: str = REGION_RESOURCE_A2_SAFE_ADOPTION_SOURCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_A2_SAFE_ADOPTION_SOURCE_SCHEMA:
            _fail(
                "safe_adoption_source_schema_mismatch",
                "unsupported safe-adoption source schema",
            )
        for name in (
            "evidence_id",
            "advisory_id",
            "policy_name",
            "policy_version",
            "physical_window_id",
            "applied_plan_id",
            "intervention_id",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), f"source.{name}"),
            )
        if self.policy_name == _DEVELOPMENT_INTERVENTION_POLICY_NAME:
            _fail(
                "development_intervention_benefit_forbidden",
                "development intervention cannot enter formal A2 benefit audit",
            )
        for name in (
            "evidence_content_sha256",
            "physical_window_payload_sha256",
            "intervention_payload_sha256",
        ):
            object.__setattr__(
                self,
                name,
                _sha256_text(getattr(self, name), f"source.{name}"),
            )
        object.__setattr__(
            self,
            "advisory_version",
            _positive_int(self.advisory_version, "source.advisory_version"),
        )
        object.__setattr__(
            self,
            "applied_plan_version",
            _nonnegative_int(
                self.applied_plan_version,
                "source.applied_plan_version",
            ),
        )
        object.__setattr__(
            self,
            "hard_constraint_violation_count",
            _nonnegative_int(
                self.hard_constraint_violation_count,
                "source.hard_constraint_violation_count",
            ),
        )
        start = _finite_nonnegative(
            self.physical_window_start_s,
            "source.physical_window_start_s",
        )
        end = _finite_nonnegative(
            self.physical_window_end_s,
            "source.physical_window_end_s",
        )
        if end <= start:
            _fail(
                "safe_adoption_source_window_invalid",
                "source physical window has non-positive duration",
            )
        object.__setattr__(self, "physical_window_start_s", start)
        object.__setattr__(self, "physical_window_end_s", end)
        object.__setattr__(
            self,
            "plan_valid_until_s",
            _finite_nonnegative(
                self.plan_valid_until_s,
                "source.plan_valid_until_s",
            ),
        )
        object.__setattr__(
            self,
            "authority_lease_expires_at_s",
            _finite_nonnegative(
                self.authority_lease_expires_at_s,
                "source.authority_lease_expires_at_s",
            ),
        )
        for name in (
            "physical_execution_observed",
            "identifiable_intervention_available",
            "available",
            "safe_adoption_available",
            "a2_benefit_available",
            "authority_granted",
            "online_truth_used",
        ):
            _strict_bool(getattr(self, name), f"source.{name}")
        if (
            not self.available
            or not self.safe_adoption_available
            or not self.identifiable_intervention_available
            or self.a2_benefit_available
            or self.authority_granted
            or self.online_truth_used
        ):
            _fail(
                "safe_adoption_source_scope_invalid",
                "source must be a truth-free adoption-only positive record",
            )
        intervention_fields = tuple(
            dict.fromkeys(
                _required_text(item, "source.intervention_fields")
                for item in _strict_sequence(
                    self.intervention_fields,
                    "source.intervention_fields",
                )
            )
        )
        if not intervention_fields:
            _fail(
                "safe_adoption_source_intervention_missing",
                "source lacks a non-noop intervention field",
            )
        object.__setattr__(
            self,
            "intervention_fields",
            intervention_fields,
        )

    @classmethod
    def from_value(
        cls,
        value: (
            RegionResourceA2SafeAdoptionAuditSource
            | RegionResourceSafeAdoptionEvidence
            | Mapping[str, Any]
        ),
    ) -> "RegionResourceA2SafeAdoptionAuditSource":
        if isinstance(value, cls):
            return value
        if isinstance(value, RegionResourceSafeAdoptionEvidence):
            return cls._from_evidence_object(value)
        return cls.from_mapping(
            _strict_mapping(value, "safe_adoption_source")
        )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "RegionResourceA2SafeAdoptionAuditSource":
        """Parse one full persisted ``RegionResourceSafeAdoptionEvidence``."""

        return cls._from_persisted_mapping(
            _strict_mapping(value, "safe_adoption_source")
        )

    @classmethod
    def _from_evidence_object(
        cls,
        evidence: RegionResourceSafeAdoptionEvidence,
    ) -> "RegionResourceA2SafeAdoptionAuditSource":
        applied = evidence.preparation.applied_recommendation
        plan = evidence.d3_successor_plan
        physical = evidence.physical_window
        if (
            applied is not None
            and not applied.intervention_evidence
            .identifiable_intervention_available
        ):
            _fail(
                "safe_adoption_source_intervention_missing",
                "source recommendation is a D3-consumable no-op",
            )
        if applied is None or plan is None or physical is None:
            _fail(
                "safe_adoption_source_chain_incomplete",
                "source lacks recommendation, plan, or physical window",
            )
        return cls(
            evidence_id=evidence.evidence_id,
            evidence_content_sha256=evidence.content_sha256,
            advisory_id=physical.advisory_id,
            advisory_version=physical.advisory_version,
            policy_name=applied.advisory.policy_name,
            policy_version=applied.advisory.policy_version,
            physical_window_id=physical.window_id,
            physical_window_start_s=physical.window_start_s,
            physical_window_end_s=physical.window_end_s,
            physical_window_payload_sha256=_canonical_sha256(
                physical.to_dict()
            ),
            physical_execution_observed=(
                physical.physical_execution_observed
            ),
            hard_constraint_violation_count=(
                physical.hard_constraint_violation_count
            ),
            applied_plan_id=physical.applied_plan_id,
            applied_plan_version=physical.applied_plan_version,
            plan_valid_until_s=plan.valid_until_s,
            authority_lease_expires_at_s=applied.lease_expires_at_s,
            intervention_id=(
                applied.intervention_evidence.intervention_id
            ),
            intervention_payload_sha256=(
                applied.intervention_evidence.content_sha256
            ),
            intervention_fields=(
                applied.intervention_evidence.intervention_fields
            ),
            identifiable_intervention_available=(
                evidence.identifiable_intervention_available
            ),
            available=evidence.available,
            safe_adoption_available=evidence.safe_adoption_available,
            a2_benefit_available=evidence.a2_benefit_available,
            authority_granted=evidence.authority_granted,
            online_truth_used=evidence.online_truth_used,
        )

    @classmethod
    def _from_persisted_mapping(
        cls,
        mapping: Mapping[str, Any],
    ) -> "RegionResourceA2SafeAdoptionAuditSource":
        _assert_truth_and_result_free(mapping)
        expected_top = {
            field.name for field in fields(RegionResourceSafeAdoptionEvidence)
        } | {"content_sha256"}
        _require_exact_keys(mapping, expected_top, "safe_adoption_source")
        stored_sha = _sha256_text(
            mapping["content_sha256"],
            "safe_adoption_source.content_sha256",
        )
        hash_payload = dict(mapping)
        hash_payload.pop("content_sha256")
        if _canonical_sha256(hash_payload) != stored_sha:
            _fail(
                "safe_adoption_source_hash_mismatch",
                "persisted safe-adoption content hash is invalid",
            )

        preparation_mapping = _strict_mapping(
            mapping["preparation"],
            "safe_adoption_source.preparation",
        )
        _require_exact_keys(
            preparation_mapping,
            {field.name for field in fields(RegionResourceSafeAdoptionPreparation)},
            "safe_adoption_source.preparation",
        )
        applied_mapping = _strict_mapping(
            preparation_mapping["applied_recommendation"],
            "safe_adoption_source.applied_recommendation",
        )
        _require_exact_keys(
            applied_mapping,
            {field.name for field in fields(RegionResourceAppliedRecommendation)},
            "safe_adoption_source.applied_recommendation",
        )
        applied_payload = dict(applied_mapping)
        applied_payload["advisory"] = RegionResourceAdvisoryContract.from_dict(
            _strict_mapping(
                applied_payload["advisory"],
                "safe_adoption_source.applied_recommendation.advisory",
            )
        )
        applied = RegionResourceAppliedRecommendation(**applied_payload)
        plan = RegionResourceD3PlanReference.from_value(
            _strict_mapping(
                mapping["d3_successor_plan"],
                "safe_adoption_source.d3_successor_plan",
            )
        )
        physical = RegionResourcePhysicalWindowEvidence.from_value(
            _strict_mapping(
                mapping["physical_window"],
                "safe_adoption_source.physical_window",
            )
        )
        return cls(
            evidence_id=mapping["evidence_id"],
            evidence_content_sha256=stored_sha,
            advisory_id=physical.advisory_id,
            advisory_version=physical.advisory_version,
            policy_name=applied.advisory.policy_name,
            policy_version=applied.advisory.policy_version,
            physical_window_id=physical.window_id,
            physical_window_start_s=physical.window_start_s,
            physical_window_end_s=physical.window_end_s,
            physical_window_payload_sha256=_canonical_sha256(
                physical.to_dict()
            ),
            physical_execution_observed=(
                physical.physical_execution_observed
            ),
            hard_constraint_violation_count=(
                physical.hard_constraint_violation_count
            ),
            applied_plan_id=physical.applied_plan_id,
            applied_plan_version=physical.applied_plan_version,
            plan_valid_until_s=plan.valid_until_s,
            authority_lease_expires_at_s=applied.lease_expires_at_s,
            intervention_id=(
                applied.intervention_evidence.intervention_id
            ),
            intervention_payload_sha256=(
                applied.intervention_evidence.content_sha256
            ),
            intervention_fields=(
                applied.intervention_evidence.intervention_fields
            ),
            identifiable_intervention_available=(
                mapping["identifiable_intervention_available"]
            ),
            available=mapping["available"],
            safe_adoption_available=mapping["safe_adoption_available"],
            a2_benefit_available=mapping["a2_benefit_available"],
            authority_granted=mapping["authority_granted"],
            online_truth_used=mapping["online_truth_used"],
        )


@dataclass(frozen=True, slots=True)
class RegionResourceA2AuditContext:
    """Common identity and exogenous configuration for one paired window."""

    comparison_key: str
    scenario_id: str
    scenario_version: str
    scale: int
    seed: int
    paired_window_id: str
    paired_exogenous_config_sha256: str
    required_window_duration_s: float
    schema: str = REGION_RESOURCE_A2_AUDIT_CONTEXT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_A2_AUDIT_CONTEXT_SCHEMA:
            _fail("audit_context_schema_mismatch", "unsupported context schema")
        for name in (
            "comparison_key",
            "scenario_id",
            "scenario_version",
            "paired_window_id",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), f"context.{name}"),
            )
        object.__setattr__(
            self,
            "scale",
            _positive_int(self.scale, "context.scale"),
        )
        object.__setattr__(
            self,
            "seed",
            _nonnegative_int(self.seed, "context.seed"),
        )
        object.__setattr__(
            self,
            "paired_exogenous_config_sha256",
            _sha256_text(
                self.paired_exogenous_config_sha256,
                "context.paired_exogenous_config_sha256",
            ),
        )
        duration = _finite_nonnegative(
            self.required_window_duration_s,
            "context.required_window_duration_s",
        )
        if duration <= 0.0:
            _fail(
                "audit_window_duration_invalid",
                "required window duration must be positive",
            )
        object.__setattr__(self, "required_window_duration_s", duration)

    @property
    def content_sha256(self) -> str:
        return _canonical_sha256(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "comparison_key": self.comparison_key,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "scale": self.scale,
            "seed": self.seed,
            "paired_window_id": self.paired_window_id,
            "paired_exogenous_config_sha256": (
                self.paired_exogenous_config_sha256
            ),
            "required_window_duration_s": self.required_window_duration_s,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content_sha256"] = self.content_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "RegionResourceA2AuditContext":
        mapping = _strict_mapping(value, "audit_context")
        _assert_truth_and_result_free(mapping)
        _require_exact_keys(
            mapping,
            {
                "schema",
                "comparison_key",
                "scenario_id",
                "scenario_version",
                "scale",
                "seed",
                "paired_window_id",
                "paired_exogenous_config_sha256",
                "required_window_duration_s",
                "content_sha256",
            },
            "audit_context",
        )
        item = cls(
            schema=mapping["schema"],
            comparison_key=mapping["comparison_key"],
            scenario_id=mapping["scenario_id"],
            scenario_version=mapping["scenario_version"],
            scale=mapping["scale"],
            seed=mapping["seed"],
            paired_window_id=mapping["paired_window_id"],
            paired_exogenous_config_sha256=(
                mapping["paired_exogenous_config_sha256"]
            ),
            required_window_duration_s=mapping[
                "required_window_duration_s"
            ],
        )
        if item.to_dict() != dict(mapping):
            _fail(
                "audit_context_recomputation_mismatch",
                "context fields or content hash differ from recomputation",
            )
        return item


@dataclass(frozen=True, slots=True)
class RegionResourceA2AuditWindowReference:
    """Truth-free pointer to one independently recorded execution window."""

    arm: RegionResourceA2AuditArm | str
    comparison_key: str
    scenario_id: str
    scenario_version: str
    scale: int
    seed: int
    paired_window_id: str
    paired_exogenous_config_sha256: str
    execution_arm_id: str
    window_id: str
    source_event_log_id: str
    source_event_log_sha256: str
    window_start_s: float
    window_end_s: float
    plan_id: str
    plan_version: int
    plan_valid_until_s: float
    authority_lease_expires_at_s: float
    physical_window_payload_sha256: str
    policy_name: str
    policy_version: str
    source_safe_adoption_evidence_sha256: str | None
    source_advisory_id: str | None
    source_advisory_version: int | None
    physical_execution_observed: bool
    window_complete: bool
    hard_constraint_violation_count: int
    online_truth_used: bool = False
    schema: str = REGION_RESOURCE_A2_AUDIT_WINDOW_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_A2_AUDIT_WINDOW_SCHEMA:
            _fail("audit_window_schema_mismatch", "unsupported window schema")
        arm = (
            self.arm
            if isinstance(self.arm, RegionResourceA2AuditArm)
            else RegionResourceA2AuditArm(str(self.arm))
        )
        object.__setattr__(self, "arm", arm)
        for name in (
            "comparison_key",
            "scenario_id",
            "scenario_version",
            "paired_window_id",
            "execution_arm_id",
            "window_id",
            "source_event_log_id",
            "plan_id",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), f"window.{name}"),
            )
        object.__setattr__(
            self,
            "scale",
            _positive_int(self.scale, "window.scale"),
        )
        object.__setattr__(
            self,
            "seed",
            _nonnegative_int(self.seed, "window.seed"),
        )
        object.__setattr__(
            self,
            "plan_version",
            _nonnegative_int(self.plan_version, "window.plan_version"),
        )
        object.__setattr__(
            self,
            "hard_constraint_violation_count",
            _nonnegative_int(
                self.hard_constraint_violation_count,
                "window.hard_constraint_violation_count",
            ),
        )
        for name in (
            "paired_exogenous_config_sha256",
            "source_event_log_sha256",
            "physical_window_payload_sha256",
        ):
            object.__setattr__(
                self,
                name,
                _sha256_text(getattr(self, name), f"window.{name}"),
            )
        start = _finite_nonnegative(
            self.window_start_s,
            "window.window_start_s",
        )
        end = _finite_nonnegative(self.window_end_s, "window.window_end_s")
        if end <= start:
            _fail(
                "audit_window_time_invalid",
                "window end must follow window start",
            )
        object.__setattr__(self, "window_start_s", start)
        object.__setattr__(self, "window_end_s", end)
        object.__setattr__(
            self,
            "plan_valid_until_s",
            _finite_nonnegative(
                self.plan_valid_until_s,
                "window.plan_valid_until_s",
            ),
        )
        object.__setattr__(
            self,
            "authority_lease_expires_at_s",
            _finite_nonnegative(
                self.authority_lease_expires_at_s,
                "window.authority_lease_expires_at_s",
            ),
        )
        for name in (
            "physical_execution_observed",
            "window_complete",
            "online_truth_used",
        ):
            _strict_bool(getattr(self, name), f"window.{name}")
        if self.online_truth_used:
            _fail(
                "online_truth_forbidden",
                "D4 benefit-audit input must be truth-free",
            )
        source_evidence_sha = _optional_sha256(
            self.source_safe_adoption_evidence_sha256,
            "window.source_safe_adoption_evidence_sha256",
        )
        source_advisory_id = _optional_text(
            self.source_advisory_id,
            "window.source_advisory_id",
        )
        source_advisory_version = _optional_nonnegative_int(
            self.source_advisory_version,
            "window.source_advisory_version",
        )
        if arm is RegionResourceA2AuditArm.A2:
            if (
                source_evidence_sha is None
                or source_advisory_id is None
                or source_advisory_version is None
                or source_advisory_version <= 0
            ):
                _fail(
                    "candidate_source_binding_missing",
                    "A2 window requires safe-adoption and advisory bindings",
                )
            if (
                self.policy_name == RuleRegionResourcePolicy.policy_name
                and self.policy_version
                == RuleRegionResourcePolicy.policy_version
            ):
                _fail(
                    "candidate_policy_invalid",
                    "A2 candidate window cannot identify the R0 rule policy",
                )
            if (
                self.policy_name
                == _DEVELOPMENT_INTERVENTION_POLICY_NAME
            ):
                _fail(
                    "development_intervention_benefit_forbidden",
                    "development intervention cannot enter formal A2 benefit audit",
                )
        else:
            if (
                source_evidence_sha is not None
                or source_advisory_id is not None
                or source_advisory_version is not None
            ):
                _fail(
                    "r0_candidate_binding_forbidden",
                    "R0 cannot reuse A2 safe-adoption or advisory bindings",
                )
            if (
                self.policy_name != RuleRegionResourcePolicy.policy_name
                or self.policy_version
                != RuleRegionResourcePolicy.policy_version
            ):
                _fail(
                    "r0_rule_identity_invalid",
                    "R0 must use the frozen deterministic rule identity",
                )
        object.__setattr__(
            self,
            "source_safe_adoption_evidence_sha256",
            source_evidence_sha,
        )
        object.__setattr__(self, "source_advisory_id", source_advisory_id)
        object.__setattr__(
            self,
            "source_advisory_version",
            source_advisory_version,
        )

    @property
    def duration_s(self) -> float:
        return self.window_end_s - self.window_start_s

    @property
    def content_sha256(self) -> str:
        return _canonical_sha256(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "arm": self.arm.value,
            "comparison_key": self.comparison_key,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "scale": self.scale,
            "seed": self.seed,
            "paired_window_id": self.paired_window_id,
            "paired_exogenous_config_sha256": (
                self.paired_exogenous_config_sha256
            ),
            "execution_arm_id": self.execution_arm_id,
            "window_id": self.window_id,
            "source_event_log_id": self.source_event_log_id,
            "source_event_log_sha256": self.source_event_log_sha256,
            "window_start_s": self.window_start_s,
            "window_end_s": self.window_end_s,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "plan_valid_until_s": self.plan_valid_until_s,
            "authority_lease_expires_at_s": (
                self.authority_lease_expires_at_s
            ),
            "physical_window_payload_sha256": (
                self.physical_window_payload_sha256
            ),
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "source_safe_adoption_evidence_sha256": (
                self.source_safe_adoption_evidence_sha256
            ),
            "source_advisory_id": self.source_advisory_id,
            "source_advisory_version": self.source_advisory_version,
            "physical_execution_observed": (
                self.physical_execution_observed
            ),
            "window_complete": self.window_complete,
            "hard_constraint_violation_count": (
                self.hard_constraint_violation_count
            ),
            "online_truth_used": False,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content_sha256"] = self.content_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "RegionResourceA2AuditWindowReference":
        mapping = _strict_mapping(value, "audit_window")
        _assert_truth_and_result_free(mapping)
        _require_exact_keys(
            mapping,
            {
                "schema",
                "arm",
                "comparison_key",
                "scenario_id",
                "scenario_version",
                "scale",
                "seed",
                "paired_window_id",
                "paired_exogenous_config_sha256",
                "execution_arm_id",
                "window_id",
                "source_event_log_id",
                "source_event_log_sha256",
                "window_start_s",
                "window_end_s",
                "plan_id",
                "plan_version",
                "plan_valid_until_s",
                "authority_lease_expires_at_s",
                "physical_window_payload_sha256",
                "policy_name",
                "policy_version",
                "source_safe_adoption_evidence_sha256",
                "source_advisory_id",
                "source_advisory_version",
                "physical_execution_observed",
                "window_complete",
                "hard_constraint_violation_count",
                "online_truth_used",
                "content_sha256",
            },
            "audit_window",
        )
        item = cls(
            schema=mapping["schema"],
            arm=mapping["arm"],
            comparison_key=mapping["comparison_key"],
            scenario_id=mapping["scenario_id"],
            scenario_version=mapping["scenario_version"],
            scale=mapping["scale"],
            seed=mapping["seed"],
            paired_window_id=mapping["paired_window_id"],
            paired_exogenous_config_sha256=(
                mapping["paired_exogenous_config_sha256"]
            ),
            execution_arm_id=mapping["execution_arm_id"],
            window_id=mapping["window_id"],
            source_event_log_id=mapping["source_event_log_id"],
            source_event_log_sha256=mapping["source_event_log_sha256"],
            window_start_s=mapping["window_start_s"],
            window_end_s=mapping["window_end_s"],
            plan_id=mapping["plan_id"],
            plan_version=mapping["plan_version"],
            plan_valid_until_s=mapping["plan_valid_until_s"],
            authority_lease_expires_at_s=(
                mapping["authority_lease_expires_at_s"]
            ),
            physical_window_payload_sha256=(
                mapping["physical_window_payload_sha256"]
            ),
            policy_name=mapping["policy_name"],
            policy_version=mapping["policy_version"],
            source_safe_adoption_evidence_sha256=(
                mapping["source_safe_adoption_evidence_sha256"]
            ),
            source_advisory_id=mapping["source_advisory_id"],
            source_advisory_version=mapping["source_advisory_version"],
            physical_execution_observed=(
                mapping["physical_execution_observed"]
            ),
            window_complete=mapping["window_complete"],
            hard_constraint_violation_count=(
                mapping["hard_constraint_violation_count"]
            ),
            online_truth_used=mapping["online_truth_used"],
        )
        if item.to_dict() != dict(mapping):
            _fail(
                "audit_window_recomputation_mismatch",
                "window fields or content hash differ from recomputation",
            )
        return item


@dataclass(frozen=True, slots=True)
class RegionResourceA2AuditPermissions:
    """Only D6 read-only audit eligibility may become true."""

    d6_benefit_audit_input_allowed: bool
    a2_assist_authority: bool = False
    model_promotion_authority: bool = False
    assignment_authority: bool = False
    failover_authority: bool = False
    control_authority: bool = False
    schema: str = REGION_RESOURCE_A2_AUDIT_PERMISSIONS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_A2_AUDIT_PERMISSIONS_SCHEMA:
            _fail(
                "audit_permissions_schema_mismatch",
                "unsupported permissions schema",
            )
        _strict_bool(
            self.d6_benefit_audit_input_allowed,
            "permissions.d6_benefit_audit_input_allowed",
        )
        for name in (
            "a2_assist_authority",
            "model_promotion_authority",
            "assignment_authority",
            "failover_authority",
            "control_authority",
        ):
            value = _strict_bool(getattr(self, name), f"permissions.{name}")
            if value:
                _fail(
                    "authority_escalation_forbidden",
                    f"A2 audit input cannot grant {name}",
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "d6_benefit_audit_input_allowed": (
                self.d6_benefit_audit_input_allowed
            ),
            "a2_assist_authority": False,
            "model_promotion_authority": False,
            "assignment_authority": False,
            "failover_authority": False,
            "control_authority": False,
        }

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "RegionResourceA2AuditPermissions":
        mapping = _strict_mapping(value, "audit_permissions")
        _require_exact_keys(
            mapping,
            {
                "schema",
                "d6_benefit_audit_input_allowed",
                "a2_assist_authority",
                "model_promotion_authority",
                "assignment_authority",
                "failover_authority",
                "control_authority",
            },
            "audit_permissions",
        )
        item = cls(**dict(mapping))
        if item.to_dict() != dict(mapping):
            _fail(
                "audit_permissions_recomputation_mismatch",
                "stored permissions differ from fail-closed recomputation",
            )
        return item


@dataclass(frozen=True, slots=True)
class RegionResourceA2BenefitAuditInput:
    """One immutable candidate/R0 pair eligible only for D6 evaluation."""

    audit_input_id: str
    context: RegionResourceA2AuditContext
    safe_adoption_evidence_sha256: str
    candidate_window: RegionResourceA2AuditWindowReference | None
    same_key_r0_window: RegionResourceA2AuditWindowReference | None
    blocker_codes: tuple[str, ...]
    candidate_physical_window_available: bool
    same_key_r0_window_available: bool
    unique_same_key_r0_available: bool
    hard_constraints_satisfied: bool
    d6_benefit_audit_eligible: bool
    permissions: RegionResourceA2AuditPermissions
    a2_benefit_available: bool = False
    authority_granted: bool = False
    final_benefit_computed: bool = False
    online_truth_used: bool = False
    consumer_module: str = "D6"
    schema: str = REGION_RESOURCE_A2_BENEFIT_AUDIT_INPUT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_A2_BENEFIT_AUDIT_INPUT_SCHEMA:
            _fail("audit_input_schema_mismatch", "unsupported input schema")
        object.__setattr__(
            self,
            "audit_input_id",
            _required_text(self.audit_input_id, "audit_input.audit_input_id"),
        )
        if not isinstance(self.context, RegionResourceA2AuditContext):
            _fail(
                "audit_context_type_invalid",
                "audit input context has an invalid type",
            )
        object.__setattr__(
            self,
            "safe_adoption_evidence_sha256",
            _sha256_text(
                self.safe_adoption_evidence_sha256,
                "audit_input.safe_adoption_evidence_sha256",
            ),
        )
        for name, value in (
            ("candidate_window", self.candidate_window),
            ("same_key_r0_window", self.same_key_r0_window),
        ):
            if value is not None and not isinstance(
                value,
                RegionResourceA2AuditWindowReference,
            ):
                _fail(
                    "audit_window_type_invalid",
                    f"{name} has an invalid type",
                )
        blockers = tuple(
            _required_text(item, "audit_input.blocker_code")
            for item in self.blocker_codes
        )
        if len(blockers) != len(set(blockers)):
            _fail(
                "audit_blocker_duplicate",
                "audit blocker codes must be unique",
            )
        object.__setattr__(self, "blocker_codes", blockers)
        for name in (
            "candidate_physical_window_available",
            "same_key_r0_window_available",
            "unique_same_key_r0_available",
            "hard_constraints_satisfied",
            "d6_benefit_audit_eligible",
            "a2_benefit_available",
            "authority_granted",
            "final_benefit_computed",
            "online_truth_used",
        ):
            _strict_bool(getattr(self, name), f"audit_input.{name}")
        if (
            self.a2_benefit_available
            or self.authority_granted
            or self.final_benefit_computed
            or self.online_truth_used
        ):
            _fail(
                "audit_scope_escalation_forbidden",
                "D4 audit input cannot claim benefit, truth, or authority",
            )
        if self.consumer_module != "D6":
            _fail(
                "audit_consumer_invalid",
                "A2 benefit-audit inputs are read-only D6 inputs",
            )
        if not isinstance(self.permissions, RegionResourceA2AuditPermissions):
            _fail(
                "audit_permissions_type_invalid",
                "audit permissions have an invalid type",
            )
        if self.d6_benefit_audit_eligible != (not blockers):
            _fail(
                "audit_eligibility_invalid",
                "D6 eligibility must equal the absence of blockers",
            )
        if (
            self.permissions.d6_benefit_audit_input_allowed
            != self.d6_benefit_audit_eligible
        ):
            _fail(
                "audit_permission_invalid",
                "D6 read permission must match computed eligibility",
            )
        expected_id = _audit_input_id(
            context_sha256=self.context.content_sha256,
            safe_adoption_evidence_sha256=(
                self.safe_adoption_evidence_sha256
            ),
            candidate_window_sha256=(
                None
                if self.candidate_window is None
                else self.candidate_window.content_sha256
            ),
            r0_window_sha256=(
                None
                if self.same_key_r0_window is None
                else self.same_key_r0_window.content_sha256
            ),
        )
        if self.audit_input_id != expected_id:
            _fail(
                "audit_input_id_mismatch",
                "audit input ID differs from immutable source bindings",
            )

    @property
    def content_sha256(self) -> str:
        return _canonical_sha256(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "audit_input_id": self.audit_input_id,
            "context": self.context.to_dict(),
            "safe_adoption_evidence_sha256": (
                self.safe_adoption_evidence_sha256
            ),
            "candidate_window": (
                None
                if self.candidate_window is None
                else self.candidate_window.to_dict()
            ),
            "same_key_r0_window": (
                None
                if self.same_key_r0_window is None
                else self.same_key_r0_window.to_dict()
            ),
            "blocker_codes": list(self.blocker_codes),
            "candidate_physical_window_available": (
                self.candidate_physical_window_available
            ),
            "same_key_r0_window_available": (
                self.same_key_r0_window_available
            ),
            "unique_same_key_r0_available": (
                self.unique_same_key_r0_available
            ),
            "hard_constraints_satisfied": self.hard_constraints_satisfied,
            "d6_benefit_audit_eligible": self.d6_benefit_audit_eligible,
            "permissions": self.permissions.to_dict(),
            "a2_benefit_available": False,
            "authority_granted": False,
            "final_benefit_computed": False,
            "online_truth_used": False,
            "consumer_module": "D6",
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content_sha256"] = self.content_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        safe_adoption_evidence: (
            RegionResourceA2SafeAdoptionAuditSource
            | RegionResourceSafeAdoptionEvidence
            | Mapping[str, Any]
        ),
    ) -> "RegionResourceA2BenefitAuditInput":
        return validate_region_resource_a2_benefit_audit_input(
            value,
            safe_adoption_evidence=safe_adoption_evidence,
        )


@dataclass(frozen=True, slots=True)
class RegionResourceA2BenefitAuditBatch:
    """Batch envelope that rejects duplicate comparison keys and R0 reuse."""

    batch_id: str
    records: tuple[RegionResourceA2BenefitAuditInput, ...]
    schema: str = REGION_RESOURCE_A2_BENEFIT_AUDIT_BATCH_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_A2_BENEFIT_AUDIT_BATCH_SCHEMA:
            _fail("audit_batch_schema_mismatch", "unsupported batch schema")
        records = tuple(self.records)
        if not records or any(
            not isinstance(item, RegionResourceA2BenefitAuditInput)
            for item in records
        ):
            _fail(
                "audit_batch_records_invalid",
                "audit batch requires D4 audit input records",
            )
        _validate_batch_uniqueness(records)
        object.__setattr__(
            self,
            "records",
            tuple(
                sorted(
                    records,
                    key=lambda item: (
                        item.context.comparison_key,
                        item.context.paired_window_id,
                    ),
                )
            ),
        )
        expected_id = _audit_batch_id(self.records)
        if self.batch_id != expected_id:
            _fail(
                "audit_batch_id_mismatch",
                "audit batch ID differs from record inventory",
            )

    @property
    def content_sha256(self) -> str:
        return _canonical_sha256(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "batch_id": self.batch_id,
            "records": [item.to_dict() for item in self.records],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content_sha256"] = self.content_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        safe_adoption_evidence_by_sha256: Mapping[
            str,
            (
                RegionResourceA2SafeAdoptionAuditSource
                | RegionResourceSafeAdoptionEvidence
                | Mapping[str, Any]
            ),
        ],
    ) -> "RegionResourceA2BenefitAuditBatch":
        mapping = _strict_mapping(value, "audit_batch")
        _assert_truth_and_result_free(mapping)
        _require_exact_keys(
            mapping,
            {"schema", "batch_id", "records", "content_sha256"},
            "audit_batch",
        )
        raw_records = _strict_sequence(mapping["records"], "audit_batch.records")
        records: list[RegionResourceA2BenefitAuditInput] = []
        for index, raw_record in enumerate(raw_records):
            record_mapping = _strict_mapping(
                raw_record,
                f"audit_batch.records[{index}]",
            )
            evidence_sha = _sha256_text(
                record_mapping.get("safe_adoption_evidence_sha256"),
                (
                    f"audit_batch.records[{index}]"
                    ".safe_adoption_evidence_sha256"
                ),
            )
            evidence = safe_adoption_evidence_by_sha256.get(evidence_sha)
            if evidence is None:
                _fail(
                    "safe_adoption_evidence_missing",
                    f"no source evidence for {evidence_sha}",
                )
            records.append(
                validate_region_resource_a2_benefit_audit_input(
                    record_mapping,
                    safe_adoption_evidence=evidence,
                )
            )
        item = assemble_region_resource_a2_benefit_audit_batch(records)
        if item.to_dict() != dict(mapping):
            _fail(
                "audit_batch_recomputation_mismatch",
                "batch inventory or content hash differs from recomputation",
            )
        return item


def assemble_region_resource_a2_benefit_audit_input(
    *,
    safe_adoption_evidence: (
        RegionResourceA2SafeAdoptionAuditSource
        | RegionResourceSafeAdoptionEvidence
        | Mapping[str, Any]
    ),
    context: RegionResourceA2AuditContext,
    candidate_window: RegionResourceA2AuditWindowReference | None,
    same_key_r0_window: RegionResourceA2AuditWindowReference | None,
) -> RegionResourceA2BenefitAuditInput:
    """Assemble one same-key pair without computing or claiming A2 benefit."""

    source = RegionResourceA2SafeAdoptionAuditSource.from_value(
        safe_adoption_evidence
    )
    if not isinstance(context, RegionResourceA2AuditContext):
        _fail(
            "audit_context_type_invalid",
            "audit context must use the D4 context DTO",
        )
    blockers: list[str] = []
    if candidate_window is None:
        blockers.append("candidate_physical_window_missing")
    else:
        _validate_window_context(candidate_window, context)
        _validate_candidate_source_binding(
            candidate_window,
            source,
        )
        blockers.extend(
            _window_availability_blockers(candidate_window, "candidate")
        )

    unique_r0 = False
    if same_key_r0_window is None:
        blockers.append("same_key_r0_window_missing")
    else:
        _validate_window_context(same_key_r0_window, context)
        if same_key_r0_window.arm is not RegionResourceA2AuditArm.R0:
            _fail("r0_arm_invalid", "same-key reference is not an R0 arm")
        blockers.extend(
            _window_availability_blockers(same_key_r0_window, "r0")
        )
        if candidate_window is not None:
            _validate_same_key_pair(
                context=context,
                candidate=candidate_window,
                r0_window=same_key_r0_window,
            )
            unique_r0 = True

    blockers = list(dict.fromkeys(blockers))
    hard_constraints_satisfied = bool(
        candidate_window is not None
        and same_key_r0_window is not None
        and candidate_window.hard_constraint_violation_count == 0
        and same_key_r0_window.hard_constraint_violation_count == 0
    )
    eligible = not blockers
    evidence_sha = source.evidence_content_sha256
    audit_input_id = _audit_input_id(
        context_sha256=context.content_sha256,
        safe_adoption_evidence_sha256=evidence_sha,
        candidate_window_sha256=(
            None if candidate_window is None else candidate_window.content_sha256
        ),
        r0_window_sha256=(
            None
            if same_key_r0_window is None
            else same_key_r0_window.content_sha256
        ),
    )
    return RegionResourceA2BenefitAuditInput(
        audit_input_id=audit_input_id,
        context=context,
        safe_adoption_evidence_sha256=evidence_sha,
        candidate_window=candidate_window,
        same_key_r0_window=same_key_r0_window,
        blocker_codes=tuple(blockers),
        candidate_physical_window_available=candidate_window is not None,
        same_key_r0_window_available=same_key_r0_window is not None,
        unique_same_key_r0_available=unique_r0,
        hard_constraints_satisfied=hard_constraints_satisfied,
        d6_benefit_audit_eligible=eligible,
        permissions=RegionResourceA2AuditPermissions(
            d6_benefit_audit_input_allowed=eligible,
        ),
    )


def validate_region_resource_a2_benefit_audit_input(
    value: Mapping[str, Any],
    *,
    safe_adoption_evidence: (
        RegionResourceA2SafeAdoptionAuditSource
        | RegionResourceSafeAdoptionEvidence
        | Mapping[str, Any]
    ),
) -> RegionResourceA2BenefitAuditInput:
    """Strictly reconstruct and recompute one serialized D4 audit input."""

    mapping = _strict_mapping(value, "audit_input")
    _assert_truth_and_result_free(mapping)
    _require_exact_keys(
        mapping,
        {
            "schema",
            "audit_input_id",
            "context",
            "safe_adoption_evidence_sha256",
            "candidate_window",
            "same_key_r0_window",
            "blocker_codes",
            "candidate_physical_window_available",
            "same_key_r0_window_available",
            "unique_same_key_r0_available",
            "hard_constraints_satisfied",
            "d6_benefit_audit_eligible",
            "permissions",
            "a2_benefit_available",
            "authority_granted",
            "final_benefit_computed",
            "online_truth_used",
            "consumer_module",
            "content_sha256",
        },
        "audit_input",
    )
    context = RegionResourceA2AuditContext.from_mapping(
        _strict_mapping(mapping["context"], "audit_input.context")
    )
    candidate = _optional_window(
        mapping["candidate_window"],
        "audit_input.candidate_window",
    )
    r0_window = _optional_window(
        mapping["same_key_r0_window"],
        "audit_input.same_key_r0_window",
    )
    expected = assemble_region_resource_a2_benefit_audit_input(
        safe_adoption_evidence=safe_adoption_evidence,
        context=context,
        candidate_window=candidate,
        same_key_r0_window=r0_window,
    )
    if expected.to_dict() != dict(mapping):
        _fail(
            "audit_input_recomputation_mismatch",
            "eligibility, blockers, permissions, or hash differ from recomputation",
        )
    return expected


def assemble_region_resource_a2_benefit_audit_batch(
    records: Sequence[RegionResourceA2BenefitAuditInput],
) -> RegionResourceA2BenefitAuditBatch:
    """Build a deterministic batch after checking unique R0 references."""

    parsed = tuple(records)
    return RegionResourceA2BenefitAuditBatch(
        batch_id=_audit_batch_id(parsed),
        records=parsed,
    )


def _validate_candidate_source_binding(
    candidate: RegionResourceA2AuditWindowReference,
    source: RegionResourceA2SafeAdoptionAuditSource,
) -> None:
    if candidate.arm is not RegionResourceA2AuditArm.A2:
        _fail("candidate_arm_invalid", "candidate window is not the A2 arm")
    float_bindings = (
        (
            candidate.window_start_s,
            source.physical_window_start_s,
            "candidate_window_start_mismatch",
        ),
        (
            candidate.window_end_s,
            source.physical_window_end_s,
            "candidate_window_end_mismatch",
        ),
        (
            candidate.plan_valid_until_s,
            source.plan_valid_until_s,
            "candidate_plan_validity_mismatch",
        ),
        (
            candidate.authority_lease_expires_at_s,
            source.authority_lease_expires_at_s,
            "candidate_authority_lease_mismatch",
        ),
    )
    for actual, expected, code in float_bindings:
        if not isclose(
            actual,
            expected,
            rel_tol=0.0,
            abs_tol=_TIME_TOLERANCE_S,
        ):
            _fail(code, f"expected {expected}, received {actual}")
    if (
        candidate.source_safe_adoption_evidence_sha256
        != source.evidence_content_sha256
        or candidate.window_id != source.physical_window_id
        or candidate.physical_window_payload_sha256
        != source.physical_window_payload_sha256
        or candidate.plan_id != source.applied_plan_id
        or candidate.plan_version != source.applied_plan_version
        or candidate.source_advisory_id != source.advisory_id
        or candidate.source_advisory_version != source.advisory_version
        or candidate.policy_name != source.policy_name
        or candidate.policy_version != source.policy_version
        or candidate.physical_execution_observed
        != source.physical_execution_observed
        or candidate.hard_constraint_violation_count
        != source.hard_constraint_violation_count
    ):
        _fail(
            "candidate_safe_adoption_binding_mismatch",
            "candidate reference differs from safe-adoption source evidence",
        )


def _validate_window_context(
    window: RegionResourceA2AuditWindowReference,
    context: RegionResourceA2AuditContext,
) -> None:
    if not isinstance(window, RegionResourceA2AuditWindowReference):
        _fail("audit_window_type_invalid", "window has an invalid type")
    identity = (
        window.comparison_key,
        window.scenario_id,
        window.scenario_version,
        window.scale,
        window.seed,
        window.paired_window_id,
        window.paired_exogenous_config_sha256,
    )
    expected = (
        context.comparison_key,
        context.scenario_id,
        context.scenario_version,
        context.scale,
        context.seed,
        context.paired_window_id,
        context.paired_exogenous_config_sha256,
    )
    if identity != expected:
        _fail(
            "audit_window_comparison_identity_mismatch",
            "window differs from scenario/scale/seed/key/window/exogenous context",
        )
    if not isclose(
        window.duration_s,
        context.required_window_duration_s,
        rel_tol=0.0,
        abs_tol=_TIME_TOLERANCE_S,
    ):
        _fail(
            "audit_window_duration_mismatch",
            "window duration differs from the frozen paired context",
        )


def _validate_same_key_pair(
    *,
    context: RegionResourceA2AuditContext,
    candidate: RegionResourceA2AuditWindowReference,
    r0_window: RegionResourceA2AuditWindowReference,
) -> None:
    if candidate.arm is not RegionResourceA2AuditArm.A2:
        _fail("candidate_arm_invalid", "candidate window is not the A2 arm")
    if r0_window.arm is not RegionResourceA2AuditArm.R0:
        _fail("r0_arm_invalid", "same-key reference is not the R0 arm")
    _validate_window_context(candidate, context)
    _validate_window_context(r0_window, context)
    if not (
        isclose(
            candidate.window_start_s,
            r0_window.window_start_s,
            rel_tol=0.0,
            abs_tol=_TIME_TOLERANCE_S,
        )
        and isclose(
            candidate.window_end_s,
            r0_window.window_end_s,
            rel_tol=0.0,
            abs_tol=_TIME_TOLERANCE_S,
        )
    ):
        _fail(
            "same_key_r0_time_window_mismatch",
            "candidate and R0 must represent the same logical time window",
        )
    reused = []
    for name in (
        "execution_arm_id",
        "window_id",
        "source_event_log_id",
        "source_event_log_sha256",
        "physical_window_payload_sha256",
    ):
        if getattr(candidate, name) == getattr(r0_window, name):
            reused.append(name)
    if reused:
        _fail(
            "same_key_r0_evidence_reuse",
            "candidate and R0 reused " + ",".join(reused),
        )


def _window_availability_blockers(
    window: RegionResourceA2AuditWindowReference,
    prefix: str,
) -> list[str]:
    blockers: list[str] = []
    if not window.physical_execution_observed:
        blockers.append(f"{prefix}_physical_execution_unobserved")
    if not window.window_complete:
        blockers.append(f"{prefix}_physical_window_incomplete")
    if window.hard_constraint_violation_count != 0:
        blockers.append(f"{prefix}_hard_constraint_violation")
    if window.window_end_s >= window.plan_valid_until_s:
        blockers.append(f"{prefix}_plan_expired_before_window_end")
    if window.window_end_s >= window.authority_lease_expires_at_s:
        blockers.append(f"{prefix}_authority_lease_expired_before_window_end")
    return blockers


def _validate_batch_uniqueness(
    records: Sequence[RegionResourceA2BenefitAuditInput],
) -> None:
    comparison_keys: set[str] = set()
    r0_window_ids: set[str] = set()
    r0_window_hashes: set[str] = set()
    r0_log_ids: set[str] = set()
    r0_log_hashes: set[str] = set()
    r0_execution_arm_ids: set[str] = set()
    for record in records:
        key = record.context.comparison_key
        r0_window = record.same_key_r0_window
        if r0_window is not None:
            identities = (
                (
                    r0_window.window_id,
                    r0_window_ids,
                    "duplicate_r0_window_id",
                ),
                (
                    r0_window.physical_window_payload_sha256,
                    r0_window_hashes,
                    "duplicate_r0_window_hash",
                ),
                (
                    r0_window.source_event_log_id,
                    r0_log_ids,
                    "duplicate_r0_event_log_id",
                ),
                (
                    r0_window.source_event_log_sha256,
                    r0_log_hashes,
                    "duplicate_r0_event_log_hash",
                ),
                (
                    r0_window.execution_arm_id,
                    r0_execution_arm_ids,
                    "duplicate_r0_execution_arm",
                ),
            )
            for identity, seen, code in identities:
                if identity in seen:
                    _fail(code, f"{key}:{identity}")
                seen.add(identity)
        if key in comparison_keys:
            _fail("duplicate_comparison_key", key)
        comparison_keys.add(key)


def _optional_window(
    value: Any,
    name: str,
) -> RegionResourceA2AuditWindowReference | None:
    if value is None:
        return None
    return RegionResourceA2AuditWindowReference.from_mapping(
        _strict_mapping(value, name)
    )


def _audit_input_id(
    *,
    context_sha256: str,
    safe_adoption_evidence_sha256: str,
    candidate_window_sha256: str | None,
    r0_window_sha256: str | None,
) -> str:
    digest = _canonical_sha256(
        {
            "schema": REGION_RESOURCE_A2_BENEFIT_AUDIT_INPUT_SCHEMA,
            "context_sha256": context_sha256,
            "safe_adoption_evidence_sha256": (
                safe_adoption_evidence_sha256
            ),
            "candidate_window_sha256": candidate_window_sha256,
            "r0_window_sha256": r0_window_sha256,
        }
    )
    return f"d4-a2-benefit-audit-{digest}"


def _audit_batch_id(
    records: Sequence[RegionResourceA2BenefitAuditInput],
) -> str:
    digest = _canonical_sha256(
        {
            "schema": REGION_RESOURCE_A2_BENEFIT_AUDIT_BATCH_SCHEMA,
            "record_sha256": sorted(item.content_sha256 for item in records),
        }
    )
    return f"d4-a2-benefit-audit-batch-{digest}"


def _assert_truth_and_result_free(value: Any, *, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            if key in _FORBIDDEN_TRUTH_OR_RESULT_KEYS:
                _fail(
                    "truth_or_result_field_forbidden",
                    f"{path}.{raw_key}",
                )
            _assert_truth_and_result_free(item, path=f"{path}.{raw_key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_truth_and_result_free(item, path=f"{path}[{index}]")


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("text_field_invalid", f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name)


def _sha256_text(value: Any, name: str) -> str:
    text = _required_text(value, name)
    if _SHA256_RE.fullmatch(text) is None:
        _fail("sha256_field_invalid", f"{name} must be lowercase SHA256")
    return text


def _optional_sha256(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _sha256_text(value, name)


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        _fail("bool_field_invalid", f"{name} must be bool")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("integer_field_invalid", f"{name} must be a non-negative int")
    return value


def _positive_int(value: Any, name: str) -> int:
    parsed = _nonnegative_int(value, name)
    if parsed <= 0:
        _fail("integer_field_invalid", f"{name} must be a positive int")
    return parsed


def _optional_nonnegative_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, name)


def _finite_nonnegative(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("float_field_invalid", f"{name} must be finite and non-negative")
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0.0:
        _fail("float_field_invalid", f"{name} must be finite and non-negative")
    return parsed


def _strict_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_field_invalid", f"{name} must be a mapping")
    return value


def _strict_sequence(value: Any, name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("sequence_field_invalid", f"{name} must be a sequence")
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    name: str,
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail(
            "mapping_fields_mismatch",
            f"{name}: missing={missing}, extra={extra}",
        )


def _fail(code: str, detail: str) -> None:
    raise RegionResourceA2BenefitAuditError(code, detail)


__all__ = [
    "REGION_RESOURCE_A2_AUDIT_CONTEXT_SCHEMA",
    "REGION_RESOURCE_A2_AUDIT_PERMISSIONS_SCHEMA",
    "REGION_RESOURCE_A2_AUDIT_WINDOW_SCHEMA",
    "REGION_RESOURCE_A2_BENEFIT_AUDIT_BATCH_SCHEMA",
    "REGION_RESOURCE_A2_BENEFIT_AUDIT_INPUT_SCHEMA",
    "REGION_RESOURCE_A2_SAFE_ADOPTION_SOURCE_SCHEMA",
    "RegionResourceA2AuditArm",
    "RegionResourceA2AuditContext",
    "RegionResourceA2AuditPermissions",
    "RegionResourceA2AuditWindowReference",
    "RegionResourceA2BenefitAuditBatch",
    "RegionResourceA2BenefitAuditError",
    "RegionResourceA2BenefitAuditInput",
    "RegionResourceA2SafeAdoptionAuditSource",
    "assemble_region_resource_a2_benefit_audit_batch",
    "assemble_region_resource_a2_benefit_audit_input",
    "validate_region_resource_a2_benefit_audit_input",
]
