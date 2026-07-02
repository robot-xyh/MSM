import pytest

from d3_assignment_planner import (
    AirSimDryRunAssignmentAdapter,
    AssignmentPlanner,
    CostModel,
    CostWeights,
    PlannerConfig,
    StalePlanError,
)
from d3_assignment_planner.solver import HungarianAssignmentSolver


def _adapter(config: PlannerConfig) -> AirSimDryRunAssignmentAdapter:
    weights = CostWeights(
        window=0.0,
        covariance=0.0,
        threat=0.0,
        resource_state=0.0,
        fov=1.0,
        conflict=0.0,
    )
    planner = AssignmentPlanner(
        cost_model=CostModel(weights=weights, config=config),
        solver=HungarianAssignmentSolver(allow_scipy=False),
        config=config,
    )
    return AirSimDryRunAssignmentAdapter(planner=planner)


def _resources() -> list[dict[str, object]]:
    return [
        {"resource_id": "R1", "status": "available", "health_score": 1.0},
        {"resource_id": "R2", "status": "available", "health_score": 1.0},
    ]


def _initial_tracks() -> list[dict[str, object]]:
    return [
        {
            "global_track_id": "T1",
            "track_state": "engageable",
            "threat_score": 0.9,
            "covariance": 0.1,
            "window_cost": 0.1,
            "pair_terms": {
                "R1": {"fov": 0.0, "conflict": 0.1, "feasible": True},
                "R2": {"fov": 1.0, "conflict": 0.1, "feasible": True},
            },
        },
        {
            "global_track_id": "T2",
            "track_state": "confirmed",
            "threat_score": 0.8,
            "covariance": [[0.05, 0.0], [0.0, 0.05]],
            "window_cost": 0.1,
            "pair_terms": {
                "R1": {"fov": 1.0, "conflict": 0.1, "feasible": True},
                "R2": {"fov": 0.0, "conflict": 0.1, "feasible": True},
            },
        },
    ]


def _shifted_tracks() -> list[dict[str, object]]:
    return [
        {
            "global_track_id": "T1",
            "track_state": "engageable",
            "threat_score": 0.9,
            "covariance": 0.1,
            "window_cost": 0.1,
            "pair_terms": {
                "R1": {"fov": 0.8, "feasible": True},
                "R2": {"fov": 0.0, "feasible": True},
            },
        },
        {
            "global_track_id": "T2",
            "track_state": "confirmed",
            "threat_score": 0.8,
            "covariance": 0.1,
            "window_cost": 0.1,
            "pair_terms": {
                "R1": {"fov": 0.0, "feasible": True},
                "R2": {"fov": 0.8, "feasible": True},
            },
        },
    ]


def test_dry_run_adapter_emits_versioned_assignment_plan() -> None:
    adapter = _adapter(PlannerConfig(enable_hysteresis=False))

    plan = adapter.plan(_initial_tracks(), _resources(), timestamp=10.0, window_id=5)

    assert plan.assignment_map() == {"T1": "R1", "T2": "R2"}
    assert plan.version == 1
    assert plan.window_id == 5
    assert plan.decision_state == "accepted"
    assert plan.human_authorization_state == "required"
    assert plan.assignments[0].cost_breakdown["fov"] == 0.0


def test_dry_run_adapter_preserves_hysteresis_fields() -> None:
    adapter = _adapter(PlannerConfig(delta=0.2, min_dwell=2.0))

    first = adapter.plan(_initial_tracks(), _resources(), timestamp=0.0)
    second = adapter.plan(
        _shifted_tracks(),
        _resources(),
        timestamp=1.0,
        previous_plan=first,
        expected_previous_version=first.version,
    )

    assert second.version == 2
    assert second.assignment_map() == first.assignment_map()
    assert second.decision_state == "held_by_hysteresis"
    assert second.changed is False
    assert second.candidate_total_cost == 0.0
    assert second.previous_total_cost_current == 1.6


def test_dry_run_adapter_keeps_stale_version_checks_intact() -> None:
    adapter = _adapter(PlannerConfig(enable_hysteresis=False))

    first = adapter.plan(_initial_tracks(), _resources(), timestamp=0.0)
    second = adapter.plan(_initial_tracks(), _resources(), timestamp=1.0, previous_plan=first)

    assert second.version == 2
    with pytest.raises(StalePlanError):
        adapter.plan(
            _initial_tracks(),
            _resources(),
            timestamp=2.0,
            previous_plan=first,
            expected_previous_version=first.version,
        )
