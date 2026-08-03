from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from d3_assignment_planner import (
    A1V3CounterfactualMode,
    A1V3PostProjectionReferencePolicy,
    A1V3SourceOnlyProjectionError,
    A1V3SourceOnlyProjectionInput,
    project_a1_v3_source_only_counterfactual,
)


def _frame(
    matrix: tuple[tuple[float, ...], ...] = ((1.0, 1.001),),
    *,
    mask: tuple[tuple[bool, ...], ...] | None = None,
    demand: tuple[int, ...] = (1,),
    threat: tuple[float, ...] = (0.8,),
    unassigned: tuple[float, ...] = (10.0,),
    previous: tuple[tuple[int, int], ...] = ((0, 0),),
    mode: A1V3CounterfactualMode = A1V3CounterfactualMode.NEAR_TIE_ALTERNATIVE,
) -> A1V3SourceOnlyProjectionInput:
    costs = np.asarray(matrix, dtype=float)
    hard_mask = np.ones(costs.shape, dtype=bool) if mask is None else np.asarray(mask)
    return A1V3SourceOnlyProjectionInput(
        frame_key=(23001, "a1-v3-episode-0001", 7),
        measurement_timestamp_s=12.5,
        arrival_timestamp_s=12.52,
        rule_cost_matrix=costs,
        hard_safe_action_mask=hard_mask,
        target_demand_slots=demand,
        target_threat_scores=threat,
        unassigned_costs=np.asarray(unassigned, dtype=float),
        previous_selected_edges=previous,
        preregistered_mode=mode,
    )


def _mapping(frame: A1V3SourceOnlyProjectionInput) -> dict[str, object]:
    return {
        "frame_key": list(frame.frame_key),
        "measurement_timestamp_s": frame.measurement_timestamp_s,
        "arrival_timestamp_s": frame.arrival_timestamp_s,
        "rule_cost_matrix": frame.rule_cost_matrix.tolist(),
        "hard_safe_action_mask": frame.hard_safe_action_mask.tolist(),
        "target_demand_slots": list(frame.target_demand_slots),
        "target_threat_scores": list(frame.target_threat_scores),
        "unassigned_costs": frame.unassigned_costs.tolist(),
        "previous_selected_edges": [
            list(edge) for edge in frame.previous_selected_edges
        ],
        "preregistered_mode": frame.preregistered_mode.value,
    }


def test_one_to_one_near_tie_selects_truth_free_alternative() -> None:
    outcome = project_a1_v3_source_only_counterfactual(_frame())

    assert outcome.frame_key == (23001, "a1-v3-episode-0001", 7)
    assert outcome.measurement_timestamp_s == 12.5
    assert outcome.arrival_timestamp_s == 12.52
    assert outcome.candidate_pre_projection_edges == ((0, 1),)
    assert outcome.effective_post_projection_edges == ((0, 1),)
    assert outcome.pre_projection_reason_codes == (
        "candidate_near_tie_alternative_generated_v1",
    )
    assert outcome.post_projection_reason_codes == (
        "effective_candidate_accepted_v1",
    )
    assert outcome.safety_diagnostics.near_tie_qualifying_target_count == 1


def test_m_to_n_coverage_candidate_falls_back_atomically() -> None:
    outcome = project_a1_v3_source_only_counterfactual(
        _frame(
            matrix=((1.0, 1.1),),
            demand=(2,),
            previous=((0, 0), (0, 1)),
            mode=A1V3CounterfactualMode.COVERAGE_DEGRADING,
        )
    )

    assert outcome.candidate_pre_projection_edges == ()
    assert outcome.effective_post_projection_edges == ((0, 0), (0, 1))
    assert outcome.coverage_diagnostics.coverage_fallback_applied is True
    assert outcome.safety_diagnostics.candidate_m_to_n_atomicity_violation_count == 0
    assert outcome.safety_diagnostics.effective_m_to_n_atomicity_violation_count == 0


def test_candidate_is_independent_of_post_projection_reference() -> None:
    frame = _frame()
    first = project_a1_v3_source_only_counterfactual(
        frame, reference_effective_edges=((0, 0),)
    )
    second = project_a1_v3_source_only_counterfactual(
        frame, reference_effective_edges=()
    )
    unsafe = project_a1_v3_source_only_counterfactual(
        frame, reference_effective_edges=((0, 0), (0, 1))
    )

    assert first.candidate_pre_projection_edges == ((0, 1),)
    assert (
        first.candidate_pre_projection_edges
        == second.candidate_pre_projection_edges
        == unsafe.candidate_pre_projection_edges
    )
    assert (
        first.pre_projection_reason_codes
        == second.pre_projection_reason_codes
        == unsafe.pre_projection_reason_codes
    )
    assert unsafe.safety_diagnostics.reference_safety_valid is False
    assert unsafe.post_projection_reason_codes[0] == (
        "reference_effective_edges_rejected_unsafe_v1"
    )

    coverage_frame = _frame(
        matrix=((1.0, 5.0), (5.0, 1.0)),
        demand=(1, 1),
        threat=(0.2, 0.9),
        unassigned=(10.0, 10.0),
        previous=((0, 0), (1, 1)),
        mode=A1V3CounterfactualMode.COVERAGE_DEGRADING,
    )
    full_floor = project_a1_v3_source_only_counterfactual(
        coverage_frame, reference_effective_edges=((0, 0), (1, 1))
    )
    reduced_floor = project_a1_v3_source_only_counterfactual(
        coverage_frame, reference_effective_edges=((1, 1),)
    )
    assert full_floor.candidate_pre_projection_edges == ((1, 1),)
    assert (
        full_floor.candidate_pre_projection_edges
        == reduced_floor.candidate_pre_projection_edges
    )
    assert full_floor.effective_post_projection_edges == ((0, 0), (1, 1))
    assert reduced_floor.effective_post_projection_edges == ((1, 1),)


def test_exact_reference_plan_stability_falls_back_for_same_coverage_rebinding() -> None:
    frame = _frame(
        matrix=((1.0, 9.0, 9.0), (9.0, 2.0, 1.0)),
        demand=(1, 1),
        threat=(0.2, 0.9),
        unassigned=(10.0, 10.0),
        previous=((0, 0), (1, 2)),
        mode=A1V3CounterfactualMode.COVERAGE_DEGRADING,
    )
    coverage_only = project_a1_v3_source_only_counterfactual(
        frame,
        reference_effective_edges=((1, 1),),
    )
    exact_first = project_a1_v3_source_only_counterfactual(
        frame,
        reference_effective_edges=((1, 1),),
        reference_policy=(
            A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE
        ),
    )
    exact_second = project_a1_v3_source_only_counterfactual(
        frame,
        reference_effective_edges=((1, 0),),
        reference_policy=(
            A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE
        ),
    )

    assert coverage_only.post_projection_reference_policy is (
        A1V3PostProjectionReferencePolicy.COVERAGE_FLOOR
    )
    assert coverage_only.candidate_pre_projection_edges == ((1, 2),)
    assert coverage_only.effective_post_projection_edges == ((1, 2),)
    assert coverage_only.post_projection_reason_codes == (
        "effective_candidate_accepted_v1",
    )
    assert (
        coverage_only.candidate_pre_projection_edges
        == exact_first.candidate_pre_projection_edges
        == exact_second.candidate_pre_projection_edges
    )
    assert (
        coverage_only.pre_projection_reason_codes
        == exact_first.pre_projection_reason_codes
        == exact_second.pre_projection_reason_codes
    )
    assert exact_first.effective_post_projection_edges == ((1, 1),)
    assert exact_second.effective_post_projection_edges == ((1, 0),)
    assert exact_first.coverage_diagnostics.lost_floor_covered_target_count == 0
    assert exact_first.post_projection_reason_codes == (
        "effective_reference_plan_stability_fallback_v1",
    )
    assert (
        exact_first.safety_diagnostics.reference_plan_stability_fallback_applied
        is True
    )
    assert exact_first.to_dict()["post_projection_reference_policy"] == (
        "exact_safe_reference"
    )


@pytest.mark.parametrize(
    ("reference", "expected_code"),
    [
        (None, "exact_reference_plan_stability_reference_required"),
        (((0, 3),), "exact_reference_plan_stability_reference_invalid"),
        (
            ((0, 0), (1, 0)),
            "exact_reference_plan_stability_reference_unsafe",
        ),
    ],
)
def test_exact_reference_plan_stability_rejects_missing_invalid_or_unsafe_reference(
    reference: tuple[tuple[int, int], ...] | None,
    expected_code: str,
) -> None:
    frame = _frame(
        matrix=((1.0, 9.0, 9.0), (9.0, 2.0, 1.0)),
        demand=(1, 1),
        threat=(0.2, 0.9),
        unassigned=(10.0, 10.0),
        previous=((0, 0), (1, 2)),
        mode=A1V3CounterfactualMode.COVERAGE_DEGRADING,
    )
    with pytest.raises(A1V3SourceOnlyProjectionError) as caught:
        project_a1_v3_source_only_counterfactual(
            frame,
            reference_effective_edges=reference,
            reference_policy=(
                A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE
            ),
        )
    assert caught.value.code == expected_code


def test_exact_reference_plan_stability_rejects_incomplete_m_to_n_reference() -> None:
    frame = _frame(
        matrix=((1.0, 1.1),),
        demand=(2,),
        previous=((0, 0), (0, 1)),
        mode=A1V3CounterfactualMode.COVERAGE_DEGRADING,
    )
    with pytest.raises(A1V3SourceOnlyProjectionError) as caught:
        project_a1_v3_source_only_counterfactual(
            frame,
            reference_effective_edges=((0, 0),),
            reference_policy=(
                A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE
            ),
        )
    assert caught.value.code == "exact_reference_plan_stability_reference_unsafe"


def test_coverage_degrading_candidate_uses_reference_coverage_fallback() -> None:
    outcome = project_a1_v3_source_only_counterfactual(
        _frame(mode=A1V3CounterfactualMode.COVERAGE_DEGRADING),
        reference_effective_edges=((0, 1),),
    )

    assert outcome.candidate_pre_projection_edges == ()
    assert outcome.effective_post_projection_edges == ((0, 1),)
    assert outcome.coverage_diagnostics.safety_floor_source == (
        "reference_effective_edges"
    )
    assert outcome.coverage_diagnostics.lost_floor_covered_target_count == 1
    assert outcome.post_projection_reason_codes == (
        "effective_reference_coverage_fallback_v1",
    )


def test_near_tie_without_true_rule_cost_boundary_fails_closed() -> None:
    outcome = project_a1_v3_source_only_counterfactual(
        _frame(matrix=((1.0, 2.0),))
    )

    assert outcome.candidate_pre_projection_edges == ()
    assert outcome.effective_post_projection_edges == ((0, 0),)
    assert outcome.safety_diagnostics.candidate_available is False
    assert outcome.safety_diagnostics.near_tie_qualifying_target_count == 0
    assert outcome.pre_projection_reason_codes == (
        "candidate_near_tie_alternative_unavailable_v1",
    )
    assert outcome.post_projection_reason_codes == (
        "effective_rule_fallback_no_candidate_v1",
    )


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (
            {"arrival_timestamp_s": 12.5},
            "stale_timestamp_order",
        ),
        (
            {"rule_cost_matrix": np.asarray(((1.0, np.nan),))},
            "rule_cost_matrix_non_finite",
        ),
        (
            {"hard_safe_action_mask": np.asarray(((1, 1),), dtype=int)},
            "hard_safe_action_mask_invalid",
        ),
    ],
)
def test_illegal_or_stale_input_fails_with_stable_code(
    change: dict[str, object], code: str
) -> None:
    with pytest.raises(A1V3SourceOnlyProjectionError) as caught:
        replace(_frame(), **change)
    assert caught.value.code == code


def test_stale_previous_edges_are_rejected() -> None:
    with pytest.raises(A1V3SourceOnlyProjectionError) as caught:
        _frame(mask=((True, False),), previous=((0, 1),))
    assert caught.value.code == "previous_edges_stale"


@pytest.mark.parametrize("field", ("teacher_edges", "global_track_id", "truth_actor_id"))
def test_forbidden_truth_or_identity_fields_are_rejected(field: str) -> None:
    payload = _mapping(_frame())
    payload[field] = []
    with pytest.raises(A1V3SourceOnlyProjectionError) as caught:
        A1V3SourceOnlyProjectionInput.from_mapping(payload)
    assert caught.value.code == "forbidden_truth_or_identity_field"


def test_deterministic_replay_and_all_authority_permissions_false() -> None:
    frame = A1V3SourceOnlyProjectionInput.from_mapping(_mapping(_frame()))
    first = project_a1_v3_source_only_counterfactual(frame)
    second = project_a1_v3_source_only_counterfactual(frame)

    assert first.to_dict() == second.to_dict()
    assert first.to_dict()["permissions"] == {
        "runtime": False,
        "assignment": False,
        "plan": False,
        "control": False,
        "global_track_id": False,
    }
    assert first.safety_diagnostics.candidate_duplicate_resource_count == 0
    assert first.safety_diagnostics.candidate_hard_edge_violation_count == 0
    assert first.safety_diagnostics.effective_duplicate_resource_count == 0
    assert first.safety_diagnostics.effective_hard_edge_violation_count == 0
