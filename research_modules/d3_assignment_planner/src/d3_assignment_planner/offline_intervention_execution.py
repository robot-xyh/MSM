"""Execute reserved-seed D3 interventions without opening online authority.

This module is the only path that may apply a development/shadow-only bundle
to an effective cost matrix.  The resulting plans are isolated experiment
artifacts: they are not published, acknowledged, or authorized for control.
The production :func:`load_model_bundle` admission policy remains unchanged.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np

from .costs import CostMatrixResult
from .learning import LearningAssistConfig, LearningCostAssistant
from .learning_bundle import (
    MODEL_BUNDLE_MANIFEST_FILENAME,
    ModelBundleManifest,
    RuleFallbackLearningAssistant,
    load_model_bundle,
    unavailable_promotion_manifest,
)
from .models import AssignmentPlan, CostWeights, PlannerConfig
from .paired_intervention import (
    CONTROL_ARM,
    OFFLINE_INTERVENTION_SCOPE,
    TREATMENT_ARM,
    PairedInterventionArmSpecification,
    PairedInterventionContractError,
    PairedInterventionExecutionReceipt,
    PairedInterventionManifest,
    PairedInterventionSeedPair,
    PairedInterventionSpecification,
    canonical_paired_intervention_sha256,
)
from .planner import AssignmentPlanner
from .planning_evidence import PlanningFrameEvidence
from .runtime_plan_ack import canonical_runtime_payload_sha256
from .shadow_evaluation import (
    SHADOW_EVALUATION_SCHEMA_V2,
    ShadowEvaluationReport,
    ShadowFrameMetrics,
)


OFFLINE_PAIRED_INTERVENTION_EXECUTION_SCHEMA_V1 = (
    "d3.offline-paired-intervention-execution.v1"
)
OFFLINE_PAIRED_INTERVENTION_REPORT_KIND_V1 = (
    "reserved_seed_rule_vs_development_bundle_intervention"
)

_FORBIDDEN_INPUT_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
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


@dataclass(frozen=True, slots=True)
class OfflineInterventionArmExecution:
    """Actual output of one isolated control or treatment arm."""

    arm_specification: PairedInterventionArmSpecification
    plan: AssignmentPlan
    effective_matrix_sha256: str
    learning_cost_applied: bool
    rule_fallback_applied: bool
    fallback_reason: str | None
    inference_elapsed_ms: float
    receipt: PairedInterventionExecutionReceipt

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm_specification": self.arm_specification.to_dict(),
            "plan": _jsonable(self.plan),
            "effective_matrix_sha256": self.effective_matrix_sha256,
            "learning_cost_applied": self.learning_cost_applied,
            "rule_fallback_applied": self.rule_fallback_applied,
            "fallback_reason": self.fallback_reason,
            "inference_elapsed_ms": float(self.inference_elapsed_ms),
            "receipt": self.receipt.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class OfflinePairedInterventionExecution:
    """Complete 20-seed result with no runtime or outcome claims."""

    specification: PairedInterventionSpecification
    paired_evaluator_report: ShadowEvaluationReport
    paired_evaluator_report_sha256: str
    manifest: PairedInterventionManifest
    arms: tuple[OfflineInterventionArmExecution, ...]
    bundle_manifest_sha256: str | None
    bundle_state_dict_sha256: str | None
    bundle_loaded: bool
    bundle_fallback_reason: str | None
    schema_version: str = OFFLINE_PAIRED_INTERVENTION_EXECUTION_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != OFFLINE_PAIRED_INTERVENTION_EXECUTION_SCHEMA_V1:
            _fail("offline_execution_schema_unsupported")
        expected_arm_count = len(self.specification.pairs) * 2
        if len(self.arms) != expected_arm_count:
            _fail("offline_execution_arm_inventory_incomplete")
        if self.manifest.specification.fingerprint != self.specification.fingerprint:
            _fail("offline_execution_specification_mismatch")
        if tuple(item.receipt for item in self.arms) != self.manifest.execution_receipts:
            _fail("offline_execution_receipt_inventory_mismatch")
        if any(
            item.receipt.paired_evaluator_report_sha256
            != self.paired_evaluator_report_sha256
            for item in self.arms
        ):
            _fail("offline_execution_report_hash_mismatch")

    @property
    def runtime_ack_available(self) -> bool:
        return False

    @property
    def outcome_available(self) -> bool:
        return False

    @property
    def counterfactual_available(self) -> bool:
        return False

    @property
    def causal_available(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "intervention_scope": OFFLINE_INTERVENTION_SCOPE,
            "report_kind": OFFLINE_PAIRED_INTERVENTION_REPORT_KIND_V1,
            "specification_sha256": self.specification.fingerprint,
            "paired_evaluator_report": self.paired_evaluator_report.to_dict(),
            "paired_evaluator_report_sha256": (
                self.paired_evaluator_report_sha256
            ),
            "manifest": self.manifest.to_dict(),
            "bundle": {
                "loaded": self.bundle_loaded,
                "fallback_reason": self.bundle_fallback_reason,
                "manifest_sha256": self.bundle_manifest_sha256,
                "state_dict_sha256": self.bundle_state_dict_sha256,
            },
            "admission": {
                "ppo_enabled": False,
                "online_assist_enabled": False,
                "online_authority_enabled": False,
                "rule_fallback_enabled": True,
                "runtime_publication_allowed": False,
            },
            "evidence_availability": {
                "runtime_ack": False,
                "outcome": False,
                "counterfactual": False,
                "causal": False,
            },
            "arms": [item.to_dict() for item in self.arms],
        }
        _assert_truth_free(payload)
        _assert_all_finite(payload)
        return payload


@dataclass(frozen=True, slots=True)
class _OfflineBundle:
    assistant: LearningCostAssistant | RuleFallbackLearningAssistant
    loaded: bool
    fallback_reason: str | None
    manifest: ModelBundleManifest | None
    manifest_sha256: str | None
    state_dict_sha256: str | None


@dataclass(frozen=True, slots=True)
class _RawArmExecution:
    pair: PairedInterventionSeedPair
    arm: PairedInterventionArmSpecification
    plan: AssignmentPlan
    rule_matrix_sha256: str
    action_mask_sha256: str
    effective_matrix_sha256: str
    learning_cost_applied: bool
    rule_fallback_applied: bool
    fallback_reason: str | None
    inference_elapsed_ms: float
    frame_metrics: ShadowFrameMetrics | None = None


class _FrozenPlanningFrameCostModel:
    """Replay an already-audited rule matrix without rebuilding sensor costs."""

    def __init__(
        self,
        result: CostMatrixResult,
        *,
        config: PlannerConfig,
        weights: CostWeights,
    ) -> None:
        self.config = config
        self.weights = weights
        self._result = _remove_recorded_switch_penalty(result)

    def build_matrix(
        self,
        tracks: Any,
        resources: Any,
        timestamp: float,
        *,
        preserved_candidate_edges: Mapping[str, tuple[str, ...]] | None = None,
    ) -> CostMatrixResult:
        del timestamp, preserved_candidate_edges
        target_ids = tuple(item.track_id for item in tracks)
        resource_ids = tuple(item.resource_id for item in resources)
        if target_ids != self._result.target_ids:
            _fail("frozen_rule_matrix_target_snapshot_mismatch")
        if resource_ids != self._result.resource_ids:
            _fail("frozen_rule_matrix_resource_snapshot_mismatch")
        return _copy_matrix_result(self._result)


def canonical_planning_frame_snapshot_sha256(
    evidence: PlanningFrameEvidence,
) -> str:
    """Hash the anonymous input side of one planning frame.

    The effective matrix and output plan are deliberately excluded because
    those are intervention outputs.  The prior plan remains part of the input.
    """

    _validate_planning_frame_basics(evidence)
    payload = {
        "schema_version": evidence.schema_version,
        "planning_path": evidence.planning_path,
        "selection_source": evidence.selection_source,
        "timestamp_s": evidence.timestamp_s,
        "forced_replan": evidence.forced_replan,
        "previous_plan_version": evidence.previous_plan_version,
        "tracks": evidence.tracks,
        "resources": evidence.resources,
        "previous_plan": evidence.previous_plan,
        "rule_matrix_result": _matrix_payload(evidence.rule_matrix_result),
    }
    _assert_truth_free(payload)
    return canonical_runtime_payload_sha256(payload)


def canonical_rule_cost_matrix_sha256(result: CostMatrixResult) -> str:
    """Hash the full deterministic rule matrix, mask, and cost evidence."""

    _validate_matrix_result(result)
    return canonical_runtime_payload_sha256(_matrix_payload(result))


def canonical_learning_action_mask_sha256(
    result: CostMatrixResult,
    *,
    expected_previous_version: int,
    current_plan_version: int,
) -> str:
    """Hash the exact hard-safe action set and its version fence."""

    if int(expected_previous_version) != int(current_plan_version):
        mask = np.zeros(np.asarray(result.matrix).shape, dtype=bool)
    else:
        mask = result.hard_safe_candidate_mask
    payload = {
        "target_ids": result.target_ids,
        "resource_ids": result.resource_ids,
        "expected_previous_version": int(expected_previous_version),
        "current_plan_version": int(current_plan_version),
        "version_compatible": (
            int(expected_previous_version) == int(current_plan_version)
        ),
        "mask": mask,
    }
    return canonical_runtime_payload_sha256(payload)


def execute_offline_paired_intervention(
    specification: PairedInterventionSpecification,
    planning_frames: Mapping[int, PlanningFrameEvidence],
    *,
    bundle_dir: str | Path,
    planner_config: PlannerConfig | None = None,
    cost_weights: CostWeights | None = None,
) -> OfflinePairedInterventionExecution:
    """Run all reserved control/treatment arms on identical anonymous inputs.

    ``bundle_dir`` is loaded in production ``shadow`` mode first.  Only after
    manifest, weight, version, holdout, and finite-parameter checks pass is its
    predictor wrapped by this isolated executor with an effective residual.
    No production assist admission or runtime authority is changed.
    """

    if not isinstance(specification, PairedInterventionSpecification):
        _fail("offline_execution_specification_type_invalid")
    frame_by_seed = {int(seed): frame for seed, frame in planning_frames.items()}
    expected_seeds = tuple(specification.reserved_seeds)
    if tuple(sorted(frame_by_seed)) != expected_seeds:
        _fail("offline_execution_frame_inventory_mismatch")
    config = planner_config or PlannerConfig()
    weights = cost_weights or CostWeights()
    _validate_execution_config(config, weights)

    first_arm = specification.pairs[0].treatment
    offline_bundle = _load_offline_development_bundle(
        bundle_dir,
        expected_manifest_sha256=first_arm.d3_bundle_sha256,
        expected_policy_version=first_arm.d3_bundle_version,
        reserved_seeds=expected_seeds,
    )

    raw_arms: list[_RawArmExecution] = []
    frame_rows: list[ShadowFrameMetrics] = []
    for pair in specification.pairs:
        evidence = frame_by_seed[pair.seed]
        _validate_pair_frame(pair, evidence)
        rule_snapshot = np.asarray(evidence.rule_matrix, dtype=float).copy()
        rule_hash = canonical_rule_cost_matrix_sha256(
            _required_rule_result(evidence)
        )
        action_mask_hash = canonical_learning_action_mask_sha256(
            _required_rule_result(evidence),
            expected_previous_version=pair.control.expected_previous_plan_version,
            current_plan_version=pair.control.current_plan_version,
        )

        control = _execute_arm(
            pair=pair,
            arm=pair.control,
            evidence=evidence,
            assistant=None,
            bundle_loaded=False,
            config=config,
            weights=weights,
            rule_hash=rule_hash,
            action_mask_hash=action_mask_hash,
        )
        treatment = _execute_arm(
            pair=pair,
            arm=pair.treatment,
            evidence=evidence,
            assistant=offline_bundle.assistant,
            bundle_loaded=offline_bundle.loaded,
            config=config,
            weights=weights,
            rule_hash=rule_hash,
            action_mask_hash=action_mask_hash,
        )
        if not np.array_equal(rule_snapshot, np.asarray(evidence.rule_matrix)):
            _fail("rule_matrix_mutated_during_intervention")
        if control.rule_matrix_sha256 != treatment.rule_matrix_sha256:
            _fail("paired_rule_matrix_hash_mismatch")
        if control.action_mask_sha256 != treatment.action_mask_sha256:
            _fail("paired_action_mask_hash_mismatch")
        metrics = _paired_frame_metrics(
            pair=pair,
            evidence=evidence,
            control=control,
            treatment=treatment,
            config=config,
        )
        raw_arms.extend((replace(control, frame_metrics=metrics), treatment))
        frame_rows.append(metrics)

    report = _build_paired_report(
        specification=specification,
        frames=tuple(frame_rows),
        planning_frames=frame_by_seed,
        bundle=offline_bundle,
    )
    report_sha = canonical_runtime_payload_sha256(report.to_dict())

    executions = tuple(
        _finalize_arm_execution(raw, report_sha=report_sha)
        for raw in raw_arms
    )
    receipts = tuple(item.receipt for item in executions)
    manifest = PairedInterventionManifest(
        specification=specification,
        execution_receipts=receipts,
    )
    return OfflinePairedInterventionExecution(
        specification=specification,
        paired_evaluator_report=report,
        paired_evaluator_report_sha256=report_sha,
        manifest=manifest,
        arms=executions,
        bundle_manifest_sha256=offline_bundle.manifest_sha256,
        bundle_state_dict_sha256=offline_bundle.state_dict_sha256,
        bundle_loaded=offline_bundle.loaded,
        bundle_fallback_reason=offline_bundle.fallback_reason,
    )


def write_offline_paired_intervention_execution(
    path: str | Path,
    result: OfflinePairedInterventionExecution,
) -> None:
    """Write one canonical, finite JSON execution artifact."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(
            result.to_dict(),
            stream,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        stream.write("\n")


def _load_offline_development_bundle(
    bundle_dir: str | Path,
    *,
    expected_manifest_sha256: str,
    expected_policy_version: str,
    reserved_seeds: tuple[int, ...],
) -> _OfflineBundle:
    path = Path(bundle_dir)
    manifest_path = path / MODEL_BUNDLE_MANIFEST_FILENAME
    actual_manifest_sha: str | None = None
    if manifest_path.is_file():
        try:
            actual_manifest_sha = _file_sha256(manifest_path)
        except OSError:
            pass
    if actual_manifest_sha != expected_manifest_sha256:
        return _offline_bundle_fallback(
            "bundle_manifest_sha256_mismatch",
            manifest_sha256=actual_manifest_sha,
        )

    loaded = load_model_bundle(path, mode="shadow")
    manifest = loaded.manifest
    state_sha = None if manifest is None else manifest.state_dict_sha256
    if not loaded.loaded or manifest is None or loaded.policy is None:
        return _offline_bundle_fallback(
            loaded.fallback_reason or "model_bundle_unavailable",
            manifest=manifest,
            manifest_sha256=actual_manifest_sha,
            state_dict_sha256=state_sha,
        )
    if manifest.policy_version != expected_policy_version:
        return _offline_bundle_fallback(
            "bundle_policy_version_mismatch",
            manifest=manifest,
            manifest_sha256=actual_manifest_sha,
            state_dict_sha256=state_sha,
        )
    admission = manifest.admission
    holdout_values = tuple(
        int(value) for value in admission.get("external_holdout_seed_values", ())
    )
    if (
        manifest.bundle_schema_version != "d3_learning_model_bundle_v3"
        or admission.get("stage") != "development"
        or tuple(admission.get("allowed_modes", ())) != ("shadow",)
        or admission.get("assist_authorized") is not False
        or admission.get("rule_fallback_required") is not True
        or not set(reserved_seeds).issubset(set(holdout_values))
    ):
        return _offline_bundle_fallback(
            "bundle_not_frozen_development_shadow_only",
            manifest=manifest,
            manifest_sha256=actual_manifest_sha,
            state_dict_sha256=state_sha,
        )
    if not _policy_parameters_are_finite(loaded.policy):
        return _offline_bundle_fallback(
            "model_state_nonfinite",
            manifest=manifest,
            manifest_sha256=actual_manifest_sha,
            state_dict_sha256=state_sha,
        )
    source_assistant = loaded.assistant
    if not isinstance(source_assistant, LearningCostAssistant):
        return _offline_bundle_fallback(
            "model_assistant_type_invalid",
            manifest=manifest,
            manifest_sha256=actual_manifest_sha,
            state_dict_sha256=state_sha,
        )
    assistant = LearningCostAssistant(
        source_assistant.predictor,
        config=LearningAssistConfig(
            mode="assist",
            alpha=manifest.alpha,
            timeout_s=manifest.deadline_s,
            min_confidence=manifest.min_confidence,
            ood_z_threshold=manifest.ood_z_threshold,
        ),
        distribution_guard=source_assistant.distribution_guard,
    )
    return _OfflineBundle(
        assistant=assistant,
        loaded=True,
        fallback_reason=None,
        manifest=manifest,
        manifest_sha256=actual_manifest_sha,
        state_dict_sha256=state_sha,
    )


def _offline_bundle_fallback(
    reason: str,
    *,
    manifest: ModelBundleManifest | None = None,
    manifest_sha256: str | None = None,
    state_dict_sha256: str | None = None,
) -> _OfflineBundle:
    return _OfflineBundle(
        assistant=RuleFallbackLearningAssistant(reason, mode="assist"),
        loaded=False,
        fallback_reason=reason,
        manifest=manifest,
        manifest_sha256=manifest_sha256,
        state_dict_sha256=state_dict_sha256,
    )


def _execute_arm(
    *,
    pair: PairedInterventionSeedPair,
    arm: PairedInterventionArmSpecification,
    evidence: PlanningFrameEvidence,
    assistant: LearningCostAssistant | RuleFallbackLearningAssistant | None,
    bundle_loaded: bool,
    config: PlannerConfig,
    weights: CostWeights,
    rule_hash: str,
    action_mask_hash: str,
) -> _RawArmExecution:
    if arm.arm_kind == CONTROL_ARM:
        if assistant is not None or bundle_loaded:
            _fail("offline_control_arm_learning_boundary_invalid")
    elif assistant is None or bundle_loaded != isinstance(
        assistant, LearningCostAssistant
    ):
        _fail("offline_treatment_bundle_state_invalid")

    rule_result = _required_rule_result(evidence)
    replay_config = _offline_replay_planner_config(config, evidence)
    frozen_model = _FrozenPlanningFrameCostModel(
        rule_result,
        config=replay_config,
        weights=weights,
    )
    planner = AssignmentPlanner(
        cost_model=frozen_model,
        config=replay_config,
        learning_assistant=assistant,
    )
    previous_plan = evidence.previous_plan
    if previous_plan is not None:
        previous_plan = planner.publish_plan(previous_plan)
    plan = planner.plan(
        evidence.tracks,
        evidence.resources,
        timestamp=float(evidence.timestamp_s),
        previous_plan=previous_plan,
        window_id=None if evidence.plan is None else evidence.plan.window_id,
        expected_previous_version=arm.expected_previous_plan_version,
        forced_replan=evidence.forced_replan,
        publish=False,
    )
    replay = planner.latest_planning_evidence
    if not replay.available:
        _fail("offline_replay_evidence_unavailable", replay.reason)
    replay_rule = _required_rule_result(replay)
    if not _matrix_results_equivalent(replay_rule, rule_result):
        _fail("rule_matrix_replay_mismatch")
    replay_action_hash = canonical_learning_action_mask_sha256(
        replay_rule,
        expected_previous_version=arm.expected_previous_plan_version,
        current_plan_version=arm.current_plan_version,
    )
    if replay_action_hash != action_mask_hash:
        _fail("action_mask_replay_mismatch")
    if arm.arm_kind == CONTROL_ARM and evidence.plan is not None:
        if not _control_plan_replay_matches(plan, evidence.plan):
            _fail("control_plan_replay_mismatch")

    effective = replay.effective_matrix_result
    if effective is None:
        _fail("offline_effective_matrix_unavailable")
    if not np.array_equal(
        effective.hard_safe_candidate_mask,
        replay_rule.hard_safe_candidate_mask,
    ):
        _fail("offline_effective_action_mask_mismatch")
    metadata = effective.metadata
    learning_applied = bool(metadata.get("learning_applied", False))
    fallback_reason = metadata.get("learning_fallback_reason")
    fallback_reason = None if fallback_reason is None else str(fallback_reason)
    rule_fallback = arm.arm_kind == TREATMENT_ARM and not learning_applied
    if arm.arm_kind == CONTROL_ARM:
        learning_applied = False
        rule_fallback = False
        fallback_reason = None
    inference_s = float(metadata.get("learning_inference_elapsed_s", 0.0) or 0.0)
    if not isfinite(inference_s) or inference_s < 0.0:
        _fail("offline_inference_elapsed_invalid")
    plan = _annotate_isolated_plan(
        plan,
        pair=pair,
        arm=arm,
        bundle_loaded=bundle_loaded,
        learning_applied=learning_applied,
        fallback_reason=fallback_reason,
    )
    canonical_runtime_payload_sha256(plan)
    return _RawArmExecution(
        pair=pair,
        arm=arm,
        plan=plan,
        rule_matrix_sha256=rule_hash,
        action_mask_sha256=action_mask_hash,
        effective_matrix_sha256=canonical_rule_cost_matrix_sha256(effective),
        learning_cost_applied=learning_applied,
        rule_fallback_applied=rule_fallback,
        fallback_reason=fallback_reason,
        inference_elapsed_ms=inference_s * 1000.0,
    )


def _annotate_isolated_plan(
    plan: AssignmentPlan,
    *,
    pair: PairedInterventionSeedPair,
    arm: PairedInterventionArmSpecification,
    bundle_loaded: bool,
    learning_applied: bool,
    fallback_reason: str | None,
) -> AssignmentPlan:
    identity_digest = canonical_paired_intervention_sha256(
        {
            "pair_id": pair.pair_id,
            "arm_spec_sha256": arm.fingerprint,
            "output_plan_version": plan.version,
            "binding_signature": tuple(sorted(_binding_signature(plan))),
        }
    )
    plan_id = f"d3-offline-{arm.seed}-{arm.arm_kind}-{identity_digest[:12]}"
    assignments = tuple(
        replace(
            assignment,
            source_node_id="d3_offline_intervention",
            link_type="offline_isolated",
            plan_version=plan.version,
            metadata={
                **dict(assignment.metadata),
                "current_plan_id": plan_id,
                "current_plan_version": plan.version,
                "intervention_scope": OFFLINE_INTERVENTION_SCOPE,
                "isolated_simulation": True,
                "runtime_execution_allowed": False,
            },
        )
        for assignment in plan.assignments
    )
    return replace(
        plan,
        plan_id=plan_id,
        assignments=assignments,
        human_authorization_state="offline_not_authorized",
        source_node_id="d3_offline_intervention",
        link_type="offline_isolated",
        metadata={
            **dict(plan.metadata),
            "current_plan_id": plan_id,
            "current_plan_version": plan.version,
            "intervention_scope": OFFLINE_INTERVENTION_SCOPE,
            "isolated_simulation": True,
            "paired_intervention_pair_id": pair.pair_id,
            "paired_intervention_arm_kind": arm.arm_kind,
            "learning_bundle_loaded_for_offline_intervention": bundle_loaded,
            "learning_cost_intervention_applied": learning_applied,
            "learning_fallback_reason": fallback_reason,
            "ppo_enabled": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "runtime_execution_allowed": False,
            "runtime_ack_available": False,
            "outcome_available": False,
            "counterfactual_available": False,
            "causal_available": False,
        },
    )


def _offline_replay_planner_config(
    config: PlannerConfig,
    evidence: PlanningFrameEvidence,
) -> PlannerConfig:
    plan = evidence.plan
    if plan is None:
        _fail("offline_execution_planning_frame_incomplete")
    return replace(
        config,
        human_authorization_state=plan.human_authorization_state,
        source_node_id=plan.source_node_id,
        target_node_id=plan.target_node_id,
        link_type=plan.link_type,
    )


def _paired_frame_metrics(
    *,
    pair: PairedInterventionSeedPair,
    evidence: PlanningFrameEvidence,
    control: _RawArmExecution,
    treatment: _RawArmExecution,
    config: PlannerConfig,
) -> ShadowFrameMetrics:
    rule_result = _required_rule_result(evidence)
    control_cost, control_unmet, control_duplicate, control_hard = _score_plan(
        control.plan,
        rule_result,
        evidence,
        high_threat_threshold=config.high_threat_threshold,
    )
    treatment_cost, treatment_unmet, treatment_duplicate, treatment_hard = _score_plan(
        treatment.plan,
        rule_result,
        evidence,
        high_threat_threshold=config.high_threat_threshold,
    )
    previous_signature = (
        frozenset() if evidence.previous_plan is None else _binding_signature(evidence.previous_plan)
    )
    return ShadowFrameMetrics(
        scenario_version=pair.control.scenario_version,
        seed=pair.seed,
        episode=pair.pair_id,
        frame_index=0,
        rule_assignment_cost=control_cost,
        shadow_assignment_cost=treatment_cost,
        rule_high_threat_unmet=control_unmet,
        shadow_high_threat_unmet=treatment_unmet,
        rule_churn=len(_binding_signature(control.plan) ^ previous_signature),
        shadow_churn=len(_binding_signature(treatment.plan) ^ previous_signature),
        rule_duplicate_count=control_duplicate,
        shadow_duplicate_count=treatment_duplicate,
        rule_hard_violation_count=control_hard,
        shadow_hard_violation_count=treatment_hard,
        inference_elapsed_ms=treatment.inference_elapsed_ms,
        fallback_reason=treatment.fallback_reason,
    )


def _build_paired_report(
    *,
    specification: PairedInterventionSpecification,
    frames: tuple[ShadowFrameMetrics, ...],
    planning_frames: Mapping[int, PlanningFrameEvidence],
    bundle: _OfflineBundle,
) -> ShadowEvaluationReport:
    input_hashes = {
        str(seed): canonical_planning_frame_snapshot_sha256(frame)
        for seed, frame in sorted(planning_frames.items())
    }
    input_set_sha = canonical_runtime_payload_sha256(input_hashes)
    split_hash = canonical_runtime_payload_sha256(
        {
            "reserved_seed_policy": specification.reserved_seed_policy_version,
            "reserved_seeds": specification.reserved_seeds,
            "input_hashes": input_hashes,
        }
    )
    model_sha = bundle.state_dict_sha256 or canonical_runtime_payload_sha256(
        {"model_state": "unavailable"}
    )
    fallback_counts = Counter(
        item.fallback_reason for item in frames if item.fallback_reason is not None
    )
    per_seed = {
        str(item.seed): {
            "frame_count": 1,
            "rule_assignment_cost_mean": item.rule_assignment_cost,
            "shadow_assignment_cost_mean": item.shadow_assignment_cost,
            "rule_high_threat_unmet_total": item.rule_high_threat_unmet,
            "shadow_high_threat_unmet_total": item.shadow_high_threat_unmet,
            "rule_churn_mean": item.rule_churn,
            "shadow_churn_mean": item.shadow_churn,
            "fallback_frame_count": int(item.fallback_reason is not None),
        }
        for item in frames
    }
    elapsed = np.asarray([item.inference_elapsed_ms for item in frames], dtype=float)
    return ShadowEvaluationReport(
        split_hash=split_hash,
        dataset_frames_sha256=input_set_sha,
        model_state_dict_sha256=model_sha,
        evaluated_split="reserved_seed_1000_1019_offline_intervention",
        frame_count=len(frames),
        unseen_seed_count=len({item.seed for item in frames}),
        rule_assignment_cost_mean=float(
            np.mean([item.rule_assignment_cost for item in frames])
        ),
        shadow_assignment_cost_mean=float(
            np.mean([item.shadow_assignment_cost for item in frames])
        ),
        rule_high_threat_unmet_total=sum(
            item.rule_high_threat_unmet for item in frames
        ),
        shadow_high_threat_unmet_total=sum(
            item.shadow_high_threat_unmet for item in frames
        ),
        rule_churn_mean=float(np.mean([item.rule_churn for item in frames])),
        shadow_churn_mean=float(np.mean([item.shadow_churn for item in frames])),
        rule_duplicate_count=sum(item.rule_duplicate_count for item in frames),
        shadow_duplicate_count=sum(item.shadow_duplicate_count for item in frames),
        rule_hard_violation_count=sum(
            item.rule_hard_violation_count for item in frames
        ),
        shadow_hard_violation_count=sum(
            item.shadow_hard_violation_count for item in frames
        ),
        inference_p50_ms=float(np.percentile(elapsed, 50)),
        inference_p95_ms=float(np.percentile(elapsed, 95)),
        fallback_reasons=dict(sorted(fallback_counts.items())),
        rule_matrix_unchanged=True,
        per_seed_metrics=per_seed,
        promotion_manifest=unavailable_promotion_manifest(
            reason="offline_intervention_execution_requires_d6_outcome_sidecar",
            split_hash=split_hash,
            dataset_frames_sha256=input_set_sha,
            model_state_dict_sha256=model_sha,
        ),
        frames=frames,
    )


def _finalize_arm_execution(
    raw: _RawArmExecution,
    *,
    report_sha: str,
) -> OfflineInterventionArmExecution:
    receipt = PairedInterventionExecutionReceipt(
        pair_id=raw.pair.pair_id,
        seed=raw.pair.seed,
        arm_kind=raw.arm.arm_kind,
        arm_spec_sha256=raw.arm.fingerprint,
        paired_evaluator_schema_version=SHADOW_EVALUATION_SCHEMA_V2,
        paired_evaluator_report_sha256=report_sha,
        input_snapshot_sha256=raw.arm.observation_input_snapshot_sha256,
        rule_cost_matrix_sha256=raw.rule_matrix_sha256,
        action_mask_sha256=raw.action_mask_sha256,
        planner_path=raw.arm.planner_path,
        source_plan_version=raw.arm.source_plan_version,
        expected_previous_plan_version=raw.arm.expected_previous_plan_version,
        current_plan_version=raw.arm.current_plan_version,
        output_plan_id=raw.plan.plan_id,
        output_plan_version=raw.plan.version,
        output_plan_payload_sha256=canonical_runtime_payload_sha256(raw.plan),
        isolated_simulation=True,
        learning_cost_applied=raw.learning_cost_applied,
        rule_matrix_unchanged=True,
        deterministic_action_mask_enforced=True,
        reachability_gate_enforced=True,
        capacity_gate_enforced=True,
        version_gate_enforced=True,
        hysteresis_gate_enforced=True,
        safety_gate_enforced=True,
        rule_fallback_available=True,
        rule_fallback_applied=raw.rule_fallback_applied,
        fallback_reason=raw.fallback_reason,
        hysteresis_decision=raw.plan.decision_state,
        inference_elapsed_ms=raw.inference_elapsed_ms,
        nonfinite_value_count=0,
        online_label_key_count=0,
        global_track_id_rewrite_count=0,
    )
    return OfflineInterventionArmExecution(
        arm_specification=raw.arm,
        plan=raw.plan,
        effective_matrix_sha256=raw.effective_matrix_sha256,
        learning_cost_applied=raw.learning_cost_applied,
        rule_fallback_applied=raw.rule_fallback_applied,
        fallback_reason=raw.fallback_reason,
        inference_elapsed_ms=raw.inference_elapsed_ms,
        receipt=receipt,
    )


def _validate_pair_frame(
    pair: PairedInterventionSeedPair,
    evidence: PlanningFrameEvidence,
) -> None:
    _validate_planning_frame_basics(evidence)
    for arm in (pair.control, pair.treatment):
        if arm.seed != pair.seed:
            _fail("offline_execution_seed_mismatch")
        if canonical_planning_frame_snapshot_sha256(evidence) != (
            arm.observation_input_snapshot_sha256
        ):
            _fail("offline_execution_input_snapshot_sha256_mismatch")
        if float(evidence.timestamp_s) != arm.intervention_timestamp_s:
            _fail("offline_execution_timestamp_mismatch")
        if evidence.previous_plan_version != arm.current_plan_version:
            _fail("offline_execution_previous_plan_version_mismatch")
        if evidence.previous_plan is None:
            if arm.current_plan_version != 0:
                _fail("offline_execution_source_plan_missing")
        elif (
            evidence.previous_plan.plan_id != arm.source_plan_id
            or evidence.previous_plan.version != arm.source_plan_version
        ):
            _fail("offline_execution_source_plan_mismatch")
    if evidence.learning_state not in {
        "rule_only",
        "shadow_proposal",
        "rule_fallback",
    }:
        _fail("offline_execution_input_not_rule_control")


def _validate_planning_frame_basics(evidence: PlanningFrameEvidence) -> None:
    if not isinstance(evidence, PlanningFrameEvidence):
        _fail("offline_execution_planning_frame_type_invalid")
    if not evidence.available:
        _fail("offline_execution_planning_frame_unavailable", evidence.reason)
    if evidence.timestamp_s is None or not isfinite(float(evidence.timestamp_s)):
        _fail("offline_execution_timestamp_invalid")
    if evidence.rule_matrix_result is None or evidence.plan is None:
        _fail("offline_execution_planning_frame_incomplete")
    _validate_matrix_result(evidence.rule_matrix_result)
    _assert_truth_free(evidence)
    _assert_all_finite(evidence)


def _validate_matrix_result(result: CostMatrixResult) -> None:
    matrix = np.asarray(result.matrix, dtype=float)
    unassigned = np.asarray(result.unassigned_costs, dtype=float)
    if matrix.shape != (len(result.target_ids), len(result.resource_ids)):
        _fail("offline_execution_rule_matrix_shape_mismatch")
    if unassigned.shape != (len(result.target_ids),):
        _fail("offline_execution_unassigned_cost_shape_mismatch")
    if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(unassigned)):
        _fail("offline_execution_rule_input_nonfinite")
    mask = result.hard_safe_candidate_mask
    if mask.shape != matrix.shape:
        _fail("offline_execution_action_mask_shape_mismatch")


def _validate_execution_config(
    config: PlannerConfig,
    weights: CostWeights,
) -> None:
    _assert_all_finite(config)
    _assert_all_finite(weights)
    if config.solver_name not in {"hungarian", "hungarian_demand_slots"}:
        _fail("offline_execution_solver_unsupported")


def _required_rule_result(evidence: PlanningFrameEvidence) -> CostMatrixResult:
    result = evidence.rule_matrix_result
    if result is None:
        _fail("offline_execution_rule_matrix_unavailable")
    return result


def _remove_recorded_switch_penalty(result: CostMatrixResult) -> CostMatrixResult:
    matrix = np.asarray(result.matrix, dtype=float).copy()
    breakdowns: list[list[dict[str, float]]] = []
    for row_index, row in enumerate(result.breakdowns):
        output_row: list[dict[str, float]] = []
        for column_index, raw in enumerate(row):
            breakdown = dict(raw)
            penalty = max(
                0.0,
                float(breakdown.get("reassignment_switch_penalty", 0.0)),
            )
            if penalty:
                matrix[row_index, column_index] -= penalty
                breakdown["reassignment_switch_penalty"] = 0.0
                breakdown["total"] = float(matrix[row_index, column_index])
            output_row.append(breakdown)
        breakdowns.append(output_row)
    return replace(
        result,
        matrix=matrix,
        breakdowns=tuple(tuple(row) for row in breakdowns),
    )


def _copy_matrix_result(result: CostMatrixResult) -> CostMatrixResult:
    return CostMatrixResult(
        matrix=np.asarray(result.matrix, dtype=float).copy(),
        breakdowns=tuple(
            tuple(dict(value) for value in row) for row in result.breakdowns
        ),
        target_ids=tuple(result.target_ids),
        resource_ids=tuple(result.resource_ids),
        unassigned_costs=np.asarray(result.unassigned_costs, dtype=float).copy(),
        target_threat_scores=tuple(float(value) for value in result.target_threat_scores),
        reject_reasons=tuple(tuple(value for value in row) for row in result.reject_reasons),
        candidate_mask=(
            None
            if result.candidate_mask is None
            else np.asarray(result.candidate_mask, dtype=bool).copy()
        ),
        metadata=dict(result.metadata),
    )


def _matrix_results_equivalent(
    left: CostMatrixResult,
    right: CostMatrixResult,
) -> bool:
    return bool(
        left.target_ids == right.target_ids
        and left.resource_ids == right.resource_ids
        and np.allclose(left.matrix, right.matrix, rtol=0.0, atol=1.0e-12)
        and np.array_equal(
            left.hard_safe_candidate_mask,
            right.hard_safe_candidate_mask,
        )
        and np.allclose(
            left.unassigned_costs,
            right.unassigned_costs,
            rtol=0.0,
            atol=1.0e-12,
        )
    )


def _matrix_payload(result: CostMatrixResult | None) -> Mapping[str, Any]:
    if result is None:
        _fail("offline_execution_rule_matrix_unavailable")
    return {
        "target_ids": result.target_ids,
        "resource_ids": result.resource_ids,
        "matrix": result.matrix,
        "unassigned_costs": result.unassigned_costs,
        "target_threat_scores": result.target_threat_scores,
        "reject_reasons": result.reject_reasons,
        "candidate_mask": result.hard_safe_candidate_mask,
        "breakdowns": result.breakdowns,
    }


def _score_plan(
    plan: AssignmentPlan,
    result: CostMatrixResult,
    evidence: PlanningFrameEvidence,
    *,
    high_threat_threshold: float,
) -> tuple[float, int, int, int]:
    target_index = {value: index for index, value in enumerate(result.target_ids)}
    resource_index = {value: index for index, value in enumerate(result.resource_ids)}
    mask = result.hard_safe_candidate_mask
    used_resources: set[str] = set()
    assigned_count = Counter(item.target_id for item in plan.assignments)
    total = 0.0
    duplicates = 0
    hard = 0
    for assignment in plan.assignments:
        row = target_index.get(assignment.target_id)
        column = resource_index.get(assignment.resource_id)
        if assignment.resource_id in used_resources:
            duplicates += 1
        used_resources.add(assignment.resource_id)
        if row is None or column is None:
            hard += 1
            continue
        if not mask[row, column]:
            hard += 1
        total += float(result.matrix[row, column])
    high_threat_unmet = 0
    for index, track in enumerate(evidence.tracks):
        required = track.effective_demand.required_resource_count
        shortfall = max(0, required - assigned_count.get(track.track_id, 0))
        total += shortfall * float(result.unassigned_costs[index])
        if track.threat_score >= high_threat_threshold:
            high_threat_unmet += shortfall
    return float(total), high_threat_unmet, duplicates, hard


def _binding_signature(plan: AssignmentPlan) -> frozenset[tuple[str, str]]:
    return frozenset(
        (assignment.target_id, assignment.resource_id)
        for assignment in plan.assignments
    )


def _control_plan_replay_matches(
    replayed: AssignmentPlan,
    recorded: AssignmentPlan,
) -> bool:
    """Require exact executable semantics while ignoring generated plan identity."""

    return (
        _binding_signature(replayed) == _binding_signature(recorded)
        and replayed.execution_signature() == recorded.execution_signature()
        and replayed.version == recorded.version
        and replayed.window_id == recorded.window_id
        and replayed.decision_state == recorded.decision_state
        and replayed.changed == recorded.changed
        and replayed.resource_count == recorded.resource_count
        and replayed.target_count == recorded.target_count
    )


def _policy_parameters_are_finite(policy: Any) -> bool:
    try:
        return all(
            bool(np.all(np.isfinite(value.detach().cpu().numpy())))
            for value in policy.state_dict().values()
        )
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_truth_free(value: Any, path: str = "$") -> None:
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _assert_truth_free(getattr(value, item.name), f"{path}.{item.name}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_INPUT_KEYS:
                _fail("offline_execution_online_label_key_present", f"{path}.{key}")
            _assert_truth_free(item, f"{path}.{key}")
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for index, item in enumerate(value):
            _assert_truth_free(item, f"{path}[{index}]")


def _assert_all_finite(value: Any, path: str = "$") -> None:
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _assert_all_finite(getattr(value, item.name), f"{path}.{item.name}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_all_finite(item, f"{path}.{key}")
        return
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "fci" and not np.all(np.isfinite(value)):
            _fail("offline_execution_nonfinite_value", path)
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for index, item in enumerate(value):
            _assert_all_finite(item, f"{path}[{index}]")
        return
    if isinstance(value, (float, np.floating)) and not isfinite(float(value)):
        _fail("offline_execution_nonfinite_value", path)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _fail(code: str, message: str | None = None) -> None:
    raise PairedInterventionContractError(code, message)


__all__ = [
    "OFFLINE_PAIRED_INTERVENTION_EXECUTION_SCHEMA_V1",
    "OFFLINE_PAIRED_INTERVENTION_REPORT_KIND_V1",
    "OfflineInterventionArmExecution",
    "OfflinePairedInterventionExecution",
    "canonical_learning_action_mask_sha256",
    "canonical_planning_frame_snapshot_sha256",
    "canonical_rule_cost_matrix_sha256",
    "execute_offline_paired_intervention",
    "write_offline_paired_intervention_execution",
]
