from __future__ import annotations

import json
from pathlib import Path

import pytest

from d2_data_association import (
    SCALABLE_3D_IDENTITY_COMMITMENT_AUDIT_SCHEMA_VERSION,
    SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1,
    SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V2,
    SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V1,
    SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V2,
    GlobalTrackLineageEvidence,
    IdentityCommitmentState,
    IdentityEvidenceCommitment,
    ObservationLineageRef,
    Scalable3DObservationTruthLabel,
    create_scalable_3d_identity_evidence_bundle,
    evaluate_scalable_3d_identity,
    hash_scalable_3d_observation_truth_labels,
    load_scalable_3d_identity_evaluation,
    sha256_file,
)


_SHA256_A = f"sha256:{'a' * 64}"
_SHA256_B = f"sha256:{'b' * 64}"


def _committed(
    track_id: str,
    association_state: str,
    timestamp: float,
    observation_id: str,
) -> IdentityEvidenceCommitment:
    return IdentityEvidenceCommitment(
        global_track_id=track_id,
        association_state=association_state,
        identity_commitment_state=IdentityCommitmentState.COMMITTED,
        reason="fresh_original_observation_accepted",
        state_timestamp=timestamp,
        commitment_generation=2,
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        source_observation_evidence_key=f"evidence:{observation_id}",
        source_observation_evidence_generation=0,
        source_observation_disposition="target_candidate",
        lease_expired_timestamp=max(timestamp - 0.1, 0.0),
        lease_expiration_reason="soft_deadline_reached",
    )


def _after_hold(
    track_id: str,
    association_state: str,
    timestamp: float,
    *,
    reason: str = "ambiguity_hold_released_without_fresh_original_observation",
    recovery_blocker_count: int = 1,
    recovery_not_before_measurement_timestamp: float | None = None,
    recovery_blocker_overflow: bool = False,
) -> IdentityEvidenceCommitment:
    return IdentityEvidenceCommitment(
        global_track_id=track_id,
        association_state=association_state,
        identity_commitment_state=(
            IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD
        ),
        reason=reason,
        state_timestamp=timestamp,
        commitment_generation=1,
        measurement_timestamp=timestamp - 0.2,
        arrival_timestamp=timestamp - 0.19,
        ambiguity_component_key="component-1",
        ambiguity_evidence_id="component-evidence-1",
        ambiguity_component_generation=4,
        publisher_node_id="D1_FUSION",
        publisher_epoch="epoch-1",
        lease_first_seen_timestamp=timestamp - 0.3,
        lease_soft_deadline=timestamp - 0.1,
        lease_hard_deadline=timestamp + 0.1,
        lease_expired_timestamp=timestamp - 0.1,
        lease_expiration_reason="soft_deadline_reached",
        recovery_blocker_count=recovery_blocker_count,
        recovery_not_before_measurement_timestamp=(
            timestamp - 0.2
            if recovery_not_before_measurement_timestamp is None
            else recovery_not_before_measurement_timestamp
        ),
        recovery_blocker_overflow=recovery_blocker_overflow,
    )


def _record(
    *,
    track_id: str,
    frame_index: int,
    association_state: str,
    commitment: IdentityEvidenceCommitment,
    observation_id: str | None,
) -> GlobalTrackLineageEvidence:
    refs = (
        ()
        if observation_id is None
        else (
            ObservationLineageRef(
                observation_id=observation_id,
                measurement_timestamp=float(frame_index),
            ),
        )
    )
    return GlobalTrackLineageEvidence(
        schema_version=SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V2,
        episode_id="episode-commitment-v2",
        frame_index=frame_index,
        frame_timestamp=float(frame_index),
        global_track_id=track_id,
        lifecycle_state="confirmed",
        association_state=association_state,
        identity_commitment=commitment,
        source_observations=refs,
    )


def _evaluate_commitment_audit_fixture():
    records = (
        _record(
            track_id="GT3D-000001",
            frame_index=0,
            association_state="created",
            commitment=_committed(
                "GT3D-000001",
                "created",
                0.0,
                "obs-0",
            ),
            observation_id="obs-0",
        ),
        _record(
            track_id="GT3D-000001",
            frame_index=1,
            association_state="unmatched",
            commitment=_after_hold(
                "GT3D-000001",
                "unmatched",
                1.0,
                reason="identity_recovery_blocked_reused_hold_evidence",
                recovery_blocker_count=2,
                recovery_not_before_measurement_timestamp=0.5,
                recovery_blocker_overflow=True,
            ),
            observation_id=None,
        ),
        _record(
            track_id="GT3D-000001",
            frame_index=2,
            association_state="matched",
            commitment=_after_hold(
                "GT3D-000001",
                "matched",
                2.0,
                reason=(
                    "identity_recovery_blocked_"
                    "measurement_not_newer_than_hold"
                ),
                recovery_blocker_count=4,
                recovery_not_before_measurement_timestamp=1.25,
                recovery_blocker_overflow=True,
            ),
            observation_id=None,
        ),
        _record(
            track_id="GT3D-000001",
            frame_index=3,
            association_state="matched",
            commitment=_committed(
                "GT3D-000001",
                "matched",
                3.0,
                "obs-3",
            ),
            observation_id="obs-3",
        ),
    )
    labels = (
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-0",
            truth_target_id="TGT-001",
            measurement_timestamp=0.0,
        ),
        Scalable3DObservationTruthLabel.target(
            observation_id="truth-presence-1",
            truth_target_id="TGT-001",
            measurement_timestamp=1.0,
        ),
        Scalable3DObservationTruthLabel.target(
            observation_id="truth-presence-2",
            truth_target_id="TGT-001",
            measurement_timestamp=2.0,
        ),
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-3",
            truth_target_id="TGT-001",
            measurement_timestamp=3.0,
        ),
    )
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="episode-commitment-v2",
        records=records,
        online_d1_records_sha256=_SHA256_A,
        online_d2_records_sha256=_SHA256_B,
        observation_truth_labels_sha256=(
            hash_scalable_3d_observation_truth_labels(labels)
        ),
    )
    return evaluate_scalable_3d_identity(bundle, labels)


def test_v1_round_trip_remains_unchanged_and_rejects_v2_fields() -> None:
    record = GlobalTrackLineageEvidence(
        schema_version=SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V1,
        episode_id="legacy",
        frame_index=0,
        frame_timestamp=0.0,
        global_track_id="GT3D-000001",
        lifecycle_state="tentative",
        association_state="created",
        source_observations=(
            ObservationLineageRef(
                observation_id="obs-legacy",
                measurement_timestamp=0.0,
            ),
        ),
    )

    assert "identity_commitment" not in record.to_dict()
    assert (
        GlobalTrackLineageEvidence.from_mapping(record.to_dict()).to_dict()
        == record.to_dict()
    )
    with pytest.raises(ValueError, match="v1 cannot carry"):
        GlobalTrackLineageEvidence(
            **{
                **record.to_dict(),
                "identity_commitment": _committed(
                    "GT3D-000001",
                    "created",
                    0.0,
                    "obs-legacy",
                ),
            }
        )


def test_v2_uncommitted_record_cannot_bind_candidate_observations() -> None:
    commitment = _after_hold("GT3D-000001", "matched", 1.0)

    with pytest.raises(ValueError, match="cannot bind observations"):
        GlobalTrackLineageEvidence(
            schema_version=SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V2,
            episode_id="episode",
            frame_index=1,
            frame_timestamp=1.0,
            global_track_id="GT3D-000001",
            lifecycle_state="confirmed",
            association_state="matched",
            identity_commitment=commitment,
            source_observations=(
                ObservationLineageRef(
                    observation_id="forbidden-candidate",
                    measurement_timestamp=1.0,
                ),
            ),
        )


@pytest.mark.parametrize("disposition", ["known_false_alarm", "unknown"])
def test_noncommittable_disposition_cannot_construct_committed_identity(
    disposition: str,
) -> None:
    with pytest.raises(ValueError, match="cannot commit identity"):
        IdentityEvidenceCommitment(
            global_track_id="GT3D-000001",
            association_state="matched",
            identity_commitment_state=IdentityCommitmentState.COMMITTED,
            reason="invalid_false_alarm_recovery",
            state_timestamp=1.0,
            measurement_timestamp=1.0,
            arrival_timestamp=1.01,
            source_observation_evidence_key="known-false-alarm",
            source_observation_evidence_generation=0,
            source_observation_disposition=disposition,
        )


def test_v2_metrics_remain_available_across_uncommitted_gap_and_count_switch() -> None:
    records = (
        _record(
            track_id="GT3D-000001",
            frame_index=0,
            association_state="created",
            commitment=_committed(
                "GT3D-000001",
                "created",
                0.0,
                "obs-0",
            ),
            observation_id="obs-0",
        ),
        _record(
            track_id="GT3D-000001",
            frame_index=1,
            association_state="unmatched",
            commitment=_after_hold(
                "GT3D-000001",
                "unmatched",
                1.0,
            ),
            observation_id=None,
        ),
        _record(
            track_id="GT3D-000002",
            frame_index=2,
            association_state="created",
            commitment=_committed(
                "GT3D-000002",
                "created",
                2.0,
                "obs-2",
            ),
            observation_id="obs-2",
        ),
    )
    labels = (
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-0",
            truth_target_id="TGT-001",
            measurement_timestamp=0.0,
        ),
        Scalable3DObservationTruthLabel.target(
            observation_id="truth-presence-gap",
            truth_target_id="TGT-001",
            measurement_timestamp=1.0,
        ),
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-2",
            truth_target_id="TGT-001",
            measurement_timestamp=2.0,
        ),
    )
    truth_hash = hash_scalable_3d_observation_truth_labels(labels)
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="episode-commitment-v2",
        records=records,
        online_d1_records_sha256=_SHA256_A,
        online_d2_records_sha256=_SHA256_B,
        observation_truth_labels_sha256=truth_hash,
    )

    evaluation = evaluate_scalable_3d_identity(bundle, labels)

    assert bundle.schema_version == (
        SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V2
    )
    assert evaluation.metrics.available is True
    assert evaluation.metrics.id_switch_count == 1
    assert evaluation.metrics.coverage_continuity == pytest.approx(2.0 / 3.0)
    assert evaluation.metrics.identity_continuity == pytest.approx(1.0 / 3.0)
    assert evaluation.frames[1].mappings[0].status == "uncommitted"
    assert evaluation.frames[1].mappings[0].source_observation_ids == ()
    assert evaluation.audit["identity_commitment_coverage"] == pytest.approx(
        2.0 / 3.0
    )
    assert evaluation.audit["uncommitted_mapping_count"] == 1
    assert evaluation.audit["uncommitted_candidate_binding_count"] == 0
    assert evaluation.audit["identity_metrics_blocking_reasons"] == []


def test_v2_evaluator_audit_exposes_strict_recovery_aggregates() -> None:
    evaluation = _evaluate_commitment_audit_fixture()
    audit = evaluation.audit

    assert (
        evaluation.schema_version
        == SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V2
    )
    assert len(evaluation.identity_evidence_records) == 4
    assert audit["identity_commitment_audit_schema_version"] == (
        SCALABLE_3D_IDENTITY_COMMITMENT_AUDIT_SCHEMA_VERSION
    )
    assert audit["identity_commitment_denominator_policy"] == {
        "all_records": "all_persisted_v2_identity_evidence_records",
        "observed_records": (
            "v2_identity_evidence_records_with_association_state_created_or_matched"
        ),
        "committed": "identity_commitment_state_equals_committed",
        "uncommitted": "all_other_v2_identity_commitment_states",
        "recovery_blocker_count": (
            "all_v2_identity_evidence_records_including_zero"
        ),
        "watermark_age": (
            "frame_timestamp_minus_recovery_not_before_measurement_timestamp_"
            "for_records_with_watermark"
        ),
    }
    assert audit["identity_commitment_all_records"] == {
        "denominator": 4,
        "committed_count": 2,
        "uncommitted_count": 2,
        "coverage": 0.5,
        "coverage_available": True,
        "coverage_reason": None,
    }
    assert audit["identity_commitment_observed_records"] == {
        "denominator": 3,
        "committed_count": 2,
        "uncommitted_count": 1,
        "coverage": pytest.approx(2.0 / 3.0),
        "coverage_available": True,
        "coverage_reason": None,
    }
    assert audit["identity_commitment_reason_counts"] == {
        "fresh_original_observation_accepted": 2,
        "identity_recovery_blocked_measurement_not_newer_than_hold": 1,
        "identity_recovery_blocked_reused_hold_evidence": 1,
    }
    assert audit["identity_recovery_blocked_reason_counts"] == {
        "identity_recovery_blocked_measurement_not_newer_than_hold": 1,
        "identity_recovery_blocked_reused_hold_evidence": 1,
    }
    assert audit["identity_recovery_blocker_count_summary"] == {
        "record_count": 4,
        "positive_record_count": 2,
        "sum": 6,
        "min": 0,
        "mean": 1.5,
        "max": 4,
    }
    assert audit["identity_recovery_watermark_age_seconds_summary"] == {
        "count": 2,
        "min": 0.5,
        "mean": 0.625,
        "max": 0.75,
    }
    assert audit["identity_recovery_blocker_overflow_record_count"] == 2
    assert audit["identity_recovery_blocker_overflow_track_count"] == 1
    assert audit["uncommitted_candidate_binding_violation_count"] == 0
    assert audit["uncommitted_source_binding_violation_count"] == 0
    assert audit["committed_anchor_across_uncommitted_gap_policy"] == (
        "compare_consecutive_committed_truth_anchors_across_uncommitted_gaps"
    )


def test_v1_evaluator_keeps_commitment_audit_unavailable() -> None:
    record = GlobalTrackLineageEvidence(
        schema_version=SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V1,
        episode_id="legacy-evaluation",
        frame_index=0,
        frame_timestamp=0.0,
        global_track_id="GT3D-000001",
        lifecycle_state="tentative",
        association_state="created",
        source_observations=(
            ObservationLineageRef(
                observation_id="obs-legacy",
                measurement_timestamp=0.0,
            ),
        ),
    )
    labels = (
        Scalable3DObservationTruthLabel.target(
            observation_id="obs-legacy",
            truth_target_id="TGT-001",
            measurement_timestamp=0.0,
        ),
    )
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="legacy-evaluation",
        records=(record,),
        online_d1_records_sha256=_SHA256_A,
        online_d2_records_sha256=_SHA256_B,
        observation_truth_labels_sha256=(
            hash_scalable_3d_observation_truth_labels(labels)
        ),
    )

    evaluation = evaluate_scalable_3d_identity(bundle, labels)

    assert (
        evaluation.schema_version
        == SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1
    )
    assert evaluation.identity_evidence_records == ()
    assert evaluation.audit["identity_commitment_all_records"] is None
    assert evaluation.audit["identity_commitment_observed_records"] is None
    assert evaluation.audit["identity_commitment_reason_counts"] is None
    assert (
        evaluation.audit[
            "identity_recovery_watermark_age_seconds_summary"
        ]
        is None
    )
    assert (
        evaluation.audit[
            "identity_recovery_blocker_overflow_record_count"
        ]
        is None
    )


def test_v2_evaluator_rejects_negative_recovery_watermark_age() -> None:
    record = _record(
        track_id="GT3D-000001",
        frame_index=1,
        association_state="matched",
        commitment=_after_hold(
            "GT3D-000001",
            "matched",
            1.0,
            reason="identity_recovery_blocked_watermark",
            recovery_not_before_measurement_timestamp=1.1,
        ),
        observation_id=None,
    )
    labels = (
        Scalable3DObservationTruthLabel.target(
            observation_id="truth-presence",
            truth_target_id="TGT-001",
            measurement_timestamp=1.0,
        ),
    )
    bundle = create_scalable_3d_identity_evidence_bundle(
        episode_id="episode-commitment-v2",
        records=(record,),
        online_d1_records_sha256=_SHA256_A,
        online_d2_records_sha256=_SHA256_B,
        observation_truth_labels_sha256=(
            hash_scalable_3d_observation_truth_labels(labels)
        ),
    )

    with pytest.raises(ValueError, match="watermark age cannot be negative"):
        evaluate_scalable_3d_identity(bundle, labels)


def test_v2_loader_recomputes_and_rejects_tampered_commitment_audit(
    tmp_path: Path,
) -> None:
    payload = _evaluate_commitment_audit_fixture().to_dict()
    payload["audit"]["identity_commitment_all_records"][
        "committed_count"
    ] = 99
    path = tmp_path / "tampered_commitment_audit.json"
    path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="audit contradicts v2 evidence records",
    ):
        load_scalable_3d_identity_evaluation(
            path,
            expected_sha256=sha256_file(path),
        )


def test_v2_loader_rejects_uncommitted_candidate_binding_even_if_audit_agrees(
    tmp_path: Path,
) -> None:
    payload = _evaluate_commitment_audit_fixture().to_dict()
    mapping = payload["frames"][1]["mappings"][0]
    mapping["candidate_truth_target_ids"] = ["TGT-FORBIDDEN"]
    payload["audit"]["uncommitted_candidate_binding_count"] = 1
    payload["audit"][
        "uncommitted_candidate_binding_violation_count"
    ] = 1
    path = tmp_path / "uncommitted_candidate_binding.json"
    path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="candidate/source binding violation count must be zero",
    ):
        load_scalable_3d_identity_evaluation(
            path,
            expected_sha256=sha256_file(path),
        )
