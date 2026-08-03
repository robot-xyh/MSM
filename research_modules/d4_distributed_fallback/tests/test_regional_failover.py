from __future__ import annotations

import pytest

from d4_distributed_fallback.coalition_safety import CoalitionMemberAck
from d4_distributed_fallback.models import C2Health
from d4_distributed_fallback.regional_failover import (
    D5Consistency,
    MobileReconSecondary,
    RegionDefinition,
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverCoordinator,
    RegionalFailoverSnapshot,
    RegionalFallbackMember,
    RegionalScenarioMetadata,
    RegionalTaskEvidence,
    SCALABLE_3D_BUS_SCHEMA,
)
from d4_distributed_fallback.secondary_readiness import SecondaryReadinessEvidence


PLAN_ID = "regional-plan"
CENTER_ID = "CENTER"
REGION_ID = "region-000"


def _scenario(
    *,
    task_count: int = 1,
    resource_count: int = 2,
    recon_count: int = 1,
    region_count: int = 1,
) -> RegionalScenarioMetadata:
    return RegionalScenarioMetadata.from_scalable_scenario(
        {
            "schema_version": "scalable3d-scenario-v1",
            "scenario_name": f"scale-{task_count}",
            "scenario_version": "test-v1",
            "target_count": task_count,
            "resource_count": resource_count,
            "recon_count": recon_count,
            "region_count": region_count,
        }
    )


def _regions(scenario: RegionalScenarioMetadata) -> tuple[RegionDefinition, ...]:
    return tuple(
        RegionDefinition(
            region_id=region_id,
            coverage_cell=f"cell-{index}",
            neighbor_region_ids=(
                (scenario.region_ids[index + 1],)
                if index + 1 < scenario.region_count
                else ()
            ),
        )
        for index, region_id in enumerate(scenario.region_ids)
    )


def _task(
    *,
    task_id: str = "task-1",
    global_track_id: str = "G-1",
    region_id: str = REGION_ID,
    plan_version: int = 1,
    epoch: int = 1,
    lease_expires_at_s: float = 20.0,
    required_member_count: int = 1,
    assigned_member_ids: tuple[str, ...] = ("INT-1",),
    required_capabilities: tuple[str, ...] = ("intercept",),
    **changes: object,
) -> RegionalTaskEvidence:
    values: dict[str, object] = {
        "task_id": task_id,
        "global_track_id": global_track_id,
        "region_id": region_id,
        "d3_plan_id": PLAN_ID,
        "d3_plan_version": plan_version,
        "d3_epoch": epoch,
        "d3_lease_expires_at_s": lease_expires_at_s,
        "required_member_count": required_member_count,
        "required_capabilities": required_capabilities,
        "d3_assigned_member_ids": assigned_member_ids,
        "coalition_id": (
            f"coalition-{global_track_id}" if required_member_count > 1 else None
        ),
        "coalition_version": plan_version if required_member_count > 1 else None,
    }
    values.update(changes)
    return RegionalTaskEvidence(**values)


def _readiness(
    node_id: str,
    *,
    now_s: float,
    epoch: int,
    lease_expires_at_s: float = 20.0,
    coverage_ratio: float = 0.90,
) -> SecondaryReadinessEvidence:
    return SecondaryReadinessEvidence(
        node_id=node_id,
        current_time_s=now_s,
        readiness_timestamp_s=now_s,
        readiness_stale_after_s=1.0,
        availability_confirmed=True,
        lease_epoch=epoch,
        lease_expires_at_s=lease_expires_at_s,
        heartbeat_timestamp_s=now_s,
        heartbeat_stale_after_s=1.0,
        cue_freshness_s=0.05,
        cue_stale_after_s=1.0,
        gimbal_pointing_ok=True,
        communication_received_timestamp_s=now_s,
        communication_stale_after_s=1.0,
        coverage_matches_requested_cell=True,
        coverage_ratio=coverage_ratio,
        network_full_view_rate=0.90,
        takeover_ready_sustained=True,
        takeover_ready_since_s=max(0.0, now_s - 0.5),
        takeover_ready_observation_count=3,
    )


def _secondary(
    *,
    now_s: float,
    epoch: int,
    region_id: str = REGION_ID,
    node_id: str = "RECON-1",
    lease_expires_at_s: float = 20.0,
    coverage_ratio: float = 0.90,
    priority: int = 10,
) -> MobileReconSecondary:
    return MobileReconSecondary(
        node_id=node_id,
        readiness_by_region={
            region_id: _readiness(
                node_id,
                now_s=now_s,
                epoch=epoch,
                lease_expires_at_s=lease_expires_at_s,
                coverage_ratio=coverage_ratio,
            )
        },
        takeover_priority=priority,
    )


def _members(*node_ids: str) -> tuple[RegionalFallbackMember, ...]:
    return tuple(
        RegionalFallbackMember(
            node_id=node_id,
            region_ids=(REGION_ID,),
            capabilities=("intercept", "visual" if index == 0 else "intercept"),
            task_bid_scores={"task-1": 10.0 - index},
        )
        for index, node_id in enumerate(node_ids)
    )


def _ack(
    member_id: str,
    *,
    plan_version: int,
    epoch: int,
    now_s: float,
    valid_until: float = 20.0,
) -> CoalitionMemberAck:
    return CoalitionMemberAck(
        resource_id=member_id,
        global_track_id="G-1",
        coalition_id="coalition-G-1",
        coalition_version=plan_version,
        plan_id=PLAN_ID,
        plan_version=plan_version,
        epoch=epoch,
        can_execute=True,
        evidence_timestamp=now_s,
        valid_until=valid_until,
    )


def _snapshot(
    *,
    now_s: float,
    health: C2Health,
    plan_version: int,
    epoch: int,
    tasks: tuple[RegionalTaskEvidence, ...],
    secondaries: tuple[MobileReconSecondary, ...] = (),
    members: tuple[RegionalFallbackMember, ...] = (),
    acks: tuple[CoalitionMemberAck, ...] = (),
    lease_expires_at_s: float = 20.0,
    partitions: tuple[str, ...] = (),
    finalize_coalition_collection: bool = False,
    scenario: RegionalScenarioMetadata | None = None,
) -> RegionalFailoverSnapshot:
    resolved_scenario = scenario or _scenario(
        task_count=max(1, len(tasks)),
        resource_count=max(1, len(members)),
        recon_count=len(secondaries),
    )
    return RegionalFailoverSnapshot(
        timestamp_s=now_s,
        scenario=resolved_scenario,
        center_health=health,
        center_node_id=CENTER_ID,
        plan_id=PLAN_ID,
        plan_version=plan_version,
        epoch=epoch,
        lease_expires_at_s=lease_expires_at_s,
        regions=_regions(resolved_scenario),
        tasks=tasks,
        secondary_nodes=secondaries,
        fallback_members=members,
        coalition_acks=acks,
        partitioned_region_ids=partitions,
        finalize_coalition_collection=finalize_coalition_collection,
    )


@pytest.mark.parametrize("scale", [5, 20, 50, 100, 200])
def test_scalable_scenario_metadata_and_center_ownership_cover_all_regions(scale: int) -> None:
    scenario = _scenario(
        task_count=scale,
        resource_count=scale,
        recon_count=max(1, scale // 25),
        region_count=scale,
    )
    tasks = tuple(
        _task(
            task_id=f"task-{index}",
            global_track_id=f"G-{index}",
            region_id=region_id,
            assigned_member_ids=(f"INT-{index}",),
        )
        for index, region_id in enumerate(scenario.region_ids)
    )
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=tasks,
            scenario=scenario,
        )
    )
    payload = decision.to_bus_payload()

    assert scenario.bus_schema_version == SCALABLE_3D_BUS_SCHEMA
    assert len(set(scenario.region_ids)) == scale
    assert decision.region_count == scale
    assert decision.task_count == scale
    assert payload["summary"]["region_count"] == scale
    assert payload["summary"]["task_count"] == scale
    assert payload["summary"]["node_count"] == scale + max(1, scale // 25)
    assert payload["summary"]["selected_layer_counts"]["center"] == scale
    assert all(
        item.ownership.owner_id == CENTER_ID
        and item.ownership.active
        and item.action == RegionalAction.CONTINUE_CENTER
        for item in decision.region_decisions
    )


def test_unique_online_task_hypotheses_may_exceed_configured_scenario_count() -> None:
    scenario = _scenario(task_count=1, resource_count=2)
    tasks = (
        _task(task_id="task-1", global_track_id="G-1"),
        _task(task_id="task-2", global_track_id="G-2"),
    )

    snapshot = _snapshot(
        now_s=1.0,
        health=C2Health.NORMAL,
        plan_version=1,
        epoch=1,
        tasks=tasks,
        scenario=scenario,
    )
    decision = RegionalFailoverCoordinator().evaluate(snapshot)

    assert scenario.task_count == 1
    assert len(snapshot.tasks) == 2
    assert decision.task_count == 2
    assert all(
        item.action == RegionalAction.CONTINUE_CENTER
        for item in decision.region_decisions
    )


@pytest.mark.parametrize(
    "tasks, message",
    [
        (
            (
                _task(task_id="task-1", global_track_id="G-1"),
                _task(task_id="task-1", global_track_id="G-2"),
            ),
            "task ids must be unique",
        ),
        (
            (
                _task(task_id="task-1", global_track_id="G-1"),
                _task(task_id="task-2", global_track_id="G-1"),
            ),
            "global_track_id values must be unique across active tasks",
        ),
    ],
)
def test_excess_online_hypotheses_do_not_relax_identity_uniqueness(
    tasks: tuple[RegionalTaskEvidence, ...], message: str
) -> None:
    scenario = _scenario(task_count=1, resource_count=2)

    with pytest.raises(ValueError, match=message):
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=tasks,
            scenario=scenario,
        )


def test_center_keeps_authority_while_active_d1_d2_evidence_requests_recon_assist() -> None:
    task = _task(
        d1_covariance_trace=3000.0,
        d2_ambiguity_score=0.8,
        d5_consistency=D5Consistency.CONSISTENT,
    )
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
            secondaries=(_secondary(now_s=1.0, epoch=1),),
            members=_members("INT-1"),
        )
    ).region_decisions[0]

    assert decision.action == RegionalAction.REQUEST_SECONDARY_ASSIST
    assert decision.ownership.owner_layer == RegionalAuthorityLayer.CENTER
    assert decision.ownership.owner_id == CENTER_ID
    assert decision.execution_allowed is True
    assert "d1_covariance_trace_high" in decision.risk_factors
    assert "d2_association_ambiguity_high" in decision.risk_factors


def test_d3_invalidity_and_d5_hard_conflict_keep_center_owner_but_fail_closed() -> None:
    task = _task(d3_is_current=False, d5_binding_conflict=True)
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
        )
    ).region_decisions[0]

    assert decision.action == RegionalAction.REQUEST_CENTER_REPLAN
    assert decision.ownership.owner_id == CENTER_ID
    assert decision.ownership.active is False
    assert decision.fail_closed is True
    assert "d3_assignment_not_current" in decision.rejection_reasons
    assert "d5_binding_conflict" in decision.risk_factors


def test_center_k2_requires_atomic_full_ack_before_execution() -> None:
    members = _members("INT-1", "INT-2")
    task = _task(
        required_member_count=2,
        assigned_member_ids=("INT-1", "INT-2"),
    )
    missing = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
            members=members,
            acks=(_ack("INT-1", plan_version=1, epoch=1, now_s=1.0),),
        )
    ).region_decisions[0]

    assert missing.selected_layer == RegionalAuthorityLayer.CENTER
    assert missing.action == RegionalAction.HOLD_FOR_REVIEW
    assert missing.ownership.owner_id == CENTER_ID
    assert missing.ownership.active is False
    assert missing.coalition_commits[0].state == "collecting_acks"
    assert missing.coalition_commits[0].atomic_committed is False

    committed = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
            members=members,
            acks=(
                _ack("INT-1", plan_version=1, epoch=1, now_s=1.0),
                _ack("INT-2", plan_version=1, epoch=1, now_s=1.0),
            ),
        )
    ).region_decisions[0]

    assert committed.action == RegionalAction.CONTINUE_CENTER
    assert committed.execution_allowed is True
    assert committed.ownership.owner_id == CENTER_ID
    assert committed.coalition_commits[0].state == "committed"
    assert committed.coalition_commits[0].atomic_committed is True


@pytest.mark.parametrize("overflow_kind", ["resource", "recon"])
def test_snapshot_rejects_node_summaries_beyond_declared_counts(
    overflow_kind: str,
) -> None:
    scenario = _scenario(
        task_count=1,
        resource_count=1,
        recon_count=1,
        region_count=1,
    )
    secondaries = (
        (
            _secondary(now_s=1.0, epoch=1, node_id="RECON-1"),
            _secondary(now_s=1.0, epoch=1, node_id="RECON-2"),
        )
        if overflow_kind == "recon"
        else ()
    )
    members = (
        _members("INT-1", "INT-2") if overflow_kind == "resource" else ()
    )
    expected = "resource_count" if overflow_kind == "resource" else "recon_count"

    with pytest.raises(ValueError, match=expected):
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(_task(),),
            secondaries=secondaries,
            members=members,
            scenario=scenario,
        )


def test_center_failure_selects_ready_mobile_recon_by_region_coverage() -> None:
    coordinator = RegionalFailoverCoordinator()
    members = _members("INT-1")
    coordinator.evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(_task(),),
            members=members,
        )
    )
    failed_task = _task(plan_version=2, epoch=2)
    decision = coordinator.evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(failed_task,),
            secondaries=(
                _secondary(
                    now_s=2.0,
                    epoch=2,
                    node_id="RECON-LOW",
                    coverage_ratio=0.70,
                    priority=20,
                ),
                _secondary(
                    now_s=2.0,
                    epoch=2,
                    node_id="RECON-HIGH",
                    coverage_ratio=0.95,
                    priority=10,
                ),
            ),
            members=members,
        )
    ).region_decisions[0]

    assert decision.action == RegionalAction.DEGRADE_TO_SECONDARY
    assert decision.selected_secondary_id == "RECON-HIGH"
    assert decision.ownership.owner_id == "RECON-HIGH"
    assert decision.ownership.owner_role == "mobile_high_recon"
    assert decision.ownership.plan_version == 2
    assert decision.ownership.epoch == 2
    assert decision.execution_allowed is True


def test_existing_secondary_owner_is_reaffirmed_without_a_false_takeover() -> None:
    coordinator = RegionalFailoverCoordinator()
    members = _members("INT-1")
    coordinator.evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(_task(),),
            members=members,
        )
    )
    first = coordinator.evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(_task(plan_version=2, epoch=2),),
            secondaries=(_secondary(now_s=2.0, epoch=2),),
            members=members,
        )
    ).region_decisions[0]
    maintained = coordinator.evaluate(
        _snapshot(
            now_s=2.2,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(_task(plan_version=2, epoch=2),),
            secondaries=(_secondary(now_s=2.2, epoch=2),),
            members=members,
        )
    ).region_decisions[0]
    successor = coordinator.evaluate(
        _snapshot(
            now_s=3.0,
            health=C2Health.FAILED,
            plan_version=3,
            epoch=3,
            tasks=(_task(plan_version=3, epoch=3),),
            secondaries=(_secondary(now_s=3.0, epoch=3),),
            members=members,
        )
    ).region_decisions[0]

    for decision in (first, maintained, successor):
        assert decision.selected_secondary_id == "RECON-1"
        assert decision.ownership.owner_id == "RECON-1"
        assert decision.execution_allowed is True
        assert decision.fail_closed is False
        assert decision.rejection_reasons == ()
    assert maintained.ownership.plan_version == 2
    assert maintained.ownership.epoch == 2
    assert successor.ownership.plan_version == 3
    assert successor.ownership.epoch == 3


def test_secondary_failure_enters_distributed_and_k2_requires_atomic_full_ack() -> None:
    coordinator = RegionalFailoverCoordinator()
    members = _members("INT-1", "INT-2")
    center_task = _task(
        required_member_count=2,
        assigned_member_ids=("INT-1", "INT-2"),
    )
    center = coordinator.evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(center_task,),
            members=members,
            acks=(
                _ack("INT-1", plan_version=1, epoch=1, now_s=1.0),
                _ack("INT-2", plan_version=1, epoch=1, now_s=1.0),
            ),
        )
    ).region_decisions[0]
    assert center.coalition_commits[0].state == "committed"
    assert (
        center.coalition_commits[0].formation_algorithm
        == "d3_center_assignment"
    )
    secondary_task = _task(
        plan_version=2,
        epoch=2,
        required_member_count=2,
        assigned_member_ids=("INT-1", "INT-2"),
    )
    secondary_decision = coordinator.evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(secondary_task,),
            secondaries=(_secondary(now_s=2.0, epoch=2),),
            members=members,
            acks=(
                _ack("INT-1", plan_version=2, epoch=2, now_s=2.0),
                _ack("INT-2", plan_version=2, epoch=2, now_s=2.0),
            ),
        )
    ).region_decisions[0]
    assert secondary_decision.execution_allowed is True
    assert secondary_decision.coalition_commits[0].state == "committed"
    assert (
        secondary_decision.coalition_commits[0].formation_algorithm
        == "d3_assignment_secondary_coordination"
    )

    distributed_task = _task(
        plan_version=3,
        epoch=3,
        required_member_count=2,
        assigned_member_ids=("INT-1", "INT-2"),
    )
    distributed_decision = coordinator.evaluate(
        _snapshot(
            now_s=3.0,
            health=C2Health.FAILED,
            plan_version=3,
            epoch=3,
            tasks=(distributed_task,),
            members=members,
            acks=(
                _ack("INT-1", plan_version=3, epoch=3, now_s=3.0),
                _ack("INT-2", plan_version=3, epoch=3, now_s=3.0),
            ),
        )
    ).region_decisions[0]

    commit = distributed_decision.coalition_commits[0]
    assert distributed_decision.action == RegionalAction.DEGRADE_TO_DISTRIBUTED
    assert distributed_decision.ownership.owner_layer == RegionalAuthorityLayer.DISTRIBUTED
    assert distributed_decision.ownership.owner_id == "INT-1"
    assert distributed_decision.fallback_assignments["task-1"] == ("INT-1", "INT-2")
    assert commit.commit_required is True
    assert commit.acked_member_ids == ("INT-1", "INT-2")
    assert commit.atomic_committed is True
    assert commit.execution_authorized is True
    assert commit.formation_algorithm == "bounded_constrained_bid_selection"


def test_regional_k3_collects_network_acks_across_successive_snapshots() -> None:
    coordinator = RegionalFailoverCoordinator()
    members = _members("INT-1", "INT-2", "INT-3")
    task = _task(
        required_member_count=3,
        assigned_member_ids=("INT-1", "INT-2", "INT-3"),
    )

    proposed = coordinator.evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
            members=members,
        )
    ).region_decisions[0]
    first_ack = coordinator.evaluate(
        _snapshot(
            now_s=1.2,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
            members=members,
            acks=(_ack("INT-1", plan_version=1, epoch=1, now_s=1.1),),
        )
    ).region_decisions[0]
    second_ack = coordinator.evaluate(
        _snapshot(
            now_s=1.4,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
            members=members,
            acks=(_ack("INT-2", plan_version=1, epoch=1, now_s=1.3),),
        )
    ).region_decisions[0]
    completed = coordinator.evaluate(
        _snapshot(
            now_s=1.6,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
            members=members,
            acks=(_ack("INT-3", plan_version=1, epoch=1, now_s=1.5),),
        )
    ).region_decisions[0]

    assert proposed.coalition_commits[0].state == "collecting_acks"
    assert proposed.coalition_commits[0].acked_member_ids == ()
    assert proposed.execution_allowed is False
    assert first_ack.coalition_commits[0].state == "collecting_acks"
    assert first_ack.coalition_commits[0].acked_member_ids == ("INT-1",)
    assert first_ack.execution_allowed is False
    assert second_ack.coalition_commits[0].state == "collecting_acks"
    assert second_ack.coalition_commits[0].acked_member_ids == (
        "INT-1",
        "INT-2",
    )
    assert second_ack.execution_allowed is False
    assert completed.coalition_commits[0].state == "committed"
    assert completed.coalition_commits[0].acked_member_ids == (
        "INT-1",
        "INT-2",
        "INT-3",
    )
    assert completed.execution_allowed is True


def test_regional_explicit_collection_finalization_aborts_missing_ack() -> None:
    coordinator = RegionalFailoverCoordinator()
    members = _members("INT-1", "INT-2")
    task = _task(
        required_member_count=2,
        assigned_member_ids=("INT-1", "INT-2"),
    )
    collecting = coordinator.evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
            members=members,
        )
    ).region_decisions[0]
    finalized = coordinator.evaluate(
        _snapshot(
            now_s=1.2,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(task,),
            members=members,
            finalize_coalition_collection=True,
        )
    ).region_decisions[0]

    assert collecting.coalition_commits[0].state == "collecting_acks"
    assert finalized.coalition_commits[0].state == "aborted"
    assert finalized.coalition_commits[0].reason == "missing_required_acks"
    assert finalized.execution_allowed is False


@pytest.mark.parametrize("missing_member", ["INT-1", "INT-2"])
def test_k2_missing_ack_is_never_partially_committed(missing_member: str) -> None:
    members = _members("INT-1", "INT-2")
    task = _task(
        plan_version=2,
        epoch=2,
        required_member_count=2,
        assigned_member_ids=("INT-1", "INT-2"),
    )
    acked_member = "INT-2" if missing_member == "INT-1" else "INT-1"
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(task,),
            members=members,
            acks=(_ack(acked_member, plan_version=2, epoch=2, now_s=2.0),),
        )
    ).region_decisions[0]

    commit = decision.coalition_commits[0]
    assert decision.selected_layer == RegionalAuthorityLayer.DISTRIBUTED
    assert decision.action == RegionalAction.HOLD_FOR_REVIEW
    assert decision.execution_allowed is False
    assert decision.ownership.owner_id is None
    assert commit.state == "collecting_acks"
    assert commit.atomic_committed is False
    assert commit.missing_member_ids == (missing_member,)


def test_stale_ack_epoch_is_rejected_and_commit_fails_closed() -> None:
    members = _members("INT-1", "INT-2")
    task = _task(
        plan_version=2,
        epoch=2,
        required_member_count=2,
        assigned_member_ids=("INT-1", "INT-2"),
    )
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(task,),
            members=members,
            acks=(
                _ack("INT-1", plan_version=2, epoch=1, now_s=2.0),
                _ack("INT-2", plan_version=2, epoch=2, now_s=2.0),
            ),
        )
    ).region_decisions[0]

    commit = decision.coalition_commits[0]
    assert decision.fail_closed is True
    assert commit.state == "collecting_acks"
    assert "ack_epoch_stale" in commit.rejected_ack_reasons
    assert commit.atomic_committed is False


def test_network_partition_revokes_committed_distributed_region() -> None:
    coordinator = RegionalFailoverCoordinator()
    members = _members("INT-1", "INT-2")
    task = _task(
        plan_version=2,
        epoch=2,
        required_member_count=2,
        assigned_member_ids=("INT-1", "INT-2"),
    )
    committed = coordinator.evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(task,),
            members=members,
            acks=(
                _ack("INT-1", plan_version=2, epoch=2, now_s=2.0),
                _ack("INT-2", plan_version=2, epoch=2, now_s=2.0),
            ),
        )
    ).region_decisions[0]
    assert committed.execution_allowed is True

    partitioned = coordinator.evaluate(
        _snapshot(
            now_s=3.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(task,),
            members=members,
            partitions=(REGION_ID,),
        )
    ).region_decisions[0]

    assert partitioned.action == RegionalAction.HOLD_FOR_REVIEW
    assert partitioned.execution_allowed is False
    assert partitioned.ownership.owner_id is None
    assert partitioned.coalition_commits[0].state == "reconfiguring"
    assert partitioned.coalition_commits[0].reason == "network_partition"


def test_network_partition_fails_closed_while_center_is_healthy() -> None:
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=1.0,
            health=C2Health.NORMAL,
            plan_version=1,
            epoch=1,
            tasks=(_task(),),
            partitions=(REGION_ID,),
        )
    ).region_decisions[0]

    assert decision.selected_layer == RegionalAuthorityLayer.CENTER
    assert decision.action == RegionalAction.HOLD_FOR_REVIEW
    assert decision.reason == "network_partition"
    assert decision.execution_allowed is False
    assert decision.ownership.owner_id is None


def test_stale_authority_epoch_and_plan_version_are_rejected() -> None:
    coordinator = RegionalFailoverCoordinator()
    members = _members("INT-1")
    current_task = _task(plan_version=3, epoch=3)
    current = coordinator.evaluate(
        _snapshot(
            now_s=3.0,
            health=C2Health.FAILED,
            plan_version=3,
            epoch=3,
            tasks=(current_task,),
            members=members,
        )
    ).region_decisions[0]
    assert current.execution_allowed is True

    stale_task = _task(plan_version=2, epoch=2)
    stale = coordinator.evaluate(
        _snapshot(
            now_s=4.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(stale_task,),
            members=members,
        )
    ).region_decisions[0]

    assert stale.fail_closed is True
    assert "authority_epoch_stale" in stale.rejection_reasons
    assert "authority_plan_version_stale" in stale.rejection_reasons


def test_expired_authority_lease_and_stale_secondary_lease_are_rejected() -> None:
    expired_task = _task(
        plan_version=2,
        epoch=2,
        lease_expires_at_s=2.0,
    )
    expired = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(expired_task,),
            members=_members("INT-1"),
            lease_expires_at_s=2.0,
        )
    ).region_decisions[0]
    assert expired.fail_closed is True
    assert "authority_lease_expired" in expired.rejection_reasons

    task = _task(plan_version=2, epoch=2)
    stale_secondary = _secondary(now_s=2.0, epoch=1)
    stale = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(task,),
            secondaries=(stale_secondary,),
        )
    ).region_decisions[0]
    assert stale.selected_secondary_id is None
    assert stale.secondary_readiness["RECON-1"]["ready"] is False
    assert "secondary_lease_epoch_stale" in stale.secondary_readiness["RECON-1"][
        "reject_reasons"
    ]
    assert stale.fail_closed is True


def test_secondary_only_owns_regions_with_explicit_coverage_evidence() -> None:
    scenario = _scenario(task_count=2, resource_count=2, recon_count=2, region_count=2)
    region_a, region_b = scenario.region_ids
    tasks = (
        _task(
            region_id=region_a,
            task_id="task-a",
            global_track_id="G-A",
            plan_version=2,
            epoch=2,
            assigned_member_ids=("INT-A",),
        ),
        _task(
            region_id=region_b,
            task_id="task-b",
            global_track_id="G-B",
            plan_version=2,
            epoch=2,
            assigned_member_ids=("INT-B",),
        ),
    )
    members = (
        RegionalFallbackMember("INT-A", (region_a,)),
        RegionalFallbackMember("INT-B", (region_b,)),
    )
    secondary_a = _secondary(
        now_s=2.0,
        epoch=2,
        region_id=region_a,
        node_id="RECON-A",
    )
    secondary_b = _secondary(
        now_s=2.0,
        epoch=2,
        region_id=region_b,
        node_id="RECON-B",
    )
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=tasks,
            secondaries=(secondary_a, secondary_b),
            members=members,
            scenario=scenario,
        )
    )

    owners = {
        region_id: ownership.owner_id
        for region_id, ownership in decision.ownership_by_region.items()
    }
    assert owners == {region_a: "RECON-A", region_b: "RECON-B"}
    assert decision.region_decisions[0].secondary_readiness["RECON-B"][
        "reject_reasons"
    ] == ["region_coverage_missing"]


def test_secondary_rejects_a_d5_held_assigned_member() -> None:
    task = _task(
        plan_version=2,
        epoch=2,
        d5_hold_member_ids=("INT-1",),
    )
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(task,),
            secondaries=(_secondary(now_s=2.0, epoch=2),),
            members=_members("INT-1"),
        )
    ).region_decisions[0]

    assert decision.selected_layer == RegionalAuthorityLayer.SECONDARY
    assert decision.selected_secondary_id == "RECON-1"
    assert decision.action == RegionalAction.HOLD_FOR_REVIEW
    assert decision.execution_allowed is False
    assert "d5_member_hold" in decision.rejection_reasons


def test_distributed_member_can_cover_multiple_capabilities_and_uses_task_lease() -> None:
    task = _task(
        plan_version=2,
        epoch=2,
        lease_expires_at_s=5.0,
        required_capabilities=("intercept", "visual"),
    )
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=(task,),
            members=_members("INT-1"),
            lease_expires_at_s=20.0,
        )
    ).region_decisions[0]

    assert decision.action == RegionalAction.DEGRADE_TO_DISTRIBUTED
    assert decision.fallback_assignments["task-1"] == ("INT-1",)
    assert decision.ownership.lease_expires_at_s == pytest.approx(5.0)
    assert decision.coalition_commits[0].lease_expires_at_s == pytest.approx(5.0)


def test_distributed_capacity_is_enforced_across_regions() -> None:
    scenario = _scenario(task_count=2, resource_count=1, recon_count=0, region_count=2)
    region_a, region_b = scenario.region_ids
    tasks = (
        _task(
            task_id="task-a",
            global_track_id="G-A",
            region_id=region_a,
            plan_version=2,
            epoch=2,
        ),
        _task(
            task_id="task-b",
            global_track_id="G-B",
            region_id=region_b,
            plan_version=2,
            epoch=2,
        ),
    )
    member = RegionalFallbackMember(
        node_id="INT-1",
        region_ids=(region_a, region_b),
        max_concurrent_tasks=1,
        task_bid_scores={"task-a": 2.0, "task-b": 1.0},
    )
    decision = RegionalFailoverCoordinator().evaluate(
        _snapshot(
            now_s=2.0,
            health=C2Health.FAILED,
            plan_version=2,
            epoch=2,
            tasks=tasks,
            members=(member,),
            scenario=scenario,
        )
    )

    first, second = decision.region_decisions
    assert first.execution_allowed is True
    assert first.fallback_assignments["task-a"] == ("INT-1",)
    assert second.execution_allowed is False
    assert "distributed_member_capacity_unsatisfied" in second.rejection_reasons
