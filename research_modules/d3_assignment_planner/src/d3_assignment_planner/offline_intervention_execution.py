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
from typing import TYPE_CHECKING, Any

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
from .models import (
    Assignment,
    AssignmentPlan,
    CoalitionPlan,
    CostWeights,
    DemandSatisfactionSummary,
    PlannerConfig,
    TargetTrack,
    continue_active_secondary_plan,
    prepare_secondary_takeover_plan,
)
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
from .planning_evidence import (
    PlanningFrameEvidence,
    canonical_recorded_authority_transition_sha256,
)
from .regional import (
    REGIONAL_OWNER_LAYERS,
    RegionalAuthorityGrant,
    RegionalAuthorityInput,
    RegionalCoalitionCommitEvidence,
)
from .runtime_plan_ack import (
    canonical_runtime_payload_sha256,
    validated_assignment_plan_payload_sha256,
)
from .shadow_evaluation import (
    SHADOW_EVALUATION_SCHEMA_V2,
    ShadowEvaluationReport,
    ShadowFrameMetrics,
)

if TYPE_CHECKING:
    from .learning_intervention_eligibility import (
        LearningInterventionFrameEvidence,
    )


OFFLINE_PAIRED_INTERVENTION_EXECUTION_SCHEMA_V1 = (
    "d3.offline-paired-intervention-execution.v1"
)
OFFLINE_PAIRED_INTERVENTION_REPORT_KIND_V1 = (
    "reserved_seed_rule_vs_development_bundle_intervention"
)
OFFLINE_ISOLATED_TARGET_INVENTORY_SCHEMA_V1 = (
    "d3.offline-isolated-target-inventory.v1"
)
OFFLINE_RECORDED_COALITION_IDENTITY_SCHEMA_V1 = (
    "d3.offline-recorded-coalition-identity.v1"
)
ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCHEMA_V1 = (
    "d3.isolated-learning-intervention-frame-replay.v1"
)
ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCOPE = (
    "single-frame-checkpoint-selection-no-admission-no-authority"
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
        "physical_outcome",
        "intercept_success",
        "reward",
    }
)

_REGIONAL_PLAN_EXECUTION_METADATA_KEYS = frozenset(
    {
        "plan_schema",
        "plan_owner",
        "active_plan_owner",
        "owner_node_id",
        "current_plan_owner",
        "current_plan_owner_node_id",
        "secondary_takeover_state",
        "secondary_plan_executable",
        "secondary_activated_at_s",
        "secondary_lease_expires_at_s",
        "secondary_leader_epoch",
        "activation_state",
        "activation_at_s",
        "executable",
        "regional_plan_schema",
        "regional_authorities",
        "regional_owner_layers",
        "regional_owner_node_ids",
        "regional_min_lease_expires_at_s",
        "regional_max_epoch",
        "regional_execution_allowed",
        "regional_commit_modes",
        "regional_single_member_authority_count",
        "regional_atomic_coalition_commit_count",
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
class IsolatedLearningInterventionFrameReplay:
    """One truth-free rule/treatment replay for checkpoint selection.

    This DTO covers one anonymous planning frame only.  It does not validate
    holdout seed inventory or split completeness, and it carries no runtime
    acknowledgement, outcome, reward, admission, publication, or authority.
    Main/D6 must validate the reserved-seed manifest around a sequence of these
    records before any formal experiment claim is made.
    """

    sequence_index: int
    input_snapshot_sha256: str
    expected_bundle_manifest_sha256: str
    actual_bundle_manifest_sha256: str | None
    expected_policy_version: str
    actual_policy_version: str | None
    bundle_state_dict_sha256: str | None
    bundle_loaded: bool
    bundle_fallback_reason: str | None
    rule_frame: PlanningFrameEvidence
    treatment_frame: PlanningFrameEvidence
    eligibility: "LearningInterventionFrameEvidence"
    content_sha256: str
    schema_version: str = (
        ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCHEMA_V1
    )
    replay_scope: str = ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCOPE

    def __post_init__(self) -> None:
        from .learning_intervention_eligibility import (
            evaluate_learning_intervention_candidate_frame,
            validate_learning_intervention_frame_evidence,
        )

        if (
            self.schema_version
            != ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCHEMA_V1
        ):
            _fail("single_frame_replay_schema_unsupported")
        if self.replay_scope != ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCOPE:
            _fail("single_frame_replay_scope_invalid")
        _single_frame_sequence_index(self.sequence_index)
        _single_frame_sha256(
            self.input_snapshot_sha256,
            "input_snapshot_sha256",
        )
        _single_frame_sha256(
            self.expected_bundle_manifest_sha256,
            "expected_bundle_manifest_sha256",
        )
        _single_frame_required_text(
            self.expected_policy_version,
            "expected_policy_version",
        )
        if self.actual_bundle_manifest_sha256 is not None:
            _single_frame_sha256(
                self.actual_bundle_manifest_sha256,
                "actual_bundle_manifest_sha256",
            )
        if self.actual_policy_version is not None:
            _single_frame_required_text(
                self.actual_policy_version,
                "actual_policy_version",
            )
        if self.bundle_state_dict_sha256 is not None:
            _single_frame_sha256(
                self.bundle_state_dict_sha256,
                "bundle_state_dict_sha256",
            )
        if type(self.bundle_loaded) is not bool:
            _fail("single_frame_replay_bundle_loaded_type_invalid")
        if self.bundle_loaded:
            if (
                self.bundle_fallback_reason is not None
                or self.actual_bundle_manifest_sha256
                != self.expected_bundle_manifest_sha256
                or self.actual_policy_version != self.expected_policy_version
                or self.bundle_state_dict_sha256 is None
            ):
                _fail("single_frame_replay_bundle_state_invalid")
        else:
            _single_frame_required_text(
                self.bundle_fallback_reason,
                "bundle_fallback_reason",
            )

        source_hashes = (
            canonical_planning_frame_snapshot_sha256(self.rule_frame),
            canonical_planning_frame_snapshot_sha256(self.treatment_frame),
        )
        if source_hashes != (
            self.input_snapshot_sha256,
            self.input_snapshot_sha256,
        ):
            _fail("single_frame_replay_input_lineage_mismatch")
        if self.rule_frame.learning_state != "rule_only":
            _fail("single_frame_replay_rule_state_invalid")
        if tuple(item.track_id for item in self.rule_frame.tracks) != tuple(
            item.track_id for item in self.treatment_frame.tracks
        ):
            _fail("single_frame_replay_global_track_id_rewrite")

        validated = validate_learning_intervention_frame_evidence(
            self.eligibility
        )
        expected = evaluate_learning_intervention_candidate_frame(
            sequence_index=self.sequence_index,
            rule_frame=self.rule_frame,
            treatment_frame=self.treatment_frame,
        )
        if canonical_runtime_payload_sha256(validated.to_dict()) != (
            canonical_runtime_payload_sha256(expected.to_dict())
        ):
            _fail("single_frame_replay_eligibility_mismatch")
        if not self.bundle_loaded and validated.eligible:
            _fail("single_frame_replay_fallback_marked_eligible")

        _assert_truth_free(self)
        _assert_all_finite(self)
        _single_frame_sha256(self.content_sha256, "content_sha256")
        expected_content = (
            canonical_isolated_learning_intervention_frame_replay_sha256(self)
        )
        if self.content_sha256 != expected_content:
            _fail("single_frame_replay_content_sha256_mismatch")

    @property
    def isolated_simulation(self) -> bool:
        return True

    @property
    def runtime_publication_allowed(self) -> bool:
        return False

    @property
    def runtime_ack_available(self) -> bool:
        return False

    @property
    def authority_available(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        """Return the complete finite, truth-free replay payload."""

        payload = _single_frame_replay_payload(self)
        payload["content_sha256"] = self.content_sha256
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


@dataclass(frozen=True, slots=True)
class _PlanningArmReplay:
    planning_frame_evidence: PlanningFrameEvidence
    plan: AssignmentPlan
    effective_matrix: CostMatrixResult
    learning_cost_applied: bool
    rule_fallback_applied: bool
    fallback_reason: str | None
    inference_elapsed_ms: float


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
        "recorded_authority_transition_sha256": (
            evidence.recorded_authority_transition_sha256
        ),
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


def canonical_isolated_learning_intervention_frame_replay_sha256(
    value: IsolatedLearningInterventionFrameReplay,
) -> str:
    """Hash the complete replay payload except its self-referential hash."""

    if not isinstance(value, IsolatedLearningInterventionFrameReplay):
        _fail("single_frame_replay_type_invalid")
    payload = _single_frame_replay_payload(value)
    _assert_truth_free(payload)
    _assert_all_finite(payload)
    return canonical_runtime_payload_sha256(payload)


def replay_isolated_learning_intervention_frame(
    rule_frame: PlanningFrameEvidence,
    *,
    sequence_index: int,
    bundle_dir: str | Path,
    expected_manifest_sha256: str,
    expected_policy_version: str,
    planner_config: PlannerConfig | None = None,
    cost_weights: CostWeights | None = None,
) -> IsolatedLearningInterventionFrameReplay:
    """Replay one frozen rule frame through isolated rule and treatment arms.

    The development bundle is loaded through the existing shadow-only loader.
    Both planning calls use ``publish=False``.  The returned evidence is only
    single-frame checkpoint-selection evidence and cannot provide runtime ACK,
    outcome, reward, admission, publication, or authority.

    ``PlanningFrameEvidence`` is anonymous and deliberately has no experiment
    seed.  Reserved seeds, split identity, and holdout inventory completeness
    remain main/D6 manifest-runner responsibilities.  The local
    ``planner.publish_plan(previous_plan)`` call seeds only the isolated
    planner instance; neither replayed candidate is published to a runtime bus.
    """

    sequence = _single_frame_sequence_index(sequence_index)
    expected_manifest = _single_frame_sha256(
        expected_manifest_sha256,
        "expected_manifest_sha256",
    )
    expected_policy = _single_frame_required_text(
        expected_policy_version,
        "expected_policy_version",
    )
    _validate_planning_frame_basics(rule_frame)
    if rule_frame.learning_state != "rule_only":
        _fail("single_frame_replay_input_not_rule_control")
    if rule_frame.previous_plan is None:
        _fail("single_frame_replay_previous_plan_missing")
    effective_rule_result = rule_frame.effective_matrix_result
    if effective_rule_result is None:
        _fail("single_frame_replay_rule_effective_matrix_mismatch")
    _validate_matrix_result(effective_rule_result)
    if canonical_rule_cost_matrix_sha256(
        _required_rule_result(rule_frame)
    ) != canonical_rule_cost_matrix_sha256(effective_rule_result):
        _fail("single_frame_replay_rule_effective_matrix_mismatch")
    _validate_single_frame_rule_source_contract(rule_frame)

    config = planner_config or PlannerConfig()
    weights = cost_weights or CostWeights()
    _validate_execution_config(config, weights)
    input_snapshot_sha256 = canonical_planning_frame_snapshot_sha256(
        rule_frame
    )
    original_rule_matrix = np.asarray(rule_frame.rule_matrix, dtype=float).copy()
    rule_result = _required_rule_result(rule_frame)
    previous_version = int(rule_frame.previous_plan.version)
    rule_matrix_sha256 = canonical_rule_cost_matrix_sha256(rule_result)
    action_mask_sha256 = canonical_learning_action_mask_sha256(
        rule_result,
        expected_previous_version=previous_version,
        current_plan_version=previous_version,
    )

    offline_bundle = _load_offline_development_bundle(
        bundle_dir,
        expected_manifest_sha256=expected_manifest,
        expected_policy_version=expected_policy,
        reserved_seeds=(),
    )
    rule_arm = _replay_planning_arm(
        arm_kind=CONTROL_ARM,
        evidence=rule_frame,
        assistant=None,
        bundle_loaded=False,
        config=config,
        weights=weights,
        rule_hash=rule_matrix_sha256,
        action_mask_hash=action_mask_sha256,
        expected_previous_version=previous_version,
        current_plan_version=previous_version,
    )
    treatment_arm = _replay_planning_arm(
        arm_kind=TREATMENT_ARM,
        evidence=rule_frame,
        assistant=offline_bundle.assistant,
        bundle_loaded=offline_bundle.loaded,
        config=config,
        weights=weights,
        rule_hash=rule_matrix_sha256,
        action_mask_hash=action_mask_sha256,
        expected_previous_version=previous_version,
        current_plan_version=previous_version,
    )
    if not np.array_equal(
        original_rule_matrix,
        np.asarray(rule_frame.rule_matrix, dtype=float),
    ):
        _fail("rule_matrix_mutated_during_intervention")
    for replayed in (
        rule_arm.planning_frame_evidence,
        treatment_arm.planning_frame_evidence,
    ):
        if (
            canonical_planning_frame_snapshot_sha256(replayed)
            != input_snapshot_sha256
        ):
            _fail("single_frame_replay_input_lineage_mismatch")

    from .learning_intervention_eligibility import (
        evaluate_learning_intervention_candidate_frame,
    )

    eligibility = evaluate_learning_intervention_candidate_frame(
        sequence_index=sequence,
        rule_frame=rule_arm.planning_frame_evidence,
        treatment_frame=treatment_arm.planning_frame_evidence,
    )
    if not offline_bundle.loaded and eligibility.eligible:
        _fail("single_frame_replay_fallback_marked_eligible")

    actual_policy_version = (
        None
        if offline_bundle.manifest is None
        else offline_bundle.manifest.policy_version
    )
    values = {
        "sequence_index": sequence,
        "input_snapshot_sha256": input_snapshot_sha256,
        "expected_bundle_manifest_sha256": expected_manifest,
        "actual_bundle_manifest_sha256": offline_bundle.manifest_sha256,
        "expected_policy_version": expected_policy,
        "actual_policy_version": actual_policy_version,
        "bundle_state_dict_sha256": offline_bundle.state_dict_sha256,
        "bundle_loaded": offline_bundle.loaded,
        "bundle_fallback_reason": offline_bundle.fallback_reason,
        "rule_frame": rule_arm.planning_frame_evidence,
        "treatment_frame": treatment_arm.planning_frame_evidence,
        "eligibility": eligibility,
    }
    content_sha256 = canonical_runtime_payload_sha256(
        _single_frame_replay_payload_from_values(**values)
    )
    return IsolatedLearningInterventionFrameReplay(
        **values,
        content_sha256=content_sha256,
    )


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
    replay = _replay_planning_arm(
        arm_kind=arm.arm_kind,
        evidence=evidence,
        assistant=assistant,
        bundle_loaded=bundle_loaded,
        config=config,
        weights=weights,
        rule_hash=rule_hash,
        action_mask_hash=action_mask_hash,
        expected_previous_version=arm.expected_previous_plan_version,
        current_plan_version=arm.current_plan_version,
    )
    plan = _annotate_isolated_plan(
        replay.plan,
        pair=pair,
        arm=arm,
        planning_frame_evidence=evidence,
        offline_solve_source_plan=evidence.previous_plan,
        formal_authority_plan=evidence.plan,
        current_tracks=evidence.tracks,
        bundle_loaded=bundle_loaded,
        learning_applied=replay.learning_cost_applied,
        fallback_reason=replay.fallback_reason,
    )
    validated_assignment_plan_payload_sha256(plan)
    return _RawArmExecution(
        pair=pair,
        arm=arm,
        plan=plan,
        rule_matrix_sha256=rule_hash,
        action_mask_sha256=action_mask_hash,
        effective_matrix_sha256=canonical_rule_cost_matrix_sha256(
            replay.effective_matrix
        ),
        learning_cost_applied=replay.learning_cost_applied,
        rule_fallback_applied=replay.rule_fallback_applied,
        fallback_reason=replay.fallback_reason,
        inference_elapsed_ms=replay.inference_elapsed_ms,
    )


def _replay_planning_arm(
    *,
    arm_kind: str,
    evidence: PlanningFrameEvidence,
    assistant: LearningCostAssistant | RuleFallbackLearningAssistant | None,
    bundle_loaded: bool,
    config: PlannerConfig,
    weights: CostWeights,
    rule_hash: str,
    action_mask_hash: str,
    expected_previous_version: int,
    current_plan_version: int,
) -> _PlanningArmReplay:
    if arm_kind == CONTROL_ARM:
        if assistant is not None or bundle_loaded:
            _fail("offline_control_arm_learning_boundary_invalid")
    elif arm_kind != TREATMENT_ARM:
        _fail("offline_arm_kind_invalid")
    elif assistant is None or bundle_loaded != isinstance(
        assistant, LearningCostAssistant
    ):
        _fail("offline_treatment_bundle_state_invalid")

    rule_result = _required_rule_result(evidence)
    if canonical_rule_cost_matrix_sha256(rule_result) != rule_hash:
        _fail("rule_matrix_replay_hash_mismatch")
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
    if evidence.planning_path == "regional_authority":
        if previous_plan is None:
            _fail("offline_regional_authority_replay_previous_plan_missing")
        authority = _recorded_regional_authority_input(evidence)
        plan = planner.plan_regional_authority(
            evidence.tracks,
            evidence.resources,
            timestamp=float(evidence.timestamp_s),
            previous_plan=previous_plan,
            authority=authority,
            expected_previous_version=expected_previous_version,
            window_id=None if evidence.plan is None else evidence.plan.window_id,
            publish=False,
        )
    else:
        plan = planner.plan(
            evidence.tracks,
            evidence.resources,
            timestamp=float(evidence.timestamp_s),
            previous_plan=previous_plan,
            window_id=None if evidence.plan is None else evidence.plan.window_id,
            expected_previous_version=expected_previous_version,
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
        expected_previous_version=expected_previous_version,
        current_plan_version=current_plan_version,
    )
    if replay_action_hash != action_mask_hash:
        _fail("action_mask_replay_mismatch")

    plan = _replay_recorded_coalition_identity(plan, evidence=evidence)
    plan = _replay_recorded_authority_identity(plan, evidence=evidence)
    if arm_kind == CONTROL_ARM and evidence.plan is not None:
        if not _control_plan_replay_matches(plan, evidence.plan):
            _fail("control_plan_replay_mismatch")
    replay = replace(
        replay,
        plan=plan,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        solver_name=plan.solver_name,
    )

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
    rule_fallback = arm_kind == TREATMENT_ARM and not learning_applied
    if arm_kind == CONTROL_ARM:
        learning_applied = False
        rule_fallback = False
        fallback_reason = None
    inference_s = float(metadata.get("learning_inference_elapsed_s", 0.0) or 0.0)
    if not isfinite(inference_s) or inference_s < 0.0:
        _fail("offline_inference_elapsed_invalid")
    return _PlanningArmReplay(
        planning_frame_evidence=replay,
        plan=plan,
        effective_matrix=effective,
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
    planning_frame_evidence: PlanningFrameEvidence,
    offline_solve_source_plan: AssignmentPlan | None,
    formal_authority_plan: AssignmentPlan | None,
    current_tracks: tuple[TargetTrack, ...],
    bundle_loaded: bool,
    learning_applied: bool,
    fallback_reason: str | None,
) -> AssignmentPlan:
    plan = _normalize_isolated_plan_target_inventory(
        plan,
        current_tracks=current_tracks,
    )
    identity_digest = canonical_paired_intervention_sha256(
        {
            "pair_id": pair.pair_id,
            "arm_spec_sha256": arm.fingerprint,
            "output_plan_version": plan.version,
            "binding_signature": tuple(sorted(_binding_signature(plan))),
            "target_inventory": {
                "target_count": plan.target_count,
                "unassigned_target_ids": plan.unassigned_target_ids,
                "incomplete_target_ids": plan.incomplete_target_ids,
            },
        }
    )
    plan_id = f"d3-offline-{arm.seed}-{arm.arm_kind}-{identity_digest[:12]}"
    solve_source_plan_sha256 = (
        None
        if offline_solve_source_plan is None
        else validated_assignment_plan_payload_sha256(
            offline_solve_source_plan
        )
    )
    authority_plan_sha256 = (
        None
        if formal_authority_plan is None
        else validated_assignment_plan_payload_sha256(formal_authority_plan)
    )
    frame_snapshot_sha256 = canonical_planning_frame_snapshot_sha256(
        planning_frame_evidence
    )
    frame_transition_schema = None
    frame_transition_sha256 = None
    if (
        offline_solve_source_plan is not None
        and formal_authority_plan is not None
    ):
        from .isolated_execution_plan import (
            ISOLATED_EXECUTION_PLANNING_FRAME_SCHEMA_V1,
            canonical_isolated_execution_planning_frame_sha256,
        )

        frame_transition_schema = ISOLATED_EXECUTION_PLANNING_FRAME_SCHEMA_V1
        frame_transition_sha256 = (
            canonical_isolated_execution_planning_frame_sha256(
                planning_frame_evidence
            )
        )
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
                "isolated_simulation_only": True,
                "production_runtime_ack": False,
                "runtime_publication_allowed": False,
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
            "paired_intervention_arm_id": arm.arm_id,
            "paired_intervention_arm_kind": arm.arm_kind,
            "paired_intervention_seed": arm.seed,
            "paired_intervention_arm_spec_sha256": arm.fingerprint,
            "source_snapshot_sha256": arm.observation_input_snapshot_sha256,
            "planning_frame_schema_version": (
                planning_frame_evidence.schema_version
            ),
            "planning_frame_transition_schema_version": (
                frame_transition_schema
            ),
            "planning_frame_path": planning_frame_evidence.planning_path,
            "planning_frame_timestamp_s": float(
                planning_frame_evidence.timestamp_s
            ),
            "planning_frame_snapshot_sha256": frame_snapshot_sha256,
            "planning_frame_transition_sha256": frame_transition_sha256,
            "offline_solve_source_plan_id": arm.source_plan_id,
            "offline_solve_source_plan_version": arm.source_plan_version,
            "offline_solve_source_plan_payload_sha256": (
                solve_source_plan_sha256
            ),
            "formal_authority_plan_id": (
                None
                if formal_authority_plan is None
                else formal_authority_plan.plan_id
            ),
            "formal_authority_plan_version": (
                None
                if formal_authority_plan is None
                else formal_authority_plan.version
            ),
            "formal_authority_plan_payload_sha256": authority_plan_sha256,
            "learning_bundle_loaded_for_offline_intervention": bundle_loaded,
            "learning_cost_intervention_applied": learning_applied,
            "learning_fallback_reason": fallback_reason,
            "ppo_enabled": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "isolated_simulation_only": True,
            "production_runtime_ack": False,
            "runtime_publication_allowed": False,
            "runtime_execution_allowed": False,
            "runtime_ack_available": False,
            "outcome_available": False,
            "counterfactual_available": False,
            "causal_available": False,
        },
    )


def _normalize_isolated_plan_target_inventory(
    plan: AssignmentPlan,
    *,
    current_tracks: tuple[TargetTrack, ...],
) -> AssignmentPlan:
    """Make the offline arm inventory explicit without changing bindings.

    A hysteresis hold can preserve the previous executable bindings while the
    current planning snapshot already contains new or unassignable targets.
    Those targets are pending execution, but they still belong to the current
    offline input roster and must be represented as unassigned/incomplete.
    """

    current_target_ids = tuple(track.track_id for track in current_tracks)
    if len(current_target_ids) != len(set(current_target_ids)):
        _fail("offline_plan_current_target_inventory_duplicate")
    if plan.target_count != len(current_target_ids):
        _fail(
            "offline_plan_target_count_snapshot_mismatch",
            "offline plan target_count does not match the current input roster",
        )
    current_target_set = set(current_target_ids)
    track_by_id = {track.track_id: track for track in current_tracks}
    assigned_counts = Counter(assignment.target_id for assignment in plan.assignments)
    previous_only_assignment_ids = tuple(
        sorted(set(assigned_counts) - current_target_set)
    )
    if previous_only_assignment_ids:
        _fail(
            "offline_plan_previous_only_executable_target",
            "offline plan contains an executable binding outside the current roster",
        )

    coalition_by_target = {}
    for coalition in plan.coalitions:
        if coalition.target_id in coalition_by_target:
            _fail("offline_plan_duplicate_target_coalition")
        coalition_by_target[coalition.target_id] = coalition
    summary_by_target = {}
    for summary in plan.demand_summaries:
        if summary.target_id in summary_by_target:
            _fail("offline_plan_duplicate_target_demand_summary")
        summary_by_target[summary.target_id] = summary

    normalized_summaries: list[DemandSatisfactionSummary] = []
    unassigned_target_ids: list[str] = []
    incomplete_target_ids: list[str] = []
    for target_id in current_target_ids:
        demand = track_by_id[target_id].effective_demand
        required = int(demand.required_resource_count)
        assigned = int(assigned_counts.get(target_id, 0))
        if assigned > required:
            _fail("offline_plan_target_assignment_exceeds_demand")
        coalition = coalition_by_target.get(target_id)
        if coalition is not None:
            if coalition.required_resource_count != required:
                _fail("offline_plan_coalition_demand_mismatch")
            if coalition.assigned_resource_count != assigned:
                _fail("offline_plan_coalition_assignment_count_mismatch")
        prior_summary = summary_by_target.get(target_id)
        if prior_summary is not None and (
            prior_summary.demand_required != required
            or prior_summary.demand_assigned != assigned
            or prior_summary.demand_shortfall != max(0, required - assigned)
        ):
            _fail("offline_plan_demand_summary_mismatch")

        shortfall = max(0, required - assigned)
        if assigned == 0:
            unassigned_target_ids.append(target_id)
        if shortfall > 0:
            incomplete_target_ids.append(target_id)
        normalized_summaries.append(
            DemandSatisfactionSummary(
                target_id=target_id,
                demand_required=required,
                demand_assigned=assigned,
                demand_shortfall=shortfall,
                coalition_complete=shortfall == 0,
                coalition_id=(
                    coalition.coalition_id
                    if coalition is not None
                    else (
                        None
                        if prior_summary is None
                        else prior_summary.coalition_id
                    )
                ),
                coalition_version=(
                    coalition.version
                    if coalition is not None
                    else (
                        None
                        if prior_summary is None
                        else prior_summary.coalition_version
                    )
                ),
                primary_resource_count=int(demand.primary_resource_count),
            )
        )

    normalized_unassigned = tuple(unassigned_target_ids)
    normalized_incomplete = tuple(incomplete_target_ids)
    normalized_coalitions = tuple(
        coalition
        for coalition in plan.coalitions
        if coalition.target_id in current_target_set
    )
    previous_inventory = {
        *(assignment.target_id for assignment in plan.assignments),
        *plan.unassigned_target_ids,
        *plan.incomplete_target_ids,
        *(coalition.target_id for coalition in plan.coalitions),
        *(summary.target_id for summary in plan.demand_summaries),
    }
    added_unassigned = tuple(
        target_id
        for target_id in normalized_unassigned
        if target_id not in set(plan.unassigned_target_ids)
    )
    added_incomplete = tuple(
        target_id
        for target_id in normalized_incomplete
        if target_id not in set(plan.incomplete_target_ids)
    )
    removed_previous_only = tuple(sorted(previous_inventory - current_target_set))
    changed = (
        normalized_unassigned != tuple(plan.unassigned_target_ids)
        or normalized_incomplete != tuple(plan.incomplete_target_ids)
        or normalized_coalitions != tuple(plan.coalitions)
        or tuple(normalized_summaries) != tuple(plan.demand_summaries)
    )
    normalized_summary_metadata = tuple(
        {
            "target_id": summary.target_id,
            "demand_required": summary.demand_required,
            "demand_assigned": summary.demand_assigned,
            "demand_shortfall": summary.demand_shortfall,
            "coalition_complete": summary.coalition_complete,
            "coalition_id": summary.coalition_id,
            "coalition_version": summary.coalition_version,
            "primary_resource_count": summary.primary_resource_count,
        }
        for summary in normalized_summaries
    )
    return replace(
        plan,
        unassigned_target_ids=normalized_unassigned,
        incomplete_target_ids=normalized_incomplete,
        coalitions=normalized_coalitions,
        demand_summaries=tuple(normalized_summaries),
        metadata={
            **dict(plan.metadata),
            "target_count": len(current_target_ids),
            "unassigned_target_ids": normalized_unassigned,
            "incomplete_target_ids": normalized_incomplete,
            "demand_summaries": normalized_summary_metadata,
            "isolated_target_inventory_schema": (
                OFFLINE_ISOLATED_TARGET_INVENTORY_SCHEMA_V1
            ),
            "isolated_target_inventory_ids": current_target_ids,
            "isolated_target_inventory_normalized": changed,
            "isolated_target_inventory_added_unassigned_ids": (
                added_unassigned
            ),
            "isolated_target_inventory_added_incomplete_ids": (
                added_incomplete
            ),
            "isolated_target_inventory_removed_previous_only_ids": (
                removed_previous_only
            ),
            "isolated_target_inventory_production_runtime_ack": False,
            "isolated_target_inventory_simulation_only": True,
        },
    )


def _offline_replay_planner_config(
    config: PlannerConfig,
    evidence: PlanningFrameEvidence,
) -> PlannerConfig:
    plan = evidence.plan
    if plan is None:
        _fail("offline_execution_planning_frame_incomplete")
    if evidence.planning_path == "authority_identity_publish":
        if evidence.previous_plan is None:
            _fail("offline_authority_replay_previous_plan_missing")
        # The online planner first emits an owner-neutral candidate and only
        # then applies the D4-selected authority identity. Replay that same
        # ordering instead of planning directly as the recorded new owner.
        plan = evidence.previous_plan
    return replace(
        config,
        human_authorization_state=plan.human_authorization_state,
        source_node_id=plan.source_node_id,
        target_node_id=plan.target_node_id,
        link_type=plan.link_type,
    )


def _recorded_regional_authority_input(
    evidence: PlanningFrameEvidence,
) -> RegionalAuthorityInput:
    """Rebuild the anonymous D4 authority input recorded in one D3 frame."""

    recorded = evidence.plan
    previous = evidence.previous_plan
    timestamp = evidence.timestamp_s
    if (
        evidence.planning_path != "regional_authority"
        or evidence.selection_source != "regional_authority"
        or recorded is None
        or previous is None
        or timestamp is None
    ):
        _fail("offline_regional_authority_replay_evidence_incomplete")
    try:
        recorded_sha256 = validated_assignment_plan_payload_sha256(recorded)
        previous_sha256 = validated_assignment_plan_payload_sha256(previous)
        transition_sha256 = canonical_recorded_authority_transition_sha256(
            planning_path=evidence.planning_path,
            selection_source=evidence.selection_source,
            timestamp_s=float(timestamp),
            plan=recorded,
            previous_plan=previous,
        )
    except Exception as exc:
        _fail("offline_regional_authority_replay_payload_invalid", str(exc))
    if not recorded_sha256 or not previous_sha256:
        _fail("offline_regional_authority_replay_payload_invalid")
    if transition_sha256 != evidence.recorded_authority_transition_sha256:
        _fail("offline_regional_authority_replay_transition_sha256_mismatch")
    if (
        recorded.version != previous.version + 1
        or recorded.previous_plan_id != previous.plan_id
    ):
        _fail("offline_regional_authority_replay_plan_lineage_invalid")
    if (
        abs(float(recorded.created_at) - float(timestamp)) > 1.0e-9
        or float(recorded.created_at) <= float(previous.created_at)
    ):
        _fail("offline_regional_authority_replay_plan_time_invalid")

    metadata = dict(recorded.metadata)
    if any(
        metadata.get(key) != "regional"
        for key in ("plan_owner", "active_plan_owner", "current_plan_owner")
    ):
        _fail("offline_regional_authority_replay_owner_invalid")
    if (
        metadata.get("activation_state") != "active"
        or metadata.get("executable") is not True
        or not str(recorded.source_node_id or "").strip()
        or recorded.link_type != "regional_multi_owner"
    ):
        _fail("offline_regional_authority_replay_plan_contract_invalid")
    try:
        activation_at_s = float(metadata["activation_at_s"])
        plan_lease_expires_at_s = float(metadata["secondary_lease_expires_at_s"])
        plan_epoch = int(metadata["secondary_leader_epoch"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail("offline_regional_authority_replay_plan_contract_invalid", str(exc))
    if (
        not isfinite(activation_at_s)
        or activation_at_s > float(timestamp)
        or not isfinite(plan_lease_expires_at_s)
        or plan_lease_expires_at_s <= float(timestamp)
        or plan_epoch < 0
    ):
        _fail("offline_regional_authority_replay_plan_contract_invalid")

    track_ids = tuple(track.track_id for track in evidence.tracks)
    target_set = set(track_ids)
    pending = set(recorded.unassigned_target_ids)
    if pending != set(recorded.incomplete_target_ids):
        _fail("offline_regional_authority_replay_pending_inventory_invalid")
    assignments_by_target = recorded.assignments_by_target()
    if set(assignments_by_target).intersection(pending):
        _fail("offline_regional_authority_replay_pending_target_authorized")
    if set(assignments_by_target) | pending != target_set:
        _fail("offline_regional_authority_replay_target_inventory_mismatch")

    summary_by_target = {
        summary.target_id: summary for summary in recorded.demand_summaries
    }
    if set(summary_by_target) != target_set:
        _fail("offline_regional_authority_replay_demand_inventory_mismatch")
    coalition_by_target = {
        coalition.target_id: coalition for coalition in recorded.coalitions
    }
    if len(coalition_by_target) != len(recorded.coalitions):
        _fail("offline_regional_authority_replay_coalition_inventory_invalid")

    groups: dict[
        tuple[str, str, str, int, float],
        dict[str, Any],
    ] = {}
    region_contracts: dict[str, tuple[str, str, str, int, float]] = {}
    assignment_epochs: list[int] = []
    assignment_leases: list[float] = []
    for target_id in track_ids:
        target_assignments = assignments_by_target.get(target_id, ())
        summary = summary_by_target[target_id]
        if not target_assignments:
            if (
                target_id not in pending
                or summary.demand_assigned != 0
                or summary.demand_shortfall != summary.demand_required
                or summary.coalition_complete
            ):
                _fail("offline_regional_authority_replay_pending_inventory_invalid")
            coalition = coalition_by_target.get(target_id)
            if coalition is not None and (
                coalition.members
                or coalition.assigned_resource_count != 0
                or coalition.complete
            ):
                _fail("offline_regional_authority_replay_pending_coalition_invalid")
            continue

        if summary.demand_assigned != len(target_assignments):
            _fail("offline_regional_authority_replay_assignment_count_mismatch")
        first_metadata = dict(target_assignments[0].metadata)
        try:
            owner_layer = str(first_metadata["regional_owner_layer"]).strip().lower()
            region_id = str(first_metadata["regional_region_id"]).strip()
            owner_node_id = str(first_metadata["owner_node_id"]).strip()
            epoch = int(first_metadata["regional_epoch"])
            lease_expires_at_s = float(
                first_metadata["regional_lease_expires_at_s"]
            )
            commit_required = bool(first_metadata["regional_commit_required"])
            commit_mode = str(first_metadata["regional_commit_mode"]).strip()
            commit_state = str(first_metadata["regional_commit_state"]).strip()
            commit_evidence_present = bool(
                first_metadata["regional_commit_evidence_present"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            _fail("offline_regional_authority_replay_assignment_contract_invalid", str(exc))
        if (
            owner_layer not in REGIONAL_OWNER_LAYERS
            or not region_id
            or not owner_node_id
            or epoch < previous.version
            or not isfinite(lease_expires_at_s)
            or lease_expires_at_s <= float(timestamp)
        ):
            _fail("offline_regional_authority_replay_assignment_contract_invalid")

        resource_ids: list[str] = []
        for assignment in target_assignments:
            item_metadata = dict(assignment.metadata)
            item_contract = (
                str(item_metadata.get("regional_owner_layer", "")).strip().lower(),
                str(item_metadata.get("regional_region_id", "")).strip(),
                str(item_metadata.get("owner_node_id", "")).strip(),
                int(item_metadata.get("regional_epoch", -1)),
                float(item_metadata.get("regional_lease_expires_at_s", float("nan"))),
                bool(item_metadata.get("regional_commit_required", False)),
                str(item_metadata.get("regional_commit_mode", "")).strip(),
                str(item_metadata.get("regional_commit_state", "")).strip(),
                bool(item_metadata.get("regional_commit_evidence_present", False)),
            )
            expected_contract = (
                owner_layer,
                region_id,
                owner_node_id,
                epoch,
                lease_expires_at_s,
                commit_required,
                commit_mode,
                commit_state,
                commit_evidence_present,
            )
            if item_contract != expected_contract:
                _fail("offline_regional_authority_replay_assignment_contract_mismatch")
            if (
                item_metadata.get("plan_owner") != "regional"
                or item_metadata.get("active_plan_owner") != "regional"
                or item_metadata.get("activation_state") != "active"
                or item_metadata.get("executable") is not True
                or assignment.source_node_id != owner_node_id
                or assignment.target_node_id != assignment.resource_id
                or assignment.link_type != f"regional_{owner_layer}"
            ):
                _fail("offline_regional_authority_replay_assignment_identity_invalid")
            resource_ids.append(assignment.resource_id)

        expected_commit_required = summary.demand_required > 1
        expected_commit_mode = (
            "atomic_coalition_commit"
            if expected_commit_required
            else "single_member_authority"
        )
        if (
            commit_required != expected_commit_required
            or commit_mode != expected_commit_mode
        ):
            _fail("offline_regional_authority_replay_commit_contract_invalid")
        if commit_required:
            if not commit_evidence_present or commit_state != "committed":
                _fail("offline_regional_authority_replay_commit_contract_invalid")
        elif commit_evidence_present:
            if commit_state != "single_member_authorized":
                _fail("offline_regional_authority_replay_commit_contract_invalid")
        elif commit_state != "single_member_authority":
            _fail("offline_regional_authority_replay_commit_contract_invalid")

        group_key = (
            region_id,
            owner_layer,
            owner_node_id,
            epoch,
            lease_expires_at_s,
        )
        prior_region_contract = region_contracts.setdefault(region_id, group_key)
        if prior_region_contract != group_key:
            _fail("offline_regional_authority_replay_region_contract_conflict")
        group = groups.setdefault(
            group_key,
            {"target_ids": [], "assignment_map": {}, "commits": []},
        )
        group["target_ids"].append(target_id)
        group["assignment_map"][target_id] = tuple(resource_ids)
        if commit_evidence_present:
            coalition = coalition_by_target.get(target_id)
            group["commits"].append(
                RegionalCoalitionCommitEvidence(
                    target_id=target_id,
                    coordinator_id=owner_node_id,
                    epoch=epoch,
                    lease_expires_at_s=lease_expires_at_s,
                    required_member_ids=tuple(resource_ids),
                    acked_member_ids=tuple(resource_ids),
                    commit_required=commit_required,
                    state=commit_state,
                    atomic_committed=commit_required,
                    execution_authorized=True,
                    coalition_id=(None if coalition is None else coalition.coalition_id),
                    coalition_version=(None if coalition is None else coalition.version),
                )
            )
        assignment_epochs.append(epoch)
        assignment_leases.append(lease_expires_at_s)

    if not groups:
        _fail("offline_regional_authority_replay_no_executable_grants")
    if (
        plan_epoch != max(assignment_epochs)
        or abs(plan_lease_expires_at_s - min(assignment_leases)) > 1.0e-9
    ):
        _fail("offline_regional_authority_replay_plan_authority_mismatch")
    owner_ids = {key[2] for key in groups}
    plan_owner_node_id = str(metadata.get("owner_node_id", "")).strip()
    if len(owner_ids) == 1 and plan_owner_node_id != next(iter(owner_ids)):
        _fail("offline_regional_authority_replay_plan_owner_mismatch")
    if metadata.get("current_plan_owner_node_id") != plan_owner_node_id:
        _fail("offline_regional_authority_replay_plan_owner_mismatch")

    grants = tuple(
        RegionalAuthorityGrant(
            region_id=region_id,
            owner_layer=owner_layer,
            owner_node_id=owner_node_id,
            owner_role=f"{owner_layer}_owner",
            epoch=epoch,
            source_plan_id=previous.plan_id,
            source_plan_version=previous.version,
            lease_expires_at_s=lease_expires_at_s,
            target_ids=tuple(group["target_ids"]),
            assigned_resource_ids_by_target=dict(group["assignment_map"]),
            coalition_commits=tuple(group["commits"]),
            decision_reason="offline_recorded_authority_replay",
        )
        for (
            region_id,
            owner_layer,
            owner_node_id,
            epoch,
            lease_expires_at_s,
        ), group in sorted(groups.items())
    )
    return RegionalAuthorityInput(
        adjudicated_at_s=activation_at_s,
        grants=grants,
    )


def _replay_recorded_coalition_identity(
    plan: AssignmentPlan,
    *,
    evidence: PlanningFrameEvidence,
) -> AssignmentPlan:
    """Restore hash-bound anonymous coalition IDs without changing a solve.

    Planning-frame anonymization assigns coalition tokens across the recorded
    current and previous plans.  A coalition first created during replay sees
    only the anonymous target ID, so the planner's deterministic local naming
    rule cannot reproduce that token.  The recorded rule plan is already part
    of the validated frame file; use its target-to-coalition namespace only
    after proving that all other coalition references remain internally
    consistent.
    """

    recorded = evidence.plan
    if recorded is None:
        _fail("offline_recorded_coalition_identity_plan_missing")
    recorded_plan_sha256 = canonical_runtime_payload_sha256(recorded)
    validated_assignment_plan_payload_sha256(plan)

    replayed_by_target = _validated_coalition_replay_inventory(
        plan,
        context="replayed",
    )
    recorded_by_target = _validated_coalition_replay_inventory(
        recorded,
        context="recorded",
    )
    if set(replayed_by_target) != set(recorded_by_target):
        _fail(
            "offline_recorded_coalition_identity_inventory_mismatch",
            "replayed and recorded target coalition inventories differ",
        )

    previous_by_target: dict[str, CoalitionPlan] = {}
    if evidence.previous_plan is not None:
        previous_by_target = _validated_coalition_replay_inventory(
            evidence.previous_plan,
            context="previous",
        )

    desired_id_by_target: dict[str, str] = {}
    restored_target_ids: list[str] = []
    for target_id in sorted(replayed_by_target):
        replayed_coalition = replayed_by_target[target_id]
        recorded_coalition = recorded_by_target[target_id]
        previous_coalition = previous_by_target.get(target_id)
        if previous_coalition is not None:
            if recorded_coalition.coalition_id != previous_coalition.coalition_id:
                _fail(
                    "offline_recorded_coalition_identity_previous_rewrite",
                    f"recorded coalition identity changed for {target_id}",
                )
            if replayed_coalition.coalition_id != previous_coalition.coalition_id:
                _fail(
                    "offline_recorded_coalition_identity_replay_discontinuity",
                    f"replayed coalition identity changed for {target_id}",
                )
        desired_id_by_target[target_id] = recorded_coalition.coalition_id
        if replayed_coalition.coalition_id != recorded_coalition.coalition_id:
            restored_target_ids.append(target_id)

    if restored_target_ids and evidence.planning_path in {
        "regional_authority",
        "authority_identity_publish",
    }:
        _fail(
            "offline_recorded_coalition_identity_authority_conflict",
            "authority replay must already carry its recorded coalition identity",
        )

    coalition_id_map = {
        replayed_by_target[target_id].coalition_id: desired_id
        for target_id, desired_id in desired_id_by_target.items()
    }
    if len(set(coalition_id_map.values())) != len(coalition_id_map):
        _fail(
            "offline_recorded_coalition_identity_duplicate",
            "recorded coalition identity is not one-to-one",
        )

    coalitions = tuple(
        replace(
            coalition,
            coalition_id=desired_id_by_target[coalition.target_id],
            metadata=_replace_coalition_identity_values(
                coalition.metadata,
                coalition_id_map,
            ),
        )
        for coalition in plan.coalitions
    )
    assignments = tuple(
        _restore_assignment_coalition_identity(
            assignment,
            replayed_by_target=replayed_by_target,
            desired_id_by_target=desired_id_by_target,
            coalition_id_map=coalition_id_map,
        )
        for assignment in plan.assignments
    )
    demand_summaries = tuple(
        _restore_summary_coalition_identity(
            summary,
            replayed_by_target=replayed_by_target,
            desired_id_by_target=desired_id_by_target,
        )
        for summary in plan.demand_summaries
    )
    identity_map = tuple(
        (
            target_id,
            replayed_by_target[target_id].coalition_id,
            desired_id_by_target[target_id],
        )
        for target_id in sorted(desired_id_by_target)
    )
    restored = replace(
        plan,
        assignments=assignments,
        coalitions=coalitions,
        demand_summaries=demand_summaries,
        metadata={
            **dict(
                _replace_coalition_identity_values(
                    plan.metadata,
                    coalition_id_map,
                )
            ),
            "offline_recorded_coalition_identity_schema": (
                OFFLINE_RECORDED_COALITION_IDENTITY_SCHEMA_V1
            ),
            "offline_recorded_coalition_identity_applied": bool(
                restored_target_ids
            ),
            "offline_recorded_coalition_identity_restored_target_ids": tuple(
                restored_target_ids
            ),
            "offline_recorded_coalition_identity_map_sha256": (
                canonical_runtime_payload_sha256(identity_map)
            ),
            "offline_recorded_coalition_identity_source_plan_sha256": (
                recorded_plan_sha256
            ),
            "offline_recorded_coalition_identity_publish_allowed": False,
            "offline_recorded_coalition_identity_runtime_ack": False,
            "offline_recorded_coalition_identity_authority": False,
        },
    )
    _validated_coalition_replay_inventory(restored, context="restored")
    validated_assignment_plan_payload_sha256(restored)
    return restored


def _validated_coalition_replay_inventory(
    plan: AssignmentPlan,
    *,
    context: str,
) -> dict[str, CoalitionPlan]:
    """Validate target, assignment, summary, and metadata coalition references."""

    by_target: dict[str, CoalitionPlan] = {}
    by_id: dict[str, CoalitionPlan] = {}
    for coalition in plan.coalitions:
        target_id = str(coalition.target_id).strip()
        coalition_id = str(coalition.coalition_id).strip()
        if (
            not target_id
            or target_id != coalition.target_id
            or not coalition_id
            or coalition_id != coalition.coalition_id
        ):
            _fail(
                "offline_recorded_coalition_identity_invalid",
                f"{context} coalition identity is empty or non-canonical",
            )
        if target_id in by_target or coalition_id in by_id:
            _fail(
                "offline_recorded_coalition_identity_duplicate",
                f"{context} coalition identity is not unique",
            )
        by_target[target_id] = coalition
        by_id[coalition_id] = coalition

    assignments_by_target: dict[str, list[Assignment]] = {}
    for assignment in plan.assignments:
        assignments_by_target.setdefault(assignment.target_id, []).append(
            assignment
        )
        coalition = by_target.get(assignment.target_id)
        if (
            coalition is None
            or assignment.coalition_id != coalition.coalition_id
            or assignment.coalition_version != coalition.version
        ):
            _fail(
                "offline_recorded_coalition_identity_assignment_mismatch",
                f"{context} assignment does not reference its target coalition",
            )
        if context != "recorded":
            member_by_resource = {
                member.resource_id: member for member in coalition.members
            }
            member = member_by_resource.get(assignment.resource_id)
            if (
                member is None
                or not member.executable
                or member.member_role != assignment.member_role
                or member.wave_id != assignment.wave_id
            ):
                _fail(
                    "offline_recorded_coalition_identity_assignment_mismatch",
                    f"{context} assignment does not match coalition membership",
                )

    summaries_by_target: dict[str, DemandSatisfactionSummary] = {}
    for summary in plan.demand_summaries:
        if summary.target_id in summaries_by_target:
            _fail(
                "offline_recorded_coalition_identity_summary_duplicate",
                f"{context} demand summary target is duplicated",
            )
        summaries_by_target[summary.target_id] = summary
        coalition = by_target.get(summary.target_id)
        if coalition is None:
            if (
                summary.coalition_id is not None
                or summary.coalition_version is not None
            ):
                _fail(
                    "offline_recorded_coalition_identity_summary_mismatch",
                    f"{context} demand summary references a missing coalition",
                )
            continue
        if not _summary_matches_coalition(summary, coalition):
            _fail(
                "offline_recorded_coalition_identity_summary_mismatch",
                f"{context} demand summary does not match its coalition",
            )

    for target_id, coalition in by_target.items():
        if target_id not in summaries_by_target:
            _fail(
                "offline_recorded_coalition_identity_summary_missing",
                f"{context} coalition has no demand summary",
            )
        assignments = assignments_by_target.get(target_id, ())
        assignment_resources = {item.resource_id for item in assignments}
        executable_members = {
            member.resource_id
            for member in coalition.members
            if member.executable
        }
        if context == "recorded":
            continue
        if coalition.complete:
            if (
                assignment_resources != executable_members
                or len(assignments) != coalition.assigned_resource_count
            ):
                _fail(
                    "offline_recorded_coalition_identity_membership_mismatch",
                    f"{context} complete coalition bindings are inconsistent",
                )
        elif assignments:
            _fail(
                "offline_recorded_coalition_identity_membership_mismatch",
                f"{context} incomplete coalition has executable assignments",
            )

    _validate_coalition_identity_metadata(
        plan.metadata,
        by_target=by_target,
        summaries_by_target=summaries_by_target,
        context=context,
    )
    return by_target


def _summary_matches_coalition(
    summary: DemandSatisfactionSummary,
    coalition: CoalitionPlan,
) -> bool:
    return (
        summary.target_id == coalition.target_id
        and summary.demand_required == coalition.required_resource_count
        and summary.demand_assigned == coalition.assigned_resource_count
        and summary.demand_shortfall == coalition.shortfall
        and summary.coalition_complete == coalition.complete
        and summary.coalition_id == coalition.coalition_id
        and summary.coalition_version == coalition.version
        and summary.primary_resource_count == coalition.primary_resource_count
    )


def _restore_assignment_coalition_identity(
    assignment: Assignment,
    *,
    replayed_by_target: Mapping[str, CoalitionPlan],
    desired_id_by_target: Mapping[str, str],
    coalition_id_map: Mapping[str, str],
) -> Assignment:
    coalition = replayed_by_target.get(assignment.target_id)
    if (
        coalition is None
        or assignment.coalition_id != coalition.coalition_id
        or assignment.coalition_version != coalition.version
    ):
        _fail(
            "offline_recorded_coalition_identity_assignment_mismatch",
            "replayed assignment coalition reference changed before restoration",
        )
    return replace(
        assignment,
        coalition_id=desired_id_by_target[assignment.target_id],
        metadata=_replace_coalition_identity_values(
            assignment.metadata,
            coalition_id_map,
        ),
    )


def _restore_summary_coalition_identity(
    summary: DemandSatisfactionSummary,
    *,
    replayed_by_target: Mapping[str, CoalitionPlan],
    desired_id_by_target: Mapping[str, str],
) -> DemandSatisfactionSummary:
    coalition = replayed_by_target.get(summary.target_id)
    if coalition is None:
        if (
            summary.coalition_id is not None
            or summary.coalition_version is not None
        ):
            _fail(
                "offline_recorded_coalition_identity_summary_mismatch",
                "replayed summary references a missing coalition",
            )
        return summary
    if (
        summary.coalition_id != coalition.coalition_id
        or summary.coalition_version != coalition.version
    ):
        _fail(
            "offline_recorded_coalition_identity_summary_mismatch",
            "replayed summary coalition reference changed before restoration",
        )
    return replace(
        summary,
        coalition_id=desired_id_by_target[summary.target_id],
    )


def _replace_coalition_identity_values(
    value: Any,
    coalition_id_map: Mapping[str, str],
) -> Any:
    """Replace only exact coalition-ID values in detached replay metadata."""

    if isinstance(value, Mapping):
        return {
            str(key): _replace_coalition_identity_values(item, coalition_id_map)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(
            _replace_coalition_identity_values(item, coalition_id_map)
            for item in value
        )
    if isinstance(value, list):
        return [
            _replace_coalition_identity_values(item, coalition_id_map)
            for item in value
        ]
    if isinstance(value, str):
        return coalition_id_map.get(value, value)
    return value


def _validate_coalition_identity_metadata(
    metadata: Mapping[str, Any],
    *,
    by_target: Mapping[str, CoalitionPlan],
    summaries_by_target: Mapping[str, DemandSatisfactionSummary],
    context: str,
) -> None:
    raw_summaries = metadata.get("demand_summaries")
    if raw_summaries is not None:
        rows = _coalition_metadata_rows(
            raw_summaries,
            context=f"{context} demand_summaries",
        )
        if set(rows) != set(summaries_by_target):
            _fail(
                "offline_recorded_coalition_identity_metadata_mismatch",
                f"{context} demand summary metadata inventory differs",
            )
        for target_id, row in rows.items():
            summary = summaries_by_target[target_id]
            expected = {
                "target_id": summary.target_id,
                "demand_required": summary.demand_required,
                "demand_assigned": summary.demand_assigned,
                "demand_shortfall": summary.demand_shortfall,
                "coalition_complete": summary.coalition_complete,
                "coalition_id": summary.coalition_id,
                "coalition_version": summary.coalition_version,
                "primary_resource_count": summary.primary_resource_count,
            }
            if any(row.get(key) != value for key, value in expected.items()):
                _fail(
                    "offline_recorded_coalition_identity_metadata_mismatch",
                    f"{context} demand summary metadata differs",
                )

    raw_membership = metadata.get("coalition_membership")
    if raw_membership is not None:
        rows = _coalition_metadata_rows(
            raw_membership,
            context=f"{context} coalition_membership",
        )
        if set(rows) != set(by_target):
            _fail(
                "offline_recorded_coalition_identity_metadata_mismatch",
                f"{context} coalition membership metadata inventory differs",
            )
        for target_id, row in rows.items():
            coalition = by_target[target_id]
            if (
                row.get("target_id") != target_id
                or row.get("coalition_id") != coalition.coalition_id
                or row.get("coalition_version") != coalition.version
                or row.get("coalition_epoch") != coalition.epoch
            ):
                _fail(
                    "offline_recorded_coalition_identity_metadata_mismatch",
                    f"{context} coalition membership metadata differs",
                )


def _coalition_metadata_rows(
    value: Any,
    *,
    context: str,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, (tuple, list)):
        _fail(
            "offline_recorded_coalition_identity_metadata_mismatch",
            f"{context} is not a sequence",
        )
    rows: dict[str, Mapping[str, Any]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            _fail(
                "offline_recorded_coalition_identity_metadata_mismatch",
                f"{context} contains a non-mapping row",
            )
        target_id = item.get("target_id")
        if not isinstance(target_id, str) or not target_id.strip():
            _fail(
                "offline_recorded_coalition_identity_metadata_mismatch",
                f"{context} contains an invalid target id",
            )
        if target_id in rows:
            _fail(
                "offline_recorded_coalition_identity_metadata_mismatch",
                f"{context} contains a duplicate target id",
            )
        rows[target_id] = item
    return rows


def _replay_recorded_regional_authority_identity(
    plan: AssignmentPlan,
    *,
    evidence: PlanningFrameEvidence,
) -> AssignmentPlan:
    """Project a validated online regional replay onto its recorded identity."""

    recorded = evidence.plan
    previous = evidence.previous_plan
    if recorded is None or previous is None:
        _fail("offline_regional_authority_replay_evidence_incomplete")
    _recorded_regional_authority_input(evidence)
    validated_assignment_plan_payload_sha256(plan)
    if (
        _binding_signature(plan) != _binding_signature(recorded)
        or plan.assignment_signature() != recorded.assignment_signature()
        or plan.unassigned_target_ids != recorded.unassigned_target_ids
        or plan.incomplete_target_ids != recorded.incomplete_target_ids
        or plan.demand_summaries != recorded.demand_summaries
        or plan.version != recorded.version
        or plan.previous_plan_id != previous.plan_id
        or plan.window_id != recorded.window_id
        or plan.decision_state != recorded.decision_state
        or plan.changed != recorded.changed
        or plan.resource_count != recorded.resource_count
        or plan.target_count != recorded.target_count
        or abs(float(plan.created_at) - float(recorded.created_at)) > 1.0e-9
    ):
        _fail("offline_regional_authority_replay_solver_semantics_mismatch")

    projected_metadata = dict(plan.metadata)
    for key in _REGIONAL_PLAN_EXECUTION_METADATA_KEYS:
        projected_metadata.pop(key, None)
    projected_metadata.update(
        {
            key: value
            for key, value in recorded.metadata.items()
            if key in _REGIONAL_PLAN_EXECUTION_METADATA_KEYS
        }
    )
    replayed = replace(
        plan,
        source_node_id=recorded.source_node_id,
        target_node_id=recorded.target_node_id,
        link_type=recorded.link_type,
        metadata={
            **projected_metadata,
            "offline_regional_authority_identity_replayed": True,
            "offline_regional_authority_transition_sha256": (
                evidence.recorded_authority_transition_sha256
            ),
            "offline_regional_authority_production_ack": False,
        },
    )
    validated_assignment_plan_payload_sha256(replayed)
    if not _control_plan_replay_matches(replayed, recorded):
        _fail("offline_regional_authority_replay_execution_signature_mismatch")
    return replayed


def _replay_recorded_authority_identity(
    plan: AssignmentPlan,
    *,
    evidence: PlanningFrameEvidence,
) -> AssignmentPlan:
    """Reapply a recorded D3 authority transform after deterministic solving."""

    if evidence.planning_path == "regional_authority":
        return _replay_recorded_regional_authority_identity(
            plan,
            evidence=evidence,
        )
    if evidence.planning_path != "authority_identity_publish":
        return plan
    recorded = evidence.plan
    previous = evidence.previous_plan
    if recorded is None or previous is None or evidence.timestamp_s is None:
        _fail("offline_authority_replay_evidence_incomplete")
    validated_assignment_plan_payload_sha256(recorded)
    metadata = dict(recorded.metadata)
    if metadata.get("active_plan_owner") != "secondary":
        _fail("offline_authority_replay_owner_unsupported")
    if metadata.get("secondary_takeover_state") != "secondary_plan_active":
        _fail("offline_authority_replay_state_invalid")
    if metadata.get("secondary_plan_executable") is not True:
        _fail("offline_authority_replay_not_executable")

    owner_node_id = str(
        metadata.get("owner_node_id") or recorded.source_node_id or ""
    ).strip()
    link_type = str(recorded.link_type or "").strip()
    try:
        activated_at_s = float(metadata["secondary_activated_at_s"])
        lease_expires_at_s = float(metadata["secondary_lease_expires_at_s"])
        leader_epoch = int(metadata["secondary_leader_epoch"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail("offline_authority_replay_contract_invalid", str(exc))
    if (
        not owner_node_id
        or not link_type
        or not isfinite(activated_at_s)
        or not isfinite(lease_expires_at_s)
        or leader_epoch <= 0
    ):
        _fail("offline_authority_replay_contract_invalid")

    previous_owner = str(
        previous.metadata.get("active_plan_owner", "center")
    ).strip()
    if previous_owner == "secondary":
        replayed = continue_active_secondary_plan(
            plan,
            previous_plan=previous,
            readiness_class="takeover_ready",
            readiness_sustained=True,
            published_at_s=float(evidence.timestamp_s),
            lease_expires_at_s=lease_expires_at_s,
            leader_epoch=leader_epoch,
        )
    else:
        replayed = prepare_secondary_takeover_plan(
            plan,
            supersedes_plan=previous,
            secondary_node_id=owner_node_id,
            readiness_class="takeover_ready",
            readiness_sustained=True,
            activated_at_s=activated_at_s,
            lease_expires_at_s=lease_expires_at_s,
            leader_epoch=leader_epoch,
            target_node_id=recorded.target_node_id,
            link_type=link_type,
        )
    replayed = replace(
        replayed,
        metadata={
            **dict(replayed.metadata),
            "offline_authority_identity_replayed": True,
            "offline_authority_identity_source_path": evidence.planning_path,
            "offline_authority_identity_production_ack": False,
        },
    )
    validated_assignment_plan_payload_sha256(replayed)
    return replayed


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
        output_plan_payload_sha256=(
            validated_assignment_plan_payload_sha256(raw.plan)
        ),
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
    if evidence.planning_path == "regional_authority":
        if evidence.plan is None or evidence.previous_plan is None:
            _fail("offline_regional_authority_replay_evidence_incomplete")
        try:
            expected_transition_sha256 = (
                canonical_recorded_authority_transition_sha256(
                    planning_path=evidence.planning_path,
                    selection_source=evidence.selection_source,
                    timestamp_s=float(evidence.timestamp_s),
                    plan=evidence.plan,
                    previous_plan=evidence.previous_plan,
                )
            )
        except Exception as exc:
            _fail("offline_regional_authority_replay_payload_invalid", str(exc))
        if (
            evidence.recorded_authority_transition_sha256
            != expected_transition_sha256
        ):
            _fail("offline_regional_authority_replay_transition_sha256_mismatch")
    elif evidence.recorded_authority_transition_sha256 is not None:
        _fail("offline_recorded_authority_transition_unexpected")


def _validate_single_frame_rule_source_contract(
    evidence: PlanningFrameEvidence,
) -> None:
    """Validate the frozen rule frame before isolated dual-arm replay."""

    previous = evidence.previous_plan
    plan = evidence.plan
    rule_result = evidence.rule_matrix_result
    if previous is None:
        _fail("single_frame_replay_previous_plan_missing")
    if plan is None or rule_result is None:
        _fail("single_frame_replay_source_plan_missing")
    if evidence.previous_plan_version != previous.version:
        _fail("single_frame_replay_previous_plan_version_mismatch")
    if evidence.plan_id != plan.plan_id or evidence.plan_version != plan.version:
        _fail("single_frame_replay_source_plan_identity_mismatch")
    if plan.version == previous.version:
        if plan.plan_id != previous.plan_id:
            _fail("single_frame_replay_stale_plan_version")
    elif plan.version == previous.version + 1:
        if plan.previous_plan_id != previous.plan_id:
            _fail("single_frame_replay_stale_plan_version")
    else:
        _fail("single_frame_replay_stale_plan_version")

    timestamp_s = float(evidence.timestamp_s)
    if timestamp_s < float(previous.created_at):
        _fail("single_frame_replay_stale_previous_plan")
    if previous.stale_after_s is not None:
        freshness_base_s = max(
            float(previous.created_at),
            float(previous.last_changed_at),
        )
        if timestamp_s > freshness_base_s + float(previous.stale_after_s):
            _fail("single_frame_replay_stale_previous_plan")

    track_ids = tuple(item.track_id for item in evidence.tracks)
    resource_ids = tuple(item.resource_id for item in evidence.resources)
    if (
        len(track_ids) != len(set(track_ids))
        or track_ids != tuple(rule_result.target_ids)
    ):
        _fail("single_frame_replay_global_track_id_snapshot_mismatch")
    if (
        len(resource_ids) != len(set(resource_ids))
        or resource_ids != tuple(rule_result.resource_ids)
    ):
        _fail("single_frame_replay_resource_id_snapshot_mismatch")


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


def _single_frame_replay_payload(
    value: IsolatedLearningInterventionFrameReplay,
) -> dict[str, Any]:
    return _single_frame_replay_payload_from_values(
        sequence_index=value.sequence_index,
        input_snapshot_sha256=value.input_snapshot_sha256,
        expected_bundle_manifest_sha256=(
            value.expected_bundle_manifest_sha256
        ),
        actual_bundle_manifest_sha256=value.actual_bundle_manifest_sha256,
        expected_policy_version=value.expected_policy_version,
        actual_policy_version=value.actual_policy_version,
        bundle_state_dict_sha256=value.bundle_state_dict_sha256,
        bundle_loaded=value.bundle_loaded,
        bundle_fallback_reason=value.bundle_fallback_reason,
        rule_frame=value.rule_frame,
        treatment_frame=value.treatment_frame,
        eligibility=value.eligibility,
    )


def _single_frame_replay_payload_from_values(
    *,
    sequence_index: int,
    input_snapshot_sha256: str,
    expected_bundle_manifest_sha256: str,
    actual_bundle_manifest_sha256: str | None,
    expected_policy_version: str,
    actual_policy_version: str | None,
    bundle_state_dict_sha256: str | None,
    bundle_loaded: bool,
    bundle_fallback_reason: str | None,
    rule_frame: PlanningFrameEvidence,
    treatment_frame: PlanningFrameEvidence,
    eligibility: "LearningInterventionFrameEvidence",
) -> dict[str, Any]:
    return {
        "schema_version": (
            ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCHEMA_V1
        ),
        "replay_scope": ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCOPE,
        "sequence_index": int(sequence_index),
        "input_snapshot_sha256": input_snapshot_sha256,
        "bundle": {
            "expected_manifest_sha256": expected_bundle_manifest_sha256,
            "actual_manifest_sha256": actual_bundle_manifest_sha256,
            "expected_policy_version": expected_policy_version,
            "actual_policy_version": actual_policy_version,
            "state_dict_sha256": bundle_state_dict_sha256,
            "loaded": bool(bundle_loaded),
            "fallback_reason": bundle_fallback_reason,
        },
        "execution_boundary": {
            "isolated_simulation": True,
            "publish_allowed": False,
            "runtime_ack_available": False,
            "authority_available": False,
            "global_track_id_rewrite_count": 0,
        },
        "rule_frame": _jsonable(rule_frame),
        "treatment_frame": _jsonable(treatment_frame),
        "eligibility": eligibility.to_dict(),
    }


def _single_frame_sequence_index(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        _fail("single_frame_replay_sequence_index_invalid")
    result = int(value)
    if result < 0:
        _fail("single_frame_replay_sequence_index_invalid")
    return result


def _single_frame_required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("single_frame_replay_text_invalid", context)
    return value.strip()


def _single_frame_sha256(value: Any, context: str) -> str:
    text = _single_frame_required_text(value, context)
    if (
        len(text) != 64
        or any(character not in "0123456789abcdef" for character in text)
        or len(set(text)) == 1
    ):
        _fail("single_frame_replay_sha256_invalid", context)
    return text


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
    "ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCHEMA_V1",
    "ISOLATED_LEARNING_INTERVENTION_FRAME_REPLAY_SCOPE",
    "OFFLINE_PAIRED_INTERVENTION_EXECUTION_SCHEMA_V1",
    "OFFLINE_PAIRED_INTERVENTION_REPORT_KIND_V1",
    "IsolatedLearningInterventionFrameReplay",
    "OfflineInterventionArmExecution",
    "OfflinePairedInterventionExecution",
    "canonical_isolated_learning_intervention_frame_replay_sha256",
    "canonical_learning_action_mask_sha256",
    "canonical_planning_frame_snapshot_sha256",
    "canonical_rule_cost_matrix_sha256",
    "execute_offline_paired_intervention",
    "replay_isolated_learning_intervention_frame",
    "write_offline_paired_intervention_execution",
]
