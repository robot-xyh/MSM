from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from d5_terminal_association.active_vision_bc_training import (
    ActiveVisionBcSplitCache,
    action_metrics,
    assess_behavior_cloning_development_readiness,
    evaluate_loss,
    intent_classification_metrics,
    intent_weighting_profile,
)
from d5_terminal_association.active_vision_contracts import (
    ActiveVisionFovMode,
    ActiveVisionIntent,
)
from d5_terminal_association.active_vision_learning import (
    ACTIVE_VISION_FEATURE_NAMES,
)


def _imbalanced_cache() -> tuple[ActiveVisionBcSplitCache, dict[str, object]]:
    sample_count = 100
    candidate_count = 2
    intent_values = tuple(item.value for item in ActiveVisionIntent)
    fov_values = tuple(item.value for item in ActiveVisionFovMode)
    intent_codes = {value: index for index, value in enumerate(intent_values)}
    candidate_intent = np.tile(
        np.asarray(
            [
                intent_codes[ActiveVisionIntent.REACQUIRE.value],
                intent_codes[ActiveVisionIntent.OBSERVE_TARGET.value],
            ],
            dtype=np.uint8,
        ),
        sample_count,
    )
    selected = np.zeros(sample_count, dtype=np.uint16)
    selected[-1] = 1
    counts = np.full(sample_count, candidate_count, dtype=np.uint16)
    offsets = np.arange(
        0,
        (sample_count + 1) * candidate_count,
        candidate_count,
        dtype=np.int64,
    )
    camera_type = np.concatenate(
        (
            np.zeros(sample_count // 2, dtype=np.uint8),
            np.ones(sample_count // 2, dtype=np.uint8),
        )
    )
    candidate_rows = sample_count * candidate_count
    files = {
        "features": np.zeros(
            (candidate_rows, len(ACTIVE_VISION_FEATURE_NAMES)),
            dtype=np.float32,
        ),
        "candidate_intent": candidate_intent,
        "candidate_fov": np.zeros(candidate_rows, dtype=np.uint8),
        "candidate_yaw": np.zeros(candidate_rows, dtype=np.float32),
        "candidate_pitch": np.zeros(candidate_rows, dtype=np.float32),
        "candidate_has_target": np.tile(
            np.asarray([0, 1], dtype=np.uint8),
            sample_count,
        ),
        "candidate_count": counts,
        "selected_index": selected,
        "camera_type": camera_type,
        "scale": np.zeros(sample_count, dtype=np.uint8),
        "scenario": np.zeros(sample_count, dtype=np.uint16),
    }
    cache = ActiveVisionBcSplitCache(
        root=Path("."),
        sample_count=sample_count,
        candidate_row_count=candidate_rows,
        feature_dim=len(ACTIVE_VISION_FEATURE_NAMES),
        files=files,
        offsets=offsets,
    )
    mappings: dict[str, object] = {
        "intent": intent_codes,
        "fov": {value: index for index, value in enumerate(fov_values)},
        "camera_type": {"interceptor": 0, "recon": 1, "unknown": 2},
        "scale": {"200v200": 0},
        "scenario": {"active-vision-200v200-v1": 0},
    }
    return cache, mappings


def test_inverse_sqrt_weighting_upweights_minority_without_fabricating_hold() -> None:
    cache, mappings = _imbalanced_cache()

    profile = intent_weighting_profile(
        cache,
        mappings=mappings,
        strategy="inverse_sqrt",
        maximum_weight=8.0,
    )

    observe_weight = profile["weight_by_intent"]["observe_target"]
    reacquire_weight = profile["weight_by_intent"]["reacquire"]
    hold_weight = profile["weight_by_intent"]["hold"]
    assert observe_weight["available"] is True
    assert reacquire_weight["available"] is True
    assert observe_weight["value"] > reacquire_weight["value"]
    assert hold_weight["available"] is False
    assert hold_weight["reason"] == "no_positive_samples"
    assert hold_weight["value"] is None
    assert set(profile["unavailable_intents"]) == {"hold", "search_sector"}
    selected_codes = np.asarray(
        cache.files["candidate_intent"][
            cache.offsets[:-1]
            + np.asarray(cache.files["selected_index"], dtype=np.int64)
        ],
        dtype=np.int64,
    )
    lookup = np.asarray(profile["weight_by_code"], dtype=np.float64)
    assert np.mean(lookup[selected_codes]) == pytest.approx(1.0)
    assert np.max(lookup[selected_codes]) <= 8.0
    assert profile["zero_padding_or_synthetic_positive_used"] is False


def test_majority_only_accuracy_cannot_pass_development_model_admission() -> None:
    cache, mappings = _imbalanced_cache()
    predictions = np.zeros(cache.sample_count, dtype=np.int64)
    confidences = np.full(cache.sample_count, 0.99, dtype=np.float64)
    metrics = action_metrics(
        cache,
        predictions,
        mappings=mappings,
        loss=0.01,
        confidences=confidences,
        out_of_distribution=np.zeros(cache.sample_count, dtype=bool),
        calibration_bin_count=10,
        ood_margin=0.05,
    )
    evaluation = {"test": metrics}
    audit = {
        "intent_counts_by_split": {
            "train": {
                "observe_target": 1,
                "search_sector": 0,
                "hold": 0,
                "reacquire": 99,
            }
        },
        "class_imbalance": {
            "majority_intent": "reacquire",
            "majority_fraction": 0.99,
        }
    }

    admission = assess_behavior_cloning_development_readiness(
        audit,
        evaluation,
    )

    assert metrics["overall"]["exact_action_accuracy"]["value"] == 0.99
    assert (
        metrics["action_distribution"]["majority_only_exact_accuracy"]["value"]
        == 0.99
    )
    assert (
        metrics["intent_classification"]["per_class"]["observe_target"][
            "recall"
        ]["value"]
        == 0.0
    )
    hold_recall = metrics["intent_classification"]["per_class"]["hold"][
        "recall"
    ]
    assert hold_recall["available"] is False
    assert hold_recall["reason"] == "no_positive_samples"
    assert hold_recall["value"] is None
    assert admission["development_model_precheck_passed"] is False
    assert admission["may_enter_formal_paired_shadow"] is False
    assert admission["assist_admitted"] is False
    assert admission["active_vision_authority_granted"] is False
    assert admission["assignment_authority_granted"] is False
    assert admission["control_authority_granted"] is False
    assert "action_recall_below_threshold:observe_target" in admission[
        "failure_reasons"
    ]
    assert "action_recall_unavailable:hold" in admission["failure_reasons"]
    assert "training_action_unavailable:hold" in admission["failure_reasons"]
    assert admission["hold_positive_fabrication_used"] is False


def test_classification_denominators_keep_undefined_metrics_unavailable() -> None:
    mapping = {0: "truth_only", 1: "prediction_only", 2: "absent"}

    metrics = intent_classification_metrics(
        np.asarray([0, 0], dtype=np.int64),
        np.asarray([1, 1], dtype=np.int64),
        mapping,
    )

    truth_only = metrics["per_class"]["truth_only"]
    assert truth_only["precision_denominator"] == 0
    assert truth_only["precision"] == {
        "available": False,
        "value": None,
        "reason": "no_predicted_samples",
    }
    assert truth_only["recall"]["value"] == 0.0
    assert truth_only["f1"]["value"] == 0.0
    prediction_only = metrics["per_class"]["prediction_only"]
    assert prediction_only["precision"]["value"] == 0.0
    assert prediction_only["recall"] == {
        "available": False,
        "value": None,
        "reason": "no_positive_samples",
    }
    assert prediction_only["f1"]["value"] == 0.0
    absent = metrics["per_class"]["absent"]
    assert absent["precision"]["available"] is False
    assert absent["recall"]["available"] is False
    assert absent["f1"]["available"] is False


class _LinearCandidateModel(torch.nn.Module):
    feature_dim = len(ACTIVE_VISION_FEATURE_NAMES)

    def __init__(self) -> None:
        super().__init__()
        self.encoder = torch.nn.Identity()
        self.actor = torch.nn.Linear(self.feature_dim, 1, bias=False)
        with torch.no_grad():
            self.actor.weight.zero_()
            self.actor.weight[0, 0] = 1.0


def test_validation_loss_uses_train_normalized_intent_weights() -> None:
    cache, mappings = _imbalanced_cache()
    cache.files["features"][:, 0] = np.tile(
        np.asarray([2.0, 0.0], dtype=np.float32),
        cache.sample_count,
    )
    profile = intent_weighting_profile(
        cache,
        mappings=mappings,
        strategy="inverse_sqrt",
        maximum_weight=8.0,
    )
    lookup = np.asarray(profile["weight_by_code"], dtype=np.float64)
    model = _LinearCandidateModel()
    logits = torch.tensor([[2.0, 0.0]], dtype=torch.float32)
    majority_loss = float(
        torch.nn.functional.cross_entropy(logits, torch.tensor([0])).item()
    )
    minority_loss = float(
        torch.nn.functional.cross_entropy(logits, torch.tensor([1])).item()
    )
    intent_codes = mappings["intent"]
    expected = (
        99 * lookup[intent_codes["reacquire"]] * majority_loss
        + lookup[intent_codes["observe_target"]] * minority_loss
    ) / (
        99 * lookup[intent_codes["reacquire"]]
        + lookup[intent_codes["observe_target"]]
    )

    actual = evaluate_loss(
        model,
        cache,
        batch_size=13,
        device=torch.device("cpu"),
        intent_weight_lookup=lookup,
    )

    assert actual == pytest.approx(expected, rel=1.0e-6)


def test_training_absent_action_is_explicit_precheck_failure() -> None:
    cache, mappings = _imbalanced_cache()
    metrics = action_metrics(
        cache,
        np.asarray(cache.files["selected_index"], dtype=np.int64),
        mappings=mappings,
        loss=0.01,
        confidences=np.full(cache.sample_count, 0.9, dtype=np.float64),
        out_of_distribution=np.zeros(cache.sample_count, dtype=bool),
    )
    audit = {
        "intent_counts_by_split": {
            "train": {
                "observe_target": 0,
                "search_sector": 1,
                "hold": 1,
                "reacquire": 99,
            }
        },
        "class_imbalance": {"majority_fraction": 0.99},
    }

    admission = assess_behavior_cloning_development_readiness(
        audit,
        {"test": metrics},
    )

    assert metrics["intent_classification"]["per_class"]["observe_target"][
        "recall"
    ]["value"] == 1.0
    assert "training_action_unavailable:observe_target" in admission[
        "failure_reasons"
    ]
    assert admission["assist_admitted"] is False
    assert admission["active_vision_authority_granted"] is False
    assert admission["assignment_authority_granted"] is False
    assert admission["control_authority_granted"] is False
