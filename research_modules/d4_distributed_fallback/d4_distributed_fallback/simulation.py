"""Scenario runner for center outage and distributed fallback simulation."""

from __future__ import annotations

import json
from typing import Any

from .coordinator import FailoverCoordinator
from .models import (
    AvailabilityBand,
    C2Health,
    CommBand,
    ConfidenceBand,
    ResourceSummary,
    TrackSummary,
    to_jsonable,
)
from .network import SimulatedNetwork


def default_resources(node_count: int, epoch: int = 1) -> list[ResourceSummary]:
    capability_cycle = ["relay", "observe", "observe", "relay", "observe"]
    comm_cycle = [CommBand.GOOD, CommBand.LIMITED, CommBand.GOOD, CommBand.LIMITED, CommBand.POOR]
    availability_cycle = [
        AvailabilityBand.HIGH,
        AvailabilityBand.HIGH,
        AvailabilityBand.MEDIUM,
        AvailabilityBand.MEDIUM,
        AvailabilityBand.LOW,
    ]
    return [
        ResourceSummary(
            node_id=f"node-{idx + 1}",
            capability_class=capability_cycle[idx % len(capability_cycle)],
            availability_band=availability_cycle[idx % len(availability_cycle)],
            comm_band=comm_cycle[idx % len(comm_cycle)],
            operator_hold=False,
            epoch=epoch,
        )
        for idx in range(node_count)
    ]


def default_tasks(task_count: int = 4, epoch: int = 1) -> list[TrackSummary]:
    confidence_cycle = [ConfidenceBand.HIGH, ConfidenceBand.MEDIUM, ConfidenceBand.HIGH, ConfidenceBand.LOW]
    return [
        TrackSummary(
            track_id=f"task-{idx + 1}",
            coarse_cell=f"cell-{idx + 1}",
            age_s=1.0 + idx * 0.75,
            confidence_band=confidence_cycle[idx % len(confidence_cycle)],
            source_count=1 + (idx % 3),
            epoch=epoch,
        )
        for idx in range(task_count)
    ]


def run_failover_simulation(
    node_count: int = 5,
    task_count: int = 4,
    failure_at_s: float = 30.0,
    end_time_s: float = 45.0,
    dt_s: float = 0.5,
    packet_loss: float = 0.10,
    min_delay_s: float = 0.1,
    max_delay_s: float = 0.5,
    seed: int = 7,
) -> dict[str, Any]:
    if not 3 <= node_count <= 5:
        raise ValueError("node_count must be between 3 and 5 for this scenario")
    epoch = 1
    resources = default_resources(node_count=node_count, epoch=epoch)
    tasks = default_tasks(task_count=min(task_count, node_count), epoch=epoch)
    node_ids = [resource.node_id for resource in resources]
    coordinators = {
        node_id: FailoverCoordinator(
            node_id=node_id,
            peer_ids=[peer for peer in node_ids if peer != node_id],
            epoch=epoch,
            heartbeat_warning_s=1.0,
            heartbeat_stale_s=2.0,
            heartbeat_failure_s=4.0,
        )
        for node_id in node_ids
    }
    cbba_result = None
    takeover_started_at_s = None
    takeover_completed_at_s = None

    now_s = 0.0
    while now_s <= end_time_s:
        for coordinator in coordinators.values():
            if now_s < failure_at_s:
                coordinator.observe_center(now_s, heartbeat_ok=True, digest_ok=True, center_epoch=epoch)
            else:
                coordinator.update_health(now_s)

        failed_nodes = [
            coordinator.node_id
            for coordinator in coordinators.values()
            if coordinator.health == C2Health.FAILED
        ]
        quorum = node_count // 2 + 1
        if cbba_result is None and len(failed_nodes) >= quorum:
            takeover_started_at_s = now_s
            network = SimulatedNetwork(
                node_ids=node_ids,
                packet_loss=packet_loss,
                min_delay_s=min_delay_s,
                max_delay_s=max_delay_s,
                seed=seed,
            )
            cbba_result = coordinators[node_ids[0]].plan_degraded(
                tasks=tasks,
                resources=resources,
                network=network,
                now_s=now_s,
                bundle_limit=1,
                max_rounds=18,
                round_period_s=0.5,
            )
            takeover_completed_at_s = now_s + cbba_result.duration_s
            break
        now_s += dt_s

    transitions = {
        node_id: [transition.to_dict() for transition in coordinator.transition_log]
        for node_id, coordinator in coordinators.items()
    }
    if cbba_result is None:
        return {
            "node_count": node_count,
            "task_count": len(tasks),
            "center_failure_at_s": failure_at_s,
            "takeover_time_s": None,
            "takeover_started_at_s": takeover_started_at_s,
            "converged": False,
            "reason": "quorum_not_reached_before_end_time",
            "health_transitions": transitions,
        }

    assignments = {
        task_id: assignment.to_dict()
        for task_id, assignment in sorted(cbba_result.assignments.items())
    }
    return {
        "node_count": node_count,
        "task_count": len(tasks),
        "center_failure_at_s": failure_at_s,
        "takeover_started_at_s": takeover_started_at_s,
        "takeover_completed_at_s": takeover_completed_at_s,
        "takeover_time_s": None
        if takeover_completed_at_s is None
        else round(takeover_completed_at_s - failure_at_s, 3),
        "consensus_rounds": cbba_result.consensus_rounds,
        "assignment_completion_rate": round(cbba_result.completion_rate, 4),
        "conflict_count": cbba_result.conflict_count,
        "messages_sent": cbba_result.messages_sent,
        "messages_delivered": cbba_result.messages_delivered,
        "messages_dropped": cbba_result.messages_dropped,
        "estimated_bytes": cbba_result.estimated_bytes,
        "converged": cbba_result.converged,
        "assignments": assignments,
        "health_transitions": transitions,
    }


def metrics_to_json(metrics: dict[str, Any]) -> str:
    return json.dumps(to_jsonable(metrics), indent=2, sort_keys=True)
