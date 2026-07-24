from commitment_test_support import committed_target_track

from d3_assignment_planner import (
    CostModel,
    CostWeights,
    PlannerConfig,
    compose_threat_score_baseline,
)
from d3_assignment_planner.models import ResourceState, TargetTrack


def test_cost_model_builds_weighted_breakdown() -> None:
    model = CostModel(
        weights=CostWeights(
            window=1.0,
            covariance=2.0,
            threat=3.0,
            resource_state=4.0,
            fov=5.0,
            conflict=6.0,
        ),
        config=PlannerConfig(),
    )
    track = committed_target_track(
        track_id="T1",
        threat_score=0.8,
        covariance=0.25,
        window_cost=0.1,
        fov_difficulty_by_resource={"R1": 0.3},
        conflict_risk_by_resource={"R1": 0.2},
    )
    resource = ResourceState(
        resource_id="R1",
        status="degraded",
        health_score=0.75,
        load_penalty=0.05,
    )

    result = model.build_matrix([track], [resource], timestamp=0.0)
    breakdown = result.breakdowns[0][0]

    assert result.matrix.shape == (1, 1)
    assert breakdown["window"] == 0.1
    assert breakdown["covariance"] == 0.5
    assert round(breakdown["threat"], 6) == 0.6
    assert round(breakdown["resource_state"], 6) == 2.6
    assert breakdown["fov"] == 1.5
    assert round(breakdown["conflict"], 6) == 1.2
    assert round(result.matrix[0, 0], 6) == round(breakdown["total"], 6)


def test_cost_model_marks_unavailable_resource_infeasible() -> None:
    config = PlannerConfig(infeasible_penalty=12345.0)
    model = CostModel(config=config)
    track = committed_target_track("T1", threat_score=0.9, covariance=0.1, window_cost=0.1)
    resource = ResourceState("R1", status="unavailable")

    result = model.build_matrix([track], [resource], timestamp=0.0)

    assert result.matrix[0, 0] == config.infeasible_penalty
    assert result.unassigned_costs[0] < config.infeasible_penalty


def test_cost_model_consumes_detailed_resource_state_fields() -> None:
    model = CostModel(
        weights=CostWeights(
            window=0.0,
            covariance=0.0,
            threat=0.0,
            resource_state=1.0,
            fov=0.0,
            conflict=0.0,
        ),
        config=PlannerConfig(),
    )
    track = committed_target_track("T1", threat_score=0.9, covariance=0.1, window_cost=0.1)
    resource = ResourceState(
        "R1",
        health_score=0.95,
        load_penalty=0.05,
        energy_fraction=0.8,
        availability_score=0.9,
        current_load=0.2,
        history_failure_rate=0.1,
    )

    result = model.build_matrix([track], [resource], timestamp=0.0)
    breakdown = result.breakdowns[0][0]

    assert round(breakdown["resource_health"], 6) == 0.05
    assert round(breakdown["resource_load_penalty"], 6) == 0.05
    assert round(breakdown["resource_energy"], 6) == 0.2
    assert round(breakdown["resource_availability"], 6) == 0.1
    assert round(breakdown["resource_current_load"], 6) == 0.2
    assert round(breakdown["resource_history_failure"], 6) == 0.1
    assert round(breakdown["resource_state"], 6) == 0.7
    assert round(result.matrix[0, 0], 6) == 0.7


def test_cost_model_marks_resource_intercept_infeasible_by_target() -> None:
    config = PlannerConfig(infeasible_penalty=12345.0)
    model = CostModel(config=config)
    track = committed_target_track("T1", threat_score=0.9, covariance=0.1, window_cost=0.1)
    resource = ResourceState(
        "R1",
        intercept_feasibility_by_target={"T1": False},
    )

    result = model.build_matrix([track], [resource], timestamp=0.0)
    breakdown = result.breakdowns[0][0]

    assert result.matrix[0, 0] == config.infeasible_penalty
    assert breakdown["reason_intercept_feasibility"] == 1.0
    assert breakdown["intercept_feasibility"] == 1.0


def test_cost_model_hard_rejects_closed_time_window_edge() -> None:
    config = PlannerConfig(infeasible_penalty=12345.0)
    model = CostModel(config=config)
    track = committed_target_track(
        "T1",
        threat_score=0.9,
        covariance=0.1,
        window_cost=0.0,
        hard_time_window=True,
        time_window_close_at_s=5.0,
    )
    resource = ResourceState("R1")

    result = model.build_matrix([track], [resource], timestamp=6.0)
    breakdown = result.breakdowns[0][0]

    assert result.matrix[0, 0] == config.infeasible_penalty
    assert result.reject_reasons == (("time_window_expired",),)
    assert breakdown["hard_time_window_reject"] == 1.0
    assert breakdown["reason_time_window_closed"] == 1.0


def test_explainable_threat_score_baseline_uses_scene_terms() -> None:
    baseline = compose_threat_score_baseline(
        target_state="engageable",
        position_ned=(100.0, 0.0, 0.0),
        velocity_ned=(-20.0, 0.0, 0.0),
        critical_zone_center_ned=(0.0, 0.0, 0.0),
        critical_zone_radius_m=20.0,
        covariance=0.2,
    )

    assert baseline.threat_score > 0.75
    assert baseline.components["critical_zone_proximity"] == 0.84
    assert baseline.components["time_to_critical_zone"] == 1.0
    assert baseline.components["speed"] == 0.5
    assert "critical_zone_proximity" in baseline.reasons
    assert "short_time_to_critical_zone" in baseline.reasons
    assert baseline.metadata["baseline"] == "d3_explainable_threat_score_v1"
