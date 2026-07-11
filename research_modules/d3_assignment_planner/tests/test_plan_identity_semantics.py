from dataclasses import replace

import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    StalePlanError,
    TargetDemand,
    TargetTrack,
    assignment_evidence_from_plan,
    assignment_records_from_plan,
    guidance_bindings_from_assignment_plan,
    prepare_secondary_takeover_plan,
)


def _planner() -> AssignmentPlanner:
    return AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))


def _track(
    target_id: str = "T1",
    *,
    demand: TargetDemand | None = None,
    preferred: str = "R1",
) -> TargetTrack:
    return TargetTrack(
        target_id,
        threat_score=0.9,
        covariance=0.1,
        window_cost=0.1,
        demand=demand,
        fov_difficulty_by_resource={
            "R1": 0.0 if preferred == "R1" else 1.0,
            "R2": 0.0 if preferred == "R2" else 1.0,
            "R3": 0.2,
            "R4": 0.3,
        },
    )


def test_identical_refresh_preserves_plan_and_assignment_identity() -> None:
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=False,
            stale_after_s=2.0,
            human_authorization_state="approved",
        )
    )
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan([_track()], resources, timestamp=0.0, window_id=4)
    refreshed = planner.plan(
        [_track()],
        resources,
        timestamp=5.0,
        previous_plan=first,
        window_id=5,
    )

    assert refreshed.execution_signature() == first.execution_signature()
    assert refreshed.plan_id == first.plan_id
    assert refreshed.version == first.version
    assert refreshed.created_at == first.created_at == 0.0
    assert refreshed.changed is False
    assert first.metadata["identity_created_at_s"] == 0.0
    assert first.metadata["last_evaluated_at_s"] == 0.0
    assert refreshed.metadata["identity_created_at_s"] == 0.0
    assert refreshed.metadata["last_evaluated_at_s"] == 5.0
    assert {item.plan_version for item in refreshed.assignments} == {first.version}
    assert {
        item.metadata["identity_created_at_s"] for item in refreshed.assignments
    } == {0.0}
    assert {
        item.metadata["last_evaluated_at_s"] for item in refreshed.assignments
    } == {5.0}
    assert refreshed.metadata["current_plan_id"] == first.plan_id
    assert refreshed.metadata["current_plan_version"] == first.version

    (record,) = assignment_records_from_plan(refreshed)
    evidence = assignment_evidence_from_plan(refreshed)
    (binding,) = guidance_bindings_from_assignment_plan(refreshed, now_s=6.0)
    assert record.timestamp == 5.0
    assert record.identity_created_at_s == 0.0
    assert record.last_evaluated_at_s == 5.0
    assert evidence.identity_created_at_s == 0.0
    assert evidence.last_evaluated_at_s == 5.0
    assert binding.metadata["identity_created_at_s"] == 0.0
    assert binding.metadata["last_evaluated_at_s"] == 5.0
    assert binding.binding_state == "active"
    assert binding.expires_at_s == 7.0


def test_forced_replan_distinguishes_ack_from_applied() -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan([_track()], resources, timestamp=0.0)
    acknowledged = planner.plan(
        [_track()],
        resources,
        timestamp=1.0,
        previous_plan=first,
        forced_replan=True,
    )
    applied = planner.plan(
        [_track(preferred="R2")],
        resources,
        timestamp=2.0,
        previous_plan=acknowledged,
        forced_replan=True,
    )

    assert acknowledged.decision_state == "replan_ack_no_change"
    assert acknowledged.metadata["replan_response_state"] == "replan_ack_no_change"
    assert acknowledged.plan_id == first.plan_id
    assert acknowledged.version == first.version
    assert acknowledged.created_at == 0.0
    assert acknowledged.metadata["identity_created_at_s"] == 0.0
    assert acknowledged.metadata["last_evaluated_at_s"] == 1.0
    assert {
        item.metadata["last_evaluated_at_s"] for item in acknowledged.assignments
    } == {1.0}
    assert acknowledged.changed is False
    assert applied.decision_state == "replan_applied"
    assert applied.metadata["replan_response_state"] == "replan_applied"
    assert applied.plan_id != first.plan_id
    assert applied.version == first.version + 1
    assert applied.created_at == 2.0
    assert applied.metadata["identity_created_at_s"] == 2.0
    assert applied.metadata["last_evaluated_at_s"] == 2.0
    assert {
        (
            item.metadata["identity_created_at_s"],
            item.metadata["last_evaluated_at_s"],
        )
        for item in applied.assignments
    } == {(2.0, 2.0)}
    assert applied.changed is True


def test_m_to_n_member_change_advances_once_then_stabilizes() -> None:
    planner = _planner()
    demand = TargetDemand(
        required_resource_count=3,
        primary_resource_count=2,
        coordination_mode="hybrid",
        arrival_window_start_s=5.0,
        arrival_window_end_s=8.0,
    )
    first_resources = [ResourceState(f"R{i}") for i in range(1, 4)]
    second_resources = [ResourceState(f"R{i}") for i in range(2, 5)]
    first = planner.plan([_track(demand=demand)], first_resources, timestamp=0.0)
    changed = planner.plan(
        [_track(demand=demand)],
        second_resources,
        timestamp=1.0,
        previous_plan=first,
    )
    refreshed = planner.plan(
        [_track(demand=demand)],
        second_resources,
        timestamp=2.0,
        previous_plan=changed,
    )

    assert changed.version == first.version + 1
    assert changed.plan_id != first.plan_id
    assert changed.coalitions[0].version == first.coalitions[0].version + 1
    assert changed.execution_signature() != first.execution_signature()
    assert refreshed.version == changed.version
    assert refreshed.plan_id == changed.plan_id
    assert refreshed.changed is False


def test_only_published_plan_advances_latest_for_stale_checks() -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan([_track()], resources, timestamp=0.0)
    candidate = planner.plan(
        [_track(preferred="R2")],
        resources,
        timestamp=1.0,
        previous_plan=first,
        publish=False,
    )

    still_current = planner.plan(
        [_track()],
        resources,
        timestamp=2.0,
        previous_plan=first,
    )
    assert still_current.plan_id == first.plan_id
    assert candidate.version == first.version + 1

    candidate = planner.publish_plan(candidate)
    assert candidate.metadata["plan_published"] is True
    with pytest.raises(StalePlanError, match="stale"):
        planner.plan(
            [_track()],
            resources,
            timestamp=3.0,
            previous_plan=first,
        )


def test_secondary_activation_and_coalition_role_change_advance_identity() -> None:
    planner = _planner()
    resources = [ResourceState(f"R{i}") for i in range(1, 4)]
    hybrid = TargetDemand(required_resource_count=3, coordination_mode="hybrid")
    center = planner.plan([_track(demand=hybrid)], resources, timestamp=0.0)
    takeover_candidate = planner.plan(
        [_track(demand=hybrid)],
        resources,
        timestamp=1.0,
        previous_plan=center,
        publish=False,
    )
    secondary = prepare_secondary_takeover_plan(
        takeover_candidate,
        supersedes_plan=center,
        secondary_node_id="secondary-node-2",
        readiness_class="takeover_ready",
        readiness_sustained=True,
        activated_at_s=1.1,
        lease_expires_at_s=5.0,
        leader_epoch=2,
    )

    assert takeover_candidate.plan_id == center.plan_id
    assert secondary.version == center.version + 1
    assert secondary.plan_id != center.plan_id
    assert secondary.metadata["active_plan_owner"] == "secondary"
    assert secondary.execution_signature() != center.execution_signature()

    secondary = planner.publish_plan(secondary)
    center_candidate = planner.plan(
        [
            _track(
                demand=replace(
                    hybrid,
                    coordination_mode="sequential",
                    primary_resource_count=1,
                )
            )
        ],
        resources,
        timestamp=2.0,
        previous_plan=secondary,
        publish=False,
    )
    assert center_candidate.version == secondary.version + 1
    assert center_candidate.coalitions[0].version == secondary.coalitions[0].version + 1
    assert center_candidate.execution_signature() != secondary.execution_signature()
