"""Truth-free regional resource advice contracts and deterministic safety gates.

This module is deliberately downstream of D4 authority arbitration.  It can
recommend aggregate regional quotas and neighboring transfers, but it cannot
elect an owner, form a coalition, create a D3 assignment, or authorize D7.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from hashlib import sha256
from math import ceil, floor, isfinite
import json
from typing import Any, Callable, Iterable, Mapping, Sequence

from .models import to_jsonable
from .regional_failover import (
    REGIONAL_FAILOVER_SCHEMA,
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverDecision,
)


REGION_RESOURCE_SNAPSHOT_SCHEMA = "d4-region-resource-snapshot-v1"
REGION_RESOURCE_PLANNING_SNAPSHOT_SCHEMA = "d4-region-resource-snapshot-v2"
REGION_RESOURCE_RECOMMENDATION_SCHEMA = "d4-region-resource-recommendation-v1"
REGION_RESOURCE_ADVISORY_SCHEMA = "d4-region-resource-advisory-v1"
REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA = "d4-region-resource-advisory-v2"
REGION_RESOURCE_CONSUMPTION_SCHEMA = "d4-region-resource-consumption-v1"
REGION_RESOURCE_ADVISORY_PUBLICATION_SCHEMA = (
    "d4-region-resource-advisory-publication-v1"
)
REGION_RESOURCE_SHADOW_REPORT_SCHEMA = "d4-region-resource-shadow-report-v1"
REGION_RESOURCE_FEATURE_SCHEMA = "d4-region-resource-features-v1"
REGION_RESOURCE_AUTHORITY_CAPABILITIES_SCHEMA = (
    "d4-region-resource-authority-capabilities-v1"
)
DETERMINISTIC_RESOURCE_PROJECTOR_NAME = "d4-deterministic-resource-projector"
DETERMINISTIC_RESOURCE_PROJECTOR_VERSION = "v1"

REGION_RESOURCE_PLANNING_REJECTION_ALLOWLIST = frozenset(
    {
        "d3_resource_infeasible",
        "d3_required_member_count_unsatisfied",
    }
)
_PLANNING_HARD_SAFETY_INDICATORS = frozenset(
    {
        "d2_duplicate_track_observed",
        "d2_id_switch_observed",
        "d5_binding_conflict",
        "d5_duplicate_terminal_lock",
        "d5_friend_conflict",
        "d5_identity_conflict",
        "network_partition",
    }
)
_ADVISORY_CONSUMPTION_ONLY_BLOCK_REASONS = frozenset(
    {
        "authority_not_active",
        "coalition_ack_incomplete",
        "fault_fence_active",
        "formal_d4_commit_incomplete",
        "formal_d4_execution_fenced",
    }
)

_FORBIDDEN_ID_KEYS = {
    "actor_id",
    "actor_truth_id",
    "global_track_id",
    "object_truth_id",
    "target_id",
    "target_truth_id",
    "truth_id",
}


class RecommendationSource(str, Enum):
    RULE = "rule"
    LEARNED = "learned"


class AdvisorMode(str, Enum):
    DISABLED = "disabled"
    SHADOW = "shadow"
    ASSIST = "assist"


class RegionResourceAdvisoryPublicationCode(str, Enum):
    """Stable main-facing result codes for publication-time authority checks."""

    CURRENT_GENERATION_ACCEPTED = "current_generation_accepted"
    ADVISORY_CONTRACT_REJECTED = "advisory_contract_rejected"
    ADVISORY_EXPIRED = "advisory_expired"
    SOURCE_SNAPSHOT_STALE = "source_snapshot_stale"
    SOURCE_REGION_SET_MISMATCH = "source_region_set_mismatch"
    SOURCE_PLAN_ID_SUPERSEDED = "source_plan_id_superseded"
    SOURCE_PLAN_VERSION_SUPERSEDED = "source_plan_version_superseded"
    SOURCE_AUTHORITY_EPOCH_SUPERSEDED = "source_authority_epoch_superseded"
    SOURCE_AUTHORITY_LEASE_MISMATCH = "source_authority_lease_mismatch"
    CURRENT_AUTHORITY_LEASE_EXPIRED = "current_authority_lease_expired"
    CURRENT_GENERATION_ROLLBACK = "current_generation_rollback"
    CURRENT_GENERATION_CONFLICT = "current_generation_conflict"
    SAME_IDENTITY_LEASE_RENEWAL_FORBIDDEN = (
        "same_identity_lease_renewal_forbidden"
    )
    SAME_IDENTITY_LEASE_CHANGE_FORBIDDEN = "same_identity_lease_change_forbidden"
    AUTHORITY_BINDING_MISMATCH = "authority_binding_mismatch"


@dataclass(frozen=True)
class RegionResourceAuthorityCapabilities:
    """Formal D4 capabilities without turning planning into execution authority."""

    region_id: str
    source_action: RegionalAction | str
    source_reason: str
    source_rejection_reasons: tuple[str, ...]
    source_risk_factors: tuple[str, ...]
    source_decision_sha256: str
    planning_replan_eligible: bool
    assignment_execution_authorized: bool
    coalition_execution_authorized: bool
    takeover_execution_authorized: bool
    control_execution_authorized: bool
    coalition_ack_complete: bool
    network_partitioned: bool
    fault_generation_fenced: bool
    capability_sha256: str = ""
    schema: str = REGION_RESOURCE_AUTHORITY_CAPABILITIES_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_AUTHORITY_CAPABILITIES_SCHEMA:
            raise ValueError("unsupported region authority capabilities schema")
        if not self.region_id or not self.source_reason:
            raise ValueError("authority capability region and source reason must not be empty")
        action = (
            self.source_action
            if isinstance(self.source_action, RegionalAction)
            else RegionalAction(str(self.source_action))
        )
        object.__setattr__(self, "source_action", action)
        object.__setattr__(
            self,
            "source_rejection_reasons",
            _unique(self.source_rejection_reasons),
        )
        object.__setattr__(
            self,
            "source_risk_factors",
            _unique(self.source_risk_factors),
        )
        for name in (
            "planning_replan_eligible",
            "assignment_execution_authorized",
            "coalition_execution_authorized",
            "takeover_execution_authorized",
            "control_execution_authorized",
            "coalition_ack_complete",
            "network_partitioned",
            "fault_generation_fenced",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if not _valid_sha256(self.source_decision_sha256):
            raise ValueError("source_decision_sha256 must be a SHA-256 digest")
        if self.coalition_execution_authorized and not self.assignment_execution_authorized:
            raise ValueError("coalition execution requires assignment execution authority")
        if self.takeover_execution_authorized and not self.control_execution_authorized:
            raise ValueError("takeover execution requires control execution authority")
        if self.control_execution_authorized != self.assignment_execution_authorized:
            raise ValueError(
                "formal assignment and control execution authority must agree"
            )
        if self.planning_replan_eligible:
            if action != RegionalAction.REQUEST_CENTER_REPLAN:
                raise ValueError(
                    "planning-only eligibility requires request_center_replan"
                )
            rejection_set = set(self.source_rejection_reasons)
            if (
                not rejection_set
                or not rejection_set.issubset(
                    REGION_RESOURCE_PLANNING_REJECTION_ALLOWLIST
                )
            ):
                raise ValueError(
                    "planning-only eligibility requires only allowlisted D3 shortages"
                )
            if any(
                (
                    self.assignment_execution_authorized,
                    self.coalition_execution_authorized,
                    self.takeover_execution_authorized,
                    self.control_execution_authorized,
                )
            ):
                raise ValueError(
                    "planning-only eligibility cannot grant execution authority"
                )
            if (
                not self.coalition_ack_complete
                or self.network_partitioned
                or self.fault_generation_fenced
                or _has_planning_hard_safety_indicator(
                    (
                        self.source_reason,
                        *self.source_rejection_reasons,
                        *self.source_risk_factors,
                    )
                )
            ):
                raise ValueError("planning-only eligibility violates a hard safety fence")
        expected_digest = _authority_capability_digest(self)
        if self.capability_sha256 and self.capability_sha256 != expected_digest:
            raise ValueError("authority capability SHA-256 does not match content")
        object.__setattr__(self, "capability_sha256", expected_digest)

    @classmethod
    def from_formal_decision(
        cls,
        decision: RegionalFailoverDecision,
        region_decision: Any,
        *,
        coalition_ack_complete: bool,
        fault_generation_fenced: bool,
    ) -> "RegionResourceAuthorityCapabilities":
        rejections = _unique(region_decision.rejection_reasons)
        network_partitioned = bool(
            region_decision.reason == "network_partition"
            or "network_partition" in set(rejections)
        )
        execution_authorized = bool(region_decision.execution_allowed)
        commits_complete = bool(
            coalition_ack_complete
            and all(
                (not commit.commit_required) or commit.execution_authorized
                for commit in region_decision.coalition_commits
            )
        )
        ownership = region_decision.ownership
        planning_replan_eligible = bool(
            region_decision.selected_layer == RegionalAuthorityLayer.CENTER
            and ownership.owner_layer == RegionalAuthorityLayer.CENTER
            and ownership.owner_role == "center"
            and bool(ownership.owner_id)
            and region_decision.action == RegionalAction.REQUEST_CENTER_REPLAN
            and float(decision.timestamp_s) < float(ownership.lease_expires_at_s)
            and bool(rejections)
            and set(rejections).issubset(
                REGION_RESOURCE_PLANNING_REJECTION_ALLOWLIST
            )
            and not execution_authorized
            and commits_complete
            and not network_partitioned
            and not fault_generation_fenced
            and not _has_planning_hard_safety_indicator(
                (
                    region_decision.reason,
                    *rejections,
                    *region_decision.risk_factors,
                )
            )
        )
        return cls(
            region_id=region_decision.region_id,
            source_action=region_decision.action,
            source_reason=region_decision.reason,
            source_rejection_reasons=rejections,
            source_risk_factors=_unique(region_decision.risk_factors),
            source_decision_sha256=str(formal_decision_digest(decision)),
            planning_replan_eligible=planning_replan_eligible,
            assignment_execution_authorized=execution_authorized,
            coalition_execution_authorized=bool(
                execution_authorized and commits_complete
            ),
            takeover_execution_authorized=bool(
                execution_authorized
                and region_decision.selected_layer
                in {
                    RegionalAuthorityLayer.SECONDARY,
                    RegionalAuthorityLayer.DISTRIBUTED,
                }
            ),
            control_execution_authorized=execution_authorized,
            coalition_ack_complete=commits_complete,
            network_partitioned=network_partitioned,
            fault_generation_fenced=bool(fault_generation_fenced),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceAuthorityCapabilities":
        _reject_truth_identifiers(value, path="region.authority_capabilities")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceNode:
    """One aggregate, online-safe region node.

    Target identity is intentionally absent.  Demand and perception inputs are
    aggregate scalars only.
    """

    region_id: str
    target_demand: float
    high_threat_backlog: float
    d1_uncertainty: float
    d2_uncertainty: float
    d5_visibility: float
    d5_consistency: float
    available_resources: int
    reserve_resources: int
    secondary_coverage: float
    secondary_readiness: float
    communication_capacity: float
    communication_latency_s: float
    packet_loss_rate: float
    current_owner_id: str | None
    current_owner_layer: RegionalAuthorityLayer | str
    plan_id: str
    plan_version: int
    epoch: int
    lease_expires_at_s: float
    committed_resources: int = 0
    coalition_ack_complete: bool = True
    owner_active: bool = True
    fault_fenced: bool = False
    fault_fence_epoch: int | None = None
    assignment_conflict_count: int = 0
    degradation_failed: bool = False
    fault_generation_fenced: bool = False
    authority_capabilities: RegionResourceAuthorityCapabilities | None = None

    def __post_init__(self) -> None:
        if not self.region_id or not self.plan_id:
            raise ValueError("region_id and plan_id must not be empty")
        layer = (
            self.current_owner_layer
            if isinstance(self.current_owner_layer, RegionalAuthorityLayer)
            else RegionalAuthorityLayer(str(self.current_owner_layer))
        )
        object.__setattr__(self, "current_owner_layer", layer)
        if layer == RegionalAuthorityLayer.HOLD:
            if self.current_owner_id is not None:
                raise ValueError("hold regions must not expose an active owner id")
        elif not self.current_owner_id:
            raise ValueError("active authority layers require current_owner_id")

        for name in (
            "target_demand",
            "high_threat_backlog",
            "d1_uncertainty",
            "d2_uncertainty",
            "communication_capacity",
            "communication_latency_s",
            "lease_expires_at_s",
        ):
            if not _finite_non_negative(getattr(self, name)):
                raise ValueError(f"{name} must be finite and non-negative")
        for name in (
            "d5_visibility",
            "d5_consistency",
            "secondary_coverage",
            "secondary_readiness",
            "packet_loss_rate",
        ):
            if not _unit_interval(getattr(self, name)):
                raise ValueError(f"{name} must be finite and in [0, 1]")
        for name in (
            "available_resources",
            "reserve_resources",
            "committed_resources",
            "plan_version",
            "epoch",
            "assignment_conflict_count",
        ):
            object.__setattr__(
                self,
                name,
                _strict_integer(
                    getattr(self, name),
                    name=name,
                    minimum=0,
                ),
            )
        for name in (
            "coalition_ack_complete",
            "owner_active",
            "fault_fenced",
            "degradation_failed",
            "fault_generation_fenced",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if self.reserve_resources + self.committed_resources > self.available_resources:
            raise ValueError(
                "reserve_resources plus committed_resources exceeds available_resources"
            )
        if self.fault_fence_epoch is not None:
            object.__setattr__(
                self,
                "fault_fence_epoch",
                _strict_integer(
                    self.fault_fence_epoch,
                    name="fault_fence_epoch",
                    minimum=0,
                ),
            )
        capabilities = self.authority_capabilities
        if capabilities is not None and not isinstance(
            capabilities, RegionResourceAuthorityCapabilities
        ):
            capabilities = RegionResourceAuthorityCapabilities.from_dict(capabilities)
            object.__setattr__(self, "authority_capabilities", capabilities)
        if capabilities is not None:
            if capabilities.region_id != self.region_id:
                raise ValueError("authority capability region does not match node")
            if (
                capabilities.planning_replan_eligible
                and layer != RegionalAuthorityLayer.CENTER
            ):
                raise ValueError("planning-only eligibility requires a center owner")
            if (
                capabilities.fault_generation_fenced
                != self.fault_generation_fenced
            ):
                raise ValueError(
                    "authority capability fault generation does not match node"
                )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceNode":
        _reject_truth_identifiers(value)
        payload = dict(value)
        required_authority_fields = {
            "current_owner_id",
            "current_owner_layer",
            "plan_id",
            "plan_version",
            "epoch",
            "lease_expires_at_s",
            "coalition_ack_complete",
            "owner_active",
            "fault_fenced",
        }
        missing = sorted(required_authority_fields - set(value))
        if missing:
            raise ValueError(
                "region authority fields missing: " + ",".join(missing)
            )
        if payload.get("authority_capabilities") is not None:
            payload["authority_capabilities"] = (
                RegionResourceAuthorityCapabilities.from_dict(
                    payload["authority_capabilities"]
                )
            )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceEdge:
    """One maneuver and communication edge between adjacent regions."""

    source_region_id: str
    target_region_id: str
    transferable_resources: int
    distance_m: float
    transfer_time_s: float
    bandwidth_mbps: float
    communication_available: bool = True
    maneuver_available: bool = True
    partitioned: bool = False
    bidirectional: bool = True
    edge_id: str = ""

    def __post_init__(self) -> None:
        if not self.source_region_id or not self.target_region_id:
            raise ValueError("edge endpoints must not be empty")
        if self.source_region_id == self.target_region_id:
            raise ValueError("region resource edges must not be self loops")
        if int(self.transferable_resources) < 0:
            raise ValueError("transferable_resources must be non-negative")
        for name in ("distance_m", "transfer_time_s", "bandwidth_mbps"):
            if not _finite_non_negative(getattr(self, name)):
                raise ValueError(f"{name} must be finite and non-negative")
        if not self.edge_id:
            direction = "bi" if self.bidirectional else "directed"
            object.__setattr__(
                self,
                "edge_id",
                f"{self.source_region_id}->{self.target_region_id}:{direction}",
            )

    @property
    def open_for_transfer(self) -> bool:
        return bool(
            self.transferable_resources > 0
            and self.bandwidth_mbps > 0.0
            and self.communication_available
            and self.maneuver_available
            and not self.partitioned
        )

    def permits(self, source_region_id: str, target_region_id: str) -> bool:
        if (
            source_region_id == self.source_region_id
            and target_region_id == self.target_region_id
        ):
            return True
        return bool(
            self.bidirectional
            and source_region_id == self.target_region_id
            and target_region_id == self.source_region_id
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceEdge":
        _reject_truth_identifiers(value)
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceSnapshot:
    """Versioned regional graph snapshot on the caller's episode clock."""

    snapshot_id: str
    scenario_id: str
    scenario_version: str
    seed: int
    timestamp_s: float
    regions: tuple[RegionResourceNode, ...]
    edges: tuple[RegionResourceEdge, ...]
    authority_digest: str = ""
    source_authority_schema: str = REGIONAL_FAILOVER_SCHEMA
    feature_schema: str = REGION_RESOURCE_FEATURE_SCHEMA
    snapshot_version: int = 1
    planning_authority_digest: str = ""
    schema: str = REGION_RESOURCE_SNAPSHOT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema not in {
            REGION_RESOURCE_SNAPSHOT_SCHEMA,
            REGION_RESOURCE_PLANNING_SNAPSHOT_SCHEMA,
        }:
            raise ValueError(f"unsupported region resource schema: {self.schema}")
        if self.feature_schema != REGION_RESOURCE_FEATURE_SCHEMA:
            raise ValueError(f"unsupported feature schema: {self.feature_schema}")
        if int(self.snapshot_version) != 1:
            raise ValueError("unsupported region resource snapshot version")
        if not self.snapshot_id or not self.scenario_id or not self.scenario_version:
            raise ValueError("snapshot and scenario identity must not be empty")
        if int(self.seed) < 0:
            raise ValueError("seed must be non-negative")
        if not _finite_non_negative(self.timestamp_s):
            raise ValueError("timestamp_s must be finite and non-negative")
        regions = tuple(self.regions)
        edges = tuple(self.edges)
        if not regions:
            raise ValueError("a region resource snapshot requires at least one region")
        object.__setattr__(self, "regions", regions)
        object.__setattr__(self, "edges", edges)
        region_ids = tuple(region.region_id for region in regions)
        if len(set(region_ids)) != len(region_ids):
            raise ValueError("region resource node ids must be unique")
        known = set(region_ids)
        edge_ids = tuple(edge.edge_id for edge in edges)
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("region resource edge ids must be unique")
        if any(
            edge.source_region_id not in known or edge.target_region_id not in known
            for edge in edges
        ):
            raise ValueError("all region resource edge endpoints must be known")
        authority_rebuild_requested = not self.authority_digest
        expected_digest = _authority_digest(regions)
        if self.authority_digest and self.authority_digest != expected_digest:
            raise ValueError("authority_digest does not match regional authority fields")
        object.__setattr__(self, "authority_digest", expected_digest)
        if self.schema == REGION_RESOURCE_SNAPSHOT_SCHEMA:
            if self.planning_authority_digest or any(
                node.authority_capabilities is not None
                or node.fault_generation_fenced
                for node in regions
            ):
                raise ValueError(
                    "legacy snapshot-v1 cannot carry planning authority capability"
                )
            object.__setattr__(self, "planning_authority_digest", "")
        else:
            expected_planning_digest = _planning_authority_digest(
                regions,
                source_authority_schema=self.source_authority_schema,
                authority_digest=expected_digest,
            )
            if (
                self.planning_authority_digest
                and self.planning_authority_digest != expected_planning_digest
                and not authority_rebuild_requested
            ):
                raise ValueError(
                    "planning_authority_digest does not match planning capabilities"
                )
            if not any(
                node.authority_capabilities is not None for node in regions
            ):
                raise ValueError(
                    "planning snapshot-v2 requires authority capabilities"
                )
            object.__setattr__(
                self,
                "planning_authority_digest",
                expected_planning_digest,
            )

    @property
    def region_count(self) -> int:
        return len(self.regions)

    @property
    def total_resources(self) -> int:
        return sum(region.available_resources for region in self.regions)

    @property
    def scenario_seed_group(self) -> tuple[str, int]:
        return (self.scenario_id, int(self.seed))

    @property
    def region_by_id(self) -> dict[str, RegionResourceNode]:
        return {region.region_id: region for region in self.regions}

    def to_dict(self) -> dict[str, Any]:
        payload = to_jsonable(self)
        if self.schema == REGION_RESOURCE_SNAPSHOT_SCHEMA:
            return _legacy_region_resource_snapshot_payload(payload)
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceSnapshot":
        _reject_truth_identifiers(value)
        payload = dict(value)
        payload["regions"] = tuple(
            RegionResourceNode.from_dict(item) for item in payload.get("regions", ())
        )
        payload["edges"] = tuple(
            RegionResourceEdge.from_dict(item) for item in payload.get("edges", ())
        )
        return cls(**payload)

    @classmethod
    def from_regional_decision(
        cls,
        decision: RegionalFailoverDecision,
        *,
        snapshot_id: str,
        scenario_id: str,
        scenario_version: str,
        seed: int,
        region_signals: Mapping[str, Mapping[str, Any]],
        edges: Sequence[RegionResourceEdge],
    ) -> "RegionResourceSnapshot":
        """Aggregate a formal D4 verdict without copying task or truth identity."""

        _reject_truth_identifiers(region_signals)
        nodes: list[RegionResourceNode] = []
        for region_decision in decision.region_decisions:
            region_id = region_decision.region_id
            signal = dict(region_signals.get(region_id, {}))
            ownership = region_decision.ownership
            committed_member_ids = {
                member_id
                for commit in region_decision.coalition_commits
                if commit.execution_authorized
                for member_id in commit.required_member_ids
            }
            ack_complete = all(
                (not commit.commit_required) or commit.execution_authorized
                for commit in region_decision.coalition_commits
            )
            ack_complete = bool(
                signal.get("coalition_ack_complete", ack_complete)
            )
            fault_generation_fenced = bool(
                signal.get("fault_generation_fenced", False)
            )
            authority_capabilities = (
                RegionResourceAuthorityCapabilities.from_formal_decision(
                    decision,
                    region_decision,
                    coalition_ack_complete=ack_complete,
                    fault_generation_fenced=fault_generation_fenced,
                )
            )
            nodes.append(
                RegionResourceNode(
                    region_id=region_id,
                    target_demand=float(signal.get("target_demand", len(region_decision.task_ids))),
                    high_threat_backlog=float(signal.get("high_threat_backlog", 0.0)),
                    d1_uncertainty=float(signal.get("d1_uncertainty", 0.0)),
                    d2_uncertainty=float(signal.get("d2_uncertainty", 0.0)),
                    d5_visibility=float(signal.get("d5_visibility", 1.0)),
                    d5_consistency=float(signal.get("d5_consistency", 1.0)),
                    available_resources=int(signal.get("available_resources", 0)),
                    reserve_resources=int(signal.get("reserve_resources", 0)),
                    secondary_coverage=float(signal.get("secondary_coverage", 0.0)),
                    secondary_readiness=float(signal.get("secondary_readiness", 0.0)),
                    communication_capacity=float(
                        signal.get("communication_capacity", 0.0)
                    ),
                    communication_latency_s=float(
                        signal.get("communication_latency_s", 0.0)
                    ),
                    packet_loss_rate=float(signal.get("packet_loss_rate", 0.0)),
                    current_owner_id=ownership.owner_id,
                    current_owner_layer=ownership.owner_layer,
                    plan_id=ownership.plan_id,
                    plan_version=ownership.plan_version,
                    epoch=ownership.epoch,
                    lease_expires_at_s=ownership.lease_expires_at_s,
                    committed_resources=int(
                        signal.get("committed_resources", len(committed_member_ids))
                    ),
                    coalition_ack_complete=ack_complete,
                    owner_active=bool(ownership.active),
                    fault_fenced=bool(
                        signal.get(
                            "fault_fenced",
                            region_decision.fail_closed
                            or not region_decision.execution_allowed,
                        )
                    ),
                    fault_fence_epoch=(
                        int(signal["fault_fence_epoch"])
                        if signal.get("fault_fence_epoch") is not None
                        else None
                    ),
                    assignment_conflict_count=int(
                        signal.get("assignment_conflict_count", 0)
                    ),
                    degradation_failed=bool(
                        signal.get("degradation_failed", region_decision.fail_closed)
                    ),
                    fault_generation_fenced=fault_generation_fenced,
                    authority_capabilities=authority_capabilities,
                )
            )
        planning_contract_required = any(
            node.authority_capabilities is not None
            and node.authority_capabilities.planning_replan_eligible
            for node in nodes
        ) or any(node.fault_generation_fenced for node in nodes)
        if not planning_contract_required:
            nodes = [
                replace(
                    node,
                    fault_generation_fenced=False,
                    authority_capabilities=None,
                )
                for node in nodes
            ]
        return cls(
            snapshot_id=snapshot_id,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            seed=seed,
            timestamp_s=decision.timestamp_s,
            regions=tuple(nodes),
            edges=tuple(edges),
            source_authority_schema=decision.schema,
            schema=(
                REGION_RESOURCE_PLANNING_SNAPSHOT_SCHEMA
                if planning_contract_required
                else REGION_RESOURCE_SNAPSHOT_SCHEMA
            ),
        )


@dataclass(frozen=True)
class RegionResourceAction:
    """Aggregate action advice for one region, never a target assignment."""

    region_id: str
    resource_quota_delta: int
    reserve_ratio: float
    reconnaissance_priority: float
    hold: bool
    request_replan: bool
    expected_owner_id: str | None
    expected_owner_layer: RegionalAuthorityLayer | str
    expected_plan_id: str
    expected_plan_version: int
    expected_epoch: int
    expected_lease_expires_at_s: float
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.region_id or not self.expected_plan_id:
            raise ValueError("action region and plan identity must not be empty")
        layer = (
            self.expected_owner_layer
            if isinstance(self.expected_owner_layer, RegionalAuthorityLayer)
            else RegionalAuthorityLayer(str(self.expected_owner_layer))
        )
        object.__setattr__(self, "expected_owner_layer", layer)
        if not _unit_interval(self.reserve_ratio):
            raise ValueError("reserve_ratio must be in [0, 1]")
        if not _unit_interval(self.reconnaissance_priority):
            raise ValueError("reconnaissance_priority must be in [0, 1]")
        object.__setattr__(
            self,
            "resource_quota_delta",
            _strict_integer(
                self.resource_quota_delta,
                name="resource_quota_delta",
            ),
        )
        object.__setattr__(
            self,
            "expected_plan_version",
            _strict_integer(
                self.expected_plan_version,
                name="expected_plan_version",
                minimum=0,
            ),
        )
        object.__setattr__(
            self,
            "expected_epoch",
            _strict_integer(
                self.expected_epoch,
                name="expected_epoch",
                minimum=0,
            ),
        )
        if not _finite_non_negative(self.expected_lease_expires_at_s):
            raise ValueError("action lease must be finite and non-negative")
        if not isinstance(self.hold, bool) or not isinstance(
            self.request_replan, bool
        ):
            raise ValueError("action hold and request_replan must be booleans")
        object.__setattr__(self, "reasons", _unique(self.reasons))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceAction":
        _reject_truth_identifiers(value, path="recommendation.action")
        required_authority_fields = {
            "expected_owner_id",
            "expected_owner_layer",
            "expected_plan_id",
            "expected_plan_version",
            "expected_epoch",
            "expected_lease_expires_at_s",
        }
        missing = sorted(required_authority_fields - set(value))
        if missing:
            raise ValueError(
                "action authority fields missing: " + ",".join(missing)
            )
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionTransferSuggestion:
    source_region_id: str
    target_region_id: str
    resource_count: int
    edge_id: str
    expected_transfer_time_s: float
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_region_id or not self.target_region_id or not self.edge_id:
            raise ValueError("transfer identity must not be empty")
        if self.source_region_id == self.target_region_id:
            raise ValueError("regional transfers must cross an edge")
        if int(self.resource_count) <= 0:
            raise ValueError("resource_count must be positive")
        if not _finite_non_negative(self.expected_transfer_time_s):
            raise ValueError("expected_transfer_time_s must be finite and non-negative")
        object.__setattr__(self, "reasons", _unique(self.reasons))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionTransferSuggestion":
        _reject_truth_identifiers(value, path="recommendation.transfer")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceRecommendation:
    snapshot_id: str
    scenario_id: str
    scenario_version: str
    seed: int
    authority_digest: str
    created_at_s: float
    policy_name: str
    policy_version: str
    source: RecommendationSource | str
    confidence: float
    actions: tuple[RegionResourceAction, ...]
    transfers: tuple[RegionTransferSuggestion, ...]
    projected: bool = False
    fallback_reason: str | None = None
    model_sha256: str | None = None
    projection_rejections: tuple[str, ...] = ()
    schema: str = REGION_RESOURCE_RECOMMENDATION_SCHEMA
    planning_authority_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_RECOMMENDATION_SCHEMA:
            raise ValueError(f"unsupported recommendation schema: {self.schema}")
        if not self.snapshot_id or not self.scenario_id or not self.scenario_version:
            raise ValueError("recommendation snapshot and scenario identity must not be empty")
        if not self.authority_digest or not self.policy_name or not self.policy_version:
            raise ValueError("authority digest and policy identity must not be empty")
        source = (
            self.source
            if isinstance(self.source, RecommendationSource)
            else RecommendationSource(str(self.source))
        )
        object.__setattr__(self, "source", source)
        if not _unit_interval(self.confidence):
            raise ValueError("recommendation confidence must be in [0, 1]")
        if not _finite_non_negative(self.created_at_s):
            raise ValueError("created_at_s must be finite and non-negative")
        actions = tuple(self.actions)
        transfers = tuple(self.transfers)
        if len({action.region_id for action in actions}) != len(actions):
            raise ValueError("recommendation actions must have unique region ids")
        if self.projected and sum(action.resource_quota_delta for action in actions) != 0:
            raise ValueError("projected recommendation must conserve total resources")
        object.__setattr__(self, "actions", actions)
        object.__setattr__(self, "transfers", transfers)
        object.__setattr__(
            self, "projection_rejections", _unique(self.projection_rejections)
        )
        if (
            self.planning_authority_digest
            and not _valid_sha256(self.planning_authority_digest)
        ):
            raise ValueError(
                "recommendation planning_authority_digest must be a SHA-256 digest"
            )

    @property
    def total_quota_delta(self) -> int:
        return sum(action.resource_quota_delta for action in self.actions)

    def to_dict(self) -> dict[str, Any]:
        payload = to_jsonable(self)
        if not self.planning_authority_digest:
            payload.pop("planning_authority_digest", None)
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceRecommendation":
        _reject_truth_identifiers(value, path="recommendation")
        payload = dict(value)
        payload["actions"] = tuple(
            RegionResourceAction.from_dict(item) for item in payload.get("actions", ())
        )
        payload["transfers"] = tuple(
            RegionTransferSuggestion.from_dict(item)
            for item in payload.get("transfers", ())
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceSourceVersion:
    """Authority and plan generation used by one advisory item."""

    region_id: str
    snapshot_id: str
    snapshot_version: int
    authority_digest: str
    owner_id: str | None
    owner_layer: RegionalAuthorityLayer | str
    plan_id: str
    plan_version: int
    epoch: int
    lease_expires_at_s: float
    coalition_ack_complete: bool
    owner_active: bool
    fault_fenced: bool
    fault_fence_epoch: int | None = None
    planning_authority_digest: str = ""
    authority_capabilities: RegionResourceAuthorityCapabilities | None = None

    def __post_init__(self) -> None:
        if not self.region_id or not self.snapshot_id or not self.authority_digest:
            raise ValueError("source region, snapshot, and authority identity must not be empty")
        if not self.plan_id:
            raise ValueError("source plan identity must not be empty")
        layer = (
            self.owner_layer
            if isinstance(self.owner_layer, RegionalAuthorityLayer)
            else RegionalAuthorityLayer(str(self.owner_layer))
        )
        object.__setattr__(self, "owner_layer", layer)
        if layer == RegionalAuthorityLayer.HOLD:
            if self.owner_id is not None:
                raise ValueError("hold source versions must not expose an owner id")
        elif not self.owner_id:
            raise ValueError("active source versions require an owner id")
        if int(self.snapshot_version) <= 0:
            raise ValueError("source snapshot_version must be positive")
        if int(self.plan_version) < 0 or int(self.epoch) < 0:
            raise ValueError("source plan_version and epoch must be non-negative")
        if not _finite_non_negative(self.lease_expires_at_s):
            raise ValueError("source lease must be finite and non-negative")
        if self.fault_fence_epoch is not None and int(self.fault_fence_epoch) < 0:
            raise ValueError("source fault_fence_epoch must be non-negative")
        if (
            self.planning_authority_digest
            and not _valid_sha256(self.planning_authority_digest)
        ):
            raise ValueError(
                "source planning_authority_digest must be a SHA-256 digest"
            )
        capabilities = self.authority_capabilities
        if capabilities is not None and not isinstance(
            capabilities, RegionResourceAuthorityCapabilities
        ):
            capabilities = RegionResourceAuthorityCapabilities.from_dict(capabilities)
            object.__setattr__(self, "authority_capabilities", capabilities)
        if capabilities is not None:
            if capabilities.region_id != self.region_id:
                raise ValueError(
                    "source authority capabilities do not match source region"
                )
            if not self.planning_authority_digest:
                raise ValueError(
                    "source authority capabilities require planning authority digest"
                )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceSourceVersion":
        _reject_truth_identifiers(value, path="advisory.source_version")
        payload = dict(value)
        if payload.get("authority_capabilities") is not None:
            payload["authority_capabilities"] = (
                RegionResourceAuthorityCapabilities.from_dict(
                    payload["authority_capabilities"]
                )
            )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceAdvisoryRegion:
    """Self-contained resource and safety proof for one regional action."""

    source_version: RegionResourceSourceVersion
    resources_before: int
    resource_quota_delta: int
    resources_after: int
    protected_reserve_resources: int
    protected_committed_resources: int
    reserve_ratio: float
    reconnaissance_priority: float
    hold: bool
    request_replan: bool
    reasons: tuple[str, ...] = ()
    planning_only: bool = False

    def __post_init__(self) -> None:
        for name in (
            "resources_before",
            "protected_reserve_resources",
            "protected_committed_resources",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.resources_after != self.resources_before + self.resource_quota_delta:
            raise ValueError("regional resource proof does not match its quota delta")
        if not _unit_interval(self.reserve_ratio):
            raise ValueError("advisory reserve_ratio must be in [0, 1]")
        if not _unit_interval(self.reconnaissance_priority):
            raise ValueError("advisory reconnaissance_priority must be in [0, 1]")
        if type(self.planning_only) is not bool:
            raise ValueError("advisory planning_only must be a boolean")
        if self.planning_only:
            capabilities = self.source_version.authority_capabilities
            if (
                capabilities is None
                or not capabilities.planning_replan_eligible
                or not self.request_replan
                or self.hold
                or self.resource_quota_delta < 0
            ):
                raise ValueError(
                    "planning-only region lacks a valid receive/replan capability"
                )
        object.__setattr__(self, "reasons", _unique(self.reasons))

    @property
    def region_id(self) -> str:
        return self.source_version.region_id

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceAdvisoryRegion":
        _reject_truth_identifiers(value, path="advisory.region")
        payload = dict(value)
        payload["source_version"] = RegionResourceSourceVersion.from_dict(
            payload["source_version"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceAdvisoryTransfer:
    """One adjacent transfer with endpoint generations and edge-capacity proof."""

    source_version: RegionResourceSourceVersion
    target_version: RegionResourceSourceVersion
    resource_count: int
    edge_id: str
    edge_source_region_id: str
    edge_target_region_id: str
    edge_capacity_resources: int
    expected_transfer_time_s: float
    bandwidth_mbps: float
    communication_available: bool
    maneuver_available: bool
    partitioned: bool
    bidirectional: bool
    reasons: tuple[str, ...] = ()
    planning_only_target: bool = False

    def __post_init__(self) -> None:
        if not self.edge_id or not self.edge_source_region_id or not self.edge_target_region_id:
            raise ValueError("advisory transfer edge identity must not be empty")
        if self.source_version.region_id == self.target_version.region_id:
            raise ValueError("advisory transfers must cross regions")
        if int(self.resource_count) <= 0:
            raise ValueError("advisory transfer resource_count must be positive")
        if int(self.edge_capacity_resources) < 0:
            raise ValueError("advisory edge capacity must be non-negative")
        if not _finite_non_negative(self.expected_transfer_time_s):
            raise ValueError("advisory transfer time must be finite and non-negative")
        if not _finite_non_negative(self.bandwidth_mbps):
            raise ValueError("advisory bandwidth must be finite and non-negative")
        if type(self.planning_only_target) is not bool:
            raise ValueError("planning_only_target must be a boolean")
        if self.planning_only_target:
            capabilities = self.target_version.authority_capabilities
            if (
                capabilities is None
                or not capabilities.planning_replan_eligible
            ):
                raise ValueError(
                    "planning-only transfer target lacks planning eligibility"
                )
        object.__setattr__(self, "reasons", _unique(self.reasons))

    @property
    def source_region_id(self) -> str:
        return self.source_version.region_id

    @property
    def target_region_id(self) -> str:
        return self.target_version.region_id

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceAdvisoryTransfer":
        _reject_truth_identifiers(value, path="advisory.transfer")
        payload = dict(value)
        payload["source_version"] = RegionResourceSourceVersion.from_dict(
            payload["source_version"]
        )
        payload["target_version"] = RegionResourceSourceVersion.from_dict(
            payload["target_version"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceAdvisoryContract:
    """Versioned, truth-free advice eligible for a later D3 planning input."""

    advisory_id: str
    snapshot_id: str
    snapshot_version: int
    snapshot_timestamp_s: float
    scenario_id: str
    scenario_version: str
    seed: int
    authority_digest: str
    created_at_s: float
    valid_from_s: float
    valid_until_s: float
    source_plan_versions: tuple[tuple[str, int], ...]
    projected: bool
    projector_name: str
    projector_version: str
    minimum_reserve_ratio: float
    minimum_reserve_resources: int
    advisory_ttl_s: float
    policy_name: str
    policy_version: str
    source: RecommendationSource | str
    confidence: float
    model_sha256: str | None
    fallback_reason: str | None
    total_resources_before: int
    total_quota_delta: int
    total_resources_after: int
    regions: tuple[RegionResourceAdvisoryRegion, ...]
    transfers: tuple[RegionResourceAdvisoryTransfer, ...]
    projection_rejections: tuple[str, ...]
    publication_rejections: tuple[str, ...]
    formal_decision_required: bool
    recommendation_schema: str = REGION_RESOURCE_RECOMMENDATION_SCHEMA
    schema: str = REGION_RESOURCE_ADVISORY_SCHEMA
    planning_authority_digest: str = ""
    planning_only_region_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema not in {
            REGION_RESOURCE_ADVISORY_SCHEMA,
            REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA,
        }:
            raise ValueError(f"unsupported advisory schema: {self.schema}")
        if self.recommendation_schema != REGION_RESOURCE_RECOMMENDATION_SCHEMA:
            raise ValueError(
                f"unsupported recommendation schema: {self.recommendation_schema}"
            )
        if not self.snapshot_id or not self.scenario_id or not self.scenario_version:
            raise ValueError("advisory snapshot and scenario identity must not be empty")
        if not self.authority_digest or not self.policy_name or not self.policy_version:
            raise ValueError("advisory authority and policy identity must not be empty")
        if not self.projector_name or not self.projector_version:
            raise ValueError("advisory projector identity must not be empty")
        source = (
            self.source
            if isinstance(self.source, RecommendationSource)
            else RecommendationSource(str(self.source))
        )
        object.__setattr__(self, "source", source)
        if int(self.snapshot_version) <= 0 or int(self.seed) < 0:
            raise ValueError("advisory snapshot_version must be positive and seed non-negative")
        for name in (
            "snapshot_timestamp_s",
            "created_at_s",
            "valid_from_s",
            "valid_until_s",
            "advisory_ttl_s",
        ):
            if not _finite_non_negative(getattr(self, name)):
                raise ValueError(f"{name} must be finite and non-negative")
        if not _unit_interval(self.minimum_reserve_ratio):
            raise ValueError("minimum_reserve_ratio must be in [0, 1]")
        if int(self.minimum_reserve_resources) < 0:
            raise ValueError("minimum_reserve_resources must be non-negative")
        if not _unit_interval(self.confidence):
            raise ValueError("advisory confidence must be in [0, 1]")
        for name in (
            "total_resources_before",
            "total_resources_after",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")

        regions = tuple(self.regions)
        transfers = tuple(self.transfers)
        if len({region.region_id for region in regions}) != len(regions):
            raise ValueError("advisory regions must be unique")
        object.__setattr__(self, "regions", regions)
        object.__setattr__(self, "transfers", transfers)
        source_plans = tuple(
            sorted(
                {(str(plan_id), int(plan_version)) for plan_id, plan_version in self.source_plan_versions}
            )
        )
        if any(not plan_id or plan_version < 0 for plan_id, plan_version in source_plans):
            raise ValueError("advisory source plan identity is invalid")
        object.__setattr__(self, "source_plan_versions", source_plans)
        object.__setattr__(
            self, "projection_rejections", _unique(self.projection_rejections)
        )
        object.__setattr__(
            self, "publication_rejections", _unique(self.publication_rejections)
        )
        planning_only_region_ids = _unique(self.planning_only_region_ids)
        if not set(planning_only_region_ids).issubset(
            {region.region_id for region in regions}
        ):
            raise ValueError("planning-only advisory regions must be known")
        object.__setattr__(
            self,
            "planning_only_region_ids",
            planning_only_region_ids,
        )
        if planning_only_region_ids:
            if self.schema != REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA:
                raise ValueError(
                    "planning-only advisory requires advisory-v2 schema"
                )
            if not _valid_sha256(self.planning_authority_digest):
                raise ValueError(
                    "planning-only advisory requires planning authority digest"
                )
            for region in regions:
                if region.region_id in set(planning_only_region_ids):
                    if not region.planning_only:
                        raise ValueError(
                            "planning-only advisory region marker is inconsistent"
                        )
                elif region.planning_only:
                    raise ValueError(
                        "unlisted region cannot carry planning-only capability"
                    )
        elif any(region.planning_only for region in regions):
            raise ValueError("planning-only region list is missing")
        elif (
            self.schema != REGION_RESOURCE_ADVISORY_SCHEMA
            or self.planning_authority_digest
        ):
            raise ValueError(
                "legacy advisory-v1 cannot carry planning-only capability"
            )
        expected_id = _region_resource_advisory_id(self)
        if self.advisory_id and self.advisory_id != expected_id:
            raise ValueError("advisory_id does not match advisory content")
        object.__setattr__(self, "advisory_id", expected_id)

    def to_dict(self) -> dict[str, Any]:
        payload = to_jsonable(self)
        if self.schema == REGION_RESOURCE_ADVISORY_SCHEMA:
            return _legacy_region_resource_advisory_payload(payload)
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceAdvisoryContract":
        _reject_truth_identifiers(value, path="advisory")
        payload = dict(value)
        payload["source_plan_versions"] = tuple(
            (str(item[0]), int(item[1]))
            for item in payload.get("source_plan_versions", ())
        )
        payload["regions"] = tuple(
            RegionResourceAdvisoryRegion.from_dict(item)
            for item in payload.get("regions", ())
        )
        payload["transfers"] = tuple(
            RegionResourceAdvisoryTransfer.from_dict(item)
            for item in payload.get("transfers", ())
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceConsumptionView:
    """Point-in-time fail-closed verdict for one advisory consumption attempt."""

    advisory: RegionResourceAdvisoryContract
    evaluated_at_s: float
    current_snapshot_id: str
    current_snapshot_version: int
    current_authority_digest: str
    consumable: bool
    rejection_reasons: tuple[str, ...]
    schema: str = REGION_RESOURCE_CONSUMPTION_SCHEMA
    planning_replan_eligible: bool = False
    execution_authorized: bool = False
    assignment_execution_authorized: bool = False
    coalition_execution_authorized: bool = False
    takeover_execution_authorized: bool = False
    control_execution_authorized: bool = False

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_CONSUMPTION_SCHEMA:
            raise ValueError(f"unsupported advisory consumption schema: {self.schema}")
        if not _finite_non_negative(self.evaluated_at_s):
            raise ValueError("consumption evaluation time must be finite and non-negative")
        if not self.current_snapshot_id or not self.current_authority_digest:
            raise ValueError("current snapshot and authority identity must not be empty")
        if int(self.current_snapshot_version) <= 0:
            raise ValueError("current_snapshot_version must be positive")
        reasons = _unique(self.rejection_reasons)
        if self.consumable and reasons:
            raise ValueError("a consumable advisory must not have rejection reasons")
        for name in (
            "planning_replan_eligible",
            "execution_authorized",
            "assignment_execution_authorized",
            "coalition_execution_authorized",
            "takeover_execution_authorized",
            "control_execution_authorized",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if any(
            (
                self.execution_authorized,
                self.assignment_execution_authorized,
                self.coalition_execution_authorized,
                self.takeover_execution_authorized,
                self.control_execution_authorized,
            )
        ):
            raise ValueError(
                "regional advisory consumption cannot grant execution authority"
            )
        if self.planning_replan_eligible and not self.consumable:
            raise ValueError(
                "rejected advisory cannot expose planning replan eligibility"
            )
        object.__setattr__(self, "rejection_reasons", reasons)

    @property
    def advisory_id(self) -> str:
        return self.advisory.advisory_id

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class RegionResourceAuthorityGeneration:
    """One truth-free authority generation used at advice publication time."""

    region_id: str
    owner_id: str | None
    owner_layer: RegionalAuthorityLayer | str
    plan_id: str
    plan_version: int
    authority_epoch: int
    lease_expires_at_s: float

    def __post_init__(self) -> None:
        if not self.region_id or not self.plan_id:
            raise ValueError("publication authority region and plan must not be empty")
        layer = (
            self.owner_layer
            if isinstance(self.owner_layer, RegionalAuthorityLayer)
            else RegionalAuthorityLayer(str(self.owner_layer))
        )
        object.__setattr__(self, "owner_layer", layer)
        if layer == RegionalAuthorityLayer.HOLD:
            if self.owner_id is not None:
                raise ValueError("hold publication authority cannot expose an owner")
        elif not self.owner_id:
            raise ValueError("active publication authority requires an owner")
        object.__setattr__(
            self,
            "plan_version",
            _strict_integer(self.plan_version, name="plan_version", minimum=0),
        )
        object.__setattr__(
            self,
            "authority_epoch",
            _strict_integer(
                self.authority_epoch,
                name="authority_epoch",
                minimum=0,
            ),
        )
        if not _finite_non_negative(self.lease_expires_at_s):
            raise ValueError(
                "publication authority lease must be finite and non-negative"
            )

    @property
    def immutable_identity(self) -> tuple[str | None, str, str, int, int]:
        return (
            self.owner_id,
            self.owner_layer.value,
            self.plan_id,
            self.plan_version,
            self.authority_epoch,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "RegionResourceAuthorityGeneration":
        _reject_truth_identifiers(value, path="advisory.publication_generation")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionResourceAdvisoryPublicationDecision:
    """Separate diagnostic publication from downstream planning consumption."""

    advisory: RegionResourceAdvisoryContract
    publication_timestamp_s: float
    current_snapshot_id: str
    current_snapshot_version: int
    current_authority_digest: str
    source_generations: tuple[RegionResourceAuthorityGeneration, ...]
    current_generations: tuple[RegionResourceAuthorityGeneration, ...]
    generation_publishable: bool
    planning_consumable: bool
    publication_reason_code: RegionResourceAdvisoryPublicationCode | str
    publication_rejection_codes: tuple[
        RegionResourceAdvisoryPublicationCode | str, ...
    ]
    publication_rejection_reasons: tuple[str, ...]
    planning_rejection_reasons: tuple[str, ...]
    schema: str = REGION_RESOURCE_ADVISORY_PUBLICATION_SCHEMA
    assignment_execution_authorized: bool = False
    coalition_execution_authorized: bool = False
    takeover_execution_authorized: bool = False
    control_execution_authorized: bool = False

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_ADVISORY_PUBLICATION_SCHEMA:
            raise ValueError("unsupported region resource publication schema")
        if not _finite_non_negative(self.publication_timestamp_s):
            raise ValueError(
                "publication_timestamp_s must be finite and non-negative"
            )
        if not self.current_snapshot_id or not self.current_authority_digest:
            raise ValueError(
                "publication current snapshot and authority must not be empty"
            )
        if int(self.current_snapshot_version) <= 0:
            raise ValueError("publication current snapshot version must be positive")
        if type(self.generation_publishable) is not bool:
            raise ValueError("generation_publishable must be a boolean")
        if type(self.planning_consumable) is not bool:
            raise ValueError("planning_consumable must be a boolean")
        reason_code = (
            self.publication_reason_code
            if isinstance(
                self.publication_reason_code,
                RegionResourceAdvisoryPublicationCode,
            )
            else RegionResourceAdvisoryPublicationCode(
                str(self.publication_reason_code)
            )
        )
        rejection_codes = tuple(
            code
            if isinstance(code, RegionResourceAdvisoryPublicationCode)
            else RegionResourceAdvisoryPublicationCode(str(code))
            for code in self.publication_rejection_codes
        )
        rejection_codes = tuple(dict.fromkeys(rejection_codes))
        rejection_reasons = _unique(self.publication_rejection_reasons)
        planning_rejection_reasons = _unique(self.planning_rejection_reasons)
        if self.generation_publishable:
            if (
                reason_code
                != RegionResourceAdvisoryPublicationCode.CURRENT_GENERATION_ACCEPTED
                or rejection_codes
                or rejection_reasons
            ):
                raise ValueError(
                    "generation-publishable advice must carry only the accepted code"
                )
        elif (
            reason_code
            == RegionResourceAdvisoryPublicationCode.CURRENT_GENERATION_ACCEPTED
            or not rejection_codes
            or reason_code != rejection_codes[0]
            or not rejection_reasons
        ):
            raise ValueError(
                "generation-rejected advice requires stable publication reasons"
            )
        if self.planning_consumable:
            if not self.generation_publishable or planning_rejection_reasons:
                raise ValueError(
                    "planning-consumable advice requires a publishable generation"
                )
        elif not planning_rejection_reasons:
            raise ValueError(
                "planning-rejected advice requires stable planning reasons"
            )
        for name in (
            "assignment_execution_authorized",
            "coalition_execution_authorized",
            "takeover_execution_authorized",
            "control_execution_authorized",
        ):
            if getattr(self, name) is not False:
                raise ValueError(
                    "advice publication cannot grant assignment or control authority"
                )
        source_generations = tuple(
            sorted(self.source_generations, key=lambda item: item.region_id)
        )
        current_generations = tuple(
            sorted(self.current_generations, key=lambda item: item.region_id)
        )
        if len({item.region_id for item in source_generations}) != len(
            source_generations
        ):
            raise ValueError("source publication generations must be unique")
        if len({item.region_id for item in current_generations}) != len(
            current_generations
        ):
            raise ValueError("current publication generations must be unique")
        object.__setattr__(self, "publication_reason_code", reason_code)
        object.__setattr__(
            self,
            "publication_rejection_codes",
            rejection_codes,
        )
        object.__setattr__(
            self,
            "publication_rejection_reasons",
            rejection_reasons,
        )
        object.__setattr__(
            self,
            "planning_rejection_reasons",
            planning_rejection_reasons,
        )
        object.__setattr__(self, "source_generations", source_generations)
        object.__setattr__(self, "current_generations", current_generations)

    @property
    def advisory_id(self) -> str:
        return self.advisory.advisory_id

    @property
    def publishable(self) -> bool:
        """Compatibility alias for main callers during the contract migration."""

        return self.generation_publishable

    @property
    def reason_code(self) -> RegionResourceAdvisoryPublicationCode:
        return self.publication_reason_code

    @property
    def rejection_codes(self) -> tuple[RegionResourceAdvisoryPublicationCode, ...]:
        return self.publication_rejection_codes

    @property
    def rejection_reasons(self) -> tuple[str, ...]:
        return self.publication_rejection_reasons

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "RegionResourceAdvisoryPublicationDecision":
        _reject_truth_identifiers(value, path="advisory.publication")
        payload = dict(value)
        if "generation_publishable" not in payload and "publishable" in payload:
            payload["generation_publishable"] = payload.pop("publishable")
        if "publication_reason_code" not in payload and "reason_code" in payload:
            payload["publication_reason_code"] = payload.pop("reason_code")
        if (
            "publication_rejection_codes" not in payload
            and "rejection_codes" in payload
        ):
            payload["publication_rejection_codes"] = payload.pop(
                "rejection_codes"
            )
        if (
            "publication_rejection_reasons" not in payload
            and "rejection_reasons" in payload
        ):
            payload["publication_rejection_reasons"] = payload.pop(
                "rejection_reasons"
            )
        if "planning_consumable" not in payload:
            payload["planning_consumable"] = bool(
                payload.get("generation_publishable", False)
            )
        if "planning_rejection_reasons" not in payload:
            payload["planning_rejection_reasons"] = (
                ()
                if payload["planning_consumable"]
                else ("legacy_publication_not_planning_consumable",)
            )
        payload["advisory"] = RegionResourceAdvisoryContract.from_dict(
            payload["advisory"]
        )
        payload["source_generations"] = tuple(
            RegionResourceAuthorityGeneration.from_dict(item)
            for item in payload.get("source_generations", ())
        )
        payload["current_generations"] = tuple(
            RegionResourceAuthorityGeneration.from_dict(item)
            for item in payload.get("current_generations", ())
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceProjectionConfig:
    minimum_reserve_ratio: float = 0.10
    minimum_reserve_resources: int = 1
    advisory_ttl_s: float = 1.0

    def __post_init__(self) -> None:
        if not _unit_interval(self.minimum_reserve_ratio):
            raise ValueError("minimum_reserve_ratio must be in [0, 1]")
        if int(self.minimum_reserve_resources) < 0:
            raise ValueError("minimum_reserve_resources must be non-negative")
        if not _finite_non_negative(self.advisory_ttl_s) or self.advisory_ttl_s <= 0.0:
            raise ValueError("advisory_ttl_s must be finite and positive")


class DeterministicResourceProjector:
    """Project arbitrary advice through immutable D4 authority fences."""

    def __init__(self, config: RegionResourceProjectionConfig | None = None) -> None:
        self.config = config or RegionResourceProjectionConfig()

    def project(
        self,
        snapshot: RegionResourceSnapshot,
        proposal: RegionResourceRecommendation,
        *,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceRecommendation:
        nodes = snapshot.region_by_id
        raw_actions = {action.region_id: action for action in proposal.actions}
        rejections: list[str] = list(proposal.projection_rejections)
        globally_stale = bool(
            proposal.snapshot_id != snapshot.snapshot_id
            or proposal.scenario_id != snapshot.scenario_id
            or proposal.scenario_version != snapshot.scenario_version
            or int(proposal.seed) != int(snapshot.seed)
            or proposal.authority_digest != snapshot.authority_digest
        )
        if globally_stale:
            rejections.append("snapshot_or_authority_version_mismatch")

        formal_by_region = (
            {item.region_id: item for item in formal_decision.region_decisions}
            if formal_decision is not None
            else {}
        )
        formal_region_set_mismatch = bool(
            formal_decision is not None and set(formal_by_region) != set(nodes)
        )
        if formal_region_set_mismatch:
            rejections.append("formal_region_set_mismatch")
        blocked: dict[str, list[str]] = {}
        planning_only_regions: set[str] = set()
        for region_id, node in nodes.items():
            planning_only = self._planning_only_eligible(
                snapshot,
                node,
                raw_actions.get(region_id),
                formal_by_region.get(region_id),
                formal_decision=formal_decision,
                bound_planning_authority_digest=(
                    proposal.planning_authority_digest
                ),
            )
            reasons = self._node_block_reasons(
                snapshot,
                node,
                raw_actions.get(region_id),
                formal_by_region.get(region_id),
                formal_decision_supplied=formal_decision is not None,
                allow_planning_only=planning_only,
            )
            if globally_stale:
                reasons.append("snapshot_or_authority_version_mismatch")
            if formal_region_set_mismatch:
                reasons.append("formal_region_set_mismatch")
            if reasons:
                blocked[region_id] = list(_unique(reasons))
            elif planning_only:
                planning_only_regions.add(region_id)
        for region_id in sorted(blocked):
            rejections.extend(
                f"region:{region_id}:{reason}" for reason in blocked[region_id]
            )

        edge_by_id = {edge.edge_id: edge for edge in snapshot.edges}
        protected_committed = {
            region_id: max(
                node.committed_resources,
                self._formal_committed_resource_count(formal_by_region.get(region_id)),
            )
            for region_id, node in nodes.items()
        }
        source_budget = {
            region_id: self._transfer_budget(
                node, committed_resources=protected_committed[region_id]
            )
            for region_id, node in nodes.items()
        }
        edge_budget = {
            edge.edge_id: int(edge.transferable_resources) for edge in snapshot.edges
        }
        accepted: list[RegionTransferSuggestion] = []
        quota_delta = {region_id: 0 for region_id in nodes}
        ordered_transfers = sorted(
            proposal.transfers,
            key=lambda transfer: (
                transfer.source_region_id,
                transfer.target_region_id,
                transfer.edge_id,
            ),
        )
        for transfer in ordered_transfers:
            reason_prefix = (
                f"transfer:{transfer.source_region_id}->{transfer.target_region_id}"
            )
            if (
                transfer.source_region_id not in nodes
                or transfer.target_region_id not in nodes
            ):
                rejections.append(f"{reason_prefix}:unknown_region")
                continue
            if transfer.source_region_id in blocked or transfer.target_region_id in blocked:
                rejections.append(f"{reason_prefix}:authority_fenced")
                continue
            if transfer.source_region_id in planning_only_regions:
                rejections.append(f"{reason_prefix}:planning_only_source_forbidden")
                continue
            edge = edge_by_id.get(transfer.edge_id)
            if edge is None or not edge.permits(
                transfer.source_region_id, transfer.target_region_id
            ):
                rejections.append(f"{reason_prefix}:non_adjacent_edge")
                continue
            if not edge.open_for_transfer:
                rejections.append(f"{reason_prefix}:edge_unavailable_or_partitioned")
                continue
            count = min(
                int(transfer.resource_count),
                source_budget[transfer.source_region_id],
                edge_budget[edge.edge_id],
            )
            if count <= 0:
                rejections.append(f"{reason_prefix}:reserve_or_capacity_fence")
                continue
            accepted.append(
                RegionTransferSuggestion(
                    source_region_id=transfer.source_region_id,
                    target_region_id=transfer.target_region_id,
                    resource_count=count,
                    edge_id=edge.edge_id,
                    expected_transfer_time_s=edge.transfer_time_s,
                    reasons=transfer.reasons,
                )
            )
            source_budget[transfer.source_region_id] -= count
            edge_budget[edge.edge_id] -= count
            quota_delta[transfer.source_region_id] -= count
            quota_delta[transfer.target_region_id] += count
            if count < transfer.resource_count:
                rejections.append(f"{reason_prefix}:clipped_by_safety_projection")

        projected_actions: list[RegionResourceAction] = []
        for region_id in sorted(nodes):
            node = nodes[region_id]
            raw = raw_actions.get(region_id)
            reasons = list(raw.reasons if raw is not None else ())
            reasons.extend(blocked.get(region_id, ()))
            hold = bool(raw.hold) if raw is not None else False
            request_replan = bool(raw.request_replan) if raw is not None else False
            if region_id in planning_only_regions:
                reasons.append("planning_only_center_replan")
                hold = False
                request_replan = True
            if region_id in blocked:
                hold = True
                request_replan = request_replan or any(
                    reason
                    in {
                        "authority_lease_expired",
                        "authority_version_mismatch",
                        "fault_fence_active",
                        "formal_decision_mismatch",
                    }
                    for reason in blocked[region_id]
                )
                quota_delta[region_id] = 0
            reserve_ratio = (
                float(raw.reserve_ratio)
                if raw is not None
                else self.config.minimum_reserve_ratio
            )
            reserve_ratio = max(self.config.minimum_reserve_ratio, reserve_ratio)
            post_resources = node.available_resources + quota_delta[region_id]
            committed_resources = protected_committed[region_id]
            feasible_reserve = max(0, post_resources - committed_resources)
            if post_resources > 0:
                reserve_ratio = min(reserve_ratio, feasible_reserve / post_resources)
            reserve_ratio = max(
                min(1.0, reserve_ratio),
                min(
                    1.0,
                    self._reserve_floor(node) / max(1, post_resources),
                ),
            )
            projected_actions.append(
                RegionResourceAction(
                    region_id=region_id,
                    resource_quota_delta=quota_delta[region_id],
                    reserve_ratio=reserve_ratio,
                    reconnaissance_priority=(
                        float(raw.reconnaissance_priority) if raw is not None else 0.0
                    ),
                    hold=hold,
                    request_replan=request_replan,
                    expected_owner_id=node.current_owner_id,
                    expected_owner_layer=node.current_owner_layer,
                    expected_plan_id=node.plan_id,
                    expected_plan_version=node.plan_version,
                    expected_epoch=node.epoch,
                    expected_lease_expires_at_s=node.lease_expires_at_s,
                    reasons=_unique(reasons),
                )
            )
        if sum(quota_delta.values()) != 0:
            raise RuntimeError("deterministic projection violated resource conservation")
        for region_id, delta in quota_delta.items():
            node = nodes[region_id]
            if delta < 0 and (
                node.available_resources + delta
                < protected_committed[region_id] + self._reserve_floor(node)
            ):
                raise RuntimeError("deterministic projection violated reserve/commit fence")

        return RegionResourceRecommendation(
            snapshot_id=snapshot.snapshot_id,
            scenario_id=snapshot.scenario_id,
            scenario_version=snapshot.scenario_version,
            seed=snapshot.seed,
            authority_digest=snapshot.authority_digest,
            created_at_s=snapshot.timestamp_s,
            policy_name=proposal.policy_name,
            policy_version=proposal.policy_version,
            source=proposal.source,
            confidence=proposal.confidence,
            actions=tuple(projected_actions),
            transfers=tuple(accepted),
            projected=True,
            fallback_reason=proposal.fallback_reason,
            model_sha256=proposal.model_sha256,
            projection_rejections=_unique(rejections),
            planning_authority_digest=snapshot.planning_authority_digest,
        )

    def build_advisory_contract(
        self,
        snapshot: RegionResourceSnapshot,
        recommendation: RegionResourceRecommendation,
        *,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceAdvisoryContract:
        """Freeze projected advice with the evidence needed by a later consumer."""

        nodes = snapshot.region_by_id
        actions = {action.region_id: action for action in recommendation.actions}
        publication_rejections: list[str] = []
        if not recommendation.projected:
            publication_rejections.append("recommendation_not_projected")
        if (
            recommendation.snapshot_id != snapshot.snapshot_id
            or recommendation.scenario_id != snapshot.scenario_id
            or recommendation.scenario_version != snapshot.scenario_version
            or int(recommendation.seed) != int(snapshot.seed)
            or recommendation.authority_digest != snapshot.authority_digest
        ):
            publication_rejections.append("source_snapshot_or_authority_mismatch")
        if recommendation.created_at_s < snapshot.timestamp_s:
            publication_rejections.append("recommendation_created_before_snapshot")

        action_regions = set(actions)
        snapshot_regions = set(nodes)
        for region_id in sorted(snapshot_regions - action_regions):
            publication_rejections.append(f"region:{region_id}:action_missing")
        for region_id in sorted(action_regions - snapshot_regions):
            publication_rejections.append(f"region:{region_id}:unknown_action_region")

        formal_by_region = (
            {item.region_id: item for item in formal_decision.region_decisions}
            if formal_decision is not None
            else {}
        )
        planning_only_regions = {
            region_id
            for region_id, node in nodes.items()
            if self._planning_only_eligible(
                snapshot,
                node,
                actions.get(region_id),
                formal_by_region.get(region_id),
                formal_decision=formal_decision,
                bound_planning_authority_digest=(
                    recommendation.planning_authority_digest
                ),
            )
        }
        if (
            planning_only_regions
            and recommendation.planning_authority_digest
            != snapshot.planning_authority_digest
        ):
            publication_rejections.append(
                "source_planning_authority_digest_mismatch"
            )
        publication_rejections.extend(
            self._formal_snapshot_rejections(snapshot, formal_decision)
        )
        protected_committed = {
            region_id: max(
                node.committed_resources,
                self._formal_committed_resource_count(formal_by_region.get(region_id)),
            )
            for region_id, node in nodes.items()
        }
        source_versions = {
            region_id: self._source_version(snapshot, node)
            for region_id, node in nodes.items()
        }

        advisory_regions: list[RegionResourceAdvisoryRegion] = []
        for region_id in sorted(nodes):
            node = nodes[region_id]
            action = actions.get(region_id)
            block_reasons = self._node_block_reasons(
                snapshot,
                node,
                action,
                formal_by_region.get(region_id),
                formal_decision_supplied=formal_decision is not None,
                allow_planning_only=region_id in planning_only_regions,
            )
            publication_rejections.extend(
                f"region:{region_id}:{reason}"
                for reason in block_reasons
                if reason not in _ADVISORY_CONSUMPTION_ONLY_BLOCK_REASONS
            )
            if recommendation.created_at_s >= node.lease_expires_at_s:
                publication_rejections.append(f"region:{region_id}:lease_expired_at_creation")

            reserve_floor = self._reserve_floor(node)
            if action is None:
                delta = 0
                reserve_ratio = reserve_floor / max(1, node.available_resources)
                reconnaissance_priority = 0.0
                hold = True
                request_replan = True
                action_reasons = ("region_action_missing",)
            else:
                delta = int(action.resource_quota_delta)
                reserve_ratio = float(action.reserve_ratio)
                reconnaissance_priority = float(action.reconnaissance_priority)
                hold = bool(action.hold)
                request_replan = bool(action.request_replan)
                action_reasons = action.reasons
            resources_after = int(node.available_resources) + delta
            if resources_after < 0:
                publication_rejections.append(
                    f"region:{region_id}:negative_post_advisory_resources"
                )
            if (
                resources_after
                < protected_committed[region_id] + reserve_floor
            ):
                publication_rejections.append(
                    f"region:{region_id}:reserve_or_committed_resources_unprotected"
                )
            if resources_after > 0:
                recommended_reserve = reserve_ratio * resources_after
                if recommended_reserve + 1e-12 < reserve_floor:
                    publication_rejections.append(
                        f"region:{region_id}:reserve_ratio_below_protected_floor"
                    )
                if (
                    recommended_reserve + protected_committed[region_id]
                    > resources_after + 1e-12
                ):
                    publication_rejections.append(
                        f"region:{region_id}:reserve_ratio_conflicts_with_commitment"
                    )
            advisory_regions.append(
                RegionResourceAdvisoryRegion(
                    source_version=source_versions[region_id],
                    resources_before=int(node.available_resources),
                    resource_quota_delta=delta,
                    resources_after=resources_after,
                    protected_reserve_resources=reserve_floor,
                    protected_committed_resources=protected_committed[region_id],
                    reserve_ratio=reserve_ratio,
                    reconnaissance_priority=reconnaissance_priority,
                    hold=hold,
                    request_replan=request_replan,
                    reasons=action_reasons,
                    planning_only=region_id in planning_only_regions,
                )
            )

        edge_by_id = {edge.edge_id: edge for edge in snapshot.edges}
        edge_usage = {edge.edge_id: 0 for edge in snapshot.edges}
        source_usage = {region_id: 0 for region_id in nodes}
        net_transfer = {region_id: 0 for region_id in nodes}
        advisory_transfers: list[RegionResourceAdvisoryTransfer] = []
        for transfer in recommendation.transfers:
            prefix = f"transfer:{transfer.source_region_id}->{transfer.target_region_id}"
            if (
                transfer.source_region_id not in nodes
                or transfer.target_region_id not in nodes
            ):
                publication_rejections.append(f"{prefix}:unknown_region")
                continue
            edge = edge_by_id.get(transfer.edge_id)
            if edge is None:
                publication_rejections.append(f"{prefix}:unknown_edge")
                continue
            if transfer.source_region_id in planning_only_regions:
                publication_rejections.append(
                    f"{prefix}:planning_only_source_forbidden"
                )
                continue
            advisory_transfers.append(
                RegionResourceAdvisoryTransfer(
                    source_version=source_versions[transfer.source_region_id],
                    target_version=source_versions[transfer.target_region_id],
                    resource_count=int(transfer.resource_count),
                    edge_id=edge.edge_id,
                    edge_source_region_id=edge.source_region_id,
                    edge_target_region_id=edge.target_region_id,
                    edge_capacity_resources=int(edge.transferable_resources),
                    expected_transfer_time_s=float(transfer.expected_transfer_time_s),
                    bandwidth_mbps=float(edge.bandwidth_mbps),
                    communication_available=bool(edge.communication_available),
                    maneuver_available=bool(edge.maneuver_available),
                    partitioned=bool(edge.partitioned),
                    bidirectional=bool(edge.bidirectional),
                    reasons=transfer.reasons,
                    planning_only_target=(
                        transfer.target_region_id in planning_only_regions
                    ),
                )
            )
            if not edge.permits(
                transfer.source_region_id, transfer.target_region_id
            ):
                publication_rejections.append(f"{prefix}:non_adjacent_edge")
            if not edge.open_for_transfer:
                publication_rejections.append(
                    f"{prefix}:edge_unavailable_or_partitioned"
                )
            if transfer.expected_transfer_time_s != edge.transfer_time_s:
                publication_rejections.append(f"{prefix}:edge_transfer_time_mismatch")
            edge_usage[edge.edge_id] += int(transfer.resource_count)
            source_usage[transfer.source_region_id] += int(transfer.resource_count)
            net_transfer[transfer.source_region_id] -= int(transfer.resource_count)
            net_transfer[transfer.target_region_id] += int(transfer.resource_count)

        for edge in snapshot.edges:
            if edge_usage[edge.edge_id] > int(edge.transferable_resources):
                publication_rejections.append(
                    f"edge:{edge.edge_id}:capacity_exceeded"
                )
        advisory_region_by_id = {
            item.region_id: item for item in advisory_regions
        }
        for region_id, node in nodes.items():
            budget = self._transfer_budget(
                node,
                committed_resources=protected_committed[region_id],
            )
            if source_usage[region_id] > budget:
                publication_rejections.append(
                    f"region:{region_id}:transfer_budget_exceeded"
                )
            advisory_region = advisory_region_by_id[region_id]
            if advisory_region.resource_quota_delta != net_transfer[region_id]:
                publication_rejections.append(
                    f"region:{region_id}:transfer_quota_mismatch"
                )

        total_before = int(snapshot.total_resources)
        total_delta = sum(item.resource_quota_delta for item in advisory_regions)
        total_after = sum(item.resources_after for item in advisory_regions)
        if total_delta != 0 or total_after != total_before:
            publication_rejections.append("total_resource_quota_not_conserved")
        if recommendation.source == RecommendationSource.LEARNED and not _valid_sha256(
            recommendation.model_sha256
        ):
            publication_rejections.append("learned_model_identity_missing_or_invalid")

        valid_until_s = min(
            recommendation.created_at_s + self.config.advisory_ttl_s,
            *(node.lease_expires_at_s for node in snapshot.regions),
        )
        if valid_until_s <= recommendation.created_at_s:
            publication_rejections.append("advisory_has_no_validity_window")
        return RegionResourceAdvisoryContract(
            advisory_id="",
            snapshot_id=snapshot.snapshot_id,
            snapshot_version=snapshot.snapshot_version,
            snapshot_timestamp_s=snapshot.timestamp_s,
            scenario_id=snapshot.scenario_id,
            scenario_version=snapshot.scenario_version,
            seed=snapshot.seed,
            authority_digest=snapshot.authority_digest,
            created_at_s=recommendation.created_at_s,
            valid_from_s=recommendation.created_at_s,
            valid_until_s=valid_until_s,
            source_plan_versions=tuple(
                (node.plan_id, node.plan_version) for node in snapshot.regions
            ),
            projected=bool(recommendation.projected),
            projector_name=DETERMINISTIC_RESOURCE_PROJECTOR_NAME,
            projector_version=DETERMINISTIC_RESOURCE_PROJECTOR_VERSION,
            minimum_reserve_ratio=self.config.minimum_reserve_ratio,
            minimum_reserve_resources=self.config.minimum_reserve_resources,
            advisory_ttl_s=self.config.advisory_ttl_s,
            policy_name=recommendation.policy_name,
            policy_version=recommendation.policy_version,
            source=recommendation.source,
            confidence=recommendation.confidence,
            model_sha256=recommendation.model_sha256,
            fallback_reason=recommendation.fallback_reason,
            total_resources_before=total_before,
            total_quota_delta=total_delta,
            total_resources_after=total_after,
            regions=tuple(advisory_regions),
            transfers=tuple(advisory_transfers),
            projection_rejections=recommendation.projection_rejections,
            publication_rejections=_unique(publication_rejections),
            formal_decision_required=formal_decision is not None,
            planning_authority_digest=(
                snapshot.planning_authority_digest
                if planning_only_regions
                else ""
            ),
            planning_only_region_ids=tuple(sorted(planning_only_regions)),
            schema=(
                REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA
                if planning_only_regions
                else REGION_RESOURCE_ADVISORY_SCHEMA
            ),
        )

    def validate_for_consumption(
        self,
        advisory: RegionResourceAdvisoryContract,
        current_snapshot: RegionResourceSnapshot,
        *,
        evaluated_at_s: float,
        consumed_advisory_ids: Iterable[str] = (),
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceConsumptionView:
        """Revalidate an advisory at the next planning boundary."""

        if not _finite_non_negative(evaluated_at_s):
            raise ValueError("evaluated_at_s must be finite and non-negative")
        reasons: list[str] = list(advisory.publication_rejections)
        reasons.extend(
            f"unsafe_projection_rejection:{rejection}"
            for rejection in advisory.projection_rejections
            if not rejection.endswith(":clipped_by_safety_projection")
        )
        if not advisory.projected:
            reasons.append("recommendation_not_projected")
        if (
            advisory.projector_name != DETERMINISTIC_RESOURCE_PROJECTOR_NAME
            or advisory.projector_version != DETERMINISTIC_RESOURCE_PROJECTOR_VERSION
        ):
            reasons.append("projector_identity_mismatch")
        if (
            advisory.minimum_reserve_ratio != self.config.minimum_reserve_ratio
            or advisory.minimum_reserve_resources
            != self.config.minimum_reserve_resources
            or advisory.advisory_ttl_s != self.config.advisory_ttl_s
        ):
            reasons.append("projector_config_mismatch")
        if advisory.advisory_id in set(consumed_advisory_ids):
            reasons.append("advisory_already_consumed")
        if evaluated_at_s < advisory.valid_from_s:
            reasons.append("advisory_not_yet_valid")
        if evaluated_at_s >= advisory.valid_until_s:
            reasons.append("advisory_expired")
        if evaluated_at_s < current_snapshot.timestamp_s:
            reasons.append("evaluation_precedes_current_snapshot")

        if advisory.scenario_id != current_snapshot.scenario_id:
            reasons.append("source_scenario_id_stale")
        if advisory.scenario_version != current_snapshot.scenario_version:
            reasons.append("source_scenario_version_stale")
        if int(advisory.seed) != int(current_snapshot.seed):
            reasons.append("source_scenario_seed_stale")
        if advisory.snapshot_id != current_snapshot.snapshot_id:
            reasons.append("source_snapshot_id_stale")
        if advisory.snapshot_version != current_snapshot.snapshot_version:
            reasons.append("source_snapshot_version_stale")
        if advisory.snapshot_timestamp_s != current_snapshot.timestamp_s:
            reasons.append("source_snapshot_timestamp_stale")
        if advisory.authority_digest != current_snapshot.authority_digest:
            reasons.append("source_authority_digest_stale")
        if (
            advisory.planning_authority_digest
            and advisory.planning_authority_digest
            != current_snapshot.planning_authority_digest
        ):
            reasons.append("source_planning_authority_digest_stale")

        current_nodes = current_snapshot.region_by_id
        advisory_regions = {region.region_id: region for region in advisory.regions}
        if set(advisory_regions) != set(current_nodes):
            reasons.append("advisory_region_set_mismatch")
        formal_by_region = (
            {item.region_id: item for item in formal_decision.region_decisions}
            if formal_decision is not None
            else {}
        )
        if advisory.formal_decision_required and formal_decision is None:
            reasons.append("current_formal_decision_missing")
        reasons.extend(
            self._formal_snapshot_rejections(current_snapshot, formal_decision)
            if formal_decision is not None
            else ()
        )
        planning_valid_regions: set[str] = set()
        for region_id in advisory.planning_only_region_ids:
            region = advisory_regions.get(region_id)
            node = current_nodes.get(region_id)
            formal_region = formal_by_region.get(region_id)
            if region is None or node is None:
                continue
            planning_action = RegionResourceAction(
                region_id=region_id,
                resource_quota_delta=region.resource_quota_delta,
                reserve_ratio=region.reserve_ratio,
                reconnaissance_priority=region.reconnaissance_priority,
                hold=region.hold,
                request_replan=region.request_replan,
                expected_owner_id=region.source_version.owner_id,
                expected_owner_layer=region.source_version.owner_layer,
                expected_plan_id=region.source_version.plan_id,
                expected_plan_version=region.source_version.plan_version,
                expected_epoch=region.source_version.epoch,
                expected_lease_expires_at_s=(
                    region.source_version.lease_expires_at_s
                ),
                reasons=region.reasons,
            )
            if self._planning_only_eligible(
                current_snapshot,
                node,
                planning_action,
                formal_region,
                formal_decision=formal_decision,
                bound_planning_authority_digest=(
                    advisory.planning_authority_digest
                ),
            ):
                planning_valid_regions.add(region_id)
            else:
                reasons.append(
                    f"region:{region_id}:planning_eligibility_not_current"
                )

        expected_net = {region_id: 0 for region_id in current_nodes}
        edge_usage = {edge.edge_id: 0 for edge in current_snapshot.edges}
        source_usage = {region_id: 0 for region_id in current_nodes}
        current_edges = {edge.edge_id: edge for edge in current_snapshot.edges}
        for transfer in advisory.transfers:
            prefix = f"transfer:{transfer.source_region_id}->{transfer.target_region_id}"
            if (
                transfer.source_region_id not in current_nodes
                or transfer.target_region_id not in current_nodes
            ):
                reasons.append(f"{prefix}:unknown_region")
                continue
            edge = current_edges.get(transfer.edge_id)
            if edge is None:
                reasons.append(f"{prefix}:unknown_edge")
                continue
            if not edge.permits(
                transfer.source_region_id, transfer.target_region_id
            ):
                reasons.append(f"{prefix}:non_adjacent_edge")
            if not edge.open_for_transfer:
                reasons.append(f"{prefix}:edge_unavailable_or_partitioned")
            if (
                transfer.edge_source_region_id != edge.source_region_id
                or transfer.edge_target_region_id != edge.target_region_id
                or transfer.edge_capacity_resources != edge.transferable_resources
                or transfer.expected_transfer_time_s != edge.transfer_time_s
                or transfer.bandwidth_mbps != edge.bandwidth_mbps
                or transfer.communication_available != edge.communication_available
                or transfer.maneuver_available != edge.maneuver_available
                or transfer.partitioned != edge.partitioned
                or transfer.bidirectional != edge.bidirectional
            ):
                reasons.append(f"{prefix}:edge_version_mismatch")
            reasons.extend(
                self._source_version_rejections(
                    transfer.source_version,
                    current_snapshot,
                    current_nodes[transfer.source_region_id],
                    evaluated_at_s=evaluated_at_s,
                    prefix=f"{prefix}:source",
                    allow_planning_only=False,
                    require_planning_binding=(
                        advisory.schema
                        == REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA
                    ),
                )
            )
            reasons.extend(
                self._source_version_rejections(
                    transfer.target_version,
                    current_snapshot,
                    current_nodes[transfer.target_region_id],
                    evaluated_at_s=evaluated_at_s,
                    prefix=f"{prefix}:target",
                    allow_planning_only=(
                        transfer.planning_only_target
                        and transfer.target_region_id in planning_valid_regions
                    ),
                    require_planning_binding=(
                        advisory.schema
                        == REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA
                    ),
                )
            )
            if transfer.planning_only_target != (
                transfer.target_region_id
                in set(advisory.planning_only_region_ids)
            ):
                reasons.append(f"{prefix}:planning_only_target_marker_mismatch")
            edge_usage[edge.edge_id] += transfer.resource_count
            source_usage[transfer.source_region_id] += transfer.resource_count
            expected_net[transfer.source_region_id] -= transfer.resource_count
            expected_net[transfer.target_region_id] += transfer.resource_count

        for edge in current_snapshot.edges:
            if edge_usage[edge.edge_id] > edge.transferable_resources:
                reasons.append(f"edge:{edge.edge_id}:capacity_exceeded")

        total_before = 0
        total_delta = 0
        total_after = 0
        current_source_plans: set[tuple[str, int]] = set()
        for region_id, region in advisory_regions.items():
            node = current_nodes.get(region_id)
            if node is None:
                continue
            current_source_plans.add((node.plan_id, int(node.plan_version)))
            reasons.extend(
                self._source_version_rejections(
                    region.source_version,
                    current_snapshot,
                    node,
                    evaluated_at_s=evaluated_at_s,
                    prefix=f"region:{region_id}",
                    allow_planning_only=region_id in planning_valid_regions,
                    require_planning_binding=(
                        advisory.schema
                        == REGION_RESOURCE_PLANNING_ADVISORY_SCHEMA
                    ),
                )
            )
            formal_region = formal_by_region.get(region_id)
            if formal_decision is not None:
                action = RegionResourceAction(
                    region_id=region_id,
                    resource_quota_delta=region.resource_quota_delta,
                    reserve_ratio=region.reserve_ratio,
                    reconnaissance_priority=region.reconnaissance_priority,
                    hold=region.hold,
                    request_replan=region.request_replan,
                    expected_owner_id=region.source_version.owner_id,
                    expected_owner_layer=region.source_version.owner_layer,
                    expected_plan_id=region.source_version.plan_id,
                    expected_plan_version=region.source_version.plan_version,
                    expected_epoch=region.source_version.epoch,
                    expected_lease_expires_at_s=(
                        region.source_version.lease_expires_at_s
                    ),
                    reasons=region.reasons,
                )
                reasons.extend(
                    f"region:{region_id}:{reason}"
                    for reason in self._node_block_reasons(
                        current_snapshot,
                        node,
                        action,
                        formal_region,
                        formal_decision_supplied=True,
                        allow_planning_only=region_id in planning_valid_regions,
                    )
                )
            current_committed = max(
                node.committed_resources,
                self._formal_committed_resource_count(formal_region),
            )
            current_reserve = self._reserve_floor(node)
            if region.resources_before != node.available_resources:
                reasons.append(f"region:{region_id}:resource_snapshot_stale")
            if region.protected_committed_resources != current_committed:
                reasons.append(f"region:{region_id}:committed_resources_stale")
            if region.protected_reserve_resources != current_reserve:
                reasons.append(f"region:{region_id}:reserve_resources_stale")
            if region.resources_after != (
                region.resources_before + region.resource_quota_delta
            ):
                reasons.append(f"region:{region_id}:resource_proof_mismatch")
            if region.resources_after < current_committed + current_reserve:
                reasons.append(
                    f"region:{region_id}:reserve_or_committed_resources_unprotected"
                )
            if region.resource_quota_delta != expected_net.get(region_id, 0):
                reasons.append(f"region:{region_id}:transfer_quota_mismatch")
            budget = self._transfer_budget(
                node,
                committed_resources=current_committed,
            )
            if source_usage.get(region_id, 0) > budget:
                reasons.append(f"region:{region_id}:transfer_budget_exceeded")
            if region.resources_after > 0:
                recommended_reserve = region.reserve_ratio * region.resources_after
                if recommended_reserve + 1e-12 < current_reserve:
                    reasons.append(f"region:{region_id}:reserve_ratio_below_floor")
                if (
                    recommended_reserve + current_committed
                    > region.resources_after + 1e-12
                ):
                    reasons.append(
                        f"region:{region_id}:reserve_ratio_conflicts_with_commitment"
                    )
            total_before += region.resources_before
            total_delta += region.resource_quota_delta
            total_after += region.resources_after

        if tuple(sorted(current_source_plans)) != advisory.source_plan_versions:
            reasons.append("source_plan_versions_stale")
        if (
            total_delta != 0
            or total_after != total_before
            or advisory.total_quota_delta != total_delta
            or advisory.total_resources_before != total_before
            or advisory.total_resources_after != total_after
        ):
            reasons.append("total_resource_quota_not_conserved")
        if advisory.source == RecommendationSource.LEARNED and not _valid_sha256(
            advisory.model_sha256
        ):
            reasons.append("learned_model_identity_missing_or_invalid")

        unique_reasons = _unique(reasons)
        return RegionResourceConsumptionView(
            advisory=advisory,
            evaluated_at_s=float(evaluated_at_s),
            current_snapshot_id=current_snapshot.snapshot_id,
            current_snapshot_version=current_snapshot.snapshot_version,
            current_authority_digest=current_snapshot.authority_digest,
            consumable=not unique_reasons,
            rejection_reasons=unique_reasons,
            planning_replan_eligible=bool(
                not unique_reasons and advisory.planning_only_region_ids
            ),
        )

    @staticmethod
    def _source_version(
        snapshot: RegionResourceSnapshot,
        node: RegionResourceNode,
    ) -> RegionResourceSourceVersion:
        return RegionResourceSourceVersion(
            region_id=node.region_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_version=snapshot.snapshot_version,
            authority_digest=snapshot.authority_digest,
            owner_id=node.current_owner_id,
            owner_layer=node.current_owner_layer,
            plan_id=node.plan_id,
            plan_version=node.plan_version,
            epoch=node.epoch,
            lease_expires_at_s=node.lease_expires_at_s,
            coalition_ack_complete=node.coalition_ack_complete,
            owner_active=node.owner_active,
            fault_fenced=node.fault_fenced,
            fault_fence_epoch=node.fault_fence_epoch,
            planning_authority_digest=snapshot.planning_authority_digest,
            authority_capabilities=node.authority_capabilities,
        )

    @staticmethod
    def _formal_snapshot_rejections(
        snapshot: RegionResourceSnapshot,
        formal_decision: RegionalFailoverDecision | None,
    ) -> tuple[str, ...]:
        if formal_decision is None:
            return ()
        reasons: list[str] = []
        if formal_decision.schema != REGIONAL_FAILOVER_SCHEMA:
            reasons.append("formal_decision_schema_mismatch")
        if formal_decision.timestamp_s != snapshot.timestamp_s:
            reasons.append("formal_decision_timestamp_mismatch")
        if formal_decision.scenario.scenario_name != snapshot.scenario_id:
            reasons.append("formal_decision_scenario_id_mismatch")
        if formal_decision.scenario.scenario_version != snapshot.scenario_version:
            reasons.append("formal_decision_scenario_version_mismatch")
        if {
            item.region_id for item in formal_decision.region_decisions
        } != set(snapshot.region_by_id):
            reasons.append("formal_region_set_mismatch")
        return _unique(reasons)

    @staticmethod
    def _source_version_rejections(
        source: RegionResourceSourceVersion,
        snapshot: RegionResourceSnapshot,
        node: RegionResourceNode,
        *,
        evaluated_at_s: float,
        prefix: str,
        allow_planning_only: bool = False,
        require_planning_binding: bool = False,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if source.region_id != node.region_id:
            reasons.append(f"{prefix}:region_id_stale")
        if source.snapshot_id != snapshot.snapshot_id:
            reasons.append(f"{prefix}:snapshot_id_stale")
        if source.snapshot_version != snapshot.snapshot_version:
            reasons.append(f"{prefix}:snapshot_version_stale")
        if source.authority_digest != snapshot.authority_digest:
            reasons.append(f"{prefix}:authority_digest_stale")
        if require_planning_binding:
            if (
                source.planning_authority_digest
                != snapshot.planning_authority_digest
            ):
                reasons.append(f"{prefix}:planning_authority_digest_stale")
            if source.authority_capabilities != node.authority_capabilities:
                reasons.append(f"{prefix}:authority_capabilities_stale")
        if source.owner_id != node.current_owner_id:
            reasons.append(f"{prefix}:owner_id_stale")
        if source.owner_layer != node.current_owner_layer:
            reasons.append(f"{prefix}:owner_layer_stale")
        if source.plan_id != node.plan_id:
            reasons.append(f"{prefix}:plan_id_stale")
        if source.plan_version != node.plan_version:
            reasons.append(f"{prefix}:plan_version_stale")
        if source.epoch != node.epoch:
            reasons.append(f"{prefix}:epoch_stale")
        if source.lease_expires_at_s != node.lease_expires_at_s:
            reasons.append(f"{prefix}:lease_version_stale")
        if evaluated_at_s >= node.lease_expires_at_s:
            reasons.append(f"{prefix}:lease_expired")
        if not node.coalition_ack_complete:
            reasons.append(f"{prefix}:coalition_ack_incomplete")
        if not node.owner_active or node.current_owner_layer == RegionalAuthorityLayer.HOLD:
            reasons.append(f"{prefix}:authority_not_active")
        if node.fault_fenced or (
            node.fault_fence_epoch is not None and node.epoch < node.fault_fence_epoch
        ):
            reasons.append(f"{prefix}:fault_fence_active")
        if source.coalition_ack_complete != node.coalition_ack_complete:
            reasons.append(f"{prefix}:coalition_ack_version_stale")
        if source.owner_active != node.owner_active:
            reasons.append(f"{prefix}:owner_active_version_stale")
        if (
            source.fault_fenced != node.fault_fenced
            or source.fault_fence_epoch != node.fault_fence_epoch
        ):
            reasons.append(f"{prefix}:fault_fence_version_stale")
        if allow_planning_only:
            capabilities = node.authority_capabilities
            planning_valid = bool(
                capabilities is not None
                and capabilities.planning_replan_eligible
                and source.authority_capabilities == capabilities
                and source.planning_authority_digest
                == snapshot.planning_authority_digest
                and not node.fault_generation_fenced
            )
            if planning_valid:
                tolerated = {
                    f"{prefix}:authority_not_active",
                    f"{prefix}:fault_fence_active",
                }
                reasons = [reason for reason in reasons if reason not in tolerated]
        return _unique(reasons)

    @staticmethod
    def _planning_only_eligible(
        snapshot: RegionResourceSnapshot,
        node: RegionResourceNode,
        action: RegionResourceAction | None,
        formal_region: Any | None,
        *,
        formal_decision: RegionalFailoverDecision | None,
        bound_planning_authority_digest: str,
    ) -> bool:
        capabilities = node.authority_capabilities
        if (
            capabilities is None
            or not capabilities.planning_replan_eligible
            or action is None
            or formal_decision is None
            or formal_region is None
            or bound_planning_authority_digest
            != snapshot.planning_authority_digest
            or node.current_owner_layer != RegionalAuthorityLayer.CENTER
            or not node.current_owner_id
            or snapshot.timestamp_s >= node.lease_expires_at_s
            or node.fault_generation_fenced
            or (
                node.fault_fence_epoch is not None
                and node.epoch < node.fault_fence_epoch
            )
            or not node.coalition_ack_complete
            or action.resource_quota_delta < 0
            or not action.request_replan
        ):
            return False
        if (
            action.expected_owner_id != node.current_owner_id
            or action.expected_owner_layer != node.current_owner_layer
            or action.expected_plan_id != node.plan_id
            or action.expected_plan_version != node.plan_version
            or action.expected_epoch != node.epoch
            or action.expected_lease_expires_at_s != node.lease_expires_at_s
        ):
            return False
        ownership = formal_region.ownership
        if (
            formal_decision.schema != snapshot.source_authority_schema
            or formal_decision.timestamp_s != snapshot.timestamp_s
            or formal_decision.scenario.scenario_name != snapshot.scenario_id
            or formal_decision.scenario.scenario_version
            != snapshot.scenario_version
            or formal_region.region_id != node.region_id
            or formal_region.selected_layer != RegionalAuthorityLayer.CENTER
            or formal_region.action != RegionalAction.REQUEST_CENTER_REPLAN
            or ownership.owner_id != node.current_owner_id
            or ownership.owner_layer != node.current_owner_layer
            or ownership.plan_id != node.plan_id
            or ownership.plan_version != node.plan_version
            or ownership.epoch != node.epoch
            or ownership.lease_expires_at_s != node.lease_expires_at_s
            or ownership.active != node.owner_active
        ):
            return False
        expected = RegionResourceAuthorityCapabilities.from_formal_decision(
            formal_decision,
            formal_region,
            coalition_ack_complete=node.coalition_ack_complete,
            fault_generation_fenced=node.fault_generation_fenced,
        )
        return bool(
            expected == capabilities
            and capabilities.source_decision_sha256
            == formal_decision_digest(formal_decision)
            and not capabilities.assignment_execution_authorized
            and not capabilities.coalition_execution_authorized
            and not capabilities.takeover_execution_authorized
            and not capabilities.control_execution_authorized
        )

    def _node_block_reasons(
        self,
        snapshot: RegionResourceSnapshot,
        node: RegionResourceNode,
        action: RegionResourceAction | None,
        formal_region: Any | None,
        *,
        formal_decision_supplied: bool,
        allow_planning_only: bool = False,
    ) -> list[str]:
        reasons: list[str] = []
        if snapshot.timestamp_s >= node.lease_expires_at_s:
            reasons.append("authority_lease_expired")
        if not node.owner_active or node.current_owner_layer == RegionalAuthorityLayer.HOLD:
            reasons.append("authority_not_active")
        if node.fault_fenced or (
            node.fault_fence_epoch is not None and node.epoch < node.fault_fence_epoch
        ):
            reasons.append("fault_fence_active")
        if not node.coalition_ack_complete:
            reasons.append("coalition_ack_incomplete")
        if action is None:
            reasons.append("region_action_missing")
        elif (
            action.expected_owner_id != node.current_owner_id
            or action.expected_owner_layer != node.current_owner_layer
            or action.expected_plan_id != node.plan_id
            or action.expected_plan_version != node.plan_version
            or action.expected_epoch != node.epoch
            or action.expected_lease_expires_at_s != node.lease_expires_at_s
        ):
            reasons.append("authority_version_mismatch")
        if formal_decision_supplied and formal_region is None:
            reasons.append("formal_region_missing")
        if formal_region is not None:
            ownership = formal_region.ownership
            if (
                ownership.owner_id != node.current_owner_id
                or ownership.owner_layer != node.current_owner_layer
                or ownership.plan_id != node.plan_id
                or ownership.plan_version != node.plan_version
                or ownership.epoch != node.epoch
                or ownership.lease_expires_at_s != node.lease_expires_at_s
                or ownership.active != node.owner_active
            ):
                reasons.append("formal_decision_mismatch")
            if formal_region.fail_closed or not formal_region.execution_allowed:
                reasons.append("formal_d4_execution_fenced")
            if any(
                commit.commit_required and not commit.execution_authorized
                for commit in formal_region.coalition_commits
            ):
                reasons.append("formal_d4_commit_incomplete")
        if allow_planning_only:
            reasons = [
                reason
                for reason in reasons
                if reason
                not in {
                    "authority_not_active",
                    "fault_fence_active",
                    "formal_d4_execution_fenced",
                }
            ]
        return reasons

    def _reserve_floor(self, node: RegionResourceNode) -> int:
        return min(
            node.available_resources - node.committed_resources,
            max(
                int(node.reserve_resources),
                int(self.config.minimum_reserve_resources),
                int(ceil(self.config.minimum_reserve_ratio * node.available_resources)),
            ),
        )

    def _transfer_budget(
        self,
        node: RegionResourceNode,
        *,
        committed_resources: int | None = None,
    ) -> int:
        protected_committed = (
            node.committed_resources
            if committed_resources is None
            else max(node.committed_resources, int(committed_resources))
        )
        return max(
            0,
            node.available_resources
            - protected_committed
            - self._reserve_floor(node),
        )

    @staticmethod
    def _formal_committed_resource_count(formal_region: Any | None) -> int:
        if formal_region is None:
            return 0
        member_ids = {
            member_id
            for commit in formal_region.coalition_commits
            if commit.execution_authorized
            for member_id in commit.required_member_ids
        }
        return len(member_ids)


class RegionResourceAdvisoryGate:
    """One-shot in-process gate for next-cycle advisory consumption."""

    def __init__(
        self,
        projector: DeterministicResourceProjector | None = None,
    ) -> None:
        self.projector = projector or DeterministicResourceProjector()
        self._consumed_advisory_ids: set[str] = set()

    @property
    def consumed_advisory_ids(self) -> frozenset[str]:
        return frozenset(self._consumed_advisory_ids)

    def consume(
        self,
        advisory: RegionResourceAdvisoryContract,
        current_snapshot: RegionResourceSnapshot,
        *,
        evaluated_at_s: float,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceConsumptionView:
        view = self.projector.validate_for_consumption(
            advisory,
            current_snapshot,
            evaluated_at_s=evaluated_at_s,
            consumed_advisory_ids=self._consumed_advisory_ids,
            formal_decision=formal_decision,
        )
        if view.consumable:
            self._consumed_advisory_ids.add(advisory.advisory_id)
        return view


class RegionResourceAdvisoryPublicationGate:
    """Authorize advice publication against the current immutable D3/D4 generation.

    The gate observes, but never edits, the caller-supplied authority snapshot.
    Accepted and rejected decisions are retained as immutable point-in-time audit
    records.  A later replan therefore does not retroactively invalidate an
    advice item that was valid when it was published.
    """

    def __init__(
        self,
        projector: DeterministicResourceProjector | None = None,
    ) -> None:
        self.projector = projector or DeterministicResourceProjector()
        self._history: list[RegionResourceAdvisoryPublicationDecision] = []
        self._current_generations: dict[
            tuple[str, str, int, str],
            RegionResourceAuthorityGeneration,
        ] = {}

    @property
    def publication_history(
        self,
    ) -> tuple[RegionResourceAdvisoryPublicationDecision, ...]:
        return tuple(self._history)

    @property
    def accepted_publications(
        self,
    ) -> tuple[RegionResourceAdvisoryPublicationDecision, ...]:
        return tuple(
            item for item in self._history if item.generation_publishable
        )

    @property
    def current_authority_generations(
        self,
    ) -> tuple[RegionResourceAuthorityGeneration, ...]:
        return tuple(
            sorted(
                self._current_generations.values(),
                key=lambda item: item.region_id,
            )
        )

    def build_current_and_authorize(
        self,
        current_snapshot: RegionResourceSnapshot,
        recommendation: RegionResourceRecommendation,
        *,
        publication_timestamp_s: float,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceAdvisoryPublicationDecision:
        """Build advice from the current snapshot, then run the publication gate."""

        advisory = self.projector.build_advisory_contract(
            current_snapshot,
            recommendation,
            formal_decision=formal_decision,
        )
        return self.authorize(
            advisory,
            current_snapshot,
            publication_timestamp_s=publication_timestamp_s,
            formal_decision=formal_decision,
        )

    def authorize(
        self,
        advisory: RegionResourceAdvisoryContract,
        current_snapshot: RegionResourceSnapshot,
        *,
        publication_timestamp_s: float,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceAdvisoryPublicationDecision:
        """Return a fail-closed publication decision for a main-owned bus writer."""

        if not _finite_non_negative(publication_timestamp_s):
            raise ValueError(
                "publication_timestamp_s must be finite and non-negative"
            )
        source_generations = self._source_generations(advisory)
        current_generations = self._snapshot_generations(current_snapshot)
        codes: list[RegionResourceAdvisoryPublicationCode] = []
        reasons: list[str] = []

        generation_codes, generation_reasons, updates = (
            self._current_generation_updates(
                current_snapshot,
                current_generations,
            )
        )
        codes.extend(generation_codes)
        reasons.extend(generation_reasons)
        if not generation_codes:
            self._current_generations.update(updates)

        consumption = self.projector.validate_for_consumption(
            advisory,
            current_snapshot,
            evaluated_at_s=publication_timestamp_s,
            formal_decision=formal_decision,
        )
        if advisory.publication_rejections:
            codes.append(
                RegionResourceAdvisoryPublicationCode.ADVISORY_CONTRACT_REJECTED
            )
            reasons.extend(advisory.publication_rejections)
        if not advisory.projected:
            codes.append(
                RegionResourceAdvisoryPublicationCode.ADVISORY_CONTRACT_REJECTED
            )
            reasons.append("recommendation_not_projected")
        if (
            advisory.projector_name != DETERMINISTIC_RESOURCE_PROJECTOR_NAME
            or advisory.projector_version
            != DETERMINISTIC_RESOURCE_PROJECTOR_VERSION
            or advisory.minimum_reserve_ratio
            != self.projector.config.minimum_reserve_ratio
            or advisory.minimum_reserve_resources
            != self.projector.config.minimum_reserve_resources
            or advisory.advisory_ttl_s
            != self.projector.config.advisory_ttl_s
        ):
            codes.append(
                RegionResourceAdvisoryPublicationCode.ADVISORY_CONTRACT_REJECTED
            )
            reasons.append("publication_projector_contract_mismatch")
        if advisory.formal_decision_required and formal_decision is None:
            codes.append(
                RegionResourceAdvisoryPublicationCode.ADVISORY_CONTRACT_REJECTED
            )
            reasons.append("current_formal_decision_missing")
        formal_snapshot_rejections = (
            self.projector._formal_snapshot_rejections(
                current_snapshot,
                formal_decision,
            )
            if formal_decision is not None
            else ()
        )
        if formal_snapshot_rejections:
            codes.append(
                RegionResourceAdvisoryPublicationCode.ADVISORY_CONTRACT_REJECTED
            )
            reasons.extend(formal_snapshot_rejections)
        if publication_timestamp_s < advisory.valid_from_s:
            codes.append(
                RegionResourceAdvisoryPublicationCode.ADVISORY_CONTRACT_REJECTED
            )
            reasons.append("advisory_not_yet_valid")
        if publication_timestamp_s >= advisory.valid_until_s:
            codes.append(RegionResourceAdvisoryPublicationCode.ADVISORY_EXPIRED)
            reasons.append("advisory_expired")
        if (
            advisory.snapshot_id != current_snapshot.snapshot_id
            or advisory.snapshot_version != current_snapshot.snapshot_version
            or advisory.snapshot_timestamp_s != current_snapshot.timestamp_s
            or advisory.authority_digest != current_snapshot.authority_digest
            or advisory.scenario_id != current_snapshot.scenario_id
            or advisory.scenario_version != current_snapshot.scenario_version
            or int(advisory.seed) != int(current_snapshot.seed)
            or (
                advisory.planning_authority_digest
                and advisory.planning_authority_digest
                != current_snapshot.planning_authority_digest
            )
            or publication_timestamp_s < current_snapshot.timestamp_s
        ):
            codes.append(
                RegionResourceAdvisoryPublicationCode.SOURCE_SNAPSHOT_STALE
            )
            reasons.append("source_snapshot_or_scenario_not_current")

        source_by_region = {
            item.region_id: item for item in source_generations
        }
        current_by_region = {
            item.region_id: item for item in current_generations
        }
        if set(source_by_region) != set(current_by_region):
            codes.append(
                RegionResourceAdvisoryPublicationCode.SOURCE_REGION_SET_MISMATCH
            )
            reasons.append("source_region_set_mismatch")
        for region_id in sorted(set(source_by_region) & set(current_by_region)):
            source = source_by_region[region_id]
            current = current_by_region[region_id]
            if source.plan_id != current.plan_id:
                codes.append(
                    RegionResourceAdvisoryPublicationCode.SOURCE_PLAN_ID_SUPERSEDED
                )
                reasons.append(f"region:{region_id}:source_plan_id_superseded")
            if source.plan_version != current.plan_version:
                codes.append(
                    RegionResourceAdvisoryPublicationCode.SOURCE_PLAN_VERSION_SUPERSEDED
                )
                reasons.append(f"region:{region_id}:source_plan_version_superseded")
            if source.authority_epoch != current.authority_epoch:
                codes.append(
                    RegionResourceAdvisoryPublicationCode.SOURCE_AUTHORITY_EPOCH_SUPERSEDED
                )
                reasons.append(
                    f"region:{region_id}:source_authority_epoch_superseded"
                )
            if source.lease_expires_at_s != current.lease_expires_at_s:
                codes.append(
                    RegionResourceAdvisoryPublicationCode.SOURCE_AUTHORITY_LEASE_MISMATCH
                )
                reasons.append(
                    f"region:{region_id}:source_authority_lease_mismatch"
                )
            if publication_timestamp_s >= current.lease_expires_at_s:
                codes.append(
                    RegionResourceAdvisoryPublicationCode.CURRENT_AUTHORITY_LEASE_EXPIRED
                )
                reasons.append(f"region:{region_id}:current_authority_lease_expired")
            if (
                source.owner_id != current.owner_id
                or source.owner_layer != current.owner_layer
            ):
                codes.append(
                    RegionResourceAdvisoryPublicationCode.AUTHORITY_BINDING_MISMATCH
                )
                reasons.append(f"region:{region_id}:authority_binding_mismatch")

        unique_codes = tuple(dict.fromkeys(codes))
        unique_reasons = _unique(reasons)
        generation_publishable = not unique_codes
        planning_rejection_reasons = list(consumption.rejection_reasons)
        if not generation_publishable:
            planning_rejection_reasons.append("generation_not_publishable")
        planning_rejection_reasons = list(_unique(planning_rejection_reasons))
        planning_consumable = bool(
            generation_publishable and consumption.consumable
        )
        decision = RegionResourceAdvisoryPublicationDecision(
            advisory=advisory,
            publication_timestamp_s=float(publication_timestamp_s),
            current_snapshot_id=current_snapshot.snapshot_id,
            current_snapshot_version=current_snapshot.snapshot_version,
            current_authority_digest=current_snapshot.authority_digest,
            source_generations=source_generations,
            current_generations=current_generations,
            generation_publishable=generation_publishable,
            planning_consumable=planning_consumable,
            publication_reason_code=(
                RegionResourceAdvisoryPublicationCode.CURRENT_GENERATION_ACCEPTED
                if generation_publishable
                else unique_codes[0]
            ),
            publication_rejection_codes=unique_codes,
            publication_rejection_reasons=unique_reasons,
            planning_rejection_reasons=tuple(planning_rejection_reasons),
        )
        self._history.append(decision)
        return decision

    def _current_generation_updates(
        self,
        snapshot: RegionResourceSnapshot,
        current_generations: tuple[RegionResourceAuthorityGeneration, ...],
    ) -> tuple[
        tuple[RegionResourceAdvisoryPublicationCode, ...],
        tuple[str, ...],
        dict[
            tuple[str, str, int, str],
            RegionResourceAuthorityGeneration,
        ],
    ]:
        codes: list[RegionResourceAdvisoryPublicationCode] = []
        reasons: list[str] = []
        updates: dict[
            tuple[str, str, int, str],
            RegionResourceAuthorityGeneration,
        ] = {}
        for current in current_generations:
            key = (
                snapshot.scenario_id,
                snapshot.scenario_version,
                int(snapshot.seed),
                current.region_id,
            )
            previous = self._current_generations.get(key)
            if previous is None:
                updates[key] = current
                continue
            if current.immutable_identity == previous.immutable_identity:
                if current.lease_expires_at_s > previous.lease_expires_at_s:
                    codes.append(
                        RegionResourceAdvisoryPublicationCode.SAME_IDENTITY_LEASE_RENEWAL_FORBIDDEN
                    )
                    reasons.append(
                        f"region:{current.region_id}:same_identity_lease_renewal_forbidden"
                    )
                elif current.lease_expires_at_s < previous.lease_expires_at_s:
                    codes.append(
                        RegionResourceAdvisoryPublicationCode.SAME_IDENTITY_LEASE_CHANGE_FORBIDDEN
                    )
                    reasons.append(
                        f"region:{current.region_id}:same_identity_lease_change_forbidden"
                    )
                continue
            if current.authority_epoch < previous.authority_epoch or (
                current.authority_epoch == previous.authority_epoch
                and current.plan_version < previous.plan_version
            ):
                codes.append(
                    RegionResourceAdvisoryPublicationCode.CURRENT_GENERATION_ROLLBACK
                )
                reasons.append(
                    f"region:{current.region_id}:current_generation_rollback"
                )
                continue
            if (
                current.authority_epoch == previous.authority_epoch
                and current.plan_version == previous.plan_version
            ):
                codes.append(
                    RegionResourceAdvisoryPublicationCode.CURRENT_GENERATION_CONFLICT
                )
                reasons.append(
                    f"region:{current.region_id}:current_generation_conflict"
                )
                continue
            updates[key] = current
        return (
            tuple(dict.fromkeys(codes)),
            _unique(reasons),
            updates,
        )

    @staticmethod
    def _source_generations(
        advisory: RegionResourceAdvisoryContract,
    ) -> tuple[RegionResourceAuthorityGeneration, ...]:
        return tuple(
            RegionResourceAuthorityGeneration(
                region_id=region.region_id,
                owner_id=region.source_version.owner_id,
                owner_layer=region.source_version.owner_layer,
                plan_id=region.source_version.plan_id,
                plan_version=region.source_version.plan_version,
                authority_epoch=region.source_version.epoch,
                lease_expires_at_s=region.source_version.lease_expires_at_s,
            )
            for region in advisory.regions
        )

    @staticmethod
    def _snapshot_generations(
        snapshot: RegionResourceSnapshot,
    ) -> tuple[RegionResourceAuthorityGeneration, ...]:
        return tuple(
            RegionResourceAuthorityGeneration(
                region_id=node.region_id,
                owner_id=node.current_owner_id,
                owner_layer=node.current_owner_layer,
                plan_id=node.plan_id,
                plan_version=node.plan_version,
                authority_epoch=node.epoch,
                lease_expires_at_s=node.lease_expires_at_s,
            )
            for node in snapshot.regions
        )


@dataclass(frozen=True)
class RuleRegionResourcePolicyConfig:
    projection: RegionResourceProjectionConfig = field(
        default_factory=RegionResourceProjectionConfig
    )
    high_threat_weight: float = 2.0
    uncertainty_weight: float = 0.5
    transfer_pressure_margin: float = 0.05


class RuleRegionResourcePolicy:
    """Deterministic baseline for aggregate regional resource suggestions."""

    policy_name = "d4-region-resource-rule"
    policy_version = "v1"

    def __init__(
        self,
        config: RuleRegionResourcePolicyConfig | None = None,
        *,
        projector: DeterministicResourceProjector | None = None,
    ) -> None:
        self.config = config or RuleRegionResourcePolicyConfig()
        if projector is not None and projector.config != self.config.projection:
            raise ValueError("rule policy and projector configuration must match")
        self.projector = projector or DeterministicResourceProjector(
            self.config.projection
        )

    def recommend(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        formal_decision: RegionalFailoverDecision | None = None,
        fallback_reason: str | None = None,
    ) -> RegionResourceRecommendation:
        nodes = snapshot.region_by_id
        pressures = {region_id: self._pressure(node) for region_id, node in nodes.items()}
        deficits = {
            region_id: max(
                0,
                int(ceil(node.target_demand + self.config.high_threat_weight * node.high_threat_backlog))
                - max(0, node.available_resources - node.reserve_resources),
            )
            for region_id, node in nodes.items()
        }
        projector = self.projector
        source_budget = {
            region_id: projector._transfer_budget(node) for region_id, node in nodes.items()
        }
        edge_budget = {
            edge.edge_id: int(edge.transferable_resources) for edge in snapshot.edges
        }
        transfers: list[RegionTransferSuggestion] = []
        candidates: list[tuple[float, str, str, RegionResourceEdge]] = []
        for edge in snapshot.edges:
            if not edge.open_for_transfer:
                continue
            directions = [(edge.source_region_id, edge.target_region_id)]
            if edge.bidirectional:
                directions.append((edge.target_region_id, edge.source_region_id))
            for source_id, target_id in directions:
                margin = pressures[target_id] - pressures[source_id]
                if margin > self.config.transfer_pressure_margin:
                    candidates.append((-margin, source_id, target_id, edge))
        for _, source_id, target_id, edge in sorted(
            candidates, key=lambda item: (item[0], item[1], item[2], item[3].edge_id)
        ):
            count = min(
                source_budget[source_id],
                deficits[target_id],
                edge_budget[edge.edge_id],
            )
            if count <= 0:
                continue
            transfers.append(
                RegionTransferSuggestion(
                    source_region_id=source_id,
                    target_region_id=target_id,
                    resource_count=count,
                    edge_id=edge.edge_id,
                    expected_transfer_time_s=edge.transfer_time_s,
                    reasons=("rule_pressure_rebalance",),
                )
            )
            source_budget[source_id] -= count
            deficits[target_id] -= count
            edge_budget[edge.edge_id] -= count

        deltas = {region_id: 0 for region_id in nodes}
        for transfer in transfers:
            deltas[transfer.source_region_id] -= transfer.resource_count
            deltas[transfer.target_region_id] += transfer.resource_count
        actions = tuple(
            self._action(snapshot, node, deltas[node.region_id], deficits[node.region_id])
            for node in sorted(snapshot.regions, key=lambda item: item.region_id)
        )
        raw = RegionResourceRecommendation(
            snapshot_id=snapshot.snapshot_id,
            scenario_id=snapshot.scenario_id,
            scenario_version=snapshot.scenario_version,
            seed=snapshot.seed,
            authority_digest=snapshot.authority_digest,
            created_at_s=snapshot.timestamp_s,
            policy_name=self.policy_name,
            policy_version=self.policy_version,
            source=RecommendationSource.RULE,
            confidence=1.0,
            actions=actions,
            transfers=tuple(transfers),
            projected=False,
            fallback_reason=fallback_reason,
            planning_authority_digest=snapshot.planning_authority_digest,
        )
        return self.projector.project(
            snapshot, raw, formal_decision=formal_decision
        )

    def recommend_contract(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        formal_decision: RegionalFailoverDecision | None = None,
        fallback_reason: str | None = None,
    ) -> RegionResourceAdvisoryContract:
        recommendation = self.recommend(
            snapshot,
            formal_decision=formal_decision,
            fallback_reason=fallback_reason,
        )
        return self.projector.build_advisory_contract(
            snapshot,
            recommendation,
            formal_decision=formal_decision,
        )

    def _pressure(self, node: RegionResourceNode) -> float:
        demand = node.target_demand + self.config.high_threat_weight * node.high_threat_backlog
        perception = self.config.uncertainty_weight * (
            node.d1_uncertainty
            + node.d2_uncertainty
            + (1.0 - node.d5_visibility)
            + (1.0 - node.d5_consistency)
        )
        communication = node.packet_loss_rate + min(1.0, node.communication_latency_s)
        capacity = max(1.0, float(node.available_resources - node.reserve_resources))
        return (demand + perception + communication) / capacity

    def _action(
        self,
        snapshot: RegionResourceSnapshot,
        node: RegionResourceNode,
        quota_delta: int,
        remaining_deficit: int,
    ) -> RegionResourceAction:
        reasons: list[str] = []
        hold = False
        request_replan = False
        if remaining_deficit > 0:
            reasons.append("unserved_regional_demand")
            request_replan = True
        if node.assignment_conflict_count > 0:
            reasons.append("assignment_conflict_observed")
            request_replan = True
        if node.degradation_failed:
            reasons.append("degradation_failure_observed")
            hold = True
            request_replan = True
        if node.fault_fenced or not node.coalition_ack_complete:
            reasons.append("formal_safety_fence_active")
            hold = True
        reserve_ratio = max(
            self.config.projection.minimum_reserve_ratio,
            node.reserve_resources / max(1, node.available_resources),
        )
        recon_priority = _clamp01(
            (
                node.d1_uncertainty
                + node.d2_uncertainty
                + (1.0 - node.d5_visibility)
                + (1.0 - node.d5_consistency)
                + min(1.0, node.high_threat_backlog / max(1.0, node.target_demand))
            )
            / 5.0
        )
        return RegionResourceAction(
            region_id=node.region_id,
            resource_quota_delta=quota_delta,
            reserve_ratio=reserve_ratio,
            reconnaissance_priority=recon_priority,
            hold=hold,
            request_replan=request_replan,
            expected_owner_id=node.current_owner_id,
            expected_owner_layer=node.current_owner_layer,
            expected_plan_id=node.plan_id,
            expected_plan_version=node.plan_version,
            expected_epoch=node.epoch,
            expected_lease_expires_at_s=node.lease_expires_at_s,
            reasons=_unique(reasons),
        )


@dataclass(frozen=True)
class RegionResourceRewardMetrics:
    high_threat_backlog: float
    transfer_time_s: float
    communication_load: float
    reserve_shortfall: float
    assignment_conflicts: float
    degradation_failures: float
    plan_jitter: float

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if not _finite_non_negative(getattr(self, name)):
                raise ValueError(f"reward metric {name} must be finite and non-negative")


@dataclass(frozen=True)
class RegionResourceRewardWeights:
    high_threat_backlog: float = 2.0
    transfer_time_s: float = 0.2
    communication_load: float = 0.1
    reserve_shortfall: float = 2.0
    assignment_conflicts: float = 3.0
    degradation_failures: float = 5.0
    plan_jitter: float = 0.5


def compute_region_resource_reward(
    metrics: RegionResourceRewardMetrics,
    weights: RegionResourceRewardWeights | None = None,
) -> float:
    """Return the legacy unversioned research cost used by local fixtures.

    This helper has no runtime ACK, availability, provenance, or outcome-window
    binding and therefore must not be treated as formal training evidence.  Use
    ``RegionResourceRewardEvidenceAdapter`` for the versioned, fail-closed
    regional reward contract.
    """

    resolved = weights or RegionResourceRewardWeights()
    return -sum(
        float(getattr(metrics, name)) * float(getattr(resolved, name))
        for name in metrics.__dataclass_fields__
    )


@dataclass(frozen=True)
class ScenarioSeedSplit:
    train: tuple[Any, ...]
    validation: tuple[Any, ...]
    test: tuple[Any, ...]
    train_groups: tuple[tuple[str, int], ...]
    validation_groups: tuple[tuple[str, int], ...]
    test_groups: tuple[tuple[str, int], ...]
    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    test_seeds: tuple[int, ...]
    unique_seed_count: int
    minimum_unseen_seeds: int
    split_seed: int
    split_sha256: str
    split_algorithm: str = "d4-numeric-seed-atomic-sha256-v1"


def split_scenario_seed_groups(
    records: Sequence[Any],
    *,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    split_seed: int = 0,
    group_getter: Callable[[Any], tuple[str, int]] | None = None,
    minimum_unique_seeds: int = 3,
    minimum_unseen_seeds: int = 2,
) -> ScenarioSeedSplit:
    """Split complete episodes by numeric seed without cross-scenario leakage.

    Every ``(scenario, seed)`` group remains intact, while all groups sharing the
    same numeric seed are assigned to the same bucket.  The hash order is used
    only to order seeds; deterministic counts keep every split non-empty.
    """

    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be in (0, 1)")
    if not 0.0 <= validation_fraction < 1.0:
        raise ValueError("validation_fraction must be in [0, 1)")
    if train_fraction + validation_fraction >= 1.0:
        raise ValueError("train and validation fractions must leave a test split")
    if int(minimum_unique_seeds) < 3:
        raise ValueError("minimum_unique_seeds must be at least 3")
    if int(minimum_unseen_seeds) < 2:
        raise ValueError("minimum_unseen_seeds must leave validation and test seeds")
    getter = group_getter or _record_group
    groups: dict[tuple[str, int], list[Any]] = {}
    for record in records:
        key = getter(record)
        if not key[0] or int(key[1]) < 0:
            raise ValueError("scenario/seed groups require non-empty scenario and seed >= 0")
        groups.setdefault((str(key[0]), int(key[1])), []).append(record)
    unique_seeds = sorted({seed for _, seed in groups})
    if len(unique_seeds) < int(minimum_unique_seeds):
        raise ValueError("fewer_than_minimum_unique_seeds")
    if len(unique_seeds) - 1 < int(minimum_unseen_seeds):
        raise ValueError("fewer_than_minimum_unseen_seeds")

    ordered_seeds = sorted(
        unique_seeds,
        key=lambda seed: (
            sha256(f"{int(split_seed)}:{seed}".encode("utf-8")).digest(),
            seed,
        ),
    )
    train_count = max(1, min(len(ordered_seeds) - 2, round(len(ordered_seeds) * train_fraction)))
    train_count = min(train_count, len(ordered_seeds) - int(minimum_unseen_seeds))
    unseen_count = len(ordered_seeds) - train_count
    validation_count = max(
        1,
        min(unseen_count - 1, round(len(ordered_seeds) * validation_fraction)),
    )
    seed_buckets = {
        "train": tuple(sorted(ordered_seeds[:train_count])),
        "validation": tuple(
            sorted(ordered_seeds[train_count : train_count + validation_count])
        ),
        "test": tuple(sorted(ordered_seeds[train_count + validation_count :])),
    }
    if any(not seeds for seeds in seed_buckets.values()):
        raise ValueError("seed split must leave train, validation, and test non-empty")
    if len(seed_buckets["validation"]) + len(seed_buckets["test"]) < int(
        minimum_unseen_seeds
    ):
        raise ValueError("fewer_than_minimum_unseen_seeds")
    seed_to_bucket = {
        seed: bucket for bucket, seeds in seed_buckets.items() for seed in seeds
    }

    buckets: dict[str, list[Any]] = {"train": [], "validation": [], "test": []}
    bucket_groups: dict[str, list[tuple[str, int]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for key in sorted(groups):
        bucket = seed_to_bucket[key[1]]
        buckets[bucket].extend(groups[key])
        bucket_groups[bucket].append(key)
    split_payload = {
        "algorithm": "d4-numeric-seed-atomic-sha256-v1",
        "split_seed": int(split_seed),
        "train": list(seed_buckets["train"]),
        "validation": list(seed_buckets["validation"]),
        "test": list(seed_buckets["test"]),
    }
    split_sha256 = sha256(
        json.dumps(
            split_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return ScenarioSeedSplit(
        train=tuple(buckets["train"]),
        validation=tuple(buckets["validation"]),
        test=tuple(buckets["test"]),
        train_groups=tuple(bucket_groups["train"]),
        validation_groups=tuple(bucket_groups["validation"]),
        test_groups=tuple(bucket_groups["test"]),
        train_seeds=seed_buckets["train"],
        validation_seeds=seed_buckets["validation"],
        test_seeds=seed_buckets["test"],
        unique_seed_count=len(unique_seeds),
        minimum_unseen_seeds=int(minimum_unseen_seeds),
        split_seed=int(split_seed),
        split_sha256=split_sha256,
    )


@dataclass(frozen=True)
class ShadowEpisodeMetrics:
    scenario_id: str
    seed: int
    high_threat_backlog: float
    transfer_time_s: float
    plan_churn: float
    communication_load: float
    fail_closed_count: float
    safety_violation_count: float
    latency_ms: float

    def __post_init__(self) -> None:
        if not self.scenario_id or int(self.seed) < 0:
            raise ValueError("shadow metrics require scenario identity and seed >= 0")
        for name in (
            "high_threat_backlog",
            "transfer_time_s",
            "plan_churn",
            "communication_load",
            "fail_closed_count",
            "safety_violation_count",
            "latency_ms",
        ):
            if not _finite_non_negative(getattr(self, name)):
                raise ValueError(f"shadow metric {name} must be finite and non-negative")

    @property
    def group(self) -> tuple[str, int]:
        return (self.scenario_id, int(self.seed))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ShadowEpisodeMetrics":
        return cls(**dict(value))


@dataclass(frozen=True)
class PairedMetricSummary:
    baseline_mean: float
    candidate_mean: float
    mean_delta: float

    def to_dict(self) -> dict[str, float]:
        return to_jsonable(self)


@dataclass(frozen=True)
class ShadowPairedEvaluationReport:
    pair_count: int
    unseen_seed_count: int
    minimum_unseen_seeds: int
    backlog: PairedMetricSummary
    transfer: PairedMetricSummary
    churn: PairedMetricSummary
    communication: PairedMetricSummary
    fail_closed: PairedMetricSummary
    safety_violations: PairedMetricSummary
    latency_p50_ms: float
    latency_p95_ms: float
    assist_recommended: bool
    recommendation_reasons: tuple[str, ...]
    schema: str = REGION_RESOURCE_SHADOW_REPORT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class ShadowPairedEvaluator:
    def __init__(self, minimum_unseen_seeds: int = 20) -> None:
        if int(minimum_unseen_seeds) <= 0:
            raise ValueError("minimum_unseen_seeds must be positive")
        self.minimum_unseen_seeds = int(minimum_unseen_seeds)

    def evaluate(
        self,
        baseline: Sequence[ShadowEpisodeMetrics],
        candidate: Sequence[ShadowEpisodeMetrics],
        *,
        training_groups: Iterable[tuple[str, int]] = (),
    ) -> ShadowPairedEvaluationReport:
        baseline_by_group = self._index(baseline)
        candidate_by_group = self._index(candidate)
        if set(baseline_by_group) != set(candidate_by_group):
            raise ValueError("shadow evaluation requires exact scenario/seed pairing")
        if not baseline_by_group:
            raise ValueError("shadow evaluation requires at least one pair")
        ordered = sorted(baseline_by_group)
        training_seeds = {int(seed) for _, seed in training_groups}
        unseen_seeds = {seed for _, seed in ordered if seed not in training_seeds}

        def summary(field_name: str) -> PairedMetricSummary:
            base_values = [float(getattr(baseline_by_group[key], field_name)) for key in ordered]
            candidate_values = [
                float(getattr(candidate_by_group[key], field_name)) for key in ordered
            ]
            baseline_mean = sum(base_values) / len(base_values)
            candidate_mean = sum(candidate_values) / len(candidate_values)
            return PairedMetricSummary(
                baseline_mean=baseline_mean,
                candidate_mean=candidate_mean,
                mean_delta=candidate_mean - baseline_mean,
            )

        backlog = summary("high_threat_backlog")
        transfer = summary("transfer_time_s")
        churn = summary("plan_churn")
        communication = summary("communication_load")
        fail_closed = summary("fail_closed_count")
        safety = summary("safety_violation_count")
        candidate_latency = [candidate_by_group[key].latency_ms for key in ordered]
        reasons: list[str] = []
        if len(unseen_seeds) < self.minimum_unseen_seeds:
            reasons.append("fewer_than_minimum_unseen_seeds")
        if safety.candidate_mean > 0.0 or safety.mean_delta > 0.0:
            reasons.append("candidate_safety_violation")
        if fail_closed.mean_delta > 0.0:
            reasons.append("candidate_fail_closed_regression")
        if backlog.mean_delta > 0.0:
            reasons.append("candidate_backlog_regression")
        return ShadowPairedEvaluationReport(
            pair_count=len(ordered),
            unseen_seed_count=len(unseen_seeds),
            minimum_unseen_seeds=self.minimum_unseen_seeds,
            backlog=backlog,
            transfer=transfer,
            churn=churn,
            communication=communication,
            fail_closed=fail_closed,
            safety_violations=safety,
            latency_p50_ms=_percentile(candidate_latency, 50.0),
            latency_p95_ms=_percentile(candidate_latency, 95.0),
            assist_recommended=not reasons,
            recommendation_reasons=_unique(reasons),
        )

    @staticmethod
    def _index(
        records: Sequence[ShadowEpisodeMetrics],
    ) -> dict[tuple[str, int], ShadowEpisodeMetrics]:
        indexed: dict[tuple[str, int], ShadowEpisodeMetrics] = {}
        for record in records:
            if record.group in indexed:
                raise ValueError("duplicate scenario/seed record in shadow evaluation")
            indexed[record.group] = record
        return indexed


def _region_resource_advisory_id(
    advisory: RegionResourceAdvisoryContract,
) -> str:
    payload = advisory.to_dict()
    payload.pop("advisory_id", None)
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return f"d4-rr-advisory-{sha256(serialized).hexdigest()}"


def _legacy_region_resource_advisory_payload(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the exact advisory-v1 content shape used before planning proofs."""

    payload = dict(value)
    payload.pop("planning_authority_digest", None)
    payload.pop("planning_only_region_ids", None)
    for region in payload.get("regions", ()):
        region.pop("planning_only", None)
        source = region.get("source_version", {})
        source.pop("planning_authority_digest", None)
        source.pop("authority_capabilities", None)
    for transfer in payload.get("transfers", ()):
        transfer.pop("planning_only_target", None)
        for key in ("source_version", "target_version"):
            source = transfer.get(key, {})
            source.pop("planning_authority_digest", None)
            source.pop("authority_capabilities", None)
    return payload


def _legacy_region_resource_snapshot_payload(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the exact snapshot-v1 shape used by frozen learning datasets."""

    payload = dict(value)
    payload.pop("planning_authority_digest", None)
    for region in payload.get("regions", ()):
        region.pop("fault_generation_fenced", None)
        region.pop("authority_capabilities", None)
    return payload


def _valid_sha256(value: str | None) -> bool:
    return bool(
        value
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _has_planning_hard_safety_indicator(values: Iterable[str]) -> bool:
    for value in values:
        normalized = str(value).strip().lower()
        if normalized in _PLANNING_HARD_SAFETY_INDICATORS:
            return True
        if any(
            token in normalized
            for token in (
                "friend_conflict",
                "duplicate_terminal_lock",
                "identity_conflict",
                "network_partition",
            )
        ):
            return True
    return False


def _authority_capability_digest(
    capabilities: RegionResourceAuthorityCapabilities,
) -> str:
    payload = to_jsonable(capabilities)
    payload.pop("capability_sha256", None)
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def formal_decision_digest(decision: RegionalFailoverDecision | None) -> str | None:
    if decision is None:
        return None
    payload = json.dumps(
        decision.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _authority_digest(regions: Sequence[RegionResourceNode]) -> str:
    payload = [
        {
            "region_id": node.region_id,
            "owner_id": node.current_owner_id,
            "owner_layer": node.current_owner_layer.value,
            "plan_id": node.plan_id,
            "plan_version": node.plan_version,
            "epoch": node.epoch,
            "lease_expires_at_s": node.lease_expires_at_s,
            "owner_active": node.owner_active,
            "coalition_ack_complete": node.coalition_ack_complete,
            "committed_resources": node.committed_resources,
            "fault_fenced": node.fault_fenced,
            "fault_fence_epoch": node.fault_fence_epoch,
        }
        for node in sorted(regions, key=lambda item: item.region_id)
    ]
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return sha256(serialized).hexdigest()


def _planning_authority_digest(
    regions: Sequence[RegionResourceNode],
    *,
    source_authority_schema: str,
    authority_digest: str,
) -> str:
    payload = {
        "source_authority_schema": str(source_authority_schema),
        "authority_digest": str(authority_digest),
        "regions": [
            {
                "region_id": node.region_id,
                "fault_generation_fenced": node.fault_generation_fenced,
                "authority_capabilities": (
                    None
                    if node.authority_capabilities is None
                    else node.authority_capabilities.to_dict()
                ),
            }
            for node in sorted(regions, key=lambda item: item.region_id)
        ],
    }
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def _record_group(record: Any) -> tuple[str, int]:
    if hasattr(record, "scenario_seed_group"):
        scenario, seed = record.scenario_seed_group
        return (str(scenario), int(seed))
    if hasattr(record, "scenario_id") and hasattr(record, "seed"):
        return (str(record.scenario_id), int(record.seed))
    if isinstance(record, Mapping):
        return (str(record["scenario_id"]), int(record["seed"]))
    raise TypeError("record does not expose scenario_id and seed")


def _reject_truth_identifiers(value: Any, path: str = "snapshot") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_ID_KEYS:
                raise ValueError(f"truth or target identity is forbidden at {path}.{key}")
            _reject_truth_identifiers(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_truth_identifiers(item, f"{path}[{index}]")


def _finite_non_negative(value: Any) -> bool:
    try:
        return isfinite(float(value)) and float(value) >= 0.0
    except (TypeError, ValueError):
        return False


def _strict_integer(
    value: Any,
    *,
    name: str,
    minimum: int | None = None,
) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        numeric = float(value)
        resolved = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite integer") from exc
    if not isfinite(numeric) or numeric != float(resolved):
        raise ValueError(f"{name} must be a finite integer")
    if minimum is not None and resolved < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return resolved


def _unit_interval(value: Any) -> bool:
    try:
        return isfinite(float(value)) and 0.0 <= float(value) <= 1.0
    except (TypeError, ValueError):
        return False


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _unique(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * float(percentile) / 100.0
    lower = int(floor(position))
    upper = int(ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight
