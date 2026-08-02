from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from airsim_runtime.p1_terminal_closure import (
    build_terminal_closure_cases,
    summarize_terminal_closure_rows,
    write_terminal_closure_bundle,
)
from airsim_runtime.run_blocks_sequence import (
    _merge_terminal_closure_stage_timings,
    _select_terminal_closure_cases,
    _terminal_closure_command_counts,
    _terminal_closure_result_row,
)


def test_terminal_closure_case_matrix_is_paired_and_versioned() -> None:
    cases = build_terminal_closure_cases((1, 2), dropout_frames=(1, 3, 5))

    assert len(cases) == 12
    assert sum(case.family == "m5n2_paired" for case in cases) == 4
    assert sum(case.family == "png_ttc" for case in cases) == 2
    assert sum(case.family == "locked_dropout" for case in cases) == 6
    three_frame = next(
        case for case in cases if case.seed == 1 and case.dropout_frames == 3
    )
    assert three_frame.dropout_end_s == pytest.approx(1.1)
    assert three_frame.metadata()["scenario_version"] == "airsim-2v2-locked-dropout-v2"
    assert three_frame.intercept_altitude_z == -5.0
    png_ttc = next(case for case in cases if case.family == "png_ttc")
    assert png_ttc.metadata()["scenario_version"] == "airsim-2v2-png-ttc-v2"
    assert png_ttc.intercept_altitude_z == -5.0
    m5n2 = next(case for case in cases if case.family == "m5n2_paired")
    assert (m5n2.resource_count, m5n2.target_count) == (5, 2)
    assert (m5n2.duration_s, m5n2.intercept_altitude_z) == (35.0, -30.0)


def test_terminal_closure_can_add_controlled_ttc_disturbance_cases() -> None:
    cases = build_terminal_closure_cases(
        (1,),
        dropout_frames=(1,),
        controlled_ttc_disturbances=("bbox_area_jump", "bbox_clipping"),
    )

    assert len(cases) == 6
    controlled = [case for case in cases if case.terminal_visual_disturbance_type]
    assert {case.terminal_visual_disturbance_type for case in controlled} == {
        "bbox_area_jump",
        "bbox_clipping",
    }
    assert {case.family for case in controlled} == {"png_ttc"}
    assert {
        case.metadata()["scenario_version"] for case in controlled
    } == {"airsim-2v2-png-ttc-controlled-v1"}

    with pytest.raises(ValueError, match="unsupported controlled TTC"):
        build_terminal_closure_cases(
            (1,),
            controlled_ttc_disturbances=("unknown",),
        )


def test_terminal_closure_m5n2_only_selection_keeps_paired_20_case_scope() -> None:
    cases = build_terminal_closure_cases(range(1, 11))

    selected = _select_terminal_closure_cases(cases, m5n2_only=True)

    assert len(selected) == 20
    assert {case.family for case in selected} == {"m5n2_paired"}
    assert {case.seed for case in selected} == set(range(1, 11))
    assert {case.profile for case in selected} == {
        "baseline",
        "candidate_soft_prediction_trend_coast",
    }


def test_terminal_closure_controlled_only_selects_two_cases_per_seed() -> None:
    cases = build_terminal_closure_cases(
        (1, 2),
        controlled_ttc_disturbances=("bbox_area_jump", "bbox_clipping"),
    )

    selected = _select_terminal_closure_cases(
        cases,
        m5n2_only=False,
        controlled_ttc_only=True,
    )

    assert len(selected) == 4
    assert all(case.terminal_visual_disturbance_type for case in selected)
    with pytest.raises(SystemExit, match="mutually exclusive"):
        _select_terminal_closure_cases(
            cases,
            m5n2_only=True,
            controlled_ttc_only=True,
        )


def test_terminal_closure_timing_merge_requires_every_case(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text(
        json.dumps({"scope": "control_tick", "total_ms": 12.0}) + "\n",
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"scope": "control_tick", "total_ms": 14.0}) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "merged.jsonl"
    rows = [
        {
            "case_id": "case-1",
            "family": "png_ttc",
            "profile": "baseline",
            "seed": 1,
            "control_tick_stage_timings": str(first),
        },
        {
            "case_id": "case-2",
            "family": "png_ttc",
            "profile": "baseline",
            "seed": 2,
            "control_tick_stage_timings": str(second),
        },
    ]

    merged = _merge_terminal_closure_stage_timings(
        rows,
        field="control_tick_stage_timings",
        output_path=output,
    )

    assert merged == output
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert [record["case_id"] for record in records] == ["case-1", "case-2"]
    assert [record["seed"] for record in records] == [1, 2]

    rows[1]["control_tick_stage_timings"] = None
    assert (
        _merge_terminal_closure_stage_timings(
            rows,
            field="control_tick_stage_timings",
            output_path=output,
        )
        is None
    )
    assert not output.exists()


def test_terminal_closure_summary_keeps_paired_layers_separate(tmp_path) -> None:
    cases = build_terminal_closure_cases((7,), dropout_frames=(1,))
    rows = []
    for case in cases:
        row = {
            "case_id": case.case_id,
            "family": case.family,
            "profile": case.profile,
            "seed": case.seed,
            "connected": True,
            "pair_opportunity_count": 3,
            "pair_success_count": 2,
            "target_opportunity_count": 2,
            "target_success_count": 2,
            "coalition_opportunity_count": 1,
            "coalition_completion_count": 0,
            "online_truth_use_count": 0,
            "truth_identity_online_use_count": 0,
            "truth_state_online_use_count": 0,
            "physical_metrics_available": True,
            "d7_actual_execution_status": "available",
            "contract_allowed_count": 1,
            "control_allowed_count": 1,
            "mode_switched_count": 1,
            "physical_intercept_count": 2,
            "terminal_switch_allowed_count": 1,
            "terminal_prediction_count": 0,
            "terminal_delivery_expired_count": 0,
            "terminal_prediction_window_expired_count": 0,
        }
        rows.append(row)

    payload = summarize_terminal_closure_rows(cases, rows)
    assert payload["acceptance"]["all_results_present"] is True
    assert payload["acceptance"]["online_truth_use_zero"] is True
    assert payload["acceptance"]["truth_identity_online_use_zero"] is True
    assert payload["acceptance"]["truth_state_online_use_zero"] is True
    assert payload["acceptance"]["physical_metrics_available"] is True
    assert payload["acceptance"]["actual_execution_all_available"] is True
    assert payload["m5n2_paired"]["pair_count"] == 1
    assert payload["m5n2_paired"]["candidate_target_non_degradation"] is True
    assert payload["m5n2_paired"]["candidate_pair_non_degradation"] is True

    paths = write_terminal_closure_bundle(tmp_path, cases, rows)
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["case_count"] == 4
    assert paths["csv"].exists()
    assert "M5N2 paired seeds" in paths["markdown"].read_text(encoding="utf-8")


def test_terminal_closure_command_counts_preserve_ttc_and_truth_semantics(tmp_path) -> None:
    path = tmp_path / "control_commands.csv"
    fieldnames = [
        "terminal_switch_allowed",
        "terminal_contract_allowed",
        "resource_id",
        "mode",
        "terminal_delivery_state",
        "terminal_delivery_reason",
        "terminal_trend_coast_applied",
        "truth_identity_online_use",
        "ttc_reject_reason",
        "disturbance_applied",
        "disturbance_type",
        "effective_control_authorized",
        "executed_guidance_law",
        "expected_global_track_id",
        "assigned_global_track_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            [
                {
                    "terminal_switch_allowed": "true",
                    "terminal_contract_allowed": "true",
                    "resource_id": "INT-01",
                    "mode": "radar_midcourse",
                    "terminal_delivery_state": "image_kf_predict",
                    "terminal_delivery_reason": "terminal_visual_image_kf_predict",
                    "terminal_trend_coast_applied": "false",
                    "truth_identity_online_use": "false",
                    "ttc_reject_reason": "area_jump",
                },
                {
                    "terminal_switch_allowed": "false",
                    "terminal_contract_allowed": "true",
                    "resource_id": "INT-01",
                    "mode": "vision_terminal",
                    "terminal_delivery_state": "expired",
                    "terminal_delivery_reason": "terminal_visual_prediction_window_expired",
                    "terminal_trend_coast_applied": "true",
                    "truth_identity_online_use": "false",
                    "ttc_reject_reason": "ttc_out_of_range",
                },
                {
                    "terminal_switch_allowed": "true",
                    "terminal_contract_allowed": "false",
                    "resource_id": "INT-02",
                    "mode": "reacquire",
                    "terminal_delivery_state": "expired",
                    "terminal_delivery_reason": "d5_not_locked",
                    "terminal_trend_coast_applied": "false",
                    "truth_identity_online_use": "false",
                    "ttc_reject_reason": "",
                },
                {
                    "terminal_switch_allowed": "false",
                    "terminal_contract_allowed": "true",
                    "resource_id": "INT-02",
                    "mode": "radar_midcourse",
                    "terminal_delivery_state": "measured",
                    "terminal_delivery_reason": "terminal_visual_measured",
                    "terminal_trend_coast_applied": "false",
                    "truth_identity_online_use": "false",
                    "ttc_reject_reason": "bbox_area_jump",
                    "disturbance_applied": "true",
                    "disturbance_type": "bbox_area_jump",
                    "effective_control_authorized": "false",
                    "executed_guidance_law": "radar_pn",
                    "expected_global_track_id": "G1",
                    "assigned_global_track_id": "G1",
                },
            ]
        )

    counts = _terminal_closure_command_counts(path)
    assert counts["command_count"] == 4
    assert counts["terminal_switch_allowed_count"] == 1
    assert counts["contract_allowed_count"] == 3
    assert counts["control_allowed_count"] == 1
    assert counts["mode_switched_count"] == 1
    assert counts["terminal_prediction_count"] == 1
    assert counts["terminal_delivery_expired_count"] == 2
    assert counts["terminal_prediction_window_expired_count"] == 1
    assert counts["terminal_trend_coast_count"] == 1
    assert counts["ttc_area_jump_reject_count"] == 2
    assert counts["ttc_out_of_range_reject_count"] == 1
    assert counts["online_truth_use_count"] == 0
    assert counts["controlled_disturbance_applied_count"] == 1
    assert counts["controlled_disturbance_compliant_count"] == 1
    assert counts["controlled_disturbance_identity_mismatch_count"] == 0
    assert counts["controlled_disturbance_control_violation_count"] == 0
    assert counts["controlled_disturbance_fallback_violation_count"] == 0


def test_terminal_closure_summary_requires_controlled_ttc_compliance() -> None:
    cases = build_terminal_closure_cases(
        (3,),
        dropout_frames=(1,),
        controlled_ttc_disturbances=("bbox_area_jump", "bbox_clipping"),
    )
    rows = []
    for case in cases:
        disturbance_type = case.terminal_visual_disturbance_type
        rows.append(
            {
                "case_id": case.case_id,
                "family": case.family,
                "profile": case.profile,
                "seed": case.seed,
                "connected": True,
                "pair_opportunity_count": 3,
                "pair_success_count": 2,
                "target_opportunity_count": 2,
                "target_success_count": 2,
                "coalition_opportunity_count": 1,
                "coalition_completion_count": 0,
                "online_truth_use_count": 0,
                "truth_identity_online_use_count": 0,
                "truth_state_online_use_count": 0,
                "physical_metrics_available": True,
                "d7_actual_execution_status": "available",
                "terminal_prediction_count": 1,
                "terminal_prediction_window_expired_count": 0,
                "controlled_disturbance_applied_count": int(
                    disturbance_type is not None
                ),
                "controlled_disturbance_compliant_count": int(
                    disturbance_type is not None
                ),
                "controlled_disturbance_identity_mismatch_count": 0,
                "ttc_area_jump_reject_count": int(
                    disturbance_type == "bbox_area_jump"
                ),
                "ttc_bbox_clipping_reject_count": int(
                    disturbance_type == "bbox_clipping"
                ),
            }
        )

    payload = summarize_terminal_closure_rows(cases, rows)

    controlled = payload["acceptance"]["controlled_ttc_disturbances"]
    assert controlled["expected_case_count"] == 2
    assert controlled["result_count"] == 2
    assert controlled["all_passed"] is True


def test_terminal_closure_result_uses_d6_physical_provenance_gate(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "control_api_used": True,
                "physical_intercept_available": True,
                "physical_intercept_source": "offline_truth_distance_scorer",
                "online_control_state_source": "d2_estimated_global_track",
                "truth_state_online_use_count": 0,
                "success_count": 1,
                "pair_count": 1,
                "parameters": {
                    "clock_speed": 0.2,
                    "intercept_radius_m": 5.0,
                    "intercept_distance_frame": "NED",
                    "intercept_distance_dimension": "3d_euclidean",
                    "intercept_success_criteria_version": (
                        "airsim-offline-range-intercept-v3"
                    ),
                },
                "pairs": [
                    {
                        "resource_id": "INT-01",
                        "target_id": "TGT-001",
                        "assigned": True,
                        "activation_state": "active",
                        "status": "range_intercept",
                        "physical_min_range_m": 4.8,
                        "physical_evidence_available": True,
                        "physical_success": True,
                        "target_state_source": "d2_estimated_global_track",
                        "time_to_intercept_s": 3.0,
                        "online_truth_id_used": False,
                        "online_truth_state_used": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    commands_path = tmp_path / "control_commands.csv"
    commands_path.write_text(
        "truth_identity_online_use,truth_state_online_use,target_state_source\n"
        "False,False,d2_estimated_global_track\n",
        encoding="utf-8",
    )
    main_timing_path = tmp_path / "main_stage_timings.jsonl"
    main_timing_path.write_text("", encoding="utf-8")
    control_timing_path = tmp_path / "control_tick_timings.jsonl"
    control_timing_path.write_text("", encoding="utf-8")
    episode = SimpleNamespace(
        metadata={"control_api_used": True},
        output_paths={
            "intercept_summary": summary_path,
            "control_commands": commands_path,
            "main_stage_timings_jsonl": main_timing_path,
            "control_tick_timings": control_timing_path,
        },
    )
    result = SimpleNamespace(connected=True, episode_results=(episode,))
    case = next(
        case
        for case in build_terminal_closure_cases((1,), dropout_frames=(1,))
        if case.family == "png_ttc"
    )

    row = _terminal_closure_result_row(case, result)

    assert row["truth_identity_online_use_count"] == 0
    assert row["truth_state_online_use_count"] == 0
    assert row["online_control_state_source"] == "d2_estimated_global_track"
    assert row["physical_intercept_source"] == "offline_truth_distance_scorer"
    assert row["clock_speed"] == pytest.approx(0.2)
    assert row["physical_metrics_available"] is True
    assert row["pair_opportunity_count"] == 1
    assert row["pair_success_count"] == 1
    assert row["target_success_count"] == 1
    assert row["main_stage_timings"] == str(main_timing_path)
    assert row["control_tick_stage_timings"] == str(control_timing_path)


def test_terminal_closure_result_keeps_missing_pair_result_unavailable(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "control_api_used": True,
                "physical_intercept_available": True,
                "physical_intercept_source": "offline_truth_distance_scorer",
                "online_control_state_source": "d2_estimated_global_track",
                "truth_state_online_use_count": 0,
                "parameters": {
                    "intercept_radius_m": 5.0,
                    "intercept_distance_frame": "NED",
                    "intercept_distance_dimension": "3d_euclidean",
                    "intercept_success_criteria_version": (
                        "airsim-offline-range-intercept-v3"
                    ),
                },
                "pairs": [
                    {
                        "resource_id": "INT-01",
                        "target_id": "TGT-001",
                        "assigned": True,
                        "activation_state": "active",
                        "physical_evidence_available": True,
                        "target_state_source": "d2_estimated_global_track",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    episode = SimpleNamespace(
        metadata={"control_api_used": True},
        output_paths={"intercept_summary": summary_path},
    )
    result = SimpleNamespace(connected=True, episode_results=(episode,))
    case = next(
        case
        for case in build_terminal_closure_cases((1,), dropout_frames=(1,))
        if case.family == "png_ttc"
    )

    row = _terminal_closure_result_row(case, result)

    assert row["physical_metrics_available"] is False
    assert row["pair_success_count"] is None
    assert "physical_success" in str(row["physical_metrics_unavailable_reason"])


def test_terminal_closure_result_registers_explicit_actual_unavailable(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "intercept_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "control_api_used": True,
                "physical_intercept_available": False,
                "physical_intercept_source": "offline_truth_distance_scorer",
                "online_control_state_source": "d2_estimated_global_track",
                "truth_state_online_use_count": 0,
                "parameters": {
                    "intercept_radius_m": 5.0,
                    "intercept_distance_frame": "NED",
                    "intercept_distance_dimension": "3d_euclidean",
                    "intercept_success_criteria_version": (
                        "airsim-offline-range-intercept-v3"
                    ),
                },
                "pairs": [],
            }
        ),
        encoding="utf-8",
    )
    unavailable_path = tmp_path / "d7_actual_execution_unavailable.json"
    unavailable_path.write_text(
        json.dumps(
            {
                "schema": "d7-actual-execution-unavailable-v1",
                "status": "unavailable",
                "case_id": "png_ttc_2v2_seed001",
                "reasons": [
                    "d7_actual_execution_command_physical_count_conflict"
                ],
            }
        ),
        encoding="utf-8",
    )
    episode = SimpleNamespace(
        metadata={"control_api_used": True},
        output_paths={
            "intercept_summary": summary_path,
            "d7_actual_execution_unavailable": unavailable_path,
        },
    )
    result = SimpleNamespace(connected=True, episode_results=(episode,))
    case = next(
        case
        for case in build_terminal_closure_cases((1,), dropout_frames=(1,))
        if case.family == "png_ttc"
    )

    row = _terminal_closure_result_row(case, result)

    assert row["d7_actual_execution_status"] == "unavailable"
    assert row["d7_actual_execution_metrics"] is None
    assert row["d7_actual_execution_unavailable"] == str(unavailable_path)
    assert row["d7_actual_execution_unavailable_reasons"] == [
        "d7_actual_execution_command_physical_count_conflict"
    ]


def test_dropout_acceptance_requires_every_seed_to_match_the_window_contract() -> None:
    cases = build_terminal_closure_cases((1, 2), dropout_frames=(1,))
    dropout_cases = [case for case in cases if case.family == "locked_dropout"]
    rows = [
        {
            "family": "locked_dropout",
            "profile": case.profile,
            "seed": case.seed,
            "dropout_frames": 1,
            "terminal_prediction_count": 1 if case.seed == 1 else 0,
            "terminal_prediction_window_expired_count": 0,
            "online_truth_use_count": 0,
        }
        for case in dropout_cases
    ]

    payload = summarize_terminal_closure_rows(dropout_cases, rows)
    dropout = payload["acceptance"]["dropout_matrix"]
    assert dropout["all_passed"] is False
    assert dropout["rows"][0]["record_count"] == 2
    assert dropout["rows"][0]["passed_record_count"] == 1
