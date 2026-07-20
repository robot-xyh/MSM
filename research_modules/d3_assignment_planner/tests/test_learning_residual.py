from __future__ import annotations

from dataclasses import replace
from time import sleep

import numpy as np
import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    BehaviorCloningBatch,
    CostModel,
    FeatureDistributionGuard,
    LearningAssistConfig,
    LearningCostAssistant,
    PlannerConfig,
    ResidualPrediction,
    ResourceState,
    SharedCandidateEdgeResidualPolicy,
    StalePlanError,
    TargetTrack,
    behavior_clone_warmup,
    build_learning_action_mask,
)


class _FixedPredictor:
    def __init__(
        self,
        delta: float | np.ndarray,
        *,
        confidence: float = 0.99,
        delay_s: float = 0.0,
    ) -> None:
        self.delta = delta
        self.confidence = confidence
        self.delay_s = delay_s

    def predict(self, features: np.ndarray) -> ResidualPrediction:
        if self.delay_s:
            sleep(self.delay_s)
        delta = np.asarray(self.delta, dtype=float)
        if delta.ndim == 0:
            delta = np.full(features.shape[0], float(delta))
        return ResidualPrediction(delta_costs=delta, confidence=self.confidence)


def _inputs() -> tuple[list[TargetTrack], list[ResourceState]]:
    tracks = [
        TargetTrack(
            "T",
            threat_score=0.9,
            covariance=0.1,
            window_cost=0.0,
            position_ned=(100.0, 0.0, -100.0),
            velocity_ned=(0.0, 0.0, 0.0),
            region_id="A",
        )
    ]
    resources = [
        ResourceState(
            "R1",
            position_ned=(0.0, 0.0, -100.0),
            max_speed_mps=20.0,
            region_id="A",
            fov_difficulty=0.1,
        ),
        ResourceState(
            "R2",
            position_ned=(10.0, 0.0, -100.0),
            max_speed_mps=20.0,
            region_id="A",
            fov_difficulty=0.2,
        ),
    ]
    return tracks, resources


def _rule_matrix() -> tuple[PlannerConfig, CostModel, object, list[TargetTrack], list[ResourceState]]:
    config = PlannerConfig.scalable_3d(
        enable_hysteresis=False,
        max_candidate_edges_per_target=2,
    )
    model = CostModel(config=config)
    tracks, resources = _inputs()
    result = model.build_matrix(tracks, resources, timestamp=0.0)
    return config, model, result, tracks, resources


def test_assist_mode_uses_the_exact_bounded_residual_formula() -> None:
    _, _, rule, tracks, resources = _rule_matrix()
    delta = np.asarray([2.0, -2.0])
    assistant = LearningCostAssistant(
        _FixedPredictor(delta),
        config=LearningAssistConfig(
            mode="assist",
            alpha=0.4,
            min_confidence=0.5,
        ),
    )

    final = assistant.apply(
        rule,
        tracks,
        resources,
        expected_previous_version=0,
        current_plan_version=0,
    )

    expected = rule.matrix[0] + 0.4 * np.tanh(delta)
    assert np.allclose(final.matrix[0], expected)
    assert final.metadata["learning_formula"] == "C_final=C_rule+alpha*tanh(delta_C)"
    assert final.metadata["learning_applied"] is True
    assert final.metadata["learning_dense_action_count"] == 0
    assert final.metadata["learning_candidate_action_count"] == 2


def test_action_mask_covers_reachability_capacity_friend_conflict_and_version() -> None:
    config = PlannerConfig.scalable_3d(
        enable_hysteresis=False,
        max_candidate_edges_per_target=4,
        max_intercept_time_s=10.0,
    )
    track = TargetTrack(
        "T",
        threat_score=0.9,
        covariance=0.1,
        window_cost=0.0,
        position_ned=(1_000.0, 0.0, -100.0),
        velocity_ned=(100.0, 0.0, 0.0),
        region_id="A",
        friendly_conflict_by_resource={"FRIEND": True},
    )
    resources = [
        ResourceState(
            "GOOD",
            position_ned=(990.0, 0.0, -100.0),
            max_speed_mps=200.0,
            region_id="A",
        ),
        ResourceState(
            "CAPACITY",
            position_ned=(990.0, 0.0, -100.0),
            max_speed_mps=200.0,
            region_id="A",
            assignment_capacity=0,
        ),
        ResourceState(
            "FRIEND",
            position_ned=(990.0, 0.0, -100.0),
            max_speed_mps=200.0,
            region_id="A",
        ),
        ResourceState(
            "UNREACHABLE",
            position_ned=(0.0, 0.0, -100.0),
            max_speed_mps=1.0,
            region_id="A",
        ),
    ]
    result = CostModel(config=config).build_matrix([track], resources, timestamp=0.0)
    current = build_learning_action_mask(
        result,
        expected_previous_version=2,
        current_plan_version=2,
    )
    stale = build_learning_action_mask(
        result,
        expected_previous_version=1,
        current_plan_version=2,
    )

    assert current.mask.tolist() == [[True, False, False, False]]
    assert dict(current.reason_counts)["resource_capacity_exhausted"] == 1
    assert dict(current.reason_counts)["friendly_conflict"] == 1
    assert dict(current.reason_counts)["intercept_unreachable_3d"] == 1
    assert stale.action_count == 0
    assert dict(stale.reason_counts)["version_constraint"] == 1


@pytest.mark.parametrize(
    ("predictor", "assist_config", "expected_reason"),
    [
        (
            _FixedPredictor(1.0, confidence=0.2),
            LearningAssistConfig(mode="assist", min_confidence=0.8),
            "low_confidence",
        ),
        (
            _FixedPredictor(1.0, delay_s=0.01),
            LearningAssistConfig(mode="assist", timeout_s=0.001, min_confidence=0.0),
            "model_timeout",
        ),
    ],
)
def test_low_confidence_and_timeout_fall_back_to_the_exact_rule_matrix(
    predictor: _FixedPredictor,
    assist_config: LearningAssistConfig,
    expected_reason: str,
) -> None:
    _, _, rule, tracks, resources = _rule_matrix()
    final = LearningCostAssistant(predictor, config=assist_config).apply(
        rule,
        tracks,
        resources,
        expected_previous_version=0,
        current_plan_version=0,
    )

    assert np.array_equal(final.matrix, rule.matrix)
    assert final.metadata["learning_applied"] is False
    assert final.metadata["learning_fallback_reason"] == expected_reason


def test_out_of_distribution_features_fall_back_before_model_inference() -> None:
    _, _, rule, tracks, resources = _rule_matrix()
    guard = FeatureDistributionGuard.fit(np.zeros((4, 12), dtype=np.float32))
    final = LearningCostAssistant(
        _FixedPredictor(1.0),
        config=LearningAssistConfig(mode="assist", ood_z_threshold=2.0),
        distribution_guard=guard,
    ).apply(
        rule,
        tracks,
        resources,
        expected_previous_version=0,
        current_plan_version=0,
    )

    assert np.array_equal(final.matrix, rule.matrix)
    assert final.metadata["learning_fallback_reason"] == "out_of_distribution"


def test_shadow_mode_reports_candidate_residuals_without_changing_rule_costs() -> None:
    _, _, rule, tracks, resources = _rule_matrix()
    shadow = LearningCostAssistant(
        _FixedPredictor(-1.0),
        config=LearningAssistConfig(mode="shadow", min_confidence=0.0),
    ).apply(
        rule,
        tracks,
        resources,
        expected_previous_version=0,
        current_plan_version=0,
    )

    assert np.array_equal(shadow.matrix, rule.matrix)
    assert shadow.metadata["learning_applied"] is False
    assert shadow.metadata["learning_shadow_only"] is True
    assert len(shadow.metadata["learning_shadow_proposed_costs"]) == 2


def test_shared_pytorch_edge_policy_supports_behavior_cloning_warmup() -> None:
    torch = pytest.importorskip("torch")
    torch.manual_seed(7)
    rng = np.random.default_rng(7)
    features = rng.uniform(0.0, 1.0, size=(32, 12)).astype(np.float32)
    selected = (features[:, 0] + features[:, 1] > 1.0).astype(np.float32)
    teacher_delta = np.where(selected > 0.0, -0.5, 0.5).astype(np.float32)
    policy = SharedCandidateEdgeResidualPolicy(hidden_size=16)

    outcome = behavior_clone_warmup(
        policy,
        [
            BehaviorCloningBatch(
                features=features,
                selected_edges=selected,
                teacher_delta_costs=teacher_delta,
            )
        ],
        epochs=20,
        learning_rate=0.02,
    )
    prediction = policy.predict(features[:5])

    assert outcome.edge_sample_count == 32
    assert outcome.final_loss < outcome.initial_loss
    assert np.asarray(prediction.delta_costs).shape == (5,)
    assert np.asarray(prediction.confidence).shape == (5,)


def test_planner_versions_learning_fallback_output_and_rejects_stale_previous_plan() -> None:
    config = PlannerConfig.scalable_3d(
        enable_hysteresis=False,
        max_candidate_edges_per_target=1,
    )
    assistant = LearningCostAssistant(
        _FixedPredictor(1.0, confidence=0.1),
        config=LearningAssistConfig(mode="assist", min_confidence=0.9),
    )
    planner = AssignmentPlanner(config=config, learning_assistant=assistant)
    tracks, resources = _inputs()
    initial = [replace(tracks[0], position_ned=(0.0, 0.0, -100.0))]
    first = planner.plan(initial, resources, timestamp=0.0)
    moved = [replace(tracks[0], position_ned=(10.0, 0.0, -100.0))]
    resources[0] = replace(resources[0], position_ned=(1_000.0, 0.0, -100.0))
    second = planner.plan(
        moved,
        resources,
        timestamp=1.0,
        previous_plan=first,
        expected_previous_version=first.version,
    )

    assert first.metadata["learning_fallback_reason"] == "low_confidence"
    assert second.metadata["learning_fallback_reason"] == "low_confidence"
    assert second.version == first.version + 1
    assert second.previous_plan_id == first.plan_id
    with pytest.raises(StalePlanError, match="stale"):
        planner.plan(
            moved,
            resources,
            timestamp=2.0,
            previous_plan=first,
            expected_previous_version=first.version,
        )
