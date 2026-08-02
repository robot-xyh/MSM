"""Main-owned, truth-isolated scenario treatments for learning-source episodes."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .models import ScenarioConfig
from .world import VectorizedPointMassWorld


EPISODE_TREATMENT_AUDIT_SCHEMA_VERSION = "scalable3d-episode-treatment-audit-v1"
D4_REGION_GRAPH_TREATMENT_SCHEMA_VERSION = (
    "scalable3d-d4-region-graph-treatment-v1"
)
D4_SUPPLY_DEMAND_TREATMENT_SCHEMA_VERSION = (
    "scalable3d-d4-supply-demand-treatment-v1"
)

_D4_TOPOLOGY_REGION_COUNTS = {
    "directed_ring_8": 8,
    "directed_grid_3x3": 9,
    "directed_ring_12": 12,
    "directed_mesh_16": 16,
}
_D4_COMMUNICATION_CONDITIONS = frozenset(
    {
        "nominal",
        "bounded_delay_and_loss",
        "partition_then_recovery",
    }
)
_D4_SUPPLY_DEMAND_CONDITIONS = frozenset(
    {
        "source_surplus_target_deficit",
        "balanced_boundary",
        "global_shortage_with_local_candidate_edge",
    }
)
_D4_TARGET_CLASSES = frozenset(
    {
        "safe_forward_transfer",
        "safe_reverse_transfer",
        "hard_no_transfer_negative",
    }
)


@dataclass(frozen=True)
class RosterTreatmentEvent:
    event_index: int
    scheduled_timestamp_s: float
    entity_kind: str
    action: str
    ordinal_start: int
    ordinal_count: int


@dataclass(frozen=True)
class EpisodeTreatmentAuditRecord:
    """Offline aggregate evidence that one configured treatment was applied."""

    event_index: int
    scheduled_timestamp_s: float
    applied_timestamp_s: float
    entity_kind: str
    action: str
    ordinal_start: int
    ordinal_count: int
    active_count_before: int
    active_count_after: int
    schema_version: str = EPISODE_TREATMENT_AUDIT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_index": self.event_index,
            "scheduled_timestamp_s": self.scheduled_timestamp_s,
            "applied_timestamp_s": self.applied_timestamp_s,
            "entity_kind": self.entity_kind,
            "action": self.action,
            "ordinal_start": self.ordinal_start,
            "ordinal_count": self.ordinal_count,
            "active_count_before": self.active_count_before,
            "active_count_after": self.active_count_after,
            "online_truth_use_count": 0,
            "identity_values_present": False,
            "permissions": {
                "runtime_authority": False,
                "assignment": False,
                "control": False,
                "global_track_id_create": False,
                "global_track_id_write": False,
            },
        }


@dataclass(frozen=True)
class D4RegionGraphTreatment:
    """Deterministic directed topology and partition window for one D4 recipe."""

    topology_id: str
    region_count: int
    communication_condition: str
    partition_start_s: float | None
    partition_end_s: float | None
    schema_version: str = D4_REGION_GRAPH_TREATMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        expected_count = _D4_TOPOLOGY_REGION_COUNTS.get(self.topology_id)
        if expected_count is None or int(self.region_count) != expected_count:
            raise ValueError("D4 topology and region count are inconsistent")
        if self.communication_condition not in _D4_COMMUNICATION_CONDITIONS:
            raise ValueError("unsupported D4 communication condition")
        if self.communication_condition == "partition_then_recovery":
            start = float(self.partition_start_s)
            end = float(self.partition_end_s)
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or start < 0.0
                or end <= start
            ):
                raise ValueError("D4 partition window must be finite and increasing")
            object.__setattr__(self, "partition_start_s", start)
            object.__setattr__(self, "partition_end_s", end)
        elif self.partition_start_s is not None or self.partition_end_s is not None:
            raise ValueError("D4 partition window requires partition_then_recovery")

    def directed_pairs(
        self,
        region_ids: tuple[str, ...],
    ) -> tuple[tuple[str, str], ...]:
        if len(region_ids) != self.region_count or len(set(region_ids)) != len(region_ids):
            raise ValueError("D4 region inventory does not match the treatment")
        index_pairs = _d4_topology_index_pairs(self.topology_id, self.region_count)
        return tuple((region_ids[source], region_ids[target]) for source, target in index_pairs)

    def partition_active(self, timestamp_s: float) -> bool:
        timestamp = float(timestamp_s)
        if not math.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("D4 partition timestamp must be finite and non-negative")
        if self.partition_start_s is None or self.partition_end_s is None:
            return False
        return self.partition_start_s <= timestamp < self.partition_end_s

    def partitioned_pairs(
        self,
        region_ids: tuple[str, ...],
        *,
        timestamp_s: float,
    ) -> frozenset[tuple[str, str]]:
        pairs = self.directed_pairs(region_ids)
        if not self.partition_active(timestamp_s):
            return frozenset()
        first_partition = set(region_ids[: (self.region_count + 1) // 2])
        return frozenset(
            (source, target)
            for source, target in pairs
            if (source in first_partition) != (target in first_partition)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "topology_id": self.topology_id,
            "region_count": self.region_count,
            "communication_condition": self.communication_condition,
            "partition_start_s": self.partition_start_s,
            "partition_end_s": self.partition_end_s,
            "permissions": {
                "runtime_authority": False,
                "assignment": False,
                "degradation": False,
                "coalition": False,
                "control": False,
            },
        }


@dataclass(frozen=True)
class D4SupplyDemandTreatment:
    """Anonymous regional supply/demand boundary for one frozen D4 recipe.

    The treatment only changes aggregate regional features.  It does not pick
    a label or bypass the D4 projector; the actual rule and projection results
    remain the evidence source used by the D4-owned v8 builder.
    """

    topology_id: str
    region_count: int
    supply_demand_condition: str
    requested_target_class: str
    requested_transfer_resource_count: int
    hard_negative_candidate_resource_count: int
    schema_version: str = D4_SUPPLY_DEMAND_TREATMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        expected_count = _D4_TOPOLOGY_REGION_COUNTS.get(self.topology_id)
        if expected_count is None or int(self.region_count) != expected_count:
            raise ValueError("D4 supply treatment topology is inconsistent")
        if self.supply_demand_condition not in _D4_SUPPLY_DEMAND_CONDITIONS:
            raise ValueError("unsupported D4 supply/demand condition")
        if self.requested_target_class not in _D4_TARGET_CLASSES:
            raise ValueError("unsupported D4 requested target class")
        positive_count = int(self.requested_transfer_resource_count)
        negative_count = int(self.hard_negative_candidate_resource_count)
        if self.requested_target_class == "hard_no_transfer_negative":
            if positive_count != 0 or negative_count not in {1, 2, 3}:
                raise ValueError("D4 hard-negative resource count is invalid")
        elif positive_count not in {1, 2, 3} or negative_count != 0:
            raise ValueError("D4 positive transfer resource count is invalid")
        object.__setattr__(self, "requested_transfer_resource_count", positive_count)
        object.__setattr__(
            self,
            "hard_negative_candidate_resource_count",
            negative_count,
        )

    @property
    def candidate_resource_count(self) -> int:
        if self.requested_target_class == "hard_no_transfer_negative":
            return self.hard_negative_candidate_resource_count
        return self.requested_transfer_resource_count

    def candidate_index_pair(self) -> tuple[int, int]:
        """Return the deterministic anonymous edge exercised by the recipe."""

        pairs = _d4_topology_index_pairs(self.topology_id, self.region_count)
        if self.requested_target_class == "safe_forward_transfer":
            direction = "forward"
        elif self.requested_target_class == "safe_reverse_transfer":
            direction = "reverse"
        else:
            # A hard negative uses a real edge whose source is deliberately
            # left with no transferable reserve-safe budget.
            return pairs[0]
        candidates = tuple(
            pair
            for pair in pairs
            if _d4_pair_direction(self.topology_id, self.region_count, pair)
            == direction
            and _d4_pair_within_partition_half(self.region_count, pair)
        )
        if not candidates:
            raise ValueError("D4 treatment has no directed candidate edge")
        return candidates[0]

    def apply(
        self,
        region_ids: tuple[str, ...],
        region_signals: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Materialize the requested boundary without using target identity."""

        if len(region_ids) != self.region_count or len(set(region_ids)) != len(
            region_ids
        ):
            raise ValueError("D4 supply treatment region inventory mismatch")
        if set(region_signals) != set(region_ids):
            raise ValueError("D4 supply treatment signal inventory mismatch")

        treated = {region_id: dict(region_signals[region_id]) for region_id in region_ids}
        default_available_resources = (
            5
            if self.supply_demand_condition
            == "source_surplus_target_deficit"
            else 3
        )
        for region_id in region_ids:
            signal = treated[region_id]
            signal.update(
                {
                    "target_demand": 1.0,
                    "high_threat_backlog": 0.0,
                    "available_resources": default_available_resources,
                    "reserve_resources": 1,
                    "committed_resources": 1,
                }
            )

        source_index, target_index = self.candidate_index_pair()
        source = treated[region_ids[source_index]]
        target = treated[region_ids[target_index]]
        count = self.candidate_resource_count
        hard_negative = self.requested_target_class == "hard_no_transfer_negative"

        if hard_negative:
            # available - committed - reserve == 0, so a real directed edge is
            # visible to the actor but cannot pass deterministic projection.
            source.update(
                {
                    "target_demand": 0.0,
                    "available_resources": 2,
                    "reserve_resources": 1,
                    "committed_resources": 1,
                }
            )
        else:
            source.update(
                {
                    "available_resources": count + 2,
                    "reserve_resources": 1,
                    "committed_resources": 0,
                    "target_demand": (
                        float(count + 1)
                        if self.supply_demand_condition == "balanced_boundary"
                        else 0.0
                    ),
                }
            )

        if self.supply_demand_condition == "source_surplus_target_deficit":
            target.update(
                {
                    "target_demand": float(count + 2),
                    "available_resources": 2,
                    "reserve_resources": 1,
                    "committed_resources": 0,
                }
            )
            if hard_negative:
                auxiliary = _d4_auxiliary_region_index(
                    self.region_count,
                    excluded={source_index, target_index},
                )
                treated[region_ids[auxiliary]].update(
                    {
                        "target_demand": 0.0,
                        "available_resources": count + 2,
                        "reserve_resources": 1,
                        "committed_resources": 0,
                    }
                )
        elif self.supply_demand_condition == "balanced_boundary":
            target.update(
                {
                    "target_demand": 1.0,
                    "available_resources": 3,
                    "reserve_resources": 1,
                    "committed_resources": 1,
                }
            )
        else:
            auxiliary = _d4_auxiliary_region_index(
                self.region_count,
                excluded={source_index, target_index},
            )
            treated[region_ids[auxiliary]].update(
                {
                    "target_demand": 0.0,
                    "available_resources": count + 2,
                    "reserve_resources": 1,
                    "committed_resources": 0,
                }
            )
            deficit = _d4_auxiliary_region_index(
                self.region_count,
                excluded={source_index, target_index, auxiliary},
            )
            treated[region_ids[deficit]].update(
                {
                    "target_demand": float(2 * self.region_count + count),
                    "available_resources": 2,
                    "reserve_resources": 1,
                    "committed_resources": 0,
                }
            )
        return treated

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "topology_id": self.topology_id,
            "region_count": self.region_count,
            "supply_demand_condition": self.supply_demand_condition,
            "requested_target_class": self.requested_target_class,
            "requested_transfer_resource_count": (
                self.requested_transfer_resource_count
            ),
            "hard_negative_candidate_resource_count": (
                self.hard_negative_candidate_resource_count
            ),
            "candidate_index_pair": list(self.candidate_index_pair()),
            "permissions": {
                "runtime_authority": False,
                "assignment": False,
                "degradation": False,
                "coalition": False,
                "control": False,
            },
        }


class EpisodeTreatmentExecutor:
    """Apply a frozen sequence of scenario events exactly once."""

    def __init__(self, events: tuple[RosterTreatmentEvent, ...] = ()) -> None:
        ordered = tuple(events)
        if tuple(item.event_index for item in ordered) != tuple(range(len(ordered))):
            raise ValueError("treatment event indices must be contiguous")
        if any(
            ordered[index].scheduled_timestamp_s
            > ordered[index + 1].scheduled_timestamp_s + 1.0e-12
            for index in range(max(0, len(ordered) - 1))
        ):
            raise ValueError("treatment events must be ordered by scheduled timestamp")
        self._events = ordered
        self._next_index = 0

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def complete(self) -> bool:
        return self._next_index == len(self._events)

    def apply_due(
        self,
        world: VectorizedPointMassWorld,
        *,
        timestamp_s: float,
    ) -> tuple[EpisodeTreatmentAuditRecord, ...]:
        timestamp = float(timestamp_s)
        if not math.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("treatment timestamp must be finite and non-negative")
        records: list[EpisodeTreatmentAuditRecord] = []
        while self._next_index < len(self._events):
            event = self._events[self._next_index]
            if event.scheduled_timestamp_s > timestamp + 1.0e-12:
                break
            before, after = world.apply_roster_event(
                entity_kind=event.entity_kind,
                action=event.action,
                ordinal_start=event.ordinal_start,
                ordinal_count=event.ordinal_count,
            )
            records.append(
                EpisodeTreatmentAuditRecord(
                    event_index=event.event_index,
                    scheduled_timestamp_s=event.scheduled_timestamp_s,
                    applied_timestamp_s=timestamp,
                    entity_kind=event.entity_kind,
                    action=event.action,
                    ordinal_start=event.ordinal_start,
                    ordinal_count=event.ordinal_count,
                    active_count_before=before,
                    active_count_after=after,
                )
            )
            self._next_index += 1
        return tuple(records)


def build_episode_treatment_executor(
    config: ScenarioConfig,
) -> EpisodeTreatmentExecutor:
    """Resolve supported main treatments from frozen recipe metadata."""

    raw_recipe = config.metadata.get("learning_source_recipe")
    if raw_recipe is None:
        return EpisodeTreatmentExecutor()
    if not isinstance(raw_recipe, Mapping):
        raise ValueError("learning_source_recipe metadata must be a mapping")
    if raw_recipe.get("module") != "D3" or raw_recipe.get("treatment_id") != (
        "roster_event_schedule_v1"
    ):
        return EpisodeTreatmentExecutor()
    raw_events = raw_recipe.get("roster_events")
    if not isinstance(raw_events, (list, tuple)) or not raw_events:
        raise ValueError("D3 roster treatment requires non-empty roster_events")
    events: list[RosterTreatmentEvent] = []
    for index, raw in enumerate(raw_events):
        if not isinstance(raw, Mapping):
            raise ValueError("roster treatment event must be a mapping")
        fraction = float(raw["fraction_of_duration"])
        if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
            raise ValueError("roster treatment fraction is invalid")
        events.append(
            RosterTreatmentEvent(
                event_index=index,
                scheduled_timestamp_s=fraction * float(config.duration_s),
                entity_kind=str(raw["entity_kind"]),
                action=str(raw["action"]),
                ordinal_start=int(raw["ordinal_start"]),
                ordinal_count=int(raw["ordinal_count"]),
            )
        )
    events.sort(key=lambda item: (item.scheduled_timestamp_s, item.event_index))
    events = [
        RosterTreatmentEvent(
            event_index=index,
            scheduled_timestamp_s=item.scheduled_timestamp_s,
            entity_kind=item.entity_kind,
            action=item.action,
            ordinal_start=item.ordinal_start,
            ordinal_count=item.ordinal_count,
        )
        for index, item in enumerate(events)
    ]
    return EpisodeTreatmentExecutor(tuple(events))


def build_d4_region_graph_treatment(
    config: ScenarioConfig,
) -> D4RegionGraphTreatment | None:
    """Resolve a D4 topology recipe without granting module authority."""

    raw_recipe = config.metadata.get("learning_source_recipe")
    if raw_recipe is None:
        return None
    if not isinstance(raw_recipe, Mapping):
        raise ValueError("learning_source_recipe metadata must be a mapping")
    if raw_recipe.get("module") != "D4":
        return None
    topology_id = str(raw_recipe.get("topology_id", ""))
    condition = str(raw_recipe.get("communication_condition", ""))
    region_count = int(raw_recipe.get("region_count", -1))
    if region_count != int(config.region_count):
        raise ValueError("D4 recipe region count differs from scenario config")
    if condition == "partition_then_recovery":
        partition_start_s = float(config.duration_s) / 3.0
        partition_end_s = 2.0 * float(config.duration_s) / 3.0
    else:
        partition_start_s = None
        partition_end_s = None
    return D4RegionGraphTreatment(
        topology_id=topology_id,
        region_count=region_count,
        communication_condition=condition,
        partition_start_s=partition_start_s,
        partition_end_s=partition_end_s,
    )


def build_d4_supply_demand_treatment(
    config: ScenarioConfig,
) -> D4SupplyDemandTreatment | None:
    """Resolve the anonymous v8 supply/demand treatment from frozen metadata."""

    raw_recipe = config.metadata.get("learning_source_recipe")
    if raw_recipe is None:
        return None
    if not isinstance(raw_recipe, Mapping):
        raise ValueError("learning_source_recipe metadata must be a mapping")
    if raw_recipe.get("module") != "D4":
        return None
    region_count = int(raw_recipe.get("region_count", -1))
    if region_count != int(config.region_count):
        raise ValueError("D4 recipe region count differs from scenario config")
    return D4SupplyDemandTreatment(
        topology_id=str(raw_recipe.get("topology_id", "")),
        region_count=region_count,
        supply_demand_condition=str(
            raw_recipe.get("supply_demand_condition", "")
        ),
        requested_target_class=str(raw_recipe.get("requested_target_class", "")),
        requested_transfer_resource_count=int(
            raw_recipe.get("requested_transfer_resource_count", -1)
        ),
        hard_negative_candidate_resource_count=int(
            raw_recipe.get("hard_negative_candidate_resource_count", -1)
        ),
    )


def _d4_topology_index_pairs(
    topology_id: str,
    region_count: int,
) -> tuple[tuple[int, int], ...]:
    if topology_id in {"directed_ring_8", "directed_ring_12"}:
        pairs: set[tuple[int, int]] = set()
        for source in range(region_count):
            target = (source + 1) % region_count
            pairs.update(((source, target), (target, source)))
        return tuple(sorted(pairs))
    if topology_id == "directed_grid_3x3":
        pairs: set[tuple[int, int]] = set()
        side = 3
        for row in range(side):
            for column in range(side):
                source = row * side + column
                if column + 1 < side:
                    target = source + 1
                    pairs.update(((source, target), (target, source)))
                if row + 1 < side:
                    target = source + side
                    pairs.update(((source, target), (target, source)))
        return tuple(sorted(pairs))
    if topology_id == "directed_mesh_16":
        return tuple(
            (source, target)
            for source in range(region_count)
            for target in range(region_count)
            if source != target
        )
    raise ValueError("unsupported D4 topology")


def _d4_pair_direction(
    topology_id: str,
    region_count: int,
    pair: tuple[int, int],
) -> str:
    source, target = pair
    if topology_id in {"directed_ring_8", "directed_ring_12"}:
        return "forward" if target == (source + 1) % region_count else "reverse"
    return "forward" if target > source else "reverse"


def _d4_pair_within_partition_half(
    region_count: int,
    pair: tuple[int, int],
) -> bool:
    first_partition = set(range((region_count + 1) // 2))
    return (pair[0] in first_partition) == (pair[1] in first_partition)


def _d4_auxiliary_region_index(
    region_count: int,
    *,
    excluded: set[int],
) -> int:
    try:
        return next(index for index in range(region_count) if index not in excluded)
    except StopIteration as exc:  # pragma: no cover - v8 starts at eight regions
        raise ValueError("D4 treatment has no auxiliary region") from exc


__all__ = [
    "D4_REGION_GRAPH_TREATMENT_SCHEMA_VERSION",
    "D4_SUPPLY_DEMAND_TREATMENT_SCHEMA_VERSION",
    "D4RegionGraphTreatment",
    "D4SupplyDemandTreatment",
    "EPISODE_TREATMENT_AUDIT_SCHEMA_VERSION",
    "EpisodeTreatmentAuditRecord",
    "EpisodeTreatmentExecutor",
    "RosterTreatmentEvent",
    "build_d4_region_graph_treatment",
    "build_d4_supply_demand_treatment",
    "build_episode_treatment_executor",
]
