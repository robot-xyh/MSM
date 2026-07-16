from __future__ import annotations

import csv
import json

import pytest

from d6_evaluation_metrics import (
    CASE_AWARE_SUITE_TIMING_MODE,
    P1AcceptanceInputs,
    P1AcceptanceReportGenerator,
    STAGE_TIMING_REPORT_SCHEMA_VERSION,
    StageTimingInputs,
    StageTimingReportGenerator,
    StageTimingValidationError,
    evaluate_stage_timing_inputs,
    load_stage_timing_jsonl,
    summarize_stage_timing_records,
)


MAIN_STAGES = (
    "communication",
    "d1_fusion",
    "d2_association",
    "d6_track_recording",
    "d3_assignment",
    "coalition_commit",
    "d5_terminal_association",
    "d4_arbitration",
    "d7_guidance_contract",
    "link_and_cross_view_recording",
)

CONTROL_STAGES = (
    "airsim_frame_sample",
    "bus_processing",
    "control_evidence_and_pair_sync",
    "guidance_and_control_rpc",
)


def test_valid_two_layer_input_is_aggregated_without_nested_sum(tmp_path) -> None:
    main_records = [
        _record("main_bus", 0, 0.0, overrides={"d1_fusion": 4.0}),
        _record("main_bus", 1, 0.1, overrides={"d1_fusion": 6.0}),
    ]
    control_records = [
        _record("control_tick", 0, 0.0, overrides={"bus_processing": 12.0}),
        _record("control_tick", 1, 0.1, overrides={"bus_processing": 16.0}),
    ]
    main_path = _write_jsonl(tmp_path / "stage_timings.jsonl", main_records)
    control_path = _write_jsonl(
        tmp_path / "control_tick_timings.jsonl", control_records
    )

    summary = evaluate_stage_timing_inputs(
        StageTimingInputs(main_bus=main_path, control_tick=control_path)
    )

    assert summary["schema_version"] == STAGE_TIMING_REPORT_SCHEMA_VERSION
    assert summary["availability"] == "available"
    assert summary["available_layer_count"] == 2
    assert summary["cross_layer_aggregation_prohibited"] is True
    assert summary["cross_layer_total_ms"] is None
    main = summary["layers"]["main_bus"]
    control = summary["layers"]["control_tick"]
    assert main["record_count"] == 2
    assert main["stages"]["d1_fusion"]["mean_ms"] == pytest.approx(5.0)
    assert control["record_count"] == 2
    assert control["stages"]["bus_processing"]["mean_ms"] == pytest.approx(14.0)
    assert "combined" not in summary


def test_case_aware_suite_allows_only_metadata_and_per_case_reset(tmp_path) -> None:
    records = [
        _case_record("main_bus", 0, 0.0, case_id="case-a", seed=1),
        _case_record("main_bus", 1, 0.1, case_id="case-a", seed=1),
        _case_record("main_bus", 0, 0.0, case_id="case-b", seed=2),
        _case_record("main_bus", 1, 0.1, case_id="case-b", seed=2),
    ]
    path = _write_jsonl(tmp_path / "merged.jsonl", records)

    loaded = load_stage_timing_jsonl(
        path,
        expected_layer="main_bus",
        input_mode=CASE_AWARE_SUITE_TIMING_MODE,
    )
    summary = summarize_stage_timing_records(
        loaded,
        expected_layer="main_bus",
        input_mode=CASE_AWARE_SUITE_TIMING_MODE,
    )

    assert summary["input_mode"] == CASE_AWARE_SUITE_TIMING_MODE
    assert summary["case_count"] == 2
    assert summary["record_count"] == 4
    assert summary["episode_continuity_assumed"] is False
    assert summary["pooled_across_cases"] is True
    assert summary["cross_case_total_ms"] is None
    assert summary["frame_index_first"] is None
    assert [item["record_count"] for item in summary["case_summaries"]] == [2, 2]
    assert [item["frame_index_first"] for item in summary["case_summaries"]] == [0, 0]


def test_case_aware_twenty_case_two_layer_evaluator_regression(tmp_path) -> None:
    main_path = _write_jsonl(
        tmp_path / "main_bus_stage_timings.jsonl",
        _twenty_case_suite_records("main_bus"),
    )
    control_path = _write_jsonl(
        tmp_path / "control_tick_stage_timings.jsonl",
        _twenty_case_suite_records("control_tick"),
    )

    summary = evaluate_stage_timing_inputs(
        StageTimingInputs(
            main_bus=main_path,
            control_tick=control_path,
            input_mode=CASE_AWARE_SUITE_TIMING_MODE,
        )
    )

    assert summary["availability"] == "available"
    assert summary["input_mode"] == CASE_AWARE_SUITE_TIMING_MODE
    assert summary["case_manifest_match"] is True
    assert summary["cross_case_total_ms"] is None
    assert summary["cross_layer_total_ms"] is None
    for layer in summary["layers"].values():
        assert layer["availability"] == "available"
        assert layer["case_count"] == 20
        assert layer["record_count"] == 40
        assert layer["frame_index_first"] is None
        assert all(
            item["frame_index_first"] == 0
            and item["timestamp_first_s"] == 0.0
            for item in layer["case_summaries"]
        )


def test_single_episode_strict_fields_are_not_relaxed_by_suite_support(tmp_path) -> None:
    path = _write_jsonl(
        tmp_path / "single_with_case_fields.jsonl",
        [_case_record("main_bus", 0, 0.0, case_id="case-a", seed=1)],
    )

    with pytest.raises(StageTimingValidationError, match="extra=.*case_id"):
        load_stage_timing_jsonl(path, expected_layer="main_bus")


def test_case_aware_suite_rejects_unknown_extra_and_missing_metadata(tmp_path) -> None:
    extra = _case_record("main_bus", 0, 0.0, case_id="case-a", seed=1)
    extra["episode_name"] = "not-allowed"
    path = _write_jsonl(tmp_path / "extra.jsonl", [extra])
    with pytest.raises(StageTimingValidationError, match="extra=.*episode_name"):
        load_stage_timing_jsonl(
            path,
            expected_layer="main_bus",
            input_mode=CASE_AWARE_SUITE_TIMING_MODE,
        )

    missing = _case_record("main_bus", 0, 0.0, case_id="case-a", seed=1)
    del missing["profile"]
    path = _write_jsonl(tmp_path / "missing.jsonl", [missing])
    with pytest.raises(StageTimingValidationError, match="missing=.*profile"):
        load_stage_timing_jsonl(
            path,
            expected_layer="main_bus",
            input_mode=CASE_AWARE_SUITE_TIMING_MODE,
        )


def test_case_aware_suite_rejects_reset_within_case_and_noncontiguous_case() -> None:
    reset_within_case = [
        _case_record("main_bus", 0, 0.0, case_id="case-a", seed=1),
        _case_record("main_bus", 0, 0.0, case_id="case-a", seed=1),
    ]
    with pytest.raises(StageTimingValidationError, match="within case"):
        summarize_stage_timing_records(
            reset_within_case,
            expected_layer="main_bus",
            input_mode=CASE_AWARE_SUITE_TIMING_MODE,
        )

    conflicting_metadata = [
        _case_record("main_bus", 0, 0.0, case_id="case-a", seed=1),
        _case_record("main_bus", 0, 0.0, case_id="case-a", seed=2),
    ]
    with pytest.raises(StageTimingValidationError, match="conflicting metadata"):
        summarize_stage_timing_records(
            conflicting_metadata,
            expected_layer="main_bus",
            input_mode=CASE_AWARE_SUITE_TIMING_MODE,
        )

    reappearing_case = [
        _case_record("main_bus", 0, 0.0, case_id="case-a", seed=1),
        _case_record("main_bus", 0, 0.0, case_id="case-b", seed=2),
        _case_record("main_bus", 1, 0.1, case_id="case-a", seed=1),
    ]
    with pytest.raises(StageTimingValidationError, match="reappeared"):
        summarize_stage_timing_records(
            reappearing_case,
            expected_layer="main_bus",
            input_mode=CASE_AWARE_SUITE_TIMING_MODE,
        )


def test_case_aware_nested_layers_require_same_case_manifest(tmp_path) -> None:
    main_path = _write_jsonl(
        tmp_path / "main.jsonl",
        [_case_record("main_bus", 0, 0.0, case_id="case-a", seed=1)],
    )
    control_path = _write_jsonl(
        tmp_path / "control.jsonl",
        [_case_record("control_tick", 0, 0.0, case_id="case-b", seed=2)],
    )

    with pytest.raises(StageTimingValidationError, match="manifests differ"):
        evaluate_stage_timing_inputs(
            StageTimingInputs(
                main_bus=main_path,
                control_tick=control_path,
                input_mode=CASE_AWARE_SUITE_TIMING_MODE,
            )
        )


def test_case_aware_merged_stream_rejects_mixed_timing_layers(tmp_path) -> None:
    path = _write_jsonl(
        tmp_path / "mixed_layers.jsonl",
        [
            _case_record("main_bus", 0, 0.0, case_id="case-a", seed=1),
            _case_record("control_tick", 1, 0.1, case_id="case-a", seed=1),
        ],
    )

    with pytest.raises(StageTimingValidationError, match="expected schema"):
        load_stage_timing_jsonl(
            path,
            expected_layer="main_bus",
            input_mode=CASE_AWARE_SUITE_TIMING_MODE,
        )


def test_not_applicable_and_error_statuses_keep_distinct_counts() -> None:
    skipped = _record(
        "main_bus",
        0,
        0.0,
        not_applicable={"d5_terminal_association"},
    )
    failed = _record(
        "main_bus",
        1,
        0.1,
        error_stage="d5_terminal_association",
    )

    summary = summarize_stage_timing_records(
        [skipped, failed], expected_layer="main_bus"
    )

    stage = summary["stages"]["d5_terminal_association"]
    assert stage["sample_count"] == 1
    assert stage["available_count"] == 0
    assert stage["not_applicable_count"] == 1
    assert stage["error_count"] == 1
    assert summary["error_record_count"] == 1


def test_old_artifact_without_timing_is_unavailable_and_not_zero(tmp_path) -> None:
    summary = evaluate_stage_timing_inputs(
        StageTimingInputs(
            main_bus=None,
            control_tick=tmp_path / "old_episode" / "control_tick_timings.jsonl",
        )
    )

    assert summary["availability"] == "unavailable"
    main = summary["layers"]["main_bus"]
    control = summary["layers"]["control_tick"]
    assert main["unavailable_reason"] == "stage_timing_artifact_not_provided"
    assert control["unavailable_reason"] == "stage_timing_artifact_missing"
    assert main["total"]["sample_count"] == 0
    assert main["total"]["mean_ms"] is None
    assert main["budget_violation_count"] is None


def test_bad_schema_or_scope_fails_closed(tmp_path) -> None:
    record = _record("main_bus", 0, 0.0)
    record["schema_version"] = "legacy-timing-v0"
    path = _write_jsonl(tmp_path / "bad_schema.jsonl", [record])
    with pytest.raises(StageTimingValidationError, match="expected schema"):
        load_stage_timing_jsonl(path, expected_layer="main_bus")

    record = _record("main_bus", 0, 0.0)
    record["scope"] = "simpleflight_control_tick"
    path = _write_jsonl(tmp_path / "bad_scope.jsonl", [record])
    with pytest.raises(StageTimingValidationError, match="expected scope"):
        load_stage_timing_jsonl(path, expected_layer="main_bus")


@pytest.mark.parametrize("invalid_value", (-1.0, float("nan"), float("inf")))
def test_negative_or_nonfinite_stage_duration_fails_closed(
    tmp_path, invalid_value: float
) -> None:
    record = _record("control_tick", 0, 0.0)
    record["stages_ms"]["airsim_frame_sample"] = invalid_value
    path = _write_jsonl(tmp_path / "bad_number.jsonl", [record])

    with pytest.raises(StageTimingValidationError):
        load_stage_timing_jsonl(path, expected_layer="control_tick")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("measured_stage_sum_ms", 999.0, "measured_stage_sum_ms conflicts"),
        ("total_ms", 0.0, "total_ms must be >="),
        ("unattributed_ms", 999.0, "unattributed_ms conflicts"),
    ),
)
def test_total_sum_and_unattributed_conflicts_fail_closed(
    field: str,
    value: float,
    message: str,
) -> None:
    record = _record("main_bus", 0, 0.0)
    record[field] = value

    with pytest.raises(StageTimingValidationError, match=message):
        summarize_stage_timing_records([record], expected_layer="main_bus")


@pytest.mark.parametrize(
    "mutator",
    (
        lambda record: record["stage_status"].__setitem__(
            "communication", "not_applicable"
        ),
        lambda record: record["stages_ms"].__setitem__("communication", None),
        lambda record: record.update(error_type="RuntimeError"),
    ),
)
def test_stage_status_conflicts_fail_closed(mutator) -> None:
    record = _record("main_bus", 0, 0.0)
    mutator(record)

    with pytest.raises(StageTimingValidationError):
        summarize_stage_timing_records([record], expected_layer="main_bus")


@pytest.mark.parametrize(
    ("first_frame", "first_timestamp", "second_frame", "second_timestamp"),
    (
        (1, 0.1, 1, 0.2),
        (2, 0.1, 1, 0.2),
        (1, 0.1, 2, 0.1),
        (1, 0.2, 2, 0.1),
    ),
)
def test_duplicate_or_out_of_order_frame_and_timestamp_fail_closed(
    first_frame: int,
    first_timestamp: float,
    second_frame: int,
    second_timestamp: float,
) -> None:
    records = [
        _record("main_bus", first_frame, first_timestamp),
        _record("main_bus", second_frame, second_timestamp),
    ]
    with pytest.raises(StageTimingValidationError, match="duplicate or out-of-order"):
        summarize_stage_timing_records(records, expected_layer="main_bus")


def test_budget_flag_conflict_fails_closed() -> None:
    record = _record("control_tick", 0, 0.0, budget_ms=1.0)
    assert record["budget_exceeded"] is True
    record["budget_exceeded"] = False

    with pytest.raises(StageTimingValidationError, match="budget_exceeded conflicts"):
        summarize_stage_timing_records([record], expected_layer="control_tick")


def test_budget_violation_dominant_stage_and_report_outputs(tmp_path) -> None:
    main_path = _write_jsonl(
        tmp_path / "stage_timings.jsonl",
        [
            _record(
                "main_bus",
                0,
                0.0,
                budget_ms=10.0,
                overrides={"d1_fusion": 15.0},
            ),
            _record(
                "main_bus",
                1,
                0.1,
                budget_ms=100.0,
                overrides={"d1_fusion": 10.0},
            ),
        ],
    )

    outputs = StageTimingReportGenerator().write_report_bundle(
        tmp_path / "report",
        inputs=StageTimingInputs(main_bus=main_path),
    )

    assert set(outputs) == {"csv", "json", "markdown", "plot"}
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs.values())
    payload = json.loads(outputs["json"].read_text(encoding="utf-8"))
    layer = payload["layers"]["main_bus"]
    assert layer["budget_violation_count"] == 1
    assert layer["budget_violation_rate"] == pytest.approx(0.5)
    assert layer["dominant_stage"] == "d1_fusion"
    rows = list(csv.DictReader(outputs["csv"].open(encoding="utf-8")))
    assert any(
        row["layer"] == "main_bus"
        and row["row_type"] == "stage"
        and row["stage_name"] == "d1_fusion"
        for row in rows
    )
    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "两层同名或嵌套耗时禁止相加" in report
    assert "真实 AirSim 同配置多 seed 的 100 ms" in report


def test_p1_acceptance_consumes_optional_stage_timing_inputs(tmp_path) -> None:
    main_path = _write_jsonl(
        tmp_path / "stage_timings.jsonl",
        [_record("main_bus", 0, 0.0, overrides={"d3_assignment": 8.0})],
    )
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path / "p1",
        inputs=P1AcceptanceInputs(main_stage_timings=main_path),
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    timing = aggregate["stage_timing"]
    assert timing["layers"]["main_bus"]["availability"] == "available"
    assert timing["layers"]["control_tick"]["availability"] == "unavailable"
    assert timing["cross_layer_total_ms"] is None
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "分阶段延迟证据" in markdown
    assert "两层不相加" in markdown


def test_p1_acceptance_accepts_explicit_case_aware_timing_envelope(tmp_path) -> None:
    main_path = _write_jsonl(
        tmp_path / "merged_main.jsonl",
        [
            _case_record("main_bus", 0, 0.0, case_id="case-a", seed=1),
            _case_record("main_bus", 0, 0.0, case_id="case-b", seed=2),
        ],
    )
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        tmp_path / "p1-suite",
        inputs=P1AcceptanceInputs(
            main_stage_timings=main_path,
            stage_timing_input_mode=CASE_AWARE_SUITE_TIMING_MODE,
        ),
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    timing = aggregate["stage_timing"]
    assert timing["input_mode"] == CASE_AWARE_SUITE_TIMING_MODE
    assert timing["layers"]["main_bus"]["case_count"] == 2
    assert timing["cross_case_total_ms"] is None
    assert timing["cross_layer_total_ms"] is None
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "不跨 case 拼接伪连续 episode" in markdown


def _record(
    layer: str,
    frame_index: int,
    timestamp_s: float,
    *,
    budget_ms: float = 100.0,
    overrides: dict[str, float] | None = None,
    not_applicable: set[str] | None = None,
    error_stage: str | None = None,
) -> dict:
    if layer == "main_bus":
        schema_version = "main-stage-timing-v1"
        scope = "main_episode_bus"
        total_stage_name = "bus_total"
        stage_names = MAIN_STAGES
    elif layer == "control_tick":
        schema_version = "control-tick-stage-timing-v1"
        scope = "simpleflight_control_tick"
        total_stage_name = "control_tick_total"
        stage_names = CONTROL_STAGES
    else:
        raise AssertionError(layer)
    stages_ms: dict[str, float | None] = {name: 1.0 for name in stage_names}
    stages_ms.update(overrides or {})
    stage_status = {name: "available" for name in stage_names}
    for name in not_applicable or set():
        stages_ms[name] = None
        stage_status[name] = "not_applicable"
    if error_stage is not None:
        stage_status[error_stage] = "error"
    measured_sum_ms = sum(value for value in stages_ms.values() if value is not None)
    unattributed_ms = 2.0
    total_ms = measured_sum_ms + unattributed_ms
    return {
        "schema_version": schema_version,
        "scope": scope,
        "frame_index": frame_index,
        "timestamp_s": timestamp_s,
        "budget_ms": budget_ms,
        "total_stage_name": total_stage_name,
        "stages_ms": stages_ms,
        "stage_status": stage_status,
        "measured_stage_sum_ms": measured_sum_ms,
        "unattributed_ms": unattributed_ms,
        "total_ms": total_ms,
        "budget_exceeded": total_ms > budget_ms,
        "error_type": "RuntimeError" if error_stage is not None else "",
        "error_message": "fixture failure" if error_stage is not None else "",
    }


def _case_record(
    layer: str,
    frame_index: int,
    timestamp_s: float,
    *,
    case_id: str,
    seed: int,
) -> dict:
    return {
        **_record(layer, frame_index, timestamp_s),
        "case_id": case_id,
        "family": "m5n2_paired",
        "profile": "baseline" if seed == 1 else "candidate",
        "seed": seed,
    }


def _twenty_case_suite_records(layer: str) -> list[dict]:
    records: list[dict] = []
    for profile, role in (
        ("baseline", "baseline"),
        ("candidate_soft_prediction_trend_coast", "candidate"),
    ):
        for seed in range(1, 11):
            case_id = f"m5n2_{role}_seed{seed:03d}"
            for frame_index, timestamp_s in ((0, 0.0), (1, 0.1)):
                record = _case_record(
                    layer,
                    frame_index,
                    timestamp_s,
                    case_id=case_id,
                    seed=seed,
                )
                record["profile"] = profile
                records.append(record)
    return records


def _write_jsonl(path, records: list[dict]):
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return path
