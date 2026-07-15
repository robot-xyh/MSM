from __future__ import annotations

import csv
from dataclasses import fields
import json

import pytest

from d6_evaluation_metrics import (
    ActualExecutionEvidenceError,
    D7_ACTUAL_EXECUTION_SCHEMA_VERSION,
    EpisodeMetrics,
    ReportGenerator,
    build_d7_actual_execution_evidence,
    merge_replay_with_execution_metrics,
    validate_d7_actual_execution_payload,
    write_d7_actual_execution_evidence,
)


def test_builder_and_writer_publish_valid_actual_execution(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)

    payload = build_d7_actual_execution_evidence(commands, summary, main)

    assert payload["schema"] == D7_ACTUAL_EXECUTION_SCHEMA_VERSION
    assert payload["case_id"] == "case-positive"
    assert payload["metrics"]["contract_allowed_count"] == 2
    assert payload["metrics"]["control_allowed_count"] == 1
    assert payload["metrics"]["terminal_switch_allowed_count"] == 1
    assert payload["metrics"]["mode_switched_count"] == 1
    assert payload["metrics"]["physical_intercept_count"] == 1
    assert payload["metrics"]["performance_sample_count"] == 3
    assert payload["metrics"]["loop_latency_ms"] == 20.0
    assert payload["metrics"]["active_degradation_count"] == 1
    assert payload["metrics"]["secondary_reassignment_count"] == 1
    assert payload["metrics"]["d4_reassign_pending_count"] == 1
    assert payload["metrics"]["terminal_lock_count"] == 1
    assert payload["metrics"]["visual_png_switch_count"] == 1
    assert payload["metrics"]["visual_png_control_allowed_sample_count"] == 1
    assert payload["metrics"]["terminal_contract_reject_count"] == 1
    assert payload["metrics"]["truth_identity_online_use_count"] == 0
    assert payload["metrics"]["truth_state_online_use_count"] == 0
    assert payload["metrics"]["target_state_freshness"] == {
        "sample_count": 3,
        "mean_age_s": 0.0,
        "p95_age_s": 0.0,
        "max_age_s": 0.0,
        "stale_count": 0,
        "stale_rate": 0.0,
        "source_distribution": {"d2_estimated_global_track": 3},
    }
    freshness_availability = payload["metrics"]["metric_availability"][
        "target_state_freshness"
    ]
    assert freshness_availability["status"] == "available"
    assert freshness_availability["source"] == "control_commands"
    assert freshness_availability["source_artifact"] == "control_commands"
    assert "measurement_age_stale_and_source" in freshness_availability[
        "semantics"
    ]
    assert payload["metrics"]["metric_availability"]["visual_png_switch_count"][
        "semantics"
    ] == "effective_control_authorized_visual_transition"
    assert payload["metrics"]["metric_availability"][
        "terminal_switch_allowed_count"
    ]["source_artifact"] == "control_commands"
    assert payload["metadata"]["raw_mode_switched_count"] == 2
    assert payload["metadata"]["actual_mode_switched_count"] == 1
    assert payload["metadata"]["plan_ids"] == ["plan-1"]
    assert payload["metadata"]["plan_versions"] == [1]
    assert payload["metadata"]["owner_node_ids"] == ["d3_central"]
    assert payload["metadata"]["metadata_availability"]["plan_ids"] == {
        "status": "available",
        "source_artifact": "control_commands",
        "reason": "validated persisted actual-execution source",
        "semantics": "distinct_persisted_control_command_plan_id",
    }
    assert all(
        len(item["sha256"]) == 64
        for item in payload["source_artifacts"].values()
    )
    validation = validate_d7_actual_execution_payload(
        payload,
        expected_seed=7,
        expected_case_id="case-positive",
        verify_source_hashes=True,
    )
    assert validation["status"] == "available"

    output = write_d7_actual_execution_evidence(
        tmp_path / "actual_execution.json",
        commands,
        summary,
        main,
    )
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted == payload


def test_builder_rejects_zero_performance_samples_without_writing(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path, performance_samples=0)
    output = tmp_path / "must-not-exist.json"

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        write_d7_actual_execution_evidence(
            output,
            commands,
            summary,
            main,
        )

    assert "d7_actual_execution_performance_samples_missing" in exc_info.value.reasons
    assert not output.exists()


def test_builder_rejects_main_and_command_mode_conflict(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path, main_mode_switched_count=2)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert "d7_actual_execution_main_mode_switched_count_conflict" in (
        exc_info.value.reasons
    )


def test_builder_rejects_effective_control_source_conflict(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[1]["terminal_control_allowed"] = "False"
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert "d7_actual_execution_control_source_conflict" in exc_info.value.reasons


def test_builder_reads_independent_terminal_switch_column(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[0]["terminal_switch_allowed"] = "not-a-boolean"
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert (
        "d7_actual_execution_control_boolean_invalid:terminal_switch_allowed:row0"
        in exc_info.value.reasons
    )


def test_builder_rejects_terminal_switch_source_conflict(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[0]["terminal_switch_allowed"] = "True"
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert "d7_actual_execution_terminal_switch_source_conflict" in (
        exc_info.value.reasons
    )


def test_builder_rejects_missing_execution_identity_column(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    for row in rows:
        row.pop("d4_target_node_id")
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert "d7_actual_execution_control_column_missing:d4_target_node_id" in (
        exc_info.value.reasons
    )


@pytest.mark.parametrize(
    "field",
    (
        "timestamp_s",
        "target_measurement_timestamp_s",
        "target_arrival_timestamp_s",
        "target_measurement_age_s",
        "target_state_stale",
        "target_state_source",
    ),
)
def test_builder_rejects_missing_target_state_freshness_column(
    tmp_path, field: str
) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    for row in rows:
        row.pop(field)
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert f"d7_actual_execution_control_column_missing:{field}" in (
        exc_info.value.reasons
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        (
            "timestamp_s",
            "-0.1",
            "d7_actual_execution_timestamp_invalid:row0",
        ),
        (
            "target_measurement_timestamp_s",
            "",
            "d7_actual_execution_target_measurement_timestamp_invalid:row0",
        ),
        (
            "target_measurement_timestamp_s",
            "nan",
            "d7_actual_execution_target_measurement_timestamp_invalid:row0",
        ),
        (
            "target_measurement_timestamp_s",
            "-0.1",
            "d7_actual_execution_target_measurement_timestamp_invalid:row0",
        ),
        (
            "target_arrival_timestamp_s",
            "inf",
            "d7_actual_execution_target_arrival_timestamp_invalid:row0",
        ),
        (
            "target_arrival_timestamp_s",
            "-0.1",
            "d7_actual_execution_target_arrival_timestamp_invalid:row0",
        ),
        (
            "target_measurement_age_s",
            "nan",
            "d7_actual_execution_target_measurement_age_invalid:row0",
        ),
        (
            "target_measurement_age_s",
            "-0.1",
            "d7_actual_execution_target_measurement_age_invalid:row0",
        ),
        (
            "target_state_stale",
            "0",
            "d7_actual_execution_target_state_stale_boolean_invalid:row0",
        ),
        (
            "target_state_source",
            " ",
            "d7_actual_execution_target_state_source_missing:row0",
        ),
    ),
)
def test_builder_rejects_invalid_target_state_freshness_value(
    tmp_path, field: str, value: str, reason: str
) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[0][field] = value
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert reason in exc_info.value.reasons


@pytest.mark.parametrize(
    ("updates", "reason"),
    (
        (
            {
                "timestamp_s": "0.2",
                "target_measurement_timestamp_s": "0.15",
                "target_arrival_timestamp_s": "0.1",
                "target_measurement_age_s": "0.05",
            },
            "d7_actual_execution_target_measurement_arrival_order_conflict:row0",
        ),
        (
            {
                "timestamp_s": "0.2",
                "target_measurement_timestamp_s": "0.1",
                "target_arrival_timestamp_s": "0.3",
                "target_measurement_age_s": "0.1",
            },
            "d7_actual_execution_target_arrival_control_order_conflict:row0",
        ),
    ),
)
def test_builder_rejects_target_state_time_conflict(
    tmp_path, updates: dict[str, str], reason: str
) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[0].update(updates)
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert reason in exc_info.value.reasons


def test_builder_rejects_target_measurement_age_conflict(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[1].update(
        {
            "target_measurement_timestamp_s": "0.0",
            "target_arrival_timestamp_s": "0.05",
            "target_measurement_age_s": "0.2",
        }
    )
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert "d7_actual_execution_target_measurement_age_conflict:row1" in (
        exc_info.value.reasons
    )


def test_explicit_zero_stale_is_available_not_zero_filled(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)

    payload = build_d7_actual_execution_evidence(commands, summary, main)

    freshness = payload["metrics"]["target_state_freshness"]
    assert freshness["sample_count"] == 3
    assert freshness["stale_count"] == 0
    assert freshness["stale_rate"] == 0.0
    assert payload["metrics"]["metric_availability"][
        "target_state_freshness"
    ]["status"] == "available"


def test_real_positive_stale_and_source_distribution_are_preserved(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[2].update(
        {
            "target_measurement_timestamp_s": "0.0",
            "target_arrival_timestamp_s": "0.1",
            "target_measurement_age_s": "0.2",
            "target_state_stale": "True",
            "target_state_source": "d1_fused_global_track",
        }
    )
    _write_command_rows(commands, rows)

    payload = build_d7_actual_execution_evidence(commands, summary, main)

    freshness = payload["metrics"]["target_state_freshness"]
    assert freshness["sample_count"] == 3
    assert freshness["mean_age_s"] == pytest.approx(0.2 / 3.0)
    assert freshness["p95_age_s"] == pytest.approx(0.18)
    assert freshness["max_age_s"] == pytest.approx(0.2)
    assert freshness["stale_count"] == 1
    assert freshness["stale_rate"] == pytest.approx(1.0 / 3.0)
    assert freshness["source_distribution"] == {
        "d1_fused_global_track": 1,
        "d2_estimated_global_track": 2,
    }


def test_builder_rejects_non_integer_plan_version(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[1]["plan_version"] = "1.5"
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert "d7_actual_execution_plan_version_invalid:row1" in exc_info.value.reasons


def test_builder_accepts_distinct_plan_versions_and_deduplicates(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    for row in rows[1:]:
        row["plan_id"] = "plan-2"
        row["plan_version"] = "2"
        row["d4_target_node_id"] = "secondary-node"
    _write_command_rows(commands, rows)

    payload = build_d7_actual_execution_evidence(commands, summary, main)

    assert payload["metadata"]["plan_ids"] == ["plan-1", "plan-2"]
    assert payload["metadata"]["plan_versions"] == [1, 2]
    assert payload["metadata"]["owner_node_ids"] == [
        "d3_central",
        "secondary-node",
    ]


def test_builder_accepts_empty_center_owner_before_secondary_owner(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    for row in rows[:2]:
        row["d4_target_node_id"] = ""
        row["terminal_control_allowed"] = "False"
        row["effective_control_authorized"] = "False"
        row["terminal_switch_allowed"] = "False"
        row["mode_switched"] = "False"
        row["physical_intercept"] = "False"
        row["d4_action"] = "continue_center"
        row["d4_mode"] = "none"
        row["assignment_phase"] = "center_initial"
        row["d5_decision_state"] = "reacquire"
        row["guidance_law"] = "radar_pn"
        row["mode"] = "radar_midcourse"
    rows[2].update(
        {
            "plan_id": "secondary-plan",
            "plan_version": "2",
            "d4_target_node_id": "SEC-01",
            "terminal_contract_allowed": "True",
            "effective_terminal_contract_allowed": "True",
            "terminal_control_allowed": "True",
            "effective_control_authorized": "True",
            "terminal_switch_allowed": "True",
            "mode_switched": "True",
            "physical_intercept": "True",
            "d4_action": "request_secondary_assist",
            "d4_mode": "active_degradation",
            "assignment_phase": "secondary_reassignment",
            "d5_decision_state": "locked",
            "guidance_law": "png_vm",
            "mode": "vision_terminal",
            "terminal_contract_reject_reason": "",
        }
    )
    _write_command_rows(commands, rows)

    payload = build_d7_actual_execution_evidence(commands, summary, main)

    assert payload["metadata"]["plan_ids"] == ["plan-1", "secondary-plan"]
    assert payload["metadata"]["plan_versions"] == [1, 2]
    assert payload["metadata"]["owner_node_ids"] == ["SEC-01"]
    assert payload["metadata"]["metadata_availability"]["owner_node_ids"][
        "status"
    ] == "available"


def test_builder_accepts_missing_owner_on_authorized_center_row(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[1]["d4_target_node_id"] = ""
    rows[1]["d4_action"] = "continue_center"
    rows[1]["d4_mode"] = "none"
    rows[1]["assignment_phase"] = "center_active"
    _write_command_rows(commands, rows)

    payload = build_d7_actual_execution_evidence(commands, summary, main)

    assert payload["metadata"]["owner_node_ids"] == ["d3_central"]
    assert payload["metadata"]["metadata_availability"]["owner_node_ids"][
        "status"
    ] == "available"


def test_builder_rejects_missing_owner_on_effective_authorized_secondary_row(
    tmp_path,
) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[1]["d4_target_node_id"] = ""
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert "d7_actual_execution_owner_node_id_missing:row1" in (
        exc_info.value.reasons
    )


def test_builder_marks_owner_unavailable_when_no_execution_requires_it(
    tmp_path,
) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    for row in rows:
        row["d4_target_node_id"] = ""
        row["terminal_control_allowed"] = "False"
        row["effective_control_authorized"] = "False"
        row["terminal_switch_allowed"] = "False"
        row["mode_switched"] = "False"
        row["physical_intercept"] = "False"
        row["d4_action"] = "continue_center"
        row["d4_mode"] = "none"
        row["assignment_phase"] = "center_initial"
        row["d5_decision_state"] = "reacquire"
        row["guidance_law"] = "radar_pn"
        row["mode"] = "radar_midcourse"
        row["terminal_contract_reject_reason"] = ""
    _write_command_rows(commands, rows)

    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    summary_payload.update(
        {
            "success_count": 0,
            "pair_physical_success_count": 0,
            "target_intercept_success_count": 0,
        }
    )
    summary.write_text(json.dumps(summary_payload), encoding="utf-8")
    main_payload = json.loads(main.read_text(encoding="utf-8"))
    main_payload["metrics"].update(
        {
            "control_allowed_count": 0,
            "mode_switched_count": 0,
            "physical_intercept_count": 0,
        }
    )
    main.write_text(json.dumps(main_payload), encoding="utf-8")

    payload = build_d7_actual_execution_evidence(commands, summary, main)

    assert payload["metadata"]["owner_node_ids"] == []
    owner_availability = payload["metadata"]["metadata_availability"][
        "owner_node_ids"
    ]
    assert owner_availability["status"] == "unavailable"
    assert owner_availability["source_artifact"] == "control_commands"
    assert "no authoritative owner observed" in owner_availability["reason"]


def test_builder_rejects_same_plan_id_with_mixed_versions(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[1]["plan_version"] = "2"
    _write_command_rows(commands, rows)

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert "d7_actual_execution_plan_version_conflict:plan-1" in (
        exc_info.value.reasons
    )


def test_builder_publishes_truth_identity_and_state_safety_counts(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    rows[0]["truth_identity_online_use"] = "True"
    _write_command_rows(commands, rows)

    payload = build_d7_actual_execution_evidence(commands, summary, main)

    assert payload["metrics"]["truth_identity_online_use_count"] == 1
    assert payload["metrics"]["truth_state_online_use_count"] == 0
    availability = payload["metrics"]["metric_availability"]
    assert availability["truth_identity_online_use_count"] == {
        "status": "available",
        "source_artifact": "control_commands",
        "reason": "validated persisted actual-execution source",
        "semantics": "persisted_command_truth_identity_use_sample",
    }
    assert availability["truth_state_online_use_count"]["source_artifact"] == (
        "intercept_summary"
    )


def test_visual_png_switch_is_transition_not_authorized_sample(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    rows = list(csv.DictReader(commands.open(newline="", encoding="utf-8")))
    repeated_visual = dict(rows[1])
    repeated_visual["timestamp_s"] = "0.15"
    repeated_visual["target_measurement_timestamp_s"] = "0.15"
    repeated_visual["target_arrival_timestamp_s"] = "0.15"
    repeated_visual["physical_intercept"] = "False"
    rows.insert(2, repeated_visual)
    _write_command_rows(commands, rows)

    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    summary_payload["record_count"] = 4
    summary.write_text(json.dumps(summary_payload), encoding="utf-8")

    main_payload = json.loads(main.read_text(encoding="utf-8"))
    main_payload["metrics"]["control_allowed_count"] = 2
    main_payload["metrics"]["mode_switched_count"] = 2
    main_payload["metrics"]["metadata"]["clock"]["frame_count"] = 4
    main_payload["metadata"]["record_counts"]["ticks"] = 4
    main.write_text(json.dumps(main_payload), encoding="utf-8")

    payload = build_d7_actual_execution_evidence(commands, summary, main)

    assert payload["metrics"]["visual_png_switch_count"] == 1
    assert payload["metrics"]["visual_png_control_allowed_sample_count"] == 2
    assert payload["metrics"]["terminal_lock_count"] == 1
    assert payload["metrics"]["active_degradation_count"] == 1


def test_validator_rejects_diagnostic_semantics_conflict(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    payload = build_d7_actual_execution_evidence(commands, summary, main)
    payload["metrics"]["metric_availability"]["visual_png_switch_count"][
        "semantics"
    ] = "effective_control_authorized_visual_sample"

    validation = validate_d7_actual_execution_payload(payload)

    assert validation["status"] == "unavailable"
    assert "d7_actual_execution_metric_semantics_invalid:visual_png_switch_count" in (
        validation["validation_reasons"]
    )


def test_validator_rejects_missing_terminal_switch_allowed_count(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    payload = build_d7_actual_execution_evidence(commands, summary, main)
    payload["metrics"].pop("terminal_switch_allowed_count")

    validation = validate_d7_actual_execution_payload(payload)

    assert validation["status"] == "unavailable"
    assert (
        "d7_actual_execution_invalid_count:terminal_switch_allowed_count"
        in validation["validation_reasons"]
    )


def test_validator_rejects_terminal_switch_count_source_conflict(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    payload = build_d7_actual_execution_evidence(commands, summary, main)
    payload["metrics"]["terminal_switch_allowed_count"] = 0

    validation = validate_d7_actual_execution_payload(
        payload,
        verify_source_hashes=True,
    )

    assert validation["status"] == "unavailable"
    assert (
        "d7_actual_execution_metric_source_conflict:terminal_switch_allowed_count"
        in validation["validation_reasons"]
    )


def test_validator_recomputes_freshness_from_hashed_csv(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    payload = build_d7_actual_execution_evidence(commands, summary, main)
    payload["metrics"]["target_state_freshness"].update(
        {
            "mean_age_s": 0.1,
            "p95_age_s": 0.1,
            "max_age_s": 0.1,
        }
    )

    validation = validate_d7_actual_execution_payload(
        payload,
        verify_source_hashes=True,
    )

    assert validation["status"] == "unavailable"
    assert (
        "d7_actual_execution_metric_source_conflict:target_state_freshness"
        in validation["validation_reasons"]
    )


def test_validator_rejects_execution_identity_provenance_conflict(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    payload = build_d7_actual_execution_evidence(commands, summary, main)
    payload["metadata"]["metadata_availability"]["plan_ids"][
        "semantics"
    ] = "replay_inferred_plan_id"

    validation = validate_d7_actual_execution_payload(payload)

    assert validation["status"] == "unavailable"
    assert "d7_actual_execution_metadata_semantics_invalid:plan_ids" in (
        validation["validation_reasons"]
    )


def test_validator_rejects_metadata_not_matching_hashed_csv(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    payload = build_d7_actual_execution_evidence(commands, summary, main)
    payload["metadata"]["plan_ids"] = ["forged-plan"]

    validation = validate_d7_actual_execution_payload(
        payload,
        verify_source_hashes=True,
    )

    assert validation["status"] == "unavailable"
    assert "d7_actual_execution_metadata_source_conflict:plan_ids" in (
        validation["validation_reasons"]
    )


def test_builder_rejects_unfinalized_main_bus(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    payload = json.loads(main.read_text(encoding="utf-8"))
    payload["metadata"]["main_episode_bus_execution_metrics_merged"] = False
    main.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ActualExecutionEvidenceError) as exc_info:
        build_d7_actual_execution_evidence(commands, summary, main)

    assert "d7_actual_execution_main_bus_not_finalized" in exc_info.value.reasons


def test_validator_rejects_tampered_source_hash(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    payload = build_d7_actual_execution_evidence(commands, summary, main)
    commands.write_text(commands.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    validation = validate_d7_actual_execution_payload(
        payload,
        verify_source_hashes=True,
    )

    assert validation["status"] == "unavailable"
    assert "d7_actual_execution_artifact_hash_mismatch:control_commands" in (
        validation["validation_reasons"]
    )


def test_report_renders_unavailable_after_canonical_merge(tmp_path) -> None:
    commands, summary, main = _write_sources(tmp_path)
    actual = build_d7_actual_execution_evidence(commands, summary, main)
    merged = merge_replay_with_execution_metrics(
        {
            "metrics": {
                "episode_id": "episode-positive",
                "seed": 7,
                "scenario_group": "actual-envelope",
                "resource_count": 2,
                "target_count": 1,
                "mode_switch_count": 99,
                "terminal_contract_reject_count": 99,
            }
        },
        actual,
    )["metrics"]
    values = {
        field.name: merged[field.name]
        for field in fields(EpisodeMetrics)
        if field.name in merged
    }
    values["mode_switch_count"] = None
    values["active_degradation_label_count"] = None
    values["unnecessary_active_degradation_count"] = None
    values["passive_failover_count"] = None
    values["cpu_budget_utilization"] = None
    values["gpu_budget_utilization"] = None
    episode = EpisodeMetrics(**values)

    report_path = ReportGenerator().write_markdown_report(
        [episode],
        tmp_path / "report.md",
    )

    report = report_path.read_text(encoding="utf-8")
    assert "unavailable" in report
    assert "actual-envelope" in report
    assert "| 1 |" in report or "| 1 " in report


def _write_sources(
    tmp_path,
    *,
    performance_samples: int = 3,
    main_mode_switched_count: int = 1,
):
    commands = tmp_path / "control_commands.csv"
    rows = [
        _command_row(
            0.0,
            contract=True,
            control=False,
            switched=False,
            physical=False,
            d4_mode="none",
            d4_action="continue_center",
            assignment_phase="",
            d5_state="reacquire",
            guidance_law="radar_pn",
            mode="radar_midcourse",
        ),
        _command_row(
            0.1,
            contract=True,
            control=True,
            switched=True,
            physical=True,
            d4_mode="active_degradation",
            d4_action="hold_for_review",
            assignment_phase="secondary_reassignment",
            d5_state="locked",
            guidance_law="png_vm",
            mode="vision_terminal",
        ),
        _command_row(
            0.2,
            contract=False,
            control=False,
            switched=True,
            physical=False,
            d4_mode="none",
            d4_action="request_center_replan",
            assignment_phase="secondary_reassignment_pending",
            d5_state="reacquire",
            guidance_law="radar_pn",
            mode="radar_midcourse",
            reject_reason="d4_reassign_pending",
        ),
    ]
    _write_command_rows(commands, rows)

    summary = tmp_path / "intercept_summary.json"
    summary.write_text(
        json.dumps(
            {
                "control_api_used": True,
                "runtime_mode": "SimpleFlight",
                "record_count": 3,
                "physical_intercept_available": True,
                "success_count": 1,
                "pair_physical_success_count": 1,
                "target_intercept_success_count": 1,
                "truth_state_online_use_count": 0,
            }
        ),
        encoding="utf-8",
    )

    main = tmp_path / "main_episode_bus_metrics.json"
    main.write_text(
        json.dumps(
            {
                "metrics": {
                    "episode_id": "episode-positive",
                    "seed": 7,
                    "resource_count": 2,
                    "target_count": 1,
                    "control_allowed_count": 1,
                    "mode_switched_count": main_mode_switched_count,
                    "physical_intercept_count": 1,
                    "loop_latency_ms": 20.0,
                    "performance_budget_violation_count": min(
                        1, performance_samples
                    ),
                    "metadata": {
                        "clock": {
                            "frame_count": performance_samples,
                            "mean_processing_duration_s": 0.02,
                        },
                        "scenario_config": {
                            "metadata": {"case_id": "case-positive"}
                        },
                    },
                },
                "metadata": {
                    "main_episode_bus_execution_metrics_merged": True,
                    "record_counts": {"ticks": performance_samples},
                },
            }
        ),
        encoding="utf-8",
    )
    return commands, summary, main


def _command_row(
    timestamp: float,
    *,
    contract: bool,
    control: bool,
    switched: bool,
    physical: bool,
    d4_mode: str,
    d4_action: str,
    assignment_phase: str,
    d5_state: str,
    guidance_law: str,
    mode: str,
    reject_reason: str = "",
) -> dict[str, str]:
    return {
        "timestamp_s": str(timestamp),
        "resource_id": "INT-01",
        "target_id": "T001",
        "terminal_contract_allowed": str(contract),
        "effective_terminal_contract_allowed": str(contract),
        "terminal_control_allowed": str(control),
        "effective_control_authorized": str(control),
        "terminal_switch_allowed": str(control),
        "terminal_semantics_version": "d7_terminal_semantics_v2",
        "mode_switched": str(switched),
        "physical_intercept": str(physical),
        "d4_action": d4_action,
        "d4_mode": d4_mode,
        "assignment_phase": assignment_phase,
        "d5_decision_state": d5_state,
        "terminal_locked": "False",
        "guidance_law": guidance_law,
        "mode": mode,
        "terminal_contract_reject_reason": reject_reason,
        "truth_identity_online_use": "False",
        "truth_state_online_use": "False",
        "plan_id": "plan-1",
        "plan_version": "1",
        "d4_target_node_id": "d3_central",
        "target_measurement_timestamp_s": str(timestamp),
        "target_arrival_timestamp_s": str(timestamp),
        "target_measurement_age_s": "0.0",
        "target_state_stale": "False",
        "target_state_source": "d2_estimated_global_track",
    }


def _write_command_rows(path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
