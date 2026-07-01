from __future__ import annotations

from d4_distributed_fallback.cbba import CBBANegotiator
from d4_distributed_fallback.models import (
    AvailabilityBand,
    CommBand,
    ConfidenceBand,
    ResourceSummary,
    TrackSummary,
)
from d4_distributed_fallback.network import SimulatedNetwork


def _resources(node_ids: list[str]) -> list[ResourceSummary]:
    return [
        ResourceSummary(
            node_id=node_id,
            capability_class="observe",
            availability_band=AvailabilityBand.HIGH,
            comm_band=CommBand.GOOD,
            epoch=1,
        )
        for node_id in node_ids
    ]


def _tasks(count: int) -> list[TrackSummary]:
    return [
        TrackSummary(
            track_id=f"task-{idx + 1}",
            coarse_cell=f"cell-{idx + 1}",
            age_s=1.0,
            confidence_band=ConfidenceBand.HIGH,
            source_count=2,
            epoch=1,
        )
        for idx in range(count)
    ]


def test_cbba_converges_without_duplicate_task_owners() -> None:
    node_ids = ["node-1", "node-2", "node-3", "node-4"]
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)
    result = CBBANegotiator(node_ids=node_ids, max_rounds=10).run(
        tasks=_tasks(3),
        resources=_resources(node_ids),
        network=network,
    )

    assert result.converged
    assert result.completion_rate == 1.0
    assert len(result.assignments) == 3
    assert len(set(result.assignments)) == 3
    assert result.messages_sent > 0


def test_cbba_tie_break_prefers_lower_node_id() -> None:
    node_ids = ["node-2", "node-1"]
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)
    result = CBBANegotiator(node_ids=node_ids, max_rounds=10).run(
        tasks=_tasks(1),
        resources=_resources(node_ids),
        network=network,
    )

    assert result.converged
    assert result.assignments["task-1"].owner == "node-1"
