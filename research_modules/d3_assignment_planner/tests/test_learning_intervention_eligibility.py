from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from commitment_test_support import committed_target_track
from d3_assignment_planner import (
    CostMatrixResult,
    CostWeights,
    LearningAssistConfig,
    LearningCostAssistant,
    LearningInterventionEligibilityError,
    PlannerConfig,
    ResidualPrediction,
    ResourceState,
    TargetDemand,
    AssignmentPlanner,
    canonical_learning_intervention_frame_evidence_sha256,
    evaluate_learning_intervention_candidate_frame,
    select_first_eligible_learning_intervention_frame,
    validate_learning_intervention_frame_evidence,
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


def _candidate_frames(*, timestamp_s: float = 1.0):
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
    rule_frame = control.latest_planning_evidence

    treatment = AssignmentPlanner(
        cost_model=_FixedMToNCostModel(),
        config=config,
        learning_assistant=LearningCostAssistant(
            _BindingChangingPredictor(),
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
    return rule_frame, treatment.latest_planning_evidence


def _evidence(sequence_index: int = 4):
    rule_frame, treatment_frame = _candidate_frames()
    return evaluate_learning_intervention_candidate_frame(
        sequence_index=sequence_index,
        rule_frame=rule_frame,
        treatment_frame=treatment_frame,
    )


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    payload["content_sha256"] = (
        canonical_learning_intervention_frame_evidence_sha256(payload)
    )
    return payload


def test_positive_m_to_n_candidate_is_truth_free_and_round_trips() -> None:
    evidence = _evidence()

    assert evidence.eligible is True
    assert evidence.reason_codes == ("eligible",)
    assert evidence.model_applied_edge_count == 6
    assert evidence.binding_change_count == 3
    assert evidence.demand_slot_count == 3
    assert evidence.m_to_n_target_count == 1
    assert evidence.rule_hard_violation_count == 0
    assert evidence.treatment_hard_violation_count == 0
    assert evidence.canonical_summary["decision"]["admission_effect"] == "none"
    assert evidence.canonical_summary["decision"]["authority_effect"] == "none"
    assert validate_learning_intervention_frame_evidence(
        evidence.to_dict()
    ) == evidence


def test_unchanged_binding_is_ineligible_even_when_costs_changed() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    unchanged = replace(
        treatment_frame,
        plan=rule_frame.plan,
        plan_id=rule_frame.plan_id,
        plan_version=rule_frame.plan_version,
    )

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=5,
        rule_frame=rule_frame,
        treatment_frame=unchanged,
    )

    assert evidence.eligible is False
    assert evidence.binding_change_count == 0
    assert "binding_unchanged" in evidence.reason_codes
    assert evidence.model_applied_edge_count > 0


def test_fallback_frame_is_ineligible() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    assert treatment_frame.effective_matrix_result is not None
    assert treatment_frame.rule_matrix_result is not None
    metadata = dict(treatment_frame.effective_matrix_result.metadata)
    metadata.update(
        {
            "learning_applied": False,
            "learning_applied_edge_count": 0,
            "learning_shadow_only": False,
            "learning_fallback_reason": "model_timeout",
        }
    )
    fallback_matrix = replace(
        treatment_frame.effective_matrix_result,
        matrix=np.asarray(treatment_frame.rule_matrix, dtype=float).copy(),
        metadata=metadata,
    )
    fallback = replace(
        treatment_frame,
        effective_matrix_result=fallback_matrix,
        learning_state="rule_fallback",
        fallback_reason="model_timeout",
        plan=rule_frame.plan,
        plan_id=rule_frame.plan_id,
        plan_version=rule_frame.plan_version,
    )

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=6,
        rule_frame=rule_frame,
        treatment_frame=fallback,
    )

    assert evidence.eligible is False
    assert evidence.fallback_reason == "model_timeout"
    assert "learning_fallback_present" in evidence.reason_codes
    assert "learning_not_applied" in evidence.reason_codes
    assert "learning_application_count_zero" in evidence.reason_codes


@pytest.mark.parametrize(
    ("metadata_update", "expected_reason"),
    (
        ({"learning_distribution_is_ood": True}, "learning_ood"),
        (
            {
                "learning_inference_elapsed_s": 2.0,
                "learning_timeout_s": 1.0,
            },
            "learning_timeout",
        ),
        (
            {"learning_distribution_max_continuous_z": float("nan")},
            "learning_nonfinite",
        ),
    ),
)
def test_unsafe_learning_diagnostic_is_ineligible(
    metadata_update: dict[str, object],
    expected_reason: str,
) -> None:
    rule_frame, treatment_frame = _candidate_frames()
    assert treatment_frame.effective_matrix_result is not None
    metadata = dict(treatment_frame.effective_matrix_result.metadata)
    metadata.update(metadata_update)
    unsafe = replace(
        treatment_frame,
        effective_matrix_result=replace(
            treatment_frame.effective_matrix_result,
            metadata=metadata,
        ),
    )

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=16,
        rule_frame=rule_frame,
        treatment_frame=unsafe,
    )

    assert evidence.eligible is False
    assert expected_reason in evidence.reason_codes


def test_missing_learning_guard_metadata_is_ineligible() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    assert treatment_frame.effective_matrix_result is not None
    metadata = dict(treatment_frame.effective_matrix_result.metadata)
    del metadata["learning_ood_z_threshold"]
    incomplete = replace(
        treatment_frame,
        effective_matrix_result=replace(
            treatment_frame.effective_matrix_result,
            metadata=metadata,
        ),
    )

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=17,
        rule_frame=rule_frame,
        treatment_frame=incomplete,
    )

    assert evidence.eligible is False
    assert "learning_metadata_incomplete" in evidence.reason_codes


def test_expired_previous_plan_is_ineligible() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    assert rule_frame.previous_plan is not None
    expired_previous = replace(
        rule_frame.previous_plan,
        stale_after_s=0.5,
    )
    expired_rule = replace(rule_frame, previous_plan=expired_previous)
    expired_treatment = replace(
        treatment_frame,
        previous_plan=expired_previous,
    )

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=18,
        rule_frame=expired_rule,
        treatment_frame=expired_treatment,
    )

    assert evidence.eligible is False
    assert "stale_plan_time_window" in evidence.reason_codes


def test_different_input_lineage_is_ineligible() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    mismatched = replace(treatment_frame, timestamp_s=2.0)

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=7,
        rule_frame=rule_frame,
        treatment_frame=mismatched,
    )

    assert evidence.eligible is False
    assert "frame_timestamp_mismatch" in evidence.reason_codes
    assert "frame_input_lineage_mismatch" in evidence.reason_codes


def test_stale_learning_version_is_ineligible() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    assert treatment_frame.effective_matrix_result is not None
    metadata = dict(treatment_frame.effective_matrix_result.metadata)
    metadata["learning_expected_previous_version"] = 0
    metadata["learning_current_plan_version"] = 0
    stale = replace(
        treatment_frame,
        effective_matrix_result=replace(
            treatment_frame.effective_matrix_result,
            metadata=metadata,
        ),
    )

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=8,
        rule_frame=rule_frame,
        treatment_frame=stale,
    )

    assert evidence.eligible is False
    assert "stale_plan_version" in evidence.reason_codes


def test_partial_executable_m_to_n_binding_fails_all_or_none() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    assert treatment_frame.plan is not None
    target_id = treatment_frame.tracks[0].track_id
    assignments = tuple(
        item
        for index, item in enumerate(treatment_frame.plan.assignments)
        if not (item.target_id == target_id and index == 0)
    )
    invalid_plan = replace(treatment_frame.plan, assignments=assignments)
    invalid = replace(treatment_frame, plan=invalid_plan)

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=9,
        rule_frame=rule_frame,
        treatment_frame=invalid,
    )

    assert evidence.eligible is False
    assert (
        "treatment_m_to_n_all_or_none_incomplete" in evidence.reason_codes
    )


def test_hard_rejected_treatment_binding_is_ineligible() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    assert treatment_frame.rule_matrix_result is not None
    assert treatment_frame.effective_matrix_result is not None
    assert treatment_frame.plan is not None
    selected = treatment_frame.plan.assignments[0]
    row = treatment_frame.rule_matrix_result.target_ids.index(selected.target_id)
    column = treatment_frame.rule_matrix_result.resource_ids.index(
        selected.resource_id
    )
    candidate_mask = np.ones((2, 3), dtype=bool)
    candidate_mask[row, column] = False
    rejected_rule = replace(
        treatment_frame.rule_matrix_result,
        candidate_mask=candidate_mask,
    )
    rejected_effective = replace(
        treatment_frame.effective_matrix_result,
        candidate_mask=candidate_mask,
    )
    rejected = replace(
        treatment_frame,
        rule_matrix_result=rejected_rule,
        effective_matrix_result=rejected_effective,
    )

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=10,
        rule_frame=rule_frame,
        treatment_frame=rejected,
    )

    assert evidence.eligible is False
    assert "action_mask_mismatch" in evidence.reason_codes
    assert "treatment_plan_hard_constraint_violation" in evidence.reason_codes


def test_missing_serialized_field_fails_closed() -> None:
    payload = _evidence().to_dict()
    del payload["rule_matrix_sha256"]

    with pytest.raises(
        LearningInterventionEligibilityError,
        match="evidence_fields_mismatch",
    ):
        validate_learning_intervention_frame_evidence(payload)


def test_manual_eligibility_boolean_fails_closed_after_rehash() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    unchanged = replace(
        treatment_frame,
        plan=rule_frame.plan,
        plan_id=rule_frame.plan_id,
        plan_version=rule_frame.plan_version,
    )
    payload = evaluate_learning_intervention_candidate_frame(
        sequence_index=11,
        rule_frame=rule_frame,
        treatment_frame=unchanged,
    ).to_dict()
    payload["eligible"] = True
    payload["canonical_summary"]["decision"]["eligible"] = True
    _rehash(payload)

    with pytest.raises(
        LearningInterventionEligibilityError,
        match="manual_eligibility_boolean_rejected",
    ):
        validate_learning_intervention_frame_evidence(payload)


def test_placeholder_sha_fails_closed_after_rehash() -> None:
    payload = _evidence().to_dict()
    payload["rule_matrix_sha256"] = "0" * 64
    payload["canonical_summary"]["lineage"]["rule_matrix_sha256"] = "0" * 64
    _rehash(payload)

    with pytest.raises(
        LearningInterventionEligibilityError,
        match="placeholder_or_invalid_sha256",
    ):
        validate_learning_intervention_frame_evidence(payload)


def test_tampered_canonical_summary_fails_closed_after_rehash() -> None:
    payload = _evidence().to_dict()
    payload["canonical_summary"]["intervention"][
        "model_applied_edge_count"
    ] = 999
    _rehash(payload)

    with pytest.raises(
        LearningInterventionEligibilityError,
        match="canonical_summary_mismatch",
    ):
        validate_learning_intervention_frame_evidence(payload)


def test_selector_returns_first_eligible_and_requires_history_order() -> None:
    first_rule, first_treatment = _candidate_frames(timestamp_s=1.0)
    second_rule, second_treatment = _candidate_frames(timestamp_s=2.0)
    third_rule, third_treatment = _candidate_frames(timestamp_s=3.0)
    unchanged = replace(
        first_treatment,
        plan=first_rule.plan,
        plan_id=first_rule.plan_id,
        plan_version=first_rule.plan_version,
    )
    first = evaluate_learning_intervention_candidate_frame(
        sequence_index=12,
        rule_frame=first_rule,
        treatment_frame=unchanged,
    )
    second = evaluate_learning_intervention_candidate_frame(
        sequence_index=13,
        rule_frame=second_rule,
        treatment_frame=second_treatment,
    )
    third = evaluate_learning_intervention_candidate_frame(
        sequence_index=14,
        rule_frame=third_rule,
        treatment_frame=third_treatment,
    )

    assert (
        select_first_eligible_learning_intervention_frame(
            (first, second, third)
        )
        == second
    )
    with pytest.raises(
        LearningInterventionEligibilityError,
        match="candidate_history_not_strictly_ordered",
    ):
        select_first_eligible_learning_intervention_frame((second, first))


def test_selector_rejects_duplicate_and_reversed_timestamps() -> None:
    for first_timestamp, second_timestamp in ((1.0, 1.0), (2.0, 1.0)):
        first_rule, first_treatment = _candidate_frames(
            timestamp_s=first_timestamp
        )
        second_rule, second_treatment = _candidate_frames(
            timestamp_s=second_timestamp
        )
        first = evaluate_learning_intervention_candidate_frame(
            sequence_index=20,
            rule_frame=first_rule,
            treatment_frame=first_treatment,
        )
        second = evaluate_learning_intervention_candidate_frame(
            sequence_index=21,
            rule_frame=second_rule,
            treatment_frame=second_treatment,
        )

        with pytest.raises(
            LearningInterventionEligibilityError,
            match="candidate_history_timestamp_not_strictly_ordered",
        ):
            select_first_eligible_learning_intervention_frame((first, second))


def test_online_truth_key_is_rejected_without_reading_its_value() -> None:
    rule_frame, treatment_frame = _candidate_frames()
    assert treatment_frame.effective_matrix_result is not None
    contaminated = replace(
        treatment_frame,
        effective_matrix_result=replace(
            treatment_frame.effective_matrix_result,
            metadata={
                **dict(treatment_frame.effective_matrix_result.metadata),
                "truth_id": "must-not-be-used",
            },
        ),
    )

    evidence = evaluate_learning_intervention_candidate_frame(
        sequence_index=15,
        rule_frame=rule_frame,
        treatment_frame=contaminated,
    )

    assert evidence.eligible is False
    assert "online_truth_input_rejected" in evidence.reason_codes
