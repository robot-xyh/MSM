from __future__ import annotations

from dataclasses import replace
import json

import numpy as np
import pytest

from commitment_test_support import committed_target_track
from d3_assignment_planner import (
    ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
    A1InterventionContractError,
    AssignmentPlanRuntimeAckEvidence,
    AssignmentPlanner,
    CostMatrixResult,
    CostWeights,
    D3RuntimeLearningEvidence,
    D4RegionalHintRuntimeEvidence,
    EvidenceAvailability,
    FORMAL_REWARD_COMPONENT_NAMES,
    LearningAssistConfig,
    LearningCostAssistant,
    PlannerConfig,
    ResidualPrediction,
    ResourceState,
    RuntimePlanBindingAck,
    RuntimePlanWindowReference,
    RuntimePlanWindowRewardEvidence,
    TargetDemand,
    assemble_a1_intervention_lifecycle,
    build_a1_intervention_preregistration,
    build_a1_plan_publication_evidence,
    canonical_runtime_payload_sha256,
    evaluate_a1_intervention_candidate,
    select_a1_intervention_candidate,
    validate_a1_intervention_candidate_evidence,
    validate_a1_intervention_lifecycle_evidence,
    validate_a1_intervention_selection_decision,
)
from d3_assignment_planner.learning import EDGE_FEATURE_NAMES


_D6_SOURCE_NAMES = (
    "online_observations",
    "d2_identity_evaluation",
    "d2_identity_manifest",
    "d2_online_d1_records",
    "d2_online_d2_records",
    "d2_observation_truth_labels",
    "d2_identity_evidence",
    "offline_truth_state",
    "offline_proximity_intercepts",
    "episode_manifest",
    "scenario_config",
)


class _FixedMToNCostModel:
    weights = CostWeights()

    def build_matrix(
        self,
        tracks,
        resources,
        timestamp,
        *,
        preserved_candidate_edges=None,
    ) -> CostMatrixResult:
        del timestamp, preserved_candidate_edges
        matrix = np.asarray(
            (
                (0.1, 0.2, 0.4),
                (0.4, 0.3, 0.1),
            ),
            dtype=float,
        )
        return CostMatrixResult(
            matrix=matrix,
            breakdowns=tuple(
                tuple(
                    {
                        "rule_total": float(matrix[row, column]),
                        "total": float(matrix[row, column]),
                    }
                    for column in range(matrix.shape[1])
                )
                for row in range(matrix.shape[0])
            ),
            target_ids=tuple(item.track_id for item in tracks),
            resource_ids=tuple(item.resource_id for item in resources),
            unassigned_costs=np.asarray((10.0, 10.0), dtype=float),
            target_threat_scores=(0.9, 0.5),
            reject_reasons=(
                (None, None, None),
                (None, None, None),
            ),
            candidate_mask=np.ones((2, 3), dtype=bool),
        )


class _BindingChangingPredictor:
    def predict(self, features: np.ndarray) -> ResidualPrediction:
        assert features.shape[0] == 6
        return ResidualPrediction(
            delta_costs=np.asarray(
                (10.0, -10.0, -10.0, -10.0, 10.0, 10.0),
                dtype=float,
            ),
            confidence=1.0,
        )


class _NonSelectedEdgePredictor:
    def predict(self, features: np.ndarray) -> ResidualPrediction:
        previous_index = EDGE_FEATURE_NAMES.index("previous_binding")
        previous = features[:, previous_index] > 0.5
        return ResidualPrediction(
            delta_costs=np.where(previous, 0.0, 0.1),
            confidence=1.0,
        )


def _frames(
    *,
    timestamp_s: float = 1.0,
    predictor=None,
):
    tracks = (
        committed_target_track(
            "global-track-a",
            0.9,
            0.1,
            0.0,
            demand=TargetDemand(
                required_resource_count=2,
                primary_resource_count=2,
            ),
        ),
        committed_target_track("global-track-b", 0.5, 0.1, 0.0),
    )
    resources = tuple(ResourceState(f"resource-{index}") for index in range(3))
    config = PlannerConfig(
        enable_hysteresis=False,
        solver_name="hungarian_demand_slots",
    )
    control = AssignmentPlanner(
        cost_model=_FixedMToNCostModel(),
        config=config,
    )
    previous = control.plan(tracks, resources, timestamp=0.0)
    control.plan(
        tracks,
        resources,
        timestamp=timestamp_s,
        previous_plan=previous,
        expected_previous_version=previous.version,
        forced_replan=True,
        publish=False,
    )

    treatment = AssignmentPlanner(
        cost_model=_FixedMToNCostModel(),
        config=config,
        learning_assistant=LearningCostAssistant(
            predictor or _BindingChangingPredictor(),
            config=LearningAssistConfig(
                mode="assist",
                alpha=1.0,
                timeout_s=1.0,
                min_confidence=0.0,
            ),
        ),
    )
    treatment.publish_plan(previous)
    treatment.plan(
        tracks,
        resources,
        timestamp=timestamp_s,
        previous_plan=previous,
        expected_previous_version=previous.version,
        forced_replan=True,
        publish=False,
    )
    return control.latest_planning_evidence, treatment.latest_planning_evidence


def _registration(*, max_binding_change_count: int = 3):
    return build_a1_intervention_preregistration(
        experiment_id="a1-common-checkpoint",
        experiment_version="v1",
        policy_artifact_sha256="1" * 64,
        evaluation_seeds=(1000, 1001),
        sequence_index_min=0,
        sequence_index_max=20,
        timestamp_s_min=0.0,
        timestamp_s_max=20.0,
        max_abs_cost_correction=1.1,
        max_rule_cost_difference=0.7,
        max_relative_rule_cost_difference=2.0,
        max_binding_change_count=max_binding_change_count,
        high_threat_threshold=0.7,
    )


def _candidate(
    *,
    seed: int = 1000,
    sequence_index: int = 4,
    timestamp_s: float = 1.0,
    predictor=None,
):
    rule, treatment = _frames(
        timestamp_s=timestamp_s,
        predictor=predictor,
    )
    evidence = evaluate_a1_intervention_candidate(
        preregistration=_registration(),
        seed=seed,
        sequence_index=sequence_index,
        rule_frame=rule,
        treatment_frame=treatment,
    )
    return evidence, rule, treatment


def _runtime_plan_payload(plan, timestamp_s: float) -> dict[str, object]:
    return {
        "timestamp": timestamp_s,
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "created_at": plan.created_at,
        "assignment_count": len(plan.assignments),
        "target_count": plan.target_count,
        "resource_count": plan.resource_count,
        "assignments": [
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
                "regional_region_id": item.metadata.get(
                    "regional_region_id"
                ),
                "regional_epoch": item.metadata.get("regional_epoch"),
                "regional_commit_mode": item.metadata.get(
                    "regional_commit_mode"
                ),
            }
            for item in plan.assignments
        ],
        "unassigned_global_track_ids": list(plan.unassigned_target_ids),
        "solver_name": plan.solver_name,
        "metadata": dict(plan.metadata),
    }


def _publication(plan, *, timestamp_s: float = 2.0):
    payload = _runtime_plan_payload(plan, timestamp_s)
    envelope = {
        "sequence": 11,
        "topic": "modules.d3.assignment_plan",
        "source": "D3",
        "timestamp": timestamp_s,
        "schema_version": plan.plan_schema,
        "payload": payload,
    }
    return build_a1_plan_publication_evidence(
        expected_plan=plan,
        source_publication=envelope,
    )


def _runtime_ack(plan, publication):
    binding_acks = tuple(
        RuntimePlanBindingAck(
            resource_id=item.resource_id,
            global_track_id=item.target_id,
            coalition_id=item.coalition_id,
            coalition_version=item.coalition_version,
            member_role=item.member_role,
            guidance_command_present=True,
            guidance_mode="midcourse_pn_3d",
            guidance_gate_reason="midcourse_position_guidance",
            control_applied_to_world=True,
            held=False,
        )
        for item in plan.assignments
    )
    return AssignmentPlanRuntimeAckEvidence(
        ack_envelope_schema=ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
        decision_id=f"{plan.plan_id}:v{plan.version}",
        ack_timestamp=publication.source_timestamp_s,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        plan_created_at=plan.created_at,
        plan_schema_version=plan.plan_schema,
        source_plan_bus_sequence=publication.source_bus_sequence,
        source_plan_payload_sha256=publication.runtime_plan_payload_sha256,
        source_guidance_bus_sequence=publication.source_bus_sequence + 1,
        source_guidance_payload_sha256="2" * 64,
        accepted=True,
        status_code="accepted_by_main_runtime",
        assignment_count=len(plan.assignments),
        binding_ack_count=len(plan.assignments),
        fully_bound_to_guidance=True,
        control_applied_binding_count=len(plan.assignments),
        held_binding_count=0,
        active_plan_owner="center",
        owner_node_id="C2",
        authority_epoch=1,
        lease_expires_at_s=10.0,
        d3_learning_evidence=D3RuntimeLearningEvidence(
            mode="assist",
            applied=True,
            shadow_only=False,
            bundle_loaded=True,
            fallback_reason=None,
            model_fingerprint="sha256:a1-test-policy",
            runtime_applied_ack_available=True,
        ),
        d4_regional_hint_evidence=D4RegionalHintRuntimeEvidence(
            considered=False,
            applied=False,
            rejected=False,
            fallback_reason=None,
            advisory_id=None,
            advisory_version=None,
            source_plan_id=None,
            source_plan_version=None,
        ),
        binding_acks=binding_acks,
        physical_outcome_available=False,
        reward_available=False,
    )


def _available(
    name: str,
    kind: str,
    value,
    digest: str,
) -> EvidenceAvailability:
    return EvidenceAvailability(
        name=name,
        evidence_kind=kind,
        available=True,
        value=value,
        reason=None,
        provenance_sha256=digest,
    )


def _unavailable(
    name: str,
    kind: str,
    reason: str,
    digest: str,
) -> EvidenceAvailability:
    return EvidenceAvailability(
        name=name,
        evidence_kind=kind,
        available=False,
        value=None,
        reason=reason,
        provenance_sha256=digest,
    )


def _physical_windows(plan, publication, ack, *, paired: bool):
    digest = "4" * 64
    ack_sha = canonical_runtime_payload_sha256(ack.to_dict())
    raw_components = tuple(
        _unavailable(
            name,
            "reward_component",
            "formal_reward_not_admitted",
            digest,
        )
        for name in FORMAL_REWARD_COMPONENT_NAMES
    )
    result = []
    for index, assignment in enumerate(plan.assignments):
        reference = RuntimePlanWindowReference(
            episode_id="a1-paired-runtime-test",
            scenario_version="a1-stage-contract-v1",
            seed=1000,
            plan_id=plan.plan_id,
            plan_version=plan.version,
            active_plan_owner="center",
            owner_node_id="C2",
            authority_epoch=1,
            resource_id=assignment.resource_id,
            global_track_id=assignment.target_id,
            coalition_id=assignment.coalition_id,
            coalition_version=assignment.coalition_version,
            member_role=assignment.member_role,
            source_plan_bus_sequence=publication.source_bus_sequence,
            source_plan_payload_sha256=(
                publication.runtime_plan_payload_sha256
            ),
            consumption_bus_sequence=publication.source_bus_sequence + 1,
            consumption_payload_sha256="2" * 64,
            ack_bus_sequence=publication.source_bus_sequence + 2,
            plan_created_at=plan.created_at,
            command_timestamp=publication.source_timestamp_s,
            consumption_timestamp=publication.source_timestamp_s,
            ack_timestamp=publication.source_timestamp_s,
            occurrence_id=f"{plan.plan_id}:v{plan.version}:binding-{index}",
            occurrence_index=1,
            adoption_kind="new_plan_identity",
            execution_signature_sha256="3" * 64,
            window_start_timestamp=publication.source_timestamp_s,
            window_end_timestamp=publication.source_timestamp_s + 1.0,
            window_interval="closed",
            runtime_ack_evidence_sha256=ack_sha,
            outcome_join_payload_sha256=digest,
            source_artifact_sha256s=tuple(
                (name, canonical_runtime_payload_sha256({"name": name}))
                for name in _D6_SOURCE_NAMES
            ),
        )
        result.append(
            RuntimePlanWindowRewardEvidence(
                reference=reference,
                command=_available(
                    "assignment_command_published",
                    "command",
                    True,
                    digest,
                ),
                ack_applied=_available(
                    "binding_control_applied",
                    "ack_applied",
                    True,
                    digest,
                ),
                observed_outcomes=(
                    _available(
                        "bounded_assigned_pair_best_distance_progress",
                        "observed_outcome",
                        0.25,
                        digest,
                    ),
                    _available(
                        "assigned_pair_five_meter_event",
                        "observed_outcome",
                        False,
                        digest,
                    ),
                    _available(
                        "same_resource_other_target_five_meter_event",
                        "observed_outcome",
                        False,
                        digest,
                    ),
                ),
                paired_evidence=(
                    _available(
                        "same_seed_paired_assignment_outcome",
                        "paired",
                        True,
                        digest,
                    )
                    if paired
                    else _unavailable(
                        "same_seed_paired_assignment_outcome",
                        "paired",
                        "paired_r0_unavailable",
                        digest,
                    )
                ),
                counterfactual_evidence=_unavailable(
                    "counterfactual_assignment_outcome",
                    "counterfactual",
                    "counterfactual_unavailable",
                    digest,
                ),
                causal_evidence=_unavailable(
                    "causal_assignment_attribution",
                    "causal",
                    "causal_unavailable",
                    digest,
                ),
                raw_reward_components=raw_components,
                formal_reward=_unavailable(
                    "formal_d3_runtime_reward",
                    "formal_reward",
                    "formal_reward_unavailable",
                    digest,
                ),
            )
        )
    return tuple(result)


def test_safe_near_competition_produces_truth_free_discrete_change() -> None:
    candidate, _, treatment = _candidate()
    payload = candidate.to_dict()

    assert candidate.policy_evaluated is True
    assert candidate.cost_correction_accepted is True
    assert candidate.assignment_changed is True
    assert candidate.near_competitive is True
    assert candidate.selected_for_paired_evaluation is True
    assert candidate.eligibility.binding_change_count == 3
    assert candidate.treatment_plan_version == candidate.previous_plan_version + 1
    assert candidate.plan_published is False
    assert candidate.runtime_ack is False
    assert candidate.physical_window_available is False
    assert treatment.plan is not None
    assert candidate.eligibility.treatment_plan_payload_sha256
    serialized = json.dumps(payload, sort_keys=True, allow_nan=False).lower()
    for forbidden in (
        '"truth"',
        '"ground_truth"',
        '"actor_id"',
        '"physical_outcome"',
        '"reward"',
    ):
        assert forbidden not in serialized
    assert validate_a1_intervention_candidate_evidence(payload) == candidate


def test_selection_is_deterministic_and_picks_first_safe_change() -> None:
    first, _, _ = _candidate(sequence_index=4, timestamp_s=1.0)
    second, _, _ = _candidate(sequence_index=5, timestamp_s=2.0)
    first_decision = select_a1_intervention_candidate(
        preregistration=_registration(),
        seed=1000,
        candidates=(first, second),
    )
    second_decision = select_a1_intervention_candidate(
        preregistration=_registration(),
        seed=1000,
        candidates=(first.to_dict(), second.to_dict()),
    )

    assert first_decision == second_decision
    assert first_decision.selected is True
    assert first_decision.selected_candidate_content_sha256 == (
        first.content_sha256
    )
    assert first_decision.selected_sequence_index == 4
    assert validate_a1_intervention_selection_decision(
        first_decision.to_dict()
    ) == first_decision


def test_no_competitive_binding_change_fails_closed() -> None:
    candidate, _, _ = _candidate(predictor=_NonSelectedEdgePredictor())
    decision = select_a1_intervention_candidate(
        preregistration=_registration(),
        seed=1000,
        candidates=(candidate,),
    )

    assert candidate.policy_evaluated is True
    assert candidate.cost_correction_accepted is True
    assert candidate.assignment_changed is False
    assert candidate.selected_for_paired_evaluation is False
    assert "assignment_unchanged" in candidate.reason_codes
    assert decision.selected is False
    assert decision.reason == "no_safe_discrete_intervention"
    assert decision.plan_published is False
    assert decision.runtime_ack is False
    assert decision.physical_window_available is False


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "truth_id",
        "target_truth_id",
        "actor_truth_id",
        "resource_actor_name",
        "target_object_id",
    ),
)
def test_online_truth_metadata_is_rejected_without_becoming_selection_input(
    forbidden_key: str,
) -> None:
    rule, treatment = _frames()
    assert treatment.effective_matrix_result is not None
    contaminated = replace(
        treatment,
        effective_matrix_result=replace(
            treatment.effective_matrix_result,
            metadata={
                **dict(treatment.effective_matrix_result.metadata),
                forbidden_key: "must-not-be-read",
            },
        ),
    )

    candidate = evaluate_a1_intervention_candidate(
        preregistration=_registration(),
        seed=1000,
        sequence_index=6,
        rule_frame=rule,
        treatment_frame=contaminated,
    )

    assert candidate.policy_evaluated is False
    assert candidate.cost_correction_accepted is False
    assert candidate.selected_for_paired_evaluation is False
    assert "policy_not_evaluated" in candidate.reason_codes
    if forbidden_key == "truth_id":
        assert "safety_shell_rejected" in candidate.reason_codes


def test_capacity_conflict_is_rejected_by_existing_safety_shell() -> None:
    rule, treatment = _frames()
    assert treatment.plan is not None
    first, second, *remaining = treatment.plan.assignments
    duplicate = replace(second, resource_id=first.resource_id)
    unsafe_plan = replace(
        treatment.plan,
        assignments=(first, duplicate, *remaining),
    )
    unsafe = replace(treatment, plan=unsafe_plan)

    candidate = evaluate_a1_intervention_candidate(
        preregistration=_registration(),
        seed=1000,
        sequence_index=7,
        rule_frame=rule,
        treatment_frame=unsafe,
    )

    assert candidate.cost_correction_accepted is False
    assert candidate.selected_for_paired_evaluation is False
    assert "safety_shell_rejected" in candidate.reason_codes
    assert any(
        code.startswith("treatment_plan_")
        for code in candidate.eligibility.reason_codes
    )


def test_hard_rejected_edge_is_not_reopened_by_selector() -> None:
    rule, treatment = _frames()
    assert treatment.rule_matrix_result is not None
    assert treatment.effective_matrix_result is not None
    assert treatment.plan is not None
    selected = treatment.plan.assignments[0]
    row = treatment.rule_matrix_result.target_ids.index(selected.target_id)
    column = treatment.rule_matrix_result.resource_ids.index(
        selected.resource_id
    )
    mask = np.asarray(
        treatment.rule_matrix_result.hard_safe_candidate_mask,
        dtype=bool,
    ).copy()
    mask[row, column] = False
    rejected = replace(
        treatment,
        rule_matrix_result=replace(
            treatment.rule_matrix_result,
            candidate_mask=mask,
        ),
        effective_matrix_result=replace(
            treatment.effective_matrix_result,
            candidate_mask=mask,
        ),
    )

    candidate = evaluate_a1_intervention_candidate(
        preregistration=_registration(),
        seed=1000,
        sequence_index=8,
        rule_frame=rule,
        treatment_frame=rejected,
    )

    assert candidate.cost_correction_accepted is False
    assert candidate.selected_for_paired_evaluation is False
    assert "safety_shell_rejected" in candidate.reason_codes
    assert "treatment_plan_hard_constraint_violation" in (
        candidate.eligibility.reason_codes
    )


def test_changed_assignment_with_stale_version_is_rejected() -> None:
    rule, treatment = _frames()
    assert treatment.plan is not None
    assert treatment.previous_plan is not None
    stale_version = treatment.previous_plan.version
    stale_plan = replace(
        treatment.plan,
        plan_id=treatment.previous_plan.plan_id,
        version=stale_version,
        previous_plan_id=treatment.previous_plan.previous_plan_id,
        assignments=tuple(
            replace(item, plan_version=stale_version)
            for item in treatment.plan.assignments
        ),
    )
    stale = replace(
        treatment,
        plan=stale_plan,
        plan_id=stale_plan.plan_id,
        plan_version=stale_plan.version,
    )

    candidate = evaluate_a1_intervention_candidate(
        preregistration=_registration(),
        seed=1000,
        sequence_index=9,
        rule_frame=rule,
        treatment_frame=stale,
    )

    assert candidate.version_contract_valid is False
    assert candidate.cost_correction_accepted is False
    assert candidate.selected_for_paired_evaluation is False
    assert "version_contract_rejected" in candidate.reason_codes


def test_binding_change_limit_is_pre_registered_and_fail_closed() -> None:
    rule, treatment = _frames()
    registration = _registration(max_binding_change_count=1)

    candidate = evaluate_a1_intervention_candidate(
        preregistration=registration,
        seed=1000,
        sequence_index=10,
        rule_frame=rule,
        treatment_frame=treatment,
    )

    assert candidate.cost_correction_accepted is True
    assert candidate.assignment_changed is True
    assert candidate.near_competitive is False
    assert candidate.selected_for_paired_evaluation is False
    assert "binding_change_limit_exceeded" in candidate.reason_codes


def test_publication_and_lifecycle_keep_ack_and_physical_window_unavailable() -> None:
    candidate, _, treatment = _candidate()
    assert treatment.plan is not None
    decision = select_a1_intervention_candidate(
        preregistration=_registration(),
        seed=1000,
        candidates=(candidate,),
    )
    publication = _publication(treatment.plan)
    lifecycle = assemble_a1_intervention_lifecycle(
        selection=decision,
        selected_candidate=candidate,
        expected_plan=treatment.plan,
        publication_evidence=publication,
    )

    assert lifecycle.policy_evaluated is True
    assert lifecycle.cost_correction_accepted is True
    assert lifecycle.assignment_changed is True
    assert lifecycle.plan_published is True
    assert lifecycle.runtime_ack is False
    assert lifecycle.physical_window_available is False
    assert lifecycle.r0_pair_available is False
    assert lifecycle.status == "published_waiting_runtime_ack"
    assert validate_a1_intervention_lifecycle_evidence(
        lifecycle.to_dict()
    ) == lifecycle


def test_lifecycle_separates_ack_physical_window_and_r0_pair() -> None:
    candidate, _, treatment = _candidate()
    assert treatment.plan is not None
    decision = select_a1_intervention_candidate(
        preregistration=_registration(),
        seed=1000,
        candidates=(candidate,),
    )
    publication = _publication(treatment.plan)
    ack = _runtime_ack(treatment.plan, publication)

    acknowledged = assemble_a1_intervention_lifecycle(
        selection=decision,
        selected_candidate=candidate,
        expected_plan=treatment.plan,
        publication_evidence=publication,
        runtime_ack_evidence=ack,
    )
    assert acknowledged.runtime_ack is True
    assert acknowledged.physical_window_available is False
    assert acknowledged.r0_pair_available is False
    assert acknowledged.status == (
        "runtime_ack_waiting_complete_physical_window"
    )

    observed = assemble_a1_intervention_lifecycle(
        selection=decision,
        selected_candidate=candidate,
        expected_plan=treatment.plan,
        publication_evidence=publication,
        runtime_ack_evidence=ack,
        physical_window_evidence=_physical_windows(
            treatment.plan,
            publication,
            ack,
            paired=False,
        ),
    )
    assert observed.physical_window_available is True
    assert observed.r0_pair_available is False
    assert observed.status == "physical_window_available_waiting_r0_pair"

    paired = assemble_a1_intervention_lifecycle(
        selection=decision,
        selected_candidate=candidate,
        expected_plan=treatment.plan,
        publication_evidence=publication,
        runtime_ack_evidence=ack,
        physical_window_evidence=_physical_windows(
            treatment.plan,
            publication,
            ack,
            paired=True,
        ),
    )
    assert paired.physical_window_available is True
    assert paired.r0_pair_available is True
    assert paired.status == "r0_pair_available"


def test_stale_or_tampered_publication_is_rejected() -> None:
    candidate, _, treatment = _candidate()
    assert treatment.plan is not None
    payload = _runtime_plan_payload(treatment.plan, 2.0)
    payload["plan_version"] = treatment.plan.version - 1
    envelope = {
        "sequence": 11,
        "topic": "modules.d3.assignment_plan",
        "source": "D3",
        "timestamp": 2.0,
        "schema_version": treatment.plan.plan_schema,
        "payload": payload,
    }

    with pytest.raises(
        A1InterventionContractError,
        match="runtime_plan_payload_mismatch",
    ):
        build_a1_plan_publication_evidence(
            expected_plan=treatment.plan,
            source_publication=envelope,
        )
    assert candidate.selected_for_paired_evaluation is True


def test_serialized_evidence_rejects_missing_or_forged_stage_fields() -> None:
    candidate, _, _ = _candidate()
    missing = candidate.to_dict()
    del missing["policy_evaluated"]
    with pytest.raises(
        A1InterventionContractError,
        match="candidate_fields_mismatch",
    ):
        validate_a1_intervention_candidate_evidence(missing)

    forged = candidate.to_dict()
    forged["plan_published"] = True
    forged_without_hash = dict(forged)
    forged_without_hash.pop("content_sha256")
    forged["content_sha256"] = canonical_runtime_payload_sha256(
        forged_without_hash
    )
    with pytest.raises(
        A1InterventionContractError,
        match="candidate_cannot_claim_runtime_stage",
    ):
        validate_a1_intervention_candidate_evidence(forged)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("rule_plan_version", 3),
        ("treatment_plan_version", 1),
        ("treatment_plan_version", 3),
    ),
)
def test_serialized_candidate_rejects_forged_plan_version_lineage(
    field: str,
    replacement: int,
) -> None:
    candidate, _, _ = _candidate()
    forged = candidate.to_dict()
    forged[field] = replacement
    unhashed = dict(forged)
    unhashed.pop("content_sha256")
    forged["content_sha256"] = canonical_runtime_payload_sha256(unhashed)

    with pytest.raises(
        A1InterventionContractError,
        match="candidate_plan_version_lineage_invalid",
    ):
        validate_a1_intervention_candidate_evidence(forged)


def test_registration_rejects_duplicate_seed_inventory() -> None:
    with pytest.raises(
        A1InterventionContractError,
        match="evaluation_seed_inventory_invalid",
    ):
        build_a1_intervention_preregistration(
            experiment_id="a1-common-checkpoint",
            experiment_version="v1",
            policy_artifact_sha256="1" * 64,
            evaluation_seeds=(1000, 1000),
            sequence_index_min=0,
            sequence_index_max=20,
            timestamp_s_min=0.0,
            timestamp_s_max=20.0,
            max_abs_cost_correction=1.1,
            max_rule_cost_difference=0.7,
            max_relative_rule_cost_difference=2.0,
            max_binding_change_count=3,
        )
