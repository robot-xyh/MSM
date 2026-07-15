import csv
import json

import pytest

from d6_evaluation_metrics import EpisodeMetrics, ReportGenerator
from d6_evaluation_metrics.intercept_replay import load_d7_guidance_timeseries


def test_terminal_delivery_metrics_are_passive_and_availability_aware(tmp_path) -> None:
    path = tmp_path / "control_commands.csv"
    fieldnames = [
        "timestamp_s",
        "resource_id",
        "target_id",
        "terminal_filter_state",
        "terminal_filter_innovation_rejected",
        "terminal_filter_reset",
        "terminal_delivery_state",
        "terminal_delivery_reason",
        "ttc_reject_reason",
        "soft_prediction_active",
        "soft_prediction_elapsed_s",
        "soft_prediction_expired",
        "terminal_coast_active",
        "terminal_coast_elapsed_s",
        "terminal_coast_expired",
        "terminal_locked",
        "visual_mode_active",
        "command_vx_mps",
        "command_vy_mps",
        "terminal_delivery_profile",
    ]
    rows = [
        {
            "timestamp_s": 0.0,
            "resource_id": "R1",
            "target_id": "T1",
            "terminal_filter_state": "measured",
            "terminal_filter_reset": "true",
            "soft_prediction_active": "false",
            "terminal_coast_active": "false",
            "terminal_locked": "true",
            "visual_mode_active": "true",
            "command_vx_mps": 1.0,
            "command_vy_mps": 0.0,
            "terminal_delivery_profile": "candidate",
        },
        {
            "timestamp_s": 0.1,
            "resource_id": "R1",
            "target_id": "T1",
            "terminal_filter_state": "soft_prediction",
            "terminal_filter_innovation_rejected": "true",
            "soft_prediction_active": "true",
            "soft_prediction_elapsed_s": 0.1,
            "terminal_coast_active": "false",
            "terminal_locked": "true",
            "visual_mode_active": "true",
            "command_vx_mps": 2.0,
            "command_vy_mps": 0.0,
            "terminal_delivery_profile": "candidate",
        },
        {
            "timestamp_s": 0.2,
            "resource_id": "R1",
            "target_id": "T1",
            "terminal_delivery_state": "blind_push",
            "ttc_reject_reason": "area_jump",
            "soft_prediction_active": "false",
            "terminal_coast_active": "true",
            "terminal_coast_elapsed_s": 0.0,
            "terminal_locked": "true",
            "visual_mode_active": "true",
            "command_vx_mps": 2.0,
            "command_vy_mps": 1.0,
            "terminal_delivery_profile": "candidate",
        },
        {
            "timestamp_s": 0.3,
            "resource_id": "R1",
            "target_id": "T1",
            "terminal_delivery_state": "blind_push",
            "ttc_reject_reason": "bbox_clipping",
            "soft_prediction_active": "false",
            "terminal_coast_active": "true",
            "terminal_coast_elapsed_s": 0.1,
            "terminal_locked": "false",
            "visual_mode_active": "true",
            "command_vx_mps": 2.0,
            "command_vy_mps": 2.0,
            "terminal_delivery_profile": "candidate",
        },
        {
            "timestamp_s": 0.4,
            "resource_id": "R1",
            "target_id": "T1",
            "terminal_delivery_state": "expired",
            "terminal_delivery_reason": "terminal_visual_lost_after_coast",
            "ttc_reject_reason": "not_expanding",
            "soft_prediction_active": "false",
            "soft_prediction_expired": "true",
            "terminal_coast_active": "false",
            "terminal_coast_expired": "true",
            "terminal_locked": "false",
            "visual_mode_active": "false",
            "command_vx_mps": 2.0,
            "command_vy_mps": 2.0,
            "terminal_delivery_profile": "candidate",
        },
        {
            "timestamp_s": 0.5,
            "resource_id": "R1",
            "target_id": "T1",
            "terminal_filter_state": "measured",
            "ttc_reject_reason": "ttc_out_of_range",
            "soft_prediction_active": "false",
            "terminal_coast_active": "false",
            "terminal_locked": "true",
            "visual_mode_active": "true",
            "command_vx_mps": 2.0,
            "command_vy_mps": 2.0,
            "terminal_delivery_profile": "candidate",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    collector = load_d7_guidance_timeseries(control_commands_path=path)
    metrics = collector.compute_episode(
        "candidate_seed1",
        seed=1,
        scenario_group="2v2",
        truth_summary={"resource_count": 2, "target_count": 2, "camera_count": 2},
    )

    assert metrics.terminal_filter_measured_count == 2
    assert metrics.terminal_filter_predicted_count == 1
    assert metrics.terminal_filter_innovation_rejected_count == 1
    assert metrics.terminal_filter_reset_count == 1
    assert metrics.terminal_filter_expired_count == 1
    assert metrics.ttc_area_jump_reject_count == 1
    assert metrics.ttc_bbox_clipping_reject_count == 1
    assert metrics.ttc_not_expanding_reject_count == 1
    assert metrics.ttc_out_of_range_reject_count == 1
    assert metrics.soft_prediction_count == 1
    assert metrics.soft_prediction_duration_s == pytest.approx(0.1)
    assert metrics.soft_prediction_expired_count == 1
    assert metrics.terminal_coast_count == 2
    assert metrics.terminal_coast_duration_s == pytest.approx(0.2)
    assert metrics.terminal_coast_expired_count == 1
    assert metrics.terminal_lock_continuity == pytest.approx(2 / 3)
    assert metrics.visual_mode_duration_s == pytest.approx(0.4)
    assert metrics.command_discontinuity_mean_mps == pytest.approx(0.6)
    assert metrics.command_discontinuity_max_mps == pytest.approx(1.0)
    assert metrics.metric_availability["terminal_filter_measured_count"]["status"] == "available"
    assert metrics.metadata["terminal_delivery_profile"] == "candidate"

    legacy = load_d7_guidance_timeseries(
        control_commands_path=_write_legacy_control_csv(tmp_path)
    ).compute_episode("legacy")
    assert legacy.terminal_filter_measured_count is None
    assert legacy.terminal_coast_duration_s is None
    assert legacy.metric_availability["terminal_filter_measured_count"]["status"] == "unavailable"


def test_terminal_delivery_report_separates_profiles_and_actual_nm(tmp_path) -> None:
    available = {
        name: {"status": "available"}
        for name in (
            "terminal_filter_measured_count",
            "pair_physical_success_count",
            "target_intercept_success_count",
            "coalition_completion_count",
            "truth_state_online_use_count",
        )
    }
    episodes = [
        EpisodeMetrics(
            episode_id="2v2_baseline_seed1",
            seed=1,
            scenario_group="2v2",
            metric_scope="execution",
            resource_count=2,
            target_count=2,
            camera_count=2,
            terminal_filter_measured_count=4,
            pair_physical_success_count=2,
            target_intercept_success_count=2,
            coalition_completion_count=None,
            truth_state_online_use_count=0,
            metric_availability={
                **available,
                "coalition_completion_count": {
                    "status": "unavailable",
                    "reason": "coalition opportunity denominator is missing",
                },
            },
            metadata={
                "terminal_delivery_profile": "baseline",
                "physical_intercept_source": "offline_truth_distance_scorer",
                "online_control_state_source": "d2_estimated_global_track",
                "physical_intercept_evidence_available": True,
            },
        ),
        EpisodeMetrics(
            episode_id="m5n2_candidate_seed1",
            seed=1,
            scenario_group="M5N2",
            metric_scope="execution",
            resource_count=5,
            target_count=2,
            camera_count=5,
            terminal_filter_measured_count=8,
            pair_physical_success_count=2,
            target_intercept_success_count=2,
            coalition_completion_count=0,
            truth_state_online_use_count=1,
            metric_availability=available,
            metadata={
                "terminal_delivery_profile": "candidate",
                "physical_intercept_source": "online_truth_state_fixture",
                "online_control_state_source": "airsim_actor_truth_fixture",
                "physical_intercept_evidence_available": True,
            },
        ),
    ]

    outputs = ReportGenerator().write_terminal_delivery_comparison_bundle(
        episodes,
        tmp_path / "report",
    )

    payload = json.loads(outputs["summary_json"].read_text(encoding="utf-8"))
    assert payload["offline_only"] is True
    assert {(row["profile"], row["resource_count"], row["target_count"]) for row in payload["groups"]} == {
        ("baseline", 2, 2),
        ("candidate", 5, 2),
    }
    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "2v2 与 M5N2 分开统计" in report
    assert "baseline" in report
    assert "candidate" in report
    assert "coalition completion" in report
    assert "Truth-state online" in report
    assert "offline_truth_distance_scorer:1" in report
    assert "coalition opportunity denominator is missing:1" in report
    csv_rows = list(csv.DictReader(outputs["episode_csv"].open(encoding="utf-8")))
    assert len(csv_rows) == 2
    assert "terminal_filter_measured_count_availability" in csv_rows[0]
    assert csv_rows[0]["truth_state_online_use_count"] == "0"
    assert csv_rows[0]["physical_intercept_source"] == (
        "offline_truth_distance_scorer"
    )
    assert csv_rows[0]["coalition_completion_count_availability"] == "unavailable"
    assert csv_rows[0]["coalition_completion_count_unavailable_reason"] == (
        "coalition opportunity denominator is missing"
    )
    baseline_group = next(
        row for row in payload["groups"] if row["profile"] == "baseline"
    )
    assert baseline_group["metrics"]["coalition_completion_count"][
        "unavailable_reasons"
    ] == {"coalition opportunity denominator is missing": 1}


def _write_legacy_control_csv(tmp_path):
    path = tmp_path / "legacy_control_commands.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("timestamp_s", "resource_id", "target_id", "mode"),
        )
        writer.writeheader()
        writer.writerow(
            {
                "timestamp_s": 0.0,
                "resource_id": "R1",
                "target_id": "T1",
                "mode": "midcourse",
            }
        )
    return path
