from __future__ import annotations

import json
from dataclasses import replace

import pytest

from d4_distributed_fallback.episode_communication import (
    EPISODE_FAULT_SCENARIOS,
    AirSimEpisodeCommunicationAdapter,
    EpisodeCommunicationConfig,
    EpisodeCommunicationTickInput,
    run_p1_episode_fault_validation_matrix,
    run_episode_communication_replay,
)
from d4_distributed_fallback.secondary_readiness import SecondaryReadinessEvidence


def _config(**overrides: object) -> EpisodeCommunicationConfig:
    values = {
        "member_ids": ("INT-1", "INT-2", "INT-3"),
        "secondary_node_ids": ("RECON-1",),
        "center_failure_timeout_s": 0.5,
        "secondary_stale_after_s": 0.4,
        "ack_deadline_s": 0.4,
        "ack_validity_s": 1.0,
        "lease_duration_s": 2.0,
        "recovery_validation_ticks": 2,
    }
    values.update(overrides)
    return EpisodeCommunicationConfig(**values)


def _tick(
    adapter: AirSimEpisodeCommunicationAdapter,
    timestamp: float,
    *,
    center: bool = False,
    secondary: bool = False,
    delay: float = 0.0,
    dropped: tuple[str, ...] = (),
    partitioned: bool = False,
    digest: bool | None = None,
    authorized: bool = False,
    epoch_overrides: dict[str, int] | None = None,
    readiness_evidence: SecondaryReadinessEvidence | None = None,
    include_readiness: bool = True,
) -> object:
    readiness = readiness_evidence or _readiness(timestamp)
    return adapter.tick(
        EpisodeCommunicationTickInput(
            timestamp_s=timestamp,
            center_heartbeat_received=center,
            secondary_heartbeat_ids=("RECON-1",) if secondary else (),
            secondary_readiness_evidence=(
                {"RECON-1": readiness}
                if secondary and include_readiness
                else {}
            ),
            message_delay_s=delay,
            dropped_ack_member_ids=dropped,
            partitioned=partitioned,
            center_digest_matches=digest,
            recovery_authorized=authorized,
            ack_epoch_overrides=epoch_overrides or {},
        )
    )


def _readiness(timestamp: float, **overrides: object) -> SecondaryReadinessEvidence:
    evidence = SecondaryReadinessEvidence(
        node_id="RECON-1",
        current_time_s=timestamp,
        readiness_timestamp_s=timestamp,
        readiness_stale_after_s=0.4,
        availability_confirmed=True,
        lease_epoch=2,
        lease_expires_at_s=timestamp + 2.0,
        heartbeat_timestamp_s=timestamp,
        heartbeat_stale_after_s=0.4,
        cue_freshness_s=0.05,
        cue_stale_after_s=0.4,
        gimbal_pointing_ok=True,
        communication_received_timestamp_s=timestamp,
        communication_stale_after_s=0.4,
        coverage_matches_requested_cell=True,
        coverage_ratio=0.9,
        network_full_view_rate=0.9,
        takeover_ready_sustained=True,
        takeover_ready_since_s=timestamp - 0.25,
        takeover_ready_observation_count=3,
    )
    return replace(evidence, **overrides)


@pytest.mark.parametrize("scenario_id", EPISODE_FAULT_SCENARIOS)
def test_pure_python_episode_replays_are_safe_and_serializable(scenario_id: str) -> None:
    report = run_episode_communication_replay(scenario_id)

    assert report.passed, report.failure_reasons
    assert all(tick.single_executable_owner for tick in report.ticks)
    assert report.validation_scope == "episode_time_fault_injection"
    assert report.real_rf_network_validated is False
    assert report.real_hardware_validated is False
    assert report.audit_fields_complete is True
    json.dumps(report.to_dict())


def test_episode_fault_matrix_meets_p1_timing_and_fail_closed_acceptance() -> None:
    report = run_p1_episode_fault_validation_matrix()
    cases = {case.scenario_id: case for case in report.cases}

    assert report.scenario_ids == EPISODE_FAULT_SCENARIOS
    assert report.summary["scenario_count"] == 7
    assert report.summary["passed_count"] == 7
    assert report.summary["normal_false_degradation_count"] == 0
    assert report.summary["all_audit_fields_complete"] is True
    assert report.summary["real_rf_network_validated"] is False

    secondary = cases["center_failure"]
    assert secondary.timing_metrics_s["center_to_secondary_executable_s"] <= 1.5
    assert secondary.acceptance_limits_s["center_to_secondary_executable_s"] == 1.5

    distributed = cases["center_secondary_failure"]
    assert distributed.timing_metrics_s["center_to_secondary_executable_s"] <= 1.5
    assert distributed.timing_metrics_s["secondary_to_distributed_commit_s"] <= 2.5
    assert any(
        tick.selected_layer == "secondary" and tick.execution_allowed
        for tick in distributed.ticks
    )
    assert any(
        tick.selected_layer == "distributed" and tick.execution_allowed
        for tick in distributed.ticks
    )

    for scenario_id in ("missing_ack", "stale_epoch", "expired_lease", "partition"):
        assert any(tick.fail_closed for tick in cases[scenario_id].ticks)


def test_episode_ticks_audit_owner_plan_coalition_epoch_and_lease() -> None:
    report = run_episode_communication_replay("center_secondary_failure")

    for tick in report.ticks:
        assert tick.plan_id == "plan-episode-1"
        assert tick.coalition_id == "coalition-episode-1"
        assert tick.plan_version >= 1
        assert tick.coalition_version >= 1
        assert tick.epoch >= 1
        if tick.selected_layer != "center":
            assert tick.lease_expires_at is not None
        if tick.execution_allowed and tick.selected_layer != "center":
            assert tick.owner_id is not None
            assert tick.lease_valid is True


def test_center_failure_has_no_owner_until_secondary_receives_every_ack() -> None:
    adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(adapter, 0.0, center=True, secondary=True)
    _tick(adapter, 0.3, center=False, secondary=True)
    proposed = _tick(adapter, 0.6, center=False, secondary=True, delay=0.2)
    waiting = _tick(adapter, 0.7, center=False, secondary=True)
    executing = _tick(adapter, 0.8, center=False, secondary=True)

    assert proposed.selected_layer == "secondary"
    assert proposed.execution_allowed is False
    assert waiting.executable_owner_ids == ()
    assert executing.owner_id == "RECON-1"
    assert executing.execution_allowed is True
    assert executing.acked_member_ids == ("INT-1", "INT-2", "INT-3")
    assert executing.metadata["arrival_coordination_required"] is False
    assert executing.metadata["multi_member_atomic_authorization_required"] is True


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("current_time_s", None),
        ("lease_expires_at_s", None),
        ("lease_expires_at_s", 0.6),
        ("heartbeat_timestamp_s", None),
        ("heartbeat_timestamp_s", 0.1),
        ("cue_freshness_s", None),
        ("gimbal_pointing_ok", None),
        ("gimbal_pointing_ok", False),
        ("communication_received_timestamp_s", None),
        ("coverage_ratio", None),
        ("coverage_ratio", 0.64),
        ("network_full_view_rate", None),
        ("network_full_view_rate", 0.79),
        ("takeover_ready_sustained", False),
    ],
)
def test_secondary_heartbeat_cannot_propose_with_incomplete_readiness_evidence(
    field_name: str,
    field_value: object,
) -> None:
    adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(adapter, 0.0, center=True, secondary=True)
    _tick(adapter, 0.3, center=False, secondary=True)
    malformed = replace(_readiness(0.6), **{field_name: field_value})

    result = _tick(
        adapter,
        0.6,
        center=False,
        secondary=True,
        readiness_evidence=malformed,
    )

    assert result.selected_layer == "distributed"
    assert result.owner_id != "RECON-1"
    assert "RECON-1" not in result.executable_owner_ids
    assessment = result.metadata["secondary_readiness_assessments"]["RECON-1"]
    assert assessment["ready"] is False


def test_secondary_heartbeat_without_readiness_dto_falls_back_to_distributed() -> None:
    adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(adapter, 0.0, center=True, secondary=True)
    _tick(adapter, 0.3, center=False, secondary=True)

    result = _tick(
        adapter,
        0.6,
        center=False,
        secondary=True,
        include_readiness=False,
    )

    assert result.selected_layer == "distributed"
    assert result.owner_id != "RECON-1"
    assert "RECON-1" not in result.executable_owner_ids
    assert result.metadata["secondary_readiness_assessments"] == {}


def test_center_and_secondary_failure_commits_distributed_owner_atomically() -> None:
    adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(adapter, 0.0, center=True, secondary=True)
    _tick(adapter, 0.3)
    proposed = _tick(adapter, 0.6, delay=0.1)
    executing = _tick(adapter, 0.7)

    assert proposed.selected_layer == "distributed"
    assert proposed.owner_id is None
    assert executing.owner_id == "INT-1"
    assert executing.commit_state == "executing"
    assert executing.executable_owner_ids == ("INT-1",)


def test_missing_ack_and_stale_epoch_both_fail_closed() -> None:
    missing_adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(missing_adapter, 0.0, center=True)
    _tick(missing_adapter, 0.3)
    _tick(missing_adapter, 0.6, dropped=("INT-3",))
    missing = _tick(missing_adapter, 1.0, dropped=("INT-3",))

    assert missing.commit_state == "aborted"
    assert missing.commit_reason == "missing_required_acks"
    assert missing.owner_id is None
    assert missing.fail_closed is True

    stale_adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(stale_adapter, 0.0, center=True)
    _tick(stale_adapter, 0.3)
    stale = _tick(stale_adapter, 0.6, epoch_overrides={"INT-2": 1})
    final = _tick(stale_adapter, 1.0)

    assert "ack_epoch_stale" in stale.rejected_ack_reasons
    assert final.commit_reason == "missing_required_acks"
    assert final.execution_allowed is False


def test_tick_audits_message_delay_drop_and_stale_plan_version() -> None:
    adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(adapter, 0.0, center=True)
    _tick(adapter, 0.3)
    proposed = adapter.tick(
        EpisodeCommunicationTickInput(
            timestamp_s=0.6,
            center_heartbeat_received=False,
            message_delay_s=0.2,
            dropped_ack_member_ids=("INT-3",),
            ack_plan_version_overrides={"INT-2": 1},
        )
    )
    delivered = _tick(adapter, 0.8, dropped=("INT-3",))

    queued = [event for event in proposed.message_events if event["status"] == "queued"]
    dropped = [event for event in proposed.message_events if event["status"] == "dropped"]
    assert next(event for event in queued if event["sender_id"] == "INT-2")[
        "delay_s"
    ] == 0.2
    assert dropped[0]["sender_id"] == "INT-3"
    assert dropped[0]["drop_reason"] == "configured_missing_ack"
    assert "ack_plan_version_stale" in delivered.rejected_ack_reasons
    assert delivered.owner_id is None


def test_partition_revokes_fallback_and_recovery_requires_new_full_ack() -> None:
    adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(adapter, 0.0, center=True)
    _tick(adapter, 0.3)
    executing = _tick(adapter, 0.6)
    assert executing.execution_allowed
    old_epoch = executing.epoch

    partition = _tick(adapter, 0.8, partitioned=True)
    reproposed = _tick(adapter, 1.0, delay=0.1)
    recovered = _tick(adapter, 1.1)

    assert partition.owner_id is None
    assert partition.fail_closed
    assert reproposed.epoch > old_epoch
    assert reproposed.execution_allowed is False
    assert recovered.acked_member_ids == ("INT-1", "INT-2", "INT-3")
    assert recovered.execution_allowed is True


def test_expired_lease_revokes_the_only_fallback_owner() -> None:
    adapter = AirSimEpisodeCommunicationAdapter(_config(lease_duration_s=0.5))
    _tick(adapter, 0.0, center=True)
    _tick(adapter, 0.3)
    executing = _tick(adapter, 0.6)
    expired = _tick(adapter, 1.2)

    assert executing.execution_allowed is True
    assert expired.commit_reason == "coalition_lease_expired"
    assert expired.owner_id is None
    assert expired.lease_valid is False
    assert expired.fail_closed is True


def test_center_recovery_keeps_fallback_during_dual_track_validation() -> None:
    adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(adapter, 0.0, center=True)
    _tick(adapter, 0.3)
    fallback = _tick(adapter, 0.6)
    first = _tick(adapter, 0.8, center=True, digest=True, authorized=True)
    conflict = _tick(adapter, 0.9, center=True, digest=False, authorized=True)
    validate = _tick(adapter, 1.0, center=True, digest=True, authorized=False)
    restored = _tick(adapter, 1.1, center=True, digest=True, authorized=True)

    assert fallback.owner_id == "INT-1"
    assert first.owner_id == "INT-1"
    assert first.plan_transition == "center_recovery_dual_track_validation"
    assert conflict.owner_id == "INT-1"
    assert validate.owner_id == "INT-1"
    assert restored.owner_id == "CENTER"
    assert restored.selected_layer == "center"
    assert restored.plan_transition == "center_recovery_accepted_after_dual_track_validation"


def test_timestamp_and_secondary_identity_validation() -> None:
    adapter = AirSimEpisodeCommunicationAdapter(_config())
    _tick(adapter, 0.0, center=True)
    with pytest.raises(ValueError, match="strictly increasing"):
        _tick(adapter, 0.0, center=True)
    with pytest.raises(ValueError, match="unknown secondary"):
        adapter.tick(
            EpisodeCommunicationTickInput(
                timestamp_s=0.1,
                center_heartbeat_received=True,
                secondary_heartbeat_ids=("UNKNOWN",),
            )
        )
