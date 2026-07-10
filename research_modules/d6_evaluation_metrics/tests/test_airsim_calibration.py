from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    AirSimCalibrationRecord,
    AirSimCalibrationReportGenerator,
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_RNG_SEED,
    STANDARD_MAPPING_VERSION,
    aggregate_cross_seed_airsim_calibration_records,
    compare_paired_airsim_calibration_records,
    load_airsim_calibration_records,
    summarize_airsim_calibration_records,
)


def test_airsim_calibration_summary_loads_d4d5_and_main_bus_outputs(
    tmp_path: Path,
) -> None:
    batch_root = tmp_path / "p1_d4d5_mobile_recon_20260708_055948"
    seed1_case = batch_root / "p1_d4d5_mobile_recon_20260708_055948_seed001" / "case_001_no_degradation"
    seed2_case = batch_root / "p1_d4d5_mobile_recon_20260708_055948_seed002" / "case_001_no_degradation"
    _write_episode_fixture(
        seed1_case,
        seed=1,
        coverage_ratio=0.70,
        detect_count=72,
        cross_view_count=4,
        not_registered_count=1,
        unnecessary_count=1,
        reject_reasons={"d5_not_locked": 2},
        contract_reject_reasons={"d4_reassign_pending": 1},
        write_contract=True,
    )
    _write_episode_fixture(
        seed2_case,
        seed=2,
        coverage_ratio=0.60,
        detect_count=68,
        cross_view_count=3,
        not_registered_count=2,
        unnecessary_count=0,
        reject_reasons={"stable_frame_count_low": 3},
        contract_reject_reasons={},
        write_contract=False,
    )

    records = load_airsim_calibration_records([batch_root])
    rows = summarize_airsim_calibration_records(records)

    assert len(records) == 3
    execution_seed1 = _find_record(records, metric_scope="execution", seed=1)
    assert execution_seed1.scenario == "no_degradation"
    assert execution_seed1.drone_count == 3
    assert execution_seed1.resource_count == 3
    assert execution_seed1.target_count == 4
    assert execution_seed1.camera_count == 6
    assert execution_seed1.secondary_count == 2
    assert execution_seed1.secondary_height_above_targets_m == pytest.approx(200.0)
    assert execution_seed1.secondary_height_bucket == "secondary_200m"
    assert execution_seed1.secondary_fov_degrees == pytest.approx(80.0)
    assert execution_seed1.detection_backend == "simGetDetections"
    assert execution_seed1.comparison_role == "baseline"
    assert execution_seed1.scenario_version == "p1-calibration-v1"
    assert execution_seed1.standard_mapping_version == STANDARD_MAPPING_VERSION
    assert execution_seed1.evidence_path.endswith("main_episode_bus_metrics.json")
    assert "p1_calibration_v1" in execution_seed1.trend_key
    assert execution_seed1.secondary_network_mean_coverage_ratio == pytest.approx(0.70)
    assert execution_seed1.secondary_visible_target_union_ratio == pytest.approx(0.70)
    assert execution_seed1.secondary_detect_count == 72
    assert execution_seed1.funnel_detect_count == 72
    assert execution_seed1.projection_valid_rate == pytest.approx(0.95)
    assert execution_seed1.geometry_gate_pass_rate == pytest.approx(4 / 72)
    assert execution_seed1.registered_candidate_count == 4
    assert execution_seed1.stable_cross_view_registration_count == 4
    assert execution_seed1.not_registered_count == 1
    assert execution_seed1.funnel_cross_view_association_count == 4
    assert execution_seed1.cross_view_registration_count == 4
    assert execution_seed1.secondary_detect_available_but_not_registered_count == 1
    assert execution_seed1.funnel_reject_reason_counts["projection_invalid"] == 0
    assert execution_seed1.funnel_reject_reason_counts["geometry_gate_rejected"] == 68
    assert execution_seed1.funnel_reject_reason_counts["stability_window_failed"] == 0
    assert execution_seed1.funnel_reject_reason_counts["registered_to_global_track"] == 4
    assert execution_seed1.unnecessary_degradation_count == 1
    assert execution_seed1.active_degradation_label_count == 4
    assert execution_seed1.d7_guidance_reject_reason_counts == {
        "d4_reassign_pending": 1,
        "d5_not_locked": 2,
    }
    assert execution_seed1.intercept_success_count == 3
    assert execution_seed1.collision_intercept_count == 2
    assert execution_seed1.range_intercept_count == 1
    assert execution_seed1.intercept_abort_count == 1
    assert execution_seed1.min_range_m == pytest.approx(1.2)
    assert execution_seed1.time_to_intercept_s == pytest.approx(4.5)
    assert execution_seed1.visual_png_switch_count == 5
    assert execution_seed1.terminal_switch_allowed_rate == pytest.approx(0.5)
    assert execution_seed1.terminal_takeover_rate == pytest.approx(0.75)
    assert execution_seed1.gate_reject_count == 3

    execution_seed1_row = _find_row(rows, metric_scope="execution", seed="1")
    assert execution_seed1_row["scenario"] == "no_degradation"
    assert execution_seed1_row["secondary_height_above_targets_m"] == pytest.approx(200.0)
    assert execution_seed1_row["comparison_role"] == "baseline"
    assert execution_seed1_row["scenario_versions"] == ["p1-calibration-v1"]
    assert execution_seed1_row["standard_mapping_versions"] == [STANDARD_MAPPING_VERSION]
    assert execution_seed1_row["secondary_height_buckets"] == ["secondary_200m"]
    assert execution_seed1_row["secondary_fov_degrees"] == pytest.approx(80.0)
    assert execution_seed1_row["secondary_count"] == "2"
    assert execution_seed1_row["detection_backend"] == "simGetDetections"
    assert execution_seed1_row["drone_count"] == "3"
    assert execution_seed1_row["target_count"] == "4"
    assert execution_seed1_row["secondary_detect_count"] == 72
    assert execution_seed1_row["funnel_detect_count"] == 72
    assert execution_seed1_row["projection_valid_rate_mean"] == pytest.approx(0.95)
    assert execution_seed1_row["geometry_gate_pass_rate_mean"] == pytest.approx(4 / 72)
    assert execution_seed1_row["registered_candidate_count"] == 4
    assert execution_seed1_row["stable_cross_view_registration_count"] == 4
    assert execution_seed1_row["not_registered_count"] == 1
    assert execution_seed1_row["active_degradation_label_count"] == 4
    assert execution_seed1_row["d7_guidance_reject_reason_counts"] == {
        "d4_reassign_pending": 1,
        "d5_not_locked": 2,
    }
    assert execution_seed1_row["intercept_success_count"] == 3
    assert execution_seed1_row["collision_intercept_count"] == 2
    assert execution_seed1_row["range_intercept_count"] == 1
    assert execution_seed1_row["intercept_abort_count"] == 1
    assert execution_seed1_row["min_range_m_mean"] == pytest.approx(1.2)
    assert execution_seed1_row["time_to_intercept_s_mean"] == pytest.approx(4.5)
    assert execution_seed1_row["visual_png_switch_count"] == 5
    assert execution_seed1_row["terminal_switch_allowed_rate_mean"] == pytest.approx(
        0.5
    )
    assert execution_seed1_row["terminal_takeover_rate_mean"] == pytest.approx(0.75)
    assert execution_seed1_row["gate_reject_count"] == 3

    contract_seed1_row = _find_row(rows, metric_scope="contract", seed="1")
    assert contract_seed1_row["d7_guidance_reject_reason_counts"] == {
        "d4_reassign_pending": 1,
        "d5_not_locked": 2,
    }


def test_airsim_calibration_report_bundle_writes_csv_json_and_chinese_markdown(
    tmp_path: Path,
) -> None:
    baseline_case = tmp_path / "batch_seed003" / "case_001_baseline_200m"
    _write_episode_fixture(
        baseline_case,
        seed=3,
        coverage_ratio=0.50,
        detect_count=55,
        cross_view_count=1,
        not_registered_count=40,
        unnecessary_count=1,
        reject_reasons={"stable_frame_count_low": 4},
        contract_reject_reasons={"d5_not_locked": 2},
        write_contract=False,
        height_m=200.0,
        comparison_role="baseline",
    )
    height_case = tmp_path / "batch_seed003" / "case_002_enhanced_50m"
    _write_episode_fixture(
        height_case,
        seed=3,
        coverage_ratio=0.45,
        detect_count=55,
        cross_view_count=1,
        not_registered_count=40,
        unnecessary_count=1,
        reject_reasons={"stable_frame_count_low": 4},
        contract_reject_reasons={"d5_not_locked": 2},
        write_contract=False,
        height_m=50.0,
        comparison_role="enhanced",
    )
    seed_case = tmp_path / "batch_seed003" / "case_003_enhanced_200m"
    _write_episode_fixture(
        seed_case,
        seed=3,
        coverage_ratio=0.65,
        detect_count=75,
        cross_view_count=0,
        not_registered_count=65,
        unnecessary_count=2,
        reject_reasons={"network_union_incomplete": 13},
        contract_reject_reasons={"d5_not_locked": 5},
        write_contract=False,
        height_m=200.0,
        comparison_role="enhanced",
    )

    generator = AirSimCalibrationReportGenerator()
    outputs = generator.write_report_bundle([tmp_path], tmp_path / "d6_report")

    assert outputs["record_csv"].exists()
    assert outputs["summary_csv"].exists()
    assert outputs["summary_json"].exists()
    assert outputs["cross_seed_csv"].exists()
    assert outputs["paired_comparison_csv"].exists()
    assert outputs["aggregate_json"].exists()
    assert outputs["aggregate_markdown"].exists()
    assert outputs["standard_mapping_csv"].exists()
    assert outputs["markdown"].exists()

    summary_rows = list(csv.DictReader(outputs["summary_csv"].open(encoding="utf-8")))
    assert summary_rows
    assert summary_rows[0]["detection_backend"] == "simGetDetections"
    assert "comparison_role" in summary_rows[0]
    assert "scenario_versions" in summary_rows[0]
    assert "standard_mapping_versions" in summary_rows[0]
    assert "evidence_paths" in summary_rows[0]
    assert "trend_keys" in summary_rows[0]
    assert "secondary_height_buckets" in summary_rows[0]
    assert "funnel_reject_reason_counts" in summary_rows[0]
    assert "network_union_incomplete" in summary_rows[0]["funnel_reject_reason_counts"]
    assert "projection_valid_rate_mean" in summary_rows[0]
    assert "stable_cross_view_registration_count" in summary_rows[0]
    assert "intercept_success_count" in summary_rows[0]
    assert "intercept_abort_count" in summary_rows[0]
    assert "visual_png_switch_count" in summary_rows[0]

    summary_payload = json.loads(outputs["summary_json"].read_text(encoding="utf-8"))
    assert summary_payload["group_fields"][:3] == ["metric_scope", "seed", "scenario"]
    assert "comparison_role" in summary_payload["group_fields"]
    assert summary_payload["rows"][0]["secondary_count"] == "2"
    assert any(
        row["secondary_height_buckets"] == ["secondary_50m"]
        for row in summary_payload["rows"]
    )
    assert any(
        row["secondary_height_buckets"] == ["secondary_200m"]
        for row in summary_payload["rows"]
    )

    mapping_rows = list(
        csv.DictReader(outputs["standard_mapping_csv"].open(encoding="utf-8"))
    )
    assert mapping_rows
    assert any(row["standard_metric_family"] == "terminal" for row in mapping_rows)

    report_text = outputs["markdown"].read_text(encoding="utf-8")
    assert "D6 AirSim 多 Seed 校准报告" in report_text
    assert "Standard C-UAS Mapping" in report_text
    assert STANDARD_MAPPING_VERSION in report_text
    assert "COURAGEOUS/CEN C-UAS testing" in report_text
    assert "Detect-to-registration Funnel" in report_text
    assert "50m vs 200m Secondary Coverage" in report_text
    assert "Coverage Funnel" in report_text
    assert "Baseline vs Enhanced" in report_text
    assert "secondary_50m" in report_text
    assert "secondary_200m" in report_text
    assert "Delta enhanced-baseline" in report_text
    assert "Projection valid" in report_text
    assert "Stable registration" in report_text
    assert "Not registered" in report_text
    assert "Active precision" in report_text
    assert "Unnecessary degradation" in report_text
    assert "D7 Guidance Reject Reason" in report_text
    assert "D6 只消费日志" in report_text
    assert "p1-calibration-v1" in report_text
    assert "network_union_incomplete" in report_text
    assert "geometry_gate_rejected" in report_text
    assert "projection_invalid" in report_text
    assert "d5_not_locked" in report_text

    aggregate_payload = json.loads(
        outputs["aggregate_json"].read_text(encoding="utf-8")
    )
    assert "seed" not in aggregate_payload["cross_seed_group_fields"]
    assert "scenario_group" in aggregate_payload["pair_group_fields"]
    assert "scenario" not in aggregate_payload["pair_group_fields"]
    assert aggregate_payload["bootstrap"] == {
        "confidence_level": 0.95,
        "method": "paired_seed_mean_percentile",
        "minimum_pair_count": 2,
        "resamples": DEFAULT_BOOTSTRAP_RESAMPLES,
        "rng_seed": DEFAULT_BOOTSTRAP_RNG_SEED,
    }
    paired_rows = list(
        csv.DictReader(outputs["paired_comparison_csv"].open(encoding="utf-8"))
    )
    cross_seed_rows = list(
        csv.DictReader(outputs["cross_seed_csv"].open(encoding="utf-8"))
    )
    success_row = next(
        row for row in cross_seed_rows if row["metric"] == "intercept_success_count"
    )
    assert success_row["sum"] == "3.0"
    assert success_row["opportunity_count"] == "4"
    assert success_row["rate"] == "0.75"
    for selected_metric in (
        "collision_intercept_count",
        "range_intercept_count",
        "intercept_abort_count",
        "min_range_m",
        "time_to_intercept_s",
        "visual_png_switch_count",
        "terminal_switch_allowed_rate",
        "terminal_takeover_rate",
        "gate_reject_count",
    ):
        assert any(row["metric"] == selected_metric for row in cross_seed_rows)
    assert any(
        row["metric"] == "secondary_network_mean_coverage_ratio"
        and row["pair_count"] == "1"
        and row["status"] == "descriptive_only"
        and row["bootstrap_ci95_low"] == ""
        and row["bootstrap_ci95_high"] == ""
        for row in paired_rows
    )
    aggregate_report = outputs["aggregate_markdown"].read_text(encoding="utf-8")
    assert "Paired Baseline vs Enhanced" in aggregate_report
    assert "Interception Outcome" in aggregate_report
    assert "3/4" in aggregate_report
    assert "active_degradation_label_count=0" in aggregate_report


def test_cross_seed_pairing_bootstrap_and_missing_seed_contract() -> None:
    records = [
        _calibration_record(seed=1, role="baseline", coverage=0.4),
        _calibration_record(seed=1, role="enhanced", coverage=0.6),
        _calibration_record(seed=2, role="baseline", coverage=0.5),
        _calibration_record(seed=2, role="enhanced", coverage=0.9),
        _calibration_record(seed=3, role="enhanced", coverage=0.7),
        _calibration_record(seed=4, role="baseline", coverage=0.3),
        _calibration_record(
            seed=5,
            role="baseline",
            coverage=0.2,
            camera_count=6,
        ),
        _calibration_record(
            seed=5,
            role="enhanced",
            coverage=0.8,
            camera_count=7,
        ),
    ]

    aggregate_rows = aggregate_cross_seed_airsim_calibration_records(records)
    baseline_coverage = next(
        row
        for row in aggregate_rows
        if row["comparison_role"] == "baseline"
        and row["camera_count"] == "6"
        and row["metric"] == "secondary_network_mean_coverage_ratio"
    )
    assert baseline_coverage["seed_count"] == 4
    assert baseline_coverage["seeds"] == [1, 2, 4, 5]

    first = compare_paired_airsim_calibration_records(records)
    second = compare_paired_airsim_calibration_records(records)
    assert first == second
    coverage_row = next(
        row
        for row in first
        if row["camera_count"] == "6"
        and row["metric"] == "secondary_network_mean_coverage_ratio"
    )
    assert coverage_row["role_pair_count"] == 2
    assert coverage_row["pair_count"] == 2
    assert coverage_row["paired_seeds"] == [1, 2]
    assert coverage_row["missing_baseline_seeds"] == [3]
    assert coverage_row["missing_enhanced_seeds"] == [4, 5]
    assert coverage_row["paired_delta_mean"] == pytest.approx(0.3)
    assert coverage_row["paired_delta_std"] == pytest.approx(0.1414213562)
    assert coverage_row["effect_size"] == pytest.approx(2.1213203436)
    assert coverage_row["bootstrap_ci95_low"] == pytest.approx(0.2)
    assert coverage_row["bootstrap_ci95_high"] == pytest.approx(0.4)
    assert coverage_row["bootstrap_resamples"] == DEFAULT_BOOTSTRAP_RESAMPLES
    assert coverage_row["bootstrap_rng_seed"] == DEFAULT_BOOTSTRAP_RNG_SEED

    camera_mismatch = next(
        row
        for row in first
        if row["camera_count"] == "7"
        and row["metric"] == "secondary_network_mean_coverage_ratio"
    )
    assert camera_mismatch["pair_count"] == 0
    assert camera_mismatch["missing_baseline_seeds"] == [5]

    active_precision = next(
        row
        for row in first
        if row["camera_count"] == "6"
        and row["metric"] == "active_degradation_precision"
    )
    assert active_precision["pair_count"] == 0
    assert active_precision["status"] == "unavailable"
    assert active_precision["paired_delta_mean"] is None


def test_read_only_episode_outcomes_are_unavailable_and_omitted_from_outcome_table(
    tmp_path: Path,
) -> None:
    read_only_dir = tmp_path / "seed001" / "episode_001_d1_sensor"
    read_only_bus = read_only_dir / "main_episode_bus"
    read_only_bus.mkdir(parents=True)
    _write_json(
        read_only_dir / "airsim_blocks_summary.json",
        {
            "connected": True,
            "episode_id": "episode_001_d1_sensor",
            "frame_count": 10,
            "image_ok_count": 10,
            "metadata": {
                "actor_target_count": 2,
                "camera_vehicle_names": ["Interceptor1", "Interceptor2"],
                "first_frame": {"resource_count": 2, "truth_count": 2},
            },
        },
    )
    _write_json(
        read_only_bus / "main_episode_bus_metrics.json",
        {
            "metrics": {
                "episode_id": "episode_001_d1_sensor",
                "seed": 1,
                "scenario_group": "blocks_actor_2v2_active_secondary_visual_png",
                "scenario_version": "blocks_actor_2v2:seed1:v1",
                "drone_count": 2,
                "resource_count": 2,
                "target_count": 2,
                "camera_count": 2,
                "intercept_success_count": 0,
                "collision_intercept_count": 0,
                "range_intercept_count": 0,
                "time_to_intercept_s": 0.0,
                "min_range_m": 0.0,
                "visual_png_switch_count": 0,
                "terminal_switch_allowed_rate": 0.0,
                "terminal_takeover_rate": 0.0,
                "gate_reject_count": 0,
                "metadata": {
                    "d7_control_command_event_count": 0,
                    "intercept_pair_event_count": 0,
                    "intercept_summary_pair_count": None,
                    "intercept_summary_success_count": None,
                    "intercept_status_counts": {},
                },
            }
        },
    )

    full_flow_dir = tmp_path / "seed001" / "episode_006_full_flow"
    _write_episode_fixture(
        full_flow_dir,
        seed=1,
        coverage_ratio=0.5,
        detect_count=10,
        cross_view_count=2,
        not_registered_count=1,
        unnecessary_count=0,
        reject_reasons={},
        contract_reject_reasons={},
        write_contract=False,
    )

    generator = AirSimCalibrationReportGenerator()
    records = generator.load_records([tmp_path])
    read_only_record = next(
        record for record in records if record.scenario == "episode_001_d1_sensor"
    )
    full_flow_record = next(
        record for record in records if record.scenario == "degrade_to_secondary"
    )

    assert read_only_record.intercept_success_count is None
    assert read_only_record.collision_intercept_count is None
    assert read_only_record.range_intercept_count is None
    assert read_only_record.intercept_abort_count is None
    assert read_only_record.min_range_m is None
    assert read_only_record.time_to_intercept_s is None
    assert read_only_record.visual_png_switch_count is None
    assert read_only_record.gate_reject_count is None
    assert full_flow_record.intercept_success_count == 3

    aggregate_rows = generator.aggregate_cross_seed(records)
    read_only_success = next(
        row
        for row in aggregate_rows
        if row["scenario"] == "episode_001_d1_sensor"
        and row["metric"] == "intercept_success_count"
    )
    assert read_only_success["status"] == "unavailable"
    assert read_only_success["value_count"] == 0
    assert read_only_success["sum"] is None
    assert read_only_success["opportunity_count"] is None

    outputs = generator.write_report_bundle([tmp_path], tmp_path / "report")
    report = outputs["aggregate_markdown"].read_text(encoding="utf-8")
    outcome_section = report.split("## Interception Outcome", 1)[1].split(
        "## Paired Baseline vs Enhanced",
        1,
    )[0]
    assert "episode_001_d1_sensor" not in outcome_section
    assert "degrade_to_secondary" in outcome_section
    assert "3/4" in outcome_section


def test_cross_seed_intercept_metrics_report_eighteen_of_twenty() -> None:
    success_counts = [2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
    records = [
        _calibration_record(
            seed=seed,
            role="not_recorded",
            coverage=0.0,
            scenario="episode_006_full_flow",
            scenario_group="blocks_actor_2v2_active_secondary_visual_png",
            target_count=2,
            intercept_success_count=success_count,
            collision_intercept_count=success_count,
            intercept_abort_count=2 - success_count,
            min_range_m=1.5 + seed / 100.0,
            time_to_intercept_s=3.0 + seed / 10.0,
            visual_png_switch_count=seed,
            terminal_switch_allowed_rate=seed / 100.0,
            terminal_takeover_rate=1.0,
            gate_reject_count=70 + seed,
            scenario_version=(
                "blocks_actor_2v2:resources2:targets2:cameras2:"
                f"seed{seed}:backendairsim:v1"
            ),
        )
        for seed, success_count in enumerate(success_counts, start=1)
    ]

    rows = aggregate_cross_seed_airsim_calibration_records(records)
    by_metric = {row["metric"]: row for row in rows}

    assert by_metric["intercept_success_count"]["seed_count"] == 10
    assert by_metric["intercept_success_count"]["sum"] == pytest.approx(18.0)
    assert by_metric["intercept_success_count"]["opportunity_count"] == 20
    assert by_metric["intercept_success_count"]["rate"] == pytest.approx(0.9)
    assert by_metric["collision_intercept_count"]["sum"] == pytest.approx(18.0)
    assert by_metric["range_intercept_count"]["sum"] == pytest.approx(0.0)
    assert by_metric["intercept_abort_count"]["sum"] == pytest.approx(2.0)
    for selected_metric in (
        "min_range_m",
        "time_to_intercept_s",
        "visual_png_switch_count",
        "terminal_switch_allowed_rate",
        "terminal_takeover_rate",
        "gate_reject_count",
    ):
        assert by_metric[selected_metric]["value_count"] == 10


def test_calibration_summary_does_not_report_zero_precision_without_labels() -> None:
    rows = summarize_airsim_calibration_records(
        [
            _calibration_record(
                seed=1,
                role="baseline",
                coverage=0.4,
                active_degradation_precision=0.0,
                active_degradation_label_count=0,
            )
        ]
    )

    assert rows[0]["active_degradation_precision_mean"] is None
    assert rows[0]["active_degradation_label_count"] == 0


def test_paired_comparison_uses_scenario_group_not_case_specific_scenario() -> None:
    records = [
        _calibration_record(
            seed=11,
            role="baseline",
            coverage=0.4,
            scenario="no_degradation",
            scenario_group="blocks_cv_5v5_d4d5_stress",
            case_name="case_001_no_degradation",
        ),
        _calibration_record(
            seed=11,
            role="enhanced",
            coverage=0.7,
            scenario="degrade_to_secondary",
            scenario_group="blocks_cv_5v5_d4d5_stress",
            case_name="case_002_degrade_to_secondary",
        ),
    ]

    rows = compare_paired_airsim_calibration_records(records)
    coverage = next(
        row
        for row in rows
        if row["metric"] == "secondary_network_mean_coverage_ratio"
    )

    assert records[0].case_name != records[1].case_name
    assert records[0].scenario != records[1].scenario
    assert coverage["scenario_group"] == "blocks_cv_5v5_d4d5_stress"
    assert coverage["pair_count"] == 1
    assert coverage["status"] == "descriptive_only"
    assert coverage["bootstrap_ci95_low"] is None
    assert coverage["bootstrap_ci95_high"] is None
    assert coverage["paired_delta_mean"] == pytest.approx(0.3)


def test_cross_seed_pairing_removes_run_seed_from_scenario_version() -> None:
    records = [
        _calibration_record(
            seed=1,
            role="baseline",
            coverage=0.4,
            scenario_version="blocks_cv_n5:v2:seed1:backendairsim",
        ),
        _calibration_record(
            seed=1,
            role="enhanced",
            coverage=0.6,
            scenario_version="blocks_cv_n5:v2:seed1:backendairsim",
        ),
        _calibration_record(
            seed=2,
            role="baseline",
            coverage=0.5,
            scenario_version="blocks_cv_n5:v2:seed2:backendairsim",
        ),
        _calibration_record(
            seed=2,
            role="enhanced",
            coverage=0.9,
            scenario_version="blocks_cv_n5:v2:seed2:backendairsim",
        ),
    ]

    aggregate_rows = aggregate_cross_seed_airsim_calibration_records(records)
    baseline_coverage = next(
        row
        for row in aggregate_rows
        if row["comparison_role"] == "baseline"
        and row["metric"] == "secondary_network_mean_coverage_ratio"
    )
    assert baseline_coverage["scenario_version"] == (
        "blocks_cv_n5:v2:backendairsim"
    )
    assert baseline_coverage["seed_count"] == 2

    paired_rows = compare_paired_airsim_calibration_records(records)
    paired_coverage = next(
        row
        for row in paired_rows
        if row["metric"] == "secondary_network_mean_coverage_ratio"
    )
    assert paired_coverage["scenario_version"] == "blocks_cv_n5:v2:backendairsim"
    assert paired_coverage["paired_seeds"] == [1, 2]
    assert paired_coverage["pair_count"] == 2
    assert paired_coverage["status"] == "available"
    assert paired_coverage["bootstrap_ci95_low"] == pytest.approx(0.2)
    assert paired_coverage["bootstrap_ci95_high"] == pytest.approx(0.4)


def test_episode_loader_prefers_main_bus_scopes_over_stale_blocks_snapshot(
    tmp_path: Path,
) -> None:
    episode_dir = tmp_path / "seed001" / "episode_006_full_flow"
    _write_episode_fixture(
        episode_dir,
        seed=1,
        coverage_ratio=0.5,
        detect_count=10,
        cross_view_count=2,
        not_registered_count=1,
        unnecessary_count=0,
        reject_reasons={},
        contract_reject_reasons={},
        write_contract=True,
    )
    blocks_path = episode_dir / "airsim_blocks_summary.json"
    blocks = json.loads(blocks_path.read_text(encoding="utf-8"))
    blocks["integrated_result"] = {
        "metrics": {
            "drone_count": 3,
            "resource_count": 3,
            "target_count": 2,
            "camera_count": 0,
            "intercept_success_count": 0,
        }
    }
    _write_json(blocks_path, blocks)

    main_bus_dir = episode_dir / "main_episode_bus"
    for name, success_count in (
        ("main_episode_bus_metrics.json", 2),
        ("main_episode_bus_contract_metrics.json", 0),
    ):
        path = main_bus_dir / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["metrics"].update(
            {
                "drone_count": 2,
                "resource_count": 2,
                "target_count": 2,
                "camera_count": 2,
                "intercept_success_count": success_count,
            }
        )
        _write_json(path, payload)

    records = load_airsim_calibration_records([episode_dir])
    execution = next(row for row in records if row.metric_scope == "execution")
    contract = next(row for row in records if row.metric_scope == "contract")

    assert (
        execution.drone_count,
        execution.resource_count,
        execution.target_count,
        execution.camera_count,
    ) == (2, 2, 2, 2)
    assert Path(execution.evidence_path).name == "main_episode_bus_metrics.json"
    assert Path(contract.evidence_path).name == (
        "main_episode_bus_contract_metrics.json"
    )


def test_d4d5_explicit_active_degradation_labels_override_unlabeled_main(
    tmp_path: Path,
) -> None:
    episode_dir = tmp_path / "batch_seed009" / "case_002_degrade_to_secondary"
    _write_episode_fixture(
        episode_dir,
        seed=9,
        coverage_ratio=0.6,
        detect_count=20,
        cross_view_count=2,
        not_registered_count=3,
        unnecessary_count=0,
        reject_reasons={},
        contract_reject_reasons={},
        write_contract=False,
    )
    d4d5_path = episode_dir / "d4d5_stress_metrics.json"
    d4d5 = json.loads(d4d5_path.read_text(encoding="utf-8"))
    d4d5.update(
        {
            "active_degradation_count": 5,
            "active_degradation_precision": 0.75,
            "active_degradation_label_count": 4,
            "unnecessary_active_degradation_count": 1,
        }
    )
    _write_json(d4d5_path, d4d5)

    main_path = episode_dir / "main_episode_bus" / "main_episode_bus_metrics.json"
    main = json.loads(main_path.read_text(encoding="utf-8"))
    main_metrics = main["metrics"]
    main_metrics["active_degradation_count"] = 0
    main_metrics["active_degradation_precision"] = 0.0
    main_metrics["active_degradation_label_count"] = 0
    main_metrics["unnecessary_active_degradation_count"] = 0
    main_metrics["metadata"]["active_degradation_reviewed_count"] = 0
    _write_json(main_path, main)

    record = _find_record(
        load_airsim_calibration_records([episode_dir]),
        metric_scope="execution",
        seed=9,
    )

    assert record.active_degradation_count == 5
    assert record.active_degradation_precision == pytest.approx(0.75)
    assert record.active_degradation_label_count == 4
    assert record.unnecessary_degradation_count == 1


def _calibration_record(
    *,
    seed: int,
    role: str,
    coverage: float,
    camera_count: int = 6,
    scenario: str = "paired_scenario",
    scenario_group: str = "blocks_cv_5v5_d4d5_stress",
    case_name: str = "paired_case",
    active_degradation_precision: float | None = None,
    active_degradation_label_count: int = 0,
    scenario_version: str = "paired-v1",
    target_count: int = 4,
    intercept_success_count: int = 0,
    collision_intercept_count: int = 0,
    range_intercept_count: int = 0,
    intercept_abort_count: int = 0,
    min_range_m: float = 0.0,
    time_to_intercept_s: float = 0.0,
    visual_png_switch_count: int = 0,
    terminal_switch_allowed_rate: float = 0.0,
    terminal_takeover_rate: float = 0.0,
    gate_reject_count: int = 0,
) -> AirSimCalibrationRecord:
    return AirSimCalibrationRecord(
        episode_id=f"{role}_{seed}_{camera_count}",
        seed=seed,
        scenario=scenario,
        scenario_group=scenario_group,
        case_name=case_name,
        metric_scope="execution",
        comparison_role=role,
        scenario_version=scenario_version,
        drone_count=3,
        resource_count=3,
        target_count=target_count,
        camera_count=camera_count,
        secondary_count=2,
        secondary_height_above_targets_m=200.0,
        secondary_fov_degrees=80.0,
        secondary_image_width_px=1920,
        secondary_image_height_px=1080,
        secondary_recon_mode="mobile_recon_gimbal",
        detection_backend="simGetDetections",
        secondary_network_mean_coverage_ratio=coverage,
        active_degradation_precision=active_degradation_precision,
        active_degradation_label_count=active_degradation_label_count,
        intercept_success_count=intercept_success_count,
        collision_intercept_count=collision_intercept_count,
        range_intercept_count=range_intercept_count,
        intercept_abort_count=intercept_abort_count,
        min_range_m=min_range_m,
        time_to_intercept_s=time_to_intercept_s,
        visual_png_switch_count=visual_png_switch_count,
        terminal_switch_allowed_rate=terminal_switch_allowed_rate,
        terminal_takeover_rate=terminal_takeover_rate,
        gate_reject_count=gate_reject_count,
    )


def _find_record(records, *, metric_scope: str, seed: int):
    for record in records:
        if record.metric_scope == metric_scope and record.seed == seed:
            return record
    raise AssertionError(f"record not found: {metric_scope=} {seed=}")


def _find_row(rows, *, metric_scope: str, seed: str):
    for row in rows:
        if row["metric_scope"] == metric_scope and row["seed"] == seed:
            return row
    raise AssertionError(f"row not found: {metric_scope=} {seed=}")


def _write_episode_fixture(
    episode_dir: Path,
    *,
    seed: int,
    coverage_ratio: float,
    detect_count: int,
    cross_view_count: int,
    not_registered_count: int,
    unnecessary_count: int,
    reject_reasons: dict[str, int],
    contract_reject_reasons: dict[str, int],
    write_contract: bool,
    height_m: float = 200.0,
    comparison_role: str = "baseline",
    scenario_version: str = "p1-calibration-v1",
) -> None:
    episode_dir.mkdir(parents=True, exist_ok=True)
    settings_path = episode_dir.parent / "generated_settings" / "blocks_cv_n3_settings.json"
    _write_settings(settings_path)
    _write_json(
        episode_dir / "airsim_blocks_summary.json",
        {
            "connected": True,
            "episode_id": episode_dir.name,
            "frame_count": 13,
            "image_ok_count": 13,
            "metadata": {
                "actor_target_count": 4,
                "camera_vehicle_names": [
                    "Interceptor_Cam_1",
                    "Interceptor_Cam_2",
                    "Interceptor_Cam_3",
                    "Secondary_Recon_1",
                    "Secondary_Recon_2",
                    "Observer_Cam",
                ],
                "resource_vehicle_names": [
                    "Interceptor_Cam_1",
                    "Interceptor_Cam_2",
                    "Interceptor_Cam_3",
                ],
                "secondary_camera_vehicle_names": [
                    "Secondary_Recon_1",
                    "Secondary_Recon_2",
                ],
                "settings_path": str(settings_path),
                "first_frame": {"resource_count": 3, "truth_count": 4},
            },
        },
    )
    _write_json(
        episode_dir / "d4d5_stress_metrics.json",
        {
            "case_name": "no_degradation"
            if "no_degradation" in episode_dir.name
            else "degrade_to_secondary",
            "calibration_role": comparison_role,
            "scenario_version": scenario_version,
            "standard_mapping_version": STANDARD_MAPPING_VERSION,
            "secondary_recon_mode": "mobile_recon_gimbal",
            "secondary_height_above_targets_m": height_m,
            "geometry": {
                "resource_camera_count": 3,
                "secondary_camera_count": 2,
                "target_count": 4,
                "secondary_height_above_targets_m": height_m,
            },
            "multi_target_fov_rate": 0.8,
            "secondary_visible_target_union_ratio": coverage_ratio,
            "secondary_network_mean_coverage_ratio": coverage_ratio,
            "secondary_network_joint_full_view_frame_rate": 0.0,
            "secondary_single_camera_full_view_frame_rate": 0.0,
            "projection_valid_rate": 0.95,
            "geometry_gate_pass_rate": cross_view_count / detect_count
            if detect_count
            else 0.0,
            "registered_candidate_count": cross_view_count,
            "stable_cross_view_registration_count": cross_view_count,
            "not_registered_count": not_registered_count,
            "secondary_gimbal_pointing_ok_rate": 1.0,
            "secondary_bbox_area_px_stats": {
                "count": detect_count,
                "mean": 3300.0 + seed,
            },
            "secondary_cue_pointing_error_m_stats": {
                "count": 10,
                "mean": 0.25,
            },
            "secondary_detect_available_but_not_registered_count": not_registered_count,
            "cross_view_association_count": cross_view_count,
            "secondary_detection_funnel_counts": {
                "detect_count": detect_count,
                "local_or_recon_cue_count": 0,
                "multi_support_count": 0,
                "cross_view_association_count": cross_view_count,
                "terminal_association_count": 0,
                "breakpoint_reasons": [
                    "not_all_targets_visible",
                    "network_union_incomplete",
                ],
                "rejection_reason_counts": {
                    "geometry_gate_rejected": max(detect_count - cross_view_count, 0),
                    "not_all_targets_visible": 26,
                    "network_union_incomplete": 13,
                    "projection_invalid": 0,
                    "stability_window_failed": 0,
                    "no_global_binding": 0,
                    "stale_or_missing_recon_cue": 0,
                    "registered_to_global_track": cross_view_count,
                },
            },
        },
    )
    main_bus_dir = episode_dir / "main_episode_bus"
    main_bus_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        main_bus_dir / "main_episode_bus_metrics.json",
        _main_bus_payload(
            episode_dir.name,
            seed=seed,
            unnecessary_count=unnecessary_count,
            reject_reasons=reject_reasons,
            contract_reject_reasons=contract_reject_reasons,
            comparison_role=comparison_role,
            scenario_version=scenario_version,
        ),
    )
    if write_contract:
        _write_json(
            main_bus_dir / "main_episode_bus_contract_metrics.json",
            _main_bus_payload(
                episode_dir.name,
                seed=seed,
                unnecessary_count=unnecessary_count,
                reject_reasons=reject_reasons,
                contract_reject_reasons=contract_reject_reasons,
                comparison_role=comparison_role,
                scenario_version=scenario_version,
            ),
        )


def _main_bus_payload(
    episode_id: str,
    *,
    seed: int,
    unnecessary_count: int,
    reject_reasons: dict[str, int],
    contract_reject_reasons: dict[str, int],
    comparison_role: str,
    scenario_version: str,
) -> dict[str, object]:
    return {
        "metrics": {
            "episode_id": episode_id,
            "seed": seed,
            "batch_seed": seed,
            "scenario_group": "blocks_cv_5v5_d4d5_stress",
            "scenario_version": scenario_version,
            "standard_mapping_version": STANDARD_MAPPING_VERSION,
            "evidence_path": f"evidence/{episode_id}/main_episode_bus_metrics.json",
            "drone_count": 3,
            "resource_count": 3,
            "target_count": 4,
            "camera_count": 6,
            "active_degradation_count": 4,
            "active_degradation_precision": 0.5,
            "active_degradation_label_count": 4,
            "unnecessary_active_degradation_count": unnecessary_count,
            "intercept_success_count": 3,
            "collision_intercept_count": 2,
            "range_intercept_count": 1,
            "time_to_intercept_s": 4.5,
            "min_range_m": 1.2,
            "visual_png_switch_count": 5,
            "terminal_switch_allowed_rate": 0.5,
            "terminal_takeover_rate": 0.75,
            "terminal_switch_reject_count": sum(reject_reasons.values()),
            "terminal_contract_reject_count": sum(contract_reject_reasons.values()),
            "gate_reject_count": sum(reject_reasons.values())
            + sum(contract_reject_reasons.values()),
            "metadata": {
                "comparison_role": comparison_role,
                "scenario_version": scenario_version,
                "standard_mapping_version": STANDARD_MAPPING_VERSION,
                "active_degradation_reviewed_count": 4,
                "intercept_status_counts": {
                    "aborted": 1,
                    "collision_intercept": 2,
                    "range_intercept": 1,
                },
                "guidance_law_counts": {"png_vm": 2, "radar_pn": 1},
                "terminal_switch_reject_reasons": reject_reasons,
                "terminal_contract_reject_reasons": contract_reject_reasons,
            },
        }
    }


def _write_settings(path: Path) -> None:
    _write_json(
        path,
        {
            "Vehicles": {
                "Interceptor_Cam_1": {"VehicleType": "ComputerVision"},
                "Interceptor_Cam_2": {"VehicleType": "ComputerVision"},
                "Interceptor_Cam_3": {"VehicleType": "ComputerVision"},
                "Secondary_Recon_1": {
                    "VehicleType": "ComputerVision",
                    "Cameras": {
                        "0": {
                            "CaptureSettings": [
                                {
                                    "ImageType": 0,
                                    "FOV_Degrees": 80.0,
                                    "Width": 1920,
                                    "Height": 1080,
                                }
                            ]
                        }
                    },
                },
                "Secondary_Recon_2": {
                    "VehicleType": "ComputerVision",
                    "Cameras": {
                        "0": {
                            "CaptureSettings": [
                                {
                                    "ImageType": 0,
                                    "FOV_Degrees": 80.0,
                                    "Width": 1920,
                                    "Height": 1080,
                                }
                            ]
                        }
                    },
                },
                "Observer_Cam": {"VehicleType": "ComputerVision"},
            }
        },
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
