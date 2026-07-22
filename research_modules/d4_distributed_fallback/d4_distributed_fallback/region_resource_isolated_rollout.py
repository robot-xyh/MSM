"""Auditable D4 adoption boundary for isolated degraded-scenario rollouts.

The contracts in this module are intentionally separate from production
runtime acknowledgement.  They let the main-owned simulator prove that one
cloned arm consumed a D4-influenced D3 plan while retaining deterministic
fallback and authority fences.  A successful verdict is simulation evidence
only; it never grants production authority, causal attribution, PPO admission,
or a degradation-effectiveness claim.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from math import isclose, isfinite
from typing import Any

from .models import C2Health, to_jsonable
from .regional_failover import (
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverDecision,
    RegionalFailoverSnapshot,
    RegionalRegionDecision,
)
from .region_resource_runtime_ack import (
    canonical_execution_binding_sha256,
    canonical_runtime_payload_sha256,
)


REGION_RESOURCE_DEGRADED_SCENARIO_LINEAGE_SCHEMA = (
    "d4-region-resource-degraded-scenario-lineage-v1"
)
REGION_RESOURCE_ISOLATED_CANDIDATE_GATE_SCHEMA = (
    "d4-region-resource-isolated-candidate-gate-v1"
)
REGION_RESOURCE_ISOLATED_PLAN_ACK_SCHEMA = (
    "d4-region-resource-isolated-plan-consumption-ack-v1"
)
REGION_RESOURCE_ISOLATED_ADOPTION_EVIDENCE_SCHEMA = (
    "d4-region-resource-isolated-adoption-evidence-v1"
)
D3_ISOLATED_PLAN_CONSUMPTION_EVIDENCE_SCHEMA = (
    "d3.isolated-plan-consumption-evidence.v1"
)
D3_ISOLATED_PLAN_CONSUMPTION_EVIDENCE_KIND = (
    "isolated_simulation_plan_consumption_confirmation"
)
D3_ISOLATED_PLAN_CONSUMPTION_ACCEPTED_STATUS = (
    "accepted_by_isolated_simulation_consumer"
)

_D3_ISOLATED_SOURCE_LINEAGE_FIELDS = frozenset(
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
_D3_ISOLATED_CONSUMPTION_FIELDS = frozenset(
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

REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE = 0.60
REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS = 50.0


class RegionResourceDegradedScenarioKind(str, Enum):
    """The only scenario classes eligible for degraded-strategy evidence."""

    CENTER_FAILED = "center_failed"
    CENTER_AND_SECONDARY_FAILED = "center_and_secondary_failed"
    ACTIVE_RISK = "active_risk"


class RegionResourceIsolatedAdoptionKind(str, Enum):
    """What an isolated plan-consumption receipt actually proves."""

    NEW_EXECUTION_PLAN_APPLIED = "new_execution_plan_applied"
    EVALUATION_REFRESH_APPLIED = "evaluation_refresh_applied"


class RegionResourceIsolatedAdoptionCode(str, Enum):
    """Stable result codes for main/D6 availability accounting."""

    CANDIDATE_ADOPTED = "isolated_candidate_new_execution_plan_applied"
    RULE_FALLBACK_APPLIED = "isolated_rule_fallback_plan_applied"
    EVALUATION_REFRESH = "isolated_evaluation_refresh_applied"
    ACK_MISSING = "isolated_plan_consumption_ack_missing"
    ACK_INVALID = "isolated_plan_consumption_ack_invalid"
    ACK_REPLAYED = "isolated_plan_consumption_ack_replayed"
    SCENARIO_INVALID = "degraded_scenario_evidence_invalid"
    NOMINAL_NOT_ELIGIBLE = "nominal_evidence_not_eligible"
    SOURCE_LINEAGE_MISMATCH = "source_lineage_mismatch"
    NETWORK_PARTITION = "network_partition_fail_closed"
    FORMAL_DECISION_REJECTED = "formal_degraded_decision_not_executable"
    CANDIDATE_GATE_INVALID = "candidate_gate_invalid"
    PLAN_SCHEMA_INVALID = "assignment_plan_contract_invalid"
    PLAN_NOT_NEW = "isolated_execution_plan_not_strictly_new"
    REFRESH_FLAGS_INVALID = "evaluation_refresh_flags_invalid"
    REFRESH_BINDINGS_CHANGED = "evaluation_refresh_bindings_changed"
    PLAN_BINDING_MISMATCH = "isolated_plan_binding_mismatch"
    AUTHORITY_OWNER_MISMATCH = "isolated_authority_owner_mismatch"
    AUTHORITY_EPOCH_STALE = "isolated_authority_epoch_stale"
    AUTHORITY_LEASE_MISMATCH = "isolated_authority_lease_mismatch"
    AUTHORITY_LEASE_EXPIRED = "isolated_authority_lease_expired"
    GENERATION_STALE = "isolated_plan_generation_stale"
    TIMESTAMP_INVALID = "isolated_evidence_timestamp_invalid"
    MALFORMED_INPUT = "isolated_evidence_malformed"


@dataclass(frozen=True)
class RegionResourceIsolatedCandidateGate:
    """Persisted candidate diagnostics before an isolated arm consumes a plan."""

    candidate_considered: bool
    candidate_id: str | None
    candidate_payload_sha256: str | None
    candidate_confidence: float | None
    minimum_confidence: float
    candidate_ood_passed: bool | None
    candidate_latency_ms: float | None
    candidate_latency_limit_ms: float
    candidate_finite: bool | None
    candidate_failure_gate_passed: bool | None
    candidate_safety_projection_passed: bool | None
    gate_pass: bool
    rule_fallback: bool
    rejection_reasons: tuple[str, ...] = ()
    isolated_simulation_only: bool = True
    production_authority: bool = False
    schema: str = REGION_RESOURCE_ISOLATED_CANDIDATE_GATE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_ISOLATED_CANDIDATE_GATE_SCHEMA:
            raise ValueError("unsupported isolated candidate gate schema")
        if self.isolated_simulation_only is not True or self.production_authority:
            raise ValueError("candidate gate must remain isolated and non-authoritative")
        if not isinstance(self.candidate_considered, bool):
            raise ValueError("candidate_considered must be boolean")
        if not isinstance(self.gate_pass, bool) or not isinstance(
            self.rule_fallback, bool
        ):
            raise ValueError("gate_pass and rule_fallback must be boolean")
        minimum = _finite_unit_interval(
            self.minimum_confidence, "minimum_confidence"
        )
        if not isclose(
            minimum,
            REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("isolated confidence threshold must remain 0.6")
        latency_limit = _finite_nonnegative(
            self.candidate_latency_limit_ms, "candidate_latency_limit_ms"
        )
        if not isclose(
            latency_limit,
            REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("isolated latency limit must remain 50 ms")
        object.__setattr__(self, "minimum_confidence", minimum)
        object.__setattr__(self, "candidate_latency_limit_ms", latency_limit)
        object.__setattr__(
            self,
            "rejection_reasons",
            _unique_text(self.rejection_reasons),
        )

        gate_values = (
            self.candidate_confidence,
            self.candidate_ood_passed,
            self.candidate_latency_ms,
            self.candidate_finite,
            self.candidate_failure_gate_passed,
            self.candidate_safety_projection_passed,
        )
        if not self.candidate_considered:
            if self.candidate_id is not None or self.candidate_payload_sha256 is not None:
                raise ValueError("unavailable candidate cannot carry identity")
            if any(value is not None for value in gate_values):
                raise ValueError("unavailable candidate cannot carry gate measurements")
            if self.gate_pass or not self.rule_fallback:
                raise ValueError("missing candidate must fail closed to rule fallback")
            if not self.rejection_reasons:
                raise ValueError("missing candidate requires an audit reason")
            return

        if not self.candidate_id or self.candidate_payload_sha256 is None:
            raise ValueError("considered candidate requires identity and payload SHA256")
        candidate_id = _text(self.candidate_id, "candidate_id")
        candidate_sha256 = str(self.candidate_payload_sha256).lower()
        _require_sha256(candidate_sha256, "candidate_payload_sha256")
        if any(value is None for value in gate_values):
            raise ValueError("considered candidate requires all gate measurements")
        confidence = _finite_unit_interval(
            self.candidate_confidence, "candidate_confidence"
        )
        latency = _finite_nonnegative(
            self.candidate_latency_ms, "candidate_latency_ms"
        )
        for name in (
            "candidate_ood_passed",
            "candidate_finite",
            "candidate_failure_gate_passed",
            "candidate_safety_projection_passed",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        expected_gate = all(
            (
                confidence >= minimum,
                bool(self.candidate_ood_passed),
                latency <= latency_limit,
                bool(self.candidate_finite),
                bool(self.candidate_failure_gate_passed),
                bool(self.candidate_safety_projection_passed),
            )
        )
        if self.gate_pass is not expected_gate:
            raise ValueError("aggregate candidate gate contradicts persisted diagnostics")
        if not self.gate_pass and not self.rule_fallback:
            raise ValueError("failed candidate gate must select deterministic fallback")
        if not self.gate_pass and not self.rejection_reasons:
            raise ValueError("failed candidate gate requires a rejection reason")
        if self.gate_pass and not self.rule_fallback and self.rejection_reasons:
            raise ValueError("adoptable candidate gate cannot carry rejections")
        if self.gate_pass and self.rule_fallback and not self.rejection_reasons:
            raise ValueError("conservative rule override requires an audit reason")
        object.__setattr__(self, "candidate_confidence", confidence)
        object.__setattr__(self, "candidate_latency_ms", latency)
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "candidate_payload_sha256", candidate_sha256)

    @property
    def sha256(self) -> str:
        return canonical_runtime_payload_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceIsolatedCandidateGate":
        _require_exact_keys(value, cls.__dataclass_fields__, "candidate_gate")
        payload = dict(value)
        payload["rejection_reasons"] = tuple(payload["rejection_reasons"])
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceDegradedScenarioLineage:
    """Content-addressed source identity for one degraded rollout cycle."""

    scenario_kind: RegionResourceDegradedScenarioKind | str
    scenario_id: str
    scenario_version: str
    seed: int
    arm_id: str
    cycle_index: int
    region_id: str
    source_timestamp_s: float
    scenario_config_sha256: str
    initial_state_sha256: str
    communication_schedule_sha256: str
    fault_schedule_sha256: str
    source_snapshot_payload_sha256: str
    formal_decision_payload_sha256: str
    source_plan_payload_sha256: str
    candidate_gate_payload_sha256: str
    isolated_simulation_only: bool = True
    nominal_evidence: bool = False
    schema: str = REGION_RESOURCE_DEGRADED_SCENARIO_LINEAGE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_DEGRADED_SCENARIO_LINEAGE_SCHEMA:
            raise ValueError("unsupported degraded scenario lineage schema")
        kind = (
            self.scenario_kind
            if isinstance(self.scenario_kind, RegionResourceDegradedScenarioKind)
            else RegionResourceDegradedScenarioKind(str(self.scenario_kind))
        )
        object.__setattr__(self, "scenario_kind", kind)
        for name in ("scenario_id", "scenario_version", "arm_id", "region_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if (
            isinstance(self.cycle_index, bool)
            or not isinstance(self.cycle_index, int)
            or self.cycle_index < 0
        ):
            raise ValueError("cycle_index must be a non-negative integer")
        object.__setattr__(
            self,
            "source_timestamp_s",
            _finite_nonnegative(self.source_timestamp_s, "source_timestamp_s"),
        )
        for name in (
            "scenario_config_sha256",
            "initial_state_sha256",
            "communication_schedule_sha256",
            "fault_schedule_sha256",
            "source_snapshot_payload_sha256",
            "formal_decision_payload_sha256",
            "source_plan_payload_sha256",
            "candidate_gate_payload_sha256",
        ):
            normalized = str(getattr(self, name)).lower()
            _require_sha256(normalized, name)
            object.__setattr__(self, name, normalized)
        if self.isolated_simulation_only is not True:
            raise ValueError("degraded lineage must remain isolated simulation only")
        if self.nominal_evidence:
            raise ValueError("nominal evidence cannot use the degraded lineage schema")

    @property
    def sha256(self) -> str:
        return canonical_runtime_payload_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceDegradedScenarioLineage":
        _require_exact_keys(value, cls.__dataclass_fields__, "scenario_lineage")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceIsolatedPlanConsumptionAck:
    """Main-produced receipt for one isolated world plan consumption."""

    ack_id: str
    source_lineage_sha256: str
    arm_id: str
    cycle_index: int
    acknowledged_at_s: float
    accepted: bool
    status_code: str
    source_plan_id: str
    source_plan_version: int
    applied_plan_id: str
    applied_plan_version: int
    applied_plan_payload_sha256: str
    execution_binding_sha256: str
    execution_source: str
    owner_layer: str
    owner_node_id: str
    authority_epoch: int
    lease_expires_at_s: float
    assignment_count: int
    control_applied_binding_count: int
    fully_consumed_by_isolated_world: bool
    network_partition_observed: bool
    isolated_simulation_only: bool = True
    production_runtime_ack: bool = False
    schema: str = REGION_RESOURCE_ISOLATED_PLAN_ACK_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_ISOLATED_PLAN_ACK_SCHEMA:
            raise ValueError("unsupported isolated plan ACK schema")
        if self.isolated_simulation_only is not True or self.production_runtime_ack:
            raise ValueError("isolated receipt cannot claim production runtime ACK")
        for name in (
            "ack_id",
            "arm_id",
            "status_code",
            "source_plan_id",
            "applied_plan_id",
            "execution_source",
            "owner_layer",
            "owner_node_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.owner_layer not in {
            RegionalAuthorityLayer.CENTER.value,
            RegionalAuthorityLayer.SECONDARY.value,
            RegionalAuthorityLayer.DISTRIBUTED.value,
        }:
            raise ValueError("isolated receipt owner layer is invalid")
        if self.execution_source not in {
            "candidate",
            "deterministic_rule_fallback",
            "evaluation_refresh",
        }:
            raise ValueError("isolated receipt execution source is invalid")
        for name in (
            "cycle_index",
            "source_plan_version",
            "applied_plan_version",
            "authority_epoch",
            "assignment_count",
            "control_applied_binding_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in (
            "accepted",
            "fully_consumed_by_isolated_world",
            "network_partition_observed",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        object.__setattr__(
            self,
            "acknowledged_at_s",
            _finite_nonnegative(self.acknowledged_at_s, "acknowledged_at_s"),
        )
        object.__setattr__(
            self,
            "lease_expires_at_s",
            _finite_nonnegative(self.lease_expires_at_s, "lease_expires_at_s"),
        )
        for name in (
            "source_lineage_sha256",
            "applied_plan_payload_sha256",
            "execution_binding_sha256",
        ):
            normalized = str(getattr(self, name)).lower()
            _require_sha256(normalized, name)
            object.__setattr__(self, name, normalized)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceIsolatedPlanConsumptionAck":
        _require_exact_keys(value, cls.__dataclass_fields__, "isolated_plan_ack")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceIsolatedAdoptionEvidence:
    """Fail-closed verdict for one degraded isolated rollout cycle."""

    code: str
    reason: str
    scenario_kind: str | None = None
    scenario_lineage_sha256: str | None = None
    scenario_validated: bool = False
    candidate_considered: bool = False
    gate_pass: bool = False
    new_execution_plan_applied: bool = False
    evaluation_refresh_applied: bool = False
    rule_fallback: bool = True
    isolated_plan_consumption_ack_available: bool = False
    isolated_candidate_adoption_available: bool = False
    adoption_kind: str | None = None
    source_plan_id: str | None = None
    source_plan_version: int | None = None
    applied_plan_id: str | None = None
    applied_plan_version: int | None = None
    owner_layer: str | None = None
    owner_node_id: str | None = None
    authority_epoch: int | None = None
    lease_expires_at_s: float | None = None
    ack_id: str | None = None
    ack_timestamp_s: float | None = None
    candidate_gate_rejection_reasons: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    isolated_simulation_only: bool = True
    production_runtime_ack: bool = False
    physical_outcome_available: bool = False
    paired_non_degradation_available: bool = False
    counterfactual_available: bool = False
    causal_effect_available: bool = False
    degradation_effectiveness_claim_allowed: bool = False
    ppo_enabled: bool = False
    assist_enabled: bool = False
    authority_enabled: bool = False
    rule_fallback_enabled: bool = True
    schema: str = REGION_RESOURCE_ISOLATED_ADOPTION_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_ISOLATED_ADOPTION_EVIDENCE_SCHEMA:
            raise ValueError("unsupported isolated adoption evidence schema")
        if not self.code or not self.reason:
            raise ValueError("isolated adoption code and reason must not be empty")
        if self.isolated_simulation_only is not True or self.production_runtime_ack:
            raise ValueError("isolated evidence cannot claim a production ACK")
        if any(
            (
                self.physical_outcome_available,
                self.paired_non_degradation_available,
                self.counterfactual_available,
                self.causal_effect_available,
                self.degradation_effectiveness_claim_allowed,
                self.ppo_enabled,
                self.assist_enabled,
                self.authority_enabled,
            )
        ):
            raise ValueError("isolated adoption evidence cannot grant outcome or authority")
        if self.rule_fallback_enabled is not True:
            raise ValueError("deterministic rule fallback must remain enabled")
        if self.new_execution_plan_applied and self.evaluation_refresh_applied:
            raise ValueError("one receipt cannot be both execution change and refresh")
        if self.isolated_plan_consumption_ack_available != bool(
            self.new_execution_plan_applied or self.evaluation_refresh_applied
        ):
            raise ValueError("isolated ACK availability contradicts adoption kind")
        expected_candidate_adoption = bool(
            self.scenario_validated
            and self.candidate_considered
            and self.gate_pass
            and self.new_execution_plan_applied
            and not self.rule_fallback
        )
        if self.isolated_candidate_adoption_available != expected_candidate_adoption:
            raise ValueError("candidate adoption availability contradicts its gates")
        if self.isolated_candidate_adoption_available and self.rejection_reasons:
            raise ValueError("adopted candidate evidence cannot contain rejections")
        if self.new_execution_plan_applied:
            expected_kind = (
                RegionResourceIsolatedAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
            )
        elif self.evaluation_refresh_applied:
            expected_kind = (
                RegionResourceIsolatedAdoptionKind.EVALUATION_REFRESH_APPLIED.value
            )
        else:
            expected_kind = None
        if self.adoption_kind != expected_kind:
            raise ValueError("adoption_kind contradicts applied-plan flags")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class _PlanView:
    payload: Mapping[str, Any]
    payload_sha256: str
    plan_id: str
    plan_version: int
    created_at_s: float
    timestamp_s: float
    owner_layer: str
    owner_node_id: str
    authority_epoch: int
    lease_expires_at_s: float
    execution_signature_changed: bool
    plan_refresh_only: bool
    evaluation_refresh_only: bool
    plan_published: bool
    execution_source: str | None
    source_lineage_sha256: str | None
    candidate_payload_sha256: str | None
    assignment_count: int
    binding_sha256: str
    unassigned_inventory_sha256: str


@dataclass
class _EvidenceContext:
    scenario_kind: str | None = None
    scenario_lineage_sha256: str | None = None
    scenario_validated: bool = False
    candidate_considered: bool = False
    gate_pass: bool = False
    rule_fallback: bool = True
    source_plan_id: str | None = None
    source_plan_version: int | None = None
    applied_plan_id: str | None = None
    applied_plan_version: int | None = None
    owner_layer: str | None = None
    owner_node_id: str | None = None
    authority_epoch: int | None = None
    lease_expires_at_s: float | None = None
    ack_id: str | None = None
    ack_timestamp_s: float | None = None
    candidate_gate_rejection_reasons: tuple[str, ...] = ()


class _ValidationFailure(ValueError):
    def __init__(
        self, code: RegionResourceIsolatedAdoptionCode, reason: str
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class RegionResourceIsolatedAdoptionVerifier:
    """Validate degraded isolated plan receipts once and fail closed."""

    def __init__(self) -> None:
        self._consumed_ack_ids: set[str] = set()
        self._highest_generation: dict[tuple[str, str], tuple[int, int]] = {}

    @property
    def consumed_ack_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._consumed_ack_ids))

    def evaluate(
        self,
        *,
        scenario_lineage_source: RegionResourceDegradedScenarioLineage
        | Mapping[str, Any],
        source_snapshot: RegionalFailoverSnapshot,
        formal_decision: RegionalFailoverDecision,
        candidate_gate_source: RegionResourceIsolatedCandidateGate
        | Mapping[str, Any],
        source_plan_source: Mapping[str, Any],
        applied_plan_source: Mapping[str, Any],
        isolated_plan_ack_source: RegionResourceIsolatedPlanConsumptionAck
        | Mapping[str, Any]
        | None,
    ) -> RegionResourceIsolatedAdoptionEvidence:
        """Return isolated evidence without changing D4 or production authority."""

        context = _EvidenceContext()
        try:
            try:
                lineage = _parse_lineage(scenario_lineage_source)
            except (KeyError, TypeError, ValueError) as error:
                _fail(
                    RegionResourceIsolatedAdoptionCode.SCENARIO_INVALID,
                    "degraded scenario lineage is invalid: "
                    f"{type(error).__name__}",
                )
            context.scenario_kind = lineage.scenario_kind.value
            context.scenario_lineage_sha256 = lineage.sha256

            try:
                gate = _parse_candidate_gate(candidate_gate_source)
            except (KeyError, TypeError, ValueError) as error:
                _fail(
                    RegionResourceIsolatedAdoptionCode.CANDIDATE_GATE_INVALID,
                    "isolated candidate gate is invalid: "
                    f"{type(error).__name__}",
                )
            context.candidate_considered = gate.candidate_considered
            context.gate_pass = gate.gate_pass
            context.rule_fallback = gate.rule_fallback
            context.candidate_gate_rejection_reasons = gate.rejection_reasons

            try:
                source_plan = _parse_plan(source_plan_source, "source_plan")
                applied_plan = _parse_plan(applied_plan_source, "applied_plan")
            except (KeyError, TypeError, ValueError) as error:
                _fail(
                    RegionResourceIsolatedAdoptionCode.PLAN_SCHEMA_INVALID,
                    "isolated D3 plan contract is invalid: "
                    f"{type(error).__name__}",
                )
            context.source_plan_id = source_plan.plan_id
            context.source_plan_version = source_plan.plan_version
            context.applied_plan_id = applied_plan.plan_id
            context.applied_plan_version = applied_plan.plan_version
            context.owner_layer = applied_plan.owner_layer
            context.owner_node_id = applied_plan.owner_node_id
            context.authority_epoch = applied_plan.authority_epoch
            context.lease_expires_at_s = applied_plan.lease_expires_at_s

            region_decision = _validate_scenario_and_lineage(
                lineage=lineage,
                source_snapshot=source_snapshot,
                formal_decision=formal_decision,
                candidate_gate=gate,
                source_plan=source_plan,
            )
            context.scenario_validated = True

            if isolated_plan_ack_source is None:
                _fail(
                    RegionResourceIsolatedAdoptionCode.ACK_MISSING,
                    "isolated world did not provide a plan-consumption receipt",
                )
            try:
                ack = _parse_ack(isolated_plan_ack_source)
            except (KeyError, TypeError, ValueError) as error:
                _fail(
                    RegionResourceIsolatedAdoptionCode.ACK_INVALID,
                    "isolated plan receipt is invalid: "
                    f"{type(error).__name__}",
                )
            context.ack_id = ack.ack_id
            context.ack_timestamp_s = ack.acknowledged_at_s
            if ack.ack_id in self._consumed_ack_ids:
                _fail(
                    RegionResourceIsolatedAdoptionCode.ACK_REPLAYED,
                    "isolated plan-consumption receipt was already consumed",
                )

            adoption_kind = _validate_plan_transition(
                lineage=lineage,
                gate=gate,
                region_decision=region_decision,
                source_plan=source_plan,
                applied_plan=applied_plan,
                ack=ack,
            )
            self._validate_generation(lineage, applied_plan)
            self._consumed_ack_ids.add(ack.ack_id)
            self._highest_generation[(lineage.arm_id, lineage.region_id)] = (
                applied_plan.authority_epoch,
                applied_plan.plan_version,
            )
            return _available_evidence(context, adoption_kind)
        except _ValidationFailure as error:
            return _rejected_evidence(context, error)
        except (KeyError, TypeError, ValueError) as error:
            return _rejected_evidence(
                context,
                _ValidationFailure(
                    RegionResourceIsolatedAdoptionCode.MALFORMED_INPUT,
                    "isolated evidence parser rejected malformed input: "
                    f"{type(error).__name__}",
                ),
            )

    def _validate_generation(
        self,
        lineage: RegionResourceDegradedScenarioLineage,
        applied_plan: _PlanView,
    ) -> None:
        previous = self._highest_generation.get((lineage.arm_id, lineage.region_id))
        if previous is None:
            return
        current = (applied_plan.authority_epoch, applied_plan.plan_version)
        if current < previous:
            _fail(
                RegionResourceIsolatedAdoptionCode.GENERATION_STALE,
                "isolated arm attempted to consume an older authority/plan generation",
            )


def build_region_resource_degraded_scenario_lineage(
    *,
    scenario_kind: RegionResourceDegradedScenarioKind | str,
    seed: int,
    arm_id: str,
    cycle_index: int,
    region_id: str,
    scenario_config_sha256: str,
    initial_state_sha256: str,
    communication_schedule_sha256: str,
    fault_schedule_sha256: str,
    source_snapshot: RegionalFailoverSnapshot,
    formal_decision: RegionalFailoverDecision,
    source_plan_source: Mapping[str, Any],
    candidate_gate: RegionResourceIsolatedCandidateGate,
) -> RegionResourceDegradedScenarioLineage:
    """Build immutable lineage around the formal D4 authority source plan.

    ``source_plan_source`` is the plan generation named by the same-cycle
    regional D4 decision.  It is not an arbitrary D3 predecessor.  In
    particular, a pre-failure center plan cannot be used as the source for a
    secondary or distributed decision.  Semantic eligibility remains the
    verifier's responsibility.
    """

    return RegionResourceDegradedScenarioLineage(
        scenario_kind=scenario_kind,
        scenario_id=source_snapshot.scenario.scenario_name,
        scenario_version=source_snapshot.scenario.scenario_version,
        seed=int(seed),
        arm_id=arm_id,
        cycle_index=int(cycle_index),
        region_id=region_id,
        source_timestamp_s=float(source_snapshot.timestamp_s),
        scenario_config_sha256=scenario_config_sha256,
        initial_state_sha256=initial_state_sha256,
        communication_schedule_sha256=communication_schedule_sha256,
        fault_schedule_sha256=fault_schedule_sha256,
        source_snapshot_payload_sha256=canonical_runtime_payload_sha256(
            source_snapshot
        ),
        formal_decision_payload_sha256=canonical_runtime_payload_sha256(
            formal_decision.to_dict()
        ),
        source_plan_payload_sha256=canonical_runtime_payload_sha256(
            source_plan_source
        ),
        candidate_gate_payload_sha256=candidate_gate.sha256,
    )


def build_region_resource_isolated_plan_consumption_ack(
    *,
    ack_id: str,
    lineage: RegionResourceDegradedScenarioLineage,
    source_plan_source: Mapping[str, Any],
    applied_plan_source: Mapping[str, Any],
    acknowledged_at_s: float,
    control_applied_binding_count: int,
    accepted: bool = True,
    fully_consumed_by_isolated_world: bool = True,
    network_partition_observed: bool = False,
) -> RegionResourceIsolatedPlanConsumptionAck:
    """Serialize a receipt after main applied the selected plan to its clone.

    ``source_plan_source`` must be the formal-authority plan bound into
    ``lineage``.  ``applied_plan_source`` is either its strictly newer
    executable successor or the exact same execution identity represented as
    an explicit refresh.  This constructor records the caller's values; the
    verifier enforces that transition and all owner/epoch/lease fences.
    """

    source_plan = _parse_plan(source_plan_source, "source_plan")
    applied_plan = _parse_plan(applied_plan_source, "applied_plan")
    return RegionResourceIsolatedPlanConsumptionAck(
        ack_id=ack_id,
        source_lineage_sha256=lineage.sha256,
        arm_id=lineage.arm_id,
        cycle_index=lineage.cycle_index,
        acknowledged_at_s=float(acknowledged_at_s),
        accepted=accepted,
        status_code=(
            "accepted_by_isolated_simulation"
            if accepted
            else "rejected_by_isolated_simulation"
        ),
        source_plan_id=source_plan.plan_id,
        source_plan_version=source_plan.plan_version,
        applied_plan_id=applied_plan.plan_id,
        applied_plan_version=applied_plan.plan_version,
        applied_plan_payload_sha256=applied_plan.payload_sha256,
        execution_binding_sha256=applied_plan.binding_sha256,
        execution_source=str(applied_plan.execution_source or ""),
        owner_layer=applied_plan.owner_layer,
        owner_node_id=applied_plan.owner_node_id,
        authority_epoch=applied_plan.authority_epoch,
        lease_expires_at_s=applied_plan.lease_expires_at_s,
        assignment_count=applied_plan.assignment_count,
        control_applied_binding_count=int(control_applied_binding_count),
        fully_consumed_by_isolated_world=fully_consumed_by_isolated_world,
        network_partition_observed=network_partition_observed,
    )


def build_region_resource_isolated_plan_ack_from_d3_evidence(
    *,
    lineage: RegionResourceDegradedScenarioLineage,
    source_plan_source: Mapping[str, Any],
    applied_plan_source: Mapping[str, Any],
    d3_consumption_evidence_source: Mapping[str, Any] | Any,
    network_partition_observed: bool = False,
) -> RegionResourceIsolatedPlanConsumptionAck:
    """Bridge a validated D3 isolated receipt into the D4 adoption boundary.

    The bridge does not import D3.  It independently checks the stable D3 v1
    serialization and then adds D4 owner/epoch/lease and degraded-lineage
    binding.  It still produces a non-production D4 receipt.
    """

    evidence = _mapping(d3_consumption_evidence_source, "d3_consumption_evidence")
    _require_exact_keys(
        evidence,
        _D3_ISOLATED_CONSUMPTION_FIELDS,
        "d3_consumption_evidence",
    )
    if evidence.get("schema_version") != D3_ISOLATED_PLAN_CONSUMPTION_EVIDENCE_SCHEMA:
        raise ValueError("unsupported D3 isolated consumption schema")
    if evidence.get("evidence_kind") != D3_ISOLATED_PLAN_CONSUMPTION_EVIDENCE_KIND:
        raise ValueError("unsupported D3 isolated consumption evidence kind")
    if (
        evidence.get("accepted") is not True
        or evidence.get("isolated_plan_applied") is not True
        or evidence.get("status")
        != D3_ISOLATED_PLAN_CONSUMPTION_ACCEPTED_STATUS
    ):
        raise ValueError("D3 isolated plan was not accepted and applied")
    forbidden_true = (
        "production_runtime_ack",
        "control_applied_to_production_world",
        "physical_outcome_available",
        "reward_available",
        "causal_evidence_available",
        "ppo_enabled",
        "online_assist_enabled",
        "online_authority_enabled",
    )
    if any(evidence.get(name) is not False for name in forbidden_true):
        raise ValueError("D3 isolated evidence claims production, outcome, or authority")
    if (
        evidence.get("isolated_simulation_only") is not True
        or evidence.get("rule_fallback_enabled") is not True
    ):
        raise ValueError("D3 isolated evidence lacks isolation or deterministic fallback")

    source_plan = _parse_plan(source_plan_source, "source_plan")
    applied_plan = _parse_plan(applied_plan_source, "applied_plan")
    for name in (
        "experiment_id",
        "experiment_version",
        "pair_id",
        "isolation_id",
        "plan_schema_version",
    ):
        _text(evidence.get(name), f"d3_consumption_evidence.{name}")
    if evidence.get("arm_kind") not in {"control", "treatment"}:
        raise ValueError("D3 isolated evidence arm_kind is invalid")
    if (
        _text(evidence.get("arm_id"), "d3_consumption_evidence.arm_id")
        != lineage.arm_id
        or _nonnegative_int(
            evidence.get("seed"), "d3_consumption_evidence.seed"
        )
        != lineage.seed
        or _nonnegative_int(
            evidence.get("rollout_cycle"),
            "d3_consumption_evidence.rollout_cycle",
        )
        != lineage.cycle_index
    ):
        raise ValueError("D3 isolated evidence belongs to another arm, seed, or cycle")
    if (
        _text(evidence.get("plan_id"), "d3_consumption_evidence.plan_id")
        != applied_plan.plan_id
        or _nonnegative_int(
            evidence.get("plan_version"),
            "d3_consumption_evidence.plan_version",
        )
        != applied_plan.plan_version
        or str(evidence.get("plan_payload_sha256", "")).lower()
        != applied_plan.payload_sha256
        or not _same_time(
            _finite_nonnegative(
                evidence.get("plan_created_at_s"),
                "d3_consumption_evidence.plan_created_at_s",
            ),
            applied_plan.created_at_s,
        )
    ):
        raise ValueError("D3 isolated evidence does not match the applied plan")
    assignment_count = _nonnegative_int(
        evidence.get("assignment_count"),
        "d3_consumption_evidence.assignment_count",
    )
    binding_count = _nonnegative_int(
        evidence.get("binding_count"),
        "d3_consumption_evidence.binding_count",
    )
    if (
        assignment_count != applied_plan.assignment_count
        or binding_count != assignment_count
    ):
        raise ValueError("D3 isolated evidence has incomplete bindings")
    for name in (
        "consumption_id",
        "arm_spec_sha256",
        "execution_receipt_sha256",
        "source_snapshot_lineage_sha256",
        "binding_inventory_sha256",
    ):
        value = evidence.get(name)
        if name == "consumption_id":
            _text(value, f"d3_consumption_evidence.{name}")
        else:
            _require_sha256(str(value), f"d3_consumption_evidence.{name}")
    source_lineage = _mapping(
        evidence.get("source_snapshot_lineage"),
        "d3_consumption_evidence.source_snapshot_lineage",
    )
    _require_exact_keys(
        source_lineage,
        _D3_ISOLATED_SOURCE_LINEAGE_FIELDS,
        "d3_consumption_evidence.source_snapshot_lineage",
    )
    if canonical_runtime_payload_sha256(source_lineage) != str(
        evidence["source_snapshot_lineage_sha256"]
    ).lower():
        raise ValueError("D3 isolated source lineage SHA256 is invalid")
    consumed_at_s = _finite_nonnegative(
        evidence.get("consumption_timestamp_s"),
        "d3_consumption_evidence.consumption_timestamp_s",
    )
    valid_until_s = _finite_nonnegative(
        evidence.get("plan_valid_until_s"),
        "d3_consumption_evidence.plan_valid_until_s",
    )
    if (
        consumed_at_s < applied_plan.created_at_s
        or consumed_at_s > valid_until_s
        or valid_until_s > applied_plan.lease_expires_at_s
    ):
        raise ValueError("D3 isolated consumption exceeds its validity window")
    identity = {
        "experiment_id": evidence["experiment_id"],
        "experiment_version": evidence["experiment_version"],
        "pair_id": evidence["pair_id"],
        "seed": evidence["seed"],
        "arm_id": evidence["arm_id"],
        "arm_kind": evidence["arm_kind"],
        "isolation_id": evidence["isolation_id"],
        "plan_id": evidence["plan_id"],
        "plan_version": evidence["plan_version"],
        "plan_payload_sha256": evidence["plan_payload_sha256"],
    }
    expected_consumption_id = (
        "d3-isolated-consumption-"
        f"{canonical_runtime_payload_sha256(identity)[:24]}"
    )
    if evidence["consumption_id"] != expected_consumption_id:
        raise ValueError("D3 isolated consumption id is invalid")

    return build_region_resource_isolated_plan_consumption_ack(
        ack_id=_text(
            evidence.get("consumption_id"),
            "d3_consumption_evidence.consumption_id",
        ),
        lineage=lineage,
        source_plan_source=source_plan.payload,
        applied_plan_source=applied_plan.payload,
        acknowledged_at_s=consumed_at_s,
        control_applied_binding_count=binding_count,
        accepted=True,
        fully_consumed_by_isolated_world=True,
        network_partition_observed=network_partition_observed,
    )


def _validate_scenario_and_lineage(
    *,
    lineage: RegionResourceDegradedScenarioLineage,
    source_snapshot: RegionalFailoverSnapshot,
    formal_decision: RegionalFailoverDecision,
    candidate_gate: RegionResourceIsolatedCandidateGate,
    source_plan: _PlanView,
) -> RegionalRegionDecision:
    if "nominal" in lineage.scenario_id.strip().lower():
        _fail(
            RegionResourceIsolatedAdoptionCode.NOMINAL_NOT_ELIGIBLE,
            "nominal scenario evidence cannot close degraded-strategy gaps",
        )
    if (
        lineage.scenario_id != source_snapshot.scenario.scenario_name
        or lineage.scenario_version != source_snapshot.scenario.scenario_version
        or not _same_time(lineage.source_timestamp_s, source_snapshot.timestamp_s)
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.SOURCE_LINEAGE_MISMATCH,
            "scenario identity or source timestamp differs from the D4 snapshot",
        )
    expected_hashes = {
        "source_snapshot_payload_sha256": canonical_runtime_payload_sha256(
            source_snapshot
        ),
        "formal_decision_payload_sha256": canonical_runtime_payload_sha256(
            formal_decision.to_dict()
        ),
        "source_plan_payload_sha256": source_plan.payload_sha256,
        "candidate_gate_payload_sha256": candidate_gate.sha256,
    }
    for name, expected in expected_hashes.items():
        if getattr(lineage, name) != expected:
            _fail(
                RegionResourceIsolatedAdoptionCode.SOURCE_LINEAGE_MISMATCH,
                f"degraded scenario source hash differs: {name}",
            )
    if formal_decision.timestamp_s != source_snapshot.timestamp_s:
        _fail(
            RegionResourceIsolatedAdoptionCode.SOURCE_LINEAGE_MISMATCH,
            "formal D4 decision and source snapshot timestamps differ",
        )
    matching = tuple(
        item
        for item in formal_decision.region_decisions
        if item.region_id == lineage.region_id
    )
    if len(matching) != 1:
        _fail(
            RegionResourceIsolatedAdoptionCode.SCENARIO_INVALID,
            "lineage region does not resolve to one formal D4 decision",
        )
    region_decision = matching[0]
    if lineage.region_id in set(source_snapshot.partitioned_region_ids):
        _fail(
            RegionResourceIsolatedAdoptionCode.NETWORK_PARTITION,
            "source region is network partitioned",
        )

    kind = lineage.scenario_kind
    if kind == RegionResourceDegradedScenarioKind.CENTER_FAILED:
        valid = bool(
            source_snapshot.center_health == C2Health.FAILED
            and region_decision.selected_layer == RegionalAuthorityLayer.SECONDARY
            and region_decision.selected_secondary_id
        )
    elif kind == RegionResourceDegradedScenarioKind.CENTER_AND_SECONDARY_FAILED:
        valid = bool(
            source_snapshot.center_health == C2Health.FAILED
            and region_decision.selected_layer == RegionalAuthorityLayer.DISTRIBUTED
            and region_decision.selected_secondary_id is None
        )
    else:
        valid = bool(
            source_snapshot.center_health != C2Health.FAILED
            and region_decision.selected_layer == RegionalAuthorityLayer.CENTER
            and region_decision.action
            in {
                RegionalAction.REQUEST_CENTER_REPLAN,
                RegionalAction.REQUEST_SECONDARY_ASSIST,
            }
            and region_decision.risk_factors
        )
    if not valid:
        _fail(
            RegionResourceIsolatedAdoptionCode.SCENARIO_INVALID,
            f"D4 snapshot/decision does not prove scenario {kind.value}",
        )
    if kind != RegionResourceDegradedScenarioKind.ACTIVE_RISK and (
        not region_decision.execution_allowed
        or region_decision.fail_closed
        or region_decision.action
        not in {
            RegionalAction.DEGRADE_TO_SECONDARY,
            RegionalAction.DEGRADE_TO_DISTRIBUTED,
        }
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.FORMAL_DECISION_REJECTED,
            "passive degraded authority lacks complete ACK/commit evidence",
        )
    ownership = region_decision.ownership
    if (
        ownership.plan_id != source_plan.plan_id
        or ownership.plan_version != source_plan.plan_version
        or ownership.owner_layer.value != source_plan.owner_layer
        or ownership.owner_id != source_plan.owner_node_id
        or ownership.epoch != source_plan.authority_epoch
        or not _same_time(ownership.lease_expires_at_s, source_plan.lease_expires_at_s)
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.SOURCE_LINEAGE_MISMATCH,
            "source D3 plan does not match the formal D4 regional authority",
        )
    if lineage.source_timestamp_s >= source_plan.lease_expires_at_s:
        _fail(
            RegionResourceIsolatedAdoptionCode.AUTHORITY_LEASE_EXPIRED,
            "formal D4 source authority lease is already expired",
        )
    return region_decision


def _validate_plan_transition(
    *,
    lineage: RegionResourceDegradedScenarioLineage,
    gate: RegionResourceIsolatedCandidateGate,
    region_decision: RegionalRegionDecision,
    source_plan: _PlanView,
    applied_plan: _PlanView,
    ack: RegionResourceIsolatedPlanConsumptionAck,
) -> RegionResourceIsolatedAdoptionKind:
    if (
        not ack.accepted
        or ack.status_code != "accepted_by_isolated_simulation"
        or not ack.fully_consumed_by_isolated_world
        or ack.control_applied_binding_count != ack.assignment_count
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.ACK_INVALID,
            "isolated world did not fully accept and consume every plan binding",
        )
    if ack.network_partition_observed:
        _fail(
            RegionResourceIsolatedAdoptionCode.NETWORK_PARTITION,
            "isolated receipt observed a network partition",
        )
    if (
        ack.source_lineage_sha256 != lineage.sha256
        or ack.arm_id != lineage.arm_id
        or ack.cycle_index != lineage.cycle_index
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.SOURCE_LINEAGE_MISMATCH,
            "isolated receipt is bound to another lineage, arm, or cycle",
        )
    if (
        ack.source_plan_id != source_plan.plan_id
        or ack.source_plan_version != source_plan.plan_version
        or ack.applied_plan_id != applied_plan.plan_id
        or ack.applied_plan_version != applied_plan.plan_version
        or ack.applied_plan_payload_sha256 != applied_plan.payload_sha256
        or ack.execution_binding_sha256 != applied_plan.binding_sha256
        or ack.assignment_count != applied_plan.assignment_count
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.PLAN_BINDING_MISMATCH,
            "isolated receipt does not match its source/applied plan and bindings",
        )
    if ack.acknowledged_at_s < max(
        applied_plan.created_at_s, applied_plan.timestamp_s
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.TIMESTAMP_INVALID,
            "isolated receipt precedes the applied plan",
        )

    ownership = region_decision.ownership
    if (
        applied_plan.owner_layer != ownership.owner_layer.value
        or applied_plan.owner_node_id != ownership.owner_id
        or ack.owner_layer != applied_plan.owner_layer
        or ack.owner_node_id != applied_plan.owner_node_id
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.AUTHORITY_OWNER_MISMATCH,
            "applied plan or receipt owner differs from formal D4 authority",
        )
    if (
        applied_plan.authority_epoch != ownership.epoch
        or ack.authority_epoch != ownership.epoch
        or applied_plan.authority_epoch < source_plan.authority_epoch
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.AUTHORITY_EPOCH_STALE,
            "applied plan or receipt carries a stale authority epoch",
        )
    if (
        not _same_time(applied_plan.lease_expires_at_s, ownership.lease_expires_at_s)
        or not _same_time(ack.lease_expires_at_s, ownership.lease_expires_at_s)
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.AUTHORITY_LEASE_MISMATCH,
            "applied plan or receipt lease differs from formal D4 authority",
        )
    if ack.acknowledged_at_s >= ownership.lease_expires_at_s:
        _fail(
            RegionResourceIsolatedAdoptionCode.AUTHORITY_LEASE_EXPIRED,
            "formal D4 authority lease expired before isolated acknowledgement",
        )
    if not applied_plan.plan_published:
        _fail(
            RegionResourceIsolatedAdoptionCode.PLAN_SCHEMA_INVALID,
            "applied D3 plan is not marked as published",
        )
    if applied_plan.source_lineage_sha256 != lineage.sha256:
        _fail(
            RegionResourceIsolatedAdoptionCode.SOURCE_LINEAGE_MISMATCH,
            "applied plan metadata does not bind the degraded source lineage",
        )
    if applied_plan.timestamp_s < lineage.source_timestamp_s:
        _fail(
            RegionResourceIsolatedAdoptionCode.TIMESTAMP_INVALID,
            "applied plan evaluation predates the degraded source frame",
        )

    same_identity = bool(
        source_plan.plan_id == applied_plan.plan_id
        and source_plan.plan_version == applied_plan.plan_version
    )
    if same_identity:
        if (
            applied_plan.execution_signature_changed
            or (applied_plan.plan_refresh_only, applied_plan.evaluation_refresh_only)
            not in {(True, False), (False, True)}
        ):
            _fail(
                RegionResourceIsolatedAdoptionCode.REFRESH_FLAGS_INVALID,
                "same-generation receipt requires one explicit refresh-only flag",
            )
        if (
            applied_plan.binding_sha256 != source_plan.binding_sha256
            or applied_plan.unassigned_inventory_sha256
            != source_plan.unassigned_inventory_sha256
            or applied_plan.owner_layer != source_plan.owner_layer
            or applied_plan.owner_node_id != source_plan.owner_node_id
            or applied_plan.authority_epoch != source_plan.authority_epoch
            or not _same_time(
                applied_plan.lease_expires_at_s, source_plan.lease_expires_at_s
            )
            or not _same_time(applied_plan.created_at_s, source_plan.created_at_s)
        ):
            _fail(
                RegionResourceIsolatedAdoptionCode.REFRESH_BINDINGS_CHANGED,
                "evaluation refresh changed execution, unassigned, or authority bindings",
            )
        _validate_candidate_plan_binding(
            gate,
            applied_plan,
            ack,
            evaluation_refresh=True,
        )
        return RegionResourceIsolatedAdoptionKind.EVALUATION_REFRESH_APPLIED

    if (
        applied_plan.plan_id == source_plan.plan_id
        or applied_plan.plan_version <= source_plan.plan_version
        or not applied_plan.execution_signature_changed
        or applied_plan.plan_refresh_only
        or applied_plan.evaluation_refresh_only
        or applied_plan.created_at_s < lineage.source_timestamp_s
        or applied_plan.created_at_s <= source_plan.created_at_s
    ):
        _fail(
            RegionResourceIsolatedAdoptionCode.PLAN_NOT_NEW,
            "execution change requires a new plan id, higher version, and new timestamp",
        )
    _validate_candidate_plan_binding(gate, applied_plan, ack)
    return RegionResourceIsolatedAdoptionKind.NEW_EXECUTION_PLAN_APPLIED


def _validate_candidate_plan_binding(
    gate: RegionResourceIsolatedCandidateGate,
    applied_plan: _PlanView,
    ack: RegionResourceIsolatedPlanConsumptionAck,
    *,
    evaluation_refresh: bool = False,
) -> None:
    expected_source = (
        "deterministic_rule_fallback"
        if gate.rule_fallback
        else ("evaluation_refresh" if evaluation_refresh else "candidate")
    )
    if applied_plan.execution_source != expected_source or ack.execution_source != expected_source:
        _fail(
            RegionResourceIsolatedAdoptionCode.CANDIDATE_GATE_INVALID,
            "applied plan source contradicts candidate gate or fallback",
        )
    if gate.rule_fallback:
        if applied_plan.candidate_payload_sha256 is not None:
            _fail(
                RegionResourceIsolatedAdoptionCode.CANDIDATE_GATE_INVALID,
                "rule fallback plan cannot claim a candidate payload",
            )
        return
    if not gate.candidate_considered or not gate.gate_pass:
        _fail(
            RegionResourceIsolatedAdoptionCode.CANDIDATE_GATE_INVALID,
            "candidate plan lacks a considered and passing candidate gate",
        )
    if applied_plan.candidate_payload_sha256 != gate.candidate_payload_sha256:
        _fail(
            RegionResourceIsolatedAdoptionCode.CANDIDATE_GATE_INVALID,
            "applied plan candidate payload differs from the persisted gate",
        )


def _parse_plan(value: Mapping[str, Any], path: str) -> _PlanView:
    payload = _mapping(value, path)
    plan_id = _text(_required(payload, "plan_id", path), f"{path}.plan_id")
    plan_version = _nonnegative_int(
        _required(payload, "plan_version", path), f"{path}.plan_version"
    )
    created_at_s = _finite_nonnegative(
        _required(payload, "created_at", path), f"{path}.created_at"
    )
    timestamp_s = _finite_nonnegative(
        _required(payload, "timestamp", path), f"{path}.timestamp"
    )
    metadata = _mapping(_required(payload, "metadata", path), f"{path}.metadata")
    owner_layer = _text(
        _required(metadata, "active_plan_owner", f"{path}.metadata"),
        f"{path}.metadata.active_plan_owner",
    ).lower()
    if owner_layer not in {
        RegionalAuthorityLayer.CENTER.value,
        RegionalAuthorityLayer.SECONDARY.value,
        RegionalAuthorityLayer.DISTRIBUTED.value,
    }:
        raise ValueError(f"unsupported plan owner layer: {owner_layer}")
    owner_node_id = _text(
        _required(metadata, "owner_node_id", f"{path}.metadata"),
        f"{path}.metadata.owner_node_id",
    )
    authority_epoch = _nonnegative_int(
        _required(metadata, "authority_epoch", f"{path}.metadata"),
        f"{path}.metadata.authority_epoch",
    )
    lease_expires_at_s = _finite_nonnegative(
        _required(metadata, "lease_expires_at_s", f"{path}.metadata"),
        f"{path}.metadata.lease_expires_at_s",
    )
    current_plan_id = _text(
        _required(metadata, "current_plan_id", f"{path}.metadata"),
        f"{path}.metadata.current_plan_id",
    )
    current_plan_version = _nonnegative_int(
        _required(metadata, "current_plan_version", f"{path}.metadata"),
        f"{path}.metadata.current_plan_version",
    )
    identity_created_at_s = _finite_nonnegative(
        _required(metadata, "identity_created_at_s", f"{path}.metadata"),
        f"{path}.metadata.identity_created_at_s",
    )
    last_evaluated_at_s = _finite_nonnegative(
        _required(metadata, "last_evaluated_at_s", f"{path}.metadata"),
        f"{path}.metadata.last_evaluated_at_s",
    )
    if (
        current_plan_id != plan_id
        or current_plan_version != plan_version
        or not _same_time(identity_created_at_s, created_at_s)
        or not _same_time(last_evaluated_at_s, timestamp_s)
    ):
        raise ValueError(f"{path} identity/evaluation metadata is inconsistent")
    assignment_count = _nonnegative_int(
        _required(payload, "assignment_count", path), f"{path}.assignment_count"
    )
    assignments = _sequence(_required(payload, "assignments", path), f"{path}.assignments")
    if assignment_count != len(assignments):
        raise ValueError(f"{path}.assignment_count differs from assignments")
    unassigned = _sequence(
        payload.get("unassigned_global_track_ids", ()),
        f"{path}.unassigned_global_track_ids",
    )
    normalized_unassigned = tuple(sorted(_text(item, path) for item in unassigned))
    if len(normalized_unassigned) != len(set(normalized_unassigned)):
        raise ValueError(f"{path}.unassigned_global_track_ids contains duplicates")
    execution_source = metadata.get("d4_isolated_execution_source")
    if execution_source is not None:
        execution_source = _text(
            execution_source, f"{path}.metadata.d4_isolated_execution_source"
        )
    lineage_sha = metadata.get("d4_source_lineage_sha256")
    if lineage_sha is not None:
        lineage_sha = str(lineage_sha).lower()
        _require_sha256(lineage_sha, f"{path}.metadata.d4_source_lineage_sha256")
    candidate_sha = metadata.get("d4_candidate_payload_sha256")
    if candidate_sha is not None:
        candidate_sha = str(candidate_sha).lower()
        _require_sha256(candidate_sha, f"{path}.metadata.d4_candidate_payload_sha256")
    return _PlanView(
        payload=payload,
        payload_sha256=canonical_runtime_payload_sha256(payload),
        plan_id=plan_id,
        plan_version=plan_version,
        created_at_s=created_at_s,
        timestamp_s=timestamp_s,
        owner_layer=owner_layer,
        owner_node_id=owner_node_id,
        authority_epoch=authority_epoch,
        lease_expires_at_s=lease_expires_at_s,
        execution_signature_changed=_bool(
            _required(metadata, "execution_signature_changed", f"{path}.metadata"),
            f"{path}.metadata.execution_signature_changed",
        ),
        plan_refresh_only=_bool(
            _required(metadata, "plan_refresh_only", f"{path}.metadata"),
            f"{path}.metadata.plan_refresh_only",
        ),
        evaluation_refresh_only=_bool(
            _required(metadata, "evaluation_refresh_only", f"{path}.metadata"),
            f"{path}.metadata.evaluation_refresh_only",
        ),
        plan_published=_bool(
            _required(metadata, "plan_published", f"{path}.metadata"),
            f"{path}.metadata.plan_published",
        ),
        execution_source=execution_source,
        source_lineage_sha256=lineage_sha,
        candidate_payload_sha256=candidate_sha,
        assignment_count=assignment_count,
        binding_sha256=canonical_execution_binding_sha256(payload, path=path),
        unassigned_inventory_sha256=canonical_runtime_payload_sha256(
            normalized_unassigned
        ),
    )


def _parse_lineage(
    value: RegionResourceDegradedScenarioLineage | Mapping[str, Any],
) -> RegionResourceDegradedScenarioLineage:
    if isinstance(value, RegionResourceDegradedScenarioLineage):
        return value
    return RegionResourceDegradedScenarioLineage.from_mapping(
        _mapping(value, "scenario_lineage")
    )


def _parse_candidate_gate(
    value: RegionResourceIsolatedCandidateGate | Mapping[str, Any],
) -> RegionResourceIsolatedCandidateGate:
    if isinstance(value, RegionResourceIsolatedCandidateGate):
        return value
    return RegionResourceIsolatedCandidateGate.from_mapping(
        _mapping(value, "candidate_gate")
    )


def _parse_ack(
    value: RegionResourceIsolatedPlanConsumptionAck | Mapping[str, Any],
) -> RegionResourceIsolatedPlanConsumptionAck:
    if isinstance(value, RegionResourceIsolatedPlanConsumptionAck):
        return value
    return RegionResourceIsolatedPlanConsumptionAck.from_mapping(
        _mapping(value, "isolated_plan_ack")
    )


def _available_evidence(
    context: _EvidenceContext,
    adoption_kind: RegionResourceIsolatedAdoptionKind,
) -> RegionResourceIsolatedAdoptionEvidence:
    new_plan = (
        adoption_kind == RegionResourceIsolatedAdoptionKind.NEW_EXECUTION_PLAN_APPLIED
    )
    refresh = (
        adoption_kind == RegionResourceIsolatedAdoptionKind.EVALUATION_REFRESH_APPLIED
    )
    candidate_adopted = bool(
        new_plan
        and context.candidate_considered
        and context.gate_pass
        and not context.rule_fallback
    )
    if candidate_adopted:
        code = RegionResourceIsolatedAdoptionCode.CANDIDATE_ADOPTED
        reason = (
            "degraded scenario, candidate gate, strict plan generation, authority "
            "fence, binding hash, and isolated consumption receipt are consistent"
        )
    elif refresh:
        code = RegionResourceIsolatedAdoptionCode.EVALUATION_REFRESH
        reason = (
            "isolated receipt proves an unchanged-binding evaluation refresh only"
        )
    else:
        code = RegionResourceIsolatedAdoptionCode.RULE_FALLBACK_APPLIED
        reason = (
            "candidate was not adopted; isolated world consumed the deterministic "
            "rule fallback under the current authority fence"
        )
    return RegionResourceIsolatedAdoptionEvidence(
        code=code.value,
        reason=reason,
        new_execution_plan_applied=new_plan,
        evaluation_refresh_applied=refresh,
        isolated_plan_consumption_ack_available=True,
        isolated_candidate_adoption_available=candidate_adopted,
        adoption_kind=adoption_kind.value,
        rejection_reasons=(),
        **asdict(context),
    )


def _rejected_evidence(
    context: _EvidenceContext,
    error: _ValidationFailure,
) -> RegionResourceIsolatedAdoptionEvidence:
    return RegionResourceIsolatedAdoptionEvidence(
        code=error.code.value,
        reason=error.reason,
        rejection_reasons=(error.code.value,),
        **asdict(context),
    )


def _fail(code: RegionResourceIsolatedAdoptionCode, reason: str) -> None:
    raise _ValidationFailure(code, reason)


def _required(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise ValueError(f"required field is missing: {path}.{key}")
    return mapping[key]


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    raise TypeError(f"{path} must be a mapping")


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{path} must be a sequence")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{path} must be non-empty text")
    return value.strip()


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{path} must be boolean")
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{path} must be a non-negative integer")
    return int(value)


def _finite_nonnegative(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{path} must be numeric")
    result = float(value)
    if not isfinite(result) or result < 0.0:
        raise ValueError(f"{path} must be finite and non-negative")
    return result


def _finite_unit_interval(value: Any, path: str) -> float:
    result = _finite_nonnegative(value, path)
    if result > 1.0:
        raise ValueError(f"{path} must be in [0, 1]")
    return result


def _require_sha256(value: str, path: str) -> None:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{path} must be a SHA256 hex digest")


def _require_exact_keys(
    value: Mapping[str, Any], expected: Mapping[str, Any], path: str
) -> None:
    actual = set(value)
    required = set(expected)
    if actual != required:
        raise ValueError(
            f"{path} keys mismatch: missing={sorted(required - actual)}, "
            f"extra={sorted(actual - required)}"
        )


def _unique_text(values: Sequence[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _same_time(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= 1.0e-9
