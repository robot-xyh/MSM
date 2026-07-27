"""Fail-closed A2 regional recommendation adoption evidence.

This module bridges deterministic regional projection and the immutable A2
evidence bundle.  It deliberately does not import main, D3, D6, D7, AirSim, or
the scalable simulation runtime.  The caller must provide transport receipts
and downstream references produced by those owners.

``prepare`` proves only that a candidate recommendation survived the current
D4 authority and resource fences.  A projected no-op may reach that stage as a
link probe, but it is not an adopted model action.  ``assemble`` first requires
a recomputed, D3-consumable intervention and then proves that it was bound to a
strictly newer D3 plan, acknowledged by the active secondary/peer owner,
atomically committed when a coalition is required, and observed in a physical
execution window.  Neither step grants authority or claims A2 performance
benefit; reward and outcome comparison remain D6-only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from hashlib import sha256
import json
from math import ceil, isfinite
import re
from typing import Any, Mapping, Sequence

from .coalition_safety import CoalitionCommitState, CoalitionMemberAck
from .communication_causal_evidence import (
    CausalCommunicationEvidenceGate,
    CausalMessageKind,
    CommunicationDeliveryReceipt,
    CommunicationEvidenceExpectation,
    CommunicationEvidenceValidation,
    canonical_payload_digest,
    expected_delivery_receipt_id,
)
from .models import C2Health
from .region_resource import (
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceAdvisoryContract,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
)
from .region_resource_runtime_ack import (
    RegionResourceRuntimeAckCode,
    RegionResourceRuntimeAckEvidence,
    RegionResourceRuntimeAdoptionKind,
    canonical_runtime_payload_sha256,
)
from .regional_failover import (
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverDecision,
)


REGION_RESOURCE_SAFE_ADOPTION_CONTEXT_SCHEMA = (
    "d4-region-resource-safe-adoption-context-v1"
)
REGION_RESOURCE_APPLIED_RECOMMENDATION_SCHEMA = (
    "d4-region-resource-applied-recommendation-v1"
)
REGION_RESOURCE_PROJECTED_INTERVENTION_SCHEMA = (
    "d4-region-resource-projected-intervention-v1"
)
REGION_RESOURCE_SAFE_ADOPTION_PREPARATION_SCHEMA = (
    "d4-region-resource-safe-adoption-preparation-v1"
)
REGION_RESOURCE_D3_PLAN_REFERENCE_SCHEMA = (
    "d4-region-resource-d3-successor-plan-reference-v1"
)
REGION_RESOURCE_COALITION_REQUIREMENT_SCHEMA = (
    "d4-region-resource-coalition-requirement-v1"
)
REGION_RESOURCE_OWNER_PLAN_ACK_SCHEMA = (
    "d4-region-resource-owner-plan-ack-v1"
)
REGION_RESOURCE_OWNER_ACK_DELIVERY_SCHEMA = (
    "d4-region-resource-owner-ack-delivery-v1"
)
REGION_RESOURCE_COALITION_ACK_DELIVERY_SCHEMA = (
    "d4-region-resource-coalition-ack-delivery-v1"
)
REGION_RESOURCE_COALITION_COMMIT_EVIDENCE_SCHEMA = (
    "d4-region-resource-coalition-commit-evidence-v1"
)
REGION_RESOURCE_PHYSICAL_WINDOW_SCHEMA = (
    "d4-region-resource-physical-window-availability-v1"
)
REGION_RESOURCE_SAFE_ADOPTION_EVIDENCE_SCHEMA = (
    "d4-region-resource-safe-adoption-evidence-v1"
)
REGION_RESOURCE_ACK_DELIVERY_VALIDATION_SCHEMA = (
    "d4-region-resource-ack-delivery-validation-v1"
)
REGION_RESOURCE_OWNER_ACK_TOPIC = "d4.regional_plan_owner_ack.v1"
REGION_RESOURCE_COALITION_ACK_TOPIC = "d4.coalition_member_ack.v1"
REGION_RESOURCE_SAFE_ADOPTION_MINIMUM_CONFIDENCE = 0.60

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TIME_TOLERANCE_S = 1.0e-9
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "airsim_id",
        "ground_truth",
        "ground_truth_id",
        "intercept_success",
        "object_id",
        "object_name",
        "offline_outcome",
        "offline_outcomes",
        "offline_reward",
        "offline_rewards",
        "offline_truth_labels",
        "outcome",
        "outcome_value",
        "reward",
        "reward_value",
        "truth",
        "truth_id",
        "truth_ids",
        "truth_position",
        "truth_velocity",
    }
)


class RegionResourceSafeAdoptionStage(str, Enum):
    """Highest verified stage in one fail-closed adoption attempt."""

    CANDIDATE_REJECTED = "candidate_rejected"
    APPLIED_RECOMMENDATION_PREPARED = "applied_recommendation_prepared"
    AWAITING_D3_PLAN = "awaiting_d3_plan"
    AWAITING_RUNTIME_ACK = "awaiting_runtime_ack"
    AWAITING_OWNER_ACK = "awaiting_owner_ack"
    AWAITING_COALITION_COMMIT = "awaiting_coalition_commit"
    AWAITING_PHYSICAL_WINDOW = "awaiting_physical_window"
    SAFE_ADOPTION_REJECTED = "safe_adoption_rejected"
    PHYSICAL_WINDOW_AVAILABLE = "physical_window_available"


class RegionResourceSafeAdoptionError(ValueError):
    """Stable validation failure used internally by the assembler."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class RegionResourceSafeAdoptionContext:
    """Truth-free authority facts frozen at recommendation consumption."""

    consumption_timestamp_s: float
    center_health: C2Health | str
    runtime_node_id: str
    advisory_version: int
    partition_generation: int
    secondary_available_region_ids: tuple[str, ...] = ()
    partitioned_region_ids: tuple[str, ...] = ()
    active_degradation_region_ids: tuple[str, ...] = ()
    active_degradation_evidence_sha256: str | None = None
    schema: str = REGION_RESOURCE_SAFE_ADOPTION_CONTEXT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_SAFE_ADOPTION_CONTEXT_SCHEMA:
            raise ValueError("unsupported safe-adoption context schema")
        object.__setattr__(
            self,
            "center_health",
            self.center_health
            if isinstance(self.center_health, C2Health)
            else C2Health(str(self.center_health)),
        )
        object.__setattr__(
            self,
            "runtime_node_id",
            _required_text(self.runtime_node_id, "runtime_node_id"),
        )
        object.__setattr__(
            self,
            "consumption_timestamp_s",
            _finite_nonnegative(
                self.consumption_timestamp_s, "consumption_timestamp_s"
            ),
        )
        object.__setattr__(
            self,
            "advisory_version",
            _positive_int(self.advisory_version, "advisory_version"),
        )
        object.__setattr__(
            self,
            "partition_generation",
            _nonnegative_int(
                self.partition_generation, "partition_generation"
            ),
        )
        for name in (
            "secondary_available_region_ids",
            "partitioned_region_ids",
            "active_degradation_region_ids",
        ):
            object.__setattr__(
                self,
                name,
                _unique_text(getattr(self, name), name),
            )
        if self.active_degradation_region_ids:
            object.__setattr__(
                self,
                "active_degradation_evidence_sha256",
                _sha256_text(
                    self.active_degradation_evidence_sha256,
                    "active_degradation_evidence_sha256",
                ),
            )
        elif self.active_degradation_evidence_sha256 is not None:
            object.__setattr__(
                self,
                "active_degradation_evidence_sha256",
                _sha256_text(
                    self.active_degradation_evidence_sha256,
                    "active_degradation_evidence_sha256",
                ),
            )

    @classmethod
    def from_value(cls, value: Any) -> "RegionResourceSafeAdoptionContext":
        if isinstance(value, cls):
            return value
        return _strict_dataclass_from_mapping(cls, value, "context")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceCoalitionRequirement:
    """One D3-declared coalition that must atomically commit."""

    global_track_id: str
    coalition_id: str
    coalition_version: int
    required_member_ids: tuple[str, ...]
    schema: str = REGION_RESOURCE_COALITION_REQUIREMENT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_COALITION_REQUIREMENT_SCHEMA:
            raise ValueError("unsupported coalition requirement schema")
        for name in ("global_track_id", "coalition_id"):
            object.__setattr__(
                self, name, _required_text(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "coalition_version",
            _positive_int(self.coalition_version, "coalition_version"),
        )
        members = _unique_text(self.required_member_ids, "required_member_ids")
        if not members:
            raise ValueError("coalition requirement needs at least one member")
        object.__setattr__(self, "required_member_ids", members)

    @classmethod
    def from_value(cls, value: Any) -> "RegionResourceCoalitionRequirement":
        if isinstance(value, cls):
            return value
        return _strict_dataclass_from_mapping(
            cls, value, "coalition_requirement"
        )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceD3PlanReference:
    """Minimal immutable reference to the strict D3 successor plan."""

    plan_id: str
    plan_version: int
    previous_plan_id: str
    previous_plan_version: int
    owner_node_id: str
    owner_layer: RegionalAuthorityLayer | str
    epoch: int
    created_at_s: float
    valid_until_s: float
    source_advisory_id: str
    source_advisory_version: int
    source_advisory_payload_sha256: str
    plan_payload_sha256: str
    plan_bus_sequence: int
    accepted_by_main_runtime: bool
    regional_hint_applied: bool
    stale_version_rejected: bool
    coalition_requirements: tuple[RegionResourceCoalitionRequirement, ...] = ()
    schema: str = REGION_RESOURCE_D3_PLAN_REFERENCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_D3_PLAN_REFERENCE_SCHEMA:
            raise ValueError("unsupported D3 plan reference schema")
        for name in (
            "plan_id",
            "previous_plan_id",
            "owner_node_id",
            "source_advisory_id",
        ):
            object.__setattr__(
                self, name, _required_text(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "owner_layer",
            self.owner_layer
            if isinstance(self.owner_layer, RegionalAuthorityLayer)
            else RegionalAuthorityLayer(str(self.owner_layer)),
        )
        for name in ("plan_version", "previous_plan_version", "epoch"):
            object.__setattr__(
                self, name, _nonnegative_int(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "source_advisory_version",
            _positive_int(
                self.source_advisory_version,
                "source_advisory_version",
            ),
        )
        object.__setattr__(
            self,
            "plan_bus_sequence",
            _positive_int(self.plan_bus_sequence, "plan_bus_sequence"),
        )
        created = _finite_nonnegative(self.created_at_s, "created_at_s")
        valid_until = _finite_nonnegative(
            self.valid_until_s, "valid_until_s"
        )
        if valid_until <= created:
            raise ValueError("D3 successor plan validity must follow creation")
        object.__setattr__(self, "created_at_s", created)
        object.__setattr__(self, "valid_until_s", valid_until)
        for name in (
            "source_advisory_payload_sha256",
            "plan_payload_sha256",
        ):
            object.__setattr__(
                self, name, _sha256_text(getattr(self, name), name)
            )
        for name in (
            "accepted_by_main_runtime",
            "regional_hint_applied",
            "stale_version_rejected",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")
        requirements = tuple(
            RegionResourceCoalitionRequirement.from_value(item)
            for item in self.coalition_requirements
        )
        keys = tuple(
            (item.global_track_id, item.coalition_id, item.coalition_version)
            for item in requirements
        )
        if len(set(keys)) != len(keys):
            raise ValueError("coalition requirements must be unique")
        object.__setattr__(
            self,
            "coalition_requirements",
            tuple(sorted(requirements, key=_coalition_requirement_key)),
        )

    @classmethod
    def from_value(cls, value: Any) -> "RegionResourceD3PlanReference":
        if isinstance(value, cls):
            return value
        mapping = _strict_mapping(value, "d3_plan_reference")
        _require_exact_keys(cls, mapping, "d3_plan_reference")
        payload = dict(mapping)
        payload["coalition_requirements"] = tuple(
            RegionResourceCoalitionRequirement.from_value(item)
            for item in _sequence(
                payload.get("coalition_requirements", ()),
                "coalition_requirements",
            )
        )
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceOwnerPlanAck:
    """Owner-generated ACK payload for one projected regional recommendation."""

    message_id: str
    owner_node_id: str
    owner_layer: RegionalAuthorityLayer | str
    region_ids: tuple[str, ...]
    advisory_id: str
    advisory_version: int
    advisory_payload_sha256: str
    source_plan_id: str
    source_plan_version: int
    applied_plan_id: str
    applied_plan_version: int
    applied_plan_payload_sha256: str
    applied_plan_bus_sequence: int
    runtime_assignment_ack_payload_sha256: str
    runtime_assignment_ack_bus_sequence: int
    epoch: int
    lease_expires_at_s: float
    partition_generation: int
    acknowledged_at_s: float
    accepted: bool
    schema: str = REGION_RESOURCE_OWNER_PLAN_ACK_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_OWNER_PLAN_ACK_SCHEMA:
            raise ValueError("unsupported owner ACK schema")
        for name in (
            "message_id",
            "owner_node_id",
            "advisory_id",
            "source_plan_id",
            "applied_plan_id",
        ):
            object.__setattr__(
                self, name, _required_text(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "owner_layer",
            self.owner_layer
            if isinstance(self.owner_layer, RegionalAuthorityLayer)
            else RegionalAuthorityLayer(str(self.owner_layer)),
        )
        regions = _unique_text(self.region_ids, "region_ids")
        if not regions:
            raise ValueError("owner ACK must cover at least one region")
        object.__setattr__(self, "region_ids", regions)
        object.__setattr__(
            self,
            "advisory_version",
            _positive_int(self.advisory_version, "advisory_version"),
        )
        object.__setattr__(
            self,
            "advisory_payload_sha256",
            _sha256_text(
                self.advisory_payload_sha256,
                "advisory_payload_sha256",
            ),
        )
        object.__setattr__(
            self,
            "applied_plan_payload_sha256",
            _sha256_text(
                self.applied_plan_payload_sha256,
                "applied_plan_payload_sha256",
            ),
        )
        object.__setattr__(
            self,
            "applied_plan_bus_sequence",
            _positive_int(
                self.applied_plan_bus_sequence,
                "applied_plan_bus_sequence",
            ),
        )
        object.__setattr__(
            self,
            "runtime_assignment_ack_payload_sha256",
            _sha256_text(
                self.runtime_assignment_ack_payload_sha256,
                "runtime_assignment_ack_payload_sha256",
            ),
        )
        object.__setattr__(
            self,
            "runtime_assignment_ack_bus_sequence",
            _positive_int(
                self.runtime_assignment_ack_bus_sequence,
                "runtime_assignment_ack_bus_sequence",
            ),
        )
        for name in (
            "source_plan_version",
            "applied_plan_version",
            "epoch",
            "partition_generation",
        ):
            object.__setattr__(
                self, name, _nonnegative_int(getattr(self, name), name)
            )
        acknowledged = _finite_nonnegative(
            self.acknowledged_at_s, "acknowledged_at_s"
        )
        lease = _finite_nonnegative(
            self.lease_expires_at_s, "lease_expires_at_s"
        )
        if acknowledged >= lease:
            raise ValueError("owner ACK must precede authority lease expiry")
        object.__setattr__(self, "acknowledged_at_s", acknowledged)
        object.__setattr__(self, "lease_expires_at_s", lease)
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be a bool")

    @classmethod
    def from_value(cls, value: Any) -> "RegionResourceOwnerPlanAck":
        if isinstance(value, cls):
            return value
        return _strict_dataclass_from_mapping(cls, value, "owner_ack")

    @classmethod
    def from_transport_payload(
        cls,
        value: Any,
    ) -> "RegionResourceOwnerPlanAck":
        """Parse the exact payload carried on the versioned owner-ACK topic."""

        mapping = _strict_mapping(value, "owner_ack_transport_payload")
        _assert_truth_and_outcome_free(mapping)
        _require_exact_named_keys(
            mapping,
            {
                "schema",
                "message_id",
                "message_kind",
                "authority_id",
                "plan_version",
                "epoch",
                "lease_expires_at_s",
                "partition_generation",
                "owner_layer",
                "region_ids",
                "advisory_id",
                "advisory_version",
                "advisory_payload_sha256",
                "source_plan_id",
                "source_plan_version",
                "applied_plan_id",
                "applied_plan_payload_sha256",
                "applied_plan_bus_sequence",
                "runtime_assignment_ack_payload_sha256",
                "runtime_assignment_ack_bus_sequence",
                "acknowledged_at_s",
                "accepted",
            },
            "owner_ack_transport_payload",
        )
        if (
            mapping["message_kind"]
            != CausalMessageKind.REGIONAL_PLAN_OWNER_ACK.value
        ):
            raise ValueError("owner ACK transport message_kind is invalid")
        ack = cls(
            schema=mapping["schema"],
            message_id=mapping["message_id"],
            owner_node_id=mapping["authority_id"],
            owner_layer=mapping["owner_layer"],
            region_ids=tuple(
                _sequence(mapping["region_ids"], "region_ids")
            ),
            advisory_id=mapping["advisory_id"],
            advisory_version=mapping["advisory_version"],
            advisory_payload_sha256=mapping["advisory_payload_sha256"],
            source_plan_id=mapping["source_plan_id"],
            source_plan_version=mapping["source_plan_version"],
            applied_plan_id=mapping["applied_plan_id"],
            applied_plan_version=mapping["plan_version"],
            applied_plan_payload_sha256=(
                mapping["applied_plan_payload_sha256"]
            ),
            applied_plan_bus_sequence=mapping["applied_plan_bus_sequence"],
            runtime_assignment_ack_payload_sha256=(
                mapping["runtime_assignment_ack_payload_sha256"]
            ),
            runtime_assignment_ack_bus_sequence=(
                mapping["runtime_assignment_ack_bus_sequence"]
            ),
            epoch=mapping["epoch"],
            lease_expires_at_s=mapping["lease_expires_at_s"],
            partition_generation=mapping["partition_generation"],
            acknowledged_at_s=mapping["acknowledged_at_s"],
            accepted=mapping["accepted"],
        )
        if ack.to_transport_payload() != _jsonable(mapping):
            raise ValueError("owner ACK transport aliases are inconsistent")
        return ack

    def to_transport_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "message_id": self.message_id,
            "message_kind": CausalMessageKind.REGIONAL_PLAN_OWNER_ACK.value,
            "authority_id": self.owner_node_id,
            "plan_version": self.applied_plan_version,
            "epoch": self.epoch,
            "lease_expires_at_s": self.lease_expires_at_s,
            "partition_generation": self.partition_generation,
            "owner_layer": self.owner_layer.value,
            "region_ids": list(self.region_ids),
            "advisory_id": self.advisory_id,
            "advisory_version": self.advisory_version,
            "advisory_payload_sha256": self.advisory_payload_sha256,
            "source_plan_id": self.source_plan_id,
            "source_plan_version": self.source_plan_version,
            "applied_plan_id": self.applied_plan_id,
            "applied_plan_payload_sha256": (
                self.applied_plan_payload_sha256
            ),
            "applied_plan_bus_sequence": self.applied_plan_bus_sequence,
            "runtime_assignment_ack_payload_sha256": (
                self.runtime_assignment_ack_payload_sha256
            ),
            "runtime_assignment_ack_bus_sequence": (
                self.runtime_assignment_ack_bus_sequence
            ),
            "acknowledged_at_s": self.acknowledged_at_s,
            "accepted": self.accepted,
        }

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceOwnerAckDelivery:
    ack: RegionResourceOwnerPlanAck
    receipt: CommunicationDeliveryReceipt
    schema: str = REGION_RESOURCE_OWNER_ACK_DELIVERY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_OWNER_ACK_DELIVERY_SCHEMA:
            raise ValueError("unsupported owner ACK delivery schema")
        object.__setattr__(
            self, "ack", RegionResourceOwnerPlanAck.from_value(self.ack)
        )
        object.__setattr__(
            self,
            "receipt",
            CommunicationDeliveryReceipt.from_value(self.receipt),
        )

    @classmethod
    def from_value(cls, value: Any) -> "RegionResourceOwnerAckDelivery":
        if isinstance(value, cls):
            return value
        mapping = _strict_mapping(value, "owner_ack_delivery")
        _require_exact_keys(cls, mapping, "owner_ack_delivery")
        return cls(
            ack=RegionResourceOwnerPlanAck.from_value(mapping["ack"]),
            receipt=CommunicationDeliveryReceipt.from_value(
                mapping["receipt"]
            ),
            schema=mapping.get(
                "schema", REGION_RESOURCE_OWNER_ACK_DELIVERY_SCHEMA
            ),
        )

    @classmethod
    def from_delivered_message(
        cls,
        delivered_message: Any,
    ) -> "RegionResourceOwnerAckDelivery":
        """Parse one delivered owner ACK and derive its content-addressed receipt."""

        envelope = _field(delivered_message, "envelope")
        ack = RegionResourceOwnerPlanAck.from_transport_payload(
            _field(envelope, "payload")
        )
        receipt = CommunicationDeliveryReceipt.from_delivered_message(
            delivered_message
        )
        delivery = cls(ack=ack, receipt=receipt)
        if (
            receipt.payload_digest
            != canonical_payload_digest(ack.to_transport_payload())
        ):
            raise ValueError("owner ACK receipt payload digest is inconsistent")
        return delivery

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceCoalitionAckDelivery:
    """Delivered member ACK bound to one coalition coordinator."""

    message_id: str
    authority_id: str
    plan_payload_sha256: str
    plan_bus_sequence: int
    lease_expires_at_s: float
    partition_generation: int
    member_ack: CoalitionMemberAck
    receipt: CommunicationDeliveryReceipt
    schema: str = REGION_RESOURCE_COALITION_ACK_DELIVERY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_COALITION_ACK_DELIVERY_SCHEMA:
            raise ValueError("unsupported coalition ACK delivery schema")
        object.__setattr__(
            self, "message_id", _required_text(self.message_id, "message_id")
        )
        object.__setattr__(
            self,
            "authority_id",
            _required_text(self.authority_id, "authority_id"),
        )
        object.__setattr__(
            self,
            "plan_payload_sha256",
            _sha256_text(
                self.plan_payload_sha256,
                "plan_payload_sha256",
            ),
        )
        object.__setattr__(
            self,
            "plan_bus_sequence",
            _positive_int(self.plan_bus_sequence, "plan_bus_sequence"),
        )
        object.__setattr__(
            self,
            "lease_expires_at_s",
            _finite_nonnegative(
                self.lease_expires_at_s, "lease_expires_at_s"
            ),
        )
        object.__setattr__(
            self,
            "partition_generation",
            _nonnegative_int(
                self.partition_generation, "partition_generation"
            ),
        )
        if not isinstance(self.member_ack, CoalitionMemberAck):
            object.__setattr__(
                self,
                "member_ack",
                CoalitionMemberAck(**dict(_strict_mapping(
                    self.member_ack, "member_ack"
                ))),
            )
        object.__setattr__(
            self,
            "receipt",
            CommunicationDeliveryReceipt.from_value(self.receipt),
        )

    @classmethod
    def from_value(cls, value: Any) -> "RegionResourceCoalitionAckDelivery":
        if isinstance(value, cls):
            return value
        mapping = _strict_mapping(value, "coalition_ack_delivery")
        _require_exact_keys(cls, mapping, "coalition_ack_delivery")
        ack_value = mapping["member_ack"]
        ack = (
            ack_value
            if isinstance(ack_value, CoalitionMemberAck)
            else CoalitionMemberAck(**dict(_strict_mapping(
                ack_value, "member_ack"
            )))
        )
        return cls(
            message_id=mapping["message_id"],
            authority_id=mapping["authority_id"],
            plan_payload_sha256=mapping["plan_payload_sha256"],
            plan_bus_sequence=mapping["plan_bus_sequence"],
            lease_expires_at_s=mapping["lease_expires_at_s"],
            partition_generation=mapping["partition_generation"],
            member_ack=ack,
            receipt=CommunicationDeliveryReceipt.from_value(
                mapping["receipt"]
            ),
            schema=mapping.get(
                "schema", REGION_RESOURCE_COALITION_ACK_DELIVERY_SCHEMA
            ),
        )

    @classmethod
    def from_delivered_message(
        cls,
        delivered_message: Any,
    ) -> "RegionResourceCoalitionAckDelivery":
        """Parse one delivered coalition ACK with its strict nested member DTO."""

        envelope = _field(delivered_message, "envelope")
        mapping = _strict_mapping(
            _field(envelope, "payload"),
            "coalition_ack_transport_payload",
        )
        _assert_truth_and_outcome_free(mapping)
        _require_exact_named_keys(
            mapping,
            {
                "schema",
                "message_id",
                "message_kind",
                "authority_id",
                "plan_version",
                "plan_payload_sha256",
                "plan_bus_sequence",
                "epoch",
                "lease_expires_at_s",
                "partition_generation",
                "member_ack",
            },
            "coalition_ack_transport_payload",
        )
        if (
            mapping["message_kind"]
            != CausalMessageKind.COALITION_MEMBER_ACK.value
        ):
            raise ValueError("coalition ACK transport message_kind is invalid")
        member_mapping = _strict_mapping(mapping["member_ack"], "member_ack")
        _require_exact_keys(CoalitionMemberAck, member_mapping, "member_ack")
        member_ack = CoalitionMemberAck(**dict(member_mapping))
        if mapping["plan_version"] != member_ack.plan_version:
            raise ValueError("coalition ACK plan_version alias is inconsistent")
        if mapping["epoch"] != member_ack.epoch:
            raise ValueError("coalition ACK epoch alias is inconsistent")
        receipt = CommunicationDeliveryReceipt.from_delivered_message(
            delivered_message
        )
        delivery = cls(
            schema=mapping["schema"],
            message_id=mapping["message_id"],
            authority_id=mapping["authority_id"],
            plan_payload_sha256=mapping["plan_payload_sha256"],
            plan_bus_sequence=mapping["plan_bus_sequence"],
            lease_expires_at_s=mapping["lease_expires_at_s"],
            partition_generation=mapping["partition_generation"],
            member_ack=member_ack,
            receipt=receipt,
        )
        if delivery.to_transport_payload() != _jsonable(mapping):
            raise ValueError("coalition ACK transport payload is inconsistent")
        return delivery

    def to_transport_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "message_id": self.message_id,
            "message_kind": CausalMessageKind.COALITION_MEMBER_ACK.value,
            "authority_id": self.authority_id,
            "plan_version": self.member_ack.plan_version,
            "plan_payload_sha256": self.plan_payload_sha256,
            "plan_bus_sequence": self.plan_bus_sequence,
            "epoch": self.member_ack.epoch,
            "lease_expires_at_s": self.lease_expires_at_s,
            "partition_generation": self.partition_generation,
            "member_ack": self.member_ack.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceCoalitionCommitEvidence:
    state: CoalitionCommitState
    member_ack_deliveries: tuple[RegionResourceCoalitionAckDelivery, ...]
    schema: str = REGION_RESOURCE_COALITION_COMMIT_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_COALITION_COMMIT_EVIDENCE_SCHEMA:
            raise ValueError("unsupported coalition commit evidence schema")
        if not isinstance(self.state, CoalitionCommitState):
            object.__setattr__(
                self,
                "state",
                CoalitionCommitState(**dict(_strict_mapping(
                    self.state, "coalition_state"
                ))),
            )
        deliveries = tuple(
            RegionResourceCoalitionAckDelivery.from_value(item)
            for item in self.member_ack_deliveries
        )
        object.__setattr__(
            self,
            "member_ack_deliveries",
            tuple(
                sorted(
                    deliveries,
                    key=lambda item: item.member_ack.resource_id,
                )
            ),
        )

    @classmethod
    def from_value(
        cls, value: Any
    ) -> "RegionResourceCoalitionCommitEvidence":
        if isinstance(value, cls):
            return value
        mapping = _strict_mapping(value, "coalition_commit_evidence")
        _require_exact_keys(cls, mapping, "coalition_commit_evidence")
        state_value = mapping["state"]
        state = (
            state_value
            if isinstance(state_value, CoalitionCommitState)
            else CoalitionCommitState(**dict(_strict_mapping(
                state_value, "coalition_state"
            )))
        )
        return cls(
            state=state,
            member_ack_deliveries=tuple(
                RegionResourceCoalitionAckDelivery.from_value(item)
                for item in _sequence(
                    mapping.get("member_ack_deliveries", ()),
                    "member_ack_deliveries",
                )
            ),
            schema=mapping.get(
                "schema",
                REGION_RESOURCE_COALITION_COMMIT_EVIDENCE_SCHEMA,
            ),
        )

    @property
    def immutable_digest(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourcePhysicalWindowEvidence:
    """Observed-state window only; no reward, truth label, or outcome value."""

    window_id: str
    available: bool
    window_start_s: float
    window_end_s: float
    advisory_id: str
    advisory_version: int
    advisory_payload_sha256: str
    applied_plan_id: str
    applied_plan_version: int
    runtime_ack_sha256: str
    owner_ack_receipt_id: str
    coalition_commit_sha256: tuple[str, ...]
    source_state_payload_sha256: str
    post_state_payload_sha256: str
    physical_execution_observed: bool
    hard_constraint_violation_count: int
    schema: str = REGION_RESOURCE_PHYSICAL_WINDOW_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_PHYSICAL_WINDOW_SCHEMA:
            raise ValueError("unsupported physical-window schema")
        for name in (
            "window_id",
            "advisory_id",
            "applied_plan_id",
            "owner_ack_receipt_id",
        ):
            object.__setattr__(
                self, name, _required_text(getattr(self, name), name)
            )
        start = _finite_nonnegative(self.window_start_s, "window_start_s")
        end = _finite_nonnegative(self.window_end_s, "window_end_s")
        if end <= start:
            raise ValueError("physical window end must follow start")
        object.__setattr__(self, "window_start_s", start)
        object.__setattr__(self, "window_end_s", end)
        object.__setattr__(
            self,
            "advisory_version",
            _positive_int(self.advisory_version, "advisory_version"),
        )
        object.__setattr__(
            self,
            "applied_plan_version",
            _nonnegative_int(
                self.applied_plan_version, "applied_plan_version"
            ),
        )
        object.__setattr__(
            self,
            "hard_constraint_violation_count",
            _nonnegative_int(
                self.hard_constraint_violation_count,
                "hard_constraint_violation_count",
            ),
        )
        for name in (
            "advisory_payload_sha256",
            "runtime_ack_sha256",
            "source_state_payload_sha256",
            "post_state_payload_sha256",
        ):
            object.__setattr__(
                self, name, _sha256_text(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "coalition_commit_sha256",
            tuple(
                sorted(
                    {
                        _sha256_text(item, "coalition_commit_sha256")
                        for item in self.coalition_commit_sha256
                    }
                )
            ),
        )
        for name in ("available", "physical_execution_observed"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")

    @classmethod
    def from_value(
        cls, value: Any
    ) -> "RegionResourcePhysicalWindowEvidence":
        if isinstance(value, cls):
            return value
        return _strict_dataclass_from_mapping(
            cls, value, "physical_window"
        )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceProjectedInterventionEvidence:
    """Recomputed evidence for one non-noop D3-consumable action."""

    intervention_id: str
    identifiable_intervention_available: bool
    intervention_fields: tuple[str, ...]
    baseline_payload_sha256: str
    projected_payload_sha256: str
    reason_codes: tuple[str, ...]
    schema: str = REGION_RESOURCE_PROJECTED_INTERVENTION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_PROJECTED_INTERVENTION_SCHEMA:
            raise ValueError("unsupported projected-intervention schema")
        object.__setattr__(
            self,
            "intervention_id",
            _required_text(self.intervention_id, "intervention_id"),
        )
        if not isinstance(self.identifiable_intervention_available, bool):
            raise TypeError(
                "identifiable_intervention_available must be a bool"
            )
        changed_fields = _unique_text(
            self.intervention_fields,
            "intervention_fields",
        )
        reasons = tuple(
            dict.fromkeys(str(item) for item in self.reason_codes)
        )
        object.__setattr__(self, "intervention_fields", changed_fields)
        object.__setattr__(self, "reason_codes", reasons)
        for name in (
            "baseline_payload_sha256",
            "projected_payload_sha256",
        ):
            object.__setattr__(
                self,
                name,
                _sha256_text(getattr(self, name), name),
            )
        if self.identifiable_intervention_available:
            if not changed_fields or reasons:
                raise ValueError(
                    "available intervention requires changed fields only"
                )
            if (
                self.baseline_payload_sha256
                == self.projected_payload_sha256
            ):
                raise ValueError(
                    "available intervention requires different payloads"
                )
        else:
            if changed_fields or not reasons:
                raise ValueError(
                    "unavailable intervention requires a reason and no fields"
                )
            if (
                self.baseline_payload_sha256
                != self.projected_payload_sha256
            ):
                raise ValueError(
                    "no-op intervention payloads must be identical"
                )
        expected_id = "d4-a2-intervention-" + _canonical_sha256(
            {
                "schema": self.schema,
                "identifiable_intervention_available": (
                    self.identifiable_intervention_available
                ),
                "intervention_fields": self.intervention_fields,
                "baseline_payload_sha256": self.baseline_payload_sha256,
                "projected_payload_sha256": self.projected_payload_sha256,
                "reason_codes": self.reason_codes,
            }
        )
        if self.intervention_id != expected_id:
            raise ValueError(
                "intervention_id does not match intervention content"
            )

    @property
    def content_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    @classmethod
    def from_value(
        cls,
        value: Any,
    ) -> "RegionResourceProjectedInterventionEvidence":
        if isinstance(value, cls):
            return value
        return _strict_dataclass_from_mapping(
            cls,
            value,
            "projected_intervention",
        )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceAppliedRecommendation:
    """Projected recommendation; intervention evidence decides adoption scope."""

    application_id: str
    advisory: RegionResourceAdvisoryContract
    intervention_evidence: RegionResourceProjectedInterventionEvidence
    advisory_version: int
    source_snapshot_payload_sha256: str
    candidate_payload_sha256: str
    projected_payload_sha256: str
    advisory_payload_sha256: str
    context_payload_sha256: str
    owner_node_id: str
    owner_layer: RegionalAuthorityLayer | str
    source_plan_id: str
    source_plan_version: int
    epoch: int
    lease_expires_at_s: float
    region_ids: tuple[str, ...]
    consumption_timestamp_s: float
    deterministic_projection_applied: bool = True
    execution_authority_granted: bool = False
    a2_benefit_claimed: bool = False
    schema: str = REGION_RESOURCE_APPLIED_RECOMMENDATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_APPLIED_RECOMMENDATION_SCHEMA:
            raise ValueError("unsupported applied-recommendation schema")
        if not isinstance(self.advisory, RegionResourceAdvisoryContract):
            object.__setattr__(
                self,
                "advisory",
                RegionResourceAdvisoryContract.from_dict(
                    _strict_mapping(self.advisory, "advisory")
                ),
            )
        object.__setattr__(
            self,
            "intervention_evidence",
            RegionResourceProjectedInterventionEvidence.from_value(
                self.intervention_evidence
            ),
        )
        for name in (
            "application_id",
            "owner_node_id",
            "source_plan_id",
        ):
            object.__setattr__(
                self, name, _required_text(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "advisory_version",
            _positive_int(self.advisory_version, "advisory_version"),
        )
        object.__setattr__(
            self,
            "owner_layer",
            self.owner_layer
            if isinstance(self.owner_layer, RegionalAuthorityLayer)
            else RegionalAuthorityLayer(str(self.owner_layer)),
        )
        object.__setattr__(
            self,
            "source_plan_version",
            _nonnegative_int(
                self.source_plan_version, "source_plan_version"
            ),
        )
        object.__setattr__(
            self, "epoch", _nonnegative_int(self.epoch, "epoch")
        )
        object.__setattr__(
            self,
            "lease_expires_at_s",
            _finite_nonnegative(
                self.lease_expires_at_s, "lease_expires_at_s"
            ),
        )
        object.__setattr__(
            self,
            "consumption_timestamp_s",
            _finite_nonnegative(
                self.consumption_timestamp_s, "consumption_timestamp_s"
            ),
        )
        regions = _unique_text(self.region_ids, "region_ids")
        if not regions:
            raise ValueError("applied recommendation requires regions")
        object.__setattr__(self, "region_ids", regions)
        for name in (
            "source_snapshot_payload_sha256",
            "candidate_payload_sha256",
            "projected_payload_sha256",
            "advisory_payload_sha256",
            "context_payload_sha256",
        ):
            object.__setattr__(
                self, name, _sha256_text(getattr(self, name), name)
            )
        for name in (
            "deterministic_projection_applied",
            "execution_authority_granted",
            "a2_benefit_claimed",
        ):
            _strict_bool(getattr(self, name), name)
        if not self.deterministic_projection_applied:
            raise ValueError("applied recommendation requires projection")
        expected_intervention = _build_projected_intervention_evidence(
            self.advisory
        )
        if self.intervention_evidence != expected_intervention:
            raise ValueError(
                "projected intervention evidence does not match advisory"
            )
        if self.execution_authority_granted or self.a2_benefit_claimed:
            raise ValueError(
                "applied recommendation cannot grant authority or claim benefit"
            )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceSafeAdoptionPreparation:
    """Fail-closed result of candidate projection and next-cycle validation."""

    available: bool
    stage: RegionResourceSafeAdoptionStage | str
    reason_codes: tuple[str, ...]
    applied_recommendation: RegionResourceAppliedRecommendation | None = None
    schema: str = REGION_RESOURCE_SAFE_ADOPTION_PREPARATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_SAFE_ADOPTION_PREPARATION_SCHEMA:
            raise ValueError("unsupported safe-adoption preparation schema")
        _strict_bool(self.available, "available")
        object.__setattr__(
            self,
            "stage",
            self.stage
            if isinstance(self.stage, RegionResourceSafeAdoptionStage)
            else RegionResourceSafeAdoptionStage(str(self.stage)),
        )
        reasons = tuple(dict.fromkeys(str(item) for item in self.reason_codes))
        object.__setattr__(self, "reason_codes", reasons)
        if self.available:
            if reasons or self.applied_recommendation is None:
                raise ValueError(
                    "available preparation needs an applied recommendation only"
                )
            if (
                self.stage
                != RegionResourceSafeAdoptionStage.APPLIED_RECOMMENDATION_PREPARED
            ):
                raise ValueError("available preparation has invalid stage")
        else:
            if not reasons:
                raise ValueError("unavailable preparation needs a reason")
            if self.applied_recommendation is not None:
                raise ValueError(
                    "unavailable preparation cannot carry an applied recommendation"
                )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RegionResourceSafeAdoptionEvidence:
    """One immutable availability verdict for actual A2 adoption evidence."""

    evidence_id: str
    available: bool
    stage: RegionResourceSafeAdoptionStage | str
    reason_codes: tuple[str, ...]
    preparation: RegionResourceSafeAdoptionPreparation
    evaluated_at_s: float
    d3_successor_plan: RegionResourceD3PlanReference | None = None
    runtime_ack: RegionResourceRuntimeAckEvidence | None = None
    owner_ack_delivery: RegionResourceOwnerAckDelivery | None = None
    coalition_commits: tuple[RegionResourceCoalitionCommitEvidence, ...] = ()
    physical_window: RegionResourcePhysicalWindowEvidence | None = None
    projection_available: bool = False
    d3_successor_plan_available: bool = False
    runtime_ack_available: bool = False
    owner_ack_available: bool = False
    coalition_commit_required: bool = False
    coalition_commit_available: bool = False
    physical_window_available: bool = False
    identifiable_intervention_available: bool = False
    safe_adoption_available: bool = False
    a2_benefit_available: bool = False
    authority_granted: bool = False
    online_truth_used: bool = False
    schema: str = REGION_RESOURCE_SAFE_ADOPTION_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_SAFE_ADOPTION_EVIDENCE_SCHEMA:
            raise ValueError("unsupported safe-adoption evidence schema")
        if not isinstance(
            self.preparation,
            RegionResourceSafeAdoptionPreparation,
        ):
            raise TypeError("preparation must be a safe-adoption DTO")
        for name in (
            "available",
            "projection_available",
            "d3_successor_plan_available",
            "runtime_ack_available",
            "owner_ack_available",
            "coalition_commit_required",
            "coalition_commit_available",
            "physical_window_available",
            "identifiable_intervention_available",
            "safe_adoption_available",
            "a2_benefit_available",
            "authority_granted",
            "online_truth_used",
        ):
            _strict_bool(getattr(self, name), name)
        object.__setattr__(
            self, "evidence_id", _required_text(self.evidence_id, "evidence_id")
        )
        object.__setattr__(
            self,
            "stage",
            self.stage
            if isinstance(self.stage, RegionResourceSafeAdoptionStage)
            else RegionResourceSafeAdoptionStage(str(self.stage)),
        )
        object.__setattr__(
            self,
            "evaluated_at_s",
            _finite_nonnegative(self.evaluated_at_s, "evaluated_at_s"),
        )
        reasons = tuple(dict.fromkeys(str(item) for item in self.reason_codes))
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(
            self,
            "coalition_commits",
            tuple(self.coalition_commits),
        )
        if self.a2_benefit_available or self.authority_granted:
            raise ValueError(
                "D4 adoption evidence cannot grant authority or claim A2 benefit"
            )
        if self.online_truth_used:
            raise ValueError("online safe-adoption evidence must be truth-free")
        expected_intervention = bool(
            self.preparation.applied_recommendation is not None
            and self.preparation.applied_recommendation.intervention_evidence
            .identifiable_intervention_available
        )
        if (
            self.identifiable_intervention_available
            != expected_intervention
        ):
            raise ValueError(
                "intervention availability disagrees with preparation"
            )
        if self.available != self.safe_adoption_available:
            raise ValueError("availability flags disagree")
        if self.available:
            required = (
                self.projection_available,
                self.identifiable_intervention_available,
                self.d3_successor_plan_available,
                self.runtime_ack_available,
                self.owner_ack_available,
                self.coalition_commit_available,
                self.physical_window_available,
            )
            if not all(required) or reasons:
                raise ValueError("available safe adoption lacks required evidence")
            if self.stage != RegionResourceSafeAdoptionStage.PHYSICAL_WINDOW_AVAILABLE:
                raise ValueError("available safe adoption has invalid stage")
        elif not reasons:
            raise ValueError("unavailable safe adoption needs a reason")

    @property
    def content_sha256(self) -> str:
        payload = self.to_dict()
        payload.pop("content_sha256", None)
        return _canonical_sha256(payload)

    def to_dict(self) -> dict[str, Any]:
        payload = _jsonable(self)
        payload["content_sha256"] = _canonical_sha256(payload)
        return payload

    def to_a2_runtime_record_prefix(self) -> dict[str, Any]:
        """Expose only the adoption prefix; D6 must add paired outcome fields."""

        return {
            "schema": self.schema,
            "evidence_id": self.evidence_id,
            "available": self.available,
            "stage": self.stage.value,
            "reason_codes": list(self.reason_codes),
            "applied_recommendation": (
                None
                if self.preparation.applied_recommendation is None
                else self.preparation.applied_recommendation.to_dict()
            ),
            "d3_successor_plan": (
                None
                if self.d3_successor_plan is None
                else self.d3_successor_plan.to_dict()
            ),
            "runtime_ack": (
                None if self.runtime_ack is None else self.runtime_ack.to_dict()
            ),
            "owner_ack_delivery": (
                None
                if self.owner_ack_delivery is None
                else self.owner_ack_delivery.to_dict()
            ),
            "coalition_commits": [
                item.to_dict() for item in self.coalition_commits
            ],
            "physical_window": (
                None
                if self.physical_window is None
                else self.physical_window.to_dict()
            ),
            "projection_available": self.projection_available,
            "identifiable_intervention_available": (
                self.identifiable_intervention_available
            ),
            "d3_successor_plan_available": (
                self.d3_successor_plan_available
            ),
            "physical_window_available": self.physical_window_available,
            "safe_adoption_available": self.safe_adoption_available,
            "a2_benefit_available": False,
            "authority_granted": False,
            "online_truth_used": False,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True, slots=True)
class RegionResourceAckDeliveryValidation:
    """Fail-closed transport verdict that never grants execution authority."""

    evidence_kind: str
    accepted: bool
    reason_codes: tuple[str, ...]
    communication_validation: CommunicationEvidenceValidation | None = None
    authority_granted: bool = False
    schema: str = REGION_RESOURCE_ACK_DELIVERY_VALIDATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_ACK_DELIVERY_VALIDATION_SCHEMA:
            raise ValueError("unsupported ACK-delivery validation schema")
        _strict_bool(self.accepted, "accepted")
        _strict_bool(self.authority_granted, "authority_granted")
        object.__setattr__(
            self,
            "evidence_kind",
            _required_text(self.evidence_kind, "evidence_kind"),
        )
        reasons = tuple(dict.fromkeys(str(item) for item in self.reason_codes))
        object.__setattr__(self, "reason_codes", reasons)
        if self.accepted and reasons:
            raise ValueError("accepted ACK delivery cannot contain reasons")
        if not self.accepted and not reasons:
            raise ValueError("rejected ACK delivery requires a reason")
        if (
            self.accepted
            and (
                self.communication_validation is None
                or not self.communication_validation.accepted
            )
        ):
            raise ValueError(
                "ACK delivery and communication verdicts are inconsistent"
            )
        if self.authority_granted:
            raise ValueError("ACK delivery validation cannot grant authority")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


def build_region_resource_owner_plan_ack(
    *,
    message_id: str,
    applied_recommendation: RegionResourceAppliedRecommendation,
    d3_successor_plan: RegionResourceD3PlanReference | Mapping[str, Any],
    runtime_ack: RegionResourceRuntimeAckEvidence | Mapping[str, Any],
    context: RegionResourceSafeAdoptionContext | Mapping[str, Any],
    acknowledged_at_s: float,
    accepted: bool = True,
) -> RegionResourceOwnerPlanAck:
    """Build the exact owner ACK expected from authoritative adoption inputs."""

    _assert_truth_and_outcome_free(
        {
            "applied_recommendation": applied_recommendation,
            "d3_successor_plan": d3_successor_plan,
            "runtime_ack": runtime_ack,
            "context": context,
        }
    )
    if not isinstance(applied_recommendation, RegionResourceAppliedRecommendation):
        raise TypeError("applied_recommendation must be a D4 DTO")
    plan = RegionResourceD3PlanReference.from_value(d3_successor_plan)
    parsed_runtime_ack = _runtime_ack_from_value(runtime_ack)
    parsed_context = RegionResourceSafeAdoptionContext.from_value(context)
    if (
        not parsed_runtime_ack.runtime_advisory_applied_ack_available
        or parsed_runtime_ack.code != RegionResourceRuntimeAckCode.APPLIED.value
    ):
        raise RegionResourceSafeAdoptionError(
            "runtime_assignment_ack_unavailable",
            parsed_runtime_ack.code,
        )
    assignment_ack_sha256 = _sha256_text(
        parsed_runtime_ack.assignment_plan_ack_payload_sha256,
        "runtime_ack.assignment_plan_ack_payload_sha256",
    )
    assignment_ack_sequence = _positive_int(
        parsed_runtime_ack.ack_bus_sequence,
        "runtime_ack.ack_bus_sequence",
    )
    return RegionResourceOwnerPlanAck(
        message_id=message_id,
        owner_node_id=applied_recommendation.owner_node_id,
        owner_layer=applied_recommendation.owner_layer,
        region_ids=applied_recommendation.region_ids,
        advisory_id=applied_recommendation.advisory.advisory_id,
        advisory_version=applied_recommendation.advisory_version,
        advisory_payload_sha256=(
            applied_recommendation.advisory_payload_sha256
        ),
        source_plan_id=applied_recommendation.source_plan_id,
        source_plan_version=applied_recommendation.source_plan_version,
        applied_plan_id=plan.plan_id,
        applied_plan_version=plan.plan_version,
        applied_plan_payload_sha256=plan.plan_payload_sha256,
        applied_plan_bus_sequence=plan.plan_bus_sequence,
        runtime_assignment_ack_payload_sha256=assignment_ack_sha256,
        runtime_assignment_ack_bus_sequence=assignment_ack_sequence,
        epoch=applied_recommendation.epoch,
        lease_expires_at_s=applied_recommendation.lease_expires_at_s,
        partition_generation=parsed_context.partition_generation,
        acknowledged_at_s=acknowledged_at_s,
        accepted=accepted,
    )


def validate_region_resource_owner_ack_delivery(
    delivery: RegionResourceOwnerAckDelivery | Mapping[str, Any],
    *,
    expected_ack: RegionResourceOwnerPlanAck | Mapping[str, Any],
    expected_destination_node_id: str,
    decision_timestamp_s: float,
    communication_gate: CausalCommunicationEvidenceGate | None = None,
) -> RegionResourceAckDeliveryValidation:
    """Validate one owner ACK payload, content-addressed receipt, and route."""

    try:
        parsed_delivery = RegionResourceOwnerAckDelivery.from_value(delivery)
        parsed_expected = RegionResourceOwnerPlanAck.from_value(expected_ack)
        destination = _required_text(
            expected_destination_node_id,
            "expected_destination_node_id",
        )
        decision_time = _finite_nonnegative(
            decision_timestamp_s,
            "decision_timestamp_s",
        )
    except (KeyError, TypeError, ValueError):
        return RegionResourceAckDeliveryValidation(
            evidence_kind="regional_plan_owner_ack_delivery",
            accepted=False,
            reason_codes=("owner_ack_delivery_invalid",),
        )

    reasons: list[str] = []
    if parsed_delivery.ack != parsed_expected:
        reasons.append("owner_ack_cross_binding_invalid")
    if not parsed_delivery.ack.accepted:
        reasons.append("owner_ack_rejected")
    receipt = parsed_delivery.receipt
    if receipt.receipt_id != expected_delivery_receipt_id(receipt):
        reasons.append("owner_ack_receipt_not_content_addressed")
    if receipt.transport_topic != REGION_RESOURCE_OWNER_ACK_TOPIC:
        reasons.append("owner_ack_transport_topic_invalid")
    if (
        abs(
            receipt.sent_timestamp_s
            - parsed_delivery.ack.acknowledged_at_s
        )
        > _TIME_TOLERANCE_S
    ):
        reasons.append("owner_ack_sent_timestamp_mismatch")

    gate = communication_gate or CausalCommunicationEvidenceGate()
    communication = gate.validate_regional_plan_owner_ack(
        receipt,
        CommunicationEvidenceExpectation(
            expected_source_node_id=parsed_expected.owner_node_id,
            expected_destination_node_id=destination,
            expected_authority_id=parsed_expected.owner_node_id,
            expected_plan_version=parsed_expected.applied_plan_version,
            expected_epoch=parsed_expected.epoch,
            expected_lease_expires_at_s=(
                parsed_expected.lease_expires_at_s
            ),
            decision_timestamp_s=decision_time,
            expected_partition_generation=(
                parsed_expected.partition_generation
            ),
            expected_payload_digest=canonical_payload_digest(
                parsed_expected.to_transport_payload()
            ),
            expected_message_id=parsed_expected.message_id,
        ),
    )
    reasons.extend(communication.reason_codes)
    normalized = tuple(dict.fromkeys(reasons))
    return RegionResourceAckDeliveryValidation(
        evidence_kind="regional_plan_owner_ack_delivery",
        accepted=not normalized,
        reason_codes=normalized,
        communication_validation=communication,
    )


def validate_region_resource_coalition_ack_delivery(
    delivery: RegionResourceCoalitionAckDelivery | Mapping[str, Any],
    *,
    expected_member_ack: CoalitionMemberAck | Mapping[str, Any],
    expected_authority_id: str,
    expected_plan_payload_sha256: str,
    expected_plan_bus_sequence: int,
    expected_lease_expires_at_s: float,
    expected_partition_generation: int,
    expected_destination_node_id: str,
    decision_timestamp_s: float,
    expected_message_id: str | None = None,
    communication_gate: CausalCommunicationEvidenceGate | None = None,
) -> RegionResourceAckDeliveryValidation:
    """Validate a strict nested coalition member ACK and its delivery receipt."""

    try:
        parsed_delivery = RegionResourceCoalitionAckDelivery.from_value(
            delivery
        )
        if isinstance(expected_member_ack, CoalitionMemberAck):
            member_ack = expected_member_ack
        else:
            member_mapping = _strict_mapping(
                expected_member_ack,
                "expected_member_ack",
            )
            _require_exact_keys(
                CoalitionMemberAck,
                member_mapping,
                "expected_member_ack",
            )
            member_ack = CoalitionMemberAck(**dict(member_mapping))
        authority_id = _required_text(
            expected_authority_id,
            "expected_authority_id",
        )
        plan_payload_sha256 = _sha256_text(
            expected_plan_payload_sha256,
            "expected_plan_payload_sha256",
        )
        plan_bus_sequence = _positive_int(
            expected_plan_bus_sequence,
            "expected_plan_bus_sequence",
        )
        lease_expires_at_s = _finite_nonnegative(
            expected_lease_expires_at_s,
            "expected_lease_expires_at_s",
        )
        partition_generation = _nonnegative_int(
            expected_partition_generation,
            "expected_partition_generation",
        )
        destination = _required_text(
            expected_destination_node_id,
            "expected_destination_node_id",
        )
        decision_time = _finite_nonnegative(
            decision_timestamp_s,
            "decision_timestamp_s",
        )
        message_id = (
            parsed_delivery.message_id
            if expected_message_id is None
            else _required_text(expected_message_id, "expected_message_id")
        )
    except (KeyError, TypeError, ValueError):
        return RegionResourceAckDeliveryValidation(
            evidence_kind="coalition_member_ack_delivery",
            accepted=False,
            reason_codes=("coalition_ack_delivery_invalid",),
        )

    expected_payload = {
        "schema": REGION_RESOURCE_COALITION_ACK_DELIVERY_SCHEMA,
        "message_id": message_id,
        "message_kind": CausalMessageKind.COALITION_MEMBER_ACK.value,
        "authority_id": authority_id,
        "plan_version": member_ack.plan_version,
        "plan_payload_sha256": plan_payload_sha256,
        "plan_bus_sequence": plan_bus_sequence,
        "epoch": member_ack.epoch,
        "lease_expires_at_s": lease_expires_at_s,
        "partition_generation": partition_generation,
        "member_ack": member_ack.to_dict(),
    }
    reasons: list[str] = []
    if parsed_delivery.to_transport_payload() != expected_payload:
        reasons.append("coalition_member_ack_cross_binding_invalid")
    receipt = parsed_delivery.receipt
    if receipt.receipt_id != expected_delivery_receipt_id(receipt):
        reasons.append("coalition_ack_receipt_not_content_addressed")
    if receipt.transport_topic != REGION_RESOURCE_COALITION_ACK_TOPIC:
        reasons.append("coalition_ack_transport_topic_invalid")
    if (
        abs(
            receipt.sent_timestamp_s
            - parsed_delivery.member_ack.evidence_timestamp
        )
        > _TIME_TOLERANCE_S
    ):
        reasons.append("coalition_ack_sent_timestamp_mismatch")

    gate = communication_gate or CausalCommunicationEvidenceGate()
    communication = gate.validate_coalition_member_ack(
        receipt,
        CommunicationEvidenceExpectation(
            expected_source_node_id=member_ack.resource_id,
            expected_destination_node_id=destination,
            expected_authority_id=authority_id,
            expected_plan_version=member_ack.plan_version,
            expected_epoch=member_ack.epoch,
            expected_lease_expires_at_s=lease_expires_at_s,
            decision_timestamp_s=decision_time,
            expected_partition_generation=partition_generation,
            expected_payload_digest=canonical_payload_digest(expected_payload),
            expected_message_id=message_id,
        ),
    )
    reasons.extend(communication.reason_codes)
    normalized = tuple(dict.fromkeys(reasons))
    return RegionResourceAckDeliveryValidation(
        evidence_kind="coalition_member_ack_delivery",
        accepted=not normalized,
        reason_codes=normalized,
        communication_validation=communication,
    )


class RegionResourceSafeAdoptionAssembler:
    """Prepare and assemble one authority-domain A2 adoption record."""

    def __init__(
        self,
        *,
        projector: DeterministicResourceProjector | None = None,
        communication_gate: CausalCommunicationEvidenceGate | None = None,
    ) -> None:
        self._projector = projector or DeterministicResourceProjector()
        self._communication_gate = (
            communication_gate or CausalCommunicationEvidenceGate()
        )
        self._highest_applied_by_region: dict[
            str, tuple[str, str, int, int]
        ] = {}
        self._final_by_input_sha256: dict[
            str, RegionResourceSafeAdoptionEvidence
        ] = {}

    def prepare(
        self,
        *,
        snapshot: RegionResourceSnapshot | Mapping[str, Any],
        candidate: RegionResourceRecommendation | Mapping[str, Any],
        context: RegionResourceSafeAdoptionContext | Mapping[str, Any],
        formal_decision: RegionalFailoverDecision | None,
    ) -> RegionResourceSafeAdoptionPreparation:
        """Project candidate actions without granting runtime authority."""

        try:
            _assert_truth_and_outcome_free(
                {
                    "snapshot": snapshot,
                    "candidate": candidate,
                    "context": context,
                    "formal_decision": formal_decision,
                }
            )
            parsed_snapshot = (
                snapshot
                if isinstance(snapshot, RegionResourceSnapshot)
                else RegionResourceSnapshot.from_dict(
                    _strict_mapping(snapshot, "snapshot")
                )
            )
            parsed_candidate = (
                candidate
                if isinstance(candidate, RegionResourceRecommendation)
                else RegionResourceRecommendation.from_dict(
                    _strict_mapping(candidate, "candidate")
                )
            )
            parsed_context = RegionResourceSafeAdoptionContext.from_value(
                context
            )
            if formal_decision is None:
                _fail(
                    "formal_decision_missing",
                    "safe adoption requires the current formal D4 decision",
                )
            if not isinstance(formal_decision, RegionalFailoverDecision):
                _fail(
                    "formal_decision_type_invalid",
                    "formal decision must be a RegionalFailoverDecision",
                )
            self._validate_context_scope(parsed_snapshot, parsed_context)
            self._validate_authority_hierarchy(
                parsed_snapshot, parsed_context, formal_decision
            )
            if parsed_candidate.source != RecommendationSource.LEARNED:
                _fail(
                    "candidate_not_learned",
                    "A2 actual adoption requires a learned candidate",
                )
            if parsed_candidate.fallback_reason is not None:
                _fail(
                    "deterministic_rule_fallback_not_candidate_adoption",
                    parsed_candidate.fallback_reason,
                )
            if (
                parsed_candidate.confidence
                < REGION_RESOURCE_SAFE_ADOPTION_MINIMUM_CONFIDENCE
            ):
                _fail(
                    "candidate_below_frozen_confidence_threshold",
                    str(parsed_candidate.confidence),
                )

            projected = self._projector.project(
                parsed_snapshot,
                parsed_candidate,
                formal_decision=formal_decision,
            )
            if projected.projection_rejections:
                _fail(
                    "deterministic_projection_rejected_or_modified",
                    ",".join(projected.projection_rejections),
                )
            advisory = self._projector.build_advisory_contract(
                parsed_snapshot,
                projected,
                formal_decision=formal_decision,
            )
            if advisory.publication_rejections:
                _fail(
                    "advisory_publication_rejected",
                    ",".join(advisory.publication_rejections),
                )
            view = self._projector.validate_for_consumption(
                advisory,
                parsed_snapshot,
                evaluated_at_s=parsed_context.consumption_timestamp_s,
                formal_decision=formal_decision,
            )
            if not view.consumable:
                _fail(
                    "advisory_consumption_rejected",
                    ",".join(view.rejection_reasons),
                )
            domain = self._single_authority_domain(advisory)
            (
                owner_node_id,
                owner_layer,
                source_plan_id,
                source_plan_version,
                epoch,
                lease_expires_at_s,
                region_ids,
            ) = domain
            if parsed_context.consumption_timestamp_s >= lease_expires_at_s:
                _fail(
                    "authority_lease_expired",
                    "consumption occurred at or after lease expiry",
                )
            if parsed_candidate.source == RecommendationSource.LEARNED:
                _sha256_text(
                    parsed_candidate.model_sha256, "candidate.model_sha256"
                )
            snapshot_sha256 = _canonical_sha256(parsed_snapshot.to_dict())
            candidate_sha256 = _canonical_sha256(parsed_candidate.to_dict())
            projected_sha256 = _canonical_sha256(projected.to_dict())
            advisory_sha256 = canonical_runtime_payload_sha256(
                advisory.to_dict()
            )
            context_sha256 = _canonical_sha256(parsed_context.to_dict())
            application_id = "d4-a2-application-" + _canonical_sha256(
                {
                    "schema": REGION_RESOURCE_APPLIED_RECOMMENDATION_SCHEMA,
                    "snapshot_sha256": snapshot_sha256,
                    "candidate_sha256": candidate_sha256,
                    "projected_sha256": projected_sha256,
                    "advisory_sha256": advisory_sha256,
                    "context_sha256": context_sha256,
                }
            )
            intervention_evidence = (
                _build_projected_intervention_evidence(advisory)
            )
            applied = RegionResourceAppliedRecommendation(
                application_id=application_id,
                advisory=advisory,
                intervention_evidence=intervention_evidence,
                advisory_version=parsed_context.advisory_version,
                source_snapshot_payload_sha256=snapshot_sha256,
                candidate_payload_sha256=candidate_sha256,
                projected_payload_sha256=projected_sha256,
                advisory_payload_sha256=advisory_sha256,
                context_payload_sha256=context_sha256,
                owner_node_id=owner_node_id,
                owner_layer=owner_layer,
                source_plan_id=source_plan_id,
                source_plan_version=source_plan_version,
                epoch=epoch,
                lease_expires_at_s=lease_expires_at_s,
                region_ids=region_ids,
                consumption_timestamp_s=parsed_context.consumption_timestamp_s,
            )
            return RegionResourceSafeAdoptionPreparation(
                available=True,
                stage=(
                    RegionResourceSafeAdoptionStage
                    .APPLIED_RECOMMENDATION_PREPARED
                ),
                reason_codes=(),
                applied_recommendation=applied,
            )
        except RegionResourceSafeAdoptionError as error:
            return _rejected_preparation(error.code)
        except (KeyError, TypeError, ValueError) as error:
            return _rejected_preparation(
                "safe_adoption_input_invalid."
                + type(error).__name__.lower()
            )

    def assemble(
        self,
        *,
        preparation: RegionResourceSafeAdoptionPreparation,
        context: RegionResourceSafeAdoptionContext | Mapping[str, Any],
        evaluated_at_s: float,
        d3_successor_plan: (
            RegionResourceD3PlanReference | Mapping[str, Any] | None
        ) = None,
        runtime_ack: (
            RegionResourceRuntimeAckEvidence | Mapping[str, Any] | None
        ) = None,
        owner_ack_delivery: (
            RegionResourceOwnerAckDelivery | Mapping[str, Any] | None
        ) = None,
        coalition_commits: Sequence[
            RegionResourceCoalitionCommitEvidence | Mapping[str, Any]
        ] = (),
        physical_window: (
            RegionResourcePhysicalWindowEvidence | Mapping[str, Any] | None
        ) = None,
    ) -> RegionResourceSafeAdoptionEvidence:
        """Assemble runtime adoption evidence; missing facts stay unavailable."""

        evaluated = _finite_nonnegative(evaluated_at_s, "evaluated_at_s")
        try:
            _assert_truth_and_outcome_free(
                {
                    "preparation": preparation,
                    "context": context,
                    "d3_successor_plan": d3_successor_plan,
                    "runtime_ack": runtime_ack,
                    "owner_ack_delivery": owner_ack_delivery,
                    "coalition_commits": coalition_commits,
                    "physical_window": physical_window,
                }
            )
            parsed_context = RegionResourceSafeAdoptionContext.from_value(
                context
            )
            if not isinstance(preparation, RegionResourceSafeAdoptionPreparation):
                _fail(
                    "preparation_type_invalid",
                    "preparation must be a safe-adoption DTO",
                )
            input_sha256 = _canonical_sha256(
                {
                    "preparation": preparation.to_dict(),
                    "context": parsed_context.to_dict(),
                    "evaluated_at_s": evaluated,
                    "d3_successor_plan": _jsonable(d3_successor_plan),
                    "runtime_ack": _jsonable(runtime_ack),
                    "owner_ack_delivery": _jsonable(owner_ack_delivery),
                    "coalition_commits": _jsonable(coalition_commits),
                    "physical_window": _jsonable(physical_window),
                }
            )
            cached = self._final_by_input_sha256.get(input_sha256)
            if cached is not None:
                return cached
            if not preparation.available or preparation.applied_recommendation is None:
                result = self._evidence(
                    input_sha256=input_sha256,
                    preparation=preparation,
                    evaluated_at_s=evaluated,
                    stage=RegionResourceSafeAdoptionStage.CANDIDATE_REJECTED,
                    reason_codes=preparation.reason_codes,
                )
                self._final_by_input_sha256[input_sha256] = result
                return result

            applied = preparation.applied_recommendation
            self._validate_context_binding(applied, parsed_context)
            if evaluated < parsed_context.consumption_timestamp_s:
                _fail(
                    "evaluation_precedes_consumption",
                    "final evaluation timestamp precedes consumption",
                )
            if evaluated >= applied.lease_expires_at_s:
                _fail(
                    "authority_lease_expired",
                    "final evaluation occurred at or after lease expiry",
                )
            if (
                not applied.intervention_evidence
                .identifiable_intervention_available
            ):
                return self._cache_unavailable(
                    input_sha256=input_sha256,
                    preparation=preparation,
                    evaluated_at_s=evaluated,
                    stage=(
                        RegionResourceSafeAdoptionStage
                        .SAFE_ADOPTION_REJECTED
                    ),
                    reason="identifiable_regional_intervention_missing",
                    projection_available=True,
                )

            if d3_successor_plan is None:
                return self._cache_unavailable(
                    input_sha256=input_sha256,
                    preparation=preparation,
                    evaluated_at_s=evaluated,
                    stage=RegionResourceSafeAdoptionStage.AWAITING_D3_PLAN,
                    reason="d3_successor_plan_missing",
                    projection_available=True,
                )
            plan = RegionResourceD3PlanReference.from_value(
                d3_successor_plan
            )
            self._validate_successor_plan(applied, plan)
            self._validate_monotonic_generation(applied, plan)

            if runtime_ack is None:
                return self._cache_unavailable(
                    input_sha256=input_sha256,
                    preparation=preparation,
                    evaluated_at_s=evaluated,
                    stage=RegionResourceSafeAdoptionStage.AWAITING_RUNTIME_ACK,
                    reason="runtime_ack_missing",
                    projection_available=True,
                    d3_plan=plan,
                )
            parsed_runtime_ack = _runtime_ack_from_value(runtime_ack)
            self._validate_runtime_ack(applied, plan, parsed_runtime_ack)

            if owner_ack_delivery is None:
                return self._cache_unavailable(
                    input_sha256=input_sha256,
                    preparation=preparation,
                    evaluated_at_s=evaluated,
                    stage=RegionResourceSafeAdoptionStage.AWAITING_OWNER_ACK,
                    reason="owner_ack_missing",
                    projection_available=True,
                    d3_plan=plan,
                    runtime_ack=parsed_runtime_ack,
                )
            owner_delivery = RegionResourceOwnerAckDelivery.from_value(
                owner_ack_delivery
            )
            self._validate_owner_ack(
                applied,
                plan,
                parsed_runtime_ack,
                parsed_context,
                owner_delivery,
                evaluated_at_s=evaluated,
            )

            commits = tuple(
                RegionResourceCoalitionCommitEvidence.from_value(item)
                for item in coalition_commits
            )
            if plan.coalition_requirements and not commits:
                return self._cache_unavailable(
                    input_sha256=input_sha256,
                    preparation=preparation,
                    evaluated_at_s=evaluated,
                    stage=(
                        RegionResourceSafeAdoptionStage
                        .AWAITING_COALITION_COMMIT
                    ),
                    reason="coalition_commit_missing",
                    projection_available=True,
                    d3_plan=plan,
                    runtime_ack=parsed_runtime_ack,
                    owner_ack=owner_delivery,
                    coalition_required=True,
                )
            self._validate_coalition_commits(
                applied,
                plan,
                parsed_context,
                commits,
                evaluated_at_s=evaluated,
            )

            if physical_window is None:
                return self._cache_unavailable(
                    input_sha256=input_sha256,
                    preparation=preparation,
                    evaluated_at_s=evaluated,
                    stage=(
                        RegionResourceSafeAdoptionStage
                        .AWAITING_PHYSICAL_WINDOW
                    ),
                    reason="physical_window_missing",
                    projection_available=True,
                    d3_plan=plan,
                    runtime_ack=parsed_runtime_ack,
                    owner_ack=owner_delivery,
                    commits=commits,
                    coalition_required=bool(plan.coalition_requirements),
                )
            window = RegionResourcePhysicalWindowEvidence.from_value(
                physical_window
            )
            self._validate_physical_window(
                applied,
                plan,
                parsed_runtime_ack,
                owner_delivery,
                commits,
                window,
                evaluated_at_s=evaluated,
            )

            result = self._evidence(
                input_sha256=input_sha256,
                preparation=preparation,
                evaluated_at_s=evaluated,
                stage=RegionResourceSafeAdoptionStage.PHYSICAL_WINDOW_AVAILABLE,
                reason_codes=(),
                available=True,
                d3_plan=plan,
                runtime_ack=parsed_runtime_ack,
                owner_ack=owner_delivery,
                commits=commits,
                physical_window=window,
                projection_available=True,
                d3_plan_available=True,
                runtime_ack_available=True,
                owner_ack_available=True,
                coalition_required=bool(plan.coalition_requirements),
                coalition_available=True,
                physical_available=True,
            )
            for region_id in applied.region_ids:
                self._highest_applied_by_region[region_id] = (
                    applied.owner_layer.value,
                    applied.owner_node_id,
                    applied.epoch,
                    plan.plan_version,
                )
            self._final_by_input_sha256[input_sha256] = result
            return result
        except RegionResourceSafeAdoptionError as error:
            input_sha256 = _canonical_sha256(
                {
                    "preparation": _jsonable(preparation),
                    "context": _jsonable(context),
                    "evaluated_at_s": evaluated,
                    "error_code": error.code,
                }
            )
            projection_available = bool(
                isinstance(
                    preparation, RegionResourceSafeAdoptionPreparation
                )
                and preparation.available
                and preparation.applied_recommendation is not None
            )
            return self._cache_unavailable(
                input_sha256=input_sha256,
                preparation=(
                    preparation
                    if isinstance(
                        preparation, RegionResourceSafeAdoptionPreparation
                    )
                    else _rejected_preparation("preparation_type_invalid")
                ),
                evaluated_at_s=evaluated,
                stage=(
                    RegionResourceSafeAdoptionStage.SAFE_ADOPTION_REJECTED
                    if projection_available
                    else RegionResourceSafeAdoptionStage.CANDIDATE_REJECTED
                ),
                reason=error.code,
                projection_available=projection_available,
            )
        except (KeyError, TypeError, ValueError) as error:
            input_sha256 = _canonical_sha256(
                {
                    "preparation": _jsonable(preparation),
                    "evaluated_at_s": evaluated,
                    "error_type": type(error).__name__,
                }
            )
            projection_available = bool(
                isinstance(
                    preparation, RegionResourceSafeAdoptionPreparation
                )
                and preparation.available
                and preparation.applied_recommendation is not None
            )
            return self._cache_unavailable(
                input_sha256=input_sha256,
                preparation=(
                    preparation
                    if isinstance(
                        preparation, RegionResourceSafeAdoptionPreparation
                    )
                    else _rejected_preparation("preparation_type_invalid")
                ),
                evaluated_at_s=evaluated,
                stage=(
                    RegionResourceSafeAdoptionStage.SAFE_ADOPTION_REJECTED
                    if projection_available
                    else RegionResourceSafeAdoptionStage.CANDIDATE_REJECTED
                ),
                reason=(
                    "safe_adoption_input_invalid."
                    + type(error).__name__.lower()
                ),
                projection_available=projection_available,
            )

    @staticmethod
    def _validate_context_scope(
        snapshot: RegionResourceSnapshot,
        context: RegionResourceSafeAdoptionContext,
    ) -> None:
        regions = set(snapshot.region_by_id)
        for name, values in (
            (
                "secondary_available_region_ids",
                context.secondary_available_region_ids,
            ),
            ("partitioned_region_ids", context.partitioned_region_ids),
            (
                "active_degradation_region_ids",
                context.active_degradation_region_ids,
            ),
        ):
            unknown = set(values) - regions
            if unknown:
                _fail(
                    "context_unknown_region",
                    f"{name}:{','.join(sorted(unknown))}",
                )
        if set(context.partitioned_region_ids) & regions:
            _fail(
                "network_partition_blocks_adoption",
                ",".join(context.partitioned_region_ids),
            )

    @staticmethod
    def _validate_authority_hierarchy(
        snapshot: RegionResourceSnapshot,
        context: RegionResourceSafeAdoptionContext,
        formal_decision: RegionalFailoverDecision,
    ) -> None:
        formal_by_region = {
            item.region_id: item for item in formal_decision.region_decisions
        }
        available_secondary = set(context.secondary_available_region_ids)
        active_regions = set(context.active_degradation_region_ids)
        for node in snapshot.regions:
            formal = formal_by_region.get(node.region_id)
            if formal is None:
                _fail("formal_region_missing", node.region_id)
            if (
                formal.ownership.owner_id != node.current_owner_id
                or formal.ownership.owner_layer != node.current_owner_layer
                or formal.ownership.plan_id != node.plan_id
                or formal.ownership.plan_version != node.plan_version
                or formal.ownership.epoch != node.epoch
                or formal.ownership.lease_expires_at_s
                != node.lease_expires_at_s
                or formal.selected_layer != node.current_owner_layer
                or formal.fail_closed
                or not formal.execution_allowed
            ):
                _fail(
                    "formal_authority_binding_invalid", node.region_id
                )
            layer = node.current_owner_layer
            if context.center_health == C2Health.NORMAL:
                if layer != RegionalAuthorityLayer.CENTER:
                    _fail(
                        "center_normal_degradation_forbidden",
                        node.region_id,
                    )
                if formal.action in {
                    RegionalAction.DEGRADE_TO_SECONDARY,
                    RegionalAction.DEGRADE_TO_DISTRIBUTED,
                }:
                    _fail(
                        "center_normal_degradation_forbidden",
                        node.region_id,
                    )
                continue
            if context.center_health == C2Health.FAILED:
                expected = (
                    RegionalAuthorityLayer.SECONDARY
                    if node.region_id in available_secondary
                    else RegionalAuthorityLayer.DISTRIBUTED
                )
                if layer != expected:
                    code = (
                        "secondary_priority_violation"
                        if expected == RegionalAuthorityLayer.SECONDARY
                        else "secondary_unavailable_owner_invalid"
                    )
                    _fail(code, node.region_id)
                expected_action = (
                    RegionalAction.DEGRADE_TO_SECONDARY
                    if expected == RegionalAuthorityLayer.SECONDARY
                    else RegionalAction.DEGRADE_TO_DISTRIBUTED
                )
                if formal.action != expected_action:
                    _fail(
                        "formal_degradation_action_mismatch",
                        node.region_id,
                    )
                continue
            if layer == RegionalAuthorityLayer.CENTER:
                continue
            if node.region_id not in active_regions:
                _fail(
                    "active_degradation_evidence_missing", node.region_id
                )
            if (
                layer == RegionalAuthorityLayer.DISTRIBUTED
                and node.region_id in available_secondary
            ):
                _fail("secondary_priority_violation", node.region_id)
            expected_action = (
                RegionalAction.DEGRADE_TO_SECONDARY
                if layer == RegionalAuthorityLayer.SECONDARY
                else RegionalAction.DEGRADE_TO_DISTRIBUTED
            )
            if formal.action != expected_action:
                _fail(
                    "formal_active_degradation_action_mismatch",
                    node.region_id,
                )

    @staticmethod
    def _single_authority_domain(
        advisory: RegionResourceAdvisoryContract,
    ) -> tuple[
        str,
        RegionalAuthorityLayer,
        str,
        int,
        int,
        float,
        tuple[str, ...],
    ]:
        domains = {
            (
                region.source_version.owner_id,
                region.source_version.owner_layer,
                region.source_version.plan_id,
                region.source_version.plan_version,
                region.source_version.epoch,
                region.source_version.lease_expires_at_s,
            )
            for region in advisory.regions
        }
        if len(domains) != 1:
            _fail(
                "authority_domain_mixed",
                "main must split adoption evidence by authority domain",
            )
        owner_id, layer, plan_id, version, epoch, lease = next(iter(domains))
        if owner_id is None or layer == RegionalAuthorityLayer.HOLD:
            _fail("authority_owner_unavailable", "active owner is missing")
        return (
            owner_id,
            layer,
            plan_id,
            int(version),
            int(epoch),
            float(lease),
            tuple(sorted(region.region_id for region in advisory.regions)),
        )

    @staticmethod
    def _validate_context_binding(
        applied: RegionResourceAppliedRecommendation,
        context: RegionResourceSafeAdoptionContext,
    ) -> None:
        if (
            applied.context_payload_sha256
            != _canonical_sha256(context.to_dict())
        ):
            _fail(
                "adoption_context_binding_mismatch",
                "context differs from prepared recommendation",
            )

    @staticmethod
    def _validate_successor_plan(
        applied: RegionResourceAppliedRecommendation,
        plan: RegionResourceD3PlanReference,
    ) -> None:
        if (
            plan.previous_plan_id != applied.source_plan_id
            or plan.previous_plan_version != applied.source_plan_version
        ):
            _fail(
                "successor_plan_source_mismatch",
                "D3 previous plan differs from D4 source plan",
            )
        if (
            plan.plan_id == applied.source_plan_id
            or plan.plan_version <= applied.source_plan_version
        ):
            _fail(
                "successor_plan_version_not_strictly_new",
                f"{plan.plan_version}<={applied.source_plan_version}",
            )
        if (
            plan.owner_node_id != applied.owner_node_id
            or plan.owner_layer != applied.owner_layer
        ):
            _fail(
                "successor_plan_authority_mismatch",
                "owner or layer differs",
            )
        if plan.epoch < applied.epoch:
            _fail(
                "successor_plan_epoch_stale",
                f"{plan.epoch}<{applied.epoch}",
            )
        if plan.epoch != applied.epoch:
            _fail(
                "successor_plan_epoch_mismatch",
                f"{plan.epoch}!={applied.epoch}",
            )
        if (
            plan.source_advisory_id != applied.advisory.advisory_id
            or plan.source_advisory_version != applied.advisory_version
            or plan.source_advisory_payload_sha256
            != applied.advisory_payload_sha256
        ):
            _fail(
                "successor_plan_advisory_mismatch",
                "D3 plan does not reference the applied recommendation",
            )
        if (
            not plan.accepted_by_main_runtime
            or not plan.regional_hint_applied
            or not plan.stale_version_rejected
        ):
            _fail(
                "successor_plan_not_applied",
                "D3/main application flags are incomplete",
            )
        if (
            plan.created_at_s < applied.consumption_timestamp_s
            or plan.valid_until_s > applied.lease_expires_at_s
        ):
            _fail(
                "successor_plan_time_scope_invalid",
                "plan creation/validity exceeds advisory authority scope",
            )

    def _validate_monotonic_generation(
        self,
        applied: RegionResourceAppliedRecommendation,
        plan: RegionResourceD3PlanReference,
    ) -> None:
        for region_id in applied.region_ids:
            previous = self._highest_applied_by_region.get(region_id)
            if previous is None:
                continue
            previous_layer, previous_owner, previous_epoch, previous_version = (
                previous
            )
            owner_changed = (
                previous_layer != applied.owner_layer.value
                or previous_owner != applied.owner_node_id
            )
            if owner_changed and not (
                applied.epoch > previous_epoch
                and applied.source_plan_version > previous_version
            ):
                _fail(
                    "authority_generation_not_advanced",
                    region_id,
                )
            if not owner_changed and (
                applied.epoch < previous_epoch
                or (
                    applied.epoch == previous_epoch
                    and applied.source_plan_version < previous_version
                )
            ):
                _fail(
                    "authority_epoch_or_plan_version_stale",
                    region_id,
                )
            if plan.plan_version <= previous_version:
                _fail(
                    "applied_plan_version_stale",
                    region_id,
                )

    @staticmethod
    def _validate_runtime_ack(
        applied: RegionResourceAppliedRecommendation,
        plan: RegionResourceD3PlanReference,
        runtime_ack: RegionResourceRuntimeAckEvidence,
    ) -> None:
        if (
            runtime_ack.schema
            != "d4-region-resource-runtime-ack-evidence-v2"
            or runtime_ack.code != RegionResourceRuntimeAckCode.APPLIED.value
            or not runtime_ack.runtime_advisory_applied_ack_available
            or runtime_ack.adoption_kind
            != RegionResourceRuntimeAdoptionKind.NEW_EXECUTION_PLAN_APPLIED.value
        ):
            _fail(
                "runtime_ack_unavailable",
                runtime_ack.code,
            )
        if (
            runtime_ack.source_plan_bus_sequence != plan.plan_bus_sequence
            or runtime_ack.source_plan_payload_sha256
            != plan.plan_payload_sha256
        ):
            _fail(
                "runtime_ack_successor_plan_source_mismatch",
                "runtime ACK does not hash-bind the D3 successor plan",
            )
        if (
            runtime_ack.ack_bus_sequence is None
            or runtime_ack.ack_bus_sequence <= 0
            or runtime_ack.assignment_plan_ack_payload_sha256 is None
            or _SHA256_RE.fullmatch(
                runtime_ack.assignment_plan_ack_payload_sha256
            )
            is None
        ):
            _fail(
                "runtime_assignment_ack_reference_missing",
                "runtime ACK needs its published payload hash and bus sequence",
            )
        expected = {
            "advisory_id": applied.advisory.advisory_id,
            "advisory_version": applied.advisory_version,
            "advisory_payload_sha256": applied.advisory_payload_sha256,
            "source_plan_id": applied.source_plan_id,
            "source_plan_version": applied.source_plan_version,
            "applied_plan_id": plan.plan_id,
            "applied_plan_version": plan.plan_version,
            "owner_layer": applied.owner_layer.value,
            "owner_node_id": applied.owner_node_id,
            "authority_epoch": applied.epoch,
            "lease_expires_at_s": applied.lease_expires_at_s,
        }
        for name, expected_value in expected.items():
            if getattr(runtime_ack, name) != expected_value:
                _fail(
                    "runtime_ack_cross_binding_invalid",
                    f"{name}:{getattr(runtime_ack, name)}!={expected_value}",
                )
        if (
            runtime_ack.acknowledged_at_s is None
            or runtime_ack.acknowledged_at_s < plan.created_at_s
            or runtime_ack.acknowledged_at_s >= applied.lease_expires_at_s
        ):
            _fail(
                "runtime_ack_timestamp_invalid",
                "runtime ACK is outside the successor-plan lease",
            )

    def _validate_owner_ack(
        self,
        applied: RegionResourceAppliedRecommendation,
        plan: RegionResourceD3PlanReference,
        runtime_ack: RegionResourceRuntimeAckEvidence,
        context: RegionResourceSafeAdoptionContext,
        delivery: RegionResourceOwnerAckDelivery,
        *,
        evaluated_at_s: float,
    ) -> None:
        ack = delivery.ack
        expected_ack = build_region_resource_owner_plan_ack(
            message_id=ack.message_id,
            applied_recommendation=applied,
            d3_successor_plan=plan,
            runtime_ack=runtime_ack,
            context=context,
            acknowledged_at_s=ack.acknowledged_at_s,
            accepted=True,
        )
        if ack != expected_ack:
            _fail(
                "owner_ack_cross_binding_invalid",
                ack.message_id,
            )
        if (
            ack.acknowledged_at_s < plan.created_at_s
            or ack.acknowledged_at_s > evaluated_at_s
        ):
            _fail(
                "owner_ack_timestamp_invalid",
                ack.message_id,
            )
        validation = validate_region_resource_owner_ack_delivery(
            delivery,
            expected_ack=expected_ack,
            expected_destination_node_id=context.runtime_node_id,
            decision_timestamp_s=evaluated_at_s,
            communication_gate=self._communication_gate,
        )
        if not validation.accepted:
            _fail(
                "owner_ack_delivery_invalid",
                ",".join(validation.reason_codes),
            )

    def _validate_coalition_commits(
        self,
        applied: RegionResourceAppliedRecommendation,
        plan: RegionResourceD3PlanReference,
        context: RegionResourceSafeAdoptionContext,
        commits: tuple[RegionResourceCoalitionCommitEvidence, ...],
        *,
        evaluated_at_s: float,
    ) -> None:
        required = {
            (
                item.global_track_id,
                item.coalition_id,
                item.coalition_version,
            ): item
            for item in plan.coalition_requirements
        }
        actual = {
            (
                item.state.global_track_id,
                item.state.coalition_id,
                item.state.coalition_version,
            ): item
            for item in commits
        }
        if len(actual) != len(commits):
            _fail(
                "coalition_commit_duplicate",
                "coalition commit keys must be unique",
            )
        if set(actual) != set(required):
            _fail(
                "coalition_commit_set_mismatch",
                f"required={sorted(required)} actual={sorted(actual)}",
            )
        for key in sorted(required):
            requirement = required[key]
            evidence = actual[key]
            state = evidence.state
            if (
                state.plan_id != plan.plan_id
                or state.plan_version != plan.plan_version
                or state.epoch != applied.epoch
                or state.coordinator_id != applied.owner_node_id
                or state.lease_expires_at != applied.lease_expires_at_s
                or state.state != "executing"
                or state.required_member_ids
                != requirement.required_member_ids
                or state.acked_member_ids
                != requirement.required_member_ids
                or state.missing_member_ids
                or state.committed_at is None
                or state.executing_at is None
                or state.executing_at > evaluated_at_s
            ):
                _fail(
                    "coalition_commit_incomplete_or_stale",
                    requirement.coalition_id,
                )
            deliveries = {
                item.member_ack.resource_id: item
                for item in evidence.member_ack_deliveries
            }
            if (
                len(deliveries) != len(evidence.member_ack_deliveries)
                or set(deliveries) != set(requirement.required_member_ids)
            ):
                _fail(
                    "coalition_member_ack_set_mismatch",
                    requirement.coalition_id,
                )
            for member_id in requirement.required_member_ids:
                delivery = deliveries[member_id]
                ack = delivery.member_ack
                if (
                    delivery.authority_id != applied.owner_node_id
                    or delivery.plan_payload_sha256
                    != plan.plan_payload_sha256
                    or delivery.plan_bus_sequence != plan.plan_bus_sequence
                    or delivery.lease_expires_at_s
                    != applied.lease_expires_at_s
                    or delivery.partition_generation
                    != context.partition_generation
                    or ack.global_track_id != requirement.global_track_id
                    or ack.coalition_id != requirement.coalition_id
                    or ack.coalition_version
                    != requirement.coalition_version
                    or ack.plan_id != plan.plan_id
                    or ack.plan_version != plan.plan_version
                    or ack.epoch != applied.epoch
                    or not ack.can_execute
                    or ack.valid_until < state.lease_expires_at
                    or ack.evidence_timestamp > state.committed_at
                ):
                    _fail(
                        "coalition_member_ack_cross_binding_invalid",
                        member_id,
                    )
                validation = validate_region_resource_coalition_ack_delivery(
                    delivery,
                    expected_member_ack=ack,
                    expected_authority_id=applied.owner_node_id,
                    expected_plan_payload_sha256=plan.plan_payload_sha256,
                    expected_plan_bus_sequence=plan.plan_bus_sequence,
                    expected_lease_expires_at_s=(
                        applied.lease_expires_at_s
                    ),
                    expected_partition_generation=(
                        context.partition_generation
                    ),
                    expected_destination_node_id=applied.owner_node_id,
                    decision_timestamp_s=state.committed_at,
                    expected_message_id=delivery.message_id,
                    communication_gate=self._communication_gate,
                )
                if not validation.accepted:
                    _fail(
                        "coalition_ack_delivery_invalid",
                        ",".join(validation.reason_codes),
                    )

    @staticmethod
    def _validate_physical_window(
        applied: RegionResourceAppliedRecommendation,
        plan: RegionResourceD3PlanReference,
        runtime_ack: RegionResourceRuntimeAckEvidence,
        owner_delivery: RegionResourceOwnerAckDelivery,
        commits: tuple[RegionResourceCoalitionCommitEvidence, ...],
        window: RegionResourcePhysicalWindowEvidence,
        *,
        evaluated_at_s: float,
    ) -> None:
        if not window.available or not window.physical_execution_observed:
            _fail(
                "physical_window_unavailable",
                window.window_id,
            )
        if window.hard_constraint_violation_count != 0:
            _fail(
                "physical_window_hard_constraint_violation",
                str(window.hard_constraint_violation_count),
            )
        if (
            window.advisory_id != applied.advisory.advisory_id
            or window.advisory_version != applied.advisory_version
            or window.advisory_payload_sha256
            != applied.advisory_payload_sha256
            or window.applied_plan_id != plan.plan_id
            or window.applied_plan_version != plan.plan_version
            or window.runtime_ack_sha256
            != _canonical_sha256(runtime_ack.to_dict())
            or window.owner_ack_receipt_id
            != owner_delivery.receipt.receipt_id
        ):
            _fail(
                "physical_window_cross_binding_invalid",
                window.window_id,
            )
        expected_commits = tuple(
            sorted(item.immutable_digest for item in commits)
        )
        if window.coalition_commit_sha256 != expected_commits:
            _fail(
                "physical_window_coalition_binding_invalid",
                window.window_id,
            )
        required_start = max(
            plan.created_at_s,
            runtime_ack.acknowledged_at_s or 0.0,
            owner_delivery.receipt.arrival_timestamp_s,
            *(
                item.state.executing_at or 0.0
                for item in commits
            ),
        )
        if (
            window.window_start_s < required_start
            or window.window_end_s > evaluated_at_s
            or window.window_end_s >= applied.lease_expires_at_s
            or window.window_end_s > plan.valid_until_s
        ):
            _fail(
                "physical_window_time_scope_invalid",
                window.window_id,
            )

    def _cache_unavailable(
        self,
        *,
        input_sha256: str,
        preparation: RegionResourceSafeAdoptionPreparation,
        evaluated_at_s: float,
        stage: RegionResourceSafeAdoptionStage,
        reason: str,
        projection_available: bool = False,
        d3_plan: RegionResourceD3PlanReference | None = None,
        runtime_ack: RegionResourceRuntimeAckEvidence | None = None,
        owner_ack: RegionResourceOwnerAckDelivery | None = None,
        commits: tuple[RegionResourceCoalitionCommitEvidence, ...] = (),
        coalition_required: bool = False,
    ) -> RegionResourceSafeAdoptionEvidence:
        result = self._evidence(
            input_sha256=input_sha256,
            preparation=preparation,
            evaluated_at_s=evaluated_at_s,
            stage=stage,
            reason_codes=(reason,),
            d3_plan=d3_plan,
            runtime_ack=runtime_ack,
            owner_ack=owner_ack,
            commits=commits,
            projection_available=projection_available,
            d3_plan_available=d3_plan is not None,
            runtime_ack_available=runtime_ack is not None,
            owner_ack_available=owner_ack is not None,
            coalition_required=coalition_required,
            coalition_available=(
                not coalition_required or bool(commits)
            ),
        )
        self._final_by_input_sha256[input_sha256] = result
        return result

    @staticmethod
    def _evidence(
        *,
        input_sha256: str,
        preparation: RegionResourceSafeAdoptionPreparation,
        evaluated_at_s: float,
        stage: RegionResourceSafeAdoptionStage,
        reason_codes: tuple[str, ...],
        available: bool = False,
        d3_plan: RegionResourceD3PlanReference | None = None,
        runtime_ack: RegionResourceRuntimeAckEvidence | None = None,
        owner_ack: RegionResourceOwnerAckDelivery | None = None,
        commits: tuple[RegionResourceCoalitionCommitEvidence, ...] = (),
        physical_window: RegionResourcePhysicalWindowEvidence | None = None,
        projection_available: bool = False,
        d3_plan_available: bool = False,
        runtime_ack_available: bool = False,
        owner_ack_available: bool = False,
        coalition_required: bool = False,
        coalition_available: bool = False,
        physical_available: bool = False,
    ) -> RegionResourceSafeAdoptionEvidence:
        return RegionResourceSafeAdoptionEvidence(
            evidence_id=f"d4-a2-safe-adoption-{input_sha256}",
            available=available,
            stage=stage,
            reason_codes=reason_codes,
            preparation=preparation,
            evaluated_at_s=evaluated_at_s,
            d3_successor_plan=d3_plan,
            runtime_ack=runtime_ack,
            owner_ack_delivery=owner_ack,
            coalition_commits=commits,
            physical_window=physical_window,
            projection_available=projection_available,
            d3_successor_plan_available=d3_plan_available,
            runtime_ack_available=runtime_ack_available,
            owner_ack_available=owner_ack_available,
            coalition_commit_required=coalition_required,
            coalition_commit_available=coalition_available,
            physical_window_available=physical_available,
            identifiable_intervention_available=bool(
                preparation.applied_recommendation is not None
                and preparation.applied_recommendation.intervention_evidence
                .identifiable_intervention_available
            ),
            safe_adoption_available=available,
        )


def _build_projected_intervention_evidence(
    advisory: RegionResourceAdvisoryContract,
) -> RegionResourceProjectedInterventionEvidence:
    """Compare D3-consumable advisory fields with the current protected state."""

    baseline_regions: list[dict[str, Any]] = []
    projected_regions: list[dict[str, Any]] = []
    changed_fields: list[str] = []
    for region in sorted(advisory.regions, key=lambda item: item.region_id):
        baseline_reserve = int(region.protected_reserve_resources)
        projected_reserve = int(
            ceil(float(region.reserve_ratio) * int(region.resources_after))
        )
        baseline_regions.append(
            {
                "region_id": region.region_id,
                "resource_count": int(region.resources_before),
                "reserve_resources": baseline_reserve,
                "hold": False,
                "request_replan": False,
            }
        )
        projected_regions.append(
            {
                "region_id": region.region_id,
                "resource_count": int(region.resources_after),
                "reserve_resources": projected_reserve,
                "hold": bool(region.hold),
                "request_replan": bool(region.request_replan),
            }
        )
        prefix = f"region:{region.region_id}"
        if int(region.resource_quota_delta) != 0:
            changed_fields.append(f"{prefix}:resource_quota")
        if projected_reserve != baseline_reserve:
            changed_fields.append(f"{prefix}:reserve_resources")
        if region.hold:
            changed_fields.append(f"{prefix}:hold")
        if region.request_replan:
            changed_fields.append(f"{prefix}:request_replan")

    projected_transfers = [
        {
            "source_region_id": transfer.source_region_id,
            "target_region_id": transfer.target_region_id,
            "resource_count": int(transfer.resource_count),
            "edge_id": transfer.edge_id,
            "expected_transfer_time_s": float(
                transfer.expected_transfer_time_s
            ),
        }
        for transfer in sorted(
            advisory.transfers,
            key=lambda item: (
                item.source_region_id,
                item.target_region_id,
                item.edge_id,
            ),
        )
    ]
    changed_fields.extend(
        (
            "transfer:"
            f"{transfer['source_region_id']}->"
            f"{transfer['target_region_id']}:"
            f"{transfer['edge_id']}"
        )
        for transfer in projected_transfers
    )
    baseline_payload = {
        "regions": baseline_regions,
        "transfers": [],
    }
    projected_payload = {
        "regions": projected_regions,
        "transfers": projected_transfers,
    }
    baseline_sha256 = _canonical_sha256(baseline_payload)
    projected_sha256 = _canonical_sha256(projected_payload)
    fields_value = tuple(sorted(set(changed_fields)))
    available = bool(fields_value)
    reasons = (
        ()
        if available
        else ("no_d3_consumable_regional_intervention",)
    )
    identity_payload = {
        "schema": REGION_RESOURCE_PROJECTED_INTERVENTION_SCHEMA,
        "identifiable_intervention_available": available,
        "intervention_fields": fields_value,
        "baseline_payload_sha256": baseline_sha256,
        "projected_payload_sha256": projected_sha256,
        "reason_codes": reasons,
    }
    return RegionResourceProjectedInterventionEvidence(
        intervention_id=(
            "d4-a2-intervention-" + _canonical_sha256(identity_payload)
        ),
        identifiable_intervention_available=available,
        intervention_fields=fields_value,
        baseline_payload_sha256=baseline_sha256,
        projected_payload_sha256=projected_sha256,
        reason_codes=reasons,
    )


def _runtime_ack_from_value(value: Any) -> RegionResourceRuntimeAckEvidence:
    if isinstance(value, RegionResourceRuntimeAckEvidence):
        return value
    mapping = _strict_mapping(value, "runtime_ack")
    _require_exact_keys(
        RegionResourceRuntimeAckEvidence, mapping, "runtime_ack"
    )
    payload = dict(mapping)
    payload["rejection_reasons"] = tuple(
        payload.get("rejection_reasons", ())
    )
    return RegionResourceRuntimeAckEvidence(**payload)


def _rejected_preparation(
    reason: str,
) -> RegionResourceSafeAdoptionPreparation:
    return RegionResourceSafeAdoptionPreparation(
        available=False,
        stage=RegionResourceSafeAdoptionStage.CANDIDATE_REJECTED,
        reason_codes=(reason,),
    )


def _coalition_requirement_key(
    item: RegionResourceCoalitionRequirement,
) -> tuple[str, str, int]:
    return (
        item.global_track_id,
        item.coalition_id,
        item.coalition_version,
    )


def _fail(code: str, detail: str) -> None:
    raise RegionResourceSafeAdoptionError(code, detail)


def _assert_truth_and_outcome_free(value: Any) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        if is_dataclass(item):
            pending.append(asdict(item))
            continue
        if isinstance(item, Mapping):
            forbidden = {
                str(key).strip().lower()
                for key in item
                if str(key).strip().lower() in _FORBIDDEN_ONLINE_KEYS
                or str(key).strip().lower().startswith("truth_")
                or str(key).strip().lower().startswith("ground_truth_")
            }
            if forbidden:
                _fail(
                    "truth_or_outcome_field_rejected",
                    ",".join(sorted(forbidden)),
                )
            pending.extend(item.values())
            continue
        if isinstance(item, (list, tuple, set)):
            pending.extend(item)


def _strict_dataclass_from_mapping(
    cls: type[Any], value: Any, name: str
) -> Any:
    mapping = _strict_mapping(value, name)
    _require_exact_keys(cls, mapping, name)
    return cls(**dict(mapping))


def _require_exact_keys(
    cls: type[Any], mapping: Mapping[str, Any], name: str
) -> None:
    expected = {item.name for item in fields(cls)}
    _require_exact_named_keys(mapping, expected, name)


def _require_exact_named_keys(
    mapping: Mapping[str, Any],
    expected: set[str],
    name: str,
) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"{name} fields mismatch missing={missing} extra={extra}"
        )


def _strict_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        if name not in value:
            raise ValueError(f"delivered message is missing {name}")
        return value[name]
    if not hasattr(value, name):
        raise ValueError(f"delivered message is missing {name}")
    return getattr(value, name)


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(
        value, Sequence
    ):
        raise TypeError(f"{name} must be a sequence")
    return value


def _required_text(value: Any, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} must not be empty")
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result


def _unique_text(values: Sequence[Any], name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be a sequence")
    return tuple(
        sorted(
            {
                _required_text(item, name)
                for item in values
            }
        )
    )


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a non-negative integer") from error
    try:
        exact = float(value) == float(result)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a non-negative integer") from error
    if result < 0 or not exact:
        raise ValueError(f"{name} must be a non-negative integer")
    return result


def _positive_int(value: Any, name: str) -> int:
    result = _nonnegative_int(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _finite_nonnegative(value: Any, name: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be finite and non-negative")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be finite and non-negative") from error
    if not isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _sha256_text(value: Any, name: str) -> str:
    result = _required_text(value, name)
    if _SHA256_RE.fullmatch(result) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return result


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            _jsonable(value),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted((_jsonable(item) for item in value), key=repr)
    return value
