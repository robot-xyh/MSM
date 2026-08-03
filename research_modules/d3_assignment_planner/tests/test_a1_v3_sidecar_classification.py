from __future__ import annotations

import pytest

from d3_assignment_planner.a1_v3_data_contract import (
    A1V3DataContractError,
    A1V3EdgeResidualRank,
)
from d3_assignment_planner.a1_v3_dataset_writer import (
    A1V3AdapterFrameEvidence,
    build_a1_v3_online_frame,
    load_a1_v3_writer_contract,
)
from d3_assignment_planner.a1_v3_sidecar_classification import (
    analyze_a1_v3_anonymous_transition,
    derive_a1_v3_frame_classifications,
)


def _frame(
    frame_index: int,
    *,
    candidate_edges: tuple[tuple[int, int], ...],
    teacher_edges: tuple[tuple[int, int], ...],
) -> A1V3AdapterFrameEvidence:
    costs = (
        (1.0, 1.1, 1.2),
        (1.3, 1.4, 1.5),
        (1.6, 1.7, 1.8),
    )
    return A1V3AdapterFrameEvidence(
        frame_index=frame_index,
        measurement_timestamp_s=frame_index + 0.25,
        arrival_timestamp_s=frame_index + 0.75,
        observed_target_count=3,
        observed_resource_count=3,
        candidate_mask_shape=(3, 3),
        candidate_mask_true_edges=candidate_edges,
        rule_cost_matrix=costs,
        teacher_edges=teacher_edges,
        candidate_selected_edges=teacher_edges,
        effective_selected_edges=teacher_edges,
        residual_ranking=tuple(
            A1V3EdgeResidualRank(
                edge=edge,
                residual=float(rank),
                rank=rank,
            )
            for rank, edge in enumerate(candidate_edges, start=1)
        ),
        target_demand_slots=(1, 1, 1),
        pre_projection_reason_codes=("candidate_available",),
        post_projection_reason_codes=("candidate_accepted",),
    )


def _shaped_frame(
    frame_index: int,
    *,
    resource_count: int,
    candidate_edges: tuple[tuple[int, int], ...],
    teacher_edges: tuple[tuple[int, int], ...],
    target_demand_slots: tuple[int, ...],
) -> A1V3AdapterFrameEvidence:
    target_count = len(target_demand_slots)
    return A1V3AdapterFrameEvidence(
        frame_index=frame_index,
        measurement_timestamp_s=frame_index + 0.25,
        arrival_timestamp_s=frame_index + 0.75,
        observed_target_count=target_count,
        observed_resource_count=resource_count,
        candidate_mask_shape=(target_count, resource_count),
        candidate_mask_true_edges=candidate_edges,
        rule_cost_matrix=tuple(
            tuple(
                float(target * resource_count + resource)
                for resource in range(resource_count)
            )
            for target in range(target_count)
        ),
        teacher_edges=teacher_edges,
        candidate_selected_edges=teacher_edges,
        effective_selected_edges=teacher_edges,
        residual_ranking=tuple(
            A1V3EdgeResidualRank(
                edge=edge,
                residual=float(rank),
                rank=rank,
            )
            for rank, edge in enumerate(candidate_edges, start=1)
        ),
        target_demand_slots=target_demand_slots,
        pre_projection_reason_codes=("candidate_available",),
        post_projection_reason_codes=("candidate_accepted",),
    )


def _classify(
    current_candidate_edges: tuple[tuple[int, int], ...],
    current_teacher_edges: tuple[tuple[int, int], ...],
):
    contract = load_a1_v3_writer_contract()
    episode = contract.schedule.episodes[0]
    all_edges = tuple(
        (target, resource)
        for target in range(3)
        for resource in range(3)
    )
    frames = tuple(
        build_a1_v3_online_frame(episode, evidence)
        for evidence in (
            _frame(
                0,
                candidate_edges=all_edges,
                teacher_edges=((0, 0), (1, 1)),
            ),
            _frame(
                1,
                candidate_edges=current_candidate_edges,
                teacher_edges=current_teacher_edges,
            ),
        )
    )
    labels = derive_a1_v3_frame_classifications(
        episode,
        frames,
        request=contract.request,
        policy=contract.sidecar_classification_policy,
    )
    return frames, labels


def test_single_slot_coverage_transfer_is_classified_from_anonymous_evidence() -> None:
    current_candidates = tuple(
        (target, resource)
        for target in (1, 2)
        for resource in range(3)
    )
    frames, labels = _classify(
        current_candidates,
        ((1, 0), (2, 2)),
    )

    transition = analyze_a1_v3_anonymous_transition(frames[0], frames[1])
    assert transition.changed_axes == ("candidate_feasibility", "teacher_edges")
    assert transition.candidate_edge_count_before == 9
    assert transition.candidate_edge_count_after == 6
    assert transition.candidate_edge_removed_count == 3
    assert transition.candidate_edge_added_count == 0
    assert transition.teacher_edge_count_delta == 0
    assert transition.coverage_deficit_delta == 0
    assert frames[0].source.measurement_timestamp_s < (
        frames[1].source.measurement_timestamp_s
    )
    assert frames[0].source.arrival_timestamp_s < frames[1].source.arrival_timestamp_s
    assert labels[1].frame_class == "positive"
    assert labels[1].action_change_type == (
        "single_target_rebind_with_resource_release"
    )


def test_single_slot_coverage_transfer_allows_matching_capacity_recovery() -> None:
    previous_candidates = tuple(
        (target, resource)
        for target in (0, 1)
        for resource in range(3)
    )
    current_candidates = tuple(
        (target, resource)
        for target in (1, 2)
        for resource in range(3)
    )
    frames, labels = _classify_from_evidence(
        previous_candidate_edges=previous_candidates,
        previous_teacher_edges=((0, 0), (1, 1)),
        current_candidate_edges=current_candidates,
        current_teacher_edges=((1, 0), (2, 2)),
    )

    transition = analyze_a1_v3_anonymous_transition(frames[0], frames[1])
    assert transition.candidate_edge_added_count == 3
    assert transition.candidate_edge_removed_count == 3
    assert transition.teacher_edge_count_delta == 0
    assert transition.coverage_deficit_delta == 0
    assert labels[1].action_change_type == (
        "single_target_rebind_with_resource_release"
    )


def test_candidate_change_with_one_resource_exchange_is_open_chain() -> None:
    current_candidates = tuple(
        edge
        for edge in (
            (0, 0),
            (0, 1),
            (1, 0),
            (1, 1),
            (1, 2),
            (2, 0),
            (2, 1),
            (2, 2),
        )
    )
    _, labels = _classify(
        current_candidates,
        ((0, 1), (1, 2)),
    )

    assert labels[1].action_change_type == (
        "single_target_rebind_with_resource_release"
    )


def test_m_to_n_slot_redistribution_with_one_resource_exchange_is_open_chain() -> None:
    contract = load_a1_v3_writer_contract()
    episode = contract.schedule.episodes[0]
    all_edges = tuple(
        (target, resource)
        for target in range(4)
        for resource in range(4)
    )
    current_edges = tuple(edge for edge in all_edges if edge != (0, 2))
    frames = tuple(
        build_a1_v3_online_frame(episode, evidence)
        for evidence in (
            _shaped_frame(
                0,
                resource_count=4,
                candidate_edges=all_edges,
                teacher_edges=((0, 0), (0, 1), (2, 2)),
                target_demand_slots=(2, 2, 1, 1),
            ),
            _shaped_frame(
                1,
                resource_count=4,
                candidate_edges=current_edges,
                teacher_edges=((1, 0), (1, 1), (3, 3)),
                target_demand_slots=(2, 2, 1, 1),
            ),
        )
    )

    labels = derive_a1_v3_frame_classifications(
        episode,
        frames,
        request=contract.request,
        policy=contract.sidecar_classification_policy,
    )

    assert labels[1].action_change_type == (
        "single_target_rebind_with_resource_release"
    )


def test_m_to_n_slot_redistribution_with_two_resource_exchanges_fails_closed() -> None:
    contract = load_a1_v3_writer_contract()
    episode = contract.schedule.episodes[0]
    all_edges = tuple(
        (target, resource)
        for target in range(4)
        for resource in range(5)
    )
    frames = tuple(
        build_a1_v3_online_frame(episode, evidence)
        for evidence in (
            _shaped_frame(
                0,
                resource_count=5,
                candidate_edges=all_edges,
                teacher_edges=((0, 0), (0, 1), (2, 2)),
                target_demand_slots=(2, 2, 1, 1),
            ),
            _shaped_frame(
                1,
                resource_count=5,
                candidate_edges=tuple(edge for edge in all_edges if edge != (0, 2)),
                teacher_edges=((1, 0), (1, 3), (3, 4)),
                target_demand_slots=(2, 2, 1, 1),
            ),
        )
    )

    with pytest.raises(
        A1V3DataContractError,
        match="sidecar_teacher_change_unclassifiable",
    ):
        derive_a1_v3_frame_classifications(
            episode,
            frames,
            request=contract.request,
            policy=contract.sidecar_classification_policy,
        )


def test_resource_preserving_target_inventory_transfer_is_multi_target_cycle() -> None:
    _, labels = _classify(
        tuple(
            (target, resource)
            for target in range(3)
            for resource in range(3)
        ),
        ((1, 0), (2, 1)),
    )

    assert labels[1].action_change_type == "multi_target_cycle"


def test_fixed_candidate_coverage_transfer_fails_closed() -> None:
    current_candidate_edges = tuple(
        (target, resource)
        for target in range(3)
        for resource in range(3)
    )
    with pytest.raises(
        A1V3DataContractError,
        match="sidecar_teacher_change_unclassifiable",
    ):
        _classify(current_candidate_edges, ((1, 0), (2, 2)))


def _classify_from_evidence(
    *,
    previous_candidate_edges: tuple[tuple[int, int], ...],
    previous_teacher_edges: tuple[tuple[int, int], ...],
    current_candidate_edges: tuple[tuple[int, int], ...],
    current_teacher_edges: tuple[tuple[int, int], ...],
):
    contract = load_a1_v3_writer_contract()
    episode = contract.schedule.episodes[0]
    frames = tuple(
        build_a1_v3_online_frame(episode, evidence)
        for evidence in (
            _frame(
                0,
                candidate_edges=previous_candidate_edges,
                teacher_edges=previous_teacher_edges,
            ),
            _frame(
                1,
                candidate_edges=current_candidate_edges,
                teacher_edges=current_teacher_edges,
            ),
        )
    )
    labels = derive_a1_v3_frame_classifications(
        episode,
        frames,
        request=contract.request,
        policy=contract.sidecar_classification_policy,
    )
    return frames, labels
