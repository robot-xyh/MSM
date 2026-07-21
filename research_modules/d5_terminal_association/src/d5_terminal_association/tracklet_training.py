"""Formal multi-graph training, calibration, evaluation, and CLI for D5."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import platform
import random
import sys
import time
from typing import Any, Mapping, Sequence

import numpy as np
import torch
from torch.nn import functional as F

from .tracklet_dataset import (
    LoadedTrackletDataset,
    LoadedTrackletEpisode,
    edge_targets,
    load_tracklet_dataset,
    sha256_json,
)
from .tracklet_gnn import NativeTrackletEdgeClassifier
from .tracklet_model_bundle import (
    load_tracklet_model_bundle,
    write_tracklet_model_bundle,
)


TRAINING_REPORT_SCHEMA_VERSION = "d5.tracklet-training-report.v1"
EVALUATION_REPORT_SCHEMA_VERSION = "d5.tracklet-evaluation-report.v1"


@dataclass(frozen=True)
class TrackletTrainingConfig:
    seed: int = 20260720
    epochs: int = 50
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-5
    hidden_dim: int = 32
    message_passing_steps: int = 2
    dropout: float = 0.0
    graphs_per_optimizer_step: int = 4
    hard_negative_ratio: float = 3.0
    max_hard_negatives_without_positive: int = 64
    ece_bins: int = 10
    latency_repeats: int = 3
    device: str = "cpu"

    def __post_init__(self) -> None:
        if self.epochs <= 0 or self.hidden_dim <= 0 or self.message_passing_steps <= 0:
            raise ValueError("epochs, hidden_dim, and message_passing_steps must be positive")
        if self.learning_rate <= 0.0 or self.weight_decay < 0.0:
            raise ValueError("learning_rate must be positive and weight_decay non-negative")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if self.graphs_per_optimizer_step <= 0:
            raise ValueError("graphs_per_optimizer_step must be positive")
        if self.hard_negative_ratio < 0.0 or self.max_hard_negatives_without_positive <= 0:
            raise ValueError("hard-negative settings are invalid")
        if self.ece_bins <= 0 or self.latency_repeats <= 0:
            raise ValueError("ece_bins and latency_repeats must be positive")
        torch.device(self.device)


@dataclass(frozen=True)
class TrackletTrainingResult:
    model: NativeTrackletEdgeClassifier
    epoch_losses: tuple[float, ...]
    validation_losses: tuple[float, ...]
    best_epoch: int
    selected_positive_edges: int
    selected_negative_edges: int
    selected_hard_negative_edges: int


def train_tracklet_edge_model(
    dataset: LoadedTrackletDataset,
    config: TrackletTrainingConfig,
    *,
    allow_partial_validation_truth: bool = False,
) -> TrackletTrainingResult:
    """Train with deterministic whole-graph gradient accumulation."""

    train_episodes = dataset.split("train")
    validation_episodes = dataset.split("validation")
    if not train_episodes or not validation_episodes:
        raise ValueError("training and validation splits must both contain episodes")
    _require_binary_validation(
        validation_episodes,
        allow_partial_truth=allow_partial_validation_truth,
    )
    _set_fixed_seed(config.seed)
    device = torch.device(config.device)
    model = NativeTrackletEdgeClassifier(
        hidden_dim=config.hidden_dim,
        message_passing_steps=config.message_passing_steps,
        dropout=config.dropout,
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    training_batches = {
        episode.graph.episode_uid: _selected_training_arrays(episode, config)
        for episode in train_episodes
    }
    selected_positive = sum(batch[2] for batch in training_batches.values())
    selected_negative = sum(batch[3] for batch in training_batches.values())
    if selected_positive + selected_negative == 0:
        raise ValueError("training split contains no labeled candidate edges")

    epoch_losses: list[float] = []
    validation_losses: list[float] = []
    best_loss = math.inf
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    for epoch in range(config.epochs):
        model.train()
        ordered = list(train_episodes)
        random.Random(config.seed + epoch).shuffle(ordered)
        per_graph_losses: list[float] = []
        for start in range(0, len(ordered), config.graphs_per_optimizer_step):
            chunk = ordered[start : start + config.graphs_per_optimizer_step]
            losses: list[torch.Tensor] = []
            optimizer.zero_grad(set_to_none=True)
            for episode in chunk:
                targets_np, mask_np, positive_count, negative_count = training_batches[
                    episode.graph.episode_uid
                ]
                if positive_count + negative_count == 0:
                    continue
                node_features, edge_index, edge_features = _graph_tensors(episode, device)
                targets = torch.as_tensor(
                    np.array(targets_np, copy=True), dtype=torch.float32, device=device
                )
                mask = torch.as_tensor(
                    np.array(mask_np, copy=True), dtype=torch.bool, device=device
                )
                positive_weight = (
                    max(1.0, negative_count / positive_count) if positive_count else 1.0
                )
                logits = model.edge_logits(node_features, edge_index, edge_features)
                losses.append(
                    F.binary_cross_entropy_with_logits(
                        logits[mask],
                        targets[mask],
                        pos_weight=torch.tensor(positive_weight, dtype=torch.float32, device=device),
                    )
                )
            if not losses:
                continue
            chunk_loss = torch.stack(losses).mean()
            if not bool(torch.isfinite(chunk_loss)):
                raise RuntimeError("non-finite training loss")
            chunk_loss.backward()
            optimizer.step()
            per_graph_losses.extend(float(loss.detach().cpu()) for loss in losses)
        if not per_graph_losses:
            raise ValueError("no trainable graph remained after hard-negative selection")
        epoch_loss = float(np.mean(per_graph_losses))
        validation_loss = _binary_cross_entropy_on_split(model, validation_episodes, device)
        epoch_losses.append(epoch_loss)
        validation_losses.append(validation_loss)
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_epoch = epoch + 1
            best_state = {
                key: value.detach().cpu().clone() for key, value in model.state_dict().items()
            }
    if best_state is None:
        raise RuntimeError("training did not produce a finite validation checkpoint")
    model.load_state_dict(best_state, strict=True)
    model.to(device)
    model.eval()
    return TrackletTrainingResult(
        model=model,
        epoch_losses=tuple(epoch_losses),
        validation_losses=tuple(validation_losses),
        best_epoch=best_epoch,
        selected_positive_edges=selected_positive,
        selected_negative_edges=selected_negative,
        selected_hard_negative_edges=selected_negative,
    )


def fit_validation_temperature(logits: np.ndarray, targets: np.ndarray) -> float:
    """Fit one deterministic scalar temperature using validation labels only."""

    values = np.asarray(logits, dtype=np.float64).reshape(-1)
    expected = np.asarray(targets, dtype=np.float64).reshape(-1)
    if values.shape != expected.shape or not values.size:
        raise ValueError("validation logits and targets must be non-empty and aligned")
    if not np.all(np.isfinite(values)) or not np.all(np.isin(expected, (0.0, 1.0))):
        raise ValueError("validation calibration inputs are invalid")
    if len(np.unique(expected)) < 2:
        raise ValueError("temperature calibration requires both validation classes")
    candidates = np.exp(np.linspace(math.log(0.05), math.log(20.0), 241))
    best_temperature = 1.0
    best_loss = math.inf
    for candidate in candidates:
        scaled = values / float(candidate)
        loss = float(np.mean(np.logaddexp(0.0, scaled) - expected * scaled))
        if loss < best_loss:
            best_loss = loss
            best_temperature = float(candidate)
    return best_temperature


def select_validation_threshold(probabilities: np.ndarray, targets: np.ndarray) -> float:
    """Choose a validation-only F1 threshold with precision-first tie breaking."""

    values = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    expected = np.asarray(targets, dtype=np.int64).reshape(-1)
    if values.shape != expected.shape or not values.size:
        raise ValueError("validation probabilities and targets must be non-empty and aligned")
    if not np.all(np.isfinite(values)) or np.any((values < 0.0) | (values > 1.0)):
        raise ValueError("validation probabilities must be finite and in [0, 1]")
    positive_total = int(np.sum(expected == 1))
    negative_total = int(np.sum(expected == 0))
    if positive_total == 0 or negative_total == 0:
        raise ValueError("threshold selection requires both validation classes")
    order = np.argsort(-values, kind="stable")
    sorted_probabilities = values[order]
    sorted_targets = expected[order]
    true_positive = 0
    false_positive = 0
    best_key = (-1.0, -1.0, -1.0)
    best_threshold = 0.5
    for index, target in enumerate(sorted_targets):
        if target == 1:
            true_positive += 1
        else:
            false_positive += 1
        at_group_end = index + 1 == len(sorted_targets) or (
            sorted_probabilities[index + 1] != sorted_probabilities[index]
        )
        if not at_group_end:
            continue
        false_negative = positive_total - true_positive
        precision = true_positive / (true_positive + false_positive)
        recall = true_positive / (true_positive + false_negative)
        f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
        threshold = float(sorted_probabilities[index])
        key = (f1, precision, threshold)
        if key > best_key:
            best_key = key
            best_threshold = threshold
    return best_threshold


def evaluate_tracklet_edge_model(
    dataset: LoadedTrackletDataset,
    model: NativeTrackletEdgeClassifier,
    *,
    split: str,
    temperature: float,
    decision_threshold: float,
    device: torch.device | str = "cpu",
    ece_bins: int = 10,
    latency_repeats: int = 3,
    model_size_bytes: int | None = None,
    allow_partial_truth_metrics: bool = False,
) -> dict[str, Any]:
    """Evaluate one split and preserve unavailable metrics as null, never zero."""

    episodes = dataset.split(split)
    if not episodes:
        raise ValueError(f"{split} split contains no episodes")
    target_device = torch.device(device)
    model.to(target_device)
    model.eval()
    temperature_value = float(temperature)
    threshold = float(decision_threshold)
    if not np.isfinite(temperature_value) or temperature_value <= 0.0:
        raise ValueError("temperature must be finite and positive")
    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("decision_threshold must be in [0, 1]")
    if ece_bins <= 0 or latency_repeats <= 0:
        raise ValueError("ece_bins and latency_repeats must be positive")

    all_probabilities: list[np.ndarray] = []
    all_targets: list[np.ndarray] = []
    latency_ms: list[float] = []
    complete_truth = all(
        episode.evaluator_labels.labels_complete for episode in episodes
    )
    with torch.no_grad():
        for episode in episodes:
            node_features, edge_index, edge_features = _graph_tensors(episode, target_device)
            logits = model.edge_logits(node_features, edge_index, edge_features)
            probabilities = torch.sigmoid(logits / temperature_value)
            values = probabilities.detach().cpu().numpy().astype(np.float64, copy=False)
            if not np.all(np.isfinite(values)):
                raise RuntimeError("model produced non-finite evaluation probabilities")
            targets, eligible = edge_targets(episode)
            all_probabilities.append(values[eligible])
            all_targets.append(np.asarray(targets[eligible], dtype=np.float64))
            for _ in range(latency_repeats):
                _synchronize_if_cuda(target_device)
                started = time.perf_counter()
                measured_logits = model.edge_logits(node_features, edge_index, edge_features)
                measured_probabilities = torch.sigmoid(measured_logits / temperature_value)
                _synchronize_if_cuda(target_device)
                elapsed = (time.perf_counter() - started) * 1000.0
                if not bool(torch.all(torch.isfinite(measured_probabilities))):
                    raise RuntimeError("model produced non-finite timed probabilities")
                latency_ms.append(elapsed)

    probabilities = np.concatenate(all_probabilities) if all_probabilities else np.empty(0)
    targets = np.concatenate(all_targets) if all_targets else np.empty(0)
    if not complete_truth and not allow_partial_truth_metrics:
        truth_metrics = {
            name: _unavailable("incomplete_evaluator_truth")
            for name in (
                "precision",
                "recall",
                "f1",
                "false_merge_rate",
                "candidate_recall",
                "brier_score",
                "ece",
            )
        }
        truth_scope = "unavailable_incomplete_evaluator_truth"
    elif not targets.size:
        truth_metrics = {
            name: _unavailable("no_labeled_candidate_edges")
            for name in (
                "precision",
                "recall",
                "f1",
                "false_merge_rate",
                "candidate_recall",
                "brier_score",
                "ece",
            )
        }
        truth_scope = "unavailable_no_labeled_candidate_edges"
    elif not complete_truth:
        truth_metrics = _labeled_edge_metrics(
            probabilities,
            targets,
            threshold=threshold,
            ece_bins=ece_bins,
        )
        truth_scope = "labeled_candidate_edges_only"
    else:
        truth_metrics = _edge_and_cluster_metrics(
            episodes,
            probabilities,
            targets,
            threshold=threshold,
            ece_bins=ece_bins,
        )
        truth_scope = "complete_graph_truth"
    latency_values = np.asarray(latency_ms, dtype=np.float64)
    latency_metrics = {
        "p50_inference_latency_ms": _available(float(np.percentile(latency_values, 50))),
        "p95_inference_latency_ms": _available(float(np.percentile(latency_values, 95))),
    }
    size_metric = (
        _available(int(model_size_bytes), unit="bytes")
        if model_size_bytes is not None
        else _unavailable("bundle_not_written")
    )
    return {
        "split": split,
        "episode_count": len(episodes),
        "complete_truth": complete_truth,
        "truth_scope": truth_scope,
        "labeled_candidate_edge_count": int(targets.size),
        "decision_threshold": threshold,
        "temperature": temperature_value,
        "metrics": {
            **truth_metrics,
            **latency_metrics,
            "model_size": size_metric,
        },
    }


def run_training_pipeline(
    dataset_dir: str | Path,
    bundle_dir: str | Path,
    report_path: str | Path,
    *,
    config: TrackletTrainingConfig | None = None,
    development_only: bool = False,
    readiness_audit_sha256: str | None = None,
) -> Mapping[str, Any]:
    """Train, calibrate, bundle, strict-reload, and evaluate once.

    The default formal path still requires complete validation truth.  The
    explicit development-only path may calibrate on labeled candidate edges,
    but its bundle is permanently marked ineligible for G1/assist.
    """

    cfg = config or TrackletTrainingConfig()
    if development_only and readiness_audit_sha256 is None:
        raise ValueError("development-only training requires readiness_audit_sha256")
    if not development_only and readiness_audit_sha256 is not None:
        raise ValueError("formal training must not attach a development readiness audit")
    pipeline_started = time.perf_counter()
    dataset = load_tracklet_dataset(dataset_dir)
    training_started = time.perf_counter()
    training = train_tracklet_edge_model(
        dataset,
        cfg,
        allow_partial_validation_truth=development_only,
    )
    training_elapsed_seconds = time.perf_counter() - training_started
    validation_logits, validation_targets = _split_logits_and_targets(
        training.model,
        dataset.split("validation"),
        torch.device(cfg.device),
    )
    temperature = fit_validation_temperature(validation_logits, validation_targets)
    validation_probabilities = _sigmoid_numpy(validation_logits / temperature)
    threshold = select_validation_threshold(validation_probabilities, validation_targets)
    validation_results = evaluate_tracklet_edge_model(
        dataset,
        training.model,
        split="validation",
        temperature=temperature,
        decision_threshold=threshold,
        device=cfg.device,
        ece_bins=cfg.ece_bins,
        latency_repeats=cfg.latency_repeats,
        allow_partial_truth_metrics=development_only,
    )
    training_config_payload = asdict(cfg)
    training_config_sha256 = sha256_json(training_config_payload)
    admission_status = (
        "development_only_fail_closed"
        if development_only
        else "research_candidate_not_default"
    )
    write_tracklet_model_bundle(
        bundle_dir,
        training.model,
        dataset_manifest_sha256=dataset.manifest_sha256,
        split_sha256=str(dataset.manifest["split_sha256"]),
        training_set_sha256=str(dataset.manifest["training_set_sha256"]),
        training_config_sha256=training_config_sha256,
        calibration_temperature=temperature,
        decision_threshold=threshold,
        validation_results=validation_results,
        admission_status=admission_status,
        readiness_audit_sha256=readiness_audit_sha256,
    )
    scorer = load_tracklet_model_bundle(
        bundle_dir,
        device=cfg.device,
        expected_dataset_manifest_sha256=dataset.manifest_sha256,
        expected_split_sha256=str(dataset.manifest["split_sha256"]),
        expected_training_set_sha256=str(dataset.manifest["training_set_sha256"]),
        expected_readiness_audit_sha256=readiness_audit_sha256,
    )
    weights_size = Path(bundle_dir, "weights.pt").stat().st_size
    train_results = evaluate_tracklet_edge_model(
        dataset,
        scorer.model,
        split="train",
        temperature=scorer.temperature,
        decision_threshold=scorer.decision_threshold,
        device=cfg.device,
        ece_bins=cfg.ece_bins,
        latency_repeats=cfg.latency_repeats,
        model_size_bytes=weights_size,
        allow_partial_truth_metrics=development_only,
    )
    test_results = evaluate_tracklet_edge_model(
        dataset,
        scorer.model,
        split="test",
        temperature=scorer.temperature,
        decision_threshold=scorer.decision_threshold,
        device=cfg.device,
        ece_bins=cfg.ece_bins,
        latency_repeats=cfg.latency_repeats,
        model_size_bytes=weights_size,
        allow_partial_truth_metrics=development_only,
    )
    final_loss_by_split = {
        split: _binary_cross_entropy_on_split(
            scorer.model,
            dataset.split(split),
            torch.device(cfg.device),
        )
        for split in ("train", "validation", "test")
    }
    report = {
        "schema_version": TRAINING_REPORT_SCHEMA_VERSION,
        "admission_status": admission_status,
        "g1_assist_eligible": False,
        "readiness_audit_sha256": readiness_audit_sha256,
        "dataset": {
            "manifest_sha256": dataset.manifest_sha256,
            "split_sha256": dataset.manifest["split_sha256"],
            "training_set_sha256": dataset.manifest["training_set_sha256"],
            "config_sha256": dataset.manifest["config_sha256"],
        },
        "training": {
            "config": training_config_payload,
            "config_sha256": training_config_sha256,
            "best_epoch": training.best_epoch,
            "epoch_losses": list(training.epoch_losses),
            "validation_losses": list(training.validation_losses),
            "selected_positive_edges": training.selected_positive_edges,
            "selected_negative_edges": training.selected_negative_edges,
            "selected_hard_negative_edges": training.selected_hard_negative_edges,
            "hard_negative_provenance": dataset.manifest["hard_negative_provenance"],
            "training_elapsed_seconds": training_elapsed_seconds,
            "final_loss_by_split": final_loss_by_split,
        },
        "calibration": {
            "source_split": "validation",
            "temperature": temperature,
            "decision_threshold": threshold,
            "threshold_objective": "validation_f1",
        },
        "train": train_results,
        "validation": validation_results,
        "test": test_results,
        "bundle": {
            "directory": str(Path(bundle_dir)),
            "manifest_sha256": scorer.bundle_manifest_sha256,
            "weights_sha256": scorer.bundle_weights_sha256,
            "implementation_sha256": scorer.manifest["code_provenance"][
                "implementation_sha256"
            ],
        },
        "hardware": _hardware_summary(cfg.device),
        "pipeline_elapsed_seconds": time.perf_counter() - pipeline_started,
    }
    _write_json_atomic(Path(report_path), report)
    return report


def run_evaluation_pipeline(
    dataset_dir: str | Path,
    bundle_dir: str | Path,
    report_path: str | Path,
    *,
    split: str = "test",
    device: str = "cpu",
    ece_bins: int = 10,
    latency_repeats: int = 3,
) -> Mapping[str, Any]:
    dataset = load_tracklet_dataset(dataset_dir)
    scorer = load_tracklet_model_bundle(
        bundle_dir,
        device=device,
        expected_dataset_manifest_sha256=dataset.manifest_sha256,
        expected_split_sha256=str(dataset.manifest["split_sha256"]),
        expected_training_set_sha256=str(dataset.manifest["training_set_sha256"]),
    )
    development_only = (
        scorer.manifest["admission"]["status"] == "development_only_fail_closed"
    )
    evaluation = evaluate_tracklet_edge_model(
        dataset,
        scorer.model,
        split=split,
        temperature=scorer.temperature,
        decision_threshold=scorer.decision_threshold,
        device=device,
        ece_bins=ece_bins,
        latency_repeats=latency_repeats,
        model_size_bytes=Path(bundle_dir, "weights.pt").stat().st_size,
        allow_partial_truth_metrics=development_only,
    )
    report = {
        "schema_version": EVALUATION_REPORT_SCHEMA_VERSION,
        "dataset_manifest_sha256": dataset.manifest_sha256,
        "bundle_manifest_sha256": scorer.bundle_manifest_sha256,
        "bundle_weights_sha256": scorer.bundle_weights_sha256,
        "evaluation": evaluation,
    }
    _write_json_atomic(Path(report_path), report)
    return report


def _selected_training_arrays(
    episode: LoadedTrackletEpisode,
    config: TrackletTrainingConfig,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    targets, eligible = edge_targets(episode)
    positive_indices = np.flatnonzero(eligible & (targets >= 0.5)).tolist()
    negative_indices = np.flatnonzero(eligible & (targets < 0.5)).tolist()
    ordered_negatives = sorted(
        negative_indices,
        key=lambda index: (float(episode.graph.gate_scores[index]), index),
    )
    if positive_indices:
        negative_limit = int(math.ceil(len(positive_indices) * config.hard_negative_ratio))
        if config.hard_negative_ratio > 0.0:
            negative_limit = max(1, negative_limit)
    else:
        negative_limit = config.max_hard_negatives_without_positive
    selected_negatives = ordered_negatives[:negative_limit]
    mask = np.zeros(episode.graph.edge_count, dtype=bool)
    mask[positive_indices] = True
    mask[selected_negatives] = True
    return targets, mask, len(positive_indices), len(selected_negatives)


def _binary_cross_entropy_on_split(
    model: NativeTrackletEdgeClassifier,
    episodes: Sequence[LoadedTrackletEpisode],
    device: torch.device,
) -> float:
    logits, targets = _split_logits_and_targets(model, episodes, device)
    values = np.logaddexp(0.0, logits) - targets * logits
    loss = float(np.mean(values))
    if not np.isfinite(loss):
        raise RuntimeError("non-finite validation loss")
    return loss


def _split_logits_and_targets(
    model: NativeTrackletEdgeClassifier,
    episodes: Sequence[LoadedTrackletEpisode],
    device: torch.device,
) -> tuple[np.ndarray, np.ndarray]:
    logits_items: list[np.ndarray] = []
    target_items: list[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for episode in episodes:
            targets, eligible = edge_targets(episode)
            node_features, edge_index, edge_features = _graph_tensors(episode, device)
            logits = model.edge_logits(node_features, edge_index, edge_features)
            values = logits.detach().cpu().numpy().astype(np.float64, copy=False)
            logits_items.append(values[eligible])
            target_items.append(np.asarray(targets[eligible], dtype=np.float64))
    logits_array = np.concatenate(logits_items) if logits_items else np.empty(0, dtype=np.float64)
    targets_array = np.concatenate(target_items) if target_items else np.empty(0, dtype=np.float64)
    if not logits_array.size:
        raise ValueError("split contains no labeled candidate edges")
    if not np.all(np.isfinite(logits_array)):
        raise RuntimeError("model produced non-finite logits")
    return logits_array, targets_array


def _require_binary_validation(
    episodes: Sequence[LoadedTrackletEpisode],
    *,
    allow_partial_truth: bool,
) -> None:
    if (
        not allow_partial_truth
        and not all(episode.evaluator_labels.labels_complete for episode in episodes)
    ):
        raise ValueError("formal calibration requires complete validation truth")
    targets = []
    for episode in episodes:
        values, eligible = edge_targets(episode)
        targets.extend(values[eligible].tolist())
    if set(targets) != {0.0, 1.0}:
        prefix = "development" if allow_partial_truth else "formal"
        raise ValueError(f"{prefix} calibration requires positive and negative validation edges")


def _graph_tensors(
    episode: LoadedTrackletEpisode,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    graph = episode.graph
    return (
        torch.as_tensor(np.array(graph.node_features, copy=True), dtype=torch.float32, device=device),
        torch.as_tensor(np.array(graph.edge_index, copy=True), dtype=torch.long, device=device),
        torch.as_tensor(np.array(graph.edge_features, copy=True), dtype=torch.float32, device=device),
    )


def _edge_and_cluster_metrics(
    episodes: Sequence[LoadedTrackletEpisode],
    probabilities: np.ndarray,
    targets: np.ndarray,
    *,
    threshold: float,
    ece_bins: int,
) -> dict[str, Any]:
    predictions = probabilities >= threshold
    expected = targets >= 0.5
    true_positive = int(np.sum(predictions & expected))
    false_positive = int(np.sum(predictions & ~expected))
    false_negative = int(np.sum(~predictions & expected))
    precision_value = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None
    )
    recall_value = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else None
    )
    if precision_value is None or recall_value is None:
        f1_value = None
    elif precision_value + recall_value:
        f1_value = 2.0 * precision_value * recall_value / (precision_value + recall_value)
    else:
        f1_value = 0.0
    false_pairs, merged_pairs = _false_merge_pair_counts(episodes, threshold, probabilities)
    candidate_numerator, candidate_denominator, candidate_available = _candidate_recall_counts(episodes)
    return {
        "precision": (
            _available(precision_value)
            if precision_value is not None
            else _unavailable("no_predicted_positive_edges")
        ),
        "recall": (
            _available(recall_value)
            if recall_value is not None
            else _unavailable("no_positive_candidate_edges")
        ),
        "f1": _available(f1_value) if f1_value is not None else _unavailable("f1_undefined"),
        "false_merge_rate": (
            _available(false_pairs / merged_pairs)
            if merged_pairs
            else _unavailable("no_predicted_merged_pairs")
        ),
        "candidate_recall": (
            _available(candidate_numerator / candidate_denominator)
            if candidate_available and candidate_denominator
            else _unavailable(
                "candidate_recall_not_declared"
                if not candidate_available
                else "no_same_target_cross_camera_pairs"
            )
        ),
        "brier_score": _available(float(np.mean((probabilities - targets) ** 2))),
        "ece": _available(_expected_calibration_error(probabilities, targets, ece_bins)),
    }


def _labeled_edge_metrics(
    probabilities: np.ndarray,
    targets: np.ndarray,
    *,
    threshold: float,
    ece_bins: int,
) -> dict[str, Any]:
    """Report development diagnostics without claiming graph-level completeness."""

    predictions = probabilities >= threshold
    expected = targets >= 0.5
    true_positive = int(np.sum(predictions & expected))
    false_positive = int(np.sum(predictions & ~expected))
    false_negative = int(np.sum(~predictions & expected))
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else None
    )
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else 0.0
        if precision is not None and recall is not None
        else None
    )
    return {
        "precision": _available(precision) if precision is not None else _unavailable(
            "no_predicted_positive_edges"
        ),
        "recall": _available(recall) if recall is not None else _unavailable(
            "no_positive_candidate_edges"
        ),
        "f1": _available(f1) if f1 is not None else _unavailable("f1_undefined"),
        "false_merge_rate": _unavailable("incomplete_graph_truth"),
        "candidate_recall": _unavailable("candidate_recall_not_fully_evaluable"),
        "brier_score": _available(float(np.mean((probabilities - targets) ** 2))),
        "ece": _available(_expected_calibration_error(probabilities, targets, ece_bins)),
    }


def _false_merge_pair_counts(
    episodes: Sequence[LoadedTrackletEpisode],
    threshold: float,
    all_probabilities: np.ndarray,
) -> tuple[int, int]:
    offset = 0
    false_pairs = 0
    merged_pairs = 0
    for episode in episodes:
        edge_count = episode.graph.edge_count
        probabilities = all_probabilities[offset : offset + edge_count]
        offset += edge_count
        if probabilities.shape != (edge_count,):
            raise RuntimeError("evaluation probability alignment failed")
        parent = list(range(episode.graph.node_count))
        cameras = [{episode.graph.camera_keys[index]} for index in range(episode.graph.node_count)]

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        order = sorted(
            range(edge_count),
            key=lambda index: (
                -float(probabilities[index]),
                int(episode.graph.edge_index[0, index]),
                int(episode.graph.edge_index[1, index]),
            ),
        )
        for edge_number in order:
            if probabilities[edge_number] < threshold:
                break
            source = int(episode.graph.edge_index[0, edge_number])
            target = int(episode.graph.edge_index[1, edge_number])
            left = find(source)
            right = find(target)
            if left == right or not cameras[left].isdisjoint(cameras[right]):
                continue
            if left > right:
                left, right = right, left
            parent[right] = left
            cameras[left].update(cameras[right])
        labels = episode.evaluator_labels.by_tracklet_key
        components: dict[int, list[int]] = {}
        for node_index in range(episode.graph.node_count):
            components.setdefault(find(node_index), []).append(node_index)
        for nodes in components.values():
            if len(nodes) < 2:
                continue
            identities = [
                labels[episode.graph.tracklet_keys[index]].truth_entity_id for index in nodes
            ]
            for left_index in range(len(identities)):
                for right_index in range(left_index + 1, len(identities)):
                    merged_pairs += 1
                    false_pairs += int(identities[left_index] != identities[right_index])
    return false_pairs, merged_pairs


def _candidate_recall_counts(
    episodes: Sequence[LoadedTrackletEpisode],
) -> tuple[int, int, bool]:
    if not all(
        episode.evaluator_labels.candidate_recall_available for episode in episodes
    ):
        return 0, 0, False
    numerator = 0
    denominator = 0
    for episode in episodes:
        labels = episode.evaluator_labels.by_tracklet_key
        groups: dict[str, dict[str, int]] = {}
        for tracklet_key, camera_key in zip(
            episode.graph.tracklet_keys,
            episode.graph.camera_keys,
            strict=True,
        ):
            identity = labels[tracklet_key].truth_entity_id
            camera_counts = groups.setdefault(identity, {})
            camera_counts[camera_key] = camera_counts.get(camera_key, 0) + 1
        for camera_counts in groups.values():
            total = sum(camera_counts.values())
            denominator += total * (total - 1) // 2
            denominator -= sum(count * (count - 1) // 2 for count in camera_counts.values())
        for source, target in episode.graph.edge_index.T:
            left_key = episode.graph.tracklet_keys[int(source)]
            right_key = episode.graph.tracklet_keys[int(target)]
            if labels[left_key].truth_entity_id == labels[right_key].truth_entity_id:
                numerator += 1
    return numerator, denominator, True


def _expected_calibration_error(
    probabilities: np.ndarray,
    targets: np.ndarray,
    bins: int,
) -> float:
    boundaries = np.linspace(0.0, 1.0, bins + 1)
    total = probabilities.size
    error = 0.0
    for index in range(bins):
        lower = boundaries[index]
        upper = boundaries[index + 1]
        mask = (
            (probabilities >= lower) & (probabilities <= upper)
            if index == bins - 1
            else (probabilities >= lower) & (probabilities < upper)
        )
        count = int(np.sum(mask))
        if not count:
            continue
        confidence = float(np.mean(probabilities[mask]))
        accuracy = float(np.mean(targets[mask]))
        error += count / total * abs(confidence - accuracy)
    return float(error)


def _available(value: float | int, *, unit: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"available": True, "value": value}
    if unit is not None:
        result["unit"] = unit
    return result


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "value": None, "reason": str(reason)}


def _sigmoid_numpy(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    output = np.empty_like(array)
    positive = array >= 0.0
    output[positive] = 1.0 / (1.0 + np.exp(-array[positive]))
    exponent = np.exp(array[~positive])
    output[~positive] = exponent / (1.0 + exponent)
    return output


def _synchronize_if_cuda(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def _set_fixed_seed(seed: int) -> None:
    random.seed(int(seed))
    np.random.seed(int(seed) % (2**32))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))
    torch.use_deterministic_algorithms(True, warn_only=True)


def _hardware_summary(device: str) -> dict[str, Any]:
    cuda_devices: list[dict[str, Any]] = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            cuda_devices.append(
                {
                    "index": index,
                    "name": properties.name,
                    "total_memory_bytes": int(properties.total_memory),
                }
            )
    return {
        "selected_device": str(torch.device(device)),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_logical_count": os.cpu_count(),
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_runtime_version": torch.version.cuda,
        "cuda_devices": cuda_devices,
    }


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train or evaluate the native D5 tracklet graph model")
    subparsers = parser.add_subparsers(dest="command", required=True)
    train = subparsers.add_parser("train", help="train, validation-calibrate, bundle, and test")
    train.add_argument("--dataset-dir", required=True)
    train.add_argument("--bundle-dir", required=True)
    train.add_argument("--report", required=True)
    train.add_argument("--seed", type=int, default=20260720)
    train.add_argument("--epochs", type=int, default=50)
    train.add_argument("--learning-rate", type=float, default=1.0e-3)
    train.add_argument("--weight-decay", type=float, default=1.0e-5)
    train.add_argument("--hidden-dim", type=int, default=32)
    train.add_argument("--message-passing-steps", type=int, default=2)
    train.add_argument("--dropout", type=float, default=0.0)
    train.add_argument("--graphs-per-step", type=int, default=4)
    train.add_argument("--hard-negative-ratio", type=float, default=3.0)
    train.add_argument("--device", default="cpu")
    train.add_argument("--ece-bins", type=int, default=10)
    train.add_argument("--latency-repeats", type=int, default=3)
    train.add_argument(
        "--development-only",
        action="store_true",
        help="allow labeled-edge calibration but permanently forbid G1/assist admission",
    )
    train.add_argument("--readiness-audit-sha256")
    evaluate = subparsers.add_parser("evaluate", help="strictly load a bundle and evaluate one split")
    evaluate.add_argument("--dataset-dir", required=True)
    evaluate.add_argument("--bundle-dir", required=True)
    evaluate.add_argument("--report", required=True)
    evaluate.add_argument("--split", choices=("validation", "test"), default="test")
    evaluate.add_argument("--device", default="cpu")
    evaluate.add_argument("--ece-bins", type=int, default=10)
    evaluate.add_argument("--latency-repeats", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "train":
        config = TrackletTrainingConfig(
            seed=args.seed,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            hidden_dim=args.hidden_dim,
            message_passing_steps=args.message_passing_steps,
            dropout=args.dropout,
            graphs_per_optimizer_step=args.graphs_per_step,
            hard_negative_ratio=args.hard_negative_ratio,
            device=args.device,
            ece_bins=args.ece_bins,
            latency_repeats=args.latency_repeats,
        )
        report = run_training_pipeline(
            args.dataset_dir,
            args.bundle_dir,
            args.report,
            config=config,
            development_only=args.development_only,
            readiness_audit_sha256=args.readiness_audit_sha256,
        )
        print(
            json.dumps(
                {
                    "admission_status": report["admission_status"],
                    "report": str(args.report),
                    "status": "trained",
                }
            )
        )
        return 0
    run_evaluation_pipeline(
        args.dataset_dir,
        args.bundle_dir,
        args.report,
        split=args.split,
        device=args.device,
        ece_bins=args.ece_bins,
        latency_repeats=args.latency_repeats,
    )
    print(json.dumps({"report": str(args.report), "status": "evaluated"}))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI.
    raise SystemExit(main())


__all__ = [
    "EVALUATION_REPORT_SCHEMA_VERSION",
    "TRAINING_REPORT_SCHEMA_VERSION",
    "TrackletTrainingConfig",
    "TrackletTrainingResult",
    "evaluate_tracklet_edge_model",
    "fit_validation_temperature",
    "run_evaluation_pipeline",
    "run_training_pipeline",
    "select_validation_threshold",
    "train_tracklet_edge_model",
]
