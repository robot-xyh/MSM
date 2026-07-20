from __future__ import annotations

from dataclasses import replace

import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    PlannerConfig,
    RegionalAuthorityGrant,
    RegionalAuthorityInput,
    RegionalCoalitionCommitEvidence,
    RegionalPlanAuthorityError,
    ResourceState,
    TargetDemand,
    TargetTrack,
)


def _planner() -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig.scalable_3d(
            enable_hysteresis=False,
            max_candidate_edges_per_target=8,
            human_authorization_state="approved",
        )
    )


def _track(target_id: str, region_id: str, x: float, demand: TargetDemand | None = None) -> TargetTrack:
    return TargetTrack(
        target_id,
        threat_score=0.95 if demand is not None else 0.7,
        covariance=0.1,
        window_cost=0.0,
        position_ned=(x, 0.0, -100.0),
        velocity_ned=(-1.0, 0.0, 0.0),
        region_id=region_id,
        candidate_resource_region_ids=("A", "B"),
        demand=demand,
    )


def _resource(resource_id: str, region_id: str, x: float) -> ResourceState:
    return ResourceState(
        resource_id,
        position_ned=(x, 0.0, -100.0),
        velocity_ned=(0.0, 0.0, 0.0),
        max_speed_mps=14.0,
        max_intercept_range_m=5_000.0,
        region_id=region_id,
        reachable_target_region_ids=("A", "B"),
    )


def _grant(
    previous,
    *,
    region_id: str,
    target_id: str,
    resource_ids: tuple[str, ...],
    owner_layer: str = "secondary",
    owner_node_id: str = "RECON-A",
    epoch: int | None = None,
    lease: float = 10.0,
    commit: RegionalCoalitionCommitEvidence | None = None,
) -> RegionalAuthorityGrant:
    return RegionalAuthorityGrant(
        region_id=region_id,
        owner_layer=owner_layer,
        owner_node_id=owner_node_id,
        owner_role=(
            "mobile_high_recon"
            if owner_layer == "secondary"
            else "cluster_representative"
        ),
        epoch=previous.version if epoch is None else epoch,
        source_plan_id=previous.plan_id,
        source_plan_version=previous.version,
        lease_expires_at_s=lease,
        target_ids=(target_id,),
        assigned_resource_ids_by_target={target_id: resource_ids},
        coalition_commits=() if commit is None else (commit,),
    )


def test_multiple_secondary_owners_publish_one_monotonic_regional_plan() -> None:
    planner = _planner()
    tracks = (_track("T-A", "A", 100.0), _track("T-B", "B", 300.0))
    resources = (_resource("R-A", "A", 0.0), _resource("R-B", "B", 250.0))
    previous = planner.plan(tracks, resources, timestamp=0.0)
    by_target = previous.assignments_by_target()
    authority = RegionalAuthorityInput(
        adjudicated_at_s=1.0,
        grants=(
            _grant(
                previous,
                region_id="A",
                target_id="T-A",
                resource_ids=(by_target["T-A"][0].resource_id,),
                owner_node_id="RECON-A",
            ),
            _grant(
                previous,
                region_id="B",
                target_id="T-B",
                resource_ids=(by_target["T-B"][0].resource_id,),
                owner_node_id="RECON-B",
            ),
        ),
    )

    regional = planner.plan_regional_authority(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        authority=authority,
        expected_previous_version=previous.version,
    )

    assert regional.version == previous.version + 1
    assert regional.previous_plan_id == previous.plan_id
    assert regional.metadata["plan_owner"] == "regional"
    assert regional.metadata["owner_node_id"] == "regional_multi_owner"
    assert regional.metadata["regional_owner_node_ids"] == ("RECON-A", "RECON-B")
    assignment_owners = {
        item.target_id: item.metadata["owner_node_id"] for item in regional.assignments
    }
    assert assignment_owners == {"T-A": "RECON-A", "T-B": "RECON-B"}


def _distributed_fixture():
    planner = _planner()
    demand = TargetDemand(
        required_resource_count=3,
        primary_resource_count=2,
        coordination_mode="hybrid",
    )
    tracks = (_track("T-HIGH", "A", 200.0, demand),)
    resources = tuple(_resource(f"R-{index}", "A", index * 20.0) for index in range(3))
    previous = planner.plan(tracks, resources, timestamp=0.0)
    member_ids = tuple(
        item.resource_id for item in previous.assignments_by_target()["T-HIGH"]
    )
    return planner, tracks, resources, previous, member_ids


def test_fully_distributed_committed_coalition_is_published() -> None:
    planner, tracks, resources, previous, member_ids = _distributed_fixture()
    commit = RegionalCoalitionCommitEvidence(
        target_id="T-HIGH",
        coordinator_id="R-0",
        epoch=previous.version,
        lease_expires_at_s=8.0,
        required_member_ids=member_ids,
        acked_member_ids=member_ids,
    )
    grant = _grant(
        previous,
        region_id="A",
        target_id="T-HIGH",
        resource_ids=member_ids,
        owner_layer="distributed",
        owner_node_id="R-0",
        lease=8.0,
        commit=commit,
    )

    plan = planner.plan_regional_authority(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        authority=RegionalAuthorityInput(1.0, (grant,)),
        expected_previous_version=previous.version,
    )

    assert plan.version == 2
    assert len(plan.assignments) == 3
    assert plan.coalitions[0].complete is True
    assert plan.metadata["regional_owner_layers"] == ("distributed",)
    assert all(item.metadata["regional_commit_state"] == "committed" for item in plan.assignments)


def test_distributed_missing_ack_is_fail_closed() -> None:
    planner, tracks, resources, previous, member_ids = _distributed_fixture()
    commit = RegionalCoalitionCommitEvidence(
        target_id="T-HIGH",
        coordinator_id="R-0",
        epoch=previous.version,
        lease_expires_at_s=8.0,
        required_member_ids=member_ids,
        acked_member_ids=member_ids[:-1],
    )
    grant = _grant(
        previous,
        region_id="A",
        target_id="T-HIGH",
        resource_ids=member_ids,
        owner_layer="distributed",
        owner_node_id="R-0",
        lease=8.0,
        commit=commit,
    )

    with pytest.raises(RegionalPlanAuthorityError) as error:
        planner.plan_regional_authority(
            tracks,
            resources,
            timestamp=1.0,
            previous_plan=previous,
            authority=RegionalAuthorityInput(1.0, (grant,)),
            expected_previous_version=previous.version,
        )
    assert error.value.reason == "regional_coalition_missing_ack"


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("old_epoch", "regional_authority_old_epoch"),
        ("expired_lease", "regional_authority_lease_expired"),
        ("stale_source", "regional_authority_stale_source_plan"),
    ),
)
def test_old_epoch_expired_lease_and_stale_source_are_rejected(
    mutation: str,
    expected_reason: str,
) -> None:
    planner = _planner()
    tracks = (_track("T", "A", 100.0),)
    resources = (_resource("R", "A", 0.0),)
    previous = planner.plan(tracks, resources, timestamp=0.0)
    grant = _grant(
        previous,
        region_id="A",
        target_id="T",
        resource_ids=("R",),
        epoch=0 if mutation == "old_epoch" else previous.version,
        lease=1.0 if mutation == "expired_lease" else 10.0,
    )
    if mutation == "stale_source":
        grant = replace(grant, source_plan_version=previous.version - 1)

    with pytest.raises(RegionalPlanAuthorityError) as error:
        planner.plan_regional_authority(
            tracks,
            resources,
            timestamp=1.0,
            previous_plan=previous,
            authority=RegionalAuthorityInput(1.0, (grant,)),
            expected_previous_version=previous.version,
        )
    assert error.value.reason == expected_reason
