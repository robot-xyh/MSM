from __future__ import annotations

import pytest

from d6_evaluation_metrics.observation_truth_sidecar import (
    ObservationTruthSidecarError,
    audit_observation_truth_sidecar,
)


def test_external_v1_remains_target_only_compatible() -> None:
    audit = audit_observation_truth_sidecar(
        [
            {
                "schema_version": "scalable3d-offline-truth-v1",
                "observation_id": "OBS-1",
                "measurement_timestamp": 0.1,
                "truth_entity_id": "TGT-1",
            }
        ],
        accepted_contract="external",
        declared_schema_version="scalable3d-offline-truth-v1",
    )

    payload = audit.to_dict()
    assert payload["target_label"]["count"] == 1
    assert payload["target_label"]["availability"] == "available"
    assert payload["known_false_alarm"]["count"] is None
    assert payload["known_false_alarm"]["availability"] == "unavailable"
    assert payload["unknown"]["count"] is None
    assert payload["missing_disposition"]["count"] == 0
    assert payload["strict_identity_eligible"] is False
    assert payload["strict_id_switch_backfilled"] is False


def test_external_v2_reports_all_three_dispositions_without_inference() -> None:
    audit = audit_observation_truth_sidecar(
        [
            {
                "schema_version": "scalable3d-offline-truth-v2",
                "observation_id": "OBS-T",
                "measurement_timestamp": 0.1,
                "truth_entity_id": "TGT-1",
                "disposition": "target",
            },
            {
                "schema_version": "scalable3d-offline-truth-v2",
                "observation_id": "OBS-FA",
                "measurement_timestamp": 0.1,
                "truth_entity_id": None,
                "disposition": "known_false_alarm",
            },
            {
                "schema_version": "scalable3d-offline-truth-v2",
                "observation_id": "OBS-U",
                "measurement_timestamp": 0.1,
                "truth_entity_id": None,
                "disposition": "unknown",
            },
        ],
        accepted_contract="external",
        declared_schema_version="scalable3d-offline-truth-v2",
    )

    payload = audit.to_dict()
    assert payload["target_label"]["count"] == 1
    assert payload["known_false_alarm"]["count"] == 1
    assert payload["unknown"]["count"] == 1
    assert payload["missing_disposition"]["count"] == 0
    assert payload["complete_disposition_available"] is True
    assert payload["strict_identity_eligible"] is False
    assert payload["strict_identity_blockers"] == [
        "unknown_observation_truth_disposition_present"
    ]
    assert payload["known_false_alarm_treated_as_target"] is False
    assert payload["inference_sources_used"] == []


def test_d2_v2_non_target_records_must_omit_truth_target_id() -> None:
    audit = audit_observation_truth_sidecar(
        [
            {
                "schema_version": "d2.scalable3d_observation_truth.v2",
                "observation_id": "OBS-T",
                "measurement_timestamp": 0.1,
                "disposition": "target",
                "truth_target_id": "TGT-1",
            },
            {
                "schema_version": "d2.scalable3d_observation_truth.v2",
                "observation_id": "OBS-FA",
                "measurement_timestamp": 0.1,
                "disposition": "known_false_alarm",
            },
        ],
        accepted_contract="d2_normalized",
    )

    assert audit.target_label_count == 1
    assert audit.known_false_alarm_count == 1
    assert audit.unknown_count == 0
    assert audit.strict_identity_eligible is True


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        (
            {
                "schema_version": "scalable3d-offline-truth-v2",
                "observation_id": "OBS-1",
                "measurement_timestamp": 0.1,
                "truth_entity_id": "TGT-1",
            },
            "observation_truth_disposition_missing",
        ),
        (
            {
                "schema_version": "scalable3d-offline-truth-v2",
                "observation_id": "OBS-1",
                "measurement_timestamp": 0.1,
                "truth_entity_id": None,
                "disposition": "unreviewed",
            },
            "unsupported_observation_truth_disposition",
        ),
        (
            {
                "schema_version": "scalable3d-offline-truth-v2",
                "observation_id": "OBS-1",
                "measurement_timestamp": 0.1,
                "truth_entity_id": "TGT-1",
                "disposition": "known_false_alarm",
            },
            "observation_truth_identity_disposition_conflict",
        ),
    ],
)
def test_v2_missing_unknown_or_conflicting_state_fails_closed(
    mutation: dict[str, object],
    error_code: str,
) -> None:
    with pytest.raises(ObservationTruthSidecarError) as exc:
        audit_observation_truth_sidecar(
            [mutation],
            accepted_contract="external",
            declared_schema_version="scalable3d-offline-truth-v2",
        )

    assert exc.value.code == error_code


def test_declared_schema_tampering_and_duplicate_conflict_fail_closed() -> None:
    v1_record = {
        "schema_version": "scalable3d-offline-truth-v1",
        "observation_id": "OBS-1",
        "measurement_timestamp": 0.1,
        "truth_entity_id": "TGT-1",
    }
    with pytest.raises(ObservationTruthSidecarError) as schema_exc:
        audit_observation_truth_sidecar(
            [v1_record],
            accepted_contract="external",
            declared_schema_version="scalable3d-offline-truth-v2",
        )
    assert schema_exc.value.code == "observation_truth_declared_schema_mismatch"

    conflicting = {
        **v1_record,
        "truth_entity_id": "TGT-2",
    }
    with pytest.raises(ObservationTruthSidecarError) as conflict_exc:
        audit_observation_truth_sidecar(
            [v1_record, conflicting],
            accepted_contract="external",
            declared_schema_version="scalable3d-offline-truth-v1",
        )
    assert conflict_exc.value.code == "observation_truth_conflicting_duplicate"
