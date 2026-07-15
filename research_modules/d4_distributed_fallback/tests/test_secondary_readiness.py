from __future__ import annotations

from dataclasses import replace

import pytest

from d4_distributed_fallback.secondary_readiness import (
    SecondaryReadinessEvidence,
    assess_secondary_readiness,
)


def _complete_evidence() -> SecondaryReadinessEvidence:
    return SecondaryReadinessEvidence(
        node_id="SEC-1",
        current_time_s=10.0,
        readiness_timestamp_s=9.9,
        readiness_stale_after_s=1.0,
        availability_confirmed=True,
        lease_epoch=4,
        lease_expires_at_s=12.0,
        heartbeat_timestamp_s=9.9,
        heartbeat_stale_after_s=1.0,
        cue_freshness_s=0.1,
        cue_stale_after_s=1.0,
        gimbal_pointing_ok=True,
        communication_received_timestamp_s=9.9,
        communication_stale_after_s=1.0,
        coverage_matches_requested_cell=True,
        coverage_ratio=0.9,
        network_full_view_rate=0.9,
        takeover_ready_sustained=True,
        takeover_ready_since_s=9.7,
        takeover_ready_observation_count=3,
    )


def test_complete_secondary_readiness_evidence_is_accepted() -> None:
    assessment = assess_secondary_readiness(
        _complete_evidence(),
        expected_current_time_s=10.0,
    )

    assert assessment.ready is True
    assert assessment.reject_reasons == ()
    assert assessment.lease_valid is True
    assert assessment.sustained_ready is True


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_reason"),
    [
        ("current_time_s", None, "current_time_missing"),
        ("lease_epoch", None, "lease_epoch_missing"),
        ("lease_expires_at_s", None, "lease_expiry_missing"),
        ("lease_expires_at_s", 10.0, "lease_expired"),
        ("heartbeat_timestamp_s", None, "heartbeat_timestamp_missing"),
        ("heartbeat_timestamp_s", 8.9, "heartbeat_stale"),
        ("cue_freshness_s", None, "cue_freshness_missing"),
        ("cue_freshness_s", 1.1, "cue_stale"),
        ("gimbal_pointing_ok", None, "gimbal_pointing_unknown"),
        ("gimbal_pointing_ok", False, "gimbal_not_pointing"),
        (
            "communication_received_timestamp_s",
            None,
            "communication_evidence_missing",
        ),
        ("communication_received_timestamp_s", 8.9, "communication_stale"),
        ("coverage_matches_requested_cell", False, "coverage_cell_mismatch"),
        ("coverage_ratio", None, "coverage_ratio_missing"),
        ("coverage_ratio", 0.64, "coverage_ratio_low"),
        ("network_full_view_rate", None, "network_full_view_rate_missing"),
        ("network_full_view_rate", 0.79, "network_full_view_rate_low"),
        ("takeover_ready_sustained", None, "sustained_readiness_missing"),
        ("takeover_ready_sustained", False, "sustained_readiness_not_met"),
        (
            "takeover_ready_observation_count",
            2,
            "sustained_observation_count_low",
        ),
    ],
)
def test_secondary_readiness_missing_stale_or_low_evidence_fails_closed(
    field_name: str,
    field_value: object,
    expected_reason: str,
) -> None:
    evidence = replace(_complete_evidence(), **{field_name: field_value})

    assessment = assess_secondary_readiness(
        evidence,
        expected_current_time_s=10.0,
    )

    assert assessment.ready is False
    assert expected_reason in assessment.reject_reasons
