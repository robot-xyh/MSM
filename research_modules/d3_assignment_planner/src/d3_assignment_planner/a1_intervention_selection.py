"""Fail-closed A1 intervention selection and lifecycle evidence.

This module does not grant assignment authority.  It freezes a truth-free
selection policy before evaluation, identifies a bounded near-competitive
assignment change, and later joins main-owned publication, runtime ACK and
physical-window evidence without manufacturing any of those stages.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from math import isfinite
from typing import Any

import numpy as np

from .learning_intervention_eligibility import (
    LearningInterventionFrameEvidence,
    evaluate_learning_intervention_candidate_frame,
    validate_learning_intervention_frame_evidence,
)
from .models import AssignmentPlan
from .planning_evidence import PlanningFrameEvidence
from .runtime_plan_ack import (
    D3_ASSIGNMENT_PLAN_TOPIC,
    AssignmentPlanRuntimeAckEvidence,
    canonical_runtime_payload_sha256,
    validated_assignment_plan_payload_sha256,
)
from .runtime_reward_evidence import (
    RuntimePlanWindowRewardEvidence,
    canonical_reward_evidence_payload_sha256,
)


A1_INTERVENTION_PREREGISTRATION_SCHEMA_V1 = (
    "d3.a1-intervention-preregistration.v1"
)
A1_INTERVENTION_CANDIDATE_EVIDENCE_SCHEMA_V1 = (
    "d3.a1-intervention-candidate-evidence.v1"
)
A1_INTERVENTION_SELECTION_DECISION_SCHEMA_V1 = (
    "d3.a1-intervention-selection-decision.v1"
)
A1_PLAN_PUBLICATION_EVIDENCE_SCHEMA_V1 = (
    "d3.a1-plan-publication-evidence.v1"
)
A1_INTERVENTION_LIFECYCLE_EVIDENCE_SCHEMA_V1 = (
    "d3.a1-intervention-lifecycle-evidence.v1"
)

A1_SELECTOR_VERSION_V1 = "d3.a1-near-competition-first-safe-change.v1"
A1_SELECTION_ORDER_V1 = (
    "strict-sequence-then-timestamp-first-safe-discrete-change"
)
A1_SELECTION_SCOPE_V1 = (
    "paired-evaluation-only-no-production-admission-no-authority"
)
A1_PREREGISTRATION_KIND = "truth-free-a1-intervention-preregistration"
A1_CANDIDATE_KIND = "truth-free-a1-intervention-candidate"
A1_SELECTION_KIND = "truth-free-a1-intervention-selection"
A1_PUBLICATION_KIND = "verified-main-d3-plan-publication"
A1_LIFECYCLE_KIND = "a1-intervention-stage-evidence"

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
        "physical_outcome",
        "intercept_success",
        "reward",
    }
)
_FORBIDDEN_TRUTH_KEY_MARKERS = (
    "truth_entity",
    "truth_id",
    "truth_label",
    "truth_position",
    "truth_state",
    "truth_velocity",
)
_IDENTITY_KEY_QUALIFIERS = frozenset(
    {"alias", "aliases", "id", "ids", "name", "names"}
)
_PREREGISTRATION_FIELDS = frozenset(
    {
        "schema_version",
        "contract_kind",
        "selection_scope",
        "selector_version",
        "selection_order",
        "experiment_id",
        "experiment_version",
        "policy_artifact_sha256",
        "evaluation_seeds",
        "sequence_index_min",
        "sequence_index_max",
        "timestamp_s_min",
        "timestamp_s_max",
        "max_abs_cost_correction",
        "max_rule_cost_difference",
        "max_relative_rule_cost_difference",
        "max_binding_change_count",
        "high_threat_threshold",
        "online_truth_allowed",
        "rule_fallback_required",
        "deterministic_safety_shell_required",
        "production_authority_granted",
        "registration_id",
        "content_sha256",
    }
)
_CANDIDATE_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "preregistration",
        "eligibility",
        "seed",
        "policy_evaluated",
        "policy_evaluation_sha256",
        "cost_correction_accepted",
        "assignment_changed",
        "near_competitive",
        "selected_for_paired_evaluation",
        "version_contract_valid",
        "max_abs_cost_correction",
        "rule_basis_score",
        "treatment_rule_basis_score",
        "absolute_rule_cost_difference",
        "relative_rule_cost_difference",
        "rule_unmet_demand_slots",
        "treatment_unmet_demand_slots",
        "rule_unmet_high_threat_slots",
        "treatment_unmet_high_threat_slots",
        "rule_plan_version",
        "treatment_plan_version",
        "previous_plan_version",
        "reason_codes",
        "plan_published",
        "runtime_ack",
        "physical_window_available",
        "content_sha256",
    }
)
_SELECTION_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "preregistration",
        "seed",
        "candidate_count",
        "policy_evaluated_count",
        "cost_correction_accepted_count",
        "assignment_changed_count",
        "near_competitive_count",
        "candidate_content_sha256s",
        "candidate_history_sha256",
        "selected",
        "reason",
        "selected_candidate_content_sha256",
        "selected_sequence_index",
        "selected_timestamp_s",
        "selected_treatment_plan_payload_sha256",
        "plan_published",
        "runtime_ack",
        "physical_window_available",
        "content_sha256",
    }
)
_PUBLICATION_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "source_bus_sequence",
        "source_timestamp_s",
        "source_topic",
        "source",
        "plan_id",
        "plan_version",
        "plan_schema_version",
        "assignment_plan_payload_sha256",
        "runtime_plan_payload_sha256",
        "source_envelope_sha256",
        "content_sha256",
    }
)
_LIFECYCLE_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "registration_id",
        "preregistration_sha256",
        "selection_decision_sha256",
        "candidate_evidence_sha256",
        "plan_id",
        "plan_version",
        "assignment_plan_payload_sha256",
        "policy_evaluated",
        "cost_correction_accepted",
        "assignment_changed",
        "plan_published",
        "runtime_ack",
        "physical_window_available",
        "r0_pair_available",
        "publication_evidence_sha256",
        "runtime_ack_evidence_sha256",
        "physical_window_evidence_sha256s",
        "required_binding_count",
        "physical_window_binding_count",
        "physical_window_available_binding_count",
        "r0_pair_available_binding_count",
        "status",
        "content_sha256",
    }
)
_ENVELOPE_FIELDS = frozenset(
    {"sequence", "topic", "source", "timestamp", "schema_version", "payload"}
)
_RUNTIME_PLAN_PAYLOAD_FIELDS = frozenset(
    {
        "timestamp",
        "plan_id",
        "plan_version",
        "created_at",
        "assignment_count",
        "target_count",
        "resource_count",
        "assignments",
        "unassigned_global_track_ids",
        "solver_name",
        "metadata",
    }
)
A1_INTERVENTION_CANDIDATE_REASON_CODES = frozenset(
    {
        "selected",
        "registration_scope_mismatch",
        "policy_not_evaluated",
        "safety_shell_rejected",
        "version_contract_rejected",
        "cost_correction_bound_exceeded",
        "demand_coverage_degraded",
        "high_threat_coverage_degraded",
        "assignment_unchanged",
        "binding_change_limit_exceeded",
        "rule_cost_basis_unavailable",
        "not_near_competitive",
        "empty_treatment_assignment",
    }
)
_CANDIDATE_REASON_CODES = A1_INTERVENTION_CANDIDATE_REASON_CODES


class A1InterventionContractError(ValueError):
    """Stable fail-closed error for A1 selection and lifecycle contracts."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        self.reason = self.code
        super().__init__(self.code if message is None else f"{self.code}: {message}")


@dataclass(frozen=True, slots=True)
class A1InterventionPreRegistration:
    """Immutable selection limits that main must persist before evaluation."""

    experiment_id: str
    experiment_version: str
    policy_artifact_sha256: str
    evaluation_seeds: tuple[int, ...]
    sequence_index_min: int
    sequence_index_max: int
    timestamp_s_min: float
    timestamp_s_max: float
    max_abs_cost_correction: float
    max_rule_cost_difference: float
    max_relative_rule_cost_difference: float
    max_binding_change_count: int
    high_threat_threshold: float
    registration_id: str
    content_sha256: str
    online_truth_allowed: bool = False
    rule_fallback_required: bool = True
    deterministic_safety_shell_required: bool = True
    production_authority_granted: bool = False
    selector_version: str = A1_SELECTOR_VERSION_V1
    selection_order: str = A1_SELECTION_ORDER_V1
    selection_scope: str = A1_SELECTION_SCOPE_V1
    contract_kind: str = A1_PREREGISTRATION_KIND
    schema_version: str = A1_INTERVENTION_PREREGISTRATION_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != A1_INTERVENTION_PREREGISTRATION_SCHEMA_V1:
            _fail("preregistration_schema_unsupported")
        if self.contract_kind != A1_PREREGISTRATION_KIND:
            _fail("preregistration_kind_invalid")
        if self.selection_scope != A1_SELECTION_SCOPE_V1:
            _fail("selection_scope_invalid")
        if self.selector_version != A1_SELECTOR_VERSION_V1:
            _fail("selector_version_unsupported")
        if self.selection_order != A1_SELECTION_ORDER_V1:
            _fail("selection_order_unsupported")
        _required_text(self.experiment_id, "experiment_id")
        _required_text(self.experiment_version, "experiment_version")
        _sha256(self.policy_artifact_sha256, "policy_artifact_sha256")
        seeds = tuple(_nonnegative_int(value, "evaluation_seed") for value in self.evaluation_seeds)
        if not seeds or seeds != tuple(sorted(set(seeds))):
            _fail("evaluation_seed_inventory_invalid")
        sequence_min = _nonnegative_int(
            self.sequence_index_min, "sequence_index_min"
        )
        sequence_max = _nonnegative_int(
            self.sequence_index_max, "sequence_index_max"
        )
        if sequence_max < sequence_min:
            _fail("sequence_index_window_invalid")
        timestamp_min = _finite_nonnegative(
            self.timestamp_s_min, "timestamp_s_min"
        )
        timestamp_max = _finite_nonnegative(
            self.timestamp_s_max, "timestamp_s_max"
        )
        if timestamp_max < timestamp_min:
            _fail("timestamp_window_invalid")
        _finite_positive(
            self.max_abs_cost_correction, "max_abs_cost_correction"
        )
        _finite_nonnegative(
            self.max_rule_cost_difference, "max_rule_cost_difference"
        )
        _finite_nonnegative(
            self.max_relative_rule_cost_difference,
            "max_relative_rule_cost_difference",
        )
        _positive_int(
            self.max_binding_change_count, "max_binding_change_count"
        )
        threshold = _finite(self.high_threat_threshold, "high_threat_threshold")
        if not 0.0 <= threshold <= 1.0:
            _fail("high_threat_threshold_invalid")
        for name in (
            "online_truth_allowed",
            "rule_fallback_required",
            "deterministic_safety_shell_required",
            "production_authority_granted",
        ):
            _strict_bool(getattr(self, name), name)
        if self.online_truth_allowed:
            _fail("online_truth_must_remain_disabled")
        if not self.rule_fallback_required:
            _fail("rule_fallback_must_remain_enabled")
        if not self.deterministic_safety_shell_required:
            _fail("deterministic_safety_shell_required")
        if self.production_authority_granted:
            _fail("production_authority_forbidden")
        object.__setattr__(self, "evaluation_seeds", seeds)

        expected_registration_id = _registration_id(self)
        if self.registration_id != expected_registration_id:
            _fail("registration_id_mismatch")
        _sha256(self.content_sha256, "content_sha256")
        if self.content_sha256 != _preregistration_content_sha256(self):
            _fail("preregistration_content_sha256_mismatch")

    @property
    def fingerprint(self) -> str:
        return self.content_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_kind": self.contract_kind,
            "selection_scope": self.selection_scope,
            "selector_version": self.selector_version,
            "selection_order": self.selection_order,
            "experiment_id": self.experiment_id,
            "experiment_version": self.experiment_version,
            "policy_artifact_sha256": self.policy_artifact_sha256,
            "evaluation_seeds": list(self.evaluation_seeds),
            "sequence_index_min": self.sequence_index_min,
            "sequence_index_max": self.sequence_index_max,
            "timestamp_s_min": self.timestamp_s_min,
            "timestamp_s_max": self.timestamp_s_max,
            "max_abs_cost_correction": self.max_abs_cost_correction,
            "max_rule_cost_difference": self.max_rule_cost_difference,
            "max_relative_rule_cost_difference": (
                self.max_relative_rule_cost_difference
            ),
            "max_binding_change_count": self.max_binding_change_count,
            "high_threat_threshold": self.high_threat_threshold,
            "online_truth_allowed": self.online_truth_allowed,
            "rule_fallback_required": self.rule_fallback_required,
            "deterministic_safety_shell_required": (
                self.deterministic_safety_shell_required
            ),
            "production_authority_granted": (
                self.production_authority_granted
            ),
            "registration_id": self.registration_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "A1InterventionPreRegistration":
        item = _strict_mapping(
            value, _PREREGISTRATION_FIELDS, "preregistration_fields_mismatch"
        )
        return cls(
            experiment_id=_required_text(item["experiment_id"], "experiment_id"),
            experiment_version=_required_text(
                item["experiment_version"], "experiment_version"
            ),
            policy_artifact_sha256=_sha256(
                item["policy_artifact_sha256"], "policy_artifact_sha256"
            ),
            evaluation_seeds=tuple(
                _nonnegative_int(value, "evaluation_seed")
                for value in _sequence(item["evaluation_seeds"], "evaluation_seeds")
            ),
            sequence_index_min=_nonnegative_int(
                item["sequence_index_min"], "sequence_index_min"
            ),
            sequence_index_max=_nonnegative_int(
                item["sequence_index_max"], "sequence_index_max"
            ),
            timestamp_s_min=_finite_nonnegative(
                item["timestamp_s_min"], "timestamp_s_min"
            ),
            timestamp_s_max=_finite_nonnegative(
                item["timestamp_s_max"], "timestamp_s_max"
            ),
            max_abs_cost_correction=_finite_positive(
                item["max_abs_cost_correction"],
                "max_abs_cost_correction",
            ),
            max_rule_cost_difference=_finite_nonnegative(
                item["max_rule_cost_difference"],
                "max_rule_cost_difference",
            ),
            max_relative_rule_cost_difference=_finite_nonnegative(
                item["max_relative_rule_cost_difference"],
                "max_relative_rule_cost_difference",
            ),
            max_binding_change_count=_positive_int(
                item["max_binding_change_count"],
                "max_binding_change_count",
            ),
            high_threat_threshold=_finite(
                item["high_threat_threshold"], "high_threat_threshold"
            ),
            registration_id=_required_text(
                item["registration_id"], "registration_id"
            ),
            content_sha256=_sha256(item["content_sha256"], "content_sha256"),
            online_truth_allowed=_strict_bool(
                item["online_truth_allowed"], "online_truth_allowed"
            ),
            rule_fallback_required=_strict_bool(
                item["rule_fallback_required"], "rule_fallback_required"
            ),
            deterministic_safety_shell_required=_strict_bool(
                item["deterministic_safety_shell_required"],
                "deterministic_safety_shell_required",
            ),
            production_authority_granted=_strict_bool(
                item["production_authority_granted"],
                "production_authority_granted",
            ),
            selector_version=_required_text(
                item["selector_version"], "selector_version"
            ),
            selection_order=_required_text(
                item["selection_order"], "selection_order"
            ),
            selection_scope=_required_text(
                item["selection_scope"], "selection_scope"
            ),
            contract_kind=_required_text(
                item["contract_kind"], "contract_kind"
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


def build_a1_intervention_preregistration(
    *,
    experiment_id: str,
    experiment_version: str,
    policy_artifact_sha256: str,
    evaluation_seeds: Sequence[int],
    sequence_index_min: int,
    sequence_index_max: int,
    timestamp_s_min: float,
    timestamp_s_max: float,
    max_abs_cost_correction: float,
    max_rule_cost_difference: float,
    max_relative_rule_cost_difference: float,
    max_binding_change_count: int,
    high_threat_threshold: float = 0.7,
) -> A1InterventionPreRegistration:
    """Build a content-addressed selection contract before frame evaluation."""

    raw_seeds = tuple(
        _nonnegative_int(value, "evaluation_seed")
        for value in evaluation_seeds
    )
    if len(raw_seeds) != len(set(raw_seeds)):
        _fail("evaluation_seed_inventory_invalid")
    values = {
        "experiment_id": _required_text(experiment_id, "experiment_id"),
        "experiment_version": _required_text(
            experiment_version, "experiment_version"
        ),
        "policy_artifact_sha256": _sha256(
            policy_artifact_sha256, "policy_artifact_sha256"
        ),
        "evaluation_seeds": tuple(sorted(raw_seeds)),
        "sequence_index_min": _nonnegative_int(
            sequence_index_min, "sequence_index_min"
        ),
        "sequence_index_max": _nonnegative_int(
            sequence_index_max, "sequence_index_max"
        ),
        "timestamp_s_min": _finite_nonnegative(
            timestamp_s_min, "timestamp_s_min"
        ),
        "timestamp_s_max": _finite_nonnegative(
            timestamp_s_max, "timestamp_s_max"
        ),
        "max_abs_cost_correction": _finite_positive(
            max_abs_cost_correction, "max_abs_cost_correction"
        ),
        "max_rule_cost_difference": _finite_nonnegative(
            max_rule_cost_difference, "max_rule_cost_difference"
        ),
        "max_relative_rule_cost_difference": _finite_nonnegative(
            max_relative_rule_cost_difference,
            "max_relative_rule_cost_difference",
        ),
        "max_binding_change_count": _positive_int(
            max_binding_change_count, "max_binding_change_count"
        ),
        "high_threat_threshold": _finite(
            high_threat_threshold, "high_threat_threshold"
        ),
        "online_truth_allowed": False,
        "rule_fallback_required": True,
        "deterministic_safety_shell_required": True,
        "production_authority_granted": False,
        "selector_version": A1_SELECTOR_VERSION_V1,
        "selection_order": A1_SELECTION_ORDER_V1,
        "selection_scope": A1_SELECTION_SCOPE_V1,
        "contract_kind": A1_PREREGISTRATION_KIND,
        "schema_version": A1_INTERVENTION_PREREGISTRATION_SCHEMA_V1,
    }
    registration_id = _registration_id_from_values(values)
    return A1InterventionPreRegistration(
        **values,
        registration_id=registration_id,
        content_sha256=canonical_runtime_payload_sha256(
            {**values, "registration_id": registration_id}
        ),
    )


@dataclass(frozen=True, slots=True)
class A1InterventionCandidateEvidence:
    """Derived stage evidence for one pre-registered rule/treatment pair."""

    preregistration: A1InterventionPreRegistration
    eligibility: LearningInterventionFrameEvidence
    seed: int
    policy_evaluated: bool
    policy_evaluation_sha256: str
    cost_correction_accepted: bool
    assignment_changed: bool
    near_competitive: bool
    selected_for_paired_evaluation: bool
    version_contract_valid: bool
    max_abs_cost_correction: float
    rule_basis_score: float | None
    treatment_rule_basis_score: float | None
    absolute_rule_cost_difference: float | None
    relative_rule_cost_difference: float | None
    rule_unmet_demand_slots: int
    treatment_unmet_demand_slots: int
    rule_unmet_high_threat_slots: int
    treatment_unmet_high_threat_slots: int
    rule_plan_version: int
    treatment_plan_version: int
    previous_plan_version: int
    reason_codes: tuple[str, ...]
    content_sha256: str
    plan_published: bool = False
    runtime_ack: bool = False
    physical_window_available: bool = False
    evidence_kind: str = A1_CANDIDATE_KIND
    schema_version: str = A1_INTERVENTION_CANDIDATE_EVIDENCE_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != A1_INTERVENTION_CANDIDATE_EVIDENCE_SCHEMA_V1:
            _fail("candidate_schema_unsupported")
        if self.evidence_kind != A1_CANDIDATE_KIND:
            _fail("candidate_kind_invalid")
        if not isinstance(
            self.preregistration, A1InterventionPreRegistration
        ):
            _fail("preregistration_type_invalid")
        if not isinstance(self.eligibility, LearningInterventionFrameEvidence):
            _fail("eligibility_type_invalid")
        seed = _nonnegative_int(self.seed, "seed")
        for name in (
            "policy_evaluated",
            "cost_correction_accepted",
            "assignment_changed",
            "near_competitive",
            "selected_for_paired_evaluation",
            "version_contract_valid",
            "plan_published",
            "runtime_ack",
            "physical_window_available",
        ):
            _strict_bool(getattr(self, name), name)
        if self.plan_published or self.runtime_ack or self.physical_window_available:
            _fail("candidate_cannot_claim_runtime_stage")
        _sha256(self.policy_evaluation_sha256, "policy_evaluation_sha256")
        correction = _finite_nonnegative(
            self.max_abs_cost_correction, "max_abs_cost_correction"
        )
        scores = (
            _optional_finite(self.rule_basis_score, "rule_basis_score"),
            _optional_finite(
                self.treatment_rule_basis_score,
                "treatment_rule_basis_score",
            ),
            _optional_finite_nonnegative(
                self.absolute_rule_cost_difference,
                "absolute_rule_cost_difference",
            ),
            _optional_finite_nonnegative(
                self.relative_rule_cost_difference,
                "relative_rule_cost_difference",
            ),
        )
        if any(value is None for value in scores) and any(
            value is not None for value in scores
        ):
            _fail("rule_cost_basis_partial")
        for name in (
            "rule_unmet_demand_slots",
            "treatment_unmet_demand_slots",
            "rule_unmet_high_threat_slots",
            "treatment_unmet_high_threat_slots",
            "rule_plan_version",
            "treatment_plan_version",
            "previous_plan_version",
        ):
            _nonnegative_int(getattr(self, name), name)
        if (
            self.rule_plan_version
            not in {self.previous_plan_version, self.previous_plan_version + 1}
            or self.treatment_plan_version
            not in {self.previous_plan_version, self.previous_plan_version + 1}
            or (
                self.version_contract_valid
                and self.eligibility.binding_change_count > 0
                and self.treatment_plan_version
                != self.previous_plan_version + 1
            )
        ):
            _fail("candidate_plan_version_lineage_invalid")
        reasons = tuple(_required_text(value, "reason_code") for value in self.reason_codes)
        if not reasons or len(reasons) != len(set(reasons)):
            _fail("candidate_reason_codes_invalid")
        if any(value not in _CANDIDATE_REASON_CODES for value in reasons):
            _fail("candidate_reason_code_unsupported")

        expected = _candidate_stage_values(
            preregistration=self.preregistration,
            eligibility=self.eligibility,
            seed=seed,
            policy_evaluated=self.policy_evaluated,
            version_contract_valid=self.version_contract_valid,
            max_abs_cost_correction=correction,
            rule_basis_score=self.rule_basis_score,
            treatment_rule_basis_score=self.treatment_rule_basis_score,
            absolute_rule_cost_difference=self.absolute_rule_cost_difference,
            relative_rule_cost_difference=self.relative_rule_cost_difference,
            rule_unmet_demand_slots=self.rule_unmet_demand_slots,
            treatment_unmet_demand_slots=self.treatment_unmet_demand_slots,
            rule_unmet_high_threat_slots=self.rule_unmet_high_threat_slots,
            treatment_unmet_high_threat_slots=(
                self.treatment_unmet_high_threat_slots
            ),
        )
        actual = (
            self.cost_correction_accepted,
            self.assignment_changed,
            self.near_competitive,
            self.selected_for_paired_evaluation,
            reasons,
        )
        if actual != expected:
            _fail("candidate_stage_derivation_mismatch")
        object.__setattr__(self, "reason_codes", reasons)
        _sha256(self.content_sha256, "content_sha256")
        if self.content_sha256 != _candidate_content_sha256(self):
            _fail("candidate_content_sha256_mismatch")

    @property
    def sequence_index(self) -> int:
        return self.eligibility.sequence_index

    @property
    def timestamp_s(self) -> float:
        return self.eligibility.timestamp_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "preregistration": self.preregistration.to_dict(),
            "eligibility": self.eligibility.to_dict(),
            "seed": self.seed,
            "policy_evaluated": self.policy_evaluated,
            "policy_evaluation_sha256": self.policy_evaluation_sha256,
            "cost_correction_accepted": self.cost_correction_accepted,
            "assignment_changed": self.assignment_changed,
            "near_competitive": self.near_competitive,
            "selected_for_paired_evaluation": (
                self.selected_for_paired_evaluation
            ),
            "version_contract_valid": self.version_contract_valid,
            "max_abs_cost_correction": self.max_abs_cost_correction,
            "rule_basis_score": self.rule_basis_score,
            "treatment_rule_basis_score": self.treatment_rule_basis_score,
            "absolute_rule_cost_difference": (
                self.absolute_rule_cost_difference
            ),
            "relative_rule_cost_difference": (
                self.relative_rule_cost_difference
            ),
            "rule_unmet_demand_slots": self.rule_unmet_demand_slots,
            "treatment_unmet_demand_slots": (
                self.treatment_unmet_demand_slots
            ),
            "rule_unmet_high_threat_slots": (
                self.rule_unmet_high_threat_slots
            ),
            "treatment_unmet_high_threat_slots": (
                self.treatment_unmet_high_threat_slots
            ),
            "rule_plan_version": self.rule_plan_version,
            "treatment_plan_version": self.treatment_plan_version,
            "previous_plan_version": self.previous_plan_version,
            "reason_codes": list(self.reason_codes),
            "plan_published": self.plan_published,
            "runtime_ack": self.runtime_ack,
            "physical_window_available": self.physical_window_available,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "A1InterventionCandidateEvidence":
        item = _strict_mapping(
            value, _CANDIDATE_FIELDS, "candidate_fields_mismatch"
        )
        return cls(
            preregistration=A1InterventionPreRegistration.from_dict(
                _mapping(item["preregistration"], "preregistration")
            ),
            eligibility=validate_learning_intervention_frame_evidence(
                _mapping(item["eligibility"], "eligibility")
            ),
            seed=_nonnegative_int(item["seed"], "seed"),
            policy_evaluated=_strict_bool(
                item["policy_evaluated"], "policy_evaluated"
            ),
            policy_evaluation_sha256=_sha256(
                item["policy_evaluation_sha256"],
                "policy_evaluation_sha256",
            ),
            cost_correction_accepted=_strict_bool(
                item["cost_correction_accepted"],
                "cost_correction_accepted",
            ),
            assignment_changed=_strict_bool(
                item["assignment_changed"], "assignment_changed"
            ),
            near_competitive=_strict_bool(
                item["near_competitive"], "near_competitive"
            ),
            selected_for_paired_evaluation=_strict_bool(
                item["selected_for_paired_evaluation"],
                "selected_for_paired_evaluation",
            ),
            version_contract_valid=_strict_bool(
                item["version_contract_valid"],
                "version_contract_valid",
            ),
            max_abs_cost_correction=_finite_nonnegative(
                item["max_abs_cost_correction"],
                "max_abs_cost_correction",
            ),
            rule_basis_score=_optional_finite(
                item["rule_basis_score"], "rule_basis_score"
            ),
            treatment_rule_basis_score=_optional_finite(
                item["treatment_rule_basis_score"],
                "treatment_rule_basis_score",
            ),
            absolute_rule_cost_difference=_optional_finite_nonnegative(
                item["absolute_rule_cost_difference"],
                "absolute_rule_cost_difference",
            ),
            relative_rule_cost_difference=_optional_finite_nonnegative(
                item["relative_rule_cost_difference"],
                "relative_rule_cost_difference",
            ),
            rule_unmet_demand_slots=_nonnegative_int(
                item["rule_unmet_demand_slots"],
                "rule_unmet_demand_slots",
            ),
            treatment_unmet_demand_slots=_nonnegative_int(
                item["treatment_unmet_demand_slots"],
                "treatment_unmet_demand_slots",
            ),
            rule_unmet_high_threat_slots=_nonnegative_int(
                item["rule_unmet_high_threat_slots"],
                "rule_unmet_high_threat_slots",
            ),
            treatment_unmet_high_threat_slots=_nonnegative_int(
                item["treatment_unmet_high_threat_slots"],
                "treatment_unmet_high_threat_slots",
            ),
            rule_plan_version=_nonnegative_int(
                item["rule_plan_version"], "rule_plan_version"
            ),
            treatment_plan_version=_nonnegative_int(
                item["treatment_plan_version"], "treatment_plan_version"
            ),
            previous_plan_version=_nonnegative_int(
                item["previous_plan_version"], "previous_plan_version"
            ),
            reason_codes=tuple(
                _required_text(value, "reason_code")
                for value in _sequence(item["reason_codes"], "reason_codes")
            ),
            content_sha256=_sha256(item["content_sha256"], "content_sha256"),
            plan_published=_strict_bool(
                item["plan_published"], "plan_published"
            ),
            runtime_ack=_strict_bool(item["runtime_ack"], "runtime_ack"),
            physical_window_available=_strict_bool(
                item["physical_window_available"],
                "physical_window_available",
            ),
            evidence_kind=_required_text(
                item["evidence_kind"], "evidence_kind"
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


def evaluate_a1_intervention_candidate(
    *,
    preregistration: A1InterventionPreRegistration | Mapping[str, Any],
    seed: int,
    sequence_index: int,
    rule_frame: PlanningFrameEvidence,
    treatment_frame: PlanningFrameEvidence,
) -> A1InterventionCandidateEvidence:
    """Evaluate one treatment correction under frozen truth-free limits."""

    registration = validate_a1_intervention_preregistration(preregistration)
    candidate_seed = _nonnegative_int(seed, "seed")
    eligibility = evaluate_learning_intervention_candidate_frame(
        sequence_index=sequence_index,
        rule_frame=rule_frame,
        treatment_frame=treatment_frame,
    )
    policy_evaluated, policy_evaluation_sha256 = _policy_evaluation(
        treatment_frame
    )
    correction = _maximum_safe_cost_correction(rule_frame, treatment_frame)
    scores = _rule_basis_comparison(
        rule_frame=rule_frame,
        treatment_frame=treatment_frame,
        high_threat_threshold=registration.high_threat_threshold,
    )
    version_contract_valid = _strict_changed_plan_version_contract(
        treatment_frame=treatment_frame,
        binding_change_count=eligibility.binding_change_count,
    )
    values = {
        "preregistration": registration,
        "eligibility": eligibility,
        "seed": candidate_seed,
        "policy_evaluated": policy_evaluated,
        "policy_evaluation_sha256": policy_evaluation_sha256,
        "version_contract_valid": version_contract_valid,
        "max_abs_cost_correction": correction,
        "rule_basis_score": scores[0],
        "treatment_rule_basis_score": scores[1],
        "absolute_rule_cost_difference": scores[2],
        "relative_rule_cost_difference": scores[3],
        "rule_unmet_demand_slots": scores[4],
        "treatment_unmet_demand_slots": scores[5],
        "rule_unmet_high_threat_slots": scores[6],
        "treatment_unmet_high_threat_slots": scores[7],
        "rule_plan_version": _plan_version(rule_frame.plan),
        "treatment_plan_version": _plan_version(treatment_frame.plan),
        "previous_plan_version": _plan_version(treatment_frame.previous_plan),
        "plan_published": False,
        "runtime_ack": False,
        "physical_window_available": False,
        "evidence_kind": A1_CANDIDATE_KIND,
        "schema_version": A1_INTERVENTION_CANDIDATE_EVIDENCE_SCHEMA_V1,
    }
    stage = _candidate_stage_values(
        preregistration=registration,
        eligibility=eligibility,
        seed=candidate_seed,
        policy_evaluated=policy_evaluated,
        version_contract_valid=version_contract_valid,
        max_abs_cost_correction=correction,
        rule_basis_score=scores[0],
        treatment_rule_basis_score=scores[1],
        absolute_rule_cost_difference=scores[2],
        relative_rule_cost_difference=scores[3],
        rule_unmet_demand_slots=scores[4],
        treatment_unmet_demand_slots=scores[5],
        rule_unmet_high_threat_slots=scores[6],
        treatment_unmet_high_threat_slots=scores[7],
    )
    payload = _candidate_payload(
        values=values,
        cost_correction_accepted=stage[0],
        assignment_changed=stage[1],
        near_competitive=stage[2],
        selected_for_paired_evaluation=stage[3],
        reason_codes=stage[4],
    )
    return A1InterventionCandidateEvidence(
        **values,
        cost_correction_accepted=stage[0],
        assignment_changed=stage[1],
        near_competitive=stage[2],
        selected_for_paired_evaluation=stage[3],
        reason_codes=stage[4],
        content_sha256=canonical_runtime_payload_sha256(payload),
    )


@dataclass(frozen=True, slots=True)
class A1InterventionSelectionDecision:
    """Deterministic first-safe-change result for one seed history."""

    preregistration: A1InterventionPreRegistration
    seed: int
    candidate_count: int
    policy_evaluated_count: int
    cost_correction_accepted_count: int
    assignment_changed_count: int
    near_competitive_count: int
    candidate_content_sha256s: tuple[str, ...]
    candidate_history_sha256: str
    selected: bool
    reason: str
    selected_candidate_content_sha256: str | None
    selected_sequence_index: int | None
    selected_timestamp_s: float | None
    selected_treatment_plan_payload_sha256: str | None
    content_sha256: str
    plan_published: bool = False
    runtime_ack: bool = False
    physical_window_available: bool = False
    evidence_kind: str = A1_SELECTION_KIND
    schema_version: str = A1_INTERVENTION_SELECTION_DECISION_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != A1_INTERVENTION_SELECTION_DECISION_SCHEMA_V1:
            _fail("selection_schema_unsupported")
        if self.evidence_kind != A1_SELECTION_KIND:
            _fail("selection_kind_invalid")
        if not isinstance(
            self.preregistration, A1InterventionPreRegistration
        ):
            _fail("preregistration_type_invalid")
        _nonnegative_int(self.seed, "seed")
        count = _nonnegative_int(self.candidate_count, "candidate_count")
        stage_counts = tuple(
            _nonnegative_int(getattr(self, name), name)
            for name in (
                "policy_evaluated_count",
                "cost_correction_accepted_count",
                "assignment_changed_count",
                "near_competitive_count",
            )
        )
        if any(value > count for value in stage_counts):
            _fail("selection_stage_count_invalid")
        digests = tuple(
            _sha256(value, "candidate_content_sha256")
            for value in self.candidate_content_sha256s
        )
        if len(digests) != count or len(digests) != len(set(digests)):
            _fail("candidate_digest_inventory_invalid")
        _sha256(self.candidate_history_sha256, "candidate_history_sha256")
        if self.candidate_history_sha256 != canonical_runtime_payload_sha256(
            {
                "registration_id": self.preregistration.registration_id,
                "seed": self.seed,
                "candidate_content_sha256s": digests,
            }
        ):
            _fail("candidate_history_sha256_mismatch")
        for name in (
            "selected",
            "plan_published",
            "runtime_ack",
            "physical_window_available",
        ):
            _strict_bool(getattr(self, name), name)
        if self.plan_published or self.runtime_ack or self.physical_window_available:
            _fail("selection_cannot_claim_runtime_stage")
        reason = _required_text(self.reason, "reason")
        selected_digest = _optional_sha256(
            self.selected_candidate_content_sha256,
            "selected_candidate_content_sha256",
        )
        selected_sequence = _optional_nonnegative_int(
            self.selected_sequence_index, "selected_sequence_index"
        )
        selected_timestamp = _optional_finite_nonnegative(
            self.selected_timestamp_s, "selected_timestamp_s"
        )
        selected_plan_digest = _optional_sha256(
            self.selected_treatment_plan_payload_sha256,
            "selected_treatment_plan_payload_sha256",
        )
        if self.selected:
            if (
                reason != "selected"
                or selected_digest is None
                or selected_digest not in digests
                or selected_sequence is None
                or selected_timestamp is None
                or selected_plan_digest is None
            ):
                _fail("selected_decision_incomplete")
        elif (
            reason != "no_safe_discrete_intervention"
            or any(
                value is not None
                for value in (
                    selected_digest,
                    selected_sequence,
                    selected_timestamp,
                    selected_plan_digest,
                )
            )
        ):
            _fail("unselected_decision_invalid")
        object.__setattr__(self, "candidate_content_sha256s", digests)
        _sha256(self.content_sha256, "content_sha256")
        if self.content_sha256 != _selection_content_sha256(self):
            _fail("selection_content_sha256_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "preregistration": self.preregistration.to_dict(),
            "seed": self.seed,
            "candidate_count": self.candidate_count,
            "policy_evaluated_count": self.policy_evaluated_count,
            "cost_correction_accepted_count": (
                self.cost_correction_accepted_count
            ),
            "assignment_changed_count": self.assignment_changed_count,
            "near_competitive_count": self.near_competitive_count,
            "candidate_content_sha256s": list(
                self.candidate_content_sha256s
            ),
            "candidate_history_sha256": self.candidate_history_sha256,
            "selected": self.selected,
            "reason": self.reason,
            "selected_candidate_content_sha256": (
                self.selected_candidate_content_sha256
            ),
            "selected_sequence_index": self.selected_sequence_index,
            "selected_timestamp_s": self.selected_timestamp_s,
            "selected_treatment_plan_payload_sha256": (
                self.selected_treatment_plan_payload_sha256
            ),
            "plan_published": self.plan_published,
            "runtime_ack": self.runtime_ack,
            "physical_window_available": self.physical_window_available,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "A1InterventionSelectionDecision":
        item = _strict_mapping(
            value, _SELECTION_FIELDS, "selection_fields_mismatch"
        )
        return cls(
            preregistration=A1InterventionPreRegistration.from_dict(
                _mapping(item["preregistration"], "preregistration")
            ),
            seed=_nonnegative_int(item["seed"], "seed"),
            candidate_count=_nonnegative_int(
                item["candidate_count"], "candidate_count"
            ),
            policy_evaluated_count=_nonnegative_int(
                item["policy_evaluated_count"], "policy_evaluated_count"
            ),
            cost_correction_accepted_count=_nonnegative_int(
                item["cost_correction_accepted_count"],
                "cost_correction_accepted_count",
            ),
            assignment_changed_count=_nonnegative_int(
                item["assignment_changed_count"],
                "assignment_changed_count",
            ),
            near_competitive_count=_nonnegative_int(
                item["near_competitive_count"], "near_competitive_count"
            ),
            candidate_content_sha256s=tuple(
                _sha256(value, "candidate_content_sha256")
                for value in _sequence(
                    item["candidate_content_sha256s"],
                    "candidate_content_sha256s",
                )
            ),
            candidate_history_sha256=_sha256(
                item["candidate_history_sha256"],
                "candidate_history_sha256",
            ),
            selected=_strict_bool(item["selected"], "selected"),
            reason=_required_text(item["reason"], "reason"),
            selected_candidate_content_sha256=_optional_sha256(
                item["selected_candidate_content_sha256"],
                "selected_candidate_content_sha256",
            ),
            selected_sequence_index=_optional_nonnegative_int(
                item["selected_sequence_index"], "selected_sequence_index"
            ),
            selected_timestamp_s=_optional_finite_nonnegative(
                item["selected_timestamp_s"], "selected_timestamp_s"
            ),
            selected_treatment_plan_payload_sha256=_optional_sha256(
                item["selected_treatment_plan_payload_sha256"],
                "selected_treatment_plan_payload_sha256",
            ),
            content_sha256=_sha256(item["content_sha256"], "content_sha256"),
            plan_published=_strict_bool(
                item["plan_published"], "plan_published"
            ),
            runtime_ack=_strict_bool(item["runtime_ack"], "runtime_ack"),
            physical_window_available=_strict_bool(
                item["physical_window_available"],
                "physical_window_available",
            ),
            evidence_kind=_required_text(
                item["evidence_kind"], "evidence_kind"
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


def select_a1_intervention_candidate(
    *,
    preregistration: A1InterventionPreRegistration | Mapping[str, Any],
    seed: int,
    candidates: Iterable[
        A1InterventionCandidateEvidence | Mapping[str, Any]
    ],
) -> A1InterventionSelectionDecision:
    """Select the first safe discrete change from a strictly ordered history."""

    registration = validate_a1_intervention_preregistration(preregistration)
    candidate_seed = _nonnegative_int(seed, "seed")
    items: list[A1InterventionCandidateEvidence] = []
    previous_sequence: int | None = None
    previous_timestamp: float | None = None
    for raw in candidates:
        item = validate_a1_intervention_candidate_evidence(raw)
        if item.preregistration.content_sha256 != registration.content_sha256:
            _fail("candidate_preregistration_mismatch")
        if item.seed != candidate_seed:
            _fail("candidate_seed_mismatch")
        if previous_sequence is not None and item.sequence_index <= previous_sequence:
            _fail("candidate_history_not_strictly_ordered")
        if previous_timestamp is not None and item.timestamp_s <= previous_timestamp:
            _fail("candidate_history_timestamp_not_strictly_ordered")
        previous_sequence = item.sequence_index
        previous_timestamp = item.timestamp_s
        items.append(item)

    digests = tuple(item.content_sha256 for item in items)
    history_sha = canonical_runtime_payload_sha256(
        {
            "registration_id": registration.registration_id,
            "seed": candidate_seed,
            "candidate_content_sha256s": digests,
        }
    )
    selected = next(
        (
            item
            for item in items
            if item.selected_for_paired_evaluation
        ),
        None,
    )
    values = {
        "preregistration": registration,
        "seed": candidate_seed,
        "candidate_count": len(items),
        "policy_evaluated_count": sum(
            item.policy_evaluated for item in items
        ),
        "cost_correction_accepted_count": sum(
            item.cost_correction_accepted for item in items
        ),
        "assignment_changed_count": sum(
            item.assignment_changed for item in items
        ),
        "near_competitive_count": sum(
            item.near_competitive for item in items
        ),
        "candidate_content_sha256s": digests,
        "candidate_history_sha256": history_sha,
        "selected": selected is not None,
        "reason": (
            "selected"
            if selected is not None
            else "no_safe_discrete_intervention"
        ),
        "selected_candidate_content_sha256": (
            None if selected is None else selected.content_sha256
        ),
        "selected_sequence_index": (
            None if selected is None else selected.sequence_index
        ),
        "selected_timestamp_s": (
            None if selected is None else selected.timestamp_s
        ),
        "selected_treatment_plan_payload_sha256": (
            None
            if selected is None
            else selected.eligibility.treatment_plan_payload_sha256
        ),
        "plan_published": False,
        "runtime_ack": False,
        "physical_window_available": False,
        "evidence_kind": A1_SELECTION_KIND,
        "schema_version": A1_INTERVENTION_SELECTION_DECISION_SCHEMA_V1,
    }
    return A1InterventionSelectionDecision(
        **values,
        content_sha256=canonical_runtime_payload_sha256(
            _selection_payload(values)
        ),
    )


@dataclass(frozen=True, slots=True)
class A1PlanPublicationEvidence:
    """A verified main bus publication for the selected D3 plan."""

    source_bus_sequence: int
    source_timestamp_s: float
    source_topic: str
    source: str
    plan_id: str
    plan_version: int
    plan_schema_version: str
    assignment_plan_payload_sha256: str
    runtime_plan_payload_sha256: str
    source_envelope_sha256: str
    content_sha256: str
    evidence_kind: str = A1_PUBLICATION_KIND
    schema_version: str = A1_PLAN_PUBLICATION_EVIDENCE_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != A1_PLAN_PUBLICATION_EVIDENCE_SCHEMA_V1:
            _fail("publication_schema_unsupported")
        if self.evidence_kind != A1_PUBLICATION_KIND:
            _fail("publication_kind_invalid")
        _positive_int(self.source_bus_sequence, "source_bus_sequence")
        _finite_nonnegative(self.source_timestamp_s, "source_timestamp_s")
        if self.source_topic != D3_ASSIGNMENT_PLAN_TOPIC:
            _fail("publication_topic_mismatch")
        if self.source != "D3":
            _fail("publication_source_mismatch")
        _required_text(self.plan_id, "plan_id")
        _positive_int(self.plan_version, "plan_version")
        _required_text(self.plan_schema_version, "plan_schema_version")
        for name in (
            "assignment_plan_payload_sha256",
            "runtime_plan_payload_sha256",
            "source_envelope_sha256",
            "content_sha256",
        ):
            _sha256(getattr(self, name), name)
        if self.content_sha256 != _publication_content_sha256(self):
            _fail("publication_content_sha256_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "source_bus_sequence": self.source_bus_sequence,
            "source_timestamp_s": self.source_timestamp_s,
            "source_topic": self.source_topic,
            "source": self.source,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "plan_schema_version": self.plan_schema_version,
            "assignment_plan_payload_sha256": (
                self.assignment_plan_payload_sha256
            ),
            "runtime_plan_payload_sha256": self.runtime_plan_payload_sha256,
            "source_envelope_sha256": self.source_envelope_sha256,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A1PlanPublicationEvidence":
        item = _strict_mapping(
            value, _PUBLICATION_FIELDS, "publication_fields_mismatch"
        )
        return cls(
            source_bus_sequence=_positive_int(
                item["source_bus_sequence"], "source_bus_sequence"
            ),
            source_timestamp_s=_finite_nonnegative(
                item["source_timestamp_s"], "source_timestamp_s"
            ),
            source_topic=_required_text(item["source_topic"], "source_topic"),
            source=_required_text(item["source"], "source"),
            plan_id=_required_text(item["plan_id"], "plan_id"),
            plan_version=_positive_int(item["plan_version"], "plan_version"),
            plan_schema_version=_required_text(
                item["plan_schema_version"], "plan_schema_version"
            ),
            assignment_plan_payload_sha256=_sha256(
                item["assignment_plan_payload_sha256"],
                "assignment_plan_payload_sha256",
            ),
            runtime_plan_payload_sha256=_sha256(
                item["runtime_plan_payload_sha256"],
                "runtime_plan_payload_sha256",
            ),
            source_envelope_sha256=_sha256(
                item["source_envelope_sha256"],
                "source_envelope_sha256",
            ),
            content_sha256=_sha256(item["content_sha256"], "content_sha256"),
            evidence_kind=_required_text(
                item["evidence_kind"], "evidence_kind"
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


def build_a1_plan_publication_evidence(
    *,
    expected_plan: AssignmentPlan,
    source_publication: Mapping[str, Any],
) -> A1PlanPublicationEvidence:
    """Validate one main D3 bus envelope against the exact selected plan."""

    if not isinstance(expected_plan, AssignmentPlan):
        _fail("expected_plan_type_invalid")
    _assert_truth_free(expected_plan)
    plan_sha = validated_assignment_plan_payload_sha256(expected_plan)
    envelope = _strict_mapping(
        source_publication, _ENVELOPE_FIELDS, "publication_envelope_fields_mismatch"
    )
    _assert_truth_free(envelope)
    sequence = _positive_int(envelope["sequence"], "source_bus_sequence")
    topic = _required_text(envelope["topic"], "source_topic")
    source = _required_text(envelope["source"], "source")
    timestamp = _finite_nonnegative(envelope["timestamp"], "source_timestamp_s")
    schema = _required_text(envelope["schema_version"], "plan_schema_version")
    if topic != D3_ASSIGNMENT_PLAN_TOPIC:
        _fail("publication_topic_mismatch")
    if source != "D3":
        _fail("publication_source_mismatch")
    if schema != expected_plan.plan_schema:
        _fail("publication_plan_schema_mismatch")
    if timestamp < float(expected_plan.created_at):
        _fail("publication_precedes_plan_creation")
    payload = _strict_mapping(
        _mapping(envelope["payload"], "runtime_plan_payload"),
        _RUNTIME_PLAN_PAYLOAD_FIELDS,
        "runtime_plan_payload_fields_mismatch",
    )
    expected_payload = _runtime_plan_payload(expected_plan, timestamp)
    runtime_payload_sha = canonical_runtime_payload_sha256(payload)
    if runtime_payload_sha != canonical_runtime_payload_sha256(expected_payload):
        _fail("runtime_plan_payload_mismatch")
    values = {
        "source_bus_sequence": sequence,
        "source_timestamp_s": timestamp,
        "source_topic": topic,
        "source": source,
        "plan_id": expected_plan.plan_id,
        "plan_version": expected_plan.version,
        "plan_schema_version": expected_plan.plan_schema,
        "assignment_plan_payload_sha256": plan_sha,
        "runtime_plan_payload_sha256": runtime_payload_sha,
        "source_envelope_sha256": canonical_runtime_payload_sha256(envelope),
        "evidence_kind": A1_PUBLICATION_KIND,
        "schema_version": A1_PLAN_PUBLICATION_EVIDENCE_SCHEMA_V1,
    }
    return A1PlanPublicationEvidence(
        **values,
        content_sha256=canonical_runtime_payload_sha256(
            _publication_payload(values)
        ),
    )


@dataclass(frozen=True, slots=True)
class A1InterventionLifecycleEvidence:
    """Six-stage A1 evidence assembled without inferring missing runtime facts."""

    registration_id: str
    preregistration_sha256: str
    selection_decision_sha256: str
    candidate_evidence_sha256: str
    plan_id: str
    plan_version: int
    assignment_plan_payload_sha256: str
    policy_evaluated: bool
    cost_correction_accepted: bool
    assignment_changed: bool
    plan_published: bool
    runtime_ack: bool
    physical_window_available: bool
    r0_pair_available: bool
    publication_evidence_sha256: str | None
    runtime_ack_evidence_sha256: str | None
    physical_window_evidence_sha256s: tuple[str, ...]
    required_binding_count: int
    physical_window_binding_count: int
    physical_window_available_binding_count: int
    r0_pair_available_binding_count: int
    status: str
    content_sha256: str
    evidence_kind: str = A1_LIFECYCLE_KIND
    schema_version: str = A1_INTERVENTION_LIFECYCLE_EVIDENCE_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != A1_INTERVENTION_LIFECYCLE_EVIDENCE_SCHEMA_V1:
            _fail("lifecycle_schema_unsupported")
        if self.evidence_kind != A1_LIFECYCLE_KIND:
            _fail("lifecycle_kind_invalid")
        _required_text(self.registration_id, "registration_id")
        for name in (
            "preregistration_sha256",
            "selection_decision_sha256",
            "candidate_evidence_sha256",
            "assignment_plan_payload_sha256",
            "content_sha256",
        ):
            _sha256(getattr(self, name), name)
        _required_text(self.plan_id, "plan_id")
        _positive_int(self.plan_version, "plan_version")
        for name in (
            "policy_evaluated",
            "cost_correction_accepted",
            "assignment_changed",
            "plan_published",
            "runtime_ack",
            "physical_window_available",
            "r0_pair_available",
        ):
            _strict_bool(getattr(self, name), name)
        if not (
            self.policy_evaluated
            and self.cost_correction_accepted
            and self.assignment_changed
        ):
            _fail("selected_candidate_stage_missing")
        publication_sha = _optional_sha256(
            self.publication_evidence_sha256,
            "publication_evidence_sha256",
        )
        ack_sha = _optional_sha256(
            self.runtime_ack_evidence_sha256,
            "runtime_ack_evidence_sha256",
        )
        window_shas = tuple(
            _sha256(value, "physical_window_evidence_sha256")
            for value in self.physical_window_evidence_sha256s
        )
        if len(window_shas) != len(set(window_shas)):
            _fail("physical_window_digest_duplicate")
        required = _positive_int(
            self.required_binding_count, "required_binding_count"
        )
        window_count = _nonnegative_int(
            self.physical_window_binding_count,
            "physical_window_binding_count",
        )
        available_count = _nonnegative_int(
            self.physical_window_available_binding_count,
            "physical_window_available_binding_count",
        )
        r0_pair_count = _nonnegative_int(
            self.r0_pair_available_binding_count,
            "r0_pair_available_binding_count",
        )
        if (
            len(window_shas) != window_count
            or available_count > window_count
            or r0_pair_count > available_count
            or window_count > required
        ):
            _fail("physical_window_count_invalid")
        if self.plan_published != (publication_sha is not None):
            _fail("publication_stage_mismatch")
        if self.runtime_ack != (ack_sha is not None):
            _fail("runtime_ack_stage_mismatch")
        if self.runtime_ack and not self.plan_published:
            _fail("runtime_ack_without_publication")
        expected_physical = (
            self.runtime_ack
            and available_count == required
            and window_count == required
        )
        if self.physical_window_available is not expected_physical:
            _fail("physical_window_stage_mismatch")
        expected_r0_pair = (
            expected_physical and r0_pair_count == required
        )
        if self.r0_pair_available is not expected_r0_pair:
            _fail("r0_pair_stage_mismatch")
        status = _required_text(self.status, "status")
        expected_status = _lifecycle_status(
            plan_published=self.plan_published,
            runtime_ack=self.runtime_ack,
            physical_window_available=self.physical_window_available,
            r0_pair_available=self.r0_pair_available,
        )
        if status != expected_status:
            _fail("lifecycle_status_mismatch")
        object.__setattr__(
            self, "physical_window_evidence_sha256s", window_shas
        )
        if self.content_sha256 != _lifecycle_content_sha256(self):
            _fail("lifecycle_content_sha256_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "registration_id": self.registration_id,
            "preregistration_sha256": self.preregistration_sha256,
            "selection_decision_sha256": self.selection_decision_sha256,
            "candidate_evidence_sha256": self.candidate_evidence_sha256,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "assignment_plan_payload_sha256": (
                self.assignment_plan_payload_sha256
            ),
            "policy_evaluated": self.policy_evaluated,
            "cost_correction_accepted": self.cost_correction_accepted,
            "assignment_changed": self.assignment_changed,
            "plan_published": self.plan_published,
            "runtime_ack": self.runtime_ack,
            "physical_window_available": self.physical_window_available,
            "r0_pair_available": self.r0_pair_available,
            "publication_evidence_sha256": (
                self.publication_evidence_sha256
            ),
            "runtime_ack_evidence_sha256": (
                self.runtime_ack_evidence_sha256
            ),
            "physical_window_evidence_sha256s": list(
                self.physical_window_evidence_sha256s
            ),
            "required_binding_count": self.required_binding_count,
            "physical_window_binding_count": (
                self.physical_window_binding_count
            ),
            "physical_window_available_binding_count": (
                self.physical_window_available_binding_count
            ),
            "r0_pair_available_binding_count": (
                self.r0_pair_available_binding_count
            ),
            "status": self.status,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "A1InterventionLifecycleEvidence":
        item = _strict_mapping(
            value, _LIFECYCLE_FIELDS, "lifecycle_fields_mismatch"
        )
        return cls(
            registration_id=_required_text(
                item["registration_id"], "registration_id"
            ),
            preregistration_sha256=_sha256(
                item["preregistration_sha256"],
                "preregistration_sha256",
            ),
            selection_decision_sha256=_sha256(
                item["selection_decision_sha256"],
                "selection_decision_sha256",
            ),
            candidate_evidence_sha256=_sha256(
                item["candidate_evidence_sha256"],
                "candidate_evidence_sha256",
            ),
            plan_id=_required_text(item["plan_id"], "plan_id"),
            plan_version=_positive_int(item["plan_version"], "plan_version"),
            assignment_plan_payload_sha256=_sha256(
                item["assignment_plan_payload_sha256"],
                "assignment_plan_payload_sha256",
            ),
            policy_evaluated=_strict_bool(
                item["policy_evaluated"], "policy_evaluated"
            ),
            cost_correction_accepted=_strict_bool(
                item["cost_correction_accepted"],
                "cost_correction_accepted",
            ),
            assignment_changed=_strict_bool(
                item["assignment_changed"], "assignment_changed"
            ),
            plan_published=_strict_bool(
                item["plan_published"], "plan_published"
            ),
            runtime_ack=_strict_bool(item["runtime_ack"], "runtime_ack"),
            physical_window_available=_strict_bool(
                item["physical_window_available"],
                "physical_window_available",
            ),
            r0_pair_available=_strict_bool(
                item["r0_pair_available"], "r0_pair_available"
            ),
            publication_evidence_sha256=_optional_sha256(
                item["publication_evidence_sha256"],
                "publication_evidence_sha256",
            ),
            runtime_ack_evidence_sha256=_optional_sha256(
                item["runtime_ack_evidence_sha256"],
                "runtime_ack_evidence_sha256",
            ),
            physical_window_evidence_sha256s=tuple(
                _sha256(value, "physical_window_evidence_sha256")
                for value in _sequence(
                    item["physical_window_evidence_sha256s"],
                    "physical_window_evidence_sha256s",
                )
            ),
            required_binding_count=_positive_int(
                item["required_binding_count"], "required_binding_count"
            ),
            physical_window_binding_count=_nonnegative_int(
                item["physical_window_binding_count"],
                "physical_window_binding_count",
            ),
            physical_window_available_binding_count=_nonnegative_int(
                item["physical_window_available_binding_count"],
                "physical_window_available_binding_count",
            ),
            r0_pair_available_binding_count=_nonnegative_int(
                item["r0_pair_available_binding_count"],
                "r0_pair_available_binding_count",
            ),
            status=_required_text(item["status"], "status"),
            content_sha256=_sha256(item["content_sha256"], "content_sha256"),
            evidence_kind=_required_text(
                item["evidence_kind"], "evidence_kind"
            ),
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
        )


def assemble_a1_intervention_lifecycle(
    *,
    selection: A1InterventionSelectionDecision | Mapping[str, Any],
    selected_candidate: A1InterventionCandidateEvidence | Mapping[str, Any],
    expected_plan: AssignmentPlan,
    publication_evidence: A1PlanPublicationEvidence
    | Mapping[str, Any]
    | None = None,
    runtime_ack_evidence: AssignmentPlanRuntimeAckEvidence | None = None,
    physical_window_evidence: Sequence[RuntimePlanWindowRewardEvidence] = (),
) -> A1InterventionLifecycleEvidence:
    """Join six A1 stages while leaving absent main/D6 evidence unavailable."""

    decision = validate_a1_intervention_selection_decision(selection)
    candidate = validate_a1_intervention_candidate_evidence(
        selected_candidate
    )
    if not decision.selected or not candidate.selected_for_paired_evaluation:
        _fail("selected_candidate_required")
    if (
        candidate.content_sha256
        != decision.selected_candidate_content_sha256
        or candidate.preregistration.content_sha256
        != decision.preregistration.content_sha256
        or candidate.seed != decision.seed
    ):
        _fail("selection_candidate_lineage_mismatch")
    if not isinstance(expected_plan, AssignmentPlan):
        _fail("expected_plan_type_invalid")
    _assert_truth_free(expected_plan)
    plan_sha = validated_assignment_plan_payload_sha256(expected_plan)
    if (
        plan_sha != candidate.eligibility.treatment_plan_payload_sha256
        or plan_sha != decision.selected_treatment_plan_payload_sha256
        or expected_plan.version != candidate.treatment_plan_version
    ):
        _fail("selected_plan_lineage_mismatch")

    publication = (
        None
        if publication_evidence is None
        else validate_a1_plan_publication_evidence(publication_evidence)
    )
    if publication is not None and (
        publication.plan_id != expected_plan.plan_id
        or publication.plan_version != expected_plan.version
        or publication.assignment_plan_payload_sha256 != plan_sha
    ):
        _fail("publication_plan_lineage_mismatch")

    ack_sha: str | None = None
    if runtime_ack_evidence is not None:
        if publication is None:
            _fail("runtime_ack_without_publication")
        ack = _validated_runtime_ack(runtime_ack_evidence)
        if (
            ack.plan_id != expected_plan.plan_id
            or ack.plan_version != expected_plan.version
            or ack.plan_schema_version != expected_plan.plan_schema
            or ack.source_plan_bus_sequence != publication.source_bus_sequence
            or ack.source_plan_payload_sha256
            != publication.runtime_plan_payload_sha256
            or not ack.runtime_learning_applied_ack_available
        ):
            _fail("runtime_ack_plan_lineage_mismatch")
        ack_sha = canonical_runtime_payload_sha256(ack.to_dict())

    windows = tuple(physical_window_evidence)
    if windows and runtime_ack_evidence is None:
        _fail("physical_window_without_runtime_ack")
    expected_bindings = {
        (item.resource_id, item.target_id) for item in expected_plan.assignments
    }
    if not expected_bindings:
        _fail("selected_plan_has_no_executable_bindings")
    window_bindings: set[tuple[str, str]] = set()
    available_bindings: set[tuple[str, str]] = set()
    r0_pair_bindings: set[tuple[str, str]] = set()
    window_hashes: list[str] = []
    for window in windows:
        if not isinstance(window, RuntimePlanWindowRewardEvidence):
            _fail("physical_window_evidence_type_invalid")
        payload = window.to_dict()
        _assert_truth_free(payload)
        reference = window.reference
        binding = (reference.resource_id, reference.global_track_id)
        if (
            reference.plan_id != expected_plan.plan_id
            or reference.plan_version != expected_plan.version
            or publication is None
            or reference.source_plan_bus_sequence
            != publication.source_bus_sequence
            or reference.source_plan_payload_sha256
            != publication.runtime_plan_payload_sha256
            or ack_sha is None
            or reference.runtime_ack_evidence_sha256 != ack_sha
            or binding not in expected_bindings
        ):
            _fail("physical_window_plan_lineage_mismatch")
        if binding in window_bindings:
            _fail("physical_window_binding_duplicate")
        window_bindings.add(binding)
        if (
            window.command.available
            and window.ack_applied.available
            and bool(window.observed_outcomes)
            and window.observed_outcomes[0].available
        ):
            available_bindings.add(binding)
            if window.paired_evidence.available:
                r0_pair_bindings.add(binding)
        window_hashes.append(
            canonical_reward_evidence_payload_sha256(payload)
        )

    physical_available = (
        ack_sha is not None
        and window_bindings == expected_bindings
        and available_bindings == expected_bindings
    )
    r0_pair_available = (
        physical_available and r0_pair_bindings == expected_bindings
    )
    values = {
        "registration_id": candidate.preregistration.registration_id,
        "preregistration_sha256": (
            candidate.preregistration.content_sha256
        ),
        "selection_decision_sha256": decision.content_sha256,
        "candidate_evidence_sha256": candidate.content_sha256,
        "plan_id": expected_plan.plan_id,
        "plan_version": expected_plan.version,
        "assignment_plan_payload_sha256": plan_sha,
        "policy_evaluated": candidate.policy_evaluated,
        "cost_correction_accepted": candidate.cost_correction_accepted,
        "assignment_changed": candidate.assignment_changed,
        "plan_published": publication is not None,
        "runtime_ack": ack_sha is not None,
        "physical_window_available": physical_available,
        "r0_pair_available": r0_pair_available,
        "publication_evidence_sha256": (
            None if publication is None else publication.content_sha256
        ),
        "runtime_ack_evidence_sha256": ack_sha,
        "physical_window_evidence_sha256s": tuple(window_hashes),
        "required_binding_count": len(expected_bindings),
        "physical_window_binding_count": len(window_bindings),
        "physical_window_available_binding_count": len(available_bindings),
        "r0_pair_available_binding_count": len(r0_pair_bindings),
        "status": _lifecycle_status(
            plan_published=publication is not None,
            runtime_ack=ack_sha is not None,
            physical_window_available=physical_available,
            r0_pair_available=r0_pair_available,
        ),
        "evidence_kind": A1_LIFECYCLE_KIND,
        "schema_version": A1_INTERVENTION_LIFECYCLE_EVIDENCE_SCHEMA_V1,
    }
    return A1InterventionLifecycleEvidence(
        **values,
        content_sha256=canonical_runtime_payload_sha256(
            _lifecycle_payload(values)
        ),
    )


def validate_a1_intervention_preregistration(
    value: A1InterventionPreRegistration | Mapping[str, Any],
) -> A1InterventionPreRegistration:
    if isinstance(value, A1InterventionPreRegistration):
        return A1InterventionPreRegistration.from_dict(value.to_dict())
    return A1InterventionPreRegistration.from_dict(
        _mapping(value, "preregistration")
    )


def validate_a1_intervention_candidate_evidence(
    value: A1InterventionCandidateEvidence | Mapping[str, Any],
) -> A1InterventionCandidateEvidence:
    if isinstance(value, A1InterventionCandidateEvidence):
        return A1InterventionCandidateEvidence.from_dict(value.to_dict())
    return A1InterventionCandidateEvidence.from_dict(
        _mapping(value, "candidate_evidence")
    )


def validate_a1_intervention_selection_decision(
    value: A1InterventionSelectionDecision | Mapping[str, Any],
) -> A1InterventionSelectionDecision:
    if isinstance(value, A1InterventionSelectionDecision):
        return A1InterventionSelectionDecision.from_dict(value.to_dict())
    return A1InterventionSelectionDecision.from_dict(
        _mapping(value, "selection_decision")
    )


def validate_a1_plan_publication_evidence(
    value: A1PlanPublicationEvidence | Mapping[str, Any],
) -> A1PlanPublicationEvidence:
    if isinstance(value, A1PlanPublicationEvidence):
        return A1PlanPublicationEvidence.from_dict(value.to_dict())
    return A1PlanPublicationEvidence.from_dict(
        _mapping(value, "publication_evidence")
    )


def validate_a1_intervention_lifecycle_evidence(
    value: A1InterventionLifecycleEvidence | Mapping[str, Any],
) -> A1InterventionLifecycleEvidence:
    if isinstance(value, A1InterventionLifecycleEvidence):
        return A1InterventionLifecycleEvidence.from_dict(value.to_dict())
    return A1InterventionLifecycleEvidence.from_dict(
        _mapping(value, "lifecycle_evidence")
    )


def _candidate_stage_values(
    *,
    preregistration: A1InterventionPreRegistration,
    eligibility: LearningInterventionFrameEvidence,
    seed: int,
    policy_evaluated: bool,
    version_contract_valid: bool,
    max_abs_cost_correction: float,
    rule_basis_score: float | None,
    treatment_rule_basis_score: float | None,
    absolute_rule_cost_difference: float | None,
    relative_rule_cost_difference: float | None,
    rule_unmet_demand_slots: int,
    treatment_unmet_demand_slots: int,
    rule_unmet_high_threat_slots: int,
    treatment_unmet_high_threat_slots: int,
) -> tuple[bool, bool, bool, bool, tuple[str, ...]]:
    allowed_eligibility = (
        eligibility.reason_codes == ("eligible",)
        or eligibility.reason_codes == ("binding_unchanged",)
    )
    correction_within_bound = (
        max_abs_cost_correction
        <= preregistration.max_abs_cost_correction + 1.0e-12
    )
    demand_not_degraded = (
        treatment_unmet_demand_slots <= rule_unmet_demand_slots
    )
    high_threat_not_degraded = (
        treatment_unmet_high_threat_slots
        <= rule_unmet_high_threat_slots
    )
    cost_accepted = (
        policy_evaluated
        and allowed_eligibility
        and version_contract_valid
        and correction_within_bound
        and demand_not_degraded
        and high_threat_not_degraded
    )
    assignment_changed = (
        cost_accepted and eligibility.binding_change_count > 0
    )
    score_available = all(
        value is not None
        for value in (
            rule_basis_score,
            treatment_rule_basis_score,
            absolute_rule_cost_difference,
            relative_rule_cost_difference,
        )
    )
    binding_limit_ok = (
        eligibility.binding_change_count
        <= preregistration.max_binding_change_count
    )
    near_competitive = bool(
        assignment_changed
        and score_available
        and binding_limit_ok
        and float(absolute_rule_cost_difference)
        <= preregistration.max_rule_cost_difference + 1.0e-12
        and float(relative_rule_cost_difference)
        <= preregistration.max_relative_rule_cost_difference + 1.0e-12
    )
    scope_ok = (
        seed in preregistration.evaluation_seeds
        and preregistration.sequence_index_min
        <= eligibility.sequence_index
        <= preregistration.sequence_index_max
        and preregistration.timestamp_s_min
        <= eligibility.timestamp_s
        <= preregistration.timestamp_s_max
    )
    nonempty_treatment = eligibility.treatment_assignment_count > 0
    selected = near_competitive and scope_ok and nonempty_treatment
    if selected:
        return True, True, True, True, ("selected",)

    reasons: list[str] = []
    if not scope_ok:
        reasons.append("registration_scope_mismatch")
    if not policy_evaluated:
        reasons.append("policy_not_evaluated")
    if not allowed_eligibility:
        reasons.append("safety_shell_rejected")
    if not version_contract_valid:
        reasons.append("version_contract_rejected")
    if not correction_within_bound:
        reasons.append("cost_correction_bound_exceeded")
    if not demand_not_degraded:
        reasons.append("demand_coverage_degraded")
    if not high_threat_not_degraded:
        reasons.append("high_threat_coverage_degraded")
    if cost_accepted and eligibility.binding_change_count == 0:
        reasons.append("assignment_unchanged")
    if assignment_changed and not binding_limit_ok:
        reasons.append("binding_change_limit_exceeded")
    if assignment_changed and not score_available:
        reasons.append("rule_cost_basis_unavailable")
    if (
        assignment_changed
        and score_available
        and binding_limit_ok
        and not near_competitive
    ):
        reasons.append("not_near_competitive")
    if not nonempty_treatment:
        reasons.append("empty_treatment_assignment")
    if not reasons:
        reasons.append("safety_shell_rejected")
    return (
        cost_accepted,
        assignment_changed,
        near_competitive,
        False,
        tuple(reasons),
    )


def _policy_evaluation(
    treatment_frame: PlanningFrameEvidence,
) -> tuple[bool, str]:
    try:
        _assert_truth_free(treatment_frame)
        result = treatment_frame.effective_matrix_result
        if result is None:
            raise ValueError("effective matrix unavailable")
        metadata = result.metadata
        payload = {
            "learning_residual_schema": metadata.get(
                "learning_residual_schema"
            ),
            "learning_mode": metadata.get("learning_mode"),
            "learning_formula": metadata.get("learning_formula"),
            "learning_alpha": metadata.get("learning_alpha"),
            "learning_candidate_action_count": metadata.get(
                "learning_candidate_action_count"
            ),
            "learning_expected_previous_version": metadata.get(
                "learning_expected_previous_version"
            ),
            "learning_current_plan_version": metadata.get(
                "learning_current_plan_version"
            ),
            "learning_inference_elapsed_s": metadata.get(
                "learning_inference_elapsed_s"
            ),
            "learning_timeout_s": metadata.get("learning_timeout_s"),
            "learning_confidence": metadata.get("learning_confidence"),
            "learning_min_confidence": metadata.get(
                "learning_min_confidence"
            ),
            "learning_distribution_is_ood": metadata.get(
                "learning_distribution_is_ood"
            ),
            "learning_fallback_reason": metadata.get(
                "learning_fallback_reason"
            ),
        }
        _assert_all_finite(payload)
        evaluated = (
            payload["learning_mode"] == "assist"
            and payload["learning_residual_schema"] is not None
            and _is_finite_number(payload["learning_inference_elapsed_s"])
            and _is_finite_number(payload["learning_timeout_s"])
            and _is_finite_number(payload["learning_confidence"])
            and _is_finite_number(payload["learning_min_confidence"])
            and payload["learning_distribution_is_ood"] is False
            and payload["learning_fallback_reason"] is None
        )
        return bool(evaluated), canonical_runtime_payload_sha256(payload)
    except (A1InterventionContractError, TypeError, ValueError, AttributeError):
        return False, canonical_runtime_payload_sha256(
            {"policy_evaluation": "unavailable"}
        )


def _maximum_safe_cost_correction(
    rule_frame: PlanningFrameEvidence,
    treatment_frame: PlanningFrameEvidence,
) -> float:
    try:
        rule = np.asarray(rule_frame.rule_matrix, dtype=float)
        effective = np.asarray(treatment_frame.effective_matrix, dtype=float)
        result = treatment_frame.rule_matrix_result
        if (
            result is None
            or rule.shape != effective.shape
            or not np.all(np.isfinite(rule))
            or not np.all(np.isfinite(effective))
        ):
            return 1.0e308
        mask = np.asarray(result.hard_safe_candidate_mask, dtype=bool)
        if mask.shape != rule.shape:
            return 1.0e308
        changed = np.abs(effective - rule)
        if np.any(changed[~mask] > 1.0e-12):
            return 1.0e308
        return float(np.max(changed[mask])) if np.any(mask) else 0.0
    except (TypeError, ValueError, AttributeError):
        return 1.0e308


def _rule_basis_comparison(
    *,
    rule_frame: PlanningFrameEvidence,
    treatment_frame: PlanningFrameEvidence,
    high_threat_threshold: float,
) -> tuple[
    float | None,
    float | None,
    float | None,
    float | None,
    int,
    int,
    int,
    int,
]:
    try:
        result = rule_frame.rule_matrix_result
        rule_plan = rule_frame.plan
        treatment_plan = treatment_frame.plan
        if result is None or rule_plan is None or treatment_plan is None:
            raise ValueError("planning input unavailable")
        rule = _score_plan_on_rule_basis(
            rule_plan,
            result=result,
            frame=rule_frame,
            high_threat_threshold=high_threat_threshold,
        )
        treatment = _score_plan_on_rule_basis(
            treatment_plan,
            result=result,
            frame=rule_frame,
            high_threat_threshold=high_threat_threshold,
        )
        difference = abs(treatment[0] - rule[0])
        relative = difference / max(abs(rule[0]), 1.0e-12)
        return (
            rule[0],
            treatment[0],
            float(difference),
            float(relative),
            rule[1],
            treatment[1],
            rule[2],
            treatment[2],
        )
    except (TypeError, ValueError, KeyError, AttributeError):
        return None, None, None, None, 0, 0, 0, 0


def _score_plan_on_rule_basis(
    plan: AssignmentPlan,
    *,
    result: Any,
    frame: PlanningFrameEvidence,
    high_threat_threshold: float,
) -> tuple[float, int, int]:
    target_index = {value: index for index, value in enumerate(result.target_ids)}
    resource_index = {
        value: index for index, value in enumerate(result.resource_ids)
    }
    matrix = np.asarray(result.matrix, dtype=float)
    unassigned = np.asarray(result.unassigned_costs, dtype=float)
    mask = np.asarray(result.hard_safe_candidate_mask, dtype=bool)
    if (
        matrix.shape != mask.shape
        or unassigned.shape != (len(result.target_ids),)
        or not np.all(np.isfinite(matrix))
        or not np.all(np.isfinite(unassigned))
    ):
        raise ValueError("rule cost basis invalid")
    assigned = Counter(item.target_id for item in plan.assignments)
    used_resources: set[str] = set()
    total = 0.0
    for assignment in plan.assignments:
        row = target_index[assignment.target_id]
        column = resource_index[assignment.resource_id]
        if assignment.resource_id in used_resources or not mask[row, column]:
            raise ValueError("unsafe assignment in rule-basis score")
        used_resources.add(assignment.resource_id)
        total += float(matrix[row, column])
    unmet = 0
    high_threat_unmet = 0
    for index, track in enumerate(frame.tracks):
        shortfall = max(
            0,
            int(track.effective_demand.required_resource_count)
            - assigned.get(track.track_id, 0),
        )
        total += shortfall * float(unassigned[index])
        unmet += shortfall
        if float(track.threat_score) >= high_threat_threshold:
            high_threat_unmet += shortfall
    if not isfinite(total):
        raise ValueError("nonfinite rule-basis score")
    return float(total), int(unmet), int(high_threat_unmet)


def _strict_changed_plan_version_contract(
    *,
    treatment_frame: PlanningFrameEvidence,
    binding_change_count: int,
) -> bool:
    plan = treatment_frame.plan
    previous = treatment_frame.previous_plan
    if plan is None or previous is None:
        return False
    if binding_change_count > 0:
        return (
            plan.version == previous.version + 1
            and plan.previous_plan_id == previous.plan_id
            and plan.plan_id != previous.plan_id
        )
    if plan.execution_signature() == previous.execution_signature():
        return (
            plan.version == previous.version
            and plan.plan_id == previous.plan_id
        ) or (
            plan.version == previous.version + 1
            and plan.previous_plan_id == previous.plan_id
        )
    return (
        plan.version == previous.version + 1
        and plan.previous_plan_id == previous.plan_id
    )


def _runtime_plan_payload(
    plan: AssignmentPlan,
    timestamp_s: float,
) -> dict[str, Any]:
    assignments = [
        {
            "resource_id": item.resource_id,
            "global_track_id": item.target_id,
            "coalition_id": item.coalition_id,
            "coalition_version": item.coalition_version,
            "member_role": item.member_role,
            "owner_node_id": item.metadata.get("owner_node_id"),
            "regional_owner_layer": item.metadata.get(
                "regional_owner_layer"
            ),
            "regional_region_id": item.metadata.get("regional_region_id"),
            "regional_epoch": item.metadata.get("regional_epoch"),
            "regional_commit_mode": item.metadata.get(
                "regional_commit_mode"
            ),
        }
        for item in plan.assignments
    ]
    return {
        "timestamp": float(timestamp_s),
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "created_at": plan.created_at,
        "assignment_count": len(plan.assignments),
        "target_count": plan.target_count,
        "resource_count": plan.resource_count,
        "assignments": assignments,
        "unassigned_global_track_ids": list(plan.unassigned_target_ids),
        "solver_name": plan.solver_name,
        "metadata": dict(plan.metadata),
    }


def _validated_runtime_ack(
    value: AssignmentPlanRuntimeAckEvidence,
) -> AssignmentPlanRuntimeAckEvidence:
    identity = (type(value).__module__, type(value).__name__)
    supported = {
        (
            "d3_assignment_planner.runtime_plan_ack",
            "AssignmentPlanRuntimeAckEvidence",
        ),
        (
            "research_modules.d3_assignment_planner.src."
            "d3_assignment_planner.runtime_plan_ack",
            "AssignmentPlanRuntimeAckEvidence",
        ),
    }
    if (
        not isinstance(value, AssignmentPlanRuntimeAckEvidence)
        and identity not in supported
    ):
        _fail("runtime_ack_evidence_type_invalid")
    if not is_dataclass(value) or isinstance(value, type):
        _fail("runtime_ack_evidence_type_invalid")
    expected_fields = frozenset(
        item.name for item in fields(AssignmentPlanRuntimeAckEvidence)
    )
    if frozenset(item.name for item in fields(value)) != expected_fields:
        _fail("runtime_ack_evidence_fields_mismatch")
    payload = value.to_dict()
    _assert_truth_free(payload)
    if (
        value.accepted is not True
        or value.status_code != "accepted_by_main_runtime"
        or value.physical_outcome_available
        or value.reward_available
    ):
        _fail("runtime_ack_evidence_invalid")
    return value


def _lifecycle_status(
    *,
    plan_published: bool,
    runtime_ack: bool,
    physical_window_available: bool,
    r0_pair_available: bool,
) -> str:
    if not plan_published:
        return "selected_not_published"
    if not runtime_ack:
        return "published_waiting_runtime_ack"
    if not physical_window_available:
        return "runtime_ack_waiting_complete_physical_window"
    if not r0_pair_available:
        return "physical_window_available_waiting_r0_pair"
    return "r0_pair_available"


def _registration_base_payload(value: A1InterventionPreRegistration) -> dict[str, Any]:
    payload = value.to_dict()
    payload.pop("registration_id", None)
    payload.pop("content_sha256", None)
    return payload


def _registration_id(value: A1InterventionPreRegistration) -> str:
    return _registration_id_from_values(_registration_base_payload(value))


def _registration_id_from_values(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("registration_id", None)
    payload.pop("content_sha256", None)
    digest = canonical_runtime_payload_sha256(payload)
    return f"a1-prereg-{digest[:24]}"


def _candidate_payload(
    *,
    values: Mapping[str, Any],
    cost_correction_accepted: bool,
    assignment_changed: bool,
    near_competitive: bool,
    selected_for_paired_evaluation: bool,
    reason_codes: Sequence[str],
) -> dict[str, Any]:
    preregistration = values["preregistration"]
    eligibility = values["eligibility"]
    if not isinstance(preregistration, A1InterventionPreRegistration):
        _fail("preregistration_type_invalid")
    if not isinstance(eligibility, LearningInterventionFrameEvidence):
        _fail("eligibility_type_invalid")
    return {
        "schema_version": values["schema_version"],
        "evidence_kind": values["evidence_kind"],
        "preregistration": preregistration.to_dict(),
        "eligibility": eligibility.to_dict(),
        "seed": values["seed"],
        "policy_evaluated": values["policy_evaluated"],
        "policy_evaluation_sha256": values["policy_evaluation_sha256"],
        "cost_correction_accepted": cost_correction_accepted,
        "assignment_changed": assignment_changed,
        "near_competitive": near_competitive,
        "selected_for_paired_evaluation": selected_for_paired_evaluation,
        "version_contract_valid": values["version_contract_valid"],
        "max_abs_cost_correction": values["max_abs_cost_correction"],
        "rule_basis_score": values["rule_basis_score"],
        "treatment_rule_basis_score": values["treatment_rule_basis_score"],
        "absolute_rule_cost_difference": values[
            "absolute_rule_cost_difference"
        ],
        "relative_rule_cost_difference": values[
            "relative_rule_cost_difference"
        ],
        "rule_unmet_demand_slots": values["rule_unmet_demand_slots"],
        "treatment_unmet_demand_slots": values[
            "treatment_unmet_demand_slots"
        ],
        "rule_unmet_high_threat_slots": values[
            "rule_unmet_high_threat_slots"
        ],
        "treatment_unmet_high_threat_slots": values[
            "treatment_unmet_high_threat_slots"
        ],
        "rule_plan_version": values["rule_plan_version"],
        "treatment_plan_version": values["treatment_plan_version"],
        "previous_plan_version": values["previous_plan_version"],
        "reason_codes": list(reason_codes),
        "plan_published": values["plan_published"],
        "runtime_ack": values["runtime_ack"],
        "physical_window_available": values["physical_window_available"],
    }


def _selection_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    preregistration = values["preregistration"]
    if not isinstance(preregistration, A1InterventionPreRegistration):
        _fail("preregistration_type_invalid")
    return {
        "schema_version": values["schema_version"],
        "evidence_kind": values["evidence_kind"],
        "preregistration": preregistration.to_dict(),
        "seed": values["seed"],
        "candidate_count": values["candidate_count"],
        "policy_evaluated_count": values["policy_evaluated_count"],
        "cost_correction_accepted_count": values[
            "cost_correction_accepted_count"
        ],
        "assignment_changed_count": values["assignment_changed_count"],
        "near_competitive_count": values["near_competitive_count"],
        "candidate_content_sha256s": list(
            values["candidate_content_sha256s"]
        ),
        "candidate_history_sha256": values["candidate_history_sha256"],
        "selected": values["selected"],
        "reason": values["reason"],
        "selected_candidate_content_sha256": values[
            "selected_candidate_content_sha256"
        ],
        "selected_sequence_index": values["selected_sequence_index"],
        "selected_timestamp_s": values["selected_timestamp_s"],
        "selected_treatment_plan_payload_sha256": values[
            "selected_treatment_plan_payload_sha256"
        ],
        "plan_published": values["plan_published"],
        "runtime_ack": values["runtime_ack"],
        "physical_window_available": values["physical_window_available"],
    }


def _publication_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "evidence_kind": values["evidence_kind"],
        "source_bus_sequence": values["source_bus_sequence"],
        "source_timestamp_s": values["source_timestamp_s"],
        "source_topic": values["source_topic"],
        "source": values["source"],
        "plan_id": values["plan_id"],
        "plan_version": values["plan_version"],
        "plan_schema_version": values["plan_schema_version"],
        "assignment_plan_payload_sha256": values[
            "assignment_plan_payload_sha256"
        ],
        "runtime_plan_payload_sha256": values[
            "runtime_plan_payload_sha256"
        ],
        "source_envelope_sha256": values["source_envelope_sha256"],
    }


def _lifecycle_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "evidence_kind": values["evidence_kind"],
        "registration_id": values["registration_id"],
        "preregistration_sha256": values["preregistration_sha256"],
        "selection_decision_sha256": values[
            "selection_decision_sha256"
        ],
        "candidate_evidence_sha256": values["candidate_evidence_sha256"],
        "plan_id": values["plan_id"],
        "plan_version": values["plan_version"],
        "assignment_plan_payload_sha256": values[
            "assignment_plan_payload_sha256"
        ],
        "policy_evaluated": values["policy_evaluated"],
        "cost_correction_accepted": values[
            "cost_correction_accepted"
        ],
        "assignment_changed": values["assignment_changed"],
        "plan_published": values["plan_published"],
        "runtime_ack": values["runtime_ack"],
        "physical_window_available": values["physical_window_available"],
        "r0_pair_available": values["r0_pair_available"],
        "publication_evidence_sha256": values[
            "publication_evidence_sha256"
        ],
        "runtime_ack_evidence_sha256": values[
            "runtime_ack_evidence_sha256"
        ],
        "physical_window_evidence_sha256s": list(
            values["physical_window_evidence_sha256s"]
        ),
        "required_binding_count": values["required_binding_count"],
        "physical_window_binding_count": values[
            "physical_window_binding_count"
        ],
        "physical_window_available_binding_count": values[
            "physical_window_available_binding_count"
        ],
        "r0_pair_available_binding_count": values[
            "r0_pair_available_binding_count"
        ],
        "status": values["status"],
    }


def _preregistration_content_sha256(
    value: A1InterventionPreRegistration,
) -> str:
    payload = value.to_dict()
    payload.pop("content_sha256", None)
    return canonical_runtime_payload_sha256(payload)


def _candidate_content_sha256(
    value: A1InterventionCandidateEvidence,
) -> str:
    payload = value.to_dict()
    payload.pop("content_sha256", None)
    return canonical_runtime_payload_sha256(payload)


def _selection_content_sha256(
    value: A1InterventionSelectionDecision,
) -> str:
    payload = value.to_dict()
    payload.pop("content_sha256", None)
    return canonical_runtime_payload_sha256(payload)


def _publication_content_sha256(
    value: A1PlanPublicationEvidence,
) -> str:
    payload = value.to_dict()
    payload.pop("content_sha256", None)
    return canonical_runtime_payload_sha256(payload)


def _lifecycle_content_sha256(
    value: A1InterventionLifecycleEvidence,
) -> str:
    payload = value.to_dict()
    payload.pop("content_sha256", None)
    return canonical_runtime_payload_sha256(payload)


def _plan_version(plan: AssignmentPlan | None) -> int:
    return 0 if plan is None else _nonnegative_int(plan.version, "plan_version")


def _assert_truth_free(value: Any, path: str = "$") -> None:
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            key = str(item.name).strip().lower()
            if _is_forbidden_online_key(key):
                _fail("online_truth_input_rejected", f"forbidden key at {path}.{key}")
            _assert_truth_free(getattr(value, item.name), f"{path}.{item.name}")
        return
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            if (
                _is_forbidden_online_key(key)
                and not path.endswith(".source_artifact_sha256s")
            ):
                _fail("online_truth_input_rejected", f"forbidden key at {path}.{key}")
            _assert_truth_free(item, f"{path}.{raw_key}")
        return
    if isinstance(value, (str, bytes, bytearray)):
        return
    if isinstance(value, np.ndarray):
        return
    if isinstance(value, Sequence):
        for index, item in enumerate(value):
            _assert_truth_free(item, f"{path}[{index}]")


def _is_forbidden_online_key(key: str) -> bool:
    normalized = str(key).strip().lower()
    if normalized in _FORBIDDEN_ONLINE_KEYS or normalized.startswith("truth_"):
        return True
    if any(marker in normalized for marker in _FORBIDDEN_TRUTH_KEY_MARKERS):
        return True
    parts = frozenset(part for part in normalized.split("_") if part)
    return bool(
        parts.intersection({"actor", "object"})
        and parts.intersection(_IDENTITY_KEY_QUALIFIERS)
    )


def _assert_all_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_all_finite(item, f"{path}.{key}")
        return
    if isinstance(value, np.ndarray):
        if not np.all(np.isfinite(value)):
            _fail("policy_evaluation_nonfinite", path)
        return
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, item in enumerate(value):
            _assert_all_finite(item, f"{path}[{index}]")
        return
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        if not isfinite(float(value)):
            _fail("policy_evaluation_nonfinite", path)


def _strict_mapping(
    value: Mapping[str, Any],
    fields_: frozenset[str],
    code: str,
) -> Mapping[str, Any]:
    item = _mapping(value, code)
    if set(item) != fields_:
        _fail(code)
    _assert_truth_free(item)
    return item


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", context)
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        _fail("sequence_required", context)
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("required_text_missing", context)
    return value.strip()


def _strict_bool(value: Any, context: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        _fail("strict_bool_required", context)
    return bool(value)


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, np.integer)
    ):
        _fail("nonnegative_int_required", context)
    result = int(value)
    if result < 0:
        _fail("nonnegative_int_required", context)
    return result


def _positive_int(value: Any, context: str) -> int:
    result = _nonnegative_int(value, context)
    if result < 1:
        _fail("positive_int_required", context)
    return result


def _optional_nonnegative_int(value: Any, context: str) -> int | None:
    return None if value is None else _nonnegative_int(value, context)


def _finite(value: Any, context: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        _fail("finite_number_required", context)
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise A1InterventionContractError(
            "finite_number_required", context
        ) from exc
    if not isfinite(result):
        _fail("finite_number_required", context)
    return result


def _finite_nonnegative(value: Any, context: str) -> float:
    result = _finite(value, context)
    if result < 0.0:
        _fail("finite_nonnegative_required", context)
    return result


def _finite_positive(value: Any, context: str) -> float:
    result = _finite(value, context)
    if result <= 0.0:
        _fail("finite_positive_required", context)
    return result


def _optional_finite(value: Any, context: str) -> float | None:
    return None if value is None else _finite(value, context)


def _optional_finite_nonnegative(
    value: Any, context: str
) -> float | None:
    return None if value is None else _finite_nonnegative(value, context)


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return False
    try:
        return isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _sha256(value: Any, context: str) -> str:
    text = _required_text(value, context).lower()
    if (
        len(text) != 64
        or any(character not in _HEX_DIGITS for character in text)
        or text == "0" * 64
    ):
        _fail("sha256_required", context)
    return text


def _optional_sha256(value: Any, context: str) -> str | None:
    return None if value is None else _sha256(value, context)


def _fail(code: str, message: str | None = None) -> None:
    raise A1InterventionContractError(code, message)
