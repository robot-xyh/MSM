from __future__ import annotations
from commitment_test_support import committed_target_track

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from d3_assignment_planner import (
    REGIONAL_PLANNING_HINT_SCHEMA_V1,
    REGIONAL_PLANNING_HINT_SUCCESSOR_SCHEMA_V1,
    AssignmentPlanner,
    LearningAssistConfig,
    LearningCostAssistant,
    PlannerConfig,
    RegionalPlanningConstraint,
    RegionalPlanningHint,
    RegionalPlanningHintError,
    RegionalTransferAllowance,
    ResidualPrediction,
    ResourceState,
    StalePlanError,
    TargetDemand,
    TargetTrack,
)


class _ZeroResidualPredictor:
    def predict(self, features: np.ndarray) -> ResidualPrediction:
        return ResidualPrediction(
            delta_costs=np.zeros(features.shape[0], dtype=float),
            confidence=0.99,
        )


def _planner(
    *,
    learning: bool = False,
    source_node_id: str = "d3_central",
) -> AssignmentPlanner:
    assistant = None
    if learning:
        assistant = LearningCostAssistant(
            _ZeroResidualPredictor(),
            config=LearningAssistConfig(
                mode="assist",
                alpha=0.25,
                min_confidence=0.5,
            ),
        )
    return AssignmentPlanner(
        config=PlannerConfig.scalable_3d(
            enable_hysteresis=False,
            max_candidate_edges_per_target=16,
            human_authorization_state="approved",
            source_node_id=source_node_id,
        ),
        learning_assistant=assistant,
    )


def _track(
    target_id: str,
    region_id: str,
    x: float,
    *,
    demand: TargetDemand | None = None,
    blocked_resource_ids: tuple[str, ...] = (),
) -> TargetTrack:
    return committed_target_track(
        target_id,
        threat_score=0.9,
        covariance=0.1,
        window_cost=0.0,
        position_ned=(x, 0.0, -100.0),
        velocity_ned=(0.0, 0.0, 0.0),
        region_id=region_id,
        feasibility_by_resource={value: False for value in blocked_resource_ids},
        demand=demand,
    )


def _resource(
    resource_id: str,
    region_id: str,
    x: float,
    *,
    status: str = "available",
) -> ResourceState:
    return ResourceState(
        resource_id,
        status=status,
        position_ned=(x, 0.0, -100.0),
        velocity_ned=(0.0, 0.0, 0.0),
        max_speed_mps=20.0,
        max_intercept_range_m=10_000.0,
        region_id=region_id,
    )


def _baseline_inputs(
    *,
    extra_source_resources: int = 1,
) -> tuple[tuple[TargetTrack, ...], tuple[ResourceState, ...]]:
    tracks = (
        _track("T-A", "A", 100.0),
        _track("T-B", "B", 1_000.0),
    )
    resources = (
        _resource("R-A0", "A", 90.0),
        *tuple(
            _resource(f"R-A{index + 1}", "A", 880.0 + index * 20.0)
            for index in range(extra_source_resources)
        ),
        _resource("R-B0", "B", 990.0),
    )
    return tracks, resources


def _hint_mapping(
    previous,
    *,
    transfer_count: int = 1,
    source_reserve_ratio: float = 0.0,
) -> dict[str, object]:
    return {
        "schema": REGIONAL_PLANNING_HINT_SCHEMA_V1,
        "advisory_id": "d4-advice-frame-0001",
        "advisory_version": 1,
        "created_at_s": 0.5,
        "expires_at_s": 10.0,
        "source_plan_id": previous.plan_id,
        "source_plan_version": previous.version,
        "projected": True,
        "constraints": [
            {
                "region_id": "A",
                "owner_id": "CENTER",
                "owner_layer": "center",
                "owner_epoch": previous.version,
                "lease_expires_at_s": 10.0,
                "source_plan_id": previous.plan_id,
                "source_plan_version": previous.version,
                "resource_quota_delta": -transfer_count,
                "reserve_ratio": source_reserve_ratio,
                "hold": False,
                "request_replan": True,
            },
            {
                "region_id": "B",
                "owner_id": "CENTER",
                "owner_layer": "center",
                "owner_epoch": previous.version,
                "lease_expires_at_s": 10.0,
                "source_plan_id": previous.plan_id,
                "source_plan_version": previous.version,
                "resource_quota_delta": transfer_count,
                "reserve_ratio": 0.0,
                "hold": False,
                "request_replan": True,
            },
        ],
        "transfer_allowances": [
            {
                "source_region_id": "A",
                "target_region_id": "B",
                "resource_count": transfer_count,
                "edge_id": "A->B",
                "expected_transfer_time_s": 2.0,
            }
        ],
    }


def _no_transfer_hint_mapping(previous) -> dict[str, object]:
    hint = _hint_mapping(previous)
    for constraint in hint["constraints"]:  # type: ignore[union-attr]
        constraint["resource_quota_delta"] = 0
        constraint["request_replan"] = False
    hint["transfer_allowances"] = []
    return hint


def _three_region_intervention_hint_mapping(previous) -> dict[str, object]:
    hint = _hint_mapping(previous)
    hint["constraints"].append(  # type: ignore[union-attr]
        {
            "region_id": "C",
            "owner_id": "CENTER",
            "owner_layer": "center",
            "owner_epoch": previous.version,
            "lease_expires_at_s": 10.0,
            "source_plan_id": previous.plan_id,
            "source_plan_version": previous.version,
            "resource_quota_delta": 0,
            "reserve_ratio": 0.0,
            "hold": True,
            "request_replan": True,
        }
    )
    return hint


def _uncommitted_region_hold_hint_mapping(previous) -> dict[str, object]:
    hint = _three_region_intervention_hint_mapping(previous)
    for constraint in hint["constraints"]:  # type: ignore[union-attr]
        constraint["resource_quota_delta"] = 0
        constraint["request_replan"] = constraint["region_id"] == "C"
    hint["transfer_allowances"] = []
    return hint


def _three_region_intervention_inputs() -> tuple[
    tuple[TargetTrack, ...],
    tuple[ResourceState, ...],
]:
    tracks = (
        _track("T-A", "A", 100.0),
        _track("T-B", "B", 1_000.0),
        _track("T-C", "C", 2_000.0),
    )
    resources = (
        _resource("R-A0", "A", 90.0),
        _resource("R-A1", "A", 980.0),
        _resource("R-B0", "B", 990.0),
        _resource("R-C0", "C", 1_990.0),
        _resource("R-C1", "C", 2_500.0),
    )
    return tracks, resources


def _assignment_pairs(plan) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((item.target_id, item.resource_id) for item in plan.assignments))


def _bind_published_regional_successor(
    planner: AssignmentPlanner,
    plan,
):
    assert "authority_epoch" not in plan.metadata
    assert "lease_expires_at_s" not in plan.metadata
    authority_epoch = plan.metadata["regional_max_epoch"]
    lease_expires_at_s = plan.metadata[
        "regional_min_lease_expires_at_s"
    ]
    return planner.bind_published_authority_generation(
        plan,
        authority_epoch=authority_epoch,
        lease_expires_at_s=lease_expires_at_s,
    )


def _hint_after_source_plan(
    previous,
    *,
    transfer_count: int = 0,
) -> dict[str, object]:
    hint = (
        _no_transfer_hint_mapping(previous)
        if transfer_count == 0
        else _hint_mapping(previous, transfer_count=transfer_count)
    )
    hint["advisory_id"] = "d4-advice-frame-0002"
    hint["advisory_version"] = 2
    hint["created_at_s"] = 1.5
    hint["expires_at_s"] = 9.0
    return hint


def _cross_region_source_plan():
    planner = _planner(source_node_id="CENTER")
    tracks, resources = _baseline_inputs(extra_source_resources=2)
    initial = planner.plan(tracks, resources, timestamp=0.0)
    active_resources = (
        resources[0],
        resources[1],
        resources[2],
        _resource("R-B0", "B", 990.0, status="unavailable"),
    )
    source = planner.plan(
        tracks,
        active_resources,
        timestamp=1.0,
        previous_plan=initial,
        regional_planning_hint=_hint_mapping(initial),
    )
    source = _bind_published_regional_successor(planner, source)
    source_pair = next(
        item
        for item in source.assignments
        if item.target_id == "T-B"
    )
    assert source_pair.resource_id in {"R-A1", "R-A2"}
    return planner, tracks, active_resources, source, source_pair.resource_id


def test_strict_mapping_factory_is_d3_owned_frozen_and_identity_safe() -> None:
    tracks, resources = _baseline_inputs()
    previous = _planner().plan(tracks, resources, timestamp=0.0)
    raw = _hint_mapping(previous)

    hint = RegionalPlanningHint.from_mapping(raw)

    assert hint.schema == REGIONAL_PLANNING_HINT_SCHEMA_V1
    assert isinstance(hint.constraints[0], RegionalPlanningConstraint)
    assert isinstance(hint.transfer_allowances[0], RegionalTransferAllowance)
    with pytest.raises(FrozenInstanceError):
        hint.advisory_id = "mutated"  # type: ignore[misc]

    forbidden = deepcopy(raw)
    forbidden["actor_truth_id"] = "AirSimActor"
    with pytest.raises(RegionalPlanningHintError) as error:
        RegionalPlanningHint.from_mapping(forbidden)
    assert error.value.reason == "regional_hint_forbidden_identity_field"

    nested_forbidden = deepcopy(raw)
    nested_forbidden["constraints"][0]["object_id"] = "physical-object"  # type: ignore[index]
    with pytest.raises(RegionalPlanningHintError) as error:
        RegionalPlanningHint.from_mapping(nested_forbidden)
    assert error.value.reason == "regional_hint_forbidden_identity_field"

    unknown = deepcopy(raw)
    unknown["confidence"] = 0.9
    with pytest.raises(RegionalPlanningHintError) as error:
        RegionalPlanningHint.from_mapping(unknown)
    assert error.value.reason == "regional_hint_mapping_unknown_field"


def test_no_hint_keeps_rule_and_hungarian_result_unchanged() -> None:
    tracks, resources = _baseline_inputs(extra_source_resources=2)
    implicit = _planner().plan(tracks, resources, timestamp=0.0)
    explicit = _planner().plan(
        tracks,
        resources,
        timestamp=0.0,
        regional_planning_hint=None,
    )

    assert _assignment_pairs(implicit) == _assignment_pairs(explicit)
    assert implicit.total_cost == pytest.approx(explicit.total_cost)
    assert implicit.solver_name == explicit.solver_name
    assert implicit.metadata["candidate_edge_count"] == explicit.metadata[
        "candidate_edge_count"
    ]
    assert implicit.metadata["regional_hint_available"] is False
    assert implicit.metadata["regional_hint_considered"] is False
    assert implicit.metadata["regional_hint_applied"] is False
    assert implicit.metadata["regional_hint_rejected"] is False


def test_valid_hint_opens_a_real_bounded_cross_region_candidate_edge() -> None:
    planner = _planner()
    tracks, resources = _baseline_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    next_resources = (
        resources[0],
        resources[1],
        _resource("R-B0", "B", 990.0, status="unavailable"),
    )

    plan = planner.plan(
        tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_hint_mapping(previous),
    )

    assert _assignment_pairs(plan) == (("T-A", "R-A0"), ("T-B", "R-A1"))
    assert plan.solver_name in {"scipy_hungarian", "fallback_dp"}
    assert plan.metadata["regional_hint_available"] is True
    assert plan.metadata["regional_hint_considered"] is True
    assert plan.metadata["regional_hint_applied"] is True
    assert plan.metadata["regional_hint_rejected"] is False
    assert plan.metadata["regional_hint_advisory_id"] == "d4-advice-frame-0001"
    assert plan.metadata["regional_hint_source_plan_id"] == previous.plan_id
    assert plan.metadata["regional_hint_source_plan_version"] == previous.version
    assert plan.metadata["regional_hint_actual_cross_region_resource_count"] == 1
    assert plan.metadata["regional_hint_cross_region_limit_satisfied"] is True
    assert plan.metadata["regional_hint_fallback_reason"] is None
    assert plan.metadata["regional_hint_transfer_usage"] == (
        {
            "source_region_id": "A",
            "target_region_id": "B",
            "allowed_resource_count": 1,
            "actual_resource_count": 1,
            "incremental_allowed_resource_count": 1,
            "incremental_actual_resource_count": 1,
            "baseline_committed_resource_count": 0,
            "retained_baseline_resource_count": 0,
            "total_actual_resource_count": 1,
        },
    )


def test_applied_hint_publishes_then_binds_uniform_authority() -> None:
    planner = _planner()
    tracks, resources = _baseline_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    next_tracks = (*tracks, _track("T-B2", "B", 1_020.0))

    plan = planner.plan(
        next_tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_hint_mapping(previous),
    )

    assert plan.version == previous.version + 1
    assert plan.plan_id != previous.plan_id
    assert plan.metadata["execution_signature_changed"] is True
    assert plan.metadata["regional_hint_constraint_applied"] is True
    assert plan.metadata["regional_hint_applied"] is True
    assert plan.metadata["regional_hint_rejected"] is False
    assert plan.metadata["regional_hint_successor_schema"] == (
        REGIONAL_PLANNING_HINT_SUCCESSOR_SCHEMA_V1
    )
    assert plan.metadata["regional_hint_successor_state"] == (
        "successor_published"
    )
    assert plan.metadata["regional_hint_successor_plan_available"] is True
    assert plan.metadata["regional_hint_successor_plan_id"] == plan.plan_id
    assert plan.metadata["regional_hint_successor_plan_version"] == plan.version
    assert plan.metadata["regional_hint_successor_source_plan_id"] == (
        previous.plan_id
    )
    assert plan.metadata["regional_hint_successor_source_plan_version"] == (
        previous.version
    )
    assert plan.metadata["regional_hint_successor_rejection_reason"] is None
    assert plan.metadata["plan_owner"] == "center"
    assert plan.metadata["active_plan_owner"] == "center"
    assert plan.metadata["current_plan_owner"] == "center"
    assert plan.metadata["owner_node_id"] == "CENTER"
    assert plan.metadata["current_plan_owner_node_id"] == "CENTER"
    assert "authority_epoch" not in plan.metadata
    assert "lease_expires_at_s" not in plan.metadata
    assert plan.metadata["regional_max_epoch"] == previous.version
    assert plan.metadata["regional_min_lease_expires_at_s"] == pytest.approx(
        10.0
    )

    bound = _bind_published_regional_successor(planner, plan)
    assert bound.metadata["authority_epoch"] == previous.version
    assert bound.metadata["lease_expires_at_s"] == pytest.approx(10.0)
    assert bound.metadata["regional_max_epoch"] == previous.version
    assert bound.metadata["regional_min_lease_expires_at_s"] == pytest.approx(
        10.0
    )


def test_nonzero_transfer_and_hold_produce_attributable_strict_successor() -> None:
    planner = _planner(source_node_id="CENTER")
    initial_tracks, initial_resources = _three_region_intervention_inputs()
    source = planner.plan(initial_tracks, initial_resources, timestamp=0.0)
    source_bindings = frozenset(_assignment_pairs(source))
    source_signature = source.execution_signature()
    assert source_bindings == {
        ("T-A", "R-A0"),
        ("T-B", "R-B0"),
        ("T-C", "R-C0"),
    }
    assert len(source.assignments) == 3
    assert set(source.unassigned_target_ids) == set()
    assert source.version == 1
    assert source.previous_plan_id is None
    assert source.metadata["plan_published"] is True

    next_resources = (
        initial_resources[0],
        initial_resources[1],
        _resource("R-B0", "B", 990.0, status="unavailable"),
        _resource("R-C0", "C", 2_400.0),
        _resource("R-C1", "C", 1_995.0),
    )
    same_input_r0 = planner.plan(
        initial_tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=source,
        publish=False,
    )
    r0_bindings = frozenset(_assignment_pairs(same_input_r0))
    r0_signature = same_input_r0.execution_signature()
    assert r0_bindings == {
        ("T-A", "R-A0"),
        ("T-C", "R-C1"),
    }
    assert len(same_input_r0.assignments) == 2
    assert set(same_input_r0.unassigned_target_ids) == {"T-B"}
    assert same_input_r0.version == source.version + 1
    assert same_input_r0.previous_plan_id == source.plan_id
    assert same_input_r0.metadata["plan_published"] is False
    assert r0_signature != source_signature

    hint = _three_region_intervention_hint_mapping(source)
    treatment = planner.plan(
        initial_tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=source,
        regional_planning_hint=hint,
    )

    treatment_bindings = frozenset(_assignment_pairs(treatment))
    treatment_signature = treatment.execution_signature()
    assert treatment_bindings == {
        ("T-A", "R-A0"),
        ("T-B", "R-A1"),
        ("T-C", "R-C0"),
    }
    assert len(treatment.assignments) == 3
    assert set(treatment.unassigned_target_ids) == set()
    assert treatment.version == same_input_r0.version == source.version + 1
    assert treatment.plan_id != source.plan_id
    assert treatment.previous_plan_id == source.plan_id
    assert treatment.metadata["plan_published"] is True
    assert treatment_signature != source_signature
    assert treatment_signature != r0_signature
    assert treatment_bindings - source_bindings == {("T-B", "R-A1")}
    assert treatment_bindings - r0_bindings == {
        ("T-B", "R-A1"),
        ("T-C", "R-C0"),
    }
    assert {
        target_id for target_id, _ in treatment_bindings
    } - {
        target_id for target_id, _ in r0_bindings
    } == {"T-B"}
    assert treatment.metadata["execution_signature_changed"] is True
    assert treatment.metadata["regional_hint_successor_state"] == (
        "successor_published"
    )
    assert treatment.metadata["regional_hint_successor_plan_available"] is True
    assert treatment.metadata["regional_hint_successor_advisory_id"] == (
        "d4-advice-frame-0001"
    )
    assert treatment.metadata["regional_hint_successor_advisory_version"] == 1
    assert treatment.metadata["regional_hint_successor_source_plan_id"] == (
        source.plan_id
    )
    assert treatment.metadata[
        "regional_hint_successor_source_plan_version"
    ] == source.version
    assert treatment.metadata["regional_hint_successor_owner_layer"] == "center"
    assert treatment.metadata["regional_hint_successor_owner_id"] == "CENTER"
    assert treatment.metadata["regional_hint_successor_owner_epoch"] == (
        source.version
    )
    assert treatment.metadata[
        "regional_hint_successor_lease_expires_at_s"
    ] == pytest.approx(10.0)
    assert treatment.metadata["regional_hint_successor_hold_region_ids"] == (
        "C",
    )
    assert treatment.metadata[
        "regional_hint_successor_request_replan_region_ids"
    ] == ("A", "B", "C")
    assert treatment.metadata["regional_hint_hold_candidate_constraint_applied"] is True
    assert treatment.metadata["regional_hint_hold_source_assignment_edges"] == (
        ("T-C", "R-C0"),
    )
    assert treatment.metadata["regional_hint_hold_candidate_reject_count"] > 0
    assert treatment.metadata["regional_hint_actual_cross_region_resource_count"] == 1
    assert treatment.metadata["regional_hint_cross_region_limit_satisfied"] is True


def test_hold_rejects_hint_when_source_assignment_is_no_longer_hard_safe() -> None:
    planner = _planner(source_node_id="CENTER")
    tracks, resources = _three_region_intervention_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    next_resources = (
        resources[0],
        resources[1],
        _resource("R-B0", "B", 990.0, status="unavailable"),
        _resource("R-C0", "C", 1_990.0, status="unavailable"),
        _resource("R-C1", "C", 1_995.0),
    )
    rule_baseline = planner.plan(
        tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=previous,
        publish=False,
    )

    result = planner.plan(
        tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_three_region_intervention_hint_mapping(previous),
    )

    assert _assignment_pairs(result) == _assignment_pairs(rule_baseline)
    assert result.metadata["regional_hint_constraint_applied"] is False
    assert result.metadata["regional_hint_applied"] is False
    assert result.metadata["regional_hint_successor_state"] == "hint_rejected"
    assert result.metadata["regional_hint_successor_plan_available"] is False
    assert result.metadata["regional_hint_fallback_reason"] == (
        "regional_hint_held_assignment_infeasible"
    )
    assert result.metadata["regional_hint_successor_owner_id"] is None
    assert result.metadata["regional_hint_successor_lease_expires_at_s"] is None


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("owner_id", "OTHER-CENTER"),
        ("owner_epoch", 99),
        ("lease_expires_at_s", 11.0),
    ),
)
def test_inconsistent_regional_authority_rejects_whole_hint(
    field: str,
    replacement: object,
) -> None:
    planner = _planner()
    tracks, resources = _baseline_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    next_tracks = (*tracks, _track("T-B2", "B", 1_020.0))
    baseline = planner.plan(
        next_tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        publish=False,
    )
    hint = _hint_mapping(previous)
    hint["constraints"][1][field] = replacement  # type: ignore[index]

    plan = planner.plan(
        next_tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=hint,
    )

    assert _assignment_pairs(plan) == _assignment_pairs(baseline)
    assert plan.total_cost == pytest.approx(baseline.total_cost)
    assert plan.metadata["regional_hint_applied"] is False
    assert plan.metadata["regional_hint_rejected"] is True
    assert plan.metadata["regional_hint_fallback_reason"] == (
        "regional_hint_authority_scope_mismatch"
    )
    assert plan.metadata["owner_node_id"] == "d3_central"
    assert "authority_epoch" not in plan.metadata
    assert "lease_expires_at_s" not in plan.metadata


@pytest.mark.parametrize("extra_source_resources", (0, 3))
def test_zero_delta_hint_returns_explicit_no_successor_without_identity_bump(
    extra_source_resources: int,
) -> None:
    planner = _planner(source_node_id="CENTER")
    tracks, resources = _baseline_inputs(
        extra_source_resources=extra_source_resources
    )
    previous = planner.plan(tracks, resources, timestamp=0.0)
    hint = _no_transfer_hint_mapping(previous)

    plan = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=hint,
    )

    assert plan.plan_id == previous.plan_id
    assert plan.version == previous.version
    assert plan.previous_plan_id == previous.previous_plan_id
    assert plan.metadata["execution_signature_changed"] is False
    assert plan.metadata["evaluation_refresh_only"] is True
    assert plan.metadata["regional_hint_constraint_applied"] is True
    assert plan.metadata["regional_hint_applied"] is False
    assert plan.metadata["regional_hint_rejected"] is True
    assert plan.metadata["regional_hint_fallback_reason"] == (
        "regional_hint_no_executable_successor"
    )
    assert plan.metadata["regional_hint_successor_schema"] == (
        REGIONAL_PLANNING_HINT_SUCCESSOR_SCHEMA_V1
    )
    assert plan.metadata["regional_hint_successor_state"] == "no_successor"
    assert plan.metadata["regional_hint_successor_plan_available"] is False
    assert plan.metadata["regional_hint_successor_plan_id"] is None
    assert plan.metadata["regional_hint_successor_plan_version"] is None
    assert plan.metadata["regional_hint_successor_rejection_reason"] == (
        "regional_hint_no_executable_successor"
    )
    assert plan.metadata["owner_node_id"] == previous.metadata["owner_node_id"]
    assert "authority_epoch" not in plan.metadata
    assert "lease_expires_at_s" not in plan.metadata

    repeated = planner.plan(
        tracks,
        resources,
        timestamp=2.0,
        previous_plan=plan,
        regional_planning_hint=hint,
    )
    assert repeated.plan_id == previous.plan_id
    assert repeated.version == previous.version
    assert repeated.metadata["regional_hint_successor_state"] == "no_successor"
    assert repeated.metadata["regional_hint_successor_plan_available"] is False


def test_request_replan_only_noop_does_not_mechanically_advance_plan() -> None:
    planner = _planner(source_node_id="CENTER")
    tracks, resources = _baseline_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    hint = _no_transfer_hint_mapping(previous)
    hint["constraints"][0]["request_replan"] = True  # type: ignore[index]

    result = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=hint,
    )

    assert result.plan_id == previous.plan_id
    assert result.version == previous.version
    assert result.metadata["regional_hint_request_replan_requested"] is True
    assert result.metadata["regional_hint_request_replan_region_ids"] == ("A",)
    assert result.metadata["regional_hint_successor_state"] == "no_successor"
    assert result.metadata["regional_hint_successor_plan_available"] is False
    assert result.metadata["regional_hint_successor_owner_id"] is None


def test_reconnaissance_priority_is_not_an_assignment_hint_action() -> None:
    planner = _planner(source_node_id="CENTER")
    tracks, resources = _baseline_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    hint = _no_transfer_hint_mapping(previous)
    hint["constraints"][0]["reconnaissance_priority"] = 0.5001  # type: ignore[index]

    result = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=hint,
    )

    assert result.plan_id == previous.plan_id
    assert result.version == previous.version
    assert result.metadata["regional_hint_constraint_applied"] is False
    assert result.metadata["regional_hint_successor_state"] == "hint_rejected"
    assert result.metadata["regional_hint_fallback_reason"] == (
        "regional_hint_mapping_unknown_field"
    )


def test_source_cross_region_commit_does_not_consume_incremental_allowance() -> None:
    planner, tracks, resources, previous, _ = _cross_region_source_plan()

    result = planner.plan(
        tracks,
        resources,
        timestamp=2.0,
        previous_plan=previous,
        regional_planning_hint=_hint_after_source_plan(previous),
    )

    assert result.plan_id != previous.plan_id
    assert result.version == previous.version + 1
    assert _assignment_pairs(result) == _assignment_pairs(previous)
    assert result.metadata["regional_hint_constraint_applied"] is True
    assert result.metadata["regional_hint_successor_state"] == "successor_published"
    assert result.metadata["regional_hint_successor_plan_available"] is True
    assert "authority_epoch" not in result.metadata
    assert "lease_expires_at_s" not in result.metadata
    assert result.metadata["regional_max_epoch"] == previous.version
    assert result.metadata["regional_min_lease_expires_at_s"] == pytest.approx(
        10.0
    )
    assert result.metadata[
        "regional_hint_transfer_allowance_semantics"
    ] == "incremental_beyond_source_plan_v1"
    assert result.metadata[
        "regional_hint_source_cross_region_commitment_count"
    ] == 1
    assert result.metadata[
        "regional_hint_retained_cross_region_commitment_count"
    ] == 1
    assert result.metadata[
        "regional_hint_incremental_cross_region_resource_count"
    ] == 0
    assert result.metadata["regional_hint_transfer_usage"] == (
        {
            "source_region_id": "A",
            "target_region_id": "B",
            "allowed_resource_count": 1,
            "actual_resource_count": 1,
            "incremental_allowed_resource_count": 0,
            "incremental_actual_resource_count": 0,
            "baseline_committed_resource_count": 1,
            "retained_baseline_resource_count": 1,
            "total_actual_resource_count": 1,
        },
    )
    assert result.metadata["regional_hint_cross_region_limit_satisfied"] is True


def test_incremental_allowance_is_additive_to_exact_source_cross_region_edge() -> None:
    planner, tracks, resources, previous, source_resource_id = (
        _cross_region_source_plan()
    )
    next_tracks = (*tracks, _track("T-B2", "B", 1_020.0))
    incremental_resource_id = (
        "R-A1" if source_resource_id == "R-A2" else "R-A2"
    )

    result = planner.plan(
        next_tracks,
        resources,
        timestamp=2.0,
        previous_plan=previous,
        regional_planning_hint=_hint_after_source_plan(
            previous,
            transfer_count=1,
        ),
    )

    assert ("T-A", "R-A0") in _assignment_pairs(result)
    assert ("T-B", source_resource_id) in _assignment_pairs(result)
    assert ("T-B2", incremental_resource_id) in _assignment_pairs(result)
    assert result.version == previous.version + 1
    assert result.metadata["regional_hint_successor_state"] == (
        "successor_published"
    )
    assert result.metadata[
        "regional_hint_source_cross_region_commitment_count"
    ] == 1
    assert result.metadata[
        "regional_hint_retained_cross_region_commitment_count"
    ] == 1
    assert result.metadata[
        "regional_hint_incremental_cross_region_resource_count"
    ] == 1
    assert result.metadata["regional_hint_actual_cross_region_resource_count"] == 2
    assert result.metadata["regional_hint_transfer_usage"] == (
        {
            "source_region_id": "A",
            "target_region_id": "B",
            "allowed_resource_count": 2,
            "actual_resource_count": 2,
            "incremental_allowed_resource_count": 1,
            "incremental_actual_resource_count": 1,
            "baseline_committed_resource_count": 1,
            "retained_baseline_resource_count": 1,
            "total_actual_resource_count": 2,
        },
    )
    assert result.metadata["regional_hint_cross_region_limit_satisfied"] is True


def test_source_cross_region_commit_does_not_open_an_unallowed_new_edge() -> None:
    planner, tracks, resources, previous, source_resource_id = (
        _cross_region_source_plan()
    )
    next_tracks = (*tracks, _track("T-B2", "B", 1_020.0))

    result = planner.plan(
        next_tracks,
        resources,
        timestamp=2.0,
        previous_plan=previous,
        regional_planning_hint=_hint_after_source_plan(previous),
    )

    assert ("T-B", source_resource_id) in _assignment_pairs(result)
    assert not any(
        target_id == "T-B2" and resource_id.startswith("R-A")
        for target_id, resource_id in _assignment_pairs(result)
    )
    assert "T-B2" in result.unassigned_target_ids
    assert result.metadata[
        "regional_hint_incremental_cross_region_resource_count"
    ] == 0
    assert result.metadata["regional_hint_cross_region_limit_satisfied"] is True


def test_source_cross_region_edge_must_remain_hard_safe() -> None:
    planner, tracks, resources, previous, source_resource_id = (
        _cross_region_source_plan()
    )
    unsafe_tracks = (
        tracks[0],
        _track(
            "T-B",
            "B",
            1_000.0,
            blocked_resource_ids=(source_resource_id,),
        ),
    )

    result = planner.plan(
        unsafe_tracks,
        resources,
        timestamp=2.0,
        previous_plan=previous,
        regional_planning_hint=_hint_after_source_plan(previous),
    )

    assert ("T-B", source_resource_id) not in _assignment_pairs(result)
    assert result.metadata["regional_hint_constraint_applied"] is False
    assert result.metadata["regional_hint_successor_state"] == "hint_rejected"
    assert result.metadata["regional_hint_fallback_reason"] == (
        "regional_hint_protected_transfer_edge_infeasible"
    )


def test_hold_without_source_commitment_can_form_attributable_successor() -> None:
    planner = _planner(source_node_id="CENTER")
    source_tracks = (
        _track("T-A", "A", 100.0),
        _track("T-B", "B", 1_000.0),
    )
    resources = (
        _resource("R-A0", "A", 90.0),
        _resource("R-A1", "A", 880.0),
        _resource("R-B0", "B", 990.0),
        _resource("R-C0", "C", 1_990.0),
    )
    previous = planner.plan(source_tracks, resources, timestamp=0.0)
    next_tracks = (*source_tracks, _track("T-C", "C", 2_000.0))
    rule_baseline = planner.plan(
        next_tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        publish=False,
    )
    assert ("T-C", "R-C0") in _assignment_pairs(rule_baseline)

    successor = planner.plan(
        next_tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_uncommitted_region_hold_hint_mapping(previous),
    )

    assert ("T-C", "R-C0") not in _assignment_pairs(successor)
    assert "T-C" in successor.unassigned_target_ids
    assert successor.plan_id != previous.plan_id
    assert successor.version == previous.version + 1
    assert successor.previous_plan_id == previous.plan_id
    assert successor.metadata["regional_hint_successor_state"] == (
        "successor_published"
    )
    assert successor.metadata["regional_hint_successor_plan_available"] is True
    assert successor.metadata["regional_hint_successor_hold_region_ids"] == (
        "C",
    )
    assert successor.metadata[
        "regional_hint_successor_request_replan_region_ids"
    ] == ("C",)
    assert successor.metadata["regional_hint_hold_source_assignment_edges"] == ()
    assert successor.metadata["regional_hint_hold_candidate_reject_count"] > 0


def test_no_hint_refresh_does_not_gain_authority_binding() -> None:
    planner = _planner()
    tracks, resources = _baseline_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)

    plan = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
    )

    assert plan.plan_id == previous.plan_id
    assert plan.version == previous.version
    assert plan.metadata["execution_signature_changed"] is False
    assert plan.metadata["evaluation_refresh_only"] is True
    assert plan.metadata["regional_hint_applied"] is False
    assert plan.metadata["owner_node_id"] == "d3_central"
    assert "authority_epoch" not in plan.metadata
    assert "lease_expires_at_s" not in plan.metadata


def test_no_hint_refresh_preserves_live_successor_authority_signature() -> None:
    planner = _planner(source_node_id="CENTER")
    tracks, base_resources = _baseline_inputs()
    resources = (*base_resources, _resource("R-B1", "B", 1_015.0))
    previous = planner.plan(tracks, resources, timestamp=0.0)
    next_tracks = (*tracks, _track("T-B2", "B", 1_020.0))
    successor = planner.plan(
        next_tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_hint_mapping(previous),
    )
    successor = _bind_published_regional_successor(planner, successor)
    authority_keys = (
        "plan_owner",
        "active_plan_owner",
        "owner_node_id",
        "current_plan_owner",
        "current_plan_owner_node_id",
        "authority_epoch",
        "lease_expires_at_s",
    )
    successor_keys = tuple(
        key
        for key in successor.metadata
        if key.startswith("regional_hint_successor_")
    )
    assignment_authority_keys = (
        "plan_owner",
        "active_plan_owner",
        "owner_node_id",
        "regional_owner_layer",
        "regional_region_id",
        "regional_epoch",
        "regional_lease_expires_at_s",
        "regional_commit_state",
        "regional_commit_mode",
        "activation_state",
        "executable",
    )

    refreshed = planner.plan(
        next_tracks,
        resources,
        timestamp=2.0,
        previous_plan=successor,
    )

    assert (refreshed.plan_id, refreshed.version) == (
        successor.plan_id,
        successor.version,
    )
    assert refreshed.execution_signature() == successor.execution_signature()
    assert refreshed.metadata["execution_signature_changed"] is False
    assert refreshed.metadata["evaluation_refresh_only"] is True
    assert refreshed.metadata["regional_hint_available"] is False
    assert refreshed.metadata["regional_hint_successor_binding_inherited"] is True
    for key in authority_keys:
        assert refreshed.metadata[key] == successor.metadata[key]
    for key in successor_keys:
        assert refreshed.metadata[key] == successor.metadata[key]
    previous_assignments = {
        (item.target_id, item.resource_id): item for item in successor.assignments
    }
    for assignment in refreshed.assignments:
        previous_assignment = previous_assignments[
            (assignment.target_id, assignment.resource_id)
        ]
        for key in assignment_authority_keys:
            assert assignment.metadata.get(key) == previous_assignment.metadata.get(key)


def test_no_hint_refresh_fails_closed_at_successor_lease_expiry() -> None:
    planner = _planner(source_node_id="CENTER")
    tracks, resources = _three_region_intervention_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    successor = planner.plan(
        (*tracks, _track("T-C2", "C", 2_020.0)),
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_three_region_intervention_hint_mapping(previous),
    )
    successor = _bind_published_regional_successor(planner, successor)

    with pytest.raises(StalePlanError) as error:
        planner.plan(
            (*tracks, _track("T-C2", "C", 2_020.0)),
            resources,
            timestamp=10.0,
            previous_plan=successor,
        )

    assert error.value.reason == "regional_hint_successor_lease_expired"


def test_no_hint_refresh_rejects_epoch_tamper_and_inactive_owner() -> None:
    planner = _planner(source_node_id="CENTER")
    tracks, resources = _baseline_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    successor = planner.plan(
        (*tracks, _track("T-B2", "B", 1_020.0)),
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_hint_mapping(previous),
    )
    successor = _bind_published_regional_successor(planner, successor)
    epoch_tampered = replace(
        successor,
        metadata={
            **dict(successor.metadata),
            "authority_epoch": successor.metadata["authority_epoch"] + 1,
        },
    )
    with pytest.raises(StalePlanError) as error:
        planner.plan(
            (*tracks, _track("T-B2", "B", 1_020.0)),
            resources,
            timestamp=2.0,
            previous_plan=epoch_tampered,
        )
    assert error.value.reason == "stale_previous_plan_semantics"

    inactive = replace(
        successor,
        metadata={**dict(successor.metadata), "owner_active": False},
    )
    with pytest.raises(StalePlanError) as error:
        planner.plan(
            (*tracks, _track("T-B2", "B", 1_020.0)),
            resources,
            timestamp=2.0,
            previous_plan=inactive,
        )
    assert error.value.reason == "regional_hint_successor_owner_inactive"


def test_generation_fence_blocks_no_hint_successor_refresh() -> None:
    planner = _planner(source_node_id="CENTER")
    tracks, resources = _baseline_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    next_tracks = (*tracks, _track("T-B2", "B", 1_020.0))
    successor = planner.plan(
        next_tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_hint_mapping(previous),
    )
    successor = _bind_published_regional_successor(planner, successor)
    fenced = planner.advance_authority_generation(
        successor,
        timestamp=2.0,
        expected_previous_version=successor.version,
        fence_reason="fault_generation_changed",
    )
    assert "authority_epoch" not in fenced.metadata
    assert "lease_expires_at_s" not in fenced.metadata
    assert "regional_max_epoch" not in fenced.metadata
    assert "regional_min_lease_expires_at_s" not in fenced.metadata
    fenced = planner.bind_published_authority_generation(
        fenced,
        authority_epoch=fenced.version,
        lease_expires_at_s=9.0,
    )

    with pytest.raises(StalePlanError) as error:
        planner.plan(
            next_tracks,
            resources,
            timestamp=3.0,
            previous_plan=fenced,
        )

    assert error.value.reason == "regional_hint_successor_generation_fenced"


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("source_plan", "regional_hint_source_plan_mismatch"),
        ("expired", "regional_hint_expired"),
        ("region_set", "regional_hint_region_set_mismatch"),
        ("conservation", "regional_hint_resource_conservation_violation"),
        ("transfer_quota", "regional_hint_transfer_quota_mismatch"),
        ("not_projected", "regional_hint_not_projected"),
        ("region_lease", "regional_hint_region_lease_expired"),
        ("forbidden_identity", "regional_hint_forbidden_identity_field"),
    ),
)
def test_invalid_or_stale_hint_records_reason_and_uses_exact_rule_fallback(
    mutation: str,
    expected_reason: str,
) -> None:
    planner = _planner()
    tracks, resources = _baseline_inputs()
    previous = planner.plan(tracks, resources, timestamp=0.0)
    next_resources = (
        resources[0],
        resources[1],
        _resource("R-B0", "B", 990.0, status="unavailable"),
    )
    baseline = planner.plan(
        tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=previous,
        publish=False,
    )
    raw = _hint_mapping(previous)

    if mutation == "source_plan":
        raw["source_plan_id"] = "stale-plan"
        for constraint in raw["constraints"]:  # type: ignore[union-attr]
            constraint["source_plan_id"] = "stale-plan"
    elif mutation == "expired":
        raw["expires_at_s"] = 0.75
    elif mutation == "region_set":
        raw["constraints"] = raw["constraints"][:1]  # type: ignore[index]
    elif mutation == "conservation":
        raw["constraints"][1]["resource_quota_delta"] = 0  # type: ignore[index]
    elif mutation == "transfer_quota":
        raw["constraints"][0]["resource_quota_delta"] = 0  # type: ignore[index]
        raw["constraints"][1]["resource_quota_delta"] = 0  # type: ignore[index]
    elif mutation == "not_projected":
        raw["projected"] = False
    elif mutation == "region_lease":
        raw["constraints"][1]["lease_expires_at_s"] = 0.75  # type: ignore[index]
    elif mutation == "forbidden_identity":
        raw["truth_id"] = "offline-truth"

    plan = planner.plan(
        tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=raw,
    )

    assert _assignment_pairs(plan) == _assignment_pairs(baseline)
    assert plan.total_cost == pytest.approx(baseline.total_cost)
    assert plan.solver_name == baseline.solver_name
    assert plan.metadata["regional_hint_available"] is True
    assert plan.metadata["regional_hint_considered"] is True
    assert plan.metadata["regional_hint_applied"] is False
    assert plan.metadata["regional_hint_rejected"] is True
    assert plan.metadata["regional_hint_fallback_reason"] == expected_reason
    assert plan.metadata["regional_hint_rejection_reasons"] == (expected_reason,)


def test_reserve_and_previous_commit_protection_rejects_unsafe_transfer_count() -> None:
    planner = _planner()
    tracks, resources = _baseline_inputs(extra_source_resources=2)
    previous = planner.plan(tracks, resources, timestamp=0.0)
    raw = _hint_mapping(
        previous,
        transfer_count=2,
        source_reserve_ratio=0.5,
    )

    plan = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=raw,
    )

    assert plan.metadata["regional_hint_applied"] is False
    assert plan.metadata["regional_hint_rejected"] is True
    assert plan.metadata["regional_hint_fallback_reason"] == (
        "regional_hint_protected_or_reserve_quota_violation"
    )
    assert ("T-A", "R-A0") in _assignment_pairs(plan)


def test_m_to_n_slots_share_the_same_transfer_pool_and_respect_its_count() -> None:
    planner = _planner()
    initial_tracks, resources = _baseline_inputs(extra_source_resources=2)
    previous = planner.plan(initial_tracks, resources, timestamp=0.0)
    next_tracks = (
        initial_tracks[0],
        _track(
            "T-B",
            "B",
            1_000.0,
            demand=TargetDemand(
                required_resource_count=2,
                primary_resource_count=2,
                coordination_mode="simultaneous",
            ),
        ),
    )
    next_resources = (
        resources[0],
        resources[1],
        resources[2],
        _resource("R-B0", "B", 990.0, status="unavailable"),
    )

    plan = planner.plan(
        next_tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_hint_mapping(previous, transfer_count=2),
    )

    assigned_to_b = {
        item.resource_id for item in plan.assignments if item.target_id == "T-B"
    }
    assert assigned_to_b == {"R-A1", "R-A2"}
    assert plan.solver_name == "hungarian_demand_slots"
    assert plan.coalitions[1].complete is True
    assert plan.metadata["regional_hint_actual_cross_region_resource_count"] == 2
    assert plan.metadata["regional_hint_transfer_usage"][0][
        "actual_resource_count"
    ] == 2
    assert plan.metadata["regional_hint_cross_region_limit_satisfied"] is True


def test_hint_does_not_override_d5_hard_edge_and_learning_still_runs() -> None:
    planner = _planner(learning=True)
    initial_tracks, resources = _baseline_inputs(extra_source_resources=2)
    previous = planner.plan(initial_tracks, resources, timestamp=0.0)
    next_tracks = (
        initial_tracks[0],
        _track(
            "T-B",
            "B",
            1_000.0,
            blocked_resource_ids=("R-A1",),
        ),
    )
    next_resources = (
        resources[0],
        resources[1],
        resources[2],
        _resource("R-B0", "B", 990.0, status="unavailable"),
    )

    plan = planner.plan(
        next_tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=previous,
        regional_planning_hint=_hint_mapping(
            previous,
            transfer_count=1,
            source_reserve_ratio=0.5,
        ),
    )

    assert ("T-B", "R-A2") in _assignment_pairs(plan)
    assert ("T-B", "R-A1") not in _assignment_pairs(plan)
    assert plan.metadata["regional_hint_applied"] is True
    assert plan.metadata["learning_applied"] is True
    assert "pair_infeasible" in plan.metadata["hard_reject_reasons"]
    assert plan.metadata["regional_hint_actual_cross_region_resource_count"] == 1
