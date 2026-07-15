from __future__ import annotations

import csv
from dataclasses import dataclass
import json

from d6_evaluation_metrics import (
    P1_ACCEPTANCE_SCHEMA_VERSION,
    P1AcceptanceInputs,
    P1AcceptanceReportGenerator,
    TERMINAL_METRIC_ENVELOPE_SCHEMA_VERSION,
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

    assert set(outputs) == {
        "per_seed_csv",
        "per_seed_json",
        "terminal_metrics_csv",
        "aggregate_json",
        "aggregate_csv",
        "markdown",
        "plot",
    }
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs.values())
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["schema_version"] == P1_ACCEPTANCE_SCHEMA_VERSION
    assert aggregate["offline_only"] is True
    assert aggregate["terminal_layers"]["contract_allowed_count"]["status"] == (
        "unavailable"
    )
    diagnostics = aggregate["terminal_layer_diagnostics"]
    assert diagnostics["contract_allowed_count"]["sum"] == 5.0
    assert diagnostics["control_allowed_count"]["sum"] == 4.0
    assert diagnostics["mode_switched_count"]["sum"] == 3.0
    assert diagnostics["physical_intercept_count"]["sum"] == 2.0
    assert aggregate["physical_levels"]["pair"]["success_count"] == 4.0
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
    # A bare physical count without producer/scope/lifecycle remains
    # unavailable and is not promoted to the generic physical-intercept layer.
    assert legacy["pair_success_count"] == ""
    assert legacy["pair_success_count_availability"] == "unavailable"

    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "末端五层证据" in report
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
    assert aggregate["d3_canonical_history"]["status"] == "unavailable"
    assert aggregate["d3_canonical_history"]["validation_reasons"] == [
        "history_summary_not_provided"
    ]
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
    # Main terminal rows remain diagnostics and cannot replace canonical actual
    # execution evidence.
    assert aggregate["terminal_layers"]["contract_allowed_count"]["status"] == (
        "unavailable"
    )
    diagnostics = aggregate["terminal_layer_diagnostics"]
    assert diagnostics["contract_allowed_count"]["sum"] == 1.0
    assert diagnostics["control_allowed_count"]["sum"] == 1.0
    assert diagnostics["mode_switched_count"]["sum"] == 1.0
    assert diagnostics["physical_intercept_count"]["sum"] == 1.0

    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "matrix complete=`True`" in report
    assert "all compliant=`True`" in report
    assert "seed count=`1`" in report
    assert "not expanding=`1`" in report
    assert "candidate triggered=`0`" in report
    assert "promotion recommended=`False`" in report


def test_terminal_metric_envelopes_isolate_planned_lock_and_execution(tmp_path) -> None:
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1AcceptanceInputs(
            main_terminal_closure={
                "rows": [
                    {
                        "case_id": "seed-1-planned",
                        "seed": 1,
                        "terminal_metrics": [
                            {
                                "metric_name": "contract_allowed_count",
                                "value": 1,
                                "producer": "main_episode_bus",
                                "metric_scope": "planned_lock",
                                "denominator": 2,
                                "lifecycle": "plan_generation",
                            },
                            {
                                "metric_name": "physical_intercept_count",
                                "value": 0,
                                "producer": "main_episode_bus",
                                "metric_scope": "planned_lock",
                                "denominator": 0,
                                "lifecycle": "plan_generation",
                            },
                        ],
                    }
                ]
            },
            d7_terminal_execution={
                "schema": "d7_terminal_execution_v1",
                "rows": [
                    {
                        "case_id": "seed-1-execution",
                        "seed": 1,
                        "terminal_metrics": [
                            {
                                "metric_name": "contract_allowed_count",
                                "value": 1,
                                "producer": "d7_runtime_bus",
                                "metric_scope": "execution",
                                "denominator": 2,
                                "lifecycle": "terminal_execution",
                            }
                        ],
                    }
                ],
            },
        ),
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    contract = aggregate["terminal_layer_diagnostics"]["contract_allowed_count"]
    assert contract["semantic_group_count"] == 2
    assert contract["cross_group_aggregation_prohibited"] is True
    assert contract["sum"] is None
    assert {
        (group["producer"], group["metric_scope"], group["lifecycle"])
        for group in contract["groups"]
    } == {
        ("main_episode_bus", "planned_lock", "plan_generation"),
        ("d7_runtime_bus", "execution", "terminal_execution"),
    }
    physical = aggregate["terminal_layer_diagnostics"]["physical_intercept_count"]
    assert physical["status"] == "unavailable"
    assert physical["sum"] is None

    rows = list(csv.DictReader(outputs["terminal_metrics_csv"].open(encoding="utf-8")))
    assert all(row["schema"] == TERMINAL_METRIC_ENVELOPE_SCHEMA_VERSION for row in rows)
    invalid = next(row for row in rows if row["metric_name"] == "physical_intercept_count")
    assert invalid["status"] == "unavailable"
    assert "denominator_has_no_samples" in invalid["unavailable_reason"]


def test_performance_zero_requires_positive_sample_denominator(tmp_path) -> None:
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1AcceptanceInputs(
            main_terminal_closure={
                "rows": [
                    {
                        "case_id": "sampled",
                        "seed": 1,
                        "performance_metrics": {
                            "sample_count": 10,
                            "loop_latency_ms": 8.5,
                            "performance_budget_violation_count": 0,
                        },
                    },
                    {
                        "case_id": "no-samples",
                        "seed": 2,
                        "performance_metrics": {
                            "sample_count": 0,
                            "loop_latency_ms": 0,
                            "performance_budget_violation_count": 0,
                        },
                    },
                ]
            }
        ),
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    latency = aggregate["performance"]["loop_latency_ms"]
    violation = aggregate["performance"]["performance_budget_violation_count"]
    assert latency["available_count"] == 1
    assert latency["unavailable_count"] == 1
    assert latency["mean"] == 8.5
    assert violation["available_count"] == 1
    assert violation["sum"] == 0
    rows = list(csv.DictReader(outputs["per_seed_csv"].open(encoding="utf-8")))
    no_samples = next(row for row in rows if row["scenario_id"] == "no-samples")
    assert no_samples["loop_latency_ms"] == ""
    assert no_samples["performance_budget_violation_count"] == ""
    assert no_samples["loop_latency_ms_availability"] == "unavailable"
    assert no_samples["performance_availability_reason"] == (
        "performance_sample_count_missing_or_zero"
    )


def test_zero_effect_and_zero_trigger_is_inconclusive_not_promoted(tmp_path) -> None:
    rows = []
    for profile in ("baseline", "candidate_soft_prediction_trend_coast"):
        rows.append(
            {
                "case_id": f"{profile}-seed-1",
                "family": "m5n2_paired",
                "profile": profile,
                "seed": 1,
                "pair_opportunity_count": 2,
                "pair_success_count": 0,
                "target_opportunity_count": 2,
                "target_success_count": 0,
                "coalition_opportunity_count": 1,
                "coalition_completion_count": 0,
                "terminal_trend_coast_count": 0,
                "physical_metric_context": {
                    "producer": "d6_offline_physical_scorer",
                    "metric_scope": "execution",
                    "lifecycle": "episode_physical_scoring",
                },
            }
        )
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1AcceptanceInputs(main_terminal_closure={"rows": rows}),
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    comparison = aggregate["candidate_non_degradation"]
    assert comparison["status"] == "pass"
    assert comparison["baseline_effect"] == 0
    assert comparison["candidate_effect"] == 0
    assert comparison["effectiveness_evidence"] == {
        "status": "inconclusive",
        "reason": "baseline_candidate_zero_and_candidate_not_triggered",
    }
    assert comparison["promotion_recommended"] is False
    assert aggregate["trend_coast"]["promotion_recommended"] is False
    assert aggregate["trend_coast"]["effectiveness_evidence"]["status"] == (
        "inconclusive"
    )


def test_terminal_suite_consumes_canonical_d3_history_file(tmp_path) -> None:
    history_path = tmp_path / "d3_plan_history.json"
    history_path.write_text(
        json.dumps(
            {
                "schema": "d3_plan_history_v1",
                "schema_version": 1,
                "episode_id": "terminal-suite-seed-7",
                "scenario_name": "M3N1_terminal",
                "seed": 7,
                "record_count": 2,
                "history": [
                    _canonical_history_record(0, 0.0),
                    _canonical_history_record(
                        1,
                        1.0,
                        plan_version=2,
                        owner="SECONDARY-1",
                        soft_count=1,
                    ),
                ],
            }
        ),
        encoding="utf-8",
    )
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path / "report",
        inputs=P1AcceptanceInputs(d3_plan_history=history_path),
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    history = aggregate["d3_canonical_history"]
    assert history["status"] == "available"
    assert history["record_count"] == 2
    assert history["latest_plan"]["plan_id"] == "plan-2"
    assert history["latest_plan"]["plan_version"] == 2
    assert [item["resource_id"] for item in history["primary_membership"]] == ["R1"]
    assert [item["resource_id"] for item in history["reserve_membership"]] == ["R2"]
    assert history["owner"]["owner_node_id"] == "SECONDARY-1"
    assert history["churn"]["owner_change_count"] == 1
    assert history["churn"]["feedback_churn_count"] == 1
    assert history["churn"]["soft_feedback_churn_count"] == 1
    seed_rows = json.loads(outputs["per_seed_json"].read_text(encoding="utf-8"))[
        "rows"
    ]
    d3_row = next(row for row in seed_rows if row["source"] == "d3_plan_history")
    assert d3_row["d3_history_status"] == "available"
    assert d3_row["plan_version"] == 2
    assert "D3 canonical history" in outputs["markdown"].read_text(encoding="utf-8")


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
                **_terminal_context(denominator=3),
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
                **_terminal_context(denominator=3),
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
            **_terminal_context(denominator=1),
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
            **_terminal_context(denominator=1),
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


def _terminal_context(*, denominator: int) -> dict:
    return {
        "terminal_metric_context": {
            "producer": "d7_runtime_bus",
            "metric_scope": "execution",
            "denominator": denominator,
            "lifecycle": "terminal_execution",
        },
        "physical_metric_context": {
            "producer": "d6_offline_physical_scorer",
            "metric_scope": "execution",
            "lifecycle": "episode_physical_scoring",
        },
    }


def _canonical_history_record(
    sequence_index: int,
    timestamp: float,
    *,
    plan_version: int = 1,
    owner: str = "CENTER",
    soft_count: int = 0,
) -> dict:
    secondary = owner != "CENTER"
    assignments = [
        {
            "target_id": "T1",
            "resource_id": "R1",
            "member_role": "primary",
            "activation_state": "active",
            "active": True,
            "coalition_id": "C1",
        },
        {
            "target_id": "T1",
            "resource_id": "R2",
            "member_role": "reserve",
            "activation_state": "standby",
            "active": False,
            "coalition_id": "C1",
        },
    ]
    return {
        "schema": "d3_plan_history_record_v1",
        "schema_version": 1,
        "sequence_index": sequence_index,
        "ordering_key": [sequence_index, timestamp],
        "timestamp": timestamp,
        "plan_schema": "assignment_plan_v2",
        "plan_id": f"plan-{plan_version}",
        "plan_version": plan_version,
        "window_id": 1,
        "changed": sequence_index > 0,
        "decision_state": "accepted",
        "resource_count": 2,
        "target_count": 1,
        "assigned_count": 2,
        "plan_owner": "secondary" if secondary else "center",
        "active_plan_owner": "secondary" if secondary else "center",
        "owner_node_id": owner,
        "source_node_id": owner,
        "selected_secondary_node_id": owner if secondary else None,
        "secondary_plan_version": plan_version if secondary else None,
        "secondary_leader_epoch": 1 if secondary else None,
        "secondary_lease_expires_at_s": timestamp + 5.0 if secondary else None,
        "previous_plan_id": None,
        "previous_plan_version": None,
        "supersedes_plan_id": None,
        "supersedes_plan_version": None,
        "assignments": assignments,
        "coalitions": [
            {
                "coalition_id": "C1",
                "version": plan_version,
                "epoch": 1,
            }
        ],
        "hysteresis": {"state": "stable", "reason": None},
        "membership_change_records": [],
        "feedback_constraints": {
            "soft_count": soft_count,
            "hard_count": 0,
        },
        "total_cost": 2.0,
        "candidate_total_cost": None,
        "previous_total_cost_current": None,
        "stale_plan_rejected": False,
        "stale_reject_reason": None,
        "latest_plan_id": f"plan-{plan_version}",
        "latest_plan_version": plan_version,
        "rollback_detected": False,
        "rollback_reason": None,
        "replan_reason": None,
    }
