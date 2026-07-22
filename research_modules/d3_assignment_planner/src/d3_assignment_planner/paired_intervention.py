"""Fail-closed contract for reserved-seed D3 paired interventions.

The contract describes and audits an offline simulation experiment.  It does
not enable PPO, online learning assistance, or assignment authority.  D3 owns
the paired input and plan-lineage declaration; D6 remains the sole owner of
outcome, counterfactual, and causal sidecars.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any

from .runtime_plan_ack import (
    D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
    AssignmentPlanRuntimeAckEvidence,
)
from .runtime_reward_evidence import (
    D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1,
)
from .shadow_evaluation import SHADOW_EVALUATION_SCHEMA_V2


PAIRED_INTERVENTION_ARM_SCHEMA_V1 = "d3.paired-intervention-arm.v1"
PAIRED_INTERVENTION_SEED_PAIR_SCHEMA_V1 = "d3.paired-intervention-seed-pair.v1"
PAIRED_INTERVENTION_SPECIFICATION_SCHEMA_V1 = (
    "d3.paired-intervention-specification.v1"
)
PAIRED_INTERVENTION_EXECUTION_RECEIPT_SCHEMA_V1 = (
    "d3.paired-intervention-execution-receipt.v1"
)
PAIRED_INTERVENTION_RUNTIME_ACK_REFERENCE_SCHEMA_V1 = (
    "d3.paired-intervention-runtime-ack-reference.v1"
)
PAIRED_INTERVENTION_MANIFEST_SCHEMA_V1 = "d3.paired-intervention-manifest.v1"
PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1 = (
    "d3.reserved-evaluation-seeds-1000-1019.v1"
)
PAIRED_INTERVENTION_RESERVED_SEEDS_V1 = tuple(range(1000, 1020))

CONTROL_ARM = "control"
TREATMENT_ARM = "treatment"
CONTROL_PLANNER_PATH = "rule_cost_then_hungarian"
TREATMENT_PLANNER_PATH = "bounded_residual_then_hungarian"
OFFLINE_INTERVENTION_SCOPE = "offline_simulation_intervention_arm"
D6_SIDECAR_OWNER = "D6"

_HEX_DIGITS = frozenset("0123456789abcdef")
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "offline_truth_labels",
    }
)

_ARM_FIELDS = frozenset(
    {
        "schema_version",
        "arm_id",
        "arm_kind",
        "seed",
        "isolation_id",
        "intervention_scope",
        "planner_path",
        "scenario_version",
        "scenario_config_sha256",
        "initial_world_state_sha256",
        "observation_input_snapshot_sha256",
        "input_snapshot_schema_version",
        "d1_d2_lineage_contract_version",
        "d1_d2_lineage_contract_sha256",
        "rule_cost_profile_version",
        "rule_cost_config_sha256",
        "d3_bundle_version",
        "d3_bundle_sha256",
        "d3_bundle_frozen",
        "threshold_version",
        "threshold_config_sha256",
        "threshold_frozen",
        "safety_shell_version",
        "safety_shell_config_sha256",
        "source_plan_id",
        "source_plan_version",
        "expected_previous_plan_version",
        "current_plan_version",
        "source_plan_created_at_s",
        "intervention_timestamp_s",
        "plan_valid_until_s",
        "learning_cost_intervention_enabled",
        "ppo_enabled",
        "online_assist_enabled",
        "online_authority_enabled",
        "rule_fallback_enabled",
    }
)
_PAIR_FIELDS = frozenset(
    {"schema_version", "pair_id", "seed", "control", "treatment"}
)
_SPEC_FIELDS = frozenset(
    {
        "schema_version",
        "experiment_id",
        "experiment_version",
        "reserved_seed_policy_version",
        "reserved_seeds",
        "paired_evaluator_schema_version",
        "runtime_ack_evidence_schema_version",
        "runtime_reward_evidence_schema_version",
        "d6_sidecar_owner",
        "ppo_enabled",
        "online_assist_enabled",
        "online_authority_enabled",
        "rule_fallback_enabled",
        "pairs",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "pair_id",
        "seed",
        "arm_kind",
        "arm_spec_sha256",
        "paired_evaluator_schema_version",
        "paired_evaluator_report_sha256",
        "input_snapshot_sha256",
        "rule_cost_matrix_sha256",
        "action_mask_sha256",
        "planner_path",
        "source_plan_version",
        "expected_previous_plan_version",
        "current_plan_version",
        "output_plan_id",
        "output_plan_version",
        "output_plan_payload_sha256",
        "isolated_simulation",
        "learning_cost_applied",
        "rule_matrix_unchanged",
        "deterministic_action_mask_enforced",
        "reachability_gate_enforced",
        "capacity_gate_enforced",
        "version_gate_enforced",
        "hysteresis_gate_enforced",
        "safety_gate_enforced",
        "rule_fallback_available",
        "rule_fallback_applied",
        "fallback_reason",
        "hysteresis_decision",
        "inference_elapsed_ms",
        "nonfinite_value_count",
        "online_label_key_count",
        "global_track_id_rewrite_count",
    }
)
_ACK_REFERENCE_FIELDS = frozenset(
    {
        "schema_version",
        "pair_id",
        "seed",
        "arm_kind",
        "execution_receipt_sha256",
        "source_ack_evidence_schema_version",
        "source_ack_evidence_sha256",
        "decision_id",
        "ack_timestamp",
        "plan_id",
        "plan_version",
        "accepted",
        "status_code",
        "source_plan_bus_sequence",
        "source_plan_payload_sha256",
        "source_guidance_bus_sequence",
        "source_guidance_payload_sha256",
        "fully_bound_to_guidance",
        "control_applied_binding_count",
        "d3_learning_mode",
        "d3_learning_applied",
        "physical_outcome_available",
        "reward_available",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "specification",
        "specification_sha256",
        "execution_receipts",
        "runtime_ack_references",
        "availability",
        "admission",
        "audit",
        "manifest_sha256",
    }
)

_PAIR_EQUIVALENCE_FIELDS = (
    "seed",
    "scenario_version",
    "scenario_config_sha256",
    "initial_world_state_sha256",
    "observation_input_snapshot_sha256",
    "input_snapshot_schema_version",
    "d1_d2_lineage_contract_version",
    "d1_d2_lineage_contract_sha256",
    "rule_cost_profile_version",
    "rule_cost_config_sha256",
    "d3_bundle_version",
    "d3_bundle_sha256",
    "d3_bundle_frozen",
    "threshold_version",
    "threshold_config_sha256",
    "threshold_frozen",
    "safety_shell_version",
    "safety_shell_config_sha256",
    "source_plan_id",
    "source_plan_version",
    "expected_previous_plan_version",
    "current_plan_version",
    "source_plan_created_at_s",
    "intervention_timestamp_s",
    "plan_valid_until_s",
    "ppo_enabled",
    "online_assist_enabled",
    "online_authority_enabled",
    "rule_fallback_enabled",
)


class PairedInterventionContractError(ValueError):
    """Stable fail-closed error raised by the paired contract."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        self.reason = self.code
        super().__init__(message or self.code)


@dataclass(frozen=True, slots=True)
class PairedInterventionArmSpecification:
    """One isolated control or treatment arm with complete input lineage."""

    arm_id: str
    arm_kind: str
    seed: int
    isolation_id: str
    intervention_scope: str
    planner_path: str
    scenario_version: str
    scenario_config_sha256: str
    initial_world_state_sha256: str
    observation_input_snapshot_sha256: str
    input_snapshot_schema_version: str
    d1_d2_lineage_contract_version: str
    d1_d2_lineage_contract_sha256: str
    rule_cost_profile_version: str
    rule_cost_config_sha256: str
    d3_bundle_version: str
    d3_bundle_sha256: str
    d3_bundle_frozen: bool
    threshold_version: str
    threshold_config_sha256: str
    threshold_frozen: bool
    safety_shell_version: str
    safety_shell_config_sha256: str
    source_plan_id: str
    source_plan_version: int
    expected_previous_plan_version: int
    current_plan_version: int
    source_plan_created_at_s: float
    intervention_timestamp_s: float
    plan_valid_until_s: float
    learning_cost_intervention_enabled: bool
    ppo_enabled: bool = False
    online_assist_enabled: bool = False
    online_authority_enabled: bool = False
    rule_fallback_enabled: bool = True
    schema_version: str = PAIRED_INTERVENTION_ARM_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != PAIRED_INTERVENTION_ARM_SCHEMA_V1:
            _fail("arm_schema_unsupported")
        for name in (
            "arm_id",
            "isolation_id",
            "scenario_version",
            "input_snapshot_schema_version",
            "d1_d2_lineage_contract_version",
            "rule_cost_profile_version",
            "d3_bundle_version",
            "threshold_version",
            "safety_shell_version",
            "source_plan_id",
        ):
            _required_text(getattr(self, name), name)
        if self.arm_kind not in {CONTROL_ARM, TREATMENT_ARM}:
            _fail("arm_kind_invalid")
        if self.seed not in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
            _fail("reserved_seed_catalog_mismatch")
        if self.intervention_scope != OFFLINE_INTERVENTION_SCOPE:
            _fail("intervention_scope_not_isolated")
        expected_path = (
            CONTROL_PLANNER_PATH
            if self.arm_kind == CONTROL_ARM
            else TREATMENT_PLANNER_PATH
        )
        if self.planner_path != expected_path:
            _fail("planner_path_mismatch")
        for name in (
            "scenario_config_sha256",
            "initial_world_state_sha256",
            "observation_input_snapshot_sha256",
            "d1_d2_lineage_contract_sha256",
            "rule_cost_config_sha256",
            "d3_bundle_sha256",
            "threshold_config_sha256",
            "safety_shell_config_sha256",
        ):
            _sha256_text(getattr(self, name), name)
        for name in (
            "d3_bundle_frozen",
            "threshold_frozen",
            "learning_cost_intervention_enabled",
            "ppo_enabled",
            "online_assist_enabled",
            "online_authority_enabled",
            "rule_fallback_enabled",
        ):
            _strict_bool(getattr(self, name), name)
        if not self.d3_bundle_frozen:
            _fail("d3_bundle_not_frozen")
        if not self.threshold_frozen:
            _fail("threshold_not_frozen")
        if self.ppo_enabled:
            _fail("ppo_must_remain_disabled")
        if self.online_assist_enabled:
            _fail("online_assist_must_remain_disabled")
        if self.online_authority_enabled:
            _fail("online_authority_must_remain_disabled")
        if not self.rule_fallback_enabled:
            _fail("rule_fallback_disabled")
        expected_intervention = self.arm_kind == TREATMENT_ARM
        if self.learning_cost_intervention_enabled is not expected_intervention:
            _fail("arm_learning_intervention_mismatch")
        versions = (
            _nonnegative_int(self.source_plan_version, "source_plan_version"),
            _nonnegative_int(
                self.expected_previous_plan_version,
                "expected_previous_plan_version",
            ),
            _nonnegative_int(self.current_plan_version, "current_plan_version"),
        )
        if len(set(versions)) != 1:
            _fail("stale_plan_version")
        created = _finite(self.source_plan_created_at_s, "source_plan_created_at_s")
        intervention = _finite(
            self.intervention_timestamp_s, "intervention_timestamp_s"
        )
        valid_until = _finite(self.plan_valid_until_s, "plan_valid_until_s")
        if intervention < created or valid_until < created or intervention > valid_until:
            _fail("stale_plan_time_window")

    @property
    def fingerprint(self) -> str:
        return canonical_paired_intervention_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "arm_id": self.arm_id,
            "arm_kind": self.arm_kind,
            "seed": int(self.seed),
            "isolation_id": self.isolation_id,
            "intervention_scope": self.intervention_scope,
            "planner_path": self.planner_path,
            "scenario_version": self.scenario_version,
            "scenario_config_sha256": self.scenario_config_sha256,
            "initial_world_state_sha256": self.initial_world_state_sha256,
            "observation_input_snapshot_sha256": (
                self.observation_input_snapshot_sha256
            ),
            "input_snapshot_schema_version": self.input_snapshot_schema_version,
            "d1_d2_lineage_contract_version": (
                self.d1_d2_lineage_contract_version
            ),
            "d1_d2_lineage_contract_sha256": (
                self.d1_d2_lineage_contract_sha256
            ),
            "rule_cost_profile_version": self.rule_cost_profile_version,
            "rule_cost_config_sha256": self.rule_cost_config_sha256,
            "d3_bundle_version": self.d3_bundle_version,
            "d3_bundle_sha256": self.d3_bundle_sha256,
            "d3_bundle_frozen": self.d3_bundle_frozen,
            "threshold_version": self.threshold_version,
            "threshold_config_sha256": self.threshold_config_sha256,
            "threshold_frozen": self.threshold_frozen,
            "safety_shell_version": self.safety_shell_version,
            "safety_shell_config_sha256": self.safety_shell_config_sha256,
            "source_plan_id": self.source_plan_id,
            "source_plan_version": int(self.source_plan_version),
            "expected_previous_plan_version": int(
                self.expected_previous_plan_version
            ),
            "current_plan_version": int(self.current_plan_version),
            "source_plan_created_at_s": float(self.source_plan_created_at_s),
            "intervention_timestamp_s": float(self.intervention_timestamp_s),
            "plan_valid_until_s": float(self.plan_valid_until_s),
            "learning_cost_intervention_enabled": (
                self.learning_cost_intervention_enabled
            ),
            "ppo_enabled": self.ppo_enabled,
            "online_assist_enabled": self.online_assist_enabled,
            "online_authority_enabled": self.online_authority_enabled,
            "rule_fallback_enabled": self.rule_fallback_enabled,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "PairedInterventionArmSpecification":
        _assert_truth_free(value)
        item = _strict_mapping(value, _ARM_FIELDS, "arm_fields_mismatch")
        return cls(
            arm_id=_required_text(item["arm_id"], "arm_id"),
            arm_kind=_required_text(item["arm_kind"], "arm_kind"),
            seed=_integer(item["seed"], "seed"),
            isolation_id=_required_text(item["isolation_id"], "isolation_id"),
            intervention_scope=_required_text(
                item["intervention_scope"], "intervention_scope"
            ),
            planner_path=_required_text(item["planner_path"], "planner_path"),
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
            observation_input_snapshot_sha256=_sha256_text(
                item["observation_input_snapshot_sha256"],
                "observation_input_snapshot_sha256",
            ),
            input_snapshot_schema_version=_required_text(
                item["input_snapshot_schema_version"],
                "input_snapshot_schema_version",
            ),
            d1_d2_lineage_contract_version=_required_text(
                item["d1_d2_lineage_contract_version"],
                "d1_d2_lineage_contract_version",
            ),
            d1_d2_lineage_contract_sha256=_sha256_text(
                item["d1_d2_lineage_contract_sha256"],
                "d1_d2_lineage_contract_sha256",
            ),
            rule_cost_profile_version=_required_text(
                item["rule_cost_profile_version"], "rule_cost_profile_version"
            ),
            rule_cost_config_sha256=_sha256_text(
                item["rule_cost_config_sha256"], "rule_cost_config_sha256"
            ),
            d3_bundle_version=_required_text(
                item["d3_bundle_version"], "d3_bundle_version"
            ),
            d3_bundle_sha256=_sha256_text(
                item["d3_bundle_sha256"], "d3_bundle_sha256"
            ),
            d3_bundle_frozen=_strict_bool(
                item["d3_bundle_frozen"], "d3_bundle_frozen"
            ),
            threshold_version=_required_text(
                item["threshold_version"], "threshold_version"
            ),
            threshold_config_sha256=_sha256_text(
                item["threshold_config_sha256"], "threshold_config_sha256"
            ),
            threshold_frozen=_strict_bool(
                item["threshold_frozen"], "threshold_frozen"
            ),
            safety_shell_version=_required_text(
                item["safety_shell_version"], "safety_shell_version"
            ),
            safety_shell_config_sha256=_sha256_text(
                item["safety_shell_config_sha256"],
                "safety_shell_config_sha256",
            ),
            source_plan_id=_required_text(item["source_plan_id"], "source_plan_id"),
            source_plan_version=_nonnegative_int(
                item["source_plan_version"], "source_plan_version"
            ),
            expected_previous_plan_version=_nonnegative_int(
                item["expected_previous_plan_version"],
                "expected_previous_plan_version",
            ),
            current_plan_version=_nonnegative_int(
                item["current_plan_version"], "current_plan_version"
            ),
            source_plan_created_at_s=_finite(
                item["source_plan_created_at_s"], "source_plan_created_at_s"
            ),
            intervention_timestamp_s=_finite(
                item["intervention_timestamp_s"], "intervention_timestamp_s"
            ),
            plan_valid_until_s=_finite(
                item["plan_valid_until_s"], "plan_valid_until_s"
            ),
            learning_cost_intervention_enabled=_strict_bool(
                item["learning_cost_intervention_enabled"],
                "learning_cost_intervention_enabled",
            ),
            ppo_enabled=_strict_bool(item["ppo_enabled"], "ppo_enabled"),
            online_assist_enabled=_strict_bool(
                item["online_assist_enabled"], "online_assist_enabled"
            ),
            online_authority_enabled=_strict_bool(
                item["online_authority_enabled"], "online_authority_enabled"
            ),
            rule_fallback_enabled=_strict_bool(
                item["rule_fallback_enabled"], "rule_fallback_enabled"
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class PairedInterventionSeedPair:
    """Exactly one control and one treatment arm for one reserved seed."""

    pair_id: str
    seed: int
    control: PairedInterventionArmSpecification
    treatment: PairedInterventionArmSpecification
    schema_version: str = PAIRED_INTERVENTION_SEED_PAIR_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != PAIRED_INTERVENTION_SEED_PAIR_SCHEMA_V1:
            _fail("seed_pair_schema_unsupported")
        _required_text(self.pair_id, "pair_id")
        if self.seed not in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
            _fail("reserved_seed_catalog_mismatch")
        if self.control.arm_kind != CONTROL_ARM or self.treatment.arm_kind != TREATMENT_ARM:
            _fail("paired_arm_missing_or_swapped")
        if self.control.seed != self.seed or self.treatment.seed != self.seed:
            _fail("paired_seed_mismatch")
        if self.control.isolation_id == self.treatment.isolation_id:
            _fail("arm_isolation_collision")
        mismatches = tuple(
            name
            for name in _PAIR_EQUIVALENCE_FIELDS
            if getattr(self.control, name) != getattr(self.treatment, name)
        )
        if mismatches:
            _fail(
                "paired_input_mismatch",
                "control/treatment differ in: " + ",".join(mismatches),
            )

    @property
    def paired_input_sha256(self) -> str:
        shared = {
            name: getattr(self.control, name) for name in _PAIR_EQUIVALENCE_FIELDS
        }
        return canonical_paired_intervention_sha256(shared)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pair_id": self.pair_id,
            "seed": int(self.seed),
            "control": self.control.to_dict(),
            "treatment": self.treatment.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PairedInterventionSeedPair":
        _assert_truth_free(value)
        item = _strict_mapping(value, _PAIR_FIELDS, "seed_pair_fields_mismatch")
        return cls(
            pair_id=_required_text(item["pair_id"], "pair_id"),
            seed=_integer(item["seed"], "seed"),
            control=PairedInterventionArmSpecification.from_dict(
                _mapping(item["control"], "control")
            ),
            treatment=PairedInterventionArmSpecification.from_dict(
                _mapping(item["treatment"], "treatment")
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class PairedInterventionSpecification:
    """Frozen 20-seed paired intervention specification."""

    experiment_id: str
    experiment_version: str
    reserved_seed_policy_version: str
    reserved_seeds: tuple[int, ...]
    paired_evaluator_schema_version: str
    runtime_ack_evidence_schema_version: str
    runtime_reward_evidence_schema_version: str
    d6_sidecar_owner: str
    ppo_enabled: bool
    online_assist_enabled: bool
    online_authority_enabled: bool
    rule_fallback_enabled: bool
    pairs: tuple[PairedInterventionSeedPair, ...]
    schema_version: str = PAIRED_INTERVENTION_SPECIFICATION_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != PAIRED_INTERVENTION_SPECIFICATION_SCHEMA_V1:
            _fail("specification_schema_unsupported")
        _required_text(self.experiment_id, "experiment_id")
        _required_text(self.experiment_version, "experiment_version")
        if (
            self.reserved_seed_policy_version
            != PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1
        ):
            _fail("reserved_seed_policy_mismatch")
        if tuple(self.reserved_seeds) != PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
            _fail("reserved_seed_catalog_mismatch")
        if self.paired_evaluator_schema_version != SHADOW_EVALUATION_SCHEMA_V2:
            _fail("paired_evaluator_schema_mismatch")
        if (
            self.runtime_ack_evidence_schema_version
            != D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1
        ):
            _fail("runtime_ack_schema_mismatch")
        if (
            self.runtime_reward_evidence_schema_version
            != D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1
        ):
            _fail("runtime_reward_schema_mismatch")
        if self.d6_sidecar_owner != D6_SIDECAR_OWNER:
            _fail("d6_sidecar_owner_mismatch")
        for name in (
            "ppo_enabled",
            "online_assist_enabled",
            "online_authority_enabled",
            "rule_fallback_enabled",
        ):
            _strict_bool(getattr(self, name), name)
        if self.ppo_enabled:
            _fail("ppo_must_remain_disabled")
        if self.online_assist_enabled:
            _fail("online_assist_must_remain_disabled")
        if self.online_authority_enabled:
            _fail("online_authority_must_remain_disabled")
        if not self.rule_fallback_enabled:
            _fail("rule_fallback_disabled")
        pair_seeds = tuple(item.seed for item in self.pairs)
        if len(pair_seeds) != len(set(pair_seeds)):
            _fail("duplicate_seed_pair")
        if tuple(sorted(pair_seeds)) != PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
            _fail("reserved_seed_pair_inventory_mismatch")
        pair_ids = tuple(item.pair_id for item in self.pairs)
        if len(pair_ids) != len(set(pair_ids)):
            _fail("duplicate_pair_id")
        arm_ids = tuple(
            arm.arm_id
            for pair in self.pairs
            for arm in (pair.control, pair.treatment)
        )
        if len(arm_ids) != len(set(arm_ids)):
            _fail("duplicate_arm_id")
        isolation_ids = tuple(
            arm.isolation_id
            for pair in self.pairs
            for arm in (pair.control, pair.treatment)
        )
        if len(isolation_ids) != len(set(isolation_ids)):
            _fail("duplicate_isolation_id")
        for name in (
            "d1_d2_lineage_contract_version",
            "d1_d2_lineage_contract_sha256",
            "rule_cost_profile_version",
            "rule_cost_config_sha256",
            "d3_bundle_version",
            "d3_bundle_sha256",
            "threshold_version",
            "threshold_config_sha256",
            "safety_shell_version",
            "safety_shell_config_sha256",
        ):
            values = {
                getattr(pair.control, name)
                for pair in self.pairs
            }
            if len(values) != 1:
                _fail("experiment_freeze_mismatch", f"not frozen: {name}")

    @property
    def fingerprint(self) -> str:
        return canonical_paired_intervention_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "experiment_version": self.experiment_version,
            "reserved_seed_policy_version": self.reserved_seed_policy_version,
            "reserved_seeds": [int(seed) for seed in self.reserved_seeds],
            "paired_evaluator_schema_version": self.paired_evaluator_schema_version,
            "runtime_ack_evidence_schema_version": (
                self.runtime_ack_evidence_schema_version
            ),
            "runtime_reward_evidence_schema_version": (
                self.runtime_reward_evidence_schema_version
            ),
            "d6_sidecar_owner": self.d6_sidecar_owner,
            "ppo_enabled": self.ppo_enabled,
            "online_assist_enabled": self.online_assist_enabled,
            "online_authority_enabled": self.online_authority_enabled,
            "rule_fallback_enabled": self.rule_fallback_enabled,
            "pairs": [pair.to_dict() for pair in self.pairs],
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "PairedInterventionSpecification":
        _assert_truth_free(value)
        item = _strict_mapping(value, _SPEC_FIELDS, "specification_fields_mismatch")
        return cls(
            experiment_id=_required_text(item["experiment_id"], "experiment_id"),
            experiment_version=_required_text(
                item["experiment_version"], "experiment_version"
            ),
            reserved_seed_policy_version=_required_text(
                item["reserved_seed_policy_version"],
                "reserved_seed_policy_version",
            ),
            reserved_seeds=tuple(
                _integer(seed, "reserved seed")
                for seed in _sequence(item["reserved_seeds"], "reserved_seeds")
            ),
            paired_evaluator_schema_version=_required_text(
                item["paired_evaluator_schema_version"],
                "paired_evaluator_schema_version",
            ),
            runtime_ack_evidence_schema_version=_required_text(
                item["runtime_ack_evidence_schema_version"],
                "runtime_ack_evidence_schema_version",
            ),
            runtime_reward_evidence_schema_version=_required_text(
                item["runtime_reward_evidence_schema_version"],
                "runtime_reward_evidence_schema_version",
            ),
            d6_sidecar_owner=_required_text(
                item["d6_sidecar_owner"], "d6_sidecar_owner"
            ),
            ppo_enabled=_strict_bool(item["ppo_enabled"], "ppo_enabled"),
            online_assist_enabled=_strict_bool(
                item["online_assist_enabled"], "online_assist_enabled"
            ),
            online_authority_enabled=_strict_bool(
                item["online_authority_enabled"], "online_authority_enabled"
            ),
            rule_fallback_enabled=_strict_bool(
                item["rule_fallback_enabled"], "rule_fallback_enabled"
            ),
            pairs=tuple(
                PairedInterventionSeedPair.from_dict(
                    _mapping(pair, "paired seed entry")
                )
                for pair in _sequence(item["pairs"], "pairs")
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class PairedInterventionExecutionReceipt:
    """One arm's execution declaration, bound to the existing paired evaluator."""

    pair_id: str
    seed: int
    arm_kind: str
    arm_spec_sha256: str
    paired_evaluator_schema_version: str
    paired_evaluator_report_sha256: str
    input_snapshot_sha256: str
    rule_cost_matrix_sha256: str
    action_mask_sha256: str
    planner_path: str
    source_plan_version: int
    expected_previous_plan_version: int
    current_plan_version: int
    output_plan_id: str
    output_plan_version: int
    output_plan_payload_sha256: str
    isolated_simulation: bool
    learning_cost_applied: bool
    rule_matrix_unchanged: bool
    deterministic_action_mask_enforced: bool
    reachability_gate_enforced: bool
    capacity_gate_enforced: bool
    version_gate_enforced: bool
    hysteresis_gate_enforced: bool
    safety_gate_enforced: bool
    rule_fallback_available: bool
    rule_fallback_applied: bool
    fallback_reason: str | None
    hysteresis_decision: str
    inference_elapsed_ms: float
    nonfinite_value_count: int
    online_label_key_count: int
    global_track_id_rewrite_count: int
    schema_version: str = PAIRED_INTERVENTION_EXECUTION_RECEIPT_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != PAIRED_INTERVENTION_EXECUTION_RECEIPT_SCHEMA_V1:
            _fail("execution_receipt_schema_unsupported")
        _required_text(self.pair_id, "pair_id")
        _required_text(self.output_plan_id, "output_plan_id")
        _required_text(self.hysteresis_decision, "hysteresis_decision")
        if self.seed not in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
            _fail("reserved_seed_catalog_mismatch")
        if self.arm_kind not in {CONTROL_ARM, TREATMENT_ARM}:
            _fail("arm_kind_invalid")
        expected_path = (
            CONTROL_PLANNER_PATH
            if self.arm_kind == CONTROL_ARM
            else TREATMENT_PLANNER_PATH
        )
        if self.planner_path != expected_path:
            _fail("planner_path_mismatch")
        if self.paired_evaluator_schema_version != SHADOW_EVALUATION_SCHEMA_V2:
            _fail("paired_evaluator_schema_mismatch")
        for name in (
            "arm_spec_sha256",
            "paired_evaluator_report_sha256",
            "input_snapshot_sha256",
            "rule_cost_matrix_sha256",
            "action_mask_sha256",
            "output_plan_payload_sha256",
        ):
            _sha256_text(getattr(self, name), name)
        for name in (
            "isolated_simulation",
            "learning_cost_applied",
            "rule_matrix_unchanged",
            "deterministic_action_mask_enforced",
            "reachability_gate_enforced",
            "capacity_gate_enforced",
            "version_gate_enforced",
            "hysteresis_gate_enforced",
            "safety_gate_enforced",
            "rule_fallback_available",
            "rule_fallback_applied",
        ):
            _strict_bool(getattr(self, name), name)
        versions = (
            _nonnegative_int(self.source_plan_version, "source_plan_version"),
            _nonnegative_int(
                self.expected_previous_plan_version,
                "expected_previous_plan_version",
            ),
            _nonnegative_int(self.current_plan_version, "current_plan_version"),
        )
        if len(set(versions)) != 1:
            _fail("stale_plan_version")
        if _nonnegative_int(self.output_plan_version, "output_plan_version") < versions[2]:
            _fail("stale_output_plan_version")
        _finite_nonnegative(self.inference_elapsed_ms, "inference_elapsed_ms")
        for name in (
            "nonfinite_value_count",
            "online_label_key_count",
            "global_track_id_rewrite_count",
        ):
            if _nonnegative_int(getattr(self, name), name) != 0:
                _fail(f"{name}_nonzero")
        required_gates = (
            self.isolated_simulation,
            self.rule_matrix_unchanged,
            self.deterministic_action_mask_enforced,
            self.reachability_gate_enforced,
            self.capacity_gate_enforced,
            self.version_gate_enforced,
            self.hysteresis_gate_enforced,
            self.safety_gate_enforced,
            self.rule_fallback_available,
        )
        if not all(required_gates):
            _fail("deterministic_safety_gate_missing")
        if self.arm_kind == CONTROL_ARM:
            if self.learning_cost_applied:
                _fail("control_learning_cost_applied")
            if self.rule_fallback_applied or self.fallback_reason is not None:
                _fail("control_fallback_claim_invalid")
        elif self.learning_cost_applied:
            if self.rule_fallback_applied or self.fallback_reason is not None:
                _fail("treatment_applied_and_fallback_conflict")
        elif not self.rule_fallback_applied:
            _fail("treatment_without_learning_or_rule_fallback")
        elif not _optional_required_text(self.fallback_reason):
            _fail("treatment_fallback_reason_missing")

    @property
    def fingerprint(self) -> str:
        return canonical_paired_intervention_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pair_id": self.pair_id,
            "seed": int(self.seed),
            "arm_kind": self.arm_kind,
            "arm_spec_sha256": self.arm_spec_sha256,
            "paired_evaluator_schema_version": self.paired_evaluator_schema_version,
            "paired_evaluator_report_sha256": (
                self.paired_evaluator_report_sha256
            ),
            "input_snapshot_sha256": self.input_snapshot_sha256,
            "rule_cost_matrix_sha256": self.rule_cost_matrix_sha256,
            "action_mask_sha256": self.action_mask_sha256,
            "planner_path": self.planner_path,
            "source_plan_version": int(self.source_plan_version),
            "expected_previous_plan_version": int(
                self.expected_previous_plan_version
            ),
            "current_plan_version": int(self.current_plan_version),
            "output_plan_id": self.output_plan_id,
            "output_plan_version": int(self.output_plan_version),
            "output_plan_payload_sha256": self.output_plan_payload_sha256,
            "isolated_simulation": self.isolated_simulation,
            "learning_cost_applied": self.learning_cost_applied,
            "rule_matrix_unchanged": self.rule_matrix_unchanged,
            "deterministic_action_mask_enforced": (
                self.deterministic_action_mask_enforced
            ),
            "reachability_gate_enforced": self.reachability_gate_enforced,
            "capacity_gate_enforced": self.capacity_gate_enforced,
            "version_gate_enforced": self.version_gate_enforced,
            "hysteresis_gate_enforced": self.hysteresis_gate_enforced,
            "safety_gate_enforced": self.safety_gate_enforced,
            "rule_fallback_available": self.rule_fallback_available,
            "rule_fallback_applied": self.rule_fallback_applied,
            "fallback_reason": self.fallback_reason,
            "hysteresis_decision": self.hysteresis_decision,
            "inference_elapsed_ms": float(self.inference_elapsed_ms),
            "nonfinite_value_count": int(self.nonfinite_value_count),
            "online_label_key_count": int(self.online_label_key_count),
            "global_track_id_rewrite_count": int(
                self.global_track_id_rewrite_count
            ),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "PairedInterventionExecutionReceipt":
        _assert_truth_free(value)
        item = _strict_mapping(value, _RECEIPT_FIELDS, "receipt_fields_mismatch")
        return cls(
            pair_id=_required_text(item["pair_id"], "pair_id"),
            seed=_integer(item["seed"], "seed"),
            arm_kind=_required_text(item["arm_kind"], "arm_kind"),
            arm_spec_sha256=_sha256_text(
                item["arm_spec_sha256"], "arm_spec_sha256"
            ),
            paired_evaluator_schema_version=_required_text(
                item["paired_evaluator_schema_version"],
                "paired_evaluator_schema_version",
            ),
            paired_evaluator_report_sha256=_sha256_text(
                item["paired_evaluator_report_sha256"],
                "paired_evaluator_report_sha256",
            ),
            input_snapshot_sha256=_sha256_text(
                item["input_snapshot_sha256"], "input_snapshot_sha256"
            ),
            rule_cost_matrix_sha256=_sha256_text(
                item["rule_cost_matrix_sha256"], "rule_cost_matrix_sha256"
            ),
            action_mask_sha256=_sha256_text(
                item["action_mask_sha256"], "action_mask_sha256"
            ),
            planner_path=_required_text(item["planner_path"], "planner_path"),
            source_plan_version=_nonnegative_int(
                item["source_plan_version"], "source_plan_version"
            ),
            expected_previous_plan_version=_nonnegative_int(
                item["expected_previous_plan_version"],
                "expected_previous_plan_version",
            ),
            current_plan_version=_nonnegative_int(
                item["current_plan_version"], "current_plan_version"
            ),
            output_plan_id=_required_text(item["output_plan_id"], "output_plan_id"),
            output_plan_version=_nonnegative_int(
                item["output_plan_version"], "output_plan_version"
            ),
            output_plan_payload_sha256=_sha256_text(
                item["output_plan_payload_sha256"],
                "output_plan_payload_sha256",
            ),
            isolated_simulation=_strict_bool(
                item["isolated_simulation"], "isolated_simulation"
            ),
            learning_cost_applied=_strict_bool(
                item["learning_cost_applied"], "learning_cost_applied"
            ),
            rule_matrix_unchanged=_strict_bool(
                item["rule_matrix_unchanged"], "rule_matrix_unchanged"
            ),
            deterministic_action_mask_enforced=_strict_bool(
                item["deterministic_action_mask_enforced"],
                "deterministic_action_mask_enforced",
            ),
            reachability_gate_enforced=_strict_bool(
                item["reachability_gate_enforced"],
                "reachability_gate_enforced",
            ),
            capacity_gate_enforced=_strict_bool(
                item["capacity_gate_enforced"], "capacity_gate_enforced"
            ),
            version_gate_enforced=_strict_bool(
                item["version_gate_enforced"], "version_gate_enforced"
            ),
            hysteresis_gate_enforced=_strict_bool(
                item["hysteresis_gate_enforced"], "hysteresis_gate_enforced"
            ),
            safety_gate_enforced=_strict_bool(
                item["safety_gate_enforced"], "safety_gate_enforced"
            ),
            rule_fallback_available=_strict_bool(
                item["rule_fallback_available"], "rule_fallback_available"
            ),
            rule_fallback_applied=_strict_bool(
                item["rule_fallback_applied"], "rule_fallback_applied"
            ),
            fallback_reason=_optional_text(item["fallback_reason"], "fallback_reason"),
            hysteresis_decision=_required_text(
                item["hysteresis_decision"], "hysteresis_decision"
            ),
            inference_elapsed_ms=_finite_nonnegative(
                item["inference_elapsed_ms"], "inference_elapsed_ms"
            ),
            nonfinite_value_count=_nonnegative_int(
                item["nonfinite_value_count"], "nonfinite_value_count"
            ),
            online_label_key_count=_nonnegative_int(
                item["online_label_key_count"], "online_label_key_count"
            ),
            global_track_id_rewrite_count=_nonnegative_int(
                item["global_track_id_rewrite_count"],
                "global_track_id_rewrite_count",
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class PairedInterventionRuntimeAckReference:
    """Hash-bound reference to an already verified runtime ACK evidence object."""

    pair_id: str
    seed: int
    arm_kind: str
    execution_receipt_sha256: str
    source_ack_evidence_schema_version: str
    source_ack_evidence_sha256: str
    decision_id: str
    ack_timestamp: float
    plan_id: str
    plan_version: int
    accepted: bool
    status_code: str
    source_plan_bus_sequence: int
    source_plan_payload_sha256: str
    source_guidance_bus_sequence: int | None
    source_guidance_payload_sha256: str | None
    fully_bound_to_guidance: bool
    control_applied_binding_count: int
    d3_learning_mode: str | None
    d3_learning_applied: bool | None
    physical_outcome_available: bool
    reward_available: bool
    schema_version: str = PAIRED_INTERVENTION_RUNTIME_ACK_REFERENCE_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != PAIRED_INTERVENTION_RUNTIME_ACK_REFERENCE_SCHEMA_V1:
            _fail("runtime_ack_reference_schema_unsupported")
        for name in ("pair_id", "decision_id", "plan_id", "status_code"):
            _required_text(getattr(self, name), name)
        if self.seed not in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
            _fail("reserved_seed_catalog_mismatch")
        if self.arm_kind not in {CONTROL_ARM, TREATMENT_ARM}:
            _fail("arm_kind_invalid")
        if self.source_ack_evidence_schema_version != D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1:
            _fail("runtime_ack_schema_mismatch")
        for name in (
            "execution_receipt_sha256",
            "source_ack_evidence_sha256",
            "source_plan_payload_sha256",
        ):
            _sha256_text(getattr(self, name), name)
        _optional_sha256_text(
            self.source_guidance_payload_sha256,
            "source_guidance_payload_sha256",
        )
        _finite_nonnegative(self.ack_timestamp, "ack_timestamp")
        _nonnegative_int(self.plan_version, "plan_version")
        _nonnegative_int(self.source_plan_bus_sequence, "source_plan_bus_sequence")
        _optional_nonnegative_int(
            self.source_guidance_bus_sequence,
            "source_guidance_bus_sequence",
        )
        _nonnegative_int(
            self.control_applied_binding_count,
            "control_applied_binding_count",
        )
        for name in (
            "accepted",
            "fully_bound_to_guidance",
            "physical_outcome_available",
            "reward_available",
        ):
            _strict_bool(getattr(self, name), name)
        if self.d3_learning_applied is not None:
            _strict_bool(self.d3_learning_applied, "d3_learning_applied")
        if self.physical_outcome_available or self.reward_available:
            _fail("runtime_ack_claims_outcome_or_reward")
        if self.arm_kind == CONTROL_ARM and self.d3_learning_applied is True:
            _fail("control_runtime_ack_claims_learning_applied")

    @classmethod
    def from_verified_ack(
        cls,
        *,
        receipt: PairedInterventionExecutionReceipt,
        acknowledgement: AssignmentPlanRuntimeAckEvidence,
    ) -> "PairedInterventionRuntimeAckReference":
        if not isinstance(acknowledgement, AssignmentPlanRuntimeAckEvidence):
            _fail("runtime_ack_not_verified")
        if (
            acknowledgement.plan_id != receipt.output_plan_id
            or acknowledgement.plan_version != receipt.output_plan_version
        ):
            _fail("runtime_ack_plan_mismatch")
        applied = acknowledgement.d3_learning_evidence.applied
        if receipt.arm_kind == TREATMENT_ARM and receipt.learning_cost_applied:
            if applied is not True:
                _fail("treatment_runtime_ack_learning_mismatch")
        if receipt.arm_kind == TREATMENT_ARM and receipt.rule_fallback_applied:
            if applied is True:
                _fail("treatment_runtime_ack_fallback_mismatch")
        payload = acknowledgement.to_dict()
        _assert_truth_free(payload)
        return cls(
            pair_id=receipt.pair_id,
            seed=receipt.seed,
            arm_kind=receipt.arm_kind,
            execution_receipt_sha256=receipt.fingerprint,
            source_ack_evidence_schema_version=str(payload["schema_version"]),
            source_ack_evidence_sha256=canonical_paired_intervention_sha256(payload),
            decision_id=acknowledgement.decision_id,
            ack_timestamp=acknowledgement.ack_timestamp,
            plan_id=acknowledgement.plan_id,
            plan_version=acknowledgement.plan_version,
            accepted=acknowledgement.accepted,
            status_code=acknowledgement.status_code,
            source_plan_bus_sequence=acknowledgement.source_plan_bus_sequence,
            source_plan_payload_sha256=(
                acknowledgement.source_plan_payload_sha256
            ),
            source_guidance_bus_sequence=(
                acknowledgement.source_guidance_bus_sequence
            ),
            source_guidance_payload_sha256=(
                acknowledgement.source_guidance_payload_sha256
            ),
            fully_bound_to_guidance=acknowledgement.fully_bound_to_guidance,
            control_applied_binding_count=(
                acknowledgement.control_applied_binding_count
            ),
            d3_learning_mode=acknowledgement.d3_learning_evidence.mode,
            d3_learning_applied=applied,
            physical_outcome_available=acknowledgement.physical_outcome_available,
            reward_available=acknowledgement.reward_available,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pair_id": self.pair_id,
            "seed": int(self.seed),
            "arm_kind": self.arm_kind,
            "execution_receipt_sha256": self.execution_receipt_sha256,
            "source_ack_evidence_schema_version": (
                self.source_ack_evidence_schema_version
            ),
            "source_ack_evidence_sha256": self.source_ack_evidence_sha256,
            "decision_id": self.decision_id,
            "ack_timestamp": float(self.ack_timestamp),
            "plan_id": self.plan_id,
            "plan_version": int(self.plan_version),
            "accepted": self.accepted,
            "status_code": self.status_code,
            "source_plan_bus_sequence": int(self.source_plan_bus_sequence),
            "source_plan_payload_sha256": self.source_plan_payload_sha256,
            "source_guidance_bus_sequence": self.source_guidance_bus_sequence,
            "source_guidance_payload_sha256": (
                self.source_guidance_payload_sha256
            ),
            "fully_bound_to_guidance": self.fully_bound_to_guidance,
            "control_applied_binding_count": int(
                self.control_applied_binding_count
            ),
            "d3_learning_mode": self.d3_learning_mode,
            "d3_learning_applied": self.d3_learning_applied,
            "physical_outcome_available": self.physical_outcome_available,
            "reward_available": self.reward_available,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "PairedInterventionRuntimeAckReference":
        _assert_truth_free(value)
        item = _strict_mapping(
            value, _ACK_REFERENCE_FIELDS, "runtime_ack_reference_fields_mismatch"
        )
        learning_applied = item["d3_learning_applied"]
        if learning_applied is not None:
            learning_applied = _strict_bool(
                learning_applied, "d3_learning_applied"
            )
        return cls(
            pair_id=_required_text(item["pair_id"], "pair_id"),
            seed=_integer(item["seed"], "seed"),
            arm_kind=_required_text(item["arm_kind"], "arm_kind"),
            execution_receipt_sha256=_sha256_text(
                item["execution_receipt_sha256"],
                "execution_receipt_sha256",
            ),
            source_ack_evidence_schema_version=_required_text(
                item["source_ack_evidence_schema_version"],
                "source_ack_evidence_schema_version",
            ),
            source_ack_evidence_sha256=_sha256_text(
                item["source_ack_evidence_sha256"],
                "source_ack_evidence_sha256",
            ),
            decision_id=_required_text(item["decision_id"], "decision_id"),
            ack_timestamp=_finite_nonnegative(
                item["ack_timestamp"], "ack_timestamp"
            ),
            plan_id=_required_text(item["plan_id"], "plan_id"),
            plan_version=_nonnegative_int(item["plan_version"], "plan_version"),
            accepted=_strict_bool(item["accepted"], "accepted"),
            status_code=_required_text(item["status_code"], "status_code"),
            source_plan_bus_sequence=_nonnegative_int(
                item["source_plan_bus_sequence"], "source_plan_bus_sequence"
            ),
            source_plan_payload_sha256=_sha256_text(
                item["source_plan_payload_sha256"],
                "source_plan_payload_sha256",
            ),
            source_guidance_bus_sequence=_optional_nonnegative_int(
                item["source_guidance_bus_sequence"],
                "source_guidance_bus_sequence",
            ),
            source_guidance_payload_sha256=_optional_sha256_text(
                item["source_guidance_payload_sha256"],
                "source_guidance_payload_sha256",
            ),
            fully_bound_to_guidance=_strict_bool(
                item["fully_bound_to_guidance"], "fully_bound_to_guidance"
            ),
            control_applied_binding_count=_nonnegative_int(
                item["control_applied_binding_count"],
                "control_applied_binding_count",
            ),
            d3_learning_mode=_optional_text(
                item["d3_learning_mode"], "d3_learning_mode"
            ),
            d3_learning_applied=learning_applied,
            physical_outcome_available=_strict_bool(
                item["physical_outcome_available"],
                "physical_outcome_available",
            ),
            reward_available=_strict_bool(
                item["reward_available"], "reward_available"
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class PairedInterventionManifest:
    """Serializable D3 manifest with deliberately separated evidence layers."""

    specification: PairedInterventionSpecification
    execution_receipts: tuple[PairedInterventionExecutionReceipt, ...] = ()
    runtime_ack_references: tuple[PairedInterventionRuntimeAckReference, ...] = ()
    schema_version: str = PAIRED_INTERVENTION_MANIFEST_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != PAIRED_INTERVENTION_MANIFEST_SCHEMA_V1:
            _fail("manifest_schema_unsupported")
        expected = {
            (pair.pair_id, pair.seed, arm.arm_kind): arm
            for pair in self.specification.pairs
            for arm in (pair.control, pair.treatment)
        }
        receipts: dict[
            tuple[str, int, str], PairedInterventionExecutionReceipt
        ] = {}
        for receipt in self.execution_receipts:
            key = (receipt.pair_id, receipt.seed, receipt.arm_kind)
            if key in receipts:
                _fail("duplicate_execution_receipt")
            arm = expected.get(key)
            if arm is None:
                _fail("execution_receipt_arm_unknown")
            if receipt.arm_spec_sha256 != arm.fingerprint:
                _fail("execution_receipt_arm_hash_mismatch")
            if receipt.input_snapshot_sha256 != arm.observation_input_snapshot_sha256:
                _fail("execution_receipt_input_hash_mismatch")
            if receipt.planner_path != arm.planner_path:
                _fail("execution_receipt_planner_path_mismatch")
            if (
                receipt.source_plan_version != arm.source_plan_version
                or receipt.expected_previous_plan_version
                != arm.expected_previous_plan_version
                or receipt.current_plan_version != arm.current_plan_version
            ):
                _fail("stale_plan_version")
            receipts[key] = receipt
        if receipts and set(receipts) != set(expected):
            _fail("execution_receipt_arm_inventory_incomplete")
        if receipts:
            report_hashes = {
                receipt.paired_evaluator_report_sha256
                for receipt in receipts.values()
            }
            if len(report_hashes) != 1:
                _fail("paired_evaluator_report_not_frozen")

        references: dict[
            tuple[str, int, str], PairedInterventionRuntimeAckReference
        ] = {}
        for reference in self.runtime_ack_references:
            key = (reference.pair_id, reference.seed, reference.arm_kind)
            if key in references:
                _fail("duplicate_runtime_ack_reference")
            receipt = receipts.get(key)
            if receipt is None:
                _fail("runtime_ack_without_execution_receipt")
            if reference.execution_receipt_sha256 != receipt.fingerprint:
                _fail("runtime_ack_receipt_hash_mismatch")
            if (
                reference.plan_id != receipt.output_plan_id
                or reference.plan_version != receipt.output_plan_version
            ):
                _fail("runtime_ack_plan_mismatch")
            if receipt.arm_kind == TREATMENT_ARM:
                if receipt.learning_cost_applied and reference.d3_learning_applied is not True:
                    _fail("treatment_runtime_ack_learning_mismatch")
                if receipt.rule_fallback_applied and reference.d3_learning_applied is True:
                    _fail("treatment_runtime_ack_fallback_mismatch")
            references[key] = reference

    @property
    def specification_sha256(self) -> str:
        return self.specification.fingerprint

    @property
    def availability(self) -> dict[str, Any]:
        receipt_count = len(self.execution_receipts)
        treatment_receipts = tuple(
            item
            for item in self.execution_receipts
            if item.arm_kind == TREATMENT_ARM
        )
        if not treatment_receipts:
            treatment = {
                "status": "unavailable",
                "available": False,
                "value": None,
                "reason": "isolated_execution_receipts_not_supplied",
                "applied_seed_count": 0,
                "fallback_seed_count": 0,
            }
        else:
            applied = sum(item.learning_cost_applied for item in treatment_receipts)
            fallback = sum(item.rule_fallback_applied for item in treatment_receipts)
            treatment = {
                "status": "available",
                "available": True,
                "value": applied == len(PAIRED_INTERVENTION_RESERVED_SEEDS_V1),
                "reason": (
                    None
                    if fallback == 0
                    else "one_or_more_treatment_arms_used_rule_fallback"
                ),
                "applied_seed_count": int(applied),
                "fallback_seed_count": int(fallback),
            }
        ack_count = len(self.runtime_ack_references)
        expected_ack_count = len(PAIRED_INTERVENTION_RESERVED_SEEDS_V1) * 2
        if ack_count == 0:
            ack_status = "unavailable"
            ack_reason = "runtime_ack_references_not_supplied"
        elif ack_count == expected_ack_count:
            ack_status = "available"
            ack_reason = None
        else:
            ack_status = "partial"
            ack_reason = "runtime_ack_reference_inventory_incomplete"
        return {
            "paired_input_equivalence": {
                "status": "available",
                "available": True,
                "value": True,
                "reason": None,
                "seed_count": len(self.specification.pairs),
            },
            "treatment_safely_applied_in_isolated_simulation": treatment,
            "runtime_ack": {
                "status": ack_status,
                "available": ack_status == "available",
                "value": True if ack_status == "available" else None,
                "reason": ack_reason,
                "reference_count": ack_count,
                "accepted_count": sum(
                    item.accepted for item in self.runtime_ack_references
                ),
                "expected_reference_count": expected_ack_count,
            },
            "outcome": {
                "status": "unavailable",
                "available": False,
                "value": None,
                "reason": "d6_outcome_sidecar_not_joined",
            },
            "counterfactual": {
                "status": "unavailable",
                "available": False,
                "value": None,
                "reason": "d6_counterfactual_sidecar_not_joined",
            },
            "causal": {
                "status": "unavailable",
                "available": False,
                "value": None,
                "reason": "d6_causal_sidecar_not_joined",
            },
            "execution_receipt_count": receipt_count,
        }

    @property
    def admission(self) -> dict[str, bool]:
        return {
            "ppo_allowed": False,
            "online_assist_allowed": False,
            "online_authority_allowed": False,
            "rule_fallback_required": True,
        }

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "fail_closed": True,
            "reserved_seed_count": len(self.specification.reserved_seeds),
            "paired_arm_count": len(self.specification.pairs) * 2,
            "online_label_key_count": 0,
            "global_track_id_rewrite_count": 0,
            "d3_computed_outcome": False,
            "d3_computed_counterfactual": False,
            "d3_computed_causal_attribution": False,
        }

    def _payload_without_manifest_sha256(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "specification": self.specification.to_dict(),
            "specification_sha256": self.specification_sha256,
            "execution_receipts": [
                item.to_dict() for item in self.execution_receipts
            ],
            "runtime_ack_references": [
                item.to_dict() for item in self.runtime_ack_references
            ],
            "availability": self.availability,
            "admission": self.admission,
            "audit": self.audit,
        }

    @property
    def fingerprint(self) -> str:
        return canonical_paired_intervention_sha256(
            self._payload_without_manifest_sha256()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._payload_without_manifest_sha256(),
            "manifest_sha256": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PairedInterventionManifest":
        _assert_truth_free(value)
        _assert_all_finite(value)
        item = _strict_mapping(value, _MANIFEST_FIELDS, "manifest_fields_mismatch")
        manifest = cls(
            specification=PairedInterventionSpecification.from_dict(
                _mapping(item["specification"], "specification")
            ),
            execution_receipts=tuple(
                PairedInterventionExecutionReceipt.from_dict(
                    _mapping(receipt, "execution receipt")
                )
                for receipt in _sequence(
                    item["execution_receipts"], "execution_receipts"
                )
            ),
            runtime_ack_references=tuple(
                PairedInterventionRuntimeAckReference.from_dict(
                    _mapping(reference, "runtime ACK reference")
                )
                for reference in _sequence(
                    item["runtime_ack_references"], "runtime_ack_references"
                )
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )
        if item["specification_sha256"] != manifest.specification_sha256:
            _fail("specification_sha256_mismatch")
        for name, expected in (
            ("availability", manifest.availability),
            ("admission", manifest.admission),
            ("audit", manifest.audit),
        ):
            if item[name] != expected:
                _fail(f"manifest_{name}_mismatch")
        if item["manifest_sha256"] != manifest.fingerprint:
            _fail("manifest_sha256_mismatch")
        return manifest


def canonical_paired_intervention_sha256(value: Any) -> str:
    """Return a canonical hash and reject non-finite or non-JSON values."""

    _assert_truth_free(value)
    _assert_all_finite(value)
    try:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("canonical_json_invalid", str(exc))
    return sha256(payload).hexdigest()


def load_paired_intervention_manifest(
    path: str | Path,
) -> PairedInterventionManifest:
    source = Path(path)
    try:
        with source.open(encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        _fail("manifest_load_failed", str(exc))
    return PairedInterventionManifest.from_dict(
        _mapping(payload, "paired intervention manifest")
    )


def write_paired_intervention_manifest(
    path: str | Path,
    manifest: PairedInterventionManifest,
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(
            manifest.to_dict(),
            stream,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")


def _strict_mapping(
    value: Any,
    fields: frozenset[str],
    code: str,
) -> Mapping[str, Any]:
    item = _mapping(value, "mapping")
    if set(item) != fields:
        _fail(code)
    return item


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", context)
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("sequence_required", context)
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("required_text_missing", context)
    return value.strip()


def _optional_required_text(value: Any) -> str | None:
    if value is None:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_text(value: Any, context: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, context)


def _strict_bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        _fail("boolean_required", context)
    return value


def _integer(value: Any, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _fail("integer_required", context)
    return int(value)


def _nonnegative_int(value: Any, context: str) -> int:
    number = _integer(value, context)
    if number < 0:
        _fail("nonnegative_integer_required", context)
    return number


def _optional_nonnegative_int(value: Any, context: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, context)


def _finite(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("finite_number_required", context)
    number = float(value)
    if not isfinite(number):
        _fail("nonfinite_value", context)
    return number


def _finite_nonnegative(value: Any, context: str) -> float:
    number = _finite(value, context)
    if number < 0.0:
        _fail("nonnegative_number_required", context)
    return number


def _sha256_text(value: Any, context: str) -> str:
    text = _required_text(value, context)
    if len(text) != 64 or any(character not in _HEX_DIGITS for character in text):
        _fail("sha256_invalid", context)
    return text


def _optional_sha256_text(value: Any, context: str) -> str | None:
    if value is None:
        return None
    return _sha256_text(value, context)


def _assert_truth_free(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            text = str(key).strip().lower()
            if text in _FORBIDDEN_ONLINE_KEYS or text.startswith("truth_"):
                _fail("online_truth_leakage", f"forbidden key at {path}.{key}")
            _assert_truth_free(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _assert_truth_free(child, f"{path}[{index}]")


def _assert_all_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _assert_all_finite(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _assert_all_finite(child, f"{path}[{index}]")
    elif isinstance(value, float) and not isfinite(value):
        _fail("nonfinite_value", path)


def _fail(code: str, message: str | None = None) -> None:
    raise PairedInterventionContractError(code, message)


__all__ = [
    "CONTROL_ARM",
    "CONTROL_PLANNER_PATH",
    "D6_SIDECAR_OWNER",
    "OFFLINE_INTERVENTION_SCOPE",
    "PAIRED_INTERVENTION_ARM_SCHEMA_V1",
    "PAIRED_INTERVENTION_EXECUTION_RECEIPT_SCHEMA_V1",
    "PAIRED_INTERVENTION_MANIFEST_SCHEMA_V1",
    "PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1",
    "PAIRED_INTERVENTION_RESERVED_SEEDS_V1",
    "PAIRED_INTERVENTION_RUNTIME_ACK_REFERENCE_SCHEMA_V1",
    "PAIRED_INTERVENTION_SEED_PAIR_SCHEMA_V1",
    "PAIRED_INTERVENTION_SPECIFICATION_SCHEMA_V1",
    "TREATMENT_ARM",
    "TREATMENT_PLANNER_PATH",
    "PairedInterventionArmSpecification",
    "PairedInterventionContractError",
    "PairedInterventionExecutionReceipt",
    "PairedInterventionManifest",
    "PairedInterventionRuntimeAckReference",
    "PairedInterventionSeedPair",
    "PairedInterventionSpecification",
    "canonical_paired_intervention_sha256",
    "load_paired_intervention_manifest",
    "write_paired_intervention_manifest",
]
