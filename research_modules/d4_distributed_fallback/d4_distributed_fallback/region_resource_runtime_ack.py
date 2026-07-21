"""Strict, main-independent runtime acknowledgement evidence for D4 advice.

The verifier in this module consumes immutable mappings or envelope-like
objects.  It deliberately does not import the main runtime, D3, D7, or the
scalable simulation package.  A projected D4 recommendation is only upgraded
to an applied runtime acknowledgement after the main consumption record, the
new D3 plan, its D7 binding, and the source message hashes agree.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from typing import Any

from .region_resource import (
    REGION_RESOURCE_ADVISORY_SCHEMA,
    REGION_RESOURCE_CONSUMPTION_SCHEMA,
    RegionResourceAdvisoryContract,
)


REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA = (
    "d4-region-resource-runtime-ack-evidence-v2"
)
REGION_RESOURCE_ADVICE_ENVELOPE_SCHEMA = (
    "d4-region-resource-advisory-runtime-v1"
)
ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA = (
    "scalable3d-assignment-plan-runtime-ack-v1"
)
D3_ASSIGNMENT_PLAN_SCHEMA = "assignment_plan_v2"
D7_GUIDANCE_SCHEMA = "d7-scalable3d-guidance-v1"

REGION_RESOURCE_CONSUMPTION_TOPIC = "modules.d4.region_resource_consumption"
D3_ASSIGNMENT_PLAN_TOPIC = "modules.d3.assignment_plan"
D7_GUIDANCE_TOPIC = "modules.d7.guidance_commands"
ASSIGNMENT_PLAN_RUNTIME_ACK_TOPIC = "runtime.assignment_plan_ack"


class RegionResourceRuntimeAckCode(str, Enum):
    """Stable fail-closed result codes for runtime evidence ingestion."""

    APPLIED = "runtime_advisory_applied_ack_available"
    ADVISORY_MISSING = "advisory_missing"
    ADVISORY_INVALID = "advisory_invalid"
    ADVISORY_NOT_PROJECTED = "advisory_not_projected"
    ADVISORY_IDENTITY_MISMATCH = "advisory_identity_mismatch"
    ADVISORY_VERSION_INVALID = "advisory_version_invalid"
    ADVISORY_VERSION_STALE = "advisory_version_stale"
    ADVISORY_ALREADY_CONSUMED = "advisory_already_consumed"
    ADVISORY_NOT_YET_VALID = "advisory_not_yet_valid"
    ADVISORY_EXPIRED = "advisory_expired"
    SCHEMA_MISMATCH = "schema_mismatch"
    SOURCE_ENVELOPE_INVALID = "source_envelope_invalid"
    SOURCE_SEQUENCE_MISMATCH = "source_sequence_mismatch"
    SOURCE_HASH_MISMATCH = "source_payload_sha256_mismatch"
    SOURCE_PLAN_MISMATCH = "source_plan_mismatch"
    PLAN_NOT_NEW = "acknowledged_plan_not_new"
    PLAN_REFRESH_SOURCE_MISSING = "plan_refresh_source_missing"
    PLAN_REFRESH_FLAGS_INVALID = "plan_refresh_flags_invalid"
    PLAN_REFRESH_BINDINGS_CHANGED = "plan_refresh_bindings_changed"
    PLAN_REFRESH_TIMESTAMP_MISMATCH = "plan_refresh_timestamp_mismatch"
    MISSING_FIELD = "required_field_missing"
    INVALID_FIELD_TYPE = "invalid_field_type"
    NONFINITE_TIMESTAMP = "nonfinite_timestamp"
    TIMESTAMP_MISMATCH = "timestamp_mismatch"
    CONSUMPTION_NOT_CONSUMABLE = "consumption_not_consumable"
    CONSUMPTION_STATE_CONTRADICTION = "consumption_state_contradiction"
    D3_HINT_NOT_APPLIED = "d3_regional_hint_not_applied"
    D3_HINT_STATE_CONTRADICTION = "d3_regional_hint_state_contradiction"
    MAIN_PLAN_NOT_ACCEPTED = "main_plan_not_accepted"
    AUTHORITY_SCOPE_MISMATCH = "authority_scope_mismatch"
    AUTHORITY_OWNER_MISMATCH = "authority_owner_mismatch"
    AUTHORITY_EPOCH_MISMATCH = "authority_epoch_mismatch"
    AUTHORITY_LEASE_MISMATCH = "authority_lease_mismatch"
    AUTHORITY_LEASE_EXPIRED = "authority_lease_expired"
    PLAN_BINDING_INCOMPLETE = "plan_binding_incomplete"
    PLAN_BINDING_MISMATCH = "plan_binding_mismatch"


class RegionResourceRuntimeAdoptionKind(str, Enum):
    """The limited fact proved by a successful runtime acknowledgement."""

    EVALUATION_REFRESH_APPLIED = "evaluation_refresh_applied"
    NEW_EXECUTION_PLAN_APPLIED = "new_execution_plan_applied"


@dataclass(frozen=True)
class RuntimeEnvelopeEvidence:
    """Read-only view of a versioned runtime envelope."""

    sequence: int | None
    topic: str
    source: str
    timestamp_s: float
    schema_version: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class RegionResourceRuntimeAckEvidence:
    """Immutable verdict for one D4 advisory runtime-consumption chain."""

    code: str
    reason: str
    runtime_advisory_applied_ack_available: bool
    adoption_kind: str | None = None
    advisory_id: str | None = None
    advisory_version: int | None = None
    source_plan_id: str | None = None
    source_plan_version: int | None = None
    applied_plan_id: str | None = None
    applied_plan_version: int | None = None
    consumed_at_s: float | None = None
    acknowledged_at_s: float | None = None
    owner_layer: str | None = None
    owner_node_id: str | None = None
    authority_epoch: int | None = None
    lease_expires_at_s: float | None = None
    source_plan_bus_sequence: int | None = None
    advisory_source_plan_bus_sequence: int | None = None
    source_guidance_bus_sequence: int | None = None
    advisory_payload_sha256: str | None = None
    source_plan_payload_sha256: str | None = None
    source_guidance_payload_sha256: str | None = None
    rejection_reasons: tuple[str, ...] = ()
    coalition_member_ack_available: bool = False
    physical_outcome_available: bool = False
    attributable_reward_available: bool = False
    paired_shadow_available: bool = False
    ppo_admission_allowed: bool = False
    assist_admission_allowed: bool = False
    authority_admission_allowed: bool = False
    schema: str = REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_RUNTIME_ACK_EVIDENCE_SCHEMA:
            raise ValueError(f"unsupported runtime ACK evidence schema: {self.schema}")
        if not self.code or not self.reason:
            raise ValueError("runtime ACK evidence code and reason must not be empty")
        if self.runtime_advisory_applied_ack_available and self.rejection_reasons:
            raise ValueError("available runtime ACK evidence cannot contain rejections")
        allowed_kinds = {item.value for item in RegionResourceRuntimeAdoptionKind}
        if self.runtime_advisory_applied_ack_available:
            if self.adoption_kind not in allowed_kinds:
                raise ValueError("available runtime ACK evidence requires an adoption kind")
        elif self.adoption_kind is not None:
            raise ValueError("rejected runtime ACK evidence cannot claim an adoption kind")
        if any(
            (
                self.coalition_member_ack_available,
                self.physical_outcome_available,
                self.attributable_reward_available,
                self.paired_shadow_available,
                self.ppo_admission_allowed,
                self.assist_admission_allowed,
                self.authority_admission_allowed,
            )
        ):
            raise ValueError("runtime advisory ACK cannot grant downstream authority")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _EvidenceContext:
    adoption_kind: str | None = None
    advisory_id: str | None = None
    advisory_version: int | None = None
    source_plan_id: str | None = None
    source_plan_version: int | None = None
    applied_plan_id: str | None = None
    applied_plan_version: int | None = None
    consumed_at_s: float | None = None
    acknowledged_at_s: float | None = None
    owner_layer: str | None = None
    owner_node_id: str | None = None
    authority_epoch: int | None = None
    lease_expires_at_s: float | None = None
    source_plan_bus_sequence: int | None = None
    advisory_source_plan_bus_sequence: int | None = None
    source_guidance_bus_sequence: int | None = None
    advisory_payload_sha256: str | None = None
    source_plan_payload_sha256: str | None = None
    source_guidance_payload_sha256: str | None = None


class _ValidationFailure(ValueError):
    def __init__(self, code: RegionResourceRuntimeAckCode, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class RegionResourceRuntimeAckParser:
    """Validate and consume D4 advisory runtime acknowledgements once.

    Instances retain only successfully consumed ``(advisory_id,
    advisory_version)`` pairs.  Replaying a successful acknowledgement through
    the same parser is rejected.  Invalid evidence never changes D4 authority,
    a D3 plan, or a D7 command.
    """

    def __init__(self) -> None:
        self._consumed: set[tuple[str, int]] = set()
        self._highest_advisory_version = 0

    @property
    def consumed_advisories(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._consumed))

    def consume(
        self,
        *,
        advisory_source: Any,
        consumption_source: Any,
        assignment_plan_ack_source: Any,
        d3_plan_source_envelope: Any,
        d7_guidance_source_envelope: Any,
        advisory_source_plan_envelope: Any | None = None,
        consumption_envelope_schema: str | None = None,
        assignment_plan_ack_envelope_schema: str | None = None,
    ) -> RegionResourceRuntimeAckEvidence:
        """Return a fail-closed evidence verdict without importing main/D3/D7."""

        context = _EvidenceContext()
        try:
            advisory = _parse_advisory(advisory_source)
            context.advisory_id = advisory.advisory_id
            context.advisory_payload_sha256 = canonical_runtime_payload_sha256(
                advisory.to_dict()
            )
            if not advisory.projected:
                _fail(
                    RegionResourceRuntimeAckCode.ADVISORY_NOT_PROJECTED,
                    "D4 advisory did not pass deterministic projection",
                )
            if advisory.publication_rejections:
                _fail(
                    RegionResourceRuntimeAckCode.ADVISORY_INVALID,
                    "D4 advisory contains publication rejections",
                )

            consumption_envelope = _parse_envelope(
                consumption_source,
                expected_topic=REGION_RESOURCE_CONSUMPTION_TOPIC,
                expected_sources=("main", "MAIN-RUNTIME"),
                expected_schema=REGION_RESOURCE_CONSUMPTION_SCHEMA,
                explicit_schema=consumption_envelope_schema,
                raw_timestamp_keys=("timestamp", "evaluated_at_s"),
                require_sequence=False,
            )
            consumption = consumption_envelope.payload
            _require_schema(
                consumption,
                REGION_RESOURCE_CONSUMPTION_SCHEMA,
                path="consumption.schema",
            )
            nested_advisory = _parse_advisory(
                _required(consumption, "advisory", "consumption")
            )
            if nested_advisory.to_dict() != advisory.to_dict():
                _fail(
                    RegionResourceRuntimeAckCode.ADVISORY_IDENTITY_MISMATCH,
                    "consumption advisory does not match the supplied D4 advisory",
                )
            consumed_at = _finite_time(
                _required(consumption, "evaluated_at_s", "consumption"),
                "consumption.evaluated_at_s",
            )
            context.consumed_at_s = consumed_at
            payload_timestamp = _finite_time(
                _required(consumption, "timestamp", "consumption"),
                "consumption.timestamp",
            )
            if not _same_time(payload_timestamp, consumed_at) or not _same_time(
                consumption_envelope.timestamp_s, consumed_at
            ):
                _fail(
                    RegionResourceRuntimeAckCode.TIMESTAMP_MISMATCH,
                    "consumption envelope, publication, and evaluation times differ",
                )
            _validate_consumption_state(consumption)
            _validate_consumption_advisory_binding(advisory, consumption, consumed_at)

            source_plans = tuple(advisory.source_plan_versions)
            if len(source_plans) != 1:
                _fail(
                    RegionResourceRuntimeAckCode.SOURCE_PLAN_MISMATCH,
                    "runtime advisory ACK requires one unambiguous source plan",
                )
            context.source_plan_id, context.source_plan_version = source_plans[0]

            ack_envelope = _parse_envelope(
                assignment_plan_ack_source,
                expected_topic=ASSIGNMENT_PLAN_RUNTIME_ACK_TOPIC,
                expected_sources=("MAIN-RUNTIME", "main"),
                expected_schema=ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA,
                explicit_schema=assignment_plan_ack_envelope_schema,
                raw_timestamp_keys=("ack_timestamp",),
                require_sequence=False,
            )
            ack = ack_envelope.payload
            acknowledged_at = _finite_time(
                _required(ack, "ack_timestamp", "assignment_plan_ack"),
                "assignment_plan_ack.ack_timestamp",
            )
            context.acknowledged_at_s = acknowledged_at
            if not _same_time(ack_envelope.timestamp_s, acknowledged_at):
                _fail(
                    RegionResourceRuntimeAckCode.TIMESTAMP_MISMATCH,
                    "assignment ACK envelope and payload timestamps differ",
                )
            if acknowledged_at < consumed_at:
                _fail(
                    RegionResourceRuntimeAckCode.TIMESTAMP_MISMATCH,
                    "assignment ACK precedes D4 advisory consumption",
                )

            d3_envelope = _parse_envelope(
                d3_plan_source_envelope,
                expected_topic=D3_ASSIGNMENT_PLAN_TOPIC,
                expected_sources=("D3",),
                expected_schema=D3_ASSIGNMENT_PLAN_SCHEMA,
                explicit_schema=None,
                raw_timestamp_keys=("timestamp", "created_at"),
                require_sequence=True,
            )
            d7_envelope = _parse_envelope(
                d7_guidance_source_envelope,
                expected_topic=D7_GUIDANCE_TOPIC,
                expected_sources=("D7",),
                expected_schema=D7_GUIDANCE_SCHEMA,
                explicit_schema=None,
                raw_timestamp_keys=("timestamp",),
                require_sequence=True,
            )
            source_plan_envelope = None
            if advisory_source_plan_envelope is not None:
                source_plan_envelope = _parse_envelope(
                    advisory_source_plan_envelope,
                    expected_topic=D3_ASSIGNMENT_PLAN_TOPIC,
                    expected_sources=("D3",),
                    expected_schema=D3_ASSIGNMENT_PLAN_SCHEMA,
                    explicit_schema=None,
                    raw_timestamp_keys=("timestamp", "created_at"),
                    require_sequence=True,
                )
                context.advisory_source_plan_bus_sequence = (
                    source_plan_envelope.sequence
                )
            context.source_plan_bus_sequence = d3_envelope.sequence
            context.source_guidance_bus_sequence = d7_envelope.sequence
            context.source_plan_payload_sha256 = canonical_runtime_payload_sha256(
                d3_envelope.payload
            )
            context.source_guidance_payload_sha256 = canonical_runtime_payload_sha256(
                d7_envelope.payload
            )

            self._validate_ack_and_sources(
                advisory=advisory,
                consumption=consumption,
                ack=ack,
                ack_envelope=ack_envelope,
                d3_envelope=d3_envelope,
                d7_envelope=d7_envelope,
                advisory_source_plan_envelope=source_plan_envelope,
                context=context,
            )

            assert context.advisory_id is not None
            assert context.advisory_version is not None
            consumption_version = consumption.get("advisory_version")
            if consumption_version is not None:
                parsed_consumption_version = _positive_int(
                    consumption_version,
                    "consumption.advisory_version",
                    RegionResourceRuntimeAckCode.ADVISORY_VERSION_INVALID,
                )
                if parsed_consumption_version != context.advisory_version:
                    _fail(
                        RegionResourceRuntimeAckCode.ADVISORY_VERSION_INVALID,
                        "consumption and D3 ACK advisory versions differ",
                    )
            key = (context.advisory_id, context.advisory_version)
            if key in self._consumed:
                _fail(
                    RegionResourceRuntimeAckCode.ADVISORY_ALREADY_CONSUMED,
                    "D4 advisory runtime acknowledgement was already consumed",
                )
            if context.advisory_version <= self._highest_advisory_version:
                _fail(
                    RegionResourceRuntimeAckCode.ADVISORY_VERSION_STALE,
                    "D4 advisory version did not advance monotonically",
                )
            self._consumed.add(key)
            self._highest_advisory_version = context.advisory_version
            return _available_evidence(context)
        except _ValidationFailure as error:
            return _rejected_evidence(context, error)
        except (KeyError, TypeError, ValueError) as error:
            failure = _ValidationFailure(
                RegionResourceRuntimeAckCode.ADVISORY_INVALID,
                f"runtime evidence parser rejected malformed input: {type(error).__name__}",
            )
            return _rejected_evidence(context, failure)

    @staticmethod
    def _validate_ack_and_sources(
        *,
        advisory: RegionResourceAdvisoryContract,
        consumption: Mapping[str, Any],
        ack: Mapping[str, Any],
        ack_envelope: RuntimeEnvelopeEvidence,
        d3_envelope: RuntimeEnvelopeEvidence,
        d7_envelope: RuntimeEnvelopeEvidence,
        advisory_source_plan_envelope: RuntimeEnvelopeEvidence | None,
        context: _EvidenceContext,
    ) -> None:
        if _strict_bool(
            _required(ack, "accepted", "assignment_plan_ack"),
            "assignment_plan_ack.accepted",
        ) is not True or _required(
            ack, "status_code", "assignment_plan_ack"
        ) != "accepted_by_main_runtime":
            _fail(
                RegionResourceRuntimeAckCode.MAIN_PLAN_NOT_ACCEPTED,
                "main runtime did not accept the D3 plan",
            )

        plan_id = _text(
            _required(ack, "plan_id", "assignment_plan_ack"),
            "assignment_plan_ack.plan_id",
        )
        plan_version = _nonnegative_int(
            _required(ack, "plan_version", "assignment_plan_ack"),
            "assignment_plan_ack.plan_version",
        )
        context.applied_plan_id = plan_id
        context.applied_plan_version = plan_version
        plan_created_at = _finite_time(
            _required(ack, "plan_created_at", "assignment_plan_ack"),
            "assignment_plan_ack.plan_created_at",
        )
        assert context.source_plan_id is not None
        assert context.source_plan_version is not None
        assert context.consumed_at_s is not None
        assert context.acknowledged_at_s is not None
        metadata = _required_mapping(d3_envelope.payload, "metadata", "d3_plan")
        adoption_kind = RegionResourceRuntimeAckParser._validate_adoption_kind(
            metadata=metadata,
            source_plan_envelope=advisory_source_plan_envelope,
            current_plan_envelope=d3_envelope,
            source_plan_id=context.source_plan_id,
            source_plan_version=context.source_plan_version,
            plan_id=plan_id,
            plan_version=plan_version,
            plan_created_at=plan_created_at,
            consumed_at_s=context.consumed_at_s,
            acknowledged_at_s=context.acknowledged_at_s,
        )
        context.adoption_kind = adoption_kind.value
        if context.acknowledged_at_s < plan_created_at:
            _fail(
                RegionResourceRuntimeAckCode.TIMESTAMP_MISMATCH,
                "assignment ACK precedes the acknowledged plan",
            )
        if _required(ack, "decision_id", "assignment_plan_ack") != (
            f"{plan_id}:v{plan_version}"
        ):
            _fail(
                RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                "assignment ACK decision identity does not match its plan",
            )

        d4_evidence = _required_mapping(
            ack,
            "d4_regional_hint_evidence",
            "assignment_plan_ack",
        )
        considered = _strict_bool(
            _required(d4_evidence, "considered", "d4_regional_hint_evidence"),
            "d4_regional_hint_evidence.considered",
        )
        applied = _strict_bool(
            _required(d4_evidence, "applied", "d4_regional_hint_evidence"),
            "d4_regional_hint_evidence.applied",
        )
        rejected = _strict_bool(
            _required(d4_evidence, "rejected", "d4_regional_hint_evidence"),
            "d4_regional_hint_evidence.rejected",
        )
        fallback_reason = _required(
            d4_evidence,
            "fallback_reason",
            "d4_regional_hint_evidence",
        )
        if (considered, applied, rejected) != (True, True, False):
            _fail(
                RegionResourceRuntimeAckCode.D3_HINT_STATE_CONTRADICTION,
                "D3 regional hint flags are not considered/applied/not-rejected",
            )
        if fallback_reason is not None:
            _fail(
                RegionResourceRuntimeAckCode.D3_HINT_NOT_APPLIED,
                "an applied D3 regional hint cannot carry a fallback reason",
            )
        advisory_id = _text(
            _required(d4_evidence, "advisory_id", "d4_regional_hint_evidence"),
            "d4_regional_hint_evidence.advisory_id",
        )
        if advisory_id != advisory.advisory_id:
            _fail(
                RegionResourceRuntimeAckCode.ADVISORY_IDENTITY_MISMATCH,
                "D3 ACK advisory identity differs from the D4 contract",
            )
        context.advisory_version = _positive_int(
            _required(d4_evidence, "advisory_version", "d4_regional_hint_evidence"),
            "d4_regional_hint_evidence.advisory_version",
            RegionResourceRuntimeAckCode.ADVISORY_VERSION_INVALID,
        )
        ack_source_plan_id = _text(
            _required(d4_evidence, "source_plan_id", "d4_regional_hint_evidence"),
            "d4_regional_hint_evidence.source_plan_id",
        )
        ack_source_plan_version = _nonnegative_int(
            _required(
                d4_evidence,
                "source_plan_version",
                "d4_regional_hint_evidence",
            ),
            "d4_regional_hint_evidence.source_plan_version",
        )
        if (
            ack_source_plan_id != context.source_plan_id
            or ack_source_plan_version != context.source_plan_version
        ):
            _fail(
                RegionResourceRuntimeAckCode.SOURCE_PLAN_MISMATCH,
                "D3 ACK source plan differs from the D4 advisory source",
            )

        RegionResourceRuntimeAckParser._validate_source_envelope_bindings(
            ack=ack,
            d3_envelope=d3_envelope,
            d7_envelope=d7_envelope,
            context=context,
        )
        RegionResourceRuntimeAckParser._validate_d3_plan_payload(
            ack=ack,
            d3_payload=d3_envelope.payload,
            d3_schema=d3_envelope.schema_version,
            d4_evidence=d4_evidence,
            plan_id=plan_id,
            plan_version=plan_version,
            plan_created_at=plan_created_at,
        )
        RegionResourceRuntimeAckParser._validate_authority(
            advisory=advisory,
            ack=ack,
            d3_payload=d3_envelope.payload,
            adoption_kind=adoption_kind,
            context=context,
        )
        RegionResourceRuntimeAckParser._validate_binding_records(
            ack=ack,
            d3_payload=d3_envelope.payload,
            d7_payload=d7_envelope.payload,
            plan_id=plan_id,
            plan_version=plan_version,
        )

        # The consumption record is an independent main-side acknowledgement.
        if _strict_bool(
            _required(consumption, "d3_hint_applied", "consumption"),
            "consumption.d3_hint_applied",
        ) is not True:
            _fail(
                RegionResourceRuntimeAckCode.D3_HINT_NOT_APPLIED,
                "main consumption record does not confirm D3 hint application",
            )
        if ack_envelope.sequence is not None:
            assert d3_envelope.sequence is not None
            assert d7_envelope.sequence is not None
            if not (
                d3_envelope.sequence < d7_envelope.sequence < ack_envelope.sequence
            ):
                _fail(
                    RegionResourceRuntimeAckCode.SOURCE_SEQUENCE_MISMATCH,
                    "D3, D7, and assignment ACK envelope order is invalid",
                )

    @staticmethod
    def _validate_source_envelope_bindings(
        *,
        ack: Mapping[str, Any],
        d3_envelope: RuntimeEnvelopeEvidence,
        d7_envelope: RuntimeEnvelopeEvidence,
        context: _EvidenceContext,
    ) -> None:
        expected_plan_sequence = _positive_int(
            _required(ack, "source_plan_bus_sequence", "assignment_plan_ack"),
            "assignment_plan_ack.source_plan_bus_sequence",
            RegionResourceRuntimeAckCode.SOURCE_SEQUENCE_MISMATCH,
        )
        expected_guidance_sequence = _positive_int(
            _required(ack, "source_guidance_bus_sequence", "assignment_plan_ack"),
            "assignment_plan_ack.source_guidance_bus_sequence",
            RegionResourceRuntimeAckCode.SOURCE_SEQUENCE_MISMATCH,
        )
        if (
            d3_envelope.sequence != expected_plan_sequence
            or d7_envelope.sequence != expected_guidance_sequence
            or expected_plan_sequence >= expected_guidance_sequence
        ):
            _fail(
                RegionResourceRuntimeAckCode.SOURCE_SEQUENCE_MISMATCH,
                "runtime ACK source sequences do not match D3/D7 envelopes",
            )
        expected_plan_hash = _sha256_text(
            _required(ack, "source_plan_payload_sha256", "assignment_plan_ack"),
            "assignment_plan_ack.source_plan_payload_sha256",
        )
        expected_guidance_hash = _sha256_text(
            _required(
                ack,
                "source_guidance_payload_sha256",
                "assignment_plan_ack",
            ),
            "assignment_plan_ack.source_guidance_payload_sha256",
        )
        if expected_plan_hash != context.source_plan_payload_sha256:
            _fail(
                RegionResourceRuntimeAckCode.SOURCE_HASH_MISMATCH,
                "runtime ACK D3 source payload hash is invalid",
            )
        if expected_guidance_hash != context.source_guidance_payload_sha256:
            _fail(
                RegionResourceRuntimeAckCode.SOURCE_HASH_MISMATCH,
                "runtime ACK D7 source payload hash is invalid",
            )

    @staticmethod
    def _validate_adoption_kind(
        *,
        metadata: Mapping[str, Any],
        source_plan_envelope: RuntimeEnvelopeEvidence | None,
        current_plan_envelope: RuntimeEnvelopeEvidence,
        source_plan_id: str,
        source_plan_version: int,
        plan_id: str,
        plan_version: int,
        plan_created_at: float,
        consumed_at_s: float,
        acknowledged_at_s: float,
    ) -> RegionResourceRuntimeAdoptionKind:
        execution_changed = _strict_bool(
            _required(metadata, "execution_signature_changed", "d3_plan.metadata"),
            "d3_plan.metadata.execution_signature_changed",
        )
        plan_refresh_only = _strict_bool(
            _required(metadata, "plan_refresh_only", "d3_plan.metadata"),
            "d3_plan.metadata.plan_refresh_only",
        )
        evaluation_refresh_only = _strict_bool(
            _required(
                metadata,
                "evaluation_refresh_only",
                "d3_plan.metadata",
            ),
            "d3_plan.metadata.evaluation_refresh_only",
        )
        if _strict_bool(
            _required(metadata, "plan_published", "d3_plan.metadata"),
            "d3_plan.metadata.plan_published",
        ) is not True:
            _fail(
                RegionResourceRuntimeAckCode.PLAN_REFRESH_FLAGS_INVALID,
                "D3 runtime ACK source was not marked as a published plan",
            )

        same_identity = (
            plan_id == source_plan_id and plan_version == source_plan_version
        )
        if same_identity and execution_changed:
            _fail(
                RegionResourceRuntimeAckCode.PLAN_NOT_NEW,
                "D3 declared changed execution semantics without advancing plan identity",
            )
        if not same_identity and (
            plan_id == source_plan_id or plan_version <= source_plan_version
        ):
            _fail(
                RegionResourceRuntimeAckCode.PLAN_NOT_NEW,
                "changed execution semantics require a strictly newer plan generation",
            )

        current_payload = current_plan_envelope.payload
        current_timestamp = _finite_time(
            _required(current_payload, "timestamp", "d3_plan"),
            "d3_plan.timestamp",
        )
        if not _same_time(current_timestamp, current_plan_envelope.timestamp_s):
            _fail(
                RegionResourceRuntimeAckCode.TIMESTAMP_MISMATCH,
                "D3 plan payload and envelope timestamps differ",
            )
        if (
            metadata.get("current_plan_id") != plan_id
            or metadata.get("current_plan_version") != plan_version
            or not _same_time(
                _finite_time(
                    _required(metadata, "identity_created_at_s", "d3_plan.metadata"),
                    "d3_plan.metadata.identity_created_at_s",
                ),
                plan_created_at,
            )
        ):
            _fail(
                RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                "D3 plan identity metadata differs from the runtime ACK",
            )
        evaluated_at_s = _finite_time(
            _required(metadata, "last_evaluated_at_s", "d3_plan.metadata"),
            "d3_plan.metadata.last_evaluated_at_s",
        )
        if not _same_time(evaluated_at_s, current_timestamp):
            _fail(
                RegionResourceRuntimeAckCode.PLAN_REFRESH_TIMESTAMP_MISMATCH,
                "D3 last evaluation time differs from its publication time",
            )

        if same_identity:
            if (evaluation_refresh_only, plan_refresh_only) not in {
                (True, False),
                (False, True),
            }:
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_REFRESH_FLAGS_INVALID,
                    "same-generation adoption requires exactly one explicit refresh-only flag",
                )
            if source_plan_envelope is None:
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_REFRESH_SOURCE_MISSING,
                    "same-generation adoption requires the advisory source-plan envelope",
                )
            if not (
                _same_time(current_timestamp, consumed_at_s)
                and _same_time(acknowledged_at_s, consumed_at_s)
            ):
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_REFRESH_TIMESTAMP_MISMATCH,
                    "refresh publication, advisory consumption, and ACK times differ",
                )
            RegionResourceRuntimeAckParser._validate_refresh_source_plan(
                source_plan_envelope=source_plan_envelope,
                current_plan_envelope=current_plan_envelope,
                source_plan_id=source_plan_id,
                source_plan_version=source_plan_version,
                plan_created_at=plan_created_at,
            )
            return RegionResourceRuntimeAdoptionKind.EVALUATION_REFRESH_APPLIED

        if not execution_changed or evaluation_refresh_only or plan_refresh_only:
            _fail(
                RegionResourceRuntimeAckCode.PLAN_REFRESH_FLAGS_INVALID,
                "new execution-plan adoption requires changed execution semantics and no refresh-only flag",
            )
        if plan_created_at < consumed_at_s:
            _fail(
                RegionResourceRuntimeAckCode.PLAN_NOT_NEW,
                "new execution plan predates D4 advisory consumption",
            )
        return RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED

    @staticmethod
    def _validate_refresh_source_plan(
        *,
        source_plan_envelope: RuntimeEnvelopeEvidence,
        current_plan_envelope: RuntimeEnvelopeEvidence,
        source_plan_id: str,
        source_plan_version: int,
        plan_created_at: float,
    ) -> None:
        source = source_plan_envelope.payload
        current = current_plan_envelope.payload
        if (
            _text(_required(source, "plan_id", "source_d3_plan"), "source_d3_plan.plan_id")
            != source_plan_id
            or _nonnegative_int(
                _required(source, "plan_version", "source_d3_plan"),
                "source_d3_plan.plan_version",
            )
            != source_plan_version
        ):
            _fail(
                RegionResourceRuntimeAckCode.SOURCE_PLAN_MISMATCH,
                "advisory source-plan envelope identity differs from the advisory",
            )
        source_created_at = _finite_time(
            _required(source, "created_at", "source_d3_plan"),
            "source_d3_plan.created_at",
        )
        source_timestamp = _finite_time(
            _required(source, "timestamp", "source_d3_plan"),
            "source_d3_plan.timestamp",
        )
        if (
            not _same_time(source_created_at, plan_created_at)
            or not _same_time(source_timestamp, source_plan_envelope.timestamp_s)
        ):
            _fail(
                RegionResourceRuntimeAckCode.PLAN_REFRESH_TIMESTAMP_MISMATCH,
                "same-generation refresh changed plan creation or source publication time",
            )
        assert source_plan_envelope.sequence is not None
        assert current_plan_envelope.sequence is not None
        if source_plan_envelope.sequence >= current_plan_envelope.sequence:
            _fail(
                RegionResourceRuntimeAckCode.SOURCE_SEQUENCE_MISMATCH,
                "advisory source plan must precede its evaluation refresh",
            )
        if _execution_binding_signature(source, "source_d3_plan") != (
            _execution_binding_signature(current, "d3_plan")
        ):
            _fail(
                RegionResourceRuntimeAckCode.PLAN_REFRESH_BINDINGS_CHANGED,
                "same-generation refresh changed assignment or coalition bindings",
            )
        source_unassigned = _text_inventory(
            source,
            "unassigned_global_track_ids",
            "source_d3_plan",
        )
        current_unassigned = _text_inventory(
            current,
            "unassigned_global_track_ids",
            "d3_plan",
        )
        if source_unassigned != current_unassigned:
            _fail(
                RegionResourceRuntimeAckCode.PLAN_REFRESH_BINDINGS_CHANGED,
                "same-generation refresh changed the unassigned target inventory",
            )

    @staticmethod
    def _validate_d3_plan_payload(
        *,
        ack: Mapping[str, Any],
        d3_payload: Mapping[str, Any],
        d3_schema: str,
        d4_evidence: Mapping[str, Any],
        plan_id: str,
        plan_version: int,
        plan_created_at: float,
    ) -> None:
        if _required(ack, "plan_schema_version", "assignment_plan_ack") != d3_schema:
            _fail(
                RegionResourceRuntimeAckCode.SCHEMA_MISMATCH,
                "assignment ACK plan schema differs from the D3 envelope",
            )
        if (
            _text(_required(d3_payload, "plan_id", "d3_plan"), "d3_plan.plan_id")
            != plan_id
            or _nonnegative_int(
                _required(d3_payload, "plan_version", "d3_plan"),
                "d3_plan.plan_version",
            )
            != plan_version
            or not _same_time(
                _finite_time(
                    _required(d3_payload, "created_at", "d3_plan"),
                    "d3_plan.created_at",
                ),
                plan_created_at,
            )
        ):
            _fail(
                RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                "assignment ACK does not describe its bound D3 plan payload",
            )
        metadata = _required_mapping(d3_payload, "metadata", "d3_plan")
        fields_to_match = (
            "considered",
            "applied",
            "rejected",
            "fallback_reason",
            "advisory_id",
            "advisory_version",
            "source_plan_id",
            "source_plan_version",
        )
        for suffix in fields_to_match:
            if metadata.get(f"regional_hint_{suffix}") != d4_evidence.get(suffix):
                _fail(
                    RegionResourceRuntimeAckCode.D3_HINT_STATE_CONTRADICTION,
                    f"D3 plan metadata does not match ACK regional hint field: {suffix}",
                )
        if metadata.get("regional_hint_projected") is not True:
            _fail(
                RegionResourceRuntimeAckCode.D3_HINT_NOT_APPLIED,
                "D3 plan did not record a projected regional hint",
            )

    @staticmethod
    def _validate_authority(
        *,
        advisory: RegionResourceAdvisoryContract,
        ack: Mapping[str, Any],
        d3_payload: Mapping[str, Any],
        adoption_kind: RegionResourceRuntimeAdoptionKind,
        context: _EvidenceContext,
    ) -> None:
        source_authorities = {
            (
                region.source_version.owner_layer.value,
                region.source_version.owner_id,
                int(region.source_version.epoch),
                float(region.source_version.lease_expires_at_s),
            )
            for region in advisory.regions
        }
        if len(source_authorities) != 1:
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_SCOPE_MISMATCH,
                "one top-level plan ACK cannot prove multiple regional authorities",
            )
        owner_layer, owner_id, epoch, lease = next(iter(source_authorities))
        context.owner_layer = owner_layer
        context.owner_node_id = owner_id
        context.authority_epoch = epoch
        context.lease_expires_at_s = lease
        if owner_id is None:
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_OWNER_MISMATCH,
                "runtime advisory source authority has no owner",
            )
        ack_owner_layer = _text(
            _required(ack, "active_plan_owner", "assignment_plan_ack"),
            "assignment_plan_ack.active_plan_owner",
        ).lower()
        ack_owner_id = _text(
            _required(ack, "owner_node_id", "assignment_plan_ack"),
            "assignment_plan_ack.owner_node_id",
        )
        if ack_owner_layer != owner_layer or ack_owner_id != owner_id:
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_OWNER_MISMATCH,
                "acknowledged plan owner differs from D4 source authority",
            )
        assert context.acknowledged_at_s is not None
        if context.acknowledged_at_s >= lease:
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_LEASE_EXPIRED,
                "D4 source authority lease is expired at acknowledgement",
            )
        metadata = _required_mapping(d3_payload, "metadata", "d3_plan")
        if (
            _required(metadata, "active_plan_owner", "d3_plan.metadata")
            != owner_layer
            or _required(metadata, "owner_node_id", "d3_plan.metadata") != owner_id
        ):
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_SCOPE_MISMATCH,
                "D3 plan metadata does not carry the verified D4 owner",
            )

        ack_epoch_value = _required(ack, "authority_epoch", "assignment_plan_ack")
        ack_lease_value = _required(
            ack,
            "lease_expires_at_s",
            "assignment_plan_ack",
        )
        metadata_epoch_value = metadata.get("authority_epoch")
        metadata_lease_value = metadata.get("lease_expires_at_s")
        authority_values = (
            ack_epoch_value,
            ack_lease_value,
            metadata_epoch_value,
            metadata_lease_value,
        )
        if all(value is None for value in authority_values):
            if adoption_kind is not (
                RegionResourceRuntimeAdoptionKind.EVALUATION_REFRESH_APPLIED
            ):
                _fail(
                    RegionResourceRuntimeAckCode.AUTHORITY_SCOPE_MISMATCH,
                    "new execution plan lacks epoch and lease authority binding",
                )
            return
        if any(value is None for value in authority_values):
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_SCOPE_MISMATCH,
                "D3 plan and ACK contain a partial epoch/lease authority binding",
            )

        ack_epoch = _nonnegative_int(
            ack_epoch_value,
            "assignment_plan_ack.authority_epoch",
        )
        metadata_epoch = _nonnegative_int(
            metadata_epoch_value,
            "d3_plan.metadata.authority_epoch",
        )
        if ack_epoch != epoch or metadata_epoch != epoch:
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_EPOCH_MISMATCH,
                "acknowledged plan authority epoch differs from D4 source epoch",
            )
        ack_lease = _finite_time(
            ack_lease_value,
            "assignment_plan_ack.lease_expires_at_s",
        )
        metadata_lease = _finite_time(
            metadata_lease_value,
            "d3_plan.metadata.lease_expires_at_s",
        )
        if not _same_time(ack_lease, lease) or not _same_time(metadata_lease, lease):
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_LEASE_MISMATCH,
                "acknowledged plan lease differs from D4 source lease",
            )

    @staticmethod
    def _validate_binding_records(
        *,
        ack: Mapping[str, Any],
        d3_payload: Mapping[str, Any],
        d7_payload: Mapping[str, Any],
        plan_id: str,
        plan_version: int,
    ) -> None:
        assignments = _required_sequence(d3_payload, "assignments", "d3_plan")
        commands = _required_sequence(d7_payload, "commands", "d7_guidance")
        bindings = _required_sequence(ack, "binding_acks", "assignment_plan_ack")
        assignment_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
        command_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
        binding_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
        for index, raw in enumerate(assignments):
            item = _as_mapping(raw, f"d3_plan.assignments[{index}]")
            key = _binding_key(item, f"d3_plan.assignments[{index}]")
            if key in assignment_by_key:
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                    "D3 plan contains a duplicated assignment binding",
                )
            assignment_by_key[key] = item
        for index, raw in enumerate(commands):
            item = _as_mapping(raw, f"d7_guidance.commands[{index}]")
            if (
                _text(_required(item, "plan_id", "d7_command"), "d7_command.plan_id")
                != plan_id
                or _nonnegative_int(
                    _required(item, "plan_version", "d7_command"),
                    "d7_command.plan_version",
                )
                != plan_version
            ):
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                    "D7 command references another plan generation",
                )
            key = _binding_key(item, f"d7_guidance.commands[{index}]")
            if key in command_by_key:
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                    "D7 guidance contains a duplicated assignment binding",
                )
            command_by_key[key] = item
        held_count = 0
        for index, raw in enumerate(bindings):
            item = _as_mapping(raw, f"assignment_plan_ack.binding_acks[{index}]")
            key = _binding_key(item, f"assignment_plan_ack.binding_acks[{index}]")
            if key in binding_by_key:
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                    "runtime ACK contains a duplicated assignment binding",
                )
            if not _strict_bool(
                _required(item, "guidance_command_present", "binding_ack"),
                "binding_ack.guidance_command_present",
            ) or not _strict_bool(
                _required(item, "control_applied_to_world", "binding_ack"),
                "binding_ack.control_applied_to_world",
            ):
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_BINDING_INCOMPLETE,
                    "an assignment binding did not reach D7 and main control",
                )
            held = _strict_bool(
                _required(item, "held", "binding_ack"),
                "binding_ack.held",
            )
            held_count += int(held)
            binding_by_key[key] = item
        if not (set(assignment_by_key) == set(command_by_key) == set(binding_by_key)):
            _fail(
                RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                "D3 assignments, D7 commands, and runtime ACK bindings differ",
            )
        for key in assignment_by_key:
            assignment = assignment_by_key[key]
            command = command_by_key[key]
            binding = binding_by_key[key]
            if binding.get("guidance_mode") != command.get("mode") or binding.get(
                "guidance_gate_reason"
            ) != command.get("gate_reason"):
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                    "runtime ACK does not match its D7 command mode or gate",
                )
            for field_name in ("coalition_id", "coalition_version", "member_role"):
                if binding.get(field_name) != assignment.get(field_name):
                    _fail(
                        RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                        f"runtime ACK binding differs from D3 assignment: {field_name}",
                    )
            if bool(binding["held"]) != (str(command.get("mode", "")) == "hold"):
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                    "runtime ACK hold state differs from D7 command mode",
                )

        count = len(assignments)
        expected_counts = {
            "assignment_count": count,
            "binding_ack_count": count,
            "control_applied_binding_count": count,
            "held_binding_count": held_count,
        }
        for key, value in expected_counts.items():
            if _nonnegative_int(
                _required(ack, key, "assignment_plan_ack"),
                f"assignment_plan_ack.{key}",
            ) != value:
                _fail(
                    RegionResourceRuntimeAckCode.PLAN_BINDING_INCOMPLETE,
                    f"runtime ACK count is inconsistent: {key}",
                )
        if _strict_bool(
            _required(ack, "fully_bound_to_guidance", "assignment_plan_ack"),
            "assignment_plan_ack.fully_bound_to_guidance",
        ) is not True:
            _fail(
                RegionResourceRuntimeAckCode.PLAN_BINDING_INCOMPLETE,
                "runtime ACK does not fully bind the D3 plan to D7",
            )
        if "command_count" in d7_payload and _nonnegative_int(
            d7_payload["command_count"], "d7_guidance.command_count"
        ) != len(commands):
            _fail(
                RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                "D7 command_count does not match its command list",
            )


def _execution_binding_signature(
    payload: Mapping[str, Any],
    path: str,
) -> tuple[tuple[Any, ...], ...]:
    assignments = _required_sequence(payload, "assignments", path)
    reported_count = _nonnegative_int(
        _required(payload, "assignment_count", path),
        f"{path}.assignment_count",
    )
    if reported_count != len(assignments):
        _fail(
            RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
            f"{path} assignment_count does not match its assignment list",
        )
    records: list[tuple[Any, ...]] = []
    keys: set[tuple[str, str]] = set()
    for index, raw in enumerate(assignments):
        item_path = f"{path}.assignments[{index}]"
        item = _as_mapping(raw, item_path)
        resource_id, global_track_id = _binding_key(item, item_path)
        key = (resource_id, global_track_id)
        if key in keys:
            _fail(
                RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
                f"{path} contains a duplicate executable binding",
            )
        keys.add(key)
        records.append(
            (
                resource_id,
                global_track_id,
                _optional_text_value(item.get("coalition_id"), f"{item_path}.coalition_id"),
                _optional_nonnegative_int_value(
                    item.get("coalition_version"),
                    f"{item_path}.coalition_version",
                ),
                _text(
                    _required(item, "member_role", item_path),
                    f"{item_path}.member_role",
                ),
                _optional_text_value(
                    item.get("owner_node_id"),
                    f"{item_path}.owner_node_id",
                ),
                _optional_text_value(
                    item.get("regional_owner_layer"),
                    f"{item_path}.regional_owner_layer",
                ),
                _optional_text_value(
                    item.get("regional_region_id"),
                    f"{item_path}.regional_region_id",
                ),
                _optional_nonnegative_int_value(
                    item.get("regional_epoch"),
                    f"{item_path}.regional_epoch",
                ),
                _optional_text_value(
                    item.get("regional_commit_mode"),
                    f"{item_path}.regional_commit_mode",
                ),
            )
        )
    return tuple(sorted(records, key=lambda item: (item[0], item[1])))


def _text_inventory(
    payload: Mapping[str, Any],
    key: str,
    path: str,
) -> tuple[str, ...]:
    values = tuple(
        _text(item, f"{path}.{key}")
        for item in _required_sequence(payload, key, path)
    )
    if len(values) != len(set(values)):
        _fail(
            RegionResourceRuntimeAckCode.PLAN_BINDING_MISMATCH,
            f"{path}.{key} contains duplicates",
        )
    return tuple(sorted(values))


def canonical_runtime_payload_sha256(value: Any) -> str:
    """Reproduce main's canonical payload hash without importing main."""

    try:
        encoded = json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _fail(
            RegionResourceRuntimeAckCode.SOURCE_HASH_MISMATCH,
            f"source payload is not canonically hashable: {type(error).__name__}",
        )
    return sha256(encoded).hexdigest()


def _validate_consumption_state(consumption: Mapping[str, Any]) -> None:
    consumable = _strict_bool(
        _required(consumption, "consumable", "consumption"),
        "consumption.consumable",
    )
    rejection_reasons = _required_sequence(
        consumption,
        "rejection_reasons",
        "consumption",
    )
    bridge_reason = _required(consumption, "bridge_rejection_reason", "consumption")
    d3_applied = _strict_bool(
        _required(consumption, "d3_hint_applied", "consumption"),
        "consumption.d3_hint_applied",
    )
    if not consumable:
        _fail(
            RegionResourceRuntimeAckCode.CONSUMPTION_NOT_CONSUMABLE,
            "main consumption gate rejected the D4 advisory",
        )
    if rejection_reasons or bridge_reason is not None:
        _fail(
            RegionResourceRuntimeAckCode.CONSUMPTION_STATE_CONTRADICTION,
            "consumable D4 evidence contains a rejection reason",
        )
    if not d3_applied:
        _fail(
            RegionResourceRuntimeAckCode.D3_HINT_NOT_APPLIED,
            "main consumption evidence did not apply the D4 hint in D3",
        )


def _validate_consumption_advisory_binding(
    advisory: RegionResourceAdvisoryContract,
    consumption: Mapping[str, Any],
    consumed_at_s: float,
) -> None:
    if consumed_at_s < advisory.valid_from_s:
        _fail(
            RegionResourceRuntimeAckCode.ADVISORY_NOT_YET_VALID,
            "D4 advisory was consumed before its validity window",
        )
    if consumed_at_s >= advisory.valid_until_s:
        _fail(
            RegionResourceRuntimeAckCode.ADVISORY_EXPIRED,
            "D4 advisory was consumed at or after expiry",
        )
    expected = {
        "current_snapshot_id": advisory.snapshot_id,
        "current_snapshot_version": advisory.snapshot_version,
        "current_authority_digest": advisory.authority_digest,
    }
    if any(consumption.get(key) != value for key, value in expected.items()):
        _fail(
            RegionResourceRuntimeAckCode.SOURCE_PLAN_MISMATCH,
            "main consumption did not revalidate the advisory source snapshot",
        )
    for region in advisory.regions:
        source = region.source_version
        if (
            source.snapshot_id != advisory.snapshot_id
            or source.snapshot_version != advisory.snapshot_version
            or source.authority_digest != advisory.authority_digest
        ):
            _fail(
                RegionResourceRuntimeAckCode.SOURCE_PLAN_MISMATCH,
                "regional authority proof differs from the advisory snapshot",
            )
        if source.lease_expires_at_s <= consumed_at_s:
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_LEASE_EXPIRED,
                "D4 source authority lease expired before consumption",
            )
        if not source.owner_active or source.fault_fenced or not source.coalition_ack_complete:
            _fail(
                RegionResourceRuntimeAckCode.AUTHORITY_SCOPE_MISMATCH,
                "D4 source authority is inactive, fenced, or lacks coalition ACK",
            )


def _parse_advisory(value: Any) -> RegionResourceAdvisoryContract:
    if isinstance(value, RegionResourceAdvisoryContract):
        return value
    if hasattr(value, "advisory_contract"):
        value = getattr(value, "advisory_contract")
        if value is None:
            _fail(
                RegionResourceRuntimeAckCode.ADVISORY_MISSING,
                "D4 advisory result has no advisory contract",
            )
        return _parse_advisory(value)
    if _looks_like_envelope(value):
        envelope = _parse_envelope(
            value,
            expected_topic="modules.d4.region_resource_advice",
            expected_sources=("D4",),
            expected_schema=REGION_RESOURCE_ADVICE_ENVELOPE_SCHEMA,
            explicit_schema=None,
            raw_timestamp_keys=("timestamp",),
            require_sequence=False,
        )
        return _parse_advisory(envelope.payload)
    mapping = _as_mapping(value, "advisory")
    if "advisory_contract" in mapping:
        nested = mapping["advisory_contract"]
        if nested is None:
            _fail(
                RegionResourceRuntimeAckCode.ADVISORY_MISSING,
                "D4 advisory result mapping has no advisory contract",
            )
        return _parse_advisory(nested)
    try:
        return RegionResourceAdvisoryContract.from_dict(mapping)
    except (KeyError, TypeError, ValueError) as error:
        _fail(
            RegionResourceRuntimeAckCode.ADVISORY_INVALID,
            f"D4 advisory contract is invalid: {type(error).__name__}",
        )


def _parse_envelope(
    value: Any,
    *,
    expected_topic: str,
    expected_sources: tuple[str, ...],
    expected_schema: str | None,
    explicit_schema: str | None,
    raw_timestamp_keys: tuple[str, ...],
    require_sequence: bool,
) -> RuntimeEnvelopeEvidence:
    full = _looks_like_envelope(value)
    if full:
        if isinstance(value, Mapping):
            sequence_value = value.get("sequence")
            topic = value.get("topic")
            source = value.get("source")
            timestamp_value = value.get("timestamp")
            schema_value = value.get("schema_version")
            payload_value = value.get("payload")
        else:
            sequence_value = getattr(value, "sequence", None)
            topic = getattr(value, "topic", None)
            source = getattr(value, "source", None)
            timestamp_value = getattr(value, "timestamp", None)
            schema_value = getattr(value, "schema_version", None)
            payload_value = getattr(value, "payload", None)
    else:
        payload_value = value
        sequence_value = None
        topic = expected_topic
        source = expected_sources[0]
        schema_value = explicit_schema
        payload_mapping = _as_mapping(payload_value, expected_topic)
        timestamp_value = None
        for key in raw_timestamp_keys:
            if key in payload_mapping:
                timestamp_value = payload_mapping[key]
                break
    payload = _as_mapping(payload_value, f"{expected_topic}.payload")
    topic_text = _text(topic, f"{expected_topic}.topic")
    source_text = _text(source, f"{expected_topic}.source")
    schema_text = _text(schema_value, f"{expected_topic}.schema_version")
    timestamp = _finite_time(timestamp_value, f"{expected_topic}.timestamp")
    if topic_text != expected_topic or source_text not in expected_sources:
        _fail(
            RegionResourceRuntimeAckCode.SOURCE_ENVELOPE_INVALID,
            f"unexpected runtime envelope source/topic for {expected_topic}",
        )
    if explicit_schema is not None and schema_text != explicit_schema:
        _fail(
            RegionResourceRuntimeAckCode.SCHEMA_MISMATCH,
            f"explicit and envelope schemas differ for {expected_topic}",
        )
    if expected_schema is not None and schema_text != expected_schema:
        _fail(
            RegionResourceRuntimeAckCode.SCHEMA_MISMATCH,
            f"unsupported envelope schema for {expected_topic}: {schema_text}",
        )
    sequence: int | None = None
    if sequence_value is not None:
        sequence = _positive_int(
            sequence_value,
            f"{expected_topic}.sequence",
            RegionResourceRuntimeAckCode.SOURCE_SEQUENCE_MISMATCH,
        )
    if require_sequence and sequence is None:
        _fail(
            RegionResourceRuntimeAckCode.SOURCE_SEQUENCE_MISMATCH,
            f"source envelope sequence is missing for {expected_topic}",
        )
    return RuntimeEnvelopeEvidence(
        sequence=sequence,
        topic=topic_text,
        source=source_text,
        timestamp_s=timestamp,
        schema_version=schema_text,
        payload=payload,
    )


def _looks_like_envelope(value: Any) -> bool:
    if isinstance(value, Mapping):
        return "payload" in value and "schema_version" in value
    return all(
        hasattr(value, name)
        for name in ("topic", "source", "timestamp", "schema_version", "payload")
    )


def _available_evidence(context: _EvidenceContext) -> RegionResourceRuntimeAckEvidence:
    assert context.adoption_kind is not None
    return RegionResourceRuntimeAckEvidence(
        code=RegionResourceRuntimeAckCode.APPLIED.value,
        reason=(
            "D4 advisory adoption is verified as "
            f"{context.adoption_kind}; main consumption, D3/D7 binding, source "
            "sequence, and payload hashes are consistent"
        ),
        runtime_advisory_applied_ack_available=True,
        rejection_reasons=(),
        **asdict(context),
    )


def _rejected_evidence(
    context: _EvidenceContext,
    error: _ValidationFailure,
) -> RegionResourceRuntimeAckEvidence:
    values = asdict(context)
    values["adoption_kind"] = None
    return RegionResourceRuntimeAckEvidence(
        code=error.code.value,
        reason=error.reason,
        runtime_advisory_applied_ack_available=False,
        rejection_reasons=(error.code.value,),
        **values,
    )


def _fail(code: RegionResourceRuntimeAckCode, reason: str) -> None:
    raise _ValidationFailure(code, reason)


def _required(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        _fail(
            RegionResourceRuntimeAckCode.MISSING_FIELD,
            f"required runtime evidence field is missing: {path}.{key}",
        )
    return mapping[key]


def _required_mapping(
    mapping: Mapping[str, Any], key: str, path: str
) -> Mapping[str, Any]:
    return _as_mapping(_required(mapping, key, path), f"{path}.{key}")


def _required_sequence(
    mapping: Mapping[str, Any], key: str, path: str
) -> Sequence[Any]:
    value = _required(mapping, key, path)
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail(
            RegionResourceRuntimeAckCode.INVALID_FIELD_TYPE,
            f"runtime evidence field must be a sequence: {path}.{key}",
        )
    return value


def _require_schema(mapping: Mapping[str, Any], expected: str, *, path: str) -> None:
    actual = _required(mapping, "schema", path.rsplit(".", 1)[0])
    if actual != expected:
        _fail(
            RegionResourceRuntimeAckCode.SCHEMA_MISMATCH,
            f"unsupported schema at {path}: {actual}",
        )


def _as_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return converted
    _fail(
        RegionResourceRuntimeAckCode.INVALID_FIELD_TYPE,
        f"runtime evidence value must be a mapping: {path}",
    )


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(
            RegionResourceRuntimeAckCode.INVALID_FIELD_TYPE,
            f"runtime evidence field must be non-empty text: {path}",
        )
    return value.strip()


def _optional_text_value(value: Any, path: str) -> str | None:
    return None if value is None else _text(value, path)


def _optional_nonnegative_int_value(value: Any, path: str) -> int | None:
    return None if value is None else _nonnegative_int(value, path)


def _strict_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(
            RegionResourceRuntimeAckCode.INVALID_FIELD_TYPE,
            f"runtime evidence field must be boolean: {path}",
        )
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(
            RegionResourceRuntimeAckCode.INVALID_FIELD_TYPE,
            f"runtime evidence field must be a non-negative integer: {path}",
        )
    return int(value)


def _positive_int(
    value: Any,
    path: str,
    code: RegionResourceRuntimeAckCode,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(code, f"runtime evidence field must be a positive integer: {path}")
    return int(value)


def _finite_time(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(
            RegionResourceRuntimeAckCode.INVALID_FIELD_TYPE,
            f"runtime timestamp must be numeric: {path}",
        )
    result = float(value)
    if not isfinite(result) or result < 0.0:
        _fail(
            RegionResourceRuntimeAckCode.NONFINITE_TIMESTAMP,
            f"runtime timestamp must be finite and non-negative: {path}",
        )
    return result


def _sha256_text(value: Any, path: str) -> str:
    text = _text(value, path).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        _fail(
            RegionResourceRuntimeAckCode.SOURCE_HASH_MISMATCH,
            f"runtime payload SHA256 is invalid: {path}",
        )
    return text


def _binding_key(mapping: Mapping[str, Any], path: str) -> tuple[str, str]:
    return (
        _text(_required(mapping, "resource_id", path), f"{path}.resource_id"),
        _text(
            _required(mapping, "global_track_id", path),
            f"{path}.global_track_id",
        ),
    )


def _same_time(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= 1.0e-9


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return _jsonable(value.item())
        except (TypeError, ValueError):
            pass
    return value
