from __future__ import annotations

import csv
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    ArrivalRecord,
    AssignmentRecord,
    CoalitionRecord,
    EventRecord,
    MetricsCollector,
    ReportGenerator,
    TargetDemandRecord,
    TerminalRecord,
    dump_episode_log_jsonl,
    load_episode_log_jsonl,
)
from d6_evaluation_metrics.simulation import write_episode_log_jsonl


def _cooperative_collector(member_count: int) -> MetricsCollector:
    collector = MetricsCollector()
    collector.add_target_demand(
        TargetDemandRecord(
            timestamp=0.0,
            global_track_id="G1",
            required_resource_count=3,
            coordination_mode="simultaneous",
            demand_assigned=min(member_count, 3),
            demand_shortfall=max(3 - member_count, 0),
            demand_complete=member_count >= 3,
            coalition_id="C1",
            coalition_version=2,
            coalition_state="committed",
            arrival_window_start=9.0,
            arrival_window_end=11.0,
            minimum_member_separation=5.0,
        )
    )
    collector.add_coalition(
        CoalitionRecord(
            timestamp=1.0,
            global_track_id="G1",
            coalition_id="C1",
            coalition_version=2,
            coalition_state="committed",
            coordination_mode="simultaneous",
            member_ids=tuple(f"R{index}" for index in range(1, member_count + 1)),
            member_roles={f"R{index}": "primary" for index in range(1, member_count + 1)},
            required_resource_count=3,
            demand_assigned=min(member_count, 3),
            demand_shortfall=max(3 - member_count, 0),
            demand_complete=member_count >= 3,
        )
    )
    for index in range(1, member_count + 1):
        collector.add_assignment(
            AssignmentRecord(
                timestamp=10.0,
                plan_id="P1",
                version=4,
                resource_id=f"R{index}",
                global_track_id="G1",
                authorization_state="authorized",
                coordination_mode="simultaneous",
                coalition_id="C1",
                coalition_version=2,
                coalition_state="committed",
                member_role="primary",
                wave_id="W1",
                required_resource_count=3,
            )
        )
        collector.add_terminal(
            TerminalRecord(
                timestamp=10.0,
                resource_id=f"R{index}",
                assigned_global_track_id="G1",
                local_track_id=f"L{index}",
                decision_state="locked",
                assignment_version=4,
                authorization_state="authorized",
                coordination_mode="simultaneous",
                coalition_id="C1",
                coalition_version=2,
                coalition_state="committed",
                member_role="primary",
                wave_id="W1",
                required_resource_count=3,
            )
        )
    return collector


def test_three_authorized_cooperative_locks_are_legal_and_fourth_is_illegal() -> None:
    legal = _cooperative_collector(3).compute_episode("legal")
    illegal = _cooperative_collector(4).compute_episode("illegal")

    assert legal.duplicate_assignment_count == 0
    assert legal.duplicate_terminal_lock_count == 1
    assert legal.erroneous_duplicate_lock_count == 0
    assert legal.planned_cooperative_lock_count == 3
    assert legal.authorized_cooperative_lock_count == 3

    assert illegal.duplicate_assignment_count == 1
    assert illegal.duplicate_terminal_lock_count == 1
    assert illegal.erroneous_duplicate_lock_count == 1
    assert illegal.planned_cooperative_lock_count == 3
    assert illegal.authorized_cooperative_lock_count == 3


def test_same_resource_lock_continuity_and_version_conflict_are_distinct() -> None:
    collector = _cooperative_collector(2)
    collector.add_terminal(
        TerminalRecord(
            timestamp=11.0,
            resource_id="R1",
            assigned_global_track_id="G1",
            local_track_id="L1",
            decision_state="locked",
            assignment_version=4,
            authorization_state="authorized",
            coalition_id="C1",
            coalition_version=2,
            member_role="primary",
            required_resource_count=3,
        )
    )
    continuity = collector.compute_episode("continuity")

    assert continuity.same_resource_lock_continuity_count == 1
    assert continuity.duplicate_terminal_lock_count == 1
    assert continuity.erroneous_duplicate_lock_count == 0

    conflict = _cooperative_collector(2)
    conflict.add_terminal(
        TerminalRecord(
            timestamp=10.0,
            resource_id="R3",
            assigned_global_track_id="G1",
            local_track_id="L3",
            decision_state="locked",
            assignment_version=3,
            authorization_state="authorized",
            coalition_id="C1",
            coalition_version=1,
            member_role="primary",
            required_resource_count=3,
        )
    )
    conflict_metrics = conflict.compute_episode("version-conflict")

    assert conflict_metrics.erroneous_duplicate_lock_count == 1
    assert conflict_metrics.authorized_cooperative_lock_count == 2

    single = MetricsCollector()
    single.add_assignment(
        AssignmentRecord(
            10.0,
            "P1",
            4,
            "R1",
            "G1",
            coalition_id="C1",
            coalition_version=2,
            required_resource_count=2,
        )
    )
    single.add_terminal(
        TerminalRecord(
            10.0,
            "R1",
            "G1",
            "L1",
            decision_state="locked",
            assignment_version=3,
            coalition_id="C1",
            coalition_version=1,
            required_resource_count=2,
        )
    )
    single_metrics = single.compute_episode("single-version-conflict")
    assert single_metrics.duplicate_terminal_lock_count == 0
    assert single_metrics.erroneous_duplicate_lock_count == 0


def test_center_replan_lifecycle_metrics_use_normative_event_names(tmp_path: Path) -> None:
    collector = MetricsCollector()
    collector.extend_events(
        [
            EventRecord(
                1.0,
                "center_replan_request_created",
                metadata={
                    "request_id": "RQ1",
                    "target_id": "G1",
                    "coalition_id": "C1",
                    "coalition_version": 2,
                    "risk_signature": "risk-a",
                    "requested_at": 1.0,
                },
            ),
            EventRecord(
                1.2,
                "center_replan_request_deduplicated",
                metadata={"request_id": "RQ1", "target_id": "G1"},
            ),
            EventRecord(
                3.0,
                "center_replan_applied",
                metadata={
                    "request_id": "RQ1",
                    "target_id": "G1",
                    "requested_at": 1.0,
                    "resolved_at": 3.0,
                    "pending_dwell_s": 2.0,
                    "resolved_plan_id": "P2",
                    "resolved_plan_version": 5,
                },
            ),
            EventRecord(
                4.0,
                "center_replan_request_created",
                metadata={"request_id": "RQ2", "target_id": "G2"},
            ),
            EventRecord(
                5.0,
                "center_replan_ack_no_change",
                metadata={
                    "request_id": "RQ2",
                    "target_id": "G2",
                    "resolved_at": 5.0,
                    "pending_dwell_s": 1.0,
                },
            ),
            EventRecord(
                6.0,
                "center_replan_request_created",
                metadata={"request_id": "RQ3", "target_id": "G3"},
            ),
            EventRecord(
                9.0,
                "center_replan_expired",
                metadata={
                    "request_id": "RQ3",
                    "target_id": "G3",
                    "resolved_at": 9.0,
                    "pending_dwell_s": 3.0,
                },
            ),
        ]
    )

    metrics = collector.compute_episode("replan")

    assert metrics.replan_request_count == 3
    assert metrics.replan_request_deduplicated_count == 1
    assert metrics.replan_no_change_ack_count == 1
    assert metrics.replan_applied_count == 1
    assert metrics.replan_expired_count == 1
    assert metrics.replan_pending_dwell_s == pytest.approx(6.0)
    assert metrics.replan_convergence_time_s == pytest.approx(1.5)
    assert metrics.m_to_n_metric_availability["replan_pending_dwell_s"] == {
        "status": "available",
        "reason": "resolved/expired replans provided pending dwell evidence",
        "numerator": 6.0,
        "denominator": 3,
    }
    assert metrics.metadata["replan_event_audit"][2]["resolved_plan_id"] == "P2"
    assert metrics.to_dict()["replan_applied_count"] == 1

    episode_csv = ReportGenerator().write_episode_csv(
        [metrics], tmp_path / "replan_episode.csv"
    )
    row = next(csv.DictReader(episode_csv.open(encoding="utf-8")))
    assert row["replan_request_count"] == "3"
    assert row["replan_pending_dwell_s"] == "6.0"
    assert row["replan_convergence_time_s"] == "1.5"


def test_replan_metrics_are_unavailable_without_lifecycle_evidence() -> None:
    metrics = MetricsCollector().compute_episode("no-replan")

    assert metrics.replan_request_count is None
    assert metrics.replan_pending_dwell_s is None
    assert metrics.replan_convergence_time_s is None
    assert metrics.m_to_n_metric_availability["replan_request_count"]["status"] == "unavailable"


def test_target_demand_shortfall_and_hybrid_reserve_wait_are_not_complete() -> None:
    collector = MetricsCollector()
    collector.add_target_demand(
        TargetDemandRecord(
            timestamp=0.0,
            global_track_id="G1",
            required_resource_count=3,
            coordination_mode="hybrid_primary_reserve",
            demand_assigned=2,
            demand_shortfall=1,
            demand_complete=False,
        )
    )
    for resource_id, role in (("R1", "primary"), ("R2", "primary"), ("R3", "reserve")):
        collector.add_assignment(
            AssignmentRecord(
                timestamp=0.0,
                plan_id="P1",
                version=1,
                resource_id=resource_id,
                global_track_id="G1",
                coordination_mode="hybrid_primary_reserve",
                coalition_id="C1",
                coalition_version=1,
                coalition_state="committed",
                member_role=role,
                required_resource_count=3,
            )
        )

    metrics = collector.compute_episode("hybrid")

    assert metrics.target_demand_satisfaction_rate_micro == pytest.approx(2 / 3)
    assert metrics.target_demand_satisfaction_rate_macro == 0.0
    assert metrics.unmet_slot_count == 1
    assert metrics.reserve_activation_count == 0
    assert metrics.reserve_activation_rate == 0.0


def test_simultaneous_and_sequential_arrival_contracts() -> None:
    simultaneous = MetricsCollector()
    simultaneous.add_target_demand(
        TargetDemandRecord(0.0, "G1", 2, "simultaneous", demand_assigned=2, demand_shortfall=0, demand_complete=True)
    )
    for resource_id, arrival_time in (("R1", 10.0), ("R2", 10.2)):
        simultaneous.add_arrival(
            ArrivalRecord(
                timestamp=arrival_time,
                global_track_id="G1",
                resource_id=resource_id,
                coalition_id="C1",
                coalition_version=1,
                coalition_state="committed",
                member_role="primary",
                coordination_mode="simultaneous",
                wave_id="W1",
                required_resource_count=2,
                arrival_timestamp=arrival_time,
                arrival_window_start=9.5,
                arrival_window_end=10.5,
                minimum_member_separation=6.0,
            )
        )
    simultaneous_metrics = simultaneous.compute_episode("simultaneous")
    assert simultaneous_metrics.simultaneous_arrival_dispersion_s == pytest.approx(0.2)
    assert simultaneous_metrics.common_window_success_rate == 1.0
    assert simultaneous_metrics.wave_interval_s is None
    assert simultaneous_metrics.m_to_n_metric_availability["wave_interval_s"]["status"] == "not_applicable"

    sequential = MetricsCollector()
    sequential.add_target_demand(
        TargetDemandRecord(0.0, "G1", 2, "sequential", demand_assigned=2, demand_shortfall=0, demand_complete=True)
    )
    sequential.extend_arrivals(
        [
            ArrivalRecord(10.0, "G1", "R1", "C1", 1, "committed", "primary", "sequential", wave_id="W1", wave_start_timestamp=10.0, wave_complete_timestamp=11.0),
            ArrivalRecord(13.0, "G1", "R2", "C1", 1, "committed", "primary", "sequential", wave_id="W2", wave_start_timestamp=13.0, wave_complete_timestamp=14.0),
        ]
    )
    sequential_metrics = sequential.compute_episode("sequential")
    assert sequential_metrics.wave_interval_s == 2.0
    assert sequential_metrics.wave_order_violation_count == 0
    assert sequential_metrics.common_window_success_rate is None
    assert sequential_metrics.m_to_n_metric_availability["common_window_success_rate"]["status"] == "not_applicable"


def test_missing_evidence_and_legacy_k1_remain_distinct() -> None:
    empty = MetricsCollector().compute_episode("empty")
    assert empty.target_demand_satisfaction_rate_micro is None
    assert empty.m_to_n_metric_availability["target_demand_satisfaction_rate_micro"]["status"] == "unavailable"
    assert empty.erroneous_duplicate_lock_count is None
    assert empty.m_to_n_metric_availability["erroneous_duplicate_lock_count"]["status"] == "unavailable"
    assert empty.common_window_success_rate is None
    assert empty.m_to_n_metric_availability["common_window_success_rate"]["status"] == "not_applicable"

    legacy = MetricsCollector()
    for resource_id in ("R1", "R2"):
        legacy.add_assignment(AssignmentRecord(0.0, "legacy", 1, resource_id, "G1"))
        legacy.add_terminal(TerminalRecord(1.0, resource_id, "G1", f"L-{resource_id}", decision_state="locked"))
    legacy_metrics = legacy.compute_episode("legacy")
    assert legacy_metrics.duplicate_assignment_count == 1
    assert legacy_metrics.duplicate_terminal_lock_count == 1
    assert legacy_metrics.target_demand_satisfaction_rate_micro is None


def test_m_to_n_jsonl_csv_and_batch_summary_wiring(tmp_path: Path) -> None:
    path = dump_episode_log_jsonl(
        [
            {"record_type": "truth_summary", "payload": {"resource_count": 3, "target_count": 1}},
            {"record_type": "target_demand", "payload": {"timestamp": 0.0, "global_track_id": "G1", "required_resource_count": 3, "coordination_mode": "simultaneous", "demand_assigned": 2, "demand_shortfall": 1, "demand_complete": False}},
            {"record_type": "coalition", "payload": {"timestamp": 1.0, "global_track_id": "G1", "coalition_id": "C1", "coalition_version": 1, "coalition_state": "committed", "coordination_mode": "simultaneous", "member_ids": ["R1", "R2"]}},
            {"record_type": "arrival", "payload": {"timestamp": 2.0, "global_track_id": "G1", "resource_id": "R1", "coalition_id": "C1", "coalition_version": 1, "coalition_state": "committed", "member_role": "primary", "coordination_mode": "simultaneous", "arrival_timestamp": 2.0}},
        ],
        tmp_path / "m_to_n.jsonl",
    )
    collector, truth = load_episode_log_jsonl(path)
    metrics = collector.compute_episode("jsonl", truth_summary=truth)
    assert metrics.resource_count == 3
    assert metrics.target_count == 1
    assert metrics.metadata["target_demand_record_count"] == 1

    generator = ReportGenerator()
    episode_csv = generator.write_episode_csv([metrics], tmp_path / "episode.csv")
    summary_csv = generator.write_summary_csv([metrics], tmp_path / "summary.csv")
    report = generator.write_markdown_report([metrics], tmp_path / "report.md")
    episode_row = next(csv.DictReader(episode_csv.open(encoding="utf-8")))
    summary_rows = list(csv.DictReader(summary_csv.open(encoding="utf-8")))
    assert episode_row["unmet_slot_count"] == "1"
    assert "detection_probability" in episode_row["metric_availability"]
    assert "target_demand_satisfaction_rate_micro" in episode_row["m_to_n_metric_availability"]
    reserve_rows = [row for row in summary_rows if row["metric"] == "reserve_activation_rate" and row["metric_scope"] == "all"]
    assert reserve_rows[0]["not_applicable_count"] == "1"
    detection_rows = [
        row
        for row in summary_rows
        if row["metric"] == "detection_probability"
        and row["metric_scope"] == "all"
    ]
    assert detection_rows[0]["count"] == "0"
    assert detection_rows[0]["unavailable_count"] == "1"
    report_text = report.read_text(encoding="utf-8")
    assert "not_applicable" in report_text
    assert "target_demand_satisfaction_rate_micro" in report_text
    assert "replan_request_count" in report_text


def test_collector_jsonl_writer_round_trips_m_to_n_records(tmp_path: Path) -> None:
    collector = _cooperative_collector(3)
    collector.add_arrival(
        ArrivalRecord(
            timestamp=10.0,
            global_track_id="G1",
            resource_id="R1",
            coalition_id="C1",
            coalition_version=2,
            coalition_state="committed",
            member_role="primary",
            coordination_mode="simultaneous",
            arrival_timestamp=10.0,
        )
    )
    path = write_episode_log_jsonl(
        collector,
        {"resource_count": 3, "target_count": 1},
        tmp_path / "collector.jsonl",
    )

    loaded, truth = load_episode_log_jsonl(path)

    assert len(loaded.target_demand_records) == 1
    assert len(loaded.coalition_records) == 1
    assert len(loaded.arrival_records) == 1
    assert loaded.compute_episode("round_trip", truth_summary=truth).unmet_slot_count == 0
