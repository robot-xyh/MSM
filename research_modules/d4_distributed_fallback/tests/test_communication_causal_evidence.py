from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from types import SimpleNamespace

import pytest

from d4_distributed_fallback.communication_causal_evidence import (
    CAUSAL_TOPIC_MESSAGE_KIND,
    COMMUNICATION_DELIVERY_RECEIPT_SCHEMA,
    CausalCommunicationEvidenceGate,
    CausalMessageKind,
    CommunicationDeliveryReceipt,
    CommunicationEvidenceExpectation,
    CommunicationEvidenceReason,
    canonical_payload_digest,
)


_AUTHORITY = "SECONDARY-01"
_GATE_NODE = "D4-AUTHORITY-GATE"
_PLAN_VERSION = 7
_EPOCH = 3
_LEASE_EXPIRY_S = 10.0
_PARTITION_GENERATION = 2
_DECISION_TIMESTAMP_S = 2.0


def _payload(kind: str, identity: str) -> dict[str, object]:
    return {
        "schema": f"fixture-{kind}-v1",
        "identity": identity,
        "plan_version": _PLAN_VERSION,
        "epoch": _EPOCH,
    }


def _topic(message_kind: str) -> str:
    return next(
        topic
        for topic, mapped_kind in CAUSAL_TOPIC_MESSAGE_KIND.items()
        if mapped_kind == message_kind
    )


def _receipt(
    *,
    identity: str = "secondary",
    source: str = _AUTHORITY,
    destination: str = _GATE_NODE,
    message_kind: str = CausalMessageKind.SECONDARY_READINESS.value,
    payload: dict[str, object] | None = None,
    receipt_id: str | None = None,
    message_id: str | None = None,
    sent_timestamp_s: float = 1.0,
    arrival_timestamp_s: float = 1.1,
    authority_id: str = _AUTHORITY,
    plan_version: int = _PLAN_VERSION,
    epoch: int = _EPOCH,
    lease_expires_at_s: float = _LEASE_EXPIRY_S,
    partition_generation: int = _PARTITION_GENERATION,
    schema: str = COMMUNICATION_DELIVERY_RECEIPT_SCHEMA,
) -> CommunicationDeliveryReceipt:
    body = payload or _payload(message_kind, identity)
    return CommunicationDeliveryReceipt(
        schema=schema,
        receipt_id=receipt_id or f"receipt-{message_kind}-{identity}",
        message_id=message_id or f"message-{message_kind}-{identity}",
        source_node_id=source,
        destination_node_id=destination,
        transport_topic=_topic(message_kind),
        transport_sequence=1,
        envelope_schema="scalable3d-bus-v1",
        message_kind=message_kind,
        sent_timestamp_s=sent_timestamp_s,
        arrival_timestamp_s=arrival_timestamp_s,
        authority_id=authority_id,
        plan_version=plan_version,
        epoch=epoch,
        lease_expires_at_s=lease_expires_at_s,
        partition_generation=partition_generation,
        payload_digest=canonical_payload_digest(body),
    )


def _expectation(
    receipt: CommunicationDeliveryReceipt,
    *,
    source: str | None = None,
    destination: str | None = None,
    authority_id: str | None = None,
    plan_version: int | None = None,
    epoch: int | None = None,
    lease_expires_at_s: float | None = None,
    decision_timestamp_s: float = _DECISION_TIMESTAMP_S,
    partition_generation: int | None = None,
    payload_digest: str | None = None,
    message_id: str | None = None,
) -> CommunicationEvidenceExpectation:
    return CommunicationEvidenceExpectation(
        expected_source_node_id=source or receipt.source_node_id,
        expected_destination_node_id=destination or receipt.destination_node_id,
        expected_authority_id=authority_id or receipt.authority_id,
        expected_plan_version=(
            receipt.plan_version if plan_version is None else plan_version
        ),
        expected_epoch=receipt.epoch if epoch is None else epoch,
        expected_lease_expires_at_s=(
            receipt.lease_expires_at_s
            if lease_expires_at_s is None
            else lease_expires_at_s
        ),
        decision_timestamp_s=decision_timestamp_s,
        expected_partition_generation=(
            receipt.partition_generation
            if partition_generation is None
            else partition_generation
        ),
        expected_payload_digest=payload_digest or receipt.payload_digest,
        expected_message_id=message_id,
    )


def _validate(
    gate: CausalCommunicationEvidenceGate,
    receipt: CommunicationDeliveryReceipt | None,
    expectation: CommunicationEvidenceExpectation,
    message_kind: str,
):
    if message_kind == CausalMessageKind.SECONDARY_READINESS.value:
        return gate.validate_secondary_readiness(receipt, expectation)
    if message_kind == CausalMessageKind.REGIONAL_PLAN_BROADCAST.value:
        return gate.validate_regional_plan_broadcast(receipt, expectation)
    if message_kind == CausalMessageKind.REGIONAL_PLAN_OWNER_ACK.value:
        return gate.validate_regional_plan_owner_ack(receipt, expectation)
    if message_kind == CausalMessageKind.COALITION_MEMBER_ACK.value:
        return gate.validate_coalition_member_ack(receipt, expectation)
    raise AssertionError(f"unsupported test message kind: {message_kind}")


@pytest.mark.parametrize("member_count", [5, 20, 50, 100, 200])
def test_causal_gate_scales_and_is_order_independent(member_count: int) -> None:
    receipts: list[
        tuple[
            CommunicationDeliveryReceipt,
            CommunicationEvidenceExpectation,
            str,
        ]
    ] = []
    readiness = _receipt(identity=f"readiness-{member_count}")
    receipts.append(
        (
            readiness,
            _expectation(readiness, message_id=readiness.message_id),
            CausalMessageKind.SECONDARY_READINESS.value,
        )
    )
    for index in range(member_count):
        member_id = f"INT-{index:04d}"
        plan_payload = _payload("plan", member_id)
        plan_receipt = _receipt(
            identity=f"plan-{member_id}",
            destination=member_id,
            message_kind=CausalMessageKind.REGIONAL_PLAN_BROADCAST.value,
            payload=plan_payload,
            arrival_timestamp_s=1.2 + index * 1.0e-6,
        )
        ack_payload = _payload("ack", member_id)
        ack_receipt = _receipt(
            identity=f"ack-{member_id}",
            source=member_id,
            destination=_AUTHORITY,
            message_kind=CausalMessageKind.COALITION_MEMBER_ACK.value,
            payload=ack_payload,
            arrival_timestamp_s=1.4 + index * 1.0e-6,
        )
        receipts.extend(
            (
                (
                    plan_receipt,
                    _expectation(plan_receipt),
                    CausalMessageKind.REGIONAL_PLAN_BROADCAST.value,
                ),
                (
                    ack_receipt,
                    _expectation(ack_receipt),
                    CausalMessageKind.COALITION_MEMBER_ACK.value,
                ),
            )
        )

    forward_gate = CausalCommunicationEvidenceGate()
    forward = {
        receipt.receipt_id: _validate(
            forward_gate,
            receipt,
            expectation,
            message_kind,
        ).to_dict()
        for receipt, expectation, message_kind in receipts
    }
    reverse_gate = CausalCommunicationEvidenceGate()
    reverse = {
        receipt.receipt_id: _validate(
            reverse_gate,
            receipt,
            expectation,
            message_kind,
        ).to_dict()
        for receipt, expectation, message_kind in reversed(receipts)
    }

    assert len(forward) == 1 + 2 * member_count
    assert set(forward) == set(reverse)
    assert all(item["accepted"] for item in forward.values())
    assert all(item["authority_granted"] is False for item in forward.values())
    assert {
        key: (
            value["accepted"],
            value["reason_codes"],
            value["receipt_digest"],
        )
        for key, value in forward.items()
    } == {
        key: (
            value["accepted"],
            value["reason_codes"],
            value["receipt_digest"],
        )
        for key, value in reverse.items()
    }


def test_exact_and_later_receipt_replay_are_idempotent() -> None:
    gate = CausalCommunicationEvidenceGate()
    receipt = _receipt()
    expectation = _expectation(receipt)

    first = gate.validate_secondary_readiness(receipt, expectation)
    duplicate = gate.validate_secondary_readiness(receipt, expectation)
    later = gate.validate_secondary_readiness(
        receipt,
        replace(expectation, decision_timestamp_s=2.1),
    )
    conflict = gate.validate_secondary_readiness(
        replace(
            receipt,
            payload_digest=canonical_payload_digest({"changed": True}),
        ),
        expectation,
    )

    assert first.accepted and not first.idempotent_replay
    assert duplicate.accepted and duplicate.idempotent_replay
    assert later.accepted and later.idempotent_replay
    assert later.decision_timestamp_s == 2.1
    assert conflict.fail_closed
    assert conflict.reason_codes == (
        CommunicationEvidenceReason.RECEIPT_CONFLICT_REPLAY.value,
    )


def test_later_receipt_reuse_keeps_binding_and_time_fences() -> None:
    gate = CausalCommunicationEvidenceGate()
    receipt = _receipt()
    expectation = _expectation(receipt)

    first = gate.validate_secondary_readiness(receipt, expectation)
    later = gate.validate_secondary_readiness(
        receipt,
        replace(expectation, decision_timestamp_s=3.0),
    )
    rewound = gate.validate_secondary_readiness(
        receipt,
        replace(expectation, decision_timestamp_s=2.5),
    )
    changed_evidence_kind = gate.validate_regional_plan_owner_ack(
        receipt,
        replace(expectation, decision_timestamp_s=3.1),
    )
    expired = gate.validate_secondary_readiness(
        receipt,
        replace(expectation, decision_timestamp_s=_LEASE_EXPIRY_S),
    )

    assert first.accepted
    assert later.accepted and later.idempotent_replay
    assert rewound.reason_codes == (
        CommunicationEvidenceReason.DECISION_TIMESTAMP_REWIND.value,
    )
    assert changed_evidence_kind.reason_codes == (
        CommunicationEvidenceReason.RECEIPT_REUSED_FOR_DIFFERENT_EVIDENCE.value,
    )
    assert expired.reason_codes == (
        CommunicationEvidenceReason.LEASE_EXPIRED.value,
    )


@pytest.mark.parametrize(
    "expectation_changes",
    (
        {"expected_source_node_id": "OTHER-SOURCE"},
        {"expected_destination_node_id": "OTHER-GATE"},
        {"expected_authority_id": "OTHER-AUTHORITY"},
        {"expected_message_id": "other-message"},
        {"expected_plan_version": _PLAN_VERSION + 1},
        {"expected_epoch": _EPOCH + 1},
        {"expected_lease_expires_at_s": _LEASE_EXPIRY_S + 1.0},
        {"expected_partition_generation": _PARTITION_GENERATION + 1},
        {
            "expected_payload_digest": canonical_payload_digest(
                {"different": "payload"}
            )
        },
    ),
)
def test_accepted_receipt_cannot_be_rebound(
    expectation_changes: dict[str, object],
) -> None:
    gate = CausalCommunicationEvidenceGate()
    receipt = _receipt()
    expectation = _expectation(receipt)
    assert gate.validate_secondary_readiness(receipt, expectation).accepted

    rebound = gate.validate_secondary_readiness(
        receipt,
        replace(
            expectation,
            decision_timestamp_s=2.1,
            **expectation_changes,
        ),
    )

    assert rebound.reason_codes == (
        CommunicationEvidenceReason.RECEIPT_REUSED_FOR_DIFFERENT_EVIDENCE.value,
    )


@pytest.mark.parametrize(
    ("receipt_changes", "expectation_changes", "reason"),
    [
        (
            {"schema": "unsupported-receipt-v99"},
            {},
            CommunicationEvidenceReason.RECEIPT_SCHEMA_UNSUPPORTED.value,
        ),
        (
            {"transport_topic": "d4.unsupported.v99"},
            {},
            CommunicationEvidenceReason.TRANSPORT_TOPIC_UNSUPPORTED.value,
        ),
        (
            {"source_node_id": "WRONG-SOURCE"},
            {},
            CommunicationEvidenceReason.SOURCE_NODE_MISMATCH.value,
        ),
        (
            {"destination_node_id": "WRONG-DESTINATION"},
            {},
            CommunicationEvidenceReason.DESTINATION_NODE_MISMATCH.value,
        ),
        (
            {
                "message_kind": CausalMessageKind.COALITION_MEMBER_ACK.value,
            },
            {},
            CommunicationEvidenceReason.MESSAGE_KIND_MISMATCH.value,
        ),
        (
            {"authority_id": "OLD-AUTHORITY"},
            {},
            CommunicationEvidenceReason.AUTHORITY_ID_MISMATCH.value,
        ),
        (
            {"plan_version": _PLAN_VERSION - 1},
            {},
            CommunicationEvidenceReason.PLAN_VERSION_STALE.value,
        ),
        (
            {"plan_version": _PLAN_VERSION + 1},
            {},
            CommunicationEvidenceReason.PLAN_VERSION_MISMATCH.value,
        ),
        (
            {"epoch": _EPOCH - 1},
            {},
            CommunicationEvidenceReason.EPOCH_STALE.value,
        ),
        (
            {"epoch": _EPOCH + 1},
            {},
            CommunicationEvidenceReason.EPOCH_MISMATCH.value,
        ),
        (
            {"lease_expires_at_s": 1.5},
            {"expected_lease_expires_at_s": 1.5},
            CommunicationEvidenceReason.LEASE_EXPIRED.value,
        ),
        (
            {},
            {"expected_lease_expires_at_s": 11.0},
            CommunicationEvidenceReason.LEASE_SCOPE_MISMATCH.value,
        ),
        (
            {"arrival_timestamp_s": 2.1},
            {},
            CommunicationEvidenceReason.ARRIVAL_AFTER_DECISION.value,
        ),
        (
            {"partition_generation": _PARTITION_GENERATION - 1},
            {},
            CommunicationEvidenceReason.PARTITION_GENERATION_MISMATCH.value,
        ),
        (
            {"payload_digest": "0" * 64},
            {},
            CommunicationEvidenceReason.PAYLOAD_DIGEST_MISMATCH.value,
        ),
    ],
)
def test_secondary_readiness_negative_reasons_are_stable(
    receipt_changes: dict[str, object],
    expectation_changes: dict[str, object],
    reason: str,
) -> None:
    valid = _receipt()
    receipt = replace(valid, **receipt_changes)
    expectation = replace(_expectation(valid), **expectation_changes)

    result = CausalCommunicationEvidenceGate().validate_secondary_readiness(
        receipt,
        expectation,
    )

    assert result.fail_closed
    assert reason in result.reason_codes
    assert result.authority_granted is False


def test_message_id_mismatch_is_rejected() -> None:
    receipt = _receipt()
    result = CausalCommunicationEvidenceGate().validate_secondary_readiness(
        receipt,
        _expectation(receipt, message_id="another-message"),
    )

    assert result.reason_codes == (
        CommunicationEvidenceReason.MESSAGE_ID_MISMATCH.value,
    )


@pytest.mark.parametrize(
    "entrypoint",
    [
        "validate_secondary_readiness",
        "validate_regional_plan_broadcast",
        "validate_regional_plan_owner_ack",
        "validate_coalition_member_ack",
    ],
)
def test_missing_receipt_fails_closed_for_every_entrypoint(entrypoint: str) -> None:
    receipt = _receipt()
    result = getattr(CausalCommunicationEvidenceGate(), entrypoint)(
        None,
        _expectation(receipt),
    )

    assert result.fail_closed
    assert result.reason_codes == (
        CommunicationEvidenceReason.RECEIPT_MISSING.value,
    )
    assert result.authority_granted is False


def test_disabled_transport_reproduction_rejects_self_reported_readiness() -> None:
    """The main 5v5 reproduction had 8/8 regions self-report ready with no network."""

    self_reported_region_readiness = [
        {
            "selected_layer": "secondary",
            "execution_allowed": True,
            "heartbeat_fresh": True,
            "communication_fresh": True,
            "sustained_ready": True,
        }
        for _ in range(8)
    ]
    assert all(
        item["execution_allowed"]
        and item["heartbeat_fresh"]
        and item["communication_fresh"]
        and item["sustained_ready"]
        for item in self_reported_region_readiness
    )

    receipt_template = _receipt()
    gate = CausalCommunicationEvidenceGate()
    results = [
        gate.validate_secondary_readiness(
            None,
            replace(
                _expectation(receipt_template),
                expected_destination_node_id=f"D4-REGION-{index}",
            ),
        )
        for index in range(8)
    ]

    assert len(results) == 8
    assert all(result.fail_closed for result in results)
    assert {
        result.primary_reason for result in results
    } == {CommunicationEvidenceReason.RECEIPT_MISSING.value}
    assert all(result.authority_granted is False for result in results)


def test_mapping_input_and_invalid_mapping_fail_closed() -> None:
    receipt = _receipt()
    expectation = _expectation(receipt)
    accepted = CausalCommunicationEvidenceGate().validate_secondary_readiness(
        receipt.to_dict(),
        expectation.to_dict(),
    )
    malformed = receipt.to_dict()
    malformed["arrival_timestamp_s"] = float("nan")
    rejected = CausalCommunicationEvidenceGate().validate_secondary_readiness(
        malformed,
        expectation,
    )

    assert accepted.accepted
    assert rejected.reason_codes == (
        CommunicationEvidenceReason.RECEIPT_INVALID.value,
    )


def test_mapping_inputs_reject_extra_fields_and_truth_prefixes() -> None:
    receipt = _receipt()
    expectation = _expectation(receipt)
    extra_receipt = receipt.to_dict()
    extra_receipt["unversioned_extension"] = "not-allowed"
    truth_receipt = receipt.to_dict()
    truth_receipt["truth_score"] = 1.0
    truth_expectation = expectation.to_dict()
    truth_expectation["ground_truth_label"] = "offline-only"

    gate = CausalCommunicationEvidenceGate()
    assert gate.validate_secondary_readiness(
        extra_receipt,
        expectation,
    ).reason_codes == (
        CommunicationEvidenceReason.RECEIPT_INVALID.value,
    )
    assert gate.validate_secondary_readiness(
        truth_receipt,
        expectation,
    ).reason_codes == (
        CommunicationEvidenceReason.RECEIPT_INVALID.value,
    )
    with pytest.raises(ValueError, match="truth fields"):
        gate.validate_secondary_readiness(receipt, truth_expectation)


def test_delivery_receipt_is_strict_frozen_and_truth_free() -> None:
    receipt = _receipt()
    with pytest.raises(FrozenInstanceError):
        receipt.plan_version = 99  # type: ignore[misc]
    with pytest.raises(TypeError):
        CAUSAL_TOPIC_MESSAGE_KIND["d4.injected.v1"] = "secondary_readiness"  # type: ignore[index]
    field_names = {item.name.lower() for item in fields(CommunicationDeliveryReceipt)}
    assert not any("truth" in name or "actor" in name for name in field_names)

    with pytest.raises(ValueError, match="truth fields"):
        canonical_payload_digest({"truth_id": "offline-only"})


@pytest.mark.parametrize(
    "changes",
    [
        {"receipt_id": ""},
        {"message_id": ""},
        {"source_node_id": ""},
        {"destination_node_id": ""},
        {"transport_topic": ""},
        {"transport_sequence": 0},
        {"envelope_schema": ""},
        {"authority_id": ""},
        {"plan_version": 0},
        {"epoch": 0},
        {"partition_generation": -1},
        {"sent_timestamp_s": float("nan")},
        {"arrival_timestamp_s": float("inf")},
        {"arrival_timestamp_s": 0.9},
        {"lease_expires_at_s": 1.0},
        {"payload_digest": "not-a-sha256"},
    ],
)
def test_delivery_receipt_rejects_invalid_contract_fields(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        replace(_receipt(), **changes)


def test_duck_typed_delivered_message_factory_needs_no_runtime_import() -> None:
    payload = {
        **_payload("ack", "INT-0001"),
        "message_id": "episode-1:message-42",
        "message_kind": CausalMessageKind.COALITION_MEMBER_ACK.value,
        "authority_id": _AUTHORITY,
        "lease_expires_at_s": _LEASE_EXPIRY_S,
        "partition_generation": _PARTITION_GENERATION,
    }
    delivered = SimpleNamespace(
        source="INT-0001",
        destination=_AUTHORITY,
        send_timestamp=1.0,
        arrival_timestamp=1.2,
        envelope=SimpleNamespace(
            sequence=42,
            topic="d4.coalition_member_ack.v1",
            source="INT-0001",
            timestamp=1.0,
            schema_version="scalable3d-bus-v1",
            payload=payload,
        ),
    )
    receipt = CommunicationDeliveryReceipt.from_delivered_message(delivered)
    result = CausalCommunicationEvidenceGate().validate_coalition_member_ack(
        receipt,
        _expectation(receipt),
    )

    assert receipt.payload_digest == canonical_payload_digest(payload)
    assert receipt.message_id == payload["message_id"]
    assert receipt.message_kind == payload["message_kind"]
    assert receipt.authority_id == payload["authority_id"]
    assert receipt.plan_version == payload["plan_version"]
    assert receipt.epoch == payload["epoch"]
    assert receipt.lease_expires_at_s == payload["lease_expires_at_s"]
    assert receipt.partition_generation == payload["partition_generation"]
    assert receipt.receipt_id.startswith("d4-receipt-")
    assert result.accepted
    with pytest.raises(TypeError):
        CommunicationDeliveryReceipt.from_delivered_message(  # type: ignore[call-arg]
            delivered,
            authority_id="CALLER-OVERRIDE",
        )


def test_duck_typed_factory_rejects_transport_envelope_source_conflict() -> None:
    delivered = SimpleNamespace(
        source="INT-0001",
        destination=_AUTHORITY,
        send_timestamp=1.0,
        arrival_timestamp=1.2,
        envelope=SimpleNamespace(
            sequence=42,
            topic="d4.coalition_member_ack.v1",
            source="IMPERSONATOR",
            timestamp=1.0,
            schema_version="scalable3d-bus-v1",
            payload={
                **_payload("ack", "INT-0001"),
                "message_id": "episode-1:message-42",
                "message_kind": CausalMessageKind.COALITION_MEMBER_ACK.value,
                "authority_id": _AUTHORITY,
                "lease_expires_at_s": _LEASE_EXPIRY_S,
                "partition_generation": _PARTITION_GENERATION,
            },
        ),
    )

    with pytest.raises(ValueError, match="source must match"):
        CommunicationDeliveryReceipt.from_delivered_message(delivered)


@pytest.mark.parametrize(
    "missing_field",
    [
        "schema",
        "message_id",
        "message_kind",
        "authority_id",
        "plan_version",
        "epoch",
        "lease_expires_at_s",
        "partition_generation",
    ],
)
def test_delivered_message_factory_rejects_missing_payload_fields(
    missing_field: str,
) -> None:
    payload = {
        **_payload("ack", "INT-0001"),
        "message_id": "episode-1:message-42",
        "message_kind": CausalMessageKind.COALITION_MEMBER_ACK.value,
        "authority_id": _AUTHORITY,
        "lease_expires_at_s": _LEASE_EXPIRY_S,
        "partition_generation": _PARTITION_GENERATION,
    }
    payload.pop(missing_field)
    delivered = SimpleNamespace(
        source="INT-0001",
        destination=_AUTHORITY,
        send_timestamp=1.0,
        arrival_timestamp=1.2,
        envelope=SimpleNamespace(
            sequence=42,
            topic="d4.coalition_member_ack.v1",
            source="INT-0001",
            timestamp=1.0,
            schema_version="scalable3d-bus-v1",
            payload=payload,
        ),
    )

    with pytest.raises(ValueError, match="missing fields"):
        CommunicationDeliveryReceipt.from_delivered_message(delivered)


def test_delivered_message_factory_rejects_topic_payload_kind_conflict() -> None:
    payload = {
        **_payload("ack", "INT-0001"),
        "message_id": "episode-1:message-42",
        "message_kind": CausalMessageKind.SECONDARY_READINESS.value,
        "authority_id": _AUTHORITY,
        "lease_expires_at_s": _LEASE_EXPIRY_S,
        "partition_generation": _PARTITION_GENERATION,
    }
    delivered = SimpleNamespace(
        source="INT-0001",
        destination=_AUTHORITY,
        send_timestamp=1.0,
        arrival_timestamp=1.2,
        envelope=SimpleNamespace(
            sequence=42,
            topic="d4.coalition_member_ack.v1",
            source="INT-0001",
            timestamp=1.0,
            schema_version="scalable3d-bus-v1",
            payload=payload,
        ),
    )

    with pytest.raises(ValueError, match="versioned envelope topic"):
        CommunicationDeliveryReceipt.from_delivered_message(delivered)


def test_delivered_message_factory_rejects_envelope_send_time_conflict() -> None:
    payload = {
        **_payload("ack", "INT-0001"),
        "message_id": "episode-1:message-42",
        "message_kind": CausalMessageKind.COALITION_MEMBER_ACK.value,
        "authority_id": _AUTHORITY,
        "lease_expires_at_s": _LEASE_EXPIRY_S,
        "partition_generation": _PARTITION_GENERATION,
    }
    delivered = SimpleNamespace(
        source="INT-0001",
        destination=_AUTHORITY,
        send_timestamp=1.0,
        arrival_timestamp=1.2,
        envelope=SimpleNamespace(
            sequence=42,
            topic="d4.coalition_member_ack.v1",
            source="INT-0001",
            timestamp=0.9,
            schema_version="scalable3d-bus-v1",
            payload=payload,
        ),
    )

    with pytest.raises(ValueError, match="send_timestamp must match"):
        CommunicationDeliveryReceipt.from_delivered_message(delivered)
