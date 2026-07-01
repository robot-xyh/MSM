from __future__ import annotations

from d4_distributed_fallback.coordinator import FailoverCoordinator
from d4_distributed_fallback.models import (
    Assignment,
    AvailabilityBand,
    C2Health,
    CommBand,
    ConfidenceBand,
    NodeRole,
    ResourceSummary,
    TrackSummary,
)
from d4_distributed_fallback.network import SimulatedNetwork


def test_degraded_planning_runs_cbba_and_sets_leader() -> None:
    node_ids = ["node-1", "node-2", "node-3"]
    resources = [
        ResourceSummary("node-1", "relay", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
        ResourceSummary("node-2", "observe", AvailabilityBand.MEDIUM, CommBand.GOOD, epoch=1),
        ResourceSummary("node-3", "observe", AvailabilityBand.LOW, CommBand.LIMITED, epoch=1),
    ]
    tasks = [
        TrackSummary("task-1", "cell-1", 1.0, ConfidenceBand.HIGH, source_count=2, epoch=1),
        TrackSummary("task-2", "cell-2", 1.0, ConfidenceBand.MEDIUM, source_count=1, epoch=1),
    ]
    coordinator = FailoverCoordinator("node-1", ["node-2", "node-3"])
    coordinator.update_health(5.0)
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)

    result = coordinator.plan_degraded(tasks, resources, network, now_s=5.0, max_rounds=10)

    assert coordinator.health == C2Health.DEGRADED
    assert coordinator.leader_id == "node-1"
    assert result.converged
    assert result.completion_rate == 1.0


def test_backup_priority_selects_backup_before_best_capability() -> None:
    resources = [
        ResourceSummary(
            "node-1",
            "relay",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            takeover_priority=50,
            epoch=1,
        ),
        ResourceSummary(
            "node-2",
            "observe",
            AvailabilityBand.MEDIUM,
            CommBand.GOOD,
            takeover_priority=10,
            lease_epoch=2,
            epoch=1,
        ),
    ]
    coordinator = FailoverCoordinator("node-1", ["node-2"])

    leader = coordinator.elect_leader(resources)

    assert leader == "node-2"


def test_center_failure_degrades_to_secondary_recon_node_before_distributed_cbba() -> None:
    node_ids = ["sec-1", "int-1", "int-2"]
    resources = [
        ResourceSummary(
            "sec-1",
            "tethered_recon",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            takeover_priority=20,
            lease_epoch=3,
            epoch=1,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-north",
        ),
        ResourceSummary("int-1", "observe", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
        ResourceSummary("int-2", "observe", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
    ]
    tasks = [
        TrackSummary("task-1", "cell-north", 1.0, ConfidenceBand.HIGH, source_count=3, epoch=1),
    ]
    coordinator = FailoverCoordinator("int-1", ["sec-1", "int-2"])
    coordinator.update_health(5.0)
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)

    result = coordinator.plan_degraded(tasks, resources, network, now_s=5.0, max_rounds=10)

    assert coordinator.leader_id == "sec-1"
    assert result.final_views["coordination_mode"]["state"] == "secondary_node"
    assert result.final_views["coordination_mode"]["leader_role"] == "secondary_recon"
    assert all(assignment.owner != "sec-1" for assignment in result.assignments.values())


def test_secondary_unavailable_falls_back_to_distributed_cbba() -> None:
    node_ids = ["sec-1", "int-1", "int-2"]
    resources = [
        ResourceSummary(
            "sec-1",
            "tethered_recon",
            AvailabilityBand.NONE,
            CommBand.GOOD,
            takeover_priority=20,
            epoch=1,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-north",
        ),
        ResourceSummary(
            "int-1",
            "observe",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            epoch=1,
            node_role=NodeRole.CLUSTER_REPRESENTATIVE,
        ),
        ResourceSummary("int-2", "observe", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
    ]
    tasks = [TrackSummary("task-1", "cell-north", 1.0, ConfidenceBand.HIGH, source_count=3, epoch=1)]
    coordinator = FailoverCoordinator("int-1", ["sec-1", "int-2"])
    coordinator.update_health(5.0)
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)

    result = coordinator.plan_degraded(tasks, resources, network, now_s=5.0, max_rounds=10)

    assert coordinator.leader_id == "int-1"
    assert result.final_views["coordination_mode"]["state"] == "distributed_cbba"


def test_degraded_planning_without_leader_returns_safe_hold_plan() -> None:
    coordinator = FailoverCoordinator("node-1", ["node-2"])
    coordinator.update_health(5.0)
    network = SimulatedNetwork(node_ids=["node-1", "node-2"])
    resources = [
        ResourceSummary("node-1", "observe", AvailabilityBand.NONE, CommBand.GOOD),
        ResourceSummary("node-2", "observe", AvailabilityBand.NONE, CommBand.GOOD),
    ]

    result = coordinator.plan_degraded([], resources, network, now_s=5.0)

    assert not result.converged
    assert result.assignments == {}
    assert result.completion_rate == 0.0


def test_nonconverged_cbba_does_not_publish_assignments() -> None:
    node_ids = ["node-1", "node-2"]
    resources = [
        ResourceSummary("node-1", "observe", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
        ResourceSummary("node-2", "observe", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
    ]
    tasks = [
        TrackSummary("task-1", "cell-1", 1.0, ConfidenceBand.HIGH, source_count=2, epoch=1),
        TrackSummary("task-2", "cell-2", 1.0, ConfidenceBand.HIGH, source_count=2, epoch=1),
    ]
    coordinator = FailoverCoordinator("node-1", ["node-2"])
    coordinator.update_health(5.0)
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=1.0)

    result = coordinator.plan_degraded(tasks, resources, network, now_s=5.0, max_rounds=1)

    assert not result.converged
    assert result.assignments == {}
    assert result.completion_rate == 0.0


def test_center_recovery_requires_clean_merge_and_human_acceptance() -> None:
    coordinator = FailoverCoordinator("node-1", ["node-2", "node-3"])
    fallback = [Assignment("task-1", "node-1", 10.0, epoch=1)]
    center_same = [Assignment("task-1", "node-1", 10.0, epoch=1, mode="center")]

    result = coordinator.merge_recovery(center_same, fallback, human_accept=True, now_s=10.0)

    assert result.restored_normal
    assert result.accepted == ["task-1"]
    assert coordinator.health == C2Health.NORMAL


def test_center_recovery_holds_degraded_on_conflict() -> None:
    coordinator = FailoverCoordinator("node-1", ["node-2", "node-3"])
    fallback = [Assignment("task-1", "node-1", 10.0, epoch=2)]
    stale_center = [Assignment("task-1", "node-2", 9.0, epoch=1, mode="center")]

    result = coordinator.merge_recovery(stale_center, fallback, human_accept=True, now_s=10.0)

    assert not result.restored_normal
    assert result.conflicts == ["task-1"]
    assert coordinator.health == C2Health.DEGRADED
