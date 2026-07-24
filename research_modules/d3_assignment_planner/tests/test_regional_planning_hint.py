from __future__ import annotations
from commitment_test_support import committed_target_track

from copy import deepcopy
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from d3_assignment_planner import (
    REGIONAL_PLANNING_HINT_SCHEMA_V1,
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
    TargetDemand,
    TargetTrack,
)


class _ZeroResidualPredictor:
    def predict(self, features: np.ndarray) -> ResidualPrediction:
        return ResidualPrediction(
            delta_costs=np.zeros(features.shape[0], dtype=float),
            confidence=0.99,
        )


def _planner(*, learning: bool = False) -> AssignmentPlanner:
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


def _assignment_pairs(plan) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((item.target_id, item.resource_id) for item in plan.assignments))


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
        },
    )


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
