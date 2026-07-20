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
    assign_seed_splits,
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


class _PreferExpensiveRuleEdgePredictor:
    def predict(self, features: np.ndarray) -> ResidualPrediction:
        assert features.shape[0] == 2
        return ResidualPrediction(
            delta_costs=np.asarray([10.0, -10.0]),
            confidence=1.0,
        )


_DATASET_SHA = "d" * 64
_MODEL_SHA = "e" * 64


def test_multi_episode_minibatch_bc_reports_train_validation_and_whole_seed_metrics() -> None:
    pytest.importorskip("torch")
    split_map = assign_seed_splits(range(5))
    seeds = {
        split: next(seed for seed, assigned in split_map.items() if assigned == split)
        for split in ("train", "validation", "test")
    }
    records = (
        tuple(
            _record(seeds["train"], f"train_{index}", split="train")
            for index in range(6)
        )
        + tuple(
            _record(
                seeds["validation"],
                f"validation_{index}",
                split="validation",
            )
            for index in range(3)
        )
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
    assert result.whole_seed_metrics[f"seed:{seeds['train']}"]["split"] == "train"
    assert (
        result.whole_seed_metrics[f"seed:{seeds['validation']}"]["split"]
        == "validation"
    )
    assert f"seed:{seeds['test']}" not in result.whole_seed_metrics


def test_training_entry_points_reject_test_seed_consumption() -> None:
    pytest.importorskip("torch")
    split_map = assign_seed_splits(range(5))
    train_seed = next(seed for seed, split in split_map.items() if split == "train")
    validation_seed = next(
        seed for seed, split in split_map.items() if split == "validation"
    )
    test_seed = next(seed for seed, split in split_map.items() if split == "test")
    train = _record(train_seed, "train", split="train")
    validation = _record(validation_seed, "validation", split="validation")
    test = _record(test_seed, "test", split="test")

    with pytest.raises(ValueError, match="cannot consume test seed"):
        train_behavior_cloning(
            (train, validation, test),
            policy=SharedEdgeActorCriticPolicy(hidden_size=8),
            epochs=1,
        )
    with pytest.raises(ValueError, match="cannot consume test seed"):
        train_native_ppo(
            (train, test),
            policy=SharedEdgeActorCriticPolicy(hidden_size=8),
            updates=1,
        )


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
    split_map = assign_seed_splits(range(5))
    train_seed = next(seed for seed, split in split_map.items() if split == "train")
    records = tuple(
        _record(train_seed, "train_episode", frame_index=index, split="train")
        for index in range(3)
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
    assert not np.any(fallback.candidate_mask)


def test_shadow_pairing_does_not_mutate_rule_matrix_and_refuses_under_20_seeds() -> None:
    split_map = assign_seed_splits(range(5))
    records = tuple(
        _record(seed, f"episode_{seed}", split=split)
        for seed, split in split_map.items()
    )
    record = next(item for item in records if item.split == "test")
    snapshot = record.rule_cost_matrix.copy()

    report = evaluate_shadow_pairs(
        records,
        _ZeroPredictor(),
        alpha=0.25,
        minimum_unseen_seeds=20,
        evidence_eligible=True,
        dataset_frames_sha256=_DATASET_SHA,
        model_state_dict_sha256=_MODEL_SHA,
    )

    assert np.array_equal(record.rule_cost_matrix, snapshot)
    assert report.rule_matrix_unchanged is True
    assert report.rule_duplicate_count == report.shadow_duplicate_count == 0
    assert report.rule_hard_violation_count == report.shadow_hard_violation_count == 0
    assert report.promotion_manifest["promotion_recommended"] is False
    assert report.promotion_manifest["promotion_status"] == "unavailable"
    assert report.promotion_manifest["reason"] == "insufficient_unseen_seed_count"


def test_shadow_promotion_requires_20_whole_unseen_test_seeds_and_no_degradation() -> None:
    split_map = assign_seed_splits(range(100), minimum_unseen_seed_count=20)
    records = tuple(
        _record(seed, "episode", split=split) for seed, split in split_map.items()
    )

    report = evaluate_shadow_pairs(
        records,
        _ZeroPredictor(),
        alpha=0.25,
        minimum_unseen_seeds=20,
        evidence_eligible=True,
        dataset_frames_sha256=_DATASET_SHA,
        model_state_dict_sha256=_MODEL_SHA,
    )

    assert report.unseen_seed_count == 20
    assert report.fallback_reasons == {}
    assert report.promotion_manifest["safety_non_degradation"] is True
    assert report.promotion_manifest["promotion_recommended"] is True


def test_validation_shadow_cannot_be_promotion_evidence() -> None:
    split_map = assign_seed_splits(range(5))
    records = tuple(
        _record(seed, "episode", split=split) for seed, split in split_map.items()
    )

    report = evaluate_shadow_pairs(
        records,
        _ZeroPredictor(),
        split="validation",
        minimum_unseen_seeds=1,
        evidence_eligible=True,
        dataset_frames_sha256=_DATASET_SHA,
        model_state_dict_sha256=_MODEL_SHA,
    )

    assert report.promotion_manifest["promotion_recommended"] is False
    assert report.promotion_manifest["reason"] == "formal_promotion_requires_test_split"


def test_shadow_non_degradation_rescores_both_assignments_on_rule_cost_basis() -> None:
    split_map = assign_seed_splits(range(5))
    records = tuple(
        _record(
            seed,
            "episode",
            target_count=1,
            resource_count=2,
            split=split,
        )
        for seed, split in split_map.items()
    )

    report = evaluate_shadow_pairs(
        records,
        _PreferExpensiveRuleEdgePredictor(),
        alpha=2.0,
        minimum_unseen_seeds=1,
        evidence_eligible=True,
        dataset_frames_sha256=_DATASET_SHA,
        model_state_dict_sha256=_MODEL_SHA,
    )

    assert report.shadow_assignment_cost_mean > report.rule_assignment_cost_mean
    assert report.promotion_manifest["assignment_cost_non_degradation"] is False
    assert report.promotion_manifest["promotion_recommended"] is False
    assert report.promotion_manifest["reason"] == (
        "assignment_cost_non_degradation_failed"
    )


def test_shadow_solver_never_selects_an_edge_outside_the_deterministic_mask() -> None:
    mask = np.asarray([[True, False], [False, True]], dtype=bool)
    split_map = assign_seed_splits(range(5))
    records = tuple(
        _record(
            seed,
            "masked_test" if split == "test" else f"episode_{seed}",
            target_count=2 if split == "test" else 3,
            resource_count=2 if split == "test" else 5,
            mask=mask if split == "test" else None,
            split=split,
        )
        for seed, split in split_map.items()
    )
    report = evaluate_shadow_pairs(records, _ZeroPredictor())

    assert report.shadow_hard_violation_count == 0
    assert report.shadow_duplicate_count == 0
