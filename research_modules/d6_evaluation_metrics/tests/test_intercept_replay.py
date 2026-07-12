from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import load_d7_guidance_timeseries, load_d7_intercept_outputs


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


def test_five_meter_ned_3d_range_intercept_is_pair_and_target_physical_success(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "control_api_used": True,
                "success_count": 1,
                "pair_count": 1,
                "parameters": {
                    "intercept_radius_m": 5.0,
                    "intercept_distance_frame": "NED",
                    "intercept_distance_dimension": "3d_euclidean",
                    "intercept_success_criteria_version": "airsim-range-intercept-v2",
                },
                "pairs": [
                    {
                        "resource_id": "INT-01",
                        "target_id": "TGT-001",
                        "assigned": True,
                        "activation_state": "active",
                        "status": "range_intercept",
                        "min_range_m": 4.9,
                        "time_to_intercept_s": 3.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    metrics = load_d7_intercept_outputs(
        intercept_summary_path=summary_path
    ).compute_episode("five_meter_success")

    assert metrics.pair_physical_success_count == 1
    assert metrics.pair_physical_success_rate == pytest.approx(1.0)
    assert metrics.target_intercept_success_count == 1
    assert metrics.target_intercept_success_rate == pytest.approx(1.0)
    assert metrics.physical_intercept_count == 1
    assert metrics.metadata["physical_success_criteria"] == {
        "intercept_radius_m": 5.0,
        "distance_frame": "NED",
        "distance_dimension": "3d_euclidean",
        "criteria_version": "airsim-range-intercept-v2",
    }
    assert metrics.metadata["physical_success_criteria_matches_5m_ned_3d"] is True


def test_one_primary_success_does_not_complete_required_coalition(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    _write_coalition_summary(
        summary_path,
        pair_statuses=("range_intercept", "timeout"),
        arrival_timestamps=(4.0, None),
    )

    metrics = load_d7_intercept_outputs(
        intercept_summary_path=summary_path
    ).compute_episode("partial_coalition")

    assert metrics.pair_physical_success_count == 1
    assert metrics.pair_physical_success_rate == pytest.approx(0.5)
    assert metrics.target_intercept_success_count == 1
    assert metrics.target_intercept_success_rate == pytest.approx(1.0)
    assert metrics.coalition_completion_count == 0
    assert metrics.coalition_completion_rate == pytest.approx(0.0)


def test_all_required_primaries_inside_arrival_window_complete_coalition(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    _write_coalition_summary(
        summary_path,
        pair_statuses=("collision_intercept", "range_intercept"),
        arrival_timestamps=(3.5, 4.5),
    )

    metrics = load_d7_intercept_outputs(
        intercept_summary_path=summary_path
    ).compute_episode("complete_coalition")

    assert metrics.pair_physical_success_count == 2
    assert metrics.target_intercept_success_count == 1
    assert metrics.coalition_completion_count == 1
    assert metrics.coalition_completion_rate == pytest.approx(1.0)
    assert metrics.metadata["completed_coalition_target_ids"] == ["TGT-001"]


def test_computer_vision_physical_success_remains_unavailable(tmp_path: Path) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "runtime_mode": "computer_vision_m_to_n",
                "physical_intercept_available": False,
                "physical_intercept_unavailable_reason": "read_only_camera_actors",
                "success_count": 0,
                "pair_count": 1,
                "pairs": [
                    {
                        "resource_id": "CAM-01",
                        "target_id": "TGT-001",
                        "status": "range_intercept",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    metrics = load_d7_intercept_outputs(
        intercept_summary_path=summary_path
    ).compute_episode("cv_unavailable")

    assert metrics.physical_intercept_count is None
    assert metrics.pair_physical_success_count is None
    assert metrics.target_intercept_success_count is None
    assert metrics.coalition_completion_count is None
    assert metrics.metadata["physical_intercept_evidence_available"] is False
    assert metrics.metadata["physical_intercept_unavailable_reason"] == (
        "ComputerVision episodes do not provide physical intercept evidence"
    )


def test_d7_intercept_outputs_aggregate_five_actor_pairs(tmp_path: Path) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    commands_path = tmp_path / "control_commands.csv"
    summary_path.write_text(
        json.dumps(
            {
                "control_api_used": True,
                "success_count": 4,
                "pair_count": 5,
                "record_count": 30,
                "pairs": [
                    {
                        "resource_id": "INT-01",
                        "target_id": "TGT-001",
                        "status": "collision_intercept",
                        "min_range_m": 0.3,
                        "time_to_intercept_s": 4.0,
                        "terminal_locked": True,
                    },
                    {
                        "resource_id": "INT-02",
                        "target_id": "TGT-002",
                        "status": "range_intercept",
                        "min_range_m": 0.8,
                        "time_to_intercept_s": 5.0,
                        "terminal_locked": True,
                    },
                    {
                        "resource_id": "INT-03",
                        "target_id": "TGT-003",
                        "status": "range_intercept",
                        "min_range_m": 0.6,
                        "time_to_intercept_s": 6.0,
                        "terminal_locked": False,
                    },
                    {
                        "resource_id": "INT-04",
                        "target_id": "TGT-004",
                        "status": "aborted",
                        "abort_reason": "terminal_detection_timeout",
                        "min_range_m": 4.0,
                        "terminal_locked": False,
                        "terminal_switch_reject_reason": "camera_quality",
                    },
                    {
                        "resource_id": "INT-05",
                        "target_id": "TGT-005",
                        "status": "collision_intercept",
                        "min_range_m": 0.5,
                        "time_to_intercept_s": 5.5,
                        "terminal_locked": True,
                    },
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _write_csv(
        commands_path,
        [
            {
                "timestamp_s": "0.0",
                "resource_id": "INT-01",
                "target_id": "TGT-001",
                "mode": "radar_midcourse",
                "range_m": "10.0",
                "terminal_locked": "False",
                "guidance_law": "radar_pn",
                "terminal_switch_allowed": "False",
                "terminal_switch_reject_reason": "",
                "status": "active",
            },
            {
                "timestamp_s": "3.5",
                "resource_id": "INT-01",
                "target_id": "TGT-001",
                "mode": "vision_terminal",
                "range_m": "0.3",
                "terminal_locked": "True",
                "guidance_law": "png_vm",
                "terminal_switch_allowed": "True",
                "terminal_switch_reject_reason": "",
                "status": "collision_intercept",
            },
            {
                "timestamp_s": "4.0",
                "resource_id": "INT-02",
                "target_id": "TGT-002",
                "mode": "vision_terminal",
                "range_m": "0.8",
                "terminal_locked": "True",
                "guidance_law": "png_vm",
                "terminal_switch_allowed": "True",
                "terminal_switch_reject_reason": "",
                "status": "range_intercept",
            },
            {
                "timestamp_s": "5.0",
                "resource_id": "INT-03",
                "target_id": "TGT-003",
                "mode": "radar_midcourse",
                "range_m": "0.6",
                "terminal_locked": "False",
                "guidance_law": "radar_pn",
                "terminal_switch_allowed": "",
                "terminal_switch_reject_reason": "",
                "status": "range_intercept",
            },
            {
                "timestamp_s": "2.0",
                "resource_id": "INT-04",
                "target_id": "TGT-004",
                "mode": "radar_midcourse",
                "range_m": "4.0",
                "terminal_locked": "False",
                "guidance_law": "radar_pn",
                "camera_quality_gate_passed": "False",
                "los_quality_gate_passed": "True",
                "maneuver_margin_gate_passed": "True",
                "terminal_switch_allowed": "False",
                "terminal_switch_reject_reason": "camera_quality",
                "status": "aborted",
            },
            {
                "timestamp_s": "4.5",
                "resource_id": "INT-05",
                "target_id": "TGT-005",
                "mode": "vision_terminal",
                "range_m": "0.5",
                "terminal_locked": "True",
                "guidance_law": "pure_pursuit",
                "terminal_switch_allowed": "True",
                "terminal_switch_reject_reason": "",
                "status": "collision_intercept",
            },
        ],
    )

    collector = load_d7_intercept_outputs(
        control_commands_path=commands_path,
        intercept_summary_path=summary_path,
    )
    metrics = collector.compute_episode("five_actor_pairs")

    assert metrics.intercept_success_count == 4
    assert metrics.collision_intercept_count == 2
    assert metrics.range_intercept_count == 2
    assert metrics.min_range_m == pytest.approx(0.3)
    assert metrics.time_to_intercept_s == pytest.approx(5.125)
    assert metrics.terminal_takeover_rate == pytest.approx(0.6)
    assert metrics.gate_reject_count == 2
    assert metrics.metadata["terminal_takeover_pair_count"] == 3
    assert metrics.metadata["terminal_takeover_pair_denominator"] == 5
    assert metrics.metadata["guidance_law_counts"] == {
        "png_vm": 2,
        "pure_pursuit": 1,
        "radar_pn": 3,
    }
    assert metrics.metadata["guidance_law_pair_counts"] == {
        "png_vm": 2,
        "pure_pursuit": 1,
        "radar_pn": 2,
    }
    assert metrics.metadata["terminal_switch_reject_reasons"] == {"camera_quality": 2}
    assert metrics.metadata["terminal_switch_reject_reason_pair_counts"] == {
        "camera_quality": 1
    }


def test_terminal_takeover_rate_is_zero_for_all_radar_pn_unlocked_pairs(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    commands_path = tmp_path / "control_commands.csv"
    _write_five_pair_summary(summary_path, locked_pair_ids=set())
    _write_csv(
        commands_path,
        [
            {
                "timestamp_s": str(index),
                "resource_id": f"INT-{index:02d}",
                "target_id": f"TGT-{index:03d}",
                "mode": "radar_midcourse",
                "guidance_law": "radar_pn",
                "terminal_locked": "False",
                "terminal_handover_pending": "True",
                "detection_seen": "True",
                "d5_decision_state": "terminal_locked",
                "terminal_switch_allowed": "False",
                "status": "active",
            }
            for index in range(1, 6)
        ],
    )

    collector = load_d7_intercept_outputs(
        control_commands_path=commands_path,
        intercept_summary_path=summary_path,
    )
    metrics = collector.compute_episode("all_radar_unlocked")

    assert metrics.terminal_takeover_rate == pytest.approx(0.0)
    assert metrics.metadata["terminal_takeover_pair_count"] == 0
    assert metrics.metadata["terminal_takeover_pair_denominator"] == 5


def test_terminal_takeover_rate_counts_one_png_locked_pair_out_of_five(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    commands_path = tmp_path / "control_commands.csv"
    _write_five_pair_summary(summary_path, locked_pair_ids={3})
    rows = [
        {
            "timestamp_s": str(index),
            "resource_id": f"INT-{index:02d}",
            "target_id": f"TGT-{index:03d}",
            "mode": "radar_midcourse",
            "guidance_law": "radar_pn",
            "terminal_locked": "False",
            "terminal_switch_allowed": "False",
            "status": "active",
        }
        for index in range(1, 6)
    ]
    rows.append(
        {
            "timestamp_s": "3.5",
            "resource_id": "INT-03",
            "target_id": "TGT-003",
            "mode": "vision_terminal",
            "guidance_law": "png_vm",
            "terminal_locked": "True",
            "terminal_switch_allowed": "True",
            "status": "range_intercept",
        }
    )
    _write_csv(commands_path, rows)

    collector = load_d7_intercept_outputs(
        control_commands_path=commands_path,
        intercept_summary_path=summary_path,
    )
    metrics = collector.compute_episode("one_png_locked")

    assert metrics.terminal_takeover_rate == pytest.approx(1 / 5)
    assert metrics.metadata["terminal_takeover_pair_count"] == 1
    assert metrics.metadata["terminal_takeover_pair_denominator"] == 5


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


def test_d7_guidance_timeseries_unifies_guidance_and_intercept_outputs(
    tmp_path: Path,
) -> None:
    guidance_records_path = tmp_path / "guidance_records.csv"
    guidance_summaries_path = tmp_path / "guidance_summaries.json"
    control_commands_path = tmp_path / "control_commands.csv"
    intercept_summary_path = tmp_path / "intercept_summary.json"

    _write_csv(
        guidance_records_path,
        [
            {
                "timestamp_s": "0.0",
                "resource_id": "INT-01",
                "target_id": "T001",
                "mode": "radar_midcourse",
                "mode_switch": "False",
                "d4_state": "normal",
                "d5_state": "terminal_pending",
                "plan_id": "plan-a",
                "plan_version": "1",
            },
            {
                "timestamp_s": "0.2",
                "resource_id": "INT-01",
                "target_id": "T001",
                "mode": "vision_terminal",
                "mode_switch": "True",
                "terminal_contract_reject_reason": "terminal_contract_not_satisfied",
                "d4_state": "active_degradation",
                "d5_state": "terminal_rejected",
                "plan_id": "plan-a",
                "plan_version": "2",
            },
        ],
    )
    guidance_summaries_path.write_text(
        json.dumps(
            [
                {
                    "episode_timestamp_s": 4.0,
                    "resource_id": "INT-02",
                    "target_id": "T002",
                    "mode_sequence": ["radar_midcourse", "vision_terminal"],
                    "plan_id": "d4_active_degradation_degrade_to_secondary",
                    "plan_version": 1,
                    "d4_state": "active_degradation",
                    "d5_state": "terminal_locked",
                    "terminal_mode_entered": True,
                    "min_range_m": 1.2,
                }
            ],
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _write_csv(
        control_commands_path,
        [
            {
                "timestamp_s": "0.3",
                "resource_id": "INT-01",
                "target_id": "T001",
                "mode": "vision_terminal",
                "terminal_switch_allowed": "False",
                "terminal_switch_reject_reason": "camera_quality",
                "d4_state": "active_degradation",
                "d5_state": "terminal_rejected",
                "plan_id": "plan-a",
                "plan_version": "2",
                "camera_quality_gate_passed": "False",
                "los_quality_gate_passed": "True",
                "maneuver_margin_gate_passed": "True",
            }
        ],
    )
    intercept_summary_path.write_text(
        json.dumps(
            {
                "success_count": 1,
                "pairs": [
                    {
                        "resource_id": "INT-01",
                        "target_id": "T001",
                        "status": "range_intercept",
                        "min_range_m": 0.7,
                        "time_to_intercept_s": 2.0,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    collector = load_d7_guidance_timeseries(
        guidance_records_path=guidance_records_path,
        guidance_summaries_path=guidance_summaries_path,
        control_commands_path=control_commands_path,
        intercept_summary_path=intercept_summary_path,
    )
    metrics = collector.compute_episode("guidance_timeseries_fixture")

    assert metrics.mode_switch_count == 2
    assert metrics.terminal_contract_reject_count == 1
    assert metrics.terminal_switch_reject_count == 2
    assert metrics.intercept_success_count == 1
    assert metrics.metadata["terminal_contract_reject_reasons"] == {
        "terminal_contract_not_satisfied": 1
    }
    assert metrics.metadata["guidance_mode_counts"] == {
        "radar_midcourse": 1,
        "vision_terminal": 3,
    }
    assert metrics.metadata["d4_state_counts"] == {
        "active_degradation": 3,
        "normal": 1,
    }
    assert metrics.metadata["d5_state_counts"] == {
        "terminal_locked": 1,
        "terminal_pending": 1,
        "terminal_rejected": 2,
    }
    assert metrics.metadata["plan_version_counts"] == {"1": 2, "2": 2}
    assert metrics.metadata["plan_ids"] == [
        "d4_active_degradation_degrade_to_secondary",
        "plan-a",
    ]


def test_control_records_report_detect_coast_and_truth_identity_diagnostics(
    tmp_path: Path,
) -> None:
    commands_path = tmp_path / "control_commands.csv"
    _write_csv(
        commands_path,
        [
            {
                "timestamp_s": "0.0",
                "resource_id": "INT-01",
                "target_id": "TGT-001",
                "detection_seen": "True",
                "image_kf_mode": "update",
                "using_blind_push": "False",
                "truth_identity_online_use": "False",
                "contract_allowed": "True",
                "control_allowed": "False",
                "mode_switched": "False",
                "physical_intercept": "False",
                "status": "active",
            },
            {
                "timestamp_s": "1.0",
                "resource_id": "INT-01",
                "target_id": "TGT-001",
                "detection_seen": "False",
                "image_kf_mode": "predict",
                "using_blind_push": "False",
                "truth_identity_online_use": "True",
                "contract_allowed": "True",
                "control_allowed": "True",
                "mode_switched": "True",
                "physical_intercept": "False",
                "status": "active",
            },
            {
                "timestamp_s": "2.0",
                "resource_id": "INT-01",
                "target_id": "TGT-001",
                "detection_seen": "True",
                "image_kf_mode": "update",
                "using_blind_push": "False",
                "truth_identity_online_use": "False",
                "contract_allowed": "True",
                "control_allowed": "True",
                "mode_switched": "False",
                "physical_intercept": "False",
                "status": "active",
            },
            {
                "timestamp_s": "3.0",
                "resource_id": "INT-01",
                "target_id": "TGT-001",
                "detection_seen": "False",
                "image_kf_mode": "invalid",
                "using_blind_push": "True",
                "truth_identity_online_use": "False",
                "contract_allowed": "True",
                "control_allowed": "True",
                "mode_switched": "False",
                "physical_intercept": "False",
                "status": "timeout",
            },
        ],
    )

    metrics = load_d7_intercept_outputs(
        control_commands_path=commands_path
    ).compute_episode("detect_coast")

    assert metrics.image_kf_predict_count == 1
    assert metrics.blind_push_count == 1
    assert metrics.visual_reacquisition_count == 1
    assert metrics.terminal_visual_lost_after_coast_count == 1
    assert metrics.truth_identity_online_use_count == 1
    assert metrics.contract_allowed_count == 4
    assert metrics.control_allowed_count == 3
    assert metrics.mode_switched_count == 1
    assert metrics.pair_physical_success_count == 0


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


def _write_five_pair_summary(path: Path, *, locked_pair_ids: set[int]) -> None:
    path.write_text(
        json.dumps(
            {
                "control_api_used": True,
                "success_count": 0,
                "pair_count": 5,
                "record_count": 5,
                "pairs": [
                    {
                        "resource_id": f"INT-{index:02d}",
                        "target_id": f"TGT-{index:03d}",
                        "status": "active",
                        "min_range_m": 10.0 + index,
                        "terminal_locked": index in locked_pair_ids,
                        "terminal_handover_pending": True,
                    }
                    for index in range(1, 6)
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_coalition_summary(
    path: Path,
    *,
    pair_statuses: tuple[str, str],
    arrival_timestamps: tuple[float | None, float | None],
) -> None:
    path.write_text(
        json.dumps(
            {
                "control_api_used": True,
                "success_count": sum(
                    status in {"collision_intercept", "range_intercept"}
                    for status in pair_statuses
                ),
                "pair_count": 2,
                "parameters": {
                    "intercept_radius_m": 5.0,
                    "intercept_distance_frame": "NED",
                    "intercept_distance_dimension": "3d_euclidean",
                    "intercept_success_criteria_version": "airsim-range-intercept-v2",
                },
                "pairs": [
                    {
                        "resource_id": f"INT-{index + 1:02d}",
                        "target_id": "TGT-001",
                        "assigned": True,
                        "activation_state": "active",
                        "member_role": "primary",
                        "required_primary": True,
                        "required_primary_count": 2,
                        "arrival_window": [3.0, 5.0],
                        "arrival_timestamp_s": arrival_timestamps[index],
                        "time_to_intercept_s": arrival_timestamps[index],
                        "status": pair_statuses[index],
                    }
                    for index in range(2)
                ],
            }
        ),
        encoding="utf-8",
    )
