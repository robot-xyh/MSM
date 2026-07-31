from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

import d2_data_association.scalable_3d_identity_diagnostics as diagnostics_module

from d2_data_association import (
    GlobalTrackLineageEvidence,
    ObservationLineageRef,
    Scalable3DIdentityEvaluation,
    Scalable3DObservationTruthLabel,
    build_scalable_3d_identity_blocker_diagnostics,
    create_scalable_3d_identity_evidence_bundle,
    evaluate_scalable_3d_identity,
    hash_scalable_3d_observation_truth_labels,
    write_scalable_3d_identity_blocker_diagnostics,
)


_SHA = "sha256:" + "9" * 64


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


def _ref(observation_id: str, timestamp: float) -> ObservationLineageRef:
    return ObservationLineageRef(
        observation_id=observation_id,
        measurement_timestamp=timestamp,
        source_lineage=(
            "opaque_online_lineage",
            "sensor:test",
            observation_id,
        ),
    )


def _record(
    frame_index: int,
    timestamp: float,
    refs: tuple[ObservationLineageRef, ...],
    *,
    association_state: str,
    lifecycle_state: str,
    global_track_id: str = "GT-001",
) -> GlobalTrackLineageEvidence:
    return GlobalTrackLineageEvidence(
        episode_id="episode-diagnostics",
        frame_index=frame_index,
        frame_timestamp=timestamp,
        global_track_id=global_track_id,
        lifecycle_state=lifecycle_state,
        association_state=association_state,
        source_observations=refs,
        d1_record_sequences=(frame_index + 1,),
        d2_record_sequence=frame_index + 101,
    )


def _evaluate(records, labels):
    labels = tuple(labels)
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="episode-diagnostics",
        records=tuple(records),
        online_d1_records_sha256="sha256:" + "1" * 64,
        online_d2_records_sha256="sha256:" + "2" * 64,
        observation_truth_labels_sha256=(
            hash_scalable_3d_observation_truth_labels(labels)
        ),
    )
    result = evaluate_scalable_3d_identity(bundle, labels)
    audit = dict(result.audit)
    audit["online_truth_isolation_verified"] = True
    audit["identity_heuristics_used"] = False
    verified = Scalable3DIdentityEvaluation(
        episode_id=result.episode_id,
        source_hashes=result.source_hashes,
        frames=result.frames,
        metrics=result.metrics,
        partial_identity_diagnostics=result.partial_identity_diagnostics,
        configuration=result.configuration,
        audit=audit,
    )
    return bundle, verified, labels


def _d1_evidence(*observation_timestamps):
    records = [
        {
            "observation_id": observation_id,
            "measurement_timestamp": timestamp,
            "availability": {
                "estimate": {"available": True, "reason": None}
            },
        }
        for observation_id, timestamp in observation_timestamps
    ]
    return {"record_count": len(records), "records": records}


def test_multi_truth_track_intervals_remain_strictly_unavailable_but_exact_d1_records_are_possible(
    tmp_path: Path,
) -> None:
    labels = (
        _label("obs-a-0", "truth-A", 0.0),
        _label("obs-b-0", "truth-B", 0.0),
        _label("obs-a-1", "truth-A", 1.0),
        _label("obs-b-1", "truth-B", 1.0),
    )
    records = (
        _record(
            0,
            0.0,
            (_ref("obs-a-0", 0.0), _ref("obs-b-0", 0.0)),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _record(
            1,
            1.0,
            (_ref("obs-a-1", 1.0), _ref("obs-b-1", 1.0)),
            association_state="matched",
            lifecycle_state="confirmed",
        ),
    )
    bundle, evaluation, normalized_labels = _evaluate(records, labels)

    diagnostics = build_scalable_3d_identity_blocker_diagnostics(
        bundle,
        evaluation,
        normalized_labels,
        identity_evaluation_sha256=_SHA,
        d1_consistency_evidence=_d1_evidence(
            ("obs-a-0", 0.0),
            ("obs-b-0", 0.0),
            ("obs-a-1", 1.0),
            ("obs-b-1", 1.0),
        ),
        d1_consistency_evidence_sha256="sha256:" + "8" * 64,
    )

    assert diagnostics.strict_identity_metrics_available is False
    assert diagnostics.blocking_reason_counts == {
        "multiple_truth_targets_for_global_track": 2
    }
    assert diagnostics.root_cause_counts == {
        "persisted_multi_truth_track_frame": 2
    }
    assert len(diagnostics.blocker_intervals) == 1
    interval = diagnostics.blocker_intervals[0]
    assert interval["frame_indices"] == [0, 1]
    assert interval["candidate_truth_target_ids"] == [
        "truth-A",
        "truth-B",
    ]
    assert {
        item["truth_label_status"]
        for frame in interval["frames"]
        for item in frame["source_observations"]
    } == {"unique"}

    d1_audit = diagnostics.d1_lineage_mapping_audit
    assert d1_audit is not None
    assert d1_audit["d1_consumable"] is True
    assert d1_audit["available_candidate_mapping_count"] == 4
    assert len(d1_audit["mapping_records"]) == 4
    assert all(
        item["schema_version"].endswith("mapping_record.v1")
        for item in d1_audit["mapping_records"]
    )

    output = tmp_path / "diagnostics.json"
    first_hash = write_scalable_3d_identity_blocker_diagnostics(
        output,
        diagnostics,
    )
    second_hash = write_scalable_3d_identity_blocker_diagnostics(
        output,
        diagnostics,
    )
    assert first_hash == second_hash


def test_missing_truth_label_fails_closed_and_emits_no_d1_mapping_records() -> None:
    labels = (_label("other-observation", "truth-A", 0.0),)
    records = (
        _record(
            0,
            0.0,
            (_ref("unlabeled-observation", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )
    bundle, evaluation, normalized_labels = _evaluate(records, labels)

    diagnostics = build_scalable_3d_identity_blocker_diagnostics(
        bundle,
        evaluation,
        normalized_labels,
        identity_evaluation_sha256=_SHA,
        d1_consistency_evidence=_d1_evidence(
            ("unlabeled-observation", 0.0),
        ),
        d1_consistency_evidence_sha256="sha256:" + "8" * 64,
    )

    assert diagnostics.blocking_reason_counts["truth_label_missing"] == 1
    d1_audit = diagnostics.d1_lineage_mapping_audit
    assert d1_audit is not None
    assert d1_audit["d1_consumable"] is False
    assert d1_audit["reason"] == "truth_label_missing"
    assert d1_audit["mapping_records"] == []
    assert d1_audit["mapping_records_emitted"] is False


def test_d1_mapping_requires_every_estimate_observation_to_have_a_d2_claim() -> None:
    labels = (
        _label("obs-associated", "truth-A", 0.0),
        _label("obs-never-published-by-d2", "truth-B", 0.0),
    )
    records = (
        _record(
            0,
            0.0,
            (_ref("obs-associated", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )
    bundle, evaluation, normalized_labels = _evaluate(records, labels)

    diagnostics = build_scalable_3d_identity_blocker_diagnostics(
        bundle,
        evaluation,
        normalized_labels,
        identity_evaluation_sha256=_SHA,
        d1_consistency_evidence=_d1_evidence(
            ("obs-associated", 0.0),
            ("obs-never-published-by-d2", 0.0),
        ),
        d1_consistency_evidence_sha256="sha256:" + "8" * 64,
    )

    assert diagnostics.strict_identity_metrics_available is True
    d1_audit = diagnostics.d1_lineage_mapping_audit
    assert d1_audit is not None
    assert d1_audit["d1_consumable"] is False
    assert d1_audit["available_candidate_mapping_count"] == 1
    assert d1_audit["unresolved_reason_counts"] == {
        "d2_lineage_claim_missing": 1
    }
    assert d1_audit["mapping_records"] == []


def test_diagnostics_reject_an_unbound_identity_evaluation_hash() -> None:
    labels = (_label("obs-a", "truth-A", 0.0),)
    records = (
        _record(
            0,
            0.0,
            (_ref("obs-a", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )
    bundle, evaluation, normalized_labels = _evaluate(records, labels)
    source_hashes = dict(evaluation.source_hashes)
    source_hashes["online_d1_records"] = "sha256:" + "7" * 64
    tampered = Scalable3DIdentityEvaluation(
        episode_id=evaluation.episode_id,
        source_hashes=source_hashes,
        frames=evaluation.frames,
        metrics=evaluation.metrics,
        partial_identity_diagnostics=evaluation.partial_identity_diagnostics,
        configuration=evaluation.configuration,
        audit=evaluation.audit,
    )

    with pytest.raises(
        ValueError,
        match="source hash mismatch",
    ):
        build_scalable_3d_identity_blocker_diagnostics(
            bundle,
            tampered,
            normalized_labels,
            identity_evaluation_sha256=_SHA,
        )


def test_multi_truth_causal_event_identifies_newest_camera_introduction() -> None:
    labels = (
        _label("radar-old", "truth-A", 1.2),
        _label("radar-newer", "truth-A", 1.6),
        _label("camera-latest", "truth-B", 1.8),
    )
    radar_old = ObservationLineageRef(
        observation_id="radar-old",
        measurement_timestamp=1.2,
        source_lineage=(
            "opaque_online_lineage",
            "sensor:RADAR-CENTER-001",
            "radar-old",
        ),
    )
    radar_newer = ObservationLineageRef(
        observation_id="radar-newer",
        measurement_timestamp=1.6,
        source_lineage=(
            "opaque_online_lineage",
            "sensor:RADAR-CENTER-001",
            "radar-newer",
        ),
    )
    camera_latest = ObservationLineageRef(
        observation_id="camera-latest",
        measurement_timestamp=1.8,
        source_lineage=(
            "opaque_online_lineage",
            "sensor:CAM-RECON-008",
            "camera-latest",
        ),
    )
    records = (
        _record(
            0,
            1.9,
            (radar_old, radar_newer, camera_latest),
            association_state="matched",
            lifecycle_state="confirmed",
        ),
    )
    bundle, evaluation, normalized_labels = _evaluate(records, labels)

    diagnostics = build_scalable_3d_identity_blocker_diagnostics(
        bundle,
        evaluation,
        normalized_labels,
        identity_evaluation_sha256=_SHA,
    )

    event = diagnostics.causal_mapping_events[0]
    assert event["reason"] == "multiple_truth_targets_for_global_track"
    assert event["causal_classification"] == (
        "newest_observation_introduced_new_truth"
    )
    assert event["historical_truth_cluster"]["truth_target_ids"] == [
        "truth-A"
    ]
    assert event["newest_observation_truth"]["truth_target_ids"] == [
        "truth-B"
    ]
    assert event["sensor_transition"]["modality_transition"] == (
        "radar->camera"
    )
    assert event["sensor_transition"]["newest_sensor_ids"] == [
        "CAM-RECON-008"
    ]


def test_lineage_age_classification_preserves_517_to_1_split() -> None:
    classifications = [
        diagnostics_module._causal_classification(
            reason="source_observation_outside_lineage_window",
            historical_truth_ids=("truth-A",),
            newest_truth_ids=("truth-A",),
            stale_source_rows=({"age_seconds": 1.01},),
            commitment_source_age=0.6,
            commitment_freshness_window_s=0.9,
            tolerance=1.0e-9,
        )
        for _ in range(517)
    ]
    classifications.append(
        diagnostics_module._causal_classification(
            reason="source_observation_outside_lineage_window",
            historical_truth_ids=("truth-A",),
            newest_truth_ids=("truth-A",),
            stale_source_rows=({"age_seconds": 1.02},),
            commitment_source_age=0.95,
            commitment_freshness_window_s=0.9,
            tolerance=1.0e-9,
        )
    )

    assert Counter(classifications) == {
        "historical_lineage_only_stale": 517,
        "active_commitment_source_stale": 1,
    }
