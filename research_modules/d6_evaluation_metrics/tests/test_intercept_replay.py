from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import load_d7_intercept_outputs


def test_d7_intercept_summary_derives_intercept_metrics(tmp_path: Path) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "control_api_used": True,
                "success_count": 2,
                "pair_count": 3,
                "record_count": 12,
                "parameters": {"intercept_radius_m": 0.75},
                "pairs": [
                    {
                        "resource_id": "INT-01",
                        "vehicle_name": "Interceptor1",
                        "target_id": "TGT-001",
                        "status": "collision_intercept",
                        "min_range_m": 0.42,
                        "time_to_intercept_s": 2.0,
                        "terminal_locked": True,
                    },
                    {
                        "resource_id": "INT-02",
                        "vehicle_name": "Interceptor2",
                        "target_id": "TGT-002",
                        "status": "range_intercept",
                        "min_range_m": 0.7,
                        "time_to_intercept_s": 3.0,
                        "terminal_locked": True,
                    },
                    {
                        "resource_id": "INT-03",
                        "vehicle_name": "Interceptor3",
                        "target_id": "TGT-003",
                        "status": "aborted",
                        "abort_reason": "terminal_detection_timeout",
                        "min_range_m": 4.5,
                        "time_to_intercept_s": None,
                    },
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    collector = load_d7_intercept_outputs(intercept_summary_path=summary_path)
    metrics = collector.compute_episode("intercept_summary_fixture")

    assert metrics.intercept_success_count == 2
    assert metrics.collision_intercept_count == 1
    assert metrics.range_intercept_count == 1
    assert metrics.time_to_intercept_s == pytest.approx(2.5)
    assert metrics.min_range_m == pytest.approx(0.42)
    assert metrics.gate_reject_count == 0
    assert metrics.metadata["intercept_pair_event_count"] == 3
    assert metrics.metadata["intercept_status_counts"] == {
        "aborted": 1,
        "collision_intercept": 1,
        "range_intercept": 1,
    }


def test_d7_control_commands_derives_gate_and_intercept_metrics(tmp_path: Path) -> None:
    commands_path = tmp_path / "control_commands.csv"
    _write_csv(
        commands_path,
        [
            {
                "timestamp_s": "0.0",
                "resource_id": "INT-01",
                "vehicle_name": "Interceptor1",
                "target_id": "TGT-001",
                "mode": "radar_midcourse",
                "range_m": "10.0",
                "terminal_handover_pending": "True",
                "guidance_law": "png_vm",
                "camera_quality_gate_passed": "True",
                "los_quality_gate_passed": "True",
                "maneuver_margin_gate_passed": "False",
                "terminal_switch_allowed": "False",
                "terminal_switch_reject_reason": "maneuver_margin",
                "collision_seen": "False",
                "status": "active",
            },
            {
                "timestamp_s": "1.0",
                "resource_id": "INT-01",
                "vehicle_name": "Interceptor1",
                "target_id": "TGT-001",
                "mode": "vision_terminal",
                "range_m": "0.6",
                "terminal_handover_pending": "False",
                "guidance_law": "png_vm",
                "camera_quality_gate_passed": "True",
                "los_quality_gate_passed": "True",
                "maneuver_margin_gate_passed": "True",
                "terminal_switch_allowed": "True",
                "terminal_switch_reject_reason": "",
                "collision_seen": "False",
                "status": "range_intercept",
            },
            {
                "timestamp_s": "0.5",
                "resource_id": "INT-02",
                "vehicle_name": "Interceptor2",
                "target_id": "TGT-002",
                "mode": "radar_midcourse",
                "range_m": "1.2",
                "terminal_handover_pending": "",
                "guidance_law": "radar_pn",
                "camera_quality_gate_passed": "",
                "los_quality_gate_passed": "",
                "maneuver_margin_gate_passed": "",
                "terminal_switch_allowed": "",
                "terminal_switch_reject_reason": "",
                "collision_seen": "True",
                "status": "active",
            },
        ],
    )

    collector = load_d7_intercept_outputs(control_commands_path=commands_path)
    terminal_switch_allowed_values = [
        record.metadata["terminal_switch_allowed"]
        for record in collector.event_records
        if "terminal_switch_allowed" in record.metadata
    ]
    assert terminal_switch_allowed_values == [False, True]

    metrics = collector.compute_episode("control_commands_fixture")

    assert metrics.intercept_success_count == 2
    assert metrics.collision_intercept_count == 1
    assert metrics.range_intercept_count == 1
    assert metrics.time_to_intercept_s == pytest.approx(0.75)
    assert metrics.min_range_m == pytest.approx(0.6)
    assert metrics.camera_quality_gate_pass_rate == pytest.approx(1.0)
    assert metrics.los_quality_gate_pass_rate == pytest.approx(1.0)
    assert metrics.maneuver_margin_gate_pass_rate == pytest.approx(0.5)
    assert metrics.terminal_switch_allowed_rate == pytest.approx(0.5)
    assert metrics.terminal_switch_reject_count == 1
    assert metrics.gate_reject_count == 1
    assert metrics.metadata["guidance_law_counts"] == {"png_vm": 2, "radar_pn": 1}
    assert metrics.metadata["terminal_switch_reject_reasons"] == {"maneuver_margin": 1}


def test_d7_control_commands_accepts_legacy_columns(tmp_path: Path) -> None:
    commands_path = tmp_path / "legacy_control_commands.csv"
    _write_csv(
        commands_path,
        [
            {
                "timestamp_s": "0.0",
                "resource_id": "INT-01",
                "target_id": "TGT-001",
                "range_m": "5.0",
                "collision_seen": "False",
                "status": "active",
                "abort_reason": "",
            },
            {
                "timestamp_s": "0.2",
                "resource_id": "INT-01",
                "target_id": "TGT-001",
                "range_m": "0.72",
                "collision_seen": "False",
                "status": "range_intercept",
                "abort_reason": "",
            },
        ],
    )

    collector = load_d7_intercept_outputs(control_commands_path=commands_path)
    metrics = collector.compute_episode("legacy_commands_fixture")

    assert metrics.intercept_success_count == 1
    assert metrics.collision_intercept_count == 0
    assert metrics.range_intercept_count == 1
    assert metrics.time_to_intercept_s == pytest.approx(0.2)
    assert metrics.min_range_m == pytest.approx(0.72)
    assert metrics.gate_reject_count == 0
    assert metrics.camera_quality_gate_pass_rate == 0.0
    assert metrics.terminal_switch_allowed_rate == 0.0


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
