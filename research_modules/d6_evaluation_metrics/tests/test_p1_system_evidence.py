from __future__ import annotations

import csv
import json
from pathlib import Path

from d6_evaluation_metrics import (
    P1SystemEvidenceInputs,
    P1SystemEvidenceReportGenerator,
    load_p1_system_evidence_source,
)


FIXTURES = Path(__file__).parent / "fixtures"
REAL_M5N2_40_CASE = FIXTURES / "p1_m5n2_cooperative_40case_20260713.json"
CORRECTED_M5N2_AGGREGATE = (
    FIXTURES / "p1_m5n2_cooperative_corrected_aggregate_20260713.json"
)


def _inputs() -> P1SystemEvidenceInputs:
    return P1SystemEvidenceInputs(
        d5_native_mot={
            "schema_version": "d5-native-mot-v1",
            "summaries": [
                {
                    "resource_id": "R1",
                    "camera_id": "front",
                    "requested_tracker_backend": "bytetrack",
                    "scenario": {"scenario_id": "native-grid", "target_distance_m": 30.0},
                    "native_active_frame_rate": 0.98,
                    "fallback_frame_count": 0,
                    "offline_detector_precision": 0.94,
                    "offline_detector_recall": 0.86,
                    "local_continuity": 0.93,
                    "terminal_local_id_switch_count": 1,
                    "warmup_excluded_p95_latency_ms": 45.0,
                    "native_mot_admitted": True,
                    "rejection_reasons": [],
                    "truth_identity_used_online": False,
                },
                {
                    "resource_id": "R2",
                    "camera_id": "front",
                    "requested_tracker_backend": "botsort",
                    "scenario": {"scenario_id": "native-grid", "target_distance_m": 30.0},
                    "native_active_frame_rate": 0.96,
                    "fallback_frame_count": 0,
                    "offline_detector_precision": 0.92,
                    "offline_detector_recall": 0.82,
                    "local_continuity": 0.91,
                    "terminal_local_id_switch_count": 0,
                    "warmup_excluded_p95_latency_ms": 72.0,
                    "native_mot_admitted": False,
                    "rejection_reasons": ["minimum_frame_count_not_met"],
                    "truth_identity_used_online": False,
                },
            ],
        },
        d2_difficulty_profiles={
            "schema_version": "d2-p1-identity-calibration/v1",
            "difficulty_results": {
                "confirmation": {
                    "by_difficulty": {
                        "combined": {
                            "seed_count": 20,
                            "scenario_still_non_discriminative": False,
                            "baseline_gnn": {
                                "metrics": {
                                    "id_switch_count": {"available": True, "sum": 3},
                                    "identity_continuity": {"available": True, "mean": 0.91},
                                    "false_track_count": {"available": True, "sum": 2},
                                    "rmse": {"available": True, "mean": 1.4},
                                    "p95_loop_latency_s": {"available": True, "mean": 0.015},
                                    "online_truth_leakage_count": 0,
                                }
                            },
                        }
                    }
                }
            },
        },
        d3_assignment_churn={
            "schema_version": "d3-plan-history-v1",
            "scenario_id": "high-threat",
            "resource_count": 5,
            "target_count": 2,
            "plans": [
                {
                    "version": 1,
                    "metadata": {
                        "terminal_authorization_scope": "per_primary",
                        "arrival_coordination_required": False,
                        "membership_change_records": [],
                    },
                    "coalitions": [{"version": 1, "epoch": 1}],
                },
                {
                    "version": 2,
                    "metadata": {
                        "terminal_authorization_scope": "per_primary",
                        "arrival_coordination_required": False,
                        "membership_change_records": [
                            {"membership_change_reason": "previous_members_hard_infeasible"}
                        ],
                    },
                    "coalitions": [{"version": 2, "epoch": 2}],
                },
            ],
        },
        d4_episode_communication={
            "schema": "d4-episode-communication-v1",
            "scenario_id": "center_failure",
            "ticks": [
                {
                    "timestamp_s": 0.0,
                    "selected_layer": "center",
                    "owner_id": "C2",
                    "epoch": 1,
                    "plan_version": 1,
                    "coalition_version": 1,
                    "commit_state": "center_active",
                    "acked_member_ids": [],
                    "missing_member_ids": [],
                    "rejected_ack_reasons": [],
                    "lease_valid": True,
                    "execution_allowed": True,
                    "fail_closed": False,
                },
                {
                    "timestamp_s": 1.0,
                    "selected_layer": "secondary",
                    "owner_id": None,
                    "epoch": 2,
                    "plan_version": 2,
                    "coalition_version": 2,
                    "commit_state": "collecting_acks",
                    "acked_member_ids": ["R1"],
                    "missing_member_ids": ["R2"],
                    "rejected_ack_reasons": ["ack_plan_version_mismatch"],
                    "lease_valid": True,
                    "execution_allowed": False,
                    "fail_closed": True,
                },
                {
                    "timestamp_s": 2.0,
                    "selected_layer": "secondary",
                    "owner_id": "S1",
                    "epoch": 2,
                    "plan_version": 2,
                    "coalition_version": 2,
                    "commit_state": "executing",
                    "acked_member_ids": ["R1", "R2"],
                    "missing_member_ids": [],
                    "rejected_ack_reasons": [],
                    "lease_valid": True,
                    "execution_allowed": True,
                    "fail_closed": False,
                },
            ],
        },
        d7_per_primary={
            "schema_version": "d7-per-primary-v1",
            "summaries": [
                {
                    "scenario_id": "M5N2_high_threat",
                    "seed": 7,
                    "resource_count": 5,
                    "target_count": 2,
                    "terminal_authorization_scope": "per_primary",
                    "arrival_coordination_required": False,
                    "terminal_contract_allowed_count": 4,
                    "terminal_switch_allowed_count": 3,
                    "mode_switch_count": 2,
                    "intercept_success_count": 1,
                    "per_primary_authorization_active_count": 4,
                    "coalition_visual_completion_bypassed_count": 3,
                    "bypassed_arrival_only_count": 3,
                    "online_truth_use_count": 0,
                }
            ],
        },
    )


def test_report_bundle_aggregates_all_p1_sources(tmp_path) -> None:
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path, inputs=_inputs()
    )

    assert all(path.exists() for path in outputs.values())
    assert outputs["plot"].stat().st_size > 0
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["schema_version"] == "d6-p1-system-evidence-v1"
    assert aggregate["offline_only"] is True
    assert aggregate["controls_air_sim"] is False
    assert aggregate["truth_policy"]["status"] == "pass"
    assert aggregate["d2_by_difficulty"]["combined"]["metrics"]["id_switch_count"]["sum"] == 3
    assert aggregate["d5_by_backend"]["bytetrack"]["metrics"]["native_mot_admitted"]["sum"] == 1
    assert aggregate["d7_terminal_layers"]["contract_allowed_count"]["sum"] == 4
    assert aggregate["d7_terminal_layers"]["control_allowed_count"]["sum"] == 3
    assert aggregate["d7_terminal_layers"]["mode_switched_count"]["sum"] == 2
    assert aggregate["d7_terminal_layers"]["physical_intercept_count"]["sum"] == 1

    rows = list(csv.DictReader(outputs["rows_csv"].open(encoding="utf-8")))
    d3 = next(row for row in rows if row["source"] == "d3_assignment_churn")
    assert d3["terminal_authorization_scope"] == "per_primary"
    assert d3["arrival_coordination_required"] == "False"
    assert d3["membership_change_count"] == "1"
    assert d3["plan_version_churn_count"] == "1"
    d4 = next(row for row in rows if row["source"] == "d4_episode_communication")
    assert d4["failover_count"] == "1"
    assert d4["ack_count"] == "2"
    assert d4["missing_ack_count"] == "1"
    assert d4["owner_change_count"] == "2"


def test_missing_metrics_remain_unavailable_and_layers_do_not_promote(tmp_path) -> None:
    inputs = P1SystemEvidenceInputs(
        d7_per_primary={
            "summaries": [
                {
                    "scenario_id": "2v2_name_must_not_define_scale",
                    "terminal_contract_allowed_count": 2,
                    "terminal_switch_allowed_count": 1,
                }
            ]
        }
    )
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path, inputs=inputs
    )
    rows = list(csv.DictReader(outputs["rows_csv"].open(encoding="utf-8")))
    row = rows[0]
    assert row["resource_count"] == ""
    assert row["target_count"] == ""
    assert row["contract_allowed_count"] == "2"
    assert row["control_allowed_count"] == "1"
    assert row["mode_switched_count"] == ""
    assert row["mode_switched_count_availability"] == "unavailable"
    assert row["physical_intercept_count"] == ""
    assert row["physical_intercept_count_availability"] == "unavailable"


def test_loader_accepts_sequence_and_report_keeps_explicit_truth_violation(tmp_path) -> None:
    assert load_p1_system_evidence_source([{"seed": 1}]) == {
        "records": [{"seed": 1}]
    }
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1SystemEvidenceInputs(
            d5_native_mot={
                "summaries": [
                    {
                        "requested_tracker_backend": "bytetrack",
                        "truth_identity_used_online": True,
                    }
                ]
            }
        ),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["truth_policy"]["online_truth_use_count"] == 1
    assert aggregate["truth_policy"]["status"] == "fail"


def test_unified_bundle_consumes_d1_d5_d4_fault_and_d7_pair_evidence(tmp_path) -> None:
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1SystemEvidenceInputs(
            d1_dense_crossing={
                "schema_version": "d1.airsim_replay_freeze_summary.v1",
                "summaries": [
                    {
                        "capture_provenance": {
                            "scenario_id": "dense-crossing",
                            "seed": seed,
                            "target_spacing_m": 2.0,
                            "evidence_path": f"seed-{seed}",
                        },
                        "accepted_observation_count": 10,
                        "rejected_observation_count": 0,
                        "rejected_observations": [],
                        "offline_truth_sample_count": 10,
                        "offline_truth_target_count": 5,
                        "field_availability": {
                            name: {"status": "available", "count": 10}
                            for name in (
                                "measurement_timestamp",
                                "arrival_timestamp",
                                "covariance",
                                "source_lineage",
                            )
                        },
                        "online_truth_leak_count": 0,
                    }
                    for seed in (1, 2)
                ],
            },
            d4_episode_communication={
                "schema": "d4_p1_communication_fault_replay_v1",
                "cases": [
                    {
                        "scenario_id": "center_secondary_failure",
                        "seed": 1,
                        "layer_trace": ["center", "secondary", "distributed"],
                        "selected_layer": "distributed",
                        "owner_id": "R1",
                        "passed": False,
                        "execution_allowed": False,
                        "fail_closed": True,
                        "acked_member_ids": ["R1", "R2"],
                        "missing_member_ids": ["R3"],
                        "rejected_ack_count": 1,
                        "failure_reasons": ["missing_required_acks"],
                    }
                ],
            },
            d5_per_primary={
                "schema_version": "d5-per-primary-v1",
                "rows": [
                    {
                        "scenario_id": "m5n2",
                        "seed": 1,
                        "resource_id": "R1",
                        "assigned_global_track_id": "G1",
                        "independently_locked": False,
                        "rejection_reasons": ["friend_conflict_present"],
                        "global_track_id_rewrite_count": 0,
                    }
                ],
            },
            d7_per_primary={
                "schema_version": "d7-cooperative-guidance-v1",
                "pair_diagnostics": [
                    {
                        "episode_id": "m5n2-seed-1",
                        "seed": 1,
                        "resource_id": "R1",
                        "target_id": "G1",
                        "contract_allowed": True,
                        "control_allowed": False,
                        "mode_switched": False,
                        "physical_intercept": False,
                        "first_failure_reason": "terminal_control_not_allowed",
                    }
                ],
            },
        ),
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    d1_metric = aggregate["by_source"]["d1_dense_crossing"]["metrics"]
    assert d1_metric["d1_replay_contract_complete"]["sum"] == 2
    assert d1_metric["dual_timestamp_coverage_rate"]["bootstrap_ci95"]["status"] == "available"
    assert aggregate["d7_terminal_layers"]["contract_allowed_count"]["sum"] == 1
    assert aggregate["d7_terminal_layers"]["control_allowed_count"]["sum"] == 0
    assert aggregate["d7_terminal_layers"]["physical_intercept_count"]["sum"] == 0
    assert aggregate["failure_reason_distribution"]["counts"] == {
        "friend_conflict_present": 1,
        "missing_required_acks": 1,
        "terminal_control_not_allowed": 1,
    }


def test_source_hash_and_unavailable_failure_distribution_are_preserved(tmp_path) -> None:
    source = tmp_path / "d7.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "d7-v1",
                "provenance": {"producer": "d7", "run_id": "run-7"},
                "summaries": [{"seed": 7, "contract_allowed_count": 0}],
            }
        ),
        encoding="utf-8",
    )
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path / "report",
        inputs=P1SystemEvidenceInputs(d7_per_primary=source),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    manifest = aggregate["source_manifest"]["d7_per_primary"]
    assert manifest["sha256"].startswith("sha256:")
    assert manifest["producer"] == "d7"
    assert manifest["run_id"] == "run-7"
    assert aggregate["failure_reason_distribution"]["status"] == "unavailable"
    assert aggregate["failure_reason_distribution"]["total_failure_reason_count"] is None


def test_real_m5n2_raw_schema_expands_d3_d5_d7_without_case_profile_regrouping(
    tmp_path,
) -> None:
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1SystemEvidenceInputs(
            d3_assignment_churn=REAL_M5N2_40_CASE,
            d5_per_primary=REAL_M5N2_40_CASE,
            d7_per_primary=REAL_M5N2_40_CASE,
        ),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))

    assert aggregate["source_manifest"]["d7_per_primary"]["schema_version"] == (
        "p1-cooperative-closure-v2"
    )
    assert aggregate["by_source"]["d3_assignment_churn"]["row_count"] == 40
    assert aggregate["by_source"]["d5_per_primary"]["row_count"] == 160
    assert aggregate["by_source"]["d7_per_primary"]["row_count"] == 164

    d3 = aggregate["by_source"]["d3_assignment_churn"]["metrics"]
    assert d3["primary_assignment_count"]["sum"] == 120
    assert d3["reserve_assignment_count"]["sum"] == 40
    assert d3["plan_version_churn_count"]["status"] == "unavailable"

    d5 = aggregate["d5_per_primary"]
    assert d5["per_primary_evidence_count"]["sum"] == 120
    assert d5["per_primary_visible_count"]["sum"] == 120
    assert d5["per_primary_associated_count"]["sum"] == 74
    assert d5["independently_locked_count"]["sum"] == 74
    assert d5["per_primary_common_lock_count"]["sum"] == 22
    assert d5["global_track_id_rewrite_count"]["sum"] == 0

    assert {
        name: summary["sum"]
        for name, summary in aggregate["d7_terminal_layers"].items()
    } == {
        "contract_allowed_count": 35,
        "control_allowed_count": 7,
        "mode_switched_count": 9,
        "physical_intercept_count": 62,
    }
    closure = aggregate["d7_cooperative_closure"]
    assert closure["profile_count"] == 4
    assert closure["selected_profile"] == "d3-p1-h020.0-w03.0-s040.0"
    assert closure["overall"]["case_opportunity_count"]["sum"] == 40
    assert closure["overall"]["coalition_opportunity_count"]["sum"] == 40
    assert closure["overall"]["coalition_completion_count"]["sum"] == 8
    best = closure["by_profile"]["d3-p1-h020.0-w03.0-s040.0"]["metrics"]
    assert best["case_opportunity_count"]["sum"] == 10
    assert best["coalition_completion_count"]["sum"] == 5
    assert closure["reserve_unauthorized_count"]["sum"] == 0
    assert aggregate["truth_policy"]["online_truth_use_count"] == 0

    rows = list(csv.DictReader(outputs["rows_csv"].open(encoding="utf-8")))
    profile_rows = [
        row for row in rows if row["family"] == "cooperative_profile_summary"
    ]
    assert len(profile_rows) == 4
    assert len({row["candidate"] for row in profile_rows}) == 4
    assert all("_seed" not in row["candidate"] for row in profile_rows)


def test_corrected_m5n2_aggregate_restores_d5_and_d7_availability(tmp_path) -> None:
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1SystemEvidenceInputs(
            d5_per_primary=CORRECTED_M5N2_AGGREGATE,
            d7_per_primary=CORRECTED_M5N2_AGGREGATE,
        ),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))

    assert aggregate["by_source"]["d5_per_primary"]["row_count"] == 1
    assert aggregate["by_source"]["d7_per_primary"]["row_count"] == 5
    d5 = aggregate["d5_per_primary"]
    assert d5["per_primary_evidence_count"]["sum"] == 120
    assert d5["per_primary_associated_count"]["sum"] == 74
    assert d5["common_lock_count"]["sum"] == 11
    assert d5["common_lock_opportunity_count"]["sum"] == 40
    assert d5["global_track_id_rewrite_count"]["sum"] == 0

    assert aggregate["d7_terminal_layers"]["physical_intercept_count"]["sum"] == 62
    closure = aggregate["d7_cooperative_closure"]
    assert closure["profile_count"] == 4
    assert closure["selected_profile"] == "d3-p1-h020.0-w03.0-s040.0"
    assert closure["overall"]["coalition_completion_count"]["sum"] == 8
    assert closure["overall"]["coalition_opportunity_count"]["sum"] == 40
    best = closure["by_profile"]["d3-p1-h020.0-w03.0-s040.0"]["metrics"]
    assert best["coalition_completion_count"]["sum"] == 5
    assert best["case_opportunity_count"]["sum"] == 10
    assert closure["reserve_unauthorized_count"]["sum"] == 0
    assert aggregate["truth_policy"] == {
        "online_truth_allowed": False,
        "online_truth_use_count": 0.0,
        "raw_truth_identifiers_exported": False,
        "status": "pass",
    }
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "## D5 per-primary 证据" in markdown
    assert "## 协同闭环 profile 与 coalition" in markdown
    assert "d3-p1-h020.0-w03.0-s040.0 | 10.0000 | 10.0000 | 5.0000" in markdown
