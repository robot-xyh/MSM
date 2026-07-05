from __future__ import annotations

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
