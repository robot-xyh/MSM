from dataclasses import replace

from d3_assignment_planner import (
    Assignment,
    AssignmentPlan,
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    TargetTrack,
    assignment_records_from_plan,
    assignment_validity_summary_from_plan,
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
