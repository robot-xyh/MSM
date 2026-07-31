from __future__ import annotations

from dataclasses import replace
import json

import pytest

from d4_distributed_fallback.region_resource import (
    DeterministicResourceProjector,
    RegionResourceAdvisoryPublicationCode,
    RegionResourceAdvisoryPublicationDecision,
    RegionResourceAdvisoryPublicationGate,
    RegionResourceNode,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
)
from d4_distributed_fallback.regional_failover import RegionalAuthorityLayer


def _snapshot(
    *,
    snapshot_id: str = "snapshot-v1",
    timestamp_s: float = 1.0,
    plan_id: str = "PLAN-A",
    plan_version: int = 1,
    authority_epoch: int = 1,
    lease_expires_at_s: float = 20.0,
    owner_id: str | None = "CENTER",
    owner_layer: RegionalAuthorityLayer = RegionalAuthorityLayer.CENTER,
    owner_active: bool = True,
    fault_fenced: bool = False,
    fault_fence_epoch: int | None = None,
) -> RegionResourceSnapshot:
    node = RegionResourceNode(
        region_id="region-000",
        target_demand=2.0,
        high_threat_backlog=1.0,
        d1_uncertainty=0.2,
        d2_uncertainty=0.1,
        d5_visibility=0.8,
        d5_consistency=0.9,
        available_resources=5,
        reserve_resources=1,
        secondary_coverage=0.9,
        secondary_readiness=0.9,
        communication_capacity=100.0,
        communication_latency_s=0.02,
        packet_loss_rate=0.01,
        current_owner_id=owner_id,
        current_owner_layer=owner_layer,
        plan_id=plan_id,
        plan_version=plan_version,
        epoch=authority_epoch,
        lease_expires_at_s=lease_expires_at_s,
        coalition_ack_complete=True,
        owner_active=owner_active,
        fault_fenced=fault_fenced,
        fault_fence_epoch=fault_fence_epoch,
    )
    return RegionResourceSnapshot(
        snapshot_id=snapshot_id,
        scenario_id="publication-contract",
        scenario_version="v1",
        seed=7,
        timestamp_s=timestamp_s,
        regions=(node,),
        edges=(),
    )


def _advisory(
    projector: DeterministicResourceProjector,
    snapshot: RegionResourceSnapshot,
):
    policy = RuleRegionResourcePolicy(projector=projector)
    recommendation = policy.recommend(snapshot)
    return projector.build_advisory_contract(snapshot, recommendation)


def test_current_generation_advice_is_publishable_and_serializable() -> None:
    snapshot = _snapshot()
    projector = DeterministicResourceProjector()
    gate = RegionResourceAdvisoryPublicationGate(projector)

    decision = gate.build_current_and_authorize(
        snapshot,
        RuleRegionResourcePolicy(projector=projector).recommend(snapshot),
        publication_timestamp_s=1.25,
    )
    restored = RegionResourceAdvisoryPublicationDecision.from_dict(
        json.loads(json.dumps(decision.to_dict(), sort_keys=True))
    )

    assert decision.generation_publishable
    assert decision.planning_consumable
    assert decision.publishable
    assert (
        decision.reason_code
        == RegionResourceAdvisoryPublicationCode.CURRENT_GENERATION_ACCEPTED
    )
    assert not decision.rejection_codes
    assert not decision.planning_rejection_reasons
    assert restored == decision
    assert gate.accepted_publications == (decision,)
    assert decision.assignment_execution_authorized is False
    assert decision.coalition_execution_authorized is False
    assert decision.takeover_execution_authorized is False
    assert decision.control_execution_authorized is False
    serialized = json.dumps(decision.to_dict(), sort_keys=True)
    assert "global_track_id" not in serialized
    assert "actor_truth_id" not in serialized


@pytest.mark.parametrize(
    ("current_changes", "expected_code"),
    [
        (
            {"plan_id": "PLAN-B"},
            RegionResourceAdvisoryPublicationCode.SOURCE_PLAN_ID_SUPERSEDED,
        ),
        (
            {"plan_version": 2},
            RegionResourceAdvisoryPublicationCode.SOURCE_PLAN_VERSION_SUPERSEDED,
        ),
        (
            {"authority_epoch": 2},
            RegionResourceAdvisoryPublicationCode.SOURCE_AUTHORITY_EPOCH_SUPERSEDED,
        ),
        (
            {"lease_expires_at_s": 15.0},
            RegionResourceAdvisoryPublicationCode.SOURCE_AUTHORITY_LEASE_MISMATCH,
        ),
    ],
)
def test_old_plan_generation_cannot_be_published(
    current_changes: dict[str, object],
    expected_code: RegionResourceAdvisoryPublicationCode,
) -> None:
    source = _snapshot()
    projector = DeterministicResourceProjector()
    advisory = _advisory(projector, source)
    current = _snapshot(
        snapshot_id="snapshot-current",
        timestamp_s=1.1,
        **current_changes,
    )

    decision = RegionResourceAdvisoryPublicationGate(projector).authorize(
        advisory,
        current,
        publication_timestamp_s=1.25,
    )

    assert not decision.generation_publishable
    assert not decision.planning_consumable
    assert not decision.publishable
    assert expected_code in decision.rejection_codes
    assert "generation_not_publishable" in decision.planning_rejection_reasons


def test_expired_current_authority_lease_fails_closed() -> None:
    snapshot = _snapshot(lease_expires_at_s=1.5)
    projector = DeterministicResourceProjector()
    advisory = _advisory(projector, snapshot)

    decision = RegionResourceAdvisoryPublicationGate(projector).authorize(
        advisory,
        snapshot,
        publication_timestamp_s=1.5,
    )

    assert not decision.generation_publishable
    assert not decision.planning_consumable
    assert not decision.publishable
    assert (
        RegionResourceAdvisoryPublicationCode.CURRENT_AUTHORITY_LEASE_EXPIRED
        in decision.rejection_codes
    )
    assert (
        RegionResourceAdvisoryPublicationCode.ADVISORY_EXPIRED
        in decision.rejection_codes
    )


def test_current_fault_fence_diagnostic_is_publishable_but_not_consumable() -> None:
    snapshot = _snapshot(
        owner_id=None,
        owner_layer=RegionalAuthorityLayer.HOLD,
        owner_active=False,
        fault_fenced=True,
        fault_fence_epoch=1,
    )
    projector = DeterministicResourceProjector()
    advisory = _advisory(projector, snapshot)

    decision = RegionResourceAdvisoryPublicationGate(projector).authorize(
        advisory,
        snapshot,
        publication_timestamp_s=1.25,
    )

    assert advisory.projected
    assert advisory.transfers == ()
    assert advisory.projection_rejections
    assert advisory.publication_rejections == ()
    assert decision.generation_publishable
    assert decision.publishable
    assert not decision.planning_consumable
    assert decision.publication_rejection_codes == ()
    assert decision.publication_rejection_reasons == ()
    assert any(
        "fault_fence_active" in reason
        for reason in decision.planning_rejection_reasons
    )
    assert decision.assignment_execution_authorized is False
    assert decision.coalition_execution_authorized is False
    assert decision.takeover_execution_authorized is False
    assert decision.control_execution_authorized is False


def test_true_contract_publication_rejection_blocks_both_layers() -> None:
    snapshot = _snapshot()
    projector = DeterministicResourceProjector()
    advisory = replace(
        _advisory(projector, snapshot),
        advisory_id="",
        publication_rejections=("contract_integrity_failure",),
    )

    decision = RegionResourceAdvisoryPublicationGate(projector).authorize(
        advisory,
        snapshot,
        publication_timestamp_s=1.25,
    )

    assert not decision.generation_publishable
    assert not decision.planning_consumable
    assert (
        RegionResourceAdvisoryPublicationCode.ADVISORY_CONTRACT_REJECTED
        in decision.publication_rejection_codes
    )
    assert "contract_integrity_failure" in (
        decision.publication_rejection_reasons
    )
    assert "generation_not_publishable" in decision.planning_rejection_reasons
    assert decision.assignment_execution_authorized is False
    assert decision.coalition_execution_authorized is False
    assert decision.takeover_execution_authorized is False
    assert decision.control_execution_authorized is False


def test_same_identity_refresh_preserves_lease_and_historical_publication() -> None:
    initial = _snapshot()
    projector = DeterministicResourceProjector()
    gate = RegionResourceAdvisoryPublicationGate(projector)
    first = gate.authorize(
        _advisory(projector, initial),
        initial,
        publication_timestamp_s=1.1,
    )
    refresh = _snapshot(
        snapshot_id="snapshot-refresh",
        timestamp_s=1.2,
    )

    second = gate.authorize(
        _advisory(projector, refresh),
        refresh,
        publication_timestamp_s=1.25,
    )
    renewed = _snapshot(
        snapshot_id="snapshot-illegal-renewal",
        timestamp_s=1.4,
        lease_expires_at_s=30.0,
    )
    renewal_attempt = gate.authorize(
        _advisory(projector, renewed),
        renewed,
        publication_timestamp_s=1.5,
    )

    assert first.publishable
    assert second.publishable
    assert gate.publication_history[0] == first
    assert gate.publication_history[0].publishable
    assert all(
        generation.lease_expires_at_s == 20.0
        for publication in gate.accepted_publications
        for generation in publication.current_generations
    )
    assert not renewal_attempt.publishable
    assert (
        RegionResourceAdvisoryPublicationCode.SAME_IDENTITY_LEASE_RENEWAL_FORBIDDEN
        in renewal_attempt.rejection_codes
    )
    assert gate.current_authority_generations[0].lease_expires_at_s == 20.0


def test_replan_supersedes_old_snapshot_without_rewriting_history() -> None:
    first_snapshot = _snapshot()
    projector = DeterministicResourceProjector()
    gate = RegionResourceAdvisoryPublicationGate(projector)
    first_advisory = _advisory(projector, first_snapshot)
    first = gate.authorize(
        first_advisory,
        first_snapshot,
        publication_timestamp_s=1.1,
    )
    replanned = _snapshot(
        snapshot_id="snapshot-v2",
        timestamp_s=1.2,
        plan_id="PLAN-B",
        plan_version=2,
        authority_epoch=2,
        lease_expires_at_s=30.0,
    )
    current = gate.authorize(
        _advisory(projector, replanned),
        replanned,
        publication_timestamp_s=1.25,
    )

    stale_against_current = gate.authorize(
        first_advisory,
        replanned,
        publication_timestamp_s=1.3,
    )
    stale_snapshot_as_current = gate.authorize(
        first_advisory,
        first_snapshot,
        publication_timestamp_s=1.4,
    )

    assert first.publishable
    assert current.publishable
    assert gate.publication_history[0] == first
    assert gate.publication_history[0].publishable
    assert not stale_against_current.publishable
    assert {
        RegionResourceAdvisoryPublicationCode.SOURCE_PLAN_ID_SUPERSEDED,
        RegionResourceAdvisoryPublicationCode.SOURCE_PLAN_VERSION_SUPERSEDED,
        RegionResourceAdvisoryPublicationCode.SOURCE_AUTHORITY_EPOCH_SUPERSEDED,
        RegionResourceAdvisoryPublicationCode.SOURCE_AUTHORITY_LEASE_MISMATCH,
    }.issubset(set(stale_against_current.rejection_codes))
    assert not stale_snapshot_as_current.publishable
    assert (
        RegionResourceAdvisoryPublicationCode.CURRENT_GENERATION_ROLLBACK
        in stale_snapshot_as_current.rejection_codes
    )
