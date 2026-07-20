"""Truth-free regional resource advice contracts and deterministic safety gates.

This module is deliberately downstream of D4 authority arbitration.  It can
recommend aggregate regional quotas and neighboring transfers, but it cannot
elect an owner, form a coalition, create a D3 assignment, or authorize D7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from math import ceil, floor, isfinite
import json
from typing import Any, Callable, Iterable, Mapping, Sequence

from .models import to_jsonable
from .regional_failover import (
    REGIONAL_FAILOVER_SCHEMA,
    RegionalAuthorityLayer,
    RegionalFailoverDecision,
)


REGION_RESOURCE_SNAPSHOT_SCHEMA = "d4-region-resource-snapshot-v1"
REGION_RESOURCE_RECOMMENDATION_SCHEMA = "d4-region-resource-recommendation-v1"
REGION_RESOURCE_SHADOW_REPORT_SCHEMA = "d4-region-resource-shadow-report-v1"
REGION_RESOURCE_FEATURE_SCHEMA = "d4-region-resource-features-v1"

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
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.reserve_resources + self.committed_resources > self.available_resources:
            raise ValueError(
                "reserve_resources plus committed_resources exceeds available_resources"
            )
        if self.fault_fence_epoch is not None and int(self.fault_fence_epoch) < 0:
            raise ValueError("fault_fence_epoch must be non-negative when present")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceNode":
        _reject_truth_identifiers(value)
        return cls(**dict(value))


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
    schema: str = REGION_RESOURCE_SNAPSHOT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_SNAPSHOT_SCHEMA:
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
        expected_digest = _authority_digest(regions)
        if self.authority_digest and self.authority_digest != expected_digest:
            raise ValueError("authority_digest does not match regional authority fields")
        object.__setattr__(self, "authority_digest", expected_digest)

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
        return to_jsonable(self)

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
                    coalition_ack_complete=bool(
                        signal.get("coalition_ack_complete", ack_complete)
                    ),
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
                )
            )
        return cls(
            snapshot_id=snapshot_id,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            seed=seed,
            timestamp_s=decision.timestamp_s,
            regions=tuple(nodes),
            edges=tuple(edges),
            source_authority_schema=decision.schema,
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
        if int(self.expected_plan_version) < 0 or int(self.expected_epoch) < 0:
            raise ValueError("action version and epoch must be non-negative")
        if not _finite_non_negative(self.expected_lease_expires_at_s):
            raise ValueError("action lease must be finite and non-negative")
        object.__setattr__(self, "reasons", _unique(self.reasons))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


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

    @property
    def total_quota_delta(self) -> int:
        return sum(action.resource_quota_delta for action in self.actions)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class RegionResourceProjectionConfig:
    minimum_reserve_ratio: float = 0.10
    minimum_reserve_resources: int = 1

    def __post_init__(self) -> None:
        if not _unit_interval(self.minimum_reserve_ratio):
            raise ValueError("minimum_reserve_ratio must be in [0, 1]")
        if int(self.minimum_reserve_resources) < 0:
            raise ValueError("minimum_reserve_resources must be non-negative")


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
        for region_id, node in nodes.items():
            reasons = self._node_block_reasons(
                snapshot,
                node,
                raw_actions.get(region_id),
                formal_by_region.get(region_id),
                formal_decision_supplied=formal_decision is not None,
            )
            if globally_stale:
                reasons.append("snapshot_or_authority_version_mismatch")
            if formal_region_set_mismatch:
                reasons.append("formal_region_set_mismatch")
            if reasons:
                blocked[region_id] = list(_unique(reasons))

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
        )

    def _node_block_reasons(
        self,
        snapshot: RegionResourceSnapshot,
        node: RegionResourceNode,
        action: RegionResourceAction | None,
        formal_region: Any | None,
        *,
        formal_decision_supplied: bool,
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

    def __init__(self, config: RuleRegionResourcePolicyConfig | None = None) -> None:
        self.config = config or RuleRegionResourcePolicyConfig()
        self.projector = DeterministicResourceProjector(self.config.projection)

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
        )
        return self.projector.project(
            snapshot, raw, formal_decision=formal_decision
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
    """Return the native research reward as a negative weighted safety cost."""

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


def split_scenario_seed_groups(
    records: Sequence[Any],
    *,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    split_seed: int = 0,
    group_getter: Callable[[Any], tuple[str, int]] | None = None,
) -> ScenarioSeedSplit:
    """Split complete ``(scenario, seed)`` groups without transition leakage."""

    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be in (0, 1)")
    if not 0.0 <= validation_fraction < 1.0:
        raise ValueError("validation_fraction must be in [0, 1)")
    if train_fraction + validation_fraction >= 1.0:
        raise ValueError("train and validation fractions must leave a test split")
    getter = group_getter or _record_group
    groups: dict[tuple[str, int], list[Any]] = {}
    for record in records:
        key = getter(record)
        if not key[0] or int(key[1]) < 0:
            raise ValueError("scenario/seed groups require non-empty scenario and seed >= 0")
        groups.setdefault((str(key[0]), int(key[1])), []).append(record)
    buckets: dict[str, list[Any]] = {"train": [], "validation": [], "test": []}
    bucket_groups: dict[str, list[tuple[str, int]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for key in sorted(groups):
        digest = sha256(f"{split_seed}:{key[0]}:{key[1]}".encode("utf-8")).digest()
        unit = int.from_bytes(digest[:8], "big") / float(2**64)
        if unit < train_fraction:
            bucket = "train"
        elif unit < train_fraction + validation_fraction:
            bucket = "validation"
        else:
            bucket = "test"
        buckets[bucket].extend(groups[key])
        bucket_groups[bucket].append(key)
    return ScenarioSeedSplit(
        train=tuple(buckets["train"]),
        validation=tuple(buckets["validation"]),
        test=tuple(buckets["test"]),
        train_groups=tuple(bucket_groups["train"]),
        validation_groups=tuple(bucket_groups["validation"]),
        test_groups=tuple(bucket_groups["test"]),
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
        training = {(str(scenario), int(seed)) for scenario, seed in training_groups}
        unseen = [group for group in ordered if group not in training]

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
        if len(unseen) < self.minimum_unseen_seeds:
            reasons.append("fewer_than_minimum_unseen_seeds")
        if safety.candidate_mean > 0.0 or safety.mean_delta > 0.0:
            reasons.append("candidate_safety_violation")
        if fail_closed.mean_delta > 0.0:
            reasons.append("candidate_fail_closed_regression")
        if backlog.mean_delta > 0.0:
            reasons.append("candidate_backlog_regression")
        return ShadowPairedEvaluationReport(
            pair_count=len(ordered),
            unseen_seed_count=len(unseen),
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
