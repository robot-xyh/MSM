from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from d4_distributed_fallback.region_resource import (
    DeterministicResourceProjector,
    RegionResourceNode,
    RegionResourceProjectionConfig,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
)
from d4_distributed_fallback.region_resource_runtime_ack import (
    ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA,
    REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA,
    RegionResourceRuntimeAdoptionKind,
    RegionResourceRuntimeAckCode,
    RegionResourceRuntimeAckParser,
    canonical_runtime_payload_sha256,
)
from d4_distributed_fallback.regional_failover import RegionalAuthorityLayer


def _runtime_fixture() -> dict[str, object]:
    projection = RegionResourceProjectionConfig(advisory_ttl_s=5.0)
    snapshot = RegionResourceSnapshot(
        snapshot_id="snapshot-runtime-1",
        scenario_id="runtime-ack-test",
        scenario_version="v1",
        seed=17,
        timestamp_s=1.0,
        regions=(
            RegionResourceNode(
                region_id="region-000",
                target_demand=2.0,
                high_threat_backlog=1.0,
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
                packet_loss_rate=0.0,
                current_owner_id="C2",
                current_owner_layer=RegionalAuthorityLayer.CENTER,
                plan_id="PLAN-OLD",
                plan_version=2,
                epoch=4,
                lease_expires_at_s=10.0,
                coalition_ack_complete=True,
                owner_active=True,
                fault_fenced=False,
            ),
        ),
        edges=(),
    )
    policy = RuleRegionResourcePolicy(
        RuleRegionResourcePolicyConfig(projection=projection)
    )
    projector = DeterministicResourceProjector(projection)
    recommendation = policy.recommend(snapshot)
    advisory = projector.build_advisory_contract(snapshot, recommendation)
    consumption_view = projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=2.0,
    )
    assert consumption_view.consumable
    consumption = {
        "timestamp": 2.0,
        **consumption_view.to_dict(),
        "bridge_rejection_reason": None,
        "d3_hint_applied": True,
        "advisory_version": 7,
    }
    assignment = {
        "resource_id": "INT-001",
        "global_track_id": "GT3D-000001",
        "coalition_id": "COAL-1",
        "coalition_version": 1,
        "member_role": "primary",
    }
    d4_hint = {
        "considered": True,
        "applied": True,
        "rejected": False,
        "fallback_reason": None,
        "advisory_id": advisory.advisory_id,
        "advisory_version": 7,
        "source_plan_id": "PLAN-OLD",
        "source_plan_version": 2,
    }
    metadata = {
        "active_plan_owner": "center",
        "owner_node_id": "C2",
        "authority_epoch": 4,
        "lease_expires_at_s": 10.0,
        "current_plan_id": "PLAN-NEW",
        "current_plan_version": 3,
        "identity_created_at_s": 2.0,
        "last_evaluated_at_s": 2.0,
        "execution_signature_changed": True,
        "plan_refresh_only": False,
        "evaluation_refresh_only": False,
        "plan_published": True,
        "regional_hint_considered": True,
        "regional_hint_applied": True,
        "regional_hint_rejected": False,
        "regional_hint_fallback_reason": None,
        "regional_hint_advisory_id": advisory.advisory_id,
        "regional_hint_advisory_version": 7,
        "regional_hint_source_plan_id": "PLAN-OLD",
        "regional_hint_source_plan_version": 2,
        "regional_hint_projected": True,
    }
    d3_payload = {
        "timestamp": 2.0,
        "plan_id": "PLAN-NEW",
        "plan_version": 3,
        "created_at": 2.0,
        "assignment_count": 1,
        "assignments": [assignment],
        "metadata": metadata,
    }
    d7_command = {
        "resource_id": "INT-001",
        "global_track_id": "GT3D-000001",
        "plan_id": "PLAN-NEW",
        "plan_version": 3,
        "mode": "midcourse_pn_3d",
        "gate_reason": "midcourse_position_guidance",
    }
    d7_payload = {
        "timestamp": 2.0,
        "command_count": 1,
        "commands": [d7_command],
    }
    d3_envelope = _envelope(
        sequence=21,
        topic="modules.d3.assignment_plan",
        source="D3",
        timestamp=2.0,
        schema="assignment_plan_v2",
        payload=d3_payload,
    )
    d7_envelope = _envelope(
        sequence=24,
        topic="modules.d7.guidance_commands",
        source="D7",
        timestamp=2.0,
        schema="d7-scalable3d-guidance-v1",
        payload=d7_payload,
    )
    binding = {
        "resource_id": "INT-001",
        "global_track_id": "GT3D-000001",
        "coalition_id": "COAL-1",
        "coalition_version": 1,
        "member_role": "primary",
        "guidance_command_present": True,
        "guidance_mode": "midcourse_pn_3d",
        "guidance_gate_reason": "midcourse_position_guidance",
        "control_applied_to_world": True,
        "held": False,
    }
    ack = {
        "decision_id": "PLAN-NEW:v3",
        "ack_timestamp": 2.0,
        "plan_id": "PLAN-NEW",
        "plan_version": 3,
        "plan_created_at": 2.0,
        "plan_schema_version": "assignment_plan_v2",
        "source_plan_bus_sequence": 21,
        "source_plan_payload_sha256": canonical_runtime_payload_sha256(d3_payload),
        "source_guidance_bus_sequence": 24,
        "source_guidance_payload_sha256": canonical_runtime_payload_sha256(
            d7_payload
        ),
        "accepted": True,
        "status_code": "accepted_by_main_runtime",
        "assignment_count": 1,
        "binding_ack_count": 1,
        "fully_bound_to_guidance": True,
        "control_applied_binding_count": 1,
        "held_binding_count": 0,
        "active_plan_owner": "center",
        "owner_node_id": "C2",
        "authority_epoch": 4,
        "lease_expires_at_s": 10.0,
        "d4_regional_hint_evidence": d4_hint,
        "binding_acks": [binding],
        "physical_outcome_available": False,
        "reward_available": False,
    }
    return {
        "advisory": advisory,
        "consumption": consumption,
        "consumption_envelope": _envelope(
            sequence=22,
            topic="modules.d4.region_resource_consumption",
            source="main",
            timestamp=2.0,
            schema="d4-region-resource-consumption-v1",
            payload=consumption,
        ),
        "d3_envelope": d3_envelope,
        "d7_envelope": d7_envelope,
        "ack": ack,
        "ack_envelope": _envelope(
            sequence=25,
            topic="runtime.assignment_plan_ack",
            source="MAIN-RUNTIME",
            timestamp=2.0,
            schema=ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA,
            payload=ack,
        ),
    }


def _envelope(
    *,
    sequence: int,
    topic: str,
    source: str,
    timestamp: float,
    schema: str,
    payload: object,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "topic": topic,
        "source": source,
        "timestamp": timestamp,
        "schema_version": schema,
        "payload": payload,
    }


def _consume(
    fixture: dict[str, object],
    *,
    parser: RegionResourceRuntimeAckParser | None = None,
):
    return (parser or RegionResourceRuntimeAckParser()).consume(
        advisory_source=fixture["advisory"],
        consumption_source=fixture["consumption_envelope"],
        assignment_plan_ack_source=fixture["ack_envelope"],
        d3_plan_source_envelope=fixture["d3_envelope"],
        d7_guidance_source_envelope=fixture["d7_envelope"],
    )


@pytest.mark.parametrize("shape", ("contract", "mapping", "result_mapping", "result"))
def test_runtime_ack_accepts_supported_advisory_shapes(shape: str) -> None:
    fixture = _runtime_fixture()
    advisory = fixture["advisory"]
    if shape == "mapping":
        fixture["advisory"] = advisory.to_dict()  # type: ignore[union-attr]
    elif shape == "result_mapping":
        fixture["advisory"] = {"advisory_contract": advisory.to_dict()}  # type: ignore[union-attr]
    elif shape == "result":
        fixture["advisory"] = SimpleNamespace(advisory_contract=advisory)

    evidence = _consume(fixture)

    assert evidence.schema == REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA
    assert evidence.code == RegionResourceRuntimeAckCode.APPLIED.value
    assert evidence.runtime_advisory_applied_ack_available is True
    assert evidence.adoption_kind == (
        RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
    )
    assert evidence.advisory_version == 7
    assert evidence.source_plan_id == "PLAN-OLD"
    assert evidence.source_plan_version == 2
    assert evidence.applied_plan_id == "PLAN-NEW"
    assert evidence.applied_plan_version == 3
    assert evidence.authority_epoch == 4
    assert evidence.coalition_member_ack_available is False
    assert evidence.physical_outcome_available is False
    assert evidence.attributable_reward_available is False
    assert evidence.paired_shadow_available is False
    assert evidence.ppo_admission_allowed is False
    assert evidence.assist_admission_allowed is False
    assert evidence.authority_admission_allowed is False


def test_raw_main_mappings_require_and_accept_explicit_envelope_schemas() -> None:
    fixture = _runtime_fixture()
    evidence = RegionResourceRuntimeAckParser().consume(
        advisory_source=fixture["advisory"],
        consumption_source=fixture["consumption"],
        assignment_plan_ack_source=fixture["ack"],
        d3_plan_source_envelope=fixture["d3_envelope"],
        d7_guidance_source_envelope=fixture["d7_envelope"],
        consumption_envelope_schema="d4-region-resource-consumption-v1",
        assignment_plan_ack_envelope_schema=ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA,
    )

    assert evidence.runtime_advisory_applied_ack_available


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("ack_schema", RegionResourceRuntimeAckCode.SCHEMA_MISMATCH),
        ("consumption_schema", RegionResourceRuntimeAckCode.SCHEMA_MISMATCH),
        ("d3_schema", RegionResourceRuntimeAckCode.SCHEMA_MISMATCH),
        ("d7_schema", RegionResourceRuntimeAckCode.SCHEMA_MISMATCH),
        ("source_sequence", RegionResourceRuntimeAckCode.SOURCE_SEQUENCE_MISMATCH),
        ("source_hash", RegionResourceRuntimeAckCode.SOURCE_HASH_MISMATCH),
        ("source_plan", RegionResourceRuntimeAckCode.SOURCE_PLAN_MISMATCH),
        ("old_plan", RegionResourceRuntimeAckCode.PLAN_NOT_NEW),
        ("advisory_id", RegionResourceRuntimeAckCode.ADVISORY_IDENTITY_MISMATCH),
        ("advisory_version", RegionResourceRuntimeAckCode.ADVISORY_VERSION_INVALID),
        ("expired", RegionResourceRuntimeAckCode.ADVISORY_EXPIRED),
        ("applied_contradiction", RegionResourceRuntimeAckCode.D3_HINT_STATE_CONTRADICTION),
        ("not_consumable", RegionResourceRuntimeAckCode.CONSUMPTION_NOT_CONSUMABLE),
        ("bridge_rejected", RegionResourceRuntimeAckCode.CONSUMPTION_STATE_CONTRADICTION),
        ("epoch", RegionResourceRuntimeAckCode.AUTHORITY_EPOCH_MISMATCH),
        ("lease", RegionResourceRuntimeAckCode.AUTHORITY_LEASE_EXPIRED),
        ("partial_binding", RegionResourceRuntimeAckCode.PLAN_BINDING_INCOMPLETE),
        ("missing_binding", RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH),
        ("missing_field", RegionResourceRuntimeAckCode.MISSING_FIELD),
        ("nonfinite", RegionResourceRuntimeAckCode.NONFINITE_TIMESTAMP),
    ),
)
def test_runtime_ack_fail_closed_matrix(
    mutation: str,
    expected_code: RegionResourceRuntimeAckCode,
) -> None:
    fixture = _runtime_fixture()
    consumption_envelope = fixture["consumption_envelope"]
    ack_envelope = fixture["ack_envelope"]
    d3_envelope = fixture["d3_envelope"]
    d7_envelope = fixture["d7_envelope"]
    assert isinstance(consumption_envelope, dict)
    assert isinstance(ack_envelope, dict)
    assert isinstance(d3_envelope, dict)
    assert isinstance(d7_envelope, dict)
    consumption = consumption_envelope["payload"]
    ack = ack_envelope["payload"]
    d3_payload = d3_envelope["payload"]
    assert isinstance(consumption, dict)
    assert isinstance(ack, dict)
    assert isinstance(d3_payload, dict)
    d4 = ack["d4_regional_hint_evidence"]
    assert isinstance(d4, dict)

    if mutation == "ack_schema":
        ack_envelope["schema_version"] = "bad-ack-schema"
    elif mutation == "consumption_schema":
        consumption_envelope["schema_version"] = "bad-consumption-schema"
    elif mutation == "d3_schema":
        d3_envelope["schema_version"] = "assignment_plan_v999"
    elif mutation == "d7_schema":
        d7_envelope["schema_version"] = "d7-guidance-v999"
    elif mutation == "source_sequence":
        ack["source_plan_bus_sequence"] = 20
    elif mutation == "source_hash":
        ack["source_plan_payload_sha256"] = "0" * 64
    elif mutation == "source_plan":
        d4["source_plan_id"] = "PLAN-OTHER"
        d3_payload["metadata"]["regional_hint_source_plan_id"] = "PLAN-OTHER"  # type: ignore[index]
        ack["source_plan_payload_sha256"] = canonical_runtime_payload_sha256(
            d3_payload
        )
    elif mutation == "old_plan":
        ack["plan_id"] = "PLAN-OLD"
        ack["plan_version"] = 2
        ack["plan_created_at"] = 1.0
    elif mutation == "advisory_id":
        d4["advisory_id"] = "ADV-OTHER"
    elif mutation == "advisory_version":
        consumption["advisory_version"] = 8
    elif mutation == "expired":
        consumption["timestamp"] = 6.0
        consumption["evaluated_at_s"] = 6.0
        consumption_envelope["timestamp"] = 6.0
    elif mutation == "applied_contradiction":
        d4["rejected"] = True
    elif mutation == "not_consumable":
        consumption["consumable"] = False
        consumption["rejection_reasons"] = ["advisory_expired"]
    elif mutation == "bridge_rejected":
        consumption["bridge_rejection_reason"] = "d3_rejected"
    elif mutation == "epoch":
        ack["authority_epoch"] = 3
    elif mutation == "lease":
        ack["ack_timestamp"] = 10.0
        ack_envelope["timestamp"] = 10.0
    elif mutation == "partial_binding":
        ack["fully_bound_to_guidance"] = False
    elif mutation == "missing_binding":
        d7_envelope["payload"]["commands"] = []  # type: ignore[index]
        d7_envelope["payload"]["command_count"] = 0  # type: ignore[index]
        ack["source_guidance_payload_sha256"] = canonical_runtime_payload_sha256(
            d7_envelope["payload"]
        )
    elif mutation == "missing_field":
        del d4["applied"]
    elif mutation == "nonfinite":
        ack["ack_timestamp"] = float("nan")
        ack_envelope["timestamp"] = float("nan")
    else:  # pragma: no cover - parameter table is exhaustive
        raise AssertionError(mutation)

    evidence = _consume(fixture)

    assert evidence.runtime_advisory_applied_ack_available is False
    assert evidence.code == expected_code.value
    assert evidence.rejection_reasons == (expected_code.value,)


def test_successful_advisory_cannot_be_consumed_twice() -> None:
    fixture = _runtime_fixture()
    parser = RegionResourceRuntimeAckParser()

    first = _consume(fixture, parser=parser)
    duplicate = _consume(deepcopy(fixture), parser=parser)

    assert first.runtime_advisory_applied_ack_available
    assert duplicate.runtime_advisory_applied_ack_available is False
    assert duplicate.code == RegionResourceRuntimeAckCode.ADVISORY_ALREADY_CONSUMED.value
    assert parser.consumed_advisories == ((first.advisory_id, 7),)


def test_successful_advisory_version_cannot_move_backwards() -> None:
    first_fixture = _runtime_fixture()
    stale_fixture = _runtime_fixture()
    parser = RegionResourceRuntimeAckParser()
    first = _consume(first_fixture, parser=parser)
    consumption = stale_fixture["consumption_envelope"]["payload"]  # type: ignore[index]
    ack = stale_fixture["ack_envelope"]["payload"]  # type: ignore[index]
    d3_payload = stale_fixture["d3_envelope"]["payload"]  # type: ignore[index]
    consumption["advisory_version"] = 6  # type: ignore[index]
    ack["d4_regional_hint_evidence"]["advisory_version"] = 6  # type: ignore[index]
    d3_payload["metadata"]["regional_hint_advisory_version"] = 6  # type: ignore[index]
    ack["source_plan_payload_sha256"] = canonical_runtime_payload_sha256(
        d3_payload
    )  # type: ignore[index]

    stale = _consume(stale_fixture, parser=parser)

    assert first.runtime_advisory_applied_ack_available
    assert stale.runtime_advisory_applied_ack_available is False
    assert stale.code == RegionResourceRuntimeAckCode.ADVISORY_VERSION_STALE.value


def test_projected_advisory_without_runtime_chain_is_not_applied_ack() -> None:
    fixture = _runtime_fixture()
    ack = fixture["ack_envelope"]["payload"]  # type: ignore[index]
    ack["d4_regional_hint_evidence"]["applied"] = False  # type: ignore[index]
    ack["d4_regional_hint_evidence"]["rejected"] = True  # type: ignore[index]
    ack["d4_regional_hint_evidence"]["fallback_reason"] = "rule_fallback"  # type: ignore[index]

    evidence = _consume(fixture)

    assert fixture["advisory"].projected is True  # type: ignore[union-attr]
    assert evidence.runtime_advisory_applied_ack_available is False
    assert evidence.code == RegionResourceRuntimeAckCode.D3_HINT_STATE_CONTRADICTION.value
