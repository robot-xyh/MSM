from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from d4_distributed_fallback import (
    C2Health,
    CoalitionCommitCoordinator,
    CoalitionMemberAck,
    CoalitionSafetyAction,
    D4ArbitrationAdapter,
    DegradationAction,
    SecondaryReadinessEvidence,
    build_coalition_commit_d6_metadata,
    build_coalition_safety_evidence,
)


TRACK_ID = "G-COMMIT-1"
COALITION_ID = "coalition-commit-1"
PLAN_ID = "plan-commit-1"
MEMBERS = ("INT-1", "INT-2", "INT-3")


def _plan() -> SimpleNamespace:
    assignments = tuple(
        SimpleNamespace(
            target_id=TRACK_ID,
            resource_id=resource_id,
            plan_version=4,
            coalition_id=COALITION_ID,
            coalition_version=2,
            required_resource_count=3,
        )
        for resource_id in MEMBERS
    )
    coalition = SimpleNamespace(
        target_id=TRACK_ID,
        coalition_id=COALITION_ID,
        version=2,
        coordination_mode="hybrid",
        required_resource_count=3,
        assigned_resource_count=3,
        complete=True,
        members=tuple(
            SimpleNamespace(resource_id=item, member_role="primary", executable=True)
            for item in MEMBERS
        ),
    )
    return SimpleNamespace(
        plan_id=PLAN_ID,
        version=4,
        created_at=9.0,
        decision_state="accepted",
        assignments=assignments,
        coalitions=(coalition,),
    )


def _track() -> SimpleNamespace:
    return SimpleNamespace(
        global_track_id=TRACK_ID,
        covariance=np.eye(6),
        timestamp=10.0,
        last_update_time=9.9,
        metadata={"coverage_cell": "cell-1"},
    )


def _terminal() -> SimpleNamespace:
    return SimpleNamespace(
        resource_id="INT-1",
        assigned_global_track_id=TRACK_ID,
        decision_state="locked",
        association_confidence=0.95,
        ambiguity_score=0.01,
        friend_conflict_state="none",
        coalition_id=COALITION_ID,
        coalition_version=2,
    )


def _propose(
    coordinator: CoalitionCommitCoordinator,
    *,
    epoch: int = 7,
    plan_version: int = 4,
    coalition_version: int = 2,
    role: str = "cluster_representative",
    lease_expires_at: float = 20.0,
    required_member_ids: tuple[str, ...] = MEMBERS,
):
    metadata = {}
    if role == "mobile_high_recon":
        readiness = SecondaryReadinessEvidence(
            node_id="RECON-1",
            current_time_s=10.0,
            readiness_timestamp_s=10.0,
            readiness_stale_after_s=1.0,
            availability_confirmed=True,
            lease_epoch=epoch,
            lease_expires_at_s=lease_expires_at,
            heartbeat_timestamp_s=10.0,
            heartbeat_stale_after_s=1.0,
            cue_freshness_s=0.1,
            cue_stale_after_s=1.0,
            gimbal_pointing_ok=True,
            communication_received_timestamp_s=10.0,
            communication_stale_after_s=1.0,
            coverage_matches_requested_cell=True,
            coverage_ratio=0.9,
            network_full_view_rate=0.9,
            takeover_ready_sustained=True,
            takeover_ready_since_s=9.7,
            takeover_ready_observation_count=3,
        )
        metadata = {"secondary_readiness_evidence": readiness.to_dict()}
    return coordinator.propose(
        global_track_id=TRACK_ID,
        coalition_id=COALITION_ID,
        coalition_version=coalition_version,
        plan_id=PLAN_ID,
        plan_version=plan_version,
        epoch=epoch,
        coordinator_id="RECON-1" if role == "mobile_high_recon" else "INT-1",
        coordinator_role=role,
        required_member_ids=required_member_ids,
        lease_expires_at=lease_expires_at,
        timestamp=10.0,
        metadata=metadata,
    )


def _ack(resource_id: str, *, epoch: int = 7, can_execute: bool = True):
    return CoalitionMemberAck(
        resource_id=resource_id,
        global_track_id=TRACK_ID,
        coalition_id=COALITION_ID,
        coalition_version=2,
        plan_id=PLAN_ID,
        plan_version=4,
        epoch=epoch,
        can_execute=can_execute,
        evidence_timestamp=10.1,
        valid_until=15.0,
        reason="ready",
    )


def _commit(
    coordinator: CoalitionCommitCoordinator,
    *,
    role: str = "cluster_representative",
):
    state = _propose(coordinator, role=role)
    for index, member_id in enumerate(MEMBERS, start=1):
        state = coordinator.record_ack(
            state,
            _ack(member_id),
            timestamp=10.1 + 0.1 * index,
        )
    return state


def test_proposal_and_partial_ack_remain_collecting_until_all_members_ack() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = coordinator.evaluate(_propose(coordinator), timestamp=10.05)

    assert state.state == "collecting_acks"
    assert state.acked_member_ids == ()
    assert state.missing_member_ids == MEMBERS

    state = coordinator.record_ack(state, _ack("INT-1"), timestamp=10.2)
    assert state.state == "collecting_acks"
    assert state.acked_member_ids == ("INT-1",)
    assert state.missing_member_ids == ("INT-2", "INT-3")

    state = coordinator.record_ack(state, _ack("INT-2"), timestamp=10.3)
    assert state.state == "collecting_acks"
    assert state.acked_member_ids == ("INT-1", "INT-2")

    state = coordinator.record_ack(state, _ack("INT-3"), timestamp=10.4)
    assert state.state == "committed"
    assert state.acked_member_ids == MEMBERS
    assert state.missing_member_ids == ()
    assert state.committed_at == 10.4


def test_normal_center_keeps_existing_coalition_path_without_commit() -> None:
    plan = _plan()
    result = D4ArbitrationAdapter().evaluate(
        timestamp=10.0,
        track=_track(),
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=_terminal(),
        c2_health=C2Health.NORMAL,
        expected_plan_version=4,
    )

    assert result.decision.action == DegradationAction.CONTINUE_CENTER
    assert result.coalition_safety.atomic_coalition_formed is False
    assert result.coalition_safety.safety_action == CoalitionSafetyAction.CONTINUE_CENTER


def test_takeover_ready_secondary_commit_is_valid_atomic_fallback() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = _commit(coordinator, role="mobile_high_recon")
    plan = _plan()

    evidence = build_coalition_safety_evidence(
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=_terminal(),
        cross_view_summary=None,
        global_track_id=TRACK_ID,
        resource_id="INT-1",
        center_available=False,
        expected_plan_version=4,
        coalition_commit_state=state,
        current_time_s=11.0,
    )

    assert state.state == "committed"
    json.dumps(state.to_dict())
    json.dumps(_ack("INT-1").to_dict())
    assert evidence.atomic_coalition_formed is True
    assert evidence.fallback_supported is True
    assert evidence.safety_action == CoalitionSafetyAction.ALLOW_ATOMIC_FALLBACK
    assert evidence.metadata["coalition_fallback_mode"] == "secondary"


def test_legacy_takeover_ready_boolean_cannot_authorize_secondary_proposal() -> None:
    coordinator = CoalitionCommitCoordinator()

    state = coordinator.propose(
        global_track_id=TRACK_ID,
        coalition_id=COALITION_ID,
        coalition_version=2,
        plan_id=PLAN_ID,
        plan_version=4,
        epoch=7,
        coordinator_id="RECON-1",
        coordinator_role="mobile_high_recon",
        required_member_ids=MEMBERS,
        lease_expires_at=20.0,
        timestamp=10.0,
        metadata={"takeover_ready": True},
    )

    assert state.state == "aborted"
    assert state.reason == "secondary_readiness_evidence_missing"


def test_distributed_three_member_commit_allows_existing_adapter_path() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = _commit(coordinator)
    state = coordinator.mark_executing(state, timestamp=10.8)
    plan = _plan()

    result = D4ArbitrationAdapter().evaluate(
        timestamp=11.0,
        track=_track(),
        plan=plan,
        assignment=plan.assignments[0],
        terminal_association=_terminal(),
        c2_health=C2Health.FAILED,
        expected_plan_version=4,
        coalition_commit_state=state,
    )

    assert result.decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED
    assert state.state == "executing"
    assert result.coalition_safety.atomic_coalition_formed is True
    metadata = build_coalition_commit_d6_metadata(state)
    assert metadata["atomic_coalition_formed"] is False
    assert metadata["coalition_lease_valid"] is False
    assert metadata["coalition_lease_current_time_present"] is False
    metadata = build_coalition_commit_d6_metadata(state, current_time_s=11.0)
    assert metadata["atomic_coalition_formed"] is True
    assert metadata["coalition_acked_member_ids"] == list(MEMBERS)


def test_missing_ack_fails_closed_when_collection_is_finalized() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = _propose(coordinator)
    state = coordinator.record_ack(state, _ack("INT-1"), timestamp=10.2)
    state = coordinator.record_ack(state, _ack("INT-2"), timestamp=10.3)

    state = coordinator.evaluate(state, timestamp=10.4, finalize=True)

    assert state.state == "aborted"
    assert state.reason == "missing_required_acks"
    assert state.missing_member_ids == ("INT-3",)
    assert build_coalition_commit_d6_metadata(state)["atomic_coalition_formed"] is False


def test_collecting_ack_window_aborts_at_lease_expiry() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = coordinator.evaluate(
        _propose(coordinator, lease_expires_at=10.5),
        timestamp=10.1,
    )

    expired = coordinator.evaluate(state, timestamp=10.5)

    assert state.state == "collecting_acks"
    assert expired.state == "aborted"
    assert expired.reason == "coalition_lease_expired"
    assert expired.resolved_at == 10.5


def test_stale_epoch_proposal_is_rejected_without_replacing_current_state() -> None:
    coordinator = CoalitionCommitCoordinator()
    current = _propose(coordinator, epoch=7)

    stale = _propose(coordinator, epoch=6)
    stale_plan = _propose(coordinator, plan_version=3)
    stale_coalition = _propose(coordinator, coalition_version=1)
    updated = coordinator.record_ack(current, _ack("INT-1"), timestamp=10.2)

    assert stale.state == "aborted"
    assert stale.reason == "coalition_epoch_stale"
    assert stale_plan.reason == "coalition_plan_version_stale"
    assert stale_coalition.reason == "coalition_version_stale"
    assert updated.acked_member_ids == ("INT-1",)


def test_expired_committed_lease_enters_reconfiguration() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = _commit(coordinator)

    expired = coordinator.evaluate(state, timestamp=20.0)

    assert expired.state == "reconfiguring"
    assert expired.reason == "coalition_lease_expired"
    assert build_coalition_commit_d6_metadata(
        state, current_time_s=20.0
    )["atomic_coalition_formed"] is False


def test_duplicate_ack_is_idempotent_and_audited() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = _propose(coordinator)
    state = coordinator.record_ack(state, _ack("INT-1"), timestamp=10.2)

    duplicate = coordinator.record_ack(state, _ack("INT-1"), timestamp=10.3)

    assert duplicate.acked_member_ids == ("INT-1",)
    assert duplicate.reason == "duplicate_ack_ignored"
    assert duplicate.metadata["duplicate_ack_count"] == 1


def test_member_capability_revocation_reconfigures_committed_coalition() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = _commit(coordinator)

    revoked = coordinator.record_ack(
        state,
        _ack("INT-1", can_execute=False),
        timestamp=11.0,
    )

    assert revoked.state == "reconfiguring"
    assert revoked.reason == "required_member_cannot_execute"


def test_non_member_ack_is_rejected_without_counting_member() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = _propose(coordinator)

    rejected = coordinator.record_ack(state, _ack("INT-9"), timestamp=10.2)

    assert rejected.state == "collecting_acks"
    assert rejected.acked_member_ids == ()
    assert rejected.reason == "ack_resource_not_required_member"
    assert rejected.metadata["rejected_ack_count"] == 1


def test_stale_ack_is_rejected_without_authorizing_current_generation() -> None:
    coordinator = CoalitionCommitCoordinator()
    state = coordinator.evaluate(_propose(coordinator), timestamp=10.05)

    rejected = coordinator.record_ack(
        state,
        _ack("INT-1", epoch=6),
        timestamp=10.2,
    )

    assert rejected.state == "collecting_acks"
    assert rejected.reason == "ack_epoch_stale"
    assert rejected.acked_member_ids == ()
    assert rejected.metadata["rejected_ack_count"] == 1
    assert (
        build_coalition_commit_d6_metadata(
            rejected,
            current_time_s=10.2,
        )["atomic_coalition_formed"]
        is False
    )


def test_network_partition_aborts_collecting_and_reconfigures_committed() -> None:
    collecting_coordinator = CoalitionCommitCoordinator()
    collecting = _propose(collecting_coordinator)
    collecting = collecting_coordinator.record_ack(
        collecting, _ack("INT-1"), timestamp=10.2
    )
    aborted = collecting_coordinator.evaluate(
        collecting, timestamp=10.3, partitioned=True
    )

    committed_coordinator = CoalitionCommitCoordinator()
    committed = _commit(committed_coordinator)
    reconfiguring = committed_coordinator.evaluate(
        committed, timestamp=11.0, partitioned=True
    )

    assert aborted.state == "aborted"
    assert reconfiguring.state == "reconfiguring"
    assert reconfiguring.reason == "network_partition"


def test_same_generation_digest_conflict_is_aborted() -> None:
    coordinator = CoalitionCommitCoordinator()
    _propose(coordinator)

    conflict = _propose(
        coordinator,
        required_member_ids=("INT-1", "INT-2", "INT-4"),
    )

    assert conflict.state == "aborted"
    assert conflict.reason == "coalition_digest_conflict"


def test_recovery_audit_never_immediately_replaces_divergent_track() -> None:
    local_coordinator = CoalitionCommitCoordinator()
    local = _commit(local_coordinator)
    recovered_coordinator = CoalitionCommitCoordinator()
    recovered = _propose(recovered_coordinator, epoch=8)

    audit = local_coordinator.audit_recovery(local, recovered, timestamp=12.0)

    assert audit["digest_match"] is False
    assert audit["recovered_newer"] is True
    assert audit["decision"] == "dual_track_review_required"
    assert audit["immediate_takeover_allowed"] is False
