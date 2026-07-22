"""Fail-closed evidence for consuming a D3 plan in an isolated rollout.

This contract confirms only that one versioned D3 plan was admitted by an
isolated simulation arm.  It is deliberately separate from the production
runtime ACK contract and cannot assert physical outcome, reward, causality,
online learning assistance, PPO, or assignment authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from .models import AssignmentPlan
from .paired_intervention import (
    CONTROL_ARM,
    TREATMENT_ARM,
    PairedInterventionArmSpecification,
    PairedInterventionExecutionReceipt,
    PairedInterventionSpecification,
)
from .planning_evidence import PlanningFrameEvidence
from .runtime_plan_ack import (
    canonical_runtime_payload_sha256,
    validated_assignment_plan_payload_sha256,
)
from .isolated_execution_plan import (
    IsolatedExecutionPlanConversionEvidence,
    validate_isolated_execution_plan_conversion,
)


ISOLATED_PLAN_SOURCE_LINEAGE_SCHEMA_V1 = (
    "d3.isolated-plan-source-lineage.v1"
)
ISOLATED_PLAN_CONSUMPTION_EVIDENCE_SCHEMA_V1 = (
    "d3.isolated-plan-consumption-evidence.v1"
)
ISOLATED_PLAN_CONSUMPTION_EVIDENCE_KIND = (
    "isolated_simulation_plan_consumption_confirmation"
)
ISOLATED_PLAN_CONSUMPTION_ACCEPTED_STATUS = (
    "accepted_by_isolated_simulation_consumer"
)

_HEX_DIGITS = frozenset("0123456789abcdef")
_LINEAGE_FIELDS = frozenset(
    {
        "schema_version",
        "scenario_version",
        "scenario_config_sha256",
        "initial_world_state_sha256",
        "input_snapshot_schema_version",
        "observation_input_snapshot_sha256",
        "d1_d2_lineage_contract_version",
        "d1_d2_lineage_contract_sha256",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "consumption_id",
        "experiment_id",
        "experiment_version",
        "pair_id",
        "seed",
        "arm_id",
        "arm_kind",
        "isolation_id",
        "arm_spec_sha256",
        "execution_receipt_sha256",
        "source_snapshot_lineage",
        "source_snapshot_lineage_sha256",
        "plan_id",
        "plan_version",
        "plan_schema_version",
        "plan_payload_sha256",
        "plan_created_at_s",
        "plan_valid_until_s",
        "rollout_cycle",
        "consumption_timestamp_s",
        "assignment_count",
        "binding_count",
        "binding_inventory_sha256",
        "accepted",
        "status",
        "isolated_plan_applied",
        "production_runtime_ack",
        "isolated_simulation_only",
        "control_applied_to_production_world",
        "physical_outcome_available",
        "reward_available",
        "causal_evidence_available",
        "ppo_enabled",
        "online_assist_enabled",
        "online_authority_enabled",
        "rule_fallback_enabled",
    }
)


class IsolatedPlanConsumptionError(ValueError):
    """Stable fail-closed error raised by the isolated consumer contract."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        self.reason = self.code
        super().__init__(message or self.code)


@dataclass(frozen=True, slots=True)
class IsolatedPlanSourceLineage:
    """Anonymous source snapshot lineage shared by paired rollout arms."""

    scenario_version: str
    scenario_config_sha256: str
    initial_world_state_sha256: str
    input_snapshot_schema_version: str
    observation_input_snapshot_sha256: str
    d1_d2_lineage_contract_version: str
    d1_d2_lineage_contract_sha256: str
    schema_version: str = ISOLATED_PLAN_SOURCE_LINEAGE_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != ISOLATED_PLAN_SOURCE_LINEAGE_SCHEMA_V1:
            _fail("source_lineage_schema_unsupported")
        for name in (
            "scenario_version",
            "input_snapshot_schema_version",
            "d1_d2_lineage_contract_version",
        ):
            _required_text(getattr(self, name), name)
        for name in (
            "scenario_config_sha256",
            "initial_world_state_sha256",
            "observation_input_snapshot_sha256",
            "d1_d2_lineage_contract_sha256",
        ):
            _sha256_text(getattr(self, name), name)

    @classmethod
    def from_arm(
        cls, arm: PairedInterventionArmSpecification
    ) -> "IsolatedPlanSourceLineage":
        if not isinstance(arm, PairedInterventionArmSpecification):
            _fail("arm_specification_type_invalid")
        return cls(
            scenario_version=arm.scenario_version,
            scenario_config_sha256=arm.scenario_config_sha256,
            initial_world_state_sha256=arm.initial_world_state_sha256,
            input_snapshot_schema_version=arm.input_snapshot_schema_version,
            observation_input_snapshot_sha256=(
                arm.observation_input_snapshot_sha256
            ),
            d1_d2_lineage_contract_version=(
                arm.d1_d2_lineage_contract_version
            ),
            d1_d2_lineage_contract_sha256=(
                arm.d1_d2_lineage_contract_sha256
            ),
        )

    @property
    def fingerprint(self) -> str:
        return canonical_runtime_payload_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_version": self.scenario_version,
            "scenario_config_sha256": self.scenario_config_sha256,
            "initial_world_state_sha256": self.initial_world_state_sha256,
            "input_snapshot_schema_version": (
                self.input_snapshot_schema_version
            ),
            "observation_input_snapshot_sha256": (
                self.observation_input_snapshot_sha256
            ),
            "d1_d2_lineage_contract_version": (
                self.d1_d2_lineage_contract_version
            ),
            "d1_d2_lineage_contract_sha256": (
                self.d1_d2_lineage_contract_sha256
            ),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "IsolatedPlanSourceLineage":
        item = _strict_mapping(
            value,
            fields=_LINEAGE_FIELDS,
            code="source_lineage_fields_mismatch",
            context="isolated source lineage",
        )
        return cls(
            scenario_version=_required_text(
                item["scenario_version"], "scenario_version"
            ),
            scenario_config_sha256=_sha256_text(
                item["scenario_config_sha256"], "scenario_config_sha256"
            ),
            initial_world_state_sha256=_sha256_text(
                item["initial_world_state_sha256"],
                "initial_world_state_sha256",
            ),
            input_snapshot_schema_version=_required_text(
                item["input_snapshot_schema_version"],
                "input_snapshot_schema_version",
            ),
            observation_input_snapshot_sha256=_sha256_text(
                item["observation_input_snapshot_sha256"],
                "observation_input_snapshot_sha256",
            ),
            d1_d2_lineage_contract_version=_required_text(
                item["d1_d2_lineage_contract_version"],
                "d1_d2_lineage_contract_version",
            ),
            d1_d2_lineage_contract_sha256=_sha256_text(
                item["d1_d2_lineage_contract_sha256"],
                "d1_d2_lineage_contract_sha256",
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class IsolatedPlanConsumptionEvidence:
    """Immutable confirmation of one isolated plan-consumption event."""

    consumption_id: str
    experiment_id: str
    experiment_version: str
    pair_id: str
    seed: int
    arm_id: str
    arm_kind: str
    isolation_id: str
    arm_spec_sha256: str
    execution_receipt_sha256: str
    source_snapshot_lineage: IsolatedPlanSourceLineage
    source_snapshot_lineage_sha256: str
    plan_id: str
    plan_version: int
    plan_schema_version: str
    plan_payload_sha256: str
    plan_created_at_s: float
    plan_valid_until_s: float
    rollout_cycle: int
    consumption_timestamp_s: float
    assignment_count: int
    binding_count: int
    binding_inventory_sha256: str
    accepted: bool
    status: str
    isolated_plan_applied: bool
    production_runtime_ack: bool
    isolated_simulation_only: bool
    control_applied_to_production_world: bool
    physical_outcome_available: bool
    reward_available: bool
    causal_evidence_available: bool
    ppo_enabled: bool
    online_assist_enabled: bool
    online_authority_enabled: bool
    rule_fallback_enabled: bool
    evidence_kind: str = ISOLATED_PLAN_CONSUMPTION_EVIDENCE_KIND
    schema_version: str = ISOLATED_PLAN_CONSUMPTION_EVIDENCE_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != ISOLATED_PLAN_CONSUMPTION_EVIDENCE_SCHEMA_V1:
            _fail("consumption_schema_unsupported")
        if self.evidence_kind != ISOLATED_PLAN_CONSUMPTION_EVIDENCE_KIND:
            _fail("consumption_evidence_kind_mismatch")
        for name in (
            "consumption_id",
            "experiment_id",
            "experiment_version",
            "pair_id",
            "arm_id",
            "isolation_id",
            "plan_id",
            "plan_schema_version",
            "status",
        ):
            _required_text(getattr(self, name), name)
        if self.arm_kind not in {CONTROL_ARM, TREATMENT_ARM}:
            _fail("arm_kind_invalid")
        _nonnegative_int(self.seed, "seed")
        _positive_int(self.plan_version, "plan_version")
        _nonnegative_int(self.rollout_cycle, "rollout_cycle")
        for name in (
            "arm_spec_sha256",
            "execution_receipt_sha256",
            "source_snapshot_lineage_sha256",
            "plan_payload_sha256",
            "binding_inventory_sha256",
        ):
            _sha256_text(getattr(self, name), name)
        created = _finite_nonnegative(
            self.plan_created_at_s, "plan_created_at_s"
        )
        valid_until = _finite_nonnegative(
            self.plan_valid_until_s, "plan_valid_until_s"
        )
        consumed = _finite_nonnegative(
            self.consumption_timestamp_s, "consumption_timestamp_s"
        )
        if valid_until < created:
            _fail("plan_validity_window_invalid")
        if consumed < created or consumed > valid_until:
            _fail("isolated_plan_consumption_outside_validity_window")
        assignment_count = _nonnegative_int(
            self.assignment_count, "assignment_count"
        )
        binding_count = _nonnegative_int(self.binding_count, "binding_count")
        if binding_count != assignment_count:
            _fail("isolated_binding_inventory_incomplete")
        if not isinstance(
            self.source_snapshot_lineage, IsolatedPlanSourceLineage
        ):
            _fail("source_lineage_type_invalid")
        if (
            self.source_snapshot_lineage_sha256
            != self.source_snapshot_lineage.fingerprint
        ):
            _fail("source_snapshot_lineage_sha256_mismatch")
        for name in (
            "accepted",
            "isolated_plan_applied",
            "production_runtime_ack",
            "isolated_simulation_only",
            "control_applied_to_production_world",
            "physical_outcome_available",
            "reward_available",
            "causal_evidence_available",
            "ppo_enabled",
            "online_assist_enabled",
            "online_authority_enabled",
            "rule_fallback_enabled",
        ):
            _strict_bool(getattr(self, name), name)
        if not self.accepted or not self.isolated_plan_applied:
            _fail("isolated_plan_not_accepted")
        if self.status != ISOLATED_PLAN_CONSUMPTION_ACCEPTED_STATUS:
            _fail("isolated_consumption_status_mismatch")
        if self.production_runtime_ack:
            _fail("production_runtime_ack_forbidden")
        if not self.isolated_simulation_only:
            _fail("isolated_simulation_marker_missing")
        if self.control_applied_to_production_world:
            _fail("production_world_control_claim_forbidden")
        if (
            self.physical_outcome_available
            or self.reward_available
            or self.causal_evidence_available
        ):
            _fail("consumption_claims_outcome_reward_or_causality")
        if self.ppo_enabled:
            _fail("ppo_must_remain_disabled")
        if self.online_assist_enabled:
            _fail("online_assist_must_remain_disabled")
        if self.online_authority_enabled:
            _fail("online_authority_must_remain_disabled")
        if not self.rule_fallback_enabled:
            _fail("rule_fallback_disabled")
        if self.consumption_id != _expected_consumption_id(self):
            _fail("consumption_id_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "consumption_id": self.consumption_id,
            "experiment_id": self.experiment_id,
            "experiment_version": self.experiment_version,
            "pair_id": self.pair_id,
            "seed": int(self.seed),
            "arm_id": self.arm_id,
            "arm_kind": self.arm_kind,
            "isolation_id": self.isolation_id,
            "arm_spec_sha256": self.arm_spec_sha256,
            "execution_receipt_sha256": self.execution_receipt_sha256,
            "source_snapshot_lineage": self.source_snapshot_lineage.to_dict(),
            "source_snapshot_lineage_sha256": (
                self.source_snapshot_lineage_sha256
            ),
            "plan_id": self.plan_id,
            "plan_version": int(self.plan_version),
            "plan_schema_version": self.plan_schema_version,
            "plan_payload_sha256": self.plan_payload_sha256,
            "plan_created_at_s": float(self.plan_created_at_s),
            "plan_valid_until_s": float(self.plan_valid_until_s),
            "rollout_cycle": int(self.rollout_cycle),
            "consumption_timestamp_s": float(self.consumption_timestamp_s),
            "assignment_count": int(self.assignment_count),
            "binding_count": int(self.binding_count),
            "binding_inventory_sha256": self.binding_inventory_sha256,
            "accepted": self.accepted,
            "status": self.status,
            "isolated_plan_applied": self.isolated_plan_applied,
            "production_runtime_ack": self.production_runtime_ack,
            "isolated_simulation_only": self.isolated_simulation_only,
            "control_applied_to_production_world": (
                self.control_applied_to_production_world
            ),
            "physical_outcome_available": self.physical_outcome_available,
            "reward_available": self.reward_available,
            "causal_evidence_available": self.causal_evidence_available,
            "ppo_enabled": self.ppo_enabled,
            "online_assist_enabled": self.online_assist_enabled,
            "online_authority_enabled": self.online_authority_enabled,
            "rule_fallback_enabled": self.rule_fallback_enabled,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "IsolatedPlanConsumptionEvidence":
        item = _strict_mapping(
            value,
            fields=_EVIDENCE_FIELDS,
            code="consumption_evidence_fields_mismatch",
            context="isolated plan-consumption evidence",
        )
        lineage = IsolatedPlanSourceLineage.from_dict(
            _mapping(item["source_snapshot_lineage"], "source_snapshot_lineage")
        )
        return cls(
            consumption_id=_required_text(
                item["consumption_id"], "consumption_id"
            ),
            experiment_id=_required_text(
                item["experiment_id"], "experiment_id"
            ),
            experiment_version=_required_text(
                item["experiment_version"], "experiment_version"
            ),
            pair_id=_required_text(item["pair_id"], "pair_id"),
            seed=_nonnegative_int(item["seed"], "seed"),
            arm_id=_required_text(item["arm_id"], "arm_id"),
            arm_kind=_required_text(item["arm_kind"], "arm_kind"),
            isolation_id=_required_text(
                item["isolation_id"], "isolation_id"
            ),
            arm_spec_sha256=_sha256_text(
                item["arm_spec_sha256"], "arm_spec_sha256"
            ),
            execution_receipt_sha256=_sha256_text(
                item["execution_receipt_sha256"],
                "execution_receipt_sha256",
            ),
            source_snapshot_lineage=lineage,
            source_snapshot_lineage_sha256=_sha256_text(
                item["source_snapshot_lineage_sha256"],
                "source_snapshot_lineage_sha256",
            ),
            plan_id=_required_text(item["plan_id"], "plan_id"),
            plan_version=_positive_int(item["plan_version"], "plan_version"),
            plan_schema_version=_required_text(
                item["plan_schema_version"], "plan_schema_version"
            ),
            plan_payload_sha256=_sha256_text(
                item["plan_payload_sha256"], "plan_payload_sha256"
            ),
            plan_created_at_s=_finite_nonnegative(
                item["plan_created_at_s"], "plan_created_at_s"
            ),
            plan_valid_until_s=_finite_nonnegative(
                item["plan_valid_until_s"], "plan_valid_until_s"
            ),
            rollout_cycle=_nonnegative_int(
                item["rollout_cycle"], "rollout_cycle"
            ),
            consumption_timestamp_s=_finite_nonnegative(
                item["consumption_timestamp_s"],
                "consumption_timestamp_s",
            ),
            assignment_count=_nonnegative_int(
                item["assignment_count"], "assignment_count"
            ),
            binding_count=_nonnegative_int(
                item["binding_count"], "binding_count"
            ),
            binding_inventory_sha256=_sha256_text(
                item["binding_inventory_sha256"],
                "binding_inventory_sha256",
            ),
            accepted=_strict_bool(item["accepted"], "accepted"),
            status=_required_text(item["status"], "status"),
            isolated_plan_applied=_strict_bool(
                item["isolated_plan_applied"], "isolated_plan_applied"
            ),
            production_runtime_ack=_strict_bool(
                item["production_runtime_ack"], "production_runtime_ack"
            ),
            isolated_simulation_only=_strict_bool(
                item["isolated_simulation_only"],
                "isolated_simulation_only",
            ),
            control_applied_to_production_world=_strict_bool(
                item["control_applied_to_production_world"],
                "control_applied_to_production_world",
            ),
            physical_outcome_available=_strict_bool(
                item["physical_outcome_available"],
                "physical_outcome_available",
            ),
            reward_available=_strict_bool(
                item["reward_available"], "reward_available"
            ),
            causal_evidence_available=_strict_bool(
                item["causal_evidence_available"],
                "causal_evidence_available",
            ),
            ppo_enabled=_strict_bool(item["ppo_enabled"], "ppo_enabled"),
            online_assist_enabled=_strict_bool(
                item["online_assist_enabled"], "online_assist_enabled"
            ),
            online_authority_enabled=_strict_bool(
                item["online_authority_enabled"],
                "online_authority_enabled",
            ),
            rule_fallback_enabled=_strict_bool(
                item["rule_fallback_enabled"], "rule_fallback_enabled"
            ),
            evidence_kind=_required_text(
                item["evidence_kind"], "evidence_kind"
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


def build_isolated_plan_consumption_evidence(
    *,
    specification: PairedInterventionSpecification,
    arm_specification: PairedInterventionArmSpecification,
    execution_receipt: PairedInterventionExecutionReceipt,
    plan: AssignmentPlan,
    rollout_cycle: int,
    consumption_timestamp_s: float,
    binding_count: int | None = None,
    planning_frame_evidence: PlanningFrameEvidence | None = None,
    offline_solve_source_plan: AssignmentPlan | None = None,
    formal_authority_plan: AssignmentPlan | None = None,
    offline_candidate_plan: AssignmentPlan | None = None,
    conversion_evidence: IsolatedExecutionPlanConversionEvidence
    | Mapping[str, Any]
    | None = None,
) -> IsolatedPlanConsumptionEvidence:
    """Construct one safe, JSON-serializable isolated consumption record."""

    plan_hash = _validate_source_context(
        specification=specification,
        arm=arm_specification,
        receipt=execution_receipt,
        plan=plan,
        planning_frame_evidence=planning_frame_evidence,
        offline_solve_source_plan=offline_solve_source_plan,
        formal_authority_plan=formal_authority_plan,
        offline_candidate_plan=offline_candidate_plan,
        conversion_evidence=conversion_evidence,
    )
    assignment_count = len(plan.assignments)
    consumed_binding_count = (
        assignment_count
        if binding_count is None
        else _nonnegative_int(binding_count, "binding_count")
    )
    lineage = IsolatedPlanSourceLineage.from_arm(arm_specification)
    binding_hash = _binding_inventory_sha256(plan)
    plan_valid_until_s = _finite_nonnegative(
        (
            plan.metadata.get("plan_valid_until_s")
            if isinstance(plan.metadata, Mapping)
            and plan.metadata.get("plan_valid_until_s") is not None
            else arm_specification.plan_valid_until_s
        ),
        "plan_valid_until_s",
    )
    identity_fields = {
        "experiment_id": specification.experiment_id,
        "experiment_version": specification.experiment_version,
        "pair_id": execution_receipt.pair_id,
        "seed": arm_specification.seed,
        "arm_id": arm_specification.arm_id,
        "arm_kind": arm_specification.arm_kind,
        "isolation_id": arm_specification.isolation_id,
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "plan_payload_sha256": plan_hash,
    }
    consumption_id = _consumption_id_from_fields(identity_fields)
    return IsolatedPlanConsumptionEvidence(
        consumption_id=consumption_id,
        experiment_id=specification.experiment_id,
        experiment_version=specification.experiment_version,
        pair_id=execution_receipt.pair_id,
        seed=arm_specification.seed,
        arm_id=arm_specification.arm_id,
        arm_kind=arm_specification.arm_kind,
        isolation_id=arm_specification.isolation_id,
        arm_spec_sha256=arm_specification.fingerprint,
        execution_receipt_sha256=execution_receipt.fingerprint,
        source_snapshot_lineage=lineage,
        source_snapshot_lineage_sha256=lineage.fingerprint,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        plan_schema_version=plan.plan_schema,
        plan_payload_sha256=plan_hash,
        plan_created_at_s=plan.created_at,
        plan_valid_until_s=plan_valid_until_s,
        rollout_cycle=_nonnegative_int(rollout_cycle, "rollout_cycle"),
        consumption_timestamp_s=_finite_nonnegative(
            consumption_timestamp_s, "consumption_timestamp_s"
        ),
        assignment_count=assignment_count,
        binding_count=consumed_binding_count,
        binding_inventory_sha256=binding_hash,
        accepted=True,
        status=ISOLATED_PLAN_CONSUMPTION_ACCEPTED_STATUS,
        isolated_plan_applied=True,
        production_runtime_ack=False,
        isolated_simulation_only=True,
        control_applied_to_production_world=False,
        physical_outcome_available=False,
        reward_available=False,
        causal_evidence_available=False,
        ppo_enabled=False,
        online_assist_enabled=False,
        online_authority_enabled=False,
        rule_fallback_enabled=True,
    )


def validate_isolated_plan_consumption_evidence(
    value: IsolatedPlanConsumptionEvidence | Mapping[str, Any],
    *,
    specification: PairedInterventionSpecification,
    arm_specification: PairedInterventionArmSpecification,
    execution_receipt: PairedInterventionExecutionReceipt,
    expected_plan: AssignmentPlan,
    planning_frame_evidence: PlanningFrameEvidence | None = None,
    offline_solve_source_plan: AssignmentPlan | None = None,
    formal_authority_plan: AssignmentPlan | None = None,
    offline_candidate_plan: AssignmentPlan | None = None,
    conversion_evidence: IsolatedExecutionPlanConversionEvidence
    | Mapping[str, Any]
    | None = None,
) -> IsolatedPlanConsumptionEvidence:
    """Validate one record against its frozen experiment and expected plan."""

    evidence = (
        value
        if isinstance(value, IsolatedPlanConsumptionEvidence)
        else IsolatedPlanConsumptionEvidence.from_dict(value)
    )
    expected = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm_specification,
        execution_receipt=execution_receipt,
        plan=expected_plan,
        rollout_cycle=evidence.rollout_cycle,
        consumption_timestamp_s=evidence.consumption_timestamp_s,
        binding_count=evidence.binding_count,
        planning_frame_evidence=planning_frame_evidence,
        offline_solve_source_plan=offline_solve_source_plan,
        formal_authority_plan=formal_authority_plan,
        offline_candidate_plan=offline_candidate_plan,
        conversion_evidence=conversion_evidence,
    )
    comparisons = (
        (
            "experiment_identity_mismatch",
            (evidence.experiment_id, evidence.experiment_version),
            (expected.experiment_id, expected.experiment_version),
        ),
        (
            "arm_identity_mismatch",
            (
                evidence.pair_id,
                evidence.seed,
                evidence.arm_id,
                evidence.arm_kind,
                evidence.isolation_id,
                evidence.arm_spec_sha256,
            ),
            (
                expected.pair_id,
                expected.seed,
                expected.arm_id,
                expected.arm_kind,
                expected.isolation_id,
                expected.arm_spec_sha256,
            ),
        ),
        (
            "source_snapshot_lineage_mismatch",
            (
                evidence.source_snapshot_lineage,
                evidence.source_snapshot_lineage_sha256,
            ),
            (
                expected.source_snapshot_lineage,
                expected.source_snapshot_lineage_sha256,
            ),
        ),
        (
            "plan_identity_or_payload_mismatch",
            (
                evidence.plan_id,
                evidence.plan_version,
                evidence.plan_schema_version,
                evidence.plan_payload_sha256,
                evidence.plan_created_at_s,
                evidence.plan_valid_until_s,
            ),
            (
                expected.plan_id,
                expected.plan_version,
                expected.plan_schema_version,
                expected.plan_payload_sha256,
                expected.plan_created_at_s,
                expected.plan_valid_until_s,
            ),
        ),
        (
            "execution_receipt_identity_mismatch",
            evidence.execution_receipt_sha256,
            expected.execution_receipt_sha256,
        ),
        (
            "assignment_binding_inventory_mismatch",
            (
                evidence.assignment_count,
                evidence.binding_count,
                evidence.binding_inventory_sha256,
            ),
            (
                expected.assignment_count,
                expected.binding_count,
                expected.binding_inventory_sha256,
            ),
        ),
        (
            "consumption_identity_mismatch",
            evidence.consumption_id,
            expected.consumption_id,
        ),
    )
    for code, actual, wanted in comparisons:
        if actual != wanted:
            _fail(code)
    return evidence


class IsolatedPlanConsumptionValidator:
    """Stateful per-experiment ledger that rejects replay and stale plans."""

    def __init__(self) -> None:
        self._consumption_ids: set[str] = set()
        self._latest_by_arm: dict[
            tuple[str, str, int, str, str], tuple[int, int, float]
        ] = {}

    @property
    def consumption_count(self) -> int:
        return len(self._consumption_ids)

    def validate_and_record(
        self,
        value: IsolatedPlanConsumptionEvidence | Mapping[str, Any],
        *,
        specification: PairedInterventionSpecification,
        arm_specification: PairedInterventionArmSpecification,
        execution_receipt: PairedInterventionExecutionReceipt,
        expected_plan: AssignmentPlan,
        planning_frame_evidence: PlanningFrameEvidence | None = None,
        offline_solve_source_plan: AssignmentPlan | None = None,
        formal_authority_plan: AssignmentPlan | None = None,
        offline_candidate_plan: AssignmentPlan | None = None,
        conversion_evidence: IsolatedExecutionPlanConversionEvidence
        | Mapping[str, Any]
        | None = None,
    ) -> IsolatedPlanConsumptionEvidence:
        evidence = validate_isolated_plan_consumption_evidence(
            value,
            specification=specification,
            arm_specification=arm_specification,
            execution_receipt=execution_receipt,
            expected_plan=expected_plan,
            planning_frame_evidence=planning_frame_evidence,
            offline_solve_source_plan=offline_solve_source_plan,
            formal_authority_plan=formal_authority_plan,
            offline_candidate_plan=offline_candidate_plan,
            conversion_evidence=conversion_evidence,
        )
        if evidence.consumption_id in self._consumption_ids:
            _fail("duplicate_plan_consumption")
        arm_key = (
            evidence.experiment_id,
            evidence.experiment_version,
            evidence.seed,
            evidence.arm_kind,
            evidence.isolation_id,
        )
        latest = self._latest_by_arm.get(arm_key)
        if latest is not None:
            latest_version, latest_cycle, latest_time = latest
            if evidence.plan_version < latest_version:
                _fail("stale_plan_version")
            if evidence.plan_version == latest_version:
                _fail("plan_version_already_consumed")
            if evidence.rollout_cycle <= latest_cycle:
                _fail("stale_rollout_cycle")
            if evidence.consumption_timestamp_s <= latest_time:
                _fail("nonmonotonic_consumption_timestamp")
        self._consumption_ids.add(evidence.consumption_id)
        self._latest_by_arm[arm_key] = (
            evidence.plan_version,
            evidence.rollout_cycle,
            evidence.consumption_timestamp_s,
        )
        return evidence


def _validate_source_context(
    *,
    specification: PairedInterventionSpecification,
    arm: PairedInterventionArmSpecification,
    receipt: PairedInterventionExecutionReceipt,
    plan: AssignmentPlan,
    planning_frame_evidence: PlanningFrameEvidence | None = None,
    offline_solve_source_plan: AssignmentPlan | None = None,
    formal_authority_plan: AssignmentPlan | None = None,
    offline_candidate_plan: AssignmentPlan | None = None,
    conversion_evidence: IsolatedExecutionPlanConversionEvidence
    | Mapping[str, Any]
    | None = None,
) -> str:
    if not isinstance(specification, PairedInterventionSpecification):
        _fail("specification_type_invalid")
    if not isinstance(arm, PairedInterventionArmSpecification):
        _fail("arm_specification_type_invalid")
    if not isinstance(receipt, PairedInterventionExecutionReceipt):
        _fail("execution_receipt_type_invalid")
    expected_arm = None
    expected_pair_id = None
    for pair in specification.pairs:
        candidates = (pair.control, pair.treatment)
        for candidate in candidates:
            if candidate.arm_id == arm.arm_id:
                expected_arm = candidate
                expected_pair_id = pair.pair_id
                break
        if expected_arm is not None:
            break
    if expected_arm is None or expected_arm.fingerprint != arm.fingerprint:
        _fail("arm_not_in_experiment_specification")
    if expected_pair_id != receipt.pair_id:
        _fail("receipt_pair_id_mismatch")
    if receipt.seed != arm.seed or receipt.arm_kind != arm.arm_kind:
        _fail("receipt_arm_identity_mismatch")
    if receipt.arm_spec_sha256 != arm.fingerprint:
        _fail("receipt_arm_spec_sha256_mismatch")
    if receipt.input_snapshot_sha256 != arm.observation_input_snapshot_sha256:
        _fail("receipt_source_snapshot_mismatch")
    conversion_values = (
        planning_frame_evidence,
        offline_solve_source_plan,
        formal_authority_plan,
        offline_candidate_plan,
        conversion_evidence,
    )
    if any(value is not None for value in conversion_values):
        if any(value is None for value in conversion_values):
            _fail("isolated_execution_conversion_context_incomplete")
        assert planning_frame_evidence is not None
        assert offline_solve_source_plan is not None
        assert formal_authority_plan is not None
        assert offline_candidate_plan is not None
        assert conversion_evidence is not None
        try:
            validate_isolated_execution_plan_conversion(
                conversion_evidence,
                specification=specification,
                arm_specification=arm,
                execution_receipt=receipt,
                planning_frame_evidence=planning_frame_evidence,
                offline_solve_source_plan=offline_solve_source_plan,
                formal_authority_plan=formal_authority_plan,
                offline_candidate_plan=offline_candidate_plan,
                expected_execution_plan=plan,
            )
        except ValueError as exc:
            _fail("isolated_execution_conversion_invalid", str(exc))
        plan_hash = validated_assignment_plan_payload_sha256(plan)
    else:
        plan_hash = validated_assignment_plan_payload_sha256(plan)
        if receipt.output_plan_id != plan.plan_id:
            _fail("receipt_output_plan_id_mismatch")
        if receipt.output_plan_version != plan.version:
            _fail("receipt_output_plan_version_mismatch")
        if receipt.output_plan_payload_sha256 != plan_hash:
            _fail("receipt_output_plan_payload_sha256_mismatch")
    metadata = plan.metadata
    if not isinstance(metadata, Mapping):
        _fail("isolated_plan_metadata_invalid")
    if metadata.get("isolated_simulation") is not True:
        _fail("isolated_plan_marker_missing")
    if metadata.get("runtime_execution_allowed") is not False:
        _fail("production_runtime_execution_not_forbidden")
    for key in ("ppo_enabled", "online_assist_enabled", "online_authority_enabled"):
        if metadata.get(key) is not False:
            _fail(f"{key}_must_remain_disabled")
    if arm.ppo_enabled or arm.online_assist_enabled or arm.online_authority_enabled:
        _fail("experiment_learning_authority_enabled")
    if not arm.rule_fallback_enabled or not specification.rule_fallback_enabled:
        _fail("rule_fallback_disabled")
    return plan_hash


def _binding_inventory_sha256(plan: AssignmentPlan) -> str:
    rows = tuple(
        sorted(
            (
                assignment.resource_id,
                assignment.target_id,
                assignment.coalition_id,
                assignment.coalition_version,
                assignment.member_role,
            )
            for assignment in plan.assignments
        )
    )
    return canonical_runtime_payload_sha256(rows)


def _expected_consumption_id(
    evidence: IsolatedPlanConsumptionEvidence,
) -> str:
    return _consumption_id_from_fields(
        {
            "experiment_id": evidence.experiment_id,
            "experiment_version": evidence.experiment_version,
            "pair_id": evidence.pair_id,
            "seed": evidence.seed,
            "arm_id": evidence.arm_id,
            "arm_kind": evidence.arm_kind,
            "isolation_id": evidence.isolation_id,
            "plan_id": evidence.plan_id,
            "plan_version": evidence.plan_version,
            "plan_payload_sha256": evidence.plan_payload_sha256,
        }
    )


def _consumption_id_from_fields(value: Mapping[str, Any]) -> str:
    digest = canonical_runtime_payload_sha256(value)
    return f"d3-isolated-consumption-{digest[:24]}"


def _strict_mapping(
    value: Any,
    *,
    fields: frozenset[str],
    code: str,
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code, f"{context} must be a mapping")
    actual = frozenset(str(key) for key in value)
    if actual != fields or any(not isinstance(key, str) for key in value):
        _fail(code, f"{context} fields do not match schema")
    return value


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", f"{context} must be a mapping")
    return value


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("text_required", f"{name} must be non-empty text")
    return value


def _sha256_text(value: Any, name: str) -> str:
    text = _required_text(value, name)
    if len(text) != 64 or any(char not in _HEX_DIGITS for char in text):
        _fail("sha256_invalid", f"{name} must be lowercase SHA-256")
    return text


def _strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        _fail("boolean_required", f"{name} must be boolean")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("nonnegative_integer_required", f"{name} must be nonnegative")
    return value


def _positive_int(value: Any, name: str) -> int:
    result = _nonnegative_int(value, name)
    if result <= 0:
        _fail("positive_integer_required", f"{name} must be positive")
    return result


def _finite_nonnegative(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("finite_number_required", f"{name} must be numeric")
    result = float(value)
    if not isfinite(result) or result < 0.0:
        _fail("finite_nonnegative_required", f"{name} must be finite and nonnegative")
    return result


def _fail(code: str, message: str | None = None) -> None:
    raise IsolatedPlanConsumptionError(code, message)
