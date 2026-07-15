from __future__ import annotations

from dataclasses import replace

import pytest

from d4_distributed_fallback.coordinator import FailoverCoordinator
from d4_distributed_fallback.models import (
    Assignment,
    AvailabilityBand,
    C2Health,
    CommBand,
    CommunicationSummary,
    ConfidenceBand,
    NodeRole,
    LinkType,
    PayloadKind,
    ResourceSummary,
    TrackSummary,
)
from d4_distributed_fallback.network import SimulatedNetwork


def _strict_readiness_fields() -> dict[str, object]:
    return {
        "lease_expires_at_s": 10.0,
        "heartbeat_timestamp_s": 4.9,
        "heartbeat_stale_after_s": 1.0,
        "cue_freshness_s": 0.1,
        "gimbal_pointing_ok": True,
        "secondary_coverage_ratio": 0.9,
        "secondary_network_full_view_rate": 0.9,
        "readiness_timestamp_s": 4.9,
        "readiness_stale_after_s": 1.0,
        "takeover_ready_since_s": 4.7,
        "takeover_ready_observation_count": 3,
        "takeover_ready_sustained": True,
    }


def _communication(node_id: str, received_at: float = 4.9) -> CommunicationSummary:
    return CommunicationSummary(
        source_node_id=node_id,
        target_node_id="int-1",
        relay_node_id=None,
        link_type=LinkType.VIDEO_CUE,
        sent_timestamp=received_at - 0.1,
        received_timestamp=received_at,
        payload_kind=PayloadKind.VIDEO_METADATA,
        stale_after_s=1.0,
    )


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
            **_strict_readiness_fields(),
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

    result = coordinator.plan_degraded(
        tasks,
        resources,
        network,
        now_s=5.0,
        max_rounds=10,
        communication_summaries=[_communication("sec-1")],
    )

    assert coordinator.leader_id == "sec-1"
    assert result.final_views["coordination_mode"]["state"] == "secondary_node"
    assert result.final_views["coordination_mode"]["leader_role"] == "secondary_recon"
    assert all(assignment.owner != "sec-1" for assignment in result.assignments.values())


def test_center_failure_can_degrade_to_mobile_high_recon_secondary_node() -> None:
    node_ids = ["mhr-1", "int-1", "int-2"]
    resources = [
        ResourceSummary(
            "mhr-1",
            "mobile_high_recon",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            takeover_priority=15,
            lease_epoch=5,
            epoch=1,
            node_role=NodeRole.MOBILE_HIGH_RECON,
            coordinator_only=True,
            coverage_cell="cell-north",
            **_strict_readiness_fields(),
        ),
        ResourceSummary("int-1", "observe", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
        ResourceSummary("int-2", "observe", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
    ]
    tasks = [
        TrackSummary("task-1", "cell-north", 1.0, ConfidenceBand.HIGH, source_count=3, epoch=1),
    ]
    coordinator = FailoverCoordinator("int-1", ["mhr-1", "int-2"])
    coordinator.update_health(5.0)
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)

    result = coordinator.plan_degraded(
        tasks,
        resources,
        network,
        now_s=5.0,
        max_rounds=10,
        communication_summaries=[_communication("mhr-1")],
    )
    mode = result.final_views["coordination_mode"]

    assert coordinator.leader_id == "mhr-1"
    assert mode["state"] == "secondary_node"
    assert mode["leader_role"] == "mobile_high_recon"
    assert mode["leader_capability_class"] == "mobile_high_recon"
    assert mode["secondary_capability_class"] == "mobile_high_recon"
    assert all(assignment.owner != "mhr-1" for assignment in result.assignments.values())


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


def test_passive_failover_selects_secondary_covering_dynamic_task_cells() -> None:
    node_ids = ["sec-south", "sec-north", "int-1", "int-2"]
    resources = [
        ResourceSummary(
            "sec-south",
            "tethered_recon",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            takeover_priority=5,
            lease_epoch=9,
            epoch=1,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-south",
            **_strict_readiness_fields(),
        ),
        ResourceSummary(
            "sec-north",
            "tethered_recon",
            AvailabilityBand.HIGH,
            CommBand.GOOD,
            takeover_priority=20,
            lease_epoch=3,
            epoch=1,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-north",
            **_strict_readiness_fields(),
        ),
        ResourceSummary("int-1", "observe", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
        ResourceSummary("int-2", "observe", AvailabilityBand.HIGH, CommBand.GOOD, epoch=1),
    ]
    tasks = [
        TrackSummary("task-1", "cell-north", 1.0, ConfidenceBand.HIGH, source_count=3, epoch=1),
        TrackSummary("task-2", "cell-north", 1.2, ConfidenceBand.MEDIUM, source_count=2, epoch=1),
    ]
    coordinator = FailoverCoordinator("int-1", ["sec-south", "sec-north", "int-2"])
    coordinator.update_health(5.0)
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)

    result = coordinator.plan_degraded(
        tasks,
        resources,
        network,
        now_s=5.0,
        max_rounds=12,
        communication_summaries=[
            _communication("sec-south"),
            _communication("sec-north"),
        ],
    )

    assert coordinator.leader_id == "sec-north"
    assert result.final_views["coordination_mode"]["state"] == "secondary_node"
    assert result.final_views["coordination_mode"]["coverage_cell"] == "cell-north"
    assert all(assignment.owner != "sec-north" for assignment in result.assignments.values())


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("lease_epoch", 0),
        ("lease_expires_at_s", None),
        ("lease_expires_at_s", 5.0),
        ("heartbeat_timestamp_s", None),
        ("heartbeat_timestamp_s", 3.9),
        ("cue_freshness_s", None),
        ("cue_freshness_s", 1.1),
        ("gimbal_pointing_ok", None),
        ("gimbal_pointing_ok", False),
        ("secondary_coverage_ratio", None),
        ("secondary_coverage_ratio", 0.64),
        ("secondary_network_full_view_rate", None),
        ("secondary_network_full_view_rate", 0.79),
        ("takeover_ready_sustained", None),
        ("takeover_ready_sustained", False),
    ],
)
def test_secondary_election_fails_closed_on_incomplete_or_stale_readiness(
    field_name: str,
    field_value: object,
) -> None:
    secondary = ResourceSummary(
        "sec-1",
        "tethered_recon",
        AvailabilityBand.HIGH,
        CommBand.GOOD,
        takeover_priority=1,
        lease_epoch=3,
        node_role=NodeRole.SECONDARY_RECON,
        coordinator_only=True,
        coverage_cell="cell-north",
        **_strict_readiness_fields(),
    )
    secondary = replace(secondary, **{field_name: field_value})
    peer = ResourceSummary(
        "int-1",
        "observe",
        AvailabilityBand.HIGH,
        CommBand.GOOD,
        takeover_priority=50,
        node_role=NodeRole.CLUSTER_REPRESENTATIVE,
    )
    task = TrackSummary(
        "task-1", "cell-north", 1.0, ConfidenceBand.HIGH, source_count=2
    )

    leader = FailoverCoordinator("int-1", ["sec-1"]).elect_leader(
        [secondary, peer],
        tasks=[task],
        current_time_s=5.0,
        communication_summaries=[_communication("sec-1")],
    )

    assert leader == "int-1"


def test_secondary_election_requires_current_time_and_communication_evidence() -> None:
    secondary = ResourceSummary(
        "sec-1",
        "tethered_recon",
        AvailabilityBand.HIGH,
        CommBand.GOOD,
        takeover_priority=1,
        lease_epoch=3,
        node_role=NodeRole.SECONDARY_RECON,
        coordinator_only=True,
        coverage_cell="cell-north",
        **_strict_readiness_fields(),
    )
    peer = ResourceSummary(
        "int-1",
        "observe",
        AvailabilityBand.HIGH,
        CommBand.GOOD,
        node_role=NodeRole.CLUSTER_REPRESENTATIVE,
    )
    task = TrackSummary(
        "task-1", "cell-north", 1.0, ConfidenceBand.HIGH, source_count=2
    )
    coordinator = FailoverCoordinator("int-1", ["sec-1"])

    missing_time = coordinator.elect_leader(
        [secondary, peer],
        tasks=[task],
        communication_summaries=[_communication("sec-1")],
    )
    missing_communication = coordinator.elect_leader(
        [secondary, peer],
        tasks=[task],
        current_time_s=5.0,
        communication_summaries=[],
    )

    assert missing_time == "int-1"
    assert missing_communication == "int-1"


def test_distributed_peer_election_does_not_apply_secondary_visual_readiness_gate() -> None:
    peer = ResourceSummary(
        "int-1",
        "observe",
        AvailabilityBand.HIGH,
        CommBand.GOOD,
        node_role=NodeRole.CLUSTER_REPRESENTATIVE,
    )

    leader = FailoverCoordinator("int-1", []).elect_leader(
        [peer],
        current_time_s=5.0,
        communication_summaries=[],
    )

    assert leader == "int-1"


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
