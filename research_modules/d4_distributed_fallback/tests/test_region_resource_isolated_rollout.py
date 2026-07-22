from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from d4_distributed_fallback.coalition_safety import CoalitionMemberAck
from d4_distributed_fallback.models import C2Health
from d4_distributed_fallback.regional_failover import (
    MobileReconSecondary,
    RegionDefinition,
    RegionalFailoverCoordinator,
    RegionalFailoverSnapshot,
    RegionalFallbackMember,
    RegionalScenarioMetadata,
    RegionalTaskEvidence,
)
from d4_distributed_fallback.region_resource_isolated_rollout import (
    REGION_RESOURCE_ISOLATED_ADOPTION_EVIDENCE_SCHEMA,
    REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
    REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
    RegionResourceDegradedScenarioKind,
    RegionResourceIsolatedAdoptionCode,
    RegionResourceIsolatedAdoptionKind,
    RegionResourceIsolatedAdoptionVerifier,
    RegionResourceIsolatedCandidateGate,
    build_region_resource_degraded_scenario_lineage,
    build_region_resource_isolated_plan_ack_from_d3_evidence,
    build_region_resource_isolated_plan_consumption_ack,
)
from d4_distributed_fallback.region_resource_runtime_ack import (
    canonical_runtime_payload_sha256,
)
from d4_distributed_fallback.secondary_readiness import SecondaryReadinessEvidence


REGION_ID = "region-000"
SOURCE_PLAN_ID = "PLAN-SOURCE"
SOURCE_PLAN_VERSION = 2
SOURCE_EPOCH = 4
SOURCE_TIME_S = 1.0
LEASE_EXPIRES_AT_S = 20.0


def _hash(character: str) -> str:
    return character * 64


def _passing_gate() -> RegionResourceIsolatedCandidateGate:
    return RegionResourceIsolatedCandidateGate(
        candidate_considered=True,
        candidate_id="D4-CANDIDATE-1",
        candidate_payload_sha256=_hash("a"),
        candidate_confidence=0.75,
        minimum_confidence=REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
        candidate_ood_passed=True,
        candidate_latency_ms=4.0,
        candidate_latency_limit_ms=REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
        candidate_finite=True,
        candidate_failure_gate_passed=True,
        candidate_safety_projection_passed=True,
        gate_pass=True,
        rule_fallback=False,
    )


def _low_confidence_gate() -> RegionResourceIsolatedCandidateGate:
    return RegionResourceIsolatedCandidateGate(
        candidate_considered=True,
        candidate_id="D4-CANDIDATE-LOW",
        candidate_payload_sha256=_hash("b"),
        candidate_confidence=0.59,
        minimum_confidence=REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
        candidate_ood_passed=True,
        candidate_latency_ms=4.0,
        candidate_latency_limit_ms=REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
        candidate_finite=True,
        candidate_failure_gate_passed=True,
        candidate_safety_projection_passed=True,
        gate_pass=False,
        rule_fallback=True,
        rejection_reasons=("candidate_low_confidence",),
    )


def _readiness(node_id: str) -> SecondaryReadinessEvidence:
    return SecondaryReadinessEvidence(
        node_id=node_id,
        current_time_s=SOURCE_TIME_S,
        readiness_timestamp_s=SOURCE_TIME_S,
        readiness_stale_after_s=1.0,
        availability_confirmed=True,
        lease_epoch=SOURCE_EPOCH,
        lease_expires_at_s=LEASE_EXPIRES_AT_S,
        heartbeat_timestamp_s=SOURCE_TIME_S,
        heartbeat_stale_after_s=1.0,
        cue_freshness_s=0.05,
        cue_stale_after_s=1.0,
        gimbal_pointing_ok=True,
        communication_received_timestamp_s=SOURCE_TIME_S,
        communication_stale_after_s=1.0,
        coverage_matches_requested_cell=True,
        coverage_ratio=0.9,
        network_full_view_rate=0.9,
        takeover_ready_sustained=True,
        takeover_ready_since_s=0.5,
        takeover_ready_observation_count=3,
    )


def _task(*, member_count: int = 1, active_risk: bool = False) -> RegionalTaskEvidence:
    members = tuple(f"INT-{index + 1}" for index in range(member_count))
    return RegionalTaskEvidence(
        task_id="TASK-1",
        global_track_id="GT3D-000001",
        region_id=REGION_ID,
        d3_plan_id=SOURCE_PLAN_ID,
        d3_plan_version=SOURCE_PLAN_VERSION,
        d3_epoch=SOURCE_EPOCH,
        d3_lease_expires_at_s=LEASE_EXPIRES_AT_S,
        required_member_count=member_count,
        required_capabilities=("intercept",),
        d3_assigned_member_ids=members,
        coalition_id="COAL-1" if member_count > 1 else None,
        coalition_version=SOURCE_PLAN_VERSION if member_count > 1 else None,
        d1_covariance_trace=3000.0 if active_risk else 10.0,
    )


def _member(node_id: str, score: float) -> RegionalFallbackMember:
    return RegionalFallbackMember(
        node_id=node_id,
        region_ids=(REGION_ID,),
        capabilities=("intercept",),
        task_bid_scores={"TASK-1": score},
    )


def _coalition_ack(member_id: str) -> CoalitionMemberAck:
    return CoalitionMemberAck(
        resource_id=member_id,
        global_track_id="GT3D-000001",
        coalition_id="COAL-1",
        coalition_version=SOURCE_PLAN_VERSION,
        plan_id=SOURCE_PLAN_ID,
        plan_version=SOURCE_PLAN_VERSION,
        epoch=SOURCE_EPOCH,
        can_execute=True,
        evidence_timestamp=SOURCE_TIME_S,
        valid_until=LEASE_EXPIRES_AT_S,
    )


def _snapshot(
    kind: RegionResourceDegradedScenarioKind,
    *,
    partitioned: bool = False,
    member_count: int = 1,
    include_coalition_acks: bool = True,
    scenario_name: str | None = None,
) -> RegionalFailoverSnapshot:
    if kind == RegionResourceDegradedScenarioKind.ACTIVE_RISK:
        health = C2Health.NORMAL
        secondaries: tuple[MobileReconSecondary, ...] = ()
        active_risk = True
    elif kind == RegionResourceDegradedScenarioKind.CENTER_FAILED:
        health = C2Health.FAILED
        secondaries = (
            MobileReconSecondary(
                node_id="RECON-1",
                readiness_by_region={REGION_ID: _readiness("RECON-1")},
                takeover_priority=10,
            ),
        )
        active_risk = False
    else:
        health = C2Health.FAILED
        secondaries = ()
        active_risk = False
    scenario = RegionalScenarioMetadata.from_scalable_scenario(
        {
            "schema_version": "scalable3d-scenario-v1",
            "scenario_name": scenario_name or f"d4-{kind.value}-test",
            "scenario_version": "degraded-v1",
            "target_count": 1,
            "resource_count": max(2, member_count),
            "recon_count": 1,
            "region_count": 1,
        }
    )
    task = _task(member_count=member_count, active_risk=active_risk)
    member_ids = tuple(f"INT-{index + 1}" for index in range(max(2, member_count)))
    coalition_acks = (
        tuple(_coalition_ack(member_id) for member_id in member_ids[:member_count])
        if member_count > 1 and include_coalition_acks
        else ()
    )
    return RegionalFailoverSnapshot(
        timestamp_s=SOURCE_TIME_S,
        scenario=scenario,
        center_health=health,
        center_node_id="CENTER",
        plan_id=SOURCE_PLAN_ID,
        plan_version=SOURCE_PLAN_VERSION,
        epoch=SOURCE_EPOCH,
        lease_expires_at_s=LEASE_EXPIRES_AT_S,
        regions=(RegionDefinition(region_id=REGION_ID, coverage_cell="cell-0"),),
        tasks=(task,),
        secondary_nodes=secondaries,
        fallback_members=tuple(
            _member(member_id, 10.0 - index)
            for index, member_id in enumerate(member_ids)
        ),
        coalition_acks=coalition_acks,
        partitioned_region_ids=((REGION_ID,) if partitioned else ()),
    )


def _source_plan(decision) -> dict[str, object]:
    region = decision.region_decisions[0]
    ownership = region.ownership
    owner_layer = (
        region.selected_layer.value
        if ownership.owner_layer.value == "hold"
        else ownership.owner_layer.value
    )
    owner_node_id = ownership.owner_id
    if owner_node_id is None and region.selected_secondary_id is not None:
        owner_node_id = region.selected_secondary_id
    if owner_node_id is None:
        owner_node_id = "INT-1"
    assignment = {
        "resource_id": "INT-1",
        "global_track_id": "GT3D-000001",
        "coalition_id": None,
        "coalition_version": None,
        "member_role": "primary",
        "owner_node_id": owner_node_id,
        "regional_owner_layer": owner_layer,
        "regional_region_id": ownership.region_id,
        "regional_epoch": ownership.epoch,
        "regional_commit_mode": region.action.value,
    }
    return {
        "timestamp": SOURCE_TIME_S,
        "plan_id": ownership.plan_id,
        "plan_version": ownership.plan_version,
        "created_at": 0.5,
        "assignment_count": 1,
        "assignments": [assignment],
        "unassigned_global_track_ids": [],
        "metadata": {
            "active_plan_owner": owner_layer,
            "owner_node_id": owner_node_id,
            "authority_epoch": ownership.epoch,
            "lease_expires_at_s": ownership.lease_expires_at_s,
            "current_plan_id": ownership.plan_id,
            "current_plan_version": ownership.plan_version,
            "identity_created_at_s": 0.5,
            "last_evaluated_at_s": SOURCE_TIME_S,
            "execution_signature_changed": False,
            "plan_refresh_only": False,
            "evaluation_refresh_only": False,
            "plan_published": True,
        },
    }


def _applied_plan(
    source_plan: dict[str, object],
    *,
    lineage_sha256: str,
    gate: RegionResourceIsolatedCandidateGate,
    refresh: bool = False,
) -> dict[str, object]:
    plan = deepcopy(source_plan)
    metadata = plan["metadata"]
    assert isinstance(metadata, dict)
    assignments = plan["assignments"]
    assert isinstance(assignments, list)
    assignment = assignments[0]
    assert isinstance(assignment, dict)
    plan["timestamp"] = 1.1
    metadata["last_evaluated_at_s"] = 1.1
    metadata["d4_source_lineage_sha256"] = lineage_sha256
    if refresh:
        metadata["execution_signature_changed"] = False
        metadata["evaluation_refresh_only"] = True
        metadata["d4_isolated_execution_source"] = (
            "deterministic_rule_fallback"
            if gate.rule_fallback
            else "evaluation_refresh"
        )
    else:
        plan["plan_id"] = "PLAN-APPLIED"
        plan["plan_version"] = SOURCE_PLAN_VERSION + 1
        plan["created_at"] = 1.1
        metadata["current_plan_id"] = "PLAN-APPLIED"
        metadata["current_plan_version"] = SOURCE_PLAN_VERSION + 1
        metadata["identity_created_at_s"] = 1.1
        metadata["execution_signature_changed"] = True
        assignment["resource_id"] = "INT-2"
        metadata["d4_isolated_execution_source"] = (
            "deterministic_rule_fallback" if gate.rule_fallback else "candidate"
        )
    metadata["d4_candidate_payload_sha256"] = (
        None if gate.rule_fallback else gate.candidate_payload_sha256
    )
    return plan


def _case(
    kind: RegionResourceDegradedScenarioKind,
    *,
    gate: RegionResourceIsolatedCandidateGate | None = None,
    refresh: bool = False,
    partitioned: bool = False,
    member_count: int = 1,
    include_coalition_acks: bool = True,
    scenario_name: str | None = None,
) -> dict[str, object]:
    resolved_gate = gate or _passing_gate()
    snapshot = _snapshot(
        kind,
        partitioned=partitioned,
        member_count=member_count,
        include_coalition_acks=include_coalition_acks,
        scenario_name=scenario_name,
    )
    decision = RegionalFailoverCoordinator().evaluate(snapshot)
    source_plan = _source_plan(decision)
    lineage = build_region_resource_degraded_scenario_lineage(
        scenario_kind=kind,
        seed=1000,
        arm_id="treatment-candidate",
        cycle_index=1,
        region_id=REGION_ID,
        scenario_config_sha256=_hash("1"),
        initial_state_sha256=_hash("2"),
        communication_schedule_sha256=_hash("3"),
        fault_schedule_sha256=_hash("4"),
        source_snapshot=snapshot,
        formal_decision=decision,
        source_plan_source=source_plan,
        candidate_gate=resolved_gate,
    )
    applied_plan = _applied_plan(
        source_plan,
        lineage_sha256=lineage.sha256,
        gate=resolved_gate,
        refresh=refresh,
    )
    ack = build_region_resource_isolated_plan_consumption_ack(
        ack_id=f"ACK-{kind.value}",
        lineage=lineage,
        source_plan_source=source_plan,
        applied_plan_source=applied_plan,
        acknowledged_at_s=1.2,
        control_applied_binding_count=1,
    )
    return {
        "snapshot": snapshot,
        "decision": decision,
        "source_plan": source_plan,
        "lineage": lineage,
        "gate": resolved_gate,
        "applied_plan": applied_plan,
        "ack": ack,
    }


def _evaluate(case: dict[str, object], *, verifier=None):
    return (verifier or RegionResourceIsolatedAdoptionVerifier()).evaluate(
        scenario_lineage_source=case["lineage"],
        source_snapshot=case["snapshot"],
        formal_decision=case["decision"],
        candidate_gate_source=case["gate"],
        source_plan_source=case["source_plan"],
        applied_plan_source=case["applied_plan"],
        isolated_plan_ack_source=case["ack"],
    )


def _d3_consumption_evidence(case: dict[str, object]) -> dict[str, object]:
    lineage = case["lineage"]
    applied = case["applied_plan"]
    assert isinstance(applied, dict)
    source_lineage = {
        "schema_version": "d3.isolated-plan-source-lineage.v1",
        "scenario_version": lineage.scenario_version,
        "scenario_config_sha256": lineage.scenario_config_sha256,
        "initial_world_state_sha256": lineage.initial_state_sha256,
        "input_snapshot_schema_version": "scalable3d-input-v1",
        "observation_input_snapshot_sha256": _hash("6"),
        "d1_d2_lineage_contract_version": "d1-d2-lineage-v1",
        "d1_d2_lineage_contract_sha256": _hash("7"),
    }
    identity = {
        "experiment_id": "D4-DEGRADED-PAIR",
        "experiment_version": "v1",
        "pair_id": "PAIR-1000",
        "seed": lineage.seed,
        "arm_id": lineage.arm_id,
        "arm_kind": "treatment",
        "isolation_id": "WORLD-TREATMENT-1000",
        "plan_id": applied["plan_id"],
        "plan_version": applied["plan_version"],
        "plan_payload_sha256": canonical_runtime_payload_sha256(applied),
    }
    consumption_id = (
        "d3-isolated-consumption-"
        f"{canonical_runtime_payload_sha256(identity)[:24]}"
    )
    return {
        "schema_version": "d3.isolated-plan-consumption-evidence.v1",
        "evidence_kind": "isolated_simulation_plan_consumption_confirmation",
        "consumption_id": consumption_id,
        **identity,
        "arm_spec_sha256": _hash("8"),
        "execution_receipt_sha256": _hash("9"),
        "source_snapshot_lineage": source_lineage,
        "source_snapshot_lineage_sha256": canonical_runtime_payload_sha256(
            source_lineage
        ),
        "plan_schema_version": "assignment_plan_v2",
        "plan_created_at_s": applied["created_at"],
        "plan_valid_until_s": LEASE_EXPIRES_AT_S,
        "rollout_cycle": lineage.cycle_index,
        "consumption_timestamp_s": 1.2,
        "assignment_count": applied["assignment_count"],
        "binding_count": applied["assignment_count"],
        "binding_inventory_sha256": _hash("c"),
        "accepted": True,
        "status": "accepted_by_isolated_simulation_consumer",
        "isolated_plan_applied": True,
        "production_runtime_ack": False,
        "isolated_simulation_only": True,
        "control_applied_to_production_world": False,
        "physical_outcome_available": False,
        "reward_available": False,
        "causal_evidence_available": False,
        "ppo_enabled": False,
        "online_assist_enabled": False,
        "online_authority_enabled": False,
        "rule_fallback_enabled": True,
    }


@pytest.mark.parametrize(
    ("kind", "expected_owner_layer"),
    (
        (RegionResourceDegradedScenarioKind.CENTER_FAILED, "secondary"),
        (
            RegionResourceDegradedScenarioKind.CENTER_AND_SECONDARY_FAILED,
            "distributed",
        ),
        (RegionResourceDegradedScenarioKind.ACTIVE_RISK, "center"),
    ),
)
def test_three_degraded_scenario_classes_accept_only_isolated_new_plan(
    kind: RegionResourceDegradedScenarioKind,
    expected_owner_layer: str,
) -> None:
    evidence = _evaluate(_case(kind))

    assert evidence.schema == REGION_RESOURCE_ISOLATED_ADOPTION_EVIDENCE_SCHEMA
    assert evidence.code == RegionResourceIsolatedAdoptionCode.CANDIDATE_ADOPTED.value
    assert evidence.scenario_kind == kind.value
    assert evidence.scenario_validated is True
    assert evidence.candidate_considered is True
    assert evidence.gate_pass is True
    assert evidence.new_execution_plan_applied is True
    assert evidence.evaluation_refresh_applied is False
    assert evidence.rule_fallback is False
    assert evidence.isolated_plan_consumption_ack_available is True
    assert evidence.isolated_candidate_adoption_available is True
    assert evidence.adoption_kind == (
        RegionResourceIsolatedAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
    )
    assert evidence.source_plan_version == SOURCE_PLAN_VERSION
    assert evidence.applied_plan_version == SOURCE_PLAN_VERSION + 1
    assert evidence.owner_layer == expected_owner_layer
    assert evidence.authority_epoch == SOURCE_EPOCH
    assert evidence.lease_expires_at_s == pytest.approx(LEASE_EXPIRES_AT_S)
    assert evidence.production_runtime_ack is False
    assert evidence.isolated_simulation_only is True
    assert evidence.physical_outcome_available is False
    assert evidence.paired_non_degradation_available is False
    assert evidence.counterfactual_available is False
    assert evidence.causal_effect_available is False
    assert evidence.degradation_effectiveness_claim_allowed is False
    assert evidence.ppo_enabled is False
    assert evidence.assist_enabled is False
    assert evidence.authority_enabled is False
    assert evidence.rule_fallback_enabled is True


@pytest.mark.parametrize("kind", tuple(RegionResourceDegradedScenarioKind))
def test_same_generation_refresh_is_not_candidate_adoption(
    kind: RegionResourceDegradedScenarioKind,
) -> None:
    evidence = _evaluate(
        _case(kind, refresh=True)
    )

    assert evidence.code == RegionResourceIsolatedAdoptionCode.EVALUATION_REFRESH.value
    assert evidence.new_execution_plan_applied is False
    assert evidence.evaluation_refresh_applied is True
    assert evidence.isolated_plan_consumption_ack_available is True
    assert evidence.isolated_candidate_adoption_available is False
    assert evidence.adoption_kind == (
        RegionResourceIsolatedAdoptionKind.EVALUATION_REFRESH_APPLIED.value
    )
    assert evidence.source_plan_id == evidence.applied_plan_id
    assert evidence.source_plan_version == evidence.applied_plan_version


@pytest.mark.parametrize("kind", tuple(RegionResourceDegradedScenarioKind))
def test_different_plan_id_with_same_version_is_not_a_refresh_or_new_plan(
    kind: RegionResourceDegradedScenarioKind,
) -> None:
    case = _case(kind)
    applied = case["applied_plan"]
    assert isinstance(applied, dict)
    metadata = applied["metadata"]
    assert isinstance(metadata, dict)
    applied["plan_version"] = SOURCE_PLAN_VERSION
    metadata["current_plan_version"] = SOURCE_PLAN_VERSION
    case["ack"] = build_region_resource_isolated_plan_consumption_ack(
        ack_id=f"ACK-SAME-VERSION-{kind.value}",
        lineage=case["lineage"],
        source_plan_source=case["source_plan"],
        applied_plan_source=applied,
        acknowledged_at_s=1.2,
        control_applied_binding_count=1,
    )

    evidence = _evaluate(case)

    assert evidence.code == RegionResourceIsolatedAdoptionCode.PLAN_NOT_NEW.value
    assert evidence.new_execution_plan_applied is False
    assert evidence.evaluation_refresh_applied is False
    assert evidence.isolated_plan_consumption_ack_available is False


@pytest.mark.parametrize(
    ("kind", "prior_owner_layer", "prior_owner_node_id"),
    (
        (RegionResourceDegradedScenarioKind.CENTER_FAILED, "center", "CENTER"),
        (
            RegionResourceDegradedScenarioKind.CENTER_AND_SECONDARY_FAILED,
            "secondary",
            "RECON-1",
        ),
    ),
)
def test_passive_failover_rejects_previous_authority_plan_as_source(
    kind: RegionResourceDegradedScenarioKind,
    prior_owner_layer: str,
    prior_owner_node_id: str,
) -> None:
    case = _case(kind)
    previous = deepcopy(case["source_plan"])
    metadata = previous["metadata"]
    assert isinstance(metadata, dict)
    assignments = previous["assignments"]
    assert isinstance(assignments, list)
    previous["plan_id"] = "PLAN-PREVIOUS-AUTHORITY"
    previous["plan_version"] = SOURCE_PLAN_VERSION - 1
    previous["created_at"] = 0.25
    metadata.update(
        {
            "active_plan_owner": prior_owner_layer,
            "owner_node_id": prior_owner_node_id,
            "authority_epoch": SOURCE_EPOCH - 1,
            "current_plan_id": "PLAN-PREVIOUS-AUTHORITY",
            "current_plan_version": SOURCE_PLAN_VERSION - 1,
            "identity_created_at_s": 0.25,
        }
    )
    for assignment in assignments:
        assignment["owner_node_id"] = prior_owner_node_id
        assignment["regional_owner_layer"] = prior_owner_layer
        assignment["regional_epoch"] = SOURCE_EPOCH - 1
    old_lineage = case["lineage"]
    case["source_plan"] = previous
    case["lineage"] = build_region_resource_degraded_scenario_lineage(
        scenario_kind=kind,
        seed=old_lineage.seed,
        arm_id=old_lineage.arm_id,
        cycle_index=old_lineage.cycle_index,
        region_id=old_lineage.region_id,
        scenario_config_sha256=old_lineage.scenario_config_sha256,
        initial_state_sha256=old_lineage.initial_state_sha256,
        communication_schedule_sha256=old_lineage.communication_schedule_sha256,
        fault_schedule_sha256=old_lineage.fault_schedule_sha256,
        source_snapshot=case["snapshot"],
        formal_decision=case["decision"],
        source_plan_source=previous,
        candidate_gate=case["gate"],
    )
    case["ack"] = None

    evidence = _evaluate(case)

    assert evidence.code == (
        RegionResourceIsolatedAdoptionCode.SOURCE_LINEAGE_MISMATCH.value
    )
    assert evidence.scenario_validated is False
    assert evidence.isolated_plan_consumption_ack_available is False


def test_low_confidence_keeps_threshold_and_applies_rule_fallback_only() -> None:
    evidence = _evaluate(
        _case(
            RegionResourceDegradedScenarioKind.CENTER_FAILED,
            gate=_low_confidence_gate(),
        )
    )

    assert evidence.code == RegionResourceIsolatedAdoptionCode.RULE_FALLBACK_APPLIED.value
    assert evidence.candidate_considered is True
    assert evidence.gate_pass is False
    assert evidence.rule_fallback is True
    assert evidence.new_execution_plan_applied is True
    assert evidence.isolated_candidate_adoption_available is False
    assert evidence.candidate_gate_rejection_reasons == (
        "candidate_low_confidence",
    )


def test_missing_isolated_ack_fails_closed() -> None:
    case = _case(RegionResourceDegradedScenarioKind.CENTER_FAILED)
    case["ack"] = None

    evidence = _evaluate(case)

    assert evidence.code == RegionResourceIsolatedAdoptionCode.ACK_MISSING.value
    assert evidence.scenario_validated is True
    assert evidence.isolated_plan_consumption_ack_available is False
    assert evidence.new_execution_plan_applied is False
    assert evidence.isolated_candidate_adoption_available is False


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("stale_epoch", RegionResourceIsolatedAdoptionCode.AUTHORITY_EPOCH_STALE),
        ("expired_lease", RegionResourceIsolatedAdoptionCode.AUTHORITY_LEASE_EXPIRED),
        ("binding_changed_after_ack", RegionResourceIsolatedAdoptionCode.PLAN_BINDING_MISMATCH),
        ("ack_binding_hash", RegionResourceIsolatedAdoptionCode.PLAN_BINDING_MISMATCH),
        ("wrong_owner", RegionResourceIsolatedAdoptionCode.AUTHORITY_OWNER_MISMATCH),
        ("production_ack", RegionResourceIsolatedAdoptionCode.ACK_INVALID),
    ),
)
def test_tampered_or_expired_isolated_receipts_fail_closed(
    mutation: str,
    expected_code: RegionResourceIsolatedAdoptionCode,
) -> None:
    case = _case(RegionResourceDegradedScenarioKind.CENTER_FAILED)
    applied = case["applied_plan"]
    assert isinstance(applied, dict)
    metadata = applied["metadata"]
    assert isinstance(metadata, dict)

    if mutation == "stale_epoch":
        metadata["authority_epoch"] = SOURCE_EPOCH - 1
        case["ack"] = build_region_resource_isolated_plan_consumption_ack(
            ack_id="ACK-STALE-EPOCH",
            lineage=case["lineage"],
            source_plan_source=case["source_plan"],
            applied_plan_source=applied,
            acknowledged_at_s=1.2,
            control_applied_binding_count=1,
        )
    elif mutation == "expired_lease":
        ack = case["ack"]
        case["ack"] = replace(ack, acknowledged_at_s=LEASE_EXPIRES_AT_S)
    elif mutation == "binding_changed_after_ack":
        assignments = applied["assignments"]
        assert isinstance(assignments, list)
        assignments[0]["resource_id"] = "INT-TAMPERED"
    elif mutation == "ack_binding_hash":
        ack = case["ack"]
        case["ack"] = replace(ack, execution_binding_sha256=_hash("f"))
    elif mutation == "wrong_owner":
        metadata["owner_node_id"] = "RECON-TAMPERED"
        case["ack"] = build_region_resource_isolated_plan_consumption_ack(
            ack_id="ACK-WRONG-OWNER",
            lineage=case["lineage"],
            source_plan_source=case["source_plan"],
            applied_plan_source=applied,
            acknowledged_at_s=1.2,
            control_applied_binding_count=1,
        )
    elif mutation == "production_ack":
        ack = case["ack"].to_dict()
        ack["production_runtime_ack"] = True
        case["ack"] = ack
    else:  # pragma: no cover
        raise AssertionError(mutation)

    evidence = _evaluate(case)

    assert evidence.code == expected_code.value
    assert evidence.isolated_plan_consumption_ack_available is False
    assert evidence.isolated_candidate_adoption_available is False
    assert evidence.production_runtime_ack is False
    assert evidence.authority_enabled is False


def test_network_partition_rejects_even_hash_consistent_sources() -> None:
    evidence = _evaluate(
        _case(
            RegionResourceDegradedScenarioKind.CENTER_FAILED,
            partitioned=True,
        )
    )

    assert evidence.code == RegionResourceIsolatedAdoptionCode.NETWORK_PARTITION.value
    assert evidence.scenario_validated is False
    assert evidence.isolated_candidate_adoption_available is False


def test_missing_coalition_member_ack_keeps_passive_failover_closed() -> None:
    evidence = _evaluate(
        _case(
            RegionResourceDegradedScenarioKind.CENTER_FAILED,
            member_count=2,
            include_coalition_acks=False,
        )
    )

    assert evidence.code == (
        RegionResourceIsolatedAdoptionCode.FORMAL_DECISION_REJECTED.value
    )
    assert evidence.isolated_plan_consumption_ack_available is False
    assert evidence.authority_enabled is False


def test_nominal_name_cannot_be_relabelled_as_degraded_evidence() -> None:
    evidence = _evaluate(
        _case(
            RegionResourceDegradedScenarioKind.ACTIVE_RISK,
            scenario_name="nominal-5v5",
        )
    )

    assert evidence.code == RegionResourceIsolatedAdoptionCode.NOMINAL_NOT_ELIGIBLE.value
    assert evidence.degradation_effectiveness_claim_allowed is False


def test_refresh_binding_change_is_not_hidden_by_same_plan_identity() -> None:
    case = _case(
        RegionResourceDegradedScenarioKind.ACTIVE_RISK,
        refresh=True,
    )
    applied = case["applied_plan"]
    assert isinstance(applied, dict)
    assignments = applied["assignments"]
    assert isinstance(assignments, list)
    assignments[0]["resource_id"] = "INT-2"
    case["ack"] = build_region_resource_isolated_plan_consumption_ack(
        ack_id="ACK-REFRESH-BINDING-TAMPER",
        lineage=case["lineage"],
        source_plan_source=case["source_plan"],
        applied_plan_source=applied,
        acknowledged_at_s=1.2,
        control_applied_binding_count=1,
    )

    evidence = _evaluate(case)

    assert evidence.code == (
        RegionResourceIsolatedAdoptionCode.REFRESH_BINDINGS_CHANGED.value
    )
    assert evidence.evaluation_refresh_applied is False
    assert evidence.isolated_candidate_adoption_available is False


def test_receipt_replay_is_rejected_without_mutating_authority() -> None:
    case = _case(RegionResourceDegradedScenarioKind.CENTER_FAILED)
    verifier = RegionResourceIsolatedAdoptionVerifier()

    first = _evaluate(case, verifier=verifier)
    replay = _evaluate(case, verifier=verifier)

    assert first.isolated_candidate_adoption_available is True
    assert replay.code == RegionResourceIsolatedAdoptionCode.ACK_REPLAYED.value
    assert replay.isolated_plan_consumption_ack_available is False
    assert verifier.consumed_ack_ids == (
        f"ACK-{RegionResourceDegradedScenarioKind.CENTER_FAILED.value}",
    )


def test_validated_d3_isolated_consumption_bridges_into_d4_adoption() -> None:
    case = _case(RegionResourceDegradedScenarioKind.CENTER_FAILED)
    case["ack"] = build_region_resource_isolated_plan_ack_from_d3_evidence(
        lineage=case["lineage"],
        source_plan_source=case["source_plan"],
        applied_plan_source=case["applied_plan"],
        d3_consumption_evidence_source=_d3_consumption_evidence(case),
    )

    evidence = _evaluate(case)

    assert evidence.code == RegionResourceIsolatedAdoptionCode.CANDIDATE_ADOPTED.value
    assert evidence.isolated_candidate_adoption_available is True
    assert evidence.production_runtime_ack is False


def test_d3_bridge_rejects_production_or_authority_claims() -> None:
    case = _case(RegionResourceDegradedScenarioKind.CENTER_FAILED)
    d3_evidence = _d3_consumption_evidence(case)
    d3_evidence["production_runtime_ack"] = True

    with pytest.raises(ValueError, match="production, outcome, or authority"):
        build_region_resource_isolated_plan_ack_from_d3_evidence(
            lineage=case["lineage"],
            source_plan_source=case["source_plan"],
            applied_plan_source=case["applied_plan"],
            d3_consumption_evidence_source=d3_evidence,
        )
