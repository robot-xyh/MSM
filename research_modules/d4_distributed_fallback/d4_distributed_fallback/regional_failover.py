"""Region-scoped D4 authority and failover contract for scalable episodes.

The contract is intentionally independent of the main-owned scalable simulator.
It consumes mappings compatible with ``ScenarioConfig.to_dict()`` and emits a
truth-free payload that can be placed in a versioned episode-bus envelope.
D4 never creates a system AssignmentPlan or rewrites ``global_track_id``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any, Mapping, Sequence

from .coalition_safety import (
    CoalitionCommitCoordinator,
    CoalitionCommitState,
    CoalitionMemberAck,
)
from .models import C2Health, to_jsonable
from .secondary_readiness import (
    SecondaryReadinessAssessment,
    SecondaryReadinessEvidence,
    assess_secondary_readiness,
)


REGIONAL_FAILOVER_SCHEMA = "d4-regional-failover-v1"
REGIONAL_SCENARIO_METADATA_SCHEMA = "d4-regional-scenario-metadata-v1"
SCALABLE_3D_SCENARIO_SCHEMA = "scalable3d-scenario-v1"
SCALABLE_3D_BUS_SCHEMA = "scalable3d-episode-bus-v1"


class RegionalAuthorityLayer(str, Enum):
    CENTER = "center"
    SECONDARY = "secondary"
    DISTRIBUTED = "distributed"
    HOLD = "hold"


class RegionalAction(str, Enum):
    CONTINUE_CENTER = "continue_center"
    REQUEST_CENTER_REPLAN = "request_center_replan"
    REQUEST_SECONDARY_ASSIST = "request_secondary_assist"
    DEGRADE_TO_SECONDARY = "degrade_to_secondary"
    DEGRADE_TO_DISTRIBUTED = "degrade_to_distributed"
    HOLD_FOR_REVIEW = "hold_for_review"


class D5Consistency(str, Enum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class RegionalScenarioMetadata:
    """D4 view of the scalable3d scenario contract without a module import."""

    scenario_name: str
    scenario_version: str
    task_count: int
    resource_count: int
    recon_count: int
    region_count: int
    region_ids: tuple[str, ...]
    source_schema_version: str = SCALABLE_3D_SCENARIO_SCHEMA
    bus_schema_version: str = SCALABLE_3D_BUS_SCHEMA
    schema: str = REGIONAL_SCENARIO_METADATA_SCHEMA

    def __post_init__(self) -> None:
        if not self.scenario_name or not self.scenario_version:
            raise ValueError("scenario identity must not be empty")
        if self.source_schema_version != SCALABLE_3D_SCENARIO_SCHEMA:
            raise ValueError(
                f"unsupported scalable3d scenario schema: {self.source_schema_version}"
            )
        if self.bus_schema_version != SCALABLE_3D_BUS_SCHEMA:
            raise ValueError(
                f"unsupported scalable3d bus schema: {self.bus_schema_version}"
            )
        if self.schema != REGIONAL_SCENARIO_METADATA_SCHEMA:
            raise ValueError(f"unsupported regional metadata schema: {self.schema}")
        for name in ("task_count", "resource_count", "region_count"):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if int(self.recon_count) < 0:
            raise ValueError("recon_count must be non-negative")
        region_ids = _unique(self.region_ids)
        if len(region_ids) != int(self.region_count):
            raise ValueError("region_ids must contain exactly region_count unique ids")
        object.__setattr__(self, "region_ids", region_ids)

    @property
    def node_count(self) -> int:
        return int(self.resource_count) + int(self.recon_count)

    @classmethod
    def from_scalable_scenario(
        cls,
        value: Mapping[str, Any] | Any,
        *,
        region_ids: Sequence[str] | None = None,
        bus_schema_version: str = SCALABLE_3D_BUS_SCHEMA,
    ) -> "RegionalScenarioMetadata":
        payload = _as_mapping(value)
        source_schema = str(
            payload.get("schema_version", SCALABLE_3D_SCENARIO_SCHEMA)
        )
        if source_schema != SCALABLE_3D_SCENARIO_SCHEMA:
            raise ValueError(f"unsupported scalable3d scenario schema: {source_schema}")
        region_count = int(payload.get("region_count", 0))
        resolved_region_ids = (
            tuple(region_ids)
            if region_ids is not None
            else _indexed_ids("region", region_count)
        )
        return cls(
            scenario_name=str(payload.get("scenario_name", "")),
            scenario_version=str(payload.get("scenario_version", "")),
            task_count=int(payload.get("target_count", 0)),
            resource_count=int(payload.get("resource_count", 0)),
            recon_count=int(payload.get("recon_count", 0)),
            region_count=region_count,
            region_ids=resolved_region_ids,
            source_schema_version=source_schema,
            bus_schema_version=str(bus_schema_version),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **to_jsonable(self),
            "node_count": self.node_count,
        }


@dataclass(frozen=True)
class RegionDefinition:
    region_id: str
    coverage_cell: str
    neighbor_region_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.region_id or not self.coverage_cell:
            raise ValueError("region_id and coverage_cell must not be empty")
        neighbors = _unique(self.neighbor_region_ids)
        if self.region_id in set(neighbors):
            raise ValueError("a region must not list itself as a neighbor")
        object.__setattr__(self, "neighbor_region_ids", neighbors)


@dataclass(frozen=True)
class RegionalTaskEvidence:
    """D1/D2/D3/D5 evidence and D3 member intent for one regional task."""

    task_id: str
    global_track_id: str
    region_id: str
    d3_plan_id: str
    d3_plan_version: int
    d3_epoch: int
    d3_lease_expires_at_s: float
    required_member_count: int = 1
    required_capabilities: tuple[str, ...] = ()
    d3_assigned_member_ids: tuple[str, ...] = ()
    coalition_id: str | None = None
    coalition_version: int | None = None
    d1_covariance_trace: float = 0.0
    d1_measurement_age_s: float = 0.0
    d2_ambiguity_score: float = 0.0
    d2_id_switch_count: int = 0
    d2_duplicate_track_count: int = 0
    d3_is_current: bool = True
    d3_resource_feasible: bool = True
    d5_consistency: D5Consistency = D5Consistency.CONSISTENT
    d5_binding_conflict: bool = False
    d5_friend_conflict: bool = False
    d5_duplicate_terminal_lock: bool = False
    d5_support_member_ids: tuple[str, ...] = ()
    d5_hold_member_ids: tuple[str, ...] = ()
    d5_ambiguous_member_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("task_id", "global_track_id", "region_id", "d3_plan_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        if int(self.required_member_count) <= 0:
            raise ValueError("required_member_count must be positive")
        for name in ("d3_plan_version", "d3_epoch"):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")
        if not _finite_non_negative(self.d3_lease_expires_at_s):
            raise ValueError("d3_lease_expires_at_s must be finite and non-negative")
        if not _finite_non_negative(self.d1_covariance_trace):
            raise ValueError("d1_covariance_trace must be finite and non-negative")
        if not _finite_non_negative(self.d1_measurement_age_s):
            raise ValueError("d1_measurement_age_s must be finite and non-negative")
        if not 0.0 <= float(self.d2_ambiguity_score) <= 1.0:
            raise ValueError("d2_ambiguity_score must be in [0, 1]")
        if int(self.d2_id_switch_count) < 0 or int(self.d2_duplicate_track_count) < 0:
            raise ValueError("D2 event counts must be non-negative")
        consistency = (
            self.d5_consistency
            if isinstance(self.d5_consistency, D5Consistency)
            else D5Consistency(str(self.d5_consistency))
        )
        object.__setattr__(self, "d5_consistency", consistency)
        for name in (
            "required_capabilities",
            "d3_assigned_member_ids",
            "d5_support_member_ids",
            "d5_hold_member_ids",
            "d5_ambiguous_member_ids",
        ):
            object.__setattr__(self, name, _unique(getattr(self, name)))
        if self.required_member_count > 1:
            if not self.coalition_id or self.coalition_version is None:
                raise ValueError("k>1 tasks require coalition_id and coalition_version")
            if int(self.coalition_version) <= 0:
                raise ValueError("coalition_version must be positive")


@dataclass(frozen=True)
class MobileReconSecondary:
    """One coordinator-only, mobile high-altitude reconnaissance secondary."""

    node_id: str
    readiness_by_region: Mapping[
        str, SecondaryReadinessEvidence | Mapping[str, Any]
    ]
    takeover_priority: int = 100
    node_role: str = field(default="mobile_high_recon", init=False)
    capability_class: str = field(default="mobile_high_recon", init=False)
    coordinator_only: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("secondary node_id must not be empty")
        evidence_by_region: dict[str, SecondaryReadinessEvidence] = {}
        for region_id, raw_evidence in self.readiness_by_region.items():
            if not str(region_id):
                raise ValueError("secondary readiness region id must not be empty")
            evidence = SecondaryReadinessEvidence.from_value(raw_evidence)
            if evidence.node_id != self.node_id:
                raise ValueError("secondary readiness node_id must match its owner")
            evidence_by_region[str(region_id)] = evidence
        object.__setattr__(self, "readiness_by_region", evidence_by_region)


@dataclass(frozen=True)
class RegionalFallbackMember:
    """Peer resource summary used by the constrained distributed fallback."""

    node_id: str
    region_ids: tuple[str, ...]
    capabilities: tuple[str, ...] = ("intercept",)
    task_bid_scores: Mapping[str, float] = field(default_factory=dict)
    available: bool = True
    communication_ready: bool = True
    operator_hold: bool = False
    max_concurrent_tasks: int = 1

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("fallback member node_id must not be empty")
        if int(self.max_concurrent_tasks) <= 0:
            raise ValueError("max_concurrent_tasks must be positive")
        regions = _unique(self.region_ids)
        capabilities = _unique(self.capabilities)
        if not regions or not capabilities:
            raise ValueError("fallback members require regions and capabilities")
        scores: dict[str, float] = {}
        for task_id, score in self.task_bid_scores.items():
            if not isfinite(float(score)):
                raise ValueError("task bid scores must be finite")
            scores[str(task_id)] = float(score)
        object.__setattr__(self, "region_ids", regions)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "task_bid_scores", scores)


@dataclass(frozen=True)
class RegionalFailoverSnapshot:
    """One versioned D4 input frame on the caller's episode clock."""

    timestamp_s: float
    scenario: RegionalScenarioMetadata
    center_health: C2Health
    center_node_id: str
    plan_id: str
    plan_version: int
    epoch: int
    lease_expires_at_s: float
    regions: tuple[RegionDefinition, ...]
    tasks: tuple[RegionalTaskEvidence, ...]
    secondary_nodes: tuple[MobileReconSecondary, ...] = ()
    fallback_members: tuple[RegionalFallbackMember, ...] = ()
    coalition_acks: tuple[CoalitionMemberAck, ...] = ()
    partitioned_region_ids: tuple[str, ...] = ()
    finalize_coalition_collection: bool = False

    def __post_init__(self) -> None:
        if not _finite_non_negative(self.timestamp_s):
            raise ValueError("timestamp_s must be finite and non-negative")
        if not self.center_node_id or not self.plan_id:
            raise ValueError("center_node_id and plan_id must not be empty")
        if int(self.plan_version) < 0 or int(self.epoch) < 0:
            raise ValueError("plan_version and epoch must be non-negative")
        if not _finite_non_negative(self.lease_expires_at_s):
            raise ValueError("lease_expires_at_s must be finite and non-negative")
        health = (
            self.center_health
            if isinstance(self.center_health, C2Health)
            else C2Health(str(self.center_health))
        )
        object.__setattr__(self, "center_health", health)
        for name in (
            "regions",
            "tasks",
            "secondary_nodes",
            "fallback_members",
            "coalition_acks",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))

        region_ids = tuple(region.region_id for region in self.regions)
        if len(set(region_ids)) != len(region_ids):
            raise ValueError("region definitions must have unique ids")
        if set(region_ids) != set(self.scenario.region_ids):
            raise ValueError("region definitions must match scenario region_ids")
        neighbor_ids = {
            neighbor
            for region in self.regions
            for neighbor in region.neighbor_region_ids
        }
        if not neighbor_ids.issubset(set(region_ids)):
            raise ValueError("region neighbor ids must reference known regions")

        task_ids = tuple(task.task_id for task in self.tasks)
        track_ids = tuple(task.global_track_id for task in self.tasks)
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("task ids must be unique")
        if len(set(track_ids)) != len(track_ids):
            raise ValueError("global_track_id values must be unique across active tasks")
        if len(self.tasks) > int(self.scenario.task_count):
            raise ValueError("active task evidence exceeds scenario task_count")
        if any(task.region_id not in set(region_ids) for task in self.tasks):
            raise ValueError("every task must reference a known region")

        secondary_ids = tuple(node.node_id for node in self.secondary_nodes)
        member_ids = tuple(member.node_id for member in self.fallback_members)
        if len(set(secondary_ids)) != len(secondary_ids):
            raise ValueError("secondary node ids must be unique")
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("fallback member ids must be unique")
        if set(secondary_ids) & set(member_ids):
            raise ValueError("mobile recon secondaries must be coordinator-only")
        if self.center_node_id in set((*secondary_ids, *member_ids)):
            raise ValueError("center_node_id must not be reused by a regional node")
        if len(secondary_ids) > int(self.scenario.recon_count):
            raise ValueError("secondary node summaries exceed scenario recon_count")
        if len(member_ids) > int(self.scenario.resource_count):
            raise ValueError("fallback member summaries exceed scenario resource_count")
        known_regions = set(region_ids)
        if any(
            region_id not in known_regions
            for node in self.secondary_nodes
            for region_id in node.readiness_by_region
        ):
            raise ValueError("secondary readiness references an unknown region")
        if any(
            region_id not in known_regions
            for member in self.fallback_members
            for region_id in member.region_ids
        ):
            raise ValueError("fallback member references an unknown region")
        partitions = _unique(self.partitioned_region_ids)
        if not set(partitions).issubset(known_regions):
            raise ValueError("partitioned_region_ids must reference known regions")
        object.__setattr__(self, "partitioned_region_ids", partitions)
        if not isinstance(self.finalize_coalition_collection, bool):
            raise TypeError("finalize_coalition_collection must be a bool")


@dataclass(frozen=True)
class CoalitionCommitSummary:
    task_id: str
    global_track_id: str
    commit_required: bool
    state: str
    coordinator_id: str
    required_member_ids: tuple[str, ...]
    acked_member_ids: tuple[str, ...]
    missing_member_ids: tuple[str, ...]
    lease_expires_at_s: float
    atomic_committed: bool
    execution_authorized: bool
    reason: str
    formation_algorithm: str | None = None
    rejected_ack_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class RegionOwnershipMetadata:
    region_id: str
    owner_id: str | None
    owner_layer: RegionalAuthorityLayer
    owner_role: str | None
    plan_id: str
    plan_version: int
    epoch: int
    lease_expires_at_s: float
    active: bool
    task_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class RegionalRegionDecision:
    region_id: str
    selected_layer: RegionalAuthorityLayer
    action: RegionalAction
    reason: str
    ownership: RegionOwnershipMetadata
    execution_allowed: bool
    fail_closed: bool
    risk_factors: tuple[str, ...]
    task_ids: tuple[str, ...]
    secondary_candidate_ids: tuple[str, ...] = ()
    selected_secondary_id: str | None = None
    secondary_readiness: Mapping[str, dict[str, Any]] = field(default_factory=dict)
    fallback_assignments: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    coalition_commits: tuple[CoalitionCommitSummary, ...] = ()
    rejection_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class RegionalFailoverDecision:
    timestamp_s: float
    scenario: RegionalScenarioMetadata
    region_decisions: tuple[RegionalRegionDecision, ...]
    schema: str = REGIONAL_FAILOVER_SCHEMA

    @property
    def region_count(self) -> int:
        return len(self.region_decisions)

    @property
    def task_count(self) -> int:
        return sum(len(decision.task_ids) for decision in self.region_decisions)

    @property
    def ownership_by_region(self) -> dict[str, RegionOwnershipMetadata]:
        return {
            decision.region_id: decision.ownership
            for decision in self.region_decisions
        }

    def to_bus_payload(self) -> dict[str, Any]:
        layer_counts = {
            layer.value: sum(
                decision.selected_layer == layer for decision in self.region_decisions
            )
            for layer in RegionalAuthorityLayer
        }
        return {
            "schema": self.schema,
            "timestamp_s": self.timestamp_s,
            "scenario": self.scenario.to_dict(),
            "summary": {
                "node_count": self.scenario.node_count,
                "resource_count": self.scenario.resource_count,
                "recon_count": self.scenario.recon_count,
                "region_count": self.region_count,
                "task_count": self.task_count,
                "execution_allowed_region_count": sum(
                    decision.execution_allowed for decision in self.region_decisions
                ),
                "fail_closed_region_count": sum(
                    decision.fail_closed for decision in self.region_decisions
                ),
                "selected_layer_counts": layer_counts,
            },
            "regions": [decision.to_dict() for decision in self.region_decisions],
        }

    def to_dict(self) -> dict[str, Any]:
        return self.to_bus_payload()


@dataclass(frozen=True)
class RegionalFailoverConfig:
    d1_covariance_trace_high: float = 2500.0
    d1_measurement_stale_s: float = 4.0
    d2_ambiguity_high: float = 0.70
    require_sustained_secondary_readiness: bool = True


class RegionalFailoverCoordinator:
    """Stateful region authority arbiter with fail-closed generation gates."""

    def __init__(self, config: RegionalFailoverConfig | None = None) -> None:
        self.config = config or RegionalFailoverConfig()
        self._accepted_ownership: dict[str, RegionOwnershipMetadata] = {}
        self._coalition_coordinator = CoalitionCommitCoordinator()
        self._coalition_states: dict[tuple[str, str], CoalitionCommitState] = {}
        self._last_timestamp_s: float | None = None

    def evaluate(self, snapshot: RegionalFailoverSnapshot) -> RegionalFailoverDecision:
        now = float(snapshot.timestamp_s)
        if self._last_timestamp_s is not None and now <= self._last_timestamp_s:
            raise ValueError("regional failover timestamps must be strictly increasing")
        self._last_timestamp_s = now
        tasks_by_region: dict[str, list[RegionalTaskEvidence]] = {
            region.region_id: [] for region in snapshot.regions
        }
        for task in snapshot.tasks:
            tasks_by_region[task.region_id].append(task)
        reserved_member_usage: dict[str, int] = {}
        decisions: list[RegionalRegionDecision] = []
        for region in sorted(snapshot.regions, key=lambda item: item.region_id):
            decisions.append(
                self._evaluate_region(
                    snapshot,
                    region,
                    tuple(
                        sorted(
                            tasks_by_region[region.region_id],
                            key=lambda item: item.task_id,
                        )
                    ),
                    reserved_member_usage=reserved_member_usage,
                )
            )
        return RegionalFailoverDecision(
            timestamp_s=now,
            scenario=snapshot.scenario,
            region_decisions=tuple(decisions),
        )

    def _evaluate_region(
        self,
        snapshot: RegionalFailoverSnapshot,
        region: RegionDefinition,
        tasks: tuple[RegionalTaskEvidence, ...],
        *,
        reserved_member_usage: dict[str, int],
    ) -> RegionalRegionDecision:
        risk_factors = self._risk_factors(snapshot, tasks)
        readiness, ready_nodes = self._secondary_readiness(snapshot, region.region_id)
        selected_secondary = ready_nodes[0] if ready_nodes else None
        candidate_ids = tuple(node.node_id for node in ready_nodes)
        task_ids = tuple(task.task_id for task in tasks)

        if region.region_id in set(snapshot.partitioned_region_ids):
            commits = self._partition_commits(region.region_id, tasks, snapshot.timestamp_s)
            center_available = snapshot.center_health != C2Health.FAILED
            return self._hold_decision(
                snapshot,
                region,
                tasks,
                selected_layer=(
                    RegionalAuthorityLayer.CENTER
                    if center_available
                    else (
                        RegionalAuthorityLayer.SECONDARY
                        if selected_secondary is not None
                        else RegionalAuthorityLayer.DISTRIBUTED
                    )
                ),
                reason="network_partition",
                risk_factors=risk_factors,
                rejection_reasons=("network_partition",),
                readiness=readiness,
                candidate_ids=candidate_ids,
                selected_secondary_id=(
                    None
                    if center_available or selected_secondary is None
                    else selected_secondary.node_id
                ),
                coalition_commits=commits,
            )

        if snapshot.center_health != C2Health.FAILED:
            return self._center_decision(
                snapshot,
                region,
                tasks,
                task_ids=task_ids,
                risk_factors=risk_factors,
                readiness=readiness,
                candidate_ids=candidate_ids,
                selected_secondary=selected_secondary,
            )

        if selected_secondary is not None:
            return self._secondary_decision(
                snapshot,
                region,
                tasks,
                selected_secondary,
                task_ids=task_ids,
                risk_factors=risk_factors,
                readiness=readiness,
                candidate_ids=candidate_ids,
                reserved_member_usage=reserved_member_usage,
            )
        return self._distributed_decision(
            snapshot,
            region,
            tasks,
            task_ids=task_ids,
            risk_factors=risk_factors,
            readiness=readiness,
            reserved_member_usage=reserved_member_usage,
        )

    def _center_decision(
        self,
        snapshot: RegionalFailoverSnapshot,
        region: RegionDefinition,
        tasks: tuple[RegionalTaskEvidence, ...],
        *,
        task_ids: tuple[str, ...],
        risk_factors: tuple[str, ...],
        readiness: Mapping[str, dict[str, Any]],
        candidate_ids: tuple[str, ...],
        selected_secondary: MobileReconSecondary | None,
    ) -> RegionalRegionDecision:
        generation_rejections = self._generation_rejections(
            region.region_id,
            snapshot,
            layer=RegionalAuthorityLayer.CENTER,
            owner_id=snapshot.center_node_id,
        )
        plan_rejections = self._plan_rejections(snapshot, tasks)
        hard_holds = _unique(
            reason
            for task in tasks
            for reason, present in (
                ("d5_friend_conflict", task.d5_friend_conflict),
                ("d5_duplicate_terminal_lock", task.d5_duplicate_terminal_lock),
            )
            if present
        )
        assignment_rejections = _unique(
            "d3_required_member_count_unsatisfied"
            for task in tasks
            if len(task.d3_assigned_member_ids) != task.required_member_count
        )
        rejections = _unique(
            (
                *generation_rejections,
                *plan_rejections,
                *hard_holds,
                *assignment_rejections,
            )
        )
        authority_lease = self._effective_lease_expires_at(snapshot, tasks)
        atomic_tasks = tuple(task for task in tasks if task.required_member_count > 1)
        atomic_assignments = {
            task.task_id: tuple(task.d3_assigned_member_ids) for task in atomic_tasks
        }
        commits: tuple[CoalitionCommitSummary, ...] = ()
        commit_rejections: tuple[str, ...] = ()
        if not rejections and atomic_tasks:
            commits = self._authorize_tasks(
                snapshot,
                region.region_id,
                atomic_tasks,
                atomic_assignments,
                coordinator_id=snapshot.center_node_id,
                coordinator_role="center",
                formation_algorithm="d3_center_assignment",
                lease_expires_at_s=authority_lease,
                secondary_readiness=None,
            )
            commit_rejections = _unique(
                summary.reason
                for summary in commits
                if not summary.execution_authorized
            )
            rejections = _unique((*rejections, *commit_rejections))

        if hard_holds:
            action = RegionalAction.HOLD_FOR_REVIEW
            reason = hard_holds[0]
        elif commit_rejections:
            action = RegionalAction.HOLD_FOR_REVIEW
            reason = commit_rejections[0]
        elif generation_rejections or plan_rejections or assignment_rejections:
            action = RegionalAction.REQUEST_CENTER_REPLAN
            reason = rejections[0]
        elif any(
            factor
            in {
                "d2_id_switch_observed",
                "d2_duplicate_track_observed",
                "d5_binding_conflict",
            }
            for factor in risk_factors
        ):
            action = RegionalAction.REQUEST_CENTER_REPLAN
            reason = "active_evidence_requires_center_replan"
        elif risk_factors and selected_secondary is not None:
            action = RegionalAction.REQUEST_SECONDARY_ASSIST
            reason = "active_evidence_requests_mobile_recon_assist"
        elif risk_factors:
            action = RegionalAction.REQUEST_CENTER_REPLAN
            reason = "active_evidence_no_ready_secondary"
        else:
            action = RegionalAction.CONTINUE_CENTER
            reason = "center_plan_current"

        execution_allowed = bool(
            float(snapshot.timestamp_s) < authority_lease
            and not rejections
            and all(summary.execution_authorized for summary in commits)
        )
        ownership = self._ownership(
            snapshot,
            region.region_id,
            task_ids,
            layer=RegionalAuthorityLayer.CENTER,
            owner_id=snapshot.center_node_id,
            owner_role="center",
            lease_expires_at_s=authority_lease,
            active=execution_allowed,
        )
        if execution_allowed:
            self._remember(ownership)
        return RegionalRegionDecision(
            region_id=region.region_id,
            selected_layer=RegionalAuthorityLayer.CENTER,
            action=action,
            reason=reason,
            ownership=ownership,
            execution_allowed=execution_allowed,
            fail_closed=not execution_allowed,
            risk_factors=risk_factors,
            task_ids=task_ids,
            secondary_candidate_ids=candidate_ids,
            selected_secondary_id=(
                None if selected_secondary is None else selected_secondary.node_id
            ),
            secondary_readiness=readiness,
            coalition_commits=commits,
            rejection_reasons=rejections,
        )

    def _secondary_decision(
        self,
        snapshot: RegionalFailoverSnapshot,
        region: RegionDefinition,
        tasks: tuple[RegionalTaskEvidence, ...],
        secondary: MobileReconSecondary,
        *,
        task_ids: tuple[str, ...],
        risk_factors: tuple[str, ...],
        readiness: Mapping[str, dict[str, Any]],
        candidate_ids: tuple[str, ...],
        reserved_member_usage: dict[str, int],
    ) -> RegionalRegionDecision:
        generation_rejections = self._generation_rejections(
            region.region_id,
            snapshot,
            layer=RegionalAuthorityLayer.SECONDARY,
            owner_id=secondary.node_id,
        )
        plan_rejections = self._plan_rejections(snapshot, tasks)
        safety_rejections = self._fallback_safety_rejections(tasks)
        rejections = _unique(
            (*generation_rejections, *plan_rejections, *safety_rejections)
        )
        evidence = secondary.readiness_by_region[region.region_id]
        claim_lease = self._effective_lease_expires_at(
            snapshot,
            tasks,
            float(evidence.lease_expires_at_s or snapshot.timestamp_s),
        )
        assignments = {
            task.task_id: tuple(task.d3_assigned_member_ids)
            for task in tasks
        }
        membership_rejections = self._validate_assignments(
            snapshot,
            region.region_id,
            tasks,
            assignments,
            reserved_member_usage=reserved_member_usage,
        )
        rejections = _unique((*rejections, *membership_rejections))
        commits: tuple[CoalitionCommitSummary, ...] = ()
        if not rejections:
            commits = self._authorize_tasks(
                snapshot,
                region.region_id,
                tasks,
                assignments,
                coordinator_id=secondary.node_id,
                coordinator_role=secondary.node_role,
                formation_algorithm="d3_assignment_secondary_coordination",
                lease_expires_at_s=claim_lease,
                secondary_readiness=evidence,
            )
            rejections = _unique(
                summary.reason
                for summary in commits
                if not summary.execution_authorized
            )
        execution_allowed = not rejections and all(
            summary.execution_authorized for summary in commits
        )
        if not tasks:
            execution_allowed = not rejections
        if not execution_allowed:
            return self._hold_decision(
                snapshot,
                region,
                tasks,
                selected_layer=RegionalAuthorityLayer.SECONDARY,
                reason=(rejections[0] if rejections else "secondary_commit_incomplete"),
                risk_factors=risk_factors,
                rejection_reasons=rejections or ("secondary_commit_incomplete",),
                readiness=readiness,
                candidate_ids=candidate_ids,
                selected_secondary_id=secondary.node_id,
                fallback_assignments=assignments,
                coalition_commits=commits,
            )
        ownership = self._ownership(
            snapshot,
            region.region_id,
            task_ids,
            layer=RegionalAuthorityLayer.SECONDARY,
            owner_id=secondary.node_id,
            owner_role=secondary.node_role,
            lease_expires_at_s=claim_lease,
            active=True,
        )
        self._reserve_member_usage(assignments, reserved_member_usage)
        self._remember(ownership)
        return RegionalRegionDecision(
            region_id=region.region_id,
            selected_layer=RegionalAuthorityLayer.SECONDARY,
            action=RegionalAction.DEGRADE_TO_SECONDARY,
            reason="center_failed_mobile_recon_takeover_committed",
            ownership=ownership,
            execution_allowed=True,
            fail_closed=False,
            risk_factors=risk_factors,
            task_ids=task_ids,
            secondary_candidate_ids=candidate_ids,
            selected_secondary_id=secondary.node_id,
            secondary_readiness=readiness,
            fallback_assignments=assignments,
            coalition_commits=commits,
        )

    def _distributed_decision(
        self,
        snapshot: RegionalFailoverSnapshot,
        region: RegionDefinition,
        tasks: tuple[RegionalTaskEvidence, ...],
        *,
        task_ids: tuple[str, ...],
        risk_factors: tuple[str, ...],
        readiness: Mapping[str, dict[str, Any]],
        reserved_member_usage: dict[str, int],
    ) -> RegionalRegionDecision:
        assignments, formation_rejections = self._form_distributed_assignments(
            snapshot,
            region.region_id,
            tasks,
            reserved_member_usage=reserved_member_usage,
        )
        coordinator_id = self._distributed_coordinator(assignments)
        generation_rejections = self._generation_rejections(
            region.region_id,
            snapshot,
            layer=RegionalAuthorityLayer.DISTRIBUTED,
            owner_id=coordinator_id,
        )
        plan_rejections = self._plan_rejections(snapshot, tasks)
        safety_rejections = self._fallback_safety_rejections(tasks)
        rejections = _unique(
            (
                *generation_rejections,
                *plan_rejections,
                *safety_rejections,
                *formation_rejections,
            )
        )
        commits: tuple[CoalitionCommitSummary, ...] = ()
        authority_lease = self._effective_lease_expires_at(snapshot, tasks)
        if coordinator_id is None:
            rejections = _unique((*rejections, "distributed_coordinator_unavailable"))
        if not rejections and coordinator_id is not None:
            commits = self._authorize_tasks(
                snapshot,
                region.region_id,
                tasks,
                assignments,
                coordinator_id=coordinator_id,
                coordinator_role="cluster_representative",
                formation_algorithm="bounded_constrained_bid_selection",
                lease_expires_at_s=authority_lease,
                secondary_readiness=None,
            )
            rejections = _unique(
                summary.reason
                for summary in commits
                if not summary.execution_authorized
            )
        execution_allowed = bool(
            coordinator_id is not None
            and not rejections
            and all(summary.execution_authorized for summary in commits)
        )
        if not tasks:
            execution_allowed = coordinator_id is not None and not rejections
        if not execution_allowed:
            return self._hold_decision(
                snapshot,
                region,
                tasks,
                selected_layer=RegionalAuthorityLayer.DISTRIBUTED,
                reason=(rejections[0] if rejections else "distributed_commit_incomplete"),
                risk_factors=risk_factors,
                rejection_reasons=rejections or ("distributed_commit_incomplete",),
                readiness=readiness,
                fallback_assignments=assignments,
                coalition_commits=commits,
            )
        ownership = self._ownership(
            snapshot,
            region.region_id,
            task_ids,
            layer=RegionalAuthorityLayer.DISTRIBUTED,
            owner_id=coordinator_id,
            owner_role="cluster_representative",
            lease_expires_at_s=authority_lease,
            active=True,
        )
        self._reserve_member_usage(assignments, reserved_member_usage)
        self._remember(ownership)
        return RegionalRegionDecision(
            region_id=region.region_id,
            selected_layer=RegionalAuthorityLayer.DISTRIBUTED,
            action=RegionalAction.DEGRADE_TO_DISTRIBUTED,
            reason="center_and_secondary_failed_atomic_distributed_fallback",
            ownership=ownership,
            execution_allowed=True,
            fail_closed=False,
            risk_factors=risk_factors,
            task_ids=task_ids,
            secondary_readiness=readiness,
            fallback_assignments=assignments,
            coalition_commits=commits,
        )

    def _hold_decision(
        self,
        snapshot: RegionalFailoverSnapshot,
        region: RegionDefinition,
        tasks: tuple[RegionalTaskEvidence, ...],
        *,
        selected_layer: RegionalAuthorityLayer,
        reason: str,
        risk_factors: tuple[str, ...],
        rejection_reasons: tuple[str, ...],
        readiness: Mapping[str, dict[str, Any]],
        candidate_ids: tuple[str, ...] = (),
        selected_secondary_id: str | None = None,
        fallback_assignments: Mapping[str, tuple[str, ...]] | None = None,
        coalition_commits: tuple[CoalitionCommitSummary, ...] = (),
    ) -> RegionalRegionDecision:
        task_ids = tuple(task.task_id for task in tasks)
        ownership = self._ownership(
            snapshot,
            region.region_id,
            task_ids,
            layer=RegionalAuthorityLayer.HOLD,
            owner_id=None,
            owner_role=None,
            lease_expires_at_s=snapshot.lease_expires_at_s,
            active=False,
        )
        return RegionalRegionDecision(
            region_id=region.region_id,
            selected_layer=selected_layer,
            action=RegionalAction.HOLD_FOR_REVIEW,
            reason=reason,
            ownership=ownership,
            execution_allowed=False,
            fail_closed=True,
            risk_factors=risk_factors,
            task_ids=task_ids,
            secondary_candidate_ids=candidate_ids,
            selected_secondary_id=selected_secondary_id,
            secondary_readiness=readiness,
            fallback_assignments=dict(fallback_assignments or {}),
            coalition_commits=coalition_commits,
            rejection_reasons=rejection_reasons,
        )

    def _secondary_readiness(
        self,
        snapshot: RegionalFailoverSnapshot,
        region_id: str,
    ) -> tuple[dict[str, dict[str, Any]], list[MobileReconSecondary]]:
        assessments: dict[str, dict[str, Any]] = {}
        ready: list[tuple[MobileReconSecondary, SecondaryReadinessAssessment, float, int]] = []
        for node in snapshot.secondary_nodes:
            evidence = node.readiness_by_region.get(region_id)
            if evidence is None:
                assessments[node.node_id] = {
                    "node_id": node.node_id,
                    "ready": False,
                    "reject_reasons": ["region_coverage_missing"],
                    "node_role": node.node_role,
                }
                continue
            assessment = assess_secondary_readiness(
                evidence,
                expected_current_time_s=snapshot.timestamp_s,
                require_sustained=self.config.require_sustained_secondary_readiness,
            )
            extra_reasons: list[str] = []
            if evidence.lease_epoch is None or int(evidence.lease_epoch) < int(snapshot.epoch):
                extra_reasons.append("secondary_lease_epoch_stale")
            if (
                evidence.lease_expires_at_s is None
                or float(evidence.lease_expires_at_s) <= float(snapshot.timestamp_s)
            ):
                extra_reasons.append("secondary_lease_expired")
            reject_reasons = _unique((*assessment.reject_reasons, *extra_reasons))
            item = {
                **assessment.to_dict(),
                "ready": not reject_reasons,
                "reject_reasons": list(reject_reasons),
                "node_role": node.node_role,
                "capability_class": node.capability_class,
                "coverage_region_id": region_id,
                "lease_epoch": evidence.lease_epoch,
                "lease_expires_at_s": evidence.lease_expires_at_s,
            }
            assessments[node.node_id] = item
            if not reject_reasons:
                ready.append(
                    (
                        node,
                        assessment,
                        float(evidence.coverage_ratio or 0.0),
                        int(evidence.lease_epoch or 0),
                    )
                )
        ready.sort(
            key=lambda item: (
                int(item[0].takeover_priority),
                -item[2],
                -item[3],
                item[0].node_id,
            )
        )
        return assessments, [item[0] for item in ready]

    def _risk_factors(
        self,
        snapshot: RegionalFailoverSnapshot,
        tasks: Sequence[RegionalTaskEvidence],
    ) -> tuple[str, ...]:
        factors: list[str] = []
        for task in tasks:
            if task.d1_covariance_trace >= self.config.d1_covariance_trace_high:
                factors.append("d1_covariance_trace_high")
            if task.d1_measurement_age_s > self.config.d1_measurement_stale_s:
                factors.append("d1_measurement_stale")
            if task.d2_ambiguity_score >= self.config.d2_ambiguity_high:
                factors.append("d2_association_ambiguity_high")
            if task.d2_id_switch_count > 0:
                factors.append("d2_id_switch_observed")
            if task.d2_duplicate_track_count > 0:
                factors.append("d2_duplicate_track_observed")
            if not task.d3_is_current:
                factors.append("d3_assignment_not_current")
            if not task.d3_resource_feasible:
                factors.append("d3_resource_infeasible")
            if task.d3_plan_id != snapshot.plan_id:
                factors.append("d3_plan_id_mismatch")
            if task.d3_plan_version != snapshot.plan_version:
                factors.append("d3_plan_version_mismatch")
            if task.d3_epoch != snapshot.epoch:
                factors.append("d3_epoch_mismatch")
            if float(snapshot.timestamp_s) >= float(task.d3_lease_expires_at_s):
                factors.append("d3_lease_expired")
            if task.d5_consistency == D5Consistency.INCONSISTENT:
                factors.append("d5_inconsistent")
            if task.d5_binding_conflict:
                factors.append("d5_binding_conflict")
            if task.d5_friend_conflict:
                factors.append("d5_friend_conflict")
            if task.d5_duplicate_terminal_lock:
                factors.append("d5_duplicate_terminal_lock")
        if snapshot.center_health in {C2Health.DEGRADED, C2Health.SUSPECT}:
            factors.append("center_health_degraded")
        return _unique(factors)

    @staticmethod
    def _plan_rejections(
        snapshot: RegionalFailoverSnapshot,
        tasks: Sequence[RegionalTaskEvidence],
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if float(snapshot.timestamp_s) >= float(snapshot.lease_expires_at_s):
            reasons.append("authority_lease_expired")
        for task in tasks:
            if task.d3_plan_id != snapshot.plan_id:
                reasons.append("d3_plan_id_mismatch")
            if task.d3_plan_version != snapshot.plan_version:
                reasons.append("d3_plan_version_mismatch")
            if task.d3_epoch != snapshot.epoch:
                reasons.append("d3_epoch_mismatch")
            if not task.d3_is_current:
                reasons.append("d3_assignment_not_current")
            if not task.d3_resource_feasible:
                reasons.append("d3_resource_infeasible")
            if float(snapshot.timestamp_s) >= float(task.d3_lease_expires_at_s):
                reasons.append("d3_lease_expired")
        return _unique(reasons)

    @staticmethod
    def _fallback_safety_rejections(
        tasks: Sequence[RegionalTaskEvidence],
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        for task in tasks:
            if task.d2_id_switch_count > 0:
                reasons.append("d2_id_switch_observed")
            if task.d2_duplicate_track_count > 0:
                reasons.append("d2_duplicate_track_observed")
            if task.d5_consistency in {D5Consistency.INCONSISTENT, D5Consistency.UNKNOWN}:
                reasons.append("d5_consistency_not_confirmed")
            if task.d5_binding_conflict:
                reasons.append("d5_binding_conflict")
            if task.d5_friend_conflict:
                reasons.append("d5_friend_conflict")
            if task.d5_duplicate_terminal_lock:
                reasons.append("d5_duplicate_terminal_lock")
        return _unique(reasons)

    @staticmethod
    def _effective_lease_expires_at(
        snapshot: RegionalFailoverSnapshot,
        tasks: Sequence[RegionalTaskEvidence],
        *additional_expiries: float,
    ) -> float:
        expiries = [
            float(snapshot.lease_expires_at_s),
            *(float(task.d3_lease_expires_at_s) for task in tasks),
            *(float(value) for value in additional_expiries),
        ]
        return min(expiries)

    def _generation_rejections(
        self,
        region_id: str,
        snapshot: RegionalFailoverSnapshot,
        *,
        layer: RegionalAuthorityLayer,
        owner_id: str | None,
    ) -> tuple[str, ...]:
        previous = self._accepted_ownership.get(region_id)
        if previous is None:
            return ()
        reasons: list[str] = []
        if snapshot.epoch < previous.epoch:
            reasons.append("authority_epoch_stale")
        if snapshot.plan_version < previous.plan_version:
            reasons.append("authority_plan_version_stale")
        same_generation = (
            snapshot.epoch == previous.epoch
            and snapshot.plan_version == previous.plan_version
        )
        if same_generation and snapshot.plan_id != previous.plan_id:
            reasons.append("authority_plan_digest_conflict")
        owner_changed = (
            previous.owner_layer != layer or previous.owner_id != owner_id
        )
        if owner_changed and not (
            snapshot.epoch > previous.epoch
            and snapshot.plan_version > previous.plan_version
        ):
            reasons.append("authority_generation_not_advanced")
        return _unique(reasons)

    def _validate_assignments(
        self,
        snapshot: RegionalFailoverSnapshot,
        region_id: str,
        tasks: Sequence[RegionalTaskEvidence],
        assignments: Mapping[str, tuple[str, ...]],
        *,
        reserved_member_usage: Mapping[str, int],
    ) -> tuple[str, ...]:
        member_by_id = {member.node_id: member for member in snapshot.fallback_members}
        usage = dict(reserved_member_usage)
        reasons: list[str] = []
        for task in tasks:
            members = _unique(assignments.get(task.task_id, ()))
            if len(members) != task.required_member_count:
                reasons.append("required_member_count_unsatisfied")
                continue
            capabilities: set[str] = set()
            for member_id in members:
                if member_id in set(task.d5_hold_member_ids):
                    reasons.append("d5_member_hold")
                member = member_by_id.get(member_id)
                if member is None:
                    reasons.append("assigned_member_summary_missing")
                    continue
                if (
                    region_id not in set(member.region_ids)
                    or not member.available
                    or not member.communication_ready
                    or member.operator_hold
                ):
                    reasons.append("assigned_member_not_executable")
                usage[member_id] = usage.get(member_id, 0) + 1
                if usage[member_id] > member.max_concurrent_tasks:
                    reasons.append("assigned_member_capacity_exceeded")
                capabilities.update(member.capabilities)
            if not set(task.required_capabilities).issubset(capabilities):
                reasons.append("required_capability_unsatisfied")
        return _unique(reasons)

    def _form_distributed_assignments(
        self,
        snapshot: RegionalFailoverSnapshot,
        region_id: str,
        tasks: Sequence[RegionalTaskEvidence],
        *,
        reserved_member_usage: Mapping[str, int],
    ) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
        usage = dict(reserved_member_usage)
        assignments: dict[str, tuple[str, ...]] = {}
        reasons: list[str] = []
        for task in tasks:
            eligible_candidates = [
                member
                for member in snapshot.fallback_members
                if region_id in set(member.region_ids)
                and member.available
                and member.communication_ready
                and not member.operator_hold
                and member.node_id not in set(task.d5_hold_member_ids)
            ]
            candidates = [
                member
                for member in eligible_candidates
                if usage.get(member.node_id, 0) < member.max_concurrent_tasks
            ]
            if not candidates and eligible_candidates:
                reasons.append("distributed_member_capacity_unsatisfied")
                continue
            candidates.sort(
                key=lambda member: (
                    -self._member_bid_score(member, task),
                    member.node_id,
                )
            )
            selected: list[RegionalFallbackMember] = []
            uncovered_capabilities = set(task.required_capabilities)
            while uncovered_capabilities and len(selected) < task.required_member_count:
                covering = [
                    member
                    for member in candidates
                    if member not in selected
                    and uncovered_capabilities & set(member.capabilities)
                ]
                if not covering:
                    break
                covering.sort(
                    key=lambda member: (
                        -len(uncovered_capabilities & set(member.capabilities)),
                        -self._member_bid_score(member, task),
                        member.node_id,
                    )
                )
                selected_member = covering[0]
                selected.append(selected_member)
                uncovered_capabilities.difference_update(selected_member.capabilities)
            if uncovered_capabilities:
                reasons.append("required_capability_unsatisfied")
                continue
            for member in candidates:
                if len(selected) >= task.required_member_count:
                    break
                if member not in selected:
                    selected.append(member)
            if len(selected) != task.required_member_count:
                reasons.append("distributed_member_capacity_unsatisfied")
                continue
            member_ids = tuple(member.node_id for member in selected)
            assignments[task.task_id] = member_ids
            for member_id in member_ids:
                usage[member_id] = usage.get(member_id, 0) + 1
        if len(assignments) != len(tasks):
            reasons.append("distributed_assignment_incomplete")
        return assignments, _unique(reasons)

    @staticmethod
    def _member_bid_score(
        member: RegionalFallbackMember,
        task: RegionalTaskEvidence,
    ) -> float:
        score = float(member.task_bid_scores.get(task.task_id, 0.0))
        if member.node_id in set(task.d5_support_member_ids):
            score += 1.0
        if member.node_id in set(task.d5_ambiguous_member_ids):
            score -= 1.0
        return score

    @staticmethod
    def _distributed_coordinator(
        assignments: Mapping[str, tuple[str, ...]],
    ) -> str | None:
        assigned_ids = sorted(
            {
                member_id
                for member_ids in assignments.values()
                for member_id in member_ids
            }
        )
        return assigned_ids[0] if assigned_ids else None

    @staticmethod
    def _reserve_member_usage(
        assignments: Mapping[str, tuple[str, ...]],
        reserved_member_usage: dict[str, int],
    ) -> None:
        for member_ids in assignments.values():
            for member_id in member_ids:
                reserved_member_usage[member_id] = (
                    reserved_member_usage.get(member_id, 0) + 1
                )

    def _authorize_tasks(
        self,
        snapshot: RegionalFailoverSnapshot,
        region_id: str,
        tasks: Sequence[RegionalTaskEvidence],
        assignments: Mapping[str, tuple[str, ...]],
        *,
        coordinator_id: str,
        coordinator_role: str,
        formation_algorithm: str,
        lease_expires_at_s: float,
        secondary_readiness: SecondaryReadinessEvidence | None,
    ) -> tuple[CoalitionCommitSummary, ...]:
        summaries: list[CoalitionCommitSummary] = []
        for task in tasks:
            required_ids = _unique(assignments.get(task.task_id, ()))
            task_lease_expires_at_s = min(
                float(lease_expires_at_s),
                float(task.d3_lease_expires_at_s),
            )
            if task.required_member_count == 1:
                authorized = bool(
                    len(required_ids) == 1
                    and float(snapshot.timestamp_s) < task_lease_expires_at_s
                )
                summaries.append(
                    CoalitionCommitSummary(
                        task_id=task.task_id,
                        global_track_id=task.global_track_id,
                        commit_required=False,
                        state=("single_member_authorized" if authorized else "aborted"),
                        coordinator_id=coordinator_id,
                        required_member_ids=required_ids,
                        acked_member_ids=required_ids if authorized else (),
                        missing_member_ids=() if authorized else required_ids,
                        lease_expires_at_s=task_lease_expires_at_s,
                        atomic_committed=False,
                        execution_authorized=authorized,
                        reason=(
                            "single_member_assignment_current"
                            if authorized
                            else "single_member_assignment_invalid"
                        ),
                        formation_algorithm=formation_algorithm,
                    )
                )
                continue

            metadata: dict[str, Any] = {
                "region_id": region_id,
                "atomic_member_authorization": True,
                "formation_algorithm": formation_algorithm,
            }
            if secondary_readiness is not None:
                metadata["secondary_readiness_evidence"] = (
                    secondary_readiness.to_dict()
                )
            state = self._coalition_coordinator.propose(
                global_track_id=task.global_track_id,
                coalition_id=str(task.coalition_id),
                coalition_version=int(task.coalition_version or 0),
                plan_id=snapshot.plan_id,
                plan_version=snapshot.plan_version,
                epoch=snapshot.epoch,
                coordinator_id=coordinator_id,
                coordinator_role=coordinator_role,
                required_member_ids=required_ids,
                lease_expires_at=task_lease_expires_at_s,
                timestamp=float(snapshot.timestamp_s),
                metadata=metadata,
            )
            rejected_reasons: list[str] = []
            for ack in snapshot.coalition_acks:
                if ack.global_track_id != task.global_track_id:
                    continue
                before = set(state.acked_member_ids)
                state = self._coalition_coordinator.record_ack(
                    state,
                    ack,
                    timestamp=float(snapshot.timestamp_s),
                )
                if ack.resource_id not in set(state.acked_member_ids) - before:
                    if state.reason.startswith("ack_"):
                        rejected_reasons.append(state.reason)
            state = self._coalition_coordinator.evaluate(
                state,
                timestamp=float(snapshot.timestamp_s),
                finalize=snapshot.finalize_coalition_collection,
            )
            self._coalition_states[(region_id, task.global_track_id)] = state
            committed = bool(
                state.state == "committed"
                and not state.missing_member_ids
                and float(snapshot.timestamp_s) < state.lease_expires_at
            )
            summaries.append(
                CoalitionCommitSummary(
                    task_id=task.task_id,
                    global_track_id=task.global_track_id,
                    commit_required=True,
                    state=state.state,
                    coordinator_id=coordinator_id,
                    required_member_ids=state.required_member_ids,
                    acked_member_ids=state.acked_member_ids,
                    missing_member_ids=state.missing_member_ids,
                    lease_expires_at_s=state.lease_expires_at,
                    atomic_committed=committed,
                    execution_authorized=committed,
                    reason=state.reason,
                    formation_algorithm=str(
                        state.metadata.get("formation_algorithm", formation_algorithm)
                    ),
                    rejected_ack_reasons=_unique(rejected_reasons),
                )
            )
        return tuple(summaries)

    def _partition_commits(
        self,
        region_id: str,
        tasks: Sequence[RegionalTaskEvidence],
        timestamp_s: float,
    ) -> tuple[CoalitionCommitSummary, ...]:
        summaries: list[CoalitionCommitSummary] = []
        for task in tasks:
            state = self._coalition_states.get((region_id, task.global_track_id))
            if state is None:
                continue
            state = self._coalition_coordinator.evaluate(
                state,
                timestamp=float(timestamp_s),
                partitioned=True,
            )
            self._coalition_states[(region_id, task.global_track_id)] = state
            summaries.append(
                CoalitionCommitSummary(
                    task_id=task.task_id,
                    global_track_id=task.global_track_id,
                    commit_required=True,
                    state=state.state,
                    coordinator_id=state.coordinator_id,
                    required_member_ids=state.required_member_ids,
                    acked_member_ids=state.acked_member_ids,
                    missing_member_ids=state.missing_member_ids,
                    lease_expires_at_s=state.lease_expires_at,
                    atomic_committed=False,
                    execution_authorized=False,
                    reason=state.reason,
                    formation_algorithm=(
                        str(state.metadata["formation_algorithm"])
                        if "formation_algorithm" in state.metadata
                        else None
                    ),
                )
            )
        return tuple(summaries)

    @staticmethod
    def _ownership(
        snapshot: RegionalFailoverSnapshot,
        region_id: str,
        task_ids: tuple[str, ...],
        *,
        layer: RegionalAuthorityLayer,
        owner_id: str | None,
        owner_role: str | None,
        lease_expires_at_s: float,
        active: bool,
    ) -> RegionOwnershipMetadata:
        return RegionOwnershipMetadata(
            region_id=region_id,
            owner_id=owner_id,
            owner_layer=layer,
            owner_role=owner_role,
            plan_id=snapshot.plan_id,
            plan_version=snapshot.plan_version,
            epoch=snapshot.epoch,
            lease_expires_at_s=float(lease_expires_at_s),
            active=active,
            task_ids=task_ids,
        )

    def _remember(self, ownership: RegionOwnershipMetadata) -> None:
        self._accepted_ownership[ownership.region_id] = ownership


def _as_mapping(value: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    raise TypeError("scenario metadata must be a mapping or expose to_dict()")


def _indexed_ids(prefix: str, count: int) -> tuple[str, ...]:
    if int(count) <= 0:
        return ()
    width = max(3, len(str(int(count))))
    return tuple(f"{prefix}-{index:0{width}d}" for index in range(int(count)))


def _unique(values: Sequence[Any] | Any) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(str(value) for value in values if str(value).strip())
    )


def _finite_non_negative(value: Any) -> bool:
    try:
        return isfinite(float(value)) and float(value) >= 0.0
    except (TypeError, ValueError):
        return False
