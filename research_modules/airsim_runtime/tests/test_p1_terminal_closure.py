from __future__ import annotations

import csv
import json

import pytest

from airsim_runtime.p1_terminal_closure import (
    build_terminal_closure_cases,
    summarize_terminal_closure_rows,
    write_terminal_closure_bundle,
)
from airsim_runtime.run_blocks_sequence import _terminal_closure_command_counts


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
    assert three_frame.metadata()["scenario_version"] == "airsim-2v2-locked-dropout-v1"
    m5n2 = next(case for case in cases if case.family == "m5n2_paired")
    assert (m5n2.resource_count, m5n2.target_count) == (5, 2)
    assert (m5n2.duration_s, m5n2.intercept_altitude_z) == (35.0, -30.0)


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
            ]
        )

    counts = _terminal_closure_command_counts(path)
    assert counts["command_count"] == 3
    assert counts["terminal_switch_allowed_count"] == 1
    assert counts["contract_allowed_count"] == 2
    assert counts["control_allowed_count"] == 1
    assert counts["mode_switched_count"] == 1
    assert counts["terminal_prediction_count"] == 1
    assert counts["terminal_delivery_expired_count"] == 2
    assert counts["terminal_prediction_window_expired_count"] == 1
    assert counts["terminal_trend_coast_count"] == 1
    assert counts["ttc_area_jump_reject_count"] == 1
    assert counts["ttc_out_of_range_reject_count"] == 1
    assert counts["online_truth_use_count"] == 0


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
