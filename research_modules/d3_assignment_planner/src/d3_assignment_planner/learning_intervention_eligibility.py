"""Truth-free qualification of D3 learning-intervention candidate frames.

The contract in this module is deliberately narrower than model admission or
runtime authority.  It proves that one treatment planning frame used the same
input as its rule control, changed at least one guarded cost and one executable
binding, and still satisfies D3 plan/version/demand contracts.  Main may use
the result to pre-register a common checkpoint before a later physical replay.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any

import numpy as np

from .costs import CostMatrixResult
from .models import (
    AssignmentPlan,
    CoalitionMemberRole,
    CoalitionState,
)
from .offline_intervention_execution import (
    canonical_learning_action_mask_sha256,
    canonical_planning_frame_snapshot_sha256,
    canonical_rule_cost_matrix_sha256,
)
from .planning_evidence import (
    PLANNING_FRAME_EVIDENCE_SCHEMA_V1,
    PlanningFrameEvidence,
)
from .runtime_plan_ack import (
    canonical_runtime_payload_sha256,
    validated_assignment_plan_payload_sha256,
)


LEARNING_INTERVENTION_FRAME_EVIDENCE_SCHEMA_V1 = (
    "d3.learning-intervention-frame-evidence.v1"
)
LEARNING_INTERVENTION_FRAME_EVIDENCE_KIND = (
    "truth-free-learning-intervention-candidate-frame"
)
LEARNING_INTERVENTION_SELECTION_SCOPE = (
    "checkpoint-selection-only-no-admission-no-authority"
)

LEARNING_INTERVENTION_REASON_CODES = (
    "eligible",
    "rule_frame_unavailable",
    "treatment_frame_unavailable",
    "planning_frame_schema_unsupported",
    "online_truth_input_rejected",
    "frame_input_invalid",
    "frame_input_lineage_mismatch",
    "planning_path_mismatch",
    "selection_source_mismatch",
    "frame_timestamp_mismatch",
    "previous_plan_missing",
    "previous_plan_lineage_mismatch",
    "stale_plan_version",
    "stale_plan_time_window",
    "rule_control_state_invalid",
    "rule_matrix_invalid",
    "treatment_matrix_invalid",
    "action_mask_mismatch",
    "learning_changed_hard_rejected_cost",
    "learning_metadata_incomplete",
    "learning_not_applied",
    "learning_application_count_mismatch",
    "learning_application_count_zero",
    "learning_fallback_present",
    "learning_ood",
    "learning_timeout",
    "learning_nonfinite",
    "rule_plan_invalid",
    "treatment_plan_invalid",
    "rule_plan_infeasible",
    "treatment_plan_infeasible",
    "rule_plan_hard_constraint_violation",
    "treatment_plan_hard_constraint_violation",
    "rule_demand_slot_contract_incomplete",
    "treatment_demand_slot_contract_incomplete",
    "rule_m_to_n_all_or_none_incomplete",
    "treatment_m_to_n_all_or_none_incomplete",
    "binding_unchanged",
)

_REASON_SET = frozenset(LEARNING_INTERVENTION_REASON_CODES)
_SHA_FIELD_NAMES = (
    "input_snapshot_sha256",
    "previous_plan_payload_sha256",
    "rule_matrix_sha256",
    "treatment_matrix_sha256",
    "action_mask_sha256",
    "rule_plan_payload_sha256",
    "treatment_plan_payload_sha256",
    "rule_binding_sha256",
    "treatment_binding_sha256",
)
_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "selection_scope",
        "sequence_index",
        "timestamp_s",
        "planning_path",
        "eligible",
        "reason_codes",
        *_SHA_FIELD_NAMES,
        "model_applied_edge_count",
        "binding_change_count",
        "rule_assignment_count",
        "treatment_assignment_count",
        "demand_slot_count",
        "m_to_n_target_count",
        "rule_hard_violation_count",
        "treatment_hard_violation_count",
        "fallback_reason",
        "canonical_summary",
        "content_sha256",
    }
)
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


class LearningInterventionEligibilityError(ValueError):
    """Raised when candidate evidence itself is malformed or tampered."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        self.reason = self.code
        super().__init__(
            self.code if message is None else f"{self.code}: {message}"
        )


@dataclass(frozen=True, slots=True)
class LearningInterventionFrameEvidence:
    """Versioned result for one rule/treatment planning-frame pair."""

    schema_version: str
    evidence_kind: str
    selection_scope: str
    sequence_index: int
    timestamp_s: float
    planning_path: str
    eligible: bool
    reason_codes: tuple[str, ...]
    input_snapshot_sha256: str
    previous_plan_payload_sha256: str
    rule_matrix_sha256: str
    treatment_matrix_sha256: str
    action_mask_sha256: str
    rule_plan_payload_sha256: str
    treatment_plan_payload_sha256: str
    rule_binding_sha256: str
    treatment_binding_sha256: str
    model_applied_edge_count: int
    binding_change_count: int
    rule_assignment_count: int
    treatment_assignment_count: int
    demand_slot_count: int
    m_to_n_target_count: int
    rule_hard_violation_count: int
    treatment_hard_violation_count: int
    fallback_reason: str | None
    canonical_summary: Mapping[str, Any]
    content_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != LEARNING_INTERVENTION_FRAME_EVIDENCE_SCHEMA_V1:
            _fail("evidence_schema_unsupported")
        if self.evidence_kind != LEARNING_INTERVENTION_FRAME_EVIDENCE_KIND:
            _fail("evidence_kind_invalid")
        if self.selection_scope != LEARNING_INTERVENTION_SELECTION_SCOPE:
            _fail("selection_scope_invalid")
        _nonnegative_int(self.sequence_index, "sequence_index")
        _finite_nonnegative(self.timestamp_s, "timestamp_s")
        _required_text(self.planning_path, "planning_path")
        _strict_bool(self.eligible, "eligible")
        reason_codes = tuple(
            _required_text(value, "reason_code") for value in self.reason_codes
        )
        if not reason_codes or len(reason_codes) != len(set(reason_codes)):
            _fail("reason_codes_invalid")
        if any(value not in _REASON_SET for value in reason_codes):
            _fail("reason_code_unsupported")
        expected_eligible = reason_codes == ("eligible",)
        if self.eligible is not expected_eligible:
            _fail("manual_eligibility_boolean_rejected")
        for name in _SHA_FIELD_NAMES:
            _nonplaceholder_sha256(getattr(self, name), name)
        for name in (
            "model_applied_edge_count",
            "binding_change_count",
            "rule_assignment_count",
            "treatment_assignment_count",
            "demand_slot_count",
            "m_to_n_target_count",
            "rule_hard_violation_count",
            "treatment_hard_violation_count",
        ):
            _nonnegative_int(getattr(self, name), name)
        if self.eligible and (
            self.model_applied_edge_count < 1
            or self.binding_change_count < 1
            or self.rule_hard_violation_count != 0
            or self.treatment_hard_violation_count != 0
            or self.fallback_reason is not None
        ):
            _fail("positive_evidence_invariant_invalid")
        if self.fallback_reason is not None:
            _required_text(self.fallback_reason, "fallback_reason")

        expected_summary = _canonical_summary(
            sequence_index=self.sequence_index,
            timestamp_s=self.timestamp_s,
            planning_path=self.planning_path,
            eligible=self.eligible,
            reason_codes=reason_codes,
            input_snapshot_sha256=self.input_snapshot_sha256,
            previous_plan_payload_sha256=self.previous_plan_payload_sha256,
            rule_matrix_sha256=self.rule_matrix_sha256,
            treatment_matrix_sha256=self.treatment_matrix_sha256,
            action_mask_sha256=self.action_mask_sha256,
            rule_plan_payload_sha256=self.rule_plan_payload_sha256,
            treatment_plan_payload_sha256=self.treatment_plan_payload_sha256,
            rule_binding_sha256=self.rule_binding_sha256,
            treatment_binding_sha256=self.treatment_binding_sha256,
            model_applied_edge_count=self.model_applied_edge_count,
            binding_change_count=self.binding_change_count,
            rule_assignment_count=self.rule_assignment_count,
            treatment_assignment_count=self.treatment_assignment_count,
            demand_slot_count=self.demand_slot_count,
            m_to_n_target_count=self.m_to_n_target_count,
            rule_hard_violation_count=self.rule_hard_violation_count,
            treatment_hard_violation_count=self.treatment_hard_violation_count,
            fallback_reason=self.fallback_reason,
        )
        if canonical_runtime_payload_sha256(self.canonical_summary) != (
            canonical_runtime_payload_sha256(expected_summary)
        ):
            _fail("canonical_summary_mismatch")
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(
            self,
            "canonical_summary",
            _freeze_json_mapping(expected_summary),
        )
        expected_content_sha256 = (
            canonical_learning_intervention_frame_evidence_sha256(self)
        )
        _nonplaceholder_sha256(self.content_sha256, "content_sha256")
        if self.content_sha256 != expected_content_sha256:
            _fail("evidence_content_sha256_mismatch")

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-native evidence payload."""

        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "selection_scope": self.selection_scope,
            "sequence_index": self.sequence_index,
            "timestamp_s": self.timestamp_s,
            "planning_path": self.planning_path,
            "eligible": self.eligible,
            "reason_codes": list(self.reason_codes),
            "input_snapshot_sha256": self.input_snapshot_sha256,
            "previous_plan_payload_sha256": self.previous_plan_payload_sha256,
            "rule_matrix_sha256": self.rule_matrix_sha256,
            "treatment_matrix_sha256": self.treatment_matrix_sha256,
            "action_mask_sha256": self.action_mask_sha256,
            "rule_plan_payload_sha256": self.rule_plan_payload_sha256,
            "treatment_plan_payload_sha256": self.treatment_plan_payload_sha256,
            "rule_binding_sha256": self.rule_binding_sha256,
            "treatment_binding_sha256": self.treatment_binding_sha256,
            "model_applied_edge_count": self.model_applied_edge_count,
            "binding_change_count": self.binding_change_count,
            "rule_assignment_count": self.rule_assignment_count,
            "treatment_assignment_count": self.treatment_assignment_count,
            "demand_slot_count": self.demand_slot_count,
            "m_to_n_target_count": self.m_to_n_target_count,
            "rule_hard_violation_count": self.rule_hard_violation_count,
            "treatment_hard_violation_count": (
                self.treatment_hard_violation_count
            ),
            "fallback_reason": self.fallback_reason,
            "canonical_summary": _json_native(self.canonical_summary),
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "LearningInterventionFrameEvidence":
        """Load strict evidence and reject omissions, extras and tampering."""

        item = _strict_mapping(value, _EVIDENCE_FIELDS, "evidence_fields_mismatch")
        return cls(
            schema_version=_required_text(
                item["schema_version"], "schema_version"
            ),
            evidence_kind=_required_text(item["evidence_kind"], "evidence_kind"),
            selection_scope=_required_text(
                item["selection_scope"], "selection_scope"
            ),
            sequence_index=_nonnegative_int(
                item["sequence_index"], "sequence_index"
            ),
            timestamp_s=_finite_nonnegative(item["timestamp_s"], "timestamp_s"),
            planning_path=_required_text(
                item["planning_path"], "planning_path"
            ),
            eligible=_strict_bool(item["eligible"], "eligible"),
            reason_codes=tuple(
                _required_text(value, "reason_code")
                for value in _sequence(item["reason_codes"], "reason_codes")
            ),
            input_snapshot_sha256=_nonplaceholder_sha256(
                item["input_snapshot_sha256"], "input_snapshot_sha256"
            ),
            previous_plan_payload_sha256=_nonplaceholder_sha256(
                item["previous_plan_payload_sha256"],
                "previous_plan_payload_sha256",
            ),
            rule_matrix_sha256=_nonplaceholder_sha256(
                item["rule_matrix_sha256"], "rule_matrix_sha256"
            ),
            treatment_matrix_sha256=_nonplaceholder_sha256(
                item["treatment_matrix_sha256"], "treatment_matrix_sha256"
            ),
            action_mask_sha256=_nonplaceholder_sha256(
                item["action_mask_sha256"], "action_mask_sha256"
            ),
            rule_plan_payload_sha256=_nonplaceholder_sha256(
                item["rule_plan_payload_sha256"],
                "rule_plan_payload_sha256",
            ),
            treatment_plan_payload_sha256=_nonplaceholder_sha256(
                item["treatment_plan_payload_sha256"],
                "treatment_plan_payload_sha256",
            ),
            rule_binding_sha256=_nonplaceholder_sha256(
                item["rule_binding_sha256"], "rule_binding_sha256"
            ),
            treatment_binding_sha256=_nonplaceholder_sha256(
                item["treatment_binding_sha256"],
                "treatment_binding_sha256",
            ),
            model_applied_edge_count=_nonnegative_int(
                item["model_applied_edge_count"], "model_applied_edge_count"
            ),
            binding_change_count=_nonnegative_int(
                item["binding_change_count"], "binding_change_count"
            ),
            rule_assignment_count=_nonnegative_int(
                item["rule_assignment_count"], "rule_assignment_count"
            ),
            treatment_assignment_count=_nonnegative_int(
                item["treatment_assignment_count"],
                "treatment_assignment_count",
            ),
            demand_slot_count=_nonnegative_int(
                item["demand_slot_count"], "demand_slot_count"
            ),
            m_to_n_target_count=_nonnegative_int(
                item["m_to_n_target_count"], "m_to_n_target_count"
            ),
            rule_hard_violation_count=_nonnegative_int(
                item["rule_hard_violation_count"],
                "rule_hard_violation_count",
            ),
            treatment_hard_violation_count=_nonnegative_int(
                item["treatment_hard_violation_count"],
                "treatment_hard_violation_count",
            ),
            fallback_reason=_optional_text(
                item["fallback_reason"], "fallback_reason"
            ),
            canonical_summary=_mapping(
                item["canonical_summary"], "canonical_summary"
            ),
            content_sha256=_nonplaceholder_sha256(
                item["content_sha256"], "content_sha256"
            ),
        )


@dataclass(frozen=True, slots=True)
class _PlanInspection:
    payload_sha256: str
    binding_sha256: str
    binding_signature: tuple[tuple[Any, ...], ...]
    assignment_count: int
    demand_slot_count: int
    m_to_n_target_count: int
    hard_violation_count: int
    feasibility_violation_count: int
    demand_contract_violation_count: int
    all_or_none_violation_count: int
    payload_valid: bool


def evaluate_learning_intervention_candidate_frame(
    *,
    sequence_index: int,
    rule_frame: PlanningFrameEvidence,
    treatment_frame: PlanningFrameEvidence,
) -> LearningInterventionFrameEvidence:
    """Derive candidate-frame eligibility from two same-input D3 frames.

    The caller supplies no eligibility, admission or authority booleans.
    ``sequence_index`` is the main-owned online-history order.  D3 evaluates
    exactly this pair and does not inspect seeds, physical outcomes or D6 data.
    """

    sequence = _nonnegative_int(sequence_index, "sequence_index")
    if not isinstance(rule_frame, PlanningFrameEvidence):
        _fail("rule_frame_type_invalid")
    if not isinstance(treatment_frame, PlanningFrameEvidence):
        _fail("treatment_frame_type_invalid")

    reasons: list[str] = []

    def reject(code: str) -> None:
        if code not in _REASON_SET:
            _fail("internal_reason_code_invalid", code)
        if code not in reasons:
            reasons.append(code)

    if not rule_frame.available:
        reject("rule_frame_unavailable")
    if not treatment_frame.available:
        reject("treatment_frame_unavailable")
    if (
        rule_frame.schema_version != PLANNING_FRAME_EVIDENCE_SCHEMA_V1
        or treatment_frame.schema_version != PLANNING_FRAME_EVIDENCE_SCHEMA_V1
    ):
        reject("planning_frame_schema_unsupported")
    try:
        _assert_truth_free(rule_frame)
        _assert_truth_free(treatment_frame)
    except LearningInterventionEligibilityError:
        reject("online_truth_input_rejected")

    timestamp_s = _candidate_timestamp(rule_frame, treatment_frame, reject)
    planning_path = _candidate_planning_path(rule_frame, treatment_frame, reject)
    if rule_frame.selection_source != treatment_frame.selection_source:
        reject("selection_source_mismatch")

    input_snapshot_sha256 = _safe_frame_sha256(rule_frame, reject)
    treatment_input_sha256 = _safe_frame_sha256(treatment_frame, reject)
    if input_snapshot_sha256 != treatment_input_sha256:
        reject("frame_input_lineage_mismatch")

    rule_result = rule_frame.rule_matrix_result
    treatment_rule_result = treatment_frame.rule_matrix_result
    effective_result = treatment_frame.effective_matrix_result
    rule_matrix_sha256 = _safe_matrix_sha256(
        rule_result,
        "rule_matrix_invalid",
        reject,
    )
    treatment_rule_sha256 = _safe_matrix_sha256(
        treatment_rule_result,
        "treatment_matrix_invalid",
        reject,
    )
    treatment_matrix_sha256 = _safe_matrix_sha256(
        effective_result,
        "treatment_matrix_invalid",
        reject,
    )
    if rule_matrix_sha256 != treatment_rule_sha256:
        reject("frame_input_lineage_mismatch")

    previous_plan = rule_frame.previous_plan
    treatment_previous_plan = treatment_frame.previous_plan
    previous_plan_payload_sha256 = _safe_plan_sha256(
        previous_plan,
        "previous_plan_missing",
        reject,
    )
    treatment_previous_sha256 = _safe_plan_sha256(
        treatment_previous_plan,
        "previous_plan_missing",
        reject,
    )
    if previous_plan_payload_sha256 != treatment_previous_sha256:
        reject("previous_plan_lineage_mismatch")

    previous_version = (
        -1 if previous_plan is None else int(previous_plan.version)
    )
    action_mask_sha256 = _fallback_digest("action-mask-unavailable")
    model_applied_edge_count = 0
    fallback_reason = _fallback_reason(treatment_frame, effective_result)

    if (
        rule_result is not None
        and treatment_rule_result is not None
        and effective_result is not None
    ):
        action_mask_sha256, model_applied_edge_count = _inspect_learning_result(
            rule_frame=rule_frame,
            treatment_frame=treatment_frame,
            rule_result=rule_result,
            treatment_rule_result=treatment_rule_result,
            effective_result=effective_result,
            previous_version=previous_version,
            reject=reject,
        )
    else:
        reject("frame_input_invalid")

    if rule_frame.learning_state != "rule_only":
        reject("rule_control_state_invalid")
    _inspect_learning_metadata(
        treatment_frame=treatment_frame,
        effective_result=effective_result,
        previous_version=previous_version,
        derived_applied_edge_count=model_applied_edge_count,
        fallback_reason=fallback_reason,
        reject=reject,
    )

    rule_inspection = _inspect_plan(
        plan=rule_frame.plan,
        frame=rule_frame,
        matrix_result=rule_result,
        prefix="rule",
        reject=reject,
    )
    treatment_inspection = _inspect_plan(
        plan=treatment_frame.plan,
        frame=treatment_frame,
        matrix_result=effective_result,
        prefix="treatment",
        reject=reject,
    )

    _inspect_version_contract(
        frame=rule_frame,
        plan=rule_frame.plan,
        previous_plan=previous_plan,
        reject=reject,
    )
    _inspect_version_contract(
        frame=treatment_frame,
        plan=treatment_frame.plan,
        previous_plan=treatment_previous_plan,
        reject=reject,
    )
    _inspect_previous_plan_freshness(
        timestamp_s=timestamp_s,
        previous_plan=previous_plan,
        reject=reject,
    )

    binding_change_count = _binding_change_count(
        rule_inspection.binding_signature,
        treatment_inspection.binding_signature,
    )
    if binding_change_count == 0:
        reject("binding_unchanged")

    demand_slot_count = max(
        rule_inspection.demand_slot_count,
        treatment_inspection.demand_slot_count,
    )
    m_to_n_target_count = max(
        rule_inspection.m_to_n_target_count,
        treatment_inspection.m_to_n_target_count,
    )
    reason_codes = ("eligible",) if not reasons else tuple(reasons)
    eligible = reason_codes == ("eligible",)
    values = {
        "schema_version": LEARNING_INTERVENTION_FRAME_EVIDENCE_SCHEMA_V1,
        "evidence_kind": LEARNING_INTERVENTION_FRAME_EVIDENCE_KIND,
        "selection_scope": LEARNING_INTERVENTION_SELECTION_SCOPE,
        "sequence_index": sequence,
        "timestamp_s": timestamp_s,
        "planning_path": planning_path,
        "eligible": eligible,
        "reason_codes": reason_codes,
        "input_snapshot_sha256": input_snapshot_sha256,
        "previous_plan_payload_sha256": previous_plan_payload_sha256,
        "rule_matrix_sha256": rule_matrix_sha256,
        "treatment_matrix_sha256": treatment_matrix_sha256,
        "action_mask_sha256": action_mask_sha256,
        "rule_plan_payload_sha256": rule_inspection.payload_sha256,
        "treatment_plan_payload_sha256": treatment_inspection.payload_sha256,
        "rule_binding_sha256": rule_inspection.binding_sha256,
        "treatment_binding_sha256": treatment_inspection.binding_sha256,
        "model_applied_edge_count": model_applied_edge_count,
        "binding_change_count": binding_change_count,
        "rule_assignment_count": rule_inspection.assignment_count,
        "treatment_assignment_count": treatment_inspection.assignment_count,
        "demand_slot_count": demand_slot_count,
        "m_to_n_target_count": m_to_n_target_count,
        "rule_hard_violation_count": rule_inspection.hard_violation_count,
        "treatment_hard_violation_count": (
            treatment_inspection.hard_violation_count
        ),
        "fallback_reason": fallback_reason,
    }
    summary = _canonical_summary(**values)
    payload = {
        **values,
        "reason_codes": list(reason_codes),
        "canonical_summary": summary,
    }
    content_sha256 = canonical_runtime_payload_sha256(payload)
    return LearningInterventionFrameEvidence(
        **values,
        canonical_summary=summary,
        content_sha256=content_sha256,
    )


def validate_learning_intervention_frame_evidence(
    value: LearningInterventionFrameEvidence | Mapping[str, Any],
) -> LearningInterventionFrameEvidence:
    """Validate typed or serialized candidate evidence without granting authority."""

    if isinstance(value, LearningInterventionFrameEvidence):
        return LearningInterventionFrameEvidence.from_dict(value.to_dict())
    return LearningInterventionFrameEvidence.from_dict(
        _mapping(value, "learning intervention frame evidence")
    )


def select_first_eligible_learning_intervention_frame(
    values: Iterable[LearningInterventionFrameEvidence | Mapping[str, Any]],
) -> LearningInterventionFrameEvidence | None:
    """Return the first eligible record from a strictly ordered main history.

    Main remains responsible for grouping by seed and for intersecting this D3
    result with any D7 checkpoint.  Both sequence index and planning timestamp
    must increase strictly; one planning cycle has one unique timestamp.
    """

    previous_sequence: int | None = None
    previous_timestamp_s: float | None = None
    first_eligible: LearningInterventionFrameEvidence | None = None
    for raw in values:
        evidence = validate_learning_intervention_frame_evidence(raw)
        if (
            previous_sequence is not None
            and evidence.sequence_index <= previous_sequence
        ):
            _fail(
                "candidate_history_not_strictly_ordered",
                "sequence_index must increase in the supplied main history",
            )
        if (
            previous_timestamp_s is not None
            and evidence.timestamp_s <= previous_timestamp_s
        ):
            _fail(
                "candidate_history_timestamp_not_strictly_ordered",
                "timestamp_s must increase in the supplied main history",
            )
        previous_sequence = evidence.sequence_index
        previous_timestamp_s = evidence.timestamp_s
        if first_eligible is None and evidence.eligible:
            first_eligible = evidence
    return first_eligible


def canonical_learning_intervention_frame_evidence_sha256(
    value: LearningInterventionFrameEvidence | Mapping[str, Any],
) -> str:
    """Hash every evidence field except its self-referential content hash."""

    payload = (
        value.to_dict()
        if isinstance(value, LearningInterventionFrameEvidence)
        else dict(_mapping(value, "learning intervention frame evidence"))
    )
    payload.pop("content_sha256", None)
    return canonical_runtime_payload_sha256(payload)


def _inspect_learning_result(
    *,
    rule_frame: PlanningFrameEvidence,
    treatment_frame: PlanningFrameEvidence,
    rule_result: CostMatrixResult,
    treatment_rule_result: CostMatrixResult,
    effective_result: CostMatrixResult,
    previous_version: int,
    reject: Any,
) -> tuple[str, int]:
    try:
        rule_matrix = np.asarray(rule_result.matrix, dtype=float)
        treatment_rule_matrix = np.asarray(
            treatment_rule_result.matrix,
            dtype=float,
        )
        effective_matrix = np.asarray(effective_result.matrix, dtype=float)
        if (
            rule_matrix.shape != treatment_rule_matrix.shape
            or rule_matrix.shape != effective_matrix.shape
            or not np.all(np.isfinite(rule_matrix))
            or not np.all(np.isfinite(treatment_rule_matrix))
            or not np.all(np.isfinite(effective_matrix))
        ):
            reject("learning_nonfinite")
            return _fallback_digest("action-mask-invalid"), 0
        rule_mask = np.asarray(
            rule_result.hard_safe_candidate_mask,
            dtype=bool,
        )
        treatment_rule_mask = np.asarray(
            treatment_rule_result.hard_safe_candidate_mask,
            dtype=bool,
        )
        effective_mask = np.asarray(
            effective_result.hard_safe_candidate_mask,
            dtype=bool,
        )
    except (TypeError, ValueError, AttributeError):
        reject("treatment_matrix_invalid")
        return _fallback_digest("action-mask-invalid"), 0

    if not np.array_equal(rule_mask, treatment_rule_mask) or not np.array_equal(
        rule_mask,
        effective_mask,
    ):
        reject("action_mask_mismatch")
    changed = effective_matrix != rule_matrix
    if np.any(changed & ~rule_mask):
        reject("learning_changed_hard_rejected_cost")
    applied_edge_count = int(np.count_nonzero(changed & rule_mask))
    version_for_mask = max(0, previous_version)
    try:
        action_mask_sha256 = canonical_learning_action_mask_sha256(
            rule_result,
            expected_previous_version=version_for_mask,
            current_plan_version=version_for_mask,
        )
    except Exception:
        reject("action_mask_mismatch")
        action_mask_sha256 = _fallback_digest("action-mask-invalid")
    if rule_frame.previous_plan_version != treatment_frame.previous_plan_version:
        reject("stale_plan_version")
    return action_mask_sha256, applied_edge_count


def _inspect_learning_metadata(
    *,
    treatment_frame: PlanningFrameEvidence,
    effective_result: CostMatrixResult | None,
    previous_version: int,
    derived_applied_edge_count: int,
    fallback_reason: str | None,
    reject: Any,
) -> None:
    if effective_result is None:
        reject("learning_metadata_incomplete")
        return
    metadata = effective_result.metadata
    required = (
        "learning_residual_schema",
        "learning_mode",
        "learning_applied",
        "learning_applied_edge_count",
        "learning_shadow_only",
        "learning_fallback_reason",
        "learning_candidate_action_count",
        "learning_expected_previous_version",
        "learning_current_plan_version",
        "learning_inference_elapsed_s",
        "learning_timeout_s",
        "learning_confidence",
        "learning_min_confidence",
        "learning_ood_z_threshold",
        "learning_absolute_feature_limit",
        "learning_distribution_diagnostic_schema",
        "learning_distribution_is_ood",
        "learning_distribution_z_threshold",
    )
    if any(name not in metadata for name in required):
        reject("learning_metadata_incomplete")
    if _contains_nonfinite_numeric(
        {
            str(name): value
            for name, value in metadata.items()
            if str(name).startswith("learning_")
        }
    ):
        reject("learning_nonfinite")

    if (
        treatment_frame.learning_state != "assist_effective"
        or metadata.get("learning_mode") != "assist"
        or metadata.get("learning_applied") is not True
        or metadata.get("learning_shadow_only") is not False
    ):
        reject("learning_not_applied")
    recorded_count = _metadata_nonnegative_int(
        metadata.get("learning_applied_edge_count")
    )
    if recorded_count is None or recorded_count != derived_applied_edge_count:
        reject("learning_application_count_mismatch")
    if derived_applied_edge_count < 1:
        reject("learning_application_count_zero")
    candidate_count = _metadata_nonnegative_int(
        metadata.get("learning_candidate_action_count")
    )
    try:
        hard_safe_candidate_count = int(
            np.count_nonzero(effective_result.hard_safe_candidate_mask)
        )
    except (TypeError, ValueError, AttributeError):
        hard_safe_candidate_count = -1
    if (
        candidate_count is None
        or candidate_count != hard_safe_candidate_count
        or derived_applied_edge_count > candidate_count
    ):
        reject("learning_metadata_incomplete")
    if fallback_reason is not None:
        reject("learning_fallback_present")
    if metadata.get("learning_distribution_is_ood") is not False:
        reject("learning_ood")

    expected_version = _metadata_nonnegative_int(
        metadata.get("learning_expected_previous_version")
    )
    current_version = _metadata_nonnegative_int(
        metadata.get("learning_current_plan_version")
    )
    if (
        previous_version < 0
        or expected_version != previous_version
        or current_version != previous_version
    ):
        reject("stale_plan_version")

    elapsed = _metadata_finite(metadata.get("learning_inference_elapsed_s"))
    timeout = _metadata_finite(metadata.get("learning_timeout_s"))
    confidence = _metadata_finite(metadata.get("learning_confidence"))
    minimum_confidence = _metadata_finite(
        metadata.get("learning_min_confidence")
    )
    configured_ood_threshold = _metadata_finite(
        metadata.get("learning_ood_z_threshold")
    )
    diagnostic_ood_threshold = _metadata_finite(
        metadata.get("learning_distribution_z_threshold")
    )
    absolute_feature_limit = _metadata_finite(
        metadata.get("learning_absolute_feature_limit")
    )
    if (
        elapsed is None
        or timeout is None
        or timeout <= 0.0
        or elapsed < 0.0
        or elapsed > timeout
    ):
        reject("learning_timeout")
    if (
        confidence is None
        or minimum_confidence is None
        or not 0.0 <= minimum_confidence <= 1.0
        or confidence < minimum_confidence
    ):
        reject("learning_metadata_incomplete")
    if (
        configured_ood_threshold is None
        or diagnostic_ood_threshold is None
        or configured_ood_threshold <= 0.0
        or diagnostic_ood_threshold != configured_ood_threshold
        or absolute_feature_limit is None
        or absolute_feature_limit <= 0.0
    ):
        reject("learning_metadata_incomplete")


def _inspect_plan(
    *,
    plan: AssignmentPlan | None,
    frame: PlanningFrameEvidence,
    matrix_result: CostMatrixResult | None,
    prefix: str,
    reject: Any,
) -> _PlanInspection:
    fallback = _fallback_digest(f"{prefix}-plan-unavailable")
    if plan is None or matrix_result is None:
        reject(f"{prefix}_plan_invalid")
        return _PlanInspection(
            payload_sha256=fallback,
            binding_sha256=_fallback_digest(f"{prefix}-binding-unavailable"),
            binding_signature=(),
            assignment_count=0,
            demand_slot_count=0,
            m_to_n_target_count=0,
            hard_violation_count=0,
            feasibility_violation_count=1,
            demand_contract_violation_count=1,
            all_or_none_violation_count=1,
            payload_valid=False,
        )
    try:
        payload_sha256 = validated_assignment_plan_payload_sha256(plan)
        payload_valid = True
    except Exception:
        payload_sha256 = fallback
        payload_valid = False
        reject(f"{prefix}_plan_invalid")

    binding_signature = _binding_signature(plan)
    binding_sha256 = canonical_runtime_payload_sha256(binding_signature)
    target_ids = tuple(matrix_result.target_ids)
    resource_ids = tuple(matrix_result.resource_ids)
    target_set = set(target_ids)
    resource_set = set(resource_ids)
    target_index = {value: index for index, value in enumerate(target_ids)}
    resource_index = {value: index for index, value in enumerate(resource_ids)}
    hard_mask = np.asarray(matrix_result.hard_safe_candidate_mask, dtype=bool)
    matrix = np.asarray(matrix_result.matrix, dtype=float)

    feasibility_violations = 0
    hard_violations = 0
    resources_seen: set[str] = set()
    assignments_by_target: dict[str, list[Any]] = {}
    for assignment in plan.assignments:
        assignments_by_target.setdefault(assignment.target_id, []).append(
            assignment
        )
        if (
            assignment.target_id not in target_set
            or assignment.resource_id not in resource_set
            or assignment.resource_id in resources_seen
            or assignment.feasibility_state != "feasible"
            or not isfinite(float(assignment.cost))
        ):
            feasibility_violations += 1
            continue
        resources_seen.add(assignment.resource_id)
        row = target_index[assignment.target_id]
        column = resource_index[assignment.resource_id]
        if not hard_mask[row, column]:
            hard_violations += 1
        if not np.isclose(
            float(assignment.cost),
            float(matrix[row, column]),
            rtol=1.0e-10,
            atol=1.0e-12,
        ):
            feasibility_violations += 1
    if (
        plan.target_count != len(target_ids)
        or plan.resource_count != len(resource_ids)
        or not isfinite(float(plan.total_cost))
    ):
        feasibility_violations += 1

    summaries = {item.target_id: item for item in plan.demand_summaries}
    coalitions = {item.target_id: item for item in plan.coalitions}
    if (
        len(summaries) != len(plan.demand_summaries)
        or len(coalitions) != len(plan.coalitions)
        or set(summaries) != target_set
        or set(coalitions) != target_set
    ):
        demand_violations = 1
    else:
        demand_violations = 0
    all_or_none_violations = 0
    expected_unassigned: set[str] = set()
    expected_incomplete: set[str] = set()
    demand_slot_count = 0
    m_to_n_target_count = 0

    track_by_id = {item.track_id: item for item in frame.tracks}
    if set(track_by_id) != target_set:
        demand_violations += 1
    for target_id in target_ids:
        track = track_by_id.get(target_id)
        summary = summaries.get(target_id)
        coalition = coalitions.get(target_id)
        if track is None or summary is None or coalition is None:
            demand_violations += 1
            continue
        demand = track.effective_demand
        required = int(demand.required_resource_count)
        primary_required = int(demand.primary_resource_count)
        demand_slot_count += required
        if required > 1:
            m_to_n_target_count += 1
        executable = tuple(assignments_by_target.get(target_id, ()))
        members = tuple(coalition.members)
        member_resource_ids = tuple(item.resource_id for item in members)
        if (
            len(member_resource_ids) != len(set(member_resource_ids))
            or any(value not in resource_set for value in member_resource_ids)
        ):
            demand_violations += 1
        for member in members:
            if member.resource_id in resource_index:
                if not hard_mask[
                    target_index[target_id],
                    resource_index[member.resource_id],
                ]:
                    hard_violations += 1
        assigned = len(members)
        complete = assigned == required
        expected_shortfall = max(0, required - assigned)
        if (
            summary.demand_required != required
            or summary.demand_assigned != assigned
            or summary.demand_shortfall != expected_shortfall
            or summary.coalition_complete is not complete
            or summary.coalition_id != coalition.coalition_id
            or summary.coalition_version != coalition.version
            or summary.primary_resource_count != primary_required
            or coalition.target_id != target_id
            or coalition.required_resource_count != required
            or coalition.assigned_resource_count != assigned
            or coalition.shortfall != expected_shortfall
            or coalition.complete is not complete
            or coalition.primary_resource_count != primary_required
            or coalition.coordination_mode != demand.coordination_mode
            or coalition.terminal_authorization_scope
            != demand.terminal_authorization_scope
            or coalition.arrival_coordination_required
            is not demand.arrival_coordination_required
        ):
            demand_violations += 1
        primary_count = sum(
            item.member_role == CoalitionMemberRole.PRIMARY.value
            for item in members
        )
        if complete:
            expected_pairs = {
                (item.resource_id, item.member_role, item.wave_id)
                for item in members
            }
            executable_pairs = {
                (item.resource_id, item.member_role, item.wave_id)
                for item in executable
            }
            if (
                coalition.state != CoalitionState.COMMITTED.value
                or len(executable) != required
                or expected_pairs != executable_pairs
                or primary_count != primary_required
                or any(not item.executable for item in members)
            ):
                all_or_none_violations += 1
            for assignment in executable:
                if (
                    assignment.required_resource_count != required
                    or assignment.coalition_id != coalition.coalition_id
                    or assignment.coalition_version != coalition.version
                    or assignment.terminal_authorization_scope
                    != demand.terminal_authorization_scope
                    or assignment.arrival_coordination_required
                    is not demand.arrival_coordination_required
                ):
                    demand_violations += 1
        else:
            expected_unassigned.add(target_id)
            expected_incomplete.add(target_id)
            if (
                coalition.state != CoalitionState.INCOMPLETE.value
                or executable
                or any(item.executable for item in members)
                or assigned >= required
                or primary_count > primary_required
            ):
                all_or_none_violations += 1

    if (
        set(plan.unassigned_target_ids) != expected_unassigned
        or set(plan.incomplete_target_ids) != expected_incomplete
        or len(plan.unassigned_target_ids) != len(set(plan.unassigned_target_ids))
        or len(plan.incomplete_target_ids) != len(set(plan.incomplete_target_ids))
    ):
        demand_violations += 1
    if m_to_n_target_count and plan.solver_name != "hungarian_demand_slots":
        demand_violations += 1

    if feasibility_violations:
        reject(f"{prefix}_plan_infeasible")
    if hard_violations:
        reject(f"{prefix}_plan_hard_constraint_violation")
    if demand_violations:
        reject(f"{prefix}_demand_slot_contract_incomplete")
    if all_or_none_violations:
        reject(f"{prefix}_m_to_n_all_or_none_incomplete")
    return _PlanInspection(
        payload_sha256=payload_sha256,
        binding_sha256=binding_sha256,
        binding_signature=binding_signature,
        assignment_count=len(plan.assignments),
        demand_slot_count=demand_slot_count,
        m_to_n_target_count=m_to_n_target_count,
        hard_violation_count=hard_violations,
        feasibility_violation_count=feasibility_violations,
        demand_contract_violation_count=demand_violations,
        all_or_none_violation_count=all_or_none_violations,
        payload_valid=payload_valid,
    )


def _inspect_version_contract(
    *,
    frame: PlanningFrameEvidence,
    plan: AssignmentPlan | None,
    previous_plan: AssignmentPlan | None,
    reject: Any,
) -> None:
    if plan is None or previous_plan is None:
        reject("previous_plan_missing")
        return
    previous_version = int(previous_plan.version)
    if frame.previous_plan_version != previous_version:
        reject("stale_plan_version")
    if frame.plan_version != plan.version or frame.plan_id != plan.plan_id:
        reject("stale_plan_version")
    if plan.version == previous_version:
        if plan.plan_id != previous_plan.plan_id:
            reject("stale_plan_version")
    elif plan.version == previous_version + 1:
        if plan.previous_plan_id != previous_plan.plan_id:
            reject("stale_plan_version")
    else:
        reject("stale_plan_version")


def _inspect_previous_plan_freshness(
    *,
    timestamp_s: float,
    previous_plan: AssignmentPlan | None,
    reject: Any,
) -> None:
    if previous_plan is None:
        reject("previous_plan_missing")
        return
    if timestamp_s < float(previous_plan.created_at):
        reject("stale_plan_time_window")
    if previous_plan.stale_after_s is None:
        return
    freshness_base = max(
        float(previous_plan.created_at),
        float(previous_plan.last_changed_at),
    )
    if timestamp_s > freshness_base + float(previous_plan.stale_after_s):
        reject("stale_plan_time_window")


def _candidate_timestamp(
    rule_frame: PlanningFrameEvidence,
    treatment_frame: PlanningFrameEvidence,
    reject: Any,
) -> float:
    values = (rule_frame.timestamp_s, treatment_frame.timestamp_s)
    if any(value is None for value in values):
        reject("frame_input_invalid")
        return 0.0
    try:
        rule_timestamp = float(values[0])
        treatment_timestamp = float(values[1])
    except (TypeError, ValueError):
        reject("frame_input_invalid")
        return 0.0
    if not isfinite(rule_timestamp) or not isfinite(treatment_timestamp):
        reject("learning_nonfinite")
        return 0.0
    if rule_timestamp != treatment_timestamp:
        reject("frame_timestamp_mismatch")
    return max(0.0, rule_timestamp)


def _candidate_planning_path(
    rule_frame: PlanningFrameEvidence,
    treatment_frame: PlanningFrameEvidence,
    reject: Any,
) -> str:
    rule_path = str(rule_frame.planning_path).strip()
    treatment_path = str(treatment_frame.planning_path).strip()
    if not rule_path:
        reject("frame_input_invalid")
        rule_path = "unavailable"
    if rule_path != treatment_path:
        reject("planning_path_mismatch")
    return rule_path


def _safe_frame_sha256(
    frame: PlanningFrameEvidence,
    reject: Any,
) -> str:
    try:
        return canonical_planning_frame_snapshot_sha256(frame)
    except Exception:
        reject("frame_input_invalid")
        return _fallback_digest("planning-frame-invalid")


def _safe_matrix_sha256(
    value: CostMatrixResult | None,
    reason: str,
    reject: Any,
) -> str:
    if value is None:
        reject(reason)
        return _fallback_digest(reason)
    try:
        return canonical_rule_cost_matrix_sha256(value)
    except Exception:
        reject(reason)
        return _fallback_digest(reason)


def _safe_plan_sha256(
    value: AssignmentPlan | None,
    reason: str,
    reject: Any,
) -> str:
    if value is None:
        reject(reason)
        return _fallback_digest(reason)
    try:
        return validated_assignment_plan_payload_sha256(value)
    except Exception:
        reject(reason)
        return _fallback_digest(reason)


def _fallback_reason(
    frame: PlanningFrameEvidence,
    effective_result: CostMatrixResult | None,
) -> str | None:
    values = [frame.fallback_reason]
    if effective_result is not None:
        values.append(effective_result.metadata.get("learning_fallback_reason"))
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _binding_signature(plan: AssignmentPlan) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        sorted(
            (
                item.resource_id,
                item.target_id,
                item.coalition_id,
                item.coalition_version,
                item.member_role,
                item.wave_id,
            )
            for item in plan.assignments
        )
    )


def _binding_change_count(
    rule: tuple[tuple[Any, ...], ...],
    treatment: tuple[tuple[Any, ...], ...],
) -> int:
    rule_by_resource = {str(item[0]): item[1:] for item in rule}
    treatment_by_resource = {str(item[0]): item[1:] for item in treatment}
    return sum(
        rule_by_resource.get(resource_id) != treatment_by_resource.get(resource_id)
        for resource_id in set(rule_by_resource) | set(treatment_by_resource)
    )


def _canonical_summary(
    *,
    schema_version: str = LEARNING_INTERVENTION_FRAME_EVIDENCE_SCHEMA_V1,
    evidence_kind: str = LEARNING_INTERVENTION_FRAME_EVIDENCE_KIND,
    selection_scope: str = LEARNING_INTERVENTION_SELECTION_SCOPE,
    sequence_index: int,
    timestamp_s: float,
    planning_path: str,
    eligible: bool,
    reason_codes: Sequence[str],
    input_snapshot_sha256: str,
    previous_plan_payload_sha256: str,
    rule_matrix_sha256: str,
    treatment_matrix_sha256: str,
    action_mask_sha256: str,
    rule_plan_payload_sha256: str,
    treatment_plan_payload_sha256: str,
    rule_binding_sha256: str,
    treatment_binding_sha256: str,
    model_applied_edge_count: int,
    binding_change_count: int,
    rule_assignment_count: int,
    treatment_assignment_count: int,
    demand_slot_count: int,
    m_to_n_target_count: int,
    rule_hard_violation_count: int,
    treatment_hard_violation_count: int,
    fallback_reason: str | None,
) -> dict[str, Any]:
    del schema_version, evidence_kind
    return {
        "frame": {
            "sequence_index": int(sequence_index),
            "timestamp_s": float(timestamp_s),
            "planning_path": planning_path,
        },
        "lineage": {
            "input_snapshot_sha256": input_snapshot_sha256,
            "previous_plan_payload_sha256": previous_plan_payload_sha256,
            "rule_matrix_sha256": rule_matrix_sha256,
            "treatment_matrix_sha256": treatment_matrix_sha256,
            "action_mask_sha256": action_mask_sha256,
        },
        "plans": {
            "rule_plan_payload_sha256": rule_plan_payload_sha256,
            "treatment_plan_payload_sha256": treatment_plan_payload_sha256,
            "rule_binding_sha256": rule_binding_sha256,
            "treatment_binding_sha256": treatment_binding_sha256,
            "rule_assignment_count": int(rule_assignment_count),
            "treatment_assignment_count": int(treatment_assignment_count),
            "demand_slot_count": int(demand_slot_count),
            "m_to_n_target_count": int(m_to_n_target_count),
            "rule_hard_violation_count": int(rule_hard_violation_count),
            "treatment_hard_violation_count": int(
                treatment_hard_violation_count
            ),
        },
        "intervention": {
            "model_applied_edge_count": int(model_applied_edge_count),
            "binding_change_count": int(binding_change_count),
            "fallback_reason": fallback_reason,
        },
        "decision": {
            "eligible": bool(eligible),
            "reason_codes": list(reason_codes),
            "selection_scope": selection_scope,
            "admission_effect": "none",
            "authority_effect": "none",
        },
    }


def _freeze_json_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _freeze_json(value)
    if not isinstance(frozen, Mapping):
        _fail("canonical_summary_invalid")
    return frozen


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _json_native(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_native(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_native(item) for item in value]
    return value


def _assert_truth_free(value: Any, path: str = "$") -> None:
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _assert_truth_free(getattr(value, item.name), f"{path}.{item.name}")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            text = str(key).strip().lower()
            if text in _FORBIDDEN_ONLINE_KEYS or text.startswith("truth_"):
                _fail("online_truth_input_rejected", f"{path}.{key}")
            _assert_truth_free(child, f"{path}.{key}")
        return
    if isinstance(value, np.ndarray):
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _assert_truth_free(child, f"{path}[{index}]")


def _strict_mapping(
    value: Mapping[str, Any],
    expected_fields: frozenset[str],
    code: str,
) -> Mapping[str, Any]:
    item = _mapping(value, "mapping")
    if frozenset(str(key) for key in item) != expected_fields:
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
        _fail("text_required", context)
    return value.strip()


def _optional_text(value: Any, context: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, context)


def _strict_bool(value: Any, context: str) -> bool:
    if type(value) is not bool:
        _fail("boolean_required", context)
    return value


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        _fail("integer_required", context)
    result = int(value)
    if result < 0:
        _fail("nonnegative_integer_required", context)
    return result


def _finite_nonnegative(value: Any, context: str) -> float:
    if isinstance(value, bool):
        _fail("finite_number_required", context)
    try:
        result = float(value)
    except (TypeError, ValueError):
        _fail("finite_number_required", context)
    if not isfinite(result) or result < 0.0:
        _fail("finite_nonnegative_required", context)
    return result


def _metadata_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        return None
    result = int(value)
    return result if result >= 0 else None


def _metadata_finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _contains_nonfinite_numeric(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float, np.integer, np.floating)):
        return not isfinite(float(value))
    if isinstance(value, np.ndarray):
        if not np.issubdtype(value.dtype, np.number):
            return False
        return bool(np.any(~np.isfinite(value)))
    if isinstance(value, Mapping):
        return any(_contains_nonfinite_numeric(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_nonfinite_numeric(item) for item in value)
    return False


def _nonplaceholder_sha256(value: Any, context: str) -> str:
    text = _required_text(value, context)
    if (
        len(text) != 64
        or any(character not in "0123456789abcdef" for character in text)
        or len(set(text)) == 1
    ):
        _fail("placeholder_or_invalid_sha256", context)
    return text


def _fallback_digest(value: str) -> str:
    return canonical_runtime_payload_sha256(
        {
            "schema": LEARNING_INTERVENTION_FRAME_EVIDENCE_SCHEMA_V1,
            "unavailable": value,
        }
    )


def _fail(code: str, message: str | None = None) -> None:
    raise LearningInterventionEligibilityError(code, message)


__all__ = [
    "LEARNING_INTERVENTION_FRAME_EVIDENCE_KIND",
    "LEARNING_INTERVENTION_FRAME_EVIDENCE_SCHEMA_V1",
    "LEARNING_INTERVENTION_REASON_CODES",
    "LEARNING_INTERVENTION_SELECTION_SCOPE",
    "LearningInterventionEligibilityError",
    "LearningInterventionFrameEvidence",
    "canonical_learning_intervention_frame_evidence_sha256",
    "evaluate_learning_intervention_candidate_frame",
    "select_first_eligible_learning_intervention_frame",
    "validate_learning_intervention_frame_evidence",
]
