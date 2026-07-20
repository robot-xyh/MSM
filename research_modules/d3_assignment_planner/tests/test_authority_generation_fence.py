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
