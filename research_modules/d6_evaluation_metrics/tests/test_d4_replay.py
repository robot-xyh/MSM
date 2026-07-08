from __future__ import annotations

import csv
from pathlib import Path

import pytest

from d6_evaluation_metrics import EventRecord, MetricsCollector, load_d4_active_degradation_decisions


def test_d4_active_degradation_csv_derives_aggregate_metrics(tmp_path: Path) -> None:
    decisions_path = tmp_path / "active_degradation_decisions.csv"
    _write_csv(
        decisions_path,
        [
            {
                "timestamp": "3.0",
                "resource_id": "INT-01",
                "global_track_id": "T001",
                "mode": "active_degradation",
                "action": "request_secondary_assist",
                "reason": "terminal_inconsistent_single_window",
                "review_label": "necessary",
                "trigger_timestamp_s": "2.5",
                "decision_timestamp_s": "3.0",
                "selected_coordinator": "SEC-NORTH",
                "coverage_cell": "north-east",
                "pre_window_start_s": "1.5",
                "post_window_end_s": "4.5",
                "target_node_id": "SEC-NORTH",
                "terminal_consistent": "False",
                "risk_factors": "d2_association_ambiguity_high;d5_terminal_confidence_low",
            },
            {
                "timestamp": "3.5",
                "resource_id": "INT-02",
                "global_track_id": "T002",
                "mode": "active_degradation",
                "action": "request_secondary_assist",
                "reason": "terminal_inconsistent_single_window",
                "review_label": "false_positive",
                "target_node_id": "SEC-NORTH",
                "terminal_consistent": "False",
                "risk_factors": "d3_assignment_cost_margin_low",
            },
        ],
    )

    collector = load_d4_active_degradation_decisions(decisions_path)
    metrics = collector.compute_episode("d4_fixture")

    assert metrics.active_degradation_count == 2
    assert metrics.active_degradation_precision == pytest.approx(0.5)
    assert metrics.unnecessary_active_degradation_count == 1
    assert metrics.secondary_node_takeover_count == 2
    assert metrics.passive_failover_count == 0
    assert metrics.distributed_fallback_count == 0
    assert metrics.metadata["trigger_reason_distribution"] == {
        "terminal_inconsistent_single_window": 2
    }
    assert metrics.metadata["active_degradation_reviewed_count"] == 2
    assert collector.event_records[0].metadata["trigger_timestamp_s"] == pytest.approx(2.5)
    assert collector.event_records[0].metadata["decision_timestamp_s"] == pytest.approx(3.0)
    assert collector.event_records[0].metadata["selected_coordinator"] == "SEC-NORTH"
    assert collector.event_records[0].metadata["coverage_cell"] == "north-east"


def test_d4_failover_active_window_delta_from_events() -> None:
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(
                timestamp=1.0,
                event_type="d4_active_degradation_decision",
                metadata={"trigger_reason": "packet_loss", "mode": "active_degradation"},
            ),
            EventRecord(
                timestamp=3.5,
                event_type="passive_failover",
                metadata={"trigger_reason": "packet_loss"},
            ),
            EventRecord(
                timestamp=5.0,
                event_type="distributed_fallback",
                metadata={
                    "trigger_reason": "node_partition",
                    "failover_active_window_delta_s": 1.25,
                },
            ),
        ]
    )

    metrics = collector.compute_episode("d4_delta_fixture")

    assert metrics.active_degradation_count == 1
    assert metrics.passive_failover_count == 1
    assert metrics.distributed_fallback_count == 1
    assert metrics.failover_active_window_delta_s == pytest.approx((2.5 + 1.25) / 2.0)
    assert metrics.metadata["trigger_reason_distribution"] == {
        "node_partition": 1,
        "packet_loss": 2,
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
