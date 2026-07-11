from dataclasses import replace

import pytest

from d3_assignment_planner import (
    AssignmentPlan,
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    TargetTrack,
    assignment_records_from_plan,
    continue_active_secondary_plan,
    guidance_bindings_from_assignment_plan,
    prepare_secondary_takeover_plan,
)


def _active_secondary_and_next_candidate(
    *,
    previous_lease_expires_at_s: float = 5.0,
) -> tuple[AssignmentPlan, AssignmentPlan]:
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=False,
            human_authorization_state="approved",
        )
    )
    tracks = (TargetTrack("T01", 0.9, 0.1, 0.1),)
    resources = (ResourceState("R01"),)
    center = planner.plan(tracks, resources, timestamp=0.0)
    takeover_candidate = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=center,
    )
    active_secondary = prepare_secondary_takeover_plan(
        takeover_candidate,
        supersedes_plan=center,
        secondary_node_id="high-recon-2",
        readiness_class="takeover_ready",
        readiness_sustained=True,
        activated_at_s=1.1,
        lease_expires_at_s=previous_lease_expires_at_s,
        leader_epoch=3,
    )
    next_candidate = planner.plan(
        tracks,
        resources,
        timestamp=2.0,
        previous_plan=active_secondary,
    )
    return active_secondary, next_candidate


def test_active_secondary_owner_continues_across_rolling_plan_version() -> None:
    active_secondary, next_candidate = _active_secondary_and_next_candidate()

    assert next_candidate.metadata["active_plan_owner"] == "center"
    continued = continue_active_secondary_plan(
        next_candidate,
        previous_plan=active_secondary,
        readiness_class="takeover_ready",
        readiness_sustained=True,
        published_at_s=2.1,
        lease_expires_at_s=7.0,
        leader_epoch=3,
    )
    (old_binding,) = guidance_bindings_from_assignment_plan(
        active_secondary,
        now_s=2.1,
        current_plan_id=continued.plan_id,
        current_plan_version=continued.version,
    )
    (current_binding,) = guidance_bindings_from_assignment_plan(
        continued,
        now_s=2.1,
        current_plan_id=continued.plan_id,
        current_plan_version=continued.version,
    )
    (record,) = assignment_records_from_plan(continued)

    assert continued.version > active_secondary.version
    assert continued.previous_plan_id == active_secondary.plan_id
    assert continued.metadata["supersedes_plan_id"] == active_secondary.plan_id
    assert continued.metadata["supersedes_plan_version"] == active_secondary.version
    assert continued.metadata["active_plan_owner"] == "secondary"
    assert continued.metadata["owner_node_id"] == "high-recon-2"
    assert continued.source_node_id == "high-recon-2"
    assert continued.metadata["secondary_leader_epoch"] == 3
    assert continued.metadata["secondary_lease_expires_at_s"] == 7.0
    assert continued.metadata["secondary_readiness_sustained"] is True
    assert continued.metadata["continuation_reason"] == "secondary_rolling_update"
    assert continued.assignments[0].metadata["owner_node_id"] == "high-recon-2"
    assert continued.assignments[0].metadata["previous_plan_id"] == (
        active_secondary.plan_id
    )
    assert continued.assignments[0].metadata["supersedes_plan_id"] == (
        active_secondary.plan_id
    )
    assert continued.assignments[0].metadata["secondary_activated_at_s"] == 1.1
    assert continued.assignments[0].metadata["secondary_leader_epoch"] == 3
    assert continued.assignments[0].metadata["secondary_lease_expires_at_s"] == 7.0
    assert continued.assignments[0].metadata["secondary_readiness_sustained"] is True
    assert old_binding.binding_state == "stale"
    assert old_binding.revoke_reason == "not_current_assignment_plan"
    assert current_binding.binding_state == "active"
    assert current_binding.assignment_validity_state == "current"
    assert record.active_plan_owner == "secondary"
    assert record.owner_node_id == "high-recon-2"


def test_secondary_continuation_rejects_expired_previous_lease() -> None:
    active_secondary, next_candidate = _active_secondary_and_next_candidate(
        previous_lease_expires_at_s=2.0,
    )

    with pytest.raises(ValueError, match="previous secondary lease is expired"):
        continue_active_secondary_plan(
            next_candidate,
            previous_plan=active_secondary,
            readiness_class="takeover_ready",
            readiness_sustained=True,
            published_at_s=2.1,
            lease_expires_at_s=4.0,
            leader_epoch=3,
        )


def test_secondary_continuation_rejects_missing_owner() -> None:
    active_secondary, next_candidate = _active_secondary_and_next_candidate()
    metadata = {
        key: value
        for key, value in active_secondary.metadata.items()
        if key
        not in {
            "owner_node_id",
            "current_plan_owner_node_id",
            "source_node_id",
            "selected_secondary_node_id",
        }
    }
    ownerless = replace(active_secondary, source_node_id=None, metadata=metadata)

    with pytest.raises(ValueError, match="owner is missing"):
        continue_active_secondary_plan(
            next_candidate,
            previous_plan=ownerless,
            readiness_class="takeover_ready",
            readiness_sustained=True,
            published_at_s=2.1,
            lease_expires_at_s=7.0,
            leader_epoch=3,
        )


def test_secondary_continuation_rejects_readiness_loss() -> None:
    active_secondary, next_candidate = _active_secondary_and_next_candidate()

    with pytest.raises(ValueError, match="readiness must be sustained"):
        continue_active_secondary_plan(
            next_candidate,
            previous_plan=active_secondary,
            readiness_class="takeover_ready",
            readiness_sustained=False,
            published_at_s=2.1,
            lease_expires_at_s=7.0,
            leader_epoch=3,
        )


def test_secondary_continuation_rejects_epoch_or_lease_regression() -> None:
    active_secondary, next_candidate = _active_secondary_and_next_candidate()

    with pytest.raises(ValueError, match="epoch must not regress"):
        continue_active_secondary_plan(
            next_candidate,
            previous_plan=active_secondary,
            readiness_class="takeover_ready",
            readiness_sustained=True,
            published_at_s=2.1,
            lease_expires_at_s=7.0,
            leader_epoch=2,
        )
    with pytest.raises(ValueError, match="lease must not regress"):
        continue_active_secondary_plan(
            next_candidate,
            previous_plan=active_secondary,
            readiness_class="takeover_ready",
            readiness_sustained=True,
            published_at_s=2.1,
            lease_expires_at_s=4.0,
            leader_epoch=3,
        )
