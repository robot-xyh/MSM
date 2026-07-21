"""Fail-closed consumer for main-owned assignment-plan runtime ACK evidence.

The consumer deliberately depends only on D3 contracts and common Python/NumPy
types. It verifies detached bus-envelope mappings and returns immutable
evidence; it never publishes or mutates an AssignmentPlan.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Any

import numpy as np

from .models import (
    ASSIGNMENT_PLAN_SCHEMA_V1,
    ASSIGNMENT_PLAN_SCHEMA_V2,
    Assignment,
    AssignmentPlan,
)


ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1 = (
    "scalable3d-assignment-plan-runtime-ack-v1"
)
D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1 = (
    "d3_assignment_plan_runtime_ack_evidence_v1"
)
D3_ASSIGNMENT_PLAN_TOPIC = "modules.d3.assignment_plan"
D7_GUIDANCE_COMMAND_TOPIC = "modules.d7.guidance_commands"

_ASSIGNMENT_PLAN_CLASS_IDENTITIES = frozenset(
    {
        ("d3_assignment_planner.models", "AssignmentPlan"),
        (
            "research_modules.d3_assignment_planner.src."
            "d3_assignment_planner.models",
            "AssignmentPlan",
        ),
        (
            "research_modules.d3_assignment_planner."
            "d3_assignment_planner.models",
            "AssignmentPlan",
        ),
    }
)
_ASSIGNMENT_CLASS_IDENTITIES = frozenset(
    {
        ("d3_assignment_planner.models", "Assignment"),
        (
            "research_modules.d3_assignment_planner.src."
            "d3_assignment_planner.models",
            "Assignment",
        ),
        (
            "research_modules.d3_assignment_planner."
            "d3_assignment_planner.models",
            "Assignment",
        ),
    }
)
_ASSIGNMENT_PLAN_FIELD_NAMES = frozenset(
    item.name for item in fields(AssignmentPlan)
)
_ASSIGNMENT_FIELD_NAMES = frozenset(item.name for item in fields(Assignment))
_SUPPORTED_ASSIGNMENT_PLAN_SCHEMAS = frozenset(
    {ASSIGNMENT_PLAN_SCHEMA_V1, ASSIGNMENT_PLAN_SCHEMA_V2}
)

_ENVELOPE_FIELDS = frozenset(
    {"sequence", "topic", "source", "timestamp", "schema_version", "payload"}
)
_D3_PLAN_PAYLOAD_FIELDS = frozenset(
    {
        "timestamp",
        "plan_id",
        "plan_version",
        "created_at",
        "assignment_count",
        "target_count",
        "resource_count",
        "assignments",
        "unassigned_global_track_ids",
        "solver_name",
        "metadata",
    }
)
_D3_ASSIGNMENT_FIELDS = frozenset(
    {
        "resource_id",
        "global_track_id",
        "coalition_id",
        "coalition_version",
        "member_role",
        "owner_node_id",
        "regional_owner_layer",
        "regional_region_id",
        "regional_epoch",
        "regional_commit_mode",
    }
)
_D7_PAYLOAD_FIELDS = frozenset(
    {"timestamp", "command_count", "mode_counts", "commands"}
)
_D7_COMMAND_REQUIRED_FIELDS = frozenset(
    {
        "resource_id",
        "global_track_id",
        "plan_id",
        "plan_version",
        "mode",
        "gate_reason",
    }
)
_D7_COMMAND_ALLOWED_FIELDS = frozenset(
    {
        *_D7_COMMAND_REQUIRED_FIELDS,
        "acceleration_ned_mps2",
        "command_norm_mps2",
        "visual_switch_allowed",
    }
)
_ACK_FIELDS = frozenset(
    {
        "decision_id",
        "ack_timestamp",
        "plan_id",
        "plan_version",
        "plan_created_at",
        "plan_schema_version",
        "source_plan_bus_sequence",
        "source_plan_payload_sha256",
        "source_guidance_bus_sequence",
        "source_guidance_payload_sha256",
        "accepted",
        "status_code",
        "assignment_count",
        "binding_ack_count",
        "fully_bound_to_guidance",
        "control_applied_binding_count",
        "held_binding_count",
        "active_plan_owner",
        "owner_node_id",
        "authority_epoch",
        "lease_expires_at_s",
        "d3_learning_evidence",
        "d4_regional_hint_evidence",
        "binding_acks",
        "physical_outcome_available",
        "reward_available",
    }
)
_BINDING_ACK_FIELDS = frozenset(
    {
        "resource_id",
        "global_track_id",
        "coalition_id",
        "coalition_version",
        "member_role",
        "guidance_command_present",
        "guidance_mode",
        "guidance_gate_reason",
        "control_applied_to_world",
        "held",
    }
)
_LEARNING_EVIDENCE_FIELDS = frozenset(
    {
        "mode",
        "applied",
        "shadow_only",
        "bundle_loaded",
        "fallback_reason",
        "model_fingerprint",
    }
)
_REGIONAL_EVIDENCE_FIELDS = frozenset(
    {
        "considered",
        "applied",
        "rejected",
        "fallback_reason",
        "advisory_id",
        "advisory_version",
        "source_plan_id",
        "source_plan_version",
    }
)
_HEX_DIGITS = frozenset("0123456789abcdef")


class AssignmentPlanRuntimeAckError(ValueError):
    """Stable fail-closed error for an invalid runtime acknowledgement."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        self.reason = self.code
        super().__init__(message or self.code)


@dataclass(frozen=True)
class RuntimePlanBindingAck:
    """One immutable D3 binding and its same-tick D7 consumption evidence."""

    resource_id: str
    global_track_id: str
    coalition_id: str | None
    coalition_version: int | None
    member_role: str
    guidance_command_present: bool
    guidance_mode: str | None
    guidance_gate_reason: str | None
    control_applied_to_world: bool
    held: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "global_track_id": self.global_track_id,
            "coalition_id": self.coalition_id,
            "coalition_version": self.coalition_version,
            "member_role": self.member_role,
            "guidance_command_present": self.guidance_command_present,
            "guidance_mode": self.guidance_mode,
            "guidance_gate_reason": self.guidance_gate_reason,
            "control_applied_to_world": self.control_applied_to_world,
            "held": self.held,
        }


@dataclass(frozen=True)
class D3RuntimeLearningEvidence:
    """Learning metadata copied from the verified source plan."""

    mode: str | None
    applied: bool | None
    shadow_only: bool | None
    bundle_loaded: bool | None
    fallback_reason: str | None
    model_fingerprint: str | None
    runtime_applied_ack_available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "applied": self.applied,
            "shadow_only": self.shadow_only,
            "bundle_loaded": self.bundle_loaded,
            "fallback_reason": self.fallback_reason,
            "model_fingerprint": self.model_fingerprint,
            "runtime_applied_ack_available": (
                self.runtime_applied_ack_available
            ),
        }


@dataclass(frozen=True)
class D4RegionalHintRuntimeEvidence:
    """Regional hint provenance copied from the verified source plan."""

    considered: bool | None
    applied: bool | None
    rejected: bool | None
    fallback_reason: str | None
    advisory_id: str | None
    advisory_version: int | None
    source_plan_id: str | None
    source_plan_version: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "considered": self.considered,
            "applied": self.applied,
            "rejected": self.rejected,
            "fallback_reason": self.fallback_reason,
            "advisory_id": self.advisory_id,
            "advisory_version": self.advisory_version,
            "source_plan_id": self.source_plan_id,
            "source_plan_version": self.source_plan_version,
        }


@dataclass(frozen=True)
class AssignmentPlanRuntimeAckEvidence:
    """Verified, serializable evidence returned to an offline D6 join."""

    ack_envelope_schema: str
    decision_id: str
    ack_timestamp: float
    plan_id: str
    plan_version: int
    plan_created_at: float
    plan_schema_version: str
    source_plan_bus_sequence: int
    source_plan_payload_sha256: str
    source_guidance_bus_sequence: int | None
    source_guidance_payload_sha256: str | None
    accepted: bool
    status_code: str
    assignment_count: int
    binding_ack_count: int
    fully_bound_to_guidance: bool
    control_applied_binding_count: int
    held_binding_count: int
    active_plan_owner: str | None
    owner_node_id: str | None
    authority_epoch: int | None
    lease_expires_at_s: float | None
    d3_learning_evidence: D3RuntimeLearningEvidence
    d4_regional_hint_evidence: D4RegionalHintRuntimeEvidence
    binding_acks: tuple[RuntimePlanBindingAck, ...]
    physical_outcome_available: bool
    reward_available: bool

    @property
    def runtime_learning_applied_ack_available(self) -> bool:
        return self.d3_learning_evidence.runtime_applied_ack_available

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
            "status": "verified",
            "ack_envelope_schema": self.ack_envelope_schema,
            "decision_id": self.decision_id,
            "ack_timestamp": self.ack_timestamp,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "plan_created_at": self.plan_created_at,
            "plan_schema_version": self.plan_schema_version,
            "source_plan_bus_sequence": self.source_plan_bus_sequence,
            "source_plan_payload_sha256": self.source_plan_payload_sha256,
            "source_guidance_bus_sequence": self.source_guidance_bus_sequence,
            "source_guidance_payload_sha256": (
                self.source_guidance_payload_sha256
            ),
            "accepted": self.accepted,
            "status_code": self.status_code,
            "assignment_count": self.assignment_count,
            "binding_ack_count": self.binding_ack_count,
            "fully_bound_to_guidance": self.fully_bound_to_guidance,
            "control_applied_binding_count": (
                self.control_applied_binding_count
            ),
            "held_binding_count": self.held_binding_count,
            "active_plan_owner": self.active_plan_owner,
            "owner_node_id": self.owner_node_id,
            "authority_epoch": self.authority_epoch,
            "lease_expires_at_s": self.lease_expires_at_s,
            "d3_learning_evidence": self.d3_learning_evidence.to_dict(),
            "d4_regional_hint_evidence": (
                self.d4_regional_hint_evidence.to_dict()
            ),
            "binding_acks": [item.to_dict() for item in self.binding_acks],
            "physical_outcome_available": self.physical_outcome_available,
            "reward_available": self.reward_available,
            "assignment_plan_mutated": False,
        }


@dataclass(frozen=True)
class _SourceEnvelope:
    sequence: int
    topic: str
    source: str
    timestamp: float
    schema_version: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class _ExpectedBinding:
    resource_id: str
    global_track_id: str
    coalition_id: str | None
    coalition_version: int | None
    member_role: str
    owner_node_id: str | None
    regional_owner_layer: str | None
    regional_region_id: str | None
    regional_epoch: int | None
    regional_commit_mode: str | None

    @classmethod
    def from_assignment(cls, assignment: Any) -> "_ExpectedBinding":
        _validate_d3_dataclass_identity(
            assignment,
            allowed_identities=_ASSIGNMENT_CLASS_IDENTITIES,
            expected_fields=_ASSIGNMENT_FIELD_NAMES,
            code="expected_assignment_type_invalid",
            context="expected assignment",
        )
        metadata = _mapping(assignment.metadata, "expected_assignment_metadata")
        return cls(
            resource_id=_required_text(
                assignment.resource_id, "expected assignment resource_id"
            ),
            global_track_id=_required_text(
                assignment.target_id, "expected assignment target_id"
            ),
            coalition_id=_optional_text(
                assignment.coalition_id, "expected assignment coalition_id"
            ),
            coalition_version=_optional_nonnegative_int(
                assignment.coalition_version,
                "expected assignment coalition_version",
            ),
            member_role=_required_text(
                assignment.member_role, "expected assignment member_role"
            ),
            owner_node_id=_optional_text(
                metadata.get("owner_node_id"), "expected owner_node_id"
            ),
            regional_owner_layer=_optional_text(
                metadata.get("regional_owner_layer"),
                "expected regional_owner_layer",
            ),
            regional_region_id=_optional_text(
                metadata.get("regional_region_id"),
                "expected regional_region_id",
            ),
            regional_epoch=_optional_nonnegative_int(
                metadata.get("regional_epoch"), "expected regional_epoch"
            ),
            regional_commit_mode=_optional_text(
                metadata.get("regional_commit_mode"),
                "expected regional_commit_mode",
            ),
        )

    def source_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "global_track_id": self.global_track_id,
            "coalition_id": self.coalition_id,
            "coalition_version": self.coalition_version,
            "member_role": self.member_role,
            "owner_node_id": self.owner_node_id,
            "regional_owner_layer": self.regional_owner_layer,
            "regional_region_id": self.regional_region_id,
            "regional_epoch": self.regional_epoch,
            "regional_commit_mode": self.regional_commit_mode,
        }


def canonical_runtime_payload_sha256(value: Any) -> str:
    """Return the SHA-256 used by main for runtime source payloads."""

    try:
        encoded = json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AssignmentPlanRuntimeAckError(
            "payload_not_canonical_json",
            "runtime payload is not finite canonical JSON",
        ) from exc
    return sha256(encoded).hexdigest()


def validate_assignment_plan_runtime_ack(
    *,
    envelope_schema: str,
    acknowledgement: Mapping[str, Any],
    d3_source_publication: Mapping[str, Any],
    expected_plan: AssignmentPlan,
    d7_source_publication: Mapping[str, Any] | None = None,
) -> AssignmentPlanRuntimeAckEvidence:
    """Verify one main runtime ACK against its D3/D7 source publications.

    Source publications use the mapping returned by main's
    VersionedEnvelope.to_dict(). Requiring the complete source envelope makes
    the bus sequence independently checkable.
    """

    schema = _required_text(envelope_schema, "ACK envelope schema")
    if schema != ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1:
        _fail(
            "ack_envelope_schema_mismatch",
            f"unsupported assignment runtime ACK schema: {schema}",
        )
    ack = _strict_mapping(
        acknowledgement,
        required_fields=_ACK_FIELDS,
        allowed_fields=_ACK_FIELDS,
        code="ack_fields_mismatch",
        context="assignment runtime ACK",
    )
    expected_bindings = _validate_expected_plan(expected_plan)
    d3_source = _parse_source_envelope(
        d3_source_publication,
        topic=D3_ASSIGNMENT_PLAN_TOPIC,
        source="D3",
        code_prefix="source_plan",
    )
    d3_payload = _validate_source_plan_payload(
        d3_source,
        expected_plan=expected_plan,
        expected_bindings=expected_bindings,
    )

    plan_id = _required_text(ack["plan_id"], "ACK plan_id")
    if plan_id != expected_plan.plan_id:
        _fail("plan_id_mismatch", "ACK plan_id does not match expected plan")
    plan_version = _positive_int(ack["plan_version"], "ACK plan_version")
    _require_plan_version(plan_version, expected_plan.version, "ACK")
    decision_id = _required_text(ack["decision_id"], "ACK decision_id")
    if decision_id != f"{expected_plan.plan_id}:v{expected_plan.version}":
        _fail("decision_id_mismatch", "ACK decision_id is not canonical")
    ack_timestamp = _finite_nonnegative(ack["ack_timestamp"], "ACK timestamp")
    if ack_timestamp != d3_source.timestamp:
        _fail(
            "ack_timestamp_mismatch",
            "ACK timestamp must equal the same-tick D3 publication timestamp",
        )
    plan_created_at = _finite_nonnegative(
        ack["plan_created_at"], "ACK plan_created_at"
    )
    if plan_created_at != float(expected_plan.created_at):
        _fail(
            "plan_created_at_mismatch",
            "ACK plan creation time does not match expected plan",
        )
    if plan_created_at > ack_timestamp:
        _fail(
            "plan_created_after_ack",
            "ACK cannot precede the expected plan creation time",
        )
    plan_schema = _required_text(
        ack["plan_schema_version"], "ACK plan_schema_version"
    )
    if plan_schema != expected_plan.plan_schema:
        _fail(
            "plan_schema_mismatch",
            "ACK plan schema does not match expected AssignmentPlan",
        )

    source_plan_sequence = _positive_int(
        ack["source_plan_bus_sequence"], "ACK source plan bus sequence"
    )
    if source_plan_sequence != d3_source.sequence:
        _fail(
            "source_plan_sequence_mismatch",
            "ACK source plan sequence does not match source envelope",
        )
    source_plan_hash = _sha256_text(
        ack["source_plan_payload_sha256"], "ACK source plan payload SHA-256"
    )
    computed_plan_hash = canonical_runtime_payload_sha256(d3_source.payload)
    if source_plan_hash != computed_plan_hash:
        _fail(
            "source_plan_payload_sha256_mismatch",
            "ACK source plan payload SHA-256 does not match canonical payload",
        )

    commands = _validate_guidance_source(
        d7_source_publication,
        acknowledgement=ack,
        expected_plan=expected_plan,
        ack_timestamp=ack_timestamp,
        d3_source_sequence=d3_source.sequence,
    )
    binding_acks = _parse_and_validate_binding_acks(
        ack["binding_acks"],
        expected_bindings=expected_bindings,
        commands=commands,
    )

    assignment_count = _nonnegative_int(
        ack["assignment_count"], "ACK assignment_count"
    )
    if assignment_count != len(expected_bindings):
        _fail(
            "assignment_count_mismatch",
            "ACK assignment_count does not match expected AssignmentPlan",
        )
    guidance_present_count = sum(
        item.guidance_command_present for item in binding_acks
    )
    binding_ack_count = _nonnegative_int(
        ack["binding_ack_count"], "ACK binding_ack_count"
    )
    if binding_ack_count != guidance_present_count:
        _fail(
            "binding_ack_count_mismatch",
            "ACK binding count does not match guidance-present rows",
        )
    fully_bound = _strict_bool(
        ack["fully_bound_to_guidance"], "ACK fully_bound_to_guidance"
    )
    if fully_bound != (guidance_present_count == len(expected_bindings)):
        _fail(
            "fully_bound_statistic_mismatch",
            "ACK fully-bound statistic is inconsistent",
        )
    applied_count = sum(item.control_applied_to_world for item in binding_acks)
    reported_applied_count = _nonnegative_int(
        ack["control_applied_binding_count"],
        "ACK control_applied_binding_count",
    )
    if reported_applied_count != applied_count:
        _fail(
            "control_applied_count_mismatch",
            "ACK control-applied count is inconsistent",
        )
    held_count = sum(item.held for item in binding_acks)
    reported_held_count = _nonnegative_int(
        ack["held_binding_count"], "ACK held_binding_count"
    )
    if reported_held_count != held_count:
        _fail("held_count_mismatch", "ACK held count is inconsistent")

    accepted = _strict_bool(ack["accepted"], "ACK accepted")
    if not accepted:
        _fail(
            "runtime_plan_not_accepted",
            "this evidence contract only admits accepted runtime plans",
        )
    status_code = _required_text(ack["status_code"], "ACK status_code")
    if status_code != "accepted_by_main_runtime":
        _fail(
            "runtime_status_code_mismatch",
            "accepted runtime ACK has an unsupported status code",
        )

    metadata = _mapping(d3_payload["metadata"], "D3 plan metadata")
    active_plan_owner = _metadata_text_ack(
        ack, metadata, "active_plan_owner"
    )
    owner_node_id = _metadata_text_ack(ack, metadata, "owner_node_id")
    authority_epoch = _metadata_int_ack(ack, metadata, "authority_epoch")
    lease_expires_at_s = _metadata_time_ack(
        ack, metadata, "lease_expires_at_s"
    )
    if (
        lease_expires_at_s is not None
        and lease_expires_at_s <= ack_timestamp
    ):
        _fail(
            "runtime_plan_lease_expired",
            "accepted runtime plan lease must extend beyond the ACK timestamp",
        )

    learning_evidence = _parse_learning_evidence(
        ack["d3_learning_evidence"], metadata
    )
    regional_evidence = _parse_regional_evidence(
        ack["d4_regional_hint_evidence"], metadata
    )

    physical_available = _strict_bool(
        ack["physical_outcome_available"],
        "ACK physical_outcome_available",
    )
    if physical_available:
        _fail(
            "physical_outcome_sidecar_required",
            "runtime ACK cannot self-assert a physical outcome",
        )
    reward_available = _strict_bool(
        ack["reward_available"], "ACK reward_available"
    )
    if reward_available:
        _fail(
            "reward_sidecar_required",
            "runtime ACK cannot self-assert an attributed reward",
        )

    guidance_sequence = _optional_positive_int(
        ack["source_guidance_bus_sequence"],
        "ACK source guidance bus sequence",
    )
    guidance_hash = _optional_sha256_text(
        ack["source_guidance_payload_sha256"],
        "ACK source guidance payload SHA-256",
    )
    return AssignmentPlanRuntimeAckEvidence(
        ack_envelope_schema=schema,
        decision_id=decision_id,
        ack_timestamp=ack_timestamp,
        plan_id=plan_id,
        plan_version=plan_version,
        plan_created_at=plan_created_at,
        plan_schema_version=plan_schema,
        source_plan_bus_sequence=source_plan_sequence,
        source_plan_payload_sha256=source_plan_hash,
        source_guidance_bus_sequence=guidance_sequence,
        source_guidance_payload_sha256=guidance_hash,
        accepted=accepted,
        status_code=status_code,
        assignment_count=assignment_count,
        binding_ack_count=binding_ack_count,
        fully_bound_to_guidance=fully_bound,
        control_applied_binding_count=reported_applied_count,
        held_binding_count=reported_held_count,
        active_plan_owner=active_plan_owner,
        owner_node_id=owner_node_id,
        authority_epoch=authority_epoch,
        lease_expires_at_s=lease_expires_at_s,
        d3_learning_evidence=learning_evidence,
        d4_regional_hint_evidence=regional_evidence,
        binding_acks=binding_acks,
        physical_outcome_available=False,
        reward_available=False,
    )


def _validate_expected_plan(plan: Any) -> tuple[_ExpectedBinding, ...]:
    _validate_d3_dataclass_identity(
        plan,
        allowed_identities=_ASSIGNMENT_PLAN_CLASS_IDENTITIES,
        expected_fields=_ASSIGNMENT_PLAN_FIELD_NAMES,
        code="expected_plan_type_invalid",
        context="expected plan",
    )
    _required_text(plan.plan_id, "expected plan_id")
    _positive_int(plan.version, "expected plan version")
    plan_schema = _required_text(plan.plan_schema, "expected plan schema")
    if plan_schema not in _SUPPORTED_ASSIGNMENT_PLAN_SCHEMAS:
        _fail(
            "expected_plan_schema_unsupported",
            f"unsupported D3 AssignmentPlan schema: {plan_schema}",
        )
    _finite_nonnegative(plan.created_at, "expected plan created_at")
    _required_text(plan.solver_name, "expected plan solver_name")
    resource_count = _nonnegative_int(plan.resource_count, "expected resource_count")
    target_count = _nonnegative_int(plan.target_count, "expected target_count")
    bindings = tuple(
        _ExpectedBinding.from_assignment(item) for item in plan.assignments
    )
    resource_ids = [item.resource_id for item in bindings]
    pairs = [(item.resource_id, item.global_track_id) for item in bindings]
    if len(resource_ids) != len(set(resource_ids)) or len(pairs) != len(set(pairs)):
        _fail(
            "expected_plan_duplicate_binding",
            "expected AssignmentPlan contains a duplicate executable binding",
        )
    if resource_count < len(resource_ids):
        _fail(
            "expected_plan_resource_count_invalid",
            "expected resource_count is smaller than assigned resources",
        )
    unassigned = tuple(
        _required_text(item, "expected unassigned global_track_id")
        for item in plan.unassigned_target_ids
    )
    incomplete = tuple(
        _required_text(item, "expected incomplete global_track_id")
        for item in plan.incomplete_target_ids
    )
    if len(unassigned) != len(set(unassigned)):
        _fail(
            "expected_plan_duplicate_unassigned_target",
            "expected plan contains duplicate unassigned target ids",
        )
    all_targets = {
        *(item.global_track_id for item in bindings),
        *unassigned,
        *incomplete,
    }
    if target_count != len(all_targets):
        _fail(
            "expected_plan_target_count_invalid",
            "expected target_count does not match target inventory",
        )
    if set(unassigned) & {item.global_track_id for item in bindings}:
        _fail(
            "expected_plan_assignment_inventory_invalid",
            "one expected target cannot be both assigned and unassigned",
        )
    canonical_runtime_payload_sha256(plan.metadata)
    return bindings


def _validate_d3_dataclass_identity(
    value: Any,
    *,
    allowed_identities: frozenset[tuple[str, str]],
    expected_fields: frozenset[str],
    code: str,
    context: str,
) -> None:
    cls = type(value)
    identity = (str(cls.__module__), str(cls.__name__))
    if identity not in allowed_identities:
        _fail(
            code,
            f"{context} has unsupported D3 class identity: "
            f"{identity[0]}.{identity[1]}",
        )
    if not is_dataclass(value) or isinstance(value, type):
        _fail(code, f"{context} must be a D3 dataclass instance")
    actual_fields = frozenset(item.name for item in fields(value))
    if actual_fields != expected_fields:
        _fail(
            code,
            f"{context} dataclass fields do not match the D3 contract",
        )


def _validate_source_plan_payload(
    envelope: _SourceEnvelope,
    *,
    expected_plan: AssignmentPlan,
    expected_bindings: tuple[_ExpectedBinding, ...],
) -> Mapping[str, Any]:
    if envelope.schema_version != expected_plan.plan_schema:
        _fail(
            "source_plan_schema_mismatch",
            "D3 source envelope schema does not match expected plan schema",
        )
    payload = _strict_mapping(
        envelope.payload,
        required_fields=_D3_PLAN_PAYLOAD_FIELDS,
        allowed_fields=_D3_PLAN_PAYLOAD_FIELDS,
        code="source_plan_payload_fields_mismatch",
        context="D3 source plan payload",
    )
    timestamp = _finite_nonnegative(payload["timestamp"], "source plan timestamp")
    if timestamp != envelope.timestamp:
        _fail(
            "source_plan_timestamp_mismatch",
            "D3 payload timestamp does not match its source envelope",
        )
    if _required_text(payload["plan_id"], "source plan_id") != expected_plan.plan_id:
        _fail(
            "source_plan_id_mismatch",
            "D3 source plan_id does not match expected plan",
        )
    version = _positive_int(payload["plan_version"], "source plan_version")
    _require_plan_version(version, expected_plan.version, "source plan")
    created_at = _finite_nonnegative(payload["created_at"], "source plan created_at")
    if created_at != float(expected_plan.created_at):
        _fail(
            "source_plan_created_at_mismatch",
            "D3 source creation time does not match expected plan",
        )
    source_assignment_count = _nonnegative_int(
        payload["assignment_count"], "source assignment_count"
    )
    if source_assignment_count != len(expected_bindings):
        _fail(
            "source_assignment_count_mismatch",
            "D3 source assignment count does not match expected plan",
        )
    if _nonnegative_int(payload["target_count"], "source target_count") != int(
        expected_plan.target_count
    ):
        _fail(
            "source_target_count_mismatch",
            "D3 source target count does not match expected plan",
        )
    if _nonnegative_int(payload["resource_count"], "source resource_count") != int(
        expected_plan.resource_count
    ):
        _fail(
            "source_resource_count_mismatch",
            "D3 source resource count does not match expected plan",
        )
    if _required_text(payload["solver_name"], "source solver_name") != str(
        expected_plan.solver_name
    ):
        _fail(
            "source_solver_name_mismatch",
            "D3 source solver does not match expected plan",
        )
    raw_unassigned = _sequence(
        payload["unassigned_global_track_ids"],
        "source unassigned_global_track_ids",
    )
    unassigned = tuple(
        _required_text(item, "source unassigned global_track_id")
        for item in raw_unassigned
    )
    if unassigned != tuple(expected_plan.unassigned_target_ids):
        _fail(
            "source_unassigned_inventory_mismatch",
            "D3 source unassigned inventory does not match expected plan",
        )
    source_metadata = _mapping(payload["metadata"], "source D3 plan metadata")
    if _canonical_json(source_metadata) != _canonical_json(expected_plan.metadata):
        _fail(
            "source_plan_metadata_mismatch",
            "D3 source metadata does not match expected plan",
        )

    raw_assignments = _sequence(payload["assignments"], "source assignments")
    source_bindings = tuple(
        _parse_source_assignment(item, index=index)
        for index, item in enumerate(raw_assignments)
    )
    _match_binding_inventory(
        source_bindings,
        expected_bindings,
        prefix="source_plan",
    )
    if tuple(item.source_dict() for item in source_bindings) != tuple(
        item.source_dict() for item in expected_bindings
    ):
        _fail(
            "source_assignment_order_mismatch",
            "D3 source assignment order does not match expected plan",
        )
    return payload


def _validate_guidance_source(
    value: Mapping[str, Any] | None,
    *,
    acknowledgement: Mapping[str, Any],
    expected_plan: AssignmentPlan,
    ack_timestamp: float,
    d3_source_sequence: int,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    ack_sequence = _optional_positive_int(
        acknowledgement["source_guidance_bus_sequence"],
        "ACK source guidance bus sequence",
    )
    ack_hash = _optional_sha256_text(
        acknowledgement["source_guidance_payload_sha256"],
        "ACK source guidance payload SHA-256",
    )
    if (ack_sequence is None) != (ack_hash is None):
        _fail(
            "source_guidance_reference_incomplete",
            "guidance sequence and payload SHA-256 must be available together",
        )
    if value is None:
        if ack_sequence is not None:
            _fail(
                "source_guidance_publication_missing",
                "ACK references a D7 source publication that was not supplied",
            )
        return {}
    if ack_sequence is None:
        _fail(
            "source_guidance_reference_missing",
            "D7 source publication requires sequence and payload SHA-256",
        )
    source = _parse_source_envelope(
        value,
        topic=D7_GUIDANCE_COMMAND_TOPIC,
        source="D7",
        code_prefix="source_guidance",
    )
    if source.sequence <= d3_source_sequence:
        _fail(
            "source_guidance_sequence_order_invalid",
            "same-tick D7 source sequence must follow the D3 plan sequence",
        )
    if source.sequence != ack_sequence:
        _fail(
            "source_guidance_sequence_mismatch",
            "ACK guidance sequence does not match source envelope",
        )
    if source.timestamp != ack_timestamp:
        _fail(
            "source_guidance_timestamp_mismatch",
            "D7 source must belong to the same scheduler tick as the ACK",
        )
    computed_hash = canonical_runtime_payload_sha256(source.payload)
    if ack_hash != computed_hash:
        _fail(
            "source_guidance_payload_sha256_mismatch",
            "ACK guidance payload SHA-256 does not match canonical payload",
        )
    payload = _strict_mapping(
        source.payload,
        required_fields={"timestamp", "commands"},
        allowed_fields=_D7_PAYLOAD_FIELDS,
        code="source_guidance_payload_fields_mismatch",
        context="D7 source guidance payload",
    )
    payload_timestamp = _finite_nonnegative(
        payload["timestamp"], "D7 payload timestamp"
    )
    if payload_timestamp != source.timestamp:
        _fail(
            "source_guidance_payload_timestamp_mismatch",
            "D7 payload timestamp does not match source envelope",
        )
    raw_commands = _sequence(payload["commands"], "D7 source commands")
    commands: dict[tuple[str, str], Mapping[str, Any]] = {}
    modes: Counter[str] = Counter()
    for index, raw in enumerate(raw_commands):
        command = _strict_mapping(
            raw,
            required_fields=_D7_COMMAND_REQUIRED_FIELDS,
            allowed_fields=_D7_COMMAND_ALLOWED_FIELDS,
            code="source_guidance_command_fields_mismatch",
            context=f"D7 source command {index}",
        )
        resource_id = _required_text(command["resource_id"], "D7 resource_id")
        global_track_id = _required_text(
            command["global_track_id"], "D7 global_track_id"
        )
        if _required_text(command["plan_id"], "D7 plan_id") != expected_plan.plan_id:
            _fail(
                "source_guidance_plan_id_mismatch",
                "D7 source command references another plan id",
            )
        version = _positive_int(command["plan_version"], "D7 plan_version")
        _require_plan_version(version, expected_plan.version, "D7 command")
        mode = _required_text(command["mode"], "D7 guidance mode")
        _optional_text(command["gate_reason"], "D7 guidance gate_reason")
        key = (resource_id, global_track_id)
        if key in commands or any(item[0] == resource_id for item in commands):
            _fail(
                "duplicate_guidance_binding",
                "D7 source contains a duplicate resource binding",
            )
        commands[key] = command
        modes[mode] += 1
    if "command_count" in payload:
        command_count = _nonnegative_int(
            payload["command_count"], "D7 command_count"
        )
        if command_count != len(commands):
            _fail(
                "source_guidance_command_count_mismatch",
                "D7 command_count does not match command inventory",
            )
    if "mode_counts" in payload:
        raw_mode_counts = _mapping(payload["mode_counts"], "D7 mode_counts")
        mode_counts = {
            _required_text(key, "D7 mode_counts key"): _nonnegative_int(
                count, "D7 mode count"
            )
            for key, count in raw_mode_counts.items()
        }
        if mode_counts != dict(sorted(modes.items())):
            _fail(
                "source_guidance_mode_counts_mismatch",
                "D7 mode_counts does not match command inventory",
            )
    return commands


def _parse_and_validate_binding_acks(
    value: Any,
    *,
    expected_bindings: tuple[_ExpectedBinding, ...],
    commands: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[RuntimePlanBindingAck, ...]:
    raw_rows = _sequence(value, "runtime binding_acks")
    parsed: list[RuntimePlanBindingAck] = []
    for index, raw in enumerate(raw_rows):
        row = _strict_mapping(
            raw,
            required_fields=_BINDING_ACK_FIELDS,
            allowed_fields=_BINDING_ACK_FIELDS,
            code="binding_ack_fields_mismatch",
            context=f"runtime binding ACK {index}",
        )
        parsed.append(
            RuntimePlanBindingAck(
                resource_id=_required_text(
                    row["resource_id"], "binding ACK resource_id"
                ),
                global_track_id=_required_text(
                    row["global_track_id"], "binding ACK global_track_id"
                ),
                coalition_id=_optional_text(
                    row["coalition_id"], "binding ACK coalition_id"
                ),
                coalition_version=_optional_nonnegative_int(
                    row["coalition_version"],
                    "binding ACK coalition_version",
                ),
                member_role=_required_text(
                    row["member_role"], "binding ACK member_role"
                ),
                guidance_command_present=_strict_bool(
                    row["guidance_command_present"],
                    "binding ACK guidance_command_present",
                ),
                guidance_mode=_optional_text(
                    row["guidance_mode"], "binding ACK guidance_mode"
                ),
                guidance_gate_reason=_optional_text(
                    row["guidance_gate_reason"],
                    "binding ACK guidance_gate_reason",
                ),
                control_applied_to_world=_strict_bool(
                    row["control_applied_to_world"],
                    "binding ACK control_applied_to_world",
                ),
                held=_strict_bool(row["held"], "binding ACK held"),
            )
        )
    if len(parsed) != len(expected_bindings):
        code = (
            "missing_assignment_binding_ack"
            if len(parsed) < len(expected_bindings)
            else "extra_assignment_binding_ack"
        )
        _fail(code, "runtime ACK binding row count does not match expected plan")
    pairs = [(item.resource_id, item.global_track_id) for item in parsed]
    resources = [item.resource_id for item in parsed]
    if len(pairs) != len(set(pairs)) or len(resources) != len(set(resources)):
        _fail(
            "duplicate_assignment_binding_ack",
            "runtime ACK contains a duplicate binding row",
        )
    _match_runtime_ack_inventory(parsed, expected_bindings)
    if tuple((item.resource_id, item.global_track_id) for item in parsed) != tuple(
        (item.resource_id, item.global_track_id) for item in expected_bindings
    ):
        _fail(
            "binding_ack_order_mismatch",
            "runtime ACK binding order does not match source plan",
        )

    expected_pairs = {
        (item.resource_id, item.global_track_id) for item in expected_bindings
    }
    extra_commands = set(commands) - expected_pairs
    if extra_commands:
        _fail(
            "extra_guidance_binding",
            "D7 source contains bindings absent from expected plan",
        )
    for row in parsed:
        command = commands.get((row.resource_id, row.global_track_id))
        present = command is not None
        if row.guidance_command_present != present:
            _fail(
                "guidance_presence_mismatch",
                "binding ACK guidance presence disagrees with D7 source",
            )
        mode = None if command is None else str(command["mode"]).strip()
        gate_reason = (
            None
            if command is None
            else _optional_text(
                command["gate_reason"], "D7 guidance gate_reason"
            )
        )
        if row.guidance_mode != mode:
            _fail(
                "guidance_mode_mismatch",
                "binding ACK guidance mode disagrees with D7 source",
            )
        if row.guidance_gate_reason != gate_reason:
            _fail(
                "guidance_gate_reason_mismatch",
                "binding ACK gate reason disagrees with D7 source",
            )
        if row.control_applied_to_world != present:
            _fail(
                "control_applied_statistic_mismatch",
                "binding ACK control-applied flag disagrees with main v1 semantics",
            )
        expected_held = command is None or mode == "hold"
        if row.held != expected_held:
            _fail(
                "held_statistic_mismatch",
                "binding ACK held flag disagrees with D7 source",
            )
    return tuple(parsed)


def _match_runtime_ack_inventory(
    rows: Sequence[RuntimePlanBindingAck],
    expected: Sequence[_ExpectedBinding],
) -> None:
    expected_by_resource = {item.resource_id: item for item in expected}
    rows_by_resource = {item.resource_id: item for item in rows}
    missing = set(expected_by_resource) - set(rows_by_resource)
    if missing:
        _fail(
            "missing_assignment_binding_ack",
            "runtime ACK is missing an expected resource binding",
        )
    extra = set(rows_by_resource) - set(expected_by_resource)
    if extra:
        _fail(
            "extra_assignment_binding_ack",
            "runtime ACK contains an unexpected resource binding",
        )
    for resource_id, expected_item in expected_by_resource.items():
        row = rows_by_resource[resource_id]
        if row.global_track_id != expected_item.global_track_id:
            _fail(
                "global_track_id_mismatch",
                "runtime ACK attempted to rebind a D3 resource to another track",
            )
        if (
            row.coalition_id,
            row.coalition_version,
            row.member_role,
        ) != (
            expected_item.coalition_id,
            expected_item.coalition_version,
            expected_item.member_role,
        ):
            _fail(
                "coalition_binding_mismatch",
                "runtime ACK coalition/version/role differs from expected plan",
            )


def _match_binding_inventory(
    actual: Sequence[_ExpectedBinding],
    expected: Sequence[_ExpectedBinding],
    *,
    prefix: str,
) -> None:
    actual_resources = [item.resource_id for item in actual]
    if len(actual_resources) != len(set(actual_resources)):
        _fail(
            f"{prefix}_duplicate_binding",
            "source plan contains duplicate resource bindings",
        )
    expected_by_resource = {item.resource_id: item for item in expected}
    actual_by_resource = {item.resource_id: item for item in actual}
    if set(actual_by_resource) != set(expected_by_resource):
        _fail(
            f"{prefix}_assignment_inventory_mismatch",
            "source plan resource inventory differs from expected plan",
        )
    for resource_id, expected_item in expected_by_resource.items():
        actual_item = actual_by_resource[resource_id]
        if actual_item.global_track_id != expected_item.global_track_id:
            _fail(
                f"{prefix}_global_track_id_mismatch",
                "source plan global_track_id differs from expected plan",
            )
        if actual_item != expected_item:
            _fail(
                f"{prefix}_assignment_semantics_mismatch",
                "source plan coalition/owner semantics differ from expected plan",
            )


def _parse_source_assignment(value: Any, *, index: int) -> _ExpectedBinding:
    row = _strict_mapping(
        value,
        required_fields=_D3_ASSIGNMENT_FIELDS,
        allowed_fields=_D3_ASSIGNMENT_FIELDS,
        code="source_plan_assignment_fields_mismatch",
        context=f"D3 source assignment {index}",
    )
    return _ExpectedBinding(
        resource_id=_required_text(row["resource_id"], "source resource_id"),
        global_track_id=_required_text(
            row["global_track_id"], "source global_track_id"
        ),
        coalition_id=_optional_text(row["coalition_id"], "source coalition_id"),
        coalition_version=_optional_nonnegative_int(
            row["coalition_version"], "source coalition_version"
        ),
        member_role=_required_text(row["member_role"], "source member_role"),
        owner_node_id=_optional_text(row["owner_node_id"], "source owner_node_id"),
        regional_owner_layer=_optional_text(
            row["regional_owner_layer"], "source regional_owner_layer"
        ),
        regional_region_id=_optional_text(
            row["regional_region_id"], "source regional_region_id"
        ),
        regional_epoch=_optional_nonnegative_int(
            row["regional_epoch"], "source regional_epoch"
        ),
        regional_commit_mode=_optional_text(
            row["regional_commit_mode"], "source regional_commit_mode"
        ),
    )


def _parse_learning_evidence(
    value: Any,
    source_metadata: Mapping[str, Any],
) -> D3RuntimeLearningEvidence:
    raw = _strict_mapping(
        value,
        required_fields=set(),
        allowed_fields=_LEARNING_EVIDENCE_FIELDS,
        code="learning_evidence_fields_mismatch",
        context="D3 learning evidence",
    )
    mode = _optional_text(raw.get("mode"), "learning mode")
    applied = _optional_bool(raw.get("applied"), "learning applied")
    shadow_only = _optional_bool(
        raw.get("shadow_only"), "learning shadow_only"
    )
    bundle_loaded = _optional_bool(
        raw.get("bundle_loaded"), "learning bundle_loaded"
    )
    fallback_reason = _optional_text(
        raw.get("fallback_reason"), "learning fallback_reason"
    )
    model_fingerprint = _optional_text(
        raw.get("model_fingerprint"), "learning model_fingerprint"
    )
    expected = {
        "mode": _optional_text(
            source_metadata.get("learning_mode"), "source learning mode"
        ),
        "applied": _producer_optional_bool(
            source_metadata.get("learning_applied")
        ),
        "shadow_only": _producer_optional_bool(
            source_metadata.get("learning_shadow_only")
        ),
        "bundle_loaded": _producer_optional_bool(
            source_metadata.get("learning_bundle_loaded")
        ),
        "fallback_reason": _optional_text(
            source_metadata.get("learning_fallback_reason"),
            "source learning fallback_reason",
        ),
        "model_fingerprint": _optional_text(
            source_metadata.get("learning_model_fingerprint"),
            "source learning model_fingerprint",
        ),
    }
    actual = {
        "mode": mode,
        "applied": applied,
        "shadow_only": shadow_only,
        "bundle_loaded": bundle_loaded,
        "fallback_reason": fallback_reason,
        "model_fingerprint": model_fingerprint,
    }
    if actual != expected:
        _fail(
            "learning_evidence_source_mismatch",
            "D3 learning evidence differs from verified source plan metadata",
        )
    if applied is True and (
        mode != "assist" or bundle_loaded is not True or shadow_only is True
    ):
        _fail(
            "learning_evidence_inconsistent",
            "a learned action cannot be applied outside loaded assist mode",
        )
    available = mode == "assist" and applied is True and bundle_loaded is True
    return D3RuntimeLearningEvidence(
        mode=mode,
        applied=applied,
        shadow_only=shadow_only,
        bundle_loaded=bundle_loaded,
        fallback_reason=fallback_reason,
        model_fingerprint=model_fingerprint,
        runtime_applied_ack_available=available,
    )


def _parse_regional_evidence(
    value: Any,
    source_metadata: Mapping[str, Any],
) -> D4RegionalHintRuntimeEvidence:
    raw = _strict_mapping(
        value,
        required_fields=set(),
        allowed_fields=_REGIONAL_EVIDENCE_FIELDS,
        code="regional_evidence_fields_mismatch",
        context="D4 regional hint evidence",
    )
    actual = D4RegionalHintRuntimeEvidence(
        considered=_optional_bool(raw.get("considered"), "regional considered"),
        applied=_optional_bool(raw.get("applied"), "regional applied"),
        rejected=_optional_bool(raw.get("rejected"), "regional rejected"),
        fallback_reason=_optional_text(
            raw.get("fallback_reason"), "regional fallback_reason"
        ),
        advisory_id=_optional_text(raw.get("advisory_id"), "regional advisory_id"),
        advisory_version=_optional_nonnegative_int(
            raw.get("advisory_version"), "regional advisory_version"
        ),
        source_plan_id=_optional_text(
            raw.get("source_plan_id"), "regional source_plan_id"
        ),
        source_plan_version=_optional_nonnegative_int(
            raw.get("source_plan_version"), "regional source_plan_version"
        ),
    )
    expected = D4RegionalHintRuntimeEvidence(
        considered=_producer_optional_bool(
            source_metadata.get("regional_hint_considered")
        ),
        applied=_producer_optional_bool(
            source_metadata.get("regional_hint_applied")
        ),
        rejected=_producer_optional_bool(
            source_metadata.get("regional_hint_rejected")
        ),
        fallback_reason=_optional_text(
            source_metadata.get("regional_hint_fallback_reason"),
            "source regional fallback_reason",
        ),
        advisory_id=_optional_text(
            source_metadata.get("regional_hint_advisory_id"),
            "source regional advisory_id",
        ),
        advisory_version=_optional_nonnegative_int(
            source_metadata.get("regional_hint_advisory_version"),
            "source regional advisory_version",
        ),
        source_plan_id=_optional_text(
            source_metadata.get("regional_hint_source_plan_id"),
            "source regional source_plan_id",
        ),
        source_plan_version=_optional_nonnegative_int(
            source_metadata.get("regional_hint_source_plan_version"),
            "source regional source_plan_version",
        ),
    )
    if actual != expected:
        _fail(
            "regional_evidence_source_mismatch",
            "D4 regional evidence differs from verified source plan metadata",
        )
    return actual


def _parse_source_envelope(
    value: Mapping[str, Any],
    *,
    topic: str,
    source: str,
    code_prefix: str,
) -> _SourceEnvelope:
    envelope = _strict_mapping(
        value,
        required_fields=_ENVELOPE_FIELDS,
        allowed_fields=_ENVELOPE_FIELDS,
        code=f"{code_prefix}_envelope_fields_mismatch",
        context=f"{code_prefix} envelope",
    )
    sequence = _positive_int(envelope["sequence"], f"{code_prefix} sequence")
    actual_topic = _required_text(envelope["topic"], f"{code_prefix} topic")
    if actual_topic != topic:
        _fail(
            f"{code_prefix}_topic_mismatch",
            f"expected source topic {topic}, got {actual_topic}",
        )
    actual_source = _required_text(envelope["source"], f"{code_prefix} source")
    if actual_source != source:
        _fail(
            f"{code_prefix}_publisher_mismatch",
            f"expected source publisher {source}, got {actual_source}",
        )
    timestamp = _finite_nonnegative(
        envelope["timestamp"], f"{code_prefix} timestamp"
    )
    source_schema = _required_text(
        envelope["schema_version"], f"{code_prefix} schema_version"
    )
    payload = _mapping(envelope["payload"], f"{code_prefix} payload")
    return _SourceEnvelope(
        sequence=sequence,
        topic=actual_topic,
        source=actual_source,
        timestamp=timestamp,
        schema_version=source_schema,
        payload=payload,
    )


def _metadata_text_ack(
    ack: Mapping[str, Any],
    metadata: Mapping[str, Any],
    key: str,
) -> str | None:
    actual = _optional_text(ack[key], f"ACK {key}")
    expected = _optional_text(metadata.get(key), f"source metadata {key}")
    if actual != expected:
        _fail(
            f"{key}_mismatch",
            f"ACK {key} differs from source plan metadata",
        )
    return actual


def _metadata_int_ack(
    ack: Mapping[str, Any],
    metadata: Mapping[str, Any],
    key: str,
) -> int | None:
    actual = _optional_nonnegative_int(ack[key], f"ACK {key}")
    expected = _optional_nonnegative_int(
        metadata.get(key), f"source metadata {key}"
    )
    if actual != expected:
        _fail(
            f"{key}_mismatch",
            f"ACK {key} differs from source plan metadata",
        )
    return actual


def _metadata_time_ack(
    ack: Mapping[str, Any],
    metadata: Mapping[str, Any],
    key: str,
) -> float | None:
    actual = _optional_finite_nonnegative(ack[key], f"ACK {key}")
    expected = _optional_finite_nonnegative(
        metadata.get(key), f"source metadata {key}"
    )
    if actual != expected:
        _fail(
            f"{key}_mismatch",
            f"ACK {key} differs from source plan metadata",
        )
    return actual


def _require_plan_version(actual: int, expected: int, context: str) -> None:
    expected_version = _positive_int(expected, "expected plan version")
    if actual == expected_version:
        return
    if actual < expected_version:
        _fail(
            "stale_plan_version",
            f"{context} references stale plan version {actual}; "
            f"expected {expected_version}",
        )
    _fail(
        "plan_version_mismatch",
        f"{context} references future plan version {actual}; "
        f"expected {expected_version}",
    )


def _strict_mapping(
    value: Any,
    *,
    required_fields: set[str] | frozenset[str],
    allowed_fields: set[str] | frozenset[str],
    code: str,
    context: str,
) -> Mapping[str, Any]:
    mapping = _mapping(value, context)
    keys = set(mapping)
    if not all(isinstance(key, str) for key in mapping):
        _fail(code, f"{context} keys must be strings")
    missing = set(required_fields) - keys
    extra = keys - set(allowed_fields)
    if missing or extra:
        _fail(
            code,
            f"{context} fields mismatch; missing={sorted(missing)}, "
            f"extra={sorted(extra)}",
        )
    return mapping


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", f"{context} must be a mapping")
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail("sequence_required", f"{context} must be a sequence")
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("text_field_invalid", f"{context} must be non-empty text")
    return value.strip()


def _optional_text(value: Any, context: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, context)


def _strict_bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        _fail("boolean_field_invalid", f"{context} must be boolean")
    return value


def _optional_bool(value: Any, context: str) -> bool | None:
    if value is None:
        return None
    return _strict_bool(value, context)


def _producer_optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        _fail("integer_field_invalid", f"{context} must be an integer")
    result = int(value)
    if result < 0:
        _fail("integer_field_invalid", f"{context} must be non-negative")
    return result


def _positive_int(value: Any, context: str) -> int:
    result = _nonnegative_int(value, context)
    if result < 1:
        _fail("positive_integer_required", f"{context} must be positive")
    return result


def _optional_nonnegative_int(value: Any, context: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, context)


def _optional_positive_int(value: Any, context: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, context)


def _finite_nonnegative(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        _fail("numeric_field_invalid", f"{context} must be numeric")
    result = float(value)
    if not isfinite(result) or result < 0.0:
        _fail(
            "nonfinite_or_negative_time",
            f"{context} must be finite and non-negative",
        )
    return result


def _optional_finite_nonnegative(value: Any, context: str) -> float | None:
    if value is None:
        return None
    return _finite_nonnegative(value, context)


def _sha256_text(value: Any, context: str) -> str:
    text = _required_text(value, context).lower()
    if len(text) != 64 or any(item not in _HEX_DIGITS for item in text):
        _fail(
            "sha256_field_invalid",
            f"{context} must be a 64-character SHA-256",
        )
    return text


def _optional_sha256_text(value: Any, context: str) -> str | None:
    if value is None:
        return None
    return _sha256_text(value, context)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AssignmentPlanRuntimeAckError(
            "payload_not_canonical_json",
            "runtime payload is not finite canonical JSON",
        ) from exc


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _jsonable(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _fail(code: str, message: str) -> None:
    raise AssignmentPlanRuntimeAckError(code, message)
