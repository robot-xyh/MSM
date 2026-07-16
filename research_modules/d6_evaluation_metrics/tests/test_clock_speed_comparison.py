from __future__ import annotations

from copy import deepcopy
import csv
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    CLOCK_SPEED_COMPARISON_SCHEMA_VERSION,
    ClockSpeedComparisonReportGenerator,
    ClockSpeedComparisonValidationError,
    compare_clock_speed_suites,
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


def test_three_suites_are_strictly_paired_and_clock_normalized(tmp_path: Path) -> None:
    suites = [_suite(tmp_path, speed) for speed in (1.0, 0.2, 0.1)]

    summary = compare_clock_speed_suites(suites)

    assert summary["schema_version"] == CLOCK_SPEED_COMPARISON_SCHEMA_VERSION
    assert summary["total_case_count"] == 60
    assert summary["pairing"] == {
        "availability": "available",
        "key_fields": ["case_id", "profile", "seed"],
        "paired_case_count": 20,
        "clock_speed_count_per_pair": 3,
    }
    assert summary["timing_contract"]["cross_layer_total_ms"] is None
    assert summary["truth_audit"]["identity"]["all_zero"] is True
    assert summary["truth_audit"]["state"]["all_zero"] is True

    baseline_01 = next(
        row
        for row in summary["aggregates"]
        if row["clock_speed"] == 0.1 and row["profile"] == "baseline"
    )
    assert baseline_01["metrics"]["active_primary_pair_success_rate"][
        "denominator"
    ] == 30
    assert baseline_01["metrics"]["second_primary_5m_success_rate"][
        "numerator"
    ] == 5
    assert baseline_01["metrics"]["main_bus_wall_mean_ms"]["value"] == 10.0
    assert baseline_01["metrics"]["control_tick_wall_mean_ms"]["value"] == 100.0
    assert baseline_01["metrics"]["simulated_time_per_tick_s"][
        "value"
    ] == pytest.approx(0.01)


def test_report_bundle_writes_json_two_csv_chinese_markdown_and_plot(
    tmp_path: Path,
) -> None:
    outputs = ClockSpeedComparisonReportGenerator().write_report_bundle(
        tmp_path / "report",
        suite_inputs=[_suite(tmp_path, speed) for speed in (0.1, 0.2, 1.0)],
    )

    assert set(outputs) == {
        "json",
        "cases_csv",
        "aggregates_csv",
        "markdown",
        "plot",
    }
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs.values())
    rows = list(csv.DictReader(outputs["cases_csv"].open(encoding="utf-8")))
    assert len(rows) == 60
    assert rows[0]["main_bus_wall_mean_ms"] == "10.0"
    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "case_id/profile/seed" in report
    assert "两层禁止相加" in report
    assert "不从目录名推断" in report


def test_missing_metric_remains_unavailable_and_does_not_become_zero(
    tmp_path: Path,
) -> None:
    suites = [_suite(tmp_path, speed) for speed in (0.1, 0.2, 1.0)]
    del suites[0]["rows"][0]["truth_state_online_use_count"]
    del suites[0]["rows"][0]["intercept_summary"]["pairs"][1][
        "physical_min_range_m"
    ]

    summary = compare_clock_speed_suites(suites)

    assert summary["truth_audit"]["state"]["availability"] == "unavailable"
    assert summary["truth_audit"]["state"]["total_online_use_count"] is None
    affected = next(
        row
        for row in summary["aggregates"]
        if row["clock_speed"] == 0.1 and row["profile"] == "baseline"
    )
    distance = affected["metrics"]["second_primary_min_distance_m"]
    assert distance["availability"] == "unavailable"
    assert distance["value"] is None
    assert distance["available_case_count"] == 9


def test_clock_speed_must_be_in_provenance_not_top_level_or_directory_name(
    tmp_path: Path,
) -> None:
    suites = [_suite(tmp_path, speed) for speed in (0.1, 0.2, 1.0)]
    suites[0]["clock_speed"] = suites[0]["provenance"].pop("clock_speed")

    with pytest.raises(
        ClockSpeedComparisonValidationError,
        match="ClockSpeed must come from suite provenance",
    ):
        compare_clock_speed_suites(suites)


def test_complete_case_result_clock_speed_is_accepted_as_persisted_provenance(
    tmp_path: Path,
) -> None:
    suites = [_suite(tmp_path, speed) for speed in (0.1, 0.2, 1.0)]
    for suite in suites:
        speed = suite["provenance"]["clock_speed"]
        del suite["provenance"]
        for row in suite["rows"]:
            row["clock_speed"] = speed

    summary = compare_clock_speed_suites(suites)

    assert {
        item["clock_speed_provenance_scope"]
        for item in summary["suite_manifest"]
    } == {"case_result"}


@pytest.mark.parametrize("use_summary_path", (False, True))
def test_path_input_uses_all_sibling_case_settings_as_clock_speed_provenance(
    tmp_path: Path,
    use_summary_path: bool,
) -> None:
    root, settings_paths = _legacy_suite_root(tmp_path, clock_speed=1.0)
    source = root / "p1_terminal_closure_summary.json" if use_summary_path else root

    summary = compare_clock_speed_suites(
        [source, _suite(tmp_path, 0.2), _suite(tmp_path, 0.1)]
    )

    suite = next(
        item for item in summary["suite_manifest"] if item["clock_speed"] == 1.0
    )
    assert suite["clock_speed_provenance_scope"] == (
        "sibling_case_generated_settings"
    )
    assert suite["clock_speed_provenance_evidence"] == [
        str(path.resolve()) for path in settings_paths
    ]


def test_sibling_case_settings_provenance_requires_all_twenty_files(
    tmp_path: Path,
) -> None:
    root, settings_paths = _legacy_suite_root(tmp_path, clock_speed=1.0)
    settings_paths[-1].unlink()

    with pytest.raises(
        ClockSpeedComparisonValidationError,
        match="sibling case settings missing",
    ):
        compare_clock_speed_suites(
            [root, _suite(tmp_path, 0.2), _suite(tmp_path, 0.1)]
        )


def test_sibling_case_settings_provenance_requires_explicit_clock_speed_key(
    tmp_path: Path,
) -> None:
    root, settings_paths = _legacy_suite_root(tmp_path, clock_speed=1.0)
    settings_paths[0].write_text(
        json.dumps({"SimMode": "Multirotor"}),
        encoding="utf-8",
    )

    with pytest.raises(
        ClockSpeedComparisonValidationError,
        match="must explicitly contain ClockSpeed",
    ):
        compare_clock_speed_suites(
            [root, _suite(tmp_path, 0.2), _suite(tmp_path, 0.1)]
        )


def test_sibling_case_settings_provenance_rejects_conflicting_values(
    tmp_path: Path,
) -> None:
    root, settings_paths = _legacy_suite_root(tmp_path, clock_speed=1.0)
    settings_paths[-1].write_text(
        json.dumps({"ClockSpeed": 0.5}),
        encoding="utf-8",
    )

    with pytest.raises(
        ClockSpeedComparisonValidationError,
        match="conflicting sibling case settings ClockSpeed",
    ):
        compare_clock_speed_suites(
            [root, _suite(tmp_path, 0.2), _suite(tmp_path, 0.1)]
        )


@pytest.mark.parametrize("invalid_value", (float("nan"), float("inf"), "fast"))
def test_sibling_case_settings_provenance_rejects_invalid_clock_speed(
    tmp_path: Path,
    invalid_value,
) -> None:
    root, settings_paths = _legacy_suite_root(tmp_path, clock_speed=1.0)
    settings_paths[0].write_text(
        json.dumps({"ClockSpeed": invalid_value}),
        encoding="utf-8",
    )

    with pytest.raises(
        ClockSpeedComparisonValidationError,
        match="contain invalid ClockSpeed",
    ):
        compare_clock_speed_suites(
            [root, _suite(tmp_path, 0.2), _suite(tmp_path, 0.1)]
        )


def test_main_enhanced_comparison_role_is_normalized_to_candidate(
    tmp_path: Path,
) -> None:
    suites = [_suite(tmp_path, speed) for speed in (0.1, 0.2, 1.0)]
    for suite in suites:
        for case in suite["cases"]:
            if case["comparison_role"] == "candidate":
                case["comparison_role"] = "enhanced"

    summary = compare_clock_speed_suites(suites)

    assert {item["comparison_role"] for item in summary["expected_profiles"]} == {
        "baseline",
        "candidate",
    }


def test_missing_seed_and_cross_speed_case_key_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    suites = [_suite(tmp_path, speed) for speed in (0.1, 0.2, 1.0)]
    missing = deepcopy(suites)
    missing[0]["cases"].pop()
    missing[0]["rows"].pop()
    with pytest.raises(ClockSpeedComparisonValidationError, match="exactly 20"):
        compare_clock_speed_suites(missing)

    mismatch = deepcopy(suites)
    mismatch[0]["cases"][0]["case_id"] = "different_case_id"
    mismatch[0]["rows"][0]["case_id"] = "different_case_id"
    with pytest.raises(ClockSpeedComparisonValidationError, match="pairing mismatch"):
        compare_clock_speed_suites(mismatch)


def test_truth_nonzero_is_preserved_and_fails_all_zero_audit(tmp_path: Path) -> None:
    suites = [_suite(tmp_path, speed) for speed in (0.1, 0.2, 1.0)]
    suites[1]["rows"][3]["truth_identity_online_use_count"] = 2

    summary = compare_clock_speed_suites(suites)

    identity = summary["truth_audit"]["identity"]
    assert identity["availability"] == "available"
    assert identity["total_online_use_count"] == 2
    assert identity["all_zero"] is False


def test_frozen_opportunity_contract_marks_actual_execution_mismatch_unavailable(
    tmp_path: Path,
) -> None:
    suites = [_suite(tmp_path, speed) for speed in (0.1, 0.2, 1.0)]
    suite_02 = next(
        suite for suite in suites if suite["provenance"]["clock_speed"] == 0.2
    )
    row = next(
        item
        for item in suite_02["rows"]
        if item["profile"] == "candidate_soft_prediction_trend_coast"
        and item["seed"] == 6
    )
    row.update(
        {
            "pair_opportunity_count": 2,
            "pair_success_count": 1,
            "target_opportunity_count": 1,
            "target_success_count": 1,
            "coalition_opportunity_count": 1,
            "coalition_completion_count": 0,
            "d7_actual_execution_status": "unavailable",
            "d7_actual_execution_unavailable_reasons": [
                "d7_actual_execution_physical_pair_count_conflict",
                "d7_actual_execution_command_physical_count_conflict",
                "d7_actual_execution_main_physical_intercept_count_conflict",
            ],
        }
    )
    row["intercept_summary"] = {
        "parameters": {"clock_speed": 0.2},
        "success_count": 2,
        "success_semantics": {
            "pair_physical_success_count": 1,
            "standby_reserve_excluded_from_pair_denominator": True,
        },
        "pairs": [
            _pair("INT-02", "T002", success=True, locked=False),
            _pair("INT-03", "T002", success=False, locked=False),
            {
                **_pair("INT-04", "T002", success=True, locked=False),
                "member_role": "reserve",
                "required_primary": False,
                "activation_state": "standby",
            },
        ],
    }

    summary = compare_clock_speed_suites(suites)

    audit = summary["opportunity_contract_audit"]
    assert audit["mismatch_case_count"] == 1
    mismatch = audit["mismatch_cases"][0]
    assert mismatch["case_id"] == "m5n2_candidate_seed006"
    assert mismatch["availability"] == "unavailable"
    assert mismatch["status"] == "contract_mismatch"
    assert mismatch["expected"] == {
        "active_primary_pair": 3,
        "target": 2,
        "coalition": 1,
    }
    assert mismatch["observed"] == {
        "active_primary_pair": 2,
        "target": 1,
        "coalition": 1,
    }
    assert "d7_actual_execution_physical_pair_count_conflict" in mismatch["reasons"]
    intercept_audit = mismatch["intercept_audit"]
    assert intercept_audit["active_primary_count"] == 2
    assert intercept_audit["active_primary_physical_success_count"] == 1
    assert intercept_audit["standby_reserve_count"] == 1
    assert intercept_audit["standby_reserve_physical_success_count"] == 1
    assert intercept_audit["raw_top_level_success_count"] == 2
    assert intercept_audit["standby_reserve_excluded_from_active_primary_success"] is True

    case_row = next(
        item
        for item in summary["case_rows"]
        if item["clock_speed"] == 0.2
        and item["profile"] == "candidate_soft_prediction_trend_coast"
        and item["seed"] == 6
    )
    assert case_row["metrics"]["active_primary_pair_success_count"][
        "availability"
    ] == "unavailable"
    assert case_row["metrics"]["second_primary_min_distance_m"][
        "availability"
    ] == "unavailable"

    aggregate = next(
        item
        for item in summary["aggregates"]
        if item["clock_speed"] == 0.2
        and item["profile"] == "candidate_soft_prediction_trend_coast"
    )
    pair_rate = aggregate["metrics"]["active_primary_pair_success_rate"]
    assert pair_rate["availability"] == "unavailable"
    assert pair_rate["available_case_count"] == 9
    assert pair_rate["unavailable_case_ids"] == ["m5n2_candidate_seed006"]
    assert "denominator" not in pair_rate


def test_report_lists_contract_mismatch_and_reserve_exclusion(tmp_path: Path) -> None:
    suites = [_suite(tmp_path, speed) for speed in (0.1, 0.2, 1.0)]
    suite_02 = suites[1]
    row = suite_02["rows"][15]
    row["d7_actual_execution_status"] = "unavailable"
    row["d7_actual_execution_unavailable_reasons"] = ["physical_pair_count_conflict"]
    row["pair_opportunity_count"] = 2
    row["target_opportunity_count"] = 1
    row["intercept_summary"]["pairs"] = row["intercept_summary"]["pairs"][:2]

    outputs = ClockSpeedComparisonReportGenerator().write_report_bundle(
        tmp_path / "contract-report",
        suite_inputs=suites,
    )

    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "M5N2 冻结机会合同审计" in report
    assert "m5n2_candidate_seed006" in report
    assert "physical_pair_count_conflict" in report
    assert "standby reserve 始终排除" in report


def _suite(tmp_path: Path, clock_speed: float) -> dict:
    suffix = str(clock_speed).replace(".", "_")
    main_path = tmp_path / f"main_{suffix}.jsonl"
    control_path = tmp_path / f"control_{suffix}.jsonl"
    _write_jsonl(main_path, [_timing_record("main_bus", total_ms=10.0)])
    _write_jsonl(control_path, [_timing_record("control_tick", total_ms=100.0)])

    cases = []
    rows = []
    for profile, role in (
        ("baseline", "baseline"),
        ("candidate_soft_prediction_trend_coast", "candidate"),
    ):
        for seed in range(1, 11):
            case_id = f"m5n2_{role}_seed{seed:03d}"
            cases.append(
                {
                    "case_id": case_id,
                    "profile": profile,
                    "comparison_role": role,
                    "seed": seed,
                    "family": "m5n2_paired",
                    "resource_count": 5,
                    "target_count": 2,
                }
            )
            second_success = seed % 2 == 0
            rows.append(
                {
                    "case_id": case_id,
                    "profile": profile,
                    "seed": seed,
                    "family": "m5n2_paired",
                    "resource_count": 5,
                    "target_count": 2,
                    "physical_metrics_available": True,
                    "d7_actual_execution_status": "available",
                    "d7_actual_execution_unavailable_reasons": [],
                    "pair_success_count": 2 if second_success else 1,
                    "pair_opportunity_count": 3,
                    "target_success_count": 2,
                    "target_opportunity_count": 2,
                    "coalition_completion_availability": "available",
                    "coalition_completion_count": int(second_success),
                    "coalition_opportunity_count": 1,
                    "truth_identity_online_use_count": 0,
                    "truth_state_online_use_count": 0,
                    "wall_timing": {"availability": "available", "elapsed_s": 12.0},
                    "main_stage_timings": str(main_path),
                    "control_tick_stage_timings": str(control_path),
                    "intercept_summary": {
                        "parameters": {"clock_speed": clock_speed},
                        "pairs": [
                            _pair("INT-01", "T001", success=True, locked=True),
                            _pair(
                                "INT-02",
                                "T001",
                                success=second_success,
                                locked=second_success,
                                collision=not second_success,
                            ),
                            _pair("INT-03", "T002", success=True, locked=True),
                        ]
                    },
                }
            )
    return {
        "provenance": {
            "clock_speed": clock_speed,
            "clock_speed_source": "generated_settings.ClockSpeed",
        },
        "cases": cases,
        "rows": rows,
    }


def _legacy_suite_root(
    tmp_path: Path,
    *,
    clock_speed: float,
) -> tuple[Path, list[Path]]:
    suite = _suite(tmp_path, clock_speed)
    del suite["provenance"]
    root = tmp_path / "legacy_m5n2_suite"
    root.mkdir()
    (root / "p1_terminal_closure_summary.json").write_text(
        json.dumps(suite),
        encoding="utf-8",
    )

    settings_paths: list[Path] = []
    for case in suite["cases"]:
        case_id = case["case_id"]
        sibling = tmp_path / f"{root.name}_{case_id.removeprefix('m5n2_')}"
        generated_settings = sibling / "generated_settings"
        generated_settings.mkdir(parents=True)
        settings_path = generated_settings / "blocks_actor_m5_n2_settings.json"
        settings_path.write_text(
            json.dumps({"ClockSpeed": clock_speed}),
            encoding="utf-8",
        )
        settings_paths.append(settings_path)
    return root, settings_paths


def _pair(
    resource_id: str,
    target_id: str,
    *,
    success: bool,
    locked: bool,
    collision: bool = False,
) -> dict:
    return {
        "resource_id": resource_id,
        "target_id": target_id,
        "member_role": "primary",
        "required_primary": True,
        "activation_state": "active",
        "physical_evidence_available": True,
        "physical_success": success,
        "physical_min_range_m": 4.0 if success else 6.0,
        "terminal_locked": locked,
        "control_stop_reason": "collision_stop" if collision else "estimated_range_stop",
    }


def _timing_record(layer: str, *, total_ms: float) -> dict:
    if layer == "main_bus":
        stages = MAIN_STAGES
        schema = "main-stage-timing-v1"
        scope = "main_episode_bus"
        total_name = "bus_total"
    else:
        stages = CONTROL_STAGES
        schema = "control-tick-stage-timing-v1"
        scope = "simpleflight_control_tick"
        total_name = "control_tick_total"
    stages_ms = {name: 0.0 for name in stages}
    stages_ms[stages[0]] = total_ms
    return {
        "schema_version": schema,
        "scope": scope,
        "frame_index": 0,
        "timestamp_s": 0.0,
        "budget_ms": 200.0,
        "total_stage_name": total_name,
        "stages_ms": stages_ms,
        "stage_status": {name: "available" for name in stages},
        "measured_stage_sum_ms": total_ms,
        "unattributed_ms": 0.0,
        "total_ms": total_ms,
        "budget_exceeded": False,
        "error_type": "",
        "error_message": "",
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
