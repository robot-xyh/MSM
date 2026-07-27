from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from d4_distributed_fallback.coalition_safety import (
    CoalitionCommitState,
    CoalitionMemberAck,
)
from d4_distributed_fallback.communication_causal_evidence import (
    CausalMessageKind,
    CommunicationDeliveryReceipt,
)
from d4_distributed_fallback.models import C2Health
from d4_distributed_fallback.region_resource import (
    AdvisorMode,
    RecommendationSource,
    RegionResourceAction,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
)
from d4_distributed_fallback.region_resource_development_intervention import (
    REGION_RESOURCE_DEVELOPMENT_HOLD_REASON,
    REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME,
    REGION_RESOURCE_DEVELOPMENT_INTERVENTION_REASON,
    REGION_RESOURCE_DEVELOPMENT_REQUEST_REPLAN_REASON,
    REGION_RESOURCE_DEVELOPMENT_TRANSFER_REASON,
    ConstrainedDevelopmentRegionResourceAdapter,
    RegionResourceDevelopmentInterventionConfig,
)
from d4_distributed_fallback.region_resource_learning import (
    RegionResourceAdvisor,
    RegionResourceAdvisorConfig,
)
from d4_distributed_fallback.region_resource_runtime_ack import (
    RegionResourceRuntimeAckCode,
    RegionResourceRuntimeAckEvidence,
    RegionResourceRuntimeAdoptionKind,
)
from d4_distributed_fallback.region_resource_a2_benefit_audit import (
    RegionResourceA2AuditArm,
    RegionResourceA2AuditContext,
    RegionResourceA2AuditWindowReference,
    RegionResourceA2BenefitAuditBatch,
    RegionResourceA2BenefitAuditError,
    RegionResourceA2SafeAdoptionAuditSource,
    assemble_region_resource_a2_benefit_audit_batch,
    assemble_region_resource_a2_benefit_audit_input,
    validate_region_resource_a2_benefit_audit_input,
)
from d4_distributed_fallback.region_resource_safe_adoption import (
    REGION_RESOURCE_COALITION_ACK_DELIVERY_SCHEMA,
    REGION_RESOURCE_COALITION_ACK_TOPIC,
    REGION_RESOURCE_OWNER_ACK_TOPIC,
    RegionResourceCoalitionAckDelivery,
    RegionResourceCoalitionCommitEvidence,
    RegionResourceCoalitionRequirement,
    RegionResourceD3PlanReference,
    RegionResourceOwnerAckDelivery,
    RegionResourceOwnerPlanAck,
    RegionResourcePhysicalWindowEvidence,
    RegionResourceSafeAdoptionAssembler,
    RegionResourceSafeAdoptionContext,
    RegionResourceSafeAdoptionPreparation,
    RegionResourceSafeAdoptionStage,
    build_region_resource_owner_plan_ack,
    validate_region_resource_coalition_ack_delivery,
    validate_region_resource_owner_ack_delivery,
)
from d4_distributed_fallback.regional_failover import (
    CoalitionCommitSummary,
    RegionOwnershipMetadata,
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverDecision,
    RegionalRegionDecision,
    RegionalScenarioMetadata,
)


def _sha(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _owner_id(layer: RegionalAuthorityLayer) -> str:
    return {
        RegionalAuthorityLayer.CENTER: "CENTER",
        RegionalAuthorityLayer.SECONDARY: "RECON-1",
        RegionalAuthorityLayer.DISTRIBUTED: "PEER-1",
    }[layer]


def _snapshot(
    *,
    layer: RegionalAuthorityLayer = RegionalAuthorityLayer.SECONDARY,
    edge_capacity: int = 3,
    partitioned: bool = False,
) -> RegionResourceSnapshot:
    owner_id = _owner_id(layer)
    regions = (
        RegionResourceNode(
            region_id="region-a",
            target_demand=6.0,
            high_threat_backlog=2.0,
            d1_uncertainty=0.2,
            d2_uncertainty=0.1,
            d5_visibility=0.8,
            d5_consistency=0.9,
            available_resources=3,
            reserve_resources=1,
            secondary_coverage=0.9,
            secondary_readiness=0.9,
            communication_capacity=100.0,
            communication_latency_s=0.02,
            packet_loss_rate=0.01,
            current_owner_id=owner_id,
            current_owner_layer=layer,
            plan_id="source-plan",
            plan_version=3,
            epoch=4,
            lease_expires_at_s=10.0,
        ),
        RegionResourceNode(
            region_id="region-b",
            target_demand=1.0,
            high_threat_backlog=0.0,
            d1_uncertainty=0.1,
            d2_uncertainty=0.1,
            d5_visibility=0.9,
            d5_consistency=0.9,
            available_resources=8,
            reserve_resources=2,
            secondary_coverage=0.9,
            secondary_readiness=0.9,
            communication_capacity=100.0,
            communication_latency_s=0.02,
            packet_loss_rate=0.01,
            current_owner_id=owner_id,
            current_owner_layer=layer,
            plan_id="source-plan",
            plan_version=3,
            epoch=4,
            lease_expires_at_s=10.0,
        ),
    )
    return RegionResourceSnapshot(
        snapshot_id="snapshot-safe-adoption",
        scenario_id="scenario-safe-adoption",
        scenario_version="v1",
        seed=101,
        timestamp_s=1.0,
        regions=regions,
        edges=(
            RegionResourceEdge(
                source_region_id="region-a",
                target_region_id="region-b",
                transferable_resources=edge_capacity,
                distance_m=500.0,
                transfer_time_s=5.0,
                bandwidth_mbps=20.0,
                partitioned=partitioned,
                edge_id="edge-ab",
            ),
        ),
    )


def _candidate(
    snapshot: RegionResourceSnapshot,
    *,
    source: RecommendationSource = RecommendationSource.LEARNED,
    confidence: float = 0.85,
    fallback_reason: str | None = None,
    transfer_count: int = 1,
    edge_id: str = "edge-ab",
) -> RegionResourceRecommendation:
    actions = tuple(
        RegionResourceAction(
            region_id=node.region_id,
            resource_quota_delta=(
                transfer_count if node.region_id == "region-a"
                else -transfer_count
            ),
            reserve_ratio=0.4,
            reconnaissance_priority=0.7,
            hold=False,
            request_replan=True,
            expected_owner_id=node.current_owner_id,
            expected_owner_layer=node.current_owner_layer,
            expected_plan_id=node.plan_id,
            expected_plan_version=node.plan_version,
            expected_epoch=node.epoch,
            expected_lease_expires_at_s=node.lease_expires_at_s,
        )
        for node in snapshot.regions
    )
    return RegionResourceRecommendation(
        snapshot_id=snapshot.snapshot_id,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=snapshot.seed,
        authority_digest=snapshot.authority_digest,
        created_at_s=snapshot.timestamp_s,
        policy_name="held-out-graph-policy",
        policy_version="a2-v1",
        source=source,
        confidence=confidence,
        actions=actions,
        transfers=(
            RegionTransferSuggestion(
                source_region_id="region-b",
                target_region_id="region-a",
                resource_count=transfer_count,
                edge_id=edge_id,
                expected_transfer_time_s=5.0,
            ),
        ),
        fallback_reason=fallback_reason,
        model_sha256=(
            _sha("held-out-graph-policy") if source == RecommendationSource.LEARNED
            else None
        ),
    )


def _noop_candidate(
    snapshot: RegionResourceSnapshot,
    *,
    reconnaissance_priority: float = 1.0,
) -> RegionResourceRecommendation:
    return RegionResourceRecommendation(
        snapshot_id=snapshot.snapshot_id,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=snapshot.seed,
        authority_digest=snapshot.authority_digest,
        created_at_s=snapshot.timestamp_s,
        policy_name="held-out-graph-policy",
        policy_version="a2-v1",
        source=RecommendationSource.LEARNED,
        confidence=0.85,
        actions=tuple(
            RegionResourceAction(
                region_id=node.region_id,
                resource_quota_delta=0,
                reserve_ratio=(
                    node.reserve_resources
                    / max(1, node.available_resources)
                ),
                reconnaissance_priority=reconnaissance_priority,
                hold=False,
                request_replan=False,
                expected_owner_id=node.current_owner_id,
                expected_owner_layer=node.current_owner_layer,
                expected_plan_id=node.plan_id,
                expected_plan_version=node.plan_version,
                expected_epoch=node.epoch,
                expected_lease_expires_at_s=node.lease_expires_at_s,
            )
            for node in snapshot.regions
        ),
        transfers=(),
        model_sha256=_sha("held-out-graph-policy"),
    )


class _StaticNoopLearnedPolicy:
    def __init__(self, recommendation: RegionResourceRecommendation) -> None:
        self.recommendation = recommendation

    def recommend_raw(
        self,
        snapshot: RegionResourceSnapshot,
    ) -> RegionResourceRecommendation:
        assert snapshot.snapshot_id == self.recommendation.snapshot_id
        return self.recommendation


def _development_adapter(
    snapshot: RegionResourceSnapshot,
    recommendation: RegionResourceRecommendation | None = None,
) -> ConstrainedDevelopmentRegionResourceAdapter:
    return ConstrainedDevelopmentRegionResourceAdapter(
        _StaticNoopLearnedPolicy(
            recommendation or _noop_candidate(snapshot)
        ),
        config=RegionResourceDevelopmentInterventionConfig(
            enabled=True,
            run_label="safe-adoption-unit-development",
            allowed_scenario_ids=(snapshot.scenario_id,),
            maximum_total_transfer_resources=1,
        ),
    )


def _formal_decision(
    snapshot: RegionResourceSnapshot,
) -> RegionalFailoverDecision:
    layer = snapshot.regions[0].current_owner_layer
    action = {
        RegionalAuthorityLayer.CENTER: RegionalAction.CONTINUE_CENTER,
        RegionalAuthorityLayer.SECONDARY: (
            RegionalAction.DEGRADE_TO_SECONDARY
        ),
        RegionalAuthorityLayer.DISTRIBUTED: (
            RegionalAction.DEGRADE_TO_DISTRIBUTED
        ),
    }[layer]
    scenario = RegionalScenarioMetadata.from_scalable_scenario(
        {
            "schema_version": "scalable3d-scenario-v1",
            "scenario_name": snapshot.scenario_id,
            "scenario_version": snapshot.scenario_version,
            "target_count": 2,
            "resource_count": snapshot.total_resources,
            "recon_count": 1,
            "region_count": snapshot.region_count,
        },
        region_ids=tuple(item.region_id for item in snapshot.regions),
    )
    decisions = tuple(
        RegionalRegionDecision(
            region_id=node.region_id,
            selected_layer=layer,
            action=action,
            reason="test_fixture",
            ownership=RegionOwnershipMetadata(
                region_id=node.region_id,
                owner_id=node.current_owner_id,
                owner_layer=layer,
                owner_role=(
                    "mobile_high_recon"
                    if layer == RegionalAuthorityLayer.SECONDARY
                    else layer.value
                ),
                plan_id=node.plan_id,
                plan_version=node.plan_version,
                epoch=node.epoch,
                lease_expires_at_s=node.lease_expires_at_s,
                active=True,
                task_ids=(),
            ),
            execution_allowed=True,
            fail_closed=False,
            risk_factors=(),
            task_ids=(),
            secondary_candidate_ids=(
                (node.current_owner_id,)
                if layer == RegionalAuthorityLayer.SECONDARY
                else ()
            ),
            selected_secondary_id=(
                node.current_owner_id
                if layer == RegionalAuthorityLayer.SECONDARY
                else None
            ),
        )
        for node in snapshot.regions
    )
    return RegionalFailoverDecision(
        timestamp_s=snapshot.timestamp_s,
        scenario=scenario,
        region_decisions=decisions,
    )


def _context(
    snapshot: RegionResourceSnapshot,
    *,
    center_health: C2Health = C2Health.FAILED,
    secondary_available: bool | None = None,
    partitioned_region_ids: tuple[str, ...] = (),
    active_degradation: bool = False,
) -> RegionResourceSafeAdoptionContext:
    layer = snapshot.regions[0].current_owner_layer
    if secondary_available is None:
        secondary_available = layer == RegionalAuthorityLayer.SECONDARY
    regions = tuple(item.region_id for item in snapshot.regions)
    active_regions = regions if active_degradation else ()
    return RegionResourceSafeAdoptionContext(
        consumption_timestamp_s=1.5,
        center_health=center_health,
        runtime_node_id="MAIN-RUNTIME",
        advisory_version=1,
        partition_generation=7,
        secondary_available_region_ids=(
            regions if secondary_available else ()
        ),
        partitioned_region_ids=partitioned_region_ids,
        active_degradation_region_ids=active_regions,
        active_degradation_evidence_sha256=(
            _sha("active-degradation") if active_regions else None
        ),
    )


def _receipt(
    *,
    payload: dict[str, object],
    source: str,
    destination: str,
    topic: str,
    sequence: int,
    sent_at_s: float,
    arrival_at_s: float,
) -> CommunicationDeliveryReceipt:
    return CommunicationDeliveryReceipt.from_delivered_message(
        _delivered_message(
            payload=payload,
            source=source,
            destination=destination,
            topic=topic,
            sequence=sequence,
            sent_at_s=sent_at_s,
            arrival_at_s=arrival_at_s,
        )
    )


def _delivered_message(
    *,
    payload: dict[str, object],
    source: str,
    destination: str,
    topic: str,
    sequence: int,
    sent_at_s: float,
    arrival_at_s: float,
) -> SimpleNamespace:
    envelope = SimpleNamespace(
        sequence=sequence,
        topic=topic,
        source=source,
        timestamp=sent_at_s,
        schema_version="scalable3d-bus-v1",
        payload=payload,
    )
    delivered = SimpleNamespace(
        source=source,
        destination=destination,
        send_timestamp=sent_at_s,
        arrival_timestamp=arrival_at_s,
        envelope=envelope,
    )
    return delivered


@dataclass(frozen=True)
class _CompleteCase:
    assembler: RegionResourceSafeAdoptionAssembler
    context: RegionResourceSafeAdoptionContext
    preparation: object
    plan: RegionResourceD3PlanReference
    runtime_ack: RegionResourceRuntimeAckEvidence
    owner_delivery: RegionResourceOwnerAckDelivery
    commits: tuple[RegionResourceCoalitionCommitEvidence, ...]
    physical_window: RegionResourcePhysicalWindowEvidence
    evaluated_at_s: float

    def assemble(self, **overrides: object):
        values = {
            "preparation": self.preparation,
            "context": self.context,
            "evaluated_at_s": self.evaluated_at_s,
            "d3_successor_plan": self.plan,
            "runtime_ack": self.runtime_ack,
            "owner_ack_delivery": self.owner_delivery,
            "coalition_commits": self.commits,
            "physical_window": self.physical_window,
        }
        values.update(overrides)
        return self.assembler.assemble(**values)


def _complete_case(
    *,
    layer: RegionalAuthorityLayer = RegionalAuthorityLayer.SECONDARY,
    coalition: bool = False,
) -> _CompleteCase:
    snapshot = _snapshot(layer=layer)
    context = _context(
        snapshot,
        center_health=(
            C2Health.NORMAL
            if layer is RegionalAuthorityLayer.CENTER
            else C2Health.FAILED
        ),
        secondary_available=layer == RegionalAuthorityLayer.SECONDARY,
    )
    assembler = RegionResourceSafeAdoptionAssembler()
    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_candidate(snapshot),
        context=context,
        formal_decision=_formal_decision(snapshot),
    )
    assert preparation.available
    assert preparation.applied_recommendation is not None
    applied = preparation.applied_recommendation

    requirements = (
        (
            RegionResourceCoalitionRequirement(
                global_track_id="GT-001",
                coalition_id="coalition-001",
                coalition_version=1,
                required_member_ids=("INT-1", "INT-2"),
            ),
        )
        if coalition
        else ()
    )
    plan = RegionResourceD3PlanReference(
        plan_id="successor-plan",
        plan_version=4,
        previous_plan_id=applied.source_plan_id,
        previous_plan_version=applied.source_plan_version,
        owner_node_id=applied.owner_node_id,
        owner_layer=applied.owner_layer,
        epoch=applied.epoch,
        created_at_s=1.6,
        valid_until_s=9.5,
        source_advisory_id=applied.advisory.advisory_id,
        source_advisory_version=applied.advisory_version,
        source_advisory_payload_sha256=applied.advisory_payload_sha256,
        plan_payload_sha256=_sha("successor-plan-payload"),
        plan_bus_sequence=100,
        accepted_by_main_runtime=True,
        regional_hint_applied=True,
        stale_version_rejected=True,
        coalition_requirements=requirements,
    )
    runtime_ack = RegionResourceRuntimeAckEvidence(
        code=RegionResourceRuntimeAckCode.APPLIED.value,
        reason="new execution plan applied",
        runtime_advisory_applied_ack_available=True,
        adoption_kind=(
            RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
        ),
        advisory_id=applied.advisory.advisory_id,
        advisory_version=applied.advisory_version,
        source_plan_id=applied.source_plan_id,
        source_plan_version=applied.source_plan_version,
        applied_plan_id=plan.plan_id,
        applied_plan_version=plan.plan_version,
        consumed_at_s=context.consumption_timestamp_s,
        acknowledged_at_s=1.7,
        owner_layer=applied.owner_layer.value,
        owner_node_id=applied.owner_node_id,
        authority_epoch=applied.epoch,
        lease_expires_at_s=applied.lease_expires_at_s,
        source_plan_bus_sequence=plan.plan_bus_sequence,
        advisory_source_plan_bus_sequence=99,
        source_guidance_bus_sequence=101,
        ack_bus_sequence=102,
        assignment_plan_ack_payload_sha256=_sha(
            "runtime-assignment-ack-payload"
        ),
        advisory_payload_sha256=applied.advisory_payload_sha256,
        source_plan_payload_sha256=plan.plan_payload_sha256,
        source_guidance_payload_sha256=_sha("guidance-payload"),
    )
    owner_ack = build_region_resource_owner_plan_ack(
        message_id="owner-ack-001",
        applied_recommendation=applied,
        d3_successor_plan=plan,
        runtime_ack=runtime_ack,
        context=context,
        acknowledged_at_s=1.8,
        accepted=True,
    )
    owner_receipt = _receipt(
        payload=owner_ack.to_transport_payload(),
        source=applied.owner_node_id,
        destination=context.runtime_node_id,
        topic=REGION_RESOURCE_OWNER_ACK_TOPIC,
        sequence=200,
        sent_at_s=owner_ack.acknowledged_at_s,
        arrival_at_s=1.82,
    )
    owner_delivery = RegionResourceOwnerAckDelivery(
        ack=owner_ack,
        receipt=owner_receipt,
    )

    commits: list[RegionResourceCoalitionCommitEvidence] = []
    if coalition:
        requirement = requirements[0]
        deliveries: list[RegionResourceCoalitionAckDelivery] = []
        for index, member_id in enumerate(requirement.required_member_ids):
            member_ack = CoalitionMemberAck(
                resource_id=member_id,
                global_track_id=requirement.global_track_id,
                coalition_id=requirement.coalition_id,
                coalition_version=requirement.coalition_version,
                plan_id=plan.plan_id,
                plan_version=plan.plan_version,
                epoch=plan.epoch,
                can_execute=True,
                evidence_timestamp=1.84 + 0.01 * index,
                valid_until=applied.lease_expires_at_s,
            )
            message_id = f"coalition-ack-{member_id}"
            payload = {
                "schema": REGION_RESOURCE_COALITION_ACK_DELIVERY_SCHEMA,
                "message_id": message_id,
                "message_kind": CausalMessageKind.COALITION_MEMBER_ACK.value,
                "authority_id": applied.owner_node_id,
                "plan_version": plan.plan_version,
                "plan_payload_sha256": plan.plan_payload_sha256,
                "plan_bus_sequence": plan.plan_bus_sequence,
                "epoch": plan.epoch,
                "lease_expires_at_s": applied.lease_expires_at_s,
                "partition_generation": context.partition_generation,
                "member_ack": member_ack.to_dict(),
            }
            receipt = _receipt(
                payload=payload,
                source=member_id,
                destination=applied.owner_node_id,
                topic=REGION_RESOURCE_COALITION_ACK_TOPIC,
                sequence=210 + index,
                sent_at_s=member_ack.evidence_timestamp,
                arrival_at_s=member_ack.evidence_timestamp + 0.005,
            )
            deliveries.append(
                RegionResourceCoalitionAckDelivery(
                    message_id=message_id,
                    authority_id=applied.owner_node_id,
                    plan_payload_sha256=plan.plan_payload_sha256,
                    plan_bus_sequence=plan.plan_bus_sequence,
                    lease_expires_at_s=applied.lease_expires_at_s,
                    partition_generation=context.partition_generation,
                    member_ack=member_ack,
                    receipt=receipt,
                )
            )
        state = CoalitionCommitState(
            global_track_id=requirement.global_track_id,
            coalition_id=requirement.coalition_id,
            coalition_version=requirement.coalition_version,
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            epoch=plan.epoch,
            coordinator_id=applied.owner_node_id,
            coordinator_role=applied.owner_layer.value,
            required_member_ids=requirement.required_member_ids,
            acked_member_ids=requirement.required_member_ids,
            state="executing",
            lease_expires_at=applied.lease_expires_at_s,
            proposed_at=1.7,
            updated_at=2.0,
            committed_at=1.9,
            executing_at=2.0,
            reason="all_required_members_acked",
        )
        commits.append(
            RegionResourceCoalitionCommitEvidence(
                state=state,
                member_ack_deliveries=tuple(deliveries),
            )
        )

    physical_window = RegionResourcePhysicalWindowEvidence(
        window_id="physical-window-001",
        available=True,
        window_start_s=2.05,
        window_end_s=2.2,
        advisory_id=applied.advisory.advisory_id,
        advisory_version=applied.advisory_version,
        advisory_payload_sha256=applied.advisory_payload_sha256,
        applied_plan_id=plan.plan_id,
        applied_plan_version=plan.plan_version,
        runtime_ack_sha256=_canonical_sha256(runtime_ack.to_dict()),
        owner_ack_receipt_id=owner_receipt.receipt_id,
        coalition_commit_sha256=tuple(
            item.immutable_digest for item in commits
        ),
        source_state_payload_sha256=_sha("physical-source-state"),
        post_state_payload_sha256=_sha("physical-post-state"),
        physical_execution_observed=True,
        hard_constraint_violation_count=0,
    )
    return _CompleteCase(
        assembler=assembler,
        context=context,
        preparation=preparation,
        plan=plan,
        runtime_ack=runtime_ack,
        owner_delivery=owner_delivery,
        commits=tuple(commits),
        physical_window=physical_window,
        evaluated_at_s=2.3,
    )


def test_valid_secondary_safe_adoption_is_available_without_benefit_claim() -> None:
    case = _complete_case()

    result = case.assemble()
    applied = result.preparation.applied_recommendation
    assert applied is not None

    assert result.available
    assert result.stage == RegionResourceSafeAdoptionStage.PHYSICAL_WINDOW_AVAILABLE
    assert result.safe_adoption_available
    assert result.identifiable_intervention_available
    assert applied.advisory.total_quota_delta == 0
    assert (
        applied.intervention_evidence.identifiable_intervention_available
    )
    assert any(
        field.startswith("transfer:")
        for field in applied.intervention_evidence.intervention_fields
    )
    assert result.coalition_commit_available
    assert not result.coalition_commit_required
    assert not result.a2_benefit_available
    assert not result.authority_granted
    assert not result.online_truth_used
    assert result.to_a2_runtime_record_prefix()["a2_benefit_available"] is False


@pytest.mark.parametrize(
    "layer",
    (
        RegionalAuthorityLayer.CENTER,
        RegionalAuthorityLayer.SECONDARY,
        RegionalAuthorityLayer.DISTRIBUTED,
    ),
)
def test_all_authority_layers_keep_safe_adoption_non_authorizing(
    layer: RegionalAuthorityLayer,
) -> None:
    result = _complete_case(layer=layer).assemble()

    assert result.available
    assert result.preparation.applied_recommendation is not None
    assert (
        result.preparation.applied_recommendation.owner_layer
        is layer
    )
    assert result.authority_granted is False
    assert result.a2_benefit_available is False
    assert result.online_truth_used is False


def test_safe_adoption_preparation_rejects_non_boolean_availability() -> None:
    with pytest.raises(TypeError, match="available must be a bool"):
        RegionResourceSafeAdoptionPreparation(
            available="false",  # type: ignore[arg-type]
            stage=RegionResourceSafeAdoptionStage.CANDIDATE_REJECTED,
            reason_codes=("invalid",),
        )

    valid = _complete_case().preparation
    with pytest.raises(
        ValueError,
        match="unavailable preparation cannot carry",
    ):
        replace(
            valid,
            available=False,
            stage=RegionResourceSafeAdoptionStage.CANDIDATE_REJECTED,
            reason_codes=("invalid",),
        )


def test_noop_projection_is_link_evidence_not_actual_a2_adoption() -> None:
    snapshot = _snapshot()
    context = _context(snapshot, secondary_available=True)
    assembler = RegionResourceSafeAdoptionAssembler()
    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_noop_candidate(snapshot),
        context=context,
        formal_decision=_formal_decision(snapshot),
    )

    assert preparation.available
    applied = preparation.applied_recommendation
    assert applied is not None
    intervention = applied.intervention_evidence
    assert applied.advisory.total_quota_delta == 0
    assert not applied.advisory.transfers
    assert not intervention.identifiable_intervention_available
    assert intervention.intervention_fields == ()
    assert intervention.reason_codes == (
        "no_d3_consumable_regional_intervention",
    )
    assert (
        intervention.baseline_payload_sha256
        == intervention.projected_payload_sha256
    )

    result = assembler.assemble(
        preparation=preparation,
        context=context,
        evaluated_at_s=1.6,
    )

    assert not result.available
    assert (
        result.stage
        == RegionResourceSafeAdoptionStage.SAFE_ADOPTION_REJECTED
    )
    assert result.reason_codes == (
        "identifiable_regional_intervention_missing",
    )
    assert result.projection_available
    assert not result.identifiable_intervention_available
    assert not result.d3_successor_plan_available
    assert not result.physical_window_available
    assert not result.safe_adoption_available
    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="safe_adoption_source_intervention_missing",
    ):
        RegionResourceA2SafeAdoptionAuditSource.from_value(result)


def test_development_adapter_creates_identifiable_bounded_intervention() -> None:
    """The probe makes the chain testable but grants no assist or authority."""

    snapshot = _snapshot()
    adapter = _development_adapter(snapshot)
    candidate = adapter.recommend_raw(snapshot)

    assert candidate.policy_name == (
        REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME
    )
    assert candidate.source is RecommendationSource.LEARNED
    assert not candidate.transfers
    request_actions = [
        item for item in candidate.actions if item.request_replan
    ]
    assert len(request_actions) == 1
    assert not any(item.hold for item in candidate.actions)
    assert any(
        REGION_RESOURCE_DEVELOPMENT_INTERVENTION_REASON in item.reasons
        and REGION_RESOURCE_DEVELOPMENT_REQUEST_REPLAN_REASON
        in item.reasons
        for item in request_actions
    )
    assert adapter.development_only
    assert adapter.maximum_advisor_mode is AdvisorMode.SHADOW
    assert not adapter.assist_enabled
    assert not adapter.authority_enabled
    assert not adapter.control_enabled
    assert not adapter.model_admitted
    assert not adapter.actual_system_benefit_claimed

    assembler = RegionResourceSafeAdoptionAssembler()
    context = _context(snapshot, secondary_available=True)
    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=candidate,
        context=context,
        formal_decision=_formal_decision(snapshot),
    )
    assert preparation.available
    applied = preparation.applied_recommendation
    assert applied is not None
    assert applied.advisory.total_quota_delta == 0
    assert applied.advisory.total_resources_before == (
        applied.advisory.total_resources_after
    )
    assert applied.intervention_evidence.identifiable_intervention_available
    assert any(
        field.endswith(":request_replan")
        for field in applied.intervention_evidence.intervention_fields
    )

    result = assembler.assemble(
        preparation=preparation,
        context=context,
        evaluated_at_s=1.6,
    )
    assert not result.available
    assert result.stage is RegionResourceSafeAdoptionStage.AWAITING_D3_PLAN
    assert result.reason_codes == ("d3_successor_plan_missing",)
    assert result.identifiable_intervention_available
    assert not result.authority_granted
    assert not result.a2_benefit_available


def test_development_adapter_retries_when_raw_reserve_projects_to_noop() -> None:
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        authority_digest="",
        regions=(
            replace(snapshot.regions[0], committed_resources=2),
            snapshot.regions[1],
        ),
    )
    base = _noop_candidate(snapshot)
    raw_reserve_change = replace(
        base,
        actions=(
            replace(base.actions[0], reserve_ratio=0.6),
            base.actions[1],
        ),
    )
    assembler = RegionResourceSafeAdoptionAssembler()
    context = _context(snapshot, secondary_available=True)
    base_preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=raw_reserve_change,
        context=context,
        formal_decision=_formal_decision(snapshot),
    )

    assert base_preparation.available
    base_applied = base_preparation.applied_recommendation
    assert base_applied is not None
    assert not (
        base_applied.intervention_evidence
        .identifiable_intervention_available
    )
    assert (
        base_applied.intervention_evidence.reason_codes
        == ("no_d3_consumable_regional_intervention",)
    )

    candidate = _development_adapter(
        snapshot,
        raw_reserve_change,
    ).recommend_raw(snapshot)

    assert candidate.policy_name == (
        REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME
    )
    assert not candidate.transfers
    assert sum(action.request_replan for action in candidate.actions) == 1
    assert not any(action.hold for action in candidate.actions)

    preparation = RegionResourceSafeAdoptionAssembler().prepare(
        snapshot=snapshot,
        candidate=candidate,
        context=context,
        formal_decision=_formal_decision(snapshot),
    )
    assert preparation.available
    applied = preparation.applied_recommendation
    assert applied is not None
    assert (
        applied.intervention_evidence
        .identifiable_intervention_available
    )
    assert any(
        field.endswith(":request_replan")
        for field in applied.intervention_evidence.intervention_fields
    )


def test_development_adapter_uses_formal_commitments_before_selection() -> None:
    snapshot = _snapshot()
    base = _noop_candidate(snapshot)
    raw_reserve_change = replace(
        base,
        actions=(
            replace(base.actions[0], reserve_ratio=0.6),
            base.actions[1],
        ),
    )
    formal = _formal_decision(snapshot)
    committed = CoalitionCommitSummary(
        task_id="formal-aggregate-task",
        global_track_id="GT-FORMAL",
        commit_required=True,
        state="committed",
        coordinator_id=snapshot.regions[0].current_owner_id,
        required_member_ids=("INT-1", "INT-2"),
        acked_member_ids=("INT-1", "INT-2"),
        missing_member_ids=(),
        lease_expires_at_s=9.0,
        atomic_committed=True,
        execution_authorized=True,
        reason="all_members_acked",
    )
    formal = replace(
        formal,
        region_decisions=(
            replace(
                formal.region_decisions[0],
                coalition_commits=(committed,),
            ),
            formal.region_decisions[1],
        ),
    )
    adapter = _development_adapter(snapshot, raw_reserve_change)

    without_formal = adapter.recommend_raw(snapshot)
    assert without_formal.policy_name == "held-out-graph-policy"
    assert not any(
        action.request_replan for action in without_formal.actions
    )

    candidate = adapter.recommend_raw(
        snapshot,
        formal_decision=formal,
    )

    assert candidate.policy_name == (
        REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME
    )
    assert sum(action.request_replan for action in candidate.actions) == 1
    assert not any(action.hold for action in candidate.actions)
    assert not candidate.transfers

    context = _context(snapshot, secondary_available=True)
    preparation = RegionResourceSafeAdoptionAssembler().prepare(
        snapshot=snapshot,
        candidate=candidate,
        context=context,
        formal_decision=formal,
    )
    assert preparation.available
    applied = preparation.applied_recommendation
    assert applied is not None
    assert (
        applied.intervention_evidence
        .identifiable_intervention_available
    )
    assert any(
        field.endswith(":request_replan")
        for field in applied.intervention_evidence.intervention_fields
    )

    advisor_result = RegionResourceAdvisor(
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            minimum_confidence=0.0,
        ),
        learned_policy=adapter,
    ).advise(
        snapshot,
        formal_decision=formal,
        unseen_seed_count=20,
    )
    assert advisor_result.effective_mode is AdvisorMode.SHADOW
    assert not advisor_result.assist_eligible
    assert advisor_result.formal_decision_unchanged
    assert advisor_result.recommendation is not None
    assert sum(
        action.request_replan
        for action in advisor_result.recommendation.actions
    ) == 1


def test_development_adapter_uses_bounded_transfer_after_request_is_resolved() -> None:
    snapshot = _snapshot()
    transfer_case = replace(
        snapshot,
        regions=(
            replace(
                snapshot.regions[0],
                target_demand=3.0,
                high_threat_backlog=0.0,
            ),
            snapshot.regions[1],
        ),
    )
    candidate = _development_adapter(transfer_case).recommend_raw(
        transfer_case
    )

    assert sum(item.resource_count for item in candidate.transfers) == 1
    assert not any(item.hold for item in candidate.actions)
    assert not any(item.request_replan for item in candidate.actions)
    assert all(
        REGION_RESOURCE_DEVELOPMENT_TRANSFER_REASON in item.reasons
        for item in candidate.transfers
    )


@pytest.mark.parametrize("seed", (1000, 1002, 1007, 1009, 1013))
def test_request_only_probe_does_not_hold_committed_region(seed: int) -> None:
    snapshot = _snapshot()
    committed = replace(
        snapshot,
        seed=seed,
        authority_digest="",
        regions=(
            replace(snapshot.regions[0], committed_resources=1),
            snapshot.regions[1],
        ),
    )
    candidate = _development_adapter(committed).recommend_raw(committed)

    assert not candidate.transfers
    assert not any(action.hold for action in candidate.actions)
    assert sum(action.request_replan for action in candidate.actions) == 1
    assert next(
        action
        for action in candidate.actions
        if action.region_id == committed.regions[0].region_id
    ).request_replan

    assembler = RegionResourceSafeAdoptionAssembler()
    context = _context(committed, secondary_available=True)
    preparation = assembler.prepare(
        snapshot=committed,
        candidate=candidate,
        context=context,
        formal_decision=_formal_decision(committed),
    )
    assert preparation.available
    result = assembler.assemble(
        preparation=preparation,
        context=context,
        evaluated_at_s=1.6,
    )
    assert result.stage is RegionResourceSafeAdoptionStage.AWAITING_D3_PLAN
    assert result.reason_codes == ("d3_successor_plan_missing",)
    assert result.identifiable_intervention_available


def test_development_hold_probe_requires_uncommitted_region() -> None:
    snapshot = _snapshot()
    balanced_nodes = tuple(
        replace(
            node,
            target_demand=0.0,
            high_threat_backlog=0.0,
            d1_uncertainty=0.1,
            d2_uncertainty=0.1,
            d5_visibility=0.9,
            d5_consistency=0.9,
            available_resources=4,
            reserve_resources=1,
            degradation_failed=(index == 0),
        )
        for index, node in enumerate(snapshot.regions)
    )
    eligible = replace(snapshot, regions=balanced_nodes)

    def adapter_for(
        case: RegionResourceSnapshot,
    ) -> ConstrainedDevelopmentRegionResourceAdapter:
        return ConstrainedDevelopmentRegionResourceAdapter(
            _StaticNoopLearnedPolicy(_noop_candidate(case)),
            config=RegionResourceDevelopmentInterventionConfig(
                enabled=True,
                run_label="safe-hold-development",
                allowed_scenario_ids=(case.scenario_id,),
                allow_request_replan=False,
            ),
        )

    hold_candidate = adapter_for(eligible).recommend_raw(eligible)
    held = [action for action in hold_candidate.actions if action.hold]
    assert len(held) == 1
    assert held[0].region_id == eligible.regions[0].region_id
    assert REGION_RESOURCE_DEVELOPMENT_HOLD_REASON in held[0].reasons

    committed = replace(
        eligible,
        authority_digest="",
        regions=(
            replace(eligible.regions[0], committed_resources=1),
            eligible.regions[1],
        ),
    )
    no_hold_candidate = adapter_for(committed).recommend_raw(committed)
    assert not any(action.hold for action in no_hold_candidate.actions)
    assert not any(
        action.request_replan for action in no_hold_candidate.actions
    )
    assert not no_hold_candidate.transfers


def test_development_adapter_keeps_balanced_legal_case_as_noop() -> None:
    snapshot = _snapshot()
    balanced = replace(
        snapshot,
        regions=tuple(
            replace(
                node,
                target_demand=0.0,
                high_threat_backlog=0.0,
                d1_uncertainty=0.1,
                d2_uncertainty=0.1,
                d5_visibility=0.9,
                d5_consistency=0.9,
                available_resources=4,
                reserve_resources=1,
            )
            for node in snapshot.regions
        ),
    )
    adapter = _development_adapter(balanced)
    candidate = adapter.recommend_raw(balanced)
    assert not candidate.transfers
    assert candidate.policy_name == "held-out-graph-policy"

    assembler = RegionResourceSafeAdoptionAssembler()
    context = _context(balanced, secondary_available=True)
    preparation = assembler.prepare(
        snapshot=balanced,
        candidate=candidate,
        context=context,
        formal_decision=_formal_decision(balanced),
    )
    result = assembler.assemble(
        preparation=preparation,
        context=context,
        evaluated_at_s=1.6,
    )
    assert result.stage is RegionResourceSafeAdoptionStage.SAFE_ADOPTION_REJECTED
    assert result.reason_codes == (
        "identifiable_regional_intervention_missing",
    )
    assert not result.identifiable_intervention_available


def test_development_force_request_is_explicit_and_request_only() -> None:
    snapshot = _snapshot()
    balanced = replace(
        snapshot,
        authority_digest="",
        regions=tuple(
            replace(
                node,
                target_demand=0.0,
                high_threat_backlog=0.0,
                d1_uncertainty=0.1,
                d2_uncertainty=0.1,
                d5_visibility=0.9,
                d5_consistency=0.9,
                committed_resources=(
                    node.available_resources - node.reserve_resources
                ),
            )
            for node in snapshot.regions
        ),
    )
    adapter = ConstrainedDevelopmentRegionResourceAdapter(
        _StaticNoopLearnedPolicy(_noop_candidate(balanced)),
        config=RegionResourceDevelopmentInterventionConfig(
            enabled=True,
            run_label="forced-request-development-probe",
            allowed_scenario_ids=(balanced.scenario_id,),
            force_request_replan_on_projected_noop=True,
        ),
    )

    candidate = adapter.recommend_raw(
        balanced,
        formal_decision=_formal_decision(balanced),
    )

    assert candidate.policy_name == (
        REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME
    )
    assert sum(action.request_replan for action in candidate.actions) == 1
    assert not any(action.hold for action in candidate.actions)
    assert not candidate.transfers
    preparation = RegionResourceSafeAdoptionAssembler().prepare(
        snapshot=balanced,
        candidate=candidate,
        context=_context(balanced, secondary_available=True),
        formal_decision=_formal_decision(balanced),
    )
    assert preparation.available
    applied = preparation.applied_recommendation
    assert applied is not None
    assert (
        applied.intervention_evidence
        .identifiable_intervention_available
    )
    assert any(
        field.endswith(":request_replan")
        for field in applied.intervention_evidence.intervention_fields
    )


def test_development_adapter_does_not_repair_stale_authority_binding() -> None:
    snapshot = _snapshot()
    base = _noop_candidate(snapshot)
    stale = replace(
        base,
        actions=(
            replace(base.actions[0], expected_epoch=base.actions[0].expected_epoch - 1),
            *base.actions[1:],
        ),
    )
    candidate = _development_adapter(snapshot, stale).recommend_raw(snapshot)
    assembler = RegionResourceSafeAdoptionAssembler()
    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=candidate,
        context=_context(snapshot, secondary_available=True),
        formal_decision=_formal_decision(snapshot),
    )

    assert not preparation.available
    assert preparation.stage is RegionResourceSafeAdoptionStage.CANDIDATE_REJECTED
    assert preparation.reason_codes == (
        "deterministic_projection_rejected_or_modified",
    )


def test_development_adapter_remains_shadow_when_assist_is_requested() -> None:
    snapshot = _snapshot()
    advisor = RegionResourceAdvisor(
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.ASSIST,
            minimum_confidence=0.0,
            minimum_unseen_seeds=1,
        ),
        learned_policy=_development_adapter(snapshot),
    )

    result = advisor.advise(
        snapshot,
        formal_decision=_formal_decision(snapshot),
        unseen_seed_count=20,
    )

    assert result.effective_mode is AdvisorMode.SHADOW
    assert not result.assist_eligible
    assert result.recommendation is not None
    assert result.recommendation.fallback_reason == "model_bundle_shadow_only"


def test_development_adapter_requires_explicit_opt_in_scope() -> None:
    with pytest.raises(
        TypeError,
        match="force_request_replan_on_projected_noop must be a bool",
    ):
        RegionResourceDevelopmentInterventionConfig(
            force_request_replan_on_projected_noop=1,
        )
    with pytest.raises(ValueError, match="requires run_label"):
        RegionResourceDevelopmentInterventionConfig(
            enabled=True,
            allowed_scenario_ids=("scenario-safe-adoption",),
        )
    with pytest.raises(ValueError, match="requires a scenario allowlist"):
        RegionResourceDevelopmentInterventionConfig(
            enabled=True,
            run_label="missing-scope",
        )

    snapshot = _snapshot()
    disabled = ConstrainedDevelopmentRegionResourceAdapter(
        _StaticNoopLearnedPolicy(_noop_candidate(snapshot)),
        config=RegionResourceDevelopmentInterventionConfig(),
    )
    with pytest.raises(ValueError, match="development_intervention_disabled"):
        disabled.recommend_raw(snapshot)


def test_unrelated_successor_chain_cannot_turn_noop_into_adoption() -> None:
    snapshot = _snapshot()
    context = _context(snapshot, secondary_available=True)
    assembler = RegionResourceSafeAdoptionAssembler()
    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_noop_candidate(snapshot),
        context=context,
        formal_decision=_formal_decision(snapshot),
    )
    unrelated = _complete_case()

    result = assembler.assemble(
        preparation=preparation,
        context=context,
        evaluated_at_s=unrelated.evaluated_at_s,
        d3_successor_plan=unrelated.plan,
        runtime_ack=unrelated.runtime_ack,
        owner_ack_delivery=unrelated.owner_delivery,
        coalition_commits=unrelated.commits,
        physical_window=unrelated.physical_window,
    )

    assert not result.safe_adoption_available
    assert result.reason_codes == (
        "identifiable_regional_intervention_missing",
    )
    assert result.projection_available
    assert not result.identifiable_intervention_available
    assert result.d3_successor_plan is None
    assert result.runtime_ack is None
    assert result.owner_ack_delivery is None
    assert result.coalition_commits == ()
    assert result.physical_window is None


def test_owner_ack_receipt_can_support_a_later_physical_window() -> None:
    case = _complete_case()

    awaiting_window = case.assemble(
        evaluated_at_s=2.05,
        physical_window=None,
    )
    completed = case.assemble()

    assert not awaiting_window.available
    assert (
        awaiting_window.stage
        == RegionResourceSafeAdoptionStage.AWAITING_PHYSICAL_WINDOW
    )
    assert awaiting_window.owner_ack_available
    assert completed.available
    assert (
        completed.stage
        == RegionResourceSafeAdoptionStage.PHYSICAL_WINDOW_AVAILABLE
    )
    assert completed.owner_ack_delivery == case.owner_delivery
    assert completed.physical_window == case.physical_window


def test_public_owner_ack_api_round_trips_and_validates_runtime_binding() -> None:
    case = _complete_case()
    ack = case.owner_delivery.ack
    delivered = _delivered_message(
        payload=ack.to_transport_payload(),
        source=ack.owner_node_id,
        destination=case.context.runtime_node_id,
        topic=REGION_RESOURCE_OWNER_ACK_TOPIC,
        sequence=case.owner_delivery.receipt.transport_sequence,
        sent_at_s=ack.acknowledged_at_s,
        arrival_at_s=case.owner_delivery.receipt.arrival_timestamp_s,
    )

    parsed_ack = RegionResourceOwnerPlanAck.from_transport_payload(
        ack.to_transport_payload()
    )
    parsed_delivery = RegionResourceOwnerAckDelivery.from_delivered_message(
        delivered
    )
    validation = validate_region_resource_owner_ack_delivery(
        parsed_delivery,
        expected_ack=ack,
        expected_destination_node_id=case.context.runtime_node_id,
        decision_timestamp_s=case.evaluated_at_s,
    )

    assert parsed_ack == ack
    assert parsed_delivery == case.owner_delivery
    assert validation.accepted
    assert not validation.authority_granted
    assert validation.communication_validation is not None
    assert validation.communication_validation.accepted
    assert (
        ack.runtime_assignment_ack_payload_sha256
        == case.runtime_ack.assignment_plan_ack_payload_sha256
    )
    assert (
        ack.runtime_assignment_ack_bus_sequence
        == case.runtime_ack.ack_bus_sequence
    )


def test_public_owner_ack_parser_rejects_missing_runtime_ack_binding() -> None:
    payload = _complete_case().owner_delivery.ack.to_transport_payload()
    payload.pop("runtime_assignment_ack_payload_sha256")

    with pytest.raises(ValueError, match="fields mismatch"):
        RegionResourceOwnerPlanAck.from_transport_payload(payload)


def test_valid_peer_coalition_requires_all_delivered_member_acks() -> None:
    case = _complete_case(
        layer=RegionalAuthorityLayer.DISTRIBUTED,
        coalition=True,
    )

    result = case.assemble()

    assert result.available
    assert result.coalition_commit_required
    assert result.coalition_commit_available
    assert len(result.coalition_commits) == 1


def test_public_coalition_ack_api_requires_strict_nested_member_contract() -> None:
    case = _complete_case(
        layer=RegionalAuthorityLayer.DISTRIBUTED,
        coalition=True,
    )
    delivery = case.commits[0].member_ack_deliveries[0]
    receipt = delivery.receipt
    delivered = _delivered_message(
        payload=delivery.to_transport_payload(),
        source=delivery.member_ack.resource_id,
        destination=delivery.authority_id,
        topic=REGION_RESOURCE_COALITION_ACK_TOPIC,
        sequence=receipt.transport_sequence,
        sent_at_s=delivery.member_ack.evidence_timestamp,
        arrival_at_s=receipt.arrival_timestamp_s,
    )

    parsed = RegionResourceCoalitionAckDelivery.from_delivered_message(
        delivered
    )
    validation = validate_region_resource_coalition_ack_delivery(
        parsed,
        expected_member_ack=delivery.member_ack,
        expected_authority_id=delivery.authority_id,
        expected_plan_payload_sha256=delivery.plan_payload_sha256,
        expected_plan_bus_sequence=delivery.plan_bus_sequence,
        expected_lease_expires_at_s=delivery.lease_expires_at_s,
        expected_partition_generation=delivery.partition_generation,
        expected_destination_node_id=delivery.authority_id,
        decision_timestamp_s=case.commits[0].state.committed_at,
        expected_message_id=delivery.message_id,
    )

    assert parsed == delivery
    assert validation.accepted
    assert not validation.authority_granted

    malformed = delivery.to_transport_payload()
    malformed["member_ack"] = dict(malformed["member_ack"])
    malformed["member_ack"].pop("global_track_id")
    malformed_delivered = _delivered_message(
        payload=malformed,
        source=delivery.member_ack.resource_id,
        destination=delivery.authority_id,
        topic=REGION_RESOURCE_COALITION_ACK_TOPIC,
        sequence=receipt.transport_sequence + 100,
        sent_at_s=delivery.member_ack.evidence_timestamp,
        arrival_at_s=receipt.arrival_timestamp_s,
    )
    with pytest.raises(ValueError, match="fields mismatch"):
        RegionResourceCoalitionAckDelivery.from_delivered_message(
            malformed_delivered
        )

    false_text = delivery.to_transport_payload()
    false_text["member_ack"] = dict(false_text["member_ack"])
    false_text["member_ack"]["can_execute"] = "false"
    false_text_delivered = _delivered_message(
        payload=false_text,
        source=delivery.member_ack.resource_id,
        destination=delivery.authority_id,
        topic=REGION_RESOURCE_COALITION_ACK_TOPIC,
        sequence=receipt.transport_sequence + 101,
        sent_at_s=delivery.member_ack.evidence_timestamp,
        arrival_at_s=receipt.arrival_timestamp_s,
    )
    with pytest.raises(TypeError, match="can_execute must be a bool"):
        RegionResourceCoalitionAckDelivery.from_delivered_message(
            false_text_delivered
        )

    with pytest.raises(ValueError, match="executing_at must be finite"):
        replace(
            case.commits[0].state,
            executing_at=float("nan"),
        )


@pytest.mark.parametrize(
    ("overrides", "stage", "reason"),
    (
        (
            {"d3_successor_plan": None},
            RegionResourceSafeAdoptionStage.AWAITING_D3_PLAN,
            "d3_successor_plan_missing",
        ),
        (
            {"runtime_ack": None},
            RegionResourceSafeAdoptionStage.AWAITING_RUNTIME_ACK,
            "runtime_ack_missing",
        ),
        (
            {"owner_ack_delivery": None},
            RegionResourceSafeAdoptionStage.AWAITING_OWNER_ACK,
            "owner_ack_missing",
        ),
        (
            {"physical_window": None},
            RegionResourceSafeAdoptionStage.AWAITING_PHYSICAL_WINDOW,
            "physical_window_missing",
        ),
    ),
)
def test_missing_runtime_evidence_stays_unavailable(
    overrides: dict[str, object],
    stage: RegionResourceSafeAdoptionStage,
    reason: str,
) -> None:
    case = _complete_case()

    result = case.assemble(**overrides)

    assert not result.available
    assert result.stage == stage
    assert result.reason_codes == (reason,)


def test_missing_required_coalition_commit_stays_unavailable() -> None:
    case = _complete_case(coalition=True)

    result = case.assemble(coalition_commits=())

    assert not result.available
    assert (
        result.stage
        == RegionResourceSafeAdoptionStage.AWAITING_COALITION_COMMIT
    )
    assert result.reason_codes == ("coalition_commit_missing",)


def test_stale_successor_epoch_is_rejected() -> None:
    case = _complete_case()
    stale_plan = replace(case.plan, epoch=case.plan.epoch - 1)

    result = case.assemble(d3_successor_plan=stale_plan)

    assert not result.available
    assert result.stage == RegionResourceSafeAdoptionStage.SAFE_ADOPTION_REJECTED
    assert result.reason_codes == ("successor_plan_epoch_stale",)


def test_successor_plan_version_must_be_strictly_new() -> None:
    case = _complete_case()
    stale_plan = replace(
        case.plan,
        plan_version=case.plan.previous_plan_version,
    )

    result = case.assemble(d3_successor_plan=stale_plan)

    assert not result.available
    assert result.reason_codes == ("successor_plan_version_not_strictly_new",)


def test_expired_authority_lease_blocks_final_adoption() -> None:
    case = _complete_case()

    result = case.assemble(evaluated_at_s=10.0)

    assert not result.available
    assert result.reason_codes == ("authority_lease_expired",)


@pytest.mark.parametrize(
    ("edge_capacity", "edge_id", "transfer_count"),
    (
        (3, "edge-does-not-exist", 1),
        (1, "edge-ab", 2),
    ),
)
def test_illegal_or_over_capacity_transfer_fails_projection(
    edge_capacity: int,
    edge_id: str,
    transfer_count: int,
) -> None:
    snapshot = _snapshot(edge_capacity=edge_capacity)
    assembler = RegionResourceSafeAdoptionAssembler()

    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_candidate(
            snapshot,
            edge_id=edge_id,
            transfer_count=transfer_count,
        ),
        context=_context(snapshot),
        formal_decision=_formal_decision(snapshot),
    )

    assert not preparation.available
    assert preparation.reason_codes == (
        "deterministic_projection_rejected_or_modified",
    )


def test_network_partition_blocks_adoption_before_projection() -> None:
    snapshot = _snapshot()
    assembler = RegionResourceSafeAdoptionAssembler()

    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_candidate(snapshot),
        context=_context(
            snapshot,
            partitioned_region_ids=("region-a",),
        ),
        formal_decision=_formal_decision(snapshot),
    )

    assert not preparation.available
    assert preparation.reason_codes == ("network_partition_blocks_adoption",)


def test_center_normal_rejects_degraded_owner() -> None:
    snapshot = _snapshot(layer=RegionalAuthorityLayer.SECONDARY)
    assembler = RegionResourceSafeAdoptionAssembler()

    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_candidate(snapshot),
        context=_context(snapshot, center_health=C2Health.NORMAL),
        formal_decision=_formal_decision(snapshot),
    )

    assert not preparation.available
    assert preparation.reason_codes == (
        "center_normal_degradation_forbidden",
    )


def test_center_failure_prioritizes_available_secondary_over_peer() -> None:
    snapshot = _snapshot(layer=RegionalAuthorityLayer.DISTRIBUTED)
    assembler = RegionResourceSafeAdoptionAssembler()

    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_candidate(snapshot),
        context=_context(snapshot, secondary_available=True),
        formal_decision=_formal_decision(snapshot),
    )

    assert not preparation.available
    assert preparation.reason_codes == ("secondary_priority_violation",)


def test_active_degradation_requires_explicit_evidence() -> None:
    snapshot = _snapshot(layer=RegionalAuthorityLayer.SECONDARY)
    assembler = RegionResourceSafeAdoptionAssembler()

    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_candidate(snapshot),
        context=_context(
            snapshot,
            center_health=C2Health.DEGRADED,
            active_degradation=False,
        ),
        formal_decision=_formal_decision(snapshot),
    )

    assert not preparation.available
    assert preparation.reason_codes == (
        "active_degradation_evidence_missing",
    )


@pytest.mark.parametrize(
    "forbidden_key",
    ("truth_id", "outcome", "offline_outcome", "reward"),
)
def test_online_truth_or_outcome_fields_are_rejected(
    forbidden_key: str,
) -> None:
    snapshot = _snapshot()
    context = _context(snapshot).to_dict()
    context[forbidden_key] = "forbidden"
    assembler = RegionResourceSafeAdoptionAssembler()

    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_candidate(snapshot),
        context=context,
        formal_decision=_formal_decision(snapshot),
    )

    assert not preparation.available
    assert preparation.reason_codes == ("truth_or_outcome_field_rejected",)


@pytest.mark.parametrize(
    ("source", "fallback_reason", "confidence", "reason"),
    (
        (
            RecommendationSource.RULE,
            "runtime_rule_fallback",
            0.9,
            "candidate_not_learned",
        ),
        (
            RecommendationSource.LEARNED,
            "runtime_rule_fallback",
            0.9,
            "deterministic_rule_fallback_not_candidate_adoption",
        ),
        (
            RecommendationSource.LEARNED,
            None,
            0.59,
            "candidate_below_frozen_confidence_threshold",
        ),
    ),
)
def test_non_candidate_or_below_threshold_advice_is_rejected(
    source: RecommendationSource,
    fallback_reason: str | None,
    confidence: float,
    reason: str,
) -> None:
    snapshot = _snapshot()
    assembler = RegionResourceSafeAdoptionAssembler()

    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=_candidate(
            snapshot,
            source=source,
            fallback_reason=fallback_reason,
            confidence=confidence,
        ),
        context=_context(snapshot),
        formal_decision=_formal_decision(snapshot),
    )

    assert not preparation.available
    assert preparation.reason_codes == (reason,)


def test_runtime_ack_must_hash_bind_successor_plan() -> None:
    case = _complete_case()
    mismatched_ack = replace(
        case.runtime_ack,
        source_plan_payload_sha256=_sha("different-plan-payload"),
    )

    result = case.assemble(runtime_ack=mismatched_ack)

    assert not result.available
    assert result.reason_codes == (
        "runtime_ack_successor_plan_source_mismatch",
    )


def test_owner_ack_must_hash_bind_successor_plan() -> None:
    case = _complete_case()
    mismatched_ack = replace(
        case.owner_delivery.ack,
        applied_plan_payload_sha256=_sha("different-plan-payload"),
    )
    mismatched_receipt = _receipt(
        payload=mismatched_ack.to_transport_payload(),
        source=mismatched_ack.owner_node_id,
        destination=case.context.runtime_node_id,
        topic=REGION_RESOURCE_OWNER_ACK_TOPIC,
        sequence=201,
        sent_at_s=mismatched_ack.acknowledged_at_s,
        arrival_at_s=1.82,
    )

    result = case.assemble(
        owner_ack_delivery=RegionResourceOwnerAckDelivery(
            ack=mismatched_ack,
            receipt=mismatched_receipt,
        )
    )

    assert not result.available
    assert result.reason_codes == ("owner_ack_cross_binding_invalid",)


def test_owner_ack_must_hash_bind_runtime_assignment_ack() -> None:
    case = _complete_case()
    mismatched_ack = replace(
        case.owner_delivery.ack,
        runtime_assignment_ack_payload_sha256=_sha(
            "different-runtime-assignment-ack"
        ),
    )
    mismatched_receipt = _receipt(
        payload=mismatched_ack.to_transport_payload(),
        source=mismatched_ack.owner_node_id,
        destination=case.context.runtime_node_id,
        topic=REGION_RESOURCE_OWNER_ACK_TOPIC,
        sequence=202,
        sent_at_s=mismatched_ack.acknowledged_at_s,
        arrival_at_s=1.82,
    )

    result = case.assemble(
        owner_ack_delivery=RegionResourceOwnerAckDelivery(
            ack=mismatched_ack,
            receipt=mismatched_receipt,
        )
    )

    assert not result.available
    assert result.reason_codes == ("owner_ack_cross_binding_invalid",)


def test_physical_window_must_hash_bind_runtime_ack() -> None:
    case = _complete_case()
    mismatched_window = replace(
        case.physical_window,
        runtime_ack_sha256=_sha("different-runtime-ack"),
    )

    result = case.assemble(physical_window=mismatched_window)

    assert not result.available
    assert result.reason_codes == ("physical_window_cross_binding_invalid",)


def test_exact_replay_is_deterministic_and_idempotent() -> None:
    case = _complete_case()

    first = case.assemble()
    second = case.assemble()

    assert second is first
    assert second.content_sha256 == first.content_sha256
    assert second.to_dict() == first.to_dict()


def _a2_benefit_audit_case() -> tuple[
    object,
    RegionResourceA2AuditContext,
    RegionResourceA2AuditWindowReference,
    RegionResourceA2AuditWindowReference,
]:
    case = _complete_case()
    evidence = case.assemble()
    applied = evidence.preparation.applied_recommendation
    assert applied is not None
    assert evidence.d3_successor_plan is not None
    assert evidence.physical_window is not None
    physical = evidence.physical_window
    context = RegionResourceA2AuditContext(
        comparison_key=(
            f"{applied.advisory.scenario_id}|"
            f"{applied.advisory.scenario_version}|5|"
            f"{applied.advisory.seed}|window-000"
        ),
        scenario_id=applied.advisory.scenario_id,
        scenario_version=applied.advisory.scenario_version,
        scale=5,
        seed=applied.advisory.seed,
        paired_window_id="window-000",
        paired_exogenous_config_sha256=_sha(
            "paired-exogenous-config-seed-101"
        ),
        required_window_duration_s=(
            physical.window_end_s - physical.window_start_s
        ),
    )
    candidate = RegionResourceA2AuditWindowReference(
        arm=RegionResourceA2AuditArm.A2,
        comparison_key=context.comparison_key,
        scenario_id=context.scenario_id,
        scenario_version=context.scenario_version,
        scale=context.scale,
        seed=context.seed,
        paired_window_id=context.paired_window_id,
        paired_exogenous_config_sha256=(
            context.paired_exogenous_config_sha256
        ),
        execution_arm_id="episode-a2-seed-101",
        window_id=physical.window_id,
        source_event_log_id="episode-a2-seed-101/events",
        source_event_log_sha256=_sha(
            "episode-a2-seed-101:event-log"
        ),
        window_start_s=physical.window_start_s,
        window_end_s=physical.window_end_s,
        plan_id=physical.applied_plan_id,
        plan_version=physical.applied_plan_version,
        plan_valid_until_s=evidence.d3_successor_plan.valid_until_s,
        authority_lease_expires_at_s=applied.lease_expires_at_s,
        physical_window_payload_sha256=_canonical_sha256(
            physical.to_dict()
        ),
        policy_name=applied.advisory.policy_name,
        policy_version=applied.advisory.policy_version,
        source_safe_adoption_evidence_sha256=evidence.content_sha256,
        source_advisory_id=physical.advisory_id,
        source_advisory_version=physical.advisory_version,
        physical_execution_observed=True,
        window_complete=True,
        hard_constraint_violation_count=0,
    )
    r0_window = RegionResourceA2AuditWindowReference(
        arm=RegionResourceA2AuditArm.R0,
        comparison_key=context.comparison_key,
        scenario_id=context.scenario_id,
        scenario_version=context.scenario_version,
        scale=context.scale,
        seed=context.seed,
        paired_window_id=context.paired_window_id,
        paired_exogenous_config_sha256=(
            context.paired_exogenous_config_sha256
        ),
        execution_arm_id="episode-r0-seed-101",
        window_id="r0-physical-window-001",
        source_event_log_id="episode-r0-seed-101/events",
        source_event_log_sha256=_sha(
            "episode-r0-seed-101:event-log"
        ),
        window_start_s=physical.window_start_s,
        window_end_s=physical.window_end_s,
        plan_id="r0-successor-plan",
        plan_version=physical.applied_plan_version,
        plan_valid_until_s=evidence.d3_successor_plan.valid_until_s,
        authority_lease_expires_at_s=applied.lease_expires_at_s,
        physical_window_payload_sha256=_sha(
            "r0-physical-window-payload"
        ),
        policy_name="d4-region-resource-rule",
        policy_version="v1",
        source_safe_adoption_evidence_sha256=None,
        source_advisory_id=None,
        source_advisory_version=None,
        physical_execution_observed=True,
        window_complete=True,
        hard_constraint_violation_count=0,
    )
    return evidence, context, candidate, r0_window


def test_development_intervention_cannot_enter_formal_benefit_audit() -> None:
    evidence, _, candidate, _ = _a2_benefit_audit_case()

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="development_intervention_benefit_forbidden",
    ):
        replace(
            candidate,
            policy_name=(
                REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME
            ),
        )

    source = RegionResourceA2SafeAdoptionAuditSource.from_value(evidence)
    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="development_intervention_benefit_forbidden",
    ):
        replace(
            source,
            policy_name=(
                REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME
            ),
        )


def test_same_key_r0_pair_is_only_d6_benefit_audit_eligible() -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()

    result = assemble_region_resource_a2_benefit_audit_input(
        safe_adoption_evidence=evidence,
        context=context,
        candidate_window=candidate,
        same_key_r0_window=r0_window,
    )

    assert result.d6_benefit_audit_eligible
    assert result.permissions.d6_benefit_audit_input_allowed
    assert result.unique_same_key_r0_available
    assert result.hard_constraints_satisfied
    assert not result.a2_benefit_available
    assert not result.authority_granted
    assert not result.final_benefit_computed
    assert not result.online_truth_used
    assert not result.permissions.a2_assist_authority
    assert not result.permissions.model_promotion_authority
    assert not result.permissions.assignment_authority
    assert not result.permissions.failover_authority
    assert not result.permissions.control_authority
    assert "outcome" not in result.to_dict()
    assert "reward" not in result.to_dict()
    assert (
        validate_region_resource_a2_benefit_audit_input(
            result.to_dict(),
            safe_adoption_evidence=evidence,
        )
        == result
    )


def test_persisted_episode_evidence_supports_offline_pair_assembly() -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()
    persisted = evidence.to_dict()

    object_source = RegionResourceA2SafeAdoptionAuditSource.from_value(
        evidence
    )
    persisted_source = RegionResourceA2SafeAdoptionAuditSource.from_value(
        persisted
    )
    result = assemble_region_resource_a2_benefit_audit_input(
        safe_adoption_evidence=persisted,
        context=context,
        candidate_window=candidate,
        same_key_r0_window=r0_window,
    )
    batch = assemble_region_resource_a2_benefit_audit_batch((result,))
    loaded_batch = RegionResourceA2BenefitAuditBatch.from_mapping(
        batch.to_dict(),
        safe_adoption_evidence_by_sha256={
            evidence.content_sha256: persisted,
        },
    )

    assert persisted_source == object_source
    assert result.d6_benefit_audit_eligible
    assert loaded_batch == batch


def test_missing_same_key_r0_is_explicitly_ineligible() -> None:
    evidence, context, candidate, _ = _a2_benefit_audit_case()

    result = assemble_region_resource_a2_benefit_audit_input(
        safe_adoption_evidence=evidence,
        context=context,
        candidate_window=candidate,
        same_key_r0_window=None,
    )

    assert not result.d6_benefit_audit_eligible
    assert result.blocker_codes == ("same_key_r0_window_missing",)
    assert not result.permissions.d6_benefit_audit_input_allowed
    assert not result.a2_benefit_available
    assert not result.authority_granted


def test_cross_key_r0_is_rejected() -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()
    mismatched = replace(r0_window, comparison_key="different-key")

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="audit_window_comparison_identity_mismatch",
    ):
        assemble_region_resource_a2_benefit_audit_input(
            safe_adoption_evidence=evidence,
            context=context,
            candidate_window=candidate,
            same_key_r0_window=mismatched,
        )


def test_candidate_plan_version_tamper_is_rejected() -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()
    mismatched = replace(
        candidate,
        plan_version=candidate.plan_version + 1,
    )

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="candidate_safe_adoption_binding_mismatch",
    ):
        assemble_region_resource_a2_benefit_audit_input(
            safe_adoption_evidence=evidence,
            context=context,
            candidate_window=mismatched,
            same_key_r0_window=r0_window,
        )


@pytest.mark.parametrize(
    "reused_fields",
    (
        ("source_event_log_id",),
        ("source_event_log_sha256",),
        ("execution_arm_id",),
        ("window_id", "physical_window_payload_sha256"),
    ),
)
def test_candidate_and_r0_evidence_reuse_is_rejected(
    reused_fields: tuple[str, ...],
) -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()
    changes = {
        name: getattr(candidate, name)
        for name in reused_fields
    }
    reused = replace(r0_window, **changes)

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="same_key_r0_evidence_reuse",
    ):
        assemble_region_resource_a2_benefit_audit_input(
            safe_adoption_evidence=evidence,
            context=context,
            candidate_window=candidate,
            same_key_r0_window=reused,
        )


def test_duplicate_r0_reference_is_rejected_by_batch() -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()
    result = assemble_region_resource_a2_benefit_audit_input(
        safe_adoption_evidence=evidence,
        context=context,
        candidate_window=candidate,
        same_key_r0_window=r0_window,
    )

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="duplicate_r0_window_id",
    ):
        assemble_region_resource_a2_benefit_audit_batch((result, result))


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        (
            {"window_complete": False},
            "r0_physical_window_incomplete",
        ),
        (
            {"physical_execution_observed": False},
            "r0_physical_execution_unobserved",
        ),
        (
            {"hard_constraint_violation_count": 1},
            "r0_hard_constraint_violation",
        ),
    ),
)
def test_incomplete_r0_window_stays_ineligible(
    changes: dict[str, object],
    reason: str,
) -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()
    unavailable = replace(r0_window, **changes)

    result = assemble_region_resource_a2_benefit_audit_input(
        safe_adoption_evidence=evidence,
        context=context,
        candidate_window=candidate,
        same_key_r0_window=unavailable,
    )

    assert not result.d6_benefit_audit_eligible
    assert reason in result.blocker_codes
    assert not result.a2_benefit_available
    assert not result.authority_granted


def test_r0_window_after_plan_or_lease_expiry_stays_ineligible() -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()
    expired = replace(
        r0_window,
        plan_valid_until_s=r0_window.window_end_s,
        authority_lease_expires_at_s=r0_window.window_end_s,
    )

    result = assemble_region_resource_a2_benefit_audit_input(
        safe_adoption_evidence=evidence,
        context=context,
        candidate_window=candidate,
        same_key_r0_window=expired,
    )

    assert not result.d6_benefit_audit_eligible
    assert result.blocker_codes == (
        "r0_plan_expired_before_window_end",
        "r0_authority_lease_expired_before_window_end",
    )


def test_r0_duration_mismatch_is_rejected() -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()
    mismatched = replace(
        r0_window,
        window_end_s=r0_window.window_end_s + 0.01,
    )

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="audit_window_duration_mismatch",
    ):
        assemble_region_resource_a2_benefit_audit_input(
            safe_adoption_evidence=evidence,
            context=context,
            candidate_window=candidate,
            same_key_r0_window=mismatched,
        )


def test_truth_field_and_online_truth_flag_are_rejected() -> None:
    _, _, _, r0_window = _a2_benefit_audit_case()
    payload = r0_window.to_dict()
    payload["truth_id"] = "forbidden"

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="truth_or_result_field_forbidden",
    ):
        RegionResourceA2AuditWindowReference.from_mapping(payload)
    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="online_truth_forbidden",
    ):
        replace(r0_window, online_truth_used=True)


def test_audit_input_missing_field_or_hash_tamper_is_rejected() -> None:
    evidence, context, candidate, r0_window = _a2_benefit_audit_case()
    result = assemble_region_resource_a2_benefit_audit_input(
        safe_adoption_evidence=evidence,
        context=context,
        candidate_window=candidate,
        same_key_r0_window=r0_window,
    )
    missing = result.to_dict()
    missing.pop("same_key_r0_window_available")
    tampered = result.to_dict()
    tampered["candidate_window"] = dict(tampered["candidate_window"])
    tampered["candidate_window"]["plan_version"] += 1

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="mapping_fields_mismatch",
    ):
        validate_region_resource_a2_benefit_audit_input(
            missing,
            safe_adoption_evidence=evidence,
        )
    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="audit_window_recomputation_mismatch",
    ):
        validate_region_resource_a2_benefit_audit_input(
            tampered,
            safe_adoption_evidence=evidence,
        )


def test_persisted_safe_adoption_hash_tamper_is_rejected() -> None:
    evidence, _, _, _ = _a2_benefit_audit_case()
    persisted = evidence.to_dict()
    persisted["evaluated_at_s"] += 0.01

    with pytest.raises(
        RegionResourceA2BenefitAuditError,
        match="safe_adoption_source_hash_mismatch",
    ):
        RegionResourceA2SafeAdoptionAuditSource.from_value(persisted)
