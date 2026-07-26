"""Fail-closed communication delivery evidence for D4 authority decisions.

The contract records transport facts only.  A validated receipt can support a
later readiness or coalition decision, but it never grants authority and does
not mutate D4 epoch, lease, plan, or coalition state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass, replace
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
import re
from types import MappingProxyType
from typing import Any, Mapping


COMMUNICATION_DELIVERY_RECEIPT_SCHEMA = "d4-communication-delivery-receipt-v1"
COMMUNICATION_EVIDENCE_EXPECTATION_SCHEMA = (
    "d4-communication-evidence-expectation-v1"
)
COMMUNICATION_EVIDENCE_VALIDATION_SCHEMA = (
    "d4-communication-evidence-validation-v1"
)
COMMUNICATION_RECEIPT_ID_SCHEMA = "d4-communication-receipt-id-v1"

CAUSAL_TOPIC_MESSAGE_KIND: Mapping[str, str] = MappingProxyType(
    {
        "d4.secondary_readiness.v1": "secondary_readiness",
        "d4.regional_plan_broadcast.v1": "regional_plan_broadcast",
        "d4.coalition_member_ack.v1": "coalition_member_ack",
    }
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TIME_TOLERANCE_S = 1.0e-9
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "offline_truth_labels",
    }
)


class CausalMessageKind(str, Enum):
    """Message kinds that may support a D4 authority-related decision."""

    SECONDARY_READINESS = "secondary_readiness"
    REGIONAL_PLAN_BROADCAST = "regional_plan_broadcast"
    COALITION_MEMBER_ACK = "coalition_member_ack"


class CausalEvidenceKind(str, Enum):
    """Validation entry points kept separate for stable audit semantics."""

    SECONDARY_READINESS = "secondary_readiness_delivery"
    REGIONAL_PLAN_BROADCAST = "regional_plan_broadcast_delivery"
    COALITION_MEMBER_ACK = "coalition_member_ack_delivery"


class CommunicationEvidenceReason(str, Enum):
    """Stable fail-closed reason codes emitted by the evidence gate."""

    RECEIPT_MISSING = "receipt_missing"
    RECEIPT_INVALID = "receipt_invalid"
    RECEIPT_SCHEMA_UNSUPPORTED = "receipt_schema_unsupported"
    RECEIPT_CONFLICT_REPLAY = "receipt_conflict_replay"
    RECEIPT_REUSED_FOR_DIFFERENT_EVIDENCE = (
        "receipt_reused_for_different_evidence"
    )
    TRANSPORT_TOPIC_UNSUPPORTED = "transport_topic_unsupported"
    MESSAGE_KIND_TOPIC_MISMATCH = "message_kind_topic_mismatch"
    SOURCE_NODE_MISMATCH = "source_node_mismatch"
    DESTINATION_NODE_MISMATCH = "destination_node_mismatch"
    MESSAGE_KIND_MISMATCH = "message_kind_mismatch"
    MESSAGE_ID_MISMATCH = "message_id_mismatch"
    AUTHORITY_ID_MISMATCH = "authority_id_mismatch"
    PLAN_VERSION_STALE = "plan_version_stale"
    PLAN_VERSION_MISMATCH = "plan_version_mismatch"
    EPOCH_STALE = "epoch_stale"
    EPOCH_MISMATCH = "epoch_mismatch"
    LEASE_EXPIRED = "lease_expired"
    LEASE_SCOPE_MISMATCH = "lease_scope_mismatch"
    ARRIVAL_AFTER_DECISION = "arrival_after_decision"
    PARTITION_GENERATION_MISMATCH = "partition_generation_mismatch"
    PAYLOAD_DIGEST_MISMATCH = "payload_digest_mismatch"


@dataclass(frozen=True)
class CommunicationDeliveryReceipt:
    """Immutable proof that one message reached one explicit destination."""

    receipt_id: str
    message_id: str
    source_node_id: str
    destination_node_id: str
    transport_topic: str
    transport_sequence: int
    envelope_schema: str
    message_kind: str
    sent_timestamp_s: float
    arrival_timestamp_s: float
    authority_id: str
    plan_version: int
    epoch: int
    lease_expires_at_s: float
    partition_generation: int
    payload_digest: str
    schema: str = COMMUNICATION_DELIVERY_RECEIPT_SCHEMA

    def __post_init__(self) -> None:
        for name in (
            "schema",
            "receipt_id",
            "message_id",
            "source_node_id",
            "destination_node_id",
            "transport_topic",
            "envelope_schema",
            "message_kind",
            "authority_id",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        for name in ("plan_version", "epoch"):
            object.__setattr__(
                self,
                name,
                _required_positive_int(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "transport_sequence",
            _required_positive_int(
                self.transport_sequence,
                "transport_sequence",
            ),
        )
        object.__setattr__(
            self,
            "partition_generation",
            _required_nonnegative_int(
                self.partition_generation,
                "partition_generation",
            ),
        )
        sent = _required_nonnegative_float(
            self.sent_timestamp_s,
            "sent_timestamp_s",
        )
        arrival = _required_nonnegative_float(
            self.arrival_timestamp_s,
            "arrival_timestamp_s",
        )
        lease_expiry = _required_nonnegative_float(
            self.lease_expires_at_s,
            "lease_expires_at_s",
        )
        if arrival + _TIME_TOLERANCE_S < sent:
            raise ValueError("arrival_timestamp_s must not precede sent_timestamp_s")
        if lease_expiry <= sent:
            raise ValueError("lease_expires_at_s must be later than sent_timestamp_s")
        object.__setattr__(self, "sent_timestamp_s", sent)
        object.__setattr__(self, "arrival_timestamp_s", arrival)
        object.__setattr__(self, "lease_expires_at_s", lease_expiry)
        object.__setattr__(
            self,
            "payload_digest",
            _required_sha256(self.payload_digest, "payload_digest"),
        )

    @classmethod
    def from_value(cls, value: Any) -> "CommunicationDeliveryReceipt":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("communication delivery receipt must be a mapping or DTO")
        return cls(
            schema=value.get("schema", COMMUNICATION_DELIVERY_RECEIPT_SCHEMA),
            receipt_id=value.get("receipt_id"),
            message_id=value.get("message_id"),
            source_node_id=value.get("source_node_id"),
            destination_node_id=value.get("destination_node_id"),
            transport_topic=value.get("transport_topic"),
            transport_sequence=value.get("transport_sequence"),
            envelope_schema=value.get("envelope_schema"),
            message_kind=value.get("message_kind"),
            sent_timestamp_s=value.get("sent_timestamp_s"),
            arrival_timestamp_s=value.get("arrival_timestamp_s"),
            authority_id=value.get("authority_id"),
            plan_version=value.get("plan_version"),
            epoch=value.get("epoch"),
            lease_expires_at_s=value.get("lease_expires_at_s"),
            partition_generation=value.get("partition_generation"),
            payload_digest=value.get("payload_digest"),
        )

    @classmethod
    def from_delivered_message(
        cls,
        delivered_message: Any,
    ) -> "CommunicationDeliveryReceipt":
        """Build from a duck-typed delivered-message object without AirSim imports.

        The object must expose ``source``, ``destination``, ``send_timestamp``,
        ``arrival_timestamp``, and an ``envelope`` containing ``sequence``,
        ``topic``, ``source``, ``timestamp``, ``schema_version``, and
        ``payload``.  This matches the main runtime transport object while
        leaving the D4 package independent from that implementation.
        """

        source = _required_text(_field(delivered_message, "source"), "source")
        destination = _required_text(
            _field(delivered_message, "destination"),
            "destination",
        )
        sent_timestamp = _required_nonnegative_float(
            _field(delivered_message, "send_timestamp"),
            "send_timestamp",
        )
        arrival_timestamp = _required_nonnegative_float(
            _field(delivered_message, "arrival_timestamp"),
            "arrival_timestamp",
        )
        envelope = _field(delivered_message, "envelope")
        envelope_source = _required_text(
            _field(envelope, "source"),
            "envelope.source",
        )
        if source != envelope_source:
            raise ValueError("delivered source must match envelope source")
        envelope_timestamp = _required_nonnegative_float(
            _field(envelope, "timestamp"),
            "envelope.timestamp",
        )
        if abs(sent_timestamp - envelope_timestamp) > _TIME_TOLERANCE_S:
            raise ValueError(
                "delivered send_timestamp must match envelope timestamp"
            )
        transport_topic = _required_text(
            _field(envelope, "topic"),
            "envelope.topic",
        )
        message_kind = CAUSAL_TOPIC_MESSAGE_KIND.get(transport_topic)
        if message_kind is None:
            raise ValueError("envelope topic is not a supported D4 causal topic")
        transport_sequence = _required_positive_int(
            _field(envelope, "sequence"),
            "envelope.sequence",
        )
        envelope_schema = _required_text(
            _field(envelope, "schema_version"),
            "envelope.schema_version",
        )
        payload = _field(envelope, "payload")
        if not isinstance(payload, Mapping):
            raise ValueError("causal communication payload must be a mapping")
        _assert_truth_free(payload)
        required_payload_fields = (
            "schema",
            "message_id",
            "message_kind",
            "authority_id",
            "plan_version",
            "epoch",
            "lease_expires_at_s",
            "partition_generation",
        )
        missing = tuple(
            name for name in required_payload_fields if name not in payload
        )
        if missing:
            raise ValueError(
                "causal communication payload is missing fields: "
                + ", ".join(missing)
            )
        _required_text(payload["schema"], "payload.schema")
        payload_message_kind = _required_text(
            payload["message_kind"],
            "payload.message_kind",
        )
        if payload_message_kind != message_kind:
            raise ValueError(
                "payload message_kind must match the versioned envelope topic"
            )
        payload_digest = canonical_payload_digest(payload)
        message_id = _required_text(payload["message_id"], "payload.message_id")
        receipt_id = _delivery_receipt_id(
            message_id=message_id,
            source_node_id=source,
            destination_node_id=destination,
            sent_timestamp_s=sent_timestamp,
            arrival_timestamp_s=arrival_timestamp,
            transport_topic=transport_topic,
            transport_sequence=transport_sequence,
            envelope_schema=envelope_schema,
            payload_digest=payload_digest,
        )
        return cls(
            receipt_id=receipt_id,
            message_id=message_id,
            source_node_id=source,
            destination_node_id=destination,
            transport_topic=transport_topic,
            transport_sequence=transport_sequence,
            envelope_schema=envelope_schema,
            message_kind=message_kind,
            sent_timestamp_s=sent_timestamp,
            arrival_timestamp_s=arrival_timestamp,
            authority_id=payload["authority_id"],
            plan_version=payload["plan_version"],
            epoch=payload["epoch"],
            lease_expires_at_s=payload["lease_expires_at_s"],
            partition_generation=payload["partition_generation"],
            payload_digest=payload_digest,
        )

    @property
    def immutable_digest(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CommunicationEvidenceExpectation:
    """Expected authority scope for one delivered evidence item."""

    expected_source_node_id: str
    expected_destination_node_id: str
    expected_authority_id: str
    expected_plan_version: int
    expected_epoch: int
    expected_lease_expires_at_s: float
    decision_timestamp_s: float
    expected_partition_generation: int
    expected_payload_digest: str
    expected_message_id: str | None = None
    schema: str = COMMUNICATION_EVIDENCE_EXPECTATION_SCHEMA

    def __post_init__(self) -> None:
        for name in (
            "schema",
            "expected_source_node_id",
            "expected_destination_node_id",
            "expected_authority_id",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if self.schema != COMMUNICATION_EVIDENCE_EXPECTATION_SCHEMA:
            raise ValueError("communication evidence expectation schema is unsupported")
        if self.expected_message_id is not None:
            object.__setattr__(
                self,
                "expected_message_id",
                _required_text(self.expected_message_id, "expected_message_id"),
            )
        for name in ("expected_plan_version", "expected_epoch"):
            object.__setattr__(
                self,
                name,
                _required_positive_int(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "expected_partition_generation",
            _required_nonnegative_int(
                self.expected_partition_generation,
                "expected_partition_generation",
            ),
        )
        object.__setattr__(
            self,
            "expected_lease_expires_at_s",
            _required_nonnegative_float(
                self.expected_lease_expires_at_s,
                "expected_lease_expires_at_s",
            ),
        )
        object.__setattr__(
            self,
            "decision_timestamp_s",
            _required_nonnegative_float(
                self.decision_timestamp_s,
                "decision_timestamp_s",
            ),
        )
        object.__setattr__(
            self,
            "expected_payload_digest",
            _required_sha256(
                self.expected_payload_digest,
                "expected_payload_digest",
            ),
        )

    @classmethod
    def from_value(cls, value: Any) -> "CommunicationEvidenceExpectation":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError(
                "communication evidence expectation must be a mapping or DTO"
            )
        return cls(
            schema=value.get(
                "schema",
                COMMUNICATION_EVIDENCE_EXPECTATION_SCHEMA,
            ),
            expected_source_node_id=value.get("expected_source_node_id"),
            expected_destination_node_id=value.get(
                "expected_destination_node_id"
            ),
            expected_authority_id=value.get("expected_authority_id"),
            expected_plan_version=value.get("expected_plan_version"),
            expected_epoch=value.get("expected_epoch"),
            expected_lease_expires_at_s=value.get(
                "expected_lease_expires_at_s"
            ),
            decision_timestamp_s=value.get("decision_timestamp_s"),
            expected_partition_generation=value.get(
                "expected_partition_generation"
            ),
            expected_payload_digest=value.get("expected_payload_digest"),
            expected_message_id=value.get("expected_message_id"),
        )

    @property
    def immutable_digest(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CommunicationEvidenceValidation:
    """Audit result only; it is deliberately incapable of granting authority."""

    evidence_kind: str
    accepted: bool
    reason_codes: tuple[str, ...]
    decision_timestamp_s: float
    receipt_id: str | None = None
    message_id: str | None = None
    receipt_digest: str | None = None
    expectation_digest: str | None = None
    idempotent_replay: bool = False
    authority_granted: bool = False
    schema: str = COMMUNICATION_EVIDENCE_VALIDATION_SCHEMA

    def __post_init__(self) -> None:
        if self.authority_granted:
            raise ValueError("communication evidence validation cannot grant authority")
        if bool(self.accepted) == bool(self.reason_codes):
            raise ValueError("accepted evidence must have no reject reason codes")
        object.__setattr__(
            self,
            "evidence_kind",
            _required_text(self.evidence_kind, "evidence_kind"),
        )
        object.__setattr__(
            self,
            "decision_timestamp_s",
            _required_nonnegative_float(
                self.decision_timestamp_s,
                "decision_timestamp_s",
            ),
        )
        object.__setattr__(
            self,
            "reason_codes",
            tuple(dict.fromkeys(str(value) for value in self.reason_codes)),
        )

    @property
    def fail_closed(self) -> bool:
        return not self.accepted

    @property
    def primary_reason(self) -> str | None:
        return self.reason_codes[0] if self.reason_codes else None

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "fail_closed": self.fail_closed,
            "primary_reason": self.primary_reason,
        }


class CausalCommunicationEvidenceGate:
    """Validate delivered receipts and fence replay without changing authority."""

    def __init__(self) -> None:
        self._receipt_digests: dict[str, str] = {}
        self._results: dict[
            tuple[str, str, str],
            CommunicationEvidenceValidation,
        ] = {}

    def validate_secondary_readiness(
        self,
        receipt: CommunicationDeliveryReceipt | Mapping[str, Any] | None,
        expectation: CommunicationEvidenceExpectation | Mapping[str, Any],
    ) -> CommunicationEvidenceValidation:
        return self._validate(
            receipt,
            expectation,
            evidence_kind=CausalEvidenceKind.SECONDARY_READINESS.value,
            expected_message_kind=CausalMessageKind.SECONDARY_READINESS.value,
        )

    def validate_regional_plan_broadcast(
        self,
        receipt: CommunicationDeliveryReceipt | Mapping[str, Any] | None,
        expectation: CommunicationEvidenceExpectation | Mapping[str, Any],
    ) -> CommunicationEvidenceValidation:
        return self._validate(
            receipt,
            expectation,
            evidence_kind=CausalEvidenceKind.REGIONAL_PLAN_BROADCAST.value,
            expected_message_kind=CausalMessageKind.REGIONAL_PLAN_BROADCAST.value,
        )

    def validate_coalition_member_ack(
        self,
        receipt: CommunicationDeliveryReceipt | Mapping[str, Any] | None,
        expectation: CommunicationEvidenceExpectation | Mapping[str, Any],
    ) -> CommunicationEvidenceValidation:
        return self._validate(
            receipt,
            expectation,
            evidence_kind=CausalEvidenceKind.COALITION_MEMBER_ACK.value,
            expected_message_kind=CausalMessageKind.COALITION_MEMBER_ACK.value,
        )

    def _validate(
        self,
        receipt_value: CommunicationDeliveryReceipt | Mapping[str, Any] | None,
        expectation_value: CommunicationEvidenceExpectation | Mapping[str, Any],
        *,
        evidence_kind: str,
        expected_message_kind: str,
    ) -> CommunicationEvidenceValidation:
        expectation = CommunicationEvidenceExpectation.from_value(expectation_value)
        if receipt_value is None:
            return self._result(
                evidence_kind=evidence_kind,
                expectation=expectation,
                reasons=(CommunicationEvidenceReason.RECEIPT_MISSING.value,),
            )
        try:
            receipt = CommunicationDeliveryReceipt.from_value(receipt_value)
        except (KeyError, TypeError, ValueError):
            return self._result(
                evidence_kind=evidence_kind,
                expectation=expectation,
                reasons=(CommunicationEvidenceReason.RECEIPT_INVALID.value,),
            )

        receipt_digest = receipt.immutable_digest
        expectation_digest = expectation.immutable_digest
        existing_digest = self._receipt_digests.get(receipt.receipt_id)
        if existing_digest is not None and existing_digest != receipt_digest:
            return self._result(
                evidence_kind=evidence_kind,
                expectation=expectation,
                receipt=receipt,
                receipt_digest=receipt_digest,
                reasons=(
                    CommunicationEvidenceReason.RECEIPT_CONFLICT_REPLAY.value,
                ),
            )

        result_key = (
            receipt.receipt_id,
            evidence_kind,
            expectation_digest,
        )
        existing_result = self._results.get(result_key)
        if existing_result is not None:
            return replace(existing_result, idempotent_replay=True)
        if existing_digest is not None:
            return self._result(
                evidence_kind=evidence_kind,
                expectation=expectation,
                receipt=receipt,
                receipt_digest=receipt_digest,
                reasons=(
                    CommunicationEvidenceReason.RECEIPT_REUSED_FOR_DIFFERENT_EVIDENCE.value,
                ),
            )

        self._receipt_digests[receipt.receipt_id] = receipt_digest
        reasons: list[str] = []
        if receipt.schema != COMMUNICATION_DELIVERY_RECEIPT_SCHEMA:
            reasons.append(
                CommunicationEvidenceReason.RECEIPT_SCHEMA_UNSUPPORTED.value
            )
        topic_message_kind = CAUSAL_TOPIC_MESSAGE_KIND.get(receipt.transport_topic)
        if topic_message_kind is None:
            reasons.append(
                CommunicationEvidenceReason.TRANSPORT_TOPIC_UNSUPPORTED.value
            )
        elif receipt.message_kind != topic_message_kind:
            reasons.append(
                CommunicationEvidenceReason.MESSAGE_KIND_TOPIC_MISMATCH.value
            )
        if receipt.source_node_id != expectation.expected_source_node_id:
            reasons.append(CommunicationEvidenceReason.SOURCE_NODE_MISMATCH.value)
        if receipt.destination_node_id != expectation.expected_destination_node_id:
            reasons.append(
                CommunicationEvidenceReason.DESTINATION_NODE_MISMATCH.value
            )
        if receipt.message_kind != expected_message_kind:
            reasons.append(CommunicationEvidenceReason.MESSAGE_KIND_MISMATCH.value)
        if (
            expectation.expected_message_id is not None
            and receipt.message_id != expectation.expected_message_id
        ):
            reasons.append(CommunicationEvidenceReason.MESSAGE_ID_MISMATCH.value)
        if receipt.authority_id != expectation.expected_authority_id:
            reasons.append(CommunicationEvidenceReason.AUTHORITY_ID_MISMATCH.value)
        if receipt.plan_version < expectation.expected_plan_version:
            reasons.append(CommunicationEvidenceReason.PLAN_VERSION_STALE.value)
        elif receipt.plan_version != expectation.expected_plan_version:
            reasons.append(CommunicationEvidenceReason.PLAN_VERSION_MISMATCH.value)
        if receipt.epoch < expectation.expected_epoch:
            reasons.append(CommunicationEvidenceReason.EPOCH_STALE.value)
        elif receipt.epoch != expectation.expected_epoch:
            reasons.append(CommunicationEvidenceReason.EPOCH_MISMATCH.value)
        if receipt.lease_expires_at_s <= expectation.decision_timestamp_s:
            reasons.append(CommunicationEvidenceReason.LEASE_EXPIRED.value)
        if (
            abs(
                receipt.lease_expires_at_s
                - expectation.expected_lease_expires_at_s
            )
            > _TIME_TOLERANCE_S
        ):
            reasons.append(CommunicationEvidenceReason.LEASE_SCOPE_MISMATCH.value)
        if (
            receipt.arrival_timestamp_s
            > expectation.decision_timestamp_s + _TIME_TOLERANCE_S
        ):
            reasons.append(
                CommunicationEvidenceReason.ARRIVAL_AFTER_DECISION.value
            )
        if (
            receipt.partition_generation
            != expectation.expected_partition_generation
        ):
            reasons.append(
                CommunicationEvidenceReason.PARTITION_GENERATION_MISMATCH.value
            )
        if receipt.payload_digest != expectation.expected_payload_digest:
            reasons.append(
                CommunicationEvidenceReason.PAYLOAD_DIGEST_MISMATCH.value
            )

        result = self._result(
            evidence_kind=evidence_kind,
            expectation=expectation,
            receipt=receipt,
            receipt_digest=receipt_digest,
            reasons=tuple(reasons),
        )
        self._results[result_key] = result
        return result

    @staticmethod
    def _result(
        *,
        evidence_kind: str,
        expectation: CommunicationEvidenceExpectation,
        reasons: tuple[str, ...],
        receipt: CommunicationDeliveryReceipt | None = None,
        receipt_digest: str | None = None,
    ) -> CommunicationEvidenceValidation:
        return CommunicationEvidenceValidation(
            evidence_kind=evidence_kind,
            accepted=not reasons,
            reason_codes=reasons,
            decision_timestamp_s=expectation.decision_timestamp_s,
            receipt_id=None if receipt is None else receipt.receipt_id,
            message_id=None if receipt is None else receipt.message_id,
            receipt_digest=receipt_digest,
            expectation_digest=expectation.immutable_digest,
        )


def canonical_payload_digest(payload: Any) -> str:
    """Return the SHA-256 digest used to bind a receipt to its exact payload."""

    _assert_truth_free(payload)
    return _canonical_sha256(payload)


def _delivery_receipt_id(
    *,
    message_id: str,
    source_node_id: str,
    destination_node_id: str,
    sent_timestamp_s: float,
    arrival_timestamp_s: float,
    transport_topic: str,
    transport_sequence: int,
    envelope_schema: str,
    payload_digest: str,
) -> str:
    digest = _canonical_sha256(
        {
            "schema": COMMUNICATION_RECEIPT_ID_SCHEMA,
            "message_id": message_id,
            "source_node_id": source_node_id,
            "destination_node_id": destination_node_id,
            "sent_timestamp_s": sent_timestamp_s,
            "arrival_timestamp_s": arrival_timestamp_s,
            "transport_topic": transport_topic,
            "transport_sequence": transport_sequence,
            "envelope_schema": envelope_schema,
            "payload_digest": payload_digest,
        }
    )
    return f"d4-receipt-{digest}"


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"value is not canonically hashable: {type(error).__name__}"
        ) from error
    return sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted((_jsonable(item) for item in value), key=repr)
    return value


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        if name not in value:
            raise ValueError(f"delivered message is missing {name}")
        return value[name]
    if not hasattr(value, name):
        raise ValueError(f"delivered message is missing {name}")
    return getattr(value, name)


def _assert_truth_free(value: Any) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if is_dataclass(item):
            pending.append(asdict(item))
            continue
        if isinstance(item, Mapping):
            forbidden = {
                str(key).strip().lower()
                for key in item
                if str(key).strip().lower() in _FORBIDDEN_ONLINE_KEYS
            }
            if forbidden:
                raise ValueError(
                    "communication payload contains evaluator-only truth fields: "
                    + ", ".join(sorted(forbidden))
                )
            pending.extend(item.values())
            continue
        if isinstance(item, (list, tuple, set)):
            pending.extend(item)


def _required_text(value: Any, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} must not be empty")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    return text


def _required_positive_int(value: Any, name: str) -> int:
    result = _required_int(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _required_nonnegative_int(value: Any, name: str) -> int:
    result = _required_int(value, name)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _required_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be an integer") from error
    try:
        same_value = float(value) == float(result)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if not same_value:
        raise ValueError(f"{name} must be an integer")
    return result


def _required_nonnegative_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be finite and non-negative")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be finite and non-negative") from error
    if not isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _required_sha256(value: Any, name: str) -> str:
    text = _required_text(value, name)
    if _SHA256_PATTERN.fullmatch(text) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return text
