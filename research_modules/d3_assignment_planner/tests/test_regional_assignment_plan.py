from __future__ import annotations
from commitment_test_support import committed_target_track

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
    StalePlanError,
    TargetDemand,
    TargetTrack,
    validated_assignment_plan_payload_sha256,
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
    return committed_target_track(
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
    assert regional.metadata["regional_commit_modes"] == (
        "single_member_authority",
    )
    assert regional.metadata["regional_single_member_authority_count"] == 2
    assert regional.metadata["regional_atomic_coalition_commit_count"] == 0
    assert all(
        item.metadata["regional_commit_required"] is False
        and item.metadata["regional_commit_mode"] == "single_member_authority"
        and item.metadata["regional_commit_state"] == "single_member_authority"
        and item.metadata["regional_commit_evidence_present"] is False
        for item in regional.assignments
    )


def test_regional_authority_preserves_bindings_and_carries_explicit_pending_target() -> None:
    planner = _planner()
    tracks = tuple(
        _track(f"T-{index}", "A", 100.0 + index * 20.0)
        for index in range(5)
    )
    initial_resources = tuple(
        _resource(f"R-{index}", "A", index * 20.0) for index in range(4)
    )
    resources = (*initial_resources, _resource("R-4", "A", 80.0))
    previous = planner.plan(tracks, initial_resources, timestamp=0.0)
    assert previous.unassigned_target_ids == ("T-4",)
    assert previous.incomplete_target_ids == ("T-4",)
    previous_by_target = previous.assignments_by_target()
    assigned_by_target = {
        target_id: (items[0].resource_id,)
        for target_id, items in previous_by_target.items()
    }
    authority = RegionalAuthorityInput(
        adjudicated_at_s=1.0,
        grants=(
            RegionalAuthorityGrant(
                region_id="A",
                owner_layer="secondary",
                owner_node_id="RECON-A",
                owner_role="mobile_high_recon",
                epoch=previous.version + 1,
                source_plan_id=previous.plan_id,
                source_plan_version=previous.version,
                lease_expires_at_s=10.0,
                target_ids=tuple(assigned_by_target),
                assigned_resource_ids_by_target=assigned_by_target,
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
    assert {
        (item.target_id, item.resource_id) for item in regional.assignments
    } == {
        (item.target_id, item.resource_id) for item in previous.assignments
    }
    assert regional.target_count == 5
    assert regional.unassigned_target_ids == ("T-4",)
    assert regional.incomplete_target_ids == ("T-4",)
    assert len(regional.demand_summaries) == 5
    assert regional.metadata["regional_unassigned_target_ids"] == ("T-4",)
    assert regional.metadata[
        "regional_pending_without_authority_target_ids"
    ] == ("T-4",)
    assert regional.metadata["regional_authority_target_ids"] == (
        "T-0",
        "T-1",
        "T-2",
        "T-3",
    )
    contracts = {
        item["target_id"]: item
        for item in regional.metadata["regional_target_commit_contracts"]
    }
    assert contracts["T-4"]["authority_granted"] is False
    assert contracts["T-4"]["commit_mode"] == "unassigned_fail_closed"
    assert contracts["T-4"]["commit_evidence_present"] is False
    assert contracts["T-4"]["execution_authorized"] is False
    assert all(item.target_id != "T-4" for item in regional.coalitions)
    assert all(
        "T-4" not in record["target_ids"]
        for record in regional.metadata["regional_authorities"]
    )
    pending_summary = next(
        item for item in regional.demand_summaries if item.target_id == "T-4"
    )
    assert (
        pending_summary.demand_required,
        pending_summary.demand_assigned,
        pending_summary.demand_shortfall,
        pending_summary.coalition_complete,
    ) == (1, 0, 1, False)
    validated_assignment_plan_payload_sha256(regional)
    assert planner.latest_planning_evidence.available is True


def test_regional_authority_cannot_omit_a_previously_assigned_target() -> None:
    planner = _planner()
    tracks = tuple(
        _track(f"T-{index}", "A", 100.0 + index * 20.0)
        for index in range(5)
    )
    resources = tuple(
        _resource(f"R-{index}", "A", index * 20.0) for index in range(5)
    )
    previous = planner.plan(tracks, resources, timestamp=0.0)
    previous_by_target = previous.assignments_by_target()
    covered_target_ids = tuple(track.track_id for track in tracks[:-1])
    grant = RegionalAuthorityGrant(
        region_id="A",
        owner_layer="secondary",
        owner_node_id="RECON-A",
        owner_role="mobile_high_recon",
        epoch=previous.version + 1,
        source_plan_id=previous.plan_id,
        source_plan_version=previous.version,
        lease_expires_at_s=10.0,
        target_ids=covered_target_ids,
        assigned_resource_ids_by_target={
            target_id: (previous_by_target[target_id][0].resource_id,)
            for target_id in covered_target_ids
        },
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
    assert error.value.reason == "regional_authority_target_set_mismatch"


def test_regional_authority_rejects_previous_only_executable_binding() -> None:
    planner = _planner()
    previous_tracks = tuple(
        _track(f"T-{index}", "A", 100.0 + index * 20.0)
        for index in range(5)
    )
    resources = tuple(
        _resource(f"R-{index}", "A", index * 20.0) for index in range(5)
    )
    previous = planner.plan(previous_tracks, resources, timestamp=0.0)
    current_tracks = previous_tracks[:-1]
    previous_by_target = previous.assignments_by_target()
    current_target_ids = tuple(track.track_id for track in current_tracks)
    grant = RegionalAuthorityGrant(
        region_id="A",
        owner_layer="secondary",
        owner_node_id="RECON-A",
        owner_role="mobile_high_recon",
        epoch=previous.version + 1,
        source_plan_id=previous.plan_id,
        source_plan_version=previous.version,
        lease_expires_at_s=10.0,
        target_ids=current_target_ids,
        assigned_resource_ids_by_target={
            target_id: (previous_by_target[target_id][0].resource_id,)
            for target_id in current_target_ids
        },
    )

    with pytest.raises(RegionalPlanAuthorityError) as error:
        planner.plan_regional_authority(
            current_tracks,
            resources,
            timestamp=1.0,
            previous_plan=previous,
            authority=RegionalAuthorityInput(1.0, (grant,)),
            expected_previous_version=previous.version,
        )
    assert error.value.reason == (
        "regional_authority_previous_execution_target_missing"
    )


def test_regional_authority_cannot_omit_an_unproven_current_target() -> None:
    planner = _planner()
    previous_tracks = tuple(
        _track(f"T-{index}", "A", 100.0 + index * 20.0)
        for index in range(4)
    )
    resources = tuple(
        _resource(f"R-{index}", "A", index * 20.0) for index in range(5)
    )
    previous = planner.plan(previous_tracks, resources, timestamp=0.0)
    previous_by_target = previous.assignments_by_target()
    grant = RegionalAuthorityGrant(
        region_id="A",
        owner_layer="secondary",
        owner_node_id="RECON-A",
        owner_role="mobile_high_recon",
        epoch=previous.version + 1,
        source_plan_id=previous.plan_id,
        source_plan_version=previous.version,
        lease_expires_at_s=10.0,
        target_ids=tuple(previous_by_target),
        assigned_resource_ids_by_target={
            target_id: (items[0].resource_id,)
            for target_id, items in previous_by_target.items()
        },
    )
    current_tracks = (*previous_tracks, _track("T-4", "A", 180.0))

    with pytest.raises(RegionalPlanAuthorityError) as error:
        planner.plan_regional_authority(
            current_tracks,
            resources,
            timestamp=1.0,
            previous_plan=previous,
            authority=RegionalAuthorityInput(1.0, (grant,)),
            expected_previous_version=previous.version,
        )
    assert error.value.reason == "regional_authority_target_set_mismatch"


def test_regional_authority_rejects_tampered_pending_inventory_evidence() -> None:
    planner = _planner()
    tracks = tuple(
        _track(f"T-{index}", "A", 100.0 + index * 20.0)
        for index in range(5)
    )
    resources = tuple(
        _resource(f"R-{index}", "A", index * 20.0) for index in range(4)
    )
    previous = planner.plan(tracks, resources, timestamp=0.0)
    previous_by_target = previous.assignments_by_target()
    grant = RegionalAuthorityGrant(
        region_id="A",
        owner_layer="secondary",
        owner_node_id="RECON-A",
        owner_role="mobile_high_recon",
        epoch=previous.version + 1,
        source_plan_id=previous.plan_id,
        source_plan_version=previous.version,
        lease_expires_at_s=10.0,
        target_ids=tuple(previous_by_target),
        assigned_resource_ids_by_target={
            target_id: (items[0].resource_id,)
            for target_id, items in previous_by_target.items()
        },
    )
    tampered = replace(previous, incomplete_target_ids=())

    with pytest.raises(RegionalPlanAuthorityError) as error:
        planner.plan_regional_authority(
            tracks,
            resources,
            timestamp=1.0,
            previous_plan=tampered,
            authority=RegionalAuthorityInput(1.0, (grant,)),
            expected_previous_version=previous.version,
        )
    assert error.value.reason == "regional_authority_target_set_mismatch"


def test_regional_authority_still_rejects_other_execution_semantic_tamper() -> None:
    planner = _planner()
    tracks = (_track("T", "A", 100.0),)
    resources = (_resource("R", "A", 0.0),)
    previous = planner.plan(tracks, resources, timestamp=0.0)
    grant = _grant(
        previous,
        region_id="A",
        target_id="T",
        resource_ids=("R",),
        owner_layer="secondary",
        owner_node_id="RECON-A",
    )
    tampered = replace(previous, human_authorization_state="required")

    with pytest.raises(StalePlanError) as error:
        planner.plan_regional_authority(
            tracks,
            resources,
            timestamp=1.0,
            previous_plan=tampered,
            authority=RegionalAuthorityInput(1.0, (grant,)),
            expected_previous_version=previous.version,
        )
    assert error.value.reason == "stale_previous_plan_semantics"


@pytest.mark.parametrize(
    ("owner_layer", "owner_node_id"),
    (("secondary", "RECON-A"), ("distributed", "R")),
)
def test_single_member_region_authority_does_not_require_atomic_commit(
    owner_layer: str,
    owner_node_id: str,
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
        owner_layer=owner_layer,
        owner_node_id=owner_node_id,
    )

    plan = planner.plan_regional_authority(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        authority=RegionalAuthorityInput(1.0, (grant,)),
        expected_previous_version=previous.version,
    )

    assert plan.version == previous.version + 1
    assert plan.metadata["regional_commit_modes"] == (
        "single_member_authority",
    )
    assignment = plan.assignments[0]
    assert assignment.metadata["regional_commit_required"] is False
    assert assignment.metadata["regional_commit_state"] == "single_member_authority"
    assert assignment.metadata["regional_commit_evidence_present"] is False


def test_d4_single_member_authorized_summary_is_accepted_without_atomic_commit() -> None:
    planner = _planner()
    tracks = (_track("T", "A", 100.0),)
    resources = (_resource("R", "A", 0.0),)
    previous = planner.plan(tracks, resources, timestamp=0.0)
    commit = RegionalCoalitionCommitEvidence(
        target_id="T",
        coordinator_id="R",
        epoch=previous.version,
        lease_expires_at_s=8.0,
        required_member_ids=("R",),
        acked_member_ids=("R",),
        commit_required=False,
        state="single_member_authorized",
        atomic_committed=False,
        execution_authorized=True,
    )
    grant = _grant(
        previous,
        region_id="A",
        target_id="T",
        resource_ids=("R",),
        owner_layer="distributed",
        owner_node_id="R",
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

    assignment = plan.assignments[0]
    assert assignment.metadata["regional_commit_mode"] == "single_member_authority"
    assert assignment.metadata["regional_commit_state"] == "single_member_authorized"
    assert assignment.metadata["regional_commit_evidence_present"] is True


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("not_authorized", "regional_single_member_not_authorized"),
        ("expired_lease", "regional_single_member_lease_expired"),
        ("owner_mismatch", "regional_coalition_coordinator_mismatch"),
        ("epoch_mismatch", "regional_coalition_epoch_mismatch"),
        ("member_mismatch", "regional_coalition_membership_mismatch"),
        ("atomic_masquerade", "regional_single_member_atomic_commit_invalid"),
        ("commit_required_mismatch", "regional_commit_requirement_mismatch"),
    ),
)
def test_single_member_invalid_authorization_is_fail_closed(
    mutation: str,
    expected_reason: str,
) -> None:
    planner = _planner()
    tracks = (_track("T", "A", 100.0),)
    resources = (_resource("R", "A", 0.0),)
    previous = planner.plan(tracks, resources, timestamp=0.0)
    evidence_member_ids = (
        ("R-OTHER",) if mutation == "member_mismatch" else ("R",)
    )
    commit = RegionalCoalitionCommitEvidence(
        target_id="T",
        coordinator_id="OTHER" if mutation == "owner_mismatch" else "R",
        epoch=(
            previous.version + 1
            if mutation == "epoch_mismatch"
            else previous.version
        ),
        lease_expires_at_s=1.0 if mutation == "expired_lease" else 8.0,
        required_member_ids=evidence_member_ids,
        acked_member_ids=(
            () if mutation == "not_authorized" else evidence_member_ids
        ),
        commit_required=mutation == "commit_required_mismatch",
        state=(
            "committed"
            if mutation == "commit_required_mismatch"
            else (
                "aborted"
                if mutation == "not_authorized"
                else "single_member_authorized"
            )
        ),
        atomic_committed=mutation in {
            "atomic_masquerade",
            "commit_required_mismatch",
        },
        execution_authorized=mutation != "not_authorized",
    )
    grant = _grant(
        previous,
        region_id="A",
        target_id="T",
        resource_ids=("R",),
        owner_layer="distributed",
        owner_node_id="R",
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
    assert error.value.reason == expected_reason


def test_single_member_grant_without_execution_permission_is_fail_closed() -> None:
    planner = _planner()
    tracks = (_track("T", "A", 100.0),)
    resources = (_resource("R", "A", 0.0),)
    previous = planner.plan(tracks, resources, timestamp=0.0)
    grant = replace(
        _grant(
            previous,
            region_id="A",
            target_id="T",
            resource_ids=("R",),
            owner_layer="distributed",
            owner_node_id="R",
        ),
        execution_allowed=False,
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
    assert error.value.reason == "regional_authority_execution_not_allowed"


def test_single_resource_cannot_be_authorized_for_two_regional_targets() -> None:
    planner = _planner()
    tracks = (_track("T-1", "A", 100.0), _track("T-2", "A", 120.0))
    resources = (_resource("R", "A", 0.0),)
    previous = planner.plan(tracks, resources, timestamp=0.0)
    grant = RegionalAuthorityGrant(
        region_id="A",
        owner_layer="distributed",
        owner_node_id="R",
        owner_role="cluster_representative",
        epoch=previous.version,
        source_plan_id=previous.plan_id,
        source_plan_version=previous.version,
        lease_expires_at_s=8.0,
        target_ids=("T-1", "T-2"),
        assigned_resource_ids_by_target={"T-1": ("R",), "T-2": ("R",)},
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
    assert error.value.reason == "regional_authority_duplicate_resource_assignment"


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
    assert plan.metadata["regional_commit_modes"] == (
        "atomic_coalition_commit",
    )
    assert plan.metadata["regional_single_member_authority_count"] == 0
    assert plan.metadata["regional_atomic_coalition_commit_count"] == 1
    assert all(
        item.metadata["regional_commit_state"] == "committed"
        for item in plan.assignments
    )
    assert all(
        item.metadata["regional_commit_required"] is True
        for item in plan.assignments
    )


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
