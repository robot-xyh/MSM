from __future__ import annotations

import csv
import hashlib
import json

from d6_evaluation_metrics import (
    D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS,
    D7_ACTUAL_EXECUTION_METADATA_SEMANTICS,
    D7_ACTUAL_EXECUTION_METADATA_SOURCES,
    D7_ACTUAL_EXECUTION_METRIC_SOURCES,
    D7_ACTUAL_EXECUTION_SCHEMA_VERSION,
    D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS,
    P1AcceptanceInputs,
    P1AcceptanceReportGenerator,
    TERMINAL_CLOSURE_CASE_EVIDENCE_REGISTRATION_SCHEMA_VERSION,
    register_terminal_closure_case_evidence,
)


def test_suite_aggregates_d3_history_by_case_and_seed(tmp_path) -> None:
    first = _write_json(tmp_path / "case-a-d3.json", _history("case-a", 1))
    second = _write_json(tmp_path / "case-b-d3.json", _history("case-b", 2))
    main = {
        "rows": [
            {"case_id": "case-a", "seed": 1, "d3_plan_history": str(first)},
            {"case_id": "case-b", "seed": 2, "d3_plan_history": str(second)},
        ]
    }

    aggregate, report = _generate(tmp_path, main)

    history = aggregate["d3_canonical_history_cases"]
    assert history["status"] == "available"
    assert history["case_count"] == 2
    assert history["available_case_count"] == 2
    assert history["record_count"] == 4
    assert [(item["case_id"], item["seed"]) for item in history["by_case_seed"]] == [
        ("case-a", 1),
        ("case-b", 2),
    ]
    assert history["by_seed"] == [
        {
            "seed": 1,
            "case_count": 1,
            "available_case_count": 1,
            "unavailable_case_count": 0,
            "case_ids": ["case-a"],
        },
        {
            "seed": 2,
            "case_count": 1,
            "available_case_count": 1,
            "unavailable_case_count": 0,
            "case_ids": ["case-b"],
        },
    ]
    assert aggregate["source_manifest"]["d3_plan_history"]["status"] == "available"
    assert "case-a" in report and "case-b" in report


def test_per_case_d7_registration_promotes_only_validated_actual_execution(
    tmp_path,
) -> None:
    d3_path = _write_json(tmp_path / "d3.json", _history("case-a", 7))
    d7_path = _write_json(
        tmp_path / "d7.json",
        _d7_execution(seed=7, artifact_dir=tmp_path),
    )
    row = register_terminal_closure_case_evidence(
        {"case_id": "case-a", "seed": 7},
        d3_plan_history_path=d3_path,
        d7_execution_metrics_path=d7_path,
    )

    assert row["d7_execution_metrics_registration"] == {
        "schema": TERMINAL_CLOSURE_CASE_EVIDENCE_REGISTRATION_SCHEMA_VERSION,
        "source": "d7_terminal_execution",
        "status": "registered",
        "path": str(d7_path),
        "reason": None,
    }
    aggregate, report = _generate(tmp_path, {"rows": [row]})

    evidence = aggregate["d7_execution_evidence"]
    assert evidence["status"] == "available"
    assert evidence["available_case_count"] == 1
    case = evidence["by_case_seed"][0]
    assert case["detected_payload_schema"] == D7_ACTUAL_EXECUTION_SCHEMA_VERSION
    assert case["metrics"]["control_allowed_count"] == 3
    assert case["metrics"]["terminal_switch_allowed_count"] == 3
    assert case["terminal_layer_import_status"] == "available"
    assert case["terminal_layer_import_reason"] == (
        "canonical_actual_execution_five_layers_validated"
    )
    assert case["target_state_freshness"]["sample_count"] == 5
    assert case["target_state_freshness"]["stale_count"] == 0
    assert case["target_state_freshness"]["source_distribution"] == {
        "d2_estimated_global_track": 5
    }
    assert case["target_state_freshness"]["source"] == "control_commands"
    assert case["target_state_freshness"]["semantics"] == (
        D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS
    )
    freshness = evidence["target_state_freshness"]
    assert freshness["sample_count"] == 5
    assert freshness["mean_age_s"] == 0.1
    assert freshness["p95_age_s"] == 0.1
    assert freshness["max_age_s"] == 0.1
    assert freshness["stale_count"] == 0
    assert freshness["stale_rate"] == 0.0
    assert "目标状态 freshness/stale" in report
    csv_rows = list(
        csv.DictReader(
            (tmp_path / "report" / "p1_acceptance_aggregate.csv").open(
                encoding="utf-8"
            )
        )
    )
    case_row = next(
        item
        for item in csv_rows
        if item["record_type"] == "case_evidence"
        and item["source"] == "d7_terminal_execution"
    )
    assert case_row["sample_count"] == "5"
    assert case_row["stale_count"] == "0"
    assert case_row["source_distribution"] == '{"d2_estimated_global_track": 5}'
    aggregate_row = next(
        item
        for item in csv_rows
        if item["record_type"] == "target_state_freshness_aggregate"
    )
    assert aggregate_row["sample_count"] == "5"
    assert aggregate_row["stale_rate"] == "0.0"
    assert evidence["actual_execution_all_available"] is True
    assert aggregate["actual_execution_all_available"] is True
    assert aggregate["overall_acceptance_passed"] is True
    control = aggregate["terminal_layers"]["control_allowed_count"]
    assert control["status"] == "available"
    assert control["sum"] == 3
    assert control["groups"][0]["metric_scope"] == "actual_execution"
    terminal_switch = aggregate["terminal_layers"][
        "terminal_switch_allowed_count"
    ]
    assert terminal_switch["layer"] == "terminal_switch"
    assert terminal_switch["status"] == "available"
    assert terminal_switch["sum"] == 3
    assert terminal_switch["denominator_sum"] == 5
    assert terminal_switch["groups"][0]["rate"] == 0.6


def test_four_explicit_unavailable_cases_fail_overall_and_passthrough_reasons(
    tmp_path,
) -> None:
    rows = []
    for index in range(4):
        case_id = f"case-{index}"
        unavailable = _write_json(
            tmp_path / f"{case_id}-unavailable.json",
            {
                "schema": "d7-actual-execution-unavailable-v1",
                "status": "unavailable",
                "case_id": case_id,
                "reasons": [
                    "d7_actual_execution_command_physical_count_conflict"
                ],
            },
        )
        rows.append(
            {
                "case_id": case_id,
                "seed": 1,
                "actual_execution_required": True,
                "d7_execution_unavailable": str(unavailable),
                "contract_allowed_count": 99,
                "terminal_switch_allowed_count": 88,
                "terminal_metric_context": {
                    "producer": "legacy_main",
                    "metric_scope": "legacy_execution_summary",
                    "denominator": 100,
                    "lifecycle": "episode_summary",
                },
            }
        )

    aggregate, report = _generate(tmp_path, {"rows": rows})

    evidence = aggregate["d7_execution_evidence"]
    assert evidence["actual_execution_required_case_count"] == 4
    assert evidence["actual_execution_available_case_count"] == 0
    assert evidence["actual_execution_unavailable_case_count"] == 4
    assert evidence["actual_execution_all_available"] is False
    assert aggregate["overall_acceptance_passed"] is False
    assert aggregate["acceptance"]["status"] == "fail"
    assert evidence["validation_reason_counts"] == {
        "d7_actual_execution_command_physical_count_conflict": 4
    }
    assert all(
        case["canonical_artifact_kind"] == "unavailable"
        and case["canonical_unavailable_reasons"]
        == ["d7_actual_execution_command_physical_count_conflict"]
        for case in evidence["by_case_seed"]
    )
    assert aggregate["terminal_layers"]["contract_allowed_count"]["status"] == (
        "unavailable"
    )
    assert aggregate["terminal_layer_diagnostics"]["contract_allowed_count"][
        "sum"
    ] == 396
    assert aggregate["terminal_layers"]["terminal_switch_allowed_count"][
        "status"
    ] == "unavailable"
    assert aggregate["terminal_layer_diagnostics"][
        "terminal_switch_allowed_count"
    ]["sum"] == 352
    assert "actual execution" in report.lower()


def test_partial_and_all_available_actual_execution_gates(tmp_path) -> None:
    actual_dir = tmp_path / "actual-a"
    actual_dir.mkdir()
    actual_path = _write_json(
        tmp_path / "actual-a.json",
        _d7_execution(
            seed=1,
            case_id="actual-a",
            artifact_dir=actual_dir,
        ),
    )
    unavailable_path = _write_json(
        tmp_path / "actual-b-unavailable.json",
        {
            "schema": "d7-actual-execution-unavailable-v1",
            "status": "unavailable",
            "case_id": "actual-b",
            "reasons": ["actual_source_conflict"],
        },
    )
    partial, _ = _generate(
        tmp_path / "partial",
        {
            "rows": [
                {
                    "case_id": "actual-a",
                    "seed": 1,
                    "d7_execution_metrics": str(actual_path),
                },
                {
                    "case_id": "actual-b",
                    "seed": 1,
                    "d7_execution_unavailable": str(unavailable_path),
                },
            ]
        },
    )
    assert partial["actual_execution_all_available"] is False
    assert partial["d7_execution_evidence"]["status"] == "partial"
    assert partial["overall_acceptance_passed"] is False

    second_dir = tmp_path / "actual-b"
    second_dir.mkdir()
    second_path = _write_json(
        tmp_path / "actual-b.json",
        _d7_execution(
            seed=1,
            case_id="actual-b",
            artifact_dir=second_dir,
        ),
    )
    complete, _ = _generate(
        tmp_path / "complete",
        {
            "rows": [
                {
                    "case_id": "actual-a",
                    "seed": 1,
                    "d7_execution_metrics": str(actual_path),
                },
                {
                    "case_id": "actual-b",
                    "seed": 1,
                    "d7_execution_metrics": str(second_path),
                },
            ]
        },
    )
    assert complete["actual_execution_all_available"] is True
    assert complete["d7_execution_evidence"]["available_case_count"] == 2
    assert complete["overall_acceptance_passed"] is True


def test_unavailable_artifact_schema_path_and_no_adjacent_guessing(tmp_path) -> None:
    bad_schema = _write_json(
        tmp_path / "bad-unavailable.json",
        {
            "schema": "wrong-unavailable-schema",
            "status": "unavailable",
            "case_id": "bad-schema",
            "reasons": ["producer_reason"],
        },
    )
    adjacent_dir = tmp_path / "adjacent"
    adjacent_dir.mkdir()
    _write_json(
        adjacent_dir / "d7_actual_execution_metrics.json",
        _d7_execution(
            seed=2,
            case_id="missing-path",
            artifact_dir=adjacent_dir,
        ),
    )
    aggregate, _ = _generate(
        tmp_path / "bad-report",
        {
            "rows": [
                {
                    "case_id": "bad-schema",
                    "seed": 1,
                    "d7_execution_unavailable": str(bad_schema),
                },
                {
                    "case_id": "missing-path",
                    "seed": 2,
                    "d7_execution_unavailable": str(
                        adjacent_dir / "missing-unavailable.json"
                    ),
                },
            ]
        },
    )
    reasons = aggregate["d7_execution_evidence"]["validation_reason_counts"]
    assert reasons["d7_actual_execution_unavailable_schema_mismatch"] == 1
    assert reasons["d7_execution_unavailable_file_not_found"] == 1
    missing = next(
        item
        for item in aggregate["d7_execution_evidence"]["by_case_seed"]
        if item["case_id"] == "missing-path"
    )
    assert missing["canonical_artifact_kind"] == "unavailable"
    assert missing["resolved_evidence_path"] is None
    assert missing["metrics"] is None


def test_missing_case_files_are_unavailable_without_zero_fill(tmp_path) -> None:
    main = {
        "rows": [
            {
                "case_id": "missing",
                "seed": 3,
                "d3_plan_history": str(tmp_path / "missing-d3.json"),
                "d7_execution_metrics": str(tmp_path / "missing-d7.json"),
            }
        ]
    }

    aggregate, report = _generate(tmp_path, main)

    d3 = aggregate["d3_canonical_history_cases"]
    d7 = aggregate["d7_execution_evidence"]
    assert d3["status"] == "unavailable"
    assert d3["record_count"] is None
    assert d3["validation_reason_counts"] == {
        "d3_plan_history_file_not_found": 1
    }
    assert d7["status"] == "unavailable"
    assert d7["metrics"]["control_allowed_count"]["sum"] is None
    assert d7["validation_reason_counts"] == {
        "d7_execution_metrics_file_not_found": 1
    }
    assert "d7_execution_metrics_file_not_found" in report


def test_schema_mismatch_is_isolated_per_case_and_reported(tmp_path) -> None:
    bad_d3 = _history("bad", 4)
    bad_d3["schema"] = "wrong-d3-schema"
    bad_d7 = _d7_execution(seed=4, case_id="bad", artifact_dir=tmp_path)
    bad_d7["schema"] = "wrong-d7-schema"
    d3_path = _write_json(tmp_path / "bad-d3.json", bad_d3)
    d7_path = _write_json(tmp_path / "bad-d7.json", bad_d7)
    main = {
        "rows": [
            {
                "case_id": "bad",
                "seed": 4,
                "d3_plan_history": str(d3_path),
                "d7_execution_metrics": str(d7_path),
            }
        ]
    }

    aggregate, _ = _generate(tmp_path, main)

    d3 = aggregate["d3_canonical_history_cases"]
    d7 = aggregate["d7_execution_evidence"]
    assert d3["validation_reason_counts"] == {
        "history_wrapper_schema_mismatch": 1
    }
    assert d7["validation_reason_counts"] == {
        "d7_actual_execution_schema_mismatch": 1
    }
    assert d7["metrics"]["contract_allowed_count"]["sum"] is None


def test_unregistered_d7_path_has_explicit_wiring_reason(tmp_path) -> None:
    row = register_terminal_closure_case_evidence(
        {"case_id": "unwired", "seed": 9},
        d7_execution_metrics_path=None,
    )
    aggregate, report = _generate(tmp_path, {"rows": [row]})

    evidence = aggregate["d7_execution_evidence"]
    assert evidence["status"] == "unavailable"
    assert evidence["all_paths_registered"] is False
    assert evidence["wiring_reason_counts"] == {
        "d7_execution_metrics_path_not_registered_by_main": 1
    }
    case = evidence["by_case_seed"][0]
    assert case["metrics"] is None
    assert case["wiring_reason"] == (
        "d7_execution_metrics_path_not_registered_by_main"
    )
    assert "不会补零" in report


def test_integrated_replay_episode_metrics_is_not_actual_execution(tmp_path) -> None:
    replay_path = _write_json(
        tmp_path / "integrated-replay-d7.json",
        {
            "episode_id": "episode-d7",
            "seed": 1,
            "implementation_status": "implemented",
            "metric_availability": {},
            "metadata": {"offline_only": True},
            "contract_allowed_count": 40,
            "contract_evaluated_count": 330,
            "control_allowed_count": 0,
            "control_evaluated_count": 330,
            "mode_switched_count": 17,
            "physical_intercept_count": 0,
            "loop_latency_ms": 0.0,
        },
    )
    main = {
        "rows": [
            {
                "case_id": "m5n2-baseline",
                "seed": 1,
                "d7_execution_metrics": str(replay_path),
            }
        ]
    }

    aggregate, _ = _generate(tmp_path, main)

    evidence = aggregate["d7_execution_evidence"]
    assert evidence["status"] == "unavailable"
    reasons = evidence["validation_reason_counts"]
    assert reasons["d7_actual_execution_schema_missing"] == 1
    assert reasons["d7_actual_execution_stage_invalid"] == 1
    assert reasons["d7_actual_execution_metrics_not_object"] == 1
    assert evidence["metrics"]["mode_switched_count"]["sum"] is None


def test_actual_execution_mode_switch_must_not_exceed_control_allowed(
    tmp_path,
) -> None:
    payload = _d7_execution(
        seed=1,
        case_id="m5n2-candidate",
        artifact_dir=tmp_path,
    )
    payload["metrics"]["control_allowed_count"] = 0
    payload["metrics"]["mode_switched_count"] = 13
    d7_path = _write_json(tmp_path / "bad-mode.json", payload)

    aggregate, _ = _generate(
        tmp_path,
        {
            "rows": [
                {
                    "case_id": "m5n2-candidate",
                    "seed": 1,
                    "d7_execution_metrics": str(d7_path),
                }
            ]
        },
    )

    reasons = aggregate["d7_execution_evidence"]["validation_reason_counts"]
    assert reasons == {
        "d7_actual_execution_mode_switch_exceeds_control_allowed": 1
    }


def _generate(tmp_path, main: dict) -> tuple[dict, str]:
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path / "report",
        inputs=P1AcceptanceInputs(main_terminal_closure=main),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    report = outputs["markdown"].read_text(encoding="utf-8")
    return aggregate, report


def _write_json(path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _history(case_id: str, seed: int) -> dict:
    return {
        "schema": "d3_plan_history_v1",
        "schema_version": 1,
        "episode_id": case_id,
        "scenario_name": f"scenario-{case_id}",
        "seed": seed,
        "record_count": 2,
        "history": [_history_record(0, 0.0), _history_record(1, 1.0)],
    }


def _history_record(sequence_index: int, timestamp: float) -> dict:
    assignments = [
        {
            "target_id": "T1",
            "resource_id": "R1",
            "member_role": "primary",
            "activation_state": "active",
            "active": True,
            "coalition_id": "C1",
        }
    ]
    return {
        "schema": "d3_plan_history_record_v1",
        "schema_version": 1,
        "sequence_index": sequence_index,
        "ordering_key": [sequence_index, timestamp],
        "timestamp": timestamp,
        "plan_schema": "assignment_plan_v2",
        "plan_id": "plan-1",
        "plan_version": 1,
        "window_id": 1,
        "changed": False,
        "decision_state": "accepted",
        "resource_count": 1,
        "target_count": 1,
        "assigned_count": 1,
        "plan_owner": "center",
        "active_plan_owner": "center",
        "owner_node_id": "CENTER",
        "source_node_id": "CENTER",
        "selected_secondary_node_id": None,
        "secondary_plan_version": None,
        "secondary_leader_epoch": None,
        "secondary_lease_expires_at_s": None,
        "previous_plan_id": None,
        "previous_plan_version": None,
        "supersedes_plan_id": None,
        "supersedes_plan_version": None,
        "assignments": assignments,
        "coalitions": [{"coalition_id": "C1", "version": 1, "epoch": 1}],
        "hysteresis": {"state": "stable", "reason": None},
        "membership_change_records": [],
        "feedback_constraints": {"soft_count": sequence_index, "hard_count": 0},
        "total_cost": 1.0,
        "candidate_total_cost": None,
        "previous_total_cost_current": None,
        "stale_plan_rejected": False,
        "stale_reject_reason": None,
        "latest_plan_id": "plan-1",
        "latest_plan_version": 1,
        "rollback_detected": False,
        "rollback_reason": None,
        "replan_reason": None,
    }


def _d7_execution(*, seed: int, case_id: str = "case-a", artifact_dir) -> dict:
    metrics = {
        "contract_allowed_count": 4,
        "contract_evaluated_count": 5,
        "control_allowed_count": 3,
        "control_evaluated_count": 5,
        "terminal_switch_allowed_count": 3,
        "mode_switched_count": 2,
        "physical_intercept_count": 1,
        "pair_physical_success_count": 1,
        "target_intercept_success_count": 1,
        "coalition_completion_count": None,
        "truth_identity_online_use_count": 0,
        "truth_state_online_use_count": 0,
        "performance_sample_count": 5,
        "loop_latency_ms": 38.0,
        "performance_budget_violation_count": 1,
        "active_degradation_count": 1,
        "secondary_reassignment_count": 1,
        "d4_reassign_pending_count": 1,
        "terminal_lock_count": 2,
        "visual_png_switch_count": 1,
        "visual_png_control_allowed_sample_count": 2,
        "terminal_contract_reject_count": 3,
        "target_state_freshness": {
            "sample_count": 5,
            "mean_age_s": 0.1,
            "p95_age_s": 0.1,
            "max_age_s": 0.1,
            "stale_count": 0,
            "stale_rate": 0.0,
            "source_distribution": {"d2_estimated_global_track": 5},
        },
    }
    required = (
        "contract_allowed_count",
        "contract_evaluated_count",
        "control_allowed_count",
        "control_evaluated_count",
        "terminal_switch_allowed_count",
        "mode_switched_count",
        "physical_intercept_count",
        "pair_physical_success_count",
        "target_intercept_success_count",
        "performance_sample_count",
        "loop_latency_ms",
        "performance_budget_violation_count",
        "active_degradation_count",
        "secondary_reassignment_count",
        "d4_reassign_pending_count",
        "terminal_lock_count",
        "visual_png_switch_count",
        "visual_png_control_allowed_sample_count",
        "terminal_contract_reject_count",
        "truth_identity_online_use_count",
        "truth_state_online_use_count",
    )
    metrics["metric_availability"] = {
        name: {
            "status": "available",
            "source_artifact": D7_ACTUAL_EXECUTION_METRIC_SOURCES[name],
            **(
                {"semantics": D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS[name]}
                if name in D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS
                else {}
            ),
        }
        for name in required
    }
    metrics["metric_availability"]["target_state_freshness"] = {
        "status": "available",
        "source": "control_commands",
        "source_artifact": "control_commands",
        "reason": "validated persisted actual-execution source",
        "semantics": D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS,
    }
    source_artifacts = {}
    for name in (
        "control_commands",
        "intercept_summary",
        "main_episode_bus_metrics",
    ):
        path = artifact_dir / f"{name}.fixture"
        if name == "control_commands":
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=(
                        "plan_id",
                        "plan_version",
                        "d4_target_node_id",
                        "effective_control_authorized",
                        "terminal_switch_allowed",
                        "timestamp_s",
                        "target_measurement_timestamp_s",
                        "target_arrival_timestamp_s",
                        "target_measurement_age_s",
                        "target_state_stale",
                        "target_state_source",
                    ),
                )
                writer.writeheader()
                for index, allowed in enumerate((True, True, True, False, False)):
                    writer.writerow(
                        {
                            "plan_id": "actual-plan",
                            "plan_version": "7",
                            "d4_target_node_id": "d3_central",
                            "effective_control_authorized": str(allowed),
                            "terminal_switch_allowed": str(allowed),
                            "timestamp_s": str(index + 0.1),
                            "target_measurement_timestamp_s": str(index),
                            "target_arrival_timestamp_s": str(index + 0.05),
                            "target_measurement_age_s": "0.1",
                            "target_state_stale": "False",
                            "target_state_source": "d2_estimated_global_track",
                        }
                    )
        else:
            path.write_text(name, encoding="utf-8")
        source_artifacts[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return {
        "schema": D7_ACTUAL_EXECUTION_SCHEMA_VERSION,
        "episode_id": "episode-d7",
        "case_id": case_id,
        "seed": seed,
        "resource_count": 5,
        "target_count": 2,
        "producer": "main_airsim_runtime",
        "execution_stage": "post_simpleflight_control",
        "metric_scope": "actual_execution",
        "semantics_version": "d7_terminal_semantics_v2",
        "source_artifacts": source_artifacts,
        "metadata": {
            "plan_ids": ["actual-plan"],
            "plan_versions": [7],
            "owner_node_ids": ["d3_central"],
            "metadata_availability": {
                name: {
                    "status": "available",
                    "source_artifact": D7_ACTUAL_EXECUTION_METADATA_SOURCES[name],
                    "reason": "validated persisted actual-execution source",
                    "semantics": D7_ACTUAL_EXECUTION_METADATA_SEMANTICS[name],
                }
                for name in D7_ACTUAL_EXECUTION_METADATA_SOURCES
            },
        },
        "metrics": metrics,
    }
