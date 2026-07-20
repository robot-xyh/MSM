from __future__ import annotations

import json
from pathlib import Path

import pytest

from d2_data_association import (
    AssociationResult,
    SCALABLE_3D_EXTERNAL_TRUTH_SCHEMA_VERSION,
    SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION,
    SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION,
    GlobalTrackLineageEvidence,
    MetricsRecorder,
    ObservationLineageRef,
    Scalable3DObservationTruthLabel,
    create_scalable_3d_identity_evidence_bundle,
    evaluate_scalable_3d_identity,
    evaluate_scalable_3d_identity_files,
    hash_scalable_3d_observation_truth_labels,
    load_scalable_3d_identity_evaluation,
    sha256_file,
    write_scalable_3d_identity_evaluation,
    write_scalable_3d_identity_evidence,
)


def _truth(
    observation_id: str,
    truth_target_id: str,
    timestamp: float,
) -> Scalable3DObservationTruthLabel:
    return Scalable3DObservationTruthLabel(
        observation_id=observation_id,
        truth_target_id=truth_target_id,
        measurement_timestamp=timestamp,
    )


def _ref(
    observation_id: str,
    timestamp: float,
    *,
    replay_generation: int = 0,
    lineage: tuple[str, ...] | None = None,
) -> ObservationLineageRef:
    return ObservationLineageRef(
        observation_id=observation_id,
        measurement_timestamp=timestamp,
        source_lineage=lineage or ("sensor-payload", observation_id),
        replay_generation=replay_generation,
    )


def _evidence(
    frame_index: int,
    timestamp: float,
    global_track_id: str,
    refs: tuple[ObservationLineageRef, ...],
    *,
    association_state: str = "matched",
    lifecycle_state: str = "confirmed",
    d1_sequences: tuple[int, ...] = (11,),
    d2_sequence: int | None = 21,
) -> GlobalTrackLineageEvidence:
    return GlobalTrackLineageEvidence(
        episode_id="episode-test",
        frame_index=frame_index,
        frame_timestamp=timestamp,
        global_track_id=global_track_id,
        lifecycle_state=lifecycle_state,
        association_state=association_state,
        source_observations=refs,
        d1_record_sequences=d1_sequences,
        d2_record_sequence=d2_sequence,
    )


def _bundle(
    records: tuple[GlobalTrackLineageEvidence, ...],
    labels: tuple[Scalable3DObservationTruthLabel, ...],
):
    return create_scalable_3d_identity_evidence_bundle(
        episode_id="episode-test",
        records=records,
        online_d1_records_sha256="sha256:" + "1" * 64,
        online_d2_records_sha256="sha256:" + "2" * 64,
        observation_truth_labels_sha256=(
            hash_scalable_3d_observation_truth_labels(labels)
        ),
    )


def _mapping(result, frame_index: int, global_track_id: str):
    frame = next(item for item in result.frames if item.frame_index == frame_index)
    return next(
        item for item in frame.mappings if item.global_track_id == global_track_id
    )


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _six_state_track(
    global_track_id: str,
    timestamp: float,
    track_state: str,
) -> dict[str, object]:
    return {
        "global_track_id": global_track_id,
        "timestamp": timestamp,
        "state_ned": [1.0, 2.0, -3.0, 0.1, 0.2, -0.3],
        "covariance": [
            [1.0 if row == column else 0.0 for column in range(6)]
            for row in range(6)
        ],
        "track_state": track_state,
    }


def _d1_online_record(
    refs: tuple[ObservationLineageRef, ...],
    *,
    sequence: int = 11,
    timestamp: float = 0.0,
    extra_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "timestamp": timestamp,
        "track_count": 1,
        "tracks": [_six_state_track("D1-001", timestamp, "stable")],
        "observation_lineage": [item.to_dict() for item in refs],
    }
    payload.update(extra_payload or {})
    return {
        "sequence": sequence,
        "topic": "modules.d1.fused_tracks",
        "source": "D1",
        "timestamp": timestamp,
        "schema_version": "d1-scalable3d-fusion-v1",
        "payload": payload,
    }


def _d2_online_record(
    identities: tuple[GlobalTrackLineageEvidence, ...],
    *,
    sequence: int = 21,
    timestamp: float = 0.0,
    id_switch_count: int | None = None,
    id_switch_count_available: bool = False,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "topic": "modules.d2.associated_tracks",
        "source": "D2",
        "timestamp": timestamp,
        "schema_version": "d2-scalable3d-association-v1",
        "payload": {
            "timestamp": timestamp,
            "track_count": len(identities),
            "tracks": [
                _six_state_track(
                    item.global_track_id,
                    timestamp,
                    item.lifecycle_state,
                )
                for item in identities
            ],
            "association": {"timestamp": timestamp},
            "id_switch_count": id_switch_count,
            "id_switch_count_available": id_switch_count_available,
            "identity_lineage_policy": (
                "d2_center_track_to_d1_source_observation_v1"
            ),
            "identity_lineage": [
                {
                    "global_track_id": item.global_track_id,
                    "lifecycle_state": item.lifecycle_state,
                    "association_state": item.association_state,
                    "source_observations": [
                        value.to_dict() for value in item.source_observations
                    ],
                }
                for item in identities
            ],
        },
    }


def _write_file_case(
    tmp_path: Path,
    record: GlobalTrackLineageEvidence,
    *,
    d1_record: dict[str, object] | None = None,
    d2_record: dict[str, object] | None = None,
) -> dict[str, object]:
    d1_path = tmp_path / "d1.jsonl"
    d2_path = tmp_path / "d2.jsonl"
    truth_path = tmp_path / "truth.jsonl"
    evidence_path = tmp_path / "evidence.json"
    _write_jsonl(
        d1_path,
        [d1_record or _d1_online_record(record.source_observations)],
    )
    _write_jsonl(
        d2_path,
        [d2_record or _d2_online_record((record,))],
    )
    _write_jsonl(
        truth_path,
        [
            {
                "schema_version": SCALABLE_3D_EXTERNAL_TRUTH_SCHEMA_VERSION,
                "observation_id": record.source_observations[0].observation_id,
                "measurement_timestamp": (
                    record.source_observations[0].measurement_timestamp
                ),
                "truth_entity_id": "truth-A",
            }
        ],
    )
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id=record.episode_id,
        records=(record,),
        online_d1_records_sha256=sha256_file(d1_path),
        online_d2_records_sha256=sha256_file(d2_path),
        observation_truth_labels_sha256=sha256_file(truth_path),
    )
    evidence_hash = write_scalable_3d_identity_evidence(evidence_path, bundle)
    return {
        "evidence_path": evidence_path,
        "expected_evidence_sha256": evidence_hash,
        "online_d1_records_path": d1_path,
        "online_d2_records_path": d2_path,
        "observation_truth_labels_path": truth_path,
    }


def test_stable_identity_metrics_and_public_artifact_round_trip(
    tmp_path: Path,
) -> None:
    labels = (
        _truth("obs-a-0", "truth-A", 0.0),
        _truth("obs-b-0", "truth-B", 0.0),
        _truth("obs-a-1", "truth-A", 1.0),
        _truth("obs-b-1", "truth-B", 1.0),
    )
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (_ref("obs-a-0", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _evidence(
            0,
            0.0,
            "GT-002",
            (_ref("obs-b-0", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _evidence(1, 1.0, "GT-001", (_ref("obs-a-1", 1.0),)),
        _evidence(1, 1.0, "GT-002", (_ref("obs-b-1", 1.0),)),
    )

    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)

    assert result.schema_version == SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION
    assert result.policy_version.endswith(".v1")
    assert result.audit["identity_heuristics_used"] is False
    assert result.metrics.id_switch_count == 0
    assert result.metrics.track_continuity == pytest.approx(1.0)
    assert result.metrics.identity_continuity == pytest.approx(1.0)
    assert result.metrics.coverage_continuity == pytest.approx(1.0)
    assert result.metrics.duplicate_truth_to_track_count == 0
    assert result.metrics.available is True
    assert all(
        mapping.status == "available"
        for frame in result.frames
        for mapping in frame.mappings
    )

    artifact_path = tmp_path / "identity_evaluation.json"
    artifact_hash = write_scalable_3d_identity_evaluation(
        artifact_path,
        result,
    )
    loaded = load_scalable_3d_identity_evaluation(
        artifact_path,
        expected_sha256=artifact_hash,
        expected_source_hashes=result.source_hashes,
    )
    assert loaded.to_dict() == result.to_dict()


def test_true_id_switch_matches_metrics_recorder_first_assignment_contract() -> None:
    labels = (
        _truth("obs-0", "truth-A", 0.0),
        _truth("obs-1", "truth-A", 1.0),
    )
    records = (
        _evidence(
            0,
            0.0,
            "GT-old",
            (_ref("obs-0", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _evidence(1, 1.0, "GT-new", (_ref("obs-1", 1.0),)),
    )

    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)

    assert result.metrics.available is True
    assert result.metrics.id_switch_count == 1
    assert result.metrics.track_continuity == pytest.approx(0.5)
    assert result.metrics.identity_continuity == pytest.approx(0.5)
    assert result.metrics.coverage_continuity == pytest.approx(1.0)


def test_identity_metric_values_match_metrics_recorder_assignment_semantics() -> None:
    labels = (
        _truth("obs-0", "truth-A", 0.0),
        _truth("obs-1", "truth-A", 1.0),
        _truth("obs-1-duplicate", "truth-A", 1.0),
    )
    records = (
        _evidence(
            0,
            0.0,
            "GT-old",
            (_ref("obs-0", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _evidence(1, 1.0, "GT-new", (_ref("obs-1", 1.0),)),
        _evidence(
            1,
            1.0,
            "GT-duplicate",
            (_ref("obs-1-duplicate", 1.0),),
        ),
    )
    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)

    recorder = MetricsRecorder()
    recorder.record_frame(
        timestamp=0.0,
        truth_ids_present=["truth-A"],
        association_result=AssociationResult(
            timestamp=0.0,
            matched_pairs=[],
            unmatched_track_ids=[],
            unmatched_detection_ids=[],
            ambiguity_score=0.0,
            associator_type="identity-contract-test",
        ),
        assignments=[("truth-A", "GT-old", None)],
        runtime_seconds=0.0,
    )
    recorder.record_frame(
        timestamp=1.0,
        truth_ids_present=["truth-A"],
        association_result=AssociationResult(
            timestamp=1.0,
            matched_pairs=[],
            unmatched_track_ids=[],
            unmatched_detection_ids=[],
            ambiguity_score=0.0,
            associator_type="identity-contract-test",
        ),
        assignments=[
            ("truth-A", "GT-new", None),
            ("truth-A", "GT-duplicate", None),
        ],
        runtime_seconds=0.0,
    )
    expected = recorder.summary()

    assert result.metrics.id_switch_count == expected["id_switch_count"]
    assert result.metrics.identity_continuity == pytest.approx(
        expected["identity_continuity"]
    )
    assert result.metrics.coverage_continuity == pytest.approx(
        expected["coverage_continuity"]
    )
    assert result.metrics.duplicate_truth_to_track_count == expected[
        "duplicate_assignment_count"
    ]


def test_one_truth_to_multiple_tracks_is_audited_as_duplicate() -> None:
    labels = (
        _truth("obs-a", "truth-A", 0.0),
        _truth("obs-b", "truth-A", 0.0),
    )
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (_ref("obs-a", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _evidence(
            0,
            0.0,
            "GT-002",
            (_ref("obs-b", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )

    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)

    assert result.metrics.available is True
    assert result.metrics.duplicate_truth_to_track_count == 1
    assert result.metrics.id_switch_count == 0
    assert result.metrics.confusion_matrix == {
        "truth-A": {"GT-001": 1, "GT-002": 1}
    }


def test_one_track_to_multiple_truth_targets_is_ambiguous_not_guessed() -> None:
    labels = (
        _truth("obs-a", "truth-A", 0.0),
        _truth("obs-b", "truth-B", 0.0),
    )
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (_ref("obs-a", 0.0), _ref("obs-b", 0.0)),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )

    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)
    mapping = _mapping(result, 0, "GT-001")

    assert mapping.status == "ambiguous"
    assert mapping.truth_target_id is None
    assert mapping.candidate_truth_target_ids == ("truth-A", "truth-B")
    assert "multiple_truth_targets_for_global_track" in mapping.unavailable_reasons
    assert result.metrics.available is False
    assert result.metrics.id_switch_count is None
    assert result.metrics.duplicate_truth_to_track_count is None


def test_missing_lineage_keeps_all_identity_values_unavailable() -> None:
    labels = (_truth("obs-a", "truth-A", 0.0),)
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )

    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)
    mapping = _mapping(result, 0, "GT-001")
    summary = result.metrics.to_dict()

    assert mapping.status == "unavailable"
    assert mapping.reason == "source_lineage_missing"
    for name in (
        "id_switch_count",
        "track_continuity",
        "identity_continuity",
        "coverage_continuity",
        "duplicate_truth_to_track_count",
    ):
        assert summary[name] is None
        assert summary[f"{name}_available"] is False


def test_duplicate_and_cross_track_lineage_are_ambiguous() -> None:
    labels = (_truth("obs-a", "truth-A", 0.0),)
    duplicate_ref = _ref("obs-a", 0.0)
    duplicate_within_track = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (duplicate_ref, duplicate_ref),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )
    within_result = evaluate_scalable_3d_identity(
        _bundle(duplicate_within_track, labels),
        labels,
    )
    within_mapping = _mapping(within_result, 0, "GT-001")
    assert within_mapping.status == "ambiguous"
    assert "duplicate_lineage_within_track_frame" in (
        within_mapping.unavailable_reasons
    )

    cross_track = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (duplicate_ref,),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _evidence(
            0,
            0.0,
            "GT-002",
            (duplicate_ref,),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )
    cross_result = evaluate_scalable_3d_identity(
        _bundle(cross_track, labels),
        labels,
    )
    assert all(
        mapping.status == "ambiguous"
        for mapping in cross_result.frames[0].mappings
    )
    assert all(
        "lineage_claimed_by_multiple_tracks" in mapping.unavailable_reasons
        for mapping in cross_result.frames[0].mappings
    )


def test_explicit_replay_generation_is_deduplicated_and_audited() -> None:
    labels = (
        _truth("obs-old", "truth-A", 0.0),
        _truth("obs-current", "truth-A", 1.0),
    )
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (_ref("obs-old", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _evidence(
            1,
            1.0,
            "GT-001",
            (
                _ref("obs-old", 0.0, replay_generation=1),
                _ref("obs-current", 1.0),
            ),
        ),
    )

    result = evaluate_scalable_3d_identity(
        _bundle(records, labels),
        labels,
        lineage_time_window_s=2.0,
    )

    assert _mapping(result, 1, "GT-001").status == "available"
    assert _mapping(result, 1, "GT-001").replayed_lineage_count == 1
    assert result.audit["replayed_lineage_count"] == 1
    assert result.metrics.available is True
    assert result.metrics.id_switch_count == 0


def test_unmarked_repeated_lineage_fails_closed() -> None:
    labels = (
        _truth("obs-old", "truth-A", 0.0),
        _truth("obs-current", "truth-A", 1.0),
    )
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (_ref("obs-old", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _evidence(
            1,
            1.0,
            "GT-001",
            (_ref("obs-old", 0.0), _ref("obs-current", 1.0)),
        ),
    )

    result = evaluate_scalable_3d_identity(
        _bundle(records, labels),
        labels,
        lineage_time_window_s=2.0,
    )

    mapping = _mapping(result, 1, "GT-001")
    assert mapping.status == "unavailable"
    assert "duplicate_lineage_without_replay_marker" in (
        mapping.unavailable_reasons
    )
    assert result.metrics.id_switch_count is None


def test_conflicting_truth_labels_are_ambiguous() -> None:
    labels = (
        _truth("obs-a", "truth-A", 0.0),
        _truth("obs-a", "truth-B", 0.0),
    )
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (_ref("obs-a", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )

    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)
    mapping = _mapping(result, 0, "GT-001")

    assert mapping.status == "ambiguous"
    assert mapping.truth_target_id is None
    assert "conflicting_truth_labels" in mapping.unavailable_reasons
    assert result.metrics.available is False


@pytest.mark.parametrize(
    ("frame_timestamp", "reference_timestamp", "label_timestamp", "window", "reason"),
    [
        (0.0, 0.0, 0.2, 1.0, "truth_label_timestamp_mismatch"),
        (0.0, 0.2, 0.2, 1.0, "source_observation_from_future"),
        (2.0, 0.0, 0.0, 1.0, "source_observation_outside_lineage_window"),
    ],
)
def test_time_inconsistency_is_unavailable(
    frame_timestamp: float,
    reference_timestamp: float,
    label_timestamp: float,
    window: float,
    reason: str,
) -> None:
    labels = (_truth("obs-a", "truth-A", label_timestamp),)
    records = (
        _evidence(
            0,
            frame_timestamp,
            "GT-001",
            (_ref("obs-a", reference_timestamp),),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )

    result = evaluate_scalable_3d_identity(
        _bundle(records, labels),
        labels,
        lineage_time_window_s=window,
    )

    mapping = _mapping(result, 0, "GT-001")
    assert mapping.status == "unavailable"
    assert reason in mapping.unavailable_reasons
    assert result.metrics.track_continuity is None


def test_track_reappearance_after_dropped_lifecycle_is_unavailable() -> None:
    labels = (
        _truth("obs-a-0", "truth-A", 0.0),
        _truth("obs-a-2", "truth-A", 2.0),
    )
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (_ref("obs-a-0", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
        _evidence(
            1,
            1.0,
            "GT-001",
            (),
            association_state="dropped",
            lifecycle_state="dropped",
        ),
        _evidence(
            2,
            2.0,
            "GT-001",
            (_ref("obs-a-2", 2.0),),
            lifecycle_state="confirmed",
        ),
    )

    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)
    mapping = _mapping(result, 2, "GT-001")

    assert mapping.status == "unavailable"
    assert "track_reappeared_after_drop" in mapping.unavailable_reasons
    assert "invalid_track_lifecycle_transition" in mapping.unavailable_reasons
    assert result.metrics.id_switch_count is None


def test_no_truth_sidecar_never_returns_zero_identity_metrics() -> None:
    labels: tuple[Scalable3DObservationTruthLabel, ...] = ()
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (_ref("obs-a", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )

    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)
    summary = result.metrics.to_dict()

    assert result.metrics.available is False
    assert result.metrics.reason == "observation_truth_labels_unavailable"
    assert summary["id_switch_count"] is None
    assert summary["track_continuity"] is None
    assert summary["duplicate_assignment_count"] is None


def test_file_entry_verifies_hashes_sequences_and_online_truth_isolation(
    tmp_path: Path,
) -> None:
    d1_path = tmp_path / "d1_online.jsonl"
    d2_path = tmp_path / "d2_online.jsonl"
    truth_path = tmp_path / "offline_truth_labels.jsonl"
    records = (
        _evidence(
            0,
            0.0,
            "GT-001",
            (_ref("obs-a", 0.0),),
            association_state="created",
            lifecycle_state="tentative",
        ),
    )
    _write_jsonl(
        d1_path,
        [_d1_online_record(records[0].source_observations)],
    )
    _write_jsonl(
        d2_path,
        [_d2_online_record(records)],
    )
    _write_jsonl(
        truth_path,
        [
            {
                "schema_version": SCALABLE_3D_EXTERNAL_TRUTH_SCHEMA_VERSION,
                "observation_id": "obs-a",
                "measurement_timestamp": 0.0,
                "truth_entity_id": "truth-A",
            }
        ],
    )
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="episode-test",
        records=records,
        online_d1_records_sha256=sha256_file(d1_path),
        online_d2_records_sha256=sha256_file(d2_path),
        observation_truth_labels_sha256=sha256_file(truth_path),
    )
    evidence_path = tmp_path / "d2_identity_evidence.json"
    evidence_hash = write_scalable_3d_identity_evidence(evidence_path, bundle)

    result = evaluate_scalable_3d_identity_files(
        evidence_path=evidence_path,
        expected_evidence_sha256=evidence_hash,
        online_d1_records_path=d1_path,
        online_d2_records_path=d2_path,
        observation_truth_labels_path=truth_path,
    )

    assert result.metrics.available is True
    assert result.metrics.id_switch_count == 0
    assert result.audit["online_truth_isolation_verified"] is True
    assert result.audit["source_record_semantics_verified"] is True
    assert result.audit["six_dimensional_track_records_verified"] is True
    assert result.audit["evidence_completeness_verified"] is True
    assert result.audit["source_verification"] == (
        "raw_source_hashes_and_record_sequences_verified"
    )
    assert result.source_hashes["online_d1_records"] == sha256_file(d1_path)

    truth_path.write_text(
        truth_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="observation_truth_labels sha256 mismatch"):
        evaluate_scalable_3d_identity_files(
            evidence_path=evidence_path,
            expected_evidence_sha256=evidence_hash,
            online_d1_records_path=d1_path,
            online_d2_records_path=d2_path,
            observation_truth_labels_path=truth_path,
        )


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("non_six_state", "six-state"),
        ("foreign_global_track", "absent from source records"),
        ("online_idsw_value", "must be null and unavailable"),
    ],
)
def test_file_entry_binds_evidence_to_six_state_d2_owned_records(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    record = _evidence(
        0,
        0.0,
        "GT-001",
        (_ref("obs-a", 0.0),),
        association_state="created",
        lifecycle_state="tentative",
    )
    d2_record = _d2_online_record((record,))
    payload = d2_record["payload"]
    assert isinstance(payload, dict)
    tracks = payload["tracks"]
    identities = payload["identity_lineage"]
    assert isinstance(tracks, list)
    assert isinstance(identities, list)
    if corruption == "non_six_state":
        tracks[0]["state_ned"] = [1.0, 2.0, 3.0]
    elif corruption == "foreign_global_track":
        tracks[0]["global_track_id"] = "GT-foreign"
        identities[0]["global_track_id"] = "GT-foreign"
    else:
        payload["id_switch_count"] = 0

    arguments = _write_file_case(
        tmp_path,
        record,
        d2_record=d2_record,
    )
    with pytest.raises(ValueError, match=message):
        evaluate_scalable_3d_identity_files(**arguments)


def test_public_loader_rejects_contradictory_idsw_availability(
    tmp_path: Path,
) -> None:
    labels = (_truth("obs-a", "truth-A", 0.0),)
    record = _evidence(
        0,
        0.0,
        "GT-001",
        (_ref("obs-a", 0.0),),
        association_state="created",
        lifecycle_state="tentative",
    )
    result = evaluate_scalable_3d_identity(_bundle((record,), labels), labels)
    payload = result.to_dict()
    payload["metrics"]["id_switch_count_available"] = False
    path = tmp_path / "contradictory_identity_evaluation.json"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="availability contradicts"):
        load_scalable_3d_identity_evaluation(
            path,
            expected_sha256=sha256_file(path),
        )


def test_online_truth_leakage_and_unknown_sequence_fail_closed(
    tmp_path: Path,
) -> None:
    d1_path = tmp_path / "d1_online.jsonl"
    d2_path = tmp_path / "d2_online.jsonl"
    truth_path = tmp_path / "truth.jsonl"
    record = _evidence(
        0,
        0.0,
        "GT-001",
        (_ref("obs-a", 0.0),),
        association_state="created",
        lifecycle_state="tentative",
        d1_sequences=(999,),
    )
    _write_jsonl(
        d1_path,
        [
            _d1_online_record(
                record.source_observations,
                extra_payload={
                    "actor_name": "forbidden-simulator-identity",
                },
            )
        ],
    )
    _write_jsonl(
        d2_path,
        [_d2_online_record((record,))],
    )
    _write_jsonl(
        truth_path,
        [
            {
                "schema_version": SCALABLE_3D_EXTERNAL_TRUTH_SCHEMA_VERSION,
                "observation_id": "obs-a",
                "measurement_timestamp": 0.0,
                "truth_entity_id": "truth-A",
            }
        ],
    )
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="episode-test",
        records=(record,),
        online_d1_records_sha256=sha256_file(d1_path),
        online_d2_records_sha256=sha256_file(d2_path),
        observation_truth_labels_sha256=sha256_file(truth_path),
    )
    evidence_path = tmp_path / "evidence.json"
    evidence_hash = write_scalable_3d_identity_evidence(evidence_path, bundle)

    with pytest.raises(ValueError, match="online identity isolation audit failed"):
        evaluate_scalable_3d_identity_files(
            evidence_path=evidence_path,
            expected_evidence_sha256=evidence_hash,
            online_d1_records_path=d1_path,
            online_d2_records_path=d2_path,
            observation_truth_labels_path=truth_path,
        )

    _write_jsonl(
        d1_path,
        [_d1_online_record(record.source_observations)],
    )
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="episode-test",
        records=(record,),
        online_d1_records_sha256=sha256_file(d1_path),
        online_d2_records_sha256=sha256_file(d2_path),
        observation_truth_labels_sha256=sha256_file(truth_path),
    )
    evidence_hash = write_scalable_3d_identity_evidence(evidence_path, bundle)
    with pytest.raises(ValueError, match="matching D1 sequences"):
        evaluate_scalable_3d_identity_files(
            evidence_path=evidence_path,
            expected_evidence_sha256=evidence_hash,
            online_d1_records_path=d1_path,
            online_d2_records_path=d2_path,
            observation_truth_labels_path=truth_path,
        )


def test_input_sized_evaluation_has_no_baseline_cardinality_assumption() -> None:
    target_count = 37
    labels = tuple(
        _truth(f"obs-{frame}-{index}", f"truth-{index}", float(frame))
        for frame in range(2)
        for index in range(target_count)
    )
    records = tuple(
        _evidence(
            frame,
            float(frame),
            f"GT-{index}",
            (_ref(f"obs-{frame}-{index}", float(frame)),),
            association_state="created" if frame == 0 else "matched",
            lifecycle_state="tentative" if frame == 0 else "confirmed",
        )
        for frame in range(2)
        for index in range(target_count)
    )

    result = evaluate_scalable_3d_identity(_bundle(records, labels), labels)

    assert sum(len(frame.mappings) for frame in result.frames) == 2 * target_count
    assert len(result.metrics.confusion_matrix or {}) == target_count
    assert result.metrics.id_switch_count == 0
    assert result.metrics.track_continuity == pytest.approx(1.0)


def test_schema_and_evaluator_truth_boundary_reject_global_track_truth_labels() -> None:
    with pytest.raises(ValueError, match="unsupported fields"):
        Scalable3DObservationTruthLabel.from_mapping(
            {
                "schema_version": SCALABLE_3D_EXTERNAL_TRUTH_SCHEMA_VERSION,
                "observation_id": "obs-a",
                "measurement_timestamp": 0.0,
                "truth_entity_id": "truth-A",
                "global_track_id": "GT-must-not-be-in-truth-sidecar",
            }
        )

    with pytest.raises(ValueError, match="unsupported identity evidence schema"):
        GlobalTrackLineageEvidence.from_mapping(
            {
                "schema_version": "d2.scalable3d_identity_evidence.v0",
                "episode_id": "episode-test",
                "frame_index": 0,
                "frame_timestamp": 0.0,
                "global_track_id": "GT-001",
                "lifecycle_state": "tentative",
                "association_state": "created",
                "source_observations": [],
                "d1_record_sequences": [11],
                "d2_record_sequence": 21,
            }
        )

    assert SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION.endswith(".v1")
