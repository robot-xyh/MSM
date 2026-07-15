import json
from dataclasses import replace

import pytest

from d3_assignment_planner import (
    PLAN_HISTORY_RECORD_SCHEMA_V1,
    AssignmentPlanner,
    PlannerConfig,
    PlanningTickHistoryRecord,
    ResourceState,
    TargetDemand,
    TargetTrack,
    plan_history_record_from_plan,
)


def _assert_no_truth_keys(value: object) -> None:
    if isinstance(value, dict):
        assert all("truth" not in str(key).lower() for key in value)
        for item in value.values():
            _assert_no_truth_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_truth_keys(item)


def _hybrid_plan():
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=True,
            solver_name="hungarian_demand_slots",
            human_authorization_state="approved",
            delta=0.2,
            min_dwell=2.0,
        )
    )
    return planner.plan(
        [
            TargetTrack(
                "T-HIGH",
                threat_score=0.95,
                covariance=0.1,
                window_cost=0.1,
                demand=TargetDemand(),
            )
        ],
        [ResourceState("R3"), ResourceState("R1"), ResourceState("R2")],
        timestamp=10.0,
        window_id=7,
    )


def test_plan_history_record_exports_ordered_primary_reserve_and_tick_state() -> None:
    plan = _hybrid_plan()
    annotated = replace(
        plan,
        assignments=tuple(reversed(plan.assignments)),
        candidate_total_cost=1.25,
        previous_total_cost_current=2.5,
        source_node_id="secondary-2",
        previous_plan_id="center-plan-4",
        metadata={
            **dict(plan.metadata),
            "plan_owner": "secondary",
            "active_plan_owner": "secondary",
            "owner_node_id": "secondary-2",
            "source_node_id": "secondary-2",
            "selected_secondary_node_id": "secondary-2",
            "secondary_plan_version": 8,
            "secondary_leader_epoch": 3,
            "secondary_lease_expires_at_s": 30.0,
            "previous_plan_version": 4,
            "supersedes_plan_id": "center-plan-4",
            "supersedes_plan_version": 4,
            "hysteresis_state": "held",
            "hysteresis_reason": "coalition_membership_hold",
            "hysteresis_reasons": ("insufficient_gain", "min_dwell_not_met"),
            "hysteresis_dwell_time_s": 1.25,
            "hysteresis_min_dwell_s": 2.0,
            "hysteresis_delta": 0.2,
            "hysteresis_candidate_change_count": 1,
            "hysteresis_max_changes_per_window": 2,
            "hysteresis_improvement_ok": False,
            "hysteresis_dwell_ok": False,
            "hysteresis_change_limit_ok": True,
            "membership_change_records": (
                {
                    "target_id": "T-HIGH",
                    "previous_members": (("R1", "primary"),),
                    "current_members": (("R2", "primary"),),
                    "membership_dwell_s": 1.25,
                    "membership_change_reason": "coalition_membership_hold",
                    "truth_id": "must-not-leak",
                },
            ),
            "replan_reason": "feedback_cost_refresh",
            "truth_id_by_target": {"T-HIGH": "must-not-leak"},
        },
    )
    feedback_metadata = {
        "feedback_constraint_classification_schema": (
            "d3_feedback_constraint_classification_v1"
        ),
        "feedback_classifications": (
            {
                "target_id": "T-HIGH",
                "resource_id": "R2",
                "terminal_feedback_state": "mismatch",
                "constraint_class": "resource_target_edge_hard",
                "constraint_scope": "resource_target_edge",
                "classification_reason": "safety_identity_conflict",
                "hard_reject": True,
                "truth_id": "must-not-leak",
            },
            {
                "target_id": "T-HIGH",
                "resource_id": "R1",
                "terminal_feedback_state": "ambiguous",
                "constraint_class": "resource_target_edge_soft",
                "constraint_scope": "resource_target_edge",
                "classification_reason": "ordinary_terminal_uncertainty",
                "hard_reject": False,
            },
        ),
    }

    record = plan_history_record_from_plan(
        annotated,
        sequence_index=12,
        timestamp=12.5,
        feedback_metadata=feedback_metadata,
    )
    payload = record.to_dict()

    assert isinstance(record, PlanningTickHistoryRecord)
    assert payload["schema"] == PLAN_HISTORY_RECORD_SCHEMA_V1
    assert payload["schema_version"] == 1
    assert payload["sequence_index"] == 12
    assert payload["ordering_key"] == [12, 12.5]
    assert payload["timestamp"] == 12.5
    assert payload["plan_id"] == plan.plan_id
    assert payload["plan_version"] == plan.version
    assert payload["window_id"] == 7
    assert payload["changed"] is True
    assert payload["decision_state"] == "accepted"
    assert (
        payload["resource_count"],
        payload["target_count"],
        payload["assigned_count"],
    ) == (3, 1, 3)
    assert payload["plan_owner"] == "secondary"
    assert payload["active_plan_owner"] == "secondary"
    assert payload["owner_node_id"] == "secondary-2"
    assert payload["source_node_id"] == "secondary-2"
    assert payload["secondary_plan_version"] == 8
    assert payload["secondary_leader_epoch"] == 3
    assert payload["secondary_lease_expires_at_s"] == 30.0
    assert payload["previous_plan_id"] == "center-plan-4"
    assert payload["previous_plan_version"] == 4
    assert payload["supersedes_plan_id"] == "center-plan-4"
    assert payload["supersedes_plan_version"] == 4

    assignments = payload["assignments"]
    assert [item["member_role"] for item in assignments] == [
        "primary",
        "primary",
        "reserve",
    ]
    assert [item["activation_state"] for item in assignments] == [
        "active",
        "active",
        "standby",
    ]
    assert [item["active"] for item in assignments] == [True, True, False]
    assert [item["assignment_validity_state"] for item in assignments] == [
        "current",
        "current",
        "standby",
    ]
    assert all(item["coalition_id"] == plan.coalitions[0].coalition_id for item in assignments)
    assert all(item["coalition_version"] == plan.coalitions[0].version for item in assignments)
    assert all(item["coalition_epoch"] == plan.coalitions[0].epoch for item in assignments)
    assert all(isinstance(item["cost"], float) for item in assignments)
    assert all("total" in item["cost_breakdown"] for item in assignments)

    (coalition,) = payload["coalitions"]
    assert coalition["coalition_id"] == plan.coalitions[0].coalition_id
    assert coalition["version"] == plan.coalitions[0].version
    assert coalition["epoch"] == plan.coalitions[0].epoch
    assert coalition["complete"] is True
    assert [item["member_role"] for item in coalition["members"]] == [
        "primary",
        "primary",
        "reserve",
    ]

    assert payload["hysteresis"]["state"] == "held"
    assert payload["hysteresis"]["reason"] == "coalition_membership_hold"
    assert payload["hysteresis"]["dwell_time_s"] == 1.25
    assert payload["hysteresis"]["min_dwell_s"] == 2.0
    assert payload["hysteresis"]["delta"] == 0.2
    assert payload["hysteresis"]["dwell_ok"] is False
    assert payload["membership_change_records"][0]["target_id"] == "T-HIGH"
    assert payload["feedback_constraints"]["soft_count"] == 1
    assert payload["feedback_constraints"]["hard_count"] == 1
    assert [
        item["resource_id"]
        for item in payload["feedback_constraints"]["classifications"]
    ] == ["R1", "R2"]
    assert payload["total_cost"] == plan.total_cost
    assert payload["candidate_total_cost"] == 1.25
    assert payload["previous_total_cost_current"] == 2.5
    assert payload["replan_reason"] == "feedback_cost_refresh"

    serialized = json.dumps(payload, allow_nan=False, sort_keys=True)
    assert json.loads(serialized) == payload
    _assert_no_truth_keys(payload)


def test_plan_history_record_supports_legacy_feedback_metadata_and_audit_reasons() -> None:
    plan = _hybrid_plan()
    annotated = replace(
        plan,
        metadata={
            **dict(plan.metadata),
            "terminal_feedback_events": (
                {
                    "target_id": "T-HIGH",
                    "resource_id": "R3",
                    "terminal_feedback_state": "friend_overlap_hold",
                    "feedback_constraint_class": "resource_hard",
                    "feedback_constraint_scope": "resource",
                    "feedback_classification_reason": "friend_overlap_hold",
                },
            ),
            "stale_plan_rejected": True,
            "stale_reject_reason": "stale_previous_version",
            "latest_plan_id": "latest-plan",
            "latest_plan_version": 9,
            "plan_rollback_detected": True,
            "plan_rollback_reason": "version_regression",
            "replan_reason": "terminal_friend_conflict",
        },
    )

    payload = plan_history_record_from_plan(
        annotated,
        sequence_index=13,
        timestamp=13.0,
    ).to_dict()

    feedback = payload["feedback_constraints"]
    assert feedback["resource_hard_count"] == 1
    assert feedback["hard_count"] == 1
    assert feedback["classifications"][0]["constraint_class"] == "resource_hard"
    assert feedback["classifications"][0]["classification_reason"] == (
        "friend_overlap_hold"
    )
    assert payload["stale_plan_rejected"] is True
    assert payload["stale_reject_reason"] == "stale_previous_version"
    assert payload["latest_plan_id"] == "latest-plan"
    assert payload["latest_plan_version"] == 9
    assert payload["rollback_detected"] is True
    assert payload["rollback_reason"] == "version_regression"
    assert payload["replan_reason"] == "terminal_friend_conflict"
    assert {item["assignment_validity_state"] for item in payload["assignments"]} == {
        "stale"
    }


@pytest.mark.parametrize(
    ("sequence_index", "timestamp", "error"),
    ((-1, 1.0, ValueError), (True, 1.0, TypeError), (1, float("nan"), ValueError)),
)
def test_plan_history_record_rejects_invalid_ordering_inputs(
    sequence_index: object,
    timestamp: float,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        plan_history_record_from_plan(
            _hybrid_plan(),
            sequence_index=sequence_index,  # type: ignore[arg-type]
            timestamp=timestamp,
        )
