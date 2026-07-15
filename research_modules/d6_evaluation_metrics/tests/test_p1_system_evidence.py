from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

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
D3_CHURN_METRICS = (
    "plan_version_churn_count",
    "coalition_version_churn_count",
    "coalition_epoch_churn_count",
    "membership_change_count",
)
D3_CANONICAL_HISTORY_METRICS = (
    *D3_CHURN_METRICS,
    "primary_membership_change_count",
    "reserve_membership_change_count",
    "owner_change_count",
    "soft_feedback_count",
    "hard_feedback_count",
)


def _d3_row(tmp_path: Path, payload: object) -> dict[str, str]:
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1SystemEvidenceInputs(d3_assignment_churn=payload),
    )
    rows = list(csv.DictReader(outputs["rows_csv"].open(encoding="utf-8")))
    return next(row for row in rows if row["source"] == "d3_assignment_churn")


def _canonical_assignment(
    resource_id: str,
    *,
    role: str,
    activation_state: str,
) -> dict[str, object]:
    return {
        "target_id": "T1",
        "resource_id": resource_id,
        "member_role": role,
        "wave_id": 0,
        "activation_state": activation_state,
        "active": activation_state == "active",
        "coalition_id": "C1",
        "coalition_version": 1,
        "coalition_epoch": 1,
        "coalition_complete": True,
        "assignment_validity_state": "current",
        "feasibility_state": "feasible",
        "cost": 1.0,
        "cost_breakdown": {"total": 1.0},
    }


def _canonical_history_record(
    sequence_index: int,
    timestamp: float,
    *,
    plan_version: int = 1,
    coalition_version: int = 1,
    coalition_epoch: int = 1,
    assignments: list[dict[str, object]] | None = None,
    active_plan_owner: str = "center",
    owner_node_id: str | None = "CENTER",
    soft_count: int = 0,
    hard_count: int = 0,
) -> dict[str, object]:
    if assignments is None:
        assignments = [
            _canonical_assignment("R1", role="primary", activation_state="active"),
            _canonical_assignment("R2", role="reserve", activation_state="standby"),
        ]
    normalized_assignments = []
    for assignment in assignments:
        item = dict(assignment)
        item["coalition_version"] = coalition_version
        item["coalition_epoch"] = coalition_epoch
        normalized_assignments.append(item)
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
        "resource_count": 3,
        "target_count": 1,
        "assigned_count": len(normalized_assignments),
        "plan_owner": active_plan_owner,
        "active_plan_owner": active_plan_owner,
        "owner_node_id": owner_node_id,
        "source_node_id": owner_node_id,
        "selected_secondary_node_id": (
            owner_node_id if active_plan_owner == "secondary" else None
        ),
        "secondary_plan_version": (
            plan_version if active_plan_owner == "secondary" else None
        ),
        "secondary_leader_epoch": (
            coalition_epoch if active_plan_owner == "secondary" else None
        ),
        "secondary_lease_expires_at_s": (
            timestamp + 5.0 if active_plan_owner == "secondary" else None
        ),
        "previous_plan_id": None,
        "previous_plan_version": None,
        "supersedes_plan_id": None,
        "supersedes_plan_version": None,
        "assignments": normalized_assignments,
        "coalitions": [
            {
                "coalition_id": "C1",
                "version": coalition_version,
                "epoch": coalition_epoch,
                "target_id": "T1",
                "state": "committed",
                "coordination_mode": "hybrid_primary_reserve",
                "required_resource_count": 1,
                "primary_resource_count": sum(
                    item["member_role"] == "primary"
                    for item in normalized_assignments
                ),
                "assigned_resource_count": len(normalized_assignments),
                "shortfall": 0,
                "complete": True,
                "members": [],
            }
        ],
        "hysteresis": {"state": "stable", "reason": None},
        # This audit record is deliberately repeated across ticks. D6 must use
        # assignment snapshot differences instead of summing this list.
        "membership_change_records": [
            {
                "target_id": "T1",
                "membership_change_reason": "historical_audit_only",
            }
        ],
        "feedback_constraints": {
            "schema": "d3_feedback_constraint_classification_v1",
            "classifications": [],
            "soft_count": soft_count,
            "hard_count": hard_count,
            "soft_edge_count": soft_count,
            "hard_edge_count": hard_count,
            "resource_hard_count": 0,
            "target_hard_count": 0,
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


def _canonical_history(
    records: list[dict[str, object]],
    *,
    record_count: int | None = None,
) -> dict[str, object]:
    return {
        "schema": "d3_plan_history_v1",
        "schema_version": 1,
        "episode_id": "canonical-history-test",
        "scenario_name": "M3N1_history",
        "record_count": len(records) if record_count is None else record_count,
        "history": records,
    }


def _d2_evidence_row_and_aggregate(
    tmp_path: Path,
    *,
    assessment: dict[str, object] | None,
    schema_version: str = "d2-p1-identity-calibration/v2",
) -> tuple[dict[str, str], dict[str, object], str]:
    decision: dict[str, object] = {
        "selected_online_path": "baseline_gnn_hungarian",
        "default_online_path_changed": False,
        "promotion_recommended": False,
        "candidate_assessments": [] if assessment is None else [assessment],
    }
    if schema_version.endswith("/v2"):
        decision["policy_version"] = (
            "d2-p1-identity-admission/ceiling-aware-error-reduction-v1"
        )
    payload = {
        "schema_version": schema_version,
        "decision": decision,
        "confirmation": {
            "results": [
                {
                    "config": {"config_id": "candidate"},
                    "associator": "GNNHungarianAssociator",
                    "per_seed": [
                        {
                            "seed": 7,
                            "id_switch_count": 1,
                            "identity_continuity": 0.984,
                            "false_track_count": 1,
                            "p95_loop_latency_s": 0.024,
                            "online_truth_leakage_count": 0,
                        }
                    ],
                }
            ]
        },
    }
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1SystemEvidenceInputs(d2_difficulty_profiles=payload),
    )
    rows = list(csv.DictReader(outputs["rows_csv"].open(encoding="utf-8")))
    row = next(item for item in rows if item["source"] == "d2_difficulty_profiles")
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    return row, aggregate, markdown


@pytest.fixture
def d2_ceiling_aware_v2_payload() -> dict[str, object]:
    policy = "d2-p1-identity-admission/ceiling-aware-error-reduction-v1"

    def assessment(
        difficulty: str,
        *,
        associator: str = "GNNHungarianAssociator",
    ) -> dict[str, object]:
        passing = difficulty in {"overall", "clutter", "combined"}
        baseline_idsw = 1.0 if passing else 0.0
        candidate_id = (
            "candidate" if associator == "GNNHungarianAssociator" else "jpda-candidate"
        )
        return {
            "candidate_id": candidate_id,
            "associator": associator,
            "admission_policy_version": policy,
            "baseline_id_switch_mean": baseline_idsw,
            "candidate_id_switch_mean": 0.5 if passing else 0.0,
            "id_switch_reduction_fraction": 0.5 if passing else None,
            "baseline_identity_continuity": 0.98 if passing else 1.0,
            "candidate_identity_continuity": 0.985 if passing else 1.0,
            "identity_continuity_baseline_headroom": 0.02 if passing else 0.0,
            "identity_continuity_increase": 0.005 if passing else 0.0,
            "identity_continuity_required_increase": 0.002 if passing else 0.0,
            "identity_continuity_error_reduction_fraction": 0.25 if passing else None,
            "baseline_false_track_mean": 0.0,
            "candidate_false_track_mean": 0.0,
            "candidate_p95_loop_latency_s": 0.02,
            "gates": {
                "id_switch_reduction": {
                    "passed": passing,
                    "reason": (
                        "required_id_switch_reduction_met"
                        if passing
                        else "baseline_zero_no_measurable_reduction_evidence"
                    ),
                },
                "identity_continuity_ceiling_aware": {
                    "passed": True,
                    "reason": "required_continuity_error_reduction_met",
                },
                "false_track_limit": {
                    "passed": True,
                    "reason": "false_track_limit_met",
                },
                "p95_loop_latency_budget": {
                    "passed": True,
                    "reason": "p95_loop_latency_budget_met",
                },
                "truth_leakage_zero": {
                    "passed": True,
                    "reason": "online_truth_leakage_zero",
                    "candidate_count": 0,
                    "required_count": 0,
                },
            },
            "gate_reasons": {
                "id_switch_reduction": (
                    "required_id_switch_reduction_met"
                    if passing
                    else "baseline_zero_no_measurable_reduction_evidence"
                ),
                "identity_continuity_ceiling_aware": (
                    "required_continuity_error_reduction_met"
                ),
                "false_track_limit": "false_track_limit_met",
                "p95_loop_latency_budget": "p95_loop_latency_budget_met",
                "truth_leakage_zero": "online_truth_leakage_zero",
            },
            "all_thresholds_passed": passing,
        }

    overall_gnn = assessment("overall")
    overall_jpda = assessment(
        "nominal", associator="JPDAAssociatorResearchAdapter"
    )
    difficulties = (
        "clutter",
        "combined",
        "delayed_noisy",
        "dropout",
        "nominal",
        "tight_crossing",
    )
    return {
        "schema_version": "d2-p1-identity-calibration/v2",
        "default_online_path": "GNNHungarianAssociator",
        "default_online_path_changed": False,
        "decision": {
            "available": True,
            "policy_version": policy,
            "policy": {"promotion_effect": "review_recommendation_only"},
            "promotion_recommended": True,
            "promotion_candidates": ["candidate"],
            "selected_online_path": "baseline_gnn_hungarian",
            "default_online_path_changed": False,
            "candidate_assessments": [overall_gnn, overall_jpda],
            "by_difficulty": {
                difficulty: {
                    "available": True,
                    "promotion_recommended": difficulty in {"clutter", "combined"},
                    "promotion_candidates": (
                        ["candidate"] if difficulty in {"clutter", "combined"} else []
                    ),
                    "candidate_assessments": [assessment(difficulty)],
                }
                for difficulty in difficulties
            },
        },
        "screening": {
            "scenario_difficulties": list(difficulties),
            "offline_truth_alignment_availability_counts": {
                "complete": 5,
                "partial": 1,
                "unavailable": 0,
            },
            "offline_truth_unmatched_sample_count": 2,
            "offline_truth_alignment_by_case": {
                "dropout:1": {
                    "availability": "partial",
                    "matched_sample_count": 10,
                    "unmatched_sample_count": 2,
                    "online_truth_injected": False,
                }
            },
        },
        "confirmation": {
            "scenario_difficulties": list(difficulties),
            "offline_truth_alignment_availability_counts": {
                "complete": 10,
                "partial": 2,
                "unavailable": 0,
            },
            "offline_truth_unmatched_sample_count": 4,
            "offline_truth_alignment_by_case": {
                "dropout:1": {
                    "availability": "partial",
                    "matched_sample_count": 10,
                    "unmatched_sample_count": 2,
                    "online_truth_injected": False,
                },
                "dropout:2": {
                    "availability": "partial",
                    "matched_sample_count": 10,
                    "unmatched_sample_count": 2,
                    "online_truth_injected": False,
                },
            },
            "results": [
                {
                    "config": {"config_id": "candidate"},
                    "associator": "GNNHungarianAssociator",
                    "per_seed": [
                        {
                            "seed": 1,
                            "scenario_difficulty": "dropout",
                            "id_switch_count": 0,
                            "identity_continuity": 1.0,
                            "false_track_count": 0,
                            "p95_loop_latency_s": 0.02,
                            "online_truth_leakage_count": 0,
                            "offline_truth_alignment": {
                                "availability": "partial",
                                "unmatched_sample_count": 2,
                            },
                        }
                    ],
                }
            ],
        },
        "jpda_comparison": {"research_adapter_only": True},
    }


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
    assert aggregate["schema_version"] == "d6-p1-system-evidence-v2"
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
    assert d3["coalition_version_churn_count"] == "1"
    assert d3["coalition_epoch_churn_count"] == "1"
    for metric in D3_CHURN_METRICS:
        assert d3[f"{metric}_availability"] == "available"
    d4 = next(row for row in rows if row["source"] == "d4_episode_communication")
    assert d4["failover_count"] == "1"
    assert d4["ack_count"] == "2"
    assert d4["missing_ack_count"] == "1"
    assert d4["owner_change_count"] == "2"


def test_d2_v2_admission_preserves_ceiling_aware_fields_and_gate_reason(
    tmp_path,
) -> None:
    policy = "d2-p1-identity-admission/ceiling-aware-error-reduction-v1"
    row, aggregate, markdown = _d2_evidence_row_and_aggregate(
        tmp_path,
        assessment={
            "candidate_id": "candidate",
            "admission_policy_version": policy,
            "baseline_identity_continuity": 0.981,
            "candidate_identity_continuity": 0.982,
            "identity_continuity_baseline_headroom": 0.019,
            "identity_continuity_increase": 0.001,
            "identity_continuity_required_increase": 0.0019,
            "identity_continuity_error_reduction_fraction": 0.001 / 0.019,
            "gates": {
                "id_switch_reduction": {
                    "passed": True,
                    "reason": "required_id_switch_reduction_met",
                },
                "identity_continuity_ceiling_aware": {
                    "passed": False,
                    "reason": "insufficient_continuity_error_reduction",
                },
            },
            "checks": {
                "id_switch_reduction": True,
                "identity_continuity_ceiling_aware": False,
            },
            "gate_reasons": {
                "identity_continuity_ceiling_aware": (
                    "less_specific_fallback_must_not_win"
                )
            },
            "all_thresholds_passed": False,
        },
    )

    assert row["admission_policy_version"] == policy
    assert float(row["baseline_identity_continuity"]) == pytest.approx(0.981)
    assert float(row["identity_continuity_baseline_headroom"]) == pytest.approx(
        0.019
    )
    assert float(row["identity_continuity_increase"]) == pytest.approx(0.001)
    assert float(row["identity_continuity_required_increase"]) == pytest.approx(
        0.0019
    )
    assert float(
        row["identity_continuity_error_reduction_fraction"]
    ) == pytest.approx(0.001 / 0.019)
    assert row["all_thresholds_passed"] == "False"
    assert row["failure_reasons_availability"] == "available"
    assert json.loads(row["failure_reasons"]) == [
        "identity_continuity_ceiling_aware:insufficient_continuity_error_reduction"
    ]
    review = aggregate["d2_admission_review"]
    assert review["effect"] == "review_recommendation_only"
    assert review["changes_online_control"] is False
    assert review["changes_default_online_path"] is False
    assert review["records"][0]["identity_continuity_baseline_headroom"] == (
        pytest.approx(0.019)
    )
    assert policy in markdown
    assert "insufficient_continuity_error_reduction" in markdown


def test_d2_v2_passing_assessment_has_available_empty_failures(tmp_path) -> None:
    row, aggregate, _ = _d2_evidence_row_and_aggregate(
        tmp_path,
        assessment={
            "candidate_id": "candidate",
            "admission_policy_version": "d2-policy-v2",
            "baseline_identity_continuity": 0.981,
            "identity_continuity_baseline_headroom": 0.019,
            "identity_continuity_increase": 0.003,
            "identity_continuity_required_increase": 0.0019,
            "identity_continuity_error_reduction_fraction": 0.003 / 0.019,
            "gates": {
                "identity_continuity_ceiling_aware": {
                    "passed": True,
                    "reason": "required_continuity_error_reduction_met",
                }
            },
            "checks": {"identity_continuity_ceiling_aware": True},
            "all_thresholds_passed": True,
        },
    )

    assert row["association_admitted"] == "True"
    assert row["all_thresholds_passed"] == "True"
    assert row["failure_reasons_availability"] == "available"
    assert json.loads(row["failure_reasons"]) == []
    assert aggregate["d2_admission_review"]["status"] == "available"


@pytest.mark.parametrize(
    ("checks", "expected_reason"),
    [
        (
            {
                "identity_continuity_gain": {
                    "passed": False,
                    "reason": "legacy_absolute_gain_not_met",
                }
            },
            "identity_continuity_gain:legacy_absolute_gain_not_met",
        ),
        ({"identity_continuity_gain": False}, "identity_continuity_gain"),
    ],
)
def test_d2_legacy_structured_and_bool_checks_remain_supported(
    tmp_path,
    checks: dict[str, object],
    expected_reason: str,
) -> None:
    row, aggregate, _ = _d2_evidence_row_and_aggregate(
        tmp_path,
        schema_version="d2-p1-identity-calibration/v1",
        assessment={
            "candidate_id": "candidate",
            "checks": checks,
            "all_thresholds_passed": False,
        },
    )

    assert json.loads(row["failure_reasons"]) == [expected_reason]
    assert row["failure_reasons_availability"] == "available"
    assert row["admission_policy_version"] == ""
    assert row["admission_policy_version_availability"] == "unavailable"
    assert aggregate["d2_admission_review"]["records"][0][
        "admission_policy_version"
    ] is None


def test_d2_missing_admission_fields_stay_unavailable_and_never_become_zero(
    tmp_path,
) -> None:
    row, aggregate, markdown = _d2_evidence_row_and_aggregate(
        tmp_path,
        schema_version="d2-p1-identity-calibration/v1",
        assessment={
            "candidate_id": "candidate",
            "all_thresholds_passed": False,
        },
    )

    for name in (
        "admission_policy_version",
        "baseline_identity_continuity",
        "identity_continuity_baseline_headroom",
        "identity_continuity_increase",
        "identity_continuity_required_increase",
        "identity_continuity_error_reduction_fraction",
    ):
        assert row[name] == ""
        assert row[f"{name}_availability"] == "unavailable"
    assert row["all_thresholds_passed"] == "False"
    assert row["failure_reasons"] == "[]"
    assert row["failure_reasons_availability"] == "unavailable"
    record = aggregate["d2_admission_review"]["records"][0]
    assert record["baseline_identity_continuity"] is None
    assert record["identity_continuity_baseline_headroom"] is None
    assert record["failure_reasons_availability"] == "unavailable"
    assert "unavailable" in markdown


def test_d2_v2_source_decision_and_alignment_are_preserved_without_recalculation(
    tmp_path: Path,
    d2_ceiling_aware_v2_payload: dict[str, object],
) -> None:
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1SystemEvidenceInputs(
            d2_difficulty_profiles=d2_ceiling_aware_v2_payload
        ),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    review = aggregate["d2_admission_review"]

    assert review["source_schema_version"] == "d2-p1-identity-calibration/v2"
    assert review["source_decision_status"] == "available"
    assert review["promotion_recommended"] is True
    assert review["promotion_candidates"] == ["candidate"]
    assert review["selected_online_path"] == "baseline_gnn_hungarian"
    assert review["default_online_path"] == "GNNHungarianAssociator"
    assert review["default_online_path_changed"] is False
    assert review["producer_decision_recalculated_by_d6"] is False
    assert review["record_count"] == 8
    assert review["by_difficulty"]["clutter"]["promotion_recommended"] is True
    assert review["by_difficulty"]["dropout"]["promotion_recommended"] is False
    dropout = review["truth_alignment_summary"]["stages"]["confirmation"][
        "by_difficulty"
    ]["dropout"]
    assert dropout["availability_counts"] == {
        "complete": 0,
        "partial": 2,
        "unavailable": 0,
    }
    assert dropout["matched_sample_count"] == 20
    assert dropout["unmatched_sample_count"] == 4
    assert review["jpda_research_adapter_only"] is True

    rows = list(csv.DictReader(outputs["rows_csv"].open(encoding="utf-8")))
    overall = next(
        row
        for row in rows
        if row["family"] == "association_admission_assessment"
        and row["assessment_scope"] == "overall"
        and row["associator"] == "GNNHungarianAssociator"
    )
    assert overall["promotion_recommended"] == "True"
    assert overall["default_online_path_changed"] == "False"
    assert json.loads(overall["admission_gate_reasons"])[
        "truth_leakage_zero"
    ] == "online_truth_leakage_zero"

    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "总体 GNN 候选五项 gate" in markdown
    assert "分档仅 `clutter, combined` 通过" in markdown
    assert "baseline IDSW=0" in markdown
    assert "Dropout truth alignment" in markdown
    assert "research_adapter_only=true" in markdown
    assert "default_online_path_changed=false" in markdown
    assert "D2-only 证据不得表述为全系统通过" in markdown


def test_d2_legacy_missing_source_decision_fields_remain_unavailable(
    tmp_path: Path,
) -> None:
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1SystemEvidenceInputs(
            d2_difficulty_profiles={
                "schema_version": "d2-p1-identity-calibration/v1",
                "profiles": [
                    {
                        "scenario_difficulty": "legacy",
                        "candidate": "legacy",
                        "id_switch_count": 0,
                    }
                ],
            }
        ),
    )
    review = json.loads(
        outputs["aggregate_json"].read_text(encoding="utf-8")
    )["d2_admission_review"]

    assert review["source_decision_status"] == "unavailable"
    assert review["promotion_recommended"] is None
    assert review["promotion_candidates"] is None
    assert review["selected_online_path"] is None
    assert review["default_online_path_changed"] is None
    assert review["by_difficulty"] is None
    assert review["truth_alignment_summary"]["status"] == "unavailable"
    assert review["producer_decision_recalculated_by_d6"] is False


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


def test_d3_final_snapshot_does_not_infer_zero_churn(tmp_path) -> None:
    row = _d3_row(
        tmp_path,
        {
            "schema_version": "d3-assignment-plan-v1",
            "version": 7,
            "metadata": {"membership_change_records": []},
            "coalitions": [{"coalition_id": "C1", "version": 4, "epoch": 4}],
        },
    )

    for metric in D3_CHURN_METRICS:
        assert row[metric] == ""
        assert row[f"{metric}_availability"] == "unavailable"


def test_d3_empty_input_keeps_churn_unavailable(tmp_path) -> None:
    row = _d3_row(tmp_path, {})

    for metric in D3_CHURN_METRICS:
        assert row[metric] == ""
        assert row[f"{metric}_availability"] == "unavailable"


def test_d3_single_unordered_record_does_not_infer_zero_churn(tmp_path) -> None:
    row = _d3_row(
        tmp_path,
        {
            "records": [
                {
                    "version": 7,
                    "metadata": {"membership_change_records": []},
                    "coalitions": [
                        {"coalition_id": "C1", "version": 4, "epoch": 4}
                    ],
                }
            ]
        },
    )

    for metric in D3_CHURN_METRICS:
        assert row[metric] == ""
        assert row[f"{metric}_availability"] == "unavailable"


def test_d3_two_stable_ordered_history_records_report_available_zero_churn(
    tmp_path,
) -> None:
    row = _d3_row(
        tmp_path,
        {
            "schema_version": "d3-plan-history-v1",
            "history": [
                {
                    "version": 7,
                    "metadata": {"membership_change_records": []},
                    "coalitions": [
                        {"coalition_id": "C1", "version": 4, "epoch": 4}
                    ],
                },
                {
                    "version": 7,
                    "metadata": {"membership_change_records": []},
                    "coalitions": [
                        {"coalition_id": "C1", "version": 4, "epoch": 4}
                    ],
                },
            ],
        },
    )

    for metric in D3_CHURN_METRICS:
        assert row[metric] == "0"
        assert row[f"{metric}_availability"] == "available"


def test_d3_explicit_zero_churn_is_available_without_history(tmp_path) -> None:
    row = _d3_row(
        tmp_path,
        {metric: 0 for metric in D3_CHURN_METRICS},
    )

    for metric in D3_CHURN_METRICS:
        assert row[metric] == "0"
        assert row[f"{metric}_availability"] == "available"


def test_d3_canonical_stable_history_reports_explicit_zero_without_truth(
    tmp_path,
) -> None:
    payload = _canonical_history(
        [
            _canonical_history_record(0, 0.0),
            _canonical_history_record(1, 1.0),
        ]
    )
    assert "truth" not in json.dumps(payload, sort_keys=True).lower()

    row = _d3_row(tmp_path, payload)

    assert row["family"] == "canonical_ordered_plan_history"
    assert row["d3_history_validation_status"] == "available"
    assert json.loads(row["d3_history_validation_reasons"]) == []
    assert row["d3_history_record_count"] == "2"
    for metric in D3_CANONICAL_HISTORY_METRICS:
        assert row[metric] == "0"
        assert row[f"{metric}_availability"] == "available"


def test_d3_canonical_history_counts_plan_and_coalition_version_changes(
    tmp_path,
) -> None:
    row = _d3_row(
        tmp_path,
        _canonical_history(
            [
                _canonical_history_record(0, 0.0),
                _canonical_history_record(
                    1,
                    1.0,
                    plan_version=2,
                    coalition_version=2,
                    coalition_epoch=2,
                ),
            ]
        ),
    )

    assert row["plan_version_churn_count"] == "1"
    assert row["coalition_version_churn_count"] == "1"
    assert row["coalition_epoch_churn_count"] == "1"
    assert row["membership_change_count"] == "0"


def test_d3_canonical_history_counts_membership_owner_and_feedback_changes(
    tmp_path,
) -> None:
    changed_assignments = [
        _canonical_assignment("R3", role="primary", activation_state="active"),
        _canonical_assignment("R2", role="reserve", activation_state="active"),
    ]
    row = _d3_row(
        tmp_path,
        _canonical_history(
            [
                _canonical_history_record(0, 0.0, soft_count=1),
                _canonical_history_record(
                    1,
                    1.0,
                    assignments=changed_assignments,
                    active_plan_owner="secondary",
                    owner_node_id="SECONDARY-1",
                    soft_count=2,
                    hard_count=1,
                ),
            ]
        ),
    )

    assert row["membership_change_count"] == "3"
    assert row["primary_membership_change_count"] == "2"
    assert row["reserve_membership_change_count"] == "1"
    assert row["owner_change_count"] == "1"
    assert row["soft_feedback_count"] == "3"
    assert row["hard_feedback_count"] == "1"


@pytest.mark.parametrize(
    ("records", "expected_reason"),
    [
        (
            [
                _canonical_history_record(1, 0.0),
                _canonical_history_record(0, 1.0),
            ],
            "sequence_index_non_monotonic",
        ),
        (
            [
                _canonical_history_record(0, 0.0),
                _canonical_history_record(0, 1.0),
            ],
            "sequence_index_duplicate",
        ),
        (
            [
                _canonical_history_record(0, 1.0),
                _canonical_history_record(1, 0.5),
            ],
            "timestamp_regression",
        ),
    ],
)
def test_d3_canonical_invalid_order_keeps_history_metrics_unavailable(
    tmp_path,
    records: list[dict[str, object]],
    expected_reason: str,
) -> None:
    row = _d3_row(tmp_path, _canonical_history(records))

    assert row["d3_history_validation_status"] == "unavailable"
    assert expected_reason in json.loads(row["d3_history_validation_reasons"])
    for metric in D3_CANONICAL_HISTORY_METRICS:
        assert row[metric] == ""
        assert row[f"{metric}_availability"] == "unavailable"


def test_d3_canonical_single_record_history_is_unavailable_with_reason(
    tmp_path,
) -> None:
    row = _d3_row(
        tmp_path,
        _canonical_history([_canonical_history_record(0, 0.0)]),
    )

    assert row["d3_history_validation_status"] == "unavailable"
    assert "history_requires_at_least_two_records" in json.loads(
        row["d3_history_validation_reasons"]
    )
    for metric in D3_CANONICAL_HISTORY_METRICS:
        assert row[metric] == ""


@pytest.mark.parametrize(
    ("mutator", "expected_reason"),
    [
        (
            lambda payload: payload["history"][1].update(
                {"schema": "wrong_history_record"}
            ),
            "history_record_schema_mismatch",
        ),
        (
            lambda payload: payload.update({"record_count": 3}),
            "history_record_count_mismatch",
        ),
        (
            lambda payload: payload["history"][1].update(
                {"ordering_key": [99, 1.0]}
            ),
            "ordering_key_mismatch",
        ),
        (
            lambda payload: payload["history"][1].pop("total_cost"),
            "history_record_missing_field:total_cost",
        ),
    ],
)
def test_d3_canonical_schema_errors_report_reason_and_no_false_zero(
    tmp_path,
    mutator,
    expected_reason: str,
) -> None:
    payload = _canonical_history(
        [_canonical_history_record(0, 0.0), _canonical_history_record(1, 1.0)]
    )
    mutator(payload)

    row = _d3_row(tmp_path, payload)

    assert expected_reason in json.loads(row["d3_history_validation_reasons"])
    for metric in D3_CANONICAL_HISTORY_METRICS:
        assert row[metric] == ""


def test_d3_canonical_validation_reason_reaches_json_and_markdown(tmp_path) -> None:
    payload = _canonical_history(
        [_canonical_history_record(0, 0.0), _canonical_history_record(0, 1.0)]
    )
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        tmp_path,
        inputs=P1SystemEvidenceInputs(d3_assignment_churn=payload),
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    validation = aggregate["d3_history_validation"]
    assert validation["status"] == "unavailable"
    assert validation["record_count"] == 2
    assert "sequence_index_duplicate" in validation["reasons"]
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "D3 canonical plan history" in markdown
    assert "sequence_index_duplicate" in markdown


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
    for metric in D3_CHURN_METRICS:
        assert d3[metric]["status"] == "unavailable"

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
