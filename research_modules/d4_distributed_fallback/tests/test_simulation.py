from __future__ import annotations

from d4_distributed_fallback.models import (
    AvailabilityBand,
    CommBand,
    CommunicationSummary,
    ConfidenceBand,
    NodeRole,
    LinkType,
    PayloadKind,
    ResourceSummary,
    TrackSummary,
)
from d4_distributed_fallback.simulation import default_resources, default_tasks, run_failover_simulation


def test_failover_simulation_reports_required_metrics_with_packet_loss() -> None:
    metrics = run_failover_simulation(node_count=5, task_count=4, packet_loss=0.05, seed=11)

    assert metrics["node_count"] == 5
    assert metrics["center_failure_at_s"] == 30.0
    assert metrics["takeover_time_s"] is not None
    assert metrics["consensus_rounds"] >= 1
    assert 0.0 <= metrics["assignment_completion_rate"] <= 1.0
    assert metrics["messages_sent"] > 0
    assert metrics["estimated_bytes"] > 0


def test_failover_simulation_uses_dynamic_counts_without_2v2_5v5_limit() -> None:
    metrics = run_failover_simulation(node_count=7, task_count=9, packet_loss=0.0, seed=13)

    assert metrics["node_count"] == 7
    assert metrics["task_count"] == 9
    assert metrics["takeover_time_s"] is not None
    assert metrics["consensus_rounds"] >= 1
    assert 0.0 <= metrics["assignment_completion_rate"] <= 1.0


def test_failover_simulation_uses_summary_list_lengths_when_provided() -> None:
    metrics = run_failover_simulation(
        resources=default_resources(6),
        tasks=default_tasks(6),
        packet_loss=0.0,
        seed=17,
    )

    assert metrics["node_count"] == 6
    assert metrics["task_count"] == 6
    assert metrics["takeover_time_s"] is not None


def test_failover_simulation_reports_secondary_coordination_metadata() -> None:
    resources = [
        ResourceSummary(
            node_id="sec-north-1",
            capability_class="tethered_recon",
            availability_band=AvailabilityBand.HIGH,
            comm_band=CommBand.GOOD,
            takeover_priority=10,
            lease_epoch=3,
            epoch=1,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-north",
            lease_expires_at_s=50.0,
            heartbeat_timestamp_s=33.9,
            heartbeat_stale_after_s=1.0,
            cue_freshness_s=0.1,
            gimbal_pointing_ok=True,
            secondary_coverage_ratio=0.9,
            secondary_network_full_view_rate=0.9,
            readiness_timestamp_s=33.9,
            readiness_stale_after_s=1.0,
            takeover_ready_since_s=33.6,
            takeover_ready_observation_count=3,
            takeover_ready_sustained=True,
        ),
        ResourceSummary(
            node_id="int-1",
            capability_class="observe",
            availability_band=AvailabilityBand.HIGH,
            comm_band=CommBand.GOOD,
            epoch=1,
        ),
        ResourceSummary(
            node_id="int-2",
            capability_class="observe",
            availability_band=AvailabilityBand.HIGH,
            comm_band=CommBand.GOOD,
            epoch=1,
        ),
    ]
    tasks = [
        TrackSummary(
            track_id="track-north-1",
            coarse_cell="cell-north",
            age_s=1.0,
            confidence_band=ConfidenceBand.HIGH,
            source_count=2,
            epoch=1,
        )
    ]

    metrics = run_failover_simulation(
        resources=resources,
        tasks=tasks,
        packet_loss=0.0,
        seed=19,
        communication_summaries=[
            CommunicationSummary(
                source_node_id="sec-north-1",
                target_node_id="int-1",
                relay_node_id=None,
                link_type=LinkType.VIDEO_CUE,
                sent_timestamp=33.8,
                received_timestamp=33.9,
                payload_kind=PayloadKind.VIDEO_METADATA,
                stale_after_s=1.0,
            )
        ],
    )
    report = metrics["cbba_report_metadata"]

    assert metrics["coordination_mode"] == "secondary_node"
    assert metrics["selected_coordinator"] == "secondary_node"
    assert metrics["d4_action"] == "degrade_to_secondary"
    assert metrics["leader_id"] == "sec-north-1"
    assert metrics["leader_role"] == "secondary_recon"
    assert metrics["coverage_cell"] == "cell-north"
    assert report["coordination_mode"] == metrics["coordination_mode"]
    assert report["consensus_rounds"] == metrics["consensus_rounds"]
    assert report["cost_gap_available"] is False
