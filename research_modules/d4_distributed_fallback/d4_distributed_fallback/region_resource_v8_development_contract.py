"""Strict train-only data contract for the D4 RegionResource v8 request.

This module is intentionally independent of a simulator and of every v7
evaluation artifact.  Main may use the DTOs to serialize a new development
source.  D4 only validates frozen request metadata and reads generated files.
Nothing in this contract grants assignment, degradation, takeover, coalition,
or control authority.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .regional_failover import RegionalAuthorityLayer


REGION_RESOURCE_V8_DATA_REQUEST_SCHEMA = (
    "d4-region-resource-v8-development-data-request-v1"
)
REGION_RESOURCE_V8_SEED_REGISTRY_SCHEMA = (
    "d4-region-resource-v8-development-seed-request-registry-v1"
)
REGION_RESOURCE_V8_REGION_STATE_SCHEMA = (
    "d4-region-resource-v8-online-region-state-v1"
)
REGION_RESOURCE_V8_DIRECTED_EDGE_SCHEMA = (
    "d4-region-resource-v8-online-directed-edge-v1"
)
REGION_RESOURCE_V8_TRANSFER_SCHEMA = (
    "d4-region-resource-v8-transfer-v1"
)
REGION_RESOURCE_V8_R0_REGION_ACTION_SCHEMA = (
    "d4-region-resource-v8-r0-region-action-v1"
)
REGION_RESOURCE_V8_R0_ACTION_TUPLE_SCHEMA = (
    "d4-region-resource-v8-r0-action-tuple-v1"
)
REGION_RESOURCE_V8_ANONYMOUS_CANDIDATE_SCHEMA = (
    "d4-region-resource-v8-anonymous-transfer-candidate-v1"
)
REGION_RESOURCE_V8_RAW_ACTOR_SCHEMA = (
    "d4-region-resource-v8-anonymous-raw-actor-action-v1"
)
REGION_RESOURCE_V8_PERMISSIONS_SCHEMA = (
    "d4-region-resource-v8-no-authority-permissions-v1"
)
REGION_RESOURCE_V8_ONLINE_FRAME_SCHEMA = (
    "d4-region-resource-v8-online-frame-v1"
)
REGION_RESOURCE_V8_OFFLINE_LABEL_SCHEMA = (
    "d4-region-resource-v8-offline-transfer-label-v1"
)
REGION_RESOURCE_V8_MAIN_SCHEDULE_ENTRY_SCHEMA = (
    "d4-region-resource-v8-main-generation-schedule-entry-v1"
)
REGION_RESOURCE_V8_MAIN_SCHEDULE_SCHEMA = (
    "d4-region-resource-v8-main-generation-schedule-v1"
)
REGION_RESOURCE_V8_EPISODE_MANIFEST_SCHEMA = (
    "d4-region-resource-v8-train-episode-manifest-v1"
)
REGION_RESOURCE_V8_DATASET_MANIFEST_SCHEMA = (
    "d4-region-resource-v8-train-dataset-manifest-v1"
)
REGION_RESOURCE_V8_READINESS_SCHEMA = (
    "d4-region-resource-v8-pre-generation-readiness-v1"
)

V8_REQUEST_ID = "d4-region-resource-v8-development-source-request-v1"
V8_REGISTRY_ID = "d4-v8-development-train-source-request-v1"
V8_REQUEST_STATUS = "frozen_request_not_generated"
V8_REGISTRY_STATUS = "request_only_no_data_generated"
V8_MAIN_SCHEDULE_STATUS = "complete_train_generation_schedule"
V8_DATASET_STATUS = "generated_train_data_pending_independent_audit"
V8_LOADED_STATUS = "generated_train_data_strictly_loaded"
V8_REQUESTED_SEEDS = tuple(range(28100, 28424))
V8_TOPOLOGY_REGION_COUNTS = {
    "directed_ring_8": 8,
    "directed_grid_3x3": 9,
    "directed_ring_12": 12,
    "directed_mesh_16": 16,
}
V8_SUPPLY_DEMAND_CONDITIONS = (
    "source_surplus_target_deficit",
    "balanced_boundary",
    "global_shortage_with_local_candidate_edge",
)
V8_COMMUNICATION_CONDITIONS = (
    "nominal",
    "bounded_delay_and_loss",
    "partition_then_recovery",
)
V8_TRANSFER_CLASSES = (
    "safe_forward_transfer",
    "safe_reverse_transfer",
    "hard_no_transfer_negative",
)
V8_HARD_NEGATIVE_REASONS = frozenset(
    {
        "high_transfer_score_but_no_safe_executable_transfer",
        "wrong_direction_candidate",
        "wrong_edge_candidate",
        "insufficient_source_surplus",
        "stale_owner_version_epoch_or_lease",
        "communication_partition_or_expired_evidence",
    }
)
V8_PROJECTION_REJECTION_REASONS = frozenset(
    {
        "candidate_not_on_directed_edge",
        "wrong_direction_candidate",
        "edge_capacity_exceeded",
        "insufficient_source_surplus",
        "communication_unavailable",
        "communication_partitioned",
        "maneuver_unavailable",
        "owner_inactive",
        "owner_fault_fenced",
        "coalition_ack_incomplete",
        "stale_owner_version_epoch_or_lease",
        "communication_partition_or_expired_evidence",
    }
)
V8_PERMISSION_NAMES = (
    "assist",
    "authority",
    "assignment",
    "degradation",
    "takeover",
    "coalition",
    "control",
    "physical",
    "d3",
    "d7",
    "production",
    "registration",
    "runtime_ack",
)
V8_FALSE_PERMISSIONS = {name: False for name in V8_PERMISSION_NAMES}

_FORBIDDEN_ONLINE_IDENTITY_KEYS = frozenset(
    {
        "actor_id",
        "actor_identity",
        "actor_name",
        "detection_truth_id",
        "global_track_id",
        "ground_truth_id",
        "object_id",
        "object_identity",
        "object_name",
        "sim_object_id",
        "sim_object_name",
        "target_id",
        "target_identity",
        "target_truth_id",
        "track_id",
        "truth_id",
        "truth_track_id",
    }
)
_FORBIDDEN_ONLINE_LABEL_KEYS = frozenset(
    {
        "expected_projected_transfers",
        "hard_negative_candidate_resource_count",
        "hard_negative_reasons",
        "label",
        "label_source",
        "offline_label",
        "positive_transfer_resource_count",
        "requested_target_class",
        "target_class",
    }
)

_REQUEST_ROOT_KEYS = frozenset(
    {
        "checkpoint_count",
        "content_sha256",
        "data_generation_count",
        "forbidden_online_fields",
        "future_acceptance_request",
        "future_candidate_rules",
        "model_registration_count",
        "permissions",
        "purpose",
        "report_date",
        "request_id",
        "required_coverage",
        "required_online_observables",
        "runtime_connection_count",
        "schema",
        "seed_registry",
        "source_isolation",
        "status",
        "training_count",
        "truth_policy",
        "v7_source_evidence",
    }
)
_REGISTRY_ROOT_KEYS = frozenset(
    {
        "cell_count",
        "content_sha256",
        "episode_generation_count",
        "existing_evaluation_seed_reuse_allowed",
        "existing_training_seed_reuse_allowed",
        "forbidden_seed_ranges",
        "formal_holdout_seed_reuse_allowed",
        "maximum_region_count",
        "minimum_region_count",
        "model_fit_count",
        "permissions",
        "registry_id",
        "replicates_per_cell",
        "report_date",
        "requested_forbidden_overlap",
        "requested_hard_negative_candidate_resource_counts",
        "requested_positive_transfer_resource_counts",
        "requested_seed_count",
        "requested_seed_range",
        "requested_seeds",
        "requested_split",
        "sample_generation_count",
        "schedule",
        "schedule_content_sha256",
        "schema",
        "status",
        "test_seed_allocation",
        "topology_count",
        "validation_seed_allocation",
        "validation_test_policy",
    }
)
_REGISTRY_SCHEDULE_KEYS = frozenset(
    {
        "communication_condition",
        "hard_negative_candidate_resource_count",
        "region_count",
        "replicate",
        "requested_target_class",
        "requested_transfer_resource_count",
        "seed",
        "split",
        "supply_demand_condition",
        "topology_id",
    }
)


class RegionResourceV8ContractError(RuntimeError):
    """Base error for the v8 train-only contract."""


class RegionResourceV8ValidationError(RegionResourceV8ContractError):
    """A supplied contract or data artifact failed closed."""


class RegionResourceV8DataUnavailableError(RegionResourceV8ContractError):
    """The frozen request has no complete generated train source yet."""


class V8PartitionState(str, Enum):
    CONNECTED = "connected"
    PARTITIONED = "partitioned"
    RECOVERING = "recovering"


class V8TransferClass(str, Enum):
    SAFE_FORWARD = "safe_forward_transfer"
    SAFE_REVERSE = "safe_reverse_transfer"
    HARD_NO_TRANSFER = "hard_no_transfer_negative"


@dataclass(frozen=True)
class V8NoAuthorityPermissions:
    assist: bool = False
    authority: bool = False
    assignment: bool = False
    degradation: bool = False
    takeover: bool = False
    coalition: bool = False
    control: bool = False
    physical: bool = False
    d3: bool = False
    d7: bool = False
    production: bool = False
    registration: bool = False
    runtime_ack: bool = False
    schema: str = REGION_RESOURCE_V8_PERMISSIONS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_PERMISSIONS_SCHEMA:
            raise ValueError("v8_permissions_schema_unsupported")
        for name in V8_PERMISSION_NAMES:
            value = getattr(self, name)
            if type(value) is not bool:
                raise ValueError(f"v8_permission_not_boolean:{name}")
            if value:
                raise ValueError(f"v8_permission_must_remain_false:{name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            **{name: getattr(self, name) for name in V8_PERMISSION_NAMES},
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8NoAuthorityPermissions":
        mapping = _strict_mapping(value, "permissions")
        _require_exact_keys(
            mapping,
            {"schema", *V8_PERMISSION_NAMES},
            "permissions",
        )
        return cls(**dict(mapping))


@dataclass(frozen=True)
class V8RegionResourceState:
    region_index: int
    region_id: str
    supply_available: int
    supply_committed: int
    supply_reserved: int
    demand_required: int
    demand_weighted: float
    supply_demand_gap: int
    owner_id: str | None
    owner_layer: RegionalAuthorityLayer | str
    plan_id: str
    plan_version: int
    epoch: int
    lease_expires_at_s: float
    coalition_ack_complete: bool
    owner_active: bool
    fault_fenced: bool
    schema: str = REGION_RESOURCE_V8_REGION_STATE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_REGION_STATE_SCHEMA:
            raise ValueError("v8_region_state_schema_unsupported")
        index = _strict_int(self.region_index, "region_index", minimum=0)
        object.__setattr__(self, "region_index", index)
        if self.region_id != f"region-{index}":
            raise ValueError("v8_region_id_not_canonical")
        for name in (
            "supply_available",
            "supply_committed",
            "supply_reserved",
            "demand_required",
        ):
            object.__setattr__(
                self,
                name,
                _strict_int(getattr(self, name), name, minimum=0),
            )
        object.__setattr__(
            self,
            "supply_demand_gap",
            _strict_int(self.supply_demand_gap, "supply_demand_gap"),
        )
        weighted = _finite_float(
            self.demand_weighted,
            "demand_weighted",
            minimum=0.0,
        )
        object.__setattr__(self, "demand_weighted", weighted)
        if self.supply_committed + self.supply_reserved > self.supply_available:
            raise ValueError("v8_region_protected_supply_exceeds_available")
        expected_gap = (
            self.supply_available
            - self.supply_committed
            - self.supply_reserved
            - self.demand_required
        )
        if self.supply_demand_gap != expected_gap:
            raise ValueError("v8_region_supply_demand_gap_mismatch")
        layer = (
            self.owner_layer
            if isinstance(self.owner_layer, RegionalAuthorityLayer)
            else RegionalAuthorityLayer(str(self.owner_layer))
        )
        object.__setattr__(self, "owner_layer", layer)
        if layer == RegionalAuthorityLayer.HOLD:
            if self.owner_id is not None:
                raise ValueError("v8_hold_region_owner_must_be_null")
        elif not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("v8_active_region_owner_required")
        if not isinstance(self.plan_id, str) or not self.plan_id.strip():
            raise ValueError("v8_region_plan_id_required")
        object.__setattr__(
            self,
            "plan_version",
            _strict_int(self.plan_version, "plan_version", minimum=0),
        )
        object.__setattr__(
            self,
            "epoch",
            _strict_int(self.epoch, "epoch", minimum=0),
        )
        object.__setattr__(
            self,
            "lease_expires_at_s",
            _finite_float(
                self.lease_expires_at_s,
                "lease_expires_at_s",
                minimum=0.0,
            ),
        )
        for name in (
            "coalition_ack_complete",
            "owner_active",
            "fault_fenced",
        ):
            _strict_bool(getattr(self, name), name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "region_index": self.region_index,
            "region_id": self.region_id,
            "supply_available": self.supply_available,
            "supply_committed": self.supply_committed,
            "supply_reserved": self.supply_reserved,
            "demand_required": self.demand_required,
            "demand_weighted": self.demand_weighted,
            "supply_demand_gap": self.supply_demand_gap,
            "owner_id": self.owner_id,
            "owner_layer": self.owner_layer.value,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "epoch": self.epoch,
            "lease_expires_at_s": self.lease_expires_at_s,
            "coalition_ack_complete": self.coalition_ack_complete,
            "owner_active": self.owner_active,
            "fault_fenced": self.fault_fenced,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8RegionResourceState":
        mapping = _strict_mapping(value, "online_frame.regions[]")
        _require_dataclass_keys(cls, mapping, "online_frame.regions[]")
        return cls(**dict(mapping))


@dataclass(frozen=True)
class V8DirectedEdgeState:
    edge_index: int
    source_region_index: int
    target_region_index: int
    transfer_capacity: int
    communication_latency_s: float
    communication_loss_rate: float
    communication_partition_state: V8PartitionState | str
    communication_available: bool
    maneuver_available: bool
    schema: str = REGION_RESOURCE_V8_DIRECTED_EDGE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_DIRECTED_EDGE_SCHEMA:
            raise ValueError("v8_directed_edge_schema_unsupported")
        for name in (
            "edge_index",
            "source_region_index",
            "target_region_index",
            "transfer_capacity",
        ):
            object.__setattr__(
                self,
                name,
                _strict_int(getattr(self, name), name, minimum=0),
            )
        if self.source_region_index == self.target_region_index:
            raise ValueError("v8_directed_edge_self_loop")
        object.__setattr__(
            self,
            "communication_latency_s",
            _finite_float(
                self.communication_latency_s,
                "communication_latency_s",
                minimum=0.0,
            ),
        )
        loss = _finite_float(
            self.communication_loss_rate,
            "communication_loss_rate",
            minimum=0.0,
            maximum=1.0,
        )
        object.__setattr__(self, "communication_loss_rate", loss)
        state = (
            self.communication_partition_state
            if isinstance(self.communication_partition_state, V8PartitionState)
            else V8PartitionState(str(self.communication_partition_state))
        )
        object.__setattr__(self, "communication_partition_state", state)
        _strict_bool(self.communication_available, "communication_available")
        _strict_bool(self.maneuver_available, "maneuver_available")
        if state == V8PartitionState.PARTITIONED and self.communication_available:
            raise ValueError("v8_partitioned_edge_cannot_be_communication_available")
        if state == V8PartitionState.CONNECTED and not self.communication_available:
            raise ValueError("v8_connected_edge_must_be_communication_available")

    @property
    def endpoint_key(self) -> tuple[int, int]:
        return (self.source_region_index, self.target_region_index)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "edge_index": self.edge_index,
            "source_region_index": self.source_region_index,
            "target_region_index": self.target_region_index,
            "transfer_capacity": self.transfer_capacity,
            "communication_latency_s": self.communication_latency_s,
            "communication_loss_rate": self.communication_loss_rate,
            "communication_partition_state": (
                self.communication_partition_state.value
            ),
            "communication_available": self.communication_available,
            "maneuver_available": self.maneuver_available,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8DirectedEdgeState":
        mapping = _strict_mapping(value, "online_frame.directed_edges[]")
        _require_dataclass_keys(cls, mapping, "online_frame.directed_edges[]")
        return cls(**dict(mapping))


@dataclass(frozen=True)
class V8Transfer:
    edge_index: int
    source_region_index: int
    target_region_index: int
    resource_count: int
    schema: str = REGION_RESOURCE_V8_TRANSFER_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_TRANSFER_SCHEMA:
            raise ValueError("v8_transfer_schema_unsupported")
        for name in ("edge_index", "source_region_index", "target_region_index"):
            object.__setattr__(
                self,
                name,
                _strict_int(getattr(self, name), name, minimum=0),
            )
        object.__setattr__(
            self,
            "resource_count",
            _strict_int(self.resource_count, "resource_count", minimum=1),
        )
        if self.source_region_index == self.target_region_index:
            raise ValueError("v8_transfer_self_loop")

    @property
    def action_key(self) -> tuple[int, int, int, int]:
        return (
            self.edge_index,
            self.source_region_index,
            self.target_region_index,
            self.resource_count,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "edge_index": self.edge_index,
            "source_region_index": self.source_region_index,
            "target_region_index": self.target_region_index,
            "resource_count": self.resource_count,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8Transfer":
        mapping = _strict_mapping(value, "transfer")
        _require_dataclass_keys(cls, mapping, "transfer")
        return cls(**dict(mapping))


@dataclass(frozen=True)
class V8R0RegionAction:
    region_index: int
    resource_quota_delta: int
    reserve_ratio: float
    reconnaissance_priority: float
    hold: bool
    request_replan: bool
    schema: str = REGION_RESOURCE_V8_R0_REGION_ACTION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_R0_REGION_ACTION_SCHEMA:
            raise ValueError("v8_r0_region_action_schema_unsupported")
        object.__setattr__(
            self,
            "region_index",
            _strict_int(self.region_index, "region_index", minimum=0),
        )
        object.__setattr__(
            self,
            "resource_quota_delta",
            _strict_int(self.resource_quota_delta, "resource_quota_delta"),
        )
        object.__setattr__(
            self,
            "reserve_ratio",
            _finite_float(
                self.reserve_ratio,
                "reserve_ratio",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "reconnaissance_priority",
            _finite_float(
                self.reconnaissance_priority,
                "reconnaissance_priority",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        _strict_bool(self.hold, "hold")
        _strict_bool(self.request_replan, "request_replan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "region_index": self.region_index,
            "resource_quota_delta": self.resource_quota_delta,
            "reserve_ratio": self.reserve_ratio,
            "reconnaissance_priority": self.reconnaissance_priority,
            "hold": self.hold,
            "request_replan": self.request_replan,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8R0RegionAction":
        mapping = _strict_mapping(value, "r0_action_tuple.region_actions[]")
        _require_dataclass_keys(cls, mapping, "r0_action_tuple.region_actions[]")
        return cls(**dict(mapping))


@dataclass(frozen=True)
class V8R0ActionTuple:
    region_actions: tuple[V8R0RegionAction, ...]
    transfers: tuple[V8Transfer, ...]
    schema: str = REGION_RESOURCE_V8_R0_ACTION_TUPLE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_R0_ACTION_TUPLE_SCHEMA:
            raise ValueError("v8_r0_action_tuple_schema_unsupported")
        actions = tuple(self.region_actions)
        transfers = tuple(self.transfers)
        if not actions:
            raise ValueError("v8_r0_region_actions_required")
        if len({item.region_index for item in actions}) != len(actions):
            raise ValueError("v8_r0_region_action_duplicate")
        if len({item.edge_index for item in transfers}) != len(transfers):
            raise ValueError("v8_r0_transfer_edge_duplicate")
        if sum(item.resource_quota_delta for item in actions) != 0:
            raise ValueError("v8_r0_resource_conservation_failed")
        object.__setattr__(self, "region_actions", actions)
        object.__setattr__(self, "transfers", transfers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "region_actions": [item.to_dict() for item in self.region_actions],
            "transfers": [item.to_dict() for item in self.transfers],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8R0ActionTuple":
        mapping = _strict_mapping(value, "r0_action_tuple")
        _require_dataclass_keys(cls, mapping, "r0_action_tuple")
        payload = dict(mapping)
        payload["region_actions"] = tuple(
            V8R0RegionAction.from_dict(item)
            for item in _strict_sequence(
                mapping["region_actions"],
                "r0_action_tuple.region_actions",
            )
        )
        payload["transfers"] = tuple(
            V8Transfer.from_dict(item)
            for item in _strict_sequence(
                mapping["transfers"],
                "r0_action_tuple.transfers",
            )
        )
        return cls(**payload)


@dataclass(frozen=True)
class V8AnonymousTransferCandidate:
    candidate_index: int
    edge_index: int
    source_region_index: int
    target_region_index: int
    resource_count: int
    activation_score: float
    schema: str = REGION_RESOURCE_V8_ANONYMOUS_CANDIDATE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_ANONYMOUS_CANDIDATE_SCHEMA:
            raise ValueError("v8_anonymous_candidate_schema_unsupported")
        for name in (
            "candidate_index",
            "edge_index",
            "source_region_index",
            "target_region_index",
        ):
            object.__setattr__(
                self,
                name,
                _strict_int(getattr(self, name), name, minimum=0),
            )
        object.__setattr__(
            self,
            "resource_count",
            _strict_int(self.resource_count, "resource_count", minimum=1),
        )
        object.__setattr__(
            self,
            "activation_score",
            _finite_float(
                self.activation_score,
                "activation_score",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        if self.source_region_index == self.target_region_index:
            raise ValueError("v8_anonymous_candidate_self_loop")

    @property
    def action_key(self) -> tuple[int, int, int, int]:
        return (
            self.edge_index,
            self.source_region_index,
            self.target_region_index,
            self.resource_count,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_index": self.candidate_index,
            "edge_index": self.edge_index,
            "source_region_index": self.source_region_index,
            "target_region_index": self.target_region_index,
            "resource_count": self.resource_count,
            "activation_score": self.activation_score,
        }

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "V8AnonymousTransferCandidate":
        mapping = _strict_mapping(value, "raw_actor.anonymous_candidates[]")
        _reject_forbidden_online_fields(mapping)
        _require_dataclass_keys(
            cls,
            mapping,
            "raw_actor.anonymous_candidates[]",
        )
        return cls(**dict(mapping))


@dataclass(frozen=True)
class V8AnonymousRawActorAction:
    activated: bool
    anonymous_candidates: tuple[V8AnonymousTransferCandidate, ...]
    schema: str = REGION_RESOURCE_V8_RAW_ACTOR_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_RAW_ACTOR_SCHEMA:
            raise ValueError("v8_raw_actor_schema_unsupported")
        _strict_bool(self.activated, "raw_actor.activated")
        candidates = tuple(self.anonymous_candidates)
        if self.activated != bool(candidates):
            raise ValueError("v8_raw_actor_activation_candidate_mismatch")
        indices = tuple(item.candidate_index for item in candidates)
        if indices != tuple(range(len(candidates))):
            raise ValueError("v8_raw_actor_candidate_index_not_contiguous")
        if len({item.edge_index for item in candidates}) != len(candidates):
            raise ValueError("v8_raw_actor_candidate_edge_duplicate")
        object.__setattr__(self, "anonymous_candidates", candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "activated": self.activated,
            "anonymous_candidates": [
                item.to_dict() for item in self.anonymous_candidates
            ],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8AnonymousRawActorAction":
        mapping = _strict_mapping(value, "raw_actor")
        _reject_forbidden_online_fields(mapping)
        _require_dataclass_keys(cls, mapping, "raw_actor")
        payload = dict(mapping)
        payload["anonymous_candidates"] = tuple(
            V8AnonymousTransferCandidate.from_dict(item)
            for item in _strict_sequence(
                mapping["anonymous_candidates"],
                "raw_actor.anonymous_candidates",
            )
        )
        return cls(**payload)


@dataclass(frozen=True)
class V8OnlineRegionResourceFrame:
    frame_id: str
    episode_id: str
    seed: int
    split: str
    frame_index: int
    measurement_timestamp: float
    arrival_timestamp: float
    topology_id: str
    region_count: int
    regions: tuple[V8RegionResourceState, ...]
    directed_edges: tuple[V8DirectedEdgeState, ...]
    r0_action_tuple: V8R0ActionTuple
    raw_actor: V8AnonymousRawActorAction
    projected_transfers: tuple[V8Transfer, ...]
    projection_rejection_reasons: tuple[str, ...]
    invariant_failure_reasons: tuple[str, ...]
    permissions: V8NoAuthorityPermissions
    schema: str = REGION_RESOURCE_V8_ONLINE_FRAME_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_ONLINE_FRAME_SCHEMA:
            raise ValueError("v8_online_frame_schema_unsupported")
        for name in ("frame_id", "episode_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"v8_online_frame_required_string:{name}")
        object.__setattr__(self, "seed", _strict_int(self.seed, "seed", minimum=0))
        if self.seed not in set(V8_REQUESTED_SEEDS):
            raise ValueError("v8_online_frame_seed_outside_frozen_train_request")
        if self.split != "train":
            raise ValueError("v8_online_frame_must_be_train_only")
        object.__setattr__(
            self,
            "frame_index",
            _strict_int(self.frame_index, "frame_index", minimum=0),
        )
        measurement = _finite_float(
            self.measurement_timestamp,
            "measurement_timestamp",
            minimum=0.0,
        )
        arrival = _finite_float(
            self.arrival_timestamp,
            "arrival_timestamp",
            minimum=0.0,
        )
        if arrival < measurement:
            raise ValueError("v8_arrival_precedes_measurement")
        object.__setattr__(self, "measurement_timestamp", measurement)
        object.__setattr__(self, "arrival_timestamp", arrival)
        expected_region_count = V8_TOPOLOGY_REGION_COUNTS.get(self.topology_id)
        if expected_region_count is None:
            raise ValueError("v8_topology_id_unsupported")
        count = _strict_int(self.region_count, "region_count", minimum=1)
        object.__setattr__(self, "region_count", count)
        if count != expected_region_count:
            raise ValueError("v8_topology_region_count_mismatch")

        regions = tuple(self.regions)
        if len(regions) != count:
            raise ValueError("v8_region_count_payload_mismatch")
        if tuple(item.region_index for item in regions) != tuple(range(count)):
            raise ValueError("v8_region_inventory_not_complete_or_ordered")
        object.__setattr__(self, "regions", regions)

        edges = tuple(self.directed_edges)
        expected_pairs = expected_v8_directed_edges(self.topology_id)
        actual_pairs = tuple(item.endpoint_key for item in edges)
        if tuple(item.edge_index for item in edges) != tuple(range(len(edges))):
            raise ValueError("v8_directed_edge_index_not_contiguous")
        if actual_pairs != expected_pairs:
            raise ValueError("v8_directed_topology_incomplete_or_wrong_direction")
        object.__setattr__(self, "directed_edges", edges)

        actions = self.r0_action_tuple.region_actions
        if tuple(item.region_index for item in actions) != tuple(range(count)):
            raise ValueError("v8_r0_region_action_tuple_incomplete_or_unordered")
        _validate_r0_quota_transfer_equivalence(self.r0_action_tuple, count)
        _validate_safe_transfers(
            transfers=self.r0_action_tuple.transfers,
            regions=regions,
            edges=edges,
            evaluated_at_s=arrival,
            context="r0",
        )

        edge_by_index = {item.edge_index: item for item in edges}
        for candidate in self.raw_actor.anonymous_candidates:
            edge = edge_by_index.get(candidate.edge_index)
            if edge is None or edge.endpoint_key != (
                candidate.source_region_index,
                candidate.target_region_index,
            ):
                raise ValueError("v8_raw_actor_candidate_not_on_directed_edge")

        projected = tuple(self.projected_transfers)
        if len({item.edge_index for item in projected}) != len(projected):
            raise ValueError("v8_projected_transfer_edge_duplicate")
        candidate_keys = {
            item.action_key for item in self.raw_actor.anonymous_candidates
        }
        if any(item.action_key not in candidate_keys for item in projected):
            raise ValueError("v8_projected_transfer_not_from_anonymous_candidate")
        _validate_safe_transfers(
            transfers=projected,
            regions=regions,
            edges=edges,
            evaluated_at_s=arrival,
            context="projected",
        )
        if projected and not self.raw_actor.activated:
            raise ValueError("v8_projected_transfer_without_raw_activation")
        object.__setattr__(self, "projected_transfers", projected)

        rejection_reasons = _unique_nonempty_strings(
            self.projection_rejection_reasons,
            "projection_rejection_reasons",
        )
        unknown_rejections = set(rejection_reasons) - V8_PROJECTION_REJECTION_REASONS
        if unknown_rejections:
            raise ValueError("v8_projection_rejection_reason_unsupported")
        object.__setattr__(
            self,
            "projection_rejection_reasons",
            rejection_reasons,
        )
        invariant_reasons = _unique_nonempty_strings(
            self.invariant_failure_reasons,
            "invariant_failure_reasons",
        )
        if invariant_reasons:
            raise ValueError("v8_invariant_failure_must_fail_closed")
        object.__setattr__(self, "invariant_failure_reasons", invariant_reasons)
        if not isinstance(self.permissions, V8NoAuthorityPermissions):
            raise ValueError("v8_online_frame_permissions_dto_required")

    @property
    def content_sha256(self) -> str:
        return canonical_v8_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "frame_id": self.frame_id,
            "episode_id": self.episode_id,
            "seed": self.seed,
            "split": self.split,
            "frame_index": self.frame_index,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "topology_id": self.topology_id,
            "region_count": self.region_count,
            "regions": [item.to_dict() for item in self.regions],
            "directed_edges": [item.to_dict() for item in self.directed_edges],
            "r0_action_tuple": self.r0_action_tuple.to_dict(),
            "raw_actor": self.raw_actor.to_dict(),
            "projected_transfers": [
                item.to_dict() for item in self.projected_transfers
            ],
            "projection_rejection_reasons": list(
                self.projection_rejection_reasons
            ),
            "invariant_failure_reasons": list(self.invariant_failure_reasons),
            "permissions": self.permissions.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "V8OnlineRegionResourceFrame":
        mapping = _strict_mapping(value, "online_frame")
        _reject_forbidden_online_fields(mapping)
        _require_dataclass_keys(cls, mapping, "online_frame")
        payload = dict(mapping)
        payload["regions"] = tuple(
            V8RegionResourceState.from_dict(item)
            for item in _strict_sequence(mapping["regions"], "online_frame.regions")
        )
        payload["directed_edges"] = tuple(
            V8DirectedEdgeState.from_dict(item)
            for item in _strict_sequence(
                mapping["directed_edges"],
                "online_frame.directed_edges",
            )
        )
        payload["r0_action_tuple"] = V8R0ActionTuple.from_dict(
            mapping["r0_action_tuple"]
        )
        payload["raw_actor"] = V8AnonymousRawActorAction.from_dict(
            mapping["raw_actor"]
        )
        payload["projected_transfers"] = tuple(
            V8Transfer.from_dict(item)
            for item in _strict_sequence(
                mapping["projected_transfers"],
                "online_frame.projected_transfers",
            )
        )
        payload["projection_rejection_reasons"] = tuple(
            _strict_sequence(
                mapping["projection_rejection_reasons"],
                "online_frame.projection_rejection_reasons",
            )
        )
        payload["invariant_failure_reasons"] = tuple(
            _strict_sequence(
                mapping["invariant_failure_reasons"],
                "online_frame.invariant_failure_reasons",
            )
        )
        payload["permissions"] = V8NoAuthorityPermissions.from_dict(
            mapping["permissions"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class V8OfflineTransferLabel:
    frame_id: str
    episode_id: str
    seed: int
    split: str
    frame_index: int
    online_frame_sha256: str
    target_class: V8TransferClass | str
    expected_projected_transfers: tuple[V8Transfer, ...]
    positive_transfer_resource_count: int
    hard_negative_candidate_resource_count: int
    hard_negative_reasons: tuple[str, ...]
    label_source: str
    schema: str = REGION_RESOURCE_V8_OFFLINE_LABEL_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_OFFLINE_LABEL_SCHEMA:
            raise ValueError("v8_offline_label_schema_unsupported")
        for name in ("frame_id", "episode_id", "label_source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"v8_offline_label_required_string:{name}")
        object.__setattr__(self, "seed", _strict_int(self.seed, "seed", minimum=0))
        if self.seed not in set(V8_REQUESTED_SEEDS):
            raise ValueError("v8_offline_label_seed_outside_frozen_train_request")
        if self.split != "train":
            raise ValueError("v8_offline_label_must_be_train_only")
        object.__setattr__(
            self,
            "frame_index",
            _strict_int(self.frame_index, "frame_index", minimum=0),
        )
        _validate_sha256(self.online_frame_sha256, "online_frame_sha256")
        target_class = (
            self.target_class
            if isinstance(self.target_class, V8TransferClass)
            else V8TransferClass(str(self.target_class))
        )
        object.__setattr__(self, "target_class", target_class)
        expected = tuple(self.expected_projected_transfers)
        if len({item.edge_index for item in expected}) != len(expected):
            raise ValueError("v8_offline_expected_transfer_edge_duplicate")
        object.__setattr__(self, "expected_projected_transfers", expected)
        positive_count = _strict_int(
            self.positive_transfer_resource_count,
            "positive_transfer_resource_count",
            minimum=0,
        )
        negative_count = _strict_int(
            self.hard_negative_candidate_resource_count,
            "hard_negative_candidate_resource_count",
            minimum=0,
        )
        object.__setattr__(self, "positive_transfer_resource_count", positive_count)
        object.__setattr__(
            self,
            "hard_negative_candidate_resource_count",
            negative_count,
        )
        reasons = _unique_nonempty_strings(
            self.hard_negative_reasons,
            "hard_negative_reasons",
        )
        if set(reasons) - V8_HARD_NEGATIVE_REASONS:
            raise ValueError("v8_hard_negative_reason_unsupported")
        object.__setattr__(self, "hard_negative_reasons", reasons)
        expected_count = sum(item.resource_count for item in expected)
        if target_class in {
            V8TransferClass.SAFE_FORWARD,
            V8TransferClass.SAFE_REVERSE,
        }:
            if positive_count not in {1, 2, 3}:
                raise ValueError("v8_positive_transfer_count_not_1_2_or_3")
            if expected_count != positive_count:
                raise ValueError("v8_positive_transfer_count_mismatch")
            if negative_count != 0 or reasons:
                raise ValueError("v8_positive_label_carries_hard_negative_fields")
        else:
            if positive_count != 0 or expected:
                raise ValueError("v8_hard_negative_must_have_no_expected_transfer")
            if negative_count not in {1, 2, 3}:
                raise ValueError("v8_hard_negative_candidate_count_not_1_2_or_3")
            if not reasons:
                raise ValueError("v8_hard_negative_reason_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "frame_id": self.frame_id,
            "episode_id": self.episode_id,
            "seed": self.seed,
            "split": self.split,
            "frame_index": self.frame_index,
            "online_frame_sha256": self.online_frame_sha256,
            "target_class": self.target_class.value,
            "expected_projected_transfers": [
                item.to_dict() for item in self.expected_projected_transfers
            ],
            "positive_transfer_resource_count": (
                self.positive_transfer_resource_count
            ),
            "hard_negative_candidate_resource_count": (
                self.hard_negative_candidate_resource_count
            ),
            "hard_negative_reasons": list(self.hard_negative_reasons),
            "label_source": self.label_source,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8OfflineTransferLabel":
        mapping = _strict_mapping(value, "offline_label")
        _require_dataclass_keys(cls, mapping, "offline_label")
        payload = dict(mapping)
        payload["expected_projected_transfers"] = tuple(
            V8Transfer.from_dict(item)
            for item in _strict_sequence(
                mapping["expected_projected_transfers"],
                "offline_label.expected_projected_transfers",
            )
        )
        payload["hard_negative_reasons"] = tuple(
            _strict_sequence(
                mapping["hard_negative_reasons"],
                "offline_label.hard_negative_reasons",
            )
        )
        return cls(**payload)


@dataclass(frozen=True)
class V8RequestScheduleEntry:
    seed: int
    split: str
    topology_id: str
    region_count: int
    supply_demand_condition: str
    communication_condition: str
    requested_target_class: V8TransferClass | str
    requested_transfer_resource_count: int
    hard_negative_candidate_resource_count: int
    replicate: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed", _strict_int(self.seed, "seed", minimum=0))
        if self.split != "train":
            raise ValueError("v8_registry_entry_not_train")
        expected_count = V8_TOPOLOGY_REGION_COUNTS.get(self.topology_id)
        if expected_count is None or self.region_count != expected_count:
            raise ValueError("v8_registry_entry_topology_region_mismatch")
        if self.supply_demand_condition not in V8_SUPPLY_DEMAND_CONDITIONS:
            raise ValueError("v8_registry_supply_demand_condition_unsupported")
        if self.communication_condition not in V8_COMMUNICATION_CONDITIONS:
            raise ValueError("v8_registry_communication_condition_unsupported")
        target_class = (
            self.requested_target_class
            if isinstance(self.requested_target_class, V8TransferClass)
            else V8TransferClass(str(self.requested_target_class))
        )
        object.__setattr__(self, "requested_target_class", target_class)
        transfer_count = _strict_int(
            self.requested_transfer_resource_count,
            "requested_transfer_resource_count",
            minimum=0,
        )
        negative_count = _strict_int(
            self.hard_negative_candidate_resource_count,
            "hard_negative_candidate_resource_count",
            minimum=0,
        )
        replicate = _strict_int(self.replicate, "replicate", minimum=0)
        if replicate not in {0, 1, 2}:
            raise ValueError("v8_registry_replicate_not_0_1_or_2")
        object.__setattr__(self, "replicate", replicate)
        requested_count = replicate + 1
        if target_class == V8TransferClass.HARD_NO_TRANSFER:
            if transfer_count != 0 or negative_count != requested_count:
                raise ValueError("v8_registry_hard_negative_count_mismatch")
        elif transfer_count != requested_count or negative_count != 0:
            raise ValueError("v8_registry_positive_count_mismatch")
        object.__setattr__(self, "requested_transfer_resource_count", transfer_count)
        object.__setattr__(
            self,
            "hard_negative_candidate_resource_count",
            negative_count,
        )

    @property
    def cell_key(self) -> tuple[str, str, str, str]:
        return (
            self.topology_id,
            self.supply_demand_condition,
            self.communication_condition,
            self.requested_target_class.value,
        )

    def to_registry_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "split": self.split,
            "topology_id": self.topology_id,
            "region_count": self.region_count,
            "supply_demand_condition": self.supply_demand_condition,
            "communication_condition": self.communication_condition,
            "requested_target_class": self.requested_target_class.value,
            "requested_transfer_resource_count": (
                self.requested_transfer_resource_count
            ),
            "hard_negative_candidate_resource_count": (
                self.hard_negative_candidate_resource_count
            ),
            "replicate": self.replicate,
        }

    @classmethod
    def from_registry_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "V8RequestScheduleEntry":
        mapping = _strict_mapping(value, "seed_registry.schedule[]")
        _require_exact_keys(mapping, _REGISTRY_SCHEDULE_KEYS, "seed_registry.schedule[]")
        return cls(**dict(mapping))


@dataclass(frozen=True)
class LoadedV8FrozenRequest:
    request_path: Path
    registry_path: Path
    request_id: str
    registry_id: str
    request_content_sha256: str
    registry_content_sha256: str
    registry_schedule_content_sha256: str
    schedule: tuple[V8RequestScheduleEntry, ...]


@dataclass(frozen=True)
class V8MainGenerationScheduleEntry:
    schedule_index: int
    episode_id: str
    seed: int
    split: str
    topology_id: str
    region_count: int
    supply_demand_condition: str
    communication_condition: str
    requested_target_class: V8TransferClass | str
    requested_transfer_resource_count: int
    hard_negative_candidate_resource_count: int
    replicate: int
    source_scenario_id: str
    source_scenario_version: str
    source_git_commit: str
    source_git_dirty: bool
    source_config_sha256: str
    online_features_relative_path: str
    offline_labels_relative_path: str
    schema: str = REGION_RESOURCE_V8_MAIN_SCHEDULE_ENTRY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_MAIN_SCHEDULE_ENTRY_SCHEMA:
            raise ValueError("v8_main_schedule_entry_schema_unsupported")
        object.__setattr__(
            self,
            "schedule_index",
            _strict_int(self.schedule_index, "schedule_index", minimum=0),
        )
        request_entry = self.request_entry
        for name in (
            "episode_id",
            "source_scenario_id",
            "source_scenario_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"v8_main_schedule_required_string:{name}")
        _validate_git_commit(self.source_git_commit)
        _strict_bool(self.source_git_dirty, "source_git_dirty")
        _validate_sha256(self.source_config_sha256, "source_config_sha256")
        _validate_relative_jsonl_path(
            self.online_features_relative_path,
            expected_root="online",
        )
        _validate_relative_jsonl_path(
            self.offline_labels_relative_path,
            expected_root="labels",
        )
        if self.online_features_relative_path == self.offline_labels_relative_path:
            raise ValueError("v8_online_and_offline_paths_must_differ")
        if request_entry.seed != self.seed:
            raise ValueError("v8_main_schedule_request_entry_seed_mismatch")

    @property
    def request_entry(self) -> V8RequestScheduleEntry:
        return V8RequestScheduleEntry(
            seed=self.seed,
            split=self.split,
            topology_id=self.topology_id,
            region_count=self.region_count,
            supply_demand_condition=self.supply_demand_condition,
            communication_condition=self.communication_condition,
            requested_target_class=self.requested_target_class,
            requested_transfer_resource_count=(
                self.requested_transfer_resource_count
            ),
            hard_negative_candidate_resource_count=(
                self.hard_negative_candidate_resource_count
            ),
            replicate=self.replicate,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schedule_index": self.schedule_index,
            "episode_id": self.episode_id,
            **self.request_entry.to_registry_dict(),
            "source_scenario_id": self.source_scenario_id,
            "source_scenario_version": self.source_scenario_version,
            "source_git_commit": self.source_git_commit,
            "source_git_dirty": self.source_git_dirty,
            "source_config_sha256": self.source_config_sha256,
            "online_features_relative_path": self.online_features_relative_path,
            "offline_labels_relative_path": self.offline_labels_relative_path,
        }

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "V8MainGenerationScheduleEntry":
        mapping = _strict_mapping(value, "main_schedule.entries[]")
        _require_dataclass_keys(cls, mapping, "main_schedule.entries[]")
        return cls(**dict(mapping))


@dataclass(frozen=True)
class V8MainGenerationSchedule:
    schedule_id: str
    request_id: str
    request_content_sha256: str
    registry_id: str
    registry_content_sha256: str
    registry_schedule_content_sha256: str
    status: str
    split: str
    entry_count: int
    entries: tuple[V8MainGenerationScheduleEntry, ...]
    permissions: V8NoAuthorityPermissions
    content_sha256: str
    schema: str = REGION_RESOURCE_V8_MAIN_SCHEDULE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_MAIN_SCHEDULE_SCHEMA:
            raise ValueError("v8_main_schedule_schema_unsupported")
        if not isinstance(self.schedule_id, str) or not self.schedule_id.strip():
            raise ValueError("v8_main_schedule_id_required")
        if self.request_id != V8_REQUEST_ID or self.registry_id != V8_REGISTRY_ID:
            raise ValueError("v8_main_schedule_frozen_binding_mismatch")
        for name in (
            "request_content_sha256",
            "registry_content_sha256",
            "registry_schedule_content_sha256",
        ):
            _validate_sha256(getattr(self, name), name)
        if self.status != V8_MAIN_SCHEDULE_STATUS:
            raise ValueError("v8_main_schedule_status_not_complete")
        if self.split != "train":
            raise ValueError("v8_main_schedule_must_be_train_only")
        entries = tuple(self.entries)
        count = _strict_int(self.entry_count, "entry_count", minimum=0)
        if count != len(V8_REQUESTED_SEEDS) or len(entries) != count:
            raise ValueError("v8_main_schedule_entry_count_mismatch")
        if tuple(item.schedule_index for item in entries) != tuple(range(count)):
            raise ValueError("v8_main_schedule_index_not_contiguous")
        if len({item.episode_id for item in entries}) != count:
            raise ValueError("v8_main_schedule_episode_id_duplicate")
        if len({item.online_features_relative_path for item in entries}) != count:
            raise ValueError("v8_main_schedule_online_path_duplicate")
        if len({item.offline_labels_relative_path for item in entries}) != count:
            raise ValueError("v8_main_schedule_offline_path_duplicate")
        if any(item.source_git_dirty for item in entries):
            raise ValueError("v8_main_schedule_dirty_source_forbidden")
        object.__setattr__(self, "entry_count", count)
        object.__setattr__(self, "entries", entries)
        if not isinstance(self.permissions, V8NoAuthorityPermissions):
            raise ValueError("v8_main_schedule_permissions_dto_required")
        _validate_content_sha256(self.to_dict(), "main_schedule")

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schedule_id": self.schedule_id,
            "request_id": self.request_id,
            "request_content_sha256": self.request_content_sha256,
            "registry_id": self.registry_id,
            "registry_content_sha256": self.registry_content_sha256,
            "registry_schedule_content_sha256": (
                self.registry_schedule_content_sha256
            ),
            "status": self.status,
            "split": self.split,
            "entry_count": self.entry_count,
            "entries": [item.to_dict() for item in self.entries],
            "permissions": self.permissions.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8MainGenerationSchedule":
        mapping = _strict_mapping(value, "main_schedule")
        _require_dataclass_keys(cls, mapping, "main_schedule")
        payload = dict(mapping)
        payload["entries"] = tuple(
            V8MainGenerationScheduleEntry.from_dict(item)
            for item in _strict_sequence(
                mapping["entries"],
                "main_schedule.entries",
            )
        )
        payload["permissions"] = V8NoAuthorityPermissions.from_dict(
            mapping["permissions"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class V8EpisodeManifestEntry:
    schedule_index: int
    episode_id: str
    seed: int
    online_features_relative_path: str
    online_features_sha256: str
    offline_labels_relative_path: str
    offline_labels_sha256: str
    frame_count: int
    first_measurement_timestamp: float
    last_arrival_timestamp: float
    schema: str = REGION_RESOURCE_V8_EPISODE_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_EPISODE_MANIFEST_SCHEMA:
            raise ValueError("v8_episode_manifest_schema_unsupported")
        object.__setattr__(
            self,
            "schedule_index",
            _strict_int(self.schedule_index, "schedule_index", minimum=0),
        )
        if not isinstance(self.episode_id, str) or not self.episode_id.strip():
            raise ValueError("v8_episode_manifest_episode_id_required")
        object.__setattr__(self, "seed", _strict_int(self.seed, "seed", minimum=0))
        _validate_relative_jsonl_path(
            self.online_features_relative_path,
            expected_root="online",
        )
        _validate_relative_jsonl_path(
            self.offline_labels_relative_path,
            expected_root="labels",
        )
        _validate_sha256(
            self.online_features_sha256,
            "online_features_sha256",
        )
        _validate_sha256(
            self.offline_labels_sha256,
            "offline_labels_sha256",
        )
        object.__setattr__(
            self,
            "frame_count",
            _strict_int(self.frame_count, "frame_count", minimum=1),
        )
        first = _finite_float(
            self.first_measurement_timestamp,
            "first_measurement_timestamp",
            minimum=0.0,
        )
        last = _finite_float(
            self.last_arrival_timestamp,
            "last_arrival_timestamp",
            minimum=0.0,
        )
        if last < first:
            raise ValueError("v8_episode_manifest_timestamp_order_invalid")
        object.__setattr__(self, "first_measurement_timestamp", first)
        object.__setattr__(self, "last_arrival_timestamp", last)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schedule_index": self.schedule_index,
            "episode_id": self.episode_id,
            "seed": self.seed,
            "online_features_relative_path": self.online_features_relative_path,
            "online_features_sha256": self.online_features_sha256,
            "offline_labels_relative_path": self.offline_labels_relative_path,
            "offline_labels_sha256": self.offline_labels_sha256,
            "frame_count": self.frame_count,
            "first_measurement_timestamp": self.first_measurement_timestamp,
            "last_arrival_timestamp": self.last_arrival_timestamp,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8EpisodeManifestEntry":
        mapping = _strict_mapping(value, "dataset_manifest.episodes[]")
        _require_dataclass_keys(cls, mapping, "dataset_manifest.episodes[]")
        return cls(**dict(mapping))


@dataclass(frozen=True)
class V8TrainDatasetManifest:
    dataset_id: str
    request_id: str
    request_content_sha256: str
    registry_id: str
    registry_content_sha256: str
    registry_schedule_content_sha256: str
    main_schedule_id: str
    main_schedule_content_sha256: str
    status: str
    split: str
    train_only: bool
    online_labels_separate: bool
    episode_count: int
    frame_count: int
    online_feature_file_count: int
    offline_label_file_count: int
    validation_seed_allocation: tuple[int, ...]
    test_seed_allocation: tuple[int, ...]
    training_count: int
    checkpoint_count: int
    model_registration_count: int
    runtime_connection_count: int
    episodes: tuple[V8EpisodeManifestEntry, ...]
    episode_inventory_sha256: str
    permissions: V8NoAuthorityPermissions
    content_sha256: str
    schema: str = REGION_RESOURCE_V8_DATASET_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_DATASET_MANIFEST_SCHEMA:
            raise ValueError("v8_dataset_manifest_schema_unsupported")
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("v8_dataset_id_required")
        if self.request_id != V8_REQUEST_ID or self.registry_id != V8_REGISTRY_ID:
            raise ValueError("v8_dataset_frozen_binding_mismatch")
        for name in (
            "request_content_sha256",
            "registry_content_sha256",
            "registry_schedule_content_sha256",
            "main_schedule_content_sha256",
            "episode_inventory_sha256",
        ):
            _validate_sha256(getattr(self, name), name)
        if not isinstance(self.main_schedule_id, str) or not self.main_schedule_id:
            raise ValueError("v8_dataset_main_schedule_id_required")
        if self.status != V8_DATASET_STATUS:
            raise ValueError("v8_dataset_status_unsupported")
        if self.split != "train" or self.train_only is not True:
            raise ValueError("v8_dataset_must_be_train_only")
        if self.online_labels_separate is not True:
            raise ValueError("v8_dataset_online_labels_must_be_separate")
        episodes = tuple(self.episodes)
        count = _strict_int(self.episode_count, "episode_count", minimum=0)
        if count != len(V8_REQUESTED_SEEDS) or len(episodes) != count:
            raise ValueError("v8_dataset_episode_count_mismatch")
        frame_count = _strict_int(self.frame_count, "frame_count", minimum=1)
        if frame_count != sum(item.frame_count for item in episodes):
            raise ValueError("v8_dataset_frame_count_mismatch")
        for name in ("online_feature_file_count", "offline_label_file_count"):
            if _strict_int(getattr(self, name), name, minimum=0) != count:
                raise ValueError(f"v8_dataset_file_count_mismatch:{name}")
        if tuple(item.schedule_index for item in episodes) != tuple(range(count)):
            raise ValueError("v8_dataset_schedule_index_not_contiguous")
        if len({item.episode_id for item in episodes}) != count:
            raise ValueError("v8_dataset_episode_id_duplicate")
        if len({item.seed for item in episodes}) != count:
            raise ValueError("v8_dataset_seed_duplicate")
        if tuple(item.seed for item in episodes) != V8_REQUESTED_SEEDS:
            raise ValueError("v8_dataset_seed_inventory_mismatch")
        expected_inventory_sha = canonical_v8_sha256(
            [item.to_dict() for item in episodes]
        )
        if self.episode_inventory_sha256 != expected_inventory_sha:
            raise ValueError("v8_dataset_episode_inventory_sha256_mismatch")
        for name in ("validation_seed_allocation", "test_seed_allocation"):
            allocation = tuple(getattr(self, name))
            if allocation:
                raise ValueError(f"v8_dataset_{name}_must_remain_empty")
            object.__setattr__(self, name, allocation)
        for name in (
            "training_count",
            "checkpoint_count",
            "model_registration_count",
            "runtime_connection_count",
        ):
            if _strict_int(getattr(self, name), name, minimum=0) != 0:
                raise ValueError(f"v8_dataset_{name}_must_remain_zero")
        object.__setattr__(self, "episodes", episodes)
        object.__setattr__(self, "episode_count", count)
        object.__setattr__(self, "frame_count", frame_count)
        if not isinstance(self.permissions, V8NoAuthorityPermissions):
            raise ValueError("v8_dataset_permissions_dto_required")
        _validate_content_sha256(self.to_dict(), "dataset_manifest")

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "dataset_id": self.dataset_id,
            "request_id": self.request_id,
            "request_content_sha256": self.request_content_sha256,
            "registry_id": self.registry_id,
            "registry_content_sha256": self.registry_content_sha256,
            "registry_schedule_content_sha256": (
                self.registry_schedule_content_sha256
            ),
            "main_schedule_id": self.main_schedule_id,
            "main_schedule_content_sha256": self.main_schedule_content_sha256,
            "status": self.status,
            "split": self.split,
            "train_only": self.train_only,
            "online_labels_separate": self.online_labels_separate,
            "episode_count": self.episode_count,
            "frame_count": self.frame_count,
            "online_feature_file_count": self.online_feature_file_count,
            "offline_label_file_count": self.offline_label_file_count,
            "validation_seed_allocation": list(self.validation_seed_allocation),
            "test_seed_allocation": list(self.test_seed_allocation),
            "training_count": self.training_count,
            "checkpoint_count": self.checkpoint_count,
            "model_registration_count": self.model_registration_count,
            "runtime_connection_count": self.runtime_connection_count,
            "episodes": [item.to_dict() for item in self.episodes],
            "episode_inventory_sha256": self.episode_inventory_sha256,
            "permissions": self.permissions.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "V8TrainDatasetManifest":
        mapping = _strict_mapping(value, "dataset_manifest")
        _require_dataclass_keys(cls, mapping, "dataset_manifest")
        payload = dict(mapping)
        payload["episodes"] = tuple(
            V8EpisodeManifestEntry.from_dict(item)
            for item in _strict_sequence(
                mapping["episodes"],
                "dataset_manifest.episodes",
            )
        )
        payload["validation_seed_allocation"] = tuple(
            _strict_sequence(
                mapping["validation_seed_allocation"],
                "dataset_manifest.validation_seed_allocation",
            )
        )
        payload["test_seed_allocation"] = tuple(
            _strict_sequence(
                mapping["test_seed_allocation"],
                "dataset_manifest.test_seed_allocation",
            )
        )
        payload["permissions"] = V8NoAuthorityPermissions.from_dict(
            mapping["permissions"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class LoadedV8Episode:
    episode_id: str
    seed: int
    online_path: Path
    offline_path: Path
    online_sha256: str
    offline_sha256: str
    frames: tuple[V8OnlineRegionResourceFrame, ...]
    labels: tuple[V8OfflineTransferLabel, ...]


@dataclass(frozen=True)
class LoadedV8TrainDataset:
    root: Path
    frozen_request: LoadedV8FrozenRequest
    main_schedule: V8MainGenerationSchedule
    manifest: V8TrainDatasetManifest
    episodes: tuple[LoadedV8Episode, ...]
    source_tree_sha256: str


@dataclass(frozen=True)
class V8PreGenerationReadiness:
    status: str
    contract_ready: bool
    train_only: bool
    request_id: str
    request_content_sha256: str
    registry_id: str
    registry_content_sha256: str
    registry_schedule_content_sha256: str
    requested_cell_count: int
    requested_replicates_per_cell: int
    requested_seed_count: int
    requested_seed_range: tuple[int, int]
    main_schedule_available: bool
    generated_episode_count: int
    loaded_episode_count: int
    data_available: bool
    model_available: bool
    validation_seed_allocation: tuple[int, ...]
    test_seed_allocation: tuple[int, ...]
    online_frame_schema: str
    offline_label_schema: str
    main_schedule_schema: str
    dataset_manifest_schema: str
    blockers: tuple[str, ...]
    permissions: V8NoAuthorityPermissions
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_V8_READINESS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V8_READINESS_SCHEMA:
            raise ValueError("v8_readiness_schema_unsupported")
        if self.status not in {V8_REQUEST_STATUS, V8_LOADED_STATUS}:
            raise ValueError("v8_readiness_status_unsupported")
        if self.contract_ready is not True or self.train_only is not True:
            raise ValueError("v8_readiness_contract_or_train_only_false")
        for name in (
            "request_content_sha256",
            "registry_content_sha256",
            "registry_schedule_content_sha256",
        ):
            _validate_sha256(getattr(self, name), name)
        if self.request_id != V8_REQUEST_ID or self.registry_id != V8_REGISTRY_ID:
            raise ValueError("v8_readiness_frozen_binding_mismatch")
        _strict_bool(self.main_schedule_available, "main_schedule_available")
        _strict_bool(self.data_available, "data_available")
        _strict_bool(self.model_available, "model_available")
        if self.model_available:
            raise ValueError("v8_model_must_remain_absent")
        for name, expected in (
            ("requested_cell_count", 108),
            ("requested_replicates_per_cell", 3),
            ("requested_seed_count", 324),
        ):
            if _strict_int(getattr(self, name), name, minimum=0) != expected:
                raise ValueError(f"v8_readiness_{name}_mismatch")
        if tuple(self.requested_seed_range) != (28100, 28423):
            raise ValueError("v8_readiness_seed_range_mismatch")
        for name in ("generated_episode_count", "loaded_episode_count"):
            object.__setattr__(
                self,
                name,
                _strict_int(getattr(self, name), name, minimum=0),
            )
        for name in ("validation_seed_allocation", "test_seed_allocation"):
            allocation = tuple(getattr(self, name))
            if allocation:
                raise ValueError(f"v8_readiness_{name}_must_remain_empty")
            object.__setattr__(self, name, allocation)
        expected_schemas = {
            "online_frame_schema": REGION_RESOURCE_V8_ONLINE_FRAME_SCHEMA,
            "offline_label_schema": REGION_RESOURCE_V8_OFFLINE_LABEL_SCHEMA,
            "main_schedule_schema": REGION_RESOURCE_V8_MAIN_SCHEDULE_SCHEMA,
            "dataset_manifest_schema": REGION_RESOURCE_V8_DATASET_MANIFEST_SCHEMA,
        }
        if any(getattr(self, name) != expected for name, expected in expected_schemas.items()):
            raise ValueError("v8_readiness_contract_schema_mismatch")
        blockers = _unique_nonempty_strings(self.blockers, "blockers")
        object.__setattr__(self, "blockers", blockers)
        if self.status == V8_REQUEST_STATUS:
            if self.data_available or self.generated_episode_count or self.loaded_episode_count:
                raise ValueError("v8_frozen_readiness_cannot_claim_generated_data")
            if not blockers:
                raise ValueError("v8_frozen_readiness_requires_blockers")
        else:
            if (
                not self.main_schedule_available
                or not self.data_available
                or self.generated_episode_count != 324
                or self.loaded_episode_count != 324
                or blockers
            ):
                raise ValueError("v8_loaded_readiness_incomplete")
        if not isinstance(self.permissions, V8NoAuthorityPermissions):
            raise ValueError("v8_readiness_permissions_dto_required")
        expected_digest = canonical_v8_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected_digest:
            raise ValueError("v8_readiness_content_sha256_mismatch")
        object.__setattr__(self, "content_sha256", expected_digest)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "contract_ready": self.contract_ready,
            "train_only": self.train_only,
            "request_id": self.request_id,
            "request_content_sha256": self.request_content_sha256,
            "registry_id": self.registry_id,
            "registry_content_sha256": self.registry_content_sha256,
            "registry_schedule_content_sha256": (
                self.registry_schedule_content_sha256
            ),
            "requested_cell_count": self.requested_cell_count,
            "requested_replicates_per_cell": (
                self.requested_replicates_per_cell
            ),
            "requested_seed_count": self.requested_seed_count,
            "requested_seed_range": list(self.requested_seed_range),
            "main_schedule_available": self.main_schedule_available,
            "generated_episode_count": self.generated_episode_count,
            "loaded_episode_count": self.loaded_episode_count,
            "data_available": self.data_available,
            "model_available": self.model_available,
            "validation_seed_allocation": list(self.validation_seed_allocation),
            "test_seed_allocation": list(self.test_seed_allocation),
            "online_frame_schema": self.online_frame_schema,
            "offline_label_schema": self.offline_label_schema,
            "main_schedule_schema": self.main_schedule_schema,
            "dataset_manifest_schema": self.dataset_manifest_schema,
            "blockers": list(self.blockers),
            "permissions": self.permissions.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}


def expected_v8_directed_edges(topology_id: str) -> tuple[tuple[int, int], ...]:
    """Return the canonical complete directed edge inventory for one topology."""

    region_count = V8_TOPOLOGY_REGION_COUNTS.get(topology_id)
    if region_count is None:
        raise RegionResourceV8ValidationError("v8_topology_id_unsupported")
    pairs: set[tuple[int, int]] = set()
    if topology_id in {"directed_ring_8", "directed_ring_12"}:
        for source in range(region_count):
            target = (source + 1) % region_count
            pairs.add((source, target))
            pairs.add((target, source))
    elif topology_id == "directed_grid_3x3":
        width = 3
        for row in range(width):
            for column in range(width):
                source = row * width + column
                if column + 1 < width:
                    target = source + 1
                    pairs.update({(source, target), (target, source)})
                if row + 1 < width:
                    target = source + width
                    pairs.update({(source, target), (target, source)})
    else:
        pairs.update(
            (source, target)
            for source in range(region_count)
            for target in range(region_count)
            if source != target
        )
    return tuple(sorted(pairs))


def classify_v8_edge_direction(
    topology_id: str,
    source_region_index: int,
    target_region_index: int,
) -> str:
    """Classify a canonical edge as forward or reverse."""

    pair = (int(source_region_index), int(target_region_index))
    if pair not in set(expected_v8_directed_edges(topology_id)):
        raise RegionResourceV8ValidationError(
            "v8_edge_direction_not_in_canonical_topology"
        )
    region_count = V8_TOPOLOGY_REGION_COUNTS[topology_id]
    if topology_id in {"directed_ring_8", "directed_ring_12"}:
        return "forward" if pair[1] == (pair[0] + 1) % region_count else "reverse"
    if topology_id == "directed_grid_3x3":
        return "forward" if pair[1] > pair[0] else "reverse"
    return "forward" if pair[1] > pair[0] else "reverse"


def canonical_v8_sha256(value: Any) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def canonical_v8_json_line(value: Mapping[str, Any]) -> bytes:
    """Serialize one DTO payload as the canonical JSONL representation."""

    return _canonical_json_bytes(value) + b"\n"


def validate_v8_data_request_payload(value: Mapping[str, Any]) -> Mapping[str, Any]:
    mapping = _strict_mapping(value, "data_request")
    _require_exact_keys(mapping, _REQUEST_ROOT_KEYS, "data_request")
    _validate_content_sha256(mapping, "data_request")
    if mapping["schema"] != REGION_RESOURCE_V8_DATA_REQUEST_SCHEMA:
        raise RegionResourceV8ValidationError("v8_data_request_schema_mismatch")
    if mapping["request_id"] != V8_REQUEST_ID:
        raise RegionResourceV8ValidationError("v8_data_request_id_mismatch")
    if mapping["status"] != V8_REQUEST_STATUS:
        raise RegionResourceV8ValidationError("v8_data_request_status_not_frozen")
    for name in (
        "data_generation_count",
        "training_count",
        "checkpoint_count",
        "model_registration_count",
        "runtime_connection_count",
    ):
        if _strict_int(mapping[name], name, minimum=0) != 0:
            raise RegionResourceV8ValidationError(
                f"v8_data_request_{name}_must_remain_zero"
            )
    _validate_false_permissions(mapping["permissions"], "data_request.permissions")

    coverage = _strict_mapping(mapping["required_coverage"], "required_coverage")
    expected_coverage_keys = {
        "communication_conditions",
        "hard_negative_candidate_resource_counts",
        "hard_negative_requirements",
        "minimum_region_count",
        "negative_label_rule",
        "positive_label_rule",
        "positive_transfer_resource_counts",
        "requested_cell_count",
        "requested_replicates_per_cell",
        "source_kind",
        "supply_demand_conditions",
        "topology_families",
        "transfer_classes",
    }
    _require_exact_keys(coverage, expected_coverage_keys, "required_coverage")
    expected_values = {
        "topology_families": list(V8_TOPOLOGY_REGION_COUNTS),
        "transfer_classes": list(V8_TRANSFER_CLASSES),
        "supply_demand_conditions": list(V8_SUPPLY_DEMAND_CONDITIONS),
        "communication_conditions": list(V8_COMMUNICATION_CONDITIONS),
        "positive_transfer_resource_counts": [1, 2, 3],
        "hard_negative_candidate_resource_counts": [1, 2, 3],
        "hard_negative_requirements": [
            "high_transfer_score_but_no_safe_executable_transfer",
            "wrong_direction_candidate",
            "wrong_edge_candidate",
            "insufficient_source_surplus",
            "stale_owner_version_epoch_or_lease",
            "communication_partition_or_expired_evidence",
        ],
    }
    for name, expected in expected_values.items():
        if coverage[name] != expected:
            raise RegionResourceV8ValidationError(
                f"v8_data_request_coverage_mismatch:{name}"
            )
    if (
        coverage["minimum_region_count"] != 8
        or coverage["requested_cell_count"] != 108
        or coverage["requested_replicates_per_cell"] != 3
    ):
        raise RegionResourceV8ValidationError("v8_data_request_coverage_count_mismatch")

    required_observables = set(
        _strict_sequence(
            mapping["required_online_observables"],
            "required_online_observables",
        )
    )
    minimum_observables = {
        "measurement_timestamp",
        "arrival_timestamp",
        "region_count",
        "directed_edge_index",
        "region_supply_available",
        "region_supply_committed",
        "region_demand_required",
        "region_demand_weighted",
        "supply_demand_gap",
        "communication_latency_s",
        "communication_loss_rate",
        "communication_partition_state",
        "owner_id",
        "owner_layer",
        "plan_id",
        "plan_version",
        "epoch",
        "lease_expires_at_s",
        "r0_action_tuple",
        "raw_actor_activation",
        "raw_actor_transfer",
        "projected_transfer",
        "projection_rejection_reasons",
        "invariant_failure_reasons",
    }
    if required_observables != minimum_observables:
        raise RegionResourceV8ValidationError(
            "v8_data_request_online_observable_inventory_mismatch"
        )

    forbidden_fields = set(
        _strict_sequence(mapping["forbidden_online_fields"], "forbidden_online_fields")
    )
    if not {
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "truth_id",
        "truth_track_id",
    }.issubset(forbidden_fields):
        raise RegionResourceV8ValidationError(
            "v8_data_request_forbidden_online_identity_incomplete"
        )
    truth_policy = _strict_mapping(mapping["truth_policy"], "truth_policy")
    _require_exact_keys(
        truth_policy,
        {
            "global_track_id_creation_or_rewrite_allowed",
            "offline_label_identity_allowed",
            "offline_labels_must_be_separate_from_online_payload",
            "online_truth_identity_allowed",
        },
        "truth_policy",
    )
    if (
        truth_policy["online_truth_identity_allowed"] is not False
        or truth_policy["offline_labels_must_be_separate_from_online_payload"]
        is not True
        or truth_policy["global_track_id_creation_or_rewrite_allowed"] is not False
    ):
        raise RegionResourceV8ValidationError("v8_data_request_truth_policy_unsafe")

    source_isolation = _strict_mapping(
        mapping["source_isolation"],
        "source_isolation",
    )
    _require_exact_keys(
        source_isolation,
        {
            "additional_rejected_ranges",
            "explicitly_rejected_ranges",
            "observable_overlap_audit_required",
            "reuse_existing_evaluation_source",
            "reuse_existing_training_source",
            "reuse_formal_holdout",
            "source_lineage_and_sha256_required",
        },
        "source_isolation",
    )
    if any(
        source_isolation[name] is not False
        for name in (
            "reuse_existing_evaluation_source",
            "reuse_existing_training_source",
            "reuse_formal_holdout",
        )
    ):
        raise RegionResourceV8ValidationError("v8_data_request_source_reuse_enabled")
    if (
        source_isolation["observable_overlap_audit_required"] is not True
        or source_isolation["source_lineage_and_sha256_required"] is not True
    ):
        raise RegionResourceV8ValidationError("v8_data_request_source_audit_disabled")
    candidate_rules = _strict_mapping(
        mapping["future_candidate_rules"],
        "future_candidate_rules",
    )
    if (
        candidate_rules.get("train_only_fit") is not True
        or candidate_rules.get("test_fit_tune_or_calibration_allowed") is not False
        or candidate_rules.get("current_v7_validation_test_tuning_allowed") is not False
        or candidate_rules.get("minimum_confidence_gate") != 0.6
        or candidate_rules.get("minimum_confidence_gate_may_be_lowered") is not False
        or candidate_rules.get("deterministic_projection_required") is not True
        or candidate_rules.get("owner_version_epoch_lease_checks_required") is not True
        or candidate_rules.get("coalition_checks_required") is not True
        or candidate_rules.get("fail_closed_required") is not True
    ):
        raise RegionResourceV8ValidationError("v8_data_request_candidate_rule_unsafe")
    return mapping


def validate_v8_seed_registry_payload(
    value: Mapping[str, Any],
) -> tuple[V8RequestScheduleEntry, ...]:
    mapping = _strict_mapping(value, "seed_registry")
    _require_exact_keys(mapping, _REGISTRY_ROOT_KEYS, "seed_registry")
    _validate_content_sha256(mapping, "seed_registry")
    if mapping["schema"] != REGION_RESOURCE_V8_SEED_REGISTRY_SCHEMA:
        raise RegionResourceV8ValidationError("v8_seed_registry_schema_mismatch")
    if mapping["registry_id"] != V8_REGISTRY_ID:
        raise RegionResourceV8ValidationError("v8_seed_registry_id_mismatch")
    if mapping["status"] != V8_REGISTRY_STATUS:
        raise RegionResourceV8ValidationError("v8_seed_registry_status_not_request_only")
    if mapping["requested_split"] != "train":
        raise RegionResourceV8ValidationError("v8_seed_registry_not_train_only")
    requested_seeds = tuple(
        _strict_int(item, "requested_seeds[]", minimum=0)
        for item in _strict_sequence(mapping["requested_seeds"], "requested_seeds")
    )
    forbidden = _expand_forbidden_seed_ranges(mapping["forbidden_seed_ranges"])
    overlap = set(requested_seeds) & forbidden
    if overlap:
        raise RegionResourceV8ValidationError("v8_seed_registry_forbidden_seed_overlap")
    if mapping["requested_forbidden_overlap"] != []:
        raise RegionResourceV8ValidationError(
            "v8_seed_registry_declared_forbidden_overlap_not_empty"
        )
    if requested_seeds != V8_REQUESTED_SEEDS:
        raise RegionResourceV8ValidationError("v8_seed_registry_seed_inventory_mismatch")
    if mapping["requested_seed_range"] != [28100, 28423]:
        raise RegionResourceV8ValidationError("v8_seed_registry_seed_range_mismatch")
    if mapping["requested_seed_count"] != 324:
        raise RegionResourceV8ValidationError("v8_seed_registry_seed_count_mismatch")
    if (
        mapping["cell_count"] != 108
        or mapping["replicates_per_cell"] != 3
        or mapping["topology_count"] != 4
        or mapping["minimum_region_count"] != 8
        or mapping["maximum_region_count"] != 16
    ):
        raise RegionResourceV8ValidationError("v8_seed_registry_matrix_count_mismatch")
    if mapping["requested_positive_transfer_resource_counts"] != [1, 2, 3]:
        raise RegionResourceV8ValidationError(
            "v8_seed_registry_positive_transfer_counts_mismatch"
        )
    if mapping["requested_hard_negative_candidate_resource_counts"] != [1, 2, 3]:
        raise RegionResourceV8ValidationError(
            "v8_seed_registry_hard_negative_counts_mismatch"
        )
    if mapping["validation_seed_allocation"] or mapping["test_seed_allocation"]:
        raise RegionResourceV8ValidationError(
            "v8_seed_registry_validation_test_must_remain_unallocated"
        )
    for name in (
        "existing_training_seed_reuse_allowed",
        "existing_evaluation_seed_reuse_allowed",
        "formal_holdout_seed_reuse_allowed",
    ):
        if mapping[name] is not False:
            raise RegionResourceV8ValidationError(
                f"v8_seed_registry_reuse_must_remain_false:{name}"
            )
    for name in (
        "episode_generation_count",
        "sample_generation_count",
        "model_fit_count",
    ):
        if _strict_int(mapping[name], name, minimum=0) != 0:
            raise RegionResourceV8ValidationError(
                f"v8_seed_registry_{name}_must_remain_zero"
            )
    _validate_false_permissions(mapping["permissions"], "seed_registry.permissions")

    raw_schedule = _strict_sequence(mapping["schedule"], "seed_registry.schedule")
    if canonical_v8_sha256(raw_schedule) != mapping["schedule_content_sha256"]:
        raise RegionResourceV8ValidationError(
            "v8_seed_registry_schedule_content_sha256_mismatch"
        )
    schedule = tuple(
        V8RequestScheduleEntry.from_registry_dict(item) for item in raw_schedule
    )
    expected = _expected_request_schedule()
    if tuple(item.to_registry_dict() for item in schedule) != tuple(
        item.to_registry_dict() for item in expected
    ):
        raise RegionResourceV8ValidationError("v8_seed_registry_schedule_matrix_mismatch")
    cell_replicates: dict[tuple[str, str, str, str], set[int]] = {}
    for item in schedule:
        cell_replicates.setdefault(item.cell_key, set()).add(item.replicate)
    if len(cell_replicates) != 108 or any(
        replicates != {0, 1, 2} for replicates in cell_replicates.values()
    ):
        raise RegionResourceV8ValidationError(
            "v8_seed_registry_108_cells_x_3_replicates_failed"
        )
    return schedule


def load_v8_frozen_request(
    request_path: str | Path,
    registry_path: str | Path,
) -> LoadedV8FrozenRequest:
    """Strictly and read-only load the frozen v8 request and seed registry."""

    request_file = _require_regular_readonly_input(request_path, "data_request")
    registry_file = _require_regular_readonly_input(registry_path, "seed_registry")
    request = validate_v8_data_request_payload(_read_json(request_file, "data_request"))
    registry_payload = _read_json(registry_file, "seed_registry")
    schedule = validate_v8_seed_registry_payload(registry_payload)
    binding = _strict_mapping(request["seed_registry"], "data_request.seed_registry")
    _require_exact_keys(
        binding,
        {
            "schema",
            "registry_id",
            "content_sha256",
            "schedule_content_sha256",
            "requested_seed_count",
        },
        "data_request.seed_registry",
    )
    expected_binding = {
        "schema": REGION_RESOURCE_V8_SEED_REGISTRY_SCHEMA,
        "registry_id": V8_REGISTRY_ID,
        "content_sha256": registry_payload["content_sha256"],
        "schedule_content_sha256": registry_payload["schedule_content_sha256"],
        "requested_seed_count": 324,
    }
    if dict(binding) != expected_binding:
        raise RegionResourceV8ValidationError(
            "v8_data_request_seed_registry_binding_mismatch"
        )
    return LoadedV8FrozenRequest(
        request_path=request_file,
        registry_path=registry_file,
        request_id=V8_REQUEST_ID,
        registry_id=V8_REGISTRY_ID,
        request_content_sha256=str(request["content_sha256"]),
        registry_content_sha256=str(registry_payload["content_sha256"]),
        registry_schedule_content_sha256=str(
            registry_payload["schedule_content_sha256"]
        ),
        schedule=schedule,
    )


def load_v8_main_generation_schedule(
    path: str | Path,
    frozen_request: LoadedV8FrozenRequest,
) -> V8MainGenerationSchedule:
    schedule_path = _require_regular_readonly_input(path, "main_schedule")
    try:
        schedule = V8MainGenerationSchedule.from_dict(
            _read_json(schedule_path, "main_schedule")
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceV8ValidationError(
            f"v8_main_schedule_invalid:{type(exc).__name__}:{exc}"
        ) from exc
    if (
        schedule.request_content_sha256
        != frozen_request.request_content_sha256
        or schedule.registry_content_sha256
        != frozen_request.registry_content_sha256
        or schedule.registry_schedule_content_sha256
        != frozen_request.registry_schedule_content_sha256
    ):
        raise RegionResourceV8ValidationError("v8_main_schedule_hash_binding_mismatch")
    if tuple(item.request_entry for item in schedule.entries) != frozen_request.schedule:
        raise RegionResourceV8ValidationError(
            "v8_main_schedule_does_not_cover_frozen_registry"
        )
    return schedule


def load_v8_episode_pair(
    online_path: str | Path,
    offline_path: str | Path,
    *,
    expected_online_sha256: str | None = None,
    expected_offline_sha256: str | None = None,
    expected_frame_count: int | None = None,
    schedule_entry: V8RequestScheduleEntry | None = None,
) -> LoadedV8Episode:
    """Read and cross-check one separate online-feature/offline-label pair."""

    online_file = _require_regular_readonly_input(online_path, "online_features")
    offline_file = _require_regular_readonly_input(offline_path, "offline_labels")
    online_bytes = _read_bytes(online_file, "online_features")
    offline_bytes = _read_bytes(offline_file, "offline_labels")
    online_sha = sha256(online_bytes).hexdigest()
    offline_sha = sha256(offline_bytes).hexdigest()
    if expected_online_sha256 is not None and online_sha != expected_online_sha256:
        raise RegionResourceV8ValidationError("v8_online_features_sha256_mismatch")
    if expected_offline_sha256 is not None and offline_sha != expected_offline_sha256:
        raise RegionResourceV8ValidationError("v8_offline_labels_sha256_mismatch")
    online_payloads = _read_jsonl_bytes(online_bytes, "online_features")
    offline_payloads = _read_jsonl_bytes(offline_bytes, "offline_labels")
    try:
        frames = tuple(
            V8OnlineRegionResourceFrame.from_dict(item) for item in online_payloads
        )
        labels = tuple(V8OfflineTransferLabel.from_dict(item) for item in offline_payloads)
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceV8ValidationError(
            f"v8_episode_dto_invalid:{type(exc).__name__}:{exc}"
        ) from exc
    if not frames or len(frames) != len(labels):
        raise RegionResourceV8ValidationError("v8_episode_frame_label_count_mismatch")
    if expected_frame_count is not None and len(frames) != expected_frame_count:
        raise RegionResourceV8ValidationError("v8_episode_manifest_frame_count_mismatch")
    _validate_episode_frame_sequence(frames)
    for frame, label in zip(frames, labels, strict=True):
        _validate_frame_label_pair(frame, label)
    episode_ids = {item.episode_id for item in frames} | {
        item.episode_id for item in labels
    }
    seeds = {item.seed for item in frames} | {item.seed for item in labels}
    if len(episode_ids) != 1 or len(seeds) != 1:
        raise RegionResourceV8ValidationError("v8_episode_identity_not_atomic")
    if schedule_entry is not None:
        _validate_episode_against_schedule(frames, labels, schedule_entry)
    return LoadedV8Episode(
        episode_id=next(iter(episode_ids)),
        seed=next(iter(seeds)),
        online_path=online_file,
        offline_path=offline_file,
        online_sha256=online_sha,
        offline_sha256=offline_sha,
        frames=frames,
        labels=labels,
    )


def load_v8_development_train_dataset(
    dataset_root: str | Path,
    request_path: str | Path,
    registry_path: str | Path,
    main_schedule_path: str | Path,
) -> LoadedV8TrainDataset:
    """Strictly load a complete 324-episode train source without writing it."""

    root = Path(dataset_root).resolve()
    if not root.is_dir():
        raise RegionResourceV8DataUnavailableError(
            "frozen_request_not_generated:dataset_root_missing"
        )
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise RegionResourceV8DataUnavailableError(
            "frozen_request_not_generated:dataset_manifest_missing"
        )
    frozen = load_v8_frozen_request(request_path, registry_path)
    main_schedule = load_v8_main_generation_schedule(main_schedule_path, frozen)
    try:
        manifest = V8TrainDatasetManifest.from_dict(
            _read_json(manifest_path, "dataset_manifest")
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceV8ValidationError(
            f"v8_dataset_manifest_invalid:{type(exc).__name__}:{exc}"
        ) from exc
    _validate_dataset_bindings(manifest, frozen, main_schedule)
    expected_files = {Path("manifest.json")}
    loaded_episodes: list[LoadedV8Episode] = []
    for schedule_item, manifest_item in zip(
        main_schedule.entries,
        manifest.episodes,
        strict=True,
    ):
        _validate_manifest_entry_binding(manifest_item, schedule_item)
        online_relative = Path(manifest_item.online_features_relative_path)
        offline_relative = Path(manifest_item.offline_labels_relative_path)
        expected_files.update({online_relative, offline_relative})
        loaded = load_v8_episode_pair(
            _resolve_inside(root, online_relative),
            _resolve_inside(root, offline_relative),
            expected_online_sha256=manifest_item.online_features_sha256,
            expected_offline_sha256=manifest_item.offline_labels_sha256,
            expected_frame_count=manifest_item.frame_count,
            schedule_entry=schedule_item.request_entry,
        )
        if (
            loaded.episode_id != manifest_item.episode_id
            or loaded.seed != manifest_item.seed
            or loaded.frames[0].measurement_timestamp
            != manifest_item.first_measurement_timestamp
            or loaded.frames[-1].arrival_timestamp
            != manifest_item.last_arrival_timestamp
        ):
            raise RegionResourceV8ValidationError(
                "v8_episode_manifest_content_binding_mismatch"
            )
        loaded_episodes.append(loaded)
    actual_files = {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    symlinks = [path for path in root.rglob("*") if path.is_symlink()]
    if symlinks:
        raise RegionResourceV8ValidationError("v8_dataset_symlink_forbidden")
    if actual_files != expected_files:
        raise RegionResourceV8ValidationError("v8_dataset_file_inventory_mismatch")
    tree_sha = canonical_v8_sha256(
        {
            str(path): _sha256_file(root / path)
            for path in sorted(expected_files, key=str)
        }
    )
    return LoadedV8TrainDataset(
        root=root,
        frozen_request=frozen,
        main_schedule=main_schedule,
        manifest=manifest,
        episodes=tuple(loaded_episodes),
        source_tree_sha256=tree_sha,
    )


def validate_v8_pre_generation_readiness(
    request_path: str | Path,
    registry_path: str | Path,
    *,
    main_schedule_path: str | Path | None = None,
    dataset_root: str | Path | None = None,
) -> V8PreGenerationReadiness:
    """Return frozen readiness unless both schedule and all episodes strictly load."""

    frozen = load_v8_frozen_request(request_path, registry_path)
    main_schedule: V8MainGenerationSchedule | None = None
    blockers: list[str] = []
    if main_schedule_path is None:
        blockers.append("complete_main_generation_schedule_absent")
    else:
        main_schedule = load_v8_main_generation_schedule(
            main_schedule_path,
            frozen,
        )
    if dataset_root is None:
        blockers.append("generated_episode_manifest_absent")
    if dataset_root is not None and main_schedule_path is None:
        raise RegionResourceV8ValidationError(
            "v8_dataset_cannot_be_validated_without_complete_main_schedule"
        )
    if dataset_root is None:
        return _frozen_readiness(
            frozen,
            main_schedule_available=main_schedule is not None,
            blockers=tuple(blockers),
        )
    loaded = load_v8_development_train_dataset(
        dataset_root,
        request_path,
        registry_path,
        main_schedule_path,
    )
    return V8PreGenerationReadiness(
        status=V8_LOADED_STATUS,
        contract_ready=True,
        train_only=True,
        request_id=frozen.request_id,
        request_content_sha256=frozen.request_content_sha256,
        registry_id=frozen.registry_id,
        registry_content_sha256=frozen.registry_content_sha256,
        registry_schedule_content_sha256=(
            frozen.registry_schedule_content_sha256
        ),
        requested_cell_count=108,
        requested_replicates_per_cell=3,
        requested_seed_count=324,
        requested_seed_range=(28100, 28423),
        main_schedule_available=True,
        generated_episode_count=loaded.manifest.episode_count,
        loaded_episode_count=len(loaded.episodes),
        data_available=True,
        model_available=False,
        validation_seed_allocation=(),
        test_seed_allocation=(),
        online_frame_schema=REGION_RESOURCE_V8_ONLINE_FRAME_SCHEMA,
        offline_label_schema=REGION_RESOURCE_V8_OFFLINE_LABEL_SCHEMA,
        main_schedule_schema=REGION_RESOURCE_V8_MAIN_SCHEDULE_SCHEMA,
        dataset_manifest_schema=REGION_RESOURCE_V8_DATASET_MANIFEST_SCHEMA,
        blockers=(),
        permissions=V8NoAuthorityPermissions(),
    )


def _frozen_readiness(
    frozen: LoadedV8FrozenRequest,
    *,
    main_schedule_available: bool,
    blockers: tuple[str, ...],
) -> V8PreGenerationReadiness:
    return V8PreGenerationReadiness(
        status=V8_REQUEST_STATUS,
        contract_ready=True,
        train_only=True,
        request_id=frozen.request_id,
        request_content_sha256=frozen.request_content_sha256,
        registry_id=frozen.registry_id,
        registry_content_sha256=frozen.registry_content_sha256,
        registry_schedule_content_sha256=(
            frozen.registry_schedule_content_sha256
        ),
        requested_cell_count=108,
        requested_replicates_per_cell=3,
        requested_seed_count=324,
        requested_seed_range=(28100, 28423),
        main_schedule_available=main_schedule_available,
        generated_episode_count=0,
        loaded_episode_count=0,
        data_available=False,
        model_available=False,
        validation_seed_allocation=(),
        test_seed_allocation=(),
        online_frame_schema=REGION_RESOURCE_V8_ONLINE_FRAME_SCHEMA,
        offline_label_schema=REGION_RESOURCE_V8_OFFLINE_LABEL_SCHEMA,
        main_schedule_schema=REGION_RESOURCE_V8_MAIN_SCHEDULE_SCHEMA,
        dataset_manifest_schema=REGION_RESOURCE_V8_DATASET_MANIFEST_SCHEMA,
        blockers=blockers,
        permissions=V8NoAuthorityPermissions(),
    )


def _expected_request_schedule() -> tuple[V8RequestScheduleEntry, ...]:
    entries: list[V8RequestScheduleEntry] = []
    index = 0
    for topology_id, region_count in V8_TOPOLOGY_REGION_COUNTS.items():
        for supply_demand in V8_SUPPLY_DEMAND_CONDITIONS:
            for communication in V8_COMMUNICATION_CONDITIONS:
                for target_class in V8_TRANSFER_CLASSES:
                    for replicate in range(3):
                        requested_count = replicate + 1
                        entries.append(
                            V8RequestScheduleEntry(
                                seed=V8_REQUESTED_SEEDS[index],
                                split="train",
                                topology_id=topology_id,
                                region_count=region_count,
                                supply_demand_condition=supply_demand,
                                communication_condition=communication,
                                requested_target_class=target_class,
                                requested_transfer_resource_count=(
                                    0
                                    if target_class
                                    == V8TransferClass.HARD_NO_TRANSFER.value
                                    else requested_count
                                ),
                                hard_negative_candidate_resource_count=(
                                    requested_count
                                    if target_class
                                    == V8TransferClass.HARD_NO_TRANSFER.value
                                    else 0
                                ),
                                replicate=replicate,
                            )
                        )
                        index += 1
    return tuple(entries)


def _validate_r0_quota_transfer_equivalence(
    action_tuple: V8R0ActionTuple,
    region_count: int,
) -> None:
    expected = [0] * region_count
    for transfer in action_tuple.transfers:
        if (
            transfer.source_region_index >= region_count
            or transfer.target_region_index >= region_count
        ):
            raise ValueError("v8_r0_transfer_region_out_of_range")
        expected[transfer.source_region_index] -= transfer.resource_count
        expected[transfer.target_region_index] += transfer.resource_count
    actual = [item.resource_quota_delta for item in action_tuple.region_actions]
    if actual != expected:
        raise ValueError("v8_r0_quota_delta_transfer_mismatch")


def _validate_safe_transfers(
    *,
    transfers: Sequence[V8Transfer],
    regions: Sequence[V8RegionResourceState],
    edges: Sequence[V8DirectedEdgeState],
    evaluated_at_s: float,
    context: str,
) -> None:
    region_by_index = {item.region_index: item for item in regions}
    edge_by_index = {item.edge_index: item for item in edges}
    outgoing: dict[int, int] = {}
    for transfer in transfers:
        edge = edge_by_index.get(transfer.edge_index)
        if edge is None or edge.endpoint_key != (
            transfer.source_region_index,
            transfer.target_region_index,
        ):
            raise ValueError(f"v8_{context}_transfer_not_on_directed_edge")
        source = region_by_index.get(transfer.source_region_index)
        target = region_by_index.get(transfer.target_region_index)
        if source is None or target is None:
            raise ValueError(f"v8_{context}_transfer_region_unknown")
        if transfer.resource_count > edge.transfer_capacity:
            raise ValueError(f"v8_{context}_transfer_capacity_exceeded")
        if not edge.communication_available:
            raise ValueError(f"v8_{context}_transfer_communication_unavailable")
        if edge.communication_partition_state == V8PartitionState.PARTITIONED:
            raise ValueError(f"v8_{context}_transfer_partitioned")
        if not edge.maneuver_available:
            raise ValueError(f"v8_{context}_transfer_maneuver_unavailable")
        for endpoint in (source, target):
            if endpoint.owner_layer == RegionalAuthorityLayer.HOLD:
                raise ValueError(f"v8_{context}_transfer_owner_hold")
            if not endpoint.owner_active:
                raise ValueError(f"v8_{context}_transfer_owner_inactive")
            if endpoint.fault_fenced:
                raise ValueError(f"v8_{context}_transfer_owner_fault_fenced")
            if not endpoint.coalition_ack_complete:
                raise ValueError(f"v8_{context}_transfer_coalition_ack_incomplete")
            if evaluated_at_s >= endpoint.lease_expires_at_s:
                raise ValueError(f"v8_{context}_transfer_stale_lease")
        outgoing[source.region_index] = (
            outgoing.get(source.region_index, 0) + transfer.resource_count
        )
    for source_index, resource_count in outgoing.items():
        if resource_count > region_by_index[source_index].supply_demand_gap:
            raise ValueError(f"v8_{context}_transfer_insufficient_source_surplus")


def _validate_frame_label_pair(
    frame: V8OnlineRegionResourceFrame,
    label: V8OfflineTransferLabel,
) -> None:
    if (
        frame.frame_id != label.frame_id
        or frame.episode_id != label.episode_id
        or frame.seed != label.seed
        or frame.split != label.split
        or frame.frame_index != label.frame_index
    ):
        raise RegionResourceV8ValidationError("v8_frame_label_identity_mismatch")
    if frame.content_sha256 != label.online_frame_sha256:
        raise RegionResourceV8ValidationError("v8_frame_label_sha256_mismatch")
    if tuple(item.action_key for item in frame.projected_transfers) != tuple(
        item.action_key for item in label.expected_projected_transfers
    ):
        raise RegionResourceV8ValidationError(
            "v8_frame_label_projected_transfer_mismatch"
        )
    projected_count = sum(item.resource_count for item in frame.projected_transfers)
    raw_count = sum(
        item.resource_count for item in frame.raw_actor.anonymous_candidates
    )
    if label.target_class == V8TransferClass.HARD_NO_TRANSFER:
        if projected_count != 0 or raw_count != label.hard_negative_candidate_resource_count:
            raise RegionResourceV8ValidationError(
                "v8_hard_negative_frame_count_mismatch"
            )
        if not frame.raw_actor.activated or not frame.projection_rejection_reasons:
            raise RegionResourceV8ValidationError(
                "v8_hard_negative_missing_candidate_or_rejection"
            )
    else:
        if projected_count != label.positive_transfer_resource_count:
            raise RegionResourceV8ValidationError("v8_positive_frame_count_mismatch")
        if frame.projection_rejection_reasons:
            raise RegionResourceV8ValidationError(
                "v8_positive_frame_projection_rejection_forbidden"
            )
        expected_direction = (
            "forward"
            if label.target_class == V8TransferClass.SAFE_FORWARD
            else "reverse"
        )
        if any(
            classify_v8_edge_direction(
                frame.topology_id,
                transfer.source_region_index,
                transfer.target_region_index,
            )
            != expected_direction
            for transfer in frame.projected_transfers
        ):
            raise RegionResourceV8ValidationError(
                "v8_positive_label_topology_direction_mismatch"
            )


def _validate_episode_frame_sequence(
    frames: Sequence[V8OnlineRegionResourceFrame],
) -> None:
    if tuple(item.frame_index for item in frames) != tuple(range(len(frames))):
        raise RegionResourceV8ValidationError("v8_episode_frame_index_not_contiguous")
    if any(
        right.measurement_timestamp < left.measurement_timestamp
        or right.arrival_timestamp < left.arrival_timestamp
        for left, right in zip(frames, frames[1:])
    ):
        raise RegionResourceV8ValidationError("v8_episode_timestamp_not_monotonic")
    for left, right in zip(frames, frames[1:]):
        if left.topology_id != right.topology_id or left.region_count != right.region_count:
            raise RegionResourceV8ValidationError("v8_episode_topology_changed")
        for old, new in zip(left.regions, right.regions, strict=True):
            if new.plan_version < old.plan_version or new.epoch < old.epoch:
                raise RegionResourceV8ValidationError(
                    "v8_episode_owner_version_epoch_rollback"
                )
            old_identity = (
                old.owner_id,
                old.owner_layer,
                old.plan_id,
                old.plan_version,
                old.epoch,
            )
            new_identity = (
                new.owner_id,
                new.owner_layer,
                new.plan_id,
                new.plan_version,
                new.epoch,
            )
            if old_identity == new_identity and (
                old.lease_expires_at_s != new.lease_expires_at_s
            ):
                raise RegionResourceV8ValidationError(
                    "v8_episode_same_generation_lease_change_forbidden"
                )
            if old.owner_id != new.owner_id and (
                new.plan_version <= old.plan_version or new.epoch <= old.epoch
            ):
                raise RegionResourceV8ValidationError(
                    "v8_episode_owner_change_requires_new_version_and_epoch"
                )


def _validate_episode_against_schedule(
    frames: Sequence[V8OnlineRegionResourceFrame],
    labels: Sequence[V8OfflineTransferLabel],
    schedule: V8RequestScheduleEntry,
) -> None:
    if any(
        frame.seed != schedule.seed
        or frame.topology_id != schedule.topology_id
        or frame.region_count != schedule.region_count
        for frame in frames
    ):
        raise RegionResourceV8ValidationError("v8_episode_schedule_feature_mismatch")
    if any(label.target_class != schedule.requested_target_class for label in labels):
        raise RegionResourceV8ValidationError("v8_episode_schedule_label_class_mismatch")
    if schedule.requested_target_class == V8TransferClass.HARD_NO_TRANSFER:
        if not any(
            label.hard_negative_candidate_resource_count
            == schedule.hard_negative_candidate_resource_count
            for label in labels
        ):
            raise RegionResourceV8ValidationError(
                "v8_episode_schedule_hard_negative_count_missing"
            )
    elif not any(
        label.positive_transfer_resource_count
        == schedule.requested_transfer_resource_count
        for label in labels
    ):
        raise RegionResourceV8ValidationError(
            "v8_episode_schedule_positive_transfer_count_missing"
        )
    _validate_supply_demand_condition(frames, schedule.supply_demand_condition)
    _validate_communication_condition(frames, schedule.communication_condition)


def _validate_supply_demand_condition(
    frames: Sequence[V8OnlineRegionResourceFrame],
    condition: str,
) -> None:
    gaps = [region.supply_demand_gap for frame in frames for region in frame.regions]
    if condition == "source_surplus_target_deficit":
        passed = any(value > 0 for value in gaps) and any(value < 0 for value in gaps)
    elif condition == "balanced_boundary":
        passed = bool(gaps) and all(abs(value) <= 1 for value in gaps)
    else:
        passed = sum(gaps) < 0 and any(value > 0 for value in gaps)
    if not passed:
        raise RegionResourceV8ValidationError(
            f"v8_episode_supply_demand_condition_not_observed:{condition}"
        )


def _validate_communication_condition(
    frames: Sequence[V8OnlineRegionResourceFrame],
    condition: str,
) -> None:
    edges = [edge for frame in frames for edge in frame.directed_edges]
    if condition == "nominal":
        passed = all(
            edge.communication_partition_state == V8PartitionState.CONNECTED
            and edge.communication_available
            and edge.communication_latency_s <= 0.05
            and edge.communication_loss_rate <= 0.01
            for edge in edges
        )
    elif condition == "bounded_delay_and_loss":
        passed = all(
            edge.communication_partition_state != V8PartitionState.PARTITIONED
            and edge.communication_available
            and edge.communication_latency_s <= 0.5
            and edge.communication_loss_rate <= 0.3
            for edge in edges
        ) and any(
            edge.communication_latency_s > 0.05
            or edge.communication_loss_rate > 0.01
            for edge in edges
        )
    else:
        partition_indices = [
            frame.frame_index
            for frame in frames
            if any(
                edge.communication_partition_state == V8PartitionState.PARTITIONED
                for edge in frame.directed_edges
            )
        ]
        recovery_indices = [
            frame.frame_index
            for frame in frames
            if all(
                edge.communication_partition_state != V8PartitionState.PARTITIONED
                for edge in frame.directed_edges
            )
        ]
        passed = bool(partition_indices) and any(
            recovered > min(partition_indices) for recovered in recovery_indices
        )
    if not passed:
        raise RegionResourceV8ValidationError(
            f"v8_episode_communication_condition_not_observed:{condition}"
        )


def _validate_dataset_bindings(
    manifest: V8TrainDatasetManifest,
    frozen: LoadedV8FrozenRequest,
    schedule: V8MainGenerationSchedule,
) -> None:
    if (
        manifest.request_content_sha256 != frozen.request_content_sha256
        or manifest.registry_content_sha256 != frozen.registry_content_sha256
        or manifest.registry_schedule_content_sha256
        != frozen.registry_schedule_content_sha256
        or manifest.main_schedule_id != schedule.schedule_id
        or manifest.main_schedule_content_sha256 != schedule.content_sha256
    ):
        raise RegionResourceV8ValidationError("v8_dataset_manifest_binding_mismatch")


def _validate_manifest_entry_binding(
    manifest: V8EpisodeManifestEntry,
    schedule: V8MainGenerationScheduleEntry,
) -> None:
    if (
        manifest.schedule_index != schedule.schedule_index
        or manifest.episode_id != schedule.episode_id
        or manifest.seed != schedule.seed
        or manifest.online_features_relative_path
        != schedule.online_features_relative_path
        or manifest.offline_labels_relative_path
        != schedule.offline_labels_relative_path
    ):
        raise RegionResourceV8ValidationError(
            "v8_episode_manifest_main_schedule_binding_mismatch"
        )


def _validate_false_permissions(value: Any, path: str) -> None:
    mapping = _strict_mapping(value, path)
    _require_exact_keys(mapping, set(V8_PERMISSION_NAMES), path)
    for name in V8_PERMISSION_NAMES:
        _strict_bool(mapping[name], f"{path}.{name}")
        if mapping[name]:
            raise RegionResourceV8ValidationError(
                f"v8_permission_must_remain_false:{name}"
            )


def _expand_forbidden_seed_ranges(value: Any) -> set[int]:
    result: set[int] = set()
    for index, item in enumerate(_strict_sequence(value, "forbidden_seed_ranges")):
        mapping = _strict_mapping(item, f"forbidden_seed_ranges[{index}]")
        _require_exact_keys(
            mapping,
            {"range", "reason"},
            f"forbidden_seed_ranges[{index}]",
        )
        bounds = _strict_sequence(mapping["range"], "forbidden_seed_range.range")
        if len(bounds) != 2:
            raise RegionResourceV8ValidationError("v8_forbidden_seed_range_invalid")
        lower = _strict_int(bounds[0], "forbidden_seed_range.lower", minimum=0)
        upper = _strict_int(bounds[1], "forbidden_seed_range.upper", minimum=0)
        if upper < lower or not isinstance(mapping["reason"], str) or not mapping["reason"]:
            raise RegionResourceV8ValidationError("v8_forbidden_seed_range_invalid")
        result.update(range(lower, upper + 1))
    return result


def _reject_forbidden_online_fields(value: Any, path: str = "online_frame") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_ONLINE_IDENTITY_KEYS:
                raise ValueError(f"v8_online_identity_leakage:{path}.{normalized}")
            if normalized in _FORBIDDEN_ONLINE_LABEL_KEYS:
                raise ValueError(f"v8_online_label_leakage:{path}.{normalized}")
            _reject_forbidden_online_fields(child, f"{path}.{normalized}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_forbidden_online_fields(child, f"{path}[{index}]")


def _strict_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegionResourceV8ValidationError(f"v8_mapping_required:{path}")
    if any(not isinstance(key, str) for key in value):
        raise RegionResourceV8ValidationError(f"v8_string_keys_required:{path}")
    return value


def _strict_sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise RegionResourceV8ValidationError(f"v8_sequence_required:{path}")
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: Iterable[str],
    path: str,
) -> None:
    expected_set = set(expected)
    actual = set(value)
    if actual != expected_set:
        missing = ",".join(sorted(expected_set - actual)) or "none"
        extra = ",".join(sorted(actual - expected_set)) or "none"
        raise RegionResourceV8ValidationError(
            f"v8_exact_keys_failed:{path}:missing={missing}:extra={extra}"
        )


def _require_dataclass_keys(
    cls: type[Any],
    value: Mapping[str, Any],
    path: str,
) -> None:
    _require_exact_keys(value, {item.name for item in fields(cls)}, path)


def _strict_int(value: Any, name: str, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise RegionResourceV8ValidationError(f"v8_integer_required:{name}")
    if minimum is not None and value < minimum:
        raise RegionResourceV8ValidationError(f"v8_integer_below_minimum:{name}")
    return value


def _strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise RegionResourceV8ValidationError(f"v8_boolean_required:{name}")
    return value


def _finite_float(
    value: Any,
    name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if type(value) not in {int, float} or not isfinite(float(value)):
        raise RegionResourceV8ValidationError(f"v8_finite_number_required:{name}")
    result = float(value)
    if minimum is not None and result < minimum:
        raise RegionResourceV8ValidationError(f"v8_number_below_minimum:{name}")
    if maximum is not None and result > maximum:
        raise RegionResourceV8ValidationError(f"v8_number_above_maximum:{name}")
    return result


def _unique_nonempty_strings(value: Iterable[Any], name: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RegionResourceV8ValidationError(
                f"v8_nonempty_string_required:{name}"
            )
        if item in seen:
            raise RegionResourceV8ValidationError(f"v8_duplicate_string:{name}")
        seen.add(item)
        result.append(item)
    return tuple(result)


def _validate_sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RegionResourceV8ValidationError(f"v8_sha256_invalid:{name}")
    return value


def _validate_content_sha256(value: Mapping[str, Any], path: str) -> None:
    digest = _validate_sha256(value.get("content_sha256"), f"{path}.content_sha256")
    payload = dict(value)
    payload.pop("content_sha256", None)
    if canonical_v8_sha256(payload) != digest:
        raise RegionResourceV8ValidationError(
            f"v8_content_sha256_mismatch:{path}"
        )


def _validate_git_commit(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) not in {40, 64}
        or any(character.lower() not in "0123456789abcdef" for character in value)
    ):
        raise RegionResourceV8ValidationError("v8_source_git_commit_invalid")
    return value.lower()


def _validate_relative_jsonl_path(value: Any, *, expected_root: str) -> None:
    if not isinstance(value, str) or not value:
        raise RegionResourceV8ValidationError("v8_relative_jsonl_path_required")
    path = Path(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or path.parts[0] != expected_root
        or path.suffix != ".jsonl"
    ):
        raise RegionResourceV8ValidationError(
            f"v8_relative_jsonl_path_invalid:{expected_root}"
        )


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RegionResourceV8ValidationError(
            f"v8_canonical_json_failed:{type(exc).__name__}"
        ) from exc


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegionResourceV8ValidationError(f"v8_duplicate_json_key:{key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise RegionResourceV8ValidationError(f"v8_nonfinite_json_constant:{value}")


def _parse_json_bytes(value: bytes, path: str) -> Any:
    try:
        return json.loads(
            value.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except RegionResourceV8ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegionResourceV8ValidationError(
            f"v8_json_parse_failed:{path}:{type(exc).__name__}"
        ) from exc


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    return _strict_mapping(
        _parse_json_bytes(_read_bytes(path, label), label),
        label,
    )


def _read_jsonl_bytes(value: bytes, label: str) -> tuple[Mapping[str, Any], ...]:
    if not value or not value.endswith(b"\n"):
        raise RegionResourceV8ValidationError(f"v8_jsonl_final_newline_required:{label}")
    result: list[Mapping[str, Any]] = []
    for index, line in enumerate(value.splitlines()):
        if not line.strip():
            raise RegionResourceV8ValidationError(f"v8_jsonl_blank_line:{label}:{index}")
        result.append(
            _strict_mapping(
                _parse_json_bytes(line, f"{label}[{index}]"),
                f"{label}[{index}]",
            )
        )
    return tuple(result)


def _require_regular_readonly_input(path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        error_cls = (
            RegionResourceV8DataUnavailableError
            if not candidate.exists()
            else RegionResourceV8ValidationError
        )
        raise error_cls(f"v8_required_file_missing_or_unsafe:{label}")
    return candidate.resolve()


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RegionResourceV8ValidationError(
            f"v8_file_read_failed:{label}:{type(exc).__name__}"
        ) from exc


def _sha256_file(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RegionResourceV8ValidationError(
            f"v8_file_hash_failed:{path.name}:{type(exc).__name__}"
        ) from exc
    return digest.hexdigest()


def _resolve_inside(root: Path, relative: Path) -> Path:
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RegionResourceV8ValidationError("v8_dataset_path_escape") from exc
    return resolved


__all__ = [
    "LoadedV8Episode",
    "LoadedV8FrozenRequest",
    "LoadedV8TrainDataset",
    "REGION_RESOURCE_V8_DATA_REQUEST_SCHEMA",
    "REGION_RESOURCE_V8_DATASET_MANIFEST_SCHEMA",
    "REGION_RESOURCE_V8_MAIN_SCHEDULE_SCHEMA",
    "REGION_RESOURCE_V8_OFFLINE_LABEL_SCHEMA",
    "REGION_RESOURCE_V8_ONLINE_FRAME_SCHEMA",
    "REGION_RESOURCE_V8_READINESS_SCHEMA",
    "REGION_RESOURCE_V8_SEED_REGISTRY_SCHEMA",
    "RegionResourceV8ContractError",
    "RegionResourceV8DataUnavailableError",
    "RegionResourceV8ValidationError",
    "V8AnonymousRawActorAction",
    "V8AnonymousTransferCandidate",
    "V8DirectedEdgeState",
    "V8EpisodeManifestEntry",
    "V8MainGenerationSchedule",
    "V8MainGenerationScheduleEntry",
    "V8NoAuthorityPermissions",
    "V8OfflineTransferLabel",
    "V8OnlineRegionResourceFrame",
    "V8PartitionState",
    "V8PreGenerationReadiness",
    "V8R0ActionTuple",
    "V8R0RegionAction",
    "V8RegionResourceState",
    "V8RequestScheduleEntry",
    "V8TrainDatasetManifest",
    "V8Transfer",
    "V8TransferClass",
    "V8_COMMUNICATION_CONDITIONS",
    "V8_FALSE_PERMISSIONS",
    "V8_HARD_NEGATIVE_REASONS",
    "V8_LOADED_STATUS",
    "V8_REQUESTED_SEEDS",
    "V8_REQUEST_STATUS",
    "V8_SUPPLY_DEMAND_CONDITIONS",
    "V8_TOPOLOGY_REGION_COUNTS",
    "V8_TRANSFER_CLASSES",
    "canonical_v8_json_line",
    "canonical_v8_sha256",
    "classify_v8_edge_direction",
    "expected_v8_directed_edges",
    "load_v8_development_train_dataset",
    "load_v8_episode_pair",
    "load_v8_frozen_request",
    "load_v8_main_generation_schedule",
    "validate_v8_data_request_payload",
    "validate_v8_pre_generation_readiness",
    "validate_v8_seed_registry_payload",
]
