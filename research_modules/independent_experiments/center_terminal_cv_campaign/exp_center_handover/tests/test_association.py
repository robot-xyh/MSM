from __future__ import annotations

from dataclasses import replace

import pytest

from research_modules.independent_experiments.center_terminal_cv_campaign.common import (
    AssociationRecord,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.association import (
    CenterHandoverAssociator,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.fixture import (
    LocalTrackTruthLabel,
    build_offline_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.reporting import (
    score_association,
)


def test_twenty_target_fixture_rejects_four_false_sources_and_keeps_four_unregistered() -> None:
    fixture = build_offline_fixture(target_count=20, seed=20260816)
    associator = CenterHandoverAssociator(fixture.camera_models)
    results = [associator.process_frame(fixture.source_cues, frame) for frame in fixture.frames]
    metrics = score_association(fixture, results, mode="offline", backend="geometry")

    assert metrics["correct_source_count"] == 16
    assert metrics["false_source_count"] == 4
    assert metrics["true_binding_count"] == 16
    assert metrics["false_binding_count"] == 0
    assert metrics["false_source_rejection_rate"] == 1.0
    assert metrics["missed_target_wrong_binding_count"] == 0
    assert metrics["unregistered_candidate_count"] == 4
    assert metrics["unregistered_local_track_candidate_count"] == 4
    assert metrics["unregistered_candidate_count_semantics"] == (
        "final_frame_unmatched_camera_local_track_count"
    )
    assert metrics["unregistered_distinct_truth_target_count"] == 4
    assert metrics["unregistered_registered_target_redundant_observation_count"] == 0
    assert metrics["unregistered_center_missed_target_observation_count"] == 4
    assert metrics["unregistered_center_missed_target_distinct_count"] == 4


def test_unregistered_metric_separates_redundant_camera_track_from_missed_target() -> None:
    fixture = build_offline_fixture(target_count=5, seed=20260816)
    associator = CenterHandoverAssociator(fixture.camera_models)
    results = [associator.process_frame(fixture.source_cues, frame) for frame in fixture.frames]
    final_result = results[-1]
    confirmed = next(
        decision for decision in final_result.decisions if decision.decision_state == "confirmed"
    )
    source_truth = next(
        label
        for label in fixture.source_truth
        if label.source_track_id == confirmed.left_track_id
    )
    original = next(
        track
        for track in fixture.frames[-1]
        if track.camera_id == confirmed.metadata["camera_id"]
        and track.local_track_id == confirmed.right_track_id
    )
    duplicate = replace(original, local_track_id="LCL-REDUNDANT-VIEW")
    duplicate_decision = AssociationRecord(
        association_id="HND-REDUNDANT-TEST",
        association_type="terminal_local_unregistered",
        left_track_id=duplicate.local_track_id,
        right_track_id=None,
        measurement_timestamp=duplicate.measurement_timestamp,
        arrival_timestamp=duplicate.arrival_timestamp,
        score=12.0,
        decision_state="unregistered_candidate",
        reject_reasons=("no_selected_source_cue",),
        metadata={"camera_id": duplicate.camera_id},
    )
    fixture_with_duplicate = replace(
        fixture,
        frames=fixture.frames[:-1] + (fixture.frames[-1] + (duplicate,),),
        local_truth=fixture.local_truth
        + (
            LocalTrackTruthLabel(
                camera_id=duplicate.camera_id,
                local_track_id=duplicate.local_track_id,
                truth_target_id=str(source_truth.truth_target_id),
            ),
        ),
    )
    results[-1] = replace(
        final_result,
        decisions=final_result.decisions + (duplicate_decision,),
        unregistered_local_track_ids=final_result.unregistered_local_track_ids
        + (duplicate.local_track_id,),
    )

    metrics = score_association(
        fixture_with_duplicate, results, mode="offline", backend="geometry"
    )

    assert metrics["unregistered_candidate_count"] == 2
    assert metrics["unregistered_local_track_candidate_count"] == 2
    assert metrics["unregistered_distinct_truth_target_count"] == 2
    assert metrics["unregistered_registered_target_redundant_observation_count"] == 1
    assert metrics["unregistered_registered_target_distinct_count"] == 1
    assert metrics["unregistered_center_missed_target_observation_count"] == 1
    assert metrics["unregistered_center_missed_target_distinct_count"] == 1
    assert metrics["unregistered_unknown_truth_label_count"] == 0


def test_two_of_three_confirmation_requires_two_selected_frames() -> None:
    fixture = build_offline_fixture(target_count=5, seed=20260816)
    associator = CenterHandoverAssociator(fixture.camera_models)
    first = associator.process_frame(fixture.source_cues, fixture.frames[0])
    second = associator.process_frame(fixture.source_cues, fixture.frames[1])
    third = associator.process_frame(fixture.source_cues, fixture.frames[2])

    assert len(first.confirmed_pairs) == 0
    assert len(second.confirmed_pairs) == 4
    assert len(third.confirmed_pairs) == 4
    assert all(
        decision.confirmation_count >= 2
        for decision in second.decisions
        if decision.decision_state == "confirmed"
    )


def test_bbox_9_99_is_rejected_and_10_is_accepted() -> None:
    fixture = build_offline_fixture(target_count=5, seed=20260816)
    source = fixture.source_cues[0]
    local = fixture.frames[0][0]
    source_label = next(
        label for label in fixture.source_truth if label.source_track_id == source.source_track_id
    )
    matching_local = next(
        record
        for record in fixture.frames[0]
        if next(
            label.truth_target_id
            for label in fixture.local_truth
            if label.local_track_id == record.local_track_id
        )
        == source_label.truth_target_id
    )
    below = replace(
        matching_local,
        bbox_xyxy=(0.0, 0.0, 9.99, 3.0),
        recognition_extent_px=9.99,
        recognized=False,
    )
    boundary = replace(
        matching_local,
        bbox_xyxy=(0.0, 0.0, 10.0, 3.0),
        recognition_extent_px=10.0,
        recognized=True,
    )
    below_result = CenterHandoverAssociator(fixture.camera_models).process_frame((source,), (below,))
    boundary_result = CenterHandoverAssociator(fixture.camera_models).process_frame(
        (source,), (boundary,)
    )
    assert below_result.selected_pairs == ()
    assert len(boundary_result.selected_pairs) == 1


def test_dummy_assignment_leaves_expired_source_and_local_unmatched() -> None:
    fixture = build_offline_fixture(target_count=5, seed=20260816)
    source = replace(fixture.source_cues[0], valid_until=0.1)
    local = fixture.frames[0][0]
    result = CenterHandoverAssociator(fixture.camera_models).process_frame((source,), (local,))
    states = {decision.decision_state for decision in result.decisions}
    assert result.selected_pairs == ()
    assert states == {"source_unmatched", "unregistered_candidate"}
    source_decision = next(
        decision for decision in result.decisions if decision.decision_state == "source_unmatched"
    )
    assert "source_time_invalid" in source_decision.reject_reasons


def test_high_optional_score_cannot_restore_geometry_rejected_edge() -> None:
    fixture = build_offline_fixture(target_count=5, seed=20260816)
    source = fixture.source_cues[0]
    unrelated = next(
        local
        for local in fixture.frames[0]
        if local.camera_id != next(iter(fixture.camera_models))
    )

    def approve_everything(candidates, _sources, _locals):
        return {candidate.candidate_id: 1.0 for candidate in candidates}

    result = CenterHandoverAssociator(
        fixture.camera_models, candidate_scorer=approve_everything
    ).process_frame((source,), (unrelated,))
    assert result.selected_pairs == ()
    assert all(
        candidate.gnn_probability is None for candidate in result.candidates if not candidate.eligible
    )
