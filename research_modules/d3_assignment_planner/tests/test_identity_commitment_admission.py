import pytest

from d3_assignment_planner import (
    AirSimDryRunAssignmentAdapter,
    AssignmentPlanner,
    CostModel,
    CostWeights,
    D3_IDENTITY_COMMITMENT_ADMISSION_SCHEMA_V1,
    IdentityCommitmentState,
    PlannerConfig,
    ResourceState,
    StalePlanError,
    TargetDemand,
    TargetTrack,
    adapt_airsim_global_tracks,
)
from d3_assignment_planner.solver import HungarianAssignmentSolver


def _planner(
    *,
    enable_hysteresis: bool = True,
    max_changes_per_window: int | None = None,
) -> AssignmentPlanner:
    config = PlannerConfig(
        enable_hysteresis=enable_hysteresis,
        delta=0.9,
        min_dwell=100.0,
        max_changes_per_window=max_changes_per_window,
    )
    return AssignmentPlanner(
        cost_model=CostModel(
            weights=CostWeights(
                window=0.0,
                covariance=0.0,
                threat=0.0,
                resource_state=0.0,
                fov=0.0,
                conflict=0.0,
            ),
            config=config,
        ),
        solver=HungarianAssignmentSolver(allow_scipy=False),
        config=config,
    )


def _track(
    track_id: str,
    state: str | IdentityCommitmentState | None = IdentityCommitmentState.COMMITTED,
    *,
    demand: TargetDemand | None = None,
) -> TargetTrack:
    return TargetTrack(
        track_id=track_id,
        threat_score=0.8,
        covariance=0.1,
        window_cost=0.1,
        demand=demand,
        identity_commitment_state=state,
    )


def _resources(count: int) -> list[ResourceState]:
    return [ResourceState(f"R-{index:03d}") for index in range(count)]


def test_first_plan_admits_only_committed_targets_with_explicit_audit() -> None:
    planner = _planner(enable_hysteresis=False)
    tracks = [
        _track("T-committed", IdentityCommitmentState.COMMITTED),
        _track(
            "T-hold",
            IdentityCommitmentState.UNCOMMITTED_AMBIGUITY_HOLD,
        ),
        _track(
            "T-after",
            IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD,
        ),
    ]

    plan = planner.plan(tracks, _resources(3), timestamp=1.0)

    assert {item.target_id for item in plan.assignments} == {"T-committed"}
    assert set(plan.unassigned_target_ids) == {"T-hold", "T-after"}
    assert plan.metadata["identity_commitment_admission_schema"] == (
        D3_IDENTITY_COMMITMENT_ADMISSION_SCHEMA_V1
    )
    assert plan.metadata["identity_commitment_committed_admitted_count"] == 1
    assert plan.metadata["identity_commitment_uncommitted_rejected_count"] == 2
    assert plan.metadata["identity_commitment_rejected_target_ids"] == (
        "T-after",
        "T-hold",
    )
    assert {
        item["reject_reason"]
        for item in plan.metadata["identity_commitment_rejection_records"]
    } == {
        IdentityCommitmentState.UNCOMMITTED_AMBIGUITY_HOLD.value,
        IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD.value,
    }
    assert plan.metadata["identity_commitment_offline_label_independent"] is True


@pytest.mark.parametrize(
    "state",
    [
        IdentityCommitmentState.UNCOMMITTED_AMBIGUITY_HOLD,
        IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD,
    ],
)
def test_each_uncommitted_state_is_a_hard_edge_rejection(
    state: IdentityCommitmentState,
) -> None:
    planner = _planner(enable_hysteresis=False)

    plan = planner.plan([_track("T1", state)], _resources(2), timestamp=0.0)

    assert plan.assignments == ()
    assert plan.unassigned_target_ids == ("T1",)
    evidence = planner.latest_planning_evidence
    assert evidence.available is True
    assert evidence.rule_matrix_result is not None
    assert {
        reason
        for row in evidence.rule_matrix_result.reject_reasons
        for reason in row
    } == {state.value}


def test_committed_previous_binding_is_removed_and_reversioned_immediately() -> None:
    planner = _planner(max_changes_per_window=0)
    first_track = _track("T1", IdentityCommitmentState.COMMITTED)
    first = planner.plan([first_track], _resources(1), timestamp=0.0)
    first_signature = first.execution_signature()

    second = planner.plan(
        [
            _track(
                "T1",
                IdentityCommitmentState.UNCOMMITTED_AMBIGUITY_HOLD,
            )
        ],
        _resources(1),
        timestamp=0.1,
        previous_plan=first,
        expected_previous_version=first.version,
    )

    assert first.execution_signature() == first_signature
    assert len(first.assignments) == 1
    assert second.assignments == ()
    assert second.version == first.version + 1
    assert second.plan_id != first.plan_id
    assert second.previous_plan_id == first.plan_id
    assert second.decision_state == "accepted_identity_commitment_replan"
    assert second.metadata["identity_commitment_forced_replan"] is True
    assert second.metadata["identity_commitment_previous_binding_target_ids"] == (
        "T1",
    )
    assert second.metadata["identity_commitment_hysteresis_bypassed"] is True
    assert second.metadata["identity_commitment_replan_reason"] == (
        "previous_target_identity_uncommitted"
    )


def test_uncommitted_m_to_n_target_blocks_all_primary_and_reserve_slots() -> None:
    planner = _planner(enable_hysteresis=False)
    demand = TargetDemand(
        required_resource_count=3,
        primary_resource_count=2,
        coordination_mode="hybrid",
    )

    plan = planner.plan(
        [
            _track(
                "T-high",
                IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD,
                demand=demand,
            )
        ],
        _resources(5),
        timestamp=0.0,
    )

    assert plan.assignments == ()
    assert all(item.target_id != "T-high" for item in plan.coalitions)
    assert plan.unassigned_target_ids == ("T-high",)
    assert plan.incomplete_target_ids == ("T-high",)
    assert plan.demand_summaries[0].demand_required == 3
    assert plan.demand_summaries[0].demand_assigned == 0
    assert plan.demand_summaries[0].demand_shortfall == 3
    assert plan.metadata["identity_commitment_all_primary_reserve_slots_blocked"]


def test_stale_predecessor_is_rejected_before_identity_replan() -> None:
    planner = _planner(enable_hysteresis=False)
    first = planner.plan([_track("T1")], _resources(1), timestamp=0.0)
    second = planner.plan(
        [_track("T1", IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD)],
        _resources(1),
        timestamp=1.0,
        previous_plan=first,
    )

    with pytest.raises(StalePlanError) as exc_info:
        planner.plan(
            [_track("T1", IdentityCommitmentState.COMMITTED)],
            _resources(1),
            timestamp=2.0,
            previous_plan=first,
            expected_previous_version=first.version,
        )

    assert second.version == first.version + 1
    assert exc_info.value.reason == "stale_previous_version"


def test_missing_commitment_field_fails_closed() -> None:
    planner = _planner(enable_hysteresis=False)
    missing_track = _track("T1", None)

    plan = planner.plan([missing_track], _resources(1), timestamp=0.0)

    assert missing_track.identity_commitment_state == "identity_commitment_missing"
    assert missing_track.effective_identity_commitment_state == (
        "identity_commitment_missing"
    )
    assert plan.assignments == ()
    assert plan.unassigned_target_ids == ("T1",)
    assert plan.metadata["identity_commitment_missing_rejected_count"] == 1
    assert plan.metadata["identity_commitment_legacy_assumed_committed_count"] == 0


def test_airsim_adapter_reads_states_and_rejects_missing_commitment() -> None:
    tracks = adapt_airsim_global_tracks(
        [
            {
                "global_track_id": "T-direct",
                "identity_commitment_state": "identity_uncommitted_ambiguity_hold",
            },
            {
                "global_track_id": "T-nested",
                "identity_commitment": {
                    "identity_commitment_state": "identity_uncommitted_after_hold"
                },
            },
            {"global_track_id": "T-legacy"},
            {
                "global_track_id": "T-committed",
                "identity_commitment_state": "committed",
            },
        ]
    )

    assert tracks[0].identity_commitment_state == (
        "identity_uncommitted_ambiguity_hold"
    )
    assert tracks[1].identity_commitment_state == "identity_uncommitted_after_hold"
    assert tracks[2].identity_commitment_state == "identity_commitment_missing"
    assert tracks[3].identity_commitment_state == "committed"
    assert tracks[0].metadata["identity_commitment_input_source"] == (
        "explicit_record_field"
    )
    assert tracks[1].metadata["identity_commitment_input_source"] == (
        "identity_commitment_mapping"
    )
    assert tracks[2].metadata["identity_commitment_input_source"] == (
        "missing_record_field"
    )

    adapter = AirSimDryRunAssignmentAdapter(
        planner=_planner(enable_hysteresis=False)
    )
    plan = adapter.plan(
        [
            {
                "global_track_id": "T-direct",
                "identity_commitment_state": (
                    "identity_uncommitted_ambiguity_hold"
                ),
            },
            {"global_track_id": "T-legacy"},
            {
                "global_track_id": "T-committed",
                "identity_commitment_state": "committed",
            },
        ],
        [
            {"resource_id": "R1"},
            {"resource_id": "R2"},
            {"resource_id": "R3"},
        ],
        timestamp=0.0,
    )
    assert {item.target_id for item in plan.assignments} == {"T-committed"}
    assert set(plan.metadata["identity_commitment_rejected_target_ids"]) == {
        "T-direct",
        "T-legacy",
    }


@pytest.mark.parametrize(
    ("target_count", "resource_count"),
    [(1, 4), (7, 3), (9, 12)],
)
def test_identity_admission_has_no_fixed_n_or_m_assumption(
    target_count: int,
    resource_count: int,
) -> None:
    planner = _planner(enable_hysteresis=False)
    tracks = [
        _track(
            f"T-{index:03d}",
            (
                IdentityCommitmentState.COMMITTED
                if index % 2 == 0
                else IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD
            ),
        )
        for index in range(target_count)
    ]

    plan = planner.plan(tracks, _resources(resource_count), timestamp=0.0)

    assert plan.target_count == target_count
    assert plan.resource_count == resource_count
    assert all(
        int(item.target_id.rsplit("-", 1)[1]) % 2 == 0
        for item in plan.assignments
    )
    assert plan.metadata["identity_commitment_uncommitted_rejected_count"] == (
        target_count // 2
    )


def test_unknown_commitment_state_is_normalized_and_fails_closed() -> None:
    planner = _planner(enable_hysteresis=False)
    track = _track("T1", "unknown_identity_state")

    plan = planner.plan([track], _resources(1), timestamp=0.0)

    assert track.identity_commitment_state == "identity_commitment_unknown"
    assert track.metadata["identity_commitment_unknown_input"] == (
        "unknown_identity_state"
    )
    assert plan.assignments == ()
    assert plan.metadata["identity_commitment_unknown_rejected_count"] == 1
    assert plan.metadata["identity_commitment_rejection_records"] == (
        {
            "target_id": "T1",
            "identity_commitment_state": "identity_commitment_unknown",
            "reject_reason": "identity_commitment_unknown",
        },
    )
