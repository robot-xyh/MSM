from __future__ import annotations

from dataclasses import replace

import pytest

from d3_assignment_planner import (
    FAULT_AUTHORITY_GENERATION_FENCE_SCHEMA_V1,
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    StalePlanError,
    TargetDemand,
    TargetTrack,
    prepare_secondary_takeover_plan,
    validated_assignment_plan_payload_sha256,
)


def _fixture():
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=True,
            min_dwell=30.0,
            human_authorization_state="approved",
        )
    )
    demand = TargetDemand(
        required_resource_count=3,
        primary_resource_count=2,
        coordination_mode="hybrid",
    )
    tracks = (
        TargetTrack(
            "T-HIGH",
            threat_score=0.95,
            covariance=0.1,
            window_cost=0.0,
            demand=demand,
        ),
    )
    resources = tuple(ResourceState(f"R-{index}") for index in range(3))
    current = planner.plan(tracks, resources, timestamp=0.0)
    return planner, current


def test_authority_generation_fence_publishes_new_identity_without_reassignment() -> None:
    planner, current = _fixture()

    fenced = planner.advance_authority_generation(
        current,
        timestamp=1.0,
        expected_previous_version=current.version,
        fence_reason="center_failure_before_regional_adjudication",
    )

    assert fenced.version == current.version + 1
    assert fenced.plan_id != current.plan_id
    assert fenced.previous_plan_id == current.plan_id
    assert fenced.assignment_signature() == current.assignment_signature()
    assert fenced.execution_signature() == current.execution_signature()
    assert fenced.coalitions == current.coalitions
    assert fenced.unassigned_target_ids == current.unassigned_target_ids
    assert fenced.incomplete_target_ids == current.incomplete_target_ids
    assert {item.target_id for item in fenced.assignments} == {"T-HIGH"}
    assert {item.resource_id for item in fenced.assignments} == {
        item.resource_id for item in current.assignments
    }
    assert {item.plan_version for item in fenced.assignments} == {fenced.version}
    assert fenced.human_authorization_state == current.human_authorization_state
    assert fenced.metadata["fault_authority_fence_schema"] == (
        FAULT_AUTHORITY_GENERATION_FENCE_SCHEMA_V1
    )
    assert fenced.metadata["fault_authority_fence_non_reassignment"] is True
    assert fenced.metadata["fault_authority_fence_execution_authorization"] is False
    assert fenced.metadata["fault_authority_fence_requires_d4_gate"] is True
    assert fenced.metadata["reassignment_applied"] is False
    assert fenced.metadata["execution_authorization_changed"] is False
    assert fenced.metadata["plan_published"] is True

    with pytest.raises(StalePlanError) as error:
        planner.plan([], [], timestamp=2.0, previous_plan=current)
    assert error.value.reason == "stale_previous_version"


def test_authority_generation_fence_normalizes_four_to_five_target_roster() -> None:
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=True,
            delta=0.2,
            min_dwell=30.0,
            human_authorization_state="approved",
        )
    )
    resources = tuple(ResourceState(f"R-{index}") for index in range(5))
    initial_tracks = tuple(
        TargetTrack(
            f"T-{index}",
            threat_score=0.2,
            covariance=0.1,
            window_cost=0.0,
            fov_difficulty_by_resource={
                resource.resource_id: (
                    0.0 if resource.resource_id == f"R-{index}" else 1.0
                )
                for resource in resources
            },
        )
        for index in range(4)
    )
    current = planner.plan(initial_tracks, resources, timestamp=0.0)
    held = planner.plan(
        (
            *initial_tracks,
            TargetTrack(
                "T-4",
                threat_score=0.2,
                covariance=0.1,
                window_cost=0.0,
                fov_difficulty_by_resource={
                    resource.resource_id: (
                        0.0 if resource.resource_id == "R-4" else 1.0
                    )
                    for resource in resources
                },
            ),
        ),
        resources,
        timestamp=1.0,
        previous_plan=current,
        expected_previous_version=current.version,
        forced_replan=True,
    )
    fenced = planner.advance_authority_generation(
        held,
        timestamp=2.0,
        expected_previous_version=held.version,
        fence_reason="center_failure_before_regional_adjudication",
    )

    assert fenced.version == held.version + 1
    assert fenced.assignment_signature() == held.assignment_signature()
    assert fenced.target_count == 5
    assert fenced.unassigned_target_ids == ("T-4",)
    assert fenced.incomplete_target_ids == ("T-4",)
    assert {item.target_id for item in fenced.demand_summaries} == {
        f"T-{index}" for index in range(5)
    }
    assert fenced.metadata["target_count"] == 5
    assert fenced.metadata["current_plan_version"] == fenced.version
    assert fenced.metadata["fault_authority_fence_generation"] == 1
    validated_assignment_plan_payload_sha256(fenced)
    evidence = planner.latest_planning_evidence
    assert evidence.available is True
    assert evidence.plan_id == fenced.plan_id
    assert evidence.plan_version == fenced.version


def test_secondary_owner_publish_rebases_matching_planning_evidence() -> None:
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=True,
            min_dwell=30.0,
            human_authorization_state="approved",
        )
    )
    tracks = (TargetTrack("T", 0.5, 0.1, 0.0),)
    resources = (ResourceState("R"),)
    previous = planner.plan(tracks, resources, timestamp=0.0)
    candidate = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        expected_previous_version=previous.version,
        publish=False,
    )
    takeover = prepare_secondary_takeover_plan(
        candidate,
        supersedes_plan=previous,
        secondary_node_id="RECON-A",
        readiness_class="takeover_ready",
        readiness_sustained=True,
        activated_at_s=1.0,
        lease_expires_at_s=5.0,
        leader_epoch=previous.version + 1,
    )

    published = planner.publish_plan(takeover)

    validated_assignment_plan_payload_sha256(published)
    evidence = planner.latest_planning_evidence
    assert evidence.available is True
    assert evidence.planning_path == "authority_identity_publish"
    assert evidence.plan_id == published.plan_id
    assert evidence.plan_version == published.version


def test_authority_generation_fence_rejects_expected_version_mismatch() -> None:
    planner, current = _fixture()

    with pytest.raises(StalePlanError) as error:
        planner.advance_authority_generation(
            current,
            timestamp=1.0,
            expected_previous_version=current.version + 1,
            fence_reason="center_failure",
        )

    assert error.value.reason == "expected_previous_version_mismatch"


def test_consecutive_authority_generation_fences_are_monotonic() -> None:
    planner, current = _fixture()
    first = planner.advance_authority_generation(
        current,
        timestamp=1.0,
        expected_previous_version=current.version,
        fence_reason="center_failure",
    )
    second = planner.advance_authority_generation(
        first,
        timestamp=2.0,
        expected_previous_version=first.version,
        fence_reason="secondary_failure",
    )

    assert (current.version, first.version, second.version) == (1, 2, 3)
    assert len({current.plan_id, first.plan_id, second.plan_id}) == 3
    assert first.metadata["fault_authority_fence_generation"] == 1
    assert second.metadata["fault_authority_fence_generation"] == 2
    assert second.metadata["fault_authority_fence_source_plan_id"] == first.plan_id
    assert second.metadata["fault_authority_fence_source_plan_version"] == first.version
    assert second.assignment_signature() == current.assignment_signature()
    assert second.execution_signature() == current.execution_signature()
    assert second.coalitions == current.coalitions


def test_authority_generation_fence_rejects_duplicate_publish() -> None:
    planner, current = _fixture()
    fenced = planner.advance_authority_generation(
        current,
        timestamp=1.0,
        expected_previous_version=current.version,
        fence_reason="center_failure",
    )

    with pytest.raises(StalePlanError) as error:
        planner.publish_plan(fenced)

    assert error.value.reason == "authority_fence_duplicate_version"


def test_publish_rejects_fence_that_changes_coalition_identity() -> None:
    planner, current = _fixture()
    fenced = planner.advance_authority_generation(
        current,
        timestamp=1.0,
        expected_previous_version=current.version,
        fence_reason="center_failure",
    )
    changed_coalition = replace(
        fenced.coalitions[0],
        version=fenced.coalitions[0].version + 1,
    )
    forged = replace(
        fenced,
        plan_id="d3-plan-forged-fence",
        version=fenced.version + 1,
        previous_plan_id=fenced.plan_id,
        coalitions=(changed_coalition,),
        metadata={
            **dict(fenced.metadata),
            "fault_authority_fence_source_plan_id": fenced.plan_id,
            "fault_authority_fence_source_plan_version": fenced.version,
        },
    )

    with pytest.raises(ValueError, match="cannot change coalitions"):
        planner.publish_plan(forged)
