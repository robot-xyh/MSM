from dataclasses import replace

from d3_assignment_planner import (
    Assignment,
    AssignmentPlan,
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    SECONDARY_PLAN_SCHEMA_V2,
    TargetTrack,
    assignment_records_from_plan,
    assignment_validity_summary_from_plan,
    prepare_secondary_takeover_plan,
)


def test_assignment_validity_summary_exports_required_fields() -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    tracks = [
        TargetTrack("T1", threat_score=0.9, covariance=0.1, window_cost=0.1),
        TargetTrack("T2", threat_score=0.8, covariance=0.1, window_cost=0.1),
    ]

    plan = planner.plan(tracks, [ResourceState("R1")], timestamp=10.0)
    summary = assignment_validity_summary_from_plan(
        plan,
        evaluated_at=12.5,
        latest_version=2,
        assignment_latency_s=0.25,
        tracks=tracks,
        high_threat_threshold=0.7,
    )

    assert summary.plan_id == plan.plan_id
    assert summary.version == 1
    assert summary.plan_age_s == 2.5
    assert summary.assignment_latency_s == 0.25
    assert summary.cost_margin == 0.0
    assert summary.stale_plan_version is True
    assert summary.duplicate_assignment_count == 0
    assert summary.unassigned_high_threat_count == 1
    assert summary.resource_count == 1
    assert summary.target_count == 2


def test_assignment_validity_summary_counts_duplicate_targets_and_resources() -> None:
    plan = AssignmentPlan(
        plan_id="manual-plan",
        version=3,
        window_id=3,
        assignments=(
            Assignment("T1", "R1", 1.0, {"total": 1.0}),
            Assignment("T1", "R2", 1.0, {"total": 1.0}),
            Assignment("T2", "R2", 1.0, {"total": 1.0}),
        ),
        unassigned_target_ids=(),
        total_cost=3.0,
        created_at=2.0,
        last_changed_at=2.0,
        candidate_total_cost=2.0,
        previous_total_cost_current=5.0,
    )

    summary = assignment_validity_summary_from_plan(
        plan,
        evaluated_at=3.0,
        latest_version=3,
        latest_plan_id="manual-plan",
    )

    assert summary.cost_margin == 3.0
    assert summary.stale_plan_version is False
    assert summary.duplicate_assignment_count == 2


def test_assignment_records_from_plan_match_d6_assignment_record_shape() -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    plan = planner.plan(
        [TargetTrack("T1", threat_score=0.9, covariance=0.1, window_cost=0.1)],
        [ResourceState("R1")],
        timestamp=4.0,
    )

    records = assignment_records_from_plan(
        plan,
        timestamp=4.2,
        truth_id_by_target={"T1": "truth-1"},
    )

    assert len(records) == 1
    record = records[0]
    assert record.timestamp == 4.2
    assert record.plan_id == plan.plan_id
    assert record.version == plan.version
    assert record.resource_id == "R1"
    assert record.global_track_id == "T1"
    assert record.authorization_state == "recorded"
    assert record.active is True
    assert record.truth_id == "truth-1"
    assert record.window_id == plan.window_id
    assert record.decision_state == "accepted"
    assert record.changed is True
    assert record.resource_count == 1
    assert record.target_count == 1
    assert record.assignment_matrix_shape == (1, 1)
    assert record.plan_owner == "center"
    assert record.active_plan_owner == "center"
    assert record.owner_node_id == "d3_central"
    assert record.source_node_id == "d3_central"
    assert record.target_node_id == "R1"
    assert record.link_type == "c2_direct"
    assert record.plan_schema == "assignment_plan_v1"
    assert record.replan_reason is None
    assert record.takeover_reason is None
    assert record.previous_plan_id is None
    assert record.previous_plan_version is None
    assert record.total_cost == plan.total_cost
    assert record.candidate_total_cost == plan.candidate_total_cost
    assert record.previous_total_cost_current == plan.previous_total_cost_current
    assert record.cost_margin == 0.0


def test_assignment_records_can_preserve_plan_authorization_state() -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    plan = planner.plan(
        [TargetTrack("T1", threat_score=0.9, covariance=0.1, window_cost=0.1)],
        [ResourceState("R1")],
        timestamp=4.0,
    )
    plan = replace(plan, human_authorization_state="required")

    records = assignment_records_from_plan(plan, authorization_state=None)

    assert records[0].authorization_state == "required"


def test_center_replan_assignment_records_export_current_plan_fields() -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    first = planner.plan(
        [TargetTrack("T1", threat_score=0.9, covariance=0.1, window_cost=0.1)],
        [ResourceState("R1")],
        timestamp=4.0,
        window_id=10,
    )
    second = planner.plan(
        [TargetTrack("T1", threat_score=0.9, covariance=0.1, window_cost=0.1)],
        [ResourceState("R1")],
        timestamp=5.0,
        previous_plan=first,
        window_id=11,
    )
    second = replace(
        second,
        metadata={
            **dict(second.metadata),
            "active_plan_owner": "center",
            "replan_reason": "request_center_replan",
            "supersedes_plan_id": first.plan_id,
            "supersedes_plan_version": first.version,
        },
    )

    (record,) = assignment_records_from_plan(second)

    assert record.version == first.version + 1
    assert record.window_id == 11
    assert record.decision_state == "accepted_no_hysteresis"
    assert record.changed is False
    assert record.plan_owner == "center"
    assert record.active_plan_owner == "center"
    assert record.replan_reason == "request_center_replan"
    assert record.previous_plan_id == first.plan_id
    assert record.previous_plan_version == first.version
    assert record.supersedes_plan_id == first.plan_id
    assert record.supersedes_plan_version == first.version
    assert record.resource_count == 1
    assert record.target_count == 1
    assert record.assignment_matrix_shape == (1, 1)


def test_secondary_takeover_assignment_records_export_owner_fields() -> None:
    center_plan = AssignmentPlan(
        plan_id="CENTER-PLAN-004",
        version=4,
        window_id=40,
        assignments=(
            Assignment("T1", "R1", 1.0, {"total": 1.0}, plan_version=4),
        ),
        unassigned_target_ids=(),
        total_cost=1.0,
        created_at=4.0,
        last_changed_at=4.0,
        source_node_id="center-c2",
        target_node_id="interceptor-group",
        link_type="c2_direct",
        resource_count=1,
        target_count=1,
        metadata={
            "active_plan_owner": "center",
            "assignment_matrix_shape": [1, 1],
        },
    )
    secondary_candidate = AssignmentPlan(
        plan_id="SECONDARY-PLAN-005",
        version=5,
        window_id=41,
        assignments=(
            Assignment("T2", "R1", 1.2, {"total": 1.2}, plan_version=5),
        ),
        unassigned_target_ids=(),
        total_cost=1.2,
        created_at=5.0,
        last_changed_at=5.0,
        previous_plan_id=center_plan.plan_id,
        source_node_id="secondary-node-2",
        target_node_id="interceptor-group",
        link_type="d4_secondary_relay",
        resource_count=1,
        target_count=1,
        metadata={"assignment_matrix_shape": [1, 1]},
    )
    secondary_plan = prepare_secondary_takeover_plan(
        secondary_candidate,
        supersedes_plan=center_plan,
        secondary_node_id="secondary-node-2",
        lease_expires_at_s=9.0,
        leader_epoch=12,
    )

    (record,) = assignment_records_from_plan(secondary_plan)

    assert record.plan_schema == SECONDARY_PLAN_SCHEMA_V2
    assert record.plan_owner == "secondary"
    assert record.active_plan_owner == "secondary"
    assert record.takeover_reason == "d4_degrade_to_secondary"
    assert record.owner_node_id == "secondary-node-2"
    assert record.source_node_id == "secondary-node-2"
    assert record.target_node_id == "R1"
    assert record.link_type == "d4_secondary_relay"
    assert record.previous_plan_id == center_plan.plan_id
    assert record.previous_plan_version == center_plan.version
    assert record.supersedes_plan_id == center_plan.plan_id
    assert record.supersedes_plan_version == center_plan.version
    assert record.resource_count == 1
    assert record.target_count == 1
    assert record.assignment_matrix_shape == (1, 1)
