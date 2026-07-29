"""Development-only A1 action-margin calibration on one frozen planning frame.

The calibration reuses a truth-free isolated frame replay and the existing
Hungarian planner.  It never publishes a plan, grants assignment authority, or
claims unseen-seed/formal evidence.  Candidate alpha and confidence values are
diagnostic inputs only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite, tanh
from typing import Any

import numpy as np

from .learning import (
    LearningAssistConfig,
    LearningCostAssistant,
    ResidualPrediction,
    build_candidate_edge_batch,
)
from .learning_intervention_eligibility import (
    evaluate_learning_intervention_candidate_frame,
)
from .models import CostWeights, PlannerConfig
from .offline_intervention_execution import (
    IsolatedLearningInterventionFrameReplay,
    _replay_planning_arm,
    _score_plan,
    _validate_execution_config,
    canonical_learning_action_mask_sha256,
    canonical_isolated_learning_intervention_frame_replay_sha256,
    canonical_rule_cost_matrix_sha256,
)
from .paired_intervention import CONTROL_ARM, TREATMENT_ARM
from .runtime_plan_ack import canonical_runtime_payload_sha256


A1_ACTION_MARGIN_CALIBRATION_SCHEMA_V1 = "d3.a1-action-margin-calibration.v1"
A1_ACTION_MARGIN_CALIBRATION_SCOPE = (
    "single-frozen-frame-development-only-no-admission-no-authority"
)

_ALLOWED_SOURCE_NO_CHANGE_REASONS = frozenset(
    {
        "binding_unchanged",
        "learning_application_count_zero",
    }
)


@dataclass(frozen=True, slots=True)
class A1ActionMarginCalibrationConfig:
    """Explicit bounded candidate grid for one development-only replay."""

    candidate_alphas: tuple[float, ...] = (0.0, 0.25, 0.5, 1.0)
    candidate_min_confidences: tuple[float, ...] = (0.0, 0.6, 0.9)
    max_abs_cost_correction: float = 1.0
    max_binding_change_count: int = 3

    def __post_init__(self) -> None:
        alphas = _finite_unique_nonnegative(
            self.candidate_alphas,
            "candidate_alphas",
        )
        confidences = _finite_unique_nonnegative(
            self.candidate_min_confidences,
            "candidate_min_confidences",
        )
        if any(value > 1.0 for value in confidences):
            raise ValueError("candidate_min_confidences must be in [0, 1]")
        if isinstance(self.max_abs_cost_correction, bool):
            raise ValueError(
                "max_abs_cost_correction must be finite and non-negative"
            )
        correction = float(self.max_abs_cost_correction)
        if not isfinite(correction) or correction < 0.0:
            raise ValueError(
                "max_abs_cost_correction must be finite and non-negative"
            )
        if (
            isinstance(self.max_binding_change_count, bool)
            or not isinstance(self.max_binding_change_count, int)
            or self.max_binding_change_count < 0
        ):
            raise ValueError(
                "max_binding_change_count must be a non-negative integer"
            )
        object.__setattr__(self, "candidate_alphas", alphas)
        object.__setattr__(
            self,
            "candidate_min_confidences",
            confidences,
        )
        object.__setattr__(self, "max_abs_cost_correction", correction)


@dataclass(frozen=True, slots=True)
class A1EdgeActionMargin:
    """Local safe-edge margin relative to one target's lowest rule cost."""

    target_id: str
    rule_best_resource_id: str
    candidate_resource_id: str
    rule_best_cost: float
    candidate_rule_cost: float
    local_rule_cost_gap: float
    recorded_residual_directional_advantage: float | None
    required_alpha_to_cross: float | None
    source_alpha_crosses_margin: bool | None
    source_bounded_residual_can_cross: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "rule_best_resource_id": self.rule_best_resource_id,
            "candidate_resource_id": self.candidate_resource_id,
            "rule_best_cost": self.rule_best_cost,
            "candidate_rule_cost": self.candidate_rule_cost,
            "local_rule_cost_gap": self.local_rule_cost_gap,
            "recorded_residual_directional_advantage": (
                self.recorded_residual_directional_advantage
            ),
            "required_alpha_to_cross": self.required_alpha_to_cross,
            "source_alpha_crosses_margin": self.source_alpha_crosses_margin,
            "source_bounded_residual_can_cross": (
                self.source_bounded_residual_can_cross
            ),
        }


@dataclass(frozen=True, slots=True)
class A1ActionMarginCandidateResult:
    """One alpha/confidence candidate evaluated without authority."""

    alpha: float
    min_confidence: float
    observed_confidence: float | None
    evaluated: bool
    classification: str
    learning_applied: bool
    effective_matrix_changed_count: int
    binding_change_count: int
    identifiable: bool
    safety_gate_passed: bool
    fallback_reason: str | None
    reason_codes: tuple[str, ...]
    max_abs_cost_correction: float
    local_margin_count: int
    recorded_residual_crossable_margin_count: int
    bounded_residual_crossable_margin_count: int
    rule_basis_cost_delta: float | None
    solver_name: str | None
    rule_binding_sha256: str | None
    candidate_binding_sha256: str | None
    expected_previous_plan_version: int | None
    candidate_plan_version: int | None
    version_contract_passed: bool
    authorization_state: str = "not_authorized"
    runtime_publication_allowed: bool = False
    assignment_authority_allowed: bool = False
    control_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if self.classification not in {
            "no_op",
            "identifiable_development_intervention",
            "safety_gate_blocked",
        }:
            raise ValueError("unsupported A1 action-margin classification")
        if (
            self.authorization_state != "not_authorized"
            or self.runtime_publication_allowed
            or self.assignment_authority_allowed
            or self.control_authority_allowed
        ):
            raise ValueError("A1 action-margin candidate cannot grant authority")
        if self.identifiable != (
            self.classification == "identifiable_development_intervention"
        ):
            raise ValueError("A1 action-margin identifiable state is inconsistent")
        if self.identifiable and (
            not self.evaluated
            or not self.safety_gate_passed
            or self.binding_change_count < 1
            or self.rule_binding_sha256 == self.candidate_binding_sha256
        ):
            raise ValueError("identifiable A1 candidate lacks binding evidence")
        if self.classification == "no_op" and (
            not self.evaluated
            or not self.safety_gate_passed
            or self.binding_change_count != 0
            or self.rule_binding_sha256 != self.candidate_binding_sha256
        ):
            raise ValueError("A1 no-op candidate is inconsistent")
        if self.classification == "safety_gate_blocked" and self.safety_gate_passed:
            raise ValueError("blocked A1 candidate cannot pass the safety gate")
        for value, field_name in (
            (self.alpha, "alpha"),
            (self.min_confidence, "min_confidence"),
            (self.max_abs_cost_correction, "max_abs_cost_correction"),
        ):
            if not isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"{field_name} must be finite and non-negative")
        if (
            self.observed_confidence is not None
            and (
                not isfinite(float(self.observed_confidence))
                or not 0.0 <= float(self.observed_confidence) <= 1.0
            )
        ):
            raise ValueError("observed_confidence must be in [0, 1]")
        if (
            self.rule_basis_cost_delta is not None
            and not isfinite(float(self.rule_basis_cost_delta))
        ):
            raise ValueError("rule_basis_cost_delta must be finite")
        for value, field_name in (
            (self.effective_matrix_changed_count, "effective_matrix_changed_count"),
            (self.binding_change_count, "binding_change_count"),
            (self.local_margin_count, "local_margin_count"),
            (
                self.recorded_residual_crossable_margin_count,
                "recorded_residual_crossable_margin_count",
            ),
            (
                self.bounded_residual_crossable_margin_count,
                "bounded_residual_crossable_margin_count",
            ),
        ):
            if isinstance(value, bool) or int(value) != value or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        binding_hashes = (
            self.rule_binding_sha256,
            self.candidate_binding_sha256,
        )
        if self.evaluated:
            if (
                any(not _is_sha256(value) for value in binding_hashes)
                or self.expected_previous_plan_version is None
                or self.candidate_plan_version is None
                or self.candidate_plan_version
                not in {
                    self.expected_previous_plan_version,
                    self.expected_previous_plan_version + 1,
                }
                or not self.version_contract_passed
                or not self.solver_name
            ):
                raise ValueError("evaluated A1 candidate lacks solver/version evidence")
        elif any(value is not None for value in binding_hashes) or any(
            value is not None
            for value in (
                self.expected_previous_plan_version,
                self.candidate_plan_version,
                self.solver_name,
            )
        ) or self.version_contract_passed:
            raise ValueError("unevaluated A1 candidate contains execution evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "min_confidence": self.min_confidence,
            "observed_confidence": self.observed_confidence,
            "evaluated": self.evaluated,
            "classification": self.classification,
            "learning_applied": self.learning_applied,
            "effective_matrix_changed_count": (
                self.effective_matrix_changed_count
            ),
            "binding_change_count": self.binding_change_count,
            "identifiable": self.identifiable,
            "safety_gate_passed": self.safety_gate_passed,
            "fallback_reason": self.fallback_reason,
            "reason_codes": list(self.reason_codes),
            "max_abs_cost_correction": self.max_abs_cost_correction,
            "local_margin_count": self.local_margin_count,
            "recorded_residual_crossable_margin_count": (
                self.recorded_residual_crossable_margin_count
            ),
            "bounded_residual_crossable_margin_count": (
                self.bounded_residual_crossable_margin_count
            ),
            "rule_basis_cost_delta": self.rule_basis_cost_delta,
            "solver_name": self.solver_name,
            "rule_binding_sha256": self.rule_binding_sha256,
            "candidate_binding_sha256": self.candidate_binding_sha256,
            "expected_previous_plan_version": (
                self.expected_previous_plan_version
            ),
            "candidate_plan_version": self.candidate_plan_version,
            "version_contract_passed": self.version_contract_passed,
            "authorization_state": self.authorization_state,
            "runtime_publication_allowed": self.runtime_publication_allowed,
            "assignment_authority_allowed": self.assignment_authority_allowed,
            "control_authority_allowed": self.control_authority_allowed,
        }


@dataclass(frozen=True, slots=True)
class A1ActionMarginCalibrationReport:
    """Truth-free diagnosis of whether a recorded residual can move a binding."""

    sequence_index: int
    input_snapshot_sha256: str
    source_bundle_manifest_sha256: str | None
    source_policy_version: str | None
    source_alpha: float | None
    source_confidence: float | None
    source_min_confidence: float | None
    source_binding_change_count: int
    source_model_applied_edge_count: int
    source_guard_passed: bool
    source_guard_reasons: tuple[str, ...]
    target_count: int
    resource_count: int
    hard_safe_action_count: int
    calibration_max_abs_cost_correction: float
    calibration_max_binding_change_count: int
    hard_gate_reason_counts: tuple[tuple[str, int], ...]
    edge_margins: tuple[A1EdgeActionMargin, ...]
    candidates: tuple[A1ActionMarginCandidateResult, ...]
    lowest_identifiable_alpha: float | None
    highest_passing_min_confidence_at_lowest_alpha: float | None
    content_sha256: str
    schema_version: str = A1_ACTION_MARGIN_CALIBRATION_SCHEMA_V1
    calibration_scope: str = A1_ACTION_MARGIN_CALIBRATION_SCOPE
    development_only: bool = True
    formal_evidence: bool = False
    unseen_seed_evidence: bool = False
    runtime_publication_allowed: bool = False
    assignment_authority_allowed: bool = False
    control_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != A1_ACTION_MARGIN_CALIBRATION_SCHEMA_V1:
            raise ValueError("unsupported A1 action-margin calibration schema")
        if self.calibration_scope != A1_ACTION_MARGIN_CALIBRATION_SCOPE:
            raise ValueError("invalid A1 action-margin calibration scope")
        if (
            not self.development_only
            or self.formal_evidence
            or self.unseen_seed_evidence
            or self.runtime_publication_allowed
            or self.assignment_authority_allowed
            or self.control_authority_allowed
        ):
            raise ValueError("A1 action-margin calibration cannot grant authority")
        if any(
            item.authorization_state != "not_authorized"
            or item.runtime_publication_allowed
            or item.assignment_authority_allowed
            or item.control_authority_allowed
            for item in self.candidates
        ):
            raise ValueError("A1 action-margin report contains authority")
        for value, field_name in (
            (self.target_count, "target_count"),
            (self.resource_count, "resource_count"),
            (self.hard_safe_action_count, "hard_safe_action_count"),
        ):
            if isinstance(value, bool) or int(value) != value or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.hard_safe_action_count > self.target_count * self.resource_count:
            raise ValueError("hard_safe_action_count exceeds matrix size")
        expected = canonical_runtime_payload_sha256(
            _report_payload(self, include_content_sha256=False)
        )
        if self.content_sha256 != expected:
            raise ValueError("A1 action-margin calibration hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return _report_payload(self, include_content_sha256=True)


class _RecordedResidualPredictor:
    """Replay the residual vector already recorded by the source frame."""

    def __init__(self, delta_costs: np.ndarray, confidence: float) -> None:
        self._delta_costs = np.asarray(delta_costs, dtype=float).reshape(-1)
        self._confidence = float(confidence)

    def predict(self, features: np.ndarray) -> ResidualPrediction:
        if np.asarray(features).shape[0] != self._delta_costs.shape[0]:
            raise ValueError("recorded residual edge inventory mismatch")
        return ResidualPrediction(
            delta_costs=self._delta_costs.copy(),
            confidence=self._confidence,
        )


def calibrate_a1_action_margin(
    replay: IsolatedLearningInterventionFrameReplay,
    *,
    planner_config: PlannerConfig,
    cost_weights: CostWeights | None = None,
    calibration_config: A1ActionMarginCalibrationConfig | None = None,
) -> A1ActionMarginCalibrationReport:
    """Evaluate a bounded alpha/confidence grid on one frozen anonymous frame.

    The function consumes no seed identity and emits no plan payload.  Every
    candidate remains a non-authoritative development diagnostic even when its
    binding differs from the rule solution.
    """

    if not isinstance(replay, IsolatedLearningInterventionFrameReplay):
        raise TypeError("replay must be IsolatedLearningInterventionFrameReplay")
    if not isinstance(planner_config, PlannerConfig):
        raise TypeError("planner_config must be PlannerConfig")
    if cost_weights is not None and not isinstance(cost_weights, CostWeights):
        raise TypeError("cost_weights must be CostWeights")
    if calibration_config is not None and not isinstance(
        calibration_config,
        A1ActionMarginCalibrationConfig,
    ):
        raise TypeError(
            "calibration_config must be A1ActionMarginCalibrationConfig"
        )
    weights = CostWeights() if cost_weights is None else cost_weights
    config = (
        A1ActionMarginCalibrationConfig()
        if calibration_config is None
        else calibration_config
    )
    _validate_execution_config(planner_config, weights)
    _validate_replay_structure(replay)
    if canonical_isolated_learning_intervention_frame_replay_sha256(
        replay
    ) != replay.content_sha256:
        raise ValueError("calibration source replay content hash mismatch")

    rule_frame = replay.rule_frame
    treatment_frame = replay.treatment_frame
    rule_result = rule_frame.rule_matrix_result
    effective_result = treatment_frame.effective_matrix_result
    if rule_result is None or effective_result is None:
        raise ValueError("calibration requires rule and treatment matrices")
    if rule_frame.previous_plan is None:
        raise ValueError("calibration requires a frozen previous plan")
    target_count = len(rule_frame.tracks)
    resource_count = len(rule_frame.resources)
    hard_safe_action_count = int(
        np.count_nonzero(rule_result.hard_safe_candidate_mask)
    )

    previous_version = int(rule_frame.previous_plan.version)
    rule_hash = canonical_rule_cost_matrix_sha256(rule_result)
    action_mask_hash = canonical_learning_action_mask_sha256(
        rule_result,
        expected_previous_version=previous_version,
        current_plan_version=previous_version,
    )
    # Reject a planner configuration that changes the frozen control binding
    # independently of the recorded residual.
    _replay_planning_arm(
        arm_kind=CONTROL_ARM,
        evidence=rule_frame,
        assistant=None,
        bundle_loaded=False,
        config=planner_config,
        weights=weights,
        rule_hash=rule_hash,
        action_mask_hash=action_mask_hash,
        expected_previous_version=previous_version,
        current_plan_version=previous_version,
    )

    metadata = dict(effective_result.metadata)
    source_alpha = _optional_finite(metadata.get("learning_alpha"))
    source_confidence = _optional_finite(metadata.get("learning_confidence"))
    source_min_confidence = _optional_finite(
        metadata.get("learning_min_confidence")
    )
    source_guard_reasons = _source_guard_reasons(
        replay,
        metadata=metadata,
        source_alpha=source_alpha,
        source_confidence=source_confidence,
    )
    residual_delta = _recorded_residual_delta(
        replay,
        source_guard_reasons=source_guard_reasons,
    )
    if residual_delta is None and not source_guard_reasons:
        source_guard_reasons = ("recorded_residual_unavailable",)
    edge_margins = _edge_action_margins(
        replay,
        residual_delta=residual_delta,
        source_alpha=source_alpha,
    )
    hard_gate_reason_counts = _hard_gate_reason_counts(rule_result)

    rule_score = _score_plan(
        rule_frame.plan,
        rule_result,
        rule_frame,
        high_threat_threshold=planner_config.high_threat_threshold,
    )[0]
    if not isfinite(rule_score):
        raise ValueError("A1 rule-basis plan score must be finite")
    candidate_results = tuple(
        _evaluate_candidate(
            replay,
            planner_config=planner_config,
            cost_weights=weights,
            calibration_config=config,
            alpha=alpha,
            min_confidence=min_confidence,
            source_confidence=source_confidence,
            residual_delta=residual_delta,
            source_guard_reasons=source_guard_reasons,
            edge_margins=edge_margins,
            rule_score=rule_score,
        )
        for min_confidence in config.candidate_min_confidences
        for alpha in config.candidate_alphas
    )
    identifiable = tuple(item for item in candidate_results if item.identifiable)
    lowest_alpha = (
        None if not identifiable else min(item.alpha for item in identifiable)
    )
    highest_confidence = (
        None
        if lowest_alpha is None
        else max(
            item.min_confidence
            for item in identifiable
            if item.alpha == lowest_alpha
        )
    )
    values = {
        "sequence_index": int(replay.sequence_index),
        "input_snapshot_sha256": replay.input_snapshot_sha256,
        "source_bundle_manifest_sha256": (
            replay.actual_bundle_manifest_sha256
        ),
        "source_policy_version": replay.actual_policy_version,
        "source_alpha": source_alpha,
        "source_confidence": source_confidence,
        "source_min_confidence": source_min_confidence,
        "source_binding_change_count": int(
            replay.eligibility.binding_change_count
        ),
        "source_model_applied_edge_count": int(
            replay.eligibility.model_applied_edge_count
        ),
        "source_guard_passed": not source_guard_reasons,
        "source_guard_reasons": source_guard_reasons,
        "target_count": target_count,
        "resource_count": resource_count,
        "hard_safe_action_count": hard_safe_action_count,
        "calibration_max_abs_cost_correction": (
            config.max_abs_cost_correction
        ),
        "calibration_max_binding_change_count": (
            config.max_binding_change_count
        ),
        "hard_gate_reason_counts": hard_gate_reason_counts,
        "edge_margins": edge_margins,
        "candidates": candidate_results,
        "lowest_identifiable_alpha": lowest_alpha,
        "highest_passing_min_confidence_at_lowest_alpha": highest_confidence,
    }
    content_sha256 = canonical_runtime_payload_sha256(
        _report_payload_from_values(**values)
    )
    return A1ActionMarginCalibrationReport(
        **values,
        content_sha256=content_sha256,
    )


def _evaluate_candidate(
    replay: IsolatedLearningInterventionFrameReplay,
    *,
    planner_config: PlannerConfig,
    cost_weights: CostWeights,
    calibration_config: A1ActionMarginCalibrationConfig,
    alpha: float,
    min_confidence: float,
    source_confidence: float | None,
    residual_delta: np.ndarray | None,
    source_guard_reasons: tuple[str, ...],
    edge_margins: tuple[A1EdgeActionMargin, ...],
    rule_score: float,
) -> A1ActionMarginCandidateResult:
    unit_adjustment = (
        None if residual_delta is None else np.tanh(residual_delta)
    )
    max_unit_adjustment = (
        0.0
        if unit_adjustment is None or unit_adjustment.size == 0
        else float(np.max(np.abs(unit_adjustment)))
    )
    max_abs_correction = float(alpha * max_unit_adjustment)
    correction_would_overflow = not isfinite(max_abs_correction)
    recorded_crossable = sum(
        item.required_alpha_to_cross is not None
        and alpha > item.required_alpha_to_cross + 1.0e-12
        for item in edge_margins
    )
    bounded_crossable = sum(
        alpha > 0.5 * item.local_rule_cost_gap + 1.0e-12
        for item in edge_margins
    )
    if source_guard_reasons or residual_delta is None:
        reasons = source_guard_reasons or ("recorded_residual_unavailable",)
        return _blocked_candidate(
            alpha=alpha,
            min_confidence=min_confidence,
            source_confidence=source_confidence,
            reason_codes=reasons,
            fallback_reason=reasons[0],
            max_abs_cost_correction=max_abs_correction,
            edge_margins=edge_margins,
            recorded_crossable=recorded_crossable,
            bounded_crossable=bounded_crossable,
        )
    if correction_would_overflow:
        return _blocked_candidate(
            alpha=alpha,
            min_confidence=min_confidence,
            source_confidence=source_confidence,
            reason_codes=("cost_correction_non_finite",),
            fallback_reason="cost_correction_non_finite",
            max_abs_cost_correction=max_abs_correction,
            edge_margins=edge_margins,
            recorded_crossable=recorded_crossable,
            bounded_crossable=bounded_crossable,
        )
    if (
        max_abs_correction
        > calibration_config.max_abs_cost_correction + 1.0e-12
    ):
        return _blocked_candidate(
            alpha=alpha,
            min_confidence=min_confidence,
            source_confidence=source_confidence,
            reason_codes=("cost_correction_bound_exceeded",),
            fallback_reason="cost_correction_bound_exceeded",
            max_abs_cost_correction=max_abs_correction,
            edge_margins=edge_margins,
            recorded_crossable=recorded_crossable,
            bounded_crossable=bounded_crossable,
        )

    metadata = replay.treatment_frame.effective_matrix_result.metadata
    assistant = LearningCostAssistant(
        _RecordedResidualPredictor(residual_delta, float(source_confidence)),
        config=LearningAssistConfig(
            mode="assist",
            alpha=alpha,
            timeout_s=float(metadata["learning_timeout_s"]),
            min_confidence=min_confidence,
            ood_z_threshold=float(metadata["learning_ood_z_threshold"]),
            absolute_feature_limit=float(
                metadata["learning_absolute_feature_limit"]
            ),
        ),
    )
    previous_version = int(replay.rule_frame.previous_plan.version)
    rule_result = replay.rule_frame.rule_matrix_result
    treatment = _replay_planning_arm(
        arm_kind=TREATMENT_ARM,
        evidence=replay.rule_frame,
        assistant=assistant,
        bundle_loaded=True,
        config=planner_config,
        weights=cost_weights,
        rule_hash=canonical_rule_cost_matrix_sha256(rule_result),
        action_mask_hash=canonical_learning_action_mask_sha256(
            rule_result,
            expected_previous_version=previous_version,
            current_plan_version=previous_version,
        ),
        expected_previous_version=previous_version,
        current_plan_version=previous_version,
    )
    eligibility = evaluate_learning_intervention_candidate_frame(
        sequence_index=replay.sequence_index,
        rule_frame=replay.rule_frame,
        treatment_frame=treatment.planning_frame_evidence,
    )
    effective = treatment.effective_matrix
    effective_matrix_changed_count = int(
        np.count_nonzero(
            np.asarray(effective.matrix, dtype=float)
            != np.asarray(rule_result.matrix, dtype=float)
        )
    )
    safe_no_op_reasons = set(eligibility.reason_codes).issubset(
        _ALLOWED_SOURCE_NO_CHANGE_REASONS
    )
    identifiable = bool(
        eligibility.eligible and eligibility.binding_change_count > 0
    )
    binding_change_limit_ok = (
        eligibility.binding_change_count
        <= calibration_config.max_binding_change_count
    )
    if identifiable and not binding_change_limit_ok:
        identifiable = False
        reason_codes = tuple(eligibility.reason_codes) + (
            "binding_change_limit_exceeded",
        )
    else:
        reason_codes = tuple(eligibility.reason_codes)
    safety_gate_passed = bool(
        (identifiable or safe_no_op_reasons) and binding_change_limit_ok
    )
    if identifiable:
        classification = "identifiable_development_intervention"
    elif treatment.rule_fallback_applied or not safety_gate_passed:
        classification = "safety_gate_blocked"
    else:
        classification = "no_op"
    candidate_score = _score_plan(
        treatment.plan,
        rule_result,
        replay.rule_frame,
        high_threat_threshold=planner_config.high_threat_threshold,
    )[0]
    if not isfinite(candidate_score) or not isfinite(rule_score):
        raise ValueError("A1 rule-basis plan score must be finite")
    return A1ActionMarginCandidateResult(
        alpha=alpha,
        min_confidence=min_confidence,
        observed_confidence=source_confidence,
        evaluated=True,
        classification=classification,
        learning_applied=treatment.learning_cost_applied,
        effective_matrix_changed_count=effective_matrix_changed_count,
        binding_change_count=int(eligibility.binding_change_count),
        identifiable=identifiable,
        safety_gate_passed=safety_gate_passed,
        fallback_reason=treatment.fallback_reason,
        reason_codes=reason_codes,
        max_abs_cost_correction=max_abs_correction,
        local_margin_count=len(edge_margins),
        recorded_residual_crossable_margin_count=recorded_crossable,
        bounded_residual_crossable_margin_count=bounded_crossable,
        rule_basis_cost_delta=float(candidate_score - rule_score),
        solver_name=treatment.plan.solver_name,
        rule_binding_sha256=eligibility.rule_binding_sha256,
        candidate_binding_sha256=eligibility.treatment_binding_sha256,
        expected_previous_plan_version=previous_version,
        candidate_plan_version=int(treatment.plan.version),
        version_contract_passed=bool(
            treatment.plan.version in {previous_version, previous_version + 1}
            and "stale_plan_version" not in eligibility.reason_codes
        ),
    )


def _blocked_candidate(
    *,
    alpha: float,
    min_confidence: float,
    source_confidence: float | None,
    reason_codes: tuple[str, ...],
    fallback_reason: str,
    max_abs_cost_correction: float,
    edge_margins: tuple[A1EdgeActionMargin, ...],
    recorded_crossable: int,
    bounded_crossable: int,
) -> A1ActionMarginCandidateResult:
    return A1ActionMarginCandidateResult(
        alpha=alpha,
        min_confidence=min_confidence,
        observed_confidence=source_confidence,
        evaluated=False,
        classification="safety_gate_blocked",
        learning_applied=False,
        effective_matrix_changed_count=0,
        binding_change_count=0,
        identifiable=False,
        safety_gate_passed=False,
        fallback_reason=fallback_reason,
        reason_codes=reason_codes,
        max_abs_cost_correction=max_abs_cost_correction,
        local_margin_count=len(edge_margins),
        recorded_residual_crossable_margin_count=recorded_crossable,
        bounded_residual_crossable_margin_count=bounded_crossable,
        rule_basis_cost_delta=None,
        solver_name=None,
        rule_binding_sha256=None,
        candidate_binding_sha256=None,
        expected_previous_plan_version=None,
        candidate_plan_version=None,
        version_contract_passed=False,
    )


def _source_guard_reasons(
    replay: IsolatedLearningInterventionFrameReplay,
    *,
    metadata: dict[str, Any],
    source_alpha: float | None,
    source_confidence: float | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not replay.bundle_loaded:
        reasons.append(replay.bundle_fallback_reason or "source_bundle_not_loaded")
    if replay.treatment_frame.learning_state != "assist_effective":
        reasons.append("source_policy_not_applied")
    if metadata.get("learning_mode") != "assist":
        reasons.append("source_learning_mode_invalid")
    if metadata.get("learning_applied") is not True:
        reasons.append("source_policy_not_applied")
    if metadata.get("learning_fallback_reason") is not None:
        reasons.append(str(metadata["learning_fallback_reason"]))
    if metadata.get("learning_distribution_is_ood") is not False:
        reasons.append("source_distribution_gate_rejected")
    if source_alpha is None or source_alpha <= 0.0:
        reasons.append("source_alpha_invalid")
    if source_confidence is None or not 0.0 <= source_confidence <= 1.0:
        reasons.append("source_confidence_invalid")
    rule_result = replay.rule_frame.rule_matrix_result
    if rule_result is None:
        reasons.append("source_rule_matrix_unavailable")
    else:
        matrix = np.asarray(rule_result.matrix, dtype=float)
        if matrix.size == 0:
            reasons.append("source_empty_assignment_matrix")
        if not np.any(rule_result.hard_safe_candidate_mask):
            reasons.append("source_no_feasible_actions")
    if replay.eligibility.binding_change_count != 0:
        reasons.append("source_binding_already_changed")
    eligibility_reasons = set(replay.eligibility.reason_codes)
    unsupported = eligibility_reasons - _ALLOWED_SOURCE_NO_CHANGE_REASONS - {
        "eligible"
    }
    reasons.extend(sorted(unsupported))
    return tuple(dict.fromkeys(reasons))


def _recorded_residual_delta(
    replay: IsolatedLearningInterventionFrameReplay,
    *,
    source_guard_reasons: tuple[str, ...],
) -> np.ndarray | None:
    if source_guard_reasons:
        return None
    rule_result = replay.rule_frame.rule_matrix_result
    effective_result = replay.treatment_frame.effective_matrix_result
    previous_version = int(replay.rule_frame.previous_plan.version)
    batch = build_candidate_edge_batch(
        rule_result,
        replay.rule_frame.tracks,
        replay.rule_frame.resources,
        expected_previous_version=previous_version,
        current_plan_version=previous_version,
        previous_plan=replay.rule_frame.previous_plan,
    )
    values: list[float] = []
    source_alpha = float(effective_result.metadata["learning_alpha"])
    for target_index, resource_index in batch.edge_indices:
        breakdown = effective_result.breakdowns[target_index][resource_index]
        try:
            delta = float(breakdown["learning_delta_c"])
        except (KeyError, TypeError, ValueError):
            return None
        if not isfinite(delta):
            return None
        expected = source_alpha * tanh(delta)
        actual = float(
            effective_result.matrix[target_index, resource_index]
            - rule_result.matrix[target_index, resource_index]
        )
        if not np.isclose(actual, expected, rtol=0.0, atol=1.0e-10):
            return None
        values.append(delta)
    return np.asarray(values, dtype=float)


def _edge_action_margins(
    replay: IsolatedLearningInterventionFrameReplay,
    *,
    residual_delta: np.ndarray | None,
    source_alpha: float | None,
) -> tuple[A1EdgeActionMargin, ...]:
    result = replay.rule_frame.rule_matrix_result
    mask = np.asarray(result.hard_safe_candidate_mask, dtype=bool)
    matrix = np.asarray(result.matrix, dtype=float)
    unit_by_edge: dict[tuple[int, int], float] = {}
    if residual_delta is not None:
        previous_version = int(replay.rule_frame.previous_plan.version)
        batch = build_candidate_edge_batch(
            result,
            replay.rule_frame.tracks,
            replay.rule_frame.resources,
            expected_previous_version=previous_version,
            current_plan_version=previous_version,
            previous_plan=replay.rule_frame.previous_plan,
        )
        unit_by_edge = {
            edge: tanh(float(residual_delta[offset]))
            for offset, edge in enumerate(batch.edge_indices)
        }

    output: list[A1EdgeActionMargin] = []
    for target_index, target_id in enumerate(result.target_ids):
        safe_columns = tuple(np.flatnonzero(mask[target_index]))
        if len(safe_columns) < 2:
            continue
        best_column = min(
            safe_columns,
            key=lambda column: (
                float(matrix[target_index, column]),
                result.resource_ids[column],
            ),
        )
        best_cost = float(matrix[target_index, best_column])
        for candidate_column in safe_columns:
            if candidate_column == best_column:
                continue
            candidate_cost = float(matrix[target_index, candidate_column])
            raw_gap = candidate_cost - best_cost
            if not isfinite(raw_gap):
                raise ValueError("A1 local rule cost gap must be finite")
            gap = max(0.0, raw_gap)
            direction = None
            required_alpha = None
            source_crosses = None
            if unit_by_edge:
                direction = float(
                    unit_by_edge[(target_index, best_column)]
                    - unit_by_edge[(target_index, candidate_column)]
                )
                if direction > 1.0e-12:
                    required_alpha = float(gap / direction)
                    if not isfinite(required_alpha):
                        raise ValueError(
                            "A1 required alpha to cross must be finite"
                        )
                    source_crosses = bool(
                        source_alpha is not None
                        and source_alpha * direction > gap + 1.0e-12
                    )
                else:
                    source_crosses = False
            output.append(
                A1EdgeActionMargin(
                    target_id=target_id,
                    rule_best_resource_id=result.resource_ids[best_column],
                    candidate_resource_id=result.resource_ids[candidate_column],
                    rule_best_cost=best_cost,
                    candidate_rule_cost=candidate_cost,
                    local_rule_cost_gap=gap,
                    recorded_residual_directional_advantage=direction,
                    required_alpha_to_cross=required_alpha,
                    source_alpha_crosses_margin=source_crosses,
                    source_bounded_residual_can_cross=bool(
                        source_alpha is not None
                        and source_alpha > 0.5 * gap + 1.0e-12
                    ),
                )
            )
    return tuple(output)


def _hard_gate_reason_counts(result: Any) -> tuple[tuple[str, int], ...]:
    counts: Counter[str] = Counter()
    for row in result.reject_reasons:
        counts.update(str(reason) for reason in row if reason is not None)
    return tuple(sorted(counts.items()))


def _report_payload(
    report: A1ActionMarginCalibrationReport,
    *,
    include_content_sha256: bool,
) -> dict[str, Any]:
    payload = _report_payload_from_values(
        sequence_index=report.sequence_index,
        input_snapshot_sha256=report.input_snapshot_sha256,
        source_bundle_manifest_sha256=report.source_bundle_manifest_sha256,
        source_policy_version=report.source_policy_version,
        source_alpha=report.source_alpha,
        source_confidence=report.source_confidence,
        source_min_confidence=report.source_min_confidence,
        source_binding_change_count=report.source_binding_change_count,
        source_model_applied_edge_count=(
            report.source_model_applied_edge_count
        ),
        source_guard_passed=report.source_guard_passed,
        source_guard_reasons=report.source_guard_reasons,
        target_count=report.target_count,
        resource_count=report.resource_count,
        hard_safe_action_count=report.hard_safe_action_count,
        calibration_max_abs_cost_correction=(
            report.calibration_max_abs_cost_correction
        ),
        calibration_max_binding_change_count=(
            report.calibration_max_binding_change_count
        ),
        hard_gate_reason_counts=report.hard_gate_reason_counts,
        edge_margins=report.edge_margins,
        candidates=report.candidates,
        lowest_identifiable_alpha=report.lowest_identifiable_alpha,
        highest_passing_min_confidence_at_lowest_alpha=(
            report.highest_passing_min_confidence_at_lowest_alpha
        ),
    )
    if include_content_sha256:
        payload["content_sha256"] = report.content_sha256
    return payload


def _report_payload_from_values(
    *,
    sequence_index: int,
    input_snapshot_sha256: str,
    source_bundle_manifest_sha256: str | None,
    source_policy_version: str | None,
    source_alpha: float | None,
    source_confidence: float | None,
    source_min_confidence: float | None,
    source_binding_change_count: int,
    source_model_applied_edge_count: int,
    source_guard_passed: bool,
    source_guard_reasons: tuple[str, ...],
    target_count: int,
    resource_count: int,
    hard_safe_action_count: int,
    calibration_max_abs_cost_correction: float,
    calibration_max_binding_change_count: int,
    hard_gate_reason_counts: tuple[tuple[str, int], ...],
    edge_margins: tuple[A1EdgeActionMargin, ...],
    candidates: tuple[A1ActionMarginCandidateResult, ...],
    lowest_identifiable_alpha: float | None,
    highest_passing_min_confidence_at_lowest_alpha: float | None,
) -> dict[str, Any]:
    return {
        "schema_version": A1_ACTION_MARGIN_CALIBRATION_SCHEMA_V1,
        "calibration_scope": A1_ACTION_MARGIN_CALIBRATION_SCOPE,
        "sequence_index": sequence_index,
        "input_snapshot_sha256": input_snapshot_sha256,
        "source_bundle_manifest_sha256": source_bundle_manifest_sha256,
        "source_policy_version": source_policy_version,
        "source_alpha": source_alpha,
        "source_confidence": source_confidence,
        "source_min_confidence": source_min_confidence,
        "source_binding_change_count": source_binding_change_count,
        "source_model_applied_edge_count": source_model_applied_edge_count,
        "source_guard_passed": source_guard_passed,
        "source_guard_reasons": list(source_guard_reasons),
        "target_count": target_count,
        "resource_count": resource_count,
        "hard_safe_action_count": hard_safe_action_count,
        "calibration_max_abs_cost_correction": (
            calibration_max_abs_cost_correction
        ),
        "calibration_max_binding_change_count": (
            calibration_max_binding_change_count
        ),
        "hard_gate_reason_counts": [
            [reason, count] for reason, count in hard_gate_reason_counts
        ],
        "edge_margins": [item.to_dict() for item in edge_margins],
        "candidates": [item.to_dict() for item in candidates],
        "lowest_identifiable_alpha": lowest_identifiable_alpha,
        "highest_passing_min_confidence_at_lowest_alpha": (
            highest_passing_min_confidence_at_lowest_alpha
        ),
        "development_only": True,
        "formal_evidence": False,
        "unseen_seed_evidence": False,
        "runtime_publication_allowed": False,
        "assignment_authority_allowed": False,
        "control_authority_allowed": False,
    }


def _validate_replay_structure(
    replay: IsolatedLearningInterventionFrameReplay,
) -> None:
    """Reject malformed or post-construction-mutated frozen frame content."""

    rule_frame = replay.rule_frame
    treatment_frame = replay.treatment_frame
    if not rule_frame.available or not treatment_frame.available:
        raise ValueError("calibration requires available rule and treatment frames")
    tracks = tuple(rule_frame.tracks)
    resources = tuple(rule_frame.resources)
    target_ids = tuple(item.track_id for item in tracks)
    resource_ids = tuple(item.resource_id for item in resources)
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("calibration target inventory contains duplicates")
    if len(set(resource_ids)) != len(resource_ids):
        raise ValueError("calibration resource inventory contains duplicates")
    if tuple(item.track_id for item in treatment_frame.tracks) != target_ids:
        raise ValueError("calibration treatment target inventory mismatch")
    if tuple(item.resource_id for item in treatment_frame.resources) != resource_ids:
        raise ValueError("calibration treatment resource inventory mismatch")

    expected_shape = (len(target_ids), len(resource_ids))
    named_results = (
        ("rule", rule_frame.rule_matrix_result),
        ("treatment_rule", treatment_frame.rule_matrix_result),
        ("treatment_effective", treatment_frame.effective_matrix_result),
    )
    masks: list[np.ndarray] = []
    for name, result in named_results:
        if result is None:
            raise ValueError(f"calibration {name} matrix is unavailable")
        if tuple(result.target_ids) != target_ids:
            raise ValueError(f"calibration {name} target inventory mismatch")
        if tuple(result.resource_ids) != resource_ids:
            raise ValueError(f"calibration {name} resource inventory mismatch")
        try:
            matrix = np.asarray(result.matrix, dtype=float)
            unassigned = np.asarray(result.unassigned_costs, dtype=float)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"calibration {name} matrix is invalid") from exc
        if matrix.shape != expected_shape:
            raise ValueError(f"calibration {name} matrix shape mismatch")
        if unassigned.shape != (len(target_ids),):
            raise ValueError(f"calibration {name} unassigned-cost shape mismatch")
        try:
            mask = np.asarray(result.hard_safe_candidate_mask, dtype=bool)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"calibration {name} action mask is invalid") from exc
        if mask.shape != expected_shape:
            raise ValueError(f"calibration {name} action-mask shape mismatch")
        if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(unassigned)):
            raise ValueError(f"calibration {name} matrix contains non-finite values")
        if len(result.breakdowns) != len(target_ids) or any(
            len(row) != len(resource_ids) for row in result.breakdowns
        ):
            raise ValueError(f"calibration {name} breakdown shape mismatch")
        masks.append(mask)
    if not all(np.array_equal(masks[0], mask) for mask in masks[1:]):
        raise ValueError("calibration hard-safe action masks do not match")


def _finite_unique_nonnegative(
    values: tuple[float, ...],
    field_name: str,
) -> tuple[float, ...]:
    if any(isinstance(value, bool) for value in values):
        raise ValueError(
            f"{field_name} must contain finite non-negative values"
        )
    try:
        output = tuple(sorted({float(value) for value in values}))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must contain finite non-negative values"
        ) from exc
    if not output:
        raise ValueError(f"{field_name} must not be empty")
    if any(not isfinite(value) or value < 0.0 for value in output):
        raise ValueError(f"{field_name} must contain finite non-negative values")
    return output


def _optional_finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        output = float(value)
    except (TypeError, ValueError):
        return None
    return output if isfinite(output) else None


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
