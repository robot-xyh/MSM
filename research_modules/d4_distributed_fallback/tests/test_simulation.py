from __future__ import annotations

from d4_distributed_fallback.simulation import run_failover_simulation


def test_failover_simulation_reports_required_metrics_with_packet_loss() -> None:
    metrics = run_failover_simulation(node_count=5, task_count=4, packet_loss=0.05, seed=11)

    assert metrics["node_count"] == 5
    assert metrics["center_failure_at_s"] == 30.0
    assert metrics["takeover_time_s"] is not None
    assert metrics["consensus_rounds"] >= 1
    assert 0.0 <= metrics["assignment_completion_rate"] <= 1.0
    assert metrics["messages_sent"] > 0
    assert metrics["estimated_bytes"] > 0
