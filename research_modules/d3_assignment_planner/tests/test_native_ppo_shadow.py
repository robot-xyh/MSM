from __future__ import annotations

from dataclasses import replace
from math import isfinite
from pathlib import Path

import numpy as np
import pytest

from d3_assignment_planner import (
    ClippedPPOTrainer,
    CostMatrixResult,
    PPOTransition,
    ResidualPrediction,
    SharedEdgeActorCriticPolicy,
    assign_episode_split,
    evaluate_shadow_pairs,
    load_model_bundle,
    train_behavior_cloning,
    train_native_ppo,
)

from test_learning_dataset_bundle import _record


class _ZeroPredictor:
    def predict(self, features: np.ndarray) -> ResidualPrediction:
        return ResidualPrediction(
            delta_costs=np.zeros(features.shape[0], dtype=float),
            confidence=1.0,
        )


def test_multi_episode_minibatch_bc_reports_train_validation_and_whole_seed_metrics() -> None:
    pytest.importorskip("torch")
    records = tuple(_record(0, f"train_{index}") for index in range(6)) + tuple(
        _record(1, f"validation_{index}") for index in range(3)
    )

    _, result = train_behavior_cloning(
        records,
        policy=SharedEdgeActorCriticPolicy(hidden_size=12),
        epochs=20,
        mini_batch_frames=2,
        learning_rate=0.01,
        seed=11,
    )

    assert result.train_frame_count == 6
    assert result.validation_frame_count == 3
    assert result.final_train_loss < result.initial_train_loss
    assert isfinite(result.validation_loss)
    assert result.whole_seed_metrics["unit_sparse_v1:0"]["split"] == "train"
    assert result.whole_seed_metrics["unit_sparse_v1:1"]["split"] == "validation"


def test_native_ppo_clip_update_is_finite_and_masked_action_cannot_be_bypassed() -> None:
    pytest.importorskip("torch")
    policy = SharedEdgeActorCriticPolicy(hidden_size=8)
    features = np.zeros((3, 12), dtype=np.float32)
    edge_mask = np.asarray([True, False, True])
    action = policy.act(
        features,
        edge_mask=edge_mask,
        advice_allowed=False,
        deterministic=True,
    )
    assert action.residuals[1] == 0.0
    with pytest.raises(ValueError, match="masked edges"):
        PPOTransition(
            features=features,
            edge_mask=edge_mask,
            residual_action=np.asarray([0.0, 0.1, 0.0]),
            advice_action=0,
            advice_allowed=False,
            old_log_probability=0.0,
            old_value=0.0,
            reward=1.0,
            advantage=1.0,
            return_value=1.0,
            scenario_version="s",
            seed=0,
            episode="e",
            frame_index=0,
        )
    transitions = tuple(
        PPOTransition(
            features=features,
            edge_mask=edge_mask,
            residual_action=action.residuals,
            advice_action=0,
            advice_allowed=False,
            old_log_probability=action.log_probability + offset,
            old_value=action.value,
            reward=1.0,
            advantage=advantage,
            return_value=1.0,
            scenario_version="s",
            seed=index,
            episode="e",
            frame_index=0,
        )
        for index, (offset, advantage) in enumerate(((2.0, 1.0), (-2.0, -1.0)))
    )

    result = ClippedPPOTrainer(
        policy, epochs=2, mini_batch_frames=2, seed=4
    ).update(transitions)

    assert all(isfinite(float(value)) for value in result.to_dict().values())
    assert 0.0 <= result.clip_fraction <= 1.0
    assert result.clip_fraction > 0.0


def test_native_ppo_pipeline_updates_variable_episode_frames() -> None:
    pytest.importorskip("torch")
    records = tuple(
        _record(0, "train_episode", frame_index=index) for index in range(3)
    )

    _, result = train_native_ppo(
        records,
        policy=SharedEdgeActorCriticPolicy(hidden_size=8),
        updates=1,
        epochs_per_update=1,
        mini_batch_frames=2,
        seed=5,
    )

    assert result.train_frame_count == 3
    assert result.update_results[0].transition_count == 3
    assert isfinite(result.update_results[0].policy_loss)
    assert isfinite(result.reward_mean)


def test_bundle_missing_and_version_constraint_return_exact_rule_matrix(
    tmp_path: Path,
) -> None:
    loaded = load_model_bundle(tmp_path / "missing", mode="shadow")
    rule = CostMatrixResult(
        matrix=np.asarray([[1.0, 2.0]]),
        breakdowns=(({}, {}),),
        target_ids=("target",),
        resource_ids=("r0", "r1"),
        unassigned_costs=np.asarray([3.0]),
        reject_reasons=((None, None),),
        candidate_mask=np.asarray([[True, True]]),
    )

    fallback = loaded.assistant.apply(
        rule,
        (),
        (),
        expected_previous_version=1,
        current_plan_version=2,
    )

    assert loaded.fallback_reason == "model_bundle_missing"
    assert np.array_equal(fallback.matrix, rule.matrix)
    assert fallback.metadata["learning_fallback_reason"] == "version_constraint"


def test_shadow_pairing_does_not_mutate_rule_matrix_and_refuses_under_20_seeds() -> None:
    record = _record(6, "test_episode")
    assert record.split == "test"
    snapshot = record.rule_cost_matrix.copy()

    report = evaluate_shadow_pairs(
        [record],
        _ZeroPredictor(),
        alpha=0.25,
        minimum_unseen_seeds=20,
        evidence_eligible=True,
    )

    assert np.array_equal(record.rule_cost_matrix, snapshot)
    assert report.rule_matrix_unchanged is True
    assert report.rule_duplicate_count == report.shadow_duplicate_count == 0
    assert report.rule_hard_violation_count == report.shadow_hard_violation_count == 0
    assert report.promotion_manifest["promotion_recommended"] is False
    assert report.promotion_manifest["promotion_status"] == "unavailable"
    assert report.promotion_manifest["reason"] == "insufficient_unseen_seed_count"


def test_shadow_promotion_requires_20_whole_unseen_test_seeds_and_no_degradation() -> None:
    test_seeds = [
        seed
        for seed in range(1_000)
        if assign_episode_split("unit_sparse_v1", seed, "episode") == "test"
    ][:20]
    records = tuple(_record(seed, "episode") for seed in test_seeds)

    report = evaluate_shadow_pairs(
        records,
        _ZeroPredictor(),
        alpha=0.25,
        minimum_unseen_seeds=20,
        evidence_eligible=True,
    )

    assert report.unseen_seed_count == 20
    assert report.fallback_reasons == {}
    assert report.promotion_manifest["safety_non_degradation"] is True
    assert report.promotion_manifest["promotion_recommended"] is True


def test_shadow_solver_never_selects_an_edge_outside_the_deterministic_mask() -> None:
    mask = np.asarray([[True, False], [False, True]], dtype=bool)
    record = _record(
        6,
        "masked_test",
        target_count=2,
        resource_count=2,
        mask=mask,
    )
    report = evaluate_shadow_pairs([record], _ZeroPredictor())

    assert report.shadow_hard_violation_count == 0
    assert report.shadow_duplicate_count == 0
