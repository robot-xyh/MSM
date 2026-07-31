from commitment_test_support import committed_target_track

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
    continue_active_secondary_plan,
    guidance_bindings_from_assignment_plan,
    prepare_secondary_takeover_plan,
    validated_assignment_plan_payload_sha256,
)


_AUTHORITY_BINDING_KEYS = {
    "authority_epoch",
    "lease_expires_at_s",
    "regional_max_epoch",
    "regional_min_lease_expires_at_s",
}


def _planner() -> AssignmentPlanner:
    return AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))


def _track(
    target_id: str = "T1",
    *,
    demand: TargetDemand | None = None,
    preferred: str = "R1",
) -> TargetTrack:
    return committed_target_track(
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
    assert refreshed.coalitions[0].version == changed.coalitions[0].version
    assert refreshed.metadata["plan_refresh_only"] is False
    assert refreshed.metadata["evaluation_refresh_only"] is True
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
    assert takeover_candidate.version == center.version
    assert takeover_candidate.metadata["evaluation_refresh_only"] is True
    assert secondary.version == center.version + 1
    assert secondary.plan_id != center.plan_id
    assert secondary.metadata["active_plan_owner"] == "secondary"
    assert secondary.metadata["new_plan_lineage_reason"] == (
        "secondary_takeover_owner_change"
    )
    assert secondary.metadata["identity_created_at_s"] == 1.1
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


def test_cooperative_cost_refresh_keeps_lineage_across_three_ticks() -> None:
    planner = AssignmentPlanner(
        config=PlannerConfig(
            enable_hysteresis=False,
            human_authorization_state="approved",
        )
    )
    demand = TargetDemand(
        required_resource_count=3,
        primary_resource_count=2,
        coordination_mode="hybrid",
    )
    resources = [ResourceState(f"R{i}") for i in range(1, 6)]
    tracks = [
        _track("T-HIGH", demand=demand),
        _track("T-LOW", demand=TargetDemand.independent(), preferred="R4"),
    ]
    first = planner.plan(
        tracks,
        resources,
        timestamp=0.0,
    )
    second = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=first,
        expected_previous_version=first.version,
    )
    third = planner.plan(
        tracks,
        resources,
        timestamp=2.0,
        previous_plan=second,
        expected_previous_version=second.version,
    )

    assert (first.version, second.version, third.version) == (1, 1, 1)
    assert first.plan_id == second.plan_id == third.plan_id
    assert first.created_at == second.created_at == third.created_at == 0.0
    assert second.previous_plan_id == third.previous_plan_id == first.previous_plan_id
    assert second.metadata["plan_refresh_only"] is False
    assert third.metadata["plan_refresh_only"] is False
    assert second.metadata["evaluation_refresh_only"] is True
    assert third.metadata["evaluation_refresh_only"] is True
    assert second.changed is third.changed is False
    assert {
        coalition.version
        for plan in (first, second, third)
        for coalition in plan.coalitions
    } == {1}
    assert {
        tuple(
            (coalition.target_id, member.resource_id, member.member_role)
            for coalition in plan.coalitions
            for member in coalition.members
        )
        for plan in (first, second, third)
    } == {
        tuple(
            (coalition.target_id, member.resource_id, member.member_role)
            for coalition in first.coalitions
            for member in coalition.members
        )
    }
    assert {assignment.plan_version for assignment in third.assignments} == {1}
    assert all(
        assignment.metadata["evaluation_refresh_only"] is True
        for assignment in third.assignments
    )
    assert {
        assignment.metadata["current_plan_id"] for assignment in third.assignments
    } == {first.plan_id}

    current = guidance_bindings_from_assignment_plan(
        first,
        current_plan_id=third.plan_id,
        current_plan_version=third.version,
    )
    assert all(binding.binding_state != "stale" for binding in current)
    assert all(
        binding.binding_state == "active"
        for binding in current
        if binding.member_role == "primary"
    )


def test_publish_rejects_compatible_refresh_with_changed_lineage_id() -> None:
    planner = _planner()
    demand = TargetDemand()
    resources = [ResourceState(f"R{i}") for i in range(1, 4)]
    first = planner.plan([_track(demand=demand)], resources, timestamp=0.0)
    refresh = planner.plan(
        [_track(demand=demand)],
        resources,
        timestamp=1.0,
        previous_plan=first,
        publish=False,
    )

    assert refresh.plan_id == first.plan_id
    with pytest.raises(
        ValueError,
        match="evaluation-only refresh cannot advance executable plan identity",
    ):
        planner.publish_plan(replace(refresh, plan_id="d3-plan-invalid-lineage"))


def test_planner_rejects_same_identity_previous_plan_with_tampered_execution() -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan([_track()], resources, timestamp=0.0)
    tampered = replace(
        first,
        assignments=(replace(first.assignments[0], resource_id="R2"),),
    )

    with pytest.raises(StalePlanError) as error:
        planner.plan(
            [_track()],
            resources,
            timestamp=1.0,
            previous_plan=tampered,
            expected_previous_version=first.version,
        )

    assert error.value.reason == "stale_previous_plan_semantics"


def test_direct_publish_uses_trusted_latest_signature_for_same_identity() -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan([_track()], resources, timestamp=0.0)
    refresh = planner.plan(
        [_track()],
        resources,
        timestamp=1.0,
        previous_plan=first,
        publish=False,
    )

    published = planner.publish_plan(refresh)
    assert published.plan_id == first.plan_id
    assert published.version == first.version

    tampered = replace(
        published,
        assignments=(replace(published.assignments[0], resource_id="R2"),),
    )
    with pytest.raises(
        ValueError,
        match="cannot change execution semantics without a new identity",
    ):
        planner.publish_plan(tampered)


def test_authority_publication_contract_separates_evaluation_diagnostics() -> None:
    planner = _planner()
    demand = TargetDemand(
        required_resource_count=3,
        primary_resource_count=2,
        coordination_mode="hybrid",
    )
    resources = [ResourceState(f"R{i}") for i in range(1, 4)]
    first = planner.plan([_track(demand=demand)], resources, timestamp=0.0)
    refreshed = planner.plan(
        [_track(demand=demand)],
        resources,
        timestamp=1.0,
        previous_plan=first,
    )

    assert refreshed.plan_id == first.plan_id
    assert refreshed.version == first.version
    assert refreshed.execution_signature() == first.execution_signature()
    assert refreshed.requires_authoritative_publication(first) is False
    assert validated_assignment_plan_payload_sha256(refreshed) != (
        validated_assignment_plan_payload_sha256(first)
    )

    reordered = replace(
        refreshed,
        assignments=tuple(reversed(refreshed.assignments)),
    )
    assert reordered.requires_authoritative_publication(first) is False

    changed = planner.plan(
        [_track(demand=demand, preferred="R2")],
        [
            ResourceState("R2"),
            ResourceState("R3"),
            ResourceState("R4"),
        ],
        timestamp=2.0,
        previous_plan=refreshed,
    )
    assert changed.requires_authoritative_publication(refreshed) is True


@pytest.mark.parametrize("tamper_kind", ("role", "owner", "lease", "count"))
def test_same_identity_authority_mutation_fails_closed(tamper_kind: str) -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan([_track()], resources, timestamp=0.0)
    if tamper_kind == "role":
        tampered = replace(
            first,
            assignments=(
                replace(first.assignments[0], member_role="reserve"),
            ),
        )
    elif tamper_kind == "owner":
        tampered = replace(
            first,
            metadata={**dict(first.metadata), "active_plan_owner": "secondary"},
        )
    elif tamper_kind == "lease":
        tampered = replace(
            first,
            metadata={**dict(first.metadata), "lease_expires_at_s": 10.0},
        )
    else:
        tampered = replace(first, resource_count=first.resource_count + 1)

    with pytest.raises(
        ValueError,
        match="same plan identity cannot change authoritative execution payload",
    ):
        tampered.requires_authoritative_publication(first)


def test_authority_generation_binding_is_opt_in_immutable_and_idempotent() -> None:
    first = _planner().plan(
        [_track()],
        [ResourceState("R1"), ResourceState("R2")],
        timestamp=2.0,
    )
    assert _AUTHORITY_BINDING_KEYS.isdisjoint(first.metadata)
    bound = first.bind_authority_generation(
        authority_epoch=0,
        lease_expires_at_s=7.5,
    )

    assert bound is not first
    assert (bound.plan_id, bound.version) == (first.plan_id, first.version)
    assert _AUTHORITY_BINDING_KEYS.isdisjoint(first.metadata)
    assert bound.metadata["authority_epoch"] == 0
    assert bound.metadata["lease_expires_at_s"] == 7.5
    assert bound.metadata["regional_max_epoch"] == 0
    assert bound.metadata["regional_min_lease_expires_at_s"] == 7.5
    assert bound.authority_signature() != first.authority_signature()
    assert bound.bind_authority_generation(0, 7.5) is bound


@pytest.mark.parametrize(
    ("authority_epoch", "lease_expires_at_s", "message"),
    (
        (-1, 7.5, "authority_epoch"),
        (1.0, 7.5, "authority_epoch"),
        (True, 7.5, "authority_epoch"),
        (0, float("nan"), "lease_expires_at_s must be finite"),
        (0, float("inf"), "lease_expires_at_s must be finite"),
        (0, 2.0, "later than plan.created_at"),
        (0, 1.0, "later than plan.created_at"),
    ),
)
def test_authority_generation_binding_rejects_invalid_values(
    authority_epoch: object,
    lease_expires_at_s: float,
    message: str,
) -> None:
    first = _planner().plan(
        [_track()],
        [ResourceState("R1"), ResourceState("R2")],
        timestamp=2.0,
    )

    with pytest.raises(ValueError, match=message):
        first.bind_authority_generation(  # type: ignore[arg-type]
            authority_epoch,
            lease_expires_at_s,
        )


@pytest.mark.parametrize(
    ("authority_epoch", "lease_expires_at_s"),
    ((4, 12.0), (3, 13.0)),
)
def test_authority_generation_binding_rejects_same_identity_rebinding(
    authority_epoch: int,
    lease_expires_at_s: float,
) -> None:
    bound = _planner().plan(
        [_track()],
        [ResourceState("R1"), ResourceState("R2")],
        timestamp=2.0,
    ).bind_authority_generation(3, 12.0)

    with pytest.raises(
        ValueError,
        match="same plan identity cannot change authority generation binding",
    ):
        bound.bind_authority_generation(authority_epoch, lease_expires_at_s)


def test_same_identity_evaluation_refresh_does_not_renew_authority_lease() -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan([_track()], resources, timestamp=0.0)
    authoritative = first.bind_authority_generation(3, 12.0)

    refreshed = planner.plan(
        [_track()],
        resources,
        timestamp=5.0,
        previous_plan=first,
    )

    assert (refreshed.plan_id, refreshed.version) == (
        authoritative.plan_id,
        authoritative.version,
    )
    assert "authority_epoch" not in refreshed.metadata
    assert "lease_expires_at_s" not in refreshed.metadata

    refreshed_authority = refreshed.bind_authority_generation(3, 12.0)
    assert refreshed_authority.metadata["lease_expires_at_s"] == 12.0
    assert (
        refreshed_authority.authority_signature()
        == authoritative.authority_signature()
    )
    assert (
        refreshed_authority.requires_authoritative_publication(authoritative)
        is False
    )
    with pytest.raises(
        ValueError,
        match="same plan identity cannot change authority generation binding",
    ):
        refreshed_authority.bind_authority_generation(3, 13.0)


def test_planner_post_publish_binding_rebases_refresh_execution_signature() -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan([_track()], resources, timestamp=0.0)

    authoritative = planner.bind_published_authority_generation(
        first,
        authority_epoch=3,
        lease_expires_at_s=12.0,
    )
    refreshed = planner.plan(
        [_track()],
        resources,
        timestamp=13.0,
        previous_plan=authoritative,
    )

    assert (refreshed.plan_id, refreshed.version) == (
        authoritative.plan_id,
        authoritative.version,
    )
    assert refreshed.metadata["authority_epoch"] == 3
    assert refreshed.metadata["lease_expires_at_s"] == 12.0
    assert refreshed.metadata["regional_max_epoch"] == 3
    assert refreshed.metadata["regional_min_lease_expires_at_s"] == 12.0
    assert refreshed.metadata["last_evaluated_at_s"] == 13.0
    assert refreshed.requires_authoritative_publication(authoritative) is False
    assert (
        planner.bind_published_authority_generation(refreshed, 3, 12.0)
        is refreshed
    )
    with pytest.raises(
        ValueError,
        match="same plan identity cannot change authority generation binding",
    ):
        planner.bind_published_authority_generation(refreshed, 3, 13.0)

    changed = planner.plan(
        [_track(preferred="R2")],
        resources,
        timestamp=14.0,
        previous_plan=refreshed,
    )
    assert (changed.plan_id, changed.version) != (
        refreshed.plan_id,
        refreshed.version,
    )
    assert _AUTHORITY_BINDING_KEYS.isdisjoint(changed.metadata)

    rebound = planner.bind_published_authority_generation(
        changed,
        authority_epoch=4,
        lease_expires_at_s=20.0,
    )
    assert {
        rebound.metadata[key] for key in _AUTHORITY_BINDING_KEYS
    } == {4, 20.0}


def test_bound_plan_fence_starts_unbound_and_accepts_new_generation() -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    first = planner.plan([_track()], resources, timestamp=0.0)
    authoritative = planner.bind_published_authority_generation(
        first,
        authority_epoch=1,
        lease_expires_at_s=5.0,
    )

    fenced = planner.advance_authority_generation(
        authoritative,
        timestamp=1.0,
        expected_previous_version=authoritative.version,
        fence_reason="center_failure_before_regional_adjudication",
    )

    assert (fenced.plan_id, fenced.version) != (
        authoritative.plan_id,
        authoritative.version,
    )
    assert _AUTHORITY_BINDING_KEYS.isdisjoint(fenced.metadata)
    rebound = planner.bind_published_authority_generation(
        fenced,
        authority_epoch=fenced.version,
        lease_expires_at_s=6.0,
    )
    assert rebound.metadata["authority_epoch"] == fenced.version
    assert rebound.metadata["lease_expires_at_s"] == 6.0
    assert rebound.metadata["regional_max_epoch"] == fenced.version
    assert rebound.metadata["regional_min_lease_expires_at_s"] == 6.0


def test_secondary_successors_bind_only_their_namespaced_generation() -> None:
    planner = _planner()
    resources = [ResourceState("R1"), ResourceState("R2")]
    center = planner.plan([_track()], resources, timestamp=0.0)
    center = planner.bind_published_authority_generation(
        center,
        authority_epoch=1,
        lease_expires_at_s=4.0,
    )
    takeover_candidate = planner.plan(
        [_track()],
        resources,
        timestamp=1.0,
        previous_plan=center,
        publish=False,
    )
    takeover = prepare_secondary_takeover_plan(
        takeover_candidate,
        supersedes_plan=center,
        secondary_node_id="secondary-node-2",
        readiness_class="takeover_ready",
        readiness_sustained=True,
        activated_at_s=1.1,
        lease_expires_at_s=5.0,
        leader_epoch=2,
    )

    assert _AUTHORITY_BINDING_KEYS.isdisjoint(takeover.metadata)
    assert takeover.metadata["secondary_leader_epoch"] == 2
    assert takeover.metadata["secondary_lease_expires_at_s"] == 5.0
    with pytest.raises(
        ValueError,
        match="authority_epoch must match secondary_leader_epoch",
    ):
        takeover.bind_authority_generation(3, 5.0)
    with pytest.raises(
        ValueError,
        match="must match secondary_lease_expires_at_s",
    ):
        takeover.bind_authority_generation(2, 5.5)

    takeover = planner.publish_plan(takeover)
    takeover = planner.bind_published_authority_generation(
        takeover,
        authority_epoch=2,
        lease_expires_at_s=5.0,
    )
    next_candidate = planner.plan(
        [_track(preferred="R2")],
        resources,
        timestamp=2.0,
        previous_plan=takeover,
        publish=False,
    )
    continued = continue_active_secondary_plan(
        next_candidate,
        previous_plan=takeover,
        readiness_class="takeover_ready",
        readiness_sustained=True,
        published_at_s=2.1,
        lease_expires_at_s=8.0,
        leader_epoch=3,
    )

    assert _AUTHORITY_BINDING_KEYS.isdisjoint(continued.metadata)
    assert continued.metadata["secondary_leader_epoch"] == 3
    assert continued.metadata["secondary_lease_expires_at_s"] == 8.0
    continued = planner.publish_plan(continued)
    continued = planner.bind_published_authority_generation(
        continued,
        authority_epoch=3,
        lease_expires_at_s=8.0,
    )
    assert continued.metadata["authority_epoch"] == 3
    assert continued.metadata["lease_expires_at_s"] == 8.0
