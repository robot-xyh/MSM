"""Cheap fail-closed viability audit for the frozen D4 A2 v8 source.

The audit executes the D4-owned rule policy, deterministic projector, runtime
evidence builder, and strict v8 DTO validation entirely in memory.  It covers
every frozen schedule cell without running the 3D world or writing a dataset.
The synthetic regional snapshots reproduce the frozen aggregate treatment
contract; they contain no target identity or truth identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Sequence

from .region_resource import (
    RecommendationSource,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
)
from .region_resource_v8_development_contract import (
    V8_COMMUNICATION_CONDITIONS,
    V8_REQUESTED_SEEDS,
    V8_SUPPLY_DEMAND_CONDITIONS,
    V8_TOPOLOGY_REGION_COUNTS,
    V8_TRANSFER_CLASSES,
    V8NoAuthorityPermissions,
    V8RequestScheduleEntry,
    V8TransferClass,
    canonical_v8_sha256,
    classify_v8_edge_direction,
    expected_v8_directed_edges,
)
from .region_resource_v8_runtime_evidence import (
    V8AnonymousCandidateEvidence,
    V8RuntimeEpisodeEvidenceBuilder,
    V8RuntimeFrameEvidence,
)


V8_SOURCE_VIABILITY_AUDIT_SCHEMA = (
    "d4-region-resource-v8-source-viability-audit-v1"
)
V8_SOURCE_VIABILITY_READY_STATUS = "all_frozen_cells_viable_in_memory"


class RegionResourceV8SourceViabilityError(ValueError):
    """The frozen source schedule cannot be proven viable."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        suffix = str(detail).strip()
        super().__init__(f"{self.code}:{suffix}" if suffix else self.code)


@dataclass(frozen=True)
class V8SourceViabilityAudit:
    schedule_episode_count: int
    audited_frame_count: int
    full_cell_combination_count: int
    reduced_combination_count: int
    topology_ids: tuple[str, ...]
    supply_demand_conditions: tuple[str, ...]
    communication_conditions: tuple[str, ...]
    target_classes: tuple[str, ...]
    positive_transfer_resource_counts: tuple[int, ...]
    hard_negative_candidate_resource_counts: tuple[int, ...]
    edge_count_by_topology: tuple[tuple[str, int], ...]
    cell_evidence_sha256: str
    all_cells_viable: bool = True
    online_truth_use_count: int = 0
    failure_count: int = 0
    permissions: V8NoAuthorityPermissions = V8NoAuthorityPermissions()
    status: str = V8_SOURCE_VIABILITY_READY_STATUS
    schema: str = V8_SOURCE_VIABILITY_AUDIT_SCHEMA
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if self.schema != V8_SOURCE_VIABILITY_AUDIT_SCHEMA:
            raise ValueError("v8_source_viability_schema_mismatch")
        if self.status != V8_SOURCE_VIABILITY_READY_STATUS:
            raise ValueError("v8_source_viability_status_mismatch")
        if not self.all_cells_viable or self.failure_count != 0:
            raise ValueError("v8_source_viability_not_ready")
        if self.online_truth_use_count != 0:
            raise ValueError("v8_source_viability_truth_use_nonzero")
        if self.schedule_episode_count != len(V8_REQUESTED_SEEDS):
            raise ValueError("v8_source_viability_episode_count_mismatch")
        if self.full_cell_combination_count != len(V8_REQUESTED_SEEDS):
            raise ValueError("v8_source_viability_full_coverage_mismatch")
        if self.reduced_combination_count != 108:
            raise ValueError("v8_source_viability_reduced_coverage_mismatch")
        if not isinstance(self.permissions, V8NoAuthorityPermissions):
            raise ValueError("v8_source_viability_permissions_invalid")
        expected = canonical_v8_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("v8_source_viability_content_sha256_mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "schedule_episode_count": self.schedule_episode_count,
            "audited_frame_count": self.audited_frame_count,
            "full_cell_combination_count": self.full_cell_combination_count,
            "reduced_combination_count": self.reduced_combination_count,
            "topology_ids": list(self.topology_ids),
            "supply_demand_conditions": list(self.supply_demand_conditions),
            "communication_conditions": list(self.communication_conditions),
            "target_classes": list(self.target_classes),
            "positive_transfer_resource_counts": list(
                self.positive_transfer_resource_counts
            ),
            "hard_negative_candidate_resource_counts": list(
                self.hard_negative_candidate_resource_counts
            ),
            "edge_count_by_topology": {
                topology_id: edge_count
                for topology_id, edge_count in self.edge_count_by_topology
            },
            "cell_evidence_sha256": self.cell_evidence_sha256,
            "all_cells_viable": self.all_cells_viable,
            "online_truth_use_count": self.online_truth_use_count,
            "failure_count": self.failure_count,
            "permissions": self.permissions.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}


def audit_v8_frozen_source_viability(
    schedule: Sequence[V8RequestScheduleEntry],
) -> V8SourceViabilityAudit:
    """Prove every frozen cell can traverse the D4 source DTO builder."""

    recipes = tuple(schedule)
    return _audit_v8_frozen_source_viability_cached(recipes)


@lru_cache(maxsize=4)
def _audit_v8_frozen_source_viability_cached(
    recipes: tuple[V8RequestScheduleEntry, ...],
) -> V8SourceViabilityAudit:
    if len(recipes) != len(V8_REQUESTED_SEEDS):
        raise RegionResourceV8SourceViabilityError(
            "v8_source_viability_schedule_count_mismatch"
        )
    if tuple(item.seed for item in recipes) != V8_REQUESTED_SEEDS:
        raise RegionResourceV8SourceViabilityError(
            "v8_source_viability_seed_order_mismatch"
        )

    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    audited_frames = 0
    for schedule_index, recipe in enumerate(recipes):
        if not isinstance(recipe, V8RequestScheduleEntry):
            raise RegionResourceV8SourceViabilityError(
                "v8_source_viability_recipe_dto_required",
                str(schedule_index),
            )
        try:
            row = _audit_cell(schedule_index, recipe)
        except (KeyError, TypeError, ValueError) as exc:
            failures.append(
                f"sequence={schedule_index},seed={recipe.seed},"
                f"reason={type(exc).__name__}:{exc}"
            )
            continue
        rows.append(row)
        audited_frames += int(row["frame_count"])

    if failures:
        raise RegionResourceV8SourceViabilityError(
            "v8_source_viability_frozen_cell_failed",
            "|".join(failures[:8]),
        )

    full_combinations = {
        (
            item.topology_id,
            item.supply_demand_condition,
            item.communication_condition,
            item.requested_target_class.value,
            _requested_count(item),
        )
        for item in recipes
    }
    reduced_combinations = {
        (
            item.topology_id,
            item.communication_condition,
            item.requested_target_class.value,
            _requested_count(item),
        )
        for item in recipes
    }
    if len(full_combinations) != 324 or len(reduced_combinations) != 108:
        raise RegionResourceV8SourceViabilityError(
            "v8_source_viability_factorial_coverage_incomplete"
        )

    return V8SourceViabilityAudit(
        schedule_episode_count=len(recipes),
        audited_frame_count=audited_frames,
        full_cell_combination_count=len(full_combinations),
        reduced_combination_count=len(reduced_combinations),
        topology_ids=tuple(V8_TOPOLOGY_REGION_COUNTS),
        supply_demand_conditions=tuple(V8_SUPPLY_DEMAND_CONDITIONS),
        communication_conditions=tuple(V8_COMMUNICATION_CONDITIONS),
        target_classes=tuple(V8_TRANSFER_CLASSES),
        positive_transfer_resource_counts=(1, 2, 3),
        hard_negative_candidate_resource_counts=(1, 2, 3),
        edge_count_by_topology=tuple(
            (topology_id, len(expected_v8_directed_edges(topology_id)))
            for topology_id in V8_TOPOLOGY_REGION_COUNTS
        ),
        cell_evidence_sha256=canonical_v8_sha256(rows),
    )


def _audit_cell(
    schedule_index: int,
    recipe: V8RequestScheduleEntry,
) -> dict[str, Any]:
    policy = RuleRegionResourcePolicy()
    source_index, target_index = _candidate_pair(recipe)
    expected_direction = (
        "hard_negative_actual_edge"
        if recipe.requested_target_class == V8TransferClass.HARD_NO_TRANSFER
        else classify_v8_edge_direction(
            recipe.topology_id,
            source_index,
            target_index,
        )
    )
    builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id=f"d4-a2-v8-viability-seed-{recipe.seed}",
        recipe=recipe,
        rule_policy=policy,
    )
    frame_count = 0
    frame_hashes: list[str] = []
    label_hashes: list[str] = []
    for frame_index, (timestamp_s, partition_active) in enumerate(
        _communication_frames(recipe.communication_condition)
    ):
        snapshot = _snapshot_for_recipe(
            recipe,
            timestamp_s=timestamp_s,
            partition_active=partition_active,
        )
        edge = next(
            (
                item
                for item in snapshot.edges
                if item.source_region_id
                == snapshot.regions[source_index].region_id
                and item.target_region_id
                == snapshot.regions[target_index].region_id
            ),
            None,
        )
        if edge is None:
            raise RegionResourceV8SourceViabilityError(
                "v8_source_viability_candidate_edge_missing"
            )
        count = _requested_count(recipe)
        r0 = policy.recommend(snapshot)
        transfer = RegionTransferSuggestion(
            source_region_id=edge.source_region_id,
            target_region_id=edge.target_region_id,
            resource_count=count,
            edge_id=edge.edge_id,
            expected_transfer_time_s=edge.transfer_time_s,
            reasons=("anonymous_frozen_recipe_candidate",),
        )
        raw = RegionResourceRecommendation(
            snapshot_id=snapshot.snapshot_id,
            scenario_id=snapshot.scenario_id,
            scenario_version=snapshot.scenario_version,
            seed=snapshot.seed,
            authority_digest=snapshot.authority_digest,
            created_at_s=snapshot.timestamp_s,
            policy_name="d4-v8-viability-anonymous-actor",
            policy_version="v1",
            source=RecommendationSource.LEARNED,
            confidence=0.9,
            actions=r0.actions,
            transfers=(transfer,),
            projected=False,
            planning_authority_digest=snapshot.planning_authority_digest,
        )
        projected = policy.projector.project(snapshot, raw)
        frame, label = builder.stage_frame(
            frame_index=frame_index,
            evidence=V8RuntimeFrameEvidence(
                snapshot=snapshot,
                r0_recommendation=r0,
                raw_actor_proposal=raw,
                projected_actor_recommendation=projected,
                anonymous_candidates=(
                    V8AnonymousCandidateEvidence(
                        transfer=transfer,
                        activation_score=0.9,
                    ),
                ),
                arrival_timestamp=timestamp_s
                + max(node.communication_latency_s for node in snapshot.regions),
            ),
        )
        frame_count += 1
        frame_hashes.append(frame.content_sha256)
        label_hashes.append(canonical_v8_sha256(label.to_dict()))
    episode = builder.finalize()
    if len(episode.frames) != frame_count or len(episode.labels) != frame_count:
        raise RegionResourceV8SourceViabilityError(
            "v8_source_viability_episode_frame_count_mismatch"
        )
    return {
        "schedule_index": schedule_index,
        "seed": recipe.seed,
        "topology_id": recipe.topology_id,
        "supply_demand_condition": recipe.supply_demand_condition,
        "communication_condition": recipe.communication_condition,
        "requested_target_class": recipe.requested_target_class.value,
        "requested_resource_count": _requested_count(recipe),
        "candidate_pair": [source_index, target_index],
        "candidate_direction": expected_direction,
        "directed_edge_count": len(expected_v8_directed_edges(recipe.topology_id)),
        "frame_count": frame_count,
        "frame_sha256": frame_hashes,
        "label_sha256": label_hashes,
        "online_truth_use_count": 0,
        "status": "viable",
    }


def _candidate_pair(recipe: V8RequestScheduleEntry) -> tuple[int, int]:
    pairs = expected_v8_directed_edges(recipe.topology_id)
    if recipe.requested_target_class == V8TransferClass.HARD_NO_TRANSFER:
        return pairs[0]
    expected = (
        "forward"
        if recipe.requested_target_class == V8TransferClass.SAFE_FORWARD
        else "reverse"
    )
    half = set(range((recipe.region_count + 1) // 2))
    candidates = tuple(
        pair
        for pair in pairs
        if classify_v8_edge_direction(recipe.topology_id, *pair) == expected
        and ((pair[0] in half) == (pair[1] in half))
    )
    if not candidates:
        raise RegionResourceV8SourceViabilityError(
            "v8_source_viability_directed_candidate_missing"
        )
    return candidates[0]


def _snapshot_for_recipe(
    recipe: V8RequestScheduleEntry,
    *,
    timestamp_s: float,
    partition_active: bool,
) -> RegionResourceSnapshot:
    region_ids = tuple(f"region-{index:03d}" for index in range(recipe.region_count))
    signals = _treated_signals(recipe)
    latency_s, loss_rate = _communication_quality(recipe.communication_condition)
    nodes = tuple(
        RegionResourceNode(
            region_id=region_id,
            target_demand=float(signal["target_demand"]),
            high_threat_backlog=0.0,
            d1_uncertainty=0.0,
            d2_uncertainty=0.0,
            d5_visibility=1.0,
            d5_consistency=1.0,
            available_resources=int(signal["available_resources"]),
            reserve_resources=int(signal["reserve_resources"]),
            committed_resources=int(signal["committed_resources"]),
            secondary_coverage=1.0,
            secondary_readiness=1.0,
            communication_capacity=40.0,
            communication_latency_s=latency_s,
            packet_loss_rate=loss_rate,
            current_owner_id="d3_central",
            current_owner_layer="center",
            plan_id="d4-v8-viability-plan",
            plan_version=1,
            epoch=1,
            lease_expires_at_s=10.0,
            coalition_ack_complete=True,
            owner_active=True,
            fault_fenced=False,
        )
        for region_id, signal in zip(region_ids, signals, strict=True)
    )
    first_half = set(range((recipe.region_count + 1) // 2))
    edges: list[RegionResourceEdge] = []
    for source_index, target_index in expected_v8_directed_edges(recipe.topology_id):
        source = nodes[source_index]
        partitioned = bool(
            partition_active
            and ((source_index in first_half) != (target_index in first_half))
        )
        edges.append(
            RegionResourceEdge(
                source_region_id=region_ids[source_index],
                target_region_id=region_ids[target_index],
                transferable_resources=max(
                    0,
                    source.available_resources
                    - source.reserve_resources
                    - source.committed_resources,
                ),
                distance_m=100.0,
                transfer_time_s=2.0,
                bandwidth_mbps=40.0,
                communication_available=not partitioned,
                maneuver_available=True,
                partitioned=partitioned,
                bidirectional=False,
            )
        )
    return RegionResourceSnapshot(
        snapshot_id=f"d4-v8-viability-{recipe.seed}-{timestamp_s:.2f}",
        scenario_id="d4-v8-viability",
        scenario_version="v1",
        seed=recipe.seed,
        timestamp_s=timestamp_s,
        regions=nodes,
        edges=tuple(edges),
    )


def _treated_signals(
    recipe: V8RequestScheduleEntry,
) -> tuple[Mapping[str, int | float], ...]:
    default_available = (
        5
        if recipe.supply_demand_condition == "source_surplus_target_deficit"
        else 3
    )
    signals: list[dict[str, int | float]] = [
        {
            "target_demand": 1.0,
            "available_resources": default_available,
            "reserve_resources": 1,
            "committed_resources": 1,
        }
        for _ in range(recipe.region_count)
    ]
    source_index, target_index = _candidate_pair(recipe)
    count = _requested_count(recipe)
    hard_negative = (
        recipe.requested_target_class == V8TransferClass.HARD_NO_TRANSFER
    )
    if hard_negative:
        signals[source_index].update(
            target_demand=0.0,
            available_resources=2,
            reserve_resources=1,
            committed_resources=1,
        )
    else:
        signals[source_index].update(
            available_resources=count + 2,
            reserve_resources=1,
            committed_resources=0,
            target_demand=(
                float(count + 1)
                if recipe.supply_demand_condition == "balanced_boundary"
                else 0.0
            ),
        )

    if recipe.supply_demand_condition == "source_surplus_target_deficit":
        signals[target_index].update(
            target_demand=float(count + 2),
            available_resources=2,
            reserve_resources=1,
            committed_resources=0,
        )
        if hard_negative:
            auxiliary = _auxiliary_index(
                recipe.region_count,
                {source_index, target_index},
            )
            signals[auxiliary].update(
                target_demand=0.0,
                available_resources=count + 2,
                reserve_resources=1,
                committed_resources=0,
            )
    elif recipe.supply_demand_condition == "balanced_boundary":
        signals[target_index].update(
            target_demand=1.0,
            available_resources=3,
            reserve_resources=1,
            committed_resources=1,
        )
    else:
        auxiliary = _auxiliary_index(
            recipe.region_count,
            {source_index, target_index},
        )
        signals[auxiliary].update(
            target_demand=0.0,
            available_resources=count + 2,
            reserve_resources=1,
            committed_resources=0,
        )
        deficit = _auxiliary_index(
            recipe.region_count,
            {source_index, target_index, auxiliary},
        )
        signals[deficit].update(
            target_demand=float(2 * recipe.region_count + count),
            available_resources=2,
            reserve_resources=1,
            committed_resources=0,
        )
    return tuple(signals)


def _communication_frames(condition: str) -> tuple[tuple[float, bool], ...]:
    if condition == "partition_then_recovery":
        return ((0.75, False), (1.25, True), (2.25, False))
    return ((0.75, False), (1.0, False), (2.0, False))


def _communication_quality(condition: str) -> tuple[float, float]:
    if condition == "bounded_delay_and_loss":
        return 0.18, 0.20
    return 0.04, 0.01


def _requested_count(recipe: V8RequestScheduleEntry) -> int:
    if recipe.requested_target_class == V8TransferClass.HARD_NO_TRANSFER:
        return recipe.hard_negative_candidate_resource_count
    return recipe.requested_transfer_resource_count


def _auxiliary_index(region_count: int, excluded: set[int]) -> int:
    try:
        return next(index for index in range(region_count) if index not in excluded)
    except StopIteration as exc:  # pragma: no cover - v8 starts at eight regions
        raise RegionResourceV8SourceViabilityError(
            "v8_source_viability_auxiliary_region_missing"
        ) from exc


__all__ = [
    "RegionResourceV8SourceViabilityError",
    "V8_SOURCE_VIABILITY_AUDIT_SCHEMA",
    "V8_SOURCE_VIABILITY_READY_STATUS",
    "V8SourceViabilityAudit",
    "audit_v8_frozen_source_viability",
]
