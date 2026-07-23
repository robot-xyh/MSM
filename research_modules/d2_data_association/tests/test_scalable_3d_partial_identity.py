from __future__ import annotations

import json
from pathlib import Path

import pytest

from d2_data_association import (
    GlobalTrackLineageEvidence,
    ObservationLineageRef,
    Scalable3DObservationTruthLabel,
    assert_scalable_3d_online_identity_records_truth_free,
    create_scalable_3d_identity_evidence_bundle,
    evaluate_scalable_3d_identity,
    hash_scalable_3d_observation_truth_labels,
    load_scalable_3d_identity_evaluation,
    sha256_file,
)


def _label(
    observation_id: str,
    truth_target_id: str,
    timestamp: float,
) -> Scalable3DObservationTruthLabel:
    return Scalable3DObservationTruthLabel(
        observation_id=observation_id,
        truth_target_id=truth_target_id,
        measurement_timestamp=timestamp,
    )


def _record(
    frame_index: int,
    global_track_id: str,
    observation_ids: tuple[str, ...],
    *,
    association_state: str | None = None,
) -> GlobalTrackLineageEvidence:
    timestamp = float(frame_index)
    return GlobalTrackLineageEvidence(
        episode_id="partial-identity-test",
        frame_index=frame_index,
        frame_timestamp=timestamp,
        global_track_id=global_track_id,
        lifecycle_state="tentative" if frame_index == 0 else "confirmed",
        association_state=(
            association_state
            or ("created" if frame_index == 0 else "matched")
        ),
        source_observations=tuple(
            ObservationLineageRef(
                observation_id=observation_id,
                measurement_timestamp=timestamp,
                source_lineage=("sensor", observation_id),
            )
            for observation_id in observation_ids
        ),
        d1_record_sequences=(10 + frame_index,),
        d2_record_sequence=20 + frame_index,
    )


def _evaluate(
    records: tuple[GlobalTrackLineageEvidence, ...],
    labels: tuple[Scalable3DObservationTruthLabel, ...],
):
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="partial-identity-test",
        records=records,
        online_d1_records_sha256="sha256:" + "1" * 64,
        online_d2_records_sha256="sha256:" + "2" * 64,
        observation_truth_labels_sha256=(
            hash_scalable_3d_observation_truth_labels(labels)
        ),
    )
    return evaluate_scalable_3d_identity(bundle, labels)


def _diagnostics(result):
    diagnostics = result.partial_identity_diagnostics
    assert diagnostics is not None
    return diagnostics


def test_fully_available_identity_retains_strict_metrics_and_full_coverage() -> None:
    labels = (
        _label("a-0", "truth-A", 0.0),
        _label("b-0", "truth-B", 0.0),
        _label("a-1", "truth-A", 1.0),
        _label("b-1", "truth-B", 1.0),
    )
    records = (
        _record(0, "GT-A", ("a-0",)),
        _record(0, "GT-B", ("b-0",)),
        _record(1, "GT-A", ("a-1",)),
        _record(1, "GT-B", ("b-1",)),
    )

    result = _evaluate(records, labels)
    diagnostics = _diagnostics(result)

    assert result.metrics.available is True
    assert result.metrics.id_switch_count == 0
    assert diagnostics.total_mapping_count == 4
    assert diagnostics.available_mapping_count == 4
    assert diagnostics.evaluable_mapping_count == 4
    assert diagnostics.evaluable_mapping_coverage == pytest.approx(1.0)
    assert diagnostics.evaluable_frame_count == 2
    assert diagnostics.evaluable_frame_coverage == pytest.approx(1.0)
    assert diagnostics.transition_opportunity_count == 2
    assert diagnostics.evaluable_transition_count == 2
    assert diagnostics.evaluable_transition_coverage == pytest.approx(1.0)
    assert diagnostics.lower_bound_anchor_excluded_truth_frame_count == 0
    assert diagnostics.lower_bound_anchor_exclusion_reason_counts == {}
    assert diagnostics.lower_bound_anchor_transition_count == 2
    assert diagnostics.id_switch_lower_bound == 0


def test_partial_missing_sidecar_reports_coverage_without_zero_idsw_claim() -> None:
    labels = (
        _label("a-0", "truth-A", 0.0),
        _label("presence-a-1", "truth-A", 1.0),
    )
    records = (
        _record(0, "GT-A", ("a-0",)),
        _record(1, "GT-A", ("missing-a-1",)),
    )

    result = _evaluate(records, labels)
    diagnostics = _diagnostics(result)
    payload = diagnostics.to_dict()

    assert result.metrics.available is False
    assert result.metrics.id_switch_count is None
    assert diagnostics.total_mapping_count == 2
    assert diagnostics.available_mapping_count == 1
    assert diagnostics.unavailable_mapping_count == 1
    assert diagnostics.evaluable_mapping_count == 1
    assert diagnostics.missing_identity_evidence_mapping_count == 1
    assert diagnostics.evaluable_mapping_coverage == pytest.approx(0.5)
    assert diagnostics.evaluable_frame_count == 1
    assert diagnostics.evaluable_frame_coverage == pytest.approx(0.5)
    assert diagnostics.transition_opportunity_count == 1
    assert diagnostics.evaluable_transition_count == 0
    assert diagnostics.lower_bound_anchor_excluded_truth_frame_count == 0
    assert diagnostics.id_switch_lower_bound is None
    assert (
        diagnostics.id_switch_lower_bound_reason
        == "no_evaluable_identity_transitions"
    )
    assert payload["id_switch_upper_bound"] is None
    assert payload["id_switch_upper_bound_available"] is False


def test_ambiguous_track_mapping_remains_strictly_unavailable() -> None:
    labels = (
        _label("a-0", "truth-A", 0.0),
        _label("a-1", "truth-A", 1.0),
        _label("b-1", "truth-B", 1.0),
    )
    records = (
        _record(0, "GT-1", ("a-0",)),
        _record(1, "GT-1", ("a-1", "b-1")),
    )

    result = _evaluate(records, labels)
    diagnostics = _diagnostics(result)

    assert result.metrics.available is False
    assert result.metrics.reason == "multiple_truth_targets_for_global_track"
    assert result.metrics.id_switch_count is None
    assert diagnostics.available_mapping_count == 1
    assert diagnostics.ambiguous_mapping_count == 1
    assert diagnostics.ambiguous_scored_mapping_count == 1
    assert diagnostics.evaluable_mapping_coverage == pytest.approx(0.5)
    assert diagnostics.evaluable_transition_count == 0
    assert diagnostics.lower_bound_anchor_excluded_truth_frame_count == 0
    assert diagnostics.id_switch_lower_bound is None


def test_two_target_crossing_produces_a_conservative_switch_lower_bound() -> None:
    labels = (
        _label("a-0", "truth-A", 0.0),
        _label("b-0", "truth-B", 0.0),
        _label("b-1", "truth-B", 1.0),
        _label("a-1", "truth-A", 1.0),
    )
    records = (
        _record(0, "GT-1", ("a-0",)),
        _record(0, "GT-2", ("b-0",)),
        _record(1, "GT-1", ("b-1",)),
        _record(1, "GT-2", ("a-1",)),
    )

    result = _evaluate(records, labels)
    diagnostics = _diagnostics(result)

    assert result.metrics.available is True
    assert result.metrics.id_switch_count == 2
    assert diagnostics.lower_bound_anchor_excluded_truth_frame_count == 0
    assert diagnostics.lower_bound_anchor_transition_count == 2
    assert diagnostics.id_switch_lower_bound == 2
    assert diagnostics.evaluable_transition_coverage == pytest.approx(1.0)


def test_duplicate_truth_mapping_does_not_create_false_lower_bound() -> None:
    labels = (
        _label("a-0-primary", "truth-A", 0.0),
        _label("a-0-duplicate", "truth-A", 0.0),
        _label("a-1-primary", "truth-A", 1.0),
        _label("a-1-duplicate", "truth-A", 1.0),
    )
    records = (
        _record(0, "GT-1", ("a-0-primary",)),
        _record(0, "GT-2", ("a-0-duplicate",)),
        _record(1, "GT-2", ("a-1-primary",)),
        _record(1, "GT-1", ("a-1-duplicate",)),
    )

    result = _evaluate(records, labels)
    diagnostics = _diagnostics(result)

    assert result.metrics.available is True
    assert result.metrics.duplicate_truth_to_track_count == 2
    assert result.metrics.id_switch_count == 1
    assert diagnostics.evaluable_mapping_coverage == pytest.approx(1.0)
    assert diagnostics.evaluable_frame_coverage == pytest.approx(1.0)
    assert diagnostics.evaluable_transition_count == 0
    assert diagnostics.evaluable_transition_coverage == pytest.approx(0.0)
    assert diagnostics.lower_bound_anchor_excluded_truth_frame_count == 2
    assert diagnostics.lower_bound_anchor_exclusion_reason_counts == {
        "multiple_evaluable_global_tracks_for_truth_frame": 2
    }
    assert diagnostics.lower_bound_anchor_transition_count == 0
    assert diagnostics.id_switch_lower_bound is None
    assert (
        diagnostics.id_switch_lower_bound_reason
        == "no_evaluable_identity_transitions"
    )


def test_duplicate_anchor_exclusion_is_audited_in_incomplete_frame() -> None:
    labels = (
        _label("a-0-primary", "truth-A", 0.0),
        _label("a-0-duplicate", "truth-A", 0.0),
        _label("a-0-ambiguous", "truth-A", 0.0),
        _label("b-0-ambiguous", "truth-B", 0.0),
    )
    records = (
        _record(0, "GT-1", ("a-0-primary",)),
        _record(0, "GT-2", ("a-0-duplicate",)),
        _record(
            0,
            "GT-3",
            ("a-0-ambiguous", "b-0-ambiguous"),
        ),
    )

    result = _evaluate(records, labels)
    diagnostics = _diagnostics(result)

    assert result.metrics.available is False
    assert result.metrics.reason == "multiple_truth_targets_for_global_track"
    assert result.metrics.id_switch_count is None
    assert diagnostics.evaluable_frame_count == 0
    assert diagnostics.lower_bound_anchor_excluded_truth_frame_count == 1
    assert diagnostics.lower_bound_anchor_exclusion_reason_counts == {
        "multiple_evaluable_global_tracks_for_truth_frame": 1
    }
    assert diagnostics.lower_bound_anchor_transition_count == 0
    assert diagnostics.id_switch_lower_bound is None


def test_zero_transition_denominator_does_not_publish_zero_lower_bound() -> None:
    labels = (_label("a-0", "truth-A", 0.0),)
    records = (_record(0, "GT-A", ("a-0",)),)

    result = _evaluate(records, labels)
    diagnostics = _diagnostics(result)
    payload = diagnostics.to_dict()

    assert result.metrics.available is True
    assert result.metrics.id_switch_count == 0
    assert diagnostics.transition_opportunity_count == 0
    assert diagnostics.evaluable_transition_count == 0
    assert diagnostics.evaluable_transition_coverage is None
    assert (
        diagnostics.evaluable_transition_coverage_reason
        == "no_truth_presence_transition_opportunities"
    )
    assert diagnostics.id_switch_lower_bound is None
    assert payload["id_switch_lower_bound_available"] is False


def test_partial_diagnostics_are_evaluator_only_and_tamper_evident(
    tmp_path: Path,
) -> None:
    labels = (_label("a-0", "truth-A", 0.0),)
    record = _record(0, "GT-A", ("a-0",))
    result = _evaluate((record,), labels)

    online_payload = record.to_dict()
    assert "partial_identity_diagnostics" not in online_payload
    assert "truth_target_id" not in json.dumps(online_payload, sort_keys=True)
    assert_scalable_3d_online_identity_records_truth_free(
        (online_payload,),
        source_name="D2 identity lineage DTO",
    )

    payload = result.to_dict()
    diagnostics = payload["partial_identity_diagnostics"]
    diagnostics["evaluable_mapping_count"] = 0
    path = tmp_path / "tampered_identity_evaluation.json"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="categories are incomplete|coverage contradicts|diagnostics contradict",
    ):
        load_scalable_3d_identity_evaluation(
            path,
            expected_sha256=sha256_file(path),
        )


def test_legacy_evaluation_v1_without_partial_diagnostics_still_loads(
    tmp_path: Path,
) -> None:
    labels = (_label("a-0", "truth-A", 0.0),)
    result = _evaluate((_record(0, "GT-A", ("a-0",)),), labels)
    payload = result.to_dict()
    payload.pop("partial_identity_diagnostics")
    path = tmp_path / "legacy_identity_evaluation.json"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    loaded = load_scalable_3d_identity_evaluation(
        path,
        expected_sha256=sha256_file(path),
    )

    assert loaded.partial_identity_diagnostics is None
    assert "partial_identity_diagnostics" not in loaded.to_dict()
    assert loaded.metrics.id_switch_count == 0
