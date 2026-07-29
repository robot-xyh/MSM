from __future__ import annotations

from dataclasses import replace

import pytest

from d4_distributed_fallback.region_resource import (
    REGION_RESOURCE_ADVISORY_SCHEMA,
    REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA,
    REGION_RESOURCE_SNAPSHOT_SCHEMA,
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceAction,
    RegionResourceAdvisoryContract,
    RegionResourceEdge,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
)
from d4_distributed_fallback.regional_failover import (
    RegionOwnershipMetadata,
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverDecision,
    RegionalRegionDecision,
    RegionalScenarioMetadata,
)


def _case(
    *,
    target_action: RegionalAction = RegionalAction.REQUEST_CENTER_REPLAN,
    target_reason: str = "d3_resource_infeasible",
    target_rejections: tuple[str, ...] = ("d3_resource_infeasible",),
    target_risk_factors: tuple[str, ...] = ("d3_resource_infeasible",),
    target_layer: RegionalAuthorityLayer = RegionalAuthorityLayer.CENTER,
    target_owner_id: str = "CENTER",
    target_owner_role: str = "center",
    target_execution_allowed: bool = False,
    target_owner_active: bool = False,
    target_lease_expires_at_s: float = 20.0,
    coalition_ack_complete: bool = True,
    fault_generation_fenced: bool = False,
    edge_partitioned: bool = False,
) -> tuple[RegionalFailoverDecision, RegionResourceSnapshot]:
    scenario = RegionalScenarioMetadata(
        scenario_name="regional-planning-probe",
        scenario_version="v1",
        task_count=2,
        resource_count=5,
        recon_count=1,
        region_count=2,
        region_ids=("region-000", "region-001"),
    )
    source_ownership = RegionOwnershipMetadata(
        region_id="region-000",
        owner_id="CENTER",
        owner_layer=RegionalAuthorityLayer.CENTER,
        owner_role="center",
        plan_id="plan-current",
        plan_version=4,
        epoch=3,
        lease_expires_at_s=20.0,
        active=True,
        task_ids=("task-source",),
    )
    target_ownership = RegionOwnershipMetadata(
        region_id="region-001",
        owner_id=target_owner_id,
        owner_layer=target_layer,
        owner_role=target_owner_role,
        plan_id="plan-current",
        plan_version=4,
        epoch=3,
        lease_expires_at_s=target_lease_expires_at_s,
        active=target_owner_active,
        task_ids=("task-target",),
    )
    source_decision = RegionalRegionDecision(
        region_id="region-000",
        selected_layer=RegionalAuthorityLayer.CENTER,
        action=RegionalAction.CONTINUE_CENTER,
        reason="center_plan_current",
        ownership=source_ownership,
        execution_allowed=True,
        fail_closed=False,
        risk_factors=(),
        task_ids=("task-source",),
    )
    target_decision = RegionalRegionDecision(
        region_id="region-001",
        selected_layer=target_layer,
        action=target_action,
        reason=target_reason,
        ownership=target_ownership,
        execution_allowed=target_execution_allowed,
        fail_closed=not target_execution_allowed,
        risk_factors=target_risk_factors,
        task_ids=("task-target",),
        rejection_reasons=target_rejections,
    )
    formal = RegionalFailoverDecision(
        timestamp_s=1.0,
        scenario=scenario,
        region_decisions=(source_decision, target_decision),
    )
    signals = {
        "region-000": {
            "target_demand": 1.0,
            "high_threat_backlog": 0.0,
            "d1_uncertainty": 0.1,
            "d2_uncertainty": 0.1,
            "d5_visibility": 1.0,
            "d5_consistency": 1.0,
            "available_resources": 4,
            "reserve_resources": 1,
            "committed_resources": 2,
            "secondary_coverage": 1.0,
            "secondary_readiness": 1.0,
            "communication_capacity": 100.0,
            "communication_latency_s": 0.01,
            "packet_loss_rate": 0.0,
            "coalition_ack_complete": True,
            "fault_fenced": False,
            "degradation_failed": False,
        },
        "region-001": {
            "target_demand": 4.0,
            "high_threat_backlog": 2.0,
            "d1_uncertainty": 0.2,
            "d2_uncertainty": 0.2,
            "d5_visibility": 1.0,
            "d5_consistency": 1.0,
            "available_resources": 1,
            "reserve_resources": 0,
            "committed_resources": 1,
            "secondary_coverage": 1.0,
            "secondary_readiness": 1.0,
            "communication_capacity": 100.0,
            "communication_latency_s": 0.01,
            "packet_loss_rate": 0.0,
            "coalition_ack_complete": coalition_ack_complete,
            # This is the existing generic formal execution fence.
            "fault_fenced": not target_execution_allowed,
            "fault_fence_epoch": 3 if not target_execution_allowed else None,
            # Only this field denotes an actual fault-generation fence.
            "fault_generation_fenced": fault_generation_fenced,
            "degradation_failed": not target_execution_allowed,
        },
    }
    snapshot = RegionResourceSnapshot.from_regional_decision(
        formal,
        snapshot_id="snapshot-current",
        scenario_id=scenario.scenario_name,
        scenario_version=scenario.scenario_version,
        seed=11,
        region_signals=signals,
        edges=(
            RegionResourceEdge(
                source_region_id="region-000",
                target_region_id="region-001",
                transferable_resources=2,
                distance_m=1000.0,
                transfer_time_s=10.0,
                bandwidth_mbps=20.0,
                partitioned=edge_partitioned,
                bidirectional=True,
                edge_id="edge-000-001",
            ),
        ),
    )
    return formal, snapshot


def _raw_transfer(
    snapshot: RegionResourceSnapshot,
    *,
    target_plan_version: int | None = None,
    target_epoch: int | None = None,
) -> RegionResourceRecommendation:
    actions: list[RegionResourceAction] = []
    for node in snapshot.regions:
        target = node.region_id == "region-001"
        actions.append(
            RegionResourceAction(
                region_id=node.region_id,
                resource_quota_delta=1 if target else -1,
                reserve_ratio=0.1 if target else 0.25,
                reconnaissance_priority=0.5,
                hold=False,
                request_replan=target,
                expected_owner_id=node.current_owner_id,
                expected_owner_layer=node.current_owner_layer,
                expected_plan_id=node.plan_id,
                expected_plan_version=(
                    target_plan_version
                    if target and target_plan_version is not None
                    else node.plan_version
                ),
                expected_epoch=(
                    target_epoch
                    if target and target_epoch is not None
                    else node.epoch
                ),
                expected_lease_expires_at_s=node.lease_expires_at_s,
            )
        )
    edge = snapshot.edges[0]
    return RegionResourceRecommendation(
        snapshot_id=snapshot.snapshot_id,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=snapshot.seed,
        authority_digest=snapshot.authority_digest,
        created_at_s=snapshot.timestamp_s,
        policy_name="planning-authority-test",
        policy_version="v1",
        source=RecommendationSource.RULE,
        confidence=1.0,
        actions=tuple(actions),
        transfers=(
            RegionTransferSuggestion(
                source_region_id="region-000",
                target_region_id="region-001",
                resource_count=1,
                edge_id=edge.edge_id,
                expected_transfer_time_s=edge.transfer_time_s,
            ),
        ),
        planning_authority_digest=snapshot.planning_authority_digest,
    )


def test_center_shortage_allows_planning_only_receive_and_consumption() -> None:
    formal, snapshot = _case()
    policy = RuleRegionResourcePolicy()

    recommendation = policy.recommend(snapshot, formal_decision=formal)
    advisory = policy.projector.build_advisory_contract(
        snapshot,
        recommendation,
        formal_decision=formal,
    )
    consumption = policy.projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=1.0,
        formal_decision=formal,
    )

    assert recommendation.transfers
    assert advisory.schema == REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA
    assert advisory.planning_only_region_ids == ("region-001",)
    assert advisory.planning_authority_digest == snapshot.planning_authority_digest
    assert len(advisory.transfers) == 1
    transfer = advisory.transfers[0]
    assert transfer.planning_only_target is True
    source = next(item for item in advisory.regions if item.region_id == "region-000")
    target = next(item for item in advisory.regions if item.region_id == "region-001")
    transfer_regions = {
        item.region_id: item
        for item in advisory.regions
        if item.region_id in {transfer.source_region_id, transfer.target_region_id}
    }
    assert set(transfer_regions) == {
        transfer.source_region_id,
        transfer.target_region_id,
    }
    assert all(not item.hold for item in transfer_regions.values())
    assert source.resources_after == 3
    assert source.protected_committed_resources == 2
    assert source.protected_reserve_resources == 1
    assert target.planning_only is True
    assert target.hold is False
    assert target.request_replan is True
    assert target.source_version.owner_active is False
    assert target.source_version.fault_fenced is True
    capabilities = target.source_version.authority_capabilities
    assert capabilities is not None
    assert capabilities.planning_replan_eligible is True
    assert capabilities.assignment_execution_authorized is False
    assert capabilities.coalition_execution_authorized is False
    assert capabilities.takeover_execution_authorized is False
    assert capabilities.control_execution_authorized is False
    assert consumption.consumable is True
    assert consumption.planning_replan_eligible is True
    assert consumption.execution_authorized is False
    assert consumption.assignment_execution_authorized is False
    assert consumption.coalition_execution_authorized is False
    assert consumption.takeover_execution_authorized is False
    assert consumption.control_execution_authorized is False

    payload = advisory.to_dict()
    assert payload["schema"] == REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA
    assert (
        RegionResourceAdvisoryContract.from_dict(payload).advisory_id
        == advisory.advisory_id
    )


def test_normal_execution_authorized_region_keeps_legacy_advisory_v1() -> None:
    formal, snapshot = _case(
        target_action=RegionalAction.CONTINUE_CENTER,
        target_reason="center_plan_current",
        target_rejections=(),
        target_risk_factors=(),
        target_execution_allowed=True,
        target_owner_active=True,
    )

    advisory = RuleRegionResourcePolicy().recommend_contract(
        snapshot,
        formal_decision=formal,
    )

    assert advisory.schema == REGION_RESOURCE_ADVISORY_SCHEMA
    assert advisory.planning_only_region_ids == ()
    assert advisory.planning_authority_digest == ""
    payload = advisory.to_dict()
    assert "planning_authority_digest" not in payload
    assert "planning_only_region_ids" not in payload
    parsed = RegionResourceAdvisoryContract.from_dict(payload)
    assert parsed.advisory_id == advisory.advisory_id
    consumption = RuleRegionResourcePolicy().projector.validate_for_consumption(
        parsed,
        snapshot,
        evaluated_at_s=1.0,
        formal_decision=formal,
    )
    assert consumption.consumable is True


@pytest.mark.parametrize(
    "case_kwargs",
    [
        {"target_lease_expires_at_s": 1.0},
        {"coalition_ack_complete": False},
        {"fault_generation_fenced": True},
        {
            "target_action": RegionalAction.HOLD_FOR_REVIEW,
            "target_reason": "network_partition",
            "target_rejections": ("network_partition",),
            "target_risk_factors": ("network_partition",),
            "edge_partitioned": True,
        },
        {
            "target_action": RegionalAction.DEGRADE_TO_SECONDARY,
            "target_reason": "center_failed_secondary_pending",
            "target_rejections": ("secondary_commit_incomplete",),
            "target_risk_factors": (),
            "target_layer": RegionalAuthorityLayer.SECONDARY,
            "target_owner_id": "RECON-0",
            "target_owner_role": "mobile_high_recon",
        },
        {
            "target_action": RegionalAction.HOLD_FOR_REVIEW,
            "target_reason": "d5_friend_conflict",
            "target_rejections": ("d5_friend_conflict",),
            "target_risk_factors": ("d5_friend_conflict",),
        },
        {
            "target_action": RegionalAction.HOLD_FOR_REVIEW,
            "target_reason": "d5_duplicate_terminal_lock",
            "target_rejections": ("d5_duplicate_terminal_lock",),
            "target_risk_factors": ("d5_duplicate_terminal_lock",),
        },
        {
            "target_action": RegionalAction.REQUEST_CENTER_REPLAN,
            "target_reason": "d5_identity_conflict",
            "target_rejections": ("d3_resource_infeasible",),
            "target_risk_factors": ("d5_identity_conflict",),
        },
    ],
)
def test_non_resource_shortage_fences_reject_planning_only_transfer(
    case_kwargs: dict[str, object],
) -> None:
    formal, snapshot = _case(**case_kwargs)
    policy = RuleRegionResourcePolicy()

    recommendation = policy.recommend(snapshot, formal_decision=formal)
    advisory = policy.projector.build_advisory_contract(
        snapshot,
        recommendation,
        formal_decision=formal,
    )
    consumption = policy.projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=1.0,
        formal_decision=formal,
    )

    assert not any(
        transfer.target_region_id == "region-001"
        for transfer in recommendation.transfers
    )
    assert advisory.planning_only_region_ids == ()
    assert consumption.consumable is False
    assert consumption.planning_replan_eligible is False


@pytest.mark.parametrize(
    ("field", "stale_value"),
    [
        ("plan", 3),
        ("epoch", 2),
    ],
)
def test_stale_plan_or_epoch_cannot_use_planning_only_exception(
    field: str,
    stale_value: int,
) -> None:
    formal, snapshot = _case()
    raw = _raw_transfer(
        snapshot,
        target_plan_version=stale_value if field == "plan" else None,
        target_epoch=stale_value if field == "epoch" else None,
    )

    projected = DeterministicResourceProjector().project(
        snapshot,
        raw,
        formal_decision=formal,
    )

    assert projected.transfers == ()
    assert any(
        "authority_version_mismatch" in reason
        for reason in projected.projection_rejections
    )


def test_current_formal_d5_hard_hold_invalidates_existing_planning_proof() -> None:
    formal, snapshot = _case()
    policy = RuleRegionResourcePolicy()
    advisory = policy.recommend_contract(snapshot, formal_decision=formal)
    hard_target = replace(
        formal.region_decisions[1],
        action=RegionalAction.HOLD_FOR_REVIEW,
        reason="d5_friend_conflict",
        rejection_reasons=("d5_friend_conflict",),
        risk_factors=("d5_friend_conflict",),
    )
    hard_formal = replace(
        formal,
        region_decisions=(formal.region_decisions[0], hard_target),
    )

    consumption = policy.projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=1.0,
        formal_decision=hard_formal,
    )

    assert consumption.consumable is False
    assert "region:region-001:planning_eligibility_not_current" in (
        consumption.rejection_reasons
    )


def test_legacy_snapshot_without_capability_cannot_gain_planning_permission() -> None:
    formal, snapshot = _case()
    payload = snapshot.to_dict()
    payload.pop("planning_authority_digest", None)
    payload["schema"] = REGION_RESOURCE_SNAPSHOT_SCHEMA
    for region in payload["regions"]:
        region.pop("fault_generation_fenced", None)
        region.pop("authority_capabilities", None)
    legacy_snapshot = RegionResourceSnapshot.from_dict(payload)

    recommendation = RuleRegionResourcePolicy().recommend(
        legacy_snapshot,
        formal_decision=formal,
    )

    assert recommendation.transfers == ()
    assert all(
        node.authority_capabilities is None for node in legacy_snapshot.regions
    )
