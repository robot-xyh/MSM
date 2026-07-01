from d3_assignment_planner import CostModel, CostWeights, PlannerConfig
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
    track = TargetTrack(
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
    track = TargetTrack("T1", threat_score=0.9, covariance=0.1, window_cost=0.1)
    resource = ResourceState("R1", status="unavailable")

    result = model.build_matrix([track], [resource], timestamp=0.0)

    assert result.matrix[0, 0] == config.infeasible_penalty
    assert result.unassigned_costs[0] < config.infeasible_penalty
