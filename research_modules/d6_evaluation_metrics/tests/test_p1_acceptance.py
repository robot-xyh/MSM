from __future__ import annotations

import csv
from dataclasses import dataclass
import json

from d6_evaluation_metrics import (
    P1_ACCEPTANCE_SCHEMA_VERSION,
    P1AcceptanceInputs,
    P1AcceptanceReportGenerator,
    load_p1_acceptance_source,
)


def test_p1_report_consumes_all_sources_and_preserves_layer_semantics(tmp_path) -> None:
    main_path = tmp_path / "p1_terminal_closure_summary.json"
    main_path.write_text(json.dumps(_main_summary()), encoding="utf-8")

    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path / "report",
        inputs=P1AcceptanceInputs(
            main_terminal_closure=main_path,
            d1_long_replay=_d1_summary(),
            d2_long_replay=_d2_summary(),
            d3_assignment_calibration=_d3_summary(),
            d4_failover_matrix=_d4_summary(),
            d5_visual_calibration=_d5_summary(),
            d7_locked_dropout=_dropout_summary(),
            d7_png_ttc=_png_ttc_summary(),
            d7_trend_coast=_trend_summary(),
        ),
    )

    assert set(outputs) == {"per_seed_csv", "aggregate_json", "markdown", "plot"}
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs.values())
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["schema_version"] == P1_ACCEPTANCE_SCHEMA_VERSION
    assert aggregate["offline_only"] is True
    assert aggregate["terminal_layers"]["contract_allowed_count"]["sum"] == 5.0
    assert aggregate["terminal_layers"]["control_allowed_count"]["sum"] == 4.0
    assert aggregate["terminal_layers"]["mode_switched_count"]["sum"] == 3.0
    assert aggregate["terminal_layers"]["physical_intercept_count"]["sum"] == 2.0
    assert aggregate["physical_levels"]["pair"]["success_count"] == 5.0
    assert aggregate["physical_levels"]["target"]["success_count"] == 4.0
    assert aggregate["physical_levels"]["coalition"]["success_count"] == 1.0
    assert aggregate["d4_failover"]["passed_count"] == 2
    assert aggregate["d2_tracking"]["id_switch_count"]["sum"] == 5.0
    assert aggregate["dropout"]["matrix_complete"] is True
    assert aggregate["png_ttc"]["required_reject_coverage_complete"] is True
    assert aggregate["trend_coast"]["promotion_recommended"] is False

    rows = list(csv.DictReader(outputs["per_seed_csv"].open(encoding="utf-8")))
    legacy = next(row for row in rows if row["scenario_id"] == "legacy_seed003")
    assert legacy["contract_allowed_count"] == ""
    assert legacy["contract_allowed_count_availability"] == "unavailable"
    assert legacy["physical_intercept_count"] == ""
    assert legacy["physical_intercept_count_availability"] == "unavailable"
    # Pair success remains independently available and is not promoted to the
    # generic physical-intercept layer.
    assert legacy["pair_success_count"] == "1"
    assert legacy["pair_success_count_availability"] == "available"

    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "末端四层证据" in report
    assert "pair、target、coalition 使用独立分母" in report
    assert "旧日志缺失字段显示为 `unavailable/NA`" in report
    assert "p1_acceptance_overview.png" in report


def test_p1_report_marks_missing_sources_and_metrics_unavailable(tmp_path) -> None:
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path / "empty",
        inputs=P1AcceptanceInputs(main_terminal_closure={"rows": []}),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["source_manifest"]["main_terminal_closure"]["status"] == "available"
    assert aggregate["source_manifest"]["d2_long_replay"]["status"] == "unavailable"
    assert aggregate["terminal_layers"]["contract_allowed_count"]["status"] == "unavailable"
    assert aggregate["physical_levels"]["pair"]["success_count"] is None
    assert aggregate["d2_tracking"]["id_switch_count"]["sum"] is None
    assert outputs["plot"].exists()


def test_main_summary_derives_terminal_specialties_without_d7_summaries(tmp_path) -> None:
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path / "main_fallback",
        inputs=P1AcceptanceInputs(main_terminal_closure=_main_fallback_summary()),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))

    assert aggregate["source_manifest"]["d7_locked_dropout"]["status"] == "unavailable"
    assert aggregate["dropout"]["derived_from"] == "main_terminal_closure"
    assert aggregate["dropout"]["matrix_complete"] is True
    assert aggregate["dropout"]["all_rows_compliant"] is True
    assert aggregate["png_ttc"]["derived_from"] == "main_terminal_closure"
    assert aggregate["png_ttc"]["seed_count"] == 1
    assert aggregate["png_ttc"]["ttc_reject_class_counts"] == {
        "bbox_area_jump": 0,
        "bbox_clipping": 0,
        "area_not_expanding": 1,
        "ttc_out_of_range": 0,
    }
    assert aggregate["png_ttc"]["required_reject_coverage_complete"] is False
    assert aggregate["trend_coast"]["candidate_trigger_count"] == 0
    assert aggregate["trend_coast"]["criteria"]["candidate_triggered"] is False
    assert aggregate["trend_coast"]["promotion_recommended"] is False
    # Four layers continue to consume only explicit same-name fields.
    assert aggregate["terminal_layers"]["contract_allowed_count"]["sum"] == 1.0
    assert aggregate["terminal_layers"]["control_allowed_count"]["sum"] == 1.0
    assert aggregate["terminal_layers"]["mode_switched_count"]["sum"] == 1.0
    assert aggregate["terminal_layers"]["physical_intercept_count"]["sum"] == 1.0

    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "matrix complete=`True`" in report
    assert "all compliant=`True`" in report
    assert "seed count=`1`" in report
    assert "not expanding=`1`" in report
    assert "candidate triggered=`0`" in report
    assert "promotion recommended=`False`" in report


def test_p1_loader_accepts_dataclass_report_objects() -> None:
    @dataclass
    class Summary:
        schema_version: str = "fixture-v1"
        seed: int = 4

    assert load_p1_acceptance_source(Summary()) == {
        "schema_version": "fixture-v1",
        "seed": 4,
    }


def _main_summary() -> dict:
    return {
        "calibration_suite_version": "p1-terminal-closure-v1",
        "rows": [
            {
                "case_id": "baseline_seed001",
                "family": "m5n2_paired",
                "profile": "baseline",
                "seed": 1,
                "resource_count": 5,
                "target_count": 2,
                "contract_allowed_count": 2,
                "control_allowed_count": 2,
                "mode_switched_count": 1,
                "physical_intercept_count": 1,
                "pair_opportunity_count": 3,
                "pair_success_count": 2,
                "target_opportunity_count": 2,
                "target_success_count": 2,
                "coalition_opportunity_count": 1,
                "coalition_completion_count": 0,
                "online_truth_use_count": 0,
            },
            {
                "case_id": "candidate_seed001",
                "family": "m5n2_paired",
                "profile": "candidate_soft_prediction_trend_coast",
                "seed": 1,
                "resource_count": 5,
                "target_count": 2,
                "contract_allowed_count": 3,
                "control_allowed_count": 2,
                "mode_switched_count": 2,
                "physical_intercept_count": 1,
                "pair_opportunity_count": 3,
                "pair_success_count": 2,
                "target_opportunity_count": 2,
                "target_success_count": 2,
                "coalition_opportunity_count": 1,
                "coalition_completion_count": 1,
                "online_truth_use_count": 0,
            },
            {
                "case_id": "legacy_seed003",
                "family": "m5n2_paired",
                "profile": "legacy",
                "seed": 3,
                "resource_count": 5,
                "target_count": 2,
                "pair_opportunity_count": 3,
                "pair_success_count": 1,
            },
        ],
        "m5n2_paired": {
            "pair_count": 1,
            "candidate_pair_non_degradation": True,
        },
    }


def _d1_summary() -> dict:
    return {
        "schema_version": "d1.long_replay_summary.v1",
        "scenario_id": "d1-crossing",
        "scenario_version": "d1-crossing-v1",
        "seed": 1,
        "target_count": 3,
        "observation_count": 100,
        "event_counts": {"radar_oosm": 4},
        "final_track_count": 3,
        "online_truth_leak_count": 0,
        "metric_availability": {"rmse": {"available": False}},
    }


def _main_fallback_summary() -> dict:
    dropout_rows = [
        {
            "dropout_frames": frame_count,
            "expected_prediction_window_expiry": frame_count >= 3,
            "passed": True,
            "prediction_count": min(frame_count, 2),
            "prediction_window_expired_count": int(frame_count >= 3),
        }
        for frame_count in range(1, 6)
    ]
    rows = [
        {
            "case_id": "m5n2_baseline_seed001",
            "family": "m5n2_paired",
            "profile": "baseline",
            "seed": 1,
            "contract_allowed_count": 0,
            "control_allowed_count": 0,
            "mode_switched_count": 0,
            "physical_intercept_count": 0,
            "terminal_trend_coast_count": 0,
        },
        {
            "case_id": "m5n2_candidate_seed001",
            "family": "m5n2_paired",
            "profile": "candidate_soft_prediction_trend_coast",
            "seed": 1,
            "contract_allowed_count": 1,
            "control_allowed_count": 1,
            "mode_switched_count": 1,
            "physical_intercept_count": 1,
            "terminal_trend_coast_count": 0,
        },
        {
            "case_id": "png_ttc_2v2_seed001",
            "family": "png_ttc",
            "profile": "png_ttc",
            "seed": 1,
            "ttc_area_jump_reject_count": 0,
            "ttc_bbox_clipping_reject_count": 0,
            "ttc_not_expanding_reject_count": 1,
            "ttc_out_of_range_reject_count": 0,
        },
    ]
    rows.extend(
        {
            "case_id": f"dropout_{item['dropout_frames']}f_seed001",
            "family": "locked_dropout",
            "profile": f"dropout_{item['dropout_frames']}_frames",
            "seed": 1,
            "dropout_frames": item["dropout_frames"],
            "terminal_prediction_count": item["prediction_count"],
            "terminal_prediction_window_expired_count": item[
                "prediction_window_expired_count"
            ],
        }
        for item in dropout_rows
    )
    return {
        "calibration_suite_version": "p1-terminal-closure-v1",
        "acceptance": {
            "dropout_matrix": {
                "all_passed": True,
                "case_count": 5,
                "rows": dropout_rows,
            }
        },
        "rows": rows,
    }


def _d2_summary() -> dict:
    return {
        "schema_version": "d2-long-replay-calibration/v1",
        "per_seed": [
            {
                "seed": 1,
                "scenario_name": "crossing",
                "target_count": 5,
                "id_switch_count": 2,
                "track_continuity": 0.8,
                "false_track_count": 1,
                "rmse": 0.3,
                "nis": {"mean": 1.2},
                "nees": {"mean": 1.1},
                "online_truth_leakage_count": 0,
            },
            {
                "seed": 2,
                "scenario_name": "crossing",
                "target_count": 5,
                "id_switch_count": 3,
                "track_continuity": 0.7,
                "false_track_count": 2,
                "rmse": 0.4,
                "online_truth_leakage_count": 0,
            },
        ],
        "aggregate": {"seed_count": 2},
    }


def _d3_summary() -> dict:
    return {
        "profile_id": "d3-p1",
        "profile_version": "v1",
        "scenario_count": 1,
        "transition_count": 1,
        "equivalent_transition_count": 1,
        "incremental_applied_count": 1,
        "fallback_count": 0,
        "rows": [
            {
                "scenario_id": "5v3",
                "scenario_kind": "non_equal_nm",
                "resource_count": 5,
                "target_count": 3,
                "incremental_applied": True,
                "assignment_equivalent": True,
                "cost_equivalent": True,
            }
        ],
    }


def _d4_summary() -> dict:
    return {
        "schema": "d4_p1_failover_disturbance_replay_v1",
        "summary": {
            "scenario_count": 2,
            "passed_count": 2,
            "false_degradation_count": 0,
        },
        "cases": [
            {
                "scenario_id": "normal",
                "passed": True,
                "execution_allowed": False,
                "fail_closed": False,
            },
            {
                "scenario_id": "missing_ack",
                "passed": True,
                "execution_allowed": False,
                "fail_closed": True,
            },
        ],
    }


def _d5_summary() -> dict:
    return {
        "schema_version": "d5-visual-readiness-v1",
        "seed_count": 2,
        "ready_seed_count": 1,
        "total_observation_count": 20,
        "total_terminal_association_count": 10,
        "seeds": [
            {"seed_id": "1", "missing_required_fields": []},
            {"seed_id": "2", "missing_required_fields": ["geometry_gate_log"]},
        ],
    }


def _dropout_summary() -> dict:
    matrix = {}
    for frame_count in range(1, 6):
        state = "image_kf_predict" if frame_count <= 2 else "expired"
        matrix[str(frame_count)] = {
            "record_count": 1,
            "identity_plan_consistent_count": 1,
            "state_counts": {state: 1},
        }
    return {
        "boundary": "d7_p1_terminal_delivery_calibration_report_only",
        "matrix_complete": True,
        "all_rows_compliant": True,
        "identity_plan_inconsistent_count": 0,
        "matrix": matrix,
    }


def _png_ttc_summary() -> dict:
    return {
        "boundary": "d7_p1_terminal_delivery_calibration_report_only",
        "seed_count": 10,
        "required_reject_coverage_complete": True,
        "ttc_reject_class_counts": {
            "bbox_area_jump": 1,
            "bbox_clipping": 2,
            "area_not_expanding": 3,
            "ttc_out_of_range": 4,
        },
    }


def _trend_summary() -> dict:
    return {
        "boundary": "d7_p1_terminal_delivery_calibration_report_only",
        "candidate_trigger_count": 2,
        "candidate_wrong_binding_count": 0,
        "candidate_command_discontinuity_rate": 0.2,
        "candidate_physical_success_rate": 0.8,
        "promotion_recommended": False,
    }
