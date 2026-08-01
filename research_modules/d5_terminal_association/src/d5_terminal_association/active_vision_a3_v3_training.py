"""A3 v3 hierarchical intent/ranking development entry point.

The training path accepts train and validation caches only. Future held-out
data has a separate one-shot contract and is intentionally not accepted here.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .active_vision_a3_v3_protocol import (
    A3_V3_CAMERA_ROLES,
    A3_V3_INTENTS,
    ACTIVE_VISION_A3_V3_DEFAULT_STATUS,
    FrozenA3V3Protocol,
    authority_false_contract,
    load_and_validate_a3_v3_source_manifest,
    load_frozen_a3_v3_protocol,
)
from .active_vision_bc_training import (
    ActiveVisionBcSplitCache,
    action_metrics,
)
from .active_vision_learning import ACTIVE_VISION_FEATURE_NAMES


ACTIVE_VISION_A3_V3_DEVELOPMENT_CACHE_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-development-cache.v1"
)
ACTIVE_VISION_A3_V3_DEVELOPMENT_REPORT_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-development-report.v1"
)
ACTIVE_VISION_A3_V3_WEIGHTS_FILENAME = "a3_v3_development_weights.pt"
ACTIVE_VISION_A3_V3_REPORT_FILENAME = "a3_v3_development_report.json"

_DEVELOPMENT_SPLITS = ("train", "validation")


@dataclass(frozen=True)
class HierarchicalIntentRankerOutput:
    base_candidate_logits: torch.Tensor
    intent_logits: torch.Tensor
    legal_intent_mask: torch.Tensor
    bounded_intent_adjustment: torch.Tensor
    candidate_logits: torch.Tensor


class HierarchicalIntentLegalCandidateRanker(nn.Module):
    """Set-context intent classifier fused into a legal candidate ranker."""

    def __init__(
        self,
        *,
        hidden_dim: int,
        maximum_absolute_logit_adjustment: float,
        feature_dim: int = len(ACTIVE_VISION_FEATURE_NAMES),
        intent_count: int = len(A3_V3_INTENTS),
    ) -> None:
        super().__init__()
        hidden = int(hidden_dim)
        if hidden <= 0:
            raise ValueError("A3 v3 hidden_dim must be positive")
        adjustment = float(maximum_absolute_logit_adjustment)
        if not math.isfinite(adjustment) or not 0.0 < adjustment <= 4.0:
            raise ValueError("A3 v3 intent adjustment must be finite and bounded")
        if int(feature_dim) <= 0 or int(intent_count) <= 1:
            raise ValueError("A3 v3 model dimensions are invalid")
        self.feature_dim = int(feature_dim)
        self.hidden_dim = hidden
        self.intent_count = int(intent_count)
        self.maximum_absolute_logit_adjustment = adjustment
        self.encoder = nn.Sequential(
            nn.Linear(self.feature_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
        )
        self.candidate_rank_head = nn.Linear(hidden, 1)
        self.intent_head = nn.Sequential(
            nn.Linear(2 * hidden, hidden),
            nn.Tanh(),
            nn.Linear(hidden, self.intent_count),
        )

    def forward(
        self,
        candidate_features: torch.Tensor,
        candidate_mask: torch.Tensor,
        candidate_intents: torch.Tensor,
    ) -> HierarchicalIntentRankerOutput:
        if candidate_features.ndim != 3:
            raise ValueError("A3 v3 candidate features must be a padded batch")
        batch_size, candidate_count, feature_dim = candidate_features.shape
        if feature_dim != self.feature_dim or batch_size <= 0 or candidate_count <= 0:
            raise ValueError("A3 v3 candidate feature shape mismatch")
        if candidate_mask.shape != (batch_size, candidate_count):
            raise ValueError("A3 v3 candidate mask shape mismatch")
        if candidate_intents.shape != (batch_size, candidate_count):
            raise ValueError("A3 v3 candidate intent shape mismatch")
        mask = candidate_mask.to(dtype=torch.bool)
        if torch.any(~torch.any(mask, dim=1)):
            raise ValueError("A3 v3 each sample requires a legal candidate")
        intent_codes = candidate_intents.to(dtype=torch.long)
        valid_codes = intent_codes[mask]
        if torch.any(valid_codes < 0) or torch.any(valid_codes >= self.intent_count):
            raise ValueError("A3 v3 legal candidate intent code is out of range")

        encoded = self.encoder(candidate_features)
        mask_values = mask.unsqueeze(-1)
        counts = torch.sum(mask_values, dim=1).clamp_min(1)
        mean_pool = torch.sum(encoded * mask_values, dim=1) / counts
        maximum_pool = encoded.masked_fill(~mask_values, -torch.inf).amax(dim=1)
        context = torch.cat((mean_pool, maximum_pool), dim=1)
        intent_logits = self.intent_head(context)

        safe_codes = torch.where(mask, intent_codes, torch.zeros_like(intent_codes))
        legal_intent_mask = torch.stack(
            tuple(
                torch.any(mask & (intent_codes == code), dim=1)
                for code in range(self.intent_count)
            ),
            dim=1,
        )
        if torch.any(~torch.any(legal_intent_mask, dim=1)):
            raise RuntimeError("A3 v3 legal intent mask is empty")

        bounded_by_intent = self.maximum_absolute_logit_adjustment * torch.tanh(
            intent_logits
        )
        candidate_adjustment = torch.gather(bounded_by_intent, 1, safe_codes)
        candidate_adjustment = candidate_adjustment.masked_fill(~mask, 0.0)
        base_logits = self.candidate_rank_head(encoded).squeeze(-1)
        candidate_logits = (base_logits + candidate_adjustment).masked_fill(
            ~mask,
            -torch.inf,
        )
        return HierarchicalIntentRankerOutput(
            base_candidate_logits=base_logits,
            intent_logits=intent_logits.masked_fill(~legal_intent_mask, -torch.inf),
            legal_intent_mask=legal_intent_mask,
            bounded_intent_adjustment=candidate_adjustment,
            candidate_logits=candidate_logits,
        )


def bounded_class_balanced_intent_weights(
    labels: np.ndarray,
    *,
    intent_count: int,
    exponent: float,
    maximum_weight_ratio: float,
) -> dict[str, Any]:
    """Compute train-only inverse-sqrt weights and reject absent intents."""

    values = np.asarray(labels)
    if values.ndim != 1 or not np.issubdtype(values.dtype, np.integer):
        raise ValueError("A3 v3 intent labels must be an integer vector")
    values = values.astype(np.int64, copy=False)
    if len(values) == 0 or np.any(values < 0) or np.any(values >= intent_count):
        raise ValueError("A3 v3 intent labels are empty or out of range")
    if not math.isfinite(exponent) or not 0.0 < exponent <= 1.0:
        raise ValueError("A3 v3 class balance exponent is invalid")
    ratio = float(maximum_weight_ratio)
    if not math.isfinite(ratio) or not 1.0 <= ratio <= 8.0:
        raise ValueError("A3 v3 maximum class weight ratio is invalid")
    counts = np.bincount(values, minlength=intent_count).astype(np.int64)
    missing = [A3_V3_INTENTS[index] for index, count in enumerate(counts) if count == 0]
    if missing:
        raise ValueError(f"A3 v3 minority intent missing from train: {missing}")
    raw = np.power(float(np.max(counts)) / counts.astype(np.float64), exponent)
    raw = np.minimum(raw, ratio)
    normalizer = float(np.sum(raw * counts) / np.sum(counts))
    weights = raw / normalizer
    absolute_minimum = 1.0 / ratio
    tolerance = 1.0e-12
    if (
        not np.all(np.isfinite(weights))
        or np.any(weights < absolute_minimum - tolerance)
        or np.any(weights > ratio + tolerance)
        or not math.isclose(
            float(np.mean(weights[values])),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    ):
        raise RuntimeError("A3 v3 class-balanced weights escaped frozen bounds")
    return {
        "method": "bounded_inverse_sqrt_train_only",
        "counts_by_intent": {
            name: int(counts[index]) for index, name in enumerate(A3_V3_INTENTS)
        },
        "weights_by_intent": {
            name: float(weights[index]) for index, name in enumerate(A3_V3_INTENTS)
        },
        "weight_by_code": weights.tolist(),
        "training_sample_weight_mean": float(np.mean(weights[values])),
        "absolute_bounds": [absolute_minimum, ratio],
        "missing_intents": [],
        "synthetic_positive_or_oversampling_used": False,
    }


def hierarchical_intent_ranking_loss(
    output: HierarchicalIntentRankerOutput,
    *,
    selected_indices: torch.Tensor,
    candidate_intents: torch.Tensor,
    class_weights: torch.Tensor,
    intent_auxiliary_loss_weight: float,
) -> dict[str, torch.Tensor]:
    """Combine legal ranking CE with class-balanced intent auxiliary CE."""

    selected = selected_indices.to(dtype=torch.long)
    if selected.ndim != 1 or selected.shape[0] != output.candidate_logits.shape[0]:
        raise ValueError("A3 v3 selected candidate indices are misaligned")
    if class_weights.shape != (output.intent_logits.shape[1],):
        raise ValueError("A3 v3 class weights have the wrong shape")
    if not torch.all(torch.isfinite(class_weights)) or torch.any(class_weights <= 0):
        raise ValueError("A3 v3 class weights must be finite and positive")
    auxiliary_weight = float(intent_auxiliary_loss_weight)
    if not math.isfinite(auxiliary_weight) or not 0.0 < auxiliary_weight <= 1.0:
        raise ValueError("A3 v3 auxiliary loss weight is out of bounds")
    selected_intents = torch.gather(
        candidate_intents.to(dtype=torch.long),
        1,
        selected.reshape(-1, 1),
    ).reshape(-1)
    if torch.any(
        ~torch.gather(
            output.legal_intent_mask,
            1,
            selected_intents.reshape(-1, 1),
        ).reshape(-1)
    ):
        raise ValueError("A3 v3 demonstrated intent is outside the legal set")

    ranking_loss = F.cross_entropy(output.candidate_logits, selected)
    per_sample_intent = F.cross_entropy(
        output.intent_logits,
        selected_intents,
        reduction="none",
    )
    sample_weights = class_weights[selected_intents]
    intent_loss = torch.sum(per_sample_intent * sample_weights) / torch.sum(
        sample_weights
    )
    composite = ranking_loss + auxiliary_weight * intent_loss
    if not torch.isfinite(composite):
        raise RuntimeError("A3 v3 composite loss is non-finite")
    return {
        "composite_loss": composite,
        "ranking_loss": ranking_loss,
        "intent_auxiliary_loss": intent_loss,
    }


def fit_validation_temperature(
    logits: np.ndarray,
    selected_indices: np.ndarray,
    *,
    minimum: float,
    maximum: float,
    grid_size: int,
) -> dict[str, Any]:
    """Fit one bounded scalar temperature on validation candidate NLL only."""

    values = np.asarray(logits, dtype=np.float64)
    selected = np.asarray(selected_indices)
    if values.ndim != 2 or values.shape[0] == 0:
        raise ValueError("A3 v3 validation logits must be a non-empty matrix")
    if selected.shape != (values.shape[0],) or not np.issubdtype(
        selected.dtype, np.integer
    ):
        raise ValueError("A3 v3 validation labels are misaligned")
    selected = selected.astype(np.int64, copy=False)
    valid = np.isfinite(values)
    counts = np.sum(valid, axis=1)
    if np.any(counts <= 0) or np.any(selected < 0) or np.any(selected >= values.shape[1]):
        raise ValueError("A3 v3 validation candidates are invalid")
    if np.any(~valid[np.arange(len(selected)), selected]):
        raise ValueError("A3 v3 validation selected candidate is masked")
    lower = float(minimum)
    upper = float(maximum)
    steps = int(grid_size)
    if (
        not math.isfinite(lower)
        or not math.isfinite(upper)
        or not 0.0 < lower < upper <= 10.0
        or steps < 2
    ):
        raise ValueError("A3 v3 temperature grid is invalid")

    temperatures = np.linspace(lower, upper, steps, dtype=np.float64)
    losses = np.empty(steps, dtype=np.float64)
    row_indices = np.arange(len(selected))
    for index, temperature in enumerate(temperatures):
        scaled = values / temperature
        row_maximum = np.max(scaled, axis=1)
        exp_sum = np.sum(
            np.where(valid, np.exp(scaled - row_maximum[:, None]), 0.0),
            axis=1,
        )
        selected_logits = scaled[row_indices, selected]
        losses[index] = float(
            np.mean(row_maximum + np.log(exp_sum) - selected_logits)
        )
    best_index = int(np.argmin(losses))
    return {
        "method": "scalar_temperature_fixed_grid",
        "fit_split": "validation",
        "test_access": False,
        "temperature": float(temperatures[best_index]),
        "validation_nll": float(losses[best_index]),
        "temperature_minimum": lower,
        "temperature_maximum": upper,
        "temperature_grid_size": steps,
        "tie_break": "lowest_temperature",
    }


def assess_metric_gate(
    metrics: Mapping[str, Any],
    gate: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply frozen per-intent, per-role, macro-recall, and ECE floors."""

    failures: list[str] = []
    classification = metrics["intent_classification"]
    macro = classification["macro_recall_supported_classes"]
    _require_available_metric(macro, "macro intent recall")
    macro_value = float(macro["value"])
    if macro_value < float(gate["minimum_macro_intent_recall"]):
        failures.append("macro_intent_recall_below_threshold")
    for intent in A3_V3_INTENTS:
        recall = classification["per_class"][intent]["recall"]
        if not recall.get("available", False):
            failures.append(f"intent_recall_unavailable:{intent}")
        elif float(recall["value"]) < float(
            gate["minimum_per_intent_recall"][intent]
        ):
            failures.append(f"intent_recall_below_threshold:{intent}")
    for role in A3_V3_CAMERA_ROLES:
        role_metrics = metrics["per_camera_type"].get(role)
        if role_metrics is None:
            failures.append(f"camera_role_unavailable:{role}")
            continue
        exact = role_metrics["exact_action_accuracy"]
        if not exact.get("available", False):
            failures.append(f"camera_role_unavailable:{role}")
        elif float(exact["value"]) < float(
            gate["minimum_per_camera_role_exact_action_accuracy"][role]
        ):
            failures.append(f"camera_role_below_threshold:{role}")
    ece = metrics["calibration"]["expected_calibration_error"]
    if not ece.get("available", False):
        failures.append("expected_calibration_error_unavailable")
    elif float(ece["value"]) > float(gate["maximum_expected_calibration_error"]):
        failures.append("expected_calibration_error_above_threshold")
    return {
        "passed": not failures,
        "failure_reasons": failures,
        "thresholds": _json_ready(gate),
        "authority": authority_false_contract(),
        "rule_fallback_required": True,
    }


def load_a3_v3_development_cache(
    root: str | Path,
    *,
    protocol: FrozenA3V3Protocol,
    source_manifest: Mapping[str, Any],
    source_evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, ActiveVisionBcSplitCache], str]:
    """Load a cache that contains train and validation, never test/held-out."""

    cache_root = Path(root)
    manifest_path = cache_root / "manifest.json"
    manifest = _read_json(manifest_path)
    expected_fields = {
        "schema_version",
        "protocol_sha256",
        "source_manifest_sha256",
        "feature_names",
        "mappings",
        "training_feature_bounds",
        "seed_catalogs",
        "splits",
    }
    _expect_fields(manifest, expected_fields, "A3 v3 development cache")
    if manifest.get("schema_version") != ACTIVE_VISION_A3_V3_DEVELOPMENT_CACHE_SCHEMA_VERSION:
        raise ValueError("A3 v3 development cache schema mismatch")
    if manifest.get("protocol_sha256") != protocol.sha256:
        raise ValueError("A3 v3 development cache protocol mismatch")
    if manifest.get("source_manifest_sha256") != source_evidence.get(
        "source_manifest_sha256"
    ):
        raise ValueError("A3 v3 development cache source manifest mismatch")
    if manifest.get("feature_names") != list(ACTIVE_VISION_FEATURE_NAMES):
        raise ValueError("A3 v3 development cache feature order mismatch")
    split_payload = manifest.get("splits")
    if not isinstance(split_payload, Mapping) or set(split_payload) != set(
        _DEVELOPMENT_SPLITS
    ):
        raise ValueError("A3 v3 development cache must contain train and validation only")
    seed_payload = manifest.get("seed_catalogs")
    if not isinstance(seed_payload, Mapping) or set(seed_payload) != set(
        _DEVELOPMENT_SPLITS
    ):
        raise ValueError("A3 v3 development cache seed catalogs are invalid")
    for split in _DEVELOPMENT_SPLITS:
        if seed_payload[split] != source_manifest["seed_catalogs"][split]:
            raise ValueError(f"A3 v3 development cache {split} seed catalog mismatch")

    mappings = manifest.get("mappings")
    if not isinstance(mappings, Mapping):
        raise ValueError("A3 v3 development cache mappings are unavailable")
    intent_mapping = mappings.get("intent")
    if not isinstance(intent_mapping, Mapping) or set(intent_mapping) != set(
        A3_V3_INTENTS
    ):
        raise ValueError("A3 v3 development cache intent mapping mismatch")
    if sorted(int(value) for value in intent_mapping.values()) != list(
        range(len(A3_V3_INTENTS))
    ):
        raise ValueError("A3 v3 development cache intent codes are invalid")
    camera_mapping = mappings.get("camera_type")
    if not isinstance(camera_mapping, Mapping) or not set(A3_V3_CAMERA_ROLES).issubset(
        camera_mapping
    ):
        raise ValueError("A3 v3 development cache camera role mapping mismatch")

    bounds = manifest.get("training_feature_bounds")
    if not isinstance(bounds, Mapping) or set(bounds) != {"minimum", "maximum"}:
        raise ValueError("A3 v3 development cache feature bounds are unavailable")
    lower = np.asarray(bounds["minimum"], dtype=np.float64)
    upper = np.asarray(bounds["maximum"], dtype=np.float64)
    if (
        lower.shape != (len(ACTIVE_VISION_FEATURE_NAMES),)
        or upper.shape != lower.shape
        or not np.all(np.isfinite(lower))
        or not np.all(np.isfinite(upper))
        or np.any(lower > upper)
    ):
        raise ValueError("A3 v3 development cache feature bounds are invalid")

    caches = {
        split: ActiveVisionBcSplitCache.load(cache_root / split, split_payload[split])
        for split in _DEVELOPMENT_SPLITS
    }
    _validate_cache_support(caches, mappings=mappings)
    return manifest, caches, _sha256_file(manifest_path)


def train_a3_v3_hierarchical_model(
    cache_manifest: Mapping[str, Any],
    caches: Mapping[str, ActiveVisionBcSplitCache],
    *,
    protocol: FrozenA3V3Protocol,
) -> tuple[
    HierarchicalIntentLegalCandidateRanker,
    dict[str, Any],
    dict[str, Any],
]:
    """Train one frozen configuration and calibrate on validation only."""

    if set(caches) != set(_DEVELOPMENT_SPLITS):
        raise ValueError("A3 v3 training accepts train and validation only")
    development = protocol.payload["development"]
    optimizer_config = development["optimizer"]
    method = protocol.payload["method"]
    loss_config = method["loss"]
    seed = int(optimizer_config["random_seed_not_episode_seed"])
    _set_fixed_seed(seed)
    torch.set_num_threads(
        min(int(optimizer_config["cpu_threads"]), os.cpu_count() or 1)
    )
    device = torch.device("cpu")
    model = HierarchicalIntentLegalCandidateRanker(
        hidden_dim=int(optimizer_config["hidden_dim"]),
        maximum_absolute_logit_adjustment=float(
            method["bounded_intent_fusion"]["maximum_absolute_logit_adjustment"]
        ),
    ).to(device)
    train_cache = caches["train"]
    validation_cache = caches["validation"]
    train_labels = selected_intent_codes(train_cache)
    weight_profile = bounded_class_balanced_intent_weights(
        train_labels,
        intent_count=len(A3_V3_INTENTS),
        exponent=float(loss_config["class_balance_exponent"]),
        maximum_weight_ratio=float(loss_config["maximum_class_weight_ratio"]),
    )
    class_weights = torch.as_tensor(
        weight_profile["weight_by_code"],
        dtype=torch.float32,
        device=device,
    )
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(optimizer_config["learning_rate"]),
        weight_decay=float(optimizer_config["weight_decay"]),
    )
    batch_size = int(optimizer_config["batch_size"])
    evaluation_batch_size = int(optimizer_config["evaluation_batch_size"])
    auxiliary_weight = float(loss_config["intent_auxiliary_loss_weight"])
    best_rule = development["best_epoch"]
    tolerance = float(best_rule["tie_tolerance"])
    best_loss = math.inf
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    epochs: list[dict[str, Any]] = []
    for epoch_index in range(int(optimizer_config["epochs"])):
        model.train()
        order = np.random.default_rng(seed + epoch_index).permutation(
            train_cache.sample_count
        )
        totals = {"composite": 0.0, "ranking": 0.0, "intent": 0.0, "samples": 0}
        for start in range(0, train_cache.sample_count, batch_size):
            indices = order[start : start + batch_size]
            features, mask, selected, candidate_intents = hierarchical_padded_batch(
                train_cache,
                indices,
            )
            output = model(
                torch.as_tensor(features, device=device),
                torch.as_tensor(mask, device=device),
                torch.as_tensor(candidate_intents, device=device),
            )
            losses = hierarchical_intent_ranking_loss(
                output,
                selected_indices=torch.as_tensor(selected, device=device),
                candidate_intents=torch.as_tensor(candidate_intents, device=device),
                class_weights=class_weights,
                intent_auxiliary_loss_weight=auxiliary_weight,
            )
            optimizer.zero_grad(set_to_none=True)
            losses["composite_loss"].backward()
            optimizer.step()
            count = len(indices)
            totals["samples"] += count
            totals["composite"] += float(losses["composite_loss"].detach()) * count
            totals["ranking"] += float(losses["ranking_loss"].detach()) * count
            totals["intent"] += float(losses["intent_auxiliary_loss"].detach()) * count
        validation_losses = evaluate_hierarchical_loss(
            model,
            validation_cache,
            batch_size=evaluation_batch_size,
            class_weights=class_weights,
            intent_auxiliary_loss_weight=auxiliary_weight,
            device=device,
        )
        epoch_report = {
            "epoch": epoch_index + 1,
            "train_composite_loss": totals["composite"] / totals["samples"],
            "train_ranking_loss": totals["ranking"] / totals["samples"],
            "train_intent_auxiliary_loss": totals["intent"] / totals["samples"],
            **{f"validation_{name}": value for name, value in validation_losses.items()},
            "train_samples_seen_once": train_cache.sample_count,
        }
        epochs.append(epoch_report)
        candidate_loss = float(validation_losses["composite_loss"])
        if candidate_loss < best_loss - tolerance:
            best_loss = candidate_loss
            best_epoch = epoch_index + 1
            best_state = {
                name: tensor.detach().cpu().clone()
                for name, tensor in model.state_dict().items()
            }
    if best_state is None:
        raise RuntimeError("A3 v3 training did not produce a best checkpoint")
    model.load_state_dict(best_state, strict=True)
    model.eval()

    logits, selected = collect_hierarchical_candidate_logits(
        model,
        validation_cache,
        batch_size=evaluation_batch_size,
        device=device,
    )
    calibration_config = development["calibration"]
    calibration = fit_validation_temperature(
        logits,
        selected,
        minimum=float(calibration_config["temperature_minimum"]),
        maximum=float(calibration_config["temperature_maximum"]),
        grid_size=int(calibration_config["temperature_grid_size"]),
    )
    metrics = metrics_from_candidate_logits(
        validation_cache,
        logits,
        selected,
        mappings=cache_manifest["mappings"],
        temperature=float(calibration["temperature"]),
        calibration_bin_count=int(calibration_config["ece_bin_count"]),
        confidence_floor=float(development["proposal_confidence_floor"]),
    )
    validation_gate = assess_metric_gate(
        metrics,
        protocol.payload["gates"]["validation"],
    )
    training_report = {
        "method": "hierarchical_intent_plus_legal_candidate_ranking",
        "configuration_count": 1,
        "hyperparameter_search": False,
        "repeat_on_failure": False,
        "train_split_only_for_gradients_features_and_class_weights": True,
        "validation_split_only_for_epoch_calibration_and_development_gate": True,
        "test_or_future_held_out_access": False,
        "ppo_started": False,
        "class_balance": weight_profile,
        "best_epoch": best_epoch,
        "best_validation_composite_loss": best_loss,
        "best_epoch_tie_break": "earliest_epoch",
        "epochs": epochs,
        "calibration": calibration,
        "validation_metrics": metrics,
        "validation_gate": validation_gate,
        "rule_fallback_required": True,
        "authority": authority_false_contract(),
    }
    return model, calibration, training_report


def evaluate_hierarchical_loss(
    model: HierarchicalIntentLegalCandidateRanker,
    cache: ActiveVisionBcSplitCache,
    *,
    batch_size: int,
    class_weights: torch.Tensor,
    intent_auxiliary_loss_weight: float,
    device: torch.device,
) -> dict[str, float]:
    if batch_size <= 0:
        raise ValueError("A3 v3 evaluation batch size must be positive")
    totals = {"composite_loss": 0.0, "ranking_loss": 0.0, "intent_auxiliary_loss": 0.0}
    model.eval()
    with torch.no_grad():
        for start in range(0, cache.sample_count, batch_size):
            indices = np.arange(start, min(start + batch_size, cache.sample_count))
            features, mask, selected, candidate_intents = hierarchical_padded_batch(
                cache,
                indices,
            )
            output = model(
                torch.as_tensor(features, device=device),
                torch.as_tensor(mask, device=device),
                torch.as_tensor(candidate_intents, device=device),
            )
            losses = hierarchical_intent_ranking_loss(
                output,
                selected_indices=torch.as_tensor(selected, device=device),
                candidate_intents=torch.as_tensor(candidate_intents, device=device),
                class_weights=class_weights,
                intent_auxiliary_loss_weight=intent_auxiliary_loss_weight,
            )
            for name in totals:
                totals[name] += float(losses[name]) * len(indices)
    return {name: value / cache.sample_count for name, value in totals.items()}


def collect_hierarchical_candidate_logits(
    model: HierarchicalIntentLegalCandidateRanker,
    cache: ActiveVisionBcSplitCache,
    *,
    batch_size: int,
    device: torch.device,
) -> tuple[np.ndarray, np.ndarray]:
    counts = np.asarray(cache.files["candidate_count"], dtype=np.int64)
    if len(counts) != cache.sample_count or np.any(counts <= 0):
        raise ValueError("A3 v3 candidate counts are invalid")
    maximum = int(np.max(counts))
    logits = np.full((cache.sample_count, maximum), -np.inf, dtype=np.float32)
    selected = np.asarray(cache.files["selected_index"], dtype=np.int64).copy()
    model.eval()
    with torch.no_grad():
        for start in range(0, cache.sample_count, batch_size):
            indices = np.arange(start, min(start + batch_size, cache.sample_count))
            features, mask, _, candidate_intents = hierarchical_padded_batch(cache, indices)
            output = model(
                torch.as_tensor(features, device=device),
                torch.as_tensor(mask, device=device),
                torch.as_tensor(candidate_intents, device=device),
            )
            values = output.candidate_logits.cpu().numpy()
            logits[start : start + len(indices), : values.shape[1]] = values
    return logits, selected


def metrics_from_candidate_logits(
    cache: ActiveVisionBcSplitCache,
    logits: np.ndarray,
    selected_indices: np.ndarray,
    *,
    mappings: Mapping[str, Any],
    temperature: float,
    calibration_bin_count: int,
    confidence_floor: float,
) -> dict[str, Any]:
    values = np.asarray(logits, dtype=np.float64)
    selected = np.asarray(selected_indices, dtype=np.int64)
    if values.shape[0] != cache.sample_count or selected.shape != (
        cache.sample_count,
    ):
        raise ValueError("A3 v3 evaluation logits are misaligned")
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise ValueError("A3 v3 calibrated temperature must be positive")
    scaled = values / temperature
    predictions = np.argmax(scaled, axis=1).astype(np.int64)
    row_maximum = np.max(scaled, axis=1)
    valid = np.isfinite(scaled)
    denominator = np.sum(
        np.where(valid, np.exp(scaled - row_maximum[:, None]), 0.0),
        axis=1,
    )
    confidences = 1.0 / denominator
    selected_logits = scaled[np.arange(cache.sample_count), selected]
    nll = float(np.mean(row_maximum + np.log(denominator) - selected_logits))
    metrics = action_metrics(
        cache,
        predictions,
        mappings=mappings,
        loss=nll,
        confidences=confidences,
        out_of_distribution=None,
        calibration_bin_count=calibration_bin_count,
    )
    metrics["proposal_coverage"] = {
        "confidence_floor": confidence_floor,
        "eligible_sample_count": int(np.sum(confidences >= confidence_floor)),
        "eligible_fraction": float(np.mean(confidences >= confidence_floor)),
        "below_floor_action_credit_used": False,
        "fallback": "deterministic_rule",
    }
    return metrics


def hierarchical_padded_batch(
    cache: ActiveVisionBcSplitCache,
    indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    sample_indices = np.asarray(indices, dtype=np.int64).reshape(-1)
    if not len(sample_indices):
        raise ValueError("A3 v3 batch cannot be empty")
    if np.any(sample_indices < 0) or np.any(sample_indices >= cache.sample_count):
        raise ValueError("A3 v3 sample index is out of range")
    counts = np.asarray(cache.files["candidate_count"][sample_indices], dtype=np.int64)
    selected = np.asarray(cache.files["selected_index"][sample_indices], dtype=np.int64)
    if np.any(counts <= 0) or np.any(selected < 0) or np.any(selected >= counts):
        raise ValueError("A3 v3 candidate count or selected index is invalid")
    maximum = int(np.max(counts))
    features = np.zeros(
        (len(sample_indices), maximum, cache.feature_dim),
        dtype=np.float32,
    )
    mask = np.zeros((len(sample_indices), maximum), dtype=bool)
    intents = np.zeros((len(sample_indices), maximum), dtype=np.int64)
    feature_source = cache.files["features"]
    intent_source = cache.files["candidate_intent"]
    for row, (sample_index, count) in enumerate(zip(sample_indices, counts, strict=True)):
        start = int(cache.offsets[sample_index])
        stop = start + int(count)
        features[row, :count] = feature_source[start:stop]
        intents[row, :count] = intent_source[start:stop]
        mask[row, :count] = True
    return features, mask, selected, intents


def selected_intent_codes(cache: ActiveVisionBcSplitCache) -> np.ndarray:
    selected = np.asarray(cache.files["selected_index"], dtype=np.int64)
    counts = np.asarray(cache.files["candidate_count"], dtype=np.int64)
    if np.any(counts <= 0) or np.any(selected < 0) or np.any(selected >= counts):
        raise ValueError("A3 v3 selected candidate indices are invalid")
    rows = cache.offsets[:-1] + selected
    values = np.asarray(cache.files["candidate_intent"][rows], dtype=np.int64)
    if np.any(values < 0) or np.any(values >= len(A3_V3_INTENTS)):
        raise ValueError("A3 v3 selected intent codes are invalid")
    return values


def protocol_status_report(protocol: FrozenA3V3Protocol) -> dict[str, Any]:
    return {
        "schema_version": ACTIVE_VISION_A3_V3_DEVELOPMENT_REPORT_SCHEMA_VERSION,
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.sha256,
        "status": ACTIVE_VISION_A3_V3_DEFAULT_STATUS,
        "data_generated": False,
        "training_started": False,
        "weights_written": False,
        "test_or_future_held_out_access": False,
        "episode_payload_read_count": 0,
        "ppo_started": False,
        "shadow": False,
        "assist": False,
        "camera_command": False,
        "rule_fallback_required": True,
        "authority": authority_false_contract(),
    }


def run_a3_v3_training_entry(
    protocol_path: str | Path,
    *,
    source_manifest_path: str | Path | None = None,
    development_cache_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    execute_training: bool = False,
) -> dict[str, Any]:
    """Validate the frozen protocol or execute one future development run."""

    protocol = load_frozen_a3_v3_protocol(protocol_path)
    if source_manifest_path is None:
        if execute_training or development_cache_dir is not None or output_dir is not None:
            raise ValueError("A3 v3 new source manifest is required before training")
        return protocol_status_report(protocol)

    source_manifest, source_evidence = load_and_validate_a3_v3_source_manifest(
        protocol,
        source_manifest_path,
    )
    if not execute_training:
        if development_cache_dir is not None or output_dir is not None:
            raise ValueError("A3 v3 cache/output arguments require --execute-training")
        return {
            **protocol_status_report(protocol),
            "status": "source_contract_ready_training_not_started",
            "data_generated": True,
            "source_manifest_sha256": source_evidence["source_manifest_sha256"],
        }
    if development_cache_dir is None or output_dir is None:
        raise ValueError("A3 v3 training requires development cache and output directory")

    cache_manifest, caches, cache_manifest_sha256 = load_a3_v3_development_cache(
        development_cache_dir,
        protocol=protocol,
        source_manifest=source_manifest,
        source_evidence=source_evidence,
    )
    output_root = Path(output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"A3 v3 output directory is not empty: {output_root}")

    model, calibration, training_report = train_a3_v3_hierarchical_model(
        cache_manifest,
        caches,
        protocol=protocol,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    weights_path = output_root / ACTIVE_VISION_A3_V3_WEIGHTS_FILENAME
    weights_payload = {
        "schema_version": ACTIVE_VISION_A3_V3_DEVELOPMENT_REPORT_SCHEMA_VERSION,
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.sha256,
        "source_manifest_sha256": source_evidence["source_manifest_sha256"],
        "development_cache_manifest_sha256": cache_manifest_sha256,
        "model_class": "HierarchicalIntentLegalCandidateRanker",
        "model_state_dict": model.state_dict(),
        "calibration": calibration,
        "runtime_profile": "development_only_no_runtime_loader",
        "rule_fallback_required": True,
        "authority": authority_false_contract(),
    }
    _torch_save_atomic(weights_path, weights_payload)
    weights_sha256 = _sha256_file(weights_path)
    calibration_sha256 = _sha256_json(calibration)
    report = {
        "schema_version": ACTIVE_VISION_A3_V3_DEVELOPMENT_REPORT_SCHEMA_VERSION,
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.sha256,
        "source_manifest_sha256": source_evidence["source_manifest_sha256"],
        "development_cache_manifest_sha256": cache_manifest_sha256,
        "status": (
            "development_validation_passed_model_frozen_future_gate_unopened"
            if training_report["validation_gate"]["passed"]
            else "development_validation_failed_closed"
        ),
        "validation_gate_passed": bool(training_report["validation_gate"]["passed"]),
        "model_frozen": True,
        "weights_sha256": weights_sha256,
        "calibration_sha256": calibration_sha256,
        "test_or_future_held_out_used_during_development": False,
        "future_held_out_access_count": 0,
        "future_held_out_selection_feedback_allowed": False,
        "training": training_report,
        "ppo_started": False,
        "shadow": False,
        "assist": False,
        "camera_command": False,
        "rule_fallback_required": True,
        "authority": authority_false_contract(),
    }
    _write_json_atomic(output_root / ACTIVE_VISION_A3_V3_REPORT_FILENAME, report)
    return report


def _validate_cache_support(
    caches: Mapping[str, ActiveVisionBcSplitCache],
    *,
    mappings: Mapping[str, Any],
) -> None:
    intent_mapping = mappings["intent"]
    camera_mapping = mappings["camera_type"]
    for split in _DEVELOPMENT_SPLITS:
        cache = caches[split]
        labels = selected_intent_codes(cache)
        missing_intents = [
            intent
            for intent in A3_V3_INTENTS
            if int(np.sum(labels == int(intent_mapping[intent]))) == 0
        ]
        if missing_intents:
            raise ValueError(
                f"A3 v3 {split} cache is missing minority intents: {missing_intents}"
            )
        camera_codes = np.asarray(cache.files["camera_type"], dtype=np.int64)
        missing_roles = [
            role
            for role in A3_V3_CAMERA_ROLES
            if int(np.sum(camera_codes == int(camera_mapping[role]))) == 0
        ]
        if missing_roles:
            raise ValueError(
                f"A3 v3 {split} cache is missing camera roles: {missing_roles}"
            )


def _require_available_metric(metric: Mapping[str, Any], label: str) -> None:
    if not metric.get("available", False) or metric.get("value") is None:
        raise ValueError(f"A3 v3 {label} is unavailable")


def _set_fixed_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def _torch_save_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        torch.save(dict(payload), temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        _json_ready(payload),
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(raw)
        temporary = Path(handle.name)
    temporary.replace(path)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to load A3 v3 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"A3 v3 JSON object expected: {path}")
    return payload


def _expect_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields mismatch")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        _json_ready(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--source-manifest")
    parser.add_argument("--development-cache-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--execute-training", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_a3_v3_training_entry(
        args.protocol,
        source_manifest_path=args.source_manifest,
        development_cache_dir=args.development_cache_dir,
        output_dir=args.output_dir,
        execute_training=args.execute_training,
    )
    print(json.dumps(_json_ready(report), sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "ACTIVE_VISION_A3_V3_DEVELOPMENT_CACHE_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_V3_DEVELOPMENT_REPORT_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_V3_REPORT_FILENAME",
    "ACTIVE_VISION_A3_V3_WEIGHTS_FILENAME",
    "HierarchicalIntentLegalCandidateRanker",
    "HierarchicalIntentRankerOutput",
    "assess_metric_gate",
    "bounded_class_balanced_intent_weights",
    "collect_hierarchical_candidate_logits",
    "evaluate_hierarchical_loss",
    "fit_validation_temperature",
    "hierarchical_intent_ranking_loss",
    "hierarchical_padded_batch",
    "load_a3_v3_development_cache",
    "metrics_from_candidate_logits",
    "protocol_status_report",
    "run_a3_v3_training_entry",
    "selected_intent_codes",
    "train_a3_v3_hierarchical_model",
]
