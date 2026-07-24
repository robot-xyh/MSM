from __future__ import annotations

import json
from pathlib import Path

import pytest

from d2_data_association import (
    OBSERVATION_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
    OBSERVATION_TRUTH_DISPOSITION_TARGET,
    OBSERVATION_TRUTH_DISPOSITION_UNKNOWN,
    SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION,
    SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION_V1,
    GlobalTrackLineageEvidence,
    ObservationLineageRef,
    Scalable3DIdentityEvaluation,
    Scalable3DObservationTruthLabel,
    build_scalable_3d_identity_blocker_diagnostics,
    create_scalable_3d_identity_evidence_bundle,
    evaluate_scalable_3d_identity,
    hash_scalable_3d_observation_truth_labels,
    load_scalable_3d_observation_truth_labels,
    write_scalable_3d_observation_truth_labels,
)


_SHA = "sha256:" + "a" * 64


def _ref(observation_id: str, timestamp: float = 0.0) -> ObservationLineageRef:
    return ObservationLineageRef(
        observation_id=observation_id,
        measurement_timestamp=timestamp,
        source_lineage=("sensor", observation_id),
    )


def _record(
    global_track_id: str,
    observation_ids: tuple[str, ...],
    *,
    timestamp: float = 0.0,
    association_state: str = "created",
) -> GlobalTrackLineageEvidence:
    return GlobalTrackLineageEvidence(
        episode_id="truth-disposition-test",
        frame_index=0,
        frame_timestamp=timestamp,
        global_track_id=global_track_id,
        lifecycle_state="tentative",
        association_state=association_state,
        source_observations=tuple(
            _ref(observation_id, timestamp)
            for observation_id in observation_ids
        ),
        d1_record_sequences=(1,),
        d2_record_sequence=2,
    )


def _evaluate(records, labels):
    labels = tuple(labels)
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="truth-disposition-test",
        records=tuple(records),
        online_d1_records_sha256="sha256:" + "1" * 64,
        online_d2_records_sha256="sha256:" + "2" * 64,
        observation_truth_labels_sha256=(
            hash_scalable_3d_observation_truth_labels(labels)
        ),
    )
    return bundle, evaluate_scalable_3d_identity(bundle, labels), labels


def _mapping(evaluation, global_track_id: str):
    return next(
        mapping
        for mapping in evaluation.frames[0].mappings
        if mapping.global_track_id == global_track_id
    )


def _verified_evaluation(
    evaluation,
) -> Scalable3DIdentityEvaluation:
    audit = dict(evaluation.audit)
    audit["online_truth_isolation_verified"] = True
    return Scalable3DIdentityEvaluation(
        episode_id=evaluation.episode_id,
        source_hashes=evaluation.source_hashes,
        frames=evaluation.frames,
        metrics=evaluation.metrics,
        partial_identity_diagnostics=evaluation.partial_identity_diagnostics,
        configuration=evaluation.configuration,
        audit=audit,
    )


def test_v1_target_only_round_trip_normalizes_to_v2(tmp_path: Path) -> None:
    v1_record = {
        "schema_version": SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION_V1,
        "observation_id": "obs-target",
        "measurement_timestamp": 1.25,
        "truth_target_id": "truth-A",
    }

    label = Scalable3DObservationTruthLabel.from_mapping(v1_record)

    assert label.disposition == OBSERVATION_TRUTH_DISPOSITION_TARGET
    assert label.source_schema_version == (
        SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION_V1
    )
    assert label.to_source_dict() == v1_record
    assert label.to_dict() == {
        "schema_version": SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION,
        "observation_id": "obs-target",
        "measurement_timestamp": 1.25,
        "disposition": OBSERVATION_TRUTH_DISPOSITION_TARGET,
        "truth_target_id": "truth-A",
    }

    path = tmp_path / "normalized.jsonl"
    digest = write_scalable_3d_observation_truth_labels(path, (v1_record,))
    loaded = load_scalable_3d_observation_truth_labels(
        path,
        expected_sha256=digest,
    )

    assert loaded[0].to_dict() == label.to_dict()
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == (
        SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION
    )


def test_v2_target_false_alarm_and_unknown_round_trip(
    tmp_path: Path,
) -> None:
    labels = (
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-target",
            measurement_timestamp=0.0,
            truth_target_id="truth-A",
        ),
        Scalable3DObservationTruthLabel.known_false_alarm(
            observation_id="obs-false-alarm",
            measurement_timestamp=0.0,
        ),
        Scalable3DObservationTruthLabel.unknown(
            observation_id="obs-unknown",
            measurement_timestamp=0.0,
        ),
    )
    path = tmp_path / "v2.jsonl"

    digest = write_scalable_3d_observation_truth_labels(path, labels)
    loaded = load_scalable_3d_observation_truth_labels(
        path,
        expected_sha256=digest,
    )

    assert tuple(item.to_dict() for item in loaded) == tuple(
        item.to_dict() for item in labels
    )
    assert [item.disposition for item in loaded] == [
        OBSERVATION_TRUTH_DISPOSITION_TARGET,
        OBSERVATION_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
        OBSERVATION_TRUTH_DISPOSITION_UNKNOWN,
    ]
    assert loaded[1].truth_target_id is None
    assert loaded[2].truth_target_id is None


@pytest.mark.parametrize(
    "payload",
    [
        {
            "schema_version": SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION,
            "observation_id": "obs-target",
            "measurement_timestamp": 0.0,
            "disposition": OBSERVATION_TRUTH_DISPOSITION_TARGET,
        },
        {
            "schema_version": SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION,
            "observation_id": "obs-fa",
            "measurement_timestamp": 0.0,
            "disposition": (
                OBSERVATION_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM
            ),
            "truth_target_id": "must-not-exist",
        },
        {
            "schema_version": SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION,
            "observation_id": "obs-unknown",
            "measurement_timestamp": 0.0,
            "disposition": OBSERVATION_TRUTH_DISPOSITION_UNKNOWN,
            "truth_target_id": "must-not-exist",
        },
    ],
)
def test_v2_disposition_and_target_identity_are_mutually_consistent(
    payload,
) -> None:
    with pytest.raises(ValueError, match="truth_target_id"):
        Scalable3DObservationTruthLabel.from_mapping(payload)


def test_target_plus_false_alarm_keeps_target_and_pure_false_alarm_is_excluded(
) -> None:
    labels = (
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-target",
            measurement_timestamp=0.0,
            truth_target_id="truth-A",
        ),
        Scalable3DObservationTruthLabel.known_false_alarm(
            observation_id="obs-fa-mixed",
            measurement_timestamp=0.0,
        ),
        Scalable3DObservationTruthLabel.known_false_alarm(
            observation_id="obs-fa-only",
            measurement_timestamp=0.0,
        ),
    )
    records = (
        _record("GT-target", ("obs-target", "obs-fa-mixed")),
        _record("GT-false-alarm", ("obs-fa-only",)),
    )

    _, evaluation, _ = _evaluate(records, labels)
    target_mapping = _mapping(evaluation, "GT-target")
    false_alarm_mapping = _mapping(evaluation, "GT-false-alarm")
    partial = evaluation.partial_identity_diagnostics

    assert target_mapping.status == "available"
    assert target_mapping.truth_target_id == "truth-A"
    assert target_mapping.candidate_truth_target_ids == ("truth-A",)
    assert false_alarm_mapping.status == "excluded"
    assert false_alarm_mapping.reason == "known_false_alarm_only"
    assert false_alarm_mapping.truth_target_id is None
    assert evaluation.metrics.available is True
    assert evaluation.metrics.id_switch_count == 0
    assert evaluation.audit["target_with_known_false_alarm_mapping_count"] == 1
    assert evaluation.audit["known_false_alarm_only_mapping_count"] == 1
    assert partial is not None
    assert partial.total_mapping_count == 2
    assert partial.scored_mapping_count == 1
    assert partial.non_scored_mapping_count == 1


def test_nonobserved_false_alarm_group_is_not_counted_as_persisted_exclusion(
) -> None:
    false_alarm = Scalable3DObservationTruthLabel.known_false_alarm(
        observation_id="obs-fa-unmatched",
        measurement_timestamp=0.0,
    )

    _, evaluation, _ = _evaluate(
        (
            _record(
                "GT-false-alarm-unmatched",
                ("obs-fa-unmatched",),
                association_state="unmatched",
            ),
        ),
        (false_alarm,),
    )
    mapping = _mapping(evaluation, "GT-false-alarm-unmatched")

    assert mapping.status == "unavailable"
    assert mapping.reason == "lineage_on_unassigned_track"
    assert {
        "lineage_on_unassigned_track",
        "track_not_assigned_in_frame",
    }.issubset(mapping.unavailable_reasons)
    assert "known_false_alarm_only" not in mapping.unavailable_reasons
    assert evaluation.audit["known_false_alarm_only_mapping_count"] == 0
    assert evaluation.audit["excluded_mapping_count"] == 0


def test_unknown_disposition_keeps_candidate_but_blocks_strict_metrics() -> None:
    labels = (
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-target",
            measurement_timestamp=0.0,
            truth_target_id="truth-A",
        ),
        Scalable3DObservationTruthLabel.unknown(
            observation_id="obs-unknown",
            measurement_timestamp=0.0,
        ),
    )

    _, evaluation, _ = _evaluate(
        (_record("GT-unknown", ("obs-target", "obs-unknown")),),
        labels,
    )
    mapping = _mapping(evaluation, "GT-unknown")

    assert mapping.status == "unavailable"
    assert mapping.candidate_truth_target_ids == ("truth-A",)
    assert "truth_label_unknown" in mapping.unavailable_reasons
    assert evaluation.metrics.available is False
    assert evaluation.metrics.reason == "truth_label_unknown"
    assert evaluation.metrics.id_switch_count is None


def test_conflicting_dispositions_and_timestamp_mismatch_fail_closed() -> None:
    conflict_labels = (
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-conflict",
            measurement_timestamp=0.0,
            truth_target_id="truth-A",
        ),
        Scalable3DObservationTruthLabel.known_false_alarm(
            observation_id="obs-conflict",
            measurement_timestamp=0.0,
        ),
    )
    _, conflict_evaluation, _ = _evaluate(
        (_record("GT-conflict", ("obs-conflict",)),),
        conflict_labels,
    )
    conflict_mapping = _mapping(conflict_evaluation, "GT-conflict")

    assert conflict_mapping.status == "ambiguous"
    assert "conflicting_truth_labels" in (
        conflict_mapping.unavailable_reasons
    )
    assert conflict_evaluation.metrics.available is False

    timestamp_label = Scalable3DObservationTruthLabel.target(
        observation_id="obs-time",
        measurement_timestamp=1.0,
        truth_target_id="truth-A",
    )
    _, timestamp_evaluation, _ = _evaluate(
        (_record("GT-time", ("obs-time",), timestamp=0.0),),
        (timestamp_label,),
    )
    timestamp_mapping = _mapping(timestamp_evaluation, "GT-time")

    assert timestamp_mapping.status == "unavailable"
    assert "truth_label_timestamp_mismatch" in (
        timestamp_mapping.unavailable_reasons
    )
    assert timestamp_evaluation.metrics.available is False


def test_v2_sidecar_and_in_memory_evaluation_reject_hash_tampering(
    tmp_path: Path,
) -> None:
    target = Scalable3DObservationTruthLabel.target(
        observation_id="obs-a",
        measurement_timestamp=0.0,
        truth_target_id="truth-A",
    )
    path = tmp_path / "truth.jsonl"
    digest = write_scalable_3d_observation_truth_labels(path, (target,))
    path.write_text(
        path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sha256 mismatch"):
        load_scalable_3d_observation_truth_labels(
            path,
            expected_sha256=digest,
        )

    record = _record("GT-001", ("obs-a",))
    bundle, _, _ = _evaluate((record,), (target,))
    false_alarm = Scalable3DObservationTruthLabel.known_false_alarm(
        observation_id="obs-a",
        measurement_timestamp=0.0,
    )
    with pytest.raises(ValueError, match="truth hash mismatch"):
        evaluate_scalable_3d_identity(bundle, (false_alarm,))


def test_diagnostics_publish_only_target_d1_mappings_and_audit_false_alarm(
) -> None:
    labels = (
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-target",
            measurement_timestamp=0.0,
            truth_target_id="truth-A",
        ),
        Scalable3DObservationTruthLabel.known_false_alarm(
            observation_id="obs-fa",
            measurement_timestamp=0.0,
        ),
    )
    records = (_record("GT-001", ("obs-target", "obs-fa")),)
    bundle, evaluation, normalized_labels = _evaluate(records, labels)
    d1_evidence = {
        "record_count": 2,
        "records": [
            {
                "observation_id": observation_id,
                "measurement_timestamp": 0.0,
                "availability": {
                    "estimate": {"available": True, "reason": None}
                },
            }
            for observation_id in ("obs-target", "obs-fa")
        ],
    }

    diagnostics = build_scalable_3d_identity_blocker_diagnostics(
        bundle,
        _verified_evaluation(evaluation),
        normalized_labels,
        identity_evaluation_sha256=_SHA,
        d1_consistency_evidence=d1_evidence,
        d1_consistency_evidence_sha256="sha256:" + "b" * 64,
    )
    d1_audit = diagnostics.d1_lineage_mapping_audit

    assert diagnostics.target_with_known_false_alarm_mapping_count == 1
    assert diagnostics.known_false_alarm_only_mapping_count == 0
    assert len(diagnostics.lineage_disposition_audit) == 1
    assert d1_audit is not None
    assert d1_audit["d1_consumable"] is True
    assert d1_audit["target_observation_count"] == 1
    assert d1_audit["known_false_alarm_exclusion_count"] == 1
    assert len(d1_audit["mapping_records"]) == 1
    assert d1_audit["mapping_records"][0]["truth_id"] == "truth-A"


def test_unknown_disposition_blocks_d1_mapping_records() -> None:
    unknown = Scalable3DObservationTruthLabel.unknown(
        observation_id="obs-unknown",
        measurement_timestamp=0.0,
    )
    record = _record("GT-001", ("obs-unknown",))
    bundle, evaluation, labels = _evaluate((record,), (unknown,))

    diagnostics = build_scalable_3d_identity_blocker_diagnostics(
        bundle,
        _verified_evaluation(evaluation),
        labels,
        identity_evaluation_sha256=_SHA,
        d1_consistency_evidence={
            "record_count": 1,
            "records": [
                {
                    "observation_id": "obs-unknown",
                    "measurement_timestamp": 0.0,
                    "availability": {
                        "estimate": {"available": True, "reason": None}
                    },
                }
            ],
        },
        d1_consistency_evidence_sha256="sha256:" + "b" * 64,
    )
    d1_audit = diagnostics.d1_lineage_mapping_audit

    assert d1_audit is not None
    assert d1_audit["d1_consumable"] is False
    assert d1_audit["reason"] == "truth_label_unknown"
    assert d1_audit["mapping_records"] == []
